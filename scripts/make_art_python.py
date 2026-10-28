import random
from PIL import Image, ImageDraw, ImageFont

PALETTES = {
 "sky":("#A7D8FF","#F5FCFF"), "lab":("#D9F2F0","#F8FFFD"),
 "space":("#101B3B","#253D70"), "ocean":("#56C5E8","#DDF8FF"),
 "forest":("#9ED69A","#E8F5C8"), "city":("#F7C98B","#FFF1D5"),
 "home":("#F4D9B7","#FFF6E8"), "cave":("#8D8A9A","#D6D0D9"),
 "desert":("#F4C477","#FFE8B0"), "mountain":("#B8D8E8","#F4FBFF")
}

def font(size, bold=False):
    try: 
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
    except: 
        return ImageFont.load_default()

async def generate_all_ai_images(scenes, out_dir, width, height):
    return [(i, None) for i in range(1, len(scenes) + 1)]

def make_scene_art(scene, idx, total, path, width=1280, height=720, ai_image_data=None):
    # --- 4X ANTI-ALIASING (DRAW AT 4K, THEN SCALE DOWN) ---
    scale = 4
    w, h = width * scale, height * scale
    
    bg = scene.get("background","sky").lower()
    top,bottom = PALETTES.get(bg, PALETTES["sky"])
    im = Image.new("RGB",(w,h),top)
    d = ImageDraw.Draw(im)
    
    # Gradient Background
    for y in range(h):
        t=y/h
        import PIL.ImageColor as IC
        a,b=IC.getrgb(top),IC.getrgb(bottom)
        col=tuple(int(a[c]*(1-t)+b[c]*t) for c in range(3))
        d.line((0,y,w,y),fill=col)
    
    ground_y=int(h*.78)
    if bg in ("sky","city","desert","mountain","forest","home","lab"):
        d.rectangle((0,ground_y,w,h), fill={"sky":"#7CCB79","city":"#D6B17A","desert":"#E5B45E","mountain":"#B5D0A1","forest":"#5EAA68","home":"#D7B68F","lab":"#C5E2DF"}.get(bg,"#7CCB79"))
    
    if bg=="space":
        for _ in range(300):
            x,y=random.randrange(w),random.randrange(int(h*.75))
            rad=random.choice([2,4,6]); d.ellipse((x-rad,y-rad,x+rad,y+rad),fill="#FFFFFF")
    elif bg=="forest":
        for x in range(35*scale,w,100*scale):
            h_tree=random.randrange(100*scale,220*scale); d.rectangle((x,ground_y-h_tree//2,x+14*scale,ground_y),fill="#795438")
            d.ellipse((x-40*scale,ground_y-h_tree-45*scale,x+55*scale,ground_y-h_tree+45*scale),fill=random.choice(["#39895B","#4B9D61","#6AB76B"]))

    # Stickman
    cx=int(w*.38); cy=int(h*.65); head=48*scale
    skin=random.choice(["#FFD7B0","#F4C9A6","#E8B58F"])
    shirt=random.choice(["#F15B5B","#3979D8","#F2B544","#6C56B8","#24A08B"])
    d.ellipse((cx-55*scale,ground_y-10*scale,cx+55*scale,ground_y+12*scale),fill="#66877A")
    d.line((cx,cy+70*scale,cx-30*scale,cy+130*scale),fill="#252A35",width=12*scale)
    d.line((cx,cy+70*scale,cx+32*scale,cy+130*scale),fill="#252A35",width=12*scale)
    d.line((cx,cy+10*scale,cx,cy+75*scale),fill=shirt,width=22*scale)
    
    action=scene.get("action","explain").lower()
    if action in ("point","explain","observe"):
        d.line((cx,cy+25*scale,cx+65*scale,cy-5*scale),fill="#252A35",width=10*scale)
        d.ellipse((cx+58*scale,cy-14*scale,cx+76*scale,cy+4*scale),fill=skin,outline="#252A35",width=2*scale)
    else:
        d.line((cx,cy+25*scale,cx-45*scale,cy-20*scale),fill="#252A35",width=10*scale)
        d.line((cx,cy+25*scale,cx+45*scale,cy-20*scale),fill="#252A35",width=10*scale)
        
    d.ellipse((cx-head,cy-head*2,cx+head,cy),fill=skin,outline="#252A35",width=5*scale)
    d.ellipse((cx-20*scale,cy-63*scale,cx-10*scale,cy-53*scale),fill="#20242B")
    d.ellipse((cx+10*scale,cy-63*scale,cx+20*scale,cy-53*scale),fill="#20242B")
    d.arc((cx-18*scale,cy-50*scale,cx+18*scale,cy-25*scale),0,180,fill="#7A3D37",width=3*scale)

    # UI Elements
    title = (scene.get("title") or "Science Discovery")[:58]
    d.rounded_rectangle((30*scale, 20*scale, w - 30*scale, 90*scale), radius=15*scale, fill="#2A5CAA")
    d.text((50*scale, 40*scale), title, font=font(28*scale, True), fill="white")

    narration = scene.get("narration", "")
    words = narration.split()
    lines = []
    current_line = ""
    for word in words:
        if len(current_line + " " + word) < 75:
            current_line += word + " "
        else:
            lines.append(current_line.strip())
            current_line = word + " "
    if current_line: lines.append(current_line.strip())
    lines = lines[:2]
    
    d.rectangle((0, h - 110*scale, w, h), fill="black")
    y_offset = h - 90*scale
    for line in lines:
        d.text((40*scale, y_offset), line, font=font(24*scale, False), fill="white")
        y_offset += 35*scale

    # Shrink back down to 720p for a beautifully smooth image
    im = im.resize((width, height), Image.Resampling.LANCZOS)
    im.save(path, quality=95)
    return path