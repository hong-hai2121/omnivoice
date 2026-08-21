# -*- coding: utf-8 -*-
"""Thumbnail cho video đã dịch — khung hình thật của video + tiêu đề đè lên.

Cách chạy (web xếp vào hàng đợi, hoặc tay):
    venv\\Scripts\\python.exe myvideo\\thumbnail_video.py --base "<thư mục>/<tên>_x0.7"
    thêm --giay 45   → bắt khung hình ở giây thứ 45 (mặc định 1/4 thời lượng)
    thêm --force     → làm lại (bản cũ được đổi tên giữ lại, không ghi đè mất)

Khác myvoice (thumbnail vẽ từ bộ khung giấy + ảnh mèo của kênh truyện): video
dịch đã CÓ SẴN hình — lấy đúng khung hình của nó làm nền, phủ dải tối phía
dưới rồi đè TIÊU ĐỀ (lấy từ <base>_seo.json, chưa có SEO thì dùng tên video).

Font tiêu đề: Merriweather ExtraBold trong kho font dùng chung
myvoice/YOUTUBE/fonts — font serif duy nhất đã kiểm là đủ dấu đôi tiếng Việt
(Georgia/Book Antiqua/Nexa Rust ra ô vuông). Kho font là tài nguyên chung của
repo, không phải cài đặt riêng của myvoice.

Ra: <base>_thumb.jpg (1280×720, JPEG — chắc chắn dưới trần 2MB của YouTube).
dang_youtube.py tự kèm ảnh này khi đăng.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]              # …/OmniVoice
VENV_PY = ROOT / "venv" / "Scripts" / "python.exe"
OUTPUT_DIR = ROOT / "myvideo" / "output"
FONT_TITLE = ROOT / "myvoice" / "YOUTUBE" / "fonts" / "Merriweather.ttf"

CANVAS_W, CANVAS_H = 1280, 720          # cỡ khuyến nghị của YouTube, nhẹ dưới 2MB

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass

_XTAG_CUOI = re.compile(r"_x\d+(?:\.\d+)?$")


def ten_hienthi(base: str) -> str:
    name = base.split("/")[-1]
    m = _XTAG_CUOI.search(name)
    return name[: m.start()] if m else name


def _ffprobe_duration(video: Path) -> float:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
            capture_output=True, text=True, timeout=60)
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def _grab_frame(video: Path, giay: float, out_png: Path) -> bool:
    """ffmpeg bắt một khung hình tại `giay` → PNG tạm."""
    r = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-ss", f"{giay:.2f}", "-i", str(video),
         "-frames:v", "1", "-q:v", "2", str(out_png)],
        capture_output=True, text=True, timeout=120)
    return r.returncode == 0 and out_png.is_file()


def _title_font(size: int):
    """Merriweather ExtraBold (variable font) — fallback Arial đậm của Windows."""
    from PIL import ImageFont
    try:
        f = ImageFont.truetype(str(FONT_TITLE), size)
        try:
            f.set_variation_by_name("ExtraBold")
        except Exception:
            pass
        return f
    except OSError:
        return ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", size)


def _wrap(draw, text: str, font, max_w: int) -> list[str] | None:
    """Ngắt theo từ cho vừa bề rộng; quá 3 dòng = cỡ chữ này không vừa."""
    words, lines, dong = text.split(), [], ""
    for w in words:
        thu = f"{dong} {w}".strip()
        if draw.textlength(thu, font=font) <= max_w:
            dong = thu
        else:
            if dong:
                lines.append(dong)
            dong = w
            if draw.textlength(w, font=font) > max_w:
                return None            # một từ đã tràn bề rộng → cỡ này quá to
    if dong:
        lines.append(dong)
    return lines if len(lines) <= 3 else None


def ve_thumbnail(base: str, giay: float | None, force: bool) -> int:
    from PIL import Image, ImageDraw

    out = OUTPUT_DIR / f"{base}_thumb.jpg"
    if out.exists() and not force:
        print(f"⏭ Đã có {out.name} — bỏ qua (dùng --force để làm lại).")
        return 0

    # Nền lấy từ video CHƯA vẽ sub (<base>.mp4 của bước ①) cho sạch chữ; chưa có
    # thì đành lấy video thành phẩm.
    video = OUTPUT_DIR / f"{base}.mp4"
    if not video.is_file():
        video = OUTPUT_DIR / f"{base}_sub.mp4"
    if not video.is_file():
        print(f"⛔ Không thấy video nào của {ten_hienthi(base)} trong output.")
        return 2

    if giay is None:
        dur = _ffprobe_duration(video)
        giay = max(3.0, dur * 0.25)    # 1/4 thời lượng — qua đoạn mở đầu tĩnh

    tmp = OUTPUT_DIR / f"{base}_thumb_khung.png"
    if not _grab_frame(video, giay, tmp):
        print(f"⛔ ffmpeg không bắt được khung hình ở giây {giay:.0f}.")
        return 2

    try:
        seo_file = OUTPUT_DIR / f"{base}_seo.json"
        title = ""
        try:
            title = (json.loads(seo_file.read_text(encoding="utf-8"))
                     .get("title") or "").strip()
        except (OSError, ValueError):
            pass
        title = title or ten_hienthi(base)

        from PIL import ImageOps
        anh = ImageOps.fit(Image.open(tmp).convert("RGB"),
                           (CANVAS_W, CANVAS_H), centering=(0.5, 0.4))

        # Dải tối chân ảnh cho chữ nổi — alpha tăng dần từ nửa dưới xuống đáy.
        lop = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
        d = ImageDraw.Draw(lop)
        for y in range(CANVAS_H // 2, CANVAS_H):
            a = int(190 * (y - CANVAS_H / 2) / (CANVAS_H / 2))
            d.line([(0, y), (CANVAS_W, y)], fill=(0, 0, 0, a))
        anh = Image.alpha_composite(anh.convert("RGBA"), lop)

        # Tiêu đề: dò cỡ chữ từ to xuống cho vừa ≤3 dòng trong 92% bề rộng.
        d = ImageDraw.Draw(anh)
        max_w = int(CANVAS_W * 0.92)
        lines, font = None, None
        for size in range(96, 35, -4):
            font = _title_font(size)
            lines = _wrap(d, title, font, max_w)
            if lines:
                break
        if not lines:                   # tiêu đề dị thường quá dài — cắt cứng
            font = _title_font(40)
            lines = [title[:60] + "…"]

        stroke = max(2, font.size // 16)
        cao_dong = int(font.size * 1.18)
        y = CANVAS_H - 36 - cao_dong * len(lines)
        for dong in lines:
            d.text((CANVAS_W // 2, y), dong, font=font, anchor="ma",
                   fill=(255, 255, 255), stroke_width=stroke,
                   stroke_fill=(12, 12, 16))
            y += cao_dong

        if out.exists():                # --force: giữ bản cũ lại, không ghi đè mất
            giu = out.with_name(f"{out.stem}_cu_{datetime.now():%Y%m%d_%H%M%S}.jpg")
            out.replace(giu)
            print(f"  (bản cũ giữ ở {giu.name})")
        anh.convert("RGB").save(out, "JPEG", quality=90, optimize=True)
        print(f"✅ {out.name} ({out.stat().st_size // 1024}KB) · «{title}»")
        return 0
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


def main() -> int:
    ap = argparse.ArgumentParser(description="Thumbnail từ khung hình video + tiêu đề SEO")
    ap.add_argument("--base", action="append", default=[],
                    help="gốc video trong output (lặp cờ cho nhiều video)")
    ap.add_argument("--giay", type=float, default=None,
                    help="bắt khung hình ở giây này (mặc định 1/4 thời lượng)")
    ap.add_argument("--force", action="store_true", help="làm lại cả video đã có thumbnail")
    args = ap.parse_args()
    if not args.base:
        print("⛔ Thiếu --base.")
        return 2
    xau = 0
    for base in args.base:
        if ve_thumbnail(base, args.giay, args.force) != 0:
            xau += 1
    return 0 if xau == 0 else 2


if __name__ == "__main__":
    if VENV_PY.exists() and Path(sys.executable).resolve() != VENV_PY.resolve():
        import subprocess as sp
        raise SystemExit(sp.call([str(VENV_PY), *sys.argv], cwd=str(ROOT)))
    raise SystemExit(main())
