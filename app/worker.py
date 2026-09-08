import hashlib
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import cv2

from app.db import (
    fetch_pending_frames,
    fetch_tables,
    load_media_and_frames,
    mark_frame_failed,
    media_input_exists,
    save_frame_observations,
)
from app.media import media_type
from app.vision import build_table_observations


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

FRAME_INTERVAL_SECONDS = 30


def get_file_hash(path: Path) -> str:
    sha256 = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(8192):
            sha256.update(chunk)
    return sha256.hexdigest()


def get_frame_interval_seconds() -> int:
    interval = int(os.getenv("FRAME_INTERVAL_SECONDS", str(FRAME_INTERVAL_SECONDS)))
    if interval <= 0:
        raise ValueError("FRAME_INTERVAL_SECONDS must be positive")
    return interval


def process_image(path: Path, media_hash: str, processed_dir: str) -> list[dict]:
    image = cv2.imread(str(path))
    if image is None:
        raise ValueError("Failed to read image")

    out_dir = Path(processed_dir) / media_hash
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "0.jpg"
    if not cv2.imwrite(str(out_path), image):
        raise ValueError("Failed to write normalized image")

    return [{
        "frame_index": 0,
        "offset_ms": 0,
        "image_path": str(out_path),
        "captured_at": datetime.now(timezone.utc),
    }]


def process_video(path: Path, media_hash: str, processed_dir: str) -> list[dict]:
    interval_ms = get_frame_interval_seconds() * 1000
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise ValueError("Failed to open video")

    out_dir = Path(processed_dir) / media_hash
    out_dir.mkdir(parents=True, exist_ok=True)
    artifacts = []
    captured_at = datetime.now(timezone.utc)

    try:
        while True:
            offset_ms = len(artifacts) * interval_ms
            capture.set(cv2.CAP_PROP_POS_MSEC, offset_ms)
            success, frame = capture.read()
            if not success:
                break

            out_path = out_dir / f"{len(artifacts)}.jpg"
            if not cv2.imwrite(str(out_path), frame):
                raise ValueError("Failed to write normalized video frame")
            artifacts.append({
                "frame_index": len(artifacts),
                "offset_ms": offset_ms,
                "image_path": str(out_path),
                "captured_at": captured_at,
            })
    finally:
        capture.release()

    if not artifacts:
        raise ValueError("No frames could be extracted from the video")
    return artifacts


def transform_media(kind: str, path: Path, media_hash: str, processed_dir: str) -> list[dict]:
    if kind == "image":
        return process_image(path, media_hash, processed_dir)
    return process_video(path, media_hash, processed_dir)


def ingest_path(path: Path, processed_dir: str) -> bool:
    try:
        kind = media_type(str(path))
    except ValueError as error:
        logger.warning("ignored unsupported file %s: %s", path.name, error)
        return False

    try:
        media_hash = get_file_hash(path)
    except OSError as error:
        logger.error("failed to read %s for hashing: %s", path.name, error)
        return False

    try:
        already_loaded = media_input_exists(media_hash)
    except Exception as error:
        logger.error("failed to check duplicate %s: %s", path.name, error)
        return False

    if already_loaded:
        logger.info("ignored duplicate file: %s", path.name)
        return False

    try:
        artifacts = transform_media(kind, path, media_hash, processed_dir)
    except Exception as error:
        logger.error("failed to transform %s: %s", path.name, error)
        try:
            load_media_and_frames(
                kind,
                str(path),
                media_hash,
                [],
                status="failed",
                error_message=str(error),
            )
        except Exception:
            logger.exception("failed to record failed input %s", path.name)
        return False

    try:
        media_input_id = load_media_and_frames(kind, str(path), media_hash, artifacts)
    except Exception:
        logger.exception("failed to load transformed input %s", path.name)
        return False
    if media_input_id is None:
        logger.info("ignored duplicate file during load: %s", path.name)
        return False
    logger.info("loaded %s input with %s frame(s): %s", kind, len(artifacts), path.name)
    return True


def process_pending_frames(detector, model_version: str) -> None:
    tables = fetch_tables()
    for frame in fetch_pending_frames():
        try:
            detections = detector(frame["image_path"])
            observations = build_table_observations(detections, tables, model_version)
            save_frame_observations(frame["id"], observations)
        except Exception as error:
            logger.exception("Failed to transform frame %s", frame["id"])
            mark_frame_failed(frame["id"], str(error))


def discover_media(input_dir: str) -> list[Path]:
    directory = Path(input_dir)
    directory.mkdir(parents=True, exist_ok=True)
    return sorted(path for path in directory.iterdir() if path.is_file())


def main() -> int:
    input_dir = os.getenv("INPUT_DIR", "data/inbox")
    processed_dir = os.getenv("PROCESSED_DIR", "data/processed")
    paths = discover_media(input_dir)
    logger.info("starting one-shot ETL for %s input file(s)", len(paths))
    for path in paths:
        ingest_path(path, processed_dir)
    logger.info("one-shot ETL finished")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
