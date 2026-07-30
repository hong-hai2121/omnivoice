# -*- coding: utf-8 -*-
"""
xoa_antoan.py — Xoá file/thư mục AN TOÀN: đưa vào THÙNG RÁC Windows thay vì xoá hẳn.

Lý do tồn tại: mọi thao tác xoá trong dự án phải KHÔI PHỤC ĐƯỢC. Trước đây
`_clear_output` xoá thẳng và đã làm mất dữ liệu; `doiten_video.py` cũng từng
`os.remove()` video GỐC sau khi chuẩn hoá (kho clip trong myvoice/videongang,
myvoice/videodoc không nằm trong git → mất là mất luôn).

Dùng SHFileOperationW của shell32 với cờ FOF_ALLOWUNDO — không cần thư viện ngoài
(send2trash/winshell). Trên nền tảng KHÔNG phải Windows thì trả về lỗi cho mọi
đường dẫn thay vì xoá hẳn (thà không xoá còn hơn xoá mất).

Dùng:
    import xoa_antoan
    ok, fail = xoa_antoan.send_to_recycle_bin([p1, p2, ...])
    xoa_antoan.recycle_one(path)     # True nếu đã vào Thùng rác
"""

import os
import sys
import logging

# FO_DELETE + cờ: ALLOWUNDO (vào Thùng rác) | NOCONFIRMATION | SILENT | NOERRORUI
_FO_DELETE = 0x0003
_FLAGS = 0x0040 | 0x0010 | 0x0004 | 0x0400


def _recycle_windows(path) -> bool:
    """Đưa MỘT đường dẫn vào Thùng rác Windows. True nếu thành công."""
    import ctypes
    from ctypes import wintypes

    class _SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", wintypes.LPCWSTR),
            ("pTo", wintypes.LPCWSTR),
            ("fFlags", ctypes.c_ushort),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", wintypes.LPCWSTR),
        ]

    # pFrom phải kết thúc bằng NULL kép -> thêm "\x00" (buffer tự thêm 1 NULL nữa).
    buf = ctypes.create_unicode_buffer(os.path.abspath(str(path)) + "\x00")
    op = _SHFILEOPSTRUCTW()
    op.wFunc = _FO_DELETE
    op.pFrom = ctypes.cast(buf, wintypes.LPCWSTR)
    op.fFlags = _FLAGS
    rc = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    return rc == 0 and not op.fAnyOperationsAborted


def recycle_one(path, on_log=None) -> bool:
    """Đưa 1 file/thư mục vào Thùng rác. True nếu xong, False nếu KHÔNG xoá được.

    KHÔNG bao giờ tự chuyển sang xoá hẳn khi thất bại — bên gọi tự quyết định.
    """
    log = on_log or logging.warning
    if not os.path.exists(path):
        return True                      # không có gì để xoá → coi như xong
    if sys.platform != "win32":
        log(f"⚠️ Không phải Windows — KHÔNG xoá {path} (tránh xoá vĩnh viễn).")
        return False
    try:
        if _recycle_windows(path):
            return True
        log(f"⚠️ Không đưa vào Thùng rác được (giữ nguyên file): {path}")
        return False
    except Exception as e:
        log(f"⚠️ Không đưa vào Thùng rác được {path}: {e}")
        return False


def send_to_recycle_bin(paths, on_log=None):
    """Đưa danh sách file/thư mục vào Thùng rác. Trả về (số thành công, số lỗi)."""
    ok = fail = 0
    for p in paths:
        if recycle_one(p, on_log=on_log):
            ok += 1
        else:
            fail += 1
    return ok, fail
