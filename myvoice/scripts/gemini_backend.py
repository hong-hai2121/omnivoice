"""Shared browser preference; no Selenium or GUI imports here.

Cách dịch qua Gemini (01/10/2026):
  • "extension" (MẶC ĐỊNH) — Chrome Extension OmniVoice Gemini: dùng ngay hồ sơ
    Chrome nào đã cài extension và đăng nhập Gemini, không cần Selenium/geckodriver.
  • "firefox" — cách cũ: Selenium điều khiển Firefox với profile đã đăng nhập.
    Giữ lại làm DỰ PHÒNG: khi chọn extension mà extension không kết nối được
    (Chrome đóng, chưa bấm Kết nối, chưa đăng nhập Gemini, cổng bận...), dich_gemini
    tự mở Firefox để việc đang chạy không đứng — tắt bằng
    OMNI_GEMINI_EXTENSION_FALLBACK=0.
"""
import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PIPE_FILE = BASE_DIR / "taogiong_pipeline.json"
TOKEN_FILE = BASE_DIR / ".gemini_extension_token"
EXTENSION_DIR = BASE_DIR.parent / "chrome_gemini_extension"
BRIDGE_PORT = 17863
# Mã kết nối MẶC ĐỊNH (01/10/2026, theo yêu cầu): máy chỉ chạy nội bộ, bridge chỉ nghe
# 127.0.0.1, nên dùng một mã cố định — extension điền sẵn và tự bật khi cài, người dùng
# không phải dán gì. Muốn mã riêng: ghi vào TOKEN_FILE hoặc đặt OMNI_GEMINI_EXTENSION_TOKEN
# rồi dán cùng mã vào popup extension.
DEFAULT_TOKEN = "omnivoice-gemini-local"
BACKENDS = ("extension", "firefox")
DEFAULT_BACKEND = "extension"
# Số giây chờ Chrome (extension) hỏi lệnh lần đầu trước khi coi là chưa kết nối.
# Service worker ngủ thì alarm 30 s đánh thức, nên phải hơn 30 s một chút.
EXTENSION_CONNECT_TIMEOUT = 40


def get_backend():
    value = os.environ.get("OMNI_GEMINI_BACKEND")
    if value is None:
        try:
            value = json.loads(PIPE_FILE.read_text(encoding="utf-8")).get("gemini_backend")
        except (OSError, ValueError, AttributeError):
            value = None
    return "firefox" if value == "firefox" else DEFAULT_BACKEND


def fallback_enabled():
    """Extension không kết nối được → có tự mở Firefox (Selenium) thay không."""
    return os.environ.get("OMNI_GEMINI_EXTENSION_FALLBACK", "1").strip().lower() not in (
        "0", "false", "no", "off", "")


def browser_label():
    return "Chrome Extension" if get_backend() == "extension" else "Firefox"


def browser_hint():
    if get_backend() == "extension":
        hint = "Mở Chrome, đăng nhập Gemini và bật kết nối trong extension OmniVoice Gemini."
        if fallback_enabled():
            hint += "\nExtension không kết nối được thì tự mở Firefox (dự phòng)."
        return hint
    return "Đóng Firefox đang mở và đảm bảo profile đã đăng nhập Google/Gemini."


def backend_picker(parent, variable, on_change):
    """Two mutually exclusive checkboxes, shared by desktop GUI panels."""
    from tkinter import ttk
    frame = ttk.Frame(parent)
    buttons = []
    for value, title in (("extension", "Dịch bằng Chrome Extension (mặc định)"),
                         ("firefox", "Dịch bằng Firefox / Selenium (dự phòng)")):
        button = ttk.Checkbutton(frame, text=title, variable=variable,
                                 onvalue=value, offvalue=value, command=on_change)
        button.pack(anchor="w")
        buttons.append(button)
    ttk.Button(frame, text="Hướng dẫn cài extension", command=lambda: show_setup(parent)).pack(anchor="w", pady=(4, 0))
    return frame, buttons


def show_setup(parent):
    import tkinter as tk
    from tkinter import ttk
    window = tk.Toplevel(parent)
    window.title("Cài Chrome Extension — OmniVoice Gemini")
    window.geometry("660x420")
    text = ("1. Mở chrome://extensions → bật Developer mode → Load unpacked.\n"
            "2. Chọn thư mục sau:\n" + str(EXTENSION_DIR) + "\n\n"
            "3. Mở biểu tượng OmniVoice Gemini, dán mã bên dưới → Lưu và kết nối.\n"
            "4. Đăng nhập Gemini trên hồ sơ Chrome đó. Chọn Chrome Extension trong GUI,\n"
            "   rồi bấm Dịch như trước. Giữ Chrome mở trong khi chạy.\n"
            "   Extension không kết nối được thì ứng dụng tự mở Firefox (dự phòng).")
    ttk.Label(window, text=text, wraplength=620).pack(padx=18, pady=18, anchor="w")
    token = connection_token()
    value = tk.StringVar(value=token)
    ttk.Entry(window, textvariable=value, state="readonly", width=65).pack(padx=18, fill="x")

    def copy():
        window.clipboard_clear()
        window.clipboard_append(token)
        copied.set("Đã sao chép mã kết nối")

    copied = tk.StringVar(value="Sao chép mã kết nối")
    ttk.Button(window, textvariable=copied, command=copy).pack(pady=12)
    ttk.Button(window, text="Mở thư mục extension", command=lambda: os.startfile(EXTENSION_DIR)).pack()


def connection_token():
    """Mã mà extension phải gửi kèm (Bearer) để bridge nhận lệnh. Thứ tự ưu tiên:
    biến OMNI_GEMINI_EXTENSION_TOKEN → file .gemini_extension_token (nếu có, không tự
    sinh) → DEFAULT_TOKEN cố định."""
    token = os.environ.get("OMNI_GEMINI_EXTENSION_TOKEN", "").strip()
    if token:
        return token
    try:
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        token = ""
    return token or DEFAULT_TOKEN
