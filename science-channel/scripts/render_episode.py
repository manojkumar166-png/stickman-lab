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
allowed = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}

def scene_number(path):
    # Accept names such as scene1, scene-01, img1, image_01, or 01.
    # Prefer an explicit scene/img/image number; otherwise use the last number in the stem.
    match = re.search(r"(?:scene|img|image)[-_ ]*(\\d{1,3})(?!.*\\d)", path.stem, re.I)
    if match:
        return int(match.group(1))
    numbers = re.findall(r"\\d+", path.stem)
    return int(numbers[-1]) if numbers else None

def normalize(src, number, target_dir):
    target = target_dir/f"scene-{number:03d}.png"
    subprocess.run(["ffmpeg","-y","-i",str(src),"-frames:v","1","-vf","scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720",str(target)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    return target

# Explicit smoke-test fixtures remain isolated from real episode behavior.
if meta.get("smoke_test") is True:
    visual_paths = []
    for n in range(1, scene_count+1):
        target = out/f"smoke-scene-{n:03d}.png"
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
        extract_dir = out/"unzipped-images"
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

    # Honor explicit 1..scene_count numbering when complete and unique.
    # Otherwise use natural filename order (image2 before image10), which supports
    # common ZIP names such as 1.png, 2.png ... 48.png or generated image names.
    numbered = [scene_number(p) for p in sources]
    if all(n is not None for n in numbered) and sorted(numbered) == list(range(1, scene_count+1)):
        ordered = [p for _, p in sorted(zip(numbered, sources), key=lambda item:item[0])]
    else:
        def natural_key(path):
            return [int(part) if part.isdigit() else part.casefold()
                    for part in re.split(r"(\\d+)", path.name)]
        ordered = sorted(sources, key=natural_key)
    normalized = out/"normalized-images"
    normalized.mkdir(exist_ok=True)
    visual_paths = [normalize(src, n, normalized) for n, src in enumerate(ordered, 1)]

# Narration text comes only from script.md. No subtitle track is generated or burned into the video.
script = (episode/"script.md").read_text()
blocks = re.findall(r"^## Scene\\s+(\\d+)\\s*\\n+([\\s\\S]*?)(?=^## Scene\\s+\\d+\\s*$|\\Z)", script, re.M)
if len(blocks) != scene_count:
    raise SystemExit(f"script.md must contain exactly {scene_count} Scene sections")
narration = []
for i, (num, body) in enumerate(blocks, 1):
    if int(num) != i:
        raise SystemExit("script.md scene order mismatch")
    text = re.sub(r"\\s+", " ", body).strip()
    if not text:
        raise SystemExit(f"Empty narration in script scene {i}")
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
weights = [max(1, len(t.split())) for t in narration]
total = sum(weights)
durations = [duration*w/total for w in weights]
concat = out/"images.txt"
with concat.open("w") as f:
    for path, seconds in zip(visual_paths, durations):
        f.write(f"file '{path.resolve()}'\\nduration {seconds:.4f}\\n")
    f.write(f"file '{visual_paths[-1].resolve()}'\\n")
silent = out/"visuals.mp4"
run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(concat),"-vf",f"scale={SETTINGS['width']}:{SETTINGS['height']}:force_original_aspect_ratio=increase,crop={SETTINGS['width']}:{SETTINGS['height']}","-r",str(SETTINGS["fps"]),"-pix_fmt","yuv420p","-an",str(silent)])

video = out/"final-video.mp4"
run(["ffmpeg","-y","-i",str(silent),"-i",str(audio),"-c:v","libx264","-preset","veryfast","-crf","21","-c:a","aac","-b:a","192k","-shortest","-movflags","+faststart",str(video)])
print(f"Rendered {video} (no subtitles)")
