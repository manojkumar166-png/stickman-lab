#!/usr/bin/env python3
"""Select and assemble only pre-approved YouTube Audio Library music tracks.

This module deliberately does not download or scrape music. A human must download
tracks from YouTube Studio's Audio Library and add verified metadata to library.json.
"""
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MUSIC_ROOT = ROOT / "assets" / "music"
MANIFEST = MUSIC_ROOT / "library.json"

TOPIC_KEYWORDS = {
    "space": ("space", "cosmos", "planet", "star", "galaxy", "black hole", "universe", "astronomy"),
    "biology": ("biology", "cell", "dna", "gene", "animal", "plant", "evolution", "body", "brain", "microbe"),
    "chemistry": ("chemistry", "molecule", "atom", "reaction", "element", "chemical", "compound"),
    "technology": ("technology", "robot", "computer", "artificial intelligence", "ai ", "chip", "quantum", "engineering"),
    "earth": ("earth", "ocean", "climate", "weather", "volcano", "earthquake", "forest", "ecosystem", "nature"),
}
MOOD_KEYWORDS = {
    "wonder": ("wonder", "mystery", "unknown", "cosmic", "strange", "universe", "ancient"),
    "tension": ("danger", "risk", "collision", "threat", "crisis", "extreme", "unstable"),
    "discovery": ("discover", "reveal", "breakthrough", "evidence", "experiment", "research", "solve"),
    "calm": ("calm", "gentle", "quiet", "balance", "peaceful", "slow", "subtle"),
    "triumph": ("finally", "success", "solution", "achievement", "future", "possibility", "incredible"),
}


def _topic(text):
    lowered = text.casefold()
    scores = {topic: sum(lowered.count(word) for word in words) for topic, words in TOPIC_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] else "general"


def _mood(text):
    lowered = text.casefold()
    scores = {mood: sum(lowered.count(word) for word in words) for mood, words in MOOD_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] else "inspiring"


def _load_approved_tracks():
    if not MANIFEST.is_file():
        return []
    try:
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"BGM disabled: music manifest could not be read: {exc}")
        return []
    approved = []
    for item in data.get("tracks", []):
        # Fail closed: require an explicit human verification record and Audio Library source.
        if item.get("verified") is not True:
            continue
        if item.get("source") != "YouTube Audio Library":
            continue
        if item.get("attribution_required") is not False:
            continue
        if not item.get("title") or not item.get("artist") or not item.get("license_name"):
            continue
        rel = Path(str(item.get("file", "")))
        if rel.is_absolute() or ".." in rel.parts:
            continue
        path = (MUSIC_ROOT / rel).resolve()
        if not path.is_relative_to(MUSIC_ROOT.resolve()) or not path.is_file():
            continue
        approved.append({**item, "_path": path})
    return approved


def _choose_track(tracks, topic, mood, seed):
    candidates = []
    for track in tracks:
        topics = [str(x).casefold() for x in track.get("topics", [])]
        moods = [str(x).casefold() for x in track.get("moods", [])]
        score = (4 if topic in topics else 2 if "general" in topics else 0)
        score += 3 if mood in moods else 1 if "inspiring" in moods else 0
        if score:
            candidates.append((score, track))
    if not candidates:
        return None
    top_score = max(score for score, _ in candidates)
    pool = [track for score, track in candidates if score == top_score]
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return pool[int.from_bytes(digest[:4], "big") % len(pool)]


def create_background_music(output_path, title, narration_scenes, scene_durations, settings):
    """Create a scene-aware music bed, or return None if no approved tracks exist."""
    if not settings.get("enabled", False):
        print("BGM is disabled in settings.")
        return None
    tracks = _load_approved_tracks()
    if not tracks:
        print("No approved YouTube Audio Library tracks found; rendering without BGM.")
        return None

    selected = []
    for index, (scene_text, duration) in enumerate(zip(narration_scenes, scene_durations), 1):
        topic = _topic(title + " " + scene_text)
        mood = _mood(scene_text)
        track = _choose_track(tracks, topic, mood, f"{title}:{index}:{topic}:{mood}")
        if track is None:
            print(f"No approved BGM match for scene {index}; rendering without BGM.")
            return None
        selected.append((track, max(0.25, float(duration))))

    # Merge adjacent scenes using the same track; only change music when the mood/topic choice changes.
    segments = []
    for track, duration in selected:
        if segments and segments[-1][0]["_path"] == track["_path"]:
            segments[-1] = (track, segments[-1][1] + duration)
        else:
            segments.append((track, duration))

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fade = min(max(0.5, float(settings.get("crossfade_seconds", 2.5))), 4.0)
    total_duration = sum(duration for _, duration in segments)
    cmd = ["ffmpeg", "-y"]
    for track, _ in segments:
        cmd += ["-stream_loop", "-1", "-i", str(track["_path"])]

    filters = []
    for index, (_, duration) in enumerate(segments):
        # Add the overlap duration to each later segment; acrossfade removes it again.
        input_duration = duration + (fade if index else 0.0)
        filters.append(
            f"[{index}:a]atrim=duration={input_duration:.4f},asetpts=PTS-STARTPTS[s{index}]"
        )
    current = "s0"
    for index in range(1, len(segments)):
        next_label = f"x{index}"
        filters.append(f"[{current}][s{index}]acrossfade=d={fade:.3f}:c1=tri:c2=tri[{next_label}]")
        current = next_label
    fade_out = min(4.0, max(0.5, total_duration))
    filters.append(
        f"[{current}]atrim=duration={total_duration:.4f},"
        f"afade=t=out:st={max(0.0, total_duration-fade_out):.4f}:d={fade_out:.4f},"
        f"aresample=48000, aformat=sample_fmts=s16:channel_layouts=stereo[out]"
    )
    cmd += ["-filter_complex", ";".join(filters), "-map", "[out]", "-c:a", "pcm_s16le", str(output_path)]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)

    credits = []
    seen = set()
    for track, _ in segments:
        key = (track.get("title"), track.get("artist"))
        if key not in seen:
            seen.add(key)
            credits.append(f"{track['title']} — {track['artist']} (YouTube Audio Library; {track['license_name']})")
    (output_path.parent / "bgm-track-record.txt").write_text(
        "Approved BGM used in this episode:\n" + "\n".join(credits) + "\n",
        encoding="utf-8",
    )
    print("Adaptive BGM tracks: " + "; ".join(f"{t['title']} — {t['artist']}" for t, _ in segments))
    return output_path
