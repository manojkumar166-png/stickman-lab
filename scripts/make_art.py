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

# A Cloudflare 429 is an account-level throttle. Stop using Cloudflare for
# the remainder of this workflow run and let the fallback providers take over.
_CLOUDFLARE_RATE_LIMITED = False

class CloudflareRateLimited(RuntimeError):
    pass

# --- CHEAP MODEL ONLY: FLUX-2-KLEIN-4B ---
CF_URL_CHEAP = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/@cf/black-forest-labs/flux-2-klein-4b"

def cf_image_cheap(prompt):
    global _CLOUDFLARE_RATE_LIMITED
    if _CLOUDFLARE_RATE_LIMITED:
        raise CloudflareRateLimited("Cloudflare rate limit already reached; using fallback providers.")
    if not CF_ACCOUNT_ID or not CF_API_TOKEN:
        raise RuntimeError("CF credentials missing")
    
    form_data = {
        "prompt": (None, prompt),
        "width": (None, "1024"),
        "height": (None, "576")
    }
    
    headers = {"Authorization": f"Bearer {CF_API_TOKEN}"}
    r = None
    for attempt in range(1, 6):
        try:
            r = requests.post(CF_URL_CHEAP, headers=headers, files=form_data, timeout=(20, 180))
            if r.status_code == 429:
                _CLOUDFLARE_RATE_LIMITED = True
                retry_after = r.headers.get("Retry-After", "not provided")
                raise CloudflareRateLimited(f"Cloudflare returned HTTP 429 (Retry-After: {retry_after}); disabling Cloudflare for this workflow run.")
            if r.status_code >= 500:
                retry_after = r.headers.get("Retry-After", "")
                try:
                    delay = max(1, min(90, int(float(retry_after)))) if retry_after else min(60, 5 * (2 ** (attempt - 1)))
                except ValueError:
                    delay = min(60, 5 * (2 ** (attempt - 1)))
                if attempt < 5:
                    print(f"Cloudflare image API returned {r.status_code} for this scene; retry {attempt}/5 in {delay}s.", flush=True)
                    time.sleep(delay)
                    continue
            r.raise_for_status()
            break
        except requests.RequestException:
            if attempt == 5:
                raise
            delay = min(60, 5 * (2 ** (attempt - 1)))
            print(f"Cloudflare image request attempt {attempt}/5 failed; retrying in {delay}s.", flush=True)
            time.sleep(delay)
    if r is None:
        raise RuntimeError("Cloudflare image request did not return a response.")
    r.raise_for_status()

    if r.headers.get("content-type", "").startswith("image/"):
        return r.content
        
    j = r.json()
    return base64.b64decode(j.get("result", j)["image"])

_OVH_LAST_CALL = 0.0

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

def ai_horde_image(prompt):
    """Anonymous AI Horde backup provider; wait up to 10 minutes for a worker."""
    base = "https://aihorde.net/api/v2"
    headers = {
        "apikey": "0000000000",
        "Client-Agent": "stickman-lab:1.0:https://github.com/manojkumar166-png/stickman-lab"
    }
    payload = {
        "prompt": prompt + "###text, watermark, logo, blurry, low quality",
        "params": {"width": 1024, "height": 576, "steps": 20, "n": 1},
        "nsfw": False,
        "censor_nsfw": True,
        "trusted_workers": False
    }
    response = requests.post(base + "/generate/async", headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    job_id = response.json().get("id")
    if not job_id:
        raise RuntimeError("AI Horde returned no job ID")
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        time.sleep(5)
        check = requests.get(base + f"/generate/check/{job_id}", headers=headers, timeout=45)
        check.raise_for_status()
        state = check.json()
        if state.get("faulted"):
            raise RuntimeError("AI Horde generation faulted")
        if state.get("done"):
            break
    else:
        raise TimeoutError("AI Horde queue timed out after 10 minutes")
    result = requests.get(base + f"/generate/status/{job_id}", headers=headers, timeout=60)
    result.raise_for_status()
    generations = result.json().get("generations") or []
    if not generations or not generations[0].get("img"):
        raise RuntimeError("AI Horde completed without an image")
    image_data = generations[0]["img"]
    if image_data.startswith("data:") and "," in image_data:
        return valid_png(base64.b64decode(image_data.split(",", 1)[1]))
    if image_data.startswith(("http://", "https://")):
        download = requests.get(image_data, timeout=(20, 180))
        download.raise_for_status()
        return valid_png(download.content)
    return valid_png(base64.b64decode(image_data, validate=True))

async def generate_all_ai_images(scenes, out_dir, width, height):
    global _CLOUDFLARE_RATE_LIMITED
    _CLOUDFLARE_RATE_LIMITED = False
    print("Generating AI illustrations: Cloudflare primary -> AI Horde backup -> OVHcloud final fallback.")
    os.makedirs(out_dir, exist_ok=True)
    results = []
    failures = []

    for i, scene in enumerate(scenes, 1):
        prompt = build_prompt(scene.get("visual", "science illustration"))
        providers = (
            ("Cloudflare FLUX.2 Klein", lambda: valid_png(cf_image_cheap(prompt))),
            ("AI Horde", lambda: ai_horde_image(prompt)),
            ("OVHcloud SDXL", lambda: ovh_image(prompt))
        )
        image_data = None
        errors = []
        for provider_name, generate in providers:
            # A 429 is a shared account throttle, not a scene-specific failure.
            # Never repeat the same throttled request for every scene.
            attempts = 1 if provider_name.startswith("Cloudflare") else (2 if provider_name.startswith("OVHcloud") else 1)
            if provider_name.startswith("Cloudflare") and _CLOUDFLARE_RATE_LIMITED:
                print(f"  Scene {i}/{len(scenes)}: skipping Cloudflare; rate limit already reached. Falling back.", flush=True)
                continue
            for attempt in range(1, attempts + 1):
                try:
                    print(f"  Scene {i}/{len(scenes)}: trying {provider_name} (attempt {attempt}/{attempts})", flush=True)
                    image_data = generate()
                    image_path = os.path.join(out_dir, f"scene-{i:03d}.png")
                    with open(image_path, "wb") as image_file:
                        image_file.write(image_data)
                    print(f"  Scene {i}/{len(scenes)}: generated with {provider_name}", flush=True)
                    break
                except Exception as error:
                    errors.append(f"{provider_name} attempt {attempt}: {error}")
                    print(f"  Scene {i}: {provider_name} failed: {error}", flush=True)
                    if attempt < attempts:
                        delay = min(60, 5 * (2 ** (attempt - 1)))
                        print(f"  Retrying {provider_name} in {delay}s.", flush=True)
                        time.sleep(delay)
            if image_data is not None:
                break

        if image_data is None:
            failures.append(f"Scene {i}: " + " | ".join(errors))
            results.append((i, None))
        else:
            results.append((i, image_data))

        if i < len(scenes):
            time.sleep(2)

    if failures:
        raise RuntimeError(
            "All configured image providers failed for one or more scenes; "
            "no stickman fallback is used. " + " || ".join(failures)
        )
    print(f"Successfully generated and saved all {len(results)} AI scene images.", flush=True)
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