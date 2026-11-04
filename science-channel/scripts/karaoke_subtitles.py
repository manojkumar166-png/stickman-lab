#!/usr/bin/env python3
"""Create phrase-based ASS captions with stable-position karaoke highlighting."""
import re
from pathlib import Path
from faster_whisper import WhisperModel


def ass_time(seconds):
    centiseconds = max(0, round(float(seconds) * 100))
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    secs, cs = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


def clean_word(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_words(words):
    """Sort Whisper output and eliminate duplicate/overlapping VAD-boundary words."""
    ordered = sorted(words, key=lambda item: (item["start"], item["end"]))
    result = []
    for item in ordered:
        word = dict(item)
        if result:
            previous = result[-1]
            if (word["word"].casefold() == previous["word"].casefold()
                    and word["start"] <= previous["end"] + 0.35):
                previous["end"] = max(previous["end"], word["end"])
                continue
            if word["start"] < previous["end"]:
                previous["end"] = max(previous["start"] + 0.03, word["start"])
        if word["end"] <= word["start"]:
            word["end"] = word["start"] + 0.03
        result.append(word)
    return result


def make_groups(words, max_words=7):
    groups, current = [], []
    for word in words:
        current.append(word)
        if len(current) >= max_words or re.search(r"""[.!?]["')\]]*$""", clean_word(word["word"])):
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups


def generate_karaoke_ass(audio_path, output_path, width=1920, height=1080):
    model = WhisperModel("small", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(str(audio_path), word_timestamps=True, vad_filter=True, beam_size=5)
    words = []
    for segment in segments:
        for item in (segment.words or []):
            token = clean_word(item.word)
            if token and item.start is not None and item.end is not None:
                words.append({"word": token, "start": float(item.start), "end": float(item.end)})
    if not words:
        raise RuntimeError("Whisper returned no word timestamps; cannot create synchronized captions.")
    words = normalize_words(words)

    # Center-anchor every cue at the exact same canvas coordinate. Bottom-aligned
    # captions move their top edge whenever a phrase wraps to another line.
    # Center alignment keeps the caption block's centre steady across cue changes.
    anchor_x = width // 2
    anchor_y = round(height * 0.88)
    header = f"""[Script Info]
Title: Science Channel Karaoke Captions
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Karaoke,DejaVu Sans,{int(height * 0.052)},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,1,5,100,100,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    groups = make_groups(words)
    for group_index, group in enumerate(groups):
        # No trailing hold: it made the outgoing phrase overlap the next phrase.
        phrase_end = max(group[-1]["end"], group[0]["start"] + 0.12)
        phrase = [w["word"] for w in group]
        for index, word in enumerate(group):
            start = word["start"]
            end = group[index + 1]["start"] if index + 1 < len(group) else phrase_end
            end = max(end, start + 0.03)
            if index == len(group) - 1 and group_index + 1 < len(groups):
                end = min(end, groups[group_index + 1][0]["start"])
            rendered = []
            for j, token in enumerate(phrase):
                escaped = token.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")
                color = r"{\c&H0000FFFF&}" if j == index else r"{\c&H00FFFFFF&}"
                rendered.append(color + escaped)
            position = rf"{{\an5\pos({anchor_x},{anchor_y})}}"
            events.append(
                f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Karaoke,,0,0,0,,"
                f"{position}{' '.join(rendered)}{{\c&H00FFFFFF&}}"
            )
    Path(output_path).write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return len(words)


def srt_time(seconds):
    milliseconds = max(0, round(float(seconds) * 1000))
    hours, remainder = divmod(milliseconds, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    secs, ms = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def generate_karaoke_srt(audio_path, output_path):
    """Generate a portable SRT file with phrase-level synchronized subtitles."""
    model = WhisperModel("small", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(
        str(audio_path), word_timestamps=True, vad_filter=True, beam_size=5
    )
    words = []
    for segment in segments:
        for item in (segment.words or []):
            token = clean_word(item.word)
            if token and item.start is not None and item.end is not None:
                words.append({
                    "word": token,
                    "start": float(item.start),
                    "end": float(item.end),
                })
    if not words:
        raise RuntimeError("Whisper returned no word timestamps; cannot create synchronized subtitles.")
    words = normalize_words(words)

    entries = []
    for group in make_groups(words, max_words=9):
        start = group[0]["start"]
        end = max(group[-1]["end"], start + 0.12)
        text = " ".join(item["word"] for item in group)
        entries.append(f"{len(entries) + 1}\n{srt_time(start)} --> {srt_time(end)}\n{text}\n")
    Path(output_path).write_text("\n".join(entries), encoding="utf-8")
    return len(words)
