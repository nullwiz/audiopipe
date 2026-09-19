"""Fast unit tests for pure pipeline logic. No torch, no models, no audio."""

import sys

import pytest

import diarize
import pipeline


def test_mapping_overlap_wins():
    diar = [
        {"speaker": "A", "start": 0.0, "end": 5.0},
        {"speaker": "B", "start": 5.0, "end": 10.0},
    ]
    chunks = [
        {"text": "hi", "timestamp": [4.0, 7.0]},  # 1s in A, 2s in B
        {"text": "yo", "timestamp": [0.5, 4.5]},  # all A
    ]
    out = pipeline.simple_speaker_mapping(chunks, diar)
    assert [(s["speaker"], s["text"]) for s in out] == [("B", "hi"), ("A", "yo")]


def test_mapping_no_overlap_falls_back_to_nearest():
    diar = [
        {"speaker": "A", "start": 0.0, "end": 1.0},
        {"speaker": "B", "start": 20.0, "end": 21.0},
    ]
    out = pipeline.simple_speaker_mapping([{"text": "x", "timestamp": [18, 19]}], diar)
    assert out[0]["speaker"] == "B"


def test_mapping_skips_empty_and_none():
    diar = [{"speaker": "A", "start": 0.0, "end": 10.0}]
    chunks = [
        {"text": "   ", "timestamp": [0, 1]},
        {"text": "ok", "timestamp": [1, None]},
        {"text": "ok", "timestamp": [1]},
        {"text": "keep", "timestamp": [2, 3]},
    ]
    out = pipeline.simple_speaker_mapping(chunks, diar)
    assert [s["text"] for s in out] == ["keep"]
    assert out[0]["start"] == 2 and out[0]["end"] == 3


def test_merge_chunk_outputs_offsets_and_sorts():
    results = [
        ({"start_time": 900.0}, [{"text": "b", "timestamp": [1.0, 2.0]}]),
        (
            {"start_time": 0.0},
            [
                {"text": "a", "timestamp": [5.0, 6.0]},
                {"text": "bad", "timestamp": None},
            ],
        ),
    ]
    out = pipeline.merge_chunk_outputs(results)
    assert [c["text"] for c in out] == ["a", "b"]
    assert out[1]["timestamp"] == [901.0, 902.0]


def test_merge_continuous_fragments():
    segs = [
        {"speaker": "A", "start": 0.0, "end": 1.0},
        {"speaker": "B", "start": 1.5, "end": 2.0},
        {"speaker": "A", "start": 2.5, "end": 3.0},  # gap 1.5 from A → merge
        {"speaker": "A", "start": 6.0, "end": 7.0},  # gap 3.0 → no merge
    ]
    out = diarize.merge_continuous_fragments(segs)
    assert out == [
        {"speaker": "A", "start": 0.0, "end": 3.0},
        {"speaker": "B", "start": 1.5, "end": 2.0},
        {"speaker": "A", "start": 6.0, "end": 7.0},
    ]


def test_speaker_kwargs_passes_only_what_was_given():
    assert diarize.speaker_kwargs(None, None, None) == {}
    assert diarize.speaker_kwargs(2, 1, 8) == {"num_speakers": 2}
    assert diarize.speaker_kwargs(None, None, 8) == {"max_speakers": 8}


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
