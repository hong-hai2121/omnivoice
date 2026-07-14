# -*- coding: utf-8 -*-
"""
seo_docx_parser.py — Tách TIÊU ĐỀ / MÔ TẢ / THẺ TAG từ file SEO của Gemini
(seoYoutube.docx) để dùng đăng YouTube qua API.

Định dạng Gemini trả về (nhận diện theo TỪ KHÓA, KHÔNG phụ thuộc emoji/số bước):

    ... CHỌN TIÊU ĐỀ VIDEO
        (Độ dài ...)                    ← chú thích, bỏ qua
        <các tiêu đề ứng viên> ...
    🏆 TIÊU ĐỀ TỐT NHẤT ĐƯỢC CHỌN:
        <tiêu đề>                       ← LẤY dòng ngay sau mốc này
    ... THẺ TAG ...
        (Độ dài ...)                    ← chú thích, bỏ qua
        Plaintext                       ← nhãn khối code, bỏ qua
        tag1, tag2, tag3, ...           ← dòng CSV = danh sách THẺ TAG
    ... MÔ TẢ VIDEO ...
        (Bạn chỉ cần copy ...)          ← chú thích, bỏ qua
        <toàn bộ phần còn lại>          ← gộp thành MÔ TẢ

Dùng:
    from seo_docx_parser import parse_seo_docx
    seo = parse_seo_docx("seoYoutube.docx")
    seo["title"], seo["description"], seo["tags"]   # tags là list[str]
"""

from pathlib import Path


def _norm(s):
    """Chuẩn hoá để so khớp từ khoá: gộp khoảng trắng + viết hoa (bỏ dấu giữ nguyên)."""
    return " ".join((s or "").split()).upper()


def _is_note(text):
    """Dòng chú thích trong ngoặc kiểu '(Độ dài ...)' — bỏ qua khi tách nội dung.

    Chấp nhận cả khi Gemini thêm dấu câu/nháy sau dấu ')' cuối, ví dụ '(...).' hay '(...)”'.
    """
    t = (text or "").strip()
    if not t.startswith("("):
        return False
    core = t.rstrip(" .,;:!?…。\"'’”")
    return core.endswith(")") or core.endswith("）")


def _looks_like_title(text):
    """Dòng TIÊU ĐỀ thật: ngắn gọn, không phải chú thích/câu dẫn.

    Loại bỏ: dòng chú thích '(...)'; dòng MỐC kết thúc bằng ':' (vd 'Tiêu đề quán
    quân tốt nhất:'); và CÂU MỞ ĐẦU dài dòng của Gemini (vd 'Dưới đây là 5 tiêu đề
    được thiết kế chuẩn SEO...') — vốn hay bị lấy nhầm làm tiêu đề.
    """
    t = (text or "").strip()
    if not t or _is_note(t):
        return False
    if t.endswith(":") or t.endswith("："):
        return False
    return len(t) <= 110 and len(t.split()) <= 18


# Nhãn rác do Gemini chèn khi xuất khối code (không phải nội dung thật).
_CODE_LABELS = {"PLAINTEXT", "PLAIN TEXT", "TEXT", "CODE", "MARKDOWN"}

# Câu hướng dẫn Gemini hay chèn đầu phần Mô tả — luôn bỏ khỏi mô tả dù nằm ở đâu.
_DESC_SKIP_PHRASES = ("copy toàn bộ nội dung", "dán vào phần mô tả")


def _is_desc_hint(text):
    """Dòng hướng dẫn 'copy ... dán vào phần mô tả' — không phải nội dung mô tả thật."""
    t = _norm(text)
    return any(_norm(p) in t for p in _DESC_SKIP_PHRASES)


def _read_paragraphs(path):
    """Đọc (text, is_heading) của từng paragraph đã strip, GIỮ NGUYÊN thứ tự.

    GIỮ luôn Heading/Title thay vì bỏ: khi người dùng DÁN nội dung Gemini vào Word,
    các mốc mục ('BƯỚC 3: THẺ TAG', 'BƯỚC 4: MÔ TẢ VIDEO') hay bị Word gán style
    Heading — nếu bỏ thì không định vị được THẺ TAG / MÔ TẢ (mất tag + mô tả). Cờ
    is_heading để phần tách TIÊU ĐỀ tránh nhặt nhầm dòng mốc làm tiêu đề.
    """
    from docx import Document
    doc = Document(str(path))
    out = []
    for p in doc.paragraphs:
        style = p.style.name or ""
        is_heading = style.startswith("Heading") or style.startswith("Title")
        out.append((p.text.strip(), is_heading))
    return out


def _title_after_marker(line):
    """Tiêu đề nằm CÙNG dòng với mốc (kiểu DÁN: 'TIÊU ĐỀ TỐT NHẤT ĐƯỢC CHỌN: <tiêu đề>').

    Tách phần sau dấu ':' (hoặc '：') ĐẦU TIÊN — chính là dấu hai chấm của mốc, nên
    phần còn lại là tiêu đề nguyên vẹn. Không có ':' hoặc sau ':' rỗng → trả ''.
    """
    for sep in (":", "："):
        if sep in line:
            return line.split(sep, 1)[1].strip()
    return ""


def parse_seo_docx(path):
    """Trả về dict {'title': str, 'description': str, 'tags': list[str]}."""
    rows = _read_paragraphs(path)
    paras = [t for t, _ in rows]
    heads = [h for _, h in rows]
    n = len(paras)

    def find(keyword):
        kw = keyword.upper()
        for i, t in enumerate(paras):
            if kw in _norm(t):
                return i
        return -1

    # Mốc "tiêu đề tốt nhất": khớp nhiều cách Gemini diễn đạt — "TIÊU ĐỀ TỐT NHẤT
    # ĐƯỢC CHỌN" hoặc "Tiêu đề QUÁN QUÂN tốt nhất" (có 'quán quân' chen giữa).
    i_best = find("TIÊU ĐỀ TỐT NHẤT")
    if i_best < 0:
        i_best = find("QUÁN QUÂN")
    if i_best < 0:
        i_best = find("TỐT NHẤT")
    i_tag = find("THẺ TAG")
    i_desc = find("MÔ TẢ VIDEO")
    if i_desc < 0:
        i_desc = find("MÔ TẢ")

    # ── TIÊU ĐỀ: ưu tiên phần CÙNG dòng với mốc (kiểu dán), sau đó tới dòng kế ──
    title = ""
    if i_best >= 0:
        # Kiểu DÁN: 'TIÊU ĐỀ TỐT NHẤT ĐƯỢC CHỌN: <tiêu đề>' — tiêu đề nằm ngay trên dòng mốc.
        same_line = _title_after_marker(paras[i_best])
        if _looks_like_title(same_line):
            title = same_line
        else:
            # Kiểu Gemini gốc: tiêu đề ở dòng NỘI DUNG kế tiếp (bỏ qua các dòng mốc/heading
            # như 'Plaintext' không phải heading nhưng dòng mốc BƯỚC 3/4 thì bỏ nhờ heads).
            for idx in range(i_best + 1, n):
                if heads[idx]:
                    continue
                if _looks_like_title(paras[idx]):
                    title = paras[idx]
                    break
    # Dự phòng: chưa có mốc "tốt nhất" thì lấy ứng viên đầu trong mục chọn tiêu đề
    # (bỏ qua câu mở đầu dài dòng nhờ _looks_like_title).
    if not title:
        i_pick = find("CHỌN TIÊU ĐỀ")
        if i_pick >= 0:
            for t in paras[i_pick + 1:]:
                if _looks_like_title(t):
                    title = t
                    break

    # ── THẺ TAG: dòng CSV (nhiều dấu phẩy nhất) trong khoảng [i_tag, i_desc) ──
    tags = []
    if i_tag >= 0:
        end = i_desc if i_desc > i_tag else n
        best_line = ""
        for t in paras[i_tag + 1:end]:
            if not t or _is_note(t) or _norm(t) in _CODE_LABELS:
                continue
            if t.count(",") > best_line.count(","):
                best_line = t
        tags = [x.strip() for x in best_line.split(",") if x.strip()]

    # ── MÔ TẢ: từ sau dòng chú thích của mục Mô tả tới hết tài liệu ──
    description = ""
    if i_desc >= 0:
        start = i_desc + 1
        while start < n and (not paras[start] or _is_note(paras[start])):
            start += 1
        desc_lines = [ln for ln in paras[start:] if not _is_desc_hint(ln)]
        while desc_lines and not desc_lines[-1]:   # bỏ dòng trống ở cuối
            desc_lines.pop()
        description = "\n".join(desc_lines).strip()

    # ── Tổng hợp lỗi CẤU TRÚC để báo cho người dùng nếu Gemini trả khác mong đợi ──
    issues = []
    if n == 0:
        issues.append("File chưa có nội dung SEO (rỗng).")
    else:
        if not title:
            issues.append("Không tìm thấy TIÊU ĐỀ "
                          "(thiếu mục 'TIÊU ĐỀ TỐT NHẤT' hoặc 'CHỌN TIÊU ĐỀ').")
        if not tags:
            issues.append("Không tìm thấy THẺ TAG "
                          "(thiếu mục 'THẺ TAG' hoặc dòng tag ngăn cách bằng dấu phẩy).")
        if not description:
            issues.append("Không tìm thấy MÔ TẢ (thiếu mục 'MÔ TẢ VIDEO').")

    return {"title": title, "description": description, "tags": tags, "issues": issues}


if __name__ == "__main__":
    import sys
    src = sys.argv[1] if len(sys.argv) > 1 else str(
        Path(__file__).resolve().parent.parent / "kịch_bản" / "seoYoutube.docx"
    )
    seo = parse_seo_docx(src)
    if seo["issues"]:
        print("⚠️ CẢNH BÁO CẤU TRÚC:")
        for s in seo["issues"]:
            print("  •", s)
        print()
    print("===== TIÊU ĐỀ =====")
    print(seo["title"], f"({len(seo['title'])} ký tự)")
    print("\n===== THẺ TAG =====")
    print(f"{len(seo['tags'])} tag | tổng {sum(len(t) for t in seo['tags'])} ký tự")
    print(", ".join(seo["tags"]))
    print("\n===== MÔ TẢ =====")
    print(seo["description"])
