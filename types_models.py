"""Type definitions and Pydantic models for AudioPipe.

This module provides comprehensive type annotations and data validation
for the AudioPipe audio processing pipeline.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Literal, Protocol, Union

from pydantic import BaseModel, Field, root_validator, validator
from pydantic.types import NonNegativeFloat, PositiveFloat, PositiveInt


# Type aliases for better readability
AudioPath = Union[str, Path]
TimestampSeconds = NonNegativeFloat
DurationSeconds = PositiveFloat
SpeakerID = str
DeviceType = Literal["cpu", "cuda", "mps"]
LanguageCode = str


class ProcessingStep(Enum):
    """Pipeline processing steps."""

    SEPARATION = 1
    DIARIZATION = 2
    TRANSCRIPTION = 3


class AudioSegment(BaseModel):
    """Represents a single audio segment with speaker attribution."""

    text: str = Field(..., description="Transcribed text content")
    start: TimestampSeconds = Field(..., description="Start time in seconds")
    end: TimestampSeconds = Field(..., description="End time in seconds")
    speaker: SpeakerID = Field(..., description="Speaker identifier")

    @validator("end")
    def end_after_start(self, v: float, values: dict[str, Any]) -> float:
        """Ensure end time is after start time."""
        if "start" in values and v <= values["start"]:
            raise ValueError("End time must be after start time")
        return v

    @property
    def duration(self) -> DurationSeconds:
        """Calculate segment duration."""
        return self.end - self.start

    def overlaps_with(self, other: AudioSegment) -> bool:
        """Check if this segment overlaps with another segment."""
        return self.start < other.end and self.end > other.start


class DiarizationSegment(BaseModel):
    """Represents a diarization segment without transcription."""

    speaker: SpeakerID = Field(..., description="Speaker identifier")
    start: TimestampSeconds = Field(..., description="Start time in seconds")
    end: TimestampSeconds = Field(..., description="End time in seconds")

    @validator("end")
    def end_after_start(self, v: float, values: dict[str, Any]) -> float:
        """Ensure end time is after start time."""
        if "start" in values and v <= values["start"]:
            raise ValueError("End time must be after start time")
        return v

    @property
    def duration(self) -> DurationSeconds:
        """Calculate segment duration."""
        return self.end - self.start


class DiarizationResult(BaseModel):
    """Complete diarization results."""

    speakers: list[SpeakerID] = Field(..., description="List of unique speaker IDs")
    segments: list[DiarizationSegment] = Field(..., description="Diarization segments")

    @validator("speakers")
    def speakers_not_empty(self, v: list[str]) -> list[str]:
        """Ensure speakers list is not empty."""
        if not v:
            raise ValueError("Speakers list cannot be empty")
        return v

    @validator("segments")
    def segments_not_empty(
        self, v: list[DiarizationSegment]
    ) -> list[DiarizationSegment]:
        """Ensure segments list is not empty."""
        if not v:
            raise ValueError("Segments list cannot be empty")
        return v

    @root_validator
    def validate_speaker_consistency(self, values: dict[str, Any]) -> dict[str, Any]:
        """Ensure all segment speakers are in the speakers list."""
        speakers = values.get("speakers", [])
        segments = values.get("segments", [])

        segment_speakers = {seg.speaker for seg in segments}
        speaker_set = set(speakers)

        if not segment_speakers.issubset(speaker_set):
            missing = segment_speakers - speaker_set
            raise ValueError(
                f"Segments contain speakers not in speakers list: {missing}"
            )

        return values


class TranscriptionResult(BaseModel):
    """Complete transcription results with speaker attribution."""

    segments: list[AudioSegment] = Field(..., description="Transcribed segments")

    @validator("segments")
    def segments_not_empty(self, v: list[AudioSegment]) -> list[AudioSegment]:
        """Ensure segments list is not empty."""
        if not v:
            raise ValueError("Segments list cannot be empty")
        return v

    @validator("segments")
    def segments_chronological(self, v: list[AudioSegment]) -> list[AudioSegment]:
        """Ensure segments are in chronological order."""
        for i in range(1, len(v)):
            if v[i].start < v[i - 1].start:
                raise ValueError("Segments must be in chronological order")
        return v

    @property
    def speakers(self) -> list[SpeakerID]:
        """Get unique speakers from segments."""
        return sorted({seg.speaker for seg in self.segments})

    @property
    def total_duration(self) -> DurationSeconds:
        """Calculate total duration from first to last segment."""
        if not self.segments:
            return 0.0
        return self.segments[-1].end - self.segments[0].start


class PipelineConfig(BaseModel):
    """Configuration for the audio processing pipeline."""

    input_audio: AudioPath = Field(..., description="Path to input audio file")
    num_speakers: PositiveInt | None = Field(None, description="Number of speakers")
    min_speakers: PositiveInt | None = Field(
        None, description="Minimum number of speakers"
    )
    max_speakers: PositiveInt | None = Field(
        None, description="Maximum number of speakers"
    )
    language: LanguageCode | None = Field(
        None, description="Language code for transcription"
    )
    start_step: ProcessingStep = Field(
        ProcessingStep.SEPARATION, description="Starting step"
    )
    device: DeviceType | None = Field(None, description="Processing device")
    chop: bool = Field(False, description="Split audio into chunks")
    chunk_duration: PositiveInt = Field(900, description="Chunk duration in seconds")

    @validator("input_audio")
    def audio_file_exists(self, v: str | Path) -> Path:
        """Ensure input audio file exists."""
        path = Path(v)
        if not path.exists():
            raise ValueError(f"Input audio file does not exist: {path}")
        return path

    @root_validator
    def validate_speaker_constraints(self, values: dict[str, Any]) -> dict[str, Any]:
        """Validate speaker number constraints."""
        num_speakers = values.get("num_speakers")
        min_speakers = values.get("min_speakers")
        max_speakers = values.get("max_speakers")

        if num_speakers is not None:
            if min_speakers is not None and num_speakers < min_speakers:
                raise ValueError("num_speakers cannot be less than min_speakers")
            if max_speakers is not None and num_speakers > max_speakers:
                raise ValueError("num_speakers cannot be greater than max_speakers")

        if min_speakers is not None and max_speakers is not None:
            if min_speakers > max_speakers:
                raise ValueError("min_speakers cannot be greater than max_speakers")

        return values


class WhisperChunk(BaseModel):
    """Represents a chunk from Whisper transcription output."""

    timestamp: list[float | None] = Field(..., description="Start and end timestamps")
    text: str = Field(..., description="Transcribed text")

    @validator("timestamp")
    def validate_timestamp(self, v: list[float | None]) -> list[float | None]:
        """Validate timestamp format."""
        if len(v) != 2:
            raise ValueError("Timestamp must have exactly 2 elements")
        if v[0] is not None and v[1] is not None and v[0] >= v[1]:
            raise ValueError("Start timestamp must be before end timestamp")
        return v

    @property
    def start_time(self) -> float | None:
        """Get start time."""
        return self.timestamp[0]

    @property
    def end_time(self) -> float | None:
        """Get end time."""
        return self.timestamp[1]


class WhisperResult(BaseModel):
    """Complete Whisper transcription result."""

    chunks: list[WhisperChunk] = Field(..., description="Transcription chunks")
    duration: float | None = Field(None, description="Total audio duration")

    @validator("chunks")
    def chunks_not_empty(self, v: list[WhisperChunk]) -> list[WhisperChunk]:
        """Ensure chunks list is not empty."""
        if not v:
            raise ValueError("Chunks list cannot be empty")
        return v


# Protocol definitions for type checking
class AudioProcessor(Protocol):
    """Protocol for audio processing functions."""

    def __call__(self, audio_path: AudioPath, **kwargs: Any) -> Any:
        """Process audio file."""
        ...


class ProgressDisplay(Protocol):
    """Protocol for progress display objects."""

    def update_progress(self, message: str) -> None:
        """Update progress message."""
        ...

    def update_log(self, message: str) -> None:
        """Update log message."""
        ...


# Exception classes
class AudioPipeError(Exception):
    """Base exception for AudioPipe errors."""


class AudioProcessingError(AudioPipeError):
    """Error during audio processing."""


class DiarizationError(AudioPipeError):
    """Error during speaker diarization."""


class TranscriptionError(AudioPipeError):
    """Error during transcription."""


class ConfigurationError(AudioPipeError):
    """Error in pipeline configuration."""
