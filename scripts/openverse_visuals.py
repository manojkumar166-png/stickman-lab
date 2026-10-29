"""Find reusable science illustrations through multiple providers.

Provider order: Openverse CC0/Public Domain, Wikimedia Commons public domain/CC0,
then optional Pixabay, Unsplash, and Pexels APIs when their keys are configured. The
manifest preserves provider, source, and license metadata; metadata is not a
legal guarantee, so review the manifest before publishing.
"""
from __future__ import annotations

import json
import os
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

OPENVERSE_API = "https://api.openverse.org/v1/images/"
WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"
PIXABAY_API = "https://pixabay.com/api/"
UNSPLASH_API = "https://api.unsplash.com/search/photos"
TIMEOUT = 30
MAX_IMAGE_BYTES = 12 * 1024 * 1024
USER_AGENT = "stickman-lab-science-visuals/1.1 (educational video pipeline)"
ALLOWED_LICENSES = {"cc0", "pdm", "public domain", "public-domain", "cc-zero"}

def _request(url: str, timeout: int = TIMEOUT, headers: dict | None = None) -> bytes:
    request_headers = {"User-Agent": USER_AGENT}
    if headers:
        request_headers.update(headers)
    req = urllib.request.Request(url, headers=request_headers)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        data = response.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("response exceeds 12 MiB limit")
    return data

def _json(url: str, headers: dict | None = None) -> dict:
    return json.loads(_request(url, headers=headers).decode("utf-8"))

def _with_retry(url: str, headers: dict | None = None) -> dict:
    last_error = None
    for attempt in range(4):
        try:
            return _json(url, headers=headers)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"provider request failed: {last_error}")

def _search_openverse(query: str) -> list[dict]:
    params = urllib.parse.urlencode({
        "q": query[:160], "license": "cc0,pdm", "page_size": 10,
        "mature": "false", "filter_dead": "true",
    })
    payload = _with_retry(OPENVERSE_API + "?" + params)
    items = []
    for item in payload.get("results", []):
        license_name = str(item.get("license", "")).lower()
        if license_name in ALLOWED_LICENSES and item.get("url") and item.get("foreign_landing_url"):
            items.append({
                "id": "openverse:" + str(item.get("id") or item["url"]),
                "url": item["url"], "source_page": item["foreign_landing_url"],
                "title": item.get("title"), "creator": item.get("creator"),
                "license": item.get("license"), "license_url": item.get("license_url"),
                "provider": "Openverse", "attribution": item.get("attribution"),
            })
    return items

def _search_wikimedia(query: str) -> list[dict]:
    params = urllib.parse.urlencode({
        "action": "query", "generator": "search",
        "gsrsearch": f'filetype:bitmap "{query}" (CC0 OR "public domain")',
        "gsrnamespace": 6, "gsrlimit": 10, "prop": "imageinfo",
        "iiprop": "url|extmetadata", "iiurlwidth": 1400, "format": "json",
    })
    payload = _with_retry(WIKIMEDIA_API + "?" + params)
    items = []
    for page in payload.get("query", {}).get("pages", {}).values():
        info_list = page.get("imageinfo") or []
        if not info_list:
            continue
        info = info_list[0]
        meta = info.get("extmetadata") or {}
        license_name = str((meta.get("LicenseShortName") or {}).get("value", "")).strip()
        license_url = str((meta.get("LicenseUrl") or {}).get("value", "")).strip()
        normalized = license_name.lower()
        if normalized not in ALLOWED_LICENSES and not ("public domain" in normalized or "cc0" in normalized):
            continue
        image_url = info.get("thumburl") or info.get("url")
        if not image_url:
            continue
        items.append({
            "id": "wikimedia:" + str(page.get("pageid")),
            "url": image_url, "source_page": page.get("canonicalurl") or info.get("descriptionurl"),
            "title": page.get("title"), "creator": (meta.get("Artist") or {}).get("value"),
            "license": license_name, "license_url": license_url,
            "provider": "Wikimedia Commons",
            "attribution": (meta.get("Credit") or {}).get("value"),
        })
    return items

def _search_pixabay(query: str) -> list[dict]:
    key = os.environ.get("PIXABAY_API_KEY")
    if not key:
        return []
    params = urllib.parse.urlencode({
        "key": key, "q": query[:100], "image_type": "illustration",
        "safesearch": "true", "per_page": 10,
    })
    payload = _with_retry(PIXABAY_API + "?" + params)
    return [{
        "id": "pixabay:" + str(item.get("id")), "url": item.get("largeImageURL") or item.get("webformatURL"),
        "source_page": item.get("pageURL"), "title": query,
        "creator": item.get("user"), "license": "Pixabay Content License",
        "license_url": "https://pixabay.com/service/license-summary/",
        "provider": "Pixabay", "attribution": item.get("user"),
    } for item in payload.get("hits", []) if item.get("largeImageURL") or item.get("webformatURL")]

def _search_unsplash(query: str) -> list[dict]:
    key = os.environ.get("UNSPLASH_ACCESS_KEY")
    if not key:
        return []
    params = urllib.parse.urlencode({"query": query[:100], "per_page": 10, "content_filter": "high"})
    payload = _with_retry(UNSPLASH_API + "?" + params, {"Authorization": f"Client-ID {key}"})
    items = []
    for item in payload.get("results", []):
        urls = item.get("urls") or {}
        image_url = urls.get("regular") or urls.get("small")
        if not image_url:
            continue
        items.append({
            "id": "unsplash:" + str(item.get("id")), "url": image_url,
            "source_page": (item.get("links") or {}).get("html"),
            "title": (item.get("alt_description") or query),
            "creator": ((item.get("user") or {}).get("name")),
            "license": "Unsplash License",
            "license_url": "https://unsplash.com/license",
            "provider": "Unsplash",
            "attribution": ((item.get("user") or {}).get("name")),
        })
    return items

def _search_pexels(query: str) -> list[dict]:
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        return []
    params = urllib.parse.urlencode({"query": query[:100], "per_page": 10, "orientation": "landscape"})
    payload = _with_retry("https://api.pexels.com/v1/search?" + params, {"Authorization": key})
    items = []
    for photo in payload.get("photos", []):
        src = photo.get("src") or {}
        image_url = src.get("large") or src.get("original")
        if not image_url:
            continue
        items.append({
            "id": "pexels:" + str(photo.get("id")),
            "url": image_url,
            "source_page": photo.get("url"),
            "title": photo.get("alt") or query,
            "creator": photo.get("photographer"),
            "license": "Pexels License",
            "license_url": "https://www.pexels.com/license/",
            "provider": "Pexels",
            "attribution": photo.get("photographer"),
        })
    return items

def _image_signature(data: bytes) -> str | None:
    if data.startswith(bytes((137, 80, 78, 71, 13, 10, 26, 10))):
        return ".png"
    if data.startswith(bytes((255, 216, 255))):
        return ".jpg"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return ".webp"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    return None
def _scene_queries(topic: str, scene: dict) -> list[str]:
    """Build short search phrases from scene meaning, not Gemini's poetic art direction."""
    text = " ".join(str(scene.get(key) or "") for key in ("title", "narration", "visual_description", "visual"))
    text = re.sub(r"[^A-Za-z0-9\s'-]", " ", text).lower()
    text = " ".join(text.split())
    topic_clean = re.sub(r"[^A-Za-z0-9\s'-]", " ", topic).lower()
    topic_clean = " ".join(topic_clean.split())

    actions = [
        (r"\b(dream|dreaming|dreams)\b", "anime man dreaming"),
        (r"\b(wake|wakes|waking|awake|awakes|awaken)\b", "anime man waking up"),
        (r"\b(sleep|sleeps|sleeping|asleep)\b", "anime man sleeping"),
        (r"\b(think|thinks|thinking|thought|wonder|wonders|wondering)\b", "anime man thinking"),
        (r"\b(walk|walks|walking|stroll|strolling)\b", "anime man walking"),
        (r"\b(run|runs|running|jog|jogging)\b", "anime man running"),
        (r"\b(cold|chill|chilly|shiver|shivers|shivering|goosebumps|gooseflesh)\b", "anime person feeling cold shivering"),
        (r"\b(scared|fear|afraid|fright|frightened|terrified)\b", "anime person scared"),
        (r"\b(remember|memory|memories|recall|recalling)\b", "anime person remembering thinking"),
        (r"\b(study|studies|studying|learn|learning|read|reading)\b", "anime person studying"),
        (r"\b(eat|eats|eating|food|hungry)\b", "anime person eating"),
        (r"\b(talk|talks|talking|speak|speaks|speaking|conversation)\b", "anime people talking"),
        (r"\b(look|looks|looking|see|sees|seeing|watch|watching)\b", "anime person looking"),
    ]
    candidates = []
    for pattern, phrase in actions:
        if re.search(pattern, text):
            candidates.append(phrase)
    # Short topical phrases help find subject-specific images after the generic action search.
    if topic_clean:
        candidates.extend([f"anime {topic_clean[:55]}", topic_clean[:70]])
    # Keep short, plain searches and try each only once.
    return list(dict.fromkeys(q.strip() for q in candidates if q.strip())) or ["anime man thinking", "anime person", topic_clean[:70] or "science illustration"]

def _search_all(query: str) -> list[dict]:
    # Collect candidates from every provider, not just the first provider that
    # responds. If its image URLs fail during download, later providers remain
    # available as fallback candidates.
    providers = [
        ("Openverse CC0/Public Domain", _search_openverse),
        ("Wikimedia Commons Public Domain/CC0", _search_wikimedia),
        ("Pixabay", _search_pixabay),
        ("Unsplash", _search_unsplash),
        ("Pexels", _search_pexels),
    ]
    all_results = []
    for provider_name, search_fn in providers:
        try:
            results = search_fn(query)
            all_results.extend(results)
            print(f"{provider_name}: found {len(results)} candidates for {query!r}", flush=True)
        except Exception as exc:
            print(f"{provider_name}: search unavailable ({exc}); continuing with other providers", flush=True)
    return all_results

def download_scene_illustrations(story: dict, output_dir: Path) -> list[Path]:
    """Try free, no-key sources first; missing images become text-only scenes."""
    scenes = story.get("scenes") or []
    if not scenes:
        raise RuntimeError("Story has no scenes; cannot search for illustrations.")
    output_dir.mkdir(parents=True, exist_ok=True)
    topic = str(story.get("topic") or "science")
    manifest, paths, used_ids = [], [], set()
    rng = random.SystemRandom()

    for index, scene in enumerate(scenes, start=1):
        queries = _scene_queries(topic, scene)
        base_query = queries[0]
        chosen = None
        errors = []
        for query in queries:
            candidates = _search_all(query)
            rng.shuffle(candidates)
            for item in candidates:
                if not item.get("url") or item.get("id") in used_ids:
                    continue
                try:
                    data = _request(str(item["url"]))
                    suffix = _image_signature(data)
                    if not suffix:
                        raise ValueError("download is not a recognized image format")
                    if len(data) < 8_000:
                        raise ValueError("image is suspiciously small")
                    chosen = (item, data, suffix, query)
                    break
                except Exception as exc:
                    errors.append(f"{item.get('provider')}: {exc}")
            if chosen:
                break

        if not chosen:
            # Do not abort the whole video because one scene has no reusable image.
            scene.pop("_external_image_path", None)
            manifest.append({
                "scene_index": index,
                "scene_title": str(scene.get("title") or ""),
                "search_query": base_query,
                "file": None,
                "provider": None,
                "license": None,
                "status": "text-only fallback",
                "error": "; ".join(errors[-3:]) or "No eligible image found after query retries",
            })
            print(f"Scene {index}/{len(scenes)}: no eligible image found; using text-only background.", flush=True)
            continue

        item, data, suffix, successful_query = chosen
        used_ids.add(item.get("id"))
        path = output_dir / f"scene-{index:03d}{suffix}"
        path.write_bytes(data)
        scene["_external_image_path"] = str(path.resolve())
        paths.append(path)
        manifest.append({
            "scene_index": index, "scene_title": str(scene.get("title") or ""),
            "search_query": successful_query, "file": path.name, "title": item.get("title"),
            "creator": item.get("creator"), "license": item.get("license"),
            "license_url": item.get("license_url"), "source_page": item.get("source_page"),
            "image_url": item.get("url"), "provider": item.get("provider"),
            "attribution": item.get("attribution"), "status": "downloaded",
        })
        print(f"Illustration {index}/{len(scenes)} via {item.get('provider')}: {successful_query} -> {path.name}", flush=True)

    (output_dir / "image-attribution-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return paths
