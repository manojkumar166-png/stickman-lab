"""Generate a science story video using images found on public search pages."""
import asyncio
import hashlib
import json
import os
import shutil
from datetime import date
from pathlib import Path

from scripts.generate_story import generate_story
from scripts.openverse_visuals import download_scene_illustrations
from scripts.external_image_scene_renderer import render_external_scenes
from scripts.make_voice import make_voice
from scripts.render_video import render_video

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"

def main():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("FFmpeg and ffprobe must be installed.")
    if not os.getenv("GEMINI_API_KEY"):
        raise RuntimeError("GEMINI_API_KEY is missing (used for story text only; never for images).")
    OUT.mkdir(exist_ok=True)
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    workflow_config = dict(config)
    workflow_config["topic_history_file"] = os.getenv("TOPIC_HISTORY_FILE", "storybook_topic_history.json")

    story = generate_story(ROOT, workflow_config)
    if not isinstance(story, dict) or not story.get("scenes"):
        raise RuntimeError("Story generator returned no scenes.")
    day = date.today().isoformat()
    topic = str(story.get("topic", "Science discovery"))
    story["visual_style"] = "static illustrations discovered through public image-search pages; review image licenses in the attribution manifest; no AI image generation"
    print(f"Topic: {topic}", flush=True)

    story_path = OUT / f"storybook-science-story-{day}.json"
    scene_dir = OUT / f"storybook-science-scenes-{day}"
    if scene_dir.exists():
        shutil.rmtree(scene_dir)
    image_dir = OUT / f"storybook-science-source-images-{day}"
    if image_dir.exists():
        shutil.rmtree(image_dir)

    # Search public-facing image pages and validate downloaded image files before rendering.
    download_scene_illustrations(story, image_dir)
    width, height = int(config.get("width", 1280)), int(config.get("height", 720))
    rendered = asyncio.run(render_external_scenes(story, scene_dir, width, height))
    if len(rendered) != len(story["scenes"]):
        raise RuntimeError(f"Expected {len(story['scenes'])} rendered scenes, got {len(rendered)}.")
    hashes = {hashlib.sha256(path.read_bytes()).hexdigest() for path in rendered}
    if len(rendered) > 1 and len(hashes) < 2:
        raise RuntimeError("Rendered scenes are identical; refusing to assemble a single-image video.")
    tiny = [path.name for path in rendered if path.stat().st_size < 8000]
    if tiny:
        raise RuntimeError(f"Unexpectedly small scene images: {tiny}")
    story_path.write_text(json.dumps(story, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Rendered {len(rendered)} static illustrated scenes ({len(hashes)} distinct frames).", flush=True)

    narration = "\n\n".join(str(s.get("narration", "")).strip() for s in story["scenes"] if s.get("narration"))
    if not narration:
        raise RuntimeError("The story contains no narration.")
    narration_path = OUT / f"storybook-science-narration-{day}.mp3"
    make_voice(narration, narration_path, config)
    video_path = OUT / f"storybook-science-{day}.mp4"
    render_video(scene_dir, narration_path, video_path, story, config)
    print(f"Finished video: {video_path}", flush=True)

if __name__ == "__main__":
    main()
