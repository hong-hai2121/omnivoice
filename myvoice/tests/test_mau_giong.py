# -*- coding: utf-8 -*-
"""🎚 Mẫu giọng cài sẵn (02/11/2026): bảng hu.MAU_GIONG dùng chung app Thử giọng / GUI /
web — bộ số hợp lệ, "Mặc định" = tắt hết, mau_khop nhận đúng tên, web đưa mẫu vào ngữ
cảnh form và KHÔNG lưu ô <select> vào options. Không mở Tk, không chạy ffmpeg."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from starlette.datastructures import FormData

from myvoice.web import core, server   # vá sys.path (scripts/) + import amain_taogiong_gui

gui = core.gui
hu = gui.hu
_VOICE_DIR = Path(__file__).resolve().parents[1] / "voice"
if str(_VOICE_DIR) not in sys.path:
    sys.path.insert(0, str(_VOICE_DIR))
import thu_giong  # noqa: E402


class BangMauTests(unittest.TestCase):
    def test_mac_dinh_dung_dau_va_tat_het(self):
        self.assertEqual(hu.mau_ten()[0], hu.MAU_MAC_DINH)
        ts = hu.mau_thong_so(hu.MAU_MAC_DINH)
        self.assertEqual(ts["pitch"], 0.0)
        self.assertFalse(hu.fx_active(**ts["fx"]))

    def test_moi_mau_du_5_so_trong_dai(self):
        for ten, m in hu.MAU_GIONG.items():
            self.assertEqual(set(m), {"pitch", *gui.FX_KEYS}, ten)
            self.assertTrue(hu.PITCH_MIN <= m["pitch"] <= hu.PITCH_MAX, ten)
            for k in gui.FX_KEYS:
                self.assertTrue(hu.FX_MIN <= m[k] <= hu.FX_MAX, f"{ten}.{k}")
            self.assertIn(ten, hu.MAU_MO_TA, ten)

    def test_cac_mau_khac_mac_dinh_deu_sang_giong(self):
        """Mục đích của bảng là trị ồm → mẫu nào ngoài Mặc định cũng bật sáng giọng."""
        for ten, m in hu.MAU_GIONG.items():
            if ten != hu.MAU_MAC_DINH:
                self.assertGreater(m["sang_giong"], 0, ten)

    def test_khong_hai_mau_cung_bo_so(self):
        bo = {(m["pitch"], tuple(sorted(hu.fx_from(m).items()))) for m in hu.MAU_GIONG.values()}
        self.assertEqual(len(bo), len(hu.MAU_GIONG))

    def test_thong_so_la_ban_sao_va_ten_la_tra_none(self):
        ts = hu.mau_thong_so("Sáng rõ")
        ts["fx"]["sang_giong"] = 1
        self.assertEqual(hu.MAU_GIONG["Sáng rõ"]["sang_giong"], 80)
        self.assertIsNone(hu.mau_thong_so(hu.MAU_TUY_CHINH))
        self.assertIsNone(hu.mau_thong_so("không có"))
        self.assertIsNone(hu.mau_thong_so(None))


class MauKhopTests(unittest.TestCase):
    def test_khop_dung_ten(self):
        for ten, m in hu.MAU_GIONG.items():
            self.assertEqual(hu.mau_khop(m["pitch"], m), ten)

    def test_doc_tu_options_dang_chuoi(self):
        """taogiong_options.json / form web đưa chuỗi, có khoá thừa — vẫn khớp."""
        opts = {"pitch": "1,0", "vang_truong_do": "0", "vang_cuong_do": "0",
                "thieu_nien": "0", "sang_giong": "80", "chunk": 160}
        self.assertEqual(hu.mau_khop(opts["pitch"], opts), "Sáng + cao nhẹ")

    def test_lech_mot_so_la_tuy_chinh(self):
        m = dict(hu.MAU_GIONG["Sáng rõ"])
        m["sang_giong"] = 75
        self.assertEqual(hu.mau_khop(m["pitch"], m), hu.MAU_TUY_CHINH)
        self.assertEqual(hu.mau_khop(0.5, hu.MAU_GIONG[hu.MAU_MAC_DINH]), hu.MAU_TUY_CHINH)

    def test_thieu_khoa_coi_nhu_tat_het(self):
        self.assertEqual(hu.mau_khop(None, None), hu.MAU_MAC_DINH)


class WebTests(unittest.TestCase):
    def test_voice_ctx_dua_mau_vao_form(self):
        opts = dict(gui.OPTS_DEFAULTS, pitch=0.0, sang_giong=80, vang_truong_do=0,
                    vang_cuong_do=0, thieu_nien=0)
        with patch.object(core, "load_options", return_value=opts), \
             patch.object(core, "load_web_settings", return_value={}), \
             patch.object(core, "list_voices", return_value=[]):
            ctx = server._voice_ctx()
        self.assertIs(ctx["mau_giong"], hu.MAU_GIONG)
        self.assertEqual([t for t, _ in ctx["mau_giong_mota"]], hu.mau_ten())
        self.assertEqual(ctx["mau_hien_tai"], "Sáng rõ")
        self.assertEqual(ctx["mau_tuy_chinh"], hu.MAU_TUY_CHINH)

    def test_server_khong_luu_o_mau_giong(self):
        """Server chỉ lưu 5 ô số (JS đã điền); ô <select> mau_giong không vào options."""
        saved: dict = {}
        form = FormData([("mau_giong", "Sáng rõ"), ("pitch", "0"), ("sang_giong", "80")])
        with patch.object(core, "load_options", return_value={"chunk": 160}), \
             patch.object(core, "save_options", side_effect=saved.update):
            server._save_opts_from_form(form)
        self.assertNotIn("mau_giong", saved)
        self.assertEqual((saved["pitch"], saved["sang_giong"]), (0.0, 80))


def _mo_tk():
    import tkinter as tk
    try:
        root = tk.Tk()
    except tk.TclError as e:          # máy không có màn hình
        raise unittest.SkipTest(f"không mở được Tk: {e}")
    root.withdraw()
    return root


class AppThuGiongTests(unittest.TestCase):
    """Hàng radio 🎚 trong voice/thu_giong.py (App thật, ẩn, không nạp model): bấm mẫu
    đặt 5 số + nhớ vào cài đặt RIÊNG của app (không đụng taogiong_options.json — 10/11/2026);
    kéo thanh lệch mẫu → "Tuỳ chỉnh"."""

    def setUp(self):
        self.root = _mo_tk()
        self.addCleanup(self.root.destroy)
        self.saved: dict = {}            # thay cho thu_giong_settings.json thật
        self.goc: dict = {}              # taogiong_options.json của bài thật — phải trống
        for p in (patch.object(thu_giong, "save_settings", lambda **kv: self.saved.update(kv)),
                  patch.object(gui, "save_opt_settings", lambda d: self.goc.update(d))):
            p.start()
            self.addCleanup(p.stop)
        self.app = thu_giong.App(self.root)

    def test_bam_mau_dat_5_so_va_nho_rieng(self):
        a = self.app
        a.var_mau.set("Sáng rõ")
        a._ap_mau()
        self.assertEqual(a._pitch(), 0.0)
        self.assertEqual(a._fx(), dict(vang_truong_do=0, vang_cuong_do=0, thieu_nien=0, sang_giong=80))
        self.assertEqual(a.var_mau.get(), "Sáng rõ")
        self.assertEqual(self.saved["fx"]["sang_giong"], 80)   # nhớ vào file riêng của app
        self.assertEqual(self.saved["pitch"], 0.0)
        self.assertEqual(self.goc, {})                         # bài thật KHÔNG bị ghi

    def test_khong_bao_gio_ghi_vao_bai_that(self):
        a = self.app
        a.var_mau.set("Sân khấu")
        a._ap_mau()
        a._set_pitch(1.0)
        a._set_am_luong(3.0)
        self.assertEqual(a._fx()["vang_cuong_do"], 25)
        self.assertEqual(self.goc, {})

    def test_keo_thanh_lech_mau_thanh_tuy_chinh(self):
        a = self.app
        a.var_mau.set("Sáng rõ")
        a._ap_mau()
        a._set_fx(sang_giong=75)
        self.assertEqual(a.var_mau.get(), hu.MAU_TUY_CHINH)
        a._set_fx(sang_giong=80)
        self.assertEqual(a.var_mau.get(), "Sáng rõ")
        a._set_pitch(1.0)
        self.assertEqual(a.var_mau.get(), "Sáng + cao nhẹ")

    def test_mo_len_radio_theo_muc_dang_luu(self):
        a = self.app
        self.assertEqual(a.var_mau.get(), hu.mau_khop(a._pitch(), a._fx()))


if __name__ == "__main__":
    unittest.main()
