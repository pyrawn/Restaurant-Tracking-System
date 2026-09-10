import os

from flask import Flask, jsonify, render_template, request

from app.db import fetch_latest_table_state, fetch_observation_history, get_connection


app = Flask(__name__)


@app.get("/health")
def health():
    try:
        with get_connection():
            pass
    except Exception as error:
        return jsonify({"status": "unavailable", "error": str(error)}), 503
    return jsonify({"status": "ok"})


@app.get("/")
def dashboard():
    return render_template("dashboard.html")


@app.get("/api/tables/latest")
def latest_tables():
    try:
        return jsonify(fetch_latest_table_state())
    except Exception as error:
        return jsonify({"error": str(error)}), 503


@app.get("/api/tables/history")
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
