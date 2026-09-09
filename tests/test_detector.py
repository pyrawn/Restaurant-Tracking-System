import os
import unittest
from unittest.mock import MagicMock, patch

from app.detector import (
    get_confidence_threshold,
    get_model_path,
    load_detector,
    model_version_from_path,
)


class DetectorTests(unittest.TestCase):
    def test_get_model_path_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(get_model_path(), "/app/models/yolov8s.pt")

    def test_get_model_path_reads_environment(self):
        with patch.dict(os.environ, {"MODEL_PATH": "/tmp/custom.pt"}):
            self.assertEqual(get_model_path(), "/tmp/custom.pt")

    def test_get_confidence_threshold_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(get_confidence_threshold(), 0.25)

    def test_model_version_from_path(self):
        self.assertEqual(model_version_from_path("/app/models/yolov8s.pt"), "yolo:yolov8s")

    @patch("app.detector.YOLO")
    def test_load_detector_filters_person_class_and_formats_detections(self, mock_yolo_cls):
        mock_box = MagicMock()
        mock_box.xyxy = [MagicMock(tolist=MagicMock(return_value=[1.0, 2.0, 3.0, 4.0]))]
        mock_box.conf = [0.87]

        mock_result = MagicMock()
        mock_result.boxes = [mock_box]

        mock_model = MagicMock()
        mock_model.predict.return_value = [mock_result]
        mock_yolo_cls.return_value = mock_model

        detect = load_detector(model_path="/tmp/model.pt", confidence_threshold=0.4)
        detections = detect("frame.jpg")

        mock_yolo_cls.assert_called_once_with("/tmp/model.pt")
        mock_model.predict.assert_called_once_with(
            source="frame.jpg", classes=[0], conf=0.4, verbose=False,
        )
        self.assertEqual(detections, [{"box": [1.0, 2.0, 3.0, 4.0], "confidence": 0.87}])


if __name__ == "__main__":
    unittest.main()
