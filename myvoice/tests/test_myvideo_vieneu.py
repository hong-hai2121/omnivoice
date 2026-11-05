# -*- coding: utf-8 -*-
"""myvideo bước ③ với chế độ 🗣 VieNeu (04/11/2026): taogiong_srt.generate_all đi qua
nap_engine/Giong (engine giả), sổ _vanban.json nhớ engine+giọng → đổi là đọc lại; steps.py
truyền --engine/--giong-vieneu; server: cài đặt mặc định, form, route nghe thử, trang render."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(REPO / "myvideo") not in sys.path:
    sys.path.insert(0, str(REPO / "myvideo"))
import taogiong_srt as ts  # noqa: E402  (tự chèn myvoice/scripts, kéo amain_taogiong_gui)
# Import server myvideo mà KHÔNG cho luồng nền (hàng đợi, canh tắt máy) khởi động: luồng
# nền sống tới cuối bộ test, GC chạy trong luồng đó dọn cửa sổ Tk sót của các test GUI
# → "Tcl_AsyncDelete: async handler deleted by the wrong thread" làm sập cả bộ test.
import gc  # noqa: E402
import threading  # noqa: E402
gc.collect()
with patch.object(threading.Thread, "start", lambda self: None):
    from myvideo.web import steps as st, server as sv  # noqa: E402

CUES = [("00:00:00,500 --> 00:00:02,000", "Xin chào Hội An"),
        ("00:00:02,500 --> 00:00:04,000", "Hôm nay trời đẹp."),
        ("00:00:04,500 --> 00:00:06,000", "Hẹn gặp lại")]


class EngineGia:
    """Thay worker VieNeu / model OmniVoice: ghi lại (mode, voice_param, text), trả 0,3 s."""
    sr = 48_000

    def __init__(self):
        self.goi = []
        self.so_tat = 0

    def doc(self, text, voice, **kw):           # đường vieneu của _generate_chunk
        self.goi.append(("vieneu", voice, text))
        return np.full(int(self.sr * 0.3), 0.1, dtype=np.float32)

    def tat(self):
        self.so_tat += 1


class TestGenerateAll(unittest.TestCase):
    def _chay(self, d, giong, sang=80, redo=False):
        eng = EngineGia()
        # clone: _generate_chunk thật gọi model.generate → thay bằng hàm giả để không cần GPU.
        def gen(model, mode, voice_param, text, dur_scale=1.0, sang_giong=0):
            if mode == "vieneu":
                return model.doc(" ".join(text.split()), voice_param), 48_000
            model.goi.append(("clone", voice_param, text, sang_giong))
            return np.full(7200, 0.1, dtype=np.float32), 24_000
        with patch.object(ts, "nap_engine", lambda mode: (eng, 48_000 if mode == "vieneu" else 24_000)), \
                patch.object(ts, "_generate_chunk", gen), \
                patch.object(ts, "_voice_prompt", lambda m, p, s: m.goi.append(("prompt", p, s))):
            files, model, sr = ts.generate_all(CUES, giong, d / "x_tts", redo=redo, sang=sang)
        return files, model, sr, eng

    def test_vieneu_doc_moi_cau_va_ghi_so(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            files, model, sr, eng = self._chay(d, ts.giong_vieneu("Ngọc Huyền"))
            self.assertEqual(sr, 48_000)
            self.assertEqual(len(files), 3)
            self.assertTrue(all(f and f.exists() for f in files))
            self.assertEqual([g[0] for g in eng.goi], ["vieneu"] * 3)        # không dựng prompt
            self.assertEqual(eng.goi[0][1], "Ngọc Huyền")
            self.assertEqual(eng.goi[0][2], "xin chào hội an.")              # tts_text như trước
            so = json.loads((d / "x_tts" / "_vanban.json").read_text(encoding="utf-8"))
            self.assertEqual((so["giong"], so["sang"]), ("vieneu|Ngọc Huyền", 0))   # VieNeu: sổ mức 0
            # chạy lại cùng cấu hình → không đọc lại gì, không nạp model
            files2, model2, sr2, eng2 = self._chay(d, ts.giong_vieneu("Ngọc Huyền"))
            self.assertIsNone(model2)
            self.assertEqual(eng2.goi, [])
            # đổi mức 🔆 khi đang VieNeu: không ảnh hưởng prompt → vẫn không đọc lại
            _f, model3, _s, eng3 = self._chay(d, ts.giong_vieneu("Ngọc Huyền"), sang=0)
            self.assertIsNone(model3)

    def test_doi_engine_hay_giong_la_doc_lai_het(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            self._chay(d, ts.giong_vieneu("Ngọc Huyền"))
            _f, _m, _s, eng = self._chay(d, ts.giong_vieneu("Hải Đăng"))
            self.assertEqual(len([g for g in eng.goi if g[0] == "vieneu"]), 3)
            _f, _m, sr, eng = self._chay(d, ts.giong_clone(Path("C:/kho/mau.wav")), sang=80)
            self.assertEqual(sr, 24_000)
            self.assertEqual(eng.goi[0], ("prompt", str(Path("C:/kho/mau.wav")), 80))
            self.assertEqual(len([g for g in eng.goi if g[0] == "clone"]), 3)
            so = json.loads((d / "x_tts" / "_vanban.json").read_text(encoding="utf-8"))
            self.assertEqual((so["giong"], so["sang"]), ("clone|mau.wav", 80))
            # clone đổi mức sáng giọng → đọc lại (như trước 04/11)
            _f, _m, _s, eng = self._chay(d, ts.giong_clone(Path("C:/kho/mau.wav")), sang=40)
            self.assertEqual(len([g for g in eng.goi if g[0] == "clone"]), 3)

    def test_so_cu_khong_co_giong(self):
        """Sổ bản cũ (chỉ sang + cau) = OmniVoice clone: nay clone → giữ; nay VieNeu → đọc lại."""
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            self._chay(d, ts.giong_clone(Path("C:/kho/mau.wav")), sang=80)
            so = d / "x_tts" / "_vanban.json"
            cu = json.loads(so.read_text(encoding="utf-8"))
            del cu["giong"]
            so.write_text(json.dumps(cu, ensure_ascii=False), encoding="utf-8")
            _f, model, _s, eng = self._chay(d, ts.giong_clone(Path("C:/kho/mau.wav")), sang=80)
            self.assertIsNone(model)
            _f, _m, _s, eng = self._chay(d, ts.giong_vieneu("Ngọc Huyền"))
            self.assertEqual(len(eng.goi), 3)

    def test_giong_vieneu_la_ve_mac_dinh(self):
        self.assertEqual(ts.giong_vieneu("không có").ten, "Ngọc Huyền")
        self.assertEqual(ts.giong_vieneu("").id, "vieneu|Ngọc Huyền")
        g = ts.giong_vieneu("Mai Anh")
        self.assertEqual((g.mode, g.voice_param, g.clone), ("vieneu", "Mai Anh", False))
        c = ts.giong_clone(Path("D:/a/b.mp3"))
        self.assertEqual((c.mode, c.ten, c.clone), ("clone", "b.mp3", True))


class TestSteps(unittest.TestCase):
    def _argv(self, s):
        with tempfile.TemporaryDirectory() as td:
            b = Path(td) / "tap1"
            (b.parent / "tap1_vi.srt").write_text("", encoding="utf-8")
            steps = st._steps_for(["giong"], "x.mp4", b, s)
        self.assertEqual(len(steps), 1)
        return steps[0].argv

    def test_mac_dinh_vieneu_ngoc_huyen(self):
        a = self._argv({"sanggiong": "80"})
        self.assertIn("--engine", a)
        self.assertEqual(a[a.index("--engine") + 1], "vieneu")
        self.assertEqual(a[a.index("--giong-vieneu") + 1], "Ngọc Huyền")
        self.assertNotIn("--voice", a)

    def test_omni_giu_voice(self):
        a = self._argv({"engine": "omni", "voice": "mau.wav", "giong_vieneu": "Mai Anh"})
        self.assertEqual(a[a.index("--engine") + 1], "omni")
        self.assertEqual(a[a.index("--voice") + 1], "mau.wav")
        self.assertEqual(a[a.index("--giong-vieneu") + 1], "Mai Anh")

    def test_nhan_buoc(self):
        self.assertIn("VieNeu", st.LABELS["giong"])


class TestServer(unittest.TestCase):
    def test_mac_dinh(self):
        self.assertEqual(sv.DEFAULTS["engine"], "vieneu")
        self.assertEqual(sv.DEFAULTS["giong_vieneu"], "Ngọc Huyền")

    def test_form(self):
        from starlette.datastructures import FormData
        s = sv._settings_from_form(FormData([("engine", "omni"), ("giong_vieneu", "Trúc Ly")]))
        self.assertEqual((s["engine"], s["giong_vieneu"]), ("omni", "Trúc Ly"))
        s = sv._settings_from_form(FormData([("engine", "x"), ("giong_vieneu", "?")]))
        self.assertEqual((s["engine"], s["giong_vieneu"]), ("vieneu", "Ngọc Huyền"))
        s = sv._settings_from_form(FormData([]))
        self.assertEqual((s["engine"], s["giong_vieneu"]), ("vieneu", "Ngọc Huyền"))

    def test_trang_chinh_va_nghe_thu(self):
        # Gọi thẳng handler (asyncio.run trong luồng chính) thay vì TestClient: TestClient chạy
        # app ở luồng khác, GC ở đó dọn biến Tk sót của các test GUI trước → Tcl_AsyncDelete
        # làm sập cả bộ test.
        import asyncio
        from starlette.requests import Request
        scope = {"type": "http", "method": "GET", "path": "/", "headers": [], "query_string": b"",
                 "app": sv.app, "router": sv.app.router, "scheme": "http", "server": ("127.0.0.1", 1)}
        with patch.object(sv, "load_settings", lambda: dict(sv.DEFAULTS)):
            r = asyncio.run(sv.index(Request(scope)))
        self.assertEqual(r.status_code, 200)
        h = r.body.decode("utf-8")
        self.assertIn('name="engine" value="vieneu" checked', h)
        self.assertIn('name="giong_vieneu"', h)
        self.assertIn('value="Ngọc Huyền" selected', h)
        self.assertEqual(asyncio.run(sv.nghe_vieneu(ten="lạ")).status_code, 404)
        with patch.object(sv, "VIENEU_NGHE_DIR", Path(tempfile.gettempdir()) / "khong_co_vieneu_x"):
            r = asyncio.run(sv.nghe_vieneu(ten="Ngọc Huyền"))
        self.assertEqual(r.status_code, 404)
        self.assertIn("Thử giọng", json.loads(r.body)["error"])


if __name__ == "__main__":
    unittest.main()
