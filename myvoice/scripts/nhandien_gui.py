# -*- coding: utf-8 -*-
"""
Giao diện: dán link video (Bilibili/YouTube/TikTok...) → tự tải MP3 → nhận diện
giọng nói TIẾNG TRUNG thành văn bản.

Chạy:  python nhandien_gui.py
"""

import sys, os

# ── Tự chuyển sang python của venv (giống taogiong_gui.py) ──────────────────────
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
_VENV_PYTHON = os.path.join(_REPO_ROOT, "venv", "Scripts", "python.exe")
if __name__ == "__main__" and os.path.exists(_VENV_PYTHON) and \
        os.path.normcase(os.path.abspath(sys.executable)) != \
        os.path.normcase(os.path.abspath(_VENV_PYTHON)):
    import subprocess
    subprocess.run([_VENV_PYTHON] + sys.argv)
    sys.exit()

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import queue
import threading
import traceback
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
from pathlib import Path

# Tái dùng pipeline nhận diện đã viết sẵn
import nhandien_giongnoi as recog

# ── Cấu hình thư mục ─────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent          # myvoice/scripts/
DOWNLOAD_DIR = BASE_DIR / "downloads_zh"             # nơi lưu mp3 tải từ link
DOWNLOAD_DIR.mkdir(exist_ok=True)
# Thư mục kịch bản của dự án — nơi lưu file .docx kết quả nhận diện
KICHBAN_DIR = BASE_DIR.parent / "kịch_bản"
KICHBAN_DIR.mkdir(exist_ok=True)

# File .docx được nạp SẴN vào ô kết quả khi vừa mở GUI (đỡ phải nhận diện lại).
# Đây là kết quả tiếng Trung đã chỉnh tay; mở app lên là dùng được ngay/gửi Gemini.
DEFAULT_RESULT_DOCX = KICHBAN_DIR / "tiengTrung.docx"

MODELS = ["tiny", "base", "small", "medium", "large-v3"]
DEFAULT_MODEL = "medium"
# Tốc độ phát audio khi nhận diện (0.7 = chậm lại cho dễ bắt chữ với giọng đọc nhanh)
SPEEDS = ["0.6", "0.7", "0.8", "0.9", "1.0"]
DEFAULT_SPEED = "0.7"
PLACEHOLDER = "Chọn file hoặc dán đường dẫn file (mp3/mp4/wav...) — hoặc link video"

# Câu hướng dẫn MẶC ĐỊNH được chèn lên ĐẦU mỗi lần bấm "Sao chép kết quả".
# Người dùng có thể sửa ngay trên GUI (tab "Câu mở đầu"); bản đã sửa lưu ở PREFIX_FILE.
COPY_PREFIX = (
"Vào thẳng nội dung dịch, không viết câu mở đầu, lời chào, tiêu đề phụ hay bất kỳ văn bản dẫn nhập nào. "

"Bạn là người dịch truyện ngắn tiếng Trung sang tiếng Việt. "
"Hãy dịch sát nghĩa nhất có thể, giữ nguyên đầy đủ nội dung, tình tiết, nhân vật, quan hệ, diễn biến, cảm xúc và ý nghĩa gốc. "
"Không tự ý thêm tình tiết mới, không bớt nội dung, không biến đổi truyện thành câu chuyện khác. "
"Nếu gặp tiếng lóng, ẩn dụ, châm biếm, cách nói truyện mạng hoặc cụm từ có nghĩa hàm ý, hãy dịch theo nghĩa thực tế trong ngữ cảnh. "
"Nếu văn bản có lỗi do nhận diện giọng nói, lỗi chính tả, đồng âm, thiếu dấu câu, dính câu, sai tên riêng hoặc méo nghĩa, hãy tự khôi phục ý hợp lý theo mạch truyện, ngắt câu lại cho đúng rồi dịch. "
"hãy dịch sao cho người Việt dễ hiểu và nhất quán theo ngữ cảnh."
"Tên nhân vật, địa danh, quan hệ gia đình và xưng hô phải thống nhất trong toàn truyện. "
"Nếu cùng một nhân vật bị nhận diện thành nhiều tên khác nhau, hãy tự quy về một tên Việt hóa nhất quán. "
"Với món ăn, đồ vật, thành ngữ hoặc cách gọi đặc thù Trung Quốc, hãy dịch sao cho người Việt dễ hiểu; nếu cần có thể giữ tên gốc kèm giải thích ngắn, nhưng không dài dòng. "
"Nếu gặp câu quảng bá kênh, kêu gọi like, đăng ký, chia sẻ, tặng quà như “小薯条邀你一起看书咯”, “请点赞/订阅/转发/打赏”, “感谢支持”..., "
"hãy đổi tên kênh gốc thành “mimi Truyện” và dịch đúng ý, nhưng không để làm rối mạch truyện chính. "
"Ví dụ: “小薯条邀你一起看书咯” dịch là “Mimi Truyện xin mời bạn lắng nghe câu chuyện hôm nay nhé”. "
"Chỉ trả lời nội dung bản dịch tiếng Việt, không tự thêm lưu ý, chú thích hay nhận xét ngoài truyện."
)


# File lưu câu mở đầu do người dùng chỉnh (giữ lại giữa các lần mở app)
PREFIX_FILE = BASE_DIR / "copy_prefix.txt"


def load_prefix() -> str:
    """Đọc câu mở đầu đã lưu; chưa có thì trả về mặc định."""
    try:
        if PREFIX_FILE.exists():
            text = PREFIX_FILE.read_text(encoding="utf-8").strip()
            if text:
                return text
    except Exception:
        pass
    return COPY_PREFIX


def save_prefix(text: str) -> None:
    """Lưu câu mở đầu ra file để lần sau mở app vẫn còn."""
    try:
        PREFIX_FILE.write_text(text.strip(), encoding="utf-8")
    except Exception:
        pass


def read_docx_body(path) -> str:
    """Đọc NỘI DUNG (中文) từ file .docx do app xuất ra, BỎ các tiêu đề.

    File .docx có Heading 1 = tên file, Heading 2 = nhãn "ĐOẠN k (n ký tự)",
    Normal = đoạn văn thật. Chỉ lấy các đoạn KHÔNG phải heading rồi ghép lại
    (tiếng Trung không có dấu cách nên nối liền). Trả về "" nếu lỗi/rỗng.
    """
    try:
        from docx import Document
        doc = Document(str(path))
        parts = [p.text.strip() for p in doc.paragraphs
                 if not p.style.name.startswith("Heading") and p.text.strip()]
        return "".join(parts)
    except Exception:
        return ""

# ── Bảng màu (đồng bộ với taogiong_gui.py) ──────────────────────────────────────
UI = dict(
    bg="#ffffff", fg="#1f2430", muted="#7b828f",
    accent="#e84393", accent_dk="#c92f7b",
    field="#ffffff", border="#e4e7ec", hover="#f1f3f6",
    log_bg="#fbfbfc", log_info="#475063", log_warn="#b07400", log_err="#d62828", ok="#1f9d55",
)

# ── Queue truyền log + sự kiện live (segment/tiến độ) từ thread nền về GUI ────
log_queue: "queue.Queue[tuple[str, str]]" = queue.Queue()
ui_queue: "queue.Queue[tuple]" = queue.Queue()   # ("seg", text) | ("prog", fraction)

# Console THẬT (terminal VSCode) — giữ lại để vẫn in log ra terminal kể cả khi
# sys.stdout bị thay bằng _StdoutToLog trong thread nền.
_CONSOLE = sys.stdout


def _to_console(text: str) -> None:
    """In một dòng ra terminal VSCode (bỏ qua nếu chạy bằng pythonw, không có console)."""
    try:
        if _CONSOLE is not None:
            _CONSOLE.write(text.rstrip("\n") + "\n")
            _CONSOLE.flush()
    except Exception:
        pass


def log(msg, level="info"):
    text = str(msg)
    log_queue.put((level, text))
    _to_console(text)   # hiện log ra cả terminal VSCode


class _StdoutToLog:
    """Chuyển mọi print() trong thread nền vào ô log của GUI, đồng thời vẫn in ra
    terminal VSCode (mirror) để theo dõi tiến trình ở console."""
    def __init__(self, mirror=None):
        self._mirror = mirror
    def write(self, s):
        if self._mirror is not None:
            try:
                self._mirror.write(s)
                self._mirror.flush()
            except Exception:
                pass
        s = s.rstrip("\n")
        if s.strip():
            log_queue.put(("info", s))
    def flush(self):
        if self._mirror is not None:
            try:
                self._mirror.flush()
            except Exception:
                pass


# ── Tải audio bằng yt-dlp → trả về đường dẫn mp3 ─────────────────────────────
def download_mp3(url: str, out_dir: Path) -> str | None:
    try:
        import yt_dlp
    except ImportError:
        log("❌ Chưa cài yt-dlp. Chạy: pip install yt-dlp", "err")
        return None

    ffmpeg_dir = os.path.dirname(recog.FFMPEG_PATH) if recog.FFMPEG_PATH else None
    captured = {"path": None}

    def hook(d):
        if d.get("status") == "downloading":
            pct = d.get("_percent_str", "").strip()
            spd = d.get("_speed_str", "").strip()
            if pct:
                log(f"⬇️  Đang tải... {pct} {spd}")
        elif d.get("status") == "finished":
            log("✅ Tải xong, đang chuyển sang MP3...")

    ydl_opts = {
        "format": "bestaudio/best",
        # Dùng %(id)s để tránh tên file có ký tự đặc biệt / tiếng Trung
        "outtmpl": os.path.join(str(out_dir), "%(id)s.%(ext)s"),
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
        ],
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "progress_hooks": [hook],
    }
    if ffmpeg_dir:
        ydl_opts["ffmpeg_location"] = ffmpeg_dir

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", "")
            log(f"🎬 Tiêu đề: {title}")
            base = ydl.prepare_filename(info)
            mp3_path = os.path.splitext(base)[0] + ".mp3"
            if os.path.exists(mp3_path):
                captured["path"] = mp3_path
    except Exception as e:
        log(f"❌ Lỗi khi tải video: {e}", "err")
        return None

    if not captured["path"] or not os.path.exists(captured["path"]):
        # Phòng khi prepare_filename không khớp: tìm file mp3 mới nhất trong out_dir
        mp3s = sorted(out_dir.glob("*.mp3"), key=lambda p: p.stat().st_mtime, reverse=True)
        if mp3s:
            captured["path"] = str(mp3s[0])
    return captured["path"]


# ── Worker: (tải nếu là link) + nhận diện (chạy trong thread) ────────────────
def worker(source: str, model_name: str, speed: float, on_seg, on_prog, on_done):
    old_stdout = sys.stdout
    sys.stdout = _StdoutToLog(mirror=old_stdout)
    transcript = None
    try:
        source = source.strip().strip('"').strip("'")
        log(f"📦 Model: {model_name}  •  Tốc độ: {speed}x")

        # 1) File có sẵn trên máy → dùng trực tiếp, KHÔNG tải
        if os.path.isfile(source):
            media_path = source
            log(f"📁 File local: {media_path}")
        # 2) Là link → tải audio về bằng yt-dlp
        elif source.lower().startswith(("http://", "https://")):
            log(f"🌐 Bắt đầu tải từ link:\n{source}")
            media_path = download_mp3(source, DOWNLOAD_DIR)
            if not media_path:
                log("❌ Không tải được audio. Dừng.", "err")
                return
            log(f"🎵 File MP3: {media_path}")
        else:
            log("❌ Không phải file hợp lệ cũng không phải link http.", "err")
            return

        log("📝 Đang nhận diện giọng nói tiếng Trung (lần đầu sẽ tải model)...")
        partial = os.path.splitext(media_path)[0] + "_zh.partial.txt"
        transcript = recog.transcribe_chinese(
            media_path, model_name=model_name, speed=speed,
            on_segment=on_seg, on_progress=on_prog, partial_path=partial,
        )
        if not transcript:
            log("❌ Không nhận diện được nội dung.", "err")
            return

        # Lưu .docx kết quả vào thư mục kịch_bản của dự án (không để cạnh file nguồn)
        out_docx = str(KICHBAN_DIR / f"{Path(media_path).stem}_zh.docx")
        recog.save_docx(transcript, out_docx, title=os.path.basename(media_path))
        log(f"💾 Đã lưu kịch bản (Word): {out_docx}", "ok")
        log("🎉 HOÀN THÀNH!", "ok")
    except Exception as e:
        log(f"❌ Lỗi: {e}", "err")
        log(traceback.format_exc(), "err")
    finally:
        sys.stdout = old_stdout
        on_done(transcript)


# ── GIAO DIỆN ────────────────────────────────────────────────────────────────
class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("Nhận diện giọng nói tiếng Trung")
        root.configure(bg=UI["bg"])
        self._center(root, 980, 600)
        root.minsize(880, 520)

        self._busy = False
        self._build_styles()
        self._build_ui()
        self._load_default_result()   # nạp sẵn nội dung từ tiengTung.docx (nếu có)
        self.root.after(120, self._poll_log)

    def _load_default_result(self):
        """Khi mở app: nạp sẵn nội dung từ DEFAULT_RESULT_DOCX vào ô kết quả.

        Có nội dung là dùng/gửi Gemini được ngay, khỏi nhận diện lại. Không có
        file thì im lặng bỏ qua (vẫn dùng app bình thường).
        """
        if not DEFAULT_RESULT_DOCX.exists():
            return
        text = read_docx_body(DEFAULT_RESULT_DOCX)
        if not text:
            return
        self.result.delete("1.0", "end")
        self.result.insert("1.0", text)
        self._build_chunk_buttons(text)   # tạo nút số theo đoạn đã tách
        self.status.set(f"📄 Đã nạp sẵn nội dung từ {DEFAULT_RESULT_DOCX.name} "
                        f"({len(self._chunks)} đoạn). Có thể gửi Gemini ngay.")

    def _center(self, root, w, h):
        """Mở cửa sổ ở giữa màn hình (ngang giữa, 1/3 từ trên xuống)."""
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        x, y = (sw - w) // 2, (sh - h) // 3
        root.geometry(f"{w}x{h}+{max(x, 0)}+{max(y, 0)}")

    def _build_styles(self):
        st = ttk.Style()
        try:
            st.theme_use("clam")
        except Exception:
            pass
        st.configure("TLabel", background=UI["bg"], foreground=UI["fg"], font=("Segoe UI", 10))
        st.configure("Muted.TLabel", background=UI["bg"], foreground=UI["muted"], font=("Segoe UI", 9))
        st.configure("Title.TLabel", background=UI["bg"], foreground=UI["accent_dk"],
                     font=("Segoe UI Semibold", 16))
        st.configure("TCombobox", fieldbackground=UI["field"], background=UI["field"])
        st.configure("Accent.TButton", font=("Segoe UI Semibold", 11), padding=(18, 9),
                     foreground="#ffffff", background=UI["accent"], borderwidth=0)
        st.map("Accent.TButton",
               background=[("active", UI["accent_dk"]), ("disabled", "#f0a8c6")])
        st.configure("Ghost.TButton", font=("Segoe UI", 10), padding=(12, 7),
                     foreground=UI["fg"], background=UI["hover"], borderwidth=0)
        st.map("Ghost.TButton", background=[("active", UI["border"])])
        st.configure("Pink.Horizontal.TProgressbar", troughcolor=UI["border"],
                     background=UI["accent"], borderwidth=0, thickness=10)

    def _build_ui(self):
        pad = dict(padx=18)
        ttk.Label(self.root, text="🎧 Audio/Video → Văn bản tiếng Trung",
                  style="Title.TLabel").pack(anchor="w", pady=(16, 2), **pad)
        ttk.Label(self.root, text="Chọn file có sẵn trên máy (mp3/mp4/wav...) hoặc dán link video.",
                  style="Muted.TLabel").pack(anchor="w", pady=(0, 12), **pad)

        # Hàng nhập: ô đường dẫn + nút Chọn file
        in_row = tk.Frame(self.root, bg=UI["bg"])
        in_row.pack(fill="x", **pad)
        self.url_var = tk.StringVar()
        self.entry = tk.Entry(in_row, textvariable=self.url_var, font=("Segoe UI", 11),
                              bg=UI["field"], fg=UI["muted"], relief="solid", bd=1,
                              highlightthickness=1, highlightcolor=UI["accent"],
                              insertbackground=UI["fg"])
        self.entry.pack(side="left", fill="x", expand=True, ipady=7)
        self.entry.insert(0, PLACEHOLDER)
        self.entry.bind("<FocusIn>", self._clear_placeholder)
        self.entry.bind("<FocusOut>", self._restore_placeholder)
        self.entry.bind("<Return>", lambda e: self.start())
        ttk.Button(in_row, text="📁 Chọn file", style="Ghost.TButton",
                   command=self._pick_file).pack(side="left", padx=(8, 0))

        # Hàng điều khiển: model + nút
        row = tk.Frame(self.root, bg=UI["bg"])
        row.pack(fill="x", pady=14, **pad)
        ttk.Label(row, text="Model:").pack(side="left")
        self.model_var = tk.StringVar(value=DEFAULT_MODEL)
        self.model_cb = ttk.Combobox(row, textvariable=self.model_var, values=MODELS,
                                     state="readonly", width=12)
        self.model_cb.pack(side="left", padx=(8, 4))
        ttk.Label(row, text="(small = nhanh, large-v3 = chính xác nhất)",
                  style="Muted.TLabel").pack(side="left")

        ttk.Label(row, text="Tốc độ:").pack(side="left", padx=(12, 0))
        self.speed_var = tk.StringVar(value=DEFAULT_SPEED)
        self.speed_cb = ttk.Combobox(row, textvariable=self.speed_var, values=SPEEDS,
                                     state="readonly", width=5)
        self.speed_cb.pack(side="left", padx=(8, 4))
        ttk.Label(row, text="(0.7 = chậm lại, dễ nghe rõ)",
                  style="Muted.TLabel").pack(side="left")

        self.btn_open = ttk.Button(row, text="📂 Mở thư mục", style="Ghost.TButton",
                                   command=self._open_folder)
        self.btn_open.pack(side="right")
        self.btn_run = ttk.Button(row, text="🚀 Nhận diện", style="Accent.TButton",
                                  command=self.start)
        self.btn_run.pack(side="right", padx=(0, 8))

        # Trạng thái + thanh tiến độ
        self.status = tk.StringVar(value="Sẵn sàng.")
        ttk.Label(self.root, textvariable=self.status, style="Muted.TLabel").pack(anchor="w", **pad)
        self.progress = ttk.Progressbar(self.root, style="Pink.Horizontal.TProgressbar",
                                        mode="determinate", maximum=100)
        self.progress.pack(fill="x", pady=(4, 0), **pad)

        # Khung kết quả + log
        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=18, pady=(8, 14))

        res_frame = tk.Frame(nb, bg=UI["bg"])
        res_bar = tk.Frame(res_frame, bg=UI["bg"])
        res_bar.pack(fill="x", pady=(4, 2))
        self.btn_copy = ttk.Button(res_bar, text="📋 Sao chép kết quả",
                                   style="Ghost.TButton", command=self._copy_result)
        self.btn_copy.pack(side="right")
        # Gửi thẳng các đoạn sang Gemini (mở Firefox bằng Selenium) — xem dich_gemini.py
        self.btn_gemini = ttk.Button(res_bar, text="🤖 Gửi Gemini",
                                     style="Accent.TButton", command=self._send_gemini)
        self.btn_gemini.pack(side="right", padx=(0, 8))

        # Hàng nút sao chép theo từng ĐOẠN (1,2,3...) — tạo động sau khi nhận diện
        # xong, trùng với cách .docx tách đoạn. Bấm số nào thì chép đoạn đó;
        # riêng đoạn 1 được chèn thêm "Câu mở đầu" (COPY_PREFIX) lên trước.
        self.chunk_bar = tk.Frame(res_frame, bg=UI["bg"])
        self.chunk_bar.pack(fill="x", pady=(0, 2))
        self._chunks = []
        self._chunk_btns = []
        self._copied = set()   # chỉ số các đoạn đã được chép (để tô màu)

        self.result = scrolledtext.ScrolledText(res_frame, font=("Microsoft YaHei", 13),
                                                wrap="word", bg="#ffffff", fg=UI["fg"],
                                                relief="flat", padx=10, pady=8)
        self.result.pack(fill="both", expand=True)
        nb.add(res_frame, text="  Kết quả (中文)  ")

        # Tab hiển thị kết quả Gemini trả về (live theo từng đoạn)
        gem_frame = tk.Frame(nb, bg=UI["bg"])
        self.gemini_box = scrolledtext.ScrolledText(gem_frame, font=("Segoe UI", 12),
                                                    wrap="word", bg="#ffffff", fg=UI["fg"],
                                                    relief="flat", padx=10, pady=8)
        self.gemini_box.pack(fill="both", expand=True)
        nb.add(gem_frame, text="  Kết quả Gemini  ")

        log_frame = tk.Frame(nb, bg=UI["bg"])
        self.logbox = scrolledtext.ScrolledText(log_frame, font=("Consolas", 9), wrap="word",
                                                bg=UI["log_bg"], fg=UI["log_info"], relief="flat",
                                                padx=10, pady=8, state="disabled")
        self.logbox.pack(fill="both", expand=True)
        self.logbox.tag_config("err", foreground=UI["log_err"])
        self.logbox.tag_config("warn", foreground=UI["log_warn"])
        self.logbox.tag_config("ok", foreground=UI["ok"])
        self.logbox.tag_config("info", foreground=UI["log_info"])
        nb.add(log_frame, text="  Nhật ký  ")

        # Tab chỉnh câu mở đầu (chèn lên đầu khi sao chép) — tự lưu ra file
        prefix_frame = tk.Frame(nb, bg=UI["bg"])
        pbar = tk.Frame(prefix_frame, bg=UI["bg"])
        pbar.pack(fill="x", pady=(4, 2))
        ttk.Label(pbar, text="Câu này được chèn lên đầu khi bấm “Sao chép kết quả”. Sửa xong sẽ tự lưu.",
                  style="Muted.TLabel").pack(side="left")
        ttk.Button(pbar, text="↺ Mặc định", style="Ghost.TButton",
                   command=self._reset_prefix).pack(side="right")
        self.prefix_box = scrolledtext.ScrolledText(prefix_frame, font=("Segoe UI", 11), wrap="word",
                                                    bg="#ffffff", fg=UI["fg"], relief="flat",
                                                    padx=10, pady=8, height=6)
        self.prefix_box.pack(fill="both", expand=True)
        self.prefix_box.insert("1.0", load_prefix())
        nb.add(prefix_frame, text="  Câu mở đầu  ")

        self.nb = nb

    # ── Placeholder helpers ──
    def _clear_placeholder(self, _=None):
        if self.entry.get() == PLACEHOLDER:
            self.entry.delete(0, "end")
            self.entry.config(fg=UI["fg"])

    def _restore_placeholder(self, _=None):
        if not self.entry.get().strip():
            self.entry.insert(0, PLACEHOLDER)
            self.entry.config(fg=UI["muted"])

    def _pick_file(self):
        path = filedialog.askopenfilename(
            title="Chọn file audio/video tiếng Trung",
            filetypes=[
                ("Audio/Video", "*.mp3 *.wav *.m4a *.aac *.flac *.ogg *.opus *.wma "
                                "*.mp4 *.mkv *.mov *.avi *.webm *.flv"),
                ("Tất cả", "*.*"),
            ],
        )
        if path:
            self.url_var.set(path)
            self.entry.config(fg=UI["fg"])

    def _copy_result(self):
        text = self.result.get("1.0", "end").strip()
        if not text:
            self.status.set("⚠️ Chưa có kết quả để sao chép.")
            return
        prefix = self.prefix_box.get("1.0", "end").strip()
        save_prefix(prefix)                          # nhớ câu mở đầu cho lần sau
        if prefix:
            text = prefix + "\n\n" + text            # chèn câu hướng dẫn lên đầu
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update()  # giữ nội dung trên clipboard kể cả khi đóng app
        self.status.set("📋 Đã sao chép kết quả vào clipboard.")
        # Hiệu ứng đổi nhãn nút trong 1.2s rồi trả về như cũ
        self.btn_copy.config(text="✔ Đã sao chép")
        self.root.after(1200, lambda: self.btn_copy.config(text="📋 Sao chép kết quả"))

    def _clear_chunk_buttons(self):
        """Xoá hàng nút đoạn (gọi khi bắt đầu nhận diện mới)."""
        for w in self.chunk_bar.winfo_children():
            w.destroy()
        self._chunks = []
        self._chunk_btns = []
        self._copied = set()   # chỉ số các đoạn đã được chép (để tô màu)

    def _build_chunk_buttons(self, transcript):
        """Tạo dãy nút số 1,2,3... theo các đoạn đã tách (giống .docx).

        Chỉ hiện khi tách được từ 2 đoạn trở lên (1 đoạn thì nút 'Sao chép
        kết quả' là đủ). Bấm nút k → chép đoạn k; riêng đoạn 1 chèn câu mở đầu.
        """
        self._clear_chunk_buttons()
        self._chunks = recog.split_into_chunks(transcript) if transcript else []
        if len(self._chunks) <= 1:
            return

        ttk.Label(self.chunk_bar, text="📋 Chép theo đoạn:",
                  style="Muted.TLabel").pack(side="left")
        for idx in range(len(self._chunks)):
            first = (idx == 0)
            b = tk.Button(
                self.chunk_bar, text=str(idx + 1), width=3, cursor="hand2",
                font=("Segoe UI Semibold", 10), relief="flat", bd=0,
                bg=(UI["accent"] if first else UI["hover"]),
                fg=("#ffffff" if first else UI["fg"]),
                activebackground=UI["accent_dk"], activeforeground="#ffffff",
                command=lambda i=idx: self._copy_chunk(i),
            )
            b.pack(side="left", padx=(6 if idx == 0 else 3, 0))
            self._chunk_btns.append(b)
        ttk.Label(self.chunk_bar, text="(đoạn 1 kèm câu mở đầu)",
                  style="Muted.TLabel").pack(side="left", padx=(8, 0))

    def _copy_chunk(self, idx):
        """Chép đoạn thứ idx (0-based) vào clipboard; đoạn 1 kèm câu mở đầu."""
        if idx >= len(self._chunks):
            return
        text = self._chunks[idx]
        if idx == 0:
            prefix = self.prefix_box.get("1.0", "end").strip()
            save_prefix(prefix)                       # nhớ câu mở đầu cho lần sau
            if prefix:
                text = prefix + "\n\n" + text
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update()  # giữ nội dung trên clipboard kể cả khi đóng app
        kem = " (kèm câu mở đầu)" if idx == 0 else ""
        self.status.set(f"📋 Đã chép đoạn {idx + 1}{kem} vào clipboard.")
        # Tô màu nút để biết đoạn nào đã chép: các đoạn đã chép trước tô xanh nhạt,
        # đoạn vừa bấm tô xanh đậm cho nổi bật.
        for i in self._copied:
            self._chunk_btns[i].config(bg="#9bd5b0", fg="#ffffff",
                                       activebackground=UI["ok"])
        self._copied.add(idx)
        self._chunk_btns[idx].config(bg=UI["ok"], fg="#ffffff",
                                     activebackground=UI["ok"])

    # ── Gửi sang Gemini ───────────────────────────────────────────────────────
    def _send_gemini(self):
        """Gửi các đoạn (đã tách khi nhận diện) sang Gemini qua Firefox/Selenium."""
        if self._busy:
            messagebox.showinfo("Đang bận", "Đang nhận diện, vui lòng đợi xong rồi gửi Gemini.")
            return

        # Ưu tiên các đoạn đã tách; chưa có thì tự tách từ nội dung đang hiển thị.
        chunks = list(self._chunks)
        if not chunks:
            text = self.result.get("1.0", "end").strip()
            if not text:
                self.status.set("⚠️ Chưa có nội dung để gửi Gemini.")
                return
            chunks = recog.split_into_chunks(text)
        if not chunks:
            self.status.set("⚠️ Không tách được đoạn nào để gửi.")
            return

        prefix = self.prefix_box.get("1.0", "end").strip()
        save_prefix(prefix)  # nhớ câu mở đầu cho lần sau

        if not messagebox.askyesno(
            "Gửi sang Gemini",
            f"Sẽ mở Firefox và gửi {len(chunks)} đoạn sang Gemini.\n\n"
            "Hãy ĐÓNG Firefox đang mở (profile bị khoá khi đang chạy) và đảm bảo "
            "profile đã đăng nhập Google.\n\nTiếp tục?",
        ):
            return

        self.btn_gemini.config(state="disabled")
        self.gemini_box.delete("1.0", "end")
        self.status.set("🤖 Đang gửi sang Gemini...")
        self.nb.select(1)  # mở tab "Kết quả Gemini" để xem chữ chạy live
        threading.Thread(
            target=self._gemini_worker, args=(chunks, prefix), daemon=True
        ).start()

    def _gemini_worker(self, chunks, prefix):
        try:
            import dich_gemini
        except Exception as e:
            log(f"❌ Không nạp được dich_gemini: {e}", "err")
            ui_queue.put(("gemini_done", None))
            return
        out = KICHBAN_DIR / "gemini_result.docx"
        try:
            results = dich_gemini.send_chunks_to_gemini(
                chunks, prefix=prefix, out_path=out,   # lưu dần sau mỗi đoạn
                on_log=lambda m: log(m),
                on_result=lambda i, total, ans: ui_queue.put(("gemini", (i, total, ans))),
            )
            dich_gemini.save_results_docx(chunks, results, out)
            log(f"💾 Đã lưu kết quả Gemini: {out}", "ok")
            ui_queue.put(("gemini_done", str(out)))
        except Exception as e:
            log(f"❌ Lỗi gửi Gemini: {e}", "err")
            log(traceback.format_exc(), "err")
            ui_queue.put(("gemini_done", None))

    def _reset_prefix(self):
        """Khôi phục câu mở đầu về mặc định và lưu lại."""
        self.prefix_box.delete("1.0", "end")
        self.prefix_box.insert("1.0", COPY_PREFIX)
        save_prefix(COPY_PREFIX)
        self.status.set("↺ Đã khôi phục câu mở đầu mặc định.")

    def _open_folder(self):
        os.startfile(str(KICHBAN_DIR))

    # ── Chạy ──
    def start(self):
        if self._busy:
            return
        src = self.url_var.get().strip().strip('"').strip("'")
        is_file = os.path.isfile(src)
        is_link = src.lower().startswith(("http://", "https://"))
        if not src or src == PLACEHOLDER or not (is_file or is_link):
            messagebox.showwarning(
                "Đầu vào không hợp lệ",
                "Hãy chọn một file có sẵn trên máy (mp3/mp4/wav...) "
                "hoặc dán một link video (bắt đầu bằng http).",
            )
            return

        self._busy = True
        self.btn_run.config(state="disabled")
        self.status.set("⏳ Đang tải model / chuẩn bị...")
        self.result.delete("1.0", "end")
        self._clear_chunk_buttons()   # bỏ nút đoạn của lần nhận diện trước
        self._clear_log()
        self.progress["value"] = 0
        self.nb.select(0)  # xem tab Kết quả để thấy chữ chạy live

        # callback chạy ở thread nền → CHỈ đẩy vào queue (an toàn luồng).
        # _poll_log chạy ở main thread sẽ tiêu thụ và cập nhật giao diện.
        on_seg = lambda text, _frac: ui_queue.put(("seg", text))
        on_prog = lambda frac: ui_queue.put(("prog", frac))
        on_done = lambda transcript: ui_queue.put(("done", transcript))

        try:
            speed = float(self.speed_var.get())
        except (TypeError, ValueError):
            speed = float(DEFAULT_SPEED)
        threading.Thread(
            target=worker,
            args=(src, self.model_var.get(), speed, on_seg, on_prog, on_done),
            daemon=True,
        ).start()

    def _play_done_sound(self, ok=True):
        """Phát âm báo khi chạy xong (thành công/thất bại). Bỏ qua nếu lỗi."""
        try:
            import winsound
            winsound.MessageBeep(
                winsound.MB_ICONASTERISK if ok else winsound.MB_ICONHAND
            )
        except Exception:
            pass

    def _finish(self, transcript):
        self._busy = False
        self.btn_run.config(state="normal")
        if transcript:
            # Thay nội dung live bằng bản hoàn chỉnh (gọn, chuẩn)
            self.result.delete("1.0", "end")
            self.result.insert("1.0", transcript)
            self._build_chunk_buttons(transcript)   # tạo nút số theo đoạn đã tách
            self.progress["value"] = 100
            self.status.set("✅ Hoàn thành. Đã lưu file Word .docx vào thư mục kịch_bản.")
            self.nb.select(0)
            self._play_done_sound(ok=True)          # 🔔 báo âm thanh khi xong
        else:
            self.status.set("❌ Thất bại. Xem tab 'Nhật ký'.")
            self._play_done_sound(ok=False)

    # ── Log polling ──
    def _clear_log(self):
        self.logbox.config(state="normal")
        self.logbox.delete("1.0", "end")
        self.logbox.config(state="disabled")

    def _poll_log(self):
        # 1) Log
        try:
            while True:
                level, msg = log_queue.get_nowait()
                self.logbox.config(state="normal")
                self.logbox.insert("end", msg + "\n", level)
                self.logbox.see("end")
                self.logbox.config(state="disabled")
        except queue.Empty:
            pass
        # 2) Sự kiện live: câu mới + tiến độ
        try:
            while True:
                kind, payload = ui_queue.get_nowait()
                if kind == "seg":
                    self.result.insert("end", payload)  # nối liền (tiếng Trung không dấu cách)
                    self.result.see("end")
                elif kind == "prog":
                    pct = max(0.0, min(payload * 100, 100.0))
                    self.progress["value"] = pct
                    self.status.set(f"📝 Đang nhận diện... {pct:.0f}%")
                elif kind == "done":
                    self._finish(payload)
                elif kind == "gemini":
                    i, total, ans = payload
                    self.gemini_box.insert("end", f"───── Đoạn {i + 1}/{total} ─────\n")
                    self.gemini_box.insert("end", (ans or "(trống)") + "\n\n")
                    self.gemini_box.see("end")
                    self.status.set(f"🤖 Gemini: xong đoạn {i + 1}/{total}")
                elif kind == "gemini_done":
                    self.btn_gemini.config(state="normal")
                    if payload:
                        self.status.set("✅ Gemini xong. Đã lưu gemini_result.docx vào kịch_bản.")
                        self._play_done_sound(ok=True)
                    else:
                        self.status.set("❌ Gửi Gemini thất bại. Xem tab 'Nhật ký'.")
                        self._play_done_sound(ok=False)
        except queue.Empty:
            pass
        self.root.after(120, self._poll_log)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
