# -*- coding: utf-8 -*-
"""🎛 CHỈNH TRƯỚC (18/11/2026) — phần dữ liệu, không kéo FastAPI.

User không muốn chạy ①→④ một mạch rồi mới biết hình/tiếng ra sao: tick một video
ở bảng Kết quả → khung xem trước ngay trên trang để chỉnh PHÓNG TO, DẢI CHE MỜ,
ÂM LƯỢNG tiếng gốc; bấm chạy thử 3 phút đầu (① chậm + SRT → ② dịch → ③ giọng)
rồi chỉnh riêng âm lượng GIỌNG ĐỌC và tiếng gốc, nghe ngay trên video đang xem.

Ba thứ module này giữ:

1. NGUỒN CHỜ (`cho_chinh` trong web_settings.json, server đọc/ghi): file/link vừa
   nạp vào ô Nguồn hiện thành một hàng ở bảng Kết quả dù chưa chạy bước nào.

2. VÙNG CHE theo TỪNG VIDEO (chinh_truoc.json, khoá = tên gốc viết thường như
   steps.tenchinh): {"y0", "y1", "w", "h"} theo PIXEL video, thêm {"x0", "x1"} khi
   lớp che HẸP hơn bề ngang (xem ngang()). Lưu ở đây chứ không
   chỉ ghi <video>_vungsub.json vì lúc chỉnh trước video ① CHƯA có (file đó nằm
   cạnh video ①), và video dài chia đoạn thì mỗi đoạn một cache riêng. Bước ④
   nhận vùng này qua cờ --vung (steps._steps_for), chay_doan chuyển nguyên cờ
   xuống từng đoạn. Trang 🫥 /vungsub lưu/xoá thì cập nhật luôn kho này, kẻo ④
   lấy số cũ đè lên số vừa sửa.

3. BẢN XEM TRƯỚC của file nguồn (web/xemtruoc/<mã>.mp4): 3 phút đầu, cao 540px,
   H.264 + AAC. Nguồn tải về hay là HEVC/AV1/mkv mà trình duyệt không phát được,
   lại nặng vài GB — bản nhỏ này phát được chắc chắn và tua tức thì. Toạ độ dải
   che tính theo TỈ LỆ khung hình nên bản thu nhỏ không làm lệch.

Phóng to / bật tắt che mờ / âm lượng là cài đặt CHUNG sẵn có (zoom, chesub,
gocdb, ttsdb trong web_settings.json) — khung chỉnh trước sửa đúng các khoá đó.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent
KHO_FILE = WEB_DIR / "chinh_truoc.json"
XEM_DIR = WEB_DIR / "xemtruoc"

THU_GIAY = 180                 # "chạy thử 3 phút"
THU_DUOI = "_thu3p"            # đuôi tên clip thử: <tên>_thu3p.mp4
XEM_CAO = 540                  # chiều cao bản xem trước
XEM_GIU = 8                    # giữ bấy nhiêu bản xem trước mới nhất
CHO_MAX = 40                   # số nguồn chờ nhớ tối đa
VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".webm", ".flv", ".avi", ".m4v", ".ts", ".wmv"}

# 🐢 TỐC ĐỘ sau khi làm chậm (20/11/2026, user yêu cầu): khung chỉnh trước có hàng nút
# chọn tốc độ — MỖI TỐC ĐỘ MỘT BẢN THỬ RIÊNG (file mang tag _x0.7 / _x0.8 nên vốn không
# đè nhau): thử 0.7 rồi thử 0.8, chọn lại 0.7 là xem ngay bản đã làm, không tạo lại.
# Đúng các nấc của ô "Tốc độ sau khi làm chậm" ở khối ① (index.html) — test giữ hai nơi khớp.
TOC_DO = ("0.6", "0.7", "0.8", "0.9", "1.0")

_KHOA = threading.Lock()
_KHOA_XEM = threading.Lock()   # mỗi lúc chỉ dựng MỘT bản xem trước (ffmpeg ăn CPU)


def chuan_toc(v, dflt: str = "0.7") -> str:
    """Tốc độ → đúng cách viết của ô chọn ở khối ① ("0.7", "1.0"); nấc lạ trong khoảng
    atempo chịu được (0.5–2) thì viết gọn ("0.75"); không đọc được / ngoài khoảng → dflt."""
    try:
        x = float(str(v).strip().replace(",", "."))
    except (TypeError, ValueError):
        return dflt
    if not 0.5 <= x <= 2.0:
        return dflt
    for t in TOC_DO:
        if abs(float(t) - x) < 1e-9:
            return t
    return f"{x:g}"


# ── Kho vùng che theo từng video ─────────────────────────────────────────────
def _doc() -> dict:
    try:
        d = json.loads(KHO_FILE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _ghi(d: dict) -> None:
    KHO_FILE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def vung(ten: str) -> dict | None:
    """Vùng che đã chỉnh tay cho video `ten` (tên gốc viết thường) → {"y0","y1","w","h"}."""
    v = _doc().get((ten or "").lower())
    if isinstance(v, dict) and all(isinstance(v.get(k), int) for k in ("y0", "y1")):
        return v
    return None


def ngang(v: dict | None) -> tuple[int, int] | None:
    """Khoảng NGANG (x0, x1) của vùng che khi nó HẸP hơn bề ngang video (20/11/2026, user:
    lớp che mờ không nhất thiết phủ hết bề ngang). Không ghi x0/x1 hoặc phủ hết → None
    (= cả bề ngang, như trước giờ)."""
    if not isinstance(v, dict):
        return None
    x0, x1, w = v.get("x0"), v.get("x1"), v.get("w")
    if not (isinstance(x0, int) and isinstance(x1, int)) or x1 - x0 < 2:
        return None
    if x0 <= 0 and isinstance(w, int) and w and x1 >= w:
        return None
    return max(0, x0), x1


def luu_vung(ten: str, y0: int, y1: int, w: int, h: int, x0=None, x1=None) -> dict:
    """x0/x1 (tuỳ chọn): mép trái/phải của lớp che theo pixel video — chỉ ghi khi lớp che
    hẹp hơn bề ngang; phủ hết thì bản ghi y như cũ (chỉ y0/y1/w/h)."""
    v = {"y0": int(y0), "y1": int(y1), "w": int(w), "h": int(h)}
    if x0 is not None and x1 is not None:
        ng = ngang({**v, "x0": int(x0), "x1": int(x1)})
        if ng:
            v["x0"], v["x1"] = ng
    with _KHOA:
        d = _doc()
        d[(ten or "").lower()] = v
        _ghi(d)
    return v


def bo_vung(ten: str) -> None:
    with _KHOA:
        d = _doc()
        if d.pop((ten or "").lower(), None) is not None:
            _ghi(d)


def ghi_cache_vung(video: Path, v: dict, ghi_chu: str) -> bool:
    """Ghi <video>_vungsub.json (chỗ bước ④ và trang 🫥 đọc) cho một video ① ĐÃ CÓ."""
    if not Path(video).is_file():
        return False
    cache = Path(video).with_name(Path(video).stem + "_vungsub.json")
    cu = {}
    try:
        cu = json.loads(cache.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    ng = ngang(v)
    cache.write_text(json.dumps(
        {"y0": v["y0"], "y1": v["y1"], "w": v["w"], "h": v["h"],
         **({"x0": ng[0], "x1": ng[1]} if ng else {}),
         "moc_giay": cu.get("moc_giay", []) if isinstance(cu, dict) else [],
         "ghi_chu": ghi_chu}, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


# ── Nguồn chờ ────────────────────────────────────────────────────────────────
def nguon_hop_le(dong: str, la_link) -> bool:
    """Một dòng ô Nguồn đáng đưa lên bảng: link tải được, hoặc FILE VIDEO có thật
    (gõ dở đường dẫn thì chưa phải file → không lưu rác)."""
    dong = (dong or "").strip().strip('"')
    if not dong:
        return False
    if la_link(dong):
        return True
    p = Path(dong)
    return p.suffix.lower() in VIDEO_EXTS and p.is_file()


def gop_nguon_cho(cu: list, moi: list[str]) -> list[str]:
    """Đẩy các nguồn vừa nạp lên đầu danh sách chờ (bỏ trùng, cắt bớt phần cũ)."""
    out: list[str] = []
    for s in [*moi, *[x for x in (cu or []) if isinstance(x, str)]]:
        s = s.strip().strip('"')
        if s and s not in out:
            out.append(s)
    return out[:CHO_MAX]


# ── Clip gốc 3 phút đầu ──────────────────────────────────────────────────────
# 20/11/2026 (user chốt luồng): chọn một video để 🎛 Chỉnh trước là CẮT NGAY 3 phút
# đầu của file nguồn ra output/<tên>_thu3p.mp4 và cho xem clip gốc đó — chưa nhận
# diện, chưa lồng tiếng gì. Bấm 🧪 mới chạy ①②③ trên CHÍNH clip này (steps.build
# "thu3p" dùng lại clip, không cắt lần hai). Cắt bằng -c copy nên gần như tức thì
# và giữ nguyên chất lượng gốc.
_KHOA_CAT = threading.Lock()


def clip_con_dung(src: Path, clip: Path) -> bool:
    """Clip 3 phút đã cắt còn dùng được: có thật, không rỗng, không cũ hơn file nguồn."""
    try:
        return (Path(clip).is_file() and Path(clip).stat().st_size > 0
                and Path(clip).stat().st_mtime >= Path(src).stat().st_mtime)
    except OSError:
        return False


def lenh_cat(src, clip) -> list[str]:
    """Lệnh ffmpeg cắt 3 phút đầu (một luồng hình + một luồng tiếng, không encode lại)."""
    return ["ffmpeg", "-y", "-loglevel", "error", "-t", str(THU_GIAY), "-i", str(src),
            "-map", "0:v:0", "-map", "0:a:0?", "-c", "copy", str(clip)]


def cat_clip(src: Path, clip: Path) -> bool:
    """Cắt clip gốc 3 phút nếu chưa có (hoặc file nguồn đã đổi). False = không cắt được
    (định dạng không chép thẳng sang mp4 được…) — nơi gọi tự lùi về cách xem khác."""
    src, clip = Path(src), Path(clip)
    if clip_con_dung(src, clip):
        return True
    with _KHOA_CAT:
        if clip_con_dung(src, clip):
            return True
        clip.parent.mkdir(parents=True, exist_ok=True)
        tam = clip.with_name(clip.stem + ".tam.mp4")
        try:
            r = subprocess.run(lenh_cat(src, tam), capture_output=True, timeout=300,
                               creationflags=0x08000000 if sys.platform == "win32" else 0)
            if r.returncode != 0 or not tam.is_file() or tam.stat().st_size == 0:
                return False
            os.replace(tam, clip)
            return True
        except (OSError, subprocess.SubprocessError):
            return False
        finally:
            try:
                tam.unlink()
            except OSError:
                pass


# ── Bản xem trước của file nguồn ─────────────────────────────────────────────
def _ma(src: Path) -> str:
    st = src.stat()
    return hashlib.md5(f"{src.resolve()}|{st.st_size}|{int(st.st_mtime)}|{THU_GIAY}|{XEM_CAO}"
                       .encode("utf-8")).hexdigest()[:16]


def xem_truoc(src: Path) -> Path:
    """Bản xem trước (3 phút đầu, 540p, H.264/AAC) của file nguồn — dựng một lần
    rồi dùng lại; ném RuntimeError kèm lý do nếu ffmpeg không dựng được."""
    src = Path(src)
    XEM_DIR.mkdir(exist_ok=True)
    out = XEM_DIR / f"{_ma(src)}.mp4"
    if out.is_file() and out.stat().st_size > 0:
        return out
    with _KHOA_XEM:
        if out.is_file() and out.stat().st_size > 0:      # luồng khác vừa dựng xong
            return out
        tam = out.with_suffix(".tam.mp4")
        r = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-t", str(THU_GIAY), "-i", str(src),
             "-map", "0:v:0", "-map", "0:a:0?",
             "-vf", f"scale=-2:{XEM_CAO}", "-c:v", "libx264", "-preset", "veryfast",
             "-crf", "27", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
             "-movflags", "+faststart", str(tam)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600,
            creationflags=0x08000000 if sys.platform == "win32" else 0)
        if r.returncode != 0 or not tam.is_file() or tam.stat().st_size == 0:
            try:
                tam.unlink()
            except OSError:
                pass
            raise RuntimeError((r.stderr or "ffmpeg không dựng được bản xem trước").strip()[-300:])
        os.replace(tam, out)
        _don_xem(giu=out)
    return out


def bo_xem_truoc(src) -> bool:
    """Xoá bản xem trước thu nhỏ của `src` (nếu đã dựng) — gọi TRƯỚC khi xoá chính `src`
    (mã bản xem trước tính từ cỡ + giờ sửa của file). Dùng khi 🗑 một video ở bảng Kết quả."""
    try:
        (XEM_DIR / f"{_ma(Path(src))}.mp4").unlink()
        return True
    except OSError:
        return False


def _don_xem(giu: Path | None = None) -> None:
    """Chỉ giữ XEM_GIU bản xem trước mới nhất (mỗi bản ~15–25 MB)."""
    try:
        ds = sorted(XEM_DIR.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return
    for p in ds[XEM_GIU:]:
        if p != giu:
            try:
                p.unlink()
            except OSError:
                pass


# ── dB ↔ thanh kéo (cùng quy ước tab 🔊 Âm thanh) ────────────────────────────
def doc_db(v, lo: int, hi: int, dflt: int) -> int:
    try:
        return max(lo, min(int(float(str(v).strip().replace(",", "."))), hi))
    except (TypeError, ValueError):
        return dflt
