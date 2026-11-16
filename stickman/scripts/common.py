#!/usr/bin/env python3
"""Shared helpers for script runner."""
import os
from pathlib import Path


def ffmpeg():
    return os.environ.get("FFMPEG", "ffmpeg")


def is_3d(folder):
    return (Path(folder) / "engine3d").exists() or "3d" in str(folder).lower()


def page_url(folder):
    p = (Path(folder) / ("engine3d" if is_3d(folder) else "engine") / "index.html").resolve()
    return f"file://{p}"


def browser_args(is3d=False):
    args = ["--no-sandbox", "--disable-gpu", "--hide-scrollbars"]
    if not is3d:
        args.append("--disable-software-rasterizer")
    return args


FRAME_JS = """t => {
    renderAt(t);
    const c = document.getElementById('c') || document.getElementById('c2d');
    return [JSON.stringify(REPORT), c.toDataURL('image/jpeg', .9)];
}"""
