"""Giữ màn hình không tắt trong lúc nhận diện / dịch / gửi SEO (03/10/2026).

Windows tắt màn hình sau 5 phút không ai đụng máy. Màn hình tắt thì Chrome coi cửa
sổ bị che, tab Gemini bị bóp hẹn giờ (1 lần/phút) → extension báo "Gemini chưa xác
nhận nhận tin nhắn" / hết giờ, đoạn dịch thành "(trống)", SEO hỏng.

Cách giữ: máy rảnh đủ NHICH_SAU giây (không ai đụng chuột/phím) thì nhích chuột 1 px
sang trái rồi trả về chỗ cũ — Windows tính là có người dùng nên màn hình không tắt,
đang tắt thì sáng lại. Người dùng đang làm việc thì không nhích. Xong việc (ra khỏi
khối with) là thôi, các bước sau (tạo giọng, dựng video) màn hình tắt bình thường.

    with giu_man_hinh():
        ...  # dịch, SEO
"""

from __future__ import annotations

import contextlib
import ctypes
import sys
import threading

NHICH_SAU = 240     # giây máy rảnh thì nhích (Windows đang đặt tắt màn hình sau 300 s)
_KIEM_MOI = 15      # giây giữa hai lần xem máy rảnh bao lâu
_MOUSEEVENTF_MOVE = 0x0001


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def ranh_giay() -> float:
    """Số giây từ lần cuối có chuột/phím (kể cả lần nhích của module này)."""
    info = _LASTINPUTINFO(ctypes.sizeof(_LASTINPUTINFO), 0)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    get_tick = ctypes.windll.kernel32.GetTickCount
    get_tick.restype = ctypes.c_uint32          # mặc định c_int → âm sau 24,8 ngày bật máy
    return ((get_tick() - info.dwTime) & 0xFFFFFFFF) / 1000.0


def nhich_chuot() -> None:
    """Chuột sang trái 1 px rồi về chỗ cũ. Đi qua hàng đợi input như chuột thật
    (SetCursorPos thì không — Windows không tính là có người dùng)."""
    user32 = ctypes.windll.user32
    user32.mouse_event(_MOUSEEVENTF_MOVE, -1, 0, 0, 0)
    user32.mouse_event(_MOUSEEVENTF_MOVE, 1, 0, 0, 0)


def _vong(dung: threading.Event) -> None:
    while True:
        try:
            if ranh_giay() >= NHICH_SAU:
                nhich_chuot()
        except Exception:       # khoá máy / không có desktop → thôi, không làm hỏng việc chính
            pass
        if dung.wait(_KIEM_MOI):
            return


@contextlib.contextmanager
def giu_man_hinh():
    """Trong khối with: máy rảnh NHICH_SAU giây là nhích chuột một lần. Xét ngay lúc
    vào khối, nên màn hình đã tắt sẵn (vd đang dựng video tập trước) cũng sáng lại."""
    if sys.platform != "win32":
        yield
        return
    dung = threading.Event()
    threading.Thread(target=_vong, args=(dung,), daemon=True,
                     name="giu_man_hinh").start()
    try:
        yield
    finally:
        dung.set()
