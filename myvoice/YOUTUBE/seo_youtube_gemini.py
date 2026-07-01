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
# CHỈ làm khi CHẠY THẲNG file này (python seo_youtube_gemini.py). Khi được GUI
# import (import seo_youtube_gemini), TUYỆT ĐỐI không tự chuyển: lúc đó sys.argv[0]
# là amain_taogiong_gui.py nên subprocess.run sẽ MỞ LẠI GUI (GUI bật 2 lần) rồi
# sys.exit() giết luôn thread SEO → SEO YouTube không chạy. Dùng normcase để tránh
# lệch hoa/thường ổ đĩa ("d:" vs "D:") gây tự chuyển nhầm.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
_VENV_PYTHON = os.path.join(_REPO_ROOT, "venv", "Scripts", "python.exe")
if __name__ == "__main__" and os.path.exists(_VENV_PYTHON) and \
        os.path.normcase(os.path.abspath(sys.executable)) != \
        os.path.normcase(os.path.abspath(_VENV_PYTHON)):
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

import time
import argparse
from pathlib import Path

import dich_gemini as g
from dich_docx import read_chunks

# ── Link cuộc trò chuyện Gemini chuyên SEO YouTube (đã có sẵn chỉ dẫn) ─────────
# CHỈ giữ phần /app/<id> — KHÔNG kèm tham số quảng cáo (gclid, utm_*, campaign_id,
# is_sa...). Link 1 cuộc trò chuyện CỤ THỂ mà còn dính tham số chiến dịch thì Gemini
# hay BỎ id rồi mở CHAT MỚI → SEO gửi nhầm vào trò chuyện trống (mất ngữ cảnh đã
# huấn luyện). Vì vậy luôn cắt bỏ phần query (kể cả khi đặt qua biến môi trường).
SEO_GEMINI_URL = os.environ.get(
    "OMNI_SEO_GEMINI_URL",
    "https://gemini.google.com/app/e1a7ace4a71c48b2",
).split("?", 1)[0].strip()


def _seo_conversation_id():
    """ID cuộc trò chuyện trong SEO_GEMINI_URL (phần sau '/app/'); '' nếu không có."""
    if "/app/" not in SEO_GEMINI_URL:
        return ""
    return SEO_GEMINI_URL.split("/app/", 1)[-1].split("/", 1)[0].strip()


def _open_seo_chat(driver, log, wait=8):
    """Điều hướng Firefox sang ĐÚNG cuộc trò chuyện SEO và XÁC NHẬN Gemini không
    đẩy sang chat mới. Thử lại 1 lần nếu bị mở chat mới. True nếu đang ở đúng chat."""
    conv_id = _seo_conversation_id()
    last = ""
    for attempt in (1, 2):
        driver.get(SEO_GEMINI_URL)
        time.sleep(wait)
        last = driver.current_url or ""
        if not conv_id or conv_id in last:
            return True
        log(f"⚠️ Lần {attempt}: Gemini mở CHAT MỚI ({last}) thay vì cuộc trò chuyện "
            f"SEO ({conv_id}) — thử lại...")
    log(f"❗ KHÔNG vào được cuộc trò chuyện SEO (đang ở {last}). KHÔNG gửi để tránh "
        "tạo SEO sai. Kiểm tra lại link OMNI_SEO_GEMINI_URL và đăng nhập Gemini.")
    return False

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


def run(input_path, output_path, max_chars=0, keep_open=True, log=print, driver=None):
    """driver: truyền 1 Firefox/driver đang mở để TÁI DÙNG (chỉ điều hướng sang cuộc
    trò chuyện SEO). Nhờ vậy không phải đóng rồi mở lại Firefox — tránh kẹt khóa
    profile khiến lần mở thứ hai thất bại. None thì tự mở Firefox mới."""
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

    own_driver = driver is None
    try:
        if driver is None:
            driver = g.init_firefox(url=SEO_GEMINI_URL)
        # Luôn điều hướng + XÁC NHẬN đang ở đúng cuộc trò chuyện SEO (kể cả khi tái
        # dùng Firefox đang ở chat dịch). Sai chat → DỪNG, không gửi nhầm ra chat mới.
        if not _open_seo_chat(driver, log):
            save_seo_docx("", output_path)   # giữ file rỗng để lần sau chạy lại SEO
            return ""
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
        if own_driver and not keep_open and driver is not None:
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
