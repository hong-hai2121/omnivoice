"""
video_doc_khung.py — Dựng video DỌC 1080×1920 từ VIDEO GỐC của bản ngang, KHÔNG ghép
clip dọc (yêu cầu 08/09/2026: tiết kiệm thời gian, bản dọc dùng lại video ngang).

"Video gốc" = YOUTUBE_goc.mp4: đoạn video đã ghép của bản ngang, NGUYÊN cỡ clip, chưa cắt,
chưa dán logo (video_khung.build_video(goc_out=...) xuất thêm ngay trong cùng một lượt ffmpeg;
YOUTUBE_goc.json có "goc": "raw" + "che"). Bản dọc cắt đúng vùng giữa theo pixel GỐC (1:1,
không phóng — user chốt 08/11/2026 "giữ video nguồn gốc không cần phóng to"; bản đầu 08/11
phóng kín dải 1080×1180 thì mờ):
  • ô ✂ che chữ Trung TẮT (mặc định): dải 1080×1080 = cả chiều cao clip, lấy 1080 px giữa.
  • ô ✂ BẬT: dải 1080×852 = bỏ mép trên CAT_TREN_MIN / dưới CAT_DUOI_MIN (watermark + phụ đề
    cháy sẵn) rồi lấy 1080 px giữa.
Tập cũ không có file gốc thì cắt từ YOUTUBE.mp4: bản khung cũ cắt vùng trong khung1 rồi phóng
cho vừa dải, bản toàn màn hình ("layout": "toanman") lấy nguyên khung hình.

Bố cục "Dọc B" (08/11/2026, user chọn sau khi xem mockup — thay bộ khung hoa + thẻ giấy
tiêu đề + thẻ Số + ảnh mèo + nút Đăng ký cũ che mất 62 % màn hình), toạ độ theo bo_cuc(che):
  • NỀN      : chính vùng video phóng kín 1080×1920, làm MỜ + tối NEN_MO_TOI (kiểu TikTok).
  • GIỮA     : dải video đặt giữa màn hình — pixel gốc 1:1.
  • TRÊN     : logo Mimi audio nhỏ góc trái + TIÊU ĐỀ tập chữ trắng viền đen (không thẻ giấy).
  • DƯỚI     : một dòng "Nghe trọn tập tại kênh Mimi audio"; ~1/5 đáy để trống (TikTok/Reels
               đè nút + caption lên đó).
Màu logo lấy theo logo bản ngang đã dùng (YOUTUBE_goc.json), không rõ thì ngẫu nhiên.
Mỗi tập vẽ MỘT lớp phủ PNG trong suốt (ve_lop_tap) rồi một lệnh ffmpeg: video gốc →
nền mờ + dải video → đè lớp PNG → audio (build_video_doc_khung).

Bộ khung tĩnh cũ ở Backbround/khungdoc/ không dùng nữa (để nguyên, không xoá).

Cách dùng:
    python video_doc_khung.py --xem-truoc [THƯ_MỤC] [--che]   # ảnh xem trước 3 màu logo
    python video_doc_khung.py --tap "kịch_bản/K104 - …" [--che]  # dựng facebook.mp4 cho 1 tập
"""

from __future__ import annotations

import json
import random
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

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
                         run_ffmpeg_progress,
                         CAT_TREN_MIN, CAT_DUOI_MIN)

THUMB_DIR = BASE_DIR / "YOUTUBE" / "thumbnail"
FONTS_DIR = BASE_DIR / "fonts"
SCRIPT_DIR = BASE_DIR / "kịch_bản"

W, H = 1080, 1920
# Dải video giữa, rộng kín 1080, KHÔNG phóng (1:1 pixel gốc của clip 1920×1080) → nét bằng clip:
#   không che → cao 1080 (cả chiều cao clip, lấy 1080 px giữa = 56 % bề ngang gốc), dải vuông.
#   che       → cao 852 = chiều cao còn lại sau khi bỏ mép trên 8 % / dưới 13 %.
# (Bản đầu 08/11: 1080×1180 phủ kín → phóng 1,38× → mờ, user bỏ.)
BAND_CAO_FULL = 1080
BAND_CAO_CHE = 852
# Nền = vùng video phủ kín 1080×1920, làm mờ ở cỡ nhỏ NEN_NHO rồi phóng lên (nhanh, mờ đều),
# tối bớt NEN_MO_TOI (0–1) cho chữ nổi.
NEN_NHO = (270, 480)
NEN_MO_TOI = 0.35
# Khối trên (dồn sát mép trên của dải): tiêu đề chữ trắng viền đen cao TIEU_DE_CAO canh giữa,
# logo cao LOGO_H góc trái phía trên tiêu đề.
LOGO_H = 150
TIEU_DE_CAO = 170
TIEU_DE_CO = (64, 40)                                # cỡ chữ thử từ lớn xuống nhỏ (bước 2)
VIEN_CHU = 5                                         # viền đen quanh chữ
# Khối dưới: một dòng kêu gọi, cách đáy dải CTA_CACH.
CTA_TEXT = "Nghe trọn tập tại kênh Mimi audio"
CTA_CACH, CTA_CO = 134, 42
FONT_CHU = "BeVietnamPro-Black.ttf"
# Vùng trong khung1 trên canvas 1920×1080 của BỘ KHUNG CŨ (các màu cùng hình) — dùng khi
# phải CẮT YOUTUBE.mp4 tập cũ thay cho video gốc.
INNER_MACDINH = (346, 120, 1228, 841)
VIEN_CHAM = 72               # đường viền chấm của khung1 cũ nằm sâu bấy nhiêu px trong vùng trong
GOC_NAME = "YOUTUBE_goc.mp4"                         # video gốc trước khi dán logo
LOP_TAP_NAME = "khungdoc_tap.png"                    # lớp phủ đã vẽ cho tập (tạm)

# tên màu → logo cùng màu trong YOUTUBE/thumbnail
MAU = {"tím": "logo tím.png", "xanh": "logo xanh.png", "đỏ": "logo đỏ.png"}

# Ưu tiên GPU (NVENC), tự fallback CPU (libx264) nếu GPU lỗi.
USE_GPU = True
NVENC_CQ = 18
X264_CRF = 18
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


# ── bố cục theo ô ✂ che chữ Trung ─────────────────────────────────────────────
def bo_cuc(che: bool) -> dict:
    """Toạ độ bố cục: dải video cao 852 (che) hay 1080 (không che) đặt GIỮA màn hình; tiêu đề +
    logo dồn lên sát mép trên dải, dòng kêu gọi dưới dải. Trả về dict band / tieu_de / logo / cta_y."""
    cao = BAND_CAO_CHE if che else BAND_CAO_FULL
    y0 = (H - cao) // 2
    tieu_de = (60, y0 - 25 - TIEU_DE_CAO, 1020, y0 - 25)
    return {"band": (0, y0, W, y0 + cao),
            "tieu_de": tieu_de,
            "logo": (40, tieu_de[1] - LOGO_H - 15),
            "cta_y": y0 + cao + CTA_CACH}


def sub_vitri(che: bool) -> str:
    """Vị trí phụ đề dọc (% chiều cao từ đáy, kieusub.vitri_margin): đáy chữ cách đáy dải 36 px
    → nằm TRONG dải video. Không che ≈ 23,8 %, che ≈ 29,7 %."""
    band = bo_cuc(che)["band"]
    return f"{(H - (band[3] - 36)) / H * 100:.1f}"


SUB_VITRI = sub_vitri(False)       # giữ tên cũ cho code ngoài (mặc định = không che)


# ── tiện ích ──────────────────────────────────────────────────────────────────
def _th():
    """Module vẽ thumbnail (ngắt dòng cân đối, logo cắt sát, dán có bóng)."""
    import dien_tieu_de_thumbnail as th
    return th


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    p = FONTS_DIR / name
    if not p.exists():
        raise FileNotFoundError(f"Thiếu font {p}")
    return ImageFont.truetype(str(p), size=size)


def duong_logo(mau: str) -> Path:
    """File logo theo màu; thiếu thì logo.png (hồng)."""
    p = THUMB_DIR / MAU.get(mau, "logo.png")
    return p if p.exists() else THUMB_DIR / "logo.png"


# ── 1) LỚP PHỦ THEO TẬP: logo, tiêu đề, dòng kêu gọi ──────────────────────────
def _ve_tieu_de(d: ImageDraw.ImageDraw, box, title: str) -> None:
    """Tiêu đề chữ trắng viền đen canh giữa box: ngắt dòng cân đối (2 rồi 3 dòng), co cỡ
    chữ từ TIEU_DE_CO[0] xuống TIEU_DE_CO[1] cho vừa; vẫn không vừa thì cắt bớt từ cuối."""
    th = _th()
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    chon = None
    for size in range(TIEU_DE_CO[0], TIEU_DE_CO[1] - 1, -2):
        font = _font(FONT_CHU, size)
        lh = round(size * 1.2)
        for max_lines in (2, 3):
            lines = th.balanced_wrap(d, title, font, bw - 2 * VIEN_CHU, max_lines)
            if lines and lh * len(lines) <= bh:
                chon = (font, lines, lh)
                break
        if chon:
            break
    if not chon:                       # tiêu đề quá dài → cắt bớt từ cuối
        font = _font(FONT_CHU, TIEU_DE_CO[1])
        words = title.split()
        while words and d.textlength(" ".join(words), font=font) > bw * 2.8:
            words.pop()
        lines = th.balanced_wrap(d, " ".join(words) + "…", font, bw, 3) or [" ".join(words)]
        chon = (font, lines, round(TIEU_DE_CO[1] * 1.2))
    font, lines, lh = chon
    y = y0 + (bh - lh * len(lines)) // 2
    for line in lines:
        d.text((x0 + bw / 2, y + lh / 2), line, font=font, anchor="mm",
               fill=(255, 255, 255, 255), stroke_width=VIEN_CHU, stroke_fill=(0, 0, 0, 235))
        y += lh


def ve_lop_tap(mau: str, episode: str, title: str, out_png: Path, log=print,
               che: bool = False) -> Path:
    """Vẽ lớp phủ TRONG SUỐT 1080×1920 cho MỘT tập theo bo_cuc(che): logo màu `mau` góc trái +
    tiêu đề + dòng "Nghe trọn tập…" → out_png. Phần dải video và nền để trống (ffmpeg lót video)."""
    th = _th()
    bc = bo_cuc(che)
    base = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    # logo cùng màu, cắt sát, cao LOGO_H, có bóng mềm
    logo = th.load_logo_cropped(duong_logo(mau))
    logo = logo.resize((round(logo.width * LOGO_H / logo.height), LOGO_H), Image.LANCZOS)
    th.paste_with_shadow(base, logo, bc["logo"])
    d = ImageDraw.Draw(base)
    so = re.sub(r"\D", "", str(episode or ""))
    tieu_de = (title or "").strip() or (f"Mimi audio Số {int(so)}" if so else "Mimi audio")
    _ve_tieu_de(d, bc["tieu_de"], tieu_de)
    d.text((W // 2, bc["cta_y"]), CTA_TEXT, font=_font(FONT_CHU, CTA_CO), anchor="mm",
           fill=(255, 255, 255, 255), stroke_width=4, stroke_fill=(0, 0, 0, 235))
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    base.save(out_png)
    return out_png


# ── 2) THÔNG TIN TẬP + NGUỒN VIDEO GỐC ────────────────────────────────────────
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


def che_cua_tap(folder: Path | None, che: bool | None = None) -> bool:
    """Trạng thái ô ✂ che chữ Trung dùng cho tập: truyền thẳng (`che`) thì theo đó, không thì
    đọc khoá "che" bản ngang đã ghi trong YOUTUBE_goc.json; không có → False (mặc định)."""
    if che is not None:
        return bool(che)
    return bool(_doc_goc_json(folder).get("che", False)) if folder else False


def chon_mau(folder: Path | None = None) -> str:
    """Màu logo bản dọc: cùng màu logo bản ngang (khoá "logo" trong YOUTUBE_goc.json; bản
    khung cũ ghi "frame" = viền khung1 cùng màu), không rõ (logo.png hồng, tập cũ) thì random."""
    if folder:
        goc = _doc_goc_json(folder)
        ten = ((goc.get("logo") or "") + " " + (goc.get("frame") or "")).lower()
        for mau in MAU:
            if mau in ten:
                return mau
    return random.choice(list(MAU))


def nguon_goc(folder: Path, ngang: Path | None = None, che: bool | None = None):
    """(video_nguồn, crop (w, h, x, y) hoặc None, phụ_đề_đã_trong_hình). Ưu tiên YOUTUBE_goc.mp4:
    bản "goc": "raw" (nguyên cỡ clip) → crop đúng cỡ dải (bo_cuc(che)) ở giữa vùng cho phép
    (che: bỏ mép trên CAT_TREN_MIN / dưới CAT_DUOI_MIN; không che: cả khung) = 1:1 không phóng;
    clip nhỏ hơn dải thì crop cả vùng cho phép rồi bên dựng phóng cho vừa. Bản gốc cũ đã cắt →
    None. Không có thì lấy YOUTUBE.mp4 (tập cũ): bố cục toàn màn hình → nguyên khung hình; bộ
    khung cũ → cắt vùng trong khung1."""
    folder = Path(folder)
    meta = _doc_goc_json(folder)
    che = che_cua_tap(folder, che)
    goc = folder / GOC_NAME
    if goc.exists() and goc.stat().st_size > 4096:
        if meta.get("goc") != "raw":
            return goc, None, False
        vw, vh = get_resolution(goc)
        if che:
            tren, duoi = (meta.get("cat") or [CAT_TREN_MIN, CAT_DUOI_MIN])[:2]
        else:
            tren, duoi = 0.0, 0.0
        y0 = int(vh * float(tren)) // 2 * 2
        vung_h = int(vh * (1.0 - float(tren) - float(duoi))) // 2 * 2
        band = bo_cuc(che)["band"]
        bw, bh = band[2] - band[0], band[3] - band[1]
        if vw >= bw and vung_h >= bh:          # đủ lớn → lấy đúng bw×bh ở giữa, 1:1
            return goc, (bw, bh, (vw - bw) // 2 // 2 * 2, (y0 + (vung_h - bh) // 2) // 2 * 2), False
        return goc, (vw, vung_h, 0, y0), False
    cands = [Path(ngang)] if ngang else []
    cands += [folder / "YOUTUBE.mp4"] + sorted(folder.glob("*_videodone.mp4"))
    for v in cands:
        if v and v.exists() and v.stat().st_size > 4096:
            co_sub = (v.with_suffix(".ass").exists() or v.with_suffix(".srt").exists())
            if meta.get("layout") == "toanman":
                return v, None, co_sub            # cả khung hình là video (logo nhỏ góc, ngoài dải cắt)
            vw, vh = get_resolution(v)
            box = meta.get("inner") or list(INNER_MACDINH)
            # Lùi vào VIEN_CHAM: đường viền CHẤM của khung1 cũ nằm sâu ~70 px trong vùng
            # trong (đo 08/09/2026), cắt sát vùng trong là lộ đường chấm trong bản dọc.
            bx, by = box[0] + VIEN_CHAM, box[1] + VIEN_CHAM
            bw, bh = box[2] - 2 * VIEN_CHAM, box[3] - 2 * VIEN_CHAM
            kx, ky = vw / 1920, vh / 1080
            crop = (round(bw * kx) // 2 * 2, round(bh * ky) // 2 * 2,
                    round(bx * kx), round(by * ky))                  # w, h, x, y
            return v, crop, co_sub
    return None, None, False


# ── 3) DỰNG VIDEO ─────────────────────────────────────────────────────────────
def build_video_doc_khung(audio_file: Path, source_video: Path, output: Path,
                          overlay_png: Path, *, crop=None, cover_png: Path | None = None,
                          log=print, progress=None, skip_existing: bool = False,
                          che: bool = False) -> Path:
    """Video gốc → nền mờ tối phủ kín 1080×1920 + chính nó trong dải video (bo_cuc(che)) → đè lớp
    PNG (logo + tiêu đề + dòng kêu gọi) → ghép audio.
    crop = (w, h, x, y) cắt trước khi dùng (vùng giữa của video gốc nguyên cỡ, hoặc vùng trong
    khung1 khi nguồn là YOUTUBE.mp4 bộ khung cũ). Nguồn đã cắt đúng cỡ dải thì KHÔNG phóng (1:1).
    cover_png = thumbnail dọc đè lên frame đầu (ảnh bìa Facebook/TikTok) — như video_doc."""
    audio_file, source_video, output = Path(audio_file), Path(source_video), Path(output)
    overlay_png = Path(overlay_png)
    if skip_existing and output.exists() and output.stat().st_size > 0:
        log(f"♻ Video dọc đã có → bỏ qua dựng lại: {output.name}")
        return output
    for p, ten in ((audio_file, "audio"), (source_video, "video gốc"), (overlay_png, "lớp phủ")):
        if not p.exists():
            raise RuntimeError(f"Không tìm thấy {ten}: {p}")
    cover_png = Path(cover_png) if cover_png else None
    if cover_png and not cover_png.exists():
        log(f"[Cảnh báo] Không tìm thấy ảnh bìa, bỏ qua: {cover_png}")
        cover_png = None
    audio_dur = get_duration(audio_file)
    band = bo_cuc(che)["band"]
    bw, bh = band[2] - band[0], band[3] - band[1]

    log(f"Bố cục dọc : {W}x{H} — dải video {bw}x{bh} tại y={band[1]} (pixel gốc, không phóng"
        f"{', ✂ che chữ Trung' if che else ''}), nền là chính video làm mờ (tối {NEN_MO_TOI:.0%}), "
        f"logo + tiêu đề trên, dòng kêu gọi dưới")
    if crop and (crop[0], crop[1]) == (bw, bh):
        cach = f" (cắt {crop[0]}x{crop[1]} tại x={crop[2]} y={crop[3]}, 1:1 không phóng)"
    elif crop:
        cach = f" (cắt {crop[0]}x{crop[1]} tại x={crop[2]} y={crop[3]} rồi phóng cho vừa dải)"
    else:
        cach = " (dùng nguyên khung hình, phóng/cắt cho vừa dải)"
    log(f"Video nguồn: {source_video.name}{cach}")
    log(f"Lớp phủ    : {overlay_png.name}")
    log(f"Audio      : {audio_file.name}  ({audio_dur:.2f}s)")
    if cover_png:
        log(f"Ảnh bìa    : {cover_png.name} (đè frame đầu)")
    log(f"Đầu ra     : {output}")

    src = "[0:v]" + (f"crop={crop[0]}:{crop[1]}:{crop[2]}:{crop[3]}," if crop else "")
    filt = (
        f"{src}split[nen][vid];"
        # nền: thu nhỏ → làm mờ → phóng kín 1080×1920 → tối bớt
        f"[nen]scale={NEN_NHO[0]}:{NEN_NHO[1]}:force_original_aspect_ratio=increase,"
        f"crop={NEN_NHO[0]}:{NEN_NHO[1]},boxblur=12:2,scale={W}:{H}:flags=bicubic,"
        f"drawbox=c=black@{NEN_MO_TOI:g}:t=fill,setsar=1[bg];"
        # dải video: nguồn đã cắt đúng bw×bh thì scale là no-op (1:1); nguồn khác cỡ thì
        # phóng/thu (lanczos) phủ kín rồi cắt giữa
        f"[vid]scale={bw}:{bh}:force_original_aspect_ratio=increase:flags=lanczos,crop={bw}:{bh},setsar=1[v];"
        f"[bg][v]overlay={band[0]}:{band[1]}:shortest=1[b1];"
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
               "-loop", "1", "-i", str(overlay_png),               # 1: lớp phủ
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
                                       label="Dựng video dọc", progress=progress)
    if rc != 0 and use_gpu:
        log("GPU lỗi, chuyển sang CPU (libx264)...")
        rc, err_tail = run_ffmpeg_progress(build_cmd(False), audio_dur, log,
                                           label="Dựng video dọc", progress=progress)
    if rc != 0:
        raise RuntimeError(f"ffmpeg lỗi:\n{err_tail}")
    final_dur = get_duration(output)
    size_mb = output.stat().st_size / 1024 / 1024
    log(f"Hoàn tất! Thời lượng {final_dur:.2f}s — {size_mb:.1f} MB — {output}")
    return output


def dung_cho_tap(folder: Path, audio: Path | None = None, output: Path | None = None, *,
                 mau: str | None = None, cover_png: Path | None = None, caption: str | None = None,
                 log=print, progress=None, skip_existing: bool = False,
                 che_chu: bool | None = None) -> tuple[Path, bool]:
    """Trọn gói cho 1 thư mục tập: chọn nguồn gốc → vẽ lớp phủ theo tập → dựng.
    caption = chữ TikTok 'Mimi audio Số N' (nguồn số tập dự phòng khi tên thư mục không có số).
    che_chu = ô ✂ che chữ Trung (None → theo YOUTUBE_goc.json của bản ngang, không có → tắt).
    Trả về (facebook.mp4, phụ_đề_đã_có_trong_hình)."""
    folder = Path(folder)
    audio = Path(audio) if audio else folder / "output.wav"
    output = Path(output) if output else folder / "facebook.mp4"
    che = che_cua_tap(folder, che_chu)
    src, crop, co_sub = nguon_goc(folder, che=che)
    if src is None:
        raise RuntimeError("chưa có video ngang / video gốc trong thư mục tập để dựng bản dọc")
    mau = mau or chon_mau(folder)
    info = thong_tin_tap(folder, caption)
    lop = ve_lop_tap(mau, info["episode"], info["title"], folder / LOP_TAP_NAME, log=log, che=che)
    log(f"🖼 Lớp phủ dọc: logo {mau}, tập {info['episode']}, tiêu đề: {info['title'][:60]}")
    out = build_video_doc_khung(audio, src, output, lop, crop=crop, cover_png=cover_png,
                                log=log, progress=progress, skip_existing=skip_existing, che=che)
    return out, co_sub


# ── 4) ẢNH XEM TRƯỚC cho web ──────────────────────────────────────────────────
def _khung_hinh_mau(tmp_dir: Path, che: bool = False) -> Image.Image | None:
    """Một khung hình video để xem trước: lấy từ tập gần nhất có video, không có thì từ một
    clip trong kho videongang/ (che → bỏ mép trên/dưới như bản dọc thật)."""
    try:
        import amain_taogiong_gui as gui
        folders = sorted(gui.episode_dirs(), key=lambda p: p.stat().st_mtime, reverse=True)
    except Exception:
        folders = sorted((p for p in SCRIPT_DIR.iterdir() if p.is_dir()),
                         key=lambda p: p.stat().st_mtime, reverse=True) if SCRIPT_DIR.exists() else []
    nguon: list[tuple[Path, str]] = []
    for f in folders:
        src, crop, _ = nguon_goc(f, che=che)
        if src is not None:
            nguon.append((src, f"crop={crop[0]}:{crop[1]}:{crop[2]}:{crop[3]}" if crop else "null"))
    try:
        if che:
            con = 1.0 - CAT_TREN_MIN - CAT_DUOI_MIN
            vf = f"crop=iw:ih*{con:.4f}:0:ih*{CAT_TREN_MIN:g}"
        else:
            vf = "null"
        nguon += [(v, vf) for v in sorted((BASE_DIR / "videongang").rglob("*.mp4"))[:3]]
    except Exception:
        pass
    out = tmp_dir / "khungdoc_mau_frame.jpg"
    for src, vf in nguon:
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


def xem_truoc(mau: str, out_path: Path, force: bool = False, log=print, che: bool = False) -> Path:
    """Ảnh JPEG 540×960 xem trước bố cục dọc (bo_cuc(che)) với logo màu `mau`, tiêu đề mẫu + một
    khung hình video thật (không có thì nền màu). Có sẵn và code bố cục chưa đổi thì trả ngay."""
    out_path = Path(out_path)
    me = Path(__file__)
    if out_path.exists() and not force \
            and out_path.stat().st_mtime >= me.stat().st_mtime:
        return out_path
    tmp = Path(tempfile.gettempdir())
    lop = ve_lop_tap(mau, "104", "Màn Lật Kèo Đầy Nghẹt Thở Của Nữ Tướng Quân Phản Diện",
                     tmp / f"khungdoc_xemtruoc_{mau}.png", log=log, che=che)
    band = bo_cuc(che)["band"]
    bw, bh = band[2] - band[0], band[3] - band[1]
    frame = _khung_hinh_mau(tmp, che)
    if frame is not None:
        nen = ImageOps.fit(frame.convert("RGB"), NEN_NHO, method=Image.LANCZOS)
        nen = nen.filter(ImageFilter.GaussianBlur(6)).resize((W, H), Image.BICUBIC)
        base = Image.blend(nen, Image.new("RGB", (W, H), "black"), NEN_MO_TOI).convert("RGBA")
        base.alpha_composite(ImageOps.fit(frame, (bw, bh), method=Image.LANCZOS), dest=(band[0], band[1]))
    else:
        base = Image.new("RGBA", (W, H), (60, 44, 60, 255))
        d = ImageDraw.Draw(base)
        d.rectangle(band, fill=(120, 80, 110, 255))
        d.text(((band[0] + band[2]) // 2, (band[1] + band[3]) // 2), "video gốc của bản ngang",
               font=_font("Baloo2-ExtraBold.ttf", 48), fill=(255, 255, 255, 255), anchor="mm")
    base.alpha_composite(Image.open(lop).convert("RGBA"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    base.convert("RGB").resize((540, 960), Image.LANCZOS).save(out_path, "JPEG", quality=86)
    return out_path


# ── CLI ───────────────────────────────────────────────────────────────────────
def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Video dọc từ video gốc của bản ngang (nền mờ + logo + tiêu đề).")
    ap.add_argument("--xem-truoc", nargs="?", const=str(BASE_DIR / "Backbround" / "khungdoc" / "xemtruoc"),
                    default=None, metavar="THƯ_MỤC",
                    help="Xuất ảnh xem trước 3 màu logo (mặc định Backbround/khungdoc/xemtruoc).")
    ap.add_argument("--tap", metavar="THƯ_MỤC", help="Dựng facebook.mp4 cho một thư mục tập.")
    ap.add_argument("--mau", choices=list(MAU), help="Ép màu logo (mặc định theo logo bản ngang / random).")
    ap.add_argument("--che", action="store_true",
                    help="✂ Che chữ Trung: dải 1080×852 bỏ mép trên/dưới (mặc định: theo YOUTUBE_goc.json / tắt).")
    args = ap.parse_args(argv)
    che = True if args.che else None
    if args.xem_truoc:
        d = Path(args.xem_truoc)
        for mau in MAU:
            print("→", xem_truoc(mau, d / f"xemtruoc {mau}{' che' if args.che else ''}.jpg",
                                 force=True, che=bool(args.che)))
    if args.tap:
        out, co_sub = dung_cho_tap(Path(args.tap), mau=args.mau, che_chu=che)
        print("✅", out, "(phụ đề đã có trong hình)" if co_sub else "")
    if not (args.xem_truoc or args.tap):
        ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
