#!/usr/bin/env python3
"""Render one explicitly identified, READY episode. Image prompts are never read here."""
import json, re, sys, subprocess, shutil
from pathlib import Path
import asyncio
import edge_tts

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = json.loads((ROOT/"settings.json").read_text())
episode = Path(sys.argv[1]).resolve()
if ROOT.resolve() not in episode.parents: raise SystemExit("Episode path must be inside science-channel")
if not (episode/"READY.txt").is_file(): raise SystemExit("READY.txt is missing")
meta=json.loads((episode/"episode.json").read_text())
scene_count=int(meta.get("scene_count",47))
scenes = json.loads((episode/"scenes.json").read_text())
if len(scenes)!=scene_count or [s.get("scene_number") for s in scenes]!=list(range(1,scene_count+1)):
    raise SystemExit(f"Expected exactly {scene_count} ordered scene records")
image_dir=episode/"images"
image_dir.mkdir(exist_ok=True)
if meta.get("smoke_test") is True:
    # Synthetic test frames are generated only for this explicitly marked fixture.
    for n in range(1,scene_count+1):
        target=image_dir/f"scene-{n:03d}.png"
        if not target.exists():
            color=["0x173B63","0x167C80","0xE0A82E"][(n-1)%3]
            subprocess.run(["ffmpeg","-y","-f","lavfi","-i",f"color=c={color}:s=1280x720:d=1","-frames:v","1",str(target)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
images=[]
for n in range(1,scene_count+1):
    p=image_dir/f"scene-{n:03d}.png"
    if not p.is_file(): raise SystemExit(f"Missing required image: {p.name}")
    images.append(p)
# Narration source is script.md only. Never open image-prompts.md.
script=(episode/"script.md").read_text()
blocks=re.findall(r"^## Scene\s+(\d+)\s*\n+([\s\S]*?)(?=^## Scene\s+\d+\s*$|\Z)",script,re.M)
if len(blocks)!=scene_count: raise SystemExit(f"script.md must contain exactly {scene_count} Scene sections")
narration=[]
for i,(num,body) in enumerate(blocks,1):
    if int(num)!=i: raise SystemExit("script.md scene order mismatch")
    text=re.sub(r"\s+"," ",body).strip()
    if not text: raise SystemExit(f"Empty narration in script scene {i}")
    narration.append(text)
out=episode/"output"; out.mkdir(exist_ok=True)
audio=out/"narration.mp3"
async def make_audio():
    communicate=edge_tts.Communicate(" ".join(narration),SETTINGS["voice"],rate=SETTINGS["speech_rate"])
    await communicate.save(str(audio))
asyncio.run(make_audio())
def run(cmd): subprocess.run(cmd,check=True)
probe=subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(audio)],text=True)
duration=float(probe.strip())
weights=[max(1,len(t.split())) for t in narration]; total=sum(weights)
durations=[duration*w/total for w in weights]
concat=out/"images.txt"
with concat.open("w") as f:
    for p,d in zip(images,durations):
        f.write(f"file '{p.resolve()}'\nduration {d:.4f}\n")
    f.write(f"file '{images[-1].resolve()}'\n")
silent=out/"visuals.mp4"
run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(concat),"-vf",f"scale={SETTINGS['width']}:{SETTINGS['height']}:force_original_aspect_ratio=increase,crop={SETTINGS['width']}:{SETTINGS['height']}","-r",str(SETTINGS["fps"]),"-pix_fmt","yuv420p","-an",str(silent)])
# Create simple scene-aligned SRT using audio duration and narration word proportions.
srt=out/"subtitles.srt"; cursor=0.0
def stamp(t):
    ms=round(t*1000); h=ms//3600000; ms%=3600000; m=ms//60000; ms%=60000; s=ms//1000; ms%=1000
    return f"{h:02}:{m:02}:{s:02},{ms:03}"
with srt.open("w") as f:
    for i,(text,d) in enumerate(zip(narration,durations),1):
        f.write(f"{i}\n{stamp(cursor)} --> {stamp(cursor+d)}\n{text}\n\n"); cursor+=d
video=out/"final-video.mp4"
run(["ffmpeg","-y","-i",str(silent),"-i",str(audio),"-vf",f"subtitles={srt}:force_style='FontName=Arial,FontSize=22,Outline=2,Shadow=1,MarginV=42'","-c:v","libx264","-preset","veryfast","-crf","21","-c:a","aac","-b:a","192k","-shortest","-movflags","+faststart",str(video)])
print(f"Rendered {video}")
