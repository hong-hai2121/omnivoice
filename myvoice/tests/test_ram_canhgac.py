# -*- coding: utf-8 -*-
"""Chốt canh RAM (28/10/2026, scripts/ram_canhgac.py): ffmpeg ngốn RAM quá ngưỡng thì bị
giết, video_khung.run_ffmpeg_progress thử lại 1 lần, vẫn vượt thì dung_neu_nvenc_loi ném
RamLoi (là GpuLoi → dừng cả lượt). Không chạy ffmpeg thật: "ffmpeg" là một script Python
con tự ăn RAM rồi ngủ; Popen được bọc để bỏ "-progress pipe:1 -nostats" mà run_ffmpeg_progress
chèn vào (python không hiểu các cờ đó)."""
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from myvoice.web import core   # noqa: F401  (đưa myvoice/scripts vào sys.path như test khác)

import ram_canhgac as ram               # noqa: E402
import video_khung                      # noqa: E402
from gpu_batbuoc import GpuLoi, RamLoi  # noqa: E402

# Tiến trình con: cấp phát <MB> rồi ngủ <giây> (để chốt kịp đo).
AN_RAM = "import sys,time; b=b'x'*(int(sys.argv[1])*1024*1024); time.sleep(float(sys.argv[2]))"

# "ffmpeg" giả: in dòng tiến trình, ăn RAM (lần 1, hoặc luôn luôn), rồi ghi file đầu ra.
FFMPEG_GIA = r"""
import os, sys, time
mb, marker, luon, out = int(sys.argv[1]), sys.argv[2], sys.argv[3] == "luon", sys.argv[-1]
lan_dau = not os.path.exists(marker)
open(marker, "a").close()
print("progress=continue", flush=True)
if luon or lan_dau:
    b = b"x" * (mb * 1024 * 1024)
    time.sleep(20)
with open(out, "wb") as f:
    f.write(b"ok")
print("out_time_us=1000000", flush=True)
print("progress=end", flush=True)
"""

_POPEN_THAT = subprocess.Popen


def _popen_bo_co_progress(cmd, **kw):
    cmd = [c for c in cmd if c not in ("-progress", "pipe:1", "-nostats")]
    return _POPEN_THAT(cmd, **kw)


class CanhGacTests(unittest.TestCase):
    def test_vuot_nguong_thi_giet_va_chup_bang_chung(self):
        child = subprocess.Popen([sys.executable, "-c", AN_RAM, "400", "30"])
        canh = ram.CanhGac(child.pid, nguong_gb=0.2, chu_ky=0.2).start()
        try:
            child.wait(timeout=15)          # bị giết → thoát sớm (không chờ 30 s)
        finally:
            canh.stop()
            if child.poll() is None:
                child.kill()
        self.assertTrue(canh.vuot)
        self.assertGreater(canh.dinh_gb, 0.2)
        self.assertIn("RAM trống", canh.bang_chung)
        self.assertIn("Ăn RAM nhiều nhất", canh.bang_chung)

    def test_duoi_nguong_thi_de_yen(self):
        child = subprocess.Popen([sys.executable, "-c", AN_RAM, "50", "1.5"])
        canh = ram.CanhGac(child.pid, nguong_gb=1.0, chu_ky=0.2).start()
        rc = child.wait(timeout=15)
        canh.stop()
        self.assertEqual(rc, 0)
        self.assertFalse(canh.vuot)
        self.assertGreater(canh.dinh_gb, 0.0)

    def test_bang_chung_co_du_lieu(self):
        s = ram.bang_chung(3)
        self.assertIn("RAM trống", s)
        top = ram.top_tien_trinh(3)
        self.assertLessEqual(len(top), 3)
        self.assertTrue(all(gb >= 0 for _n, _p, gb in top))


class RunFfmpegProgressTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ram_canhgac_"))
        self.script = self.tmp / "ffmpeg_gia.py"
        self.script.write_text(FFMPEG_GIA, encoding="utf-8")
        self.out = self.tmp / "ra.mp4"
        self.marker = self.tmp / "da_chay.txt"
        self.logs: list[str] = []

    def _cmd(self, luon: bool):
        return [sys.executable, str(self.script), "400", str(self.marker),
                "luon" if luon else "lan_dau", str(self.out)]

    def _chay(self, luon: bool):
        with patch.object(video_khung.subprocess, "Popen", _popen_bo_co_progress), \
             patch.object(ram, "NGUONG_GB", 0.2), patch.object(ram, "CHU_KY_S", 0.2), \
             patch.object(video_khung, "CHO_THU_LAI_S", 0.1):
            t0 = time.monotonic()
            rc, tail = video_khung.run_ffmpeg_progress(self._cmd(luon), 1.0, log=self.logs.append)
            return rc, tail, time.monotonic() - t0

    def test_lan_1_bi_giet_lan_2_xong(self):
        rc, tail, giay = self._chay(luon=False)
        self.assertEqual(rc, 0)
        self.assertTrue(self.out.exists())
        self.assertLess(giay, 15, "phải giết sớm, không chờ ffmpeg giả ngủ 20 s")
        bao = [ln for ln in self.logs if ram.TAG in ln]
        self.assertEqual(len(bao), 1)
        self.assertIn("lần 1/2", bao[0])
        self.assertTrue((self.tmp / "ffmpeg_ram_loi.txt").exists(), "phải ghi bằng chứng cạnh video")

    def test_ca_2_lan_vuot_thi_ram_loi(self):
        rc, tail, giay = self._chay(luon=True)
        self.assertNotEqual(rc, 0)
        self.assertTrue(tail.startswith(ram.TAG))
        self.assertIn("lần 2/2", tail)
        self.assertLess(giay, 30)
        with self.assertRaises(RamLoi):
            video_khung.dung_neu_nvenc_loi(rc, tail, True)
        with self.assertRaises(RamLoi):          # CPU chủ ý vẫn phải dừng khi ngốn RAM
            video_khung.dung_neu_nvenc_loi(rc, tail, False)
        self.assertTrue(issubclass(RamLoi, GpuLoi))   # để `except GpuLoi: raise` dừng cả lượt

    def test_nvenc_loi_thuong_van_la_gpu_loi(self):
        with self.assertRaises(GpuLoi) as cm:
            video_khung.dung_neu_nvenc_loi(1, "Cannot load nvEncodeAPI64.dll", True)
        self.assertNotIsInstance(cm.exception, RamLoi)
        self.assertIsNone(video_khung.dung_neu_nvenc_loi(0, "", True))


if __name__ == "__main__":
    unittest.main()
