# -*- coding: utf-8 -*-
"""
Giao diện: dán link video (Bilibili/YouTube/TikTok...) → tự tải MP3 → nhận diện
giọng nói TIẾNG TRUNG thành văn bản.

Chạy:  python nhan_dien_gui.py
"""

import sys, os

# ── Tự chuyển sang python của venv (giống clone_gui.py) ──────────────────────
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
_VENV_PYTHON = os.path.join(_REPO_ROOT, "venv", "Scripts", "python.exe")
if os.path.exists(_VENV_PYTHON) and os.path.abspath(sys.executable) != os.path.abspath(_VENV_PYTHON):
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
import nhan_dien_audio_tieng_trung as recog

# ── Cấu hình thư mục ─────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent          # myvoice/scripts/
DOWNLOAD_DIR = BASE_DIR / "downloads_zh"             # nơi lưu mp3 tải từ link
DOWNLOAD_DIR.mkdir(exist_ok=True)
# Thư mục kịch bản của dự án — nơi lưu file .docx kết quả nhận diện
KICHBAN_DIR = BASE_DIR.parent / "kịch_bản"
KICHBAN_DIR.mkdir(exist_ok=True)

MODELS = ["tiny", "base", "small", "medium", "large-v3"]
DEFAULT_MODEL = "medium"
# Tốc độ phát audio khi nhận diện (0.7 = chậm lại cho dễ bắt chữ với giọng đọc nhanh)
SPEEDS = ["0.6", "0.7", "0.8", "0.9", "1.0"]
DEFAULT_SPEED = "0.7"
PLACEHOLDER = "Chọn file hoặc dán đường dẫn file (mp3/mp4/wav...) — hoặc link video"

# Câu hướng dẫn MẶC ĐỊNH được chèn lên ĐẦU mỗi lần bấm "Sao chép kết quả".
# Người dùng có thể sửa ngay trên GUI (tab "Câu mở đầu"); bản đã sửa lưu ở PREFIX_FILE.
COPY_PREFIX = (
"Dưới đây là một truyện ngắn tiếng Trung. Hãy dịch sang tiếng Việt sát nghĩa nhất có thể, "
"giữ nguyên đầy đủ nội dung, tình tiết, nhân vật, diễn biến và ý nghĩa gốc của truyện. "
"Không tự ý thêm tình tiết mới, không tự ý bớt tình tiết, không biến đổi nội dung thành một câu chuyện khác. "
"Tuy nhiên, khi chuyển sang tiếng Việt, hãy được phép diễn đạt lại câu chữ cho tự nhiên, rõ nghĩa và dễ hiểu với người Việt, "
"miễn là không làm sai lệch ý gốc. Không dịch cứng từng chữ nếu cách dịch đó khiến câu tiếng Việt khó hiểu, thô hoặc không tự nhiên. "
"Nếu một cụm tiếng Trung có nghĩa hàm ý, tiếng lóng, cách nói ẩn dụ, cách nói châm biếm hoặc cách nói theo truyện mạng, "
"hãy dịch theo nghĩa thực tế trong ngữ cảnh, giúp người Việt hiểu đúng ngay khi đọc. "
"Ví dụ: nếu gặp cách nói như “发绿的僵尸鸭”, không dịch cứng thành “vịt zombie phát xanh”, "
"mà hãy diễn đạt dễ hiểu là “thịt vịt chết lâu ngày, đã hư đến mức chuyển màu xanh” hoặc "
"“thịt vịt hỏng, chết lâu ngày đến mức phát xanh” tùy ngữ cảnh. "
"Nếu có chỗ nào câu chữ bị sai do nhận diện giọng nói, lỗi chính tả, lỗi đồng âm, thiếu dấu câu hoặc câu văn bị méo nghĩa, "
"hãy tự đoán theo ngữ cảnh, tự ngắt câu lại hợp lý và dịch theo nghĩa hợp lý nhất. "
"Nếu văn bản có dấu hiệu được nhận diện từ audio tốc độ nhanh, nhiều chỗ bị dính câu, mất chữ, sai tên riêng hoặc sai thuật ngữ, "
"hãy ưu tiên khôi phục ý đúng theo mạch truyện trước khi dịch. "
"Với các thuật ngữ truyện mạng Trung Quốc như 系统, 攻略, 假千金, 真千金, 金手指, 宿主, 重生, 绑定, "
"时空管理局, 高维度系统, 豆包, 豆包网..., hãy dịch sao cho người Việt dễ hiểu, có thể Việt hóa theo nghĩa, "
"không cần dịch cứng từng chữ. Ví dụ: 系统 dịch là hệ thống, 攻略 dịch là lấy lòng/công lược/thao túng thiện cảm tùy ngữ cảnh, "
"假千金 dịch là thiên kim giả, 真千金 dịch là thiên kim thật, 金手指 dịch là bàn tay vàng/năng lực gian lận, "
"宿主 dịch là ký chủ hoặc người được hệ thống ràng buộc tùy ngữ cảnh, 重生 dịch là trọng sinh/sống lại, "
"绑定 dịch là ràng buộc/liên kết, 时空管理局 dịch là Cục Quản lý Thời không, "
"豆包 dịch là hệ thống Đậu Bao ngốc nghếch hoặc hệ thống Đậu Bao, "
"豆包网 dịch là web Đậu Bao giả hoặc Trang web Đậu Bao tùy ngữ cảnh. "
"Với các món ăn, đồ vật, thành ngữ hoặc cách gọi đặc thù Trung Quốc, hãy dịch sao cho người Việt dễ hiểu. "
"Nếu cần, có thể giữ tên gốc kèm cách giải thích ngắn trong câu, nhưng không được làm dài dòng quá mức. "
"Tên nhân vật, địa danh, quan hệ gia đình và xưng hô phải dịch nhất quán trong toàn truyện. "
"Nếu gặp các tên bị nhận diện sai nhưng theo ngữ cảnh là cùng một người, hãy tự quy về một tên thống nhất. "
"Ví dụ cùng một nhân vật nhưng bị nhận diện thành nhiều dạng khác nhau thì hãy chọn một tên Việt hóa nhất quán và dùng xuyên suốt. "
"Khi dịch truyện, nếu gặp câu quảng bá kênh như “小薯条邀你一起看书咯”, "
"“请点赞/订阅/转发/打赏”, “感谢支持”, hoặc các câu kêu gọi like, theo dõi, đăng ký, chia sẻ, tặng quà, "
"hãy đổi tên kênh gốc thành “mimi Truyện”, không giữ tên kênh Trung Quốc. "
"Ví dụ: “小薯条邀你一起看书咯” dịch thành “mimi Truyện mời bạn cùng đọc truyện đây”. "
"Các câu quảng bá kênh vẫn dịch đúng ý nếu có trong văn bản, nhưng không để chúng làm rối mạch truyện chính. "
"Nội dung còn lại vẫn phải dịch sát nghĩa, giữ đúng mạch truyện, đúng cảm xúc, đúng quan hệ nhân vật và đúng diễn biến gốc. "
"Ưu tiên bản dịch tiếng Việt tự nhiên, dễ đọc, dễ hiểu, nhưng tuyệt đối không bịa thêm nội dung mới."
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

# ── Bảng màu (đồng bộ với clone_gui.py) ──────────────────────────────────────
UI = dict(
    bg="#ffffff", fg="#1f2430", muted="#7b828f",
    accent="#e84393", accent_dk="#c92f7b",
    field="#ffffff", border="#e4e7ec", hover="#f1f3f6",
    log_bg="#fbfbfc", log_info="#475063", log_warn="#b07400", log_err="#d62828", ok="#1f9d55",
)

# ── Queue truyền log + sự kiện live (segment/tiến độ) từ thread nền về GUI ────
log_queue: "queue.Queue[tuple[str, str]]" = queue.Queue()
ui_queue: "queue.Queue[tuple]" = queue.Queue()   # ("seg", text) | ("prog", fraction)


def log(msg, level="info"):
    log_queue.put((level, str(msg)))


class _StdoutToLog:
    """Chuyển mọi print() trong thread nền vào ô log của GUI."""
    def write(self, s):
        s = s.rstrip("\n")
        if s.strip():
            log_queue.put(("info", s))
    def flush(self):
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
    sys.stdout = _StdoutToLog()
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
        root.geometry("760x600")
        root.minsize(640, 520)

        self._busy = False
        self._build_styles()
        self._build_ui()
        self.root.after(120, self._poll_log)

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
        self.result = scrolledtext.ScrolledText(res_frame, font=("Microsoft YaHei", 13),
                                                wrap="word", bg="#ffffff", fg=UI["fg"],
                                                relief="flat", padx=10, pady=8)
        self.result.pack(fill="both", expand=True)
        nb.add(res_frame, text="  Kết quả (中文)  ")

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

    def _finish(self, transcript):
        self._busy = False
        self.btn_run.config(state="normal")
        if transcript:
            # Thay nội dung live bằng bản hoàn chỉnh (gọn, chuẩn)
            self.result.delete("1.0", "end")
            self.result.insert("1.0", transcript)
            self.progress["value"] = 100
            self.status.set("✅ Hoàn thành. Đã lưu file Word .docx vào thư mục kịch_bản.")
            self.nb.select(0)
        else:
            self.status.set("❌ Thất bại. Xem tab 'Nhật ký'.")

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
        except queue.Empty:
            pass
        self.root.after(120, self._poll_log)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
