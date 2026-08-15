# -*- coding: utf-8 -*-
"""
dang_tap_youtube.py — Đăng video YouTube của MỘT THƯ MỤC TẬP (kịch_bản/NN - ...).

Cầu nối giữa quy trình tổng (scripts/amain_taogiong_gui.py) và lớp gọi API
(dang_video_youtube.py):
  • tìm YOUTUBE.mp4 + thumbnail<NN>.png của tập,
  • xếp giờ đăng vào khung 08:00 / 18:00 còn trống kế tiếp,
  • gọi upload_video rồi ghi kết quả ra youtube_upload.json trong thư mục tập,
  • đăng kèm YouTube Short (short.mp4) hẹn sau bản chính 1 giờ — xem upload_short.

youtube_upload.json vừa là BẰNG CHỨNG ĐÃ ĐĂNG (chạy lại quy trình sẽ bỏ qua tập
đó, không đăng trùng lên kênh) vừa là chỗ tra lại link + giờ hẹn của từng tập.

Tiêu đề/mô tả/thẻ tag KHÔNG dựng ở đây mà do bên gọi truyền vào (amain dùng
_seo_copy_blocks — đúng nội dung tab "Copy SEO theo tập"), để cách đặt tiêu đề
chỉ có MỘT nơi quy định.
"""

import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

RECORD_NAME = "youtube_upload.json"   # bản ghi lần đăng, nằm trong thư mục tập
VIDEO_NAME = "YOUTUBE.mp4"            # bản NGANG — chỉ video này lên YouTube
TIKTOK_NAME = "tiktok.mp4"            # bản dọc mồi, đăng TikTok bằng tay
FACEBOOK_NAME = "facebook.mp4"        # bản dọc mồi, đăng Facebook bằng tay
# Hai bản DỌC đều đăng tay, đều được đổi tên sau khi đăng — xem rename_doc().
DOC_LABELS = {TIKTOK_NAME: "TikTok", FACEBOOK_NAME: "Facebook"}

# YouTube Short: bản dọc ≤ 2:50 cắt từ TikTok (xem scripts/video_short.py), đăng TỰ
# ĐỘNG ngay sau video chính. Để short lên sau bản đầy đủ SHORT_DELAY_HOURS giờ thì
# người xem short bấm vào link mô tả là bản full đã có sẵn trên kênh.
SHORT_NAME = "short.mp4"
SHORT_DELAY_HOURS = 1
SHORT_HASHTAG = "#Shorts"

BAD_CHARS = '<>:"/\\|?*'   # Windows cấm các ký tự này trong tên file
MAX_STEM = 120            # cắt tên cho đường dẫn không chạm giới hạn 260 của Windows

# Chốt chống đăng trùng TÊN TRUYỆN (xem upload_episode). Chỉ tắt khi thật sự muốn
# hai video cùng tên trên kênh — đặt biến môi trường này =1 trước khi chạy.
ALLOW_DUP_TITLE_ENV = "OMNI_ALLOW_DUP_TITLE"
ALLOW_DUP_TITLE = os.environ.get(ALLOW_DUP_TITLE_ENV, "").strip().lower() in (
    "1", "true", "yes")

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


def safe_stem(text: str) -> str:
    """Một dòng chữ → phần tên file hợp lệ trên Windows (chưa có đuôi); '' nếu rỗng.

    '|' đổi thành '-' cho còn đọc được ('… Số 12 | Tên truyện' → '… Số 12 - Tên
    truyện'); các ký tự cấm khác bỏ hẳn. Windows cũng không cho tên kết thúc bằng
    '.' hoặc khoảng trắng nên cắt luôn.
    """
    stem = (text or "").replace("|", "-")
    stem = "".join(c for c in stem if c not in BAD_CHARS and c >= " ")
    stem = re.sub(r"\s{2,}", " ", stem).strip()
    if len(stem) > MAX_STEM:
        stem = stem[:MAX_STEM].rstrip()
    return stem.rstrip(". ")


def time_stem(name, when) -> str:
    """Tên theo GIỜ BẢN YOUTUBE LÊN SÓNG: 'facebook 09-08-2026 18h00'.

    Video dọc là bản MỒI trỏ về bản đầy đủ trên YouTube ("Full ở Mimi audio Số
    N"), nên đăng tay phải canh theo lúc bản YouTube lên sóng. Giờ đó chỉ biết
    được SAU khi đăng (mới xếp được khung giờ), nên gắn vào tên file ngay lúc này
    — mở thư mục là thấy, khỏi phải tra lại từng video trên kênh.
    """
    # Windows cấm dấu ':' trong tên file → dùng '18h00'.
    return f"{Path(name).stem} {when:%d-%m-%Y %Hh%M}"


def rename_doc(folder, name, stem, log):
    """Đổi tên video dọc <name> → '<stem>.mp4'. Trả về Path mới / None.

    Không có file (chưa bật tạo video dọc đó) hoặc stem rỗng → bỏ qua im lặng.
    """
    src = Path(folder) / name
    label = DOC_LABELS.get(name, src.stem)
    if not src.is_file() or not stem:
        return None
    dst = src.with_name(f"{stem}.mp4")
    if dst.exists():
        log(f"⚠️ Đã có {dst.name} → giữ nguyên {src.name}.", "warn")
        return None
    try:
        src.rename(dst)
        log(f"🎞 Video {label} → {dst.name}", "info")
        return dst
    except OSError as e:
        log(f"⚠️ Không đổi được tên video {label}: {e}", "warn")
        return None


def short_title(blocks, max_title) -> str:
    """Tiêu đề cho Short: kiểu TikTok ('Full ở Mimi audio Số 12 | …') + '#Shorts'.

    Tiêu đề TikTok dài hơn bản YouTube đúng 'Full ở ' nên có tập vượt mốc 100 ký
    tự dù bản YouTube vẫn lọt. Thử lần lượt từ bản đầy đủ nhất xuống, lấy cái đầu
    tiên vừa — thà mất hashtag còn hơn mất tiêu đề (YouTube nhận Short theo khung
    hình dọc + dưới 3 phút, hashtag chỉ là tín hiệu phụ).
    """
    tiktok = (blocks.get("title_tiktok") or "").strip()
    chinh = (blocks.get("title") or "").strip()
    for ung_vien in (f"{tiktok} {SHORT_HASHTAG}", tiktok,
                     f"{chinh} {SHORT_HASHTAG}", chinh):
        ung_vien = ung_vien.strip()
        if ung_vien and len(ung_vien) <= max_title:
            return ung_vien
    return ""


def short_description(main_url: str, episode: str) -> str:
    """Mô tả Short: câu dẫn về bản full + hashtag. Ngắn gọn vì Shorts chỉ hiện vài dòng."""
    dong = [f"▶ Nghe full tại: {main_url}", ""] if main_url else []
    tags = [SHORT_HASHTAG]
    try:
        import thumbnail_gui as tg
        ep_tag = tg.episode_hashtag(episode)
        tags = ([ep_tag] if ep_tag else []) + [SHORT_HASHTAG] + list(tg.FULL_HASHTAGS)
    except Exception:
        # Thiếu thumbnail_gui thì vẫn đăng được, chỉ là mô tả trơ hashtag mặc định.
        pass
    dong.append(" ".join(tags))
    return "\n".join(dong)


def upload_short(folder, episode, blocks, main_url, publish_local, cfg, log,
                 progress_cb=None):
    """Đăng short.mp4 của tập, hẹn sau video chính SHORT_DELAY_HOURS giờ.

    Trả về dict {'video_id','url','publish_at','publish_at_text'} hoặc None khi bỏ
    qua (không có file / không dựng được tiêu đề). Lỗi API thì ném ra cho bên gọi —
    upload_episode bắt lại để sự cố của Short không kéo đổ bản ghi video chính.

    publish_local=None (đăng công khai ngay / unlisted) → Short cũng theo đúng chế
    độ đó, không hẹn giờ; giữ cho hai video của cùng một tập luôn cùng trạng thái.
    """
    import dang_video_youtube as yt

    video = Path(folder) / SHORT_NAME
    if not video.is_file() or video.stat().st_size == 0:
        return None

    title = short_title(blocks, yt.MAX_TITLE)
    if not title:
        log(f"⚠️ Tập {episode}: không dựng được tiêu đề Short → bỏ qua Short.", "warn")
        return None

    short_at = publish_local + timedelta(hours=SHORT_DELAY_HOURS) if publish_local else None
    privacy = "private" if publish_local else cfg.get("privacy", "schedule")
    khi = (f"hẹn công khai {short_at:%d/%m/%Y %H:%M}" if short_at
           else PRIVACY_LABELS.get(privacy, privacy))
    log(f"⬆ Đăng Short tập {episode}: {video.name} → {khi}", "info")

    video_id = yt.upload_video({
        "video_path": str(video),
        "title": title,
        "description": short_description(main_url, episode),
        "tags": [t.strip() for t in (blocks.get("tags") or "").split(",") if t.strip()],
        "category_id": str(cfg.get("category_id") or DEFAULTS["category_id"]),
        "privacy": privacy,
        "publish_at": yt.to_rfc3339(short_at) if short_at else None,
        "made_for_kids": bool(cfg.get("made_for_kids", False)),
        "contains_ai": bool(cfg.get("contains_ai", True)),
        # Shorts lấy frame đầu làm ảnh bìa mà frame đầu ĐÃ là thumbnail dọc (build_video_doc
        # đè cover_png lên frame đầu của bản TikTok) → không cần đặt ảnh bìa riêng.
        "thumbnail_path": None,
    }, log, progress_cb or (lambda _p: None))

    return {
        "video_id": video_id,
        "url": f"https://youtu.be/{video_id}",
        "title": title,
        "publish_at": short_at.isoformat(timespec="seconds") if short_at else "",
        "publish_at_text": (short_at.strftime("%d/%m/%Y %H:%M") if short_at
                            else PRIVACY_LABELS.get(privacy, privacy)),
    }


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
    'title_tiktok' (nếu có) dùng để đặt tên file video TikTok — xem rename_doc.
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

    # CHỐT CUỐI chống SEO lấy nhầm kết quả của tập khác: mỗi tập là một truyện khác
    # nhau, nên tên truyện trùng video đã có trên kênh gần như chắc chắn là SEO hỏng.
    # Đã dính thật: tập 55–58, 49, 08 cùng mang một tiêu đề vì bước SEO đọc trúng câu
    # trả lời cũ trong chat Gemini. Thà bỏ qua để làm lại SEO còn hơn để kênh có 5
    # video cùng tên.
    if not ALLOW_DUP_TITLE:
        dup = yt.duplicate_title_on_channel(title, ep)
        if dup:
            log(f"⛔ Tập {ep}: kênh ĐÃ CÓ video cùng tên truyện — “{dup.get('title')}”. "
                f"Nhiều khả năng SEO của tập này lấy nhầm kết quả cũ → KHÔNG đăng. "
                f"Xoá seoYoutube.docx của tập rồi chạy lại bước SEO. "
                f"(Đặt {ALLOW_DUP_TITLE_ENV}=1 nếu thật sự muốn đăng trùng tên.)", "err")
            return None

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

    # Đổi tên hai bản dọc — chỉ làm được SAU khi đăng, vì tới lúc đó mới biết khung
    # giờ nào được xếp. Không hẹn giờ (công khai ngay / unlisted) thì lấy chính thời
    # điểm đăng.
    #   • TikTok  → ĐÚNG tiêu đề SEO TikTok ('Full ở Mimi audio Số 12 - Tên truyện'),
    #     đăng tay chỉ việc nhìn tên file mà điền. Chưa có tiêu đề thì lùi về tên
    #     theo giờ, hơn là để nguyên tiktok.mp4.
    #   • Facebook → theo giờ bản YouTube lên sóng, để trong thư mục vẫn còn một chỗ
    #     nhìn ra lịch đăng.
    live_at = publish_local or datetime.now().astimezone()
    tiktok = rename_doc(folder, TIKTOK_NAME,
                        safe_stem(blocks.get("title_tiktok")) or time_stem(TIKTOK_NAME, live_at),
                        log)
    facebook = rename_doc(folder, FACEBOOK_NAME, time_stem(FACEBOOK_NAME, live_at), log)

    # YouTube Short — video PHỤ. Bản chính đã lên kênh rồi, nên mọi sự cố ở đây chỉ
    # được phép thành một dòng cảnh báo: nuốt lỗi để còn ghi bản ghi, không thì lần
    # chạy sau tưởng chưa đăng và đăng TRÙNG bản chính.
    main_url = f"https://youtu.be/{video_id}"
    short = None
    try:
        short = upload_short(folder, ep, blocks, main_url, publish_local, cfg, log,
                             progress_cb)
    except Exception as e:
        log(f"⚠️ Tập {ep}: đăng Short lỗi ({e}) — video chính KHÔNG ảnh hưởng. "
            f"Đăng Short tay từ {SHORT_NAME} nếu cần.", "warn")
    if short:
        log(f"✅ Short tập {ep}: {short['url']} — {short['publish_at_text']}", "ok")

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
        "facebook_file": facebook.name if facebook else "",
        # Short rỗng = chưa/không đăng được (thiếu short.mp4 hoặc lỗi API). Bản ghi
        # tồn tại nên lần chạy sau bỏ qua CẢ TẬP — muốn có Short thì đăng tay.
        "short_video_id": short["video_id"] if short else "",
        "short_url": short["url"] if short else "",
        "short_publish_at": short["publish_at"] if short else "",
        "short_publish_at_text": short["publish_at_text"] if short else "",
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
