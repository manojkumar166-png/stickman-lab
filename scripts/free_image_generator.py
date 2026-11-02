#!/usr/bin/env python3
"""Free-tier-only image generation with sequential provider fallback."""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import random
import sys
import time
from pathlib import Path

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "free-image-generator" / "output"
LOG_PATH = ROOT / "free-image-generator" / "provider-log.jsonl"
TIMEOUT = (20, 180)


def log(event: dict) -> None:
    event["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    print(json.dumps(event, ensure_ascii=False), flush=True)


def retry_delay(response: requests.Response | None, attempt: int) -> int:
    if response is not None:
        raw = response.headers.get("Retry-After", "")
        try:
            return max(2, min(90, int(float(raw))))
        except (TypeError, ValueError):
            pass
    return min(60, 3 * (2 ** (attempt - 1)) + random.randint(0, 2))


def request_with_retries(provider: str, method: str, url: str, *, headers: dict,
                         json_body: dict, attempts: int = 3) -> requests.Response:
    last_error = None
    for attempt in range(1, attempts + 1):
        response = None
        try:
            response = requests.request(method, url, headers=headers, json=json_body, timeout=TIMEOUT)
            if response.status_code == 200:
                return response
            # Invalid credentials, unsupported models, and other permanent 4xx
            # errors should move straight to the next provider.
            if 400 <= response.status_code < 500 and response.status_code not in (408, 409, 425, 429):
                raise RuntimeError(f"{provider}: permanent HTTP {response.status_code}: {response.text[:800]}")
            last_error = RuntimeError(f"{provider}: HTTP {response.status_code}: {response.text[:800]}")
        except requests.RequestException as exc:
            last_error = exc
        if attempt < attempts:
            delay = retry_delay(response, attempt)
            log({"provider": provider, "status": "retry", "attempt": attempt,
                 "next_attempt_in_seconds": delay, "error": str(last_error)[:800]})
            time.sleep(delay)
    raise RuntimeError(f"{provider}: exhausted {attempts} attempts: {last_error}")


def validate_image(data: bytes) -> bytes:
    if not data:
        raise ValueError("Provider returned an empty image.")
    with Image.open(io.BytesIO(data)) as image:
        image.verify()
    with Image.open(io.BytesIO(data)) as image:
        image = image.convert("RGB")
        output = io.BytesIO()
        image.save(output, format="PNG", optimize=True)
        return output.getvalue()


def ovhcloud(prompt: str) -> bytes:
    url = "https://stable-diffusion-xl.endpoints.kepler.ai.cloud.ovh.net/api/text2image"
    headers = {"accept": "application/octet-stream", "Content-Type": "application/json"}
    response = request_with_retries("ovhcloud-sdxl", "POST", url, headers=headers,
        json_body={"prompt": prompt, "negative_prompt": "blurry, low quality, watermark, text, logo"})
    if response.headers.get("Content-Type", "").startswith("application/json"):
        payload = response.json()
        encoded = payload.get("data", [{}])[0].get("b64_json")
        if not encoded:
            raise ValueError(f"OVHcloud response did not contain image bytes: {str(payload)[:800]}")
        return validate_image(base64.b64decode(encoded))
    return validate_image(response.content)


def zhipu(prompt: str) -> bytes:
    token = os.getenv("ZHIPU_API_KEY", "").strip()
    if not token:
        raise RuntimeError("Zhipu skipped: ZHIPU_API_KEY is not configured.")
    response = request_with_retries("zhipu-cogview-3-flash", "POST",
        "https://open.bigmodel.cn/api/paas/v4/images/generations",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json_body={"model": "cogview-3-flash", "prompt": prompt, "size": "1024x1024"})
    payload = response.json()
    items = payload.get("data") or []
    if not items:
        raise ValueError(f"Zhipu response contained no image: {str(payload)[:800]}")
    item = items[0]
    if item.get("b64_json"):
        return validate_image(base64.b64decode(item["b64_json"]))
    if not item.get("url"):
        raise ValueError(f"Zhipu response contained no image URL: {str(payload)[:800]}")
    downloaded = requests.get(item["url"], timeout=TIMEOUT)
    downloaded.raise_for_status()
    return validate_image(downloaded.content)


def pollinations(prompt: str) -> bytes:
    encoded = requests.utils.quote(prompt, safe="")
    response = requests.get(f"https://image.pollinations.ai/prompt/{encoded}",
        params={"width": 1024, "height": 576, "nologo": "true"},
        headers={"Accept": "image/*"}, timeout=TIMEOUT)
    response.raise_for_status()
    return validate_image(response.content)


PROVIDERS = [
    ("ovhcloud-sdxl", ovhcloud),
    ("zhipu-cogview-3-flash", zhipu),
    ("pollinations-free-classic", pollinations),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate an image using free-tier APIs only.")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--height", type=int, default=576)
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    if not args.prompt.strip():
        parser.error("Prompt must not be empty.")
    if not (256 <= args.width <= 2048 and 256 <= args.height <= 2048):
        parser.error("Width and height must each be between 256 and 2048 pixels.")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = Path(args.output) if args.output else OUT_DIR / "generated-image.png"
    failures = []
    for name, provider in PROVIDERS:
        started = time.monotonic()
        try:
            image_bytes = provider(args.prompt.strip())
            image_bytes = validate_image(image_bytes)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(image_bytes)
            log({"provider": name, "status": "success", "output": str(output_path),
                 "bytes": len(image_bytes), "elapsed_seconds": round(time.monotonic() - started, 2)})
            print(f"IMAGE_OUTPUT={output_path}")
            return 0
        except Exception as exc:
            message = str(exc)
            failures.append({"provider": name, "error": message})
            log({"provider": name, "status": "failed", "elapsed_seconds": round(time.monotonic() - started, 2),
                 "error": message[:1200]})
            print(f"{name} failed; moving to next free provider: {message}", file=sys.stderr, flush=True)

    log({"status": "all_providers_failed", "failures": failures})
    print("All configured free image providers failed. No paid provider was called.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
