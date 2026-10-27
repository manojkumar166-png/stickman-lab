from PIL import Image, ImageDraw, ImageFont
import hashlib, math, random

PALETTES = {
 "sky":("#A7D8FF","#F5FCFF"), "lab":("#D9F2F0","#F8FFFD"),
 "space":("#101B3B","#253D70"), "ocean":("#56C5E8","#DDF8FF"),
 "forest":("#9ED69A","#E8F5C8"), "city":("#F7C98B","#FFF1D5"),
 "home":("#F4D9B7","#FFF6E8"), "cave":("#8D8A9A","#D6D0D9"),
 "desert":("#F4C477","#FFE8B0"), "mountain":("#B8D8E8","#F4FBFF")
}
def font(size, bold=False):
    options = (["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"] if bold else
               ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"])
    try: return ImageFont.truetype(options[0], size)
    except: return ImageFont.load_default()
def make_scene_art(scene, idx, total, path, width=1280, height=720):
    seed = int(hashlib.sha256((scene.get("visual","")+str(idx)).encode()).hexdigest()[:8],16)
    r = random.Random(seed)
    bg = scene.get("background","sky").lower()
    top,bottom = PALETTES.get(bg, PALETTES["sky"])
    im = Image.new("RGB",(width,height),top)
    d = ImageDraw.Draw(im)
    # Gradient sky/background
    import PIL.ImageColor as IC
    a,b=IC.getrgb(top),IC.getrgb(bottom)
    for y in range(height):
        t=y/height
        col=tuple(int(a[c]*(1-t)+b[c]*t) for c in range(3))
        d.line((0,y,width,y),fill=col)
    # Ground and setting-specific scenery
    ground_y=int(height*.78)
    if bg in ("sky","city","desert","mountain","forest","home","lab"):
        d.rectangle((0,ground_y,width,height), fill={"sky":"#7CCB79","city":"#D6B17A","desert":"#E5B45E","mountain":"#B5D0A1","forest":"#5EAA68","home":"#D7B68F","lab":"#C5E2DF"}.get(bg,"#7CCB79"))
    if bg=="space":
        for _ in range(100):
            x,y=r.randrange(width),r.randrange(int(height*.75))
            rad=r.choice([1,2,3]); d.ellipse((x-rad,y-rad,x+rad,y+rad),fill="#FFFFFF")
        d.ellipse((width*.72,height*.12,width*.87,height*.32),fill="#F2E7B8")
    elif bg=="ocean":
        for y in range(int(height*.48),height,32):
            d.arc((r.randrange(-100,100),y,width+r.randrange(0,100),y+50),0,180,fill="#FFFFFF",width=4)
    elif bg=="forest":
        for x in range(35,width,100):
            h=r.randrange(100,220); d.rectangle((x,ground_y-h//2,x+14,ground_y),fill="#795438")
            d.ellipse((x-40,ground_y-h-45,x+55,ground_y-h+45),fill=r.choice(["#39895B","#4B9D61","#6AB76B"]))
    elif bg=="city":
        for x in range(0,width,110):
            h=r.randrange(100,260); d.rectangle((x,ground_y-h,x+85,ground_y),fill=r.choice(["#E68D72","#E9B85F","#A3B9D7"]))
            for wy in range(ground_y-h+20,ground_y-15,35):
                for wx in range(x+15,x+75,30): d.rectangle((wx,wy,wx+12,wy+15),fill="#FFF1B5")
    elif bg=="lab":
        d.rectangle((width*.62,height*.22,width*.9,height*.63),fill="#FFFFFF",outline="#6EAAA7",width=5)
        d.rectangle((width*.68,height*.3,width*.75,height*.5),fill="#9FE8F1",outline="#477C94",width=3)
        d.ellipse((width*.78,height*.32,width*.86,height*.42),fill="#F2B7D5")
    elif bg=="home":
        d.polygon([(width*.08,height*.48),(width*.25,height*.28),(width*.42,height*.48)],fill="#D77B62")
        d.rectangle((width*.12,height*.48,width*.38,height*.78),fill="#FFF0D5",outline="#9A755E",width=4)
        d.rectangle((width*.2,height*.57,width*.27,height*.67),fill="#8DD5E8")
    # Sun/clouds
    if bg in ("sky","city","mountain","desert"):
        d.ellipse((width-180,50,width-90,140),fill="#FFE47A")
        for cx,cy in [(170,130),(410,90),(850,160)]:
            d.ellipse((cx,cy,cx+100,cy+48),fill="#FFFFFF")
            d.ellipse((cx+25,cy-20,cx+80,cy+45),fill="#FFFFFF")
    # Main stick character, slightly varied pose
    cx=int(width*(.38 + (idx%3)*.06)); cy=int(height*.65)
    head=48
    skin=r.choice(["#FFD7B0","#F4C9A6","#E8B58F"])
    shirt=r.choice(["#F15B5B","#3979D8","#F2B544","#6C56B8","#24A08B"])
    # shadow
    d.ellipse((cx-55,ground_y-10,cx+55,ground_y+12),fill="#66877A")
    # legs
    d.line((cx,cy+70,cx-30,cy+130),fill="#252A35",width=12)
    d.line((cx,cy+70,cx+32,cy+130),fill="#252A35",width=12)
    # torso
    d.line((cx,cy+10,cx,cy+75),fill=shirt,width=22)
    action=scene.get("action","explain").lower()
    if action in ("point","explain","observe"):
        d.line((cx,cy+25,cx+65,cy-5),fill="#252A35",width=10)
        d.ellipse((cx+58,cy-14,cx+76,cy+4),fill=skin,outline="#252A35",width=2)
        d.line((cx,cy+25,cx-38,cy+48),fill="#252A35",width=10)
    elif action in ("celebrate","surprised"):
        d.line((cx,cy+25,cx-45,cy-20),fill="#252A35",width=10)
        d.line((cx,cy+25,cx+45,cy-20),fill="#252A35",width=10)
    elif action=="run":
        d.line((cx,cy+25,cx-50,cy+10),fill="#252A35",width=10)
        d.line((cx,cy+25,cx+50,cy+5),fill="#252A35",width=10)
    else:
        d.line((cx,cy+25,cx-42,cy+48),fill="#252A35",width=10)
        d.line((cx,cy+25,cx+42,cy+48),fill="#252A35",width=10)
    # head + face
    d.ellipse((cx-head,cy-head*2,cx+head,cy),fill=skin,outline="#252A35",width=5)
    d.ellipse((cx-20,cy-63,cx-10,cy-53),fill="#20242B")
    d.ellipse((cx+10,cy-63,cx+20,cy-53),fill="#20242B")
    d.arc((cx-18,cy-50,cx+18,cy-25),0,180,fill="#7A3D37",width=3)
    # speech-free visual doodles based on scene index
    for j in range(3):
        x=width*.65+j*75
        yy=height*.35+math.sin(idx+j)*35
        d.ellipse((int(x),int(yy),int(x+45),int(yy+45)),fill=r.choice(["#FFE47A","#F4A7C4","#8ED8F2"]),outline="#FFFFFF",width=3)
    # Scene heading and visual hint, avoid embedding long generated text
    title=(scene.get("title") or f"Science discovery")[:58]
    d.rounded_rectangle((40,35,width-40,112),radius=20,fill="#FFFFFF",outline="#26364A",width=3)
    d.text((65,53),title,font=font(30,True),fill="#253247")
    d.rounded_rectangle((40,height-70,300,height-28),radius=12,fill="#FFFFFF")
    d.text((55,height-62),f"SCIENCE • SCENE {idx}/{total}",font=font(16,True),fill="#34445A")
    im.save(path, quality=92)
