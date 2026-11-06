import os, random, hashlib, asyncio, aiohttp, io, urllib.parse, base64, time, requests
from PIL import Image, ImageDraw, ImageFont

STYLE = ("high-quality Pixar-inspired 3D animated feature-film style, polished stylized 3D rendering, "
         "appealing expressive 3D characters when relevant, detailed dimensional environments, "
         "rich colors, carefully crafted materials and textures, cinematic composition, "
         "soft global illumination, natural depth, beautiful movie-quality lighting and shadows, "
         "immersive family-friendly animated world, 16:9 landscape composition; "
         "clearly three-dimensional, not flat 2D vector art, not a 2D cartoon illustration, "
         "no bold 2D outlines, no flat color fills, no simplistic vector shapes, "
         "no text, captions, logos, watermarks, title bars, blue strips, black bars, subtitle panels, borders or graphic overlays, not photorealistic live-action")

def font(size, bold=False):
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
    except:
        return ImageFont.load_default()

def build_prompt(visual):
    clean = " ".join(visual.split()).replace('"', "")[:250]
    return f"{clean}, {STYLE}"

# --- CLOUDFLARE CREDENTIALS ---
CF_ACCOUNT_ID = os.getenv("CF_ACCOUNT_ID")
CF_API_TOKEN = os.getenv("CF_API_TOKEN")

# Temporarily pause Cloudflare after HTTP 429, then automatically try it again.
_CLOUDFLARE_COOLDOWN_UNTIL = 0.0

class CloudflareRateLimited(RuntimeError):
    pass

class CloudflarePromptFlagged(RuntimeError):
    pass

# --- CHEAP MODEL ONLY: FLUX-2-KLEIN-4B ---
CF_URL_CHEAP = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/@cf/black-forest-labs/flux-2-klein-4b"

def cf_image_cheap(prompt):
    if not CF_ACCOUNT_ID or not CF_API_TOKEN:
        raise RuntimeError("CF credentials missing")
    form_data = {"prompt": (None, prompt), "width": (None, "1024"), "height": (None, "576")}
    headers = {"Authorization": f"Bearer {CF_API_TOKEN}"}
    for attempt in range(1, 4):
        response = requests.post(CF_URL_CHEAP, headers=headers, files=form_data, timeout=(20, 180))
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "")
            try:
                wait = max(60, min(1800, int(float(retry_after)))) if retry_after else (300 * attempt)
            except ValueError:
                wait = 300 * attempt
            if attempt == 3:
                raise CloudflareRateLimited(
                    f"Cloudflare rate limit persisted after {attempt} attempts; checkpoint saved for next run."
                )
            print(f"Cloudflare HTTP 429. Waiting {wait}s before retry {attempt + 1}/3.", flush=True)
            time.sleep(wait)
            continue
        if response.status_code >= 500 and attempt < 3:
            wait = 30 * attempt
            print(f"Cloudflare HTTP {response.status_code}; retrying in {wait}s.", flush=True)
            time.sleep(wait)
            continue
        if not response.ok:
            print(f"Cloudflare HTTP {response.status_code}", flush=True)
            print(f"Cloudflare response: {response.text[:3000]}", flush=True)
            try:
                error_payload = response.json()
            except ValueError:
                error_payload = {}
            errors = error_payload.get("errors", []) if isinstance(error_payload, dict) else []
            if response.status_code == 400 and any(
                isinstance(item, dict) and item.get("code") == 3030 for item in errors
            ):
                raise CloudflarePromptFlagged("Cloudflare safety filter flagged this prompt (error 3030).")
            response.raise_for_status()
        if response.headers.get("content-type", "").startswith("image/"):
            return response.content
        payload = response.json()
        return base64.b64decode(payload.get("result", payload)["image"])
    raise CloudflareRateLimited("Cloudflare remained unavailable; checkpoint saved for next run.")

def valid_png(raw):
    if not raw:
        raise ValueError("Image provider returned an empty response")
    with Image.open(io.BytesIO(raw)) as im:
        im.verify()
    with Image.open(io.BytesIO(raw)) as im:
        converted = im.convert("RGB")
        output = io.BytesIO()
        converted.save(output, format="PNG", optimize=True)
        return output.getvalue()

def rewrite_flagged_prompt(original_visual, attempt):
    """Rewrite a flagged scene into a safe depiction of the same story beat."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing; cannot rewrite flagged scene prompt.")
    model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    strategies = {
        1: (
            "Rewrite the description from scratch in simple, neutral, family-friendly language. "
            "Keep the same subject, scientific concept, characters, setting, and narrative purpose. "
            "Remove ambiguous or unnecessarily intense wording; do not just swap synonyms."
        ),
        2: (
            "Re-stage the same story moment as a clearly safe educational 3D illustration. "
            "Preserve the central science concept and what the viewer needs to understand, "
            "but replace any potentially sensitive physical action with a harmless symbolic "
            "visual metaphor, demonstration model, or non-contact interaction."
        ),
        3: (
            "Create a substantially different but meaning-equivalent visual composition for "
            "the same scene. Focus on the scientific idea and narrative beat using benign "
            "objects, a classroom or laboratory demonstration, and calm character poses. "
            "Avoid depicting injury, violence, weapons, dangerous acts, or graphic detail."
        ),
        4: (
            "Show the same story beat through a close-up educational science exhibit or "
            "hands-on demonstration. Preserve the key subject and concept, but communicate "
            "the action through objects, physical models, and visual cause and effect."
        ),
        5: (
            "Use a wide establishing shot of the same setting and moment, preserving the "
            "important characters or scientific subject. Communicate the same narrative "
            "purpose through calm poses, safe distance, and a clear visual metaphor. "
            "Use a noticeably different camera angle and composition."
        ),
    }
    strategy = strategies.get(attempt, strategies[5])
    instruction = (
        "You are revising a visual prompt because an image-generation safety filter rejected "
        "the previous wording. Your job is to make a genuinely safer depiction, not to bypass "
        "or trick the safety system.\n"
        f"{strategy}\n"
        "Keep it suitable for a general-audience educational science video. "
        "Describe only visible image content. Do not include text, captions, labels, logos, "
        "or instructions. Return one concise visual description only, with no explanation.\n\n"
        f"Original scene description:\n{original_visual}"
    )
    response = requests.post(
        url, params={"key": api_key},
        json={"contents": [{"parts": [{"text": instruction}]}],
              "generationConfig": {"temperature": 0.65}},
        timeout=(20, 90)
    )
    response.raise_for_status()
    revised = response.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    if not revised:
        raise RuntimeError("Gemini returned an empty revised visual prompt.")
    return revised[:1000]


async def generate_all_ai_images(scenes, out_dir, width, height, story_path=None):
    print("Generating AI illustrations with Cloudflare FLUX.2 Klein only.", flush=True)
    os.makedirs(out_dir, exist_ok=True)
    results = []
    for i, scene in enumerate(scenes, 1):
        image_path = os.path.join(out_dir, f"scene-{i:03d}.png")
        if os.path.isfile(image_path) and os.path.getsize(image_path) > 0:
            try:
                with Image.open(image_path) as existing:
                    existing.verify()
                with open(image_path, "rb") as image_file:
                    results.append((i, image_file.read()))
                print(f"  Scene {i}/{len(scenes)} already saved; skipping.", flush=True)
                continue
            except Exception:
                os.remove(image_path)
        original_visual = scene.get("visual", "science illustration")
        prompt = build_prompt(original_visual)
        print(f"  Scene {i}/{len(scenes)}: requesting Cloudflare.", flush=True)
        try:
            image_data = valid_png(cf_image_cheap(prompt))
        except CloudflarePromptFlagged:
            image_data = None
            # Ask Gemini to rephrase only this scene, then retry Cloudflare.
            for rewrite_attempt in range(1, 6):
                try:
                    revised_visual = rewrite_flagged_prompt(original_visual, rewrite_attempt)
                    revised_prompt = build_prompt(revised_visual)
                    print(f"  Scene {i}: Gemini revised flagged prompt ({rewrite_attempt}/5); retrying Cloudflare.", flush=True)
                    image_data = valid_png(cf_image_cheap(revised_prompt))
                    scene["visual"] = revised_visual
                    if story_path:
                        import json
                        from pathlib import Path
                        story_file = Path(story_path)
                        saved_story = json.loads(story_file.read_text(encoding="utf-8"))
                        saved_story["scenes"][i - 1]["visual"] = revised_visual
                        temporary_story = story_file.with_name(story_file.name + ".tmp")
                        temporary_story.write_text(
                            json.dumps(saved_story, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8",
                        )
                        os.replace(temporary_story, story_file)
                    break
                except CloudflareRateLimited:
                    raise
                except CloudflarePromptFlagged:
                    print(f"  Scene {i}: revised prompt was still flagged.", flush=True)
                except Exception as exc:
                    print(f"  Scene {i}: prompt rewrite/retry failed: {exc}", flush=True)
            # Never substitute an unrelated generic image: the scene must retain
            # its story meaning. Stop with a clear error if all meaning-preserving
            # Gemini rewrites are rejected; saved scenes remain checkpointed.
            if image_data is None:
                raise RuntimeError(
                    f"Scene {i}: Cloudflare rejected the original prompt and all five "
                    "meaning-preserving Gemini rewrites. Review this scene's visual description; "
                    "all previously generated scene images are preserved."
                )
        except CloudflareRateLimited:
            print(f"Cloudflare quota/rate limit reached at scene {i}; completed scenes are preserved.", flush=True)
            raise
        with open(image_path, "wb") as image_file:
            image_file.write(image_data)
        results.append((i, image_data))
        print(f"  Scene {i}/{len(scenes)}: saved from Cloudflare.", flush=True)
        if i < len(scenes):
            time.sleep(2)
    print(f"Generated or resumed {len(results)} of {len(scenes)} scene images.", flush=True)
    if len(results) != len(scenes):
        missing = sorted(set(range(1, len(scenes) + 1)) - {index for index, _ in results})
        raise RuntimeError(f"Scene images still missing after fallback: {missing}. Saved images are checkpointed; rerun to retry only missing scenes.")
    return results

def make_scene_art(scene, idx, total, path, width=1280, height=720, ai_image_data=None):
    if ai_image_data:
        try:
            im = Image.open(io.BytesIO(ai_image_data)).convert("RGB")
            im = im.resize((width, height), Image.Resampling.LANCZOS)
        except Exception as e:
            print(f"Error processing image for scene {idx}: {e}")
            ai_image_data = None

    if not ai_image_data:
        raise RuntimeError(f"Scene {idx}: no valid AI-generated image was supplied; refusing stickman fallback.")

    # Clean full-frame artwork: no title/caption bars or text overlays.
    im.save(path, quality=95)
    return path