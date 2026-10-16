# Contributing to AudioPipe

Thank you for considering contributing to AudioPipe! This document provides guidelines for contributing to the project.

## Project Structure

The project consists of the following key files:

```
audiopipe/
├── .github/workflows/      # CI: lint + unit on every push, integration on dispatch/weekly
│   └── ci.yml
├── pipeline.py             # Main orchestration script (also the `audiopipe` entry point)
├── dem.py                  # Audio separation (Demucs)
├── diarize.py              # Speaker diarization (NVIDIA Nemotron 3 Diarization)
├── test/
│   ├── conftest.py         # Pytest options (--integration, --runslow)
│   ├── test_unit.py        # Fast tests of pure logic; run by default
│   ├── test_integration.py # Real model runs; need --integration
│   └── data/               # Test audio
├── requirements.txt        # Runtime dependencies
├── requirements-dev.txt    # + pytest, ruff, mypy
├── README.md               # Project documentation
├── README.test.md          # Testing documentation
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
   pip install -r requirements-dev.txt
   ```

## Testing

Before submitting a pull request:

```bash
ruff check . && ruff format --check .
mypy --config-file mypy.ini dem.py diarize.py pipeline.py server.py
pytest                                              # unit tests, seconds
pytest test/test_integration.py -v --integration    # real models, minutes
```

CI runs lint + unit tests on every push to `master`; integration tests run weekly and on manual dispatch.

## Environment Variables

- `HF_HUB_OFFLINE=1`: Never hit the network (same as `--offline`); models must be cached
- `FORCE_CPU=1`: Skip GPU detection entirely

## Pull Request Process

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run the tests
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## Coding Style

- `ruff format` is the formatter; `ruff check` and strict `mypy` must pass
- Keep pure logic importable without torch (import heavy deps inside functions) so unit tests stay fast
