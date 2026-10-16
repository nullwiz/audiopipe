"""Fast unit tests for pure pipeline logic. No torch, no models, no audio."""

import sys

import numpy as np
import pytest

import diarize
import pipeline
import server


def probs(*runs):
    """Build (frames, 8) probabilities from (speaker, seconds) runs; None = silence."""
    rows = []
    for spk, sec in runs:
        row = np.zeros(8)
        if spk is not None:
            row[spk] = 0.9
        rows += [row] * round(sec / diarize.FRAME_SEC)
    return np.array(rows)


def spans(segments):
    return [(s["speaker"][-1], s["start"], s["end"]) for s in segments]


def test_probs_to_segments_turns_and_merging():
    p = probs((0, 2), (None, 0.5), (0, 1), (1, 3), (None, 2), (1, 1))
    # A's 0.5 s pause merges; B's 2 s pause exceeds max_gap and splits
    assert spans(diarize.probs_to_segments(p)) == [
        ("0", 0.0, 3.5),
        ("1", 3.5, 6.5),
        ("1", 8.5, 9.5),
    ]


def test_probs_to_segments_overlap_goes_to_most_likely_speaker():
    p = probs((0, 2), (1, 2))
    p[150:200, 1] = 0.6  # B starts talking over A, but A is louder there
    assert spans(diarize.probs_to_segments(p)) == [("0", 0.0, 2.0), ("1", 2.0, 4.0)]


def test_probs_to_segments_drops_blips_and_rejoins():
    p = probs((0, 2), (1, 0.1), (0, 2))
    assert spans(diarize.probs_to_segments(p)) == [("0", 0.0, 4.1)]


def test_probs_to_segments_num_speakers_reassigns_extras():
    p = probs((0, 2), (2, 1), (1, 2))
    p[200:300, 1] = 0.3  # spurious third speaker; B is the runner-up
    out = diarize.probs_to_segments(p, num_speakers=2)
    assert spans(out) == [("0", 0.0, 2.0), ("1", 2.0, 5.0)]


def test_probs_to_segments_caps_length_at_least_confident_frame():
    p = probs((0, 70))
    p[2500, 0] = 0.55  # the dip inside the [20 s, 30 s] cut window
    out = diarize.probs_to_segments(p, max_len=30)
    assert spans(out) == [("0", 0.0, 25.0), ("0", 25.0, 45.0), ("0", 45.0, 70.0)]
    assert diarize.probs_to_segments(np.zeros((0, 8))) == []


def test_consolidate_segments():
    segs = [
        {"text": "hello", "start": 0.0, "end": 1.0, "speaker": "A"},
        {"text": "there", "start": 1.5, "end": 2.0, "speaker": "A"},
        {"text": "hi", "start": 2.2, "end": 3.0, "speaker": "B"},
        {"text": "later", "start": 5.0, "end": 6.0, "speaker": "B"},  # gap 2 > 1
    ]
    out = pipeline.consolidate_segments(segs, max_gap=1.0)
    assert out == [
        {"text": "hello there", "start": 0.0, "end": 2.0, "speaker": "A"},
        {"text": "hi", "start": 2.2, "end": 3.0, "speaker": "B"},
        {"text": "later", "start": 5.0, "end": 6.0, "speaker": "B"},
    ]
    assert segs[0]["text"] == "hello"  # input not mutated


def test_run_command_success():
    pipeline.run_command_with_progress(
        [sys.executable, "-c", "print('Loading thing'); print('Loading thing')"],
        "demo",
    )


def test_run_command_failure_carries_stderr():
    code = "import sys; sys.stderr.write('boom happened\\n'); sys.exit(3)"
    with pytest.raises(RuntimeError, match="boom happened"):
        pipeline.run_command_with_progress([sys.executable, "-c", code], "demo")


def test_get_device_force_cpu_does_not_import_torch(monkeypatch):
    monkeypatch.setenv("FORCE_CPU", "1")
    monkeypatch.setitem(sys.modules, "torch", None)  # import would raise ImportError
    assert pipeline.get_device("cuda") == "cpu"
    monkeypatch.delenv("FORCE_CPU")
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("AUDIOPIPE_TESTING", raising=False)
    assert pipeline.get_device("cpu") == "cpu"


def test_to_text_and_batched():
    segs = [{"speaker": "SPEAKER_00", "start": 3725.4, "end": 3726, "text": "hi"}]
    assert pipeline.to_text(segs) == "[01:02:05] SPEAKER_00: hi\n"
    assert pipeline.batched([5, 4, 3, 2, 1], 2) == [[5, 4], [3, 2], [1]]


def test_server_origin_allowlist():
    assert server.origin_allowed(None)
    assert server.origin_allowed("https://nullwiz.github.io")
    assert server.origin_allowed("http://127.0.0.1:8765")
    assert server.origin_allowed("http://localhost:3000")
    assert not server.origin_allowed("https://evil.example")
    assert not server.origin_allowed("http://localhost.evil.example")


def test_server_parse_options():
    opts = server.parse_options("num_speakers=2&language=de&separate=0&filename=a.MP3")
    assert opts == {
        "num_speakers": 2,
        "language": "de",
        "separate": False,
        "suffix": ".mp3",
    }
    assert server.parse_options("filename=../../x.s;h")["suffix"] == ""
    with pytest.raises(ValueError):
        server.parse_options("num_speakers=9")
