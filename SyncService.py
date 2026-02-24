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

API_URL        = "https://activate.imcbs.com/corporate-clientid/list/"
CLIENT_LIST_URL = "https://activate.imcbs.com/client-id-list/get-client-ids/"


class CompanyMismatchError(Exception):
    """Raised when company_name or place from the API does not match misel table."""
    pass



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


def validate_company_info(client_id: str, db_dsn: str) -> None:
    """
    Fetches company_name and place for client_id from the activation server
    and cross-checks them against firm_name and address1 in the local misel table.
    Raises CompanyMismatchError with a descriptive message on any mismatch.
    """
    import pyodbc

    # ── 1. Fetch client list from activation server ──────────────────
    try:
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(CLIENT_LIST_URL, context=ctx, timeout=10) as res:
            payload = json.loads(res.read().decode("utf-8"))
    except Exception as e:
        raise CompanyMismatchError(
            f"Cannot reach activation server to verify company info.\n\nDetails: {e}"
        )

    if not payload.get("status"):
        raise CompanyMismatchError(
            "Activation server returned an error response during company verification."
        )

    # Find this client's entry
    api_company = None
    api_place   = None
    for entry in payload.get("data", []):
        if entry.get("client_id") == client_id:
            api_company = (entry.get("company_name") or "").strip()
            api_place   = (entry.get("place") or "").strip()
            break

    if api_company is None:
        raise CompanyMismatchError(
            f"Client ID '{client_id}' was not found in the activation server client list."
        )

    # ── 2. Read firm_name and address1 from local misel table ────────
    try:
        conn_str = f"DSN={db_dsn};UID={DB_UID};PWD={DB_PWD}"
        conn = pyodbc.connect(conn_str, autocommit=True, timeout=10)
        cur  = conn.cursor()
        cur.execute("SELECT firm_name, address1 FROM DBA.misel")
        row = cur.fetchone()
        cur.close()
        conn.close()
    except Exception as e:
        raise CompanyMismatchError(
            f"Cannot read misel table from local database.\n\nDetails: {e}"
        )

    if row is None:
        raise CompanyMismatchError("The misel table is empty in the local database.")

    db_firm_name = (row[0] or "").strip()
    db_address1  = (row[1] or "").strip()

    # ── 3. Compare (case-insensitive) ────────────────────────────────
    name_match  = api_company.lower() == db_firm_name.lower()
    place_match = api_place.lower()   == db_address1.lower()

    if not name_match and not place_match:
        raise CompanyMismatchError(
            f"COMPANY NAME & PLACE MISMATCH\n\n"
            f"  API company_name : {api_company}\n"
            f"  DB  firm_name    : {db_firm_name}\n\n"
            f"  API place        : {api_place}\n"
            f"  DB  address1     : {db_address1}"
        )
    elif not name_match:
        raise CompanyMismatchError(
            f"COMPANY NAME MISMATCH\n\n"
            f"  API company_name : {api_company}\n"
            f"  DB  firm_name    : {db_firm_name}"
        )
    elif not place_match:
        raise CompanyMismatchError(
            f"PLACE MISMATCH\n\n"
            f"  API place    : {api_place}\n"
            f"  DB  address1 : {db_address1}"
        )

    print(f"✅ Company info verified — '{db_firm_name}' / '{db_address1}'")



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

    print("🔐 Verifying company & place against local database...")
    validate_company_info(client_id, db_dsn)

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
