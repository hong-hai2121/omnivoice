# -*- coding: utf-8 -*-
"""
seo_youtube_gemini.py — Lấy ĐOẠN ĐẦU của nội dung đã dịch (gemini_result.docx),
gửi NGUYÊN VĂN (KHÔNG kèm câu lệnh / yêu cầu nào) lên một cuộc trò chuyện Gemini
đã được tạo sẵn cho việc SEO YouTube, rồi lưu kết quả ra seoYoutube.docx.

Ý tưởng:
• Cuộc trò chuyện Gemini ở link bên dưới ĐÃ ĐƯỢC HUẤN LUYỆN/RA ĐỀ trước (đã có
  sẵn chỉ dẫn "viết tiêu đề + mô tả + hashtag SEO cho YouTube"). Vì vậy script
  này chỉ cần DÁN đoạn đầu của truyện vào là Gemini tự trả về phần SEO.
• Không chèn prefix/câu lệnh — đúng yêu cầu "chỉ gửi nội dung".

Chạy:
    python seo_youtube_gemini.py                          # dùng gemini_result.docx mặc định
    python seo_youtube_gemini.py "gemini_result.docx"     # đổi file nguồn
    python seo_youtube_gemini.py -o "seoYoutube.docx"      # đổi file kết quả
    python seo_youtube_gemini.py --chars 1500             # cắt còn N ký tự đầu (0 = cả đoạn)
    python seo_youtube_gemini.py --no-keep-open           # đóng Firefox sau khi xong
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

# Thư mục hiện tại (myvoice/YOUTUBE) + thư mục scripts (nơi có dich_gemini.py,
# dich_docx.py). Thêm cả hai vào sys.path để import được.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_DIR = os.path.join(os.path.dirname(_THIS_DIR), "scripts")
for _p in (_THIS_DIR, _SCRIPTS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import argparse
from pathlib import Path

import dich_gemini as g
from dich_docx import read_chunks

# ── Link cuộc trò chuyện Gemini chuyên SEO YouTube (đã có sẵn chỉ dẫn) ─────────
SEO_GEMINI_URL = os.environ.get(
    "OMNI_SEO_GEMINI_URL",
    "https://gemini.google.com/app/e1a7ace4a71c48b2?is_sa=1&is_sa=1"
    "&android-min-version=301356232&ios-min-version=322.0&campaign_id=bkws"
    "&utm_source=sem&utm_medium=paid-media&utm_campaign=bkws&pt=9008&mt=8"
    "&ct=p-growth-sem-bkws&gclsrc=aw.ds&gad_source=1&gad_campaignid=22165684207"
    "&gbraid=0AAAAApk5BhlAGVEaouhBwUbsMM3XYJIlr"
    "&gclid=CjwKCAjw0dPRBhAPEiwAE5vTTiQwe0DnA-Gqs0gZrpcA0Bn0KiLcRqrSG-SAFggRkHJoRJ6Lb_wKDhoCkCAQAvD_BwE",
)

# ── Đường dẫn mặc định ───────────────────────────────────────────────────────
KICHBAN_DIR = Path(_SCRIPTS_DIR).parent / "kịch_bản"
DEFAULT_INPUT = KICHBAN_DIR / "gemini_result.docx"
DEFAULT_OUTPUT = KICHBAN_DIR / "seoYoutube.docx"


def first_chunk(path):
    """Lấy đoạn nội dung ĐẦU TIÊN (bỏ Heading/Title) trong file .docx đã dịch."""
    chunks = read_chunks(path)
    return chunks[0] if chunks else ""


def save_seo_docx(content, out_path):
    """Lưu phần SEO YouTube ra .docx (1 mục, giữ nguyên xuống dòng từ Gemini)."""
    from docx import Document
    doc = Document()
    doc.add_heading("SEO YouTube (Gemini)", level=1)
    for line in (content or "(trống)").splitlines() or ["(trống)"]:
        doc.add_paragraph(line)
    doc.save(str(out_path))
    return out_path


def reset_docx(out_path):
    """Làm RỖNG file kết quả ngay đầu mỗi lần chạy: ghi đè bằng .docx hợp lệ nhưng
    chưa có nội dung (chỉ tiêu đề). Nhờ vậy nếu lần chạy này lỗi giữa chừng thì
    file cũng không còn dính kết quả của lần chạy trước."""
    from docx import Document
    doc = Document()
    doc.add_heading("SEO YouTube (Gemini)", level=1)
    doc.save(str(out_path))
    return out_path


def run(input_path, output_path, max_chars=0, keep_open=True, log=print):
    text = first_chunk(input_path)
    if not text:
        log(f"❌ Không đọc được đoạn đầu từ: {input_path}")
        return ""
    if max_chars and max_chars > 0:
        text = text[:max_chars]

    log(f"📄 Nguồn : {input_path}")
    log(f"💾 Kết quả: {output_path}")

    # Làm RỖNG file kết quả trước, rồi mới gửi & ghi nội dung mới của lần chạy này.
    reset_docx(output_path)
    log("🧹 Đã làm rỗng file kết quả (sẽ ghi nội dung mới sau khi Gemini trả lời).")

    log(f"📤 Gửi đoạn đầu ({len(text)} ký tự) — KHÔNG kèm câu lệnh — lên Gemini SEO...")

    driver = None
    try:
        driver = g.init_firefox(url=SEO_GEMINI_URL)
        log("✅ Đã mở cuộc trò chuyện Gemini SEO. Đang gửi nội dung...")
        # prefix="" → chỉ gửi nguyên văn nội dung, không thêm yêu cầu gì.
        ans = g.send_to_gemini(driver, text, prefix="", on_log=log)
        if not ans:
            log("⚠️ Gemini không trả về kết quả SEO.")
            ans = ""
        save_seo_docx(ans, output_path)
        log(f"\n========== KẾT QUẢ SEO YOUTUBE ==========\n{ans or '(trống)'}\n")
        log(f"✅ XONG: đã lưu SEO → {output_path}")
        return ans
    finally:
        if not keep_open and driver is not None:
            try:
                driver.quit()
            except Exception:
                pass


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Gửi đoạn đầu của truyện (đã dịch) lên Gemini SEO YouTube và lưu kết quả."
    )
    parser.add_argument("input", nargs="?", default=str(DEFAULT_INPUT),
                        help="File .docx nguồn (mặc định: gemini_result.docx).")
    parser.add_argument("-o", "--output", default=str(DEFAULT_OUTPUT),
                        help="File .docx lưu kết quả (mặc định: seoYoutube.docx).")
    parser.add_argument("--chars", type=int, default=0,
                        help="Chỉ gửi N ký tự đầu của đoạn (0 = cả đoạn).")
    parser.add_argument("--no-keep-open", dest="keep_open", action="store_false",
                        help="Đóng Firefox sau khi xong.")
    args = parser.parse_args(argv)

    run(args.input, args.output, max_chars=args.chars, keep_open=args.keep_open)


if __name__ == "__main__":
    main()
