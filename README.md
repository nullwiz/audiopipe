# [AudioPipe](https://nullwiz.github.io/audiopipe/)
<img width="1099" alt="Screenshot_1" src="https://github.com/user-attachments/assets/4b98dbf8-351d-4dd3-933e-dc720613e3bb" />

Denoising, speaker diarization and transcription in a single local pipeline.
Feed it a podcast, interview or meeting; get back who said what, with timestamps, as JSON and plain text.

**Runs entirely on your machine.** No API keys, no Hugging Face token, no cloud. Models download once (about 3 GB) and then `--offline` guarantees nothing touches the network.

## Models

| Step | Model | Notes |
|------|-------|-------|
| Separation | [Demucs `htdemucs`](https://github.com/facebookresearch/demucs) | Strips music/noise; skip with `--no-separation` |
| Diarization | [NVIDIA Nemotron 3 Diarization](https://huggingface.co/nvidia/Nemotron-3-Diarization) | Streaming Sortformer, up to 8 speakers, any length |
| Transcription | [NVIDIA Nemotron 3.5 ASR](https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b) (default) | 600M params, 32 languages, punctuation, language auto-detect |
| | any Whisper checkpoint via `--model` | e.g. `openai/whisper-large-v3-turbo` for 99 languages |

Both NVIDIA models are open weights (OpenMDW 1.1, commercial use OK) and run through 🤗 Transformers on CUDA, Apple Silicon (MPS) or CPU. NeMo isn't needed.

## How it works

1. **Separation**: Demucs pulls the vocals out of the input → `combined_vocals.wav`
2. **Diarization**: Nemotron 3 Diarization labels every 10 ms frame with a speaker. Overlaps go to the most likely speaker, blips under 0.25 s are dropped, and same-speaker turns within 1 s are merged, capped at 30 s → `combined_vocals_diarized.json`
3. **Transcription**: each speaker turn is cut out and transcribed on its own, in batches. Speaker attribution comes straight from the diarizer, with no timestamp guesswork → `final_transcription.json` + `final_transcription.txt`

On an M-series Mac, a 10-minute two-speaker recording takes about 40 s end to end, including separation.

## Requirements

- Python 3.10+
- FFmpeg
- Optional: an NVIDIA GPU or Apple Silicon; CPU works too

## Installation

```bash
git clone https://github.com/nullwiz/audiopipe.git
cd audiopipe
pip install -e .          # gives you the `audiopipe` command
brew install ffmpeg       # or apt-get install ffmpeg
```

## Usage

```bash
# Everything: separate → diarize → transcribe
audiopipe input.mp3

# Clean speech (no music)? Skip separation, it's faster
audiopipe meeting.m4a --no-separation

# Known speaker count and language
audiopipe input.mp3 --num-speakers 3 --language de

# Whisper instead of Nemotron ASR (for languages outside Nemotron's 32)
audiopipe input.mp3 --model openai/whisper-large-v3-turbo

# Fully offline after the first run
audiopipe input.mp3 --offline

# Resume: 2 = from diarization, 3 = transcription only
audiopipe input.mp3 --start-step 3 -o runs/ep01
```

`python pipeline.py ...` works the same without installing.

## Output

All files go to `--output-dir` (default `output/`):

- **`final_transcription.txt`**: the readable transcript
  ```
  [00:00:00] SPEAKER_00: Welcome back to the show.
  [00:00:05] SPEAKER_01: Thanks for having me.
  ```
- **`final_transcription.json`**: the same, structured
  ```json
  {"segments": [{"text": "Welcome back to the show.", "speaker": "SPEAKER_00", "start": 0.0, "end": 5.79}]}
  ```
- **`combined_vocals_diarized.json`**: who spoke when, `{"speakers": [...], "segments": [{"speaker", "start", "end"}]}`
- **`combined_vocals.wav`** / **`combined_background.wav`**: separated stems
- **`pipeline.log`**: detailed log

Speakers are numbered in order of first appearance.

## Options

```
audiopipe INPUT [OPTIONS]

  --num-speakers, -n 1-8       Number of speakers, if known
  --language, -l CODE          e.g. en, de-DE; auto-detected if omitted
  --start-step, -s 1|2|3       1=separation, 2=diarization, 3=transcription
  --device, -d cpu|cuda|mps    Auto-detected if omitted
  --output-dir, -o DIR         Default: output
  --model, -m NAME             ASR model id or local path (default nvidia/nemotron-3.5-asr-streaming-0.6b;
                               ids containing "whisper" use the Whisper pipeline)
  --no-separation              Skip Demucs
  --offline                    Never touch the network (models must be cached)
  --no-consolidate             One segment per diarized turn; don't merge same-speaker runs
```

## Web UI

The viewer at [nullwiz.github.io/audiopipe](https://nullwiz.github.io/audiopipe/) is a static page: drop in a `final_transcription.json` (plus the audio, for a waveform) to browse, search and export SRT.

To transcribe from the browser, start the local backend:

```bash
audiopipe-serve            # http://127.0.0.1:8737, add --offline / --device as needed
```

Open http://127.0.0.1:8737, or keep using the GitHub Pages page: it detects the backend on `127.0.0.1:8737` and shows **TRANSCRIBE AUDIO**. Audio goes only to your own machine. The backend listens on loopback only and accepts browser requests only from the Pages site and localhost. If your browser blocks an https page from reaching `http://127.0.0.1`, use the local URL. A different backend can be set with `?backend=http://host:port`.

The steps also run standalone:

```bash
python dem.py INPUT [--device cpu|cuda|mps] [--vocals-only] [-o DIR]
python diarize.py VOCALS.wav [--num-speakers N] [--device cpu|cuda|mps] [--model ID_OR_PATH]
```

## Supported formats

Anything FFmpeg decodes: `.mp3`, `.wav`, `.m4a`, `.flac`, `.ogg`, and video (`.mp4`, `.mov`, `.mkv`, ...).

## Troubleshooting

- **Wrong speaker count**: pass `--num-speakers`. It keeps the N earliest voices and reassigns stray frames to them.
- **Overlapping speech**: each moment goes to one speaker, so short interjections over someone else can be lost.
- **Language**: Nemotron ASR auto-detects. Pass `--language` to pin it, or use a Whisper model for languages it doesn't cover.
- **Offline errors**: run once online (or `hf download nvidia/Nemotron-3-Diarization` and `hf download nvidia/nemotron-3.5-asr-streaming-0.6b`) so the models are cached.
- **Memory**: `--device cpu` if the GPU runs out. Long files are fine since both models work in chunks.

## Testing

```bash
pip install -r requirements-dev.txt
pytest                                                   # unit tests, no models
pytest test/test_integration.py -v --integration --runslow   # real models on test/data/
```

See [README.test.md](README.test.md).
