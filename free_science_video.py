import json
import os
import shutil
from datetime import date
from pathlib import Path

from scripts.generate_story import generate_story
from scripts.make_voice import make_voice
from scripts.free_visuals import choose_style, prepare_scene
from scripts.free_ai_art import generate_ai_images, save_ai_image
from scripts.render_video import render_video

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"

def main():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("FFmpeg and ffprobe must be installed.")
    if not os.getenv("GEMINI_API_KEY"):
        raise RuntimeError("GEMINI_API_KEY is missing. Add it as a GitHub Actions secret.")

    OUT.mkdir(exist_ok=True)
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    # Isolate this workflow's topic history from the existing workflows.
    free_config = dict(config)
    free_config["topic_history_file"] = "free_topic_history.json"
    story = generate_story(ROOT, free_config)
    if not isinstance(story, dict) or not story.get("scenes"):
        raise RuntimeError("Story generator returned no scenes.")

    day = date.today().isoformat()
    topic = str(story.get("topic", "Science discovery"))
    style = choose_style(topic)
    story["visual_style"] = style
    print(f"Topic: {topic}")
    print(f"Visual style for the entire video: {style}")

    story_path = OUT / f"free-science-story-{day}.json"
    story_path.write_text(json.dumps(story, ensure_ascii=False, indent=2), encoding="utf-8")

    scene_dir = OUT / f"free-science-scenes-{day}"
    if scene_dir.exists():
        shutil.rmtree(scene_dir)
    scene_dir.mkdir(parents=True)

    width, height = int(config.get("width", 1280)), int(config.get("height", 720))
    # Use the same free-tier Cloudflare image provider already used by the other
    # experimental generator, when its existing secrets are configured. If the
    # provider/quota is unavailable, each scene falls back independently.
    ai_images = generate_ai_images(story["scenes"], width, height, workers=3)
    credits = []
    for i, scene in enumerate(story["scenes"], 1):
        image_path = scene_dir / f"scene-{i:03d}.png"
        image_bytes = ai_images.get(i)
        if image_bytes:
            try:
                credit = save_ai_image(image_bytes, scene, image_path, width, height)
                credit["scene"] = i
            except Exception as exc:
                print(f"Could not process AI image for scene {i}: {exc}; using fallback.", flush=True)
                credit = prepare_scene(scene, topic, style, image_path, width, height, i)
        else:
            credit = prepare_scene(scene, topic, style, image_path, width, height, i)
        credits.append(credit)
        print(f"Prepared scene {i}/{len(story['scenes'])}: {credit['title']}", flush=True)

    credits_path = OUT / f"free-science-image-credits-{day}.json"
    credits_path.write_text(json.dumps(credits, ensure_ascii=False, indent=2), encoding="utf-8")

    narration = "\n\n".join(str(s.get("narration", "")).strip() for s in story["scenes"] if s.get("narration"))
    if not narration:
        raise RuntimeError("The story contains no narration.")
    narration_path = OUT / f"free-science-narration-{day}.mp3"
    print("Generating narration audio...", flush=True)
    make_voice(narration, narration_path, config)
    print(f"Narration ready: {narration_path}", flush=True)

    video_path = OUT / f"free-science-{day}.mp4"
    print(f"Rendering {len(story['scenes'])} scenes with the same FFmpeg renderer as the faster workflows...", flush=True)
    render_video(scene_dir, narration_path, video_path, story, config)
    print(f"Finished video: {video_path}")
    print(f"Style: {style}")
    print(f"Image source/license report: {credits_path}")

if __name__ == "__main__":
    main()
