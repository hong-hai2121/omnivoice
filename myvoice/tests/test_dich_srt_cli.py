# -*- coding: utf-8 -*-
"""GPT CLI (codex exec) làm cách dịch thứ ba — "cli" trong gemini_backend.

Hai đường dùng: (1) myvideo/dich_srt.py --cli: đề bài gửi lại TRỌN GÓI từng lô;
(2) dich_gemini với GptCliDriver (dịch truyện theo đoạn, SEO, 🔁): câu hướng dẫn
đăng ký một lần rồi gửi KÈM MỖI đoạn, đuôi bản dịch trước làm ngữ cảnh, get() = quên.
GPT CLI thật được thay bằng stub .py (OMNI_GPT_CLI trỏ tới file .py → chạy bằng python
hiện tại) — không gọi mạng. Ngoài ra: chọn codex mới nhất trên PATH, tiến độ lưu sau
mỗi lô, dừng sau 3 lô lỗi liên tiếp."""
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "myvideo"))
import dich_srt  # noqa: E402  (tự chèn myvoice/scripts vào sys.path)
import dich_gptcli  # noqa: E402
import gemini_backend  # noqa: E402

# Stub "codex": --version / login status / exec. exec đọc đề bài từ stdin, ghi file -o:
# có dòng B[x] (dịch SRT) → mỗi dòng "B[x] Dich x"; không có (dịch theo đoạn / SEO) →
# một bản dịch dài không chữ Hán. Đề bài được ghi vào STUB_LOG để test soi.
STUB = r'''
import os, sys
args = sys.argv[1:]
if os.environ.get("STUB_LOG"):          # argv của từng lệnh → <STUB_LOG>.args (soi -m / -c)
    with open(os.environ["STUB_LOG"] + ".args", "a", encoding="utf-8") as f:
        f.write(" ".join(args) + "\n")
if args[:1] == ["--version"]:
    print("codex-cli 9.9.9"); sys.exit(0)
if args[:2] == ["login", "status"]:
    print("Logged in using ChatGPT"); sys.exit(0)
if os.environ.get("STUB_FAIL"):
    print("ERROR: {\"detail\":\"model not supported\"}", file=sys.stderr); sys.exit(1)
out = args[args.index("-o") + 1]
prompt = sys.stdin.read()
with open(os.environ["STUB_LOG"], "a", encoding="utf-8") as f:
    f.write(prompt + "\n=====\n")
lines = []
for l in prompt.splitlines():
    if l.startswith("B["):          # "bản dịch" không được còn chữ Hán, kẻo TienDo coi là chưa xong
        ma, _, goc = l.partition(" ")
        lines.append(f"{ma} Dich {ma[2:-1]}")
if not lines:
    n = prompt.count("=====")
    lines = ["Lão Tần gật đầu rồi nói: " + "chúng ta đi thôi, trời đã tối rồi. " * 12
             + f"(lệnh {os.path.getsize(os.environ['STUB_LOG'])})"]
with open(out, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
'''

TEXTS = ["你好老秦", "今天天气很好", "我们去吃饭吧", "他是谁", "快走"]


class CliPromptTests(unittest.TestCase):
    def test_de_bai_luon_mang_du_yeu_cau(self):
        body = "B[3] 我们去吃饭吧\nB[4] 他是谁"
        p = dich_srt.cli_prompt("zh", body, [("你好老秦", "Chào lão Tần")])
        self.assertIn(dich_srt.gemini_prefix("zh"), p)      # yêu cầu dịch gửi lại nguyên vẹn
        self.assertIn("MỘT LẦN", p)                         # lời dặn riêng cho CLI
        self.assertIn("NGỮ CẢNH", p)
        self.assertIn("你好老秦 → Chào lão Tần", p)
        self.assertLess(p.index("NGỮ CẢNH"), p.index(body))  # ngữ cảnh đứng trước lô
        self.assertTrue(p.rstrip().endswith("không markdown."))
        self.assertNotIn("NGỮ CẢNH", dich_srt.cli_prompt("en", "B[1] hi"))
        self.assertIn("TIẾNG ANH CẦN DỊCH", dich_srt.cli_prompt("en", "B[1] hi"))

    def test_ngu_canh_cat_cau_dai(self):
        dai = "x" * 500
        p = dich_srt.cli_prompt("zh", "B[2] y", [(dai, dai)])
        self.assertNotIn(dai, p)
        self.assertIn("x" * (dich_srt.NGU_CANH_MAX_CHARS - 1) + "…", p)


class TienDoTests(unittest.TestCase):
    def test_ngu_canh_lay_cau_ngay_truoc_da_dich(self):
        with tempfile.TemporaryDirectory() as d:
            td = dich_srt.TienDo(TEXTS, os.path.join(d, "p.json"), "zh")
            td.nhan([0, 1, 3], {1: "A", 2: "B", 4: "D"})
            self.assertEqual(td.ngu_canh(2, 4), [("你好老秦", "A"), ("今天天气很好", "B")])
            self.assertEqual(td.ngu_canh(4, 4), [("他是谁", "D")])   # câu 2 chưa dịch → dừng
            self.assertEqual(td.ngu_canh(0), [])
            self.assertEqual(td.ngu_canh(2, 1), [("今天天气很好", "B")])

    def test_nhan_bo_ma_la_va_cau_han(self):
        with tempfile.TemporaryDirectory() as d:
            td = dich_srt.TienDo(TEXTS, os.path.join(d, "p.json"), "zh")
            got = td.nhan([0, 1], {1: "Chào", 2: "今天天气很好", 9: "lạ"})
            self.assertEqual(got, 2)
            self.assertEqual(td.todo(), [1, 2, 3, 4])      # câu 2 còn nguyên Hán = chưa xong
            self.assertNotIn(8, td.done)


class _StubBase(unittest.TestCase):
    """Dựng stub codex + biến môi trường cho mỗi test; xoá cache binary."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.stub = os.path.join(self.tmp.name, "codex_stub.py")
        Path(self.stub).write_text(STUB, encoding="utf-8")
        self.log = os.path.join(self.tmp.name, "prompts.log")
        self.env = patch.dict(os.environ, {"OMNI_GPT_CLI": self.stub, "STUB_LOG": self.log,
                                           "STUB_FAIL": ""})
        self.env.start()
        self.addCleanup(self.env.stop)
        dich_gptcli._cache.clear()
        self.addCleanup(dich_gptcli._cache.clear)
        self.partial = os.path.join(self.tmp.name, "x_vi.partial.json")

    def prompts(self):
        if not os.path.exists(self.log):
            return []
        return [p for p in Path(self.log).read_text(encoding="utf-8").split("=====\n") if p.strip()]


class GptCliStubTests(_StubBase):
    def test_kiem_tra_va_goi(self):
        info = dich_gptcli.kiem_tra()
        self.assertEqual(info["version"], "9.9.9")
        self.assertTrue(info["logged_in"])
        self.assertEqual(dich_gptcli.goi("B[1] 你好"), "B[1] Dich 1")

    def test_translate_cli_gui_lai_de_bai_moi_lo(self):
        # batch_chars nhỏ → nhiều lô; mỗi lô phải tự mang đủ yêu cầu dịch + ngữ cảnh lô trước.
        vi = dich_srt.translate_cli(TEXTS, self.partial, batch_chars=30, lang="zh")
        self.assertEqual(vi, [f"Dich {i + 1}" for i in range(len(TEXTS))])
        self.assertFalse(os.path.exists(self.partial))      # xong trọn vẹn → bỏ file tiến độ
        ps = self.prompts()
        self.assertGreaterEqual(len(ps), 2)
        prefix = dich_srt.gemini_prefix("zh")
        for p in ps:
            self.assertIn(prefix, p)
            self.assertIn("MỘT LẦN", p)
        self.assertNotIn("NGỮ CẢNH", ps[0])
        self.assertIn("NGỮ CẢNH", ps[1])
        self.assertIn("你好老秦 → Dich 1", ps[1])

    def test_translate_cli_dung_sau_3_lo_loi(self):
        os.environ["STUB_FAIL"] = "1"
        with patch.object(dich_srt, "CLI_LOI_LIEN_TIEP", 3):
            vi = dich_srt.translate_cli(TEXTS, self.partial, batch_chars=10, lang="zh")
        self.assertIsNone(vi)                                # không câu nào → không ghi kết quả
        self.assertEqual(self.prompts(), [])                 # stub chết trước khi ghi log

    def test_tiep_tuc_tien_do_cu(self):
        Path(self.partial).write_text(json.dumps({
            "chu_ky": f"{len(TEXTS)}|{sum(len(t) for t in TEXTS)}",
            "cau": {"0": "Đã dịch rồi", "1": "Cũng xong"}}), encoding="utf-8")
        vi = dich_srt.translate_cli(TEXTS, self.partial, batch_chars=5000, lang="zh")
        self.assertEqual(vi[:2], ["Đã dịch rồi", "Cũng xong"])
        self.assertEqual(vi[2:], ["Dich 3", "Dich 4", "Dich 5"])
        self.assertEqual(len(self.prompts()), 1)
        self.assertIn("今天天气很好 → Cũng xong", self.prompts()[0])


class GptCliDriverTests(_StubBase):
    """GptCliDriver thay driver trình duyệt trong dich_gemini."""

    def test_compose_mang_du_moi_lenh_va_get_quen_het(self):
        d = dich_gptcli.GptCliDriver("gpt-cli://x")
        p0 = d.compose("B[1] 你好")
        self.assertTrue(p0.startswith(dich_gptcli.CLI_HEADER))
        self.assertNotIn("ĐOẠN CẦN DỊCH", p0)              # chưa đăng ký hướng dẫn: tin trần (SEO)
        d.set_instruction("HƯỚNG DẪN X")
        d.remember("Câu trước đã dịch xong.")
        p = d.compose("你好", prefix="NHẮC")
        vi_tri = [p.index(s) for s in (dich_gptcli.CLI_HEADER, "HƯỚNG DẪN X", "NHẮC",
                                       "ĐUÔI BẢN DỊCH", "Câu trước đã dịch xong.",
                                       "ĐOẠN CẦN DỊCH:\n你好")]
        self.assertEqual(vi_tri, sorted(vi_tri))
        d.get("https://gemini.google.com/app/abc")
        self.assertEqual(d.current_url, "https://gemini.google.com/app/abc")
        self.assertNotIn("HƯỚNG DẪN X", d.compose("x"))
        self.assertNotIn("ĐUÔI BẢN DỊCH", d.compose("x"))

    def test_duoi_van_ban_lui_ve_dau_cau(self):
        t = "Câu một rất dài. " * 10 + "Câu cuối cùng ở đây."
        duoi = dich_gptcli.duoi_van_ban(t, 60)
        self.assertTrue(duoi.startswith("Câu "))
        self.assertTrue(duoi.endswith("Câu cuối cùng ở đây."))
        self.assertLessEqual(len(duoi), 60)

    def test_dich_gemini_re_nhanh_cli(self):
        import dich_gemini as g
        quiet = lambda *_a, **_k: None   # noqa: E731
        with patch.dict(os.environ, {"OMNI_GEMINI_BACKEND": "cli"}):
            drv = g.init_firefox(on_log=quiet)
            self.assertTrue(getattr(drv, "is_gpt_cli", False))
            self.assertTrue(g.is_driver_alive(drv))
            self.assertEqual(g._get_responses(drv), [])
            self.assertIs(g.restart_firefox(drv, on_log=quiet), drv)
            # Câu hướng dẫn: KHÔNG tốn một lệnh "sẵn sàng chưa", chỉ đăng ký bản CLI.
            g.send_prefix_to_gemini(drv, g.load_prefix(), on_log=quiet)
            self.assertEqual(self.prompts(), [])
            self.assertEqual(drv.instruction, g.TRANSLATE_PREFIX_CLI.strip())
            self.assertNotIn("sẵn sàng chưa", drv.instruction)
            self.assertNotIn("tin nhắn tiếp theo", drv.instruction)
            self.assertIn("ĐOẠN CẦN DỊCH", drv.instruction)
            self.assertNotIn(g.TRANSLATE_RULES.strip(), drv.instruction)   # bản CLI viết riêng, ngắn
            # Dịch theo đoạn qua đúng vòng lặp sẵn có của dich_gemini.
            drv.get(g.GEMINI_URL)
            chunks = ["你好老秦。今天天气很好。", "我们去吃饭吧。他是谁？"]
            res = g.send_chunks_to_gemini(chunks, prefix=g.load_prefix(), on_log=quiet,
                                          driver=drv, keep_open=True)
        self.assertEqual(len(res), 2)
        self.assertTrue(all(r.startswith("Lão Tần") for r in res))
        ps = self.prompts()
        self.assertEqual(len(ps), 2)                         # mỗi đoạn đúng một lệnh
        for p, chunk in zip(ps, chunks):
            self.assertIn(dich_gptcli.CLI_HEADER, p)
            self.assertIn(g.TRANSLATE_PREFIX_CLI.strip(), p)   # hướng dẫn gửi lại kèm MỖI đoạn
            self.assertIn("ĐOẠN CẦN DỊCH:\n" + g.FICTION_TAG.strip() + "\n" + chunk, p)
        self.assertNotIn("ĐUÔI BẢN DỊCH", ps[0])
        self.assertIn("ĐUÔI BẢN DỊCH", ps[1])               # đoạn 2 mang đuôi bản dịch đoạn 1
        self.assertIn("trời đã tối rồi.", ps[1])

    def test_prefix_cli_ngan_rieng_du_y(self):
        """Câu hướng dẫn CLI gửi lại KÈM MỖI đoạn nên phải ngắn (≤ 1/2 bản chat) nhưng
        vẫn giữ các ý quyết định chất lượng; không có câu chỉ hợp với chat."""
        import dich_gemini as g
        cli, chat = g.TRANSLATE_PREFIX_CLI, g.TRANSLATE_PREFIX
        self.assertLess(len(cli), len(chat) / 2)
        for y in ("ĐOẠN CẦN DỊCH", "Chỉ in bản dịch", "nói tránh", "không từ chối",
                  "nhận diện giọng nói", "xưng hô thống nhất", "Mimi audio",
                  "nhắc lại đoạn mở đầu", g._FICTION_TAG_NGAN):
            self.assertIn(y, cli)
        for x in ("sẵn sàng chưa", "tin nhắn tiếp theo"):
            self.assertNotIn(x, cli)
        self.assertLess(len(dich_gptcli.CLI_HEADER), 220)

    def test_cli_instruction_bo_cau_hoi_san_sang(self):
        import dich_gemini as g
        self.assertEqual(g.cli_instruction(g.TRANSLATE_PREFIX), g.TRANSLATE_PREFIX_CLI.strip())
        self.assertEqual(g.cli_instruction("Dịch giúp tôi. Bạn sẵn sàng chưa?"), "Dịch giúp tôi.")
        self.assertEqual(g.cli_instruction(""), "")

    def test_seo_kieu_mot_tin_khong_hướng_dan(self):
        import dich_gemini as g
        quiet = lambda *_a, **_k: None   # noqa: E731
        d = dich_gptcli.GptCliDriver()
        ans = g.send_to_gemini(d, "Nội dung truyện", prefix="YÊU CẦU SEO", on_log=quiet)
        self.assertTrue(ans.startswith("Lão Tần"))
        p = self.prompts()[0]
        self.assertIn("YÊU CẦU SEO\n\nNội dung truyện", p)
        self.assertNotIn("ĐOẠN CẦN DỊCH", p)


class BackendTests(unittest.TestCase):
    def test_cli_la_lua_chon_hop_le(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(gemini_backend, "PIPE_FILE", Path(tmp) / "pipe.json"), \
                patch.dict(os.environ, {"OMNI_GEMINI_BACKEND": ""}):
            os.environ.pop("OMNI_GEMINI_BACKEND")
            gemini_backend.PIPE_FILE.write_text('{"model": "medium"}', encoding="utf-8")
            self.assertEqual(gemini_backend.set_backend("cli"), "cli")
            self.assertEqual(gemini_backend.get_backend(), "cli")
            self.assertEqual(gemini_backend.saved_backend(), "cli")
            self.assertEqual(gemini_backend.browser_label(), "GPT CLI (Codex)")
            self.assertIn("codex login", gemini_backend.browser_hint())
            data = json.loads(gemini_backend.PIPE_FILE.read_text(encoding="utf-8"))
            self.assertEqual(data["model"], "medium")       # khoá khác giữ nguyên
            self.assertEqual(gemini_backend.set_backend("bogus"), "extension")
            with patch.dict(os.environ, {"OMNI_GEMINI_BACKEND": "cli"}):
                self.assertEqual(gemini_backend.get_backend(), "cli")


class CaiDatTests(_StubBase):
    """Model / mức cố gắng lưu ở tab 🤖 (taogiong_pipeline.json) → MỌI lệnh codex exec mang
    -m / -c model_reasoning_effort; biến môi trường thắng ô; trống thì theo config.toml."""

    def setUp(self):
        super().setUp()
        self.pipe = Path(self.tmp.name) / "pipe.json"
        self.pipe.write_text('{"model": "medium", "gemini_backend": "cli"}', encoding="utf-8")
        for p in (patch.object(gemini_backend, "PIPE_FILE", self.pipe),
                  patch.dict(os.environ, {"OMNI_GPT_CLI_MODEL": "", "OMNI_GPT_CLI_EFFORT": "",
                                          "CODEX_HOME": self.tmp.name})):
            p.start()
            self.addCleanup(p.stop)

    def args(self):
        f = Path(self.log + ".args")
        return f.read_text(encoding="utf-8").splitlines() if f.exists() else []

    def test_luu_va_doc_giu_khoa_khac(self):
        self.assertEqual(dich_gptcli.cai_dat(), {"model": "", "effort": ""})
        self.assertEqual(dich_gptcli.luu_cai_dat("gpt-6-luna", "HIGH"),
                         {"model": "gpt-6-luna", "effort": "high"})
        d = json.loads(self.pipe.read_text(encoding="utf-8"))
        self.assertEqual((d["model"], d["gemini_backend"]), ("medium", "cli"))   # khoá khác giữ nguyên
        self.assertEqual(dich_gptcli.luu_cai_dat(effort="bogus")["effort"], "")  # mức lạ → mặc định
        self.assertEqual(dich_gptcli.cai_dat()["model"], "gpt-6-luna")           # None = không đổi

    def test_goi_mang_model_va_muc_da_luu(self):
        dich_gptcli.luu_cai_dat("gpt-6-luna", "high")
        dich_gptcli.goi("hi")
        a = self.args()[-1]
        self.assertIn("-m gpt-6-luna", a)
        self.assertIn('-c model_reasoning_effort="high"', a)
        dich_gptcli.luu_cai_dat("", "")
        dich_gptcli.goi("hi")
        a = self.args()[-1]
        self.assertNotIn("-m ", a)
        self.assertNotIn("model_reasoning_effort", a)

    def test_bien_moi_truong_thang_o_cai_dat(self):
        dich_gptcli.luu_cai_dat("gpt-6-luna", "high")
        with patch.dict(os.environ, {"OMNI_GPT_CLI_MODEL": "gpt-x", "OMNI_GPT_CLI_EFFORT": "low"}):
            hl = dich_gptcli.hieu_luc()
            self.assertEqual((hl["model"], hl["effort"]), ("gpt-x", "low"))
            self.assertIn("OMNI_GPT_CLI_MODEL", hl["model_nguon"])
            dich_gptcli.goi("hi")
            self.assertIn("-m gpt-x", self.args()[-1])
        hl = dich_gptcli.hieu_luc()
        self.assertEqual(hl["model"], "gpt-6-luna")
        self.assertIn("ô cài đặt", hl["model_nguon"])

    def test_config_toml_va_models_cache(self):
        home = Path(self.tmp.name)
        (home / "config.toml").write_text(
            'model = "gpt-6.1-sol"\nmodel_reasoning_effort = "medium"\n'
            '[windows]\nsandbox = "unelevated"\n', encoding="utf-8")
        (home / "models_cache.json").write_text(json.dumps({"models": [
            {"slug": "gpt-6-luna", "display_name": "GPT-6-Luna", "description": "Fast",
             "visibility": "list", "priority": 5, "default_reasoning_level": "medium",
             "supported_reasoning_levels": [{"effort": "low"}, {"effort": "medium"},
                                            {"effort": "ultra"}]},
            {"slug": "gpt-6.1-sol", "display_name": "GPT-6.1-Sol", "visibility": "list",
             "priority": 1, "supported_reasoning_levels": []},
            {"slug": "gpt-reserve", "visibility": "hide", "priority": 4}]}), encoding="utf-8")
        self.assertEqual(dich_gptcli.config_mac_dinh(), {"model": "gpt-6.1-sol", "effort": "medium"})
        ms = dich_gptcli.danh_sach_model()
        self.assertEqual([m["slug"] for m in ms], ["gpt-6.1-sol", "gpt-6-luna"])  # theo priority, bỏ hide
        self.assertEqual(ms[1]["muc"], ["low", "medium"])                           # "ultra" không đưa vào
        hl = dich_gptcli.hieu_luc()                                                 # chưa lưu gì → config.toml
        self.assertEqual((hl["model"], hl["effort"]), ("gpt-6.1-sol", "medium"))
        self.assertIn("config.toml", hl["model_nguon"])
        self.assertIn("gpt-6.1-sol", dich_gptcli.mo_ta_hieu_luc())

    def test_khong_co_file_trong_codex_home(self):
        self.assertEqual(dich_gptcli.config_mac_dinh(), {"model": "", "effort": ""})
        self.assertEqual(dich_gptcli.danh_sach_model(), [])
        self.assertEqual(dich_gptcli.hieu_luc()["model_nguon"], "codex tự chọn")


class TimCodexTests(unittest.TestCase):
    """Quét PATH, lấy bản MỚI NHẤT (máy có codex 0.84 đứng trước 0.163 trong PATH)."""

    def _stub_dir(self, root, name, version):
        d = Path(root) / name
        d.mkdir()
        if os.name == "nt":
            (d / "codex.cmd").write_text(f"@echo codex-cli {version}\r\n", encoding="ascii")
        else:
            p = d / "codex"
            p.write_text(f"#!/bin/sh\necho codex-cli {version}\n", encoding="ascii")
            p.chmod(p.stat().st_mode | stat.S_IEXEC)
        return str(d)

    def test_chon_ban_moi_nhat_tren_path(self):
        with tempfile.TemporaryDirectory() as root:
            cu = self._stub_dir(root, "cu", "0.84.0")
            moi = self._stub_dir(root, "moi", "0.163.0")
            with patch.dict(os.environ, {"PATH": os.pathsep.join([cu, moi]), "OMNI_GPT_CLI": ""}):
                dich_gptcli._cache.clear()
                path, ver = dich_gptcli.tim_codex()
                dich_gptcli._cache.clear()
            self.assertEqual(ver, (0, 163, 0))
            self.assertEqual(os.path.dirname(path), moi)

    def test_khong_co_codex(self):
        with tempfile.TemporaryDirectory() as root:
            with patch.dict(os.environ, {"PATH": root, "OMNI_GPT_CLI": ""}):
                dich_gptcli._cache.clear()
                with self.assertRaises(dich_gptcli.GptCliError):
                    dich_gptcli.tim_codex()
                dich_gptcli._cache.clear()


if __name__ == "__main__":
    unittest.main()
