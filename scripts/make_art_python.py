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
    bg = scene.get("background","sky").lower()
    top,bottom = PALETTES.get(bg, PALETTES["sky"])
    im = Image.new("RGB",(width,height),top)
    d = ImageDraw.Draw(im)
    for y in range(height):
        t=y/height
        import PIL.ImageColor as IC
        a,b=IC.getrgb(top),IC.getrgb(bottom)
        col=tuple(int(a[c]*(1-t)+b[c]*t) for c in range(3))
        d.line((0,y,width,y),fill=col)
    
    ground_y=int(height*.78)
    if bg in ("sky","city","desert","mountain","forest","home","lab"):
        d.rectangle((0,ground_y,width,height), fill={"sky":"#7CCB79","city":"#D6B17A","desert":"#E5B45E","mountain":"#B5D0A1","forest":"#5EAA68","home":"#D7B68F","lab":"#C5E2DF"}.get(bg,"#7CCB79"))
    
    if bg=="space":
        for _ in range(100):
            x,y=random.randrange(width),random.randrange(int(height*.75))
            rad=random.choice([1,2,3]); d.ellipse((x-rad,y-rad,x+rad,y+rad),fill="#FFFFFF")
    elif bg=="forest":
        for x in range(35,width,100):
            h=random.randrange(100,220); d.rectangle((x,ground_y-h//2,x+14,ground_y),fill="#795438")
            d.ellipse((x-40,ground_y-h-45,x+55,ground_y-h+45),fill=random.choice(["#39895B","#4B9D61","#6AB76B"]))

    cx=int(width*.38); cy=int(height*.65); head=48
    skin=random.choice(["#FFD7B0","#F4C9A6","#E8B58F"])
    shirt=random.choice(["#F15B5B","#3979D8","#F2B544","#6C56B8","#24A08B"])
    d.ellipse((cx-55,ground_y-10,cx+55,ground_y+12),fill="#66877A")
    d.line((cx,cy+70,cx-30,cy+130),fill="#252A35",width=12)
    d.line((cx,cy+70,cx+32,cy+130),fill="#252A35",width=12)
    d.line((cx,cy+10,cx,cy+75),fill=shirt,width=22)
    
    action=scene.get("action","explain").lower()
    if action in ("point","explain","observe"):
        d.line((cx,cy+25,cx+65,cy-5),fill="#252A35",width=10)
        d.ellipse((cx+58,cy-14,cx+76,cy+4),fill=skin,outline="#252A35",width=2)
    else:
        d.line((cx,cy+25,cx-45,cy-20),fill="#252A35",width=10)
        d.line((cx,cy+25,cx+45,cy-20),fill="#252A35",width=10)
        
    d.ellipse((cx-head,cy-head*2,cx+head,cy),fill=skin,outline="#252A35",width=5)
    d.ellipse((cx-20,cy-63,cx-10,cy-53),fill="#20242B")
    d.ellipse((cx+10,cy-63,cx+20,cy-53),fill="#20242B")
    d.arc((cx-18,cy-50,cx+18,cy-25),0,180,fill="#7A3D37",width=3)

    d = ImageDraw.Draw(im)
    title = (scene.get("title") or "Science Discovery")[:58]
    d.rounded_rectangle((30, 20, width - 30, 90), radius=15, fill="#2A5CAA")
    d.text((50, 40), title, font=font(28, True), fill="white")

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
    
    d.rectangle((0, height - 110, width, height), fill="black")
    y_offset = height - 90
    for line in lines:
        d.text((40, y_offset), line, font=font(24, False), fill="white")
        y_offset += 35

    im.save(path, quality=95)
    return path