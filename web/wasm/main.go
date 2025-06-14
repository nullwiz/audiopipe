package main

import (
	"encoding/json"
	"fmt"
	"log"
	"sort"
	"strconv"
	"strings"
	"syscall/js"
	"time"
)

type AudioPipeApp struct {
	transcriptionData    *TranscriptionData
	consolidatedData     []ConsolidatedSegment
	audioData            *AudioData
	currentView          string
	searchQuery          string
	isDarkTheme          bool
	statistics           Statistics
	speakerColors        map[string]string
	isPlaying            bool
	currentTime          float64
	consolidationThreshold float64
	isConsolidated       bool
}

type TranscriptionData struct {
	Segments []Segment `json:"segments"`
}

type Segment struct {
	Speaker string  `json:"speaker"`
	Start   float64 `json:"start"`
	End     float64 `json:"end"`
	Text    string  `json:"text"`
}

type ConsolidatedSegment struct {
	Speaker   string    `json:"speaker"`
	Start     float64   `json:"start"`
	End       float64   `json:"end"`
	Text      string    `json:"text"`
	Segments  []Segment `json:"segments"`
	WordCount int       `json:"wordCount"`
}

type Statistics struct {
	SegmentCount  int     `json:"segmentCount"`
	SpeakerCount  int     `json:"speakerCount"`
	TotalDuration float64 `json:"totalDuration"`
	WordCount     int     `json:"wordCount"`
}

type AudioData struct {
	FileName   string   `json:"fileName"`
	Duration   float64  `json:"duration"`
	WaveSurfer js.Value `json:"-"`
	FileBlob   js.Value `json:"-"`
}

var app *AudioPipeApp

func main() {
	app = &AudioPipeApp{
		currentView:            "timeline",
		isDarkTheme:            false,
		speakerColors:          make(map[string]string),
		consolidationThreshold: 10.0,
		isConsolidated:         false,
	}

	app.initializeTheme()

	js.Global().Set("loadTranscriptionFile", js.FuncOf(app.loadTranscriptionFile))
	js.Global().Set("loadAudioFile", js.FuncOf(app.loadAudioFile))
	js.Global().Set("togglePlayback", js.FuncOf(app.togglePlayback))
	js.Global().Set("seekAudio", js.FuncOf(app.seekAudio))
	js.Global().Set("seekToTime", js.FuncOf(app.seekToTime))
	js.Global().Set("toggleTheme", js.FuncOf(app.toggleTheme))
	js.Global().Set("handleSearch", js.FuncOf(app.handleSearch))
	js.Global().Set("clearSearch", js.FuncOf(app.clearSearch))
	js.Global().Set("exportAsText", js.FuncOf(app.exportAsText))
	js.Global().Set("exportAsSRT", js.FuncOf(app.exportAsSRT))
	js.Global().Set("downloadConsolidated", js.FuncOf(app.downloadConsolidated))
	js.Global().Set("showTimelineView", js.FuncOf(app.showTimelineView))
	js.Global().Set("showVisualizationView", js.FuncOf(app.showVisualizationView))
	js.Global().Set("consolidateSegments", js.FuncOf(app.consolidateSegments))
	js.Global().Set("updateConsolidationThreshold", js.FuncOf(app.updateConsolidationThreshold))
	js.Global().Set("applyConsolidation", js.FuncOf(app.applyConsolidation))

	app.setupEventListeners()
	app.showUploadState()
	app.showToast("AudioPipe WASM Ready", "success")

	select {}
}

func (app *AudioPipeApp) initializeTheme() {
	localStorage := js.Global().Get("localStorage")
	savedTheme := localStorage.Call("getItem", "theme")

	if !savedTheme.IsNull() && savedTheme.String() == "dark" {
		app.isDarkTheme = true
		js.Global().Get("document").Get("body").Get("classList").Call("add", "dark-theme")
	}

	app.updateThemeIcon()
}

func (app *AudioPipeApp) updateThemeIcon() {
	themeIcon := js.Global().Get("document").Call("querySelector", "#theme-toggle i")
	if !themeIcon.IsNull() {
		if app.isDarkTheme {
			themeIcon.Set("className", "fas fa-sun")
		} else {
			themeIcon.Set("className", "fas fa-moon")
		}
	}
}

func (app *AudioPipeApp) setupEventListeners() {
	document := js.Global().Get("document")

	fileInput := document.Call("getElementById", "file-input")
	if !fileInput.IsNull() {
		fileInput.Call("addEventListener", "change", js.FuncOf(app.handleFileInput))
	}

	audioInput := document.Call("getElementById", "audio-input")
	if !audioInput.IsNull() {
		audioInput.Call("addEventListener", "change", js.FuncOf(app.handleAudioInput))
	}

	loadFileBtn := document.Call("getElementById", "load-file-btn")
	if !loadFileBtn.IsNull() {
		loadFileBtn.Call("addEventListener", "click", js.FuncOf(func(this js.Value, args []js.Value) interface{} {
			document.Call("getElementById", "file-input").Call("click")
			return nil
		}))
	}

	loadAudioBtn := document.Call("getElementById", "load-audio-btn")
	if !loadAudioBtn.IsNull() {
		loadAudioBtn.Call("addEventListener", "click", js.FuncOf(func(this js.Value, args []js.Value) interface{} {
			document.Call("getElementById", "audio-input").Call("click")
			return nil
		}))
	}

	themeToggle := document.Call("getElementById", "theme-toggle")
	if !themeToggle.IsNull() {
		themeToggle.Call("addEventListener", "click", js.FuncOf(app.toggleTheme))
	}

	searchInput := document.Call("getElementById", "search-input")
	if !searchInput.IsNull() {
		searchInput.Call("addEventListener", "input", js.FuncOf(app.handleSearchInput))
	}

	clearSearchBtn := document.Call("getElementById", "clear-search")
	if !clearSearchBtn.IsNull() {
		clearSearchBtn.Call("addEventListener", "click", js.FuncOf(app.clearSearch))
	}

	app.setupExportButtons()
	app.setupViewButtons()
	app.setupConsolidationControls()
	app.setupDragAndDrop()
}

func (app *AudioPipeApp) setupExportButtons() {
	document := js.Global().Get("document")

	exportText := document.Call("getElementById", "export-text")
	if !exportText.IsNull() {
		exportText.Call("addEventListener", "click", js.FuncOf(app.exportAsText))
	}

	exportSRT := document.Call("getElementById", "export-srt")
	if !exportSRT.IsNull() {
		exportSRT.Call("addEventListener", "click", js.FuncOf(app.exportAsSRT))
	}

	exportConsolidated := document.Call("getElementById", "export-consolidated")
	if !exportConsolidated.IsNull() {
		exportConsolidated.Call("addEventListener", "click", js.FuncOf(app.downloadConsolidated))
	}
}

func (app *AudioPipeApp) setupViewButtons() {
	document := js.Global().Get("document")

	viewTimeline := document.Call("getElementById", "view-timeline")
	if !viewTimeline.IsNull() {
		viewTimeline.Call("addEventListener", "click", js.FuncOf(app.showTimelineView))
	}

	viewSpeakers := document.Call("getElementById", "view-speakers")
	if !viewSpeakers.IsNull() {
		viewSpeakers.Call("addEventListener", "click", js.FuncOf(app.showTimelineView)) // Same as timeline for now
	}

	viewVisualization := document.Call("getElementById", "view-visualization")
	if !viewVisualization.IsNull() {
		viewVisualization.Call("addEventListener", "click", js.FuncOf(app.showVisualizationView))
	}
}

func (app *AudioPipeApp) setupConsolidationControls() {
	document := js.Global().Get("document")

	thresholdSlider := document.Call("getElementById", "consolidation-threshold")
	if !thresholdSlider.IsNull() {
		thresholdSlider.Call("addEventListener", "input", js.FuncOf(app.updateConsolidationThreshold))
	}

	applyBtn := document.Call("getElementById", "apply-consolidation")
	if !applyBtn.IsNull() {
		applyBtn.Call("addEventListener", "click", js.FuncOf(app.applyConsolidation))
	}
}

func (app *AudioPipeApp) setupDragAndDrop() {
	document := js.Global().Get("document")
	dropZone := document.Call("getElementById", "file-drop-zone")

	if dropZone.IsNull() {
		log.Printf("Drop zone element not found")
		return
	}

	log.Printf("Setting up drag and drop functionality")

	events := []string{"dragenter", "dragover", "dragleave", "drop"}
	for _, event := range events {
		dropZone.Call("addEventListener", event, js.FuncOf(app.preventDefaults))
		document.Get("body").Call("addEventListener", event, js.FuncOf(app.preventDefaults))
	}

	dragEvents := []string{"dragenter", "dragover"}
	for _, event := range dragEvents {
		dropZone.Call("addEventListener", event, js.FuncOf(func(this js.Value, args []js.Value) interface{} {
			log.Printf("Drag event: %s", event)
			dropZone.Get("classList").Call("add", "drag-over")
			return nil
		}))
	}

	leaveEvents := []string{"dragleave", "drop"}
	for _, event := range leaveEvents {
		dropZone.Call("addEventListener", event, js.FuncOf(func(this js.Value, args []js.Value) interface{} {
			log.Printf("Drag leave/drop event: %s", event)
			dropZone.Get("classList").Call("remove", "drag-over")
			return nil
		}))
	}

	dropZone.Call("addEventListener", "drop", js.FuncOf(app.handleFileDrop))

	log.Printf("Drag and drop setup completed")
}

func (app *AudioPipeApp) preventDefaults(this js.Value, args []js.Value) interface{} {
	if len(args) > 0 {
		args[0].Call("preventDefault")
		args[0].Call("stopPropagation")
	}
	return nil
}

func (app *AudioPipeApp) handleFileInput(this js.Value, args []js.Value) interface{} {
	if len(args) > 0 {
		files := args[0].Get("target").Get("files")
		if files.Length() > 0 {
			app.processFile(files.Index(0))
		}
	}
	return nil
}

func (app *AudioPipeApp) handleFileDrop(this js.Value, args []js.Value) interface{} {
	log.Printf("File drop event triggered")

	if len(args) == 0 {
		log.Printf("No arguments in drop event")
		return nil
	}

	event := args[0]
	dataTransfer := event.Get("dataTransfer")
	if dataTransfer.IsUndefined() {
		log.Printf("No dataTransfer in drop event")
		return nil
	}

	files := dataTransfer.Get("files")
	if files.IsUndefined() {
		log.Printf("No files in dataTransfer")
		return nil
	}

	fileCount := files.Length()
	log.Printf("Dropped %d files", fileCount)

	if fileCount > 0 {
		file := files.Index(0)
		fileName := file.Get("name").String()
		fileType := file.Get("type").String()
		log.Printf("Processing dropped file: %s (type: %s)", fileName, fileType)
		app.processFile(file)
	} else {
		log.Printf("No files to process")
	}

	return nil
}

func (app *AudioPipeApp) loadTranscriptionFile(this js.Value, args []js.Value) interface{} {
	if len(args) > 0 {
		app.processFile(args[0])
	}
	return nil
}

func (app *AudioPipeApp) processFile(file js.Value) {
	fileName := file.Get("name").String()
	fileType := file.Get("type").String()

	if strings.HasPrefix(fileType, "audio/") {
		app.processAudioFile(file)
		return
	}

	app.showLoadingState("Processing " + fileName + "...")

	reader := js.Global().Get("FileReader").New()

	reader.Set("onload", js.FuncOf(func(this js.Value, args []js.Value) interface{} {
		result := args[0].Get("target").Get("result").String()
		app.parseTranscriptionData(result, fileName)
		return nil
	}))

	reader.Set("onerror", js.FuncOf(func(this js.Value, args []js.Value) interface{} {
		app.showToast("Failed to read file", "error")
		app.showUploadState()
		return nil
	}))

	reader.Call("readAsText", file)
}

func (app *AudioPipeApp) parseTranscriptionData(jsonData, fileName string) {
	var transcriptionData TranscriptionData

	err := json.Unmarshal([]byte(jsonData), &transcriptionData)
	if err != nil {
		app.showToast("Invalid JSON format", "error")
		app.showUploadState()
		return
	}

	if len(transcriptionData.Segments) == 0 {
		app.showToast("No segments found in transcription", "warning")
		app.showUploadState()
		return
	}

	app.transcriptionData = &transcriptionData

	app.calculateStatistics()
	app.generateSpeakerColors()
	app.updateStatistics()
	app.showToast(fmt.Sprintf("Loaded %s with %d segments", fileName, len(transcriptionData.Segments)), "success")

	app.showTimelineView(js.Value{}, []js.Value{})
}

func (app *AudioPipeApp) calculateStatistics() {
	if app.transcriptionData == nil {
		return
	}

	segments := app.transcriptionData.Segments
	speakerMap := make(map[string]bool)
	totalWords := 0
	maxEnd := 0.0

	for _, segment := range segments {
		speakerMap[segment.Speaker] = true
		words := len(strings.Fields(segment.Text))
		totalWords += words

		if segment.End > maxEnd {
			maxEnd = segment.End
		}
	}

	app.statistics = Statistics{
		SegmentCount:  len(segments),
		SpeakerCount:  len(speakerMap),
		TotalDuration: maxEnd,
		WordCount:     totalWords,
	}
}

func (app *AudioPipeApp) generateSpeakerColors() {
	if app.transcriptionData == nil {
		return
	}

	colors := []string{
		"#ef4444", "#f97316", "#eab308", "#22c55e",
		"#06b6d4", "#3b82f6", "#8b5cf6", "#ec4899",
		"#f59e0b", "#10b981", "#6366f1", "#d946ef",
	}

	speakers := app.getUniqueSpeakers()
	for i, speaker := range speakers {
		app.speakerColors[speaker] = colors[i%len(colors)]
	}
}

func (app *AudioPipeApp) getUniqueSpeakers() []string {
	if app.transcriptionData == nil {
		return []string{}
	}

	speakerMap := make(map[string]bool)
	for _, segment := range app.transcriptionData.Segments {
		speakerMap[segment.Speaker] = true
	}

	speakers := make([]string, 0, len(speakerMap))
	for speaker := range speakerMap {
		speakers = append(speakers, speaker)
	}

	sort.Strings(speakers)
	return speakers
}

func (app *AudioPipeApp) hideAllStates() {
	document := js.Global().Get("document")
	sections := []string{
		"welcome-state", "loading-state", "error-state", "no-results-state",
		"transcription-content", "visualization-content",
	}

	for _, section := range sections {
		element := document.Call("getElementById", section)
		if !element.IsNull() {
			element.Get("style").Set("display", "none")
		}
	}
}

func (app *AudioPipeApp) showUploadState() {
	app.hideAllStates()
	document := js.Global().Get("document")
	welcomeState := document.Call("getElementById", "welcome-state")
	if !welcomeState.IsNull() {
		welcomeState.Get("style").Set("display", "block")
	}
}

func (app *AudioPipeApp) showLoadingState(message string) {
	app.hideAllStates()
	document := js.Global().Get("document")
	loadingState := document.Call("getElementById", "loading-state")
	if !loadingState.IsNull() {
		loadingState.Get("style").Set("display", "block")

		loadingMessage := document.Call("getElementById", "loading-message")
		if !loadingMessage.IsNull() {
			loadingMessage.Set("textContent", message)
		}
	}
}

func (app *AudioPipeApp) showTimelineView(this js.Value, args []js.Value) interface{} {
	app.currentView = "timeline"
	app.hideAllStates()

	if app.transcriptionData != nil {
		app.showTimelineContent()
		app.setActiveView("view-timeline")
	} else {
		app.showUploadState()
	}
	return nil
}

func (app *AudioPipeApp) showVisualizationView(this js.Value, args []js.Value) interface{} {
	app.currentView = "visualization"
	app.hideAllStates()

	if app.transcriptionData != nil {
		app.showVisualizationContent()
		app.setActiveView("view-visualization")
	} else {
		app.showUploadState()
	}
	return nil
}

func (app *AudioPipeApp) showTimelineContent() {
	document := js.Global().Get("document")
	transcriptionContent := document.Call("getElementById", "transcription-content")
	if !transcriptionContent.IsNull() {
		transcriptionContent.Get("style").Set("display", "block")
		app.renderTimeline()
	}
}

func (app *AudioPipeApp) showVisualizationContent() {
	document := js.Global().Get("document")
	visualizationContent := document.Call("getElementById", "visualization-content")
	if !visualizationContent.IsNull() {
		visualizationContent.Get("style").Set("display", "block")
		app.renderSpeakerTimelines()
	}
}

func (app *AudioPipeApp) setActiveView(activeButtonId string) {
	document := js.Global().Get("document")
	viewButtons := []string{"view-timeline", "view-speakers", "view-visualization"}

	for _, buttonId := range viewButtons {
		button := document.Call("getElementById", buttonId)
		if !button.IsNull() {
			if buttonId == activeButtonId {
				button.Get("classList").Call("add", "active")
			} else {
				button.Get("classList").Call("remove", "active")
			}
		}
	}
}

func (app *AudioPipeApp) updateStatistics() {
	document := js.Global().Get("document")

	segmentCount := document.Call("getElementById", "segment-count")
	if !segmentCount.IsNull() {
		segmentCount.Set("textContent", strconv.Itoa(app.statistics.SegmentCount))
	}

	speakerCount := document.Call("getElementById", "speaker-count")
	if !speakerCount.IsNull() {
		speakerCount.Set("textContent", strconv.Itoa(app.statistics.SpeakerCount))
	}

	totalDuration := document.Call("getElementById", "total-duration")
	if !totalDuration.IsNull() {
		totalDuration.Set("textContent", app.formatTime(app.statistics.TotalDuration))
	}

	wordCount := document.Call("getElementById", "word-count")
	if !wordCount.IsNull() {
		wordCount.Set("textContent", strconv.Itoa(app.statistics.WordCount))
	}
}

func (app *AudioPipeApp) formatTime(seconds float64) string {
	totalSecs := int(seconds)
	mins := totalSecs / 60
	secs := totalSecs % 60
	return fmt.Sprintf("%d:%02d", mins, secs)
}

func (app *AudioPipeApp) formatSRTTime(seconds float64) string {
	totalSecs := int(seconds)
	hours := totalSecs / 3600
	minutes := (totalSecs % 3600) / 60
	secs := totalSecs % 60
	ms := int((seconds - float64(totalSecs)) * 1000)

	return fmt.Sprintf("%02d:%02d:%02d,%03d", hours, minutes, secs, ms)
}

func (app *AudioPipeApp) toggleTheme(this js.Value, args []js.Value) interface{} {
	body := js.Global().Get("document").Get("body")
	localStorage := js.Global().Get("localStorage")

	if app.isDarkTheme {
		body.Get("classList").Call("remove", "dark-theme")
		localStorage.Call("setItem", "theme", "light")
		app.isDarkTheme = false
	} else {
		body.Get("classList").Call("add", "dark-theme")
		localStorage.Call("setItem", "theme", "dark")
		app.isDarkTheme = true
	}

	app.updateThemeIcon()
	return nil
}

func (app *AudioPipeApp) renderTimeline() {
	if app.transcriptionData == nil {
		return
	}

	document := js.Global().Get("document")
	container := document.Call("getElementById", "transcription-content")
	if container.IsNull() {
		return
	}

	var htmlBuilder strings.Builder

	if app.isConsolidated && len(app.consolidatedData) > 0 {
		for _, segment := range app.consolidatedData {
			speakerColor := app.speakerColors[segment.Speaker]

			htmlBuilder.WriteString(fmt.Sprintf(`
				<div class="timeline-segment-item consolidated" data-start="%.2f" data-end="%.2f">
					<div class="segment-header">
						<div class="speaker-info">
							<div class="speaker-badge" style="background-color: %s"></div>
							<span class="speaker-name">%s</span>
						</div>
						<div class="segment-time">
							%s - %s
						</div>
					</div>
					<div class="segment-text">%s</div>
				</div>
			`, segment.Start, segment.End, speakerColor, segment.Speaker,
				app.formatTime(segment.Start), app.formatTime(segment.End), segment.Text))
		}
	} else {
		for _, segment := range app.transcriptionData.Segments {
			speakerColor := app.speakerColors[segment.Speaker]

			htmlBuilder.WriteString(fmt.Sprintf(`
				<div class="timeline-segment-item" data-start="%.2f" data-end="%.2f">
					<div class="segment-header">
						<div class="speaker-info">
							<div class="speaker-badge" style="background-color: %s"></div>
							<span class="speaker-name">%s</span>
						</div>
						<div class="segment-time">
							%s - %s
						</div>
					</div>
					<div class="segment-text">%s</div>
				</div>
			`, segment.Start, segment.End, speakerColor, segment.Speaker,
				app.formatTime(segment.Start), app.formatTime(segment.End), segment.Text))
		}
	}

	container.Set("innerHTML", htmlBuilder.String())
}

func (app *AudioPipeApp) renderSpeakerTimelines() {
	if app.transcriptionData == nil {
		return
	}

	document := js.Global().Get("document")
	container := document.Call("getElementById", "speaker-waveforms")
	if container.IsNull() {
		return
	}

	speakers := app.getUniqueSpeakers()
	var htmlBuilder strings.Builder

	speakerColors := []string{
		"#d4a574", // Golden/Orange - SPEAKER_00
		"#7ba3d4", // Blue - SPEAKER_01
		"#a47bd4", // Purple
		"#74d4a5", // Green
		"#d47474", // Red
		"#d4d474", // Yellow
	}

	for i, speaker := range speakers {
		speakerSegments := app.getSegmentsForSpeaker(speaker)

		colorIndex := i % len(speakerColors)
		speakerColor := speakerColors[colorIndex]

		htmlBuilder.WriteString(fmt.Sprintf(`
			<div class="speaker-waveform-track" data-speaker="%s">
				<div class="speaker-waveform-header">
					<div class="speaker-info">
						<div class="speaker-badge speaker-%d" style="background-color: %s"></div>
						<span class="speaker-name">%s</span>
					</div>
					<div class="speaker-stats">
						<span>%d</span>
					</div>
				</div>
				<div class="speaker-waveform-content">
					<div class="speaker-waveform-track-display">
						%s
					</div>
				</div>
			</div>
		`, speaker, colorIndex, speakerColor, speaker, len(speakerSegments),
			app.renderProfessionalSpeakerSegmentBars(speaker, speakerSegments, colorIndex)))
	}

	container.Set("innerHTML", htmlBuilder.String())
}

func (app *AudioPipeApp) renderProfessionalSpeakerSegmentBars(speaker string, segments []Segment, colorIndex int) string {
	if len(segments) == 0 {
		return ""
	}

	totalDuration := app.statistics.TotalDuration
	var htmlBuilder strings.Builder

	htmlBuilder.WriteString(`<div class="clean-speaker-timeline" style="position: relative; height: 40px; background: var(--speaker-track-bg); border-radius: 4px; overflow: hidden;">`)

	for i, segment := range segments {
		startPercent := (segment.Start / totalDuration) * 100
		widthPercent := ((segment.End - segment.Start) / totalDuration) * 100

		htmlBuilder.WriteString(fmt.Sprintf(`
			<div class="speaker-segment-bar speaker-%d"
				 data-start="%.2f"
				 data-end="%.2f"
				 data-index="%d"
				 style="left: %.2f%%; width: %.2f%%;"
				 title="%s: %s - %s&#10;%s">
			</div>
		`, colorIndex, segment.Start, segment.End, i, startPercent, widthPercent,
			speaker, app.formatTime(segment.Start), app.formatTime(segment.End), segment.Text))
	}

	htmlBuilder.WriteString("</div>")
	return htmlBuilder.String()
}

func (app *AudioPipeApp) renderSpeakerSegmentBars(speaker string, segments []Segment) string {
	if len(segments) == 0 {
		return ""
	}

	totalDuration := app.statistics.TotalDuration
	speakerColor := app.speakerColors[speaker]
	var htmlBuilder strings.Builder

	htmlBuilder.WriteString(`<div class="clean-speaker-timeline" style="position: relative; height: 35px; background: transparent; border-radius: 4px;">`)

	for i, segment := range segments {
		startPercent := (segment.Start / totalDuration) * 100
		widthPercent := ((segment.End - segment.Start) / totalDuration) * 100

		duration := segment.End - segment.Start
		tooltipText := fmt.Sprintf("%s\n%s - %s (%.1fs)\n\"%s\"",
			speaker,
			app.formatTime(segment.Start),
			app.formatTime(segment.End),
			duration,
			segment.Text)

		htmlBuilder.WriteString(fmt.Sprintf(`
			<div class="speaker-segment-bar clickable-segment"
				 data-start="%.2f"
				 data-end="%.2f"
				 data-speaker="%s"
				 data-text="%s"
				 data-index="%d"
				 style="left: %.2f%%; width: %.2f%%; background-color: %s; cursor: pointer;"
				 title="%s"
				 onclick="seekToTime(null, [%.2f])">
			</div>
		`, segment.Start, segment.End, speaker, segment.Text, i, startPercent, widthPercent, speakerColor, tooltipText, segment.Start))
	}

	htmlBuilder.WriteString("</div>")
	return htmlBuilder.String()
}

func (app *AudioPipeApp) getSegmentsForSpeaker(speaker string) []Segment {
	var segments []Segment
	for _, segment := range app.transcriptionData.Segments {
		if segment.Speaker == speaker {
			segments = append(segments, segment)
		}
	}
	return segments
}

func (app *AudioPipeApp) getTotalDurationForSpeaker(segments []Segment) float64 {
	total := 0.0
	for _, segment := range segments {
		total += segment.End - segment.Start
	}
	return total
}

func (app *AudioPipeApp) handleSearchInput(this js.Value, args []js.Value) interface{} {
	if len(args) > 0 {
		query := args[0].Get("target").Get("value").String()
		app.handleSearch(js.Value{}, []js.Value{js.ValueOf(query)})
	}
	return nil
}

func (app *AudioPipeApp) handleSearch(this js.Value, args []js.Value) interface{} {
	if len(args) == 0 {
		return nil
	}

	query := args[0].String()
	app.searchQuery = query

	document := js.Global().Get("document")
	clearButton := document.Call("getElementById", "clear-search")

	if strings.TrimSpace(query) != "" {
		if !clearButton.IsNull() {
			clearButton.Get("style").Set("display", "block")
		}
		app.filterTranscription(query)
	} else {
		if !clearButton.IsNull() {
			clearButton.Get("style").Set("display", "none")
		}
		app.showAllSegments()
	}

	return nil
}

func (app *AudioPipeApp) clearSearch(this js.Value, args []js.Value) interface{} {
	document := js.Global().Get("document")

	searchInput := document.Call("getElementById", "search-input")
	if !searchInput.IsNull() {
		searchInput.Set("value", "")
	}

	clearButton := document.Call("getElementById", "clear-search")
	if !clearButton.IsNull() {
		clearButton.Get("style").Set("display", "none")
	}

	app.searchQuery = ""
	app.showAllSegments()
	return nil
}

func (app *AudioPipeApp) filterTranscription(query string) {
	document := js.Global().Get("document")
	segments := document.Call("querySelectorAll", ".timeline-segment-item")
	visibleCount := 0
	queryLower := strings.ToLower(query)

	for i := 0; i < segments.Length(); i++ {
		segment := segments.Index(i)
		text := strings.ToLower(segment.Get("textContent").String())

		if strings.Contains(text, queryLower) {
			segment.Get("style").Set("display", "block")
			visibleCount++
		} else {
			segment.Get("style").Set("display", "none")
		}
	}

	if visibleCount == 0 {
		app.showNoResultsState()
	}
}

func (app *AudioPipeApp) showAllSegments() {
	document := js.Global().Get("document")
	segments := document.Call("querySelectorAll", ".timeline-segment-item")

	for i := 0; i < segments.Length(); i++ {
		segment := segments.Index(i)
		segment.Get("style").Set("display", "block")
	}

	noResultsState := document.Call("getElementById", "no-results-state")
	if !noResultsState.IsNull() {
		noResultsState.Get("style").Set("display", "none")
	}
}

func (app *AudioPipeApp) showNoResultsState() {
	app.hideAllStates()
	document := js.Global().Get("document")
	noResultsState := document.Call("getElementById", "no-results-state")
	if !noResultsState.IsNull() {
		noResultsState.Get("style").Set("display", "block")
	}
}

func (app *AudioPipeApp) exportAsText(this js.Value, args []js.Value) interface{} {
	if app.transcriptionData == nil {
		app.showToast("No transcription data to export", "warning")
		return nil
	}

	var textBuilder strings.Builder

	for _, segment := range app.transcriptionData.Segments {
		textBuilder.WriteString(fmt.Sprintf("[%s - %s] %s: %s\n\n",
			app.formatTime(segment.Start), app.formatTime(segment.End),
			segment.Speaker, segment.Text))
	}

	navigator := js.Global().Get("navigator")
	if !navigator.Get("clipboard").IsUndefined() {
		navigator.Get("clipboard").Call("writeText", textBuilder.String()).Call("then",
			js.FuncOf(func(this js.Value, args []js.Value) interface{} {
				app.showToast("Transcription copied to clipboard", "success")
				return nil
			})).Call("catch",
			js.FuncOf(func(this js.Value, args []js.Value) interface{} {
				app.showToast("Failed to copy to clipboard", "error")
				return nil
			}))
	} else {
		app.showToast("Clipboard API not supported", "error")
	}

	return nil
}

func (app *AudioPipeApp) exportAsSRT(this js.Value, args []js.Value) interface{} {
	if app.transcriptionData == nil {
		app.showToast("No transcription data to export", "warning")
		return nil
	}

	var srtBuilder strings.Builder

	for i, segment := range app.transcriptionData.Segments {
		srtBuilder.WriteString(fmt.Sprintf("%d\n%s --> %s\n%s: %s\n\n",
			i+1, app.formatSRTTime(segment.Start), app.formatSRTTime(segment.End),
			segment.Speaker, segment.Text))
	}

	app.downloadFile("transcription.srt", srtBuilder.String(), "text/plain")
	app.showToast("SRT file downloaded", "success")

	return nil
}

func (app *AudioPipeApp) downloadConsolidated(this js.Value, args []js.Value) interface{} {
	if len(app.consolidatedData) == 0 {
		app.showToast("No consolidated segments to download", "warning")
		return nil
	}

	data := map[string]interface{}{
		"segments":               app.consolidatedData,
		"consolidationThreshold": 1.0, // Default threshold
		"generatedAt":            time.Now().Format(time.RFC3339),
	}

	jsonData, err := json.MarshalIndent(data, "", "  ")
	if err != nil {
		app.showToast("Failed to generate JSON", "error")
		return nil
	}

	app.downloadFile("consolidated_segments.json", string(jsonData), "application/json")
	app.showToast("Consolidated segments downloaded", "success")

	return nil
}

func (app *AudioPipeApp) downloadFile(filename, content, mimeType string) {
	uint8Array := js.Global().Get("Uint8Array").New(len(content))
	js.CopyBytesToJS(uint8Array, []byte(content))

	blob := js.Global().Get("Blob").New(
		[]interface{}{uint8Array},
		map[string]interface{}{"type": mimeType},
	)

	url := js.Global().Get("URL").Call("createObjectURL", blob)

	document := js.Global().Get("document")
	link := document.Call("createElement", "a")
	link.Set("href", url)
	link.Set("download", filename)

	document.Get("body").Call("appendChild", link)
	link.Call("click")
	document.Get("body").Call("removeChild", link)

	js.Global().Get("URL").Call("revokeObjectURL", url)
}

func (app *AudioPipeApp) consolidateSegments(this js.Value, args []js.Value) interface{} {
	if app.transcriptionData == nil {
		return nil
	}

	threshold := 1.0 // Default threshold in seconds
	if len(args) > 0 {
		if val := args[0].Float(); val > 0 {
			threshold = val
		}
	}

	segments := make([]Segment, len(app.transcriptionData.Segments))
	copy(segments, app.transcriptionData.Segments)

	sort.Slice(segments, func(i, j int) bool {
		return segments[i].Start < segments[j].Start
	})

	var consolidated []ConsolidatedSegment
	var currentGroup *ConsolidatedSegment

	for _, segment := range segments {
		if currentGroup == nil ||
			currentGroup.Speaker != segment.Speaker ||
			(segment.Start-currentGroup.End) > threshold {

			if currentGroup != nil {
				consolidated = append(consolidated, *currentGroup)
			}

			currentGroup = &ConsolidatedSegment{
				Speaker:   segment.Speaker,
				Start:     segment.Start,
				End:       segment.End,
				Text:      segment.Text,
				Segments:  []Segment{segment},
				WordCount: len(strings.Fields(segment.Text)),
			}
		} else {
			currentGroup.End = segment.End
			currentGroup.Text += " " + segment.Text
			currentGroup.Segments = append(currentGroup.Segments, segment)
			currentGroup.WordCount += len(strings.Fields(segment.Text))
		}
	}

	if currentGroup != nil {
		consolidated = append(consolidated, *currentGroup)
	}

	app.consolidatedData = consolidated

	app.showToast(fmt.Sprintf("Consolidated %d segments into %d groups",
		len(segments), len(consolidated)), "success")

	return nil
}

func (app *AudioPipeApp) showToast(message, toastType string) {
	document := js.Global().Get("document")

	toast := document.Call("createElement", "div")
	toast.Set("className", fmt.Sprintf("toast toast-%s", toastType))
	toast.Set("textContent", message)

	style := toast.Get("style")
	style.Set("position", "fixed")
	style.Set("top", "20px")
	style.Set("right", "20px")
	style.Set("padding", "12px 20px")
	style.Set("borderRadius", "6px")
	style.Set("color", "white")
	style.Set("fontWeight", "500")
	style.Set("zIndex", "10000")
	style.Set("maxWidth", "400px")

	switch toastType {
	case "success":
		style.Set("backgroundColor", "#22c55e")
	case "error":
		style.Set("backgroundColor", "#ef4444")
	case "warning":
		style.Set("backgroundColor", "#f59e0b")
	default:
		style.Set("backgroundColor", "#3b82f6")
	}

	document.Get("body").Call("appendChild", toast)

	js.Global().Call("setTimeout", js.FuncOf(func(this js.Value, args []js.Value) interface{} {
		if !toast.Get("parentNode").IsNull() {
			toast.Get("parentNode").Call("removeChild", toast)
		}
		return nil
	}), 3000)

	log.Printf("Toast [%s]: %s", toastType, message)
}

func (app *AudioPipeApp) isValidAudioFormat(fileName, mimeType string) bool {
	validMimeTypes := []string{
		"audio/mpeg",     // MP3
		"audio/mp3",      // MP3 (alternative)
		"audio/wav",      // WAV
		"audio/wave",     // WAV (alternative)
		"audio/x-wav",    // WAV (alternative)
		"audio/mp4",      // M4A
		"audio/m4a",      // M4A
		"audio/aac",      // AAC
		"audio/ogg",      // OGG
		"audio/webm",     // WebM
	}

	for _, validType := range validMimeTypes {
		if mimeType == validType {
			return true
		}
	}

	fileName = strings.ToLower(fileName)
	validExtensions := []string{".mp3", ".wav", ".m4a", ".aac", ".ogg", ".webm"}

	for _, ext := range validExtensions {
		if strings.HasSuffix(fileName, ext) {
			return true
		}
	}

	return false
}

func (app *AudioPipeApp) estimateProcessingTime(fileSize int) int {
	sizeMB := float64(fileSize) / (1024 * 1024)
	estimatedSeconds := int(sizeMB * 0.5)

	if estimatedSeconds < 2 {
		estimatedSeconds = 2
	} else if estimatedSeconds > 120 {
		estimatedSeconds = 120
	}

	return estimatedSeconds
}

func (app *AudioPipeApp) calculateTimeout(fileSize int) int {
	sizeMB := float64(fileSize) / (1024 * 1024)
	timeoutSeconds := 30 + int(sizeMB)

	if timeoutSeconds < 30 {
		timeoutSeconds = 30
	} else if timeoutSeconds > 300 {
		timeoutSeconds = 300
	}

	return timeoutSeconds
}

func (app *AudioPipeApp) updateLoadingMessage(message string) {
	document := js.Global().Get("document")
	loadingMessage := document.Call("getElementById", "loading-message")
	if !loadingMessage.IsNull() {
		loadingMessage.Set("textContent", message)
	}
}

func (app *AudioPipeApp) handleAudioInput(this js.Value, args []js.Value) interface{} {
	if len(args) > 0 {
		files := args[0].Get("target").Get("files")
		if files.Length() > 0 {
			app.processAudioFile(files.Index(0))
		}
	}
	return nil
}

func (app *AudioPipeApp) loadAudioFile(this js.Value, args []js.Value) interface{} {
	if len(args) > 0 {
		app.processAudioFile(args[0])
	}
	return nil
}

func (app *AudioPipeApp) processAudioFile(file js.Value) {
	fileName := file.Get("name").String()
	fileSize := file.Get("size").Int()
	fileType := file.Get("type").String()

	log.Printf("🎵 AUDIO PROCESSING STARTED: %s (size: %.2f MB, type: %s)", fileName, float64(fileSize)/(1024*1024), fileType)

	if !app.isValidAudioFormat(fileName, fileType) {
		log.Printf("❌ AUDIO VALIDATION FAILED: Unsupported format %s", fileType)
		app.showToast("Unsupported audio format. Supported: MP3, WAV, M4A, AAC, OGG", "error")
		app.showUploadState()
		return
	}
	log.Printf("✅ AUDIO VALIDATION PASSED: Format %s is supported", fileType)

	fileSizeMB := float64(fileSize) / (1024 * 1024)
	app.showLoadingState(fmt.Sprintf("Loading audio file %s (%.1f MB)...", fileName, fileSizeMB))

	maxSizeMB := 500
	if fileSize > maxSizeMB*1024*1024 {
		log.Printf("❌ AUDIO SIZE VALIDATION FAILED: %.1f MB exceeds %d MB limit", fileSizeMB, maxSizeMB)
		app.showToast(fmt.Sprintf("Audio file too large (max %d MB). Current: %.1f MB", maxSizeMB, fileSizeMB), "error")
		app.showUploadState()
		return
	}
	log.Printf("✅ AUDIO SIZE VALIDATION PASSED: %.1f MB is within %d MB limit", fileSizeMB, maxSizeMB)

	log.Printf("🌊 INITIALIZING WAVESURFER.JS...")
	app.initializeWaveSurfer(file, fileName)
}

func (app *AudioPipeApp) initializeWaveSurfer(file js.Value, fileName string) {
	log.Printf("🌊 WAVESURFER INITIALIZATION STARTED...")

	waveSurferGlobal := js.Global().Get("WaveSurfer")
	if waveSurferGlobal.IsUndefined() {
		log.Printf("❌ WAVESURFER NOT FOUND: WaveSurfer.js library not loaded")
		app.showToast("WaveSurfer.js library not loaded", "error")
		app.showUploadState()
		return
	}
	log.Printf("✅ WAVESURFER LIBRARY FOUND: WaveSurfer.js is available")

	document := js.Global().Get("document")
	container := document.Call("getElementById", "main-waveform")
	if container.IsNull() {
		log.Printf("❌ WAVEFORM CONTAINER NOT FOUND: #main-waveform element missing")
		app.showToast("Waveform container not found", "error")
		app.showUploadState()
		return
	}
	log.Printf("✅ WAVEFORM CONTAINER FOUND: #main-waveform element located")

	container.Set("innerHTML", "")
	log.Printf("🧹 CONTAINER CLEARED: Removed placeholder content")

	log.Printf("🎨 CREATING WAVESURFER INSTANCE...")

	containerWidth := container.Get("clientWidth").Int()
	if containerWidth == 0 {
		containerWidth = 800
	}

	maxPixelsPerSecond := 2.0

	waveSurfer := waveSurferGlobal.Call("create", map[string]interface{}{
		"container":        container,
		"waveColor":        "#22c55e",
		"progressColor":    "#16a34a",
		"cursorColor":      "#ffffff",
		"barWidth":         2,
		"barRadius":        1,
		"responsive":       true,
		"height":           120,
		"normalize":        true,
		"backend":          "WebAudio",
		"pixelRatio":       1,
		"interact":         true,
		"hideScrollbar":    true,
		"minPxPerSec":      maxPixelsPerSecond, // Limit resolution for large files
	})

	if waveSurfer.IsUndefined() {
		log.Printf("❌ WAVESURFER CREATION FAILED: Could not create WaveSurfer instance")
		app.showToast("Failed to create WaveSurfer instance", "error")
		app.showUploadState()
		return
	}
	log.Printf("✅ WAVESURFER INSTANCE CREATED: WaveSurfer initialized successfully")

	fileBlob := file
	log.Printf("📁 FILE BLOB STORED: Ready for WaveSurfer loading")

	log.Printf("🎧 SETTING UP WAVESURFER EVENT LISTENERS...")

	waveSurfer.Call("on", "ready", js.FuncOf(func(this js.Value, args []js.Value) interface{} {
		duration := waveSurfer.Call("getDuration").Float()
		log.Printf("✅ WAVESURFER READY: Waveform loaded, Duration=%.2fs", duration)

		app.audioData = &AudioData{
			FileName:   fileName,
			Duration:   duration,
			WaveSurfer: waveSurfer,
			FileBlob:   fileBlob,
		}

		app.updateAudioUI()
		app.showToast(fmt.Sprintf("Loaded audio: %s (%.1fs)", fileName, duration), "success")

		if app.transcriptionData != nil {
			log.Printf("📝 TRANSCRIPTION DATA AVAILABLE: Switching to visualization view")
			app.showVisualizationView(js.Value{}, []js.Value{})
		} else {
			log.Printf("📝 NO TRANSCRIPTION DATA: Staying in upload state")
			app.showUploadState()
		}

		return nil
	}))

	waveSurfer.Call("on", "loading", js.FuncOf(func(this js.Value, args []js.Value) interface{} {
		if len(args) > 0 {
			progress := args[0].Float()
			log.Printf("📊 WAVESURFER LOADING: %.1f%% complete", progress)

			progressMessage := fmt.Sprintf("Loading and analyzing audio: %.1f%% complete", progress)
			app.updateLoadingMessage(progressMessage)
		}
		return nil
	}))

	waveSurfer.Call("on", "error", js.FuncOf(func(this js.Value, args []js.Value) interface{} {
		errorMsg := "Unknown error"
		if len(args) > 0 {
			error := args[0]
			if !error.IsUndefined() {
				if !error.Get("message").IsUndefined() {
					errorMsg = error.Get("message").String()
				} else {
					errorMsg = error.String()
				}
			}
		}
		log.Printf("❌ WAVESURFER ERROR: %s", errorMsg)

		if strings.Contains(errorMsg, "Invalid array length") || strings.Contains(errorMsg, "RangeError") {
			log.Printf("🔧 MEMORY ERROR DETECTED: Audio file too large for current settings")
			app.showToast("Audio file is very large. Waveform display may be limited.", "warning")
		} else {
			app.showToast("Failed to load audio: "+errorMsg, "error")
			app.showUploadState()
		}
		return nil
	}))

	waveSurfer.Call("on", "play", js.FuncOf(func(this js.Value, args []js.Value) interface{} {
		log.Printf("▶️ WAVESURFER PLAY: Audio playback started")
		app.isPlaying = true
		app.updatePlayButton()
		return nil
	}))

	waveSurfer.Call("on", "pause", js.FuncOf(func(this js.Value, args []js.Value) interface{} {
		log.Printf("⏸️ WAVESURFER PAUSE: Audio playback paused")
		app.isPlaying = false
		app.updatePlayButton()
		return nil
	}))

	waveSurfer.Call("on", "audioprocess", js.FuncOf(func(this js.Value, args []js.Value) interface{} {
		if len(args) > 0 {
			currentTime := args[0].Float()
			app.currentTime = currentTime
			app.updateTimeDisplay()
			app.highlightCurrentSpeaker()
		}
		return nil
	}))

	log.Printf("✅ WAVESURFER EVENT LISTENERS SETUP COMPLETE")

	log.Printf("📂 LOADING AUDIO FILE INTO WAVESURFER...")

	js.Global().Call("setTimeout", js.FuncOf(func(this js.Value, args []js.Value) interface{} {
		promise := js.Global().Get("Promise").Call("resolve").Call("then", js.FuncOf(func(this js.Value, args []js.Value) interface{} {
			waveSurfer.Call("loadBlob", fileBlob)
			return nil
		}))

		promise.Call("catch", js.FuncOf(func(this js.Value, args []js.Value) interface{} {
			log.Printf("❌ WAVESURFER LOADBLOB FAILED: Creating fallback waveform")
			app.createFallbackWaveform(container, fileName)
			return nil
		}))

		return nil
	}), 100)
}

func (app *AudioPipeApp) createFallbackWaveform(container js.Value, fileName string) {
	log.Printf("🔧 CREATING FALLBACK WAVEFORM: For large audio file")

	container.Set("innerHTML", "")

	document := js.Global().Get("document")
	fallbackDiv := document.Call("createElement", "div")
	fallbackDiv.Get("style").Set("width", "100%")
	fallbackDiv.Get("style").Set("height", "120px")
	fallbackDiv.Get("style").Set("background", "linear-gradient(90deg, #22c55e 0%, #16a34a 50%, #22c55e 100%)")
	fallbackDiv.Get("style").Set("border-radius", "4px")
	fallbackDiv.Get("style").Set("display", "flex")
	fallbackDiv.Get("style").Set("align-items", "center")
	fallbackDiv.Get("style").Set("justify-content", "center")
	fallbackDiv.Get("style").Set("color", "white")
	fallbackDiv.Get("style").Set("font-weight", "bold")
	fallbackDiv.Get("style").Set("cursor", "pointer")
	fallbackDiv.Set("textContent", "🎵 Large Audio File - Click to Play")

	container.Call("appendChild", fallbackDiv)

	app.showToast("Large audio file loaded with simplified waveform", "info")
}













func (app *AudioPipeApp) updateConsolidationThreshold(this js.Value, args []js.Value) interface{} {
	if len(args) > 0 {
		valueStr := args[0].Get("target").Get("value").String()
		threshold, err := strconv.ParseFloat(valueStr, 64)
		if err != nil {
			log.Printf("Error parsing threshold value: %v", err)
			return nil
		}

		app.consolidationThreshold = threshold

		document := js.Global().Get("document")
		thresholdValue := document.Call("getElementById", "threshold-value")
		if !thresholdValue.IsNull() {
			thresholdValue.Set("textContent", fmt.Sprintf("%.1fs", threshold))
		}
	}
	return nil
}

func (app *AudioPipeApp) applyConsolidation(this js.Value, args []js.Value) interface{} {
	if app.transcriptionData == nil {
		app.showToast("No transcription data loaded", "warning")
		return nil
	}

	app.showLoadingState("Consolidating segments...")

	consolidated := app.consolidateSegmentsByThreshold(app.consolidationThreshold)
	app.consolidatedData = consolidated
	app.isConsolidated = true

	app.showToast(fmt.Sprintf("Consolidated %d segments into %d groups", len(app.transcriptionData.Segments), len(consolidated)), "success")

	if app.currentView == "timeline" {
		app.showTimelineView(js.Value{}, []js.Value{})
	} else if app.currentView == "visualization" {
		app.showVisualizationView(js.Value{}, []js.Value{})
	}

	return nil
}

func (app *AudioPipeApp) consolidateSegmentsByThreshold(threshold float64) []ConsolidatedSegment {
	if app.transcriptionData == nil || len(app.transcriptionData.Segments) == 0 {
		return []ConsolidatedSegment{}
	}

	segments := app.transcriptionData.Segments
	var consolidated []ConsolidatedSegment

	currentGroup := ConsolidatedSegment{
		Speaker: segments[0].Speaker,
		Start:   segments[0].Start,
		End:     segments[0].End,
		Text:    segments[0].Text,
	}

	for i := 1; i < len(segments); i++ {
		segment := segments[i]
		gap := segment.Start - currentGroup.End

		if segment.Speaker == currentGroup.Speaker && gap <= threshold {
			currentGroup.End = segment.End
			currentGroup.Text += " " + segment.Text
		} else {
			consolidated = append(consolidated, currentGroup)
			currentGroup = ConsolidatedSegment{
				Speaker: segment.Speaker,
				Start:   segment.Start,
				End:     segment.End,
				Text:    segment.Text,
			}
		}
	}

	consolidated = append(consolidated, currentGroup)
	return consolidated
}



func (app *AudioPipeApp) highlightCurrentSpeaker() {
	if app.transcriptionData == nil {
		return
	}

	document := js.Global().Get("document")
	segments := document.Call("querySelectorAll", ".timeline-segment-item")

	for i := 0; i < segments.Length(); i++ {
		segment := segments.Index(i)
		startAttr := segment.Call("getAttribute", "data-start")
		endAttr := segment.Call("getAttribute", "data-end")

		if !startAttr.IsNull() && !endAttr.IsNull() {
			startStr := startAttr.String()
			endStr := endAttr.String()

			startTime, startErr := strconv.ParseFloat(startStr, 64)
			endTime, endErr := strconv.ParseFloat(endStr, 64)

			if startErr != nil || endErr != nil {
				log.Printf("⚠️ SPEAKER HIGHLIGHT: Failed to parse time attributes - start='%s', end='%s'", startStr, endStr)
				continue
			}

			if app.currentTime >= startTime && app.currentTime <= endTime {
				segment.Get("classList").Call("add", "current-playing")
			} else {
				segment.Get("classList").Call("remove", "current-playing")
			}
		}
	}
}

func (app *AudioPipeApp) updateAudioUI() {
	if app.audioData == nil {
		return
	}

	document := js.Global().Get("document")

	filenameElement := document.Call("getElementById", "audio-filename")
	if !filenameElement.IsNull() {
		filenameElement.Set("textContent", app.audioData.FileName)
	}

	totalTimeElement := document.Call("getElementById", "total-time")
	if !totalTimeElement.IsNull() {
		totalTimeElement.Set("textContent", app.formatTime(app.audioData.Duration))
	}
}

func (app *AudioPipeApp) togglePlayback(this js.Value, args []js.Value) interface{} {
	if app.audioData == nil {
		log.Printf("⚠️ PLAYBACK TOGGLE IGNORED: No audio data loaded")
		app.showToast("No audio file loaded", "warning")
		return nil
	}

	waveSurfer := app.audioData.WaveSurfer
	if waveSurfer.IsUndefined() {
		log.Printf("❌ PLAYBACK TOGGLE FAILED: WaveSurfer instance not available")
		app.showToast("Audio player not available", "error")
		return nil
	}

	isPlaying := waveSurfer.Call("isPlaying").Bool()
	if isPlaying {
		log.Printf("⏸️ PAUSING PLAYBACK: WaveSurfer pause requested")
		waveSurfer.Call("pause")
	} else {
		log.Printf("▶️ STARTING PLAYBACK: WaveSurfer play requested")
		waveSurfer.Call("play")
	}

	return nil
}



func (app *AudioPipeApp) seekAudio(this js.Value, args []js.Value) interface{} {
	if len(args) > 0 && app.audioData != nil {
		time := args[0].Float()
		app.seekToTime(js.Value{}, []js.Value{js.ValueOf(time)})
	}
	return nil
}

func (app *AudioPipeApp) seekToTime(this js.Value, args []js.Value) interface{} {
	if len(args) == 0 || app.audioData == nil {
		log.Printf("⚠️ SEEK IGNORED: No arguments or audio data")
		return nil
	}

	targetTime := args[0].Float()

	if targetTime < 0 {
		targetTime = 0
	} else if targetTime > app.audioData.Duration {
		targetTime = app.audioData.Duration
	}

	log.Printf("🎯 SEEKING TO TIME: %.2fs", targetTime)

	waveSurfer := app.audioData.WaveSurfer
	if !waveSurfer.IsUndefined() {
		waveSurfer.Call("seekTo", targetTime/app.audioData.Duration)
		log.Printf("✅ WAVESURFER SEEK COMPLETE: Moved to %.2fs", targetTime)
	} else {
		log.Printf("❌ SEEK FAILED: WaveSurfer instance not available")
	}

	app.currentTime = targetTime
	app.updateTimeDisplay()

	return nil
}

func (app *AudioPipeApp) updatePlayButton() {
	document := js.Global().Get("document")
	playBtn := document.Call("querySelector", ".waveform-controls .waveform-btn i")

	if !playBtn.IsNull() {
		if app.isPlaying {
			playBtn.Set("className", "fas fa-pause")
		} else {
			playBtn.Set("className", "fas fa-play")
		}
	}
}

func (app *AudioPipeApp) updateTimeDisplay() {
	document := js.Global().Get("document")
	currentTimeElement := document.Call("getElementById", "current-time")

	if !currentTimeElement.IsNull() {
		currentTimeElement.Set("textContent", app.formatTime(app.currentTime))
	}
}


