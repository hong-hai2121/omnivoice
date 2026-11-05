# -*- coding: utf-8 -*-
"""
thu_giong.py — Thử nhanh các giọng mẫu trong thư mục voice/giong_mau/.

Chọn 1 giọng (hoặc tạo cho TẤT CẢ), nhập/dùng kịch bản mẫu sẵn rồi tạo audio
clone để NGHE THỬ xem giọng nào hợp. Chức năng giống "tạo giọng" nhưng gọn,
chỉ để so sánh giọng. Kết quả lưu ở voice/_thu_giong/<tên_giọng>.wav.
Khi nghe có thể chỉnh TỐC ĐỘ (giữ cao độ) và TÔNG GIỌNG (cao/trầm theo bán cung,
giữ tốc độ), và từ 20/10/2026 thêm hai BỘ LỌC kiểu CapCut: 🔔 TIẾNG VANG (trường
độ / cường độ) và 🧒 GIỌNG THIẾU NIÊN (cường độ), thang 0–100, 0 = tắt — tất cả
chỉ ảnh hưởng bản phát, file gốc không đổi. Lõi ở scripts/hieuung_giong.py, bài
thật áp đúng bộ lọc đó nên mở app lên là các thanh ở đúng mức bài thật sẽ ra.
Từ 23/10/2026 thêm 🔆 SÁNG GIỌNG (cường độ) trị giọng clone "ồm": bản phát áp
EQ ngay như hai bộ lọc kia, nhưng lúc bấm Tạo nó còn EQ cả GIỌNG MẪU trong bộ
nhớ khi dựng prompt (đúng như bài thật; file mẫu không đổi) nên bản thử mức N
lưu riêng _thu_giong/<tên_giọng>_sang<N>.wav — đổi mức thì bấm Tạo lại để nghe
đúng, kéo thanh sau khi tạo chỉ đổi phần EQ output.
Đường sinh audio đi Y HỆT bài thật (amain_taogiong_gui.run_tts): làm sạch chữ →
chia mỗi đoạn một câu (cỡ "chunk" trong taogiong_options.json) → sinh từng đoạn
→ cân mức to giữa các đoạn → ghép có khoảng nghỉ theo dấu câu → đệm im lặng
cuối → nén nhẹ + chuẩn độ to. Nghe thử ra sao thì bài thật ra vậy.
Từ 01/11/2026 các thanh chỉnh ở đây DÙNG CHUNG thông số với bài thật: tốc độ =
ô "Tăng tốc" video ngang (ngang_speed), tông (pitch) và 4 bộ lọc đọc từ
taogiong_options.json lúc mở, và khi bật 🔗 Đồng bộ (mặc định bật) thì nhả
chuột / bấm ± là ghi ngay vào đúng khoá đó — GUI/web mở lại là thấy, khỏi chép
tay từng số. Tắt 🔗 để thử tự do không đụng bài thật; "↻ Lấy từ bài thật" kéo
các thanh về mức đang lưu.
Từ 02/11/2026 có hàng nút NGHE để đối chiếu clone với người thật: 🎧 GIỌNG MẪU
phát file gốc trong voice/giong_mau/ NGUYÊN BẢN (không qua thanh chỉnh; mp3/wav lạ được đổi
sang wav 16-bit tạm ở _thu_giong/_giongmau/ vì winsound chỉ phát wav PCM),
▶ GIỌNG CLONE phát bản thử theo thanh chỉnh (như trước), ⇄ MẪU → CLONE phát mẫu
xong tự phát tiếp bản clone; ⏹ Dừng cắt cả chuỗi.
Từ 04/11/2026 bấm một mẫu 🎚 MẪU GIỌNG là PHÁT NGAY bản clone của giọng đang chọn
với bộ số của mẫu đó (y như bấm ▶ Giọng clone) — so các mẫu chỉ cần bấm lần lượt,
khỏi bấm thêm nút nghe; chưa có bản thử thì chỉ báo ở Nhật ký, không hộp thoại.
Cùng ngày đổi bố cục sang MENU DỌC bên trái (tỷ lệ màn hình ngang): tab trên
🎙️ OMNIVOICE là toàn bộ màn thử giọng cũ, tab dưới 🗣️ VIENEU-TTS là trang DÙNG THỬ
VieNeu-TTS (kho clone ở voice/VieNeu-TTS, bản 3.8.3) gồm 5 tab con:
  ⚙️ Chuẩn bị & server — cài kho bằng uv sync vào .venv RIÊNG trong kho (GPU: torch cu128
     / CPU: ONNX), bật/tắt API server chuẩn OpenAI của kho (apps.openai_speech, cổng 8000,
     chọn backend/precision), bật Web UI Gradio (cổng 7860, đủ 4 tab gốc) và mở tài liệu.
  🎧 Đọc văn bản — giọng dựng sẵn (25 giọng) hoặc CLONE từ giọng mẫu của mình (đăng ký
     file trong voice/giong_mau/ lên server), tag cảm xúc [cười]…, temperature, max chars;
     xin pcm theo luồng để đo chunk đầu / RTF; kết quả lưu _thu_giong/vieneu/ và phát ngay.
  🎭 Hội thoại — kịch bản "Tên: câu", quét vai, gán giọng từng vai, nghỉ giữa câu, ghép.
  📝 SRT → audio — đọc từng cue, xếp đúng mốc thời gian (tràn thì đẩy cue sau) hoặc nối tiếp.
  📋 Danh mục chức năng — bảng VIENEU_CHUC_NANG (soạn từ README.vi.md, apps/, docs/).
Mọi việc nặng chạy thread nền qua vieneu_client (không import gói vieneu vào venv này);
kết quả về UI qua self.q ("call" / "vnlog" / "vnstatus"). Đóng cửa sổ là tắt server +
Web UI con. Tab đang mở (cả tab con) nhớ giữa các lần chạy.
Cùng ngày gom GIỌNG MẪU (wav/mp3) + .prompt.pt vào voice/giong_mau/ — voice/ chỉ còn
code (file này), kho VieNeu-TTS/ và kết quả thử _thu_giong/. Bài thật (amain VOICE_DIR),
web (core.VOICE_DIR) và myvideo (VOICE_DIRS[0]) cùng trỏ voice/giong_mau/ nên kho vẫn
dùng chung; tên giọng đã lưu trong cài đặt là tên file trần nên không phải đổi gì.

Chạy:  python thu_giong.py   (tự chuyển sang python của venv)
"""

import sys
import os

# ── Tự chuyển sang python của venv (giống các *_gui.py khác) ─────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))                      # myvoice/voice
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, os.pardir, os.pardir))  # OmniVoice (gốc repo)
_VENV_PYTHON = os.path.join(_REPO_ROOT, "venv", "Scripts", "python.exe")
if __name__ == "__main__" and os.path.exists(_VENV_PYTHON) and \
        os.path.normcase(os.path.abspath(sys.executable)) != \
        os.path.normcase(os.path.abspath(_VENV_PYTHON)):
    import subprocess
    subprocess.run([_VENV_PYTHON] + sys.argv)
    sys.exit()
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)   # để import được package omnivoice
_SCRIPTS_DIR = os.path.join(_REPO_ROOT, "myvoice", "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

# Đường sinh audio dùng CHUNG với bản tạo giọng thật — xem _synthesize.
# Import module này KHÔNG mở cửa sổ nào (mainloop nằm trong __main__), và nó
# đặt sẵn PYTORCH_CUDA_ALLOC_CONF trước lần import torch đầu tiên.
import amain_taogiong_gui as tts   # noqa: E402  (phải sau khi vá sys.path)
import hieuung_giong as hu         # noqa: E402  bộ lọc giọng + lõi đổi tông/tốc độ (ffmpeg)
import vieneu_client as vn         # noqa: E402  VieNeu-TTS qua API server của kho (.venv riêng)

import re
import json
import logging
import queue
import shutil
import subprocess
import threading
import time
import traceback
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog

import numpy as np
import soundfile as sf

HERE_DIR = Path(_HERE)                        # myvoice/voice: code (file này) + kho VieNeu-TTS + kết quả thử
VOICE_DIR = HERE_DIR / "giong_mau"            # GIỌNG MẪU (wav/mp3) + .prompt.pt — gom riêng từ 04/11/2026, cùng
                                              # thư mục với amain_taogiong_gui.VOICE_DIR (bài thật, web, myvideo)
OUT_DIR = HERE_DIR / "_thu_giong"             # nơi lưu audio nghe thử
VN_OUT = OUT_DIR / "vieneu"                   # kết quả VieNeu (đọc / hội thoại / SRT)
VIENEU_DIR = HERE_DIR / "VieNeu-TTS"          # kho VieNeu-TTS (git clone, 04/11/2026) — nối qua vieneu_client
SIDEBAR_W = 190                               # bề rộng menu dọc bên trái (px)
# Các tab menu dọc: (khoá nhớ trong settings, chữ trên nút, mô tả nhỏ dưới chữ)
TABS = [("omni", "🎙️  OmniVoice", "thử giọng clone, chỉnh tông & bộ lọc"),
        ("vieneu", "🗣️  VieNeu-TTS", "dùng thử: server · đọc · hội thoại · SRT")]
VOICE_DIR.mkdir(exist_ok=True)                # thiếu thì tạo rỗng cho biết chỗ bỏ giọng mẫu vào
OUT_DIR.mkdir(exist_ok=True)
AUDIO_EXTS = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wma"}
CHUNK_DEFAULT = 160                           # cỡ cắt câu dài khi chưa có taogiong_options.json

# ── NHỚ LỰA CHỌN GIỮA CÁC LẦN CHẠY ──────────────────────────────────────────────
# File nhỏ riêng trong _thu_giong/ chỉ nhớ những gì CỦA RIÊNG app này (giọng đang
# chọn, ô 🔗 Đồng bộ). Thông số giọng (tốc độ / tông / bộ lọc) KHÔNG nằm đây: chúng
# là của bài thật, đọc/ghi thẳng taogiong_options.json (xem bai_that_doc/bai_that_luu;
# tts.save_opt_settings gộp khoá nên không xoá cài đặt khác của GUI/web).
SETTINGS_FILE = OUT_DIR / "thu_giong_settings.json"


def load_settings() -> dict:
    """Cài đặt đã nhớ; chưa có file hoặc file hỏng thì coi như rỗng."""
    try:
        d = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_settings(**kv) -> None:
    """Ghi đè các khoá trong kv, giữ nguyên khoá khác. Lỗi ghi thì bỏ qua —
    không nhớ được lựa chọn không đáng để chặn việc đang làm."""
    try:
        SETTINGS_FILE.write_text(
            json.dumps({**load_settings(), **kv}, ensure_ascii=False, indent=2),
            encoding="utf-8")
    except Exception:
        pass

# ── NGHE THỬ THEO TỐC ĐỘ / TÔNG GIỌNG ──────────────────────────────────────────
# Đổi tốc độ bằng ffmpeg atempo (GIỮ NGUYÊN cao độ, không bị "chipmunk" như cách
# đổi sample rate). Đổi tông giọng theo BÁN CUNG bằng ffmpeg rubberband (GIỮ
# NGUYÊN tốc độ, giữ formant nên vẫn ra "người đó" nói cao/trầm hơn); build
# ffmpeg không có rubberband thì dùng asetrate (kéo cả cao độ lẫn tốc độ) rồi
# atempo bù lại tốc độ. File gốc trong _thu_giong/ KHÔNG bị đụng — bản đã chỉnh
# để riêng ở _thu_giong/_tocdo/, cache theo từng cặp (tốc độ, tông).
FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
SPEED_DIR = OUT_DIR / "_tocdo"
# 🎧 Nghe giọng mẫu (02/11/2026): winsound chỉ phát wav PCM, mà mẫu thường là mp3
# (hoặc wav float) → đổi sang wav 16-bit một lần, cache ở đây theo TÊN ĐẦY ĐỦ
# ("hà chi.mp3" → "hà chi.mp3.wav") để "hà chi.mp3" và "hà chi.wav" không đè nhau.
MAU_DIR = OUT_DIR / "_giongmau"
# Tốc độ = ô "Tăng tốc" video ngang của bài thật (ngang_speed, atempo giữ cao độ, kẹp
# 0,5–2,0 như App._parse_speed bên GUI) — cùng dải để đồng bộ hai chiều không bị kẹp.
SPEED_MIN, SPEED_MAX, SPEED_STEP = 0.5, 2.0, 0.05
PITCH_MIN, PITCH_MAX, PITCH_STEP = tts.PITCH_MIN, tts.PITCH_MAX, 0.5   # bán cung
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Kịch bản mẫu để thử giọng (sửa tay thoải mái) — có câu kể, câu hỏi để nghe ngữ điệu.
DEFAULT_SCRIPT = (
    "Tôi cứ nghĩ, chỉ cần mình quay lưng, anh ấy sẽ chẳng bao giờ giữ lại. "
    "Nhưng ngay khi tôi chạm tay vào cửa, phía sau bỗng vang lên một tiếng gọi gấp gáp. "
    "“Đừng đi!” "
    "Tôi khựng lại, cố giấu đôi mắt đã đỏ hoe. "
    "Anh bước tới, giọng run run: "
    "“Em giận anh cũng được, mắng anh cũng được… "
    "nhưng đừng biến mất khỏi cuộc đời anh thêm lần nào nữa.”"
)

DEFAULT_HOI_THOAI = (
    "Lan: Anh về rồi à? Em tưởng tối nay anh bận lắm. [cười]\n"
    "Minh: Bận thì bận, nhưng hôm nay anh muốn ăn cơm nhà.\n"
    "Lan: Vậy ngồi đi, em dọn lên ngay.\n"
    "Minh: Ừ, có thêm món gì không? [hắng giọng] Anh đói lắm rồi.\n"
)

UI = dict(
    bg="#ffffff", fg="#1f2430", muted="#7b828f",
    accent="#e84393", accent_dk="#c92f7b",
    field="#ffffff", border="#e4e7ec", hover="#f1f3f6",
    log_bg="#fbfbfc", log_info="#475063", log_warn="#b07400", log_err="#d62828", ok="#1f9d55",
    # menu dọc bên trái (04/11/2026): nền tối, tab đang mở tô màu nhấn
    side_bg="#1f2430", side_fg="#d6dbe6", side_muted="#8b93a3", side_hover="#2b3140",
    side_active="#e84393", side_active_fg="#ffffff",
)



def list_voices():
    """Danh sách file giọng mẫu trong thư mục (bỏ qua thư mục con _thu_giong)."""
    if not VOICE_DIR.exists():
        return []
    return sorted(f.name for f in VOICE_DIR.iterdir()
                  if f.is_file() and f.suffix.lower() in AUDIO_EXTS)


def chunk_size() -> int:
    """Cỡ cắt câu dài (ô "chunk" mục Cài đặt) — đọc từ taogiong_options.json của
    bản tạo giọng thật để chia đoạn y hệt bên đó; chưa có/lỗi thì CHUNK_DEFAULT."""
    try:
        return int(tts.load_opt_settings().get("chunk") or CHUNK_DEFAULT)
    except Exception:
        return CHUNK_DEFAULT


def split_chunks(text, max_len=None):
    """Tách đoạn y hệt bản tạo giọng thật (tts.split_chunks: mỗi đoạn MỘT câu, câu
    dài hơn `max_len` thì cắt thêm ở ; : ,) — nghe thử mà chia đoạn khác thì chỗ
    ngắt và nhịp đọc đã khác, so sánh giọng thành vô nghĩa.
    Thêm lưới: văn bản không có dấu câu nào thì lấy nguyên cả bài làm 1 đoạn."""
    return tts.split_chunks(text, max_len or chunk_size()) or [text.strip()]


def safe_stem(name: str) -> str:
    """Bỏ phần đuôi + ký tự không hợp lệ để đặt tên file kết quả."""
    return re.sub(r"[^\w\-. ]+", "_", Path(name).stem).strip() or "giong"


def out_file(voice: str, sang: int = 0) -> Path:
    """File nghe thử của một giọng. Mức 🔆 Sáng giọng > 0 thì giọng MẪU đã được EQ
    lúc dựng prompt → bản thử khác hẳn bản mức 0, lưu riêng `<giọng>_sang<N>.wav`
    (mức 0 giữ tên cũ `<giọng>.wav` nên bản thử đã có vẫn dùng được)."""
    sang = hu.parse_fx(sang)
    return OUT_DIR / f"{safe_stem(voice)}{f'_sang{sang}' if sang else ''}.wav"


def mau_wav_file(voice: str) -> Path:
    """Bản wav 16-bit để winsound phát được của giọng MẪU `voice` (tên file trong
    voice/giong_mau/). Giữ nguyên tên gốc kèm đuôi rồi thêm .wav — xem MAU_DIR."""
    return MAU_DIR / f"{Path(voice).name}.wav"


# ── đổi tốc độ / tông / bộ lọc bằng ffmpeg ─────────────────────────────────────
# Lõi (rubberband giữ formant, dự phòng asetrate+atempo; tiếng vang bằng afir +
# đáp ứng xung tự sinh; thiếu niên = dời formant + nhỉnh cao độ) nằm ở
# scripts/hieuung_giong.py — bài thật (amain_taogiong_gui.run_tts) cũng áp đúng
# bộ lọc đó lên output.wav (tuỳ chọn "pitch" + 4 khoá bộ lọc). Ở đây chỉ dùng
# lại hu.build_ffmpeg_args, không chép.


def fmt_pitch(semitones: float) -> str:
    """'+2.0', '-1.5', còn 0 thì '0.0' (không ra '+0.0' hay '-0.0')."""
    return f"{semitones:+.1f}" if abs(semitones) > 1e-9 else "0.0"


def default_pitch() -> float:
    """Tông mặc định = tuỳ chọn "pitch" của bài thật (taogiong_options.json) —
    mở app lên là nghe đúng tông mà bài thật sẽ ra; kéo về 0 để nghe giọng gốc."""
    try:
        return tts.parse_pitch(tts.load_opt_settings().get("pitch"), 0.0)
    except Exception:
        return 0.0


def default_fx() -> dict:
    """Bộ lọc mặc định = 4 khoá bộ lọc của bài thật (taogiong_options.json) —
    mở app lên là nghe đúng bộ lọc bài thật sẽ ra; kéo về 0 để tắt."""
    try:
        return hu.fx_from(tts.load_opt_settings())
    except Exception:
        return hu.fx_from(None)


def parse_speed(value, default: float = 1.0) -> float:
    """Đọc tốc độ ("1.2", "1,15", 1.2) → float kẹp [SPEED_MIN, SPEED_MAX], làm tròn
    về bội SPEED_STEP — cùng cách đọc với ô Tăng tốc bên GUI/web."""
    try:
        v = float(str(value).replace(",", ".").strip())
    except (TypeError, ValueError):
        v = default
    v = round(v / SPEED_STEP) * SPEED_STEP
    return round(max(SPEED_MIN, min(v, SPEED_MAX)), 2)


def default_speed() -> float:
    """Tốc độ mặc định = ô "Tăng tốc" video ngang của bài thật (ngang_speed) — mở app
    lên là nghe đúng nhịp mà video ngang sẽ ra; kéo về 1.0 để nghe tốc độ gốc."""
    try:
        return parse_speed(tts.load_opt_settings().get("ngang_speed"), 1.0)
    except Exception:
        return 1.0


# ── DÙNG CHUNG THÔNG SỐ GIỌNG VỚI BÀI THẬT (01/11/2026) ─────────────────────────
# Ba nhóm thanh chỉnh ở đây ↔ đúng khoá GUI/web dùng trong taogiong_options.json:
#   tốc độ nghe  ↔ ngang_speed (ô "Tăng tốc" video ngang, chuỗi "1.2")
#   tông giọng   ↔ pitch (float bán cung)
#   4 bộ lọc     ↔ vang_truong_do / vang_cuong_do / thieu_nien / sang_giong (int 0–100)
def bai_that_doc() -> dict:
    """Thông số giọng bài thật đang lưu → {"speed", "pitch", "fx"} (đã kẹp)."""
    return dict(speed=default_speed(), pitch=default_pitch(), fx=default_fx())


def bai_that_luu(speed: float, pitch: float, fx: dict | None) -> None:
    """Ghi thông số giọng vào taogiong_options.json đúng khoá GUI/web đọc; các khoá
    khác giữ nguyên (tts.save_opt_settings gộp dict)."""
    tts.save_opt_settings(dict(ngang_speed=f"{parse_speed(speed):g}",
                               pitch=tts.parse_pitch(pitch, 0.0),
                               **hu.fx_from(fx)))


def mo_ta_thong_so(speed: float, pitch: float, fx: dict | None) -> str:
    """'1.20×, tông +1.0, bộ lọc sáng giọng 80' — dòng trạng thái đồng bộ."""
    return f"{speed:.2f}×, tông {fmt_pitch(pitch)}, bộ lọc {hu.fx_describe(**hu.fx_from(fx))}"


# ── 🗣️ VIENEU-TTS: DANH MỤC ĐỦ CHỨC NĂNG (04/11/2026) ─────────────────────────
# Soạn từ README.vi.md, config.yaml, apps/*.py, finetune/README.md, docs/ của kho đã
# clone ở VIENEU_DIR (gói vieneu 3.8.3). Hiển thị ở tab con 📋 Danh mục; dùng thử thì ở
# các tab con ⚙️ 🎧 🎭 📝 bên cạnh (qua vieneu_client — API server của kho).
# Mỗi nhóm: (tên, tóm tắt một dòng, các dòng chi tiết). Dòng bắt đầu bằng "→" là ghi
# chú liên hệ với app mình (tô màu nhấn), còn lại là gạch đầu dòng.
VIENEU_CHUC_NANG: list[tuple[str, str, list[str]]] = [
    ("🧠 Mô hình (backbone) & chất lượng",
     "v3 Turbo là bản mặc định/hiện hành; Nano cho máy yếu; v1/v2 đã ngừng; v4 không mở mã.",
     ["VieNeu-TTS-v3-Turbo (mặc định): 48 kHz, song ngữ Việt–Anh, huấn luyện từ đầu trên 10.000+ giờ; "
      "CPU chạy bằng ONNX Runtime KHÔNG cần torch (fp32 RTF ≈ 0,55–0,62; precision=\"int8\" RTF ≈ 0,35 "
      "nhưng cần CPU có VNNI), GPU CUDA chạy PyTorch (RTF ≈ 0,02 khi batch, nhanh hơn CPU ~25–50 lần).",
      "VieNeu-TTS-v3-Nano (preview): 24 kHz, flow-matching 48M tham số cho CPU yếu / điện thoại / board ARM; "
      "11 giọng + clone; nhanh gấp ~3 Turbo (RTF 0,11–0,22) nhưng chất lượng thấp hơn rõ, nhất là tiếng Anh. "
      "Tham số riêng: steps (16; 8 nhanh gấp đôi), sway, cfg (3.0), speed, seed, threads.",
      "VieNeu-TTS-v2 / v2-CPU (GGUF) / v2-Turbo / v1: đã ngừng cập nhật, chỉ giữ cho hệ đang chạy "
      "(v2 có chế độ Podcast, server LMDeploy). Trong config.yaml của Web UI vẫn chọn được v2, v1 (GPU).",
      "Sắp ra: v3 bản đầy đủ (GPU, server). v4 (clone gần nguyên bản) chỉ có qua API/vieneu.io, không mã nguồn mở.",
      "Codec: MOSS-Audio-Tokenizer-Nano (v3), NeuCodec Distill / VieNeu-Codec (v1, v2). Phiên âm: sea-g2p (Rust). "
      "Tuỳ chọn đóng dấu nước Resemble Perth (pip install vieneu[watermark]; apply_watermark=True mặc định khi có).",
      "→ OmniVoice của mình: 24 kHz, clone từ mẫu + prompt Whisper. VieNeu Turbo ra 48 kHz, không cần phiên âm mẫu."]),
    ("🎙️ Giọng dựng sẵn (preset) — không cần clip mẫu",
     "25 giọng v3 Turbo phủ 3 miền, 10 giọng tuyển chọn; 11 giọng v3 Nano.",
     ["10 giọng tuyển chọn (ổn định, tự nhiên nhất): Adam bựa, Trúc Ly, Thiện Minh, Mai Anh, Hải Đăng (mặc định), "
      "Thùy Dung, Thiền Tâm Đức, Ngọc Huyền, Quang Sơn, Ngọc Trân.",
      "Miền Bắc: Minh Đức, Phạm Tuyên, Xuân Vĩnh, Thanh Bình, Ngọc Linh, Đoan Trang, Quỳnh Anh, Quốc Tuấn. "
      "Miền Trung: Quang Sơn, Ngọc Trân. Miền Nam: Adam, Thái Sơn, Thục Đoan, Minh Triết, Mỹ Duyên, Đức Trí, "
      "Kim Thanh (+ Thùy Dung).",
      "v3 Nano: Adam, Ái Hân, Mỹ Duyên, Đức Trí, Hữu Quân, Xuân Tiên, Mai Anh, Trúc Ly, Anh Khôi, Minh Quân, Mạnh Dũng.",
      "SDK: list_preset_voices() (đúng thứ tự trên), get_preset_voice(tên), infer(text, voice=\"Hải Đăng\"). "
      "Phong cách đọc đi theo giọng mẫu — tham số style (tin_tuc, doc_truyen…) đã BỎ, truyền vào bị bỏ qua.",
      "Quy chuẩn voices.json (vieneu.voice.presets v1.0) để đóng gói giọng dùng lại; giọng tự lưu nằm "
      "~/.vieneu/user_voices_v3_turbo.json (VIENEU_HOME đổi chỗ) và hiện trong mọi ô chọn giọng."]),
    ("🎤 Clone giọng tức thì (zero-shot)",
     "Clip 3–8 giây là đủ, tự khử nhiễu, v3 không cần gõ nội dung clip; chạy cả trên CPU không torch.",
     ["infer(text, ref_audio=\"clip.wav\", denoise=True): clip dài hơn 8 s tự cắt, khử nhiễu nền + chuẩn hoá trước "
      "khi clone (đặt denoise=False nếu clip đã sạch). v2 GPU mới cần ref_text; v3 chỉ cần audio.",
      "add_voice(tên, clip) đăng ký một lần rồi gọi theo tên như preset (dùng được cả trong Hội thoại); save_voices() "
      "giữ lại cho lần sau; remove_voice(); encode_reference(clip) lấy (speaker embedding, codes).",
      "denoise(clip, out_path=…) chỉ khử nhiễu, trả wav 44,1 kHz mono — để nghe/lưu bản sạch.",
      "Web UI tab 🎤 Voice Cloning: tải clip (.wav 3–5 s), ô 🔇 Denoise, ô văn bản đọc thử, 💾 Lưu giọng (tên + mô tả) "
      "vào kho giọng người dùng, 🗑️ Xoá; ví dụ mẫu sẵn trong examples/audio_ref/ (có example_ngoc_huyen.wav).",
      "Toàn bộ pipeline clone chạy bằng onnxruntime + soxr + kaldi-native-fbank → bản cài CPU cũng clone được.",
      "→ Chỗ nối với kho giọng của mình (voice/giong_mau/): cùng clip mẫu, VieNeu chỉ cần add_voice, không cần .prompt.pt."]),
    ("📖 Đọc truyện / văn bản dài (Web UI tab 🦜 Đọc truyện)",
     "Dán chữ hoặc tải PDF, tự chia đoạn, sinh từng đoạn (GPU gộp lô), nghe + tải kết quả.",
     ["Ô văn bản nhiều dòng; 📄 tải PDF → trích xuất chữ tự điền (cần pip install vieneu[pdf] = PyMuPDF), sửa trước khi tạo.",
      "Chọn giọng (preset hoặc giọng đã lưu), chế độ sinh Standard; ⚙️ nâng cao: 🌡️ Temperature (≈0,8 ổn định nhất), "
      "📝 Max Chars per Chunk (mặc định 256; text_settings trong config.yaml).",
      "⚡ Batch Processing + 📊 Batch Size (tới 32): gộp nhiều đoạn vào một lần forward — v3 Turbo cần GPU CUDA; "
      "trên CPU/ONNX ô này không tác dụng. ⏹️ Dừng giữa chừng, ô Trạng thái, Ước tính thời gian, nút tải về.",
      "SDK tương ứng: một infer() cho văn bản dài tự chia chunk và tự batch trên GPU; chunk theo max_chars."]),
    ("🎭 Hội thoại nhiều người nói (Podcast / Conversation)",
     "Kịch bản dạng \"Tên: câu nói\", gán giọng riêng từng nhân vật, batch cả kịch bản bất kể người nói.",
     ["Web UI tab 🎭 Hội thoại: dán kịch bản, 🔍 Quét nhân vật → mỗi tên một ô chọn giọng (preset hoặc giọng đã lưu), "
      "⏱️ Khoảng lặng giữa câu 0–3 s (mặc định 0,3), 🎭 Bắt đầu hội thoại. Tab hiện khi backbone hỗ trợ (v3, v2).",
      "SDK: infer_batch(texts, voice=…) — v3 gom các chunk của mọi câu vào chung từng bước forward trên GPU "
      "(RTF ≈ 0,011–0,02); CPU vẫn chạy được nhưng tuần tự.",
      "→ Tương đương kiểu \"đọc kịch bản nhiều vai\"; OmniVoice bên mình hiện một giọng cho cả bài."]),
    ("📝 SRT → audio (apps/srt_speech.py, Web UI tab 📝 SRT)",
     "Đọc phụ đề tiếng Việt từng cue bằng một giọng, xếp đúng mốc thời gian, xuất wav/mp3.",
     ["Nhận file .srt tiếng Việt + giọng mẫu; mỗi cue bắt đầu đúng giờ SRT, câu đọc tràn sang cue sau thì ĐẨY cue sau "
      "lùi lại (báo số cue bị dời) — không co giãn giọng nên luôn tự nhiên; hoặc bỏ giữ giờ để đọc nối tiếp.",
      "Định dạng xuất wav / mp3. Không dịch, không ghép video, không vẽ sub (app chính thức mới có Dubbing).",
      "→ Việc này myvideo đang làm bằng OmniVoice (taogiong_srt.py: TTS từng câu + xếp timeline chống đè + xoá tiếng gốc)."]),
    ("😄 Tag cảm xúc / phi ngôn từ (thử nghiệm)",
     "Chèn thẳng vào chữ, Turbo và Nano đều hiểu.",
     ["[cười], [thở dài], [hắng giọng] đặt ngay trong văn bản: \"Nghe hay quá đi [cười]. Để mình nói tiếp [hắng giọng].\"",
      "Temperature ≈ 0,8 cho kết quả ổn định nhất; là tính năng thử nghiệm nên có lúc bỏ qua tag."]),
    ("⚡ Sinh theo lô & tốc độ",
     "infer_batch nhiều câu một lần forward; GPU dùng CUDA graph gộp mỗi khung, không cần torch.compile.",
     ["infer_batch(texts, batch_size=…) tối đa max_batch_size (32, đặt được 64; batch_size=1 tắt); một infer() văn bản "
      "dài cũng tự batch các chunk.",
      "Số đo (RTX 3060 + i5 gen 12): GPU batch RTF 0,011–0,02 (30 câu / 130 s audio trong 1,5–2,3 s), GPU một câu 0,10; "
      "CPU Turbo fp32 0,55–0,62 (nạp ~19 s), int8 0,35 (nạp ~14 s); Nano 0,22 / 0,11 (nạp ~3 s).",
      "Mỗi khung âm thanh là một CUDA graph (acoustic + sampling + phạt lặp + backbone); lần đầu mỗi cỡ batch +~0,5 s "
      "để capture; VIENEU_FUSED_FRAME=0 quay về vòng lặp thường."]),
    ("🔊 Streaming thời gian thực",
     "Audio ra theo từng frame: GPU chunk đầu ~115 ms và 16 luồng đồng thời; CPU cũng stream được.",
     ["infer_stream(text, voice=…) trả từng mảng np.float32 48 kHz để phát/ghi ngay; gọi từ nhiều thread = nhiều người "
      "nghe; Vieneu(max_streams=16) đặt trần (tối đa 32, 32 luồng RTF 0,93 vẫn real-time nhưng hết biên).",
      "GPU: TTFA ~115 ms một luồng, ~185 ms khi 16 luồng cùng lúc, ~134 ms cho request mới chen vào; VRAM ~1,1 GB đỉnh. "
      "CPU fp32: 1 luồng, 260–400 ms; int8: 2 luồng, 140–195 ms. Nano không stream theo frame (trả chunk hoàn chỉnh).",
      "Demo trình duyệt cũ: apps/web_stream.py (FastAPI, http://127.0.0.1:8001, client/client.html)."]),
    ("🌐 API server chuẩn OpenAI (apps/openai_speech.py)",
     "POST /v1/audio/speech thay thẳng cho OpenAI TTS — đổi base_url là OpenAI SDK, Pipecat, LiveKit, Vercel AI dùng được.",
     ["Chạy: uv run python -m apps.openai_speech → http://localhost:8000 (tự nhận GPU/CPU; VIENEU_BACKEND=onnx ép CPU; "
      "VIENEU_MAX_STREAMS đặt số luồng, mặc định 16 GPU / 1 CPU; quá tải → 429, có hàng đợi nhỏ).",
      "Endpoint: POST /v1/audio/speech (response_format pcm s16le 48 kHz hoặc wav; body chunked hoặc SSE), GET /v1/models, "
      "GET /v1/voices, POST /v1/voices (clone giọng từ clip upload, không đè tên giọng có sẵn → 409), GET /health.",
      "examples/openai_speech_client.py --bench 8 tự đo TTFA / RTF trên máy mình; docs/streaming.vi.md có đủ số đo và cách "
      "chọn max_streams theo số người dùng (16 luồng ≈ 45–80 người dùng chatbot thoại).",
      "→ Nếu nối VieNeu vào myvoice/myvideo theo kiểu dịch vụ, đây là cửa gọn nhất: bật server, app gọi HTTP, không đụng venv."]),
    ("🐳 Docker & triển khai",
     "Compose sẵn 4 profile; image CPU không torch; server LMDeploy v2 cũ đã ngừng.",
     ["docker compose -f docker/docker-compose.yml --profile api-gpu | api-cpu up → API streaming :8000; "
      "--profile gpu | cpu → Web UI Gradio :7860. Dockerfile.cpu / .gpu / .serve; docker-compose.build.yml, .prod.yml; "
      "hướng dẫn build production ở docs/Deploy.vi.md.",
      "Cũ (đã ngừng): docker run pnnbao/vieneu-tts:latest --tunnel (LMDeploy, cổng 23333, đường hầm bore) + SDK "
      "Vieneu(mode=\"remote\", api_base=…) cho v2 — pip install vieneu[legacy]; model 0.3B nhanh hơn qua image :serve."]),
    ("🎓 Fine-tune LoRA (finetune/)",
     "Dạy v3 Turbo một giọng / một phong cách đọc trên GPU phổ thông (~6 GB VRAM), rồi dùng như preset.",
     ["uv sync --extra finetune (torch, transformers, peft, accelerate). Dữ liệu: metadata.csv (file_name|text) + raw_audio/, "
      "mọi clip CÙNG MỘT người nói, 3–15 s, sạch, nội dung đúng chữ kể cả dấu câu.",
      "prepare_dataset.py (CPU, không torch: phiên âm sea-g2p + mã hoá codec MOSS + speaker embedding 192 chiều → "
      "train.parquet) → train_lora.py (rank 16, lr 2e-4, 3 epoch, bf16; --r/--alpha, --target all, --grad-checkpoint, "
      "--merge) → merge_lora.py (có --push-to-hub) → make_voice.py đóng gói giọng vào model đã merge.",
      "Dùng: Vieneu(mode=\"v3turbo\", backbone_repo=\"finetune/output/my_voice/merged\") rồi infer(voice=\"Giọng của tôi\") "
      "— không cần audio mẫu, giữ đủ preset/batch/streaming trên PyTorch GPU; mỗi giọng một LoRA riêng.",
      "Web UI: Backbone \"Custom Model\" nhập HF repo / đường dẫn local, HF token (repo private), Base Model cho LoRA; "
      "docs/CUSTOM_MODEL_USAGE.md (LoRA + LMDeploy, GGUF trên CPU, full finetune) cho dòng v1/v2."]),
    ("🖥️ Web UI Gradio (apps/gradio_main.py — lệnh vieneu-web / make demo, :7860)",
     "Một trang: chọn model → 4 tab làm việc → ô kết quả; có bản Intel XPU riêng.",
     ["Khối model: 🦜 Backbone (v3 Turbo, v3 Nano, v2 GPU, v1 GPU, Custom Model), 🎵 Codec, 🖥️ Device (Auto/CPU/CUDA…), "
      "🚀 Optimize with LMDeploy (v1/v2 trên GPU NVIDIA), 🔄 Tải Model + dòng trạng thái.",
      "4 tab: 🦜 Đọc truyện · 🎭 Hội thoại · 📝 SRT · 🎤 Voice Cloning (ẩn/hiện theo backbone có hỗ trợ); dưới là ⚡ Batch, "
      "⚙️ Cài đặt nâng cao (Temperature, Max Chars), ⏹️ Dừng; cột phải: 🎧 Kết quả, Trạng thái, Ước tính thời gian, Tải về.",
      "apps/gradio_xpu.py + run_xpu.bat / setup_xpu_uv.bat: bản chạy GPU Intel (XPU). apps/ui_constants.py, ui_utils.py: "
      "chữ/giao diện; apps/user_voices.py: kho giọng người dùng đã lưu.",
      "Windows có bộ cài độc lập ở vieneu.io/#/download (app chính thức, không phải kho mã này)."]),
    ("📦 Cài đặt, SDK & công cụ đi kèm",
     "uv là đường chính; pip install vieneu cũng được; Makefile gói sẵn mọi lệnh.",
     ["uv sync (CPU, không torch, Python ≥ 3.10) · uv sync --extra cuda (GPU: torch 2.8.0 cu128 + transformers) · "
      "--extra finetune · --group dev (pytest). pip: vieneu, vieneu[cuda], vieneu[pdf], vieneu[watermark], vieneu[legacy]. "
      "Windows GPU: cài torch cu128 + transformers 4.57.6 TRƯỚC rồi pip install vieneu.",
      "SDK một lớp Vieneu(mode=v3turbo|v3nano|remote…, backend=auto|onnx|torch, precision=fp32|int8, max_streams, "
      "backbone_repo…): infer / infer_batch / infer_stream / save / list_preset_voices / get_preset_voice / add_voice / "
      "remove_voice / save_voices / encode_reference / denoise / close.",
      "Makefile: setup, setup-cpu, setup-gpu, setup-finetune, demo (= run, Web UI), stream (web_stream), docker-cpu/gpu, "
      "docker-build-*, check (pytest), clean. examples/: main.py, main_v3turbo.py, main_v3nano.py, main_remote.py, "
      "openai_speech_client.py, audio_ref/ (4 clip + text), srt/sample_vi.srt. tests/: pytest theo engine.",
      "Giấy phép Apache 2.0. Model trên Hugging Face pnnbao-ump/VieNeu-TTS-v3-Turbo (và v2, v1); Colab demo; Discord."]),
    ("🚫 Không có trong kho mở này / đã bỏ",
     "Biết trước để không đi tìm.",
     ["Dubbing (lồng tiếng video), Lecture, TikTok Reel, Audiobook: chỉ trong app VieNeu chính thức (vieneu.io). "
      "v4 (clone gần nguyên bản) độc quyền qua API.",
      "style (phong cách đọc) đã bỏ; server LMDeploy + mode remote chỉ cho v2 đã ngừng; v3 Nano không stream theo frame.",
      "Lộ trình chưa xong: v3 đầy đủ (GPU server, điều khiển cảm xúc ổn định, thêm giọng), Mobile SDK Android/iOS."]),
]
VIENEU_GHI_CHU = ("Nguồn: README.vi.md, config.yaml, apps/gradio_main.py, apps/openai_speech.py, apps/srt_speech.py, "
                  "apps/web_stream.py, apps/user_voices.py, finetune/README.md, docs/streaming.vi.md, "
                  "docs/CUSTOM_MODEL_USAGE.md, pyproject.toml, Makefile của kho (vieneu 3.8.3, clone 04/11/2026). "
                  "Số đo tốc độ là của tác giả trên RTX 3060 + Core i5 gen 12.")


vieneu_trang_thai = vn.trang_thai     # kho đã clone/cài chưa, bản nào — xem vieneu_client


class _LogTap(logging.Handler):
    """Đưa logging.info/warning của các hàm DÙNG CHUNG với bài thật (nạp model,
    dựng prompt, cân mức, chuẩn độ to, trả VRAM — amain_taogiong_gui) vào ô Nhật
    ký của app: nghe thử thấy đủ diễn biến y như bài thật."""

    def __init__(self, q):
        super().__init__(logging.INFO)
        self._q = q

    def emit(self, record):
        try:
            lv = ("err" if record.levelno >= logging.ERROR
                  else "warn" if record.levelno >= logging.WARNING else "info")
            self._q.put(("log", (lv, record.getMessage())))
        except Exception:
            pass


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("Thử giọng — OmniVoice · VieNeu-TTS")
        root.configure(bg=UI["bg"])
        # 04/11/2026: +SIDEBAR_W cho menu dọc bên trái, rộng thêm 150 để lộ các dòng
        # gợi ý bên phải — tỷ lệ ngang hợp màn hình rộng (_center tự kẹp theo màn hình).
        self._center(root, 1100 + SIDEBAR_W + 150, 830)
        root.minsize(900 + SIDEBAR_W, 730)

        self._busy = False
        self._playing = False
        self._last_src = None       # file wav GỐC vừa phát (để đổi tốc độ phát lại)
        self._last_raw = False      # True = vừa phát GIỌNG MẪU nguyên bản → kéo thanh không phát lại
        self._play_until = 0.0      # mốc thời gian dự kiến phát xong (winsound không báo)
        self._ab_token = 0          # ⇄ mẫu → clone: đổi số là huỷ lượt phát clone đang hẹn
        self._model = None          # nạp 1 lần, dùng lại
        self._sr = None
        self.q = queue.Queue()      # (kind, payload) từ thread nền
        logging.getLogger().addHandler(_LogTap(self.q))   # log hàm dùng chung → Nhật ký
        logging.getLogger().setLevel(logging.INFO)

        self._build_styles()
        self._build_ui()
        self._reload_voices()
        self.root.after(120, self._poll)

    # ── tiện ích ──
    def _center(self, root, w, h):
        """Đặt cỡ w×h giữa màn hình; màn nhỏ hơn thì kẹp lại cho vừa (chừa viền/thanh tiêu đề)."""
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        w, h = min(w, sw - 40), min(h, sh - 40)
        root.geometry(f"{w}x{h}+{max((sw - w)//2, 0)}+{max((sh - h)//3, 0)}")

    def _build_styles(self):
        st = ttk.Style()
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        C = UI
        st.configure("TFrame", background=C["bg"])
        st.configure("TLabel", background=C["bg"], foreground=C["fg"], font=("Segoe UI", 10))
        st.configure("Title.TLabel", background=C["bg"], foreground=C["accent_dk"],
                     font=("Segoe UI Semibold", 16))
        st.configure("Muted.TLabel", background=C["bg"], foreground=C["muted"], font=("Segoe UI", 9))
        st.configure("TButton", padding=(12, 7), font=("Segoe UI", 10))
        st.configure("Accent.TButton", foreground="#ffffff", background=C["accent"],
                     padding=(16, 9), font=("Segoe UI", 10, "bold"))
        st.map("Accent.TButton", background=[("active", C["accent_dk"]), ("disabled", "#f0a8c6")])
        st.configure("TCheckbutton", background=C["bg"], foreground=C["fg"], font=("Segoe UI", 10))
        st.map("TCheckbutton", background=[("active", C["bg"])],
               foreground=[("selected", C["accent_dk"])],
               indicatorcolor=[("selected", C["accent"]), ("!selected", "#cfd3da")])

    def _build_ui(self):
        """Khung chung (04/11/2026): MENU DỌC bên trái (cột 0, bề rộng cố định) + vùng
        nội dung (cột 1, co giãn) chứa các trang xếp chồng cùng một ô lưới; bấm tab
        là tkraise trang đó. Trang OmniVoice = toàn bộ màn thử giọng cũ."""
        self.root.columnconfigure(0, weight=0)
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)

        # ── menu dọc ──
        side = tk.Frame(self.root, bg=UI["side_bg"], width=SIDEBAR_W)
        side.grid(row=0, column=0, sticky="ns")
        side.grid_propagate(False)          # giữ đúng bề rộng, không co theo chữ
        tk.Label(side, text="🎚️  Thử giọng", bg=UI["side_bg"], fg="#ffffff",
                 font=("Segoe UI Semibold", 15)).pack(anchor="w", padx=18, pady=(22, 0))
        tk.Label(side, text="so giọng mẫu ↔ clone", bg=UI["side_bg"], fg=UI["side_muted"],
                 font=("Segoe UI", 9)).pack(anchor="w", padx=18, pady=(0, 18))
        self._tab_btns: dict[str, tk.Label] = {}
        for key, ten, mo_ta in TABS:
            self._tab_btns[key] = self._tab_btn(side, key, ten, mo_ta)
        tk.Label(side, text="giọng mẫu: voice/giong_mau/", bg=UI["side_bg"],
                 fg=UI["side_muted"], font=("Segoe UI", 8)).pack(side="bottom", anchor="w",
                                                                   padx=18, pady=(0, 14))

        # ── vùng nội dung: các trang chồng lên nhau ──
        holder = ttk.Frame(self.root)
        holder.grid(row=0, column=1, sticky="nsew")
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)
        self._pages = {"omni": self._build_omni_page(holder),
                       "vieneu": self._build_vieneu_page(holder)}
        for p in self._pages.values():
            p.grid(row=0, column=0, sticky="nsew")
        self._tab = None
        self._chon_tab(load_settings().get("tab") or "omni", luu=False)

    def _tab_btn(self, side: tk.Frame, key: str, ten: str, mo_ta: str) -> tk.Label:
        """Một tab trên menu dọc: nhãn 2 dòng (tên + mô tả nhỏ), bấm là mở trang `key`;
        rê chuột đổi nền nhẹ khi chưa phải tab đang mở."""
        lb = tk.Label(side, text=f"{ten}\n{mo_ta}", bg=UI["side_bg"], fg=UI["side_fg"],
                      font=("Segoe UI", 10), justify="left", anchor="w", cursor="hand2",
                      padx=18, pady=10, wraplength=SIDEBAR_W - 36)
        lb.pack(fill="x")
        lb.bind("<Button-1>", lambda _e, k=key: self._chon_tab(k))
        lb.bind("<Enter>", lambda _e, k=key: self._tab_hover(k, True))
        lb.bind("<Leave>", lambda _e, k=key: self._tab_hover(k, False))
        return lb

    def _tab_hover(self, key: str, vao: bool):
        if key == self._tab:
            return
        self._tab_btns[key].config(bg=UI["side_hover"] if vao else UI["side_bg"])

    def _chon_tab(self, key: str, luu: bool = True):
        """Mở trang `key`: tô tab đang mở, đưa trang lên trên, nhớ vào settings (lần sau
        mở đúng tab này). Khoá lạ (settings cũ) → về OmniVoice."""
        if key not in self._pages:
            key = "omni"
        self._tab = key
        for k, lb in self._tab_btns.items():
            if k == key:
                lb.config(bg=UI["side_active"], fg=UI["side_active_fg"])
            else:
                lb.config(bg=UI["side_bg"], fg=UI["side_fg"])
        self._pages[key].tkraise()
        if luu:
            save_settings(tab=key)

    # ── 🗣️ VieNeu-TTS: DÙNG THỬ qua API server của kho (04/11/2026) ────────────────
    def _build_vieneu_page(self, parent) -> ttk.Frame:
        """Trang VieNeu-TTS: tiêu đề, Notebook 5 tab con (⚙️ chuẩn bị & server · 🎧 đọc văn
        bản · 🎭 hội thoại · 📝 SRT · 📋 danh mục), dưới cùng là dòng trạng thái + Nhật ký
        riêng (log server/cài đặt/kết quả). Việc nặng chạy thread nền (vieneu_client), về UI
        qua self.q. Server + Web UI là tiến trình con từ .venv của kho — không import vieneu."""
        self.vn_api = vn.ApiServer()
        self.vn_web = vn.WebUi()
        self._vn_busy = False
        self._vn_last: Path | None = None        # wav vừa tạo (▶ Nghe lại)
        self._vn_chon_sau: str | None = None     # giọng vừa đăng ký → chọn sau khi tải lại danh sách
        self.vn_voices: list[dict] = []          # giọng trên server (id, name, description)
        self.vn_vai_cb: dict[str, ttk.Combobox] = {}
        self._vn_btns: list[ttk.Button] = []     # nút khoá khi đang bận
        st = load_settings()

        page = ttk.Frame(parent)
        pad = dict(padx=16)
        ttk.Label(page, text="🗣️  VieNeu-TTS — dùng thử qua API server của kho",
                  style="Title.TLabel").pack(anchor="w", pady=(14, 2), **pad)
        ttk.Label(page, text=("v3 Turbo 48 kHz · 25 giọng dựng sẵn · clone giọng mẫu của mình · hội thoại nhiều "
                              "vai · SRT → audio · đo streaming. Cài + bật server ở tab ⚙️ rồi dùng các tab bên "
                              "cạnh; Web UI Gradio có đủ 4 tab gốc trên trình duyệt."),
                  style="Muted.TLabel", wraplength=960, justify="left").pack(anchor="w", pady=(0, 8), **pad)

        # Nhật ký + dòng trạng thái ghim ĐÁY (pack trước, side=bottom) để luôn thấy dù tab con
        # cao; Notebook pack sau lấy phần còn lại.
        logf = ttk.LabelFrame(page, text="  Nhật ký VieNeu (server · cài đặt · kết quả)  ", padding=4)
        logf.pack(side="bottom", fill="x", pady=(0, 10), **pad)
        self.vn_logbox = scrolledtext.ScrolledText(logf, height=5, wrap="word", state="disabled",
                                                   font=("Consolas", 9), relief="flat", borderwidth=0,
                                                   bg=UI["log_bg"], fg=UI["log_info"], padx=8, pady=4)
        self.vn_logbox.pack(fill="x")
        for tag, color in [("info", UI["log_info"]), ("warn", UI["log_warn"]),
                           ("err", UI["log_err"]), ("ok", UI["ok"])]:
            self.vn_logbox.tag_config(tag, foreground=color)
        self.vn_status = tk.StringVar(value="Sẵn sàng.")
        ttk.Label(page, textvariable=self.vn_status, style="Muted.TLabel").pack(side="bottom", anchor="w",
                                                                                 pady=(4, 2), **pad)

        self.vn_nb = ttk.Notebook(page)
        self.vn_nb.pack(fill="both", expand=True, **pad)
        for ten, build in (("⚙️  Chuẩn bị & server", self._vn_tab_server),
                           ("🎧  Đọc văn bản", self._vn_tab_doc),
                           ("🎭  Hội thoại", self._vn_tab_hoi_thoai),
                           ("📝  SRT → audio", self._vn_tab_srt),
                           ("📋  Danh mục chức năng", self._vn_tab_danh_muc)):
            f = ttk.Frame(self.vn_nb, padding=8)
            build(f)
            self.vn_nb.add(f, text=ten)
        try:
            self.vn_nb.select(int(st.get("vn_tab", 0)))
        except Exception:
            pass
        self.vn_nb.bind("<<NotebookTabChanged>>",
                        lambda _e: save_settings(vn_tab=self.vn_nb.index("current")))
        self._vn_cap_nhat_trang_thai()
        return page

    # ── tab ⚙️ chuẩn bị & server ──
    def _vn_tab_server(self, f):
        st = load_settings()
        box = ttk.LabelFrame(f, text="  Kho mã & trạng thái  ", padding=6)
        box.pack(fill="x")
        ttk.Label(box, text=f"Thư mục: {VIENEU_DIR}").pack(anchor="w")
        self.vn_lbl_kho = ttk.Label(box, text="", style="Muted.TLabel", wraplength=920, justify="left")
        self.vn_lbl_kho.pack(anchor="w", pady=(2, 6))
        hang = ttk.Frame(box)
        hang.pack(anchor="w")
        ttk.Button(hang, text="↻ Kiểm lại", command=self._vn_cap_nhat_trang_thai).pack(side="left")
        ttk.Button(hang, text="📁 Mở thư mục", command=lambda: self._mo_thu_muc(VIENEU_DIR)).pack(side="left", padx=(8, 0))
        for nhan, duoi in (("📖 README.vi.md", "README.vi.md"),
                           ("🔊 docs/streaming.vi.md", "docs/streaming.vi.md"),
                           ("🎓 finetune/README.md", "finetune/README.md")):
            p = VIENEU_DIR / duoi
            ttk.Button(hang, text=nhan, state="normal" if p.exists() else "disabled",
                       command=lambda p=p: self._mo_thu_muc(p)).pack(side="left", padx=(8, 0))

        box2 = ttk.LabelFrame(f, text="  Cài đặt — uv sync vào .venv riêng trong kho (không đụng venv OmniVoice)  ", padding=6)
        box2.pack(fill="x", pady=(6, 0))
        h2 = ttk.Frame(box2)
        h2.pack(anchor="w")
        self.vn_btn_cai_gpu = ttk.Button(h2, text="⬇ Cài GPU (uv sync --extra cuda)", command=lambda: self._vn_cai(True))
        self.vn_btn_cai_gpu.pack(side="left")
        self.vn_btn_cai_cpu = ttk.Button(h2, text="⬇ Cài CPU (uv sync)", command=lambda: self._vn_cai(False))
        self.vn_btn_cai_cpu.pack(side="left", padx=(8, 0))
        self._vn_btns += [self.vn_btn_cai_gpu, self.vn_btn_cai_cpu]
        ttk.Label(box2, text=("GPU: torch 2.8 cu128 (đúng bản venv OmniVoice, máy có RTX), lần đầu tải ~2–3 GB · "
                              "CPU: chỉ ONNX, RTF ≈ 0,5 · lần đầu bật server còn tải model từ Hugging Face."),
                  style="Muted.TLabel", wraplength=920, justify="left").pack(anchor="w", pady=(3, 0))

        box3 = ttk.LabelFrame(f, text="  API server chuẩn OpenAI (apps.openai_speech) — các tab 🎧 🎭 📝 gọi vào đây  ", padding=6)
        box3.pack(fill="x", pady=(6, 0))
        h3 = ttk.Frame(box3)
        h3.pack(anchor="w")
        ttk.Label(h3, text="Backend:").pack(side="left")
        self.var_vn_backend = tk.StringVar(value=st.get("vn_backend") or "auto")
        for v, nhan in (("auto", "auto"), ("pytorch", "pytorch (GPU)"), ("onnx", "onnx (CPU)")):
            ttk.Radiobutton(h3, text=nhan, value=v, variable=self.var_vn_backend).pack(side="left", padx=(6, 0))
        ttk.Label(h3, text="   Precision (CPU):").pack(side="left")
        self.var_vn_prec = tk.StringVar(value=st.get("vn_precision") or "fp32")
        for v in vn.PRECISIONS:
            ttk.Radiobutton(h3, text=v, value=v, variable=self.var_vn_prec).pack(side="left", padx=(6, 0))
        ttk.Label(h3, text="   Cổng:").pack(side="left")
        self.var_vn_cong = tk.StringVar(value=str(st.get("vn_cong") or vn.CONG_API))
        ttk.Entry(h3, textvariable=self.var_vn_cong, width=6).pack(side="left", padx=(6, 0))
        h3b = ttk.Frame(box3)
        h3b.pack(anchor="w", pady=(6, 0))
        self.vn_btn_bat = ttk.Button(h3b, text="▶ Bật server", style="Accent.TButton", command=self._vn_bat_server)
        self.vn_btn_bat.pack(side="left")
        self.vn_btn_tat = ttk.Button(h3b, text="⏹ Tắt server", command=self._vn_tat_server, state="disabled")
        self.vn_btn_tat.pack(side="left", padx=(8, 0))
        self.vn_lbl_server = ttk.Label(h3b, text="Server: chưa bật", style="Muted.TLabel")
        self.vn_lbl_server.pack(side="left", padx=(12, 0))
        self._vn_btns.append(self.vn_btn_bat)

        box4 = ttk.LabelFrame(f, text="  Web UI Gradio của kho — Đọc truyện/PDF · Hội thoại · SRT · Voice Cloning (trình duyệt)  ", padding=6)
        box4.pack(fill="x", pady=(6, 0))
        h4 = ttk.Frame(box4)
        h4.pack(anchor="w")
        ttk.Label(h4, text="Cổng:").pack(side="left")
        self.var_vn_cong_web = tk.StringVar(value=str(st.get("vn_cong_web") or vn.CONG_WEB))
        ttk.Entry(h4, textvariable=self.var_vn_cong_web, width=6).pack(side="left", padx=(6, 10))
        self.vn_btn_web = ttk.Button(h4, text="🌐 Bật & mở trình duyệt", command=self._vn_bat_web)
        self.vn_btn_web.pack(side="left")
        self.vn_btn_web_tat = ttk.Button(h4, text="⏹ Tắt Web UI", command=self._vn_tat_web, state="disabled")
        self.vn_btn_web_tat.pack(side="left", padx=(8, 0))
        self.vn_lbl_web = ttk.Label(h4, text="Web UI: chưa bật", style="Muted.TLabel")
        self.vn_lbl_web.pack(side="left", padx=(12, 0))
        self._vn_btns.append(self.vn_btn_web)
        ttk.Label(box4, text="Trên trang: chọn Backbone v3 Turbo → 🔄 Tải Model rồi dùng 4 tab (Web UI và API server "
                             "nạp model riêng, ~1 GB VRAM mỗi cái).",
                  style="Muted.TLabel", wraplength=920, justify="left").pack(anchor="w", pady=(3, 0))

    # ── tab 🎧 đọc văn bản ──
    def _vn_tab_doc(self, f):
        st = load_settings()
        g = ttk.Frame(f)
        g.pack(fill="x")
        ttk.Label(g, text="Giọng:").pack(side="left")
        self.vn_cb_giong = ttk.Combobox(g, width=30, state="readonly")
        self.vn_cb_giong.pack(side="left", padx=(6, 0))
        ttk.Button(g, text="↻ Giọng trên server", command=self._vn_tai_giong).pack(side="left", padx=(6, 0))
        g2 = ttk.Frame(f)
        g2.pack(fill="x", pady=(6, 0))
        ttk.Label(g2, text="🎤 Clone từ giọng mẫu của mình (voice/giong_mau/):").pack(side="left")
        self.vn_cb_mau = ttk.Combobox(g2, width=34, state="readonly", values=list_voices())
        self.vn_cb_mau.pack(side="left", padx=(6, 0))
        if st.get("voice") in list_voices():
            self.vn_cb_mau.set(st["voice"])
        self.vn_btn_dang_ky = ttk.Button(g2, text="➕ Đăng ký lên server", command=self._vn_dang_ky)
        self.vn_btn_dang_ky.pack(side="left", padx=(6, 0))
        self._vn_btns.append(self.vn_btn_dang_ky)
        ttk.Label(f, text="Đăng ký = server clone giọng từ file mẫu (tự khử nhiễu, cắt ≤ 8 s, không cần phiên âm) "
                          "và thêm vào danh sách Giọng với tên file — chỉ còn trong tiến trình server đang chạy.",
                  style="Muted.TLabel", wraplength=920, justify="left").pack(anchor="w", pady=(2, 0))

        ttk.Label(f, text="Văn bản:", style="Muted.TLabel").pack(anchor="w", pady=(8, 2))
        self.vn_txt = tk.Text(f, height=5, wrap="word", font=("Segoe UI", 11), bg=UI["field"], fg=UI["fg"],
                              relief="flat", borderwidth=0, highlightthickness=1,
                              highlightbackground=UI["border"], highlightcolor=UI["accent"], padx=10, pady=8)
        self.vn_txt.pack(fill="x")
        self.vn_txt.insert("1.0", DEFAULT_SCRIPT)
        tg = ttk.Frame(f)
        tg.pack(fill="x", pady=(4, 0))
        ttk.Label(tg, text="Tag cảm xúc (chèn tại con trỏ, thử nghiệm):", style="Muted.TLabel").pack(side="left")
        for t in vn.TAG_CAM_XUC:
            ttk.Button(tg, text=t, command=lambda t=t: self._vn_chen_tag(t)).pack(side="left", padx=(6, 0))

        p = ttk.Frame(f)
        p.pack(fill="x", pady=(8, 0))
        ttk.Label(p, text="🌡  Temperature:").pack(side="left")
        self.var_vn_temp = tk.DoubleVar(value=float(st.get("vn_temp", 0.8)))
        self.lbl_vn_temp = ttk.Label(p, text=f"{self.var_vn_temp.get():.2f}", width=5, font=("Segoe UI Semibold", 10))
        ttk.Scale(p, from_=0.0, to=2.0, length=200, orient="horizontal", variable=self.var_vn_temp,
                  command=lambda _v: self.lbl_vn_temp.config(text=f"{self.var_vn_temp.get():.2f}")).pack(side="left", padx=6)
        self.lbl_vn_temp.pack(side="left")
        ttk.Label(p, text="(≈0,8 ổn định nhất)   Max chars/đoạn:", style="Muted.TLabel").pack(side="left", padx=(8, 0))
        self.var_vn_max_chars = tk.IntVar(value=int(st.get("vn_max_chars", 256)))
        ttk.Spinbox(p, from_=64, to=512, increment=32, width=5, textvariable=self.var_vn_max_chars).pack(side="left", padx=(6, 0))

        a = ttk.Frame(f)
        a.pack(fill="x", pady=(10, 0))
        self.vn_btn_doc = ttk.Button(a, text="🔊  Tạo & nghe", style="Accent.TButton", command=self._vn_doc)
        self.vn_btn_doc.pack(side="left")
        ttk.Button(a, text="▶  Nghe lại", command=self._vn_nghe_lai).pack(side="left", padx=(8, 0))
        ttk.Button(a, text="⏹  Dừng", command=self._stop_play).pack(side="left", padx=(8, 0))
        ttk.Button(a, text="📁  Mở thư mục kết quả", command=lambda: self._mo_thu_muc(VN_OUT)).pack(side="right")
        self._vn_btns.append(self.vn_btn_doc)
        self.vn_lbl_kq = ttk.Label(f, text="Kết quả: chưa có — mỗi lần tạo đo chunk đầu (TTFA), thời gian sinh và RTF.",
                                   style="Muted.TLabel", wraplength=920, justify="left")
        self.vn_lbl_kq.pack(anchor="w", pady=(6, 0))

    # ── tab 🎭 hội thoại ──
    def _vn_tab_hoi_thoai(self, f):
        st = load_settings()
        ttk.Label(f, text="Mỗi dòng  Tên: câu nói  (dòng không có tên nối vào câu trước). Bấm 🔍 Quét nhân vật rồi "
                          "chọn giọng cho từng vai — giọng dựng sẵn hoặc giọng mẫu đã đăng ký ở tab 🎧.",
                  style="Muted.TLabel", wraplength=920, justify="left").pack(anchor="w")
        self.vn_txt_ht = tk.Text(f, height=7, wrap="word", font=("Segoe UI", 11), bg=UI["field"], fg=UI["fg"],
                                 relief="flat", borderwidth=0, highlightthickness=1,
                                 highlightbackground=UI["border"], highlightcolor=UI["accent"], padx=10, pady=8)
        self.vn_txt_ht.pack(fill="x", pady=(4, 0))
        self.vn_txt_ht.insert("1.0", DEFAULT_HOI_THOAI)
        r = ttk.Frame(f)
        r.pack(fill="x", pady=(6, 0))
        ttk.Button(r, text="🔍 Quét nhân vật", command=self._vn_quet_vai).pack(side="left")
        ttk.Label(r, text="   ⏱ Nghỉ giữa câu (s):").pack(side="left")
        self.var_vn_nghi = tk.DoubleVar(value=float(st.get("vn_nghi", 0.3)))
        ttk.Spinbox(r, from_=0.0, to=3.0, increment=0.1, width=5, textvariable=self.var_vn_nghi).pack(side="left", padx=(6, 0))
        self.vn_vai_frame = ttk.Frame(f)
        self.vn_vai_frame.pack(fill="x", pady=(6, 0))
        a = ttk.Frame(f)
        a.pack(fill="x", pady=(10, 0))
        self.vn_btn_ht = ttk.Button(a, text="🎭  Tạo hội thoại & nghe", style="Accent.TButton", command=self._vn_tao_hoi_thoai)
        self.vn_btn_ht.pack(side="left")
        ttk.Button(a, text="▶  Nghe lại", command=self._vn_nghe_lai).pack(side="left", padx=(8, 0))
        ttk.Button(a, text="⏹  Dừng", command=self._stop_play).pack(side="left", padx=(8, 0))
        ttk.Button(a, text="📁  Mở thư mục kết quả", command=lambda: self._mo_thu_muc(VN_OUT)).pack(side="right")
        self._vn_btns.append(self.vn_btn_ht)
        self.vn_lbl_ht = ttk.Label(f, text="", style="Muted.TLabel", wraplength=920, justify="left")
        self.vn_lbl_ht.pack(anchor="w", pady=(6, 0))

    # ── tab 📝 SRT → audio ──
    def _vn_tab_srt(self, f):
        st = load_settings()
        r = ttk.Frame(f)
        r.pack(fill="x")
        ttk.Label(r, text="File .srt tiếng Việt:").pack(side="left")
        self.var_vn_srt = tk.StringVar(value=st.get("vn_srt") or "")
        ttk.Entry(r, textvariable=self.var_vn_srt, width=70).pack(side="left", padx=(6, 0))
        ttk.Button(r, text="📂 Chọn…", command=self._vn_chon_srt).pack(side="left", padx=(6, 0))
        r2 = ttk.Frame(f)
        r2.pack(fill="x", pady=(8, 0))
        ttk.Label(r2, text="Giọng:").pack(side="left")
        self.vn_cb_giong_srt = ttk.Combobox(r2, width=30, state="readonly")
        self.vn_cb_giong_srt.pack(side="left", padx=(6, 0))
        self.var_vn_giu_moc = tk.BooleanVar(value=bool(st.get("vn_giu_moc", True)))
        ttk.Checkbutton(r2, text="Giữ mốc thời gian (cue đọc tràn → đẩy cue sau lùi lại, không co giãn giọng)",
                        variable=self.var_vn_giu_moc).pack(side="left", padx=(12, 0))
        a = ttk.Frame(f)
        a.pack(fill="x", pady=(10, 0))
        self.vn_btn_srt = ttk.Button(a, text="🎵  Tạo audio từ SRT & nghe", style="Accent.TButton", command=self._vn_tao_srt)
        self.vn_btn_srt.pack(side="left")
        ttk.Button(a, text="▶  Nghe lại", command=self._vn_nghe_lai).pack(side="left", padx=(8, 0))
        ttk.Button(a, text="⏹  Dừng", command=self._stop_play).pack(side="left", padx=(8, 0))
        ttk.Button(a, text="📁  Mở thư mục kết quả", command=lambda: self._mo_thu_muc(VN_OUT)).pack(side="right")
        self._vn_btns.append(self.vn_btn_srt)
        self.vn_lbl_srt = ttk.Label(f, text="", style="Muted.TLabel", wraplength=920, justify="left")
        self.vn_lbl_srt.pack(anchor="w", pady=(6, 0))
        ttk.Label(f, text="Chỉ đọc + xếp timeline (như apps/srt_speech.py của kho). Dịch, vẽ sub, thay tiếng vào video "
                          "vẫn là việc của myvideo; file _vi.srt của myvideo nằm trong myvideo/output/<video>/.",
                  style="Muted.TLabel", wraplength=920, justify="left").pack(anchor="w", pady=(10, 0))

    # ── tab 📋 danh mục ──
    def _vn_tab_danh_muc(self, f):
        f.rowconfigure(0, weight=1)
        f.columnconfigure(0, weight=1)
        txt = tk.Text(f, wrap="word", font=("Segoe UI", 10), bg=UI["field"], fg=UI["fg"],
                      relief="flat", borderwidth=0, highlightthickness=0, padx=12, pady=8,
                      cursor="arrow", spacing1=1, spacing3=1)
        txt.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(f, orient="vertical", command=txt.yview)
        sb.grid(row=0, column=1, sticky="ns")
        txt.configure(yscrollcommand=sb.set)
        txt.tag_config("h", font=("Segoe UI Semibold", 12), foreground=UI["accent_dk"], spacing1=12, spacing3=2)
        txt.tag_config("tom", font=("Segoe UI", 10, "italic"), foreground=UI["muted"],
                       lmargin1=4, lmargin2=4, spacing3=4)
        txt.tag_config("li", lmargin1=18, lmargin2=34, spacing3=3)
        txt.tag_config("ghi", foreground=UI["accent_dk"], lmargin1=18, lmargin2=34, spacing3=3)
        txt.insert("end", f"Danh mục đủ chức năng của VieNeu-TTS ({len(VIENEU_CHUC_NANG)} nhóm, bản "
                          f"{vn.phien_ban()}). Dùng thử: ⚙️ cài + server, 🎧 đọc/clone/tag cảm xúc/đo streaming, "
                          "🎭 hội thoại, 📝 SRT ở các tab bên cạnh; Web UI Gradio (tab ⚙️) có Đọc truyện/PDF, "
                          "Hội thoại, SRT, Voice Cloning gốc. Fine-tune LoRA và Docker: theo tài liệu (nút mở ở tab ⚙️).\n",
                   "tom")
        for i, (ten, tom, dong) in enumerate(VIENEU_CHUC_NANG, 1):
            txt.insert("end", f"{i}. {ten}\n", "h")
            if tom:
                txt.insert("end", tom + "\n", "tom")
            for d in dong:
                if d.startswith("→"):
                    txt.insert("end", d + "\n", "ghi")
                else:
                    txt.insert("end", "•  " + d + "\n", "li")
        txt.insert("end", "\n" + VIENEU_GHI_CHU + "\n", "tom")
        txt.config(state="disabled")        # chỉ đọc; vẫn cuộn + bôi chọn được
        self._vieneu_text = txt

    # ── tiện ích chung của trang VieNeu ──
    def _vn_log(self, msg, level="info"):
        self.q.put(("vnlog", (level, str(msg))))

    def _vn_logbox_write(self, level, msg):
        self.vn_logbox.config(state="normal")
        self.vn_logbox.insert("end", msg + "\n", level)
        self.vn_logbox.see("end")
        self.vn_logbox.config(state="disabled")

    def _vn_set_status(self, text):
        self.q.put(("vnstatus", text))

    def _vn_call(self, fn):
        self.q.put(("call", fn))

    def _vn_set_busy(self, busy: bool):
        self._vn_busy = busy
        for b in self._vn_btns:
            b.config(state="disabled" if busy else "normal")
        if not busy:
            self._vn_cap_nhat_trang_thai()

    def _vn_chay(self, viec: str, fn, xong=None):
        """Chạy fn() trong thread nền, khoá các nút sinh; xong → xong(kết quả) trên thread Tk.
        Lỗi → ghi Nhật ký VieNeu (không hộp thoại) và mở khoá."""
        if self._vn_busy:
            self._vn_log("⏳ Đang bận việc khác — đợi xong đã.", "warn")
            return
        self._vn_set_busy(True)
        self._vn_set_status(viec + "…")

        def run():
            try:
                kq = fn()
            except Exception as e:
                self._vn_log(f"❌ {viec}: {e}", "err")
                self._vn_set_status(f"Lỗi: {viec}.")
                self._vn_call(lambda: self._vn_set_busy(False))
                return

            def ok():
                self._vn_set_busy(False)
                if xong:
                    xong(kq)
            self._vn_call(ok)
        threading.Thread(target=run, daemon=True, name="vieneu-" + viec[:24]).start()

    def _vn_cap_nhat_trang_thai(self):
        tt = vn.trang_thai()
        self.vn_lbl_kho.config(text="Trạng thái: " + tt["mo_ta"])
        if not self._vn_busy:
            ok = "normal" if tt["da_cai"] else "disabled"
            self.vn_btn_bat.config(state=ok)
            self.vn_btn_web.config(state=ok)
        self._vn_cap_nhat_server()

    def _vn_cap_nhat_server(self):
        api, web = self.vn_api, self.vn_web
        if api.dang_chay:
            h = api.health(0.5)
            mo_ta = (f"sẵn sàng — backend {h.get('backend')}, {h.get('max_streams')} luồng, {h.get('sample_rate')} Hz"
                     if h else "đang nạp model… (xem Nhật ký)")
            self.vn_lbl_server.config(text=f"Server: {api.url} — {mo_ta}")
        else:
            self.vn_lbl_server.config(text="Server: chưa bật")
        self.vn_btn_tat.config(state="normal" if api.dang_chay else "disabled")
        self.vn_lbl_web.config(text=f"Web UI: {web.url}" if web.dang_chay else "Web UI: chưa bật")
        self.vn_btn_web_tat.config(state="normal" if web.dang_chay else "disabled")

    def _vn_server_san_sang(self) -> bool:
        if not self.vn_api.dang_chay:
            messagebox.showwarning("Chưa bật server", "Bật API server ở tab ⚙️ Chuẩn bị & server trước.")
            return False
        return True

    def _vn_cong(self, var: tk.StringVar, mac_dinh: int) -> int | None:
        try:
            c = int(var.get())
            if 1 <= c <= 65535:
                return c
        except ValueError:
            pass
        messagebox.showwarning("Cổng sai", f"Cổng phải là số 1–65535 (mặc định {mac_dinh}).")
        return None

    # ── cài đặt / server / web ui ──
    def _vn_cai(self, gpu: bool):
        nhan = "GPU (uv sync --extra cuda)" if gpu else "CPU (uv sync)"
        self._vn_log(f"⬇ Cài VieNeu-TTS {nhan} — lần đầu tải vài trăm MB tới vài GB, cứ để chạy…")

        def fn():
            rc = vn.cai_dat(gpu, lambda s: self._vn_log("  " + s))
            if rc != 0:
                raise RuntimeError(f"uv sync thoát mã {rc} — xem dòng lỗi trong Nhật ký")
            return rc

        def xong(_rc):
            self._vn_log("✅ Cài xong. Bấm ▶ Bật server rồi sang tab 🎧.", "ok")
            self._vn_set_status("Cài xong.")
        self._vn_chay("Cài VieNeu-TTS", fn, xong)

    def _vn_bat_server(self):
        cong = self._vn_cong(self.var_vn_cong, vn.CONG_API)
        if cong is None:
            return
        backend, prec = self.var_vn_backend.get(), self.var_vn_prec.get()
        save_settings(vn_cong=cong, vn_backend=backend, vn_precision=prec)
        try:
            self.vn_api.bat(cong, backend, prec, on_line=lambda s: self._vn_log("  " + s))
        except Exception as e:
            self._vn_log(f"❌ Không bật được server: {e}", "err")
            return
        self._vn_log(f"▶ Bật API server ở {self.vn_api.url} (backend {backend}, precision {prec}) — nạp model + "
                     "warm-up; lần đầu còn tải model từ Hugging Face…")
        self._vn_cap_nhat_server()

        def fn():
            h = self.vn_api.cho_san_sang()
            if not h:
                raise RuntimeError("server không lên được — xem dòng lỗi cuối trong Nhật ký")
            return h

        def xong(h):
            self._vn_log(f"✅ Server sẵn sàng: backend {h.get('backend')}, {h.get('max_streams')} luồng, "
                         f"{h.get('sample_rate')} Hz. Sang tab 🎧 để đọc thử.", "ok")
            self._vn_set_status("Server sẵn sàng.")
            self._vn_tai_giong()
        self._vn_chay("Đợi server sẵn sàng", fn, xong)

    def _vn_tat_server(self):
        self.vn_api.tat()
        self._vn_log("⏹ Đã tắt API server.")
        self.vn_status.set("Đã tắt server.")
        self._vn_cap_nhat_server()

    def _vn_bat_web(self):
        cong = self._vn_cong(self.var_vn_cong_web, vn.CONG_WEB)
        if cong is None:
            return
        save_settings(vn_cong_web=cong)
        try:
            self.vn_web.bat(cong, on_line=lambda s: self._vn_log("  [web] " + s))
        except Exception as e:
            self._vn_log(f"❌ Không bật được Web UI: {e}", "err")
            return
        self._vn_log(f"🌐 Bật Web UI Gradio ở {self.vn_web.url} — mở trình duyệt khi trang lên…")
        self._vn_cap_nhat_server()
        url = self.vn_web.url

        def fn():
            if not self.vn_web.cho_san_sang():
                raise RuntimeError("Web UI không lên được — xem dòng [web] trong Nhật ký")
            return url

        def xong(u):
            webbrowser.open(u)
            self._vn_log(f"✅ Web UI đang chạy: {u} (trên trang: 🔄 Tải Model rồi dùng 4 tab).", "ok")
            self._vn_set_status("Web UI đang chạy.")
        self._vn_chay("Đợi Web UI", fn, xong)

    def _vn_tat_web(self):
        self.vn_web.tat()
        self._vn_log("⏹ Đã tắt Web UI.")
        self._vn_cap_nhat_server()

    def _vn_tat_het(self):
        """Đóng cửa sổ: tắt server + Web UI con (tiến trình riêng, không tự chết theo app)."""
        for p in (getattr(self, "vn_api", None), getattr(self, "vn_web", None)):
            if p is not None:
                p.tat()

    # ── giọng ──
    def _vn_ids(self) -> list[str]:
        return [v["id"] for v in self.vn_voices]

    def _vn_tai_giong(self):
        if not self.vn_api.dang_chay:
            self._vn_log("⚠️ Bật server trước rồi mới tải được danh sách giọng.", "warn")
            return

        def xong(vs):
            self.vn_voices = vs
            ids = self._vn_ids()
            nho = load_settings().get("vn_giong")
            for cb in (self.vn_cb_giong, self.vn_cb_giong_srt, *self.vn_vai_cb.values()):
                cur = cb.get()
                cb["values"] = ids
                if self._vn_chon_sau in ids and cb is self.vn_cb_giong:
                    cb.set(self._vn_chon_sau)
                elif cur in ids:
                    cb.set(cur)
                elif nho in ids:
                    cb.set(nho)
                elif ids:
                    cb.set(ids[0])
            self._vn_chon_sau = None
            self._vn_log(f"🎙️ {len(ids)} giọng trên server: " + ", ".join(ids[:14]) + (" …" if len(ids) > 14 else ""))
        self._vn_chay("Tải danh sách giọng", lambda: vn.giong_tren_server(self.vn_api.url), xong)

    def _vn_dang_ky(self):
        if not self._vn_server_san_sang():
            return
        mau = self.vn_cb_mau.get()
        if not mau:
            messagebox.showwarning("Chưa chọn giọng mẫu", "Chọn một file trong voice/giong_mau/ để đăng ký.")
            return
        ten = vn.ten_giong_tu_file(mau)
        clip = VOICE_DIR / mau
        url = self.vn_api.url

        def xong(kq):
            self._vn_chon_sau = kq.get("id") or ten
            self._vn_log(f"✅ Đã đăng ký giọng clone '{self._vn_chon_sau}' từ {mau}.", "ok")
            self._vn_tai_giong()
        self._vn_log(f"➕ Đăng ký {mau} → giọng '{ten}' (server khử nhiễu + trích hồ sơ giọng)…")
        self._vn_chay("Đăng ký giọng clone", lambda: vn.dang_ky_giong(url, ten, clip, True, "giọng mẫu của mình"), xong)

    def _vn_chen_tag(self, tag: str):
        self.vn_txt.insert("insert", " " + tag)
        self.vn_txt.focus_set()

    # ── sinh: đọc / hội thoại / SRT ──
    def _vn_thong_so(self) -> tuple[float, int]:
        temp = round(float(self.var_vn_temp.get()), 2)
        try:
            mc = int(self.var_vn_max_chars.get())
        except (tk.TclError, ValueError):
            mc = 256
        mc = min(max(mc, 64), 512)
        save_settings(vn_temp=temp, vn_max_chars=mc)
        return temp, mc

    def _vn_play(self, p: Path, nhan: str):
        """Phát wav kết quả VieNeu bằng _play_wav dùng chung; đánh dấu _last_raw để thanh chỉnh
        bên OmniVoice không dựng lại file này theo bộ lọc của bài thật."""
        self._stop_play()
        self._last_src, self._last_raw = p, True
        d = self._play_wav(p, lambda d: f"{nhan}  ({d:.1f}s)")
        self.vn_status.set(f"{nhan} — đang phát {d:.1f}s: {p.name}")

    def _vn_nghe_lai(self):
        if self._vn_last and self._vn_last.exists():
            self._vn_play(self._vn_last, "▶ VieNeu")
        else:
            self._vn_log("ℹ️ Chưa có bản nào — bấm Tạo trước.")

    def _vn_doc(self):
        if not self._vn_server_san_sang():
            return
        text = self.vn_txt.get("1.0", "end").strip()
        if not text:
            messagebox.showwarning("Văn bản trống", "Nhập văn bản cần đọc.")
            return
        giong = self.vn_cb_giong.get()
        temp, mc = self._vn_thong_so()
        save_settings(vn_giong=giong)
        url = self.vn_api.url
        out = VN_OUT / f"{safe_stem(giong or 'mac_dinh')}.wav"

        def fn():
            a, info = vn.doc(url, text, giong or None, temp, mc,
                             on_chunk=lambda n: self._vn_set_status(f"Đang nhận audio… {n / 1024:.0f} KB"))
            return vn.ghi_wav(out, a), info

        def xong(kq):
            p, info = kq
            self._vn_last = p
            self.vn_lbl_kq.config(text="Kết quả: " + vn.mo_ta_info(info))
            self._vn_log(f"✅ {p.name} ({giong or 'giọng mặc định'}): {vn.mo_ta_info(info)}", "ok")
            self._vn_play(p, f"🔊 VieNeu · {giong or 'mặc định'}")
        self._vn_log(f"🔊 Sinh VieNeu: giọng {giong or 'mặc định'}, temperature {temp}, {len(text)} ký tự…")
        self._vn_chay("Sinh giọng VieNeu", fn, xong)

    def _vn_quet_vai(self):
        for w in self.vn_vai_frame.winfo_children():
            w.destroy()
        self.vn_vai_cb = {}
        ids = self._vn_ids()
        vai = vn.nhan_vat(self.vn_txt_ht.get("1.0", "end"))
        if not vai:
            self.vn_lbl_ht.config(text="Không thấy dòng nào dạng  Tên: câu nói.")
            return
        nho = load_settings().get("vn_vai") or {}
        for i, ten in enumerate(vai):
            row = ttk.Frame(self.vn_vai_frame)
            row.pack(anchor="w", pady=(0, 3))
            ttk.Label(row, text=f"{ten}:", width=16).pack(side="left")
            cb = ttk.Combobox(row, width=30, state="readonly", values=ids)
            cb.pack(side="left")
            chon = nho.get(ten) if nho.get(ten) in ids else (ids[i % len(ids)] if ids else "")
            cb.set(chon)
            self.vn_vai_cb[ten] = cb
        self.vn_lbl_ht.config(text=f"{len(vai)} vai: " + ", ".join(vai)
                              + ("" if ids else "  — bật server + ↻ Giọng trên server để có giọng chọn"))

    def _vn_tao_hoi_thoai(self):
        if not self._vn_server_san_sang():
            return
        script = self.vn_txt_ht.get("1.0", "end")
        if not self.vn_vai_cb:
            self._vn_quet_vai()
        giong = {t: cb.get() for t, cb in self.vn_vai_cb.items()}
        save_settings(vn_vai=giong, vn_nghi=float(self.var_vn_nghi.get()))
        nghi = float(self.var_vn_nghi.get())
        temp, _mc = self._vn_thong_so()
        url = self.vn_api.url
        out = VN_OUT / "hoi_thoai.wav"

        def fn():
            a, infos = vn.hoi_thoai(url, script, giong, nghi, temp,
                                    on_progress=lambda i, n, t: self._vn_set_status(f"Hội thoại: câu {i}/{n} ({t})…"))
            return vn.ghi_wav(out, a), infos

        def xong(kq):
            p, infos = kq
            self._vn_last = p
            tong = sum(i["tong_s"] for i in infos)
            audio = sum(i["audio_s"] for i in infos)
            self.vn_lbl_ht.config(text=f"Xong: {len(infos)} câu, audio {audio:.1f} s (sinh {tong:.1f} s, "
                                       f"nghỉ {nghi} s giữa câu) → {p.name}")
            self._vn_log(f"✅ Hội thoại {len(infos)} câu → {p.name}: audio {audio:.1f} s, sinh {tong:.1f} s.", "ok")
            self._vn_play(p, "🎭 Hội thoại VieNeu")
        self._vn_log(f"🎭 Hội thoại: {len(giong)} vai ({', '.join(f'{t} = {g}' for t, g in giong.items())})…")
        self._vn_chay("Tạo hội thoại", fn, xong)

    def _vn_chon_srt(self):
        goc = Path(_REPO_ROOT) / "myvideo" / "output"
        p = filedialog.askopenfilename(title="Chọn file phụ đề .srt tiếng Việt",
                                       filetypes=[("Phụ đề SRT", "*.srt"), ("Tất cả", "*.*")],
                                       initialdir=str(goc if goc.is_dir() else Path(_HERE)))
        if p:
            self.var_vn_srt.set(p)
            save_settings(vn_srt=p)

    def _vn_tao_srt(self):
        if not self._vn_server_san_sang():
            return
        p = Path(self.var_vn_srt.get().strip())
        if not p.is_file():
            messagebox.showwarning("Thiếu file SRT", "Chọn một file .srt có thật.")
            return
        giong = self.vn_cb_giong_srt.get()
        giu = bool(self.var_vn_giu_moc.get())
        save_settings(vn_srt=str(p), vn_giu_moc=giu)
        temp, _mc = self._vn_thong_so()
        url = self.vn_api.url
        out = VN_OUT / f"{safe_stem(p.name)}_vieneu.wav"

        def fn():
            track, tt = vn.srt_sang_audio(url, p, giong or None, giu, temp,
                                          on_progress=lambda i, n, t: self._vn_set_status(f"SRT: cue {i}/{n} — {t[:40]}…"))
            return vn.ghi_wav(out, track), tt

        def xong(kq):
            q, tt = kq
            self._vn_last = q
            mo_ta = (f"{tt['so_cue']} cue · audio {tt['audio_s']} s · "
                     + (f"{tt['day']} cue bị đẩy, lệch tối đa {tt['lech_max_s']} s" if giu else "đọc nối tiếp"))
            self.vn_lbl_srt.config(text="Xong: " + mo_ta + f" → {q.name}")
            self._vn_log(f"✅ SRT {p.name} → {q.name}: {mo_ta}.", "ok")
            self._vn_play(q, "📝 SRT VieNeu")
        self._vn_log(f"📝 SRT → audio: {p.name}, giọng {giong or 'mặc định'}, {'giữ mốc' if giu else 'nối tiếp'}…")
        self._vn_chay("Tạo audio từ SRT", fn, xong)

    def _build_omni_page(self, parent) -> ttk.Frame:
        """Trang OmniVoice = màn thử giọng cũ (trước 04/11/2026 là cả cửa sổ)."""
        page = ttk.Frame(parent)
        pad = dict(padx=16)
        ttk.Label(page, text="🎙️  OmniVoice — chọn giọng + kịch bản mẫu để nghe",
                  style="Title.TLabel").pack(anchor="w", pady=(14, 2), **pad)
        ttk.Label(page, text="Tạo audio clone ngắn để so sánh xem giọng nào hợp; 🎧 nghe lại "
                             "giọng mẫu gốc để đối chiếu clone với người thật. "
                             "Kết quả lưu ở voice/_thu_giong/.",
                  style="Muted.TLabel").pack(anchor="w", pady=(0, 10), **pad)

        body = ttk.Frame(page)
        body.pack(fill="both", expand=True, **pad)
        body.columnconfigure(0, weight=0, minsize=300)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        # ── Trái: danh sách giọng ──
        left = ttk.LabelFrame(body, text="  Giọng mẫu  ", padding=10)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        self.listbox = tk.Listbox(left, activestyle="dotbox", font=("Segoe UI", 10),
                                  bg=UI["field"], fg=UI["fg"], selectbackground=UI["accent"],
                                  selectforeground="#ffffff", relief="flat",
                                  highlightthickness=1, highlightbackground=UI["border"])
        self.listbox.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(left, orient="vertical", command=self.listbox.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.listbox.configure(yscrollcommand=sb.set)
        self.listbox.bind("<Double-Button-1>", lambda _e: self._on_make_one())
        self.listbox.bind("<<ListboxSelect>>", self._on_pick_voice)
        ttk.Button(left, text="↻ Tải lại danh sách",
                   command=self._reload_voices).grid(row=1, column=0, columnspan=2,
                                                     sticky="ew", pady=(8, 0))

        # ── Phải: kịch bản + nút + log ──
        right = ttk.Frame(body)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(11, weight=1)     # ô Nhật ký co giãn, các hàng thanh chỉnh giữ nguyên

        ttk.Label(right, text="Kịch bản thử (sửa tay được):",
                  style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        self.txt = tk.Text(right, height=4, wrap="word", font=("Segoe UI", 11),
                           bg=UI["field"], fg=UI["fg"], relief="flat", borderwidth=0,
                           highlightthickness=1, highlightbackground=UI["border"],
                           highlightcolor=UI["accent"], padx=10, pady=8)
        self.txt.grid(row=1, column=0, sticky="ew", pady=(4, 10))
        self.txt.insert("1.0", DEFAULT_SCRIPT)

        actions = ttk.Frame(right)
        actions.grid(row=2, column=0, sticky="ew")
        self.btn_make = ttk.Button(actions, text="🔊  Tạo & nghe giọng đã chọn",
                                   style="Accent.TButton", command=self._on_make_one)
        self.btn_make.pack(side="left")
        self.btn_all = ttk.Button(actions, text="🔁  Tạo cho TẤT CẢ giọng",
                                  command=self._on_make_all)
        self.btn_all.pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="📁  Mở thư mục kết quả",
                   command=self._open_out).pack(side="right")

        # ── 🎧 Hàng NGHE (02/11/2026): đối chiếu giọng mẫu (người thật) với bản clone ──
        # Mẫu phát NGUYÊN BẢN — thanh tốc độ/tông/bộ lọc không đụng vào, vì đó là thứ
        # model nghe để học; clone phát theo thanh chỉnh = đúng thứ bài thật sẽ ra.
        nghe = ttk.Frame(right)
        nghe.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(nghe, text="🎧  Nghe:", font=("Segoe UI Semibold", 10)).pack(side="left")
        self.btn_mau = ttk.Button(nghe, text="🎤  Giọng mẫu (gốc)", command=self._on_play_sample)
        self.btn_mau.pack(side="left", padx=(8, 0))
        self.btn_play = ttk.Button(nghe, text="▶  Giọng clone", command=self._on_play_saved)
        self.btn_play.pack(side="left", padx=(8, 0))
        self.btn_ab = ttk.Button(nghe, text="⇄  Mẫu → clone", command=self._on_play_ab)
        self.btn_ab.pack(side="left", padx=(8, 0))
        self.btn_stop = ttk.Button(nghe, text="⏹  Dừng", command=self._stop_play)
        self.btn_stop.pack(side="left", padx=(8, 0))
        ttk.Label(nghe, text="mẫu = file gốc trong voice/giong_mau/, không qua thanh chỉnh  •  clone = bản thử theo thanh chỉnh",
                  style="Muted.TLabel").pack(side="left", padx=(12, 0))

        # ── 🔗 Thông số giọng dùng chung với bài thật (01/11/2026) ──
        # Mở lên: các thanh ở đúng mức taogiong_options.json. Bật 🔗 (mặc định): nhả
        # chuột / bấm ± là ghi ngay vào đó — GUI/web dùng chung file nên "chỉnh ở
        # đây = chỉnh ở bài thật". Tắt 🔗 để thử thoải mái; ↻ kéo về mức đang lưu.
        bt0 = bai_that_doc()
        self._da_luu = dict(bt0)          # mức vừa đồng bộ — không đổi thì không ghi lại
        sync_row = ttk.Frame(right)
        sync_row.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        ttk.Label(sync_row, text="⚙️  Thông số giọng = bài thật:",
                  font=("Segoe UI Semibold", 10)).pack(side="left")
        self.var_sync = tk.BooleanVar(value=bool(load_settings().get("dong_bo", True)))
        ttk.Checkbutton(sync_row, text="🔗 Đồng bộ (đổi là lưu vào bài thật)",
                        variable=self.var_sync, command=self._on_sync_toggle).pack(side="left", padx=(10, 0))
        ttk.Button(sync_row, text="↻ Lấy từ bài thật", command=self._lay_bai_that).pack(side="left", padx=(8, 0))
        self.lbl_sync = ttk.Label(right, style="Muted.TLabel",
                                  text=("🔗 đang ở mức bài thật (taogiong_options.json): " + mo_ta_thong_so(**bt0))
                                  if self.var_sync.get() else
                                  "tắt đồng bộ: chỉnh ở đây không đụng bài thật (mở lên vẫn lấy mức bài thật)")
        self.lbl_sync.grid(row=5, column=0, sticky="w", pady=(2, 0))

        # ── Tốc độ nghe thử (= ô Tăng tốc video ngang của bài thật) ──
        speed_row = ttk.Frame(right)
        speed_row.grid(row=6, column=0, sticky="ew", pady=(6, 0))
        ttk.Label(speed_row, text="⏩  Tốc độ:", width=15).pack(side="left")
        ttk.Button(speed_row, text="−", width=3,
                   command=lambda: self._bump_speed(-SPEED_STEP)).pack(side="left", padx=(8, 0))
        self.var_speed = tk.DoubleVar(value=bt0["speed"])
        self.scale_speed = ttk.Scale(speed_row, from_=SPEED_MIN, to=SPEED_MAX, length=280,
                                     orient="horizontal", variable=self.var_speed,
                                     command=lambda _v: self._update_speed_label())
        self.scale_speed.pack(side="left", padx=6)
        self.scale_speed.bind("<ButtonRelease-1>", self._on_speed_release)
        ttk.Button(speed_row, text="+", width=3,
                   command=lambda: self._bump_speed(SPEED_STEP)).pack(side="left")
        self.lbl_speed = ttk.Label(speed_row, text=f"{self._speed():.2f}×", width=6,
                                   font=("Segoe UI Semibold", 11))
        self.lbl_speed.pack(side="left", padx=(10, 0))
        ttk.Button(speed_row, text="↺ 1.0×", width=8,
                   command=lambda: self._set_speed(1.0)).pack(side="left", padx=(6, 0))
        ttk.Label(speed_row, text="= ô Tăng tốc video ngang (giữ cao độ)  •  file gốc không đổi",
                  style="Muted.TLabel").pack(side="left", padx=(12, 0))

        # ── 🎚 Mẫu giọng cài sẵn (02/11/2026) + Tông giọng — chung một ô lưới ──
        # Bấm một mẫu = đặt tông + 4 bộ lọc theo bảng hu.MAU_GIONG (cùng bảng với GUI
        # và web) rồi PHÁT NGAY bản clone giọng đang chọn với bộ số đó (04/11/2026 —
        # bấm là nghe, như ▶ Giọng clone); 🔗 bật thì ghi luôn vào bài thật. Kéo thanh
        # lệch mẫu → nhãn thành "Tuỳ chỉnh". Sáng giọng đổi mức thì phải bấm Tạo lại
        # mới nghe đúng (prompt dựng từ giọng mẫu đã EQ), các mức khác đổi là nghe ngay.
        giong_box = ttk.Frame(right)
        giong_box.grid(row=7, column=0, sticky="ew", pady=(6, 0))
        mau_row = ttk.Frame(giong_box)
        mau_row.pack(fill="x")
        ttk.Label(mau_row, text="🎚  Mẫu giọng:", width=15).pack(side="left")
        self.var_mau = tk.StringVar(value=hu.MAU_TUY_CHINH)
        for ten in hu.mau_ten():
            ttk.Radiobutton(mau_row, text=ten, value=ten, variable=self.var_mau,
                            command=self._ap_mau).pack(side="left", padx=(8, 0))
        self.lbl_mau = ttk.Label(mau_row, text="", style="Muted.TLabel")
        self.lbl_mau.pack(side="left", padx=(12, 0))

        # ── Tông giọng nghe thử (cao độ theo bán cung, giữ tốc độ) ──
        pitch_row = ttk.Frame(giong_box)
        pitch_row.pack(fill="x", pady=(6, 0))
        ttk.Label(pitch_row, text="🎵  Tông giọng:", width=15).pack(side="left")
        ttk.Button(pitch_row, text="−", width=3,
                   command=lambda: self._bump_pitch(-PITCH_STEP)).pack(side="left", padx=(8, 0))
        self.var_pitch = tk.DoubleVar(value=bt0["pitch"])
        self.scale_pitch = ttk.Scale(pitch_row, from_=PITCH_MIN, to=PITCH_MAX, length=280,
                                     orient="horizontal", variable=self.var_pitch,
                                     command=lambda _v: self._update_pitch_label())
        self.scale_pitch.pack(side="left", padx=6)
        self.scale_pitch.bind("<ButtonRelease-1>", self._on_pitch_release)
        ttk.Button(pitch_row, text="+", width=3,
                   command=lambda: self._bump_pitch(PITCH_STEP)).pack(side="left")
        self.lbl_pitch = ttk.Label(pitch_row, text=fmt_pitch(self._pitch()), width=6,
                                   font=("Segoe UI Semibold", 11))
        self.lbl_pitch.pack(side="left", padx=(10, 0))
        ttk.Button(pitch_row, text="↺ 0", width=8,
                   command=lambda: self._set_pitch(0.0)).pack(side="left", padx=(6, 0))
        ttk.Label(pitch_row, text="bán cung: + cao, − trầm  •  giữ tốc độ  •  = ô Tông giọng bài thật",
                  style="Muted.TLabel").pack(side="left", padx=(12, 0))

        # ── Bộ lọc giọng kiểu CapCut (0–100, 0 = tắt): tiếng vang + thiếu niên ──
        fx0 = bt0["fx"]
        self.var_fx, self.lbl_fx = {}, {}
        vang_row = ttk.Frame(right)
        vang_row.grid(row=8, column=0, sticky="ew", pady=(6, 0))
        ttk.Label(vang_row, text="🔔  Tiếng vang:", width=15).pack(side="left")
        self._fx_slider(vang_row, "vang_truong_do", "trường độ", fx0, length=140)
        self._fx_slider(vang_row, "vang_cuong_do", "cường độ", fx0, length=140)
        ttk.Button(vang_row, text="↺ tắt", width=6,
                   command=lambda: self._set_fx(vang_cuong_do=0)).pack(side="left", padx=(6, 0))
        ttk.Label(vang_row, text="bật khi cường độ > 0  •  = ô 🔔 bài thật",
                  style="Muted.TLabel").pack(side="left", padx=(12, 0))

        tn_row = ttk.Frame(right)
        tn_row.grid(row=9, column=0, sticky="ew", pady=(6, 0))
        ttk.Label(tn_row, text="🧒  Thiếu niên:", width=15).pack(side="left")
        self._fx_slider(tn_row, "thieu_nien", "cường độ", fx0, length=280)
        ttk.Button(tn_row, text="↺ 0", width=6,
                   command=lambda: self._set_fx(thieu_nien=0)).pack(side="left", padx=(6, 0))
        ttk.Label(tn_row, text="giọng trẻ hơn: dời formant + nhỉnh cao độ  •  giữ tốc độ",
                  style="Muted.TLabel").pack(side="left", padx=(12, 0))

        # 🔆 Sáng giọng (23/10/2026): EQ bớt ồm — bản phát áp ngay; lúc bấm Tạo còn
        # EQ cả giọng mẫu trong bộ nhớ khi dựng prompt (đúng đường bài thật).
        sang_row = ttk.Frame(right)
        sang_row.grid(row=10, column=0, sticky="ew", pady=(6, 0))
        ttk.Label(sang_row, text="🔆  Sáng giọng:", width=15).pack(side="left")
        self._fx_slider(sang_row, "sang_giong", "cường độ", fx0, length=280)
        ttk.Button(sang_row, text="↺ 0", width=6,
                   command=lambda: self._set_fx(sang_giong=0)).pack(side="left", padx=(6, 0))
        ttk.Label(sang_row, text="bớt ồm 150–500 Hz, thêm 3 kHz + dải cao  •  lúc Tạo: EQ cả giọng mẫu "
                                 "(file mẫu không đổi)",
                  style="Muted.TLabel").pack(side="left", padx=(12, 0))
        self._cap_nhat_mau()          # radio 🎚 sáng đúng mẫu đang lưu (hoặc không cái nào)

        self.status = tk.StringVar(value="Sẵn sàng.")
        ttk.Label(right, textvariable=self.status, style="Muted.TLabel").grid(
            row=12, column=0, sticky="w", pady=(8, 2))
        self.pb = ttk.Progressbar(right, mode="determinate", maximum=100)
        self.pb.grid(row=13, column=0, sticky="ew", pady=(0, 8))   # lề đáy, không sát mép cửa sổ

        logf = ttk.LabelFrame(right, text="  Nhật ký  ", padding=6)
        logf.grid(row=11, column=0, sticky="nsew", pady=(8, 4))
        logf.rowconfigure(0, weight=1)
        logf.columnconfigure(0, weight=1)
        self.logbox = scrolledtext.ScrolledText(logf, height=5, wrap="word", state="disabled",
                                                font=("Consolas", 9), relief="flat", borderwidth=0,
                                                bg=UI["log_bg"], fg=UI["log_info"], padx=8, pady=6)
        self.logbox.grid(row=0, column=0, sticky="nsew")
        for tag, color in [("info", UI["log_info"]), ("warn", UI["log_warn"]),
                           ("err", UI["log_err"]), ("ok", UI["ok"])]:
            self.logbox.tag_config(tag, foreground=color)
        return page

    # ── danh sách giọng ──
    def _reload_voices(self):
        voices = list_voices()
        self.listbox.delete(0, "end")
        for v in voices:
            self.listbox.insert("end", v)
        if voices:
            # Chọn lại giọng của lần trước; giọng đó bị xoá/đổi tên thì lùi về đầu.
            nho = load_settings().get("voice")
            i = voices.index(nho) if nho in voices else 0
            self.listbox.selection_set(i)
            self.listbox.activate(i)
            self.listbox.see(i)
        self.status.set(f"Có {len(voices)} giọng trong {VOICE_DIR.name}/.")

    def _selected_voice(self):
        sel = self.listbox.curselection()
        return self.listbox.get(sel[0]) if sel else None

    def _on_pick_voice(self, _e=None):
        """Nhớ giọng NGAY lúc bấm, không đợi lúc thoát — app có bị tắt ngang
        (hoặc đóng bằng nút X lúc đang tạo) thì lần sau vẫn mở đúng giọng đó."""
        v = self._selected_voice()
        if v and v != load_settings().get("voice"):
            save_settings(voice=v)

    # ── log / queue ──
    def _log(self, msg, level="info"):
        self.q.put(("log", (level, str(msg))))

    def _set_status(self, text):
        self.q.put(("status", text))

    def _set_prog(self, pct):
        self.q.put(("prog", pct))

    def _poll(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    level, msg = payload
                    self.logbox.config(state="normal")
                    self.logbox.insert("end", msg + "\n", level)
                    self.logbox.see("end")
                    self.logbox.config(state="disabled")
                elif kind == "status":
                    self.status.set(payload)
                elif kind == "prog":
                    self.pb["value"] = payload
                elif kind == "vnlog":                      # Nhật ký riêng tab VieNeu
                    level, msg = payload
                    self._vn_logbox_write(level, msg)
                elif kind == "vnstatus":
                    self.vn_status.set(payload)
                elif kind == "call":                       # hàm cần chạy trên thread Tk
                    payload()
                elif kind == "done":
                    self._set_busy(False)
                    play = payload
                    if play and Path(play).exists():
                        self._play_file(Path(play))
        except queue.Empty:
            pass
        self.root.after(120, self._poll)

    def _set_busy(self, busy):
        self._busy = busy
        state = "disabled" if busy else "normal"
        # 🎤 Giọng mẫu vẫn bấm được lúc đang tạo: không đụng model, nghe lại mẫu trong
        # lúc chờ là hợp lý (tạo xong thì bản clone tự phát và cắt mẫu).
        for b in (self.btn_make, self.btn_all, self.btn_play, self.btn_ab):
            b.config(state=state)

    # ── model ──
    def _ensure_model(self):
        """Nạp model OmniVoice 1 lần (lần đầu sẽ chậm), giữ lại cho các lượt sau."""
        if self._model is not None:
            return
        self._log("📦 Đang tải model OmniVoice... lần đầu hơi lâu.")
        self._set_status("Đang tải model...")
        self._model, self._sr = tts.load_omnivoice()   # một chỗ nạp chung với bài thật
        self._log("✅ Đã tải model.", "ok")

    # (_don_vram / _xa_whisper_con / _nha_model trước đây tự viết lại gc +
    #  empty_cache y như amain; 24/10/2026 gộp về bản dùng chung _tra_vram /
    #  _free_asr / _do_omnivoice — log của chúng vào ô Nhật ký qua _LogTap.)
    def _xa_whisper_con(self):
        """Xả Whisper mà OmniVoice tự nạp để phiên âm giọng mẫu (~1.6 GB) — bản
        dùng chung tts._free_asr: tự trả VRAM và ghi log. Chỉ là lưới dự phòng:
        từ khi dùng chung _voice_prompt, dựng prompt xong là đã xả ngay."""
        if self._model is not None:
            tts._free_asr(self._model)

    def _nha_model(self):
        """Nhả hẳn OmniVoice khỏi VRAM (đóng cửa sổ). Bấm tạo lại thì tự nạp lại.
        Dùng chung tts._do_omnivoice (bỏ tham chiếu TRƯỚC) rồi tts._tra_vram (dọn
        SAU) — ngược thứ tự thì trọng số còn sống, dọn chẳng trả được gì."""
        if self._model is None:
            return
        self._model = tts._do_omnivoice(self._model, "đóng cửa sổ Thử giọng")
        tts._tra_vram()

    def _synthesize(self, text, voice_path, sang=0):
        """Sinh audio clone cho 1 giọng; ghép các đoạn nếu kịch bản dài.
        `sang` = mức 🔆 Sáng giọng: > 0 thì giọng mẫu được EQ trong bộ nhớ lúc dựng
        prompt (tts._voice_prompt) — đúng như bài thật làm.

        Gọi THẲNG _generate_chunk của bản tạo giọng thật, không tự gọi
        model.generate nữa: nghe thử phải đi đúng đường mà bài thật sẽ đi, không
        thì nghe xong chẳng suy ra được gì. Ba thứ khác nhau trước đây:
          • khung thời lượng: giờ là vn_duration() đếm ÂM TIẾT, trước để model tự
            đoán theo KÝ TỰ — đo được lệch nhịp đọc 17% so với 6%;
          • language="vi" + num_step=NUM_STEP giống hệt bài thật;
          • voice_clone_prompt dựng 1 lần rồi lưu .prompt.pt cạnh file giọng mẫu,
            thay vì ref_audio= khiến mỗi đoạn phải chạy lại Whisper phiên âm.
            Prompt này bài thật dùng lại được luôn.
        """
        # clean_text y hệt bài thật ("…" → ".", bỏ ngoặc kép, gạch ngang → cách)
        # rồi .lower() — bài thật cũng vào model bằng chữ thường.
        chunks = split_chunks(tts.clean_text(text).lower())
        parts = []
        for j, c in enumerate(chunks):
            self._set_status(f"Đang tạo đoạn {j + 1}/{len(chunks)}...")
            a = tts._generate_chunk(self._model, "clone", str(voice_path), c,
                                    sang_giong=sang)[0]
            parts.append(np.asarray(a, dtype="float32"))
        # Ghép Y HỆT bài thật (run_tts): cân mức to giữa các đoạn → cắt im lặng
        # mép đoạn rồi chèn nghỉ theo dấu kết thúc đoạn (hết câu 0,45 s, hết đoạn
        # văn 0,60 s, ; : 0,30 s, phẩy 0,25 s — PAUSE_* bên tts) → đệm im lặng
        # cuối. Trước đây ghép thẳng nên chỗ nghỉ giữa câu khác hẳn bài thật.
        self._set_status("Đang ghép các đoạn...")
        parts = tts._balance_chunk_levels(parts, self._sr,
                                          moc=bool(tts.load_opt_settings().get("chuan_am", False)))
        merged = tts._join_with_pauses(parts, chunks, self._sr)
        tail = np.zeros(int(tts.TAIL_SILENCE_SEC * self._sr), dtype="float32")
        return np.concatenate([merged, tail])

    def _save(self, out: Path, audio) -> None:
        """Ghi wav rồi chuẩn độ to y hệt bài thật (nén nhẹ SPEECH_COMPRESSOR +
        loudnorm về VOICE_LUFS) — so giọng mà bản to bản nhỏ thì tai nghiêng về
        bản to, so sánh không công bằng."""
        sf.write(str(out), audio, self._sr)
        if not tts.load_opt_settings().get("chuan_am", False):
            self._log("⏭ Không chuẩn âm (ô 🔉 của bài thật đang tắt) — giữ mức gốc của giọng.")
            return
        self._set_status("Đang chuẩn hoá độ to...")
        try:
            tts._loudnorm_file(out, tts.VOICE_LUFS, pre_filter=tts.SPEECH_COMPRESSOR)
        except Exception as e:
            self._log(f"⚠️ Không chuẩn được độ to ({e}) → giữ bản chưa chuẩn.", "warn")

    # ── tạo cho 1 giọng ──
    def _on_make_one(self):
        if self._busy:
            return
        voice = self._selected_voice()
        if not voice:
            messagebox.showwarning("Chưa chọn giọng", "Hãy chọn một giọng trong danh sách.")
            return
        text = self.txt.get("1.0", "end").strip()
        if not text:
            messagebox.showwarning("Thiếu kịch bản", "Hãy nhập kịch bản thử.")
            return
        self._stop_play()
        self._set_busy(True)
        self.pb["value"] = 0
        # Đọc mức sáng giọng ở luồng chính (tk.Var không đọc từ luồng nền).
        sang = self._fx()["sang_giong"]
        threading.Thread(target=self._worker_one, args=(voice, text, sang), daemon=True).start()

    def _worker_one(self, voice, text, sang=0):
        out = None
        try:
            self._ensure_model()
            self._log(f"🎙️ Thử giọng: {voice}"
                      + (f"  (🔆 sáng giọng {sang}: EQ cả giọng mẫu lúc dựng prompt)" if sang else ""))
            audio = self._synthesize(text, VOICE_DIR / voice, sang)
            out = out_file(voice, sang)
            self._save(out, audio)
            self.pb["value"] = 100
            self._log(f"✅ Xong → {out.name} (nghe thử ngay).", "ok")
            self._set_status(f"Xong: {voice} → đang phát...")
        except Exception as e:
            self._log(f"❌ Lỗi: {e}", "err")
            self._log(traceback.format_exc(), "err")
            self._set_status(f"Lỗi: {e}")
            out = None
        finally:
            self._xa_whisper_con()   # xong lượt → Whisper hết việc, trả VRAM
            self.q.put(("done", str(out) if out else None))

    # ── tạo cho tất cả giọng ──
    def _on_make_all(self):
        if self._busy:
            return
        voices = list_voices()
        if not voices:
            messagebox.showwarning("Không có giọng", f"Không thấy giọng nào trong {VOICE_DIR}.")
            return
        text = self.txt.get("1.0", "end").strip()
        if not text:
            messagebox.showwarning("Thiếu kịch bản", "Hãy nhập kịch bản thử.")
            return
        if not messagebox.askyesno(
                "Tạo cho tất cả",
                f"Sẽ tạo audio thử cho TẤT CẢ {len(voices)} giọng.\n"
                "Có thể mất một lúc. Xong rồi chọn từng giọng bấm '▶ Nghe lại' để so sánh.\n\nTiếp tục?"):
            return
        self._stop_play()
        self._set_busy(True)
        self.pb["value"] = 0
        sang = self._fx()["sang_giong"]
        threading.Thread(target=self._worker_all, args=(voices, text, sang), daemon=True).start()

    def _worker_all(self, voices, text, sang=0):
        try:
            self._ensure_model()
            total = len(voices)
            if sang:
                self._log(f"🔆 Sáng giọng {sang}: EQ cả giọng mẫu lúc dựng prompt "
                          f"(bản thử lưu *_sang{sang}.wav).")
            for k, voice in enumerate(voices):
                self._log(f"[{k + 1}/{total}] 🎙️ {voice}")
                try:
                    audio = self._synthesize(text, VOICE_DIR / voice, sang)
                    out = out_file(voice, sang)
                    self._save(out, audio)
                    self._log(f"   ✅ → {out.name}", "ok")
                except Exception as e:
                    self._log(f"   ❌ {voice}: {e}", "err")
                self._set_prog(int((k + 1) / total * 100))
            self._set_status(f"Xong tất cả {total} giọng. Chọn giọng + '▶ Nghe lại' để so sánh.")
            self._log("🎉 Hoàn thành tạo cho tất cả giọng.", "ok")
        except Exception as e:
            self._log(f"❌ Lỗi: {e}", "err")
            self._set_status(f"Lỗi: {e}")
        finally:
            self._xa_whisper_con()   # xong cả mẻ → Whisper hết việc, trả VRAM
            self.q.put(("done", None))

    # ── tốc độ nghe thử ──
    def _speed(self) -> float:
        """Tốc độ đang chọn, đã làm tròn về bội của SPEED_STEP (1.05, 1.10, 1.15...)."""
        v = round(self.var_speed.get() / SPEED_STEP) * SPEED_STEP
        return round(min(SPEED_MAX, max(SPEED_MIN, v)), 2)

    def _update_speed_label(self):
        self.lbl_speed.config(text=f"{self._speed():.2f}×")

    def _set_speed(self, value: float):
        self.var_speed.set(min(SPEED_MAX, max(SPEED_MIN, value)))
        self._update_speed_label()
        self._on_speed_release()

    def _bump_speed(self, delta: float):
        self._set_speed(self._speed() + delta)

    def _on_speed_release(self, _e=None):
        """Nhả chuột / bấm ±: nếu đang phát dở thì phát lại luôn ở tốc độ mới để so sánh."""
        self._update_speed_label()
        self._luu_bai_that()
        self._replay_if_playing()

    # ── 🔗 dùng chung thông số với bài thật ──
    def _thong_so(self) -> dict:
        """Mức đang chọn trên 3 nhóm thanh — cùng dạng bai_that_doc()."""
        return dict(speed=self._speed(), pitch=self._pitch(), fx=self._fx())

    def _luu_bai_that(self):
        """Bật 🔗 thì ghi mức đang chọn vào taogiong_options.json (đúng khoá GUI/web);
        chưa đổi so với lần ghi trước thì thôi. Chỉ gọi từ luồng chính (đọc tk.Var)."""
        if not self.var_sync.get():
            return
        ts = self._thong_so()
        if ts == self._da_luu:
            return
        try:
            bai_that_luu(**ts)
        except Exception as e:
            self._log(f"⚠️ Không lưu được vào taogiong_options.json: {e}", "warn")
            return
        self._da_luu = ts
        self.lbl_sync.config(text="✓ đã lưu vào bài thật: " + mo_ta_thong_so(**ts))

    def _lay_bai_that(self):
        """↻: kéo 3 nhóm thanh về đúng mức taogiong_options.json đang lưu (GUI/web vừa
        đổi thì bấm nút này). Không ghi ngược lại; đang phát thì phát lại cho nghe."""
        bt = bai_that_doc()
        self._da_luu = dict(bt)
        self.var_speed.set(bt["speed"])
        self.var_pitch.set(bt["pitch"])
        for k, v in bt["fx"].items():
            self.var_fx[k].set(v)
        self._update_speed_label()
        self._update_pitch_label()
        self._update_fx_labels()
        self._cap_nhat_mau()
        self.lbl_sync.config(text="↻ đã lấy từ bài thật: " + mo_ta_thong_so(**bt))
        self._replay_if_playing()

    def _on_sync_toggle(self):
        """Tick 🔗: đẩy ngay mức đang chọn sang bài thật; bỏ tick: từ giờ chỉnh tự do."""
        save_settings(dong_bo=bool(self.var_sync.get()))
        if self.var_sync.get():
            self._da_luu = None
            self._luu_bai_that()
            if self._da_luu is None:      # không có gì để ghi (lỗi) → vẫn báo trạng thái
                self.lbl_sync.config(text="🔗 đang đồng bộ với bài thật")
        else:
            self.lbl_sync.config(text="tắt đồng bộ: chỉnh ở đây không đụng bài thật")

    # ── 🎚 mẫu giọng cài sẵn (bảng hu.MAU_GIONG, chung với GUI/web) ──
    def _ap_mau(self):
        """Bấm một mẫu: đặt tông + 4 bộ lọc theo bảng (lưu vào bài thật nếu 🔗) rồi
        PHÁT NGAY bản clone của giọng đang chọn với bộ số đó — như bấm ▶ Giọng clone
        (04/11/2026: trước chỉ đặt thanh, đang phát dở mới phát lại; bấm mẫu xong
        phải bấm thêm nút nghe mới so được). Không phát được (đang tạo / chưa chọn
        giọng / chưa có bản thử) thì báo ở Nhật ký, không chặn bằng hộp thoại."""
        ts = hu.mau_thong_so(self.var_mau.get())
        if ts is None:
            return
        sang_cu = self._fx()["sang_giong"]
        self.var_pitch.set(ts["pitch"])
        for k, v in ts["fx"].items():
            self.var_fx[k].set(v)
        self._update_pitch_label()
        self._update_fx_labels()
        self._cap_nhat_mau()
        self._luu_bai_that()
        if self._nghe_mau_giong():
            return
        if ts["fx"]["sang_giong"] != sang_cu:
            self._log(f"ℹ️ Mẫu '{self.var_mau.get()}' đổi mức sáng giọng {sang_cu} → "
                      f"{ts['fx']['sang_giong']}: bấm '🔊 Tạo & nghe' để dựng lại (prompt từ "
                      "giọng mẫu đã EQ); tông/vang/thiếu niên thì nghe ngay.", "warn")

    def _nghe_mau_giong(self) -> bool:
        """Phát bản clone giọng đang chọn theo bộ số vừa đặt (bấm mẫu 🎚). Trả True nếu
        đã phát. Đang tạo thì thôi (file đang ghi; tạo xong bản mới tự phát theo
        thanh chỉnh hiện tại). Chưa có bản thử → _clone_file đã báo ở Nhật ký."""
        if self._busy:
            self._log(f"ℹ️ Đã đặt mẫu '{self.var_mau.get()}' — đang tạo, xong sẽ tự phát "
                      "theo mẫu này.")
            return False
        voice = self._selected_voice()
        if not voice:
            self._log("ℹ️ Chưa chọn giọng trong danh sách nên chưa phát được mẫu.", "warn")
            return False
        f = self._clone_file(voice, hoi=False)
        if not f:
            return False
        self._play_file(f)
        return True

    def _cap_nhat_mau(self):
        """Nhãn mẫu đi theo thanh: khớp đúng bộ số mẫu nào thì chọn mẫu đó, không
        thì "Tuỳ chỉnh" (không radio nào sáng)."""
        if not hasattr(self, "lbl_mau"):
            return
        ten = hu.mau_khop(self._pitch(), self._fx())
        self.var_mau.set(ten)
        self.lbl_mau.config(text=hu.MAU_MO_TA.get(ten, "bộ số riêng — bấm một mẫu để điền lại"))

    # ── tông giọng nghe thử ──
    def _pitch(self) -> float:
        """Số bán cung đang chọn, đã làm tròn về bội của PITCH_STEP (0.5, 1.0, 1.5...)."""
        v = round(self.var_pitch.get() / PITCH_STEP) * PITCH_STEP
        return round(min(PITCH_MAX, max(PITCH_MIN, v)), 1)

    def _update_pitch_label(self):
        self.lbl_pitch.config(text=fmt_pitch(self._pitch()))

    def _set_pitch(self, value: float):
        self.var_pitch.set(min(PITCH_MAX, max(PITCH_MIN, value)))
        self._update_pitch_label()
        self._on_pitch_release()

    def _bump_pitch(self, delta: float):
        self._set_pitch(self._pitch() + delta)

    def _on_pitch_release(self, _e=None):
        """Nhả chuột / bấm ±: nếu đang phát dở thì phát lại luôn ở tông mới để so sánh."""
        self._update_pitch_label()
        self._cap_nhat_mau()
        self._luu_bai_that()
        self._replay_if_playing()

    # ── bộ lọc giọng nghe thử (tiếng vang / thiếu niên) ──
    def _fx_slider(self, parent, key: str, label: str, init: dict, length: int):
        """Một thanh 0–100 + nhãn số cho khoá bộ lọc `key` (nhả chuột → phát lại)."""
        ttk.Label(parent, text=f"{label}:").pack(side="left", padx=(8, 4))
        self.var_fx[key] = tk.DoubleVar(value=init.get(key, 0))
        sc = ttk.Scale(parent, from_=hu.FX_MIN, to=hu.FX_MAX, length=length,
                       orient="horizontal", variable=self.var_fx[key],
                       command=lambda _v: self._update_fx_labels())
        sc.pack(side="left", padx=(0, 4))
        sc.bind("<ButtonRelease-1>", self._on_fx_release)
        self.lbl_fx[key] = ttk.Label(parent, text=str(int(init.get(key, 0))), width=4,
                                     font=("Segoe UI Semibold", 11))
        self.lbl_fx[key].pack(side="left")

    def _fx(self) -> dict:
        """4 mức bộ lọc đang chọn (int 0–100) — cùng dạng dict mà bài thật nhận."""
        return {k: hu.parse_fx(v.get()) for k, v in self.var_fx.items()}

    def _update_fx_labels(self):
        for k, v in self._fx().items():
            self.lbl_fx[k].config(text=str(v))

    def _set_fx(self, **vals):
        for k, v in vals.items():
            self.var_fx[k].set(hu.parse_fx(v))
        self._on_fx_release()

    def _on_fx_release(self, _e=None):
        """Nhả chuột / bấm ↺: nếu đang phát dở thì phát lại luôn với bộ lọc mới."""
        self._update_fx_labels()
        self._cap_nhat_mau()
        self._luu_bai_that()
        self._replay_if_playing()

    def _replay_if_playing(self):
        """Kéo thanh lúc đang phát CLONE → phát lại ngay với mức mới. Đang phát GIỌNG
        MẪU thì thôi: mẫu luôn nguyên bản, thanh chỉnh không áp lên nó."""
        if self._last_raw:
            return
        if self._is_playing() and self._last_src and self._last_src.exists():
            self._play_file(self._last_src)

    def _is_playing(self) -> bool:
        """winsound không báo khi phát xong → ước lượng bằng độ dài file."""
        return self._playing and time.monotonic() < self._play_until

    def _render_file(self, src: Path, speed: float, pitch: float, fx: dict | None = None) -> Path:
        """Bản đã đổi tốc độ (giữ cao độ), tông (giữ tốc độ) và/hoặc bộ lọc của
        `src` — dùng lại nếu đã render và còn mới. Tông 0 + không bộ lọc thì tên
        file y như trước (`...@1.05x.wav`) để cache tốc độ cũ vẫn dùng được."""
        SPEED_DIR.mkdir(exist_ok=True)
        fx = hu.fx_from(fx)
        tag = (f"@{speed:.2f}x" + (f"{pitch:+.1f}st" if abs(pitch) > 1e-9 else "")
               + hu.fx_tag(**fx))
        dst = SPEED_DIR / f"{src.stem}{tag}.wav"
        if dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
            return dst
        args, sr, _ = hu.build_ffmpeg_args(src, speed, pitch, None, **fx)
        proc = subprocess.run(
            [FFMPEG, "-y", "-loglevel", "error", *args, "-ar", str(sr), str(dst)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            creationflags=CREATE_NO_WINDOW)
        if proc.returncode != 0 or not dst.exists():
            raise RuntimeError((proc.stderr or "ffmpeg lỗi không rõ").strip()[-300:])
        return dst

    # ── phát lại bản CLONE ──
    def _clone_file(self, voice: str, hoi: bool = True) -> Path | None:
        """Bản thử (clone) của `voice` ứng với mức 🔆 đang chọn. Chưa có bản mức này
        nhưng có bản mức 0 thì lùi về đó (báo rõ); chưa có gì → trả None, báo bằng
        hộp thoại (`hoi`=True, bấm nút nghe) hoặc chỉ Nhật ký + trạng thái (`hoi`=False,
        bấm mẫu 🎚 — mẫu đã đặt xong rồi, không chặn người dùng)."""
        sang = self._fx()["sang_giong"]
        f = out_file(voice, sang)
        if not f.exists() and sang and out_file(voice, 0).exists():
            # Chưa có bản dựng với giọng mẫu EQ mức này → phát bản mẫu gốc + EQ output
            # cho nghe tạm, nhưng nói rõ: bài thật còn EQ cả giọng mẫu.
            self._log(f"ℹ️ Chưa có bản thử dựng với giọng mẫu EQ mức {sang} → phát bản mẫu "
                      "gốc + EQ output. Bấm '🔊 Tạo & nghe' để nghe đúng như bài thật.", "warn")
            f = out_file(voice, 0)
        if not f.exists():
            if hoi:
                messagebox.showinfo("Chưa có bản thử",
                                    f"Chưa tạo bản thử cho '{voice}'.\nBấm '🔊 Tạo & nghe' trước.")
            else:
                self._log(f"ℹ️ Chưa có bản thử cho '{voice}' → bấm '🔊 Tạo & nghe' một lần, "
                          "sau đó bấm mẫu 🎚 là nghe ngay.", "warn")
                self.status.set(f"Chưa có bản thử cho '{voice}' — bấm '🔊 Tạo & nghe' trước.")
            return None
        return f

    def _on_play_saved(self):
        voice = self._selected_voice()
        if not voice:
            messagebox.showwarning("Chưa chọn giọng", "Hãy chọn một giọng để nghe lại.")
            return
        f = self._clone_file(voice)
        if f:
            self._play_file(f)

    def _play_file(self, path: Path):
        """Phát `path` (bản clone GỐC) ở tốc độ + tông + bộ lọc đang chọn; file gốc không bị sửa."""
        self._stop_play()
        self._last_src, self._last_raw = path, False
        speed, pitch, fx = self._speed(), self._pitch(), self._fx()
        play_path = path
        if abs(speed - 1.0) > 1e-6 or abs(pitch) > 1e-9 or hu.fx_active(**fx):
            self.status.set(f"🎚️ Đang đổi tốc độ {speed:.2f}× / tông {fmt_pitch(pitch)} / "
                            f"bộ lọc {hu.fx_describe(**fx)}...")
            self.root.update_idletasks()
            try:
                play_path = self._render_file(path, speed, pitch, fx)
            except Exception as e:
                self._log(f"⚠️ Không đổi được tốc độ/tông/bộ lọc ({e}) → phát bản gốc.", "warn")
                speed, pitch, fx = 1.0, 0.0, hu.fx_from(None)
        self._play_wav(play_path, lambda d: (
            f"▶ Đang phát clone: {path.name}  ({speed:.2f}×, tông {fmt_pitch(pitch)}, "
            f"bộ lọc: {hu.fx_describe(**fx)}, {d:.1f}s)"))

    # ── 🎤 giọng MẪU nguyên bản (02/11/2026) ──
    def _wav_giong_mau(self, src: Path) -> Path:
        """Đổi giọng mẫu `src` (mp3 / wav bất kỳ) sang wav 16-bit cho winsound phát được;
        cache ở MAU_DIR theo tên đầy đủ, còn mới hơn file mẫu thì dùng lại. Không áp
        gì khác — mẫu phải nghe đúng như thứ model được nghe."""
        dst = mau_wav_file(src.name)
        if dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
            return dst
        MAU_DIR.mkdir(exist_ok=True)
        proc = subprocess.run(
            [FFMPEG, "-y", "-loglevel", "error", "-i", str(src), "-c:a", "pcm_s16le", str(dst)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            creationflags=CREATE_NO_WINDOW)
        if proc.returncode != 0 or not dst.exists():
            raise RuntimeError((proc.stderr or "ffmpeg lỗi không rõ").strip()[-300:])
        return dst

    def _on_play_sample(self):
        voice = self._selected_voice()
        if not voice:
            messagebox.showwarning("Chưa chọn giọng", "Hãy chọn một giọng để nghe mẫu.")
            return
        self._play_sample(voice)

    def _play_sample(self, voice: str) -> float:
        """Phát file giọng mẫu gốc trong voice/giong_mau/ NGUYÊN BẢN (không tốc độ / tông / bộ lọc).
        Trả thời lượng (s) để ⇄ hẹn phát clone tiếp; 0 nếu không phát được."""
        src = VOICE_DIR / voice
        if not src.exists():
            messagebox.showwarning("Thiếu file giọng mẫu", f"Không thấy file:\n{src}")
            return 0.0
        self._stop_play()
        self._last_src, self._last_raw = src, True
        sang = self._fx()["sang_giong"]
        if sang:
            self._log(f"ℹ️ Phát mẫu GỐC. Bài thật đang để 🔆 {sang} nên dựng prompt từ mẫu đã EQ "
                      "sáng giọng — bản clone sẽ sáng hơn mẫu này một chút là đúng.")
        try:
            play_path = self._wav_giong_mau(src)
        except Exception as e:
            self._log(f"⚠️ Không đổi được giọng mẫu sang wav ({e}) → mở bằng trình phát mặc định.", "warn")
            try:
                os.startfile(str(src))  # type: ignore[attr-defined]
            except Exception as e2:
                messagebox.showerror("Lỗi phát giọng mẫu", str(e2))
            return 0.0
        return self._play_wav(play_path, lambda d: (
            f"🎤 Đang phát giọng MẪU gốc: {voice}  ({d:.1f}s, không qua thanh chỉnh)"))

    def _play_wav(self, play_path: Path, status_of) -> float:
        """Phát wav `play_path` bằng winsound (không chặn); `status_of(giây)` → dòng trạng
        thái. Trả thời lượng ước lượng để _is_playing / ⇄ biết lúc nào xong (winsound
        không báo khi phát hết)."""
        try:
            duration = sf.info(str(play_path)).duration
        except Exception:
            duration = 0.0
        try:
            import winsound
            winsound.PlaySound(str(play_path), winsound.SND_FILENAME | winsound.SND_ASYNC)
            self._playing = True
            self._play_until = time.monotonic() + duration + 0.3
            self.status.set(status_of(duration))
        except Exception:
            try:
                os.startfile(str(play_path))  # type: ignore[attr-defined]
            except Exception as e:
                messagebox.showerror("Lỗi phát audio", str(e))
        return duration

    # ── ⇄ mẫu → clone: phát mẫu gốc, hết thì tự phát bản clone để đối chiếu ──
    def _on_play_ab(self):
        voice = self._selected_voice()
        if not voice:
            messagebox.showwarning("Chưa chọn giọng", "Hãy chọn một giọng để so sánh.")
            return
        clone = self._clone_file(voice)
        if not clone:
            return
        dur = self._play_sample(voice)
        if dur <= 0:
            return
        # Hẹn sau khi mẫu phát hết (+0,6 s nghỉ); _stop_play / phát thứ khác đổi token
        # → lượt hẹn tự bỏ, không bất ngờ vang clone lên giữa việc khác.
        self._ab_token += 1
        token = self._ab_token
        self._log(f"⇄ {voice}: mẫu gốc {dur:.1f}s → rồi tự phát clone {clone.name}.")
        self.root.after(int((dur + 0.6) * 1000), lambda: self._ab_clone(token, clone))

    def _ab_clone(self, token: int, clone: Path):
        if token != self._ab_token:
            return
        self._play_file(clone)

    def _stop_play(self):
        self._ab_token += 1          # huỷ lượt clone đang hẹn của ⇄ (nếu có)
        try:
            import winsound
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass
        self._playing = False
        self._play_until = 0.0

    def _open_out(self):
        self._mo_thu_muc(OUT_DIR)

    def _mo_thu_muc(self, thu_muc: Path):
        """Mở `thu_muc` bằng Explorer; không mở được thì ghi đường dẫn ra dòng trạng thái."""
        try:
            os.startfile(str(thu_muc))  # type: ignore[attr-defined]
        except Exception:
            self.status.set(f"Thư mục: {thu_muc}")


def main():
    root = tk.Tk()
    app = App(root)

    # Nhả model TRƯỚC khi Tk đóng: để CUDA tự dọn lúc trình thông dịch thoát thì
    # thi thoảng treo/nổ lỗi driver trên Windows, mà máy chấm dứt tiến trình chậm
    # thì card vẫn kẹt vài GB trong lúc bên kia (tạo giọng, dựng video) đang chờ.
    def _thoat():
        try:
            app._vn_tat_het()        # server + Web UI VieNeu là tiến trình con — tắt theo cửa sổ
        except Exception:
            pass
        try:
            app._nha_model()
        except Exception:
            pass
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", _thoat)
    root.mainloop()


if __name__ == "__main__":
    main()
