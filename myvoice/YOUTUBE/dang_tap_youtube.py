# -*- coding: utf-8 -*-
"""
dang_tap_youtube.py — Đăng video YouTube của MỘT THƯ MỤC TẬP (kịch_bản/NN - ...).

Cầu nối giữa quy trình tổng (scripts/amain_taogiong_gui.py) và lớp gọi API
(dang_video_youtube.py):
  • tìm YOUTUBE.mp4 + thumbnail<NN>.png của tập,
  • xếp giờ đăng vào khung 08:00 / 18:00 còn trống kế tiếp,
  • gọi upload_video rồi ghi kết quả ra youtube_upload.json trong thư mục tập.

youtube_upload.json vừa là BẰNG CHỨNG ĐÃ ĐĂNG (chạy lại quy trình sẽ bỏ qua tập
đó, không đăng trùng lên kênh) vừa là chỗ tra lại link + giờ hẹn của từng tập.

Tiêu đề/mô tả/thẻ tag KHÔNG dựng ở đây mà do bên gọi truyền vào (amain dùng
_seo_copy_blocks — đúng nội dung tab "Copy SEO theo tập"), để cách đặt tiêu đề
chỉ có MỘT nơi quy định.
"""

import json
from datetime import datetime
from pathlib import Path

RECORD_NAME = "youtube_upload.json"   # bản ghi lần đăng, nằm trong thư mục tập
VIDEO_NAME = "YOUTUBE.mp4"            # bản NGANG — chỉ video này lên YouTube
TIKTOK_NAME = "tiktok.mp4"            # bản dọc mồi, đăng TikTok bằng tay

# Cài đặt cho việc ĐĂNG TỰ ĐỘNG (quy trình tổng). Để file riêng, KHÔNG dùng chung
# settings.json của app đăng tay — file đó nhớ cả tiêu đề/mô tả của lần đăng gần
# nhất, trộn vào đây thì mỗi lần đăng tay lại đổi luôn cấu hình chạy tự động.
SETTINGS_FILE = Path(__file__).resolve().parent / "dang_tudong.json"
DEFAULTS = dict(
    category_id="22",        # Người & Blog
    privacy="schedule",      # schedule = riêng tư tới giờ hẹn | public | unlisted
    made_for_kids=False,     # video có phải làm cho trẻ em không
    contains_ai=True,        # khai báo nội dung do AI tạo (kênh dùng giọng TTS)
)
PRIVACY_LABELS = {
    "schedule": "Hẹn giờ (riêng tư tới giờ rồi tự công khai)",
    "public": "Công khai ngay",
    "unlisted": "Không công khai / ai có link",
}


def load_settings() -> dict:
    """Cài đặt đăng tự động; thiếu khoá nào lấy mặc định."""
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {**DEFAULTS, **data}
    except (OSError, ValueError):
        pass
    return dict(DEFAULTS)


def save_settings(data: dict) -> dict:
    """Ghi đè cài đặt đăng tự động (giữ các khoá không truyền vào)."""
    merged = {**load_settings(), **(data or {})}
    SETTINGS_FILE.write_text(json.dumps(merged, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    return merged


def record_path(folder):
    return Path(folder) / RECORD_NAME


def already_uploaded(folder):
    """Bản ghi lần đăng trước của tập (dict); chưa đăng hoặc file hỏng → None."""
    p = record_path(folder)
    if not p.is_file():
        return None
    try:
        rec = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return rec if isinstance(rec, dict) and rec.get("video_id") else None


def find_video(folder):
    """YOUTUBE.mp4 của tập; nhận cả tên cũ *_videodone.mp4. Không có → None."""
    folder = Path(folder)
    p = folder / VIDEO_NAME
    if p.is_file():
        return p
    old = sorted(folder.glob("*_videodone.mp4"))
    return old[0] if old else None


def find_thumbnail(folder, episode):
    """thumbnail<NN>.png (bản NGANG) của tập — bỏ bản '_dọc' vốn dành cho TikTok."""
    folder, ep = Path(folder), str(episode).strip()
    for name in (f"thumbnail{ep}.png", f"thumbnail{ep.lstrip('0') or '0'}.png"):
        p = folder / name
        if p.is_file():
            return p
    return None


def rename_tiktok(folder, when, log):
    """Đổi tên tiktok.mp4 → 'tiktok <ngày giờ YouTube>.mp4'. Trả về Path mới / None.

    Video TikTok là bản MỒI trỏ về bản đầy đủ trên YouTube ("Full ở Mimi audio Số
    N"), nên đăng TikTok phải canh theo lúc bản YouTube lên sóng. Giờ đó chỉ biết
    được SAU khi đăng (mới xếp được khung giờ), nên gắn vào tên file ngay lúc này —
    mở thư mục là thấy, khỏi phải tra lại từng video trên kênh.

    Không có file (chưa bật tạo video TikTok) → bỏ qua im lặng.
    """
    src = Path(folder) / TIKTOK_NAME
    if not src.is_file():
        return None
    # Windows cấm dấu ':' trong tên file → dùng '08h00'.
    dst = src.with_name(f"tiktok {when:%d-%m-%Y %Hh%M}.mp4")
    if dst.exists():
        log(f"⚠️ Đã có {dst.name} → giữ nguyên {src.name}.", "warn")
        return None
    try:
        src.rename(dst)
        log(f"🎞 Video TikTok → {dst.name} (giờ bản YouTube lên sóng).", "info")
        return dst
    except OSError as e:
        log(f"⚠️ Không đổi được tên video TikTok: {e}", "warn")
        return None


def _current_channel_id():
    """Id kênh đang đăng nhập (theo cache) — ghi vào bản ghi để biết video lên kênh nào.

    Một Gmail có thể có nhiều kênh mà token chỉ gắn với đúng một kênh, nên ghi lại
    id giúp phát hiện ngay nếu cả mẻ lỡ lên nhầm kênh.
    """
    try:
        import dang_video_youtube as yt
        return yt.load_video_cache().get("current") or ""
    except Exception:
        return ""


def upload_episode(folder, episode, blocks, log, progress_cb=None):
    """Đăng video của 1 tập, hẹn giờ vào khung trống kế tiếp (08:00 / 18:00).

    blocks: {'title', 'desc', 'tags'} đã chuẩn hoá; 'tags' là chuỗi ngăn dấu phẩy.
    log(msg, level): level dùng chung với dang_video_youtube ('info'/'warn'/'err'/'ok').

    Trả về bản ghi đã lưu (dict), hoặc None nếu BỎ QUA — đã đăng rồi, thiếu video,
    hoặc SEO không hợp lệ; lý do luôn được ghi vào log.
    """
    import dang_video_youtube as yt

    folder = Path(folder)
    ep = str(episode)

    old = already_uploaded(folder)
    if old:
        log(f"♻ Bỏ qua đăng tập {ep} — đã đăng: {old.get('url', '')}", "info")
        return None

    video = find_video(folder)
    if video is None:
        log(f"⚠️ Tập {ep}: không có {VIDEO_NAME} → chưa đăng được.", "warn")
        return None

    title = (blocks.get("title") or "").strip()
    desc = blocks.get("desc") or ""
    tags = [t.strip() for t in (blocks.get("tags") or "").split(",") if t.strip()]
    if not title:
        log(f"⚠️ Tập {ep}: SEO không có tiêu đề → không đăng.", "warn")
        return None
    if len(title) > yt.MAX_TITLE:
        # Cắt cụt tiêu đề rồi vẫn đăng thì video lên kênh mang cái tên hụt — thà bỏ
        # qua để sửa SEO xong đăng lại bằng nút ⑥ ở tab Nhận diện.
        log(f"⚠️ Tập {ep}: tiêu đề {len(title)} ký tự > {yt.MAX_TITLE} → KHÔNG đăng. "
            "Sửa SEO rồi đăng lại.", "warn")
        return None
    if len(desc) > yt.MAX_DESC:
        log(f"⚠️ Tập {ep}: mô tả {len(desc)} ký tự > {yt.MAX_DESC} → cắt bớt phần cuối.",
            "warn")
        desc = desc[:yt.MAX_DESC]

    cfg = load_settings()
    mode = cfg.get("privacy", "schedule")
    # Hẹn giờ ⇒ YouTube bắt buộc để private, tới giờ mới tự công khai. Đây cũng là
    # mức an toàn nhất: video đã lên kênh nhưng chưa ai thấy, còn kịp sửa/xoá.
    publish_local = yt.next_publish_slot() if mode == "schedule" else None
    privacy = "private" if mode == "schedule" else mode

    thumb = find_thumbnail(folder, ep)
    if thumb is None:
        log(f"⚠️ Tập {ep}: không thấy thumbnail{ep}.png — đăng không kèm ảnh bìa.", "warn")

    when = (f"hẹn công khai {publish_local:%d/%m/%Y %H:%M}" if publish_local
            else PRIVACY_LABELS.get(mode, mode))
    log(f"⬆ Đăng tập {ep}: {video.name} → {when}", "info")
    video_id = yt.upload_video({
        "video_path": str(video),
        "title": title,
        "description": desc,
        "tags": tags,
        "category_id": str(cfg.get("category_id") or DEFAULTS["category_id"]),
        "privacy": privacy,
        "publish_at": yt.to_rfc3339(publish_local) if publish_local else None,
        "made_for_kids": bool(cfg.get("made_for_kids", False)),
        "contains_ai": bool(cfg.get("contains_ai", True)),
        "thumbnail_path": str(thumb) if thumb else None,
    }, log, progress_cb or (lambda _p: None))

    # Gắn giờ bản YouTube lên sóng vào tên video TikTok. Chỉ làm được SAU khi đăng
    # vì tới lúc đó mới biết khung giờ nào được xếp. Không hẹn giờ (công khai ngay /
    # unlisted) thì lấy chính thời điểm đăng.
    tiktok = rename_tiktok(folder, publish_local or datetime.now().astimezone(), log)

    rec = {
        "episode": ep,
        "video_id": video_id,
        "url": f"https://youtu.be/{video_id}",
        "title": title,
        "privacy": privacy,
        "publish_at": publish_local.isoformat(timespec="seconds") if publish_local else "",
        "publish_at_text": (publish_local.strftime("%d/%m/%Y %H:%M") if publish_local
                            else PRIVACY_LABELS.get(mode, mode)),
        "uploaded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "video_file": video.name,
        "tiktok_file": tiktok.name if tiktok else "",
        "thumbnail": thumb.name if thumb else "",
        "made_for_kids": bool(cfg.get("made_for_kids", False)),
        "contains_ai": bool(cfg.get("contains_ai", True)),
        "channel_id": _current_channel_id(),
    }
    try:
        record_path(folder).write_text(json.dumps(rec, ensure_ascii=False, indent=1),
                                       encoding="utf-8")
    except OSError as e:
        # Video ĐÃ lên kênh rồi; không ghi được bản ghi thì lần chạy sau sẽ đăng
        # trùng → báo thật to để còn xử lý tay.
        log(f"❌ Tập {ep}: ĐÃ ĐĂNG ({rec['url']}) nhưng KHÔNG ghi được "
            f"{RECORD_NAME}: {e}. Chạy lại có thể đăng TRÙNG!", "err")
    log(f"✅ Tập {ep} đã đăng: {rec['url']} — {rec['publish_at_text']}", "ok")
    return rec
