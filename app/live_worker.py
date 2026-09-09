import logging
import os
import time

from app.detector import load_detector, model_version_from_path
from app.worker import ingest_path, process_pending_frames
from app.youtube import capture_frames

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def get_env_int(name: str, default: int) -> int:
    value = int(os.getenv(name, str(default)))
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def run_cycle(
    video_url: str,
    frame_count: int,
    capture_interval: int,
    input_dir: str,
    processed_dir: str,
    detector,
    model_version: str,
) -> list[dict]:
    captured_paths = capture_frames(video_url, frame_count, capture_interval, input_dir)
    for path in captured_paths:
        ingest_path(path, processed_dir)
    results = process_pending_frames(detector, model_version)

    for result in results:
        logger.info(
            "frame %s (%s): %s person detection(s) -> %s",
            result["frame_id"],
            result["image_path"],
            result["person_detections"],
            {
                observation["table_id"]: observation["people_count"]
                for observation in result["observations"]
            },
        )
    return results


def main() -> int:
    video_url = os.environ["LIVE_STREAM_URL"]
    frame_count = get_env_int("LIVE_FRAME_COUNT", 5)
    capture_interval = get_env_int("LIVE_CAPTURE_INTERVAL_SECONDS", 30)
    poll_interval = get_env_int("LIVE_POLL_INTERVAL_SECONDS", 30)
    mode = os.getenv("LIVE_MODE", "once")
    input_dir = os.getenv("INPUT_DIR", "data/inbox")
    processed_dir = os.getenv("PROCESSED_DIR", "data/processed")

    detector = load_detector()
    model_version = model_version_from_path()

    logger.info(
        "starting live capture: url=%s mode=%s frames=%s capture_interval=%ss poll_interval=%ss",
        video_url, mode, frame_count, capture_interval, poll_interval,
    )

    while True:
        try:
            run_cycle(
                video_url, frame_count, capture_interval,
                input_dir, processed_dir, detector, model_version,
            )
        except Exception:
            logger.exception("live capture cycle failed")

        if mode != "loop":
            break
        time.sleep(poll_interval)

    logger.info("live capture finished")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
