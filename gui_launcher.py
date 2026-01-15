# ===============================
# HIDE CONSOLE WINDOW (WINDOWS)
# ===============================
import os
import sys

if os.name == "nt":
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)  # 0 = SW_HIDE
    except Exception:
        pass


# ===============================
# NORMAL IMPORTS (UNCHANGED)
# ===============================
import threading
import tkinter as tk
from tkinter import ttk
import socket
import re
import webbrowser

from PIL import Image, ImageTk
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

        # Always forward to real stdout
        try:
            self.original.write(msg)
        except Exception:
            pass

        if not msg.strip():
            return

        # Backend start
        if "Starting backend" in msg or "Starting development server" in msg:
            self._log("🚀 Starting backend...\n", "info")
            return

        if "Backend running on" in msg or "Starting development server at" in msg:
            self._log(f"🟢 Backend running on http://{LOCAL_IP}:{PORT}\n", "success")
            return

        # HTTP log parsing (SHOW URL)
        m = self.http.search(msg)
        if m:
            method, url, code = m.groups()
            code = int(code)
            icon = "✅" if code < 400 else "❌"
            tag = "success" if code < 400 else "error"
            self._log(f"{icon} {method} {url} → {code}\n", tag)
            return

        # Errors
        if "ERROR" in msg or "Exception" in msg or "Traceback" in msg:
            self._log(f"❌ {msg}", "error")

    def flush(self):
        try:
            self.original.flush()
        except Exception:
            pass

    def _log(self, text, tag):
        self.widget.after(0, self.widget.insert, tk.END, text, tag)
        self.widget.after(0, self.widget.see, tk.END)


# ===============================
# BACKEND CONTROL
# ===============================
backend_running = False


def start_backend():
    global backend_running
    if backend_running:
        log.insert(tk.END, "⚠️ Backend already running\n", "info")
        return

    backend_running = True
    log.insert(tk.END, "🚀 Starting backend...\n", "info")

    def run():
        try:
            SyncService.main()
        except Exception as e:
            log.insert(tk.END, f"❌ Backend crashed: {e}\n", "error")

    threading.Thread(target=run, daemon=True).start()


# ===============================
# GUI
# ===============================
root = tk.Tk()
root.title("TASK PMS SYNC TOOL")
root.geometry("1000x600")
root.resizable(True, True)

# Header
header = ttk.Frame(root)
header.pack(fill="x", padx=10, pady=8)

ttk.Label(
    header,
    text="TASK PMS SYNC TOOL",
    font=("Segoe UI", 18, "bold")
).pack(side="left")

ttk.Button(
    header,
    text="Start Backend",
    command=start_backend
).pack(side="right")


# ===============================
# LOG AREA
# ===============================
box = ttk.LabelFrame(root, text="Server Activity")
box.pack(fill="both", expand=True, padx=10, pady=8)

log = tk.Text(
    box,
    bg="#0b1220",
    fg="#e5e7eb",
    font=("Consolas", 10),
    wrap="word"
)
log.pack(fill="both", expand=True)

log.tag_config("success", foreground="#22c55e")
log.tag_config("error", foreground="#ef4444")
log.tag_config("info", foreground="#38bdf8")


# ===============================
# FOOTER (UNCHANGED)
# ===============================
footer = ttk.Frame(root)
footer.pack(fill="x", pady=4)

ttk.Label(
    footer,
    text=f"● Backend running on {LOCAL_IP}:{PORT}",
    foreground="green"
).pack(side="left", padx=8)


def open_site():
    webbrowser.open("https://imcbs.com")


try:
    base = getattr(sys, "_MEIPASS", os.path.dirname(__file__))
    img = Image.open(os.path.join(base, "imcbs_logo.png")).resize((40, 36))
    logo = ImageTk.PhotoImage(img)
    lbl = tk.Label(footer, image=logo, cursor="hand2")
    lbl.image = logo
    lbl.pack(side="right", padx=6)
    lbl.bind("<Button-1>", lambda e: open_site())
except:
    pass

tk.Label(
    footer,
    text="Powered by IMCBS.COM",
    fg="#2563eb",
    cursor="hand2"
).pack(side="right")


# ===============================
# REDIRECT STDOUT SAFELY
# ===============================
_real_stdout = sys.stdout
_real_stderr = sys.stderr

sys.stdout = Redirect(log, _real_stdout)
sys.stderr = Redirect(log, _real_stderr)

root.mainloop()
