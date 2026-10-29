"""Generate a science story video with hand-authored HTML/CSS/JS storybook scenes."""
import json, os, shutil
from datetime import date
from pathlib import Path
from scripts.generate_story import generate_story
from scripts.storybook_scene_renderer import render_scenes
from scripts.make_voice import make_voice
from scripts.render_video import render_video

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"output"

def main():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("FFmpeg and ffprobe must be installed.")
    if not os.getenv("GEMINI_API_KEY"):
        raise RuntimeError("GEMINI_API_KEY is missing (used for story text only, never image generation).")
    OUT.mkdir(exist_ok=True)
    config=json.loads((ROOT/"config.json").read_text(encoding="utf-8"))
    workflow_config=dict(config)
    workflow_config["topic_history_file"]=os.getenv("TOPIC_HISTORY_FILE","storybook_topic_history.json")
    story=generate_story(ROOT,workflow_config)
    if not isinstance(story,dict) or not story.get("scenes"):
        raise RuntimeError("Story generator returned no scenes.")
    day=date.today().isoformat()
    topic=str(story.get("topic","Science discovery"))
    story["visual_style"]="hand-authored Ghibli-inspired storybook atmosphere; HTML/CSS/JavaScript; no AI-generated images"
    print(f"Topic: {topic}",flush=True)
    story_path=OUT/f"storybook-science-story-{day}.json"
    story_path.write_text(json.dumps(story,ensure_ascii=False,indent=2),encoding="utf-8")
    scene_dir=OUT/f"storybook-science-scenes-{day}"
    if scene_dir.exists(): shutil.rmtree(scene_dir)
    width,height=int(config.get("width",1280)),int(config.get("height",720))
    rendered=__import__("asyncio").run(render_scenes(story,scene_dir,width,height))
    if len(rendered)!=len(story["scenes"]):
        raise RuntimeError(f"Expected {len(story['scenes'])} rendered scenes, got {len(rendered)}.")
    narration="\n\n".join(str(s.get("narration","")).strip() for s in story["scenes"] if s.get("narration"))
    if not narration: raise RuntimeError("The story contains no narration.")
    narration_path=OUT/f"storybook-science-narration-{day}.mp3"
    make_voice(narration,narration_path,config)
    video_path=OUT/f"storybook-science-{day}.mp4"
    render_video(scene_dir,narration_path,video_path,story,config)
    print(f"Finished video: {video_path}",flush=True)

if __name__=="__main__": main()
