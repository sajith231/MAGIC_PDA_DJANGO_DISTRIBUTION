# ===============================
# HIDE CONSOLE WINDOW (WINDOWS)
# ===============================
import os
import sys
from tkinter import messagebox
import ctypes
# ===============================
# LOAD CONFIG (DB_DSN)
# ===============================
import json

def load_db_dsn():
    try:
        base = getattr(sys, "_MEIPASS", os.path.dirname(__file__))
        cfg_path = os.path.join(base, "config.json")

        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        return cfg.get("DB_DSN", "NOT SET")
    except Exception:
        return "NOT FOUND"

DB_DSN_NAME = load_db_dsn()


if os.name == "nt":
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)  # 0 = SW_HIDE
    except Exception:
        pass

# ===============================
# SINGLE INSTANCE CHECK (WINDOWS)
# Uses a mutex to detect duplicates.
# Uses a local socket so the 2nd instance
# can tell the 1st to restore its window.
# ===============================
_INSTANCE_PORT = 47832          # arbitrary local port for IPC
_INSTANCE_MAGIC = b"SHOW_WINDOW"

mutex_name = "TASK_PMS_SYNC_TOOL_SINGLE_INSTANCE"
mutex = ctypes.windll.kernel32.CreateMutexW(None, False, mutex_name)
ERROR_ALREADY_EXISTS = 183

if ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
    # ── Another instance is running ──
    # Signal it to restore its window, then exit quietly.
    import socket as _sock
    try:
        s = _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM)
        s.settimeout(1)
        s.connect(("127.0.0.1", _INSTANCE_PORT))
        s.sendall(_INSTANCE_MAGIC)
        s.close()
    except Exception:
        pass

    # Always show the "already running" info box so the user knows.
    import tkinter as _tk
    _r = _tk.Tk()
    _r.withdraw()
    messagebox.showinfo(
        "Already Running",
        "TASK PMS Sync Tool is already running.\n\nThe existing window has been restored."
    )
    _r.destroy()
    sys.exit(0)

# ===============================
# NORMAL IMPORTS (UNCHANGED)
# ===============================
import threading
import tkinter as tk
from tkinter import ttk
import socket
import re
import webbrowser
from datetime import datetime

from PIL import Image, ImageTk
import pystray
import SyncService

PORT = 8000

# ===============================
# IP DETECTION
# ===============================
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

LOCAL_IP = get_local_ip()

# ===============================
# SAFE STDOUT REDIRECTOR
# ===============================
class Redirect:
    def __init__(self, widget, original):
        self.widget = widget
        self.original = original
        self.http = re.compile(r'"(GET|POST)\s+([^"]+)"\s+(\d{3})')

    def write(self, msg):
        if not msg:
            return

        try:
            self.original.write(msg)
        except Exception:
            pass

        if not msg.strip():
            return

        timestamp = datetime.now().strftime("%H:%M:%S")

        if "Starting backend" in msg or "Starting development server" in msg:
            self._log(f"[{timestamp}] 🚀 Starting backend...\n", "info")
            return

        if "Backend running on" in msg or "Starting development server at" in msg:
            self._log(f"[{timestamp}] 🟢 Backend running on http://{LOCAL_IP}:{PORT}\n", "success")
            self.widget.after(500, _on_backend_confirmed_running)
            return

        m = self.http.search(msg)
        if m:
            method, url, code = m.groups()
            code = int(code)
            icon = "✅" if code < 400 else "❌"
            tag = "success" if code < 400 else "error"
            self._log(f"[{timestamp}] {icon} {method} {url} → {code}\n", tag)
            return

        if "✅" in msg:
            self._log(f"[{timestamp}] {msg.strip()}\n", "success")
            return

        if "🔐" in msg or "🚀 Starting" in msg:
            self._log(f"[{timestamp}] {msg.strip()}\n", "info")
            return

        if "ERROR" in msg or "Exception" in msg or "Traceback" in msg or "❌" in msg:
            self._log(f"[{timestamp}] {msg if '❌' in msg else '❌ ' + msg}", "error")

    def flush(self):
        try:
            self.original.flush()
        except Exception:
            pass

    def _log(self, text, tag):
        self.widget.after(0, self.widget.insert, tk.END, text, tag)
        self.widget.after(0, self.widget.see, tk.END)

# ===============================
# AUTO-RESTART EVERY 3 HOURS
# ===============================
AUTO_RESTART_SECONDS = 3 * 60 * 60   # 3 hours

_restart_label   = None   # tk.Label — filled in after GUI is built
_restart_after_id = None  # tk.after handle

def _format_countdown(seconds_left):
    h = seconds_left // 3600
    m = (seconds_left % 3600) // 60
    s = seconds_left % 60
    return f"🔄 Auto-restart in {h:02d}:{m:02d}:{s:02d}"

def _do_process_restart():
    """Hard-restart the whole EXE — cleanest way to reset Django."""
    try:
        import subprocess
        exe = sys.executable          # path to the running .exe (or python)
        args = sys.argv[:]
        subprocess.Popen([exe] + args[1:])
    except Exception:
        pass
    os._exit(0)

def _countdown_tick(seconds_left):
    global _restart_after_id

    if _restart_label:
        try:
            if seconds_left > 0:
                _restart_label.config(text=_format_countdown(seconds_left))
            else:
                _restart_label.config(text="🔄 Restarting now…")
        except Exception:
            pass

    if seconds_left <= 0:
        # Log the restart event
        try:
            ts = datetime.now().strftime("%H:%M:%S")
            log.insert(tk.END,
                f"[{ts}] 🔄 Auto-restart triggered (3-hour cycle)\n", "info")
            log.see(tk.END)
        except Exception:
            pass
        # Give tkinter 600 ms to render the label, then restart
        root.after(600, _do_process_restart)
        return

    _restart_after_id = root.after(1000, _countdown_tick, seconds_left - 1)

def start_auto_restart_timer():
    """Call once after GUI is fully built to begin the countdown."""
    _countdown_tick(AUTO_RESTART_SECONDS)


# ===============================
# BACKEND CONTROL
# ===============================
backend_running = False
status_label = None
status_indicator = None
tray_icon = None  # forward-declared so update_status can reference it safely

def update_status(running):
    """Update status indicator and label"""
    if status_label and status_indicator:
        if running:
            status_indicator.config(bg="#22c55e")
            status_label.config(text="ONLINE", foreground="#22c55e")
            start_btn.config(state="disabled")
            stop_btn.config(state="normal")
            if tray_icon:
                try:
                    tray_icon.title = "TASK PMS Sync Tool — ONLINE"
                except Exception:
                    pass
        else:
            status_indicator.config(bg="#ef4444")
            status_label.config(text="OFFLINE", foreground="#ef4444")
            start_btn.config(state="normal")
            stop_btn.config(state="disabled")
            if tray_icon:
                try:
                    tray_icon.title = "TASK PMS Sync Tool — OFFLINE"
                except Exception:
                    pass

_backend_hide_done = False  # fire only once per session

def _on_backend_confirmed_running():
    """Called from main thread exactly once when Django server is confirmed up."""
    global _backend_hide_done
    if _backend_hide_done:
        return
    _backend_hide_done = True
    root.withdraw()  # silently hide to tray — no popup


def start_backend():
    global backend_running
    if backend_running:
        log.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ Backend already running\n", "info")
        return

    backend_running = True
    update_status(True)
    log.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 Starting backend...\n", "info")

    def run():
        global backend_running
        try:
            SyncService.main()
        except SyncService.CompanyMismatchError as e:
            detail = str(e)
            log.after(0, log.insert, tk.END,
                f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Company/Place verification failed:\n{detail}\n",
                "error")
            log.after(0, log.see, tk.END)
            messagebox.showerror(
                "Company / Place Verification Failed",
                f"❌ The database does not match the registered client info.\n\n{detail}\n\n"
                "Please correct firm_name or address1 in the misel table, then restart."
            )
            backend_running = False
            root.after(0, update_status, False)
        except SystemExit:
            log.insert(
                tk.END,
                f"[{datetime.now().strftime('%H:%M:%S')}] ❌ License validation failed\n❌ Unauthorized client or TASK PMS not enabled\n",
                "error"
            )
            backend_running = False
            update_status(False)
        except Exception as e:
            log.insert(
                tk.END,
                f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Backend crashed: {e}\n",
                "error"
            )
            backend_running = False
            update_status(False)

    threading.Thread(target=run, daemon=True).start()

def stop_backend():
    global backend_running

    if not backend_running:
        messagebox.showinfo(
            "Backend Not Running",
            "The backend is not currently running."
        )
        return

    confirm = messagebox.askokcancel(
        "Stop Backend",
        "Are you sure you want to stop the backend?\n\nAll active connections will be closed."
    )

    if not confirm:
        return

    log.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] 🛑 Stopping backend...\n", "info")
    backend_running = False
    update_status(False)

    # Hard stop (safe for EXE apps)
    os._exit(0)

def clear_logs():
    """Clear the log window"""
    log.delete(1.0, tk.END)
    log.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] 📋 Logs cleared\n", "info")

def copy_url():
    """Copy URL to clipboard"""
    url = f"http://{LOCAL_IP}:{PORT}"
    root.clipboard_clear()
    root.clipboard_append(url)
    messagebox.showinfo("Copied", f"URL copied to clipboard:\n{url}")

# ===============================
# GUI
# ===============================
root = tk.Tk()

# 🔹 Window / Taskbar Icon — use PNG via wm_iconphoto (works reliably in frozen EXE)
try:
    base = getattr(sys, "_MEIPASS", os.path.dirname(__file__))
    _icon_img = Image.open(os.path.join(base, "pms_icone.png")).resize((64, 64), Image.Resampling.LANCZOS)
    _icon_photo = ImageTk.PhotoImage(_icon_img)
    root.wm_iconphoto(True, _icon_photo)
except Exception:
    pass

root.title("TASK PMS Sync Tool - Professional Edition")
root.geometry("1200x700")
root.resizable(True, True)
root.configure(bg="#f8fafc")

# ── Remove MINIMIZE button via Windows API ──
def _remove_minimize_button():
    try:
        GWL_STYLE      = -16
        WS_MINIMIZEBOX = 0x00020000
        hwnd = ctypes.windll.user32.FindWindowW(None, "TASK PMS Sync Tool - Professional Edition")
        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_STYLE, style & ~WS_MINIMIZEBOX)
    except Exception:
        pass

root.after(100, _remove_minimize_button)

# Custom Style
style = ttk.Style()
style.theme_use('clam')

# Configure custom styles
style.configure("Header.TFrame", background="#ffffff")
style.configure("Main.TFrame", background="#f8fafc")
style.configure("Card.TFrame", background="#ffffff", relief="flat")

style.configure("Title.TLabel", background="#ffffff", font=("Segoe UI", 22, "bold"), foreground="#0f172a")
style.configure("Subtitle.TLabel", background="#ffffff", font=("Segoe UI", 11), foreground="#64748b")
style.configure("Status.TLabel", background="#ffffff", font=("Segoe UI", 10, "bold"))
style.configure("Info.TLabel", background="#ffffff", font=("Segoe UI", 10), foreground="#475569")

# Custom button styles
style.configure("Start.TButton", font=("Segoe UI", 10, "bold"), padding=10)
style.configure("Stop.TButton", font=("Segoe UI", 10, "bold"), padding=10)
style.configure("Action.TButton", font=("Segoe UI", 9), padding=8)

style.map("Start.TButton",
          background=[("active", "#16a34a"), ("!disabled", "#22c55e")],
          foreground=[("!disabled", "white")])
style.map("Stop.TButton",
          background=[("active", "#dc2626"), ("!disabled", "#ef4444")],
          foreground=[("!disabled", "white")])

# ===============================
# HEADER SECTION
# ===============================
header = tk.Frame(root, bg="#ffffff", height=140)
header.pack(fill="x", padx=0, pady=0)
header.pack_propagate(False)

# Header content container
header_content = tk.Frame(header, bg="#ffffff")
header_content.pack(fill="both", expand=True, padx=30, pady=20)

# Left side - Logo and Title
left_section = tk.Frame(header_content, bg="#ffffff")
left_section.pack(side="left", fill="y")

# 🔹 App Icon
try:
    base = getattr(sys, "_MEIPASS", os.path.dirname(__file__))
    icon_img = Image.open(os.path.join(base, "pms_icone.png")).resize((48, 48), Image.Resampling.LANCZOS)
    title_icon = ImageTk.PhotoImage(icon_img)
    
    icon_lbl = tk.Label(left_section, image=title_icon, bg="#ffffff")
    icon_lbl.image = title_icon
    icon_lbl.pack(side="left", padx=(0, 15))
except Exception:
    pass

# Title and subtitle
title_container = tk.Frame(left_section, bg="#ffffff")
title_container.pack(side="left")

tk.Label(
    title_container,
    text="TASK PMS SYNC TOOL",
    font=("Segoe UI", 22, "bold"),
    fg="#0f172a",
    bg="#ffffff"
).pack(anchor="w")

tk.Label(
    title_container,
    text="Professional Sync Tool Service",
    font=("Segoe UI", 11),
    fg="#64748b",
    bg="#ffffff"
).pack(anchor="w")

tk.Label(
    title_container,
    text=f"🗄 Database DSN: {DB_DSN_NAME}",
    font=("Segoe UI", 10, "bold"),
    fg="#2563eb",
    bg="#ffffff"
).pack(anchor="w", pady=(4, 0))

# Right side - Status and Controls
right_section = tk.Frame(header_content, bg="#ffffff")
right_section.pack(side="right", fill="y")

# Status Card
status_card = tk.Frame(right_section, bg="#f1f5f9", relief="flat", bd=0)
status_card.pack(side="top", pady=(0, 10))

status_content = tk.Frame(status_card, bg="#f1f5f9")
status_content.pack(padx=20, pady=12)

tk.Label(
    status_content,
    text="STATUS:",
    font=("Segoe UI", 9, "bold"),
    fg="#64748b",
    bg="#f1f5f9"
).pack(side="left", padx=(0, 10))

# Status indicator (colored circle)
status_indicator = tk.Canvas(status_content, width=12, height=12, bg="#f1f5f9", highlightthickness=0)
status_indicator.pack(side="left", padx=(0, 8))
status_indicator.create_oval(2, 2, 12, 12, fill="#ef4444", outline="")

# Status text
status_label = tk.Label(
    status_content,
    text="OFFLINE",
    font=("Segoe UI", 11, "bold"),
    fg="#ef4444",
    bg="#f1f5f9"
)
status_label.pack(side="left")

# Control buttons
btn_container = tk.Frame(right_section, bg="#ffffff")
btn_container.pack(side="top")

start_btn = tk.Button(
    btn_container,
    text="▶  Start Service",
    command=start_backend,
    font=("Segoe UI", 10, "bold"),
    bg="#22c55e",
    fg="white",
    activebackground="#16a34a",
    activeforeground="white",
    relief="flat",
    padx=20,
    pady=10,
    cursor="hand2",
    bd=0
)
start_btn.pack(side="left", padx=(0, 8))

stop_btn = tk.Button(
    btn_container,
    text="■  Stop Service",
    command=stop_backend,
    font=("Segoe UI", 10, "bold"),
    bg="#ef4444",
    fg="white",
    activebackground="#dc2626",
    activeforeground="white",
    relief="flat",
    padx=20,
    pady=10,
    cursor="hand2",
    state="disabled",
    bd=0
)
stop_btn.pack(side="left")

# Separator line
separator = tk.Frame(root, bg="#e2e8f0", height=1)
separator.pack(fill="x")

# ===============================
# MAIN CONTENT AREA
# ===============================
main_content = tk.Frame(root, bg="#f8fafc")
main_content.pack(fill="both", expand=True, padx=30, pady=20)

# Info Cards Row
info_row = tk.Frame(main_content, bg="#f8fafc")
info_row.pack(fill="x", pady=(0, 20))

# Server URL Card
url_card = tk.Frame(info_row, bg="#ffffff", relief="flat", bd=1, highlightbackground="#e2e8f0", highlightthickness=1)
url_card.pack(side="left", fill="both", expand=True, padx=(0, 10))

url_content = tk.Frame(url_card, bg="#ffffff")
url_content.pack(padx=20, pady=15)

tk.Label(
    url_content,
    text="🌐 Server Address",
    font=("Segoe UI", 10, "bold"),
    fg="#475569",
    bg="#ffffff"
).pack(anchor="w")

url_text = tk.Label(
    url_content,
    text=f"http://{LOCAL_IP}:{PORT}",
    font=("Segoe UI", 14, "bold"),
    fg="#2563eb",
    bg="#ffffff"
)
url_text.pack(anchor="w", pady=(5, 0))

# Local IP Card
ip_card = tk.Frame(info_row, bg="#ffffff", relief="flat", bd=1, highlightbackground="#e2e8f0", highlightthickness=1)
ip_card.pack(side="left", fill="both", expand=True)

ip_content = tk.Frame(ip_card, bg="#ffffff")
ip_content.pack(padx=20, pady=15)

tk.Label(
    ip_content,
    text="📡 Local IP Address",
    font=("Segoe UI", 10, "bold"),
    fg="#475569",
    bg="#ffffff"
).pack(anchor="w")

tk.Label(
    ip_content,
    text=LOCAL_IP,
    font=("Segoe UI", 14, "bold"),
    fg="#059669",
    bg="#ffffff"
).pack(anchor="w", pady=(5, 0))

tk.Label(
    ip_content,
    text=f"Port: {PORT}",
    font=("Segoe UI", 9),
    fg="#64748b",
    bg="#ffffff"
).pack(anchor="w", pady=(10, 0))

# ===============================
# LOG AREA
# ===============================
log_container = tk.Frame(main_content, bg="#ffffff", relief="flat", bd=1, highlightbackground="#e2e8f0", highlightthickness=1)
log_container.pack(fill="both", expand=True)

# Log header
log_header = tk.Frame(log_container, bg="#f8fafc", height=45)
log_header.pack(fill="x")
log_header.pack_propagate(False)

log_header_content = tk.Frame(log_header, bg="#f8fafc")
log_header_content.pack(fill="both", padx=15, pady=10)

tk.Label(
    log_header_content,
    text="📊 Server Activity Monitor",
    font=("Segoe UI", 11, "bold"),
    fg="#0f172a",
    bg="#f8fafc"
).pack(side="left")

clear_btn = tk.Button(
    log_header_content,
    text="🗑 Clear Logs",
    command=clear_logs,
    font=("Segoe UI", 9),
    bg="#f1f5f9",
    fg="#475569",
    activebackground="#e2e8f0",
    activeforeground="#475569",
    relief="flat",
    padx=12,
    pady=5,
    cursor="hand2",
    bd=0
)
clear_btn.pack(side="right")

# Log text area with scrollbar
log_frame = tk.Frame(log_container, bg="#0f172a")
log_frame.pack(fill="both", expand=True)

scrollbar = tk.Scrollbar(log_frame)
scrollbar.pack(side="right", fill="y")

log = tk.Text(
    log_frame,
    bg="#0f172a",
    fg="#e2e8f0",
    font=("Consolas", 10),
    wrap="word",
    yscrollcommand=scrollbar.set,
    padx=15,
    pady=10,
    relief="flat",
    insertbackground="#22c55e"
)
log.pack(fill="both", expand=True)
scrollbar.config(command=log.yview)

# Log color tags
log.tag_config("success", foreground="#22c55e", font=("Consolas", 10, "bold"))
log.tag_config("error", foreground="#ef4444", font=("Consolas", 10, "bold"))
log.tag_config("info", foreground="#3b82f6", font=("Consolas", 10))

# Initial log message
log.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] ⚡ TASK PMS Sync Tool initialized\n", "info")
log.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] 📍 Server address: http://{LOCAL_IP}:{PORT}\n", "info")
log.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] ⏳ Waiting for service to start...\n", "info")

# ===============================
# FOOTER
# ===============================
footer = tk.Frame(root, bg="#ffffff", height=70)
footer.pack(fill="x", side="bottom")
footer.pack_propagate(False)

# Top border
footer_border = tk.Frame(footer, bg="#e2e8f0", height=1)
footer_border.pack(fill="x")

footer_content = tk.Frame(footer, bg="#ffffff")
footer_content.pack(expand=True)

def open_site():
    webbrowser.open("https://imcbs.com")

# Logo and text container
branding = tk.Frame(footer_content, bg="#ffffff")
branding.pack()

# Logo
try:
    base = getattr(sys, "_MEIPASS", os.path.dirname(__file__))
    img = Image.open(os.path.join(base, "imcbs_logo.png")).resize((80, 68), Image.Resampling.LANCZOS)
    logo = ImageTk.PhotoImage(img)
    
    logo_lbl = tk.Label(branding, image=logo, cursor="hand2", bg="#ffffff")
    logo_lbl.image = logo
    logo_lbl.pack(side="left", padx=(0, 12))
    logo_lbl.bind("<Button-1>", lambda e: open_site())
except Exception:
    pass

# Branding text
branding_text = tk.Frame(branding, bg="#ffffff")
branding_text.pack(side="left")

text_lbl = tk.Label(
    branding_text,
    text="Powered by IMCBS.COM",
    fg="#2563eb",
    cursor="hand2",
    font=("Segoe UI", 11, "bold"),
    bg="#ffffff"
)
text_lbl.pack()
text_lbl.bind("<Button-1>", lambda e: open_site())

tk.Label(
    branding_text,
    text="© 2026 IMCBS. All rights reserved.",
    font=("Segoe UI", 8),
    fg="#94a3b8",
    bg="#ffffff"
).pack()

# ── Auto-restart countdown label (right side of footer) ──
_restart_label = tk.Label(
    footer_content,
    text=_format_countdown(AUTO_RESTART_SECONDS),
    font=("Segoe UI", 9),
    fg="#94a3b8",
    bg="#ffffff"
)
_restart_label.pack(pady=(4, 0))

# ===============================
# REDIRECT STDOUT SAFELY
# ===============================
_real_stdout = sys.stdout
_real_stderr = sys.stderr

sys.stdout = Redirect(log, _real_stdout)
sys.stderr = Redirect(log, _real_stderr)

# Initialize status
update_status(False)

# ===============================
# SYSTEM TRAY ICON
# ===============================
def create_tray_image():
    """Load pms_icone.png for tray; fallback to plain blue square."""
    try:
        base = getattr(sys, "_MEIPASS", os.path.dirname(__file__))
        img = Image.open(os.path.join(base, "pms_icone.png")).resize((64, 64), Image.Resampling.LANCZOS).convert("RGBA")
        return img
    except Exception:
        img = Image.new("RGBA", (64, 64), color=(37, 99, 235, 255))
        return img

def bring_to_front():
    """Restore and focus the main window (called from any thread)."""
    root.after(0, _do_bring_to_front)

def _do_bring_to_front():
    root.deiconify()
    root.lift()
    root.focus_force()
    # Flash the taskbar button so the user notices
    try:
        root.attributes("-topmost", True)
        root.after(200, lambda: root.attributes("-topmost", False))
    except Exception:
        pass

def show_window(icon, item):
    """Restore main window from tray."""
    bring_to_front()

def quit_app(icon, item):
    """Fully quit the application."""
    icon.stop()
    os._exit(0)

def on_close_to_tray():
    """Hide window to tray when X is clicked — do NOT exit."""
    root.withdraw()

def start_tray():
    """Start tray icon immediately in background thread."""
    global tray_icon
    tray_menu = pystray.Menu(
        pystray.MenuItem("Open TASK PMS Sync", show_window, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", quit_app),
    )
    tray_icon = pystray.Icon(
        "TASK_PMS_SYNC",
        create_tray_image(),
        "TASK PMS Sync Tool",
        tray_menu,
    )
    threading.Thread(target=tray_icon.run, daemon=True).start()

# X button -> hide to tray instead of closing
root.protocol("WM_DELETE_WINDOW", on_close_to_tray)

# Show in system tray immediately when app starts
start_tray()

# ===============================
# IPC LISTENER  ← NEW
# Listens on localhost for a signal from a second instance.
# When received, restores the window to the foreground.
# ===============================
def _ipc_listener():
    """Background thread: accepts one connection, reads magic bytes, restores window."""
    try:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", _INSTANCE_PORT))
        srv.listen(5)
        srv.settimeout(None)          # block forever — daemon thread exits with app
        while True:
            try:
                conn, _ = srv.accept()
                data = conn.recv(64)
                conn.close()
                if data.strip() == _INSTANCE_MAGIC:
                    bring_to_front()
            except Exception:
                pass
    except Exception:
        pass   # port already in use or other error — non-fatal

threading.Thread(target=_ipc_listener, daemon=True).start()

# Kick off the 3-hour auto-restart countdown
start_auto_restart_timer()

root.mainloop()