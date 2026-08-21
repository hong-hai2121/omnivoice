# -*- coding: utf-8 -*-
"""Hồ sơ KÊNH của myvideo — quản lý NHIỀU tài khoản đăng bài dễ dàng.

Mỗi tài khoản (một kênh YouTube + một Facebook Page đi cùng nhau) là MỘT thư
mục trong myvideo/kenh/<tên>/ chứa trọn cấu hình + sổ sách của riêng nó:

    myvideo/kenh/
      client_secret.json         ← OAuth client DÙNG CHUNG (một Google Cloud
                                   project phục vụ được nhiều kênh); hồ sơ nào
                                   cần project riêng thì đặt bản riêng trong
                                   thư mục hồ sơ đó — bản riêng thắng bản chung.
      <tên kênh>/
        facebook.json            ← {"page_id": "…", "access_token": "…"} của Page
        token.json               ← token YouTube (KHOÁ vào đúng kênh đã chọn
                                   lúc bấm 🔑 đăng nhập)
        kenh_video_cache.json    ← cache kênh + video YouTube
        da_dang.json             ← sổ "đã đăng Page" (nguồn sự thật Facebook)
        page_cache.json          ← bản đọc Page gần nhất
        cooldown.json            ← mốc tạm ngưng khi chạm hạn mức Meta

Kênh ĐANG DÙNG chọn trên web (khoá `kenh` trong web_settings.json); các script
CLI nhận --kenh, bỏ trống thì tự đọc khoá đó. Đổi kênh không lẫn sổ sách —
mỗi hồ sơ một bộ, thêm kênh mới = thêm một thư mục.

Biên nhận cạnh video (<base>_youtube_upload.json / _facebook_upload.json) ghi
THEO TỪNG KÊNH: {"<tên kênh>": {…}} — video đã lên kênh A vẫn đăng được lên
kênh B, và mỗi kênh không bao giờ đăng trùng chính nó.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent          # myvideo/
KENH_DIR = BASE_DIR / "kenh"
SETTINGS_FILE = BASE_DIR / "web" / "web_settings.json"

# Tên hồ sơ = tên thư mục: chữ/số đầu, sau đó cho thêm cách, gạch, chấm —
# đủ đặt "kenh-phim", "Trung Quoc 2"… mà không mở đường ../ hay ký tự cấm.
_TEN_RE = re.compile(r"^[A-Za-z0-9À-ỹ][A-Za-z0-9À-ỹ _.-]{0,40}$")

_FB_MAU = {
    "_huongdan": ("Điền Page ID và Page access token DÀI HẠN (quyền "
                  "pages_manage_posts + pages_read_engagement) của Page thuộc "
                  "hồ sơ kênh này rồi lưu lại — web sẽ tự mở khoá nút đăng."),
    "page_id": "",
    "access_token": "",
}


def ten_hople(ten) -> bool:
    return bool(ten) and bool(_TEN_RE.match(str(ten)))


def thu_muc(ten: str) -> Path:
    return KENH_DIR / ten


def danh_sach() -> list[str]:
    """Các hồ sơ kênh hiện có (tên thư mục), theo thứ tự tên."""
    try:
        return sorted((p.name for p in KENH_DIR.iterdir()
                       if p.is_dir() and ten_hople(p.name)), key=str.lower)
    except OSError:
        return []


def hien_tai() -> str:
    """Kênh đang chọn trên web — "" nếu chưa chọn/không còn tồn tại.

    Chỉ MỘT hồ sơ mà chưa chọn gì thì dùng luôn hồ sơ đó — đỡ một bước bấm."""
    try:
        ten = (json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
               .get("kenh") or "").strip()
    except (OSError, ValueError):
        ten = ""
    ds = danh_sach()
    if ten in ds:
        return ten
    return ds[0] if len(ds) == 1 else ""


def tao(ten: str) -> str:
    """Tạo hồ sơ kênh mới (thư mục + facebook.json mẫu) → lỗi hoặc ""."""
    if not ten_hople(ten):
        return ("Tên kênh chỉ gồm chữ/số/cách/gạch/chấm, tối đa 41 ký tự "
                "(vd: kenh-phim, TrungQuoc2).")
    d = thu_muc(ten)
    if d.exists():
        return f"Hồ sơ kênh “{ten}” đã có rồi."
    try:
        d.mkdir(parents=True)
        (d / "facebook.json").write_text(
            json.dumps(_FB_MAU, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as e:
        return f"Không tạo được thư mục hồ sơ: {e}"
    return ""


# ── Facebook của một hồ sơ ───────────────────────────────────────────────────
def fb_config(ten: str) -> tuple[str, str]:
    """→ (page_id, access_token) của hồ sơ — chuỗi rỗng nếu chưa điền."""
    try:
        d = json.loads((thu_muc(ten) / "facebook.json").read_text(encoding="utf-8"))
        return (str(d.get("page_id") or "").strip(),
                str(d.get("access_token") or "").strip())
    except (OSError, ValueError):
        return "", ""


def fb_thieu(ten: str) -> str:
    """Vì sao Facebook của hồ sơ CHƯA đăng được — "" là sẵn sàng."""
    if not ten:
        return "chưa chọn hồ sơ kênh nào (tạo/chọn ở đầu khối Đăng bài)"
    pid, tok = fb_config(ten)
    if not (pid and tok):
        return (f"điền page_id + access_token vào "
                f"{(thu_muc(ten) / 'facebook.json')}")
    return ""


# ── YouTube của một hồ sơ ────────────────────────────────────────────────────
def client_secret(ten: str) -> Path:
    """OAuth client cho hồ sơ: bản RIÊNG trong thư mục hồ sơ thắng bản CHUNG."""
    rieng = thu_muc(ten) / "client_secret.json"
    return rieng if rieng.exists() else KENH_DIR / "client_secret.json"


def yt_token(ten: str) -> Path:
    return thu_muc(ten) / "token.json"


def yt_cache(ten: str) -> Path:
    return thu_muc(ten) / "kenh_video_cache.json"


def yt_thieu(ten: str) -> str:
    """Vì sao YouTube của hồ sơ CHƯA đăng được — "" là sẵn sàng."""
    if not ten:
        return "chưa chọn hồ sơ kênh nào (tạo/chọn ở đầu khối Đăng bài)"
    if not client_secret(ten).exists():
        return (f"chưa có client_secret.json — tải OAuth client từ Google Cloud "
                f"Console, đặt vào {KENH_DIR} (dùng chung) hoặc {thu_muc(ten)}")
    if not yt_token(ten).exists():
        return ("chưa đăng nhập kênh này — bấm 🔑 Đăng nhập YouTube "
                "(chọn ĐÚNG kênh của hồ sơ)")
    return ""


# ── Biên nhận THEO KÊNH cạnh video ──────────────────────────────────────────
def doc_bien_nhan(path: Path) -> dict:
    """Biên nhận dạng {tên kênh: {…}}. File thời một-kênh (dict phẳng có
    video_id) được hiểu là của kênh "(cu)" — không nhận nhầm sang kênh mới."""
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(d, dict):
        return {}
    if "video_id" in d:                 # định dạng cũ, trước khi có hồ sơ kênh
        return {"(cu)": d}
    return {k: v for k, v in d.items() if isinstance(v, dict)}


def ghi_bien_nhan(path: Path, ten: str, info: dict) -> None:
    d = doc_bien_nhan(path)
    d[ten] = info
    path.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
