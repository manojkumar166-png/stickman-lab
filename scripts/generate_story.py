import os, json, random, time, re
from difflib import SequenceMatcher
from pathlib import Path

import requests

GROQ_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip()
KILO_MODEL = os.getenv("KILO_MODEL", "kilo-auto/free").strip()
KILO_FALLBACK_MODELS = [x.strip() for x in os.getenv("KILO_FALLBACK_MODELS", "nvidia/nemotron-3.5-super-vl:free,dots-studio/dots-3-note-preview:free,nvidia/nemotron-3-ultra-550b-a55b:free").split(",") if x.strip()]

class PermanentProviderError(RuntimeError):
    """A non-retryable provider response such as HTTP 400 or 404."""

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
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.9, "maxOutputTokens": 16000},
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



def _call_openai_compatible(provider, model, prompt, attempts=3):
    """Call an OpenAI-compatible inference endpoint with compatibility fallbacks."""
    if provider == "Groq":
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {GROQ_KEY}",
            "Content-Type": "application/json",
        }
        max_tokens = 16000
    elif provider == "Kilo":
        url = "https://ai-gateway.kilo.ai/api/v1/chat/completions"
        headers = {"Content-Type": "application/json"}
        max_tokens = 12000
    else:
        raise ValueError(f"Unsupported backup provider: {provider}")

    messages = [
        {
            "role": "system",
            "content": (
                "Return exactly one valid JSON object matching the requested schema. "
                "Do not use Markdown fences or add commentary."
            ),
        },
        {"role": "user", "content": prompt},
    ]
    base_body = {"model": model, "messages": messages}
    if provider == "Groq":
        full_body = {
            **base_body,
            "temperature": 0.8,
            "max_completion_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        request_bodies = [full_body]
    else:
        # Some free routed models reject optional sampling/token controls.
        # Retry one time with the strict minimum OpenAI-compatible payload.
        request_bodies = [
            {**base_body, "max_tokens": max_tokens},
            base_body,
        ]

    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            response = None
            for variant_index, body in enumerate(request_bodies):
                response = requests.post(
                    url,
                    headers=headers,
                    json=body,
                    timeout=(20, 240),
                )
                if response.status_code == 400 and variant_index + 1 < len(request_bodies):
                    print(
                        f"{provider} model {model} rejected optional parameters; "
                        "retrying with the minimal request body.",
                        flush=True,
                    )
                    continue
                if response.status_code in (408, 425, 429, 500, 502, 503, 504):
                    raise RuntimeError(
                        f"{provider} HTTP {response.status_code}: {response.text[:1200]}"
                    )
                if not response.ok:
                    error = (
                        f"{provider} HTTP {response.status_code}: "
                        f"{response.text[:1400]}"
                    )
                    if 400 <= response.status_code < 500:
                        raise PermanentProviderError(error)
                    raise RuntimeError(error)
                break

            if response is None:
                raise RuntimeError(f"{provider} returned no HTTP response.")
            choices = response.json().get("choices") or []
            message = choices[0].get("message", {}) if choices else {}
            content = message.get("content", "")
            if isinstance(content, list):
                content = "".join(
                    part.get("text", "")
                    for part in content
                    if isinstance(part, dict)
                )
            if not isinstance(content, str) or not content.strip():
                raise RuntimeError(f"{provider} returned an empty completion.")
            print(f"{provider} story planner active: {model}", flush=True)
            return {"candidates": [{"content": {"parts": [{"text": content}]}}]}
        except PermanentProviderError as exc:
            last_error = exc
            print(
                f"{provider} rejected model {model}; advancing to another model: {exc}",
                flush=True,
            )
            break
        except Exception as exc:
            last_error = exc
            print(
                f"{provider} planner attempt {attempt}/{attempts} failed: "
                f"{type(exc).__name__}: {exc}",
                flush=True,
            )
            if attempt < attempts:
                time.sleep(min(30, attempt * 7))
    raise RuntimeError(
        f"{provider} failed after {attempts} attempts: {last_error}"
    ) from last_error


def _call_story_model(api_key, model, prompt):
    """Call the selected provider again when a partial story needs repair."""
    if model.startswith("groq:"):
        return _call_openai_compatible("Groq", model.split(":", 1)[1], prompt)
    if model.startswith("kilo:"):
        return _call_openai_compatible("Kilo", model.split(":", 1)[1], prompt)
    return _call_gemini(api_key, model, prompt)


def _response_text(data):
    candidates = data.get("candidates") or []
    parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
    return "".join(part.get("text", "") for part in parts if isinstance(part, dict))


def _decode_json_object(raw):
    """Decode a JSON object even when a provider wraps it in a Markdown fence."""
    raw = str(raw or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        if raw.endswith("```"):
            raw = raw[:-3].strip()
    start = raw.find("{")
    if start < 0:
        raise ValueError("completion did not contain a JSON object")
    value, _ = json.JSONDecoder().raw_decode(raw, start)
    if not isinstance(value, dict):
        raise ValueError("completion JSON root was not an object")
    return value


def _parse_story_json(raw):
    """Parse a full story or salvage every complete scene from a truncated JSON reply."""
    try:
        return _decode_json_object(raw)
    except (ValueError, json.JSONDecodeError):
        decoder = json.JSONDecoder()
        text = str(raw or "")
        recovered = {}
        for field in ("topic", "description"):
            match = re.search(r'"' + field + r'"\s*:\s*', text)
            if match:
                try:
                    value, _ = decoder.raw_decode(text, match.end())
                    recovered[field] = value
                except (ValueError, json.JSONDecodeError):
                    pass

        scene_match = re.search(r'"scenes"\s*:\s*\[', text)
        if scene_match:
            cursor = scene_match.end()
            scenes = []
            while cursor < len(text):
                while cursor < len(text) and (text[cursor].isspace() or text[cursor] == ','):
                    cursor += 1
                if cursor >= len(text) or text[cursor] == ']':
                    break
                try:
                    item, next_cursor = decoder.raw_decode(text, cursor)
                except (ValueError, json.JSONDecodeError):
                    break
                if not isinstance(item, dict):
                    break
                scenes.append(item)
                cursor = next_cursor
            if scenes:
                recovered["scenes"] = scenes
                if recovered.get("topic"):
                    print(
                        f"Recovered {len(scenes)} complete scenes from a truncated model response; "
                        "the missing scenes will be regenerated.",
                        flush=True,
                    )
                    return recovered
        raise ValueError("model response was malformed or truncated and contained no recoverable story") from None



def _repair_missing_scenes(api_key, model, story, desired_count):
    """Repair a partial story in small batches; never discard its completed scenes."""
    scenes = story.get("scenes")
    if not isinstance(scenes, list):
        return False
    if len(scenes) > desired_count:
        story["scenes"] = scenes[:desired_count]
        return True

    batch_number = 0
    while len(scenes) < desired_count:
        batch_number += 1
        missing = min(8, desired_count - len(scenes))
        prompt = f"""
Continue this educational science explainer as a seamless continuation.
Topic: {story.get("topic", "")}
Description: {story.get("description", "")}
The story currently has {len(scenes)} complete scenes and needs exactly {missing} additional scenes in this batch.
The final existing scenes are:
{json.dumps(scenes[-5:], ensure_ascii=False)}
Return ONLY valid JSON in this shape: {{"scenes":[{{"title":"short heading","narration":"28-32 spoken words","visual":"drawable cartoon scene without text","background":"sky, lab, space, ocean, forest, city, home, cave, desert, or mountain","action":"explain, walk, point, run, think, surprised, celebrate, observe"}}]}}
Return exactly {missing} new scenes. Do not repeat earlier explanations. Keep the narration factually careful and make the final scene of the whole story a memorable conclusion.
"""
        batch_added = False
        for attempt in range(1, 4):
            try:
                data = _call_story_model(api_key, model, prompt)
                addition = _decode_json_object(_response_text(data))
                new_scenes = addition.get("scenes", [])
                if not isinstance(new_scenes, list) or not new_scenes:
                    raise ValueError("repair response contained no scene list")
                accepted = [
                    item for item in new_scenes
                    if isinstance(item, dict)
                    and isinstance(item.get("narration"), str)
                    and item.get("narration", "").strip()
                    and isinstance(item.get("visual"), str)
                    and item.get("visual", "").strip()
                ]
                if not accepted:
                    raise ValueError("repair response contained no complete scene records")
                scenes.extend(accepted[:missing])
                story["scenes"] = scenes
                print(
                    f"Scene repair batch {batch_number}: added {min(len(accepted), missing)} "
                    f"scenes; {len(scenes)}/{desired_count} complete.",
                    flush=True,
                )
                batch_added = True
                break
            except Exception as exc:
                print(
                    f"Scene repair batch {batch_number}, attempt {attempt}/3 failed: {exc}",
                    flush=True,
                )
                if attempt < 3:
                    time.sleep(attempt * 3)
        if not batch_added:
            return False
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
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("GEMINI_API_KEY is not set; skipping Gemini and using configured free LLM fallbacks.", flush=True)

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
    if api_key:
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
    target_minutes = max(1, int(config.get("target_minutes", 8)))
    target_words_low = target_minutes * 140
    target_words_high = target_minutes * 160

    # The original default remains science. The animated explainer workflow can
    # select another broad niche without changing existing science workflows.
    niche = str(config.get("content_niche", "science")).strip() or "science"
    niche = niche[:80]
    for generation_attempt in range(5):
        category = random.choice(TOPIC_CATEGORIES) if niche.lower() == "science" else niche
        print(f"Content niche ({generation_attempt + 1}/5): {category}", flush=True)
        prompt = f"""
Create an original, factually careful educational {niche} explainer for a colorful animated-character video.

TOPIC STYLE REFERENCE — read these examples from the repository's topics.txt:
{examples}

Choose ONE fresh, specific, curiosity-driven question in this category or niche: {category}.
Use topics.txt only as a guide to concise, accessible storytelling style, not as a subject list when the selected niche is not science.
Do not simply copy a seed topic or make a minor wording change to one.
Generate a different subject/question each time, drawing from the selected niche.
Do NOT repeat or closely rephrase any previously used topic in this history:
{json.dumps(recent_history, ensure_ascii=False)}

The title must be a concise natural question in an approachable style.
Return the selected topic in the JSON "topic" field and make the entire explainer answer that exact question.

Target narration duration: about {target_minutes} minutes, approximately {target_words_low}-{target_words_high} spoken words.
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
CRITICAL SCENE COUNT: Output exactly {desired_scene_count} scene objects in the scenes array — not {desired_scene_count - 1}, not {desired_scene_count + 1}. Count the objects before returning JSON. The final array must contain {desired_scene_count} complete objects. Do not stop early to save tokens; keep each narration within the requested 28-32 words. Create exactly {desired_scene_count} scenes. The total narration should match approximately {target_minutes} minutes at 140-160 words per minute. Begin with a surprising hook, build curiosity, explain the subject accurately in plain language, and end with a memorable takeaway. Avoid fabricated statistics, unsupported claims, medical advice, and repetitive filler. Use age-friendly language. Each narration must be a complete spoken paragraph and should be 28-32 words, not shorter. Make visual descriptions easy to illustrate with simple cartoon shapes. Do not put text or labels inside scene images. JSON only, no Markdown fences.
"""

        data = None
        for model in models:
            print(f"Trying Gemini model: {model}")
            try:
                data = _call_gemini(api_key, model, prompt)
                used_model = model
                break
            except Exception as exc:
                print(f"  {model} failed: {type(exc).__name__}: {str(exc)[:400]}", flush=True)

        if data is None and GROQ_KEY:
            try:
                data = _call_openai_compatible("Groq", GROQ_MODEL, prompt)
                used_model = "groq:" + GROQ_MODEL
            except Exception as exc:
                print(f"Groq story fallback unavailable: {type(exc).__name__}: {exc}", flush=True)

        if data is None:
            kilo_models = list(dict.fromkeys([KILO_MODEL] + KILO_FALLBACK_MODELS))
            for kilo_model in kilo_models:
                try:
                    data = _call_openai_compatible("Kilo", kilo_model, prompt)
                    used_model = "kilo:" + kilo_model
                    break
                except Exception as exc:
                    print(
                        f"Kilo anonymous model {kilo_model} unavailable: "
                        f"{type(exc).__name__}: {exc}",
                        flush=True,
                    )

        if data is None:
            raise RuntimeError(
                "All Gemini models and configured open-weight fallbacks failed. "
                "Check the provider-specific errors above and rerun; no story was saved."
            )

        try:
            raw = _response_text(data)
            candidate_story = _parse_story_json(raw)
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            print(
                f"Planner response was malformed/truncated on generation attempt "
                f"{generation_attempt + 1}/5: {exc}. Requesting a fresh complete story.",
                flush=True,
            )
            continue

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
