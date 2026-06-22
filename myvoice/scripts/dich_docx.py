# -*- coding: utf-8 -*-
"""
dich_docx.py — Đọc file .docx kết quả nhận diện (đã tách "ĐOẠN k"), gửi
TỪNG ĐOẠN lên Gemini để dịch, rồi lưu kết quả ra .docx. Dùng lại được nhiều lần.

Chạy:
    python dich_docx.py                         # dùng đường dẫn mặc định bên dưới
    python dich_docx.py "input.docx"            # đổi file nguồn
    python dich_docx.py "input.docx" -o "out.docx"
    python dich_docx.py --limit 1               # chỉ gửi đoạn 1 (để test)
    python dich_docx.py --no-keep-open          # đóng Firefox sau khi xong

Đặc điểm:
• Câu mở đầu (prefix dịch) lấy từ scripts/copy_prefix.txt, chỉ chèn vào ĐOẠN 1
  (Gemini nhớ ngữ cảnh các đoạn sau) — giống hệt nút "Sao chép" trong GUI nhận diện.
• Lưu DẦN sau mỗi đoạn → dừng giữa chừng vẫn giữ được phần đã dịch.
"""

import sys
import os

# ── Tự chuyển sang python của venv (giống các script khác trong thư mục này) ──
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
_VENV_PYTHON = os.path.join(_REPO_ROOT, "venv", "Scripts", "python.exe")
if os.path.exists(_VENV_PYTHON) and os.path.abspath(sys.executable) != os.path.abspath(_VENV_PYTHON):
    import subprocess
    subprocess.run([_VENV_PYTHON] + sys.argv)
    sys.exit()

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import argparse
from pathlib import Path

from docx import Document
import dich_gemini as g

# ── Đường dẫn mặc định ───────────────────────────────────────────────────────
KICHBAN_DIR = Path(_SCRIPTS_DIR).parent / "kịch_bản"
DEFAULT_INPUT = KICHBAN_DIR / "tiengTrung.docx"
DEFAULT_OUTPUT = KICHBAN_DIR / "gemini_result.docx"
PREFIX_FILE = Path(_SCRIPTS_DIR) / "copy_prefix.txt"


def read_chunks(path):
    """Mỗi paragraph nội dung (bỏ Heading 'ĐOẠN k' và Title) = 1 đoạn đã lưu."""
    doc = Document(str(path))
    chunks = []
    for para in doc.paragraphs:
        style = (para.style.name or "")
        t = para.text.strip()
        if not t or style.startswith("Heading") or style.startswith("Title"):
            continue
        chunks.append(t)
    return chunks


def load_prefix():
    """Câu mở đầu (prefix dịch) lưu ở copy_prefix.txt; chưa có thì trả về rỗng."""
    if PREFIX_FILE.exists():
        return PREFIX_FILE.read_text(encoding="utf-8").strip()
    return ""


def run(input_path, output_path, limit=0, keep_open=True, log=print):
    chunks = read_chunks(input_path)
    if not chunks:
        log(f"❌ Không đọc được đoạn nào từ: {input_path}")
        return []
    if limit and limit > 0:
        chunks = chunks[:limit]

    prefix = load_prefix()
    log(f"📚 {len(chunks)} đoạn sẽ gửi | prefix {len(prefix)} ký tự")
    log(f"📄 Nguồn : {input_path}")
    log(f"💾 Kết quả: {output_path}")

    # Lưu DẦN sau mỗi đoạn: dừng giữa chừng vẫn giữ phần đã dịch.
    acc = []

    def on_result(i, total, ans):
        acc.append(ans)
        # Lưu DẦN ngay sau khi nhận xong đoạn này (trước khi gửi đoạn kế tiếp)
        g.save_results_docx(chunks[:len(acc)], acc, output_path)
        # In nguyên văn kết quả đoạn để theo dõi
        log(f"\n========== KẾT QUẢ ĐOẠN {i + 1}/{total} ==========\n{ans or '(trống)'}\n")
        log(f"💾 Đã lưu {len(acc)}/{total} đoạn → {output_path}")

    results = g.send_chunks_to_gemini(
        chunks, prefix=prefix, on_log=log, on_result=on_result, keep_open=keep_open
    )
    # Lưu lần cuối cho chắc (đủ tiêu đề/đoạn)
    g.save_results_docx(chunks, results, output_path)
    ok = sum(1 for r in results if r and r.strip())
    log(f"✅ XONG: {ok}/{len(results)} đoạn có kết quả → {output_path}")
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description="Gửi nội dung .docx lên Gemini để dịch.")
    parser.add_argument("input", nargs="?", default=str(DEFAULT_INPUT),
                        help="File .docx nguồn (đã tách ĐOẠN).")
    parser.add_argument("-o", "--output", default=str(DEFAULT_OUTPUT),
                        help="File .docx lưu kết quả.")
    parser.add_argument("--limit", type=int, default=0,
                        help="Chỉ gửi N đoạn đầu (0 = tất cả).")
    parser.add_argument("--no-keep-open", dest="keep_open", action="store_false",
                        help="Đóng Firefox sau khi xong.")
    args = parser.parse_args(argv)

    run(args.input, args.output, limit=args.limit, keep_open=args.keep_open)


if __name__ == "__main__":
    main()
