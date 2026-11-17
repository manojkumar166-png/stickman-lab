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
        preview = response_text[:1200].replace("\n", " ")
        raise ValueError(f"Gemini response contained no complete candidates JSON object. Response begins: {preview}")
    return candidates[0]


def rewrite_flagged_prompt(original_visual, attempt):
    """Rewrite a flagged scene using a model fallback chain; never depend on one configured model."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("GEMINI_API_KEY is unavailable; using a conservative educational fallback prompt.", flush=True)
        return _safe_educational_fallback(original_visual)

    configured = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()
    configured_fallbacks = [
        item.strip() for item in os.getenv("GEMINI_FALLBACK_MODELS", "").split(",")
        if item.strip()
    ]
    models = []
    for model in [configured, *configured_fallbacks, "gemini-3.8-flash", "gemini-3.5-flash-lite"]:
        if model and model not in models:
            models.append(model)

    strategies = {
        1: "Rewrite from scratch in simple, neutral, family-friendly language. Preserve the science concept and story purpose; remove ambiguous or intense wording.",
        2: "Represent the same concept with a harmless symbolic model or classroom demonstration. Avoid physical contact or risky action.",
        3: "Use a different calm educational composition with benign objects and friendly characters observing from a safe distance.",
        4: "Show the concept through a close-up science exhibit, physical model, or visual metaphor.",
        5: "Use a wide establishing shot of a calm educational setting that communicates the same general science topic.",
    }
    strategy = strategies.get(attempt, strategies[5])
    instruction = (
        "Create a safer general-audience educational image description. Do not bypass or trick safety filters. "
        "Preserve the educational idea while removing risky or ambiguous details. Describe visible content only. "
        "Return one concise description, no markdown.\n\n"
        f"{strategy}\nOriginal scene description:\n{original_visual}"
    )
    request_body = {
        "contents": [{"parts": [{"text": instruction}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 512},
    }

    errors = []
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        for api_attempt in range(1, 3):
            try:
                response = requests.post(
                    url, params={"key": api_key}, json=request_body, timeout=(15, 60)
                )
                if response.status_code == 404:
                    errors.append(f"{model}: HTTP 404 (model unavailable)")
                    print(f"Gemini model {model} is unavailable; moving to the next fallback.", flush=True)
                    break
                if response.status_code in (400, 401, 403):
                    errors.append(f"{model}: HTTP {response.status_code}: {response.text[:300]}")
                    break
                if response.status_code == 429 or response.status_code >= 500:
                    raise requests.HTTPError(
                        f"Gemini temporary HTTP {response.status_code}: {response.text[:500]}",
                        response=response,
                    )
                response.raise_for_status()
                payload = _extract_gemini_payload(response.text)
                parts = payload["candidates"][0]["content"]["parts"]
                revised = "\n".join(
                    part["text"] for part in parts
                    if isinstance(part, dict) and isinstance(part.get("text"), str)
                ).strip()
                if revised:
                    print(f"Safe-prompt rewrite succeeded with {model}.", flush=True)
                    return " ".join(revised.split())[:1000]
                raise ValueError("Gemini returned no text in its first candidate.")
            except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
                errors.append(f"{model} attempt {api_attempt}: {type(exc).__name__}: {exc}")
                if api_attempt < 2:
                    time.sleep(3 * api_attempt)

    print(
        "All Gemini prompt-rewrite models failed; using a conservative educational fallback. "
        + " | ".join(errors[-6:]),
        flush=True,
    )
    return _safe_educational_fallback(original_visual)


def _safe_educational_fallback(original_visual):
    """Use a neutral local fallback without reusing wording rejected by the image safety filter."""
    return (
        "A calm, family-friendly 3D educational science illustration in a bright classroom or museum. "
        "Show a simple tabletop science model, neutral scientific objects, and friendly animated "
        "characters observing from a comfortable distance. Use a clear, harmless visual metaphor, "
        "soft cinematic lighting, and a peaceful setting. "
        "No danger, injury, conflict, bodily detail, weapons, text, labels, or intense action."
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