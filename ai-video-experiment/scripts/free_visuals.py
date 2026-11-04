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


def _radial_sphere(size, base, highlight=(255, 255, 255), light=(-0.38, -0.48), strength=0.72):
    """Fast Pillow-only faux-3D sphere built from shaded layers and a soft specular highlight."""
    w, h = size
    base_rgb = tuple(int(base[i:i+2], 16) for i in (1, 3, 5)) if isinstance(base, str) else base
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img, "RGBA")
    # Dark edge / body, then offset lit layers create volume without expensive pixel loops.
    d.ellipse((1, 1, w-2, h-2), fill=(*tuple(int(v*.48) for v in base_rgb), 255))
    d.ellipse((w*.06, h*.045, w*.92, h*.91), fill=(*tuple(int(v*.72) for v in base_rgb), 255))
    d.ellipse((w*.10, h*.08, w*.84, h*.82), fill=(*base_rgb, 255))
    lit = tuple(min(255, int(base_rgb[i]*.55 + highlight[i]*.45)) for i in range(3))
    d.ellipse((w*.14, h*.10, w*.67, h*.62), fill=(*lit, 210))
    # Small blurred highlight gives a glossy, animated-feature lighting cue.
    hi = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    hd = ImageDraw.Draw(hi)
    hd.ellipse((w*.18, h*.13, w*.47, h*.35), fill=(*highlight, int(150*strength)))
    hi = hi.filter(ImageFilter.GaussianBlur(max(2, int(min(w, h)*.035))))
    img = Image.alpha_composite(img, hi)
    return img

def fallback_illustration(topic, scene_title, narration, width, height, index):
    """Create polished, animated-feature-inspired 3D-looking science art with Pillow.

    This is procedural rendering, not a diffusion model: use gradients, depth,
    glossy shaded objects, atmospheric light, soft shadows, and cinematic framing
    instead of flat diagram icons.
    """
    from PIL import ImageChops, ImageEnhance
    W, H = int(width), int(height)
    # Classify from this scene's own title and narration first. Putting the episode
    # topic first caused broad words such as "space" to override the actual scene.
    scene_key = (scene_title + " " + narration[:700]).lower()
    key = scene_key if len(scene_key.split()) >= 3 else (scene_key + " " + topic.lower())
    # Deep, colorful background gradient.
    tops = [(9, 17, 43), (12, 29, 54), (20, 19, 54), (7, 34, 52)]
    bottoms = [(28, 53, 85), (29, 38, 83), (49, 28, 76), (10, 61, 72)]
    palette_idx = index % len(tops)
    # Build the gradient as a narrow strip and resize in Pillow's optimized C code.
    top, bottom = tops[palette_idx], bottoms[palette_idx]
    strip = Image.new("RGB", (1, H))
    sp = strip.load()
    for y in range(H):
        t = y / max(1, H - 1)
        sp[0, y] = tuple(int(top[ch] * (1-t) + bottom[ch] * t) for ch in range(3))
    image = strip.resize((W, H))
    # Atmospheric glow and soft, out-of-focus background lights.
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((W*.19, H*.04, W*.77, H*.88), fill=(54, 123, 220, 46))
    gd.ellipse((W*.48, H*.12, W*.91, H*.77), fill=(176, 75, 202, 30))
    glow = glow.filter(ImageFilter.GaussianBlur(max(18, int(W*.045))))
    image = Image.alpha_composite(image.convert("RGBA"), glow)
    draw = ImageDraw.Draw(image, "RGBA")
    # Tiny depth-of-field particles; restrained rather than diagram decoration.
    for i in range(54):
        x = (i * 197 + index * 83) % W
        y = (i * 113 + index * 47) % int(H * .78)
        r = 1 + (i % 3)
        draw.ellipse((x-r, y-r, x+r, y+r), fill=(177, 215, 255, 45 + (i % 4) * 12))

    def sphere(cx, cy, radius, color, highlight=(255,255,255), outline=None):
        # Blurred contact shadow gives the object a sense of weight.
        shadow = Image.new("RGBA", (W, H), (0,0,0,0))
        sd = ImageDraw.Draw(shadow)
        sd.ellipse((cx-radius*.8, cy+radius*.62, cx+radius*.9, cy+radius*1.05), fill=(0,0,0,120))
        shadow = shadow.filter(ImageFilter.GaussianBlur(max(5, int(radius*.16))))
        image.alpha_composite(shadow)
        obj = _radial_sphere((int(radius*2), int(radius*2)), color, highlight)
        image.alpha_composite(obj, (int(cx-radius), int(cy-radius)))
        if outline:
            ImageDraw.Draw(image, "RGBA").ellipse((cx-radius, cy-radius, cx+radius, cy+radius), outline=outline, width=max(2,int(radius*.025)))

    cx, cy = int(W*.52), int(H*.40)
    # Pick one dominant, rounded 3D subject based on scene meaning.
    if any(w in scene_key for w in ("brain", "neuron", "memory", "dream", "sleep", "thought", "nerve")):
        # Overlapping shaded lobes read as a soft sculpted brain, not a flat icon.
        for dx, dy, r, col in [(-.12,-.02,.17,"#f06f91"),(-.02,-.13,.17,"#ff91a8"),(.10,-.09,.17,"#e85d88"),(.16,.04,.14,"#ff9caf"),(.05,.11,.16,"#f27b9c"),(-.09,.10,.14,"#d94f7b")]:
            sphere(int(W*(.51+dx)), int(H*(.38+dy)), int(min(W,H)*r), col, (255,218,225))
        d = ImageDraw.Draw(image, "RGBA")
        d.arc((W*.40,H*.24,W*.54,H*.46), 230, 75, fill=(255,222,230,210), width=5)
        d.arc((W*.51,H*.19,W*.66,H*.44), 100, 280, fill=(255,222,230,190), width=5)
    elif any(w in scene_key for w in ("plant", "tree", "photosynthesis", "flower", "forest", "leaf")):
        d = ImageDraw.Draw(image, "RGBA")
        d.rounded_rectangle((W*.49,H*.37,W*.535,H*.70), radius=18, fill=(91,112,73,255))
        sphere(int(W*.45),int(H*.36),int(min(W,H)*.12),"#54bd7b",(223,255,202))
        sphere(int(W*.56),int(H*.31),int(min(W,H)*.14),"#72d88b",(231,255,200))
        sphere(int(W*.51),int(H*.23),int(min(W,H)*.13),"#8de59b",(245,255,214))
        sphere(int(W*.40),int(H*.48),int(min(W,H)*.075),"#39a967",(205,255,210))
        sphere(int(W*.60),int(H*.46),int(min(W,H)*.08),"#42b971",(205,255,210))
        sphere(int(W*.72),int(H*.20),int(min(W,H)*.065),"#ffd56a",(255,250,210))
    elif any(w in scene_key for w in ("ocean", "water", "rain", "ice", "wave", "sea", "sound", "vibration", "frequency", "echo", "ear", "eardrum")):
        # Large luminous glassy orb plus layered atmospheric wave ribbons.
        sphere(cx, int(H*.38), int(min(W,H)*.19), "#1f8fc2", (210,247,255), (145,225,255,120))
        d = ImageDraw.Draw(image, "RGBA")
        for j, alpha in enumerate((170,130,95,70)):
            box = (W*(.23-j*.035), H*(.18-j*.025), W*(.79+j*.035), H*(.62+j*.025))
            d.arc(box, 200, 340, fill=(107,226,255,alpha), width=max(3, int(W*.005)))
        # Bright highlight streak creates a glass / studio-lit finish.
        d.arc((W*.39,H*.22,W*.55,H*.49), 205, 290, fill=(245,255,255,210), width=max(3,int(W*.006)))
    elif any(w in scene_key for w in ("atom", "molecule", "electron", "chemical", "dna", "cell", "protein")):
        sphere(cx, cy, int(min(W,H)*.105), "#ffbd59", (255,250,205))
        d = ImageDraw.Draw(image, "RGBA")
        for box, angle in [((W*.34,H*.18,W*.70,H*.62),25),((W*.34,H*.18,W*.70,H*.62),145),((W*.28,H*.23,W*.76,H*.57),80)]:
            d.ellipse(box, outline=(120,220,255,205), width=max(3,int(W*.004)))
        for px, py, col in [(W*.35,H*.34,"#53c7ff"),(W*.64,H*.31,"#ff6f91"),(W*.57,H*.58,"#65e5bc")]:
            sphere(int(px),int(py),int(min(W,H)*.055),col,(255,255,255))
    elif any(w in scene_key for w in ("planet", "space", "galaxy", "star", "moon", "mars", "jupiter", "universe", "black hole", "solar")):
        sphere(cx, int(H*.39), int(min(W,H)*.23), "#b66b55", (255,215,177))
        d = ImageDraw.Draw(image, "RGBA")
        d.arc((W*.20,H*.20,W*.82,H*.59), 190, 345, fill=(132,215,255,210), width=max(5,int(W*.008)))
        d.arc((W*.18,H*.24,W*.84,H*.65), 12, 166, fill=(255,194,126,170), width=max(3,int(W*.004)))
        sphere(int(W*.72),int(H*.23),int(min(W,H)*.045),"#ffe8a0",(255,255,255))
    elif any(w in scene_key for w in ("volcano", "eruption", "lava", "fire", "heat", "sun", "lightning", "storm")):
        d = ImageDraw.Draw(image, "RGBA")
        d.polygon([(W*.25,H*.67),(W*.43,H*.34),(W*.51,H*.46),(W*.61,H*.31),(W*.79,H*.67)], fill=(69,70,94,255))
        d.polygon([(W*.43,H*.34),(W*.51,H*.46),(W*.61,H*.31),(W*.57,H*.48),(W*.47,H*.48)], fill=(255,132,68,255))
        sphere(int(W*.52),int(H*.29),int(min(W,H)*.065),"#ffb347",(255,246,195))
        for j in range(12):
            x = int(W*(.42+(j*37%18)/100))
            y = int(H*(.22+(j*29%25)/100))
            sphere(x,y,max(5,int(min(W,H)*.012)),"#ff784b",(255,224,157))
    else:
        # A glossy, sculptural science object; still shaded and cinematic.
        sphere(cx, cy, int(min(W,H)*.18), "#4a9bd8", (226,247,255))
        sphere(int(W*.61), int(H*.33), int(min(W,H)*.075), "#ffbd59", (255,249,207))
        sphere(int(W*.43), int(H*.49), int(min(W,H)*.055), "#62d7bd", (236,255,246))
        d = ImageDraw.Draw(image, "RGBA")
        d.arc((W*.28,H*.18,W*.74,H*.66), 200, 340, fill=(192,230,255,190), width=max(4,int(W*.005)))

    # Cinematic depth vignette and soft light bloom.
    image = image.convert("RGB")
    image = ImageEnhance.Contrast(image).enhance(1.06)
    # Soft vignette made from nested ellipses; avoids millions of Python pixel operations.
    vignette = Image.new("L", (W, H), 148)
    vd = ImageDraw.Draw(vignette)
    for j in range(18):
        inset_x = int(W * (0.025 + j * 0.018))
        inset_y = int(H * (0.025 + j * 0.018))
        shade = int(255 - j * 6.0)
        vd.ellipse((inset_x, inset_y, W-inset_x, H-inset_y), fill=max(148, shade))
    dark = Image.new("RGB", (W,H), (0,0,0))
    image = Image.composite(image, dark, vignette)
    # Subtle bottom title panel with a clean movie-poster treatment.
    panel_h = int(H*.18)
    overlay = Image.new("RGBA", (W,H), (0,0,0,0))
    od = ImageDraw.Draw(overlay)
    od.rectangle((0,H-panel_h,W,H), fill=(4,9,24,205))
    image = Image.alpha_composite(image.convert("RGBA"), overlay)
    d = ImageDraw.Draw(image, "RGBA")
    d.text((int(W*.045), H-panel_h+int(H*.022)), "SCIENCE • ANIMATED VISUAL", font=font(max(18,int(H*.027)), True), fill=(116,226,255,255))
    lines = textwrap.wrap(scene_title or topic, width=max(28,int(W/22)))[:2]
    for j,line in enumerate(lines):
        d.text((int(W*.045),H-panel_h+int(H*.06)+j*int(H*.045)),line,font=font(max(25,int(H*.039)),True),fill=(255,255,255,255))
    return image.convert("RGB")

def prepare_scene(scene, topic, style, out_path, width, height, index):
    title = str(scene.get("title") or topic).strip()
    narration = str(scene.get("narration") or "").strip()
    # Search concise scene labels, not narration paragraphs; this improves relevance
    # and avoids needlessly unique, long requests to Commons.
    query = " ".join(title.split()[:7]) or " ".join(topic.split()[:7])
    # Cartoon episodes use our consistent locally rendered 3D animated-feature look.
    # Avoid mixing flat Commons diagrams into a single episode; cinematic episodes
    # can still use real photographs from free sources.
    candidates = [] if style == "cartoon" else commons_search(query, style)
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
            # Only overscale by the maximum zoom amount. The old 2x source scale
            # processed four times as many pixels as needed for every scene.
            zoompan = f"scale={int(width*1.12)}:{int(height*1.12)}:force_original_aspect_ratio=increase,crop={int(width*1.12)}:{int(height*1.12)},zoompan=z='min(zoom+0.00035,1.08)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={width}x{height}:fps={fps},format=yuv420p"
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-framerate", "1", "-i", str(image), "-vf", zoompan,
                 "-frames:v", str(frames), "-an", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "24", str(clip)],
                check=True
            )
            clips.append(clip)
        concat = tmp / "concat.txt"
        concat.write_text("".join(f"file '{p.as_posix()}'\n" for p in clips), encoding="utf-8")
        silent = tmp / "silent.mp4"
        print("Combining scene clips...", flush=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(silent)], check=True)
        print("Adding narration without re-encoding the video...", flush=True)
        # Every scene clip already has the final H.264 settings. Copying that
        # stream avoids an expensive second full encode of the entire video.
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(silent), "-i", str(audio_path),
             "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
             "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", str(output_path)],
            check=True
        )
