import logging
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def resolve_stream_url(video_url: str) -> str:
    result = subprocess.run(
        ["yt-dlp", "--no-warnings", "-g", "-f", "bestvideo/best", video_url],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise ValueError(f"yt-dlp failed to resolve stream: {result.stderr.strip()[-500:]}")

    lines = [line for line in result.stdout.strip().splitlines() if line]
    if not lines:
        raise ValueError("yt-dlp returned no stream URL")
    return lines[-1]


def capture_snapshot(stream_url: str, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", stream_url, "-frames:v", "1", "-q:v", "2", str(out_path)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0 or not out_path.exists():
        raise ValueError(f"ffmpeg failed to capture snapshot: {result.stderr.strip()[-500:]}")


def capture_frames(
    video_url: str,
    count: int,
    interval_seconds: int,
    output_dir: str,
) -> list[Path]:
    stream_url = resolve_stream_url(video_url)
    captured_paths: list[Path] = []

    for index in range(count):
        if index > 0:
            time.sleep(interval_seconds)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        out_path = Path(output_dir) / f"live_{timestamp}.jpg"
        capture_snapshot(stream_url, out_path)
        captured_paths.append(out_path)
        logger.info("captured live frame %s/%s: %s", index + 1, count, out_path)

    return captured_paths
