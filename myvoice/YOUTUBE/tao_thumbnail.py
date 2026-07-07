# -*- coding: utf-8 -*-
"""Tạo thumbnail YouTube 1280x720 từ tiêu đề SEO.

Chạy nhanh (tự đọc kịch_bản/seoYoutube.docx):
    python tao_thumbnail.py

Tùy chỉnh:
    python tao_thumbnail.py --title "Tiêu đề mới" --background "D:\\anh.png"
    python tao_thumbnail.py --docx "D:\\seoYoutube.docx" --output "D:\\thumbnail.png"

Mặc định ảnh được lưu tại: myvoice/kịch_bản/thumbnail.png
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from seo_docx_parser import parse_seo_docx


WIDTH, HEIGHT = 1280, 720
HERE = Path(__file__).resolve().parent
MYVOICE_DIR = HERE.parent
KICHBAN_DIR = MYVOICE_DIR / "kịch_bản"
DEFAULT_DOCX = KICHBAN_DIR / "seoYoutube.docx"
DEFAULT_OUTPUT = KICHBAN_DIR / "thumbnail.png"
# Không gán ngẫu nhiên ảnh trong Anh/: ảnh có thể không liên quan tiêu đề.
# Không truyền --background thì dùng nền gradient trung tính.
DEFAULT_BACKGROUND = None


def load_font(size: int) -> ImageFont.FreeTypeFont:
    """Ưu tiên font Windows đậm, có hỗ trợ đầy đủ dấu tiếng Việt."""
    candidates = (
        Path("C:/Windows/Fonts/arialbd.ttf"),
        Path("C:/Windows/Fonts/tahomabd.ttf"),
        Path("C:/Windows/Fonts/calibrib.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    )
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def cover_image(path: Path, size: tuple[int, int]) -> Image.Image:
    """Cắt ảnh theo kiểu cover để phủ kín khung thumbnail."""
    with Image.open(path) as source:
        return ImageOps.fit(
            source.convert("RGB"), size, method=Image.Resampling.LANCZOS,
            centering=(0.62, 0.5),
        )


def fallback_background(size: tuple[int, int]) -> Image.Image:
    """Nền gradient dùng khi chưa có ảnh minh họa."""
    image = Image.new("RGB", size)
    px = image.load()
    for y in range(size[1]):
        for x in range(size[0]):
            t = (x / size[0] + y / size[1]) / 2
            px[x, y] = (int(28 + 55 * t), int(13 + 9 * t), int(38 + 36 * t))
    return image


def title_without_channel(title: str) -> str:
    """Bỏ hậu tố thương hiệu sau dấu | để phần chữ chính dễ đọc hơn."""
    return re.split(r"\s*\|\s*", title.strip(), maxsplit=1)[0].strip()


def fit_title(draw: ImageDraw.ImageDraw, text: str, max_width: int,
              max_lines: int = 3) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    """Chọn cỡ chữ và xuống dòng sao cho tiêu đề luôn vừa thumbnail."""
    words = text.split()
    for size in range(78, 39, -2):
        font = load_font(size)
        lines: list[str] = []
        current = ""
        for word in words:
            proposed = f"{current} {word}".strip()
            if draw.textbbox((0, 0), proposed, font=font)[2] <= max_width:
                current = proposed
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        if len(lines) <= max_lines:
            return font, lines

    # Trường hợp cực dài: vẫn bảo đảm không tràn bằng cách cắt phần cuối.
    font = load_font(40)
    lines = []
    current = ""
    for word in words:
        proposed = f"{current} {word}".strip()
        if draw.textbbox((0, 0), proposed, font=font)[2] <= max_width:
            current = proposed
        elif len(lines) < max_lines - 1:
            lines.append(current)
            current = word
        else:
            while draw.textbbox((0, 0), f"{current}…", font=font)[2] > max_width:
                current = current.rsplit(" ", 1)[0]
            lines.append(f"{current}…")
            return font, lines
    if current:
        lines.append(current)
    return font, lines[:max_lines]


def draw_text_centered(draw: ImageDraw.ImageDraw, x: int, y: int, width: int,
                       text: str, font: ImageFont.FreeTypeFont,
                       *, fill: str, stroke_width: int = 0,
                       stroke_fill: str = "black") -> None:
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
    text_width = bbox[2] - bbox[0]
    draw.text(
        (x + (width - text_width) // 2, y), text, font=font, fill=fill,
        stroke_width=stroke_width, stroke_fill=stroke_fill,
    )


def create_thumbnail(title: str, output: Path, background: Path | None = None) -> Path:
    """Render thumbnail PNG chuẩn YouTube từ tiêu đề và một ảnh nền tùy chọn."""
    title = title_without_channel(title)
    if not title:
        raise ValueError("Tiêu đề đang trống.")

    if background and background.is_file():
        canvas = cover_image(background, (WIDTH, HEIGHT)).convert("RGBA")
    else:
        canvas = fallback_background((WIDTH, HEIGHT)).convert("RGBA")

    # Làm tối vùng đặt chữ để ảnh nền không làm mất độ tương phản.
    shade = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    shade_px = shade.load()
    for x in range(WIDTH):
        alpha = int(210 - min(x / WIDTH, 1) * 165)
        for y in range(HEIGHT):
            shade_px[x, y] = (11, 7, 14, alpha)
    canvas = Image.alpha_composite(canvas, shade)

    draw = ImageDraw.Draw(canvas)
    text_x, text_width = 54, 800

    # Nhãn thương hiệu và thể loại giữ bố cục nhất quán giữa các thumbnail.
    badge_font = load_font(27)
    draw.rounded_rectangle((text_x, 52, text_x + 270, 98), radius=13, fill="#dc1e3f")
    draw_text_centered(draw, text_x, 59, 270, "MIMI AUDIO", badge_font, fill="white")

    genre_font = load_font(27)
    draw.text((text_x, 128), "TRUYỆN AUDIO • KỊCH TÍNH", font=genre_font,
              fill="#ffd64a", stroke_width=1, stroke_fill="#24140a")

    title_font, lines = fit_title(draw, title.upper(), text_width)
    line_height = int(title_font.size * 1.16)
    block_height = line_height * len(lines)
    start_y = max(185, (HEIGHT - block_height) // 2)
    for index, line in enumerate(lines):
        draw.text(
            (text_x, start_y + index * line_height), line, font=title_font,
            fill="white", stroke_width=max(2, title_font.size // 25), stroke_fill="#170b14",
        )

    # Nhấn vào mức giá nếu tiêu đề có, phù hợp với dạng tiêu đề như "388 TỆ".
    price = re.search(r"\b\d{2,5}\s*(?:TỆ|K|TRIỆU|ĐỒNG)\b", title, flags=re.IGNORECASE)
    if price:
        price_font = load_font(40)
        label = price.group(0).upper()
        bbox = draw.textbbox((0, 0), label, font=price_font)
        box_w = bbox[2] - bbox[0] + 42
        box_y = 620
        draw.rounded_rectangle((text_x, box_y, text_x + box_w, box_y + 62),
                               radius=14, fill="#f5c400", outline="white", width=2)
        draw_text_centered(draw, text_x, box_y + 7, box_w, label, price_font,
                           fill="#3a1600", stroke_width=0)

    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(output, format="PNG", optimize=True)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tạo thumbnail YouTube 1280x720 từ tiêu đề SEO."
    )
    parser.add_argument("--title", help="Tiêu đề tự nhập; ưu tiên hơn --docx.")
    parser.add_argument("--docx", type=Path, default=DEFAULT_DOCX,
                        help="File seoYoutube.docx để tự lấy tiêu đề.")
    parser.add_argument("--background", type=Path, default=DEFAULT_BACKGROUND,
                        help="Ảnh nền; bỏ qua hoặc không tồn tại sẽ dùng nền gradient.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                        help="File PNG đầu ra.")
    args = parser.parse_args()

    title = (args.title or "").strip()
    if not title:
        if not args.docx.is_file():
            raise SystemExit(f"Không tìm thấy file SEO: {args.docx}")
        title = parse_seo_docx(args.docx)["title"].strip()
    if not title:
        raise SystemExit("Không lấy được tiêu đề. Dùng --title để nhập thủ công.")

    saved = create_thumbnail(title, args.output, args.background)
    print(f"Đã tạo thumbnail: {saved}")
    print(f"Tiêu đề: {title}")


if __name__ == "__main__":
    main()
