"""Bật myvoice — bản WEB.  Mở file này rồi bấm ▶ Run trong VS Code là chạy.

Vì sao có file này: VS Code chỉ bấm ▶ chạy được file .py, không chạy .bat.
Nội dung y hệt `chay.bat` (và `chay_gui.bat` khi thêm cờ --gui).

Chạy bằng BẤT KỲ python nào cũng được: nếu interpreter đang dùng không phải venv
của dự án thì file tự khởi động lại bằng venv\\Scripts\\python.exe — không thì sẽ
thiếu fastapi/uvicorn/torch.

    python myvoice/chay.py            → cửa sổ nhỏ: server chạy nền + nút mở link web
    python myvoice/chay.py --console  → chạy thẳng trong console như trước (không cửa sổ)
    python myvoice/chay.py --gui      → GUI Tkinter bản cũ (amain_taogiong_gui.py)

Cửa sổ nhỏ (mặc định) tự bật server rồi ĐỢI bạn bấm nút mới mở trình duyệt — không
tự mở như bản console. Đóng cửa sổ = tắt server (nếu server do cửa sổ này bật).
Trong cửa sổ có sẵn: 🌐 mở link · 📋 copy link · 🗑 xóa output (vào Thùng rác) ·
và hai chế độ khi hàng đợi web chạy xong hết — ⏻ tắt máy hoặc 🌙 cho máy ngủ
(chọn một, tick cái này thì cái kia tự bỏ).
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
LOG_LOI = ROOT / "myvoice" / "chay_loi.log"      # lỗi khi chạy bằng pythonw (không console)

# Server chạy nền, không cần cửa sổ console riêng (nhật ký đã hiện trong cửa sổ này).
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# Số phút chờ trước khi tắt máy khi bật ô "⏻ Tự động tắt máy" (giống GUI Tkinter).
# Huỷ bất cứ lúc nào: mở CMD gõ  shutdown /a
SHUTDOWN_DELAY_MIN = 5

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
        return int(os.environ.get("MYVOICE_WEB_PORT", "8765"))
    except ValueError:
        return 8765


def _port_busy(port: int, timeout: float = 0.3) -> bool:
    """Đã có ai nghe ở cổng này chưa (nhiều khả năng là server đang chạy sẵn)."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _web_url(port: int) -> str:
    """Địa chỉ kèm token — server ghi token ra web/token.txt lúc khởi động, nên chỉ
    đọc được SAU khi server lên. Chưa có token thì trả địa chỉ trần (web sẽ hỏi)."""
    from urllib.parse import quote
    try:
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        token = ""
    return f"http://127.0.0.1:{port}/" + (f"?token={quote(token)}" if token else "")


# ── Cửa sổ nhỏ: bật server nền + nút mở link ────────────────────────────────
def _run_launcher(port: int) -> int:
    """Cửa sổ Tkinter tối giản: trạng thái · địa chỉ · nút mở link · nhật ký.

    Server chạy trong tiến trình con KHÔNG có console (CREATE_NO_WINDOW) nên mọi
    thông báo/lỗi của nó được bơm vào ô nhật ký dưới — bỏ console mà vẫn nhìn thấy
    lỗi khởi động. Đóng cửa sổ thì tắt luôn server nếu server do cửa sổ này bật.
    """
    import queue
    import tkinter as tk
    import webbrowser
    from tkinter import messagebox, ttk

    proc: subprocess.Popen | None = None
    owner = False                      # server có phải do cửa sổ này bật không
    lines: "queue.Queue[str]" = queue.Queue()
    # Cờ dùng CHUNG với luồng nền — không đọc biến Tk ngoài luồng Tk (không an toàn).
    # sleep_armed/sleep_left: trạng thái chế độ ngủ ĐỌC VỀ TỪ SERVER (server mới là
    # nơi giữ bộ đếm), luồng nền ghi vào đây rồi _sleep_sync bên luồng Tk đọc ra.
    flags = {"auto_shutdown": False, "saw_busy": False, "scheduled": False,
             "sleep_armed": None, "sleep_left": ""}

    root = tk.Tk()
    root.title("myvoice — bảng điều khiển web")
    root.geometry("640x420")
    root.minsize(520, 300)

    wrap = ttk.Frame(root, padding=12)
    wrap.pack(fill="both", expand=True)
    wrap.columnconfigure(0, weight=1)
    wrap.rowconfigure(5, weight=1)          # hàng nhật ký giãn

    status = tk.StringVar(value="⏳ Đang bật server…")
    ttk.Label(wrap, textvariable=status, font=("Segoe UI", 11, "bold")).grid(
        row=0, column=0, sticky="w")

    url_var = tk.StringVar(value="")
    url_entry = ttk.Entry(wrap, textvariable=url_var, state="readonly")
    url_entry.grid(row=1, column=0, sticky="ew", pady=(8, 0))

    btns = ttk.Frame(wrap)
    btns.grid(row=2, column=0, sticky="w", pady=(10, 8))
    btn_open = ttk.Button(btns, text="🌐  Mở link web", state="disabled")
    btn_open.pack(side="left")
    btn_copy = ttk.Button(btns, text="📋  Copy link", state="disabled")
    btn_copy.pack(side="left", padx=(8, 0))
    btn_clear = ttk.Button(btns, text="🗑  Xóa output", state="disabled")
    btn_clear.pack(side="left", padx=(8, 0))
    btn_quit = ttk.Button(btns, text="⏹  Tắt & thoát")
    btn_quit.pack(side="left", padx=(8, 0))

    # Hai chế độ "xong hết thì…", CHỌN MỘT (tick cái này thì cái kia tự bỏ):
    #   ⏻ tắt máy  — cửa sổ này tự canh: hỏi server 15 giây/lần rồi hẹn `shutdown /s`.
    #   🌙 cho ngủ — GIAO CHO SERVER: bảng web đã có sẵn bộ đếm (web/power.py), ở đây
    #                chỉ bật/tắt hộ (POST /hangdoi/ngu) và soi lại trạng thái. Làm thêm
    #                một bộ đếm thứ hai ở đây thì hai bên đá nhau.
    sd_row = ttk.Frame(wrap)
    sd_row.grid(row=3, column=0, sticky="w", pady=(0, 2))
    var_shutdown = tk.BooleanVar(value=False)
    chk_shutdown = ttk.Checkbutton(
        sd_row, text=f"⏻  Tự động tắt máy khi chạy xong (sau {SHUTDOWN_DELAY_MIN} phút)",
        variable=var_shutdown, state="disabled")
    chk_shutdown.pack(side="left")
    ttk.Label(sd_row, text="huỷ: mở CMD gõ  shutdown /a",
              foreground="#888").pack(side="left", padx=(10, 0))

    sl_row = ttk.Frame(wrap)
    sl_row.grid(row=4, column=0, sticky="w", pady=(0, 8))
    var_sleep = tk.BooleanVar(value=False)
    chk_sleep = ttk.Checkbutton(
        sl_row, text="🌙  Tự động cho máy NGỦ khi chạy xong",
        variable=var_sleep, state="disabled")
    chk_sleep.pack(side="left")
    sleep_note = tk.StringVar(value="")
    ttk.Label(sl_row, textvariable=sleep_note,
              foreground="#888").pack(side="left", padx=(10, 0))

    log_box = tk.Text(wrap, height=10, wrap="word", state="disabled",
                      font=("Consolas", 9))
    log_box.grid(row=5, column=0, sticky="nsew")
    scroll = ttk.Scrollbar(wrap, orient="vertical", command=log_box.yview)
    scroll.grid(row=5, column=1, sticky="ns")
    log_box.config(yscrollcommand=scroll.set)

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
        status.set(f"● Đang chạy — cổng {port}"
                   + ("" if owner else "  (tiến trình khác bật sẵn)"))
        for w in (btn_open, btn_copy, btn_clear, chk_shutdown, chk_sleep):
            w.config(state="normal")
        if not owner:
            btn_quit.config(text="✖  Đóng cửa sổ")
        log(f"🌐 Sẵn sàng: {url_var.get()}")
        log("Bấm '🌐 Mở link web' để mở trong trình duyệt.")

    def _poll(n: int = 0) -> None:
        if _port_busy(port):
            _ready()
            return
        if proc is not None and proc.poll() is not None:
            status.set(f"⛔ Server tắt ngay khi bật (mã {proc.returncode}) — xem nhật ký")
            return
        if n >= 75:                       # ~30 giây
            status.set("⚠️ Server chưa phản hồi sau 30 giây — xem nhật ký")
            return
        root.after(400, _poll, n + 1)

    def _start() -> None:
        nonlocal proc, owner
        if _port_busy(port):              # đã chạy sẵn → KHÔNG bật cái thứ hai (lỗi bind)
            log(f"🌐 Bảng web đang chạy sẵn ở cổng {port} — dùng luôn bản đó.")
            _ready()
            return
        log("🌐 Đang bật server…")
        env = {**os.environ,
               "MYVOICE_WEB_NO_OPEN": "1",     # đợi bấm nút, không tự mở trình duyệt
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
            status.set("⛔ Không bật được server")
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

    # ── 🌙 Tự động cho máy ngủ khi hàng đợi chạy xong ────────────────────────
    # Việc canh hàng đợi + đếm ngược do SERVER làm (myvoice/web/power.py) — ô tick ở
    # đây chỉ là cái công tắc từ xa của ô 🌙 trên trang web, nên tick ở đâu cũng ra
    # một kết quả và nhật ký ngủ tự hiện trong ô log này (log server chảy vào đây).
    def _post_sleep(on: bool) -> None:
        """Bật/tắt chế độ ngủ ở server. Chạy luồng nền — có chạm mạng."""
        def work() -> None:
            try:
                _http("/hangdoi/ngu", {"on": "1"} if on else {})
            except Exception as e:
                lines.put(f"❌ Không đặt được chế độ ngủ: {e}\n")
        threading.Thread(target=work, daemon=True).start()

    def _toggle_sleep() -> None:
        if var_sleep.get() and var_shutdown.get():   # hai chế độ loại trừ nhau
            var_shutdown.set(False)
            _toggle_shutdown()          # huỷ luôn lệnh tắt máy đã hẹn (nếu có)
        _post_sleep(bool(var_sleep.get()))
        log("🌙 Bật cho máy ngủ: hàng đợi web xong hết là máy ngủ (huỷ: bỏ tick)."
            if var_sleep.get() else "🌙 Đã tắt chế độ tự động cho máy ngủ.")

    def _sleep_sync() -> None:
        """Soi lại ô 🌙 theo SERVER — nguồn sự thật là nó: tick/bỏ tick bên trang web,
        hay ngủ xong server tự bỏ tick, thì ô ở đây cũng đổi theo. Chạy trên luồng Tk,
        chỉ đọc `flags` mà luồng nền đã ghi sẵn."""
        armed = flags.get("sleep_armed")
        if armed is not None and bool(armed) != bool(var_sleep.get()):
            var_sleep.set(bool(armed))
        left = flags.get("sleep_left") or ""
        sleep_note.set(f"⏳ ngủ sau {left} — huỷ: bỏ tick" if left else
                       ("chờ hàng đợi xong hết" if var_sleep.get() else ""))
        root.after(1000, _sleep_sync)

    # ── ⏻ Tự động tắt máy khi hàng đợi chạy xong ────────────────────────────
    def _toggle_shutdown() -> None:
        flags["auto_shutdown"] = bool(var_shutdown.get())
        if flags["auto_shutdown"]:
            flags["saw_busy"] = False        # phải THẤY BẬN rồi rảnh mới tắt
            if var_sleep.get():              # hai chế độ loại trừ nhau
                var_sleep.set(False)
                _post_sleep(False)
                log("🌙 Bỏ chế độ cho máy ngủ (đã chọn tắt máy).")
            log(f"⏻ Bật tự động tắt máy: hàng đợi web xong hết thì tắt máy sau "
                f"{SHUTDOWN_DELAY_MIN} phút.")
            return
        log("⏻ Đã tắt chế độ tự động tắt máy.")
        if flags["scheduled"]:               # đã hẹn rồi thì huỷ luôn lệnh hẹn
            try:
                subprocess.run(["shutdown", "/a"], check=False,
                               creationflags=CREATE_NO_WINDOW)
                log("✖ Đã huỷ lệnh hẹn tắt máy.")
            except Exception as e:
                log(f"⚠️ Không huỷ được lệnh tắt máy ({e}) — mở CMD gõ: shutdown /a")
            flags["scheduled"] = False

    def _shutdown_watcher() -> None:
        """Luồng nền: 15 giây hỏi /api/trangthai một lần — vừa canh giờ tắt máy, vừa
        lấy trạng thái chế độ ngủ của server về cho _sleep_sync vẽ lại ô 🌙.

        CHỈ hẹn tắt khi đã từng thấy bận rồi mới rảnh — tick lúc chưa chạy gì thì
        không tắt máy ngay."""
        import time
        while True:
            time.sleep(15)
            try:
                st = _http("/api/trangthai")
            except Exception:
                continue                     # server tắt/chưa lên → thử lại lượt sau
            if not isinstance(st, dict):
                continue
            flags["sleep_armed"] = st.get("sleep_armed")
            flags["sleep_left"] = st.get("sleep_left") or ""
            if not flags["auto_shutdown"] or flags["scheduled"]:
                continue
            if st.get("busy") or st.get("upload_busy"):
                flags["saw_busy"] = True
                continue
            if not flags["saw_busy"]:
                continue
            flags["scheduled"] = True
            lines.put(f"⏻ Hàng đợi đã xong — HẸN TẮT MÁY sau {SHUTDOWN_DELAY_MIN} "
                      "phút. Huỷ: mở CMD gõ  shutdown /a\n")
            try:
                subprocess.run(
                    ["shutdown", "/s", "/t", str(SHUTDOWN_DELAY_MIN * 60), "/c",
                     f"myvoice da chay xong - tat may sau {SHUTDOWN_DELAY_MIN} phut. "
                     "Huy: shutdown /a"],
                    check=False, creationflags=CREATE_NO_WINDOW)
            except Exception as e:
                lines.put(f"❌ Không hẹn được tắt máy: {e}\n")

    def _close() -> None:
        if flags["scheduled"]:
            log("⚠️ Đã hẹn tắt máy — đóng cửa sổ KHÔNG huỷ lệnh đó (huỷ: shutdown /a).")
        if var_sleep.get() and owner:
            # Bộ đếm ngủ nằm TRONG server, mà đóng cửa sổ là tắt server → hết ngủ.
            log("🌙 Tắt server = huỷ luôn lệnh cho máy ngủ.")
        if owner:
            log("⏹ Đang tắt server…")
            root.update_idletasks()
            _stop_server()
        root.destroy()

    btn_open.config(command=_open)
    btn_copy.config(command=_copy)
    btn_clear.config(command=_clear_output)
    btn_quit.config(command=_close)
    chk_shutdown.config(command=_toggle_shutdown)
    chk_sleep.config(command=_toggle_sleep)
    root.protocol("WM_DELETE_WINDOW", _close)
    url_entry.bind("<Double-Button-1>", lambda _e: _open())

    threading.Thread(target=_shutdown_watcher, daemon=True).start()
    _sleep_sync()
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
        return subprocess.call([sys.executable, str(GUI)], cwd=str(ROOT))

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
