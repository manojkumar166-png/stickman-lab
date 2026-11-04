#!/usr/bin/env python3
"""Validate a staged Telegram ZIP and extract its 48 scene images."""
import os
import re
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

EPISODE_PATH = os.environ["EPISODE_PATH"].strip()
ZIP_PATH = os.environ["ZIP_PATH"].strip()
ROOT = Path("science-channel/daily-episodes")
STAGING_ROOT = Path("science-channel/telegram-uploads")
ALLOWED = {".png", ".jpg", ".jpeg", ".webp"}
MAX_ZIP_BYTES = 25 * 1024 * 1024
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_TOTAL_IMAGE_BYTES = 250 * 1024 * 1024


def fail(message):
    print(message, file=sys.stderr)
    raise SystemExit(1)


def natural_key(value):
    return [int(part) if part.isdigit() else part.casefold()
            for part in re.split(r"(\d+)", value)]


def order_image_entries(entries):
    """Sort by numeric chunks in each filename; ZIP archive order is never used."""
    return list(enumerate(
        sorted(entries, key=lambda item: (
            natural_key(Path(item.filename).name),
            Path(item.filename).name.casefold(),
            item.filename.casefold(),
        )),
        start=1,
    ))


def main():
    match = re.fullmatch(
        r"science-channel/daily-episodes/(\d{4}-\d{2}-\d{2})/([A-Za-z0-9][A-Za-z0-9._-]*)",
        EPISODE_PATH,
    )
    if not match or ".." in Path(EPISODE_PATH).parts:
        fail("Invalid episode_path. Expected a folder under science-channel/daily-episodes/Month YYYY/YYYY-MM-DD/.")

    # The filename is irrelevant: accept any .zip filename staged directly
    # in the Telegram upload directory. zipfile below verifies the actual format.
    zip_path = PurePosixPath(ZIP_PATH)
    if (
        zip_path.is_absolute()
        or len(zip_path.parts) != 3
        or zip_path.parts[:2] != ("science-channel", "telegram-uploads")
        or ".." in zip_path.parts
        or zip_path.suffix.lower() != ".zip"
    ):
        fail(
            "Invalid staged ZIP path. Provide the path to any .zip file directly "
            "inside science-channel/telegram-uploads/; the filename does not matter."
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

    installed = []
    try:
        with zipfile.ZipFile(archive_path) as archive:
            image_entries = []
            total_uncompressed = 0
            for info in archive.infolist():
                if info.is_dir():
                    continue
                member = PurePosixPath(info.filename)
                mode = (info.external_attr >> 16) & 0o170000
                if member.is_absolute() or ".." in member.parts or "\\" in info.filename or mode == 0o120000:
                    fail("ZIP contains an unsafe path or symbolic link.")
                if Path(member.name).suffix.lower() in ALLOWED:
                    if info.file_size <= 0 or info.file_size > MAX_IMAGE_BYTES:
                        fail(f"Image has an invalid or excessive size: {member.name}")
                    total_uncompressed += info.file_size
                    if total_uncompressed > MAX_TOTAL_IMAGE_BYTES:
                        fail("ZIP expands beyond the 250 MiB total image limit.")
                    image_entries.append(info)
            if len(image_entries) != 48:
                fail(f"ZIP must contain exactly 48 supported images; found {len(image_entries)}.")
            names = [Path(item.filename).name.casefold() for item in image_entries]
            if len(set(names)) != 48:
                fail("ZIP contains duplicate image filenames.")

            # Extract into a temporary directory first. A corrupt member or CRC
            # failure must never leave a half-imported episode in images/incoming.
            with tempfile.TemporaryDirectory(prefix=".zip-import-", dir=incoming) as temp_name:
                temp_dir = Path(temp_name)
                staged = []
                for index, info in order_image_entries(image_entries):
                    suffix = Path(info.filename).suffix.lower()
                    target = temp_dir / f"scene-{index:02d}{suffix}"
                    written = 0
                    with archive.open(info) as source, target.open("wb") as destination:
                        while True:
                            chunk = source.read(1024 * 1024)
                            if not chunk:
                                break
                            written += len(chunk)
                            if written > MAX_IMAGE_BYTES or written > info.file_size:
                                fail(f"Image expanded beyond its declared size or 20 MB: {info.filename}")
                            destination.write(chunk)
                    if written != info.file_size:
                        fail(f"Image size mismatch while extracting: {info.filename}")
                    staged.append((target, incoming / target.name))
                for source, destination in staged:
                    source.replace(destination)
                    installed.append(destination)
    except zipfile.BadZipFile:
        for installed_path in installed:
            installed_path.unlink(missing_ok=True)
        fail("The uploaded document is not a valid ZIP archive.")
    except (RuntimeError, OSError, EOFError) as exc:
        for installed_path in installed:
            installed_path.unlink(missing_ok=True)
        fail(f"Could not safely extract the ZIP archive: {exc}")

    (episode / "READY.txt").write_text(
        "All 48 scene images imported from Telegram.\n", encoding="utf-8"
    )
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as handle:
        handle.write(f"episode_path={EPISODE_PATH}\n")
        handle.write(f"zip_path={ZIP_PATH}\n")
    print(f"Imported 48 images into {incoming}")


if __name__ == "__main__":
    main()
