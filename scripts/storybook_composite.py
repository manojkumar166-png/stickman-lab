"""Original 2D storybook + science illustration renderer.

Uses Pillow only: no AI image generation, no Blender, and no external image API.
Scenes combine layered painted landscapes with topic-aware scientific drawings.
"""
from __future__ import annotations

import math
import random
import re
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

PALETTES = [
    ((198, 226, 218), (247, 218, 166), (56, 112, 91), (38, 76, 70)),
    ((180, 211, 231), (249, 210, 165), (77, 128, 133), (44, 75, 99)),
    ((215, 205, 232), (250, 219, 177), (113, 113, 155), (58, 68, 104)),
    ((184, 222, 197), (250, 227, 177), (91, 143, 98), (45, 91, 69)),
]

def _gradient(size, top, bottom):
    w, h = size
    strip = Image.new("RGB", (1, h))
    p = strip.load()
    for y in range(h):
        t = y / max(1, h - 1)
        p[0, y] = tuple(round(top[i] * (1-t) + bottom[i] * t) for i in range(3))
    return strip.resize((w, h), Image.Resampling.BICUBIC).convert("RGBA")

def _cloud(d, x, y, s, fill):
    d.ellipse((x-s, y-s*.30, x+s*.05, y+s*.55), fill=fill)
    d.ellipse((x-s*.45, y-s*.8, x+s*.45, y+s*.45), fill=fill)
    d.ellipse((x, y-s*.52, x+s, y+s*.48), fill=fill)
    d.rounded_rectangle((x-s*.65, y, x+s*.75, y+s*.45), radius=int(s*.2), fill=fill)

def _tree(d, x, ground, scale, foliage, trunk=(104, 82, 60, 255)):
    d.rounded_rectangle((x-scale*.055, ground-scale*.7, x+scale*.055, ground), radius=max(2,int(scale*.025)), fill=trunk)
    for dx, dy, r in [(-.20,-.68,.27),(.02,-.88,.30),(.23,-.66,.27),(-.02,-.52,.25)]:
        d.ellipse((x+(dx-r)*scale, ground+(dy-r)*scale, x+(dx+r)*scale, ground+(dy+r)*scale), fill=foliage)

def _landscape(image, rng, palette, theme):
    w, h = image.size
    sky, light, green, deep = palette
    d = ImageDraw.Draw(image, "RGBA")
    # Warm sun and delicate halo.
    sx, sy, sr = int(w*.79), int(h*.20), int(min(w,h)*.075)
    halo = Image.new("RGBA", image.size, (0,0,0,0))
    hd = ImageDraw.Draw(halo)
    hd.ellipse((sx-sr*2.3, sy-sr*2.3, sx+sr*2.3, sy+sr*2.3), fill=(*light, 55))
    halo = halo.filter(ImageFilter.GaussianBlur(max(8,int(sr*.55))))
    image.alpha_composite(halo)
    d = ImageDraw.Draw(image, "RGBA")
    d.ellipse((sx-sr, sy-sr, sx+sr, sy+sr), fill=(*light, 245))
    # Hand-built cloud clusters, irregular mountain silhouettes and layered hills.
    for i in range(4):
        x = int(w*(.12 + i*.22 + rng.uniform(-.035,.035)))
        y = int(h*(.17 + rng.uniform(-.045,.045)))
        _cloud(d, x, y, int(w*rng.uniform(.035,.065)), (255,250,232,125))
    ridge1 = [(0,h*.57)]
    for i in range(9):
        ridge1.append((int(w*i/8), int(h*(.40 + rng.random()*.14))))
    ridge1 += [(w,h*.68),(w,h),(0,h)]
    d.polygon(ridge1, fill=(*sky, 210))
    ridge2 = [(0,h*.68)]
    for i in range(11):
        ridge2.append((int(w*i/10), int(h*(.53 + rng.random()*.13))))
    ridge2 += [(w,h*.8),(w,h),(0,h)]
    d.polygon(ridge2, fill=(*green, 170))
    # Rolling foreground.
    ridge3 = [(0,h*.79)]
    for i in range(13):
        ridge3.append((int(w*i/12), int(h*(.70 + rng.random()*.11))))
    ridge3 += [(w,h),(0,h)]
    d.polygon(ridge3, fill=(*deep, 235))
    # Foreground trees vary in size and spacing to create depth.
    for layer, count in [(0,10),(1,7)]:
        for _ in range(count):
            x = rng.randint(-int(w*.03), int(w*1.03))
            ground = int(h*(.91 if layer == 0 else .82))
            scale = rng.uniform(.055,.12)*w*(1 if layer == 0 else .72)
            color = (*deep, 245) if layer == 0 else (*green, 220)
            _tree(d, x, ground, scale, color)
    # Fine grass strokes add a lightly illustrated finish.
    for _ in range(150):
        x = rng.randint(0,w-1); y = rng.randint(int(h*.82),h-1)
        length = rng.randint(3,12)
        d.line((x,y,x+rng.randint(-3,3),y-length), fill=(224,226,167,rng.randint(35,95)), width=1)

def _stars(d, rng, w, h):
    for _ in range(180):
        x, y = rng.randrange(w), rng.randrange(int(h*.82))
        r = rng.choice([1,1,2,2,3])
        d.ellipse((x-r,y-r,x+r,y+r), fill=(255,248,219,rng.randint(95,230)))

def _science_overlay(image, text, title, rng):
    w,h = image.size
    t = text.lower()
    d = ImageDraw.Draw(image, "RGBA")
    # A translucent parchment-like panel anchors the science drawing without
    # turning the entire image into a UI card.
    panel = (int(w*.59), int(h*.12), int(w*.94), int(h*.65))
    d.rounded_rectangle(panel, radius=int(w*.018), fill=(255,249,225,178), outline=(255,255,255,190), width=2)
    cx, cy = int(w*.765), int(h*.375)
    scale = min(w,h)
    def line(points, fill=(51,85,100,235), width=4):
        d.line(points, fill=fill, width=width, joint="curve")
    def dot(x,y,r,fill):
        d.ellipse((x-r,y-r,x+r,y+r), fill=fill)
    # Accurate conceptual shapes are intentionally schematic, not claimed to be
    # to scale. Scene narration should explain the mechanism.
    if any(k in t for k in ("atom","electron","molecule","chemical","bond","particle","quantum")):
        for rx, ry, angle in [(scale*.105,scale*.045,0),(scale*.105,scale*.045,60),(scale*.105,scale*.045,120)]:
            pts=[]
            for j in range(121):
                a=j*math.tau/120
                xx=rx*math.cos(a); yy=ry*math.sin(a)
                ar=math.radians(angle)
                pts.append((cx+xx*math.cos(ar)-yy*math.sin(ar),cy+xx*math.sin(ar)+yy*math.cos(ar)))
            line(pts,(55,111,138,220),max(2,int(scale*.004)))
        dot(cx,cy,scale*.028,(241,156,74,255))
        for x,y,c in [(cx-scale*.09,cy-scale*.035,(68,155,204,255)),(cx+scale*.085,cy-scale*.02,(213,94,107,255)),(cx,cy+scale*.09,(78,157,122,255))]:
            dot(x,y,scale*.017,c)
    elif any(k in t for k in ("cell","bacteria","virus","membrane","nucleus","mitochond")):
        d.ellipse((cx-scale*.12,cy-scale*.105,cx+scale*.12,cy+scale*.105),fill=(137,194,170,210),outline=(48,112,93,255),width=4)
        d.ellipse((cx-scale*.043,cy-scale*.045,cx+scale*.043,cy+scale*.045),fill=(113,119,176,245))
        for j in range(9):
            a=j*math.tau/9
            x=cx+math.cos(a)*scale*.082; y=cy+math.sin(a)*scale*.064
            d.ellipse((x-scale*.014,y-scale*.011,x+scale*.014,y+scale*.011),fill=(236,170,91,235))
    elif any(k in t for k in ("dna","gene","genetic","double helix")):
        pts1=[]; pts2=[]
        for j in range(100):
            y=cy-scale*.14+j*(scale*.28/99)
            x=cx+math.sin(j*.19)*scale*.055
            pts1.append((x,y)); pts2.append((2*cx-x,y))
        line(pts1,(71,132,190,255),max(3,int(scale*.008)))
        line(pts2,(208,103,121,255),max(3,int(scale*.008)))
        for j in range(0,100,7): line([pts1[j],pts2[j]],(92,113,126,190),2)
    elif any(k in t for k in ("planet","moon","mars","jupiter","earth","solar system","orbit","galaxy","star","space","black hole","universe")):
        rr=scale*.10
        d.ellipse((cx-rr,cy-rr,cx+rr,cy+rr),fill=(85,153,181,255),outline=(255,255,255,230),width=3)
        for j in range(5):
            yy=cy-rr*.72+j*rr*.34
            d.arc((cx-rr*.82,yy-rr*.15,cx+rr*.82,yy+rr*.22),0,180,fill=(197,219,190,220),width=3)
        d.ellipse((cx-rr*1.65,cy-rr*.43,cx+rr*1.65,cy+rr*.43),outline=(208,160,99,230),width=3)
        dot(cx+rr*1.5,cy,scale*.012,(245,178,89,255))
    elif any(k in t for k in ("water cycle","evaporat","condens","rain","cloud","weather","water","ocean","river")):
        # Water body, upward evaporation arrows and cloud/rain.
        d.polygon([(cx-scale*.15,cy+scale*.07),(cx-scale*.12,cy+scale*.14),(cx+scale*.14,cy+scale*.14),(cx+scale*.16,cy+scale*.07)],fill=(80,164,202,230))
        _cloud(d,cx,cy-scale*.08,scale*.045,(255,255,255,245))
        for dx in [-.07,0,.07]:
            x=cx+scale*dx
            line([(x,cy+scale*.045),(x,cy-scale*.005)],(56,128,162,230),3)
            line([(x-4,cy-scale*.005),(x,cy-scale*.014),(x+4,cy-scale*.005)],(56,128,162,230),3)
    elif any(k in t for k in ("plant","photosynth","leaf","tree","flower","forest","chlorophyll")):
        line([(cx,cy+scale*.13),(cx,cy-scale*.08)],(61,124,75,255),max(4,int(scale*.01)))
        for side in [-1,1]:
            d.ellipse((cx+side*scale*.015-scale*.065,cy-scale*.06-scale*.03,cx+side*scale*.015+scale*.065,cy+scale*.005),fill=(87,164,96,240),outline=(49,115,67,255),width=2)
        dot(cx+scale*.11,cy-scale*.10,scale*.025,(246,190,79,255))
        line([(cx+scale*.09,cy-scale*.06),(cx+scale*.045,cy-scale*.02)],(225,157,63,220),3)
    elif any(k in t for k in ("brain","neuron","nerve","memory","heart","blood","body","lung","breath")):
        # Stylized anatomy diagram with connected lobes / vessels.
        col=(205,110,124,245)
        for dx,dy,r in [(-.045,-.01,.055),(.015,-.055,.06),(.065,-.015,.05),(.02,.045,.055),(-.045,.045,.045)]:
            d.ellipse((cx+scale*(dx-r),cy+scale*(dy-r),cx+scale*(dx+r),cy+scale*(dy+r)),fill=col,outline=(150,73,94,255),width=2)
        line([(cx,cy+scale*.08),(cx,cy+scale*.14)],(150,73,94,255),4)
    elif any(k in t for k in ("volcano","lava","eruption","earthquake","tectonic","rock","geology")):
        d.polygon([(cx-scale*.16,cy+scale*.12),(cx-scale*.055,cy-scale*.08),(cx,cy-scale*.015),(cx+scale*.055,cy-scale*.08),(cx+scale*.16,cy+scale*.12)],fill=(113,100,96,255),outline=(70,71,78,255))
        line([(cx,cy-scale*.07),(cx,cy-scale*.015)],(239,111,63,255),max(4,int(scale*.012)))
        for j in range(6):
            x=cx+math.sin(j*4)*scale*.05
            y=cy-scale*(.10+(j%3)*.025)
            dot(x,y,scale*.009,(241,133,69,240))
    else:
        # General force / energy / sound waves.
        for j in range(3):
            box=(cx-scale*(.12+j*.025),cy-scale*(.10+j*.025),cx+scale*(.12+j*.025),cy+scale*(.10+j*.025))
            d.arc(box,205,335,fill=(69,133,158,220-j*45),width=4)
        dot(cx,cy,scale*.032,(238,166,81,255))
    # Fine paper grain is subtle and does not obscure the science drawing.
    # The title is placed in a restrained lower ribbon, avoiding dense text on art.
    d = ImageDraw.Draw(image, "RGBA")
    d.rectangle((0,int(h*.89),w,h),fill=(24,49,47,185))
    # Keep text rendering dependent on standard system fonts.
    try:
        from PIL import ImageFont
        font_path="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        f=ImageFont.truetype(font_path,max(20,int(h*.033)))
    except Exception:
        f=ImageFont.load_default()
    label=(title or "A science discovery").strip()
    if len(label)>70: label=label[:67].rstrip()+"…"
    d.text((int(w*.045),int(h*.915)),label,font=f,fill=(255,250,230,250),stroke_width=1,stroke_fill=(30,55,50,180))

def render_storybook_stills(story: dict, out_dir: Path, width: int, height: int):
    out_dir=Path(out_dir); out_dir.mkdir(parents=True,exist_ok=True)
    topic=str(story.get("topic","Science discovery"))
    credits=[]
    scenes=story.get("scenes",[])
    if not scenes: raise RuntimeError("No scenes to illustrate.")
    for i,scene in enumerate(scenes,1):
        title=str(scene.get("title") or topic)
        narration=str(scene.get("narration") or "")
        visual=str(scene.get("visual") or "")
        bg=str(scene.get("background") or "")
        key=" ".join([topic,title,narration,visual,bg]).lower()
        seed=int.from_bytes((topic+"|"+title+"|"+str(i)).encode("utf-8"),"little") % (2**32)
        rng=random.Random(seed)
        palette=PALETTES[seed%len(PALETTES)]
        night=any(k in key for k in ("night","space","planet","galaxy","universe","star","moon","black hole","astronaut","cosmos"))
        if night:
            image=_gradient((width,height),(20,31,65),(65,65,103))
            _stars(ImageDraw.Draw(image,"RGBA"),rng,width,height)
            # Celestial glow and a layered alien horizon make space scenes atmospheric.
            d=ImageDraw.Draw(image,"RGBA")
            for j in range(5):
                x=int(width*(j/4))
                y=int(height*(.68+rng.random()*.10))
                d.ellipse((x-width*.22,y-height*.02,x+width*.22,y+height*.30),fill=(79+j*5,100+j*4,135+j*3,100))
            _science_overlay(image,key,title,rng)
        else:
            image=_gradient((width,height),palette[0],palette[1])
            _landscape(image,rng,palette,bg)
            _science_overlay(image,key,title,rng)
        # Gentle color grade and fine grain provide a tactile illustrated feel.
        image=image.convert("RGB")
        grain=Image.new("RGB",image.size)
        gp=grain.load()
        for y in range(height):
            for x in range(width):
                n=rng.choice((-2,-1,0,0,0,1,2))
                gp[x,y]=(max(0,min(255,244+n)),max(0,min(255,238+n)),max(0,min(255,224+n)))
        image=Image.blend(image,grain,0.035)
        path=out_dir/f"scene-{i:03d}.png"
        image.save(path,"PNG",optimize=True)
        credits.append({"scene":i,"scene_title":title,"style":"original layered 2D storybook + science illustration","source":"Original Pillow illustration","license":"Created by this workflow; no external image assets","artist":"Workflow-generated","notes":"Conceptual schematic; not to scale. Verify scientific details against narration."})
        if i==1 or i%8==0 or i==len(scenes):
            print(f"Illustrated scene {i}/{len(scenes)}: {title}",flush=True)
    return credits
