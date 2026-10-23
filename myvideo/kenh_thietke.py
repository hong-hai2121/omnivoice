# -*- coding: utf-8 -*-
"""kenh_thietke.py — Bộ nhận diện kênh cho một HỒ SƠ KÊNH của myvideo.

Hai việc, ra file PNG nền trong suốt trong myvideo/kenh/<tên>/ (đúng tên mà
bước ④ video_gansub_cung.py tìm):

  1) NHẬP LOGO/MASCOT có sẵn (--mascot FILE[=tên] …): cắt sát phần có hình (bỏ
     lề trong suốt thừa để cỡ "rộng 12%% khung" tính đúng), chừa lề 2%%, lưu
     "logo <tên>.png". Hồ sơ chứa NHIỀU logo*.png thì chọn trên web (khoá
     logo_file) — 22/10/2026 haivietsub có hai mascot "cá mập xanh" và "hải cẩu tím"
     do người dùng vẽ ngoài, thay cho wordmark tự vẽ.
  2) VẼ KHUNG VIỀN: khung.png 16:9 (1920×1080) đè lên video gốc cần dịch và
     khung_doc.png 9:16 (1080×1920) cho bản dọc — bước ④ tự lấy khi --khung doc.
     Khung = dải viền bo góc tô chuyển sắc nhẹ + vạch sáng mép trong + chùm
     BONG BÓNG ở hai góc chéo (trái trên · phải dưới — chừa góc phải trên cho
     logo), vẽ theo BẢNG MÀU (--mau) khớp mascot đang dùng:
        tim   (mặc định) đo từ mascot hải cẩu tím: tím than · tím · hoa cà · hồng phấn
        xanh  bản nam tính tông xanh da trời ban đầu, hợp mascot cá mập xanh
     Thêm --nhan để ngàm nhãn wordmark vào góc trái dưới (mặc định không).

Còn giữ bộ vẽ WORDMARK CÁCH ĐIỆU (--logo-chu → logo.png): font hiển thị đậm,
nghiêng (shear), mặt chữ chuyển sắc có vệt bóng nửa trên, khối 3D, viền đậm,
bóng mờ — dựng từ MỘT mask chữ nên đổi font/chữ/bảng màu là cả bộ đổi theo.
Dùng khi kênh khác chưa có logo riêng.

Vẽ bằng Pillow ở độ phân giải gấp đôi rồi thu về (SS) cho nét mịn.

Chạy:
    venv\\Scripts\\python myvideo\\kenh_thietke.py --kenh haivietsub --force
    --mau tim|xanh               bảng màu khung (mặc định tim)
    --mascot "C:\\…\\ca map.png=cá mập xanh" "C:\\…\\hai cau.png=hải cẩu tím"
                                 nhập mascot (phần sau dấu = là tên, bỏ = lấy tên file)
    --logo-chu                   vẽ thêm logo.png wordmark cách điệu
    --nhan                       khung viền có nhãn wordmark góc trái dưới
    --khong-bong-bong            khung trơn, không chùm bong bóng ở góc
    --chu1 Hai --chu2 VietSub    chữ của wordmark;  --font Anton-Regular.ttf  font
    --xem-truoc                  xuất xemtruoc.jpg (khung + logo đang dùng trên nền xám)

Font cách điệu mặc định KHÔNG có dấu tiếng Việt; chữ có dấu (HẢI…) thì tự lùi
về BeVietnamPro-Black (đủ dấu) để không ra ô vuông.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent              # myvideo/
ROOT = BASE_DIR.parent                                  # …/OmniVoice
sys.path.insert(0, str(BASE_DIR))
import kenh_hoso  # noqa: E402

FONT_DIR = ROOT / "myvoice" / "fonts"                   # kho font dùng chung của repo
FONT_CACH_DIEU = FONT_DIR / "Anton-Regular.ttf"         # chữ hiển thị đậm, nét dày, dáng nam tính
FONT_DU_PHONG = FONT_DIR / "BeVietnamPro-Black.ttf"     # đủ dấu tiếng Việt (dự phòng)
# Font đã có dáng nghiêng sẵn thì shear nhẹ thôi; font đứng thì nghiêng ~11°.
NGHIENG_THEO_FONT = {"Bangers-Regular.ttf": 0.08}
NGHIENG_MAC_DINH = 0.20

TRANG = (255, 255, 255, 255)
TRONG = (0, 0, 0, 0)

# ── BẢNG MÀU theo mascot đang dùng ───────────────────────────────────────────
# Mỗi bảng: vien_tren/vien_duoi = dải viền khung (chuyển sắc nhẹ từ trên xuống,
# cùng là màu viền chữ wordmark), vach = vạch sáng mép trong, khoi = mặt khối 3D
# wordmark, icon = bong bóng phụ đề, mat1/mat2 = chuyển sắc mặt chữ 1/2 (trên →
# dưới), bong_bong = màu chùm bong bóng ở góc khung (đậm → nhạt).
BANG_MAU = {
    # Đo từ ảnh mascot hải cẩu tím (22/10/2026): viền nét #1D0234, áo hoodie
    # #AA49D2, hải cẩu #C09BD8/#C5B6E6, bọt nước #E5C5EC, hồng phấn #F6E1E4.
    "tim": dict(
        vien_tren=(58, 20, 100, 255),     # #3A1464
        vien_duoi=(29, 2, 52, 255),       # #1D0234
        vach=(170, 73, 210, 255),         # #AA49D2
        khoi=(109, 40, 217, 255),         # #6D28D9
        icon=(170, 73, 210, 255),
        mat1=(TRANG, (229, 197, 236, 255)),                 # trắng → hoa cà
        mat2=((192, 155, 216, 255), (170, 73, 210, 255)),   # tím nhạt → tím
        bong_bong=[(178, 115, 217, 255), (197, 182, 230, 255),
                   (229, 197, 236, 255), (246, 225, 228, 255)],
    ),
    # Bản nam tính tông xanh da trời ban đầu — hợp mascot cá mập xanh.
    "xanh": dict(
        vien_tren=(14, 50, 90, 255),      # #0E325A
        vien_duoi=(8, 32, 58, 255),       # #08203A
        vach=(14, 165, 233, 255),         # #0EA5E9
        khoi=(3, 90, 140, 255),           # #035A8C
        icon=(14, 165, 233, 255),
        mat1=(TRANG, (186, 230, 253, 255)),
        mat2=((125, 211, 252, 255), (14, 165, 233, 255)),
        bong_bong=[(14, 165, 233, 255), (125, 211, 252, 255),
                   (186, 230, 253, 255), (240, 249, 255, 255)],
    ),
}
MAU_MAC_DINH = "tim"

SS = 2                           # vẽ gấp đôi rồi thu về cho mịn

# Khung viền (số đo ở cỡ THẬT, px): bề dày dải viền, bán kính bo góc trong, vạch mép trong.
VIEN_DAY = 22
VIEN_BO = 36
VIEN_VACH = 4
# Chùm bong bóng ở góc: (cách mép ngang, cách mép dọc, bán kính, số màu trong bong_bong)
# tính từ GÓC, px ở cỡ thật; nhô vào trong hình một chút như bọt nước bám mép khung.
BONG_BONG_GOC = [(34, 30, 15, 1), (62, 16, 9, 2), (22, 62, 9, 3), (50, 48, 6, 0),
                 (84, 34, 6, 2), (14, 92, 5, 1), (104, 18, 4, 3), (36, 80, 4, 0)]
# Nhãn wordmark góc trái dưới (ngàm vào dải viền dưới): cao nhãn, cao chữ trong nhãn, cách mép trái.
NHAN_CAO = 46
NHAN_CHU_CAO = 30
NHAN_LE_TRAI = 64

CHU1_MAC_DINH, CHU2_MAC_DINH = "Hai", "VietSub"


# ── Font ─────────────────────────────────────────────────────────────────────
def _co_dau(s: str) -> bool:
    return any(ord(c) > 0x24F for c in s)        # ngoài Latin mở rộng A/B = có dấu tiếng Việt


def chon_font(chu: str, font_path: Path | None = None) -> Path:
    """Font cách điệu cho chữ không dấu; chữ có dấu tiếng Việt lùi về font đủ dấu."""
    p = font_path or FONT_CACH_DIEU
    if _co_dau(chu) and p != FONT_DU_PHONG:
        return FONT_DU_PHONG
    return p


def _font(path: Path, px: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), px)


# ── Biểu tượng phụ đề: bong bóng thoại + hai dòng chữ trắng ──────────────────
def ve_icon_sub(d: ImageDraw.ImageDraw, x: float, y: float, s: float, mau: tuple) -> None:
    """Bong bóng thoại (ô bo góc + đuôi nhỏ góc trái dưới) với hai vạch trắng
    tượng trưng dòng phụ đề. Viền/khối 3D do lớp wordmark lo chung với chữ."""
    r = s * 0.22
    d.rounded_rectangle([x, y, x + s, y + s * 0.82], radius=r, fill=mau)
    d.polygon([(x + s * 0.18, y + s * 0.78), (x + s * 0.42, y + s * 0.78),
               (x + s * 0.18, y + s)], fill=mau)
    h = s * 0.11
    d.rounded_rectangle([x + s * 0.18, y + s * 0.25, x + s * 0.82, y + s * 0.25 + h],
                        radius=h / 2, fill=TRANG)
    d.rounded_rectangle([x + s * 0.18, y + s * 0.46, x + s * 0.60, y + s * 0.46 + h],
                        radius=h / 2, fill=TRANG)


# ── Các lớp của chữ cách điệu ────────────────────────────────────────────────
def _to_chuyen_sac(mask: Image.Image, tren: tuple, duoi: tuple, bong: float = 0.22) -> Image.Image:
    """Tô mặt chữ theo `mask` bằng chuyển sắc dọc tren→duoi trong đúng khoảng cao
    của chữ; nửa trên pha thêm trắng (`bong`) tạo vệt bóng gắt kiểu chrome/kẹo."""
    out = Image.new("RGBA", mask.size, TRONG)
    bb = mask.getbbox()
    if not bb:
        return out
    x0, y0, x1, y1 = bb
    h = max(1, y1 - y0)
    cot = []
    for i in range(h):
        t = i / max(1, h - 1)
        c = [round(tren[k] + (duoi[k] - tren[k]) * t) for k in range(3)]
        if t < 0.47:
            c = [round(v + (255 - v) * bong) for v in c]
        cot.append((*c, 255))
    grad = Image.new("RGBA", (1, h))
    grad.putdata(cot)
    lop = Image.new("RGBA", mask.size, TRONG)
    lop.paste(grad.resize((x1 - x0, h), Image.NEAREST), (x0, y0))
    out.paste(lop, (0, 0), mask)
    return out


def _nghieng(im: Image.Image, k: float, y_goc: float) -> Image.Image:
    """Nghiêng kiểu chữ in nghiêng: điểm trên đường `y_goc` dịch phải k·(y_goc−y).
    Thêm lề phải cho phần đỉnh trượt sang, không bị cắt."""
    W, H = im.size
    them = int(abs(k) * H) + 4
    nen = Image.new(im.mode, (W + them, H), 0 if im.mode == "L" else TRONG)
    nen.paste(im, (0, 0))
    return nen.transform(nen.size, Image.AFFINE, (1, k, -k * y_goc, 0, 1, 0),
                         resample=Image.BICUBIC)


def _gian(mask: Image.Image, r: int) -> Image.Image:
    """Nở mask ra r px (viền quanh chữ): làm mờ rồi cắt ngưỡng → nhanh hơn
    MaxFilter nhiều lần ở cỡ 2× mà mép vẫn tròn đều; làm mịn lại 1 px."""
    if r <= 0:
        return mask.copy()
    mo = mask.filter(ImageFilter.GaussianBlur(r * 0.55))
    cat = mo.point(lambda v: 255 if v >= 28 else 0)
    return cat.filter(ImageFilter.GaussianBlur(0.8))


def _khoi(mask: Image.Image, sau: int, dx: int = 1, dy: int = 1) -> Image.Image:
    """Khối 3D: chồng mask dịch (dx,dy) từng bước tới độ sâu `sau` — phần nhô
    ra dưới-phải chữ chính là mặt khối."""
    khoi = Image.new("L", mask.size, 0)
    for i in range(1, sau + 1):
        buoc = Image.new("L", mask.size, 0)
        buoc.paste(mask, (i * dx, i * dy))
        khoi = ImageChops.lighter(khoi, buoc)
    return khoi


def _lop_mau(mask: Image.Image, mau: tuple) -> Image.Image:
    lop = Image.new("RGBA", mask.size, mau)
    lop.putalpha(ImageChops.multiply(mask, Image.new("L", mask.size, mau[3])))
    return lop


def ve_wordmark(chu1: str, chu2: str, cao: int = 240, font_path: Path | None = None,
                co_icon: bool = True, mau: dict | None = None) -> Image.Image:
    """Wordmark cách điệu một dòng: [biểu tượng phụ đề] CHU1 CHU2 — nghiêng,
    mặt chữ chuyển sắc, khối 3D, viền đậm, bóng mờ, màu theo bảng `mau`.
    `cao` = cỡ chữ ở cỡ thật; canvas tự cắt sát nội dung. Trả về RGBA (cỡ thật)."""
    mau = mau or BANG_MAU[MAU_MAC_DINH]
    S = SS
    fp = chon_font(chu1 + chu2, font_path)
    f = _font(fp, cao * S)
    k = NGHIENG_THEO_FONT.get(fp.name, NGHIENG_MAC_DINH)
    cap = -f.getbbox("H", anchor="ls")[1]              # chiều cao chữ hoa
    b1, b2 = f.getbbox(chu1, anchor="ls"), f.getbbox(chu2, anchor="ls")
    w1, w2 = b1[2] - b1[0], b2[2] - b2[0]
    dinh = max(-b1[1], -b2[1])                         # tới đỉnh cao nhất (dấu/ascender)
    day = max(b1[3], b2[3], 0)                         # tới đáy descender
    icon = round(cap * 1.0) if co_icon else 0
    gap = round(cao * S * 0.16) if co_icon else 0      # icon ↔ chữ
    khoang = round(cao * S * 0.22)                     # CHU1 ↔ CHU2
    vien = max(2, round(cao * S * 0.055))              # viền đậm
    sau = max(2, round(cao * S * 0.05))                # độ sâu khối 3D
    pad = round(cao * S * 0.45)                        # lề đủ cho viền + khối + bóng

    W = pad + icon + gap + w1 + khoang + w2 + pad
    H = pad + dinh + day + pad
    y_base = pad + dinh
    # Mask từng phần (để tô chuyển sắc riêng) + lớp màu của icon.
    m1 = Image.new("L", (W, H), 0)
    m2 = Image.new("L", (W, H), 0)
    mi = Image.new("L", (W, H), 0)
    mau_icon = Image.new("RGBA", (W, H), TRONG)
    x = pad
    if co_icon:
        yi = y_base - cap / 2 - icon / 2
        ve_icon_sub(ImageDraw.Draw(mau_icon), x, yi, icon, mau["icon"])
        mi = mau_icon.getchannel("A")
        x += icon + gap
    ImageDraw.Draw(m1).text((x, y_base), chu1, font=f, fill=255, anchor="ls")
    x += w1 + khoang
    ImageDraw.Draw(m2).text((x, y_base), chu2, font=f, fill=255, anchor="ls")

    # Nghiêng mọi lớp cùng một phép (điểm trên baseline trượt phải).
    m1, m2, mi = (_nghieng(m, k, y_base) for m in (m1, m2, mi))
    mau_icon = _nghieng(mau_icon, k, y_base)
    mat = Image.alpha_composite(_to_chuyen_sac(m1, *mau["mat1"]), _to_chuyen_sac(m2, *mau["mat2"]))
    mat = Image.alpha_composite(mat, mau_icon)
    m_tat = ImageChops.lighter(ImageChops.lighter(m1, m2), mi)

    # Khối 3D dưới chữ, viền bao cả chữ lẫn khối, bóng mờ dưới cùng.
    khoi = _khoi(m_tat, sau)
    vien_m = _gian(ImageChops.lighter(m_tat, khoi), vien)
    bong = _lop_mau(vien_m.filter(ImageFilter.GaussianBlur(cao * S * 0.05)), (0, 0, 0, 120))
    out = Image.new("RGBA", m_tat.size, TRONG)
    out.alpha_composite(bong, dest=(0, round(cao * S * 0.05)))
    out.alpha_composite(_lop_mau(vien_m, mau["vien_duoi"]))
    out.alpha_composite(_lop_mau(khoi, mau["khoi"]))
    out.alpha_composite(mat)

    bb = out.getbbox()
    le = round(cao * S * 0.06)
    out = out.crop((max(0, bb[0] - le), max(0, bb[1] - le),
                    min(out.width, bb[2] + le), min(out.height, bb[3] + le)))
    return out.resize((max(1, out.width // S), max(1, out.height // S)), Image.LANCZOS)


# ── KHUNG VIỀN ───────────────────────────────────────────────────────────────
def ve_nhan(im: Image.Image, x0: int, y1: int, wordmark: Image.Image, S: int, mau: dict) -> None:
    """Nhãn góc trái dưới: viên thuốc màu viền, viền vạch sáng, ngàm vào dải viền
    dưới (đáy sát mép ngoài, thân nhô vào trong hình) chứa wordmark thu nhỏ —
    trông như một "mấu" của khung chứ không phải watermark dán thêm."""
    cao = NHAN_CAO * S
    h = NHAN_CHU_CAO * S
    w = round(wordmark.width * h / wordmark.height)
    wm = wordmark.resize((w, h), Image.LANCZOS)
    le = round(14 * S)
    W = le + w + le
    y0 = y1 - cao
    ImageDraw.Draw(im).rounded_rectangle([x0, y0, x0 + W, y1], radius=cao / 2,
                                         fill=mau["vien_duoi"], outline=mau["vach"],
                                         width=round(VIEN_VACH * S * 0.6))
    im.alpha_composite(wm, dest=(x0 + le, y0 + (cao - h) // 2))


def _bong_bong(d: ImageDraw.ImageDraw, cx: float, cy: float, r: float, mau: tuple,
               vien: tuple, S: int) -> None:
    """Một bong bóng: tròn tô màu, viền mảnh màu tối (đọc được trên cảnh sáng),
    chấm bóng trắng lệch trên-trái như bọt nước trong ảnh mascot."""
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=mau,
              outline=(vien[0], vien[1], vien[2], 150), width=max(1, round(1.2 * S)))
    gx, gy, gr = cx - r * 0.38, cy - r * 0.40, r * 0.30
    d.ellipse([gx - gr, gy - gr * 0.8, gx + gr, gy + gr * 0.8], fill=(255, 255, 255, 215))


def ve_bong_bong_goc(im: Image.Image, W: int, H: int, S: int, mau: dict) -> None:
    """Chùm bong bóng ở hai góc chéo TRÁI TRÊN và PHẢI DƯỚI (góc phải trên để
    trống cho logo kênh, góc trái dưới cho nhãn nếu bật). Bong bóng bám mép
    khung, nhô vào trong hình một chút."""
    d = ImageDraw.Draw(im)
    vien = mau["vien_duoi"]
    for dx, dy, r, i in BONG_BONG_GOC:
        c = mau["bong_bong"][i % len(mau["bong_bong"])]
        _bong_bong(d, dx * S, dy * S, r * S, c, vien, S)                          # trái trên
        _bong_bong(d, W * S - dx * S, H * S - dy * S, r * S, c, vien, S)          # phải dưới


def ve_khung(W: int, H: int, mau: dict, wordmark: Image.Image | None = None,
             bong_bong: bool = True) -> Image.Image:
    """Khung viền W×H: dải viền dày VIEN_DAY tô chuyển sắc nhẹ vien_tren→vien_duoi,
    lòng trong suốt bo góc VIEN_BO, vạch sáng VIEN_VACH sát mép trong, chùm bong
    bóng hai góc chéo; có `wordmark` thì thêm nhãn góc trái dưới."""
    S = SS
    # Dải viền chuyển sắc dọc (trên sáng hơn chút, dưới đậm) — cột 1 px kéo ngang.
    cot = Image.new("RGBA", (1, H * S))
    cot.putdata([tuple(round(mau["vien_tren"][k] + (mau["vien_duoi"][k] - mau["vien_tren"][k])
                             * i / max(1, H * S - 1)) for k in range(4))
                 for i in range(H * S)])
    im = cot.resize((W * S, H * S), Image.NEAREST)
    d = ImageDraw.Draw(im)
    v, r, vach = VIEN_DAY * S, VIEN_BO * S, VIEN_VACH * S
    # Vạch sáng: viền bo góc rộng `vach`, mép trong trùng đúng mép lòng khung.
    d.rounded_rectangle([v - vach, v - vach, W * S - 1 - (v - vach), H * S - 1 - (v - vach)],
                        radius=r + vach, outline=mau["vach"], width=vach)
    # Khoét lòng trong suốt.
    mask = Image.new("L", im.size, 255)
    ImageDraw.Draw(mask).rounded_rectangle([v, v, W * S - 1 - v, H * S - 1 - v],
                                           radius=r, fill=0)
    im.putalpha(mask)
    # Trang trí vẽ SAU khoét nên đè lên cả lòng khung lẫn vạch sáng.
    if bong_bong:
        ve_bong_bong_goc(im, W, H, S, mau)
    if wordmark is not None:
        ve_nhan(im, x0=NHAN_LE_TRAI * S, y1=H * S - round(6 * S), wordmark=wordmark, S=S, mau=mau)
    return im.resize((W, H), Image.LANCZOS)


# ── NHẬP LOGO / MASCOT CÓ SẴN ────────────────────────────────────────────────
_KY_TU_CAM = re.compile(r'[\\/:*?"<>|]+')          # ký tự Windows cấm trong tên file


def nhap_mascot(kenh: str, src: Path, ten: str = "", log=print) -> Path:
    """Đưa ảnh logo/mascot (PNG nền trong suốt) vào hồ sơ kênh thành "logo <tên>.png".

    Cắt sát phần có hình theo kênh alpha — ảnh vẽ ngoài hay chừa lề trong suốt
    rộng, để nguyên thì bước ④ scale "rộng 12%% khung" ra hình nhỏ hơn ý — rồi
    chừa lại lề 2%% cho mép không chạm. Giữ nguyên độ phân giải gốc. Tên lấy từ
    `ten` (hoặc tên file), tự thêm "logo " phía trước để kenh_hoso.logos() thấy."""
    im = Image.open(src).convert("RGBA")
    bb = im.getchannel("A").getbbox()
    if bb:
        im = im.crop(bb)
    le = round(max(im.size) * 0.02)
    nen = Image.new("RGBA", (im.width + 2 * le, im.height + 2 * le), TRONG)
    nen.alpha_composite(im, dest=(le, le))
    ten = _KY_TU_CAM.sub(" ", (ten or Path(src).stem)).strip()
    if not ten.lower().startswith("logo"):
        ten = f"logo {ten}"
    p = kenh_hoso.thu_muc(kenh) / f"{ten}.png"
    nen.save(p, optimize=True)
    log(f"🖼 {p.name}  {nen.width}×{nen.height}  (từ {Path(src).name})")
    return p


def _tach_mascot(arg: str) -> tuple[Path, str]:
    """'FILE=tên' → (FILE, tên); không có '=' hợp lệ → (FILE, '')."""
    if "=" in arg:
        duong, ten = arg.rsplit("=", 1)
        if ten and not any(c in ten for c in "\\/") and not ten.lower().endswith(".png"):
            return Path(duong), ten
    return Path(arg), ""


# ── XEM TRƯỚC ────────────────────────────────────────────────────────────────
def xem_truoc(khung: Image.Image, logo: Image.Image | None) -> Image.Image:
    """Đặt khung + logo (rộng 12%% khung, lề như bước ④) lên nền xám chuyển
    sắc để ngắm bố cục — ảnh JPG, không dùng vào video."""
    W, H = khung.size
    nen = Image.new("RGBA", (W, H))
    px = nen.load()
    for yy in range(H):
        g = 70 + int(90 * yy / H)
        for xx in range(W):
            px[xx, yy] = (g, g + 8, g + 18, 255)
    nen.alpha_composite(khung)
    if logo is not None:
        lw = max(48, round(W * 0.12 / 2) * 2)
        lg = logo.resize((lw, round(logo.height * lw / logo.width)), Image.LANCZOS)
        pad = max(12, W // 100, round(min(W, H) * 0.045))
        nen.alpha_composite(lg, dest=(W - lw - pad, pad))
    return nen.convert("RGB")


# ── CHẠY ─────────────────────────────────────────────────────────────────────
def tao_bo(kenh: str, chu1: str = CHU1_MAC_DINH, chu2: str = CHU2_MAC_DINH,
           force: bool = False, xemtruoc: bool = False, font_path: Path | None = None,
           logo_chu: bool = False, nhan: bool = False, mascots: list[str] = (),
           mau: str = MAU_MAC_DINH, bong_bong: bool = True, log=print) -> list[Path]:
    d = kenh_hoso.thu_muc(kenh)
    if not d.is_dir():
        raise FileNotFoundError(f"Chưa có hồ sơ kênh “{kenh}” ({d}) — tạo ở khối "
                                "📤 Đăng bài hoặc kenh_hoso.tao().")
    if mau not in BANG_MAU:
        raise ValueError(f"Bảng màu “{mau}” không có — chọn: {', '.join(BANG_MAU)}")
    bm = BANG_MAU[mau]
    ra = []
    for arg in mascots:
        src, ten = _tach_mascot(arg)
        if not src.is_file():
            raise FileNotFoundError(f"Không thấy ảnh mascot: {src}")
        ra.append(nhap_mascot(kenh, src, ten, log=log))

    wm = None
    if logo_chu or nhan:
        fp = chon_font(chu1 + chu2, font_path)
        if not fp.is_file():
            raise FileNotFoundError(f"Thiếu font {fp}")
        log(f"🔤 Font wordmark: {fp.name}")
        # Wordmark vẽ MỘT lần ở cỡ lớn, logo dùng nguyên, nhãn khung thu nhỏ từ đó.
        wm = ve_wordmark(chu1, chu2, cao=240, font_path=font_path, mau=bm)
    log(f"🎨 Bảng màu khung: {mau}" + ("" if bong_bong else " (không bong bóng)"))
    viec = ([("logo.png", lambda: wm)] if logo_chu else []) + [
        ("khung.png", lambda: ve_khung(1920, 1080, bm, wm if nhan else None, bong_bong)),
        ("khung_doc.png", lambda: ve_khung(1080, 1920, bm, wm if nhan else None, bong_bong))]
    for ten, ve in viec:
        p = d / ten
        if p.exists() and not force:
            log(f"⏭ {p.name} đã có — giữ nguyên (thêm --force để vẽ lại).")
            continue
        im = ve()
        im.save(p, optimize=True)
        log(f"🎨 {p.name}  {im.width}×{im.height}")
        ra.append(p)
    if xemtruoc:
        kh = Image.open(d / "khung.png").convert("RGBA")
        lp = kenh_hoso.logo_dang_dung(kenh)       # logo đang chọn trên web
        lg = Image.open(lp).convert("RGBA") if lp else None
        p = d / "xemtruoc.jpg"
        xem_truoc(kh, lg).save(p, quality=90)
        log(f"👀 {p.name}" + (f"  (logo: {lp.name})" if lp else "  (chưa có logo)"))
        ra.append(p)
    return ra


def main() -> int:
    ap = argparse.ArgumentParser(description="Nhập logo/mascot + vẽ khung viền cho một hồ sơ kênh myvideo.")
    ap.add_argument("--kenh", default="", help="tên hồ sơ trong myvideo/kenh/ "
                                                "(mặc định: hồ sơ đang chọn trên web)")
    ap.add_argument("--mau", default=MAU_MAC_DINH, choices=sorted(BANG_MAU),
                    help=f"bảng màu khung/wordmark (mặc định {MAU_MAC_DINH})")
    ap.add_argument("--mascot", nargs="+", default=[], metavar="FILE[=tên]",
                    help="ảnh logo/mascot PNG nền trong suốt đưa vào hồ sơ thành 'logo <tên>.png'")
    ap.add_argument("--logo-chu", action="store_true", help="vẽ thêm logo.png wordmark cách điệu")
    ap.add_argument("--nhan", action="store_true", help="khung viền có nhãn wordmark góc trái dưới")
    ap.add_argument("--khong-bong-bong", action="store_true", help="khung trơn, không bong bóng ở góc")
    ap.add_argument("--chu1", default=CHU1_MAC_DINH, help=f"chữ 1 wordmark (mặc định {CHU1_MAC_DINH})")
    ap.add_argument("--chu2", default=CHU2_MAC_DINH, help=f"chữ 2 wordmark (mặc định {CHU2_MAC_DINH})")
    ap.add_argument("--font", default="", help=f"file font trong {FONT_DIR} "
                                                f"(mặc định {FONT_CACH_DIEU.name})")
    ap.add_argument("--force", action="store_true", help="vẽ đè khung/logo wordmark đã có")
    ap.add_argument("--xem-truoc", action="store_true", help="xuất thêm xemtruoc.jpg")
    a = ap.parse_args()
    kenh = a.kenh or kenh_hoso.hien_tai()
    if not kenh:
        print("❌ Chưa chọn hồ sơ kênh — truyền --kenh <tên>.")
        return 2
    font_path = (FONT_DIR / a.font) if a.font else None
    try:
        tao_bo(kenh, a.chu1, a.chu2, force=a.force, xemtruoc=a.xem_truoc, font_path=font_path,
               logo_chu=a.logo_chu, nhan=a.nhan, mascots=a.mascot,
               mau=a.mau, bong_bong=not a.khong_bong_bong)
    except Exception as e:
        print(f"❌ {e}")
        return 1
    print(f"✅ Hồ sơ kênh “{kenh}” → {kenh_hoso.thu_muc(kenh)}  "
          f"(logo: {', '.join(kenh_hoso.logos(kenh)) or 'chưa có'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
