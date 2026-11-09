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
Cùng ngày đổi bố cục sang MENU DỌC bên trái (tỷ lệ màn hình ngang). Tab 🗣️ VIENEU-TTS từng
nằm dưới tab 🎙️ OMNIVOICE đã GỠ 09/11/2026 theo yêu cầu user (card RTX 4060 TDR khi chạy SDK
đó; code ở nhánh luu-sau-02-11-vieneu). Tab đang mở nhớ giữa các lần chạy.
Cùng ngày gom GIỌNG MẪU (wav/mp3) + .prompt.pt vào voice/giong_mau/ — voice/ chỉ còn
code (file này) và kết quả thử _thu_giong/. Bài thật (amain VOICE_DIR),
web (core.VOICE_DIR) và myvideo (VOICE_DIRS[0]) cùng trỏ voice/giong_mau/ nên kho vẫn
dùng chung; tên giọng đã lưu trong cài đặt là tên file trần nên không phải đổi gì.
Từ 07/11/2026 trang 🎙️ OMNIVOICE làm lại theo đúng khối "3 Cài đặt tạo giọng" của web
myvoice (chức năng tương ứng): ① Giọng mẫu · ② Văn bản thử · ③ Cài đặt giọng (🎚 mẫu,
🎵 tông, ⏩ tốc độ, 🔔 vang, 🧒 thiếu niên, 🔆 sáng giọng, 🔊 ÂM LƯỢNG dB —
ô 🔊 là mới, cùng khoá am_luong_db với GUI/web, 🔗 đồng bộ như các thanh
khác) rồi hàng NGHE. Chữ giải thích dài dời vào tooltip (rê chuột lên nhãn), mỗi hàng gọn.
VĂN BẢN THỬ không còn là câu mẫu cố định: mở app là lấy ≈30 GIÂY ĐẦU (ô "≈ giây" đổi được)
của KỊCH BẢN MỚI NHẤT trong kịch_bản/ (thư mục tập tạo sau cùng có input.docx/txt), dừng ở
cuối câu — kich_ban_moi_nhat() + van_ban_dau(); ↻ lấy lại, ✎ về câu mẫu cũ, sửa tay vẫn
được. Bản clone lưu THÔ (cân mức tương đối giữa câu như bài thật; chuẩn âm −14 LUFS gỡ hẳn
10/11/2026); 🔊 âm lượng áp lúc PHÁT cùng tông /
bộ lọc / tốc độ (_render_file, cache theo cả bộ số, dựng ở luồng nền) — bật/tắt là nghe
ngay, không dựng lại. Nút 🎧 BÀI THẬT (30 s) = đúng nút 🎧 Nghe thử của web: áp bộ số đang
chọn lên mẫu ~30 s giọng gốc của tập đầu đợt kịch bản mới nhất (scripts/taogiong_nghethu.py,
voice/nghe_thu/) rồi phát — nghe đúng giọng bài thật đang dùng mà không cần
tạo; kéo thanh lúc đang phát là dựng + phát lại.

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
import dich_input_docx as inputdocx  # noqa: E402  đọc input.docx/txt của tập (văn bản thử = kịch bản mới nhất)
import taogiong_nghethu as nt      # noqa: E402  mẫu 🎧 nghe thử ~30 s giọng gốc bài thật (như nút 🎧 web)

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

HERE_DIR = Path(_HERE)                        # myvoice/voice: code (file này) + kết quả thử
VOICE_DIR = HERE_DIR / "giong_mau"            # GIỌNG MẪU (wav/mp3) + .prompt.pt — gom riêng từ 04/11/2026, cùng
                                              # thư mục với amain_taogiong_gui.VOICE_DIR (bài thật, web, myvideo)
OUT_DIR = HERE_DIR / "_thu_giong"             # nơi lưu audio nghe thử
SIDEBAR_W = 190                               # bề rộng menu dọc bên trái (px)
# Các tab menu dọc: (khoá nhớ trong settings, chữ trên nút, mô tả nhỏ dưới chữ)
TABS = [("omni", "🎙️  OmniVoice", "thử giọng clone · cài đặt giọng = web")]
# (tab "vieneu" gỡ 09/11/2026 — settings cũ còn ghi tab="vieneu" thì _chon_tab về "omni")
VOICE_DIR.mkdir(exist_ok=True)                # thiếu thì tạo rỗng cho biết chỗ bỏ giọng mẫu vào
OUT_DIR.mkdir(exist_ok=True)
AUDIO_EXTS = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wma"}
CHUNK_DEFAULT = 160                           # cỡ cắt câu dài khi chưa có taogiong_options.json
# 07/11/2026: VĂN BẢN THỬ = ≈ ngần này giây đầu của kịch bản mới nhất (cùng cỡ với mẫu 🎧
# của web: taogiong_nghethu.MAU_GIAY); ô "≈ giây" trên trang đổi được trong dải dưới.
VAN_BAN_GIAY = 30
VAN_BAN_GIAY_MIN, VAN_BAN_GIAY_MAX = 10, 120
AMLUONG_STEP = 0.5                            # bước 🔊 âm lượng (dB) — như Spinbox GUI / gợi ý web
NHAN_CLONE = "▶ Đang phát clone"              # chữ mở đầu dòng trạng thái khi phát bản clone (mặc định _play_file)
FX_KEYS = tuple(hu.fx_from(None))             # 4 khoá bộ lọc, đúng thứ tự bảng hu.fx_from

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

# Câu mẫu cố định — từ 07/11/2026 chỉ còn là DỰ PHÒNG (nút ✎, hoặc khi kịch_bản/ chưa có tập
# nào có input): mặc định ô văn bản lấy ≈30 s đầu kịch bản mới nhất (van_ban_dau). Có câu
# kể, câu hỏi để nghe ngữ điệu.
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

# Chú thích cho tooltip (rê chuột lên nhãn) — thay các dòng giải thích dài kế thanh chỉnh,
# nội dung theo đúng title= của các ô bên web (_form_voice.html, khối "Cài đặt tạo giọng").
TIP = dict(
    pitch="+ cao hơn, − trầm hơn, 0 = giữ nguyên (bán cung). Giữ tốc độ, giữ âm sắc người đọc. "
          "Bài thật áp lên audio gốc ngay sau khi ghép nên video ngang/dọc/TikTok đều theo; "
          "chỉ áp lúc tạo giọng, ♻ dùng lại audio thì giữ tông cũ.",
    speed="= ô Tăng tốc video ngang (ngang_speed) của bài thật, 0,5–2,0×: atempo giữ cao độ. "
          "Chỉ ảnh hưởng bản phát ở đây và video ngang; file clone không đổi.",
    vang_truong_do="0–100. Độ dài đuôi vang như CapCut: 0 = phòng nhỏ, 100 = hội trường. "
                   "Chỉ có tác dụng khi cường độ > 0.",
    vang_cuong_do="0–100, 0 = tắt. Mức tiếng vang trộn vào giọng; áp cùng lúc với tông lên audio gốc.",
    thieu_nien="0–100, 0 = tắt. Giọng trẻ hơn: dời formant + nhỉnh cao độ theo mức "
               "(100 = formant ×1,18 và +4 bán cung). Giữ tốc độ.",
    sang_giong="0–100, 0 = tắt. Trị giọng clone ồm: EQ bớt 150–500 Hz, nâng 3 kHz + dải cao "
               "(100 = ±6 dB, thêm exciter). Bản phát áp ngay; lúc Tạo còn EQ cả GIỌNG MẪU trong bộ "
               "nhớ khi dựng prompt (file mẫu không đổi) → đổi mức thì bấm Tạo lại mới nghe đúng, "
               "bản thử lưu riêng <giọng>_sang<N>.wav.",
    am_luong="0 = giữ nguyên. + to hơn, − nhỏ hơn (−10 … +20 dB, bước 0,5; +6 dB ≈ to gấp đôi). "
             "Cộng một mức lên cả bài, không nén; mức dương có bộ chặn đỉnh. Bài thật áp sau cùng "
             "lên audio gốc; ở đây áp lúc phát nên đổi là nghe ngay.",
    dong_bo="Bật: nhả chuột / bấm ± / tick ô là ghi ngay vào taogiong_options.json — GUI/web mở lại "
            "là thấy (chỉnh ở đây = chỉnh bài thật). Tắt: thử tự do, không đụng bài thật (mở app "
            "vẫn lấy mức bài thật).",
    lay_bai_that="Kéo mọi ô về đúng mức taogiong_options.json đang lưu (GUI/web vừa đổi thì bấm). "
                 "Không ghi ngược lại.",
    mau_giong="Bấm một mẫu = đặt tông + 4 bộ lọc theo bảng chung với GUI/web rồi PHÁT NGAY bản clone "
              "của giọng đang chọn với bộ số đó "
              "(chưa có bản thì chỉ báo ở Nhật ký). Kéo thanh lệch mẫu → 'Tuỳ chỉnh'.",
    giong_mau="File giọng mẫu (wav/mp3) trong voice/giong_mau/ — kho chung với bài thật, web và "
              "myvideo. Bấm đôi = Tạo & nghe giọng đó.",
    van_ban_giay="Độ dài đọc ước lượng của văn bản thử (10–120 s). Đổi số rồi Enter (hoặc bấm ↻) "
                 "để lấy lại từ kịch bản.",
    lay_lai="Lấy lại ≈N giây đầu của kịch bản mới nhất trong kịch_bản/ (thư mục tập tạo sau cùng có "
            "input.docx/txt). Ghi đè chữ đang sửa.",
    cau_mau="Về câu mẫu cố định (có câu kể, câu hỏi) thay cho đoạn kịch bản.",
    tao="Sinh bản clone của văn bản thử bằng giọng đang chọn, đi y hệt đường bài thật (làm sạch chữ, "
        "chia mỗi câu một đoạn, cân mức giữa câu, nghỉ theo dấu) rồi phát theo các ô ③. Lưu "
        "voice/_thu_giong/<giọng>.wav (mức 🔆 > 0: <giọng>_sang<N>.wav).",
    tao_tat_ca="Tạo bản thử cho mọi giọng trong kho với cùng văn bản — xong chọn từng giọng bấm ▶ để so.",
    nghe_mau="Phát file gốc trong voice/giong_mau/ NGUYÊN BẢN (không qua thanh chỉnh) — thứ model "
             "nghe để học.",
    nghe_clone="Phát bản thử đã tạo của giọng đang chọn, áp đủ các ô ③ (như bài thật sẽ ra).",
    nghe_ab="Phát mẫu gốc xong tự phát tiếp bản clone để đối chiếu.",
    nghe_bai_that="= nút 🎧 Nghe thử của web: áp bộ số đang chọn (tông, bộ lọc, chuẩn âm, âm lượng, "
                  "tốc độ) lên ~30 s GIỌNG GỐC của tập đầu đợt kịch bản mới nhất (voice/nghe_thu, "
                  "scripts/taogiong_nghethu.py) rồi phát — nghe đúng giọng bài thật đang dùng mà "
                  "không cần tạo. Kéo thanh lúc đang phát là dựng + phát lại.",
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
# Các ô ③ ở đây ↔ đúng khoá GUI/web dùng trong taogiong_options.json:
#   tốc độ nghe  ↔ ngang_speed (ô "Tăng tốc" video ngang, chuỗi "1.2")
#   tông giọng   ↔ pitch (float bán cung)
#   4 bộ lọc     ↔ vang_truong_do / vang_cuong_do / thieu_nien / sang_giong (int 0–100)
#   🔊 âm lượng  ↔ am_luong_db (float dB, bước 0,5)          — thêm 07/11/2026
def default_am_luong() -> float:
    """🔊 Âm lượng (dB) = khoá am_luong_db của bài thật; 0 = giữ nguyên."""
    try:
        return hu.parse_amluong(tts.load_opt_settings().get("am_luong_db"),
                                tts.OPTS_DEFAULTS.get("am_luong_db", 0.0))
    except Exception:
        return 0.0


def fmt_am_luong(db: float) -> str:
    """'+5.0 dB', '-2.5 dB', còn 0 thì '0 dB'."""
    return f"{db:+.1f} dB" if abs(db) > 1e-9 else "0 dB"


def bai_that_doc() -> dict:
    """Thông số giọng bài thật đang lưu → {"speed", "pitch", "fx", "am_luong"} (đã kẹp)."""
    return dict(speed=default_speed(), pitch=default_pitch(), fx=default_fx(),
                am_luong=default_am_luong())


def bai_that_luu(speed: float, pitch: float, fx: dict | None,
                 am_luong: float | None = None) -> None:
    """Ghi thông số giọng vào taogiong_options.json đúng khoá GUI/web đọc; các khoá
    khác giữ nguyên (tts.save_opt_settings gộp dict). am_luong = None →
    không đụng khoá đó (chỗ gọi cũ 3 tham số vẫn chạy)."""
    d = dict(ngang_speed=f"{parse_speed(speed):g}", pitch=tts.parse_pitch(pitch, 0.0),
             **hu.fx_from(fx))
    if am_luong is not None:
        d["am_luong_db"] = hu.parse_amluong(am_luong)
    tts.save_opt_settings(d)


def mo_ta_thong_so(speed: float, pitch: float, fx: dict | None,
                   am_luong: float = 0.0) -> str:
    """'1.20×, tông +1.0, bộ lọc sáng giọng 80, âm lượng +5.0 dB' — dòng trạng thái."""
    s = f"{speed:.2f}×, tông {fmt_pitch(pitch)}, bộ lọc {hu.fx_describe(**hu.fx_from(fx))}"
    if abs(hu.parse_amluong(am_luong)) > 1e-9:
        s += f", âm lượng {fmt_am_luong(hu.parse_amluong(am_luong))}"
    return s


# ── VĂN BẢN THỬ = ≈30 GIÂY ĐẦU KỊCH BẢN MỚI NHẤT (07/11/2026) ──────────────────
_HET_CAU = (".", "!", "?", "。", "！", "？")


def kich_ban_moi_nhat():
    """Thư mục tập TẠO SAU CÙNG trong kịch_bản/ có kịch bản (input.docx / input.txt có
    chữ). "Mới nhất" tính theo lúc tạo thư mục (như mẫu 🎧 của web: nt._tao_luc) chứ không
    theo số tập — số có khi cấp lại cho truyện khác. Không có → None."""
    ds = []
    for p in tts.episode_dirs():
        if inputdocx.find_input(p) is None:
            continue
        try:
            ds.append((nt._tao_luc(p), int(tts.episode_of(p.name) or 0), p))
        except OSError:
            pass
    return max(ds, key=lambda r: (r[0], r[1]))[2] if ds else None


def van_ban_dau(text: str, giay: float = VAN_BAN_GIAY, chunk: int | None = None) -> tuple[str, dict]:
    """Phần đầu `text` đọc hết ≈ `giay` giây, dừng ở CUỐI CÂU (hết câu / hết đoạn văn —
    mẩu bị cắt ở ; : , thì lấy tiếp tới hết câu). Chia câu đúng như lúc tạo giọng
    (tts.split_chunks theo ô chunk) và ước giờ bằng vn_duration + nghỉ theo dấu
    (_pause_after) — chính thước đo bài thật dùng. Giữ nguyên chữ hoa / ngoặc kép cho dễ
    đọc khi sửa tay (lúc Tạo mới clean_text + lower như bài thật).
    Trả (văn bản, {"so_cau", "giay", "het": True nếu lấy hết bài})."""
    chunks = tts.split_chunks(text or "", chunk or chunk_size())
    lay, tong = [], 0.0
    for c in chunks:
        lay.append(c)
        tong += (tts.vn_duration(tts.clean_text(c)) or 0.0) + tts._pause_after(c)
        if tong >= giay and (c.rstrip(" \t").endswith("\n") or c.rstrip().endswith(_HET_CAU)):
            break
    doan, cau = [], []
    for c in lay:
        cau.append(c.strip())
        if c.rstrip(" \t").endswith("\n"):
            doan.append(" ".join(cau))
            cau = []
    if cau:
        doan.append(" ".join(cau))
    return "\n".join(doan), dict(so_cau=len(lay), giay=round(tong, 1), het=len(lay) == len(chunks))




class Tooltip:
    """Chú thích hiện khi rê chuột lên widget ~0,5 s (thay các dòng giải thích dài kế thanh
    chỉnh — vai trò của title= trên web). Một cửa sổ nhỏ không viền, tự ẩn khi rời chuột
    hay bấm. Không có chữ thì không gắn gì."""

    def __init__(self, widget, text: str, delay_ms: int = 500, wrap: int = 440):
        self.w, self.text, self.delay, self.wrap = widget, text or "", delay_ms, wrap
        self._hen = None
        self._tip = None
        if not self.text:
            return
        widget.bind("<Enter>", self._len, add="+")
        widget.bind("<Leave>", self._an, add="+")
        widget.bind("<ButtonPress>", self._an, add="+")

    def _len(self, _e=None):
        self._huy()
        self._hen = self.w.after(self.delay, self._hien)

    def _hien(self):
        self._hen = None
        if self._tip is not None:
            return
        try:
            x = self.w.winfo_rootx() + 12
            y = self.w.winfo_rooty() + self.w.winfo_height() + 6
        except tk.TclError:
            return
        tip = tk.Toplevel(self.w)
        tip.wm_overrideredirect(True)
        try:
            tip.attributes("-topmost", True)
        except tk.TclError:
            pass
        tk.Label(tip, text=self.text, justify="left", wraplength=self.wrap, bg="#fffbe6",
                 fg=UI["fg"], relief="solid", borderwidth=1, font=("Segoe UI", 9),
                 padx=8, pady=5).pack()
        tip.wm_geometry(f"+{x}+{y}")
        self._tip = tip

    def _huy(self):
        if self._hen is not None:
            try:
                self.w.after_cancel(self._hen)
            except tk.TclError:
                pass
            self._hen = None

    def _an(self, _e=None):
        self._huy()
        if self._tip is not None:
            try:
                self._tip.destroy()
            except tk.TclError:
                pass
            self._tip = None


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
        root.title("Thử giọng — OmniVoice")
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
        self._last_bai_that = False  # True = vừa phát mẫu 🎧 BÀI THẬT → kéo thanh là dựng lại mẫu đó
        self._render_token = 0      # lượt dựng bản phát (luồng nền): đổi số là bỏ kết quả lượt cũ
        self._last_nhan = NHAN_CLONE  # chữ mở đầu dòng trạng thái của bản vừa phát (phát lại giữ nguyên)
        self._model = None          # nạp 1 lần, dùng lại
        self._sr = None
        self.q = queue.Queue()      # (kind, payload) từ thread nền
        logging.getLogger().addHandler(_LogTap(self.q))   # log hàm dùng chung → Nhật ký
        logging.getLogger().setLevel(logging.INFO)

        # 07/11/2026: biến tk của ② văn bản thử + ③ cài đặt giọng tạo MỘT LẦN ở đây rồi gắn vào trang
        # (trước có hai trang OmniVoice / VieNeu dùng chung; trang VieNeu gỡ 09/11/2026). Nhãn số gom ở
        # _nhan (khoá → [nhãn]) để cập nhật cùng lúc.
        st = load_settings()
        bt0 = bai_that_doc()
        self._da_luu = dict(bt0)          # mức vừa đồng bộ — không đổi thì không ghi lại
        self.var_speed = tk.DoubleVar(master=root, value=bt0["speed"])
        self.var_pitch = tk.DoubleVar(master=root, value=bt0["pitch"])
        self.var_fx = {k: tk.DoubleVar(master=root, value=bt0["fx"].get(k, 0)) for k in FX_KEYS}
        self.var_am_luong = tk.DoubleVar(master=root, value=bt0["am_luong"])
        self.var_sync = tk.BooleanVar(master=root, value=bool(st.get("dong_bo", True)))
        self.var_mau = tk.StringVar(master=root, value=hu.MAU_TUY_CHINH)
        self.var_giay = tk.StringVar(master=root, value=str(self._kep_giay(st.get("van_ban_giay"))))
        self._nhan: dict[str, list] = {}                      # "speed" / "pitch" / "am_luong" / "fx:<k>" / "sync" / "mau"
        self._o_van_ban: list[tuple[tk.Text, ttk.Label]] = []  # (ô chữ, nhãn nguồn) ② ở từng trang
        self._btn_bai_that: list[ttk.Button] = []             # nút 🎧 Bài thật ở từng trang (khoá lúc dựng)

        self._build_styles()
        self._build_ui()
        self._reload_voices()
        self._nap_van_ban(bao=True)   # ≈30 s đầu kịch bản mới nhất (không có → câu mẫu)
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
        st.configure("Nho.TButton", padding=(5, 3), font=("Segoe UI", 9))   # − + ↺ và nút phụ
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
        self._pages = {"omni": self._build_omni_page(holder)}
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

    def _build_omni_page(self, parent) -> ttk.Frame:
        """Trang OmniVoice — làm lại 07/11/2026 theo khối "3 Cài đặt tạo giọng" của web myvoice
        (chức năng tương ứng): ① Giọng mẫu (trái) · ② Văn bản thử = ≈30 s đầu kịch bản mới
        nhất · nút Tạo + hàng Nghe (có 🎧 Bài thật = nút 🎧 Nghe thử của web) · ③ Cài đặt
        giọng dùng chung với bài thật xếp 2 cột, giải thích dài nằm trong tooltip · Nhật ký."""
        page = ttk.Frame(parent)
        pad = dict(padx=16)
        ttk.Label(page, text="🎙️  OmniVoice — thử giọng clone đúng như bài thật sẽ ra",
                  style="Title.TLabel").pack(anchor="w", pady=(14, 2), **pad)
        ttk.Label(page, text="Chọn giọng → 🔊 Tạo & nghe. Các ô ③ là cài đặt giọng của bài thật "
                             "(GUI/web dùng chung; 🔗 bật là đổi ở đây = đổi bên kia). Rê chuột lên "
                             "nhãn để xem giải thích. Kết quả: voice/_thu_giong/.",
                  style="Muted.TLabel", wraplength=1000, justify="left").pack(anchor="w", pady=(0, 10), **pad)

        body = ttk.Frame(page)
        body.pack(fill="both", expand=True, **pad)
        body.columnconfigure(0, weight=0, minsize=280)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        # ── ① Giọng mẫu ──
        left = ttk.LabelFrame(body, text="  ① Giọng mẫu  ", padding=10)
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
        Tooltip(self.listbox, TIP["giong_mau"])
        ttk.Button(left, text="↻ Tải lại danh sách",
                   command=self._reload_voices).grid(row=1, column=0, columnspan=2,
                                                     sticky="ew", pady=(8, 0))

        right = ttk.Frame(body)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(4, weight=1)      # ô Nhật ký co giãn, các khối khác giữ nguyên

        # ── ② Văn bản thử: ≈N giây đầu kịch bản mới nhất (07/11/2026) ──
        vb, self.txt, self.lbl_van_ban = self._build_van_ban(right)
        vb.grid(row=0, column=0, sticky="ew")

        # ── nút tạo ──
        actions = ttk.Frame(right)
        actions.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.btn_make = ttk.Button(actions, text="🔊  Tạo & nghe giọng đã chọn",
                                   style="Accent.TButton", command=self._on_make_one)
        self.btn_make.pack(side="left")
        Tooltip(self.btn_make, TIP["tao"])
        self.btn_all = ttk.Button(actions, text="🔁  Tạo cho TẤT CẢ giọng",
                                  command=self._on_make_all)
        self.btn_all.pack(side="left", padx=(8, 0))
        Tooltip(self.btn_all, TIP["tao_tat_ca"])
        ttk.Button(actions, text="📁  Kết quả", command=self._open_out).pack(side="right")

        # ── 🎧 Hàng NGHE: mẫu gốc · clone · mẫu → clone · bài thật (= 🎧 web) · dừng ──
        nghe = ttk.Frame(right)
        nghe.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        ttk.Label(nghe, text="🎧  Nghe:", font=("Segoe UI Semibold", 10)).pack(side="left")
        self.btn_mau = ttk.Button(nghe, text="🎤  Giọng mẫu (gốc)", command=self._on_play_sample)
        self.btn_mau.pack(side="left", padx=(8, 0))
        Tooltip(self.btn_mau, TIP["nghe_mau"])
        self.btn_play = ttk.Button(nghe, text="▶  Giọng clone", command=self._on_play_saved)
        self.btn_play.pack(side="left", padx=(8, 0))
        Tooltip(self.btn_play, TIP["nghe_clone"])
        self.btn_ab = ttk.Button(nghe, text="⇄  Mẫu → clone", command=self._on_play_ab)
        self.btn_ab.pack(side="left", padx=(8, 0))
        Tooltip(self.btn_ab, TIP["nghe_ab"])
        self.btn_bai_that = ttk.Button(nghe, text="🎧  Bài thật (30 s)", command=self._on_nghe_bai_that)
        self.btn_bai_that.pack(side="left", padx=(8, 0))
        Tooltip(self.btn_bai_that, TIP["nghe_bai_that"])
        self._btn_bai_that.append(self.btn_bai_that)
        self.btn_stop = ttk.Button(nghe, text="⏹  Dừng", command=self._stop_play)
        self.btn_stop.pack(side="left", padx=(8, 0))

        # ── ③ Cài đặt giọng = bài thật (khối "Cài đặt tạo giọng" của web) ──
        self._build_khoi_cai_dat(right).grid(row=3, column=0, sticky="ew", pady=(8, 0))

        # ── Nhật ký + trạng thái ──
        logf = ttk.LabelFrame(right, text="  Nhật ký  ", padding=6)
        logf.grid(row=4, column=0, sticky="nsew", pady=(8, 0))
        logf.rowconfigure(0, weight=1)
        logf.columnconfigure(0, weight=1)
        self.logbox = scrolledtext.ScrolledText(logf, height=4, wrap="word", state="disabled",
                                                font=("Consolas", 9), relief="flat", borderwidth=0,
                                                bg=UI["log_bg"], fg=UI["log_info"], padx=8, pady=6)
        self.logbox.grid(row=0, column=0, sticky="nsew")
        for tag, color in [("info", UI["log_info"]), ("warn", UI["log_warn"]),
                           ("err", UI["log_err"]), ("ok", UI["ok"])]:
            self.logbox.tag_config(tag, foreground=color)
        self.status = tk.StringVar(value="Sẵn sàng.")
        ttk.Label(right, textvariable=self.status, style="Muted.TLabel").grid(
            row=5, column=0, sticky="w", pady=(6, 2))
        self.pb = ttk.Progressbar(right, mode="determinate", maximum=100)
        self.pb.grid(row=6, column=0, sticky="ew", pady=(0, 8))   # lề đáy, không sát mép cửa sổ
        return page

    def _thanh(self, parent, row: int, col: int, nhan: str, var, lo, hi, step, get, set_, fmt,
               on_release, tip: str, reset=None, length: int = 150, key: str | None = None):
        """Một hàng thanh chỉnh kiểu chung cho ③: nhãn (tooltip) · − · thanh · + · số · ↺.
        `get()` / `set_(v)` đọc / đặt giá trị đã làm tròn (set_ tự gọi on_release),
        `fmt(v)` → chữ ô số, ↺ đặt về `reset` (None = không có nút). `key` → nhãn số đăng ký vào
        self._nhan[key] để kéo thanh ở trang này thì số ở mọi trang đổi theo (biến tk dùng chung
        chỉ kéo thanh kia đi, không gọi command của nó). Trả nhãn số."""
        f = ttk.Frame(parent)
        f.grid(row=row, column=col, sticky="ew", pady=(4, 0), padx=(0, 10) if col == 0 else 0)
        lb = ttk.Label(f, text=nhan, width=18)
        lb.pack(side="left")
        Tooltip(lb, tip)
        ttk.Button(f, text="−", width=2, style="Nho.TButton",
                   command=lambda: set_(get() - step)).pack(side="left")
        lbl = ttk.Label(f, text=fmt(get()), width=8, font=("Segoe UI Semibold", 10))
        nhoms = self._nhan.setdefault(key, []) if key else []
        nhoms.append(lbl)
        sc = ttk.Scale(f, from_=lo, to=hi, length=length, orient="horizontal", variable=var,
                       command=lambda _v: [l.config(text=fmt(get())) for l in nhoms])
        sc.pack(side="left", padx=4)
        sc.bind("<ButtonRelease-1>", on_release)
        ttk.Button(f, text="+", width=2, style="Nho.TButton",
                   command=lambda: set_(get() + step)).pack(side="left")
        lbl.pack(side="left", padx=(6, 0))
        if reset is not None:
            ttk.Button(f, text="↺", width=2, style="Nho.TButton",
                       command=lambda: set_(reset)).pack(side="left", padx=(2, 0))
        return lbl

    def _build_khoi_cai_dat(self, parent) -> ttk.LabelFrame:
        """Khối ③ Cài đặt giọng (= khối "Cài đặt tạo giọng" của web): 🔗 đồng bộ · ↻ lấy từ bài thật ·
        🎚 mẫu giọng · hai cột thanh (🎵 tông | ⏩ tốc độ · 🔔 vang trường độ | cường độ · 🧒 thiếu niên |
        🔆 sáng giọng · 🔊 âm lượng | 🔉 chuẩn âm). Gắn biến tk tạo ở __init__; nhãn chữ đăng ký vào
        self._nhan để _update_* / _cap_nhat_mau / _dat_nhan cập nhật. Trả LabelFrame — trang tự grid/pack."""
        cd = ttk.LabelFrame(parent, text="  ③ Cài đặt giọng — dùng chung với bài thật (taogiong_options.json)  ",
                            padding=(10, 6))
        cd.columnconfigure(0, weight=1, uniform="cot")
        cd.columnconfigure(1, weight=1, uniform="cot")

        sync_row = ttk.Frame(cd)
        sync_row.grid(row=0, column=0, columnspan=2, sticky="ew")
        cb = ttk.Checkbutton(sync_row, text="🔗 Đồng bộ với bài thật", variable=self.var_sync,
                             command=self._on_sync_toggle)
        cb.pack(side="left")
        Tooltip(cb, TIP["dong_bo"])
        b = ttk.Button(sync_row, text="↻ Lấy từ bài thật", style="Nho.TButton", command=self._lay_bai_that)
        b.pack(side="left", padx=(10, 0))
        Tooltip(b, TIP["lay_bai_that"])
        if self._nhan.get("sync"):                       # trang thứ hai: chép dòng trạng thái đang có
            chu = self._nhan["sync"][0].cget("text")
        elif self.var_sync.get():
            chu = "🔗 đang ở mức bài thật: " + mo_ta_thong_so(**self._da_luu)
        else:
            chu = "tắt đồng bộ: chỉnh ở đây không đụng bài thật"
        lbl_sync = ttk.Label(sync_row, style="Muted.TLabel", wraplength=560, justify="left", text=chu)
        lbl_sync.pack(side="left", padx=(12, 0))
        self._nhan.setdefault("sync", []).append(lbl_sync)

        # 🎚 Mẫu giọng (bảng hu.MAU_GIONG chung GUI/web): bấm = đặt 5 ô + phát ngay bản clone.
        mau_row = ttk.Frame(cd)
        mau_row.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        lb = ttk.Label(mau_row, text="🎚 Mẫu giọng:", width=18)
        lb.pack(side="left")
        Tooltip(lb, TIP["mau_giong"])
        for ten in hu.mau_ten():
            r = ttk.Radiobutton(mau_row, text=ten, value=ten, variable=self.var_mau, command=self._ap_mau)
            r.pack(side="left", padx=(6, 0))
            Tooltip(r, hu.MAU_MO_TA.get(ten, ""))
        lbl_mau = ttk.Label(cd, text="", style="Muted.TLabel", wraplength=880, justify="left")
        lbl_mau.grid(row=2, column=0, columnspan=2, sticky="w", padx=(4, 0))
        self._nhan.setdefault("mau", []).append(lbl_mau)

        # Hai cột thanh chỉnh: tông | tốc độ · vang trường độ | vang cường độ ·
        # thiếu niên | sáng giọng · âm lượng | chuẩn âm.
        self._thanh(cd, 3, 0, "🎵 Tông giọng:", self.var_pitch, PITCH_MIN, PITCH_MAX, PITCH_STEP,
                    self._pitch, self._set_pitch, fmt_pitch, self._on_pitch_release, TIP["pitch"],
                    reset=0.0, key="pitch")
        self._thanh(cd, 3, 1, "⏩ Tốc độ:", self.var_speed, SPEED_MIN, SPEED_MAX, SPEED_STEP,
                    self._speed, self._set_speed, lambda v: f"{v:.2f}×", self._on_speed_release,
                    TIP["speed"], reset=1.0, key="speed")
        for (r, c), key, nhan in (((4, 0), "vang_truong_do", "🔔 Vang trường độ:"),
                                  ((4, 1), "vang_cuong_do", "🔔 Vang cường độ:"),
                                  ((5, 0), "thieu_nien", "🧒 Thiếu niên:"),
                                  ((5, 1), "sang_giong", "🔆 Sáng giọng:")):
            self._thanh(cd, r, c, nhan, self.var_fx[key], hu.FX_MIN, hu.FX_MAX, 5,
                        (lambda k=key: self._fx()[k]), (lambda v, k=key: self._set_fx(**{k: v})),
                        lambda v: str(int(v)), self._on_fx_release, TIP[key], reset=0, key="fx:" + key)
        self._thanh(cd, 6, 0, "🔊 Âm lượng:", self.var_am_luong, hu.AMLUONG_MIN, hu.AMLUONG_MAX,
                    AMLUONG_STEP, self._am_luong, self._set_am_luong, fmt_am_luong,
                    self._on_am_luong_release, TIP["am_luong"], reset=0.0, key="am_luong")
        self._cap_nhat_mau()          # radio 🎚 sáng đúng mẫu đang lưu (hoặc không cái nào)
        return cd

    def _build_van_ban(self, parent, height: int = 5):
        """Khối ② Văn bản thử cho một trang: nhãn nguồn · ô "≈ giây" (biến chung) · ↻ · ✎ · ô chữ.
        Đăng ký (ô chữ, nhãn) vào self._o_van_ban để _nap_van_ban / ✎ điền MỌI trang cùng lúc (một
        văn bản thử cho cả app). Trả (LabelFrame, Text, Label) — trang tự grid/pack."""
        vb = ttk.LabelFrame(parent, text=f"  ② Văn bản thử — ≈ {VAN_BAN_GIAY} s đầu kịch bản mới nhất  ",
                            padding=(10, 6))
        vb.columnconfigure(0, weight=1)
        hdr = ttk.Frame(vb)
        hdr.grid(row=0, column=0, sticky="ew")
        lbl = ttk.Label(hdr, text="📄 …", style="Muted.TLabel")
        lbl.pack(side="left")
        b = ttk.Button(hdr, text="✎ Câu mẫu", style="Nho.TButton", command=self._van_ban_mau_san)
        b.pack(side="right")
        Tooltip(b, TIP["cau_mau"])
        b = ttk.Button(hdr, text="↻ Lấy lại", style="Nho.TButton",
                       command=lambda: self._nap_van_ban(bao=True))
        b.pack(side="right", padx=(0, 6))
        Tooltip(b, TIP["lay_lai"])
        sp = ttk.Spinbox(hdr, from_=VAN_BAN_GIAY_MIN, to=VAN_BAN_GIAY_MAX, increment=5,
                         textvariable=self.var_giay, width=4, command=self._on_giay_doi)
        sp.pack(side="right", padx=(0, 10))
        sp.bind("<Return>", lambda _e: self._on_giay_doi())
        Tooltip(sp, TIP["van_ban_giay"])
        ttk.Label(hdr, text="≈ giây:").pack(side="right", padx=(0, 4))
        txt = tk.Text(vb, height=height, wrap="word", font=("Segoe UI", 11),
                      bg=UI["field"], fg=UI["fg"], relief="flat", borderwidth=0,
                      highlightthickness=1, highlightbackground=UI["border"],
                      highlightcolor=UI["accent"], padx=10, pady=8)
        txt.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self._o_van_ban.append((txt, lbl))
        return vb, txt, lbl

    def _dat_nhan(self, key: str, text: str):
        """Đặt chữ cho nhãn `key` ở MỌI trang (xem _nhan)."""
        for lb in self._nhan.get(key, ()):
            lb.config(text=text)

    # Nhãn của trang OmniVoice theo tên cũ (test + chỗ gọi cũ); mọi trang cập nhật qua _dat_nhan.
    lbl_pitch = property(lambda self: self._nhan["pitch"][0])
    lbl_speed = property(lambda self: self._nhan["speed"][0])
    lbl_am_luong = property(lambda self: self._nhan["am_luong"][0])
    lbl_sync = property(lambda self: self._nhan["sync"][0])
    lbl_mau = property(lambda self: self._nhan["mau"][0])
    lbl_fx = property(lambda self: {k: self._nhan["fx:" + k][0] for k in FX_KEYS})

    # ── Nhật ký / dòng trạng thái của trang (chỉ còn một trang từ 09/11/2026) ──
    def _kenh(self, trang: str | None = None):
        """(hàm ghi Nhật ký, biến dòng trạng thái). `trang` giữ để chỗ gọi cũ không đổi; hàm log
        chỉ đẩy vào self.q nên gọi được từ luồng nền."""
        return self._log, self.status

    def _log_trang(self, msg, level="info"):
        self._kenh()[0](msg, level)

    def _status_var(self):
        return self._kenh()[1]

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

    # ── ② văn bản thử = ≈N giây đầu kịch bản mới nhất (07/11/2026) ──
    @staticmethod
    def _kep_giay(v) -> int:
        """Ô "≈ giây": số nguyên trong [VAN_BAN_GIAY_MIN, VAN_BAN_GIAY_MAX]; rác → VAN_BAN_GIAY."""
        try:
            g = int(round(float(str(v).replace(",", ".").strip())))
        except (TypeError, ValueError):
            g = VAN_BAN_GIAY
        return max(VAN_BAN_GIAY_MIN, min(VAN_BAN_GIAY_MAX, g))

    def _giay(self) -> int:
        g = self._kep_giay(self.var_giay.get())
        self.var_giay.set(str(g))
        return g

    def _on_giay_doi(self):
        """Quay ô / Enter: nhớ số giây rồi lấy lại văn bản theo số mới."""
        save_settings(van_ban_giay=self._giay())
        self._nap_van_ban(bao=False)

    def _dat_van_ban(self, text: str, nhan: str):
        """Điền MỌI ô văn bản thử đã đăng ký cùng một chữ + nhãn nguồn."""
        for txt, lbl in self._o_van_ban:
            txt.delete("1.0", "end")
            txt.insert("1.0", text)
            lbl.config(text=nhan)

    def _van_ban_mau_san(self):
        """✎: về câu mẫu cố định (DEFAULT_SCRIPT)."""
        self._dat_van_ban(DEFAULT_SCRIPT, "✎ câu mẫu sẵn · sửa tay được")

    def _nap_van_ban(self, bao: bool = False):
        """Điền ô văn bản = ≈N giây đầu kịch bản mới nhất (kich_ban_moi_nhat + van_ban_dau);
        kịch_bản/ chưa có tập nào có input, hoặc đọc lỗi → câu mẫu sẵn (báo ở Nhật ký khi
        `bao`). Ghi đè chữ đang sửa — chỉ gọi lúc mở app, bấm ↻ hay đổi ô giây."""
        giay = self._giay()
        try:
            tap = kich_ban_moi_nhat()
            if tap is None:
                raise FileNotFoundError("kịch_bản/ chưa có tập nào có input.docx / input.txt")
            text = inputdocx.strip_marks(inputdocx.read_input_text(inputdocx.input_for(tap)))
            van_ban, tt = van_ban_dau(text, giay)
            if not van_ban.strip():
                raise ValueError(f"kịch bản {tap.name} trống")
        except Exception as e:
            self._dat_van_ban(DEFAULT_SCRIPT, f"✎ câu mẫu sẵn ({e})")
            if bao:
                self._log_trang(f"ℹ️ Văn bản thử: dùng câu mẫu sẵn — {e}.", "warn")
            return
        so = tts.episode_of(tap.name) or tap.name
        self._dat_van_ban(van_ban, f"📄 tập {so} · {tt['so_cau']} câu · ≈{tt['giay']:.0f} s"
                          + (" (cả bài)" if tt["het"] else "") + " · sửa tay được")
        if bao:
            self._log_trang(f"📄 Văn bản thử: ≈{tt['giay']:.0f} s đầu ({tt['so_cau']} câu) kịch bản mới nhất "
                      f"— {tap.name}.")

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
                elif kind == "call":                       # hàm cần chạy trên thread Tk
                    payload()
                elif kind == "done":
                    self._set_busy(False)
                    play = payload
                    if play and Path(play).exists():
                        self._play_file(Path(play), trang="omni")   # bản clone vừa tạo → báo ở trang OmniVoice
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
        parts = tts._balance_chunk_levels(parts, self._sr)   # cân tương đối, giữ mức gốc
        merged = tts._join_with_pauses(parts, chunks, self._sr)
        tail = np.zeros(int(tts.TAIL_SILENCE_SEC * self._sr), dtype="float32")
        return np.concatenate([merged, tail])

    def _save(self, out: Path, audio) -> None:
        """Ghi wav THÔ (07/11/2026): 🔊 âm lượng áp lúc PHÁT trong _render_file, cùng chỗ với tông / bộ lọc /
        tốc độ, để bật/tắt là nghe ngay như nút 🎧 bên web. File này tương ứng "audio gốc
        chưa hậu kỳ" (output_chunks ghép lại) của bài thật."""
        sf.write(str(out), audio, self._sr)

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
        self._dat_nhan("speed", f"{self._speed():.2f}×")

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
        """Mức đang chọn trên các ô ③ — cùng dạng bai_that_doc() (speed, pitch, fx, am_luong)."""
        return dict(speed=self._speed(), pitch=self._pitch(), fx=self._fx(),
                    am_luong=self._am_luong())

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
        self._dat_nhan("sync", "✓ đã lưu vào bài thật: " + mo_ta_thong_so(**ts))

    def _lay_bai_that(self):
        """↻: kéo mọi ô ③ về đúng mức taogiong_options.json đang lưu (GUI/web vừa đổi thì
        bấm nút này). Không ghi ngược lại; đang phát thì phát lại cho nghe."""
        bt = bai_that_doc()
        self._da_luu = dict(bt)
        self.var_speed.set(bt["speed"])
        self.var_pitch.set(bt["pitch"])
        for k, v in bt["fx"].items():
            self.var_fx[k].set(v)
        self.var_am_luong.set(bt["am_luong"])
        self._update_speed_label()
        self._update_pitch_label()
        self._update_fx_labels()
        self._update_am_luong_label()
        self._cap_nhat_mau()
        self._dat_nhan("sync", "↻ đã lấy từ bài thật: " + mo_ta_thong_so(**bt))
        self._replay_if_playing()

    def _on_sync_toggle(self):
        """Tick 🔗: đẩy ngay mức đang chọn sang bài thật; bỏ tick: từ giờ chỉnh tự do."""
        save_settings(dong_bo=bool(self.var_sync.get()))
        if self.var_sync.get():
            self._da_luu = None
            self._luu_bai_that()
            if self._da_luu is None:      # không có gì để ghi (lỗi) → vẫn báo trạng thái
                self._dat_nhan("sync", "🔗 đang đồng bộ với bài thật")
        else:
            self._dat_nhan("sync", "tắt đồng bộ: chỉnh ở đây không đụng bài thật")

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
        if not self._nhan.get("mau"):
            return
        ten = hu.mau_khop(self._pitch(), self._fx())
        self.var_mau.set(ten)
        self._dat_nhan("mau", hu.MAU_MO_TA.get(ten, "bộ số riêng — bấm một mẫu để điền lại"))

    # ── tông giọng nghe thử ──
    def _pitch(self) -> float:
        """Số bán cung đang chọn, đã làm tròn về bội của PITCH_STEP (0.5, 1.0, 1.5...)."""
        v = round(self.var_pitch.get() / PITCH_STEP) * PITCH_STEP
        return round(min(PITCH_MAX, max(PITCH_MIN, v)), 1)

    def _update_pitch_label(self):
        self._dat_nhan("pitch", fmt_pitch(self._pitch()))

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
    # ── 🔊 âm lượng (07/11/2026, cùng khoá am_luong_db với GUI/web) ──
    def _am_luong(self) -> float:
        """Mức 🔊 đang chọn (dB), làm tròn 0,5 và kẹp như hu.parse_amluong."""
        return hu.parse_amluong(self.var_am_luong.get())

    def _update_am_luong_label(self):
        self._dat_nhan("am_luong", fmt_am_luong(self._am_luong()))

    def _set_am_luong(self, value: float):
        self.var_am_luong.set(max(hu.AMLUONG_MIN, min(hu.AMLUONG_MAX, value)))
        self._update_am_luong_label()
        self._on_am_luong_release()

    def _on_am_luong_release(self, _e=None):
        """Nhả chuột / bấm ±: lưu (🔗) rồi nếu đang phát thì phát lại ở mức mới."""
        self._update_am_luong_label()
        self._luu_bai_that()
        self._replay_if_playing()

    def _fx(self) -> dict:
        """4 mức bộ lọc đang chọn (int 0–100) — cùng dạng dict mà bài thật nhận."""
        return {k: hu.parse_fx(v.get()) for k, v in self.var_fx.items()}

    def _update_fx_labels(self):
        for k, v in self._fx().items():
            self._dat_nhan("fx:" + k, str(v))

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
        """Kéo thanh lúc đang phát → phát lại ngay với mức mới: bản CLONE thì dựng lại từ file
        thô, mẫu 🎧 BÀI THẬT thì dựng lại mẫu (như web: đổi ô là dựng + phát lại). Đang phát
        GIỌNG MẪU gốc thì thôi — mẫu luôn nguyên bản, thanh chỉnh không áp lên nó."""
        if self._last_raw:
            return
        if not self._is_playing():
            return
        if self._last_bai_that:
            self._on_nghe_bai_that()
            return
        if self._last_src and self._last_src.exists():
            # bản có chữ mở đầu riêng thì giữ; bản clone gọi y như cũ (không thêm tham số)
            kw = {} if self._last_nhan == NHAN_CLONE else dict(nhan=self._last_nhan)
            self._play_file(self._last_src, **kw)

    def _is_playing(self) -> bool:
        """winsound không báo khi phát xong → ước lượng bằng độ dài file."""
        return self._playing and time.monotonic() < self._play_until

    def _render_file(self, src: Path, speed: float, pitch: float, fx: dict | None = None,
                     am_luong: float = 0.0) -> Path:
        """Bản phát của `src` theo đúng thứ tự bài thật: tốc độ (giữ cao độ) + tông (giữ tốc
        độ) + bộ lọc (một lượt ffmpeg) → 🔊 âm lượng (chuẩn âm −14 LUFS gỡ hẳn 10/11/2026).
        Cache ở SPEED_DIR theo cả bộ số, dùng lại nếu còn mới hơn `src`; tông 0,
        không bộ lọc / âm lượng thì tên y như trước (`...@1.05x.wav`) nên cache
        tốc độ cũ vẫn dùng được. Không có gì để áp → trả chính `src`. Gọi được từ luồng nền
        (tên file tạm riêng theo tiến trình + luồng)."""
        src = Path(src)
        fx = hu.fx_from(fx)
        am_luong = hu.parse_amluong(am_luong)
        if (abs(speed - 1.0) <= 1e-6 and abs(pitch) <= 1e-9 and not hu.fx_active(**fx)
                and abs(am_luong) <= 1e-9):
            return src
        cache = SPEED_DIR
        cache.mkdir(parents=True, exist_ok=True)
        tag = (f"@{speed:.2f}x" + (f"{pitch:+.1f}st" if abs(pitch) > 1e-9 else "")
               + hu.fx_tag(**fx)
               + (f"_am{am_luong:+.1f}" if abs(am_luong) > 1e-9 else ""))
        dst = cache / f"{src.stem}{tag}.wav"
        if dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
            return dst
        rieng = f".{os.getpid()}_{threading.get_ident()}"
        tam = cache / f"{dst.stem}{rieng}.tmp.wav"
        try:
            args, sr, _ = hu.build_ffmpeg_args(src, speed, pitch, None, **fx)
            proc = subprocess.run(
                [FFMPEG, "-y", "-loglevel", "error", *args, "-ar", str(sr), "-c:a", "pcm_s16le", str(tam)],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                creationflags=CREATE_NO_WINDOW)
            if proc.returncode != 0 or not tam.exists():
                raise RuntimeError((proc.stderr or "ffmpeg lỗi không rõ").strip()[-300:])
            hu.apply_amluong_file(tam, am_luong)
            os.replace(tam, dst)
        finally:
            tam.unlink(missing_ok=True)
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

    def _play_file(self, path: Path, nhan: str = NHAN_CLONE, trang: str | None = None):
        """Phát `path` (bản clone THÔ) theo đủ các ô ③: tốc độ, tông,
        bộ lọc, 🔉 chuẩn âm, 🔊 âm lượng — dựng ở luồng nền (_render_file; có chuẩn âm thì ffmpeg mất
        1–3 s) rồi phát; file gốc không bị sửa. Trong lúc dựng coi như "đang phát" để kéo thanh tiếp
        là dựng lại theo mức mới; kết quả lượt cũ về sau bị bỏ (token). `nhan` mở đầu dòng trạng
        thái; `trang` = trang nhận trạng thái / Nhật ký (None = trang đang mở)."""
        self._stop_play()
        self._last_src, self._last_raw, self._last_bai_that, self._last_nhan = path, False, False, nhan
        ts = self._thong_so()
        log, sv = self._kenh(trang)
        self._render_token += 1
        token = self._render_token
        self._playing, self._play_until = True, time.monotonic() + 120
        sv.set(f"🎚️ Đang áp {mo_ta_thong_so(**ts)}...")

        def work():
            out, err = path, None
            try:
                out = self._render_file(path, **ts)
            except Exception as e:
                err = e
            self.q.put(("call", lambda: self._phat_sau_dung(token, path, out, err, ts, nhan, log, sv)))
        threading.Thread(target=work, daemon=True).start()

    def _phat_sau_dung(self, token: int, path: Path, out: Path, err, ts: dict,
                       nhan: str = NHAN_CLONE, log=None, sv=None):
        """Về luồng Tk sau khi dựng xong: còn đúng lượt thì phát (lỗi → phát bản gốc)."""
        if token != self._render_token:
            return
        if err is not None:
            (log or self._log)(f"⚠️ Không áp được thanh chỉnh ({err}) → phát bản gốc.", "warn")
            out, mo_ta = path, "bản gốc, chưa áp gì"
        else:
            mo_ta = mo_ta_thong_so(**ts)
        self._play_wav(out, lambda d: f"{nhan}: {path.name}  ({mo_ta}, {d:.1f}s)", sv)

    # ── 🎧 BÀI THẬT (30 s) = nút 🎧 Nghe thử của web (07/11/2026) ──
    def _on_nghe_bai_that(self):
        """Áp bộ số đang chọn lên mẫu ~30 s giọng gốc của tập đầu đợt kịch bản mới nhất
        (taogiong_nghethu.nghe_thu: cùng hàm, cùng thứ tự với bài thật) rồi phát; tốc độ
        áp thêm qua _render_file (mẫu đã có tông/bộ lọc nên chỉ còn tốc độ). Dựng ở luồng
        nền; đang phát mà kéo thanh thì _replay_if_playing gọi lại hàm này. Nút có ở cả hai
        trang (self._btn_bai_that) — khoá hết lúc dựng; báo về trang bấm nút."""
        self._stop_play()
        ts = self._thong_so()
        log, sv = self._kenh()
        self._last_src, self._last_raw, self._last_bai_that = None, False, True
        self._render_token += 1
        token = self._render_token
        self._playing, self._play_until = True, time.monotonic() + 120
        sv.set("🎧 Đang dựng bản nghe thử bài thật...")
        for b in self._btn_bai_that:
            b.config(state="disabled")

        def work():
            kq, out, err = None, None, None
            try:
                kq = nt.nghe_thu(pitch=ts["pitch"], fx=ts["fx"], am_luong=ts["am_luong"], log=log)
                out = Path(kq["file"])
                if abs(ts["speed"] - 1.0) > 1e-6:
                    out = self._render_file(out, ts["speed"], 0.0, None)
            except Exception as e:
                err = e
            self.q.put(("call", lambda: self._phat_bai_that(token, kq, out, err, ts, log, sv)))
        threading.Thread(target=work, daemon=True).start()

    def _phat_bai_that(self, token: int, kq, out, err, ts: dict, log=None, sv=None):
        log, sv = log or self._log, sv or self.status
        for b in self._btn_bai_that:
            b.config(state="normal")
        if token != self._render_token:
            return
        if err is not None:
            self._playing = False
            log(f"⚠️ Nghe thử bài thật: {err}", "warn")
            sv.set(f"Không nghe thử được bài thật: {err}")
            return
        mau = kq["mau"]
        nhan = nt.nhan_mau(mau)
        log(f"🎧 Bài thật — {nhan} · {kq['mo_ta']}" + ("" if kq["moi"] else " (bản đã có)"))
        g = mau.get("giong") or {}
        if g.get("che_do") == "clone" and ts["fx"]["sang_giong"] != int(mau.get("sang_goc") or 0):
            log(f"ℹ️ Mẫu sinh lúc 🔆 Sáng giọng {int(mau.get('sang_goc') or 0)}; bài thật ở mức "
                f"{ts['fx']['sang_giong']} còn EQ cả giọng mẫu nên sẽ khác đôi chút.")
        self._play_wav(out, lambda d: (
            f"🎧 Đang phát bản nghe thử BÀI THẬT — {nhan}  ({ts['speed']:.2f}×, {kq['mo_ta']}, {d:.1f}s)"), sv)

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
            self._log_trang(f"ℹ️ Phát mẫu GỐC. Bài thật đang để 🔆 {sang} nên dựng prompt từ mẫu đã EQ "
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

    def _play_wav(self, play_path: Path, status_of, sv=None) -> float:
        """Phát wav `play_path` bằng winsound (không chặn); `status_of(giây)` → dòng trạng
        thái ghi vào `sv` (None = dòng trạng thái của trang đang mở). Trả thời lượng ước lượng
        để _is_playing / ⇄ biết lúc nào xong (winsound không báo khi phát hết)."""
        try:
            duration = sf.info(str(play_path)).duration
        except Exception:
            duration = 0.0
        try:
            import winsound
            winsound.PlaySound(str(play_path), winsound.SND_FILENAME | winsound.SND_ASYNC)
            self._playing = True
            self._play_until = time.monotonic() + duration + 0.3
            (sv or self._status_var()).set(status_of(duration))
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
        self._render_token += 1      # lượt dựng bản phát (clone / bài thật) đang chạy → kết quả về bị bỏ
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
            app._nha_model()
        except Exception:
            pass
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", _thoat)
    root.mainloop()


if __name__ == "__main__":
    main()
