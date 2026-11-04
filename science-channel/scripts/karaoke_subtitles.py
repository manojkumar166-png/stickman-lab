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


def make_groups(words, max_words=14, max_chars=84, pause_seconds=0.42):
    """Build short caption phrases sized for no more than two display lines."""
    groups, current, char_count = [], [], 0
    for word in words:
        token = clean_word(word["word"])
        added = len(token) + (1 if current else 0)
        pause = bool(current and word["start"] - current[-1]["end"] >= pause_seconds)
        sentence_end = bool(re.search(r"""[.!?]["')\]]*$""", token))
        if current and (pause or len(current) >= max_words or char_count + added > max_chars):
            groups.append(current)
            current, char_count = [], 0
            added = len(token)
        current.append(word)
        char_count += added
        if sentence_end:
            groups.append(current)
            current, char_count = [], 0
    if current:
        groups.append(current)
    return groups


def wrap_phrase(tokens, max_line_chars=42):
    """Return token indexes after which ASS should start a second line."""
    breaks, line_chars = set(), 0
    for index, token in enumerate(tokens):
        token_len = len(token)
        added = token_len + (1 if line_chars else 0)
        if line_chars and line_chars + added > max_line_chars:
            # A group is capped at two lines; if needed, the group builder
            # will have split it before it reaches this point.
            breaks.add(index - 1)
            line_chars = token_len
        else:
            line_chars += added
    return breaks


def transcribe_with_original_whisper(audio_path):
    """Fallback to the original working faster-whisper-small word-timestamp method."""
    from faster_whisper import WhisperModel

    print("WhisperX failed; using original faster-whisper-small fallback.", flush=True)
    model = WhisperModel("small", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(
        str(audio_path), word_timestamps=True, vad_filter=True, beam_size=5
    )
    words = []
    for segment in segments:
        for item in (segment.words or []):
            token = clean_word(item.word)
            if token and item.start is not None and item.end is not None:
                start, end = float(item.start), float(item.end)
                if end > start:
                    words.append({"word": token, "start": start, "end": end})
    if not words:
        raise RuntimeError("Original faster-whisper fallback returned no word timestamps.")
    return normalize_words(words)


def transcribe_with_whisperx(audio_path, device="cpu", model_name="large-v3-turbo"):
    """Run WhisperX transcription and alignment."""
    import whisperx

    model = whisperx.load_model(
        model_name,
        device=device,
        compute_type="int8" if device == "cpu" else "float16",
        language="en",
    )
    result = model.transcribe(str(audio_path), batch_size=8, language="en")
    align_model, metadata = whisperx.load_align_model(
        language_code=result.get("language", "en"), device=device
    )
    aligned = whisperx.align(
        result["segments"], align_model, metadata, str(audio_path), device,
        return_char_alignments=False,
    )
    words = []
    for segment in aligned.get("segments", []):
        words.extend(_segment_words(segment))
    if not words:
        raise RuntimeError("WhisperX returned no transcript words.")
    print(f"WhisperX produced {len(words)} aligned words.", flush=True)
    return normalize_words(words)


def transcribe_and_align(audio_path, device="cpu", model_name="large-v3-turbo"):
    """Use faster-whisper by default; WhisperX can be primary for selected workflows."""
    import os

    backend = os.environ.get("KARAOKE_WHISPER_BACKEND", "faster-whisper").strip().lower()
    if backend not in {"faster-whisper", "whisperx"}:
        raise ValueError(
            "KARAOKE_WHISPER_BACKEND must be 'faster-whisper' or 'whisperx'."
        )

    if backend == "whisperx":
        try:
            return transcribe_with_whisperx(audio_path, device, model_name)
        except Exception as whisperx_error:
            print(
                f"WhisperX primary backend failed: {whisperx_error!r}; "
                "falling back to faster-whisper.",
                flush=True,
            )
            try:
                return transcribe_with_original_whisper(audio_path)
            except Exception as fallback_error:
                raise RuntimeError(
                    "Both WhisperX and faster-whisper failed. "
                    f"WhisperX error: {whisperx_error!r}; "
                    f"faster-whisper error: {fallback_error!r}"
                ) from fallback_error

    try:
        return transcribe_with_original_whisper(audio_path)
    except Exception as faster_error:
        print(
            f"faster-whisper primary backend failed: {faster_error!r}; "
            "falling back to WhisperX.",
            flush=True,
        )
        try:
            return transcribe_with_whisperx(audio_path, device, model_name)
        except Exception as fallback_error:
            raise RuntimeError(
                "Both faster-whisper and WhisperX failed. "
                f"faster-whisper error: {faster_error!r}; "
                f"WhisperX error: {fallback_error!r}"
            ) from fallback_error


def generate_karaoke_ass(audio_path, output_path, width=1920, height=1080):
    words = transcribe_and_align(audio_path)
    anchor_x = width // 2
    # Keep captions close to the bottom edge, matching the faster-whisper layout.
    # This renderer is shared by both faster-whisper and WhisperX backends.
    anchor_y = round(height * 0.94)
    header = f"""[Script Info]
Title: WhisperX Word Karaoke Captions
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Karaoke,DejaVu Sans,{int(height * 0.052)},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,1,2,100,100,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    groups = make_groups(words)
    for group in groups:
        phrase = [item["word"] for item in group]
        line_breaks = wrap_phrase(phrase)
        for index, word in enumerate(group):
            start = word["start"]
            end = group[index + 1]["start"] if index + 1 < len(group) else word["end"]
            end = max(start + 0.03, end)
            rendered = []
            for j, token in enumerate(phrase):
                escaped = token.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")
                color = r"{\c&H0000FFFF&}" if j == index else r"{\c&H00FFFFFF&}"
                rendered.append(color + escaped)
                if j in line_breaks:
                    rendered.append(r"\N")
            position = rf"{{\an2\pos({anchor_x},{anchor_y})}}"
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
