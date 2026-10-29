"""Optional free-tier Cloudflare Workers AI artwork for the isolated free-science workflow.

Uses the same provider/model already present in scripts/make_art.py, but with
scene-grounded 3D animated-feature prompts. Falls back cleanly when credentials
or free quota are unavailable. No paid provider is called by this module.
"""
import base64
import io
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

ACCOUNT_ID = os.getenv("CF_ACCOUNT_ID", "").strip()
API_TOKEN = os.getenv("CF_API_TOKEN", "").strip()
MODEL = "@cf/black-forest-labs/flux-2-klein-4b"
API_URL = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/ai/run/{MODEL}" if ACCOUNT_ID else ""
HEADERS = {"Authorization": f"Bearer {API_TOKEN}"}
STYLE = (
    "High-end 3D animated feature film frame, beautifully art-directed, "
    "cinematic global illumination, soft physically based lighting, rich but natural color, "
    "detailed materials, believable depth, expressive appealing 3D forms, polished professional CGI. "
    "Accurately depict the specific science described; do not substitute a generic sphere or unrelated object. "
    "One clear focal subject, carefully composed 16:9 wide shot, visually rich environment, no words, no letters, no watermark."
)

def _prompt(scene):
    title = str(scene.get("title") or "Science concept").strip()
    narration = " ".join(str(scene.get("narration") or "").split())[:900]
    visual = " ".join(str(scene.get("visual") or "").split())[:500]
    return (
        f"Create one image for this exact educational science scene. Scene title: {title}. "
        f"Scene visual direction: {visual or title}. Narration context: {narration}. "
        "Show the actual subject and action stated in the scene, scientifically plausible, with relevant objects/environment. "
        "Do not add labels, diagrams, text, captions, logos, or unrelated planets/orbs. "
        f"Visual style: {STYLE}"
    )

def _request_image(scene, index, width, height):
    if not API_URL or not API_TOKEN:
        return index, None, "Cloudflare AI credentials are not configured"
    prompt = _prompt(scene)
    # Cloudflare's existing endpoint accepts multipart form fields.
    last_error = "unknown error"
    for attempt in range(3):
        try:
            response = requests.post(
                API_URL,
                headers=HEADERS,
                files={
                    "prompt": (None, prompt),
                    "width": (None, str(min(1024, int(width)))),
                    "height": (None, str(min(1024, int(height)))),
                },
                timeout=100,
            )
            if response.status_code in (429, 500, 502, 503, 504):
                last_error = f"HTTP {response.status_code}"
                if attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
            response.raise_for_status()
            if response.headers.get("content-type", "").startswith("image/"):
                return index, response.content, None
            payload = response.json()
            result = payload.get("result", payload)
            encoded = result.get("image") if isinstance(result, dict) else None
            if not encoded:
                raise RuntimeError("Provider response did not contain an image")
            return index, base64.b64decode(encoded), None
        except Exception as exc:
            last_error = str(exc)[:300]
            if attempt < 2:
                time.sleep(2 ** attempt)
    return index, None, last_error

def generate_ai_images(scenes, width, height, workers=3):
    """Generate images concurrently; never block fallback visuals on one bad scene."""
    if not API_URL or not API_TOKEN:
        print("Cloudflare AI secrets missing; using the free local/image-search fallback.")
        return {}
    results = {}
    print(f"Generating scene-matched 3D artwork with {MODEL} (up to {workers} concurrent requests)...", flush=True)
    with ThreadPoolExecutor(max_workers=max(1, min(int(workers), 3))) as pool:
        futures = {
            pool.submit(_request_image, scene, i, width, height): (i, scene)
            for i, scene in enumerate(scenes, 1)
        }
        for future in as_completed(futures):
            index, data, error = future.result()
            title = str(futures[future][1].get("title") or f"Scene {index}")
            if data:
                results[index] = data
                print(f"AI image {index}/{len(scenes)} ready: {title}", flush=True)
            else:
                print(f"AI image {index}/{len(scenes)} unavailable: {error}; will use fallback.", flush=True)
    print(f"AI artwork result: {len(results)}/{len(scenes)} scenes generated.", flush=True)
    return results

def save_ai_image(image_bytes, scene, out_path, width, height):
    """Normalize generated image to a stable 16:9 still; no animation or zoom."""
    with Image.open(io.BytesIO(image_bytes)) as source:
        image = ImageOps.fit(source.convert("RGB"), (int(width), int(height)), method=Image.Resampling.LANCZOS)
    image.save(out_path, "PNG", optimize=True)
    return {
        "scene": None,
        "scene_title": str(scene.get("title") or "Science scene"),
        "style": "3D animated-feature-inspired AI image",
        "title": str(scene.get("title") or "Generated science artwork"),
        "url": "",
        "source_url": "https://developers.cloudflare.com/workers-ai/",
        "license": "Generated image; check applicable model/provider terms before commercial use",
        "artist": "Cloudflare Workers AI / FLUX.2 Klein 4B",
        "description": "Scene-specific generated image based on the scene title, visual direction, and narration.",
    }
