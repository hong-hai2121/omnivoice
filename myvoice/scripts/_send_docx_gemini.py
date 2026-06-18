# -*- coding: utf-8 -*-
"""Tạm thời: gửi nội dung 1 file .docx (đã tách ĐOẠN) lên Gemini tuần tự. Xoá sau."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from docx import Document
import gemini_client as g

DOCX = r"D:\Python\omnivoice\OmniVoice\myvoice\kịch_bản\已完结复仇 爽文一口气看完更过瘾_哔哩哔哩_bilibili_zh.docx"
PREFIX_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "copy_prefix.txt")


def read_chunks(path):
    """Mỗi paragraph nội dung (không phải Heading/Title) = 1 đoạn đã lưu."""
    doc = Document(path)
    out = []
    for para in doc.paragraphs:
        style = (para.style.name or "")
        t = para.text.strip()
        if not t or style.startswith("Heading") or style.startswith("Title"):
            continue
        out.append(t)
    return out


prefix = ""
if os.path.exists(PREFIX_FILE):
    prefix = open(PREFIX_FILE, encoding="utf-8").read().strip()

chunks = read_chunks(DOCX)
print(f"📚 {len(chunks)} đoạn | prefix {len(prefix)} ký tự | bắt đầu gửi Gemini...", flush=True)

results = g.send_chunks_to_gemini(
    chunks, prefix=prefix,
    on_log=lambda m: print(m, flush=True),
    on_result=lambda i, total, ans: print(
        f"\n========== KẾT QUẢ ĐOẠN {i+1}/{total} ==========\n{ans}\n", flush=True
    ),
    keep_open=True,   # để Firefox mở cho bạn xem/đối chiếu
)

out = os.path.splitext(DOCX)[0] + "_gemini.docx"
g.save_results_docx(chunks, results, out)
ok = sum(1 for r in results if r and r.strip())
print(f"\n💾 ĐÃ LƯU: {out}", flush=True)
print(f"✅ HOÀN TẤT: {ok}/{len(results)} đoạn có kết quả.", flush=True)
