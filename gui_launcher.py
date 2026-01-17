# ===============================
# HIDE CONSOLE WINDOW (WINDOWS)
# ===============================
import os
import sys
from tkinter import messagebox
import ctypes




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
# ===============================
mutex_name = "TASK_PMS_SYNC_TOOL_SINGLE_INSTANCE"

mutex = ctypes.windll.kernel32.CreateMutexW(
    None, False, mutex_name
)

ERROR_ALREADY_EXISTS = 183

if ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
    messagebox.showinfo(
        "Already Running",
        "TASK PMS Sync Tool is already running.\n\nPlease check the existing window."
    )
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

        try:
            self.original.write(msg)
        except Exception:
            pass

        if not msg.strip():
            return

        if "Starting backend" in msg or "Starting development server" in msg:
            self._log("🚀 Starting backend...\n", "info")
            return

        if "Backend running on" in msg or "Starting development server at" in msg:
            self._log(f"🟢 Backend running on http://{LOCAL_IP}:{PORT}\n", "success")
            return

        m = self.http.search(msg)
        if m:
            method, url, code = m.groups()
            code = int(code)
            icon = "✅" if code < 400 else "❌"
            tag = "success" if code < 400 else "error"
            self._log(f"{icon} {method} {url} → {code}\n", tag)
            return

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
        global backend_running
        try:
            SyncService.main()

        except SystemExit:
            log.insert(
                tk.END,
                "❌ License validation failed\n❌ Unauthorized client or TASK PMS not enabled\n",
                "error"
            )
            backend_running = False

        except Exception as e:
            log.insert(
                tk.END,
                f"❌ Backend crashed: {e}\n",
                "error"
            )
            backend_running = False


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

    log.insert(tk.END, "🛑 Stopping backend...\n", "info")
    backend_running = False

    # Hard stop (safe for EXE apps)
    os._exit(0)




# ===============================
# GUI
# ===============================
root = tk.Tk()

# 🔹 Window / Taskbar Icon
try:
    base = getattr(sys, "_MEIPASS", os.path.dirname(__file__))
    root.iconbitmap(os.path.join(base, "pms_icone.ico"))
except Exception:
    pass

root.title("TASK PMS SYNC TOOL")
root.geometry("1000x600")
root.resizable(True, True)


# ===============================
# HEADER
# ===============================
header = ttk.Frame(root)
header.pack(fill="x", padx=10, pady=8)


# ===============================
# HEADER ICON + TITLE + RUNNING IP
# ===============================
title_frame = ttk.Frame(header)
title_frame.pack(side="left")

# 🔹 App Icon (inside UI)
try:
    base = getattr(sys, "_MEIPASS", os.path.dirname(__file__))
    icon_img = Image.open(os.path.join(base, "pms_icone.png")).resize((36, 36))
    title_icon = ImageTk.PhotoImage(icon_img)

    icon_lbl = tk.Label(title_frame, image=title_icon)
    icon_lbl.image = title_icon
    icon_lbl.pack(side="left", padx=(0, 10))
except Exception:
    pass

# 🔹 App Title
ttk.Label(
    title_frame,
    text="TASK PMS SYNC TOOL",
    font=("Segoe UI", 18, "bold")
).pack(side="left")

# 🔹 RUNNING IP (BIG & CLEAR)
ttk.Label(
    title_frame,
    text=f"Running on: http://{LOCAL_IP}:{PORT}",
    font=("Segoe UI", 12, "bold"),
    foreground="#16a34a"  # green
).pack(side="left", padx=(20, 0))


# ===============================
# HEADER BUTTONS (RIGHT)
# ===============================
btn_frame = ttk.Frame(header)
btn_frame.pack(side="right")

start_btn = ttk.Button(
    btn_frame,
    text="▶ Start Backend",
    command=start_backend
)
start_btn.pack(side="left", padx=(0, 8))

stop_btn = ttk.Button(
    btn_frame,
    text="■ Stop Backend",
    command=stop_backend
)
stop_btn.pack(side="left")


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
# FOOTER (CENTERED – LOGO LEFT, TEXT RIGHT)
# ===============================
footer = ttk.Frame(root)
footer.pack(fill="x", pady=6)

# center container
footer_center = ttk.Frame(footer)
footer_center.pack(expand=True)

def open_site():
    webbrowser.open("https://imcbs.com")

# Logo (LEFT)
try:
    base = getattr(sys, "_MEIPASS", os.path.dirname(__file__))
    img = Image.open(os.path.join(base, "imcbs_logo.png")).resize((106, 90))
    logo = ImageTk.PhotoImage(img)

    logo_lbl = tk.Label(footer_center, image=logo, cursor="hand2")
    logo_lbl.image = logo
    logo_lbl.pack(side="left", padx=(0, 6))
    logo_lbl.bind("<Button-1>", lambda e: open_site())
except Exception:
    pass

# Text (RIGHT of logo)
text_lbl = tk.Label(
    footer_center,
    text="Powered by IMCBS.COM",
    fg="#2563eb",
    cursor="hand2",
    font=("Segoe UI", 10, "bold")
)
text_lbl.pack(side="left")
text_lbl.bind("<Button-1>", lambda e: open_site())


# ===============================
# REDIRECT STDOUT SAFELY
# ===============================
_real_stdout = sys.stdout
_real_stderr = sys.stderr

sys.stdout = Redirect(log, _real_stdout)
sys.stderr = Redirect(log, _real_stderr)

root.mainloop()
