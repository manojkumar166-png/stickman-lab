#!/usr/bin/env python3
"""Offline, API-free stickman short-film renderer using Pillow and FFmpeg."""
from __future__ import annotations
import argparse, json, math, os, re, shutil, subprocess, tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

PALETTES = [
    ((26,35,62),(63,52,91),(245,174,113)), ((26,57,66),(43,91,91),(245,193,116)),
    ((63,39,57),(112,62,75),(255,190,137)), ((29,48,76),(56,82,116),(166,215,207)),
    ((52,43,70),(91,69,108),(245,190,155)),
]
def font(size, bold=False):
    p="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    return ImageFont.truetype(p,size) if Path(p).is_file() else ImageFont.load_default()

def split_story(story, limit=6):
    parts=[p.strip() for p in re.split(r"(?<=[.!?])\s+|\s+(?:then|next)\s+",story,flags=re.I) if p.strip()]
    if len(parts)==1 and len(parts[0].split())>18:
        words=parts[0].split(); step=max(8,math.ceil(len(words)/4))
        parts=[" ".join(words[i:i+step]) for i in range(0,len(words),step)]
    if not parts: parts=["A stickman starts an unexpected adventure."]
    if len(parts)>limit:
        parts=[" ".join(parts[round(i*len(parts)/limit):round((i+1)*len(parts)/limit)]) for i in range(limit)]
    return parts

def action_for(text):
    t=text.casefold()
    rules=[
        (("run","sprint","chase","escape"),"run"),(("jump","leap","hop"),"jump"),
        (("dance","celebrate","party"),"dance"),(("fall","trip","slip"),"fall"),
        (("wave","hello","goodbye","greet"),"wave"),(("fight","punch","kick","battle"),"fight"),
        (("stop","freeze","time"),"stop"),(("sit","rest","wait"),"sit"),
        (("walk","leave","approach","travel"),"walk"),(("point","show","discover","find","notice"),"point")]
    for words,action in rules:
        if any(word in t for word in words): return action
    return "think"

def wrap(draw,text,fnt,width):
    lines=[]; current=""
    for word in text.split():
        test=(current+" "+word).strip()
        if draw.textbbox((0,0),test,font=fnt)[2]<=width: current=test
        else:
            if current: lines.append(current)
            current=word
    if current: lines.append(current)
    return lines

def background(im,index):
    w,h=im.size; top,bottom,accent=PALETTES[index%len(PALETTES)]; d=ImageDraw.Draw(im)
    for y in range(h):
        q=y/max(1,h-1); c=tuple(int(top[i]*(1-q)+bottom[i]*q) for i in range(3))
        d.line((0,y,w,y),fill=c)
    horizon=int(h*.76); d.rectangle((0,horizon,w,h),fill=(25,29,45)); d.line((0,horizon,w,horizon),fill=accent,width=max(2,w//500))
    for i in range(9):
        bw=int(w*(.035+(i%3)*.012)); x=int((i+.5)*w/9); bh=int(h*(.10+((i*7+index*3)%8)/100))
        d.rectangle((x,horizon-bh,x+bw,horizon),fill=(31,38,59))
        for wy in range(horizon-bh+12,horizon-8,22): d.rectangle((x+7,wy,x+12,wy+7),fill=accent)
    for i in range(22):
        x=(i*137+index*83)%w; y=(i*71+index*29)%max(1,int(h*.55)); r=1+i%3
        d.ellipse((x-r,y-r,x+r,y+r),fill=(230,224,211))
    return accent

def character(im,x,ground,scale,action,phase,second=False):
    d=ImageDraw.Draw(im); s=scale; bob=math.sin(phase*2*math.pi)*(5*s if action in ("walk","run","dance") else 2*s)
    head=ground-112*s+bob; hip=ground-38*s+bob
    if action in ("jump","fall"): hip-=abs(math.sin(phase*math.pi))*48*s; head-=abs(math.sin(phase*math.pi))*48*s
    torso=head+23*s; stride=math.sin(phase*2*math.pi)*(25 if action=="run" else 17)*s
    if action=="sit": hip=ground-28*s; stride=0
    line=max(3,int(6*s)); ink=(24,27,39) if not second else (19,34,43)
    d.ellipse((x-34*s,ground-7*s,x+34*s,ground+5*s),fill=(17,20,32))
    if action=="sit":
        d.line((x,hip,x+28*s,hip+12*s,x+48*s,hip+12*s),fill=ink,width=line)
        d.line((x,hip,x-24*s,hip+13*s,x-44*s,hip+13*s),fill=ink,width=line)
    else:
        d.line((x,hip,x-14*s-stride,ground-4*s),fill=ink,width=line)
        d.line((x,hip,x+14*s+stride,ground-4*s),fill=ink,width=line)
    d.line((x,torso,x,hip),fill=ink,width=line+1)
    left=(x-27*s,torso+34*s); right=(x+27*s,torso+34*s)
    if action=="wave": right=(x+44*s,torso-28*s+math.sin(phase*8)*5*s)
    elif action=="point": right=(x+57*s,torso+2*s)
    elif action=="fight": left,right=(x-42*s,torso-2*s),(x+42*s,torso-2*s)
    elif action=="jump": left,right=(x-43*s,torso-25*s),(x+43*s,torso-25*s)
    elif action=="fall": left,right=(x-43*s,torso+45*s),(x+43*s,torso+45*s)
    elif action=="dance":
        left=(x-45*s,torso-18*s*math.sin(phase*6)); right=(x+45*s,torso-18*s*math.cos(phase*6))
    d.line((x,torso+9*s,*left),fill=ink,width=line); d.line((x,torso+9*s,*right),fill=ink,width=line)
    r=19*s; d.ellipse((x-r,head-r,x+r,head+r),fill=(247,190,151),outline=ink,width=max(2,int(2*s)))
    eye=max(2,int(2.5*s))
    for ex in (x-7*s,x+7*s): d.ellipse((ex-eye,head-3*s-eye,ex+eye,head-3*s+eye),fill=ink)
    if action in ("dance","wave"): d.arc((x-8*s,head+2*s,x+8*s,head+13*s),5,175,fill=ink,width=max(2,int(2*s)))
    else: d.line((x-5*s,head+9*s,x+5*s,head+9*s),fill=ink,width=max(2,int(2*s)))

def prop(im,story,accent,t):
    d=ImageDraw.Draw(im); s=story.casefold(); w,h=im.size; x,y=int(w*.72),int(h*.56); r=int(min(w,h)*.045)
    if any(k in s for k in ("ball","football","basket")):
        d.ellipse((x-r,y-r,x+r,y+r),fill=(239,125,75),outline=(255,232,196),width=4)
        d.arc((x-r,y-r,x+r,y+r),40,220,fill=(70,48,54),width=3)
    elif any(k in s for k in ("door","gate","portal")):
        d.rounded_rectangle((x-2*r,y-3*r,x+2*r,y+3*r),radius=r,fill=(36,119,119),outline=accent,width=5)
        d.ellipse((x+r,y,x+r+6,y+6),fill=(255,218,135))
    elif any(k in s for k in ("phone","message","text")):
        d.rounded_rectangle((x-r,y-2*r,x+r,y+2*r),radius=8,fill=(28,31,48),outline=accent,width=4)
        d.line((x-r//2,y-r,x+r//2,y-r),fill=(255,255,255),width=3)
    elif any(k in s for k in ("star","wish","magic","time")):
        rr=int(r*(1+.12*math.sin(t*5))); d.ellipse((x-2*rr,y-2*rr,x+2*rr,y+2*rr),fill=(255,202,115))
        d.ellipse((x-rr,y-rr,x+rr,y+rr),fill=(255,241,190))
    else: d.ellipse((x-r,y-r,x+r,y+r),fill=accent,outline=(255,239,209),width=4)

def render(size,scene,index,count,action,progress,t,title):
    w,h=size; im=Image.new("RGB",size); accent=background(im,index); prop(im,scene,accent,t)
    ground=int(h*.77); travel=(progress-.5)*w*.22 if action in ("walk","run") else math.sin(progress*math.pi)*w*.06
    scale=min(w,h)/720; character(im,int(w*.37+travel),ground,scale,action,progress)
    if any(k in scene.casefold() for k in ("friend","stranger","someone","together","meet","people")):
        character(im,int(w*.61),ground,scale*.88,"wave" if index%2 else "think",progress,True)
    d=ImageDraw.Draw(im); band=int(h*.81); d.rectangle((0,band,w,h),fill=(18,21,36))
    tf=font(max(18,int(h*.032)),True); bf=font(max(15,int(h*.022)))
    d.text((int(w*.05),int(h*.84)),title[:70],font=tf,fill=(255,229,198))
    for j,line in enumerate(wrap(d,scene,bf,int(w*.90))[:2]): d.text((int(w*.05),int(h*.895)+j*int(h*.035)),line,font=bf,fill=(221,222,231))
    d.text((int(w*.95),int(h*.85)),f"{index+1}/{count}",font=bf,fill=accent,anchor="ra")
    return im

def main():
    p=argparse.ArgumentParser(description="Free offline stickman MP4 generator")
    p.add_argument("--story",default=os.getenv("STICKMAN_STORY","A curious stickman finds a glowing door, opens it, and discovers a brighter world."))
    p.add_argument("--title",default=os.getenv("STICKMAN_TITLE","A Stickman Short"))
    p.add_argument("--seconds",type=int,default=int(os.getenv("STICKMAN_SECONDS","20")))
    p.add_argument("--fps",type=int,default=24); p.add_argument("--width",type=int,default=1280); p.add_argument("--height",type=int,default=720)
    p.add_argument("--output-dir",default="output/free-stickman"); a=p.parse_args()
    if not shutil.which("ffmpeg"): raise SystemExit("FFmpeg is required.")
    if not 5<=a.seconds<=60: raise SystemExit("--seconds must be between 5 and 60.")
    if a.fps not in (24,30): raise SystemExit("--fps must be 24 or 30.")
    if a.width<640 or a.height<360: raise SystemExit("Minimum resolution is 640x360.")
    out=Path(a.output_dir); out.mkdir(parents=True,exist_ok=True); scenes=split_story(a.story); actions=[action_for(s) for s in scenes]
    per=a.seconds/len(scenes)
    film={"title":a.title,"story":a.story,"duration_seconds":a.seconds,"fps":a.fps,"resolution":f"{a.width}x{a.height}",
          "production":"Offline Python/Pillow + FFmpeg; no API keys or paid services",
          "scenes":[{"number":i+1,"text":s,"action":actions[i],"duration":per} for i,s in enumerate(scenes)]}
    (out/"storyboard.json").write_text(json.dumps(film,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (out/"storyboard.md").write_text("# "+a.title+"\n\n"+a.story+"\n\n"+"\n".join(f"## Scene {i+1} — {actions[i]}\n\n{s}\n" for i,s in enumerate(scenes)),encoding="utf-8")
    total=a.seconds*a.fps
    with tempfile.TemporaryDirectory(prefix="free-stickman-") as td:
        tmp=Path(td)
        for frame in range(total):
            t=frame/a.fps; idx=min(len(scenes)-1,int(t/per)); local=(t-idx*per)/per
            image=render((a.width,a.height),scenes[idx],idx,len(scenes),actions[idx],local,t,a.title)
            image.save(tmp/f"frame-{frame:06d}.jpg",quality=90,optimize=True)
            if frame%(a.fps*5)==0: print(f"Rendered {frame}/{total} frames",flush=True)
        video=out/"stickman-short.mp4"
        subprocess.run(["ffmpeg","-y","-hide_banner","-loglevel","error","-framerate",str(a.fps),"-i",str(tmp/"frame-%06d.jpg"),
            "-c:v","libx264","-preset","veryfast","-crf","20","-pix_fmt","yuv420p","-movflags","+faststart","-t",str(a.seconds),str(video)],check=True)
    if not video.is_file() or video.stat().st_size<10000: raise SystemExit("MP4 validation failed.")
    probe=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(video)],check=True,capture_output=True,text=True)
    print(f"VIDEO_READY={video}\nDURATION_SECONDS={probe.stdout.strip()}\nSIZE_BYTES={video.stat().st_size}")

if __name__=="__main__": main()
