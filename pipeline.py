import os
import json
import subprocess
import logging
import time
import torch
from pydub import AudioSegment
import sys
import select
import platform


class RetroDisplay:
    def __init__(self):
        self.progress_line = ""
        self.log_line = ""
        self.last_log = ""
        self.initialized = False
        self.num_lines = 0
        self.update_count = 0
        
    def _clear_lines(self, num_lines):
        """Clear the specified number of lines from the console"""
        if num_lines <= 0:
            return
        
        # Move cursor up and clear lines
        sys.stdout.write(f"\033[{num_lines}F")
        for _ in range(num_lines):
            sys.stdout.write("\033[K\n")
        sys.stdout.write(f"\033[{num_lines}F")
        
    def update_progress(self, line):
        if not self.initialized:
            print("\n\n")  # Create initial space for our display
            self.initialized = True
            self.num_lines = 2
            
        # Only update if the line changed to avoid flickering
        if line != self.progress_line:
            self.progress_line = line
            self._refresh()
            
    def update_log(self, line):
        if not self.initialized:
            print("\n\n")  # Create initial space
            self.initialized = True
            self.num_lines = 2
            
        # Only update if it's a new log message to avoid duplicates
        if line and line != self.last_log:
            self.log_line = line
            self.last_log = line
            self._refresh()
            
    def _refresh(self):
        """Refresh the display by clearing and redrawing lines"""
        if not (self.progress_line or self.log_line):
            return
        
        # Calculate lines needed for display
        progress_lines = self.progress_line.count('\n') + 1 if self.progress_line else 0
        log_lines = self.log_line.count('\n') + 1 if self.log_line else 0
        total_lines = progress_lines + log_lines
        
        # Clear previous display
        self._clear_lines(self.num_lines)
        
        # Draw new content
        if self.progress_line:
            print(self.progress_line)
        
        if self.log_line:
            print(self.log_line)
            
        # Update line count
        self.num_lines = total_lines
        sys.stdout.flush()
        
        # Increment update counter (useful for debugging)
        self.update_count += 1


display = RetroDisplay()


class TqdmLoggingHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            display.update_log(msg)
            self.flush()
        except Exception:
            self.handleError(record)


logging.basicConfig(filename="pipeline.log", level=logging.INFO, format="%(message)s")
console_handler = TqdmLoggingHandler()
console_handler.setFormatter(logging.Formatter("%(message)s"))
logging.getLogger().addHandler(console_handler)


def get_device(device=None):
    """Determine the appropriate device to use"""
    print(f"DEBUG: get_device called with parameter: {device}")
    
    # Check environment variables that might influence device selection
    force_cpu = os.environ.get("FORCE_CPU") == "1"
    is_ci = os.environ.get("GITHUB_ACTIONS") == "true" or os.environ.get("AUDIOPIPE_TESTING") == "1"
    
    print(f"DEBUG: Environment checks:")
    print(f"  - FORCE_CPU env var: {os.environ.get('FORCE_CPU', 'not set')}")
    print(f"  - CI environment detected: {is_ci}")
    
    # Always return CPU if forced by environment variables
    if force_cpu or is_ci:
        print(f"DEBUG: Forcing CPU due to environment settings (FORCE_CPU={force_cpu}, is_ci={is_ci})")
        return "cpu"
    
    # Check available hardware
    cuda_available = torch.cuda.is_available()
    mps_available = (
        platform.system() == "Darwin" 
        and hasattr(torch.backends, "mps") 
        and torch.backends.mps.is_available()
    )
    
    print(f"DEBUG: Hardware availability:")
    print(f"  - CUDA available: {cuda_available}")
    print(f"  - MPS available: {mps_available}")
    
    # If specific device requested
    if device:
        if device == "cpu":
            print(f"DEBUG: CPU explicitly requested")
            return "cpu"
        elif device == "cuda" and cuda_available:
            print(f"DEBUG: CUDA explicitly requested and available")
            return "cuda"
        elif device == "mps" and mps_available:
            print(f"DEBUG: MPS explicitly requested and available")
            return "mps"
        else:
            print(f"DEBUG: Requested device '{device}' not available or invalid")
    
    # Auto-select best available device
    if cuda_available:
        print(f"DEBUG: Auto-selecting CUDA (best available)")
        return "cuda"
    elif mps_available:
        print(f"DEBUG: Auto-selecting MPS (best available)")
        return "mps"
    else:
        print(f"DEBUG: Auto-selecting CPU (only option available)")
        return "cpu"


def run_command_with_progress(cmd, desc, expected_steps=None):
    """Run a command and show progress bar"""
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        bufsize=1,
    )

    spinner = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    progress = 0
    start_time = time.time()
    last_update = start_time
    stderr_output = []

    # Patterns to filter out spam
    skip_patterns = [
        "configuration:",
        "Voila!",
        "Your file has been transcribed",
        "go check it out",
    ]

    important_patterns = [
        "Error:",
        "Warning:",
        "Failed:",
        "Exception:",
        "Processing",
        "Loading",
        "Initializing",
    ]

    # Track seen messages to avoid duplicates
    seen_messages = set()

    while True:
        reads = [process.stdout, process.stderr]
        readable, _, _ = select.select(reads, [], [], 0.1)

        current_time = time.time()

        if current_time - last_update >= 0.1:
            elapsed = current_time - start_time
            if expected_steps:
                progress = min(int(elapsed * 5), expected_steps)
                percentage = (progress / expected_steps) * 100
                bar_length = 30
                filled = int(bar_length * progress / expected_steps)
                bar = "█" * filled + "░" * (bar_length - filled)
                progress_line = f"{desc} [{bar}] {percentage:3.0f}% ({progress}/{expected_steps}) [{elapsed:.1f}s]"
            else:
                spin_idx = int(current_time * 10) % len(spinner)
                spin_char = spinner[spin_idx]
                progress_line = f"{desc} {spin_char} [{elapsed:.1f}s]"

            display.update_progress(progress_line)
            last_update = current_time

        for stream in readable:
            output = stream.readline()
            if output:
                output = output.strip()

                # Skip duplicate messages and filtered messages
                if output in seen_messages or any(pattern in output for pattern in skip_patterns):
                    continue
                
                seen_messages.add(output)

                if stream == process.stderr:
                    logging.warning(output)
                    stderr_output.append(output)
                else:
                    logging.info(output)

                if any(pattern in output for pattern in important_patterns):
                    if stream == process.stderr:
                        display.update_log(f"⚠️  {output}")
                    else:
                        display.update_log(output)

        if process.poll() is not None:
            break

    if process.returncode != 0:
        remaining_stderr = process.stderr.read().strip()
        if remaining_stderr:
            stderr_output.append(remaining_stderr)
            logging.error(remaining_stderr)

        error_msg = "\n".join(stderr_output) if stderr_output else "Unknown error"
        display.update_log(f"❌ Error: {error_msg}")
        raise RuntimeError(error_msg)


def run_demucs(input_audio):
    """Run demucs separation and get vocals"""
    print("\n[1/3] Running audio separation")
    run_command_with_progress(
        ["python", "-u", "dem.py", input_audio], "🎵 Separating vocals"
    )
    return "output/combined_vocals.wav"


def run_diarization(vocals_path, num_speakers=None):
    """Run speaker diarization"""
    print("\n[2/3] Running speaker diarization")
    cmd = ["python", "-u", "diarize.py", vocals_path]
    if num_speakers:
        cmd.extend(["-n", str(num_speakers)])

    run_command_with_progress(cmd, "🎙️ Diarizing speakers")
    return vocals_path.replace(".wav", "_diarized.json")


def extract_audio_segment(audio_path, start, end, output_path):
    """Extract a segment from audio file using pydub"""
    audio = AudioSegment.from_wav(audio_path)
    start_ms = int(start * 1000)
    end_ms = int(end * 1000)
    segment = audio[start_ms:end_ms]
    segment.export(output_path, format="wav", parameters=["-y"])


def transcribe_segment(segment_path, output_json, model="openai/whisper-medium", language=None, use_gpu=None, testing=False):
    """Transcribe an audio segment using the insanely-fast-whisper CLI."""
    # Check for test environment
    is_ci = os.environ.get('CI', 'false').lower() == 'true'
    force_cpu = os.environ.get('FORCE_CPU', 'false').lower() == 'true' or os.environ.get('FORCE_CPU', '0') == '1'
    testing_env = os.environ.get('AUDIOPIPE_TESTING', 'false').lower() == 'true' or os.environ.get('AUDIOPIPE_TESTING', '0') == '1'
    
    # Debug output for CI environment
    if is_ci or force_cpu or testing_env:
        print(f"DEBUG: CI={is_ci}, FORCE_CPU={force_cpu}, AUDIOPIPE_TESTING={testing_env}")
    
    desc = f"🗣️ Transcribing segments"
    
    # Determine device settings based on environment and available hardware
    if force_cpu or testing_env or is_ci:
        device_id = "-1"  # -1 is used to indicate CPU
    else:
        # For CUDA, use device 0 by default
        device_id = "0" if torch.cuda.is_available() else "-1"
    
    # Debug output for device selection
    if is_ci or force_cpu or testing_env:
        print(f"DEBUG: Selected device_id: {device_id}")
    
    # Base command with required arguments
    cmd = [
        "insanely-fast-whisper",
        "--file-name", segment_path,
        "--model-name", model,
        "--output-file", output_json,
        "--device-id", device_id,
    ]
    
    # Add language parameter if specified
    if language:
        cmd.extend(["--language", language])
    
    # Add batch size if using GPU
    if device_id != "-1":
        cmd.extend(["--batch-size", "32"])
    
    try:
        run_command_with_progress(cmd, desc, expected_steps=None)
        # Check if the output file was created and has content
        if not os.path.exists(output_json) or os.path.getsize(output_json) == 0:
            raise RuntimeError("Transcription output file was not created or is empty")
        
    except Exception as e:
        # Make sure we capture and report any errors during transcription
        logging.error(f"Error during transcription: {str(e)}")
        print(f"DEBUG: Error during transcription: {str(e)}")
        raise RuntimeError(f"Transcription failed: {str(e)}")


def process_speaker_segments(
    speakers_segments,
    audio_path,
    output_dir,
    chunk_max_duration=30.0,
    language=None,
    device=None,
):
    """Process the speaker segments, create chunks and transcribe them."""
    display.update_progress(f"🔄 Processing {len(speakers_segments)} speakers...")
    
    # Initialize output structure
    processed_segments = {}
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Process each speaker
    for speaker_idx, (speaker, segments) in enumerate(speakers_segments.items(), 1):
        speaker_dir = os.path.join(output_dir, speaker)
        os.makedirs(speaker_dir, exist_ok=True)
        
        display.update_progress(f"🔊 Processing {speaker} ({speaker_idx}/{len(speakers_segments)})")
        
        # Sort segments by start time to maintain chronological order
        segments.sort(key=lambda x: x["start"])
        
        # Initialize chunks for this speaker
        chunks = []
        current_chunk = []
        current_duration = 0
        
        # Group segments into chunks based on max duration
        for segment in segments:
            segment_duration = segment["end"] - segment["start"]
            
            # If adding this segment exceeds the max duration, start a new chunk
            if current_duration + segment_duration > chunk_max_duration and current_chunk:
                chunks.append(current_chunk)
                current_chunk = [segment]
                current_duration = segment_duration
            else:
                current_chunk.append(segment)
                current_duration += segment_duration
        
        # Add the last chunk if not empty
        if current_chunk:
            chunks.append(current_chunk)
        
        # Initialize processed segments for this speaker
        processed_segments[speaker] = []
        
        # Process each chunk
        for chunk_idx, chunk in enumerate(chunks):
            try:
                display.update_progress(f"📄 Processing {speaker} chunk {chunk_idx+1}/{len(chunks)}")
                
                # Extract audio for this chunk
                chunk_start = chunk[0]["start"]
                chunk_end = chunk[-1]["end"]
                chunk_audio_path = os.path.join(speaker_dir, f"chunk_{chunk_idx}.wav")
                extract_audio_segment(audio_path, chunk_start, chunk_end, chunk_audio_path)
                
                # Transcribe the chunk
                chunk_json_path = os.path.join(speaker_dir, f"chunk_{chunk_idx}.json")
                
                # Call the updated transcribe_segment function with the correct parameters
                transcribe_segment(
                    segment_path=chunk_audio_path,
                    output_json=chunk_json_path,
                    model="openai/whisper-large-v3", 
                    language=language,
                    use_gpu=(device != "cpu")
                )
                
                # Load and parse the transcription result
                with open(chunk_json_path, 'r') as f:
                    result = json.load(f)
                
                # Process the transcription results
                segments_from_chunk = []
                for item in result["chunks"]:
                    if item["timestamp"][0] is None or item["timestamp"][1] is None:
                        continue
                    
                    # Adjust timestamps to be relative to the original audio
                    segment_data = {
                        "text": item["text"],
                        "start": chunk_start + item["timestamp"][0],
                        "end": chunk_start + item["timestamp"][1],
                    }
                    segments_from_chunk.append(segment_data)
                
                # Add processed segments to the speaker's data
                processed_segments[speaker].extend(segments_from_chunk)
                
            except Exception as e:
                logging.error(f"Error processing {speaker} chunk {chunk_idx}: {str(e)}")
                display.update_progress(f"❌ Error processing {speaker} chunk {chunk_idx}: {str(e)}")
                print(f"DEBUG: Error processing {speaker} chunk {chunk_idx}: {str(e)}")
                # Continue with the next chunk instead of failing the entire process
                continue
        
        # Sort the processed segments by start time
        processed_segments[speaker].sort(key=lambda x: x["start"])
    
    return processed_segments


def main(input_audio, num_speakers=None, language=None, start_step=1, device=None):
    """Run the complete pipeline"""
    start_time = time.time()

    try:
        if start_step <= 1:
            vocals_path = run_demucs(input_audio)
        else:
            vocals_path = "output/combined_vocals.wav"
            if not os.path.exists(vocals_path):
                raise FileNotFoundError(
                    f"Cannot skip to step {start_step}: {vocals_path} not found"
                )

        if start_step <= 2:
            diarization_path = run_diarization(vocals_path, num_speakers)
        else:
            diarization_path = vocals_path.replace(".wav", "_diarized.json")
            if not os.path.exists(diarization_path):
                raise FileNotFoundError(
                    f"Cannot skip to step {start_step}: {diarization_path} not found"
                )

        with open(diarization_path) as f:
            diarization_data = json.load(f)

        output_dir = "output/speakers"
        transcriptions = process_speaker_segments(
            diarization_data["speakers"], vocals_path, output_dir, language, device
        )

        output_path = os.path.join("output", "final_transcription.json")
        output_data = {
            "speakers": diarization_data["speakers"],
            "segments": transcriptions,
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

        elapsed_time = time.time() - start_time
        print(f"\n✨ Pipeline complete in {elapsed_time:.1f}s!")
        print(f"📝 Output saved to: {output_path}")
        print(f"📊 Found {len(diarization_data['speakers'])} speakers")
        print(f"🔤 Transcribed {len(transcriptions)} segments")
        print("\nCheck pipeline.log for detailed logs")
        return output_path

    except Exception as e:
        logging.error(f"Pipeline failed: {str(e)}")
        print(f"\n❌ Pipeline failed: {str(e)}")
        print("📝 Check pipeline.log for detailed logs")
        raise


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="End-to-end audio processing pipeline")
    parser.add_argument("input_audio", help="Path to input audio file")
    parser.add_argument(
        "--num-speakers", "-n", type=int, help="Number of speakers (optional)"
    )
    parser.add_argument(
        "--language",
        "-l",
        help="Language code for transcription (e.g. 'en', 'es', 'fr')",
    )
    parser.add_argument(
        "--start-step",
        "-s",
        type=int,
        choices=[1, 2, 3],
        default=1,
        help="Start from step: 1=demucs, 2=diarization, 3=transcription",
    )
    parser.add_argument(
        "--device",
        "-d",
        choices=["cpu", "cuda", "mps"],
        help="Device to use for processing (auto-detected if not specified)",
    )
    args = parser.parse_args()

    main(
        args.input_audio, args.num_speakers, args.language, args.start_step, args.device
    )
