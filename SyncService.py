#!/usr/bin/env python3
"""
SyncService — freeze-aware Django launcher
Ensures SyncService.exe alias exists for legacy backend calls
"""

import json
import os
import socket
import sys
import shutil
from typing import Tuple


# ----------------------------- helpers ---------------------------------------
def _exe_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _strip_comment(s: str) -> str:
    if not isinstance(s, str):
        return s
    return s.split("#", 1)[0].strip()


def ensure_legacy_exe_alias():
    """
    Create SyncService.exe alias if backend expects it
    """
    if not getattr(sys, "frozen", False):
        return

    exe_dir = _exe_dir()
    current_exe = sys.executable
    legacy_exe = os.path.join(exe_dir, "SyncService.exe")

    if not os.path.exists(legacy_exe):
        try:
            shutil.copy2(current_exe, legacy_exe)
            print("🧩 Created legacy alias: SyncService.exe")
        except Exception as e:
            print(f"⚠️ Could not create SyncService.exe alias: {e}")


# ----------------------------- config ----------------------------------------
def load_config(exe_dir: str) -> dict:
    cfg_path = os.path.join(exe_dir, "config.json")
    if not os.path.isfile(cfg_path):
        print("❌ config.json not found")
        sys.exit(1)

    with open(cfg_path, "r", encoding="utf-8") as f:
        return json.load(f)


# ----------------------------- IP auto-pick ----------------------------------
def ipv4_candidates():
    cands = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        cands.append(s.getsockname()[0])
        s.close()
    except Exception:
        pass

    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip and ip != "127.0.0.1":
                cands.append(ip)
    except Exception:
        pass

    return list(dict.fromkeys(cands))


def select_bind_ip(port: int) -> Tuple[str, list]:
    tried = []
    for ip in ipv4_candidates():
        tried.append(ip)
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind((ip, port))
            s.close()
            return ip, tried
        except Exception:
            pass

    tried.append("0.0.0.0")
    return "0.0.0.0", tried


# ----------------------------- Django setup ----------------------------------
def bootstrap_django(settings: str, proj_root: str):
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", settings)
    if proj_root not in sys.path:
        sys.path.insert(0, proj_root)

    import django
    django.setup()


def apply_migrations():
    from django.core.management import call_command
    call_command("migrate", interactive=False, verbosity=1)


def run_server(bind_ip: str, port: int):
    from django.core.management import call_command
    call_command("runserver", f"{bind_ip}:{port}", use_reloader=False)


# ----------------------------- Main ------------------------------------------
def main():
    exe_dir = _exe_dir()

    # 🔥 IMPORTANT FIX
    ensure_legacy_exe_alias()

    cfg = load_config(exe_dir)

    security = cfg.get("security", {})
    database = cfg.get("database", {})

    os.environ["SECRET_KEY"] = security.get("SECRET_KEY", "")
    os.environ["DEBUG"] = str(security.get("DEBUG", False))
    os.environ["PAIR_PASSWORD"] = security.get("PAIR_PASSWORD", "")
    os.environ["JWT_SECRET"] = security.get("JWT_SECRET", "")
    os.environ["JWT_ALGO"] = security.get("JWT_ALGO", "HS256")

    os.environ["DB_UID"] = database.get("DB_UID", "dba")
    os.environ["DB_PWD"] = database.get("DB_PWD", "")
    os.environ["DB_DSN"] = _strip_comment(database.get("DB_DSN", ""))

    settings_module = cfg.get("settings", "django_sync.settings")
    port = int(cfg.get("port", 8000))

    bootstrap_django(settings_module, exe_dir)

    bind_ip, tried = select_bind_ip(port)

    from datetime import datetime
    import django

    print("🚀 Starting TASK PMS SYNC backend...")
    print(f"🔎 IP tried={tried}, chosen={bind_ip}")
    print("⚙️ Applying migrations...")
    apply_migrations()

    print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print(f"Django {django.get_version()}, settings '{settings_module}'")
    print(f"🟢 Server running at http://{bind_ip}:{port}/")

    run_server(bind_ip, port)


if __name__ == "__main__":
    main()
