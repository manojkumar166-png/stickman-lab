import os, json, random, time, re
from difflib import SequenceMatcher
from pathlib import Path

import requests

KILO_MODEL = "kilo-auto/free"
KILO_FALLBACK_MODELS = ["nvidia/nemotron-3.5-lightning:free", "openrouter/free"]

class PermanentProviderError(RuntimeError):
    """A non-retryable provider response such as HTTP 400 or 404."""

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


PROVIDER_CONFIG = {
    # Public endpoints that do not require credentials. Availability may vary.
    "Kilo": ("https://api.kilo.ai/api/gateway", "", "kilo-auto/free"),
    "OVH": ("https://oai.endpoints.kepler.ai.cloud.ovh.net/v1", "", "gpt-oss-20b"),
}


def _call_openai_compatible(provider, model, prompt, attempts=2):
    """Call a configured OpenAI-compatible provider with bounded retries."""
    if provider not in PROVIDER_CONFIG:
        raise ValueError(f"Unsupported backup provider: {provider}")
    base_url, key_env, _ = PROVIDER_CONFIG[provider]
    # Intentionally anonymous: this workflow must never require an API key.
    headers = {"Content-Type": "application/json"}
    if provider == "OpenRouter":
        headers["HTTP-Referer"] = "https://github.com/manojkumar166-png/stickman-lab"
        headers["X-Title"] = "Free Animated 3D Explainer"
    messages = [
        {"role": "system", "content": (
            "Return exactly one valid JSON object matching the requested schema. "
            "Do not use Markdown fences or add commentary."
        )},
        {"role": "user", "content": prompt},
    ]
    url = base_url.rstrip("/") + "/chat/completions"
    request_bodies = [
        {"model": model, "messages": messages, "temperature": 0.7, "max_tokens": 12000},
        {"model": model, "messages": messages},
    ]
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            response = None
            for variant_index, body in enumerate(request_bodies):
                response = requests.post(url, headers=headers, json=body, timeout=(12, 90))
                if response.status_code == 400 and variant_index == 0:
                    # Some free-tier models reject optional sampling parameters.
                    continue
                if response.status_code in (408, 425, 429, 500, 502, 503, 504):
                    raise RuntimeError(f"{provider} HTTP {response.status_code}: {response.text[:700]}")
                if not response.ok:
                    message = f"{provider} HTTP {response.status_code}: {response.text[:700]}"
                    if 400 <= response.status_code < 500:
                        raise PermanentProviderError(message)
                    raise RuntimeError(message)
                break
            if response is None or not response.ok:
                raise RuntimeError(f"{provider} returned no successful response")
            payload = response.json()
            choices = payload.get("choices") or []
            message = choices[0].get("message", {}) if choices else {}
            content = message.get("content", "")
            if isinstance(content, list):
                content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
            if not isinstance(content, str) or not content.strip():
                raise RuntimeError(f"{provider} returned an empty completion")
            print(f"Story planner active: {provider}/{model}", flush=True)
            return {"candidates": [{"content": {"parts": [{"text": content}]}}]}
        except PermanentProviderError:
            raise
        except Exception as exc:
            last_error = exc
            print(f"{provider} attempt {attempt}/{attempts} failed: {type(exc).__name__}: {exc}", flush=True)
            if attempt < attempts:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"{provider} failed after {attempts} attempts: {last_error}") from last_error


def _call_gemini(api_key, model, prompt):
    """Call Gemini when configured; return the same response shape as other providers."""
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "systemInstruction": {"parts": [{"text": (
            "Return exactly one valid JSON object matching the requested schema. "
            "Do not use Markdown fences or add commentary."
        )}]},
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 12000,
            "responseMimeType": "application/json",
        },
    }
    response = requests.post(url, headers=headers, json=body, timeout=(12, 120))
    if response.status_code in (408, 425, 429, 500, 502, 503, 504):
        raise RuntimeError(f"Gemini HTTP {response.status_code}: {response.text[:700]}")
    if not response.ok:
        raise PermanentProviderError(f"Gemini HTTP {response.status_code}: {response.text[:700]}")
    payload = response.json()
    candidates = payload.get("candidates") or []
    if not candidates:
        raise RuntimeError(f"Gemini returned no candidates: {str(payload)[:700]}")
    print(f"Story planner active: Gemini/{model}", flush=True)
    return {"candidates": candidates}


def _call_story_model(api_key, model, prompt):
    """Repair a story using the same keyless provider that generated it."""
    if ":" not in model:
        raise RuntimeError("Offline fallback does not make remote repair calls")
    provider, provider_model = model.split(":", 1)
    if provider == "Gemini":
        return _call_gemini(api_key, provider_model, prompt)
    return _call_openai_compatible(provider, provider_model, prompt)


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


def _local_story_fallback(niche, desired_scene_count, history=None):
    """Deterministic offline story: keep rendering possible when every API is down."""
    banks = {
        "science": [
            ("Why does the Moon seem to change shape?", "moon phases"),
            ("How do plants turn sunlight into food?", "photosynthesis"),
            ("Why does lightning happen before thunder?", "storms"),
            ("How do vaccines help the immune system?", "immune memory"),
        ],
        "technology": [
            ("How does the internet move information around the world?", "internet routing"),
            ("How do computers learn patterns from examples?", "machine learning"),
            ("How does a battery store and release energy?", "battery chemistry"),
        ],
        "history": [
            ("How did ancient trade routes connect distant societies?", "trade routes"),
            ("How did the printing press change the spread of ideas?", "printing press"),
        ],
        "psychology": [
            ("Why does the brain remember some moments better than others?", "memory"),
            ("How do habits become automatic?", "habit formation"),
        ],
        "finance": [
            ("How does compound growth make money change over time?", "compound growth"),
            ("Why do prices rise when demand outpaces supply?", "supply and demand"),
        ],
        "self-improvement": [
            ("How can small daily actions build lasting skills?", "deliberate practice"),
            ("Why does breaking a big goal into steps help?", "goal setting"),
        ],
        "general education": [
            ("How do simple systems create surprising results?", "complex systems"),
        ],
    }
    options = banks.get(str(niche).lower(), banks["general education"])
    history = history or []
    fresh_options = [item for item in options if not _is_repeat(item[0], history)]
    if fresh_options:
        topic, concept = random.choice(fresh_options)
    else:
        topic, concept = random.choice(options)
        topic = f"How can we understand {concept} through a fresh everyday example?"
    beats = [
        ("Start with a question", f"Everyday experience gives us clues about {concept}, but the full explanation is more interesting than it first appears. Let us build the idea one clear step at a time.", "A curious stick figure studies a simple everyday example", "home", "think"),
        ("Notice the key parts", f"First identify the main parts involved in {concept}. Each part has a role, and understanding those roles makes the larger process easier to follow.", "A character points to three simple illustrated components", "lab", "point"),
        ("Follow the first change", f"When the process begins, one small change affects the next part. This chain of events is the central idea behind understanding {concept}.", "Connected objects respond one after another", "lab", "observe"),
        ("Look for a pattern", f"Repeated observations help reveal a pattern. Instead of memorizing isolated facts, look at what stays consistent and what changes as conditions become different.", "A character compares several clear visual examples", "city", "explain"),
        ("Test the explanation", f"A useful explanation should make sense in a new example too. Change one condition, keep the others steady, and observe how the result responds.", "A simple experiment with one changing variable", "lab", "observe"),
        ("Avoid a common mix-up", f"It is easy to confuse two events that happen together with one event causing the other. Careful comparisons help separate coincidence from a real explanation.", "Two parallel timelines are compared by a character", "lab", "think"),
        ("Connect the bigger picture", f"Now connect the individual parts. Their interactions explain why {concept} can produce an outcome that no single part could create alone.", "Small pieces combine into one larger system", "space", "explain"),
        ("See it in daily life", f"This idea appears in ordinary life more often than expected. Recognizing it helps turn an abstract explanation into something practical and memorable.", "A stick figure spots the concept in daily surroundings", "home", "surprised"),
        ("Remember the limits", f"Real situations can include extra factors, so this simple model is a starting point rather than the whole story. New evidence can refine an explanation.", "A simple model gains additional surrounding details", "lab", "observe"),
        ("Take away the main idea", f"The central lesson is to follow the parts, watch how they interact, and test explanations against evidence. That habit makes complicated subjects easier to understand.", "The character celebrates as the complete visual system comes together", "sky", "celebrate"),
    ]
    scenes = []
    for index in range(desired_scene_count):
        title, narration, visual, background, action = beats[index % len(beats)]
        scenes.append({
            "title": f"{title} ({index + 1})",
            "narration": narration,
            "visual": visual + "; clean colorful educational cartoon, no written words",
            "background": background,
            "action": action,
        })
    print("WARNING: All remote LLM providers failed; using deterministic offline explainer fallback.", flush=True)
    return {
        "topic": topic,
        "description": f"A simple step-by-step visual introduction to {concept}.",
        "scenes": scenes,
        "generation_mode": "offline_fallback",
    }


def generate_story(root: Path, config: dict) -> dict:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if api_key:
        print("Gemini API key detected; Gemini will be tried first with free-provider fallbacks.", flush=True)
    else:
        print("GEMINI_API_KEY is not set; using free-provider fallbacks and offline generation.", flush=True)

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
        # Gemini is preferred when a secret is configured. Keyless providers and
        # the deterministic local generator remain available as automatic fallbacks.
        provider_models = []
        if api_key:
            provider_models.append(("Gemini", str(config.get("gemini_model") or "gemini-2.5-flash")))
        provider_models.extend([
            # Second choice: anonymous OVH inference (no API key required).
            ("OVH", "gpt-oss-20b"),
            # Third choice: anonymous Kilo, followed by its free model fallbacks.
            ("Kilo", KILO_MODEL),
            *[("Kilo", model) for model in KILO_FALLBACK_MODELS],
        ])
        for provider, provider_model in provider_models:
            if data is not None:
                break
            if not provider_model:
                continue
            try:
                if provider == "Gemini":
                    data = _call_gemini(api_key, provider_model, prompt)
                else:
                    data = _call_openai_compatible(provider, provider_model, prompt)
                used_model = provider + ":" + provider_model
                break
            except Exception as exc:
                print(f"{provider}/{provider_model} unavailable: {type(exc).__name__}: {str(exc)[:450]}", flush=True)

        if data is None:
            story = _local_story_fallback(niche, desired_scene_count)
            used_model = "offline:template"
            break

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
            print("Keyless provider returned an invalid scenes field; requesting a fresh story.", flush=True)
            continue
        if len(returned_scenes) != desired_scene_count:
            actual_count = len(returned_scenes)
            print(f"Keyless provider returned {actual_count} scenes; repairing to exactly {desired_scene_count}.", flush=True)
            if not _repair_missing_scenes(api_key, used_model, candidate_story, desired_scene_count):
                last_scene_count = len(candidate_story.get("scenes", []))
                print("Could not repair this story's scene count; requesting a fresh story.", flush=True)
                continue
            returned_scenes = candidate_story["scenes"]
        last_scene_count = None

        candidate_topic = str(candidate_story.get("topic", "")).strip()
        if _is_repeat(candidate_topic, history):
            last_duplicate = candidate_topic or "(empty title)"
            print(f"Keyless provider returned a repeated/too-similar topic: {last_duplicate!r}; choosing another category.")
            recent_history = history[-150:] + ([last_duplicate] if last_duplicate else [])
            continue
        story = candidate_story
        break

    if story is None:
        print(
            "Remote providers did not produce a valid, complete, non-repeated story after "
            "five attempts; switching to the offline story generator.",
            flush=True,
        )
        story = _local_story_fallback(niche, desired_scene_count, history)
        used_model = "offline:template"

    print(f"Story generated with {used_model}: {story['topic']}")
    scenes = story.get("scenes", [])
    if not isinstance(scenes, list) or len(scenes) < 5:
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
