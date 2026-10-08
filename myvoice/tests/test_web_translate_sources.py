"""Step ② accepts source input without running real ASR, Gemini or uploads."""
import asyncio
from contextlib import ExitStack
import unittest
from unittest.mock import AsyncMock, patch

from starlette.datastructures import FormData
from starlette.requests import Request

from myvoice.web import core

with patch("threading.Thread.start"):
    from myvoice.web import server


def episode(number, **changes):
    state = dict(recognize=True, translate=True, input=True, seo=True,
                 thumbnail=True, video_ngang=True, upload=True)
    state.update(changes)
    return dict(episode=str(number), source=f"source-{number}", steps=state)


class TranslateSourcesTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.rows = self.mock(core, "episode_rows", return_value=[])
        self.plan = self.mock(core, "plan_episodes", side_effect=lambda lines, *a, **k:
                              [""] * len(lines))
        self.remember = self.mock(core, "remember_sources")
        self.drop = self.mock(core, "drop_from_src_draft")
        self.mock(core, "load_pipeline", return_value={"model": "small", "speed": "0.8"})
        self.mock(core, "save_pipeline")
        self.mock(server, "_auto_upload_wanted", return_value=False)
        self.mock(server.steps_mod, "cleanup_tmp")
        self.queue = self.mock(server.runner, "enqueue")
        self.upload = self.mock(server.steps_mod, "queue_upload")
        self.logs = self.mock(server, "log")

    def mock(self, target, name, **kwargs):
        return self.stack.enter_context(patch.object(target, name, **kwargs))

    def run_button(self, sources="", selected=(), action="translate", **fields):
        form = FormData([("action", action), ("sources", sources), *fields.items(),
                         *(("tap", str(ep)) for ep in selected)])
        request = Request({"type": "http", "headers": [(b"referer", b"http://localhost/")]})
        with patch.object(request, "form", AsyncMock(return_value=form)):
            response = asyncio.run(server.run_recog(request))
        self.assertEqual(response.status_code, 303)

    def queued_steps(self, index=0):
        return self.queue.call_args_list[index].args[1]

    def assert_chain(self, keys, index=0, source=None):
        steps = self.queued_steps(index)
        self.assertEqual([s.argv[s.argv.index("--steps") + 1] for s in steps], keys)
        if source is not None:
            for step in steps:
                self.assertEqual(step.argv[step.argv.index("--source") + 1], source)
        self.upload.assert_not_called()

    def test_new_local_file_runs_without_episode_rows(self):
        source = r"C:\Users\PC\Downloads\truyen moi.mp3"
        self.run_button(sources=source)
        self.assertEqual(self.queue.call_count, 1)
        self.assert_chain(["recognize", "translate", "input", "seo"], source=source)
        self.rows.assert_not_called()
        self.remember.assert_called_once_with([source])
        self.drop.assert_called_once_with([source])
        self.assertFalse(any("0 tập" in c.args[0] for c in self.logs.call_args_list))

    def test_multiple_sources_keep_order_and_ignore_blank_or_duplicate_lines(self):
        first, second = "https://example.com/video/1", r"D:\audio\2.mp3"
        self.run_button(sources=f" \n {first} \n\n{second}\n{first}\n")
        self.assertEqual(self.queue.call_count, 2)
        for i, source in enumerate((first, second)):
            self.assert_chain(["recognize", "translate", "input", "seo"], i, source)
        self.drop.assert_called_once_with([first, second])

    def test_source_input_takes_precedence_over_unselected_old_episodes(self):
        self.rows.return_value = [episode(127, translate=False, input=False, seo=False)]
        self.run_button(sources="new-source.mp3")
        self.assertEqual(self.queue.call_count, 1)
        self.assert_chain(["recognize", "translate", "input", "seo"], source="new-source.mp3")
        self.rows.assert_not_called()

    def test_selected_episode_takes_precedence_over_sources(self):
        self.rows.return_value = [episode(127), episode(128)]
        self.run_button(sources="new-source.mp3", selected=[127])
        self.assertEqual(self.queue.call_count, 1)
        self.assert_chain(["translate", "input", "seo"], source="source-127")
        self.plan.assert_not_called()
        self.drop.assert_not_called()

    def test_unknown_selection_does_not_run_sources_or_other_episodes(self):
        self.rows.return_value = [episode(128, seo=False)]
        self.run_button(sources="new-source.mp3", selected=[999])
        self.queue.assert_not_called()
        self.drop.assert_not_called()

    def test_empty_sources_resume_each_missing_part_including_seo(self):
        self.rows.return_value = [episode(127, seo=False), episode(128, input=False),
                                 episode(129, translate=False), episode(130),
                                 episode(131, recognize=False, input=False)]
        self.run_button(sources=" \n ")
        self.assertEqual(self.queue.call_count, 3)
        for i, number in enumerate((127, 128, 129)):
            self.assert_chain(["translate", "input", "seo"], i, f"source-{number}")
        self.drop.assert_not_called()

    def test_force_does_not_redo_existing_recognition_for_source(self):
        self.run_button(sources="old-source.mp3", force="on")
        steps = self.queued_steps()
        self.assertNotIn("--force", steps[0].argv)
        for step in steps[1:]:
            self.assertIn("--force", step.argv)
        # No explicit episode: runner resolves the existing source via its manifest.
        for step in steps:
            self.assertNotIn("--episode", step.argv)

    def test_source_episode_numbering_is_shared_with_script_route(self):
        self.plan.side_effect = None
        self.plan.return_value = ["150", "151"]
        self.run_button(sources="one.mp3\ntwo.mp3", episode="150", epsrc="manual")
        self.plan.assert_called_once_with(["one.mp3", "two.mp3"], "150", mode="manual")
        for i, number in enumerate(("150", "151")):
            for step in self.queued_steps(i):
                self.assertEqual(step.argv[step.argv.index("--episode") + 1], number)

    def test_failed_build_keeps_sources_that_were_not_queued(self):
        original = server.steps_mod.build_steps

        def build(keys, **kwargs):
            if kwargs["source"] == "bad.mp3":
                return [], "test build error"
            return original(keys, **kwargs)

        with patch.object(server.steps_mod, "build_steps", side_effect=build):
            self.run_button(sources="good.mp3\nbad.mp3\nlater.mp3")
        self.assertEqual(self.queue.call_count, 1)
        self.drop.assert_called_once_with(["good.mp3"])
        self.assertTrue(any("test build error" in c.args[0] for c in self.logs.call_args_list))

    def test_thumbnail_button_does_not_consume_source_input(self):
        self.rows.return_value = [episode(127, thumbnail=False)]
        self.run_button(sources="new-source.mp3", action="thumbnail")
        self.assert_chain(["thumbnail"], source="source-127")
        self.plan.assert_not_called()
        self.drop.assert_not_called()


if __name__ == "__main__":
    unittest.main()
