import os
from pathlib import Path

from ultralytics import YOLO

PERSON_CLASS_ID = 0
DEFAULT_MODEL_PATH = "/app/models/model.pt"
DEFAULT_CONFIDENCE_THRESHOLD = 0.5


def get_model_path() -> str:
    return os.getenv("MODEL_PATH", DEFAULT_MODEL_PATH)


def get_confidence_threshold() -> float:
    return float(os.getenv("CONFIDENCE_THRESHOLD", str(DEFAULT_CONFIDENCE_THRESHOLD)))


def model_version_from_path(model_path: str | None = None) -> str:
    return f"yolo:{Path(model_path or get_model_path()).stem}"


def load_detector(model_path: str | None = None, confidence_threshold: float | None = None):
    model_path = model_path or get_model_path()
    confidence_threshold = (
        confidence_threshold if confidence_threshold is not None else get_confidence_threshold()
    )
    model = YOLO(model_path)

    def detect(image_path: str) -> list[dict]:
        results = model.predict(
            source=image_path,
            classes=[PERSON_CLASS_ID],
            conf=confidence_threshold,
            verbose=False,
        )
        detections = []
        for result in results:
            for box in result.boxes:
                detections.append({
                    "box": [float(value) for value in box.xyxy[0].tolist()],
                    "confidence": float(box.conf[0]),
                })
        return detections

    return detect
