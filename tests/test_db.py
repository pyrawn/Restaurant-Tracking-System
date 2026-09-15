from datetime import datetime, timezone
from unittest import TestCase
from unittest.mock import MagicMock, patch

from app.db import (
    ScheduleConflict,
    _episode_people_served,
    create_shift,
    fetch_latest_table_state,
    fetch_observation_history,
    fetch_waiter_stats,
    fetch_waiters,
    verify_user,
)


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


class EpisodePeopleServedTests(TestCase):
    def test_counts_peak_per_contiguous_occupied_run(self):
        observations = [
            (1, 4, True),
            (1, 4, True),
            (1, 0, False),
            (1, 2, True),
            (2, 3, True),
            (2, 0, False),
        ]

        self.assertEqual(_episode_people_served(observations), 9)

    def test_episode_still_open_at_end_of_window_counts(self):
        observations = [(1, 2, True), (1, 3, True), (1, 1, True)]

        self.assertEqual(_episode_people_served(observations), 3)

    def test_no_observations_returns_zero(self):
        self.assertEqual(_episode_people_served([]), 0)

    def test_never_occupied_returns_zero(self):
        observations = [(1, 0, False), (1, 0, False)]

        self.assertEqual(_episode_people_served(observations), 0)


class AuthTests(TestCase):
    @patch("app.db.check_password_hash")
    @patch("app.db.get_connection")
    def test_verify_user_returns_user_on_valid_password(self, get_connection, check_password_hash):
        check_password_hash.return_value = True
        cursor = MagicMock()
        cursor.fetchone.return_value = (1, "victor", "hash")
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor
        get_connection.return_value.__enter__.return_value = connection

        self.assertEqual(verify_user("victor", "123"), {"id": 1, "username": "victor"})

    @patch("app.db.get_connection")
    def test_verify_user_returns_none_when_username_unknown(self, get_connection):
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor
        get_connection.return_value.__enter__.return_value = connection

        self.assertIsNone(verify_user("nope", "123"))

    @patch("app.db.check_password_hash")
    @patch("app.db.get_connection")
    def test_verify_user_returns_none_on_wrong_password(self, get_connection, check_password_hash):
        check_password_hash.return_value = False
        cursor = MagicMock()
        cursor.fetchone.return_value = (1, "victor", "hash")
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor
        get_connection.return_value.__enter__.return_value = connection

        self.assertIsNone(verify_user("victor", "wrong"))


class WaiterTests(TestCase):
    @patch("app.db.get_connection")
    def test_fetch_waiters_maps_rows(self, get_connection):
        cursor = MagicMock()
        cursor.fetchall.return_value = [(1, "Carlos Mendoza", True)]
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor
        get_connection.return_value.__enter__.return_value = connection

        result = fetch_waiters()

        self.assertEqual(result, [{"id": 1, "name": "Carlos Mendoza", "active": True}])


class ShiftSchedulingTests(TestCase):
    @patch("app.db.get_connection")
    def test_create_shift_raises_on_waiter_overlap(self, get_connection):
        cursor = MagicMock()
        cursor.fetchone.side_effect = [(1,)]  # waiter overlap found
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor
        get_connection.return_value.__enter__.return_value = connection

        with self.assertRaises(ScheduleConflict):
            create_shift(
                1,
                datetime(2026, 1, 1, 9, tzinfo=timezone.utc),
                datetime(2026, 1, 1, 12, tzinfo=timezone.utc),
                [1],
            )

    @patch("app.db.get_connection")
    def test_create_shift_raises_on_table_overlap(self, get_connection):
        cursor = MagicMock()
        cursor.fetchone.side_effect = [None, (1,)]  # waiter ok, table conflict
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor
        get_connection.return_value.__enter__.return_value = connection

        with self.assertRaises(ScheduleConflict):
            create_shift(
                1,
                datetime(2026, 1, 1, 9, tzinfo=timezone.utc),
                datetime(2026, 1, 1, 12, tzinfo=timezone.utc),
                [1],
            )

    @patch("app.db.get_connection")
    def test_create_shift_returns_new_id_when_no_conflict(self, get_connection):
        cursor = MagicMock()
        cursor.fetchone.side_effect = [None, None, (42,)]
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor
        get_connection.return_value.__enter__.return_value = connection

        shift_id = create_shift(
            1,
            datetime(2026, 1, 1, 9, tzinfo=timezone.utc),
            datetime(2026, 1, 1, 12, tzinfo=timezone.utc),
            [1, 2],
        )

        self.assertEqual(shift_id, 42)


class WaiterStatsTests(TestCase):
    @patch("app.db.get_connection")
    def test_fetch_waiter_stats_aggregates_single_shift(self, get_connection):
        starts_at = datetime(2026, 1, 1, 9, tzinfo=timezone.utc)
        ends_at = datetime(2026, 1, 1, 11, tzinfo=timezone.utc)
        cursor = MagicMock()
        cursor.fetchall.side_effect = [
            [(1, 10, "Carlos Mendoza", starts_at, ends_at, [1, 2])],
            [(1, 4, True), (1, 4, True), (1, 0, False), (2, 2, True), (2, 0, False)],
        ]
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor
        get_connection.return_value.__enter__.return_value = connection

        result = fetch_waiter_stats(starts_at, ends_at)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["waiter_name"], "Carlos Mendoza")
        self.assertEqual(result[0]["shifts"], 1)
        self.assertEqual(result[0]["hours_worked"], 2.0)
        self.assertEqual(result[0]["avg_occupancy"], 2.0)
        self.assertEqual(result[0]["people_served"], 6)
