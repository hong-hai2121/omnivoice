"""
Lồng video vào bộ khung trang trí nhiều lớp trong Backbround/.

Thứ tự lớp (từ dưới lên trên):
  1. Khung0.png  -> nền dưới cùng
  2. video       -> nằm trong vùng khung của khung1 (cắt bo góc)
  3. khung1.png  -> viền khung video
  4. khung3.png  -> lớp trang trí trên cùng (chữ/hoa văn)

Quy trình:
  - Dò vùng trống + dựng mặt nạ bo góc từ khung1 (viền hồng).
  - Thu/phóng video vừa vùng trong, cắt bo góc, rồi xếp các lớp lên.
  - Giữ nguyên audio gốc của video.

MODE:
  - "fit"  : hiện trọn video (có thể có dải nền trên/dưới) — không mất hình.
  - "fill" : phóng to + cắt cho video phủ kín vùng trong khung.

Cách dùng:
    python frame_video.py
"""

import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent.parent   # myvoice/
BG_DIR   = BASE_DIR / "Backbround"
KHUNG0   = BG_DIR / "Khung0.png"     # nền dưới cùng
KHUNG1   = BG_DIR / "khung1.png"     # viền khung video
KHUNG3   = BG_DIR / "khung3.png"     # trang trí trên cùng
VIDEO_IN = BASE_DIR / "videongang" / "一起来邂逅宫崎骏的夏天_哔哩哔哩_bilibili.mp4"
OUTPUT   = VIDEO_IN.with_name(VIDEO_IN.stem + "_khung.mp4")

MODE  = "fill"      # "fit" hoặc "fill"
INSET = 6           # thu vào trong vài px để không đè lên viền


def get_duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return float(json.loads(r.stdout)["format"]["duration"])


def pink_mask(png_path: Path):
    """Trả về (ảnh RGBA, mảng bool pixel hồng)."""
    im = Image.open(png_path).convert("RGBA")
    a  = np.array(im)
    alpha = a[:, :, 3]
    r, g, b = (a[:, :, 0].astype(int),
               a[:, :, 1].astype(int),
               a[:, :, 2].astype(int))
    # Pixel "hồng": đỏ cao, xanh lá/lam vừa phải, không trong suốt
    pink = (r > 200) & (g > 100) & (g < 200) & (b < 200) & (alpha > 50)
    return im, pink


def detect_inner_box(im, pink):
    """Trả về (x, y, w, h) vùng trống bên trong viền khung hồng."""
    ys, xs = np.where(pink)
    if len(xs) == 0:
        raise RuntimeError("Không tìm thấy viền khung trong ảnh PNG.")

    cy, cx = im.height // 2, im.width // 2

    def inner_edges(mask_line):
        idx = np.where(mask_line)[0]
        first_end = idx[0]                       # mép trong của viền đặc bên đầu
        for v in idx[1:]:
            if v == first_end + 1:
                first_end = v
            else:
                break
        last_start = idx[-1]                     # mép trong của viền đặc bên cuối
        for v in idx[-2::-1]:
            if v == last_start - 1:
                last_start = v
            else:
                break
        return first_end, last_start

    left_in, right_in = inner_edges(pink[cy, :])
    top_in, bottom_in = inner_edges(pink[:, cx])

    x = left_in + 1 + INSET
    y = top_in  + 1 + INSET
    w = (right_in - left_in - 1) - 2 * INSET
    h = (bottom_in - top_in - 1) - 2 * INSET
    return x, y, w, h


def build_mask(pink, out_path: Path):
    """
    Tạo mặt nạ trắng = vùng bên trong khung (kể cả góc bo tròn), đen = bên ngoài.
    binary_fill_holes lấp kín phần trong vòng viền hồng -> ra đúng hình bo góc
    của khung (gồm cả viền, viền sẽ bị khung phủ lên sau).
    """
    show = ndimage.binary_fill_holes(pink)
    Image.fromarray(np.where(show, 255, 0).astype("uint8"), "L").save(out_path)


def main():
    for f in (KHUNG0, KHUNG1, KHUNG3, VIDEO_IN):
        if not f.exists():
            print(f"[LỖI] Không tìm thấy: {f}")
            sys.exit(1)

    im, pink = pink_mask(KHUNG1)
    cw, ch = im.size                                 # khung = kích thước canvas
    ix, iy, iw, ih = detect_inner_box(im, pink)
    dur = get_duration(VIDEO_IN)

    mask_path = Path(tempfile.gettempdir()) / "khung_mask.png"
    build_mask(pink, mask_path)

    print(f"Khung      : {cw}x{ch}")
    print(f"Vùng trong : x={ix} y={iy} {iw}x{ih}")
    print(f"Chế độ     : {MODE}")
    print(f"Đầu vào    : {VIDEO_IN.name}")
    print(f"Đầu ra     : {OUTPUT}\n")

    if MODE == "fill":
        # Phủ kín vùng trong rồi cắt thừa; đặt vào canvas tại (ix, iy)
        place = (
            f"[0:v]scale={iw}:{ih}:force_original_aspect_ratio=increase,"
            f"crop={iw}:{ih},pad={cw}:{ch}:{ix}:{iy}:black[vid];"
        )
    else:  # fit
        # Thu vừa khít (giữ trọn hình), căn giữa trong vùng khung
        place = (
            f"[0:v]scale={iw}:{ih}:force_original_aspect_ratio=decrease,"
            f"pad={cw}:{ch}:{ix}+({iw}-iw)/2:{iy}+({ih}-ih)/2:black[vid];"
        )

    # Xếp lớp: nền khung0 -> video (cắt bo góc) -> viền khung1 -> trang trí khung3
    # Inputs: 0=video 1=khung0 2=khung1 3=khung3 4=mask
    filt = (
        place +
        f"[4:v]format=gray[mask];"
        f"[vid][mask]alphamerge[va];"
        f"[1:v]scale={cw}:{ch}[bg];"
        f"[bg][va]overlay=0:0[b1];"
        f"[b1][2:v]overlay=0:0[b2];"
        f"[b2][3:v]overlay=0:0[out]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", str(VIDEO_IN),
        "-loop", "1", "-i", str(KHUNG0),
        "-loop", "1", "-i", str(KHUNG1),
        "-loop", "1", "-i", str(KHUNG3),
        "-loop", "1", "-i", str(mask_path),
        "-filter_complex", filt,
        "-map", "[out]",
        "-map", "0:a?",
        "-shortest",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        str(OUTPUT),
    ]

    print("Đang dựng video...")
    result = subprocess.run(cmd, capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    mask_path.unlink(missing_ok=True)
    if result.returncode != 0:
        print(f"[LỖI ffmpeg]\n{result.stderr[-1000:]}", file=sys.stderr)
        sys.exit(1)

    size_mb = OUTPUT.stat().st_size / 1024 / 1024
    print(f"\nHoàn tất!")
    print(f"  Thời lượng : {dur:.2f}s")
    print(f"  Dung lượng : {size_mb:.1f} MB")
    print(f"  Kết quả    : {OUTPUT}")


if __name__ == "__main__":
    main()
