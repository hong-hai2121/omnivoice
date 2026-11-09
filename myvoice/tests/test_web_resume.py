"""Regression tests for Home's resume planner; no rendering or uploads run."""
from contextlib import ExitStack
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from starlette.datastructures import FormData
from starlette.requests import Request

from myvoice.web import core

# Import routes without starting queue workers or the idle/sleep watcher.
with patch("threading.Thread.start"):
    from myvoice.web import server


OPTIONS = dict(make_video=True, make_video_doc=True, make_tiktok=True, make_short=True)


def completed_steps(**changes):
    result = dict.fromkeys(("recognize", "translate", "input", "seo", "thumbnail",
                            "audio", "video_ngang", "video_doc", "video_tiktok",
                            "video_short", "upload", "short", "facebook"), True)
    result["doc_cho_seo"] = False
    result.update(changes)
    return result


def row(episode, **changes):
    return dict(episode=str(episode), source=f"source-{episode}",
                steps=completed_steps(**changes))


class MissingStepsTests(unittest.TestCase):
    def missing(self, steps, **kwargs):
        return core.missing_steps(steps, "full", options=OPTIONS, **kwargs)

    def test_episode_126_needs_remaining_video_outputs(self):
        state = completed_steps(video_doc=False, video_tiktok=False, video_short=False,
                                upload=False, short=False, facebook=False)
        self.assertEqual(self.missing(state, upload=True), ["tts"])

    def test_each_enabled_output_can_resume_independently(self):
        for key in ("audio", "video_ngang", "video_doc", "video_tiktok", "video_short"):
            with self.subTest(output=key):
                self.assertEqual(self.missing(completed_steps(**{key: False})), ["tts"])

    def test_disabled_video_outputs_do_not_trigger_rebuild(self):
        state = completed_steps(video_ngang=False, video_doc=False,
                                video_tiktok=False, video_short=False)
        options = dict(make_video=False, make_video_doc=False, make_tiktok=False,
                       make_short=True)
        self.assertEqual(core.missing_steps(state, "full", options=options), [])

    def test_short_requires_tiktok_and_short_options(self):
        for changes in (dict(make_tiktok=False), dict(make_short=False)):
            with self.subTest(options=changes):
                self.assertEqual(core.missing_steps(
                    completed_steps(video_short=False), "full",
                    options={**OPTIONS, **changes}), [])

    def test_episode_127_needs_uploads_without_rebuilding(self):
        state = completed_steps(upload=False, short=False, facebook=False)
        self.assertEqual(self.missing(state, upload=True), ["upload", "facebook"])

    def test_main_upload_respects_auto_upload_setting(self):
        self.assertEqual(self.missing(completed_steps(upload=False, short=False)), [])

    def test_already_uploaded_episode_only_resumes_missing_short(self):
        self.assertEqual(self.missing(completed_steps(short=False), upload=True), ["short"])

    def test_complete_episode_has_no_work(self):
        self.assertEqual(self.missing(completed_steps(), upload=True), [])

    def test_deferred_seo_still_triggers_build(self):
        self.assertEqual(self.missing(completed_steps(doc_cho_seo=True)), ["tts"])

    def test_facebook_uses_selected_video_variant(self):
        state = completed_steps(video_doc=False, facebook=False)
        options = {**OPTIONS, "make_video_doc": False}
        self.assertEqual(core.missing_steps(state, "ngan", options=options), ["facebook"])
        self.assertEqual(core.missing_steps(state, "full", options=options), [])

    def test_short_file_is_separate_from_upload_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            state = core.folder_steps(folder, "126")
            self.assertFalse(state["video_short"])
            (folder / "short.mp4").touch()
            state = core.folder_steps(folder, "126")
            self.assertTrue(state["video_short"])
            self.assertFalse(state["short"])

    def test_table_counts_only_enabled_build_outputs_and_deferred_seo(self):
        state = completed_steps(video_doc=False, video_tiktok=False, video_short=False)
        options = {**OPTIONS, "make_video_doc": False, "make_tiktok": False}
        with patch.object(core, "load_options", return_value=options), \
                patch.object(core.gui, "load_manifest", return_value={}), \
                patch.object(core.gui, "episode_dirs", return_value=[Path("E126")]), \
                patch.object(core, "translation_pairs", return_value=([], [])), \
                patch.object(core, "folder_steps", return_value=state), \
                patch.object(core, "blank_chunks", return_value=[]), \
                patch.object(core, "red_chunks", return_value=[]):
            result = core.episode_rows()[0]
            self.assertEqual(result["done_count"], result["total_steps"])
            state["doc_cho_seo"] = True
            result = core.episode_rows()[0]
            self.assertLess(result["done_count"], result["total_steps"])


class ResumeRouteTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.rows = self.mock(core, "episode_rows", return_value=[])
        self.auto_upload = self.mock(server, "_auto_upload_wanted", return_value=True)
        self.fb_auto = self.mock(core, "facebook_auto", return_value=True)
        self.mock(core, "facebook_ban", return_value="full")
        self.mock(core, "load_options", return_value=OPTIONS)
        self.on_channel = self.mock(core, "episodes_on_channel", return_value=set())
        self.mock(core, "load_pipeline", return_value={})
        self.mock(server.steps_mod, "cleanup_tmp")
        self.mock(server.steps_mod, "_write_tts_json", return_value=("test-tts.json", ""))
        self.queue = self.mock(server.runner, "enqueue")
        self.upload = self.mock(server.steps_mod, "queue_upload")
        self.short = self.mock(server.steps_mod, "queue_short")
        self.facebook = self.mock(server.steps_mod, "queue_facebook")
        self.logs = self.mock(server, "log")

    def mock(self, target, name, **kwargs):
        return self.stack.enter_context(patch.object(target, name, **kwargs))

    def run_resume(self, selected=()):
        request = Request({"type": "http", "headers": [(b"referer", b"http://localhost/")]})
        response = server._run_resume(request, FormData([("tap", str(ep)) for ep in selected]))
        self.assertEqual(response.status_code, 303)

    def test_126_and_127_resume_with_or_without_checkbox_selection(self):
        for selected in ((), (126, 127)):
            with self.subTest(selected=selected):
                self.queue.reset_mock()
                self.upload.reset_mock()
                self.facebook.reset_mock()
                self.rows.return_value = [
                    row(127, upload=False, short=False, facebook=False),
                    row(126, video_doc=False, video_tiktok=False, video_short=False,
                        upload=False, short=False, facebook=False),
                ]
                self.run_resume(selected)
                self.queue.assert_called_once()
                title, built = self.queue.call_args.args
                self.assertIn("126", title)
                argv = built[0].argv
                self.assertEqual(argv[argv.index("--steps") + 1], "tts")
                self.assertNotIn("--force", argv)
                self.assertIsNotNone(built[0].on_success)
                self.upload.assert_called_once_with("127")
                self.facebook.assert_called_once_with("127")
                self.short.assert_not_called()

    def test_unselected_old_posts_are_deferred_with_accurate_message(self):
        self.fb_auto.return_value = False
        self.rows.return_value = [row(125, short=False, facebook=False)]
        self.run_resume()
        self.queue.assert_not_called()
        self.upload.assert_not_called()
        self.short.assert_not_called()
        self.facebook.assert_not_called()
        self.assertIn("tick", self.logs.call_args.args[0])
        self.assertNotIn("✅", self.logs.call_args.args[0])

    def test_selected_old_posts_use_separate_queues(self):
        self.rows.return_value = [row(125, short=False, facebook=False)]
        self.run_resume((125,))
        self.queue.assert_not_called()
        self.upload.assert_not_called()
        self.short.assert_called_once_with("125")
        self.facebook.assert_called_once_with("125")

    def test_auto_upload_off_does_not_queue_main_upload(self):
        self.auto_upload.return_value = False
        self.rows.return_value = [row(127, upload=False, short=False)]
        self.run_resume((127,))
        self.upload.assert_not_called()
        self.queue.assert_not_called()

    def test_channel_cache_prevents_reupload(self):
        self.on_channel.return_value = {127}
        self.rows.return_value = [row(127, upload=False, short=False)]
        self.run_resume((127,))
        self.upload.assert_not_called()

    def test_127_already_on_channel_resumes_facebook_without_selection(self):
        self.on_channel.return_value = {127}
        self.rows.return_value = [row(127, upload=False, short=False, facebook=False)]
        self.run_resume()
        self.upload.assert_not_called()
        self.queue.assert_not_called()
        self.facebook.assert_called_once_with("127")

    def test_auto_facebook_does_not_implicitly_resume_old_shorts(self):
        self.rows.return_value = [row(125, short=False, facebook=False)]
        self.run_resume()
        self.facebook.assert_called_once_with("125")
        self.short.assert_not_called()

    def test_auto_facebook_off_is_respected_for_unselected_upload(self):
        self.fb_auto.return_value = False
        self.rows.return_value = [row(127, upload=False, short=False, facebook=False)]
        self.run_resume()
        self.upload.assert_called_once_with("127")
        self.facebook.assert_not_called()

    def test_missing_source_is_not_reported_as_complete(self):
        self.rows.return_value = [{**row(126, recognize=False), "source": ""}]
        self.run_resume((126,))
        self.queue.assert_not_called()
        self.assertIn("chưa xếp chạy được", self.logs.call_args.args[0])

    def test_invalid_tts_settings_are_not_reported_as_complete(self):
        self.rows.return_value = [row(126, video_doc=False)]
        self.mock(server.steps_mod, "_write_tts_json", return_value=("", "Thiếu giọng mẫu"))
        self.run_resume((126,))
        self.queue.assert_not_called()
        self.assertIn("chưa xếp chạy được", self.logs.call_args.args[0])

    def test_unknown_selection_is_not_reported_as_complete(self):
        self.run_resume((999,))
        self.queue.assert_not_called()
        self.assertIn("Không tìm thấy", self.logs.call_args.args[0])

    def test_front_steps_for_all_episodes_precede_builds(self):
        self.rows.return_value = [row(ep, seo=False, video_doc=False) for ep in (127, 126)]
        self.run_resume()
        jobs = [call.args for call in self.queue.call_args_list]
        self.assertEqual(len(jobs), 4)
        self.assertIn("126", jobs[0][0])
        self.assertIn("127", jobs[1][0])
        for _, built in jobs[:2]:
            argv = built[0].argv
            self.assertEqual(argv[argv.index("--steps") + 1], "seo")
        for _, built in jobs[2:]:
            argv = built[0].argv
            self.assertEqual(argv[argv.index("--steps") + 1], "tts")
            self.assertEqual(argv[argv.index("--require") + 1], "translate,input")


if __name__ == "__main__":
    unittest.main()
