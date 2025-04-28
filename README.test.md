# Testing AudioPipe

This document provides comprehensive guidance on testing the AudioPipe project.

## Test Structure

The project uses pytest and includes integration tests:

1. **Integration Tests**
   - Located in `test/test_integration.py`
   - Test the complete pipeline with real audio processing
   - Use real audio samples in `test/data/`

## Running Tests

### Quick Start

For convenience, use the provided shell script:

```bash
# Run all tests with coverage report
./run_tests.sh
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

## Troubleshooting

1. **Missing Dependencies**:
   - Ensure you've installed all required packages with `pip install -r requirements.txt`
   - For testing, also run `pip install pytest pytest-cov edge-tts`

2. **Edge-TTS Issues**:
   - If edge-tts fails, the tests will create mock audio files
   - For best results, ensure edge-tts is properly installed

3. **CUDA/GPU Issues**:
   - The tests can run on CPU if GPU is not available
   - Set environment variables as needed: `export PYTORCH_ENABLE_MPS_FALLBACK=1`

4. **Audio Processing Failures**:
   - Ensure FFmpeg is properly installed: `sudo apt-get install ffmpeg`
   - Check output files in the `output/` directory for debugging

## Continuous Integration

The project includes a GitHub Actions workflow for automated testing:

- Integration tests run on every push
- Full pipeline tests can be run manually
- See `.github/workflows/test.yml` for details 

## Visualizing Results

The project includes `visualize.py` for analyzing pipeline outputs:

```bash
# Generate waveform visualization
python visualize.py waveform input.mp3

# Create speaker diarization timeline
python visualize.py diarization output/combined_vocals_diarized.json

# Visualize transcript
python visualize.py transcript output/final_transcription.json

# Create interactive HTML report (most useful)
python visualize.py report output/final_transcription.json --audio output/combined_vocals.wav
```

Each command accepts a `--output` parameter to specify the output file location. 