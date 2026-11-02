# -*- coding: utf-8 -*-
"""voice/thu_giong.py — hàng nút 🎧 Nghe (02/11/2026): 🎤 giọng mẫu gốc, ▶ giọng clone,
⇄ mẫu → clone. Không nạp model; phần Tk chỉ dựng cửa sổ ẩn (withdraw) và bỏ qua
khi máy không có màn hình. winsound được chặn để test không phát tiếng thật."""
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import numpy as np
import soundfile as sf

from myvoice.web import core   # vá sys.path (scripts/) + import amain_taogiong_gui một lần

gui = core.gui
_VOICE_DIR = Path(__file__).resolve().parents[1] / "voice"
if str(_VOICE_DIR) not in sys.path:
    sys.path.insert(0, str(_VOICE_DIR))
import thu_giong  # noqa: E402


class MauWavFileTests(unittest.TestCase):
    def test_ten_cache_giu_duoi_goc(self):
        """'hà chi.mp3' → '_giongmau/hà chi.mp3.wav' — cùng kiểu đặt tên .prompt.pt cạnh mẫu."""
        self.assertEqual(thu_giong.mau_wav_file("hà chi.mp3"),
                         thu_giong.MAU_DIR / "hà chi.mp3.wav")

    def test_mp3_va_wav_cung_ten_khong_de_nhau(self):
        self.assertNotEqual(thu_giong.mau_wav_file("hà chi.mp3"),
                            thu_giong.mau_wav_file("hà chi.wav"))

    def test_thu_muc_cache_rieng(self):
        self.assertEqual(thu_giong.MAU_DIR.parent, thu_giong.OUT_DIR)
        self.assertNotEqual(thu_giong.MAU_DIR, thu_giong.SPEED_DIR)


def _mo_tk():
    import tkinter as tk
    try:
        root = tk.Tk()
    except tk.TclError as e:          # máy không có màn hình
        raise unittest.SkipTest(f"không mở được Tk: {e}")
    root.withdraw()
    return root


class AppNgheTests(unittest.TestCase):
    """Dựng App thật (ẩn) để kiểm hàng nút + luồng phát, không nạp model."""

    def setUp(self):
        self.root = _mo_tk()
        self.addCleanup(self.root.destroy)
        # Không ghi vào taogiong_options.json thật khi 🔗 đồng bộ bật.
        p = patch.object(gui, "save_opt_settings", lambda *_a, **_k: None)
        p.start()
        self.addCleanup(p.stop)
        self.app = thu_giong.App(self.root)

    def test_co_du_nut_nghe(self):
        a = self.app
        for b in (a.btn_mau, a.btn_play, a.btn_ab, a.btn_stop):
            self.assertTrue(b.winfo_exists())
        self.assertIn("mẫu", a.btn_mau.cget("text"))
        self.assertIn("clone", a.btn_play.cget("text"))
        self.assertIn("→", a.btn_ab.cget("text"))

    def test_busy_khoa_clone_ab_nhung_khong_khoa_mau(self):
        a = self.app
        a._set_busy(True)
        self.assertEqual(str(a.btn_play.cget("state")), "disabled")
        self.assertEqual(str(a.btn_ab.cget("state")), "disabled")
        self.assertEqual(str(a.btn_mau.cget("state")), "normal")
        a._set_busy(False)
        self.assertEqual(str(a.btn_ab.cget("state")), "normal")

    def test_keo_thanh_khong_phat_lai_khi_dang_nghe_mau(self):
        a = self.app
        a._play_file = MagicMock()
        a._last_src = Path(__file__)
        a._playing, a._play_until = True, time.monotonic() + 30
        a._last_raw = True
        a._replay_if_playing()
        a._play_file.assert_not_called()
        a._last_raw = False
        a._replay_if_playing()
        a._play_file.assert_called_once_with(Path(__file__))

    def test_dung_huy_luot_clone_dang_hen(self):
        a = self.app
        a._play_file = MagicMock()
        with patch("winsound.PlaySound"):
            token = a._ab_token + 1
            a._ab_token = token
            a._stop_play()                       # ⏹ → token đổi
        a._ab_clone(token, Path("x.wav"))        # lượt hẹn cũ → bỏ
        a._play_file.assert_not_called()
        a._ab_clone(a._ab_token, Path("x.wav"))  # token hiện tại → phát
        a._play_file.assert_called_once_with(Path("x.wav"))

    def test_ab_hen_phat_clone_sau_khi_mau_het(self):
        a = self.app
        clone = Path("clone.wav")
        a._selected_voice = lambda: "giong.mp3"
        a._clone_file = MagicMock(return_value=clone)
        a._play_sample = MagicMock(return_value=2.0)
        a._play_file = MagicMock()
        hen = {}
        a.root.after = lambda ms, cb: hen.update(ms=ms, cb=cb)
        a._on_play_ab()
        a._play_sample.assert_called_once_with("giong.mp3")
        self.assertEqual(hen["ms"], 2600)        # 2,0 s mẫu + 0,6 s nghỉ
        hen["cb"]()
        a._play_file.assert_called_once_with(clone)

    def test_ab_khong_phat_khi_chua_co_clone(self):
        a = self.app
        a._selected_voice = lambda: "giong.mp3"
        a._clone_file = MagicMock(return_value=None)
        a._play_sample = MagicMock()
        a._on_play_ab()
        a._play_sample.assert_not_called()

    def test_phat_mau_thieu_file_tra_0(self):
        a = self.app
        with patch.object(thu_giong.messagebox, "showwarning") as w:
            self.assertEqual(a._play_sample("__khong_co_giong_nay__.mp3"), 0.0)
        w.assert_called_once()

    def test_phat_mau_la_nguyen_ban_va_danh_dau_raw(self):
        """_play_sample: đổi sang wav qua _wav_giong_mau rồi phát, _last_raw=True,
        không gọi _render_file (không áp thanh chỉnh)."""
        a = self.app
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        src = Path(tmp.name) / "giong_test.mp3"
        src.write_bytes(b"\0" * 16)              # chỉ cần tồn tại; đổi wav đã mock
        wav = Path("mau.wav")
        a._wav_giong_mau = MagicMock(return_value=wav)
        a._render_file = MagicMock()
        a._play_wav = MagicMock(return_value=3.5)
        with patch.object(thu_giong, "VOICE_DIR", Path(tmp.name)):
            d = a._play_sample("giong_test.mp3")
        self.assertEqual(d, 3.5)
        self.assertTrue(a._last_raw)
        self.assertEqual(a._last_src, src)
        a._wav_giong_mau.assert_called_once_with(src)
        a._render_file.assert_not_called()
        a._play_wav.assert_called_once()
        self.assertEqual(a._play_wav.call_args.args[0], wav)
        self.assertIn("MẪU", a._play_wav.call_args.args[1](3.5))


@unittest.skipUnless(shutil.which("ffmpeg"), "cần ffmpeg")
class WavGiongMauTests(unittest.TestCase):
    """_wav_giong_mau: đổi mẫu (wav float) sang wav 16-bit, cache theo mtime."""

    def setUp(self):
        self.root = _mo_tk()
        self.addCleanup(self.root.destroy)
        p = patch.object(gui, "save_opt_settings", lambda *_a, **_k: None)
        p.start()
        self.addCleanup(p.stop)
        self.app = thu_giong.App(self.root)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        p2 = patch.object(thu_giong, "MAU_DIR", self.tmp / "_giongmau")
        p2.start()
        self.addCleanup(p2.stop)
        self.src = self.tmp / "mau.wav"
        sr = 24000
        t = np.arange(int(0.3 * sr)) / sr
        sf.write(str(self.src), (0.3 * np.sin(2 * np.pi * 220 * t)).astype("float32"), sr,
                 subtype="FLOAT")

    def test_doi_sang_16bit_va_dung_cache(self):
        dst = self.app._wav_giong_mau(self.src)
        self.assertEqual(dst, thu_giong.MAU_DIR / "mau.wav.wav")
        self.assertTrue(dst.exists())
        self.assertEqual(sf.info(str(dst)).subtype, "PCM_16")
        with patch.object(thu_giong.subprocess, "run") as run:
            self.assertEqual(self.app._wav_giong_mau(self.src), dst)
        run.assert_not_called()                  # còn mới → không chạy ffmpeg lại
        # mẫu đổi (mtime mới hơn) → đổi lại
        os.utime(self.src, None)
        time.sleep(0.05)
        os.utime(self.src, (time.time() + 5, time.time() + 5))
        with patch.object(thu_giong.subprocess, "run", wraps=thu_giong.subprocess.run) as run:
            self.app._wav_giong_mau(self.src)
        run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
