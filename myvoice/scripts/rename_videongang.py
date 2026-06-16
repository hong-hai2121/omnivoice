# -*- coding: utf-8 -*-
"""
Chuẩn hóa và đặt lại tên video ngang trong thư mục videongang.

Mỗi lần chạy:
  1. Quét toàn bộ video trong thư mục, chỉ giữ video NGANG (width > height).
  2. Video chưa chuẩn hóa  -> ép về cùng 1 khung hình (mặc định 1920x1080, 30fps,
     giữ tỷ lệ gốc + chèn viền đen) và LOẠI BỎ ÂM THANH GỐC.
  3. Đặt lại tên toàn bộ theo số thứ tự (1.mp4, 2.mp4, ...). Video nào đã đúng
     số thứ tự thì giữ nguyên, video nào lệch thì đổi tên.

Yêu cầu: ffmpeg và ffprobe có trong PATH.
"""

import json
import os
import subprocess
import sys

# ----------------------------- CẤU HÌNH -----------------------------
VIDEO_DIR = r"D:\Python\omnivoice\OmniVoice\myvoice\videongang"
TARGET_W = 1920          # chiều rộng khung hình chuẩn
TARGET_H = 1080          # chiều cao khung hình chuẩn
TARGET_FPS = 30          # khung hình/giây
OUT_EXT = ".mp4"         # đuôi file đầu ra
NUM_DIGITS = 3           # số chữ số khi đánh số (3 -> 001, 002, ...)
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".flv", ".webm", ".m4v", ".wmv", ".ts"}
# Marker đánh dấu file đã được chuẩn hóa (đã ép khung hình + bỏ tiếng).
PROCESSED_TAG = "_ng_"
# Ưu tiên dùng GPU (NVIDIA NVENC); tự fallback về CPU (libx264) nếu GPU lỗi.
USE_GPU = True
# --------------------------------------------------------------------

# Được gán trong main(): True nếu ffmpeg có encoder h264_nvenc.
HAVE_NVENC = False


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def has_nvenc():
    """Kiểm tra ffmpeg có encoder h264_nvenc hay không."""
    res = run(["ffmpeg", "-hide_banner", "-encoders"])
    return res.returncode == 0 and "h264_nvenc" in res.stdout


def probe_dimensions(path):
    """Trả về (width, height) hoặc None nếu không đọc được."""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "json", path,
    ]
    res = run(cmd)
    if res.returncode != 0:
        return None
    try:
        streams = json.loads(res.stdout).get("streams", [])
        if not streams:
            return None
        w = int(streams[0]["width"])
        h = int(streams[0]["height"])
        return w, h
    except (ValueError, KeyError, IndexError):
        return None


def is_processed(name):
    """File đã chuẩn hóa có dạng <PROCESSED_TAG><số><OUT_EXT>, ví dụ _ng_001.mp4"""
    base, ext = os.path.splitext(name)
    if ext.lower() != OUT_EXT:
        return False
    if not base.startswith(PROCESSED_TAG):
        return False
    num = base[len(PROCESSED_TAG):]
    return num.isdigit()


def processed_index(name):
    base = os.path.splitext(name)[0]
    return int(base[len(PROCESSED_TAG):])


def final_name(index):
    return f"{PROCESSED_TAG}{index:0{NUM_DIGITS}d}{OUT_EXT}"


def _encode(src_path, dst_path, gpu):
    """Chạy ffmpeg với encoder GPU hoặc CPU. Trả về (ok, thông báo lỗi)."""
    vf = (
        f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=decrease,"
        f"pad={TARGET_W}:{TARGET_H}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"setsar=1,fps={TARGET_FPS}"
    )
    if gpu:
        codec = [
            "-c:v", "h264_nvenc",
            "-preset", "p5",        # cân bằng tốc độ/chất lượng
            "-rc", "vbr",
            "-cq", "20",
        ]
    else:
        codec = [
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "20",
        ]
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", src_path,
        "-vf", vf,
        "-an",                      # loại bỏ toàn bộ âm thanh gốc
        *codec,
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        dst_path,
    ]
    res = run(cmd)
    err = res.stderr.strip().splitlines()[-1] if res.stderr.strip() else ""
    return res.returncode == 0, err


def normalize(src_path, dst_path):
    """Ép khung hình về TARGET_WxTARGET_H, bỏ tiếng. Trả về True nếu thành công."""
    if USE_GPU and HAVE_NVENC:
        ok, err = _encode(src_path, dst_path, gpu=True)
        if ok:
            return True
        print(f"    [GPU lỗi -> CPU] {err}")
        if os.path.exists(dst_path):
            os.remove(dst_path)

    ok, err = _encode(src_path, dst_path, gpu=False)
    if not ok:
        print(f"    [LỖI ffmpeg] {err}")
    return ok


def main():
    global HAVE_NVENC
    if not os.path.isdir(VIDEO_DIR):
        print(f"Không tìm thấy thư mục: {VIDEO_DIR}")
        sys.exit(1)

    HAVE_NVENC = has_nvenc()
    if USE_GPU and HAVE_NVENC:
        print("Encoder: GPU (h264_nvenc), fallback CPU (libx264)")
    else:
        print("Encoder: CPU (libx264)")

    entries = [f for f in os.listdir(VIDEO_DIR)
               if os.path.isfile(os.path.join(VIDEO_DIR, f))
               and os.path.splitext(f)[1].lower() in VIDEO_EXTS]

    processed = sorted([f for f in entries if is_processed(f)], key=processed_index)
    raw = [f for f in entries if not is_processed(f)]

    print(f"Thư mục : {VIDEO_DIR}")
    print(f"Đã chuẩn hóa: {len(processed)} | Chưa xử lý: {len(raw)}")

    # 1) Xử lý các video thô: lọc video ngang, chuẩn hóa khung hình + bỏ tiếng.
    new_processed = []   # đường dẫn tạm (chưa đánh số cuối cùng)
    skipped_portrait = 0
    for f in raw:
        src = os.path.join(VIDEO_DIR, f)
        dims = probe_dimensions(src)
        if dims is None:
            print(f"  [BỎ QUA] không đọc được: {f}")
            continue
        w, h = dims
        if w <= h:
            skipped_portrait += 1
            print(f"  [BỎ QUA] video dọc/vuông ({w}x{h}): {f}")
            continue

        # tên tạm an toàn, tránh trùng trong lúc xử lý
        tmp = os.path.join(VIDEO_DIR, f"__tmp_{len(new_processed)}{OUT_EXT}")
        print(f"  [XỬ LÝ] {f}  ({w}x{h}) -> {TARGET_W}x{TARGET_H}, bỏ tiếng")
        if normalize(src, tmp):
            os.remove(src)               # xóa file gốc sau khi tạo bản chuẩn hóa
            new_processed.append(tmp)
        else:
            if os.path.exists(tmp):
                os.remove(tmp)

    # 2) Gộp danh sách: video đã chuẩn hóa trước đó + video vừa xử lý.
    ordered = [os.path.join(VIDEO_DIR, f) for f in processed] + new_processed

    # 3) Đặt lại tên tuần tự. Đổi tên 2 pha (qua tên tạm) để tránh đè nhau.
    desired = [os.path.join(VIDEO_DIR, final_name(i)) for i in range(1, len(ordered) + 1)]

    # Pha A: đưa mọi file cần đổi tên về tên trung gian duy nhất.
    stage = []
    renamed = 0
    for i, (cur, want) in enumerate(zip(ordered, desired)):
        if os.path.normcase(cur) == os.path.normcase(want):
            stage.append(cur)            # đã đúng số thứ tự, giữ nguyên
            continue
        mid = os.path.join(VIDEO_DIR, f"__stage_{i}{OUT_EXT}")
        os.replace(cur, mid)
        stage.append(mid)

    # Pha B: từ tên trung gian -> tên cuối cùng.
    for cur, want in zip(stage, desired):
        if os.path.normcase(cur) == os.path.normcase(want):
            continue
        os.replace(cur, want)
        renamed += 1

    print("-" * 50)
    print(f"Hoàn tất. Tổng video ngang: {len(ordered)}")
    print(f"  - Mới chuẩn hóa: {len(new_processed)}")
    print(f"  - Đổi tên lại  : {renamed}")
    if skipped_portrait:
        print(f"  - Bỏ qua video dọc/vuông: {skipped_portrait}")


if __name__ == "__main__":
    main()
