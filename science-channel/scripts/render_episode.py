#!/usr/bin/env python3
"""Render one READY episode from either a ZIP archive or individual scene images."""
import json, re, sys, subprocess, zipfile, time
from pathlib import Path, PurePosixPath
import asyncio
import edge_tts
from karaoke_subtitles import generate_karaoke_ass

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
# Temporary render assets stay separate from the final deliverable.
work = out/"work"
work.mkdir(exist_ok=True)
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
    normalized = work/"normalized-images"
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

audio = work/"narration.mp3"

def split_narration(text, max_chars=2400):
    """Keep TTS requests short enough to avoid oversized/fragile single requests."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    chunks, current = [], ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        # Split unusually long sentences at word boundaries.
        pieces = []
        while len(sentence) > max_chars:
            cut = sentence.rfind(" ", 0, max_chars)
            if cut < 1:
                cut = max_chars
            pieces.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        if sentence:
            pieces.append(sentence)
        for piece in pieces:
            candidate = f"{current} {piece}".strip()
            if current and len(candidate) > max_chars:
                chunks.append(current)
                current = piece
            else:
                current = candidate
    if current:
        chunks.append(current)
    return chunks

async def make_audio():
    chunks = split_narration(" ".join(narration))
    chunk_dir = work/"audio-chunks"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    audio_parts = []
    print(f"Generating narration in {len(chunks)} short TTS chunks.")
    for index, chunk in enumerate(chunks, 1):
        part = chunk_dir/f"narration-{index:03d}.mp3"
        last_error = None
        for attempt in range(1, 6):
            part.unlink(missing_ok=True)
            try:
                communicate = edge_tts.Communicate(
                    chunk, SETTINGS["voice"], rate=SETTINGS["speech_rate"]
                )
                await asyncio.wait_for(communicate.save(str(part)), timeout=180)
                if not part.is_file() or part.stat().st_size < 1024:
                    raise RuntimeError("TTS returned an empty or incomplete audio file")
                probe_part = subprocess.run(
                    ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                     "-of", "default=noprint_wrappers=1:nokey=1", str(part)],
                    capture_output=True, text=True, timeout=30
                )
                if probe_part.returncode != 0 or not probe_part.stdout.strip():
                    raise RuntimeError("TTS output is not a readable audio stream")
                last_error = None
                print(f"TTS chunk {index}/{len(chunks)} completed.")
                break
            except Exception as exc:
                last_error = exc
                part.unlink(missing_ok=True)
                if attempt < 5:
                    delay = min(30, 2 ** attempt)
                    print(
                        f"TTS chunk {index}/{len(chunks)} failed "
                        f"(attempt {attempt}/5): {exc}. Retrying in {delay}s."
                    )
                    await asyncio.sleep(delay)
        if last_error is not None:
            raise RuntimeError(
                f"TTS failed for narration chunk {index}/{len(chunks)} "
                f"after 5 attempts. Check Edge TTS availability, voice "
                f"'{SETTINGS['voice']}', and network/rate limits. Last error: {last_error}"
            ) from last_error
        audio_parts.append(part)

    concat_list = work/"audio-chunks.txt"
    with concat_list.open("w", encoding="utf-8") as handle:
        for part in audio_parts:
            escaped = part.resolve().as_posix().replace("'", "'\\''")
            handle.write(f"file '{escaped}'\n")
    # Re-encode the joined chunks instead of stream-copying them. Edge TTS can
    # return individually valid MP3 chunks with slightly different stream headers
    # or timestamps; stream-copy concatenation is brittle in that situation.
    combine_cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", str(concat_list),
        "-vn", "-c:a", "libmp3lame", "-q:a", "2", "-ar", "24000",
        "-ac", "1", "-write_xing", "0", str(audio)
    ]
    try:
        subprocess.run(
            combine_cmd, check=True, stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE, text=True, timeout=300
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip()
        print(f"FFmpeg narration assembly failed:\n{detail}")
        raise RuntimeError(
            f"Could not combine {len(audio_parts)} valid Edge TTS chunks. "
            f"FFmpeg reported: {detail or 'no diagnostic output'}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("FFmpeg narration assembly exceeded 300 seconds.") from exc

    if not audio.is_file() or audio.stat().st_size < 1024:
        raise RuntimeError("Combining narration chunks produced an empty audio file")
    final_probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(audio)],
        capture_output=True, text=True, timeout=30
    )
    if final_probe.returncode != 0 or not final_probe.stdout.strip():
        raise RuntimeError("Combined narration MP3 failed audio-stream validation")
    print(
        f"Combined {len(audio_parts)} TTS chunks into "
        f"{float(final_probe.stdout.strip()):.1f}s of narration."
    )

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

captions = work/"karaoke-captions.ass"
word_count = generate_karaoke_ass(audio, captions, SETTINGS["width"], SETTINGS["height"])
video = out/"final-video.mp4"
run(["ffmpeg","-y","-i",str(silent),"-i",str(audio),"-vf",f"subtitles={captions}:fontsdir=/usr/share/fonts/truetype/dejavu","-c:v","libx264","-preset","veryfast","-crf","21","-c:a","aac","-b:a","192k","-shortest","-movflags","+faststart",str(video)])
print(f"Rendered {video} with karaoke captions ({word_count} timed words)")
