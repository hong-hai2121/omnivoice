# -*- coding: utf-8 -*-
"""Kiểm tra bộ lọc giọng (scripts/hieuung_giong.py): đọc tham số, chuỗi filter
ffmpeg, đáp ứng xung tiếng vang; phần chạy ffmpeg thật chỉ chạy khi máy có ffmpeg."""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import hieuung_giong as hu  # noqa: E402

SR = 24000


class ParseTests(unittest.TestCase):
    def test_parse_fx_clamps_and_reads_text(self):
        self.assertEqual(hu.parse_fx("76"), 76)
        self.assertEqual(hu.parse_fx("76,4"), 76)
        self.assertEqual(hu.parse_fx(150), 100)
        self.assertEqual(hu.parse_fx(-3), 0)
        self.assertEqual(hu.parse_fx(None, 7), 7)
        self.assertEqual(hu.parse_fx("abc", 7), 7)

    def test_fx_from_fills_missing_keys(self):
        self.assertEqual(hu.fx_from(None),
                         dict(vang_truong_do=0, vang_cuong_do=0, thieu_nien=0, sang_giong=0))
        self.assertEqual(hu.fx_from({"vang_truong_do": "80", "vang_cuong_do": 76, "x": 1}),
                         dict(vang_truong_do=80, vang_cuong_do=76, thieu_nien=0, sang_giong=0))

    def test_active_tag_describe(self):
        self.assertFalse(hu.fx_active(vang_truong_do=80, vang_cuong_do=0, thieu_nien=0))
        self.assertTrue(hu.fx_active(vang_cuong_do=1))
        self.assertTrue(hu.fx_active(thieu_nien=1))
        self.assertEqual(hu.fx_tag(80, 0, 0), "")
        self.assertEqual(hu.fx_tag(80, 76, 100), "_vang80-76_tn100")
        self.assertEqual(hu.fx_describe(), "không")
        self.assertIn("thiếu niên 100", hu.fx_describe(80, 76, 100))

    def test_teen_params(self):
        self.assertEqual(hu.teen_params(0), (1.0, 0.0))
        r, st = hu.teen_params(100)
        self.assertAlmostEqual(r, hu.TN_FORMANT_MAX)
        self.assertAlmostEqual(st, hu.TN_PITCH_MAX_ST)
        r50, st50 = hu.teen_params(50)
        self.assertAlmostEqual(r50, 1 + (hu.TN_FORMANT_MAX - 1) / 2)
        self.assertAlmostEqual(st50, hu.TN_PITCH_MAX_ST / 2)


class FilterChainTests(unittest.TestCase):
    def test_no_change_gives_empty_chain(self):
        with patch.object(hu, "has_rubberband", return_value=True):
            self.assertEqual(hu.build_audio_filter(1.0, 0.0, SR), "")

    def test_pitch_only_matches_old_behaviour(self):
        with patch.object(hu, "has_rubberband", return_value=True):
            f = hu.build_audio_filter(1.0, 2.0, SR)
        self.assertEqual(f, f"rubberband=pitch={2 ** (2 / 12):.5f}:formant=preserved"
                            ":transients=smooth:detector=soft")

    def test_teen_chain_shifts_formant_separately(self):
        with patch.object(hu, "has_rubberband", return_value=True):
            parts = hu.build_audio_filter(1.0, 0.0, SR, thieu_nien=100).split(",")
        r = round(SR * hu.TN_FORMANT_MAX) / SR
        p = 2 ** (hu.TN_PITCH_MAX_ST / 12)
        self.assertTrue(parts[0].startswith(f"rubberband=pitch={p / r:.5f}:formant=preserved"))
        self.assertEqual(parts[1], f"asetrate={round(SR * hu.TN_FORMANT_MAX)}")
        self.assertEqual(parts[2], f"aresample={SR}")
        self.assertEqual(parts[3], f"atempo={1 / r:.3f}")

    def test_teen_without_rubberband_falls_back_to_asetrate(self):
        with patch.object(hu, "has_rubberband", return_value=False):
            f = hu.build_audio_filter(1.0, 0.0, SR, thieu_nien=100)
        self.assertIn("asetrate=", f)
        self.assertNotIn("rubberband", f)
        self.assertIn("atempo=", f)

    def test_speed_combines_with_teen(self):
        with patch.object(hu, "has_rubberband", return_value=True):
            f = hu.build_audio_filter(1.2, 0.0, SR, thieu_nien=100)
        r = round(SR * hu.TN_FORMANT_MAX) / SR
        self.assertTrue(f.endswith(f"atempo={1.2 / r:.3f}"))


class SangGiongTests(unittest.TestCase):
    def test_fx_helpers_include_sang(self):
        self.assertEqual(hu.fx_from({"sang_giong": "60"})["sang_giong"], 60)
        self.assertTrue(hu.fx_active(sang_giong=1))
        self.assertFalse(hu.fx_active(sang_giong=0))
        self.assertEqual(hu.fx_tag(0, 0, 0, 60), "_sang60")
        self.assertEqual(hu.fx_tag(80, 76, 100, 60), "_vang80-76_tn100_sang60")
        self.assertIn("sáng giọng 60", hu.fx_describe(sang_giong=60))
        self.assertEqual(hu.fx_describe(sang_giong=0), "không")

    def test_chain_scales_with_level(self):
        self.assertEqual(hu.sang_chain(0, SR), [])
        c100 = hu.sang_chain(100, SR)
        self.assertEqual(c100[0], f"highpass=f={hu.SANG_HP_HZ[1]:.0f}")
        self.assertIn(f"equalizer=f=230:t=q:w=1.2:g={hu.SANG_EQ[0][2]:.2f}", c100)
        self.assertIn(f"equalizer=f=3200:t=q:w=0.9:g={hu.SANG_EQ[2][2]:.2f}", c100)
        self.assertIn(f"highshelf=f=6000:g={hu.SANG_SHELF[1]:.2f}", c100)
        self.assertTrue(any(p.startswith("aexciter=amount=1.00") for p in c100))
        c50 = hu.sang_chain(50, SR)
        self.assertIn(f"equalizer=f=230:t=q:w=1.2:g={hu.SANG_EQ[0][2] / 2:.2f}", c50)
        self.assertFalse(any(p.startswith("aexciter") for p in c50))       # exciter chỉ từ > 50
        self.assertFalse(any(p.startswith("aexciter")
                             for p in hu.sang_chain(100, SR, exciter=False)))  # EQ giọng mẫu
        self.assertFalse(any(p.startswith("aexciter")
                             for p in hu.sang_chain(100, 16000)))          # ceil trên Nyquist

    def test_build_audio_filter_puts_eq_after_pitch_and_limits(self):
        with patch.object(hu, "has_rubberband", return_value=True):
            f = hu.build_audio_filter(1.0, 0.0, SR, sang_giong=60)
            g = hu.build_audio_filter(1.2, 0.0, SR, thieu_nien=100, sang_giong=60)
            self.assertEqual(hu.build_audio_filter(1.0, 0.0, SR, sang_giong=0), "")
        self.assertTrue(f.startswith("highpass=f="))
        self.assertTrue(f.endswith(f"alimiter=limit={hu.SANG_LIMIT}:attack=5:release=60"
                                   ":level=false:latency=true"))
        r = round(SR * hu.TN_FORMANT_MAX) / SR
        self.assertIn(f"atempo={1.2 / r:.3f},highpass=f=", g)   # EQ đứng SAU asetrate/atempo

    def test_ffmpeg_args_pass_sang(self):
        with patch.object(hu, "has_rubberband", return_value=True):
            args, sr, active = hu.build_ffmpeg_args("in.wav", 1.0, 0.0, SR, sang_giong=40)
        self.assertTrue(active)
        self.assertIn("highpass=f=", args[args.index("-filter:a") + 1])


class ReverbTests(unittest.TestCase):
    def test_vang_params_scale(self):
        p0, p100 = hu.vang_params(0, 100), hu.vang_params(100, 100)
        self.assertAlmostEqual(p0["rt60"], hu.VANG_RT60_MIN)
        self.assertAlmostEqual(p100["rt60"], hu.VANG_RT60_MAX)
        self.assertAlmostEqual(p100["wet"], hu.VANG_WET_MAX)
        self.assertAlmostEqual(p100["dry"], hu.VANG_DRY_MIN)
        self.assertEqual(hu.vang_params(80, 0)["wet"], 0.0)

    def test_ir_has_dry_impulse_and_decaying_wet_tail(self):
        ir = hu.build_ir(SR, 80, 76)
        pr = hu.vang_params(80, 76)
        self.assertEqual(ir.dtype, np.float32)
        self.assertTrue(np.all(np.isfinite(ir)))
        self.assertAlmostEqual(float(ir[0]), pr["dry"], places=5)        # xung trực tiếp
        tail = ir.astype(np.float64).copy()
        tail[0] -= pr["dry"]
        self.assertAlmostEqual(float(np.sum(tail ** 2)), pr["wet"] ** 2, places=4)
        self.assertAlmostEqual(len(ir) / SR, pr["predelay_ms"] / 1000 + pr["rt60"] * 1.15, delta=0.01)
        # Đuôi phải tắt dần: năng lượng 10 % cuối nhỏ hơn hẳn 10 % đầu sau tiền trễ.
        start = int(pr["predelay_ms"] / 1000 * SR)
        n = len(ir) - start
        head = np.sum(tail[start:start + n // 10] ** 2)
        end = np.sum(tail[-n // 10:] ** 2)
        self.assertLess(end, head * 0.01)
        # Cùng tham số → cùng đáp ứng xung (seed cố định); cường độ khác → IR khác.
        self.assertTrue(np.array_equal(ir, hu.build_ir(SR, 80, 76)))
        self.assertFalse(np.array_equal(ir, hu.build_ir(SR, 80, 30)))

    def test_ffmpeg_args_use_afir_only_when_reverb_on(self):
        with tempfile.TemporaryDirectory() as td, \
                patch.object(hu, "IR_CACHE_DIR", Path(td)), \
                patch.object(hu, "has_rubberband", return_value=True):
            args, sr, active = hu.build_ffmpeg_args("in.wav", 1.0, 0.0, SR, 80, 76, 0)
            self.assertTrue(active)
            self.assertEqual(sr, SR)
            fc = args[args.index("-filter_complex") + 1]
            self.assertIn("afir=dry=1:wet=1", fc)       # tỉ lệ dry/wet nằm trong IR
            self.assertIn("irnorm=-1", fc)
            self.assertIn("apad=pad_dur=", fc)
            self.assertTrue(Path(args[3]).exists())            # file IR đã sinh
            args2, _, active2 = hu.build_ffmpeg_args("in.wav", 1.0, 0.0, SR, 80, 0, 0)
            self.assertFalse(active2)
            self.assertNotIn("-filter_complex", args2)


@unittest.skipUnless(shutil.which("ffmpeg"), "cần ffmpeg trong PATH")
class FfmpegRoundTripTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.src = Path(self.td.name) / "tone.wav"
        t = np.arange(int(SR * 1.0)) / SR
        sf.write(str(self.src), (0.3 * np.sin(2 * np.pi * 220 * t)).astype("float32"), SR)

    def tearDown(self):
        self.td.cleanup()

    def test_teen_keeps_duration_and_sample_rate(self):
        out = hu.apply_fx_file(self.src, Path(self.td.name) / "tn.wav", thieu_nien=100)
        info = sf.info(str(out))
        self.assertEqual(info.samplerate, SR)
        self.assertAlmostEqual(info.duration, 1.0, delta=0.05)

    def test_reverb_extends_by_rt60_and_keeps_level(self):
        # Nhiễu trắng (không phải sin): tích chập với đuôi năng lượng 1 giữ RMS,
        # nên mức ra ≈ rms_in · √(dry² + wet²) (dry và đuôi không tương quan).
        x = (0.2 * np.random.default_rng(1).standard_normal(SR)).astype("float32")
        src = Path(self.td.name) / "noise.wav"
        sf.write(str(src), x, SR)
        with patch.object(hu, "IR_CACHE_DIR", Path(self.td.name)):
            out = hu.apply_fx_file(src, Path(self.td.name) / "vang.wav",
                                   vang_truong_do=80, vang_cuong_do=76)
        y, sr = sf.read(str(out))
        self.assertEqual(sr, SR)
        pr = hu.vang_params(80, 76)
        self.assertAlmostEqual(len(y) / SR, 1.0 + pr["rt60"], delta=0.05)
        expect = float(np.sqrt(np.mean(x ** 2))) * np.sqrt(pr["dry"] ** 2 + pr["wet"] ** 2)
        rms_out = float(np.sqrt(np.mean(y[SR // 2: SR] ** 2)))   # bỏ nửa đầu: đuôi chưa đầy
        self.assertAlmostEqual(rms_out / expect, 1.0, delta=0.3)

    def test_reverb_keeps_dry_path_exact_and_aligned(self):
        x = np.zeros(SR, dtype="float32")
        x[100] = 1.0
        src = Path(self.td.name) / "click.wav"
        sf.write(str(src), x, SR)
        with patch.object(hu, "IR_CACHE_DIR", Path(self.td.name)):
            out = hu.apply_fx_file(src, Path(self.td.name) / "click_vang.wav",
                                   vang_truong_do=80, vang_cuong_do=76, codec="pcm_f32le")
        y, _ = sf.read(str(out))
        pr = hu.vang_params(80, 76)
        self.assertTrue(np.all(np.abs(y[:100]) < 1e-6))               # không có gì trước xung
        self.assertAlmostEqual(float(y[100]), pr["dry"], places=3)    # dry đúng mức, không trễ
        start = 100 + int(pr["predelay_ms"] / 1000 * SR)
        self.assertGreater(float(np.sqrt(np.mean(y[start:start + SR // 10] ** 2))), 1e-3)

    def test_sang_brightens_noise_and_keeps_length(self):
        x = (0.2 * np.random.default_rng(2).standard_normal(SR * 2)).astype("float32")
        src = Path(self.td.name) / "noise_sang.wav"
        sf.write(str(src), x, SR)
        out = hu.apply_fx_file(src, Path(self.td.name) / "sang.wav", sang_giong=100,
                               codec="pcm_f32le")
        y, sr = sf.read(str(out))
        self.assertEqual(sr, SR)
        self.assertAlmostEqual(len(y) / SR, 2.0, delta=0.05)
        self.assertLessEqual(float(np.abs(y).max()), hu.SANG_LIMIT + 0.02)

        def tilt(a):
            spec = np.abs(np.fft.rfft(a)) ** 2
            fr = np.fft.rfftfreq(len(a), 1 / SR)
            lo = spec[(fr >= 150) & (fr < 400)].sum()
            hi = spec[(fr >= 2500) & (fr < 6000)].sum()
            return hi / lo
        # Cắt −6 dB dải trầm + nâng +6 dB dải cao → tỉ lệ cao/trầm tăng ≥ 12 dB (≈ ×16).
        self.assertGreater(tilt(y[:len(x)]), tilt(x) * 4)

    def test_eq_giong_mau_tam_makes_temp_wav_and_keeps_source(self):
        truoc = self.src.read_bytes()
        tmp = hu.eq_giong_mau_tam(self.src, 100)
        try:
            self.assertTrue(tmp.exists())
            self.assertNotEqual(tmp.resolve(), self.src.resolve())
            self.assertEqual(tmp.suffix, ".wav")
            self.assertEqual(sf.info(str(tmp)).samplerate, SR)
        finally:
            tmp.unlink(missing_ok=True)
        self.assertEqual(self.src.read_bytes(), truoc)      # file mẫu gốc không bị đụng

    def test_nothing_to_apply_copies_file(self):
        out = hu.apply_fx_file(self.src, Path(self.td.name) / "copy.wav")
        self.assertEqual(out.read_bytes(), self.src.read_bytes())


if __name__ == "__main__":
    unittest.main()
