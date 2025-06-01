// AudioPipe Transcription Viewer - Main JavaScript
class AudioPipeViewer {
  constructor() {
    this.transcriptionData = null;
    this.filteredData = null;
    this.consolidatedData = null;
    this.currentView = 'timeline';
    this.searchQuery = '';
    this.speakerFilters = new Set();
    this.currentAudio = null;
    this.currentSegment = null;
    this.audioContext = null;
    this.audioBuffer = null;
    this.spectrogramData = null;
    this.consolidationThreshold = 1.0;

    this.init();
  }

  init() {
    this.setupEventListeners();
    this.setupTheme();
    this.setupDragAndDrop();
    this.showWelcomeState();
  }

  setupEventListeners() {
    // File loading
    document.getElementById('load-file-btn').addEventListener('click', () => {
      document.getElementById('file-input').click();
    });
    
    document.getElementById('file-input').addEventListener('change', (e) => {
      if (e.target.files.length > 0) {
        this.loadTranscriptionFile(e.target.files[0]);
      }
    });

    // Audio file loading
    document.getElementById('audio-file-input').addEventListener('change', (e) => {
      console.log('Audio file input changed, files:', e.target.files.length);
      if (e.target.files.length > 0) {
        console.log('Loading audio file:', e.target.files[0].name);
        this.loadAudioFile(e.target.files[0]);
      }
    });

    // Theme toggle
    document.getElementById('theme-toggle').addEventListener('click', () => {
      this.toggleTheme();
    });

    // Search functionality
    const searchInput = document.getElementById('search-input');
    searchInput.addEventListener('input', (e) => {
      this.handleSearch(e.target.value);
    });

    document.getElementById('clear-search').addEventListener('click', () => {
      this.clearSearch();
    });

    // View controls
    document.getElementById('view-timeline').addEventListener('click', () => {
      this.setView('timeline');
    });

    document.getElementById('view-speakers').addEventListener('click', () => {
      this.setView('speakers');
    });

    document.getElementById('view-visualization').addEventListener('click', () => {
      this.setView('visualization');
    });

    // Export functionality
    document.getElementById('export-text').addEventListener('click', () => {
      this.exportAsText();
    });

    document.getElementById('export-srt').addEventListener('click', () => {
      this.exportAsSRT();
    });

    document.getElementById('export-consolidated').addEventListener('click', () => {
      this.exportConsolidatedJSON();
    });

    // Visualization controls
    document.getElementById('consolidation-threshold')?.addEventListener('input', (e) => {
      this.consolidationThreshold = parseFloat(e.target.value);
      document.getElementById('threshold-value').textContent = `${this.consolidationThreshold}s`;
    });

    document.getElementById('apply-consolidation')?.addEventListener('click', () => {
      this.generateConsolidatedSegments();
    });

    document.getElementById('download-consolidated-segments')?.addEventListener('click', () => {
      this.downloadConsolidatedSegments();
    });

    // Spectrogram interaction
    document.getElementById('spectrogram-canvas')?.addEventListener('click', (e) => {
      this.handleSpectrogramClick(e);
    });

    // Spectrogram error click to load audio - use event delegation
    document.addEventListener('click', (e) => {
      if (e.target.closest('#spectrogram-error')) {
        console.log('Spectrogram error clicked, opening file picker');
        const audioFileInput = document.getElementById('audio-file-input');
        if (audioFileInput) {
          audioFileInput.click();
        } else {
          console.error('Audio file input not found');
        }
      }
    });

    // Audio player controls
    const audioElement = document.getElementById('audio-element');
    if (audioElement) {
      audioElement.addEventListener('timeupdate', () => {
        this.updateAudioProgress();
      });

      audioElement.addEventListener('loadedmetadata', () => {
        this.updateAudioDuration();
      });
    }

    document.getElementById('play-pause')?.addEventListener('click', () => {
      this.toggleAudioPlayback();
    });

    document.getElementById('audio-seek')?.addEventListener('input', (e) => {
      this.seekAudio(e.target.value);
    });

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
      this.handleKeyboardShortcuts(e);
    });

    // Modal close
    document.addEventListener('click', (e) => {
      if (e.target.classList.contains('modal-overlay')) {
        this.closeModal();
      }
    });
  }

  setupTheme() {
    const savedTheme = localStorage.getItem('audiopipe-theme') || 'light';
    this.setTheme(savedTheme);
  }

  setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    const themeIcon = document.querySelector('#theme-toggle i');
    if (themeIcon) {
      themeIcon.className = theme === 'dark' ? 'fas fa-sun' : 'fas fa-moon';
    }
    localStorage.setItem('audiopipe-theme', theme);
  }

  toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    this.setTheme(newTheme);
  }

  setupDragAndDrop() {
    const dropZone = document.getElementById('file-drop-zone');
    if (!dropZone) return;

    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
      dropZone.addEventListener(eventName, this.preventDefaults, false);
      document.body.addEventListener(eventName, this.preventDefaults, false);
    });

    ['dragenter', 'dragover'].forEach(eventName => {
      dropZone.addEventListener(eventName, () => {
        dropZone.classList.add('drag-over');
      }, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
      dropZone.addEventListener(eventName, () => {
        dropZone.classList.remove('drag-over');
      }, false);
    });

    dropZone.addEventListener('drop', (e) => {
      const files = e.dataTransfer.files;
      if (files.length > 0) {
        this.loadTranscriptionFile(files[0]);
      }
    }, false);
  }

  preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
  }

  showWelcomeState() {
    this.hideAllStates();
    document.getElementById('welcome-state').style.display = 'block';
  }

  showLoadingState() {
    this.hideAllStates();
    document.getElementById('loading-state').style.display = 'block';
  }

  showErrorState(message) {
    this.hideAllStates();
    const errorState = document.getElementById('error-state');
    const errorMessage = document.getElementById('error-message');
    if (errorMessage) {
      errorMessage.textContent = message;
    }
    errorState.style.display = 'block';
  }

  showTranscriptionContent() {
    this.hideAllStates();
    document.getElementById('transcription-content').style.display = 'block';
  }

  showNoResultsState() {
    this.hideAllStates();
    document.getElementById('no-results-state').style.display = 'block';
  }

  hideAllStates() {
    const states = [
      'welcome-state',
      'loading-state',
      'error-state',
      'transcription-content',
      'visualization-content',
      'no-results-state'
    ];

    states.forEach(stateId => {
      const element = document.getElementById(stateId);
      if (element) {
        element.style.display = 'none';
      }
    });
  }

  async loadTranscriptionFile(file) {
    if (!file.name.endsWith('.json')) {
      this.showErrorState('Please select a valid JSON file');
      return;
    }

    this.showLoadingState();

    try {
      const text = await this.readFileAsText(file);
      const data = JSON.parse(text);

      if (!this.validateTranscriptionData(data)) {
        throw new Error('Invalid transcription format');
      }

      this.transcriptionData = data;
      this.filteredData = data.segments;
      this.processTranscriptionData();
      this.renderTranscription();
      this.updateStatistics();
      this.setupSpeakerLegend();
      this.showTranscriptionContent();

      this.showToast('Transcription loaded successfully!', 'success');

    } catch (error) {
      console.error('Error loading transcription:', error);
      this.showErrorState(`Error loading file: ${error.message}`);
      this.showToast('Failed to load transcription file', 'error');
    }
  }

  async loadAudioFile(file) {
    console.log('loadAudioFile called with:', file.name, file.type);

    // Validate audio file type
    const validTypes = ['audio/mp3', 'audio/mpeg', 'audio/wav', 'audio/x-wav', 'audio/m4a', 'audio/flac', 'audio/ogg'];
    const isValidType = validTypes.some(type => file.type.startsWith(type)) ||
                       file.name.match(/\.(mp3|wav|m4a|flac|ogg)$/i);

    console.log('File type validation:', isValidType, 'File type:', file.type);

    if (!isValidType) {
      this.showToast('Please select a valid audio file (MP3, WAV, M4A, FLAC, OGG)', 'error');
      return;
    }

    try {
      // Show loading state
      this.showToast('Loading audio file...', 'info');
      console.log('Starting audio file loading process');

      // Create object URL for the audio file
      const audioUrl = URL.createObjectURL(file);
      console.log('Created object URL:', audioUrl);

      // Load audio into the audio player
      const audioElement = document.getElementById('audio-element');
      if (!audioElement) {
        throw new Error('Audio element not found');
      }

      console.log('Setting audio source');
      audioElement.src = audioUrl;

      // Show audio player
      const audioPlayer = document.getElementById('audio-player');
      if (audioPlayer) {
        audioPlayer.style.display = 'block';
        console.log('Audio player shown');
      }

      // Wait for audio to load
      console.log('Waiting for audio metadata to load');
      await new Promise((resolve, reject) => {
        const timeout = setTimeout(() => {
          reject(new Error('Audio loading timeout'));
        }, 10000); // 10 second timeout

        audioElement.addEventListener('loadedmetadata', () => {
          clearTimeout(timeout);
          console.log('Audio metadata loaded successfully');
          resolve();
        }, { once: true });

        audioElement.addEventListener('error', (e) => {
          clearTimeout(timeout);
          console.error('Audio loading error:', e);
          reject(new Error('Failed to load audio'));
        }, { once: true });
      });

      this.showToast(`Audio file loaded: ${file.name}`, 'success');
      console.log('Audio file loaded successfully');

      // If we're in visualization view, regenerate spectrogram
      if (this.currentView === 'visualization') {
        console.log('Regenerating spectrogram for visualization view');
        this.initializeSpectrogram();
      }

    } catch (error) {
      console.error('Error loading audio file:', error);
      this.showToast(`Failed to load audio file: ${error.message}`, 'error');
    }
  }

  readFileAsText(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = (e) => resolve(e.target.result);
      reader.onerror = (e) => reject(new Error('Failed to read file'));
      reader.readAsText(file);
    });
  }

  validateTranscriptionData(data) {
    if (!data || !Array.isArray(data.segments)) {
      return false;
    }

    // Check if segments have required fields
    return data.segments.every(segment => 
      typeof segment.text === 'string' &&
      typeof segment.start === 'number' &&
      typeof segment.end === 'number' &&
      typeof segment.speaker === 'string'
    );
  }

  processTranscriptionData() {
    // Sort segments by start time
    this.transcriptionData.segments.sort((a, b) => a.start - b.start);
    
    // Calculate additional metadata
    this.transcriptionData.segments.forEach((segment, index) => {
      segment.id = index;
      segment.duration = segment.end - segment.start;
      segment.wordCount = segment.text.trim().split(/\s+/).length;
    });
  }

  formatTime(seconds) {
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.floor(seconds % 60);
    return `${minutes.toString().padStart(2, '0')}:${remainingSeconds.toString().padStart(2, '0')}`;
  }

  formatDuration(seconds) {
    if (seconds < 60) {
      return `${seconds.toFixed(1)}s`;
    }
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.floor(seconds % 60);
    return `${minutes}m ${remainingSeconds}s`;
  }

  getSpeakerColor(speaker) {
    const colors = [
      'var(--speaker-1)', 'var(--speaker-2)', 'var(--speaker-3)', 'var(--speaker-4)',
      'var(--speaker-5)', 'var(--speaker-6)', 'var(--speaker-7)', 'var(--speaker-8)'
    ];
    
    const speakerIndex = parseInt(speaker.replace('SPEAKER_', '')) || 0;
    return colors[speakerIndex % colors.length];
  }

  highlightSearchText(text, query) {
    if (!query) return text;

    const regex = new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
    return text.replace(regex, '<mark>$1</mark>');
  }

  handleSearch(query) {
    this.searchQuery = query.toLowerCase().trim();

    const clearButton = document.getElementById('clear-search');
    if (this.searchQuery) {
      clearButton.style.display = 'block';
    } else {
      clearButton.style.display = 'none';
    }

    this.filterAndRenderTranscription();
  }

  clearSearch() {
    document.getElementById('search-input').value = '';
    this.searchQuery = '';
    document.getElementById('clear-search').style.display = 'none';
    this.filterAndRenderTranscription();
  }

  filterAndRenderTranscription() {
    if (!this.transcriptionData) return;

    let filtered = this.transcriptionData.segments;

    // Apply search filter
    if (this.searchQuery) {
      filtered = filtered.filter(segment =>
        segment.text.toLowerCase().includes(this.searchQuery) ||
        segment.speaker.toLowerCase().includes(this.searchQuery)
      );
    }

    // Apply speaker filters
    if (this.speakerFilters.size > 0) {
      filtered = filtered.filter(segment =>
        !this.speakerFilters.has(segment.speaker)
      );
    }

    this.filteredData = filtered;

    if (filtered.length === 0 && (this.searchQuery || this.speakerFilters.size > 0)) {
      this.showNoResultsState();
    } else {
      this.renderTranscription();
      this.showTranscriptionContent();
    }
  }

  setView(view) {
    this.currentView = view;

    // Update button states
    document.getElementById('view-timeline').classList.toggle('active', view === 'timeline');
    document.getElementById('view-speakers').classList.toggle('active', view === 'speakers');
    document.getElementById('view-visualization').classList.toggle('active', view === 'visualization');

    if (view === 'visualization') {
      this.showVisualizationContent();
    } else {
      this.renderTranscription();
    }
  }

  renderTranscription() {
    const container = document.getElementById('transcription-content');
    if (!container || !this.filteredData) return;

    if (this.currentView === 'timeline') {
      this.renderTimelineView(container);
    } else {
      this.renderSpeakerView(container);
    }
  }

  renderTimelineView(container) {
    const html = this.filteredData.map(segment => this.createSegmentHTML(segment)).join('');
    container.innerHTML = html;
    this.attachSegmentEventListeners();
  }

  renderSpeakerView(container) {
    const speakerGroups = this.groupSegmentsBySpeaker(this.filteredData);

    const html = Object.entries(speakerGroups).map(([speaker, segments]) => {
      const segmentCount = segments.length;
      const totalDuration = segments.reduce((sum, seg) => sum + seg.duration, 0);
      const wordCount = segments.reduce((sum, seg) => sum + seg.wordCount, 0);

      return `
        <div class="speaker-group">
          <div class="speaker-group-header">
            <div class="speaker-info">
              <div class="speaker-badge" style="background-color: ${this.getSpeakerColor(speaker)}"></div>
              <span class="speaker-group-title">${speaker}</span>
            </div>
            <div class="speaker-group-stats">
              ${segmentCount} segments • ${this.formatDuration(totalDuration)} • ${wordCount} words
            </div>
          </div>
          <div class="speaker-segments">
            ${segments.map(segment => this.createSegmentHTML(segment)).join('')}
          </div>
        </div>
      `;
    }).join('');

    container.innerHTML = html;
    this.attachSegmentEventListeners();
  }

  groupSegmentsBySpeaker(segments) {
    return segments.reduce((groups, segment) => {
      if (!groups[segment.speaker]) {
        groups[segment.speaker] = [];
      }
      groups[segment.speaker].push(segment);
      return groups;
    }, {});
  }

  createSegmentHTML(segment) {
    const highlightedText = this.highlightSearchText(segment.text, this.searchQuery);

    return `
      <div class="segment speaker-${segment.speaker}" data-segment-id="${segment.id}">
        <div class="segment-header">
          <div class="segment-info">
            <div class="segment-speaker">
              <div class="speaker-badge" style="background-color: ${this.getSpeakerColor(segment.speaker)}"></div>
              <span>${segment.speaker}</span>
            </div>
            <div class="segment-time">${this.formatTime(segment.start)} - ${this.formatTime(segment.end)}</div>
          </div>
          <div class="segment-duration">${this.formatDuration(segment.duration)}</div>
        </div>
        <div class="segment-text">${highlightedText}</div>
      </div>
    `;
  }

  attachSegmentEventListeners() {
    document.querySelectorAll('.segment').forEach(element => {
      element.addEventListener('click', (e) => {
        const segmentId = parseInt(e.currentTarget.dataset.segmentId);
        this.showSegmentDetails(segmentId);
      });
    });
  }

  showSegmentDetails(segmentId) {
    const segment = this.transcriptionData.segments.find(s => s.id === segmentId);
    if (!segment) return;

    const modal = document.getElementById('segment-modal');
    const detailsContainer = document.getElementById('segment-details');

    detailsContainer.innerHTML = `
      <div class="segment-detail-item">
        <span class="segment-detail-label">Speaker</span>
        <span class="segment-detail-value">${segment.speaker}</span>
      </div>
      <div class="segment-detail-item">
        <span class="segment-detail-label">Start Time</span>
        <span class="segment-detail-value">${this.formatTime(segment.start)}</span>
      </div>
      <div class="segment-detail-item">
        <span class="segment-detail-label">End Time</span>
        <span class="segment-detail-value">${this.formatTime(segment.end)}</span>
      </div>
      <div class="segment-detail-item">
        <span class="segment-detail-label">Duration</span>
        <span class="segment-detail-value">${this.formatDuration(segment.duration)}</span>
      </div>
      <div class="segment-detail-item">
        <span class="segment-detail-label">Word Count</span>
        <span class="segment-detail-value">${segment.wordCount}</span>
      </div>
      <div class="segment-detail-item">
        <span class="segment-detail-label">Text</span>
        <span class="segment-detail-value">${segment.text}</span>
      </div>
    `;

    modal.style.display = 'flex';
  }

  closeModal() {
    document.getElementById('segment-modal').style.display = 'none';
  }

  updateStatistics() {
    if (!this.transcriptionData) return;

    const segments = this.transcriptionData.segments;
    const speakers = [...new Set(segments.map(s => s.speaker))];
    const totalDuration = Math.max(...segments.map(s => s.end));
    const wordCount = segments.reduce((sum, s) => sum + s.wordCount, 0);

    document.getElementById('total-segments').textContent = segments.length;
    document.getElementById('total-speakers').textContent = speakers.length;
    document.getElementById('total-duration').textContent = this.formatTime(totalDuration);
    document.getElementById('word-count').textContent = wordCount.toLocaleString();
  }

  setupSpeakerLegend() {
    if (!this.transcriptionData) return;

    const speakers = [...new Set(this.transcriptionData.segments.map(s => s.speaker))];
    const speakerCounts = {};

    this.transcriptionData.segments.forEach(segment => {
      speakerCounts[segment.speaker] = (speakerCounts[segment.speaker] || 0) + 1;
    });

    const legendContainer = document.getElementById('speaker-legend');
    legendContainer.innerHTML = speakers.map(speaker => `
      <div class="speaker-item" data-speaker="${speaker}">
        <div class="speaker-info">
          <div class="speaker-badge" style="background-color: ${this.getSpeakerColor(speaker)}"></div>
          <span class="speaker-name">${speaker}</span>
        </div>
        <span class="speaker-count">${speakerCounts[speaker]}</span>
      </div>
    `).join('');

    // Add click handlers for speaker filtering
    legendContainer.querySelectorAll('.speaker-item').forEach(item => {
      item.addEventListener('click', (e) => {
        const speaker = e.currentTarget.dataset.speaker;
        this.toggleSpeakerFilter(speaker);
      });
    });
  }

  toggleSpeakerFilter(speaker) {
    if (this.speakerFilters.has(speaker)) {
      this.speakerFilters.delete(speaker);
    } else {
      this.speakerFilters.add(speaker);
    }

    // Update UI
    const speakerItem = document.querySelector(`[data-speaker="${speaker}"]`);
    if (speakerItem) {
      speakerItem.classList.toggle('filtered', this.speakerFilters.has(speaker));
    }

    this.filterAndRenderTranscription();
  }

  exportAsText() {
    if (!this.filteredData) {
      this.showToast('No transcription data to export', 'error');
      return;
    }

    const text = this.filteredData.map(segment => {
      const timeStamp = `[${this.formatTime(segment.start)} - ${this.formatTime(segment.end)}]`;
      return `${timeStamp} ${segment.speaker}: ${segment.text}`;
    }).join('\n\n');

    navigator.clipboard.writeText(text).then(() => {
      this.showToast('Transcription copied to clipboard!', 'success');
    }).catch(() => {
      this.showToast('Failed to copy to clipboard', 'error');
    });
  }

  exportAsSRT() {
    if (!this.filteredData) {
      this.showToast('No transcription data to export', 'error');
      return;
    }

    const srtContent = this.filteredData.map((segment, index) => {
      const startTime = this.formatSRTTime(segment.start);
      const endTime = this.formatSRTTime(segment.end);
      return `${index + 1}\n${startTime} --> ${endTime}\n${segment.speaker}: ${segment.text}\n`;
    }).join('\n');

    const blob = new Blob([srtContent], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'transcription.srt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    this.showToast('SRT file downloaded!', 'success');
  }

  formatSRTTime(seconds) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    const ms = Math.floor((seconds % 1) * 1000);

    return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')},${ms.toString().padStart(3, '0')}`;
  }

  toggleAudioPlayback() {
    const audio = document.getElementById('audio-element');
    const playPauseBtn = document.getElementById('play-pause');
    const icon = playPauseBtn.querySelector('i');

    if (audio.paused) {
      audio.play();
      icon.className = 'fas fa-pause';
    } else {
      audio.pause();
      icon.className = 'fas fa-play';
    }
  }

  updateAudioProgress() {
    const audio = document.getElementById('audio-element');
    const seekBar = document.getElementById('audio-seek');
    const currentTimeSpan = document.getElementById('current-time');

    if (audio.duration) {
      const progress = (audio.currentTime / audio.duration) * 100;
      seekBar.value = progress;
      currentTimeSpan.textContent = this.formatTime(audio.currentTime);

      // Highlight current segment
      this.highlightCurrentSegment(audio.currentTime);
    }
  }

  updateAudioDuration() {
    const audio = document.getElementById('audio-element');
    const totalTimeSpan = document.getElementById('total-time');

    if (audio.duration) {
      totalTimeSpan.textContent = this.formatTime(audio.duration);
    }
  }

  seekAudio(value) {
    const audio = document.getElementById('audio-element');
    if (audio.duration) {
      audio.currentTime = (value / 100) * audio.duration;
    }
  }

  highlightCurrentSegment(currentTime) {
    if (!this.transcriptionData) return;

    // Remove previous highlights
    document.querySelectorAll('.segment.current-playing').forEach(el => {
      el.classList.remove('current-playing');
    });

    // Find and highlight current segment
    const currentSegment = this.transcriptionData.segments.find(segment =>
      currentTime >= segment.start && currentTime <= segment.end
    );

    if (currentSegment) {
      const segmentElement = document.querySelector(`[data-segment-id="${currentSegment.id}"]`);
      if (segmentElement) {
        segmentElement.classList.add('current-playing');
        segmentElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }
  }

  handleKeyboardShortcuts(e) {
    // Space bar for play/pause
    if (e.code === 'Space' && e.target.tagName !== 'INPUT') {
      e.preventDefault();
      this.toggleAudioPlayback();
    }

    // Escape to close modal
    if (e.code === 'Escape') {
      this.closeModal();
    }

    // Ctrl/Cmd + F for search focus
    if ((e.ctrlKey || e.metaKey) && e.code === 'KeyF') {
      e.preventDefault();
      document.getElementById('search-input').focus();
    }
  }

  showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;

    const iconClass = type === 'success' ? 'fa-check-circle' :
                     type === 'error' ? 'fa-exclamation-circle' : 'fa-info-circle';

    toast.innerHTML = `
      <div class="toast-icon">
        <i class="fas ${iconClass}"></i>
      </div>
      <div class="toast-message">${message}</div>
      <button class="toast-close">
        <i class="fas fa-times"></i>
      </button>
    `;

    container.appendChild(toast);

    // Auto remove after 5 seconds
    setTimeout(() => {
      if (toast.parentNode) {
        toast.parentNode.removeChild(toast);
      }
    }, 5000);

    // Manual close
    toast.querySelector('.toast-close').addEventListener('click', () => {
      if (toast.parentNode) {
        toast.parentNode.removeChild(toast);
      }
    });
  }

  // ===== VISUALIZATION METHODS =====

  showVisualizationContent() {
    this.hideAllStates();
    document.getElementById('visualization-content').style.display = 'block';

    // Initialize visualizations
    this.renderSpeakerTimeline();
    this.generateConsolidatedSegments();
    this.initializeSpectrogram();
  }

  async initializeSpectrogram() {
    const canvas = document.getElementById('spectrogram-canvas');
    const loadingDiv = document.getElementById('spectrogram-loading');
    const errorDiv = document.getElementById('spectrogram-error');

    if (!canvas) return;

    // Show loading state initially
    loadingDiv.style.display = 'flex';
    errorDiv.style.display = 'none';
    canvas.style.display = 'none';

    try {
      // Try to get audio from the audio element
      const audioElement = document.getElementById('audio-element');
      if (!audioElement || !audioElement.src) {
        throw new Error('No audio file loaded');
      }

      // Initialize Web Audio API
      if (!this.audioContext) {
        this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
      }

      // Load and analyze audio
      await this.loadAudioForAnalysis(audioElement.src);
      this.generateSpectrogram();

      canvas.style.display = 'block';
      loadingDiv.style.display = 'none';

    } catch (error) {
      console.warn('Spectrogram generation failed:', error);
      loadingDiv.style.display = 'none';

      // Check if we have transcription data to show simplified waveform
      if (this.transcriptionData) {
        this.generateSimpleWaveform();
        canvas.style.display = 'block';
      } else {
        errorDiv.style.display = 'flex';
      }
    }
  }

  async loadAudioForAnalysis(audioSrc) {
    try {
      const response = await fetch(audioSrc);
      const arrayBuffer = await response.arrayBuffer();
      this.audioBuffer = await this.audioContext.decodeAudioData(arrayBuffer);
    } catch (error) {
      throw new Error('Failed to load audio for analysis');
    }
  }

  generateSpectrogram() {
    if (!this.audioBuffer) return;

    const canvas = document.getElementById('spectrogram-canvas');
    const ctx = canvas.getContext('2d');

    // Set canvas size
    const containerWidth = canvas.parentElement.clientWidth;
    const containerHeight = 200;
    canvas.width = containerWidth;
    canvas.height = containerHeight;
    canvas.style.width = containerWidth + 'px';
    canvas.style.height = containerHeight + 'px';

    const audioData = this.audioBuffer.getChannelData(0);
    const sampleRate = this.audioBuffer.sampleRate;
    const duration = this.audioBuffer.duration;

    // FFT parameters
    const fftSize = 2048;
    const hopSize = fftSize / 4;
    const numFrames = Math.floor((audioData.length - fftSize) / hopSize) + 1;
    const numBins = fftSize / 2;

    // Create spectrogram data
    const spectrogramData = new Array(numFrames);
    for (let frame = 0; frame < numFrames; frame++) {
      const startSample = frame * hopSize;
      const frameData = audioData.slice(startSample, startSample + fftSize);

      // Apply window function (Hann window)
      for (let i = 0; i < frameData.length; i++) {
        frameData[i] *= 0.5 * (1 - Math.cos(2 * Math.PI * i / (frameData.length - 1)));
      }

      // Compute FFT (simplified - using basic frequency analysis)
      const spectrum = this.computeSpectrum(frameData);
      spectrogramData[frame] = spectrum;
    }

    this.spectrogramData = spectrogramData;
    this.renderSpectrogramToCanvas(ctx, spectrogramData, containerWidth, containerHeight, duration);
  }

  computeSpectrum(frameData) {
    const spectrum = new Array(frameData.length / 2);

    // Simple magnitude spectrum calculation
    for (let k = 0; k < spectrum.length; k++) {
      let real = 0, imag = 0;

      for (let n = 0; n < frameData.length; n++) {
        const angle = -2 * Math.PI * k * n / frameData.length;
        real += frameData[n] * Math.cos(angle);
        imag += frameData[n] * Math.sin(angle);
      }

      spectrum[k] = Math.sqrt(real * real + imag * imag);
    }

    return spectrum;
  }

  renderSpectrogramToCanvas(ctx, spectrogramData, width, height, duration) {
    const imageData = ctx.createImageData(width, height);
    const data = imageData.data;

    for (let x = 0; x < width; x++) {
      const frameIndex = Math.floor((x / width) * spectrogramData.length);
      const spectrum = spectrogramData[frameIndex] || [];

      for (let y = 0; y < height; y++) {
        const freqIndex = Math.floor(((height - y) / height) * spectrum.length);
        const magnitude = spectrum[freqIndex] || 0;

        // Convert magnitude to color (log scale)
        const intensity = Math.min(255, Math.max(0, Math.log(magnitude + 1) * 50));

        const pixelIndex = (y * width + x) * 4;

        // Color mapping: blue to yellow to red
        if (intensity < 85) {
          data[pixelIndex] = 0;     // R
          data[pixelIndex + 1] = 0; // G
          data[pixelIndex + 2] = intensity * 3; // B
        } else if (intensity < 170) {
          data[pixelIndex] = (intensity - 85) * 3; // R
          data[pixelIndex + 1] = (intensity - 85) * 3; // G
          data[pixelIndex + 2] = 255 - (intensity - 85) * 3; // B
        } else {
          data[pixelIndex] = 255; // R
          data[pixelIndex + 1] = 255 - (intensity - 170) * 3; // G
          data[pixelIndex + 2] = 0; // B
        }

        data[pixelIndex + 3] = 255; // Alpha
      }
    }

    ctx.putImageData(imageData, 0, 0);

    // Add time markers
    this.addTimeMarkers(ctx, width, height, duration);
  }

  generateSimpleWaveform() {
    const canvas = document.getElementById('spectrogram-canvas');
    const ctx = canvas.getContext('2d');

    // Set canvas size
    const containerWidth = canvas.parentElement.clientWidth;
    const containerHeight = 200;
    canvas.width = containerWidth;
    canvas.height = containerHeight;

    // Clear canvas
    ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--bg-primary');
    ctx.fillRect(0, 0, containerWidth, containerHeight);

    // Draw placeholder waveform
    ctx.strokeStyle = getComputedStyle(document.documentElement).getPropertyValue('--accent-primary');
    ctx.lineWidth = 2;
    ctx.beginPath();

    for (let x = 0; x < containerWidth; x++) {
      const y = containerHeight / 2 + Math.sin(x * 0.02) * 30 * Math.random();
      if (x === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    }

    ctx.stroke();

    // Add duration from transcription data
    const duration = this.transcriptionData ?
      Math.max(...this.transcriptionData.segments.map(s => s.end)) : 0;
    this.addTimeMarkers(ctx, containerWidth, containerHeight, duration);

    canvas.style.display = 'block';
  }

  addTimeMarkers(ctx, width, height, duration) {
    if (!duration) return;

    ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--text-muted');
    ctx.font = '10px sans-serif';

    const numMarkers = Math.min(10, Math.floor(duration / 10));
    for (let i = 0; i <= numMarkers; i++) {
      const x = (i / numMarkers) * width;
      const time = (i / numMarkers) * duration;

      // Draw marker line
      ctx.strokeStyle = getComputedStyle(document.documentElement).getPropertyValue('--border-color');
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x, height - 20);
      ctx.lineTo(x, height);
      ctx.stroke();

      // Draw time label
      ctx.fillText(this.formatTime(time), x - 15, height - 5);
    }
  }

  handleSpectrogramClick(event) {
    if (!this.transcriptionData) return;

    const canvas = event.target;
    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const canvasWidth = canvas.width;

    // Calculate time position
    const duration = Math.max(...this.transcriptionData.segments.map(s => s.end));
    const clickTime = (x / canvasWidth) * duration;

    // Seek audio to this position
    const audioElement = document.getElementById('audio-element');
    if (audioElement && audioElement.duration) {
      audioElement.currentTime = clickTime;
      this.showToast(`Seeking to ${this.formatTime(clickTime)}`, 'info');
    }
  }

  renderSpeakerTimeline() {
    if (!this.transcriptionData) return;

    const container = document.getElementById('speaker-timeline');
    if (!container) return;

    const segments = this.transcriptionData.segments;
    const speakers = [...new Set(segments.map(s => s.speaker))].sort();
    const totalDuration = Math.max(...segments.map(s => s.end));

    container.innerHTML = speakers.map(speaker => {
      const speakerSegments = segments.filter(s => s.speaker === speaker);

      return `
        <div class="timeline-track">
          <div class="timeline-speaker-label">
            <div class="speaker-badge" style="background-color: ${this.getSpeakerColor(speaker)}"></div>
            <span>${speaker}</span>
          </div>
          <div class="timeline-track-bar" data-speaker="${speaker}">
            ${speakerSegments.map(segment => {
              const leftPercent = (segment.start / totalDuration) * 100;
              const widthPercent = ((segment.end - segment.start) / totalDuration) * 100;

              return `
                <div class="timeline-segment"
                     data-segment-id="${segment.id}"
                     style="left: ${leftPercent}%; width: ${widthPercent}%; background-color: ${this.getSpeakerColor(speaker)}"
                     title="${this.formatTime(segment.start)} - ${this.formatTime(segment.end)}: ${segment.text.substring(0, 100)}...">
                  ${widthPercent > 5 ? segment.id + 1 : ''}
                </div>
              `;
            }).join('')}
          </div>
        </div>
      `;
    }).join('');

    // Add event listeners for timeline interaction
    this.attachTimelineEventListeners();
  }

  attachTimelineEventListeners() {
    // Timeline segment clicks
    document.querySelectorAll('.timeline-segment').forEach(element => {
      element.addEventListener('click', (e) => {
        e.stopPropagation();
        const segmentId = parseInt(e.target.dataset.segmentId);
        this.jumpToSegment(segmentId);
      });

      // Hover tooltip
      element.addEventListener('mouseenter', (e) => {
        this.showTimelineTooltip(e);
      });

      element.addEventListener('mouseleave', () => {
        this.hideTimelineTooltip();
      });
    });

    // Timeline bar clicks (seek to position)
    document.querySelectorAll('.timeline-track-bar').forEach(bar => {
      bar.addEventListener('click', (e) => {
        if (e.target === bar) { // Only if clicking on the bar itself, not a segment
          this.handleTimelineBarClick(e);
        }
      });
    });
  }

  jumpToSegment(segmentId) {
    const segment = this.transcriptionData.segments.find(s => s.id === segmentId);
    if (!segment) return;

    // Seek audio to segment start
    const audioElement = document.getElementById('audio-element');
    if (audioElement && audioElement.duration) {
      audioElement.currentTime = segment.start;
    }

    // Switch to timeline view and highlight segment
    if (this.currentView !== 'timeline') {
      this.setView('timeline');
    }

    // Scroll to segment in transcript
    setTimeout(() => {
      const segmentElement = document.querySelector(`[data-segment-id="${segmentId}"]`);
      if (segmentElement) {
        segmentElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
        segmentElement.classList.add('highlighted');
        setTimeout(() => segmentElement.classList.remove('highlighted'), 2000);
      }
    }, 100);

    this.showToast(`Jumped to ${segment.speaker}: ${segment.text.substring(0, 50)}...`, 'info');
  }

  handleTimelineBarClick(event) {
    if (!this.transcriptionData) return;

    const bar = event.currentTarget;
    const rect = bar.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const barWidth = rect.width;

    const totalDuration = Math.max(...this.transcriptionData.segments.map(s => s.end));
    const clickTime = (x / barWidth) * totalDuration;

    // Seek audio to this position
    const audioElement = document.getElementById('audio-element');
    if (audioElement && audioElement.duration) {
      audioElement.currentTime = clickTime;
      this.showToast(`Seeking to ${this.formatTime(clickTime)}`, 'info');
    }
  }

  showTimelineTooltip(event) {
    const segmentId = parseInt(event.target.dataset.segmentId);
    const segment = this.transcriptionData.segments.find(s => s.id === segmentId);
    if (!segment) return;

    const tooltip = document.createElement('div');
    tooltip.className = 'timeline-tooltip';
    tooltip.innerHTML = `
      <strong>${segment.speaker}</strong><br>
      ${this.formatTime(segment.start)} - ${this.formatTime(segment.end)}<br>
      ${segment.text.substring(0, 100)}${segment.text.length > 100 ? '...' : ''}
    `;

    document.body.appendChild(tooltip);

    const rect = event.target.getBoundingClientRect();
    tooltip.style.left = rect.left + 'px';
    tooltip.style.top = (rect.top - tooltip.offsetHeight - 10) + 'px';

    this.currentTooltip = tooltip;
  }

  hideTimelineTooltip() {
    if (this.currentTooltip) {
      document.body.removeChild(this.currentTooltip);
      this.currentTooltip = null;
    }
  }

  generateConsolidatedSegments() {
    if (!this.transcriptionData) return;

    const segments = [...this.transcriptionData.segments].sort((a, b) => a.start - b.start);
    const consolidated = [];

    let currentGroup = null;

    for (const segment of segments) {
      if (!currentGroup ||
          currentGroup.speaker !== segment.speaker ||
          (segment.start - currentGroup.end) > this.consolidationThreshold) {

        // Start new group
        if (currentGroup) {
          consolidated.push(currentGroup);
        }

        currentGroup = {
          speaker: segment.speaker,
          start: segment.start,
          end: segment.end,
          text: segment.text,
          segments: [segment],
          wordCount: segment.wordCount
        };
      } else {
        // Extend current group
        currentGroup.end = segment.end;
        currentGroup.text += ' ' + segment.text;
        currentGroup.segments.push(segment);
        currentGroup.wordCount += segment.wordCount;
      }
    }

    // Add final group
    if (currentGroup) {
      consolidated.push(currentGroup);
    }

    this.consolidatedData = consolidated;
    this.renderConsolidatedSegments();
  }

  renderConsolidatedSegments() {
    const container = document.getElementById('consolidated-segments');
    if (!container || !this.consolidatedData) return;

    container.innerHTML = this.consolidatedData.map((group, index) => {
      const duration = group.end - group.start;
      const segmentCount = group.segments.length;

      return `
        <div class="consolidated-segment" data-group-id="${index}">
          <div class="consolidated-header">
            <div class="consolidated-speaker">
              <div class="speaker-badge" style="background-color: ${this.getSpeakerColor(group.speaker)}"></div>
              <span>${group.speaker}</span>
            </div>
            <div class="consolidated-stats">
              <span>${this.formatTime(group.start)} - ${this.formatTime(group.end)}</span>
              <span>${this.formatDuration(duration)}</span>
              <span>${segmentCount} segments</span>
              <span>${group.wordCount} words</span>
            </div>
          </div>
          <div class="consolidated-text">${group.text}</div>
          <div class="consolidated-segments-list">
            Original segments: ${group.segments.map(s => `#${s.id + 1}`).join(', ')}
          </div>
        </div>
      `;
    }).join('');

    // Add click handlers
    container.querySelectorAll('.consolidated-segment').forEach(element => {
      element.addEventListener('click', (e) => {
        const groupId = parseInt(e.currentTarget.dataset.groupId);
        const group = this.consolidatedData[groupId];
        if (group) {
          this.jumpToSegment(group.segments[0].id);
        }
      });
    });
  }

  exportConsolidatedJSON() {
    if (!this.consolidatedData) {
      this.showToast('No consolidated data available. Please generate consolidated segments first.', 'error');
      return;
    }

    const exportData = {
      metadata: {
        originalSegments: this.transcriptionData.segments.length,
        consolidatedSegments: this.consolidatedData.length,
        consolidationThreshold: this.consolidationThreshold,
        totalDuration: Math.max(...this.transcriptionData.segments.map(s => s.end)),
        generatedAt: new Date().toISOString()
      },
      consolidatedSegments: this.consolidatedData.map(group => ({
        speaker: group.speaker,
        start: group.start,
        end: group.end,
        duration: group.end - group.start,
        text: group.text,
        wordCount: group.wordCount,
        segmentCount: group.segments.length,
        originalSegmentIds: group.segments.map(s => s.id)
      }))
    };

    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'consolidated_transcription.json';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    this.showToast('Consolidated JSON downloaded!', 'success');
  }

  downloadConsolidatedSegments() {
    if (!this.consolidatedData) {
      this.showToast('No consolidated data available. Please generate consolidated segments first.', 'error');
      return;
    }

    // Create simplified export format focused on segment data
    const exportData = this.consolidatedData.map(group => ({
      text: group.text,
      start: group.start,
      end: group.end,
      speaker: group.speaker,
      duration: group.end - group.start,
      segmentCount: group.segments.length,
      originalSegmentIds: group.segments.map(s => s.id)
    }));

    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `consolidated_segments_${this.consolidationThreshold}s.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    this.showToast(`Consolidated segments downloaded! (${this.consolidatedData.length} segments, ${this.consolidationThreshold}s threshold)`, 'success');
  }
}

// Global functions for HTML onclick handlers
function resetToWelcome() {
  if (window.audioPipeViewer) {
    window.audioPipeViewer.showWelcomeState();
  }
}

function clearSearch() {
  if (window.audioPipeViewer) {
    window.audioPipeViewer.clearSearch();
  }
}

function closeModal() {
  if (window.audioPipeViewer) {
    window.audioPipeViewer.closeModal();
  }
}

// Initialize the application when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
  window.audioPipeViewer = new AudioPipeViewer();
});
