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
    ]

def insert_media_input(media_type: str, source_path: str, media_hash: str) -> int | None:
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO media_inputs (media_type, source_path, media_hash) VALUES (%s, %s, %s) RETURNING id",
                    (media_type, source_path, media_hash),
                )
                row = cursor.fetchone()
                if row:
                    return row[0]
                return None
    except psycopg.errors.UniqueViolation:
        return None

def update_media_input_status(media_input_id: int, status: str, error_message: str | None = None) -> None:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE media_inputs SET status = %s, error_message = %s WHERE id = %s",
                (status, error_message, media_input_id),
            )

def insert_frame(media_input_id: int, frame_index: int, offset_ms: int, image_path: str, captured_at: datetime) -> None:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO frames (media_input_id, frame_index, offset_ms, image_path, captured_at) VALUES (%s, %s, %s, %s, %s)",
                (media_input_id, frame_index, offset_ms, image_path, captured_at),
            )
