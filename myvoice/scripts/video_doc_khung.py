"""
video_doc_khung.py — Dựng video DỌC 1080×1920 từ VIDEO GỐC của bản ngang, KHÔNG ghép
clip dọc nữa (yêu cầu 08/09/2026: tiết kiệm thời gian, bản dọc dùng lại video ngang).

"Video gốc" = đoạn video đã ghép của bản ngang TRƯỚC khi lồng khung khung0/khung1/khung2
(video_khung.build_video(goc_out=...) xuất thêm file YOUTUBE_goc.mp4 ngay trong cùng một
lượt ffmpeg). Tập cũ không có file gốc thì CẮT vùng trong khung1 của YOUTUBE.mp4 — hình y
hệt, chỉ khác là đã có phụ đề ngang trong hình.

Bố cục (bản thiết kế "Màn hình dọc Mimi audio", đã xem trên web + ảnh ở Downloads):
  • NỀN      : nền hoa xoay dọc (YOUTUBE/thumbnail/khung nen*.png) — cùng bộ thumbnail dọc.
  • GIỮA     : dải video BAND (y 587→1333, tỉ lệ đúng vùng trong khung1 ≈ 1,45) — video gốc
               phủ kín; viền là khung "anhdoc <màu>.png" (bộ thumbnail) XOAY NGANG.
  • TRÊN     : logo (trái) + thẻ Số đầu mèo (phải) + TIÊU ĐỀ tập trên tờ giấy.
  • DƯỚI     : ảnh mèo (kho Anh/) + thẻ "Nghe trọn tập tại kênh Mimi audio" (font Coiny
               dễ thương) + nút Đăng ký (cắt từ khung2 của bản ngang) + #MimiAudioSoN.

Bộ khung TĨNH ba màu (tím / xanh / đỏ) được TẠO SẴN MỘT LẦN vào Backbround/khungdoc/
("khungdoc <màu>.png" + khungdoc.json ghi toạ độ) — tao_khung_san(). Lần dựng sau chỉ
đọc file trong thư mục (muốn đổi hình, sửa/thay PNG ở đó hoặc chạy `--tao-khung --force`).
Mỗi tập vẽ thêm tiêu đề / số / ảnh mèo / hashtag lên bản sao (ve_lop_tap) rồi một lệnh
ffmpeg: video gốc scale vào dải + đè lớp PNG + audio (build_video_doc_khung).

Cách dùng:
    python video_doc_khung.py --tao-khung [--force]     # tạo/tạo lại bộ khung tĩnh
    python video_doc_khung.py --xem-truoc [THƯ_MỤC]     # ảnh xem trước 3 màu
    python video_doc_khung.py --tap "kịch_bản/K104 - …"  # dựng facebook.mp4 cho 1 tập
"""

from __future__ import annotations

import json
import random
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps

for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream is not None:
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

_SCRIPTS_DIR = Path(__file__).resolve().parent
BASE_DIR = _SCRIPTS_DIR.parent                       # myvoice/
for _p in (_SCRIPTS_DIR, BASE_DIR / "YOUTUBE"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from video_khung import (get_duration, get_resolution, has_nvenc,   # noqa: E402
                         run_ffmpeg_progress)

BG_DIR = BASE_DIR / "Backbround"
KHUNGDOC_DIR = BG_DIR / "khungdoc"                   # bộ khung dọc tạo sẵn
THUMB_DIR = BASE_DIR / "YOUTUBE" / "thumbnail"
FONTS_DIR = BASE_DIR / "fonts"
ANH_DIR = BASE_DIR / "Anh"
SCRIPT_DIR = BASE_DIR / "kịch_bản"

W, H = 1080, 1920
# Dải video: tỉ lệ đúng vùng đặt video của khung1 (1248×861 sau nới OVERSCAN, đo
# 08/09/2026) → rộng 1080 thì cao 745 → lấy 746 (chẵn), đặt giữa.
BAND = (0, 587, 1080, 1333)
VIEN_DE = 14                 # khung màu đè lên mép video bấy nhiêu px (che đường ghép)
# Vùng trong khung1 trên canvas 1920×1080 (video_khung.detect_inner_box, các màu cùng
# hình) — dùng khi phải CẮT YOUTUBE.mp4 cũ thay cho video gốc.
INNER_MACDINH = (346, 120, 1228, 841)
VIEN_CHAM = 72               # đường viền chấm của khung1 nằm sâu bấy nhiêu px trong vùng trong
GOC_NAME = "YOUTUBE_goc.mp4"                         # video gốc trước khi lồng khung
LOP_TAP_NAME = "khungdoc_tap.png"                    # lớp phủ đã vẽ cho tập (tạm)
# Phụ đề dọc nằm TRONG dải video: đáy chữ cách đáy khung 1920-(1333-36)=623 px ≈ 32,4%
# (kieusub.vitri_margin nhận % chiều cao từ đáy).
SUB_VITRI = "32.4"

# tên màu → (khung anhdoc, logo, nền hoa) — đều trong YOUTUBE/thumbnail
MAU = {
    "tím":  ("anhdoc tím.png",  "logo tím.png",  "khung nen 1.png"),
    "xanh": ("anhdoc xanh.png", "logo xanh.png", "khung nen 3.png"),
    "đỏ":   ("anhdoc đỏ.png",   "logo đỏ.png",   "khung nen 4.png"),
}
# Bố cục khối trên / dưới (px trên canvas 1080×1920)
LOGO_POS, LOGO_H = (64, 72), 210
BADGE_W, BADGE_POS = 250, (1080 - 64 - 250, 62)
PAPER = (56, 300, 1024, 556)                         # tờ giấy tiêu đề
PAPER_PAD = (44, 30, 44, 30)                         # lề trong giấy (trái, trên, phải, dưới)
CAT_BOX = (64, 1395, 364, 1775)                      # khung ảnh mèo (viền 12 px)
CAT_VIEN = 12
CTA = (420, 1415, 1016, 1815)                        # thẻ "Nghe trọn tập…"
SUBSCRIBE_CROP = (14, 683, 306, 777)                 # nút Đăng ký trong Backbround/khung2.png
NEN_CAM = (253, 246, 234)                            # màu giấy
CHU_TOI = (74, 28, 46)                               # chữ tối trên thẻ trắng
TIEU_DE_MAU = (123, 26, 43)                          # màu tiêu đề (như thumbnail)

USE_GPU = True
NVENC_CQ = 18
X264_CRF = 18
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


# ── tiện ích ──────────────────────────────────────────────────────────────────
def _th():
    """Module vẽ thumbnail (font tiêu đề, ngắt dòng cân đối, logo, thẻ số, nền hoa)."""
    import dien_tieu_de_thumbnail as th
    return th


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    p = FONTS_DIR / name
    if not p.exists():
        raise FileNotFoundError(f"Thiếu font {p}")
    return ImageFont.truetype(str(p), size=size)


def _bbox_alpha(im: Image.Image):
    return im.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()


def _lo_trong(im: Image.Image) -> tuple[int, int, int, int]:
    """Lỗ trong (alpha = 0) của một khung viền: quét hàng/cột giữa → (x0, x1, y0, y1)."""
    a = im.getchannel("A")
    w, h = im.size

    def khoang(seq):
        best, s = (0, 0, 0), None
        for i, v in enumerate(list(seq) + [255]):
            if v == 0 and s is None:
                s = i
            if v != 0 and s is not None:
                if i - s > best[0]:
                    best = (i - s, s, i)
                s = None
        return best

    gx = khoang(a.getpixel((x, h // 2)) for x in range(w))
    gy = khoang(a.getpixel((w // 2, y)) for y in range(h))
    return gx[1], gx[2], gy[1], gy[2]


def _dan(base: Image.Image, layer: Image.Image, pos: tuple[int, int]) -> None:
    """Dán layer RGBA lên base tại pos, cắt phần lòi ra ngoài canvas (pos có thể âm)."""
    x, y = pos
    lx0, ly0 = max(0, -x), max(0, -y)
    lx1 = min(layer.width, base.width - x)
    ly1 = min(layer.height, base.height - y)
    if lx1 <= lx0 or ly1 <= ly0:
        return
    base.alpha_composite(layer.crop((lx0, ly0, lx1, ly1)), dest=(x + lx0, y + ly0))


def _bo_goc(im: Image.Image, r: int) -> Image.Image:
    """Bo góc ảnh RGBA bán kính r (nhân vào alpha)."""
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, im.width - 1, im.height - 1), r, fill=255)
    im = im.copy()
    im.putalpha(ImageChops.multiply(im.getchannel("A"), mask))
    return im


def _bong(base: Image.Image, box, r: int, mo: int = 22, do_dam: int = 70) -> None:
    """Bóng mờ dưới một khối bo góc (giống box-shadow của bản thiết kế)."""
    from PIL import ImageFilter
    x0, y0, x1, y1 = box
    pad = mo * 2
    sh = Image.new("RGBA", (x1 - x0 + pad * 2, y1 - y0 + pad * 2), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((pad, pad + 10, pad + x1 - x0, pad + y1 - y0 + 10),
                                         r, fill=(80, 30, 50, do_dam))
    sh = sh.filter(ImageFilter.GaussianBlur(mo))
    _dan(base, sh, (x0 - pad, y0 - pad))


def accent_cua(mau: str) -> tuple[int, int, int]:
    """Màu chủ đạo của logo cùng màu (nhuộm thẻ số, viền, chữ nhấn)."""
    return tuple(_th().logo_accent_colour(THUMB_DIR / MAU[mau][1]))


# ── 1) BỘ KHUNG TĨNH tạo sẵn ──────────────────────────────────────────────────
def duong_khung(mau: str) -> Path:
    return KHUNGDOC_DIR / f"khungdoc {mau}.png"


def _ve_giay(base: Image.Image, box, accent) -> None:
    """Tờ giấy kem có dòng kẻ, viền chấm màu nhấn, băng dính trên (tiêu đề vẽ sau)."""
    x0, y0, x1, y1 = box
    _bong(base, box, 18)
    giay = Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, 0))
    d = ImageDraw.Draw(giay)
    d.rounded_rectangle((0, 0, giay.width - 1, giay.height - 1), 18, fill=(*NEN_CAM, 255))
    for y in range(PAPER_PAD[1] + 74, giay.height - PAPER_PAD[3], 74):   # dòng kẻ
        d.line((PAPER_PAD[0], y, giay.width - PAPER_PAD[2], y), fill=(120, 90, 100, 40), width=3)
    # viền chấm màu nhấn
    d.rounded_rectangle((12, 12, giay.width - 13, giay.height - 13), 12,
                        outline=(*accent, 140), width=5)
    base.alpha_composite(giay, dest=(x0, y0))
    tape = Image.new("RGBA", (220, 50), (255, 255, 255, 140))
    ImageDraw.Draw(tape).rectangle((0, 0, 219, 49), outline=(255, 255, 255, 210), width=2)
    tape = tape.rotate(3, expand=True, resample=Image.BICUBIC)
    _dan(base, tape, ((x0 + x1) // 2 - tape.width // 2, y0 - 22))


def _ve_the_cta(base: Image.Image, box, accent) -> dict:
    """Thẻ trắng "Nghe trọn tập tại kênh / Mimi audio" + nút Đăng ký. Trả về chỗ vẽ hashtag."""
    x0, y0, x1, y1 = box
    _bong(base, box, 30)
    the = Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, 0))
    d = ImageDraw.Draw(the)
    d.rounded_rectangle((0, 0, the.width - 1, the.height - 1), 30, fill=(255, 255, 255, 236))
    # đuôi bong bóng chỉ sang ảnh mèo
    d.polygon([(0, 70), (-1, 70), (0, 102)], fill=(255, 255, 255, 236))
    cx = the.width // 2
    # Dòng 1: "Nghe trọn tập tại kênh" — font Coiny bầu bĩnh, "trọn tập" màu nhấn
    f1 = _font("Coiny-Regular.ttf", 46)
    parts = [("Nghe ", CHU_TOI), ("trọn tập", accent), (" tại kênh", CHU_TOI)]
    tw = sum(d.textlength(t, font=f1) for t, _ in parts)
    x = cx - tw / 2
    for t, mau in parts:
        d.text((x, 38), t, font=f1, fill=(*mau, 255))
        x += d.textlength(t, font=f1)
    # Dòng 2: "Mimi audio" to, màu nhấn viền trắng (cute)
    f2 = _font("Coiny-Regular.ttf", 64)
    d.text((cx, 128), "Mimi audio", font=f2, fill=(*accent, 255), anchor="mt",
           stroke_width=5, stroke_fill=(255, 255, 255, 255))
    # nút Đăng ký cắt từ khung2 của bản ngang
    k2 = BG_DIR / "khung2.png"
    sub_y = 218
    if k2.exists():
        nut = Image.open(k2).convert("RGBA").crop(SUBSCRIBE_CROP)
        nut = nut.resize((round(nut.width * 96 / nut.height), 96), Image.LANCZOS)
        the.alpha_composite(nut, dest=(cx - nut.width // 2, sub_y))
    # bóng nhẹ dưới nút để nổi trên thẻ trắng: bỏ qua cho gọn
    base.alpha_composite(the, dest=(x0, y0))
    # tam giác đuôi chỉ sang trái (vẽ thẳng lên base cho khỏi bị cắt)
    ImageDraw.Draw(base).polygon([(x0 - 24, y0 + 86), (x0 + 2, y0 + 70), (x0 + 2, y0 + 102)],
                                 fill=(255, 255, 255, 236))
    return {"tag": (x0 + cx, y0 + 344)}                # tâm dòng hashtag


def _ve_khung_tinh(mau: str) -> tuple[Image.Image, dict]:
    """Ghép lớp tĩnh của một màu → (ảnh RGBA 1080×1920 có lỗ ở dải video, toạ độ)."""
    th = _th()
    anhdoc, logo_name, nen = MAU[mau]
    accent = accent_cua(mau)
    base = th.vertical_background(THUMB_DIR / nen).convert("RGBA")
    if base.size != (W, H):
        base = ImageOps.fit(base, (W, H), method=Image.LANCZOS)
    # làm dịu hai đầu (chữ nổi hơn) — như lớp .bg-dim của bản thiết kế
    dim = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dd = ImageDraw.Draw(dim)
    for y in range(H):
        t = y / H
        a = 26 * (1 - t / 0.30) if t < 0.30 else (46 * (t - 0.70) / 0.30 if t > 0.70 else 0)
        if a > 0:
            dd.line((0, y, W, y), fill=(40, 10, 30, int(a)))
    base.alpha_composite(dim)
    # lỗ video
    lo = Image.new("L", (W, H), 255)
    ImageDraw.Draw(lo).rectangle((BAND[0], BAND[1], BAND[2] - 1, BAND[3] - 1), fill=0)
    base.putalpha(ImageChops.multiply(base.getchannel("A"), lo))
    # khung màu (anhdoc) xoay ngang, kéo cho lỗ trong ôm đúng dải video (+VIEN_DE mỗi cạnh)
    fr = Image.open(THUMB_DIR / anhdoc).convert("RGBA")
    fr = fr.crop(_bbox_alpha(fr)).transpose(Image.ROTATE_270)
    ox0, ox1, oy0, oy1 = _lo_trong(fr)
    bw, bh = BAND[2] - BAND[0], BAND[3] - BAND[1]
    sx = (bw + 2 * VIEN_DE) / (ox1 - ox0)
    sy = (bh + 2 * VIEN_DE) / (oy1 - oy0)
    fr = fr.resize((round(fr.width * sx), round(fr.height * sy)), Image.LANCZOS)
    _dan(base, fr, (round(BAND[0] - VIEN_DE - ox0 * sx), round(BAND[1] - VIEN_DE - oy0 * sy)))
    # logo cùng màu
    logo = th.load_logo_cropped(THUMB_DIR / logo_name)
    logo = logo.resize((round(logo.width * LOGO_H / logo.height), LOGO_H), Image.LANCZOS)
    th.paste_with_shadow(base, logo, LOGO_POS)
    # tờ giấy tiêu đề (chữ vẽ theo tập)
    _ve_giay(base, PAPER, accent)
    # khung ảnh mèo (ảnh dán theo tập)
    _bong(base, CAT_BOX, 22)
    ImageDraw.Draw(base).rounded_rectangle(CAT_BOX, 22, fill=(255, 255, 255, 255),
                                           outline=(*accent, 255), width=CAT_VIEN)
    toa_do = _ve_the_cta(base, CTA, accent)
    toa_do.update({
        "band": list(BAND), "paper": list(PAPER), "paper_pad": list(PAPER_PAD),
        "badge": [BADGE_POS[0], BADGE_POS[1], BADGE_W],
        "cat": [CAT_BOX[0] + CAT_VIEN, CAT_BOX[1] + CAT_VIEN, CAT_BOX[2] - CAT_VIEN, CAT_BOX[3] - CAT_VIEN],
        "accent": list(accent), "sub_vitri": SUB_VITRI,
    })
    return base, toa_do


def tao_khung_san(force: bool = False, log=print) -> dict:
    """Tạo bộ khung tĩnh 3 màu vào Backbround/khungdoc/ (bỏ qua màu đã có, trừ khi force).
    Trả về dict toạ độ (cũng ghi ra khungdoc.json)."""
    KHUNGDOC_DIR.mkdir(parents=True, exist_ok=True)
    meta_path = KHUNGDOC_DIR / "khungdoc.json"
    meta = {}
    if meta_path.exists() and not force:
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    for mau in MAU:
        p = duong_khung(mau)
        if p.exists() and not force and mau in meta:
            continue
        log(f"🖼 Tạo khung dọc màu {mau} → {p.name}")
        im, toa_do = _ve_khung_tinh(mau)
        im.save(p, optimize=True)
        meta[mau] = toa_do
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return meta


def doc_meta(mau: str, log=print) -> dict:
    """Toạ độ của khung màu `mau`; thiếu khung/json thì tự tạo (lần chạy đầu)."""
    meta_path = KHUNGDOC_DIR / "khungdoc.json"
    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    if mau not in meta or not duong_khung(mau).exists():
        meta = tao_khung_san(log=log)
    return meta[mau]


# ── 2) LỚP THEO TẬP: tiêu đề, số, ảnh mèo, hashtag ────────────────────────────
def _ve_tieu_de(base: Image.Image, box, title: str) -> None:
    """Tiêu đề trên giấy: font serif đậm của thumbnail, ngắt dòng cân đối, co cỡ cho vừa."""
    th = _th()
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    d = ImageDraw.Draw(base)
    chon = None
    for size in range(76, 36, -2):
        font = th.find_font(size)
        for max_lines in (2, 3):
            lines = th.balanced_wrap(d, title, font, bw, max_lines)
            if not lines:
                continue
            lh = round(size * 1.18)
            if lh * len(lines) <= bh and all(d.textlength(l, font=font) <= bw for l in lines):
                chon = (font, lines, lh)
                break
        if chon:
            break
    if not chon:                       # tiêu đề quá dài → cắt bớt từ cuối
        font = th.find_font(40)
        words = title.split()
        while words and d.textlength(" ".join(words), font=font) > bw * 2.8:
            words.pop()
        lines = th.balanced_wrap(d, " ".join(words) + "…", font, bw, 3) or [" ".join(words)]
        chon = (font, lines, 47)
    font, lines, lh = chon
    y = y0 + (bh - lh * len(lines)) // 2
    for line in lines:
        d.text((x0 + bw / 2, y + lh / 2), line, font=font, anchor="mm",
               fill=(*TIEU_DE_MAU, 255), stroke_width=1, stroke_fill=(*TIEU_DE_MAU, 255))
        y += lh


def chon_anh_meo(folder: Path | None = None) -> Path | None:
    """Ảnh mèo cho khối dưới: ưu tiên ảnh đã dùng cho thumbnail dọc nếu ghi lại được,
    không thì random trong kho Anh/ (ảnh cao hơn rộng ưu tiên vì khung đứng)."""
    try:
        files = _th().list_photo_files(ANH_DIR)
    except Exception:
        files = sorted(p for p in ANH_DIR.glob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"))
    if not files:
        return None
    dung = [p for p in files if p.suffix.lower() != ".png"]     # bỏ ảnh 2000×2000 nặng
    return random.choice(dung or files)


def ve_lop_tap(mau: str, episode: str, title: str, out_png: Path,
               photo: Path | None = None, log=print) -> Path:
    """Vẽ lớp phủ cho MỘT tập: khung tĩnh + tiêu đề + thẻ số + ảnh mèo + hashtag → out_png."""
    th = _th()
    meta = doc_meta(mau, log=log)
    base = Image.open(duong_khung(mau)).convert("RGBA")
    accent = tuple(meta["accent"])
    # thẻ số đầu mèo (sprite của thumbnail dọc: nhuộm màu + "SỐ" + số tập)
    so = str(int(re.sub(r"\D", "", str(episode)) or 0)) if re.sub(r"\D", "", str(episode)) else str(episode)
    th_badge_w = th.V_BADGE_WIDTH
    try:
        th.V_BADGE_WIDTH = meta["badge"][2]
        badge = th._vertical_badge_sprite(so, accent)
    finally:
        th.V_BADGE_WIDTH = th_badge_w
    th.paste_with_shadow(base, badge, (meta["badge"][0], meta["badge"][1]))
    # tiêu đề
    px0, py0, px1, py1 = meta["paper"]
    pl, pt, pr, pb = meta["paper_pad"]
    _ve_tieu_de(base, (px0 + pl, py0 + pt, px1 - pr, py1 - pb), (title or "").strip() or f"Mimi audio Số {so}")
    # ảnh mèo
    photo = Path(photo) if photo else chon_anh_meo()
    if photo and photo.exists():
        cx0, cy0, cx1, cy1 = meta["cat"]
        anh = ImageOps.fit(Image.open(photo).convert("RGBA"), (cx1 - cx0, cy1 - cy0),
                           method=Image.LANCZOS)
        base.alpha_composite(_bo_goc(anh, 12), dest=(cx0, cy0))
    # hashtag
    tx, ty = meta["tag"]
    ImageDraw.Draw(base).text((tx, ty), f"#MimiAudioSo{so}", font=_font("Baloo2-ExtraBold.ttf", 34),
                              fill=(*accent, 255), anchor="mm")
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    base.save(out_png)
    return out_png


# ── 3) THÔNG TIN TẬP + NGUỒN VIDEO GỐC ────────────────────────────────────────
def thong_tin_tap(folder: Path, caption: str | None = None) -> dict:
    """{'episode', 'title'} của thư mục tập: số từ tên thư mục ("K104 - …") hoặc chữ TikTok
    'Mimi audio Số 104'; tiêu đề từ youtube_seo.txt (dòng sau "TIÊU ĐỀ YOUTUBE", bỏ
    "Mimi audio Số N |"), không có thì lấy phần sau " - " của tên thư mục."""
    folder = Path(folder)
    ep = ""
    m = re.match(r"^[A-Z]*\s*(\d+)", folder.name)
    if m:
        ep = m.group(1)
    elif caption:
        m = re.search(r"(\d+)", caption)
        ep = m.group(1) if m else ""
    title = ""
    seo = folder / "youtube_seo.txt"
    if seo.exists():
        try:
            lines = seo.read_text(encoding="utf-8").splitlines()
            for i, l in enumerate(lines):
                if "TIÊU ĐỀ YOUTUBE" in l.upper():
                    for l2 in lines[i + 1:]:
                        if l2.strip():
                            title = l2.strip()
                            break
                    break
        except Exception:
            title = ""
    if not title and " - " in folder.name:
        title = folder.name.split(" - ", 1)[1]
    if not ep:                                   # thư mục không có số → lấy "Số N" trong tiêu đề SEO
        m = re.search(r"Số\s*(\d+)", title, re.IGNORECASE)
        ep = m.group(1) if m else ""
    # "Mimi audio Số 104 | Màn Lật Kèo…" → phần không chứa "Mimi audio"
    if "|" in title:
        parts = [p.strip() for p in title.split("|")]
        khac = [p for p in parts if "mimi audio" not in p.lower()]
        title = max(khac or parts, key=len)
    return {"episode": ep, "title": title}


def _doc_goc_json(folder: Path) -> dict:
    p = Path(folder) / (Path(GOC_NAME).stem + ".json")
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except Exception:
        return {}


def chon_mau(folder: Path | None = None) -> str:
    """Màu khung dọc: cùng màu viền khung1 của bản ngang (ghi ở YOUTUBE_goc.json), không rõ
    (khung1.png hồng, tập cũ) thì random."""
    if folder:
        khung = (_doc_goc_json(folder).get("frame") or "").lower()
        for mau in MAU:
            if mau in khung:
                return mau
    return random.choice(list(MAU))


def nguon_goc(folder: Path, ngang: Path | None = None):
    """(video_nguồn, crop hoặc None, phụ_đề_đã_trong_hình). Ưu tiên YOUTUBE_goc.mp4; không có
    thì cắt vùng trong khung1 của YOUTUBE.mp4 (tập cũ)."""
    folder = Path(folder)
    goc = folder / GOC_NAME
    if goc.exists() and goc.stat().st_size > 4096:
        return goc, None, False
    cands = [Path(ngang)] if ngang else []
    cands += [folder / "YOUTUBE.mp4"] + sorted(folder.glob("*_videodone.mp4"))
    for v in cands:
        if v and v.exists() and v.stat().st_size > 4096:
            vw, vh = get_resolution(v)
            box = _doc_goc_json(folder).get("inner") or list(INNER_MACDINH)
            # Lùi vào VIEN_CHAM: đường viền CHẤM của khung1 nằm sâu ~70 px trong vùng
            # trong (đo 08/09/2026), cắt sát vùng trong là lộ đường chấm trong bản dọc.
            bx, by = box[0] + VIEN_CHAM, box[1] + VIEN_CHAM
            bw, bh = box[2] - 2 * VIEN_CHAM, box[3] - 2 * VIEN_CHAM
            kx, ky = vw / 1920, vh / 1080
            crop = (round(bw * kx) // 2 * 2, round(bh * ky) // 2 * 2,
                    round(bx * kx), round(by * ky))                  # w, h, x, y
            co_sub = (v.with_suffix(".ass").exists() or v.with_suffix(".srt").exists())
            return v, crop, co_sub
    return None, None, False


# ── 4) DỰNG VIDEO ─────────────────────────────────────────────────────────────
def build_video_doc_khung(audio_file: Path, source_video: Path, output: Path,
                          overlay_png: Path, *, crop=None, cover_png: Path | None = None,
                          log=print, progress=None, skip_existing: bool = False) -> Path:
    """Video gốc → scale phủ kín dải BAND → đè lớp PNG (khung + trên + dưới) → ghép audio.
    crop = (w, h, x, y) cắt trước khi scale (khi nguồn là YOUTUBE.mp4 đã lồng khung).
    cover_png = thumbnail dọc đè lên frame đầu (ảnh bìa Facebook/TikTok) — như video_doc."""
    audio_file, source_video, output = Path(audio_file), Path(source_video), Path(output)
    overlay_png = Path(overlay_png)
    if skip_existing and output.exists() and output.stat().st_size > 0:
        log(f"♻ Video dọc đã có → bỏ qua dựng lại: {output.name}")
        return output
    for p, ten in ((audio_file, "audio"), (source_video, "video gốc"), (overlay_png, "lớp khung")):
        if not p.exists():
            raise RuntimeError(f"Không tìm thấy {ten}: {p}")
    cover_png = Path(cover_png) if cover_png else None
    if cover_png and not cover_png.exists():
        log(f"[Cảnh báo] Không tìm thấy ảnh bìa, bỏ qua: {cover_png}")
        cover_png = None
    audio_dur = get_duration(audio_file)
    bw, bh = BAND[2] - BAND[0], BAND[3] - BAND[1]

    log(f"Khung dọc  : {W}x{H} — video gốc trong dải {bw}x{bh} tại y={BAND[1]} (khung dọc tạo sẵn)")
    log(f"Video nguồn: {source_video.name}" + (f" (cắt vùng trong khung {crop[0]}x{crop[1]})" if crop else " (video gốc trước khi lồng khung)"))
    log(f"Lớp khung  : {overlay_png.name}")
    log(f"Audio      : {audio_file.name}  ({audio_dur:.2f}s)")
    if cover_png:
        log(f"Ảnh bìa    : {cover_png.name} (đè frame đầu)")
    log(f"Đầu ra     : {output}")

    src = "[0:v]" + (f"crop={crop[0]}:{crop[1]}:{crop[2]}:{crop[3]}," if crop else "")
    filt = (
        f"{src}scale={bw}:{bh}:force_original_aspect_ratio=increase,crop={bw}:{bh},setsar=1[v];"
        f"color=c=0xf3d9e2:s={W}x{H}:r=25[bg];"
        f"[bg][v]overlay={BAND[0]}:{BAND[1]}:shortest=1[b1];"
        f"[b1][1:v]overlay=0:0" + ("[b2];" if cover_png else "[out]")
    )
    if cover_png:
        filt += (f"[3:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1[cov];"
                 f"[b2][cov]overlay=0:0:enable='lt(n\\,1)'[out]")

    def build_cmd(gpu):
        codec = (["-c:v", "h264_nvenc", "-preset", "p5", "-tune", "hq", "-rc", "vbr",
                  "-cq", str(NVENC_CQ), "-b:v", "0", "-profile:v", "high"] if gpu
                 else ["-c:v", "libx264", "-preset", "slow", "-crf", str(X264_CRF), "-profile:v", "high"])
        cmd = ["ffmpeg", "-y",
               "-stream_loop", "-1", "-i", str(source_video),      # 0: video gốc (lặp nếu ngắn)
               "-loop", "1", "-i", str(overlay_png),               # 1: lớp khung
               "-i", str(audio_file)]                              # 2: audio
        if cover_png:
            cmd += ["-loop", "1", "-i", str(cover_png)]            # 3: ảnh bìa
        cmd += ["-filter_complex", filt, "-map", "[out]", "-map", "2:a",
                "-t", f"{audio_dur:.6f}", *codec, "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", str(output)]
        return cmd

    use_gpu = USE_GPU and has_nvenc()
    log("Đang dựng video dọc từ video gốc... (GPU - h264_nvenc)" if use_gpu
        else "Đang dựng video dọc từ video gốc... (CPU - libx264)")
    rc, err_tail = run_ffmpeg_progress(build_cmd(use_gpu), audio_dur, log,
                                       label="Dựng video dọc (khung)", progress=progress)
    if rc != 0 and use_gpu:
        log("GPU lỗi, chuyển sang CPU (libx264)...")
        rc, err_tail = run_ffmpeg_progress(build_cmd(False), audio_dur, log,
                                           label="Dựng video dọc (khung)", progress=progress)
    if rc != 0:
        raise RuntimeError(f"ffmpeg lỗi:\n{err_tail}")
    final_dur = get_duration(output)
    size_mb = output.stat().st_size / 1024 / 1024
    log(f"Hoàn tất! Thời lượng {final_dur:.2f}s — {size_mb:.1f} MB — {output}")
    return output


def dung_cho_tap(folder: Path, audio: Path | None = None, output: Path | None = None, *,
                 mau: str | None = None, cover_png: Path | None = None, caption: str | None = None,
                 log=print, progress=None, skip_existing: bool = False) -> tuple[Path, bool]:
    """Trọn gói cho 1 thư mục tập: chọn nguồn gốc → vẽ lớp theo tập → dựng.
    caption = chữ TikTok 'Mimi audio Số N' (nguồn số tập dự phòng khi tên thư mục không có số).
    Trả về (facebook.mp4, phụ_đề_đã_có_trong_hình)."""
    folder = Path(folder)
    audio = Path(audio) if audio else folder / "output.wav"
    output = Path(output) if output else folder / "facebook.mp4"
    src, crop, co_sub = nguon_goc(folder)
    if src is None:
        raise RuntimeError("chưa có video ngang / video gốc trong thư mục tập để dựng bản dọc")
    mau = mau or chon_mau(folder)
    info = thong_tin_tap(folder, caption)
    lop = ve_lop_tap(mau, info["episode"], info["title"], folder / LOP_TAP_NAME, log=log)
    log(f"🖼 Lớp khung dọc: màu {mau}, tập {info['episode']}, tiêu đề: {info['title'][:60]}")
    out = build_video_doc_khung(audio, src, output, lop, crop=crop, cover_png=cover_png,
                                log=log, progress=progress, skip_existing=skip_existing)
    return out, co_sub


# ── 5) ẢNH XEM TRƯỚC cho web ──────────────────────────────────────────────────
def _khung_hinh_mau(tmp_dir: Path) -> Image.Image | None:
    """Một khung hình video gốc để xem trước: lấy từ tập gần nhất có video."""
    try:
        import amain_taogiong_gui as gui
        folders = sorted(gui.episode_dirs(), key=lambda p: p.stat().st_mtime, reverse=True)
    except Exception:
        folders = sorted((p for p in SCRIPT_DIR.iterdir() if p.is_dir()),
                         key=lambda p: p.stat().st_mtime, reverse=True) if SCRIPT_DIR.exists() else []
    for f in folders:
        src, crop, _ = nguon_goc(f)
        if src is None:
            continue
        out = tmp_dir / "khungdoc_mau_frame.jpg"
        vf = (f"crop={crop[0]}:{crop[1]}:{crop[2]}:{crop[3]}" if crop else "null")
        try:
            dur = get_duration(src)
            r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{max(1.0, dur * 0.2):.2f}",
                                "-i", str(src), "-frames:v", "1", "-vf", vf, str(out)],
                               capture_output=True, creationflags=CREATE_NO_WINDOW, timeout=60)
            if r.returncode == 0 and out.exists():
                return Image.open(out).convert("RGBA")
        except Exception:
            continue
    return None


def xem_truoc(mau: str, out_path: Path, force: bool = False, log=print) -> Path:
    """Ảnh JPEG 540×960 xem trước khung dọc màu `mau` với tiêu đề/số/ảnh mẫu + một khung
    hình video gốc thật (không có thì nền màu). Có sẵn và khung chưa đổi thì trả ngay."""
    out_path = Path(out_path)
    khung = duong_khung(mau)
    if out_path.exists() and not force and khung.exists() \
            and out_path.stat().st_mtime >= khung.stat().st_mtime:
        return out_path
    tmp = Path(tempfile.gettempdir())
    lop = ve_lop_tap(mau, "104", "Màn Lật Kèo Đầy Nghẹt Thở Của Nữ Tướng Quân Phản Diện",
                     tmp / f"khungdoc_xemtruoc_{mau}.png", log=log)
    base = Image.new("RGBA", (W, H), (243, 217, 226, 255))
    bw, bh = BAND[2] - BAND[0], BAND[3] - BAND[1]
    frame = _khung_hinh_mau(tmp)
    if frame is not None:
        base.alpha_composite(ImageOps.fit(frame, (bw, bh), method=Image.LANCZOS), dest=(BAND[0], BAND[1]))
    else:
        d = ImageDraw.Draw(base)
        d.rectangle(BAND, fill=(120, 80, 110, 255))
        d.text(((BAND[0] + BAND[2]) // 2, (BAND[1] + BAND[3]) // 2), "video gốc của bản ngang",
               font=_font("Baloo2-ExtraBold.ttf", 48), fill=(255, 255, 255, 255), anchor="mm")
    base.alpha_composite(Image.open(lop).convert("RGBA"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    base.convert("RGB").resize((540, 960), Image.LANCZOS).save(out_path, "JPEG", quality=86)
    return out_path


# ── CLI ───────────────────────────────────────────────────────────────────────
def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Video dọc từ video gốc của bản ngang + khung dọc tạo sẵn.")
    ap.add_argument("--tao-khung", action="store_true", help="Tạo bộ khung tĩnh 3 màu vào Backbround/khungdoc/.")
    ap.add_argument("--force", action="store_true", help="Tạo lại cả khung đã có.")
    ap.add_argument("--xem-truoc", nargs="?", const=str(KHUNGDOC_DIR / "xemtruoc"), default=None,
                    metavar="THƯ_MỤC", help="Xuất ảnh xem trước 3 màu (mặc định Backbround/khungdoc/xemtruoc).")
    ap.add_argument("--tap", metavar="THƯ_MỤC", help="Dựng facebook.mp4 cho một thư mục tập.")
    ap.add_argument("--mau", choices=list(MAU), help="Ép màu khung (mặc định theo khung ngang / random).")
    args = ap.parse_args(argv)
    if args.tao_khung:
        tao_khung_san(force=args.force)
        print(f"✅ Bộ khung ở {KHUNGDOC_DIR}")
    if args.xem_truoc:
        d = Path(args.xem_truoc)
        for mau in MAU:
            print("→", xem_truoc(mau, d / f"xemtruoc {mau}.jpg", force=True))
    if args.tap:
        out, co_sub = dung_cho_tap(Path(args.tap), mau=args.mau)
        print("✅", out, "(phụ đề đã có trong hình)" if co_sub else "")
    if not (args.tao_khung or args.xem_truoc or args.tap):
        ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
