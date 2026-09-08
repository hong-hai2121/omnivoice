"""
Vẽ thêm các kiểu NỀN Khung0 (lớp dưới cùng của video ngang) — chủ đề mèo, tông hồng.

Khung0.png gốc là nền vẽ tay. Script này vẽ thêm vài kiểu khác bằng PIL (không cần
ảnh ngoài) để mỗi lần dựng video_khung.build_video chọn NGẪU NHIÊN một nền trong
Backbround/Khung0*.png (giống cách chọn viền khung1*.png).

BỐ CỤC GIỮ NGUYÊN theo Khung0.png gốc — nền ghép với nhiều lớp khác (viền khung1,
logo ở K2_LOGO_BOX, nút Subscribe + mèo của khung2), nên chỉ những vùng sau còn
NHÌN THẤY sau khi lồng (đo bằng cách ghép khung1.png + logo + khung2.png):
  - Cột trái  x 0–315   : góc trên (y 0–345) và góc dưới (y 785–1080);
                          y 348–775 bị logo + nút Subscribe che → để trơn.
  - Cột phải  x 1607–1920: cả chiều cao, 3 cụm như bản gốc (trên / giữa / dưới).
  - Dải trên  y 0–86    : trừ 2 cụm mèo của khung2 (x 476–786 và 1121–1442).
  - Dải dưới  y 995–1080: trừ mèo to của khung2 (x 819–1267).
Mọi kiểu đều đặt 5 cụm trang trí đúng chỗ bản gốc: mèo góc trên trái, cụm hoa/đồ
chơi góc dưới trái, đôi mèo trên phải, mèo ló đầu + dấu chân giữa phải, mèo mẹ con
+ tim dưới phải. Phần giữa (bị video che) chỉ có nền + hoạ tiết.

Cách dùng:
    python scripts/video_khung0_tao.py            # vẽ các kiểu còn thiếu
    python scripts/video_khung0_tao.py --force    # vẽ lại tất cả
    python scripts/video_khung0_tao.py --xem      # kèm ảnh ghép thử (Backbround/khung0_xemtruoc/)
    python scripts/video_khung0_tao.py --kieu "chấm bi"   # chỉ một kiểu
"""

from __future__ import annotations

import argparse
import math
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
BG_DIR = BASE_DIR / "Backbround"
XEM_DIR = BG_DIR / "khung0_xemtruoc"

W, H = 1920, 1080
S = 3                       # vẽ ở 3x rồi thu về (khử răng cưa)

OUT = (46, 36, 40, 255)     # màu viền nét (đen ấm)
LW = 4.5                    # độ dày viền ở 1x
EAR = (255, 172, 192, 255)  # tai trong
NOSE = (236, 112, 138, 255)
BLUSH = (255, 140, 165, 130)

# Bảng màu lông (pastel)
TRANG = (255, 255, 255, 255)
KEM = (255, 246, 226, 255)
CAM = (247, 178, 102, 255)
XAM = (196, 196, 206, 255)
NAU = (176, 136, 114, 255)
DEN = (74, 70, 76, 255)
HONG_NHAT = (255, 226, 234, 255)


# ─────────────────────────────────────────────────────────────── vẽ cơ bản ──
class Ve:
    """Bút vẽ nhận toạ độ 1x (1920×1080), tự nhân S khi vẽ lên ảnh lớn."""

    def __init__(self, im: Image.Image):
        self.im = im
        self.d = ImageDraw.Draw(im, "RGBA")

    def ellipse(self, cx, cy, rx, ry, fill):
        if rx <= 0 or ry <= 0:
            return
        self.d.ellipse([(cx - rx) * S, (cy - ry) * S, (cx + rx) * S, (cy + ry) * S], fill=fill)

    def poly(self, pts, fill):
        self.d.polygon([(x * S, y * S) for x, y in pts], fill=fill)

    def line(self, pts, fill, w):
        P = [(x * S, y * S) for x, y in pts]
        self.d.line(P, fill=fill, width=max(1, round(w * S)), joint="curve")
        r = w * S / 2
        for x, y in (P[0], P[-1]):
            self.d.ellipse([x - r, y - r, x + r, y + r], fill=fill)

    def rrect(self, x0, y0, x1, y1, r, fill):
        self.d.rounded_rectangle([x0 * S, y0 * S, x1 * S, y1 * S], radius=r * S, fill=fill)


def bezier(pts, n=24):
    """Điểm trên đường Bezier (bậc bất kỳ) — để vẽ đuôi/cành cong bằng polyline."""
    out = []
    k = len(pts) - 1
    for i in range(n + 1):
        t = i / n
        x = y = 0.0
        for j, (px, py) in enumerate(pts):
            b = math.comb(k, j) * (1 - t) ** (k - j) * t ** j
            x += b * px
            y += b * py
        out.append((x, y))
    return out


def arc_pts(cx, cy, r, a0, a1, n=16):
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def heart_pts(cx, cy, s, rot=0.0, n=64):
    """Đa giác hình tim (cong mượt), rộng ≈ 2s, đỉnh nhọn hướng xuống khi rot=0."""
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        x = 16 * math.sin(t) ** 3
        y = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
        x, y = x / 16 * s, y / 16 * s
        if rot:
            c, sn = math.cos(rot), math.sin(rot)
            x, y = x * c - y * sn, x * sn + y * c
        pts.append((cx + x, cy + y))
    return pts


def star_pts(cx, cy, r, n=5, inner=0.45, rot=-90):
    pts = []
    for i in range(2 * n):
        rr = r if i % 2 == 0 else r * inner
        a = math.radians(rot + 180 / n * i)
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return pts


def draw_parts(ve: Ve, parts, expand=0.0, color=None):
    """Vẽ danh sách bộ phận; expand>0 = nới rộng mọi bộ phận (lượt vẽ viền)."""
    for p in parts:
        f = color or p["fill"]
        k = p["k"]
        if k == "e":
            ve.ellipse(p["cx"], p["cy"], p["rx"] + expand, p["ry"] + expand, f)
        elif k == "p":
            ve.poly(p["pts"], f)
            if expand > 0:
                ve.line(list(p["pts"]) + [p["pts"][0]], f, 2 * expand)
        elif k == "l":
            ve.line(p["pts"], f, p["w"] + 2 * expand)
        elif k == "r":
            ve.rrect(p["x0"] - expand, p["y0"] - expand, p["x1"] + expand, p["y1"] + expand,
                     p["r"] + expand, f)


def draw_shape(ve: Ve, parts, lw=LW, outline=OUT):
    """Hình = nhiều bộ phận chung MỘT đường viền bao ngoài (như tranh vẽ nét)."""
    if lw:
        draw_parts(ve, parts, expand=lw, color=outline)
    draw_parts(ve, parts)


def E(cx, cy, rx, ry, fill):
    return {"k": "e", "cx": cx, "cy": cy, "rx": rx, "ry": ry, "fill": fill}


def P(pts, fill):
    return {"k": "p", "pts": pts, "fill": fill}


def L(pts, w, fill):
    return {"k": "l", "pts": pts, "w": w, "fill": fill}


def R(x0, y0, x1, y1, r, fill):
    return {"k": "r", "x0": x0, "y0": y0, "x1": x1, "y1": y1, "r": r, "fill": fill}


def darker(c, f=0.78):
    return (int(c[0] * f), int(c[1] * f), int(c[2] * f), c[3])


# ─────────────────────────────────────────────────────────────────── mèo ──
class Meo:
    """Vẽ một con mèo theo hệ toạ độ cục bộ (bán kính đầu = 1) đặt tại (cx, cy), cỡ s."""

    def __init__(self, ve: Ve, cx, cy, s, mau=TRANG, *, lat=False):
        self.ve, self.cx, self.cy, self.s, self.mau = ve, cx, cy, s, mau
        self.flip = -1 if lat else 1

    def T(self, u, v):
        return (self.cx + u * self.s * self.flip, self.cy + v * self.s)

    def e(self, u, v, ru, rv, fill=None):
        x, y = self.T(u, v)
        return E(x, y, ru * self.s, rv * self.s, fill or self.mau)

    def p(self, pts, fill=None):
        return P([self.T(u, v) for u, v in pts], fill or self.mau)

    def l(self, pts, w, fill=None):
        return L([self.T(u, v) for u, v in pts], w * self.s, fill or self.mau)

    def r(self, u0, v0, u1, v1, rad, fill=None):
        x0, y0 = self.T(u0, v0)
        x1, y1 = self.T(u1, v1)
        return R(min(x0, x1), y0, max(x0, x1), y1, rad * self.s, fill or self.mau)

    # bộ phận dùng chung
    def tai(self, dy=0.0):
        # Tai = tam giác; lượt viền (line joint="curve") tự bo tròn đỉnh, KHÔNG thêm
        # chấm tròn ở đỉnh (thử rồi: thành "cục" thừa trên tai).
        L_ = [(-1.0, -0.35 + dy), (-0.8, -1.42 + dy), (-0.15, -0.88 + dy)]
        R_ = [(1.0, -0.35 + dy), (0.8, -1.42 + dy), (0.15, -0.88 + dy)]
        return [self.p(L_), self.p(R_)]

    def tai_trong(self, dy=0.0):
        for sign in (-1, 1):
            tri = [(-1.0, -0.35 + dy), (-0.8, -1.42 + dy), (-0.15, -0.88 + dy)]
            cx_ = sum(p[0] for p in tri) / 3
            cy_ = sum(p[1] for p in tri) / 3
            inner = [(cx_ + (x - cx_) * 0.52, cy_ + (y - cy_) * 0.52) for x, y in tri]
            inner = [(sign * x, y) for x, y in inner]
            draw_parts(self.ve, [self.p(inner, EAR)])

    def mat(self, kieu="cham", dy=0.0, hx=0.44, hy=-0.05):
        """Mắt: cham (chấm tròn), cuoi (cong ^ ^), nham (nháy 1 bên), to (mắt to)."""
        ve = self.ve
        for sign in (-1, 1):
            x, y = hx * sign, hy + dy
            if kieu == "cuoi" or (kieu == "nham" and sign == -1):
                pts = [self.T(u, v) for u, v in arc_pts(x, y + 0.12, 0.17, 200, 340, 12)]
                ve.line(pts, OUT, 0.075 * self.s)
            elif kieu == "to":
                draw_parts(ve, [self.e(x, y, 0.15, 0.17, OUT), self.e(x + 0.05, y - 0.06, 0.05, 0.055, TRANG)])
            else:
                draw_parts(ve, [self.e(x, y, 0.1, 0.11, OUT), self.e(x + 0.035, y - 0.04, 0.03, 0.03, TRANG)])

    def mui_mieng(self, dy=0.0, rau=True):
        ve = self.ve
        draw_parts(ve, [self.e(0, 0.2 + dy, 0.085, 0.06, NOSE)])
        for sign in (-1, 1):
            pts = [self.T(u, v) for u, v in arc_pts(0.13 * sign, 0.24 + dy, 0.13, 20, 160, 10)]
            ve.line(pts, OUT, 0.055 * self.s)
        draw_parts(ve, [self.e(-0.72, 0.3 + dy, 0.2, 0.11, BLUSH), self.e(0.72, 0.3 + dy, 0.2, 0.11, BLUSH)])
        if rau:
            for sign in (-1, 1):
                for a, b in (((0.78, 0.12), (1.35, 0.02)), ((0.8, 0.3), (1.38, 0.4))):
                    ve.line([self.T(a[0] * sign, a[1] + dy), self.T(b[0] * sign, b[1] + dy)], OUT, 0.045 * self.s)

    def vet(self, vets, mau):
        """Vệt lông màu khác (mèo tam thể, mèo vá) — ellipse nằm trong đầu/thân.
        Mỗi vệt (u, v, ru, rv) dùng `mau`, hoặc (u, v, ru, rv, mau_riêng)."""
        draw_parts(self.ve, [self.e(*v[:4], v[4] if len(v) > 4 else mau) for v in vets])

    def soc(self, dy=0.0, mau=None):
        """3 sọc trán mèo mướp."""
        c = mau or darker(self.mau, 0.72)
        for u0, v0, u1, v1 in ((-0.28, -0.82, -0.2, -0.5), (0, -0.92, 0, -0.55), (0.28, -0.82, 0.2, -0.5)):
            self.ve.line([self.T(u0, v0 + dy), self.T(u1, v1 + dy)], c, 0.075 * self.s)

    # ── các tư thế ──
    def ngoi(self, *, mat="cham", tay="xuoi", duoi=True, vet=None, vet_mau=None, soc=False):
        """Ngồi nhìn thẳng; tay='vay' = giơ một tay lên chào."""
        parts = [self.e(0, 1.62, 1.15, 1.22), self.e(0, 0, 1.18, 1.02)] + self.tai()
        parts.append(self.e(-0.52, 2.62, 0.38, 0.24))
        if tay == "vay":
            # cánh tay nối từ thân lên bàn tay giơ cạnh đầu
            parts.append(self.l([(0.8, 1.45), (1.28, 0.75)], 0.5))
            parts.append(self.e(1.32, 0.62, 0.34, 0.3))
        else:
            parts.append(self.e(0.52, 2.62, 0.38, 0.24))
        if duoi:
            parts.append(self.l(bezier([(0.9, 2.5), (1.95, 2.65), (2.15, 1.55), (1.7, 1.2)]), 0.36))
        draw_shape(self.ve, parts)
        if vet:
            self.vet(vet, vet_mau or CAM)
        if soc:
            self.soc()
        self.tai_trong()
        self.mat(mat)
        self.mui_mieng()
        ve = self.ve
        for u in (-0.64, -0.4):                      # ngón tay trái
            ve.line([self.T(u, 2.52), self.T(u, 2.7)], OUT, 0.05 * self.s)
        if tay != "vay":
            for u in (0.4, 0.64):
                ve.line([self.T(u, 2.52), self.T(u, 2.7)], OUT, 0.05 * self.s)
        else:
            for v in (0.5, 0.74):
                ve.line([self.T(1.54, v), self.T(1.66, v)], OUT, 0.05 * self.s)

    def nam(self, *, mat="cuoi", vet=None, vet_mau=None, soc=False):
        """Nằm "ổ bánh mì" — thân bo tròn, tay giấu, đuôi cuộn bên phải."""
        parts = [self.r(-1.55, 0.05, 1.55, 1.55, 0.72), self.e(-0.12, -0.22, 1.14, 0.98)]
        parts += self.tai(dy=-0.22)
        parts += [self.e(-0.62, 1.5, 0.36, 0.2), self.e(0.28, 1.5, 0.36, 0.2)]
        parts.append(self.l(bezier([(1.25, 1.4), (2.15, 1.45), (2.2, 0.55), (1.72, 0.4)]), 0.32))
        draw_shape(self.ve, parts)
        if vet:
            self.vet(vet, vet_mau or CAM)
        if soc:
            self.soc(dy=-0.22)
        self.tai_trong(dy=-0.22)
        self.mat(mat, dy=-0.22, hx=0.46)
        self.mui_mieng(dy=-0.22)
        for u in (-0.72, -0.5, 0.18, 0.4):
            self.ve.line([self.T(u, 1.42), self.T(u, 1.6)], OUT, 0.05 * self.s)

    def ngo(self, *, mat="to", vet=None, vet_mau=None, soc=False):
        """Ló đầu ra, hai tay bám mép — phần bên trái đầu nằm dưới viền khung."""
        parts = [self.e(0, 0, 1.18, 1.02)] + self.tai()
        parts += [self.e(-0.5, 0.95, 0.42, 0.28), self.e(0.42, 1.0, 0.42, 0.28)]
        draw_shape(self.ve, parts)
        if vet:
            self.vet(vet, vet_mau or CAM)
        if soc:
            self.soc()
        self.tai_trong()
        self.mat(mat)
        self.mui_mieng()
        # Vạch ngón ở NỬA DƯỚI bàn tay (vẽ cao hơn thì trông như răng dưới cằm).
        for u in (-0.64, -0.38, 0.28, 0.54):
            self.ve.line([self.T(u, 1.02), self.T(u, 1.2)], OUT, 0.05 * self.s)

    def lung(self, *, duoi="phai", vet=None, vet_mau=None, soc=False, dau_lech=0.0):
        """Nhìn từ SAU LƯNG (đôi mèo ngồi cạnh nhau). duoi: 'phai'/'trai' (cuộn thành nửa tim)."""
        parts = [self.e(0, 1.05, 1.05, 1.32), self.e(dau_lech, -0.55, 1.0, 0.92)] + self.tai(dy=-0.55)
        if duoi == "phai":
            parts.append(self.l(bezier([(0.55, 2.2), (1.15, 2.42), (1.42, 1.72), (1.08, 1.32)]), 0.34))
        else:
            parts.append(self.l(bezier([(-0.55, 2.2), (-1.15, 2.42), (-1.42, 1.72), (-1.08, 1.32)]), 0.34))
        draw_shape(self.ve, parts)
        if vet:
            self.vet(vet, vet_mau or CAM)
        if soc:
            c = darker(self.mau, 0.72)
            for v in (0.55, 0.95, 1.35):
                pts = [self.T(u, w) for u, w in arc_pts(0, v - 0.75, 0.9, 62, 118, 10)]
                self.ve.line(pts, c, 0.08 * self.s)


# ───────────────────────────────────────────────────────────── đồ trang trí ──
def tim(ve: Ve, cx, cy, s, mau, vien=None, sang=True, rot=0.0):
    pts = heart_pts(cx, cy, s, rot)
    if vien:
        draw_shape(ve, [P(pts, mau)], lw=max(1.5, s * 0.08), outline=vien)
    else:
        ve.poly(pts, mau)
    if sang and s >= 14:
        ve.ellipse(cx - s * 0.42, cy - s * 0.42, s * 0.14, s * 0.1, (255, 255, 255, 170))


def dau_chan(ve: Ve, cx, cy, s, mau=OUT, goc=0.0):
    """Dấu chân mèo: đệm to + 4 ngón, xoay theo hướng đi (độ)."""
    a = math.radians(goc)

    def T(u, v):
        return (cx + (u * math.cos(a) - v * math.sin(a)) * s, cy + (u * math.sin(a) + v * math.cos(a)) * s)

    x, y = T(0, 0.3)
    ve.ellipse(x, y, s * 0.55, s * 0.45, mau)
    # ellipse không xoay được → đệm lớn tròn, ngón tròn
    for u, v, r in ((-0.72, -0.25, 0.24), (-0.26, -0.62, 0.26), (0.26, -0.62, 0.26), (0.72, -0.25, 0.24)):
        x, y = T(u, v)
        ve.ellipse(x, y, r * s, r * s, mau)


def ngoi_sao(ve: Ve, cx, cy, r, mau, vien=None):
    pts = star_pts(cx, cy, r)
    if vien:
        draw_shape(ve, [P(pts, mau)], lw=max(1.5, r * 0.1), outline=vien)
    else:
        ve.poly(pts, mau)


def lap_lanh(ve: Ve, cx, cy, r, mau):
    ve.poly(star_pts(cx, cy, r, n=4, inner=0.28), mau)


def hoa(ve: Ve, cx, cy, r, mau_canh, mau_nhuy=(255, 232, 120, 255), vien=None, canh=5, rot=0.0):
    parts = []
    for i in range(canh):
        a = math.radians(rot + 360 / canh * i)
        parts.append(E(cx + math.cos(a) * r * 0.62, cy + math.sin(a) * r * 0.62, r * 0.42, r * 0.42, mau_canh))
    draw_shape(ve, parts, lw=(max(1.5, r * 0.08) if vien else 0), outline=vien or OUT)
    draw_shape(ve, [E(cx, cy, r * 0.28, r * 0.28, mau_nhuy)], lw=(max(1.5, r * 0.08) if vien else 0), outline=vien or OUT)


def hoa_anh_dao(ve: Ve, cx, cy, r, mau=(255, 190, 205, 255), rot=0.0):
    """5 cánh hình tim (khuyết ở đầu cánh) quanh nhuỵ vàng."""
    for i in range(5):
        th = math.radians(rot + 72 * i)
        px, py = cx + math.cos(th) * r * 0.66, cy + math.sin(th) * r * 0.66
        ve.poly(heart_pts(px, py, r * 0.44, th + math.pi / 2), mau)
    for i in range(5):
        th = math.radians(rot + 72 * i + 36)
        ve.line([(cx, cy), (cx + math.cos(th) * r * 0.36, cy + math.sin(th) * r * 0.36)], (255, 214, 120, 255), r * 0.05)
        ve.ellipse(cx + math.cos(th) * r * 0.36, cy + math.sin(th) * r * 0.36, r * 0.06, r * 0.06, (255, 200, 90, 255))
    ve.ellipse(cx, cy, r * 0.12, r * 0.12, (255, 226, 140, 255))


def canh_hoa(ve: Ve, cx, cy, s, rot, mau=(255, 196, 210, 255)):
    ve.poly(heart_pts(cx, cy, s, rot), mau)


def dau_tay(ve: Ve, cx, cy, s, vien=True):
    pts = []
    for i in range(48):
        t = 2 * math.pi * i / 48
        pts.append((cx + s * 0.88 * math.sin(t) * (1 + 0.28 * math.cos(t)), cy - s * math.cos(t) * 1.0))
    parts = [P(pts, (255, 112, 132, 255))]
    draw_shape(ve, parts, lw=(max(1.5, s * 0.1) if vien else 0))
    la = []
    for a in (-150, -90, -30):
        ra = math.radians(a)
        la.append(E(cx + math.cos(ra) * s * 0.42, cy - s * 0.78 + math.sin(ra) * s * 0.3, s * 0.3, s * 0.18, (120, 200, 130, 255)))
    draw_shape(ve, la, lw=(max(1.5, s * 0.1) if vien else 0))
    ve.line([(cx, cy - s * 0.95), (cx, cy - s * 1.3)], (90, 160, 100, 255), s * 0.1)
    for u, v in ((-0.35, -0.2), (0.35, -0.2), (0, 0.05), (-0.4, 0.3), (0.4, 0.3), (0, 0.55), (-0.2, -0.55), (0.2, -0.55)):
        ve.ellipse(cx + u * s, cy + v * s, s * 0.07, s * 0.1, (255, 240, 200, 255))


def cuon_len(ve: Ve, cx, cy, r, mau, day=None):
    """Cuộn len: hình tròn + vài đường cong + sợi dây thả ra."""
    draw_shape(ve, [E(cx, cy, r, r, mau)])
    c = darker(mau, 0.75)
    for a0, off in ((150, -0.45), (150, 0.0), (150, 0.45)):
        pts = arc_pts(cx + off * r * 0.6, cy, r * 0.92, a0 + 30, a0 + 130, 14)
        pts = [(x, y) for x, y in pts if (x - cx) ** 2 + (y - cy) ** 2 <= (r * 0.93) ** 2]
        if len(pts) > 2:
            ve.line(pts, c, r * 0.1)
    if day:
        ve.line(bezier(day), c, r * 0.11)


def ca(ve: Ve, cx, cy, s, mau=(150, 200, 240, 255), lat=False):
    f = -1 if lat else 1
    parts = [E(cx, cy, s, s * 0.55, mau),
             P([(cx + f * s * 0.75, cy), (cx + f * s * 1.45, cy - s * 0.55), (cx + f * s * 1.45, cy + s * 0.55)], mau)]
    draw_shape(ve, parts, lw=max(1.5, s * 0.1))
    ve.ellipse(cx - f * s * 0.45, cy - s * 0.12, s * 0.1, s * 0.1, OUT)
    ve.ellipse(cx - f * s * 0.42, cy - s * 0.15, s * 0.035, s * 0.035, TRANG)
    pts = arc_pts(cx - f * s * 0.05, cy, s * 0.35, -60, 60, 10) if not lat else arc_pts(cx + s * 0.05, cy, s * 0.35, 120, 240, 10)
    ve.line(pts, darker(mau, 0.7), s * 0.07)


def no(ve: Ve, cx, cy, s, mau):
    """Nơ: hai cánh + nút giữa."""
    parts = [P([(cx - s * 0.15, cy), (cx - s * 1.05, cy - s * 0.62), (cx - s * 1.0, cy + s * 0.6)], mau),
             P([(cx + s * 0.15, cy), (cx + s * 1.05, cy - s * 0.62), (cx + s * 1.0, cy + s * 0.6)], mau),
             E(cx - s * 0.62, cy - s * 0.3, s * 0.42, s * 0.34, mau), E(cx + s * 0.62, cy - s * 0.3, s * 0.42, s * 0.34, mau),
             E(cx - s * 0.62, cy + s * 0.28, s * 0.4, s * 0.32, mau), E(cx + s * 0.62, cy + s * 0.28, s * 0.4, s * 0.32, mau)]
    draw_shape(ve, parts, lw=max(1.5, s * 0.1))
    draw_shape(ve, [E(cx, cy, s * 0.26, s * 0.3, darker(mau, 0.85))], lw=max(1.5, s * 0.1))


def may(ve: Ve, cx, cy, s, mau=(255, 255, 255, 200)):
    for u, v, r in ((-0.9, 0.1, 0.5), (-0.3, -0.25, 0.7), (0.45, -0.1, 0.62), (1.0, 0.2, 0.45)):
        ve.ellipse(cx + u * s, cy + v * s, r * s, r * s, mau)
    ve.rrect(cx - 1.3 * s, cy, cx + 1.35 * s, cy + 0.6 * s, 0.3 * s, mau)


def cay_hoa(ve: Ve, cx, cy, mau_hoa, mau_la=(150, 215, 190, 255), cao=1.0, nghieng=0.0, r=30, canh=5):
    """Một bông hoa có cuống + 2 lá (góc dưới trái như bản gốc)."""
    top = (cx + nghieng * 60, cy - 150 * cao)
    stem = bezier([(cx, cy), (cx + nghieng * 20, cy - 70 * cao), top])
    ve.line(stem, mau_la, 5)
    for k, side in ((0.35, -1), (0.6, 1)):
        i = int(len(stem) * k)
        x, y = stem[i]
        pts = bezier([(x, y), (x + side * 26, y - 18), (x + side * 48, y - 8), (x + side * 24, y + 10), (x, y)], 24)
        ve.poly(pts, mau_la)
    hoa(ve, top[0], top[1], r, mau_hoa, vien=darker(mau_hoa, 0.7), canh=canh)


# ──────────────────────────────────────────────────────────────── nền ──
def nen_mau_nuoc(mau1, mau2, seed, sang=None):
    """Nền hồng loang màu nước: nhiễu tần số thấp phóng to + vài đốm sáng mờ."""
    rng = np.random.default_rng(seed)
    noise = rng.random((18, 32)).astype("float32")
    small = Image.fromarray((noise * 255).astype("uint8"), "L").resize((W, H), Image.Resampling.BICUBIC)
    n = np.asarray(small).astype("float32") / 255.0
    n = (n - n.min()) / max(1e-6, (n.max() - n.min()))
    a = np.array(mau1[:3], dtype="float32")
    b = np.array(mau2[:3], dtype="float32")
    rgb = a[None, None, :] * (1 - n[..., None]) + b[None, None, :] * n[..., None]
    im = Image.fromarray(rgb.clip(0, 255).astype("uint8"), "RGB").convert("RGBA")
    # đốm sáng mềm
    spot = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(spot)
    for _ in range(9):
        x, y = rng.integers(0, W), rng.integers(0, H)
        rx, ry = rng.integers(180, 420), rng.integers(120, 300)
        d.ellipse([x - rx, y - ry, x + rx, y + ry], fill=int(rng.integers(50, 110)))
    spot = spot.filter(ImageFilter.GaussianBlur(90))
    white = Image.new("RGBA", (W, H), sang or (255, 255, 255, 255))
    im = Image.composite(white, im, spot)
    return im.resize((W * S, H * S), Image.Resampling.BICUBIC)


def hoa_tiet_cham_bi(ve: Ve, rng, mau=(255, 255, 255, 150), buoc=96, r=13):
    for j, y in enumerate(range(-buoc, H + buoc, buoc)):
        off = buoc // 2 if j % 2 else 0
        for x in range(-buoc + off, W + buoc, buoc):
            ve.ellipse(x, y, r, r, mau)


def hoa_tiet_ca_ro(ve: Ve, mau=(255, 255, 255, 62), buoc=88, rong=44):
    for x in range(0, W + buoc, buoc):
        ve.d.rectangle([x * S, 0, (x + rong) * S, H * S], fill=mau)
    for y in range(0, H + buoc, buoc):
        ve.d.rectangle([0, y * S, W * S, (y + rong) * S], fill=mau)


def hoa_tiet_soc_cheo(ve: Ve, mau=(255, 255, 255, 78), buoc=150, rong=58):
    for x0 in range(-H - buoc, W + buoc, buoc):
        ve.poly([(x0, H), (x0 + H, 0), (x0 + H + rong, 0), (x0 + rong, H)], mau)


def hoa_tiet_rai(ve: Ve, rng, ve_mot, buoc=190, jitter=55, xac_suat=0.75):
    """Rải hoạ tiết nhỏ theo lưới lệch + ngẫu nhiên (khắp nền; phần giữa bị video che)."""
    for j, y in enumerate(range(60, H, buoc)):
        off = buoc // 2 if j % 2 else 0
        for x in range(60 + off, W, buoc):
            if rng.random() < xac_suat:
                ve_mot(x + rng.integers(-jitter, jitter), y + rng.integers(-jitter, jitter))


# ─────────────────────────────────────────────────────────── các kiểu ──
def _dau_chan_duong(ve, mau=OUT, s=13):
    """Vệt dấu chân từ góc trên phải đi xuống mèo ló đầu (như bản gốc)."""
    x0, y0, x1, y1 = 1895, 385, 1700, 765
    n = 8
    ang = math.degrees(math.atan2(y1 - y0, x1 - x0)) + 90
    for i in range(n):
        t = i / (n - 1)
        x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
        side = -1 if i % 2 else 1
        nx, ny = -(y1 - y0), (x1 - x0)
        ln = math.hypot(nx, ny)
        x += nx / ln * 22 * side
        y += ny / ln * 22 * side
        dau_chan(ve, x, y, s, mau, ang)


def _tim_goc_duoi_phai(ve, mau, mau2):
    for x, y, s in ((1330, 1042, 34), (1425, 1015, 22), (1548, 1045, 30), (1640, 812, 17), (1878, 800, 22), (1905, 1000, 16)):
        tim(ve, x, y, s, mau if s > 20 else mau2)


def _doi_meo(ve, m1, m2, vet1=None, vet2=None, soc1=False, soc2=False, tim_mau=(255, 120, 150, 255)):
    cx, cy, s = 1766, 178, 54
    Meo(ve, cx - 1.02 * s, cy, s, m1).lung(duoi="phai", vet=vet1, soc=soc1)
    Meo(ve, cx + 1.02 * s, cy, s, m2).lung(duoi="trai", vet=vet2, soc=soc2)
    for x, y, r in ((cx - 80, cy - 118, 12), (cx + 92, cy - 132, 15), (cx + 118, cy - 48, 9), (cx - 118, cy - 40, 10)):
        tim(ve, x, y, r, tim_mau, sang=False)


def _me_con(ve, m_me, m_con, mat_me="cuoi", vet_me=None, vet_con=None, soc_me=False, soc_con=False):
    Meo(ve, 1790, 922, 60, m_me).ngoi(mat=mat_me, duoi=True, vet=vet_me, soc=soc_me)
    Meo(ve, 1692, 1002, 36, m_con).ngoi(mat="cham", duoi=False, vet=vet_con, soc=soc_con)


def _diem_xuyet(ve, kind, mau, mau2=None):
    """Điểm xuyết nhỏ ở dải trên/dưới còn nhìn thấy (giữa các cụm của khung2)."""
    spots_top = [(392, 44), (446, 30), (860, 42), (940, 30), (1010, 46), (1075, 32), (1480, 40), (1546, 28)]
    spots_bot = [(400, 1040), (470, 1058), (560, 1038), (700, 1052), (780, 1034), (1300, 1050)]
    for i, (x, y) in enumerate(spots_top + spots_bot):
        s = 11 + (i % 3) * 3
        c = mau if i % 2 else (mau2 or mau)
        if kind == "tim":
            tim(ve, x, y, s, c, sang=False)
        elif kind == "sao":
            (ngoi_sao if i % 3 else lap_lanh)(ve, x, y, s, c)
        elif kind == "dau_chan":
            dau_chan(ve, x, y, s * 0.75, c, (i * 37) % 360 - 180)
        elif kind == "canh_hoa":
            canh_hoa(ve, x, y, s * 0.9, (i * 0.9) % math.pi, c)
        elif kind == "dau_tay":
            dau_tay(ve, x, y, s * 0.9)


def kieu_cham_bi(ve: Ve, rng):
    hoa_tiet_cham_bi(ve, rng)
    # Góc trên trái: mèo trắng vá hồng giơ tay chào (như bản gốc)
    Meo(ve, 150, 128, 58, TRANG).ngoi(mat="cham", tay="vay", vet=[(-0.55, -0.5, 0.55, 0.36), (0.75, 1.3, 0.42, 0.5)], vet_mau=HONG_NHAT)
    # Góc dưới trái: hoa
    cay_hoa(ve, 70, 1075, (255, 150, 180, 255), cao=0.85, nghieng=-0.4, r=32)
    cay_hoa(ve, 165, 1080, (200, 160, 240, 255), cao=1.15, nghieng=0.15, r=36)
    cay_hoa(ve, 250, 1078, (150, 210, 240, 255), cao=0.7, nghieng=0.45, r=26, canh=6)
    # Trên phải: đôi mèo
    _doi_meo(ve, XAM, CAM, soc2=True)
    # Giữa phải: mèo kem ló đầu + dấu chân
    _dau_chan_duong(ve)
    Meo(ve, 1668, 590, 76, KEM).ngo(mat="to")
    # Dưới phải: mẹ con + tim
    _tim_goc_duoi_phai(ve, (255, 150, 170, 255), (255, 190, 205, 255))
    _me_con(ve, TRANG, TRANG, vet_me=[(0.6, -0.55, 0.55, 0.4), (-0.7, 1.5, 0.5, 0.7)], vet_con=[(-0.5, -0.5, 0.45, 0.32)])
    _diem_xuyet(ve, "tim", (255, 160, 180, 255), (255, 200, 215, 255))


def kieu_ca_ro(ve: Ve, rng):
    # Dải HỒNG trên nền hồng nhạt (dải trắng phủ 3/4 diện tích → nền hoá trắng, mất tông hồng)
    hoa_tiet_ca_ro(ve, mau=(255, 150, 185, 56))
    Meo(ve, 150, 205, 60, CAM).nam(mat="cuoi", soc=True)
    no(ve, 92, 120, 22, (255, 120, 150, 255))
    # Dưới trái: cuộn len + cá
    cuon_len(ve, 90, 985, 48, (255, 150, 180, 255), day=[(130, 1010), (200, 1060), (270, 1000), (300, 1075)])
    cuon_len(ve, 200, 1040, 34, (170, 200, 250, 255))
    ca(ve, 250, 925, 30, (255, 200, 120, 255))
    ca(ve, 110, 880, 24, (150, 200, 240, 255), lat=True)
    _doi_meo(ve, TRANG, XAM, vet1=[(0.45, -0.85, 0.42, 0.3)], soc2=True, tim_mau=(255, 110, 140, 255))
    _dau_chan_duong(ve, (150, 90, 110, 255))
    Meo(ve, 1668, 590, 76, TRANG).ngo(mat="cham", vet=[(-0.6, -0.55, 0.5, 0.36), (0.75, 0.2, 0.42, 0.5)], vet_mau=CAM)
    _tim_goc_duoi_phai(ve, (255, 130, 160, 255), (255, 180, 200, 255))
    _me_con(ve, KEM, CAM, mat_me="cuoi", soc_con=True)
    _diem_xuyet(ve, "sao", (255, 214, 110, 255), (255, 170, 190, 255))


def kieu_dau_tay(ve: Ve, rng):
    hoa_tiet_rai(ve, rng, lambda x, y: dau_tay(ve, x, y, 15 + int(rng.integers(0, 6))), buoc=210, xac_suat=0.7)
    hoa_tiet_rai(ve, rng, lambda x, y: tim(ve, x, y, 9, (255, 170, 190, 255), sang=False), buoc=170, xac_suat=0.5)
    Meo(ve, 150, 128, 58, XAM).ngoi(mat="cuoi", tay="vay")
    # Dưới trái: bụi dâu + mèo con nằm
    for x, y, s in ((40, 990, 26), (100, 1040, 30), (60, 1075, 22)):
        dau_tay(ve, x, y, s)
    ve.line(bezier([(90, 1080), (110, 990), (160, 930)]), (90, 160, 100, 255), 5)
    for x, y in ((120, 972), (150, 945)):
        ve.poly(bezier([(x, y), (x + 20, y - 26), (x + 46, y - 12), (x + 22, y + 8), (x, y)], 20), (130, 205, 140, 255))
    Meo(ve, 215, 1015, 34, CAM).nam(mat="cuoi", soc=True)
    _doi_meo(ve, KEM, NAU, soc2=True, tim_mau=(255, 100, 130, 255))
    _dau_chan_duong(ve)
    Meo(ve, 1668, 590, 76, TRANG).ngo(mat="to")
    _tim_goc_duoi_phai(ve, (255, 120, 150, 255), (255, 180, 200, 255))
    _me_con(ve, CAM, XAM, mat_me="nham", soc_me=True)
    _diem_xuyet(ve, "dau_tay", (255, 112, 132, 255))


def kieu_hoa_anh_dao(ve: Ve, rng):
    hoa_tiet_rai(ve, rng, lambda x, y: canh_hoa(ve, x, y, 8 + int(rng.integers(0, 6)), rng.random() * math.pi), buoc=150, xac_suat=0.8)
    hoa_tiet_rai(ve, rng, lambda x, y: hoa_anh_dao(ve, x, y, 16 + int(rng.integers(0, 8)), rot=rng.random() * 72), buoc=330, xac_suat=0.6)
    # mèo tam thể: vá cam + vá xám (vệt vẽ TRƯỚC mặt/tai trong nên không đè nét mặt)
    Meo(ve, 150, 128, 58, TRANG).ngoi(mat="cham", vet=[(-0.6, -0.5, 0.5, 0.36), (0.55, 1.4, 0.45, 0.6),
                                                       (0.5, -0.55, 0.36, 0.26, XAM)], vet_mau=CAM)
    # Dưới trái: cành anh đào
    canh = bezier([(0, 1080), (90, 960), (200, 910), (300, 850)], 30)
    ve.line(canh, (150, 100, 90, 255), 9)
    for k, side in ((0.35, -1), (0.55, 1), (0.8, -1)):
        x, y = canh[int(len(canh) * k)]
        ve.line(bezier([(x, y), (x + 25 * side, y - 45), (x + 60 * side, y - 70)]), (150, 100, 90, 255), 6)
    for x, y, r in ((70, 980, 30), (130, 925, 36), (215, 912, 30), (280, 855, 34), (70, 900, 24), (240, 968, 26), (170, 860, 22)):
        hoa_anh_dao(ve, x, y, r, rot=rng.random() * 72)
    _doi_meo(ve, TRANG, DEN, tim_mau=(255, 130, 160, 255))
    _dau_chan_duong(ve, (140, 80, 100, 255))
    Meo(ve, 1668, 590, 76, CAM).ngo(mat="cuoi", soc=True)
    _tim_goc_duoi_phai(ve, (255, 140, 170, 255), (255, 190, 210, 255))
    _me_con(ve, XAM, KEM, mat_me="cuoi")
    _diem_xuyet(ve, "canh_hoa", (255, 170, 195, 255), (255, 205, 220, 255))


def kieu_keo_soc(ve: Ve, rng):
    hoa_tiet_soc_cheo(ve, mau=(255, 150, 185, 80))   # sọc hồng đậm trên nền hồng nhạt
    Meo(ve, 150, 205, 60, KEM).nam(mat="cuoi", vet=[(-0.7, -0.75, 0.42, 0.3), (0.95, 0.9, 0.42, 0.42)], vet_mau=NAU)
    ngoi_sao(ve, 250, 90, 22, (255, 214, 110, 255), vien=OUT)
    lap_lanh(ve, 60, 70, 16, (255, 230, 140, 255))
    # Dưới trái: hoa + sao
    cay_hoa(ve, 80, 1078, (255, 200, 110, 255), cao=0.9, nghieng=-0.35, r=30, canh=6)
    cay_hoa(ve, 175, 1080, (255, 140, 170, 255), cao=1.15, nghieng=0.1, r=36)
    cay_hoa(ve, 255, 1078, (170, 200, 250, 255), cao=0.7, nghieng=0.5, r=26)
    ngoi_sao(ve, 40, 880, 18, (255, 214, 110, 255), vien=OUT)
    lap_lanh(ve, 270, 850, 14, (255, 230, 140, 255))
    _doi_meo(ve, CAM, TRANG, soc1=True, vet2=[(-0.4, -0.85, 0.42, 0.3)], tim_mau=(255, 120, 150, 255))
    _dau_chan_duong(ve, (170, 100, 120, 255))
    Meo(ve, 1668, 590, 76, XAM).ngo(mat="to")
    _tim_goc_duoi_phai(ve, (255, 140, 165, 255), (255, 195, 210, 255))
    _me_con(ve, TRANG, TRANG, mat_me="cuoi",
            vet_con=[(0.5, -0.5, 0.45, 0.32, DEN), (-0.6, 1.4, 0.45, 0.6, DEN)])
    _diem_xuyet(ve, "sao", (255, 214, 110, 255), (255, 170, 190, 255))


KIEU = {
    # tên file: (hàm vẽ, màu nền 1, màu nền 2, seed)
    "chấm bi":      (kieu_cham_bi,     (255, 214, 226), (255, 236, 242), 11),
    "ca rô":        (kieu_ca_ro,       (255, 232, 240), (255, 244, 247), 22),
    "dâu tây":      (kieu_dau_tay,     (255, 222, 232), (255, 240, 244), 33),
    "hoa anh đào":  (kieu_hoa_anh_dao, (255, 218, 230), (255, 238, 243), 44),
    "kẹo sọc":      (kieu_keo_soc,     (255, 230, 238), (255, 244, 247), 55),
}


def ve_kieu(ten: str) -> Image.Image:
    fn, m1, m2, seed = KIEU[ten]
    rng = np.random.default_rng(seed)
    random.seed(seed)
    im = nen_mau_nuoc(m1, m2, seed)
    ve = Ve(im)
    fn(ve, rng)
    return im.resize((W, H), Image.Resampling.LANCZOS)


def duong_dan(ten: str) -> Path:
    return BG_DIR / f"Khung0 {ten}.png"


def tao_tat_ca(force=False, chi_kieu=None, log=print) -> list[Path]:
    ra = []
    for ten in KIEU:
        if chi_kieu and ten != chi_kieu:
            continue
        p = duong_dan(ten)
        if p.exists() and not force:
            log(f"♻ Đã có: {p.name}")
            ra.append(p)
            continue
        log(f"🎨 Vẽ {p.name} ...")
        im = ve_kieu(ten)
        BG_DIR.mkdir(parents=True, exist_ok=True)
        im.convert("RGB").save(p, optimize=True)     # nền đục hoàn toàn như Khung0.png gốc
        ra.append(p)
    return ra


def ghep_thu(bg: Path, out: Path):
    """Ảnh ghép thử: nền + ô video xám + khung1 (hồng) + logo + khung2 — đúng lớp của video_khung."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import video_khung as vk
    from scipy import ndimage
    k0 = Image.open(bg).convert("RGBA")
    im1, pink = vk.frame_mask(vk.KHUNG1)
    show = ndimage.binary_fill_holes(pink)
    top = vk.paste_logo(im1.copy(), vk.LOGO_DIR / "logo.png")
    top = Image.alpha_composite(top, Image.open(vk.KHUNG2).convert("RGBA"))
    vid = Image.new("RGBA", k0.size, (110, 110, 110, 255))
    mask = Image.fromarray(np.where(show, 255, 0).astype("uint8"))
    comp = k0.copy()
    comp.paste(vid, (0, 0), mask)
    comp = Image.alpha_composite(comp, top)
    out.parent.mkdir(parents=True, exist_ok=True)
    comp.convert("RGB").save(out, quality=90)
    return out


def main():
    ap = argparse.ArgumentParser(description="Vẽ các kiểu nền Khung0 (mèo, tông hồng)")
    ap.add_argument("--force", action="store_true", help="vẽ lại cả kiểu đã có")
    ap.add_argument("--kieu", default="", help="chỉ vẽ một kiểu (tên trong KIEU)")
    ap.add_argument("--xem", action="store_true", help="xuất ảnh ghép thử vào Backbround/khung0_xemtruoc/")
    a = ap.parse_args()
    if a.kieu and a.kieu not in KIEU:
        print(f"Không có kiểu {a.kieu!r}. Có: {', '.join(KIEU)}")
        sys.exit(2)
    files = tao_tat_ca(force=a.force, chi_kieu=a.kieu or None)
    if a.xem:
        for p in ([BG_DIR / "Khung0.png"] if not a.kieu else []) + files:
            if p.exists():
                o = ghep_thu(p, XEM_DIR / (p.stem + ".jpg"))
                print(f"👀 {o}")


if __name__ == "__main__":
    main()
