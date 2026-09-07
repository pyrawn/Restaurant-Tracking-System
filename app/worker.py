import logging
import os
import time
from pathlib import Path

from app.media import media_type


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def discover_media(input_dir: str) -> list[Path]:
    directory = Path(input_dir)
    directory.mkdir(parents=True, exist_ok=True)
    return sorted(path for path in directory.iterdir() if path.is_file())


def main() -> None:
    input_dir = os.getenv("INPUT_DIR", "/app/data/inbox")
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
            logger.info("discovered %s input: %s", kind, path.name)
            seen.add(path)
        time.sleep(poll_seconds)


if __name__ == "__main__":
    main()
