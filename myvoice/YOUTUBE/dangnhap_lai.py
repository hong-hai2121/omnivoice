# -*- coding: utf-8 -*-
"""Đăng nhập LẠI YouTube uploader — lấy token MỚI (vd sau khi app chuyển Public,
đổi kênh, hay token cũ hết hạn không tự làm mới được).

Mở trình duyệt với màn hình CHỌN TÀI KHOẢN; app chưa qua thẩm định Google thì
màn hình cảnh báo "Google hasn't verified this app" → Advanced → Continue.
Token cũ tự giữ thành token_old_<ngày giờ>.json, CHỈ bị thay khi đăng nhập
thành công — huỷ giữa chừng không mất gì.

Chạy: đúp chuột dangnhap_lai.bat (hoặc venv\\Scripts\\python.exe dangnhap_lai.py).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import dang_video_youtube as yt  # noqa: E402


def log(msg, level="info"):
    print(f"[{level}] {msg}", flush=True)


def main():
    print("🔑 Đăng nhập lại YouTube — trình duyệt sẽ mở, chọn ĐÚNG kênh rồi bấm Cho phép.")
    creds = yt.get_credentials(log, force_new=True)
    if creds:
        print(f"✅ XONG — token mới đã lưu: {yt.TOKEN_FILE}")
        print("   (App đã Public nên token này không còn hết hạn 7 ngày như thời Testing.)")
    else:
        print("❌ Không lấy được token — token cũ giữ nguyên.")


if __name__ == "__main__":
    main()
