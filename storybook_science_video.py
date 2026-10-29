"""Generate an automated AI-illustrated 2D science video."""
import json
import os
import shutil
from datetime import date
from pathlib import Path

from scripts.generate_story import generate_story
from scripts.generate_scene_images import generate_scene_images
from scripts.storybook_html_compositor import compose
from scripts.make_voice import make_voice
from scripts.render_video import render_video

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"

def main():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("FFmpeg and ffprobe must be installed.")
    for secret in ("GEMINI_API_KEY", "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN"):
        if not os.getenv(secret):
            raise RuntimeError(f"{secret} is missing. Add it in GitHub Actions secrets.")
    OUT.mkdir(exist_ok=True)
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    workflow_config = dict(config)
    workflow_config["topic_history_file"] = os.getenv("TOPIC_HISTORY_FILE", "storybook_topic_history.json")
    story = generate_story(ROOT, workflow_config)
    if not isinstance(story, dict) or not story.get("scenes"):
        raise RuntimeError("Story generator returned no scenes.")
    day = date.today().isoformat()
    topic = str(story.get("topic", "Science discovery"))
    story["visual_style"] = "original AI-generated 2D storybook illustrations composed with HTML/CSS"
    print(f"Topic: {topic}", flush=True)
    story_path = OUT / f"storybook-science-story-{day}.json"
    story_path.write_text(json.dumps(story, ensure_ascii=False, indent=2), encoding="utf-8")
    raw_dir = OUT / f"storybook-science-ai-raw-{day}"
    scene_dir = OUT / f"storybook-science-scenes-{day}"
    for path in (raw_dir, scene_dir):
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True)
    width, height = int(config.get("width", 1280)), int(config.get("height", 720))
    credits = generate_scene_images(story, raw_dir, width, height)
    raw_images = sorted(raw_dir.glob("scene-*.png"))
    if len(raw_images) != len(story["scenes"]):
        raise RuntimeError(f"Expected {len(story['scenes'])} AI images, got {len(raw_images)}.")
    import asyncio
    asyncio.run(compose(raw_images, story, scene_dir, width, height))
    credits_path = OUT / f"storybook-science-image-credits-{day}.json"
    credits_path.write_text(json.dumps(credits, ensure_ascii=False, indent=2), encoding="utf-8")
    narration = "\n\n".join(str(s.get("narration", "")).strip() for s in story["scenes"] if s.get("narration"))
    if not narration:
        raise RuntimeError("The story contains no narration.")
    narration_path = OUT / f"storybook-science-narration-{day}.mp3"
    make_voice(narration, narration_path, config)
    video_path = OUT / f"storybook-science-{day}.mp4"
    render_video(scene_dir, narration_path, video_path, story, config)
    shutil.rmtree(raw_dir, ignore_errors=True)
    print(f"Finished video: {video_path}", flush=True)
    print(f"Image source/license report: {credits_path}", flush=True)

if __name__ == "__main__":
    main()
