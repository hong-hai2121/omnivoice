# -*- coding: utf-8 -*-
"""
Giao diện: ĐĂNG VIDEO TỰ ĐỘNG LÊN YOUTUBE (tiêu đề + mô tả + thẻ tag).

Dùng YouTube Data API v3 (OAuth). Lần đầu chạy sẽ mở trình duyệt để bạn đăng nhập
và cấp quyền; sau đó token được lưu lại (token.json) nên các lần sau không phải
đăng nhập lại.

Chạy:  python dang_video_youtube.py

────────────────────────────────────────────────────────────────────────────
CHUẨN BỊ MỘT LẦN (bắt buộc, do YouTube yêu cầu OAuth):
  1. Vào https://console.cloud.google.com/  → tạo Project.
  2. "APIs & Services" → "Library" → bật "YouTube Data API v3".
  3. "APIs & Services" → "OAuth consent screen": chọn External, điền tên app,
     thêm email của bạn vào mục "Test users".
  4. "Credentials" → "Create Credentials" → "OAuth client ID" → loại
     "Desktop app" → tải file JSON về, đổi tên thành  client_secret.json
     và đặt vào thư mục:  myvoice/YOUTUBE/client_secret.json
  (Nút "Mở thư mục cấu hình" trong app sẽ mở đúng thư mục này.)

CÀI THƯ VIỆN (nếu thiếu — app sẽ báo và cho cài tự động):
  pip install google-api-python-client google-auth-oauthlib google-auth-httplib2
────────────────────────────────────────────────────────────────────────────
"""

import sys, os

# ── Tự chuyển sang python của venv (giống các script *_gui.py khác) ──────────
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
_VENV_PYTHON = os.path.join(_REPO_ROOT, "venv", "Scripts", "python.exe")
if os.path.exists(_VENV_PYTHON) and os.path.abspath(sys.executable) != os.path.abspath(_VENV_PYTHON):
    import subprocess
    subprocess.run([_VENV_PYTHON] + sys.argv)
    sys.exit()

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import json
import queue
import threading
import traceback
import subprocess
import webbrowser
from pathlib import Path
from datetime import datetime, timezone

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog

# ── Cấu hình thư mục ─────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent              # myvoice/YOUTUBE/
YT_DIR = BASE_DIR                                        # client_secret/token/settings nằm cùng thư mục script
YT_DIR.mkdir(exist_ok=True)
CLIENT_SECRET_FILE = YT_DIR / "client_secret.json"      # bạn tải từ Google Cloud Console
TOKEN_FILE = YT_DIR / "token.json"                      # token đăng nhập, tự sinh sau lần đầu
SETTINGS_FILE = YT_DIR / "settings.json"                # ghi nhớ lựa chọn lần trước

VIDEO_EXTS = [("Video", "*.mp4 *.mov *.mkv *.avi *.flv *.webm *.m4v *.wmv"),
              ("Tất cả", "*.*")]
IMAGE_EXTS = [("Ảnh", "*.jpg *.jpeg *.png"), ("Tất cả", "*.*")]

# Quyền tối thiểu để upload video + đặt thumbnail cho kênh của chính bạn.
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

# Giới hạn của YouTube (để cảnh báo sớm trước khi gọi API).
MAX_TITLE = 100        # ký tự
MAX_DESC = 5000        # ký tự
MAX_TAGS_TOTAL = 480   # tổng ký tự của toàn bộ tag (YouTube ~500, để dư an toàn)

# Danh mục video phổ biến (categoryId của YouTube). Nhãn hiển thị → id.
CATEGORIES = {
    "Phim & Hoạt hình (1)": "1",
    "Ô tô & Xe cộ (2)": "2",
    "Âm nhạc (10)": "10",
    "Thú cưng & Động vật (15)": "15",
    "Thể thao (17)": "17",
    "Du lịch & Sự kiện (19)": "19",
    "Trò chơi / Gaming (20)": "20",
    "Người & Blog (22)": "22",
    "Hài (23)": "23",
    "Giải trí (24)": "24",
    "Tin tức & Chính trị (25)": "25",
    "Hướng dẫn & Phong cách (26)": "26",
    "Giáo dục (27)": "27",
    "Khoa học & Công nghệ (28)": "28",
}
DEFAULT_CATEGORY = "Giải trí (24)"

PRIVACY = {
    "Riêng tư (private)": "private",
    "Không công khai / ai có link (unlisted)": "unlisted",
    "Công khai (public)": "public",
}
DEFAULT_PRIVACY = "Không công khai / ai có link (unlisted)"

# ── Bảng màu giao diện (nền trắng, accent đỏ YouTube) ────────────────────────
UI = dict(
    bg="#ffffff", card="#ffffff", border="#e4e7ec", field="#ffffff",
    fg="#1f2430", muted="#7b828f",
    accent="#ff0000", accent_dk="#cc0000",
    hover="#f1f3f6",
    log_bg="#fbfbfc", log_info="#475063", log_warn="#b07400", log_err="#d62828",
    log_ok="#1d8a4e",
)


# ───────────────────────────────────────────────────────────────────────────
# Phần backend: xác thực + upload (tách khỏi GUI để dễ đọc)
# ───────────────────────────────────────────────────────────────────────────
def _check_deps():
    """Trả về None nếu đủ thư viện, ngược lại trả về thông báo lỗi."""
    try:
        import google_auth_oauthlib.flow      # noqa: F401
        import googleapiclient.discovery       # noqa: F401
        import googleapiclient.http            # noqa: F401
        import google.auth.transport.requests  # noqa: F401
        return None
    except ImportError as e:
        return str(e)


def install_deps(log):
    """Cài các thư viện Google API vào venv hiện tại."""
    pkgs = ["google-api-python-client", "google-auth-oauthlib", "google-auth-httplib2"]
    log(f"Đang cài: {' '.join(pkgs)} ...", "info")
    proc = subprocess.run([sys.executable, "-m", "pip", "install", *pkgs],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.stdout:
        log(proc.stdout.strip(), "info")
    if proc.returncode != 0:
        log(proc.stderr.strip(), "err")
        raise RuntimeError("Cài thư viện thất bại.")
    log("Đã cài xong thư viện Google API.", "ok")


def get_credentials(log):
    """Lấy credentials hợp lệ; tự refresh hoặc mở trình duyệt đăng nhập khi cần."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not CLIENT_SECRET_FILE.exists():
        raise FileNotFoundError(
            "Chưa có client_secret.json.\n\n"
            f"Hãy đặt file vào:\n{CLIENT_SECRET_FILE}\n\n"
            "Xem hướng dẫn lấy file ở đầu script (hoặc nút 'Hướng dẫn lấy quyền')."
        )

    creds = None
    if TOKEN_FILE.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        except Exception:
            creds = None

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        log("Token hết hạn — đang làm mới...", "info")
        try:
            creds.refresh(Request())
            TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
            return creds
        except Exception:
            log("Làm mới token thất bại, sẽ đăng nhập lại.", "warn")

    log("Mở trình duyệt để đăng nhập Google & cấp quyền...", "info")
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_FILE), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
    log("Đăng nhập thành công, đã lưu token.", "ok")
    return creds


def upload_video(opts, log, progress_cb):
    """
    Thực hiện upload. `opts` là dict gồm:
      video_path, title, description, tags(list), category_id,
      privacy, publish_at(str RFC3339 hoặc None), made_for_kids(bool),
      thumbnail_path(str hoặc None)
    Trả về video_id.
    """
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError

    creds = get_credentials(log)
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

    status = {
        "privacyStatus": opts["privacy"],
        "selfDeclaredMadeForKids": bool(opts["made_for_kids"]),
    }
    # Hẹn giờ đăng: YouTube yêu cầu privacy = private và có publishAt.
    if opts.get("publish_at"):
        status["privacyStatus"] = "private"
        status["publishAt"] = opts["publish_at"]

    body = {
        "snippet": {
            "title": opts["title"],
            "description": opts["description"],
            "tags": opts["tags"],
            "categoryId": opts["category_id"],
        },
        "status": status,
    }

    media = MediaFileUpload(opts["video_path"], chunksize=4 * 1024 * 1024, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    log("Bắt đầu tải video lên YouTube...", "info")
    response = None
    while response is None:
        try:
            chunk_status, response = request.next_chunk()
        except HttpError as e:
            raise RuntimeError(f"Lỗi từ YouTube API: {e}")
        if chunk_status:
            progress_cb(int(chunk_status.progress() * 100))
    progress_cb(100)

    video_id = response["id"]
    log(f"Đăng video thành công! ID = {video_id}", "ok")
    log(f"Link: https://youtu.be/{video_id}", "ok")

    # Đặt thumbnail (nếu có).
    if opts.get("thumbnail_path"):
        try:
            log("Đang đặt ảnh thumbnail...", "info")
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(opts["thumbnail_path"]),
            ).execute()
            log("Đã đặt thumbnail.", "ok")
        except HttpError as e:
            log(f"Không đặt được thumbnail (video vẫn đã đăng): {e}", "warn")

    return video_id


# ───────────────────────────────────────────────────────────────────────────
# GUI
# ───────────────────────────────────────────────────────────────────────────
class App:
    def __init__(self, root):
        self.root = root
        self.q = queue.Queue()           # hàng đợi log/progress từ thread worker
        self.worker = None
        root.title("Đăng video tự động lên YouTube")
        root.configure(bg=UI["bg"])
        root.geometry("760x720")
        root.minsize(680, 600)

        self._build_styles()
        self._build_form()
        self._build_log()
        self._load_settings()
        self._poll_queue()

    # ---- style ----
    def _build_styles(self):
        st = ttk.Style()
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure("TFrame", background=UI["bg"])
        st.configure("TLabel", background=UI["bg"], foreground=UI["fg"])
        st.configure("Muted.TLabel", background=UI["bg"], foreground=UI["muted"])
        st.configure("TButton", padding=6)
        st.configure("Accent.TButton", foreground="#ffffff",
                     background=UI["accent"], padding=8)
        st.map("Accent.TButton",
               background=[("active", UI["accent_dk"]), ("disabled", "#f0a3a3")])

    # ---- form ----
    def _build_form(self):
        pad = dict(padx=12, pady=4)
        frm = ttk.Frame(self.root)
        frm.pack(fill="x", **pad)
        frm.columnconfigure(1, weight=1)

        r = 0
        # File video
        ttk.Label(frm, text="File video *").grid(row=r, column=0, sticky="w")
        self.var_video = tk.StringVar()
        ttk.Entry(frm, textvariable=self.var_video).grid(row=r, column=1, sticky="ew", padx=6)
        ttk.Button(frm, text="Chọn...", command=self._pick_video).grid(row=r, column=2)
        r += 1

        # Tiêu đề
        ttk.Label(frm, text="Tiêu đề *").grid(row=r, column=0, sticky="w")
        self.var_title = tk.StringVar()
        self.var_title.trace_add("write", lambda *_: self._update_counters())
        ttk.Entry(frm, textvariable=self.var_title).grid(row=r, column=1, sticky="ew", padx=6)
        self.lbl_title_cnt = ttk.Label(frm, text="0/100", style="Muted.TLabel")
        self.lbl_title_cnt.grid(row=r, column=2, sticky="e")
        r += 1

        # Mô tả
        ttk.Label(frm, text="Mô tả").grid(row=r, column=0, sticky="nw", pady=(6, 0))
        self.txt_desc = tk.Text(frm, height=6, wrap="word",
                                bg=UI["field"], fg=UI["fg"], relief="solid", borderwidth=1)
        self.txt_desc.grid(row=r, column=1, columnspan=2, sticky="ew", padx=6, pady=(6, 0))
        self.txt_desc.bind("<KeyRelease>", lambda _e: self._update_counters())
        r += 1
        self.lbl_desc_cnt = ttk.Label(frm, text="0/5000", style="Muted.TLabel")
        self.lbl_desc_cnt.grid(row=r, column=1, columnspan=2, sticky="e", padx=6)
        r += 1

        # Tags
        ttk.Label(frm, text="Thẻ tag").grid(row=r, column=0, sticky="w")
        self.var_tags = tk.StringVar()
        self.var_tags.trace_add("write", lambda *_: self._update_counters())
        ttk.Entry(frm, textvariable=self.var_tags).grid(row=r, column=1, sticky="ew", padx=6)
        self.lbl_tags_cnt = ttk.Label(frm, text="0/480", style="Muted.TLabel")
        self.lbl_tags_cnt.grid(row=r, column=2, sticky="e")
        r += 1
        ttk.Label(frm, text="(các tag cách nhau bằng dấu phẩy)",
                  style="Muted.TLabel").grid(row=r, column=1, sticky="w", padx=6)
        r += 1

        # Danh mục + quyền riêng tư
        row2 = ttk.Frame(frm)
        row2.grid(row=r, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        row2.columnconfigure(1, weight=1)
        row2.columnconfigure(3, weight=1)
        ttk.Label(row2, text="Danh mục").grid(row=0, column=0, sticky="w")
        self.var_cat = tk.StringVar(value=DEFAULT_CATEGORY)
        ttk.Combobox(row2, textvariable=self.var_cat, values=list(CATEGORIES),
                     state="readonly", width=24).grid(row=0, column=1, sticky="w", padx=6)
        ttk.Label(row2, text="Chế độ").grid(row=0, column=2, sticky="w")
        self.var_priv = tk.StringVar(value=DEFAULT_PRIVACY)
        ttk.Combobox(row2, textvariable=self.var_priv, values=list(PRIVACY),
                     state="readonly", width=30).grid(row=0, column=3, sticky="w", padx=6)
        r += 1

        # Thumbnail + made for kids
        row3 = ttk.Frame(frm)
        row3.grid(row=r, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        row3.columnconfigure(1, weight=1)
        ttk.Label(row3, text="Thumbnail").grid(row=0, column=0, sticky="w")
        self.var_thumb = tk.StringVar()
        ttk.Entry(row3, textvariable=self.var_thumb).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(row3, text="Chọn...", command=self._pick_thumb).grid(row=0, column=2)
        self.var_kids = tk.BooleanVar(value=False)
        ttk.Checkbutton(row3, text="Nội dung cho trẻ em",
                        variable=self.var_kids).grid(row=0, column=3, padx=(10, 0))
        r += 1

        # Hẹn giờ đăng
        row4 = ttk.Frame(frm)
        row4.grid(row=r, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        self.var_sched_on = tk.BooleanVar(value=False)
        ttk.Checkbutton(row4, text="Hẹn giờ đăng (giờ máy tính)",
                        variable=self.var_sched_on,
                        command=self._toggle_sched).grid(row=0, column=0, sticky="w")
        self.var_sched = tk.StringVar()
        self.ent_sched = ttk.Entry(row4, textvariable=self.var_sched, width=22, state="disabled")
        self.ent_sched.grid(row=0, column=1, sticky="w", padx=6)
        ttk.Label(row4, text="dạng: 2026-06-20 14:30",
                  style="Muted.TLabel").grid(row=0, column=2, sticky="w")
        r += 1

        # Nút thao tác
        rowb = ttk.Frame(frm)
        rowb.grid(row=r, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        self.btn_upload = ttk.Button(rowb, text="⬆  ĐĂNG VIDEO", style="Accent.TButton",
                                     command=self._on_upload)
        self.btn_upload.pack(side="left")
        ttk.Button(rowb, text="Mở thư mục cấu hình",
                   command=self._open_cfg_dir).pack(side="left", padx=6)
        ttk.Button(rowb, text="Hướng dẫn lấy quyền",
                   command=self._open_help).pack(side="left")
        r += 1

        # Thanh tiến trình
        self.pb = ttk.Progressbar(frm, mode="determinate", maximum=100)
        self.pb.grid(row=r, column=0, columnspan=3, sticky="ew", pady=(10, 0))

    def _build_log(self):
        wrap = ttk.Frame(self.root)
        wrap.pack(fill="both", expand=True, padx=12, pady=(8, 12))
        ttk.Label(wrap, text="Nhật ký", style="Muted.TLabel").pack(anchor="w")
        self.log_widget = scrolledtext.ScrolledText(
            wrap, height=8, wrap="word", state="disabled",
            bg=UI["log_bg"], fg=UI["log_info"], relief="solid", borderwidth=1)
        self.log_widget.pack(fill="both", expand=True)
        for tag, color in [("info", UI["log_info"]), ("warn", UI["log_warn"]),
                           ("err", UI["log_err"]), ("ok", UI["log_ok"])]:
            self.log_widget.tag_config(tag, foreground=color)

    # ---- helpers GUI ----
    def _pick_video(self):
        f = filedialog.askopenfilename(title="Chọn file video", filetypes=VIDEO_EXTS)
        if f:
            self.var_video.set(f)
            if not self.var_title.get().strip():
                self.var_title.set(Path(f).stem)   # gợi ý tiêu đề từ tên file

    def _pick_thumb(self):
        f = filedialog.askopenfilename(title="Chọn ảnh thumbnail", filetypes=IMAGE_EXTS)
        if f:
            self.var_thumb.set(f)

    def _toggle_sched(self):
        self.ent_sched.config(state="normal" if self.var_sched_on.get() else "disabled")

    def _open_cfg_dir(self):
        try:
            os.startfile(str(YT_DIR))   # Windows
        except Exception:
            self.log(f"Thư mục cấu hình: {YT_DIR}", "info")

    def _open_help(self):
        webbrowser.open("https://console.cloud.google.com/apis/library/youtube.googleapis.com")
        messagebox.showinfo(
            "Hướng dẫn lấy quyền",
            "1. Bật 'YouTube Data API v3' trong Google Cloud Console.\n"
            "2. Tạo OAuth client ID loại 'Desktop app'.\n"
            "3. Tải JSON, đổi tên thành client_secret.json và đặt vào thư mục cấu hình\n"
            "   (bấm nút 'Mở thư mục cấu hình').\n\n"
            "Chi tiết đầy đủ nằm ở phần đầu file script.")

    def _update_counters(self):
        t = len(self.var_title.get())
        d = len(self.txt_desc.get("1.0", "end-1c"))
        tags = self._parse_tags()
        g = sum(len(x) for x in tags) + max(0, len(tags) - 1)  # ~ tổng ký tự kể cả dấu phẩy
        self.lbl_title_cnt.config(text=f"{t}/{MAX_TITLE}",
                                  foreground=UI["log_err"] if t > MAX_TITLE else UI["muted"])
        self.lbl_desc_cnt.config(text=f"{d}/{MAX_DESC}",
                                 foreground=UI["log_err"] if d > MAX_DESC else UI["muted"])
        self.lbl_tags_cnt.config(text=f"{g}/{MAX_TAGS_TOTAL}",
                                 foreground=UI["log_err"] if g > MAX_TAGS_TOTAL else UI["muted"])

    def _parse_tags(self):
        return [t.strip() for t in self.var_tags.get().split(",") if t.strip()]

    def log(self, msg, level="info"):
        self.q.put(("log", level, msg))

    # ---- queue polling (cập nhật GUI từ thread chính) ----
    def _poll_queue(self):
        try:
            while True:
                kind, *rest = self.q.get_nowait()
                if kind == "log":
                    level, msg = rest
                    self.log_widget.config(state="normal")
                    self.log_widget.insert("end", msg + "\n", level)
                    self.log_widget.see("end")
                    self.log_widget.config(state="disabled")
                elif kind == "progress":
                    self.pb["value"] = rest[0]
                elif kind == "done":
                    self.btn_upload.config(state="normal")
                    self.worker = None
        except queue.Empty:
            pass
        self.root.after(120, self._poll_queue)

    # ---- validate + upload ----
    def _validate(self):
        v = self.var_video.get().strip()
        if not v or not Path(v).is_file():
            return "Chưa chọn file video hợp lệ."
        if not self.var_title.get().strip():
            return "Chưa nhập tiêu đề."
        if len(self.var_title.get()) > MAX_TITLE:
            return f"Tiêu đề quá dài (> {MAX_TITLE} ký tự)."
        if len(self.txt_desc.get('1.0', 'end-1c')) > MAX_DESC:
            return f"Mô tả quá dài (> {MAX_DESC} ký tự)."
        th = self.var_thumb.get().strip()
        if th and not Path(th).is_file():
            return "File thumbnail không tồn tại."
        if self.var_sched_on.get():
            try:
                self._sched_to_rfc3339()
            except ValueError:
                return "Giờ hẹn không đúng định dạng (vd: 2026-06-20 14:30)."
        return None

    def _sched_to_rfc3339(self):
        """Chuyển 'YYYY-MM-DD HH:MM' (giờ máy) sang RFC3339 UTC mà API yêu cầu."""
        raw = self.var_sched.get().strip()
        dt = datetime.strptime(raw, "%Y-%m-%d %H:%M")
        dt_utc = dt.astimezone().astimezone(timezone.utc)
        return dt_utc.strftime("%Y-%m-%dT%H:%M:%S.0Z")

    def _on_upload(self):
        if self.worker is not None:
            return
        err = self._validate()
        if err:
            messagebox.showerror("Thiếu thông tin", err)
            return

        opts = {
            "video_path": self.var_video.get().strip(),
            "title": self.var_title.get().strip(),
            "description": self.txt_desc.get("1.0", "end-1c"),
            "tags": self._parse_tags(),
            "category_id": CATEGORIES[self.var_cat.get()],
            "privacy": PRIVACY[self.var_priv.get()],
            "made_for_kids": self.var_kids.get(),
            "thumbnail_path": self.var_thumb.get().strip() or None,
            "publish_at": self._sched_to_rfc3339() if self.var_sched_on.get() else None,
        }
        self._save_settings()
        self.pb["value"] = 0
        self.btn_upload.config(state="disabled")
        self.worker = threading.Thread(target=self._run, args=(opts,), daemon=True)
        self.worker.start()

    def _run(self, opts):
        try:
            missing = _check_deps()
            if missing:
                self.log(f"Thiếu thư viện Google API ({missing}).", "warn")
                install_deps(self.log)
                if _check_deps():
                    raise RuntimeError("Vẫn thiếu thư viện sau khi cài. Hãy cài thủ công.")
            upload_video(opts, self.log,
                         lambda p: self.q.put(("progress", p)))
        except Exception as e:
            self.log("LỖI: " + str(e), "err")
            self.log(traceback.format_exc(), "err")
        finally:
            self.q.put(("done",))

    # ---- ghi nhớ lựa chọn ----
    def _save_settings(self):
        data = {
            "title": self.var_title.get(),
            "description": self.txt_desc.get("1.0", "end-1c"),
            "tags": self.var_tags.get(),
            "category": self.var_cat.get(),
            "privacy": self.var_priv.get(),
            "made_for_kids": self.var_kids.get(),
        }
        try:
            SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
        except Exception:
            pass

    def _load_settings(self):
        if not SETTINGS_FILE.exists():
            self.log("Sẵn sàng. Lần đầu dùng: đặt client_secret.json vào thư mục cấu hình "
                     "(nút 'Mở thư mục cấu hình').", "info")
            return
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            self.var_title.set(data.get("title", ""))
            self.txt_desc.insert("1.0", data.get("description", ""))
            self.var_tags.set(data.get("tags", ""))
            if data.get("category") in CATEGORIES:
                self.var_cat.set(data["category"])
            if data.get("privacy") in PRIVACY:
                self.var_priv.set(data["privacy"])
            self.var_kids.set(bool(data.get("made_for_kids", False)))
            self._update_counters()
        except Exception:
            pass


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
