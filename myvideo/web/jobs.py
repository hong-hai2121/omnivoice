# -*- coding: utf-8 -*-
"""Hàng đợi việc cho web myvideo — tái dùng nguyên JobRunner/Step/LogTail của
myvoice.web.jobs (một worker, mỗi bước một tiến trình con, dừng là taskkill cả cây).

Lưu ý: import myvoice.web.jobs sẽ tạo luôn hai hàng đợi toàn cục của bên đó
(runner/upload_runner) — hai luồng daemon ngủ chờ việc, không ai xếp việc thì
mỗi giây chỉ tỉnh dậy một lần, coi như không tốn gì. Đổi lại khỏi chép ~400
dòng logic hàng đợi đã chạy ổn định bên myvoice.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from myvoice.web.jobs import JobRunner, LogTail, Step  # noqa: E402,F401

# Nhật ký phải hiện được trên TRANG WEB: server myvideo thường chạy ẩn bằng
# pythonw (launcher chay.py) nên không có console nào để nhìn.
tail = LogTail(maxlen=300)
q = JobRunner(tail=tail)
