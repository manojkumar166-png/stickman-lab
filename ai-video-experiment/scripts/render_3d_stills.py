"""Run the Blender still renderer once for all scenes, with a free Pillow fallback."""
import json
import shutil
import subprocess
from pathlib import Path

from scripts.free_visuals import choose_style, prepare_scene

def render_3d_stills(story, scene_dir, width, height):
    scene_dir = Path(scene_dir)
    blender = shutil.which("blender")
    scenes = story.get("scenes", [])
    topic = str(story.get("topic", "Science discovery"))
    style = str(story.get("visual_style") or choose_style(topic))
    if blender:
        story_file = scene_dir / "story-for-blender.json"
        story_file.write_text(json.dumps(story, ensure_ascii=False), encoding="utf-8")
        script = Path(__file__).with_name("blender_science_stills.py")
        command = [
            blender, "--background", "--factory-startup",
            "--python", str(script), "--",
            str(story_file), str(scene_dir), str(int(width)), str(int(height)),
        ]
        print("Rendering static 3D science stills in one Blender process (no zoom or animation)...", flush=True)
        result = subprocess.run(command, text=True, stdout=None, stderr=None)
        if result.returncode == 0:
            credits = []
            for i, scene in enumerate(scenes, 1):
                image = scene_dir / f"scene-{i:03d}.png"
                if not image.exists() or image.stat().st_size < 1000:
                    raise RuntimeError(f"Blender did not produce a valid image for scene {i}")
                credits.append({
                    "scene": i,
                    "scene_title": str(scene.get("title") or topic),
                    "style": "Locally rendered 3D CGI still",
                    "title": "Original Blender-generated 3D science scene",
                    "url": "",
                    "source_url": "",
                    "license": "Original procedural geometry rendered with Blender",
                    "artist": "Workflow-generated with Blender Python API",
                    "description": "Static 3D scene assembled from scene-title and narration keywords; no external image API.",
                })
            try:
                story_file.unlink()
            except OSError:
                pass
            return credits
        print("Blender renderer failed; falling back to the existing free image pipeline.", flush=True)
    else:
        print("Blender is not installed; falling back to the existing free image pipeline.", flush=True)
    credits = []
    for i, scene in enumerate(scenes, 1):
        image_path = scene_dir / f"scene-{i:03d}.png"
        credits.append(prepare_scene(scene, topic, style, image_path, width, height, i))
    return credits
