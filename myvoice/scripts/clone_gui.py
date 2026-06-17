"""
Giao diện desktop cho Voice Cloning — chạy: python clone_gui.py
"""

import sys, os
# Gốc repo OmniVoice (chứa package omnivoice + venv) — lùi 2 cấp từ myvoice/scripts/
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
_VENV_PYTHON = os.path.join(_REPO_ROOT, "venv", "Scripts", "python.exe")
if os.path.exists(_VENV_PYTHON) and os.path.abspath(sys.executable) != os.path.abspath(_VENV_PYTHON):
    import subprocess
    subprocess.run([_VENV_PYTHON] + sys.argv)
    sys.exit()
# Để import được package omnivoice ở gốc repo dù chạy từ thư mục con
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
# Để import được frame_video.py nằm cùng thư mục scripts/
_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import re
import hashlib
import threading
import logging
import queue
import numpy as np
import soundfile as sf
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
from pathlib import Path


BASE_DIR   = Path(__file__).resolve().parent.parent   # myvoice/
VOICE_DIR  = BASE_DIR / "voice"
SCRIPT_DIR = BASE_DIR / "kịch_bản"
OUTPUT_DIR = SCRIPT_DIR / "output"                    # nơi gom mọi kết quả (wav + video + chunks)
FAV_FILE   = BASE_DIR / "voice_favorites.json"        # danh sách giọng mẫu yêu thích
AUDIO_EXTS = {".mp3", ".wav", ".MP3", ".WAV", ".flac", ".FLAC"}
STAR       = "★ "                                     # tiền tố hiển thị cho giọng yêu thích

# Kho hiệu ứng phủ lên video (scripts/hieuung/) — thường là .mov có alpha
EFFECTS_DIR = Path(__file__).resolve().parent / "hieuung"
EFFECT_EXTS = {".mov", ".mp4", ".webm", ".mkv", ".avi", ".gif"}
EFFECT_NONE = "Không (mặc định)"                       # mục "không thêm hiệu ứng"

# ── BẢNG MÀU GIAO DIỆN (nền trắng) ───────────────────────────────────────────
UI = dict(
    bg="#ffffff", card="#ffffff", border="#e4e7ec", field="#ffffff",
    fg="#1f2430", muted="#7b828f",
    accent="#e84393", accent_dk="#c92f7b", accent_soft="#f4c4dc",
    track="#edeff2", hover="#f1f3f6", press="#e6e9ee",
    log_bg="#fbfbfc", log_info="#475063", log_warn="#b07400", log_err="#d62828",
)

SCRIPT_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# Tự chuyển input.txt cũ từ voice/ sang kịch_bản/ nếu chưa có
_old_input = VOICE_DIR / "input.txt"
_new_input = SCRIPT_DIR / "input.txt"
if not _new_input.exists():
    if _old_input.exists():
        _new_input.write_bytes(_old_input.read_bytes())
    else:
        _new_input.write_text("", encoding="utf-8")


def list_voice_files():
    if not VOICE_DIR.exists():
        return []
    return sorted(f.name for f in VOICE_DIR.iterdir() if f.suffix in AUDIO_EXTS)


def list_effect_files():
    """Danh sách file hiệu ứng trong scripts/hieuung/ (chỉ tên file)."""
    if not EFFECTS_DIR.exists():
        return []
    return sorted(f.name for f in EFFECTS_DIR.iterdir()
                  if f.is_file() and f.suffix.lower() in EFFECT_EXTS)


def strip_star(label: str) -> str:
    """Bỏ tiền tố ★ để lấy lại tên file thật từ chuỗi hiển thị trong combobox."""
    return label[len(STAR):] if label.startswith(STAR) else label


def load_favorites() -> set:
    try:
        import json
        return set(json.loads(FAV_FILE.read_text(encoding="utf-8")))
    except Exception:
        return set()


def save_favorites(favorites: set):
    import json
    try:
        FAV_FILE.write_text(
            json.dumps(sorted(favorites), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        logging.warning(f"Không lưu được danh sách yêu thích: {e}")


# ── QUEUE ĐỂ TRUYỀN LOG TỪ THREAD VỀ GUI ───────────────────────────────────
log_queue = queue.Queue()


class QueueHandler(logging.Handler):
    def emit(self, record):
        log_queue.put((record.levelno, self.format(record)))


# ── LOGIC CLONE ──────────────────────────────────────────────────────────────
# ── PHÁT HIỆN SPIKE ──────────────────────────────────────────────────────────
_SPIKE_RATIO  = 5.0   # khung vượt N× median RMS → spike
_SILENT_RMS   = 0.005 # median quá thấp = gần im lặng
_FRAME_MS     = 50    # độ dài mỗi khung phân tích (ms)


def detect_spike(path: Path, sr: int) -> list[float]:
    """Trả về danh sách thời điểm (giây) bị spike, rỗng nếu OK."""
    data, _ = sf.read(str(path), dtype="float32", always_2d=False)
    if data.ndim > 1:
        data = data.mean(axis=1)
    frame = int(sr * _FRAME_MS / 1000)
    frames = [data[i:i+frame] for i in range(0, len(data) - frame, frame)]
    if not frames:
        return [0.0]
    rms = np.array([np.sqrt(np.mean(f**2)) for f in frames])
    median = float(np.median(rms))
    if median < _SILENT_RMS:
        return [0.0]
    threshold = _SPIKE_RATIO * max(median, 1e-4)
    bad = np.where(rms > threshold)[0]
    return [round(float(t) * _FRAME_MS / 1000, 2) for t in bad]


# ── TÁCH LOGIC GENERATE 1 CHUNK ───────────────────────────────────────────────
def _generate_chunk(model, mode, voice_param, chunk):
    if mode == "clone":
        return model.generate(text=chunk, ref_audio=voice_param)
    elif mode == "design":
        return model.generate(text=chunk, instruct=voice_param)
    return model.generate(text=chunk)


SPLIT_CHARS = re.compile(r'(?<=[.!?。！？\n])\s*')

# Ký tự thay bằng khoảng trắng (tránh ghép từ)
_REPLACE_WITH_SPACE = re.compile(r'[—–\-]+')
# Ký tự xóa hoàn toàn
_REMOVE = re.compile(r'["""\'\'\'`~@#$%^&*_+=|\\<>\[\]{}]')
# Dấu ba chấm → dấu chấm
_ELLIPSIS = re.compile(r'…+|\.{2,}')
# Nhiều khoảng trắng → 1
_SPACES = re.compile(r'[ \t]+')


def clean_text(text: str) -> str:
    text = _ELLIPSIS.sub('.', text)
    text = _REPLACE_WITH_SPACE.sub(' ', text)
    text = _REMOVE.sub('', text)
    text = _SPACES.sub(' ', text)
    return text.strip()


def split_chunks(text: str, max_len: int):
    parts = SPLIT_CHARS.split(text)
    chunks, current = [], ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if len(current) + len(part) + 1 <= max_len:
            current = (current + " " + part).strip()
        else:
            if current:
                chunks.append(current)
            current = part
    if current:
        chunks.append(current)
    return chunks


def chunks_dir_for(output_path: Path) -> Path:
    """Thư mục chunks dùng chung cho mọi bản đánh số (output, output1, output2…).

    Bỏ phần số đuôi của tên file để các lần chạy ghi vào CÙNG một thư mục
    (output_chunks), tránh tạo output1_chunks, output2_chunks… mỗi lần và
    giữ được khả năng tái dùng/“resume” chunk đã tạo.
    """
    stem = output_path.stem
    base = re.match(r"^(.*?)(\d*)$", stem).group(1) or stem
    return output_path.parent / (base + "_chunks")


def unique_path(path: Path) -> Path:
    """Nếu file đã tồn tại, trả về tên mới tăng số: output.wav → output1.wav → output2.wav…"""
    if not path.exists():
        return path
    m = re.match(r"^(.*?)(\d*)$", path.stem)
    base = m.group(1)
    n = int(m.group(2)) + 1 if m.group(2) else 1
    while True:
        cand = path.with_name(f"{base}{n}{path.suffix}")
        if not cand.exists():
            return cand
        n += 1


def run_tts(mode, voice_param, chunks, output, progress_var, status_var, btn_run, btn_pause, btn_preview, pause_event, make_video=False, effect=None):
    import torch
    from omnivoice.models.omnivoice import OmniVoice
    from omnivoice.utils.common import get_best_device

    try:
        total = len(chunks)
        output_path = Path(output)
        tmp_dir = chunks_dir_for(output_path)
        tmp_dir.mkdir(parents=True, exist_ok=True)

        # Chữ ký cấu hình (giọng/chế độ/văn bản). Nếu khác lần trước → xóa chunk
        # cũ để tạo lại, tránh ghép nhầm giọng/đoạn của lần chạy trước.
        sig = hashlib.sha1("|".join([mode, str(voice_param), *chunks])
                           .encode("utf-8")).hexdigest()
        sig_file = tmp_dir / "_signature.txt"
        old_sig = sig_file.read_text(encoding="utf-8").strip() if sig_file.exists() else None
        if old_sig != sig:
            stale = list(tmp_dir.glob("*.wav"))
            for w in stale:
                w.unlink()
            if stale:
                logging.warning(
                    f"Cấu hình đổi (giọng/chế độ/văn bản) → xóa {len(stale)} "
                    "chunk cũ, tạo lại từ đầu."
                )
            sig_file.write_text(sig, encoding="utf-8")

        logging.info(f"Tổng {total} đoạn — tải model...")
        status_var.set("Đang tải model...")

        device = get_best_device()
        model = OmniVoice.from_pretrained(
            "k2-fsa/OmniVoice", device_map=device, dtype=torch.float16
        )
        sr = model.sampling_rate

        for i, chunk in enumerate(chunks):
            # Chờ nếu đang tạm dừng
            if not pause_event.is_set():
                status_var.set(f"⏸  Đã tạm dừng (đoạn {i+1}/{total})")
                logging.info("Tạm dừng...")
                pause_event.wait()
                status_var.set(f"Đoạn {i+1}/{total}...")
                logging.info("Tiếp tục.")

            tmp_file = tmp_dir / f"{i:04d}.wav"
            pct = int((i / total) * 100)
            progress_var.set(pct)
            status_var.set(f"Đoạn {i+1}/{total}...")

            if tmp_file.exists() and tmp_file.stat().st_size > 4096:
                logging.info(f"[{i+1}/{total}] bỏ qua (đã có)")
                continue
            elif tmp_file.exists():
                logging.warning(f"[{i+1}/{total}] file cũ bị lỗi/cụt → generate lại")
                tmp_file.unlink()

            logging.info(f"[{i+1}/{total}] {chunk[:60]!r}")
            result = _generate_chunk(model, mode, voice_param, chunk)
            sf.write(str(tmp_file), result[0], sr)

        # ── KIỂM TRA SPIKE SAU KHI GENERATE XONG ────────────────────────────
        status_var.set("Kiểm tra chất lượng audio...")
        logging.info("Kiểm tra spike toàn bộ chunks...")
        bad_chunks = []
        for i in range(total):
            f = tmp_dir / f"{i:04d}.wav"
            spikes = detect_spike(f, sr)
            if spikes:
                bad_chunks.append(i)
                logging.warning(f"  [SPIKE] {f.name} tại {spikes[:3]}s → render lại")

        if bad_chunks:
            logging.info(f"Render lại {len(bad_chunks)} chunk lỗi: {bad_chunks}")
            for idx, i in enumerate(bad_chunks):
                status_var.set(f"Render lại chunk lỗi {idx+1}/{len(bad_chunks)}...")
                tmp_file = tmp_dir / f"{i:04d}.wav"
                tmp_file.unlink(missing_ok=True)
                result = _generate_chunk(model, mode, voice_param, chunks[i])
                sf.write(str(tmp_file), result[0], sr)
                logging.info(f"  [{i:04d}] render lại xong")
        else:
            logging.info("Không phát hiện spike — tất cả chunk OK.")

        status_var.set("Đang ghép file...")
        logging.info("Ghép tất cả đoạn...")
        parts = [
            sf.read(str(tmp_dir / f"{i:04d}.wav"), dtype="float32")[0]
            for i in range(total)
        ]

        # Crossfade ngắn giữa các chunk để tránh click/vấp tại ranh giới
        fade = min(256, min(len(p) for p in parts) // 2)
        fade_in  = np.linspace(0, 1, fade, dtype="float32")
        fade_out = np.linspace(1, 0, fade, dtype="float32")
        merged = parts[0].copy()
        merged[-fade:] *= fade_out
        for p in parts[1:]:
            p = p.copy()
            p[:fade] *= fade_in
            merged[-fade:] += p[:fade]
            merged = np.concatenate([merged, p[fade:]])

        sf.write(output, merged, sr)
        progress_var.set(100)
        status_var.set(f"Xong!  →  {output}")
        logging.info(f"Đã lưu → {output}")
        btn_preview.config(state="normal")   # cho phép nghe thử kết quả

        # ── TỰ DỰNG VIDEO TỪ AUDIO VỪA TẠO (nếu bật) ───────────────────────
        if make_video:
            status_var.set("Đang dựng video...")
            logging.info("Bắt đầu dựng video từ audio vừa tạo...")
            try:
                from frame_video import build_video
                video_out = build_video(Path(output), log=logging.info, effect=effect)
                status_var.set(f"Xong! Video → {video_out}")
                logging.info(f"Đã tạo video → {video_out}")
            except Exception as e:
                logging.error(f"Lỗi dựng video: {e}")
                status_var.set(f"Audio xong, lỗi dựng video: {e}")

    except Exception as e:
        logging.error(f"Lỗi: {e}")
        status_var.set(f"Lỗi: {e}")
    finally:
        pause_event.set()
        btn_run.config(state="normal")
        btn_pause.config(state="disabled", text="⏸  Tạm dừng")


# ── GIAO DIỆN ────────────────────────────────────────────────────────────────
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("OmniVoice TTS")
        self.resizable(True, True)
        self.configure(bg=UI["bg"])
        self._apply_theme()
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._playing = False
        self._preview_after = None
        self._last_output = None
        self._favorites = load_favorites()
        self._setup_logging()
        self._build_ui()
        self._poll_log()
        self.update_idletasks()
        self.minsize(880, 600)
        self._center(1000, 660)

    def _apply_theme(self):
        """Theme nền trắng, phẳng, hiện đại (dựa trên 'clam' để tùy biến màu)."""
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        C = UI
        base_font  = ("Segoe UI", 10)
        small_font = ("Segoe UI", 8)

        st.configure(".", background=C["bg"], foreground=C["fg"],
                     font=base_font, bordercolor=C["border"],
                     focuscolor=C["bg"], troughcolor=C["track"])
        st.configure("TFrame", background=C["bg"])
        st.configure("TLabel", background=C["bg"], foreground=C["fg"])
        st.configure("Header.TLabel", font=("Segoe UI", 19, "bold"),
                     foreground=C["fg"])
        st.configure("Brand.TLabel", font=("Segoe UI", 19, "bold"),
                     foreground=C["accent"])
        st.configure("Sub.TLabel", font=("Segoe UI", 9), foreground=C["muted"])
        st.configure("Hint.TLabel", font=small_font, foreground=C["muted"])

        # Khung "thẻ" có viền nhẹ
        st.configure("TLabelframe", background=C["card"], bordercolor=C["border"],
                     relief="solid", borderwidth=1, padding=10)
        st.configure("TLabelframe.Label", background=C["card"],
                     foreground=C["accent"], font=("Segoe UI", 10, "bold"))

        # Nhập liệu
        for w in ("TEntry", "TSpinbox"):
            st.configure(w, fieldbackground=C["field"], background=C["field"],
                         bordercolor=C["border"], lightcolor=C["border"],
                         darkcolor=C["border"], insertcolor=C["fg"], padding=5)
            st.map(w, bordercolor=[("focus", C["accent"])],
                   lightcolor=[("focus", C["accent"])])
        st.configure("TSpinbox", arrowcolor=C["muted"])

        st.configure("TCombobox", fieldbackground=C["field"], background=C["field"],
                     bordercolor=C["border"], lightcolor=C["border"],
                     darkcolor=C["border"], arrowcolor=C["muted"], padding=5)
        st.map("TCombobox",
               fieldbackground=[("readonly", C["field"])],
               foreground=[("readonly", C["fg"])],
               selectbackground=[("readonly", C["field"])],
               selectforeground=[("readonly", C["fg"])],
               bordercolor=[("focus", C["accent"])],
               lightcolor=[("focus", C["accent"])])
        # Danh sách xổ xuống của combobox
        self.option_add("*TCombobox*Listbox.background", C["field"])
        self.option_add("*TCombobox*Listbox.foreground", C["fg"])
        self.option_add("*TCombobox*Listbox.selectBackground", C["accent"])
        self.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
        self.option_add("*TCombobox*Listbox.font", base_font)

        # Radio
        st.configure("TRadiobutton", background=C["card"], foreground=C["fg"])
        st.map("TRadiobutton",
               background=[("active", C["card"])],
               foreground=[("active", C["accent"]), ("selected", C["accent"])],
               indicatorcolor=[("selected", C["accent"]), ("!selected", "#cfd3da")])

        # Checkbox
        st.configure("TCheckbutton", background=C["card"], foreground=C["fg"])
        st.map("TCheckbutton",
               background=[("active", C["card"])],
               foreground=[("active", C["accent"]), ("selected", C["accent"])],
               indicatorcolor=[("selected", C["accent"]), ("!selected", "#cfd3da")])

        # Nút phụ (xám nhạt) + nút chính (nhấn hồng)
        st.configure("TButton", background="#eef0f3", foreground=C["fg"],
                     bordercolor=C["border"], relief="flat",
                     focusthickness=0, padding=(14, 8), font=base_font)
        st.map("TButton",
               background=[("active", C["hover"]), ("pressed", C["press"]),
                           ("disabled", "#f4f5f7")],
               foreground=[("disabled", "#aeb4be")])
        st.configure("Accent.TButton", background=C["accent"], foreground="#ffffff",
                     padding=(20, 9), font=("Segoe UI", 10, "bold"))
        st.map("Accent.TButton",
               background=[("active", C["accent_dk"]), ("pressed", C["accent_dk"]),
                           ("disabled", C["accent_soft"])],
               foreground=[("disabled", "#ffffff")])

        # Thanh tiến trình
        st.configure("TProgressbar", background=C["accent"],
                     troughcolor=C["track"], bordercolor=C["track"],
                     lightcolor=C["accent"], darkcolor=C["accent"], thickness=12)

    def _center(self, w, h):
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x, y = (sw - w) // 2, (sh - h) // 3
        self.geometry(f"{w}x{h}+{max(x,0)}+{max(y,0)}")

    def _setup_logging(self):
        handler = QueueHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%H:%M:%S"))
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(logging.INFO)

    def _build_ui(self):
        C = UI
        root = ttk.Frame(self, padding=18)
        root.grid(sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        # Cột trái (điều khiển) cố định, cột phải (log) mở rộng
        root.columnconfigure(0, weight=0, minsize=470)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        # ════════════════════════════════════════════════
        # CỘT TRÁI — toàn bộ điều khiển
        # ════════════════════════════════════════════════
        left = ttk.Frame(root)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        left.columnconfigure(0, weight=1)

        # ── Header ──
        hdr = ttk.Frame(left)
        hdr.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        title = ttk.Frame(hdr)
        title.pack(anchor="w")
        ttk.Label(title, text="🎧", style="Header.TLabel").pack(side="left", padx=(0, 8))
        ttk.Label(title, text="OmniVoice", style="Header.TLabel").pack(side="left")
        ttk.Label(title, text="TTS", style="Brand.TLabel").pack(side="left", padx=(6, 0))
        ttk.Label(hdr, text="Chuyển văn bản thành giọng nói — Clone · Thiết kế · Mặc định",
                  style="Sub.TLabel").pack(anchor="w", pady=(2, 0))

        # ── Chế độ ──
        sec_mode = ttk.LabelFrame(left, text="  Chế độ  ")
        sec_mode.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        sec_mode.columnconfigure(0, weight=1)

        self.var_mode = tk.StringVar(value="clone")
        mode_row = ttk.Frame(sec_mode)
        mode_row.grid(row=0, column=0, sticky="w")
        for label, val, desc in [
            ("🎙  Clone",   "clone",   "Nhái giọng mẫu"),
            ("🎨  Thiết kế", "design",  "Mô tả giọng"),
            ("🔊  Mặc định", "default", "Model tự chọn"),
        ]:
            f = ttk.Frame(mode_row)
            f.pack(side="left", padx=(0, 18))
            ttk.Radiobutton(f, text=label, variable=self.var_mode,
                            value=val, command=self._on_mode_change).pack(anchor="w")
            ttk.Label(f, text=desc, style="Hint.TLabel").pack(anchor="w", padx=22)

        ttk.Separator(sec_mode, orient="horizontal").grid(
            row=1, column=0, sticky="ew", pady=10)

        self.voice_frame = ttk.Frame(sec_mode)
        self.voice_frame.grid(row=2, column=0, sticky="ew")

        # Clone
        self.frm_clone = ttk.Frame(self.voice_frame)
        ttk.Label(self.frm_clone, text="Giọng mẫu:", width=11, anchor="w").pack(side="left", padx=(0, 6))
        self.var_ref = tk.StringVar()
        self.cb_ref = ttk.Combobox(self.frm_clone, textvariable=self.var_ref,
                                   values=[], width=30, state="readonly")
        self.cb_ref.pack(side="left")
        self.cb_ref.bind("<<ComboboxSelected>>", lambda e: self._update_fav_button())
        self.btn_fav = ttk.Button(self.frm_clone, text="☆", width=3,
                                  command=self._toggle_favorite)
        self.btn_fav.pack(side="left", padx=(6, 0))
        ttk.Button(self.frm_clone, text="↻", width=3,
                   command=self._refresh_voices).pack(side="left", padx=(6, 0))
        self._reload_voice_combo()   # nạp danh sách (yêu thích ★ lên đầu) + chọn mục đầu

        # Design
        self.frm_design = ttk.Frame(self.voice_frame)
        lang_row = ttk.Frame(self.frm_design)
        lang_row.pack(anchor="w", pady=(0, 4))
        ttk.Label(lang_row, text="Ngôn ngữ:").pack(side="left", padx=(0, 8))
        self.var_lang = tk.StringVar(value="en")
        ttk.Radiobutton(lang_row, text="English", variable=self.var_lang,
                        value="en", command=self._on_lang_change).pack(side="left", padx=4)
        ttk.Radiobutton(lang_row, text="中文", variable=self.var_lang,
                        value="zh", command=self._on_lang_change).pack(side="left", padx=4)
        self.design_attr_frame = ttk.Frame(self.frm_design)
        self.design_attr_frame.pack(anchor="w", fill="x")
        res_row = ttk.Frame(self.frm_design)
        res_row.pack(anchor="w", fill="x", pady=(6, 0))
        ttk.Label(res_row, text="Lệnh model:").pack(side="left", padx=(0, 8))
        self.var_instruct = tk.StringVar(value="female, young adult")
        ttk.Entry(res_row, textvariable=self.var_instruct, width=36).pack(side="left", fill="x", expand=True)

        self._design_vars: list[tk.StringVar] = []
        self._design_sep = ", "
        self._build_design_dropdowns()

        # Default
        self.frm_default = ttk.Frame(self.voice_frame)
        ttk.Label(self.frm_default, text="Model tự động chọn giọng phù hợp với văn bản",
                  style="Sub.TLabel").pack(side="left", padx=2)

        self._on_mode_change()

        # ── Tệp ──
        sec_file = ttk.LabelFrame(left, text="  Tệp  ")
        sec_file.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        sec_file.columnconfigure(1, weight=1)

        for r, (lbl, attr, default, is_save) in enumerate([
            ("Văn bản (.txt):", "var_txt", str(SCRIPT_DIR / "input.txt"),  False),
            ("Kết quả (.wav):", "var_out", str(OUTPUT_DIR / "output.wav"), True),
        ]):
            ttk.Label(sec_file, text=lbl, width=14, anchor="w").grid(
                row=r, column=0, sticky="w", padx=(0, 8), pady=4)
            var = tk.StringVar(value=default)
            setattr(self, attr, var)
            ttk.Entry(sec_file, textvariable=var).grid(
                row=r, column=1, sticky="ew", pady=4)
            cmd = (lambda v=var: self._pick_save(v, [("WAV", "*.wav")])) if is_save \
                else (lambda v=var: self._pick_file(v, [("Text", "*.txt")]))
            ttk.Button(sec_file, text="Chọn…", width=8, command=cmd).grid(
                row=r, column=2, padx=(8, 0), pady=4)

        # ── Cài đặt ──
        sec_opt = ttk.LabelFrame(left, text="  Cài đặt  ")
        sec_opt.grid(row=3, column=0, sticky="ew", pady=(0, 12))

        chunk_row = ttk.Frame(sec_opt)
        chunk_row.pack(anchor="w", fill="x")
        ttk.Label(chunk_row, text="Độ dài đoạn (ký tự):").pack(side="left", padx=(0, 8))
        self.var_chunk = tk.IntVar(value=300)
        ttk.Spinbox(chunk_row, from_=100, to=1000, increment=50,
                    textvariable=self.var_chunk, width=7).pack(side="left")
        ttk.Label(chunk_row, text="nhỏ hơn = nhẹ RAM GPU hơn",
                  style="Hint.TLabel").pack(side="left", padx=8)

        video_row = ttk.Frame(sec_opt)
        video_row.pack(anchor="w", fill="x", pady=(8, 0))
        self.var_make_video = tk.BooleanVar(value=True)
        ttk.Checkbutton(video_row, text="🎬  Tự dựng video sau khi tạo audio",
                        variable=self.var_make_video).pack(side="left")
        ttk.Label(video_row, text="(ghép video nền + khung)",
                  style="Hint.TLabel").pack(side="left", padx=8)

        # Hiệu ứng phủ lên toàn bộ video (từ đầu đến cuối) — lấy từ scripts/hieuung/
        fx_row = ttk.Frame(sec_opt)
        fx_row.pack(anchor="w", fill="x", pady=(8, 0))
        ttk.Label(fx_row, text="✨  Hiệu ứng:").pack(side="left", padx=(0, 8))
        self.var_effect = tk.StringVar(value=EFFECT_NONE)
        self.cb_effect = ttk.Combobox(fx_row, textvariable=self.var_effect,
                                      values=[EFFECT_NONE] + list_effect_files(),
                                      width=26, state="readonly")
        self.cb_effect.pack(side="left")
        ttk.Button(fx_row, text="↻", width=3,
                   command=self._refresh_effects).pack(side="left", padx=(6, 0))
        ttk.Label(fx_row, text="(phủ lên toàn video)",
                  style="Hint.TLabel").pack(side="left", padx=8)

        # ── Hành động ──
        act = ttk.Frame(left)
        act.grid(row=4, column=0, sticky="ew", pady=(2, 12))
        self.btn_run = ttk.Button(act, text="▶  Chạy", command=self._start,
                                  style="Accent.TButton")
        self.btn_run.pack(side="left", padx=(0, 8))
        self.btn_pause = ttk.Button(act, text="⏸  Tạm dừng", command=self._toggle_pause,
                                    state="disabled")
        self.btn_pause.pack(side="left", padx=(0, 8))
        self.btn_preview = ttk.Button(act, text="🔊  Nghe thử", command=self._toggle_preview,
                                      state="disabled")
        self.btn_preview.pack(side="left", padx=(0, 8))
        ttk.Button(act, text="🗑  Xóa output", command=self._clear_output).pack(side="left")

        # ── Tiến trình ──
        prog_frame = ttk.Frame(left)
        prog_frame.grid(row=5, column=0, sticky="ew")
        prog_frame.columnconfigure(0, weight=1)
        self.progress = tk.IntVar(value=0)
        self.progress_bar = ttk.Progressbar(prog_frame, variable=self.progress,
                                            maximum=100, mode="determinate")
        self.progress_bar.grid(row=0, column=0, sticky="ew")
        self.status = tk.StringVar(value="Sẵn sàng.")
        ttk.Label(prog_frame, textvariable=self.status,
                  style="Sub.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))

        # ════════════════════════════════════════════════
        # CỘT PHẢI — Log (mở rộng theo chiều ngang)
        # ════════════════════════════════════════════════
        log_frame = ttk.LabelFrame(root, text="  Nhật ký  ")
        log_frame.grid(row=0, column=1, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log_box = scrolledtext.ScrolledText(
            log_frame, width=58, height=30, state="disabled",
            font=("Consolas", 9), relief="flat", borderwidth=0,
            background=C["log_bg"], foreground=C["log_info"],
            insertbackground=C["fg"], selectbackground=C["accent_soft"],
            padx=10, pady=8, wrap="word",
        )
        self.log_box.grid(row=0, column=0, sticky="nsew")
        self.log_box.tag_config("info", foreground=C["log_info"])
        self.log_box.tag_config("warn", foreground=C["log_warn"])
        self.log_box.tag_config("err", foreground=C["log_err"])

    def _build_design_dropdowns(self):
        for w in self.design_attr_frame.winfo_children():
            w.destroy()
        self._design_vars.clear()
        self._design_maps: list[dict] = []

        NONE = "—"

        if self.var_lang.get() == "en":
            self._design_sep = ", "
            # (label_vi, [(hiển_thị_vi, giá_trị_model), ...])
            groups = [
                [
                    ("Giới tính", [(NONE,""), ("Nữ","female"), ("Nam","male")]),
                    ("Tuổi",      [(NONE,""), ("Trẻ em","child"), ("Thiếu niên","teenager"),
                                   ("Thanh niên","young adult"), ("Trung niên","middle-aged"),
                                   ("Cao tuổi","elderly")]),
                    ("Âm điệu",  [(NONE,""), ("Rất thấp","very low pitch"), ("Thấp","low pitch"),
                                   ("Vừa","moderate pitch"), ("Cao","high pitch"),
                                   ("Rất cao","very high pitch")]),
                    ("Đặc biệt", [(NONE,""), ("Thì thầm","whisper")]),
                ],
                [
                    ("Giọng vùng", [(NONE,""), ("Mỹ","american accent"), ("Úc","australian accent"),
                                    ("Anh","british accent"), ("Canada","canadian accent"),
                                    ("Trung Quốc","chinese accent"), ("Ấn Độ","indian accent"),
                                    ("Nhật Bản","japanese accent"), ("Hàn Quốc","korean accent"),
                                    ("Bồ Đào Nha","portuguese accent"), ("Nga","russian accent")]),
                ],
            ]
        else:
            self._design_sep = "，"
            groups = [
                [
                    ("Giới tính", [(NONE,""), ("Nữ","女"), ("Nam","男")]),
                    ("Tuổi",      [(NONE,""), ("Trẻ em","儿童"), ("Thiếu niên","少年"),
                                   ("Thanh niên","青年"), ("Trung niên","中年"), ("Cao tuổi","老年")]),
                    ("Âm điệu",  [(NONE,""), ("Rất thấp","极低音调"), ("Thấp","低音调"),
                                   ("Vừa","中音调"), ("Cao","高音调"), ("Rất cao","极高音调")]),
                    ("Đặc biệt", [(NONE,""), ("Thì thầm","耳语")]),
                ],
                [
                    ("Phương ngữ", [(NONE,""), ("Đông Bắc","东北话"), ("Vân Nam","云南话"),
                                    ("Tứ Xuyên","四川话"), ("Ninh Hạ","宁夏话"), ("Cam Túc","甘肃话"),
                                    ("Quế Lâm","桂林话"), ("Hà Nam","河南话"), ("Tế Nam","济南话"),
                                    ("Thiểm Tây","陕西话"), ("Thạch Gia Trang","石家庄话"),
                                    ("Quý Châu","贵州话"), ("Thanh Đảo","青岛话")]),
                ],
            ]

        for group in groups:
            row_f = ttk.Frame(self.design_attr_frame)
            row_f.pack(anchor="w", pady=3)
            for label, options in group:
                displays = [d for d, _ in options]
                mapping  = {d: v for d, v in options}
                cell = ttk.Frame(row_f)
                cell.pack(side="left", padx=(0, 14))
                ttk.Label(cell, text=label, font=("Segoe UI", 8)).pack(anchor="w")
                var = tk.StringVar(value=NONE)
                self._design_vars.append(var)
                self._design_maps.append(mapping)
                ttk.Combobox(cell, textvariable=var, values=displays,
                             width=17, state="readonly").pack()
                var.trace_add("write", lambda *_: self._update_instruct())

    def _on_lang_change(self):
        self._build_design_dropdowns()
        self._update_instruct()

    def _update_instruct(self):
        parts = []
        for var, mapping in zip(self._design_vars, self._design_maps):
            actual = mapping.get(var.get(), "")
            if actual:
                parts.append(actual)
        self.var_instruct.set(self._design_sep.join(parts))

    def _on_mode_change(self):
        for frm in (self.frm_clone, self.frm_design, self.frm_default):
            frm.pack_forget()
        {"clone":   self.frm_clone,
         "design":  self.frm_design,
         "default": self.frm_default}[self.var_mode.get()].pack(anchor="w")

    def _current_voice(self) -> str:
        """Tên file giọng mẫu thật đang chọn (đã bỏ tiền tố ★)."""
        return strip_star(self.var_ref.get())

    def _reload_voice_combo(self, keep: str | None = None):
        """Dựng lại danh sách giọng: yêu thích (★) lên đầu, còn lại theo a-z.

        keep = tên file thật muốn giữ chọn; mặc định giữ mục đang chọn.
        """
        files = list_voice_files()
        favs = [f for f in files if f in self._favorites]
        rest = [f for f in files if f not in self._favorites]
        ordered = favs + rest
        display = [(STAR + f if f in self._favorites else f) for f in ordered]
        self.cb_ref["values"] = display

        want = keep if keep is not None else self._current_voice()
        if want in ordered:
            self.var_ref.set(STAR + want if want in self._favorites else want)
        elif display:
            self.var_ref.set(display[0])
        else:
            self.var_ref.set("")
        self._update_fav_button()

    def _update_fav_button(self):
        fav = self._current_voice() in self._favorites
        self.btn_fav.config(text="★" if fav else "☆")

    def _toggle_favorite(self):
        name = self._current_voice()
        if not name:
            return
        if name in self._favorites:
            self._favorites.discard(name)
            logging.info(f"☆ Bỏ yêu thích: {name}")
        else:
            self._favorites.add(name)
            logging.info(f"★ Đã thêm yêu thích: {name}")
        save_favorites(self._favorites)
        self._reload_voice_combo(keep=name)

    def _refresh_voices(self):
        self._reload_voice_combo()
        logging.info(f"Tìm thấy {len(list_voice_files())} file giọng trong {VOICE_DIR}")

    def _refresh_effects(self):
        """Nạp lại danh sách hiệu ứng trong scripts/hieuung/."""
        cur = self.var_effect.get()
        effects = list_effect_files()
        self.cb_effect["values"] = [EFFECT_NONE] + effects
        if cur not in ([EFFECT_NONE] + effects):
            self.var_effect.set(EFFECT_NONE)
        logging.info(f"Tìm thấy {len(effects)} hiệu ứng trong {EFFECTS_DIR}")

    def _clear_output(self):
        """Xóa toàn bộ trong thư mục output (wav, video, và các thư mục chunks)."""
        import shutil
        if not OUTPUT_DIR.exists():
            messagebox.showinfo("Thông báo", "Chưa có thư mục output.")
            return
        items = list(OUTPUT_DIR.iterdir())
        if not items:
            messagebox.showinfo("Thông báo", "Thư mục output đã trống.")
            return
        n_files = sum(1 for p in items if p.is_file())
        n_dirs  = sum(1 for p in items if p.is_dir())
        if not messagebox.askyesno(
                "Xác nhận",
                f"Xóa TẤT CẢ trong:\n{OUTPUT_DIR}\n\n"
                f"({n_files} file + {n_dirs} thư mục — gồm wav, video, chunks)\n\n"
                "Không thể hoàn tác!"):
            return
        self._stop_preview()   # nhả file đang nghe (nếu có) để xóa được
        for p in items:
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.unlink(missing_ok=True)
        # Đặt lại tên kết quả về output.wav để đánh số lại từ đầu
        self.var_out.set(str(OUTPUT_DIR / "output.wav"))
        self._last_output = None
        self.btn_preview.config(state="disabled")
        logging.info(f"Đã xóa toàn bộ output trong {OUTPUT_DIR}")
        self.status.set("Đã xóa output.")

    def _pick_file(self, var, filetypes):
        path = filedialog.askopenfilename(filetypes=filetypes)
        if path:
            var.set(path)

    def _pick_save(self, var, filetypes):
        path = filedialog.asksaveasfilename(defaultextension=".wav", filetypes=filetypes)
        if path:
            var.set(path)

    def _start(self):
        mode = self.var_mode.get()
        if mode == "clone":
            voice_name = self._current_voice()
            if not voice_name:
                messagebox.showwarning("Thiếu giọng mẫu",
                                       f"Không tìm thấy file audio trong:\n{VOICE_DIR}")
                return
            voice_param = str(VOICE_DIR / voice_name)
        elif mode == "design":
            voice_param = self.var_instruct.get().strip()
            if not voice_param:
                messagebox.showwarning("Thiếu mô tả", "Vui lòng nhập mô tả giọng đọc.")
                return
        else:
            voice_param = None

        # ── Chia text ngay tại đây, trước khi khởi động thread ──────────────
        text_file = Path(self.var_txt.get())
        try:
            full_text = clean_text(text_file.read_text(encoding="utf-8"))
        except Exception as e:
            messagebox.showerror("Lỗi đọc file", str(e))
            return

        chunks = split_chunks(full_text.lower(), self.var_chunk.get())
        if not chunks:
            messagebox.showwarning("File trống", "File văn bản không có nội dung.")
            return

        preview_path = text_file.parent / (text_file.stem + "_preview.txt")
        if preview_path.exists():
            preview_path.unlink()
        preview_path.write_text("\n\n".join(chunks), encoding="utf-8")
        logging.info(f"Chia {len(chunks)} đoạn (chunk={self.var_chunk.get()} ký tự) → {preview_path.name}")

        # Nếu file kết quả đã tồn tại → tự đặt tên mới (output.wav → output1.wav …),
        # KHÔNG ghi đè bản cũ.
        out_path = unique_path(Path(self.var_out.get()))
        if str(out_path) != self.var_out.get():
            logging.info(f"File kết quả đã có → dùng tên mới: {out_path.name}")
            self.var_out.set(str(out_path))
            self.status.set(f"Kết quả sẽ lưu thành: {out_path.name}")
        self._last_output = self.var_out.get()

        self._stop_preview()                         # dừng audio đang nghe (nếu có)
        self.btn_preview.config(state="disabled")    # khóa tới khi tạo xong lần này
        self._pause_event = threading.Event()
        self._pause_event.set()
        self.btn_run.config(state="disabled")
        self.btn_pause.config(state="normal", text="⏸  Tạm dừng")
        # Hiệu ứng phủ video (nếu chọn) — chuyển thành đường dẫn đầy đủ
        effect_name = self.var_effect.get()
        effect_path = None
        if effect_name and effect_name != EFFECT_NONE:
            p = EFFECTS_DIR / effect_name
            effect_path = str(p) if p.exists() else None
            if effect_path:
                logging.info(f"Hiệu ứng phủ video: {effect_name}")

        self.progress.set(0)
        self.status.set(f"Đã chia {len(chunks)} đoạn — đang khởi động...")
        threading.Thread(
            target=run_tts,
            args=(mode, voice_param, chunks, self.var_out.get(),
                  self.progress, self.status,
                  self.btn_run, self.btn_pause, self.btn_preview, self._pause_event,
                  self.var_make_video.get(), effect_path),
            daemon=True,
        ).start()

    def _toggle_pause(self):
        if self._pause_event.is_set():
            self._pause_event.clear()
            self.btn_pause.config(text="▶  Tiếp tục")
        else:
            self._pause_event.set()
            self.btn_pause.config(text="⏸  Tạm dừng")

    # ── NGHE THỬ KẾT QUẢ ──────────────────────────────────────────────────────
    def _toggle_preview(self):
        if self._playing:
            self._stop_preview()
        else:
            self._play_preview()

    def _play_preview(self):
        path = Path(self._last_output or self.var_out.get())
        if not path.exists():
            messagebox.showinfo("Chưa có audio",
                                "Chưa có file kết quả để nghe. Hãy chạy tạo giọng trước.")
            return
        try:
            import winsound
            winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception:
            # Không phát nội bộ được → mở bằng trình phát mặc định của hệ thống
            try:
                os.startfile(str(path))  # type: ignore[attr-defined]
            except Exception as e:
                messagebox.showerror("Lỗi phát audio", str(e))
            return
        self._playing = True
        self.btn_preview.config(text="⏹  Dừng nghe")
        # Tự nhả nút khi nghe hết (winsound không báo kết thúc)
        try:
            dur = sf.info(str(path)).duration
            self._preview_after = self.after(int(dur * 1000) + 300, self._stop_preview)
        except Exception:
            self._preview_after = None

    def _stop_preview(self):
        try:
            import winsound
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass
        if self._preview_after is not None:
            try:
                self.after_cancel(self._preview_after)
            except Exception:
                pass
            self._preview_after = None
        self._playing = False
        self.btn_preview.config(text="🔊  Nghe thử")

    def _poll_log(self):
        while not log_queue.empty():
            levelno, msg = log_queue.get_nowait()
            tag = ("err" if levelno >= logging.ERROR
                   else "warn" if levelno >= logging.WARNING else "info")
            self.log_box.config(state="normal")
            self.log_box.insert("end", msg + "\n", tag)
            self.log_box.see("end")
            self.log_box.config(state="disabled")
        self.after(200, self._poll_log)


if __name__ == "__main__":
    App().mainloop()
