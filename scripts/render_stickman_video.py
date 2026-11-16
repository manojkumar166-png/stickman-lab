#!/usr/bin/env python3
"""Render a 30-second illustrated stickman short to MP4 using Pillow + FFmpeg.

This is a deterministic, API-free 2D vector-style renderer. It creates original
artwork in the reference palette (plum rooms, teal door, coral hoodie, warm light).
"""
import json
import math
import pathlib
import shutil
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = pathlib.Path("stickman-films/latest")
FILM = ROOT / "film.json"
OUTPUT = ROOT / "video.mp4"
W, H, FPS = 960, 540, 30

def font(size, bold=False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for p in candidates:
        if pathlib.Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

def ease(x):
    x = max(0.0, min(1.0, x))
    return x*x*(3-2*x)

def draw_gradient(draw, top, bottom):
    for y in range(H):
        t = y / H
        c = tuple(int(top[i]*(1-t)+bottom[i]*t) for i in range(3))
        draw.line((0,y,W,y), fill=c)

def room_scene(t, scene_i, title):
    im = Image.new("RGB", (W,H), (30,16,43))
    d = ImageDraw.Draw(im)
    warm = scene_i >= 4
    top = (74,35,83) if not warm else (115,66,77)
    bottom = (35,20,48) if not warm else (76,43,58)
    draw_gradient(d, top, bottom)
    # floor and baseboard
    d.rectangle((0,405,W,H), fill=(48,27,51) if not warm else (94,57,60))
    d.rectangle((0,400,W,408), fill=(103,59,75))
    # window with sunset skyline
    d.rounded_rectangle((80,62,310,250), radius=7, fill=(39,26,55), outline=(91,56,89), width=8)
    d.rectangle((91,73,299,239), fill=(100,65,105) if not warm else (247,174,124))
    d.rectangle((91,177,299,239), fill=(80,60,113) if not warm else (237,153,112))
    for x,hh in [(110,45),(145,68),(184,38),(225,58),(264,30)]:
        d.rectangle((x,239-hh,x+20,239), fill=(66,51,94) if not warm else (203,127,117))
    d.line((195,73,195,239), fill=(47,34,59), width=7)
    d.line((91,160,299,160), fill=(47,34,59), width=7)
    # wall picture and plant
    d.rectangle((360,105,411,164), fill=(54,35,62), outline=(173,130,119), width=4)
    d.ellipse((379,119,393,133), fill=(255,196,119))
    d.rectangle((383,132,390,151), fill=(227,115,99))
    d.ellipse((835,360,890,384), fill=(29,61,59))
    for k in range(5):
        x=862+(k-2)*10
        d.line((862,376,x,334+(k%2)*10), fill=(53,142,126), width=5)
    # teal door on right, opens during discovery beats
    door_x = 760
    d.rectangle((door_x,48,925,405), fill=(25,18,39))
    d.rectangle((door_x+9,57,916,398), fill=(35,111,111), outline=(87,174,159), width=5)
    d.rectangle((door_x+30,80,895,220), fill=(41,128,126))
    d.ellipse((door_x+28,248,door_x+42,262), fill=(242,194,116))
    # table / desk
    d.rectangle((115,355,360,383), fill=(105,57,65))
    d.rectangle((130,382,148,450), fill=(73,39,52))
    d.rectangle((328,382,346,450), fill=(73,39,52))
    d.ellipse((150,337,182,349), fill=(210,173,137))
    d.rectangle((159,323,174,341), fill=(215,202,179))
    # subtle foreground vignette
    return im

def draw_hero(im, x, y, scale, mood="sad", arm=0.0, phone=False):
    d = ImageDraw.Draw(im)
    s = scale
    # shadow
    d.ellipse((x-42*s,y+105*s,x+47*s,y+121*s), fill=(27,17,36))
    # legs and shoes
    d.line((x-12*s,y+66*s,x-20*s,y+108*s), fill=(37,31,48), width=max(3,int(10*s)))
    d.line((x+12*s,y+66*s,x+23*s,y+108*s), fill=(37,31,48), width=max(3,int(10*s)))
    d.ellipse((x-38*s,y+101*s,x-12*s,y+112*s), fill=(31,27,43))
    d.ellipse((x+12*s,y+101*s,x+40*s,y+112*s), fill=(31,27,43))
    # hoodie body, hood and arms
    d.ellipse((x-34*s,y-4*s,x+34*s,y+74*s), fill=(180,66,68))
    d.rounded_rectangle((x-31*s,y+4*s,x+31*s,y+78*s), radius=int(18*s), fill=(239,105,83), outline=(195,72,70), width=max(2,int(3*s)))
    d.arc((x-25*s,y-8*s,x+25*s,y+36*s), 180, 360, fill=(174,62,67), width=max(3,int(7*s)))
    # arm pose
    hand_x=x+42*s+arm*22*s
    hand_y=y+47*s-arm*25*s
    d.line((x+22*s,y+25*s,hand_x,hand_y), fill=(239,105,83), width=max(4,int(12*s)))
    d.ellipse((hand_x-6*s,hand_y-6*s,hand_x+6*s,hand_y+6*s), fill=(255,218,184))
    d.line((x-22*s,y+25*s,x-40*s,y+57*s), fill=(239,105,83), width=max(4,int(12*s)))
    # face
    d.ellipse((x-39*s,y-83*s,x+39*s,y-7*s), fill=(255,222,183), outline=(238,194,164), width=max(1,int(2*s)))
    # brows / eyes
    if mood == "sad":
        d.line((x-22*s,y-54*s,x-10*s,y-58*s), fill=(76,55,62), width=max(2,int(3*s)))
        d.line((x+10*s,y-58*s,x+22*s,y-54*s), fill=(76,55,62), width=max(2,int(3*s)))
        mouth=(x-10*s,y-28*s,x+10*s,y-15*s)
        d.arc(mouth, 190, 350, fill=(104,62,66), width=max(2,int(3*s)))
    elif mood == "happy":
        d.arc((x-23*s,y-59*s,x-5*s,y-43*s), 190, 350, fill=(67,51,59), width=max(2,int(3*s)))
        d.arc((x+5*s,y-59*s,x+23*s,y-43*s), 190, 350, fill=(67,51,59), width=max(2,int(3*s)))
        d.arc((x-14*s,y-35*s,x+14*s,y-11*s), 5, 175, fill=(135,62,66), width=max(2,int(3*s)))
    else:
        d.ellipse((x-19*s,y-54*s,x-12*s,y-45*s), fill=(61,49,57))
        d.ellipse((x+12*s,y-54*s,x+19*s,y-45*s), fill=(61,49,57))
        d.line((x-8*s,y-20*s,x+8*s,y-20*s), fill=(104,62,66), width=max(2,int(3*s)))
    if phone:
        d.rounded_rectangle((x-17*s,y+15*s,x+17*s,y+57*s), radius=int(5*s), fill=(31,27,49), outline=(118,102,145), width=2)
        d.rectangle((x-11*s,y+22*s,x+11*s,y+47*s), fill=(241,219,203))
        d.line((x-7*s,y+30*s,x+7*s,y+30*s), fill=(207,132,132), width=2)

def draw_prop(im, scene_i, t):
    d=ImageDraw.Draw(im)
    # Story-symbol object glows in center-left; the same visual motif evolves.
    pulse=(math.sin(t*4)+1)/2
    cx,cy=505,290
    glow=int(22+25*pulse)
    d.ellipse((cx-48-glow,cy-48-glow,cx+48+glow,cy+48+glow), fill=(94,58,105))
    d.ellipse((cx-38,cy-38,cx+38,cy+38), fill=(239,181,125), outline=(255,220,165), width=4)
    d.ellipse((cx-20,cy-20,cx+20,cy+20), fill=(255,230,184))
    if scene_i < 3:
        d.line((cx,cy-20,cx,cy+18), fill=(113,70,87), width=5)
        d.line((cx,cy,cx+18,cy-10), fill=(113,70,87), width=4)
    else:
        d.text((cx,cy-13),"✦",font=font(34,True),fill=(147,83,94),anchor="mm")

def draw_text_overlay(im, text, sub=None, end=False):
    d=ImageDraw.Draw(im)
    # translucent lower strip
    d.rectangle((0,455,W,540), fill=(22,14,32))
    d.text((W//2,481), text[:64], font=font(23,True), fill=(255,229,205), anchor="mm")
    if sub:
        d.text((W//2,515), sub[:90], font=font(13), fill=(218,194,210), anchor="mm")

def main():
    if not FILM.exists():
        raise SystemExit(f"Missing {FILM}; generate the film package first.")
    film=json.loads(FILM.read_text(encoding="utf-8"))
    scenes=film.get("scenes", [])
    if not scenes:
        raise SystemExit("film.json contains no scenes")
    ROOT.mkdir(parents=True,exist_ok=True)
    if not shutil.which("ffmpeg"):
        raise SystemExit("FFmpeg is required but was not found.")
    with tempfile.TemporaryDirectory() as tmp:
        frames=pathlib.Path(tmp)
        for frame in range(30*FPS):
            t=frame/FPS
            idx=next((i for i,s in enumerate(scenes) if float(s.get("start",0)) <= t < float(s.get("end",30))),len(scenes)-1)
            sc=scenes[idx]
            start=float(sc.get("start",0)); end=float(sc.get("end",30))
            local=max(0,t-start)
            progress=(t-start)/max(.01,end-start)
            im=room_scene(t,idx,film.get("title",""))
            # Camera-like push/pull is simulated with a smooth crop and resize.
            zoom=1.0+0.055*ease(progress) if idx%2==0 else 1.045-0.045*ease(progress)
            hero_x=int(280+80*ease(progress)) if idx in (2,3,6,7) else 280
            hero_y=int(305+4*math.sin(t*2.2))
            mood="happy" if idx>=7 else ("neutral" if idx in (2,3,4,5) else "sad")
            draw_prop(im,idx,t)
            draw_hero(im,hero_x,hero_y,1.0,mood,arm=ease(progress) if idx in (3,6,7) else 0.1,phone=(idx in (6,7,8)))
            if idx in (4,5,8):
                # warm doorway spill
                d=ImageDraw.Draw(im)
                d.polygon([(760,80),(920,80),(920,400),(760,400)],fill=(255,183,123))
                d.rectangle((770,90,910,390),fill=(255,207,157))
                draw_hero(im,820,315,0.58,"happy" if idx==8 else "sad",arm=0.5)
            caption=sc.get("title","A small moment")
            draw_text_overlay(im, film.get("title","A Stickman Short") if idx==0 else caption,
                              f"{int(t):02d}s  •  {film.get('style','2D cinematic')}")
            # End card occupies final 2 seconds.
            if t>=28:
                overlay=Image.new("RGBA",(W,H),(25,15,35,0))
                od=ImageDraw.Draw(overlay)
                od.rectangle((0,0,W,H),fill=(25,15,35,170))
                im=Image.alpha_composite(im.convert("RGBA"),overlay).convert("RGB")
                d=ImageDraw.Draw(im)
                d.text((W//2,225),film.get("end_card","One small kindness can change everything."),
                       font=font(28,True),fill=(255,224,190),anchor="mm")
                d.text((W//2,275),film.get("title","A Stickman Short"),
                       font=font(20),fill=(226,194,215),anchor="mm")
            # subtle vignette
            if zoom != 1.0:
                nw,nh=int(W/zoom),int(H/zoom)
                left=(W-nw)//2; top=(H-nh)//2
                im=im.crop((left,top,left+nw,top+nh)).resize((W,H),Image.Resampling.LANCZOS)
            im.save(frames/f"{frame:05d}.jpg",quality=88)
        cmd=["ffmpeg","-y","-loglevel","error","-framerate",str(FPS),"-i",str(frames/"%05d.jpg"),
             "-vf","scale=1920:1080:flags=lanczos,format=yuv420p","-r",str(FPS),
             "-c:v","libx264","-preset","veryfast","-crf","20","-movflags","+faststart",str(OUTPUT)]
        subprocess.run(cmd,check=True)
    print(f"Rendered MP4: {OUTPUT} (1920x1080, 30fps, 30s)")

if __name__=="__main__":
    main()
