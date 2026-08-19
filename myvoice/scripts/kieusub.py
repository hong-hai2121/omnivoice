# -*- coding: utf-8 -*-
"""kieusub.py — KHO KIỂU PHỤ ĐỀ dùng chung cho myvoice VÀ myvideo.

Chuyển từ myvideo về đây (2026-08-16) để hai bảng điều khiển dùng CHUNG một
nguồn: mẫu JSON trong myvoice/scripts/kieusub_mau/, font rời trong
myvoice/fonts/, ảnh xem trước trong myvoice/web/static/kieusub/ (myvideo mount
thêm đường dẫn này nên hai web cùng thấy một bộ ảnh).

Mỗi kiểu là MỘT file JSON — muốn thêm kiểu mới chỉ cần thả thêm file JSON
("thutu" quyết định chỗ đứng trong danh sách), ảnh xem trước tự vẽ khi web
khởi động, hoặc chạy tay:

    python myvoice/scripts/kieusub.py --taomau        # vẽ ảnh còn thiếu
    python myvoice/scripts/kieusub.py --taomau --ep   # vẽ lại TOÀN BỘ

Các "hieuung" đang có (kiểu tĩnh ra ảnh PNG, kiểu động ra WEBP chuyển động):
  tinh     chữ đứng yên — dáng vẻ do font/màu/viền/bóng/blur của JSON quyết định
  hopbo    chữ trên khung nền bo góc tự đo bề rộng (kiểu cổ điển của myvoice)
  glitch   chữ + 2 bản lệch màu đỏ/xanh hai phía (tách lớp kiểu CapCut/TikTok)
  viendoi  viền KÉP: viền trong + viền ngoài khác màu (kiểu tiêu đề phim recap)
  karaoke  cả câu hiện sẵn, từ đang đọc NHUỘM MÀU dần theo giọng (thẻ \\k)
  hienlo   từ hiện DẦN và ở lại, từ đang đọc đổi màu + phóng nhẹ (kiểu Hormozi)
  tungtu   MỖI từ bật to đúng lúc đọc rồi nhường chỗ từ sau (word-pop TikTok)

SRT không có mốc giờ từng từ nên chia thời lượng câu theo ĐỘ DÀI từ — giọng
TTS đọc khá đều nên nhìn vẫn khớp nhịp đọc.

Khung hình: mặc định NGANG 1920x1080 (như video_gansub); video DỌC 1080x1920
truyền play_w/play_h/margin_v tương ứng vào write_ass_kieu, và lấy trần ký
tự/dòng qua chon_max_chars(k, user_max, doc=True) — khung hẹp bằng 1080/1920
nên trần rút theo tỉ lệ 23/50 giống SUB_MAX_CHARS_DOC của video_gansub.

Màu trong JSON ghi kiểu RGB hex quen mắt ("FFD700"); code tự đảo sang BGR của
ASS. Font trong myvoice/fonts KHÔNG cần cài vào Windows — bộ lọc subtitles
nhận chúng qua ':fontsdir=' (xem fontsdir_arg).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent            # myvoice/scripts/
MYVOICE_DIR = SCRIPTS_DIR.parent                         # myvoice/
MAU_DIR = SCRIPTS_DIR / "kieusub_mau"                    # kho JSON các kiểu
ANH_DIR = MYVOICE_DIR / "web" / "static" / "kieusub"     # ảnh xem trước (cả 2 web dùng)
FONT_DIR = MYVOICE_DIR / "fonts"                         # kho font rời (Anton, Bangers…)

MACDINH = "hopbo"

ASS_PLAY_W, ASS_PLAY_H = 1920, 1080
SUB_MARGIN_V = 173        # đáy chữ cách đáy khung (px) — cùng số với video_gansub
BOX_PAD_X, BOX_PAD_Y, BOX_RADIUS = 24, 10, 26            # hộp bo góc kiểu cổ điển

# Kiểu có chuyển động → ảnh xem trước là WEBP động; còn lại PNG tĩnh.
HIEUUNG_DONG = {"karaoke", "hienlo", "tungtu"}

# Đủ khoá mặc định — JSON chỉ cần ghi khoá muốn đổi.
GOC = dict(
    ten="", mota="", thutu=99, hieuung="tinh",
    font="Arial", fontfile=r"C:\Windows\Fonts\arialbd.ttf", size=67,
    bold=True, hoa=False,                 # hoa=True → in HOA toàn bộ
    mau_chu="FFFFFF",                     # màu chữ (RGB hex)
    mau_noibat="FFD700",                  # màu từ đang đọc (karaoke/hienlo)
    nhieu_mau=[],                         # hienlo: xoay vòng màu nổi bật theo từ
    mau_vien="000000", vien=0,            # viền + độ dày
    mau_vien2="000000", vien2=0,          # viendoi: viền NGOÀI thứ hai (dày thêm)
    mau_bong="000000", bong=0,            # bóng đổ + độ sâu
    blur=0,                               # nhoè mép → quầng sáng neon
    borderstyle=1,                        # 3 = khối nền đặc (màu = mau_nen)
    mau_nen="000000", nen_alpha="60",     # hộp/khối nền + độ trong (00 đặc…FF trong)
    pop=True,                             # hienlo/tungtu: từ mới phóng nhẹ
    lech=6,                               # glitch: hai bản màu lệch đi bấy nhiêu px
    ti_co=1.0,                            # tỉ lệ ap_cochu đã phóng (hộp bo góc dãn theo)
    max_chars=0,                          # >0: trần ký tự/dòng RIÊNG của kiểu (font to
)                                         # phải xuống dòng sớm hơn kẻo tràn mép)


# ── Màu: RGB hex của JSON → BGR của ASS ──────────────────────────────────────
def _rgb_style(rgb: str, alpha: str = "00") -> str:
    """'FFD700' → '&H0000D7FF' (dạng trong dòng Style:)."""
    rgb = rgb.strip().lstrip("#")
    return f"&H{alpha}{rgb[4:6]}{rgb[2:4]}{rgb[0:2]}".upper()


def _rgb_tag(rgb: str) -> str:
    """'FFD700' → '&H00D7FF&' (dạng trong thẻ ghi đè \\1c…)."""
    rgb = rgb.strip().lstrip("#")
    return f"&H{rgb[4:6]}{rgb[2:4]}{rgb[0:2]}&".upper()


# ── Kho mẫu JSON ─────────────────────────────────────────────────────────────
def danh_sach() -> list[dict]:
    """Mọi kiểu trong kieusub_mau/ (đã trộn đủ khoá mặc định), xếp theo thutu."""
    out = []
    try:
        files = sorted(MAU_DIR.glob("*.json"))
    except OSError:
        return []
    for p in files:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue                      # file hỏng thì bỏ qua, không sập web
        if isinstance(d, dict):
            out.append({**GOC, **d, "id": p.stem})
    out.sort(key=lambda d: (d.get("thutu", 99), d["id"]))
    return out


def lay(ten: str) -> dict:
    """Một kiểu theo tên file (không .json); sai tên → kiểu mặc định."""
    for d in danh_sach():
        if d["id"] == ten:
            return d
    for d in danh_sach():
        if d["id"] == MACDINH:
            return d
    return {**GOC, "id": MACDINH, "ten": "Hộp bo góc", "hieuung": "hopbo"}


def danh_sach_web() -> list[dict]:
    """Cho giao diện: kèm tên file ảnh xem trước + mtime làm số chống cache."""
    out = []
    for d in danh_sach():
        anh, v = "", 0
        for ext in (".webp", ".png"):     # kiểu đổi hiệu ứng thì ưu tiên ảnh mới hơn
            p = ANH_DIR / (d["id"] + ext)
            try:
                mt = int(p.stat().st_mtime)
            except OSError:
                continue
            if mt > v:
                anh, v = p.name, mt
        out.append({**d, "anh": anh, "v": v})
    return out


def chon_max_chars(k: dict, user_max, doc: bool = False) -> int:
    """Trần ký tự/dòng HIỆU LỰC của một kiểu.

    Ngang: trần riêng của kiểu (font to → trần nhỏ) ∧ số người dùng đặt.
    Dọc (1080x1920): khung hẹp bằng 1080/1920 nên trần rút theo tỉ lệ 23/50 —
    kiểu mặc định (bề rộng chuẩn 50) ra đúng 23 như SUB_MAX_CHARS_DOC cũ.
    """
    user_max = int(user_max)
    if doc:
        goc = k["max_chars"] or 50        # bề rộng chuẩn khung ngang của kiểu
        return min(user_max, max(8, round(goc * 23 / 50)))
    return min(user_max, k["max_chars"]) if k["max_chars"] else user_max


# ── Kho font riêng cho ffmpeg/libass ─────────────────────────────────────────
def fontsdir_arg(cwd) -> str:
    """':fontsdir=…' cho bộ lọc subtitles — để libass thấy font trong
    myvoice/fonts mà KHÔNG cần cài vào Windows.

    Ưu tiên đường dẫn TƯƠNG ĐỐI so với cwd của ffmpeg (né vụ escape dấu ':' của
    ổ đĩa Windows trong filtergraph); khác ổ đĩa mới phải dùng tuyệt đối — khi
    đó BỌC NHÁY ĐƠN + escape '\\:' (dạng trần 'D\\:' là ffmpeg từ chối)."""
    if not FONT_DIR.is_dir():
        return ""
    try:
        p = os.path.relpath(FONT_DIR, cwd).replace("\\", "/")
    except ValueError:                            # cwd nằm ổ đĩa khác
        p = ("'" + str(FONT_DIR).replace("\\", "/")
             .replace(":", "\\:") + "'")
    return ":fontsdir=" + p


def _fontfile(k: dict) -> str:
    """fontfile của kiểu — ghi tương đối trong JSON thì hiểu là so với myvoice/."""
    p = Path(k["fontfile"])
    return str(p if p.is_absolute() else MYVOICE_DIR / p)


# ── Danh sách font chọn được (cho ô "Font chữ" trên web) ─────────────────────
# Font RỜI trong myvoice/fonts (libass thấy qua fontsdir, khớp theo TÊN FAMILY
# đọc từ file) + vài font Windows quen thuộc đủ glyph tiếng Việt.
# KHÔNG đưa Impact vào đây: thiếu glyph tiếng Việt dấu chồng (ộ ữ ế…) → tofu.
_FONT_HE_THONG = [("Arial", "arial.ttf"), ("Arial Black", "ariblk.ttf"),
                  ("Segoe UI", "segoeui.ttf"), ("Tahoma", "tahoma.ttf"),
                  ("Verdana", "verdana.ttf"),
                  ("Times New Roman", "times.ttf"), ("Calibri", "calibri.ttf")]
_FONT_CACHE: list[dict] | None = None


def danh_sach_font() -> list[dict]:
    """→ [{"ten": family, "file": đường dẫn hoặc "", "he_thong": bool}]
    — font rời trong kho đứng trước, font Windows đứng sau."""
    global _FONT_CACHE
    if _FONT_CACHE is not None:
        return _FONT_CACHE
    out = []
    try:
        from PIL import ImageFont
        for p in sorted(FONT_DIR.glob("*.*")):
            if p.suffix.lower() not in (".ttf", ".otf"):
                continue
            try:
                fam = ImageFont.truetype(str(p), 40).getname()[0]
            except Exception:
                fam = p.stem
            out.append({"ten": fam, "file": str(p), "he_thong": False})
    except Exception:
        pass
    windir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    for ten, f in _FONT_HE_THONG:
        p = windir / f
        out.append({"ten": ten, "file": str(p) if p.is_file() else "",
                    "he_thong": True})
    _FONT_CACHE = out
    return out


def ap_font(k: dict, font: str) -> dict:
    """Đè font của một kiểu bằng font người dùng chọn (giữ nguyên mọi thứ khác).
    Tìm được file font thì thay luôn fontfile để phần ĐO CHỮ (hộp hopbo) đúng."""
    if not font:
        return k
    k = {**k, "font": font}
    for f in danh_sach_font():
        if f["ten"].lower() == font.lower() and f["file"]:
            k["fontfile"] = f["file"]
            break
    return k


def ap_mau(k: dict, mau: str) -> dict:
    """Đè MÀU CHỮ của kiểu ('FFD700' hoặc '#FFD700'; rỗng/sai dạng = giữ màu
    gốc). Chỉ đổi mau_chu — viền/bóng/nền/màu nổi bật karaoke giữ nguyên."""
    mau = (mau or "").strip().lstrip("#")
    if len(mau) != 6:
        return k
    return {**k, "mau_chu": mau.upper()}


def ap_cochu(k: dict, cochu) -> dict:
    """PHÓNG TO / THU NHỎ chữ của kiểu theo % (100 hoặc rỗng = giữ nguyên).

    Nhân cả viền/bóng/nhoè/độ lệch glitch theo cùng tỉ lệ nên dáng chữ không
    đổi, chỉ to nhỏ đi; đồng thời RÚT trần ký tự/dòng theo tỉ lệ NGƯỢC — chữ to
    hơn thì ít ký tự lọt một dòng hơn, không rút là chữ tràn ra mép khung.
    Kiểu để max_chars = 0 (theo số người dùng đặt) lấy 50 làm bề rộng chuẩn,
    nhưng chỉ khi thật sự đổi cỡ — để 100% giữ nguyên hành vi cũ.
    """
    try:
        pct = float(str(cochu).strip())
    except (TypeError, ValueError):
        return k
    if not 50 <= pct <= 200 or round(pct) == 100:
        return k
    ti = pct / 100
    k = {**k, "size": max(8, round(k["size"] * ti)), "ti_co": ti}
    for kh in ("vien", "vien2", "bong", "lech"):
        if k.get(kh):
            k[kh] = max(1, round(k[kh] * ti))
    if k.get("blur"):
        k["blur"] = round(k["blur"] * ti, 1)
    k["max_chars"] = max(8, round((k["max_chars"] or 50) / ti))
    return k


# ── Đo chữ (chỉ kiểu hopbo cần, để tính bề rộng khung nền) ───────────────────
def _text_width(text: str, k: dict) -> float:
    try:
        from PIL import ImageFont
        return ImageFont.truetype(_fontfile(k), k["size"]).getlength(text)
    except Exception:
        return len(text) * k["size"] * 0.52


def _line_metrics(k: dict) -> tuple[int, int]:
    try:
        from PIL import ImageFont
        return ImageFont.truetype(_fontfile(k), k["size"]).getmetrics()
    except Exception:
        return int(k["size"] * 0.9), int(k["size"] * 0.25)


def _rounded_rect_path(x0, y0, x1, y1, r) -> str:
    """Lệnh vẽ ASS (\\p1) cho hình chữ nhật bo 4 góc — như video_gansub."""
    x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
    r = int(max(0, min(r, (x1 - x0) // 2, (y1 - y0) // 2)))
    return (f"m {x0 + r} {y0} "
            f"l {x1 - r} {y0} b {x1} {y0} {x1} {y0} {x1} {y0 + r} "
            f"l {x1} {y1 - r} b {x1} {y1} {x1} {y1} {x1 - r} {y1} "
            f"l {x0 + r} {y1} b {x0} {y1} {x0} {y1} {x0} {y1 - r} "
            f"l {x0} {y0 + r} b {x0} {y0} {x0} {y0} {x0 + r} {y0}")


def _ass_ts(sec: float) -> str:
    if sec < 0:
        sec = 0
    cs = int(round(sec * 100))
    h, cs = divmod(cs, 360_000)
    m, cs = divmod(cs, 6_000)
    s, cs = divmod(cs, 100)
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


# ── Chia từ + chia mốc giờ từng từ ───────────────────────────────────────────
def _tach_tu(cue: str) -> list[tuple[str, bool]]:
    """'dòng1\\ndòng2' → [(từ, có_xuống_dòng_SAU_từ_này)] — giữ cấu trúc dòng."""
    out = []
    lines = [l for l in cue.split("\n") if l.strip()]
    for li, line in enumerate(lines):
        ws = line.split()
        for wi, w in enumerate(ws):
            out.append((w, wi == len(ws) - 1 and li < len(lines) - 1))
    return out


def _moc_tu(words, st: float, en: float) -> list[tuple[float, float]]:
    """Chia [st, en] cho từng từ theo độ dài từ → [(t_bắt_đầu, t_kết_thúc)]."""
    tong = sum(max(1, len(w)) for w, _ in words) or 1
    dur = max(0.01, en - st)
    moc, t, acc = [], st, 0
    for w, _ in words:
        acc += max(1, len(w))
        t2 = st + dur * acc / tong
        moc.append((t, t2))
        t = t2
    if moc:
        moc[-1] = (moc[-1][0], en)
    return moc


# ── Phần đầu file .ass ───────────────────────────────────────────────────────
def _header(k: dict, play_w: int, play_h: int, margin_v: int) -> str:
    if k["hieuung"] == "karaoke":
        # \k tô từ Secondary (chưa đọc) sang Primary (đã đọc).
        primary, secondary = _rgb_style(k["mau_noibat"]), _rgb_style(k["mau_chu"])
    else:
        primary = secondary = _rgb_style(k["mau_chu"])
    if int(k["borderstyle"]) == 3:        # khối nền đặc: màu khối nằm ở OutlineColour
        outline_c, back_c = _rgb_style(k["mau_nen"]), _rgb_style("000000", "FF")
    else:
        outline_c = _rgb_style(k["mau_vien"])
        back_c = _rgb_style(k["mau_bong"], "6E")      # bóng đen mờ, không đặc
    bold = -1 if k["bold"] else 0
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {play_w}
PlayResY: {play_h}
ScaledBorderAndShadow: yes
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, \
BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, \
BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,{k['font']},{k['size']},{primary},{secondary},{outline_c},{back_c},\
{bold},0,0,0,100,100,0,0,{k['borderstyle']},{k['vien']},{k['bong']},2,20,20,{margin_v},1
Style: Box,{k['font']},{k['size']},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,\
0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


# ── Từng hiệu ứng ────────────────────────────────────────────────────────────
def _ev_tinh(out, k, cue, st, en, extra):
    body = cue.replace("\n", "\\N")
    out.append(f"Dialogue: 1,{_ass_ts(st)},{_ass_ts(en)},Sub,,0,0,0,,{extra}{body}\n")


def _ev_hopbo(out, k, cue, st, en, extra, play_w, play_h, margin_v):
    ascent, descent = _line_metrics(k)
    line_h = ascent + descent
    cx = play_w / 2
    text_bottom = play_h - margin_v
    lines = cue.split("\n")
    w = max(_text_width(ln, k) for ln in lines)
    # Chữ phóng to thì lề/bo góc của hộp phải dãn theo, không thì hộp bó sát
    # chữ trông như thiếu chỗ thở.
    ti = float(k.get("ti_co") or 1)
    pad_x, pad_y = BOX_PAD_X * ti, BOX_PAD_Y * ti
    x0, x1 = cx - w / 2 - pad_x, cx + w / 2 + pad_x
    y1 = text_bottom + pad_y
    y0 = text_bottom - line_h * len(lines) - pad_y
    path = _rounded_rect_path(x0, y0, x1, y1, BOX_RADIUS * ti)
    a, b = _ass_ts(st), _ass_ts(en)
    out.append(
        f"Dialogue: 0,{a},{b},Box,,0,0,0,,"
        f"{{\\p1\\pos(0,0)\\c{_rgb_tag(k['mau_nen'])}\\alpha&H{k['nen_alpha']}&"
        f"\\bord0\\shad0}}{path}{{\\p0}}\n")
    out.append(f"Dialogue: 1,{a},{b},Sub,,0,0,0,,{extra}"
               + "\\N".join(lines) + "\n")


def _ev_glitch(out, k, cue, st, en, extra, margin_v):
    """Glitch tách màu kiểu CapCut/TikTok: chữ chính + 2 bản LỆCH màu đỏ/xanh
    hai phía chéo nhau.

    Bản lệch dịch chỗ bằng MARGIN của từng event (đè lên margin của style):
    canh giữa dưới nên lệch ngang = (trái−phải)/2, lệch dọc = đổi MarginV.
    Không dùng toạ độ tuyệt đối nên xuống dòng/canh giữa vẫn như thường."""
    body = cue.replace("\n", "\\N")
    a, b = _ass_ts(st), _ass_ts(en)
    d = int(k["lech"])
    mau = (list(k["nhieu_mau"]) + ["FF2E4C", "00E5FF"])[:2]     # đỏ + xanh lơ
    # MỖI bản một layer riêng: event cùng layer trùng giờ bị libass đẩy lên
    # tránh đè nhau (collision) — khác layer thì chồng đúng chỗ như ý.
    for lop, (m, dx, dy) in enumerate([(mau[0], -d, d), (mau[1], d, -d)]):
        ml, mr = max(1, 20 + dx), max(1, 20 - dx)   # tâm dịch (trái−phải)/2 = dx
        mv = max(1, margin_v - dy)                  # dy dương = tụt xuống
        out.append(f"Dialogue: {lop},{a},{b},Sub,,{ml},{mr},{mv},,"
                   f"{{\\1c{_rgb_tag(m)}\\bord0\\shad0}}{body}\n")
    out.append(f"Dialogue: 2,{a},{b},Sub,,0,0,0,,{extra}{body}\n")


def _ev_viendoi(out, k, cue, st, en, extra):
    """Viền KÉP kiểu tiêu đề phim (vd vàng + viền đỏ + viền đen ngoài cùng).

    ASS chỉ cho MỘT viền mỗi style nên vẽ 3 lớp chồng đúng chỗ: dưới cùng viền
    ngoài (dày = vien + vien2, mang luôn bóng đổ), giữa viền trong, trên cùng
    thân chữ — mỗi lớp một layer để libass không collision-đẩy lệch nhau."""
    body = cue.replace("\n", "\\N")
    a, b = _ass_ts(st), _ass_ts(en)
    out.append(f"Dialogue: 0,{a},{b},Sub,,0,0,0,,"
               f"{{\\bord{int(k['vien']) + int(k['vien2'])}"
               f"\\3c{_rgb_tag(k['mau_vien2'])}}}{body}\n")
    out.append(f"Dialogue: 1,{a},{b},Sub,,0,0,0,,"
               f"{{\\bord{k['vien']}\\3c{_rgb_tag(k['mau_vien'])}\\shad0}}{body}\n")
    out.append(f"Dialogue: 2,{a},{b},Sub,,0,0,0,,{extra}{{\\bord0\\shad0}}{body}\n")


def _ev_karaoke(out, k, cue, st, en, extra):
    words = _tach_tu(cue)
    if not words:
        return
    moc = _moc_tu(words, st, en)
    tong_cs = max(1, int(round((en - st) * 100)))
    parts, acc = [], 0
    for i, ((w, br), (t1, t2)) in enumerate(zip(words, moc)):
        d = (max(1, tong_cs - acc) if i == len(words) - 1
             else max(1, int(round((t2 - t1) * 100))))
        acc += d
        parts.append(f"{{\\k{d}}}{w}")
        if br:
            parts.append("\\N")
        elif i < len(words) - 1:
            parts.append(" ")
    out.append(f"Dialogue: 1,{_ass_ts(st)},{_ass_ts(en)},Sub,,0,0,0,,"
               f"{extra}{''.join(parts)}\n")


def _ev_hienlo(out, k, cue, st, en, extra):
    """Từ hiện dần và Ở LẠI; từ đang đọc đổi màu (+ phóng nhẹ nếu pop)."""
    words = _tach_tu(cue)
    if not words:
        return
    moc = _moc_tu(words, st, en)
    mau = k["nhieu_mau"] or [k["mau_noibat"]]
    pop = "\\fscx125\\fscy125\\t(0,110,\\fscx100\\fscy100)" if k["pop"] else ""
    for i, ((w, _br), (t1, t2)) in enumerate(zip(words, moc)):
        truoc = []
        for wj, brj in words[:i]:
            truoc.append(wj)
            truoc.append("\\N" if brj else " ")
        cur = f"{{\\1c{_rgb_tag(mau[i % len(mau)])}{pop}}}{w}"
        out.append(f"Dialogue: 1,{_ass_ts(t1)},{_ass_ts(t2)},Sub,,0,0,0,,"
                   f"{extra}{''.join(truoc)}{cur}\n")


def _ev_tungtu(out, k, cue, st, en, extra):
    """Mỗi từ một mình trên màn hình, bật to đúng lúc đọc."""
    words = _tach_tu(cue)
    if not words:
        return
    moc = _moc_tu(words, st, en)
    pop = ("{\\fscx70\\fscy70\\t(0,110,\\fscx106\\fscy106)"
           "\\t(110,190,\\fscx100\\fscy100)}" if k["pop"] else "")
    for (w, _br), (t1, t2) in zip(words, moc):
        out.append(f"Dialogue: 1,{_ass_ts(t1)},{_ass_ts(t2)},Sub,,0,0,0,,"
                   f"{extra}{pop}{w}\n")


def write_ass_kieu(cues, cue_times, ass_path: Path, kieu=MACDINH,
                   play_w: int = ASS_PLAY_W, play_h: int = ASS_PLAY_H,
                   margin_v: int = SUB_MARGIN_V) -> Path:
    """Ghi .ass theo kiểu đã chọn. `kieu`: tên kiểu (str) hoặc dict mẫu đã đọc.

    `cues` là chữ ĐÃ xuống dòng sẵn (như write_ass của video_gansub) — người
    gọi tự quyết định trần ký tự/dòng qua chon_max_chars(k, user_max, doc).
    play_w/play_h/margin_v: khung NGANG mặc định; video DỌC truyền
    (1080, 1920, 380) như write_ass của video_gansub.
    """
    k = lay(kieu) if isinstance(kieu, str) else {**GOC, **kieu}
    extra = f"{{\\blur{k['blur']}}}" if k["blur"] else ""
    hu = k["hieuung"]
    out = [_header(k, play_w, play_h, margin_v)]
    for cue, (st, en) in zip(cues, cue_times):
        if k["hoa"]:
            cue = cue.upper()
        if hu == "hopbo":
            _ev_hopbo(out, k, cue, st, en, extra, play_w, play_h, margin_v)
        elif hu == "glitch":
            _ev_glitch(out, k, cue, st, en, extra, margin_v)
        elif hu == "viendoi":
            _ev_viendoi(out, k, cue, st, en, extra)
        elif hu == "karaoke":
            _ev_karaoke(out, k, cue, st, en, extra)
        elif hu == "hienlo":
            _ev_hienlo(out, k, cue, st, en, extra)
        elif hu == "tungtu":
            _ev_tungtu(out, k, cue, st, en, extra)
        else:
            _ev_tinh(out, k, cue, st, en, extra)
    ass_path = Path(ass_path)
    ass_path.write_text("".join(out), encoding="utf-8")
    return ass_path


# ── Ảnh xem trước cho giao diện web ──────────────────────────────────────────
# Câu mẫu cố ý có dấu chồng (ộ ữ ế ị) — font nào thiếu glyph tiếng Việt là lộ
# ô vuông ngay trên ảnh xem trước, khỏi đợi burn thật mới biết.
CAU_MAU = "Cuộc sống là những chuyến đi thú vị"
_NEN = "gradients=s=960x540:c0=0x2b3a55:c1=0x10131c:d=3.4"
_NEN_DUPHONG = "color=c=0x1c2431:s=960x540:d=3.4"


def _wrap_tho(text: str, n: int) -> str:
    """Xuống dòng CÂN ĐỐI cho câu mẫu (chỉ dùng vẽ ảnh; burn thật có
    wrap_sentence): chia 2 dòng tại ranh giới từ gần giữa nhất — tránh cảnh
    một từ lẻ loi rơi xuống dòng dưới trong ảnh xem trước."""
    if n <= 0 or len(text) <= n:
        return text
    words = text.split()
    best, lech = None, 10 ** 9
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        if abs(len(a) - len(b)) < lech and len(a) <= n and len(b) <= n:
            best, lech = f"{a}\n{b}", abs(len(a) - len(b))
    return best or text


def _cau_mau_theo_dong(k: dict, dong: int) -> str:
    """Câu mẫu bẻ dòng ĐÚNG như burn thật sẽ hiện.

    dong>=2: hai dòng cân đối (như ảnh mẫu trong kho kiểu).
    dong==1: chỉ mẩu ĐẦU — burn thật cắt câu dài thành nhiều lần hiện chữ, mỗi
    lần một dòng, nên vẽ cả câu vào một dòng là ảnh xem trước nói dối.
    """
    cau = _wrap_tho(CAU_MAU, k["max_chars"])
    return cau if dong >= 2 else cau.splitlines()[0]


def ve_mau(k: dict) -> Path | None:
    """Vẽ ảnh xem trước MỘT kiểu (tên file = id của kiểu)."""
    return _ve_anh_kieu(k, k["id"])


def _ve_anh_kieu(k: dict, ten_goc: str, margin_v: int = SUB_MARGIN_V,
                 ca_khung: bool = False, dong: int = 2) -> Path | None:
    """Vẽ ảnh xem trước cho dict kiểu `k` ra ANH_DIR/<ten_goc>.png|webp.

    Vẽ bằng đúng đường burn thật (libass qua ffmpeg) nên ảnh là xem trước
    TRUNG THỰC, không phải mô phỏng CSS.
    ca_khung=False: cắt lấy dải dưới — chỗ phụ đề nằm — cho thẻ chọn gọn mà
    chữ vẫn to. ca_khung=True: giữ NGUYÊN khung 16:9 (xem VỊ TRÍ chữ trên
    màn hình ngang; margin_v đổi được để thử vị trí khác).
    """
    ANH_DIR.mkdir(parents=True, exist_ok=True)
    ext = ".webp" if k["hieuung"] in HIEUUNG_DONG else ".png"
    dest = ANH_DIR / (ten_goc + ext)
    tmp = ANH_DIR / f"_mau_{ten_goc}.ass"
    write_ass_kieu([_cau_mau_theo_dong(k, dong)], [(0.25, 3.15)], tmp, k,
                   margin_v=margin_v)
    if ca_khung:
        kich, vf_them = "768x432", ""
    else:
        kich, vf_them = "960x540", ",crop=960:300:0:240"
    # Khung ngang: nền là khung hình THẬT của video ngang (có viền trang trí)
    # để canh vị trí chuẩn; các trường hợp còn lại nền gradient trừu tượng.
    nen_anh = _nen_ngang() if ca_khung else None
    if nen_anh is not None:
        # ảnh tĩnh lặp thành clip 3.4s cho khớp mốc giờ của câu mẫu
        dau_vao = [["-loop", "1", "-framerate", "14", "-t", "3.4",
                    "-i", nen_anh.name]]
        vf_dau = "scale=768:432,"
    else:
        dau_vao = [["-f", "lavfi", "-i",
                    f"gradients=s={kich}:c0=0x2b3a55:c1=0x10131c:d=3.4"],
                   ["-f", "lavfi", "-i", f"color=c=0x1c2431:s={kich}:d=3.4"]]
        vf_dau = ""                       # máy thiếu gradients thì rơi về nền trơn
    vf = f"{vf_dau}subtitles={tmp.name}{fontsdir_arg(ANH_DIR)}{vf_them}"
    if ext == ".png":
        duoi = ["-ss", "1.7", "-frames:v", "1", "-vf", vf, dest.name]
    else:
        duoi = ["-vf", vf + ",fps=14", "-c:v", "libwebp", "-loop", "0", dest.name]
    ok = False
    for dau in dau_vao:
        r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *dau, *duoi],
                           cwd=str(ANH_DIR))
        if r.returncode == 0:
            ok = True
            break
    try:
        tmp.unlink()
    except OSError:
        pass
    if ok:
        # kiểu vừa đổi tĩnh↔động thì dọn ảnh đuôi cũ kẻo web vớ nhầm bản cũ
        cu = ANH_DIR / (ten_goc + (".png" if ext == ".webp" else ".webp"))
        try:
            cu.unlink()
        except OSError:
            pass
        return dest
    return None


def _nen_ngang() -> Path | None:
    """Khung hình MẪU của video ngang làm nền cho ảnh xem vị trí (768x432).

    Thứ tự nguồn:
      1. nen_ngang.png đặt TAY trong static/kieusub (dùng nguyên trạng).
      2. KHUNG TRANG TRÍ GỐC myvoice/Backbround/khung1.png — sạch, không dính
         chữ nào; phần trong suốt lót nền phẳng tối cho chữ mẫu nổi rõ.
         (nen_ngang.jpg là CACHE tự sinh — khung1.png mới hơn thì vẽ lại.)
      3. Trích từ YOUTUBE.mp4 mới nhất (làm MỜ dải sub cũ — video sub kín
         từ đầu tới cuối) / clip gốc videongang."""
    dest = ANH_DIR / "nen_ngang.jpg"
    khung = MYVOICE_DIR / "Backbround" / "khung1.png"
    tay = ANH_DIR / "nen_ngang.png"
    if tay.is_file():
        return tay
    if dest.is_file():
        try:
            if not khung.is_file() or dest.stat().st_mtime >= khung.stat().st_mtime:
                return dest
        except OSError:
            return dest
    ANH_DIR.mkdir(parents=True, exist_ok=True)
    if khung.is_file():
        try:
            from PIL import Image
            nen = Image.new("RGB", (1920, 1080), (30, 36, 52))
            lop = Image.open(khung).convert("RGBA")
            nen.paste(lop, (0, 0), lop)
            nen.resize((768, 432), Image.LANCZOS).save(dest, quality=90)
            return dest
        except Exception:
            pass
    # Dải MỜ che sub cũ: vùng sub mặc định (MarginV 173, ~2 dòng) trên khung 432.
    che = ("scale=768:432,split[a][b];"
           "[b]crop=768:130:0:275,gblur=sigma=16[c];[a][c]overlay=0:275")
    nguon: list[tuple[Path, str]] = []
    try:
        nguon += [(v, che) for v in
                  sorted((MYVOICE_DIR / "kịch_bản").glob("*/YOUTUBE.mp4"),
                         key=lambda p: p.stat().st_mtime, reverse=True)[:2]]
    except OSError:
        pass
    try:
        nguon += [(v, "scale=768:432") for v in
                  sorted((MYVOICE_DIR / "videongang").rglob("*.mp4"))[:2]]
    except OSError:
        pass
    ANH_DIR.mkdir(parents=True, exist_ok=True)
    for v, vf in nguon:
        for ss in ("90", "1"):            # video/clip quá ngắn thì lùi về giây 1
            r = subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-ss", ss,
                 "-i", str(v.resolve()), "-frames:v", "1", "-vf", vf, dest.name],
                cwd=str(ANH_DIR))
            if r.returncode == 0 and dest.is_file():
                return dest
    return None


def vitri_margin(vitri, play_h: int, macdinh: int) -> int:
    """'% chiều cao tính từ đáy' → MarginV px; rỗng/sai → mặc định của khung."""
    try:
        pct = float(str(vitri).strip())
    except (TypeError, ValueError):
        return macdinh
    if not 1 <= pct <= 60:
        return macdinh
    return round(play_h * pct / 100)


def ve_xemtruoc(kieu_id: str, font: str = "", mau: str = "",
                vitri="", ca_khung: bool = False, cochu="",
                dong: int = 2) -> Path | None:
    """Ảnh xem thử TỔ HỢP kiểu + font + màu + cỡ chữ + số dòng (+ vị trí).

    ca_khung=True → khung ngang 16:9 NGUYÊN VẸN để thấy chữ nằm đâu trên màn
    hình (vitri = % chiều cao từ đáy, rỗng = mặc định 173px ≈ 16%).
    cochu = % phóng to/thu nhỏ chữ, dong = số dòng mỗi lần hiện chữ (1 hoặc 2).
    Không đè gì → trả thẳng ảnh mẫu sẵn có của kiểu. Còn lại render bản riêng
    vào cache xt_<hash> (mỗi tổ hợp chỉ render MỘT lần, lần sau trả ngay)."""
    co = str(cochu or "").strip()
    nguyen_co = (not co) or co in ("100", "100.0")
    dong = 1 if str(dong) in ("1", "1.0") else 2
    k = ap_cochu(ap_mau(ap_font(lay(kieu_id), font), mau), co)
    ext = ".webp" if k["hieuung"] in HIEUUNG_DONG else ".png"
    if not font and not mau and not ca_khung and nguyen_co and dong == 2:
        p = ANH_DIR / (k["id"] + ext)
        return p if p.is_file() else ve_mau(k)
    margin = vitri_margin(vitri, ASS_PLAY_H, SUB_MARGIN_V)
    # Nền thật đổi (tập mới / thay file nen_ngang) thì cache phải vẽ lại →
    # trộn mtime của nền vào khoá cache.
    nen_mt = 0
    if ca_khung:
        nf = _nen_ngang()
        nen_mt = int(nf.stat().st_mtime) if nf else 0
    import hashlib
    key = hashlib.md5(f"{k['id']}|{font}|{mau}|{co}|{dong}|{margin}|{ca_khung}"
                      f"|{nen_mt}".encode("utf-8")).hexdigest()[:12]
    dest = ANH_DIR / (f"xt_{key}" + ext)
    if dest.is_file():
        return dest
    p = _ve_anh_kieu(k, f"xt_{key}", margin_v=margin, ca_khung=ca_khung,
                     dong=dong)
    _don_xemtruoc()
    return p


def _don_xemtruoc(giu: int = 80) -> None:
    """Cache xem thử chỉ giữ `giu` file mới nhất — khỏi phình vô hạn."""
    try:
        xt = sorted(ANH_DIR.glob("xt_*.*"), key=lambda p: p.stat().st_mtime)
        for p in xt[:-giu]:
            p.unlink()
    except OSError:
        pass


def taomau(ep: bool = False, ids: list[str] | None = None) -> int:
    """Vẽ ảnh xem trước cho các kiểu (thiếu mới vẽ; ep=True vẽ lại hết) → số ảnh."""
    n = 0
    for k in danh_sach():
        if ids and k["id"] not in ids:
            continue
        ext = ".webp" if k["hieuung"] in HIEUUNG_DONG else ".png"
        if not ep and (ANH_DIR / (k["id"] + ext)).is_file():
            continue
        if ve_mau(k):
            print(f"🖼  {k['id']}{ext} — {k['ten']}")
            n += 1
        else:
            print(f"⚠️  Không vẽ được ảnh mẫu cho kiểu {k['id']}")
    return n


# ── Ảnh xem trước FONT (cho khu "Font chữ" trong popup chọn kiểu) ─────────────
def _slug_font(ten: str) -> str:
    return "font_" + re.sub(r"[^a-z0-9]+", "-", ten.lower()).strip("-")


def ve_mau_font(ep: bool = False) -> int:
    """Vẽ ảnh xem trước cho từng font (chữ trắng nền tối, 640x200 — cùng tỉ lệ
    16:5 với thẻ kiểu nên giao diện tái dùng nguyên bộ CSS).

    Vẽ bằng ĐÚNG libass sẽ burn — vài font Windows (vd Arial Black) không có
    glyph Việt DỰNG SẴN nhưng libass tự ghép dấu vẫn chuẩn, còn Pillow thì ra
    ô vuông → Pillow chỉ được dùng để ĐO bề rộng chọn cỡ chữ cho vừa khung.
    Rất nhẹ: mỗi font một PNG tĩnh, vẽ MỘT lần rồi thôi."""
    ANH_DIR.mkdir(parents=True, exist_ok=True)
    W, H = 640, 200
    n = 0
    for f in danh_sach_font():
        if not f["file"]:
            continue
        dest = ANH_DIR / (_slug_font(f["ten"]) + ".png")
        if dest.exists() and not ep:
            continue
        size = 44
        try:
            from PIL import ImageFont
            w100 = ImageFont.truetype(f["file"], 100).getlength(CAU_MAU)
            if w100:
                size = max(22, min(58, int(100 * (W - 56) / w100)))
        except Exception:
            pass
        k = {"hieuung": "tinh", "font": f["ten"], "fontfile": f["file"],
             "size": size, "bold": False, "mau_chu": "FFFFFF",
             "vien": 0, "bong": 0}
        tmp = ANH_DIR / "_mau_font.ass"
        write_ass_kieu([CAU_MAU], [(0.2, 3.0)], tmp, k, play_w=W, play_h=H,
                       margin_v=max(10, (H - int(size * 1.3)) // 2))
        r = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
             "-i", f"color=c=0x181E2C:s={W}x{H}:d=3", "-ss", "1",
             "-frames:v", "1",
             "-vf", f"subtitles={tmp.name}{fontsdir_arg(ANH_DIR)}", dest.name],
            cwd=str(ANH_DIR))
        try:
            tmp.unlink()
        except OSError:
            pass
        if r.returncode == 0:
            n += 1
    return n


def danh_sach_font_web() -> list[dict]:
    """danh_sach_font + tên file ảnh xem trước & mtime chống cache (cho web)."""
    out = []
    for f in danh_sach_font():
        p = ANH_DIR / (_slug_font(f["ten"]) + ".png")
        try:
            anh, v = p.name, int(p.stat().st_mtime)
        except OSError:
            anh, v = "", 0
        out.append({**f, "anh": anh, "v": v})
    return out


def taomau_thieu() -> None:
    """Cho server gọi lúc khởi động (trong thread nền) — không bao giờ ném lỗi."""
    try:
        taomau(ep=False)
        ve_mau_font(ep=False)
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser(description="Kho kiểu phụ đề dùng chung myvoice/myvideo.")
    ap.add_argument("--taomau", action="store_true", help="Vẽ ảnh xem trước còn thiếu.")
    ap.add_argument("--ep", action="store_true", help="Vẽ lại cả ảnh đã có.")
    ap.add_argument("--kieu", nargs="*", help="Chỉ vẽ các kiểu này (tên file JSON).")
    args = ap.parse_args()
    if args.taomau:
        n = taomau(ep=args.ep, ids=args.kieu)
        nf = ve_mau_font(ep=args.ep) if not args.kieu else 0
        print(f"✅ Đã vẽ {n} ảnh kiểu + {nf} ảnh font vào {ANH_DIR}")
    else:
        for k in danh_sach():
            dong = "động" if k["hieuung"] in HIEUUNG_DONG else "tĩnh"
            print(f"  {k['thutu']:>2}. {k['id']:<10} {dong}  {k['ten']} — {k['mota']}")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
