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
DEFAULT_INPUT = KICHBAN_DIR / "input.docx"     # 05/09/2026: kịch bản TTS ở dạng Word

# Dòng cấu trúc cần bỏ (kể cả khi không phải Heading): tiêu đề tổng + "Đoạn k ..."
_SKIP_RE = re.compile(r"^(kết quả dịch từ gemini.*|đoạn\s*\d+.*|doan\s*\d+.*)$", re.IGNORECASE)

# Chú thích trong ngoặc cần bỏ: () và [] (kèm cả ngoặc full-width của bản gốc
# tiếng Trung: （）［］). Mỗi mẫu chỉ khớp 1 lớp ngoặc; main() lặp để xử lý ngoặc
# lồng nhau. LƯU Ý: KHÔNG bỏ ngoặc lưỡi liềm 【】 — giữ nguyên nội dung trong đó.
_ANNOTATION_RE = re.compile(
    r"\([^()]*\)|\[[^\[\]]*\]|（[^（）]*）|［[^［］]*］"
)

# Chuỗi đánh dấu ĐOẠN CHƯA DỊCH mà dich_gemini đệm vào docx khi Gemini treo/lỗi giữa
# chừng (_save_progress → "(chưa dịch)", save_results_docx → "(trống)").
# ⚠️ PHẢI kiểm TRƯỚC remove_annotations: chúng nằm trong ngoặc () nên bị _ANNOTATION_RE
# xoá sạch → mất nguyên đoạn mà KHÔNG để lại dấu vết nào trong input.txt (tập 42: mất
# đoạn 4-7/7, video ra chỉ 16 phút thay vì 35 phút).
_UNTRANSLATED_MARKS = ("(chưa dịch)", "(trống)")


def find_untranslated(text):
    """Trả về list marker 'đoạn chưa dịch' còn sót trong text (rỗng = đã dịch đủ)."""
    low = (text or "").lower()
    return [m for m in _UNTRANSLATED_MARKS if m in low]


# ── Câu DẪN NHẬP Gemini tự thêm ở đầu đoạn (08/09/2026) ─────────────────────────
# Dù đề bài đã cấm, Gemini vẫn thỉnh thoảng mở đầu bằng một dòng kiểu
# "Bản dịch tiếng Việt mạch truyện:", "Dưới đây là bản dịch tiếng Việt sát nghĩa:",
# "**Bản dịch:**". Để lọt là TTS đọc luôn câu đó lên video. Bỏ TRƯỚC khi ghi input
# (mọi đường tạo input đều gọi remove_lead_lines: _batch_prepare_input,
# _prepare_input_from_gemini, main() ở dưới):
#   • dòng chỉ gồm câu dẫn nhập (có/không ':' cuối)      → bỏ cả dòng;
#   • câu dẫn nhập đứng đầu dòng, ':' rồi nội dung theo sau → chỉ cắt phần trước ':'.
# Chỉ xét dòng BẮT ĐẦU bằng cụm trong _LEAD_STARTS, phần đầu ngắn (≤ _LEAD_MAX_LEN)
# và có chữ "bản dịch"/"phần dịch"/"dịch sang tiếng Việt" (_LEAD_KEY_RE) — để không
# cắt nhầm lời thoại thật: tập 96/100 có "theo mạch truyện thông thường…", "mạch
# truyện của chính nó…" nằm giữa câu → không đụng. Giữ nguyên dấu tô đỏ U+E000/U+E001
# bọc đoạn (dich_input_docx.wrap_red). Gặp mẫu mới thì thêm vào _LEAD_STARTS /
# _LEAD_KEY_RE (đầu dòng) hoặc _LEAD_INLINE_RE (giữa dòng), đừng viết bộ lọc khác.
_LEAD_STARTS = ("bản dịch", "dưới đây là", "sau đây là", "đây là", "tiếp theo là",
                "phần dịch", "nội dung dịch")
_LEAD_KEY_RE = re.compile(r"bản dịch|phần dịch|nội dung dịch|dịch (sang|ra) tiếng việt")
_LEAD_MAX_LEN = 80          # phần đầu (trước ':') dài hơn thì coi là câu truyện thật
_LEAD_EDGE = "*_\"'“”‘’ \t.:"   # ký tự trang trí quanh câu dẫn nhập (markdown, ngoặc kép)
_REST_EDGE = "*_ \t"        # đầu phần nội dung còn lại chỉ bỏ markdown/khoảng trắng
_split_marks_re = None      # dựng muộn: dich_input_docx import muộn dich_kiemtra ↔ file này
# Câu dẫn nhập DÍNH GIỮA dòng (tập 95/101: Gemini dịch dở vài chục chữ rồi chèn
# "Dưới đây là bản dịch tiếng Việt mượt mà, giữ trọn văn phong…:" và dịch lại từ đầu,
# không xuống dòng → "…tất cả mọiDưới đây là bản dịch…"). Chỉ cắt ĐÚNG câu dẫn nhập,
# giữ cả phần trước lẫn sau (không tự cắt bản dịch dở — xem is_result_duplicated bên
# dich_gemini: người dùng muốn tự kiểm). Mẫu CHẶT để không cắt lời thoại thật: phải có
# "dưới đây/sau đây/tiếp theo là bản dịch…" hoặc "bản dịch tiếng Việt" + chữ đặc trưng
# của Gemini (mạch truyện / sát nghĩa / mượt mà / đầy đủ…) và kết bằng ':'.
_LEAD_INLINE_RE = re.compile(
    r"(?:(?:dưới đây|sau đây|tiếp theo) là (?:bản dịch|phần dịch|nội dung dịch)[^:\n.!?]{0,70}"
    r"|bản dịch tiếng việt(?: (?:mạch truyện|sát nghĩa|mượt mà|đầy đủ|hoàn chỉnh|trọn vẹn"
    r"|tự nhiên|chi tiết|của đoạn|của truyện)[^:\n.!?]{0,60})?)\s*:\s*",
    re.IGNORECASE)


def _split_marks(line):
    """Tách dấu tô đỏ (dich_input_docx.MARK_START / MARK_END — mỗi dấu là CHUỖI, có
    kèm dấu chấm) và khoảng trắng ở hai đầu dòng → (đầu, lõi, cuối): lõi đem so khớp,
    hai đầu ghép lại nguyên vẹn."""
    global _split_marks_re
    if _split_marks_re is None:
        try:
            import dich_input_docx as inputdocx
            marks = [re.escape(inputdocx.MARK_START), re.escape(inputdocx.MARK_END)]
        except Exception:
            marks = []
        unit = "(?:" + "|".join(marks + [r"\s"]) + ")"
        _split_marks_re = re.compile(rf"^({unit}*)(.*?)({unit}*)$", re.S)
    return _split_marks_re.match(line).groups()


def remove_lead_lines(text):
    """Bỏ câu dẫn nhập Gemini tự thêm (xem chú thích trên) → (text_mới, [câu đã bỏ])."""
    out, removed = [], []
    for line in (text or "").split("\n"):
        pre, core, post = _split_marks(line)
        core_l = core.lstrip(_LEAD_EDGE)              # bỏ trang trí ĐẦU dòng (**, ngoặc kép)
        if core_l.lower().startswith(_LEAD_STARTS):
            head, sep, rest = core_l.partition(":")
            if not sep:                                # cả dòng là câu dẫn nhập, không hai chấm
                head, rest = core_l.rstrip(_LEAD_EDGE), ""
            if len(head) <= _LEAD_MAX_LEN and _LEAD_KEY_RE.search(head.lower()):
                removed.append(head.strip(_LEAD_EDGE) + ":")
                rest = rest.lstrip(_REST_EDGE)         # giữ nguyên dấu câu / ngoặc kép câu thật
                keep = pre + rest + post if rest else pre + post
                if keep.strip():
                    out.append(keep)                   # nội dung sau ':' hoặc dấu tô đỏ còn lại
                continue
        # Câu dẫn nhập dính giữa dòng → cắt riêng câu đó, giữ hai bên (cách nhau 1 khoảng trắng).
        if _LEAD_INLINE_RE.search(core):
            hits = []
            core2 = _LEAD_INLINE_RE.sub(lambda m: hits.append(m.group(0).strip()) or " ", core)
            removed.extend(hits)
            core2 = re.sub(r"[ \t]{2,}", " ", core2).strip()
            if (pre + core2 + post).strip():
                out.append(pre + core2 + post)
            continue
        out.append(line)
    return "\n".join(out), removed


# Sửa từ/cụm cố định KHI tạo input.txt: (từ_gốc, từ_thay). Gồm 2 loại:
#   • né bộ lọc  : giết→giớt, máu→máo… (TTS/nền tảng chặn từ nhạy cảm)
#   • chính tả   : tỳ→tì (tì tay · tì vết · đàn tì bà)
# Khớp được cả cụm nhiều từ (vd "sát hại"). MỘT danh sách duy nhất — thêm chữ mới
# chỉ cần nối vào đây, mọi đường tạo input.txt tự có (xem apply_word_fixes).
_WORD_FIXES = [
    ("giết", "giớt"),
    ("chết", "chớt"),
    ("sát hại", "giới hại"),
    ("máu", "máo"),
    ("ma túy", "mai thúy"),
    ("cưỡng hiếp", "cưỡng híp"),
    ("tỳ", "tì"),
    # Chỉ chữ "ĩ" ĐỨNG MỘT MÌNH: khớp nguyên tiếng nên "kĩ", "sĩ", "nghĩ",
    # "đĩa" không bị đụng — chỉ cái "ĩ" trơ trọi mới thành "ỹ".
    ("ĩ", "ỹ"),
]


def _match_case(src, new):
    """Chép kiểu hoa/thường của từ gốc sang từ thay: GIẾT→GIỚT, Giết→Giớt."""
    if src.isupper():
        return new.upper()
    if src[:1].isupper():
        return new[:1].upper() + new[1:]
    return new


def apply_word_fixes(text):
    """Thay các từ/cụm trong _WORD_FIXES (vd 'giết'→'giớt', 'tỳ'→'tì').

    Khớp NGUYÊN TỪ/TIẾNG (word boundary) nên 'tỷ' (tỷ đồng), 'tý', 'tỵ' không bị
    đụng; giữ nguyên kiểu viết hoa; ưu tiên cụm DÀI trước để tránh thay nhầm phần
    trùng (vd 'sát hại' xử lý trước 'hại')."""
    for old, new in sorted(_WORD_FIXES, key=lambda p: len(p[0]), reverse=True):
        pattern = re.compile(r"\b" + re.escape(old) + r"\b", re.IGNORECASE)
        text = pattern.sub(lambda m, n=new: _match_case(m.group(0), n), text)
    return text


def remove_annotations(text):
    """Bỏ các chú thích nằm trong dấu () và [] (kể cả ngoặc lồng nhau), rồi dọn
    khoảng trắng thừa do việc bỏ ngoặc để lại. Trả về nội dung đã làm sạch."""
    prev = None
    while prev != text:                 # lặp tới khi không còn ngoặc nào (xử lý lồng nhau)
        prev = text
        text = _ANNOTATION_RE.sub("", text)
    cleaned = []
    for line in text.split("\n"):
        line = re.sub(r"[ \t]{2,}", " ", line)         # gộp nhiều khoảng trắng
        line = re.sub(r"\s+([,.;:!?…])", r"\1", line)  # bỏ space trước dấu câu
        line = line.strip()
        if line:                        # bỏ dòng rỗng còn lại (vd dòng chỉ có chú thích)
            cleaned.append(line)
    return "\n".join(cleaned).strip()


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
                        help="File input.docx cho TTS (đuôi .txt → ghi txt thuần).")
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
    import dich_input_docx as inputdocx
    content, red_idx = inputdocx.gemini_content_marked(docx_path)   # giữ tô đỏ
    if red_idx:
        print(f"🟥 Đoạn tô đỏ trong docx (dịch nhờ câu nhắc) sẽ tô đỏ theo: {red_idx}")
    if not content:
        print(f"❌ Không lấy được nội dung nào từ: {docx_path}")
        sys.exit(2)
    # Bỏ câu dẫn nhập Gemini tự thêm ("Bản dịch tiếng Việt mạch truyện:"…) — xem
    # remove_lead_lines. Không bỏ là TTS đọc luôn câu đó.
    content, bo = remove_lead_lines(content)
    if bo:
        print(f"🧹 Bỏ {len(bo)} câu dẫn nhập của Gemini: {bo}")

    # ── CHẶN: còn đoạn CHƯA DỊCH thì dừng ngay, TRƯỚC khi bỏ chú thích ────────
    marks = find_untranslated(content)
    if marks and not args.force:
        print(f"\n⛔ DỪNG: docx còn đoạn chưa dịch {marks} → CHƯA ghi input.txt, "
              "CHƯA tạo audio.\n   Hãy chạy lại bước dịch Gemini cho các đoạn còn "
              "thiếu (hoặc chạy lại với --force nếu chấp nhận mất đoạn đó).")
        sys.exit(1)
    if marks and args.force:
        print(f"\n⚠️  Còn đoạn chưa dịch {marks} nhưng --force → vẫn ghi input.txt "
              "(input.txt sẽ THIẾU nội dung các đoạn đó).")

    # ── Bỏ chú thích trong () và [] — áp dụng SAU các bước chuẩn bị ở trên ─────
    print("🧽 BƯỚC 2b — Bỏ chú thích trong dấu () và []...")
    content = remove_annotations(content)
    if not content:
        print(f"❌ Sau khi bỏ chú thích không còn nội dung nào từ: {docx_path}")
        sys.exit(2)

    # ── Sửa từ cố định để TTS đọc đúng (vd 'giết' → 'giớt', 'tỳ' → 'tì') ──────
    print(f"✏️  BƯỚC 2c — Sửa {len(_WORD_FIXES)} từ/cụm cố định cho TTS "
          "(giết→giớt, chết→chớt, tỳ→tì, ...)...")
    content = apply_word_fixes(content)

    inputdocx.write_input(out_path, content)
    print(f"💾 BƯỚC 3 — Đã ghi {len(content)} ký tự → {out_path}")
    print("✅ SẴN SÀNG TẠO AUDIO: mở taogiong_gui.py và bấm '▶ Chạy'.")
    sys.exit(0)


if __name__ == "__main__":
    main()
