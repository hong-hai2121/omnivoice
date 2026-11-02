# -*- coding: utf-8 -*-
"""
thu_giong.py — Thử nhanh các giọng mẫu trong thư mục voice/.

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
phát file gốc trong voice/ NGUYÊN BẢN (không qua thanh chỉnh; mp3/wav lạ được đổi
sang wav 16-bit tạm ở _thu_giong/_giongmau/ vì winsound chỉ phát wav PCM),
▶ GIỌNG CLONE phát bản thử theo thanh chỉnh (như trước), ⇄ MẪU → CLONE phát mẫu
xong tự phát tiếp bản clone; ⏹ Dừng cắt cả chuỗi.

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

import re
import json
import logging
import queue
import shutil
import subprocess
import threading
import time
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

import numpy as np
import soundfile as sf

VOICE_DIR = Path(_HERE)                       # thư mục chứa giọng mẫu = chính thư mục này
OUT_DIR = VOICE_DIR / "_thu_giong"            # nơi lưu audio nghe thử
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

UI = dict(
    bg="#ffffff", fg="#1f2430", muted="#7b828f",
    accent="#e84393", accent_dk="#c92f7b",
    field="#ffffff", border="#e4e7ec", hover="#f1f3f6",
    log_bg="#fbfbfc", log_info="#475063", log_warn="#b07400", log_err="#d62828", ok="#1f9d55",
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
    voice/). Giữ nguyên tên gốc kèm đuôi rồi thêm .wav — xem MAU_DIR."""
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
        self._center(root, 1100, 830)
        root.minsize(900, 730)

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
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
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
        pad = dict(padx=16)
        ttk.Label(self.root, text="🎚️  Thử giọng — chọn giọng + kịch bản mẫu để nghe",
                  style="Title.TLabel").pack(anchor="w", pady=(14, 2), **pad)
        ttk.Label(self.root, text="Tạo audio clone ngắn để so sánh xem giọng nào hợp; 🎧 nghe lại "
                                  "giọng mẫu gốc để đối chiếu clone với người thật. "
                                  "Kết quả lưu ở voice/_thu_giong/.",
                  style="Muted.TLabel").pack(anchor="w", pady=(0, 10), **pad)

        body = ttk.Frame(self.root)
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
        self.txt = tk.Text(right, height=5, wrap="word", font=("Segoe UI", 11),
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
        ttk.Label(nghe, text="mẫu = file gốc trong voice/, không qua thanh chỉnh  •  clone = bản thử theo thanh chỉnh",
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
        # và web); 🔗 bật thì ghi luôn vào bài thật. Kéo thanh lệch mẫu → nhãn thành
        # "Tuỳ chỉnh". Sáng giọng đổi mức thì phải bấm Tạo lại mới nghe đúng (prompt
        # dựng từ giọng mẫu đã EQ), các mức khác đổi là nghe ngay.
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
        self.pb.grid(row=13, column=0, sticky="ew")

        logf = ttk.LabelFrame(right, text="  Nhật ký  ", padding=6)
        logf.grid(row=11, column=0, sticky="nsew", pady=(10, 6))
        logf.rowconfigure(0, weight=1)
        logf.columnconfigure(0, weight=1)
        self.logbox = scrolledtext.ScrolledText(logf, height=7, wrap="word", state="disabled",
                                                font=("Consolas", 9), relief="flat", borderwidth=0,
                                                bg=UI["log_bg"], fg=UI["log_info"], padx=8, pady=6)
        self.logbox.grid(row=0, column=0, sticky="nsew")
        for tag, color in [("info", UI["log_info"]), ("warn", UI["log_warn"]),
                           ("err", UI["log_err"]), ("ok", UI["ok"])]:
            self.logbox.tag_config(tag, foreground=color)

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
        parts = tts._balance_chunk_levels(parts, self._sr)
        merged = tts._join_with_pauses(parts, chunks, self._sr)
        tail = np.zeros(int(tts.TAIL_SILENCE_SEC * self._sr), dtype="float32")
        return np.concatenate([merged, tail])

    def _save(self, out: Path, audio) -> None:
        """Ghi wav rồi chuẩn độ to y hệt bài thật (nén nhẹ SPEECH_COMPRESSOR +
        loudnorm về VOICE_LUFS) — so giọng mà bản to bản nhỏ thì tai nghiêng về
        bản to, so sánh không công bằng."""
        sf.write(str(out), audio, self._sr)
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
        """Bấm một mẫu: đặt tông + 4 bộ lọc theo bảng rồi đi đúng đường nhả chuột
        (lưu vào bài thật nếu 🔗, phát lại nếu đang phát) — một lượt cho cả 5 số."""
        ts = hu.mau_thong_so(self.var_mau.get())
        if ts is None:
            return
        sang_cu = self._fx()["sang_giong"]
        self.var_pitch.set(ts["pitch"])
        for k, v in ts["fx"].items():
            self.var_fx[k].set(v)
        self._update_pitch_label()
        self._on_fx_release()
        if ts["fx"]["sang_giong"] != sang_cu:
            self._log(f"ℹ️ Mẫu '{self.var_mau.get()}' đổi mức sáng giọng {sang_cu} → "
                      f"{ts['fx']['sang_giong']}: bấm '🔊 Tạo & nghe' để dựng lại (prompt từ "
                      "giọng mẫu đã EQ); tông/vang/thiếu niên thì nghe ngay.", "warn")

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
    def _clone_file(self, voice: str) -> Path | None:
        """Bản thử (clone) của `voice` ứng với mức 🔆 đang chọn. Chưa có bản mức này
        nhưng có bản mức 0 thì lùi về đó (báo rõ); chưa có gì → hộp thoại, trả None."""
        sang = self._fx()["sang_giong"]
        f = out_file(voice, sang)
        if not f.exists() and sang and out_file(voice, 0).exists():
            # Chưa có bản dựng với giọng mẫu EQ mức này → phát bản mẫu gốc + EQ output
            # cho nghe tạm, nhưng nói rõ: bài thật còn EQ cả giọng mẫu.
            self._log(f"ℹ️ Chưa có bản thử dựng với giọng mẫu EQ mức {sang} → phát bản mẫu "
                      "gốc + EQ output. Bấm '🔊 Tạo & nghe' để nghe đúng như bài thật.", "warn")
            f = out_file(voice, 0)
        if not f.exists():
            messagebox.showinfo("Chưa có bản thử",
                                f"Chưa tạo bản thử cho '{voice}'.\nBấm '🔊 Tạo & nghe' trước.")
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
        """Phát file giọng mẫu gốc trong voice/ NGUYÊN BẢN (không tốc độ / tông / bộ lọc).
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
        try:
            os.startfile(str(OUT_DIR))  # type: ignore[attr-defined]
        except Exception:
            self.status.set(f"Thư mục kết quả: {OUT_DIR}")


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
