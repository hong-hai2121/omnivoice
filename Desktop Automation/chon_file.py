# -*- coding: utf-8 -*-
"""
chon_file.py — Hộp thoại chọn file mp4, in đường dẫn ra màn hình (mỗi dòng một cái).

Vì sao phải có file riêng: trang web KHÔNG lấy được đường dẫn thật của file trên
máy — trình duyệt cố tình giấu đi, `<input type=file>` chỉ đưa ra mỗi tên file.
Mà bộ này cần ĐƯỜNG DẪN ĐẦY ĐỦ để đưa cho TikTok. Nên bảng điều khiển gọi file
này như một tiến trình con: nó bật hộp thoại chọn file của Windows, người dùng
chọn xong thì nó in đường dẫn ra, bên kia đọc lấy.

Chạy tiến trình RIÊNG chứ không gọi tkinter ngay trong server, vì tkinter phải ở
luồng chính mới ổn định, còn server thì đang chạy nhiều luồng.

    python chon_file.py [--thu-muc THƯ_MỤC_MỞ_SẴN]
"""

import argparse
import sys
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--thu-muc", default="")
    args = ap.parse_args()

    import tkinter as tk
    from tkinter import filedialog

    goc = tk.Tk()
    goc.withdraw()
    goc.attributes("-topmost", True)     # nổi lên trên cửa sổ trình duyệt

    ban_dau = args.thu_muc if args.thu_muc and Path(args.thu_muc).is_dir() else None
    duong_dan = filedialog.askopenfilenames(
        parent=goc, title="Chọn video mp4 để đăng TikTok",
        initialdir=ban_dau,
        filetypes=[("Video", "*.mp4 *.mov *.m4v *.webm"), ("Tất cả", "*.*")])
    goc.destroy()

    for p in duong_dan:
        print(str(Path(p)))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
