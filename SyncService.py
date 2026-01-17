#!/usr/bin/env python3
"""
SyncService — locked backend
PAIR_PASSWORD is HARD-CODED
Only DB_DSN is read from config.json
"""

# ===============================
# HIDE CONSOLE WINDOW (WINDOWS)
# ===============================
import os
import sys
import urllib.request
import ssl

if os.name == "nt":
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
    except Exception:
        pass


# ===============================
# SAFE STDOUT / STDERR FOR --noconsole
# ===============================
if sys.stdout is None:
    class _DummyIO:
        def write(self, *_): 
            pass
        def flush(self): 
            pass

    sys.stdout = _DummyIO()
    sys.stderr = _DummyIO()


# ===============================
# ORIGINAL IMPORTS (UNCHANGED)
# ===============================
import json
import socket
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

API_URL = "https://activate.imcbs.com/corporate-clientid/list/"


def validate_client_id(client_id: str) -> bool:
    """
    Returns True only if client_id exists
    AND project list contains 'TASK PMS'
    """
    try:
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(API_URL, context=ctx, timeout=10) as res:
            payload = json.loads(res.read().decode("utf-8"))

        if not payload.get("success"):
            return False

        for corp in payload.get("data", []):
            for shop in corp.get("shops", []):
                if shop.get("client_id") == client_id:
                    projects = shop.get("projects", [])
                    return "TASK PMS" in projects

        return False

    except Exception as e:
        print(f"❌ Client validation failed: {e}")
        return False



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

    if "DB_DSN" not in cfg or "CLIENT_ID" not in cfg:
        print("❌ config.json must contain DB_DSN and CLIENT_ID")
        sys.exit(1)

    return cfg["DB_DSN"], cfg["CLIENT_ID"]



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
    db_dsn, client_id = load_config()

    print("🔐 Validating client license...")

    if not validate_client_id(client_id):
        print("❌ License check failed (Invalid client or TASK PMS not enabled)")
        sys.exit(1)

    print("✅ Client verified for TASK PMS")

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
