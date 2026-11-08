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
                # 17/10/2026: việc xếp theo ĐỢT, số tập nằm ở kwargs episodes.
                self.assertIn("đợt 4", title)
                self.assertEqual(self.queue.call_args.kwargs["episodes"], ["126"])
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

    def test_cli_backend_runs_each_episode_to_completion_in_order(self):
        """08/11/2026: dịch bằng GPT CLI (không cần màn hình) → mỗi tập một việc trọn bước,
        tập nhỏ trước; link Bilibili thì có bước tải và một việc đóng Bili23 ở cuối."""
        self.mock(core, "load_pipeline", return_value={"gemini_backend": "cli"})
        self.rows.return_value = [
            {**row(127, recognize=False, translate=False, input=False, seo=False,
                   thumbnail=False, audio=False, video_ngang=False, video_doc=False),
             "source": "https://www.bilibili.com/video/BV1x"},
            row(126, seo=False, video_doc=False),
        ]
        self.run_resume()
        jobs = [call for call in self.queue.call_args_list]
        self.assertEqual(len(jobs), 3)
        t126, (s126,) = jobs[0].args
        t127, (s127,) = jobs[1].args
        self.assertIn("Tập 126", t126)
        self.assertIn("Tập 127", t127)
        self.assertEqual(s126.argv[s126.argv.index("--steps") + 1], "seo,tts")
        self.assertEqual(s127.argv[s127.argv.index("--steps") + 1],
                         "tai,recognize,translate,input,seo,thumbnail,tts")
        self.assertNotIn("--require", s127.argv)
        self.assertIsNotNone(s126.on_success)
        self.assertEqual(jobs[0].kwargs["episodes"], ["126"])
        t_dong, (s_dong,) = jobs[2].args
        self.assertIn("Bili23", t_dong)
        self.assertEqual(s_dong.argv[-1], "--dong-app")
        self.assertTrue(jobs[2].kwargs["light"])

    def test_cli_backend_without_links_does_not_close_bili23(self):
        self.mock(core, "load_pipeline", return_value={"gemini_backend": "firefox"})
        self.rows.return_value = [row(126, seo=False)]
        self.run_resume()
        self.assertEqual(self.queue.call_count, 1)
        self.assertIn("Tập 126", self.queue.call_args.args[0])

    def test_extension_backend_keeps_four_batches(self):
        self.mock(core, "load_pipeline", return_value={"gemini_backend": "extension"})
        self.rows.return_value = [row(ep, seo=False, video_doc=False) for ep in (127, 126)]
        self.run_resume()
        titles = [call.args[0] for call in self.queue.call_args_list]
        self.assertEqual(len(titles), 2)
        self.assertIn("đợt 3", titles[0])
        self.assertIn("đợt 4", titles[1])
        self.assertEqual(self.queue.call_args_list[0].kwargs["episodes"], ["126", "127"])

    def test_extension_backend_closes_bili23_after_batch_2_and_moves_old_close_job(self):
        """Link Bilibili: việc đóng Bili23 nằm SAU đợt 2 (đợt 2 có thể tải lại link hỏng ở
        đợt 1); việc đóng cũ còn chờ trong hàng đợi thì bị bỏ để xếp lại ở cuối."""
        self.mock(core, "load_pipeline", return_value={"gemini_backend": "extension"})
        remove = self.mock(server.runner, "remove", return_value=True)
        self.mock(server.runner, "state", return_value={"pending": [
            {"id": 7, "title": server.steps_mod.DONG_BILI23_TITLE},
            {"id": 8, "title": "⏩ đợt 3 · dịch → input.docx → SEO — 1 tập"}]})
        self.rows.return_value = [
            {**row(127, recognize=False, translate=False, input=False, seo=False,
                   thumbnail=False, video_doc=False),
             "source": "https://www.bilibili.com/video/BV1x"},
            row(126, seo=False, video_doc=False),
        ]
        self.run_resume()
        titles = [call.args[0] for call in self.queue.call_args_list]
        self.assertEqual([t.split(" — ")[0] for t in titles],
                         ["⏩ đợt 1 · tải video/audio", "⏩ đợt 2 · nhận diện tiếng Trung",
                          server.steps_mod.DONG_BILI23_TITLE,
                          "⏩ đợt 3 · dịch → input.docx → SEO",
                          "⏩ đợt 4 · thumbnail → giọng + video"])
        self.assertTrue(self.queue.call_args_list[2].kwargs["light"])
        remove.assert_called_once_with(7)

    def test_no_close_job_without_links(self):
        self.mock(core, "load_pipeline", return_value={"gemini_backend": "extension"})
        self.rows.return_value = [row(126, recognize=False, translate=False, input=False,
                                      seo=False, thumbnail=False, video_doc=False)]
        self.run_resume()
        titles = [call.args[0] for call in self.queue.call_args_list]
        self.assertNotIn(server.steps_mod.DONG_BILI23_TITLE, titles)
        self.assertEqual(len(titles), 3)        # đợt 2, 3, 4 (nguồn là file → không tải)

    def test_front_steps_for_all_episodes_precede_builds(self):
        self.rows.return_value = [row(ep, seo=False, video_doc=False) for ep in (127, 126)]
        self.run_resume()
        # 17/10/2026: hai ĐỢT (SEO mọi tập → dựng mọi tập), mỗi đợt một việc, mỗi tập một
        # bước, tập nhỏ trước; bước dựng phải --require bước dịch của đợt trước.
        jobs = self.queue.call_args_list
        self.assertEqual(len(jobs), 2)
        (t_seo, seo_steps), (t_tts, tts_steps) = jobs[0].args, jobs[1].args
        self.assertIn("đợt 3", t_seo)
        self.assertIn("đợt 4", t_tts)
        self.assertEqual(jobs[0].kwargs["episodes"], ["126", "127"])
        self.assertEqual([len(seo_steps), len(tts_steps)], [2, 2])
        for built in seo_steps:
            argv = built.argv
            self.assertEqual(argv[argv.index("--steps") + 1], "seo")
            self.assertTrue(built.continue_on_fail)
        for built in tts_steps:
            argv = built.argv
            self.assertEqual(argv[argv.index("--steps") + 1], "tts")
            self.assertEqual(argv[argv.index("--require") + 1], "translate,input")


if __name__ == "__main__":
    unittest.main()
