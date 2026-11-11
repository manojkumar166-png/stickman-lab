#!/usr/bin/env python3
"""Independent Gemini planner for the Science Channel pipeline."""
import json, os, re, time, datetime, difflib, random
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = json.loads((ROOT / "settings.json").read_text())
API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip()
KILO_MODEL = os.getenv("KILO_MODEL", "kilo-auto/free").strip()
KILO_FALLBACK_MODELS = [
    item.strip() for item in os.getenv(
        "KILO_FALLBACK_MODELS",
        "nvidia/nemotron-3.5-super-vl:free,dots-studio/dots-3-note-preview:free,nvidia/nemotron-3-ultra-550b-a55b:free",
    ).split(",") if item.strip()
]
MODEL = os.getenv("GEMINI_MODEL") or SETTINGS["gemini_model"]
API = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
HISTORY = ROOT / "history/generated-topics.json"
TOPICS = ROOT / "topics.txt"
TODAY = datetime.date.today().isoformat()


def topic_slug(value):
    """Create a readable, filesystem-safe folder suffix from an episode topic."""
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug[:70].strip("-") or "untitled-topic"

def parse_gemini_json(raw_text):
    """Parse Gemini JSON, tolerating Markdown fences and harmless surrounding text."""
    text = raw_text.strip().lstrip("\ufeff")
    text = re.sub(r"^\s*\`\`\`(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*\`\`\`\s*$", "", text)

    # Isolate the first complete JSON object if Gemini adds surrounding prose.
    start = text.find("{")
    if start < 0:
        raise json.JSONDecodeError("No JSON object found in Gemini response", text, 0)
    depth = 0
    in_string = False
    escaped = False
    end = None
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                end = index + 1
                break
    if end is None:
        raise json.JSONDecodeError("Gemini response contains an incomplete JSON object", text, len(text))
    return json.loads(text[start:end])


def gemini(prompt, temperature=0.7):
    """Call Gemini with automatic model failover and retries for transient/invalid responses.

    The configured primary model is always tried first on a fresh run. Once a model
    succeeds, it becomes the preferred model for the remaining calls in this process.
    """
    global MODEL, API
    configured = ([MODEL] + SETTINGS.get("gemini_fallback_models", [])) if API_KEY else []
    if not API_KEY:
        failures_note = "GEMINI_API_KEY is not configured; skipped Gemini."
        print(failures_note, flush=True)
    # Preserve order while removing duplicates and empty entries.
    model_candidates = list(dict.fromkeys(
        str(model).strip() for model in configured if str(model).strip()
    ))
    failures = []

    for model_index, model in enumerate(model_candidates):
        model_api = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        request_prompt = prompt
        last_error = None

        # Two attempts per model for transient errors or malformed model output,
        # then move to the next configured model instead of stalling the workflow.
        for attempt in range(3):
            payload = {
                "contents": [{"parts": [{"text": request_prompt}]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "maxOutputTokens": 16000,
                    "temperature": temperature,
                }
            }
            try:
                response = requests.post(
                    model_api, params={"key": API_KEY}, json=payload, timeout=(20, 180)
                )
                if not response.ok:
                    detail = response.text[:2000]
                    message = f"Gemini model {model} returned HTTP {response.status_code}: {detail}"
                    lowered = detail.casefold()
                    model_unavailable = any(term in lowered for term in (
                        "model not found", "not found for api version",
                        "is not supported", "does not exist", "not available",
                        "permission denied for model", "model is not enabled",
                        "unsupported model"
                    ))
                    if response.status_code in (400, 403, 404) and not model_unavailable:
                        # A malformed request or invalid API key is not fixed by
                        # switching models, so surface the real API response.
                        raise requests.HTTPError(message, response=response)
                    if response.status_code not in (400, 403, 404, 408, 429, 500, 502, 503, 504):
                        raise requests.HTTPError(message, response=response)
                    last_error = RuntimeError(message)
                    raise last_error

                data = response.json()
                candidates = data.get("candidates") or []
                if not candidates:
                    raise ValueError(
                        f"{model} returned no candidates: " +
                        json.dumps(data.get("promptFeedback", {}), ensure_ascii=False)[:1000]
                    )

                candidate = candidates[0]
                parts = candidate.get("content", {}).get("parts", [])
                response_text = "".join(
                    part.get("text", "") for part in parts if isinstance(part, dict)
                )
                try:
                    result = parse_gemini_json(response_text)
                except (json.JSONDecodeError, TypeError) as exc:
                    finish_reason = candidate.get("finishReason", "unknown")
                    raise RuntimeError(
                        f"{model} returned invalid JSON (finishReason={finish_reason}): {exc}"
                    ) from exc

                # Keep the successful model first for every subsequent planner stage.
                MODEL = model
                API = model_api
                if model_index:
                    print(
                        f"Gemini failover succeeded: switched to {model} "
                        f"(primary model {model_candidates[0]} was unavailable).",
                        flush=True
                    )
                else:
                    print(f"Gemini model active: {model}", flush=True)
                return result

            except requests.HTTPError as exc:
                last_error = exc
                print(
                    f"Gemini model {model} rejected the request; moving to the next provider/model: {exc}",
                    flush=True,
                )
                break
            except (requests.RequestException, ValueError, KeyError, TypeError, RuntimeError) as exc:
                last_error = exc
                print(
                    f"Gemini model {model} failed (attempt {attempt + 1}/2): {exc}",
                    flush=True
                )
                if attempt < 2:
                    request_prompt = (
                        prompt +
                        "\n\nAUTOMATIC RETRY: The previous request on model " + model +
                        " failed: " + str(exc)[:800] +
                        ". Return one complete valid JSON object only. Correct the issue, " +
                        "escape all strings correctly, and do not include Markdown or commentary."
                    )
                    delay = min(30, 2 ** (attempt + 1))
                    time.sleep(delay)

        failures.append(f"{model}: {last_error}")
        if model_index < len(model_candidates) - 1:
            print(
                f"Switching Gemini model automatically: {model} -> {model_candidates[model_index + 1]}",
                flush=True
            )

    # Try Groq when its optional secret is configured.
    if GROQ_API_KEY:
        groq_url = "https://api.groq.com/openai/v1/chat/completions"
        for attempt in range(1, 4):
            try:
                response = requests.post(
                    groq_url,
                    headers={
                        "Authorization": f"Bearer {GROQ_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": GROQ_MODEL,
                        "messages": [
                            {
                                "role": "system",
                                "content": "Return one complete valid JSON object matching the requested schema. No Markdown or commentary.",
                            },
                            {"role": "user", "content": prompt},
                        ],
                        "response_format": {"type": "json_object"},
                        "max_completion_tokens": 16000,
                        "temperature": temperature,
                    },
                    timeout=(20, 180),
                )
                if response.status_code in (408, 425, 429, 500, 502, 503, 504):
                    raise RuntimeError(
                        f"Groq HTTP {response.status_code}: {response.text[:1200]}"
                    )
                response.raise_for_status()
                choices = response.json().get("choices") or []
                result_text = (
                    choices[0].get("message", {}).get("content", "")
                    if choices else ""
                )
                result = parse_gemini_json(result_text)
                print(f"Groq planner fallback active: {GROQ_MODEL}", flush=True)
                return result
            except Exception as exc:
                failures.append(f"Groq attempt {attempt}/3: {type(exc).__name__}: {exc}")
                if attempt < 3:
                    time.sleep(min(30, attempt * 5))
    else:
        print("Groq planner fallback skipped: GROQ_API_KEY is not configured.", flush=True)

    # Kilo Auto Free works without an API key. Try its current free catalogue
    # after Gemini/Groq, using a minimal body if a routed model rejects max_tokens.
    kilo_url = "https://ai-gateway.kilo.ai/api/v1/chat/completions"
    kilo_models = list(dict.fromkeys([KILO_MODEL] + KILO_FALLBACK_MODELS))
    kilo_errors = []
    for kilo_model in kilo_models:
        messages = [
            {
                "role": "system",
                "content": "Return one complete valid JSON object matching the requested schema. No Markdown or commentary.",
            },
            {"role": "user", "content": prompt},
        ]
        request_bodies = [
            {"model": kilo_model, "messages": messages, "max_tokens": 16000},
            {"model": kilo_model, "messages": messages},
        ]
        for attempt in range(1, 3):
            try:
                response = None
                for variant_index, body in enumerate(request_bodies):
                    response = requests.post(
                        kilo_url,
                        headers={"Content-Type": "application/json"},
                        json=body,
                        timeout=(20, 240),
                    )
                    if response.status_code == 400 and variant_index + 1 < len(request_bodies):
                        print(
                            f"Kilo model {kilo_model} rejected optional token limits; retrying minimal payload.",
                            flush=True,
                        )
                        continue
                    if response.status_code in (408, 425, 429, 500, 502, 503, 504):
                        raise RuntimeError(
                            f"Kilo HTTP {response.status_code}: {response.text[:1200]}"
                        )
                    if not response.ok:
                        error = f"Kilo model {kilo_model} HTTP {response.status_code}: {response.text[:1400]}"
                        kilo_errors.append(error)
                        print(error, flush=True)
                        if 400 <= response.status_code < 500:
                            break
                        raise RuntimeError(error)
                    break
                if response is None or not response.ok:
                    break
                choices = response.json().get("choices") or []
                result_text = (
                    choices[0].get("message", {}).get("content", "")
                    if choices else ""
                )
                if isinstance(result_text, list):
                    result_text = "".join(
                        part.get("text", "") for part in result_text if isinstance(part, dict)
                    )
                result = parse_gemini_json(result_text)
                print(f"Kilo anonymous planner fallback active: {kilo_model}", flush=True)
                return result
            except Exception as exc:
                kilo_errors.append(
                    f"{kilo_model} attempt {attempt}/2: {type(exc).__name__}: {exc}"
                )
                if attempt < 2:
                    time.sleep(attempt * 7)

    raise RuntimeError(
        "All configured story-planning providers failed. "
        + "Gemini: " + (" | ".join(failures) if failures else "skipped")
        + " | Kilo: " + (" | ".join(kilo_errors) if kilo_errors else "no model response")
    )

def gemini_validated(prompt, validator, stage, temperature=0.7, attempts=3):
    """Regenerate Gemini output when its JSON is valid but fails stage-specific checks."""
    if not callable(validator):
        raise TypeError(
            f"{stage!r}: validator must be a callable function; got {type(validator).__name__}. "
            "Expected gemini_validated(prompt, validator, stage, temperature=...)."
        )
    if not isinstance(stage, str) or not stage.strip():
        raise TypeError("gemini_validated stage must be a non-empty string")
    last_error = None
    retry_prompt = prompt
    stage_started = time.perf_counter()
    for attempt in range(1, attempts + 1):
        try:
            result = gemini(retry_prompt, temperature)
            validator(result)
            print(f"{stage} completed in {time.perf_counter() - stage_started:.1f}s", flush=True)
            return result
        except (ValueError, KeyError, TypeError, RuntimeError, json.JSONDecodeError) as exc:
            last_error = exc
            print(
                f"{stage} validation failed (attempt {attempt}/{attempts}): {exc}",
                flush=True
            )
            if attempt < attempts:
                retry_prompt = (
                    prompt +
                    "\n\nAUTOMATIC CORRECTION REQUIRED: The previous response failed "
                    f"{stage} validation: {exc}. Regenerate the entire response and correct "
                    "the problem. Return one complete valid JSON object only. Follow every "
                    "required field, type, count, and ordering rule exactly. Do not add "
                    "Markdown or commentary."
                )
                time.sleep(2 * attempt)
    raise RuntimeError(
        f"{stage} could not be generated correctly after {attempts} correction attempts: {last_error}"
    )


def validate_topic(data):
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object")
    if not isinstance(data.get("title"), str) or not data["title"].strip():
        raise ValueError("Missing or empty title")
    if not isinstance(data.get("angle"), str) or not data["angle"].strip():
        raise ValueError("Missing or empty angle")


def validate_duplicate_review(data):
    if not isinstance(data, dict) or not isinstance(data.get("duplicate"), bool):
        raise ValueError("Expected boolean 'duplicate' field")
    if not isinstance(data.get("reason", ""), str):
        raise ValueError("Expected string 'reason' field")


def validate_episode(data):
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object")
    if not isinstance(data.get("title"), str) or not data["title"].strip():
        raise ValueError("Missing or empty episode title")
    if not isinstance(data.get("description"), str):
        raise ValueError("Missing or invalid description")
    scenes = data.get("scenes")
    if not isinstance(scenes, list) or len(scenes) != 48:
        raise ValueError("Expected exactly 48 scenes")
    for number, scene in enumerate(scenes, 1):
        if not isinstance(scene, dict) or scene.get("scene_number") != number:
            raise ValueError(f"Scene {number} is missing or out of order")
        if not isinstance(scene.get("narration"), str) or not scene["narration"].strip():
            raise ValueError(f"Scene {number} has empty narration")
        if not isinstance(scene.get("visual_beat"), str) or not scene["visual_beat"].strip():
            raise ValueError(f"Scene {number} has empty visual_beat")


def validate_image_prompts(data):
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object")
    prompts = data.get("prompts")
    if not isinstance(prompts, list) or len(prompts) != 48:
        raise ValueError("Expected exactly 48 image prompts")
    for number, item in enumerate(prompts, 1):
        if not isinstance(item, dict) or item.get("scene_number") != number:
            raise ValueError(f"Image prompt {number} is missing or out of order")
        if not isinstance(item.get("prompt"), str) or not item["prompt"].strip():
            raise ValueError(f"Image prompt {number} is empty")

history = json.loads(HISTORY.read_text()) if HISTORY.exists() else {"topics":[]}
# Also recover topics from existing episode packages, so an interrupted run cannot
# cause an already-created topic to be selected again.
used_topics = list(history.get("topics", []))
used_topic_details = list(history.get("topic_details", []))
episode_root = ROOT / "daily-episodes"
if episode_root.exists():
    for metadata in episode_root.glob("*/*/episode-*/episode.json"):
        try:
            saved = json.loads(metadata.read_text())
            if saved.get("title"):
                used_topics.append(saved["title"])
                used_topic_details.append({
                    "title": saved["title"],
                    "angle": saved.get("angle", ""),
                    "pillar": saved.get("pillar", "")
                })
        except (OSError, json.JSONDecodeError):
            continue

def topic_key(value):
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()

seen = {topic_key(x) for x in used_topics if x.strip()}
def is_duplicate_topic(candidate):
    key = topic_key(candidate)
    return key in seen or any(
        difflib.SequenceMatcher(None, key, topic_key(old)).ratio() >= 0.88
        for old in used_topics if isinstance(old, str) and old.strip()
    )

def is_seed_reuse(candidate):
    """Reject selecting or lightly rewording a topics.txt style example."""
    key = topic_key(candidate)
    if not key:
        return True
    for seed in topic_seed_lines:
        seed_key = topic_key(seed)
        if key == seed_key or difflib.SequenceMatcher(None, key, seed_key).ratio() >= 0.82:
            return True
    return False

def has_same_underlying_subject(candidate_title, candidate_angle, candidate_pillar):
    # A second Gemini review compares meaning, not just title wording.
    # Fail closed: if the reviewer cannot return a clear decision, stop rather
    # than risk publishing a duplicate episode.
    history_for_review = list(used_topic_details)
    detailed_titles = {
        topic_key(item.get("title", ""))
        for item in history_for_review if isinstance(item, dict)
    }
    # Include every legacy title too, even when newer records have richer metadata.
    history_for_review.extend(
        {"title": old, "angle": "", "pillar": ""}
        for old in used_topics
        if isinstance(old, str) and topic_key(old) not in detailed_titles
    )
    review = gemini_validated("""You are a strict duplicate-episode detector for a science YouTube channel.
Compare the proposed episode with the COMPLETE historical episode list.
Return { "duplicate": true, "reason": "..." } if it covers the same core scientific
subject, event, phenomenon, question, mechanism, or substantially the same viewer takeaway,
even when the wording, framing, example, or title is different.
Treat paraphrases and alternate consequences of the same central phenomenon as duplicates.
For example, "What if the Sun disappeared?" and "How long could Earth survive without sunlight?"
are duplicates because both explore Earth losing the Sun/sunlight.
Return duplicate=false only when the central subject and explanation are genuinely distinct.
When uncertain, return duplicate=true. Compare meanings, not keyword overlap.
Proposed episode: """ + json.dumps({
        "title": candidate_title, "angle": candidate_angle, "pillar": candidate_pillar
    }, ensure_ascii=False) + """
Historical episodes: """ + json.dumps(history_for_review, ensure_ascii=False),
    validate_duplicate_review, "Semantic duplicate review", temperature=0.1)
    if review["duplicate"]:
        print("Rejected semantically repeated topic: " + str(review.get("reason", "same underlying subject")))
    return review["duplicate"]
# Read the topic seed file as a STYLE GUIDE, not a fixed list of titles to reuse.
# Each run randomly selects a broad category; Gemini invents a fresh question in that category.
topic_seed_lines = []
if TOPICS.exists():
    for line in TOPICS.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if value and not value.startswith("#"):
            topic_seed_lines.append(value)

topic_pillars = [
    ("Space and astronomy", "Why do stars twinkle?"),
    ("Human body and mind", "Why do we get goosebumps?"),
    ("Earth, oceans and weather", "Why is the ocean salty?"),
    ("Animals and animal behaviour", "How do bees communicate?"),
    ("Plants and the natural world", "How do plants know which way is up?"),
    ("Everyday physics", "How do magnets work?"),
    ("Light, sound and vision", "Why is the sky blue?"),
    ("Earth's geology and natural processes", "How do volcanoes erupt?"),
    ("Technology and engineering", "How do airplanes stay in the air?"),
    ("Chemistry and materials around us", "Why does metal rust?"),
    ("Dinosaurs, fossils and ancient Earth", "How do fossils reveal what ancient animals looked like?"),
    ("Brain, memory and senses", "How does the brain store memories?"),
    ("Weather, clouds and the water cycle", "How do clouds make rain?"),
    ("Moon, planets and the solar system", "Why does the Moon change shape?"),
    ("Animal senses and abilities", "How can bats find their way in the dark?"),
    ("Food and everyday chemistry", "Why does bread rise when it bakes?"),
    ("Science of time and space", "Why does time seem different in space?"),
    ("Human body everyday mysteries", "Why do we sneeze?"),
]
selected_pillar, pillar_example = random.SystemRandom().choice(topic_pillars)
# One planner run selects exactly ONE new topic inside the randomly selected pillar.
# Retry if Gemini suggests a previously used title or returns a near-duplicate.
topic = None
for attempt in range(5):
    topic_data = gemini_validated("""You are the topic editor for a mainstream, curiosity-driven science YouTube channel.
Your job is to invent ONE fresh episode idea that has the same accessible, naturally intriguing style as the examples—not to copy the examples.

RANDOMLY SELECTED CATEGORY FOR THIS RUN (mandatory): """ + selected_pillar + """
A short example of the kind of clear question that fits this category: """ + pillar_example + """

The repository file science-channel/topics.txt contains topic seeds and examples. Read the supplied seed list below as a guide to the channel's style: simple, specific, familiar, curiosity-driven science questions. These seeds are NOT a queue and NOT titles to reuse. Do not simply select a line, paraphrase it, or make a minor variation of one. Invent a new subject/question with a similar feel.
TOPIC SEEDS / STYLE REFERENCES: """ + json.dumps(topic_seed_lines, ensure_ascii=False) + """

Before choosing, silently brainstorm at least 10 genuinely different candidate questions that fit the selected category. Pick the strongest one based on broad audience interest, instant understanding, a natural curiosity gap, scientific depth, and visual storytelling potential. Return only the single best new idea.

STYLE TARGET:
- Think of questions ordinary curious people naturally ask: Why do we dream? Why is the ocean salty? How do airplanes stay in the air? Why does the Moon change shape? How do bees communicate? Why is the sky blue? How do black holes work? Why do we get goosebumps? How do plants know which way is up? Why do we have fingerprints? How do clouds make rain? Why do we sneeze? How do magnets work? Why do stars twinkle? Why is space silent? How do volcanoes erupt?
- These are examples of the desired simplicity and broad curiosity, not a list to copy. Make up fresh questions.
- Titles should be short, clear, conversational, and understandable at a glance. Often a natural "Why...", "How...", or "What makes..." question works best.
- Interesting science is enough. Do not manufacture drama, danger, catastrophe, or extreme stakes to make a title clickable.
- A simple question can be an excellent episode. Do not mistake straightforward wording for a boring idea.
- Avoid contrived disasters, bizarre body-horror, implausible hypotheticals, over-engineered scenarios, exaggerated clickbait, obscure specialist topics, and vague textbook headings.
- The science must support a complete 8–10 minute explanation with several layers, examples, surprising facts, and visual possibilities.
- Stay strictly within the selected category. Do not drift into another category because its topic sounds more dramatic.
- Be scientifically grounded; for mysteries, focus on real open questions and evidence, not paranormal speculation.
- The proposed subject must be genuinely distinct from every previous episode. Never reuse the same underlying phenomenon, event, mechanism, central question, or viewer takeaway with different wording. Check the complete used-topic list below; if there is meaningful overlap, silently choose another candidate.
- Do not expose brainstorming, rankings, or rejected candidates.

Return JSON only: {"title":"...","angle":"one sentence describing the distinctive explanation or curiosity hook"}.
Previously generated topics (never repeat or closely duplicate): """ + json.dumps(used_topics, ensure_ascii=False) +
"\nThe only permitted category for this episode is: " + selected_pillar, validate_topic, "Topic generation", 0.45)
    candidate = topic_data.get("title", "").strip()
    candidate_angle = topic_data.get("angle", "").strip()
    if candidate and not is_seed_reuse(candidate) and not is_duplicate_topic(candidate):
        if has_same_underlying_subject(candidate, candidate_angle, selected_pillar):
            continue
        topic = {"title": candidate, "angle": candidate_angle}
        break
    if candidate and is_seed_reuse(candidate):
        print("Rejected topic because it selected or too closely reworded a topics.txt style example: " + candidate)
if topic is None:
    raise RuntimeError("Gemini did not provide a new unused topic after 5 attempts; no episode was created.")

title = topic["title"]

# Use the next available episode number for today; never overwrite an earlier run.
month_root = episode_root / datetime.date.today().strftime("%B %Y")
day_root = month_root / TODAY
day_root.mkdir(parents=True, exist_ok=True)
existing_numbers = []
for path in day_root.glob("episode-*"):
    match = re.fullmatch(r"episode-(\d+)(?:-[a-z0-9-]+)?", path.name)
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
episode = gemini_validated(script_prompt, validate_episode, "48-scene script", 0.65)
scenes = episode["scenes"]

# Derive exactly one image prompt from each finalized narration scene.
prompt_data = gemini_validated("""Create exactly 48 image prompts from this finalized 48-scene narration.
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
Use a 16:9 cinematic 3D family-animation aesthetic, composed for a 1920x1080 landscape frame.
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
Final script scenes: """ + json.dumps(scenes, ensure_ascii=False), validate_image_prompts, "48 image prompts", 0.55)
prompts = prompt_data["prompts"]

# Reserve the topic only after the full script and all 48 prompts validate.
# A malformed/truncated Gemini response therefore does not consume a topic.
history.setdefault("topics", []).append(title)
history.setdefault("topic_details", []).append({
    "title": title,
    "angle": topic.get("angle", ""),
    "pillar": selected_pillar
})
HISTORY.parent.mkdir(parents=True, exist_ok=True)
HISTORY.write_text(json.dumps(history, indent=2, ensure_ascii=False) + "\n")

final_title = episode.get("title", title).strip()
folder = day_root / f"episode-{episode_number:03d}-{topic_slug(final_title)}"
images = folder / "images" / "incoming"
images.mkdir(parents=True, exist_ok=False)
(folder / "episode.json").write_text(json.dumps({
    "episode_id": f"{TODAY}-episode-{episode_number:03d}",
    "date": TODAY, "title": final_title,
    "angle": topic.get("angle", ""), "pillar": selected_pillar,
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
(folder / "README.md").write_text(
    f"# {final_title}\n\n- Episode: {episode_number:03d}\n- Date: {TODAY}\n"
    "- Scenes/images required: 48\n- Status: Awaiting images\n\n"
    "## Upload images\nUpload exactly 48 images, or one ZIP containing 48 images, into images/incoming/. "
    "Use numbered filenames such as scene-001.webp through scene-048.webp to preserve scene order. "
    "Then add READY.txt when the package is ready to render.\n\n"
    "## Package files\n- episode.json: metadata\n- script.md: narration\n"
    "- scenes.json: ordered scene data\n- image-prompts.md: image prompts\n"
)
(images / ".gitkeep").write_text("")

print(f"Created ONE new topic: {final_title}")
print(f"Created {folder} with 48 narration scenes and 48 matching prompts; upload 48 images (one ZIP or 48 files) to images/incoming/")
