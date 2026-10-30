# -*- coding: utf-8 -*-
"""Tab 🤖 GPT CLI (web/gptcli_test.py): kiểm tra kết nối + nhắn thử và đợi trả lời,
chạy trong luồng của server. codex thật thay bằng stub .py của test_dich_srt_cli."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from myvoice.tests.test_dich_srt_cli import _StubBase
import dich_gptcli  # noqa: E402  (đường dẫn đã chèn khi import test_dich_srt_cli)
import gemini_backend  # noqa: E402


class GptCliTesterTests(_StubBase):
    def setUp(self):
        super().setUp()
        from myvoice.web import gptcli_test
        self.mod = gptcli_test
        self.tester = gptcli_test.GptCliTester()

    def _wait(self):
        self.tester._thread.join(15)
        self.assertFalse(self.tester.running())
        return self.tester.state()

    def test_check_tim_codex_dang_nhap_va_ping(self):
        self.tester.start("check")
        s = self._wait()
        self.assertEqual(s["error"], "")
        self.assertEqual(s["info"]["version"], "9.9.9")
        self.assertTrue(s["info"]["logged_in"])
        self.assertTrue(s["result"].startswith("Lão Tần"))     # lệnh thử ngắn có trả lời
        self.assertGreater(s["finished"], 0)
        self.assertIn(self.mod.PING_TEXT, s["prompt"])
        self.assertEqual(s["text"], self.mod.PING_TEXT)          # bong bóng "Bạn" trên tab
        self.assertTrue(any("🎉" in l for l in s["lines"]))
        self.assertTrue(any("🎛" in l for l in s["lines"]))      # nói rõ model / mức sẽ dùng
        self.assertIn("model", s["info"])

    def test_send_tin_tu_do(self):
        self.tester.start("send", "xin chào, bạn là ai?")
        s = self._wait()
        self.assertEqual(s["error"], "")
        self.assertTrue(s["result"].startswith("Lão Tần"))
        self.assertTrue(s["prompt"].startswith(dich_gptcli.CLI_HEADER))
        self.assertIn("xin chào, bạn là ai?", s["prompt"])
        self.assertNotIn("ĐOẠN CẦN DỊCH", s["prompt"])       # tin tự do: không câu hướng dẫn dịch
        self.assertGreaterEqual(s["elapsed"], 0)
        self.assertEqual(s["text"], "xin chào, bạn là ai?")
        self.assertFalse(s["full"])
        self.assertEqual(len(self.prompts()), 1)

    def test_send_nhu_luc_dich_that(self):
        import dich_gemini as g
        self.tester.start("send", "你好", full_prefix=True)
        s = self._wait()
        self.assertEqual(s["error"], "")
        self.assertIn(g.TRANSLATE_PREFIX_CLI.strip(), s["prompt"])   # hướng dẫn đi kèm trong cùng lệnh
        self.assertIn("ĐOẠN CẦN DỊCH:\n" + g.FICTION_TAG.strip() + "\n你好", s["prompt"])
        self.assertEqual(len(self.prompts()), 1)                    # không tốn lệnh "sẵn sàng chưa"

    def test_khong_co_codex_bao_loi(self):
        with tempfile.TemporaryDirectory() as trong, \
                patch.dict(os.environ, {"PATH": trong, "OMNI_GPT_CLI": ""}):
            dich_gptcli._cache.clear()
            self.tester.start("check")
            s = self._wait()
        self.assertIn("Không tìm thấy codex", s["error"])
        self.assertEqual(s["result"], "")

    def test_cli_loi_bao_trong_error(self):
        os.environ["STUB_FAIL"] = "1"
        self.tester.start("send", "hi")
        s = self._wait()
        self.assertIn("model not supported", s["error"])
        self.assertEqual(s["result"], "")

    def test_kiem_tra_dau_vao(self):
        with self.assertRaises(ValueError):
            self.tester.start("send", "   ")
        with self.assertRaises(ValueError):
            self.tester.start("bogus")


class GptCliRoutesTests(_StubBase):
    """Route tab 🤖: trang, thẻ trạng thái, ô cài đặt tự lưu. File pipe thật thay bằng file
    tạm (route /gpt-cli/luu ghi taogiong_pipeline.json — không POST vào file thật)."""

    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        with patch("threading.Thread.start"):
            from myvoice.web import server
        cls.server = server
        cls.client = TestClient(server.app)

    def setUp(self):
        super().setUp()
        self.pipe = Path(self.tmp.name) / "pipe.json"
        self.pipe.write_text('{"gemini_backend": "firefox", "model": "large-v3"}', encoding="utf-8")
        for p in (patch.object(gemini_backend, "PIPE_FILE", self.pipe),
                  patch.dict(os.environ, {"OMNI_GPT_CLI_MODEL": "", "OMNI_GPT_CLI_EFFORT": "",
                                          "CODEX_HOME": self.tmp.name, "OMNI_GEMINI_BACKEND": ""})):
            p.start()
            self.addCleanup(p.stop)
        os.environ.pop("OMNI_GEMINI_BACKEND", None)
        self.tok = {"token": self.server.TOKEN}

    def luu(self, **data):
        r = self.client.post("/gpt-cli/luu", params=self.tok, data=data,
                             headers={"HX-Request": "true"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("savenote", r.text)
        return json.loads(self.pipe.read_text(encoding="utf-8"))

    def test_trang_va_the_trang_thai(self):
        r = self.client.get("/gpt-cli", params=self.tok)
        self.assertEqual(r.status_code, 200)
        for dau in ("cli-caidat", "cli-chat", "st-model", 'name="effort"', "__khac__"):
            self.assertIn(dau, r.text)
        s = self.client.get("/api/gptcli-info", params=self.tok).json()
        self.assertTrue(s["ok"])
        self.assertEqual((s["version"], s["backend"], s["model_nguon"]),
                         ("9.9.9", "firefox", "codex tự chọn"))

    def test_luu_model_muc_khong_dung_cach_dich(self):
        d = self.luu(model="__khac__", model_khac="gpt-6-luna", effort="high")
        self.assertEqual((d["gptcli_model"], d["gptcli_effort"]), ("gpt-6-luna", "high"))
        self.assertEqual((d["gemini_backend"], d["model"]), ("firefox", "large-v3"))  # không đụng
        d = self.luu(model="gpt-6.1-sol", effort="")
        self.assertEqual((d["gptcli_model"], d["gptcli_effort"]), ("gpt-6.1-sol", ""))
        s = self.client.get("/api/gptcli-info", params=self.tok).json()
        self.assertEqual((s["model"], s["model_nguon"]), ("gpt-6.1-sol", "ô cài đặt tab GPT CLI"))

    def test_o_dung_cli_lam_cach_dich(self):
        self.luu(co_dung_cli="1")                        # không tick, đang firefox → GIỮ firefox
        self.assertEqual(gemini_backend.saved_backend(), "firefox")
        self.luu(co_dung_cli="1", dung_cli="on")
        self.assertEqual(gemini_backend.saved_backend(), "cli")
        self.luu(co_dung_cli="1")                        # bỏ tick khi đang cli → về mặc định
        self.assertEqual(gemini_backend.saved_backend(), "extension")
        self.assertEqual(json.loads(self.pipe.read_text(encoding="utf-8"))["model"], "large-v3")


if __name__ == "__main__":
    unittest.main()
