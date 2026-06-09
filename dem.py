from __future__ import annotations

import argparse
import glob
import os
import platform
import shutil
import subprocess

import torch
from pydub import AudioSegment


# Config
CHUNKS_DIR = "chunks"
INPUT_DIR = "input"
OUTPUT_DIR = "output"
SEPARATED_DIR = os.path.join("separated")
MODEL = "htdemucs"
STEM = "vocals"
MAX_FILE_SIZE_MB = 60  # Maximum file size to process as a single unit
CHUNK_DURATION_SECONDS = 15 * 60


def get_device(device: str | None = None) -> str:
    """Determine the appropriate device to use."""
    if device:
        if device == "cpu":
            return "cpu"
        if device == "cuda" and torch.cuda.is_available():
            return "cuda"
        if (
            device == "mps"
            and hasattr(torch.backends, "mps")
            and torch.backends.mps.is_available()
        ):
            return "mps"

    if torch.cuda.is_available():
        return "cuda"
    if (
        platform.system() == "Darwin"
        and hasattr(torch.backends, "mps")
        and torch.backends.mps.is_available()
    ):
        return "mps"
    return "cpu"


def run_demucs_on_chunk(chunk_path: str, device: str | None = None) -> None:
    """Run demucs on a single audio chunk."""
    device_arg = get_device(device)
    command = [
        "demucs",
        "-n",
        MODEL,
        "--two-stems",
        STEM,
        "--device",
        device_arg,
        chunk_path,
    ]
    print(f"🔊 Processing chunk: {chunk_path} (using {device_arg})")
    subprocess.run(command, check=True)


def split_audio_into_chunks(input_file: str) -> list[str]:
    """Split a large input into WAV chunks for lower-memory Demucs runs."""
    if os.path.exists(CHUNKS_DIR):
        shutil.rmtree(CHUNKS_DIR)
    os.makedirs(CHUNKS_DIR, exist_ok=True)

    output_pattern = os.path.join(CHUNKS_DIR, "chunk_%03d.wav")
    command = [
        "ffmpeg",
        "-y",
        "-i",
        input_file,
        "-f",
        "segment",
        "-segment_time",
        str(CHUNK_DURATION_SECONDS),
        "-reset_timestamps",
        "1",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-c:a",
        "pcm_s16le",
        output_pattern,
    ]
    print(f"✂️ Splitting large file into {CHUNK_DURATION_SECONDS // 60}-minute chunks")
    subprocess.run(command, check=True)

    chunks = sorted(glob.glob(os.path.join(CHUNKS_DIR, "chunk_*.wav")))
    if not chunks:
        raise RuntimeError(f"No chunks created for {input_file}")
    return chunks


def recombine_stems(stem_path_pattern: str, output_path: str) -> None:
    """Recombine separated audio stems into a single file."""
    print(f"🔗 Recombining: {stem_path_pattern} -> {output_path}")
    parts = sorted(glob.glob(stem_path_pattern))

    if not parts:
        raise FileNotFoundError(f"No matching stem parts found: {stem_path_pattern}")

    print(f"📦 Found {len(parts)} files:")
    for p in parts:
        print(f"   - {p}")

    concat_list_file = "combine_list.txt"
    with open(concat_list_file, "w") as f:
        for part in parts:
            f.write(f"file '{os.path.abspath(part)}'\n")

    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                concat_list_file,
                "-c",
                "copy",
                output_path,
            ],
            check=True,
        )
        size = os.path.getsize(output_path)
        if size < 100:
            print(f"❌ Output file too small: {output_path}")
        else:
            print(f"✅ Exported (via ffmpeg): {output_path} ({size} bytes)")
    except subprocess.CalledProcessError:
        print("⚠️ ffmpeg concat failed, falling back to pydub...")
        combine_with_pydub(parts, output_path)

    os.remove(concat_list_file)

    if not os.path.exists(output_path) or os.path.getsize(output_path) < 100:
        raise RuntimeError(f"Failed to create a valid output file: {output_path}")


def combine_with_pydub(parts: list[str], output_path: str) -> None:
    """Combine audio parts using pydub as fallback."""
    combined = AudioSegment.silent(duration=0)
    for part in parts:
        try:
            audio = AudioSegment.from_file(part)
            if len(audio) == 0:
                print(f"⚠️ Skipping empty file: {part}")
                continue
            combined += audio
        except Exception as e:
            print(f"❌ Failed to load {part}: {e}")

    if len(combined) == 0:
        raise RuntimeError(f"No valid audio found for {output_path}")

    combined.export(output_path, format="wav", parameters=["-y"])
    size = os.path.getsize(output_path)
    print(f"✅ Exported (via pydub): {output_path} ({size} bytes)")


def process_input_file(
    input_file: str, device: str | None = None, vocals_only: bool = False
) -> str:
    """Process a single input file."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for output_name in ("combined_vocals.wav", "combined_background.wav"):
        output_path = os.path.join(OUTPUT_DIR, output_name)
        if os.path.exists(output_path):
            os.remove(output_path)

    if os.path.exists(SEPARATED_DIR):
        shutil.rmtree(SEPARATED_DIR)

    # Check file size
    file_size_mb = os.path.getsize(input_file) / (1024 * 1024)
    if file_size_mb <= MAX_FILE_SIZE_MB:
        print(
            f"🔍 File is under {MAX_FILE_SIZE_MB}MB ({file_size_mb:.1f}MB), "
            "processing as a single unit"
        )
        run_demucs_on_chunk(input_file, device)
    else:
        print(
            f"🔍 File is over {MAX_FILE_SIZE_MB}MB ({file_size_mb:.1f}MB), "
            "chunking before separation"
        )
        for chunk in split_audio_into_chunks(input_file):
            run_demucs_on_chunk(chunk, device)

    track_folder = os.path.join(SEPARATED_DIR, MODEL)

    recombine_stems(
        os.path.join(track_folder, "*", "vocals.wav"),
        os.path.join(OUTPUT_DIR, "combined_vocals.wav"),
    )

    if not vocals_only:
        recombine_stems(
            os.path.join(track_folder, "*", "no_vocals.wav"),
            os.path.join(OUTPUT_DIR, "combined_background.wav"),
        )

    print("✅ Done! Separated and recombined audio saved in:", OUTPUT_DIR)
    return os.path.join(OUTPUT_DIR, "combined_vocals.wav")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Separate vocals from background music"
    )
    parser.add_argument("input_file", help="Path to input audio file")
    parser.add_argument(
        "--device",
        "-d",
        choices=["cpu", "cuda", "mps"],
        help="Device to use for processing (auto-detected if not specified)",
    )
    parser.add_argument(
        "--vocals-only",
        action="store_true",
        help="Only recombine the vocals stem; skip the background output",
    )
    args = parser.parse_args()

    process_input_file(args.input_file, args.device, args.vocals_only)
