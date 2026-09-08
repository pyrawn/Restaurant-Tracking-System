import hashlib
import logging
import os
import time
import shutil
from datetime import datetime, timezone
from pathlib import Path

import cv2

from app.media import media_type
from app.db import insert_media_input, update_media_input_status, insert_frame

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

FRAME_INTERVAL_SECONDS = 30


def get_file_hash(path: Path) -> str:
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    return sha256.hexdigest()


def process_image(media_input_id: int, path: Path, media_hash: str, processed_dir: str):
    img = cv2.imread(str(path))
    if img is None:
        raise ValueError("Failed to read image")
    
    out_dir = Path(processed_dir) / media_hash
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "0.jpg"
    
    # Save the frame
    shutil.copy2(path, out_path)
    
    captured_at = datetime.now(timezone.utc)
    insert_frame(media_input_id, 0, 0, str(out_path), captured_at)


def process_video(media_input_id: int, path: Path, media_hash: str, processed_dir: str):
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError("Failed to open video")
    
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = 30.0  # Fallback
        
    out_dir = Path(processed_dir) / media_hash
    out_dir.mkdir(parents=True, exist_ok=True)
    
    frame_index = 0
    captured_at = datetime.now(timezone.utc)
    
    while True:
        # Calculate frame position
        offset_ms = frame_index * FRAME_INTERVAL_SECONDS * 1000
        cap.set(cv2.CAP_PROP_POS_MSEC, offset_ms)
        
        ret, frame = cap.read()
        if not ret:
            break
            
        out_path = out_dir / f"{frame_index}.jpg"
        cv2.imwrite(str(out_path), frame)
        
        insert_frame(media_input_id, frame_index, int(offset_ms), str(out_path), captured_at)
        frame_index += 1
        
    cap.release()
    
    if frame_index == 0:
        raise ValueError("No frames could be extracted from the video")


def discover_media(input_dir: str) -> list[Path]:
    directory = Path(input_dir)
    directory.mkdir(parents=True, exist_ok=True)
    return sorted(path for path in directory.iterdir() if path.is_file())


def main() -> None:
    input_dir = os.getenv("INPUT_DIR", "data/inbox")
    processed_dir = os.getenv("PROCESSED_DIR", "data/processed")
    poll_seconds = int(os.getenv("INGEST_POLL_SECONDS", "30"))
    seen: set[Path] = set()

    logger.info("worker ready; watching %s every %ss", input_dir, poll_seconds)
    while True:
        for path in discover_media(input_dir):
            if path in seen:
                continue
            
            try:
                kind = media_type(str(path))
            except ValueError:
                logger.warning("ignored unsupported file: %s", path.name)
                seen.add(path)
                continue
            
            try:
                media_hash = get_file_hash(path)
            except Exception as e:
                logger.error("Failed to hash file %s: %s", path.name, e)
                seen.add(path)
                continue

            media_input_id = insert_media_input(kind, str(path), media_hash)
            
            if media_input_id is None:
                logger.info("Ignored duplicate file: %s", path.name)
                seen.add(path)
                continue
                
            logger.info("Processing %s input: %s (id: %s)", kind, path.name, media_input_id)
            try:
                if kind == "image":
                    process_image(media_input_id, path, media_hash, processed_dir)
                elif kind == "video":
                    process_video(media_input_id, path, media_hash, processed_dir)
                update_media_input_status(media_input_id, "processed")
                logger.info("Successfully processed %s", path.name)
            except Exception as e:
                logger.error("Failed to process %s: %s", path.name, e)
                update_media_input_status(media_input_id, "failed", str(e))
                
            seen.add(path)
        time.sleep(poll_seconds)


if __name__ == "__main__":
    main()
