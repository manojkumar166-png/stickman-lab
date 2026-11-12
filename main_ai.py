import os, json, subprocess, shutil, asyncio, re
from pathlib import Path
from datetime import date
from scripts.generate_story import generate_story
from scripts.make_art import make_scene_art, generate_all_ai_images
from scripts.make_voice import make_voice
from scripts.render_video import render_video

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"
OUT.mkdir(exist_ok=True)


def valid_media(path, minimum_size):
    if not path.is_file() or path.stat().st_size < minimum_size:
        return False
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True
    )
    if probe.returncode != 0:
        return False
    try:
        return float(probe.stdout.strip()) > 0
    except (TypeError, ValueError):
        return False


def main():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("FFmpeg and ffprobe are required.")

    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    today = date.today().isoformat()

    # A failed run is identified by its saved, incomplete story JSON. The
    # workflow restores output/ from ai-image-progress before this script runs.
    pending = []
    for candidate in OUT.glob("story-*.json"):
        try:
            saved = json.loads(candidate.read_text(encoding="utf-8"))
            scenes = saved.get("scenes")
            if isinstance(scenes, list) and len(scenes) == int(config["scene_count"]) and saved.get("completed") is not True:
                pending.append((candidate.stat().st_mtime_ns, candidate, saved))
        except Exception:
            continue

    if pending:
        _, story_path, story = max(pending, key=lambda item: item[0])
        run_key = story_path.stem.removeprefix("story-")
        print(f"Resuming saved pipeline checkpoint: {story_path.name}", flush=True)
    else:
        run_key = today
        story_path = OUT / f"story-{run_key}.json"
        suffix = 1
        while story_path.exists():
            suffix += 1
            run_key = f"{today}-{suffix}"
            story_path = OUT / f"story-{run_key}.json"
        story = generate_story(ROOT, config)
        story["completed"] = False
        temporary_story = story_path.with_name(story_path.name + ".tmp")
        temporary_story.write_text(json.dumps(story, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary_story, story_path)
        print(f"Saved new story checkpoint: {story_path.name}", flush=True)

    print(f"Topic: {story['topic']}", flush=True)
    scene_dir = OUT / f"scenes-{run_key}"
    scene_dir.mkdir(parents=True, exist_ok=True)

    images_data = asyncio.run(
        generate_all_ai_images(
            story["scenes"], scene_dir, config["width"], config["height"], story_path=story_path
        )
    )
    ai_images = {index: image_data for index, image_data in images_data}

    # Do not rewrite valid scene files on a resumed run.
    for index, scene in enumerate(story["scenes"], 1):
        scene_file = scene_dir / f"scene-{index:03d}.png"
        if scene_file.is_file() and scene_file.stat().st_size > 1000:
            try:
                from PIL import Image
                with Image.open(scene_file) as image:
                    image.verify()
                continue
            except Exception:
                scene_file.unlink(missing_ok=True)
        make_scene_art(
            scene, index, len(story["scenes"]), scene_file,
            config["width"], config["height"], ai_image_data=ai_images.get(index)
        )

    narration_path = OUT / f"narration-{run_key}.mp3"
    narration_text = "\n\n".join(scene["narration"].strip() for scene in story["scenes"])
    if valid_media(narration_path, 1000):
        print(f"Reusing completed narration checkpoint: {narration_path.name}", flush=True)
    else:
        print("Generating narration; previous story and images are preserved.", flush=True)
        make_voice(narration_text, narration_path, config)
        if not valid_media(narration_path, 1000):
            raise RuntimeError("Narration stage did not produce a valid MP3.")

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(narration_path)],
        capture_output=True, text=True, check=True
    )
    duration = float(probe.stdout.strip())
    print(f"Narration length: {duration / 60:.1f} min", flush=True)

    topic_slug = re.sub(r"[^a-z0-9]+", "-", story["topic"].lower()).strip("-")[:80].strip("-") or "science-video"
    video_path = OUT / f"{topic_slug}-{run_key}.mp4"
    if valid_media(video_path, 100000):
        print(f"Reusing completed render checkpoint: {video_path.name}", flush=True)
    else:
        print("Rendering video; previous story, images and narration are preserved.", flush=True)
        render_video(scene_dir, narration_path, video_path, story, config)
        if not valid_media(video_path, 100000):
            raise RuntimeError("Video-render stage did not produce a valid MP4.")

    print(f"PIPELINE_VIDEO={video_path}", flush=True)
    print(f"PIPELINE_RUN_KEY={run_key}", flush=True)
    print(f"Finished or resumed pipeline: {video_path}", flush=True)


if __name__ == "__main__":
    main()
