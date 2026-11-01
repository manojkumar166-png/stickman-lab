#!/usr/bin/env python3
"""Validate a staged Telegram ZIP and extract its 48 scene images."""
import os
import re
import sys
import zipfile
from pathlib import Path, PurePosixPath

EPISODE_PATH = os.environ["EPISODE_PATH"].strip()
ZIP_PATH = os.environ["ZIP_PATH"].strip()
ROOT = Path("science-channel/daily-episodes")
STAGING_ROOT = Path("science-channel/telegram-uploads")
ALLOWED = {".png", ".jpg", ".jpeg", ".webp"}
MAX_ZIP_BYTES = 25 * 1024 * 1024
MAX_IMAGE_BYTES = 20 * 1024 * 1024


def fail(message):
    print(message, file=sys.stderr)
    raise SystemExit(1)


def natural_key(value):
    return [int(part) if part.isdigit() else part.casefold()
            for part in re.split(r"(\d+)", value)]


def main():
    match = re.fullmatch(
        r"science-channel/daily-episodes/(\d{4}-\d{2}-\d{2})/([A-Za-z0-9][A-Za-z0-9._-]*)",
        EPISODE_PATH,
    )
    if not match or ".." in Path(EPISODE_PATH).parts:
        fail("Invalid episode_path. Expected a folder under science-channel/daily-episodes/YYYY-MM-DD/.")

    # Accept safe ZIP filenames in the dedicated staging directory. Do not
    # require a specific UUID length/case: staging implementations may use
    # different unique filename formats.
    zip_path = PurePosixPath(ZIP_PATH)
    if (
        zip_path.is_absolute()
        or len(zip_path.parts) != 3
        or zip_path.parts[:2] != ("science-channel", "telegram-uploads")
        or ".." in zip_path.parts
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*\\.zip", zip_path.name, re.IGNORECASE)
    ):
        fail(
            "Invalid staged ZIP path. ZIP_PATH must be a ZIP file directly inside "
            "science-channel/telegram-uploads/, for example "
            "science-channel/telegram-uploads/upload-123.zip."
        )

    episode = Path(EPISODE_PATH)
    archive_path = Path(ZIP_PATH)
    if not (episode / "episode.json").is_file():
        fail(f"Episode metadata not found: {EPISODE_PATH}/episode.json")
    if not archive_path.is_file():
        fail("Staged Telegram ZIP was not found in the repository checkout.")
    if archive_path.stat().st_size <= 0 or archive_path.stat().st_size > MAX_ZIP_BYTES:
        fail("ZIP must be larger than 0 and no larger than 25 MB.")

    incoming = episode / "images" / "incoming"
    incoming.mkdir(parents=True, exist_ok=True)
    existing = [p for p in incoming.iterdir()
                if p.is_file() and p.suffix.lower() in ALLOWED]
    if existing:
        fail("This episode already contains incoming images. Refusing to overwrite them.")

    try:
        with zipfile.ZipFile(archive_path) as archive:
            image_entries = []
            for info in archive.infolist():
                if info.is_dir():
                    continue
                member = PurePosixPath(info.filename)
                mode = (info.external_attr >> 16) & 0o170000
                if member.is_absolute() or ".." in member.parts or mode == 0o120000:
                    fail("ZIP contains an unsafe path or symbolic link.")
                if Path(member.name).suffix.lower() in ALLOWED:
                    if info.file_size > MAX_IMAGE_BYTES:
                        fail(f"Image exceeds 20 MB: {member.name}")
                    image_entries.append(info)
            image_entries.sort(key=lambda item: natural_key(item.filename))
            if len(image_entries) != 48:
                fail(f"ZIP must contain exactly 48 supported images; found {len(image_entries)}.")
            names = [Path(item.filename).name.casefold() for item in image_entries]
            if len(set(names)) != 48:
                fail("ZIP contains duplicate image filenames.")
            for index, info in enumerate(image_entries, start=1):
                suffix = Path(info.filename).suffix.lower()
                target = incoming / f"scene-{index:02d}{suffix}"
                target.write_bytes(archive.read(info))
    except zipfile.BadZipFile:
        fail("The uploaded document is not a valid ZIP archive.")

    (episode / "READY.txt").write_text(
        "All 48 scene images imported from Telegram.\n", encoding="utf-8"
    )
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as handle:
        handle.write(f"episode_path={EPISODE_PATH}\n")
        handle.write(f"zip_path={ZIP_PATH}\n")
    print(f"Imported 48 images into {incoming}")


if __name__ == "__main__":
    main()
