import os, sys, json, subprocess, shutil
from pathlib import Path
from datetime import date
from scripts.generate_story import generate_story
from scripts.make_art import make_scene_art
from scripts.make_voice import make_voice
from scripts.render_video import render_video

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"
OUT.mkdir(exist_ok=True)

def main():
    if not shutil.which("ffmpeg"):
        raise RuntimeError("FFmpeg was not found. Install it and make sure `ffmpeg` is on PATH.")
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    day = date.today().isoformat()
    story_path = OUT / f"story-{day}.json"
    if not os.getenv("GEMINI_API_KEY"):
        raise RuntimeError("GEMINI_API_KEY is missing. Add it as an environment variable / GitHub Actions secret.")
    story = generate_story(ROOT, config)
    story_path.write_text(json.dumps(story, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Topic: {story['topic']}")
    print("Generating colorful scene artwork...")
    scene_dir = OUT / f"scenes-{day}"
    if scene_dir.exists():
        shutil.rmtree(scene_dir)
    scene_dir.mkdir(parents=True)
    for i, scene in enumerate(story["scenes"], 1):
        make_scene_art(scene, i, len(story["scenes"]), scene_dir / f"scene-{i:03d}.png",
                       config["width"], config["height"])
    narration = "\n\n".join(s["narration"].strip() for s in story["scenes"])
    narration_path = OUT / f"narration-{day}.mp3"
    make_voice(narration, narration_path, config)
    video_path = OUT / f"stickman-science-{day}.mp4"
    render_video(scene_dir, narration_path, video_path, story, config)
    print(f"Finished: {video_path}")
    print(f"Story: {story_path}")
    print(f"Topic: {story['topic']}")

if __name__ == "__main__":
    main()
