# -*- coding: utf-8 -*-
"""“Xong hết thì cho máy NGỦ / TẮT MÁY” — tuỳ chọn trên khối hàng đợi web myvideo.

Phỏng theo myvoice/web/power.py nhưng đứng RIÊNG: bên đó lấy lệnh ngủ từ module
GUI (amain_taogiong_gui) — import là kéo cả GUI nặng vào server; myvideo chỉ
mượn ý tưởng chức năng nên chép lại đúng hàm ngủ ~20 dòng.

Ba chốt an toàn (học từ myvoice):
  • phải TỪNG THẤY hàng đợi BẬN rồi mới tính rảnh — tick lúc chưa chạy gì thì
    không úp máy ngay;
  • rảnh rồi vẫn đếm ngược N phút, có việc mới chen vào là huỷ đếm
    (bước này xong nối bước sau, hàng đợi rảnh vài giây là chuyện thường);
  • thực hiện xong TỰ BỎ TICK — một lần duy nhất, mẻ sau không bị bất ngờ.

Bỏ tick trên trang là huỷ, kể cả khi đang đếm ngược. NGỦ chờ 3 phút (lỡ ngủ thì
chạm chuột là dậy, không mất gì); TẮT MÁY chờ 5 phút và còn hẹn thêm 60 giây
qua `shutdown /s /t 60` — đổi ý thì mở CMD gõ `shutdown /a`.
"""

from __future__ import annotations

import logging
import subprocess
import threading
import time

from .jobs import q

CREATE_NO_WINDOW = 0x08000000
POLL_SEC = 5.0
# Ngủ dễ huỷ hơn nhiều (chạm chuột là dậy) nên chờ ngắn hơn tắt máy.
DELAY_MIN = {"ngu": 3, "tat": 5}
MODE_LABEL = {"ngu": "NGỦ", "tat": "TẮT MÁY"}


def suspend_computer() -> str:
    """Đưa máy vào chế độ NGỦ ngay. Trả "" nếu gọi được, hoặc mô tả lỗi.

    Chép từ myvoice/scripts/amain_taogiong_gui.suspend_computer (xem chú thích
    đầu file vì sao chép thay vì import). Tham số (0, 1, 0): số 0 đầu là xin
    NGỦ chứ không ngủ đông; máy bật sẵn hibernate muốn ngủ thật thì tắt một
    lần bằng `powercfg -h off`.
    """
    import ctypes
    try:
        if ctypes.windll.powrprof.SetSuspendState(0, 1, 0):
            return ""
    except Exception as e:
        logging.warning(f"⚠️ Gọi SetSuspendState không được ({e}) — thử lại bằng rundll32.")
    try:
        subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
                       check=False, creationflags=CREATE_NO_WINDOW)
        return ""
    except Exception as e:
        return str(e)


class PowerWhenDone:
    """Trạng thái ô tick + chế độ (ngủ/tắt) + luồng nền canh hàng đợi."""

    def __init__(self) -> None:
        self._armed = False
        self._mode = "ngu"
        self._saw_busy = False
        self._due = 0.0            # 0 = chưa đếm ngược (mốc time.monotonic)
        self._lock = threading.Lock()
        threading.Thread(target=self._watch, daemon=True).start()

    # ── API cho tầng web ────────────────────────────────────────────────────
    def arm(self, on: bool, mode: str = "") -> None:
        with self._lock:
            if mode not in DELAY_MIN:
                mode = self._mode
            if on == self._armed and mode == self._mode:
                return
            counting = bool(self._due)
            self._armed, self._mode = on, mode
            self._saw_busy = False     # đổi trạng thái = đếm lại, phải thấy bận đã
            self._due = 0.0
        if on:
            q.note(f"{'🌙' if mode == 'ngu' else '⏻'} Bật chế độ {MODE_LABEL[mode]} khi xong: "
                   f"hàng đợi xong hết + rảnh {DELAY_MIN[mode]} phút. Huỷ: bỏ tick trên trang.")
        elif counting:
            q.note("✖ Đã huỷ đếm ngược ngủ/tắt máy.")
        else:
            q.note("Đã tắt chế độ tự ngủ/tắt máy khi xong.")

    def state(self) -> dict:
        """Dữ liệu cho khối hàng đợi (_queue.html), làm mới 2 giây/lần."""
        with self._lock:
            left = max(0.0, self._due - time.monotonic()) if self._due else 0.0
            return {
                "armed": self._armed,
                "mode": self._mode,
                "delay_min": DELAY_MIN[self._mode],
                "counting": bool(self._due),
                "left": f"{int(left) // 60}:{int(left) % 60:02d}" if self._due else "",
            }

    # ── Luồng nền ───────────────────────────────────────────────────────────
    def _watch(self) -> None:
        while True:
            time.sleep(POLL_SEC)
            try:
                mode = self._tick()
                if mode:
                    self._fire(mode)
            except Exception as e:          # luồng canh không được chết
                q.note(f"⚠️ Lỗi khi canh chế độ ngủ/tắt máy: {e}")

    def _tick(self) -> str:
        """Một lượt kiểm tra → tên chế độ nếu ĐẾN GIỜ, "" nếu chưa."""
        with self._lock:
            if not self._armed:
                return ""
            if q.busy():
                self._saw_busy = True
                if self._due:               # việc mới chen vào giữa lúc đếm ngược
                    self._due = 0.0
                    q.note("Có việc mới → huỷ đếm ngược, chờ xong hết đã.")
                return ""
            if not self._saw_busy:          # tick lúc đang rảnh: chờ mẻ tới
                return ""
            if not self._due:
                self._due = time.monotonic() + DELAY_MIN[self._mode] * 60
                q.note(f"Hàng đợi đã xong — máy sẽ {MODE_LABEL[self._mode]} sau "
                       f"{DELAY_MIN[self._mode]} phút. Huỷ: bỏ tick trên trang.")
                return ""
            if time.monotonic() < self._due:
                return ""
            # Một lần duy nhất: hạ cờ TRƯỚC khi thực hiện.
            mode = self._mode
            self._armed = False
            self._saw_busy = False
            self._due = 0.0
            return mode

    def _fire(self, mode: str) -> None:
        if mode == "ngu":
            q.note("🌙 Cho máy ngủ… (chạm chuột/bàn phím là dậy, server vẫn còn nguyên)")
            err = suspend_computer()
            if err:
                q.note(f"❌ Không cho máy ngủ được: {err}")
                return
            q.note("☀️ Máy đã dậy — bảng điều khiển chạy tiếp bình thường.")
            return
        q.note("⏻ Hẹn TẮT MÁY sau 60 giây — đổi ý thì mở CMD gõ:  shutdown /a")
        try:
            subprocess.run(["shutdown", "/s", "/t", "60", "/c",
                            "myvideo: hang doi da xong. Huy: shutdown /a"],
                           check=False, creationflags=CREATE_NO_WINDOW)
        except Exception as e:
            q.note(f"❌ Không hẹn tắt máy được: {e}")


watcher = PowerWhenDone()
