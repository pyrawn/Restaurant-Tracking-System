import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from app.worker import (
    get_file_hash,
    process_image,
    process_video,
    main,
    FRAME_INTERVAL_SECONDS
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
        h = get_file_hash(test_file)
        self.assertEqual(h, "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9")

    @patch("app.worker.insert_frame")
    @patch("app.worker.cv2.imread")
    @patch("app.worker.shutil.copy2")
    def test_process_image_valid(self, mock_copy2, mock_imread, mock_insert_frame):
        # Setup mock valid image
        mock_imread.return_value = "dummy_img_data"
        
        test_file = self.inbox_dir / "image.jpg"
        test_file.write_text("fake image data")
        
        media_hash = "dummyhash"
        process_image(1, test_file, media_hash, str(self.processed_dir))
        
        # Verify
        mock_copy2.assert_called_once()
        mock_insert_frame.assert_called_once()
        args = mock_insert_frame.call_args[0]
        self.assertEqual(args[0], 1) # media_input_id
        self.assertEqual(args[1], 0) # frame_index
        self.assertEqual(args[2], 0) # offset_ms

    @patch("app.worker.cv2.imread")
    def test_process_image_corrupt(self, mock_imread):
        mock_imread.return_value = None
        
        test_file = self.inbox_dir / "corrupt.jpg"
        test_file.write_text("bad data")
        
        with self.assertRaises(ValueError):
            process_image(1, test_file, "hash", str(self.processed_dir))

    @patch("app.worker.insert_frame")
    @patch("app.worker.cv2.VideoCapture")
    @patch("app.worker.cv2.imwrite")
    def test_process_video_valid(self, mock_imwrite, mock_videocapture, mock_insert_frame):
        # Mock video capture that returns 2 frames
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.return_value = 30.0 # fps
        
        # side effect for read: return True twice, then False
        mock_cap.read.side_effect = [(True, "frame1"), (True, "frame2"), (False, None)]
        mock_videocapture.return_value = mock_cap
        
        test_file = self.inbox_dir / "video.mp4"
        test_file.write_text("fake video data")
        
        process_video(2, test_file, "vidhash", str(self.processed_dir))
        
        # Should have saved 2 frames
        self.assertEqual(mock_imwrite.call_count, 2)
        self.assertEqual(mock_insert_frame.call_count, 2)
        
        # Verify frame indices and offsets
        first_call_args = mock_insert_frame.call_args_list[0][0]
        self.assertEqual(first_call_args[1], 0) # frame_index
        self.assertEqual(first_call_args[2], 0) # offset_ms
        
        second_call_args = mock_insert_frame.call_args_list[1][0]
        self.assertEqual(second_call_args[1], 1)
        self.assertEqual(second_call_args[2], FRAME_INTERVAL_SECONDS * 1000)

    @patch("app.worker.cv2.VideoCapture")
    def test_process_video_corrupt(self, mock_videocapture):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False
        mock_videocapture.return_value = mock_cap
        
        test_file = self.inbox_dir / "corrupt.mp4"
        test_file.write_text("bad video")
        
        with self.assertRaises(ValueError):
            process_video(2, test_file, "hash", str(self.processed_dir))

    @patch("app.worker.time.sleep", side_effect=InterruptedError("stop loop"))
    @patch("app.worker.insert_media_input")
    @patch("app.worker.update_media_input_status")
    @patch("app.worker.process_image")
    def test_main_loop_processes_files(self, mock_process_image, mock_update_status, mock_insert, mock_sleep):
        # Setup files
        valid_img = self.inbox_dir / "valid.jpg"
        valid_img.write_text("valid")
        unsupported = self.inbox_dir / "file.txt"
        unsupported.write_text("unsupported")
        duplicate = self.inbox_dir / "dup.jpg"
        duplicate.write_text("dup")
        
        # Mock insert behavior: valid returns 1, duplicate returns None
        def mock_insert_side_effect(kind, path, hash_val):
            if "dup" in path:
                return None
            return 1
            
        mock_insert.side_effect = mock_insert_side_effect
        
        # Set environment variables for main
        os.environ["INPUT_DIR"] = str(self.inbox_dir)
        os.environ["PROCESSED_DIR"] = str(self.processed_dir)
        os.environ["INGEST_POLL_SECONDS"] = "0"
        
        with self.assertRaises(InterruptedError):
            main()
            
        # Verify valid image was processed
        mock_process_image.assert_called_once()
        # Verify valid image got updated status
        mock_update_status.assert_called_once_with(1, "processed")
        
        # Duplicate should not trigger processing
        # Unsupported should not even trigger insert
        self.assertEqual(mock_insert.call_count, 2) # Only valid and dup got to insert

