# -*- coding: utf-8 -*-
"""
dich_input_docx.py — File KỊCH BẢN đầu vào TTS ở dạng Word: input.docx.

05/09/2026: người dùng yêu cầu đổi hẳn input.txt → input.docx, để mở/sửa/kiểm trong
Word và giữ được MÀU: đoạn dịch được nhờ câu nhắc sau khi Gemini từ chối (xem
dich_gemini.REFUSAL_NUDGE / read_red_marks) được TÔ ĐỎ cả trong gemini_result.docx
lẫn input.docx.

Quy ước dùng chung cho mọi nơi:
  • GHI  → write_input(path, content): CHUẨN HOÁ (normalize_for_input) rồi ghi — đuôi
           .docx → docx (có tô đỏ), đuôi khác → txt.
  • ĐỌC  → read_input_text(path): nhận cả .docx lẫn .txt (tập cũ chỉ có input.txt
           vẫn chạy được, không phải tạo lại).
  • TÌM  → find_input(folder): input.docx (chuẩn) → input.txt (tập cũ) → None.
  • Ô "Văn bản" còn lưu đường dẫn .txt cũ → resolve_input(path) tự đổi sang file
    cùng tên đuôi kia nếu file đã lưu không còn.

Chuẩn hoá khi ghi (yêu cầu 05/09/2026, xem normalize_for_input): nội dung là MỘT
ĐOẠN LIỀN — không xuống dòng, không dòng trắng; bỏ hết gạch ngang dài/ngắn — –, nháy
kép “ ” ", nháy đơn ‘ ’ '; gọn khoảng trắng. clean_text lúc tạo giọng vốn đã bỏ các
dấu này, nay bỏ ngay trong file để mở Word thấy sạch. Hệ quả: không còn ký tự "\\n"
nên lúc ghép audio không có chỗ nghỉ dài "hết đoạn văn", chỉ còn nghỉ theo dấu câu.

Đánh dấu đoạn đỏ khi DỰNG nội dung (trước các bước dọn câu quảng bá / sửa từ /
bỏ chú thích): bọc đoạn bằng wrap_red() → MARK_START và MARK_END, mỗi dấu là MỘT
DÒNG riêng kết thúc bằng "." để replace_channel_promo (tách câu theo dấu kết câu,
xoá câu quảng bá) coi nó là một câu độc lập, không bị xoá theo câu đứng cạnh.
Các bước dọn không đụng tới ký tự vùng riêng U+E000/U+E001 (dich_hanviet đã sửa dải
Hán 05/09/2026 để không nuốt chúng). Khi ghi, dấu được gỡ và phần nằm giữa tô đỏ;
strip_marks() bỏ dấu cho bản .txt.
"""

from __future__ import annotations

import re
from pathlib import Path

INPUT_NAME = "input.docx"
LEGACY_INPUT_NAME = "input.txt"
INPUT_NAMES = (INPUT_NAME, LEGACY_INPUT_NAME)

MARK_START = "."
MARK_END = "."
_MARK_RE = re.compile(r"([])\.?")
RED_RGB = (0xC0, 0x00, 0x00)

# Ký tự BỎ khi ghi input (yêu cầu 05/09/2026): gạch ngang dài/ngắn (→ khoảng trắng để
# hai chữ hai bên không dính nhau), nháy kép cong/thẳng, nháy đơn cong/thẳng.
_DASH_RE = re.compile(r"[—–]+")
_QUOTE_RE = re.compile(r"[“”\"‘’']")
_WS_RE = re.compile(r"[ \t ]+")
_SPACE_BEFORE_PUNCT_RE = re.compile(r" +([,.;:!?…])")
# Dấu tô đỏ kèm khoảng trắng/xuống dòng bao quanh → giữ dấu + đúng một khoảng trắng sau.
_MARK_WS_RE = re.compile(r"\s*([])\.?\s*")


# ── Tìm / kiểm file ──────────────────────────────────────────────────────────
def input_path(folder) -> Path:
    """Đường dẫn CHUẨN để ghi kịch bản mới của một thư mục tập."""
    return Path(folder) / INPUT_NAME


def has_content(path) -> bool:
    """File có tồn tại và có chữ không (docx rỗng vẫn nặng vài KB nên phải đọc)."""
    try:
        p = Path(path)
        if not p.is_file() or p.stat().st_size == 0:
            return False
        if p.suffix.lower() == ".docx":
            return bool(read_input_text(p).strip())
        return True
    except Exception:
        return False


def find_input(folder) -> Path | None:
    """File kịch bản CÓ NỘI DUNG của thư mục tập: input.docx trước, input.txt (tập
    cũ) sau; không có → None."""
    folder = Path(folder)
    for name in INPUT_NAMES:
        p = folder / name
        if has_content(p):
            return p
    return None


def input_for(folder) -> Path:
    """File kịch bản để ĐỌC của thư mục tập: bản có nội dung (docx/txt) nếu có, không
    thì đường dẫn chuẩn input.docx (bên gọi tự báo thiếu)."""
    return find_input(folder) or input_path(folder)


def resolve_input(path) -> Path:
    """Đường dẫn người dùng đưa (ô 'Văn bản'/--input): file không có → thử file cùng
    tên với đuôi kia (input.txt ↔ input.docx). Vẫn không có → trả nguyên để bên gọi
    báo lỗi đúng tên."""
    p = Path(path)
    if p.is_file():
        return p
    other = {".docx": ".txt", ".txt": ".docx"}.get(p.suffix.lower())
    if other:
        alt = p.with_suffix(other)
        if alt.is_file():
            return alt
    return p


# ── Đọc ─────────────────────────────────────────────────────────────────────
def read_input_text(path) -> str:
    """Nội dung chữ của kịch bản: .docx → mỗi paragraph một dòng; khác → đọc txt."""
    p = Path(path)
    if p.suffix.lower() == ".docx":
        from docx import Document
        doc = Document(str(p))
        return "\n".join(para.text for para in doc.paragraphs)
    try:
        return p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return p.read_text(encoding="utf-8-sig", errors="replace")


# ── Đánh dấu đỏ ─────────────────────────────────────────────────────────────
def wrap_red(text: str) -> str:
    """Bọc một đoạn để write_input tô đỏ (dấu đứng riêng dòng — xem đầu file)."""
    return f"{MARK_START}\n{text}\n{MARK_END}"


def strip_marks(text: str) -> str:
    """Bỏ mọi dấu đánh dấu đỏ (khi chỉ cần chữ)."""
    return _MARK_RE.sub("", text or "")


def gemini_content_marked(gemini_docx) -> tuple[str, list[int]]:
    """Nội dung ghép từ gemini_result.docx (bỏ tiêu đề / 'Đoạn k'), đoạn nào đang
    TÔ ĐỎ trong docx thì bọc wrap_red. → (nội_dung, danh_sách_đoạn_đỏ)."""
    import dich_kiemtra as cg
    import dich_gemini as g
    chunks = cg.read_docx_chunks(gemini_docx)          # [(nhãn, nội dung)]
    red = g.read_red_marks(gemini_docx, len(chunks))
    parts, red_idx = [], []
    for k, (label, text) in enumerate(chunks, 1):
        m = re.search(r"\d+", label or "")
        j = int(m.group()) if m else k
        if j in red or k in red:
            parts.append(wrap_red(text))
            red_idx.append(j)
        else:
            parts.append(text)
    return "\n".join(parts).strip(), red_idx


# ── Chuẩn hoá ───────────────────────────────────────────────────────────────
def normalize_for_input(text: str) -> str:
    """Nội dung cuối để ghi input: MỘT đoạn liền, không xuống dòng / dòng trắng; bỏ
    — – “ ” " ‘ ’ '; gọn khoảng trắng; không có khoảng trắng trước dấu câu. Dấu tô đỏ
    (U+E000/U+E001) được giữ, kèm đúng một khoảng trắng sau dấu."""
    t = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    t = _QUOTE_RE.sub("", t)
    t = _DASH_RE.sub(" ", t)
    t = _MARK_WS_RE.sub(lambda m: m.group(1) + " ", t)
    t = re.sub(r"\s*\n\s*", " ", t)          # mọi xuống dòng → một khoảng trắng
    t = _WS_RE.sub(" ", t)
    t = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", t)
    return t.strip()


# ── Ghi ─────────────────────────────────────────────────────────────────────
def write_input(path, content: str) -> Path:
    """Chuẩn hoá (normalize_for_input) rồi ghi kịch bản: đuôi .docx → Word (phần giữa
    MARK_START/MARK_END tô đỏ), đuôi khác → txt thuần (bỏ dấu). Tạo thư mục cha nếu
    thiếu."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    content = normalize_for_input(content or "")
    if p.suffix.lower() == ".docx":
        _write_docx(p, content)
    else:
        p.write_text(strip_marks(content), encoding="utf-8")
    return p


def _write_docx(path: Path, content: str) -> None:
    from docx import Document
    from docx.shared import RGBColor

    doc = Document()
    red = False
    for line in content.split("\n"):           # sau chuẩn hoá thường chỉ còn 1 dòng
        pieces = _MARK_RE.split(line)          # [chữ, dấu, chữ, dấu, ..., chữ]
        if len(pieces) == 1:                   # dòng không có dấu
            _add_para(doc, line, red, RGBColor)
            continue
        runs = []
        for idx, piece in enumerate(pieces):
            if idx % 2 == 1:                   # dấu → đổi trạng thái
                red = (piece == "")
            elif piece:
                runs.append((piece, red))
        if any(t.strip() for t, _ in runs):
            para = doc.add_paragraph()
            for t, is_red in runs:
                run = para.add_run(t)
                if is_red and t.strip():
                    run.font.color.rgb = RGBColor(*RED_RGB)
    doc.save(str(path))


def _add_para(doc, line: str, red: bool, RGBColor) -> None:
    para = doc.add_paragraph()
    if line:
        run = para.add_run(line)
        if red and line.strip():
            run.font.color.rgb = RGBColor(*RED_RGB)


def red_lines(path) -> list[int]:
    """Số paragraph (1-based) có chữ tô đỏ trong input.docx — để kiểm/thử."""
    from docx import Document
    out = []
    try:
        doc = Document(str(path))
    except Exception:
        return out
    for i, para in enumerate(doc.paragraphs, 1):
        for run in para.runs:
            try:
                rgb = run.font.color.rgb if run.font.color is not None else None
            except Exception:
                rgb = None
            if rgb is not None and rgb[0] >= 0xB0 and rgb[1] <= 0x40 and rgb[2] <= 0x40:
                out.append(i)
                break
    return out


def red_text(path) -> str:
    """Toàn bộ chữ đang tô đỏ trong input.docx (nối lại) — để kiểm/thử."""
    from docx import Document
    parts = []
    try:
        doc = Document(str(path))
    except Exception:
        return ""
    for para in doc.paragraphs:
        for run in para.runs:
            try:
                rgb = run.font.color.rgb if run.font.color is not None else None
            except Exception:
                rgb = None
            if rgb is not None and rgb[0] >= 0xB0 and rgb[1] <= 0x40 and rgb[2] <= 0x40:
                parts.append(run.text)
    return "".join(parts)
