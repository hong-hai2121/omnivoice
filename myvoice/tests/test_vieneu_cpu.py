# -*- coding: utf-8 -*-
"""VieNeu-TTS làm phương án tạo giọng thứ 2, chạy CPU ngay trong tiến trình (11/11/2026):
scripts/taogiong_vieneu.py (máy đọc), chế độ "vieneu" trong amain_taogiong_gui (nap_engine /
do_engine / _generate_chunk / run_tts), ô chọn ở web myvoice và engine bước ③ của myvideo.

KHÔNG nạp model thật: SDK vieneu và máy đọc đều là đồ giả. Thư mục ra là thư mục TẠM.
Chỉ GET trang (không POST route lưu nào — route lưu ghi đè web_settings.json thật)."""
import hashlib
import json
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import soundfile as sf
from starlette.datastructures import FormData

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "myvoice" / "scripts"
for p in (str(REPO), str(SCRIPTS), str(REPO / "myvideo")):
    if p not in sys.path:
        sys.path.insert(0, p)

import taogiong_vieneu as vn  # noqa: E402
import amain_taogiong_gui as gui  # noqa: E402
import taogiong_srt as ts  # noqa: E402  (bước ③ của myvideo)

import gc  # noqa: E402
gc.collect()
with patch.object(threading.Thread, "start", lambda self: None):   # không cho luồng nền của server chạy
    from myvideo.web import steps as st, server as sv  # noqa: E402
    from myvoice.web import core, server as mv_server  # noqa: E402

SR = 48_000
SAN_SANG = dict(co_kho=True, thieu=[], san_sang=True, mo_ta="ok")


def _cau(giay=5.0, hz=300, bien=0.2):
    """Một 'câu' giả: tiếng sin, 0,1 s im lặng hai mép như engine vẫn để."""
    t = np.arange(int(SR * giay)) / SR
    lang = np.zeros(int(0.1 * SR), dtype=np.float32)
    return np.concatenate([lang, (bien * np.sin(2 * np.pi * hz * t)).astype(np.float32), lang])


class _TtsGia:
    """Thế chỗ đối tượng Vieneu() của SDK."""
    tra = None                      # audio infer() trả về; None → 0,1 s tiếng

    def __init__(self, **kw):
        from huggingface_hub import constants as hf
        self.offline_luc_nap = bool(hf.HF_HUB_OFFLINE)       # cờ "chỉ dùng cache" lúc đang nạp
        self.kw, self.goi, self.dong = kw, [], False
        self.sample_rate, self.backend = SR, "onnx"

    def infer(self, text, **kw):
        self.goi.append((text, kw))
        return np.full(4800, 0.1, dtype=np.float32) if self.tra is None else self.tra

    def close(self):
        self.dong = True


class _MayGia(vn.MayDoc):
    """Máy đọc giả (vẫn là vn.MayDoc để do_engine nhận ra), không nạp gì."""

    def __init__(self):
        self.tts, self.sr, self.backend, self.t_nap = object(), SR, "onnx", 0.0
        self.doc_goi, self.da_tat = [], False

    def doc(self, text, voice=vn.GIONG_MAC_DINH):
        self.doc_goi.append((text, voice))
        return _cau()

    def tat(self):
        self.da_tat = True


def _sdk_gia():
    """Cho `from vieneu import Vieneu` trong MayDoc() lấy lớp giả."""
    m = types.ModuleType("vieneu")
    m.Vieneu = _TtsGia
    return patch.dict(sys.modules, {"vieneu": m})


# ── scripts/taogiong_vieneu.py ─────────────────────────────────────────────────
class TestModule(unittest.TestCase):
    def test_giong_mac_dinh_la_ngoc_huyen(self):
        self.assertEqual(vn.GIONG_MAC_DINH, "Ngọc Huyền")
        self.assertIn(vn.GIONG_MAC_DINH, vn.GIONG_DUNG_SAN)
        self.assertEqual(len(vn.GIONG_DUNG_SAN), len(set(vn.GIONG_DUNG_SAN)))

    def test_danh_sach_khop_file_cua_kho(self):
        f = vn.SRC / "vieneu" / "assets" / "voices_v3_turbo.json"
        if not f.is_file():
            self.skipTest("kho VieNeu-TTS không có trên đĩa")
        ten = tuple(json.loads(f.read_text(encoding="utf-8"))["presets"])
        self.assertEqual(vn.GIONG_DUNG_SAN, ten)

    def test_giong_hop_le(self):
        self.assertEqual(vn.giong_hop_le("Mai Anh"), "Mai Anh")
        self.assertEqual(vn.giong_hop_le("  Mai Anh "), "Mai Anh")
        for la in ("", None, "ngochuyen.mp3", "ngọc huyền"):
            self.assertEqual(vn.giong_hop_le(la), "Ngọc Huyền")

    def test_trang_thai_thieu_kho(self):
        with tempfile.TemporaryDirectory() as td, patch.object(vn, "SRC", Path(td)):
            tt = vn.trang_thai()
        self.assertFalse(tt["co_kho"])
        self.assertFalse(tt["san_sang"])
        self.assertIn("git clone", tt["mo_ta"])

    def test_trang_thai_thieu_goi(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "vieneu").mkdir()
            (Path(td) / "vieneu" / "__init__.py").write_text("", encoding="utf-8")
            that = vn.importlib.util.find_spec
            with patch.object(vn, "SRC", Path(td)), \
                    patch.object(vn.importlib.util, "find_spec",
                                 lambda m: None if m == "sea_g2p" else that(m)):
                tt = vn.trang_thai()
        self.assertTrue(tt["co_kho"])
        self.assertFalse(tt["san_sang"])
        self.assertEqual(tt["thieu"], ["sea-g2p==0.9.1"])
        self.assertIn("pip install sea-g2p==0.9.1", tt["mo_ta"])

    def test_import_module_khong_keo_gi_nang(self):
        """GUI / web import module này lúc mở: không được nạp torch, onnxruntime hay SDK."""
        ma = ("import sys; sys.path.insert(0, sys.argv[1]); import taogiong_vieneu; "
              "print([m for m in ('torch', 'onnxruntime', 'vieneu', 'transformers') if m in sys.modules])")
        r = subprocess.run([sys.executable, "-c", ma, str(SCRIPTS)], capture_output=True, text=True)
        self.assertEqual(r.stdout.strip(), "[]", r.stderr)


class TestMayDoc(unittest.TestCase):
    def _may(self):
        with _sdk_gia(), patch.object(vn, "trang_thai", return_value=SAN_SANG):
            return vn.MayDoc()

    def test_nap_bang_onnx_cpu(self):
        """Phải nói rõ backend onnx + device cpu — không để SDK tự dò CUDA rồi nạp bản GPU."""
        may = self._may()
        self.assertEqual(may.tts.kw, {"backend": "onnx", "device": "cpu"})
        self.assertEqual(may.sr, SR)
        self.assertEqual(len(may.tts.goi), 1)                 # câu làm nóng

    def test_uu_tien_cache_khong_hoi_mang(self):
        """Nạp bằng model đã có trong cache: cờ offline của huggingface_hub bật TRONG lúc nạp
        (không hỏi mạng, giọng không tự đổi theo repo) rồi trả lại như cũ."""
        from huggingface_hub import constants as hf
        with patch.object(hf, "HF_HUB_OFFLINE", False):
            may = self._may()
            self.assertFalse(hf.HF_HUB_OFFLINE)
        self.assertTrue(may.tu_cache)
        self.assertTrue(may.tts.offline_luc_nap)

    def test_cache_thieu_thi_tai_ve(self):
        """Lần nạp đầu trên máy (cache chưa có model): bản chỉ-cache lỗi → nạp lại cho tải về."""
        from huggingface_hub import constants as hf

        class _ThieuCache(_TtsGia):
            def __init__(self, **kw):
                if hf.HF_HUB_OFFLINE:
                    raise OSError("chưa có trong cache")
                super().__init__(**kw)

        m = types.ModuleType("vieneu")
        m.Vieneu = _ThieuCache
        with patch.dict(sys.modules, {"vieneu": m}), \
                patch.object(vn, "trang_thai", return_value=SAN_SANG), \
                patch.object(hf, "HF_HUB_OFFLINE", False):
            may = vn.MayDoc()
            self.assertFalse(hf.HF_HUB_OFFLINE)
        self.assertFalse(may.tu_cache)
        self.assertFalse(may.tts.offline_luc_nap)
        self.assertEqual(may.tts.kw, {"backend": "onnx", "device": "cpu"})

    def test_chua_san_sang_thi_bao_ro(self):
        chua = dict(co_kho=False, thieu=[], san_sang=False, mo_ta="thiếu kho X")
        with patch.object(vn, "trang_thai", return_value=chua):
            with self.assertRaises(RuntimeError) as cm:
                vn.MayDoc()
        self.assertIn("thiếu kho X", str(cm.exception))

    def test_doc_mot_cau(self):
        may = self._may()
        a = may.doc("câu   một\n", "Mai Anh")
        self.assertEqual(a.dtype, np.float32)
        text, kw = may.tts.goi[-1]
        self.assertEqual(text, "câu một")
        self.assertEqual(kw["voice"], "Mai Anh")
        self.assertEqual((kw["temperature"], kw["top_k"]), (vn.NHIET_DO, vn.TOP_K))
        self.assertFalse(kw["apply_watermark"])

    def test_giong_la_thi_ngoc_huyen(self):
        may = self._may()
        may.doc("xin chào", "giọng không có")
        self.assertEqual(may.tts.goi[-1][1]["voice"], "Ngọc Huyền")

    def test_cau_rong_thi_chen_lang(self):
        may = self._may()
        may.tts.tra = np.zeros(0, dtype=np.float32)
        with patch.object(vn.logging, "warning") as canh_bao:
            a = may.doc("…")
        self.assertEqual(len(a), int(vn.LANG_KHI_RONG * SR))
        self.assertTrue(canh_bao.called)

    def test_tat_roi_thi_khong_doc_duoc(self):
        may = self._may()
        tts = may.tts
        may.tat()
        may.tat()                                             # gọi lại không lỗi
        self.assertTrue(tts.dong)
        with self.assertRaises(RuntimeError):
            may.doc("xin chào")


# ── amain_taogiong_gui: chế độ "vieneu" ────────────────────────────────────────
class TestCheDo(unittest.TestCase):
    def test_vieneu_la_phuong_an_thu_hai_mac_dinh_van_clone(self):
        self.assertEqual(gui.MODES, ("clone", "vieneu", "design", "default"))
        self.assertEqual(gui.OPTS_DEFAULTS["mode"], "clone")
        self.assertEqual(gui.OPTS_DEFAULTS["vieneu_voice"], "Ngọc Huyền")

    def test_doc_cai_dat_da_luu(self):
        self.assertEqual(gui.che_do_da_luu({"mode": "vieneu"}), "vieneu")
        self.assertEqual(gui.che_do_da_luu({"mode": "la"}), "clone")
        self.assertEqual(gui.che_do_da_luu({}), "clone")
        self.assertEqual(gui.giong_vieneu_da_luu({"vieneu_voice": "Mai Anh"}), "Mai Anh")
        self.assertEqual(gui.giong_vieneu_da_luu({}), "Ngọc Huyền")

    def test_nap_engine_vieneu_khong_nap_omnivoice(self):
        with patch.object(gui.vn, "MayDoc", _MayGia), \
                patch.object(gui, "load_omnivoice") as omni, patch.object(gui.logging, "info"):
            may, sr = gui.nap_engine("vieneu", "cuda")
        self.assertIsInstance(may, _MayGia)
        self.assertEqual(sr, SR)
        omni.assert_not_called()

    def test_nap_engine_con_lai_la_omnivoice(self):
        for mode in ("clone", "design", "default"):
            with patch.object(gui, "load_omnivoice", return_value=("omni", 24000)) as omni, \
                    patch.object(gui.vn, "MayDoc") as may:
                self.assertEqual(gui.nap_engine(mode, "cuda"), ("omni", 24000))
            omni.assert_called_once_with("cuda")
            may.assert_not_called()

    def test_do_engine(self):
        may = _MayGia()
        with patch.object(gui, "_do_omnivoice") as omni, patch.object(gui.logging, "info"):
            self.assertIsNone(gui.do_engine(may, "thử"))
        self.assertTrue(may.da_tat)
        omni.assert_not_called()
        with patch.object(gui, "_do_omnivoice", return_value=None) as omni:
            gui.do_engine("omni", "thử")
        omni.assert_called_once_with("omni", "thử")

    def test_generate_chunk(self):
        may = _MayGia()
        kq = gui._generate_chunk(may, "vieneu", "Mai Anh", "câu  một.\n", dur_scale=1.06, sang_giong=80)
        self.assertEqual(may.doc_goi, [("câu một.", "Mai Anh")])
        self.assertEqual(len(kq), 1)                          # cùng dạng result[0] của OmniVoice
        self.assertEqual(kq[0].dtype, np.float32)


class _V:
    def __init__(self, v):
        self.v = v

    def set(self, v):
        self.v = v

    def get(self):
        return self.v


class TestRunTts(unittest.TestCase):
    """Cả bước tạo giọng ở chế độ vieneu với máy đọc giả: ra wav 48 kHz, không đụng CUDA
    trong lúc sinh câu, mức 🔆 không vào chữ ký."""

    def test_chay_tron_buoc(self):
        import torch
        td = Path(tempfile.mkdtemp(prefix="vieneu_cpu_"))
        self.addCleanup(lambda: __import__("shutil").rmtree(td, ignore_errors=True))
        output = td / "output.wav"
        chunks = [f"câu số {i}." for i in range(gui.VRAM_CLEAN_EVERY + 2)]   # qua mốc dọn VRAM
        ev = threading.Event()
        ev.set()
        stub = gui._NullWidget()
        # Bỏ bước ASR kiểm mất chữ: chặn import đúng MỘT module (như test_nghe_thu).
        cu = sys.modules.get("taogiong_kiemtra_matchu", self)
        sys.modules["taogiong_kiemtra_matchu"] = None
        self.addCleanup(lambda: sys.modules.pop("taogiong_kiemtra_matchu", None) if cu is self
                        else sys.modules.__setitem__("taogiong_kiemtra_matchu", cu))
        cac_may = []

        class _MayGhi(_MayGia):           # phải là LỚP: do_engine dùng isinstance(model, vn.MayDoc)
            def __init__(self):
                super().__init__()
                cac_may.append(self)

        with patch.object(gui.vn, "MayDoc", _MayGhi), \
                patch.multiple(gui, _tra_vram=MagicMock(), _play_done_sound=MagicMock(),
                               _apply_voice_fx_file=MagicMock(), load_omnivoice=MagicMock()), \
                patch.object(torch.cuda, "empty_cache") as don_vram, \
                patch.object(torch.cuda, "mem_get_info") as do_vram, \
                patch.object(gui.logging, "info"), patch.object(gui.logging, "warning"):
            ok = gui.run_tts("vieneu", "Ngọc Huyền", chunks, str(output), _V(0), _V(""),
                             stub, stub, stub, ev, fx={"sang_giong": 80})
            gui.load_omnivoice.assert_not_called()
        self.assertTrue(ok)
        self.assertEqual(len(cac_may), 1)                     # nạp đúng một lần
        may = cac_may[0]
        self.assertEqual(sf.info(str(output)).samplerate, SR)
        self.assertEqual([t for t, _g in may.doc_goi], chunks)
        self.assertEqual({g for _t, g in may.doc_goi}, {"Ngọc Huyền"})
        self.assertTrue(may.da_tat)
        don_vram.assert_not_called()                          # không dọn VRAM giữa chừng
        do_vram.assert_not_called()                           # không đánh thức card lúc sinh câu
        # Chữ ký KHÔNG có "sang80": VieNeu không dựng prompt, đổi 🔆 không sinh lại câu.
        mong = hashlib.sha1("|".join(["vieneu", "Ngọc Huyền", f"step{gui.NUM_STEP}",
                                      f"fade{gui.FADE_OUT_SEC}", *chunks]).encode("utf-8")).hexdigest()
        sig = (gui.chunks_dir_for(output) / "_signature.txt").read_text(encoding="utf-8").strip()
        self.assertEqual(sig, mong)


# ── web myvoice ────────────────────────────────────────────────────────────────
class TestWebMyvoice(unittest.TestCase):
    def _settings(self, web, tt=SAN_SANG):
        with patch.object(core, "load_web_settings", return_value=web), \
                patch.object(core, "load_options", return_value={}), \
                patch.object(core.gui.vn, "trang_thai", return_value=tt):
            return core.tts_settings()

    def test_mac_dinh_van_la_clone_ngoc_huyen(self):
        self.assertEqual(core.WEB_DEFAULTS["mode"], "clone")
        self.assertEqual(core.WEB_DEFAULTS["vieneu_voice"], "Ngọc Huyền")

    def test_tts_settings_vieneu(self):
        s, loi = self._settings({"mode": "vieneu", "vieneu_voice": "Mai Anh"})
        self.assertEqual(loi, "")
        self.assertEqual((s["mode"], s["voice_param"]), ("vieneu", "Mai Anh"))
        s, _ = self._settings({"mode": "vieneu", "vieneu_voice": "không có"})
        self.assertEqual(s["voice_param"], "Ngọc Huyền")

    def test_chua_san_sang_thi_dung_khong_doi_sang_clone(self):
        chua = dict(co_kho=True, thieu=["sea-g2p==0.9.1"], san_sang=False, mo_ta="thiếu gói X")
        s, loi = self._settings({"mode": "vieneu"}, chua)
        self.assertIsNone(s)
        self.assertIn("thiếu gói X", loi)

    def test_trang_co_o_chon(self):
        from fastapi.testclient import TestClient
        with patch.object(mv_server, "_vram", return_value={}):
            c = TestClient(mv_server.app)
            c.cookies.set(mv_server.COOKIE, mv_server.TOKEN)
            html = c.get("/").text
        self.assertIn('name="mode" value="vieneu"', html)
        self.assertIn('<select name="vieneu_voice">', html)
        for ten in vn.GIONG_DUNG_SAN:
            self.assertIn(f'<option value="{ten}"', html)
        # thứ tự hàng chế độ: clone → vieneu → design → default
        vi_tri = [html.index(f'name="mode" value="{m}"') for m in gui.MODES]
        self.assertEqual(vi_tri, sorted(vi_tri))


# ── myvideo bước ③ ─────────────────────────────────────────────────────────────
class TestMyvideo(unittest.TestCase):
    def _argv(self, s):
        with tempfile.TemporaryDirectory() as td:
            b = Path(td) / "tap1"
            (b.parent / "tap1_vi.srt").write_text("", encoding="utf-8")
            steps = st._steps_for(["giong"], "x.mp4", b, s)
        self.assertEqual(len(steps), 1)
        return steps[0]

    def test_mac_dinh_la_omnivoice(self):
        self.assertEqual(sv.DEFAULTS["engine"], "omni")
        self.assertEqual(sv.DEFAULTS["giong_vieneu"], "Ngọc Huyền")
        buoc = self._argv({"voice": "mau.wav"})
        self.assertNotIn("--engine", buoc.argv)               # lệnh OmniVoice y như trước
        self.assertIn("OmniVoice", buoc.label)

    def test_chon_vieneu_thi_truyen_engine(self):
        buoc = self._argv({"engine": "vieneu", "giong_vieneu": "Mai Anh", "voice": "mau.wav"})
        a = buoc.argv
        self.assertEqual(a[a.index("--engine") + 1], "vieneu")
        self.assertEqual(a[a.index("--giong-vieneu") + 1], "Mai Anh")
        self.assertEqual(a[a.index("--voice") + 1], "mau.wav")   # đổi về omni là có giọng mẫu
        self.assertIn("VieNeu", buoc.label)
        a = self._argv({"engine": "vieneu"}).argv
        self.assertEqual(a[a.index("--giong-vieneu") + 1], "Ngọc Huyền")

    def test_doc_form(self):
        s = sv._settings_from_form(FormData([("engine", "vieneu"), ("giong_vieneu", "Mai Anh")]))
        self.assertEqual((s["engine"], s["giong_vieneu"]), ("vieneu", "Mai Anh"))
        s = sv._settings_from_form(FormData([]))              # trang cũ còn mở, chưa có ô
        self.assertEqual((s["engine"], s["giong_vieneu"]), ("omni", "Ngọc Huyền"))
        s = sv._settings_from_form(FormData([("engine", "la"), ("giong_vieneu", "la")]))
        self.assertEqual((s["engine"], s["giong_vieneu"]), ("omni", "Ngọc Huyền"))

    def test_giong_vieneu(self):
        g = ts.giong_vieneu("Mai Anh")
        self.assertEqual((g.mode, g.voice_param, g.id), ("vieneu", "Mai Anh", "vieneu|Mai Anh"))
        self.assertFalse(g.clone)
        with patch("builtins.print"):
            self.assertEqual(ts.giong_vieneu("không có").ten, "Ngọc Huyền")
        self.assertEqual(ts.giong_vieneu("").ten, "Ngọc Huyền")

    def test_generate_all_bang_vieneu(self):
        may = _MayGia()
        cues = [((0, 1_000_000), "câu một."), ((1_000_000, 2_000_000), "câu hai.")]
        with tempfile.TemporaryDirectory() as td, \
                patch.object(ts, "nap_engine", return_value=(may, SR)) as nap, \
                patch("builtins.print"):
            tts_dir = Path(td) / "tap1_vi_tts"
            files, model, sr = ts.generate_all(cues, ts.giong_vieneu("Ngọc Huyền"), tts_dir, sang=80)
            nap.assert_called_once_with("vieneu")
            self.assertIs(model, may)
            self.assertEqual(sr, SR)
            self.assertEqual(len(may.doc_goi), 2)
            self.assertEqual({g for _t, g in may.doc_goi}, {"Ngọc Huyền"})
            for f in files:
                self.assertEqual(sf.info(str(f)).samplerate, SR)
            so = json.loads((tts_dir / "_vanban.json").read_text(encoding="utf-8"))
        self.assertEqual(so["giong"], "vieneu|Ngọc Huyền")
        self.assertEqual(so["sang"], 0)                       # VieNeu không EQ prompt

    def test_trang_co_o_chon(self):
        src = (REPO / "myvideo" / "web" / "templates" / "index.html").read_text(encoding="utf-8")
        for can in ('name="engine" value="omni"', 'name="engine" value="vieneu"',
                    'name="giong_vieneu"', 'id="khoiVieneu"', "veEngine"):
            self.assertIn(can, src)
        # OmniVoice đứng trước (mặc định), VieNeu là phương án thứ 2.
        self.assertLess(src.index('name="engine" value="omni"'), src.index('name="engine" value="vieneu"'))


if __name__ == "__main__":
    unittest.main()
