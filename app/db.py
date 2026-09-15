import json
import os
from datetime import date, datetime

import psycopg
from werkzeug.security import check_password_hash


TABLE_STATE_COLUMNS = (
    "table_id",
    "table_name",
    "capacity",
    "people_count",
    "occupied",
    "confidence",
    "model_version",
    "processed_at",
)

FRAME_COLUMNS = ("id", "image_path", "media_input_id", "frame_index", "captured_at")
TABLE_COLUMNS = ("id", "name", "capacity", "polygon")

HISTORY_COLUMNS = ("table_id", "table_name", "people_count", "occupied", "processed_at")


def get_connection():
    return psycopg.connect(os.environ["DATABASE_URL"])


def _rows_to_dicts(rows, columns):
    return [
        {
            column: value.isoformat() if isinstance(value, (date, datetime)) else value
            for column, value in zip(columns, row)
        }
        for row in rows
    ]


def fetch_latest_table_state() -> list[dict]:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM latest_table_state ORDER BY table_id")
            rows = cursor.fetchall()

    return _rows_to_dicts(rows, TABLE_STATE_COLUMNS)


def fetch_observation_history(hours: int = 3) -> list[dict]:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT t.id, t.name, o.people_count, o.occupied, o.processed_at
                FROM table_observations AS o
                JOIN tables AS t ON t.id = o.table_id
                WHERE o.processed_at >= NOW() - make_interval(hours => %s)
                ORDER BY o.processed_at
                """,
                (hours,),
            )
            rows = cursor.fetchall()

    return _rows_to_dicts(rows, HISTORY_COLUMNS)


def media_input_exists(media_hash: str) -> bool:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM media_inputs WHERE media_hash = %s",
                (media_hash,),
            )
            return cursor.fetchone() is not None


def load_media_and_frames(
    media_type: str,
    source_path: str,
    media_hash: str,
    frames: list[dict],
    status: str = "processed",
    error_message: str | None = None,
) -> int | None:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO media_inputs
                    (media_type, source_path, media_hash, status, error_message)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (media_hash) DO NOTHING
                RETURNING id
                """,
                (media_type, source_path, media_hash, status, error_message),
            )
            row = cursor.fetchone()
            if row is None:
                return None

            media_input_id = row[0]
            for frame in frames:
                cursor.execute(
                    """
                    INSERT INTO frames
                        (media_input_id, frame_index, offset_ms, image_path, captured_at)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        media_input_id,
                        frame["frame_index"],
                        frame["offset_ms"],
                        frame["image_path"],
                        frame["captured_at"],
                    ),
                )
            return media_input_id


def fetch_pending_frames() -> list[dict]:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, image_path, media_input_id, frame_index, captured_at
                FROM frames
                WHERE status = 'pending'
                ORDER BY id
                """
            )
            rows = cursor.fetchall()
    return [dict(zip(FRAME_COLUMNS, row)) for row in rows]


def fetch_tables() -> list[dict]:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id, name, capacity, polygon FROM tables ORDER BY id")
            rows = cursor.fetchall()

    tables = []
    for row in rows:
        table = dict(zip(TABLE_COLUMNS, row))
        if isinstance(table["polygon"], str):
            table["polygon"] = json.loads(table["polygon"])
        tables.append(table)
    return tables


def save_frame_observations(frame_id: int, observations: list[dict]) -> None:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            for observation in observations:
                cursor.execute(
                    """
                    INSERT INTO table_observations
                        (frame_id, table_id, people_count, occupied, confidence,
                         model_version)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (frame_id, table_id) DO UPDATE SET
                        people_count = EXCLUDED.people_count,
                        occupied = EXCLUDED.occupied,
                        confidence = EXCLUDED.confidence,
                        model_version = EXCLUDED.model_version,
                        processed_at = NOW()
                    """,
                    (
                        frame_id,
                        observation["table_id"],
                        observation["people_count"],
                        observation["occupied"],
                        observation["confidence"],
                        observation["model_version"],
                    ),
                )
            cursor.execute("UPDATE frames SET status = 'processed' WHERE id = %s", (frame_id,))


def mark_frame_failed(frame_id: int, error_message: str) -> None:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE frames SET status = 'failed' WHERE id = %s",
                (frame_id,),
            )


# --- Operational dashboard: auth, waiters, shift scheduling, stats -------

WAITER_COLUMNS = ("id", "name", "active")


class ScheduleConflict(Exception):
    """Raised when a shift would double-book a waiter or a table."""


def verify_user(username: str, password: str) -> dict | None:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, username, password_hash FROM users WHERE username = %s",
                (username,),
            )
            row = cursor.fetchone()

    if row is None or not check_password_hash(row[2], password):
        return None
    return {"id": row[0], "username": row[1]}


def fetch_waiters(active_only: bool = False) -> list[dict]:
    query = "SELECT id, name, active FROM waiters"
    if active_only:
        query += " WHERE active"
    query += " ORDER BY name"

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

    return [dict(zip(WAITER_COLUMNS, row)) for row in rows]


def create_waiter(name: str) -> int:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO waiters (name) VALUES (%s) RETURNING id",
                (name,),
            )
            return cursor.fetchone()[0]


def fetch_shifts(start: datetime, end: datetime) -> list[dict]:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT s.id, s.waiter_id, w.name, s.starts_at, s.ends_at,
                       COALESCE(
                           array_agg(t.id ORDER BY t.name)
                               FILTER (WHERE t.id IS NOT NULL),
                           '{}'
                       ),
                       COALESCE(
                           array_agg(t.name ORDER BY t.name)
                               FILTER (WHERE t.id IS NOT NULL),
                           '{}'
                       )
                FROM waiter_shifts s
                JOIN waiters w ON w.id = s.waiter_id
                LEFT JOIN waiter_shift_tables wst ON wst.shift_id = s.id
                LEFT JOIN tables t ON t.id = wst.table_id
                WHERE s.starts_at < %s AND s.ends_at > %s
                GROUP BY s.id, s.waiter_id, w.name, s.starts_at, s.ends_at
                ORDER BY s.starts_at
                """,
                (end, start),
            )
            rows = cursor.fetchall()

    return [
        {
            "id": shift_id,
            "waiter_id": waiter_id,
            "waiter_name": waiter_name,
            "starts_at": starts_at.isoformat(),
            "ends_at": ends_at.isoformat(),
            "table_ids": list(table_ids),
            "table_names": list(table_names),
        }
        for shift_id, waiter_id, waiter_name, starts_at, ends_at, table_ids, table_names in rows
    ]


def _has_waiter_overlap(cursor, waiter_id, starts_at, ends_at, exclude_shift_id=None) -> bool:
    cursor.execute(
        """
        SELECT 1 FROM waiter_shifts
        WHERE waiter_id = %s AND starts_at < %s AND ends_at > %s
          AND (%s::bigint IS NULL OR id != %s)
        LIMIT 1
        """,
        (waiter_id, ends_at, starts_at, exclude_shift_id, exclude_shift_id),
    )
    return cursor.fetchone() is not None


def _has_table_overlap(cursor, table_ids, starts_at, ends_at, exclude_shift_id=None) -> bool:
    if not table_ids:
        return False
    cursor.execute(
        """
        SELECT 1
        FROM waiter_shift_tables wst
        JOIN waiter_shifts s ON s.id = wst.shift_id
        WHERE wst.table_id = ANY(%s) AND s.starts_at < %s AND s.ends_at > %s
          AND (%s::bigint IS NULL OR s.id != %s)
        LIMIT 1
        """,
        (table_ids, ends_at, starts_at, exclude_shift_id, exclude_shift_id),
    )
    return cursor.fetchone() is not None


def _replace_shift_tables(cursor, shift_id: int, table_ids: list[int]) -> None:
    cursor.execute("DELETE FROM waiter_shift_tables WHERE shift_id = %s", (shift_id,))
    for table_id in table_ids:
        cursor.execute(
            "INSERT INTO waiter_shift_tables (shift_id, table_id) VALUES (%s, %s)",
            (shift_id, table_id),
        )


def create_shift(waiter_id: int, starts_at: datetime, ends_at: datetime, table_ids: list[int]) -> int:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            if _has_waiter_overlap(cursor, waiter_id, starts_at, ends_at):
                raise ScheduleConflict("El mesero ya tiene un turno en ese horario.")
            if _has_table_overlap(cursor, table_ids, starts_at, ends_at):
                raise ScheduleConflict("Una de las mesas ya está asignada en ese horario.")

            cursor.execute(
                "INSERT INTO waiter_shifts (waiter_id, starts_at, ends_at) VALUES (%s, %s, %s) RETURNING id",
                (waiter_id, starts_at, ends_at),
            )
            shift_id = cursor.fetchone()[0]
            _replace_shift_tables(cursor, shift_id, table_ids)
            return shift_id


def update_shift(
    shift_id: int, waiter_id: int, starts_at: datetime, ends_at: datetime, table_ids: list[int]
) -> None:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            if _has_waiter_overlap(cursor, waiter_id, starts_at, ends_at, exclude_shift_id=shift_id):
                raise ScheduleConflict("El mesero ya tiene un turno en ese horario.")
            if _has_table_overlap(cursor, table_ids, starts_at, ends_at, exclude_shift_id=shift_id):
                raise ScheduleConflict("Una de las mesas ya está asignada en ese horario.")

            cursor.execute(
                "UPDATE waiter_shifts SET waiter_id = %s, starts_at = %s, ends_at = %s WHERE id = %s",
                (waiter_id, starts_at, ends_at, shift_id),
            )
            _replace_shift_tables(cursor, shift_id, table_ids)


def delete_shift(shift_id: int) -> None:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM waiter_shifts WHERE id = %s", (shift_id,))


def _episode_people_served(observations: list[tuple]) -> int:
    """Sum the peak people_count of each contiguous occupied run per table.

    observations must be ordered by (table_id, processed_at); each item is
    (table_id, people_count, occupied). Avoids counting the same seated
    party once per detection frame (~every 30-40s) instead of once per visit.
    """
    served = 0
    current_table = None
    in_episode = False
    episode_peak = 0

    for table_id, people_count, occupied in observations:
        if table_id != current_table:
            if in_episode:
                served += episode_peak
            current_table = table_id
            in_episode = False
            episode_peak = 0

        if occupied:
            in_episode = True
            episode_peak = max(episode_peak, people_count)
        elif in_episode:
            served += episode_peak
            in_episode = False
            episode_peak = 0

    if in_episode:
        served += episode_peak
    return served


def fetch_waiter_stats(start: datetime, end: datetime) -> list[dict]:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT s.id, s.waiter_id, w.name, s.starts_at, s.ends_at,
                       array_agg(DISTINCT wst.table_id)
                FROM waiter_shifts s
                JOIN waiters w ON w.id = s.waiter_id
                JOIN waiter_shift_tables wst ON wst.shift_id = s.id
                WHERE s.starts_at < %s AND s.ends_at > %s
                GROUP BY s.id, s.waiter_id, w.name, s.starts_at, s.ends_at
                ORDER BY w.name, s.starts_at
                """,
                (end, start),
            )
            shifts = cursor.fetchall()

            stats_by_waiter: dict[int, dict] = {}
            for shift_id, waiter_id, waiter_name, starts_at, ends_at, table_ids in shifts:
                cursor.execute(
                    """
                    SELECT table_id, people_count, occupied
                    FROM table_observations
                    WHERE table_id = ANY(%s) AND processed_at >= %s AND processed_at < %s
                    ORDER BY table_id, processed_at
                    """,
                    (table_ids, max(starts_at, start), min(ends_at, end)),
                )
                observations = cursor.fetchall()

                entry = stats_by_waiter.setdefault(
                    waiter_id,
                    {
                        "waiter_id": waiter_id,
                        "waiter_name": waiter_name,
                        "shifts": 0,
                        "hours_worked": 0.0,
                        "occupancy_sum": 0.0,
                        "occupancy_count": 0,
                        "people_served": 0,
                    },
                )
                entry["shifts"] += 1
                entry["hours_worked"] += (ends_at - starts_at).total_seconds() / 3600
                entry["occupancy_sum"] += sum(row[1] for row in observations)
                entry["occupancy_count"] += len(observations)
                entry["people_served"] += _episode_people_served(observations)

    results = [
        {
            "waiter_id": entry["waiter_id"],
            "waiter_name": entry["waiter_name"],
            "shifts": entry["shifts"],
            "hours_worked": round(entry["hours_worked"], 1),
            "avg_occupancy": round(
                entry["occupancy_sum"] / entry["occupancy_count"], 2
            )
            if entry["occupancy_count"]
            else 0.0,
            "people_served": entry["people_served"],
        }
        for entry in stats_by_waiter.values()
    ]
    results.sort(key=lambda row: row["waiter_name"])
    return results
