"""Free, topic-matched science visuals using Wikimedia Commons and Pillow."""
import json
import math
import re
import subprocess
import textwrap
import time
from pathlib import Path
from urllib.parse import quote

import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
HEADERS = {"User-Agent": "FreeScienceVideoWorkflow/1.0 (educational video; contact via GitHub repository)"}
TIMEOUT = 20
_SEARCH_CACHE = {}
_LAST_SEARCH_AT = 0.0
_MIN_SEARCH_INTERVAL = 1.25

CINEMATIC_WORDS = {
    "black hole", "galaxy", "galaxies", "universe", "planet", "planets", "space",
    "star", "stars", "supernova", "nebula", "volcano", "eruption", "earthquake",
    "ocean", "deep sea", "wildlife", "aurora", "storm", "hurricane", "tornado",
    "lightning", "dinosaur", "extinction", "meteor", "asteroid", "mars", "moon",
    "solar system", "tsunami", "glacier", "mountain", "coral reef"
}
CARTOON_WORDS = {
    "atom", "molecule", "cell", "cells", "dna", "brain", "memory", "magnet",
    "electricity", "energy", "force", "gravity", "photosynthesis", "blood",
    "heart", "body", "fingerprint", "sneeze", "dream", "airplane", "flight",
    "sound", "light", "rain", "cloud", "plant", "plants", "bee", "bees",
    "how does", "how do", "why do we"
}

def choose_style(topic):
    text = topic.lower()
    cinematic = sum(3 if phrase in text else 0 for phrase in CINEMATIC_WORDS)
    cartoon = sum(2 if phrase in text else 0 for phrase in CARTOON_WORDS)
    if cinematic > cartoon:
        return "cinematic"
    if cartoon > cinematic:
        return "cartoon"
    # Topic-driven tie-breaker: abstract mechanism/explanation -> cartoon;
    # place, phenomenon, or "what would happen" -> cinematic.
    if any(w in text for w in ("what would happen", "why is", "why does", "where", "when")):
        return "cinematic"
    return "cartoon"

def font(size, bold=False):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            pass
    return ImageFont.load_default()

def commons_search(query, style):
    """Search Commons politely, reuse in-run results, and back off on rate limits."""
    global _LAST_SEARCH_AT
    clean_query = " ".join(query.lower().split())
    cache_key = (clean_query, style)
    if cache_key in _SEARCH_CACHE:
        return _SEARCH_CACHE[cache_key]
    suffix = " educational illustration diagram" if style == "cartoon" else " photograph science"
    params = {
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": query + suffix, "gsrnamespace": 6, "gsrlimit": 10,
        "prop": "imageinfo", "iiprop": "url|extmetadata", "iiurlwidth": 1800,
    }
    pages = {}
    for attempt in range(4):
        wait = _MIN_SEARCH_INTERVAL - (time.monotonic() - _LAST_SEARCH_AT)
        if wait > 0:
            time.sleep(wait)
        try:
            response = requests.get(COMMONS_API, params=params, headers=HEADERS, timeout=TIMEOUT)
            _LAST_SEARCH_AT = time.monotonic()
            if response.status_code == 429 or response.status_code >= 500:
                retry_after = response.headers.get("Retry-After", "")
                try:
                    delay = min(30.0, max(2.0, float(retry_after)))
                except ValueError:
                    delay = min(20.0, 2.0 ** (attempt + 1))
                if attempt < 3:
                    print(f"Commons rate/server limit ({response.status_code}); retrying in {delay:.0f}s.")
                    time.sleep(delay)
                    continue
            response.raise_for_status()
            pages = response.json().get("query", {}).get("pages", {})
            break
        except (requests.RequestException, ValueError) as exc:
            if attempt < 3:
                delay = min(20.0, 2.0 ** (attempt + 1))
                print(f"Commons search attempt {attempt + 1} failed: {exc}; retrying in {delay:.0f}s.")
                time.sleep(delay)
                continue
            print(f"Commons search failed after retries: {exc}; using original fallback illustration.")
            _SEARCH_CACHE[cache_key] = []
            return []
    results = []
    for page in pages.values():
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata", {})
        title = page.get("title", "")
        mime = info.get("mime", "")
        url = info.get("thumburl") or info.get("url")
        if not url or not mime.startswith("image/"):
            continue
        title_lower = title.lower()
        if style == "cartoon":
            # Prefer files that are explicitly diagrams, drawings, or illustrations.
            score = sum(term in title_lower for term in ("diagram", "illustration", "drawing", "cartoon", "scheme", "structure", "cycle"))
            if score == 0:
                continue
        results.append({
            "title": title.replace("File:", ""),
            "url": url,
            "source_url": info.get("descriptionurl", ""),
            "license": meta.get("LicenseShortName", {}).get("value", "License not listed"),
            "artist": re.sub("<[^>]+>", "", meta.get("Artist", {}).get("value", ""))[:300],
            "description": re.sub("<[^>]+>", "", meta.get("ImageDescription", {}).get("value", ""))[:500],
        })
    _SEARCH_CACHE[cache_key] = results
    return results

def nasa_search(query):
    """Search NASA's free public image library without an API key."""
    try:
        response = requests.get(
            "https://images-api.nasa.gov/search",
            params={"q": query, "media_type": "image", "page_size": 8},
            headers=HEADERS, timeout=12,
        )
        response.raise_for_status()
        items = response.json().get("collection", {}).get("items", [])
        found = []
        for item in items:
            data = (item.get("data") or [{}])[0]
            links = item.get("links") or []
            image_url = next((x.get("href") for x in links if x.get("render") == "image"), None)
            if not image_url:
                image_url = next((x.get("href") for x in links if x.get("rel") == "preview"), None)
            if not image_url or not image_url.startswith("https://"):
                continue
            found.append({
                "title": data.get("title", "NASA image"),
                "url": image_url,
                "source_url": "https://images.nasa.gov/",
                "license": "NASA media (verify item-specific usage notes)",
                "artist": data.get("photographer") or data.get("center") or "NASA",
                "description": (data.get("description") or "")[:500],
            })
        return found
    except Exception as exc:
        print(f"NASA image search unavailable: {exc}")
        return []


SPACE_TERMS = ("space", "astronaut", "planet", "jupiter", "mars", "sun", "solar", "universe",
               "satellite", "spacecraft", "vacuum", "plasma", "nebula", "galaxy", "moon")


def fallback_illustration(topic, scene_title, narration, width, height, index):
    """Create a clean, original diagram-like illustration when no good free file is found."""
    image = Image.new("RGB", (width, height), "#101b35")
    draw = ImageDraw.Draw(image)
    title = scene_title or topic
    # Friendly color palette; shapes are explanatory rather than character drawings.
    palette = ["#55d6be", "#ffd166", "#6cb6ff", "#ff7b9c", "#b8a1ff"]
    for i in range(70):
        x = (i * 137 + index * 41) % width
        y = (i * 83 + index * 29) % height
        r = 1 + (i % 3)
        draw.ellipse((x-r, y-r, x+r, y+r), fill="#304263")
    cx, cy = width // 2, height // 2 - 15
    key = (topic + " " + scene_title + " " + narration).lower()
    scene_key = (scene_title + " " + narration).lower()
    # Topic-specific fallback art for sleep, dreams, and neuroscience. Draw a
    # different visual cue for each scene instead of reusing generic node diagrams.
    if any(x in scene_key for x in ("dream", "sleep", "rem", "nightmare", "brain", "neural", "lucid", "memory", "forget", "animal", "baby", "fear", "threat", "falling", "flying", "paralyzed", "muscle", "movie", "cinema")):
        draw.ellipse((cx-260, cy-170, cx+260, cy+170), fill="#182b50", outline="#6cb6ff", width=5)
        if any(x in scene_key for x in ("rem", "paralyzed", "muscle")):
            # Eyes and REM movement lines.
            draw.ellipse((cx-125, cy-50, cx-25, cy+10), outline="#ffffff", width=8)
            draw.ellipse((cx+25, cy-50, cx+125, cy+10), outline="#ffffff", width=8)
            draw.arc((cx-110, cy-45, cx-35, cy+5), 190, 345, fill="#ff7b9c", width=7)
            draw.arc((cx+35, cy-45, cx+110, cy+5), 190, 345, fill="#ff7b9c", width=7)
            for j in range(3):
                draw.line((cx-210+j*18, cy-115, cx-175+j*18, cy-135), fill="#55d6be", width=5)
                draw.line((cx+175+j*18, cy+105, cx+210+j*18, cy+85), fill="#55d6be", width=5)
        elif any(x in scene_key for x in ("memory", "forget", "consolidation", "neural", "highways", "problem solving")):
            # Brain-like lobes with linked memory nodes.
            for x, y, r in ((cx-85,cy-30,65),(cx-25,cy-75,58),(cx+40,cy-60,62),(cx+90,cy-5,55),(cx+20,cy+45,58),(cx-55,cy+40,55)):
                draw.ellipse((x-r,y-r,x+r,y+r), fill="#ff7b9c", outline="#ffd6e0", width=3)
            nodes = [(cx-120,cy-30),(cx-25,cy-85),(cx+70,cy-45),(cx+110,cy+25),(cx,cy+60)]
            for j in range(len(nodes)-1):
                draw.line((*nodes[j], *nodes[j+1]), fill="#ffd166", width=7)
        elif any(x in scene_key for x in ("nightmare", "fear", "threat", "falling", "paradox", "stress")):
            # A dream cloud with a bold lightning / fear symbol.
            draw.ellipse((cx-150,cy-65,cx-35,cy+40), fill="#b8a1ff")
            draw.ellipse((cx-75,cy-110,cx+60,cy+40), fill="#b8a1ff")
            draw.ellipse((cx+15,cy-60,cx+145,cy+45), fill="#b8a1ff")
            draw.polygon([(cx+15,cy-70),(cx-25,cy+5),(cx+15,cy+5),(cx-5,cy+75),(cx+65,cy-15),(cx+25,cy-15)], fill="#ffd166")
        elif any(x in scene_key for x in ("animal", "animals", "baby", "babies")):
            # Small sleeping animal/baby silhouette and dream stars.
            draw.ellipse((cx-100,cy-75,cx+95,cy+80), fill="#ffd166", outline="#fff0bf", width=4)
            draw.ellipse((cx-70,cy-110,cx-20,cy-60), fill="#ffd166")
            draw.ellipse((cx+25,cy-110,cx+75,cy-60), fill="#ffd166")
            draw.arc((cx-35,cy-5,cx+10,cy+30), 10, 170, fill="#101b35", width=5)
            draw.arc((cx+30,cy-5,cx+75,cy+30), 10, 170, fill="#101b35", width=5)
            for sx,sy in ((cx+175,cy-120),(cx+220,cy-45),(cx-190,cy+90)):
                draw.polygon([(sx,sy-18),(sx+6,sy-5),(sx+20,sy),(sx+6,sy+6),(sx,sy+20),(sx-6,sy+6),(sx-20,sy),(sx-6,sy-5)], fill="#55d6be")
        elif any(x in scene_key for x in ("lucid", "controlling", "personal cinema", "movie", "flying")):
            # Thought bubble with a miniature dream landscape.
            for bx,by,br in ((cx-140,cy-90,48),(cx-70,cy-125,60),(cx+10,cy-120,58),(cx+100,cy-80,50)):
                draw.ellipse((bx-br,by-br,bx+br,by+br), fill="#263f6b", outline="#6cb6ff", width=4)
            draw.ellipse((cx-12,cy-25,cx+12,cy-1), fill="#ffffff")
            draw.ellipse((cx+25,cy+8,cx+42,cy+25), fill="#ffffff")
            draw.ellipse((cx+45,cy+30,cx+57,cy+42), fill="#ffffff")
            draw.arc((cx-160,cy-30,cx+160,cy+150), 185, 350, fill="#55d6be", width=8)
            draw.ellipse((cx+80,cy+15,cx+125,cy+60), fill="#ffd166")
        else:
            # Default sleep scene: pillow, sleeper, crescent moon and stars.
            draw.rounded_rectangle((cx-210,cy+35,cx+210,cy+125), radius=28, fill="#6cb6ff", outline="#b8dcff", width=4)
            draw.ellipse((cx-135,cy-85,cx+25,cy+75), fill="#ffd6b0", outline="#fff0df", width=4)
            draw.arc((cx-95,cy-20,cx-35,cy+20), 10, 170, fill="#101b35", width=6)
            draw.arc((cx-20,cy-20,cx+40,cy+20), 10, 170, fill="#101b35", width=6)
            draw.ellipse((cx+90,cy-145,cx+190,cy-45), fill="#ffd166")
            draw.ellipse((cx+120,cy-165,cx+210,cy-65), fill="#182b50")
            for sx,sy in ((cx-210,cy-120),(cx+30,cy-155),(cx+220,cy+5)):
                draw.polygon([(sx,sy-16),(sx+5,sy-5),(sx+16,sy),(sx+5,sy+5),(sx,sy+16),(sx-5,sy+5),(sx-16,sy),(sx-5,sy-5)], fill="#55d6be")
    elif any(x in key for x in ("space", "planet", "sun", "moon", "star", "galaxy", "black hole")):
        for r, color in ((190, "#263f6b"), (130, "#345f8b"), (70, "#4b8bb5")):
            draw.ellipse((cx-r, cy-r, cx+r, cy+r), fill=color, outline="#9bd8ff", width=3)
        draw.ellipse((cx-43, cy-43, cx+43, cy+43), fill="#ffd166")
        draw.ellipse((cx-250, cy-110, cx-225, cy-85), fill="#ffffff")
        draw.ellipse((cx+215, cy+105, cx+238, cy+128), fill="#ffffff")
    elif any(x in key for x in ("atom", "molecule", "cell", "dna", "chemical")):
        for j, (dx, dy) in enumerate(((-120, -40), (0, 0), (120, -40), (-65, 100), (75, 100))):
            x, y = cx + dx, cy + dy
            if j:
                draw.line((cx, cy, x, y), fill="#8fb9d9", width=8)
            r = 35 if j == 0 else 26
            draw.ellipse((x-r, y-r, x+r, y+r), fill=palette[j], outline="#ffffff", width=3)
    elif any(x in key for x in ("sound", "noise", "explosion", "boom", "bell", "wave", "vibration", "ear", "eardrum", "music", "roar", "whisper", "silence", "train", "radio")):
        # Sound-wave scene: wavefronts and a source object, not the generic node map.
        for radius, color in ((90, "#ffd166"), (155, "#55d6be"), (225, "#6cb6ff")):
            draw.arc((cx-radius, cy-radius, cx+radius, cy+radius), 235, 125, fill=color, width=9)
        if any(x in key for x in ("explosion", "boom", "loud")):
            draw.polygon([(cx,cy-125),(cx+35,cy-40),(cx+110,cy-75),(cx+65,cy+5),(cx+130,cy+55),(cx+40,cy+60),(cx+15,cy+145),(cx-25,cy+65),(cx-105,cy+90),(cx-60,cy+15),(cx-120,cy-35),(cx-35,cy-45)], fill="#ff7b4a", outline="#ffd166")
        elif any(x in key for x in ("ear", "eardrum", "internal", "body")):
            draw.ellipse((cx-65,cy-100,cx+65,cy+100), fill="#ffb5a7", outline="#ffe1da", width=6)
            draw.arc((cx-35,cy-65,cx+40,cy+65), 250, 110, fill="#9b4357", width=8)
            draw.line((cx+10,cy-35,cx+70,cy-10,cx+10,cy+25), fill="#9b4357", width=7)
        elif any(x in key for x in ("radio", "astronaut", "space", "star wars", "vacuum", "planet", "mars", "jupiter", "sun")):
            draw.ellipse((cx-90,cy-90,cx+90,cy+90), fill="#c65d4d", outline="#ffb28a", width=5)
            draw.arc((cx-185,cy-135,cx+185,cy+135), 190, 350, fill="#6cb6ff", width=7)
            draw.arc((cx-235,cy-175,cx+235,cy+175), 10, 170, fill="#55d6be", width=6)
            draw.ellipse((cx+150,cy-95,cx+177,cy-68), fill="#ffffff")
        else:
            # Repeating pressure wave through air or another material.
            pts = [(x, cy + int(90 * math.sin((x-cx)/38))) for x in range(50, width-50, 5)]
            draw.line(pts, fill="#55d6be", width=9)
            draw.line((50, cy+150, width-50, cy+150), fill="#6cb6ff", width=5)
            for x in range(100, width-80, 110):
                draw.ellipse((x-9,cy+135,x+9,cy+165), fill="#ffd166")
    elif any(x in key for x in ("ocean", "water", "rain", "cloud", "ice")):
        for j in range(5):
            y = cy - 100 + j * 48
            pts = [(x, y + int(12 * math.sin(x / 45 + j))) for x in range(60, width-50, 12)]
            draw.line(pts, fill=palette[j % len(palette)], width=7)
        draw.ellipse((cx-55, cy-190, cx+55, cy-80), fill="#78c9ff")
    elif any(x in key for x in ("plant", "bee", "flower", "photosynthesis", "tree")):
        draw.line((cx, cy+140, cx, cy-70), fill="#69bd75", width=18)
        draw.ellipse((cx-140, cy-90, cx-5, cy-20), fill="#69bd75")
        draw.ellipse((cx+5, cy-150, cx+140, cy-75), fill="#8bd17f")
        draw.ellipse((cx-40, cy-220, cx+40, cy-140), fill="#ffd166")
    else:
        # Abstract concept map with connected nodes.
        points = [(cx, cy-105), (cx-145, cy+15), (cx+145, cy+15), (cx-80, cy+130), (cx+80, cy+130)]
        for j in range(1, len(points)):
            draw.line((*points[0], *points[j]), fill="#607ca8", width=8)
        for j, (x, y) in enumerate(points):
            r = 45 if j == 0 else 34
            draw.ellipse((x-r, y-r, x+r, y+r), fill=palette[j], outline="#ffffff", width=4)
    # Readable title panel.
    panel_h = 132
    draw.rectangle((0, height-panel_h, width, height), fill="#081225")
    draw.text((48, height-panel_h+20), "SCIENCE EXPLAINED", font=font(22, True), fill="#55d6be")
    lines = textwrap.wrap(title, width=55)[:2]
    for j, line in enumerate(lines):
        draw.text((48, height-panel_h+53+j*34), line, font=font(29, True), fill="#ffffff")
    return image

def prepare_scene(scene, topic, style, out_path, width, height, index):
    title = str(scene.get("title") or topic).strip()
    narration = str(scene.get("narration") or "").strip()
    # Search concise scene labels, not narration paragraphs; this improves relevance
    # and avoids needlessly unique, long requests to Commons.
    query = " ".join(title.split()[:7]) or " ".join(topic.split()[:7])
    candidates = commons_search(query, style)
    scene_text = (topic + " " + title + " " + narration[:500]).lower()
    # Commons can rate-limit hosted runners. For space-related cinematic scenes,
    # try NASA's no-key image API before drawing a fallback.
    if not candidates and style == "cinematic" and any(term in scene_text for term in SPACE_TERMS):
        nasa_query = " ".join((title + " " + topic).split()[:8])
        candidates = nasa_search(nasa_query)
        if candidates:
            print(f"NASA supplied {len(candidates)} candidate image(s) for scene {index}: {title}")
    selected = None
    selected_bytes = None
    # First relevant Commons match. Downloads are bounded and failures fall through.
    for item in candidates[:5]:
        try:
            r = requests.get(item["url"], headers=HEADERS, timeout=TIMEOUT)
            r.raise_for_status()
            if len(r.content) > 18_000_000:
                continue
            from io import BytesIO
            import io
            im = Image.open(BytesIO(r.content)).convert("RGB")
            if im.width < 400 or im.height < 250:
                continue
            selected = item
            selected_bytes = r.content
            break
        except Exception as exc:
            print(f"Skipping image {item.get('title')}: {exc}")
    if selected is not None:
        # Use original downloaded response again for clarity and keep fit/crop predictable.
        try:
            from io import BytesIO
            from PIL import ImageOps
            image = ImageOps.fit(Image.open(BytesIO(selected_bytes)).convert("RGB"), (width, height), method=Image.Resampling.LANCZOS)
            if style == "cinematic":
                image = image.filter(ImageFilter.GaussianBlur(0.15))
                shade = Image.new("RGB", image.size, "#000000")
                image = Image.blend(image, shade, 0.12)
            draw = ImageDraw.Draw(image, "RGBA")
            panel_h = max(110, int(height * 0.19))
            draw.rectangle((0, height-panel_h, width, height), fill=(5, 12, 28, 205))
            draw.text((int(width*.045), height-panel_h+16), "SCIENCE • " + style.upper(), font=font(max(18, int(height*.028)), True), fill=(85, 214, 190, 255))
            for j, line in enumerate(textwrap.wrap(title, width=48)[:2]):
                draw.text((int(width*.045), height-panel_h+48+j*34), line, font=font(max(24, int(height*.039)), True), fill=(255,255,255,255))
        except Exception as exc:
            print(f"Image processing failed: {exc}; using illustration fallback.")
            image = fallback_illustration(topic, title, narration, width, height, index)
            selected = None
    else:
        image = fallback_illustration(topic, title, narration, width, height, index)
    image.save(out_path, "PNG", optimize=True)
    source = selected or {
        "title": "Original procedural science illustration",
        "url": "",
        "source_url": "",
        "license": "Original generated with Pillow",
        "artist": "Workflow-generated",
        "description": "Fallback illustration because a suitable Commons file was not found."
    }
    return {"scene": index, "scene_title": title, "style": style, **source}

def render_motion_video(scene_dir, audio_path, output_path, config):
    width, height = int(config.get("width", 1280)), int(config.get("height", 720))
    fps = int(config.get("fps", 24))
    images = sorted(scene_dir.glob("scene-*.png"))
    if not images:
        raise RuntimeError("No scene images were created.")
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
        capture_output=True, text=True, check=True
    )
    total = float(probe.stdout.strip())
    per_scene = total / len(images)
    import tempfile
    with tempfile.TemporaryDirectory(prefix="free_science_") as tmp:
        tmp = Path(tmp)
        clips = []
        for i, image in enumerate(images):
            if i == 0 or (i + 1) % 5 == 0 or i + 1 == len(images):
                print(f"Rendering video clips: {i+1}/{len(images)}", flush=True)
            clip = tmp / f"clip-{i:03d}.mp4"
            frames = max(2, round(per_scene * fps))
            # Gentle Ken Burns zoom; reset for every image so style remains stable.
            zoompan = f"scale={width*2}:{height*2}:force_original_aspect_ratio=increase,crop={width*2}:{height*2},zoompan=z='min(zoom+0.00035,1.08)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={width}x{height}:fps={fps},format=yuv420p"
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(image), "-vf", zoompan,
                 "-frames:v", str(frames), "-an", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "24", str(clip)],
                check=True
            )
            clips.append(clip)
        concat = tmp / "concat.txt"
        concat.write_text("".join(f"file '{p.as_posix()}'\n" for p in clips), encoding="utf-8")
        silent = tmp / "silent.mp4"
        print("Combining scene clips...", flush=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(silent)], check=True)
        print("Adding narration and finalizing MP4...", flush=True)
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(silent), "-i", str(audio_path),
             "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
             "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", str(output_path)],
            check=True
        )
