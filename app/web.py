import os
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Flask, jsonify, redirect, render_template, request, session, url_for

from app.db import (
    ScheduleConflict,
    create_shift,
    create_waiter,
    delete_shift,
    fetch_latest_table_state,
    fetch_observation_history,
    fetch_shifts,
    fetch_tables,
    fetch_waiter_stats,
    fetch_waiters,
    get_connection,
    update_shift,
    verify_user,
)


app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-change-me")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "authentication required"}), 401
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


@app.get("/health")
def health():
    try:
        with get_connection():
            pass
    except Exception as error:
        return jsonify({"status": "unavailable", "error": str(error)}), 503
    return jsonify({"status": "ok"})


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if session.get("user_id"):
            return redirect(url_for("dashboard"))
        return render_template("login.html", error=None)

    username = request.form.get("username", "")
    password = request.form.get("password", "")
    user = verify_user(username, password)
    if user is None:
        return render_template("login.html", error="Usuario o contraseña incorrectos."), 401

    session["user_id"] = user["id"]
    session["username"] = user["username"]
    next_path = request.args.get("next") or url_for("dashboard")
    return redirect(next_path)


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/")
@login_required
def dashboard():
    return render_template("dashboard.html", username=session.get("username"))


@app.get("/api/tables/latest")
@login_required
def latest_tables():
    try:
        return jsonify(fetch_latest_table_state())
    except Exception as error:
        return jsonify({"error": str(error)}), 503


@app.get("/api/tables/history")
@login_required
def tables_history():
    try:
        hours = int(request.args.get("hours", 3))
    except ValueError:
        return jsonify({"error": "hours must be an integer"}), 400
    hours = min(max(hours, 1), 24)

    try:
        return jsonify(fetch_observation_history(hours=hours))
    except Exception as error:
        return jsonify({"error": str(error)}), 503


@app.get("/schedule")
@login_required
def schedule():
    return render_template("schedule.html", username=session.get("username"))


@app.get("/api/waiters")
@login_required
def list_waiters():
    try:
        return jsonify(fetch_waiters())
    except Exception as error:
        return jsonify({"error": str(error)}), 503


@app.post("/api/waiters")
@login_required
def add_waiter():
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400

    try:
        waiter_id = create_waiter(name)
    except Exception as error:
        return jsonify({"error": str(error)}), 503
    return jsonify({"id": waiter_id, "name": name, "active": True}), 201


@app.get("/api/shift-tables")
@login_required
def list_shift_tables():
    try:
        return jsonify(fetch_tables())
    except Exception as error:
        return jsonify({"error": str(error)}), 503


@app.get("/api/shifts")
@login_required
def list_shifts():
    try:
        start = _parse_datetime(request.args["start"])
        end = _parse_datetime(request.args["end"])
    except (KeyError, ValueError):
        return jsonify({"error": "start and end query params (ISO datetimes) are required"}), 400

    try:
        return jsonify(fetch_shifts(start, end))
    except Exception as error:
        return jsonify({"error": str(error)}), 503


def _shift_payload(body: dict) -> tuple[int, datetime, datetime, list[int]]:
    waiter_id = int(body["waiter_id"])
    starts_at = _parse_datetime(body["starts_at"])
    ends_at = _parse_datetime(body["ends_at"])
    table_ids = [int(table_id) for table_id in body.get("table_ids", [])]
    return waiter_id, starts_at, ends_at, table_ids


@app.post("/api/shifts")
@login_required
def add_shift():
    body = request.get_json(silent=True) or {}
    try:
        waiter_id, starts_at, ends_at, table_ids = _shift_payload(body)
    except (KeyError, ValueError, TypeError):
        return jsonify({"error": "waiter_id, starts_at, ends_at, table_ids are required"}), 400

    if ends_at <= starts_at:
        return jsonify({"error": "ends_at must be after starts_at"}), 400

    try:
        shift_id = create_shift(waiter_id, starts_at, ends_at, table_ids)
    except ScheduleConflict as error:
        return jsonify({"error": str(error)}), 409
    except Exception as error:
        return jsonify({"error": str(error)}), 503
    return jsonify({"id": shift_id}), 201


@app.put("/api/shifts/<int:shift_id>")
@login_required
def edit_shift(shift_id: int):
    body = request.get_json(silent=True) or {}
    try:
        waiter_id, starts_at, ends_at, table_ids = _shift_payload(body)
    except (KeyError, ValueError, TypeError):
        return jsonify({"error": "waiter_id, starts_at, ends_at, table_ids are required"}), 400

    if ends_at <= starts_at:
        return jsonify({"error": "ends_at must be after starts_at"}), 400

    try:
        update_shift(shift_id, waiter_id, starts_at, ends_at, table_ids)
    except ScheduleConflict as error:
        return jsonify({"error": str(error)}), 409
    except Exception as error:
        return jsonify({"error": str(error)}), 503
    return jsonify({"id": shift_id})


@app.delete("/api/shifts/<int:shift_id>")
@login_required
def remove_shift(shift_id: int):
    try:
        delete_shift(shift_id)
    except Exception as error:
        return jsonify({"error": str(error)}), 503
    return "", 204


@app.get("/waiters/stats")
@login_required
def waiter_stats_page():
    return render_template("waiter_stats.html", username=session.get("username"))


@app.get("/api/waiters/stats")
@login_required
def waiter_stats_api():
    now = datetime.now(timezone.utc)
    try:
        start = _parse_datetime(request.args["start"]) if "start" in request.args else now - timedelta(days=7)
        end = _parse_datetime(request.args["end"]) if "end" in request.args else now
    except ValueError:
        return jsonify({"error": "start/end must be ISO datetimes"}), 400

    try:
        return jsonify(fetch_waiter_stats(start, end))
    except Exception as error:
        return jsonify({"error": str(error)}), 503


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
