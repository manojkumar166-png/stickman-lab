import os, random, hashlib, asyncio, aiohttp, io, urllib.parse, base64, time, requests, json
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

# Disable Cloudflare for the remainder of this process after quota exhaustion,
# an authentication failure, or repeated transient service errors.
_CLOUDFLARE_DISABLED = False

class CloudflareRateLimited(RuntimeError):
    pass

class CloudflareUnavailable(RuntimeError):
    pass

class CloudflarePromptFlagged(RuntimeError):
    pass

# --- CHEAP MODEL ONLY: FLUX-2-KLEIN-4B ---
CF_URL_CHEAP = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/@cf/black-forest-labs/flux-2-klein-4b"

def cf_image_cheap(prompt):
    """Generate an image with Cloudflare Workers AI only, retrying transient failures."""
    if not CF_ACCOUNT_ID or not CF_API_TOKEN:
        raise CloudflareUnavailable("Cloudflare credentials are missing.")

    form_data = {"prompt": (None, prompt), "width": (None, "1024"), "height": (None, "576")}
    headers = {"Authorization": f"Bearer {CF_API_TOKEN}"}
    last_error = None

    for attempt in range(1, 6):
        try:
            response = requests.post(
                CF_URL_CHEAP, headers=headers, files=form_data, timeout=(20, 180)
            )
        except requests.RequestException as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt == 5:
                break
            wait = min(60, attempt * 10)
            print(f"Cloudflare network error; retrying in {wait}s ({attempt}/5): {last_error}", flush=True)
            time.sleep(wait)
            continue

        if response.status_code == 429 or response.status_code >= 500:
            last_error = f"HTTP {response.status_code}: {response.text[:800]}"
            if attempt == 5:
                break
            retry_after = response.headers.get("Retry-After", "")
            try:
                wait = min(120, max(1, int(float(retry_after)))) if retry_after else min(60, attempt * 10)
            except (TypeError, ValueError):
                wait = min(60, attempt * 10)
            print(f"Cloudflare temporary error; retrying in {wait}s ({attempt}/5): {last_error}", flush=True)
            time.sleep(wait)
            continue

        if response.status_code in (401, 403):
            raise CloudflareUnavailable(
                f"Cloudflare authentication/permission error HTTP {response.status_code}: {response.text[:1200]}"
            )

        if not response.ok:
            try:
                error_payload = response.json()
            except ValueError:
                error_payload = {}
            errors = error_payload.get("errors", []) if isinstance(error_payload, dict) else []
            if response.status_code == 400 and any(
                isinstance(item, dict) and item.get("code") == 3030 for item in errors
            ):
                raise CloudflarePromptFlagged("Cloudflare safety filter flagged this scene prompt (error 3030).")
            raise CloudflareUnavailable(
                f"Cloudflare rejected the image request with HTTP {response.status_code}: {response.text[:1200]}"
            )

        try:
            if response.headers.get("content-type", "").startswith("image/"):
                image_data = response.content
            else:
                payload = response.json()
                image_data = base64.b64decode(payload.get("result", payload)["image"])
            if not image_data:
                raise ValueError("Cloudflare returned an empty image.")
            return image_data
        except (ValueError, KeyError, TypeError) as exc:
            last_error = f"Invalid Cloudflare image response: {exc}"
            if attempt < 5:
                wait = min(60, attempt * 10)
                print(f"{last_error}; retrying in {wait}s ({attempt}/5).", flush=True)
                time.sleep(wait)
                continue

    raise CloudflareUnavailable(
        f"Cloudflare image generation failed after five attempts. Last error: {last_error}"
    )


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

def _extract_gemini_payload(response_text):
    """Decode a Gemini response even if a proxy appended a second JSON object."""
    decoder = json.JSONDecoder()
    candidates = []
    for offset, char in enumerate(response_text):
        if char != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(response_text[offset:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and isinstance(payload.get("candidates"), list):
            candidates.append(payload)
    if not candidates:
        preview = response_text[:1200].replace("\\n", " ")
        raise ValueError(f"Gemini response contained no complete candidates JSON object. Response begins: {preview}")
    return candidates[0]


def rewrite_flagged_prompt(original_visual, attempt):
    """Rewrite a flagged scene into a safe depiction of the same story beat."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing; cannot rewrite flagged scene prompt.")
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
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
            "but replace potentially sensitive physical action with a harmless symbolic "
            "visual metaphor, demonstration model, or non-contact interaction."
        ),
        3: (
            "Create a substantially different but meaning-equivalent visual composition for "
            "the same scene. Focus on the scientific idea and narrative beat using benign "
            "objects, a classroom or laboratory demonstration, and calm character poses."
        ),
        4: (
            "Show the same story beat through a close-up educational science exhibit or "
            "hands-on demonstration. Preserve the key subject and concept, but communicate "
            "the action through objects, physical models, and visual cause and effect."
        ),
        5: (
            "Use a wide establishing shot of the same setting and moment, preserving the "
            "important characters or scientific subject. Communicate the same narrative "
            "purpose through calm poses, safe distance, and a clear visual metaphor."
        ),
    }
    strategy = strategies.get(attempt, strategies[5])
    instruction = (
        "Revise this image prompt into a genuinely safer general-audience educational depiction. "
        "Do not bypass or trick the image safety system. Preserve the educational concept and "
        "story beat while removing risky or ambiguous details. Describe only visible image content. "
        "Return one concise visual description only, with no explanation or markdown.\n\n"
        f"{strategy}\nOriginal scene description:\n{original_visual}"
    )

    request_body = {
        "contents": [{"parts": [{"text": instruction}]}],
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 512},
    }
    last_error = None
    for api_attempt in range(1, 6):
        try:
            response = requests.post(
                url,
                params={"key": api_key},
                json=request_body,
                timeout=(20, 90),
            )
            if response.status_code == 429 or response.status_code >= 500:
                raise requests.HTTPError(
                    f"Gemini temporary HTTP {response.status_code}: {response.text[:800]}",
                    response=response,
                )
            response.raise_for_status()
            payload = _extract_gemini_payload(response.text)
            parts = payload["candidates"][0]["content"]["parts"]
            revised = "\n".join(
                part["text"] for part in parts
                if isinstance(part, dict) and isinstance(part.get("text"), str)
            ).strip()
            if not revised:
                raise ValueError("Gemini returned no text in its first candidate.")
            return " ".join(revised.split())[:1000]
        except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if api_attempt == 5:
                break
            wait = min(30, api_attempt * 5)
            print(
                f"Gemini safe-prompt rewrite request failed ({api_attempt}/5); "
                f"retrying in {wait}s: {last_error}",
                flush=True,
            )
            time.sleep(wait)

    raise RuntimeError(
        f"Gemini safe-prompt rewrite failed after five API attempts: {last_error}"
    )


async def generate_all_ai_images(scenes, out_dir, width, height, story_path=None):
    """Generate every missing scene through Cloudflare Workers AI; never use another image provider."""
    print("Generating AI illustrations with Cloudflare Workers AI only.", flush=True)
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
                print(f"Scene {i}/{len(scenes)} already checkpointed; skipping.", flush=True)
                continue
            except Exception:
                os.remove(image_path)

        original_visual = scene.get("visual", "science illustration")
        image_data = None
        last_error = None
        try:
            try:
                print(f"Scene {i}/{len(scenes)}: requesting Cloudflare Workers AI.", flush=True)
                image_data = valid_png(cf_image_cheap(build_prompt(original_visual)))
            except CloudflarePromptFlagged:
                for rewrite_attempt in range(1, 6):
                    try:
                        revised_visual = rewrite_flagged_prompt(original_visual, rewrite_attempt)
                        revised_prompt = build_prompt(revised_visual)
                        print(
                            f"Scene {i}: safe prompt revision {rewrite_attempt}/5; retrying Cloudflare only.",
                            flush=True,
                        )
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
                    except CloudflarePromptFlagged as exc:
                        last_error = exc
                        print(f"Scene {i}: Cloudflare still flagged the revised prompt ({rewrite_attempt}/5).", flush=True)
                if image_data is None:
                    raise CloudflarePromptFlagged(
                        f"Cloudflare rejected the original prompt and all five safe revisions for scene {i}."
                    ) from last_error

            if not image_data:
                raise RuntimeError("Cloudflare returned an empty image.")
            image_data = valid_png(image_data)
            temporary_image = image_path + ".tmp"
            with open(temporary_image, "wb") as image_file:
                image_file.write(image_data)
            os.replace(temporary_image, image_path)
            results.append((i, image_data))
            print(f"Scene {i}/{len(scenes)}: saved Cloudflare image checkpoint.", flush=True)
            if i < len(scenes):
                time.sleep(2)
        except Exception as exc:
            raise RuntimeError(
                f"Cloudflare could not generate scene {i}/{len(scenes)} after its retries. "
                f"Completed scene images remain saved; the next workflow attempt will resume at this scene. "
                f"Cause: {type(exc).__name__}: {exc}"
            ) from exc

    if len(results) != len(scenes):
        missing = sorted(set(range(1, len(scenes) + 1)) - {index for index, _ in results})
        raise RuntimeError(f"Cloudflare scene images missing: {missing}. Saved images will be reused on retry.")
    print(f"Cloudflare images ready: {len(results)}/{len(scenes)} scenes.", flush=True)
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