# -*- coding: utf-8 -*-
"""Kho giọng mẫu gom vào voice/giong_mau/ (04/11/2026): bài thật (amain), web (core), app
Thử giọng (voice/thu_giong.py) và myvideo (VOICE_DIRS[0]) phải cùng trỏ một chỗ; voice/
không còn wav/mp3/.pt nằm ngoài. Không nạp model."""
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

    def test_ket_qua_thu_khong_nam_trong_giong_mau(self):
        self.assertEqual(thu_giong.OUT_DIR, KHO.parent / "_thu_giong")
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


if __name__ == "__main__":
    unittest.main()
