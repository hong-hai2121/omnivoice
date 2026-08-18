# -*- coding: utf-8 -*-
"""Kiểm tra MẤT CHỮ sau khi tạo giọng: ASR từng đoạn (faster-whisper, CPU)
rồi đối chiếu từng TỪ với văn bản của đoạn đó.

VÌ SAO CẦN: OmniVoice là masked-diffusion, căn chỉnh chữ–tiếng NGẦM nên thi
thoảng NUỐT nguyên một câu ngắn — đo trên tập 49/53 (08-2026) là 7–12% số
đoạn. Hay mất nhất là câu thuật thoại kẹp giữa hai câu thoại ("tôi hỏi",
"tôi gật đầu", "trần lệ khóc òa lên") và cụm lặp liền kề ("không chia.
không chia."). detect_spike KHÔNG thấy được lỗi này: audio vẫn sạch, chỉ
thiếu lời. Lỗi cũng không nằm ở duration — các đoạn bị ép khung ngắn nhất
lại không mất chữ (đã kiểm chứng bằng ASR).

CÁCH HOẠT ĐỘNG: một tầng duy nhất — quét TẤT CẢ đoạn bằng large-v3-turbo
(GPU float16, beam 5).

  Bản cũ là 2 tầng `small` → `medium` chạy CPU: small nghe sót câu ngắn nên hay
  báo oan, phải medium chốt lại mới tin (đo thực tế: small gắn cờ 25, medium xác
  nhận 24). turbo nghe đủ chuẩn để bỏ hẳn tầng lọc đó, và chạy trên GPU thì
  nhanh hơn cả hai tầng CPU cộng lại.

  Đánh đổi: không còn tầng xác minh nên đoạn báo oan sẽ bị render lại thừa. Mất
  thêm ~thời gian sinh 1 đoạn chứ không hỏng gì — lượt kiểm kế tiếp vẫn soi lại
  bản mới, và bản render lại của một đoạn vốn đã đủ chữ thì cũng đủ chữ.

VRAM: bên gọi phải DỠ OmniVoice khỏi VRAM TRƯỚC khi gọi, và gọi giai_phong()
để trả VRAM lại TRƯỚC khi nạp OmniVoice render lại — card 8GB không chứa nổi
cả hai. Còn dưới VRAM_TOI_THIEU_GB trống thì tự lùi về CPU int8: chậm hơn
nhiều nhưng vẫn ra kết quả, không chặn pipeline.

DÙNG TRONG run_tts (amain_taogiong_gui.py):
    bad = quet_va_xac_minh(chunks, tmp_dir, on_log=logging.info)
    # bad = {idx: ["cụm chữ bị mất", ...]} → giai_phong(), nạp lại OmniVoice,
    # render lại các idx đó, dỡ OmniVoice, rồi gọi lại quet_va_xac_minh(...,
    # chi_cac_doan=set(bad)) để kiểm lần nữa.
    giai_phong()   # xong thì trả VRAM/RAM (~1.6 GB)
"""

import re
import unicodedata
import difflib
from pathlib import Path

# Cùng cache offline với nhandien_giongnoi (models--<chủ repo>--faster-whisper-*).
WHISPER_CACHE = Path(__file__).resolve().parent / "whisper_cache"

# Ngưỡng coi là MẤT CHỮ THẬT: mất >= ngần này từ liền nhau.
# Bản cũ để 2 vì tai `small` nghe sót từ lẻ quá thường, 1 từ là báo oan liên tục.
# large-v3-turbo nghe chắc hơn nên hạ xuống 1 — bắt được cả trường hợp nuốt đúng
# một từ. Đo trên bài 59 (161 đoạn): ngưỡng 2 gắn cờ 3 đoạn, ngưỡng 1 gắn 9 đoạn,
# trong đó 2 đoạn là rác do cách viết (đã chặn bằng _khac_cach_viet bên dưới).
MAT_TOI_THIEU = 1

# Từ chỉ số bằng chữ — để nhận ra "sáu mươi" và "60" là một, không phải mất chữ.
_SO_BANG_CHU = {
    "không", "một", "mốt", "hai", "ba", "bốn", "tư", "năm", "lăm", "sáu",
    "bảy", "bẩy", "tám", "chín", "mười", "mươi", "trăm", "nghìn", "ngàn",
    "triệu", "tỷ", "tỉ", "linh", "lẻ", "rưỡi",
}

# Model DUY NHẤT dùng để nghe lại. beam 5 vì không còn tầng xác minh phía sau
# nữa — cờ gắn ở đây là quyết định render lại luôn.
MODEL_NAME = "large-v3-turbo"
BEAM_SIZE = 5

# Còn ít hơn ngần này VRAM trống thì nạp lên GPU chỉ tổ tràn sang RAM (chậm hơn
# cả CPU) — lùi về CPU cho chắc. turbo float16 chiếm ~1.6 GB, chừa dư một ít.
VRAM_TOI_THIEU_GB = 2.5

_MODELS = {}          # tên model → WhisperModel (nạp 1 lần cho mỗi lượt quét)
_THIET_BI = ""        # "cuda/float16" | "cpu/int8" — chỉ để ghi log

_W = re.compile(r"[0-9a-zà-ỹ]+")
_DIGIT_CHU = re.compile(r"(?<=\d)(?=[a-zà-ỹ])|(?<=[a-zà-ỹ])(?=\d)")


def _norm_words(s):
    """Chuỗi → list từ đã chuẩn hóa để so khớp: thường, NFC, tách chữ–số dính
    nhau ("9h42" → "9 h 42" để không báo oan khi văn bản viết "9 giờ 42")."""
    s = unicodedata.normalize("NFC", (s or "").lower())
    s = _DIGIT_CHU.sub(" ", s)
    return _W.findall(s)


def _chon_thiet_bi():
    """(device, compute_type): GPU nếu CÒN ĐỦ VRAM TRỐNG, không thì CPU.

    Đo VRAM trống ngay lúc gọi chứ không chỉ hỏi cuda.is_available(): bên gọi đã
    dỡ OmniVoice ra rồi thì trống thật, còn nếu quên dỡ (hoặc Chrome đang ăn hết)
    thì lùi về CPU vẫn hơn là nạp lên rồi tràn sang RAM.
    """
    try:
        import torch
        if torch.cuda.is_available():
            free_b, _ = torch.cuda.mem_get_info()
            if free_b / 2**30 >= VRAM_TOI_THIEU_GB:
                return "cuda", "float16"
    except Exception:
        pass
    return "cpu", "int8"


def _get_model(name=MODEL_NAME):
    """Nạp faster-whisper `name` từ cache offline (nạp 1 lần cho mỗi lượt quét).
    Ném RuntimeError nếu thiếu thư viện/model — bên gọi tự bỏ qua bước kiểm tra.

    KHÔNG nhớ lần hỏng vào _MODELS: bản cũ ghi `_MODELS[name] = None` rồi mới
    raise, nên lần gọi sau rơi vào nhánh cache và trả về None thay vì ném lỗi —
    bên gọi tưởng nạp được, tới `model.transcribe(...)` mới vỡ bằng AttributeError
    khó lần. Hỏng thì cứ để trống, lượt sau thử lại (nạp hỏng gần như tức thì).
    """
    global _THIET_BI
    if _MODELS.get(name) is not None:
        return _MODELS[name]
    device, compute = _chon_thiet_bi()
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel(name, device=device, compute_type=compute,
                             download_root=str(WHISPER_CACHE),
                             local_files_only=True)
    except Exception as e:
        raise RuntimeError(f"không nạp được faster-whisper '{name}': {e}")
    _MODELS[name] = model
    _THIET_BI = f"{device}/{compute}"
    return model


def giai_phong():
    """Trả VRAM/RAM của model đã nạp. Gọi lại nhiều lần vô hại.

    PHẢI gọi trước khi nạp lại OmniVoice để render lại: card 8GB không đủ chỗ cho
    cả OmniVoice lẫn turbo.

    Thứ tự ở đây mới đúng: bỏ tham chiếu (_MODELS.clear()) TRƯỚC, gc.collect()
    gọi hàm huỷ của model, rồi empty_cache() mới trả được khối về cho driver.
    Bỏ tham chiếu không thôi thì allocator của torch vẫn giữ khối đó, còn dọn
    trước khi bỏ tham chiếu thì chẳng trả được gì (xem _do_omnivoice bên
    amain_taogiong_gui). Riêng faster-whisper chạy trên CTranslate2 — bộ nhớ của
    nó nằm NGOÀI allocator của torch nên phần trả thật nằm ở gc.collect();
    empty_cache() chỉ để dọn nốt phần của torch, giữ cho chắc.
    """
    import gc
    _MODELS.clear()
    gc.collect()
    try:
        import torch
        torch.cuda.empty_cache()
    except Exception:
        pass


def _khac_cach_viet(ref_span, hyp_span):
    """True nếu hai bên chỉ khác CÁCH VIẾT chứ không thiếu lời.

    Ở ngưỡng 1 từ, hai kiểu này chiếm phần lớn báo oan:
      • ngắt từ khác nhau : "r d" ↔ "rd", "bâng khuâng" ↔ "bângkhuâng"
        → nối liền hai bên mà bằng nhau thì audio vẫn đủ chữ.
      • số viết chữ vs viết số : kịch bản "sáu mươi", whisper nghe ra "60".
    """
    if not hyp_span:
        return False                      # không nghe được gì → mất thật
    if "".join(ref_span) == "".join(hyp_span):
        return True
    return (all(t in _SO_BANG_CHU for t in ref_span)
            and any(c.isdigit() for t in hyp_span for c in t))


def _tim_cum_mat(ref_text, wav_path, model, beam_size):
    """ASR `wav_path` rồi so từng từ với `ref_text`.

    Trả list cụm chữ bị mất (rỗng = đủ chữ). Chỉ tính:
      • delete  >= MAT_TOI_THIEU từ liền nhau, hoặc
      • replace mà phía ASR ngắn hơn >= MAT_TOI_THIEU từ (nuốt chữ + nghe
        nhòe phần còn lại — vd "tạ lâm xuyên không nói gì hắn" → "tạng sắn").
    ASR nghe nhầm 1-đổi-1 (sai dấu, sai phụ âm) KHÔNG bị tính.
    """
    segs, _ = model.transcribe(str(wav_path), language="vi",
                               beam_size=beam_size, vad_filter=False,
                               condition_on_previous_text=False)
    hyp = " ".join(s.text for s in segs)
    ref_w, hyp_w = _norm_words(ref_text), _norm_words(hyp)
    sm = difflib.SequenceMatcher(a=ref_w, b=hyp_w, autojunk=False)
    cum_mat = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "delete" and (i2 - i1) >= MAT_TOI_THIEU:
            cum_mat.append(" ".join(ref_w[i1:i2]))
        elif tag == "replace" and (i2 - i1) - (j2 - j1) >= MAT_TOI_THIEU:
            if _khac_cach_viet(ref_w[i1:i2], hyp_w[j1:j2]):
                continue
            cum_mat.append(" ".join(ref_w[i1:i2]) + " → " + " ".join(hyp_w[j1:j2]))
    return cum_mat


def quet_va_xac_minh(chunks, tmp_dir, on_log=None, chi_cac_doan=None,
                     status=None):
    """Quét mất chữ cho các đoạn đã sinh trong `tmp_dir` (file NNNN.wav).

    chunks       : list văn bản từng đoạn (đúng thứ tự file).
    chi_cac_doan : set index — chỉ kiểm các đoạn này (dùng khi kiểm lại sau
                   render lại). None = kiểm tất cả.
    status       : callable(str) cập nhật dòng trạng thái GUI (tùy chọn).

    Trả {idx: [cụm chữ bị mất]}.
    Thiếu thư viện/model thì cảnh báo rồi trả {} (không chặn pipeline).
    """
    log = on_log or (lambda *_: None)
    tmp_dir = Path(tmp_dir)
    try:
        model = _get_model()
    except RuntimeError as e:
        log(f"⚠️ Bỏ qua kiểm tra mất chữ: {e}")
        return {}

    ds = sorted(chi_cac_doan) if chi_cac_doan else range(len(chunks))
    ds = [i for i in ds if (tmp_dir / f"{i:04d}.wav").exists()]
    log(f"🎧 Nghe lại {len(ds)} đoạn bằng {MODEL_NAME} ({_THIET_BI}, beam {BEAM_SIZE})...")

    # Lỗi lẻ ở 1 file (wav hỏng…) chỉ cảnh báo rồi bỏ qua đoạn đó — không được
    # làm sập cả worker tạo giọng.
    mat = {}
    for n, i in enumerate(ds):
        if status and (n % 10 == 0 or len(ds) < 20):
            status(f"Kiểm tra mất chữ {n + 1}/{len(ds)}...")
        try:
            cum = _tim_cum_mat(chunks[i], tmp_dir / f"{i:04d}.wav", model,
                               beam_size=BEAM_SIZE)
        except Exception as e:
            log(f"⚠️ Không kiểm được đoạn {i:04d}: {e}")
            continue
        if cum:
            mat[i] = cum
    return mat
