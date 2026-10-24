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
    python taogiong_srt.py "….srt" --sang 0           (tắt 🔆 sáng giọng; mặc định 80)
    python taogiong_srt.py "….srt" --pitch 1 --vang 80 76 --thieunien 30
                                   (tông giọng + bộ lọc như myvoice; mặc định 0 = tắt)

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
# Kho giọng: từ 24/10/2026 DÙNG CHUNG DANH SÁCH với myvoice (myvoice/voice — user
# soạn danh sách giọng mới ở đó; .prompt.pt / .sang<N>.prompt.pt bên đó dùng lại
# được vì cùng cách lưu). Kho cũ myvideo/voice vẫn đọc thêm để giọng đã chọn
# không mất; trùng tên thì myvoice/voice thắng. Cài đặt vẫn riêng (web_settings).
VOICE_DIRS = (REPO_ROOT / "myvoice" / "voice", SCRIPT_DIR / "voice")
VOICE_DIR = VOICE_DIRS[0]      # tên cũ — kho tìm ĐẦU TIÊN

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
    """Tìm file giọng mẫu: đường dẫn đầy đủ → tên file trong các kho VOICE_DIRS
    (myvoice/voice trước, rồi myvideo/voice) → file audio đầu tiên tìm thấy."""
    if name:
        p = Path(name)
        if p.is_file():
            return p
        for d in VOICE_DIRS:
            p = d / name
            if p.is_file():
                return p
        print(f"⚠️ Không thấy giọng '{name}' — dùng giọng mặc định thay thế.")
    for d in VOICE_DIRS:
        try:
            entries = sorted(d.iterdir())
        except OSError:
            continue
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


# ── Khung thời lượng theo ÂM TIẾT tiếng Việt — DÙNG CHUNG với myvoice ────────
# Trước 13/10/2026 khối này CHÉP NGUYÊN VĂN từ myvoice/scripts/amain_taogiong_gui.py
# (VN_RATE/VN_PAUSE_*/NUM_STEP + vn_duration); nay import thẳng để myvoice chỉnh
# nhịp đọc là bên này theo luôn, không còn hai bản chực lệch nhau. Import module
# GUI là AN TOÀN: cửa sổ chỉ mở dưới __main__ — taogiong_chia_cau và web runner
# bên myvoice cũng import đúng kiểu này. VÌ SAO CẦN vn_duration: OmniVoice sinh
# song song — CHỐT trước số token audio rồi mới nhồi chữ vào khung đó; để model
# tự đoán theo trọng số KÝ TỰ thì câu tiếng Việt nhiều từ ngắn bị khung quá hẹp
# → đọc gấp, TỪ CUỐI nhỏ dần rồi mất (xem chú thích hiệu chỉnh bên myvoice).
# detect_spike cũng lấy từ đó: quét tiếng TO bất thường / file câm — cùng một
# hàm với run_tts bên myvoice (lớp kiểm thô chạy trước lớp ASR).
from amain_taogiong_gui import (  # noqa: E402
    NUM_STEP, detect_spike, vn_duration,
    # 24/10/2026 — GỘP CODE TRÙNG: các hàm dưới trước đây CHÉP LẠI trong file này
    # (nạp model, trả VRAM, dựng prompt giọng mẫu, đọc một câu). Nay dùng thẳng
    # bản của myvoice — sửa một nơi là hai bảng cùng theo. Tên cũ giữ qua alias.
    load_omnivoice as _load_omnivoice, _tra_vram, _do_omnivoice, _voice_prompt,
    _generate_chunk,
    # Mang từ myvoice sang (trước đây myvideo chưa có): cân mức giữa các câu, nén
    # nhẹ + chuẩn độ to -14 LUFS, tông giọng + bộ lọc giọng (mix_audio / main).
    _balance_chunk_levels, _loudnorm_file, SPEECH_COMPRESSOR, VOICE_LUFS, parse_pitch)
# 🔆 SÁNG GIỌNG (23/10/2026) — bộ lọc trị giọng clone "ồm" (giọng mẫu dồn năng
# lượng vào 150–600 Hz, model chép y nguyên). Dùng chung LÕI với myvoice
# (scripts/hieuung_giong.py: chuỗi EQ ffmpeg + eq_giong_mau_tam), còn MỨC là cài
# đặt riêng của myvideo: khoá sanggiong trong web/web_settings.json (mặc định 80),
# bước ③ truyền qua --sang. Áp ở hai chỗ như bên myvoice: EQ giọng mẫu trong bộ
# nhớ lúc dựng prompt (_voice_prompt) và EQ lên audio tổng _audio.wav sau khi
# trộn (main) — từng câu không EQ riêng để khỏi gọi ffmpeg cả nghìn lần.
import hieuung_giong as hu  # noqa: E402

SANG_MAC_DINH = 80

# Các hàm dùng chung với myvoice ghi nhật ký qua logging (bài thật có cửa sổ log
# riêng); đây là script dòng lệnh nên đẩy thẳng ra stdout để trang web myvideo
# thấy đủ (nạp prompt, cân mức, chuẩn độ to…).
import logging  # noqa: E402
logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout, force=True)


def generate_all(cues, voice_path, tts_dir, redo=False, sang=0):
    """Sinh wav cho từng câu (bỏ qua câu đã có — chạy lại là tiếp tục).

    Trả về (files, model, sr): files là list đường dẫn wav song song với cues
    (None nếu câu rỗng/lỗi); model/sr để bên gọi tự dỡ khỏi VRAM
    (model = None khi mọi câu đã có sẵn, chưa phải nạp).
    sang: mức 🔆 Sáng giọng 0–100 — EQ giọng mẫu lúc dựng prompt; mức khác lần
    chạy trước (ghi trong _vanban.json) thì đọc lại toàn bộ câu.
    """
    import soundfile as sf

    tts_dir.mkdir(exist_ok=True)
    # SỔ VĂN BẢN của từng wav: 0007.wav là câu nào. Không có sổ này thì "wav đã
    # có → bỏ qua" là bẫy — dịch lại (đổi cách cắt câu, sửa tay bản dịch) làm
    # câu thứ 7 thành câu khác hẳn, mà wav cũ vẫn nằm đó nên video ra lắp giọng
    # của câu cũ vào chỗ câu mới. So sổ thì chỉ đọc lại đúng câu đã đổi.
    so_van_ban = tts_dir / "_vanban.json"
    moi = [tts_text(t) for _tl, t in cues]
    # Từ 23/10/2026 sổ ghi thêm MỨC SÁNG GIỌNG đã dùng: {"sang": N, "cau": [...]}
    # (sổ cũ là list thuần = mức 0). Mức khác lần trước → prompt giọng mẫu khác →
    # giọng khác → phải đọc lại TOÀN BỘ, không thì nửa bài giọng cũ nửa bài mới.
    sang = hu.parse_fx(sang)
    sang_cu = 0
    try:
        cu = json.loads(so_van_ban.read_text(encoding="utf-8"))
        if isinstance(cu, dict):
            sang_cu, cu = hu.parse_fx(cu.get("sang"), 0), list(cu.get("cau") or [])
    except Exception:
        # Thư mục của bản cũ (chưa có sổ): tin đám wav đang có nếu SỐ LƯỢNG khớp
        # số câu; lệch số là chắc chắn cắt câu đã khác → đọc lại từ đầu.
        co = sorted(tts_dir.glob("[0-9][0-9][0-9][0-9].wav"))
        cu = list(moi) if len(co) == len(cues) else []
        if len(co) != len(cues):
            print(f"⚠️ Thư mục có {len(co)} wav cũ mà bản dịch nay {len(cues)} câu "
                  "— cắt câu đã khác, đọc lại từ đầu cho khỏi lắp nhầm giọng.")
    doi_sang = bool(cu) and sang_cu != sang
    if doi_sang and not redo:
        print(f"🔆 Mức sáng giọng đổi {sang_cu} → {sang} (EQ giọng mẫu lúc dựng prompt) "
              f"→ đọc lại toàn bộ {len(cues)} câu.")
        redo = True
    todo = []
    for i, text in enumerate(moi):
        f = tts_dir / f"{i + 1:04d}.wav"
        if redo or not f.exists() or i >= len(cu) or cu[i] != text:
            todo.append((i, f, text))
    # Chỉ đếm câu có LỜI khác sổ cũ — câu đọc lại vì --redo-tts hay vì đổi mức
    # sáng giọng (đã báo riêng ở trên) không phải "đổi lời".
    doi = sum(1 for i, _f, t in todo
              if i < len(cu) and cu[i] and cu[i] != t
              and (tts_dir / f"{i + 1:04d}.wav").exists())
    if doi:
        print(f"✏️ {doi} câu đã đổi lời so với lần chạy trước → đọc lại đúng mấy câu đó.")
    # Wav thừa của lần cắt câu trước: KHÔNG xoá (mọi thứ xoá được phải khôi phục
    # được), chỉ báo để biết mà dọn tay nếu tiếc chỗ.
    thua = [p for p in tts_dir.glob("[0-9][0-9][0-9][0-9].wav")
            if int(p.stem) > len(cues)]
    if thua:
        print(f"🧺 {len(thua)} wav thừa của lần cắt câu trước còn nằm trong "
              f"{tts_dir.name}/ (không dùng nữa — xoá tay nếu muốn lấy lại chỗ).")
    def _ghi_so(cau):
        so_van_ban.write_text(json.dumps({"sang": sang, "cau": cau}, ensure_ascii=False),
                              encoding="utf-8")
    # Đổi mức sáng giọng thì ghi sổ TRỐNG trước — lỡ đứt giữa chừng, lần sau không
    # tin nhầm đám wav giọng cũ; đọc xong hết mới ghi đủ (cuối hàm).
    _ghi_so([] if doi_sang else moi)

    files = [tts_dir / f"{i + 1:04d}.wav" for i in range(len(cues))]
    if not todo:
        print("♻ Toàn bộ câu đã có audio — bỏ qua bước tạo giọng.")
        return files, None, 0

    print(f"🔊 Giọng mẫu: {voice_path.name}"
          + (f"  ·  🔆 sáng giọng {sang} (EQ mẫu lúc dựng prompt)" if sang else ""))
    model, sr = _load_omnivoice()
    _voice_prompt(model, str(voice_path), sang)   # dựng/nạp prompt 1 lần, xả Whisper ngay

    done_before = len(cues) - len(todo)
    if done_before:
        print(f"♻ {done_before} câu đã có sẵn, còn {len(todo)} câu cần tạo.")
    for n, (i, f, text) in enumerate(todo, 1):
        if not text:
            files[i] = None
            continue
        print(f"  [{n}/{len(todo)}] câu {i + 1}: {text[:50]!r}")
        try:
            sf.write(str(f), _generate_chunk(model, "clone", str(voice_path), text,
                                             sang_giong=sang)[0], sr)
        except Exception as e:
            print(f"  ⚠️ Câu {i + 1} lỗi TTS: {e} — bỏ qua.")
            files[i] = None
    _ghi_so(moi)
    return files, model, sr


# (_load_omnivoice / _tra_vram / _nha_whisper / _do_omnivoice / _voice_prompt / _doc_cau
#  trước đây nằm ở đây, CHÉP từ myvoice. 24/10/2026 gộp về amain_taogiong_gui —
#  xem khối import đầu file: load_omnivoice, _tra_vram, _free_asr, _do_omnivoice,
#  _voice_prompt, _generate_chunk. Khác duy nhất: _generate_chunk vuốt tắt 10 ms
#  cuối câu (FADE_OUT_SEC) như bài thật — chống "cạch" ở mép, không đổi nhịp.)


# ── Kiểm SPIKE ngay sau khi sinh (tái dùng detect_spike của myvoice) ─────────
def kiemtra_spike(cues, files, model, sr, voice_path, sang=0):
    """Lớp kiểm THÔ, y nếp run_tts bên myvoice: quét spike (tiếng lạ TO bất
    thường gấp 5 lần nền / file gần như câm) toàn bộ câu NGAY khi OmniVoice còn
    trên VRAM — câu dính thì re-roll luôn, không tốn lượt nạp lại model. Lớp ASR
    kiemtra_va_docla phía sau mới soi mất chữ + tiếng lạ ngang mức lời nói.
    Trả về model (có thể vừa nạp nếu mọi câu lấy từ cache mà vẫn dính spike)."""
    import soundfile as sf

    if not sr:
        for f in files:
            if f and Path(f).exists():
                sr = sf.info(str(f)).samplerate
                break
        if not sr:
            return model
    bad = []
    for i, f in enumerate(files):
        if not f or not Path(f).exists():
            continue
        try:
            spikes = detect_spike(Path(f), sr)
        except Exception:
            continue
        if spikes:
            bad.append((i, spikes))
    if not bad:
        print("✅ Kiểm spike: không câu nào có tiếng to bất thường.")
        return model
    texts = [tts_text(t) for _t, t in cues]
    print(f"🔊 {len(bad)} câu có spike → đọc lại ngay "
          f"(câu {', '.join(str(i + 1) for i, _s in bad)})...")
    if model is None:
        model, sr = _load_omnivoice()
    _voice_prompt(model, str(voice_path), sang)
    for i, spikes in bad:
        print(f"  câu {i + 1}: spike tại {spikes[:3]}s → đọc lại")
        try:
            sf.write(str(files[i]), _generate_chunk(model, "clone", str(voice_path), texts[i],
                                                    sang_giong=sang)[0], sr)
        except Exception as e:
            print(f"  ⚠️ Câu {i + 1} lỗi khi đọc lại: {e}")
    # Không quét lại vòng nữa — như myvoice: bản re-roll hiếm khi dính tiếp,
    # và lớp ASR phía sau vẫn nghe lại toàn bộ (kể cả các câu vừa đọc lại).
    return model


# ── Kiểm MẤT CHỮ + TIẾNG LẠ, đọc lại câu hỏng (tái dùng taogiong_kiemtra_matchu)
def kiemtra_va_docla(cues, files, tts_dir, voice_path, sang=0):
    """ASR đối chiếu TỪNG câu với văn bản (large-v3-turbo, xem
    taogiong_kiemtra_matchu — bộ kiểm còn soi cả TIẾNG LẠ rè/rít không phải
    giọng đọc). Câu dính cờ được đọc lại ngay: lượt 1 re-roll, lượt 2 nới
    khung +6% (cùng mức myvoice). OmniVoice là masked-diffusion nên thi thoảng nuốt cụm từ — đo
    bên myvoice là 7–12% số đoạn; có vòng này thì mọi video tự được
    "bảo hành đủ chữ".

    VRAM: card 8GB không chứa nổi cả OmniVoice lẫn ASR nên hai model LUÂN PHIÊN
    — bên gọi phải dỡ OmniVoice TRƯỚC khi vào đây (bộ kiểm đo VRAM trống, thấy
    chật là tự lùi về CPU int8, chậm hơn nhiều lần), và ở đây trả VRAM của ASR
    trước mỗi lượt nạp lại OmniVoice để đọc lại câu hỏng."""
    import shutil

    import soundfile as sf
    try:
        import taogiong_kiemtra_matchu as ktm
    except Exception as e:
        print(f"⚠️ Bỏ qua kiểm tra mất chữ + tiếng lạ (không nạp được bộ kiểm: {e})")
        return

    texts = [tts_text(t) for _t, t in cues]
    sr_spike = next((sf.info(str(f)).samplerate for f in files
                     if f and Path(f).exists()), 0)
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
        print(f"🕵️ Kiểm tra mất chữ + tiếng lạ {len(cues)} câu (ASR nghe lại)...")
        bad = ktm.quet_va_xac_minh(texts, shim, on_log=print)
        # Lượt 2 nới khung +6% — cùng mức với run_tts bên myvoice (1.06).
        for lan, scale in ((1, 1.0), (2, 1.06)):
            if not bad:
                break
            print(f"🔁 Lượt đọc lại {lan}: {len(bad)} câu nuốt chữ / có tiếng lạ "
                  f"(câu {', '.join(str(i + 1) for i in sorted(bad))})...")
            # Trả VRAM của ASR RỒI mới nạp OmniVoice — hai model không cùng lúc
            # nằm trên card 8GB được.
            ktm.giai_phong()
            _tra_vram("trả VRAM của ASR để nạp lại OmniVoice")
            model, sr = _load_omnivoice()
            _voice_prompt(model, str(voice_path), sang)
            for i in sorted(bad):
                try:
                    sf.write(str(files[i]),
                             _generate_chunk(model, "clone", str(voice_path), texts[i],
                                             dur_scale=scale, sang_giong=sang)[0], sr)
                    # Như myvoice: bản đọc lại dính spike thì chỉ CẢNH BÁO để
                    # nghe tay — lượt quét ASR kế tiếp vẫn soi lại câu này.
                    spikes = detect_spike(Path(files[i]), sr_spike or sr)
                    if spikes:
                        print(f"  ⚠️ Câu {i + 1} bản đọc lại có spike tại "
                              f"{spikes[:3]}s — nghe kiểm tay.")
                except Exception as e:
                    print(f"  ⚠️ Câu {i + 1} lỗi khi đọc lại: {e}")
            model = _do_omnivoice(model, "quét lại lượt sau")
            _tra_vram()
            _sync(sorted(bad))
            bad = ktm.quet_va_xac_minh(texts, shim, on_log=print,
                                       chi_cac_doan=set(bad))
        if bad:
            print(f"⚠️ Còn {len(bad)} câu lỗi sau 2 lượt đọc lại "
                  f"(câu {', '.join(str(i + 1) for i in sorted(bad))}) — nên nghe lại tay.")
        else:
            print("✅ Kiểm tra mất chữ + tiếng lạ: đạt toàn bộ.")
    finally:
        ktm.giai_phong()
        _tra_vram("xong bước kiểm mất chữ")
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
    # Mang từ myvoice sang (24/10/2026): CÂN MỨC GIỮA CÁC CÂU trước khi đặt lên
    # timeline — mỗi câu sinh riêng một lượt nên to nhỏ lệch nhau (bên myvoice đo
    # chênh tới 11 dB); kéo về cùng mức rồi đặt cả bài vào mốc SPEECH_RMS_DBFS để
    # bộ nén SPEECH_COMPRESSOR ở _loudnorm_file (main) ăn đúng ngưỡng như bài thật.
    co_wav = [s for s in segments if s.get("wav")]
    parts = []
    for s in co_wav:
        data, _ = sf.read(str(s["wav"]), dtype="float32")
        if data.ndim > 1:
            data = data.mean(axis=1)
        parts.append(np.ascontiguousarray(data, dtype="float32"))
    parts = _balance_chunk_levels(parts, sr)
    canvas = np.zeros(int(timeline_end / US * sr) + sr, dtype="float32")
    for s, data in zip(co_wav, parts):
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
                        help="Giọng mẫu: tên file trong myvoice/voice (hoặc kho cũ "
                             "myvideo/voice) hoặc đường dẫn (mặc định: file audio đầu "
                             "tiên tìm thấy).")
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
    # 🎵🔔🧒 mang từ myvoice sang (24/10/2026) — cùng thang, cùng lõi hieuung_giong;
    # mặc định 0 = y như trước. Áp lên audio TỔNG cùng lúc với --sang (main).
    parser.add_argument("--pitch", type=float, default=0.0,
                        help="🎵 Tông giọng (bán cung: + cao, − trầm, 0 = giữ; giữ tốc độ).")
    parser.add_argument("--vang", nargs=2, type=int, metavar=("TRUONG_DO", "CUONG_DO"),
                        default=(0, 0),
                        help="🔔 Tiếng vang: trường độ 0–100, cường độ 0–100 (0 = tắt).")
    parser.add_argument("--thieunien", type=int, default=0,
                        help="🧒 Giọng thiếu niên: cường độ 0–100 (0 = tắt).")
    parser.add_argument("--sang", type=int, default=SANG_MAC_DINH,
                        help="🔆 Sáng giọng 0–100 (0 = tắt): EQ giọng mẫu lúc dựng prompt "
                             f"+ EQ audio tổng — trị giọng clone ồm. Mặc định {SANG_MAC_DINH}.")
    args = parser.parse_args()
    sang = hu.parse_fx(args.sang)

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
            print("❌ Không tìm thấy giọng mẫu nào trong "
                  + " / ".join(str(d) for d in VOICE_DIRS))
            sys.exit(1)
        files, model, _sr = generate_all(cues, voice, tts_dir, redo=args.redo_tts, sang=sang)
        # 1a. Kiểm SPIKE ngay khi model còn trên VRAM (lớp thô, re-roll tại chỗ).
        if not args.no_kiemtra:
            model = kiemtra_spike(cues, files, model, _sr, voice, sang)
        # Dỡ OmniVoice NGAY: bước kiểm chữ cần cả card cho ASR, còn phần xếp
        # timeline + ghép wav bên dưới chạy CPU nên giữ model lại chỉ tổ chiếm chỗ.
        model = _do_omnivoice(model, "TTS xong")
        _tra_vram()
        # 1b. Kiểm mất chữ + đọc lại câu hỏng NGAY (trước khi xếp timeline —
        # câu đọc lại có thể đổi thời lượng nên phải xong xuôi rồi mới xếp).
        if not args.no_kiemtra:
            kiemtra_va_docla(cues, files, tts_dir, voice, sang)

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
        # Y như bài thật bên myvoice (run_tts), trên audio TỔNG: TÔNG GIỌNG + BỘ LỌC
        # (tiếng vang / thiếu niên / sáng giọng) trong MỘT lần ffmpeg trước, rồi nén
        # nhẹ giữa các câu + chuẩn độ to -14 LUFS (SPEECH_COMPRESSOR + loudnorm 2
        # lượt). Không đổi thời lượng (rubberband giữ tốc độ, alimiter bù trễ; chỉ
        # tiếng vang nối thêm đuôi RT60 ở cuối) nên timeline/SRT đã xếp vẫn khớp.
        # Bước ④ vẫn loudnorm lại theo ô tab 🔊 (ttsdb/ttsnorm) như trước.
        fx = hu.fx_from(dict(vang_truong_do=args.vang[0], vang_cuong_do=args.vang[1],
                             thieu_nien=args.thieunien, sang_giong=sang))
        pitch = parse_pitch(args.pitch, 0.0)
        if abs(pitch) > 1e-9 or hu.fx_active(**fx):
            try:
                hu.apply_fx_file(out_wav, pitch=pitch, **fx)
                print(f"🎵 Đã đổi giọng audio tổng: tông {pitch:+.1f} bán cung, "
                      f"bộ lọc: {hu.fx_describe(**fx)} (giữ tốc độ).")
            except Exception as e:
                print(f"⚠️ Không đổi được giọng ({e}) → giữ audio gốc.")
        try:
            _loudnorm_file(out_wav, VOICE_LUFS, pre_filter=SPEECH_COMPRESSOR)
        except Exception as e:
            print(f"⚠️ Không chuẩn được độ to ({e}) → giữ bản chưa chuẩn.")
        print(f"💾 Audio tổng     : {out_wav.name}")

    print("\n✅ Xong. Audio CHƯA gắn vào video — bước gắn làm riêng sau khi nghe thử.")


if __name__ == "__main__":
    main()
