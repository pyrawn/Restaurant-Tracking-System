import json
import os
from datetime import date, datetime

import psycopg


TABLE_STATE_COLUMNS = (
    "table_id",
    "table_name",
    "capacity",
    "people_count",
    "occupied",
    "confidence",
    "detected_waiter_id",
    "model_version",
    "processed_at",
    "assigned_waiter_id",
    "assigned_waiter_name",
)

FRAME_COLUMNS = ("id", "image_path", "media_input_id", "frame_index", "captured_at")
TABLE_COLUMNS = ("id", "name", "capacity", "polygon")


def get_connection():
    return psycopg.connect(os.environ["DATABASE_URL"])


def fetch_latest_table_state() -> list[dict]:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM latest_table_state ORDER BY table_id")
            rows = cursor.fetchall()

    return [
        {
            column: value.isoformat() if isinstance(value, (date, datetime)) else value
            for column, value in zip(TABLE_STATE_COLUMNS, row)
        }
        for row in rows
    ]


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
                         detected_waiter_id, model_version)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (frame_id, table_id) DO UPDATE SET
                        people_count = EXCLUDED.people_count,
                        occupied = EXCLUDED.occupied,
                        confidence = EXCLUDED.confidence,
                        detected_waiter_id = EXCLUDED.detected_waiter_id,
                        model_version = EXCLUDED.model_version,
                        processed_at = NOW()
                    """,
                    (
                        frame_id,
                        observation["table_id"],
                        observation["people_count"],
                        observation["occupied"],
                        observation["confidence"],
                        observation.get("detected_waiter_id"),
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
