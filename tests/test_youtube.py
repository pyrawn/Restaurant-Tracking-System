import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from app.youtube import capture_frames, capture_snapshot, resolve_stream_url


class YoutubeTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch("app.youtube.subprocess.run")
    def test_resolve_stream_url_returns_last_line(self, mock_run):
        mock_run.return_value = CompletedProcess(
            args=[], returncode=0, stdout="https://stream.example/manifest.m3u8\n", stderr="",
        )

        stream_url = resolve_stream_url("https://www.youtube.com/live/example")

        self.assertEqual(stream_url, "https://stream.example/manifest.m3u8")

    @patch("app.youtube.subprocess.run")
    def test_resolve_stream_url_raises_on_failure(self, mock_run):
        mock_run.return_value = CompletedProcess(
            args=[], returncode=1, stdout="", stderr="ERROR: No video formats found",
        )

        with self.assertRaises(ValueError):
            resolve_stream_url("https://www.youtube.com/live/example")

    @patch("app.youtube.subprocess.run")
    def test_capture_snapshot_raises_when_file_missing(self, mock_run):
        mock_run.return_value = CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        out_path = Path(self.temp_dir.name) / "frame.jpg"

        with self.assertRaises(ValueError):
            capture_snapshot("https://stream.example/manifest.m3u8", out_path)

    @patch("app.youtube.time.sleep")
    @patch("app.youtube.capture_snapshot")
    @patch("app.youtube.resolve_stream_url", return_value="https://stream.example/manifest.m3u8")
    def test_capture_frames_resolves_once_and_captures_count(
        self, mock_resolve, mock_snapshot, mock_sleep
    ):
        paths = capture_frames(
            "https://www.youtube.com/live/example",
            count=3,
            interval_seconds=10,
            output_dir=self.temp_dir.name,
        )

        mock_resolve.assert_called_once_with("https://www.youtube.com/live/example")
        self.assertEqual(mock_snapshot.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)
        self.assertEqual(len(paths), 3)


if __name__ == "__main__":
    unittest.main()
