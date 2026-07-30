# -*- coding: utf-8 -*-
"""
kiemtra_daura.py — Chốt kiểm ĐỘ DÀI đầu ra, bắt lỗi "ra thiếu nội dung mà không ai biết".

Bối cảnh: tập 42 (video gốc 35 phút) ra video chỉ 16 phút vì Gemini chết ở đoạn 4/7,
4 đoạn còn lại bị đệm "(chưa dịch)" rồi bị xoá âm thầm khi tạo input.txt. Không có
bước nào đo xem đầu ra có ngắn bất thường không nên lỗi lọt tới tận video.

Hai phép đo ĐỘC LẬP (số liệu đo từ các tập đã chạy đúng — xem hằng số bên dưới):

  1. check_ban_dich()  — input.txt (tiếng Việt) so với bản nhận diện tiếng Trung.
     Bắt lỗi MẤT ĐOẠN KHI DỊCH (ca tập 42). Tập lành: 4.56–4.75 ký tự Việt / 1 chữ Hán;
     tập 42 chỉ 2.17.

  2. check_audio()     — output.wav so với số ký tự input.txt.
     Bắt lỗi TTS hụt chunk / ffmpeg cắt cụt. Tập lành: 18.20–18.28 ký tự/giây
     (rất ổn định, lệch chưa tới 0.5%).

Phép 1 KHÔNG thay được phép 2 và ngược lại: tập 42 có output.wav khớp hoàn toàn với
input.txt của nó (18.28 ký tự/giây) — vì lỗi nằm ở thượng nguồn.
"""

import re
import subprocess
from pathlib import Path

# ── Số liệu đo thực tế trên các tập đã chạy đúng (tập 43–47) ─────────────────
# Ký tự tiếng Việt trong input.txt trên MỖI chữ Hán của bản nhận diện.
TY_LE_VIET_TREN_HAN = 4.6           # đo được: 4.56 · 4.59 · 4.63 · 4.64 · 4.75
# Ngưỡng CHẶN: dưới mức này coi như bản dịch bị mất đoạn. Đặt rộng tay — thấp hơn
# tập lành thấp nhất (4.56) tới 23%, mà vẫn cao hơn tập 42 hỏng (2.17) tới 61%.
NGUONG_VIET_TREN_HAN = 3.5

# Ký tự input.txt đọc được trong 1 giây audio (giọng OmniVoice, tốc độ mặc định).
KY_TU_MOI_GIAY = 18.25              # đo được: 18.20 – 18.28
# Audio ngắn hơn mức dự kiến quá tỉ lệ này → cảnh báo (0.15 = hụt trên 15%).
SAI_SO_AUDIO = 0.15

_CJK_RE = re.compile(r"[㐀-䶿一-鿿]")


def _dem_han_trong_docx(path) -> int:
    """Số chữ Hán trong file .docx bản nhận diện tiếng Trung (0 nếu đọc không được)."""
    try:
        from docx import Document
        txt = "\n".join(p.text for p in Document(str(path)).paragraphs)
    except Exception:
        return 0
    return len(_CJK_RE.findall(txt))


def tim_docx_tieng_trung(folder):
    """Tìm bản nhận diện tiếng Trung trong thư mục tập (*_zh.docx hoặc tiengTrung.docx)."""
    folder = Path(folder)
    for pat in ("*_zh.docx", "tiengTrung.docx"):
        hits = sorted(folder.glob(pat))
        if hits:
            return hits[0]
    return None


def do_dai_audio(path):
    """Thời lượng (giây) của file audio/video qua ffprobe. None nếu không đọc được."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=60)
        return float(r.stdout.strip())
    except Exception:
        return None


def check_ban_dich(noi_dung_viet, folder):
    """So input.txt (tiếng Việt) với bản nhận diện tiếng Trung của CÙNG tập.

    Trả về (ok, thong_diep). ok=False nghĩa là bản dịch NGẮN BẤT THƯỜNG → nhiều khả
    năng mất đoạn. Không tìm thấy bản tiếng Trung → (True, None): không đủ dữ kiện
    để kết luận thì cho qua, KHÔNG chặn oan.
    """
    zh = tim_docx_tieng_trung(folder)
    if not zh:
        return True, None
    n_han = _dem_han_trong_docx(zh)
    if n_han < 500:                      # bản nhận diện quá ngắn → không đủ cơ sở
        return True, None
    n_viet = len(noi_dung_viet or "")
    ty_le = n_viet / n_han
    if ty_le >= NGUONG_VIET_TREN_HAN:
        return True, None
    thieu = 1 - ty_le / TY_LE_VIET_TREN_HAN
    return False, (
        f"bản dịch NGẮN BẤT THƯỜNG: {n_viet:,} ký tự Việt / {n_han:,} chữ Hán "
        f"= {ty_le:.2f} (tập bình thường ~{TY_LE_VIET_TREN_HAN}, ngưỡng "
        f"{NGUONG_VIET_TREN_HAN}) → ước tính THIẾU khoảng {thieu:.0%} nội dung. "
        f"Kiểm tra {zh.name} và gemini_result.docx xem có đoạn nào chưa dịch."
    )


def check_audio(audio_path, input_txt):
    """So thời lượng output.wav với số ký tự input.txt.

    Trả về (ok, thong_diep). ok=False nghĩa là audio ngắn hơn dự kiến quá SAI_SO_AUDIO
    → TTS hụt chunk hoặc file bị cắt cụt. Thiếu dữ kiện → (True, None).
    """
    try:
        n = len(Path(input_txt).read_text(encoding="utf-8"))
    except Exception:
        return True, None
    if n < 1000:
        return True, None
    that = do_dai_audio(audio_path)
    if not that:
        return True, None
    du_kien = n / KY_TU_MOI_GIAY
    if that >= du_kien * (1 - SAI_SO_AUDIO):
        return True, None
    return False, (
        f"audio NGẮN HƠN DỰ KIẾN: {that / 60:.1f} phút, đáng lẽ ~{du_kien / 60:.1f} "
        f"phút cho {n:,} ký tự (hụt {1 - that / du_kien:.0%}) → nhiều khả năng thiếu "
        f"chunk hoặc file bị cắt cụt. Kiểm tra thư mục output_chunks."
    )
