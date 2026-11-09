"""Giữ màn hình không tắt trong lúc nhận diện / dịch / gửi SEO (03/10/2026).

Windows tắt màn hình sau 5 phút không ai đụng máy. Màn hình tắt thì Chrome coi cửa
sổ bị che, tab Gemini bị bóp hẹn giờ (1 lần/phút) → extension báo "Gemini chưa xác
nhận nhận tin nhắn" / hết giờ, đoạn dịch thành "(trống)", SEO hỏng.

Cách giữ: máy rảnh đủ NHICH_SAU giây (không ai đụng chuột/phím) thì nhích chuột 1 px
sang trái rồi trả về chỗ cũ — Windows tính là có người dùng nên màn hình không tắt,
đang tắt thì sáng lại. Người dùng đang làm việc thì không nhích. Xong việc (ra khỏi
khối with) là thôi, các bước sau (tạo giọng, dựng video) màn hình tắt bình thường.

Đánh thức TRƯỚC khi bắt đầu (17/10/2026): vào khối with là nhích chuột ngay; máy đang
rảnh từ DANH_THUC_NEU_RANH giây trở lên (màn hình có thể đã tắt — vd vừa tải/dựng
video xong) thì CHỜ CHO_SANG giây cho màn hình sáng hẳn và Chrome thả tab Gemini rồi
mới làm việc. Trước đây chỉ nhích rồi gửi Gemini ngay, màn hình chưa kịp sáng → lượt
gửi đầu hỏng, người dùng phải tự lắc chuột.

    with giu_man_hinh():
        ...  # dịch, SEO
    with giu_man_hinh(cho_sang=0):
        ...  # nhận diện: giữ màn hình nhưng không cần chờ sáng
"""

from __future__ import annotations

import contextlib
import ctypes
import logging
import sys
import threading
import time

# Giây máy rảnh thì nhích. Máy này đặt tắt màn hình sau 300 s khi cắm điện nhưng chỉ
# 180 s khi chạy pin (powercfg VIDEOIDLE, 17/10/2026) — 240 s thì chạy pin là màn
# hình tắt trước khi kịp nhích; 150 s an toàn cho cả hai, nhích chỉ khi máy rảnh nên
# không phiền ai.
NHICH_SAU = 150
_KIEM_MOI = 15      # giây giữa hai lần xem máy rảnh bao lâu
_MOUSEEVENTF_MOVE = 0x0001
DANH_THUC_NEU_RANH = 60   # máy rảnh từ đây (giây) coi như màn hình có thể đã tắt
CHO_SANG = 10             # giây chờ sau khi nhích cho màn hình sáng + Chrome thả tab


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


def danh_thuc(cho_sang: float = CHO_SANG) -> bool:
    """Nhích chuột NGAY để đánh thức màn hình. Máy đang rảnh ≥ DANH_THUC_NEU_RANH giây
    (màn hình có thể đã tắt) và cho_sang > 0 thì chờ thêm cho_sang giây cho màn hình
    sáng hẳn, Chrome thả tab Gemini, rồi mới trả về. → True nếu đã chờ."""
    if sys.platform != "win32":
        return False
    try:
        ranh = ranh_giay()          # đo TRƯỚC khi nhích (nhích xong là về 0)
        nhich_chuot()
    except Exception:
        return False
    if cho_sang > 0 and ranh >= DANH_THUC_NEU_RANH:
        logging.info(f"🖱 Máy rảnh {ranh / 60:.0f} phút, màn hình có thể đã tắt → đã nhích "
                     f"chuột, chờ {cho_sang:.0f} s cho sáng hẳn rồi mới bắt đầu.")
        time.sleep(cho_sang)
        return True
    return False


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
def giu_man_hinh(cho_sang: float = CHO_SANG):
    """Trong khối with: máy rảnh NHICH_SAU giây là nhích chuột một lần. Vào khối là
    nhích ngay (danh_thuc): màn hình đã tắt sẵn (vd vừa tải/dựng video) thì sáng lại,
    và nếu máy đang rảnh lâu thì chờ cho_sang giây cho sáng hẳn rồi mới làm việc.
    cho_sang=0: chỉ nhích, không chờ (bước không cần màn hình như nhận diện)."""
    if sys.platform != "win32":
        yield
        return
    danh_thuc(cho_sang)
    dung = threading.Event()
    threading.Thread(target=_vong, args=(dung,), daemon=True,
                     name="giu_man_hinh").start()
    try:
        yield
    finally:
        dung.set()
