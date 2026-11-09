# -*- coding: utf-8 -*-
"""voice/thu_giong.py: thông số giọng là CỦA RIÊNG app (10/11/2026) — nhớ trong
thu_giong_settings.json, KHÔNG đọc/ghi taogiong_options.json của bài thật. Không mở
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


class ThongSoRiengTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.goc = Path(tmp.name) / "taogiong_options.json"      # bài thật — phải KHÔNG bị đụng/đọc
        self.goc.write_text(json.dumps({
            "chunk": 160, "ngang_speed": "1.2", "pitch": 1.0, "sang_giong": 80, "am_luong_db": 5.0,
        }), encoding="utf-8")
        self.rieng = Path(tmp.name) / "thu_giong_settings.json"
        for p in (patch.object(gui, "OPTS_FILE", self.goc), patch.object(thu_giong, "SETTINGS_FILE", self.rieng)):
            p.start()
            self.addCleanup(p.stop)

    def _rieng(self) -> dict:
        return json.loads(self.rieng.read_text(encoding="utf-8"))

    def test_mac_dinh_khong_lay_tu_bai_that(self):
        bt = thu_giong.thong_so_doc()
        self.assertEqual(bt, dict(speed=1.0, pitch=0.0, fx=thu_giong.hu.fx_from(None), am_luong=0.0))
        self.assertEqual(thu_giong.default_speed(), 1.0)

    def test_luu_vao_file_rieng_khong_dung_bai_that(self):
        goc_truoc = self.goc.read_text(encoding="utf-8")
        thu_giong.thong_so_luu(1.05, 2.0, dict(vang_truong_do=40, vang_cuong_do=30,
                                               thieu_nien=0, sang_giong=60), am_luong=3.0)
        d = self._rieng()
        self.assertEqual((d["speed"], d["pitch"], d["am_luong"]), (1.05, 2.0, 3.0))
        self.assertEqual(d["fx"], dict(vang_truong_do=40, vang_cuong_do=30, thieu_nien=0, sang_giong=60))
        self.assertEqual(self.goc.read_text(encoding="utf-8"), goc_truoc)   # bài thật y nguyên

    def test_luu_roi_doc_lai_khop(self):
        thu_giong.thong_so_luu(1.5, -1.5, dict(sang_giong=100))
        bt = thu_giong.thong_so_doc()
        self.assertEqual((bt["speed"], bt["pitch"]), (1.5, -1.5))
        self.assertEqual(bt["fx"]["sang_giong"], 100)
        self.assertEqual(bt["fx"]["thieu_nien"], 0)
        self.assertEqual(bt["am_luong"], 0.0)                 # không truyền → giữ (chưa có) = 0

    def test_luu_kep_theo_gioi_han(self):
        thu_giong.thong_so_luu(9.0, 99.0, None)
        d = self._rieng()
        self.assertEqual(d["speed"], thu_giong.SPEED_MAX)
        self.assertEqual(d["pitch"], gui.PITCH_MAX)

    def test_mo_ta(self):
        s = thu_giong.mo_ta_thong_so(1.2, 1.0, dict(sang_giong=80))
        self.assertIn("1.20×", s)
        self.assertIn("+1.0", s)
        self.assertIn("sáng giọng 80", s)


if __name__ == "__main__":
    unittest.main()
