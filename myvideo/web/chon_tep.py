# -*- coding: utf-8 -*-
"""Hộp CHỌN FILE của Windows cho nút "📂 Thêm từ máy" của web myvideo.

    python chon_tep.py [thư_mục_mở_sẵn]

Chạy thành TIẾN TRÌNH RIÊNG (server gọi qua subprocess, xem /api/chon-tep): Tk
chỉ chịu sống ở luồng chính của một tiến trình, còn server là uvicorn đa luồng.
Trình duyệt không cho trang web biết đường dẫn thật của file người dùng chọn
(<input type=file> chỉ trả "C:\\fakepath\\…") mà quy trình lại cần đường dẫn
thật — server chạy ngay trên máy này nên tự nó mở hộp chọn là đúng chỗ.

In ra stdout MỘT dòng JSON: danh sách đường dẫn đã chọn ([] = bấm Cancel).
JSON để nguyên dạng \\uXXXX (ensure_ascii) — tên file tiếng Trung/Việt đi qua
đường ống stdout không lệ thuộc bảng mã console.
"""

from __future__ import annotations

import json
import os
import sys

# Đuôi video/audio quy trình nhận — hộp chọn chỉ LỌC sẵn theo đây, mục "Tất cả"
# vẫn cho chọn file bất kỳ.
MEDIA = ("mp4 mkv mov avi webm flv ts m4v mp3 wav m4a aac flac ogg opus").split()


def main() -> int:
    import tkinter as tk
    from tkinter import filedialog

    thu_muc = sys.argv[1] if len(sys.argv) > 1 else ""
    root = tk.Tk()
    root.withdraw()
    # Server chạy ẩn nên hộp chọn không có cửa sổ mẹ nào đang nổi — ghim "luôn
    # trên cùng" kẻo nó mở ra NẰM SAU trình duyệt, người dùng tưởng nút hỏng.
    root.attributes("-topmost", True)
    root.update()
    chon = filedialog.askopenfilenames(
        parent=root,
        title="Thêm video / audio nguồn — giữ Ctrl hoặc Shift để chọn nhiều file",
        initialdir=thu_muc if os.path.isdir(thu_muc) else None,
        filetypes=[("Video / audio", " ".join(f"*.{e}" for e in MEDIA)),
                   ("Tất cả", "*.*")])
    root.destroy()
    # Tk trả đường dẫn gạch xuôi (C:/Users/…) — đổi về dạng Windows cho giống
    # đường dẫn người dùng tự dán, để so trùng trong ô Nguồn khớp nhau.
    paths = [os.path.normpath(p) for p in chon]
    sys.stdout.write(json.dumps(paths, ensure_ascii=True))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
