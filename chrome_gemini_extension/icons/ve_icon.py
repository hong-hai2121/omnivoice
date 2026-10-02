"""Vẽ biểu tượng extension OmniVoice Gemini (dịch Trung → Việt) — 02/10/2026.

Cùng tông với biểu tượng OmniVoice (myvoice/web/static/omnivoice-voice.ico): ô vuông bo
góc tím chuyển màu, nét trắng. Hai bong bóng hội thoại: "文" (tiếng Trung) và "Vi"
(tiếng Việt). Cỡ 16 px chỉ giữ chữ "文" cho rõ. Chạy lại để vẽ lại:
    venv\\Scripts\\python.exe chrome_gemini_extension\\icons\\ve_icon.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
FONTS = Path(r"C:\Windows\Fonts")
TOP, BOTTOM = (160, 126, 246), (104, 56, 230)     # tím OmniVoice (trên → dưới)
INK = (98, 52, 222)                                # chữ tím trên nền trắng
SS = 8                                             # vẽ to rồi thu nhỏ cho mượt


def font(name, size):
    return ImageFont.truetype(str(FONTS / name), size)


def background(px):
    """Ô vuông bo góc tím chuyển màu dọc, cỡ px (đã nhân SS)."""
    grad = Image.new("RGBA", (px, px))
    draw = ImageDraw.Draw(grad)
    for y in range(px):
        t = y / (px - 1)
        draw.line([(0, y), (px, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(TOP, BOTTOM)) + (255,))
    mask = Image.new("L", (px, px), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, px - 1, px - 1], radius=round(px * 0.22), fill=255)
    out = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    out.paste(grad, (0, 0), mask)
    return out


def centered_text(draw, box, text, fnt, fill):
    x0, y0, x1, y1 = box
    l, t, r, b = draw.textbbox((0, 0), text, font=fnt)
    draw.text(((x0 + x1 - (r - l)) / 2 - l, (y0 + y1 - (b - t)) / 2 - t), text, font=fnt, fill=fill)


def bubble(draw, box, tail, fill, outline=None, width=0):
    """Bong bóng bo góc + đuôi tam giác (tail = 3 điểm). Có outline thì vẽ một bản
    trắng to hơn `width` bao trọn cả thân lẫn đuôi trước, rồi phủ bản màu lên."""
    radius = round((box[3] - box[1]) * 0.28)
    if outline:
        x0, y0, x1, y1 = box
        draw.rounded_rectangle([x0 - width, y0 - width, x1 + width, y1 + width],
                               radius=radius + width, fill=outline)
        # Nét dày chạy quanh đuôi (nét vẽ ở giữa đường) + chấm tròn ở đỉnh cho bo tròn.
        draw.polygon(tail, fill=outline)
        draw.line(list(tail) + [tail[0]], fill=outline, width=2 * width, joint="curve")
        for x, y in tail:
            draw.ellipse([x - width, y - width, x + width, y + width], fill=outline)
    draw.rounded_rectangle(box, radius=radius, fill=fill)
    draw.polygon(tail, fill=fill)


def full_icon(size):
    px = size * SS
    img = background(px)
    d = ImageDraw.Draw(img)
    u = px / 128                                    # đơn vị theo khung 128
    # Bong bóng sau (trên trái): trắng, chữ "文" tím.
    back = [round(16 * u), round(18 * u), round(80 * u), round(70 * u)]
    bubble(d, back, [(round(26 * u), round(66 * u)), (round(44 * u), round(66 * u)),
                     (round(22 * u), round(84 * u))], fill=(255, 255, 255, 255))
    centered_text(d, back, "文", font("msyhbd.ttc", round(40 * u)), INK + (255,))
    # Bong bóng trước (dưới phải): tím đậm viền trắng, chữ "Vi" trắng.
    front = [round(50 * u), round(56 * u), round(112 * u), round(106 * u)]
    stroke = max(SS, round(5 * u))
    bubble(d, front, [(round(80 * u), round(100 * u)), (round(96 * u), round(100 * u)),
                      (round(100 * u), round(117 * u))],
           fill=BOTTOM + (255,), outline=(255, 255, 255, 255), width=stroke)
    centered_text(d, front, "Vi", font("segoeuib.ttf", round(32 * u)), (255, 255, 255, 255))
    return img.resize((size, size), Image.LANCZOS)


def small_icon(size):
    """16 px: chỉ chữ "文" trắng trên nền tím — hai bong bóng không đọc được ở cỡ này."""
    px = size * SS
    img = background(px)
    d = ImageDraw.Draw(img)
    centered_text(d, [0, 0, px, px], "文", font("msyhbd.ttc", round(px * 0.78)), (255, 255, 255, 255))
    return img.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")       # console Windows cp1252 không in được tiếng Việt
    for size in (16, 32, 48, 128):
        (small_icon if size == 16 else full_icon)(size).save(HERE / f"icon{size}.png")
        print("đã vẽ", HERE / f"icon{size}.png")
    # Ảnh xem trước cả 4 cỡ cạnh nhau (không dùng trong extension).
    sheet = Image.new("RGBA", (16 + 32 + 48 + 128 + 50, 140), (245, 247, 251, 255))
    x = 10
    for size in (16, 32, 48, 128):
        sheet.paste(Image.open(HERE / f"icon{size}.png"), (x, 140 - size - 6), Image.open(HERE / f"icon{size}.png"))
        x += size + 10
    sheet.save(HERE.parent.parent / "chrome_gemini_icon_preview.png")
