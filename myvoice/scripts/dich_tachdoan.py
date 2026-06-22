# -*- coding: utf-8 -*-
"""
Tách 1 file .docx kịch bản (tiếng Trung) thành các đoạn nhỏ ~1000–1500 ký tự,
CẮT Ở CUỐI CÂU (không cắt giữa câu). Dùng lại logic split_into_chunks của recog.

Cách dùng:
    python dich_tachdoan.py "duong_dan/kich_ban_zh.docx"          # ghi đè file đó
    python dich_tachdoan.py "a.docx" --out "a_tach.docx"          # ghi ra file mới
    python dich_tachdoan.py "a.docx" --min 1000 --max 1500
"""

import argparse
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import nhandien_giongnoi as recog


def read_docx_text(path):
    """Đọc toàn bộ chữ trong docx, bỏ qua các dòng tiêu đề (Heading)."""
    from docx import Document
    doc = Document(path)
    title = None
    parts = []
    for par in doc.paragraphs:
        if par.style.name.startswith("Heading"):
            if title is None and par.text.strip():
                title = par.text.strip()      # giữ tiêu đề đầu tiên (tên truyện)
            continue                          # bỏ mọi heading (kể cả "ĐOẠN k" cũ)
        if par.text.strip():
            parts.append(par.text.strip())
    return "".join(parts), title


def main():
    ap = argparse.ArgumentParser(description="Tách docx kịch bản thành đoạn ~1000–1500 ký tự, cắt ở cuối câu.")
    ap.add_argument("docx", help="Đường dẫn file .docx cần tách.")
    ap.add_argument("--out", default=None, help="File .docx xuất ra (mặc định: ghi đè file gốc).")
    ap.add_argument("--min", type=int, default=1000, help="Số ký tự tối thiểu mỗi đoạn (mặc định 1000).")
    ap.add_argument("--max", type=int, default=1500, help="Số ký tự tối đa mỗi đoạn (mặc định 1500).")
    args = ap.parse_args()

    if not os.path.isfile(args.docx):
        print(f"❌ Không tìm thấy file: {args.docx}")
        sys.exit(1)

    text, title = read_docx_text(args.docx)
    if not text:
        print("❌ File không có nội dung chữ.")
        sys.exit(1)
    if not title:
        title = os.path.splitext(os.path.basename(args.docx))[0]

    out_path = args.out or args.docx          # mặc định ghi đè
    print(f"📖 Đọc {len(text)} ký tự từ: {args.docx}")
    recog.save_docx(text, out_path, title=title, chunk=True,
                    min_chars=args.min, max_chars=args.max)
    print(f"💾 Đã lưu bản đã tách đoạn: {out_path}")


if __name__ == "__main__":
    main()
