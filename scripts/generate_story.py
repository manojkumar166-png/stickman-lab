import os, json, random, time, re
from difflib import SequenceMatcher
from pathlib import Path

import requests

MODEL_FALLBACKS = [
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.6-flash",
    "gemini-3.8-flash",
]

# Broad categories are deliberately mixed so consecutive videos explore
# different areas of science while keeping the simple question-led style.
TOPIC_CATEGORIES = [
    "space and astronomy",
    "Earth, oceans and weather",
    "animals and nature",
    "plants and ecosystems",
    "human body and senses",
    "brain, memory and behavior",
    "physics, forces and motion",
    "light, sound and color",
    "chemistry and everyday materials",
    "technology and engineering",
    "time, energy and the universe",
]


def _call_gemini(api_key, model, prompt, attempts=3):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.9},
    }
    last_err = None
    for attempt in range(attempts):
        try:
            r = requests.post(url, params={"key": api_key}, json=body, timeout=180)
        except requests.RequestException as e:
            last_err = f"network error: {e}"
            time.sleep(2 ** attempt)
            continue
        if r.status_code == 200:
            return r.json()
        if r.status_code in (429, 500, 502, 503, 504):
            last_err = f"{r.status_code}: {r.text[:300]}"
            wait = 2 ** attempt
            print(f"  {model} -> {r.status_code}, retrying in {wait}s...")
            time.sleep(wait)
            continue
        raise RuntimeError(f"Gemini API error {r.status_code} on {model}: {r.text[:1000]}")
    raise RuntimeError(f"Gemini API gave up on {model} after {attempts} tries: {last_err}")



def _repair_missing_scenes(api_key, model, story, desired_count):
    """Ask Gemini to continue a short story instead of discarding a nearly complete response."""
    scenes = story.get("scenes")
    if not isinstance(scenes, list):
        return False
    if len(scenes) > desired_count:
        story["scenes"] = scenes[:desired_count]
        return True

    for repair_attempt in range(1, 4):
        missing = desired_count - len(scenes)
        if missing <= 0:
            return True
        prompt = f"""
Continue this educational science explainer as a seamless continuation.
Topic: {story.get("topic", "")}
Description: {story.get("description", "")}
The story currently has {len(scenes)} scenes and needs exactly {missing} additional scenes.
The final existing scenes are:
{json.dumps(scenes[-5:], ensure_ascii=False)}
Return ONLY valid JSON in this shape: {{"scenes":[{{"title":"short heading","narration":"28-32 spoken words","visual":"drawable cartoon scene without text","background":"sky, lab, space, ocean, forest, city, home, cave, desert, or mountain","action":"explain, walk, point, run, think, surprised, celebrate, observe"}}]}}
Return exactly {missing} new scenes. Do not repeat earlier explanations. Keep the narration factually careful and make the final added scene a memorable conclusion.
"""
        try:
            data = _call_gemini(api_key, model, prompt)
            raw = data["candidates"][0]["content"]["parts"][0]["text"]
            addition = json.loads(raw)
            new_scenes = addition.get("scenes", []) if isinstance(addition, dict) else addition
            if not isinstance(new_scenes, list) or not new_scenes:
                raise ValueError("repair response contained no scene list")
            accepted = [item for item in new_scenes if isinstance(item, dict)]
            scenes.extend(accepted[:missing])
            story["scenes"] = scenes
            print(f"Scene-count repair {repair_attempt}/3 added {min(len(accepted), missing)} scenes; {len(scenes)}/{desired_count} now available.", flush=True)
        except Exception as exc:
            print(f"Scene-count repair {repair_attempt}/3 failed: {exc}", flush=True)
            time.sleep(repair_attempt * 2)
    return len(story.get("scenes", [])) == desired_count

def _normalise_topic(value):
    value = re.sub(r"[^a-z0-9 ]+", " ", str(value).lower())
    return " ".join(value.split())


def _is_repeat(candidate, history):
    candidate_norm = _normalise_topic(candidate)
    if not candidate_norm:
        return True
    candidate_words = set(candidate_norm.split())
    for previous in history:
        previous_norm = _normalise_topic(previous)
        if not previous_norm:
            continue
        if candidate_norm == previous_norm:
            return True
        if SequenceMatcher(None, candidate_norm, previous_norm).ratio() >= 0.88:
            return True
        previous_words = set(previous_norm.split())
        union = candidate_words | previous_words
        if union and len(candidate_words & previous_words) / len(union) >= 0.78:
            return True
    return False


def _read_history(path):
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [str(item).strip() for item in data if str(item).strip()]
        print("Topic history has an unexpected format; starting with an empty history.")
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not safely read topic history at {path}: {exc}") from exc
    return []


def generate_story(root: Path, config: dict) -> dict:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Set GEMINI_API_KEY.")

    topics_path = root / "topics.txt"
    if not topics_path.is_file():
        raise RuntimeError(f"Topic reference file is missing: {topics_path}")
    topics = [
        line.strip() for line in topics_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not topics:
        raise RuntimeError("topics.txt has no usable example topics.")

    history_path = root / config.get("topic_history_file", "topic_history.json")
    history = _read_history(history_path)
    # Seed examples are style references, not a fixed queue. Never deliberately
    # reuse one if it already appears in the published topic history.
    examples = "\n".join(f"- {topic}" for topic in topics)
    recent_history = history[-150:]
    models = []
    preferred = config.get("gemini_model", "").strip()
    if preferred:
        models.append(preferred)
    for model in MODEL_FALLBACKS:
        if model not in models:
            models.append(model)

    data = None
    used_model = None
    story = None
    last_duplicate = None
    last_scene_count = None
    desired_scene_count = int(config.get("scene_count", 48))

    # Each retry selects a fresh category and asks Gemini for a different
    # question. This avoids a fixed topic rotation and rejects repeated titles.
    for generation_attempt in range(5):
        category = random.choice(TOPIC_CATEGORIES)
        print(f"Random science category ({generation_attempt + 1}/5): {category}")
        prompt = f"""
Create an original, factually careful educational science explainer for a colorful stickman cartoon video.

TOPIC STYLE REFERENCE — read these examples from the repository's topics.txt:
{examples}

Choose ONE fresh, specific science question in this randomly selected category: {category}.
Use topics.txt only as a guide to its simple, curiosity-driven question style and broad variety.
Do not simply copy a seed topic or make a minor wording change to one.
Generate a different subject/question each time, drawing from the selected category.
Do NOT repeat or closely rephrase any previously used topic in this history:
{json.dumps(recent_history, ensure_ascii=False)}

The title must be a concise natural question in the same approachable style as the examples.
Return the selected topic in the JSON "topic" field and make the entire explainer answer that exact question.

Target narration duration: about {config.get('target_minutes', 8)} minutes, approximately 1200-1350 spoken words.
Return ONLY valid JSON with this schema:
{{
 "topic": "a concise title",
 "description": "one sentence",
 "scenes": [
   {{
    "title": "short scene heading",
    "narration": "natural voiceover, about 28-32 words",
    "visual": "a concrete, drawable scene description, no written text in image",
    "background": "one of: sky, lab, space, ocean, forest, city, home, cave, desert, mountain",
    "action": "one of: explain, walk, point, run, think, surprised, celebrate, observe"
   }}
 ]
}}
Create exactly {config.get('scene_count', 48)} scenes. The total narration should be close to 8 minutes at 125-145 words per minute. Begin with a surprising hook, build curiosity, explain the science accurately in plain language, and end with a memorable takeaway. Avoid fabricated statistics, unsupported claims, medical advice, and repetitive filler. Use age-friendly language. Each narration must be a complete spoken paragraph and should be 28-32 words, not shorter. Make visual descriptions easy to illustrate with simple cartoon shapes. Do not put text or labels inside scene images. JSON only, no Markdown fences.
"""

        data = None
        for model in models:
            print(f"Trying Gemini model: {model}")
            try:
                data = _call_gemini(api_key, model, prompt)
                used_model = model
                break
            except RuntimeError as exc:
                print(f"  {model} failed: {str(exc)[:200]}")
        if data is None:
            raise RuntimeError("All Gemini models failed. Check network/quota and retry later.")

        try:
            raw = data["candidates"][0]["content"]["parts"][0]["text"]
            candidate_story = json.loads(raw)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Could not parse AI story response: {exc}; response was {str(data)[:1200]}") from exc

        returned_scenes = candidate_story.get("scenes", [])
        if not isinstance(returned_scenes, list):
            last_scene_count = "invalid"
            print("Gemini returned an invalid scenes field; requesting a fresh story.", flush=True)
            continue
        if len(returned_scenes) != desired_scene_count:
            actual_count = len(returned_scenes)
            print(f"Gemini returned {actual_count} scenes; repairing to exactly {desired_scene_count}.", flush=True)
            if not _repair_missing_scenes(api_key, used_model, candidate_story, desired_scene_count):
                last_scene_count = len(candidate_story.get("scenes", []))
                print("Could not repair this story's scene count; requesting a fresh story.", flush=True)
                continue
            returned_scenes = candidate_story["scenes"]
        last_scene_count = None

        candidate_topic = str(candidate_story.get("topic", "")).strip()
        if _is_repeat(candidate_topic, history):
            last_duplicate = candidate_topic or "(empty title)"
            print(f"Gemini returned a repeated/too-similar topic: {last_duplicate!r}; choosing another category.")
            recent_history = history[-150:] + ([last_duplicate] if last_duplicate else [])
            continue
        story = candidate_story
        break

    if story is None:
        if last_scene_count is not None:
            raise RuntimeError(
                f"Gemini could not produce exactly {desired_scene_count} scenes after 5 story attempts "
                f"(last response contained {last_scene_count}). No story or topic history was saved; rerun to try again."
            )
        raise RuntimeError(
            "Gemini could not produce a sufficiently new topic after 5 category attempts. "
            f"Last rejected topic: {last_duplicate!r}. No history was changed; rerun to try again."
        )

    print(f"Story generated with {used_model}: {story['topic']}")
    scenes = story.get("scenes", [])
    if not isinstance(scenes, list) or len(scenes) < 8:
        raise RuntimeError("AI returned too few scenes; rerun.")

    for scene in scenes:
        if not isinstance(scene, dict):
            raise RuntimeError("AI returned a malformed scene; rerun.")
        defaults = {
            "title": "Science discovery",
            "narration": "Let's explore this idea step by step.",
            "visual": "A stickman points at a simple illustration",
            "background": "lab",
            "action": "point",
        }
        for key, fallback in defaults.items():
            if not isinstance(scene.get(key), str) or not scene[key].strip():
                scene[key] = fallback

    final_topic = str(story.get("topic", "")).strip()
    if not final_topic or _is_repeat(final_topic, history):
        raise RuntimeError("Generated topic is empty or duplicates history; refusing to save it.")

    # Topic history is published by the workflow only after the video and
    # subtitles have been generated successfully. A failed/incomplete run
    # must remain eligible for retry without consuming its topic.
    return story
