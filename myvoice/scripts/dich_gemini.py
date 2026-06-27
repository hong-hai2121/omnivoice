# -*- coding: utf-8 -*-
"""
dich_gemini.py — Mở Firefox bằng Selenium, vào Gemini (gemini.google.com),
gửi từng ĐOẠN văn bản (đã tách ở bước nhận diện) rồi lấy kết quả trả về.

Tương tự src/browser_client.py của dự án GetLinktoText (gửi ChatGPT), nhưng nhắm
vào Gemini. Dùng được theo 2 cách:

1) Gọi từ GUI nhận diện (nhandien_gui.py) — sau khi nhận diện + chia đoạn xong,
   bấm nút "🤖 Gửi Gemini":
       send_chunks_to_gemini(chunks, prefix=..., on_log=..., on_result=...)

2) Chạy thẳng từ terminal:
       python dich_gemini.py "đường_dẫn.txt_hoặc_.docx"
   → đọc nội dung, tách đoạn, gửi Gemini, in kết quả + lưu *_gemini.docx.

LƯU Ý QUAN TRỌNG
----------------
• Profile Firefox phải là profile đã ĐĂNG NHẬP Google/Gemini. Firefox đang mở
  bằng profile đó phải ĐÓNG trước (Firefox khoá profile khi đang chạy).
• Gemini là web app động, các CSS selector (ô nhập / nút gửi / khối trả lời) có
  thể đổi theo phiên bản. Nếu không gửi/nhận được, chỉnh các hằng
  EDITOR_SELECTORS / SEND_SELECTORS / RESPONSE_SELECTORS bên dưới.
"""

import sys
import os

# ── Tự chuyển sang python của venv (giống taogiong_gui.py / nhandien_gui.py) ────
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

import time
from pathlib import Path

# ── Cấu hình (có thể override bằng biến môi trường) ──────────────────────────
GEMINI_URL = os.environ.get(
    "OMNI_GEMINI_URL",
    "https://gemini.google.com/app?is_sa=1&is_sa=1&android-min-version=301356232"
    "&ios-min-version=322.0&campaign_id=bkws&utm_source=sem&utm_medium=paid-media"
    "&utm_campaign=bkws&pt=9008&mt=8&ct=p-growth-sem-bkws&gclsrc=aw.ds&gad_source=1"
    "&gad_campaignid=22165684207"
    "&gclid=Cj0KCQjwrs7RBhDuARIsAIVfBD1R7j08CXiARVLmZzwZaiMkH_d7zXm5NRAxdmHBfahGH6HY1ZghbUIaAifpEALw_wcB",
)

# Firefox + geckodriver. Tái dùng geckodriver có sẵn của dự án GetLinktoText.
FIREFOX_BINARY = os.environ.get(
    "OMNI_FIREFOX_BINARY", r"C:\Program Files\Mozilla Firefox\firefox.exe"
)
GECKODRIVER_PATH = os.environ.get(
    "OMNI_GECKODRIVER", r"D:\Python\GetLinktoText\geckodriver.exe"
)
# Profile Firefox đã đăng nhập Google. Đổi qua biến môi trường OMNI_FIREFOX_PROFILE
# nếu tài khoản Gemini của bạn nằm ở profile khác.
FIREFOX_PROFILE_PATH = os.environ.get(
    "OMNI_FIREFOX_PROFILE",
    r"C:\Users\PC\AppData\Roaming\Mozilla\Firefox\Profiles\jf2te79d.default-release",
)

# Thời gian chờ Gemini trả lời mỗi đoạn (giây) và thời gian "đứng yên" để coi là xong.
RESPONSE_TIMEOUT = int(os.environ.get("OMNI_GEMINI_TIMEOUT", "300"))
RESPONSE_SETTLE = float(os.environ.get("OMNI_GEMINI_SETTLE", "6"))

# ── Selector cho Gemini (đã dò trên Gemini thật 2026-06; chỉnh nếu DOM đổi) ───
# Ô nhập lệnh: Gemini dùng trình soạn thảo Quill (div.ql-editor contenteditable,
# role=textbox, aria-label="Nhập câu lệnh cho Gemini").
EDITOR_SELECTORS = [
    "div.ql-editor[contenteditable='true']",
    "rich-textarea div.ql-editor",
    "div[contenteditable='true'][role='textbox']",
    "textarea",
]
# Nút gửi: aria-label="Gửi tin nhắn" (en: "Send message"), bên trong là
# mat-icon[fonticon='arrow_upward']. fonticon độc lập ngôn ngữ nên đặt cuối làm
# fallback chắc ăn. Chỉ hiện sau khi đã gõ chữ.
SEND_SELECTORS = [
    "button[aria-label='Gửi tin nhắn']",
    "button[aria-label='Send message']",
    "button[aria-label*='Gửi']",
    "button[aria-label*='Send']",
    "button.send-button",
    "button:has(mat-icon[fonticon='arrow_upward'])",
]
# Khối chứa câu trả lời của model. <message-content> trả về text sạch và chỉ có
# ở câu trả lời (câu hỏi của người dùng dùng phần tử khác) nên dùng làm chính.
RESPONSE_SELECTORS = [
    "message-content",
    ".markdown",
    ".model-response-text",
    "model-response",
]


def _ensure_selenium():
    """Import selenium, báo lỗi rõ ràng nếu chưa cài."""
    try:
        import selenium  # noqa: F401
    except ImportError as e:
        raise RuntimeError(
            "Chưa cài selenium. Chạy:  "
            f'"{_VENV_PYTHON}" -m pip install selenium'
        ) from e


# ── Khởi tạo Firefox ─────────────────────────────────────────────────────────
def init_firefox(profile=None, url=GEMINI_URL, wait=8):
    """Mở Firefox bằng Selenium (dùng profile đã đăng nhập Google) và vào Gemini."""
    _ensure_selenium()
    from selenium import webdriver
    from selenium.webdriver.firefox.options import Options as FirefoxOptions
    from selenium.webdriver.firefox.service import Service as FirefoxService

    profile = profile or FIREFOX_PROFILE_PATH
    options = FirefoxOptions()
    if FIREFOX_BINARY and os.path.exists(FIREFOX_BINARY):
        options.binary_location = FIREFOX_BINARY
    if profile and os.path.isdir(profile):
        options.add_argument("-profile")
        options.add_argument(profile)

    # Có geckodriver sẵn thì dùng; không thì để Selenium Manager tự tải.
    if GECKODRIVER_PATH and os.path.exists(GECKODRIVER_PATH):
        service = FirefoxService(executable_path=GECKODRIVER_PATH)
    else:
        service = FirefoxService()

    driver = webdriver.Firefox(service=service, options=options)
    driver.get(url)
    time.sleep(wait)
    return driver


def is_driver_alive(driver):
    try:
        if driver is None:
            return False
        _ = driver.current_url
        return True
    except Exception:
        return False


# ── Helper thao tác DOM ──────────────────────────────────────────────────────
def _find_editor(driver):
    from selenium.webdriver.common.by import By
    for sel in EDITOR_SELECTORS:
        for e in driver.find_elements(By.CSS_SELECTOR, sel):
            try:
                if e.is_displayed():
                    return e
            except Exception:
                continue
    return None


def _get_responses(driver):
    """Danh sách phần tử chứa câu trả lời của model (theo selector khớp đầu tiên)."""
    from selenium.webdriver.common.by import By
    for sel in RESPONSE_SELECTORS:
        els = driver.find_elements(By.CSS_SELECTOR, sel)
        if els:
            return els
    return []


def _click_send(driver):
    from selenium.webdriver.common.by import By
    for sel in SEND_SELECTORS:
        for b in driver.find_elements(By.CSS_SELECTOR, sel):
            try:
                if b.is_displayed() and b.is_enabled():
                    b.click()
                    return True
            except Exception:
                continue
    return False


def _set_clipboard(text):
    """Đưa text lên clipboard (Unicode chuẩn). True nếu thành công."""
    try:
        import pyperclip
        pyperclip.copy(text)
        return True
    except Exception:
        # Fallback: dùng PowerShell Set-Clipboard nếu không có pyperclip
        try:
            import subprocess
            subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "$t=[Console]::In.ReadToEnd(); Set-Clipboard -Value $t"],
                input=text, text=True, encoding="utf-8", timeout=10,
            )
            return True
        except Exception:
            return False


def _type_and_submit(driver, editor, text):
    """DÁN (paste) text vào ô nhập rồi gửi — không gõ giả lập từng chữ.

    Đưa text lên clipboard rồi Ctrl+V (nhanh + giữ đúng nội dung). Nếu không dán
    được thì mới fallback sang gõ send_keys.
    """
    from selenium.webdriver.common.keys import Keys

    editor.click()
    # Xoá nội dung cũ còn sót trong ô nhập
    editor.send_keys(Keys.CONTROL, "a")
    editor.send_keys(Keys.DELETE)

    pasted = False
    if _set_clipboard(text):
        editor.send_keys(Keys.CONTROL, "v")   # dán từ clipboard
        time.sleep(0.5)
        # Kiểm tra đã dán được chữ vào ô chưa (Quill cập nhật .text)
        try:
            pasted = bool((editor.text or "").strip())
        except Exception:
            pasted = True

    if not pasted:
        # Fallback: gõ từng dòng (Shift+Enter cho xuống dòng để không submit sớm)
        from selenium.webdriver.common.action_chains import ActionChains
        editor.send_keys(Keys.CONTROL, "a")
        editor.send_keys(Keys.DELETE)
        lines = text.replace("\r\n", "\n").split("\n")
        actions = ActionChains(driver)
        for i, line in enumerate(lines):
            if i:
                actions.key_down(Keys.SHIFT).send_keys(Keys.ENTER).key_up(Keys.SHIFT)
            if line:
                actions.send_keys(line)
        actions.perform()
        time.sleep(0.4)

    # Ưu tiên bấm nút Send; không thấy thì nhấn Enter.
    if not _click_send(driver):
        editor.send_keys(Keys.ENTER)


# ── Gửi 1 đoạn ───────────────────────────────────────────────────────────────
def send_to_gemini(driver, text, prefix="", timeout=RESPONSE_TIMEOUT,
                   settle=RESPONSE_SETTLE, on_log=print):
    """Gửi 1 đoạn tới Gemini, chờ tới khi câu trả lời ổn định rồi trả về văn bản.

    prefix: câu hướng dẫn chèn lên đầu (thường chỉ dùng cho đoạn đầu tiên).
    """
    from selenium.webdriver.support.ui import WebDriverWait

    if driver is None or not is_driver_alive(driver):
        on_log("❌ Firefox/driver không sẵn sàng.")
        return None

    prompt = (prefix.strip() + "\n\n" + text) if prefix and prefix.strip() else text

    try:
        editor = WebDriverWait(driver, 30).until(lambda d: _find_editor(d))
    except Exception:
        on_log("❌ Không tìm thấy ô nhập của Gemini. Kiểm tra đã vào gemini.google.com chưa.")
        return None

    def _norm(s):
        return " ".join((s or "").split())

    # Ghi nhớ các câu trả lời ĐÃ CÓ trước khi gửi, và nội dung mình sắp gửi, để
    # tuyệt đối không bắt nhầm câu cũ hoặc chính tin nhắn mình vừa gửi (echo).
    before_texts = {_norm(e.text) for e in _get_responses(driver)}
    sent_norm = _norm(prompt)
    sent_head = sent_norm[:60]   # phòng khi Gemini hiển thị tin người dùng hơi khác

    _type_and_submit(driver, editor, prompt)
    on_log("⌛ Đang chờ Gemini trả lời...")

    deadline = time.time() + timeout

    def _candidate():
        """Câu trả lời MỚI của Gemini: khác tin mình gửi, khác câu cũ, không rỗng."""
        for e in reversed(_get_responses(driver)):
            t = (e.text or "").strip()
            if not t:
                continue
            nt = _norm(t)
            if nt == sent_norm or nt.startswith(sent_head):
                continue   # đây là tin nhắn của chính mình (echo)
            if nt in before_texts:
                continue   # câu trả lời cũ từ lượt trước
            return t
        return None

    # Chờ câu trả lời mới xuất hiện rồi ổn định (ngừng gõ) trong `settle` giây.
    last_text, stable_at, seen = "", None, False
    while time.time() < deadline:
        cur = _candidate()
        if cur:
            seen = True
            if cur == last_text:
                if stable_at is None:
                    stable_at = time.time()
                elif time.time() - stable_at >= settle:
                    return cur
            else:
                last_text, stable_at = cur, None
        time.sleep(1.5)

    if not seen:
        on_log("❌ Gemini không phản hồi (hết thời gian chờ).")
    return last_text or None


# ── Gửi nhiều đoạn ───────────────────────────────────────────────────────────
def send_chunks_to_gemini(chunks, prefix="", on_log=print, on_result=None,
                          driver=None, profile=None, keep_open=True, out_path=None):
    """Gửi lần lượt các đoạn tới Gemini, trả về list kết quả (cùng thứ tự).

    - prefix chỉ chèn vào ĐOẠN ĐẦU (Gemini nhớ ngữ cảnh các đoạn sau) — đúng như
      cách GUI nhận diện chèn "Câu mở đầu" cho đoạn 1 khi sao chép.
    - on_result(i, total, answer): callback sau mỗi đoạn (để cập nhật GUI).
    - driver: truyền driver có sẵn để tái dùng; None thì tự mở Firefox.
    - keep_open: True thì để Firefox mở sau khi xong (tiện xem/đối chiếu).
    - out_path: nếu có, LƯU NGAY ra .docx sau MỖI đoạn nhận được kết quả. Nhờ vậy
      nếu lỗi giữa chừng (timeout, mất mạng, Firefox đóng...) thì các đoạn đã xong
      vẫn được giữ lại — chạy lại để dịch tiếp phần còn thiếu.
    """
    own_driver = driver is None
    results = []
    total = len(chunks)

    def _save_progress():
        """Ghi tiến độ hiện tại ra out_path; đệm '(chưa dịch)' cho đoạn còn lại."""
        if out_path is None:
            return
        try:
            padded = results + ["(chưa dịch)"] * (total - len(results))
            save_results_docx(chunks, padded, out_path)
        except Exception as e:
            on_log(f"⚠️ Không lưu được tiến độ: {e}")

    try:
        if driver is None:
            on_log("🌐 Đang mở Firefox + Gemini...")
            driver = init_firefox(profile=profile)
            on_log("✅ Đã mở Gemini. Bắt đầu gửi từng đoạn...")

        for i, chunk in enumerate(chunks):
            p = prefix if i == 0 else ""
            on_log(f"📤 Gửi đoạn {i + 1}/{total} ({len(chunk)} ký tự)...")
            try:
                ans = send_to_gemini(driver, chunk, prefix=p, on_log=on_log)
            except Exception as e:
                # ── LỖI GIỮA CHỪNG ──────────────────────────────────────────
                # Lưu lại những đoạn ĐÃ XONG rồi báo lỗi để dừng sạch; phần đã
                # dịch không bị mất. Chạy lại sẽ dịch tiếp từ đoạn bị lỗi.
                on_log(f"❌ Lỗi khi gửi đoạn {i + 1}/{total}: {e}")
                _save_progress()
                if out_path is not None:
                    on_log(f"💾 Đã lưu {len(results)}/{total} đoạn xong → {out_path}. "
                           "Chạy lại để dịch tiếp phần còn thiếu.")
                raise
            if ans:
                on_log(f"✅ Đã nhận kết quả đoạn {i + 1}/{total}.")
            else:
                on_log(f"⚠️ Đoạn {i + 1}/{total} không có kết quả.")
                ans = ""
            results.append(ans)
            _save_progress()          # ← LƯU NGAY sau mỗi đoạn nhận được kết quả
            if on_result:
                on_result(i, total, ans)
        on_log("🎉 Đã gửi xong tất cả các đoạn cho Gemini.")
        return results
    finally:
        if own_driver and not keep_open and driver is not None:
            try:
                driver.quit()
            except Exception:
                pass


# ── Lưu kết quả ──────────────────────────────────────────────────────────────
def save_results_docx(chunks, results, out_path):
    """Lưu kết quả Gemini ra file Word: mỗi đoạn 1 mục."""
    from docx import Document
    doc = Document()
    doc.add_heading("Kết quả dịch từ Gemini", level=1)
    for i, ans in enumerate(results):
        doc.add_heading(f"Đoạn {i + 1}", level=2)
        doc.add_paragraph(ans or "(trống)")
    doc.save(str(out_path))
    return out_path


# ── Chạy thẳng từ terminal ───────────────────────────────────────────────────
def _read_source_text(path):
    p = Path(path)
    if p.suffix.lower() == ".docx":
        from docx import Document
        d = Document(str(p))
        return "\n".join(par.text for par in d.paragraphs)
    return p.read_text(encoding="utf-8")


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(
        description="Gửi văn bản (đã tách đoạn) tới Gemini và lưu kết quả."
    )
    parser.add_argument("source", help="File .txt hoặc .docx chứa nội dung cần gửi.")
    parser.add_argument("--prefix-file", help="File chứa câu hướng dẫn chèn lên đầu đoạn 1.")
    parser.add_argument("--profile", help="Đường dẫn profile Firefox đã đăng nhập Google.")
    args = parser.parse_args(argv)

    text = _read_source_text(args.source)
    prefix = ""
    if args.prefix_file and os.path.exists(args.prefix_file):
        prefix = Path(args.prefix_file).read_text(encoding="utf-8").strip()

    # Tái dùng bộ tách đoạn của pipeline nhận diện nếu có.
    try:
        import nhandien_giongnoi as recog
        chunks = recog.split_into_chunks(text)
    except Exception:
        chunks = [text]

    print(f"📚 Đã tách {len(chunks)} đoạn. Bắt đầu gửi Gemini...")
    results = send_chunks_to_gemini(chunks, prefix=prefix, profile=args.profile, keep_open=True)

    out = Path(args.source).with_name(Path(args.source).stem + "_gemini.docx")
    save_results_docx(chunks, results, out)
    print(f"💾 Đã lưu kết quả: {out}")


if __name__ == "__main__":
    main()
