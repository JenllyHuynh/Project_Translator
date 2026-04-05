"""
=============================================================
  gui.py - Overlay Song Ngữ EN/VI, Always on Top (Máy Chính)
=============================================================
  Layout:
  ┌─────────────────────────────────────────────────┐
  │ 🎧 Translator  ● Live  [1510ms]           ◐  ✕ │
  ├─────────────────────────────────────────────────┤
  │ 🇬🇧  Hello everyone, let's begin the meeting... │
  │ 🇻🇳  Xin chào mọi người, hãy bắt đầu họp...   │
  └─────────────────────────────────────────────────┘
=============================================================
"""

import tkinter as tk
from collections import deque
import threading

#  Cấu hình giao diện
MAX_HISTORY   = 3           # Số cặp EN/VI giữ lại
FONT_SIZE_EN  = 15          # Cỡ chữ tiếng Anh (nhỏ hơn chút vì là phụ)
FONT_SIZE_VI  = 16          # Cỡ chữ tiếng Việt (to hơn = đọc chính)
BG_COLOR      = "#111318"   # Nền tối đậm
EN_COLOR      = "#A8B8D0"   # Xanh nhạt — tiếng Anh (phụ)
VI_COLOR      = "#F5F0E8"   # Trắng ấm — tiếng Việt (chính)
HEADER_BG     = "#1E2128"
STATUS_OK     = "#34D399"   # Xanh lá
STATUS_BUSY   = "#FBBF24"   # Vàng
STATUS_ERR    = "#F87171"   # Đỏ
WINDOW_ALPHA  = 0.88
WINDOW_WIDTH  = 860
WINDOW_HEIGHT = 220


class TranslatorOverlay:
    """
    Overlay song ngữ EN + VI.
    - Dòng trên: tiếng Anh gốc (màu nhạt)
    - Dòng dưới: tiếng Việt dịch (màu sáng, to hơn)
    - Thread-safe: mọi update đều dùng root.after()
    """

    def __init__(self):
        self.root = tk.Tk()
        self._lock    = threading.Lock()
        self._en_hist = deque(maxlen=MAX_HISTORY)
        self._vi_hist = deque(maxlen=MAX_HISTORY)
        self._setup_window()
        self._setup_widgets()
        self._setup_drag()

    #  Window setup
    def _setup_window(self):
        r = self.root
        r.overrideredirect(True)           # Ẩn title bar
        r.attributes("-topmost", True)     # Always on top
        r.attributes("-alpha", WINDOW_ALPHA)
        r.configure(bg=BG_COLOR)
        r.wm_attributes("-toolwindow", True)  # Không xuất hiện Taskbar

        sw = r.winfo_screenwidth()
        sh = r.winfo_screenheight()
        x  = (sw - WINDOW_WIDTH) // 2
        y  = sh - WINDOW_HEIGHT - 72      # Cách đáy 72px (trên taskbar)
        r.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}+{x}+{y}")

    #  Widget layout
    def _setup_widgets(self):
        r = self.root

        # Header bar
        self.header = tk.Frame(r, bg=HEADER_BG, height=26)
        self.header.pack(fill="x", side="top")
        self.header.pack_propagate(False)

        tk.Label(
            self.header, text="🎧 Translator",
            bg=HEADER_BG, fg="#5A6478",
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left", padx=10, pady=3)

        # Status dot + text
        self.status_lbl = tk.Label(
            self.header, text="● Chờ kết nối...",
            bg=HEADER_BG, fg="#5A6478",
            font=("Segoe UI", 9),
        )
        self.status_lbl.pack(side="left", padx=4)

        # Ping
        self.ping_lbl = tk.Label(
            self.header, text="",
            bg=HEADER_BG, fg="#3B82F6",
            font=("Segoe UI", 9),
        )
        self.ping_lbl.pack(side="left", padx=6)

        # Nút ✕
        xbtn = tk.Label(
            self.header, text=" ✕ ",
            bg=HEADER_BG, fg="#4A5568",
            font=("Segoe UI", 10, "bold"), cursor="hand2",
        )
        xbtn.pack(side="right", padx=4)
        xbtn.bind("<Button-1>", lambda _: self.quit())
        xbtn.bind("<Enter>",    lambda _: xbtn.configure(fg=STATUS_ERR))
        xbtn.bind("<Leave>",    lambda _: xbtn.configure(fg="#4A5568"))

        # Nút alpha toggle
        self._alpha_hi = False
        abtn = tk.Label(
            self.header, text=" ◐ ",
            bg=HEADER_BG, fg="#4A5568",
            font=("Segoe UI", 10), cursor="hand2",
        )
        abtn.pack(side="right", padx=2)
        abtn.bind("<Button-1>", self._toggle_alpha)

        # Nút clear history
        clr = tk.Label(
            self.header, text=" ⌫ ",
            bg=HEADER_BG, fg="#4A5568",
            font=("Segoe UI", 10), cursor="hand2",
        )
        clr.pack(side="right", padx=2)
        clr.bind("<Button-1>", lambda _: self._clear())
        clr.bind("<Enter>",    lambda _: clr.configure(fg=STATUS_BUSY))
        clr.bind("<Leave>",    lambda _: clr.configure(fg="#4A5568"))

        # Separator
        tk.Frame(r, bg="#2A2F3A", height=1).pack(fill="x")

        # Content area
        content = tk.Frame(r, bg=BG_COLOR, padx=12, pady=8)
        content.pack(fill="both", expand=True)

        # Dòng EN 🇬🇧
        en_row = tk.Frame(content, bg=BG_COLOR)
        en_row.pack(fill="x", anchor="w")

        tk.Label(
            en_row, text="🇬🇧",
            bg=BG_COLOR, font=("Segoe UI", 11),
        ).pack(side="left", anchor="nw", padx=(0, 6))

        self.en_var = tk.StringVar(value="")
        self.en_lbl = tk.Label(
            en_row,
            textvariable=self.en_var,
            bg=BG_COLOR, fg=EN_COLOR,
            font=("Segoe UI", FONT_SIZE_EN),
            wraplength=WINDOW_WIDTH - 60,
            justify="left", anchor="nw",
        )
        self.en_lbl.pack(side="left", fill="x", expand=True)

        # Thin divider giữa 2 ngôn ngữ
        tk.Frame(content, bg="#1E2128", height=1).pack(fill="x", pady=(4, 4))

        # Dòng VI 🇻🇳
        vi_row = tk.Frame(content, bg=BG_COLOR)
        vi_row.pack(fill="x", anchor="w")

        tk.Label(
            vi_row, text="🇻🇳",
            bg=BG_COLOR, font=("Segoe UI", 11),
        ).pack(side="left", anchor="nw", padx=(0, 6))

        self.vi_var = tk.StringVar(value="")
        self.vi_lbl = tk.Label(
            vi_row,
            textvariable=self.vi_var,
            bg=BG_COLOR, fg=VI_COLOR,
            font=("Segoe UI", FONT_SIZE_VI, "bold"),
            wraplength=WINDOW_WIDTH - 60,
            justify="left", anchor="nw",
        )
        self.vi_lbl.pack(side="left", fill="x", expand=True)

    #  Drag to move
    def _setup_drag(self):
        self._dx = self._dy = 0

        def press(e):
            self._dx = e.x_root - self.root.winfo_x()
            self._dy = e.y_root - self.root.winfo_y()

        def drag(e):
            self.root.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

        self.header.bind("<ButtonPress-1>", press)
        self.header.bind("<B1-Motion>",     drag)

    #  Internal helpers
    def _toggle_alpha(self, _=None):
        self._alpha_hi = not self._alpha_hi
        self.root.attributes("-alpha", 0.97 if self._alpha_hi else WINDOW_ALPHA)

    def _clear(self):
        def _do():
            self._en_hist.clear()
            self._vi_hist.clear()
            self.en_var.set("")
            self.vi_var.set("")
        self.root.after(0, _do)

    @staticmethod
    def _trim(text: str, max_len: int = 160) -> str:
        return text[:max_len - 3] + "..." if len(text) > max_len else text

    #  Public API (thread-safe)
    def set_status(self, text: str, color: str = STATUS_OK):
        self.root.after(0, lambda: self.status_lbl.configure(text=text, fg=color))

    def set_ping(self, whisper_ms: int, translate_ms: int, total_ms: int):
        label = f"[🗣 {whisper_ms}ms  🇻🇳 {translate_ms}ms  ⏱ {total_ms}ms]"
        self.root.after(0, lambda: self.ping_lbl.configure(text=label))

    def show_transcript(self, en: str, vi: str, whisper_ms=0, translate_ms=0, total_ms=0):
        """Cập nhật cả 2 dòng EN và VI (thread-safe)."""
        def _update():
            with self._lock:
                if en:
                    self._en_hist.append(self._trim(en))
                if vi:
                    self._vi_hist.append(self._trim(vi))

                self.en_var.set("\n".join(self._en_hist))
                self.vi_var.set("\n".join(self._vi_hist))
                self.set_ping(whisper_ms, translate_ms, total_ms)
                self.set_status("● Live", STATUS_OK)

        self.root.after(0, _update)

    def show_only_en(self, en: str, duration_ms: int = 0):
        """Fallback: chỉ có EN, VI đang chờ hoặc lỗi."""
        def _update():
            with self._lock:
                self._en_hist.append(self._trim(en))
                self.en_var.set("\n".join(self._en_hist))
                self.vi_var.set("đang dịch...")
                self.ping_lbl.configure(text=f"[🗣 {duration_ms}ms]")
                self.set_status("● Đang dịch VI...", STATUS_BUSY)
        self.root.after(0, _update)

    def show_error(self, msg: str):
        self.root.after(0, lambda: self.set_status(f"● {msg}", STATUS_ERR))

    def show_connecting(self):
        self.set_status("● Đang kết nối...", STATUS_BUSY)

    def quit(self):
        self.root.destroy()

    def run(self):
        self.root.mainloop()
