import threading
import tkinter as tk
from tkinter import ttk, messagebox
import sys
import re
import socket
import os
import webbrowser

from PIL import Image, ImageTk

import SyncService  # backend entry


# ===============================
# Get real local IP
# ===============================
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


LOCAL_IP = get_local_ip()
PORT = 8000


# ===============================
# Redirect stdout / stderr
# ===============================
class TextRedirector:
    def __init__(self, text_widget):
        self.text_widget = text_widget
        self.request_patterns = [
            re.compile(r'"(GET|POST|PUT|DELETE|PATCH) (.*?) HTTP/[\d.]+" (\d{3})'),
            re.compile(r'\] "(GET|POST|PUT|DELETE|PATCH) (.*?) HTTP/[\d.]+" (\d{3})')
        ]

    def write(self, msg):
        if not msg.strip():
            return

        if "Server running at" in msg:
            self._write(
                f"🟢 Server running at http://{LOCAL_IP}:{PORT}/\n",
                "info"
            )
            return

        for pattern in self.request_patterns:
            match = pattern.search(msg)
            if match:
                method, url, status = match.groups()
                status = int(status)
                icon = "✅" if status < 400 else "❌"
                tag = "success" if status < 400 else "error"
                self._write(
                    f"{method:<6} {url:<30} {icon} ({status})\n",
                    tag
                )
                return

        if "error" in msg.lower() or "exception" in msg.lower():
            self._write(msg, "error")

    def _write(self, text, tag):
        self.text_widget.after(0, self.text_widget.insert, tk.END, text, tag)
        self.text_widget.after(0, self.text_widget.see, tk.END)

    def flush(self):
        pass


# ===============================
# Backend Runner
# ===============================
def start_backend():
    try:
        SyncService.main()
    except Exception as e:
        log_text.insert(
            tk.END,
            f"\n❌ Backend crashed: {e}\n",
            "error"
        )


def run_backend_thread():
    if backend_running.get():
        messagebox.showinfo("Info", "Backend already running")
        return

    backend_running.set(True)
    log_text.insert(
        tk.END,
        "🚀 Starting TASK PMS SYNC backend...\n",
        "info"
    )

    threading.Thread(target=start_backend, daemon=True).start()


# ===============================
# GUI Setup
# ===============================
root = tk.Tk()
root.title("TASK PMS SYNC TOOL")
root.geometry("950x550")
root.resizable(True, True)

backend_running = tk.BooleanVar(value=False)


# ===============================
# Header
# ===============================
header = ttk.Frame(root)
header.pack(fill="x", padx=12, pady=10)

ttk.Label(
    header,
    text="TASK PMS SYNC TOOL",
    font=("Segoe UI", 18, "bold")
).pack(side="left")

ttk.Button(
    header,
    text="Start Backend",
    command=run_backend_thread
).pack(side="right")


# ===============================
# Log Area
# ===============================
log_frame = ttk.LabelFrame(root, text="Server Activity")
log_frame.pack(fill="both", expand=True, padx=12, pady=10)

log_text = tk.Text(
    log_frame,
    bg="#0b1220",
    fg="#e5e7eb",
    insertbackground="white",
    font=("Consolas", 10),
    wrap="word"
)
log_text.pack(fill="both", expand=True)

scrollbar = ttk.Scrollbar(log_text, command=log_text.yview)
log_text.configure(yscrollcommand=scrollbar.set)
scrollbar.pack(side="right", fill="y")

log_text.tag_config("success", foreground="#22c55e")
log_text.tag_config("error", foreground="#ef4444")
log_text.tag_config("info", foreground="#38bdf8")


# ===============================
# Footer (FULL LOGO VISIBLE + CENTERED)
# ===============================
footer = ttk.Frame(root, height=130)   # 🔥 HEIGHT FIX
footer.pack(fill="x")
footer.pack_propagate(False)           # 🔥 PREVENT CLIPPING


def open_imcbs():
    webbrowser.open("https://imcbs.com")

def load_logo():
    try:
        base = getattr(sys, "_MEIPASS", os.path.dirname(__file__))
        logo_path = os.path.join(base, "imcbs_logo.png")
        img = Image.open(logo_path)
        img = img.resize((110, 100))   # ❗UNCHANGED SIZE
        return ImageTk.PhotoImage(img)
    except Exception as e:
        print("Logo load error:", e)
        return None


# ---- CENTER BLOCK (ABSOLUTE CENTER) ----
center_block = ttk.Frame(footer)
center_block.place(relx=0.5, rely=0.5, anchor="center")

logo_img = load_logo()

if logo_img:
    logo_lbl = tk.Label(center_block, image=logo_img, cursor="hand2")
    logo_lbl.image = logo_img
    logo_lbl.pack(side="left", padx=(0, 12))
    logo_lbl.bind("<Button-1>", lambda e: open_imcbs())

power_lbl = tk.Label(
    center_block,
    text="Powered by IMCBS.COM",
    font=("Segoe UI", 11, "bold"),
    fg="#2563eb",
    cursor="hand2"
)
power_lbl.pack(side="left")
power_lbl.bind("<Button-1>", lambda e: open_imcbs())


# ---- STATUS (LEFT, DOES NOT AFFECT CENTER) ----
status_lbl = ttk.Label(
    footer,
    text=f"● Backend running on {LOCAL_IP}:{PORT}",
    foreground="green"
)
status_lbl.place(x=12, y=footer.winfo_reqheight() - 28)


# ===============================
# Redirect stdout / stderr
# ===============================
sys.stdout = TextRedirector(log_text)
sys.stderr = TextRedirector(log_text)


# ===============================
# Start GUI
# ===============================
root.mainloop()
