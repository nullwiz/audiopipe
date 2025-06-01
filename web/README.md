# AudioPipe Web Frontend

A modern, responsive web interface for viewing AudioPipe transcription results. This standalone application provides an intuitive way to explore, search, and analyze transcribed audio content with speaker attribution.

## Features

### Core Functionality
- **File Loading**: Drag-and-drop or file picker for JSON transcription files
- **Chronological Display**: Timeline view showing segments in order with timestamps
- **Speaker Attribution**: Color-coded speaker identification and filtering
- **Real-time Search**: Text search with highlighting across all segments
- **Responsive Design**: Works seamlessly on desktop, tablet, and mobile devices

### Advanced Features
- **Dark/Light Theme**: Toggle between themes with persistent preference
- **Speaker Filtering**: Click speakers in the legend to hide/show their segments
- **Multiple Views**: Timeline, Speaker, and Visualization views
- **Export Options**: Copy as text, download as SRT, or export consolidated JSON
- **Audio Playback**: Sync audio playback with transcript highlighting (if audio file available)
- **Segment Details**: Click segments for detailed timing and metadata
- **Keyboard Shortcuts**: Space for play/pause, Escape to close modals, Ctrl+F for search

### Visualization Features
- **Audio Spectrogram**: Real-time frequency analysis visualization with click-to-seek
- **Audio File Loading**: Click spectrogram area to load local audio files for visualization
- **Speaker Timeline**: Horizontal timeline tracks showing speaker segments proportionally
- **Consolidated Segments**: Greedy algorithm to merge consecutive speaker segments
- **Interactive Timeline**: Click timeline segments to jump to transcript locations
- **Visual Debugging**: Hover tooltips with segment details and timing information
- **Simplified Export**: Download consolidated segments as clean JSON format

### Statistics Panel
- Total segments count
- Number of unique speakers
- Total duration
- Word count
- Speaker-specific statistics

## File Structure

```
web/
├── index.html              # Main HTML structure
├── styles.css              # Complete CSS styling with theme support
├── script.js               # Full JavaScript functionality
├── sample_transcription.json # Example transcription file for testing
└── README.md               # This documentation
```

## Usage

### Getting Started

1. **Open the Application**
   ```bash
   # Simply open index.html in any modern web browser
   open web/index.html
   # or
   python -m http.server 8000  # For local development server
   ```

2. **Load Transcription Data**
   - Drag and drop your `final_transcription.json` file onto the drop zone
   - Or click "Browse Files" to select the file
   - Use the provided `sample_transcription.json` for testing

### Expected JSON Format

The application expects transcription files in this format:

```json
{
  "metadata": {
    "audioFile": "audio.wav",
    "totalDuration": 120.5,
    "sampleRate": 44100,
    "channels": 1
  },
  "segments": [
    {
      "text": "Transcribed text content",
      "start": 0.0,
      "end": 5.2,
      "speaker": "SPEAKER_00"
    },
    {
      "text": "Next segment text",
      "start": 5.2,
      "end": 10.1,
      "speaker": "SPEAKER_01"
    }
  ]
}
```

**Required Fields:**
- `segments`: Array of transcription segments
- `segments[].text`: Transcribed text content
- `segments[].start`: Start time in seconds
- `segments[].end`: End time in seconds
- `segments[].speaker`: Speaker identifier (e.g., "SPEAKER_00")

**Optional Fields:**
- `metadata`: Additional audio file information
- `metadata.audioFile`: Original audio filename
- `metadata.totalDuration`: Total audio duration
- `metadata.sampleRate`: Audio sample rate
- `metadata.channels`: Number of audio channels

### Consolidated Segments Format

The sidebar's consolidated export generates this enhanced format with metadata:

```json
{
  "metadata": {
    "originalSegments": 15,
    "consolidatedSegments": 8,
    "consolidationThreshold": 1.0,
    "totalDuration": 133.5,
    "generatedAt": "2024-01-15T10:30:00.000Z"
  },
  "consolidatedSegments": [
    {
      "speaker": "SPEAKER_00",
      "start": 0.0,
      "end": 25.1,
      "duration": 25.1,
      "text": "Combined text from multiple consecutive segments...",
      "wordCount": 45,
      "segmentCount": 3,
      "originalSegmentIds": [0, 2, 5]
    }
  ]
}
```

### Simplified Consolidated Export

The visualization tab's download button generates a cleaner format focused on segment data:

```json
[
  {
    "text": "Combined text from multiple consecutive segments...",
    "start": 0.0,
    "end": 25.1,
    "speaker": "SPEAKER_00",
    "duration": 25.1,
    "segmentCount": 3,
    "originalSegmentIds": [0, 2, 5]
  },
  {
    "text": "Another consolidated segment...",
    "start": 30.5,
    "end": 45.8,
    "speaker": "SPEAKER_01",
    "duration": 15.3,
    "segmentCount": 2,
    "originalSegmentIds": [3, 4]
  }
]
```

**File naming**: `consolidated_segments_[threshold]s.json` (e.g., `consolidated_segments_1.0s.json`)

### Interface Overview

#### Header
- **AudioPipe Logo**: Application branding
- **Theme Toggle**: Switch between dark and light themes
- **Load Transcription**: Button to load new transcription files

#### Sidebar (Desktop)
- **Statistics Panel**: Overview metrics
- **Speaker Legend**: Color-coded speaker list with filtering
- **Export Options**: Text copy and SRT download

#### Main Content Area
- **Search Bar**: Real-time text search with highlighting
- **View Controls**: Toggle between Timeline, Speaker, and Visualization views
- **Audio Player**: Playback controls (when audio is available)
- **Transcription Display**: Main content area with segments

#### Visualization View
- **Audio Spectrogram**: Frequency analysis visualization spanning full audio duration
- **Audio Loading**: Click spectrogram area to load local audio files (MP3, WAV, M4A, FLAC, OGG)
- **Speaker Timeline**: Horizontal tracks showing speaker segments proportionally
- **Consolidated Segments**: Configurable threshold for merging consecutive segments
- **Interactive Controls**: Click-to-seek, hover tooltips, and segment navigation
- **Export Controls**: Apply consolidation and download simplified JSON format

#### Segment Display
Each segment shows:
- Speaker identification with color badge
- Start and end timestamps
- Duration
- Transcribed text with search highlighting
- Click for detailed modal view

### Keyboard Shortcuts

- **Space**: Play/pause audio (when available)
- **Escape**: Close open modals
- **Ctrl/Cmd + F**: Focus search input

### Browser Compatibility

- **Chrome/Edge**: Full support (recommended)
- **Firefox**: Full support
- **Safari**: Full support
- **Mobile Browsers**: Responsive design works on all modern mobile browsers

### Local Development

For local development with CORS support:

```bash
# Python 3
python -m http.server 8000

# Python 2
python -m SimpleHTTPServer 8000

# Node.js
npx serve .

# PHP
php -S localhost:8000
```

Then open `http://localhost:8000` in your browser.

## Technical Details

### Architecture
- **Pure HTML/CSS/JavaScript**: No frameworks or dependencies
- **CSS Variables**: Theme support with custom properties
- **ES6 Classes**: Modern JavaScript with clean architecture
- **Responsive Grid/Flexbox**: Mobile-first responsive design
- **Local Storage**: Theme preference persistence

### Performance
- **Efficient Rendering**: Virtual scrolling for large transcriptions
- **Debounced Search**: Optimized real-time search
- **Lazy Loading**: Progressive content loading
- **Memory Management**: Proper cleanup and event handling

### Accessibility
- **Keyboard Navigation**: Full keyboard accessibility
- **Screen Reader Support**: Semantic HTML and ARIA labels
- **High Contrast**: Theme support for accessibility
- **Focus Management**: Proper focus handling for modals

## Integration with AudioPipe

This web frontend is designed to work with AudioPipe's simple architecture:

1. **AudioPipe Pipeline**: Processes audio files and generates `output/final_transcription.json`
2. **Web Frontend**: Loads and visualizes the transcription results
3. **Standalone Operation**: No server required, works entirely client-side

### Workflow

#### Standard Workflow
```
Audio File → AudioPipe Pipeline → final_transcription.json → Web Frontend → Interactive Visualization
```

#### Audio Loading for Visualization
```
1. Load transcription JSON file
2. Switch to Visualization view
3. Click spectrogram area to load audio file
4. Audio syncs with transcript timeline
5. Interactive spectrogram and timeline visualization
```

**Supported Audio Formats**: MP3, WAV, M4A, FLAC, OGG

## Customization

### Themes
Modify CSS variables in `styles.css` to customize colors:

```css
:root {
  --accent-primary: #your-color;
  --speaker-1: #your-speaker-color;
  /* ... */
}
```

### Speaker Colors
The application supports up to 8 distinct speaker colors. Add more in the CSS variables section if needed.

### Branding
Update the logo and branding in the header section of `index.html`.

## Troubleshooting

### Common Issues

1. **File Won't Load**
   - Ensure JSON format matches expected structure
   - Check browser console for error messages
   - Verify file is valid JSON

2. **CORS Errors**
   - Use a local development server instead of file:// protocol
   - Some browsers restrict local file access

3. **Audio Not Playing**
   - Ensure audio file is in supported format (MP3, WAV, OGG)
   - Check browser audio permissions
   - Audio file must be accessible via HTTP/HTTPS

4. **Audio Loading for Spectrogram**
   - Click the spectrogram error area to load audio files
   - Supported formats: MP3, WAV, M4A, FLAC, OGG
   - Check browser console for detailed loading progress
   - Ensure file is not corrupted or too large

5. **Mobile Display Issues**
   - Ensure viewport meta tag is present
   - Test responsive breakpoints
   - Check touch event handling

6. **Layout Issues**
   - Interface uses full viewport width at all zoom levels
   - Test at 100%, 125%, 150%, 180% zoom for consistency
   - Report any horizontal scrolling issues

### Browser Console
Open browser developer tools (F12) to see detailed error messages and debug information. Audio loading includes comprehensive console logging for troubleshooting.

## License

This web frontend is part of the AudioPipe project and follows the same licensing terms.
