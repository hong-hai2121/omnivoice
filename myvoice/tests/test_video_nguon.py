# -*- coding: utf-8 -*-
"""🎞 'Lấy video tải xuống làm video nguồn' (24/10/2026): tìm video nguồn của tập,
tỉ lệ kéo thời lượng, và cài đặt đi từ taogiong_options.json tới runner.
Không chạy ffmpeg, không mở cửa sổ Tk."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from myvoice.web import core
from myvoice.web.runners import run_episode

gui = core.gui
import video_khung  # noqa: E402  (sys.path đã có scripts/ nhờ core)


class TenTaiBilibiliTests(unittest.TestCase):
    def test_bv_and_av_ids(self):
        self.assertEqual(gui.ten_tai_bilibili(
            "https://www.bilibili.com/video/BV1CGpc6YEub/?spm_id_from=333"), "BV1CGpc6YEub")
        self.assertEqual(gui.ten_tai_bilibili("https://bilibili.com/video/av170001"), "av170001")

    def test_short_link_falls_back_to_tail(self):
        self.assertEqual(gui.ten_tai_bilibili("https://b23.tv/abcXYZ?x=1"), "b23_abcXYZ")
        self.assertEqual(gui.ten_tai_bilibili(""), "")

    def test_runner_uses_shared_helper(self):
        self.assertEqual(run_episode._ten_tai_bilibili("https://b23.tv/q1"),
                         gui.ten_tai_bilibili("https://b23.tv/q1"))
        self.assertIs(run_episode._BILI_LINK_RE, gui.BILI_LINK_RE)


class NguonVideoPathTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def test_empty_source(self):
        p, why = gui.nguon_video_path("")
        self.assertIsNone(p)
        self.assertIn("không có nguồn", why)

    def test_local_video_file_is_used_directly(self):
        v = self.dir / "tap.mp4"
        v.write_bytes(b"0")
        p, why = gui.nguon_video_path(f'"{v}"')
        self.assertEqual(p, v)
        self.assertEqual(why, "")

    def test_local_audio_file_has_no_picture(self):
        a = self.dir / "tap.mp3"
        a.write_bytes(b"0")
        p, why = gui.nguon_video_path(str(a))
        self.assertIsNone(p)
        self.assertIn("audio", why)

    def test_bilibili_link_maps_to_downloads(self):
        link = "https://www.bilibili.com/video/BV1CGpc6YEub/?vd_source=x"
        with patch.object(gui, "TAI_VE_DIR", self.dir):
            p, why = gui.nguon_video_path(link)
            self.assertIsNone(p)
            self.assertIn("BV1CGpc6YEub.mp4", why)
            (self.dir / "BV1CGpc6YEub.mp4").write_bytes(b"0")
            p, why = gui.nguon_video_path(link)
        self.assertEqual(p, self.dir / "BV1CGpc6YEub.mp4")
        self.assertEqual(why, "")

    def test_other_links_only_give_mp3(self):
        p, why = gui.nguon_video_path("https://www.youtube.com/watch?v=abc")
        self.assertIsNone(p)
        self.assertIn("mp3", why)


class NguonVideoCuaTapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.folder = self.dir / "A07 - 95"
        self.folder.mkdir()
        self.video = self.dir / "goc.mp4"
        self.video.write_bytes(b"0")

    def test_lookup_by_folder_path(self):
        manifest = {"k": {"episode": "7", "folder": str(self.folder), "source": str(self.video)}}
        with patch.object(gui, "load_manifest", return_value=manifest):
            p, why = gui.nguon_video_cua_tap(self.folder)
        self.assertEqual(p, self.video)

    def test_lookup_by_episode_when_folder_moved(self):
        manifest = {"k": {"episode": "07", "folder": r"C:\cu\07", "source": str(self.video)}}
        with patch.object(gui, "load_manifest", return_value=manifest):
            p, why = gui.nguon_video_cua_tap(self.folder)          # số tập lấy từ tên thư mục
            self.assertEqual(p, self.video)
            p, why = gui.nguon_video_cua_tap(self.dir / "output", episode="7")
            self.assertEqual(p, self.video)

    def test_unknown_folder(self):
        with patch.object(gui, "load_manifest", return_value={}):
            p, why = gui.nguon_video_cua_tap(self.dir / "output")
        self.assertIsNone(p)
        self.assertIn("manifest", why)

    def test_explicit_path_wins_then_manifest(self):
        with patch.object(gui, "load_manifest", return_value={}):
            p, _ = gui._video_nguon_cho_ngang(str(self.video), self.folder)
            self.assertEqual(p, self.video)
            p, why = gui._video_nguon_cho_ngang(str(self.dir / "mat.mp4"), self.folder)
            self.assertIsNone(p)


class TiLeKeoTests(unittest.TestCase):
    def test_exact_ratio_inside_clamp(self):
        self.assertAlmostEqual(video_khung.ti_le_keo(100, 130), 1.3)
        self.assertAlmostEqual(video_khung.ti_le_keo(100, 80), 0.8)

    def test_clamped_outside_range(self):
        self.assertEqual(video_khung.ti_le_keo(100, 500), video_khung.KEO_MAX)
        self.assertEqual(video_khung.ti_le_keo(100, 10), video_khung.KEO_MIN)

    def test_missing_measurements_keep_speed(self):
        self.assertEqual(video_khung.ti_le_keo(0, 100), 1.0)
        self.assertEqual(video_khung.ti_le_keo(None, 100), 1.0)


class SettingsFlowTests(unittest.TestCase):
    def test_defaults_off_and_120(self):
        self.assertFalse(gui.OPTS_DEFAULTS["ngang_tu_nguon"])
        self.assertEqual(gui.OPTS_DEFAULTS["ngang_nguon_zoom"], 120)

    def test_tts_settings_carry_option_and_clamp_zoom(self):
        opts = dict(gui.OPTS_DEFAULTS, ngang_tu_nguon=True, ngang_nguon_zoom="350")
        with patch.object(core, "load_options", return_value=opts), \
             patch.object(core, "load_web_settings", return_value={"mode": "default"}):
            ts, err = core.tts_settings()
        self.assertEqual(err, "")
        self.assertTrue(ts["ngang_tu_nguon"])
        self.assertEqual(ts["ngang_nguon_zoom"], 200)

    def test_parse_nguon_zoom(self):
        f = gui.App._parse_nguon_zoom
        self.assertEqual(f(""), 120)
        self.assertEqual(f("130"), 130)
        self.assertEqual(f("99"), 100)
        self.assertEqual(f("1,5e2"), 150)

    def test_step_tts_passes_source_video_to_runner(self):
        """Bật 🎞 + nguồn là file video → cài đặt gửi run_tts có ngang_source_video."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        video = Path(tmp.name) / "goc.mp4"
        video.write_bytes(b"0")
        seen = {}

        class FakeApp:
            def _seo_docx_valid(self, p):
                return True

            def _batch_run_tts(self, folder, ts, episode):
                seen.update(ts)
                return True

        state = {"tts": {"ngang_tu_nguon": True, "make_video": True, "make_video_doc": False}}
        with patch.object(run_episode, "_close_driver"):
            code = run_episode.step_tts(FakeApp(), Path(tmp.name), "07", state, str(video))
        self.assertEqual(code, 0)
        self.assertEqual(seen.get("ngang_source_video"), str(video))

    def test_step_tts_without_video_leaves_lookup_to_run_tts(self):
        seen = {}

        class FakeApp:
            def _seo_docx_valid(self, p):
                return True

            def _batch_run_tts(self, folder, ts, episode):
                seen.update(ts)
                return True

        state = {"tts": {"ngang_tu_nguon": True, "make_video": True}}
        with patch.object(run_episode, "_close_driver"):
            run_episode.step_tts(FakeApp(), Path(tempfile.gettempdir()), "07", state,
                                 "https://www.youtube.com/watch?v=x")
        self.assertNotIn("ngang_source_video", seen)


if __name__ == "__main__":
    unittest.main()
