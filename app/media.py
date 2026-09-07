from pathlib import Path


def media_type(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png"}:
        return "image"
    if suffix == ".mp4":
        return "video"
    raise ValueError(f"unsupported media type: {suffix or '<none>'}")
