"""Đăng video YouTube của MỘT tập — runner cho bảng điều khiển web.

Mỏng như các runner khác: không tự viết lại gì, chỉ gọi
YOUTUBE/dang_tap_youtube.upload_episode (đúng hàm mà GUI dùng) nên hai bản không
thể lệch nhau về tiêu đề, giờ hẹn hay cách chống đăng trùng.

Cách gọi (steps.py lo phần này):
    python run_upload.py --episode 46

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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Đăng YouTube video của một tập.")
    parser.add_argument("--episode", required=True, help="Số tập, ví dụ 46.")
    args = parser.parse_args(argv)

    _setup_logging()
    episode = str(args.episode).strip().zfill(2)

    folder = core.episode_folder(episode)
    if folder is None:
        logging.error(f"❌ Không thấy thư mục tập {episode} trong kịch_bản/.")
        return ERROR

    ok, msg = core.upload_check()
    if not ok:
        logging.error(f"⛔ {msg}")
        return ERROR

    import dang_tap_youtube as up

    if up.already_uploaded(folder):
        logging.info(f"♻ Bỏ qua: tập {episode} đã đăng (có {up.RECORD_NAME}).")
        return STOP
    if int(episode) in core.episodes_on_channel():
        logging.warning(f"⚠ Bỏ qua: kênh ĐÃ CÓ video 'Số {int(episode)}' "
                        "(nhiều khả năng đã đăng tay) — tránh đăng trùng.")
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
