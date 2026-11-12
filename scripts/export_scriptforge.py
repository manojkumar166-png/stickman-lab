#!/usr/bin/env python3
"""Export the generated story as a timestamped ScriptForge script and split narration into 3 parts."""
import argparse, json, re, subprocess
from pathlib import Path

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--story", required=True)
    ap.add_argument("--voice", required=True)
    ap.add_argument("--output", default="output")
    ap.add_argument("--target-minutes", type=int, default=6)
    a = ap.parse_args()
    out = Path(a.output); out.mkdir(parents=True, exist_ok=True)
    story = json.loads(Path(a.story).read_text(encoding="utf-8"))
    scenes = story.get("scenes") or []
    if not scenes: raise SystemExit("No scenes in generated story JSON.")
    probe = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",a.voice],check=True,capture_output=True,text=True)
    duration = float(probe.stdout.strip())
    weights = [max(1,len(str(s.get("narration","")).split())) for s in scenes]
    total = sum(weights)
    def stamp(t):
        n = int(t)
        return f"{n//60:02d}:{n%60:02d}"
    lines = [f"# {story.get('topic','Video script')}", "", f"**Target runtime:** {a.target_minutes} minutes", "", "## Script"]
    cursor = 0.0
    for i, scene in enumerate(scenes):
        lines += [f"### [{stamp(cursor)}] {scene.get('title') or 'Scene '+str(i+1)}", "", "[NARRATION]", str(scene.get("narration","")).strip(), "", "[VISUAL]", str(scene.get("visual","")).strip(), ""]
        cursor += duration * weights[i] / total
    narration = " ".join(str(s.get("narration","")).strip() for s in scenes)
    words = len(narration.split())
    topic = str(story.get("topic","")).rstrip("?")
    lines += ["## Publishing package", "", "### Alternative titles",
              f"1. {story.get('topic','')}", f"2. The Truth About {topic}", f"3. What Nobody Explains About {topic}",
              "", "### Thumbnail text", topic[:42].upper(), "", "### Tags",
              "#explainer #education #animation #storytelling #facelessyoutube",
              "", f"**Word count:** {words}", f"**Estimated runtime:** {words/150:.1f} minutes"]
    (out / "scriptforge-script.md").write_text("\n".join(lines),encoding="utf-8")
    segment = max(1.0,duration/3)
    subprocess.run(["ffmpeg","-y","-v","error","-i",a.voice,"-f","segment","-segment_time",str(segment),"-reset_timestamps","1","-c","copy",str(out/"voiceover-part-%02d.mp3")],check=True)
    print(f"ScriptForge script: {words} words; voiceover split into 3 segments.")

if __name__ == "__main__":
    main()
