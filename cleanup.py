#!/usr/bin/env python3
"""
Cleanup script for AudioPipe output files

This script provides options to clean up output files based on user preferences.
"""

import argparse
import shutil
from pathlib import Path

# Default output directory
OUTPUT_DIR = "output"


def cleanup_all():
    """Remove all output files and directories except .gitkeep"""
    print("🧹 Cleaning up all output files...")
    for item in Path(OUTPUT_DIR).glob("*"):
        if item.name == ".gitkeep":
            continue

        if item.is_file():
            item.unlink()
            print(f"  ✓ Deleted file: {item}")
        elif item.is_dir():
            shutil.rmtree(item)
            print(f"  ✓ Deleted directory: {item}")

    print("✨ All output files cleaned up!")


def cleanup_temp():
    """Remove temporary directories but keep final output files"""
    print("🧹 Cleaning up temporary files and directories...")

    # Clean up speaker directories
    speakers_dir = Path(OUTPUT_DIR) / "speakers"
    if speakers_dir.exists():
        shutil.rmtree(speakers_dir)
        print(f"  ✓ Deleted directory: {speakers_dir}")

    # Clean up chunks
    chunks_dir = Path("chunks")
    if chunks_dir.exists():
        shutil.rmtree(chunks_dir)
        print(f"  ✓ Deleted directory: {chunks_dir}")

    # Clean up separated
    separated_dir = Path("separated")
    if separated_dir.exists():
        shutil.rmtree(separated_dir)
        print(f"  ✓ Deleted directory: {separated_dir}")

    # Clean up backup
    backup_dir = Path(OUTPUT_DIR) / "backup"
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
        print(f"  ✓ Deleted directory: {backup_dir}")

    print("✨ Temporary files cleaned up!")


def cleanup_intermediates():
    """Keep only final output JSON files"""
    print("🧹 Cleaning up intermediate files...")

    # Find and keep only the final JSON files
    to_keep = [
        "final_transcription.json",
        "final_transcription_consolidated.json",
        ".gitkeep",
    ]

    for item in Path(OUTPUT_DIR).glob("*"):
        if item.name not in to_keep and item.is_file():
            item.unlink()
            print(f"  ✓ Deleted file: {item}")

    # Also clean up directories
    cleanup_temp()

    print("✨ Intermediate files cleaned up!")


def main():
    parser = argparse.ArgumentParser(description="Clean up AudioPipe output files")

    parser.add_argument(
        "--all",
        "-a",
        action="store_true",
        help="Remove all output files (complete cleanup)",
    )

    parser.add_argument(
        "--temp",
        "-t",
        action="store_true",
        help="Remove temporary directories only (speakers/, chunks/, separated/, backup/)",
    )

    parser.add_argument(
        "--intermediates",
        "-i",
        action="store_true",
        help="Keep only final JSONs (remove audio files and temporaries)",
    )

    args = parser.parse_args()

    # If no arguments provided, show help
    if not any([args.all, args.temp, args.intermediates]):
        parser.print_help()
        return

    # Process based on flags
    if args.all:
        cleanup_all()
    elif args.intermediates:
        cleanup_intermediates()
    elif args.temp:
        cleanup_temp()


if __name__ == "__main__":
    main()
