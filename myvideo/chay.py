# -*- coding: utf-8 -*-
"""Bật myvideo — bản WEB (rút gọn từ myvoice/chay.py, cùng cách vận hành).

    python myvideo/chay.py            → cửa sổ nhỏ: server chạy nền, TỰ mở web
    python myvideo/chay.py --console  → chạy thẳng server trong console

Cửa sổ nhỏ bật server (cổng 8766), server sẵn sàng là TỰ MỞ trang web trong
trình duyệt (nút '🌐 Mở link web' chỉ để mở LẠI khi lỡ đóng tab).
Đóng cửa sổ = tắt server (nếu server do cửa sổ này bật).
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # …/OmniVoice
VENV_PY = ROOT / "venv" / "Scripts" / "python.exe"
TOKEN_FILE = ROOT / "myvideo" / "web" / "token.txt"
LOG_LOI = ROOT / "myvideo" / "chay_loi.log"
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass


def _is_venv_python() -> bool:
    """Tính cả pythonw.exe — shortcut Desktop gọi pythonw để khỏi nhảy console."""
    try:
        if not VENV_PY.exists():
            return False
        me = Path(sys.executable).resolve()
        return (me.parent == VENV_PY.parent.resolve()
                and me.stem.lower() in ("python", "pythonw"))
    except OSError:
        return False


def _console_python() -> str:
    """python.exe (không phải pythonw) cho server con — cần đọc được stdout."""
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe":
        alt = exe.with_name("python.exe")
        if alt.exists():
            return str(alt)
    return sys.executable


def _report_fatal(e: BaseException) -> None:
    """pythonw không có console — ghi log + hiện hộp thoại để không 'im lặng'."""
    import traceback
    text = "".join(traceback.format_exception(type(e), e, e.__traceback__))
    try:
        LOG_LOI.write_text(text, encoding="utf-8")
    except OSError:
        pass
    try:
        import tkinter as tk
        from tkinter import messagebox
        r = tk.Tk()
        r.withdraw()
        messagebox.showerror("myvideo — không mở được cửa sổ",
                             f"{e}\n\nChi tiết ghi ở:\n{LOG_LOI}")
        r.destroy()
    except Exception:
        pass


def _web_port() -> int:
    try:
        return int(os.environ.get("MYVIDEO_WEB_PORT", "8766"))
    except ValueError:
        return 8766


def _port_busy(port: int, timeout: float = 0.3) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _web_url(port: int) -> str:
    from urllib.parse import quote
    try:
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        token = ""
    return f"http://127.0.0.1:{port}/" + (f"?token={quote(token)}" if token else "")


# Bảng màu launcher — cùng tông indigo/tím với web myvideo, nền tối cho sang.
MAU = dict(
    bg="#12142b", card="#1c1f42", vien="#2b2f63",
    fg="#eef0ff", mo="#9aa3d0",
    accent="#4f46e5", accent_h="#6366f1",
    xam="#272b58", xam_h="#333870",
    do="#3a1631", do_chu="#fb7185", do_h="#4d1c40",
    log_bg="#0c0e20", log_fg="#8f97c4",
)


def _run_launcher(port: int) -> int:
    """Cửa sổ launcher: nền tối indigo, header gradient, nút màu có hover,
    tự CĂN GIỮA màn hình khi mở. Trạng thái · địa chỉ · mở link · nhật ký."""
    import queue
    import tkinter as tk
    import webbrowser

    proc: subprocess.Popen | None = None
    owner = False
    lines: "queue.Queue[str]" = queue.Queue()

    root = tk.Tk()
    root.title("myvideo — bảng điều khiển web")
    root.configure(bg=MAU["bg"])
    root.minsize(560, 380)

    # ── Header: dải gradient indigo → tím + tên app (vẽ lại khi đổi cỡ) ──────
    header = tk.Canvas(root, height=66, bd=0, highlightthickness=0,
                       bg=MAU["bg"])
    header.pack(fill="x")

    def _ve_header(_e=None):
        header.delete("all")
        w = max(header.winfo_width(), 560)
        c1, c2 = (0x31, 0x2E, 0x81), (0x8B, 0x3A, 0xED)
        for i in range(0, w, 2):        # vẽ dải 2px cho nhẹ
            t = i / max(1, w - 1)
            header.create_rectangle(
                i, 0, i + 2, 66, width=0,
                fill="#%02x%02x%02x" % tuple(int(a + (b - a) * t)
                                             for a, b in zip(c1, c2)))
        header.create_text(22, 33, anchor="w", text="🎬",
                           font=("Segoe UI Emoji", 20))
        header.create_text(62, 24, anchor="w", text="myvideo", fill="white",
                           font=("Segoe UI", 15, "bold"))
        header.create_text(62, 46, anchor="w", fill="#cdd3ff",
                           text="bảng điều khiển web — video Trung → thuyết minh Việt",
                           font=("Segoe UI", 9))

    header.bind("<Configure>", _ve_header)

    wrap = tk.Frame(root, bg=MAU["bg"])
    wrap.pack(fill="both", expand=True, padx=16, pady=(12, 14))
    wrap.columnconfigure(0, weight=1)
    wrap.rowconfigure(4, weight=1)

    # ── Trạng thái: chấm màu + chữ ───────────────────────────────────────────
    st_row = tk.Frame(wrap, bg=MAU["bg"])
    st_row.grid(row=0, column=0, sticky="w")
    dot = tk.Canvas(st_row, width=12, height=12, bd=0, highlightthickness=0,
                    bg=MAU["bg"])
    dot.pack(side="left", pady=1)
    dot_id = dot.create_oval(2, 2, 11, 11, fill="#fbbf24", width=0)
    status = tk.StringVar(value="Đang bật server…")
    tk.Label(st_row, textvariable=status, bg=MAU["bg"], fg=MAU["fg"],
             font=("Segoe UI", 11, "bold")).pack(side="left", padx=(8, 0))

    def _dot(mau: str) -> None:
        dot.itemconfig(dot_id, fill=mau)

    # ── Ô địa chỉ (thẻ chìm, double-click là mở) ─────────────────────────────
    url_var = tk.StringVar(value="")
    url_entry = tk.Entry(wrap, textvariable=url_var, state="readonly",
                         readonlybackground=MAU["card"], fg="#aab2ff",
                         relief="flat", insertbackground=MAU["fg"],
                         highlightthickness=1, font=("Consolas", 10),
                         highlightbackground=MAU["vien"],
                         highlightcolor=MAU["accent"])
    url_entry.grid(row=1, column=0, sticky="ew", pady=(10, 0), ipady=8)

    # ── Nút màu, bo cảm giác bằng padding + hover ────────────────────────────
    def _nut(parent, text, bg, hbg, fg="white"):
        b = tk.Button(parent, text=text, bg=bg, fg=fg, activebackground=hbg,
                      activeforeground=fg, disabledforeground="#565b8d",
                      bd=0, relief="flat", cursor="hand2",
                      font=("Segoe UI", 10, "bold"), padx=18, pady=9)
        b._bg, b._hbg = bg, hbg
        b.bind("<Enter>", lambda _e: str(b["state"]) == "normal"
               and b.config(bg=b._hbg))
        b.bind("<Leave>", lambda _e: b.config(bg=b._bg))
        return b

    def _doi_mau(b, bg, hbg):
        b._bg, b._hbg = bg, hbg
        b.config(bg=bg, activebackground=hbg)

    btns = tk.Frame(wrap, bg=MAU["bg"])
    btns.grid(row=2, column=0, sticky="w", pady=(12, 10))
    btn_open = _nut(btns, "🌐  Mở link web", MAU["xam"], MAU["xam_h"])
    btn_open.config(state="disabled")
    btn_open.pack(side="left")
    btn_copy = _nut(btns, "📋  Copy link", MAU["xam"], MAU["xam_h"],
                    fg=MAU["mo"])
    btn_copy.config(state="disabled")
    btn_copy.pack(side="left", padx=(10, 0))
    btn_quit = _nut(btns, "⏻  Tắt & thoát", MAU["do"], MAU["do_h"],
                    fg=MAU["do_chu"])
    btn_quit.pack(side="left", padx=(10, 0))

    tk.Label(wrap, text="NHẬT KÝ", bg=MAU["bg"], fg=MAU["mo"],
             font=("Segoe UI", 8, "bold")).grid(row=3, column=0, sticky="w")

    log_box = tk.Text(wrap, height=9, wrap="word", state="disabled",
                      bg=MAU["log_bg"], fg=MAU["log_fg"], bd=0,
                      insertbackground=MAU["fg"], padx=10, pady=8,
                      selectbackground=MAU["accent"],
                      highlightthickness=1, highlightbackground=MAU["vien"],
                      font=("Consolas", 9))
    log_box.grid(row=4, column=0, sticky="nsew", pady=(4, 0))
    scroll = tk.Scrollbar(wrap, orient="vertical", command=log_box.yview,
                          troughcolor=MAU["bg"], bd=0, width=10)
    scroll.grid(row=4, column=1, sticky="ns", pady=(4, 0))
    log_box.config(yscrollcommand=scroll.set)

    # ── CĂN GIỮA màn hình ────────────────────────────────────────────────────
    w, h = 680, 470
    root.update_idletasks()
    x = (root.winfo_screenwidth() - w) // 2
    y = max(0, (root.winfo_screenheight() - h) // 2 - 24)
    root.geometry(f"{w}x{h}+{x}+{y}")

    def log(msg: str) -> None:
        log_box.config(state="normal")
        log_box.insert("end", msg.rstrip() + "\n")
        if int(log_box.index("end-1c").split(".")[0]) > 500:
            log_box.delete("1.0", "100.0")
        log_box.see("end")
        log_box.config(state="disabled")

    def _pump(p: subprocess.Popen) -> None:
        assert p.stdout is not None
        for line in p.stdout:
            lines.put(line)

    def _drain() -> None:
        while True:
            try:
                log(lines.get_nowait())
            except queue.Empty:
                break
        root.after(200, _drain)

    def _ready() -> None:
        nonlocal owner
        url_var.set(_web_url(port))
        status.set(f"Đang chạy — cổng {port}"
                   + ("" if owner else "  (tiến trình khác bật sẵn)"))
        _dot("#4ade80")
        for b in (btn_open, btn_copy):
            b.config(state="normal")
        _doi_mau(btn_open, MAU["accent"], MAU["accent_h"])   # nút chính sáng lên
        btn_copy.config(fg="white")
        if not owner:
            btn_quit.config(text="✖  Đóng cửa sổ")
        log(f"🌐 Sẵn sàng: {url_var.get()}")
        # Tự mở luôn — khỏi phải bấm nút; nút '🌐 Mở link web' để mở LẠI khi cần.
        _open()
        log("⚠️ Nhớ ĐÓNG Firefox trước khi chạy video có bước dịch Gemini.")

    def _poll(n: int = 0) -> None:
        if _port_busy(port):
            _ready()
            return
        if proc is not None and proc.poll() is not None:
            status.set(f"Server tắt ngay khi bật (mã {proc.returncode}) — xem nhật ký")
            _dot("#fb7185")
            return
        if n >= 75:
            status.set("Server chưa phản hồi sau 30 giây — xem nhật ký")
            _dot("#fb7185")
            return
        root.after(400, _poll, n + 1)

    def _start() -> None:
        nonlocal proc, owner
        if _port_busy(port):
            log(f"🌐 Bảng web đang chạy sẵn ở cổng {port} — dùng luôn bản đó.")
            _ready()
            return
        log("🌐 Đang bật server…")
        env = {**os.environ, "MYVIDEO_WEB_NO_OPEN": "1",
               "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
        try:
            proc = subprocess.Popen(
                [_console_python(), "-m", "myvideo.web.server"],
                cwd=str(ROOT), env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1,
                creationflags=CREATE_NO_WINDOW)
        except Exception as e:
            status.set("Không bật được server")
            _dot("#fb7185")
            log(f"❌ {e}")
            return
        owner = True
        threading.Thread(target=_pump, args=(proc,), daemon=True).start()
        root.after(400, _poll, 0)

    def _stop_server() -> None:
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def _open() -> None:
        if url_var.get():
            webbrowser.open(url_var.get())
            log(f"↗ Đã mở: {url_var.get()}")

    def _copy() -> None:
        root.clipboard_clear()
        root.clipboard_append(url_var.get())
        log("📋 Đã copy địa chỉ.")

    def _close() -> None:
        if owner:
            log("⏹ Đang tắt server…")
            root.update_idletasks()
            _stop_server()
        root.destroy()

    btn_open.config(command=_open)
    btn_copy.config(command=_copy)
    btn_quit.config(command=_close)
    root.protocol("WM_DELETE_WINDOW", _close)
    url_entry.bind("<Double-Button-1>", lambda _e: _open())

    root.after(100, _start)
    _drain()
    root.mainloop()
    _stop_server()
    return 0


def main(argv: list[str]) -> int:
    if VENV_PY.exists() and not _is_venv_python():
        print(f"↻ Chạy lại bằng python của dự án: {VENV_PY}")
        return subprocess.call([str(VENV_PY), str(Path(__file__).resolve()), *argv],
                               cwd=str(ROOT))
    if not VENV_PY.exists():
        print(f"⚠️ Không thấy {VENV_PY} — đang dùng {sys.executable}.")

    sys.path.insert(0, str(ROOT))
    if "--console" not in argv:
        try:
            return _run_launcher(_web_port())
        except Exception as e:
            _report_fatal(e)
            if not sys.stdout:
                return 1
            print(f"⚠️ Không mở được cửa sổ ({e}) — chạy bản console.")

    from myvideo.web.server import main as run_server     # noqa: E402
    run_server()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
