from __future__ import annotations

import json
import logging
import os
import platform
import select
import subprocess
import sys
import time
from typing import Any

import torch
from pydub import AudioSegment


class RetroDisplay:
    """Terminal display manager for progress and log updates."""

    def __init__(self) -> None:
        self.progress_line: str = ""
        self.log_line: str = ""
        self.last_log: str = ""
        self.initialized: bool = False
        self.num_lines: int = 0
        self.update_count: int = 0

    def _clear_lines(self, num_lines: int) -> None:
        """Clear the specified number of lines from the console."""
        if num_lines <= 0:
            return

        # Move cursor up and clear lines
        sys.stdout.write(f"\033[{num_lines}F")
        for _ in range(num_lines):
            sys.stdout.write("\033[K\n")
        sys.stdout.write(f"\033[{num_lines}F")

    def update_progress(self, line: str) -> None:
        """Update the progress display line."""
        if not self.initialized:
            print("\n\n")  # Create initial space for our display
            self.initialized = True
            self.num_lines = 2

        # Only update if the line changed to avoid flickering
        if line != self.progress_line:
            self.progress_line = line
            self._refresh()

    def update_log(self, line: str) -> None:
        """Update the log display line."""
        if not self.initialized:
            print("\n\n")  # Create initial space
            self.initialized = True
            self.num_lines = 2

        # Only update if it's a new log message to avoid duplicates
        if line and line != self.last_log:
            self.log_line = line
            self.last_log = line
            self._refresh()

    def _refresh(self) -> None:
        """Refresh the display by clearing and redrawing lines."""
        if not (self.progress_line or self.log_line):
            return

        # Calculate lines needed for display
        progress_lines = self.progress_line.count("\n") + 1 if self.progress_line else 0
        log_lines = self.log_line.count("\n") + 1 if self.log_line else 0
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
    """Custom logging handler that integrates with RetroDisplay."""

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record through the display system."""
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


def get_device(device: str | None = None) -> str:
    """Determine the appropriate device to use for processing."""
    print(f"DEBUG: get_device called with parameter: {device}")

    # Check environment variables that might influence device selection
    force_cpu = os.environ.get("FORCE_CPU") == "1"
    github_actions = os.environ.get("GITHUB_ACTIONS") == "true"
    audiopipe_testing = os.environ.get("AUDIOPIPE_TESTING") == "1"
    is_ci = github_actions or audiopipe_testing

    print("DEBUG: Environment checks:")
    print(f"  - FORCE_CPU env var: {os.environ.get('FORCE_CPU', 'not set')}")
    print(f"  - GITHUB_ACTIONS env var: {os.environ.get('GITHUB_ACTIONS', 'not set')}")
    print(f"  - AUDIOPIPE_TESTING env var: {os.environ.get('AUDIOPIPE_TESTING', 'not set')}")
    print(f"  - CI environment detected: {is_ci}")

    # Always return CPU if forced by environment variables
    if force_cpu or is_ci:
        print(
            f"DEBUG: Forcing CPU due to environment settings "
            f"(FORCE_CPU={force_cpu}, is_ci={is_ci})"
        )
        return "cpu"

    # Check available hardware
    cuda_available = torch.cuda.is_available()

    # Additional CUDA debugging
    if cuda_available:
        try:
            cuda_device_count = torch.cuda.device_count()
            current_device = torch.cuda.current_device()
            device_name = torch.cuda.get_device_name(current_device)
            print(f"DEBUG: CUDA device count: {cuda_device_count}")
            print(f"DEBUG: Current CUDA device: {current_device}")
            print(f"DEBUG: CUDA device name: {device_name}")
        except Exception as e:
            print(f"DEBUG: Error getting CUDA info: {e}")
            cuda_available = False

    mps_available = (
        platform.system() == "Darwin"
        and hasattr(torch.backends, "mps")
        and torch.backends.mps.is_available()
    )

    print("DEBUG: Hardware availability:")
    print(f"  - CUDA available: {cuda_available}")
    print(f"  - MPS available: {mps_available}")
    print(f"  - Platform: {platform.system()}")

    # If specific device requested
    if device:
        if device == "cpu":
            print("DEBUG: CPU explicitly requested")
            return "cpu"
        if device == "cuda" and cuda_available:
            print("DEBUG: CUDA explicitly requested and available")
            return "cuda"
        if device == "mps" and mps_available:
            print("DEBUG: MPS explicitly requested and available")
            return "mps"
        print(f"DEBUG: Requested device '{device}' not available or invalid, falling back to CPU")
        return "cpu"

    # Auto-select best available device
    if cuda_available:
        print("DEBUG: Auto-selecting CUDA (best available)")
        return "cuda"
    if mps_available:
        print("DEBUG: Auto-selecting MPS (best available)")
        return "mps"
    print("DEBUG: Auto-selecting CPU (only option available)")
    return "cpu"


def run_command_with_progress(
    cmd: list[str], desc: str, expected_steps: int | None = None
) -> None:
    """Run a command and show progress bar."""
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
                progress_line = (
                    f"{desc} [{bar}] {percentage:3.0f}% "
                    f"({progress}/{expected_steps}) [{elapsed:.1f}s]"
                )
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
                if output in seen_messages or any(
                    pattern in output for pattern in skip_patterns
                ):
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
        if process.stderr:
            remaining_stderr = process.stderr.read().strip()
            if remaining_stderr:
                stderr_output.append(remaining_stderr)
                logging.error(remaining_stderr)

        error_msg = "\n".join(stderr_output) if stderr_output else "Unknown error"
        display.update_log(f"❌ Error: {error_msg}")
        raise RuntimeError(error_msg)


def run_demucs(input_audio: str) -> str:
    """Run demucs separation and get vocals."""
    print("\n[1/3] Running audio separation")
    run_command_with_progress(
        ["python", "-u", "dem.py", input_audio], "🎵 Separating vocals"
    )
    return "output/combined_vocals.wav"


def run_diarization(vocals_path: str, num_speakers: int | None = None) -> str:
    """Run speaker diarization with improved parameters to reduce over-segmentation."""
    print("\n[2/3] Running speaker diarization")
    cmd = ["python", "-u", "diarize.py", vocals_path]

    if num_speakers:
        cmd.extend(["-n", str(num_speakers)])
    else:
        cmd.extend(["--min-speakers", "1", "--max-speakers", "8"])

    run_command_with_progress(cmd, "🎙️ Diarizing speakers")
    return vocals_path.replace(".wav", "_diarized.json")


def extract_audio_segment(
    audio_path: str, start: float, end: float, output_path: str
) -> None:
    """Extract a segment from audio file using pydub."""
    audio = AudioSegment.from_wav(audio_path)
    start_ms = int(start * 1000)
    end_ms = int(end * 1000)
    segment = audio[start_ms:end_ms]
    segment.export(output_path, format="wav", parameters=["-y"])


def run_complete_transcription(
    audio_path: str, language: str | None = None, device: str | None = None
) -> dict[str, Any]:
    """Run insanely-fast-whisper on complete audio file."""
    display.update_progress("🎙️ Running Whisper on complete audio file...")

    # Determine the actual device to use
    actual_device = get_device(device)
    print(f"DEBUG: Transcription using device: {actual_device}")

    output_json = "output/complete_whisper_transcription.json"
    os.makedirs("output", exist_ok=True)

    cmd = [
        "insanely-fast-whisper",
        "--file-name",
        audio_path,
        "--model-name",
        "openai/whisper-large-v3",
        "--transcript-path",
        output_json,
    ]

    if language:
        cmd.extend(["--language", language])
    else:
        cmd.extend(["--language", "en"])

    # Add GPU configuration only if using CUDA and it's actually available
    if actual_device == "cuda" and torch.cuda.is_available():
        print("DEBUG: Adding CUDA configuration to Whisper command")
        cmd.extend(["--device-id", "0"])
        cmd.extend(["--batch-size", "32"])
    else:
        print(f"DEBUG: Using CPU mode for Whisper (device: {actual_device})")

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600, check=False
        )

        if result.returncode != 0:
            logging.error(f"Whisper transcription failed: {result.stderr}")
            raise RuntimeError(f"Whisper transcription failed: {result.stderr}")

        if os.path.exists(output_json):
            with open(output_json, encoding="utf-8") as f:
                data = json.load(f)
            display.update_progress(
                f"✅ Whisper completed: {len(data.get('chunks', []))} chunks"
            )
            return data
        raise RuntimeError(f"Transcription output file not found: {output_json}")

    except subprocess.TimeoutExpired:
        raise RuntimeError("Whisper transcription timed out")
    except Exception as e:
        logging.exception(f"Error running Whisper: {e}")
        raise


def simple_speaker_mapping(
    whisper_chunks: list[dict[str, Any]], diarization_segments: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Simple mapping: for each Whisper chunk, find overlapping diarization segment.

    This could be improved significantly, but for now we just find the best match
    based on overlap.
    """
    display.update_progress("🔗 Mapping speakers to transcription...")

    mapped_segments = []

    for chunk in whisper_chunks:
        # Get chunk timing
        if "timestamp" not in chunk or len(chunk["timestamp"]) != 2:
            continue

        chunk_start, chunk_end = chunk["timestamp"]
        if chunk_start is None or chunk_end is None:
            continue

        chunk_text = chunk.get("text", "").strip()
        if not chunk_text:
            continue

        # Find overlapping diarization segment
        best_speaker = None
        max_overlap = 0

        for diar_seg in diarization_segments:
            diar_start = diar_seg["start"]
            diar_end = diar_seg["end"]

            # Calculate overlap
            overlap_start = max(chunk_start, diar_start)
            overlap_end = min(chunk_end, diar_end)

            if overlap_start < overlap_end:
                overlap_duration = overlap_end - overlap_start
                if overlap_duration > max_overlap:
                    max_overlap = overlap_duration
                    best_speaker = diar_seg["speaker"]

        # If no overlap found, find closest segment
        if not best_speaker:
            chunk_center = (chunk_start + chunk_end) / 2
            min_distance = float("inf")

            for diar_seg in diarization_segments:
                diar_center = (diar_seg["start"] + diar_seg["end"]) / 2
                distance = abs(chunk_center - diar_center)

                if distance < min_distance:
                    min_distance = distance
                    best_speaker = diar_seg["speaker"]

        # Add mapped segment
        if best_speaker:
            mapped_segments.append(
                {
                    "text": chunk_text,
                    "start": round(chunk_start, 3),
                    "end": round(chunk_end, 3),
                    "speaker": best_speaker,
                }
            )

    display.update_progress(f"✅ Mapped {len(mapped_segments)} segments")
    return mapped_segments


def chop_audio(input_audio: str, chunk_duration: int = 900) -> list[dict[str, Any]]:
    """Split audio into chunks of specified duration."""
    display.update_progress(
        f"🔪 Chopping audio into {chunk_duration // 60}-minute chunks..."
    )

    audio = AudioSegment.from_file(input_audio)
    total_duration = len(audio) / 1000  # Convert to seconds
    chunk_duration_ms = chunk_duration * 1000

    chunks = []
    chunk_paths = []

    for i in range(0, len(audio), chunk_duration_ms):
        chunk = audio[i : i + chunk_duration_ms]
        chunk_start_time = i / 1000
        chunk_end_time = min((i + chunk_duration_ms) / 1000, total_duration)

        # Create chunk filename
        chunk_filename = f"output/chunk_{i // chunk_duration_ms:03d}.wav"
        os.makedirs("output", exist_ok=True)

        # Export chunk
        chunk.export(chunk_filename, format="wav")

        chunks.append(
            {
                "path": chunk_filename,
                "start_time": chunk_start_time,
                "end_time": chunk_end_time,
                "index": i // chunk_duration_ms,
            }
        )
        chunk_paths.append(chunk_filename)

    display.update_progress(f"✅ Created {len(chunks)} audio chunks")
    return chunks


def merge_chunk_outputs(
    chunk_results: list[tuple[dict[str, Any], list[dict[str, Any]]]],
) -> list[dict[str, Any]]:
    """Merge transcription outputs from multiple chunks into chronological order."""
    display.update_progress("🔗 Merging chunk transcriptions...")

    all_segments = []

    for chunk_info, segments in chunk_results:
        chunk_start_offset = chunk_info["start_time"]

        # Adjust timestamps to be relative to original audio
        for segment in segments:
            adjusted_segment = segment.copy()
            adjusted_segment["start"] += chunk_start_offset
            adjusted_segment["end"] += chunk_start_offset
            all_segments.append(adjusted_segment)

    # Sort by start time for chronological output
    all_segments.sort(key=lambda x: x["start"])

    display.update_progress(
        f"✅ Merged {len(all_segments)} segments from {len(chunk_results)} chunks"
    )
    return all_segments


def process_single_chunk(chunk_info, num_speakers=None, language=None, device=None):
    """Process a single audio chunk through the complete pipeline."""
    chunk_path = chunk_info["path"]
    chunk_index = chunk_info["index"]

    display.update_progress(f"🔄 Processing chunk {chunk_index + 1}...")

    # Step 1: Run demucs on chunk
    vocals_path = run_demucs(chunk_path)

    # Step 2: Run diarization on chunk vocals
    diarization_path = run_diarization(vocals_path, num_speakers)

    # Step 3: Load diarization data
    with open(diarization_path) as f:
        diarization_data = json.load(f)

    # Step 4: Run complete transcription on chunk vocals
    whisper_data = run_complete_transcription(vocals_path, language, device)

    if not whisper_data or "chunks" not in whisper_data:
        raise RuntimeError(f"Whisper transcription failed for chunk {chunk_index}")

    # Step 5: Simple speaker mapping
    mapped_segments = simple_speaker_mapping(
        whisper_data["chunks"], diarization_data["segments"]
    )

    return chunk_info, mapped_segments


def main(
    input_audio,
    num_speakers=None,
    language=None,
    start_step=1,
    device=None,
    chop=False,
):
    """Run the complete pipeline with optional audio chopping."""
    start_time = time.time()

    try:
        if chop:
            # Chopped processing mode
            display.update_progress("🔪 Running pipeline with audio chopping...")

            # Step 1: Chop audio into 15-minute chunks
            chunks = chop_audio(input_audio)

            # Step 2: Process each chunk
            chunk_results = []
            for chunk_info in chunks:
                try:
                    chunk_info, segments = process_single_chunk(
                        chunk_info, num_speakers, language, device
                    )
                    chunk_results.append((chunk_info, segments))
                except Exception as e:
                    logging.warning(
                        f"Failed to process chunk {chunk_info['index']}: {e}"
                    )
                    continue

            if not chunk_results:
                raise RuntimeError("No chunks were successfully processed")

            # Step 3: Merge chunk outputs
            mapped_segments = merge_chunk_outputs(chunk_results)

        else:
            # Standard single-file processing mode
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

            # Step 3: Run complete transcription on audio file
            display.update_progress("\n[3/3] Running complete audio transcription")
            whisper_data = run_complete_transcription(vocals_path, language, device)

            if not whisper_data or "chunks" not in whisper_data:
                raise RuntimeError("Whisper transcription failed")

            # Step 4: Simple speaker mapping
            display.update_progress("Mapping speakers to transcription...")
            mapped_segments = simple_speaker_mapping(
                whisper_data["chunks"], diarization_data["segments"]
            )

            if not mapped_segments:
                raise RuntimeError("No segments could be mapped to speakers")

            # Sort by start time for chronological output
            mapped_segments.sort(key=lambda x: x["start"])

        # Save final output (same for both modes)
        output_path = os.path.join("output", "final_transcription.json")
        output_data = {"segments": mapped_segments}

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

        elapsed_time = time.time() - start_time

        # Get speaker count from mapped segments
        unique_speakers = list({seg["speaker"] for seg in mapped_segments})

        print(f"\n✨ Pipeline complete in {elapsed_time:.1f}s!")
        print(f"📝 Output saved to: {output_path}")
        print(f"📊 Found {len(unique_speakers)} speakers: {unique_speakers}")
        print(f"🔤 Transcribed {len(mapped_segments)} segments")

        if mapped_segments:
            total_duration = mapped_segments[-1]["end"] - mapped_segments[0]["start"]
            print(f"⏱️ Total duration: {total_duration:.1f}s")

        if chop:
            print("🔪 Processed using audio chopping mode")

        print("\nCheck pipeline.log for detailed logs")
        return output_path

    except Exception as e:
        logging.exception("Pipeline failed")
        print(f"\n❌ Pipeline failed: {e}")
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
    parser.add_argument(
        "--chop",
        "-c",
        action="store_true",
        help="Split input audio into 15-minute chunks for processing "
        "(useful for very long audio files)",
    )
    args = parser.parse_args()

    main(
        args.input_audio,
        args.num_speakers,
        args.language,
        args.start_step,
        args.device,
        args.chop,
    )
