# -*- coding: utf-8 -*-
"""
dich_kiemtra.py — Kiểm tra file .docx kết quả Gemini, phát hiện các câu
"dẫn nhập" / câu thừa mà Gemini hay tự thêm (dù prefix đã yêu cầu KHÔNG thêm), ví dụ:
    "Dưới đây là bản dịch tiếng Việt sát nghĩa, đầy đủ nội dung..."
    "Bản dịch truyện ngắn"

Nếu thấy → THÔNG BÁO: in cảnh báo + beep, liệt kê đoạn nào dính câu nào.

Chạy:
    python dich_kiemtra.py                      # kiểm tra gemini_result.docx mặc định
    python dich_kiemtra.py "duong_dan.docx"     # kiểm tra file khác

Mã thoát: 0 = sạch, 1 = có phát hiện (tiện gọi từ script khác).
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

from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
KICHBAN_DIR = _SCRIPTS_DIR.parent / "kịch_bản"
DEFAULT_DOCX = KICHBAN_DIR / "gemini_result.docx"

# ── Các câu "dẫn nhập / thừa" cần phát hiện (so khớp KHÔNG phân biệt hoa thường).
#    Thêm/bớt câu ở đây nếu gặp mẫu mới. ────────────────────────────────────────
SUSPECT_PHRASES = [
    "dưới đây là bản dịch",
    "bản dịch truyện ngắn",
    "đây là bản dịch",
    "sau đây là bản dịch",
    "tiếp theo là bản dịch",
    "dưới đây là phần dịch",
    "dưới đây là nội dung",
    "bản dịch tiếng việt sát nghĩa",
    "hy vọng bản dịch",
    "hi vọng bản dịch",
    "chúc bạn đọc truyện vui vẻ",
    "lưu ý:",
    "ghi chú:",
    "(lưu ý",
]


def read_docx_chunks(path):
    """Trả về list (nhãn_đoạn, nội_dung). Nếu có heading 'ĐOẠN/Đoạn k' thì gom
    nội dung theo từng đoạn; không thì mỗi paragraph là 1 mục."""
    from docx import Document
    doc = Document(str(path))
    chunks = []
    cur_label, cur_text = None, []

    def flush():
        if cur_text:
            chunks.append((cur_label or f"Đoạn {len(chunks) + 1}", "\n".join(cur_text).strip()))

    for para in doc.paragraphs:
        t = para.text.strip()
        if not t:
            continue
        style = (para.style.name or "")
        low = t.lower()
        is_heading = style.startswith("Heading") or style.startswith("Title")
        if is_heading and (low.startswith("đoạn") or low.startswith("doan")):
            flush()
            cur_label, cur_text = t, []
        elif is_heading and "kết quả dịch" in low:
            continue  # tiêu đề tổng, bỏ qua
        else:
            cur_text.append(t)
    flush()
    return chunks


def find_suspects(text):
    """Trả về list (câu_dính, đoạn_trích) cho mọi câu nghi vấn xuất hiện trong text."""
    hits = []
    low = text.lower()
    for phrase in SUSPECT_PHRASES:
        idx = low.find(phrase)
        if idx != -1:
            start = max(0, idx - 10)
            end = min(len(text), idx + len(phrase) + 40)
            snippet = text[start:end].replace("\n", " ").strip()
            hits.append((phrase, snippet))
    return hits


def check_docx(path, on_log=print):
    path = Path(path)
    if not path.exists():
        on_log(f"❌ Không tìm thấy file: {path}")
        return None

    chunks = read_docx_chunks(path)
    on_log(f"📄 Kiểm tra: {path}")
    on_log(f"📚 Tổng {len(chunks)} đoạn.\n")

    findings = []
    for label, text in chunks:
        hits = find_suspects(text)
        if hits:
            findings.append((label, hits))

    if not findings:
        on_log("✅ SẠCH — không phát hiện câu dẫn nhập/thừa nào.")
        return findings

    on_log(f"⚠️  PHÁT HIỆN {len(findings)} đoạn có câu dẫn nhập/thừa:\n")
    for label, hits in findings:
        on_log(f"  • {label}:")
        for phrase, snippet in hits:
            on_log(f"      - dính \"{phrase}\"")
            on_log(f"        → …{snippet}…")
    # Beep thông báo
    try:
        import winsound
        winsound.MessageBeep(winsound.MB_ICONHAND)
    except Exception:
        pass
    return findings


def main(argv=None):
    args = argv if argv is not None else sys.argv[1:]
    path = args[0] if args else str(DEFAULT_DOCX)
    findings = check_docx(path)
    # 1 = có phát hiện, 0 = sạch, 2 = lỗi (không có file)
    if findings is None:
        sys.exit(2)
    sys.exit(1 if findings else 0)


if __name__ == "__main__":
    main()
