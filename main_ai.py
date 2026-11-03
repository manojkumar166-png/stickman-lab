import os, sys, json, subprocess, shutil, asyncio, re
from pathlib import Path
from datetime import date
from scripts.generate_story import generate_story
from scripts.make_art import make_scene_art, generate_all_ai_images
from scripts.make_voice import make_voice
from scripts.render_video import render_video

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"
OUT.mkdir(exist_ok=True)

def main():
    if not shutil.which("ffmpeg"):
        raise RuntimeError("FFmpeg was not found.")
    
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    day = date.today().isoformat()
    # Any story restored from ai-image-progress represents a failed run.
    # Resume it even if all scene images were already generated (the failure
    # may have happened during voice, rendering, subtitles, or upload).
    pending_story = None
    for candidate in sorted(OUT.glob("story-*.json"), reverse=True):
        candidate_day = candidate.stem.removeprefix("story-")
        try:
            candidate_story = json.loads(candidate.read_text(encoding="utf-8"))
            saved_scenes = candidate_story.get("scenes")
            if (
                isinstance(saved_scenes, list)
                and len(saved_scenes) == int(config["scene_count"])
                and candidate_story.get("completed") is not True
            ):
                pending_story = (candidate, candidate_story, candidate_day)
                break
            if isinstance(saved_scenes, list) and len(saved_scenes) != int(config["scene_count"]):
                print(
                    f"Skipping checkpoint {candidate.name}: it has {len(saved_scenes)} scenes, "
                    f"but the current target is {config['scene_count']}.",
                    flush=True,
                )
        except Exception:
            continue
    if pending_story:
        story_path, story, scene_day = pending_story
        # Refresh the checkpoint timestamp so downstream workflow steps select
        # this resumed story rather than an older completed story in the folder.
        story_path.touch()
        print(f"Resuming saved failed-run story from {scene_day}.")
    else:
        # A successful run is marked completed by the workflow only after
        # Telegram delivery and topic-history publication. If another run is
        # started on the same date, give it a fresh story/image checkpoint so
        # it cannot accidentally reuse the previous run's scene images.
        run_number = 1
        story_path = OUT / f"story-{day}.json"
        while story_path.exists():
            run_number += 1
            story_path = OUT / f"story-{day}-{run_number}.json"
        scene_day = day if run_number == 1 else f"{day}-{run_number}"

    if not os.getenv("GEMINI_API_KEY"):
        raise RuntimeError("GEMINI_API_KEY is missing.")

    if not pending_story:
        story = generate_story(ROOT, config)
        story["completed"] = False
        temporary_story = story_path.with_name(story_path.name + ".tmp")
        temporary_story.write_text(
            json.dumps(story, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary_story, story_path)
    else:
        print(f"Resuming saved story: {story.get('topic', 'untitled')}")
    print(f"Topic: {story['topic']}")

    print(f"Generating AI scene artwork ({len(story['scenes'])} scenes)...", flush=True)
    scene_dir = OUT / f"scenes-{scene_day}"
    scene_dir.mkdir(parents=True, exist_ok=True)

    # Force AI generation for this experiment
    ai_images = {}
    images_data = asyncio.run(generate_all_ai_images(story["scenes"], scene_dir, config["width"], config["height"], story_path=story_path))
    for i, img_data in images_data:
        ai_images[i] = img_data

    for i, scene in enumerate(story["scenes"], 1):
        make_scene_art(scene, i, len(story["scenes"]), scene_dir / f"scene-{i:03d}.png",
                       config["width"], config["height"], ai_image_data=ai_images.get(i))

    print("All scene images are prepared. Starting narration generation...", flush=True)
    narration = "\n\n".join(s["narration"].strip() for s in story["scenes"])
    narration_path = OUT / f"narration-{day}.mp3"
    make_voice(narration, narration_path, config)

    dur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(narration_path)],
        capture_output=True, text=True).stdout)
    print(f"Narration length: {dur/60:.1f} min")

    topic_slug = re.sub(r"[^a-z0-9]+", "-", story["topic"].lower()).strip("-")[:80].strip("-") or "science-video"
    video_path = OUT / f"{topic_slug}-{day}.mp4"
    print("Narration is ready. Starting FFmpeg video rendering...", flush=True)
    render_video(scene_dir, narration_path, video_path, story, config)

    print(f"Finished: {video_path}")

if __name__ == "__main__":
    main()