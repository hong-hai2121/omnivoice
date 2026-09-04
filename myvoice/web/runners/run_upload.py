"""Đăng video YouTube của MỘT tập — runner cho bảng điều khiển web.

Mỏng như các runner khác: không tự viết lại gì, chỉ gọi
YOUTUBE/dang_tap_youtube.upload_episode (đúng hàm mà GUI dùng) nên hai bản không
thể lệch nhau về tiêu đề, giờ hẹn hay cách chống đăng trùng.

Cách gọi (steps.py lo phần này):
    python run_upload.py --episode 46
    python run_upload.py --episode 85 --short   # chỉ đăng Short cho tập đã có video chính

Mã thoát: 0 = đã đăng · 77 = bỏ qua có chủ ý (đã đăng rồi, thiếu video/SEO,
kênh đã có tập này) · 2 = lỗi.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_WEB_DIR = Path(__file__).resolve().parent.parent
_BASE_DIR = _WEB_DIR.parent                     # myvoice/
for _p in (str(_BASE_DIR.parent), str(_BASE_DIR / "scripts"), str(_BASE_DIR / "YOUTUBE"),
           str(_BASE_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from myvoice.web import core                    # noqa: E402

STOP = 77       # bỏ qua có chủ ý — không phải sự cố
ERROR = 2


def _setup_logging() -> None:
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for h in list(root.handlers):
        root.removeHandler(h)
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(handler)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _log(msg, level="info") -> None:
    """Bộ log cho dang_tap_youtube (mức của nó: info/warn/err/ok)."""
    {"err": logging.error, "warn": logging.warning}.get(level, logging.info)(msg)


def _post_short(folder: Path, episode: str) -> int:
    """Chỉ đăng Short (short.mp4) cho tập ĐÃ có video chính trên kênh.

    Dành cho tập mà lượt đăng đổ sau video chính (tập 85, 04/09/2026: thumbnail
    quá 2 MB) hoặc Short rớt vì quota (tập 94): bản ghi youtube_upload.json có mà
    short_video_id trống. Chống trùng hai lớp: bản ghi đã có Short, hoặc kênh đã
    có video 'Full ở … Số N'. Đăng xong điền Short vào đúng bản ghi đó.
    """
    import json
    import re
    from datetime import datetime

    import dang_tap_youtube as up
    import dang_video_youtube as yt

    rec = up.already_uploaded(folder)
    if rec is None:
        logging.warning(f"⚠ Bỏ qua Short tập {episode}: chưa đăng video chính "
                        f"(không có {up.RECORD_NAME}) — đăng video chính trước, Short đi kèm.")
        return STOP
    if rec.get("short_video_id"):
        logging.info(f"♻ Bỏ qua: tập {episode} đã có Short ({rec.get('short_url', '')}).")
        return STOP
    try:
        data = yt.load_video_cache()
        videos = (data["channels"].get(data.get("current")) or {}).get("videos", [])
    except Exception:
        videos = []
    n = int(episode)
    dup = next((v for v in videos
                if (v.get("title") or "").lower().startswith("full ở")
                and re.search(rf"\bSố\s+0*{n}\b", v.get("title") or "")), None)
    if dup:
        logging.warning(f"⚠ Bỏ qua Short tập {episode}: kênh ĐÃ CÓ “{dup.get('title')}” "
                        f"(https://youtu.be/{dup.get('id', '')}) — tránh đăng trùng.")
        return STOP
    if not (folder / up.SHORT_NAME).is_file():
        logging.warning(f"⚠ Tập {episode}: không có {up.SHORT_NAME} → không đăng Short được.")
        return STOP
    blocks = core.seo_blocks(folder, episode)
    if not blocks:
        logging.error(f"❌ Tập {episode}: chưa đọc được SEO (seoYoutube.docx) → không đăng Short.")
        return STOP

    publish_local = None
    if rec.get("publish_at"):
        try:
            publish_local = datetime.fromisoformat(rec["publish_at"])
        except ValueError:
            publish_local = None
    # Bản chính đã công khai từ trước (đăng bù muộn) → mốc hẹn của Short tính từ
    # BÂY GIỜ, không thì YouTube từ chối giờ hẹn trong quá khứ.
    now = datetime.now().astimezone()
    if publish_local is not None and publish_local < now:
        publish_local = now

    short = up.upload_short(folder, episode, blocks, rec["url"], publish_local,
                            up.load_settings(), _log,
                            progress_cb=lambda p: print(f"⬆ Tải lên {p}%", flush=True))
    if not short:
        return STOP
    rec.update({
        "short_video_id": short["video_id"], "short_url": short["url"],
        "short_publish_at": short["publish_at"],
        "short_publish_at_text": short["publish_at_text"],
    })
    try:
        up.record_path(folder).write_text(json.dumps(rec, ensure_ascii=False, indent=1),
                                          encoding="utf-8")
    except OSError as e:
        logging.error(f"❌ Tập {episode}: Short ĐÃ ĐĂNG ({short['url']}) nhưng KHÔNG ghi được "
                      f"{up.RECORD_NAME}: {e}. Chạy lại có thể đăng TRÙNG Short!")
    logging.info(f"✅ Short tập {episode}: {short['url']} — {short['publish_at_text']}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Đăng YouTube video của một tập.")
    parser.add_argument("--episode", required=True, help="Số tập, ví dụ 46.")
    parser.add_argument("--short", action="store_true",
                        help="Chỉ đăng Short (short.mp4) cho tập ĐÃ đăng video chính mà bản ghi còn thiếu Short.")
    args = parser.parse_args(argv)

    _setup_logging()
    episode = str(args.episode).strip().zfill(2)

    folder = core.episode_folder(episode)
    if folder is None:
        logging.error(f"❌ Không thấy thư mục tập {episode} trong kịch_bản/.")
        return ERROR

    # Đọc lại kênh NGAY TRƯỚC KHI ĐĂNG, không tin ảnh chụp lúc bấm nút: mẻ chạy đêm
    # cách lúc bấm hàng giờ — token có thể vừa hết hạn, mà khung giờ 08:00/18:00 cũng
    # phải tính trên danh sách video mới nhất (kể cả video hẹn từ máy khác), không
    # thì hai tập đè nhau một khung.
    chan, msg = core.refresh_channel()
    if chan is None:
        logging.error(f"⛔ {msg}")
        return ERROR
    logging.info(f"📺 Kênh: {chan['title']} — {chan['video_count']} video.")

    import dang_tap_youtube as up

    if args.short:
        return _post_short(folder, episode)

    if up.already_uploaded(folder):
        logging.info(f"♻ Bỏ qua: tập {episode} đã đăng (có {up.RECORD_NAME}).")
        return STOP
    if int(episode) in core.episodes_on_channel():
        logging.warning(f"⚠ Bỏ qua: kênh ĐÃ CÓ video 'Số {int(episode)}' "
                        "(nhiều khả năng đã đăng tay) — tránh đăng trùng.")
        return STOP

    # ⛔ CHỐT CUỐI trước khi đăng (giống _upload_one bên GUI): bản dịch còn đoạn
    # hỏng (chưa dịch / bị Gemini từ chối / dịch cụt) → TUYỆT ĐỐI KHÔNG ĐĂNG, dù
    # video đã render. Tập 85/87 từng lên thẳng YouTube với 14-25% nội dung thiếu
    # qua đúng đường runner này.
    bad = core.gui.kiem_ban_dich_folder(folder)
    if bad:
        mota = ", ".join(f"đoạn {j} {ly_do}" for j, ly_do in bad)
        logging.error(f"⛔ KHÔNG ĐĂNG tập {episode}: bản dịch có đoạn hỏng ({mota}). "
                      "Dịch lại các đoạn hỏng, render lại rồi mới đăng.")
        return STOP

    blocks = core.seo_blocks(folder, episode)
    if not blocks:
        logging.error(f"❌ Tập {episode}: chưa đọc được SEO (seoYoutube.docx) → không đăng.")
        return STOP

    rec = up.upload_episode(folder, episode, blocks, _log,
                            progress_cb=lambda p: print(f"⬆ Tải lên {p}%", flush=True))
    if rec is None:
        return STOP     # lý do đã ghi trong log (thiếu video, tiêu đề quá dài…)
    return 0


if __name__ == "__main__":
    sys.exit(main())
