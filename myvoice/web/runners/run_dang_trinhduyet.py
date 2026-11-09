"""Đăng YouTube Studio + TikTok Studio (qua Chrome thật) cho MỘT hay nhiều tập — runner cho bảng web
và cũng là lệnh dòng lệnh.

Mỏng như run_upload.py: mọi chốt an toàn giống đường API (bản dịch còn đoạn hỏng → KHÔNG đăng; SEO phải
đọc được; đã có biên nhận → bỏ qua), rồi gọi TRINHDUYET/dang_tap_trinhduyet.dang_tap.

    python run_dang_trinhduyet.py --episode 156
    python run_dang_trinhduyet.py --episode 153 154 155 --nen-tang youtube
    python run_dang_trinhduyet.py --episode 156 --chay-thu        # làm hết, DỪNG trước nút cuối
    python run_dang_trinhduyet.py --episode 156 --ke-hoach        # chỉ in kế hoạch, không mở trình duyệt

Mã thoát: 0 = có đăng được ít nhất một việc · 77 = bỏ qua có chủ ý (đã đăng, thiếu video/SEO, chưa liên
kết profile…) · 2 = lỗi (kể cả cấu hình trỏ vào profile của tool tham khảo).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_WEB_DIR = Path(__file__).resolve().parent.parent
_BASE_DIR = _WEB_DIR.parent                     # myvoice/
for _p in (str(_BASE_DIR.parent), str(_BASE_DIR / "scripts"), str(_BASE_DIR / "YOUTUBE"),
           str(_BASE_DIR / "TRINHDUYET"), str(_BASE_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

STOP = 77
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
    {"err": logging.error, "warn": logging.warning}.get(level, logging.info)(msg)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Đăng YouTube Studio / TikTok Studio qua Chrome thật.")
    parser.add_argument("--episode", nargs="+", required=True, help="Số tập (một hoặc nhiều), ví dụ 153 154.")
    parser.add_argument("--nen-tang", nargs="+", default=["youtube", "tiktok"], choices=["youtube", "tiktok"],
                        help="Nền tảng đăng (mặc định cả hai).")
    parser.add_argument("--chay-thu", action="store_true", help="Làm hết các bước rồi DỪNG trước nút cuối.")
    parser.add_argument("--ke-hoach", action="store_true", help="Chỉ in kế hoạch (file, tiêu đề, giờ), không mở trình duyệt.")
    parser.add_argument("--khong-doc-lich", action="store_true", help="Không đọc lịch thật trên Studio (chỉ dựa biên nhận local).")
    args = parser.parse_args(argv)
    _setup_logging()

    import trinhduyet
    import dang_tap_trinhduyet as dt
    from myvoice.web import core

    cfg = trinhduyet.load_config()
    if args.khong_doc_lich:
        cfg["doc_lich_that"] = False

    # Cấu hình từng nền tảng: chưa liên kết → bỏ nền tảng đó (STOP); trùng profile tham khảo → lỗi, dừng hẳn.
    nen_tang = []
    for name in args.nen_tang:
        try:
            p = trinhduyet.kiem_san_sang(cfg, name)
            logging.info(f"🌐 {trinhduyet.NHAN[name]}: profile '{p['profile_dir']}'")
            nen_tang.append(name)
        except trinhduyet.ProfileCamError as e:
            logging.error(f"⛔ {e}")
            return ERROR
        except trinhduyet.ChuaCauHinhError as e:
            if args.ke_hoach:
                nen_tang.append(name)       # kế hoạch thì vẫn in được
            logging.warning(f"⏭ {e}")
    if not nen_tang:
        logging.warning(f"⚠ Chưa nền tảng nào liên kết profile — điền {trinhduyet.CONFIG_PATH} rồi chạy lại.")
        return STOP

    rc = STOP
    lich_that = {}
    try:
        if not args.ke_hoach:
            lich_that = dt.doc_lich_that(cfg, nen_tang, _log)
        for raw in args.episode:
            episode = str(raw).strip().zfill(2)
            folder = core.episode_folder(episode)
            if folder is None:
                logging.error(f"❌ Không thấy thư mục tập {episode} trong kịch_bản/.")
                rc = ERROR
                continue
            # ⛔ CHỐT CUỐI (giống run_upload.py): bản dịch còn đoạn hỏng → TUYỆT ĐỐI KHÔNG ĐĂNG.
            bad = core.gui.kiem_ban_dich_folder(folder)
            if bad:
                mota = ", ".join(f"đoạn {j} {ly_do}" for j, ly_do in bad)
                logging.error(f"⛔ KHÔNG ĐĂNG tập {episode}: bản dịch có đoạn hỏng ({mota}).")
                continue
            blocks = core.seo_blocks(folder, episode)
            if not blocks:
                logging.error(f"❌ Tập {episode}: chưa đọc được SEO (seoYoutube.docx) → không đăng.")
                continue
            if args.ke_hoach:
                taken = dt.gio_da_hen_local(folder.parent)
                for name in nen_tang:
                    plan = (dt.ke_hoach_youtube if name == "youtube" else dt.ke_hoach_tiktok)(
                        folder, episode, blocks, cfg, taken=taken[name])
                    logging.info(dt.mo_ta_ke_hoach(plan, name))
                continue
            kq = dt.dang_tap(folder, episode, blocks, nen_tang, cfg, _log, dry_run=args.chay_thu, lich_that=lich_that)
            for name, r in kq.items():
                if isinstance(r, dict):
                    rc = 0 if rc != ERROR else rc
                    if r.get("publish_at"):      # cộng mốc vừa xếp để tập sau nối tiếp (kể cả khi chưa quét lại local)
                        lich_that.setdefault(name, []).append(dt.parse_dt(r["publish_at"]))
                        if r.get("short_publish_at"):
                            lich_that[name].append(dt.parse_dt(r["short_publish_at"]))
                elif isinstance(r, str) and r.startswith("lỗi"):
                    rc = ERROR
    finally:
        if not args.chay_thu:
            trinhduyet.ngat_tat_ca(dong_tab=True, log=logging.info)
        else:
            logging.info("ℹ Chạy thử: giữ tab Chrome mở để bạn kiểm tra; relay sẽ tắt khi tiến trình kết thúc.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
