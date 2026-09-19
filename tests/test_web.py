from unittest import TestCase
from unittest.mock import patch

from app.db import ScheduleConflict
from app.web import app


class AuthenticatedTestCase(TestCase):
    """Base class for routes that sit behind @login_required."""

    def setUp(self):
        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session["user_id"] = 1
            session["username"] = "victor"


class LoginGatingTests(TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_dashboard_redirects_to_login_when_unauthenticated(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_api_route_returns_401_json_when_unauthenticated(self):
        response = self.client.get("/api/tables/latest")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json(), {"error": "authentication required"})

    @patch("app.web.verify_user")
    def test_login_sets_session_and_redirects(self, verify_user):
        verify_user.return_value = {"id": 1, "username": "victor"}

        response = self.client.post("/login", data={"username": "victor", "password": "123"})

        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as session:
            self.assertEqual(session["user_id"], 1)

    @patch("app.web.verify_user")
    def test_login_rejects_bad_credentials(self, verify_user):
        verify_user.return_value = None

        response = self.client.post("/login", data={"username": "victor", "password": "wrong"})

        self.assertEqual(response.status_code, 401)
        with self.client.session_transaction() as session:
            self.assertNotIn("user_id", session)

    def test_logout_clears_session(self):
        with self.client.session_transaction() as session:
            session["user_id"] = 1

        response = self.client.get("/logout")

        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as session:
            self.assertNotIn("user_id", session)


class TablesApiTests(AuthenticatedTestCase):
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


class WaiterApiTests(AuthenticatedTestCase):
    @patch("app.web.fetch_waiters")
    def test_list_waiters(self, fetch_waiters):
        fetch_waiters.return_value = [{"id": 1, "name": "Carlos Mendoza", "active": True}]

        response = self.client.get("/api/waiters")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), [{"id": 1, "name": "Carlos Mendoza", "active": True}])

    @patch("app.web.create_waiter")
    def test_add_waiter_requires_name(self, create_waiter):
        response = self.client.post("/api/waiters", json={"name": "  "})

        self.assertEqual(response.status_code, 400)
        create_waiter.assert_not_called()

    @patch("app.web.create_waiter")
    def test_add_waiter_creates_and_returns_id(self, create_waiter):
        create_waiter.return_value = 7

        response = self.client.post("/api/waiters", json={"name": "Nuevo Mesero"})

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["id"], 7)


class ShiftApiTests(AuthenticatedTestCase):
    def test_list_shifts_requires_start_and_end(self):
        response = self.client.get("/api/shifts")

        self.assertEqual(response.status_code, 400)

    @patch("app.web.fetch_shifts")
    def test_list_shifts_passes_parsed_range(self, fetch_shifts):
        fetch_shifts.return_value = []

        response = self.client.get("/api/shifts?start=2026-01-01T00:00:00%2B00:00&end=2026-01-02T00:00:00%2B00:00")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(fetch_shifts.called)

    @patch("app.web.create_shift")
    def test_add_shift_rejects_missing_fields(self, create_shift):
        response = self.client.post("/api/shifts", json={"waiter_id": 1})

        self.assertEqual(response.status_code, 400)
        create_shift.assert_not_called()

    @patch("app.web.create_shift")
    def test_add_shift_rejects_end_before_start(self, create_shift):
        response = self.client.post(
            "/api/shifts",
            json={
                "waiter_id": 1,
                "starts_at": "2026-01-01T12:00:00+00:00",
                "ends_at": "2026-01-01T09:00:00+00:00",
                "table_ids": [1],
            },
        )

        self.assertEqual(response.status_code, 400)
        create_shift.assert_not_called()

    @patch("app.web.create_shift")
    def test_add_shift_returns_409_on_conflict(self, create_shift):
        create_shift.side_effect = ScheduleConflict("El mesero ya tiene un turno en ese horario.")

        response = self.client.post(
            "/api/shifts",
            json={
                "waiter_id": 1,
                "starts_at": "2026-01-01T09:00:00+00:00",
                "ends_at": "2026-01-01T12:00:00+00:00",
                "table_ids": [1],
            },
        )

        self.assertEqual(response.status_code, 409)

    @patch("app.web.create_shift")
    def test_add_shift_creates_successfully(self, create_shift):
        create_shift.return_value = 5

        response = self.client.post(
            "/api/shifts",
            json={
                "waiter_id": 1,
                "starts_at": "2026-01-01T09:00:00+00:00",
                "ends_at": "2026-01-01T12:00:00+00:00",
                "table_ids": [1, 2],
            },
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["id"], 5)

    @patch("app.web.delete_shift")
    def test_delete_shift(self, delete_shift):
        response = self.client.delete("/api/shifts/5")

        self.assertEqual(response.status_code, 204)
        delete_shift.assert_called_once_with(5)


class BulkShiftApiTests(AuthenticatedTestCase):
    def test_bulk_rejects_empty_list(self):
        response = self.client.post("/api/shifts/bulk", json={"shifts": []})

        self.assertEqual(response.status_code, 400)

    def test_bulk_rejects_missing_shifts_key(self):
        response = self.client.post("/api/shifts/bulk", json={})

        self.assertEqual(response.status_code, 400)

    @patch("app.web.create_shift")
    def test_bulk_reports_mixed_success_and_conflicts(self, create_shift):
        create_shift.side_effect = [1, ScheduleConflict("El mesero ya tiene un turno en ese horario.")]

        response = self.client.post(
            "/api/shifts/bulk",
            json={
                "shifts": [
                    {
                        "waiter_id": 1,
                        "starts_at": "2026-01-01T09:00:00+00:00",
                        "ends_at": "2026-01-01T12:00:00+00:00",
                        "table_ids": [1],
                    },
                    {
                        "waiter_id": 1,
                        "starts_at": "2026-01-08T09:00:00+00:00",
                        "ends_at": "2026-01-08T12:00:00+00:00",
                        "table_ids": [1],
                    },
                ]
            },
        )

        self.assertEqual(response.status_code, 207)
        body = response.get_json()
        self.assertEqual(body["created"], [{"index": 0, "id": 1}])
        self.assertEqual(len(body["conflicts"]), 1)
        self.assertEqual(body["conflicts"][0]["index"], 1)

    @patch("app.web.create_shift")
    def test_bulk_flags_invalid_item_without_aborting_others(self, create_shift):
        create_shift.return_value = 9

        response = self.client.post(
            "/api/shifts/bulk",
            json={
                "shifts": [
                    {"waiter_id": 1},  # missing starts_at/ends_at/table_ids
                    {
                        "waiter_id": 1,
                        "starts_at": "2026-01-01T09:00:00+00:00",
                        "ends_at": "2026-01-01T12:00:00+00:00",
                        "table_ids": [1],
                    },
                ]
            },
        )

        self.assertEqual(response.status_code, 207)
        body = response.get_json()
        self.assertEqual(body["conflicts"], [{"index": 0, "error": "invalid shift payload"}])
        self.assertEqual(body["created"], [{"index": 1, "id": 9}])


class WaiterStatsApiTests(AuthenticatedTestCase):
    @patch("app.web.fetch_waiter_stats")
    def test_stats_defaults_to_last_seven_days(self, fetch_waiter_stats):
        fetch_waiter_stats.return_value = []

        response = self.client.get("/api/waiters/stats")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(fetch_waiter_stats.called)

    @patch("app.web.fetch_waiter_stats")
    def test_stats_passes_through_custom_range(self, fetch_waiter_stats):
        fetch_waiter_stats.return_value = [{"waiter_name": "Carlos Mendoza", "people_served": 6}]

        response = self.client.get(
            "/api/waiters/stats?start=2026-01-01T00:00:00%2B00:00&end=2026-01-02T00:00:00%2B00:00"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()[0]["people_served"], 6)
