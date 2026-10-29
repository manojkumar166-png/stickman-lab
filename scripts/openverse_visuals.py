"""Find and download public-domain/CC0 illustrations for every story scene.

Only CC0 and Public Domain Mark results are accepted. Openverse metadata is not
a legal guarantee; source/creator/license URLs are preserved in the manifest.
"""
from __future__ import annotations

import concurrent.futures
import json
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://api.openverse.org/v1/images/"
ALLOWED_LICENSES = {"cc0", "pdm"}
MAX_WORKERS = 3
TIMEOUT = 20
MAX_IMAGE_BYTES = 12 * 1024 * 1024
USER_AGENT = "stickman-lab-public-domain-illustrations/1.0"

def _request(url: str, timeout: int = TIMEOUT) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read(MAX_IMAGE_BYTES + 1)

def _search(query: str) -> list[dict]:
    params = urllib.parse.urlencode({
        "q": query[:200],
        "license": "cc0,pdm",
        "page_size": 10,
        "mature": "false",
        "filter_dead": "true",
    })
    last_error = None
    for attempt in range(3):
        try:
            payload = json.loads(_request(API + "?" + params).decode("utf-8"))
            return [
                item for item in payload.get("results", [])
                if str(item.get("license", "")).lower() in ALLOWED_LICENSES
                and item.get("url")
                and item.get("foreign_landing_url")
            ]
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Openverse search failed for {query!r}: {last_error}")

def _safe_name(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-").lower()
    return value[:60] or "scene"

def _image_signature(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith((b"RIFF",)) and data[8:12] == b"WEBP":
        return ".webp"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    return None

def _scene_query(topic: str, scene: dict) -> str:
    parts = [str(scene.get(k) or "") for k in ("title", "visual", "visual_description")]
    # Narration can be long/noisy; use it only when visual metadata is missing.
    if not any(parts):
        parts.append(str(scene.get("narration") or "")[:100])
    cleaned = " ".join(" ".join(parts).split())
    cleaned = re.sub(r"[^\w\s,-]", " ", cleaned)
    cleaned = " ".join(cleaned.split())
    # Prefer the scene subject, with topic as context rather than the whole narration.
    return (cleaned or topic)[:180]

def download_scene_illustrations(story: dict, output_dir: Path) -> list[Path]:
    scenes = story.get("scenes") or []
    if not scenes:
        raise RuntimeError("Story has no scenes; cannot search for illustrations.")
    output_dir.mkdir(parents=True, exist_ok=True)
    topic = str(story.get("topic") or "science")
    queries = [_scene_query(topic, scene) for scene in scenes]
    unique_queries = list(dict.fromkeys(q.casefold() for q in queries))
    original_by_normalized = {q.casefold(): q for q in queries}

    # Bounded concurrency; no search-engine scraping and no image-generation API.
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        search_results = list(pool.map(_search, [original_by_normalized[q] for q in unique_queries]))
    results_by_query = dict(zip(unique_queries, search_results))

    rng = random.SystemRandom()
    manifest = []
    paths = []
    used_ids = set()
    for index, (scene, query) in enumerate(zip(scenes, queries), start=1):
        candidates = list(results_by_query[query.casefold()])
        # Randomize only among public-domain/CC0 candidates returned for this scene.
        rng.shuffle(candidates)
        chosen = None
        last_error = None
        for item in candidates:
            if item.get("id") in used_ids:
                continue
            try:
                data = _request(str(item["url"]))
                if len(data) > MAX_IMAGE_BYTES:
                    raise ValueError("image exceeds 12 MiB limit")
                suffix = _image_signature(data)
                if not suffix:
                    raise ValueError("download is not a recognized image format")
                if len(data) < 8_000:
                    raise ValueError("image is suspiciously small")
                chosen = (item, data, suffix)
                break
            except (urllib.error.URLError, TimeoutError, ValueError) as exc:
                last_error = str(exc)
        if not chosen:
            reason = f"; last download error: {last_error}" if last_error else ""
            raise RuntimeError(
                f"No downloadable CC0/Public Domain illustration for scene {index} "
                f"({scene.get('title')!r}), query={query!r}; found {len(candidates)} "
                f"eligible candidates{reason}. Stopping before narration/video rendering."
            )
        item, data, suffix = chosen
        used_ids.add(item.get("id"))
        path = output_dir / f"scene-{index:03d}{suffix}"
        path.write_bytes(data)
        scene["_external_image_path"] = str(path.resolve())
        paths.append(path)
        manifest.append({
            "scene_index": index,
            "scene_title": str(scene.get("title") or ""),
            "search_query": query,
            "file": path.name,
            "title": item.get("title"),
            "creator": item.get("creator"),
            "license": item.get("license"),
            "license_version": item.get("license_version"),
            "license_url": item.get("license_url"),
            "source_page": item.get("foreign_landing_url"),
            "image_url": item.get("url"),
            "provider": item.get("provider"),
            "source": item.get("source"),
            "width": item.get("width"),
            "height": item.get("height"),
            "attribution": item.get("attribution"),
        })
        print(f"Public-domain visual {index}/{len(scenes)}: {query} -> {path.name}", flush=True)

    (output_dir / "image-attribution-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return paths
