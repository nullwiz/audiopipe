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
from typing import IO, Any


HERE = Path(__file__).resolve().parent
DEFAULT_MODEL = "nvidia/nemotron-3.5-asr-streaming-0.6b"
SR = 16000


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


def run_demucs(input_audio: str, output_dir: str, device: str) -> str:
    """Run demucs separation and get vocals."""
    print("\n[1/3] Running audio separation")
    run_command_with_progress(
        [
            sys.executable,
            "-u",
            str(HERE / "dem.py"),
            input_audio,
            "-o",
            output_dir,
            "-d",
            device,
        ],
        "🎵 Separating vocals",
    )
    return os.path.join(output_dir, "combined_vocals.wav")


def convert_to_wav(input_audio: str, output_dir: str) -> str:
    """Skip separation: just decode the input to 16 kHz mono as the 'vocals'."""
    print("\n[1/3] Skipping separation, converting input to 16 kHz mono")
    out = os.path.join(output_dir, "combined_vocals.wav")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            input_audio,
            "-ac",
            "1",
            "-ar",
            str(SR),
            out,
        ],
        check=True,
    )
    return out


def run_diarization(
    vocals_path: str, device: str, num_speakers: int | None = None
) -> str:
    """Run speaker diarization; output JSON lands next to the vocals file."""
    print("\n[2/3] Running speaker diarization")
    cmd = [sys.executable, "-u", str(HERE / "diarize.py"), vocals_path, "-d", device]
    if num_speakers:
        cmd.extend(["-n", str(num_speakers)])
    run_command_with_progress(cmd, "🎙️ Diarizing speakers")
    return vocals_path.replace(".wav", "_diarized.json")


def batched(order: list[int], size: int) -> list[list[int]]:
    return [order[i : i + size] for i in range(0, len(order), size)]


def transcribe_segments(
    audio: Any,
    segments: list[dict[str, Any]],
    model: str = DEFAULT_MODEL,
    language: str | None = None,
    device: str = "cpu",
    batch_size: int = 8,
) -> list[str]:
    """Transcribe each diarized segment's audio; returns one text per segment.

    Nemotron ASR by default; any model id containing "whisper" goes through the
    transformers Whisper pipeline instead (more languages, slower).
    """
    clips = [audio[int(s["start"] * SR) : int(s["end"] * SR)] for s in segments]
    # longest first and similar lengths together → less padding per batch
    order = sorted(range(len(clips)), key=lambda i: -len(clips[i]))
    texts = [""] * len(clips)
    batches = batched(order, batch_size)

    if "whisper" in model.lower():
        from transformers import pipeline as hf_pipeline

        pipe = hf_pipeline("automatic-speech-recognition", model=model, device=device)
        kwargs = {"language": language, "task": "transcribe"} if language else {}
        for n, idx in enumerate(batches, 1):
            display.update_progress(f"🔤 Transcribing batch {n}/{len(batches)}...")
            batch: Any = [clips[i] for i in idx]
            out = pipe(batch, batch_size=len(idx), generate_kwargs=kwargs)
            for i, r in zip(idx, out, strict=True):
                texts[i] = " ".join(r["text"].split())
        return texts

    import torch
    from transformers import AutoModelForRNNT, AutoProcessor

    processor = AutoProcessor.from_pretrained(model)
    net = AutoModelForRNNT.from_pretrained(model).to(device)
    net.eval()
    for n, idx in enumerate(batches, 1):
        display.update_progress(f"🔤 Transcribing batch {n}/{len(batches)}...")
        inputs = processor(
            [clips[i] for i in idx], sampling_rate=SR, language=language or "auto"
        ).to(device, dtype=net.dtype)
        with torch.inference_mode():
            ids = net.generate(**inputs, return_dict_in_generate=True).sequences
        decoded = processor.batch_decode(ids, skip_special_tokens=True)
        for i, text in zip(idx, decoded, strict=True):
            texts[i] = " ".join(text.split())
    return texts


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


def to_text(segments: list[dict[str, Any]]) -> str:
    """Readable transcript: one '[hh:mm:ss] SPEAKER: text' line per segment."""
    return "".join(
        f"[{time.strftime('%H:%M:%S', time.gmtime(s['start']))}] "
        f"{s['speaker']}: {s['text']}\n"
        for s in segments
    )


def main(
    input_audio: str,
    num_speakers: int | None = None,
    language: str | None = None,
    start_step: int = 1,
    device: str | None = None,
    output_dir: str = "output",
    model: str = DEFAULT_MODEL,
    consolidate: bool = True,
    separate: bool = True,
) -> str:
    """Run the complete pipeline: separate → diarize → transcribe each turn."""
    start_time = time.time()
    os.makedirs(output_dir, exist_ok=True)
    device = get_device(device)

    try:
        if start_step <= 1:
            vocals_path = (
                run_demucs(input_audio, output_dir, device)
                if separate
                else convert_to_wav(input_audio, output_dir)
            )
        else:
            vocals_path = os.path.join(output_dir, "combined_vocals.wav")
            if not os.path.exists(vocals_path):
                raise FileNotFoundError(
                    f"Cannot skip to step {start_step}: {vocals_path} not found"
                )

        if start_step <= 2:
            diarization_path = run_diarization(vocals_path, device, num_speakers)
        else:
            diarization_path = vocals_path.replace(".wav", "_diarized.json")
            if not os.path.exists(diarization_path):
                raise FileNotFoundError(
                    f"Cannot skip to step {start_step}: {diarization_path} not found"
                )

        with open(diarization_path) as f:
            turns = json.load(f)["segments"]
        if not turns:
            raise RuntimeError("Diarization found no speech")

        print(f"\n[3/3] Transcribing {len(turns)} turns with {model}")
        from diarize import load_audio

        texts = transcribe_segments(
            load_audio(vocals_path), turns, model, language, device
        )
        segments = [
            {"text": text, **turn}
            for turn, text in zip(turns, texts, strict=True)
            if text
        ]
        if not segments:
            raise RuntimeError("Transcription produced no text")
        if consolidate:
            segments = consolidate_segments(segments)

        output_path = os.path.join(output_dir, "final_transcription.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({"segments": segments}, f, indent=2, ensure_ascii=False)
        text_path = os.path.join(output_dir, "final_transcription.txt")
        with open(text_path, "w", encoding="utf-8") as f:
            f.write(to_text(segments))

        speakers = sorted({seg["speaker"] for seg in segments})
        print(f"\n✨ Pipeline complete in {time.time() - start_time:.1f}s!")
        print(f"📝 Output saved to: {output_path} and {text_path}")
        print(f"📊 Found {len(speakers)} speakers: {speakers}")
        print(f"🔤 Transcribed {len(segments)} segments")
        print("\nCheck pipeline.log in the output directory for details")
        return output_path

    except Exception as e:
        logging.exception("Pipeline failed")
        print(f"\n❌ Pipeline failed: {e}")
        print("📝 Check pipeline.log in the output directory for details")
        raise


def cli(argv: list[str] | None = None) -> None:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(
        description="Local speaker diarization + transcription pipeline"
    )
    parser.add_argument("input_audio", help="Path to input audio/video file")
    parser.add_argument(
        "--num-speakers",
        "-n",
        type=int,
        choices=range(1, 9),
        metavar="1-8",
        help="Number of speakers, if known (the diarizer tracks up to 8)",
    )
    parser.add_argument(
        "--language",
        "-l",
        help="Language code (e.g. 'en', 'de-DE'); auto-detected if omitted",
    )
    parser.add_argument(
        "--start-step",
        "-s",
        type=int,
        choices=[1, 2, 3],
        default=1,
        help="Start from step: 1=separation, 2=diarization, 3=transcription",
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
        help=f"ASR model (default {DEFAULT_MODEL}); any Whisper checkpoint such "
        "as openai/whisper-large-v3-turbo also works, for 99 languages",
    )
    parser.add_argument(
        "--no-separation",
        action="store_true",
        help="Skip Demucs vocal separation (faster; fine for clean speech)",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Never touch the network; models must already be downloaded",
    )
    parser.add_argument(
        "--no-consolidate",
        action="store_true",
        help="Keep one segment per diarized turn instead of merging same-speaker runs",
    )
    args = parser.parse_args(argv)

    if args.offline:  # inherited by the separation/diarization subprocesses too
        os.environ["HF_HUB_OFFLINE"] = "1"
    os.makedirs(args.output_dir, exist_ok=True)
    setup_logging(os.path.join(args.output_dir, "pipeline.log"))
    main(
        args.input_audio,
        args.num_speakers,
        args.language,
        args.start_step,
        args.device,
        args.output_dir,
        args.model,
        not args.no_consolidate,
        not args.no_separation,
    )


if __name__ == "__main__":
    cli()
