#!/usr/bin/env python3
"""Independent Gemini planner for the Science Channel pipeline."""
import json, os, re, time, datetime, difflib
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = json.loads((ROOT / "settings.json").read_text())
API_KEY = os.environ["GEMINI_API_KEY"]
MODEL = os.getenv("GEMINI_MODEL") or SETTINGS["gemini_model"]
API = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
HISTORY = ROOT / "history/generated-topics.json"
TOPICS = ROOT / "topics.txt"
PRESENTER = (ROOT / "character/presenter-reference.md").read_text()
TODAY = datetime.date.today().isoformat()


def topic_slug(value):
    """Create a readable, filesystem-safe folder suffix from an episode topic."""
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug[:70].strip("-") or "untitled-topic"

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
seen_topics = list(history.get("topics",[]))
def is_duplicate_topic(candidate):
    key = re.sub(r"[^a-z0-9]+", " ", candidate.casefold()).strip()
    return any(
        key == re.sub(r"[^a-z0-9]+", " ", old.casefold()).strip()
        or difflib.SequenceMatcher(None, key, re.sub(r"[^a-z0-9]+", " ", old.casefold()).strip()).ratio() >= 0.88
        for old in seen_topics
    )
seed_topics = [x.strip() for x in TOPICS.read_text().splitlines() if x.strip() and not x.lstrip().startswith("#")]
topic_data = gemini("""Create exactly 3 distinct, compelling, accurate science-explainer topics for a general YouTube audience.
Avoid all previously used topics and close paraphrases. You may use these seed ideas but are not limited to them.
Return JSON only: {"topics":[{"title":"...","angle":"one-sentence distinctive angle"}]}.
Previously used topics: """ + json.dumps(history.get("topics",[])[-500:]) +
"\nSeed ideas: " + json.dumps(seed_topics))
topics = topic_data.get("topics",[])
if len(topics) != 3: raise ValueError(f"Expected exactly 3 topics, got {len(topics)}")
for idx, item in enumerate(topics,1):
    title = item["title"].strip()
    if is_duplicate_topic(title): raise ValueError("Gemini returned a duplicate or near-duplicate topic: "+title)
    # Stage 1: create the complete narration script and exactly 48 ordered scenes.
    script_prompt = f"""Write a complete 8–10 minute English science explainer episode titled {title!r}.
Angle: {item.get('angle','')}. Audience: curious general viewers. Scientifically accurate, engaging,
clear and conversational. Return JSON only with keys title, description, scenes.
scenes must contain EXACTLY 48 objects, each with scene_number (1..48), narration (spoken narration only,
about 20–30 words), and visual_beat (brief description of what the narration is showing).
Narration across all 48 scenes must form a coherent complete script of about 1,100–1,350 words.
No image prompt in this stage. Number scenes consecutively from 1 to 48."""
    episode = gemini(script_prompt,0.65)
    scenes = episode.get("scenes",[])
    if len(scenes) != 48 or [s.get("scene_number") for s in scenes] != list(range(1,49)):
        raise ValueError(f"Episode {idx}: script did not contain exactly 48 correctly numbered scenes")
    if any(not str(s.get("narration","")).strip() for s in scenes): raise ValueError("Empty narration scene")
    # Stage 2: derive prompts from the finalized narration; exact one-to-one scene mapping.
    prompt_data = gemini("""Create exactly 48 image prompts from this finalized 48-scene narration.
Do not rewrite, reorder, merge, or add scenes. Each prompt must depict its corresponding narration
and visual beat. Include the same recurring presenter identity in every prompt when he appears.
16:9 cinematic 3D family-animation aesthetic; no text, captions, logos or watermarks.
Return JSON only: {"prompts":[{"scene_number":1,"prompt":"..."}]}.
Presenter identity guide: """ + PRESENTER + "\nFinal script scenes: " + json.dumps(scenes,ensure_ascii=False),0.55)
    prompts = prompt_data.get("prompts",[])
    if len(prompts)!=48 or [p.get("scene_number") for p in prompts]!=list(range(1,49)):
        raise ValueError(f"Episode {idx}: expected exactly 48 ordered image prompts")
    day_root = ROOT / "daily-episodes" / TODAY
    final_title = str(episode.get("title", title)).strip()
    folder = day_root / f"episode-{idx:03d}-{topic_slug(final_title)}"
    images = folder / "images" / "incoming"
    images.mkdir(parents=True,exist_ok=True)
    (folder/"episode.json").write_text(json.dumps({"episode_id":f"{TODAY}-episode-{idx:03d}","date":TODAY,"title":final_title,"description":episode.get("description",""),"scene_count":48,"target_minutes":"8-10","status":"awaiting_images"},indent=2,ensure_ascii=False)+"\n")
    script = [f"# {final_title}","",episode.get("description",""),""]
    for s in scenes: script += [f"## Scene {s['scene_number']:02d}","",s["narration"].strip(),""]
    (folder/"script.md").write_text("\n".join(script))
    (folder/"scenes.json").write_text(json.dumps(scenes,indent=2,ensure_ascii=False)+"\n")
    prompt_lines = [f"# Image prompts — {title}","", "Generate each image manually in Meta AI. Keep scene numbering unchanged.",""]
    for p in prompts: prompt_lines += [f"## Scene {p['scene_number']:02d}","",p["prompt"].strip(),""]
    (folder/"image-prompts.md").write_text("\n".join(prompt_lines))
    (folder/"README.md").write_text(
        f"# {final_title}\n\n- Episode: {idx:03d}\n- Date: {TODAY}\n"
        "- Scenes/images required: 48\n- Status: Awaiting images\n\n"
        "## Upload images\nUpload exactly 48 images into images/incoming/ using numbered names "
        "(scene-001.webp through scene-048.webp).\n\n"
        "## Package files\n- episode.json: metadata\n- script.md: narration\n"
        "- scenes.json: ordered scenes\n- image-prompts.md: image prompts\n"
    )
    (images/".gitkeep").write_text("")
    history.setdefault("topics",[]).append(final_title)
    seen_topics.append(final_title)
    print(f"Created {folder} with 48 narration scenes and 48 matching prompts; upload all 48 numbered images to images/incoming/")
HISTORY.parent.mkdir(parents=True,exist_ok=True)
HISTORY.write_text(json.dumps(history,indent=2,ensure_ascii=False)+"\n")
