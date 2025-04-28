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
    print("HUGGING_FACE_TOKEN='your_token_here' python diarize.py your_audio.wav")

PIPELINE = "pyannote/speaker-diarization-3.1"
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def diarize_audio(audio_path, num_speakers=None, min_speakers=None, max_speakers=None):
    """
    Perform speaker diarization on an audio file.
    Returns a list of segments with speaker IDs and timestamps.

    Args:
        audio_path: Path to audio file
        num_speakers: Exact number of speakers if known
        min_speakers: Minimum number of speakers
        max_speakers: Maximum number of speakers
    """
    # Print detailed debug info
    print(f"Debug: Using token: {'Available' if HUGGING_FACE_TOKEN else 'NOT AVAILABLE'}")
    if HUGGING_FACE_TOKEN:
        masked_token = HUGGING_FACE_TOKEN[:4] + "..." + HUGGING_FACE_TOKEN[-4:] if len(HUGGING_FACE_TOKEN) > 8 else "***"
        print(f"Debug: Token value: {masked_token}")
    
    try:
        # Initialize pipeline and move to GPU
        pipeline = Pipeline.from_pretrained(PIPELINE, use_auth_token=HUGGING_FACE_TOKEN)
        pipeline.to(DEVICE)

        # Enable TF32 for better performance
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True

        # Prepare diarization kwargs
        kwargs = {}
        if num_speakers is not None:
            kwargs["num_speakers"] = num_speakers
        if min_speakers is not None:
            kwargs["min_speakers"] = min_speakers
        if max_speakers is not None:
            kwargs["max_speakers"] = max_speakers

        print("⏳ Processing audio...")

        # Run diarization
        diarization = pipeline(audio_path, **kwargs)

        print("✨ Converting segments...")

        # Convert to list of segments
        segments = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            segments.append({"speaker": speaker, "start": turn.start, "end": turn.end})

        return segments
    except Exception as e:
        print(f"Error in diarize_audio: {str(e)}", file=sys.stderr)
        # Print additional information for debugging
        print(f"Python version: {sys.version}", file=sys.stderr)
        print(f"PyTorch version: {torch.__version__}", file=sys.stderr)
        print(f"Device: {DEVICE}", file=sys.stderr)
        print(f"Audio path: {audio_path}", file=sys.stderr)
        raise


def combine_diarization_with_transcription(diarization_segments, transcription_chunks):
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


def process_audio_with_diarization(
    audio_path,
    transcription_output_path=None,
    num_speakers=None,
    min_speakers=None,
    max_speakers=None,
):
    """
    Main function to process audio with diarization and optionally combine with transcription.
    """
    print(f"🚀 Running diarization on {DEVICE}")
    if num_speakers:
        print(f"👥 Using exact number of speakers: {num_speakers}")
    elif min_speakers or max_speakers:
        print(f"👥 Speaker bounds: {min_speakers or 'auto'} - {max_speakers or 'auto'}")

    # Get diarization segments
    diarization_segments = diarize_audio(
        audio_path, num_speakers, min_speakers, max_speakers
    )

    # Base output with just diarization
    output_data = {
        "speakers": list(set(seg["speaker"] for seg in diarization_segments)),
        "segments": diarization_segments,
    }

    # If transcription file exists, combine them
    if transcription_output_path and os.path.exists(transcription_output_path):
        with open(transcription_output_path, "r") as f:
            transcription_data = json.load(f)

        combined_output = combine_diarization_with_transcription(
            diarization_segments, transcription_data["chunks"]
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
        "--num-speakers", "-n", type=int, help="Exact number of speakers", default=None
    )
    parser.add_argument(
        "--min-speakers", type=int, help="Minimum number of speakers", default=None
    )
    parser.add_argument(
        "--max-speakers", type=int, help="Maximum number of speakers", default=None
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
