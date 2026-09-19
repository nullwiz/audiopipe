from __future__ import annotations

import argparse
import json
import logging
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import IO, Any, cast

from pydub import AudioSegment


HERE = Path(__file__).resolve().parent
DEFAULT_MODEL = "openai/whisper-large-v3"


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


def setup_logging(log_file: str = "pipeline.log") -> None:
    """Configure file + display logging. Called from the CLI entry, not on import."""
    logging.basicConfig(filename=log_file, level=logging.INFO, format="%(message)s")
    console_handler = TqdmLoggingHandler()
    console_handler.setFormatter(logging.Formatter("%(message)s"))
    logging.getLogger().addHandler(console_handler)


def get_device(device: str | None = None) -> str:
    """Determine the appropriate device to use for processing.

    Environment short-circuits (FORCE_CPU, CI) are checked before torch is
    imported so this stays cheap and works without torch installed.
    """
    force_cpu = os.environ.get("FORCE_CPU") == "1"
    is_ci = (
        os.environ.get("GITHUB_ACTIONS") == "true"
        or os.environ.get("AUDIOPIPE_TESTING") == "1"
    )
    if force_cpu or is_ci or device == "cpu":
        logging.info(
            "Using device: cpu (FORCE_CPU=%s, CI=%s, requested=%s)",
            force_cpu,
            is_ci,
            device,
        )
        return "cpu"

    import torch

    cuda_available = torch.cuda.is_available()
    mps_available = hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
    logging.debug(
        "CUDA available: %s, MPS available: %s", cuda_available, mps_available
    )

    if cuda_available:
        try:
            logging.debug(
                "CUDA device: %s",
                torch.cuda.get_device_name(torch.cuda.current_device()),
            )
        except Exception as e:
            logging.debug("Error getting CUDA info: %s", e)
            cuda_available = False

    if device == "cuda" and cuda_available:
        chosen = "cuda"
    elif device == "mps" and mps_available:
        chosen = "mps"
    elif device:
        logging.warning(
            "Requested device %r not available, falling back to CPU", device
        )
        chosen = "cpu"
    elif cuda_available:
        chosen = "cuda"
    elif mps_available:
        chosen = "mps"
    else:
        chosen = "cpu"

    logging.info("Using device: %s", chosen)
    return chosen


def _pump(stream: IO[str], name: str, out: queue.Queue[tuple[str, str] | None]) -> None:
    """Read lines from a subprocess stream into the queue; None marks EOF."""
    for line in iter(stream.readline, ""):
        out.put((name, line))
    out.put(None)


def run_command_with_progress(cmd: list[str], desc: str) -> None:
    """Run a command, show a spinner, and route its output to the log/display."""
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    assert process.stderr is not None

    # Portable (Windows too): one reader thread per pipe instead of select().
    lines: queue.Queue[tuple[str, str] | None] = queue.Queue()
    for stream, name in ((process.stdout, "stdout"), (process.stderr, "stderr")):
        threading.Thread(target=_pump, args=(stream, name, lines), daemon=True).start()

    spinner = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    start_time = time.time()
    stderr_output: list[str] = []
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
    seen_messages: set[str] = set()
    open_streams = 2

    while open_streams:
        try:
            item = lines.get(timeout=0.1)
        except queue.Empty:
            item = None
            got_item = False
        else:
            got_item = True

        elapsed = time.time() - start_time
        spin_char = spinner[int(time.time() * 10) % len(spinner)]
        display.update_progress(f"{desc} {spin_char} [{elapsed:.1f}s]")

        if not got_item:
            continue
        if item is None:
            open_streams -= 1
            continue

        name, output = item
        output = output.strip()
        if not output or output in seen_messages:
            continue
        if any(pattern in output for pattern in skip_patterns):
            continue
        seen_messages.add(output)

        if name == "stderr":
            logging.warning(output)
            stderr_output.append(output)
        else:
            logging.info(output)

        if any(pattern in output for pattern in important_patterns):
            display.update_log(f"⚠️  {output}" if name == "stderr" else output)

    process.wait()
    if process.returncode != 0:
        error_msg = "\n".join(stderr_output) if stderr_output else "Unknown error"
        display.update_log(f"❌ Error: {error_msg}")
        raise RuntimeError(error_msg)


def run_demucs(input_audio: str, output_dir: str) -> str:
    """Run demucs separation and get vocals."""
    print("\n[1/3] Running audio separation")
    run_command_with_progress(
        [sys.executable, "-u", str(HERE / "dem.py"), input_audio, "-o", output_dir],
        "🎵 Separating vocals",
    )
    return os.path.join(output_dir, "combined_vocals.wav")


def run_diarization(vocals_path: str, num_speakers: int | None = None) -> str:
    """Run speaker diarization; output JSON lands next to the vocals file."""
    print("\n[2/3] Running speaker diarization")
    cmd = [sys.executable, "-u", str(HERE / "diarize.py"), vocals_path]
    if num_speakers:
        cmd.extend(["-n", str(num_speakers)])
    run_command_with_progress(cmd, "🎙️ Diarizing speakers")
    return vocals_path.replace(".wav", "_diarized.json")


def run_complete_transcription(
    audio_path: str,
    language: str | None = None,
    device: str | None = None,
    model: str = DEFAULT_MODEL,
    output_dir: str = "output",
) -> dict[str, Any]:
    """Run Whisper transcription on a complete audio file."""
    display.update_progress("🎙️ Running Whisper on complete audio file...")
    actual_device = get_device(device)

    # insanely-fast-whisper only supports CUDA and MPS, not CPU
    if actual_device == "cpu":
        return run_cpu_transcription(audio_path, language, model)
    return run_gpu_transcription(audio_path, language, actual_device, model, output_dir)


def run_cpu_transcription(
    audio_path: str, language: str | None = None, model: str = DEFAULT_MODEL
) -> dict[str, Any]:
    """Run Whisper transcription using transformers directly for CPU mode."""
    try:
        import librosa
        import torch
        from transformers import pipeline as hf_pipeline

        logging.info("Loading Whisper model %s with transformers (CPU)", model)
        pipe = hf_pipeline(
            "automatic-speech-recognition",
            model=model,
            device=-1,  # Force CPU
            torch_dtype=torch.float32,
        )

        audio, sr = librosa.load(audio_path, sr=16000)

        generate_kwargs: dict[str, Any] = {}
        if language:
            generate_kwargs["language"] = language
        result = pipe(audio, return_timestamps=True, generate_kwargs=generate_kwargs)

        chunks = []
        result_data = cast(dict[str, Any], result)
        if "chunks" in result_data:
            for chunk in result_data["chunks"]:
                chunks.append(
                    {"text": chunk["text"].strip(), "timestamp": chunk["timestamp"]}
                )
        else:
            chunks.append(
                {
                    "text": result_data["text"].strip(),
                    "timestamp": [0.0, len(audio) / sr],
                }
            )

        display.update_progress(f"✅ Whisper completed: {len(chunks)} chunks")
        return {"chunks": chunks}

    except Exception as e:
        raise RuntimeError(f"CPU transcription failed: {e}") from e


def run_gpu_transcription(
    audio_path: str,
    language: str | None = None,
    device: str = "cuda",
    model: str = DEFAULT_MODEL,
    output_dir: str = "output",
) -> dict[str, Any]:
    """Run Whisper transcription using insanely-fast-whisper for GPU/MPS."""
    output_json = os.path.join(output_dir, "complete_whisper_transcription.json")
    os.makedirs(output_dir, exist_ok=True)

    cmd = [
        "insanely-fast-whisper",
        "--file-name",
        audio_path,
        "--model-name",
        model,
        "--transcript-path",
        output_json,
    ]
    if language:
        cmd.extend(["--language", language])

    if device == "cuda":
        cmd.extend(["--device-id", "0", "--batch-size", "32"])
    elif device == "mps":
        cmd.extend(["--device-id", "mps", "--batch-size", "16"])
    else:
        raise RuntimeError(f"Unsupported device for insanely-fast-whisper: {device}")

    # No timeout: a long podcast on large-v3 can legitimately take a long while.
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        logging.error(f"Whisper transcription failed: {result.stderr}")
        raise RuntimeError(f"Whisper transcription failed: {result.stderr}")

    if not os.path.exists(output_json):
        raise RuntimeError(f"Transcription output file not found: {output_json}")
    with open(output_json, encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
    display.update_progress(
        f"✅ Whisper completed: {len(data.get('chunks', []))} chunks"
    )
    return data


def simple_speaker_mapping(
    whisper_chunks: list[dict[str, Any]],
    diarization_segments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """For each Whisper chunk, pick the diarization speaker with the most overlap.

    Falls back to the nearest segment (by centre distance) when nothing overlaps.
    """
    display.update_progress("🔗 Mapping speakers to transcription...")

    mapped_segments = []

    for chunk in whisper_chunks:
        if "timestamp" not in chunk or len(chunk["timestamp"]) != 2:
            continue

        chunk_start, chunk_end = chunk["timestamp"]
        if chunk_start is None or chunk_end is None:
            continue

        chunk_text = chunk.get("text", "").strip()
        if not chunk_text:
            continue

        best_speaker = None
        max_overlap = 0.0

        for diar_seg in diarization_segments:
            overlap = min(chunk_end, diar_seg["end"]) - max(
                chunk_start, diar_seg["start"]
            )
            if overlap > max_overlap:
                max_overlap = overlap
                best_speaker = diar_seg["speaker"]

        if not best_speaker:
            chunk_center = (chunk_start + chunk_end) / 2
            min_distance = float("inf")
            for diar_seg in diarization_segments:
                diar_center = (diar_seg["start"] + diar_seg["end"]) / 2
                distance = abs(chunk_center - diar_center)
                if distance < min_distance:
                    min_distance = distance
                    best_speaker = diar_seg["speaker"]

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


def consolidate_segments(
    segments: list[dict[str, Any]], max_gap: float = 1.0
) -> list[dict[str, Any]]:
    """Merge consecutive same-speaker segments separated by at most max_gap seconds."""
    out: list[dict[str, Any]] = []
    for seg in segments:
        prev = out[-1] if out else None
        if (
            prev is not None
            and prev["speaker"] == seg["speaker"]
            and seg["start"] - prev["end"] <= max_gap
        ):
            prev["text"] = f"{prev['text']} {seg['text']}".strip()
            prev["end"] = max(prev["end"], seg["end"])
        else:
            out.append(dict(seg))
    return out


def chop_audio(
    input_audio: str, output_dir: str, chunk_duration: int = 900
) -> list[dict[str, Any]]:
    """Split audio into chunks of chunk_duration seconds under output_dir/chunks."""
    display.update_progress(
        f"🔪 Chopping audio into {chunk_duration // 60}-minute chunks..."
    )

    audio = AudioSegment.from_file(input_audio)
    total_duration = len(audio) / 1000
    chunk_duration_ms = chunk_duration * 1000
    chunks_dir = os.path.join(output_dir, "chunks")
    os.makedirs(chunks_dir, exist_ok=True)

    chunks = []
    for index, i in enumerate(range(0, len(audio), chunk_duration_ms)):
        chunk_filename = os.path.join(chunks_dir, f"chunk_{index:03d}.wav")
        audio[i : i + chunk_duration_ms].export(chunk_filename, format="wav")
        chunks.append(
            {
                "path": chunk_filename,
                "start_time": i / 1000,
                "end_time": min((i + chunk_duration_ms) / 1000, total_duration),
                "index": index,
            }
        )

    display.update_progress(f"✅ Created {len(chunks)} audio chunks")
    return chunks


def merge_chunk_outputs(
    chunk_results: list[tuple[dict[str, Any], list[dict[str, Any]]]],
) -> list[dict[str, Any]]:
    """Offset per-chunk Whisper chunks by their chunk start and concatenate in order."""
    all_chunks: list[dict[str, Any]] = []
    for chunk_info, whisper_chunks in chunk_results:
        offset = chunk_info["start_time"]
        for wc in whisper_chunks:
            ts = wc.get("timestamp")
            if not ts or len(ts) != 2 or ts[0] is None or ts[1] is None:
                continue
            all_chunks.append({**wc, "timestamp": [ts[0] + offset, ts[1] + offset]})
    all_chunks.sort(key=lambda c: c["timestamp"][0])
    return all_chunks


def transcribe_chopped(
    vocals_path: str,
    output_dir: str,
    chunk_minutes: int,
    language: str | None,
    device: str | None,
    model: str,
) -> list[dict[str, Any]]:
    """Transcribe vocals in fixed-length chunks and return globally-timed chunks."""
    chunks = chop_audio(vocals_path, output_dir, chunk_minutes * 60)
    results: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    for chunk_info in chunks:
        display.update_progress(
            f"🔄 Transcribing chunk {chunk_info['index'] + 1}/{len(chunks)}..."
        )
        data = run_complete_transcription(
            chunk_info["path"], language, device, model, output_dir
        )
        if not data or "chunks" not in data:
            raise RuntimeError(f"Whisper failed for chunk {chunk_info['index']}")
        results.append((chunk_info, data["chunks"]))
    return merge_chunk_outputs(results)


def main(
    input_audio: str,
    num_speakers: int | None = None,
    language: str | None = None,
    start_step: int = 1,
    device: str | None = None,
    chop: bool = False,
    output_dir: str = "output",
    model: str = DEFAULT_MODEL,
    chunk_minutes: int = 15,
    consolidate: bool = True,
) -> str:
    """Run the complete pipeline: separate → diarize → transcribe → map speakers."""
    start_time = time.time()
    os.makedirs(output_dir, exist_ok=True)

    try:
        if start_step <= 1:
            vocals_path = run_demucs(input_audio, output_dir)
        else:
            vocals_path = os.path.join(output_dir, "combined_vocals.wav")
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

        display.update_progress("\n[3/3] Running transcription")
        if chop:
            whisper_chunks = transcribe_chopped(
                vocals_path, output_dir, chunk_minutes, language, device, model
            )
        else:
            whisper_data = run_complete_transcription(
                vocals_path, language, device, model, output_dir
            )
            if not whisper_data or "chunks" not in whisper_data:
                raise RuntimeError("Whisper transcription failed")
            whisper_chunks = whisper_data["chunks"]

        mapped_segments = simple_speaker_mapping(
            whisper_chunks, diarization_data["segments"]
        )
        if not mapped_segments:
            raise RuntimeError("No segments could be mapped to speakers")
        mapped_segments.sort(key=lambda x: x["start"])
        if consolidate:
            mapped_segments = consolidate_segments(mapped_segments)

        output_path = os.path.join(output_dir, "final_transcription.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({"segments": mapped_segments}, f, indent=2, ensure_ascii=False)

        elapsed_time = time.time() - start_time
        unique_speakers = sorted({seg["speaker"] for seg in mapped_segments})

        print(f"\n✨ Pipeline complete in {elapsed_time:.1f}s!")
        print(f"📝 Output saved to: {output_path}")
        print(f"📊 Found {len(unique_speakers)} speakers: {unique_speakers}")
        print(f"🔤 Transcribed {len(mapped_segments)} segments")
        total_duration = mapped_segments[-1]["end"] - mapped_segments[0]["start"]
        print(f"⏱️ Total duration: {total_duration:.1f}s")
        if chop:
            print(f"🔪 Transcribed in {chunk_minutes}-minute chunks")
        print("\nCheck pipeline.log for detailed logs")
        return output_path

    except Exception as e:
        logging.exception("Pipeline failed")
        print(f"\n❌ Pipeline failed: {e}")
        print("📝 Check pipeline.log for detailed logs")
        raise


def cli(argv: list[str] | None = None) -> None:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description="End-to-end audio processing pipeline")
    parser.add_argument("input_audio", help="Path to input audio file")
    parser.add_argument(
        "--num-speakers", "-n", type=int, help="Number of speakers (optional)"
    )
    parser.add_argument(
        "--language",
        "-l",
        help="Language code for transcription (e.g. 'en'); auto-detected if omitted",
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
        "--output-dir", "-o", default="output", help="Directory for all outputs"
    )
    parser.add_argument(
        "--model",
        "-m",
        default=DEFAULT_MODEL,
        help=f"Whisper model (default {DEFAULT_MODEL}; "
        "openai/whisper-large-v3-turbo is much faster on CPU)",
    )
    parser.add_argument(
        "--chop",
        "-c",
        action="store_true",
        help="Transcribe in fixed-length chunks (useful for very long audio files)",
    )
    parser.add_argument(
        "--chunk-minutes",
        type=int,
        default=15,
        help="Chunk length in minutes when using --chop (default 15)",
    )
    parser.add_argument(
        "--no-consolidate",
        action="store_true",
        help="Keep raw Whisper chunks instead of merging consecutive same-speaker ones",
    )
    args = parser.parse_args(argv)

    setup_logging()
    main(
        args.input_audio,
        args.num_speakers,
        args.language,
        args.start_step,
        args.device,
        args.chop,
        args.output_dir,
        args.model,
        args.chunk_minutes,
        not args.no_consolidate,
    )


if __name__ == "__main__":
    cli()
