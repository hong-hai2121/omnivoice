# -*- coding: utf-8 -*-
r"""Điền tiêu đề có đổ bóng vào mẫu thumbnail dạng tờ giấy.

Chạy từ thư mục gốc OmniVoice:
    venv\Scripts\python myvoice\YOUTUBE\dien_tieu_de_thumbnail.py

Ảnh gốc thumbnail/tiêu đề.png luôn được giữ nguyên. Mặc định file kết quả được
lưu vào myvoice/kịch_bản/output theo tên thumbnail01.png, thumbnail02.png, ...
và không ghi đè bản cũ. Thêm --doc để tạo kèm bản DỌC 1080×1920 (add_title_vertical).
"""

from __future__ import annotations

import argparse
from functools import lru_cache
from itertools import combinations
import random
import re
import sys
import unicodedata
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps


HERE = Path(__file__).resolve().parent
THUMBNAIL_DIR = HERE / "thumbnail"
# Khung tiêu đề (tờ giấy chứa chữ): có NHIỀU mẫu "tiêu đề.png", "tiêu đề 2.png", ... và mỗi
# lần tạo thumbnail chọn NGẪU NHIÊN một mẫu (random_title_template), như nền hoa. Mỗi mẫu có
# vùng đặt chữ khác nhau → khai báo trong TEXT_BOXES; mẫu không có trong bảng dùng TEXT_BOX.
SOURCE_IMAGE = THUMBNAIL_DIR / "tiêu đề.png"   # mẫu gốc: giấy kẻ dòng + kẹp giấy
TITLE_PATTERN = "tiêu đề*.png"
# Nền hoa: có NHIỀU mẫu (khung nen 1.png, khung nen 2.png, ...) và mỗi lần tạo
# thumbnail sẽ chọn NGẪU NHIÊN một mẫu cho mới mẻ. Thêm/bớt nền chỉ cần thêm/xoá
# file "khung nen *.png" trong thư mục thumbnail, không phải sửa code. Ảnh nền tự
# co giãn về đúng canvas nên không bắt buộc cùng kích thước.
BACKGROUND_PATTERN = "khung nen*.png"
# Khung trang trí trên cùng (banner "Mimi Audio"), KHÔNG in sẵn logo. Có nhiều màu đi
# kèm logo cùng màu: "khung trên.png" (vàng) ↔ "logo.png" (hồng), "khung trên xanh.png"
# ↔ "logo xanh.png", ... (xem frame_for_logo). Logo được dán lại vào H_LOGO_BOX.
FOREGROUND_FRAME_IMAGE = THUMBNAIL_DIR / "khung trên.png"
FRAME_IMAGE = THUMBNAIL_DIR / "ảnh.png"              # khung ảnh NGANG (mèo nằm ngang)
# Khung ảnh DỌC: có nhiều màu đi theo logo (anhdoc.png hồng ↔ logo.png, anhdoc tím.png ↔
# logo tím.png, anhdoc đỏ.png ↔ logo đỏ.png ...; xem photo_frame_for_logo). Thiếu màu nào
# thì dùng anhdoc.png. Mỗi khung vẽ chữ nhật viền hơi khác nhau nên hộp ghép ảnh được DÒ
# theo từng khung (frame_inner_box_vertical) chứ không dùng chung một hộp cố định.
FRAME_IMAGE_VERTICAL = THUMBNAIL_DIR / "anhdoc.png"  # khung ảnh DỌC (mèo dọc/đứng)
NUMBER_FRAME_IMAGE = THUMBNAIL_DIR / "Số.png"
# Logo Mimi audio cho bản DỌC: có NHIỀU màu (logo.png hồng, logo xanh.png, logo tím.png,
# logo đỏ.png ...) và mỗi lần tạo thumbnail dọc sẽ chọn NGẪU NHIÊN một logo, giống cách
# chọn nền hoa. Thêm/bớt màu chỉ cần thêm/xoá file "logo*.png" trong thư mục thumbnail.
LOGO_PATTERN = "logo*.png"
LOGO_IMAGE = THUMBNAIL_DIR / "logo.png"  # logo hồng gốc (tách từ khung trên.png) — dự phòng khi không có logo khác
CAT_IMAGE_DIR = HERE.parent / "Anh"
OUTPUT_DIR = HERE.parent / "kịch_bản" / "output"
DEFAULT_TITLE = "Bữa Tiệc Toàn Ngỗng 388 Tệ Và Sự Thật Đau Đớn Sau Nhiều Năm."
DEFAULT_NUMBER = "01"

# Hậu tố thương hiệu "| Mimi audio" CHỈ bỏ khi VẼ chữ lên thumbnail. Tiêu đề để
# COPY (đăng YouTube) đi đường khác (thumbnail_gui._copy_title) nên vẫn giữ nguyên.
_BRAND_SUFFIX_RE = re.compile(r"\s*\|\s*mimi\s*(?:audio|truyện)\s*$", re.IGNORECASE)


def strip_brand_suffix(title: str) -> str:
    """Bỏ phần '| Mimi audio' ở CUỐI tiêu đề (chỉ dùng cho chữ trên thumbnail)."""
    return _BRAND_SUFFIX_RE.sub("", title or "").rstrip()

# Phần giấy có dòng kẻ trong ảnh mẫu (hệ toạ độ 1920×1080). Góc theo mặt giấy;
# ảnh tiêu đề.png gần như PHẲNG NGANG (dòng kẻ ~ -0.4°) nên góc ≈ 0.
# Dùng gần hết phần giấy có dòng kẻ để tiêu đề nổi bật như thumbnail YouTube.
# Đo lại khi đổi ảnh mẫu (bản 2026-07-09 giấy dời xuống/rộng hơn): vùng dòng kẻ
# hiện x≈60→1270, y≈395(dòng đầu)→959(dòng cuối), giấy tới x1330/y1066.
TEXT_BOX = (58, 366, 1258, 974)
# Hộp chữ theo từng mẫu khung tiêu đề (hệ 1920×1080, key = tên file). Đo từ đường viền
# trang trí của mẫu rồi lùi vào để né hoạ tiết góc; mép trên ≥ ~345 để không đè logo.
TEXT_BOXES = {
    "tiêu đề.png": TEXT_BOX,
    "tiêu đề 2.png": (120, 350, 1235, 975),   # sổ pastel viền tím kép (54,289,1301,1033): né tim/sao 4 góc
    "tiêu đề 3.png": (75, 372, 1295, 850),    # thẻ tím viền chấm hồng (62,207,1311,971): né góc gấp xanh (x≥1206, y≥856) + đáy thẻ số đầu mèo (y≤418)
    "tiêu đề 4.png": (140, 365, 1245, 975),   # sổ xanh lá viền kép (74,243,1313,1007): né lá/hoa 4 góc (~130px)
    "tiêu đề 5.png": (120, 395, 1190, 965),   # sổ xanh dương viền kép (56,254,1251,1004): né mặt trời phải trên, mây phải dưới
}
TEXT_ANGLE = 0.0
TEXT_PADDING = 10

# ── Kiểu chữ tiêu đề CỔ ĐIỂN ────────────────────────────────────────────────────
# Serif dày, lõi MỘT màu đỏ rượu/mận đậm (không đỏ tươi), có VIỀN TRẮNG bao quanh
# cho nổi bật, và một BÓNG KEM lệch THẲNG xuống dưới nhẹ → chữ nổi, cổ điển.
TITLE_COLOR = (120, 24, 40)           # đỏ rượu / đỏ mận đậm (lõi chữ)
TITLE_WHITE = (255, 255, 255)         # viền trắng bao quanh chữ
TITLE_CREAM = (250, 244, 230)         # màu BÓNG KEM (bản sao lệch xuống)

# Độ lệch/độ dày (hệ 1920px, tự co theo scale_x).
TITLE_WHITE_STROKE = 4                # bề dày viền trắng quanh chữ
TITLE_CREAM_OFFSET = 6                # bóng kem lệch THẲNG xuống dưới, nhẹ
TITLE_CREAM_STROKE = 2                # bề dày bản sao kem (cho bóng lộ ra dưới viền trắng)

# Vùng BÊN TRONG khung ảnh.png trên canvas 1920×1080. Ảnh mèo bị crop theo
# đúng hình chữ nhật này, sau đó ảnh khung được phủ lên trên để che hoàn toàn phần dư.
FRAME_INNER_BOX = (1225, 452, 1880, 855)
# Lỗ của khung DỌC (anhdoc.png) — dò từ vùng trong suốt bên trong + nới nhẹ để ảnh
# phủ kín dưới viền khung (không hở mép trong suốt).
FRAME_INNER_BOX_VERTICAL = (1285, 159, 1898, 1078)   # hộp của anhdoc.png; DỰ PHÒNG khi dò viền thất bại
# Ảnh mèo phủ RỘNG hơn mép ngoài đường viền khung dọc bấy nhiêu px (trái, trên, phải, dưới)
# để viền nằm đè lên ảnh, không hở mép trong suốt. Đo từ anhdoc.png gốc: viền chữ nhật
# (1321, 190, 1866, 1047) so với hộp FRAME_INNER_BOX_VERTICAL ở trên.
PHOTO_FRAME_OVERLAP = (36, 31, 32, 31)
# Dải dùng để dò đường viền (hệ 1920×1080): đường DỌC đếm trong dải hàng y 350..850, đường
# NGANG đếm trong dải cột x 1400..1750 — vùng giữa cạnh, tránh nơ/tim/sao trang trí ở góc.
FRAME_DETECT_BAND_Y = (350, 850)
FRAME_DETECT_BAND_X = (1400, 1750)
FRAME_DETECT_MIN_FILL = 0.25          # cột/hàng có ≥25% pixel đục trong dải = đường viền (nét đứt vẫn đạt)
# Vị trí logo Mimi audio trên thumbnail NGANG (hệ 1920×1080): đúng hộp mà logo từng
# chiếm trong "khung trên.png" cũ (đo bằng cách so khung cũ với khung đã bỏ logo).
H_LOGO_BOX = (1, 3, 364, 347)
# Bán kính bo góc ảnh khi dùng khung DỌC (theo hệ 1920x1080).
PHOTO_CORNER_RADIUS = 45
PHOTO_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

# Hộp đặt số trong thẻ Số.png (canvas 1920×1080). Thẻ hiện tại (2026-09-03) là hình ĐẦU MÈO
# thẳng đứng: vòng tròn tím bên trong có tâm (1213, 228), đường kính 340, cung trên giữa
# hai tai thấp nhất ở y≈102 → hộp 270×240 quanh tâm, góc 0. Đổi thẻ thì đo lại tâm/đường
# kính vòng đặt số rồi sửa hộp này (thẻ cũ là tag nghiêng: hộp (1318,100,1658,310), góc -13).
NUMBER_TEXT_BOX = (1078, 108, 1348, 348)
NUMBER_ANGLE = 0.0

# ── Thumbnail DỌC (1080×1920, chuẩn YouTube Shorts) ─────────────────────────────
# Bố cục (2026-09-04): nền hoa (khung nen*.png, xoay dọc) → KHUNG TIÊU ĐỀ random
# (tiêu đề*.png) được KÉO DÀI kín khung dọc → hàng đầu: logo (trái) + thẻ số đầu mèo
# (phải) → tiêu đề to ở giữa → ảnh mèo trong khung anhdoc cùng màu logo ở nửa dưới.
# KHÔNG còn dùng ảnh mèo làm nền.
#
# Kéo dài khung tiêu đề: mẫu gốc nằm NGANG (giấy ~1320×900 trên canvas 1920×1080) nên
# co theo bề ngang rồi cắt 3 lát theo chiều dọc: NẮP TRÊN (lỗ gáy, băng dính, kẹp giấy,
# hoạ tiết góc trên) giữ nguyên, DẢI GIỮA (chỉ có viền hai bên + nền giấy) được LẶP cho
# đủ chiều cao, NẮP DƯỚI (hoạ tiết góc dưới, góc gấp) giữ nguyên → không méo hoạ tiết.
# Mỗi mẫu khai báo trong V_TEMPLATES (hệ 1920×1080):
#   paper = (x0, y0, x1, y1) mép tờ giấy (tính cả lỗ gáy; băng dính/kẹp lòi ra ngoài
#           được phép tràn vào lề); band = (y0, y1) dải giữa sạch hoạ tiết để lặp (giấy
#           kẻ dòng: chọn đúng bội số chu kỳ dòng, từ giữa 2 dòng tới giữa 2 dòng);
#   inset = (trái, trên, phải, dưới) lùi từ mép giấy vào vùng đặt nội dung (né băng
#           dính/kẹp ở trên, góc gấp ở dưới). Mẫu lạ dùng V_TEMPLATE_DEFAULT_INSET (dò bbox alpha).
VERTICAL_CANVAS = (1080, 1920)
V_MARGIN = 56                        # lề nền hoa quanh tờ giấy
V_TEMPLATES = {
    "tiêu đề.png":   dict(paper=(10, 189, 1326, 1080), band=(436, 919), inset=(50, 141, 56, 40)),   # giấy kẻ dòng (chu kỳ ~80.6px, dải = 6 dòng), kẹp giấy 2 góc trên
    "tiêu đề 2.png": dict(paper=(17, 192, 1337, 1069), band=(420, 880), inset=(58, 128, 47, 49)),   # sổ pastel viền tím kép, băng dính + tim/sao 4 góc
    "tiêu đề 3.png": dict(paper=(19, 181, 1375, 1024), band=(430, 800), inset=(71, 119, 65, 175)),  # thẻ tím viền chấm hồng; inset dưới lớn né góc gấp xanh (x≥1200, y≥855)
    "tiêu đề 4.png": dict(paper=(34, 145, 1353, 1046), band=(420, 840), inset=(46, 140, 53, 46)),   # sổ xanh lá viền kép, băng dính + lá/hoa 4 góc
    "tiêu đề 5.png": dict(paper=(16, 157, 1291, 1044), band=(420, 820), inset=(54, 128, 56, 54)),   # sổ xanh dương viền kép, mặt trời/mây các góc
}
V_TEMPLATE_DEFAULT_INSET = (60, 150, 60, 50)
V_HEADER_HEIGHT = 300               # hàng logo + thẻ số (px canvas)
V_LOGO_SIZE = 300                   # logo tròn (cắt sát) co vừa hộp vuông này
V_BADGE_WIDTH = 290                 # bề ngang thẻ số đầu mèo (Số.png cắt sát, nhuộm màu logo)
V_ROW_GAP = 34                      # hở giữa hàng đầu / tiêu đề / ảnh
V_TITLE_SHARE = 0.52                # phần chiều cao còn lại dành cho tiêu đề (còn lại là ảnh)
V_TITLE_PAD_X = 10
V_TITLE_STROKE_RATIO = 0.032        # viền trắng MỎNG theo cỡ chữ (tách chữ mà không thành mảng nền)
V_PHOTO_CORNER_RADIUS = 30          # bo góc ảnh trong khung anhdoc (px canvas)
V_FRAME_CAP_EXTRA = 60              # nắp trái/phải khung anhdoc lấn qua đường viền bấy nhiêu px (hệ 1920) để giữ góc/sao
V_SHADOW = dict(offset=(0, 12), blur=16, colour=(45, 15, 35), opacity=0.42)   # bóng đổ chung cho giấy/logo/thẻ số
# Nhuộm thẻ số theo màu logo: nền kem → pha PASTEL (tỷ lệ trắng), viền → màu logo (đường trong)
# tới màu pha (đường ngoài, sáng hơn).
V_BADGE_FILL_WHITE = 0.74
V_BADGE_EDGE_WHITE = 0.40
V_BADGE_NUMBER_COLOUR = (195, 28, 41)      # đỏ như thẻ số bản ngang
V_BADGE_NUMBER_STROKE = (255, 247, 222)


for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)


FONTS_DIR = HERE / "fonts"

# Kiểu chữ tiêu đề: SERIF cổ điển. Mỗi mục là (đường_dẫn, biến_thể) — "biến thể"
# chỉ dùng cho variable font (Merriweather/Lora) để chọn độ đậm; font Windows
# thường để None. Thứ tự = mức ưu tiên, dừng ở font đầu tiên có trên máy.
#   • Merriweather ExtraBold — serif Google Fonts, ĐỦ dấu tiếng Việt; nét đậm vừa
#     phải: nổi trên thumbnail mà vẫn thoáng, dễ đọc (tải sẵn trong fonts/, offline).
#     Đổi biến thể sang "Black" nếu muốn dày khối hơn, "Bold" nếu muốn mảnh hơn.
#   • Lora Bold — serif Google thanh lịch hơn, cũng đủ dấu Việt.
#   • Times/Cambria/Constantia Bold — serif Windows dựng sẵn, ĐÃ KIỂM TRA đủ dấu
#     đôi tiếng Việt (ẫ ệ ự ữ ợ...), dùng khi thiếu font bundle.
# CẢNH BÁO — các font sau THIẾU dấu đôi tiếng Việt (ra ô vuông) nên KHÔNG dùng làm
# fallback: Georgia, Book Antiqua, và Nexa Rust (bản free). PIL/FreeType không tự
# ghép dấu tổ hợp nên font phải có sẵn glyph precomposed thì chữ mới hiện đủ dấu.
_TITLE_FONT_CANDIDATES = (
    (FONTS_DIR / "Merriweather.ttf", "ExtraBold"),
    (FONTS_DIR / "Lora.ttf", "Bold"),
    (Path("C:/Windows/Fonts/timesbd.ttf"), None),    # Times New Roman Bold
    (Path("C:/Windows/Fonts/cambriab.ttf"), None),   # Cambria Bold
    (Path("C:/Windows/Fonts/constanb.ttf"), None),   # Constantia Bold
    (Path("C:/Windows/Fonts/arialbd.ttf"), None),    # cứu cánh cuối: sans đậm
)


@lru_cache(maxsize=256)
def find_font(size: int) -> ImageFont.FreeTypeFont:
    """Font tiêu đề serif cổ điển, đủ dấu tiếng Việt (xem _TITLE_FONT_CANDIDATES)."""
    for font_path, variation in _TITLE_FONT_CANDIDATES:
        if not font_path.exists():
            continue
        font = ImageFont.truetype(str(font_path), size=size)
        if variation:
            try:
                font.set_variation_by_name(variation)
            except (OSError, ValueError):
                # File không phải variable font hoặc thiếu biến thể → giữ nét mặc định.
                pass
        return font
    raise FileNotFoundError("Không tìm thấy font serif hỗ trợ tiếng Việt.")


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
    # CHỐNG TREO: tiêu đề bất thường (rất nhiều từ — thường do parse SEO lấy nhầm cả
    # câu mở đầu) khiến số tổ hợp ngắt dòng bùng nổ giai thừa → CPU treo hàng phút.
    # Quá dài thì bỏ cách "cân đối" (trả None → fit_text hạ cỡ rồi báo lỗi gọn),
    # KHÔNG quét tổ hợp. Tiêu đề thật luôn ngắn (≤ ~16 từ) nên không ảnh hưởng.
    if len(words) > 18:
        return None

    # TĂNG TỐC: bề rộng mỗi cụm từ liên tiếp words[i:j] chỉ đo MỘT lần rồi dùng lại cho
    # mọi tổ hợp ngắt dòng (trước đây đo lại từng dòng của từng tổ hợp → hàng nghìn lần
    # textbbox mỗi cỡ chữ, bản dọc 5 dòng mất ~25 s/ảnh). Kết quả chọn ra KHÔNG đổi.
    span_width: dict[tuple[int, int], int] = {}

    def width_of(start: int, stop: int) -> int:
        key = (start, stop)
        width = span_width.get(key)
        if width is None:
            width = draw.textbbox((0, 0), " ".join(words[start:stop]), font=font, stroke_width=3)[2]
            span_width[key] = width
        return width

    total_width = width_of(0, len(words))
    if total_width <= max_width:
        # Một dòng vừa chỗ luôn thắng điểm (imbalance 0, dòng rộng nhất) → trả ngay.
        return [" ".join(words)]
    space_width = draw.textbbox((0, 0), " ", font=font)[2]

    candidates: list[tuple[tuple[float, float, int], list[str]]] = []
    for line_count in range(2, min(max_lines, len(words)) + 1):
        # Cắt tỉa: tổng bề rộng các dòng ≈ total - (k-1) khoảng trắng, nên dòng rộng nhất
        # ≥ trung bình; trung bình vượt max_width thì không tổ hợp k dòng nào vừa.
        if (total_width - (line_count - 1) * space_width) / line_count > max_width + 4:
            continue
        for breaks in combinations(range(1, len(words)), line_count - 1):
            points = (0, *breaks, len(words))
            widths = [width_of(points[index], points[index + 1]) for index in range(line_count)]
            if max(widths) > max_width:
                continue
            lines = [" ".join(words[points[index]:points[index + 1]]) for index in range(line_count)]

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
        # Giãn dòng RẤT KHÍT (0.08) để chữ TO nhất, lấp đầy giấy. Chỉ chừa tối thiểu
        # cho dấu tiếng Việt cao không dính dòng trên. Tăng số này nếu muốn thoáng hơn.
        spacing = max(6, round(size * 0.08))
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


def list_background_images(thumbnail_dir: Path = THUMBNAIL_DIR) -> list[Path]:
    """Liệt kê các ảnh nền hoa (khung nen 1.png, khung nen 2.png, ...) theo thứ tự."""
    return sorted(thumbnail_dir.glob(BACKGROUND_PATTERN), key=natural_sort_key)


def random_background(thumbnail_dir: Path = THUMBNAIL_DIR) -> Path:
    """Chọn ngẫu nhiên một ảnh nền hoa để mỗi thumbnail trông mới mẻ."""
    backgrounds = list_background_images(thumbnail_dir)
    if not backgrounds:
        raise FileNotFoundError(
            f"Không tìm thấy ảnh nền '{BACKGROUND_PATTERN}' trong {thumbnail_dir}"
        )
    return random.choice(backgrounds)


def list_title_templates(thumbnail_dir: Path = THUMBNAIL_DIR) -> list[Path]:
    """Liệt kê các mẫu khung tiêu đề (tiêu đề.png, tiêu đề 2.png, ...) theo thứ tự."""
    return sorted(thumbnail_dir.glob(TITLE_PATTERN), key=natural_sort_key)


def random_title_template(thumbnail_dir: Path = THUMBNAIL_DIR) -> Path:
    """Chọn ngẫu nhiên một mẫu khung tiêu đề; không có mẫu nào thì về SOURCE_IMAGE."""
    templates = list_title_templates(thumbnail_dir)
    return random.choice(templates) if templates else SOURCE_IMAGE


def text_box_for(source: Path) -> tuple[int, int, int, int]:
    """Hộp chữ (hệ 1920×1080) của một mẫu khung tiêu đề; mẫu lạ dùng TEXT_BOX."""
    name = unicodedata.normalize("NFC", source.name).casefold()
    for key, box in TEXT_BOXES.items():
        if unicodedata.normalize("NFC", key).casefold() == name:
            return box
    return TEXT_BOX


def list_logo_images(thumbnail_dir: Path = THUMBNAIL_DIR) -> list[Path]:
    """Liệt kê các logo (logo.png, logo xanh.png, logo tím.png, ...) theo thứ tự."""
    return sorted(thumbnail_dir.glob(LOGO_PATTERN), key=natural_sort_key)


def random_logo(thumbnail_dir: Path = THUMBNAIL_DIR) -> Path:
    """Chọn ngẫu nhiên một logo cho thumbnail DỌC; không có logo nào thì về LOGO_IMAGE."""
    logos = list_logo_images(thumbnail_dir)
    return random.choice(logos) if logos else LOGO_IMAGE


def colour_variant(base: Path, logo_path: Path) -> Path:
    """File cùng hậu tố màu với logo: base "khung trên.png" + "logo xanh.png" → "khung trên xanh.png".

    Ghép theo hậu tố sau chữ "logo"; không có file màu đó thì trả về base.
    """
    stem = logo_path.stem
    suffix = stem[len("logo"):] if stem.casefold().startswith("logo") else ""
    candidate = logo_path.parent / f"{base.stem}{suffix}{base.suffix}"
    return candidate if candidate.is_file() else base


def frame_for_logo(logo_path: Path) -> Path:
    """Khung trên CÙNG MÀU với logo: "logo xanh.png" → "khung trên xanh.png"."""
    return colour_variant(FOREGROUND_FRAME_IMAGE, logo_path)


def photo_frame_for_logo(logo_path: Path) -> Path:
    """Khung ảnh dọc CÙNG MÀU với logo: "logo tím.png" → "anhdoc tím.png"."""
    return colour_variant(FRAME_IMAGE_VERTICAL, logo_path)


@lru_cache(maxsize=None)
def detect_vertical_frame_border(frame_path: Path) -> tuple[int, int, int, int] | None:
    """Dò chữ nhật viền (mép ngoài, hệ 1920×1080) của khung ảnh dọc từ kênh alpha.

    Chiếu alpha lên trục: cột nào có nhiều pixel đục trong dải FRAME_DETECT_BAND_Y là đường
    viền dọc, hàng nào có nhiều pixel đục trong dải FRAME_DETECT_BAND_X là đường viền ngang.
    Trả về None nếu không thấy đủ 2 đường dọc + 2 đường ngang (khung lạ) → dùng hộp dự phòng.
    """
    try:
        import numpy as np
    except ImportError:
        return None
    frame = Image.open(frame_path).convert("RGBA")
    if frame.size != (1920, 1080):
        frame = frame.resize((1920, 1080), Image.Resampling.LANCZOS)
    opaque = np.array(frame.getchannel("A")) > 32
    y0, y1 = FRAME_DETECT_BAND_Y
    x0, x1 = FRAME_DETECT_BAND_X
    cols = np.where(opaque[y0:y1, :].sum(axis=0) >= FRAME_DETECT_MIN_FILL * (y1 - y0))[0]
    rows = np.where(opaque[:, x0:x1].sum(axis=1) >= FRAME_DETECT_MIN_FILL * (x1 - x0))[0]
    # Cần 2 đường dọc (trái/phải) và 2 đường ngang (trên/dưới) tách xa nhau.
    if len(cols) < 2 or len(rows) < 2 or cols[-1] - cols[0] < 200 or rows[-1] - rows[0] < 200:
        return None
    return int(cols[0]), int(rows[0]), int(cols[-1]), int(rows[-1])


def frame_inner_box_vertical(frame_path: Path) -> tuple[int, int, int, int]:
    """Hộp ghép ảnh (hệ 1920×1080) cho một khung dọc: viền dò được + nới PHOTO_FRAME_OVERLAP."""
    border = detect_vertical_frame_border(frame_path)
    if border is None:
        return FRAME_INNER_BOX_VERTICAL
    left, top, right, bottom = PHOTO_FRAME_OVERLAP
    return (max(0, border[0] - left), max(0, border[1] - top),
            min(1920, border[2] + right), min(1080, border[3] + bottom))


def load_logo_cropped(logo_path: Path) -> Image.Image:
    """Nạp logo RGBA và cắt sát phần có hình (bỏ lề trong suốt của file 1920×1080)."""
    logo = Image.open(logo_path).convert("RGBA")
    bbox = logo.getchannel("A").point(lambda a: 255 if a > 32 else 0).getbbox()
    return logo.crop(bbox) if bbox else logo


def add_logo_to_frame(base: Image.Image, logo_path: Path) -> Image.Image:
    """Dán logo vào góc trái trên (H_LOGO_BOX) — chỗ logo từng nằm trong khung trên cũ."""
    if not logo_path.is_file():
        return base
    width, height = base.size
    scale_x, scale_y = width / 1920, height / 1080
    x0, y0, x1, y1 = H_LOGO_BOX
    box_w = round(x1 * scale_x) - round(x0 * scale_x)
    box_h = round(y1 * scale_y) - round(y0 * scale_y)
    logo = ImageOps.contain(load_logo_cropped(logo_path), (box_w, box_h),
                            method=Image.Resampling.LANCZOS)
    pos = (round(x0 * scale_x) + (box_w - logo.width) // 2,
           round(y0 * scale_y) + (box_h - logo.height) // 2)
    result = base.copy()
    result.alpha_composite(logo, pos)
    return result


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
        # Nhân với alpha có sẵn để ảnh cutout (nền trong suốt) không thành mảng đen.
        photo.putalpha(ImageChops.multiply(photo.getchannel("A"), mask))
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


def draw_title_text(
    layer: Image.Image,
    content: str,
    font: ImageFont.FreeTypeFont,
    center: tuple[int, int],
    spacing: int,
    scale_x: float,
) -> None:
    """Vẽ tiêu đề cổ điển: BÓNG KEM lệch xuống → viền TRẮNG → lõi đỏ rượu đồng nhất."""
    draw = ImageDraw.Draw(layer)
    common = dict(font=font, spacing=spacing, anchor="mm", align="center")
    cx, cy = center
    down = round(TITLE_CREAM_OFFSET * scale_x)
    white_w = max(2, round(TITLE_WHITE_STROKE * scale_x))
    cream_stroke = max(1, round(TITLE_CREAM_STROKE * scale_x))

    # 1) Bóng kem: bản sao màu kem lệch THẲNG xuống, hơi dày hơn cả viền trắng để
    #    ló ra phía dưới viền (không lệch ngang → không nghiêng).
    draw.multiline_text(
        (cx, cy + down), content, fill=(*TITLE_CREAM, 255),
        stroke_width=white_w + cream_stroke, stroke_fill=(*TITLE_CREAM, 255), **common,
    )
    # 2) Viền TRẮNG bao quanh + lõi chữ đỏ rượu / mận đậm (MỘT màu đồng nhất).
    draw.multiline_text(
        center, content, fill=(*TITLE_COLOR, 255),
        stroke_width=white_w, stroke_fill=(*TITLE_WHITE, 255), **common,
    )


def _fit_vertical_title(
    title: str, box_width: int, box_height: int, max_lines: int = 5
) -> tuple[ImageFont.FreeTypeFont, str, int, int]:
    """Tìm cỡ font + cách ngắt dòng lớn nhất vừa hộp tiêu đề bản dọc.

    Trả về (font, nội_dung_đã_ngắt_dòng, spacing, stroke) — stroke là độ dày viền
    trắng; đo bằng viền ngoài cùng (dày hơn) để chữ chắc chắn không tràn hộp.
    """
    measure = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    maximum_size = max(60, round(min(box_width * 0.26, box_height * 0.5)))
    for size in range(maximum_size, 40, -2):
        font = find_font(size)
        lines = balanced_wrap(measure, title, font, box_width, max_lines)
        if lines is None:
            continue
        content = "\n".join(lines)
        spacing = max(8, round(size * 0.16))
        stroke = max(3, round(size * V_TITLE_STROKE_RATIO))
        edge = stroke + max(2, round(stroke * 0.35))   # viền ngoài cùng — dày nhất
        left, top, right, bottom = measure.multiline_textbbox(
            (0, 0), content, font=font, spacing=spacing, stroke_width=edge
        )
        if right - left <= box_width and bottom - top <= box_height:
            return font, content, spacing, stroke
    raise ValueError("Tiêu đề quá dài để đặt lên thumbnail dọc.")


def _draw_vertical_title(
    layer: Image.Image,
    content: str,
    font: ImageFont.FreeTypeFont,
    center: tuple[int, int],
    spacing: int,
    stroke: int,
) -> None:
    """Vẽ tiêu đề bản dọc: BÓNG KEM lệch xuống → viền TRẮNG → lõi đỏ rượu đồng nhất."""
    draw = ImageDraw.Draw(layer)
    common = dict(font=font, spacing=spacing, anchor="mm", align="center")
    cx, cy = center
    down = max(1, round(stroke * 1.2))   # bóng kem lệch xuống theo cỡ chữ bản dọc
    # 1) Bóng kem lệch thẳng xuống (bản sao màu kem, dày hơn viền trắng để ló ra dưới).
    draw.multiline_text((cx, cy + down), content, fill=(*TITLE_CREAM, 255),
                        stroke_width=round(stroke * 1.5), stroke_fill=(*TITLE_CREAM, 255), **common)
    # 2) Viền TRẮNG bao quanh + lõi chữ đỏ rượu đồng nhất.
    draw.multiline_text(center, content, fill=(*TITLE_COLOR, 255),
                        stroke_width=stroke, stroke_fill=(*TITLE_WHITE, 255), **common)


# ── Bản dọc: kéo dài khung tiêu đề ───────────────────────────────────────────────
def vertical_template_geometry(source: Path) -> tuple[tuple[int, int, int, int], tuple[int, int], tuple[int, int, int, int]]:
    """(paper, band, inset) hệ 1920×1080 của một mẫu khung tiêu đề; mẫu lạ dò theo bbox alpha."""
    name = unicodedata.normalize("NFC", source.name).casefold()
    for key, geo in V_TEMPLATES.items():
        if unicodedata.normalize("NFC", key).casefold() == name:
            return geo["paper"], geo["band"], geo["inset"]
    layer = Image.open(source).convert("RGBA")
    if layer.size != (1920, 1080):
        layer = layer.resize((1920, 1080), Image.Resampling.LANCZOS)
    bbox = layer.getchannel("A").point(lambda a: 255 if a > 32 else 0).getbbox() or (0, 0, 1920, 1080)
    x0, y0, x1, y1 = bbox
    # Dải giữa = 30% chiều cao ở chính giữa giấy: thường chỉ có viền hai bên.
    band = (round(y0 + (y1 - y0) * 0.35), round(y0 + (y1 - y0) * 0.65))
    return bbox, band, V_TEMPLATE_DEFAULT_INSET


def expand_layer(layer: Image.Image, cap_end: int, cap_start: int, target: int, axis: str = "y") -> Image.Image:
    """Kéo dài một lớp RGBA theo trục axis bằng cách LẶP dải giữa, giữ nguyên 2 nắp.

    axis="y": nắp trên = hàng 0..cap_end, dải giữa = cap_end..cap_start, nắp dưới = cap_start..hết;
    kết quả cao đúng `target`. axis="x" tương tự theo cột. Dải giữa được co nhẹ để lặp
    đúng số nguyên lần (mối nối rơi vào đúng cuối dải, không cắt dở chu kỳ hoạ tiết).
    Nếu target ngắn hơn 2 nắp thì cắt bớt nắp trên (không lặp).
    """
    if axis == "x":
        # Xoay 90° để dùng lại đường đi theo trục y: cột x → hàng (width - x).
        rotated = expand_layer(layer.transpose(Image.Transpose.ROTATE_90),
                               layer.width - cap_start, layer.width - cap_end, target, "y")
        return rotated.transpose(Image.Transpose.ROTATE_270)
    width, height = layer.size
    cap_end = max(0, min(cap_end, height))
    cap_start = max(cap_end, min(cap_start, height))
    top = layer.crop((0, 0, width, cap_end))
    bottom = layer.crop((0, cap_start, width, height))
    mid = layer.crop((0, cap_end, width, cap_start))
    need = target - top.height - bottom.height
    out = Image.new("RGBA", (width, target), (0, 0, 0, 0))
    if need < 0:
        # Không đủ chỗ cho cả 2 nắp: cắt bớt phần dưới của nắp trên.
        top = top.crop((0, 0, width, max(0, top.height + need)))
    out.paste(top, (0, 0))
    if need > 0 and mid.height > 0:
        repeats = max(1, round(need / mid.height))
        tile_h = max(1, -(-need // repeats))
        tile = mid.resize((width, tile_h), Image.Resampling.LANCZOS)
        y = top.height
        while y < top.height + need:
            piece = min(tile_h, top.height + need - y)
            out.paste(tile.crop((0, 0, width, piece)), (0, y))
            y += piece
    out.paste(bottom, (0, target - bottom.height))
    return out


def _composite_clipped(base: Image.Image, layer: Image.Image, pos: tuple[int, int]) -> None:
    """alpha_composite cho phép toạ độ âm / tràn mép (tự cắt phần ngoài canvas)."""
    x, y = pos
    left, top = max(0, -x), max(0, -y)
    right = min(layer.width, base.width - x)
    bottom = min(layer.height, base.height - y)
    if right <= left or bottom <= top:
        return
    base.alpha_composite(layer.crop((left, top, right, bottom)), (x + left, y + top))


def paste_with_shadow(base: Image.Image, sprite: Image.Image, pos: tuple[int, int]) -> None:
    """Dán sprite RGBA lên base (tại chỗ) kèm bóng đổ mềm phía dưới (V_SHADOW)."""
    ox, oy = V_SHADOW["offset"]
    blur = V_SHADOW["blur"]
    pad = blur * 3
    shadow = Image.new("RGBA", (sprite.width + 2 * pad, sprite.height + 2 * pad), (0, 0, 0, 0))
    alpha = sprite.getchannel("A").point(lambda a: round(a * V_SHADOW["opacity"]))
    tint = Image.new("RGBA", sprite.size, (*V_SHADOW["colour"], 255))
    tint.putalpha(alpha)
    shadow.paste(tint, (pad, pad))
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
    _composite_clipped(base, shadow, (pos[0] - pad + ox, pos[1] - pad + oy))
    _composite_clipped(base, sprite, pos)


def build_vertical_paper(source: Path) -> tuple[Image.Image, tuple[int, int, int, int]]:
    """Khung tiêu đề kéo dài kín canvas dọc (kèm bóng) + hộp nội dung (px canvas)."""
    paper, band, inset = vertical_template_geometry(source)
    canvas_w, canvas_h = VERTICAL_CANVAS
    px0, py0, px1, py1 = paper
    scale = (canvas_w - 2 * V_MARGIN) / (px1 - px0)
    layer = Image.open(source).convert("RGBA")
    if layer.size != (1920, 1080):
        layer = layer.resize((1920, 1080), Image.Resampling.LANCZOS)
    layer = layer.resize((round(1920 * scale), round(1080 * scale)), Image.Resampling.LANCZOS)
    paper_h_target = canvas_h - 2 * V_MARGIN
    expanded_h = layer.height + paper_h_target - round((py1 - py0) * scale)
    layer = expand_layer(layer, round(band[0] * scale), round(band[1] * scale), expanded_h, "y")
    out = Image.new("RGBA", VERTICAL_CANVAS, (0, 0, 0, 0))
    paste_with_shadow(out, layer, (V_MARGIN - round(px0 * scale), V_MARGIN - round(py0 * scale)))
    il, it, ir, ib = inset
    content = (V_MARGIN + round(il * scale), V_MARGIN + round(it * scale),
               canvas_w - V_MARGIN - round(ir * scale), canvas_h - V_MARGIN - round(ib * scale))
    return out, content


def vertical_background(path: Path) -> Image.Image:
    """Nền hoa cho bản dọc: ảnh ngang thì XOAY 90° (nét hơn crop dải hẹp) rồi phủ kín canvas."""
    background = Image.open(path).convert("RGBA")
    if background.width > background.height:
        background = background.rotate(90, expand=True)
    return ImageOps.fit(background, VERTICAL_CANVAS, method=Image.Resampling.LANCZOS)


# ── Bản dọc: logo, thẻ số, khung ảnh ─────────────────────────────────────────────
@lru_cache(maxsize=None)
def logo_accent_colour(logo_path: Path) -> tuple[int, int, int]:
    """Màu chủ đạo (đậm, bão hoà) của logo — trung vị các pixel bão hoà; dùng nhuộm thẻ số."""
    fallback = (170, 90, 210)
    try:
        import numpy as np
    except ImportError:
        return fallback
    logo = load_logo_cropped(logo_path)
    if logo.width > 400:
        logo = logo.resize((400, round(logo.height * 400 / logo.width)))
    px = np.asarray(logo).astype(int)
    rgb, alpha = px[..., :3], px[..., 3]
    sat = rgb.max(axis=2) - rgb.min(axis=2)
    mask = (alpha > 200) & (sat > 90) & (rgb.max(axis=2) > 90)
    if mask.sum() < 50:
        return fallback
    return tuple(int(v) for v in np.median(rgb[mask], axis=0))


def _mix_white(colour: tuple[int, int, int], white: float) -> tuple[int, int, int]:
    return tuple(round(c + (255 - c) * white) for c in colour)


def tinted_number_tag(tag_path: Path, accent: tuple[int, int, int]) -> Image.Image:
    """Thẻ Số.png (đầu mèo) cắt sát và nhuộm theo màu logo: nền kem → pastel, viền → màu logo.

    Nền kem gần trùng màu giấy nên thẻ nguyên bản đặt lên giấy sẽ chìm; nhuộm để nổi.
    Không có numpy thì trả thẻ nguyên bản (chỉ cắt sát).
    """
    tag = Image.open(tag_path).convert("RGBA")
    bbox = tag.getchannel("A").point(lambda a: 255 if a > 32 else 0).getbbox()
    tag = tag.crop(bbox) if bbox else tag
    try:
        import numpy as np
    except ImportError:
        return tag
    px = np.asarray(tag).astype(float)
    rgb, alpha = px[..., :3], px[..., 3]
    fill = np.array(_mix_white(accent, V_BADGE_FILL_WHITE), dtype=float)
    edge_dark = np.array(accent, dtype=float)
    edge_light = np.array(_mix_white(accent, V_BADGE_EDGE_WHITE), dtype=float)
    is_fill = rgb.min(axis=2) >= 225
    lum = rgb.mean(axis=2)
    opaque = alpha > 32
    edge_lum = lum[opaque & ~is_fill]
    lo, hi = (np.percentile(edge_lum, 5), np.percentile(edge_lum, 95)) if edge_lum.size else (0.0, 255.0)
    t = np.clip((lum - lo) / max(hi - lo, 1.0), 0.0, 1.0)[..., None]
    edge = edge_dark * (1 - t) + edge_light * t
    out = np.where(is_fill[..., None], fill, edge)
    px[..., :3] = np.where(opaque[..., None], out, rgb)
    return Image.fromarray(px.clip(0, 255).astype("uint8"))   # 4 kênh uint8 → RGBA


def _vertical_badge_sprite(number: str, accent: tuple[int, int, int]) -> Image.Image:
    """Sprite thẻ số bản dọc: đầu mèo nhuộm màu + chữ 'SỐ' nhỏ + số tập to (cỡ V_BADGE_WIDTH)."""
    if not NUMBER_FRAME_IMAGE.is_file():
        raise FileNotFoundError(f"Không tìm thấy khung số: {NUMBER_FRAME_IMAGE}")
    tag = tinted_number_tag(NUMBER_FRAME_IMAGE, accent)
    scale = V_BADGE_WIDTH / tag.width
    tag = tag.resize((V_BADGE_WIDTH, round(tag.height * scale)), Image.Resampling.LANCZOS)
    # Tâm/bán kính vòng tròn trong thẻ (đo từ Số.png: tâm (1213,228), đường kính 340 trên
    # canvas 1920×1080; bbox thẻ bắt đầu (1016,31)) → đổi sang toạ độ sprite.
    src_bbox = Image.open(NUMBER_FRAME_IMAGE).convert("RGBA").getchannel("A").point(
        lambda a: 255 if a > 32 else 0).getbbox() or (1016, 31, 1408, 419)
    cx = round((1213 - src_bbox[0]) * scale)
    cy = round((228 - src_bbox[1]) * scale)
    radius = round(170 * scale)
    draw = ImageDraw.Draw(tag)
    red, cream = (*V_BADGE_NUMBER_COLOUR, 255), (*V_BADGE_NUMBER_STROKE, 255)
    label_font = find_font(max(20, round(radius * 0.30)))
    draw.text((cx, cy - round(radius * 0.56)), "SỐ", font=label_font, anchor="mm",
              fill=red, stroke_width=3, stroke_fill=cream)
    # Số tập: co cỡ để 1–3 chữ số nằm gọn trong vòng tròn (dưới chữ SỐ).
    max_w, max_h = round(radius * 1.45), round(radius * 1.0)
    number_font = find_font(30)
    for size in range(round(radius * 1.15), 30, -3):
        font = find_font(size)
        left, top, right, bottom = draw.textbbox((0, 0), number, font=font, stroke_width=6)
        if right - left <= max_w and bottom - top <= max_h:
            number_font = font
            break
    draw.text((cx, cy + round(radius * 0.22)), number, font=number_font, anchor="mm",
              fill=red, stroke_width=6, stroke_fill=cream)
    return tag


def _vertical_photo_frame(frame_path: Path, box: tuple[int, int, int, int]) -> tuple[Image.Image, tuple[int, int, int, int]]:
    """Khung anhdoc (dọc) kéo NGANG cho vừa hộp box (px canvas): (sprite khung, hộp ảnh trong sprite).

    Co khung theo chiều cao hộp rồi lặp dải giữa (viền trên/dưới) theo trục x cho đủ bề
    ngang; nắp trái/phải giữ viền đứng + sao/tim ở góc. Hộp ảnh = đường viền dò được ±
    PHOTO_FRAME_OVERLAP, đổi sang toạ độ sprite sau khi kéo.
    """
    frame = Image.open(frame_path).convert("RGBA")
    if frame.size != (1920, 1080):
        frame = frame.resize((1920, 1080), Image.Resampling.LANCZOS)
    bbox = frame.getchannel("A").point(lambda a: 255 if a > 32 else 0).getbbox() or (0, 0, 1920, 1080)
    border = detect_vertical_frame_border(frame_path) or (
        FRAME_INNER_BOX_VERTICAL[0] + PHOTO_FRAME_OVERLAP[0], FRAME_INNER_BOX_VERTICAL[1] + PHOTO_FRAME_OVERLAP[1],
        FRAME_INNER_BOX_VERTICAL[2] - PHOTO_FRAME_OVERLAP[2], FRAME_INNER_BOX_VERTICAL[3] - PHOTO_FRAME_OVERLAP[3])
    target_w, target_h = box[2] - box[0], box[3] - box[1]
    scale = target_h / (bbox[3] - bbox[1])
    sprite = frame.crop(bbox).resize((round((bbox[2] - bbox[0]) * scale), target_h), Image.Resampling.LANCZOS)
    cap_l = round((border[0] - bbox[0] + V_FRAME_CAP_EXTRA) * scale)
    cap_r = round((border[2] - bbox[0] - V_FRAME_CAP_EXTRA) * scale)
    if sprite.width < target_w:
        sprite = expand_layer(sprite, cap_l, cap_r, target_w, "x")
    ol, ot, orr, ob = PHOTO_FRAME_OVERLAP
    inner = (round((border[0] - ol - bbox[0]) * scale),
             round((border[1] - ot - bbox[1]) * scale),
             sprite.width - round((bbox[2] - border[2] - orr) * scale),
             sprite.height - round((bbox[3] - border[3] - ob) * scale))
    return sprite, inner


def add_vertical_photo(base: Image.Image, photo_path: Path, frame_path: Path,
                       box: tuple[int, int, int, int]) -> None:
    """Ghép ảnh mèo (cover, bo góc) vào khung anhdoc kéo ngang đặt tại box; sửa base tại chỗ."""
    if not photo_path.is_file():
        raise FileNotFoundError(f"Không tìm thấy ảnh mèo: {photo_path}")
    if not frame_path.is_file():
        raise FileNotFoundError(f"Không tìm thấy ảnh khung: {frame_path}")
    sprite, inner = _vertical_photo_frame(frame_path, box)
    inner_size = (max(1, inner[2] - inner[0]), max(1, inner[3] - inner[1]))
    photo = Image.open(photo_path).convert("RGBA")
    photo = ImageOps.fit(photo, inner_size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.4))
    mask = Image.new("L", inner_size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, inner_size[0] - 1, inner_size[1] - 1),
                                           radius=V_PHOTO_CORNER_RADIUS, fill=255)
    # NHÂN với alpha có sẵn: ảnh mèo cutout (nền trong suốt) giữ trong suốt → lộ nền giấy,
    # không thành mảng ĐEN như khi putalpha thay hẳn alpha.
    photo.putalpha(ImageChops.multiply(photo.getchannel("A"), mask))
    # Căn giữa sprite trong box theo bề ngang (khung có thể hẹp hơn box nếu không kéo được).
    x = box[0] + (box[2] - box[0] - sprite.width) // 2
    y = box[1]
    _composite_clipped(base, photo, (x + inner[0], y + inner[1]))
    _composite_clipped(base, sprite, (x, y))


def add_title_vertical(
    output: Path,
    title: str,
    photo_path: Path,
    number: str,
    logo_path: Path | None = None,
    max_lines: int = 5,
    source: Path | None = None,
    background: Path | None = None,
) -> Path:
    """Tạo thumbnail DỌC 1080×1920: nền hoa + khung tiêu đề kéo dài kín khung + logo +
    thẻ số đầu mèo + tiêu đề + ảnh mèo trong khung anhdoc.

    Dùng chung ảnh/tiêu đề/số tập với bản ngang; ảnh mèo nằm trong khung (KHÔNG làm nền).
    File lưu cùng thư mục output, không ghi đè bản cũ (unique_path). Không truyền
    logo_path/source/background → chọn NGẪU NHIÊN logo "logo*.png" (khung ảnh + màu thẻ số
    đi theo), mẫu khung tiêu đề "tiêu đề*.png" và nền hoa "khung nen*.png".
    """
    if not photo_path.is_file():
        raise FileNotFoundError(f"Không tìm thấy ảnh mèo: {photo_path}")
    title = strip_brand_suffix(title)   # bỏ '| Mimi audio' khỏi chữ trên thumbnail
    if logo_path is None:
        logo_path = random_logo()
    if source is None:
        source = random_title_template()
    if background is None:
        background = random_background()

    # 1) Nền hoa xoay dọc + 2) khung tiêu đề kéo dài kín canvas (kèm bóng).
    base = vertical_background(background)
    paper, content = build_vertical_paper(source)
    base.alpha_composite(paper)
    cx0, cy0, cx1, cy1 = content

    # 3) Hàng đầu: logo tròn (trái) + thẻ số đầu mèo nhuộm màu logo (phải).
    accent = logo_accent_colour(logo_path) if logo_path.is_file() else (170, 90, 210)
    if logo_path.is_file():
        logo = ImageOps.contain(load_logo_cropped(logo_path), (V_LOGO_SIZE, V_HEADER_HEIGHT),
                                method=Image.Resampling.LANCZOS)
        paste_with_shadow(base, logo, (cx0, cy0 + (V_HEADER_HEIGHT - logo.height) // 2))
    if number:
        badge = _vertical_badge_sprite(number, accent)
        paste_with_shadow(base, badge, (cx1 - badge.width, cy0 + (V_HEADER_HEIGHT - badge.height) // 2))

    # 4) Chia phần còn lại cho tiêu đề (trên) và ảnh (dưới).
    body_top = cy0 + V_HEADER_HEIGHT + V_ROW_GAP
    remaining = cy1 - body_top - V_ROW_GAP
    title_h = round(remaining * V_TITLE_SHARE)
    photo_box = (cx0, cy1 - (remaining - title_h), cx1, cy1)
    title_box = (cx0 + V_TITLE_PAD_X, body_top, cx1 - V_TITLE_PAD_X, body_top + title_h)

    # 5) Tiêu đề.
    box_width, box_height = title_box[2] - title_box[0], title_box[3] - title_box[1]
    center = ((title_box[0] + title_box[2]) // 2, (title_box[1] + title_box[3]) // 2)
    font, content_text, spacing, stroke = _fit_vertical_title(title, box_width, box_height, max_lines)
    title_layer = Image.new("RGBA", VERTICAL_CANVAS, (0, 0, 0, 0))
    _draw_vertical_title(title_layer, content_text, font, center, spacing, stroke)
    base.alpha_composite(title_layer)

    # 6) Ảnh mèo trong khung anhdoc cùng màu logo (kéo ngang vừa bề rộng nội dung).
    frame_path = photo_frame_for_logo(logo_path)
    if not frame_path.is_file():
        frame_path = FRAME_IMAGE_VERTICAL
    add_vertical_photo(base, photo_path, frame_path, photo_box)

    output.parent.mkdir(parents=True, exist_ok=True)
    output = unique_path(output)
    base.convert("RGB").save(output, format="PNG")
    return output


def add_title(
    source: Path | None,
    output: Path,
    title: str,
    photo_path: Path,
    frame_path: Path,
    number: str,
    number_frame_path: Path,
    max_lines: int = 4,
    background: Path | None = None,
    logo: Path | None = None,
) -> Path:
    title = strip_brand_suffix(title)   # bỏ '| Mimi audio' khỏi chữ trên thumbnail
    # Không truyền mẫu khung tiêu đề → chọn NGẪU NHIÊN một mẫu "tiêu đề*.png".
    if source is None:
        source = random_title_template()
    paper = Image.open(source).convert("RGBA")
    # Thứ tự lớp: nền hoa → tờ giấy/ảnh/nội dung → khung trang trí trên cùng.
    # Không truyền nền cụ thể → chọn NGẪU NHIÊN một mẫu "khung nen *.png".
    if background is None:
        background = random_background()
    background_layer = load_canvas_layer(background, paper.size)
    base = Image.alpha_composite(background_layer, paper)
    width, height = base.size

    # Tỷ lệ này được thiết kế cho ảnh 1920x1080; vẫn co giãn nếu ảnh mẫu thay đổi kích thước.
    scale_x = width / 1920
    scale_y = height / 1080
    x0, y0, x1, y1 = text_box_for(source)   # mỗi mẫu khung tiêu đề có vùng đặt chữ riêng
    box = (
        round(x0 * scale_x), round(y0 * scale_y),
        round(x1 * scale_x), round(y1 * scale_y),
    )
    box_width, box_height = box[2] - box[0], box[3] - box[1]
    center = ((box[0] + box[2]) // 2, (box[1] + box[3]) // 2)

    font, content, spacing = fit_text(title, box_width, box_height, max_lines)
    text_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))

    # Chữ cổ điển: bóng KEM lệch thẳng xuống + lõi đỏ rượu (xem draw_title_text).
    draw_title_text(text_layer, content, font, center, spacing, scale_x)

    # Xoay nhẹ theo góc của tờ giấy trong ảnh mẫu (góc ≈ 0 với ảnh phẳng hiện tại).
    text_layer = text_layer.rotate(TEXT_ANGLE, resample=Image.Resampling.BICUBIC, center=center)
    result = Image.alpha_composite(base, text_layer)
    # Chọn logo TRƯỚC vì khung ảnh dọc và khung trên đều đi theo màu logo.
    if logo is None:
        logo = random_logo()
    # LUÔN dùng khung ảnh DỌC (anhdoc*.png, cùng màu logo) cho mọi thumbnail — KHÔNG dùng
    # khung NGANG (ảnh.png) nữa. Ảnh mèo (ngang hay dọc) đều được crop cover vào khung dọc
    # và bo góc cho đẹp; hộp ghép ảnh dò theo từng khung màu để không lệch viền.
    # Chỉ lùi về khung ngang nếu THIẾU file anhdoc.png.
    photo_frame = photo_frame_for_logo(logo)
    if photo_frame.is_file():
        chosen_frame, chosen_box, round_corners = photo_frame, frame_inner_box_vertical(photo_frame), True
    else:
        chosen_frame, chosen_box, round_corners = frame_path, FRAME_INNER_BOX, False
    result = add_photo_to_frame(result, photo_path, chosen_frame, chosen_box,
                                round_corners=round_corners)
    if number:
        result = add_number_to_tag(result, number, number_frame_path)
    # Khung trang trí trên cùng CÙNG MÀU logo (frame_for_logo). Khung trên không còn in sẵn
    # logo nên logo được dán lại đúng vị trí gốc (H_LOGO_BOX), lớp trên cùng.
    result = Image.alpha_composite(result, load_canvas_layer(frame_for_logo(logo), result.size))
    result = add_logo_to_frame(result, logo)

    output.parent.mkdir(parents=True, exist_ok=True)
    output = unique_path(output)
    result.save(output, format="PNG")
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Điền tiêu đề có đổ bóng vào ảnh mẫu thumbnail.")
    parser.add_argument("--title", default=DEFAULT_TITLE, help="Tiêu đề cần đặt lên ảnh.")
    parser.add_argument("--input", type=Path,
                        help="Mẫu khung tiêu đề cụ thể. Bỏ trống để chọn ngẫu nhiên trong các 'tiêu đề*.png'.")
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
    parser.add_argument("--background", type=Path,
                        help="Ảnh nền hoa cụ thể. Bỏ trống để chọn ngẫu nhiên trong các 'khung nen *.png'.")
    parser.add_argument("--logo", type=Path,
                        help="Logo cụ thể (logo.png, logo xanh.png ...). Bỏ trống để chọn ngẫu nhiên; "
                             "khung trên tự đi theo màu logo.")
    parser.add_argument("--doc", action="store_true",
                        help="Tạo thêm bản DỌC 1080×1920 (cùng ảnh/tiêu đề/số/logo/khung tiêu đề/nền), tên thêm hậu tố _doc.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.input.expanduser().resolve() if args.input else random_title_template()
    if not source.is_file():
        raise FileNotFoundError(f"Không tìm thấy ảnh mẫu: {source}")

    if args.max_lines < 1:
        raise ValueError("--max-lines phải lớn hơn hoặc bằng 1.")
    photo = args.photo.expanduser().resolve() if args.photo else select_default_photo(args.photo_dir.expanduser())
    output_path = args.output.expanduser() if args.output else next_thumbnail_path()
    # Chọn nền tại đây để in ra đúng mẫu đã dùng (không truyền → add_title tự random).
    background = args.background.expanduser().resolve() if args.background else random_background()
    logo = args.logo.expanduser().resolve() if args.logo else random_logo()
    output = add_title(
        source,
        output_path,
        args.title.strip(),
        photo,
        args.frame.expanduser().resolve(),
        args.number.strip(),
        args.number_frame.expanduser().resolve(),
        args.max_lines,
        background,
        logo=logo,
    )
    print(f"Ảnh trong khung: {photo}")
    print(f"Khung tiêu đề: {source.name}")
    print(f"Nền hoa: {background.name}")
    print(f"Logo: {logo.name} — khung trên: {frame_for_logo(logo).name} — khung ảnh: {photo_frame_for_logo(logo).name}")
    print(f"Số trên thẻ: {args.number.strip() or '(không hiển thị)'}")
    print(f"Đã tạo thumbnail: {output}")
    if args.doc:
        output_doc = add_title_vertical(
            output.with_name(f"{output.stem}_doc{output.suffix}"), args.title.strip(), photo,
            args.number.strip(), logo_path=logo, source=source, background=background)
        print(f"Đã tạo thumbnail dọc: {output_doc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
