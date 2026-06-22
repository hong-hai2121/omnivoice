"""
Xóa âm thanh + scale lên 1080p (1080×1920 dọc) cho tất cả video .mp4 trong mp4/
Kết quả lưu vào thư mục mp4_no_audio/ với tên file giữ nguyên.

Yêu cầu: ffmpeg cài sẵn trong PATH
  pip install tqdm  (tùy chọn, hiển thị thanh tiến trình)
"""

import io
import subprocess
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent.parent   # myvoice/
SRC_DIR = BASE_DIR / "mp4"
DST_DIR = BASE_DIR / "mp4_no_audio"

# Scale target: 1080×1920 (portrait Full HD, 9:16)
# scale=1080:-2  → width=1080, height tự điều chỉnh giữ tỷ lệ gốc (chia hết cho 2)
SCALE_FILTER = "scale=1080:-2"

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
    """Scale lên 1080p + xóa audio. Trả True nếu thành công."""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(src),
        "-an",                          # xóa audio
        "-vf", SCALE_FILTER,            # scale về 1080p
        "-c:v", "libx264",              # encode H.264
        "-crf", "18",                   # chất lượng cao (0=lossless, 51=tệ nhất)
        "-preset", "fast",              # tốc độ encode cân bằng
        "-pix_fmt", "yuv420p",          # tương thích tối đa
        str(dst),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"\n[LỖI] {src.name}\n{result.stderr[-600:]}", file=sys.stderr)
        return False
    return True


def get_resolution(path: Path) -> str:
    """Trả về '1080x1920' hoặc 'unknown'."""
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    return r.stdout.strip().replace(",", "×") if r.returncode == 0 else "unknown"


def main():
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
            res = get_resolution(dst_file)
            print(f"  [OK] {vid.name}  →  {res}")
            ok += 1
        else:
            fail += 1

    print(f"\nHoàn tất — thành công: {ok} (bỏ qua: {skipped}), lỗi: {fail}")
    print(f"Kết quả: {DST_DIR}")


if __name__ == "__main__":
    main()
