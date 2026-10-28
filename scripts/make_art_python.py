"""Cartoon presenter and procedural science visuals for daily videos."""
import math
import random
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

PALETTES = {
    "sky": ("#A7D8FF", "#F5FCFF"), "lab": ("#D9F2F0", "#F8FFFD"),
    "space": ("#101B3B", "#253D70"), "ocean": ("#56C5E8", "#DDF8FF"),
    "forest": ("#9ED69A", "#E8F5C8"), "city": ("#F7C98B", "#FFF1D5"),
    "home": ("#F4D9B7", "#FFF6E8"), "cave": ("#8D8A9A", "#D6D0D9"),
    "desert": ("#F4C477", "#FFE8B0"), "mountain": ("#B8D8E8", "#F4FBFF"),
}

INK = "#202A38"
SHIRT = "#2878D0"
PANTS = "#273449"
SKIN = "#F2C29D"
WHITE = "#FFFFFF"
GOLD = "#FFD34E"

def font(size, bold=False):
    names = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for name in names:
        try: return ImageFont.truetype(name, max(8, int(size)))
        except OSError: pass
    return ImageFont.load_default()

def rgb(color):
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))

def mix(a, b, t):
    return tuple(int(a[i] * (1 - t) + b[i] * t) for i in range(3))

def draw_background(image, draw, background, frame, scale):
    """Draw a detailed, locally generated cartoon science environment."""
    w, h = image.size
    background = str(background or "sky").lower()
    top, bottom = PALETTES.get(background, PALETTES["sky"])
    a, b = rgb(top), rgb(bottom)

    # Smooth vertical gradient.
    bands = 120
    for i in range(bands):
        y0 = int(h * i / bands)
        y1 = int(h * (i + 1) / bands) + 1
        draw.rectangle((0, y0, w, y1), fill=mix(a, b, i / max(1, bands - 1)))

    rng = random.Random(2025 + sum(ord(c) for c in background))
    ground_y = int(h * 0.79)
    unit = max(1, scale)
    line = max(1, 2 * unit)

    def ellipse(box, fill, outline=None, width=1):
        draw.ellipse(box, fill=fill, outline=outline, width=width)

    def cloud(x, y, size):
        ellipse((x, y + size*.25, x+size*1.4, y+size*.8), "#F8FDFF")
        ellipse((x+size*.2, y, x+size*.8, y+size*.75), "#FFFFFF")
        ellipse((x+size*.65, y+size*.12, x+size*1.25, y+size*.75), "#FFFFFF")

    def star(x, y, r, color="#FFFFFF"):
        ellipse((x-r, y-r, x+r, y+r), color)
        if r >= 3 * unit:
            draw.line((x-r*2, y, x+r*2, y), fill=color, width=unit)
            draw.line((x, y-r*2, x, y+r*2), fill=color, width=unit)

    if background in ("sky", "mountain", "city", "desert"):
        sx, sy = int(w*.81), int(h*.19)
        sr = int(min(w, h)*.055)
        for k in range(4, 0, -1):
            r = int(sr*(1 + k*.18))
            ellipse((sx-r, sy-r, sx+r, sy+r), "#FCECC0" if k > 2 else "#FFF5D5")
        ellipse((sx-sr, sy-sr, sx+sr, sy+sr), "#FFE69A")

        if background in ("sky", "mountain"):
            for x, y, size in ((int(w*.08), int(h*.15), int(w*.12)), (int(w*.43), int(h*.10), int(w*.10)), (int(w*.65), int(h*.25), int(w*.08))):
                cloud(x, y, size)

        if background == "mountain":
            draw.polygon([(0, int(h*.67)), (int(w*.15), int(h*.31)), (int(w*.27), int(h*.58)), (int(w*.43), int(h*.27)), (int(w*.62), int(h*.66)), (int(w*.79), int(h*.38)), (w, int(h*.67)), (w, h), (0, h)], fill="#9DBDD0")
            draw.polygon([(int(w*.15), int(h*.31)), (int(w*.10), int(h*.44)), (int(w*.18), int(h*.41)), (int(w*.22), int(h*.49)), (int(w*.27), int(h*.58))], fill="#F7FCFF")
            draw.polygon([(int(w*.43), int(h*.27)), (int(w*.36), int(h*.43)), (int(w*.44), int(h*.39)), (int(w*.50), int(h*.49)), (int(w*.62), int(h*.66))], fill="#F7FCFF")
            draw.polygon([(0, int(h*.70)), (int(w*.23), int(h*.52)), (int(w*.43), int(h*.70)), (int(w*.70), int(h*.53)), (w, int(h*.70)), (w, h), (0, h)], fill="#B8D6A0")
        elif background == "desert":
            draw.polygon([(0, int(h*.63)), (int(w*.25), int(h*.48)), (int(w*.49), int(h*.64)), (int(w*.76), int(h*.47)), (w, int(h*.61)), (w, h), (0, h)], fill="#E8BD72")
            draw.polygon([(0, int(h*.72)), (int(w*.32), int(h*.62)), (int(w*.55), int(h*.74)), (int(w*.82), int(h*.61)), (w, int(h*.70)), (w, h), (0, h)], fill="#F0CF88")
            for x, y in ((int(w*.13), int(h*.62)), (int(w*.91), int(h*.65))):
                draw.rectangle((x-5*unit, y-55*unit, x+5*unit, y), fill="#41865A")
                draw.rectangle((x-19*unit, y-40*unit, x-5*unit, y-33*unit), fill="#41865A")
                draw.rectangle((x-19*unit, y-49*unit, x-12*unit, y-33*unit), fill="#41865A")
                draw.rectangle((x+5*unit, y-30*unit, x+18*unit, y-23*unit), fill="#41865A")
                draw.rectangle((x+11*unit, y-40*unit, x+18*unit, y-23*unit), fill="#41865A")
        elif background == "city":
            for i, x in enumerate(range(0, w, int(w*.105))):
                bw = int(w*.075)
                bh = rng.randint(int(h*.15), int(h*.34))
                by = int(h*.76) - bh
                color = rng.choice(("#D7A97D", "#E6B88B", "#C89E84", "#EAD0A4"))
                draw.rectangle((x, by, x+bw, int(h*.76)), fill=color, outline="#B58B71", width=unit)
                for wx in range(x+7*unit, x+bw-4*unit, 14*unit):
                    for wy in range(by+9*unit, int(h*.75), 18*unit):
                        draw.rectangle((wx, wy, wx+5*unit, wy+7*unit), fill="#FFF1B5")

    elif background == "space":
        for _ in range(145):
            x = rng.randrange(w); y = rng.randrange(int(h*.83)); r = rng.choice((1, 1, 2, 3))*unit
            star(x, y, r, rng.choice(("#FFFFFF", "#D6E7FF", "#B6C8FF", "#FFE5B5")))
        for x, y, rx, ry, color in ((int(w*.25), int(h*.25), int(w*.15), int(h*.08), "#283D77"), (int(w*.55), int(h*.18), int(w*.12), int(h*.06), "#46336E"), (int(w*.75), int(h*.60), int(w*.13), int(h*.07), "#263C71")):
            ellipse((x-rx, y-ry, x+rx, y+ry), color)
        px = int(w*.79 + math.sin(frame*.025)*8*unit); py = int(h*.40); pr = int(min(w, h)*.085)
        draw.ellipse((px-pr, py-pr, px+pr, py+pr), fill="#E9A66A", outline="#FFF0C4", width=line)
        draw.arc((px-pr*1.55, py-pr*.42, px+pr*1.55, py+pr*.42), 190, 350, fill="#FFF0C4", width=3*unit)
        draw.arc((px-pr*1.55, py-pr*.42, px+pr*1.55, py+pr*.42), 10, 170, fill="#FFF0C4", width=3*unit)
        ellipse((int(w*.13), int(h*.35), int(w*.19), int(h*.42)), "#A889DC")
        ellipse((int(w*.50), int(h*.64), int(w*.55), int(h*.69)), "#61B8E6")

    elif background == "ocean":
        draw.rectangle((0, int(h*.47), w, h), fill="#38A9D6")
        draw.rectangle((0, int(h*.54), w, h), fill="#278DBD")
        for x, y, rx, ry in ((int(w*.18), int(h*.47), int(w*.13), int(h*.06)), (int(w*.77), int(h*.47), int(w*.17), int(h*.07))):
            ellipse((x-rx, y-ry, x+rx, y+ry), "#78BD86")
        for row in range(6):
            yy = int(h*(.59 + row*.065))
            for col in range(8):
                xx = int(w*(col/7)) + (row % 2)*int(w*.035)
                draw.arc((xx, yy, xx+int(w*.09), yy+16*unit), 190, 340, fill="#B7F2FF", width=2*unit)
        for i in range(16):
            x = int((i*137 + frame*.5) % w); y = int(h*.70 + (i%4)*int(h*.055)); r = (2 + i%4)*unit
            draw.ellipse((x-r, y-r, x+r, y+r), outline="#B7F2FF", width=unit)

    elif background == "forest":
        draw.rectangle((0, int(h*.57), w, h), fill="#7EBC79")
        for layer in range(2):
            base = int(h*(.64 + layer*.07)); step = int(w*.11)
            for i, x in enumerate(range(-step, w+step, step)):
                tree_h = int(h*(.19 + ((i*17+layer*7)%5)*.025))
                shade = ("#6FB17A", "#4F9865", "#39895B")[(i+layer) % 3]
                draw.polygon([(x, base-tree_h), (x-step*.55, base-tree_h*.35), (x-step*.25, base-tree_h*.35), (x-step*.65, base), (x+step*.65, base), (x+step*.25, base-tree_h*.35), (x+step*.55, base-tree_h*.35)], fill=shade)
        for x in (int(w*.07), int(w*.91)):
            draw.rectangle((x-9*unit, int(h*.36), x+9*unit, int(h*.80)), fill="#76513A")
            draw.line((x, int(h*.48), x+25*unit, int(h*.40)), fill="#76513A", width=5*unit)
            draw.line((x, int(h*.55), x-22*unit, int(h*.47)), fill="#76513A", width=5*unit)
            for dx, dy, r in ((-18, -8, 30), (12, -23, 35), (35, -3, 27)):
                rr = r*unit
                ellipse((x+dx*unit-rr, int(h*.39)+dy*unit-rr, x+dx*unit+rr, int(h*.39)+dy*unit+rr), "#368652")

    elif background == "lab":
        draw.rectangle((0, int(h*.73), w, h), fill="#AFCFCB")
        draw.rectangle((0, int(h*.68), w, int(h*.72)), fill="#E8F6F3")
        for x in (int(w*.06), int(w*.77)):
            draw.rounded_rectangle((x, int(h*.17), x+int(w*.15), int(h*.49)), radius=8*unit, fill="#8ED4E9", outline="#FFFFFF", width=4*unit)
            draw.line((x+int(w*.075), int(h*.18), x+int(w*.075), int(h*.48)), fill="#FFFFFF", width=3*unit)
            draw.line((x, int(h*.33), x+int(w*.15), int(h*.33)), fill="#FFFFFF", width=3*unit)
        for y in (int(h*.22), int(h*.36)):
            draw.rectangle((int(w*.29), y, int(w*.68), y+5*unit), fill="#8EA9A6")
        for i, x in enumerate((.34, .42, .51, .60)):
            bx = int(w*x); by = int(h*(.22 if i%2 == 0 else .36))
            draw.rectangle((bx, by, bx+12*unit, by+20*unit), fill="#E7FBFF", outline="#397D83", width=unit)
            draw.polygon([(bx, by+12*unit), (bx+12*unit, by+12*unit), (bx+12*unit, by+20*unit), (bx, by+20*unit)], fill=("#8BE3C1", "#7CCCF2", "#F3D56C", "#C6A7F2")[i])
        draw.rectangle((int(w*.24), int(h*.60), int(w*.72), int(h*.65)), fill="#EAF7F5", outline="#668E8A", width=2*unit)
        draw.rectangle((int(w*.27), int(h*.65), int(w*.69), int(h*.75)), fill="#91B9B4")
        for x in (int(w*.37), int(w*.49), int(w*.61)):
            draw.rectangle((x, int(h*.67), x+int(w*.08), int(h*.72)), fill="#B9D8D3", outline="#668E8A", width=unit)

    elif background == "home":
        draw.rectangle((0, int(h*.75), w, h), fill="#D7B68F")
        draw.rectangle((int(w*.08), int(h*.17), int(w*.31), int(h*.48)), fill="#BCE9F8", outline="#FFFFFF", width=5*unit)
        draw.line((int(w*.195), int(h*.18), int(w*.195), int(h*.47)), fill="#FFFFFF", width=3*unit)
        draw.line((int(w*.09), int(h*.32), int(w*.30), int(h*.32)), fill="#FFFFFF", width=3*unit)
        draw.rounded_rectangle((int(w*.65), int(h*.51), int(w*.91), int(h*.70)), radius=12*unit, fill="#6D9DD0", outline="#466C9A", width=2*unit)
        draw.rectangle((int(w*.67), int(h*.67), int(w*.70), int(h*.77)), fill="#795A43")
        draw.rectangle((int(w*.86), int(h*.67), int(w*.89), int(h*.77)), fill="#795A43")
        draw.rounded_rectangle((int(w*.69), int(h*.54), int(w*.78), int(h*.63)), radius=5*unit, fill="#B6D4F2")

    elif background == "cave":
        draw.polygon([(0, 0), (w, 0), (w, int(h*.18)), (int(w*.85), int(h*.27)), (int(w*.67), int(h*.19)), (int(w*.49), int(h*.30)), (int(w*.28), int(h*.19)), (int(w*.13), int(h*.27)), (0, int(h*.20))], fill="#777789")
        for i in range(9):
            x = int(w*i/8); length = rng.randint(int(h*.05), int(h*.15))
            draw.polygon([(x, 0), (x+int(w*.045), 0), (x+int(w*.022), length)], fill="#A8A5B5")
        draw.polygon([(0, int(h*.73)), (int(w*.17), int(h*.63)), (int(w*.34), int(h*.75)), (int(w*.56), int(h*.66)), (int(w*.78), int(h*.75)), (w, int(h*.65)), (w, h), (0, h)], fill="#777789")
        for x, y in ((.14, .72), (.83, .72), (.65, .79)):
            xx, yy = int(w*x), int(h*y)
            draw.polygon([(xx, yy), (xx-9*unit, yy+20*unit), (xx, yy+40*unit), (xx+9*unit, yy+20*unit)], fill="#72D8E8", outline="#D0FBFF")

    if background not in ("space", "ocean", "cave"):
        ground_colors = {"sky": "#7CCB79", "city": "#D6B17A", "desert": "#E5B45E", "mountain": "#B5D0A1", "forest": "#5EAA68", "home": "#D7B68F", "lab": "#C5E2DF"}
        if background in ground_colors:
            draw.rectangle((0, ground_y, w, h), fill=ground_colors[background])

    return ground_y

def draw_science_object(draw, name, x, y, size, frame, scale):
    """Draw recognizable science props with shading and simple animation."""
    name = str(name or "science").lower()
    x, y, s = int(x), int(y), max(12, int(size))
    lw = max(2, 2 * scale)
    bob = math.sin(frame * 0.09) * 3 * scale
    y = int(y + bob)

    def ell(box, fill, outline=None, width=1):
        draw.ellipse(box, fill=fill, outline=outline, width=width)

    def label(text, px, py, fill="#FFFFFF"):
        draw.text((px, py), text, font=font(max(12, s//5), True), fill=fill)

    if any(word in name for word in ("earth", "planet", "mars", "moon", "orbit", "solar system")):
        r = s
        draw.ellipse((x-r*1.55, y-r*.48, x+r*1.55, y+r*.48), outline="#FFE6A6", width=lw)
        ell((x-r, y-r, x+r, y+r), "#378DD0", "#E5F6FF", lw)
        ell((x-r*.85, y-r*.70, x+r*.12, y+r*.73), "#2B70B0")
        draw.polygon([(x-r*.62, y-r*.32), (x-r*.20, y-r*.52), (x+r*.04, y-r*.22), (x-r*.15, y+r*.02), (x-r*.44, y+r*.14), (x-r*.62, y-r*.32)], fill="#61BD76")
        draw.polygon([(x+r*.14, y+r*.05), (x+r*.65, y-r*.15), (x+r*.75, y+r*.30), (x+r*.38, y+r*.58), (x+r*.13, y+r*.30)], fill="#61BD76")
        ell((x-r*.37, y-r*.83, x+r*.10, y-r*.64), "#FFFFFF")
        angle = frame * .04
        sx = x + math.cos(angle)*r*1.55; sy = y + math.sin(angle)*r*.48
        ell((sx-4*scale, sy-4*scale, sx+4*scale, sy+4*scale), GOLD)

    elif any(word in name for word in ("atom", "electron", "molecule", "particle", "chemistry")):
        for angle in (0, 60, 120):
            draw.ellipse((x-s*1.1, y-s*.32, x+s*1.1, y+s*.32), outline="#8CB8FF", width=lw)
            points = []
            for k in range(61):
                a = math.radians(k*6 + angle)
                px = x + math.cos(a)*s; py = y + math.sin(a)*s*.32
                points.append((px, py))
            draw.line(points, fill="#8CB8FF", width=lw)
        ell((x-s*.23, y-s*.23, x+s*.23, y+s*.23), "#FFD34E", "#FFF4BD", lw)
        for angle in (frame*5, frame*5+120, frame*5+240):
            ex = x + math.cos(math.radians(angle))*s*.83; ey = y + math.sin(math.radians(angle))*s*.27
            ell((ex-5*scale, ey-5*scale, ex+5*scale, ey+5*scale), "#F05D5E", "#FFFFFF", scale)

    elif any(word in name for word in ("water", "ocean", "wave", "rain", "cloud", "water cycle")):
        points = [(x, y-s), (x-s*.48, y-s*.22), (x-s*.54, y+s*.28), (x-s*.32, y+s*.68), (x, y+s*.82), (x+s*.32, y+s*.68), (x+s*.54, y+s*.28), (x+s*.48, y-s*.22), (x, y-s)]
        draw.polygon(points, fill="#54C9F0", outline="#FFFFFF")
        ell((x-s*.24, y-s*.05, x-s*.04, y+s*.28), "#BDF4FF")
        draw.arc((x-s*.30, y+s*.24, x+s*.30, y+s*.61), 5, 165, fill="#E6FCFF", width=lw)

    elif any(word in name for word in ("energy", "electric", "lightning", "power", "charge", "voltage")):
        points = [(x+s*.08, y-s), (x-s*.42, y+s*.03), (x-s*.05, y+s*.03), (x-s*.28, y+s*.82), (x+s*.48, y-s*.13), (x+s*.12, y-s*.13)]
        draw.polygon(points, fill="#FFD34E", outline="#FFF2B0")
        draw.line(points+[points[0]], fill="#D98C16", width=lw)

    elif any(word in name for word in ("plant", "tree", "leaf", "photosynthesis", "forest", "flower")):
        draw.polygon([(x-s*.48, y+s*.30), (x+s*.48, y+s*.30), (x+s*.32, y+s*.85), (x-s*.32, y+s*.85)], fill="#C87948", outline="#7B4935")
        draw.line((x, y+s*.36, x, y-s*.63), fill="#327B42", width=lw)
        ell((x-s*.70, y-s*.50, x+s*.02, y+s*.04), "#43A95A", "#267A3C", lw)
        ell((x-s*.02, y-s*.77, x+s*.69, y-s*.16), "#6CCB70", "#267A3C", lw)
        draw.line((x-s*.53, y-s*.28, x-s*.06, y-s*.03), fill="#B7ED9B", width=scale)
        draw.line((x+s*.04, y-s*.48, x+s*.49, y-s*.28), fill="#B7ED9B", width=scale)
        ell((x+s*.62, y-s*1.0, x+s*.88, y-s*.74), "#FFD34E")

    elif any(word in name for word in ("volcano", "lava", "eruption", "magma")):
        draw.polygon([(x-s, y+s*.78), (x-s*.48, y-s*.10), (x-s*.17, y-s*.68), (x+s*.16, y-s*.68), (x+s*.48, y-s*.10), (x+s, y+s*.78)], fill="#7B5147", outline="#4E3738", width=lw)
        draw.arc((x-s*.26, y-s*.82, x+s*.26, y-s*.50), 180, 360, fill="#FF8A35", width=lw*2)
        draw.polygon([(x-s*.20, y-s*.60), (x-s*.08, y-s*.20), (x+s*.05, y-s*.08), (x+s*.20, y-s*.58)], fill="#FF7B32")
        for i in range(5):
            px = x + math.sin(frame*.12+i)*s*.38; py = y - s*(.75 + ((frame*.025+i*.23) % .5))
            ell((px-3*scale, py-3*scale, px+3*scale, py+3*scale), "#FFB64D")

    elif any(word in name for word in ("circuit", "computer", "robot", "technology", "microchip")):
        draw.rounded_rectangle((x-s*.75, y-s*.63, x+s*.75, y+s*.63), radius=8*scale, fill="#345477", outline="#BDE7FF", width=lw)
        draw.rounded_rectangle((x-s*.35, y-s*.28, x+s*.35, y+s*.28), radius=4*scale, fill="#45C8B0", outline="#E0FFF8", width=lw)
        for side in (-1, 1):
            for i in range(4):
                py = y-s*.42+i*s*.28; px1 = x+side*s*.75; px2 = x+side*s*.95
                draw.line((px1, py, px2, py), fill="#FFD34E", width=lw)
        for i in range(3):
            px = x-s*.35+i*s*.35
            draw.line((px, y-s*.63, px, y-s*.83), fill="#FFD34E", width=lw)

    elif any(word in name for word in ("heart", "blood", "body", "human", "anatomy")):
        draw.ellipse((x-s*.62, y-s*.48, x+s*.05, y+s*.25), fill="#E95669", outline="#A92F48", width=lw)
        draw.ellipse((x-s*.05, y-s*.48, x+s*.62, y+s*.25), fill="#E95669", outline="#A92F48", width=lw)
        draw.polygon([(x-s*.58, y-s*.12), (x+s*.58, y-s*.12), (x, y+s*.78)], fill="#E95669", outline="#A92F48")
        draw.line((x-s*.1, y-s*.15, x-s*.18, y+s*.35), fill="#FFB4C1", width=lw)
        draw.line((x+s*.15, y-s*.1, x+s*.05, y+s*.30), fill="#FFB4C1", width=lw)

    else:
        draw.rounded_rectangle((x-s*.20, y-s*.90, x+s*.20, y-s*.45), radius=3*scale, fill="#DFF8FF", outline="#287A9B", width=lw)
        draw.polygon([(x-s*.20, y-s*.48), (x-s*.75, y+s*.50), (x-s*.65, y+s*.78), (x+s*.65, y+s*.78), (x+s*.75, y+s*.50), (x+s*.20, y-s*.48)], fill="#DFF8FF", outline="#287A9B")
        draw.polygon([(x-s*.57, y+s*.36), (x+s*.57, y+s*.36), (x+s*.65, y+s*.63), (x-s*.65, y+s*.63)], fill="#46B9A7")
        ell((x-s*.27, y+s*.05, x-s*.10, y+s*.22), "#FFFFFF")
        ell((x+s*.14, y+s*.16, x+s*.28, y+s*.30), "#FFFFFF")

def render_character_frame(width, height, frame=0, fps=24, action="explain", emotion="curious", speaking=True, character_x=None, blink_phase=None, background="sky", title="Science Discovery", narration="", object_name="science", scene_seed=0, shot_type="presenter"):
    scale = 2
    w, h = int(width)*scale, int(height)*scale
    image = Image.new("RGB", (w, h), "#FFFFFF")
    draw = ImageDraw.Draw(image)

    ground_y = draw_background(image, draw, str(background).lower(), frame, scale)
    action = str(action or "explain").lower()
    emotion = str(emotion or "curious").lower()
    t = frame / max(1, fps)

    bob = math.sin(t*5) * 2.5 * scale
    walk = math.sin(t*8) * 7 * scale if action in ("walk", "run", "celebrate") else 0
    cx = int((character_x if character_x is not None else .35)*w + walk)
    cy = int(h*.47 + bob)
    head = int(min(w, h)*.085)

    if shot_type not in ("closeup", "object"):
        draw_science_object(draw, object_name, int(w*.76), int(h*.48), int(min(w, h)*.09), frame, scale)

    draw.ellipse((cx-42*scale, ground_y-7*scale, cx+42*scale, ground_y+5*scale), fill="#66877A")
    stride = math.sin(t*8)*10*scale if action in ("walk", "run", "celebrate") else 0
    hip = cy + head*1.5
    draw.line((cx-5*scale, hip, cx-20*scale+stride, ground_y-8*scale), fill=PANTS, width=12*scale)
    draw.line((cx+5*scale, hip, cx+20*scale-stride, ground_y-8*scale), fill=PANTS, width=12*scale)
    draw.ellipse((cx-33*scale+stride, ground_y-14*scale, cx-8*scale+stride, ground_y-3*scale), fill=WHITE, outline=INK, width=2*scale)
    draw.ellipse((cx+8*scale-stride, ground_y-14*scale, cx+33*scale-stride, ground_y-3*scale), fill=WHITE, outline=INK, width=2*scale)

    torso_top = cy + head*.45
    torso_bottom = cy + head*2.0
    draw.rounded_rectangle((cx-head*.68, torso_top, cx+head*.68, torso_bottom), radius=14*scale, fill=SHIRT, outline=INK, width=3*scale)
    draw.rectangle((cx-8*scale, cy+head*.18, cx+8*scale, cy+head*.62), fill=SKIN)

    arm_y = torso_top + head*.25
    if action in ("point", "explain", "observe"):
        ends = [(cx-head*1.35, arm_y+head*.55), (cx+head*1.75, arm_y-head*.35)]
    elif action in ("surprised", "celebrate", "run"):
        ends = [(cx-head*1.3, arm_y-head*.65), (cx+head*1.3, arm_y-head*.65)]
    elif action == "think":
        ends = [(cx-head*1.1, arm_y+head*.6), (cx+head*.75, cy-head*.15)]
    else:
        ends = [(cx-head*1.15, arm_y+head*.7), (cx+head*1.15, arm_y+head*.7)]

    for ex, ey in ends:
        draw.line((cx-head*.55, arm_y, ex, ey), fill=INK, width=10*scale)
        draw.ellipse((ex-7*scale, ey-7*scale, ex+7*scale, ey+7*scale), fill=SKIN, outline=INK, width=2*scale)

    draw.ellipse((cx-head, cy-head*1.05, cx+head, cy+head*.95), fill=SKIN, outline=INK, width=3*scale)
    draw.ellipse((cx-head*1.08, cy-head*.1, cx-head*.83, cy+head*.28), fill=SKIN, outline=INK, width=2*scale)
    draw.ellipse((cx+head*.83, cy-head*.1, cx+head*1.08, cy+head*.28), fill=SKIN, outline=INK, width=2*scale)
    draw.pieslice((cx-head*1.02, cy-head*1.12, cx+head*1.02, cy+head*.15), 180, 360, fill="#3B2B27", outline=INK, width=2*scale)

    blink = blink_phase if blink_phase is not None else t % 3.4
    eyes_closed = 3.15 < blink < 3.27
    eye_y = cy-head*.08
    for ex in (cx-head*.36, cx+head*.36):
        if eyes_closed:
            draw.line((ex-head*.13, eye_y, ex+head*.13, eye_y), fill=INK, width=3*scale)
        else:
            draw.ellipse((ex-head*.13, eye_y-head*.17, ex+head*.13, eye_y+head*.17), fill=WHITE, outline=INK, width=2*scale)
            draw.ellipse((ex-head*.055, eye_y-head*.08, ex+head*.055, eye_y+head*.09), fill=INK)

    brow_y = eye_y - head*(.36 if emotion in ("surprised", "amazed", "excited") else .28)
    draw.line((cx-head*.53, brow_y, cx-head*.22, brow_y-head*.03), fill="#3B2B27", width=3*scale)
    draw.line((cx+head*.22, brow_y-head*.03, cx+head*.53, brow_y), fill="#3B2B27", width=3*scale)

    mouth_y = cy + head*.47
    mouth_open = speaking and math.sin(t*11.5) > -.15
    if emotion in ("surprised", "amazed"):
        mouth_open = True
    if mouth_open:
        mouth_h = head*(.16 + .08*abs(math.sin(t*7)))
        draw.ellipse((cx-head*.17, mouth_y-mouth_h*.45, cx+head*.17, mouth_y+mouth_h), fill="#702D32", outline=INK, width=2*scale)
    else:
        draw.arc((cx-head*.22, mouth_y-head*.05, cx+head*.22, mouth_y+head*.22), 5, 175, fill="#8B4140", width=3*scale)

    draw.rounded_rectangle((20*scale, 14*scale, w-20*scale, 66*scale), radius=10*scale, fill="#245AA5")
    draw.text((34*scale, 23*scale), str(title or "Science Discovery")[:58], font=font(18*scale, True), fill=WHITE)

    words = str(narration or "").split()
    subtitle = " ".join(words[:12])
    if len(words) > 12: subtitle += "..."
    draw.rounded_rectangle((16*scale, h-70*scale, w-16*scale, h-12*scale), radius=8*scale, fill="#111923")
    draw.text((27*scale, h-55*scale), subtitle, font=font(12*scale), fill=WHITE)

    if emotion in ("surprised", "amazed", "excited"):
        sx, sy = cx+head*1.2, cy-head*1.35
        draw.ellipse((sx, sy, sx+12*scale, sy+12*scale), fill=GOLD)
        draw.text((sx+2*scale, sy-2*scale), "!", font=font(12*scale, True), fill=INK)

    return image.resize((int(width), int(height)), Image.Resampling.LANCZOS)

def make_scene_art(scene, idx, total, path, width=1280, height=720, ai_image_data=None):
    image = render_character_frame(width, height, frame=0, fps=12, action=scene.get("action", "explain"), emotion=scene.get("emotion", "curious"), speaking=False, background=scene.get("background", "sky"), title=scene.get("title", "Science Discovery"), narration=scene.get("narration", ""), object_name=scene.get("visual", "science"), shot_type=scene.get("shot_type", "presenter"))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", optimize=True)
    return path

async def generate_all_ai_images(scenes, out_dir, width, height):
    return [(i, None) for i in range(1, len(scenes)+1)]