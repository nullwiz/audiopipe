# [AudioPipe](https://nullwiz.github.io/audiopipe/)
<img width="1099" alt="Screenshot_1" src="https://github.com/user-attachments/assets/4b98dbf8-351d-4dd3-933e-dc720613e3bb" />

Denoising, speaker diarization and transcription in a single streamlined process. 
It's perfect for transcribing podcasts, interviews, or any multi-speaker audio content, as long as they have clear audio.
In the output, you'll get a JSON file with the transcript, speaker labels, and timestamps. 

## Features

- **Audio Source Separation**: Extract vocals from background music/noise
- **Speaker Diarization**: Identify and separate different speakers
- **Transcription**: Convert speech to text with timestamps
- **Post-processing**: Consolidate transcripts for readability
- **Clean Display**: Real-time progress updates without cluttering the console
- **Step Skipping**: Start the pipeline from any step
- **Cross-platform**: Supports Windows, macOS, and Linux

## Requirements

- Python 3.8+
- FFmpeg (for audio processing)
- CUDA-compatible GPU (recommended, but CPU mode available)
- Hugging Face token (optional, for enhanced speaker diarization accuracy)

### Installation

```bash
# Clone the repository
git clone https://github.com/nullwiz/audiopipe.git
cd audiopipe

# Install dependencies
pip install -r requirements.txt

# For macOS (with Homebrew)
brew install ffmpeg
```

## Usage

```bash
# Basic usage - runs all steps in sequence
python pipeline.py input.mp3

# Resume from a specific step:
python pipeline.py input.mp3 --start-step 2  # Skip separation, start from diarization
python pipeline.py input.mp3 --start-step 3  # Skip to transcription step

# Optional parameters:
python pipeline.py input.mp3 --num-speakers 3 --language en

# For very long audio files (>1 hour), use chopping mode:
python pipeline.py input.mp3 --chop  # Splits into 15-minute chunks for processing
```

## Pipeline Steps

The process consists of three main steps that can be run together or separately:

1. **Separation** (Step 1): Extracts vocals from background using Demucs
   - Input: Any audio/video file
   - Output: `output/combined_vocals.wav`
   - Note: Files under 60MB are processed as a single unit; larger files are chunked automatically

2. **Diarization** (Step 2): Identifies different speakers
   - Input: `output/combined_vocals.wav`
   - Output: `output/combined_vocals_diarized.json`
   - Tip: Use `--num-speakers` for better results when speaker count is known

3. **Transcription** (Step 3): Converts complete audio to text, then maps speakers
   - Input: `output/combined_vocals.wav` and diarization data
   - Output: `output/final_transcription.json`
   - Architecture: Complete audio transcription → speaker mapping (no chunking)
   - Tip: Specify `--language` code for improved accuracy

## Output Files Explained

The pipeline creates several files during processing, all stored in the `output/` directory:

### Audio Files
- **`combined_vocals.wav`**: Extracted voices/speech from the input
- **`combined_background.wav`**: Background music/noise separated from the input
- **`speakers/SPEAKER_XX/*.wav`**: Individual audio segments for each speaker

### JSON Files
- **`combined_vocals_diarized.json`**: Speaker diarization results showing who speaks when
  ```json
  {
    "speakers": ["SPEAKER_01", "SPEAKER_02", ...],
    "segments": [
      {"speaker": "SPEAKER_01", "start": 0.0, "end": 2.5},
      {"speaker": "SPEAKER_02", "start": 2.7, "end": 5.1},
      ...
    ]
  }
  ```

- **`final_transcription.json`**: Complete transcription with speaker attribution in chronological order
  ```json
  {
    "segments": [
      {"text": "Complete sentence or phrase", "start": 0.1, "end": 2.5, "speaker": "SPEAKER_01"},
      {"text": "Another speaker's response", "start": 2.7, "end": 5.1, "speaker": "SPEAKER_02"},
      {"text": "Continuing conversation", "start": 5.3, "end": 8.0, "speaker": "SPEAKER_01"},
      ...
    ]
  }
  ```

### Temporary Directories
- **`separated/`**: Intermediate files from audio separation (preserved for resuming)
- **`chunks/`**: Audio chunks when using `--chop` mode (preserved for debugging)

### Resuming from Steps
The presence of these files allows the pipeline to resume from different steps:
- If `combined_vocals.wav` exists, audio separation can be skipped (step 1)
- If `combined_vocals_diarized.json` exists, diarization can be skipped (step 2)

## Visualization Tools

AudioPipe includes tools to visualize your transcripts and generate interactive reports:

```bash
# Generate timeline visualization for transcript
python visualize.py transcript output/final_transcription.json

# Generate interactive HTML report with audio playback
python visualize.py report output/final_transcription.json --audio output/combined_vocals.wav

# Visualize raw diarization (speaker timeline)
python visualize.py diarization output/combined_vocals_diarized.json
```

For best results:
1. Use the HTML report for interactive exploration of longer content
2. For very long audio (>1 hour), use `--chop` mode for processing

## Supported File Formats

- Audio: `.mp3`, `.wav`, `.m4a`, `.flac`, `.ogg`
- Video (extracts audio): `.mp4`, `.mov`, `.avi`, `.mkv`

## Command-Line Options

### pipeline.py

```
python pipeline.py INPUT_AUDIO [OPTIONS]

Arguments:
  INPUT_AUDIO                Path to input audio/video file

Options:
  --num-speakers, -n INT     Number of speakers (optional, auto-detected if not specified)
  --language, -l STRING      Language code for transcription (e.g., 'en', 'es', 'fr')
  --start-step, -s [1-3]     Start from step: 1=separation, 2=diarization, 3=transcription
  --chop, -c                 Split input audio into 15-minute chunks for processing
  --device, -d [cpu|cuda|mps] Device to use for processing (auto-detected if not specified)
  --help                     Show this help message
```

### dem.py (Audio Separation - removes background noise)

```
python dem.py INPUT_FILE

Arguments:
  INPUT_FILE                 Path to input audio/video file
```

### diarize.py (Speaker Diarization)

```
python diarize.py INPUT_AUDIO [OPTIONS]

Arguments:
  INPUT_AUDIO                Path to vocals audio file (usually output/combined_vocals.wav)

Options:
  --num-speakers, -n INT     Number of speakers (optional, auto-detected if not specified)
```

## macOS Support

For macOS users, there are two operation modes:

### CPU Mode (No CUDA)

For Macs without dedicated NVIDIA GPUs:

```bash
# Add this to your .bashrc or .zshrc
export PYTORCH_ENABLE_MPS_FALLBACK=1

# Run with CPU-only flag
python pipeline.py input.mp3 --device cpu
```

### GPU Mode (Apple Silicon)

For M1/M2/M3 Macs, you can utilize Metal Performance Shaders:

```bash
# Install PyTorch with MPS support
pip install torch torchvision torchaudio

# Run with MPS device
python pipeline.py input.mp3 --device mps
```

## Output Format

The final output is a JSON file with chronological segments:

```json
{
  "segments": [
    {
      "text": "Transcript text for this segment",
      "start": 0.5,
      "end": 4.2,
      "speaker": "SPEAKER_01"
    },
    {
      "text": "Response from another speaker",
      "start": 4.5,
      "end": 7.8,
      "speaker": "SPEAKER_02"
    },
    ...
  ]
}
```

## Troubleshooting

- **Audio Processing**:
  - Standard mode processes complete audio files for best quality
  - For very long files (>1 hour), use `--chop` to split into 15-minute chunks
  - If you get memory errors, try using `--device cpu` which uses less memory

- **Transcription Accuracy**:
  - Specify the language with `--language` for better results
  - Complete audio transcription provides better context than chunking
  - Improved accuracy for clear audio with minimal background noise

- **Speaker Identification**:
  - If speakers are not correctly identified, try setting `--num-speakers`
  - Better results when speakers have distinct voices and don't talk over each other
  - Hugging Face token improves diarization accuracy but is not required

## Testing

The project includes a test suite for validating the pipeline functionality:

```bash
# Run basic integration tests
python -m pytest test/test_integration.py -v --integration

# Run full pipeline test (slower)
python -m pytest test/test_integration.py::test_full_pipeline -v --integration --runslow
```


- **Full Pipeline Test**: Use `--runslow` to run the complete pipeline test
- **Hugging Face Token**: For full testing, provide your token with `--hf-token` or set the `HUGGING_FACE_TOKEN` environment variable

For more details on Testing, check [README.test.md](README.test.md).
