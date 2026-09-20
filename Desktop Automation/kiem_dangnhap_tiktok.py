# -*- coding: utf-8 -*-
"""
kiem_dangnhap_tiktok.py — Profile 83 đã đăng nhập TikTok chưa?

Mở trang đăng của TikTok Studio bằng ĐÚNG Chrome Profile 83 (hồ sơ thật, không
cổng gỡ lỗi, không đóng Chrome), rồi trả lời bằng hai thứ ở tầng hệ điều hành:
  • TIÊU ĐỀ cửa sổ — TikTok đặt tên trang khác hẳn khi chưa đăng nhập,
  • ẢNH CHỤP NGẦM  — để mắt người nhìn lại cho chắc.
Không đọc cookie, không đụng DOM.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dung_venv import dam_bao_venv                          # noqa: E402

dam_bao_venv(__file__)

import subprocess           # noqa: E402
import time                 # noqa: E402

from thu_khong_chiem_chuot import (ANH, CHROME_EXE, PROFILE, chup_ngam,  # noqa: E402
                                   lop_cua_so, tieu_de, user32, _ENUM)

URL = "https://www.tiktok.com/tiktokstudio/upload"


def cua_so_chrome_moi_nhat() -> int | None:
    """Cửa sổ Chrome hiện lên trên cùng nhất (EnumWindows đi từ trên xuống)."""
    ra = []

    def _moi(h, _):
        if user32.IsWindowVisible(h) and lop_cua_so(h) == "Chrome_WidgetWin_1" \
                and tieu_de(h).strip():
            ra.append(h)
        return True

    user32.EnumWindows(_ENUM(_moi), 0)
    return ra[0] if ra else None


def main():
    ANH.mkdir(parents=True, exist_ok=True)
    print(f"▶ Mở {URL}")
    print(f"  bằng Chrome '{PROFILE}' — hồ sơ THẬT, không cổng gỡ lỗi")
    subprocess.Popen([str(CHROME_EXE), f"--profile-directory={PROFILE}",
                      "--new-window", URL])

    hwnd, td = None, ""
    for _ in range(50):
        time.sleep(0.6)
        h = cua_so_chrome_moi_nhat()
        if h:
            t = tieu_de(h)
            if "Chrome" in t and t != "New Tab - Google Chrome":
                hwnd, td = h, t
                if "TikTok" in t:
                    break
    if not hwnd:
        sys.exit("❌ Không thấy cửa sổ Chrome nào.")

    time.sleep(6)          # TikTok là SPA, để nó dựng xong rồi hãy đọc
    td = tieu_de(hwnd)
    print(f"\n  Tiêu đề cửa sổ: {td!r}")

    thap = td.lower()
    if "log in" in thap or "đăng nhập" in thap or "login" in thap:
        ket = "CHƯA đăng nhập"
    elif "tiktok" in thap:
        ket = "CÓ VẺ ĐÃ đăng nhập (tiêu đề là trang TikTok Studio)"
    else:
        ket = "chưa đọc được — xem ảnh"
    print(f"  → {ket}")

    img, _, ok = chup_ngam(hwnd)
    if img:
        p = ANH / "tiktok_profile83.png"
        img.save(p)
        print(f"  Ảnh chụp ngầm: {p}")
    else:
        print("  ⚠ Không chụp được cửa sổ.")


if __name__ == "__main__":
    main()
