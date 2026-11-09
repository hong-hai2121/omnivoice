# -*- coding: utf-8 -*-
"""Ô "Tải Bilibili" (05/11/2026): mức video khi tải link Bilibili qua app Bili23 —
tên file của bản thấp, lệnh gửi script tải, đường đi của cài đặt từ form tới runner.
Không tải gì thật, không mở app Bili23."""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from starlette.datastructures import FormData

from myvoice.web import core, server, steps
from myvoice.web.runners import run_episode

gui = core.gui

# Nạp ĐÚNG file script mà runner gọi (không chèn myvideo/ vào sys.path).
_spec = importlib.util.spec_from_file_location("video_taibilibili", run_episode.TAIBILI_SCRIPT)
tb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tb)

LINK = "https://www.bilibili.com/video/BV1CGpc6YEub/?vd_source=x"
BV = "BV1CGpc6YEub"


class MucVaTenFileTests(unittest.TestCase):
    def test_default_is_highest(self):
        self.assertEqual(gui.PIPE_DEFAULTS["bili_quality"], "auto")
        self.assertEqual(gui.BILI_QUALITIES[0], "auto")

    def test_normalize(self):
        self.assertEqual(gui.chuan_bili_quality("360p"), "360P")
        self.assertEqual(gui.chuan_bili_quality(" 720P "), "720P")
        for la in ("", None, "AUTO", "auto", "4K", "abc"):
            self.assertEqual(gui.chuan_bili_quality(la), "auto")

    def test_low_quality_gets_its_own_file_name(self):
        self.assertEqual(gui.ten_file_bilibili(LINK), BV)
        self.assertEqual(gui.ten_file_bilibili(LINK, "auto"), BV)
        self.assertEqual(gui.ten_file_bilibili(LINK, "360P"), f"{BV}_360P")
        self.assertEqual(gui.ten_file_bilibili(LINK, "linh tinh"), BV)
        self.assertEqual(gui.ten_file_bilibili("", "360P"), "")

    def test_low_quality_file_is_never_used_as_picture_source(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(gui, "TAI_VE_DIR", Path(tmp)):
            (Path(tmp) / f"{BV}_360P.mp4").write_bytes(b"0")
            p, why = gui.nguon_video_path(LINK)
            self.assertIsNone(p)
            self.assertIn("chất lượng thấp", why)
            self.assertIn(f"{BV}_360P.mp4", why)
            (Path(tmp) / f"{BV}.mp4").write_bytes(b"0")
            p, why = gui.nguon_video_path(LINK)
            self.assertEqual(p, Path(tmp) / f"{BV}.mp4")


class ScriptTaiTests(unittest.TestCase):
    def test_chuan_chat_luong(self):
        self.assertEqual(tb.chuan_chat_luong("360"), "360P")
        self.assertEqual(tb.chuan_chat_luong("360p"), "360P")
        self.assertEqual(tb.chuan_chat_luong("1080P"), "1080P")
        self.assertEqual(tb.chuan_chat_luong(""), "auto")
        self.assertEqual(tb.chuan_chat_luong("Auto"), "auto")
        with self.assertRaises(tb.ThatBai):
            tb.chuan_chat_luong("sieu net")

    def test_every_web_choice_is_known_to_the_script(self):
        for muc in gui.BILI_QUALITIES:
            self.assertEqual(tb.chuan_chat_luong(muc), muc)

    def test_chon_muc_never_goes_above_request_when_avoidable(self):
        du = ["auto", "1080P", "720P", "480P", "360P"]
        self.assertEqual(tb.chon_muc("auto", du), "auto")
        self.assertEqual(tb.chon_muc("360P", du), "360P")
        self.assertEqual(tb.chon_muc("720P", ["auto", "1080P", "480P", "360P"]), "480P")
        # Video chỉ có mức cao hơn → mức THẤP NHẤT đang có, không để app nhảy lên cao nhất.
        self.assertEqual(tb.chon_muc("360P", ["auto", "1080P", "720P", "480P"]), "480P")
        # App chưa báo các mức đang có → cứ xin đúng mức người dùng chọn.
        self.assertEqual(tb.chon_muc("360P", []), "360P")
        self.assertEqual(tb.chon_muc("360P", None), "360P")


class _FakeProc:
    """Thay subprocess.Popen: ghi lại lệnh, giả vờ script đã tải xong file --out."""
    seen: list = []

    def __init__(self, argv, **kw):
        type(self).seen.append(list(argv))
        Path(argv[argv.index("--out") + 1]).write_bytes(b"0")
        self.stdout = iter(())

    def wait(self):
        return 0


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        _FakeProc.seen = []
        for p in (patch.object(gui, "TAI_VE_DIR", self.dir),
                  patch.object(run_episode.subprocess, "Popen", _FakeProc)):
            p.start()
            self.addCleanup(p.stop)

    def test_default_downloads_full_file_without_quality_flag(self):
        media, why = run_episode._tai_video_bilibili(LINK)
        self.assertEqual((media, why), (str(self.dir / f"{BV}.mp4"), ""))
        self.assertNotIn("--chat-luong", _FakeProc.seen[0])

    def test_low_quality_goes_to_suffixed_file(self):
        media, why = run_episode._tai_video_bilibili(LINK, "360P")
        self.assertEqual((media, why), (str(self.dir / f"{BV}_360P.mp4"), ""))
        argv = _FakeProc.seen[0]
        self.assertEqual(argv[argv.index("--chat-luong") + 1], "360P")
        self.assertFalse((self.dir / f"{BV}.mp4").exists())

    def test_existing_full_file_is_reused_instead_of_downloading_low(self):
        full = self.dir / f"{BV}.mp4"
        full.write_bytes(b"0" * 1_000_001)
        media, why = run_episode._tai_video_bilibili(LINK, "360P")
        self.assertEqual((media, why), (str(full), ""))
        self.assertEqual(_FakeProc.seen, [])

    def test_picture_source_option_forces_highest(self):
        with patch.object(core, "load_options",
                          return_value={"ngang_tu_nguon": True, "make_video": True}):
            self.assertEqual(run_episode._muc_tai_bilibili("360P"), "auto")
        with patch.object(core, "load_options",
                          return_value={"ngang_tu_nguon": True, "make_video": False}):
            self.assertEqual(run_episode._muc_tai_bilibili("360P"), "360P")
        with patch.object(core, "load_options", return_value={"ngang_tu_nguon": False}):
            self.assertEqual(run_episode._muc_tai_bilibili("360p"), "360P")
            self.assertEqual(run_episode._muc_tai_bilibili(""), "auto")

    def test_fetch_media_hands_quality_to_downloader(self):
        with patch.object(core, "load_options", return_value={}), \
                patch.object(run_episode, "_tai_video_bilibili",
                             return_value=("x.mp4", "")) as tai:
            media, why = run_episode._fetch_media(LINK, "07", "360P")
        self.assertEqual(media, "x.mp4")
        tai.assert_called_once_with(LINK, "360P")


class WebFlowTests(unittest.TestCase):
    def test_runner_argv_carries_saved_quality(self):
        with patch.object(core, "load_pipeline", return_value={"bili_quality": "360P"}):
            argv = steps._base_argv("tai", LINK, "", False)
        self.assertEqual(argv[argv.index("--bili-quality") + 1], "360P")
        with patch.object(core, "load_pipeline", return_value={"model": "medium"}):
            argv = steps._base_argv("tai", LINK, "", False)
        self.assertEqual(argv[argv.index("--bili-quality") + 1], "auto")

    def test_runner_accepts_the_flag(self):
        with patch.object(run_episode, "_setup_logging"), \
                patch.object(run_episode, "HeadlessApp"), \
                patch.object(run_episode, "_resolve_folder",
                             return_value=(Path(tempfile.gettempdir()), "07")), \
                patch.object(run_episode, "step_tai", return_value=0) as tai:
            run_episode.main(["--steps", "tai", "--source", LINK, "--bili-quality", "360P"])
        self.assertEqual(tai.call_args.args[-1], "360P")

    def test_both_forms_save_quality_and_keep_it_when_field_is_absent(self):
        original = {"model": "medium", "speed": "0.7", "bili_quality": "480P"}
        for save in (server._save_pipe_from_form, server._save_model_speed):
            for form, mong in (({"bili_quality": "360P"}, "360P"),
                               ({"bili_quality": "linh tinh"}, "auto"),
                               ({"model": "small"}, "480P")):
                with patch.object(server.core, "load_pipeline", return_value=dict(original)), \
                        patch.object(server.core, "save_pipeline") as write:
                    save(FormData(form))
                self.assertEqual(write.call_args.args[0]["bili_quality"], mong)

    def test_pages_show_the_select_with_saved_choice(self):
        from fastapi.testclient import TestClient
        with patch.object(server, "_vram", return_value={}), \
                patch.object(server.core, "upload_slots_text", return_value="08:00"), \
                patch.object(server.core, "load_pipeline",
                             return_value={"model": "medium", "bili_quality": "360P"}):
            client = TestClient(server.app)
            client.cookies.set(server.COOKIE, server.TOKEN)
            for trang in ("/", "/nhandien"):
                html = client.get(trang).text
                self.assertIn('name="bili_quality"', html, trang)
                self.assertRegex(html, r'value="360P"\s+selected', trang)
                self.assertNotRegex(html, r'value="auto"\s+selected', trang)


if __name__ == "__main__":
    unittest.main()
