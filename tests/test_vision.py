from unittest import TestCase

from app.vision import build_table_observations, point_in_polygon


class VisionTests(TestCase):
    polygon = [[0, 0], [10, 0], [10, 10], [0, 10]]

    def test_point_in_polygon_includes_boundary(self):
        self.assertTrue(point_in_polygon((5, 5), self.polygon))
        self.assertTrue(point_in_polygon((0, 5), self.polygon))
        self.assertFalse(point_in_polygon((15, 5), self.polygon))

    def test_assigns_detection_by_bottom_center(self):
        tables = [
            {"id": 1, "polygon": self.polygon},
            {"id": 2, "polygon": [[20, 0], [30, 0], [30, 10], [20, 10]]},
        ]
        detections = [
            {"box": [1, 1, 3, 4], "confidence": 0.8},
            {"box": [50, 50, 60, 60], "confidence": 0.9},
        ]

        result = build_table_observations(detections, tables, "mock-v1")

        self.assertEqual(result[0]["table_id"], 1)
        self.assertEqual(result[0]["people_count"], 1)
        self.assertTrue(result[0]["occupied"])
        self.assertEqual(result[0]["confidence"], 0.8)
        self.assertEqual(result[0]["model_version"], "mock-v1")
        self.assertEqual(result[1]["people_count"], 0)
        self.assertFalse(result[1]["occupied"])
