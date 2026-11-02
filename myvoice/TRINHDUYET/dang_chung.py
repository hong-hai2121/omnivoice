# -*- coding: utf-8 -*-
"""Hàm dùng chung cho các module đăng qua trình duyệt (YouTube Studio / TikTok Studio)."""
from __future__ import annotations

import os
import re
import time

# BIỂU THỨC JS (không phải hàm) tìm input[type=file] xuyên shadow DOM — dùng được cả với
# Runtime.evaluate (CDP) lẫn page.evaluate_handle.
JS_FIND_FILE_INPUT = """(() => {
  const deep = (root, sel) => {
    const el = root.querySelector(sel); if (el) return el;
    for (const e of root.querySelectorAll('*')) {
      if (e.shadowRoot) { const r = deep(e.shadowRoot, sel); if (r) return r; }
    }
    return null;
  };
  return deep(document, 'input[type=file]');
})()"""

# Ô chọn ẢNH (thumbnail) — input[type=file] có accept chứa "image", xuyên shadow DOM.
JS_FIND_IMAGE_INPUT = """(() => {
  const all = [];
  const walk = (root) => {
    for (const e of root.querySelectorAll('input[type=file]')) all.push(e);
    for (const e of root.querySelectorAll('*')) if (e.shadowRoot) walk(e.shadowRoot);
  };
  walk(document);
  return all.find(e => /image/i.test(e.getAttribute('accept') || '')) || null;
})()"""


def set_file_via_cdp(page, file_path, log=print, find_js=JS_FIND_FILE_INPUT, ten="file"):
    """Nạp file vào input[type=file] mà KHÔNG mở hộp thoại Windows.

    Đường chính: CDP DOM.setFileInputFiles gửi ĐƯỜNG DẪN qua relay → trình duyệt tự đọc file, không
    vướng giới hạn 50 MB mà Playwright áp cho trình duyệt nối qua connect_over_cdp. Cần extension
    bật 'Cho phép truy cập URL tệp' (không thì CDP trả "Not allowed").
    Dự phòng: set_input_files của Playwright (file <= 50 MB)."""
    from trinhduyet import cdp_send
    try:
        res = cdp_send("Runtime.evaluate", {"expression": find_js, "returnByValue": False})
        obj = ((res or {}).get("result") or {}).get("objectId")
        if not obj:
            raise RuntimeError(f"không thấy ô chọn {ten} trên trang")
        cdp_send("DOM.setFileInputFiles", {"files": [os.path.abspath(file_path)], "objectId": obj})
        log(f"✓ Đã nạp {ten} qua CDP (không giới hạn dung lượng).")
        return "cdp"
    except Exception as e:
        msg = str(e)
        if "Not allowed" in msg:
            raise RuntimeError(
                "Chrome từ chối đọc file (Not allowed) — hãy bật 'Cho phép truy cập URL tệp' cho "
                "Playwright Extension trong profile này (chrome://extensions → Chi tiết).") from e
        log(f"  (CDP không được: {msg[:120]} → thử cách của Playwright, giới hạn 50 MB)")
    h = page.evaluate_handle(find_js)
    el = h.as_element()
    if el is None:
        raise RuntimeError(f"không thấy ô chọn {ten} trên trang")
    el.set_input_files(file_path, timeout=15000)
    log(f"✓ Đã nạp {ten} qua Playwright.")
    return "playwright"


def _noi_dung_o(box):
    try:
        v = box.evaluate("e => ('value' in e && typeof e.value === 'string') ? e.value : (e.innerText || e.textContent || '')")
    except Exception:
        v = box.inner_text()
    return (v or "").strip()


def clear_field(page, box, log=None, ten="ô nhập"):
    """XÓA SẠCH chữ cũ trong ô (Studio tự điền tên file). Làm tới 3 cách, mỗi cách kiểm tra ô đã
    trống thật; vẫn còn chữ thì raise để không gõ nối vào chữ cũ."""
    box.click()
    page.wait_for_timeout(150)
    cach = [("Ctrl+A + Delete", lambda: (page.keyboard.press("Control+a"), page.keyboard.press("Delete"))),
            ("Ctrl+A + Backspace", lambda: (page.keyboard.press("Control+a"), page.keyboard.press("Backspace"))),
            ("End + Backspace từng ký tự", lambda: (page.keyboard.press("Control+End"),
                                                    [page.keyboard.press("Backspace") for _ in range(len(_noi_dung_o(box)) + 5)]))]
    for ten_cach, lam in cach:
        lam()
        page.wait_for_timeout(300)
        if not _noi_dung_o(box):
            if log and ten_cach != "Ctrl+A + Delete":
                log(f"  (đã xoá sạch {ten} bằng {ten_cach})")
            return True
    raise RuntimeError(f"Không xoá sạch được {ten}, vẫn còn: {_noi_dung_o(box)[:80]!r}")


def clear_and_insert(page, box, text, log=None, ten="ô nhập"):
    clear_field(page, box, log, ten)
    if text:
        page.keyboard.insert_text(text)
    page.wait_for_timeout(300)


def norm_space(s):
    return " ".join((s or "").split())


def wait_until(fn, timeout_sec, every=2.0, desc=""):
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            r = fn()
            if r:
                return r
        except Exception:
            pass
        time.sleep(every)
    raise RuntimeError(f"Hết giờ chờ {desc or 'điều kiện'} ({timeout_sec}s).")


_HASHTAG_RE = re.compile(r"#[\wÀ-ỹ]+", re.UNICODE)


def hashtags_in_text(text, limit=None):
    """Mọi #hashtag trong `text` theo thứ tự xuất hiện, bỏ trùng (không phân biệt hoa thường).
    limit: chỉ lấy N cái đầu."""
    out, seen = [], set()
    for t in _HASHTAG_RE.findall(text or ""):
        k = t.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(t)
    return out[:limit] if limit else out
