from unittest import TestCase

from app.domain import table_state
from app.media import media_type


class MediaAndDomainTests(TestCase):
    def test_classifies_images_and_mp4(self):
        self.assertEqual(media_type("capture.PNG"), "image")
        self.assertEqual(media_type("session.mp4"), "video")

    def test_rejects_unknown_media(self):
        with self.assertRaises(ValueError):
            media_type("notes.txt")

    def test_table_state_uses_count_and_confidence(self):
        self.assertEqual(table_state(0, 0.90), "free")
        self.assertEqual(table_state(2, 0.90), "occupied")
        self.assertEqual(table_state(2, 0.40), "review")
