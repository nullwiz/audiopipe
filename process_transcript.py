#!/usr/bin/env python3
import json
import argparse
from typing import List, Dict
from dataclasses import dataclass
from pathlib import Path

@dataclass
class Segment:
    speaker: str
    text: str
    start: float
    end: float

def load_transcription(file_path: str) -> Dict:
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def consolidate_segments(segments: List[Dict], max_gap: float = 3.0) -> List[Dict]:
    """Consolidate consecutive segments from the same speaker into single utterances"""
    if not segments:
        return []
    
    consolidated = []
    current_speaker = None
    current_text = []
    current_start = None
    current_end = None
    
    for segment in segments:
        should_start_new = (
            current_speaker is None or
            segment["speaker"] != current_speaker or
            (segment["start"] - current_end > max_gap)
        )
        
        if should_start_new:
            if current_text:
                consolidated.append({
                    "speaker": current_speaker,
                    "text": " ".join(current_text),
                    "start": current_start,
                    "end": current_end
                })
            current_speaker = segment["speaker"]
            current_text = [segment["text"].strip()]
            current_start = segment["start"]
            current_end = segment["end"]
        else:
            current_text.append(segment["text"].strip())
            current_end = segment["end"]
    
    if current_text:
        consolidated.append({
            "speaker": current_speaker,
            "text": " ".join(current_text),
            "start": current_start,
            "end": current_end
        })
    
    return consolidated

def main():
    parser = argparse.ArgumentParser(description="Process transcription output to consolidate segments and fix encoding")
    parser.add_argument("input", help="Path to input JSON file (default: output/final_transcription.json)", 
                      nargs='?', default="output/final_transcription.json")
    parser.add_argument("--output", "-o", help="Path to output JSON file", default=None)
    parser.add_argument("--max-gap", "-g", type=float, help="Maximum gap between segments to consolidate (seconds)", 
                      default=3.0)
    parser.add_argument("--debug", "-d", action="store_true", help="Show detailed debug info about consolidation")
    args = parser.parse_args()
    
    data = load_transcription(args.input)
    
    consolidated = consolidate_segments(data["segments"], args.max_gap)
    
    output_data = {
        "speakers": data["speakers"],
        "segments": consolidated
    }
    
    if args.output:
        output_path = args.output
    else:
        input_path = Path(args.input)
        output_path = str(input_path.parent / f"{input_path.stem}_consolidated{input_path.suffix}")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    print(f"\n✨ Processing complete!")
    print(f"📊 Consolidated {len(data['segments'])} segments into {len(consolidated)} utterances")
    print(f"📝 Output saved to: {output_path}")
    
    if args.debug:
        print("\n🔍 Debug Info:")
        for i, segment in enumerate(consolidated[:5]):
            print(f"\nSegment {i}:")
            print(f"  Speaker: {segment['speaker']}")
            print(f"  Time: {segment['start']:.2f}s - {segment['end']:.2f}s (duration: {segment['end'] - segment['start']:.2f}s)")
            print(f"  Text: {segment['text']}")
    else:
        print("\n📜 Sample output:")
        for segment in consolidated[:3]:
            print(f"\n{segment['speaker']} ({segment['start']:.1f}s - {segment['end']:.1f}s):")
            print(f"  {segment['text']}")

if __name__ == "__main__":
    main() 