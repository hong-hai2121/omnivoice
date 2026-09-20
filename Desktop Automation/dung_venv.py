# -*- coding: utf-8 -*-
"""
dung_venv.py — Bảo đảm script đang chạy bằng python của venv dự án.

Vì sao cần: bấm nút ▶ trong VS Code thì nó chạy bằng interpreter đang chọn ở
thanh dưới, thường là Python hệ thống — bên đó KHÔNG có numpy/Pillow nên script
chết ngay dòng import, mà thông báo lỗi lại không nói gì về nguyên nhân thật.

Cách chữa: gọi dam_bao_venv(__file__) ở NGAY ĐẦU file, TRƯỚC mọi import nặng.
Nếu đang chạy sai python thì nó gọi lại chính file đó bằng python của venv rồi
thoát, nên dù bấm ▶, bấm F5, hay gõ tay bằng python nào cũng ra cùng kết quả.

Chỉ dùng thư viện chuẩn, để bản thân file này không bao giờ là thứ gây lỗi.
"""

import os
import subprocess
import sys
from pathlib import Path

VENV_PYTHON = Path(__file__).resolve().parent.parent / "venv" / "Scripts" / "python.exe"
_CO_DAU = "OMNI_DA_DOI_PYTHON"        # chặn gọi lại vòng tròn nếu có gì bất thường


def dang_dung_venv() -> bool:
    try:
        return Path(sys.executable).resolve() == VENV_PYTHON.resolve()
    except OSError:
        return False


def dam_bao_venv(file_goi: str) -> None:
    """Đang chạy sai python thì chạy lại bằng python của venv rồi thoát.

    Mọi thông báo ở đây chỉ dùng chữ KHÔNG DẤU. Lý do: lúc này ta còn đang chạy
    bằng python lạ, màn hình lệnh của nó thường ở bảng mã cp1252 — in một chữ có
    dấu là UnicodeEncodeError, script chết ngay tại dòng báo tin, mà lỗi hiện ra
    lại chẳng liên quan gì tới nguyên nhân thật."""
    if dang_dung_venv() or os.environ.get(_CO_DAU):
        return
    if not VENV_PYTHON.exists():
        print(f"[!] Khong thay python cua venv: {VENV_PYTHON}\n"
              f"    Dang chay tam bang: {sys.executable}", file=sys.stderr)
        return

    print(f"[i] Dang chay bang python khac: {sys.executable}")
    print(f"    Chuyen sang python cua venv: {VENV_PYTHON}\n", flush=True)
    moi = dict(os.environ, **{_CO_DAU: "1", "PYTHONIOENCODING": "utf-8",
                              "PYTHONUTF8": "1"})
    ra = subprocess.run([str(VENV_PYTHON), "-X", "utf8",
                         str(Path(file_goi).resolve()), *sys.argv[1:]], env=moi)
    sys.exit(ra.returncode)
