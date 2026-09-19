# Testing AudioPipe

This document provides comprehensive guidance on testing the AudioPipe project.

## Test Structure

The project uses pytest and has two layers:

1. **Unit Tests** (`test/test_unit.py`)
   - Pure logic: speaker mapping, segment consolidation, chunk merging, subprocess runner
   - Need only `pytest` and `pydub`; run by default
2. **Integration Tests** (`test/test_integration.py`)
   - Real Demucs / pyannote / Whisper runs on `test/data/`
   - Need the full `requirements.txt`, ffmpeg, and `--integration`

## Running Tests

### Quick Start

For convenience, use the provided shell script:

```bash
# Unit tests only
./run_tests.sh

# Include integration tests
AUDIOPIPE_INTEGRATION=1 ./run_tests.sh

# Include slow tests as well
AUDIOPIPE_INTEGRATION=1 AUDIOPIPE_SLOW=1 ./run_tests.sh
```

### Running Specific Tests

```bash
# Run integration tests (individual steps)
python -m pytest test/test_integration.py -v --integration

# Run full pipeline test (slow)
python -m pytest test/test_integration.py::test_full_pipeline -v --integration --runslow

# Run all tests with coverage
python -m pytest test/test_integration.py -v --integration --runslow --cov=. --cov-report=html
```

## Coverage Report

After running tests with coverage, a detailed HTML report is generated in the `htmlcov/` directory. Open `htmlcov/index.html` in your browser to view:

- Line-by-line coverage for each file
- Summary of overall project coverage
- Missing lines that need test coverage

## Test Data

The test data in `test/data/` includes:

- `speaker1.wav` - Sample audio from a male voice
- `speaker2.wav` - Sample audio from a female voice
- `test_input.wav` - Combined audio for testing the full pipeline

## Troubleshooting Tests

Here are some common issues you might encounter with tests:

- **Missing token**: If the `HUGGING_FACE_TOKEN` is not available, the diarization tests will be skipped
- If ffmpeg is not installed, audio processing tests will fail
- Set environment variables as needed: `export PYTORCH_ENABLE_MPS_FALLBACK=1`
- The transcription step is the most resource-intensive and may fail on limited hardware; `FORCE_CPU=1` is set by CI

## Continuous Integration

The project includes a GitHub Actions workflow for automated testing:

- Lint, mypy, and unit tests run on every push and PR to `master`
- Integration tests run weekly and via "Run workflow" (needs the `HUGGING_FACE_TOKEN` secret)
- See `.github/workflows/ci.yml`
