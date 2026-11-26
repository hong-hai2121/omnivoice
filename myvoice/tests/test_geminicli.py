# -*- coding: utf-8 -*-
"""Gemini CLI (Antigravity `agy -p`) làm cách dịch thứ tư — "gemini_cli" trong
gemini_backend, đi chung đường với GPT CLI (dich_gptcli rẽ sang dich_geminicli).

agy thật thay bằng stub .py (OMNI_GEMINI_CLI trỏ tới file .py) — không gọi mạng; codex
thay bằng stub của test_dich_srt_cli để chắc Gemini KHÔNG gọi nhầm sang codex."""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from test_dich_srt_cli import STUB as CODEX_STUB, TEXTS  # noqa: E402 (chèn sẵn sys.path)

import dich_geminicli  # noqa: E402
import dich_gptcli  # noqa: E402
import dich_srt  # noqa: E402
import gemini_backend  # noqa: E402

# Stub "agy": --version / models / -p <đề bài>. In MỘT dòng JSON như agy thật; argv ghi
# vào <STUB_LOG>.args (soi --model), đề bài vào STUB_LOG. Đề bài bảo "đọc file" → đọc
# de_bai.txt trong thư mục làm việc (đường đề bài quá dài).
AGY_STUB = r'''
import json, os, sys
args = sys.argv[1:]
with open(os.environ["STUB_LOG"] + ".args", "a", encoding="utf-8") as f:
    f.write(json.dumps(args, ensure_ascii=False) + "\n")
if args[:1] == ["--version"]:
    print("agy 7.7.7"); sys.exit(0)
if args[:1] == ["models"]:
    print("gemini-9-thu-high\tGemini 9 Thu (High)\nkhac-model\tKhong phai Gemini"); sys.exit(0)
if os.environ.get("STUB_FAIL"):
    print(json.dumps({"status": "ERROR", "error": "invalid model selection: x"})); sys.exit(1)
prompt = args[args.index("-p") + 1]
if "de_bai.txt" in prompt:
    prompt = open("de_bai.txt", encoding="utf-8").read()
with open(os.environ["STUB_LOG"], "a", encoding="utf-8") as f:
    f.write(prompt + "\n=====\n")
lines = [f"{l.split(' ')[0]} Dich {l.split(' ')[0][2:-1]}" for l in prompt.splitlines() if l.startswith("B[")]
print("dong chu thua truoc JSON")
print(json.dumps({"status": "SUCCESS", "conversation_id": "c1",
                  "response": "\n".join(lines) or "Xin chào từ Gemini"}, ensure_ascii=False))
'''


class _AgyBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = Path(self.tmp.name)
        (d / "agy_stub.py").write_text(AGY_STUB, encoding="utf-8")
        (d / "codex_stub.py").write_text(CODEX_STUB, encoding="utf-8")
        self.log = str(d / "agy.log")
        self.codex_log = str(d / "codex.log")
        self.pipe = d / "pipe.json"
        self.pipe.write_text("{}", encoding="utf-8")
        for p in (patch.dict(os.environ, {
                      "OMNI_GEMINI_CLI": str(d / "agy_stub.py"), "OMNI_GPT_CLI": str(d / "codex_stub.py"),
                      "STUB_LOG": self.log, "STUB_FAIL": "", "OMNI_GEMINI_CLI_MODEL": "",
                      "OMNI_GPT_CLI_MODEL": "", "OMNI_GPT_CLI_EFFORT": ""}),
                  patch.object(gemini_backend, "PIPE_FILE", self.pipe)):
            p.start()
            self.addCleanup(p.stop)
        os.environ.pop("OMNI_GEMINI_BACKEND", None)
        for c in (dich_gptcli._cache, dich_geminicli._cache, dich_geminicli._model_cache):
            c.clear()
            self.addCleanup(c.clear)

    def prompts(self):
        if not os.path.exists(self.log):
            return []
        return [p for p in Path(self.log).read_text(encoding="utf-8").split("=====\n") if p.strip()]

    def argv(self):
        return [json.loads(l) for l in Path(self.log + ".args").read_text(encoding="utf-8").splitlines()]


class BackendTests(_AgyBase):
    def test_lua_chon_thu_tu(self):
        self.assertEqual(gemini_backend.set_backend("gemini_cli"), "gemini_cli")
        self.assertEqual(gemini_backend.saved_backend(), "gemini_cli")
        self.assertTrue(gemini_backend.la_cli())
        self.assertEqual(gemini_backend.cli_nha(), "gemini")
        self.assertEqual(dich_gptcli.ten_cli(), "Gemini CLI")
        self.assertIn("agy", gemini_backend.browser_hint())
        gemini_backend.set_backend("cli")
        self.assertTrue(gemini_backend.la_cli())
        self.assertEqual(gemini_backend.cli_nha(), "gpt")
        gemini_backend.set_backend("extension")
        self.assertFalse(gemini_backend.la_cli())
        self.assertEqual(dich_gptcli.nha_hien_tai(), "gpt")       # không phải CLI → --cli gõ tay vẫn là GPT

    def test_bien_moi_truong_chot_luc_xep_hang(self):
        with patch.dict(os.environ, {"OMNI_GEMINI_BACKEND": "gemini_cli"}):
            self.assertEqual(dich_gptcli.nha_hien_tai(), "gemini")


class GoiTests(_AgyBase):
    def test_kiem_tra_va_goi(self):
        info = dich_gptcli.kiem_tra("gemini")
        self.assertEqual((info["version"], info["nha"], info["ten"], info["lenh"]),
                         ("7.7.7", "gemini", "Gemini CLI", "agy"))
        self.assertTrue(info["logged_in"])
        self.assertIn("Gemini CLI", dich_gptcli.mo_ta_cli(info))
        self.assertEqual(dich_gptcli.goi("xin chào", nha="gemini"), "Xin chào từ Gemini")
        a = self.argv()[-1]
        self.assertEqual(a[-2:], ["-p", "xin chào"])
        self.assertIn("--disable-slash-commands", a)
        self.assertNotIn("--model", a)                             # chưa chọn model → agy tự chọn
        self.assertFalse(os.path.exists(self.codex_log))           # không gọi nhầm codex

    def test_theo_o_cach_dich(self):
        gemini_backend.set_backend("gemini_cli")
        self.assertEqual(dich_gptcli.goi("hi"), "Xin chào từ Gemini")
        gemini_backend.set_backend("cli")
        self.assertNotEqual(dich_gptcli.goi("hi"), "Xin chào từ Gemini")   # về codex stub

    def test_model_luu_rieng_khong_dung_gptcli(self):
        dich_gptcli.luu_cai_dat("gpt-6-luna", "high")
        self.assertEqual(dich_gptcli.luu_cai_dat("gemini-9-thu-high", nha="gemini"),
                         {"model": "gemini-9-thu-high", "effort": ""})
        self.assertEqual(dich_gptcli.cai_dat(), {"model": "gpt-6-luna", "effort": "high"})
        dich_gptcli.goi("hi", nha="gemini")
        a = self.argv()[-1]
        self.assertEqual(a[a.index("--model") + 1], "gemini-9-thu-high")
        hl = dich_gptcli.hieu_luc("gemini")
        self.assertEqual((hl["model"], hl["effort"]), ("gemini-9-thu-high", ""))
        self.assertIn("gemini-9-thu-high", dich_gptcli.mo_ta_hieu_luc(nha="gemini"))
        with patch.dict(os.environ, {"OMNI_GEMINI_CLI_MODEL": "gemini-x"}):
            self.assertIn("OMNI_GEMINI_CLI_MODEL", dich_gptcli.hieu_luc("gemini")["model_nguon"])

    def test_danh_sach_model_loc_gemini(self):
        ms = dich_gptcli.danh_sach_model("gemini")
        self.assertEqual([m["slug"] for m in ms], ["gemini-9-thu-high"])
        self.assertEqual(ms[0]["ten"], "Gemini 9 Thu (High)")

    def test_de_bai_dai_di_qua_file(self):
        dai = "Câu rất dài. " * 4000                              # > 30 000 ký tự dòng lệnh
        self.assertEqual(dich_gptcli.goi(dai, nha="gemini"), "Xin chào từ Gemini")
        self.assertIn("de_bai.txt", self.argv()[-1][-1])           # dòng lệnh chỉ còn câu "đọc file"
        self.assertEqual(self.prompts()[-1].strip(), dai.strip())  # nội dung file = đề bài nguyên vẹn

    def test_loi_thanh_gptclierror(self):
        with patch.dict(os.environ, {"STUB_FAIL": "1"}):
            with self.assertRaises(dich_gptcli.GptCliError) as cm:
                dich_gptcli.goi("hi", nha="gemini")
        self.assertIn("Model này không có", str(cm.exception))

    def test_khong_co_agy(self):
        with tempfile.TemporaryDirectory() as trong, \
                patch.dict(os.environ, {"OMNI_GEMINI_CLI": "", "PATH": trong}), \
                patch.object(dich_geminicli, "_thu_muc_ung_vien", lambda: [trong]):
            dich_geminicli._cache.clear()
            with self.assertRaises(dich_gptcli.GptCliError):
                dich_gptcli.kiem_tra("gemini")


class DriverVaSrtTests(_AgyBase):
    def test_driver_chot_nha_luc_tao(self):
        gemini_backend.set_backend("gemini_cli")
        import dich_gemini as g
        logs = []
        drv = g.init_firefox(on_log=logs.append)
        self.assertTrue(g._is_cli(drv))
        self.assertEqual((drv.nha, g._ten_cli(drv)), ("gemini", "Gemini CLI"))
        self.assertTrue(any("Gemini CLI" in l and "agy 7.7.7" in l for l in logs))
        gemini_backend.set_backend("cli")                          # đổi ô giữa chừng
        self.assertEqual(drv.send("hi"), "Xin chào từ Gemini")     # driver vẫn là Gemini
        self.assertTrue(self.prompts()[-1].startswith(dich_gptcli.CLI_HEADER))

    def test_dich_srt_qua_gemini(self):
        partial = os.path.join(self.tmp.name, "x_vi.partial.json")
        vi = dich_srt.translate_cli(TEXTS, partial, batch_chars=20, lang="zh", nha="gemini")
        self.assertEqual(vi, [f"Dich {i}" for i in range(1, len(TEXTS) + 1)])
        self.assertGreater(len(self.prompts()), 1)                 # nhiều lô, mỗi lô một lệnh agy
        self.assertFalse(os.path.exists(self.codex_log))


class TesterTests(_AgyBase):
    def test_tab_thu_gemini(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from myvoice.web import gptcli_test
        t = gptcli_test.GptCliTester("gemini")
        t.start("send", "你好")
        het = time.time() + 30
        while t.running() and time.time() < het:
            time.sleep(0.05)
        s = t.state()
        self.assertEqual(s["error"], "")
        self.assertEqual(s["result"], "Xin chào từ Gemini")
        self.assertEqual(s["info"]["nha"], "gemini")
        self.assertTrue(any("agy 7.7.7" in l for l in s["lines"]))


if __name__ == "__main__":
    unittest.main()
