import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.worker import (
    FRAME_INTERVAL_SECONDS,
    get_file_hash,
    get_frame_interval_seconds,
    ingest_path,
    main,
    process_image,
    process_pending_frames,
    process_video,
)


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.inbox_dir = Path(self.temp_dir.name) / "inbox"
        self.inbox_dir.mkdir()
        self.processed_dir = Path(self.temp_dir.name) / "processed"
        self.processed_dir.mkdir()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_get_file_hash(self):
        test_file = self.inbox_dir / "test.txt"
        test_file.write_text("hello world")
        self.assertEqual(
            get_file_hash(test_file),
            "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9",
        )

    @patch("app.worker.cv2.imread", return_value="decoded image")
    @patch("app.worker.cv2.imwrite", return_value=True)
    def test_process_image_returns_artifact_without_database_write(
        self, mock_imwrite, mock_imread
    ):
        test_file = self.inbox_dir / "image.png"
        test_file.write_text("fake image data")

        artifacts = process_image(test_file, "dummyhash", str(self.processed_dir))

        self.assertEqual(artifacts[0]["frame_index"], 0)
        self.assertEqual(artifacts[0]["offset_ms"], 0)
        self.assertEqual(artifacts[0]["image_path"],
                         str(self.processed_dir / "dummyhash" / "0.jpg"))
        mock_imread.assert_called_once()
        mock_imwrite.assert_called_once()

    @patch("app.worker.cv2.imread", return_value=None)
    def test_process_image_rejects_corrupt_input(self, mock_imread):
        test_file = self.inbox_dir / "corrupt.jpg"
        test_file.write_text("bad data")

        with self.assertRaises(ValueError):
            process_image(test_file, "hash", str(self.processed_dir))

    @patch("app.worker.cv2.VideoCapture")
    @patch("app.worker.cv2.imwrite", return_value=True)
    def test_process_video_returns_artifacts_without_database_write(
        self, mock_imwrite, mock_videocapture
    ):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.side_effect = [(True, "frame1"), (True, "frame2"), (False, None)]
        mock_videocapture.return_value = mock_cap

        test_file = self.inbox_dir / "video.mp4"
        test_file.write_text("fake video data")

        artifacts = process_video(test_file, "vidhash", str(self.processed_dir))

        self.assertEqual(len(artifacts), 2)
        self.assertEqual(artifacts[0]["offset_ms"], 0)
        self.assertEqual(artifacts[1]["offset_ms"], FRAME_INTERVAL_SECONDS * 1000)
        self.assertEqual(mock_imwrite.call_count, 2)
        mock_cap.release.assert_called_once()

    @patch("app.worker.cv2.VideoCapture")
    def test_process_video_rejects_corrupt_input(self, mock_videocapture):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False
        mock_videocapture.return_value = mock_cap

        test_file = self.inbox_dir / "corrupt.mp4"
        test_file.write_text("bad video")

        with self.assertRaises(ValueError):
            process_video(test_file, "hash", str(self.processed_dir))

    @patch("app.worker.fetch_pending_frames")
    @patch("app.worker.fetch_tables")
    @patch("app.worker.save_frame_observations")
    @patch("app.worker.mark_frame_failed")
    def test_process_pending_frames_uses_injected_detector(
        self, mock_mark_failed, mock_save, mock_tables, mock_frames
    ):
        mock_frames.return_value = [{"id": 7, "image_path": "frame.jpg"}]
        mock_tables.return_value = [{
            "id": 1,
            "polygon": [[0, 0], [10, 0], [10, 10], [0, 10]],
        }]
        detector = lambda path: [{"box": [1, 1, 3, 4], "confidence": 0.9}]

        results = process_pending_frames(detector, "mock-v1")

        mock_save.assert_called_once()
        self.assertEqual(mock_save.call_args.args[0], 7)
        self.assertEqual(results[0]["frame_id"], 7)
        self.assertEqual(results[0]["person_detections"], 1)
        self.assertEqual(mock_save.call_args.args[1][0]["people_count"], 1)
        mock_mark_failed.assert_not_called()

    def test_frame_interval_reads_environment(self):
        with patch.dict(os.environ, {"FRAME_INTERVAL_SECONDS": "5"}):
            self.assertEqual(get_frame_interval_seconds(), 5)

    @patch("app.worker.load_media_and_frames")
    @patch("app.worker.transform_media")
    @patch("app.worker.media_input_exists", return_value=False)
    @patch("app.worker.get_file_hash", return_value="hash")
    @patch("app.worker.media_type", return_value="image")
    def test_ingest_transforms_before_loading(
        self, mock_media_type, mock_hash, mock_exists, mock_transform, mock_load
    ):
        events = []
        mock_transform.side_effect = lambda *args: events.append("transform") or [{
            "frame_index": 0,
            "offset_ms": 0,
            "image_path": "processed/0.jpg",
            "captured_at": datetime.now(timezone.utc),
        }]
        mock_load.side_effect = lambda *args, **kwargs: events.append("load") or 1
        test_file = self.inbox_dir / "image.jpg"
        test_file.write_text("fake image data")

        ingest_path(test_file, str(self.processed_dir))

        self.assertEqual(events, ["transform", "load"])
        mock_load.assert_called_once()

    @patch("app.worker.load_media_and_frames")
    @patch("app.worker.transform_media", side_effect=ValueError("bad media"))
    @patch("app.worker.media_input_exists", return_value=False)
    @patch("app.worker.get_file_hash", return_value="hash")
    @patch("app.worker.media_type", return_value="image")
    def test_failed_transform_loads_no_frames(
        self, mock_media_type, mock_hash, mock_exists, mock_transform, mock_load
    ):
        test_file = self.inbox_dir / "corrupt.jpg"
        test_file.write_text("bad data")

        ingest_path(test_file, str(self.processed_dir))

        mock_load.assert_called_once()
        self.assertEqual(mock_load.call_args.args[3], [])
        self.assertEqual(mock_load.call_args.kwargs["status"], "failed")

    @patch("app.worker.process_pending_frames", return_value=[])
    @patch("app.worker.model_version_from_path", return_value="mock-v1")
    @patch("app.worker.load_detector")
    @patch("app.worker.ingest_path")
    @patch("app.worker.discover_media")
    def test_main_processes_inbox_once(
        self, mock_discover, mock_ingest, mock_load_detector, mock_model_version, mock_process
    ):
        paths = [self.inbox_dir / "one.jpg"]
        mock_discover.return_value = paths
        mock_detector = MagicMock()
        mock_load_detector.return_value = mock_detector

        with patch.dict(os.environ, {
            "INPUT_DIR": str(self.inbox_dir),
            "PROCESSED_DIR": str(self.processed_dir),
        }):
            result = main()

        self.assertEqual(result, 0)
        mock_ingest.assert_called_once_with(paths[0], str(self.processed_dir))
        mock_process.assert_called_once_with(mock_detector, "mock-v1")
