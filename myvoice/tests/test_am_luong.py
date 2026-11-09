# -*- coding: utf-8 -*-
"""🔊 Âm lượng cơ bản (06/11/2026): ô dB mục "Cài đặt tạo giọng" — đọc/kẹp số, chuỗi filter,
cộng dB thật bằng ffmpeg (gain thuần khi còn dư đỉnh, bộ chặn ghìm khi vượt trần), mốc
_amluong.txt cho luồng ♻, gói cài đặt web và lưu form. Không mở Tk, không nạp model."""
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile as sf
from starlette.datastructures import FormData

from myvoice.web import core, server   # vá sys.path (scripts/) + import amain_taogiong_gui

gui = core.gui
hu = gui.hu
SR = 24_000


def _tone(rms_db, giay=1.0):
    a = 10 ** (rms_db / 20) * np.sqrt(2) * np.sin(2 * np.pi * 220 * np.arange(int(SR * giay)) / SR)
    return a.astype(np.float32)


def _rms_db(a):
    return 20 * np.log10(np.sqrt(np.mean(a.astype("float64") ** 2)))


class DocSoTests(unittest.TestCase):
    def test_kep_va_lam_tron(self):
        self.assertEqual(hu.parse_amluong("+3"), 3.0)
        self.assertEqual(hu.parse_amluong("2,5"), 2.5)
        self.assertEqual(hu.parse_amluong(4.26), 4.5)          # bước 0,5
        self.assertEqual(hu.parse_amluong(99), hu.AMLUONG_MAX)
        self.assertEqual(hu.parse_amluong(-99), hu.AMLUONG_MIN)

    def test_so_hong_ve_mac_dinh(self):
        for v in (None, "", "abc", float("nan")):
            self.assertEqual(hu.parse_amluong(v), 0.0, repr(v))
        self.assertEqual(hu.parse_amluong("abc", 3.0), 3.0)

    def test_chuoi_filter(self):
        self.assertEqual(hu.amluong_chain(0), [])
        self.assertEqual(hu.amluong_chain(-4), ["volume=-4.0dB"])        # giảm: không cần chặn đỉnh
        tang = hu.amluong_chain(6)
        self.assertEqual(tang[0], "volume=6.0dB")
        self.assertTrue(tang[1].startswith(f"alimiter=limit={hu.AMLUONG_LIMIT}"))
        self.assertIn("level=false", tang[1])                           # không tự kéo to thêm


@unittest.skipUnless(shutil.which("ffmpeg"), "cần ffmpeg")
class CongDbTests(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp(prefix="amluong_"))
        self.addCleanup(shutil.rmtree, self.td, True)

    def _wav(self, rms_db, ten="a.wav"):
        f = self.td / ten
        sf.write(str(f), _tone(rms_db), SR, subtype="PCM_16")
        return f

    def test_con_du_dinh_la_gain_thuan(self):
        f = self._wav(-20.0)                      # đỉnh ≈ −17 dBFS, +6 dB vẫn dưới trần
        truoc, _ = sf.read(str(f), dtype="float32")
        hu.apply_amluong_file(f, 6.0)
        sau, sr = sf.read(str(f), dtype="float32")
        self.assertEqual(sr, SR)
        self.assertEqual(len(sau), len(truoc))    # không lệch thời lượng (phụ đề bám theo audio)
        self.assertAlmostEqual(_rms_db(sau) - _rms_db(truoc), 6.0, delta=0.1)

    def test_giam(self):
        f = self._wav(-20.0)
        hu.apply_amluong_file(f, -6.0)
        self.assertAlmostEqual(_rms_db(sf.read(str(f), dtype="float32")[0]), -26.0, delta=0.1)

    def test_vuot_tran_thi_bo_chan_ghim_khong_vo_tieng(self):
        f = self._wav(-6.0)                       # đỉnh ≈ −3 dBFS, +10 dB lẽ ra vượt 0 dBFS 7 dB
        hu.apply_amluong_file(f, 10.0)
        sau, _ = sf.read(str(f), dtype="float32")
        self.assertLessEqual(float(np.max(np.abs(sau))), hu.AMLUONG_LIMIT + 0.01)
        self.assertGreater(_rms_db(sau), -6.0)    # vẫn to hơn bản gốc

    def test_muc_0_khong_dung_file(self):
        f = self._wav(-20.0)
        goc = f.read_bytes()
        hu.apply_amluong_file(f, 0)
        self.assertEqual(f.read_bytes(), goc)
        out = hu.apply_amluong_file(f, 0, self.td / "b.wav")
        self.assertEqual(out.read_bytes(), goc)   # out khác src → chép nguyên

    def test_nhat_ky_noi_ro_bo_chan(self):
        mo_ta = gui._tang_am_luong_file(self._wav(-20.0), 6.0)
        self.assertIn("chưa chạm trần", mo_ta)
        self.assertIn("LUFS", mo_ta)              # báo độ to trước → sau
        self.assertNotIn("nên hạ mức", mo_ta)
        mo_ta = gui._tang_am_luong_file(self._wav(-6.0, "to.wav"), 10.0)
        self.assertIn("bộ chặn", mo_ta)
        self.assertIn("nên hạ mức", mo_ta)        # bộ chặn đè cả tín hiệu → độ to lên hụt → khuyên hạ
        self.assertNotIn("nên hạ mức", gui._tang_am_luong_file(self._wav(-20.0, "giam.wav"), -6.0))


class MocTests(unittest.TestCase):
    def test_ghi_doc_moc(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(gui._doc_amluong_da_ap(td), 0.0)      # tập cũ chưa có file
            gui._ghi_amluong_da_ap(td, 4.5)
            self.assertEqual(gui._doc_amluong_da_ap(td), 4.5)
            gui._ghi_amluong_da_ap(td, 0.0)                        # tạo lại ở mức 0 → mốc về 0
            self.assertEqual(gui._doc_amluong_da_ap(td), 0.0)


class CaiDatTests(unittest.TestCase):
    def _ts(self, **opts):
        with patch.object(core, "load_options", lambda: dict(gui.OPTS_DEFAULTS, **opts)), \
                patch.object(core, "load_web_settings", lambda: dict(core.WEB_DEFAULTS)):
            ts, loi = core.tts_settings()
        self.assertEqual(loi, "")
        return ts

    def test_mac_dinh_0(self):
        self.assertEqual(gui.OPTS_DEFAULTS["am_luong_db"], 0.0)
        self.assertEqual(self._ts()["am_luong"], 0.0)
        self.assertIn("am_luong", gui.run_tts.__code__.co_varnames)

    def test_goi_web_doc_va_kep(self):
        self.assertEqual(self._ts(am_luong_db="4,5")["am_luong"], 4.5)
        self.assertEqual(self._ts(am_luong_db=99)["am_luong"], hu.AMLUONG_MAX)

    def _luu(self, gia_tri, san_co=None):
        saved: dict = {}
        with patch.object(core, "load_options", return_value=dict(san_co or {"chunk": 160})), \
             patch.object(core, "save_options", side_effect=saved.update):
            server._save_opts_from_form(FormData([("am_luong_db", gia_tri)]))
        return saved

    def test_form_luu_va_kep(self):
        self.assertEqual(self._luu("+3")["am_luong_db"], 3.0)
        self.assertEqual(self._luu("2,5")["am_luong_db"], 2.5)
        self.assertEqual(self._luu("50")["am_luong_db"], hu.AMLUONG_MAX)   # ô hiện đúng mức sẽ áp
        # gõ chữ: giữ mức đang lưu
        self.assertEqual(self._luu("abc", {"am_luong_db": 4.0})["am_luong_db"], 4.0)

    def test_form_khong_co_o_thi_khong_dung(self):
        saved: dict = {}
        with patch.object(core, "load_options", return_value={"chunk": 160}), \
             patch.object(core, "save_options", side_effect=saved.update):
            server._save_opts_from_form(FormData([("chunk", "200")]))
        self.assertNotIn("am_luong_db", saved)

    def test_cac_form_co_o_nhap(self):
        tpl = Path(server.__file__).resolve().parent / "templates" / "_form_voice.html"
        self.assertIn('name="am_luong_db"', tpl.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
