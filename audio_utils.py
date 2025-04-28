#!/usr/bin/env python3
"""
Audio Utilities for AudioPipe

This module provides audio processing utilities to enhance audio quality
and optimize processing for the pipeline.
"""

import os
import numpy as np
import soundfile as sf
import logging
from typing import Tuple, Optional, List, Dict
import librosa
import torch

logger = logging.getLogger(__name__)

def analyze_audio(audio_path: str) -> Dict:
    """
    Analyze audio file and return key metrics
    
    Args:
        audio_path: Path to audio file
        
    Returns:
        dict: Audio metrics including:
            - rms_db: Root mean square in dB
            - peak_db: Peak level in dB
            - snr: Estimated signal-to-noise ratio
            - duration: Audio duration in seconds
            - sample_rate: Sample rate in Hz
    """
    try:
        # Load audio with librosa
        y, sr = librosa.load(audio_path, sr=None)
        
        # Calculate RMS level
        rms = np.sqrt(np.mean(y**2))
        rms_db = 20 * np.log10(rms + 1e-10)  # Add small value to avoid log(0)
        
        # Calculate peak level
        peak = np.max(np.abs(y))
        peak_db = 20 * np.log10(peak + 1e-10)
        
        # Estimate SNR (simplified method)
        # Take the quietest 1% of audio as noise estimate
        y_sorted = np.sort(np.abs(y))
        noise_level = np.mean(y_sorted[:int(len(y_sorted) * 0.01)])
        signal_level = np.mean(y_sorted[int(len(y_sorted) * 0.5):])  # Top 50% as signal
        snr = 20 * np.log10((signal_level + 1e-10) / (noise_level + 1e-10))
        
        # Get duration
        duration = librosa.get_duration(y=y, sr=sr)
        
        return {
            "rms_db": rms_db,
            "peak_db": peak_db,
            "snr": snr,
            "duration": duration,
            "sample_rate": sr
        }
    
    except Exception as e:
        logger.error(f"Error analyzing audio: {str(e)}")
        return {
            "rms_db": None,
            "peak_db": None, 
            "snr": None,
            "duration": 0,
            "sample_rate": 0,
            "error": str(e)
        }

def apply_gain_control(audio_path: str, output_path: Optional[str] = None, 
                       target_rms_db: float = -20.0, 
                       max_gain_db: float = 30.0) -> str:
    """
    Apply automatic gain control to audio to reach target RMS level
    
    Args:
        audio_path: Path to input audio file
        output_path: Path to output audio file (if None, creates temp file)
        target_rms_db: Target RMS level in dB
        max_gain_db: Maximum gain to apply in dB
        
    Returns:
        str: Path to processed audio file
    """
    # If no output path provided, create one
    if output_path is None:
        output_dir = os.path.dirname(audio_path)
        filename = os.path.basename(audio_path)
        name, ext = os.path.splitext(filename)
        output_path = os.path.join(output_dir, f"{name}_normalized{ext}")
    
    # Analyze audio
    metrics = analyze_audio(audio_path)
    
    # Check if analysis succeeded
    if metrics["rms_db"] is None:
        logger.warning(f"Could not analyze audio: {metrics.get('error', 'Unknown error')}. " 
                     f"Skipping gain control for {audio_path}")
        # Return original path if we can't process
        return audio_path
    
    # Calculate required gain
    current_rms_db = metrics["rms_db"]
    required_gain_db = target_rms_db - current_rms_db
    
    # Apply gain limiting
    if required_gain_db > max_gain_db:
        logger.warning(f"Required gain ({required_gain_db:.1f} dB) exceeds maximum ({max_gain_db} dB). "
                     f"Limiting gain to {max_gain_db} dB")
        required_gain_db = max_gain_db
    
    # Skip if no significant gain is needed
    if abs(required_gain_db) < 0.5:
        logger.info(f"Audio level already close to target ({current_rms_db:.1f} dB). Skipping gain control")
        return audio_path
    
    try:
        # Load audio
        y, sr = librosa.load(audio_path, sr=None)
        
        # Calculate gain factor
        gain_factor = 10 ** (required_gain_db / 20.0)
        
        # Apply gain
        y_normalized = y * gain_factor
        
        # Prevent clipping
        if np.max(np.abs(y_normalized)) > 0.999:
            # Find the scaling factor to prevent clipping
            clip_gain = 0.999 / np.max(np.abs(y_normalized))
            y_normalized = y_normalized * clip_gain
            logger.warning(f"Applied anti-clipping factor of {clip_gain:.4f}")
        
        # Save normalized audio
        sf.write(output_path, y_normalized, sr)
        logger.info(f"Applied gain of {required_gain_db:.1f} dB to {audio_path}")
        
        return output_path
    
    except Exception as e:
        logger.error(f"Error applying gain control: {str(e)}")
        return audio_path  # Return original path if processing fails

def detect_voice_activity(audio_path: str, threshold_db: float = -40.0, 
                         min_duration: float = 0.3) -> List[Tuple[float, float]]:
    """
    Simple Voice Activity Detection to find segments with speech
    
    Args:
        audio_path: Path to audio file
        threshold_db: Energy threshold in dB for speech detection
        min_duration: Minimum duration of speech segment in seconds
        
    Returns:
        list: List of (start_time, end_time) tuples for speech segments
    """
    try:
        # Load audio
        y, sr = librosa.load(audio_path, sr=None)
        
        # Convert threshold to amplitude
        threshold_amp = 10 ** (threshold_db / 20.0)
        
        # Calculate frame energy
        frame_length = int(0.025 * sr)  # 25ms frames
        hop_length = int(0.010 * sr)    # 10ms hop
        
        # Get energy of frames
        energy = librosa.feature.rms(y=y, frame_length=frame_length, 
                                    hop_length=hop_length)[0]
        
        # Find frames above threshold
        speech_frames = energy > threshold_amp
        
        # Convert frames to time segments
        segments = []
        in_speech = False
        start_frame = 0
        
        for i, is_speech in enumerate(speech_frames):
            if is_speech and not in_speech:
                # Speech start
                start_frame = i
                in_speech = True
            elif not is_speech and in_speech:
                # Speech end
                end_frame = i
                # Convert frames to time
                start_time = start_frame * hop_length / sr
                end_time = end_frame * hop_length / sr
                
                # Only keep segments longer than min_duration
                if end_time - start_time >= min_duration:
                    segments.append((start_time, end_time))
                
                in_speech = False
        
        # Handle if audio ends during speech
        if in_speech:
            end_frame = len(speech_frames)
            start_time = start_frame * hop_length / sr
            end_time = end_frame * hop_length / sr
            
            if end_time - start_time >= min_duration:
                segments.append((start_time, end_time))
        
        return segments
    
    except Exception as e:
        logger.error(f"Error in voice activity detection: {str(e)}")
        return []

def ensure_mono(audio_path: str, output_path: Optional[str] = None) -> str:
    """
    Ensure audio is mono by averaging channels if stereo
    
    Args:
        audio_path: Path to input audio file
        output_path: Path to output audio file (if None, creates one)
        
    Returns:
        str: Path to mono audio file
    """
    if output_path is None:
        output_dir = os.path.dirname(audio_path)
        filename = os.path.basename(audio_path)
        name, ext = os.path.splitext(filename)
        output_path = os.path.join(output_dir, f"{name}_mono{ext}")
    
    try:
        # Load audio
        y, sr = librosa.load(audio_path, sr=None, mono=False)
        
        # Check if already mono (returned shape will be (samples,) for mono)
        if len(y.shape) == 1:
            # Already mono, return original file
            return audio_path
        
        # Convert to mono
        y_mono = librosa.to_mono(y)
        
        # Save as mono
        sf.write(output_path, y_mono, sr)
        logger.info(f"Converted {audio_path} to mono: {output_path}")
        
        return output_path
    
    except Exception as e:
        logger.error(f"Error ensuring mono audio: {str(e)}")
        return audio_path  # Return original path if processing fails

def estimate_chunk_size(audio_path: str, available_memory_gb: float = 4.0) -> int:
    """
    Estimate optimal chunk size (in seconds) based on audio properties and available memory
    
    Args:
        audio_path: Path to audio file
        available_memory_gb: Available GPU memory in GB
        
    Returns:
        int: Recommended chunk size in seconds
    """
    try:
        # Get audio info
        y, sr = librosa.load(audio_path, sr=None, duration=10)  # Just load a small sample
        
        # Get file duration
        duration = librosa.get_duration(filename=audio_path)
        
        # Estimating memory requirements (this is a very rough estimate)
        # We assume ~50MB per second of audio for processing
        memory_per_second_mb = 50
        
        # Convert available memory to MB
        available_memory_mb = available_memory_gb * 1024
        
        # Calculate maximum chunk size
        max_chunk_size = int(available_memory_mb / memory_per_second_mb)
        
        # Limit to reasonable range
        if max_chunk_size < 10:
            logger.warning(f"Very limited memory ({available_memory_gb}GB). Using minimum chunk size of 10s")
            return 10
        
        if max_chunk_size > 300:
            # Cap at 5 minutes to avoid excessive memory usage
            return 300
        
        # Round to nearest 10 seconds for convenience
        return max_chunk_size - (max_chunk_size % 10)
    
    except Exception as e:
        logger.error(f"Error estimating chunk size: {str(e)}")
        # Return a reasonable default
        return 30

def clear_audio_cache():
    """
    Clear any cached audio data and free GPU memory
    """
    try:
        # Clear GPU cache if available
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            logger.debug("Cleared CUDA cache")
    except Exception as e:
        logger.error(f"Error clearing audio cache: {str(e)}")

def get_audio_quality_warnings(metrics: Dict) -> List[str]:
    """
    Generate warnings based on audio metrics
    
    Args:
        metrics: Audio metrics from analyze_audio()
        
    Returns:
        list: List of warning messages
    """
    warnings = []
    
    # Check levels
    if metrics.get("rms_db") is not None:
        if metrics["rms_db"] < -35:
            warnings.append(f"Audio level is very low ({metrics['rms_db']:.1f} dB). "
                          f"Consider using automatic gain control.")
            
        if metrics["peak_db"] > -1:
            warnings.append(f"Audio has peaks near clipping ({metrics['peak_db']:.1f} dB). "
                          f"Quality may be affected.")
    
    # Check SNR
    if metrics.get("snr") is not None:
        if metrics["snr"] < 15:
            warnings.append(f"Estimated signal-to-noise ratio is low ({metrics['snr']:.1f} dB). "
                          f"Transcription quality may be poor.")
    
    return warnings 