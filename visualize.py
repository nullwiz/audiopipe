#!/usr/bin/env python3
"""
Visualization utilities for AudioPipe

This module provides visualization tools for audio, diarization, and transcription results.
"""

import os
import json
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import librosa
import librosa.display
import soundfile as sf
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
import argparse
import colorsys
import time

def create_color_palette(n_colors: int) -> List[str]:
    """
    Create a visually distinct color palette
    
    Args:
        n_colors: Number of colors to generate
        
    Returns:
        list: List of hex color codes
    """
    colors = []
    for i in range(n_colors):
        # Use golden ratio to get well-distributed hues
        hue = i * 0.618033988749895 % 1
        # High saturation, medium brightness
        saturation = 0.7
        value = 0.9
        # Convert to RGB and then to hex
        r, g, b = colorsys.hsv_to_rgb(hue, saturation, value)
        colors.append(f'#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}')
    return colors

def plot_waveform(audio_path: str, output_path: Optional[str] = None) -> str:
    """
    Plot audio waveform
    
    Args:
        audio_path: Path to audio file
        output_path: Path to save the plot image (if None, auto-generated)
        
    Returns:
        str: Path to saved plot image
    """
    if output_path is None:
        output_dir = os.path.dirname(audio_path)
        filename = os.path.basename(audio_path)
        name, ext = os.path.splitext(filename)
        output_path = os.path.join(output_dir, f"{name}_waveform.png")
    
    # Load audio
    y, sr = librosa.load(audio_path, sr=None)
    
    # Create plot
    plt.figure(figsize=(12, 4))
    librosa.display.waveshow(y, sr=sr, alpha=0.8)
    plt.title(f"Waveform - {os.path.basename(audio_path)}")
    plt.xlabel("Time (s)")
    plt.ylabel("Amplitude")
    plt.tight_layout()
    
    # Save plot
    plt.savefig(output_path, dpi=150)
    plt.close()
    
    return output_path

def plot_diarization(diarized_json_path: str, audio_path: Optional[str] = None, 
                    output_path: Optional[str] = None) -> str:
    """
    Plot speaker diarization results
    
    Args:
        diarized_json_path: Path to diarization JSON file
        audio_path: Optional path to audio file for waveform background
        output_path: Path to save the plot image (if None, auto-generated)
        
    Returns:
        str: Path to saved plot image
    """
    if output_path is None:
        output_dir = os.path.dirname(diarized_json_path)
        filename = os.path.basename(diarized_json_path)
        name, ext = os.path.splitext(filename)
        output_path = os.path.join(output_dir, f"{name}_visualization.png")
    
    # Load diarization results
    with open(diarized_json_path, 'r') as f:
        diarization = json.load(f)
    
    # Extract segments
    segments = diarization.get('segments', [])
    speakers = diarization.get('speakers', [])
    
    if not segments:
        print(f"No segments found in {diarized_json_path}")
        return None
    
    # Get time range
    min_time = min(segment['start'] for segment in segments)
    max_time = max(segment['end'] for segment in segments)
    duration = max_time - min_time
    
    # Create plot
    fig, axs = plt.subplots(figsize=(12, 6), nrows=2, gridspec_kw={'height_ratios': [1, 3]})
    
    # Plot waveform if audio path provided
    if audio_path and os.path.exists(audio_path):
        y, sr = librosa.load(audio_path, sr=None)
        librosa.display.waveshow(y, sr=sr, ax=axs[0], alpha=0.8)
        axs[0].set_xlim(min_time, max_time)
        axs[0].set_title("Audio Waveform")
    else:
        axs[0].set_visible(False)
        fig.set_size_inches(12, 4)
    
    # Create color palette
    colors = create_color_palette(len(speakers))
    color_map = {speaker: color for speaker, color in zip(speakers, colors)}
    
    # Plot diarization segments
    axs[1].set_ylim(0, len(speakers) + 1)
    axs[1].set_xlim(min_time, max_time)
    axs[1].set_xlabel("Time (s)")
    axs[1].set_ylabel("Speaker")
    axs[1].set_title("Speaker Diarization")
    
    # Add speaker labels
    axs[1].set_yticks(range(1, len(speakers) + 1))
    axs[1].set_yticklabels(speakers)
    
    # Plot segments
    speaker_y_pos = {speaker: i+1 for i, speaker in enumerate(speakers)}
    
    for segment in segments:
        speaker = segment['speaker']
        start = segment['start']
        end = segment['end']
        y_pos = speaker_y_pos[speaker]
        
        # Draw rectangle for segment
        rect = patches.Rectangle(
            (start, y_pos - 0.4), 
            end - start, 
            0.8, 
            linewidth=1, 
            edgecolor='black', 
            facecolor=color_map[speaker],
            alpha=0.7
        )
        axs[1].add_patch(rect)
    
    # Add grid
    axs[1].grid(True, axis='x', alpha=0.3)
    
    # Adjust layout
    plt.tight_layout()
    
    # Save plot
    plt.savefig(output_path, dpi=150)
    plt.close()
    
    return output_path

def plot_transcript(transcript_json_path: str, output_path: Optional[str] = None, 
                   consolidated: bool = True, highlight_keywords: Optional[List[str]] = None) -> str:
    """
    Plot transcript with speaker timeline
    
    Args:
        transcript_json_path: Path to transcript JSON file
        output_path: Path to save the plot image (if None, auto-generated)
        consolidated: Whether the transcript is consolidated or raw
        highlight_keywords: List of keywords to highlight in transcript
        
    Returns:
        str: Path to saved plot image
    """
    if output_path is None:
        output_dir = os.path.dirname(transcript_json_path)
        filename = os.path.basename(transcript_json_path)
        name, ext = os.path.splitext(filename)
        output_path = os.path.join(output_dir, f"{name}_visualization.png")
    
    # Load transcript
    with open(transcript_json_path, 'r') as f:
        transcript = json.load(f)
    
    # Extract segments
    segments = transcript.get('segments', [])
    speakers = transcript.get('speakers', [])
    
    if not segments:
        print(f"No segments found in {transcript_json_path}")
        return None
    
    # Get time range
    min_time = min(segment['start'] for segment in segments)
    max_time = max(segment['end'] for segment in segments)
    duration = max_time - min_time
    
    # Create color palette
    colors = create_color_palette(len(speakers))
    color_map = {speaker: color for speaker, color in zip(speakers, colors)}
    
    # Calculate figure size - make it more compact
    fig_width = min(14, max(10, duration / 10))  # Adjust width based on duration
    fig_height = min(20, max(6, len(segments) * 0.2))  # More compact height
    
    # Create plot
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    
    # Set title based on file type
    title = "Consolidated Transcript" if consolidated else "Detailed Transcript"
    ax.set_title(title)
    
    # Plot timeline
    ax.set_xlim(min_time, max_time)
    ax.set_xlabel("Time (s)")
    ax.set_yticks([])  # Hide y-axis ticks
    
    # Add time markers
    time_interval = max(1, int(duration / 20))  # At most 20 time markers
    time_marks = np.arange(int(min_time), int(max_time) + 1, time_interval)
    for t in time_marks:
        ax.axvline(x=t, color='gray', linestyle='--', alpha=0.3)
    
    # Plot segments with text more compactly
    y_pos = fig_height - 1  # Start closer to the top
    segment_spacing = 0.7    # Reduce spacing between segments
    
    for i, segment in enumerate(segments):
        speaker = segment['speaker']
        start = segment['start']
        end = segment['end']
        text = segment.get('text', '')
        
        # Draw compact rectangle for segment
        rect = patches.Rectangle(
            (start, y_pos - 0.25), 
            end - start, 
            0.5, 
            linewidth=1, 
            edgecolor='black', 
            facecolor=color_map[speaker],
            alpha=0.7
        )
        ax.add_patch(rect)
        
        # Add speaker label
        ax.text(start - 0.01, y_pos, f"{speaker}", 
               ha='right', va='center', fontsize=8, 
               fontweight='bold', color=color_map[speaker])
        
        # Add time label - made smaller
        time_label = f"[{start:.1f}s - {end:.1f}s]"
        ax.text(start + (end - start)/2, y_pos + 0.3, time_label, 
               ha='center', va='center', fontsize=7, color='gray')
        
        # Format text with wrapping to fit in figure
        wrapped_text = text
        if len(text) > 80:  # For long text, wrap it
            words = text.split()
            wrapped_text = ""
            line = ""
            for word in words:
                if len(line + " " + word) > 80:
                    wrapped_text += line + "\n"
                    line = word
                else:
                    line = line + " " + word if line else word
            wrapped_text += line
        
        # Add text, potentially with highlighting
        if highlight_keywords and any(keyword.lower() in text.lower() for keyword in highlight_keywords):
            ax.text(start + 0.1, y_pos - 0.5, wrapped_text, 
                   ha='left', va='top', fontsize=9, wrap=True,
                   bbox=dict(facecolor='lightyellow', alpha=0.5, pad=2))
            
            # Draw star marker
            ax.plot(start, y_pos, marker='*', markersize=8, color='red')
        else:
            ax.text(start + 0.1, y_pos - 0.5, wrapped_text, 
                   ha='left', va='top', fontsize=9, wrap=True)
        
        y_pos -= segment_spacing  # More compact spacing
    
    # Adjust layout and ensure text fits
    plt.tight_layout()
    
    # Save plot with high DPI for better text rendering
    plt.savefig(output_path, dpi=200, bbox_inches='tight')
    plt.close()
    
    return output_path

def generate_html_report(transcript_path: str, audio_path: Optional[str] = None, 
                        diarized_json_path: Optional[str] = None,
                        output_path: Optional[str] = None) -> str:
    """
    Generate interactive HTML report with transcript, audio playback and visualizations
    
    Args:
        transcript_path: Path to transcript JSON file
        audio_path: Optional path to original audio file
        diarized_json_path: Optional path to diarization JSON file
        output_path: Path to save HTML file (if None, auto-generated)
        
    Returns:
        str: Path to saved HTML file
    """
    if output_path is None:
        output_dir = os.path.dirname(transcript_path)
        filename = os.path.basename(transcript_path)
        name, ext = os.path.splitext(filename)
        output_path = os.path.join(output_dir, f"{name}_report.html")
    
    # Load transcript
    with open(transcript_path, 'r') as f:
        transcript = json.load(f)
    
    # Extract segments and speakers
    segments = transcript.get('segments', [])
    speakers = transcript.get('speakers', [])
    
    if not segments:
        print(f"No segments found in {transcript_path}")
        return None
    
    # Create color palette
    colors = create_color_palette(len(speakers))
    color_map = {speaker: color for speaker, color in zip(speakers, colors)}
    
    # Generate speaker color styles
    speaker_styles = ""
    for speaker, color in color_map.items():
        speaker_styles += f".{speaker.replace('_', '-')} {{ background-color: {color}; color: white; }}\n"
    
    # Convert audio path to relative if provided
    audio_element = ""
    if audio_path and os.path.exists(audio_path):
        # Get relative path to audio file
        rel_audio_path = os.path.relpath(audio_path, os.path.dirname(output_path))
        audio_element = f"""
        <div class="card audio-player">
            <div class="card-header">
                <h5>Audio Player</h5>
            </div>
            <div class="card-body">
                <audio controls style="width:100%">
                    <source src="{rel_audio_path}" type="audio/wav">
                    Your browser does not support the audio element.
                </audio>
            </div>
        </div>
        """
    
    # Generate summary stats
    total_duration = max(segment['end'] for segment in segments) - min(segment['start'] for segment in segments)
    total_words = sum(len(segment.get('text', '').split()) for segment in segments)
    
    stats_element = f"""
    <div class="card stats-card">
        <div class="card-header">
            <h5>Transcript Stats</h5>
        </div>
        <div class="card-body">
            <div class="row">
                <div class="col-md-3">
                    <div class="stat-item">
                        <div class="stat-value">{len(speakers)}</div>
                        <div class="stat-label">Speakers</div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="stat-item">
                        <div class="stat-value">{len(segments)}</div>
                        <div class="stat-label">Segments</div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="stat-item">
                        <div class="stat-value">{int(total_duration)}s</div>
                        <div class="stat-label">Duration</div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="stat-item">
                        <div class="stat-value">{total_words}</div>
                        <div class="stat-label">Words</div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    """
    
    # Prepare timeline data with proper escaping for JavaScript
    timeline_data = []
    for segment in segments:
        speaker = segment['speaker']
        start = segment['start']
        end = segment['end']
        text = segment.get('text', '').replace('\\', '\\\\').replace('"', '\\"')
        
        timeline_data.append({
            'speaker': speaker,
            'start': start,
            'end': end,
            'text': text
        })
    
    # Script with proper JavaScript formatting
    js_script = """
    <script>
        // Timeline data
        const segments = TIMELINE_DATA_PLACEHOLDER;
        
        // Find total duration
        const maxTime = Math.max(...segments.map(s => s.end));
        
        // Set up timeline
        const timelineRuler = document.getElementById('timeline-ruler');
        const timelineContent = document.getElementById('timeline-content');
        const transcriptContent = document.getElementById('transcript-content');
        const searchInput = document.getElementById('searchInput');
        
        // Add time markers
        const interval = Math.max(1, Math.ceil(maxTime / 30)); // At most 30 markers
        for (let i = 0; i <= maxTime; i += interval) {
            const marker = document.createElement('div');
            marker.className = 'timeline-marker';
            marker.style.left = `${(i / maxTime) * 100}%`;
            
            const label = document.createElement('div');
            label.className = 'timeline-label';
            label.textContent = `${i}s`;
            label.style.left = `${(i / maxTime) * 100}%`;
            
            timelineRuler.appendChild(marker);
            timelineRuler.appendChild(label);
        }
        
        // Add segments to timeline
        segments.forEach((segment, index) => {
            const segmentEl = document.createElement('div');
            segmentEl.className = `segment ${segment.speaker.replace('_', '-')}`;
            segmentEl.style.left = `${(segment.start / maxTime) * 100}%`;
            segmentEl.style.width = `${((segment.end - segment.start) / maxTime) * 100}%`;
            segmentEl.textContent = segment.text.substring(0, 20) + (segment.text.length > 20 ? '...' : '');
            segmentEl.dataset.index = index;
            segmentEl.title = segment.text;
            
            segmentEl.addEventListener('click', () => {
                // Scroll to transcript segment
                const transcriptSegment = document.getElementById(`transcript-${index}`);
                transcriptSegment.scrollIntoView({ behavior: 'smooth' });
                
                // Highlight for a moment
                transcriptSegment.style.backgroundColor = '#e2e3fe';
                setTimeout(() => {
                    transcriptSegment.style.backgroundColor = '';
                }, 2000);
                
                // Play audio from this point if available
                const audio = document.querySelector('audio');
                if (audio) {
                    audio.currentTime = segment.start;
                    audio.play();
                }
            });
            
            timelineContent.appendChild(segmentEl);
        });
        
        // Add segments to transcript
        segments.forEach((segment, index) => {
            const segmentEl = document.createElement('div');
            segmentEl.className = 'transcript-segment';
            segmentEl.id = `transcript-${index}`;
            
            const header = document.createElement('div');
            header.className = 'transcript-header';
            
            const speaker = document.createElement('span');
            speaker.className = `speaker-label ${segment.speaker.replace('_', '-')}`;
            speaker.textContent = segment.speaker;
            
            const time = document.createElement('span');
            time.className = 'timestamp';
            time.textContent = `[${segment.start.toFixed(1)}s - ${segment.end.toFixed(1)}s]`;
            
            header.appendChild(speaker);
            header.appendChild(time);
            
            const content = document.createElement('div');
            content.className = 'transcript-content';
            content.textContent = segment.text;
            content.dataset.originalText = segment.text;
            
            segmentEl.appendChild(header);
            segmentEl.appendChild(content);
            
            segmentEl.addEventListener('click', () => {
                // Play audio from this point if available
                const audio = document.querySelector('audio');
                if (audio) {
                    audio.currentTime = segment.start;
                    audio.play();
                }
            });
            
            transcriptContent.appendChild(segmentEl);
        });
        
        // Search functionality
        searchInput.addEventListener('input', () => {
            const searchTerm = searchInput.value.toLowerCase().trim();
            
            // Reset all highlights first
            document.querySelectorAll('.transcript-content').forEach(el => {
                el.innerHTML = el.dataset.originalText;
            });
            
            if (searchTerm.length < 2) return; // Only search for terms with at least 2 characters
            
            let foundAny = false;
            
            document.querySelectorAll('.transcript-segment').forEach(segment => {
                const contentEl = segment.querySelector('.transcript-content');
                const text = contentEl.dataset.originalText.toLowerCase();
                
                if (text.includes(searchTerm)) {
                    // Highlight the matching text
                    const regex = new RegExp(`(${escapeRegExp(searchTerm)})`, 'gi');
                    contentEl.innerHTML = contentEl.dataset.originalText.replace(
                        regex, '<span class="search-highlight">$1</span>'
                    );
                    segment.style.display = 'block';
                    foundAny = true;
                    
                    // If it's the first match, scroll to it
                    if (!foundAny) {
                        segment.scrollIntoView({ behavior: 'smooth' });
                    }
                } else {
                    segment.style.display = 'block'; // Always show all segments for now
                }
            });
        });
        
        // Helper function to escape special characters in search term for regex
        function escapeRegExp(string) {
            return string.replace(/[.*+?^${}()|[\\]]/g, '\\$&');
        }
    </script>
    """
    
    # Insert the timeline data into the JavaScript
    js_script = js_script.replace("TIMELINE_DATA_PLACEHOLDER", json.dumps(timeline_data))
    
    # Generate HTML content with Bootstrap
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AudioPipe Transcript Report</title>
    <!-- Bootstrap CSS -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        :root {{
            --primary-color: #3498db;
            --secondary-color: #2c3e50;
            --light-bg: #f8f9fa;
            --dark-bg: #343a40;
            --success-color: #2ecc71;
        }}
        
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            background-color: #f5f5f5;
            padding-top: 20px;
            padding-bottom: 40px;
        }}
        
        .container {{
            max-width: 1200px;
            background-color: white;
            border-radius: 8px;
            box-shadow: 0 0 15px rgba(0,0,0,0.1);
            padding: 20px;
        }}
        
        .title-section {{
            border-bottom: 1px solid #eee;
            margin-bottom: 20px;
            padding-bottom: 10px;
        }}
        
        h1, h2, h3, h4, h5 {{
            color: var(--secondary-color);
        }}
        
        .card {{
            margin-bottom: 20px;
            border: none;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        
        .card-header {{
            background-color: white;
            border-bottom: 2px solid #f0f0f0;
            font-weight: bold;
        }}
        
        .audio-player {{
            background-color: var(--light-bg);
        }}
        
        .stats-card .stat-item {{
            text-align: center;
            padding: 10px;
        }}
        
        .stats-card .stat-value {{
            font-size: 2rem;
            font-weight: bold;
            color: var(--primary-color);
        }}
        
        .stats-card .stat-label {{
            text-transform: uppercase;
            font-size: 0.8rem;
            color: #6c757d;
        }}
        
        .timeline-container {{
            position: relative;
            height: 150px;
            background-color: #f0f0f0;
            margin: 20px 0;
            overflow-x: auto;
            border-radius: 5px;
        }}
        
        .timeline-ruler {{
            height: 20px;
            position: relative;
            background-color: #e0e0e0;
        }}
        
        .timeline-content {{
            position: relative;
            height: 130px;
        }}
        
        .timeline-marker {{
            position: absolute;
            top: 0;
            height: 100%;
            width: 1px;
            background-color: #888;
        }}
        
        .timeline-label {{
            position: absolute;
            top: 2px;
            transform: translateX(-50%);
            font-size: 10px;
            color: #555;
        }}
        
        .segment {{
            position: absolute;
            height: 30px;
            border-radius: 4px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.2);
            top: 40px;
            opacity: 0.9;
            cursor: pointer;
            overflow: hidden;
            white-space: nowrap;
            text-overflow: ellipsis;
            font-size: 12px;
            padding: 2px 5px;
            box-sizing: border-box;
            transition: all 0.2s ease;
            color: white;
            text-shadow: 0 0 2px rgba(0,0,0,0.5);
        }}
        
        .segment:hover {{
            height: 60px;
            top: 30px;
            z-index: 10;
            opacity: 1;
            box-shadow: 0 3px 8px rgba(0,0,0,0.3);
        }}
        
        .transcript-segment {{
            margin-bottom: 15px;
            border-radius: 5px;
            background-color: white;
            cursor: pointer;
            transition: all 0.2s;
            border: 1px solid #eee;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        }}
        
        .transcript-segment:hover {{
            box-shadow: 0 3px 10px rgba(0,0,0,0.1);
            transform: translateY(-2px);
        }}
        
        .transcript-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 15px;
            border-bottom: 1px solid #f0f0f0;
        }}
        
        .transcript-content {{
            padding: 10px 15px;
            line-height: 1.5;
        }}
        
        .speaker-label {{
            display: inline-block;
            padding: 3px 10px;
            border-radius: 20px;
            color: white;
            font-weight: bold;
        }}
        
        .timestamp {{
            color: #6c757d;
            font-size: 0.9em;
        }}
        
        .search-box {{
            margin: 20px 0;
        }}
        
        .search-highlight {{
            background-color: yellow;
            font-weight: bold;
        }}
        
        {speaker_styles}
    </style>
</head>
<body>
    <div class="container">
        <div class="title-section">
            <h1 class="text-center">AudioPipe Transcript Report</h1>
            <p class="text-center text-muted">Generated on {time.strftime("%Y-%m-%d %H:%M:%S")}</p>
        </div>
        
        <div class="row">
            <div class="col-md-12">
                {audio_element}
                
                {stats_element}
                
                <div class="card">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <h5 class="mb-0">Interactive Timeline</h5>
                        <small class="text-muted">Click on segments to navigate</small>
                    </div>
                    <div class="card-body p-0">
                        <div class="timeline-container">
                            <div class="timeline-ruler" id="timeline-ruler"></div>
                            <div class="timeline-content" id="timeline-content"></div>
                        </div>
                    </div>
                </div>
                
                <div class="card">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <h5 class="mb-0">Transcript</h5>
                        <div class="search-box">
                            <input type="text" id="searchInput" class="form-control form-control-sm" placeholder="Search transcript...">
                        </div>
                    </div>
                    <div class="card-body">
                        <div id="transcript-content"></div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <!-- Bootstrap Bundle with Popper -->
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/js/bootstrap.bundle.min.js"></script>
    
    {js_script}
</body>
</html>
"""
    
    # Write HTML to file
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"HTML report saved to: {output_path}")
    return output_path

def main():
    """Command-line interface for visualization utilities"""
    parser = argparse.ArgumentParser(description="AudioPipe Visualization Tools")
    
    # Main subcommand parser
    subparsers = parser.add_subparsers(dest="command", help="Visualization command")
    
    # Waveform command
    waveform_parser = subparsers.add_parser("waveform", help="Plot audio waveform")
    waveform_parser.add_argument("audio_path", help="Path to audio file")
    waveform_parser.add_argument("--output", "-o", help="Output path for plot")
    
    # Diarization command
    diar_parser = subparsers.add_parser("diarization", help="Plot speaker diarization")
    diar_parser.add_argument("json_path", help="Path to diarization JSON file")
    diar_parser.add_argument("--audio", "-a", help="Path to audio file for waveform background")
    diar_parser.add_argument("--output", "-o", help="Output path for plot")
    
    # Transcript command
    transcript_parser = subparsers.add_parser("transcript", help="Plot transcript timeline")
    transcript_parser.add_argument("json_path", help="Path to transcript JSON file")
    transcript_parser.add_argument("--output", "-o", help="Output path for plot")
    transcript_parser.add_argument("--consolidated", "-c", action="store_true", 
                                 help="Input is consolidated transcript")
    transcript_parser.add_argument("--highlight", "-hl", nargs="+", 
                                 help="Keywords to highlight in transcript")
    
    # HTML report command
    report_parser = subparsers.add_parser("report", help="Generate HTML report")
    report_parser.add_argument("transcript_path", help="Path to transcript JSON file")
    report_parser.add_argument("--audio", "-a", help="Path to audio file")
    report_parser.add_argument("--diarization", "-d", help="Path to diarization JSON file")
    report_parser.add_argument("--output", "-o", help="Output path for HTML file")
    
    # Parse arguments
    args = parser.parse_args()
    
    # Handle commands
    if args.command == "waveform":
        output_path = plot_waveform(args.audio_path, args.output)
        print(f"Waveform plot saved to: {output_path}")
    
    elif args.command == "diarization":
        output_path = plot_diarization(args.json_path, args.audio, args.output)
        print(f"Diarization plot saved to: {output_path}")
    
    elif args.command == "transcript":
        output_path = plot_transcript(args.json_path, args.output, 
                                     args.consolidated, args.highlight)
        print(f"Transcript plot saved to: {output_path}")
    
    elif args.command == "report":
        output_path = generate_html_report(args.transcript_path, args.audio, 
                                          args.diarization, args.output)
        print(f"HTML report saved to: {output_path}")
    
    else:
        parser.print_help()

if __name__ == "__main__":
    main() 