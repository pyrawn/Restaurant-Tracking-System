from unittest import TestCase
from unittest.mock import patch

from app.web import app


class WebRoutesTests(TestCase):
    def setUp(self):
        self.client = app.test_client()

    @patch("app.web.fetch_latest_table_state")
    def test_latest_tables_returns_json(self, fetch_latest_table_state):
        fetch_latest_table_state.return_value = [{"table_id": 1, "table_name": "Table 1"}]

        response = self.client.get("/api/tables/latest")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), [{"table_id": 1, "table_name": "Table 1"}])

    @patch("app.web.fetch_latest_table_state")
    def test_latest_tables_returns_503_on_failure(self, fetch_latest_table_state):
        fetch_latest_table_state.side_effect = RuntimeError("db down")

        response = self.client.get("/api/tables/latest")

        self.assertEqual(response.status_code, 503)

    @patch("app.web.fetch_observation_history")
    def test_history_defaults_to_three_hours(self, fetch_observation_history):
        fetch_observation_history.return_value = []

        response = self.client.get("/api/tables/history")

        self.assertEqual(response.status_code, 200)
        fetch_observation_history.assert_called_once_with(hours=3)

    @patch("app.web.fetch_observation_history")
    def test_history_passes_through_hours_query_param(self, fetch_observation_history):
        fetch_observation_history.return_value = []

        response = self.client.get("/api/tables/history?hours=8")

        self.assertEqual(response.status_code, 200)
        fetch_observation_history.assert_called_once_with(hours=8)

    @patch("app.web.fetch_observation_history")
    def test_history_clamps_out_of_range_hours(self, fetch_observation_history):
        fetch_observation_history.return_value = []

        response = self.client.get("/api/tables/history?hours=100")

        self.assertEqual(response.status_code, 200)
        fetch_observation_history.assert_called_once_with(hours=24)

    def test_history_rejects_non_integer_hours(self):
        response = self.client.get("/api/tables/history?hours=abc")

        self.assertEqual(response.status_code, 400)
