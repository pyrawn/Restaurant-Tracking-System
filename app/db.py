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
        for row in rows
    ]
