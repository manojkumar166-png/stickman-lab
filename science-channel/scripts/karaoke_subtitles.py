#!/usr/bin/env python3
"""Generate fixed-position, word-highlighted karaoke captions using WhisperX alignment."""
import re
from pathlib import Path

import whisperx


def ass_time(seconds):
    centiseconds = max(0, round(float(seconds) * 100))
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    secs, cs = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


def clean_word(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _segment_words(segment):
    """Keep every transcript token; estimate only words the aligner could not time."""
    raw = segment.get("words") or []
    items = []
    if raw:
        for item in raw:
            token = clean_word(item.get("word"))
            if token:
                items.append({
                    "word": token,
                    "start": item.get("start"),
                    "end": item.get("end"),
                })
    else:
        tokens = re.findall(r"\S+", clean_word(segment.get("text", "")))
        items = [{"word": token, "start": None, "end": None} for token in tokens]

    if not items:
        return []

    seg_start = float(segment.get("start", 0.0))
    seg_end = max(float(segment.get("end", seg_start + 0.1)), seg_start + 0.1)

    # Fill unaligned words between neighbouring aligned anchors using character
    # weights. This preserves words instead of silently dropping low-confidence
    # alignment results.
    anchors = [-1]
    anchors.extend(
        i for i, item in enumerate(items)
        if item["start"] is not None and item["end"] is not None
    )
    anchors.append(len(items))
    for left, right in zip(anchors, anchors[1:]):
        missing = list(range(left + 1, right))
        if not missing:
            continue
        window_start = (
            float(items[left]["end"]) if left >= 0 and items[left]["end"] is not None
            else seg_start
        )
        window_end = (
            float(items[right]["start"]) if right < len(items) and items[right]["start"] is not None
            else seg_end
        )
        window_end = max(window_end, window_start + 0.03)
        weights = [max(1, len(items[i]["word"])) for i in missing]
        total = sum(weights)
        cursor = window_start
        for i, weight in zip(missing, weights):
            next_cursor = cursor + (window_end - window_start) * weight / total
            items[i]["start"], items[i]["end"] = cursor, next_cursor
            cursor = next_cursor

    for item in items:
        item["start"] = max(seg_start, float(item["start"]))
        item["end"] = min(seg_end, float(item["end"]))
        if item["end"] <= item["start"]:
            item["end"] = item["start"] + 0.035
    return items


def normalize_words(words):
    """Sort word cues and enforce a strictly forward, non-overlapping timeline."""
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
                previous["end"] = max(previous["start"] + 0.025, word["start"])
        if word["end"] <= word["start"]:
            word["end"] = word["start"] + 0.035
        result.append(word)
    return result


def make_groups(words, max_words=6, pause_seconds=0.42):
    groups, current = [], []
    for word in words:
        if current and word["start"] - current[-1]["end"] >= pause_seconds:
            groups.append(current)
            current = []
        current.append(word)
        if len(current) >= max_words or re.search(r"""[.!?]["')\]]*$""", word["word"]):
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups


def transcribe_and_align(audio_path, device="cpu", model_name="large-v3-turbo"):
    """Transcribe in English, then force-align every transcript word to the audio."""
    model = whisperx.load_model(
        model_name,
        device=device,
        compute_type="int8" if device == "cpu" else "float16",
        language="en",
    )
    result = model.transcribe(str(audio_path), batch_size=8, language="en")
    align_model, metadata = whisperx.load_align_model(
        language_code=result.get("language", "en"),
        device=device,
    )
    aligned = whisperx.align(
        result["segments"],
        align_model,
        metadata,
        str(audio_path),
        device,
        return_char_alignments=False,
    )
    words = []
    for segment in aligned.get("segments", []):
        words.extend(_segment_words(segment))
    if not words:
        raise RuntimeError("WhisperX returned no transcript words; cannot create karaoke captions.")
    return normalize_words(words)


def generate_karaoke_ass(audio_path, output_path, width=1920, height=1080):
    words = transcribe_and_align(audio_path)
    anchor_x = width // 2
    anchor_y = round(height * 0.88)
    header = f"""[Script Info]
Title: WhisperX Word Karaoke Captions
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
    for group in groups:
        phrase = [item["word"] for item in group]
        for index, word in enumerate(group):
            start = word["start"]
            end = group[index + 1]["start"] if index + 1 < len(group) else word["end"]
            end = max(start + 0.03, end)
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
    """Generate phrase-level SRT subtitles from the same WhisperX-aligned words."""
    words = transcribe_and_align(audio_path)
    entries = []
    for group in make_groups(words, max_words=9):
        start = group[0]["start"]
        end = group[-1]["end"]
        text = " ".join(item["word"] for item in group)
        entries.append(f"{len(entries) + 1}\n{srt_time(start)} --> {srt_time(end)}\n{text}\n")
    Path(output_path).write_text("\n".join(entries), encoding="utf-8")
    return len(words)
