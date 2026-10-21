# -*- coding: utf-8 -*-
"""Bật myvideo — bản WEB (rút gọn từ myvoice/chay.py, cùng cách vận hành).

    python myvideo/chay.py            → cửa sổ nhỏ: server chạy nền, TỰ mở web
    python myvideo/chay.py --console  → chạy thẳng server trong console

Cửa sổ nhỏ bật server (cổng 8766 — bận thì tự nhảy 8767, 8768, …; myvoice cũng
mặc định 8766 nên hai bảng chạy cùng lúc vẫn được), server sẵn sàng là TỰ MỞ trang web trong
trình duyệt (nút '🌐 Mở link web' chỉ để mở LẠI khi lỡ đóng tab).
Đóng cửa sổ = tắt server (nếu server do cửa sổ này bật).

Hai chế độ "xong hết thì…" — ⏻ TẮT MÁY hoặc 🌙 cho máy NGỦ sau 3 phút rảnh,
CHỌN MỘT, MẶC ĐỊNH không tick gì. Cả hai do SERVER giữ (web/power.py canh hàng
đợi + đếm ngược); ô ở đây chỉ là công tắc từ xa, khớp hai chiều với ô trên
trang web.
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
CONG_FILE = ROOT / "myvideo" / "web" / "cong.txt"    # cổng bảng web dùng lần gần nhất (_chon_cong)
LOG_LOI = ROOT / "myvideo" / "chay_loi.log"
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# Số phút chờ sau khi hàng đợi rảnh rồi mới ngủ/tắt máy — CHỈ để ghi nhãn ô
# tick; bộ đếm thật nằm ở myvideo/web/power.py (DELAY_MIN), sửa thì sửa cả hai.
POWER_DELAY_MIN = 3

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


def _is_myvideo(port: int, timeout: float = 1.0) -> bool:
    """Cái đang nghe ở cổng có ĐÚNG là bảng web myvideo không (hỏi /api/ping) —
    myvoice cũng mặc định 8766, chỉ dò "cổng bận" thì mở nhầm bảng của nó."""
    import json
    from urllib.request import urlopen
    try:
        with urlopen(f"http://127.0.0.1:{port}/api/ping", timeout=timeout) as r:
            return json.load(r).get("app") == "myvideo"
    except Exception:
        return False


# Cổng mặc định bận → dò tiếp 8767, 8768, … Khớp SO_CONG_THU + _chon_cong trong
# myvideo/web/server.py.
SO_CONG_THU = 20


def _cong_trong(port: int) -> bool:
    """Cổng còn trống không — BIND THỬ, không connect.

    Bind được ở đây = server ngay sau cũng bind được ("chưa ai nghe" theo connect
    chưa đủ: cổng có thể đã bị bind mà chưa listen). Và bind trả lời tức thì
    (~0,05 ms); connect tới cổng TRỐNG trên Windows lại chờ hết timeout (~0,4 s),
    quét 20 cổng kiểu đó mất ~8 s — chính là lý do trước đây bật bảng web lâu.
    """
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _cong_da_nho(uu_tien: int) -> int | None:
    """Cổng ghi trong CONG_FILE lần trước — chỉ tin khi còn nằm trong dải đang dò
    (đổi MYVIDEO_WEB_PORT sang dải khác thì bỏ qua số cũ). Không có/hỏng → None."""
    try:
        p = int(CONG_FILE.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    return p if uu_tien <= p < uu_tien + SO_CONG_THU else None


def _nho_cong(port: int) -> None:
    """Ghi cổng vừa chọn cho lần sau; ghi hỏng (ổ chỉ đọc…) thì thôi, không chết."""
    try:
        CONG_FILE.write_text(str(port), encoding="utf-8")
    except OSError:
        pass


def _chon_cong(uu_tien: int) -> tuple[int, bool]:
    """Chọn cổng cho bảng web → (cổng, myvideo_đã_chạy_sẵn_ở_đó).

    Thứ tự dò: cổng NHỚ từ lần trước (web/cong.txt) → cổng ưu tiên → phần còn lại
    của dải uu_tien … uu_tien+SO_CONG_THU-1.
    1) Đã có myvideo nghe sẵn ở cổng nào trong dải → trả cổng đó + True: dùng luôn,
       không bật cái thứ hai.
    2) Chưa có → cổng TRỐNG đầu tiên theo thứ tự trên. Cổng nhớ đứng đầu nên bị
       đẩy sang 8767 một lần là lần sau vào thẳng 8767, khỏi dò lại. Cổng ưu tiên
       bị chương trình KHÁC chiếm (myvoice chẳng hạn) thì tự nhảy cổng thay vì
       văng traceback "địa chỉ đang bận".
    Cổng chọn được GHI LẠI vào web/cong.txt. Cả dải đều bận → OSError.

    Dò bằng bind (tức thì) nên quét cả dải chỉ mất vài ms; chỉ cổng ĐANG bận mới
    phải hỏi /api/ping xem có phải mình không.
    """
    dai = range(uu_tien, uu_tien + SO_CONG_THU)
    nho = _cong_da_nho(uu_tien)
    thu_tu = ([nho] if nho is not None else []) + [p for p in dai if p != nho]
    trong = {p: _cong_trong(p) for p in thu_tu}
    for p in thu_tu:
        if not trong[p] and _is_myvideo(p):
            _nho_cong(p)
            return p, True
    for p in thu_tu:
        if trong[p] and _cong_trong(p):      # dò lại sát lúc chọn cho chắc
            _nho_cong(p)
            return p, False
    raise OSError(f"Không còn cổng trống trong khoảng {dai.start}–{dai[-1]} "
                  "(toàn bị chương trình khác chiếm). Đặt MYVIDEO_WEB_PORT sang dải khác.")


def _bao_doi_cong(uu_tien: int, port: int) -> str:
    """Câu báo khi cổng chọn ≠ cổng ưu tiên: do nhớ từ lần trước, hay do bị chiếm."""
    if _cong_trong(uu_tien):
        return (f"ℹ️ Dùng cổng {port} nhớ từ lần trước (cổng {uu_tien} đang trống — "
                f"xoá web/cong.txt nếu muốn quay về {uu_tien}).")
    return f"⚠️ Cổng {uu_tien} đang bị chương trình khác chiếm → dùng cổng {port}."


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
    root.minsize(560, 440)

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
    wrap.rowconfigure(6, weight=1)          # hàng nhật ký giãn

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

    # Hai chế độ "xong hết thì…", CHỌN MỘT (tick ô này thì ô kia tự bỏ), MẶC
    # ĐỊNH không tick gì. CẢ HAI do SERVER giữ (web/power.py: canh hàng đợi +
    # đếm ngược 3 phút) — khác myvoice/chay.py (⏻ tự canh ở cửa sổ): ô ở đây
    # chỉ là công tắc từ xa, bấm thì POST /hangdoi/power rồi soi lại
    # /api/trangthai để vẽ theo sự thật của server.
    def _chk(parent, text, var):
        return tk.Checkbutton(parent, text=text, variable=var, bg=MAU["bg"],
                              fg=MAU["fg"], activebackground=MAU["bg"],
                              activeforeground=MAU["fg"],
                              selectcolor=MAU["card"],
                              disabledforeground="#565b8d", bd=0,
                              highlightthickness=0, cursor="hand2",
                              font=("Segoe UI", 9))

    sd_row = tk.Frame(wrap, bg=MAU["bg"])
    sd_row.grid(row=3, column=0, sticky="w", pady=(0, 2))
    var_shutdown = tk.BooleanVar(value=False)
    chk_shutdown = _chk(
        sd_row, f"⏻  Xong hết thì TẮT MÁY (sau {POWER_DELAY_MIN} phút rảnh)",
        var_shutdown)
    chk_shutdown.config(state="disabled")
    chk_shutdown.pack(side="left")
    tk.Label(sd_row, text="huỷ phút chót: mở CMD gõ  shutdown /a", bg=MAU["bg"],
             fg=MAU["mo"], font=("Segoe UI", 8)).pack(side="left", padx=(10, 0))

    sl_row = tk.Frame(wrap, bg=MAU["bg"])
    sl_row.grid(row=4, column=0, sticky="w", pady=(0, 8))
    var_sleep = tk.BooleanVar(value=False)
    chk_sleep = _chk(
        sl_row, f"🌙  Xong hết thì cho máy NGỦ (sau {POWER_DELAY_MIN} phút rảnh)",
        var_sleep)
    chk_sleep.config(state="disabled")
    chk_sleep.pack(side="left")
    power_note = tk.StringVar(value="")
    tk.Label(sl_row, textvariable=power_note, bg=MAU["bg"], fg=MAU["mo"],
             font=("Segoe UI", 8)).pack(side="left", padx=(10, 0))

    tk.Label(wrap, text="NHẬT KÝ", bg=MAU["bg"], fg=MAU["mo"],
             font=("Segoe UI", 8, "bold")).grid(row=5, column=0, sticky="w")

    log_box = tk.Text(wrap, height=9, wrap="word", state="disabled",
                      bg=MAU["log_bg"], fg=MAU["log_fg"], bd=0,
                      insertbackground=MAU["fg"], padx=10, pady=8,
                      selectbackground=MAU["accent"],
                      highlightthickness=1, highlightbackground=MAU["vien"],
                      font=("Consolas", 9))
    log_box.grid(row=6, column=0, sticky="nsew", pady=(4, 0))
    scroll = tk.Scrollbar(wrap, orient="vertical", command=log_box.yview,
                          troughcolor=MAU["bg"], bd=0, width=10)
    scroll.grid(row=6, column=1, sticky="ns", pady=(4, 0))
    log_box.config(yscrollcommand=scroll.set)

    # ── CĂN GIỮA màn hình ────────────────────────────────────────────────────
    w, h = 680, 530
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
        for wg in (btn_open, btn_copy, chk_shutdown, chk_sleep):
            wg.config(state="normal")
        _doi_mau(btn_open, MAU["accent"], MAU["accent_h"])   # nút chính sáng lên
        btn_copy.config(fg="white")
        if not owner:
            btn_quit.config(text="✖  Đóng cửa sổ")
        log(f"🌐 Sẵn sàng: {url_var.get()}")
        # Tự mở luôn — khỏi phải bấm nút; nút '🌐 Mở link web' để mở LẠI khi cần.
        _open()
        log("🧩 Bước dịch Gemini đi qua Chrome Extension (như myvoice) — giữ Chrome "
            "đã đăng nhập Gemini mở; không kết nối được thì tự mở Firefox thay.")
        _sync_power_now()       # server chạy sẵn có thể đã bật ⏻/🌙 → ô khớp ngay

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
        nonlocal proc, owner, port
        uu_tien = port
        # Cổng ưu tiên bị chương trình KHÁC chiếm (myvoice chẳng hạn) → tự chọn cổng
        # trống kế tiếp; đã có myvideo chạy sẵn đâu đó trong dải → dùng luôn bản đó.
        try:
            port, dang_chay = _chon_cong(uu_tien)
        except OSError as e:
            status.set("Không còn cổng trống — xem nhật ký")
            _dot("#fb7185")
            log(f"⛔ {e}")
            return
        if dang_chay:
            log(f"🌐 Bảng web đang chạy sẵn ở cổng {port} — dùng luôn bản đó.")
            _ready()
            return
        if port != uu_tien:
            log(_bao_doi_cong(uu_tien, port))
        log("🌐 Đang bật server…")
        env = {**os.environ,
               "MYVIDEO_WEB_PORT": str(port),  # server nghe ĐÚNG cổng vừa chọn
               "MYVIDEO_WEB_NO_OPEN": "1",
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

    # ── Gọi chính server đang chạy (kèm token) ──────────────────────────────
    def _http(path: str, data: dict | None = None):
        """GET (data=None) hoặc POST form tới server. Trả dict nếu JSON, không
        thì trả chuỗi. Gọi TRONG LUỒNG NỀN — mạng chậm sẽ treo cửa sổ.

        POST gửi kèm header HX-Request: các nút của server trả lời htmx bằng
        khối HTML tại chỗ (mã 200); thiếu header là bị chuyển hướng 303 về "/"
        KHÔNG kèm token → urllib bám theo rồi ăn 401 dù lệnh đã chạy."""
        import json
        import urllib.parse
        import urllib.request
        try:
            token = TOKEN_FILE.read_text(encoding="utf-8").strip()
        except OSError:
            token = ""
        url = f"http://127.0.0.1:{port}{path}?token={urllib.parse.quote(token)}"
        body = urllib.parse.urlencode(data).encode() if data is not None else None
        req = urllib.request.Request(
            url, data=body,
            headers={"HX-Request": "true"} if body is not None else {})
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8", "replace")
        try:
            return json.loads(raw)
        except ValueError:
            return raw

    # ── ⏻ / 🌙 "Xong hết thì…" — MỘT trạng thái, server là nguồn sự thật ────
    # pw["mode"] ∈ {"", "tat", "ngu"} là chế độ cửa sổ đang vẽ; mọi thay đổi
    # (bấm ô, server báo về) đều đi qua _apply_mode nên hai ô không bao giờ
    # cùng bật. Chống "GET cũ ghi đè POST mới" (ô nhấp nháy/tự bật lại — đã
    # gặp bên myvoice 08/09/2026) bằng seq/pending: kết quả GET chỉ được ghi
    # khi seq lúc xin còn là seq hiện tại VÀ không còn POST nào đang bay.
    sync_lock = threading.Lock()
    pw = {"mode": "", "srv_mode": None, "left": "", "seq": 0, "pending": 0}

    def _apply_server_power(st, seq: int) -> None:
        """Ghi trạng thái ⏻/🌙 server trả về vào pw — BỎ QUA nếu đã cũ."""
        p = st.get("power") if isinstance(st, dict) else None
        if not isinstance(p, dict):
            return
        with sync_lock:
            if seq != pw["seq"] or pw["pending"]:
                return
            pw["srv_mode"] = (p.get("mode") or "") if p.get("armed") else ""
            pw["left"] = p.get("left") or ""

    def _post_power(mode: str) -> None:
        """Đẩy chế độ lên server. Ghi pw NGAY (ô tick khớp tức thì), gọi mạng
        ở luồng nền; hỏng thì thử lại một lần, vẫn hỏng thì hỏi lại server để
        ô tick vẽ theo sự thật chứ không theo ý vừa bấm."""
        with sync_lock:
            pw["seq"] += 1
            pw["pending"] += 1
            pw["srv_mode"] = mode
            if not mode:
                pw["left"] = ""

        def work() -> None:
            import time
            err = None
            for lan in (1, 2):
                try:
                    _http("/hangdoi/power",
                          {"on": "1", "mode": mode} if mode else {"mode": ""})
                    err = None
                    break
                except Exception as e:
                    err = e
                    if lan == 1:
                        time.sleep(2)
            with sync_lock:
                pw["pending"] -= 1
            if err is not None:
                lines.put(f"❌ Không đặt được chế độ ngủ/tắt máy ở server ({err})"
                          " — ô tick sẽ vẽ lại theo trạng thái thật của server.\n")
                _sync_power_now()
        threading.Thread(target=work, daemon=True).start()

    def _sync_power_now() -> None:
        """Hỏi NGAY trạng thái server (không đợi lượt poll 5 giây): lúc server
        vừa sẵn sàng — server chạy sẵn có thể đã bật ⏻/🌙 bên trang web, ô ở
        đây phải khớp — và sau khi POST hỏng. Chạy luồng nền."""
        with sync_lock:
            seq = pw["seq"]

        def work() -> None:
            try:
                st = _http("/api/trangthai")
            except Exception:
                return
            _apply_server_power(st, seq)
        threading.Thread(target=work, daemon=True).start()

    def _apply_mode(mode: str, source: str = "user") -> None:
        """Nơi DUY NHẤT đổi chế độ. mode: "" / "tat" / "ngu". Chạy trên luồng Tk.

        source="user"  : bấm ở cửa sổ này → đẩy lên server.
        source="server": server báo về (tick bên trang web, hoặc tự bỏ tick sau
                         khi ngủ/tắt xong) → chỉ vẽ lại, KHÔNG POST ngược lại
                         kẻo hai bên đá nhau vô tận."""
        old = pw["mode"]
        if mode == old:
            return
        pw["mode"] = mode
        var_shutdown.set(mode == "tat")
        var_sleep.set(mode == "ngu")
        if source == "user":
            _post_power(mode)
        if mode:
            log(("🌙" if mode == "ngu" else "⏻")
                + f" Bật chế độ {'cho máy NGỦ' if mode == 'ngu' else 'TẮT MÁY'}"
                f" khi xong: hàng đợi xong hết + rảnh {POWER_DELAY_MIN} phút."
                + (" (đã bỏ ô kia)" if old else ""))
        elif source == "user":
            log("✖ Đã tắt chế độ ngủ/tắt máy khi xong.")
        else:
            log("Server đã bỏ tick ngủ/tắt máy (bỏ bên trang web / vừa thực hiện xong).")

    def _click_shutdown() -> None:
        _apply_mode("tat" if var_shutdown.get() else "")

    def _click_sleep() -> None:
        _apply_mode("ngu" if var_sleep.get() else "")

    def _power_sync() -> None:
        """Mỗi giây soi pw (luồng nền ghi) → vẽ ô tick + dòng đếm ngược."""
        with sync_lock:
            srv, left, pending = pw["srv_mode"], pw["left"], pw["pending"]
        if srv is not None and not pending and srv != pw["mode"]:
            _apply_mode(srv, source="server")
        if pw["mode"] and left:
            power_note.set(f"⏳ {'ngủ' if pw['mode'] == 'ngu' else 'tắt máy'} "
                           f"sau {left} — huỷ: bỏ tick")
        elif pw["mode"]:
            power_note.set("chờ hàng đợi xong hết")
        else:
            power_note.set("")
        root.after(1000, _power_sync)

    def _power_watcher() -> None:
        """Luồng nền: 5 giây hỏi /api/trangthai một lần cho _power_sync vẽ lại."""
        import time
        while True:
            time.sleep(5)
            with sync_lock:
                seq = pw["seq"]
            try:
                st = _http("/api/trangthai")
            except Exception:
                continue           # server tắt/chưa lên → thử lại lượt sau
            _apply_server_power(st, seq)

    def _close() -> None:
        if pw["mode"] and owner:
            # Bộ đếm ⏻/🌙 nằm TRONG server, đóng cửa sổ là tắt server → hết
            # hẹn (lệnh `shutdown /s` ĐÃ nổ thì vẫn chạy — huỷ: shutdown /a).
            log("✖ Tắt server = huỷ luôn chế độ ngủ/tắt máy đang chờ.")
        if owner:
            log("⏹ Đang tắt server…")
            root.update_idletasks()
            _stop_server()
        root.destroy()

    btn_open.config(command=_open)
    btn_copy.config(command=_copy)
    btn_quit.config(command=_close)
    chk_shutdown.config(command=_click_shutdown)
    chk_sleep.config(command=_click_sleep)
    root.protocol("WM_DELETE_WINDOW", _close)
    url_entry.bind("<Double-Button-1>", lambda _e: _open())

    threading.Thread(target=_power_watcher, daemon=True).start()
    _power_sync()
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
