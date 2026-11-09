# -*- coding: utf-8 -*-
"""🔉 Chuẩn âm thành tuỳ chọn, mặc định TẮT (05/11/2026): _balance_chunk_levels không neo mức
khi moc=False; cài đặt/gói web myvoice; myvideo: --chuan-am bước ③, --tts-lufs 0 bước ④,
LOUD = anull khi tts_lufs 0."""
import gc
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

REPO = Path(__file__).resolve().parents[2]
for p in (REPO, REPO / "myvideo"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
from myvoice.web import core  # noqa: E402  (vá sys.path scripts/ + import amain_taogiong_gui)
import amain_taogiong_gui as tts  # noqa: E402

gc.collect()
with patch.object(threading.Thread, "start", lambda self: None):   # không cho luồng nền myvideo chạy
    from myvideo.web import steps as st, server as sv  # noqa: E402


def _tone(db, sr=24_000, giay=0.5):
    a = 10 ** (db / 20) * np.sqrt(2) * np.sin(2 * np.pi * 220 * np.arange(int(sr * giay)) / sr)
    return a.astype(np.float32)


def _rms_db(a):
    return 20 * np.log10(np.sqrt(np.mean(a.astype("float64") ** 2)))


class TestCanMuc(unittest.TestCase):
    def test_mac_dinh_tat(self):
        self.assertIs(tts.OPTS_DEFAULTS["chuan_am"], False)
        with patch.object(core, "load_options", lambda: dict(tts.OPTS_DEFAULTS)), \
                patch.object(core, "load_web_settings", lambda: dict(core.WEB_DEFAULTS)):
            ts_, loi = core.tts_settings()
        self.assertEqual(loi, "")
        self.assertIs(ts_["chuan_am"], False)
        self.assertIn("chuan_am", tts.run_tts.__code__.co_varnames)

    def test_khong_neo_muc_khi_tat(self):
        parts = [_tone(-30), _tone(-31), _tone(-29)]       # giọng nhỏ (~ -30 dBFS)
        ra = tts._balance_chunk_levels(parts, 24_000, moc=False)
        # cân tương đối: ba đoạn về cùng mức quanh trung vị (-30), KHÔNG kéo lên -18
        muc = [_rms_db(p) for p in ra]
        self.assertLess(max(muc) - min(muc), 0.2)
        self.assertAlmostEqual(float(np.median(muc)), -30.0, delta=0.3)

    def test_neo_muc_khi_bat(self):
        parts = [_tone(-30), _tone(-31), _tone(-29)]
        ra = tts._balance_chunk_levels(parts, 24_000, moc=True)
        self.assertAlmostEqual(float(np.median([_rms_db(p) for p in ra])), tts.SPEECH_RMS_DBFS, delta=0.5)


class TestMyvideo(unittest.TestCase):
    def _steps(self, keys, s):
        with tempfile.TemporaryDirectory() as td:
            b = Path(td) / "tap1"
            for suf in ("_vi.srt", "_vi_audio.wav", ".mp4", "_vi_sapxep.srt"):
                (b.parent / ("tap1" + suf)).write_text("", encoding="utf-8")
            return {x.label[:1]: x.argv for x in st._steps_for(keys, "x.mp4", b, s)}

    def test_mac_dinh_tat_buoc_3_va_4(self):
        self.assertIs(sv.DEFAULTS["chuanam"], False)
        a = self._steps(["giong"], {})["③"]
        self.assertNotIn("--chuan-am", a)
        a = self._steps(["giong"], {"chuanam": True})["③"]
        self.assertIn("--chuan-am", a)

    def test_form(self):
        from starlette.datastructures import FormData
        self.assertIs(sv._settings_from_form(FormData([]))["chuanam"], False)
        self.assertIs(sv._settings_from_form(FormData([("chuanam", "on")]))["chuanam"], True)

    def test_buoc_4_tts_lufs(self):
        import video_gansub_cung as vg  # noqa: F401  (chỉ cần import được sau khi vá)
        argv = self._steps(["gan"], {}).get("④")
        if argv is None:
            self.skipTest("bước ④ cần điều kiện khác trong _steps_for")
        self.assertIn("--tts-lufs", argv)
        self.assertEqual(argv[argv.index("--tts-lufs") + 1], "0")
        argv = self._steps(["gan"], {"chuanam": True, "ttsnorm": True}).get("④")
        self.assertEqual(argv[argv.index("--tts-lufs") + 1], "-23")

    def test_taogiong_srt_co_co_chuan_am(self):
        import taogiong_srt as ts2
        src = Path(ts2.__file__).read_text(encoding="utf-8")
        self.assertIn('"--chuan-am"', src)
        self.assertIn("moc=chuan_am", src)


if __name__ == "__main__":
    unittest.main()
