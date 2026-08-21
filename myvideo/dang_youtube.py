# -*- coding: utf-8 -*-
"""Đăng MỘT video đã dựng xong (bước ④) lên kênh YouTube của MỘT HỒ SƠ KÊNH.

Chạy trong hàng đợi đăng của web (mỗi video một tiến trình), hoặc tay:
    venv\\Scripts\\python.exe myvideo\\dang_youtube.py --base "<thư mục>/<tên>_x0.7" [--kenh <tên>]
    venv\\Scripts\\python.exe myvideo\\dang_youtube.py --dangnhap [--doi-kenh] [--kenh <tên>]
(bỏ --kenh = dùng kênh đang chọn trên web — khoá `kenh` của web_settings.json)

Video      : <base>_sub.mp4 trong myvideo/output
Metadata   : <base>_seo.json (nút 📑 SEO trên web) — thiếu thì tiêu đề = tên video
Thumbnail  : <base>_thumb.jpg/png nếu có (nút 🖼 trên web)
Biên nhận  : <base>_youtube_upload.json — ghi THEO KÊNH ({tên: {…}}): kênh đã
             đăng thì KHÔNG đăng lại (thoát 77, hàng đợi hiện "bỏ qua" chứ
             không đỏ), kênh KHÁC vẫn đăng được; giữ video_id/url để tra lại.
Cài đặt    : myvideo/web/web_settings.json (yt_category / yt_privacy / yt_kids /
             yt_ai) — kho riêng myvideo, không đụng cài đặt myvoice.

⚠️ HỒ SƠ KÊNH (nhiều tài khoản): token/cache nằm trong myvideo/kenh/<tên>/
(xem myvideo/kenh_hoso.py). Hồ sơ chưa cấu hình thì thoát 77 kèm hướng dẫn.
Không bao giờ đọc token của myvoice.

Mã thoát: 0 = đã đăng · 77 = bỏ qua có chủ ý (đã đăng rồi / chưa có kênh) ·
2 = lỗi thật (thiếu video, API hỏng...).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]              # …/OmniVoice
VENV_PY = ROOT / "venv" / "Scripts" / "python.exe"
OUTPUT_DIR = ROOT / "myvideo" / "output"
SETTINGS_FILE = ROOT / "myvideo" / "web" / "web_settings.json"

sys.path.insert(0, str(ROOT / "myvideo" / "YOUTUBE"))
sys.path.insert(0, str(ROOT / "myvideo"))
import dang_video_youtube as yt  # noqa: E402
import kenh_hoso  # noqa: E402

# Console Windows hay là cp1252 — ép UTF-8 trước khi in tiếng Việt/emoji.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass

_XTAG_CUOI = re.compile(r"_x\d+(?:\.\d+)?$")


def _log(msg: str, level: str = "info") -> None:
    dau = {"ok": "✅", "warn": "⚠️", "err": "⛔"}.get(level, "·")
    print(f"{dau} {msg}", flush=True)


def ten_hienthi(base: str) -> str:
    """Tên video cho người đọc: phần tên trong `base`, cắt tag _x… cuối."""
    name = base.split("/")[-1]
    m = _XTAG_CUOI.search(name)
    return name[: m.start()] if m else name


def _settings() -> dict:
    try:
        d = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _load_seo(base: str) -> dict:
    try:
        d = json.loads((OUTPUT_DIR / f"{base}_seo.json").read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _tags_of(seo: dict) -> list[str]:
    """Thẻ tag từ SEO (list hoặc chuỗi phẩy) — cắt cho tổng ≤500 ký tự."""
    raw = seo.get("tags") or []
    if isinstance(raw, str):
        raw = [t.strip() for t in raw.split(",")]
    tags, total = [], 0
    for t in raw:
        t = str(t).strip()
        if not t:
            continue
        # Đếm kiểu YouTube: tag có dấu cách bị bọc ngoặc kép (+2), cộng dấu phẩy.
        cost = len(t) + (2 if " " in t else 0) + (1 if tags else 0)
        if total + cost > 500:
            break
        tags.append(t)
        total += cost
    return tags


def chon_kenh(ten: str) -> tuple[str, str]:
    """Chọn hồ sơ kênh cho lượt chạy → (tên đã chốt, lỗi). Trỏ thư viện YT vào
    token/cache của hồ sơ đó."""
    ten = (ten or "").strip() or kenh_hoso.hien_tai()
    if not ten:
        return "", ("chưa chọn hồ sơ kênh nào — tạo/chọn ở khối Đăng bài trên "
                    "web, hoặc chạy kèm --kenh <tên>")
    if ten not in kenh_hoso.danh_sach():
        return "", f"không có hồ sơ kênh “{ten}” trong {kenh_hoso.KENH_DIR}"
    yt.chon_kenh(kenh_hoso.thu_muc(ten), kenh_hoso.client_secret(ten))
    return ten, ""


def dang_mot_video(base: str, kenh: str) -> int:
    kenh, loi = chon_kenh(kenh)
    if loi:
        print(f"⏳ {loi}")
        return 77
    print(f"📡 Hồ sơ kênh: {kenh}")
    thieu = kenh_hoso.yt_thieu(kenh)
    if thieu:
        print(f"⏳ Hồ sơ “{kenh}” chưa đăng YouTube được: {thieu}")
        print("   (Video vẫn nằm chờ — cấu hình xong bấm đăng lại là được.)")
        return 77

    # Biên nhận theo KÊNH: kênh này đã đăng thì thôi, kênh khác không tính.
    receipt = OUTPUT_DIR / f"{base}_youtube_upload.json"
    cu = kenh_hoso.doc_bien_nhan(receipt).get(kenh)
    if cu:
        print(f"⏭ Kênh “{kenh}” đã đăng video này rồi "
              f"({cu.get('url') or 'video ' + str(cu.get('video_id', '?'))}) — bỏ qua.")
        return 77

    video = OUTPUT_DIR / f"{base}_sub.mp4"
    if not video.is_file():
        print(f"⛔ Chưa có video thành phẩm: {video}")
        return 2

    # Đăng nhập bằng token sẵn có, KHÔNG mở trình duyệt — đây là lượt chạy nền.
    if yt.get_credentials(_log, interactive=False) is None:
        print("⏳ Token hết hạn và không tự làm mới được — bấm 🔑 Đăng nhập YouTube rồi đăng lại.")
        return 77

    seo = _load_seo(base)
    title = (seo.get("title") or "").strip() or ten_hienthi(base)
    if len(title) > yt.MAX_TITLE:
        title = title[: yt.MAX_TITLE - 1].rstrip() + "…"
    desc = (seo.get("desc") or "").strip()[: yt.MAX_DESC]

    st = _settings()
    privacy = st.get("yt_privacy") or "schedule"
    publish_at = None
    if privacy == "schedule":
        slot = yt.next_publish_slot()
        publish_at = yt.to_rfc3339(slot)
        print(f"🗓 Khung giờ công chiếu: {slot:%a %d/%m %H:%M}")
        privacy = "private"                 # API: hẹn giờ = private + publishAt

    thumb_path = None
    for duoi in ("_thumb.jpg", "_thumb.png"):     # jpg là bản thumbnail_video.py vẽ
        thumb = OUTPUT_DIR / f"{base}{duoi}"
        if not thumb.is_file():
            continue
        if thumb.stat().st_size <= yt.THUMB_MAX_BYTES:
            thumb_path = str(thumb)
        else:
            _log(f"Thumbnail vượt 2MB ({thumb.stat().st_size // 1024}KB) — đăng không kèm ảnh.", "warn")
        break

    print(f"⬆ {ten_hienthi(base)} · {video.stat().st_size // 1_000_000} MB · «{title}»")
    last_pct = [-10]

    def _tien_do(pct: int) -> None:
        # In theo nấc 10% — mỗi dòng là một mục nhật ký hàng đợi, in dày ngập log.
        if pct >= last_pct[0] + 10:
            print(f"    … {pct}%", flush=True)
            last_pct[0] = pct

    video_id = yt.upload_video({
        "video_path": str(video),
        "title": title,
        "description": desc,
        "tags": _tags_of(seo),
        "category_id": str(st.get("yt_category") or "22"),
        "privacy": privacy,
        "publish_at": publish_at,
        "made_for_kids": bool(st.get("yt_kids")),
        "contains_ai": bool(st.get("yt_ai", True)),
        "thumbnail_path": thumb_path,
    }, _log, _tien_do)

    info = {
        "video_id": video_id,
        "url": f"https://youtu.be/{video_id}",
        "title": title,
        "privacy": privacy if not publish_at else "schedule",
        "publish_at": publish_at or "",
        "uploaded_at": datetime.now().isoformat(timespec="seconds"),
        "base": base,
    }
    try:
        kenh_hoso.ghi_bien_nhan(receipt, kenh, info)
    except OSError as e:
        # Không ghi được biên nhận = lần chạy sau có thể đăng TRÙNG — phải la to.
        _log(f"KHÔNG ghi được biên nhận {receipt.name}: {e} — chạy lại có thể đăng trùng!", "err")
    return 0


def dang_nhap(kenh: str, doi_kenh: bool) -> int:
    kenh, loi = chon_kenh(kenh)
    if loi:
        print(f"⏳ {loi}")
        return 77
    print(f"📡 Hồ sơ kênh: {kenh}")
    if not yt.CLIENT_SECRET_FILE.exists():
        print(f"⏳ Chưa có client_secret.json — tải OAuth client từ Google Cloud "
              f"Console, đặt vào {kenh_hoso.KENH_DIR} (dùng chung) hoặc "
              f"{kenh_hoso.thu_muc(kenh)} (riêng hồ sơ này).")
        return 77
    try:
        # Hạn 5 phút: lượt đăng nhập chạy trong hàng đợi nền, bỏ dở giữa chừng
        # mà không có hạn thì tiến trình treo giữ cổng callback mãi.
        yt.get_credentials(_log, force_new=doi_kenh, login_timeout=300)
        chan, videos = yt.fetch_channel_videos(_log)
    except Exception as e:
        if type(e).__name__ == "WSGITimeoutError":
            print("⛔ Chờ quá 5 phút không thấy bấm 'Cho phép' — bấm nút đăng nhập lại khi sẵn sàng.")
        else:
            print(f"⛔ Đăng nhập lỗi: {e}")
        return 2
    slot = yt.next_publish_slot()
    print(f"✅ Hồ sơ “{kenh}” ↔ kênh: {chan['title']} "
          f"({chan.get('custom_url') or chan['id']}) · {chan['video_count']} video "
          f"· khung giờ trống kế tiếp {slot:%d/%m/%Y %H:%M}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Đăng video myvideo lên kênh YouTube của một hồ sơ kênh")
    ap.add_argument("--base", default="", help="gốc video trong output (vd: '<thư mục>/<tên>_x0.7')")
    ap.add_argument("--kenh", default="",
                    help="hồ sơ kênh trong myvideo/kenh/ (bỏ trống = kênh đang chọn trên web)")
    ap.add_argument("--dangnhap", action="store_true", help="đăng nhập kênh (mở trình duyệt)")
    ap.add_argument("--doi-kenh", action="store_true",
                    help="cùng --dangnhap: bỏ token cũ (có backup), chọn lại kênh")
    args = ap.parse_args()
    if args.dangnhap:
        return dang_nhap(args.kenh, args.doi_kenh)
    if not args.base:
        print("⛔ Thiếu --base (hoặc dùng --dangnhap).")
        return 2
    return dang_mot_video(args.base, args.kenh)


if __name__ == "__main__":
    # Chạy nhầm python ngoài venv thì tự chạy lại bằng python của dự án.
    if VENV_PY.exists() and Path(sys.executable).resolve() != VENV_PY.resolve():
        import subprocess
        raise SystemExit(subprocess.call([str(VENV_PY), *sys.argv], cwd=str(ROOT)))
    raise SystemExit(main())
