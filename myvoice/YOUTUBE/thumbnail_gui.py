# -*- coding: utf-8 -*-
"""GUI tạo thumbnail: nhập tiêu đề, số tập và chọn ảnh mèo ngẫu nhiên.

Chạy từ thư mục gốc OmniVoice:
    venv\Scripts\python myvoice\YOUTUBE\thumbnail_gui.py
"""

from __future__ import annotations

import json
import queue
import random
import threading
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from PIL import Image, ImageOps, ImageTk

import dien_tieu_de_thumbnail as renderer


STATE_FILE = Path(__file__).resolve().with_name("thumbnail_gui_state.json")
# Tiêu đề được lấy từ cùng file SEO mà công cụ đăng video dùng (kịch_bản/seoYoutube.docx).
KICHBAN_DIR = Path(__file__).resolve().parent.parent / "kịch_bản"
SEO_DOCX_FILE = KICHBAN_DIR / "seoYoutube.docx"
WINDOW_WIDTH = 1040
WINDOW_HEIGHT = 735


# ── Thêm "Số <tập>" / thẻ từ khóa theo số tập (khớp công cụ đăng video) ──────────
def add_episode_to_title(title: str, ep: str) -> str:
    """Chèn 'Số <ep>' ngay sau 'Mimi audio' trong tiêu đề (khớp số ở thumbnail).
    Không có 'Mimi audio' thì thêm vào cuối; đã có 'Số' sẵn thì giữ nguyên."""
    title = (title or "").strip()
    if not ep or not title:
        return title
    marker = "mimi audio"
    idx = title.lower().rfind(marker)
    if idx == -1:
        return f"{title} Số {ep}"
    end = idx + len(marker)
    after = title[end:]
    if after.lstrip().lower().startswith("số"):   # tránh nhân đôi khi chạy lại
        return title
    return f"{title[:end]} Số {ep}{after}".rstrip()


def add_episode_to_description(description: str, ep: str) -> str:
    """Thêm 'Số <ep>' vào dòng tiêu đề ĐẦU của mô tả (lần 'Mimi audio' xuất hiện
    đầu tiên — thường là tiêu đề ở trên cùng), để mô tả khớp với tiêu đề."""
    description = description or ""
    if not ep or not description:
        return description
    marker = "mimi audio"
    idx = description.lower().find(marker)
    if idx == -1:
        return description
    end = idx + len(marker)
    after = description[end:]
    if after.lstrip().lower().startswith("số"):
        return description
    return f"{description[:end]} Số {ep}{after}"


def ensure_brand_suffix(title: str) -> str:
    """Đảm bảo tiêu đề kết thúc bằng '| Mimi audio' (dùng cho phần COPY đăng
    YouTube). Ô nhập tiêu đề đã bỏ hậu tố này nên copy phải gắn lại."""
    title = (title or "").strip()
    if not title or title.lower().endswith("mimi audio"):
        return title
    return f"{title} | Mimi audio"


def add_episode_tag(tags, ep: str):
    """Đưa thẻ 'mimi audio số <ep>' lên ĐẦU danh sách tag (thêm nếu chưa có, hoặc
    dời lên đầu nếu đã nằm ở chỗ khác)."""
    tags = list(tags or [])
    if not ep:
        return tags
    extra = f"mimi audio số {ep}"
    rest = [t for t in tags if (t or "").strip().lower() != extra.lower()]
    return [extra] + rest


# ── Quy ước cố định khi COPY đăng YouTube ───────────────────────────────────────
FULL_TITLE_PREFIX = "[FULL]"            # luôn mở đầu tiêu đề
FULL_HASHTAGS = ("#truyenfull", "#full")  # luôn có trong mô tả
MAX_TAGS_LEN = 500                      # tổng ký tự thẻ tag (nối ', ') PHẢI <= giá trị này (giới hạn YouTube)

# Thẻ tag ƯU TIÊN BỎ TRƯỚC khi phải cắt cho vừa 500 (so khớp BỎ DẤU + không phân biệt
# hoa/thường, nên 'truyện Việt Nam' cũng khớp 'viet nam'). Thêm cụm khác vào đây nếu cần.
DEPRIORITIZED_TAG_SUBSTRINGS = ("viet nam",)


def _strip_accents(s: str) -> str:
    """Bỏ dấu tiếng Việt + viết thường để so khớp không phụ thuộc dấu/hoa thường."""
    import unicodedata
    s = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


def _is_deprioritized_tag(tag: str) -> bool:
    """True nếu thẻ nên BỎ TRƯỚC khi cắt (vd chứa 'việt nam')."""
    norm = _strip_accents(tag)
    return any(sub in norm for sub in DEPRIORITIZED_TAG_SUBSTRINGS)


def add_full_prefix(title: str) -> str:
    """Thêm '[FULL]' vào ĐẦU tiêu đề (bỏ qua nếu đã có sẵn)."""
    title = (title or "").strip()
    if not title or title.lower().startswith(FULL_TITLE_PREFIX.lower()):
        return title
    return f"{FULL_TITLE_PREFIX} {title}"


def add_full_hashtags(description: str) -> str:
    """Bổ sung hashtag '#truyenfull #full' vào CUỐI mô tả (bỏ cái đã có)."""
    description = description or ""
    low = description.lower()
    extra = [h for h in FULL_HASHTAGS if h.lower() not in low]
    if not extra:
        return description
    joined = " ".join(extra)
    if not description.strip():
        return joined
    return f"{description.rstrip()}\n{joined}"


def episode_hashtag(ep: str) -> str:
    """Hashtag tập ở ĐẦU mô tả: '#MimiAudioSo<ep>' (CamelCase, BỎ dấu — đồng bộ các
    hashtag #MimiAudio/#TruyenAudio sẵn có). ep rỗng → ''."""
    ep = (ep or "").strip()
    return f"#MimiAudioSo{ep}" if ep else ""


def add_episode_hashtag_top(description: str, ep: str) -> str:
    """Chèn hashtag tập ('#MimiAudioSo<ep>') lên ĐẦU mô tả, CÙNG DÒNG với bộ hashtag
    sẵn có (cách bằng dấu cách, KHÔNG xuống dòng).

    Bỏ qua nếu ep rỗng, hoặc mô tả đã mở đầu bằng đúng hashtag này (tránh nhân đôi
    khi copy lại)."""
    description = description or ""
    tag = episode_hashtag(ep)
    if not tag:
        return description
    if description.lstrip().lower().startswith(tag.lower()):
        return description
    if not description.strip():
        return tag
    return f"{tag} {description.lstrip()}"


def youtube_tags_len(tags) -> int:
    """Độ dài thẻ tag theo cách YOUTUBE ĐẾM cho giới hạn 500 — KHÔNG phải len chuỗi.

    YouTube bọc mỗi tag CÓ DẤU CÁCH trong ngoặc kép (+2 ký tự) rồi nối bằng dấu phẩy
    (n−1 dấu). Vì gần như mọi tag đều có dấu cách, chuỗi 481 ký tự thường (nối ', ')
    có thể bị YouTube tính thành >500 → báo vượt. Đo bằng hàm này mới khớp YouTube."""
    tags = [t for t in ((x or "").strip() for x in tags) if t]
    if not tags:
        return 0
    return sum(len(t) + (2 if " " in t else 0) for t in tags) + (len(tags) - 1)


def cap_tags(tags, ep: str, limit: int = MAX_TAGS_LEN) -> str:
    """Nối thẻ tag bằng ', ', thẻ tập ('mimi audio số <ep>') để Ở ĐẦU danh sách.

    Lấy LẦN LƯỢT từ đầu; ĐO theo cách YouTube đếm (youtube_tags_len — tag có dấu cách
    +2 cho ngoặc kép). Khi thêm 1 thẻ mà tổng VƯỢT `limit` thì BỎ thẻ đó VÀ mọi thẻ
    đứng SAU nó (cắt tại ranh giới, không nhảy cóc lấy thẻ ngắn hơn ở phía sau)."""
    tag_list = add_episode_tag(tags, ep)   # thẻ tập đã ở ĐẦU danh sách
    # Dời các thẻ ƯU TIÊN BỎ (vd chứa 'việt nam') xuống CUỐI để khi cắt cho vừa 500
    # chúng bị bỏ TRƯỚC các thẻ khác. Giữ nguyên thứ tự tương đối trong từng nhóm;
    # thẻ tập ('mimi audio số <ep>') không dính nên vẫn nằm đầu.
    tag_list = ([t for t in tag_list if not _is_deprioritized_tag(t)]
                + [t for t in tag_list if _is_deprioritized_tag(t)])
    kept: list[str] = []
    for t in tag_list:
        t = (t or "").strip()
        if not t:
            continue
        if youtube_tags_len(kept + [t]) <= limit:
            kept.append(t)
        else:
            break            # thẻ này vượt limit (YouTube) → bỏ nó và các thẻ sau
    return ", ".join(kept)


class ThumbnailGUI:
    def __init__(self, root, embed: bool = False, on_done=None, on_upload_scripts=None):
        self.root = root
        self.on_done = on_done
        # Nút "Tải kịch bản lên Drive" (chủ động): callback do app cha cấp, tải kịch
        # bản của CẢ trường hợp nhiều link (kịch_bản/<số tập>/input.txt) lẫn 1 link
        # (kịch_bản/input.txt). None → không hiện nút (chạy thumbnail_gui.py độc lập).
        self.on_upload_scripts = on_upload_scripts
        # embed=True → nhúng vào 1 Frame của app khác (không gọi method của cửa sổ
        # như title/geometry/protocol, và không tự căn giữa màn hình).
        self.embed = embed
        if not embed:
            self.root.title("Tạo thumbnail YouTube")
            self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
            self.root.minsize(920, 650)
            self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.configure(bg="#F4F6FB")

        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.photos = renderer.list_photo_files(renderer.CAT_IMAGE_DIR)
        self.selected_photo: Path | None = None
        self.preview_image: ImageTk.PhotoImage | None = None
        self.running = False

        self.number_var = tk.StringVar(value=self._load_episode_number())
        # Tự LƯU số tập mỗi khi thay đổi (gõ tay hoặc +/−) → các công cụ khác luôn đọc
        # đúng số hiện tại (vd chữ 'Mimi audio Số N' trên video TikTok).
        self.number_var.trace_add("write", lambda *_: self._save_episode_number())
        self.photo_name_var = tk.StringVar(value="Chưa chọn ảnh")
        self.status_var = tk.StringVar(value="Sẵn sàng")
        self.output_var = tk.StringVar(value="")

        self._build_ui()
        self._autofill_title_from_seo()   # điền sẵn tiêu đề từ seoYoutube.docx (giống file đăng video)
        self._choose_random_photo()
        self.root.after(100, self._poll_events)
        if not embed:
            self.root.after(120, self._center_window)

    @staticmethod
    def _load_episode_number() -> str:
        """Đọc số tập gần nhất; lỗi/mất file thì quay về 01."""
        try:
            saved = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            number = str(saved.get("episode_number", "")).strip()
            if number.isdecimal():
                return number.zfill(max(2, len(number)))
        except (OSError, ValueError, json.JSONDecodeError):
            pass
        return renderer.DEFAULT_NUMBER

    def _save_episode_number(self) -> None:
        number = self.number_var.get().strip()
        if not number.isdecimal():
            return
        try:
            STATE_FILE.write_text(
                json.dumps({"episode_number": number}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            # Không làm gián đoạn GUI nếu thư mục không cho ghi cấu hình.
            pass

    def _center_window(self) -> None:
        # Dùng kích thước đặt sẵn thay vì winfo_width() khi Tk vừa khởi tạo (lúc đó
        # Windows đôi khi trả về 1×1, khiến góc trái trên nằm đúng giữa màn hình).
        x = max(0, (self.root.winfo_screenwidth() - WINDOW_WIDTH) // 2)
        y = max(0, (self.root.winfo_screenheight() - WINDOW_HEIGHT) // 2)
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}+{x}+{y}")

    def _setup_style(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        # Khi nhúng (embed) thì KHÔNG ghi đè style dùng chung (TEntry) để không làm
        # đổi giao diện của app chủ. Các nút dùng tên style riêng "Thumb*" cho an toàn.
        if not self.embed:
            style.configure("TEntry", padding=8, font=("Segoe UI", 11))
        style.configure("Thumb.TButton", background="#6D5CE8", foreground="white", padding=(18, 11), font=("Segoe UI", 11, "bold"))
        style.map("Thumb.TButton", background=[("active", "#5946D8"), ("disabled", "#C9C3F4")])
        style.configure("ThumbSoft.TButton", background="#EEEAFE", foreground="#5140C8", padding=(13, 8), font=("Segoe UI", 10, "bold"))
        style.map("ThumbSoft.TButton", background=[("active", "#E0DBFB")])
        style.configure("ThumbStepper.TButton", background="#E7E3FC", foreground="#5140C8", padding=(7, 3), font=("Segoe UI", 13, "bold"))
        style.map("ThumbStepper.TButton", background=[("active", "#D8D1FA")])

    @staticmethod
    def _card(parent: tk.Misc) -> tk.Frame:
        return tk.Frame(
            parent,
            bg="white",
            highlightbackground="#E4E8F1",
            highlightthickness=1,
            padx=22,
            pady=20,
        )

    def _build_ui(self) -> None:
        self._setup_style()

        # Khi nhúng (embed) thì làm gọn banner + lề để chừa chỗ cho các nút bên dưới
        # không bị che/mất trong cửa sổ app chủ (vốn thấp hơn cửa sổ độc lập).
        header = tk.Frame(self.root, bg="#302B63", height=70 if self.embed else 120)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(
            header,
            text="THUMBNAIL STUDIO",
            bg="#302B63",
            fg="#FFFFFF",
            font=("Segoe UI", 15 if self.embed else 19, "bold"),
        ).pack(anchor="w", padx=34, pady=((12 if self.embed else 22), 2))
        tk.Label(
            header,
            text="Nhập tiêu đề · đánh số tập · chọn ảnh mèo ngẫu nhiên · tạo thumbnail chỉ với một nút bấm",
            bg="#302B63",
            fg="#D9D4FF",
            font=("Segoe UI", 9 if self.embed else 10),
        ).pack(anchor="w", padx=34)

        main = tk.Frame(self.root, bg="#F4F6FB", padx=24, pady=12 if self.embed else 22)
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=6, minsize=510)
        main.columnconfigure(1, weight=4, minsize=350)
        main.rowconfigure(0, weight=1)

        input_card = self._card(main)
        input_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        input_card.columnconfigure(0, weight=1)

        tk.Label(input_card, text="Nội dung thumbnail", bg="white", fg="#1F2440", font=("Segoe UI", 15, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        tk.Label(
            input_card,
            text="Thiết kế tự căn giữa, xuống dòng và phóng to theo độ dài tiêu đề.",
            bg="white",
            fg="#697386",
            font=("Segoe UI", 10),
        ).grid(row=1, column=0, sticky="w", pady=(3, 17))

        tk.Label(input_card, text="TIÊU ĐỀ", bg="white", fg="#4A5568", font=("Segoe UI", 9, "bold")).grid(
            row=2, column=0, sticky="w", pady=(0, 6)
        )
        self.title_text = tk.Text(
            input_card,
            height=4 if self.embed else 5,
            wrap="word",
            font=("Segoe UI", 13),
            bg="#FBFCFF",
            fg="#1F2440",
            insertbackground="#6D5CE8",
            relief="solid",
            borderwidth=1,
            highlightthickness=1,
            highlightbackground="#DFE4EE",
            highlightcolor="#8A7CF0",
            padx=12,
            pady=10,
        )
        self.title_text.grid(row=3, column=0, sticky="ew")

        number_card = tk.Frame(input_card, bg="#F8F7FF", padx=14, pady=12, highlightbackground="#E6E1FF", highlightthickness=1)
        number_card.grid(row=4, column=0, sticky="ew", pady=(16, 0))
        number_card.columnconfigure(1, weight=1)
        tk.Label(number_card, text="Số tập", bg="#F8F7FF", fg="#38305F", font=("Segoe UI", 11, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Entry(number_card, textvariable=self.number_var, width=9, justify="center", font=("Segoe UI", 14, "bold")).grid(
            row=0, column=1, sticky="e"
        )
        stepper = tk.Frame(number_card, bg="#F8F7FF")
        stepper.grid(row=0, column=2, sticky="e", padx=(8, 0))
        ttk.Button(stepper, text="−", style="ThumbStepper.TButton", width=3, command=lambda: self._change_episode(-1)).pack(
            side="left", padx=(0, 4)
        )
        ttk.Button(stepper, text="+", style="ThumbStepper.TButton", width=3, command=lambda: self._change_episode(1)).pack(
            side="left"
        )
        tk.Label(number_card, text="Ví dụ: 01, 02, 15", bg="#F8F7FF", fg="#77708E", font=("Segoe UI", 9)).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(4, 0)
        )

        separator = tk.Frame(input_card, bg="#EBEEF5", height=1)
        separator.grid(row=5, column=0, sticky="ew", pady=18)

        photo_header = tk.Frame(input_card, bg="white")
        photo_header.grid(row=6, column=0, sticky="ew")
        photo_header.columnconfigure(0, weight=1)
        tk.Label(photo_header, text="Ảnh mèo ngẫu nhiên", bg="white", fg="#1F2440", font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        self.random_button = ttk.Button(photo_header, text="↻ Đổi ảnh", style="ThumbSoft.TButton", command=self._choose_random_photo)
        self.random_button.grid(row=0, column=1, sticky="e")
        tk.Label(
            input_card,
            textvariable=self.photo_name_var,
            bg="white",
            fg="#697386",
            font=("Segoe UI", 10),
            anchor="w",
            wraplength=430,
        ).grid(row=7, column=0, sticky="w", pady=(6, 18))

        action = tk.Frame(input_card, bg="white")
        action.grid(row=8, column=0, sticky="ew")
        status_col = 2 if self.on_upload_scripts else 1
        action.columnconfigure(status_col, weight=1)
        self.create_button = ttk.Button(action, text="✦ Tạo thumbnail", style="Thumb.TButton", command=self._start_render)
        self.create_button.grid(row=0, column=0, sticky="w")
        # Nút CHỦ ĐỘNG tải kịch bản lên Drive — tải cả nhiều link lẫn 1 link. Không
        # còn tự động tải khi tạo thumbnail; chỉ tải khi bấm nút này.
        self.upload_drive_button = None
        if self.on_upload_scripts:
            self.upload_drive_button = ttk.Button(
                action,
                text="⬆ Tải kịch bản lên Drive",
                style="ThumbSoft.TButton",
                command=self._on_upload_scripts_click,
            )
            self.upload_drive_button.grid(row=0, column=1, sticky="w", padx=(10, 0))
        self.status_label = tk.Label(action, textvariable=self.status_var, bg="white", fg="#6D5CE8", font=("Segoe UI", 10, "bold"))
        self.status_label.grid(row=0, column=status_col, sticky="e")

        # 3 nút COPY nội dung đăng YouTube (lấy từ seoYoutube.docx + 'Số <tập>').
        copy_row = tk.Frame(input_card, bg="white")
        copy_row.grid(row=9, column=0, sticky="ew", pady=(16, 0))
        ttk.Button(copy_row, text="📋 Tiêu đề", style="ThumbSoft.TButton",
                   command=self._copy_title).pack(side="left")
        ttk.Button(copy_row, text="📋 Mô tả", style="ThumbSoft.TButton",
                   command=self._copy_description).pack(side="left", padx=(8, 0))
        ttk.Button(copy_row, text="📋 Thẻ tag", style="ThumbSoft.TButton",
                   command=self._copy_tags).pack(side="left", padx=(8, 0))
        tk.Label(
            input_card,
            text="Tiêu đề & mô tả tự thêm “Số <tập>”; thẻ tag thêm “mimi audio số <tập>”.",
            bg="white", fg="#697386", font=("Segoe UI", 9), anchor="w", wraplength=430,
        ).grid(row=10, column=0, sticky="w", pady=(6, 0))

        preview_card = self._card(main)
        preview_card.grid(row=0, column=1, sticky="nsew", padx=(12, 0))
        preview_card.columnconfigure(0, weight=1)
        preview_card.rowconfigure(2, weight=1)
        tk.Label(preview_card, text="Xem trước ảnh mèo", bg="white", fg="#1F2440", font=("Segoe UI", 15, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        tk.Label(
            preview_card,
            text=f"Tự chọn từ {len(self.photos)} ảnh trong thư mục Anh",
            bg="white",
            fg="#697386",
            font=("Segoe UI", 10),
        ).grid(row=1, column=0, sticky="w", pady=(3, 16))
        preview_shell = tk.Frame(preview_card, bg="#F5F6FA", highlightbackground="#E2E6EF", highlightthickness=1)
        preview_shell.grid(row=2, column=0, sticky="nsew")
        self.preview_label = tk.Label(preview_shell, bg="#F5F6FA", anchor="center")
        self.preview_label.pack(fill="both", expand=True, padx=10, pady=10)

        output_card = tk.Frame(preview_card, bg="#F8FAFE", padx=12, pady=11, highlightbackground="#E1E8F4", highlightthickness=1)
        output_card.grid(row=3, column=0, sticky="ew", pady=(16, 0))
        tk.Label(output_card, text="FILE KẾT QUẢ", bg="#F8FAFE", fg="#607089", font=("Segoe UI", 8, "bold")).pack(anchor="w")
        tk.Label(
            output_card,
            textvariable=self.output_var,
            bg="#F8FAFE",
            fg="#285EA8",
            font=("Segoe UI", 9),
            justify="left",
            anchor="w",
            wraplength=310,
        ).pack(anchor="w", pady=(4, 0))

    def _autofill_title_from_seo(self) -> None:
        """Tự điền tiêu đề từ kịch_bản/seoYoutube.docx — cùng nguồn với công cụ đăng video.

        Chỉ điền khi ô tiêu đề đang trống; thiếu file/thư viện thì im lặng bỏ qua.
        """
        if self.title_text.get("1.0", "end").strip():
            return
        if not SEO_DOCX_FILE.exists():
            return
        try:
            from seo_docx_parser import parse_seo_docx
            seo = parse_seo_docx(SEO_DOCX_FILE)
        except Exception:
            return
        # Ô nhập (và chữ trên thumbnail) bỏ hậu tố '| Mimi audio'; nút Copy tiêu
        # đề sẽ tự gắn lại hậu tố này khi đăng YouTube.
        title = renderer.strip_brand_suffix((seo.get("title") or "").strip())
        if title:
            self.title_text.insert("1.0", title)
            self.status_var.set(f"Đã điền tiêu đề từ {SEO_DOCX_FILE.name}")

    def _choose_random_photo(self) -> None:
        if self.running:
            return
        if not self.photos:
            messagebox.showerror("Không có ảnh", f"Không tìm thấy ảnh trong:\n{renderer.CAT_IMAGE_DIR}")
            return
        choices = [path for path in self.photos if path != self.selected_photo] or self.photos
        self.selected_photo = random.choice(choices)
        self.photo_name_var.set(f"Đang dùng: {self.selected_photo.name}")
        self._update_preview(self.selected_photo)

    def _update_preview(self, photo_path: Path) -> None:
        image = Image.open(photo_path).convert("RGBA")
        image = ImageOps.contain(image, (410, 260), method=Image.Resampling.LANCZOS)
        background = Image.new("RGBA", (420, 310), (245, 246, 250, 255))
        offset = ((background.width - image.width) // 2, (background.height - image.height) // 2)
        background.alpha_composite(image, dest=offset)
        self.preview_image = ImageTk.PhotoImage(background)
        self.preview_label.configure(image=self.preview_image)

    def _change_episode(self, delta: int) -> None:
        current = self.number_var.get().strip()
        if not current.isdecimal():
            messagebox.showerror("Số tập không hợp lệ", "Số tập chỉ gồm các chữ số, ví dụ 01 hoặc 12.", parent=self.root)
            return
        width = max(2, len(current))
        next_number = max(0, int(current) + delta)
        self.number_var.set(str(next_number).zfill(width))
        self._save_episode_number()

    # ── 3 nút COPY: tiêu đề / mô tả / thẻ tag (đã gắn 'Số <tập>') ───────────────
    def _episode_number(self) -> str:
        ep = self.number_var.get().strip()
        return ep if ep.isdecimal() else ""

    def _read_seo(self) -> dict:
        """Đọc seoYoutube.docx → {title, description, tags}. Lỗi thì trả rỗng + báo."""
        try:
            from seo_docx_parser import parse_seo_docx
            return parse_seo_docx(SEO_DOCX_FILE)
        except Exception as e:
            self.status_var.set(f"Lỗi đọc SEO: {e}")
            return {"title": "", "description": "", "tags": []}

    def _copy_text(self, text: str, what: str) -> None:
        text = text or ""
        if not text.strip():
            self.status_var.set(f"Không có {what} để copy (kiểm tra seoYoutube.docx).")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status_var.set(f"✓ Đã copy {what} ({len(text)} ký tự)")

    def _copy_title(self) -> None:
        # Tiêu đề copy LẤY THẲNG TỪ tài liệu SEO (seoYoutube.docx) + số tập — KHÔNG
        # lấy từ ô nhập (ô nhập đã bỏ '| Mimi audio' cho thumbnail). SEO đã có sẵn
        # '| Mimi audio'; ensure_brand_suffix chỉ phòng khi SEO thiếu hậu tố.
        title = ensure_brand_suffix(self._read_seo().get("title", ""))
        title = add_episode_to_title(title, self._episode_number())
        self._copy_text(add_full_prefix(title), "tiêu đề")

    def _copy_description(self) -> None:
        seo = self._read_seo()
        ep = self._episode_number()
        desc = add_episode_to_description(seo.get("description", ""), ep)
        desc = add_episode_hashtag_top(desc, ep)      # '#MimiAudioSo<ep>' lên đầu
        self._copy_text(add_full_hashtags(desc), "mô tả")

    def _copy_tags(self) -> None:
        seo = self._read_seo()
        self._copy_text(cap_tags(seo.get("tags", []), self._episode_number()), "thẻ tag")

    def _on_upload_scripts_click(self) -> None:
        """Bấm nút 'Tải kịch bản lên Drive' → gọi callback của app cha. Callback tự
        chạy nền và tự bật/tắt nút qua tham chiếu _thumb_gui.upload_drive_button."""
        if not self.on_upload_scripts:
            return
        try:
            self.on_upload_scripts()
        except Exception as e:
            self.status_var.set(f"Lỗi tải kịch bản: {e}")

    def _start_render(self) -> None:
        if self.running:
            return
        title = self.title_text.get("1.0", "end").strip()
        number = self.number_var.get().strip()
        if not title:
            messagebox.showerror("Thiếu tiêu đề", "Hãy nhập tiêu đề thumbnail.", parent=self.root)
            return
        if not number:
            messagebox.showerror("Thiếu số", "Hãy nhập số tập, ví dụ 01.", parent=self.root)
            return
        if self.selected_photo is None:
            messagebox.showerror("Thiếu ảnh", "Hãy chọn ảnh ngẫu nhiên trước.", parent=self.root)
            return

        self.running = True
        self.create_button.configure(state="disabled")
        self.random_button.configure(state="disabled")
        self.status_var.set("Đang tạo...")
        self.status_label.configure(fg="#D97706")
        self.output_var.set("")
        threading.Thread(
            target=self._render_worker,
            args=(title, number, self.selected_photo),
            daemon=True,
        ).start()

    def _render_worker(self, title: str, number: str, photo_path: Path) -> None:
        try:
            output = renderer.add_title(
                renderer.SOURCE_IMAGE,
                renderer.next_thumbnail_path(),
                title,
                photo_path,
                renderer.FRAME_IMAGE,
                number,
                renderer.NUMBER_FRAME_IMAGE,
            )
            # Bản DỌC (1080×1920): cùng ảnh + tiêu đề + số tập, tên thêm hậu tố _doc.
            # Lỗi bản dọc không chặn bản ngang — ghi lại để báo nhẹ trong trạng thái.
            output_doc, doc_error = "", ""
            try:
                output_doc = str(renderer.add_title_vertical(
                    output.with_name(f"{output.stem}_doc{output.suffix}"),
                    title,
                    photo_path,
                    number,
                ))
            except Exception as exc:
                doc_error = str(exc)
            self.events.put(("done", {
                "output": str(output),
                "output_doc": output_doc,
                "doc_error": doc_error,
                "title": title,
                "number": number,
            }))
        except BaseException:
            self.events.put(("error", traceback.format_exc()))

    def _poll_events(self) -> None:
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "done":
                    info = value if isinstance(value, dict) else {"output": str(value)}
                    output = str(info.get("output", ""))
                    output_doc = str(info.get("output_doc", ""))
                    doc_error = str(info.get("doc_error", ""))
                    self.running = False
                    self.create_button.configure(state="normal")
                    self.random_button.configure(state="normal")
                    self.status_var.set("Hoàn tất" if not doc_error else "Xong bản ngang (bản dọc lỗi)")
                    self.status_label.configure(fg="#15803D" if not doc_error else "#D97706")
                    self.output_var.set(output + (f"\n{output_doc}" if output_doc else ""))
                    lines = [f"Thumbnail ngang:\n{output}"]
                    if output_doc:
                        lines.append(f"Thumbnail dọc:\n{output_doc}")
                    if doc_error:
                        lines.append(f"(Bản dọc lỗi: {doc_error})")
                    messagebox.showinfo("Hoàn tất", "\n\n".join(lines), parent=self.root)
                elif kind == "error":
                    self.running = False
                    self.create_button.configure(state="normal")
                    self.random_button.configure(state="normal")
                    self.status_var.set("Có lỗi")
                    self.status_label.configure(fg="#DC2626")
                    self.output_var.set(value)
                    messagebox.showerror("Tạo thumbnail thất bại", "Xem lỗi hiển thị bên dưới.", parent=self.root)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_events)

    def _on_close(self) -> None:
        if self.running:
            messagebox.showwarning("Đang tạo thumbnail", "Hãy đợi quá trình tạo thumbnail hoàn tất trước khi đóng.", parent=self.root)
            return
        self._save_episode_number()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    ThumbnailGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
