"""Free storybook-inspired 2D science stills using openly licensed image sources.

This is an original visual treatment, not copied Studio Ghibli artwork. It prefers
topic-relevant Commons/NASA images and uses a designed 2D fallback when none is found.
"""
import io
import re
import time
import textwrap
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps, ImageFont

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
HEADERS = {"User-Agent": "StickmanLabFreeScience/1.0 (educational video; open-source workflow)"}
TIMEOUT = 18
FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
]

def _font(size):
    for path in FONT_PATHS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default()

def _strip_html(text):
    return re.sub(r"<[^>]+>", "", text or "").strip()

def _commons_candidates(query):
    params = {
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": f'{query} (illustration OR painting OR photograph OR artwork)',
        "gsrnamespace": 6, "gsrlimit": 12, "prop": "imageinfo",
        "iiprop": "url|extmetadata", "iiurlwidth": 1800,
    }
    try:
        response = requests.get(COMMONS_API, params=params, headers=HEADERS, timeout=TIMEOUT)
        response.raise_for_status()
        pages = response.json().get("query", {}).get("pages", {}).values()
    except Exception as exc:
        print(f"Commons search unavailable for {query!r}: {exc}", flush=True)
        return []
    candidates = []
    for page in pages:
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata", {})
        url = info.get("thumburl") or info.get("url")
        if not url or not str(info.get("mime", "")).startswith("image/"):
            continue
        title = page.get("title", "").replace("File:", "")
        low = title.lower()
        score = sum(word in low for word in ("illustration", "painting", "watercolor", "watercolour", "artwork", "drawing", "landscape", "diagram"))
        # Prefer relevant illustrated material but retain photographs if no art is available.
        candidates.append((score, {
            "title": title, "url": url, "source_url": info.get("descriptionurl", ""),
            "license": _strip_html(meta.get("LicenseShortName", {}).get("value", "License not listed")),
            "artist": _strip_html(meta.get("Artist", {}).get("value", ""))[:250],
            "description": _strip_html(meta.get("ImageDescription", {}).get("value", ""))[:400],
        }))
    return [item for _, item in sorted(candidates, key=lambda x: x[0], reverse=True)]

def _nasa_candidates(query):
    try:
        r = requests.get("https://images-api.nasa.gov/search",
                         params={"q": query, "media_type": "image", "page_size": 8},
                         headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        items = r.json().get("collection", {}).get("items", [])
    except Exception as exc:
        print(f"NASA image search unavailable: {exc}", flush=True)
        return []
    found = []
    for item in items:
        data = (item.get("data") or [{}])[0]
        links = item.get("links") or []
        url = next((x.get("href") for x in links if x.get("render") == "image"), None)
        if not url:
            url = next((x.get("href") for x in links if x.get("rel") == "preview"), None)
        if url and url.startswith("https://"):
            found.append({"title": data.get("title", "NASA image"), "url": url,
                          "source_url": "https://images.nasa.gov/",
                          "license": "NASA media; verify item-specific usage notes",
                          "artist": data.get("photographer") or data.get("center") or "NASA",
                          "description": (data.get("description") or "")[:400]})
    return found

def _storybook_grade(image):
    """Warm, soft illustrated treatment without imitating any specific film frame."""
    image = ImageOps.autocontrast(image.convert("RGB"), cutoff=1)
    image = ImageEnhance.Color(image).enhance(0.88)
    image = ImageEnhance.Contrast(image).enhance(0.92)
    # Reduce harsh photographic micro-detail and gently blend edges.
    smooth = image.filter(ImageFilter.MedianFilter(3)).filter(ImageFilter.SMOOTH)
    image = Image.blend(image, smooth, 0.22)
    # Warm paper-light color grade.
    tint = Image.new("RGB", image.size, (255, 225, 177))
    image = Image.blend(image, tint, 0.07)
    # Very subtle paper grain, deterministic and lightweight.
    grain = Image.effect_noise(image.size, 8).convert("RGB")
    image = Image.blend(image, grain, 0.025)
    return image

def _fallback_scene(title, topic, width, height, index):
    """A designed 2D storybook landscape fallback, never a generic 3D sphere."""
    w, h = width, height
    low = (title + " " + topic).lower()
    if any(k in low for k in ("ocean", "sea", "reef", "water", "underwater", "marine")):
        top, bottom = (122, 203, 211), (24, 89, 115)
        terrain = [(0,.66),(.12,.62),(.25,.69),(.38,.64),(.53,.73),(.68,.65),(.82,.70),(1,.61)]
        scene = "water"
    elif any(k in low for k in ("space", "planet", "sun", "star", "galaxy", "moon", "universe", "black hole")):
        top, bottom = (24, 36, 79), (75, 74, 112)
        terrain = []
        scene = "space"
    elif any(k in low for k in ("forest", "plant", "tree", "photosynthesis", "ecosystem", "animal", "dinosaur")):
        top, bottom = (178, 219, 208), (73, 124, 93)
        terrain = [(0,.68),(.15,.53),(.30,.66),(.47,.48),(.65,.65),(.82,.50),(1,.64)]
        scene = "land"
    elif any(k in low for k in ("volcano", "lava", "fire", "heat")):
        top, bottom = (246, 172, 115), (77, 54, 63)
        terrain = [(0,.72),(.2,.66),(.36,.50),(.50,.34),(.63,.54),(.82,.67),(1,.72)]
        scene = "land"
    else:
        top, bottom = (170, 210, 224), (232, 204, 155)
        terrain = [(0,.70),(.15,.59),(.31,.67),(.50,.53),(.67,.65),(.83,.56),(1,.68)]
        scene = "land"
    strip = Image.new("RGB", (1, h))
    p = strip.load()
    for y in range(h):
        t = y / max(1, h-1)
        p[0, y] = tuple(int(top[c]*(1-t)+bottom[c]*t) for c in range(3))
    im = strip.resize((w,h)).convert("RGBA")
    d = ImageDraw.Draw(im, "RGBA")
    # Soft sun / moon glow and painted cloud bands.
    glow = Image.new("RGBA", (w,h), (0,0,0,0))
    gd = ImageDraw.Draw(glow)
    sx, sy, r = int(w*.76), int(h*.24), int(min(w,h)*.09)
    gd.ellipse((sx-r*2,sy-r*2,sx+r*2,sy+r*2), fill=(255,230,164,65))
    gd.ellipse((sx-r,sy-r,sx+r,sy+r), fill=(255,238,190,235))
    glow = glow.filter(ImageFilter.GaussianBlur(max(8, int(w*.018))))
    im = Image.alpha_composite(im, glow)
    d = ImageDraw.Draw(im, "RGBA")
    for j in range(4):
        x = int(w*(.08 + j*.22))
        y = int(h*(.18 + (j%2)*.09))
        d.ellipse((x,y,x+int(w*.13),y+int(h*.035)), fill=(255,255,242,100))
        d.ellipse((x+int(w*.025),y-int(h*.018),x+int(w*.09),y+int(h*.035)), fill=(255,255,242,120))
    if scene == "space":
        for n in range(95):
            x = (n*137 + index*71) % w
            y = (n*83 + index*29) % int(h*.75)
            rr = 1 + n%2
            d.ellipse((x-rr,y-rr,x+rr,y+rr), fill=(255,245,214,90+n%100))
        # A stylized nebula cloud, not a planet substitute.
        nebula = Image.new("RGBA", (w,h), (0,0,0,0))
        nd = ImageDraw.Draw(nebula)
        nd.ellipse((w*.16,h*.18,w*.60,h*.63), fill=(127,119,184,65))
        nebula = nebula.filter(ImageFilter.GaussianBlur(int(w*.045)))
        im = Image.alpha_composite(im, nebula)
    else:
        # Layered painted hills/waves with gently uneven silhouettes.
        for layer, (color, offset, alpha) in enumerate([
            ((42,83,94,155), .04, 160), ((53,112,95,190), .10, 220),
            ((42,88,70,235), .16, 245)
        ]):
            pts = [(0,h)]
            for x, y in terrain:
                pts.append((int(x*w), int((y+offset)*h)))
            pts.append((w,h))
            d.polygon(pts, fill=color)
        if scene == "water":
            for n in range(32):
                x = (n*101 + index*43) % w
                y = int(h*(.67 + (n%9)*.027))
                d.arc((x,y,x+int(w*.10),y+int(h*.025)), 185, 345, fill=(192,239,226,100), width=2)
        elif scene == "land":
            # Sparse layered foliage silhouettes for a storybook environment.
            for n in range(18):
                x = (n*173 + index*47) % w
                base_y = int(h*(.67 + (n%3)*.045))
                rad = int(h*(.035 + (n%4)*.008))
                d.ellipse((x-rad,base_y-rad*2,x+rad,base_y), fill=(32,83,67,210))
                d.rectangle((x-3,base_y-rad//2,x+3,base_y+int(h*.06)), fill=(83,78,56,220))
    # Elegant title treatment with readable contrast.
    overlay = Image.new("RGBA", (w,h), (0,0,0,0))
    od = ImageDraw.Draw(overlay)
    od.rectangle((0,int(h*.79),w,h), fill=(20,36,43,150))
    im = Image.alpha_composite(im, overlay)
    d = ImageDraw.Draw(im, "RGBA")
    d.text((int(w*.045),int(h*.825)), "SCIENCE STORYBOOK", font=_font(max(16,int(h*.025))), fill=(255,231,176,255))
    lines = textwrap.wrap(title or topic, width=max(25,int(w/22)))[:2]
    for j, line in enumerate(lines):
        d.text((int(w*.045),int(h*.865)+j*int(h*.045)), line, font=_font(max(24,int(h*.037))), fill=(255,255,245,255), stroke_width=1, stroke_fill=(25,42,48,180))
    return im.convert("RGB")

def render_storybook_stills(story, scene_dir, width, height):
    scene_dir = Path(scene_dir)
    scene_dir.mkdir(parents=True, exist_ok=True)
    topic = str(story.get("topic", "Science discovery"))
    credits = []
    for i, scene in enumerate(story.get("scenes", []), 1):
        title = str(scene.get("title") or topic).strip()
        narration = str(scene.get("narration") or "").strip()
        query = " ".join((title + " " + topic).split()[:8])
        candidates = _commons_candidates(query)
        if not candidates and any(k in (query+" "+narration).lower() for k in ("space","sun","planet","star","galaxy","moon","mars","nebula")):
            candidates = _nasa_candidates(query)
        selected, image = None, None
        for candidate in candidates[:6]:
            try:
                response = requests.get(candidate["url"], headers=HEADERS, timeout=TIMEOUT)
                response.raise_for_status()
                if len(response.content) > 20_000_000:
                    continue
                with Image.open(io.BytesIO(response.content)) as source:
                    source.load()
                    if source.width < 400 or source.height < 250:
                        continue
                    image = ImageOps.fit(source.convert("RGB"), (width,height), method=Image.Resampling.LANCZOS)
                selected = candidate
                break
            except Exception as exc:
                print(f"Skipping candidate image for scene {i}: {exc}", flush=True)
        if image is None:
            image = _fallback_scene(title, topic, width, height, i)
            credit = {"title":"Original procedural 2D storybook scene", "source_url":"",
                      "license":"Original workflow-generated artwork", "artist":"Stickman Lab workflow"}
        else:
            image = _storybook_grade(image)
            # Soft lower-third title panel, matching the illustrated visual identity.
            overlay = Image.new("RGBA", image.size, (0,0,0,0))
            d = ImageDraw.Draw(overlay)
            panel_top = int(height*.79)
            d.rectangle((0,panel_top,width,height), fill=(20,36,43,165))
            image = Image.alpha_composite(image.convert("RGBA"), overlay)
            d = ImageDraw.Draw(image, "RGBA")
            d.text((int(width*.045),int(height*.815)), "SCIENCE STORYBOOK", font=_font(max(16,int(height*.025))), fill=(255,231,176,255))
            for j, line in enumerate(textwrap.wrap(title, width=max(25,int(width/22)))[:2]):
                d.text((int(width*.045),int(height*.855)+j*int(height*.043)), line, font=_font(max(24,int(height*.037))), fill=(255,255,245,255), stroke_width=1, stroke_fill=(25,42,48,180))
            credit = selected
        out_path = scene_dir / f"scene-{i:03d}.png"
        image.convert("RGB").save(out_path, "PNG", optimize=True)
        credits.append({"scene":i,"scene_title":title,"style":"Original storybook-inspired 2D",
                        **credit})
        print(f"Rendered storybook 2D scene {i}/{len(story.get('scenes', []))}: {title}", flush=True)
        time.sleep(0.15)
    return credits
