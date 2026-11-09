# -*- coding: utf-8 -*-
"""Tắt app = trả VRAM (user chốt 09/11/2026). Hai lớp chốt, lớp nào cũng phải đứng riêng được:
  1. chay.py (myvoice + myvideo) đóng cửa sổ → _tat_cay: taskkill /T cả cây server → runner →
     script bước, không chỉ terminate() mỗi server.
  2. Hai server FastAPI có hook shutdown gọi stop_all() mọi hàng đợi (Ctrl+C chế độ console).
Tiến trình thật chỉ là `python -c sleep` nhỏ; không nạp model, không mở Tk."""
import asyncio
import os
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import psutil

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "myvoice" / "voice"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
import gc  # noqa: E402
gc.collect()
with patch.object(threading.Thread, "start", lambda self: None):
    from myvideo.web import server as sv_video  # noqa: E402
from myvoice.web import server as sv_voice  # noqa: E402
import importlib  # noqa: E402
chay_voice = importlib.import_module("myvoice.chay")
chay_video = importlib.import_module("myvideo.chay")

PY = sys.executable
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _ngu(giay=60) -> subprocess.Popen:
    """Tiến trình 'cha' giả: ngủ `giay` giây."""
    return subprocess.Popen([PY, "-c", f"import time; time.sleep({giay})"],
                            creationflags=CREATE_NO_WINDOW)


def _doi_chet(pid: int, cho: float = 8.0) -> bool:
    han = time.monotonic() + cho
    while time.monotonic() < han:
        if not psutil.pid_exists(pid):
            return True
        try:
            if psutil.Process(pid).status() == psutil.STATUS_ZOMBIE:
                return True
        except psutil.Error:
            return True
        time.sleep(0.1)
    return not psutil.pid_exists(pid)


# ── 1. launcher tắt cả cây ───────────────────────────────────────────────────────
class TestTatCay(unittest.TestCase):
    def _cay(self) -> tuple[subprocess.Popen, int]:
        """Cha python sinh con python ngủ 60 s, in PID con rồi tự ngủ — y cấu trúc
        server → runner/worker. Trả (cha, pid con)."""
        ma = ("import subprocess, sys, time\n"
              "c = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
              "print(c.pid, flush=True)\n"
              "time.sleep(60)\n")
        cha = subprocess.Popen([PY, "-c", ma], stdout=subprocess.PIPE, text=True,
                               creationflags=CREATE_NO_WINDOW)
        con = int(cha.stdout.readline().strip())
        return cha, con

    def _kiem(self, tat_cay):
        cha, con = self._cay()
        try:
            self.assertTrue(psutil.pid_exists(con))
            tat_cay(cha)
            self.assertIsNotNone(cha.poll(), "server giả còn sống")
            self.assertTrue(_doi_chet(con), "tiến trình con (worker giả) còn sống sau khi tắt app")
        finally:
            for p in (con, cha.pid):
                try:
                    psutil.Process(p).kill()
                except psutil.Error:
                    pass
            if cha.stdout:
                cha.stdout.close()

    def test_myvideo(self):
        self._kiem(chay_video._tat_cay)

    def test_myvoice(self):
        self._kiem(chay_voice._tat_cay)

    def test_khong_co_gi_thi_thoi(self):
        chay_video._tat_cay(None)
        p = subprocess.Popen([PY, "-c", "pass"], creationflags=CREATE_NO_WINDOW)
        p.wait(10)
        chay_video._tat_cay(p)          # đã chết sẵn → không ném


# ── 2. hook shutdown của hai server ──────────────────────────────────────────────
class TestHookServer(unittest.TestCase):
    def test_myvideo_dung_ca_ba_hang_doi(self):
        with patch.object(sv_video.q, "stop_all") as a, patch.object(sv_video.q_dang, "stop_all") as b, \
                patch.object(sv_video.q_fb, "stop_all") as c:
            asyncio.run(sv_video._tat_viec_khi_server_tat())
        for m in (a, b, c):
            m.assert_called_once_with()
        self.assertIn(sv_video._tat_viec_khi_server_tat, sv_video.app.router.on_shutdown)

    def test_myvoice_dung_ca_ba_hang_doi(self):
        with patch.object(sv_voice.runner, "stop_all") as a, \
                patch.object(sv_voice.upload_runner, "stop_all") as b, \
                patch.object(sv_voice.fb_runner, "stop_all") as c:
            asyncio.run(sv_voice._tat_viec_khi_server_tat())
        for m in (a, b, c):
            m.assert_called_once_with()
        self.assertIn(sv_voice._tat_viec_khi_server_tat, sv_voice.app.router.on_shutdown)

    def test_mot_hang_loi_khong_chan_hang_khac(self):
        with patch.object(sv_video.q, "stop_all", side_effect=RuntimeError("x")), \
                patch.object(sv_video.q_dang, "stop_all") as b, patch.object(sv_video.q_fb, "stop_all") as c:
            asyncio.run(sv_video._tat_viec_khi_server_tat())
        b.assert_called_once_with()
        c.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
