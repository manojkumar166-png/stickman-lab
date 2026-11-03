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

def ovh_image(prompt):
    """Anonymous OVHcloud SDXL fallback; limited to roughly 2 requests/minute."""
    global _OVH_LAST_CALL
    wait = max(0.0, 31.0 - (time.monotonic() - _OVH_LAST_CALL))
    if wait:
        print(f"  Waiting {wait:.1f}s for OVHcloud's anonymous rate limit.", flush=True)
        time.sleep(wait)
    _OVH_LAST_CALL = time.monotonic()
    response = requests.post(
        "https://stable-diffusion-xl.endpoints.kepler.ai.cloud.ovh.net/api/text2image",
        headers={"accept": "application/octet-stream", "Content-Type": "application/json"},
        json={
            "prompt": prompt,
            "negative_prompt": "text, letters, typography, watermark, logo, signature, border, collage, split screen, duplicate subjects, extra limbs, malformed hands, deformed face, distorted anatomy, blurry, pixelated, low detail, flat lighting, oversaturated, noisy, jpeg artifacts"
        },
        timeout=(20, 180)
    )
    response.raise_for_status()
    if "application/json" in response.headers.get("Content-Type", ""):
        encoded = (response.json().get("data") or [{}])[0].get("b64_json")
        if not encoded:
            raise ValueError("OVHcloud returned no image data")
        return valid_png(base64.b64decode(encoded))
    return valid_png(response.content)

async def generate_all_ai_images(scenes, out_dir, width, height):
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
        prompt = build_prompt(scene.get("visual", "science illustration"))
        print(f"  Scene {i}/{len(scenes)}: requesting Cloudflare.", flush=True)
        try:
            image_data = valid_png(cf_image_cheap(prompt))
        except CloudflareRateLimited:
            print(f"Cloudflare quota/rate limit reached at scene {i}; completed scenes are preserved.", flush=True)
            raise
        with open(image_path, "wb") as image_file:
            image_file.write(image_data)
        results.append((i, image_data))
        print(f"  Scene {i}/{len(scenes)}: saved from Cloudflare.", flush=True)
        if i < len(scenes):
            time.sleep(2)
    print(f"Successfully generated or resumed all {len(results)} scene images.", flush=True)
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