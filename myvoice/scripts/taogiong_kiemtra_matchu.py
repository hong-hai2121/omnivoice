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

CÁCH HOẠT ĐỘNG (2 tầng để vừa nhanh vừa ít báo oan):
  1. Quét TẤT CẢ đoạn bằng model `small` (CPU int8, beam 1) — nhanh.
  2. Đoạn bị nghi → xác minh lại bằng `medium` (beam 5) — chỉ vài đoạn nên
     không tốn bao nhiêu. small nghe sót câu ngắn khá thường; medium chốt
     thì mới tin (đo thực tế: small gắn cờ 25, medium xác nhận 24).
Chạy hoàn toàn trên CPU — KHÔNG đụng vào VRAM đang chứa OmniVoice.

DÙNG TRONG run_tts (amain_taogiong_gui.py):
    bad = quet_va_xac_minh(chunks, tmp_dir, on_log=logging.info)
    # bad = {idx: ["cụm chữ bị mất", ...]} → render lại các idx đó rồi gọi
    # lại quet_va_xac_minh(..., chi_cac_doan=set(bad)) để kiểm lần nữa.
    giai_phong()   # xong cả bài thì trả RAM (~2 GB cho small+medium)
"""

import re
import unicodedata
import difflib
from pathlib import Path

# Cùng cache offline với nhandien_giongnoi (models--Systran--faster-whisper-*).
WHISPER_CACHE = Path(__file__).resolve().parent / "whisper_cache"

# Ngưỡng coi là MẤT CHỮ THẬT: mất >= 2 từ liền nhau. 1 từ lẻ thì ASR nghe
# nhầm nhiều hơn là model nuốt (và mất 1 từ cũng khó nhận ra khi nghe).
MAT_TOI_THIEU = 2

_MODELS = {}          # "small"/"medium" → WhisperModel (nạp 1 lần, dùng cả bài)

_W = re.compile(r"[0-9a-zà-ỹ]+")
_DIGIT_CHU = re.compile(r"(?<=\d)(?=[a-zà-ỹ])|(?<=[a-zà-ỹ])(?=\d)")


def _norm_words(s):
    """Chuỗi → list từ đã chuẩn hóa để so khớp: thường, NFC, tách chữ–số dính
    nhau ("9h42" → "9 h 42" để không báo oan khi văn bản viết "9 giờ 42")."""
    s = unicodedata.normalize("NFC", (s or "").lower())
    s = _DIGIT_CHU.sub(" ", s)
    return _W.findall(s)


def _get_model(name):
    """Nạp faster-whisper `name` trên CPU int8 từ cache offline (nạp 1 lần).
    Trả None nếu thiếu thư viện/model — bên gọi tự bỏ qua bước kiểm tra."""
    if name in _MODELS:
        return _MODELS[name]
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel(name, device="cpu", compute_type="int8",
                             download_root=str(WHISPER_CACHE),
                             local_files_only=True)
    except Exception as e:
        _MODELS[name] = None
        raise RuntimeError(f"không nạp được faster-whisper '{name}': {e}")
    _MODELS[name] = model
    return model


def giai_phong():
    """Trả RAM của các model đã nạp (gọi khi xong cả bài)."""
    import gc
    _MODELS.clear()
    gc.collect()


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
            cum_mat.append(" ".join(ref_w[i1:i2]) + " → " + " ".join(hyp_w[j1:j2]))
    return cum_mat


def quet_va_xac_minh(chunks, tmp_dir, on_log=None, chi_cac_doan=None,
                     status=None):
    """Quét mất chữ cho các đoạn đã sinh trong `tmp_dir` (file NNNN.wav).

    chunks       : list văn bản từng đoạn (đúng thứ tự file).
    chi_cac_doan : set index — chỉ kiểm các đoạn này (dùng khi kiểm lại sau
                   render lại). None = kiểm tất cả.
    status       : callable(str) cập nhật dòng trạng thái GUI (tùy chọn).

    Trả {idx: [cụm chữ bị mất]} — CHỈ gồm đoạn medium đã xác nhận.
    Thiếu thư viện/model thì cảnh báo rồi trả {} (không chặn pipeline).
    """
    log = on_log or (lambda *_: None)
    tmp_dir = Path(tmp_dir)
    try:
        small = _get_model("small")
    except RuntimeError as e:
        log(f"⚠️ Bỏ qua kiểm tra mất chữ: {e}")
        return {}

    ds = sorted(chi_cac_doan) if chi_cac_doan else range(len(chunks))
    ds = [i for i in ds if (tmp_dir / f"{i:04d}.wav").exists()]

    # Tầng 1: quét nhanh bằng small. Lỗi lẻ ở 1 file (wav hỏng…) chỉ cảnh báo
    # rồi bỏ qua đoạn đó — không được làm sập cả worker tạo giọng.
    nghi = {}
    for n, i in enumerate(ds):
        if status and (n % 10 == 0 or len(ds) < 20):
            status(f"Kiểm tra mất chữ {n + 1}/{len(ds)}...")
        try:
            cum = _tim_cum_mat(chunks[i], tmp_dir / f"{i:04d}.wav", small, beam_size=1)
        except Exception as e:
            log(f"⚠️ Không kiểm được đoạn {i:04d}: {e}")
            continue
        if cum:
            nghi[i] = cum
    if not nghi:
        return {}

    # Tầng 2: chốt lại bằng medium (chỉ các đoạn bị nghi)
    try:
        medium = _get_model("medium")
    except RuntimeError as e:
        log(f"⚠️ Không nạp được medium để xác minh ({e}) — dùng kết quả small.")
        return nghi

    mat = {}
    for n, i in enumerate(sorted(nghi)):
        if status:
            status(f"Xác minh mất chữ {n + 1}/{len(nghi)}...")
        try:
            cum = _tim_cum_mat(chunks[i], tmp_dir / f"{i:04d}.wav", medium, beam_size=5)
        except Exception as e:
            log(f"⚠️ Không xác minh được đoạn {i:04d} ({e}) — giữ kết quả small.")
            cum = nghi[i]
        if cum:
            mat[i] = cum
    return mat
