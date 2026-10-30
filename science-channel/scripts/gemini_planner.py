#!/usr/bin/env python3
"""Independent Gemini planner for the Science Channel pipeline."""
import json, os, re, time, datetime
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = json.loads((ROOT / "settings.json").read_text())
API_KEY = os.environ["GEMINI_API_KEY"]
MODEL = os.getenv("GEMINI_MODEL") or SETTINGS["gemini_model"]
API = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
HISTORY = ROOT / "history/generated-topics.json"
TOPICS = ROOT / "topics.txt"
TODAY = datetime.date.today().isoformat()

def gemini(prompt, temperature=0.7):
    payload = {"contents":[{"parts":[{"text":prompt}]}],
               "generationConfig":{"temperature":temperature,"responseMimeType":"application/json"}}
    for attempt in range(5):
        r = requests.post(API, params={"key":API_KEY}, json=payload, timeout=180)
        if r.ok:
            data = r.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(re.sub(r"^\s*```json|\s*```$", "", text.strip()))
        if r.status_code not in (429,500,502,503): r.raise_for_status()
        time.sleep(3 * (attempt + 1))
    r.raise_for_status()

history = json.loads(HISTORY.read_text()) if HISTORY.exists() else {"topics":[]}
# Also recover topics from existing episode packages, so an interrupted run cannot
# cause an already-created topic to be selected again.
used_topics = list(history.get("topics", []))
episode_root = ROOT / "daily-episodes"
if episode_root.exists():
    for metadata in episode_root.glob("*/episode-*/episode.json"):
        try:
            saved = json.loads(metadata.read_text())
            if saved.get("title"):
                used_topics.append(saved["title"])
        except (OSError, json.JSONDecodeError):
            continue

def topic_key(value):
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()

seen = {topic_key(x) for x in used_topics if x.strip()}
seed_topics = [x.strip() for x in TOPICS.read_text().splitlines() if x.strip() and not x.lstrip().startswith("#")]

# One planner run selects exactly ONE new topic. Retry if Gemini suggests a
# previously used title or returns a duplicate/near-identical normalized title.
topic = None
for attempt in range(5):
    topic_data = gemini("""Choose exactly ONE fresh, compelling, scientifically accurate YouTube science-explainer topic.
It must be clearly different from every previously used topic; do not rephrase or narrow an old topic.
Return JSON only: {"title":"...","angle":"one-sentence distinctive angle"}.
Previously used topics (never repeat these): """ + json.dumps(used_topics[-1000:], ensure_ascii=False) +
"\nSeed ideas (optional inspiration): " + json.dumps(seed_topics, ensure_ascii=False), 0.7)
    candidate = topic_data.get("title", "").strip()
    if candidate and topic_key(candidate) not in seen:
        topic = {"title": candidate, "angle": topic_data.get("angle", "")}
        break
if topic is None:
    raise RuntimeError("Gemini did not provide a new unused topic after 5 attempts; no episode was created.")

title = topic["title"]
# Use the next available episode number for today; never overwrite an earlier run.
day_root = episode_root / TODAY
day_root.mkdir(parents=True, exist_ok=True)
existing_numbers = []
for path in day_root.glob("episode-*"):
    match = re.fullmatch(r"episode-(\d+)", path.name)
    if match:
        existing_numbers.append(int(match.group(1)))
episode_number = max(existing_numbers, default=0) + 1

# Create the complete narration script and exactly 48 ordered scenes.
script_prompt = f"""Write a complete 8–10 minute English science explainer episode titled {title!r}.
Angle: {topic.get('angle','')}. Audience: curious general viewers. Scientifically accurate, engaging,
clear and conversational. Return JSON only with keys title, description, scenes.
scenes must contain EXACTLY 48 objects, each with scene_number (1..48), narration (spoken narration only,
about 20–30 words), and visual_beat (brief description of what the narration is showing).
Narration across all 48 scenes must form a coherent complete script of about 1,100–1,350 words.
No image prompt in this stage. Number scenes consecutively from 1 to 48."""
episode = gemini(script_prompt, 0.65)
scenes = episode.get("scenes", [])
if len(scenes) != 48 or [s.get("scene_number") for s in scenes] != list(range(1,49)):
    raise ValueError("Script did not contain exactly 48 correctly numbered scenes")
if any(not str(s.get("narration", "")).strip() for s in scenes):
    raise ValueError("Empty narration scene")

# Derive exactly one image prompt from each finalized narration scene.
prompt_data = gemini("""Create exactly 48 image prompts from this finalized 48-scene narration.
Do not rewrite, reorder, merge, or add scenes. Each prompt must depict its corresponding narration
and visual beat as a cinematic visual, not as a person explaining the narration.
IMPORTANT: Do NOT add a presenter, host, narrator, teacher, spokesperson, talking-head character,
or recurring man/person by default. Do not show anyone facing the camera and explaining the topic.
Do not include the presenter-reference character. There is no on-screen explainer.
Show the actual subject, scientific concept, action, environment, objects, or visual metaphor
described by that specific scene. Human figures are allowed only when the scene itself calls for
a person or when a human figure is essential to communicate the visual idea; in that case, show
them participating in the scene rather than presenting or explaining to the viewer.
For example, a scene about flying in dreams should show a human figure soaring through dreamlike
clouds and skies, not a man standing and explaining dreams.
Keep all 48 images visually varied and specific to their own scene; do not force a character into
scenes that do not need one.
COPYRIGHT-SAFETY RULES — apply these to EVERY one of the 48 prompts:
- Create a genuinely original scientific illustration from the scene description. Use original compositions,
  visual metaphors, object arrangements, environments, lighting and details.
- Do NOT imitate or request the style of Disney, Pixar, Marvel, any other studio/franchise, a famous artist,
  a living artist, or any identifiable illustrator. Use only a broad, generic visual description.
- Do NOT include copyrighted characters, franchise-specific designs, recognizable branded mascots,
  company logos, trademarks, or watermarks.
- Do NOT recreate, trace, closely copy, or make a variation of an existing online image, artwork,
  thumbnail, poster, book illustration, or another creator's work. Do not use image URLs or references
  as a source to reproduce.
- If a scene concept risks resembling a protected character or recognizable artwork, redesign it as
  an original generic scientific visualization while preserving the scientific meaning.
- Do not claim that an image is guaranteed copyright-free or legally cleared. These prompt rules reduce
  avoidable similarity risks but cannot guarantee that a generated result will never receive a claim.
Use an original cinematic 3D scientific-illustration aesthetic, composed for a 1920x1080 landscape frame.
Do not emulate any particular animation studio, franchise or artist.
Generate each image in WebP when the image tool supports it, because WebP usually gives an excellent
quality-to-file-size balance. Otherwise use any available format supported by the renderer: PNG, JPG/JPEG,
BMP, GIF, TIF or TIFF. Do not require JPG/JPEG and do not sacrifice visual quality just to meet a file-size
target. **Image file-size target: 500 KB–2 MB per image.** If the image tool offers format,
quality or compression controls, use settings that stay in this range while preserving fine scientific
details. Treat this as a target, not a hard limit; never make an image visibly worse just to hit it.
Avoid unnecessarily huge textures or empty high-detail backgrounds. Keep the full visual readable at 1920x1080.
No text, captions, logos or watermarks. The optional image-preparation utility can resize and convert
supported source images to numbered JPGs for smaller browser uploads; conversion is not required.
Return JSON only: {"prompts":[{"scene_number":1,"prompt":"..."}]}.
Final script scenes: """ + json.dumps(scenes, ensure_ascii=False), 0.55)
prompts = prompt_data.get("prompts", [])
if len(prompts) != 48 or [p.get("scene_number") for p in prompts] != list(range(1,49)):
    raise ValueError("Expected exactly 48 ordered image prompts")

folder = day_root / f"episode-{episode_number:03d}"
images = folder / "images" / "incoming"
images.mkdir(parents=True, exist_ok=False)
final_title = episode.get("title", title).strip()
(folder / "episode.json").write_text(json.dumps({
    "episode_id": f"{TODAY}-episode-{episode_number:03d}",
    "date": TODAY, "title": final_title,
    "description": episode.get("description", ""),
    "scene_count": 48, "target_minutes": "8-10",
    "status": "awaiting_images"
}, indent=2, ensure_ascii=False) + "\n")

script_lines = [f"# {final_title}", "", episode.get("description", ""), ""]
for scene in scenes:
    script_lines += [f"## Scene {scene['scene_number']:02d}", "", scene["narration"].strip(), ""]
(folder / "script.md").write_text("\n".join(script_lines))

(folder / "scenes.json").write_text(json.dumps(scenes, indent=2, ensure_ascii=False) + "\n")
prompt_lines = [f"# Image prompts — {final_title}", "",
                "Generate each image manually in Meta AI. Keep scene numbering unchanged.", ""]
for prompt in prompts:
    prompt_lines += [f"## Scene {prompt['scene_number']:02d}", "", prompt["prompt"].strip(), ""]
(folder / "image-prompts.md").write_text("\n".join(prompt_lines))
(images / ".gitkeep").write_text("")

# Persist the topic immediately after successfully creating its package.
history.setdefault("topics", []).append(final_title)
HISTORY.parent.mkdir(parents=True, exist_ok=True)
HISTORY.write_text(json.dumps(history, indent=2, ensure_ascii=False) + "\n")
print(f"Created ONE new topic: {final_title}")
print(f"Created {folder} with 48 narration scenes and 48 matching prompts; upload 48 images (one ZIP or 48 files) to images/incoming/")
