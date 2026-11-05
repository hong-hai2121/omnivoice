# -*- coding: utf-8 -*-
"""Kho giọng mẫu gom vào voice/giong_mau/ (04/11/2026): bài thật (amain), web (core), app
Thử giọng (voice/thu_giong.py) và myvideo (VOICE_DIRS[0]) phải cùng trỏ một chỗ; voice/
không còn wav/mp3/.pt nằm ngoài. Tab 🗣️ VieNeu-TTS của app Thử giọng liệt kê ĐỦ nhóm
chức năng (VIENEU_CHUC_NANG) và vẽ hết ra ô chữ. Không nạp model, Tk mở ẩn."""
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

REPO = Path(__file__).resolve().parents[2]            # OmniVoice/
KHO = REPO / "myvoice" / "voice" / "giong_mau"


class KhoGiongMauTests(unittest.TestCase):
    def test_bai_that_web_thu_giong_cung_mot_kho(self):
        self.assertEqual(gui.VOICE_DIR, KHO)
        self.assertEqual(core.VOICE_DIR, KHO)
        self.assertEqual(thu_giong.VOICE_DIR, KHO)

    def test_ket_qua_thu_va_kho_vieneu_khong_nam_trong_giong_mau(self):
        self.assertEqual(thu_giong.OUT_DIR, KHO.parent / "_thu_giong")
        self.assertEqual(thu_giong.VIENEU_DIR, KHO.parent / "VieNeu-TTS")
        self.assertEqual(thu_giong.HERE_DIR, KHO.parent)

    def test_voice_khong_con_giong_mau_nam_ngoai(self):
        """voice/ chỉ còn code + thư mục con; mọi wav/mp3/.pt phải ở giong_mau/."""
        duoi = thu_giong.AUDIO_EXTS | {".pt"}
        ngoai = sorted(p.name for p in KHO.parent.iterdir()
                       if p.is_file() and p.suffix.lower() in duoi)
        self.assertEqual(ngoai, [])

    def test_myvideo_tro_cung_kho(self):
        """steps.py (ô chọn giọng bước ③) và taogiong_srt.py (CLI) tìm giọng ở giong_mau trước.
        Đọc chữ nguồn thay vì import: taogiong_srt kéo cả torch/omnivoice."""
        for f in ("myvideo/web/steps.py", "myvideo/taogiong_srt.py"):
            src = (REPO / f).read_text(encoding="utf-8")
            self.assertIn('VOICE_DIRS = (REPO_ROOT / "myvoice" / "voice" / "giong_mau",', src, f)

    def test_list_voices_chi_lay_audio_bo_qua_pt_va_thu_muc(self):
        with tempfile.TemporaryDirectory() as d:
            kho = Path(d)
            (kho / "a.wav").write_bytes(b"\0")
            (kho / "a.wav.prompt.pt").write_bytes(b"\0")
            (kho / "b.mp3").write_bytes(b"\0")
            (kho / "thu_muc_con").mkdir()
            with patch.object(thu_giong, "VOICE_DIR", kho):
                self.assertEqual(thu_giong.list_voices(), ["a.wav", "b.mp3"])


class DanhMucVieNeuTests(unittest.TestCase):
    """Bảng VIENEU_CHUC_NANG phủ đủ các mảng VieNeu-TTS có (theo README.vi.md 3.8.3)."""

    def test_du_cac_mang_chuc_nang(self):
        ten = " | ".join(t for t, _, _ in thu_giong.VIENEU_CHUC_NANG)
        for tu in ("Mô hình", "dựng sẵn", "Clone", "Đọc truyện", "Hội thoại", "SRT",
                   "cảm xúc", "lô", "Streaming", "OpenAI", "Docker", "LoRA", "Gradio",
                   "Cài đặt", "Không có"):
            self.assertIn(tu, ten, tu)
        self.assertGreaterEqual(len(thu_giong.VIENEU_CHUC_NANG), 15)

    def test_moi_nhom_co_tom_tat_va_chi_tiet(self):
        for ten, tom, dong in thu_giong.VIENEU_CHUC_NANG:
            self.assertTrue(ten.strip() and tom.strip(), ten)
            self.assertTrue(dong, ten)
            self.assertTrue(all(d.strip() for d in dong), ten)

    def test_chi_tiet_nhac_den_dieu_quan_trong(self):
        """Những con số / tên dễ hỏi lại phải có trong bảng: 48 kHz, 25 giọng, clip 3–8 s,
        tag cảm xúc, endpoint OpenAI, lệnh cài, tên giọng mặc định."""
        tat_ca = "\n".join(d for _, tom, dong in thu_giong.VIENEU_CHUC_NANG for d in [tom, *dong])
        for tu in ("48 kHz", "25 giọng", "3–8", "[cười]", "/v1/audio/speech", "uv sync",
                   "Hải Đăng", "infer_stream", "add_voice", "train_lora.py", "vieneu.io"):
            self.assertIn(tu, tat_ca, tu)

    def test_trang_thai_khong_import_vieneu(self):
        tt = thu_giong.vieneu_trang_thai()
        self.assertEqual(set(tt), {"co_kho", "da_cai", "gpu", "phien_ban", "mo_ta"})
        self.assertTrue(tt["mo_ta"])
        self.assertNotIn("vieneu", sys.modules)        # chỉ dò find_spec, không nạp gói


def _mo_tk():
    import tkinter as tk
    try:
        root = tk.Tk()
    except tk.TclError as e:          # máy không có màn hình
        raise unittest.SkipTest(f"không mở được Tk: {e}")
    root.withdraw()
    return root


class TabVieNeuTests(unittest.TestCase):
    """App thật mở ẩn (không nạp model): trang 🗣️ có đủ nhóm trong ô chữ, chỉ đọc."""

    def setUp(self):
        self.root = _mo_tk()
        self.addCleanup(self.root.destroy)
        p = patch.object(gui, "save_opt_settings", lambda d: None)   # không ghi taogiong_options.json
        p.start()
        self.addCleanup(p.stop)
        self.app = thu_giong.App(self.root)

    def test_trang_vieneu_ve_du_nhom(self):
        a = self.app
        self.assertIn("vieneu", a._pages)
        chu = a._vieneu_text.get("1.0", "end")
        for i, (ten, _tom, dong) in enumerate(thu_giong.VIENEU_CHUC_NANG, 1):
            self.assertIn(f"{i}. {ten}", chu)
            for d in dong:
                self.assertIn(d, chu)
        self.assertIn(thu_giong.VIENEU_GHI_CHU, chu)
        self.assertEqual(a._vieneu_text.cget("state"), "disabled")

    def test_nam_tab_con_va_nut_dung_thu(self):
        a = self.app
        self.assertEqual(len(a.vn_nb.tabs()), 5)
        for b in (a.vn_btn_cai_gpu, a.vn_btn_cai_cpu, a.vn_btn_bat, a.vn_btn_tat, a.vn_btn_web,
                  a.vn_btn_doc, a.vn_btn_dang_ky, a.vn_btn_ht, a.vn_btn_srt):
            self.assertTrue(b.winfo_exists())
        self.assertEqual(a.vn_btn_tat.cget("state").string, "disabled")   # chưa bật server
        self.assertFalse(a.vn_api.dang_chay)
        a._vn_tat_het()                                                     # không gì chạy → không lỗi

    def test_quet_vai_tao_o_chon_giong_tung_vai(self):
        a = self.app
        a.vn_voices = [dict(id="Mai Anh", name="Mai Anh", description=""),
                       dict(id="Hải Đăng", name="Hải Đăng", description="")]
        a.vn_txt_ht.delete("1.0", "end")
        a.vn_txt_ht.insert("1.0", "An: xin chào\nBình: chào An\nAn: khoẻ không?")
        a._vn_quet_vai()
        self.assertEqual(list(a.vn_vai_cb), ["An", "Bình"])
        self.assertEqual([cb.get() for cb in a.vn_vai_cb.values()], ["Mai Anh", "Hải Đăng"])

    def test_chen_tag_cam_xuc_vao_van_ban(self):
        a = self.app
        a.vn_txt.delete("1.0", "end")
        a.vn_txt.insert("1.0", "Nghe hay quá")
        a.vn_txt.mark_set("insert", "end-1c")
        a._vn_chen_tag("[cười]")
        self.assertEqual(a.vn_txt.get("1.0", "end").strip(), "Nghe hay quá [cười]")

    def test_chon_tab_vieneu_roi_quay_lai(self):
        a = self.app
        with patch.object(thu_giong, "save_settings") as luu:
            a._chon_tab("vieneu")
            self.assertEqual(a._tab, "vieneu")
            luu.assert_called_with(tab="vieneu")
            a._chon_tab("omni")
            self.assertEqual(a._tab, "omni")


if __name__ == "__main__":
    unittest.main()
