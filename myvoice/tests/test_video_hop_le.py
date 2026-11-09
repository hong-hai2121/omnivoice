# -*- coding: utf-8 -*-
"""Video cụt không được tính là "đã có" (09/11/2026): ffmpeg bị ngắt giữa chừng để lại mp4
không có moov → ffprobe đọc không ra → video_hop_le False → ⏩ dựng lại thay vì đem đăng.
Dựng một mp4 thật bằng ffmpeg (nhiễu 2 s), cắt cụt 60 % làm file hỏng. Không nạp model."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from myvoice.web import core   # vá sys.path (scripts/)

import video_khung as vk  # noqa: E402

FFMPEG = shutil.which("ffmpeg")


def _mp4_that(path: Path) -> None:
    """mp4 nhiễu 640×360, 2 s — đủ lớn (> VIDEO_MIN_BYTES) vì nhiễu nén rất kém."""
    subprocess.run([FFMPEG, "-y", "-v", "error", "-f", "lavfi",
                    "-i", "nullsrc=s=640x360:r=25,geq=random(1)*255:128:128", "-t", "2",
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18", "-pix_fmt", "yuv420p",
                    str(path)], check=True, timeout=120)


@unittest.skipUnless(FFMPEG, "cần ffmpeg/ffprobe")
class VideoHopLeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.td = tempfile.mkdtemp()
        cls.tot = Path(cls.td) / "YOUTUBE.mp4"
        _mp4_that(cls.tot)
        cls.cut = Path(cls.td) / "cut.mp4"
        raw = cls.tot.read_bytes()
        cls.cut.write_bytes(raw[: int(len(raw) * 0.6)])      # mất đuôi (moov) → ffprobe đọc không ra
        cls.rong = Path(cls.td) / "rong.mp4"
        cls.rong.touch()
        cls.nho = Path(cls.td) / "nho.mp4"
        cls.nho.write_bytes(b"\0" * 1000)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.td, ignore_errors=True)

    def test_file_tot_hop_le(self):
        self.assertGreater(self.tot.stat().st_size, vk.VIDEO_MIN_BYTES)
        self.assertTrue(vk.video_hop_le(self.tot))
        self.assertTrue(core.video_hop_le(self.tot))

    def test_file_cut_rong_nho_khong_hop_le(self):
        self.assertFalse(vk.video_hop_le(self.cut))
        self.assertFalse(vk.video_hop_le(self.rong))
        self.assertFalse(vk.video_hop_le(self.nho))
        self.assertFalse(vk.video_hop_le(Path(self.td) / "khong_co.mp4"))
        self.assertFalse(core.video_hop_le(self.cut))

    def test_folder_steps_khong_tinh_video_cut(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d)
            shutil.copy(self.cut, f / "YOUTUBE.mp4")
            shutil.copy(self.cut, f / "facebook.mp4")
            shutil.copy(self.cut, f / "tiktok.mp4")
            shutil.copy(self.cut, f / "short.mp4")
            st = core.folder_steps(f, "126")
            self.assertFalse(st["video_ngang"])
            self.assertFalse(st["video_doc"])
            self.assertFalse(st["video_tiktok"])
            self.assertFalse(st["video_short"])
            self.assertIn("tts", core.missing_steps(
                {**st, "recognize": True, "translate": True, "input": True, "seo": True,
                 "thumbnail": True, "audio": True},
                "full", options=dict(make_video=True, make_video_doc=True, make_tiktok=True,
                                     make_short=True)))
            for ten in ("YOUTUBE.mp4", "facebook.mp4", "tiktok.mp4", "short.mp4"):
                shutil.copy(self.tot, f / ten)
            st = core.folder_steps(f, "126")
            self.assertTrue(st["video_ngang"] and st["video_doc"]
                            and st["video_tiktok"] and st["video_short"])

    def test_xoa_video_cut_chi_xoa_file_hong(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d)
            hong = f / "a.mp4"
            lanh = f / "b.mp4"
            shutil.copy(self.cut, hong)
            shutil.copy(self.tot, lanh)
            ghi = []
            vk.xoa_video_cut(hong, lanh, None, f / "khong_co.mp4", log=ghi.append)
            self.assertFalse(hong.exists())
            self.assertTrue(lanh.exists())
            self.assertEqual(len(ghi), 1)

    def test_build_video_khong_bo_qua_file_cut(self):
        """skip_existing chỉ ♻ bỏ qua khi file dùng được; file cụt thì đi tiếp dựng lại
        (ở đây dừng ngay sau đó vì không có audio — chỉ cần thấy KHÔNG trả về sớm)."""
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "YOUTUBE.mp4"
            shutil.copy(self.cut, out)
            ghi = []
            with self.assertRaises(Exception):
                vk.build_video(Path(d) / "khong_co.wav", log=ghi.append, skip_existing=True,
                               output=out)
            self.assertTrue(any("CỤT" in s for s in ghi), ghi)
            shutil.copy(self.tot, out)
            ghi.clear()
            self.assertEqual(vk.build_video(Path(d) / "khong_co.wav", log=ghi.append,
                                            skip_existing=True, output=out), out)
            self.assertTrue(any("♻" in s for s in ghi), ghi)


if __name__ == "__main__":
    unittest.main()
