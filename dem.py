import os
import subprocess
import argparse
import shutil
import glob
import platform
from pydub import AudioSegment
import torch

# Config
CHUNKS_DIR = "chunks"
INPUT_DIR = "input"
OUTPUT_DIR = "output"
SEPARATED_DIR = os.path.join("separated")
MODEL = "htdemucs"
STEM = "vocals"


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


def run_demucs_on_chunk(chunk_path, device=None):
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


def recombine_stems(stem_path_pattern, output_path):
    print(f"🔗 Recombining: {stem_path_pattern} -> {output_path}")
    parts = sorted(glob.glob(stem_path_pattern))

    if not parts:
        print("❌ No matching stem parts found.")
        return

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


def combine_with_pydub(parts, output_path):
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
        print(f"❌ No valid audio found for {output_path}")
        return

    combined.export(output_path, format="wav", parameters=["-y"])
    size = os.path.getsize(output_path)
    print(f"✅ Exported (via pydub): {output_path} ({size} bytes)")


def process_input_file(input_file, device=None):
    """Process a single input file"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if os.path.exists(SEPARATED_DIR):
        shutil.rmtree(SEPARATED_DIR)

    run_demucs_on_chunk(input_file, device)

    track_folder = os.path.join(SEPARATED_DIR, MODEL)

    recombine_stems(
        os.path.join(track_folder, "*", "vocals.wav"),
        os.path.join(OUTPUT_DIR, "combined_vocals.wav"),
    )

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
    args = parser.parse_args()

    process_input_file(args.input_file, args.device)
