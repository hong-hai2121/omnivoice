"""“Xong hết thì TẮT MÁY (⏻) / CHO MÁY NGỦ (🌙)” — hai ô của bảng điều khiển web.

Lịch sử: 🌙 là ô đầu tiên (ngủ: sáng chạm chuột là mọi thứ còn nguyên — server, hàng
đợi, phiên đăng nhập YouTube, Firefox của bước dịch). 26/10/2026 user bỏ 🌙, chỉ giữ
⏻ tắt máy. 31/10/2026 user cho 🌙 quay lại và hạ cả hai xuống chờ 1 phút. Hai ô dùng
CHUNG một bộ đếm: chỉ một chế độ (mode) được bật — "" (tắt) / "shutdown" / "sleep",
tick ô này là bỏ ô kia (hẹn tắt máy rồi lại cho ngủ là kiểu hỏng nhất).

Cách chạy: một luồng nền hỏi CẢ BA hàng đợi (chính + đăng YouTube + Facebook) vài
giây một lần. Ba chốt an toàn, học từ ô ⏻ bên GUI:

  • phải TỪNG THẤY BẬN rồi mới rảnh — tick lúc chưa chạy gì thì không tắt/ngủ ngay;
  • rảnh rồi vẫn đếm ngược SHUTDOWN_DELAY_MIN / SLEEP_DELAY_MIN phút, có việc mới chen
    vào là huỷ đếm (bước này xong thường nối tiếp bước sau, hàng đợi rảnh vài giây là
    chuyện thường);
  • bộ đếm nằm TRONG server, lệnh chỉ phát ra đúng lúc hết giờ → bỏ tick trên trang
    web là huỷ, kể cả lúc đang đếm ngược, không cần `shutdown /a`.

Hết giờ: ⏻ tắt NGAY (shutdown /s /f /t 0 — mọi app bị đóng không hỏi, đúng ý khi chạy
mẻ qua đêm không ai ngồi máy); 🌙 gọi suspend_computer của GUI (SetSuspendState), hàm
này chỉ trả về khi máy đã DẬY, server chạy tiếp bình thường. Trước khi đếm còn tập
dựng xong CHƯA đăng thì ghi cảnh báo vào nhật ký đăng (chỉ báo, không tự đăng).

NHỚ LẦN TRƯỚC (08/11/2026, user yêu cầu — trước đó mặc định TẮT mỗi lần mở server): mỗi lần
người dùng tick/bỏ tick, lựa chọn ("" / "shutdown" / "sleep") ghi vào web_settings.json khoá
`power_mode` (file riêng của bản web — KHÔNG đụng khoá "shutdown"/"sleep" của GUI Tkinter
trong taogiong_pipeline.json); server mở lại thì khoi_phuc() bật y như lần trước. Hết giờ
tự bỏ tick trong RAM nhưng KHÔNG đổi lựa chọn đã nhớ — mẻ đêm sau vẫn tắt/ngủ như đã
chọn. Vẫn phải THẤY BẬN rồi mới đếm, nên mở server mà không chạy gì thì không tắt/ngủ.
Đêm 08/11/2026: mẻ 2 chạy lúc 01:21 quên tick ⏻, card chết lúc 02:17 mà máy nằm cả đêm.
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time

from . import core
from .jobs import fb_runner, log, runner, upload_runner

# Số phút chờ + lệnh ngủ lấy CHUNG với GUI (amain_taogiong_gui) — ô bên GUI và ô trên
# trang web cùng một con số / cùng một lệnh, sửa một chỗ là cả hai cùng đổi.
SHUTDOWN_DELAY_MIN = core.gui.SHUTDOWN_DELAY_MIN
SLEEP_DELAY_MIN = core.gui.SLEEP_DELAY_MIN
suspend = core.gui.suspend_computer
POLL_SEC = 5.0
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

MODES = ("shutdown", "sleep")
ICON = {"shutdown": "⏻", "sleep": "🌙", "": ""}
LABEL = {"shutdown": "tắt máy", "sleep": "cho máy ngủ", "": ""}
# Khoá nhớ lựa chọn trong web_settings.json (xem đầu file).
NHO_KHOA = "power_mode"


def delay_min(mode: str) -> int:
    return SLEEP_DELAY_MIN if mode == "sleep" else SHUTDOWN_DELAY_MIN


def _norm(mode) -> str:
    """Nhận cả kiểu cũ arm(True/False) lẫn tên chế độ; tên lạ thì coi như tắt."""
    if mode is True:
        return "shutdown"
    if not mode:
        return ""
    return mode if mode in MODES else ""


class PowerWhenDone:
    """Trạng thái hai ô tick (một chế độ duy nhất) + luồng nền canh hàng đợi."""

    def __init__(self) -> None:
        # Khởi tạo TẮT; server gọi khoi_phuc() lúc mở để lấy lại lựa chọn lần trước (xem đầu
        # file) — không đọc file ở đây để import module trong test/script lẻ không bật gì.
        self._mode = ""
        self._saw_busy = False
        self._due = 0.0            # 0 = chưa đếm ngược (mốc time.monotonic)
        self._warn_due = False     # vừa bắt đầu đếm → soát tập chưa đăng (ngoài lock)
        self._lock = threading.Lock()
        threading.Thread(target=self._watch, daemon=True).start()

    # ── API cho tầng web ────────────────────────────────────────────────────
    def arm(self, mode, nho: bool = True) -> None:
        """Đặt chế độ: "" tắt, "shutdown" ⏻, "sleep" 🌙 (True/False kiểu cũ = ⏻/tắt).
        Đổi ⏻ ↔ 🌙 giữa lúc đang đếm thì đếm lại từ đầu — phải thấy bận đã.
        nho=True (người dùng tick): ghi lựa chọn ra web_settings.json cho lần mở sau;
        khoi_phuc() gọi với nho=False vì chỉ đọc lại."""
        mode = _norm(mode)
        if nho:
            self._nho(mode)
        with self._lock:
            if mode == self._mode:
                return
            prev, self._mode = self._mode, mode
            self._saw_busy = False     # bật (lại) = đếm lại từ đầu, phải thấy bận đã
            counting, self._due = bool(self._due), 0.0
            self._warn_due = False
        if mode:
            log(f"{ICON[mode]} Bật {LABEL[mode]} khi xong: hàng đợi xong hết + rảnh "
                f"{delay_min(mode)} phút thì {LABEL[mode]}. Huỷ: bỏ tick trên trang web.")
        elif counting:
            log(f"✖ Đã huỷ đếm ngược {LABEL[prev]}.")
        else:
            log(f"{ICON[prev]} Đã tắt chế độ {LABEL[prev]} khi xong.")

    def _nho(self, mode: str) -> None:
        """Ghi lựa chọn ra web_settings.json (khoá NHO_KHOA). Hỏng thì chỉ báo — không được
        làm hỏng việc tick."""
        try:
            core.save_web_settings({NHO_KHOA: mode})
        except Exception as e:          # noqa: BLE001
            log(f"⚠️ Không ghi nhớ được lựa chọn {ICON[mode] or '⏻/🌙'} cho lần sau: {e}")

    def khoi_phuc(self) -> str:
        """Lúc mở server: bật lại chế độ đã chọn lần trước → tên chế độ ("" = lần trước để
        tắt, không bật gì). Chỉ ĐỌC web_settings.json, không ghi lại."""
        try:
            mode = _norm(core.load_web_settings().get(NHO_KHOA, ""))
        except Exception:               # noqa: BLE001 — file hỏng thì coi như tắt
            mode = ""
        if mode:
            self.arm(mode, nho=False)
        return mode

    def state(self) -> dict:
        """Dữ liệu cho khối hàng đợi (_queue.html, làm mới 2 giây/lần) và
        /api/trangthai (cửa sổ chay.py vẽ theo)."""
        with self._lock:
            mode = self._mode
            left = max(0.0, self._due - time.monotonic()) if self._due else 0.0
            return {
                "armed": bool(mode),
                "mode": mode,
                "label": LABEL[mode],
                "delay_min": delay_min(mode),
                "shutdown_delay_min": SHUTDOWN_DELAY_MIN,
                "sleep_delay_min": SLEEP_DELAY_MIN,
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
                if due == "shutdown":
                    self._shutdown_now()
                elif due == "sleep":
                    self._sleep_now()
            except Exception as e:          # luồng canh không được chết
                log(f"⚠️ Lỗi khi canh chế độ tắt máy/ngủ: {e}")

    def _warn_pending_upload(self) -> None:
        """Bắt đầu đếm ngược mà còn tập dựng xong CHƯA đăng → nói ra.

        Hàng đợi rỗng KHÔNG đồng nghĩa “đã đăng hết”: việc đăng chỉ được nối khi ô
        “⬆ tự động đăng” bật lúc bấm chạy. Im lặng tắt máy rồi sáng ra mới biết
        cả mẻ chưa lên kênh là kiểu hỏng khó chịu nhất — nên đây là chỗ hỏi lại lần
        cuối, ngay trước khi tắt/ngủ.

        Chỉ CẢNH BÁO, không tự đăng: đăng là việc hướng ra ngoài, không được tự ý
        làm thay chỉ vì máy sắp tắt.
        """
        with self._lock:
            if not self._warn_due:
                return
            self._warn_due = False
            mode = self._mode or "shutdown"
        try:
            pending = core.episodes_pending_upload()
        except Exception:
            return
        if pending:
            upload_runner.note(
                f"⚠️ Sắp {LABEL[mode]} mà còn {len(pending)} tập dựng xong CHƯA đăng: "
                f"{', '.join(pending)}. Muốn đăng thì bỏ tick {ICON[mode]} rồi bấm "
                f"“⬆ Đăng ngay các tập chưa đăng” — máy vẫn {LABEL[mode]} đúng lịch "
                "nếu để yên.")

    def _tick(self) -> str:
        """Một lượt kiểm tra → tên chế độ nghĩa là ĐẾN GIỜ (tắt máy / ngủ), "" = chưa."""
        with self._lock:
            mode = self._mode
            if not mode:
                return ""
            # heavy_busy: việc "light" (xem kế hoạch Facebook…) không được tính —
            # bấm nút xem trước xong mà máy đếm ngược tắt/ngủ thì vô lý. Hàng đợi
            # Facebook phải có mặt: đang tải video lên Page mà tắt máy là hỏng.
            if (runner.heavy_busy() or upload_runner.heavy_busy()
                    or fb_runner.heavy_busy()):
                self._saw_busy = True
                if self._due:               # việc mới chen vào giữa lúc đếm ngược
                    self._due = 0.0
                    self._warn_due = False
                    log(f"{ICON[mode]} Có việc mới → huỷ đếm ngược, chờ xong hết đã.")
                return ""
            if not self._saw_busy:          # tick lúc đang rảnh: chờ mẻ tới
                return ""
            if not self._due:
                self._due = time.monotonic() + delay_min(mode) * 60
                self._warn_due = True       # _warn_pending_upload lo phần soát
                log(f"{ICON[mode]} Hàng đợi đã xong — máy sẽ {LABEL[mode].upper()} sau "
                        f"{delay_min(mode)} phút. Huỷ: bỏ tick trên trang web.")
                return ""
            if time.monotonic() < self._due:
                return ""
            # Một lần duy nhất: hạ cờ TRƯỚC khi gọi lệnh — lệnh hỏng thì không gọi
            # lại mỗi 5 giây, mà cũng không còn tick treo cho mẻ sau (ngủ dậy không
            # bị ngủ lại ngay).
            self._mode = ""
            self._saw_busy = False
            self._due = 0.0
            return mode

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

    def _sleep_now(self) -> None:
        log("🌙 Hết giờ — cho máy ngủ… (chạm chuột/bàn phím là dậy, server vẫn còn nguyên)")
        try:
            err = suspend()                 # chỉ trả về khi máy đã DẬY
        except Exception as e:
            err = str(e)
        if err:
            log(f"❌ Không cho máy ngủ được: {err}")
            return
        log("☀️ Máy đã dậy — bảng điều khiển chạy tiếp bình thường.")


ShutdownWhenDone = PowerWhenDone      # tên cũ (26–31/10/2026), phòng chỗ nào còn gọi
watcher = PowerWhenDone()
