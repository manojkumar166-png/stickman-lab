"""Generate one original AI illustration per scene using Cloudflare Workers AI.

Required GitHub Actions secrets:
  CLOUDFLARE_ACCOUNT_ID
  CLOUDFLARE_API_TOKEN (Workers AI Read permission)

The workflow intentionally fails clearly rather than silently falling back to procedural art.
"""
from __future__ import annotations

import base64
import json
import os
import re
import time
from pathlib import Path

import requests

MODEL = "@cf/black-forest-labs/flux-1-schnell"
STYLE = (
    "Original hand-painted 2D science storybook illustration, cinematic composition, "
    "rich environmental detail, delicate painterly textures, layered foreground and "
    "background, atmospheric perspective, soft natural lighting, carefully designed "
    "color harmony, expressive but scientifically plausible, premium illustrated "
    "educational film art. Entire image is a finished illustration, not a diagram, "
    "not a UI, no captions, no letters, no watermark. Absolutely not 3D, not CGI, "
    "not a render, no photorealism."
)

def safe_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-")[:64] or "scene"

def make_prompt(scene: dict, topic: str, index: int) -> str:
    description = str(scene.get("visual_description") or scene.get("visual") or
                      scene.get("image_prompt") or scene.get("narration") or topic)
    narration = str(scene.get("narration", "")).strip()
    return (
        f"{STYLE}\nTopic: {topic}. Scene {index + 1}.\n"
        f"Scene-specific visual: {description[:1200]}\n"
        f"Scientific context to depict accurately: {narration[:500]}\n"
        "Use a wide 16:9 landscape composition. Build a clear focal point and "
        "supporting environmental storytelling. The scene must be visually distinct "
        "from other scenes while retaining a cohesive storybook art direction."
    )

def generate_scene_images(story: dict, output_dir: Path, width: int, height: int) -> list[dict]:
    account = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
    token = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
    if not account or not token:
        raise RuntimeError(
            "AI illustration setup incomplete. Add GitHub Actions secrets "
            "CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN (Workers AI Read permission). "
            "No procedural-art fallback is enabled."
        )
    endpoint = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{MODEL}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    output_dir.mkdir(parents=True, exist_ok=True)
    scenes = story.get("scenes") or []
    credits = []
    session = requests.Session()
    for index, scene in enumerate(scenes):
        path = output_dir / f"scene-{index:03d}.png"
        if path.exists() and path.stat().st_size > 10_000:
            credits.append({"file": path.name, "source": "Cloudflare Workers AI", "model": MODEL})
            continue
        prompt = make_prompt(scene, str(story.get("topic", "Science")), index)
        payload = {"prompt": prompt, "steps": 4}
        last_error = None
        for attempt in range(3):
            try:
                response = session.post(endpoint, headers=headers, json=payload, timeout=240)
                if response.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                    time.sleep(8 * (attempt + 1))
                    continue
                if not response.ok:
                    raise RuntimeError(f"Cloudflare AI HTTP {response.status_code}: {response.text[:1200]}")
                content_type = response.headers.get("content-type", "")
                if "image/" in content_type:
                    image_bytes = response.content
                else:
                    result = response.json()
                    if result.get("success") is False:
                        raise RuntimeError(f"Cloudflare AI error: {result.get('errors')}")
                    data = result.get("result", {})
                    encoded = data.get("image") or data.get("data")
                    if isinstance(encoded, list) and encoded:
                        encoded = encoded[0]
                    if not encoded:
                        raise RuntimeError(f"Unexpected image response: {json.dumps(result)[:1200]}")
                    image_bytes = base64.b64decode(encoded)
                if len(image_bytes) < 10_000:
                    raise RuntimeError("Image response was unexpectedly small.")
                path.write_bytes(image_bytes)
                credits.append({"file": path.name, "source": "Cloudflare Workers AI",
                                "model": MODEL, "prompt": prompt})
                print(f"Generated {path.name} ({index + 1}/{len(scenes)})", flush=True)
                break
            except Exception as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(5 * (attempt + 1))
        else:
            raise RuntimeError(f"Image generation failed for scene {index + 1}: {last_error}") from last_error
    return credits
