"""Bật myvoice — bản WEB.  Mở file này rồi bấm ▶ Run trong VS Code là chạy.

Vì sao có file này: VS Code chỉ bấm ▶ chạy được file .py, không chạy .bat.
Nội dung y hệt `chay.bat` (và `chay_gui.bat` khi thêm cờ --gui).

Chạy bằng BẤT KỲ python nào cũng được: nếu interpreter đang dùng không phải venv
của dự án thì file tự khởi động lại bằng venv\\Scripts\\python.exe — không thì sẽ
thiếu fastapi/uvicorn/torch.

    python myvoice/chay.py          → bảng điều khiển web (trình duyệt tự mở)
    python myvoice/chay.py --gui    → GUI Tkinter bản cũ
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # …/OmniVoice
VENV_PY = ROOT / "venv" / "Scripts" / "python.exe"
GUI = ROOT / "myvoice" / "scripts" / "amain_taogiong_gui.py"

# Console của VS Code / cmd hay là cp1252: in tiếng Việt sẽ nổ UnicodeEncodeError
# NGAY dòng thông báo đầu tiên, chưa kịp bật gì cả. Ép UTF-8 trước mọi thứ.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")   # type: ignore[union-attr]
    except Exception:
        pass


def _is_venv_python() -> bool:
    try:
        return VENV_PY.exists() and Path(sys.executable).resolve() == VENV_PY.resolve()
    except OSError:
        return False


def main(argv: list[str]) -> int:
    if VENV_PY.exists() and not _is_venv_python():
        print(f"↻ Chạy lại bằng python của dự án: {VENV_PY}")
        return subprocess.call([str(VENV_PY), str(Path(__file__).resolve()), *argv],
                               cwd=str(ROOT))

    if not VENV_PY.exists():
        print(f"⚠️ Không thấy {VENV_PY} — đang dùng {sys.executable}. "
              "Thiếu thư viện thì tạo lại venv của dự án.")

    sys.path.insert(0, str(ROOT))
    if "--gui" in argv:
        print("🖥  Mở GUI Tkinter (bản cũ)…")
        return subprocess.call([sys.executable, str(GUI)], cwd=str(ROOT))

    from myvoice.web.server import main as run_server     # noqa: E402
    run_server()                                          # chặn tới khi Ctrl+C
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
