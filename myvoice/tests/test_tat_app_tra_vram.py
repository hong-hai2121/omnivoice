# -*- coding: utf-8 -*-
"""Tắt app = trả VRAM (user chốt 09/11/2026). Ba lớp chốt, lớp nào cũng phải đứng riêng được:
  1. vieneu_worker --parent-pid: worker canh tiến trình cha, cha chết là tự thoát (canh_cha);
     vieneu_client.SdkWorker.bat luôn truyền cờ này.
  2. chay.py (myvoice + myvideo) đóng cửa sổ → _tat_cay: taskkill /T cả cây server → runner →
     script bước → worker, không chỉ terminate() mỗi server.
  3. Hai server FastAPI có hook shutdown gọi stop_all() mọi hàng đợi (Ctrl+C chế độ console).
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
import vieneu_client as vn  # noqa: E402
import vieneu_worker as vw  # noqa: E402
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


# ── 1. worker canh cha ───────────────────────────────────────────────────────────
class TestCanhCha(unittest.TestCase):
    def test_cha_chet_thi_goi(self):
        cha = _ngu()
        ev = threading.Event()
        try:
            t = vw.canh_cha(cha.pid, ev.set, moi=0.2)
            self.assertIsNotNone(t)
            self.assertFalse(ev.wait(1.0), "cha còn sống mà đã báo chết")
            cha.kill()
            cha.wait(5)
            self.assertTrue(ev.wait(5.0), "cha chết 5 s rồi mà worker chưa biết")
        finally:
            if cha.poll() is None:
                cha.kill()

    def test_cha_da_chet_truoc_khi_canh(self):
        cha = subprocess.Popen([PY, "-c", "pass"], creationflags=CREATE_NO_WINDOW)
        cha.wait(10)
        ev = threading.Event()
        vw.canh_cha(cha.pid, ev.set, moi=0.2)
        self.assertTrue(ev.wait(5.0))

    def test_pid_0_khong_canh(self):
        self.assertIsNone(vw.canh_cha(0, lambda: None))
        self.assertIsNone(vw.canh_cha(-5, lambda: None))

    def test_cha_con_song(self):
        self.assertTrue(vw.cha_con_song(os.getpid()))
        cha = subprocess.Popen([PY, "-c", "pass"], creationflags=CREATE_NO_WINDOW)
        cha.wait(10)
        self.assertFalse(vw.cha_con_song(cha.pid))
        self.assertFalse(vw.cha_con_song(0))

    def test_doi_so_co_parent_pid(self):
        a = vw.doi_so().parse_args(["--port", "8011", "--parent-pid", "123"])
        self.assertEqual((a.port, a.parent_pid), (8011, 123))
        self.assertEqual(vw.doi_so().parse_args([]).parent_pid, 0)

    def test_sdkworker_truyen_parent_pid(self):
        w = vn.SdkWorker()
        goi = {}

        def bat_gia(cmd, env, cong, on_line):
            goi["cmd"] = cmd
            w.proc = MagicMock()
            w.proc.poll.return_value = None
            w.cong = cong

        with patch.object(vn.SdkWorker, "_bat", side_effect=bat_gia, autospec=False), \
                patch.object(vn.SdkWorker, "cho_san_sang", return_value={"sr": 48000, "voices": ["A"], "backend": "gia"}), \
                patch.object(vn, "chon_cong", return_value=8099):
            w.bat(device="cuda")
        cmd = goi["cmd"]
        self.assertIn("--parent-pid", cmd)
        self.assertEqual(cmd[cmd.index("--parent-pid") + 1], str(os.getpid()))
        self.assertEqual(cmd[cmd.index("--device") + 1], "cuda")


# ── 2. launcher tắt cả cây ───────────────────────────────────────────────────────
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


# ── 3. hook shutdown của hai server ──────────────────────────────────────────────
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
