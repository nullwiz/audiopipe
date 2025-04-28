#!/usr/bin/env python3
import os
import json
import pytest
import subprocess
import shutil
from pathlib import Path

@pytest.fixture(scope="module")
def setup_test_env():
    """Setup test environment with real test audio files"""
    # Create output directory if it doesn't exist
    os.makedirs("output", exist_ok=True)
    
    # Ensure test input exists
    test_input = Path("test/data/test_input.wav")
    assert test_input.exists(), "Test input file missing"
    
    # Backup any existing output
    if Path("output/backup").exists():
        shutil.rmtree("output/backup")
    
    # Move any existing output to backup
    output_files = [f for f in Path("output").glob("*") if f.name != ".gitkeep"]
    if output_files:
        os.makedirs("output/backup", exist_ok=True)
        for f in output_files:
            if f.is_file():
                shutil.copy2(f, Path("output/backup") / f.name)
            elif f.is_dir() and f.name != "backup":
                shutil.copytree(f, Path("output/backup") / f.name)
    
    yield test_input
    
    # Cleanup created test files but leave output for inspection
    print("\nLeaving output files for inspection in 'output/' directory")

@pytest.mark.integration
def test_audio_separation(setup_test_env):
    """Test the audio separation step"""
    test_input = setup_test_env
    
    # Run audio separation
    result = subprocess.run(
        ["python", "dem.py", str(test_input)],
        capture_output=True, text=True
    )
    
    # Check for success
    assert result.returncode == 0, f"Audio separation failed: {result.stderr}"
    
    # Check output files exist
    vocals_path = Path("output/combined_vocals.wav")
    background_path = Path("output/combined_background.wav")
    
    assert vocals_path.exists(), "Vocals file not created"
    assert background_path.exists(), "Background file not created"
    
    # Check file sizes are reasonable (not empty)
    assert vocals_path.stat().st_size > 1000, "Vocals file too small"
    assert background_path.stat().st_size > 1000, "Background file too small"
    
    print(f"✅ Audio separation successful")
    return vocals_path

@pytest.mark.integration
def test_diarization(setup_test_env):
    """Test the speaker diarization step"""
    # First run separation if needed
    vocals_path = Path("output/combined_vocals.wav")
    if not vocals_path.exists():
        vocals_path = test_audio_separation(setup_test_env)
    
    # Run diarization with 2 speakers
    result = subprocess.run(
        ["python", "diarize.py", str(vocals_path), "--num-speakers", "2"],
        capture_output=True, text=True
    )
    
    # Check for success
    assert result.returncode == 0, f"Diarization failed: {result.stderr}"
    
    # Check output file exists
    diarized_json = Path("output/combined_vocals_diarized.json")
    assert diarized_json.exists(), "Diarization JSON not created"
    
    # Parse and validate content
    with open(diarized_json, 'r') as f:
        data = json.load(f)
    
    assert "speakers" in data, "Missing speakers in output"
    assert "segments" in data, "Missing segments in output"
    assert len(data["speakers"]) == 2, f"Expected 2 speakers, got {len(data['speakers'])}"
    assert len(data["segments"]) > 0, "No segments detected"
    
    print(f"✅ Diarization successful with {len(data['segments'])} segments")
    return diarized_json

@pytest.mark.integration
def test_transcription(setup_test_env):
    """Test the transcription step"""
    # Make sure previous steps are done
    diarized_json = Path("output/combined_vocals_diarized.json")
    if not diarized_json.exists():
        diarized_json = test_diarization(setup_test_env)
    
    # Run the full pipeline with start-step 3 (transcription only)
    result = subprocess.run(
        ["python", "pipeline.py", str(setup_test_env), "--start-step", "3"],
        capture_output=True, text=True
    )
    
    # Check for success
    assert result.returncode == 0, f"Transcription failed: {result.stderr}"
    
    # Check output file exists
    transcript_json = Path("output/final_transcription.json")
    assert transcript_json.exists(), "Transcription JSON not created"
    
    # Parse and validate content
    with open(transcript_json, 'r') as f:
        data = json.load(f)
    
    assert "speakers" in data, "Missing speakers in transcript"
    assert "segments" in data, "Missing segments in transcript"
    assert len(data["segments"]) > 0, "No segments transcribed"
    
    # Check content - should contain specific keywords from our test file
    all_text = " ".join(seg["text"].lower() for seg in data["segments"])
    expected_phrases = ["test", "speaker", "fox", "jump"]
    found_phrases = [phrase for phrase in expected_phrases if phrase in all_text]
    
    assert len(found_phrases) > 0, f"Expected phrases not found in transcript: {expected_phrases}"
    
    print(f"✅ Transcription successful with {len(data['segments'])} segments")
    print(f"Found expected phrases: {found_phrases}")
    return transcript_json

@pytest.mark.integration
def test_consolidation(setup_test_env):
    """Test the transcript consolidation step"""
    # Make sure previous steps are done
    transcript_json = Path("output/final_transcription.json")
    if not transcript_json.exists():
        transcript_json = test_transcription(setup_test_env)
    
    # Run the consolidation
    result = subprocess.run(
        ["python", "process_transcript.py"],
        capture_output=True, text=True
    )
    
    # Check for success
    assert result.returncode == 0, f"Consolidation failed: {result.stderr}"
    
    # Check output file exists
    consolidated_json = Path("output/final_transcription_consolidated.json")
    assert consolidated_json.exists(), "Consolidated JSON not created"
    
    # Parse and validate content
    with open(consolidated_json, 'r') as f:
        consolidated_data = json.load(f)
    
    with open(transcript_json, 'r') as f:
        original_data = json.load(f)
    
    assert "speakers" in consolidated_data, "Missing speakers in consolidated output"
    assert "segments" in consolidated_data, "Missing segments in consolidated output"
    
    # Consolidation should generally produce fewer or equal segments
    assert len(consolidated_data["segments"]) <= len(original_data["segments"]), \
        "Consolidation resulted in more segments than the original"
    
    print(f"✅ Consolidation successful")
    print(f"Original segments: {len(original_data['segments'])}")
    print(f"Consolidated segments: {len(consolidated_data['segments'])}")
    return consolidated_json

@pytest.mark.integration
@pytest.mark.slow
def test_full_pipeline(setup_test_env):
    """Test the entire pipeline from start to finish"""
    # Clean output directory
    for pattern in ["combined_*", "*_diarized.json", "final_*.json"]:
        for f in Path("output").glob(pattern):
            if f.is_file():
                f.unlink()
    
    # Run the full pipeline
    result = subprocess.run(
        ["python", "pipeline.py", str(setup_test_env), "--num-speakers", "2", "--language", "en"],
        capture_output=True, text=True
    )
    
    # Check for success
    assert result.returncode == 0, f"Full pipeline failed: {result.stderr}"
    
    # Check output files exist
    assert Path("output/combined_vocals.wav").exists(), "Vocals not created"
    assert Path("output/combined_vocals_diarized.json").exists(), "Diarization not created"
    assert Path("output/final_transcription.json").exists(), "Transcription not created"
    
    # Run consolidation
    subprocess.run(["python", "process_transcript.py"], check=True)
    assert Path("output/final_transcription_consolidated.json").exists(), "Consolidation not created"
    
    print(f"✅ Full pipeline successful")
    
    # Print a summary of the final output
    with open("output/final_transcription_consolidated.json", 'r') as f:
        final_data = json.load(f)
    
    print("\nFinal Transcript:")
    for i, segment in enumerate(final_data["segments"]):
        print(f"{segment['speaker']} ({segment['start']:.1f}-{segment['end']:.1f}): {segment['text']}")

if __name__ == "__main__":
    pytest.main(["-v", "--integration", "test/test_integration.py"]) 