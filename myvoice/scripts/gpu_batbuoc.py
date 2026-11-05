# -*- coding: utf-8 -*-
"""GPU BẮT BUỘC (27/10/2026): chức năng nào dùng GPU mà GPU không có / không chạy được
thì ném GpuLoi — báo lỗi rồi DỪNG, không âm thầm rớt về CPU.

VÌ SAO: đêm 27/10/2026 (tập 152) ffmpeg NVENC chết vì hết bộ nhớ ảo (ngốn 52 GB RAM),
video_khung chỉ in "GPU lỗi, chuyển sang CPU (libx264)" rồi vứt luôn lỗi thật của
ffmpeg và dựng tiếp bằng CPU chậm gấp nhiều lần — không ai biết có chuyện gì. Whisper
kiểm tra mất chữ cũng từng lùi về CPU int8 khi thiếu VRAM, OmniVoice/nhận diện thì
tự chọn CPU khi không thấy CUDA. Chủ trương mới: GPU là bắt buộc ở các bước nặng;
lỗi GPU phải nổi lên tới hàng đợi (tập coi như CHƯA xong) để người dùng xử lý
(dọn VRAM, đóng app chiếm GPU, xem lỗi ffmpeg) rồi chạy lại.

Dùng ở: video_khung / video_doc / video_doc_khung / video_gansub (NVENC),
taogiong_kiemtra_matchu (ASR kiểm tra), nhandien_giongnoi (nhận diện),
amain_taogiong_gui.load_omnivoice (OmniVoice). Bên gọi bắt `except GpuLoi: raise`
TRƯỚC các `except Exception` vốn nuốt lỗi để đi tiếp.
"""


class GpuLoi(RuntimeError):
    """GPU (NVENC / CUDA) không dùng được — bên gọi phải DỪNG, không được chuyển sang CPU."""


class RamLoi(GpuLoi):
    """ffmpeg (NVENC) ngốn RAM bất thường, bị chốt canh RAM (scripts/ram_canhgac.py) giết
    cả hai lần thử (28/10/2026). Kế thừa GpuLoi để mọi chỗ `except GpuLoi: raise` dừng cả
    lượt y như lỗi GPU: vụ tập 152 xảy ra khi card bị tranh chấp (python TTS 6 GB + CapCut
    3,4 GB chạy nền), cách xử lý giống nhau — dọn GPU/RAM, đóng app rồi chạy lại."""


# ── LỖI GPU → DỪNG CẢ HÀNG ĐỢI WEB (05/11/2026) ──────────────────────────────
# Đêm 05/11/2026 driver NVIDIA treo lúc 02:33 (mẻ 6 tập 164–169): từ đó tới khi khởi động
# lại máy không tiến trình mới nào dùng được CUDA. Tập nào cũng dừng vì GpuLoi, nhưng
# runner trả mã lỗi THƯỜNG nên hàng đợi cứ lấy tập kế tiếp và hỏng y hệt 5 lần, rồi ô ⏻
# tắt máy. Lỗi GPU là lỗi mà việc SAU cũng sẽ dính → runner (web/runners/run_episode.py,
# run_tts.py) trả mã RIÊNG dưới đây, hàng đợi (web/jobs.py, Step.halt_codes) thấy mã này
# thì tạm dừng cả hàng đợi thay vì chạy tiếp.
MA_THOAT_GPU = 79

# run_tts nuốt mọi lỗi rồi chỉ trả True/False (GUI sống tiếp sau khi lỗi), nên loại lỗi
# không tới được runner. Nó ghi GpuLoi vừa gặp vào đây; runner đọc lại để chọn mã thoát.
_loi_cuoi = ""


def ghi_loi(e) -> None:
    """Ghi nhớ lỗi GPU vừa làm dừng lượt chạy (run_tts gọi trong khối except)."""
    global _loi_cuoi
    _loi_cuoi = str(e).strip() or type(e).__name__


def loi_cuoi() -> str:
    """Lỗi GPU đã làm dừng lượt chạy gần nhất trong tiến trình này; "" = không phải lỗi GPU."""
    return _loi_cuoi


def xoa_loi() -> None:
    """Đầu mỗi lượt run_tts: lỗi của lượt trước (GUI sống mãi) không được dính sang lượt này."""
    global _loi_cuoi
    _loi_cuoi = ""
