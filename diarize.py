import torch
from pyannote.audio import Pipeline
import json
import os
import argparse
import sys

# --- Config
# Try to get token from environment variable, otherwise use a default message
HUGGING_FACE_TOKEN = os.environ.get("HUGGING_FACE_TOKEN", None)
if not HUGGING_FACE_TOKEN:
    print("⚠️ Warning: HUGGING_FACE_TOKEN environment variable not set.")
    print("Please set your Hugging Face token as an environment variable:")
    print("export HUGGING_FACE_TOKEN='your_token_here'")
    print("Or pass it as an environment variable when running the script:")
    print(
        "HUGGING_FACE_TOKEN='your_token_here' python diarize.py your_audio.wav"
    )

PIPELINE = "pyannote/speaker-diarization-3.1"
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def merge_continuous_fragments(segments):
    """Merge adjacent segments from the same speaker with small gaps."""
    if not segments:
        return segments

    # Group segments by speaker
    segments_by_speaker = {}
    for segment in segments:
        speaker = segment["speaker"]
        if speaker not in segments_by_speaker:
            segments_by_speaker[speaker] = []
        segments_by_speaker[speaker].append(segment)

    # Sort each speaker's segments by start time
    for speaker in segments_by_speaker:
        segments_by_speaker[speaker].sort(key=lambda x: x["start"])

    merged_segments = []

    for speaker, speaker_segments in segments_by_speaker.items():
        if not speaker_segments:
            continue

        current_segment = speaker_segments[0].copy()

        for next_segment in speaker_segments[1:]:
            gap = next_segment["start"] - current_segment["end"]

            if gap <= 2.0:  # Merge segments with gaps ≤2 seconds
                current_segment["end"] = next_segment["end"]
            else:
                merged_segments.append(current_segment)
                current_segment = next_segment.copy()

        merged_segments.append(current_segment)

    merged_segments.sort(key=lambda x: x["start"])
    return merged_segments


def diarize_audio(
    audio_path, num_speakers=None, min_speakers=None, max_speakers=None
):
    """
    Standard pyannote 3.1 speaker diarization.

    Args:
        audio_path: Path to audio file
        num_speakers: Exact number of speakers if known
        min_speakers: Minimum number of speakers
        max_speakers: Maximum number of speakers

    Returns:
        List of segments with speaker IDs and timestamps
    """
    print("🎙️ Starting pyannote 3.1 diarization...")
    print(
        f"Debug: Using token: {'Available' if HUGGING_FACE_TOKEN else 'NOT AVAILABLE'}"
    )

    try:
        print("🔧 Initializing pyannote speaker-diarization-3.1 pipeline...")

        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=HUGGING_FACE_TOKEN,
        )

        print(f"🚀 Moving pipeline to {DEVICE}...")
        pipeline.to(DEVICE)

        # Enable TF32 for better performance
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True

        # Configure speaker count
        kwargs = {}
        if num_speakers is not None:
            kwargs["num_speakers"] = num_speakers
            print(f"🎯 Using exact speaker count: {num_speakers}")
        elif min_speakers is not None or max_speakers is not None:
            kwargs["min_speakers"] = min_speakers or 4
            kwargs["max_speakers"] = max_speakers or 10
            print(
                f"🎯 Using speaker range: {kwargs['min_speakers']}-{kwargs['max_speakers']}"
            )
        else:
            kwargs["min_speakers"] = 4
            kwargs["max_speakers"] = 10
            print("🎯 Using default speaker range: 4-10")

        print("🎙️ Running pyannote diarization (this may take a few minutes)...")
        diarization = pipeline(audio_path, **kwargs)

        print("🎙️ Extracting segments from diarization output...")
        segments = []

        for turn, _, speaker in diarization.itertracks(yield_label=True):
            duration = turn.end - turn.start

            if duration >= 0.05:  # Filter out very short artifacts
                segments.append(
                    {
                        "speaker": speaker,
                        "start": round(turn.start, 3),
                        "end": round(turn.end, 3),
                    }
                )

        print(f"🎙️ Extracted {len(segments)} raw segments from pyannote")

        segments.sort(key=lambda x: x["start"])

        unique_speakers = len(set(seg["speaker"] for seg in segments))
        print(f"🎯 Detected {unique_speakers} unique speakers in raw output")

        return segments
    except Exception as e:
        print(f"Error in diarize_audio: {str(e)}", file=sys.stderr)
        # Print additional information for debugging
        print(f"Python version: {sys.version}", file=sys.stderr)
        print(f"PyTorch version: {torch.__version__}", file=sys.stderr)
        print(f"Device: {DEVICE}", file=sys.stderr)
        print(f"Audio path: {audio_path}", file=sys.stderr)
        raise


def combine_diarization_with_transcription(
    diarization_segments, transcription_chunks
):
    """
    Combine diarization results with transcription chunks to create
    a final output with both speaker IDs and transcribed text.
    """
    combined_output = []

    for chunk in transcription_chunks:
        chunk_start, chunk_end = chunk["timestamp"]
        speakers_in_chunk = set()

        # Find all speakers active during this chunk
        for segment in diarization_segments:
            if segment["start"] <= chunk_end and segment["end"] >= chunk_start:
                speakers_in_chunk.add(segment["speaker"])

        combined_output.append(
            {
                "timestamp": [chunk_start, chunk_end],
                "text": chunk["text"],
                "speakers": sorted(list(speakers_in_chunk)),
            }
        )

    return combined_output


def apply_post_processing(raw_segments):
    """Apply conservative merging to raw diarization segments."""
    print("🔧 Applying post-processing to raw diarization output...")

    merged_segments = merge_continuous_fragments(raw_segments)

    fragment_reduction = len(raw_segments) - len(merged_segments)
    if fragment_reduction > 0:
        print(f"🔧 Merged {fragment_reduction} fragmented segments")
    else:
        print("🔧 No fragmentation detected - segments already optimal")

    final_speakers = sorted(set(seg["speaker"] for seg in merged_segments))
    print(
        f"🎯 Final speaker count after post-processing: {len(final_speakers)} speakers"
    )

    return merged_segments


def process_audio_with_diarization(
    audio_path,
    transcription_output_path=None,
    num_speakers=None,
    min_speakers=None,
    max_speakers=None,
):
    """Main function to process audio with diarization and optional post-processing."""
    print(f"🚀 Running diarization on {DEVICE}")
    if num_speakers:
        print(f"👥 Using exact number of speakers: {num_speakers}")
    elif min_speakers or max_speakers:
        print(
            f"👥 Speaker bounds: {min_speakers or 'auto'} - {max_speakers or 'auto'}"
        )

    # Get raw diarization segments
    raw_segments = diarize_audio(
        audio_path, num_speakers, min_speakers, max_speakers
    )

    # Apply post-processing
    processed_segments = apply_post_processing(raw_segments)

    # Create output data
    output_data = {
        "speakers": sorted(set(seg["speaker"] for seg in processed_segments)),
        "segments": processed_segments,
    }

    # If transcription file exists, combine them
    if transcription_output_path and os.path.exists(transcription_output_path):
        with open(transcription_output_path, "r") as f:
            transcription_data = json.load(f)

        combined_output = combine_diarization_with_transcription(
            processed_segments, transcription_data["chunks"]
        )
        output_data["chunks"] = combined_output

    # Generate output path
    base_path = os.path.splitext(audio_path)[0]
    output_path = f"{base_path}_diarized.json"

    # Save output
    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2)

    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("audio_path", help="Path to the audio file")
    parser.add_argument(
        "--transcription",
        "-t",
        help="Optional: Path to transcription JSON file",
        default=None,
    )
    parser.add_argument(
        "--num-speakers",
        "-n",
        type=int,
        help="Exact number of speakers",
        default=None,
    )
    parser.add_argument(
        "--min-speakers",
        type=int,
        help="Minimum number of speakers",
        default=None,
    )
    parser.add_argument(
        "--max-speakers",
        type=int,
        help="Maximum number of speakers",
        default=None,
    )
    args = parser.parse_args()

    output_path = process_audio_with_diarization(
        args.audio_path,
        args.transcription,
        args.num_speakers,
        args.min_speakers,
        args.max_speakers,
    )
    print(f"✅ Processed output saved to: {output_path}")
