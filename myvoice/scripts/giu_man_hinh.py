"""Đánh thức / giữ màn hình sáng CHỈ trong lúc dùng Gemini qua Chrome Extension.

Vì sao (03/10/2026): Windows tắt màn hình sau 5 phút (cắm điện) / 3 phút (pin) không ai
đụng máy. Màn hình tắt thì Chrome coi cửa sổ bị che, tab Gemini bị bóp hẹn giờ
(1 lần/phút) → extension báo "Gemini chưa xác nhận nhận tin nhắn" / hết giờ, đoạn dịch
thành "(trống)", SEO hỏng. Firefox (Selenium), GPT CLI, nhận diện Whisper, tải, tạo
giọng, dựng video… không cần màn hình.

Cách giữ: nhích chuột 1 px sang trái rồi trả về chỗ cũ qua hàng đợi input như chuột
thật — Windows tính là có người dùng nên màn hình không tắt, đang tắt thì sáng lại.
Chỉ nhích khi máy rảnh đủ NHICH_SAU giây; người dùng đang làm việc thì không đụng.

Ai gọi (02/11/2026, theo yêu cầu "chỉ khi cần extension để dịch mới đánh thức màn
hình"): CHÍNH gemini_extension.ChromeExtensionDriver. Trước đó run_episode /
dich_lai_trong / myvideo bọc cả bước (kể cả nhận diện) trong `with giu_man_hinh()` →
màn hình sáng suốt hàng giờ dù không cần; khối with đó đã bỏ.
  • kết nối được Chrome → danh_thuc(CHO_SANG): nhích ngay; máy rảnh từ
    DANH_THUC_NEU_RANH giây trở lên (màn hình có thể đã tắt — vd vừa tải/nhận diện
    xong) thì chờ CHO_SANG giây cho sáng hẳn, Chrome thả tab, rồi mới điều khiển.
  • mỗi lần gửi / mở chat mới → giu_neu_ranh(CHO_SANG): driver nằm chờ lâu (giữa
    hai bước, GUI để mở) thì đánh thức lại y như trên; đang dùng liên tục thì không.
  • mỗi lần đọc câu trả lời (poll vài giây một lần) → giu_neu_ranh(): rảnh ≥ NHICH_SAU
    thì nhích, không chờ.
Hết lượt gửi/đợi là thôi — không có luồng nền nào, các bước sau màn hình tắt bình thường.
"""

from __future__ import annotations

import ctypes
import logging
import sys
import time

# Giây máy rảnh thì nhích. Máy này đặt tắt màn hình sau 300 s khi cắm điện nhưng chỉ
# 180 s khi chạy pin (powercfg VIDEOIDLE, 17/10/2026) — 240 s thì chạy pin là màn
# hình tắt trước khi kịp nhích; 150 s an toàn cho cả hai, nhích chỉ khi máy rảnh nên
# không phiền ai.
NHICH_SAU = 150
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
    """Nhích chuột NGAY để đánh thức màn hình (lúc extension vừa kết nối). Máy đang
    rảnh ≥ DANH_THUC_NEU_RANH giây (màn hình có thể đã tắt) và cho_sang > 0 thì chờ
    thêm cho_sang giây cho màn hình sáng hẳn, Chrome thả tab Gemini, rồi mới trả về.
    → True nếu đã chờ."""
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


def giu_neu_ranh(cho_sang: float = 0) -> bool:
    """Gọi mỗi lần extension gửi / đọc Gemini: máy rảnh ≥ NHICH_SAU giây thì nhích chuột
    một lần (→ True), chưa đủ thì không làm gì. Đang trao đổi liên tục với Gemini thì
    poll vài giây một lần nên màn hình không kịp tắt; dừng trao đổi là thôi nhích.
    cho_sang > 0: SẮP GỬI mà máy đã rảnh lâu vậy (driver nằm chờ giữa hai bước) → màn
    hình có thể đã tắt, chờ thêm cho_sang giây cho sáng hẳn. Đọc câu trả lời thì để 0."""
    if sys.platform != "win32":
        return False
    try:
        ranh = ranh_giay()
        if ranh < NHICH_SAU:
            return False
        nhich_chuot()
    except Exception:       # khoá máy / không có desktop → thôi, không làm hỏng việc chính
        return False
    if cho_sang > 0:
        logging.info(f"🖱 Máy rảnh {ranh / 60:.0f} phút, màn hình có thể đã tắt → đã nhích "
                     f"chuột, chờ {cho_sang:.0f} s cho sáng hẳn rồi mới gửi Gemini.")
        time.sleep(cho_sang)
    return True
