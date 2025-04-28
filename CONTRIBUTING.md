# Contributing to AudioPipe

Thank you for considering contributing to AudioPipe! This document provides guidelines for contributing to the project.

## Project Structure

The project consists of the following key files:

```
audiopipe/
├── .github/workflows/      # CI/CD configurations
│   └── test.yml            # GitHub Actions workflow for testing
├── pipeline.py             # Main orchestration script
├── dem.py                  # Audio separation module
├── diarize.py              # Speaker diarization module
├── process_transcript.py   # Post-processing for consolidation
├── test_pipeline.py        # Test suite
├── conftest.py             # Pytest configuration
├── requirements.txt        # Python dependencies
├── README.md               # Project documentation
├── TESTING.md              # Testing documentation
├── CONTRIBUTING.md         # Contribution guidelines
├── .gitignore              # Git ignore patterns
└── output/                 # Output directory (only .gitkeep is committed)
    └── .gitkeep            # Empty file to preserve directory
```

## Development Environment

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/audiopipe.git
   cd audiopipe
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   pip install pytest pytest-cov edge-tts  # For testing
   ```

3. Set up your Hugging Face token:
   ```bash
   export HUGGING_FACE_TOKEN='your_token_here'
   ```

## Testing

Before submitting a pull request, please run the test suite:

```bash
# Run basic tests
pytest test_pipeline.py -v -k "not slow"

# Run all tests including slow ones (if you have time)
pytest test_pipeline.py -v --runslow
```

## Environment Variables

- `HUGGING_FACE_TOKEN`: Required for speaker diarization (pyannote.audio)

## Pull Request Process

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run the tests
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## Coding Style

- Follow PEP 8 guidelines
- Include docstrings for functions and classes
- Keep comments concise and meaningful
- Use type hints where appropriate
