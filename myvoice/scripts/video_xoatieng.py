# -*- coding: utf-8 -*-
"""
Xóa âm thanh gốc + chuẩn hóa khung hình (tỷ lệ đồng nhất) cho video tải về.

Hai cách dùng:
  • KHÔNG tham số  → mở GIAO DIỆN (GUI):
        - Chọn nhiều video cần xử lý (mặc định mở ở thư mục Downloads).
        - Chọn khung hình đích: Ngang 1920×1080 hoặc Dọc 1080×1920.
        - Video KHÁC tỷ lệ được CẮT ĐẦY KHUNG (crop, KHÔNG viền đen).
        - Tùy chọn CẮT BỎ số giây đầu / cuối mỗi video (0 = không cắt).
        - Chọn thư mục đầu ra (mặc định myvoice/videongang) + tiền tố tên.
        - Đặt tên tuần tự: <tiền tố><số>.mp4 (vd nauan01.mp4, nauan02.mp4…),
          tự nối tiếp số lớn nhất đang có trong thư mục đích (chạy lại không đè).
        - GIỮ NGUYÊN file gốc trong Downloads (không xóa).
        - Ưu tiên GPU (NVENC), tự fallback CPU (libx264).

  • --batch        → luồng CŨ: xóa tiếng + scale mọi .mp4 trong mp4/ sang
                     mp4_no_audio/ (đầu vào cho video_ghepcuoi.py). Giữ nguyên
                     hành vi trước đây để không phá pipeline final_video.

Yêu cầu: ffmpeg + ffprobe có trong PATH.
  pip install tqdm  (tùy chọn, cho thanh tiến trình ở chế độ --batch)
"""

import argparse
import io
import json
import re
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent.parent   # myvoice/

# ── Mặc định cho GUI ────────────────────────────────────────────────────────
DOWNLOADS_DIR   = Path.home() / "Downloads"
DEFAULT_OUT_DIR = BASE_DIR / "videongang"
DEFAULT_PREFIX  = "nauan"
FPS             = 30            # ép cùng 30fps, khớp pipeline ghép (video_khung.py)
NUM_DIGITS      = 2            # nauan01, nauan02… (tự dài thêm khi vượt 99)
VIDEO_EXTS      = {".mp4", ".mov", ".mkv", ".avi", ".flv", ".webm", ".m4v", ".wmv", ".ts"}

# Khung hình đích cho GUI: nhãn -> (rộng, cao).
TARGETS = {
    "Ngang 1920×1080": (1920, 1080),
    "Dọc 1080×1920":   (1080, 1920),
}

# Ưu tiên GPU; tự fallback CPU nếu GPU lỗi.
USE_GPU     = True
NVENC_ARGS  = ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "20"]
X264_ARGS   = ["-c:v", "libx264", "-preset", "medium", "-crf", "20"]

# ── Luồng CŨ (--batch): xóa tiếng + scale mp4/ -> mp4_no_audio/ ──────────────
SRC_DIR = BASE_DIR / "mp4"
DST_DIR = BASE_DIR / "mp4_no_audio"
SCALE_FILTER = "scale=1080:-2"   # dọc 1080p, giữ tỷ lệ gốc (giữ nguyên hành vi cũ)


# ════════════════════════════════ Tiện ích ffmpeg ═══════════════════════════
def _run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def has_nvenc() -> bool:
    """ffmpeg có encoder h264_nvenc (GPU NVIDIA) hay không."""
    r = _run(["ffmpeg", "-hide_banner", "-encoders"])
    return r.returncode == 0 and "h264_nvenc" in r.stdout


def probe_stream(path: Path):
    """Trả về (codec_name, width, height) hoặc None nếu không đọc được."""
    r = _run(["ffprobe", "-v", "error", "-select_streams", "v:0",
              "-show_entries", "stream=codec_name,width,height",
              "-of", "json", str(path)])
    if r.returncode != 0:
        return None
    try:
        s = json.loads(r.stdout)["streams"][0]
        return s.get("codec_name", ""), int(s["width"]), int(s["height"])
    except (ValueError, KeyError, IndexError):
        return None


def get_resolution(path: Path) -> str:
    """Trả về '1920×1080' hoặc 'unknown' (chỉ để log)."""
    r = _run(["ffprobe", "-v", "error", "-select_streams", "v:0",
              "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path)])
    return r.stdout.strip().replace(",", "×") if r.returncode == 0 else "unknown"


def probe_duration(path: Path):
    """Trả về thời lượng (giây, float) hoặc None nếu không đọc được."""
    r = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
              "-of", "default=nw=1:nk=1", str(path)])
    try:
        return float(r.stdout.strip())
    except ValueError:
        return None


def _ff(cmd):
    """Chạy ffmpeg, trả về (ok, dòng lỗi cuối)."""
    r = _run(cmd)
    err = r.stderr.strip().splitlines()[-1] if r.stderr.strip() else ""
    return r.returncode == 0, err


# ═══════════════════════ Đặt tên tuần tự trong thư mục đích ══════════════════
def next_index(out_dir: Path, prefix: str) -> int:
    """Số thứ tự kế tiếp: max(<prefix><số>.mp4) hiện có + 1 (mặc định 1)."""
    pat = re.compile(rf"^{re.escape(prefix)}(\d+)\.mp4$", re.IGNORECASE)
    mx = 0
    if out_dir.is_dir():
        for f in out_dir.iterdir():
            m = pat.match(f.name)
            if m:
                mx = max(mx, int(m.group(1)))
    return mx + 1


def out_name(prefix: str, index: int) -> str:
    return f"{prefix}{index:0{NUM_DIGITS}d}.mp4"


# ═══════════════ Xử lý 1 video: xóa tiếng + chuẩn hóa (CẮT ĐẦY KHUNG) ════════
def process_one(src: Path, dst: Path, tw: int, th: int, use_gpu: bool,
                trim_start: float = 0.0, trim_end: float = 0.0):
    """Xóa tiếng + đưa video về đúng tw×th bằng CROP (cắt đầy khung, không viền đen).

    trim_start / trim_end: số giây cắt bỏ ở đầu / cuối (0 = không cắt).

    - Không cắt + clip ĐÃ đúng (h264 + đúng kích thước) -> chỉ COPY + bỏ tiếng (~tức thì).
    - Còn lại: (cắt bằng -ss/-t chính xác) + scale phủ kín + crop giữa về tw×th,
      ép 30fps, encode lại. Ưu tiên NVENC; lỗi thì thử không hwaccel, rồi libx264.
    Trả về (ok: bool, mô tả: str).
    """
    info = probe_stream(src)
    if info is None:
        return False, "không đọc được luồng video"
    codec, w, h = info

    trimming = trim_start > 0 or trim_end > 0

    # Cắt: tính thời lượng còn lại để giới hạn bằng -t.
    tt = []
    trim_desc = ""
    if trimming:
        total = probe_duration(src)
        if total is None:
            return False, "không đọc được thời lượng để cắt"
        out_dur = total - trim_start - trim_end
        if out_dur <= 0.05:
            return False, f"cắt quá dài (còn {out_dur:.2f}s)"
        tt = ["-t", f"{out_dur:.3f}"]
        parts = []
        if trim_start > 0:
            parts.append(f"-{trim_start:g}s đầu")
        if trim_end > 0:
            parts.append(f"-{trim_end:g}s cuối")
        trim_desc = " · cắt " + ", ".join(parts)
    # -ss trước -i: tua nhanh nhưng vẫn chính xác khi có re-encode.
    ss = ["-ss", f"{trim_start:.3f}"] if trim_start > 0 else []

    # 1) Không cắt + đã đúng định dạng đích -> copy nguyên luồng, chỉ bỏ tiếng.
    if not trimming and codec == "h264" and w == tw and h == th:
        ok, err = _ff(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                       "-i", str(src), "-c", "copy", "-an",
                       "-movflags", "+faststart", str(dst)])
        if ok:
            return True, f"copy ({w}×{h})"
        if dst.exists():
            dst.unlink()

    # 2) Encode: (cắt) + scale phủ kín (increase) + crop giữa về tw×th, ép 30fps.
    vf = (f"scale={tw}:{th}:force_original_aspect_ratio=increase,"
          f"crop={tw}:{th},setsar=1,fps={FPS}")
    enc = NVENC_ARGS if use_gpu else X264_ARGS
    base = "-hide_banner", "-loglevel", "error"

    # Lần lượt thử: GPU(hwaccel) → cùng encoder không hwaccel → CPU libx264.
    attempts = []
    if use_gpu:
        attempts.append((["ffmpeg", "-y", *base, "-hwaccel", "cuda", *ss,
                          "-i", str(src), *tt, "-vf", vf, "-an", *NVENC_ARGS,
                          "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(dst)],
                         f"crop {w}×{h} → {tw}×{th}{trim_desc}"))
    attempts.append((["ffmpeg", "-y", *base, *ss, "-i", str(src), *tt,
                      "-vf", vf, "-an", *enc,
                      "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(dst)],
                     f"crop {w}×{h} → {tw}×{th}{trim_desc}"))
    if use_gpu:
        attempts.append((["ffmpeg", "-y", *base, *ss, "-i", str(src), *tt,
                          "-vf", vf, "-an", *X264_ARGS,
                          "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(dst)],
                         f"crop {w}×{h} → {tw}×{th}{trim_desc} (CPU)"))

    err = "ffmpeg lỗi"
    for cmd, desc in attempts:
        ok, err = _ff(cmd)
        if ok:
            return True, desc
        if dst.exists():
            dst.unlink()

    return False, err or "ffmpeg lỗi"


def run_files(files, out_dir: Path, prefix: str, tw: int, th: int,
              trim_start: float = 0.0, trim_end: float = 0.0,
              log=print, progress=None):
    """Xử lý danh sách file đã chọn. GIỮ NGUYÊN file gốc.

    trim_start / trim_end: số giây cắt bỏ ở đầu / cuối mỗi video (0 = không cắt).
    progress(done, total) (tùy chọn) để GUI cập nhật thanh tiến trình.
    Trả về (số ok, số lỗi).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    use_gpu = USE_GPU and has_nvenc()
    log("Encoder: GPU (h264_nvenc), fallback CPU (libx264)"
        if use_gpu else "Encoder: CPU (libx264)")
    log(f"Khung hình: {tw}×{th}  ·  chế độ CẮT ĐẦY KHUNG (không viền đen)")
    if trim_start > 0 or trim_end > 0:
        log(f"Cắt bỏ    : {trim_start:g}s đầu · {trim_end:g}s cuối (mỗi video)")
    log(f"Đầu ra    : {out_dir}   ·  tiền tố '{prefix}'")
    log(f"Số video  : {len(files)}")
    log("-" * 54)

    idx = next_index(out_dir, prefix)
    ok = fail = 0
    total = len(files)
    for i, f in enumerate(files, 1):
        src = Path(f)
        dst = out_dir / out_name(prefix, idx)
        good, how = process_one(src, dst, tw, th, use_gpu, trim_start, trim_end)
        if good:
            log(f"  [OK] {src.name}  →  {dst.name}  ({how})")
            ok += 1
            idx += 1
        else:
            log(f"  [LỖI] {src.name}  —  {how}")
            fail += 1
        if progress:
            progress(i, total)

    log("-" * 54)
    log(f"Hoàn tất — thành công: {ok}, lỗi: {fail}")
    log(f"Kết quả: {out_dir}")
    return ok, fail


# ═════════════════════════════════ GIAO DIỆN ════════════════════════════════
def _build_gui(root):
    """Dựng widget vào `root` (tách riêng để test được mà không mainloop)."""
    import queue
    import threading
    import tkinter as tk
    from tkinter import ttk, filedialog, scrolledtext

    # ── Bảng màu (nền trắng, phẳng, hiện đại — đồng bộ với GUI tạo giọng) ────
    C = dict(
        bg="#ffffff", card="#ffffff", border="#e4e7ec", field="#ffffff",
        fg="#1f2430", muted="#7b828f",
        accent="#e84393", accent_dk="#c92f7b", accent_soft="#f4c4dc",
        track="#edeff2", hover="#f1f3f6", press="#e6e9ee",
        log_bg="#fbfbfc", log_ok="#2e9e5b", log_warn="#b07400",
        log_err="#d62828", log_muted="#9aa1ad",
    )
    base_font, small_font = ("Segoe UI", 10), ("Segoe UI", 9)

    root.title("Xóa tiếng & chuẩn hóa video")
    root.configure(bg=C["bg"])

    try:
        st = ttk.Style(root)
        st.theme_use("clam")
        st.configure(".", background=C["bg"], foreground=C["fg"], font=base_font,
                     bordercolor=C["border"], focuscolor=C["bg"],
                     troughcolor=C["track"])
        st.configure("TFrame", background=C["bg"])
        st.configure("TLabel", background=C["card"], foreground=C["fg"])
        st.configure("Header.TLabel", font=("Segoe UI", 17, "bold"),
                     foreground=C["fg"], background=C["bg"])
        st.configure("Sub.TLabel", font=small_font, foreground=C["muted"],
                     background=C["bg"])
        st.configure("Hint.TLabel", font=small_font, foreground=C["muted"])
        st.configure("Field.TLabel", foreground=C["muted"])

        # Thẻ (card) viền nhẹ, tiêu đề hồng đậm
        st.configure("Card.TLabelframe", background=C["card"],
                     bordercolor=C["border"], relief="solid", borderwidth=1,
                     padding=14)
        st.configure("Card.TLabelframe.Label", background=C["card"],
                     foreground=C["accent"], font=("Segoe UI", 10, "bold"))

        # Nhập liệu
        st.configure("TEntry", fieldbackground=C["field"], bordercolor=C["border"],
                     lightcolor=C["border"], darkcolor=C["border"],
                     insertcolor=C["fg"], padding=6)
        st.map("TEntry", bordercolor=[("focus", C["accent"])],
               lightcolor=[("focus", C["accent"])])
        st.configure("TCombobox", fieldbackground=C["field"], background=C["field"],
                     bordercolor=C["border"], lightcolor=C["border"],
                     darkcolor=C["border"], arrowcolor=C["muted"], padding=6)
        st.map("TCombobox",
               fieldbackground=[("readonly", C["field"])],
               foreground=[("readonly", C["fg"])],
               selectbackground=[("readonly", C["field"])],
               selectforeground=[("readonly", C["fg"])],
               bordercolor=[("focus", C["accent"])],
               lightcolor=[("focus", C["accent"])])
        root.option_add("*TCombobox*Listbox.background", C["field"])
        root.option_add("*TCombobox*Listbox.foreground", C["fg"])
        root.option_add("*TCombobox*Listbox.selectBackground", C["accent"])
        root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
        root.option_add("*TCombobox*Listbox.font", base_font)

        # Nút phụ (xám nhạt) + nút chính (hồng)
        st.configure("TButton", background="#eef0f3", foreground=C["fg"],
                     bordercolor=C["border"], relief="flat", focusthickness=0,
                     padding=(14, 7), font=base_font)
        st.map("TButton",
               background=[("active", C["hover"]), ("pressed", C["press"]),
                           ("disabled", "#f4f5f7")],
               foreground=[("disabled", "#aeb4be")])
        st.configure("Accent.TButton", foreground="#ffffff", background=C["accent"],
                     font=("Segoe UI", 11, "bold"), padding=(24, 10),
                     relief="flat", focusthickness=0)
        st.map("Accent.TButton",
               background=[("active", C["accent_dk"]), ("pressed", C["accent_dk"]),
                           ("disabled", C["accent_soft"])],
               foreground=[("disabled", "#ffffff")])

        # Thanh tiến trình
        st.configure("TProgressbar", background=C["accent"], troughcolor=C["track"],
                     bordercolor=C["track"], lightcolor=C["accent"],
                     darkcolor=C["accent"], thickness=12)
    except tk.TclError:
        pass

    log_q: "queue.Queue" = queue.Queue()
    busy = {"v": False}
    picked = {"files": []}       # danh sách file đã chọn

    # ── Trạng thái (dùng StringVar để tách khỏi thứ tự tạo widget) ───────────
    src_status     = tk.StringVar(value="(chưa chọn)")
    out_var        = tk.StringVar(value=str(DEFAULT_OUT_DIR))
    prefix_var     = tk.StringVar(value=DEFAULT_PREFIX)
    target_var     = tk.StringVar(value="Ngang 1920×1080")
    trim_start_var = tk.StringVar(value="0")
    trim_end_var   = tk.StringVar(value="0")

    def pick_files():
        init = DOWNLOADS_DIR if DOWNLOADS_DIR.is_dir() else Path.home()
        fs = filedialog.askopenfilenames(
            title="Chọn video cần xóa tiếng",
            initialdir=str(init),
            filetypes=[("Video", "*.mp4 *.mov *.mkv *.avi *.flv *.webm *.m4v *.wmv *.ts"),
                       ("Tất cả", "*.*")])
        if fs:
            picked["files"] = list(fs)
            src_status.set(f"✓  {len(fs)} video đã chọn")

    def pick_out():
        d = filedialog.askdirectory(title="Chọn thư mục đầu ra",
                                    initialdir=out_var.get() or str(BASE_DIR))
        if d:
            out_var.set(d)

    outer = ttk.Frame(root, padding=18)
    outer.pack(fill="both", expand=True)
    outer.columnconfigure(0, weight=1)

    # ── Tiêu đề (thanh hồng + tiêu đề + mô tả) ──────────────────────────────
    head = ttk.Frame(outer)
    head.grid(row=0, column=0, sticky="ew")
    head.columnconfigure(1, weight=1)
    tk.Frame(head, bg=C["accent"], width=5)\
        .grid(row=0, column=0, rowspan=2, sticky="ns", padx=(0, 12))
    ttk.Label(head, text="Xóa tiếng & chuẩn hóa video", style="Header.TLabel")\
        .grid(row=0, column=1, sticky="w")
    ttk.Label(head, text="Cắt đầy khung về khung hình đồng nhất · bỏ tiếng gốc · "
              "đánh số nối tiếp. File gốc trong Downloads được giữ nguyên.",
              style="Sub.TLabel", wraplength=660, justify="left")\
        .grid(row=1, column=1, sticky="w", pady=(4, 0))

    # ── Thẻ 1: Nguồn & đầu ra ───────────────────────────────────────────────
    card1 = ttk.LabelFrame(outer, text="  Nguồn & đầu ra  ", style="Card.TLabelframe")
    card1.grid(row=1, column=0, sticky="ew", pady=(16, 0))
    card1.columnconfigure(1, weight=1)

    ttk.Label(card1, text="Video nguồn", style="Field.TLabel")\
        .grid(row=0, column=0, sticky="w")
    ttk.Label(card1, textvariable=src_status, style="Hint.TLabel")\
        .grid(row=0, column=1, sticky="w", padx=(12, 12))
    ttk.Button(card1, text="Chọn video…", command=pick_files)\
        .grid(row=0, column=2, sticky="e")

    ttk.Label(card1, text="Thư mục ra", style="Field.TLabel")\
        .grid(row=1, column=0, sticky="w", pady=(12, 0))
    ttk.Entry(card1, textvariable=out_var)\
        .grid(row=1, column=1, sticky="ew", padx=(12, 12), pady=(12, 0))
    ttk.Button(card1, text="Chọn…", command=pick_out)\
        .grid(row=1, column=2, sticky="e", pady=(12, 0))

    ttk.Label(card1, text="Tiền tố tên", style="Field.TLabel")\
        .grid(row=2, column=0, sticky="w", pady=(12, 0))
    ttk.Entry(card1, textvariable=prefix_var, width=20)\
        .grid(row=2, column=1, sticky="w", padx=(12, 12), pady=(12, 0))

    # ── Thẻ 2: Tùy chọn xử lý ───────────────────────────────────────────────
    card2 = ttk.LabelFrame(outer, text="  Tùy chọn xử lý  ", style="Card.TLabelframe")
    card2.grid(row=2, column=0, sticky="ew", pady=(12, 0))
    card2.columnconfigure(1, weight=1)

    ttk.Label(card2, text="Khung hình", style="Field.TLabel")\
        .grid(row=0, column=0, sticky="w")
    ttk.Combobox(card2, textvariable=target_var, values=list(TARGETS.keys()),
                 state="readonly", width=20)\
        .grid(row=0, column=1, sticky="w", padx=(12, 0))

    ttk.Label(card2, text="Cắt bỏ (giây)", style="Field.TLabel")\
        .grid(row=1, column=0, sticky="w", pady=(12, 0))
    trim_row = ttk.Frame(card2)
    trim_row.grid(row=1, column=1, sticky="w", padx=(12, 0), pady=(12, 0))
    ttk.Label(trim_row, text="đầu").pack(side="left")
    ttk.Entry(trim_row, textvariable=trim_start_var, width=6)\
        .pack(side="left", padx=(6, 16))
    ttk.Label(trim_row, text="cuối").pack(side="left")
    ttk.Entry(trim_row, textvariable=trim_end_var, width=6)\
        .pack(side="left", padx=(6, 16))
    ttk.Label(trim_row, text="(0 = không cắt)", style="Hint.TLabel").pack(side="left")

    # ── Nút chạy + thanh tiến trình ─────────────────────────────────────────
    action = ttk.Frame(outer)
    action.grid(row=3, column=0, sticky="ew", pady=(16, 0))
    action.columnconfigure(1, weight=1)
    btn = ttk.Button(action, text="▶  Chạy", style="Accent.TButton")
    btn.grid(row=0, column=0, sticky="w")
    pbar = ttk.Progressbar(action, mode="determinate")
    pbar.grid(row=0, column=1, sticky="ew", padx=(14, 0))

    # ── Thẻ Nhật ký ─────────────────────────────────────────────────────────
    logcard = ttk.LabelFrame(outer, text="  Nhật ký  ", style="Card.TLabelframe")
    logcard.grid(row=4, column=0, sticky="nsew", pady=(12, 0))
    logcard.rowconfigure(0, weight=1)
    logcard.columnconfigure(0, weight=1)
    outer.rowconfigure(4, weight=1)

    box = scrolledtext.ScrolledText(logcard, height=12, font=("Consolas", 9),
                                    wrap="word", state="disabled", relief="flat",
                                    bg=C["log_bg"], fg=C["fg"], borderwidth=0,
                                    padx=10, pady=8)
    box.grid(row=0, column=0, sticky="nsew")
    box.tag_configure("ok", foreground=C["log_ok"])
    box.tag_configure("err", foreground=C["log_err"])
    box.tag_configure("warn", foreground=C["log_warn"])
    box.tag_configure("done", foreground=C["accent"], font=("Consolas", 9, "bold"))
    box.tag_configure("muted", foreground=C["log_muted"])

    def _log_tag(line):
        s = line.strip()
        if s.startswith("[OK]"):
            return "ok"
        if s.startswith("[LỖI]"):
            return "err"
        if s.startswith("[!]"):
            return "warn"
        if s.startswith("Hoàn tất"):
            return "done"
        if s and set(s) == {"-"}:
            return "muted"
        return ""

    def gui_log(msg):
        log_q.put(("log", str(msg)))

    def gui_progress(done, total):
        log_q.put(("prog", (done, total)))

    def worker(files, out_dir, prefix, tw, th, ts, te):
        try:
            run_files(files, out_dir, prefix, tw, th, trim_start=ts, trim_end=te,
                      log=gui_log, progress=gui_progress)
        except Exception as e:                       # noqa: BLE001 - show mọi lỗi lên GUI
            gui_log(f"[LỖI] {e}")
        finally:
            log_q.put(("done", None))

    def _parse_secs(text):
        try:
            v = float(str(text).replace(",", ".").strip() or "0")
        except ValueError:
            return 0.0
        return v if v > 0 else 0.0

    def start():
        if busy["v"]:
            return
        files = picked["files"]
        if not files:
            gui_log("[!] Chưa chọn video nào — bấm 'Chọn video…' trước.")
            return
        prefix = prefix_var.get().strip() or DEFAULT_PREFIX
        out_dir = Path(out_var.get().strip() or str(DEFAULT_OUT_DIR))
        tw, th = TARGETS[target_var.get()]
        ts = _parse_secs(trim_start_var.get())
        te = _parse_secs(trim_end_var.get())

        busy["v"] = True
        btn.config(state="disabled")
        pbar.config(value=0, maximum=len(files))
        box.config(state="normal")
        box.delete("1.0", "end")
        box.config(state="disabled")
        threading.Thread(target=worker, args=(files, out_dir, prefix, tw, th, ts, te),
                         daemon=True).start()

    btn.config(command=start)

    def poll():
        try:
            while True:
                kind, payload = log_q.get_nowait()
                if kind == "done":
                    busy["v"] = False
                    btn.config(state="normal")
                elif kind == "prog":
                    done, total = payload
                    pbar.config(maximum=max(total, 1), value=done)
                else:  # log
                    box.config(state="normal")
                    box.insert("end", payload + "\n", _log_tag(payload))
                    box.see("end")
                    box.config(state="disabled")
        except queue.Empty:
            pass
        root.after(150, poll)

    poll()
    return root


def launch_gui():
    import tkinter as tk
    root = tk.Tk()
    _build_gui(root)
    root.minsize(680, 560)
    root.update_idletasks()
    w, h = 760, 660
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"{w}x{h}+{max((sw - w) // 2, 0)}+{max((sh - h) // 3, 0)}")
    root.mainloop()


# ═══════════════════════ Luồng CŨ: mp4/ -> mp4_no_audio/ ════════════════════
try:
    from tqdm import tqdm
    _tqdm = tqdm
except ImportError:
    def _tqdm(it, **kw):
        total = kw.get("total", "?")
        for i, x in enumerate(it, 1):
            print(f"  [{i}/{total}] {x}")
            yield x


def process_video(src: Path, dst: Path) -> bool:
    """(Luồng cũ) Scale lên 1080p + xóa audio. Trả True nếu thành công."""
    cmd = [
        "ffmpeg", "-y", "-i", str(src),
        "-an", "-vf", SCALE_FILTER,
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-pix_fmt", "yuv420p", str(dst),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"\n[LỖI] {src.name}\n{result.stderr[-600:]}", file=sys.stderr)
        return False
    return True


def run_batch_folder():
    """(Luồng cũ) Xóa tiếng + scale mọi .mp4 trong mp4/ sang mp4_no_audio/."""
    if not SRC_DIR.exists():
        print(f"[LỖI] Không tìm thấy thư mục nguồn: {SRC_DIR}")
        sys.exit(1)

    DST_DIR.mkdir(exist_ok=True)
    videos = sorted(SRC_DIR.glob("*.mp4"))
    if not videos:
        print("Không có file .mp4 nào trong thư mục mp4/")
        sys.exit(0)

    print(f"Nguồn  : {SRC_DIR}")
    print(f"Đích   : {DST_DIR}")
    print(f"Scale  : {SCALE_FILTER}  →  1080×1920 (portrait HD)")
    print(f"Tổng   : {len(videos)} file\n")

    ok, fail, skipped = 0, 0, 0
    for vid in _tqdm(videos, total=len(videos), desc="Xử lý"):
        dst_file = DST_DIR / vid.name
        if dst_file.exists() and dst_file.stat().st_size > 4096:
            print(f"  [bỏ qua] {vid.name} (đã tồn tại)")
            skipped += 1
            ok += 1
            continue
        if process_video(vid, dst_file):
            print(f"  [OK] {vid.name}  →  {get_resolution(dst_file)}")
            ok += 1
        else:
            fail += 1

    print(f"\nHoàn tất — thành công: {ok} (bỏ qua: {skipped}), lỗi: {fail}")
    print(f"Kết quả: {DST_DIR}")


def main():
    parser = argparse.ArgumentParser(
        description="Xóa tiếng + chuẩn hóa khung hình video (GUI mặc định).")
    parser.add_argument("--batch", action="store_true",
                        help="Luồng cũ: mp4/ -> mp4_no_audio/ (đầu vào cho video_ghepcuoi).")
    args = parser.parse_args()

    if args.batch:
        run_batch_folder()
    else:
        launch_gui()


if __name__ == "__main__":
    main()
