"""“Xong hết thì TẮT MÁY” — ô ⏻ của bảng điều khiển web.

(26/10/2026: thay cho ô 🌙 “cho máy ngủ” — user bỏ chế độ ngủ ở cả web, cửa sổ
chay.py lẫn GUI Tkinter, chỉ giữ tắt máy. Đừng thêm 🌙 lại.)

Cách chạy: một luồng nền hỏi CẢ BA hàng đợi (chính + đăng YouTube + Facebook) vài
giây một lần. Ba chốt an toàn, học từ ô ⏻ bên GUI:

  • phải TỪNG THẤY BẬN rồi mới rảnh — tick lúc chưa chạy gì thì không tắt máy ngay;
  • rảnh rồi vẫn đếm ngược SHUTDOWN_DELAY_MIN phút, có việc mới chen vào là huỷ đếm
    (bước này xong thường nối tiếp bước sau, hàng đợi rảnh vài giây là chuyện thường);
  • bộ đếm nằm TRONG server, lệnh `shutdown` chỉ phát ra đúng lúc hết giờ → bỏ tick
    trên trang web là huỷ, kể cả lúc đang đếm ngược, không cần `shutdown /a`.

Hết giờ thì tắt NGAY (shutdown /s /f /t 0): mọi app bị đóng không hỏi — đúng ý khi
chạy mẻ qua đêm không ai ngồi máy. Trước khi đếm còn tập dựng xong CHƯA đăng thì
ghi cảnh báo vào nhật ký đăng (chỉ báo, không tự đăng).

MẶC ĐỊNH TẮT mỗi lần mở server — muốn chạy qua đêm rồi tắt máy thì tick tay trên
trang web hoặc cửa sổ desktop (chay.py — công tắc từ xa của ô này).
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time

from . import core
from .jobs import fb_runner, log, runner, upload_runner

# Số phút chờ lấy CHUNG với GUI (amain_taogiong_gui.SHUTDOWN_DELAY_MIN) — ô ⏻ bên
# GUI và ô ⏻ trên trang web cùng một con số, sửa một chỗ là cả hai cùng đổi.
SHUTDOWN_DELAY_MIN = core.gui.SHUTDOWN_DELAY_MIN
POLL_SEC = 5.0
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


class ShutdownWhenDone:
    """Trạng thái của ô tick + luồng nền canh hàng đợi."""

    def __init__(self) -> None:
        # Mặc định TẮT (xem đầu file) — tick tay mới đếm giờ tắt.
        self._armed = False
        self._saw_busy = False
        self._due = 0.0            # 0 = chưa đếm ngược (mốc time.monotonic)
        self._warn_due = False     # vừa bắt đầu đếm → soát tập chưa đăng (ngoài lock)
        self._lock = threading.Lock()
        threading.Thread(target=self._watch, daemon=True).start()

    # ── API cho tầng web ────────────────────────────────────────────────────
    def arm(self, on: bool) -> None:
        with self._lock:
            if on == self._armed:
                return
            self._armed = on
            self._saw_busy = False     # bật lại = đếm lại từ đầu, phải thấy bận đã
            counting, self._due = bool(self._due), 0.0
            self._warn_due = False
        if on:
            log(f"⏻ Bật tắt máy khi xong: hàng đợi xong hết + rảnh {SHUTDOWN_DELAY_MIN} "
                "phút thì tắt máy. Huỷ: bỏ tick trên trang web.")
        elif counting:
            log("✖ Đã huỷ đếm ngược tắt máy.")
        else:
            log("⏻ Đã tắt chế độ tắt máy khi xong.")

    def state(self) -> dict:
        """Dữ liệu cho khối hàng đợi (_queue.html, làm mới 2 giây/lần) và
        /api/trangthai (cửa sổ chay.py vẽ theo)."""
        with self._lock:
            left = max(0.0, self._due - time.monotonic()) if self._due else 0.0
            return {
                "armed": self._armed,
                "delay_min": SHUTDOWN_DELAY_MIN,
                "counting": bool(self._due),
                "left": f"{int(left) // 60}:{int(left) % 60:02d}" if self._due else "",
            }

    # ── Luồng nền ───────────────────────────────────────────────────────────
    def _watch(self) -> None:
        while True:
            time.sleep(POLL_SEC)
            try:
                due = self._tick()
                self._warn_pending_upload()   # ngoài _lock: hàm này quét thư mục
                if due:
                    self._shutdown_now()
            except Exception as e:          # luồng canh không được chết
                log(f"⚠️ Lỗi khi canh chế độ tắt máy: {e}")

    def _warn_pending_upload(self) -> None:
        """Bắt đầu đếm ngược mà còn tập dựng xong CHƯA đăng → nói ra.

        Hàng đợi rỗng KHÔNG đồng nghĩa “đã đăng hết”: việc đăng chỉ được nối khi ô
        “⬆ tự động đăng” bật lúc bấm chạy. Im lặng tắt máy rồi sáng ra mới biết
        cả mẻ chưa lên kênh là kiểu hỏng khó chịu nhất — nên đây là chỗ hỏi lại lần
        cuối, ngay trước khi tắt.

        Chỉ CẢNH BÁO, không tự đăng: đăng là việc hướng ra ngoài, không được tự ý
        làm thay chỉ vì máy sắp tắt.
        """
        with self._lock:
            if not self._warn_due:
                return
            self._warn_due = False
        try:
            pending = core.episodes_pending_upload()
        except Exception:
            return
        if pending:
            upload_runner.note(
                f"⚠️ Sắp tắt máy mà còn {len(pending)} tập dựng xong CHƯA đăng: "
                f"{', '.join(pending)}. Muốn đăng thì bỏ tick ⏻ rồi bấm "
                "“⬆ Đăng ngay các tập chưa đăng” — máy vẫn tắt đúng lịch nếu để yên.")

    def _tick(self) -> bool:
        """Một lượt kiểm tra → True nghĩa là ĐẾN GIỜ TẮT MÁY."""
        with self._lock:
            if not self._armed:
                return False
            # heavy_busy: việc "light" (xem kế hoạch Facebook…) không được tính —
            # bấm nút xem trước xong mà máy đếm ngược tắt thì vô lý. Hàng đợi
            # Facebook phải có mặt: đang tải video lên Page mà tắt máy là hỏng.
            if (runner.heavy_busy() or upload_runner.heavy_busy()
                    or fb_runner.heavy_busy()):
                self._saw_busy = True
                if self._due:               # việc mới chen vào giữa lúc đếm ngược
                    self._due = 0.0
                    self._warn_due = False
                    log("⏻ Có việc mới → huỷ đếm ngược, chờ xong hết đã.")
                return False
            if not self._saw_busy:          # tick lúc đang rảnh: chờ mẻ tới
                return False
            if not self._due:
                self._due = time.monotonic() + SHUTDOWN_DELAY_MIN * 60
                self._warn_due = True       # _warn_pending_upload lo phần soát
                log(f"⏻ Hàng đợi đã xong — máy sẽ TẮT sau {SHUTDOWN_DELAY_MIN} phút. "
                    "Huỷ: bỏ tick “Xong hết thì tắt máy” trên trang web.")
                return False
            if time.monotonic() < self._due:
                return False
            # Một lần duy nhất: hạ cờ TRƯỚC khi gọi lệnh — lệnh hỏng thì không gọi
            # lại mỗi 5 giây, mà cũng không còn tick treo cho mẻ sau.
            self._armed = False
            self._saw_busy = False
            self._due = 0.0
            return True

    def _shutdown_now(self) -> None:
        log("⏻ Hết giờ — đang TẮT MÁY (shutdown /s /f /t 0)…")
        try:
            r = subprocess.run(
                ["shutdown", "/s", "/f", "/t", "0", "/c",
                 "myvoice da chay xong - tat may."],
                check=False, capture_output=True, text=True,
                creationflags=CREATE_NO_WINDOW)
        except Exception as e:
            log(f"❌ Không tắt máy được: {e}")
            return
        if r.returncode:
            log(f"❌ Không tắt máy được (mã {r.returncode}): "
                f"{(r.stderr or r.stdout or '').strip()}")


watcher = ShutdownWhenDone()
