# -*- coding: utf-8 -*-
"""
chay_web.py — Bật bảng điều khiển TikTok rồi tự mở trình duyệt.

Mở file này bấm ▶ Run trong VS Code là chạy (VS Code không chạy được .bat, nên
mới có bản .py này bên cạnh chay_web.bat — cùng một việc).

Chạy bằng python nào cũng được: không phải venv thì nó tự khởi động lại bằng
venv\\Scripts\\python.exe, nếu không sẽ thiếu fastapi/uvicorn.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dung_venv import dam_bao_venv                          # noqa: E402

dam_bao_venv(__file__)

import socket                   # noqa: E402
import threading                # noqa: E402
import time                     # noqa: E402
import webbrowser               # noqa: E402

import web_tiktok               # noqa: E402

DIA_CHI = f"http://127.0.0.1:{web_tiktok.CONG}"


def cong_ban(cong: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", cong)) == 0


def mo_khi_san_sang() -> None:
    for _ in range(60):
        if cong_ban(web_tiktok.CONG):
            webbrowser.open(DIA_CHI)
            return
        time.sleep(0.4)


def main() -> None:
    if cong_ban(web_tiktok.CONG):
        print(f"Bảng điều khiển đã chạy sẵn — mở lại: {DIA_CHI}")
        webbrowser.open(DIA_CHI)
        return
    threading.Thread(target=mo_khi_san_sang, daemon=True).start()
    web_tiktok.main()


if __name__ == "__main__":
    main()
