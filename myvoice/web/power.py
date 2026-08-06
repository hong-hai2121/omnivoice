"""“Xong hết thì cho máy NGỦ” — tuỳ chọn của bảng điều khiển web.

NGỦ chứ không TẮT MÁY: chạy mẻ qua đêm xong chỉ cần máy thôi tốn điện; sáng chạm
chuột là mọi thứ còn nguyên — server web, hàng đợi, phiên đăng nhập YouTube,
Firefox của bước dịch. Tắt máy thì sáng ra phải dựng lại tất cả từ đầu.

Cách chạy: một luồng nền hỏi CẢ HAI hàng đợi (chính + đăng YouTube) vài giây một
lần. Ba chốt an toàn, học từ ô ⏻ bên GUI:

  • phải TỪNG THẤY BẬN rồi mới rảnh — tick lúc chưa chạy gì thì không úp máy ngay;
  • rảnh rồi vẫn đếm ngược SLEEP_DELAY_MIN phút, có việc mới chen vào là huỷ đếm
    (bước này xong thường nối tiếp bước sau, hàng đợi rảnh vài giây là chuyện thường);
  • ngủ xong TỰ BỎ TICK — một lần duy nhất, mẻ sau không bị ngủ bất ngờ.

Bỏ tick trên trang web là huỷ, kể cả khi đang đếm ngược.
"""

from __future__ import annotations

import threading
import time

from . import core
from .jobs import log, runner, upload_runner

# Lệnh ngủ + số phút chờ lấy CHUNG với GUI (amain_taogiong_gui) — ô 🌙 bên GUI và ô
# 🌙 trên trang web phải cư xử y hệt nhau, sửa một chỗ là cả hai cùng đổi.
suspend = core.gui.suspend_computer
SLEEP_DELAY_MIN = core.gui.SLEEP_DELAY_MIN
POLL_SEC = 5.0


class SleepWhenDone:
    """Trạng thái của ô tick + luồng nền canh hàng đợi."""

    def __init__(self) -> None:
        self._armed = False
        self._saw_busy = False
        self._due = 0.0            # 0 = chưa đếm ngược (mốc time.monotonic)
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
        if on:
            log(f"🌙 Bật chế độ ngủ: hàng đợi xong hết + rảnh {SLEEP_DELAY_MIN} "
                "phút thì máy ngủ. Huỷ: bỏ tick trên trang web.")
        elif counting:
            log("✖ Đã huỷ đếm ngược ngủ.")
        else:
            log("🌙 Đã tắt chế độ ngủ khi xong.")

    def state(self) -> dict:
        """Dữ liệu cho khối hàng đợi (_queue.html), làm mới 2 giây/lần."""
        with self._lock:
            left = max(0.0, self._due - time.monotonic()) if self._due else 0.0
            return {
                "armed": self._armed,
                "delay_min": SLEEP_DELAY_MIN,
                "counting": bool(self._due),
                "left": f"{int(left) // 60}:{int(left) % 60:02d}" if self._due else "",
            }

    # ── Luồng nền ───────────────────────────────────────────────────────────
    def _watch(self) -> None:
        while True:
            time.sleep(POLL_SEC)
            try:
                if self._tick():
                    self._sleep_now()
            except Exception as e:          # luồng canh không được chết
                log(f"⚠️ Lỗi khi canh chế độ ngủ: {e}")

    def _tick(self) -> bool:
        """Một lượt kiểm tra → True nghĩa là ĐẾN GIỜ NGỦ."""
        with self._lock:
            if not self._armed:
                return False
            if runner.busy() or upload_runner.busy():
                self._saw_busy = True
                if self._due:               # việc mới chen vào giữa lúc đếm ngược
                    self._due = 0.0
                    log("🌙 Có việc mới → huỷ đếm ngược, chờ xong hết đã.")
                return False
            if not self._saw_busy:          # tick lúc đang rảnh: chờ mẻ tới
                return False
            if not self._due:
                self._due = time.monotonic() + SLEEP_DELAY_MIN * 60
                log(f"🌙 Hàng đợi đã xong — máy sẽ NGỦ sau {SLEEP_DELAY_MIN} phút. "
                    "Huỷ: bỏ tick “Xong hết thì cho máy ngủ” trên trang web.")
                return False
            if time.monotonic() < self._due:
                return False
            # Một lần duy nhất: hạ cờ TRƯỚC khi ngủ, khỏi ngủ lại ngay sau khi dậy.
            self._armed = False
            self._saw_busy = False
            self._due = 0.0
            return True

    def _sleep_now(self) -> None:
        log("🌙 Cho máy ngủ… (chạm chuột/bàn phím là dậy, server vẫn còn nguyên)")
        err = suspend()
        if err:
            log(f"❌ Không cho máy ngủ được: {err}")
            return
        log("☀️ Máy đã dậy — bảng điều khiển chạy tiếp bình thường.")


watcher = SleepWhenDone()
