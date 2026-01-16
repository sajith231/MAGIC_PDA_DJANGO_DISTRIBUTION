# build.py — AUTO multi-exe packager for TASK PMS SYNC (GUI + SyncService)
import os
import sys
import subprocess
import shutil
import venv

PROJECT_NAME = "TASK_PMS_SYNC"
GUI_ENTRY = "gui_launcher.py"
SERVICE_ENTRY = "SyncService.py"

# Files & folders that MUST travel with the EXE
EXTRA_DATA = [
    ("config.json", "."),
    ("django_sync", "django_sync"),
    ("db.sqlite3", "."),
    ("imcbs_logo.png", "."),
]

REQUIREMENTS = [
    "pyinstaller",
    "Django",
    "psutil",
    "pyjwt",
    "pyodbc",
    "Pillow",
    "djangorestframework",
    "django-cors-headers",
]

DIST_ROOT = f"{PROJECT_NAME.lower()}_dist"
BUILD_DIR = "build"
DIST_DIR = "dist"
VENV_DIR = ".buildvenv"


# -------------------------------------------------
def run(cmd):
    print(">", " ".join(cmd))
    subprocess.run(cmd, check=True)


def ensure_venv():
    if not os.path.isdir(VENV_DIR):
        venv.EnvBuilder(with_pip=True).create(VENV_DIR)

    return (
        os.path.join(VENV_DIR, "Scripts", "python.exe")
        if os.name == "nt"
        else os.path.join(VENV_DIR, "bin", "python")
    )


# -------------------------------------------------
def build():
    py = ensure_venv()

    # Install deps
    run([py, "-m", "pip", "install", "--upgrade", "pip"])
    run([py, "-m", "pip", "install", *REQUIREMENTS])

    # Clean old builds
    for p in (BUILD_DIR, DIST_DIR, DIST_ROOT, f"{PROJECT_NAME}.spec", "SyncService.spec"):
        if os.path.exists(p):
            shutil.rmtree(p, ignore_errors=True) if os.path.isdir(p) else os.remove(p)

    # ---------- ADD DATA ----------
    add_data = []
    sep = ";" if os.name == "nt" else ":"
    for src, dst in EXTRA_DATA:
        if os.path.exists(src):
            add_data += ["--add-data", f"{src}{sep}{dst}"]

    # =================================================
    # 1️⃣ BUILD GUI EXE
    # =================================================
    gui_cmd = [
        py, "-m", "PyInstaller",
        "--onefile",
        "--noconsole",              # ✅ IMPORTANT: NO TERMINAL WINDOW
        f"--name={PROJECT_NAME}",

        # Django hidden imports (REQUIRED)
        "--hidden-import=django.core.management",
        "--hidden-import=django.core.management.commands.runserver",
        "--hidden-import=django.core.management.base",
        "--hidden-import=django.conf",
        "--hidden-import=django.apps",
        "--hidden-import=django.urls",
        "--hidden-import=django.http",

        *add_data,
        GUI_ENTRY,
    ]


    print("\n🚀 Building GUI EXE …")
    run(gui_cmd)

    # =================================================
    # 2️⃣ BUILD SyncService EXE (BACKGROUND WORKER)
    # =================================================
    service_cmd = [
        py, "-m", "PyInstaller",
        "--onefile",
        "--noconsole",
        "--name=SyncService",
        SERVICE_ENTRY,
    ]

    print("\n🚀 Building SyncService EXE …")
    run(service_cmd)

    # =================================================
    # 3️⃣ FINAL DISTRIBUTION FOLDER
    # =================================================
    os.makedirs(DIST_ROOT, exist_ok=True)

    # Copy EXEs
    shutil.copy2(
        os.path.join(DIST_DIR, f"{PROJECT_NAME}.exe"),
        os.path.join(DIST_ROOT, f"{PROJECT_NAME}.exe"),
    )

    shutil.copy2(
        os.path.join(DIST_DIR, "SyncService.exe"),
        os.path.join(DIST_ROOT, "SyncService.exe"),
    )

    # Copy assets + config
    for src, dst in EXTRA_DATA:
        if not os.path.exists(src):
            continue

        target = DIST_ROOT if dst == "." else os.path.join(DIST_ROOT, dst)
        if os.path.isdir(src):
            shutil.copytree(src, target, dirs_exist_ok=True)
        else:
            os.makedirs(target, exist_ok=True)
            shutil.copy2(src, os.path.join(target, os.path.basename(src)))

    print("\n✅ BUILD SUCCESSFUL")
    print("📦 Final folder:", os.path.abspath(DIST_ROOT))
    print("✔ GUI + SyncService bundled correctly")


# -------------------------------------------------
if __name__ == "__main__":
    build()
