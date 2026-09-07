import os

from flask import Flask, jsonify, render_template

from app.db import fetch_latest_table_state, get_connection


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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
