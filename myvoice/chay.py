"""Bật myvoice — bản WEB.  Mở file này rồi bấm ▶ Run trong VS Code là chạy.

Vì sao có file này: VS Code chỉ bấm ▶ chạy được file .py, không chạy .bat.
Nội dung y hệt `chay.bat` (và `chay_gui.bat` khi thêm cờ --gui).

Chạy bằng BẤT KỲ python nào cũng được: nếu interpreter đang dùng không phải venv
của dự án thì file tự khởi động lại bằng venv\\Scripts\\python.exe — không thì sẽ
thiếu fastapi/uvicorn/torch.

    python myvoice/chay.py            → cửa sổ nhỏ: server chạy nền + nút mở link web
    python myvoice/chay.py --console  → chạy thẳng trong console như trước (không cửa sổ)
    python myvoice/chay.py --gui      → GUI Tkinter bản cũ (amain_taogiong_gui.py)

Cửa sổ nhỏ (mặc định) tự bật server rồi TỰ MỞ trình duyệt ngay khi server sẵn
sàng — nút 🌐 vẫn còn để mở LẠI. Đóng cửa sổ = tắt server (nếu server do cửa sổ
này bật). Trong cửa sổ có sẵn: 🌐 mở link · 📋 copy link · 🗑 xóa output (vào
Thùng rác) · hai ô ⏻ "tắt máy" / 🌙 "cho máy ngủ" khi hàng đợi web chạy xong hết.
Bộ đếm do SERVER giữ (web/power.py, mặc định TẮT) — ô ở đây là công tắc từ xa, cùng
trạng thái với ô trên trang web. (🌙 bỏ 26/10/2026, user cho quay lại 31/10/2026.)
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # …/OmniVoice
VENV_PY = ROOT / "venv" / "Scripts" / "python.exe"
GUI = ROOT / "myvoice" / "scripts" / "amain_taogiong_gui.py"
TOKEN_FILE = ROOT / "myvoice" / "web" / "token.txt"
CONG_FILE = ROOT / "myvoice" / "web" / "cong.txt"    # cổng bảng web dùng lần gần nhất (_chon_cong)
LOG_LOI = ROOT / "myvoice" / "chay_loi.log"      # lỗi khi chạy bằng pythonw (không console)

# Server chạy nền, không cần cửa sổ console riêng (nhật ký đã hiện trong cửa sổ này).
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# Số phút chờ trước khi tắt máy / cho máy ngủ khi bật ô ⏻ / 🌙 — CHỈ để ghi nhãn:
# bộ đếm thật nằm trong server (web/power.py lấy từ amain_taogiong_gui.SHUTDOWN_DELAY_MIN
# và SLEEP_DELAY_MIN), đổi bên đó thì đổi cả đây cho nhãn khớp.
SHUTDOWN_DELAY_MIN = 1
SLEEP_DELAY_MIN = 1

# Console của VS Code / cmd hay là cp1252: in tiếng Việt sẽ nổ UnicodeEncodeError
# NGAY dòng thông báo đầu tiên, chưa kịp bật gì cả. Ép UTF-8 trước mọi thứ.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")   # type: ignore[union-attr]
    except Exception:
        pass


def _is_venv_python() -> bool:
    """Đang chạy bằng python CỦA VENV chưa — tính cả pythonw.exe, vì shortcut ngoài
    Desktop gọi pythonw để khỏi nhảy cửa sổ console. Không tính pythonw thì file này
    sẽ tự khởi động lại bằng python.exe và bung ra đúng cái console vừa tránh."""
    try:
        if not VENV_PY.exists():
            return False
        me = Path(sys.executable).resolve()
        return (me.parent == VENV_PY.parent.resolve()
                and me.stem.lower() in ("python", "pythonw"))
    except OSError:
        return False


def _console_python() -> str:
    """python.exe (không phải pythonw) để chạy server con: pythonw + đường ống stdout
    hay bị None, mà nhật ký server thì cần đọc được. Vẫn ẩn nhờ CREATE_NO_WINDOW."""
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe":
        alt = exe.with_name("python.exe")
        if alt.exists():
            return str(alt)
    return sys.executable


def _report_fatal(e: BaseException) -> None:
    """Chạy bằng pythonw thì KHÔNG có console để in lỗi — ghi ra file log và cố hiện
    hộp thoại, để bấm shortcut không bao giờ 'im lặng chẳng thấy gì'."""
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
        messagebox.showerror("myvoice — không mở được cửa sổ",
                             f"{e}\n\nChi tiết ghi ở:\n{LOG_LOI}")
        r.destroy()
    except Exception:
        pass


# ── Thông tin bảng web (khớp myvoice/web/server.py) ─────────────────────────
def _web_port() -> int:
    try:
        return int(os.environ.get("MYVOICE_WEB_PORT", "8766"))
    except ValueError:
        return 8766


def _port_busy(port: int, timeout: float = 0.3) -> bool:
    """Đã có ai nghe ở cổng này chưa (nhiều khả năng là server đang chạy sẵn)."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _is_myvoice(port: int, timeout: float = 1.0) -> bool:
    """Cái đang nghe ở cổng có ĐÚNG là bảng web myvoice không (hỏi /api/ping).
    19/10/2026: dự án "Đăng video tự động" (DangvideoYTBTikTokZalo) cũng nghe 8765 —
    chỉ dò cổng bận thì tưởng bảng web mình đang chạy sẵn, mở nhầm bảng của nó."""
    import json
    from urllib.request import urlopen
    try:
        with urlopen(f"http://127.0.0.1:{port}/api/ping", timeout=timeout) as r:
            return json.load(r).get("app") == "myvoice"
    except Exception:
        return False


# Cổng mặc định bận (myvideo cũng mặc định 8766) → dò tiếp 8767, 8768, …
# Khớp SO_CONG_THU + _chon_cong trong myvoice/web/server.py.
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
    (đổi MYVOICE_WEB_PORT sang dải khác thì bỏ qua số cũ). Không có/hỏng → None."""
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
    """Chọn cổng cho bảng web → (cổng, myvoice_đã_chạy_sẵn_ở_đó).

    Thứ tự dò: cổng NHỚ từ lần trước (web/cong.txt) → cổng ưu tiên → phần còn lại
    của dải uu_tien … uu_tien+SO_CONG_THU-1.
    1) Đã có myvoice nghe sẵn ở cổng nào trong dải → trả cổng đó + True: dùng luôn,
       không bật cái thứ hai.
    2) Chưa có → cổng TRỐNG đầu tiên theo thứ tự trên. Cổng nhớ đứng đầu nên bị
       đẩy sang 8767 một lần là lần sau vào thẳng 8767, khỏi dò lại. Cổng ưu tiên
       bị chương trình KHÁC chiếm (myvideo chẳng hạn) thì tự nhảy cổng thay vì
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
        if not trong[p] and _is_myvoice(p):
            _nho_cong(p)
            return p, True
    for p in thu_tu:
        if trong[p] and _cong_trong(p):      # dò lại sát lúc chọn cho chắc
            _nho_cong(p)
            return p, False
    raise OSError(f"Không còn cổng trống trong khoảng {dai.start}–{dai[-1]} "
                  "(toàn bị chương trình khác chiếm). Đặt MYVOICE_WEB_PORT sang dải khác.")


def _bao_doi_cong(uu_tien: int, port: int) -> str:
    """Câu báo khi cổng chọn ≠ cổng ưu tiên: do nhớ từ lần trước, hay do bị chiếm."""
    if _cong_trong(uu_tien):
        return (f"ℹ️ Dùng cổng {port} nhớ từ lần trước (cổng {uu_tien} đang trống — "
                f"xoá web/cong.txt nếu muốn quay về {uu_tien}).")
    return f"⚠️ Cổng {uu_tien} đang bị chương trình khác chiếm → dùng cổng {port}."


def _web_url(port: int) -> str:
    """Địa chỉ kèm token — server ghi token ra web/token.txt lúc khởi động, nên chỉ
    đọc được SAU khi server lên. Chưa có token thì trả địa chỉ trần (web sẽ hỏi)."""
    from urllib.parse import quote
    try:
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        token = ""
    return f"http://127.0.0.1:{port}/" + (f"?token={quote(token)}" if token else "")


# Bảng màu launcher — tông TÍM thương hiệu myvoice, nền tối cho sang
# (cùng kiểu với launcher myvideo, chỉ khác tông màu).
MAU = dict(
    bg="#161129", card="#221a40", vien="#332758",
    fg="#f2eeff", mo="#a99cd0",
    accent="#7c3aed", accent_h="#8b5cf6",
    xam="#2b2150", xam_h="#382b68",
    do="#3a1631", do_chu="#fb7185", do_h="#4d1c40",
    log_bg="#100b20", log_fg="#9a8fc4",
)


# ── Cửa sổ nhỏ: bật server nền + nút mở link ────────────────────────────────
def _run_launcher(port: int) -> int:
    """Cửa sổ launcher: nền tối tím, header gradient, nút màu có hover, tự CĂN
    GIỮA màn hình. Trạng thái · địa chỉ · mở link · xóa output · tắt máy khi xong.

    Server chạy trong tiến trình con KHÔNG có console (CREATE_NO_WINDOW) nên mọi
    thông báo/lỗi của nó được bơm vào ô nhật ký dưới — bỏ console mà vẫn nhìn thấy
    lỗi khởi động. Đóng cửa sổ thì tắt luôn server nếu server do cửa sổ này bật.
    """
    import queue
    import tkinter as tk
    import webbrowser
    from tkinter import messagebox

    proc: subprocess.Popen | None = None
    owner = False                      # server có phải do cửa sổ này bật không
    lines: "queue.Queue[str]" = queue.Queue()
    # Cờ dùng CHUNG với luồng nền — không đọc biến Tk ngoài luồng Tk (không an toàn).
    # mode/left: trạng thái ô ⏻/🌙 ĐỌC VỀ TỪ SERVER (server mới là nơi giữ bộ đếm),
    # luồng nền ghi vào đây rồi _shutdown_sync bên luồng Tk đọc ra. mode: None = chưa
    # hỏi được server, "" = tắt, "shutdown" = ⏻ tắt máy, "sleep" = 🌙 cho máy ngủ.
    flags = {"mode": None, "left": ""}

    root = tk.Tk()
    root.title("myvoice — bảng điều khiển web")
    root.configure(bg=MAU["bg"])
    root.minsize(600, 420)

    # ── Header: dải gradient tím + tên app (vẽ lại khi đổi cỡ) ───────────────
    header = tk.Canvas(root, height=66, bd=0, highlightthickness=0, bg=MAU["bg"])
    header.pack(fill="x")

    def _ve_header(_e=None):
        header.delete("all")
        w = max(header.winfo_width(), 600)
        c1, c2 = (0x3B, 0x1A, 0x78), (0x93, 0x33, 0xEA)
        for i in range(0, w, 2):        # vẽ dải 2px cho nhẹ
            t = i / max(1, w - 1)
            header.create_rectangle(
                i, 0, i + 2, 66, width=0,
                fill="#%02x%02x%02x" % tuple(int(a + (b - a) * t)
                                             for a, b in zip(c1, c2)))
        header.create_text(22, 33, anchor="w", text="🎧",
                           font=("Segoe UI Emoji", 20))
        header.create_text(62, 24, anchor="w", text="myvoice", fill="white",
                           font=("Segoe UI", 15, "bold"))
        header.create_text(62, 46, anchor="w", fill="#ddd0ff",
                           text="bảng điều khiển web — kịch bản → giọng đọc → video",
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
                         readonlybackground=MAU["card"], fg="#c4b5fd",
                         relief="flat", insertbackground=MAU["fg"],
                         highlightthickness=1, font=("Consolas", 10),
                         highlightbackground=MAU["vien"],
                         highlightcolor=MAU["accent"])
    url_entry.grid(row=1, column=0, sticky="ew", pady=(10, 0), ipady=8)

    # ── Nút màu, hover đổi sắc ───────────────────────────────────────────────
    def _nut(parent, text, bg, hbg, fg="white"):
        b = tk.Button(parent, text=text, bg=bg, fg=fg, activebackground=hbg,
                      activeforeground=fg, disabledforeground="#5c5486",
                      bd=0, relief="flat", cursor="hand2",
                      font=("Segoe UI", 10, "bold"), padx=16, pady=9)
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
    btn_copy = _nut(btns, "📋  Copy link", MAU["xam"], MAU["xam_h"], fg=MAU["mo"])
    btn_copy.config(state="disabled")
    btn_copy.pack(side="left", padx=(10, 0))
    btn_clear = _nut(btns, "🗑  Xóa output", MAU["xam"], MAU["xam_h"], fg=MAU["mo"])
    btn_clear.config(state="disabled")
    btn_clear.pack(side="left", padx=(10, 0))
    btn_quit = _nut(btns, "⏻  Tắt & thoát", MAU["do"], MAU["do_h"], fg=MAU["do_chu"])
    btn_quit.pack(side="left", padx=(10, 0))

    # Ô ⏻ "xong hết thì tắt máy" / 🌙 "xong hết thì cho máy ngủ" — GIAO CHO SERVER:
    # bảng web giữ bộ đếm (web/power.py), ở đây chỉ bật/tắt hộ (POST /hangdoi/tatmay)
    # và soi lại trạng thái. Làm thêm một bộ đếm thứ hai ở đây thì hai bên đá nhau —
    # xem khối ⏻/🌙 bên dưới. Hai ô loại trừ nhau: tick ô này là bỏ ô kia.
    def _chk(parent, text, var):
        return tk.Checkbutton(parent, text=text, variable=var, bg=MAU["bg"],
                              fg=MAU["fg"], activebackground=MAU["bg"],
                              activeforeground=MAU["fg"],
                              selectcolor=MAU["card"],
                              disabledforeground="#5c5486", bd=0,
                              highlightthickness=0, cursor="hand2",
                              font=("Segoe UI", 9))

    sd_row = tk.Frame(wrap, bg=MAU["bg"])
    sd_row.grid(row=3, column=0, sticky="w", pady=(0, 8))
    var_shutdown = tk.BooleanVar(value=False)
    chk_shutdown = _chk(
        sd_row, f"⏻  Tự động tắt máy khi xong (sau {SHUTDOWN_DELAY_MIN} phút)",
        var_shutdown)
    chk_shutdown.config(state="disabled")
    chk_shutdown.pack(side="left")
    var_sleep = tk.BooleanVar(value=False)
    chk_sleep = _chk(
        sd_row, f"🌙  Tự động ngủ khi xong (sau {SLEEP_DELAY_MIN} phút)",
        var_sleep)
    chk_sleep.config(state="disabled")
    chk_sleep.pack(side="left", padx=(10, 0))
    shutdown_note = tk.StringVar(value="")
    tk.Label(sd_row, textvariable=shutdown_note, bg=MAU["bg"], fg=MAU["mo"],
             font=("Segoe UI", 8)).pack(side="left", padx=(10, 0))

    tk.Label(wrap, text="NHẬT KÝ", bg=MAU["bg"], fg=MAU["mo"],
             font=("Segoe UI", 8, "bold")).grid(row=5, column=0, sticky="w")

    log_box = tk.Text(wrap, height=10, wrap="word", state="disabled",
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
    w, h = 720, 520
    root.update_idletasks()
    x = (root.winfo_screenwidth() - w) // 2
    y = max(0, (root.winfo_screenheight() - h) // 2 - 24)
    root.geometry(f"{w}x{h}+{x}+{y}")

    def log(msg: str) -> None:
        log_box.config(state="normal")
        log_box.insert("end", msg.rstrip() + "\n")
        if int(log_box.index("end-1c").split(".")[0]) > 500:   # giữ 500 dòng cuối
            log_box.delete("1.0", "100.0")
        log_box.see("end")
        log_box.config(state="disabled")

    def _pump(p: subprocess.Popen) -> None:
        """Đọc stdout server trong luồng riêng (Text chỉ đụng được từ luồng Tk)."""
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
        for wg in (btn_open, btn_copy, btn_clear, chk_shutdown, chk_sleep):
            wg.config(state="normal")
        _doi_mau(btn_open, MAU["accent"], MAU["accent_h"])   # nút chính sáng lên
        btn_copy.config(fg="white")
        btn_clear.config(fg="white")
        if not owner:
            btn_quit.config(text="✖  Đóng cửa sổ")
        log(f"🌐 Sẵn sàng: {url_var.get()}")
        _open()                 # tự mở luôn — nút 🌐 chỉ còn để mở LẠI khi lỡ đóng tab
        _sync_shutdown_now()    # lấy trạng thái ⏻/🌙 của server → ô khớp ngay từ đầu

    def _poll(n: int = 0) -> None:
        if _port_busy(port):
            _ready()
            return
        if proc is not None and proc.poll() is not None:
            status.set(f"Server tắt ngay khi bật (mã {proc.returncode}) — xem nhật ký")
            _dot("#fb7185")
            return
        if n >= 75:                       # ~30 giây
            status.set("Server chưa phản hồi sau 30 giây — xem nhật ký")
            _dot("#fb7185")
            return
        root.after(400, _poll, n + 1)

    def _start() -> None:
        nonlocal proc, owner, port
        uu_tien = port
        # Cổng ưu tiên bị chương trình KHÁC chiếm (myvideo chẳng hạn) → tự chọn cổng
        # trống kế tiếp; đã có myvoice chạy sẵn đâu đó trong dải → dùng luôn bản đó.
        try:
            port, dang_chay = _chon_cong(uu_tien)
        except OSError as e:
            status.set("Không còn cổng trống — xem nhật ký")
            _dot("#fb7185")
            log(f"⛔ {e}")
            return
        if dang_chay:                     # đã chạy sẵn → KHÔNG bật cái thứ hai (lỗi bind)
            log(f"🌐 Bảng web đang chạy sẵn ở cổng {port} — dùng luôn bản đó.")
            _ready()
            return
        if port != uu_tien:
            log(_bao_doi_cong(uu_tien, port))
        log("🌐 Đang bật server…")
        env = {**os.environ,
               "MYVOICE_WEB_PORT": str(port),  # server nghe ĐÚNG cổng vừa chọn —
                                               # _poll/_ready/_http bên này trông vào nó
               "MYVOICE_WEB_NO_OPEN": "1",     # server đừng mở — _ready() bên này
                                               # tự mở, kẻo bung ra hai tab
               "PYTHONIOENCODING": "utf-8",
               "PYTHONUNBUFFERED": "1"}
        try:
            proc = subprocess.Popen(
                [_console_python(), "-m", "myvoice.web.server"],
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
        url = url_var.get()
        if url:
            webbrowser.open(url)
            log(f"↗ Đã mở: {url}")

    def _copy() -> None:
        root.clipboard_clear()
        root.clipboard_append(url_var.get())
        log("📋 Đã copy địa chỉ.")

    # ── Gọi chính server đang chạy (kèm token) ──────────────────────────────
    def _http(path: str, data: dict | None = None):
        """GET (data=None) hoặc POST form tới server. Trả dict nếu JSON, không thì
        trả chuỗi. Gọi TRONG LUỒNG NỀN — mạng chậm sẽ treo cửa sổ."""
        import json
        import urllib.parse
        import urllib.request
        try:
            token = TOKEN_FILE.read_text(encoding="utf-8").strip()
        except OSError:
            token = ""
        url = f"http://127.0.0.1:{port}{path}?token={urllib.parse.quote(token)}"
        body = urllib.parse.urlencode(data).encode() if data is not None else None
        with urllib.request.urlopen(url, data=body, timeout=30) as r:
            raw = r.read().decode("utf-8", "replace")
        try:
            return json.loads(raw)
        except ValueError:
            return raw

    # ── 🗑 Xóa output ───────────────────────────────────────────────────────
    def _clear_output() -> None:
        """Nhờ CHÍNH server xoá (POST /giongnoi/xoaketqua) — dùng lại đúng đường đã
        kiểm của bản web: mọi thứ vào THÙNG RÁC Windows, file kịch_bản/ được tạo lại
        bản rỗng. Không tự viết lệnh xoá ở đây để khỏi lệch nhau và khỏi xoá hẳn."""
        if not messagebox.askyesno(
                "Xóa output",
                "Đưa vào THÙNG RÁC Windows (khôi phục lại được):\n\n"
                "  • toàn bộ output/\n"
                "  • các thư mục tập (01, 02, …)\n"
                "  • file trong kịch_bản/ (tạo lại bản rỗng)\n\n"
                "Đang có việc chạy trong hàng đợi thì nên dừng trước.\n\nXoá?",
                icon="warning", default="no"):
            return
        btn_clear.config(state="disabled")
        log("🗑 Đang đưa vào Thùng rác…")

        def work() -> None:
            try:
                _http("/giongnoi/xoaketqua", {"confirm": "1"})
                lines.put("🗑 Đã xoá xong (chi tiết ở các dòng nhật ký của server).\n")
            except Exception as e:
                lines.put(f"❌ Xoá output lỗi: {e}\n")
            root.after(0, lambda: btn_clear.config(state="normal"))

        threading.Thread(target=work, daemon=True).start()

    # ── ⏻ "Xong hết thì tắt máy" / 🌙 "cho máy ngủ" — công tắc từ xa của hai ô trên
    # trang web. Server (myvoice/web/power.py) mới là nơi canh hàng đợi + đếm ngược +
    # phát lệnh; cửa sổ này KHÔNG tự hẹn `shutdown /s` hay tự ngủ (hai bộ đếm thì đá
    # nhau). Bấm ô là POST /hangdoi/tatmay (on=1 tắt máy, ngu=1 ngủ, không gì = tắt),
    # rồi soi lại /api/trangthai để vẽ đúng khi người ta tick bên trang web hay
    # server tự bỏ tick lúc hết giờ. Một "mode" duy nhất: "" / "shutdown" / "sleep".
    #
    # Chống "GET cũ ghi đè POST mới" (bài học 08/09/2026 với ô 🌙 cũ): seq tăng mỗi
    # lần bấm; kết quả GET chỉ được ghi khi seq lúc xin bằng seq hiện tại VÀ không
    # còn POST nào đang bay (pending). Bấm là ghi flags ngay (lạc quan), POST hỏng
    # thì thử lại một lần rồi mới hỏi lại server.
    sync_lock = threading.Lock()
    flags.update(drawn="", seq=0, pending=0)
    NHAN = {"shutdown": "tắt máy", "sleep": "cho máy ngủ"}
    ICON = {"shutdown": "⏻", "sleep": "🌙"}

    def _mode_of(st: dict) -> str:
        """Chế độ server đang bật, đọc từ /api/trangthai. Server cũ (trước 31/10/2026)
        không có "shutdown_mode" thì suy từ cờ armed."""
        mode = st.get("shutdown_mode")
        if mode is None:
            mode = "shutdown" if st.get("shutdown_armed") else ""
        return mode if mode in NHAN else ""

    def _apply_state(st: dict, seq: int) -> None:
        """Ghi trạng thái ⏻/🌙 server trả về vào flags — BỎ QUA nếu đã cũ (xem trên)."""
        with sync_lock:
            if seq != flags["seq"] or flags["pending"]:
                return
            flags["mode"] = _mode_of(st)
            flags["left"] = st.get("shutdown_left") or ""

    def _post_shutdown(mode: str) -> None:
        """Đặt chế độ ("" / "shutdown" / "sleep") ở server. Ghi flags NGAY (ô tick
        khớp tức thì), gọi mạng ở luồng nền; hỏng thì thử lại một lần, vẫn hỏng thì
        hỏi lại server để ô tick vẽ theo sự thật chứ không theo ý vừa bấm."""
        with sync_lock:
            flags["seq"] += 1
            flags["pending"] += 1
            flags["mode"] = mode
            if not mode:
                flags["left"] = ""
        data = {"shutdown": {"on": "1"}, "sleep": {"ngu": "1"}}.get(mode, {})

        def work() -> None:
            import time
            err = None
            for lan in (1, 2):
                try:
                    _http("/hangdoi/tatmay", data)
                    err = None
                    break
                except Exception as e:
                    err = e
                    if lan == 1:
                        time.sleep(2)
            with sync_lock:
                flags["pending"] -= 1
            if err is not None:
                lines.put(f"❌ Không đặt được chế độ tắt máy/ngủ ở server ({err}) — "
                          "ô ⏻/🌙 sẽ vẽ lại theo trạng thái thật của server.\n")
                _sync_shutdown_now()
        threading.Thread(target=work, daemon=True).start()

    def _sync_shutdown_now() -> None:
        """Hỏi NGAY trạng thái ⏻ của server (không đợi lượt poll): lúc server vừa
        sẵn sàng — server đang chạy sẵn có thể đã bật ⏻, ô ở đây phải khớp — và sau
        khi POST hỏng. Chạy luồng nền."""
        with sync_lock:
            seq = flags["seq"]

        def work() -> None:
            try:
                st = _http("/api/trangthai")
            except Exception:
                return
            if isinstance(st, dict):
                _apply_state(st, seq)
        threading.Thread(target=work, daemon=True).start()

    def _draw(mode: str, source: str) -> None:
        """Nơi DUY NHẤT đổi hai ô tick. Chạy trên luồng Tk.

        mode: "" (tắt) / "shutdown" (⏻) / "sleep" (🌙) — hai ô loại trừ nhau nên vẽ
        cả hai theo một giá trị, không bao giờ cùng tick.
        source="user"  : bấm ở cửa sổ này → đẩy lên server.
        source="server": server báo đổi (tick bên trang web, hoặc hết giờ tự bỏ tick)
                         → chỉ vẽ lại, KHÔNG POST ngược kẻo hai bên đá nhau vô tận.
        """
        if mode == flags["drawn"]:
            return
        prev, flags["drawn"] = flags["drawn"], mode
        var_shutdown.set(mode == "shutdown")
        var_sleep.set(mode == "sleep")
        delay = SLEEP_DELAY_MIN if mode == "sleep" else SHUTDOWN_DELAY_MIN
        nhan_cu = NHAN.get(prev, "tắt máy")
        icon_cu = ICON.get(prev, "⏻")
        if source == "user":
            _post_shutdown(mode)
            log(f"{ICON[mode]} Bật {NHAN[mode]} khi xong: hàng đợi web xong hết + rảnh "
                f"{delay} phút thì {NHAN[mode]} (huỷ: bỏ tick)." if mode
                else f"{icon_cu} Đã tắt chế độ tự động {nhan_cu}.")
        else:
            log(f"{ICON[mode]} Server đang bật {NHAN[mode]} khi xong — không muốn thì bỏ tick."
                if mode else
                f"{icon_cu} Server đã tắt chế độ {nhan_cu} (bỏ tick bên trang web / đã hết giờ).")

    def _click_shutdown() -> None:
        _draw("shutdown" if var_shutdown.get() else "", source="user")

    def _click_sleep() -> None:
        _draw("sleep" if var_sleep.get() else "", source="user")

    def _shutdown_sync() -> None:
        """Mỗi giây soi flags (luồng nền ghi) → vẽ ô ⏻/🌙 + dòng đếm ngược. Server là
        nguồn sự thật, nhưng KHÔNG đụng gì khi còn POST của mình đang bay."""
        with sync_lock:
            mode = flags["mode"]
            left = flags["left"] or ""
            pending = flags["pending"]
        if mode is not None and not pending and mode != flags["drawn"]:
            _draw(mode, source="server")
        drawn = flags["drawn"]
        shutdown_note.set(f"⏳ {NHAN[drawn]} sau {left} — huỷ: bỏ tick" if left and drawn
                          else ("chờ hàng đợi xong hết" if drawn else ""))
        root.after(1000, _shutdown_sync)

    def _state_watcher() -> None:
        """Luồng nền: 5 giây hỏi /api/trangthai một lần, lấy trạng thái ⏻ của server
        về cho _shutdown_sync vẽ lại (qua _apply_state, có lọc kết quả cũ)."""
        import time
        while True:
            time.sleep(5)
            with sync_lock:
                seq = flags["seq"]
            try:
                st = _http("/api/trangthai")
            except Exception:
                continue                     # server tắt/chưa lên → thử lại lượt sau
            if isinstance(st, dict):
                _apply_state(st, seq)

    def _close() -> None:
        if flags["drawn"]:
            # Bộ đếm ⏻/🌙 nằm TRONG server: đóng cửa sổ mà server do mình bật thì server
            # tắt theo → hết hẹn; server của tiến trình khác thì vẫn đếm tiếp.
            nhan = NHAN.get(flags["drawn"], "tắt máy")
            log(f"⏻ Tắt server = huỷ luôn lệnh {nhan} khi xong." if owner else
                f"⏻ Server vẫn chạy (tiến trình khác) nên vẫn {nhan} khi xong — "
                "huỷ: bỏ tick trên trang web.")
        if owner:
            log("⏹ Đang tắt server…")
            root.update_idletasks()
            _stop_server()
        root.destroy()

    btn_open.config(command=_open)
    btn_copy.config(command=_copy)
    btn_clear.config(command=_clear_output)
    btn_quit.config(command=_close)
    chk_shutdown.config(command=_click_shutdown)
    chk_sleep.config(command=_click_sleep)
    root.protocol("WM_DELETE_WINDOW", _close)
    url_entry.bind("<Double-Button-1>", lambda _e: _open())

    threading.Thread(target=_state_watcher, daemon=True).start()
    _shutdown_sync()
    root.after(100, _start)
    _drain()
    root.mainloop()
    _stop_server()          # phòng khi cửa sổ bị đóng bằng đường khác
    return 0


def main(argv: list[str]) -> int:
    if VENV_PY.exists() and not _is_venv_python():
        print(f"↻ Chạy lại bằng python của dự án: {VENV_PY}")
        return subprocess.call([str(VENV_PY), str(Path(__file__).resolve()), *argv],
                               cwd=str(ROOT))

    if not VENV_PY.exists():
        print(f"⚠️ Không thấy {VENV_PY} — đang dùng {sys.executable}. "
              "Thiếu thư viện thì tạo lại venv của dự án.")

    sys.path.insert(0, str(ROOT))
    if "--gui" in argv:
        print("🖥  Mở GUI Tkinter (bản cũ)…")
        # PHẢI truyền --gui: chạy amain_taogiong_gui.py không cờ là nó chuyển ngược về web.
        return subprocess.call([sys.executable, str(GUI), "--gui"], cwd=str(ROOT))

    if "--console" not in argv:
        try:
            return _run_launcher(_web_port())
        except Exception as e:      # máy không có tkinter → quay về bản console
            _report_fatal(e)
            if not sys.stdout:      # chạy bằng pythonw: không có console để quay về
                return 1
            print(f"⚠️ Không mở được cửa sổ ({e}) — chạy bản console.")

    from myvoice.web.server import main as run_server     # noqa: E402
    run_server()                                          # chặn tới khi Ctrl+C
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
