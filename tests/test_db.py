from unittest import TestCase
from unittest.mock import MagicMock, patch

from app.db import fetch_latest_table_state, fetch_observation_history


class DatabaseMappingTests(TestCase):
    @patch("app.db.get_connection")
    def test_fetch_latest_table_state_maps_all_rows(self, get_connection):
        cursor = MagicMock()
        cursor.fetchall.return_value = [
            (1, "Table 1", 4, 2, True, 0.9, "mock-v1", None),
            (2, "Table 2", 4, 0, False, 0.95, "mock-v1", None),
        ]
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor
        get_connection.return_value.__enter__.return_value = connection

        result = fetch_latest_table_state()

        self.assertEqual([table["table_id"] for table in result], [1, 2])
        self.assertEqual(result[1]["table_name"], "Table 2")

    @patch("app.db.get_connection")
    def test_fetch_observation_history_maps_all_rows_and_passes_hours(self, get_connection):
        cursor = MagicMock()
        cursor.fetchall.return_value = [
            (1, "Table 1", 2, True, None),
            (1, "Table 1", 3, True, None),
        ]
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor
        get_connection.return_value.__enter__.return_value = connection

        result = fetch_observation_history(hours=6)

        self.assertEqual(cursor.execute.call_args[0][1], (6,))
        self.assertEqual([row["people_count"] for row in result], [2, 3])
        self.assertEqual(result[0]["table_name"], "Table 1")
