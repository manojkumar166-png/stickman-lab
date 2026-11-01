#!/usr/bin/env python3
"""Independent Gemini planner for the Science Channel pipeline."""
import json, os, re, time, datetime, difflib, random
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
    """Call Gemini with retries for transient network/API errors and malformed JSON."""
    request_prompt = prompt
    last_error = None
    for attempt in range(5):
        payload = {
            "contents": [{"parts": [{"text": request_prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "maxOutputTokens": 16384
            }
        }
        try:
            response = requests.post(API, params={"key": API_KEY}, json=payload, timeout=180)
            if not response.ok:
                error_detail = response.text[:2000]
                last_error = RuntimeError(
                    f"Gemini API HTTP {response.status_code}: {error_detail}"
                )
                if response.status_code not in (408, 429, 500, 502, 503, 504):
                    raise requests.HTTPError(
                        f"{last_error}. This is a non-retryable API/configuration error.",
                        response=response
                    )
                raise last_error

            data = response.json()
            candidates = data.get("candidates") or []
            if not candidates:
                raise ValueError(
                    "Gemini returned no candidates: " +
                    json.dumps(data.get("promptFeedback", {}), ensure_ascii=False)[:1000]
                )

            candidate = candidates[0]
            parts = candidate.get("content", {}).get("parts", [])
            response_text = "".join(
                part.get("text", "") for part in parts if isinstance(part, dict)
            )
            try:
                return parse_gemini_json(response_text)
            except (json.JSONDecodeError, TypeError) as exc:
                finish_reason = candidate.get("finishReason", "unknown")
                last_error = RuntimeError(
                    f"Invalid Gemini JSON (finishReason={finish_reason}): {exc}"
                )
                raise last_error

        except requests.HTTPError:
            # Authentication, permission, and other permanent 4xx errors need a
            # configuration fix; repeating the same request cannot repair them.
            raise
        except requests.RequestException as exc:
            last_error = exc
        except (ValueError, KeyError, TypeError, RuntimeError) as exc:
            last_error = exc

        print(
            f"Gemini request/response failed (attempt {attempt + 1}/5): {last_error}",
            flush=True
        )
        if attempt < 4:
            request_prompt = (
                prompt +
                "\n\nAUTOMATIC RETRY: The previous Gemini request failed: " +
                str(last_error)[:800] +
                ". Return one complete valid JSON object only. Correct the issue, "
                "escape all strings correctly, and do not include Markdown or commentary."
            )
            time.sleep(min(3 * (attempt + 1), 15))

    raise RuntimeError(
        f"Gemini request failed after 5 attempts. Last error: {last_error}"
    )

def gemini_validated(prompt, validator, stage, temperature=0.7, attempts=3):
    """Regenerate Gemini output when its JSON is valid but fails stage-specific checks."""
    last_error = None
    retry_prompt = prompt
    for attempt in range(1, attempts + 1):
        try:
            result = gemini(retry_prompt, temperature)
            validator(result)
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
                    "\\n\\nAUTOMATIC CORRECTION REQUIRED: The previous response failed "
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
    for metadata in episode_root.glob("*/episode-*/episode.json"):
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
    0.1, validate_duplicate_review, "Semantic duplicate review")
    if review["duplicate"]:
        print("Rejected semantically repeated topic: " + str(review.get("reason", "same underlying subject")))
    return review["duplicate"]
# Every episode must belong to one of these seven broad, viewer-friendly pillars.
# Choose the pillar randomly in Python so Gemini cannot drift into unrelated niche subjects.
topic_pillars = [
    ("Space and astronomy", "What would happen if Earth stopped rotating?"),
    ("Human body and mind", "Why does your brain create dreams?"),
    ("Physics and extreme what-if scenarios", "What would happen if gravity suddenly became weaker?"),
    ("Earth science and natural wonders", "What lies beneath the Earth's deepest oceans?"),
    ("Technology and future inventions", "How could quantum computers change the world?"),
    ("Animals and animal superpowers", "How do animals survive extreme environments?"),
    ("Mysteries of science and the universe", "Could humans ever travel through time?"),
    ("Chemistry and astonishing materials", "Could a material exist that is harder than diamond?"),
    ("Oceans and underwater discoveries", "What strange worlds could exist beneath the deepest ocean?"),
    ("Dinosaurs, fossils and prehistoric life", "What did the world look like when dinosaurs ruled?"),
    ("Earth, climate and extreme weather", "What would happen if the Gulf Stream stopped?"),
    ("Engineering and mega-structures", "How could humans build a city under the ocean?"),
    ("Food science and everyday mysteries", "Why does popcorn explode and turn inside out?"),
    ("Inventions and scientific breakthroughs", "What accidental discovery changed the modern world?"),
    ("Extreme scientific what-if scenarios", "What if Earth suddenly stopped spinning?"),
    ("Impossible-sounding science", "Can humans survive in space without a spacesuit?"),
    ("Hidden mysteries and unseen worlds", "What is really at the bottom of the ocean?"),
    ("Unexpected abilities and nature's superpowers", "How can the human brain recognize a face in a split second?"),
    ("Future possibilities and human survival", "Could humans one day live on Mars permanently?"),
]
selected_pillar, pillar_example = random.SystemRandom().choice(topic_pillars)

# One planner run selects exactly ONE new topic inside the randomly selected pillar.
# Retry if Gemini suggests a previously used title or returns a near-duplicate.
topic = None
for attempt in range(5):
    topic_data = gemini_validated("""You are planning a mainstream, curiosity-driven Science Channel episode.
The category for THIS episode has already been randomly selected and is mandatory.
Selected category: """ + selected_pillar + """
Example of the desired broad, accessible question style: """ + pillar_example + """
Generate exactly ONE exceptionally compelling, fresh episode topic strictly within the selected category.
PRIMARY GOAL: earn the click AND keep the viewer watching. Imagine the audience is scrolling YouTube:
the title must make a broad, curious viewer instantly feel "Wait, is that really possible?" or
"I have to know what happens." Prioritize mass audience appeal, instant comprehension, and a powerful
curiosity gap over showing off obscure scientific knowledge.

Before choosing, silently brainstorm several different candidate ideas and select the strongest one.
Score the best candidate against these standards; reject it unless it is excellent:
- INSTANT HOOK: creates a vivid question, surprising possibility, relatable mystery, or high-stakes scenario.
- BROAD APPEAL: connects to something people already care about: their body, everyday life, Earth, animals,
  space, danger, survival, the future, or a familiar technology.
- CLEAR PAYOFF: viewers can imagine what they will discover, and the answer is more surprising than the premise.
- VISUAL STORY: can be shown through striking scenes, experiments, comparisons, scale, or consequences.
- RETENTION: naturally unfolds into escalating revelations, not a one-fact explanation.
A strong idea should combine at least TWO of these: a shocking-but-true consequence, a familiar thing behaving
in an unexpected way, a relatable "what if", a hidden process with an astonishing result, a counterintuitive
scientific fact, or a big question with a genuinely surprising evidence-based answer.

Prefer topics with a human connection, real-world stakes, wonder, or a "this changes how I see the world" payoff.
Use concrete, vivid language. Make the title concise, natural, emotionally engaging, and understandable to a
12-year-old without dumbing down the science. The angle must explain the specific hook and the sequence of
discoveries that will keep viewers watching.

Avoid bland textbook topics ("How do stars work?"), dry school-assignment phrasing, jargon, obscure trivia,
tiny niche facts, generic "amazing facts", listicle bait, fake urgency, misleading exaggeration, sensational
misinformation, and claims science cannot support. Do not choose a topic merely because it sounds technically
impressive. Do not sacrifice truth for clickbait.
The topic must sustain a complete 8–10 minute story: open with an irresistible question or visual moment,
raise the stakes, reveal increasingly surprising facts, and finish with a satisfying scientifically accurate
answer or twist.
Do NOT switch to another category. Do NOT choose obscure species, highly specialized biological mechanisms,
technical research-paper questions, or tiny niche facts. For Animals, focus on familiar or visually striking
animals and extraordinary abilities/survival strategies that reveal a bigger scientific idea. For Technology,
focus on consequential technologies and surprising real-world possibilities or limitations. For Mysteries
of science, choose profound questions that can be explored with evidence, not paranormal speculation.
Create a title that sounds like a compelling YouTube episode, usually as a question or a vivid "what if".
The subject itself must be completely new, not merely a differently worded title. Never reuse the same underlying question, event, scientific phenomenon, or central explanation from any previously generated episode. Treat synonyms, paraphrases, alternate wording, and narrow variations of an old topic as repeats. Compare against the COMPLETE lifetime used-topic list below; if the idea overlaps, choose a genuinely different subject.
Return JSON only: {"title":"...","angle":"one-sentence distinctive angle explaining the hook and why viewers will care"}.
Previously used topics (never repeat these): """ + json.dumps(used_topics, ensure_ascii=False) +
"\nThe only permitted category for this episode is: " + selected_pillar, validate_topic, "Topic generation", 0.45)
    candidate = topic_data.get("title", "").strip()
    candidate_angle = topic_data.get("angle", "").strip()
    if candidate and not is_duplicate_topic(candidate):
        if has_same_underlying_subject(candidate, candidate_angle, selected_pillar):
            continue
        topic = {"title": candidate, "angle": candidate_angle}
        break
if topic is None:
    raise RuntimeError("Gemini did not provide a new unused topic after 5 attempts; no episode was created.")

title = topic["title"]

# Use the next available episode number for today; never overwrite an earlier run.
day_root = episode_root / TODAY
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
