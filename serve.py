#!/usr/bin/env python3
"""
Servidor web para FreshRSS Embeds.
Lee credenciales de variables de entorno (ver .env.example).
"""

import os
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from flask import Flask, send_from_directory, jsonify, request

import freshrss_db

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
PORT = int(os.environ.get("PORT", "8765"))

app = Flask(__name__)

# ── Panel de configuración (⚙) ───────────────────────────────────────────────
# Mismo patrón que el resto de apps. Los cambios en FRESHRSS_* necesitan
# reiniciar el contenedor (se leen una vez al arrancar, como aquí arriba). La
# frecuencia de actualización la fija el cron de Ofelia en docker-compose.yml,
# no una variable aquí.
SETTINGS_ENV_PATH = BASE_DIR / ".env"
SETTINGS_PASSWORD = os.environ.get("SETTINGS_PASSWORD", "")
VARS_SPEC = [
    {"name": "FRESHRSS_SERVER", "secret": False, "help": "URL del servidor FreshRSS"},
    {"name": "FRESHRSS_USER", "secret": False, "help": "Usuario de FreshRSS"},
    {"name": "FRESHRSS_PASS", "secret": True, "help": "Contraseña de FreshRSS"},
    {"name": "FRESHRSS_FEEDS", "secret": False, "help": "Feeds a incluir, separados por coma"},
    {"name": "GH_PAT", "secret": True, "help": "Token de GitHub (fine-grained, contents:write sobre este repo) para publicar docs/ automáticamente"},
]
_HAS_SECRETS = any(v.get("secret") for v in VARS_SPEC)


def _read_env_file(path):
    values = {}
    if not os.path.exists(path):
        return values
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
                v = v[1:-1]
            values[k.strip()] = v
    return values


def _shell_quote_env_value(v):
    # publish_docs.sh hace "source .env"; sin comillas, un valor con "$algo"
    # (p.ej. una contraseña con ese substring literal) se intenta expandir
    # como variable y revienta el propio "source" con "set -u" activo.
    # Comillas simples evitan además cualquier otra expansión al hacer source.
    if v == "":
        return "''"
    return "'" + v.replace("'", "'\\''") + "'"


def _write_env_file(path, updates):
    lines = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    seen = set()
    out = []
    for line in lines:
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            k = s.split("=", 1)[0].strip()
            if k in updates:
                out.append(f"{k}={_shell_quote_env_value(updates[k])}\n")
                seen.add(k)
                continue
        out.append(line)
    for k, v in updates.items():
        if k not in seen:
            if out and not out[-1].endswith("\n"):
                out[-1] += "\n"
            out.append(f"{k}={_shell_quote_env_value(v)}\n")
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(out)


def _current_value(spec):
    file_vals = _read_env_file(SETTINGS_ENV_PATH)
    if spec["name"] in file_vals:
        return file_vals[spec["name"]]
    return os.environ.get(spec["name"], spec.get("default", ""))


def _check_auth(password):
    if not SETTINGS_PASSWORD:
        return not _HAS_SECRETS
    return password == SETTINGS_PASSWORD


@app.route("/api/settings", methods=["POST"])
def api_settings():
    d = request.get_json(silent=True) or {}
    password = d.get("password") or ""
    requires = bool(SETTINGS_PASSWORD) or _HAS_SECRETS
    authorized = _check_auth(password)
    if requires and not authorized:
        error = "Contraseña incorrecta" if password else None
        if not SETTINGS_PASSWORD:
            error = "Este servicio tiene credenciales pero no hay SETTINGS_PASSWORD configurada. Añádela al .env y reinicia el contenedor."
        return jsonify({"requires_password": True, "authorized": False, "error": error})
    vars_out = [
        {"name": v["name"], "value": _current_value(v), "secret": v["secret"], "help": v.get("help", "")}
        for v in VARS_SPEC
    ]
    return jsonify({"requires_password": requires, "authorized": True, "vars": vars_out})


@app.route("/api/settings/save", methods=["POST"])
def api_settings_save():
    d = request.get_json(silent=True) or {}
    if not _check_auth(d.get("password") or ""):
        return jsonify({"error": "Contraseña incorrecta"}), 403
    known = {v["name"] for v in VARS_SPEC}
    updates = {k: v for k, v in (d.get("values") or {}).items() if k in known}
    if not updates:
        return jsonify({"error": "Nada que guardar"}), 400
    _write_env_file(SETTINGS_ENV_PATH, updates)
    return jsonify({"ok": True, "message": "Guardado. Reinicia el contenedor para aplicar los cambios."})

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


@app.route("/api/listened", methods=["POST"])
def api_listened():
    d = request.get_json(silent=True) or {}
    item_id = d.get("id")
    if not item_id:
        return jsonify({"ok": False, "error": "id requerido"}), 400
    freshrss_db.mark_listened(item_id)
    # Regenera solo desde lo que ya hay en docs/ (freshrss_regen_local.py),
    # sin tocar la red -- antes esto reusaba el mismo flujo que /api/update
    # (refetch completo de todos los feeds contra FreshRSS), que puede
    # tardar varios minutos solo para ocultar un ítem ya descargado. Se
    # ejecuta síncrono (no en background) porque sin red es cuestión de
    # segundos, así que la respuesta ya refleja el estado final real.
    try:
        result = subprocess.run(
            [str(VENV_PYTHON), "freshrss_regen_local.py", "--output-dir", "docs"],
            cwd=str(BASE_DIR), capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            return jsonify({"ok": True, "warning": f"marcado, pero falló la regeneración local: {result.stderr}"})
    except Exception as e:
        return jsonify({"ok": True, "warning": f"marcado, pero falló la regeneración local: {e}"})
    return jsonify({"ok": True})


if __name__ == "__main__":
    if not FRESHRSS_PASS:
        print("ADVERTENCIA: FRESHRSS_PASS no está configurado. La actualización automática fallará.")

    # La actualización periódica la dispara Ofelia (ofelia.job-exec.freshrss-update
    # en docker-compose.yml), no un scheduler interno — mismo patrón que el resto.
    print(f"Servidor iniciado en http://0.0.0.0:{PORT}")
    app.run(host="0.0.0.0", port=PORT)
