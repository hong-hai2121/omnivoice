# -*- coding: utf-8 -*-
"""
dich_chuanbi_input.py — Chuẩn bị input.txt cho TTS từ kết quả Gemini.

Luồng (chạy TRƯỚC khi tạo audio):
  1. CHECK gemini_result.docx bằng dich_kiemtra (bắt câu dẫn nhập/thừa
     Gemini hay tự thêm, vd "Dưới đây là bản dịch...", "Bản dịch truyện ngắn").
     → Nếu CÓ: BÁO (beep + liệt kê) và DỪNG, KHÔNG ghi input.txt (sửa docx trước).
  2. Bỏ cấu trúc: tiêu đề "Kết quả dịch từ Gemini" và các mục "Đoạn k".
  3. Ghép toàn bộ nội dung thành 1 đoạn hoàn chỉnh → ghi vào kịch_bản/input.txt.
  → Sau đó mở taogiong_gui.py bấm "▶ Chạy" để tạo audio.

Chạy:
    python dich_chuanbi_input.py
    python dich_chuanbi_input.py "gemini_result.docx" -o "input.txt"
    python dich_chuanbi_input.py --force   # ghi input.txt kể cả khi check thấy lỗi

Mã thoát: 0 = đã ghi input.txt · 1 = check thấy lỗi (đã dừng) · 2 = thiếu file/nội dung.
"""

import sys
import os

# ── Tự chuyển sang python của venv (giống các script khác trong thư mục) ──────
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
_VENV_PYTHON = os.path.join(_REPO_ROOT, "venv", "Scripts", "python.exe")
if __name__ == "__main__" and os.path.exists(_VENV_PYTHON) and \
        os.path.normcase(os.path.abspath(sys.executable)) != \
        os.path.normcase(os.path.abspath(_VENV_PYTHON)):
    import subprocess
    subprocess.run([_VENV_PYTHON] + sys.argv)
    sys.exit()

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import re
import argparse
from pathlib import Path

import dich_kiemtra as checker

KICHBAN_DIR = Path(_SCRIPTS_DIR).parent / "kịch_bản"
DEFAULT_DOCX = KICHBAN_DIR / "gemini_result.docx"
DEFAULT_INPUT = KICHBAN_DIR / "input.txt"

# Dòng cấu trúc cần bỏ (kể cả khi không phải Heading): tiêu đề tổng + "Đoạn k ..."
_SKIP_RE = re.compile(r"^(kết quả dịch từ gemini.*|đoạn\s*\d+.*|doan\s*\d+.*)$", re.IGNORECASE)


def extract_content(path):
    """Lấy toàn bộ nội dung, bỏ tiêu đề 'Kết quả dịch từ Gemini' và các 'Đoạn k',
    ghép thành 1 nội dung hoàn chỉnh (giữ ngắt đoạn tự nhiên bằng xuống dòng)."""
    from docx import Document
    doc = Document(str(path))
    parts = []
    for para in doc.paragraphs:
        t = para.text.strip()
        if not t:
            continue
        style = (para.style.name or "")
        if style.startswith("Heading") or style.startswith("Title"):
            continue
        if _SKIP_RE.match(t):
            continue
        parts.append(t)
    return "\n".join(parts).strip()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Bỏ cấu trúc docx Gemini, ghép nội dung vào input.txt (có check trước)."
    )
    parser.add_argument("docx", nargs="?", default=str(DEFAULT_DOCX),
                        help="File .docx kết quả Gemini.")
    parser.add_argument("-o", "--output", default=str(DEFAULT_INPUT),
                        help="File input.txt cho TTS.")
    parser.add_argument("--force", action="store_true",
                        help="Vẫn ghi input.txt dù check thấy câu dẫn nhập/thừa.")
    args = parser.parse_args(argv)

    docx_path = Path(args.docx)
    out_path = Path(args.output)

    # ── Bước 1: CHECK trước khi tạo audio ────────────────────────────────────
    print("🔎 BƯỚC 1 — Kiểm tra câu dẫn nhập/thừa trong docx Gemini...")
    findings = checker.check_docx(docx_path)
    if findings is None:
        sys.exit(2)  # không có file
    if findings and not args.force:
        print("\n⛔ DỪNG: docx còn câu dẫn nhập/thừa ở trên → CHƯA ghi input.txt, "
              "CHƯA tạo audio.\n   Hãy sửa lại gemini_result.docx (hoặc chạy lại với "
              "--force nếu vẫn muốn ghi).")
        sys.exit(1)
    if findings and args.force:
        print("\n⚠️  Có lỗi nhưng --force → vẫn ghi input.txt.")

    # ── Bước 2+3: bỏ cấu trúc, ghép nội dung, ghi input.txt ───────────────────
    print("\n🧹 BƯỚC 2 — Bỏ cấu trúc 'Kết quả dịch từ Gemini' / 'Đoạn k', ghép nội dung...")
    content = extract_content(docx_path)
    if not content:
        print(f"❌ Không lấy được nội dung nào từ: {docx_path}")
        sys.exit(2)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")
    print(f"💾 BƯỚC 3 — Đã ghi {len(content)} ký tự → {out_path}")
    print("✅ SẴN SÀNG TẠO AUDIO: mở taogiong_gui.py và bấm '▶ Chạy'.")
    sys.exit(0)


if __name__ == "__main__":
    main()
