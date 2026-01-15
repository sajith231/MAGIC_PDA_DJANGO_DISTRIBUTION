# build.py — one-click packager for TASK PMS SYNC (GUI only)
import os, sys, subprocess, shutil, venv

PROJECT_NAME = "TASK_PMS_SYNC"
ENTRY_SCRIPT = "gui_launcher.py"

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
    "djangorestframework-simplejwt",
    "django-cors-headers",
]

DIST_ROOT = f"{PROJECT_NAME.lower()}_dist"
BUILD_DIR = "build"
DIST_DIR = "dist"
VENV_DIR = ".buildvenv"


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


def build():
    py = ensure_venv()

    run([py, "-m", "pip", "install", "--upgrade", "pip"])
    run([py, "-m", "pip", "install", *REQUIREMENTS])

    for p in (BUILD_DIR, DIST_DIR, DIST_ROOT, f"{PROJECT_NAME}.spec"):
        if os.path.exists(p):
            shutil.rmtree(p, ignore_errors=True) if os.path.isdir(p) else os.remove(p)

    add_data = []
    sep = ";" if os.name == "nt" else ":"
    for src, dst in EXTRA_DATA:
        if os.path.exists(src):
            add_data += ["--add-data", f"{src}{sep}{dst}"]

    cmd = [
        py, "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        f"--name={PROJECT_NAME}",
        *add_data,
        ENTRY_SCRIPT
    ]

    print("\n🚀 Building EXE …")
    run(cmd)

    os.makedirs(DIST_ROOT, exist_ok=True)
    exe = f"{PROJECT_NAME}.exe"
    shutil.copy2(os.path.join(DIST_DIR, exe), os.path.join(DIST_ROOT, exe))

    for src, dst in EXTRA_DATA:
        if not os.path.exists(src):
            continue

        target = DIST_ROOT if dst == "." else os.path.join(DIST_ROOT, dst)

        if os.path.isdir(src):
            shutil.copytree(src, target, dirs_exist_ok=True)
        else:
            os.makedirs(target, exist_ok=True)
            shutil.copy2(src, os.path.join(target, os.path.basename(src)))

    print(f"\n✅ Build completed: {os.path.abspath(DIST_ROOT)}")


if __name__ == "__main__":
    build()
