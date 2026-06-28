# -*- coding: utf-8 -*-
"""Điền tiêu đề có đổ bóng vào mẫu thumbnail dạng tờ giấy.

Chạy từ thư mục gốc OmniVoice:
    venv\Scripts\python myvoice\YOUTUBE\dien_tieu_de_thumbnail.py

Ảnh gốc thumbnail/tiêu đề.png luôn được giữ nguyên. Mặc định file kết quả được
lưu vào myvoice/kịch_bản/output theo tên thumbnail01.png, thumbnail02.png, ...
và không ghi đè bản cũ.
"""

from __future__ import annotations

import argparse
from functools import lru_cache
from itertools import combinations
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps


HERE = Path(__file__).resolve().parent
THUMBNAIL_DIR = HERE / "thumbnail"
SOURCE_IMAGE = THUMBNAIL_DIR / "tiêu đề.png"
BACKGROUND_IMAGE = THUMBNAIL_DIR / "khung nên.png"
FOREGROUND_FRAME_IMAGE = THUMBNAIL_DIR / "khung trên.png"
FRAME_IMAGE = THUMBNAIL_DIR / "ảnh.png"              # khung ảnh NGANG (mèo nằm ngang)
FRAME_IMAGE_VERTICAL = THUMBNAIL_DIR / "anhdoc.png"  # khung ảnh DỌC (mèo dọc/đứng)
NUMBER_FRAME_IMAGE = THUMBNAIL_DIR / "Số.png"
CAT_IMAGE_DIR = HERE.parent / "Anh"
OUTPUT_DIR = HERE.parent / "kịch_bản" / "output"
DEFAULT_TITLE = "Bữa Tiệc Toàn Ngỗng 388 Tệ Và Sự Thật Đau Đớn Sau Nhiều Năm."
DEFAULT_NUMBER = "01"

# Hậu tố thương hiệu "| Mimi Truyện" CHỈ bỏ khi VẼ chữ lên thumbnail. Tiêu đề để
# COPY (đăng YouTube) đi đường khác (thumbnail_gui._copy_title) nên vẫn giữ nguyên.
_BRAND_SUFFIX_RE = re.compile(r"\s*\|\s*mimi\s*truyện\s*$", re.IGNORECASE)


def strip_brand_suffix(title: str) -> str:
    """Bỏ phần '| Mimi Truyện' ở CUỐI tiêu đề (chỉ dùng cho chữ trên thumbnail)."""
    return _BRAND_SUFFIX_RE.sub("", title or "").rstrip()

# Phần giấy có dòng kẻ trong ảnh mẫu. Góc dương giúp chữ nghiêng theo mặt giấy.
# Dùng gần hết phần giấy có dòng kẻ để tiêu đề nổi bật như thumbnail YouTube.
TEXT_BOX = (65, 265, 1235, 885)
TEXT_ANGLE = 6.7
TEXT_PADDING = 34

# Bảng màu tiêu đề: chữ tô gradient đỏ (sáng trên → sậm dưới) cho có chiều sâu,
# bọc viền trắng dày và một rim tối rất mỏng ngoài cùng để tách hẳn khỏi nền giấy.
TITLE_COLOR_TOP = (236, 64, 64)       # đỏ tươi phía trên
TITLE_COLOR_BOTTOM = (150, 10, 24)    # đỏ sậm phía dưới
TITLE_OUTLINE = (255, 255, 255)       # viền trắng
TITLE_EDGE = (60, 0, 6)               # rim tối ngoài cùng

# Vùng BÊN TRONG khung ảnh.png trên canvas 1920×1080. Ảnh mèo bị crop theo
# đúng hình chữ nhật này, sau đó ảnh khung được phủ lên trên để che hoàn toàn phần dư.
FRAME_INNER_BOX = (1225, 452, 1880, 855)
# Lỗ của khung DỌC (anhdoc.png) — dò từ vùng trong suốt bên trong + nới nhẹ để ảnh
# phủ kín dưới viền khung (không hở mép trong suốt).
FRAME_INNER_BOX_VERTICAL = (1285, 159, 1898, 1078)
# Bán kính bo góc ảnh khi dùng khung DỌC (theo hệ 1920x1080).
PHOTO_CORNER_RADIUS = 45
PHOTO_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

# Vùng trắng bên trong thẻ Số.png (canvas 1920×1080). Góc âm làm số nghiêng
# theo thẻ đang xuôi xuống về phía phải. Thẻ số đã được dời sang trái 132px,
# xuống 15px so với bản cũ nên hộp chữ dời theo cùng độ lệch.
NUMBER_TEXT_BOX = (1318, 100, 1658, 310)
NUMBER_ANGLE = -13.0


for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)


@lru_cache(maxsize=128)
def find_font(size: int) -> ImageFont.FreeTypeFont:
    """Dùng font Windows siêu đậm (ultra-bold), có đầy đủ dấu tiếng Việt.

    Ưu tiên Segoe UI Black / Arial Black để chữ nổi khối, dày nét như thumbnail
    chuyên nghiệp; vẫn lùi về Arial Bold nếu máy thiếu các font trên.
    """
    candidates = (
        Path("C:/Windows/Fonts/seguibl.ttf"),   # Segoe UI Black
        Path("C:/Windows/Fonts/ariblk.ttf"),    # Arial Black
        Path("C:/Windows/Fonts/arialbd.ttf"),
        Path("C:/Windows/Fonts/tahomabd.ttf"),
        Path("C:/Windows/Fonts/calibrib.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    )
    for font_path in candidates:
        if font_path.exists():
            return ImageFont.truetype(str(font_path), size=size)
    raise FileNotFoundError("Không tìm thấy font Windows hỗ trợ tiếng Việt.")


def balanced_wrap(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    max_lines: int,
) -> list[str] | None:
    """Ngắt dòng cân đối nhất, không chỉ ngắt tại từ cuối còn vừa chỗ."""
    words = text.split()
    if not words:
        return None

    candidates: list[tuple[tuple[float, float, int], list[str]]] = []
    for line_count in range(1, min(max_lines, len(words)) + 1):
        for breaks in combinations(range(1, len(words)), line_count - 1):
            points = (0, *breaks, len(words))
            lines = [" ".join(words[points[index]:points[index + 1]]) for index in range(line_count)]
            widths = [
                draw.textbbox((0, 0), line, font=font, stroke_width=3)[2]
                for line in lines
            ]
            if max(widths) > max_width:
                continue

            # Ưu tiên các dòng có độ dài gần nhau và lấp đầy vùng chữ.
            average = sum(widths) / len(widths)
            imbalance = sum((line_width - average) ** 2 for line_width in widths) / max(average, 1)
            score = (imbalance, -min(widths), line_count)
            candidates.append((score, lines))

    if not candidates:
        return None
    return min(candidates, key=lambda candidate: candidate[0])[1]


def fit_text(
    text: str,
    width: int,
    height: int,
    max_lines: int,
) -> tuple[ImageFont.FreeTypeFont, str, int]:
    """Tìm cỡ font lớn nhất và cách xuống dòng cân đối vừa vùng giấy."""
    measure = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    maximum_size = max(42, round(min(width * 0.20, height * 0.62)))
    minimum_size = max(24, round(min(width, height) * 0.03))
    for size in range(maximum_size, minimum_size - 1, -2):
        font = find_font(size)
        lines = balanced_wrap(measure, text, font, width - TEXT_PADDING, max_lines)
        if lines is None:
            continue
        content = "\n".join(lines)
        spacing = max(6, round(size * 0.15))
        left, top, right, bottom = measure.multiline_textbbox(
            (0, 0), content, font=font, spacing=spacing, stroke_width=3
        )
        if right - left <= width - TEXT_PADDING and bottom - top <= height - TEXT_PADDING:
            return font, content, spacing
    raise ValueError("Tiêu đề quá dài để đặt lên ảnh mẫu.")


def unique_path(path: Path) -> Path:
    """Trả tên file chưa tồn tại để bảo toàn mọi bản thumbnail cũ."""
    if not path.exists():
        return path
    number = 2
    while True:
        candidate = path.with_name(f"{path.stem}_{number}{path.suffix}")
        if not candidate.exists():
            return candidate
        number += 1


def next_thumbnail_path(output_dir: Path = OUTPUT_DIR) -> Path:
    """Trả về thumbnail01.png, thumbnail02.png, ... đầu tiên chưa tồn tại."""
    output_dir.mkdir(parents=True, exist_ok=True)
    number = 1
    while True:
        candidate = output_dir / f"thumbnail{number:02d}.png"
        if not candidate.exists():
            return candidate
        number += 1


def load_canvas_layer(path: Path, size: tuple[int, int]) -> Image.Image:
    """Nạp một lớp PNG và co giãn về đúng kích thước canvas khi cần."""
    if not path.is_file():
        raise FileNotFoundError(f"Không tìm thấy ảnh khung: {path}")
    layer = Image.open(path).convert("RGBA")
    if layer.size != size:
        layer = layer.resize(size, Image.Resampling.LANCZOS)
    return layer


def natural_sort_key(path: Path) -> list[object]:
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", path.name)]


def list_photo_files(photo_dir: Path) -> list[Path]:
    """Liệt kê ảnh mèo hợp lệ, không dùng Pink.png đặc biệt."""
    if not photo_dir.is_dir():
        raise FileNotFoundError(f"Không tìm thấy thư mục ảnh: {photo_dir}")
    return sorted(
        (
            path for path in photo_dir.iterdir()
            if path.is_file() and path.suffix.casefold() in PHOTO_EXTENSIONS and path.name.casefold() != "pink.png"
        ),
        key=natural_sort_key,
    )


def select_default_photo(photo_dir: Path) -> Path:
    """Chọn ảnh mèo đầu tiên theo thứ tự tên."""
    photos = list_photo_files(photo_dir)
    if not photos:
        raise FileNotFoundError(f"Không có ảnh .png/.jpg/.jpeg/.webp trong: {photo_dir}")
    return photos[0]


def add_photo_to_frame(base: Image.Image, photo_path: Path, frame_path: Path,
                       inner_box_ref: tuple = FRAME_INNER_BOX,
                       round_corners: bool = False) -> Image.Image:
    """Ghép ảnh theo kiểu cover vào lòng khung và xóa mọi phần nằm ngoài khung.

    inner_box_ref: toạ độ "lỗ" của khung (ngang hay dọc) theo hệ 1920x1080.
    round_corners: True thì bo góc ảnh (dùng cho khung dọc cho đẹp).
    """
    if not photo_path.is_file():
        raise FileNotFoundError(f"Không tìm thấy ảnh mèo: {photo_path}")
    if not frame_path.is_file():
        raise FileNotFoundError(f"Không tìm thấy ảnh khung: {frame_path}")

    width, height = base.size
    scale_x, scale_y = width / 1920, height / 1080
    x0, y0, x1, y1 = inner_box_ref
    inner_box = (
        round(x0 * scale_x), round(y0 * scale_y),
        round(x1 * scale_x), round(y1 * scale_y),
    )
    inner_size = (inner_box[2] - inner_box[0], inner_box[3] - inner_box[1])

    # ImageOps.fit thực hiện crop cover: không méo ảnh, phần thừa ngoài khung bị bỏ.
    photo = Image.open(photo_path).convert("RGBA")
    photo = ImageOps.fit(photo, inner_size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
    if round_corners:
        # Bo góc ảnh: vẽ mặt nạ chữ nhật bo góc rồi gán làm alpha của ảnh.
        radius = max(1, round(PHOTO_CORNER_RADIUS * scale_x))
        mask = Image.new("L", inner_size, 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            (0, 0, inner_size[0] - 1, inner_size[1] - 1), radius=radius, fill=255)
        photo.putalpha(mask)
    clipped_photo = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    clipped_photo.alpha_composite(photo, dest=(inner_box[0], inner_box[1]))

    frame = Image.open(frame_path).convert("RGBA")
    if frame.size != base.size:
        frame = frame.resize(base.size, Image.Resampling.LANCZOS)

    # Phủ khung lên sau cùng: viền/mây/ngôi sao không bị ảnh mèo che.
    result = Image.alpha_composite(base, clipped_photo)
    return Image.alpha_composite(result, frame)


def add_number_to_tag(base: Image.Image, number: str, tag_path: Path) -> Image.Image:
    """Ghi số tập vào thẻ Số.png, tự co font để số luôn nằm gọn trong thẻ."""
    if not tag_path.is_file():
        raise FileNotFoundError(f"Không tìm thấy khung số: {tag_path}")

    width, height = base.size
    scale_x, scale_y = width / 1920, height / 1080
    x0, y0, x1, y1 = NUMBER_TEXT_BOX
    box = (
        round(x0 * scale_x), round(y0 * scale_y),
        round(x1 * scale_x), round(y1 * scale_y),
    )
    box_width, box_height = box[2] - box[0], box[3] - box[1]
    center = ((box[0] + box[2]) // 2, (box[1] + box[3]) // 2)

    tag = Image.open(tag_path).convert("RGBA")
    if tag.size != base.size:
        tag = tag.resize(base.size, Image.Resampling.LANCZOS)

    measure = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    number_font: ImageFont.FreeTypeFont | None = None
    for size in range(round(box_height * 0.95), 20, -2):
        font = find_font(size)
        left, top, right, bottom = measure.textbbox((0, 0), number, font=font, stroke_width=3)
        if right - left <= box_width - 24 and bottom - top <= box_height - 24:
            number_font = font
            break
    if number_font is None:
        raise ValueError("Số quá dài để đặt vào thẻ số.")

    shadow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    text_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    text_draw = ImageDraw.Draw(text_layer)
    shadow_draw.text(
        (center[0] + round(5 * scale_x), center[1] + round(6 * scale_y)),
        number,
        font=number_font,
        anchor="mm",
        fill=(0, 0, 0, 165),
        stroke_width=5,
        stroke_fill=(0, 0, 0, 145),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=max(2, round(4 * scale_x))))
    text_draw.text(
        center,
        number,
        font=number_font,
        anchor="mm",
        fill=(195, 28, 41, 255),
        stroke_width=max(2, round(3 * scale_x)),
        stroke_fill=(255, 247, 222, 255),
    )

    shadow = shadow.rotate(NUMBER_ANGLE, resample=Image.Resampling.BICUBIC, center=center)
    text_layer = text_layer.rotate(NUMBER_ANGLE, resample=Image.Resampling.BICUBIC, center=center)
    result = Image.alpha_composite(base, tag)
    result = Image.alpha_composite(result, shadow)
    return Image.alpha_composite(result, text_layer)


def vertical_gradient(
    size: tuple[int, int],
    top_color: tuple[int, int, int],
    bottom_color: tuple[int, int, int],
    y0: int,
    y1: int,
) -> Image.Image:
    """Tạo lớp gradient dọc; màu chỉ chuyển trong khoảng [y0, y1] của chữ."""
    width, height = size
    grad = Image.new("RGBA", size)
    draw = ImageDraw.Draw(grad)
    span = max(y1 - y0, 1)
    for y in range(height):
        t = min(1.0, max(0.0, (y - y0) / span))
        color = tuple(
            round(top_color[index] + (bottom_color[index] - top_color[index]) * t)
            for index in range(3)
        )
        draw.line([(0, y), (width, y)], fill=(*color, 255))
    return grad


def draw_title_text(
    layer: Image.Image,
    content: str,
    font: ImageFont.FreeTypeFont,
    center: tuple[int, int],
    spacing: int,
    scale_x: float,
) -> None:
    """Vẽ tiêu đề: rim tối ngoài cùng → viền trắng dày → lõi chữ tô gradient đỏ."""
    draw = ImageDraw.Draw(layer)
    common = dict(font=font, spacing=spacing, anchor="mm", align="center")
    white_width = max(3, round(4 * scale_x))
    edge_width = white_width + max(2, round(3 * scale_x))

    # 1) Rim tối hơi loe ra ngoài viền trắng để chữ không bị "chìm" vào nền sáng.
    draw.multiline_text(
        center, content, fill=(*TITLE_EDGE, 255),
        stroke_width=edge_width, stroke_fill=(*TITLE_EDGE, 255), **common,
    )
    # 2) Viền trắng dày bao quanh lõi chữ.
    draw.multiline_text(
        center, content, fill=(*TITLE_OUTLINE, 255),
        stroke_width=white_width, stroke_fill=(*TITLE_OUTLINE, 255), **common,
    )
    # 3) Lõi chữ: tô gradient đỏ qua mask đúng hình glyph (không kèm viền).
    bbox = draw.multiline_textbbox(center, content, stroke_width=0, **common)
    mask = Image.new("L", layer.size, 0)
    ImageDraw.Draw(mask).multiline_text(center, content, fill=255, stroke_width=0, **common)
    grad = vertical_gradient(
        layer.size, TITLE_COLOR_TOP, TITLE_COLOR_BOTTOM, bbox[1], bbox[3]
    )
    layer.paste(grad, (0, 0), mask)


def add_title(
    source: Path,
    output: Path,
    title: str,
    photo_path: Path,
    frame_path: Path,
    number: str,
    number_frame_path: Path,
    max_lines: int = 4,
) -> Path:
    title = strip_brand_suffix(title)   # bỏ '| Mimi Truyện' khỏi chữ trên thumbnail
    paper = Image.open(source).convert("RGBA")
    # Thứ tự lớp: nền hoa → tờ giấy/ảnh/nội dung → khung trang trí trên cùng.
    background = load_canvas_layer(BACKGROUND_IMAGE, paper.size)
    base = Image.alpha_composite(background, paper)
    width, height = base.size

    # Tỷ lệ này được thiết kế cho ảnh 1920x1080; vẫn co giãn nếu ảnh mẫu thay đổi kích thước.
    scale_x = width / 1920
    scale_y = height / 1080
    x0, y0, x1, y1 = TEXT_BOX
    box = (
        round(x0 * scale_x), round(y0 * scale_y),
        round(x1 * scale_x), round(y1 * scale_y),
    )
    box_width, box_height = box[2] - box[0], box[3] - box[1]
    center = ((box[0] + box[2]) // 2, (box[1] + box[3]) // 2)

    font, content, spacing = fit_text(title, box_width, box_height, max_lines)
    text_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    shadow_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow_layer)

    # Bóng đen mềm tách chữ khỏi nền giấy, sau đó vẽ chữ đỏ có viền kem.
    shadow_position = (center[0] + round(8 * scale_x), center[1] + round(9 * scale_y))
    shadow_draw.multiline_text(
        shadow_position,
        content,
        font=font,
        fill=(0, 0, 0, 120),
        spacing=spacing,
        anchor="mm",
        align="center",
        stroke_width=5,
        stroke_fill=(0, 0, 0, 110),
    )
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=max(3, round(8 * scale_x))))
    draw_title_text(text_layer, content, font, center, spacing, scale_x)

    # Cả bóng và chữ cùng xoay nhẹ để theo góc của tờ giấy trong ảnh mẫu.
    shadow_layer = shadow_layer.rotate(TEXT_ANGLE, resample=Image.Resampling.BICUBIC, center=center)
    text_layer = text_layer.rotate(TEXT_ANGLE, resample=Image.Resampling.BICUBIC, center=center)
    result = Image.alpha_composite(base, shadow_layer)
    result = Image.alpha_composite(result, text_layer)
    # Chọn khung theo HƯỚNG ảnh mèo: ảnh DỌC (cao > rộng) → anhdoc.png; ảnh NGANG
    # → ảnh.png. Chỉ dùng MỘT khung, không chồng cả hai. Thiếu khung dọc thì lùi
    # về khung ngang cho an toàn.
    with Image.open(photo_path) as _p:
        is_portrait = _p.height > _p.width
    use_vertical = is_portrait and FRAME_IMAGE_VERTICAL.is_file()
    if use_vertical:
        chosen_frame, chosen_box = FRAME_IMAGE_VERTICAL, FRAME_INNER_BOX_VERTICAL
    else:
        chosen_frame, chosen_box = frame_path, FRAME_INNER_BOX
    # Khung dọc → bo góc ảnh cho đẹp.
    result = add_photo_to_frame(result, photo_path, chosen_frame, chosen_box,
                                round_corners=use_vertical)
    if number:
        result = add_number_to_tag(result, number, number_frame_path)
    result = Image.alpha_composite(result, load_canvas_layer(FOREGROUND_FRAME_IMAGE, result.size))

    output.parent.mkdir(parents=True, exist_ok=True)
    output = unique_path(output)
    result.save(output, format="PNG")
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Điền tiêu đề có đổ bóng vào ảnh mẫu thumbnail.")
    parser.add_argument("--title", default=DEFAULT_TITLE, help="Tiêu đề cần đặt lên ảnh.")
    parser.add_argument("--input", type=Path, default=SOURCE_IMAGE, help="Ảnh PNG mẫu.")
    parser.add_argument(
        "--output",
        type=Path,
        help="File PNG kết quả. Bỏ trống để tự lưu thumbnail01.png, thumbnail02.png, ... trong kịch_bản/output.",
    )
    parser.add_argument("--photo", type=Path, help="Ảnh mèo; mặc định lấy ảnh đầu tiên trong --photo-dir.")
    parser.add_argument("--photo-dir", type=Path, default=CAT_IMAGE_DIR, help="Thư mục chứa ảnh mèo.")
    parser.add_argument("--frame", type=Path, default=FRAME_IMAGE, help="Ảnh PNG khung mèo.")
    parser.add_argument("--number", default=DEFAULT_NUMBER, help="Số hiển thị trên thẻ (mặc định: 01).")
    parser.add_argument("--number-frame", type=Path, default=NUMBER_FRAME_IMAGE, help="Ảnh PNG thẻ số.")
    parser.add_argument("--max-lines", type=int, default=4, help="Số dòng tối đa (mặc định: 4).")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.input.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Không tìm thấy ảnh mẫu: {source}")

    if args.max_lines < 1:
        raise ValueError("--max-lines phải lớn hơn hoặc bằng 1.")
    photo = args.photo.expanduser().resolve() if args.photo else select_default_photo(args.photo_dir.expanduser())
    output_path = args.output.expanduser() if args.output else next_thumbnail_path()
    output = add_title(
        source,
        output_path,
        args.title.strip(),
        photo,
        args.frame.expanduser().resolve(),
        args.number.strip(),
        args.number_frame.expanduser().resolve(),
        args.max_lines,
    )
    print(f"Ảnh trong khung: {photo}")
    print(f"Số trên thẻ: {args.number.strip() or '(không hiển thị)'}")
    print(f"Đã tạo thumbnail: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
