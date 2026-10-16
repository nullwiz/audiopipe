from __future__ import annotations

import argparse
import json
import os
from typing import Any

import numpy as np


MODEL = "nvidia/Nemotron-3-Diarization"
SAMPLE_RATE = 16000
FRAME_SEC = 0.01  # the model emits one logit row per 10 ms
MAX_SPEAKERS = 8


def probs_to_segments(
    probs: np.ndarray,
    num_speakers: int | None = None,
    threshold: float = 0.5,
    min_dur: float = 0.25,
    max_gap: float = 1.0,
    max_len: float = 30.0,
) -> list[dict[str, Any]]:
    """Turn (frames, speakers) activity probabilities into non-overlapping segments.

    Each speech frame goes to its single most likely speaker (overlaps are
    resolved, so audio is never transcribed twice). Speaker channels are in
    order of first arrival, so num_speakers keeps the first N. Blips shorter
    than min_dur are dropped, same-speaker neighbours within max_gap merge, and
    nothing exceeds max_len: over-long speech is split at its least confident
    frame so ASR models with a context cap (and Whisper's 30 s window) cope.
    """
    if len(probs) == 0:
        return []
    speech = probs.max(axis=1) > threshold  # before trimming: late speakers still count
    if num_speakers:
        probs = probs[:, :num_speakers]
    confidence = probs.max(axis=1)
    owner = np.where(speech, probs.argmax(axis=1), -1)

    # run-length encode owner → [speaker, start_frame, end_frame)
    edges = np.flatnonzero(np.diff(owner)) + 1
    starts = np.concatenate([[0], edges])
    ends = np.concatenate([edges, [len(owner)]])
    runs = [
        [int(owner[s]), int(s), int(e)]
        for s, e in zip(starts, ends, strict=True)
        if owner[s] >= 0 and (e - s) * FRAME_SEC >= min_dur
    ]

    max_frames = round(max_len / FRAME_SEC)
    gap_frames = round(max_gap / FRAME_SEC)
    merged: list[list[int]] = []
    for spk, s, e in runs:
        prev = merged[-1] if merged else None
        if (
            prev
            and prev[0] == spk
            and s - prev[2] <= gap_frames
            and e - prev[1] <= max_frames
        ):
            prev[2] = e
        else:
            merged.append([spk, s, e])

    out: list[dict[str, Any]] = []
    for spk, s, e in merged:
        while e - s > max_frames:
            # cut at the least confident frame in the last third of the window
            lo = s + max_frames * 2 // 3
            cut = lo + int(confidence[lo : s + max_frames].argmin())
            out.append(_segment(spk, s, cut))
            s = cut
        out.append(_segment(spk, s, e))
    return out


def _segment(spk: int, start: int, end: int) -> dict[str, Any]:
    return {
        "speaker": f"SPEAKER_{spk:02d}",
        "start": round(start * FRAME_SEC, 2),
        "end": round(end * FRAME_SEC, 2),
    }


def load_audio(path: str) -> np.ndarray:
    """Mono float32 at 16 kHz (librosa decodes via soundfile/ffmpeg)."""
    import librosa

    audio, _ = librosa.load(path, sr=SAMPLE_RATE, mono=True)
    return audio


def speaker_probs(audio: np.ndarray, device: str, model: str = MODEL) -> np.ndarray:
    """Run Nemotron 3 Diarization offline; returns (frames, 8) probabilities."""
    import torch
    from transformers import AutoModelForAudioFrameClassification, AutoProcessor

    processor = AutoProcessor.from_pretrained(model)
    net = AutoModelForAudioFrameClassification.from_pretrained(model).to(device)
    net.eval()
    inputs = processor(audio, sampling_rate=SAMPLE_RATE).to(device, dtype=net.dtype)
    with torch.inference_mode():  # offline mode chunks internally: any length works
        logits = net(**inputs).logits[0]
    return torch.sigmoid(logits).float().cpu().numpy()


def diarize(
    audio_path: str,
    num_speakers: int | None = None,
    device: str = "cpu",
    model: str = MODEL,
) -> dict[str, Any]:
    print(f"🎙️ Running {model} on {device}...")
    probs = speaker_probs(load_audio(audio_path), device, model)
    segments = probs_to_segments(probs, num_speakers)
    speakers = sorted({s["speaker"] for s in segments})
    print(f"🎯 {len(speakers)} speakers, {len(segments)} segments")
    return {"speakers": speakers, "segments": segments}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Local speaker diarization")
    parser.add_argument("audio_path", help="Path to the audio file")
    parser.add_argument(
        "--num-speakers",
        "-n",
        type=int,
        choices=range(1, MAX_SPEAKERS + 1),
        metavar=f"1-{MAX_SPEAKERS}",
        help="Number of speakers, if known",
    )
    parser.add_argument("--device", "-d", default="cpu", help="cpu, cuda or mps")
    parser.add_argument("--model", default=MODEL, help="Model id or local path")
    args = parser.parse_args()

    result = diarize(args.audio_path, args.num_speakers, args.device, args.model)
    output_path = f"{os.path.splitext(args.audio_path)[0]}_diarized.json"
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"✅ Saved: {output_path}")
