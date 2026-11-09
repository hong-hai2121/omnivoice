# -*- coding: utf-8 -*-
"""voice/thu_giong.py dùng chung thông số giọng với bài thật (01/11/2026): tốc độ ↔
ngang_speed, tông ↔ pitch, 4 bộ lọc ↔ FX_KEYS trong taogiong_options.json. Không mở
cửa sổ Tk, không nạp model."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from myvoice.web import core   # vá sys.path (scripts/) + import amain_taogiong_gui một lần

gui = core.gui
_VOICE_DIR = Path(__file__).resolve().parents[1] / "voice"
if str(_VOICE_DIR) not in sys.path:
    sys.path.insert(0, str(_VOICE_DIR))
import thu_giong  # noqa: E402


class ParseSpeedTests(unittest.TestCase):
    def test_doc_chuoi_gui_web(self):
        self.assertEqual(thu_giong.parse_speed("1.2"), 1.2)
        self.assertEqual(thu_giong.parse_speed("1,15"), 1.15)
        self.assertEqual(thu_giong.parse_speed(1.0), 1.0)

    def test_kep_va_lam_tron_buoc(self):
        self.assertEqual(thu_giong.parse_speed("3"), thu_giong.SPEED_MAX)
        self.assertEqual(thu_giong.parse_speed("0.1"), thu_giong.SPEED_MIN)
        self.assertEqual(thu_giong.parse_speed("1.12"), 1.1)
        self.assertEqual(thu_giong.parse_speed("xx", 1.0), 1.0)
        self.assertEqual(thu_giong.parse_speed(None), 1.0)

    def test_dai_toc_do_trung_voi_gui(self):
        """GUI kẹp 0,5–2,0 (App._parse_speed) → bên này cùng dải để không bị kẹp khi đồng bộ."""
        self.assertEqual((thu_giong.SPEED_MIN, thu_giong.SPEED_MAX), (0.5, 2.0))


class BaiThatTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.opts = Path(tmp.name) / "taogiong_options.json"
        self.opts.write_text(json.dumps({
            "chunk": 160, "ngang_speed": "1.2", "pitch": 1.0,
            "vang_truong_do": 0, "vang_cuong_do": 0, "thieu_nien": 0, "sang_giong": 80,
            "ngang_source": ["nauan"], "make_video": True,
        }, ensure_ascii=False), encoding="utf-8")
        p = patch.object(gui, "OPTS_FILE", self.opts)
        p.start()
        self.addCleanup(p.stop)

    def _doc(self) -> dict:
        return json.loads(self.opts.read_text(encoding="utf-8"))

    def test_doc_dung_khoa_bai_that(self):
        bt = thu_giong.bai_that_doc()
        self.assertEqual(bt["speed"], 1.2)
        self.assertEqual(bt["pitch"], 1.0)
        self.assertEqual(bt["fx"], dict(vang_truong_do=0, vang_cuong_do=0,
                                        thieu_nien=0, sang_giong=80))
        self.assertEqual(thu_giong.default_speed(), 1.2)

    def test_luu_ghi_dung_khoa_giu_khoa_khac(self):
        thu_giong.bai_that_luu(1.05, 2.0, dict(vang_truong_do=40, vang_cuong_do=30,
                                               thieu_nien=0, sang_giong=60))
        d = self._doc()
        self.assertEqual(d["ngang_speed"], "1.05")      # chuỗi như GUI/web lưu
        self.assertEqual(d["pitch"], 2.0)
        self.assertEqual((d["vang_truong_do"], d["vang_cuong_do"], d["thieu_nien"], d["sang_giong"]),
                         (40, 30, 0, 60))
        # khoá không thuộc thông số giọng không bị đụng
        self.assertEqual(d["ngang_source"], ["nauan"])
        self.assertEqual(d["chunk"], 160)
        self.assertTrue(d["make_video"])

    def test_luu_roi_doc_lai_khop(self):
        thu_giong.bai_that_luu(1.5, -1.5, dict(sang_giong=100))
        bt = thu_giong.bai_that_doc()
        self.assertEqual((bt["speed"], bt["pitch"]), (1.5, -1.5))
        self.assertEqual(bt["fx"]["sang_giong"], 100)
        self.assertEqual(bt["fx"]["thieu_nien"], 0)

    def test_luu_kep_theo_gioi_han_gui(self):
        thu_giong.bai_that_luu(9.0, 99.0, None)
        d = self._doc()
        self.assertEqual(d["ngang_speed"], "2")
        self.assertEqual(d["pitch"], gui.PITCH_MAX)

    def test_mo_ta(self):
        s = thu_giong.mo_ta_thong_so(1.2, 1.0, dict(sang_giong=80))
        self.assertIn("1.20×", s)
        self.assertIn("+1.0", s)
        self.assertIn("sáng giọng 80", s)


if __name__ == "__main__":
    unittest.main()
