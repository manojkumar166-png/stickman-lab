#!/usr/bin/env python3
"""Render one READY episode from either a ZIP archive or individual scene images."""
import json, re, sys, subprocess, zipfile
from pathlib import Path, PurePosixPath
import asyncio
import edge_tts

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = json.loads((ROOT/"settings.json").read_text())
episode = Path(sys.argv[1]).resolve()
if ROOT.resolve() not in episode.parents:
    raise SystemExit("Episode path must be inside science-channel")
if not (episode/"READY.txt").is_file():
    raise SystemExit("READY.txt is missing")
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
# Temporary render assets stay separate from the final deliverable.
work = out/"work"
work.mkdir(exist_ok=True)
allowed = {".png", ".jpg", ".jpeg", ".webp"}

def scene_number(path):
    match = re.search(r"(?:scene[-_ ]*)?(\d{1,3})$", path.stem, re.I)
    return int(match.group(1)) if match else None

def normalize(src, number, target_dir):
    target = target_dir/f"scene-{number:03d}.png"
    subprocess.run(["ffmpeg","-y","-i",str(src),"-frames:v","1","-vf","scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720",str(target)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    return target

# Explicit smoke-test fixtures remain isolated from real episode behavior.
if meta.get("smoke_test") is True:
    visual_paths = []
    for n in range(1, scene_count+1):
        target = work/f"smoke-scene-{n:03d}.png"
        color = ["0x173B63","0x167C80","0xE0A82E"][(n-1)%3]
        subprocess.run(["ffmpeg","-y","-f","lavfi","-i",f"color=c={color}:s=1280x720:d=1","-frames:v","1",str(target)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        visual_paths.append(target)
else:
    archives = sorted([p for p in incoming.iterdir() if p.is_file() and p.suffix.lower()==".zip"], key=lambda p:p.name.casefold())
    individual = sorted([p for p in incoming.iterdir() if p.is_file() and p.suffix.lower() in allowed], key=lambda p:p.name.casefold())
    if archives and individual:
        raise SystemExit("Upload either ZIP archive(s) or individual image files, not both in the same incoming folder.")
    sources = []
    if archives:
        if len(archives) != 1:
            raise SystemExit("Upload exactly one ZIP archive per episode.")
        extract_dir = work/"unzipped-images"
        extract_dir.mkdir(exist_ok=True)
        with zipfile.ZipFile(archives[0]) as zf:
            members = []
            for info in zf.infolist():
                if info.is_dir():
                    continue
                member = PurePosixPath(info.filename)
                if member.is_absolute() or ".." in member.parts:
                    raise SystemExit("ZIP contains an unsafe path.")
                if member.suffix.lower() in allowed:
                    members.append(info)
            if len(members) != scene_count:
                raise SystemExit(f"ZIP must contain exactly {scene_count} images; found {len(members)}.")
            for info in members:
                dest = extract_dir/Path(info.filename).name
                with zf.open(info) as src, dest.open("wb") as dst:
                    dst.write(src.read())
                sources.append(dest)
    else:
        if len(individual) != scene_count:
            raise SystemExit(f"Upload exactly {scene_count} individual images or one ZIP containing {scene_count}; found {len(individual)} images.")
        sources = individual

    # Preflight uploaded images before spending time generating narration.
    if len({p.name.casefold() for p in sources}) != len(sources):
        raise SystemExit("Image filenames collide after ZIP extraction; give every scene a unique filename.")
    for source in sources:
        check = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(source), "-frames:v", "1", "-f", "null", "-"],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True
        )
        if check.returncode != 0:
            raise SystemExit(f"Image validation failed for {source.name}: {check.stderr[-500:]}")
    # If filenames contain scene numbers, honor those; otherwise use alphabetical order.
    numbered = [scene_number(p) for p in sources]
    if all(n is not None for n in numbered):
        if sorted(numbered) != list(range(1, scene_count+1)):
            raise SystemExit("Numbered image filenames must cover scene-001 through scene-048 exactly, without duplicates.")
        ordered = [p for _, p in sorted(zip(numbered, sources), key=lambda item:item[0])]
    else:
        ordered = sorted(sources, key=lambda p:p.name.casefold())
    normalized = work/"normalized-images"
    normalized.mkdir(exist_ok=True)
    visual_paths = [normalize(src, n, normalized) for n, src in enumerate(ordered, 1)]

# Narration and subtitle text come only from script.md. image-prompts.md is never opened.
script = (episode/"script.md").read_text()
blocks = re.findall(r"^## Scene\s+(\d+)\s*\n+([\s\S]*?)(?=^## Scene\s+\d+\s*$|\Z)", script, re.M)
if len(blocks) != scene_count:
    raise SystemExit(f"script.md must contain exactly {scene_count} Scene sections")
narration = []
for i, (num, body) in enumerate(blocks, 1):
    if int(num) != i:
        raise SystemExit("script.md scene order mismatch")
    text = re.sub(r"\s+", " ", body).strip()
    if not text:
        raise SystemExit(f"Empty narration in script scene {i}")
    narration.append(text)

audio = work/"narration.mp3"
async def make_audio():
    communicate = edge_tts.Communicate(" ".join(narration), SETTINGS["voice"], rate=SETTINGS["speech_rate"])
    await communicate.save(str(audio))
asyncio.run(make_audio())

def run(cmd):
    subprocess.run(cmd, check=True)

probe = subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(audio)], text=True)
duration = float(probe.strip())
weights = [max(1, len(t.split())) for t in narration]
total = sum(weights)
durations = [duration*w/total for w in weights]
concat = work/"images.txt"
with concat.open("w") as f:
    for path, seconds in zip(visual_paths, durations):
        f.write(f"file '{path.resolve()}'\nduration {seconds:.4f}\n")
    f.write(f"file '{visual_paths[-1].resolve()}'\n")
silent = work/"visuals.mp4"
run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(concat),"-vf",f"scale={SETTINGS['width']}:{SETTINGS['height']}:force_original_aspect_ratio=increase,crop={SETTINGS['width']}:{SETTINGS['height']}","-r",str(SETTINGS["fps"]),"-pix_fmt","yuv420p","-an",str(silent)])

srt = work/"subtitles.srt"
cursor = 0.0
def stamp(t):
    ms=round(t*1000); h=ms//3600000; ms%=3600000; m=ms//60000; ms%=60000; sec=ms//1000; ms%=1000
    return f"{h:02}:{m:02}:{sec:02},{ms:03}"
with srt.open("w") as f:
    for i, (text, seconds) in enumerate(zip(narration, durations), 1):
        f.write(f"{i}\n{stamp(cursor)} --> {stamp(cursor+seconds)}\n{text}\n\n")
        cursor += seconds
video = out/"final-video.mp4"
run(["ffmpeg","-y","-i",str(silent),"-i",str(audio),"-vf",f"subtitles={srt}:force_style='FontName=Arial,FontSize=22,Outline=2,Shadow=1,MarginV=42'","-c:v","libx264","-preset","veryfast","-crf","21","-c:a","aac","-b:a","192k","-shortest","-movflags","+faststart",str(video)])
print(f"Rendered {video}")
