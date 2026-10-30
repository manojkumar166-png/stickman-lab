#!/usr/bin/env python3
"""Render one READY episode using three uploaded images and generated scene cards."""
import json, re, sys, subprocess, shutil, html
from pathlib import Path
import asyncio
import edge_tts

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = json.loads((ROOT/"settings.json").read_text())
episode = Path(sys.argv[1]).resolve()
if ROOT.resolve() not in episode.parents: raise SystemExit("Episode path must be inside science-channel")
if not (episode/"READY.txt").is_file(): raise SystemExit("READY.txt is missing")
meta = json.loads((episode/"episode.json").read_text())
scene_count = int(meta.get("scene_count", SETTINGS.get("scene_count", 48)))
scenes = json.loads((episode/"scenes.json").read_text())
if len(scenes) != scene_count or [s.get("scene_number") for s in scenes] != list(range(1, scene_count+1)):
    raise SystemExit(f"Expected exactly {scene_count} ordered scene records")

image_dir = episode/"images"
incoming = image_dir/"incoming"
incoming.mkdir(parents=True, exist_ok=True)
out = episode/"output"
out.mkdir(exist_ok=True)

# Smoke-test fixtures retain their isolated synthetic-image path.
if meta.get("smoke_test") is True:
    for n in range(1, scene_count+1):
        target = image_dir/f"scene-{n:03d}.png"
        if not target.exists():
            color = ["0x173B63","0x167C80","0xE0A82E"][(n-1)%3]
            subprocess.run(["ffmpeg","-y","-f","lavfi","-i",f"color=c={color}:s=1280x720:d=1","-frames:v","1",str(target)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    visual_paths = [image_dir/f"scene-{n:03d}.png" for n in range(1,scene_count+1)]
else:
    allowed = {".png", ".jpg", ".jpeg", ".webp"}
    uploads = sorted([p for p in incoming.iterdir() if p.is_file() and p.suffix.lower() in allowed], key=lambda p:p.name.casefold())
    if len(uploads) != 3:
        raise SystemExit(f"Upload exactly 3 images (any filenames) into images/incoming/. Found {len(uploads)}.")
    normalized = image_dir/"normalized"
    normalized.mkdir(exist_ok=True)
    visual_paths = []
    for n, src in enumerate(uploads, 1):
        target = normalized/f"scene-{n:03d}.png"
        subprocess.run(["ffmpeg","-y","-i",str(src),"-frames:v","1","-vf","scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720",str(target)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        visual_paths.append(target)

# Narration comes only from script.md. Prompts are never opened by the renderer.
script = (episode/"script.md").read_text()
blocks = re.findall(r"^## Scene\s+(\d+)\s*\n+([\s\S]*?)(?=^## Scene\s+\d+\s*$|\Z)", script, re.M)
if len(blocks) != scene_count: raise SystemExit(f"script.md must contain exactly {scene_count} Scene sections")
narration = []
for i, (num, body) in enumerate(blocks, 1):
    if int(num) != i: raise SystemExit("script.md scene order mismatch")
    text = re.sub(r"\s+", " ", body).strip()
    if not text: raise SystemExit(f"Empty narration in script scene {i}")
    narration.append(text)

audio = out/"narration.mp3"
async def make_audio():
    communicate = edge_tts.Communicate(" ".join(narration), SETTINGS["voice"], rate=SETTINGS["speech_rate"])
    await communicate.save(str(audio))
asyncio.run(make_audio())

def run(cmd):
    subprocess.run(cmd, check=True)

probe = subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(audio)], text=True)
duration = float(probe.strip())
weights = [max(1,len(t.split())) for t in narration]
total = sum(weights)
durations = [duration*w/total for w in weights]

# Scenes 1–3 use uploads. Scenes 4–48 get custom non-blank scientific motion-card backgrounds.
if meta.get("smoke_test") is True:
    pass
else:
    for n in range(4, scene_count+1):
        target = out/f"generated-scene-{n:03d}.mp4"
        hue = (n*29) % 360
        # A dark science-themed animated gradient with orbit rings and scene index.
        vf = f"drawbox=x=iw*0.08:y=ih*0.12:w=iw*0.84:h=ih*0.76:color=0x18A6B0@0.22:t=5,drawbox=x=iw*0.16:y=ih*0.22:w=iw*0.68:h=ih*0.56:color=0xF5B942@0.18:t=3,drawtext=text='SCIENCE  /  SCENE {n:02d}':fontcolor=white:fontsize=48:x=(w-text_w)/2:y=h*0.43"
        subprocess.run(["ffmpeg","-y","-f","lavfi","-i",f"color=c=0x102B4E:s=1280x720:r=30:d=1","-vf",vf,"-frames:v","1",str(target)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        visual_paths.append(target)

# Build one timed still-image sequence, holding each scene for its narration share.
concat = out/"images.txt"
with concat.open("w") as f:
    for idx, d in enumerate(durations):
        path = visual_paths[idx] if idx < 3 or meta.get("smoke_test") is True else visual_paths[idx]
        f.write(f"file '{path.resolve()}'\nduration {d:.4f}\n")
    f.write(f"file '{visual_paths[-1].resolve()}'\n")
silent = out/"visuals.mp4"
run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(concat),"-vf",f"scale={SETTINGS['width']}:{SETTINGS['height']}:force_original_aspect_ratio=increase,crop={SETTINGS['width']}:{SETTINGS['height']}","-r",str(SETTINGS["fps"]),"-pix_fmt","yuv420p","-an",str(silent)])

srt = out/"subtitles.srt"
cursor = 0.0
def stamp(t):
    ms=round(t*1000); h=ms//3600000; ms%=3600000; m=ms//60000; ms%=60000; sec=ms//1000; ms%=1000
    return f"{h:02}:{m:02}:{sec:02},{ms:03}"
with srt.open("w") as f:
    for i,(text,d) in enumerate(zip(narration,durations),1):
        f.write(f"{i}\n{stamp(cursor)} --> {stamp(cursor+d)}\n{text}\n\n")
        cursor += d
video = out/"final-video.mp4"
run(["ffmpeg","-y","-i",str(silent),"-i",str(audio),"-vf",f"subtitles={srt}:force_style='FontName=Arial,FontSize=22,Outline=2,Shadow=1,MarginV=42'","-c:v","libx264","-preset","veryfast","-crf","21","-c:a","aac","-b:a","192k","-shortest","-movflags","+faststart",str(video)])
print(f"Rendered {video}")
