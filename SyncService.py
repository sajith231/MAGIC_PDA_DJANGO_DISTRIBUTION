#!/usr/bin/env python3
"""
SyncService — locked backend
PAIR_PASSWORD is HARD-CODED
Only DB_DSN is read from config.json
"""

import json
import os
import socket
import sys
import shutil
from typing import Tuple

# ===============================
# HARD LOCKED CONSTANTS
# ===============================
DJANGO_SETTINGS_MODULE = "django_sync.settings"
PORT = 8000

PAIR_PASSWORD = "IMC-MOBILE"   # 🔒 HARD CODED (PAIRING FIX)

DB_UID = "dba"
DB_PWD = "(*$^)"

SECRET_KEY = "super-secret-change-me"
DEBUG = False

JWT_SECRET = "SyncAnywhereJWTSecret2025"
JWT_ALGO = "HS256"


# ===============================
# Helpers
# ===============================
def exe_dir():
    return os.path.dirname(sys.executable if getattr(sys, "frozen", False) else __file__)


def load_config():
    path = os.path.join(exe_dir(), "config.json")
    if not os.path.exists(path):
        print("❌ config.json not found")
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    if "DB_DSN" not in cfg:
        print("❌ config.json must contain DB_DSN")
        sys.exit(1)

    return cfg["DB_DSN"]


def select_ip(port):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "0.0.0.0"


# ===============================
# Django
# ===============================
def bootstrap_django():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", DJANGO_SETTINGS_MODULE)
    sys.path.insert(0, exe_dir())
    import django
    django.setup()


def apply_migrations():
    from django.core.management import call_command
    call_command("migrate", interactive=False, verbosity=0)


def run_server(ip, port):
    from django.core.management import call_command
    call_command("runserver", f"{ip}:{port}", use_reloader=False)


# ===============================
# MAIN
# ===============================
def main():
    db_dsn = load_config()

    # 🔐 ENVIRONMENT
    os.environ["PAIR_PASSWORD"] = PAIR_PASSWORD
    os.environ["DB_DSN"] = db_dsn
    os.environ["DB_UID"] = DB_UID
    os.environ["DB_PWD"] = DB_PWD

    os.environ["SECRET_KEY"] = SECRET_KEY
    os.environ["DEBUG"] = str(DEBUG)
    os.environ["JWT_SECRET"] = JWT_SECRET
    os.environ["JWT_ALGO"] = JWT_ALGO

    bootstrap_django()

    ip = select_ip(PORT)

    print("🚀 Starting TASK PMS SYNC backend...")
    apply_migrations()
    print(f"🟢 Backend running on http://{ip}:{PORT}")

    run_server(ip, PORT)


if __name__ == "__main__":
    main()
