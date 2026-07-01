#!/usr/bin/env python3
"""
Servidor web para FreshRSS Embeds.
Lee credenciales de variables de entorno (ver .env.example).
"""

import os
import subprocess
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from flask import Flask, send_from_directory, jsonify

BASE_DIR = Path(__file__).parent
DOCS_DIR = BASE_DIR / "docs"
_venv_python = Path("~/Scripts/python_venv/bin/python").expanduser()
VENV_PYTHON = _venv_python if _venv_python.exists() else Path("python3")

FRESHRSS_SERVER = os.environ.get("FRESHRSS_SERVER", "https://rss.pollete.duckdns.org")
FRESHRSS_USER   = os.environ.get("FRESHRSS_USER", "pollo")
FRESHRSS_PASS   = os.environ.get("FRESHRSS_PASS", "")
FRESHRSS_FEEDS  = os.environ.get(
    "FRESHRSS_FEEDS",
    "Ambientblog,Ban Ban Ton Ton,Depósito sonoro,Lost Turntable,FW Rare Jazz Vinyl Collector",
).split(",")
UPDATE_INTERVAL_DAYS = int(os.environ.get("UPDATE_INTERVAL_DAYS", "7"))
PORT = int(os.environ.get("PORT", "8765"))

app = Flask(__name__)

_lock = threading.Lock()
_status = {
    "running": False,
    "last_update": None,
    "last_error": None,
    "next_update": None,
}


def _do_update():
    with _lock:
        if _status["running"]:
            return
        _status["running"] = True
        _status["last_error"] = None

    try:
        def run(cmd):
            result = subprocess.run(
                cmd,
                cwd=str(BASE_DIR),
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr or result.stdout)

        run([
            str(VENV_PYTHON), "freshrss_html_generator.py",
            "--server", FRESHRSS_SERVER,
            "--username", FRESHRSS_USER,
            "--password", FRESHRSS_PASS,
            "--unread-only",
            "--max-articles", "0",
            "--output-dir", "docs",
            "--feeds", *FRESHRSS_FEEDS,
        ])

        run([
            str(VENV_PYTHON), "freshrss_html_index.py",
            "--input-dir", "docs",
        ])

        _status["last_update"] = datetime.now().isoformat()
    except Exception as e:
        _status["last_error"] = str(e)
    finally:
        _status["running"] = False


def _scheduler():
    interval = UPDATE_INTERVAL_DAYS * 86400
    while True:
        next_run = datetime.now() + timedelta(seconds=interval)
        _status["next_update"] = next_run.isoformat()
        time.sleep(interval)
        threading.Thread(target=_do_update, daemon=True).start()


@app.route("/")
def index():
    return send_from_directory(str(DOCS_DIR), "index.html")


@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(str(DOCS_DIR), filename)


@app.route("/api/update", methods=["POST"])
def api_update():
    if _status["running"]:
        return jsonify({"status": "already_running"}), 409
    threading.Thread(target=_do_update, daemon=True).start()
    return jsonify({"status": "started"})


@app.route("/api/status")
def api_status():
    return jsonify(_status)


if __name__ == "__main__":
    if not FRESHRSS_PASS:
        print("ADVERTENCIA: FRESHRSS_PASS no está configurado. La actualización automática fallará.")

    threading.Thread(target=_scheduler, daemon=True).start()
    print(f"Servidor iniciado en http://0.0.0.0:{PORT}")
    print(f"Actualización automática cada {UPDATE_INTERVAL_DAYS} días")
    app.run(host="0.0.0.0", port=PORT)
