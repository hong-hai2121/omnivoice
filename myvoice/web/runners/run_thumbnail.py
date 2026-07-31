"""Tạo thumbnail từ tiêu đề tự nhập — bản web của tab Thumbnail bên GUI.

Dựng cả hai bản bằng đúng renderer của GUI (dien_tieu_de_thumbnail):
  • ngang 1920×1080 → thumbnail<tập>.png
  • dọc  1080×1920 → thumbnail<tập>_dọc.png

Tạo thumbnail cho một TẬP đã có SEO thì dùng run_episode.py --steps thumbnail
(nó tự lấy tiêu đề trong seoYoutube.docx của tập đó).
"""

from __future__ import annotations

import argparse
import logging
import random
import sys
import traceback
from pathlib import Path

_WEB_DIR = Path(__file__).resolve().parent.parent
_BASE_DIR = _WEB_DIR.parent
for _p in (str(_BASE_DIR.parent), str(_BASE_DIR / "scripts"), str(_BASE_DIR / "YOUTUBE"),
           str(_BASE_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import amain_taogiong_gui as gui                  # noqa: E402
from run_episode import _setup_logging            # noqa: E402

ERROR = 2


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Tạo thumbnail từ tiêu đề (bản web).")
    parser.add_argument("--title", required=True, help="Tiêu đề hiển thị trên ảnh.")
    parser.add_argument("--episode", default="", help="Số tập in trên thẻ số.")
    parser.add_argument("--photo", default="", help="Tên ảnh trong myvoice/Anh (trống = ngẫu nhiên).")
    parser.add_argument("--out-dir", default="", help="Thư mục lưu (trống = thư mục của tập).")
    parser.add_argument("--doc", action="store_true", help="Làm thêm bản dọc 1080×1920.")
    args = parser.parse_args(argv)

    _setup_logging()
    title = args.title.strip()
    if not title:
        logging.error("❌ Chưa có tiêu đề.")
        return ERROR

    try:
        import dien_tieu_de_thumbnail as renderer

        photos = renderer.list_photo_files(renderer.CAT_IMAGE_DIR)
        if not photos:
            logging.error(f"❌ Không có ảnh nào trong {renderer.CAT_IMAGE_DIR}.")
            return ERROR
        photo = next((p for p in photos if p.name == args.photo), None) if args.photo \
            else random.choice(photos)
        if photo is None:
            logging.warning(f"⚠️ Không thấy ảnh “{args.photo}” → lấy ngẫu nhiên.")
            photo = random.choice(photos)
        logging.info(f"🖼  Ảnh nền: {photo.name}")

        ep = str(args.episode).strip().zfill(2) if str(args.episode).strip() else ""
        if args.out_dir:
            out_dir = Path(args.out_dir)
        else:
            found = gui.find_episode_dir(ep) if ep else None
            out_dir = found or gui.SCRIPT_DIR
        out_dir.mkdir(parents=True, exist_ok=True)

        out_png = out_dir / (f"thumbnail{ep}.png" if ep else "thumbnail.png")
        renderer.add_title(renderer.SOURCE_IMAGE, out_png, title, photo,
                           renderer.FRAME_IMAGE, ep, renderer.NUMBER_FRAME_IMAGE)
        logging.info(f"🖼  Đã tạo thumbnail ngang: {out_png}")

        if args.doc:
            out_doc = out_dir / (f"thumbnail{ep}_dọc.png" if ep else "thumbnail_dọc.png")
            try:
                renderer.add_title_vertical(out_doc, title, photo, ep)
                logging.info(f"🖼  Đã tạo thumbnail dọc: {out_doc}")
            except Exception as e:       # lỗi bản dọc không làm hỏng bản ngang
                logging.warning(f"⚠️ Không tạo được bản dọc: {e}")

        if ep.isdecimal():
            gui.save_episode_number(max(gui.load_episode_number(), int(ep)))
        return 0
    except Exception as e:
        logging.error(f"❌ Lỗi tạo thumbnail: {e}")
        logging.error(traceback.format_exc())
        return ERROR


if __name__ == "__main__":
    sys.exit(main())
