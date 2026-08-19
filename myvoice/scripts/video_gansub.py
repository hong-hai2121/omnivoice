# -*- coding: utf-8 -*-
"""
Gắn phụ đề (sub) vào video — dùng ĐÚNG chữ từ file kịch bản gốc, căn thời gian theo audio.

Ý tưởng:
  1. Đọc văn bản gốc (vd kịch_bản/input.txt) → cắt thành các "cue" phụ đề ngắn.
  2. Dùng faster-whisper nghe audio (tiếng Việt, word-level timestamps) để biết mỗi
     TỪ vang lên vào lúc nào.
  3. Khớp (align) chuỗi từ gốc với chuỗi từ Whisper → suy ra mốc giờ bắt đầu/kết thúc
     cho từng cue. Chữ hiển thị là chữ GỐC (không dùng chữ Whisper nhận ra), nên
     chính xác 100%; Whisper chỉ dùng để lấy mốc thời gian.
  4. Xuất file .srt rồi MUX (nhúng mềm) vào mp4 bằng ffmpeg — không render lại hình,
     player có thể bật/tắt phụ đề.

Cách dùng:
    # mặc định: audio tách từ video, kịch bản = input.txt CẠNH video (nếu có)
    python video_gansub.py "duong_dan/output_videodone.mp4"

    # chỉ xuất .srt để tải lên YouTube Studio, KHÔNG đụng tới file video
    python video_gansub.py "kịch_bản/35 - 94/YOUTUBE.mp4" --srt-only

    # chỉ rõ audio + kịch bản + nơi lưu
    python video_gansub.py "output_videodone.mp4" --audio "output3.wav" \
        --script "../kịch_bản/input.txt" --out "output_sub.mp4"

Yêu cầu:
    pip install faster-whisper
    ffmpeg + ffprobe trong PATH.
"""

import argparse
import difflib
import math
import os
import re
import subprocess
import sys
from pathlib import Path

# Console Windows in được tiếng Việt
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# Tái dùng hạ tầng Whisper sẵn có (nạp model từ cache local, không gọi mạng)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nhandien_giongnoi import (  # noqa: E402
    extract_audio,
    get_audio_duration,
    get_model,
)

SCRIPT_DIR = Path(__file__).resolve().parent
# input.txt nằm ở myvoice/kịch_bản/
DEFAULT_SCRIPT = SCRIPT_DIR.parent / "kịch_bản" / "input.txt"


def guess_script(video_path: Path) -> Path:
    """Đoán file kịch bản cho video.

    Pipeline để MỖI dự án một thư mục riêng (vd kịch_bản/35 - 94/) chứa cả video
    lẫn input.txt của chính nó, nên ưu tiên input.txt NẰM CẠNH video; chỉ khi
    không có (hoặc rỗng) mới lùi về input.txt dùng chung ở kịch_bản/.
    """
    sibling = video_path.resolve().parent / "input.txt"
    if sibling.is_file() and sibling.stat().st_size > 0:
        return sibling
    return DEFAULT_SCRIPT

AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma"}

# Tách câu: sau dấu kết câu (. ! ? …) và khoảng trắng theo sau.
_SENT_SPLIT = re.compile(r"(?<=[.!?…])\s+")
# Token để KHỚP: \w (có Unicode) bắt được chữ Việt có dấu, số, và cả chữ Hán lẫn vào.
_WORD_RE = re.compile(r"\w+", re.UNICODE)


def norm_tokens(text: str):
    """Tách văn bản thành danh sách token thường-hoá (chữ thường, bỏ dấu câu)."""
    return _WORD_RE.findall(text.lower())


# ----------------------------------------------------------------------------- #
# 1) Cắt văn bản gốc thành các cue phụ đề ngắn
# ----------------------------------------------------------------------------- #
def wrap_sentence(sentence: str, max_chars: int):
    """Cắt 1 câu dài thành nhiều mẩu ≤ max_chars, CHIA ĐỀU, cắt ở ranh giới từ.

    Cách tham lam (nhồi cho đầy max_chars rồi vứt phần thừa xuống dòng sau) đẻ ra
    rất nhiều dòng mồ côi kiểu "nay." / "xẻo." — đọc rất khó chịu. Ở đây tính
    trước số dòng cần thiết rồi nhắm độ dài trung bình, nên các dòng dài xấp xỉ
    nhau và không còn chữ rơi lại một mình.
    """
    words = sentence.split()
    if not words:
        return []
    n_lines = max(1, math.ceil(len(sentence) / max_chars))
    target = len(sentence) / n_lines

    pieces, cur = [], ""
    for w in words:
        cand = (cur + " " + w).strip()
        if not cur:
            cur = cand
            continue
        if len(cand) > max_chars:
            wrap = True
        elif len(pieces) < n_lines - 1 and len(cand) > target:
            # Đã quá mức nhắm tới: giữ w lại hay đẩy sang dòng sau, chọn bên nào
            # cho độ dài gần `target` hơn.
            wrap = (len(cand) - target) > (target - len(cur))
        else:
            wrap = False
        if wrap:
            pieces.append(cur)
            cur = w
        else:
            cur = cand
    if cur:
        pieces.append(cur)
    return pieces


def build_cues(text: str, max_chars: int, max_lines: int = 1):
    """Trả về danh sách cue (chuỗi hiển thị) từ văn bản gốc.

    Mỗi dòng không rỗng = 1 đoạn; tách đoạn thành câu; câu quá dài thì cắt theo từ.
    Giữ NGUYÊN chữ gốc (kể cả hoa/thường, dấu câu) để hiển thị.

    max_lines = số DÒNG tối đa mỗi lần hiện chữ:
      1 — mỗi cue một dòng ≤ max_chars (nếp cũ).
      2 — mỗi cue gom tới 2 dòng, đúng như ảnh mẫu của kho kiểu: cắt câu thành
          mẩu vừa MỘT lần hiện chữ (≤ max_chars × max_lines ký tự) rồi bẻ mẩu
          đó thành các dòng dài xấp xỉ nhau. Chữ ở lại trên hình lâu gấp đôi
          nên dễ đọc hơn, và không còn cảnh nửa câu trôi mất trước khi đọc kịp.
    Các dòng trong một cue nối bằng ký tự xuống dòng — write_srt ghi thẳng (SRT
    cho phép cue nhiều dòng), kieusub.write_ass_kieu tự đổi sang mã của ASS.
    """
    max_lines = max(1, int(max_lines or 1))
    cues = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        for sentence in _SENT_SPLIT.split(line):
            sentence = sentence.strip()
            if not sentence:
                continue
            if max_lines == 1:
                if len(sentence) <= max_chars:
                    cues.append(sentence)
                else:
                    cues.extend(wrap_sentence(sentence, max_chars))
                continue
            for mau in wrap_sentence(sentence, max_chars * max_lines):
                cues.append("\n".join(wrap_sentence(mau, max_chars)))
    return cues


# ----------------------------------------------------------------------------- #
# 2) Nghe audio → danh sách từ kèm mốc giờ
# ----------------------------------------------------------------------------- #
# Chống kẹt vòng lặp: temperature phải là DÃY thì Whisper mới giải mã lại được ở
# nhiệt độ cao hơn khi thấy đoạn lặp (temperature=0 là tắt hẳn cơ chế đó).
# no_repeat_ngram_size + repetition_penalty chặn ngay lúc giải mã. Ở script này
# một đoạn kẹt lặp không làm sai CHỮ (chữ lấy từ text gốc) nhưng làm cả cửa sổ 30s
# không khớp được -> mốc giờ phải nội suy -> sub lệch giờ.
_TRANSCRIBE_OPTS = dict(
    language="vi",
    word_timestamps=True,        # cần mốc giờ TỪNG TỪ để căn sub
    condition_on_previous_text=False,
    temperature=(0.0, 0.2, 0.4, 0.6, 0.8, 1.0),
    beam_size=5,
    compression_ratio_threshold=2.4,
    log_prob_threshold=-1.0,
    no_repeat_ngram_size=3,
    repetition_penalty=1.1,
    vad_filter=True,
    vad_parameters=dict(min_silence_duration_ms=400),
)


def transcribe_words(audio_path, model_name="large-v3-turbo", on_progress=None):
    """Nghe audio, trả về (words, starts, ends): 3 list song song.

    words[i] là token thường-hoá của từ thứ i; starts/ends là mốc giờ (giây).
    """
    # Dùng model thường (không batched) để word_timestamps ổn định.
    model, _batched, _device = get_model(model_name, use_batched=False)
    duration = get_audio_duration(audio_path) or 0
    print("📝 Đang nghe audio để lấy mốc thời gian (tiếng Việt)...")
    segments, info = model.transcribe(audio_path, **_TRANSCRIBE_OPTS)
    total = duration or float(getattr(info, "duration", 0) or 0)

    words, starts, ends = [], [], []
    for seg in segments:
        for w in (seg.words or []):
            tok = norm_tokens(w.word)
            if not tok:
                continue
            # Một "từ" Whisper hiếm khi gồm nhiều token; nếu có, chia đều mốc giờ.
            n = len(tok)
            span = (w.end - w.start) / n if n else 0
            for k, t in enumerate(tok):
                words.append(t)
                starts.append(w.start + k * span)
                ends.append(w.start + (k + 1) * span)
        if on_progress and total:
            on_progress(min(seg.end / total, 1.0))
    return words, starts, ends


# ----------------------------------------------------------------------------- #
# 3) Khớp từ gốc ↔ từ Whisper → mốc giờ cho từng cue
# ----------------------------------------------------------------------------- #
def align_cues(cues, w_words, w_starts, w_ends, audio_dur):
    """Gán (start, end) cho từng cue dựa trên khớp chuỗi từ.

    - Xây chuỗi token gốc (nối tất cả cue) + nhớ token nào thuộc cue nào.
    - SequenceMatcher khớp token gốc với token Whisper.
    - Token gốc khớp được → lấy mốc giờ Whisper; token không khớp → nội suy.
    - Cue lấy start = mốc đầu của token sớm nhất, end = mốc cuối token muộn nhất.
    """
    # Chuỗi token gốc + bản đồ token → cue
    o_words, o_cue = [], []
    for ci, cue in enumerate(cues):
        for t in norm_tokens(cue):
            o_words.append(t)
            o_cue.append(ci)

    n = len(o_words)
    o_start = [None] * n
    o_end = [None] * n

    if w_words and n:
        sm = difflib.SequenceMatcher(a=o_words, b=w_words, autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                for k in range(i2 - i1):
                    o_start[i1 + k] = w_starts[j1 + k]
                    o_end[i1 + k] = w_ends[j1 + k]

    # Nội suy mốc giờ cho token chưa khớp (kẹp giữa 2 token đã biết)
    _interpolate(o_start, o_end, audio_dur)

    # Gom theo cue
    cue_times = []
    for ci in range(len(cues)):
        idxs = [i for i in range(n) if o_cue[i] == ci]
        if not idxs:
            cue_times.append(None)
            continue
        st = min(o_start[i] for i in idxs if o_start[i] is not None)
        en = max(o_end[i] for i in idxs if o_end[i] is not None)
        cue_times.append((st, en))

    _fill_empty_cues(cue_times, audio_dur)
    _sanitize(cue_times, audio_dur)
    return cue_times


def _interpolate(o_start, o_end, audio_dur):
    """Điền mốc giờ còn thiếu bằng nội suy tuyến tính theo chỉ số token."""
    n = len(o_start)
    if n == 0:
        return
    # Mỏ neo đầu/cuối nếu thiếu
    if o_start[0] is None:
        o_start[0] = 0.0
    if o_end[n - 1] is None:
        o_end[n - 1] = audio_dur or (o_start[0] + n * 0.3)

    # Lấp start
    i = 0
    while i < n:
        if o_start[i] is None:
            j = i
            while j < n and o_start[j] is None:
                j += 1
            left = o_end[i - 1] if i > 0 and o_end[i - 1] is not None else o_start[i - 1]
            right = o_start[j] if j < n else (audio_dur or left)
            left = left if left is not None else 0.0
            right = right if right is not None else left
            step = (right - left) / (j - i + 1)
            for k in range(i, j):
                o_start[k] = left + step * (k - i + 1)
            i = j
        else:
            i += 1
    # End suy ra từ start kế tiếp nếu thiếu
    for i in range(n):
        if o_end[i] is None:
            o_end[i] = o_start[i + 1] if i + 1 < n else (audio_dur or o_start[i] + 0.3)


def _fill_empty_cues(cue_times, audio_dur):
    """Cue không có token nào khớp (vd toàn chữ Hán) → nội suy từ cue lân cận."""
    n = len(cue_times)
    for i in range(n):
        if cue_times[i] is not None:
            continue
        prev_end = next((cue_times[k][1] for k in range(i - 1, -1, -1)
                         if cue_times[k]), 0.0)
        nxt_start = next((cue_times[k][0] for k in range(i + 1, n)
                          if cue_times[k]), audio_dur or prev_end + 1.0)
        if nxt_start <= prev_end:
            nxt_start = prev_end + 1.0
        cue_times[i] = (prev_end, nxt_start)


def _sanitize(cue_times, audio_dur, min_dur=0.6, gap=0.04):
    """Bảo đảm thời gian tăng dần, không chồng lấn, mỗi cue đủ dài để đọc."""
    prev_end = 0.0
    for i, t in enumerate(cue_times):
        st, en = t
        st = max(st, prev_end)
        if en < st + min_dur:
            en = st + min_dur
        if audio_dur:
            en = min(en, audio_dur)
            st = min(st, max(0.0, audio_dur - 0.1))
        cue_times[i] = (st, en)
        prev_end = en + gap


# ----------------------------------------------------------------------------- #
# 4) Xuất SRT + mux vào video
# ----------------------------------------------------------------------------- #
def _fmt_ts(sec: float) -> str:
    if sec < 0:
        sec = 0
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(cues, cue_times, srt_path: Path):
    lines = []
    for i, (cue, (st, en)) in enumerate(zip(cues, cue_times), 1):
        lines.append(str(i))
        lines.append(f"{_fmt_ts(st)} --> {_fmt_ts(en)}")
        lines.append(cue)
        lines.append("")
    srt_path.write_text("\n".join(lines), encoding="utf-8")
    return srt_path


# Kiểu chữ phụ đề khi burn-in (cú pháp force_style của ASS).
# Chữ trắng đậm trên KHUNG NỀN đen mờ, canh giữa dưới — đọc được trên mọi nền,
# kể cả khung hình sáng trắng hay nền trang trí nhiều hoạ tiết.
# FontSize tính theo độ cao 1080; ffmpeg tự co theo độ phân giải thật.
#
# Hai điểm dễ sai của ASS, nhớ kỹ khi chỉnh:
#   • BorderStyle=3 (khung nền đặc) tô hộp bằng OutlineColour, KHÔNG phải
#     BackColour — BackColour lúc này chỉ còn dùng cho bóng đổ.
#   • Màu ghi dạng &HAABBGGRR, trong đó AA là ĐỘ TRONG SUỐT ngược đời:
#     00 = đen đặc hoàn toàn, FF = trong suốt hoàn toàn. Muốn nền ĐẬM hơn thì
#     GIẢM số (&H60 → &H30), muốn nhạt hơn thì tăng.
#   • Outline = độ dày đệm quanh chữ (khung nền to/nhỏ theo số này).
#
# FontSize=18 (không phải 22) để khung nền của dòng dài nhất — 50 ký tự theo
# --max-chars mặc định — vẫn nằm gọn trong khung video, không tràn ra viền
# trang trí hai bên. Muốn chữ to hơn thì tăng FontSize VÀ giảm --max-chars
# tương ứng, nếu không khung nền sẽ thò ra ngoài.
BURN_STYLE = (
    "FontName=Arial,FontSize=18,Bold=1,"
    "PrimaryColour=&H00FFFFFF,OutlineColour=&H60000000,BackColour=&H00000000,"
    "BorderStyle=3,Outline=5,Shadow=0,Alignment=2,MarginV=45"
)


# ── KHUNG NỀN BO TRÒN ────────────────────────────────────────────────────────
# ASS KHÔNG có sẵn khung nền bo góc: BorderStyle=3 luôn vẽ hộp VUÔNG và không có
# tham số bán kính. Nên muốn bo tròn thì phải tự sinh file .ass, mỗi dòng phụ đề
# thành 2 event: lớp 0 vẽ hình chữ nhật bo góc bằng lệnh vẽ vector \p1, lớp 1 là
# chữ đè lên. Muốn đo được bề rộng hộp thì phải đo bề rộng chữ trước → dùng Pillow
# đọc đúng file font mà libass sẽ dùng.
#
# Toạ độ tính trong khung 1920x1080; ffmpeg tự co theo độ phân giải thật.
ASS_PLAY_W, ASS_PLAY_H = 1920, 1080

# ── Khung DỌC 1080x1920 (facebook.mp4 / tiktok.mp4) ──────────────────────────
# Video dọc hẹp hơn nhiều (1080 thay vì 1920) nên PHẢI có bộ số riêng, không dùng
# chung với khung ngang được:
#   • Giữ nguyên SUB_FONT_SIZE=67 → chữ chiếm 6.2% BỀ RỘNG khung, đúng bằng tỉ lệ
#     của khung ngang, nên nhìn to bằng nhau.
#   • max_chars phải giảm 50 → 23. Con số này đo bằng Pillow trên DÒNG RỘNG NHẤT của
#     cả 6 kịch bản thật, không phải ước lượng trung bình — chữ hoa và ký tự rộng làm
#     dòng xấu nhất phình hơn hẳn mức trung bình:
#         23 ký tự →  935px = 87% của 1080   ← chọn (khung ngang đang ở 91%)
#         24 ký tự →  999px = 92%
#         27 ký tự → 1084px = 100%  ← chạm sát mép, tràn
#     Để nguyên 50 thì khung nền tràn ra ngoài mép video.
#   • MarginV 380px (≈20% chiều cao) thay vì 173: đáy video dọc bị thanh công cụ
#     của TikTok/Reels/Facebook che, để thấp quá là chữ bị khuất.
ASS_PLAY_W_DOC, ASS_PLAY_H_DOC = 1080, 1920
SUB_MARGIN_V_DOC = 380
SUB_MAX_CHARS_DOC = 23

SUB_FONT       = "Arial"
SUB_FONT_FILE  = r"C:\Windows\Fonts\arialbd.ttf"   # Arial Bold — chỉ dùng để ĐO chữ
SUB_FONT_SIZE  = 67       # px (bằng FontSize=18 của khung 384x288 mà ffmpeg dùng)
SUB_MARGIN_V   = 173      # đáy dòng chữ cách đáy khung hình bao nhiêu px
BOX_PAD_X      = 24       # đệm trái/phải giữa chữ và mép hộp
BOX_PAD_Y      = 10       # đệm trên/dưới
BOX_RADIUS     = 26       # bán kính bo góc
BOX_ALPHA      = "60"     # độ TRONG SUỐT: 00 = đen đặc, FF = trong suốt hẳn


def _text_width(text: str) -> float:
    """Bề rộng chữ (px) ở SUB_FONT_SIZE. Thiếu font → ước lượng thô theo số ký tự."""
    try:
        from PIL import ImageFont
        return ImageFont.truetype(SUB_FONT_FILE, SUB_FONT_SIZE).getlength(text)
    except Exception:
        return len(text) * SUB_FONT_SIZE * 0.52


def _line_metrics():
    """(ascent, descent) của font ở SUB_FONT_SIZE — để biết dòng chữ cao bao nhiêu."""
    try:
        from PIL import ImageFont
        return ImageFont.truetype(SUB_FONT_FILE, SUB_FONT_SIZE).getmetrics()
    except Exception:
        return int(SUB_FONT_SIZE * 0.9), int(SUB_FONT_SIZE * 0.25)


def _rounded_rect_path(x0, y0, x1, y1, r) -> str:
    """Lệnh vẽ ASS (\\p1) cho hình chữ nhật bo 4 góc.

    Mỗi góc là một đường bezier bậc 3 với CẢ HAI điểm điều khiển đặt ngay tại đỉnh
    góc vuông — kéo đường cong sát vào góc, cho ra cung tròn đều mắt.
    """
    x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
    r = int(max(0, min(r, (x1 - x0) // 2, (y1 - y0) // 2)))
    return (f"m {x0 + r} {y0} "
            f"l {x1 - r} {y0} b {x1} {y0} {x1} {y0} {x1} {y0 + r} "
            f"l {x1} {y1 - r} b {x1} {y1} {x1} {y1} {x1 - r} {y1} "
            f"l {x0 + r} {y1} b {x0} {y1} {x0} {y1} {x0} {y1 - r} "
            f"l {x0} {y0 + r} b {x0} {y0} {x0} {y0} {x0 + r} {y0}")


def _ass_ts(sec: float) -> str:
    """Mốc giờ kiểu ASS: H:MM:SS.cc (phần trăm giây)."""
    if sec < 0:
        sec = 0
    cs = int(round(sec * 100))
    h, cs = divmod(cs, 360_000)
    m, cs = divmod(cs, 6_000)
    s, cs = divmod(cs, 100)
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


def _ass_header(play_w=ASS_PLAY_W, play_h=ASS_PLAY_H, margin_v=SUB_MARGIN_V) -> str:
    """Phần đầu file .ass cho MỘT khung hình cụ thể (ngang hay dọc).

    Trước đây đây là hằng số dựng sẵn ở mức module nên chỉ ra được khung 1920x1080;
    làm phụ đề cho video dọc thì phải đổi PlayRes + MarginV nên chuyển thành hàm.
    """
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {play_w}
PlayResY: {play_h}
ScaledBorderAndShadow: yes
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, \
BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, \
BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,{SUB_FONT},{SUB_FONT_SIZE},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,\
-1,0,0,0,100,100,0,0,1,0,0,2,20,20,{margin_v},1
Style: Box,{SUB_FONT},{SUB_FONT_SIZE},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,\
0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def write_ass(cues, cue_times, ass_path: Path,
              play_w=ASS_PLAY_W, play_h=ASS_PLAY_H, margin_v=SUB_MARGIN_V):
    """Ghi .ass: mỗi dòng phụ đề = 1 hộp bo góc (lớp 0) + chữ trắng (lớp 1).

    play_w/play_h/margin_v: khung hình đích. Mặc định = khung NGANG 1920x1080.
    Video DỌC truyền ASS_PLAY_W_DOC / ASS_PLAY_H_DOC / SUB_MARGIN_V_DOC.
    """
    ascent, descent = _line_metrics()
    line_h = ascent + descent
    cx = play_w / 2
    # libass đặt ĐÁY dòng chữ cách đáy khung đúng MarginV.
    text_bottom = play_h - margin_v
    out = [_ass_header(play_w, play_h, margin_v)]
    for cue, (st, en) in zip(cues, cue_times):
        lines = cue.split("\n")
        w = max(_text_width(ln) for ln in lines)
        n = len(lines)
        x0, x1 = cx - w / 2 - BOX_PAD_X, cx + w / 2 + BOX_PAD_X
        y1 = text_bottom + BOX_PAD_Y
        y0 = text_bottom - line_h * n - BOX_PAD_Y
        path = _rounded_rect_path(x0, y0, x1, y1, BOX_RADIUS)
        a, b = _ass_ts(st), _ass_ts(en)
        out.append(
            f"Dialogue: 0,{a},{b},Box,,0,0,0,,"
            f"{{\\p1\\pos(0,0)\\c&H000000&\\alpha&H{BOX_ALPHA}&\\bord0\\shad0}}{path}{{\\p0}}\n"
        )
        body = "\\N".join(lines)
        out.append(f"Dialogue: 1,{a},{b},Sub,,0,0,0,,{body}\n")
    ass_path.write_text("".join(out), encoding="utf-8")
    return ass_path


def has_nvenc() -> bool:
    """Kiểm tra ffmpeg có encoder h264_nvenc (GPU NVIDIA) hay không."""
    try:
        r = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        return r.returncode == 0 and "h264_nvenc" in r.stdout
    except Exception:
        return False


def burn_subs(video_path: Path, sub_path: Path, out_path: Path, style=BURN_STYLE):
    """Vẽ CỨNG phụ đề thẳng vào khung hình (hardsub) — phải re-encode video.

    `sub_path` nhận .ass (đã có sẵn kiểu + khung nền bo góc, KHÔNG ép force_style)
    hoặc .srt (không có kiểu riêng → ép bằng force_style, khung nền vuông).

    Ưu tiên GPU (h264_nvenc) cho nhanh; nếu GPU lỗi tự fallback về CPU (libx264).
    Để né rắc rối escape đường dẫn Windows (dấu ':' của ổ đĩa) trong bộ lọc
    subtitles, ta chạy ffmpeg với cwd = thư mục chứa file phụ đề và chỉ truyền TÊN file.
    """
    # fontsdir: kho font rời myvoice/fonts (Anton, Bangers… của bộ kiểu phụ đề
    # kieusub) — libass tự thấy, không cần cài font vào Windows.
    import kieusub
    vf = f"subtitles={sub_path.name}{kieusub.fontsdir_arg(sub_path.parent)}"
    if sub_path.suffix.lower() != ".ass":
        vf += f":force_style='{style}'"

    def build_cmd(gpu):
        if gpu:
            codec = ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "19"]
        else:
            codec = ["-c:v", "libx264", "-preset", "medium", "-crf", "18"]
        return [
            "ffmpeg", "-y",
            "-i", str(video_path.resolve()),
            "-vf", vf,
            *codec,
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            str(out_path.resolve()),
        ]

    use_gpu = has_nvenc()
    print("   Encode: GPU (h264_nvenc)" if use_gpu else "   Encode: CPU (libx264)")
    result = subprocess.run(build_cmd(use_gpu), capture_output=True, text=True,
                            encoding="utf-8", errors="replace", cwd=str(sub_path.parent))
    # GPU lỗi (driver/độ phân giải/encoder) → thử lại bằng CPU để không hỏng cả lượt.
    if result.returncode != 0 and use_gpu:
        print("   GPU lỗi, chuyển sang CPU (libx264)...")
        result = subprocess.run(build_cmd(False), capture_output=True, text=True,
                                encoding="utf-8", errors="replace", cwd=str(sub_path.parent))
    if result.returncode != 0:
        print(f"❌ Lỗi ffmpeg khi burn sub:\n{result.stderr[-1200:]}", file=sys.stderr)
        return False
    return True


def mux_softsub(video_path: Path, srt_path: Path, out_path: Path):
    """Nhúng mềm .srt vào mp4 (codec mov_text), không render lại hình/tiếng."""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(srt_path),
        "-map", "0", "-map", "1",
        "-c", "copy",
        "-c:s", "mov_text",
        "-metadata:s:s:0", "language=vie",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                            errors="replace")
    if result.returncode != 0:
        print(f"❌ Lỗi ffmpeg khi mux sub:\n{result.stderr[-1000:]}", file=sys.stderr)
        return False
    return True


# ----------------------------------------------------------------------------- #
def main():
    parser = argparse.ArgumentParser(
        description="Gắn phụ đề (soft sub) vào video, dùng chữ gốc + căn giờ theo audio."
    )
    parser.add_argument("video", help="Video cần gắn phụ đề (mp4).")
    parser.add_argument("--audio", default=None,
                        help="File audio để căn giờ (mặc định: tách từ video).")
    parser.add_argument("--script", default=None,
                        help="File văn bản kịch bản gốc (mặc định: input.txt cạnh video, "
                             "không có thì lùi về ../kịch_bản/input.txt).")
    parser.add_argument("--out", default=None,
                        help="Video kết quả (mặc định: <tên video>_sub.mp4).")
    parser.add_argument("--model", default="large-v3-turbo",
                        help="Model whisper: tiny/base/small/medium/large-v3-turbo/large-v3 "
                             "(mặc định: large-v3-turbo).")
    parser.add_argument("--max-chars", type=int, default=50,
                        help="Độ dài tối đa mỗi dòng phụ đề (mặc định: 50).")
    parser.add_argument("--burn", action="store_true",
                        help="Vẽ cứng phụ đề vào hình (hardsub, re-encode) thay vì nhúng mềm.")
    parser.add_argument("--kieu", default="hopbo",
                        help="Kiểu phụ đề khi --burn — tên file JSON trong "
                             "scripts/kieusub_mau (mặc định hopbo: hộp bo góc cũ).")
    parser.add_argument("--font", default="",
                        help="Đè font của kiểu khi --burn (tên font trong "
                             "myvoice/fonts hoặc font Windows; rỗng = theo kiểu).")
    parser.add_argument("--mau", default="",
                        help="Đè MÀU CHỮ của kiểu khi --burn (RGB hex, vd FFD700; "
                             "rỗng = theo kiểu).")
    parser.add_argument("--mau-vien", default="",
                        help="Đè MÀU VIỀN quanh chữ khi --burn (RGB hex, vd 00E5FF; "
                             "rỗng = viền gốc của kiểu).")
    parser.add_argument("--cochu", default="",
                        help="Phóng to/thu nhỏ chữ của kiểu khi --burn, tính bằng %% "
                             "(50-200; rỗng hoặc 100 = giữ cỡ gốc của kiểu).")
    parser.add_argument("--dong", type=int, default=1, choices=[1, 2],
                        help="Số DÒNG mỗi lần hiện chữ (1 = như cũ; 2 = gom hai "
                             "dòng một lần, giống ảnh mẫu của kho kiểu).")
    parser.add_argument("--srt-only", action="store_true",
                        help="CHỈ xuất file .srt (vd để tải lên YouTube Studio), không đụng video.")
    args = parser.parse_args()

    video_path = Path(args.video)
    if not video_path.is_file():
        print(f"❌ Không tìm thấy video: {video_path}")
        sys.exit(1)
    script_path = Path(args.script) if args.script else guess_script(video_path)
    if not script_path.is_file():
        print(f"❌ Không tìm thấy file kịch bản: {script_path}")
        sys.exit(1)
    if script_path.stat().st_size == 0:
        print(f"❌ File kịch bản rỗng: {script_path}")
        sys.exit(1)

    out_path = Path(args.out) if args.out else video_path.with_name(video_path.stem + "_sub.mp4")
    srt_path = out_path.with_suffix(".srt")

    # 1) Cue từ kịch bản gốc. Burn theo kiểu font to (Anton, Bangers…) thì kiểu
    # mang trần ký tự/dòng riêng nhỏ hơn — lấy trần chặt hơn giữa kiểu và --max-chars.
    max_chars = args.max_chars
    if args.burn:
        import kieusub
        max_chars = kieusub.chon_max_chars(
            kieusub.ap_cochu(kieusub.ap_font(kieusub.lay(args.kieu), args.font),
                             args.cochu), max_chars)
    text = script_path.read_text(encoding="utf-8")
    cues = build_cues(text, max_chars, args.dong)
    if not cues:
        print("❌ Kịch bản rỗng, không có gì để làm phụ đề.")
        sys.exit(1)
    print(f"✂️  Đã cắt {len(cues)} dòng phụ đề từ: {script_path.name}")

    # 2) Chuẩn bị audio để nghe
    temp_wav = None
    if args.audio:
        audio_path = args.audio
        if Path(audio_path).suffix.lower() not in AUDIO_EXTS:
            temp_wav = str(out_path.with_name(out_path.stem + "_temp16k.wav"))
            if not extract_audio(audio_path, temp_wav):
                sys.exit(1)
            audio_path = temp_wav
    else:
        temp_wav = str(out_path.with_name(out_path.stem + "_temp16k.wav"))
        print("🎧 Tách audio từ video để căn giờ...")
        if not extract_audio(str(video_path), temp_wav):
            sys.exit(1)
        audio_path = temp_wav

    audio_dur = get_audio_duration(audio_path) or 0
    if audio_dur:
        print(f"⏳ Thời lượng audio: {audio_dur / 60:.1f} phút")

    # 3) Nghe + khớp
    def _prog(frac):
        print(f"\r   tiến độ nghe: {frac * 100:5.1f}%", end="", flush=True)

    w_words, w_starts, w_ends = transcribe_words(audio_path, args.model, on_progress=_prog)
    print()
    if not w_words:
        print("⚠️ Whisper không nhận được từ nào — phụ đề sẽ rải đều theo thời lượng.")
    cue_times = align_cues(cues, w_words, w_starts, w_ends, audio_dur)

    # 4) SRT + mux
    write_srt(cues, cue_times, srt_path)
    print(f"💾 Đã ghi phụ đề: {srt_path}")

    def _cleanup_temp():
        if temp_wav and os.path.exists(temp_wav):
            try:
                os.remove(temp_wav)
            except Exception:
                pass

    if args.srt_only:
        # Chỉ cần .srt (tải lên YouTube Studio) — không copy/re-encode file video.
        _cleanup_temp()
        print("\n✅ Hoàn tất! (chỉ xuất .srt — video giữ nguyên, không bị đụng vào)")
        print(f"   File .srt : {srt_path}  ({len(cues)} dòng)")
        print("   Tải lên: YouTube Studio → video → Phụ đề → Tải tệp lên → chọn .srt")
        return

    if args.burn:
        # Burn thì dùng .ass (mang được kiểu riêng) chứ không phải .srt: ép .srt
        # bằng force_style chỉ ra khung nền VUÔNG. Kiểu lấy từ kho kieusub_mau.
        import kieusub
        kieu = kieusub.ap_cochu(
            kieusub.ap_mau_vien(
                kieusub.ap_mau(kieusub.ap_font(kieusub.lay(args.kieu), args.font),
                               args.mau), args.mau_vien), args.cochu)
        ass_path = kieusub.write_ass_kieu(cues, cue_times,
                                          srt_path.with_suffix(".ass"), kieu)
        print(f"💾 Đã ghi kiểu phụ đề: {kieu['ten']} ({kieu['id']}) → {ass_path.name}")
        print("🎬 Đang VẼ CỨNG phụ đề vào hình (re-encode, hơi lâu)...")
        ok = burn_subs(video_path, ass_path, out_path)
    else:
        print("🎬 Đang nhúng phụ đề (soft sub) vào video...")
        ok = mux_softsub(video_path, srt_path, out_path)

    _cleanup_temp()

    if not ok:
        sys.exit(1)
    size_mb = out_path.stat().st_size / 1024 / 1024
    print(f"\n✅ Hoàn tất!")
    print(f"   Video có sub : {out_path}  ({size_mb:.1f} MB)")
    print(f"   File .srt     : {srt_path}")
    print("   (Phụ đề mềm — bật/tắt trong trình phát. Nếu player không hiện, mở .srt kèm theo.)")


if __name__ == "__main__":
    main()
