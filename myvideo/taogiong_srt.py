# -*- coding: utf-8 -*-
"""
taogiong_srt.py — Tạo giọng OmniVoice cho TỪNG CÂU của SRT tiếng Việt, rồi
SẮP XẾP các audio trên timeline (chống đè) — CHƯA gắn vào video.

Vì sao phải sắp xếp: câu tiếng Việt đọc bằng OmniVoice thường DÀI hơn khe thời
gian của câu gốc tiếng Trung trong SRT, nên đặt audio đúng mốc SRT là chúng đè
lên nhau. Logic sắp xếp lấy NGUYÊN VĂN từ auto_fix_capcut.py (dự án
GetLinktoText/XulyAmThanh — phần xếp audio CapCut draft_content.json):

  • get_timeline_end   — biên phải cứng; biên trái là 0.
  • is_overlap         — max(startA,startB) < min(endA,endB).
  • Vòng chính         — sort theo start, quét từng cặp liền kề, gặp cặp đè
                         đầu tiên thì giải quyết rồi sort lại quét lại;
                         dừng khi 1 vòng không đổi gì.
  • resolve_pair_with_blocks — thang leo k = 1,2,3…: đẩy D phải → C trái →
                         block (D,E) phải → block (C,B) trái → … Block đẩy
                         phải không vượt timeline_end / không đè segment sau;
                         đẩy trái không xuống dưới 0 / không đè segment trước.
                         Hàm shift trả LƯỢNG DỊCH THỰC TẾ nên tận dụng được
                         từng khe trống nhỏ.
  • Đơn vị: MICRO GIÂY (μs) — giữ đúng đơn vị CapCut để port không sai một ly.

Khác bản gốc DUY NHẤT một chỗ (có chủ đích): MAX_ITER không cố định 300 mà
= max(300, 3 × số câu) — SRT có cả nghìn câu, mỗi vòng chỉ giải quyết 1 cặp
nên 300 vòng không đủ; vẫn giữ vai trò chốt chặn lặp vô tận như bản gốc.

Cách dùng:
    python taogiong_srt.py "output/…_x0.7_vi.srt"
    python taogiong_srt.py "….srt" --voice "hachi.mp3" --limit 10   (thử 10 câu)
    python taogiong_srt.py "….srt" --only-arrange     (đã có wav, chỉ xếp lại)

Kết quả (cạnh file SRT):
    <tên>_tts/0001.wav…      — audio từng câu (chạy lại tự bỏ qua câu đã có)
    <tên>_timeline.json      — mốc SRT, mốc ĐÃ XẾP, thời lượng, độ lệch từng câu
    <tên>_sapxep.srt         — SRT theo mốc đã xếp (sub khớp audio mới)
    <tên>_audio.wav          — audio tổng: từng câu đặt đúng mốc đã xếp
"""

import sys
import os

# ── Tự chuyển sang python của venv (torch/omnivoice/soundfile nằm ở đó) ──────
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
_VENV_PYTHON = os.path.join(_REPO_ROOT, "venv", "Scripts", "python.exe")
if __name__ == "__main__" and os.path.exists(_VENV_PYTHON) and \
        os.path.normcase(os.path.abspath(sys.executable)) != \
        os.path.normcase(os.path.abspath(_VENV_PYTHON)):
    import subprocess
    sys.exit(subprocess.run([_VENV_PYTHON] + sys.argv).returncode)

import argparse
import json
import re
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
# Kho giọng RIÊNG của myvideo — độc lập với myvoice (chỉ mượn Ý TƯỞNG chức năng,
# không đọc cài đặt hay kho file bên đó). Thêm/bớt giọng: bỏ file audio vào đây.
VOICE_DIR = SCRIPT_DIR / "voice"

sys.path.insert(0, str(SCRIPT_DIR))
# Bộ kiểm MẤT CHỮ tái dùng của myvoice (taogiong_kiemtra_matchu — chạy CPU,
# không đụng VRAM đang chứa OmniVoice). Tái dùng CODE là chủ trương chung;
# chỉ cấm chia sẻ cài đặt người dùng giữa hai bảng điều khiển.
sys.path.insert(0, str(REPO_ROOT / "myvoice" / "scripts"))
from dich_srt import parse_srt  # noqa: E402  (dùng chung parser SRT)

US = 1_000_000          # 1 giây = 1_000_000 μs (đơn vị CapCut)
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".flac", ".ogg"}

_TS = re.compile(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})")


def _parse_time_line(time_line):
    """'HH:MM:SS,mmm --> HH:MM:SS,mmm' → (start_us, end_us)."""
    m = _TS.findall(time_line)
    if len(m) < 2:
        return 0, 0
    def us(h, mi, s, ms):
        return ((int(h) * 3600 + int(mi) * 60 + int(s)) * 1000 + int(ms)) * 1000
    return us(*m[0]), us(*m[1])


def _fmt_srt_time(t_us):
    ms = int(round(max(t_us, 0) / 1000))
    h, ms = divmod(ms, 3600000)
    mi, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{mi:02d}:{s:02d},{ms:03d}"


# ════════════════════════════════════════════════════════════════════════════
# PHẦN 1 — TẠO GIỌNG OmniVoice cho từng câu (cách gọi y hệt myvoice/taogiong.py)
# ════════════════════════════════════════════════════════════════════════════
def resolve_voice(name):
    """Tìm file giọng mẫu: đường dẫn đầy đủ → tên trong myvideo/voice/ →
    file audio đầu tiên trong kho."""
    if name:
        p = Path(name)
        if p.is_file():
            return p
        p = VOICE_DIR / name
        if p.is_file():
            return p
        print(f"⚠️ Không thấy giọng '{name}' — dùng giọng mặc định thay thế.")
    try:
        entries = sorted(VOICE_DIR.iterdir())
    except OSError:
        return None
    for p in entries:
        if p.is_file() and p.suffix.lower() in AUDIO_EXTS:
            return p
    return None


# Ký tự chỉ để hiển thị, đọc lên vô nghĩa/đọc sai — bỏ trước khi TTS.
_STRIP_FOR_TTS = str.maketrans("", "", "\"'“”‘’«»「」『』()（）[]…—–-")


def tts_text(text):
    """Chuẩn hoá 1 câu trước khi đưa vào OmniVoice (thường hoá như taogiong.py)."""
    t = re.sub(r"\s{2,}", " ", text.translate(_STRIP_FOR_TTS)).strip().lower()
    # Dòng SRT thường KHÔNG có dấu kết câu → thêm "." để vn_duration cộng khoảng
    # nghỉ cuối và model có tín hiệu hết câu — đỡ đọc gấp/nuốt từ cuối. Dấu giữa
    # câu đứng cuối thì THAY bằng "." (",." dính nhau làm TTS đọc cụt — bài học
    # từ amain_taogiong_gui).
    if t and t[-1] in ",;:":
        t = t[:-1].rstrip() + "."
    elif t and t[-1] not in ".!?":
        t += "."
    return t


# ── Khung thời lượng theo ÂM TIẾT tiếng Việt ─────────────────────────────────
# Chép từ myvoice/scripts/amain_taogiong_gui.py (module GUI nặng, không import
# làm thư viện được — xem chú thích bên đó về số đo hiệu chỉnh). VÌ SAO CẦN:
# OmniVoice sinh song song — CHỐT trước số token audio rồi mới nhồi chữ vào
# khung đó; để model tự đoán theo trọng số KÝ TỰ thì câu tiếng Việt nhiều từ
# ngắn bị khung quá hẹp → đọc gấp, TỪ CUỐI nhỏ dần rồi mất. Tính khung theo số
# âm tiết thì nhịp đọc đều và đủ chỗ cho từ cuối.
VN_RATE      = 4.65   # âm tiết/giây khi đang nói liên tục
VN_PAUSE_MID = 0.112  # giây nghỉ thêm cho mỗi dấu , ; :
VN_PAUSE_END = 0.262  # giây nghỉ thêm cho mỗi dấu . ! ?
NUM_STEP     = 32     # số bước giải mã — mặc định tác giả model đã kiểm

_VN_TOKEN  = re.compile(r"[0-9A-Za-zÀ-ỹà-ỹ]+")
_VN_MID_RE = re.compile(r"[,;:]")
_VN_END_RE = re.compile(r"[.!?]")
_VN_SYL_PER_DIGIT = 1.5          # "26" → "hai mươi sáu": mỗi chữ số ~1.5 âm tiết
_VN_CJK    = re.compile(r"[一-鿿㐀-䶿豈-﫿]")   # chữ Hán sót qua bước dịch
_VN_VOWELS = re.compile(r"[aeiouyàáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩị"
                        r"òóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵ]+")


def _vn_syl_token(tok):
    """Số âm tiết đọc ra của MỘT token (text đã .lower() trước khi vào đây)."""
    if tok.isdigit():
        return len(tok) * _VN_SYL_PER_DIGIT
    if any(c.isdigit() for c in tok):
        return sum(_VN_SYL_PER_DIGIT if c.isdigit() else 1 for c in tok)
    return max(1, len(_VN_VOWELS.findall(tok)))


def vn_duration(text):
    """Số giây nên dành cho câu `text` — None nếu không có âm tiết nào
    (ép duration khi đó sẽ lỗi, để model tự đoán)."""
    syllables = sum(_vn_syl_token(tok) for tok in _VN_TOKEN.findall(text))
    syllables += len(_VN_CJK.findall(text))
    if not syllables:
        return None
    return (syllables / VN_RATE
            + len(_VN_MID_RE.findall(text)) * VN_PAUSE_MID
            + len(_VN_END_RE.findall(text)) * VN_PAUSE_END)


def generate_all(cues, voice_path, tts_dir, redo=False):
    """Sinh wav cho từng câu (bỏ qua câu đã có — chạy lại là tiếp tục).

    Trả về (files, model, sr): files là list đường dẫn wav song song với cues
    (None nếu câu rỗng/lỗi); model/sr để bước kiểm mất chữ đọc lại câu hỏng
    (model = None khi mọi câu đã có sẵn, chưa phải nạp).
    """
    import soundfile as sf

    tts_dir.mkdir(exist_ok=True)
    todo = []
    for i, (_t, text) in enumerate(cues):
        f = tts_dir / f"{i + 1:04d}.wav"
        if redo or not f.exists():
            todo.append((i, f, tts_text(text)))

    files = [tts_dir / f"{i + 1:04d}.wav" for i in range(len(cues))]
    if not todo:
        print("♻ Toàn bộ câu đã có audio — bỏ qua bước tạo giọng.")
        return files, None, 0

    print(f"🔊 Giọng mẫu: {voice_path.name}")
    model, sr = _load_omnivoice()

    done_before = len(cues) - len(todo)
    if done_before:
        print(f"♻ {done_before} câu đã có sẵn, còn {len(todo)} câu cần tạo.")
    for n, (i, f, text) in enumerate(todo, 1):
        if not text:
            files[i] = None
            continue
        print(f"  [{n}/{len(todo)}] câu {i + 1}: {text[:50]!r}")
        try:
            sf.write(str(f), _doc_cau(model, text, voice_path), sr)
        except Exception as e:
            print(f"  ⚠️ Câu {i + 1} lỗi TTS: {e} — bỏ qua.")
            files[i] = None
    return files, model, sr


def _load_omnivoice():
    import torch
    from omnivoice.models.omnivoice import OmniVoice
    from omnivoice.utils.common import get_best_device

    device = get_best_device()
    print(f"⏳ Đang tải model OmniVoice ({device})…")
    model = OmniVoice.from_pretrained("k2-fsa/OmniVoice", device_map=device,
                                      dtype=torch.float16)
    return model, model.sampling_rate


def _doc_cau(model, text, voice_path, dur_scale=1.0):
    """Đọc MỘT câu → mảng audio. language + duration + num_step: cùng bộ tham
    số bên myvoice — thiếu duration là khung bị đoán hụt, nuốt từ cuối câu.
    dur_scale: nới khung khi đọc lại câu bị nuốt chữ (lượt 2 dùng 1.08)."""
    dur = vn_duration(text)
    if dur is not None:
        dur *= dur_scale
    return model.generate(text=text, ref_audio=str(voice_path),
                          language="vi", duration=dur, num_step=NUM_STEP)[0]


# ── Kiểm MẤT CHỮ + đọc lại câu hỏng (tái dùng taogiong_kiemtra_matchu) ───────
def kiemtra_va_docla(cues, files, tts_dir, voice_path, model, sr):
    """ASR đối chiếu TỪNG câu với văn bản (2 tầng small→medium, chạy CPU).
    Câu bị nuốt chữ được đọc lại ngay: lượt 1 re-roll, lượt 2 nới khung +8%.
    OmniVoice là masked-diffusion nên thi thoảng nuốt cụm từ — đo bên myvoice
    là 7–12% số đoạn; có vòng này thì mọi video tự được "bảo hành đủ chữ"."""
    import shutil

    import soundfile as sf
    try:
        import taogiong_kiemtra_matchu as ktm
    except Exception as e:
        print(f"⚠️ Bỏ qua kiểm tra mất chữ (không nạp được bộ kiểm: {e})")
        return

    texts = [tts_text(t) for _t, t in cues]
    # Bộ kiểm đọc file <i:04d>.wav ĐÁNH SỐ TỪ 0 theo index — file của ta đánh
    # từ 0001 nên chép sang thư mục đệm cho đúng khuôn (wav nhỏ, không đáng kể).
    shim = Path(tts_dir) / "_kiemtra"
    shim.mkdir(exist_ok=True)

    def _sync(idxs):
        for i in idxs:
            if files[i] and Path(files[i]).exists():
                shutil.copy(files[i], shim / f"{i:04d}.wav")

    try:
        _sync(range(len(cues)))
        print(f"🕵️ Kiểm tra mất chữ {len(cues)} câu (ASR trên CPU)...")
        bad = ktm.quet_va_xac_minh(texts, shim, on_log=print)
        for lan, scale in ((1, 1.0), (2, 1.08)):
            if not bad:
                break
            print(f"🔁 Lượt đọc lại {lan}: {len(bad)} câu nuốt chữ "
                  f"(câu {', '.join(str(i + 1) for i in sorted(bad))})...")
            if model is None:
                model, sr = _load_omnivoice()
            for i in sorted(bad):
                try:
                    sf.write(str(files[i]),
                             _doc_cau(model, texts[i], voice_path, dur_scale=scale), sr)
                except Exception as e:
                    print(f"  ⚠️ Câu {i + 1} lỗi khi đọc lại: {e}")
            _sync(sorted(bad))
            bad = ktm.quet_va_xac_minh(texts, shim, on_log=print,
                                       chi_cac_doan=set(bad))
        if bad:
            print(f"⚠️ Còn {len(bad)} câu chưa đủ chữ sau 2 lượt đọc lại "
                  f"(câu {', '.join(str(i + 1) for i in sorted(bad))}) — nên nghe lại tay.")
        else:
            print("✅ Kiểm tra mất chữ: đủ chữ toàn bộ.")
    finally:
        ktm.giai_phong()
        shutil.rmtree(shim, ignore_errors=True)


# ════════════════════════════════════════════════════════════════════════════
# PHẦN 2 — SẮP XẾP audio chống đè
# Port NGUYÊN VĂN từ GetLinktoText/SourceTruyen/XulyAmThanh/auto_fix_capcut.py
# (chỉ bỏ phần đọc CapCut draft — segment ở đây do ta tự dựng, cùng cấu trúc
#  {"id", "target_timerange": {"start", "duration"}}, đơn vị μs).
# ════════════════════════════════════════════════════════════════════════════
def is_overlap(seg_a, seg_b):
    """Kiểm tra 2 segment có đè nhau không (theo target_timerange)."""
    a = seg_a["target_timerange"]
    b = seg_b["target_timerange"]
    startA, endA = a["start"], a["start"] + a["duration"]
    startB, endB = b["start"], b["start"] + b["duration"]
    return max(startA, startB) < min(endA, endB)


def shift_block_right(segments, start_index, block_len, amount, timeline_end):
    """Dời block segments[start_index .. start_index+block_len-1] sang phải,
    không vượt timeline_end và không đè segment kế tiếp. Trả lượng dịch thực tế."""
    n = len(segments)
    if amount <= 0 or start_index >= n:
        return 0
    end_index = min(start_index + block_len - 1, n - 1)
    if end_index < start_index:
        return 0
    block = segments[start_index: end_index + 1]

    max_end_block = max(s["target_timerange"]["start"] + s["target_timerange"]["duration"]
                        for s in block)
    max_shift = timeline_end - max_end_block

    if end_index < n - 1:
        next_start = segments[end_index + 1]["target_timerange"]["start"]
        last = segments[end_index]["target_timerange"]
        max_shift = min(max_shift, next_start - (last["start"] + last["duration"]))

    max_shift = max(0, max_shift)
    shift = min(amount, max_shift)
    if shift <= 0:
        return 0
    for s in block:
        s["target_timerange"]["start"] += shift
    return shift


def shift_block_left(segments, end_index, block_len, amount, min_start=0):
    """Dời block segments[end_index-block_len+1 .. end_index] sang trái,
    không cho xuống dưới min_start và không đè segment ngay trước block."""
    n = len(segments)
    if amount <= 0 or end_index < 0:
        return 0
    end_index = min(end_index, n - 1)
    start_index = max(0, end_index - block_len + 1)
    if start_index > end_index:
        return 0
    block = segments[start_index: end_index + 1]

    min_start_block = min(s["target_timerange"]["start"] for s in block)
    max_shift = min_start_block - min_start

    if start_index > 0:
        prev = segments[start_index - 1]["target_timerange"]
        first_start = segments[start_index]["target_timerange"]["start"]
        max_shift = min(max_shift, first_start - (prev["start"] + prev["duration"]))

    max_shift = max(0, max_shift)
    shift = min(amount, max_shift)
    if shift <= 0:
        return 0
    for s in block:
        s["target_timerange"]["start"] -= shift
    return shift


def resolve_pair_with_blocks(segments, idx, timeline_end):
    """Xử lý cặp (C=segments[idx], D=segments[idx+1]) theo thang leo dần:
    đẩy D phải → C trái → block (D,E) phải → block (C,B) trái → … (k tăng dần).
    Trả về True nếu có thay đổi."""
    if idx < 0 or idx + 1 >= len(segments):
        return False
    C = segments[idx]
    D = segments[idx + 1]

    def overlap():
        return is_overlap(C, D)

    if not overlap():
        return False

    changed = False
    left_count = idx + 1
    right_count = len(segments) - (idx + 1)
    max_k = max(left_count, right_count)

    for k in range(1, max_k + 1):
        moved_this_k = False

        if overlap() and right_count >= k:
            need = (C["target_timerange"]["start"] + C["target_timerange"]["duration"]
                    - D["target_timerange"]["start"])
            if need > 0 and shift_block_right(segments, idx + 1, k, need, timeline_end) > 0:
                changed = True
                moved_this_k = True
        if not overlap():
            return changed

        if overlap() and left_count >= k:
            need = (C["target_timerange"]["start"] + C["target_timerange"]["duration"]
                    - D["target_timerange"]["start"])
            if need > 0 and shift_block_left(segments, idx, k, need, min_start=0) > 0:
                changed = True
                moved_this_k = True
        if not overlap():
            return changed

        if not moved_this_k:
            continue

    return changed


def process_all_audio_segments(segments, timeline_end):
    """Vòng ngoài của bản gốc: sort → quét cặp liền kề → giải quyết cặp đè đầu
    tiên → sort lại quét lại; dừng khi một vòng không đổi gì.

    MAX_ITER: bản gốc cố định 300; ở đây = max(300, 3 × số câu) vì SRT có cả
    nghìn segment (mỗi vòng chỉ xử 1 cặp) — vẫn là chốt chặn lặp vô tận.
    """
    if len(segments) <= 1:
        print("  Ít hơn 2 segment audio, bỏ qua.")
        return False

    max_iter = max(300, 3 * len(segments))
    for iteration in range(1, max_iter + 1):
        segments.sort(key=lambda s: s["target_timerange"]["start"])
        changed_any = False
        before_positions = [s["target_timerange"]["start"] for s in segments]

        for i in range(len(segments) - 1):
            if not is_overlap(segments[i], segments[i + 1]):
                continue
            if resolve_pair_with_blocks(segments, i, timeline_end):
                changed_any = True
                break  # sort lại rồi xử tiếp ở vòng sau

        after_positions = [s["target_timerange"]["start"] for s in segments]
        if not changed_any or after_positions == before_positions:
            print(f"  Không còn thay đổi sau {iteration} vòng, dừng.")
            return True

    print(f"  ⚠ Đạt MAX_ITER ({max_iter}), dừng để tránh lặp vô tận.")
    return True


def count_overlaps(segments):
    ordered = sorted(segments, key=lambda s: s["target_timerange"]["start"])
    return sum(1 for a, b in zip(ordered, ordered[1:]) if is_overlap(a, b))


def ep_trai_con_de(segments):
    """Vòng VÉT sau thang leo: còn cặp đè (thường do đuôi video chạm biên phải,
    không đẩy phải được nữa) thì NÉN khối bên trái về phía 0 — gom nốt từng khe
    hở còn sót và cả khoảng trống TRƯỚC câu đầu tiên. Trả về tổng μs đã nén.

    Chỉ cứu được khi phía trái còn chỗ; timeline đã kín từ 0 thì đành chịu
    (tổng tiếng dài hơn khung video — không phép dời nào xử được)."""
    segments.sort(key=lambda s: s["target_timerange"]["start"])
    tong = 0
    for i in range(1, len(segments)):
        a = segments[i - 1]["target_timerange"]
        b = segments[i]["target_timerange"]
        need = a["start"] + a["duration"] - b["start"]
        while need > 0:
            # tìm khe hở GẦN i nhất về phía trái (kể cả trước câu 0)
            gj, gap = None, 0
            for j in range(i - 1, -1, -1):
                tr = segments[j]["target_timerange"]
                floor = 0 if j == 0 else (segments[j - 1]["target_timerange"]["start"]
                                          + segments[j - 1]["target_timerange"]["duration"])
                g = tr["start"] - floor
                if g > 0:
                    gj, gap = j, g
                    break
            if gj is None:                      # kín tới tận 0 — hết cách
                break
            dich = min(need, gap)
            for k in range(gj, i):
                segments[k]["target_timerange"]["start"] -= dich
            need -= dich
            tong += dich
    return tong


# ════════════════════════════════════════════════════════════════════════════
# PHẦN 3 — Ghi kết quả
# ════════════════════════════════════════════════════════════════════════════
def get_timeline_end(segments, video_path):
    """Biên phải cứng: bản gốc lấy end lớn nhất của MỌI segment (video + audio).
    Ở đây 'segment video' chính là cả video nền → thời lượng video (nếu có)."""
    max_end = max((s["target_timerange"]["start"] + s["target_timerange"]["duration"]
                   for s in segments), default=0)
    if video_path and Path(video_path).is_file():
        import subprocess
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            video_end = int(float(r.stdout.strip()) * US)
            print(f"🎞 Video nền: {Path(video_path).name} — {video_end / US:.1f}s")
            return max(max_end, video_end)
        except Exception as e:
            print(f"⚠️ Không đọc được thời lượng video ({e}) — dùng end lớn nhất của audio.")
    return max_end


def mix_audio(segments, out_wav, timeline_end):
    """Đặt từng wav vào đúng mốc ĐÃ XẾP trên một nền im lặng dài timeline_end."""
    import numpy as np
    import soundfile as sf

    sr = None
    for s in segments:
        if s.get("wav"):
            sr = sf.info(str(s["wav"])).samplerate
            break
    if sr is None:
        return None
    canvas = np.zeros(int(timeline_end / US * sr) + sr, dtype="float32")
    for s in segments:
        if not s.get("wav"):
            continue
        data, _ = sf.read(str(s["wav"]), dtype="float32")
        if data.ndim > 1:
            data = data.mean(axis=1)
        o = int(s["target_timerange"]["start"] / US * sr)
        end = min(o + len(data), len(canvas))
        canvas[o:end] += data[:end - o]
    np.clip(canvas, -1.0, 1.0, out=canvas)
    sf.write(str(out_wav), canvas, sr, subtype="PCM_16")
    return out_wav


def main():
    parser = argparse.ArgumentParser(
        description="TTS OmniVoice theo SRT tiếng Việt + sắp xếp audio chống đè.")
    parser.add_argument("srt", help="File .srt tiếng Việt (…_vi.srt).")
    parser.add_argument("--voice", default="",
                        help="Giọng mẫu: tên file trong myvideo/voice hoặc đường dẫn "
                             "(mặc định: file audio đầu tiên trong myvideo/voice).")
    parser.add_argument("--video", default="",
                        help="Video nền để lấy biên phải (mặc định: tự tìm "
                             "<tên bỏ _vi>.mp4 cạnh SRT).")
    parser.add_argument("--limit", type=int, default=0,
                        help="Chỉ làm N câu đầu (để thử). 0 = tất cả.")
    parser.add_argument("--only-arrange", action="store_true",
                        help="Bỏ qua TTS (wav đã có) — chỉ sắp xếp + ghi kết quả.")
    parser.add_argument("--redo-tts", action="store_true",
                        help="Tạo lại toàn bộ audio, bỏ qua wav đã có.")
    parser.add_argument("--no-kiemtra", action="store_true",
                        help="Bỏ bước kiểm mất chữ bằng ASR + đọc lại câu hỏng.")
    args = parser.parse_args()

    srt_path = Path(args.srt)
    if not srt_path.is_file():
        print(f"❌ Không tìm thấy file: {srt_path}")
        sys.exit(1)

    cues = parse_srt(str(srt_path))
    if args.limit > 0:
        cues = cues[:args.limit]
    if not cues:
        print("❌ SRT không có câu nào.")
        sys.exit(1)
    print(f"📖 {len(cues)} câu từ: {srt_path.name}")

    stem = srt_path.with_suffix("")          # …_x0.7_vi
    tts_dir = Path(str(stem) + "_tts")

    # ── 1. TTS từng câu ──────────────────────────────────────────────────────
    if args.only_arrange:
        files = [tts_dir / f"{i + 1:04d}.wav" for i in range(len(cues))]
        files = [f if f.exists() else None for f in files]
        print(f"♻ --only-arrange: dùng {sum(1 for f in files if f)} wav có sẵn trong {tts_dir.name}/")
    else:
        voice = resolve_voice(args.voice)
        if voice is None:
            print(f"❌ Không tìm thấy giọng mẫu nào trong {VOICE_DIR}")
            sys.exit(1)
        files, model, sr = generate_all(cues, voice, tts_dir, redo=args.redo_tts)
        # 1b. Kiểm mất chữ + đọc lại câu hỏng NGAY (trước khi xếp timeline —
        # câu đọc lại có thể đổi thời lượng nên phải xong xuôi rồi mới xếp).
        if not args.no_kiemtra:
            kiemtra_va_docla(cues, files, tts_dir, voice, model, sr)

    # ── 2. Dựng segment (μs) và sắp xếp ─────────────────────────────────────
    import soundfile as sf
    segments = []
    for i, ((time_line, text), wav) in enumerate(zip(cues, files)):
        if not wav:
            continue
        start_us, _end_us = _parse_time_line(time_line)
        dur_us = int(sf.info(str(wav)).duration * US)
        segments.append({
            "id": i + 1, "text": text, "wav": str(wav), "srt_start": start_us,
            "target_timerange": {"start": start_us, "duration": dur_us},
        })
    if not segments:
        print("❌ Không có audio nào để sắp xếp.")
        sys.exit(1)

    video = args.video or str(stem).removesuffix("_vi") + ".mp4"
    timeline_end = get_timeline_end(segments, video)
    print(f"📐 Biên phải timeline: {timeline_end / US:.1f}s | "
          f"đè nhau trước khi xếp: {count_overlaps(segments)} cặp")

    process_all_audio_segments(segments, timeline_end)

    # Vét lần cuối: cặp nào còn đè (đuôi chạm biên phải) thì nén về trái.
    if count_overlaps(segments):
        nen = ep_trai_con_de(segments)
        if nen:
            print(f"⬅ Nén thêm về trái {nen / US:.2f}s cho các cặp còn đè.")

    remaining = count_overlaps(segments)
    shifts = [abs(s["target_timerange"]["start"] - s["srt_start"]) for s in segments]
    print(f"📊 Sau khi xếp: còn {remaining} cặp đè | lệch so với SRT: "
          f"trung bình {sum(shifts) / len(shifts) / US:.2f}s, "
          f"lớn nhất {max(shifts) / US:.2f}s")

    # ── 3. Ghi kết quả ──────────────────────────────────────────────────────
    segments.sort(key=lambda s: s["target_timerange"]["start"])

    out_json = Path(str(stem) + "_timeline.json")
    out_json.write_text(json.dumps({
        "srt": srt_path.name, "timeline_end_us": timeline_end,
        "remaining_overlaps": remaining,
        "cues": [{
            "id": s["id"], "text": s["text"], "wav": s["wav"],
            "srt_start_ms": s["srt_start"] // 1000,
            "start_ms": s["target_timerange"]["start"] // 1000,
            "duration_ms": s["target_timerange"]["duration"] // 1000,
            "shift_ms": (s["target_timerange"]["start"] - s["srt_start"]) // 1000,
        } for s in segments],
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"💾 Timeline       : {out_json.name}")

    out_srt = Path(str(stem) + "_sapxep.srt")
    with open(out_srt, "w", encoding="utf-8") as f:
        for n, s in enumerate(segments, 1):
            tr = s["target_timerange"]
            f.write(f"{n}\n{_fmt_srt_time(tr['start'])} --> "
                    f"{_fmt_srt_time(tr['start'] + tr['duration'])}\n{s['text']}\n\n")
    print(f"💾 SRT đã xếp     : {out_srt.name}")

    out_wav = Path(str(stem) + "_audio.wav")
    if mix_audio(segments, out_wav, timeline_end):
        print(f"💾 Audio tổng     : {out_wav.name}")

    print("\n✅ Xong. Audio CHƯA gắn vào video — bước gắn làm riêng sau khi nghe thử.")


if __name__ == "__main__":
    main()
