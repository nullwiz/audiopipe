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
    if device:
        if device == "cpu":
            return "cpu"
        elif device == "cuda" and torch.cuda.is_available():
            return "cuda"
        elif (
            device == "mps"
            and hasattr(torch.backends, "mps")
            and torch.backends.mps.is_available()
        ):
            return "mps"

    if torch.cuda.is_available():
        return "cuda"
    elif (
        platform.system() == "Darwin"
        and hasattr(torch.backends, "mps")
        and torch.backends.mps.is_available()
    ):
        return "mps"
    else:
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


def transcribe_segment(
    audio_path,
    output_path,
    language=None,
    current_segment=None,
    total_segments=None,
    device=None,
):
    """Transcribe an audio segment using insanely-fast-whisper CLI"""
    device_param = get_device(device)
    device_id = "0" if device_param == "cuda" else device_param

    cmd = [
        "insanely-fast-whisper",
        "--file-name",
        audio_path,
        "--transcript-path",
        output_path,
        "--model-name",
        "openai/whisper-large-v3",
        "--timestamp",
        "word",
        "--device-id",
        device_id,
        "--batch-size",
        "16",
    ]

    if language:
        cmd.extend(["--language", language])

    desc = "🗣️ Transcribing segments"
    if current_segment is not None and total_segments is not None:
        desc = f"🗣️ Transcribing segment {current_segment}/{total_segments}"

    try:
        run_command_with_progress(cmd, desc, expected_steps=None)
    except RuntimeError as e:
        raise RuntimeError(f"Transcription failed: {str(e)}")

    try:
        with open(output_path) as f:
            result = json.load(f)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse transcription output: {str(e)}")
    except FileNotFoundError:
        raise RuntimeError("Transcription output file not found")

    segments = []
    for chunk in result["chunks"]:
        if chunk["timestamp"][0] is None or chunk["timestamp"][1] is None:
            continue
        segments.append(
            {
                "text": chunk["text"],
                "start": chunk["timestamp"][0],
                "end": chunk["timestamp"][1],
            }
        )
    return segments


def process_speaker_segments(
    vocals_path, diarization_data, output_dir, language=None, device=None
):
    """Process each speaker's segments and transcribe them"""
    print("\n[3/3] Running transcription")
    os.makedirs(output_dir, exist_ok=True)

    speaker_segments = {}
    for segment in diarization_data["segments"]:
        speaker = segment["speaker"]
        if speaker not in speaker_segments:
            speaker_segments[speaker] = []
        speaker_segments[speaker].append(segment)

    all_transcriptions = []

    full_audio = AudioSegment.from_wav(vocals_path)

    MAX_CHUNK_DURATION = 30

    for speaker, segments in speaker_segments.items():
        speaker_dir = os.path.join(output_dir, speaker)
        os.makedirs(speaker_dir, exist_ok=True)

        segments.sort(key=lambda x: x["start"])

        chunks = []
        current_chunk = []
        current_duration = 0

        for segment in segments:
            duration = segment["end"] - segment["start"]

            if duration > MAX_CHUNK_DURATION:
                if current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = []
                    current_duration = 0

                start = segment["start"]
                while start < segment["end"]:
                    end = min(start + MAX_CHUNK_DURATION, segment["end"])
                    chunks.append(
                        [{"start": start, "end": end, "speaker": segment["speaker"]}]
                    )
                    start = end
                continue

            if current_duration + duration > MAX_CHUNK_DURATION:
                chunks.append(current_chunk)
                current_chunk = []
                current_duration = 0

            current_chunk.append(segment)
            current_duration += duration

        if current_chunk:
            chunks.append(current_chunk)

        for chunk_idx, chunk_segments in enumerate(chunks):
            chunk_audio = AudioSegment.empty()
            segment_offsets = []
            current_offset = 0

            for segment in chunk_segments:
                start_ms = int(segment["start"] * 1000)
                end_ms = int(segment["end"] * 1000)
                segment_audio = full_audio[start_ms:end_ms]

                segment_offsets.append(
                    {
                        "concat_start": current_offset / 1000,
                        "orig_start": segment["start"],
                        "duration": (end_ms - start_ms) / 1000,
                    }
                )

                current_offset += len(segment_audio)
                chunk_audio += segment_audio

            chunk_path = os.path.join(speaker_dir, f"chunk_{chunk_idx}.wav")
            transcript_path = os.path.join(speaker_dir, f"chunk_{chunk_idx}.json")

            try:
                chunk_audio.export(chunk_path, format="wav", parameters=["-y"])

                display.update_log(
                    f"🗣️ Transcribing {speaker}'s audio (chunk {chunk_idx + 1}/{len(chunks)})..."
                )
                transcription = transcribe_segment(
                    chunk_path, transcript_path, language=language, device=device
                )

                for trans in transcription:
                    # Ensure we have valid float values
                    trans_start = float(trans["start"]) if trans["start"] is not None else 0.0
                    trans_end = float(trans["end"]) if trans["end"] is not None else 0.0
                    
                    if trans_start >= trans_end:
                        logging.warning(f"Skipping invalid segment: start={trans_start}, end={trans_end}")
                        continue

                    for offset in segment_offsets:
                        # Calculate segment boundaries
                        offset_end = offset["concat_start"] + offset["duration"]
                        
                        if (
                            trans_start >= offset["concat_start"]
                            and trans_start < offset_end
                        ):
                            # Calculate adjusted timestamps with proper type checking
                            try:
                                orig_start = offset["orig_start"] + (trans_start - offset["concat_start"])
                                
                                # Handle potential None or invalid values
                                orig_end = min(
                                    offset["orig_start"] + offset["duration"],
                                    offset["orig_start"] + (trans_end - offset["concat_start"])
                                )
                                
                                # Ensure we have valid values
                                if orig_end <= orig_start:
                                    logging.warning(f"Invalid segment timing: start={orig_start}, end={orig_end}")
                                    continue
                                
                                all_transcriptions.append(
                                    {
                                        "speaker": speaker,
                                        "text": trans["text"],
                                        "start": orig_start,
                                        "end": orig_end,
                                    }
                                )
                            except (TypeError, ValueError) as e:
                                logging.error(f"Error processing segment: {e}, segment: {trans}, offset: {offset}")
                            break

            except Exception as e:
                logging.error(
                    f"Failed to process {speaker} chunk {chunk_idx}: {str(e)}"
                )
                if os.path.exists(chunk_path):
                    os.remove(chunk_path)
                if os.path.exists(transcript_path):
                    os.remove(transcript_path)
                raise RuntimeError(
                    f"Processing failed for {speaker} chunk {chunk_idx}: {str(e)}"
                ) from e
            finally:
                if os.path.exists(chunk_path):
                    os.remove(chunk_path)
                if os.path.exists(transcript_path):
                    os.remove(transcript_path)

    all_transcriptions.sort(key=lambda x: x["start"])
    return all_transcriptions


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
            vocals_path, diarization_data, output_dir, language, device
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
