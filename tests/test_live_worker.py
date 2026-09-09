import os
import unittest
from unittest.mock import MagicMock, patch

from app.live_worker import main, run_cycle


class StopLoop(Exception):
    pass


class LiveWorkerTests(unittest.TestCase):
    @patch("app.live_worker.process_pending_frames")
    @patch("app.live_worker.ingest_path")
    @patch("app.live_worker.capture_frames")
    def test_run_cycle_ingests_captured_frames_and_runs_detector(
        self, mock_capture, mock_ingest, mock_process
    ):
        mock_capture.return_value = ["/data/inbox/live_1.jpg", "/data/inbox/live_2.jpg"]
        mock_process.return_value = [{
            "frame_id": 1,
            "image_path": "/data/processed/x/0.jpg",
            "person_detections": 2,
            "observations": [{"table_id": 1, "people_count": 2}],
        }]
        detector = MagicMock()

        results = run_cycle(
            "https://www.youtube.com/live/example",
            frame_count=2,
            capture_interval=30,
            input_dir="/data/inbox",
            processed_dir="/data/processed",
            detector=detector,
            model_version="mock-v1",
        )

        mock_capture.assert_called_once_with(
            "https://www.youtube.com/live/example", 2, 30, "/data/inbox",
        )
        self.assertEqual(mock_ingest.call_count, 2)
        mock_process.assert_called_once_with(detector, "mock-v1")
        self.assertEqual(results[0]["person_detections"], 2)

    @patch("app.live_worker.time.sleep")
    @patch("app.live_worker.run_cycle")
    @patch("app.live_worker.model_version_from_path", return_value="mock-v1")
    @patch("app.live_worker.load_detector")
    def test_main_runs_once_by_default(
        self, mock_load_detector, mock_model_version, mock_run_cycle, mock_sleep
    ):
        with patch.dict(os.environ, {
            "LIVE_STREAM_URL": "https://www.youtube.com/live/example",
        }, clear=True):
            result = main()

        self.assertEqual(result, 0)
        mock_run_cycle.assert_called_once()
        mock_sleep.assert_not_called()

    @patch("app.live_worker.time.sleep")
    @patch("app.live_worker.run_cycle")
    @patch("app.live_worker.model_version_from_path", return_value="mock-v1")
    @patch("app.live_worker.load_detector")
    def test_main_loops_when_mode_is_loop(
        self, mock_load_detector, mock_model_version, mock_run_cycle, mock_sleep
    ):
        mock_sleep.side_effect = [None, StopLoop()]

        with patch.dict(os.environ, {
            "LIVE_STREAM_URL": "https://www.youtube.com/live/example",
            "LIVE_MODE": "loop",
        }, clear=True):
            with self.assertRaises(StopLoop):
                main()

        self.assertEqual(mock_run_cycle.call_count, 2)

    @patch("app.live_worker.run_cycle", side_effect=ValueError("boom"))
    @patch("app.live_worker.model_version_from_path", return_value="mock-v1")
    @patch("app.live_worker.load_detector")
    def test_main_survives_cycle_failure_in_once_mode(
        self, mock_load_detector, mock_model_version, mock_run_cycle
    ):
        with patch.dict(os.environ, {
            "LIVE_STREAM_URL": "https://www.youtube.com/live/example",
        }, clear=True):
            result = main()

        self.assertEqual(result, 0)


if __name__ == "__main__":
    unittest.main()
