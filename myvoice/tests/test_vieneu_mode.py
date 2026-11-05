# -*- coding: utf-8 -*-
"""Chế độ 🗣 VieNeu trong bài tạo giọng thật (04/11/2026): worker SDK + client, nhánh engine
trong amain_taogiong_gui, GUI mặc định tick VieNeu và chuyển qua lại với Clone.
Không cần cài VieNeu: worker chạy với engine GIẢ (make_server), GUI ẩn."""
import socket
import sys
import threading
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from myvoice.web import core  # noqa: F401  vá sys.path (scripts/) + import amain_taogiong_gui
import amain_taogiong_gui as tts  # noqa: E402

_VOICE_DIR = Path(__file__).resolve().parents[1] / "voice"
if str(_VOICE_DIR) not in sys.path:
    sys.path.insert(0, str(_VOICE_DIR))
import vieneu_client as vn  # noqa: E402
import vieneu_worker as vw  # noqa: E402


def _cong_trong() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class EngineGia:
    """Thay Vieneu(): ghi lại lời gọi, trả 0,5 s sin cho mỗi text (dài theo số chữ)."""
    voices = ["Ngọc Huyền", "Hải Đăng"]
    backend = "gia"

    def __init__(self):
        self.goi: list[tuple] = []

    def infer(self, texts, voice, temperature, top_k):
        self.goi.append((list(texts), voice, temperature, top_k))
        out = []
        for i, t in enumerate(texts):
            n = int(vw.SR * (0.2 + 0.01 * len(t)))
            out.append(0.3 * np.sin(2 * np.pi * (220 + 55 * i) * np.arange(n) / vw.SR).astype(np.float32))
        return out


class WorkerGia:
    """Thay SdkWorker trong các test không cần HTTP: doc() ghi lại, tat() đếm."""
    sr = 48_000

    def __init__(self):
        self.goi: list[tuple[str, str]] = []
        self.so_tat = 0

    def doc(self, text, voice, **kw):
        self.goi.append((text, voice))
        return np.zeros(4800, dtype=np.float32)

    def tat(self):
        self.so_tat += 1


class TestWorkerVaClient(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.eng = EngineGia()
        cls.cong = _cong_trong()
        cls.srv = vw.make_server(cls.eng, cls.cong)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.w = vn.SdkWorker()
        cls.w.cong = cls.cong          # không bật tiến trình con — server giả đang nghe cổng này

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def test_ma_hoa_giai_ma_khop(self):
        a = np.linspace(-1, 1, 1000, dtype=np.float32)
        b = vn.giai_ma_audio(vw.ma_hoa_audio(a))
        self.assertEqual(b.dtype, np.float32)
        self.assertEqual(len(b), 1000)
        self.assertLess(float(np.abs(a - b).max()), 1e-4)
        # int16 vào thẳng, stereo → mono
        c = vn.giai_ma_audio(vw.ma_hoa_audio(np.array([[16384, 16384], [0, 0]], dtype=np.int16)))
        self.assertAlmostEqual(float(c[0]), 0.5, places=3)

    def test_health_co_sr_va_giong(self):
        h = self.w.health()
        self.assertEqual(h["status"], "ok")
        self.assertEqual(h["sr"], 48_000)
        self.assertEqual(h["voices"], ["Ngọc Huyền", "Hải Đăng"])

    def test_doc_mot_doan(self):
        a = self.w.doc("Xin chào Hội An.", "Ngọc Huyền", temperature=0.5)
        self.assertEqual(a.dtype, np.float32)
        self.assertGreater(len(a), vw.SR * 0.3)
        self.assertEqual(self.eng.goi[-1], (["Xin chào Hội An."], "Ngọc Huyền", 0.5, 50))

    def test_doc_nhieu_giu_thu_tu_va_do_dai(self):
        texts = ["Câu một.", "Câu thứ hai dài hơn một chút.", "Ba."]
        out = self.w.doc_nhieu(texts, "Hải Đăng")
        self.assertEqual(len(out), 3)
        self.assertEqual([len(x) for x in out],
                         [int(vw.SR * (0.2 + 0.01 * len(t))) for t in texts])
        self.assertEqual(self.eng.goi[-1][0], texts)

    def test_loi_400_khi_texts_rong(self):
        with self.assertRaises(RuntimeError) as cm:
            self.w.doc_nhieu([], "Ngọc Huyền")
        self.assertIn("400", str(cm.exception))
        with self.assertRaises(RuntimeError):
            self.w.doc("   ", "Ngọc Huyền")

    def test_loi_engine_thanh_500_khong_chet_server(self):
        def no(*a, **k):
            raise ValueError("giọng lạ")
        with patch.object(self.eng, "infer", no):
            with self.assertRaises(RuntimeError) as cm:
                self.w.doc("x", "ai đó")
        self.assertIn("500", str(cm.exception))
        self.assertIn("giọng lạ", str(cm.exception))
        self.assertTrue(self.w.health())      # server vẫn sống

    def test_duong_la_404(self):
        import requests
        self.assertEqual(requests.get(self.w.url + "/khac", timeout=2).status_code, 404)

    def test_chon_cong_tra_cong_trong(self):
        c = vn.chon_cong(self.cong, 5)       # cổng đầu đang bận (server giả) → phải nhảy qua
        self.assertNotEqual(c, self.cong)
        self.assertTrue(self.cong < c < self.cong + 5)

    def test_danh_sach_giong_tinh(self):
        self.assertEqual(len(vn.GIONG_DUNG_SAN), 25)
        self.assertIn("Ngọc Huyền", vn.GIONG_DUNG_SAN)
        self.assertEqual(vn.GIONG_MAC_DINH, "Ngọc Huyền")
        self.assertEqual(len(set(vn.GIONG_DUNG_SAN)), 25)


class TestEngineTrongAmain(unittest.TestCase):
    def test_mac_dinh_la_vieneu_ngoc_huyen(self):
        self.assertEqual(tts.OPTS_DEFAULTS["mode"], "vieneu")
        self.assertEqual(tts.OPTS_DEFAULTS["vieneu_voice"], "Ngọc Huyền")
        self.assertEqual(tts.MODES[0], tts.MODE_VIENEU)
        self.assertIn("clone", tts.MODES)

    def test_generate_chunk_vieneu_goi_worker(self):
        w = WorkerGia()
        kq = tts._generate_chunk(w, "vieneu", "Ngọc Huyền", "  Xin  chào\nHội An. ", dur_scale=1.06, sang_giong=80)
        self.assertEqual(kq[1], 48_000)
        self.assertEqual(len(kq[0]), 4800)
        self.assertEqual(w.goi, [("Xin chào Hội An.", "Ngọc Huyền")])   # gộp khoảng trắng như clone

    def test_do_engine_tat_worker_tra_none(self):
        w = vn.SdkWorker()
        with patch.object(w, "tat") as tat:
            self.assertIsNone(tts.do_engine(w, "thử"))
        tat.assert_called_once()

    def test_do_engine_omnivoice_di_duong_cu(self):
        with patch.object(tts, "_do_omnivoice", return_value=None) as do:
            self.assertIsNone(tts.do_engine(object(), "thử"))
        do.assert_called_once()

    def test_nap_engine_vieneu_chua_cai_bao_ro(self):
        with patch.object(tts.vn, "trang_thai", return_value=dict(da_cai=False)):
            with self.assertRaises(RuntimeError) as cm:
                tts.nap_engine("vieneu")
        self.assertIn("chưa cài", str(cm.exception))
        self.assertIn("Clone", str(cm.exception))

    def test_nap_engine_vieneu_bat_worker(self):
        class W:
            sr, backend, giong = 48_000, "gia", ["a"]

            def bat(self, device="auto", on_line=None):   # 05/11/2026: bài thật ép device="cuda"
                self.da_bat = True
                return {}
        w = W()
        with patch.object(tts.vn, "trang_thai", return_value=dict(da_cai=True)), \
                patch.object(tts.vn, "SdkWorker", return_value=w):
            model, sr = tts.nap_engine("vieneu")
        self.assertIs(model, w)
        self.assertTrue(w.da_bat)
        self.assertEqual(sr, 48_000)

    def test_chu_ky_phan_biet_che_do_va_giong(self):
        """mode/voice_param nằm trong chữ ký run_tts → đổi engine là sinh lại đoạn."""
        import hashlib
        def sig(mode, voice):
            return hashlib.sha1("|".join([mode, str(voice), f"step{tts.NUM_STEP}",
                                          f"fade{tts.FADE_OUT_SEC}", "a", "b"]).encode()).hexdigest()
        self.assertNotEqual(sig("vieneu", "Ngọc Huyền"), sig("clone", "x.wav"))
        self.assertNotEqual(sig("vieneu", "Ngọc Huyền"), sig("vieneu", "Hải Đăng"))


class TestGuiCheDo(unittest.TestCase):
    """App thật nhưng ẩn, cài đặt = MẶC ĐỊNH (không đọc/ghi taogiong_options.json của user)."""

    @classmethod
    def setUpClass(cls):
        cls._p = patch.object(tts, "load_opt_settings", lambda: dict(tts.OPTS_DEFAULTS))
        cls._p.start()
        try:
            cls.app = tts.App()
        except tk.TclError as e:
            cls._p.stop()
            raise unittest.SkipTest(f"không mở được Tk: {e}")
        cls.app.withdraw()
        cls.app.update_idletasks()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.app.destroy()
        finally:
            cls._p.stop()

    def test_mo_len_tick_vieneu_ngoc_huyen(self):
        self.assertEqual(self.app.var_mode.get(), "vieneu")
        self.assertEqual(self.app.var_vieneu_voice.get(), "Ngọc Huyền")
        self.assertEqual(self.app.frm_vieneu.winfo_manager(), "pack")
        self.assertEqual(self.app.frm_clone.winfo_manager(), "")
        self.assertEqual(list(self.app.cb_vieneu["values"]), list(vn.GIONG_DUNG_SAN))

    def test_chuyen_qua_clone_roi_quay_lai(self):
        self.app.var_mode.set("clone")
        self.app._on_mode_change()
        self.assertEqual(self.app.frm_clone.winfo_manager(), "pack")
        self.assertEqual(self.app.frm_vieneu.winfo_manager(), "")
        self.app.var_mode.set("vieneu")
        self.app._on_mode_change()
        self.assertEqual(self.app.frm_vieneu.winfo_manager(), "pack")
        self.assertEqual(self.app.frm_clone.winfo_manager(), "")

    def test_cai_dat_chay_vieneu(self):
        self.app.var_mode.set("vieneu")
        self.app.var_vieneu_voice.set("Hải Đăng")
        with patch.object(tts.vn, "trang_thai", return_value=dict(da_cai=True)):
            ts = self.app._collect_tts_settings()
        self.assertIsNotNone(ts)
        self.assertEqual(ts["mode"], "vieneu")
        self.assertEqual(ts["voice_param"], "Hải Đăng")
        self.app.var_vieneu_voice.set("Ngọc Huyền")

    def test_chua_cai_thi_canh_bao_khong_chay(self):
        self.app.var_mode.set("vieneu")
        with patch.object(tts.vn, "trang_thai", return_value=dict(da_cai=False)), \
                patch.object(tts.messagebox, "showwarning") as warn:
            self.assertIsNone(self.app._collect_tts_settings())
        warn.assert_called_once()
        self.assertIn("Cài GPU", warn.call_args[0][1])

    def test_luu_cai_dat_co_mode_va_giong(self):
        self.app.var_mode.set("vieneu")
        with patch.object(tts, "save_opt_settings") as save:
            self.app._save_opt_settings()
        d = save.call_args[0][0]
        self.assertEqual(d["mode"], "vieneu")
        self.assertEqual(d["vieneu_voice"], "Ngọc Huyền")

    def test_mode_lau_tro_ve_mac_dinh(self):
        """Giá trị lạ / thiếu trong file cài đặt (bản cũ) không làm radio trống."""
        self.assertEqual(tts.che_do_da_luu({}), ("vieneu", "Ngọc Huyền"))
        self.assertEqual(tts.che_do_da_luu(dict(mode="x", vieneu_voice="?")), ("vieneu", "Ngọc Huyền"))
        self.assertEqual(tts.che_do_da_luu(dict(mode="clone", vieneu_voice="Hải Đăng")), ("clone", "Hải Đăng"))
        self.assertEqual(tts.che_do_da_luu(dict(mode="design")), ("design", "Ngọc Huyền"))


class TestWeb(unittest.TestCase):
    """Bản web (chạy thẳng amain là mở web): mặc định vieneu, lưu/đọc giọng VieNeu, gói cài đặt."""

    def test_mac_dinh_web_la_vieneu(self):
        self.assertEqual(core.WEB_DEFAULTS["mode"], "vieneu")
        self.assertEqual(core.WEB_DEFAULTS["vieneu_voice"], "Ngọc Huyền")
        self.assertEqual(core.giong_vieneu_hop_le(None), "Ngọc Huyền")
        self.assertEqual(core.giong_vieneu_hop_le("lạ"), "Ngọc Huyền")
        self.assertEqual(core.giong_vieneu_hop_le("Hải Đăng"), "Hải Đăng")

    def test_tts_settings_vieneu(self):
        with patch.object(core, "load_web_settings", lambda: dict(core.WEB_DEFAULTS, vieneu_voice="Mai Anh")), \
                patch.object(tts.vn, "trang_thai", return_value=dict(da_cai=True)):
            st, loi = core.tts_settings()
        self.assertEqual(loi, "")
        self.assertEqual((st["mode"], st["voice_param"]), ("vieneu", "Mai Anh"))

    def test_tts_settings_vieneu_chua_cai(self):
        with patch.object(core, "load_web_settings", lambda: dict(core.WEB_DEFAULTS)), \
                patch.object(tts.vn, "trang_thai", return_value=dict(da_cai=False)):
            st, loi = core.tts_settings()
        self.assertIsNone(st)
        self.assertIn("Cài GPU", loi)

    def test_luu_form_co_vieneu_voice(self):
        from starlette.datastructures import FormData
        from myvoice.web import server
        got = {}
        with patch.object(core, "save_web_settings", got.update), \
                patch.object(server, "_save_opts_from_form", lambda f: None):
            server._save_voice_from_form(FormData([("mode", "vieneu"), ("vieneu_voice", "Trúc Ly"),
                                                   ("voice", "x.wav")]))
            self.assertEqual((got["mode"], got["vieneu_voice"]), ("vieneu", "Trúc Ly"))
            server._save_voice_from_form(FormData([("voice", "x.wav")]))   # form cũ không có ô
            self.assertEqual((got["mode"], got["vieneu_voice"]), ("vieneu", "Ngọc Huyền"))

    def test_ngu_canh_trang_giong(self):
        from myvoice.web import server
        with patch.object(core, "load_web_settings", lambda: dict(core.WEB_DEFAULTS, vieneu_voice="?")), \
                patch.object(tts.vn, "trang_thai", return_value=dict(da_cai=True)):
            ctx = server._voice_ctx()
        self.assertEqual(ctx["vieneu_voices"], list(vn.GIONG_DUNG_SAN))
        self.assertEqual(ctx["current_vieneu_voice"], "Ngọc Huyền")
        self.assertTrue(ctx["vieneu_da_cai"])
        html = (Path(core.WEB_DIR) / "templates" / "_form_voice.html").read_text(encoding="utf-8")
        self.assertIn('("vieneu", "🗣 VieNeu"', html)
        self.assertIn('name="vieneu_voice"', html)


if __name__ == "__main__":
    unittest.main()
