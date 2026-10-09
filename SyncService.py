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
# PRE-LOAD HTTP / SSL STACK
# ===============================
# On a PyInstaller --onefile build these modules live inside base_library.zip in
# the _MEIxxxxxx temp folder. Python's zipimport loads and then CLOSES that zip,
# so antivirus or a temp cleaner can delete it while the app is still running.
# urlopen then fails with "No such file or directory: ...base_library.zip" on its
# next lazy import. Importing the whole stack up-front caches it in sys.modules,
# so the license HTTP calls no longer need to read the zip again at runtime.
try:
    import http.client        # noqa: F401
    import urllib.error       # noqa: F401
    import urllib.parse       # noqa: F401
    import base64             # noqa: F401
    import email              # noqa: F401
    import email.message      # noqa: F401
    import select             # noqa: F401
except Exception:
    pass


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
JWT_EXPIRY_DAYS = 36500

API_URL        = "https://activate.imcbs.com/corporate-clientid/list/"
CLIENT_LIST_URL = "https://activate.imcbs.com/client-id-list/get-client-ids/"


class CompanyMismatchError(Exception):
    """Raised when company_name or place from the API does not match misel table."""
    pass


class ActivationServerUnreachable(Exception):
    """Raised when the activation server cannot be reached (network down, etc.)."""
    pass


class RuntimeFilesMissing(Exception):
    """Raised when bundled runtime files (e.g. base_library.zip) were removed at runtime."""
    pass


def _is_runtime_file_error(exc) -> bool:
    """True when the error is caused by missing bundled _MEI runtime files.

    This happens when antivirus or a temp-file cleaner deletes files inside the
    PyInstaller _MEIxxxxxx extraction folder while the app is still running.
    """
    mei = getattr(sys, "_MEIPASS", None)
    text = str(exc)
    return "base_library.zip" in text or (bool(mei) and mei in text)



def validate_client_id(client_id: str) -> bool:
    """
    Returns True only if client_id exists
    AND project list contains 'TASK PMS'
    Retries 3 times to handle temp folder cleanup issues.
    """
    import time
    client_id = (client_id or "").strip()
    for attempt in range(3):
        try:
            ctx = ssl.create_default_context()
            req = urllib.request.Request(API_URL, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) TASK-PMS/1.0",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
            })
            with urllib.request.urlopen(req, context=ctx, timeout=15) as res:
                payload = json.loads(res.read().decode("utf-8"))
            if not payload.get("success"):
                return False
            for corp in payload.get("data", []):
                for shop in corp.get("shops", []):
                    if (shop.get("client_id") or "").strip() == client_id:
                        return "TASK PMS" in shop.get("projects", [])
            return False
        except Exception as e:
            if _is_runtime_file_error(e):
                # Files are gone for good — retrying cannot fix this.
                raise RuntimeFilesMissing(str(e))
            print(f"⚠️ Attempt {attempt+1} failed: {e}")
            time.sleep(5)
    raise ActivationServerUnreachable("Cannot reach activation server to validate license.")


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
        req = urllib.request.Request(CLIENT_LIST_URL, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) TASK-PMS/1.0"
        })
        with urllib.request.urlopen(req, context=ctx, timeout=10) as res:
            payload = json.loads(res.read().decode("utf-8"))
    except Exception as e:
        if _is_runtime_file_error(e):
            raise RuntimeFilesMissing(str(e))
        raise ActivationServerUnreachable(
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

    return (
        cfg["DB_DSN"],
        (cfg.get("CLIENT_ID") or "").strip(),
        cfg.get("DEBTO", "NO"),
        cfg.get("METHOD", 1),
    )



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
    import time
    db_dsn, client_id, debto, method = load_config()

    print(f"🔧 METHOD = {method}")

    print("🔐 Validating client license...")

    # A transient "no" from the activation server must NOT kill this running
    # process. Keep retrying in the background so the SAME instance self-heals
    # (no need to quit from tray and relaunch).
    LICENSE_RETRY_INTERVAL = 5
    first_license_fail = True

    while True:
        try:
            if validate_client_id(client_id):
                print("✅ Client verified for TASK PMS")

                print("🔐 Verifying company & place against local database...")
                validate_company_info(client_id, db_dsn)
                break

            # Transient failure — report once, then keep retrying.
            if first_license_fail:
                print("❌ License check failed (Invalid client or TASK PMS not enabled)")
                first_license_fail = False
            print("⚠️ License not confirmed yet — retrying in 5s...")
            time.sleep(LICENSE_RETRY_INTERVAL)

        except RuntimeFilesMissing as e:
            # Antivirus / temp cleanup deleted the app's extracted runtime files.
            # Retrying cannot recover them — report clearly and let the GUI stop.
            print("❌ Bundled application files were removed while running.")
            print("   This is usually caused by antivirus or a temp-file cleaner deleting")
            print("   files inside the app's temporary extraction folder.")
            print("   Please restart TASK_PMS and add an antivirus exclusion for the app.")
            raise

        except ActivationServerUnreachable as e:
            print(f"⚠️ Activation server unreachable: {e}")
            print("⏳ Waiting for network and retrying automatically in 15s...")
            time.sleep(15)

    # ── METHOD 2: Discover and switch to second database ──
    if method == 2:
        print("🔄 METHOD 2 — Discovering second database from dba.sounds...")
        try:
            import pyodbc
            from sync.sql_helper import (
                fetch_second_db_info,
                SecondDatabaseConnector,
                set_second_db,
            )

            # 1. Connect to FIRST DB via DSN
            conn_str = f"DSN={db_dsn};UID={DB_UID};PWD={DB_PWD}"
            first_conn = pyodbc.connect(conn_str, autocommit=True, timeout=10)
            print("   ✅ Connected to first DB")

            # 2. Read dba.sounds
            pf, df = fetch_second_db_info(first_conn)
            print(f"   📋 Second DB: pf={pf}, df={df}")

            # 3. Close FIRST DB
            first_conn.close()
            print("   🔒 Closed first DB connection")

            # 4. Connect to SECOND DB
            connector = SecondDatabaseConnector(db_name=pf, db_file_path=df)
            connector.connect()
            print("   ✅ Connected to second DB")

            # 5. Monkey-patch sql_helper to use second DB
            set_second_db(connector)
            print("   🔓 All get_connection() calls now use second DB")

        except Exception as e:
            print(f"❌ METHOD 2 failed: {e}")
            print("   Falling back to first DB (METHOD 1 behavior)")
            # continue with first DB as fallback

    # 🔐 ENVIRONMENT
    os.environ["PAIR_PASSWORD"] = PAIR_PASSWORD
    os.environ["DB_DSN"] = db_dsn
    os.environ["DB_UID"] = DB_UID
    os.environ["DB_PWD"] = DB_PWD
    os.environ["DEBTO"] = debto

    os.environ["SECRET_KEY"] = SECRET_KEY
    os.environ["DEBUG"] = str(DEBUG)
    os.environ["JWT_SECRET"] = JWT_SECRET
    os.environ["JWT_ALGO"] = JWT_ALGO
    # setdefault (not plain assign) so a JWT_EXPIRY_DAYS already present in the
    # operator's environment wins over the built-in default.
    os.environ.setdefault("JWT_EXPIRY_DAYS", str(JWT_EXPIRY_DAYS))

    bootstrap_django()

    ip = select_ip(PORT)

    print("🚀 Starting TASK PMS SYNC backend...")
    apply_migrations()
    print(f"🟢 Backend running on http://{ip}:{PORT}")

    run_server(ip, PORT)


if __name__ == "__main__":
    main()
