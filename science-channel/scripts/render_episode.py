#!/usr/bin/env python3
"""Render one READY episode from either a ZIP archive or individual scene images."""
import json, re, sys, subprocess, zipfile
from pathlib import Path, PurePosixPath
import asyncio
import edge_tts
from karaoke_subtitles import generate_karaoke_ass
from cinematic_effects import analyze_scenes, render_scene_clip, create_sound_effect_track
from bgm_engine import create_background_music

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
    match = re.search(r"(?:scene|img|image)[-_ ]*(\d{1,3})(?!.*\d)", path.stem, re.I)
    if match:
        return int(match.group(1))
    numbers = re.findall(r"\d+", path.stem)
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
                    for part in re.split(r"(\d+)", path.name)]
        ordered = sorted(sources, key=natural_key)
    normalized = out/"normalized-images"
    normalized.mkdir(exist_ok=True)
    visual_paths = [normalize(src, n, normalized) for n, src in enumerate(ordered, 1)]

# Narration text comes only from script.md; Whisper aligns word timestamps to the generated narration.
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
        f.write(f"file '{path.resolve()}'\nduration {seconds:.4f}\n")
    f.write(f"file '{visual_paths[-1].resolve()}'\n")
silent = out/"visuals.mp4"
captions = out/"karaoke-captions.ass"
word_count = generate_karaoke_ass(audio, captions, SETTINGS["width"], SETTINGS["height"])
video = out/"final-video.mp4"
effects_settings = SETTINGS.get("cinematic_effects", {})
cinematic_enabled = bool(effects_settings.get("enabled", False))
cinematic_used = False
soundtrack = out/"cinematic-sfx.wav"

def render_original_visuals():
    run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(concat),"-vf",f"scale={SETTINGS['width']}:{SETTINGS['height']}:force_original_aspect_ratio=increase,crop={SETTINGS['width']}:{SETTINGS['height']}","-r",str(SETTINGS["fps"]),"-pix_fmt","yuv420p","-an",str(silent)])

if cinematic_enabled:
    try:
        title = str(meta.get("title", ""))
        plan = analyze_scenes(title, narration, int(effects_settings.get("max_major_impacts", 6)))
        clip_dir = out/"cinematic-scenes"
        clip_dir.mkdir(exist_ok=True)
        clip_list = out/"cinematic-scenes.txt"
        with clip_list.open("w", encoding="utf-8") as listing:
            for index, (image_path, seconds, scene_plan) in enumerate(zip(visual_paths, durations, plan["scenes"]), 1):
                clip = clip_dir/f"scene-{index:03d}.mp4"
                render_scene_clip(image_path, clip, seconds, SETTINGS["width"], SETTINGS["height"], SETTINGS["fps"], plan["profile"], scene_plan)
                listing.write(f"file '{clip.resolve()}'\n")
        run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(clip_list),"-an","-c:v","libx264","-preset","veryfast","-crf","21","-pix_fmt","yuv420p",str(silent)])
        cinematic_used = True
        print(f"Adaptive cinematic profile: {plan['topic']}")
        if effects_settings.get("sound_effects", False):
            create_sound_effect_track(soundtrack, duration, durations, plan["scenes"])
    except Exception as exc:
        print(f"WARNING: Cinematic rendering failed; using original renderer: {exc}")
        cinematic_used = False
        soundtrack.unlink(missing_ok=True)
        render_original_visuals()
else:
    render_original_visuals()

bgm_path = out/"background-music.wav"
bgm_settings = SETTINGS.get("bgm", {})
try:
    create_background_music(bgm_path, str(meta.get("title", "")), narration, durations, bgm_settings)
except Exception as exc:
    print(f"WARNING: BGM generation failed; continuing without music: {exc}")
    bgm_path.unlink(missing_ok=True)

def mux_final_audio():
    cmd = ["ffmpeg", "-y", "-i", str(silent), "-i", str(audio)]
    has_sfx = cinematic_used and soundtrack.exists()
    has_bgm = bgm_path.exists()
    sfx_index = None
    bgm_index = None
    if has_sfx:
        sfx_index = 2
        cmd += ["-i", str(soundtrack)]
    if has_bgm:
        bgm_index = 3 if has_sfx else 2
        cmd += ["-i", str(bgm_path)]

    filters = []
    if has_bgm:
        filters.append(f"[{bgm_index}:a]volume=0.18[bgmquiet]")
        filters.append(f"[bgmquiet][1:a]sidechaincompress=threshold=0.025:ratio=8:attack=25:release=600[ducked]")
    if has_sfx:
        filters.append(f"[{sfx_index}:a]volume=0.22[sfxquiet]")
        filters.append("[1:a][sfxquiet]amix=inputs=2:weights='1 1':normalize=0[voice_sfx]")
        if has_bgm:
            filters.append("[voice_sfx][ducked]amix=inputs=2:weights='1 1':normalize=0[aout]")
        else:
            filters.append("[voice_sfx]anull[aout]")
    elif has_bgm:
        filters.append("[1:a][ducked]amix=inputs=2:weights='1 1':normalize=0[aout]")

    cmd += ["-vf", f"subtitles={captions}:fontsdir=/usr/share/fonts/truetype/dejavu"]
    if filters:
        cmd += ["-filter_complex", ";".join(filters), "-map", "0:v:0", "-map", "[aout]"]
    else:
        cmd += ["-map", "0:v:0", "-map", "1:a:0"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
            "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(video)]
    run(cmd)

try:
    mux_final_audio()
except Exception as exc:
    print(f"WARNING: Final audio mix failed; retrying with original narration only: {exc}")
    bgm_path.unlink(missing_ok=True)
    soundtrack.unlink(missing_ok=True)
    if cinematic_used:
        cinematic_used = False
        render_original_visuals()
    run(["ffmpeg","-y","-i",str(silent),"-i",str(audio),"-vf",f"subtitles={captions}:fontsdir=/usr/share/fonts/truetype/dejavu","-map","0:v:0","-map","1:a:0","-c:v","libx264","-preset","veryfast","-crf","21","-c:a","aac","-b:a","192k","-shortest","-movflags","+faststart",str(video)])

mode = "adaptive cinematic" if cinematic_used else "original fallback"
music_mode = "with adaptive BGM" if bgm_path.exists() else "without BGM (safe fallback)"
print(f"Rendered {video} in {mode} mode {music_mode} with karaoke captions ({word_count} timed words)")
