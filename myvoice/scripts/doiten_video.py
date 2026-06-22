# -*- coding: utf-8 -*-
"""
Chuẩn hóa + đổi tên tuần tự video — cho CẢ video NGANG lẫn video DỌC.

Hai chế độ:
  - ngang : thư mục videongang/, ép về 1920x1080, GIỮ video ngang (w > h), tag _ng_
  - doc   : thư mục videodoc/,   ép về 1080x1920, GIỮ video dọc  (h > w), tag _doc_

Mỗi lần chạy (theo chế độ đã chọn):
  1. Quét video trong thư mục, chỉ giữ video ĐÚNG HƯỚNG của chế độ.
  2. Video chưa chuẩn hóa -> ép cùng khung hình + 30fps + LOẠI BỎ ÂM THANH GỐC.
  3. Đổi tên toàn bộ theo số thứ tự (<tag>001.mp4, <tag>002.mp4, ...). File đã đúng
     số thì giữ nguyên, lệch thì đổi.

Cách dùng:
    python doiten_video.py                 # MỞ GUI để chọn ngang/dọc rồi chạy
    python doiten_video.py --mode ngang    # chạy thẳng chế độ ngang (không GUI)
    python doiten_video.py --mode doc      # chạy thẳng chế độ dọc (không GUI)

Yêu cầu: ffmpeg và ffprobe có trong PATH.
"""

import argparse
import io
import json
import os
import subprocess
import sys
from pathlib import Path

# Ép UTF-8 cho stdout/stderr khi chạy CLI (guard cho trường hợp không có .buffer).
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent.parent   # myvoice/

# ----------------------------- CẤU HÌNH THEO CHẾ ĐỘ -----------------------------
# orient: "landscape" = giữ video ngang (w > h); "portrait" = giữ video dọc (h > w).
MODES = {
    "ngang": {
        "label": "Video ngang (videongang → 1920×1080)",
        "dir": BASE_DIR / "videongang",
        "target_w": 1920, "target_h": 1080,
        "tag": "_ng_",
        "orient": "landscape",
    },
    "doc": {
        "label": "Video dọc (videodoc → 1080×1920)",
        "dir": BASE_DIR / "videodoc",
        "target_w": 1080, "target_h": 1920,
        "tag": "_doc_",
        "orient": "portrait",
    },
}

TARGET_FPS = 30          # khung hình/giây
OUT_EXT = ".mp4"         # đuôi file đầu ra
NUM_DIGITS = 3           # số chữ số khi đánh số (3 -> 001, 002, ...)
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".flv", ".webm", ".m4v", ".wmv", ".ts"}
# Ưu tiên dùng GPU (NVIDIA NVENC); tự fallback về CPU (libx264) nếu GPU lỗi.
USE_GPU = True
# --------------------------------------------------------------------------------

# Được gán trong run_rename(): True nếu ffmpeg có encoder h264_nvenc.
HAVE_NVENC = False


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def has_nvenc():
    """Kiểm tra ffmpeg có encoder h264_nvenc hay không."""
    res = run(["ffmpeg", "-hide_banner", "-encoders"])
    return res.returncode == 0 and "h264_nvenc" in res.stdout


def probe_stream(path):
    """Trả về (codec_name, width, height) hoặc None nếu không đọc được."""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=codec_name,width,height",
        "-of", "json", path,
    ]
    res = run(cmd)
    if res.returncode != 0:
        return None
    try:
        s = json.loads(res.stdout).get("streams", [])[0]
        return s.get("codec_name", ""), int(s["width"]), int(s["height"])
    except (ValueError, KeyError, IndexError):
        return None


def is_processed(name, tag):
    """File đã chuẩn hóa có dạng <tag><số><OUT_EXT>, ví dụ _ng_001.mp4 / _doc_001.mp4"""
    base, ext = os.path.splitext(name)
    if ext.lower() != OUT_EXT:
        return False
    if not base.startswith(tag):
        return False
    return base[len(tag):].isdigit()


def processed_index(name, tag):
    return int(os.path.splitext(name)[0][len(tag):])


def final_name(index, tag):
    return f"{tag}{index:0{NUM_DIGITS}d}{OUT_EXT}"


def _ff(cmd):
    """Chạy ffmpeg, trả về (ok, dòng lỗi cuối)."""
    res = run(cmd)
    err = res.stderr.strip().splitlines()[-1] if res.stderr.strip() else ""
    return res.returncode == 0, err


def _same_aspect(w, h, tw, th):
    """True nếu tỉ lệ khung hình của clip ~ bằng tỉ lệ đích (cho phép sai số nhỏ)."""
    return abs(w / h - tw / th) < 0.01


def normalize(src_path, dst_path, target_w, target_h, codec, w, h, log=print):
    """Chuẩn hóa video về target_w×target_h + bỏ tiếng. Trả về (True/False, mô tả cách làm).

    - Clip ĐÃ đúng (h264 + đúng kích thước)  -> chỉ COPY + bỏ tiếng (giữ nguyên fps, ~tức thì).
    - Clip CẦN convert, CÙNG tỉ lệ           -> full GPU (scale_cuda), ép 30fps.
    - Clip CẦN convert, KHÁC tỉ lệ           -> CPU scale + pad (letterbox), ép 30fps.
    Khi convert: ưu tiên NVENC, lỗi thì fallback libx264.
    """
    # 1) Đã đúng định dạng đích -> copy nguyên luồng video, chỉ bỏ tiếng. Giữ nguyên fps.
    if codec == "h264" and w == target_w and h == target_h:
        ok, err = _ff(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                       "-i", src_path, "-c", "copy", "-an",
                       "-movflags", "+faststart", dst_path])
        if ok:
            return True, "copy (giữ fps)"
        log(f"    [copy lỗi -> encode] {err}")
        if os.path.exists(dst_path):
            os.remove(dst_path)

    # 2) Cần convert, CÙNG tỉ lệ + có NVENC -> giải mã + scale + encode TOÀN BỘ trên GPU.
    if USE_GPU and HAVE_NVENC and _same_aspect(w, h, target_w, target_h):
        ok, err = _ff([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-hwaccel", "cuda", "-hwaccel_output_format", "cuda", "-i", src_path,
            "-vf", f"scale_cuda={target_w}:{target_h}", "-r", str(TARGET_FPS),
            "-an", "-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "20",
            "-movflags", "+faststart", dst_path])
        if ok:
            return True, "scale GPU, ép 30fps"
        log(f"    [GPU scale lỗi -> CPU] {err}")
        if os.path.exists(dst_path):
            os.remove(dst_path)

    # 3) Fallback / khác tỉ lệ: CPU scale + pad (letterbox), ép 30fps.
    vf = (
        f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,"
        f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"setsar=1,fps={TARGET_FPS}"
    )
    enc = (["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "20"]
           if (USE_GPU and HAVE_NVENC)
           else ["-c:v", "libx264", "-preset", "medium", "-crf", "20"])
    ok, err = _ff([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-hwaccel", "cuda", "-i", src_path,
        "-vf", vf, "-an", *enc,
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", dst_path])
    if ok:
        return True, "scale+pad, ép 30fps"
    # Có thể -hwaccel cuda không hỗ trợ -> thử lại không hwaccel.
    ok, err = _ff([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", src_path, "-vf", vf, "-an", *enc,
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", dst_path])
    if not ok:
        log(f"    [LỖI ffmpeg] {err}")
    return ok, "scale+pad, ép 30fps"


def run_rename(mode, log=print):
    """Chuẩn hóa + đổi tên tuần tự cho 1 chế độ ('ngang' hoặc 'doc')."""
    global HAVE_NVENC
    cfg = MODES[mode]
    video_dir = str(cfg["dir"])
    tag = cfg["tag"]
    tw, th = cfg["target_w"], cfg["target_h"]
    orient = cfg["orient"]
    huong = "ngang" if orient == "landscape" else "dọc"

    if not os.path.isdir(video_dir):
        log(f"Không tìm thấy thư mục: {video_dir}")
        return 0

    HAVE_NVENC = has_nvenc()
    log("Encoder: GPU (h264_nvenc), fallback CPU (libx264)"
        if (USE_GPU and HAVE_NVENC) else "Encoder: CPU (libx264)")

    entries = [f for f in os.listdir(video_dir)
               if os.path.isfile(os.path.join(video_dir, f))
               and os.path.splitext(f)[1].lower() in VIDEO_EXTS]

    processed = sorted([f for f in entries if is_processed(f, tag)],
                       key=lambda f: processed_index(f, tag))
    raw = [f for f in entries if not is_processed(f, tag)]

    log(f"Chế độ  : {cfg['label']}")
    log(f"Thư mục : {video_dir}")
    log(f"Đã chuẩn hóa: {len(processed)} | Chưa xử lý: {len(raw)}")

    # 1) Xử lý video thô: lọc đúng hướng, chuẩn hóa khung hình + bỏ tiếng.
    new_processed = []   # đường dẫn tạm (chưa đánh số cuối cùng)
    skipped = 0
    for f in raw:
        src = os.path.join(video_dir, f)
        info = probe_stream(src)
        if info is None:
            log(f"  [BỎ QUA] không đọc được: {f}")
            continue
        codec, w, h = info
        wrong = (orient == "landscape" and w <= h) or (orient == "portrait" and h <= w)
        if wrong:
            skipped += 1
            log(f"  [BỎ QUA] sai hướng cho chế độ {huong} ({w}x{h}): {f}")
            continue

        tmp = os.path.join(video_dir, f"__tmp_{len(new_processed)}{OUT_EXT}")
        ok, how = normalize(src, tmp, tw, th, codec, w, h, log=log)
        if ok:
            log(f"  [OK] {f}  ({codec} {w}x{h}) -> {how}")
            os.remove(src)               # xóa file gốc sau khi tạo bản chuẩn hóa
            new_processed.append(tmp)
        else:
            log(f"  [LỖI] {f}")
            if os.path.exists(tmp):
                os.remove(tmp)

    # 2) Gộp: video đã chuẩn hóa trước đó + video vừa xử lý.
    ordered = [os.path.join(video_dir, f) for f in processed] + new_processed

    # 3) Đặt lại tên tuần tự (đổi tên 2 pha qua tên tạm để tránh đè nhau).
    desired = [os.path.join(video_dir, final_name(i, tag)) for i in range(1, len(ordered) + 1)]

    stage = []
    renamed = 0
    for i, (cur, want) in enumerate(zip(ordered, desired)):
        if os.path.normcase(cur) == os.path.normcase(want):
            stage.append(cur)            # đã đúng số thứ tự, giữ nguyên
            continue
        mid = os.path.join(video_dir, f"__stage_{i}{OUT_EXT}")
        os.replace(cur, mid)
        stage.append(mid)

    for cur, want in zip(stage, desired):
        if os.path.normcase(cur) == os.path.normcase(want):
            continue
        os.replace(cur, want)
        renamed += 1

    log("-" * 50)
    log(f"Hoàn tất. Tổng video {huong}: {len(ordered)}")
    log(f"  - Mới chuẩn hóa: {len(new_processed)}")
    log(f"  - Đổi tên lại  : {renamed}")
    if skipped:
        log(f"  - Bỏ qua sai hướng: {skipped}")
    return len(ordered)


# ───────────────────────── GIAO DIỆN (chọn ngang/dọc) ──────────────────────────
def _build_rename_gui(root):
    """Dựng toàn bộ widget vào `root` (tách riêng để test được mà không mainloop)."""
    import queue
    import threading
    import tkinter as tk
    from tkinter import ttk, scrolledtext

    root.title("Đổi tên & chuẩn hóa video")
    root.configure(bg="#ffffff")
    root.geometry("700x480")

    try:
        st = ttk.Style(root)
        st.theme_use("clam")
        st.configure(".", background="#ffffff", foreground="#1f2430", font=("Segoe UI", 10))
        st.configure("TFrame", background="#ffffff")
        st.configure("TLabel", background="#ffffff")
        st.configure("TRadiobutton", background="#ffffff")
        st.configure("Accent.TButton", foreground="#ffffff", background="#e84393",
                     font=("Segoe UI Semibold", 10), padding=(18, 9), borderwidth=0)
        st.map("Accent.TButton",
               background=[("active", "#c92f7b"), ("disabled", "#f0a8c6")])
    except tk.TclError:
        pass

    log_q: "queue.Queue[str]" = queue.Queue()
    busy = {"v": False}

    frm = ttk.Frame(root, padding=16)
    frm.pack(fill="both", expand=True)

    ttk.Label(frm, text="Chuẩn hóa khung hình + xóa tiếng + đổi tên tuần tự",
              font=("Segoe UI Semibold", 13)).pack(anchor="w")
    ttk.Label(frm, text="Chọn thư mục video cần xử lý rồi bấm Chạy.",
              foreground="#7b828f").pack(anchor="w", pady=(2, 10))

    mode_var = tk.StringVar(value="ngang")
    mrow = ttk.Frame(frm)
    mrow.pack(anchor="w")
    ttk.Label(mrow, text="Chế độ:").pack(side="left", padx=(0, 12))
    for val in ("ngang", "doc"):
        ttk.Radiobutton(mrow, text=MODES[val]["label"], variable=mode_var,
                        value=val).pack(side="left", padx=(0, 16))

    btn = ttk.Button(frm, text="▶  Chạy", style="Accent.TButton")
    btn.pack(anchor="w", pady=(12, 8))

    box = scrolledtext.ScrolledText(frm, height=16, font=("Consolas", 9), wrap="word",
                                    state="disabled", relief="flat",
                                    bg="#fbfbfc", padx=10, pady=8)
    box.pack(fill="both", expand=True)

    def gui_log(msg):
        log_q.put(str(msg))

    def worker(mode):
        try:
            run_rename(mode, log=gui_log)
        except Exception as e:
            gui_log(f"[LỖI] {e}")
        finally:
            log_q.put("__DONE__")

    def start():
        if busy["v"]:
            return
        busy["v"] = True
        btn.config(state="disabled")
        box.config(state="normal")
        box.delete("1.0", "end")
        box.config(state="disabled")
        threading.Thread(target=worker, args=(mode_var.get(),), daemon=True).start()

    btn.config(command=start)

    def poll():
        try:
            while True:
                line = log_q.get_nowait()
                if line == "__DONE__":
                    busy["v"] = False
                    btn.config(state="normal")
                    continue
                box.config(state="normal")
                box.insert("end", line + "\n")
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
    _build_rename_gui(root)
    root.mainloop()


def main():
    parser = argparse.ArgumentParser(
        description="Chuẩn hóa khung hình + xóa tiếng + đổi tên tuần tự (video ngang/dọc)."
    )
    parser.add_argument("--mode", choices=["ngang", "doc"],
                        help="Chạy thẳng chế độ này (không mở GUI).")
    args = parser.parse_args()

    if args.mode:
        run_rename(args.mode)
    else:
        launch_gui()


if __name__ == "__main__":
    main()
