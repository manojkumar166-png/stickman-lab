import os, json, random, time, requests
from pathlib import Path

MODEL_FALLBACKS = [
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.6-flash",
    "gemini-3.8-flash",
]

def _call_gemini(api_key, model, prompt, attempts=3):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.8},
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


def generate_story(root: Path, config: dict) -> dict:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Set GEMINI_API_KEY.")

    topics = [x.strip() for x in (root / "topics.txt").read_text(encoding="utf-8").splitlines() if x.strip()]
    history_path = root / config.get("topic_history_file", "topic_history.json")
    history = json.loads(history_path.read_text(encoding="utf-8")) if history_path.exists() else []
    
    if not topics:
        raise RuntimeError("topics.txt has no topics. Add at least one topic, one per line.")

    available = [t for t in topics if t not in history]
    # Never invent topics: when every listed topic has been used, reuse one from topics.txt.
    topic = random.choice(available if available else topics)
    if available:
        print(f"Selected topic from topics.txt: {topic}")
    else:
        print(f"All listed topics were used; reusing topic from topics.txt: {topic}")
    prompt_topic_instruction = f"""Use this exact topic from topics.txt: "{topic}".
Do not invent, replace, broaden, or rename the topic. The returned JSON "topic" must match it exactly."""

    prompt = f"""
Create an original, factually careful educational science explainer for a colorful stickman cartoon video.
{prompt_topic_instruction}
Target narration duration: about {config.get('target_minutes', 8)} minutes, approximately 1200-1350 spoken words.
Return ONLY valid JSON with this schema:
{{
 "topic": "a concise title",
 "description": "one sentence",
 "scenes": [
   {{
    "title": "short scene heading",
    "narration": "natural voiceover, about 28-32 words",
    "visual": "a detailed cinematic illustration brief: subject placement, foreground/midground/background, environment, lighting, color palette, focal point, scientific objects and their relationships; no written text in image",
    "background": "one of: sky, lab, space, ocean, forest, city, home, cave, desert, mountain",
    "action": "one of: explain, walk, point, run, think, surprised, celebrate, observe"
   }}
 ]
}}
Create exactly {config.get('scene_count', 48)} scenes. The total narration should be close to 8 minutes at 125-145 words per minute. Begin with a surprising hook, build curiosity, explain the science accurately in plain language, and end with a memorable takeaway. Avoid fabricated statistics, unsupported claims, medical advice, and repetitive filler. Use age-friendly language. Each narration must be a complete spoken paragraph and should be 28-32 words, not shorter. Visual descriptions must be rich, specific, and suitable for original hand-painted 2D storybook illustrations, not simple icon scenes. Describe a distinct composition for every scene, including the setting, scale, foreground details, background depth, lighting, mood, and exact scientific subject/action. Avoid repeating the same composition. Keep scientific structures plausible and explainable. No 3D/CGI look. Do not put text or labels inside scene images. JSON only, no Markdown fences.
"""

    preferred = config.get("gemini_model", "").strip()
    models = []
    if preferred:
        models.append(preferred)
    for m in MODEL_FALLBACKS:
        if m not in models:
            models.append(m)

    data = None
    used_model = None
    for model in models:
        print(f"Trying Gemini model: {model}")
        try:
            data = _call_gemini(api_key, model, prompt)
            used_model = model
            break
        except RuntimeError as e:
            print(f"  {model} failed: {str(e)[:200]}")
            continue
    if data is None:
        raise RuntimeError("All Gemini models failed. Check network/quota and retry later.")

    print(f"Story generated with {used_model}")

    try:
        raw = data["candidates"][0]["content"]["parts"][0]["text"]
        story = json.loads(raw)
    except Exception as e:
        raise RuntimeError(f"Could not parse AI story response: {e}; response was {str(data)[:1200]}")

    scenes = story.get("scenes", [])
    if not isinstance(scenes, list) or len(scenes) < 8:
        raise RuntimeError("AI returned too few scenes; rerun.")

    for s in scenes:
        for key in ("title", "narration", "visual", "background", "action"):
            if not isinstance(s.get(key), str) or not s[key].strip():
                s[key] = {
                    "title": "Science discovery",
                    "narration": "Let's explore this idea step by step.",
                    "visual": "A stickman points at a simple illustration",
                    "background": "lab",
                    "action": "point",
                }[key]

    # Enforce the selected topics.txt entry even if the model tries to rename it.
    story["topic"] = topic
    final_topic = topic
    history.append(final_topic)
    history_path.write_text(json.dumps(history[-100:], indent=2), encoding="utf-8")
    
    return story