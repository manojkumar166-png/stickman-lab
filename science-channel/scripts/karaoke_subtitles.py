#!/usr/bin/env python3
"""Create phrase-based ASS captions with the currently spoken word highlighted."""
import re
from faster_whisper import WhisperModel

def ass_time(seconds):
    centiseconds = max(0, round(float(seconds) * 100))
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    secs, cs = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"

def clean_word(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()

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

    header = f"""[Script Info]
Title: Science Channel Karaoke Captions
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Karaoke,DejaVu Sans,{int(height * 0.052)},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,1,2,100,100,95,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for group in make_groups(words):
        phrase_end = max(group[-1]["end"], group[0]["start"] + 0.12) + 0.18
        phrase = [w["word"] for w in group]
        for index, word in enumerate(group):
            start = word["start"]
            end = group[index + 1]["start"] if index + 1 < len(group) else phrase_end
            end = max(end, start + 0.08)
            rendered = []
            for j, token in enumerate(phrase):
                escaped = token.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")
                color = r"{\c&H0000FFFF&}" if j == index else r"{\c&H00FFFFFF&}"
                rendered.append(color + escaped)
            events.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Karaoke,,0,0,0,,{' '.join(rendered)}{{\\c&H00FFFFFF&}}")
    with open(output_path, "w", encoding="utf-8") as target:
        target.write(header + "\n".join(events) + "\n")
    return len(words)
