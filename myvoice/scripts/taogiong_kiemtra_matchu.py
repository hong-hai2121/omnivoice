# -*- coding: utf-8 -*-
"""Kiểm tra MẤT CHỮ + TIẾNG LẠ sau khi tạo giọng: ASR từng đoạn
(faster-whisper) rồi đối chiếu từng TỪ với văn bản của đoạn đó, đồng thời
soi tiếng rè/rít không phải giọng đọc.

VÌ SAO CẦN: OmniVoice là masked-diffusion, căn chỉnh chữ–tiếng NGẦM nên thi
thoảng NUỐT nguyên một câu ngắn — đo trên tập 49/53 (08-2026) là 7–12% số
đoạn. Hay mất nhất là câu thuật thoại kẹp giữa hai câu thoại ("tôi hỏi",
"tôi gật đầu", "trần lệ khóc òa lên") và cụm lặp liền kề ("không chia.
không chia."). detect_spike KHÔNG thấy được lỗi này: audio vẫn sạch, chỉ
thiếu lời. Lỗi cũng không nằm ở duration — các đoạn bị ép khung ngắn nhất
lại không mất chữ (đã kiểm chứng bằng ASR).

TIẾNG LẠ (thêm 08-2026): thi thoảng OmniVoice còn sinh tiếng rè/rít/ù to nhỏ
thất thường KHÔNG phải giọng đọc. detect_spike bó tay khi tiếng lạ nằm ở mức
âm lượng ngang lời nói (nó chỉ bắt vọt gấp 5 lần nền), còn phép so từ ở đây
bó tay khi chữ vẫn đủ. Tận dụng luôn lượt ASR sẵn có, bắt theo 3 tín hiệu:
  • whisper nghe THỪA chữ không có trong kịch bản — tiếng lạ bị "nghe nhầm"
    ra chữ (opcode insert/replace phía hyp dài hơn, trước đây bị bỏ qua);
  • chỉ số tin cậy tụt: avg_logprob thấp / no_speech_prob cao /
    compression_ratio cao — whisper bảo "đoạn này có âm mà không phải lời";
  • bật word_timestamps để biết khoảng nào LÀ lời nói; khoảng NGOÀI lời mà
    RMS vẫn cao kéo dài = tiếng lạ — bắt được cả khi chữ vẫn nhận đủ
    (trường hợp hai lớp kiểm cũ đều lọt).
Đoạn dính cờ nào cũng gộp chung vào dict trả về của quet_va_xac_minh → bên
gọi render lại y hệt đoạn mất chữ, không phải sửa gì.

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
    # bad = {idx: ["cụm chữ bị mất" | "tiếng lạ ...", ...]} → giai_phong(),
    # nạp lại OmniVoice,
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

# ── Ngưỡng TIẾNG LẠ (rè/rít/ù không phải giọng đọc) ─────────────────────────
# Chưa có bộ file lỗi mẫu để đo nên đây là ngưỡng khởi điểm THIÊN VỀ BẮT NHẦM
# hơn bỏ sót: đoạn bị bắt nhầm chỉ tốn thời gian render lại 1 lượt chứ không
# hỏng gì (lượt kiểm kế tiếp vẫn soi lại bản mới). Mọi cờ đều ghi kèm chỉ số
# đo được vào log — báo nhầm/sót nhiều thì nhìn log mà chỉnh các số này.
ON_LOGPROB = -1.0    # avg_logprob dưới ngưỡng = whisper nghe không ra lời
                     # (lời TTS sạch thường ở khoảng −0.1…−0.4; −1.0 là mốc
                     #  chính faster-whisper dùng làm log_prob_threshold)
ON_NO_SPEECH = 0.6   # no_speech_prob trên ngưỡng = "không phải lời nói"
                     # (trùng no_speech_threshold mặc định của whisper)
ON_NEN = 2.4         # compression_ratio trên ngưỡng = chữ lặp vô nghĩa, dấu
                     # hiệu whisper ảo giác trên nền tiếng lạ (mốc chuẩn 2.4)
CHEN_TOI_THIEU = 2   # nghe THỪA >= ngần này từ liền nhau không có trong kịch
                     # bản mới tính — 1 từ lẻ dễ là nghe nhầm thường
ON_DEM_LOI = 0.15    # giây — nới mỗi từ thêm hai đầu chừng này trước khi coi
                     # phần còn lại là "ngoài lời nói" (mốc thời gian từng từ
                     # của whisper lệch ±0.1–0.2s, cộng hơi thở dính đuôi từ)
ON_VUNG_GIAY = 0.35  # vùng ngoài lời ồn LIÊN TỤC >= ngần này giây mới tính —
                     # ngắn hơn thường là hơi thở/vang đuôi câu bình thường
ON_TY_LE_RMS = 0.25  # khung ngoài lời coi là ồn khi RMS >= 25% mức lời nói
                     # (hơi thở ~10–20%, tiếng rè "rít lên to" ngang lời nói)
ON_RMS_SAN = 0.006   # ... và không dưới sàn tuyệt đối này — đoạn lời nói nhỏ
                     # bất thường sẽ kéo ngưỡng tỷ lệ xuống sát 0, sàn này
                     # chặn việc nhạy quá với nền gần im
ON_KHUNG_MS = 50     # cỡ khung đo RMS (ms) — trùng _FRAME_MS của detect_spike

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
      • số viết chữ vs viết số : xét CẢ HAI CHIỀU — kịch bản "sáu mươi" mà
        whisper nghe ra "60" (chiều mất chữ), và kịch bản "1975" mà whisper
        nghe ra "một chín bảy lăm" (chiều nghe thừa — hyp dài hơn ref 3 từ,
        không chặn thì dính oan cờ tiếng lạ).
    """
    if not hyp_span or not ref_span:
        return False                      # một bên trống → lệch thật
    if "".join(ref_span) == "".join(hyp_span):
        return True
    if (all(t in _SO_BANG_CHU for t in ref_span)
            and any(c.isdigit() for t in hyp_span for c in t)):
        return True
    return (all(t in _SO_BANG_CHU for t in hyp_span)
            and any(c.isdigit() for t in ref_span for c in t))


def _kiem_tra_doan(ref_text, wav_path, model, beam_size):
    """ASR `wav_path` MỘT lần rồi chạy cả hai phép kiểm trên kết quả đó:
    so từng từ với `ref_text` (mất chữ / nghe thừa) + soi tiếng lạ.

    word_timestamps=True để _tim_tieng_la biết khoảng nào là lời nói — chậm
    hơn chút (~10–20%) nhưng vẫn chỉ MỘT lượt ASR, không tốn thêm VRAM.
    Trả list mô tả lỗi (rỗng = đoạn đạt).
    """
    segs, _ = model.transcribe(str(wav_path), language="vi",
                               beam_size=beam_size, vad_filter=False,
                               condition_on_previous_text=False,
                               word_timestamps=True)
    segs = list(segs)      # generator — ASR chạy thật ở đây, chạy đúng 1 lần
    return _tim_cum_mat(ref_text, segs) + _tim_tieng_la(wav_path, segs)


def _tim_cum_mat(ref_text, segs):
    """So từng từ giữa `ref_text` và bản ASR `segs`.

    Trả list cụm chữ lệch (rỗng = đủ chữ). Chỉ tính:
      • delete  >= MAT_TOI_THIEU từ liền nhau (mất chữ), hoặc
      • replace mà phía ASR ngắn hơn >= MAT_TOI_THIEU từ (nuốt chữ + nghe
        nhòe phần còn lại — vd "tạ lâm xuyên không nói gì hắn" → "tạng sắn"),
      • insert/replace mà phía ASR DÀI hơn >= CHEN_TOI_THIEU từ — whisper
        nghe ra chữ KHÔNG có trong kịch bản, dấu hiệu tiếng lạ bị "nghe
        nhầm" thành lời (trước đây insert bị bỏ qua hẳn).
    ASR nghe nhầm 1-đổi-1 (sai dấu, sai phụ âm) KHÔNG bị tính.
    """
    hyp = " ".join(s.text for s in segs)
    ref_w, hyp_w = _norm_words(ref_text), _norm_words(hyp)
    sm = difflib.SequenceMatcher(a=ref_w, b=hyp_w, autojunk=False)
    cum_mat = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "delete" and (i2 - i1) >= MAT_TOI_THIEU:
            cum_mat.append(" ".join(ref_w[i1:i2]))
        elif tag == "insert" and (j2 - j1) >= CHEN_TOI_THIEU:
            cum_mat.append("tiếng lạ (nghe thừa): " + " ".join(hyp_w[j1:j2]))
        elif tag == "replace":
            if _khac_cach_viet(ref_w[i1:i2], hyp_w[j1:j2]):
                continue
            if (i2 - i1) - (j2 - j1) >= MAT_TOI_THIEU:
                cum_mat.append(" ".join(ref_w[i1:i2]) + " → "
                               + " ".join(hyp_w[j1:j2]))
            elif (j2 - j1) - (i2 - i1) >= CHEN_TOI_THIEU:
                cum_mat.append("tiếng lạ (nghe thừa): "
                               + " ".join(ref_w[i1:i2]) + " → "
                               + " ".join(hyp_w[j1:j2]))
    return cum_mat


def _tim_tieng_la(wav_path, segs):
    """Soi TIẾNG LẠ (rè/rít/ù không phải giọng đọc) trong 1 đoạn wav, dựa trên
    bản ASR `segs` đã có sẵn (word_timestamps=True) — không chạy thêm ASR.

    Hai lớp, đều ghi kèm chỉ số đo được để chỉnh ngưỡng qua log:
      1. Chỉ số tin cậy whisper từng segment (avg_logprob / no_speech_prob /
         compression_ratio) — bắt tiếng lạ ĐÈ lên lời làm whisper nghe nhòe.
      2. Năng lượng NGOÀI lời nói: khung 50ms nào nằm ngoài mốc thời gian các
         từ (đã nới ON_DEM_LOI hai đầu) mà RMS vẫn >= ngưỡng, liên tục đủ
         ON_VUNG_GIAY → tiếng lạ trước/sau/giữa câu, bắt được CẢ khi chữ vẫn
         nhận đủ và độ tin cậy vẫn cao.
    Trả list mô tả (rỗng = sạch).

    GIỚI HẠN nói thẳng: tiếng lạ đè CHỒNG đúng lúc đang nói mà chữ vẫn rõ, độ
    tin cậy vẫn cao thì cả hai lớp đều mù — trường hợp đó chỉ còn tai người.
    """
    loi = []

    # Lớp 1 — chỉ số tin cậy từng segment. getattr vì bản faster-whisper cũ /
    # chạy batched có thể thiếu thuộc tính.
    for s in segs:
        vi_tri = f"{s.start:.1f}–{s.end:.1f}s"
        alp = getattr(s, "avg_logprob", None)
        nsp = getattr(s, "no_speech_prob", None)
        cr = getattr(s, "compression_ratio", None)
        if alp is not None and alp < ON_LOGPROB:
            loi.append(f"tiếng lạ (nghe không ra lời, logprob {alp:.2f} tại {vi_tri})")
        if nsp is not None and nsp > ON_NO_SPEECH:
            loi.append(f"tiếng lạ (không phải lời nói, no_speech {nsp:.2f} tại {vi_tri})")
        if cr is not None and cr > ON_NEN:
            loi.append(f"tiếng lạ (chữ lặp vô nghĩa, nén {cr:.2f} tại {vi_tri})")

    # Lớp 2 — năng lượng ngoài lời nói. Thiếu numpy/soundfile (không thể xảy
    # ra trong pipeline thật — run_tts đã dùng cả hai) thì bỏ lớp này chứ
    # không chặn lớp 1.
    try:
        import numpy as np
        import soundfile as sf
    except Exception:
        return loi
    data, sr = sf.read(str(wav_path), dtype="float32")
    if data.ndim > 1:
        data = data.mean(axis=1)
    khung = max(1, int(sr * ON_KHUNG_MS / 1000))
    n = len(data) // khung
    if n == 0:
        return loi
    rms = np.sqrt((data[: n * khung].reshape(n, khung) ** 2).mean(axis=1))
    giay_khung = ON_KHUNG_MS / 1000.0

    words = [w for s in segs for w in (getattr(s, "words", None) or [])]
    if not words:
        # Không nghe ra từ nào mà audio vẫn có âm → tiếng lạ toàn đoạn (phần
        # mất chữ cũng sẽ gắn cờ delete cả câu — hai lý do cùng về một dict).
        if float(np.median(rms)) >= ON_RMS_SAN:
            loi.append("tiếng lạ (có âm thanh nhưng không nghe ra lời nào)")
        return loi

    la_loi_noi = np.zeros(n, dtype=bool)
    for w in words:
        a = int(max(0.0, w.start - ON_DEM_LOI) / giay_khung)
        b = int((w.end + ON_DEM_LOI) / giay_khung) + 1
        la_loi_noi[a:min(b, n)] = True

    muc_loi_noi = float(np.median(rms[la_loi_noi])) if la_loi_noi.any() else 0.0
    nguong = max(ON_RMS_SAN, ON_TY_LE_RMS * muc_loi_noi)
    on = (~la_loi_noi) & (rms >= nguong)

    # Gom khung ồn LIỀN NHAU thành vùng, vùng đủ dài mới tính.
    toi_thieu = max(1, int(round(ON_VUNG_GIAY / giay_khung)))
    i = 0
    while i < n:
        if not on[i]:
            i += 1
            continue
        j = i
        while j < n and on[j]:
            j += 1
        if j - i >= toi_thieu:
            loi.append(f"tiếng lạ {(j - i) * giay_khung:.1f}s tại "
                       f"{i * giay_khung:.1f}s (ngoài lời nói, RMS "
                       f"{float(rms[i:j].mean()):.3f} / lời {muc_loi_noi:.3f})")
        i = j
    return loi


def quet_va_xac_minh(chunks, tmp_dir, on_log=None, chi_cac_doan=None,
                     status=None):
    """Quét mất chữ + tiếng lạ cho các đoạn đã sinh trong `tmp_dir`
    (file NNNN.wav).

    chunks       : list văn bản từng đoạn (đúng thứ tự file).
    chi_cac_doan : set index — chỉ kiểm các đoạn này (dùng khi kiểm lại sau
                   render lại). None = kiểm tất cả.
    status       : callable(str) cập nhật dòng trạng thái GUI (tùy chọn).

    Trả {idx: [mô tả lỗi: cụm chữ bị mất / "tiếng lạ ..."]}.
    Thiếu thư viện/model thì cảnh báo rồi trả {} (không chặn pipeline).
    """
    log = on_log or (lambda *_: None)
    tmp_dir = Path(tmp_dir)
    try:
        model = _get_model()
    except RuntimeError as e:
        log(f"⚠️ Bỏ qua kiểm tra mất chữ + tiếng lạ: {e}")
        return {}

    ds = sorted(chi_cac_doan) if chi_cac_doan else range(len(chunks))
    ds = [i for i in ds if (tmp_dir / f"{i:04d}.wav").exists()]
    log(f"🎧 Nghe lại {len(ds)} đoạn bằng {MODEL_NAME} ({_THIET_BI}, beam {BEAM_SIZE})...")

    # Lỗi lẻ ở 1 file (wav hỏng…) chỉ cảnh báo rồi bỏ qua đoạn đó — không được
    # làm sập cả worker tạo giọng.
    mat = {}
    for n, i in enumerate(ds):
        if status and (n % 10 == 0 or len(ds) < 20):
            status(f"Kiểm tra chữ & tiếng lạ {n + 1}/{len(ds)}...")
        try:
            cum = _kiem_tra_doan(chunks[i], tmp_dir / f"{i:04d}.wav", model,
                                 beam_size=BEAM_SIZE)
        except Exception as e:
            log(f"⚠️ Không kiểm được đoạn {i:04d}: {e}")
            continue
        if cum:
            mat[i] = cum
    return mat
