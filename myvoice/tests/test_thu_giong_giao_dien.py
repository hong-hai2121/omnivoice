# -*- coding: utf-8 -*-
"""voice/thu_giong.py — trang OmniVoice làm lại 07/11/2026 theo khối "Cài đặt tạo giọng"
của web myvoice: ô văn bản = ≈30 s đầu kịch bản mới nhất (kich_ban_moi_nhat + van_ban_dau),
hai ô mới 🔊 âm lượng / 🔉 chuẩn âm đồng bộ cùng khoá với GUI/web, bản phát dựng ở luồng
nền (_render_file áp cả chuẩn âm + âm lượng), nút 🎧 Bài thật = taogiong_nghethu. Không nạp
model; phần Tk mở cửa sổ ẩn, bỏ qua khi máy không có màn hình; không ghi cài đặt thật."""
import json
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import soundfile as sf

from myvoice.web import core   # vá sys.path (scripts/) + import amain_taogiong_gui một lần

gui = core.gui
hu = gui.hu
_VOICE_DIR = Path(__file__).resolve().parents[1] / "voice"
if str(_VOICE_DIR) not in sys.path:
    sys.path.insert(0, str(_VOICE_DIR))
import thu_giong  # noqa: E402
import taogiong_nghethu as nt  # noqa: E402

# ~10 âm tiết một câu ≈ 2,15 s + nghỉ 0,45 s → ~2,6 s/câu.
CAU = "Trời hôm nay trong xanh và gió thổi rất nhẹ nhàng."


class VanBanDauTests(unittest.TestCase):
    def test_lay_du_giay_roi_dung_o_cuoi_cau(self):
        text = " ".join([CAU] * 40)
        vb, tt = thu_giong.van_ban_dau(text, giay=30, chunk=160)
        self.assertGreaterEqual(tt["giay"], 30)
        self.assertLess(tt["giay"], 30 + 4)              # chỉ dư đúng một câu
        self.assertTrue(vb.endswith("."))
        self.assertFalse(tt["het"])
        self.assertEqual(tt["so_cau"], vb.count(CAU))
        self.assertLess(len(vb), len(text))

    def test_bai_ngan_lay_het(self):
        vb, tt = thu_giong.van_ban_dau(CAU + " Rồi mọi chuyện cũng xong.", giay=30, chunk=160)
        self.assertEqual(vb, CAU + " Rồi mọi chuyện cũng xong.")
        self.assertTrue(tt["het"])
        self.assertEqual(tt["so_cau"], 2)

    def test_khong_dung_o_mau_bi_cat_boi_dau_phay(self):
        """Câu dài hơn ô chunk bị cắt ở dấu phẩy thành nhiều mẩu — đủ giây giữa câu thì vẫn
        lấy tiếp tới hết câu, không để văn bản thử cụt ở dấu phẩy."""
        dai = ("Cô ấy bước đi thật chậm, " * 6 + "rồi dừng lại trước cửa.")
        vb, tt = thu_giong.van_ban_dau(dai + " Câu sau đứng riêng một mình.", giay=1, chunk=40)
        self.assertTrue(vb.endswith("cửa."), vb)
        self.assertNotIn("Câu sau", vb)
        self.assertGreater(tt["so_cau"], 1)              # nhiều mẩu nhưng là một câu

    def test_giu_doan_van_va_chu_hoa(self):
        text = "Đoạn một câu một. Đoạn một câu hai.\nĐoạn hai câu một. Đoạn hai câu hai."
        vb, tt = thu_giong.van_ban_dau(text, giay=1000, chunk=160)
        self.assertEqual(vb, text)
        self.assertTrue(tt["het"])
        vb2, _ = thu_giong.van_ban_dau(text, giay=0.1, chunk=160)
        self.assertEqual(vb2, "Đoạn một câu một.")      # dừng ngay sau câu đầu, giữ chữ hoa

    def test_van_ban_trong(self):
        self.assertEqual(thu_giong.van_ban_dau("", giay=30, chunk=160),
                         ("", dict(so_cau=0, giay=0.0, het=True)))


class KichBanMoiNhatTests(unittest.TestCase):
    """Chọn thư mục tập TẠO SAU CÙNG có input (docx/txt có chữ), không theo số tập."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.kb = Path(tmp.name) / "kịch_bản"
        self.kb.mkdir()
        self.luc = {}
        for p in (patch.object(gui, "SCRIPT_DIR", self.kb),
                  patch.object(nt, "_tao_luc", lambda p: self.luc[Path(p).name])):
            p.start()
            self.addCleanup(p.stop)

    def tap(self, ten, luc, input_txt=None):
        d = self.kb / ten
        d.mkdir()
        if input_txt is not None:
            (d / "input.txt").write_text(input_txt, encoding="utf-8")
        self.luc[ten] = luc
        return d

    def test_lay_tap_tao_sau_cung_co_input(self):
        self.tap("A01 - x", 100.0, "Tập một.")
        moi = self.tap("B02 - y", 300.0, "Tập hai.")
        self.tap("C03 - z", 400.0)                        # tạo sau nhất nhưng chưa có kịch bản
        self.tap("D04 - w", 50.0, "Tập bốn.")             # số lớn nhất nhưng tạo trước
        self.assertEqual(thu_giong.kich_ban_moi_nhat(), moi)

    def test_khong_tap_nao_co_input(self):
        self.tap("A01 - x", 100.0)
        self.tap("B02 - y", 200.0, "")                    # file rỗng = chưa có nội dung
        self.assertIsNone(thu_giong.kich_ban_moi_nhat())

    def test_kich_ban_trong_tra_none(self):
        self.assertIsNone(thu_giong.kich_ban_moi_nhat())


class ThongSoAmLuongTests(unittest.TestCase):
    """thong_so_doc / thong_so_luu nhớ 🔊 am_luong trong thu_giong_settings.json (riêng của app,
    10/11/2026 — không còn liên kết taogiong_options.json; 🔉 chuan_am gỡ 10/11/2026)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.f = Path(tmp.name) / "thu_giong_settings.json"
        self.f.write_text(json.dumps({"voice": "a.wav", "speed": 1.2, "pitch": 0.0,
                                      "fx": {"sang_giong": 0}, "am_luong": 5.0}), encoding="utf-8")
        p = patch.object(thu_giong, "SETTINGS_FILE", self.f)
        p.start()
        self.addCleanup(p.stop)

    def _doc(self):
        return json.loads(self.f.read_text(encoding="utf-8"))

    def test_doc_du_khoa(self):
        bt = thu_giong.thong_so_doc()
        self.assertEqual(set(bt), {"speed", "pitch", "fx", "am_luong"})
        self.assertEqual((bt["speed"], bt["am_luong"]), (1.2, 5.0))
        self.assertNotIn("chuan_am", bt)

    def test_luu_du_bo_so(self):
        thu_giong.thong_so_luu(1.0, 1.0, None, am_luong=6.3)
        d = self._doc()
        self.assertEqual(d["am_luong"], 6.5)              # làm tròn 0,5 như hu.parse_amluong
        self.assertEqual(d["voice"], "a.wav")             # khoá khác giữ nguyên
        self.assertNotIn("chuan_am", d)

    def test_goi_kieu_cu_khong_dung_am_luong(self):
        thu_giong.thong_so_luu(1.0, 2.0, None)
        d = self._doc()
        self.assertEqual(d["am_luong"], 5.0)
        self.assertEqual(d["pitch"], 2.0)

    def test_mo_ta_co_am_luong(self):
        s = thu_giong.mo_ta_thong_so(1.2, 0.0, None, am_luong=5.0)
        self.assertIn("âm lượng +5.0 dB", s)
        s0 = thu_giong.mo_ta_thong_so(1.2, 0.0, None)
        self.assertNotIn("âm lượng", s0)
        self.assertNotIn("chuẩn âm", s0)
        self.assertEqual(thu_giong.fmt_am_luong(0.0), "0 dB")
        self.assertEqual(thu_giong.fmt_am_luong(-2.5), "-2.5 dB")


def _mo_tk():
    import tkinter as tk
    try:
        root = tk.Tk()
    except tk.TclError as e:          # máy không có màn hình
        raise unittest.SkipTest(f"không mở được Tk: {e}")
    root.withdraw()
    return root


class AppGiaoDienTests(unittest.TestCase):
    """App thật mở ẩn: đủ ô mới, văn bản thử nạp từ kịch bản, phát lại theo loại đang phát."""

    def setUp(self):
        self.root = _mo_tk()
        self.addCleanup(self.root.destroy)
        for p in (patch.object(gui, "save_opt_settings", lambda *_a, **_k: None),
                  patch.object(thu_giong, "save_settings", lambda **_k: None)):
            p.start()
            self.addCleanup(p.stop)
        self.app = thu_giong.App(self.root)

    def test_co_du_o_moi_va_nut_bai_that(self):
        a = self.app
        for w in (a.btn_bai_that, a.lbl_am_luong, a.lbl_van_ban, a.txt):
            self.assertTrue(w.winfo_exists())
        self.assertIn("Bài thật", a.btn_bai_that.cget("text"))
        ts = a._thong_so()
        self.assertEqual(set(ts), {"speed", "pitch", "fx", "am_luong"})
        self.assertEqual(ts["am_luong"], thu_giong.default_am_luong())
        self.assertEqual(set(a.var_fx), {"vang_truong_do", "vang_cuong_do", "thieu_nien", "sang_giong"})

    def test_trang_vua_cua_so_mac_dinh(self):
        """Hai cột thanh chỉnh + hàng nút phải vừa bề ngang/cao cửa sổ mặc định (không tràn)."""
        a = self.app
        a._chon_tab("omni", luu=False)
        self.root.update_idletasks()
        trang = a._pages["omni"]
        self.assertLessEqual(trang.winfo_reqwidth(), 1100 + 150)
        self.assertLessEqual(trang.winfo_reqheight(), 830)

    def test_van_ban_nap_tu_kich_ban_moi_nhat(self):
        a = self.app
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        tap = Path(tmp.name) / "Z170 - truyện thử"
        tap.mkdir()
        (tap / "input.txt").write_text(" ".join([CAU] * 30), encoding="utf-8")
        a.var_giay.set("20")
        with patch.object(thu_giong, "kich_ban_moi_nhat", lambda: tap):
            a._nap_van_ban(bao=True)
        chu = a.txt.get("1.0", "end").strip()
        self.assertTrue(chu.startswith(CAU))
        self.assertTrue(chu.endswith("."))
        self.assertLess(len(chu), len(" ".join([CAU] * 30)))
        self.assertIn("tập 170", a.lbl_van_ban.cget("text"))
        self.assertIn("≈2", a.lbl_van_ban.cget("text"))     # ≈20–23 s

    def test_khong_co_kich_ban_thi_dung_cau_mau(self):
        a = self.app
        with patch.object(thu_giong, "kich_ban_moi_nhat", lambda: None):
            a._nap_van_ban(bao=False)
        self.assertEqual(a.txt.get("1.0", "end").strip(), thu_giong.DEFAULT_SCRIPT)
        self.assertIn("câu mẫu", a.lbl_van_ban.cget("text"))
        a._van_ban_mau_san()
        self.assertEqual(a.txt.get("1.0", "end").strip(), thu_giong.DEFAULT_SCRIPT)

    def test_o_giay_kep_va_rac(self):
        a = self.app
        self.assertEqual(a._kep_giay("45"), 45)
        self.assertEqual(a._kep_giay("3"), thu_giong.VAN_BAN_GIAY_MIN)
        self.assertEqual(a._kep_giay("999"), thu_giong.VAN_BAN_GIAY_MAX)
        self.assertEqual(a._kep_giay("xx"), thu_giong.VAN_BAN_GIAY)
        self.assertEqual(a._kep_giay(None), thu_giong.VAN_BAN_GIAY)

    def test_am_luong_lam_tron_va_kep(self):
        a = self.app
        a._replay_if_playing = MagicMock()
        a._set_am_luong(6.3)
        self.assertEqual(a._am_luong(), 6.5)
        self.assertEqual(a.lbl_am_luong.cget("text"), "+6.5 dB")
        a._set_am_luong(99)
        self.assertEqual(a._am_luong(), hu.AMLUONG_MAX)
        a._set_am_luong(0)
        self.assertEqual(a.lbl_am_luong.cget("text"), "0 dB")

    def test_keo_thanh_khi_dang_nghe_bai_that_thi_dung_lai_mau(self):
        a = self.app
        a._on_nghe_bai_that = MagicMock()
        a._play_file = MagicMock()
        a._playing, a._play_until = True, time.monotonic() + 30
        a._last_raw, a._last_bai_that, a._last_src = False, True, None
        a._replay_if_playing()
        a._on_nghe_bai_that.assert_called_once()
        a._play_file.assert_not_called()

    def test_phat_clone_dung_o_luong_nen_roi_phat(self):
        """_play_file: dựng (_render_file) ở luồng nền → về queue → _play_wav với bản dựng."""
        a = self.app
        ra = Path("ban_dung.wav")
        a._render_file = MagicMock(return_value=ra)
        a._play_wav = MagicMock(return_value=1.0)
        a._play_file(Path("clone.wav"))
        self.assertTrue(a._is_playing())                  # đang dựng = coi như đang phát
        for _ in range(50):
            if a.q.qsize():
                break
            time.sleep(0.02)
        kind, cb = "", None
        while kind != "call":                             # bỏ qua dòng log lúc mở app
            kind, cb = a.q.get_nowait()
        cb()
        a._play_wav.assert_called_once()
        self.assertEqual(a._play_wav.call_args.args[0], ra)
        self.assertEqual(a._render_file.call_args.args[0], Path("clone.wav"))
        self.assertEqual(set(a._render_file.call_args.kwargs), {"speed", "pitch", "fx", "am_luong"})

    def test_dung_bo_ket_qua_luot_dung_cu(self):
        a = self.app
        a._play_wav = MagicMock()
        token = a._render_token
        with patch("winsound.PlaySound"):
            a._stop_play()
        a._phat_sau_dung(token, Path("x.wav"), Path("y.wav"), None, a._thong_so())
        a._play_wav.assert_not_called()


@unittest.skipUnless(shutil.which("ffmpeg"), "cần ffmpeg")
class RenderFileTests(unittest.TestCase):
    """_render_file áp 🔊 âm lượng và 🔉 chuẩn âm lên bản phát (file gốc không đổi)."""

    def setUp(self):
        self.root = _mo_tk()
        self.addCleanup(self.root.destroy)
        for p in (patch.object(gui, "save_opt_settings", lambda *_a, **_k: None),
                  patch.object(thu_giong, "save_settings", lambda **_k: None)):
            p.start()
            self.addCleanup(p.stop)
        self.app = thu_giong.App(self.root)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        p2 = patch.object(thu_giong, "SPEED_DIR", self.tmp / "_tocdo")
        p2.start()
        self.addCleanup(p2.stop)
        self.src = self.tmp / "clone.wav"
        sr = 24000
        t = np.arange(int(4.0 * sr)) / sr
        self.x = (0.1 * np.sin(2 * np.pi * 220 * t)).astype("float32")
        sf.write(str(self.src), self.x, sr, subtype="FLOAT")

    @staticmethod
    def _rms(p):
        x, _ = sf.read(str(p), dtype="float32")
        return float(np.sqrt(np.mean(x.astype("float64") ** 2)))

    def test_khong_ap_gi_tra_chinh_file(self):
        self.assertEqual(self.app._render_file(self.src, 1.0, 0.0, None, am_luong=0.0),
                         self.src)

    def test_am_luong_cong_6db(self):
        out = self.app._render_file(self.src, 1.0, 0.0, None, am_luong=6.0)
        self.assertNotEqual(out, self.src)
        self.assertIn("_am+6.0", out.name)
        self.assertAlmostEqual(self._rms(out) / self._rms(self.src), 2.0, delta=0.1)
        self.assertEqual(self._rms(self.src), float(np.sqrt(np.mean(self.x.astype("float64") ** 2))))
        # cache: gọi lại không chạy ffmpeg
        with patch.object(thu_giong.subprocess, "run") as run:
            self.assertEqual(self.app._render_file(self.src, 1.0, 0.0, None, am_luong=6.0), out)
        run.assert_not_called()

if __name__ == "__main__":
    unittest.main()
