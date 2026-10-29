"""Find reusable science illustrations by searching public website pages (no provider APIs)."""
from __future__ import annotations

import json
import random
import re
import urllib.parse
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright
from scripts.generate_story import _call_gemini

TIMEOUT = 25
MAX_IMAGE_BYTES = 12 * 1024 * 1024
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"

# Public search pages only. These are normal browser URLs, not provider API endpoints.
PUBLIC_SEARCHES = [
    ("Openverse", "https://openverse.org/search/image?q={query}&license=cc0,pdm"),
    ("Wikimedia Commons", "https://commons.wikimedia.org/w/index.php?search={query}&title=Special:MediaSearch&type=image"),
    ("Pixabay", "https://pixabay.com/images/search/{path_query}/"),
    ("Unsplash", "https://unsplash.com/s/photos/{path_query}"),
    ("Pexels", "https://www.pexels.com/search/{path_query}/"),
]

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

def _public_page_url(template: str, query: str) -> str:
    return template.format(
        query=urllib.parse.quote_plus(query),
        path_query=urllib.parse.quote(query.lower()),
    )

def _search_public_page(browser, provider: str, url: str, query: str) -> list[dict]:
    """Open a provider's human-facing search page and collect linked image results."""
    page = browser.new_page(user_agent=USER_AGENT, viewport={"width": 1365, "height": 900})
    items = []
    try:
        response = page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT * 1000)
        if response is None or response.status >= 400:
            raise RuntimeError(f"public search page returned HTTP {response.status if response else 'no response'}")
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass
        page.wait_for_timeout(1200)
        # Public search pages differ; use linked image cards rather than API payloads.
        cards = page.locator("a").evaluate_all("""anchors => anchors.map(a => {
          const imgs = Array.from(a.querySelectorAll('img'));
          if (!imgs.length) return null;
          const img = imgs.find(i => (i.currentSrc || i.src || i.getAttribute('data-src') || '').startsWith('http')) || imgs[0];
          const image = img.currentSrc || img.src || img.getAttribute('data-src') || '';
          const srcset = img.getAttribute('srcset') || img.getAttribute('data-srcset') || '';
          const candidate = srcset.split(',').map(s => s.trim().split(/\\s+/)[0]).filter(Boolean).pop();
          return {href: a.href || '', image: image || candidate || '', alt: img.alt || '', title: a.getAttribute('aria-label') || a.title || ''};
        }).filter(x => x && x.href && x.image && /^https?:/.test(x.image))""")
        seen = set()
        for card in cards:
            source_page, image_url = card["href"], card["image"]
            if source_page in seen or image_url.startswith("data:"):
                continue
            seen.add(source_page)
            lower_page = source_page.lower()
            # Only retain links that appear to be actual image/detail results from the provider.
            if provider == "Wikimedia Commons" and "commons.wikimedia.org" not in lower_page:
                continue
            if provider == "Openverse" and "openverse.org" not in lower_page:
                continue
            if provider == "Pixabay" and "pixabay.com" not in lower_page:
                continue
            if provider == "Unsplash" and "unsplash.com" not in lower_page:
                continue
            if provider == "Pexels" and "pexels.com" not in lower_page:
                continue
            # Skip logos, avatars, and tiny UI assets; downloads are validated again later.
            if any(term in image_url.lower() for term in ("logo", "avatar", "icon", "profile")):
                continue
            license_name = {
                "Openverse": "CC0/Public Domain search filter (verify source page)",
                "Wikimedia Commons": "License must be verified on file page",
                "Pixabay": "Pixabay Content License",
                "Unsplash": "Unsplash License",
                "Pexels": "Pexels License",
            }[provider]
            items.append({
                "id": provider.lower().replace(" ", "-") + ":" + source_page,
                "url": image_url, "source_page": source_page,
                "title": card.get("alt") or card.get("title") or query,
                "creator": None, "license": license_name,
                "license_url": {
                    "Openverse": "https://openverse.org/",
                    "Wikimedia Commons": "https://commons.wikimedia.org/wiki/Commons:Licensing",
                    "Pixabay": "https://pixabay.com/service/license-summary/",
                    "Unsplash": "https://unsplash.com/license",
                    "Pexels": "https://www.pexels.com/license/",
                }[provider],
                "provider": provider, "attribution": None,
            })
            if len(items) >= 12:
                break
    finally:
        page.close()
    print(f"{provider}: public page yielded {len(items)} linked image candidates for {query!r}", flush=True)
    return items

def _search_all(query: str) -> list[dict]:
    """Search public website pages in a browser; never call provider APIs."""
    all_results = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            for provider, template in PUBLIC_SEARCHES:
                url = _public_page_url(template, query)
                try:
                    all_results.extend(_search_public_page(browser, provider, url, query))
                except Exception as exc:
                    print(f"{provider}: public search page unavailable ({exc}); continuing", flush=True)
        finally:
            browser.close()
    return all_results

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
    """Build short, literal searches from the topic and narration, not art-direction prose."""
    def words(value: object) -> list[str]:
        value = re.sub(r"[^A-Za-z0-9\s'-]", " ", str(value or "")).lower()
        return [w for w in value.split() if w]

    # Do not search visual_description: it often contains irrelevant details like
    # character colors, clothing, and poetic art direction.
    topic_words = words(topic)
    title_words = words(scene.get("title"))
    narration_words = words(scene.get("narration"))

    stop = {
        "the", "a", "an", "and", "or", "but", "to", "of", "in", "on", "at",
        "for", "from", "with", "by", "as", "is", "are", "was", "were", "be",
        "been", "being", "it", "its", "this", "that", "these", "those", "you",
        "your", "we", "our", "they", "them", "their", "he", "she", "his", "her",
        "i", "me", "my", "do", "does", "did", "how", "why", "what", "when",
        "where", "which", "who", "can", "could", "will", "would", "may", "might",
        "have", "has", "had", "not", "no", "if", "then", "than", "so", "very",
        "just", "into", "about", "because", "there", "here", "through", "each",
        "every", "some", "many", "much", "more", "most", "often", "like",
        "scene", "introduction", "introduces", "shows", "show", "visual", "image",
        "vibrant", "cyan", "yellow", "stickman", "wearing", "foreground",
        "background", "stands", "standing", "looking", "curiously", "work", "works", "working", "function", "functions",
    }
    candidates = []

    def add(query: str):
        query = " ".join(query.split()).strip()
        if query and query not in candidates:
            candidates.append(query)

    # First search the actual topic using ordinary subject words.
    meaningful_topic = [w for w in topic_words if w not in stop]
    if meaningful_topic:
        add(" ".join(meaningful_topic[:5]))
        if len(meaningful_topic) > 2:
            add(" ".join(meaningful_topic[-3:]))

    # Then use simple subject/action terms from the scene title and spoken script.
    script_words = [w for w in title_words + narration_words if w not in stop]
    if script_words:
        add(" ".join(script_words[:4]))
        # Keep a small number of distinctive words, not whole sentences.
        for word in script_words:
            if word not in candidates and len(word) > 3:
                add(word)
            if len(candidates) >= 8:
                break

    # Put known subject phrases first so the search never becomes a leftover title fragment
    # such as "black holes work". These are the actual objects/topics the scene is about.
    combined = " ".join(topic_words + title_words + narration_words)
    expansions = [
        (r"\b(black hole|black holes|blackhole|blackholes|event horizon|accretion disk)\b",
         ["black hole anime", "anime black hole illustration", "anime space black hole",
          "black hole accretion disk", "ghibli style black hole"]),
        (r"\b(star|stars|twinkle|twinkling|starlight)\b", ["anime stars", "anime night sky stars", "anime twinkling stars"]),
        (r"\b(planet|planets|orbit|orbiting)\b", ["anime planets", "anime planets in space", "anime planet orbit"]),
        (r"\b(moon|lunar)\b", ["anime moon", "anime moon in night sky"]),
        (r"\b(sun|solar|sunlight)\b", ["anime sun", "anime sunlight"]),
        (r"\b(cloud|clouds|cloudy)\b", ["anime clouds", "anime sky with clouds"]),
        (r"\b(rain|rainfall|raindrop|raindrops)\b", ["anime rain", "anime rainy sky"]),
        (r"\b(light|lightwave|refraction|atmosphere)\b", ["light through atmosphere"]),
        (r"\b(ice|freezing|frozen)\b", ["ice"]),
        (r"\b(electricity|electric|current|circuit)\b", ["electric circuit"]),
        (r"\b(magnet|magnetic|magnetism)\b", ["magnet"]),
        (r"\b(heart|heartbeat|blood)\b", ["human heart"]),
        (r"\b(plant|plants|photosynthesis|leaf|leaves)\b", ["green plant"]),
    ]
    specific_queries = []
    for pattern, phrases in expansions:
        if re.search(pattern, combined):
            for phrase in phrases:
                if phrase not in specific_queries:
                    specific_queries.append(phrase)

    # Prioritize specific science objects over generic title/narration keywords.
    candidates = specific_queries + candidates

    # Search for anime-style scenery and science objects, not people/characters.
    # Add style variants to the specific queries first, while preserving direct queries as fallbacks.
    styled = []
    for query in specific_queries[:5]:
        if "anime" not in query:
            styled.append("anime style " + query)
        if "ghibli" not in query:
            styled.append("ghibli style " + query)
    for query in candidates:
        if query not in specific_queries:
            if "anime" not in query:
                styled.append("anime style " + query)
            if "ghibli" not in query:
                styled.append("ghibli style " + query)
            if len(styled) >= 10:
                break
    return list(dict.fromkeys(styled + candidates))[:16] or ["anime black hole illustration"]

def _gemini_scene_queries(topic: str, scenes: list[dict]) -> dict[int, list[str]]:
    """Ask Gemini for concise public image-search references based on each scene's actual script."""
    import os
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("GEMINI_API_KEY missing; using local image-query fallback.", flush=True)
        return {}

    scene_briefs = []
    for index, scene in enumerate(scenes, start=1):
        scene_briefs.append({
            "scene": index,
            "title": str(scene.get("title") or ""),
            "narration": str(scene.get("narration") or ""),
            "visual": str(scene.get("visual") or scene.get("visual_description") or ""),
            "background": str(scene.get("background") or ""),
        })
    prompt = f"""
You are preparing search terms for finding existing still illustrations on ordinary public image-search websites.
The science video topic is: {topic}
For each numbered scene below, return 3 to 5 short, literal English image-search queries based on the actual science subject, objects, setting, and action in that scene.
Prioritize concrete visual references and scenery over character descriptions. Include a mix of a specific science object/phenomenon and a relevant environment when appropriate. Search for existing hand-drawn 2D, anime, or storybook-style illustrations, but do not put all style words into every query.
Do not write prompts for generating images. Do not suggest APIs, API endpoints, or image-generation services. Do not include full narration sentences, abstract phrases, character clothing/colors, or generic queries like "science illustration".
Return ONLY JSON in this exact shape:
{{"scenes":[{{"scene":1,"queries":["...","...","..."]}}]}}
Include every scene number exactly once. Keep each query between 2 and 8 words.
Scene data:
{json.dumps(scene_briefs, ensure_ascii=False)}
"""
    models = ["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-3.6-flash", "gemini-3.8-flash"]
    for model in models:
        try:
            print(f"Gemini: generating image-search references with {model}", flush=True)
            response = _call_gemini(api_key, model, prompt, attempts=2)
            raw = response["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(raw)
            output = {}
            for entry in parsed.get("scenes", []):
                try:
                    index = int(entry.get("scene"))
                except (TypeError, ValueError):
                    continue
                queries = []
                for value in entry.get("queries", []):
                    query = re.sub(r"[^A-Za-z0-9 '-]", " ", str(value))
                    query = " ".join(query.split()).strip()
                    if 2 <= len(query.split()) <= 8 and query.lower() not in {q.lower() for q in queries}:
                        queries.append(query)
                if 1 <= index <= len(scenes) and queries:
                    output[index] = queries[:5]
            if output:
                print(f"Gemini generated image-search references for {len(output)}/{len(scenes)} scenes.", flush=True)
                return output
            print(f"{model}: returned no usable search references; trying fallback model.", flush=True)
        except Exception as exc:
            print(f"{model}: image-reference generation failed ({exc}); trying fallback model.", flush=True)
    print("Gemini image-reference generation unavailable; using local query fallback.", flush=True)
    return {}

def download_scene_illustrations(story: dict, output_dir: Path) -> list[Path]:
    """Try free, no-key sources first; missing images become text-only scenes."""
    scenes = story.get("scenes") or []
    if not scenes:
        raise RuntimeError("Story has no scenes; cannot search for illustrations.")
    output_dir.mkdir(parents=True, exist_ok=True)
    topic = str(story.get("topic") or "science")
    manifest, paths, used_ids = [], [], set()
    rng = random.SystemRandom()
    gemini_queries = _gemini_scene_queries(topic, scenes)

    for index, scene in enumerate(scenes, start=1):
        queries = gemini_queries.get(index) or _scene_queries(topic, scene)
        print(f"Scene {index}/{len(scenes)} image searches: {queries}", flush=True)
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
