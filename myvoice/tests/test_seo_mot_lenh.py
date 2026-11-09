# -*- coding: utf-8 -*-
"""SEO YouTube bằng MỘT câu lệnh (01/11/2026): đề bài SEO tự chứa, đoạn trích đứng ở
CUỐI tin sau mốc "ĐOẠN TRÍCH TRUYỆN:" — Gemini (một tin) hay GPT CLI (một lệnh codex
exec) đều nhận trọn gói, không còn kiểu "ra đề trước, gửi đoạn sau". codex thật thay
bằng stub .py (OMNI_GPT_CLI trỏ tới file .py), không gọi mạng, không mở trình duyệt."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
for _p in ("myvoice/YOUTUBE", "myvoice/scripts"):
    sys.path.insert(0, str(REPO / _p))
import dich_gemini as g  # noqa: E402
import dich_gptcli  # noqa: E402
import seo_youtube_gemini as seo  # noqa: E402
from seo_docx_parser import parse_seo_docx  # noqa: E402

TITLE = "Màn Kịch Của Lão Tần Khiến Cả Làng Sửng Sốt | Mimi audio"
# Câu trả lời SEO mẫu đúng định dạng đề bài yêu cầu (như GPT CLI trả cho tập 155/156).
SEO_ANSWER = f"""---

## 🎯 BƯỚC 1: CHỌN TIÊU ĐỀ VIDEO

1. Sự Thật Đằng Sau... Bữa Cơm Định Mệnh Của Lão Tần | Mimi audio
2. {TITLE}
3. Câu Chuyện Đời Lão Tần Và Sự Thật Đau Đớn Sau Nhiều Năm... | Mimi audio
4. Truyện Tâm Lý Xã Hội Về Luật Nhân Quả... Lão Tần Trả Giá | Mimi audio
5. Bí Mật Sau Cuộc Đời... Lão Tần Và Đứa Con Thất Lạc | Mimi audio

**🏆 Tiêu đề tốt nhất được chọn:**

> {TITLE}

---

## 🏷️ BƯỚC 2: VIẾT THẺ TAG YOUTUBE

```text
truyện audio, truyện đêm khuya, truyện tâm lý xã hội, Mimi audio, Lão Tần, bữa cơm định mệnh
```

---

## 📝 BƯỚC 3: VIẾT MÔ TẢ VIDEO CHUẨN SEO

#MimiAudio #TruyenAudio #TruyenTamLyXaHoi #TruyenKichTinh #Audio
{TITLE}
Lão Tần gật đầu nhận lời mời rồi phát hiện bữa cơm là một cái bẫy.
Người ngồi đối diện chính là đứa con ông bỏ rơi hai mươi năm trước.
👉 Đăng ký Mimi audio và bật chuông để nghe truyện mới mỗi ngày.
"""

# Stub codex: --version / login status / exec. exec ghi đề bài vào STUB_LOG rồi trả
# SEO_ANSWER (đọc từ file STUB_ANSWER) — hoặc lỗi nếu STUB_FAIL.
STUB = r'''
import os, sys
args = sys.argv[1:]
if args[:1] == ["--version"]:
    print("codex-cli 9.9.9"); sys.exit(0)
if args[:2] == ["login", "status"]:
    print("Logged in using ChatGPT"); sys.exit(0)
prompt = sys.stdin.read()
with open(os.environ["STUB_LOG"], "a", encoding="utf-8") as f:
    f.write(prompt + "\n=====\n")
if os.environ.get("STUB_FAIL"):
    print("ERROR: stream disconnected", file=sys.stderr); sys.exit(1)
out = args[args.index("-o") + 1]
with open(os.environ["STUB_ANSWER"], encoding="utf-8") as f:
    ans = f.read()
with open(out, "w", encoding="utf-8") as f:
    f.write(ans)
'''

EXCERPT = ("Lão Tần gật đầu rồi nói: chúng ta đi thôi, trời đã tối rồi. Bữa cơm hôm ấy "
           "đổi cả đời ông.")
quiet = lambda *_a, **_k: None   # noqa: E731


def _make_input_docx(path):
    from docx import Document
    doc = Document()
    doc.add_heading("Kết quả dịch từ Gemini", level=1)
    doc.add_heading("ĐOẠN 1", level=2)
    doc.add_paragraph(EXCERPT)
    doc.add_heading("ĐOẠN 2", level=2)
    doc.add_paragraph("Đoạn hai không được gửi đi làm SEO.")
    doc.save(str(path))


class DeBaiTests(unittest.TestCase):
    def test_de_bai_la_mot_lenh_tu_chua(self):
        p = seo.SEO_PROMPT
        self.assertTrue(p.rstrip().endswith(seo.EXCERPT_MARK))      # đoạn trích nối ngay sau
        self.assertIn("CUỐI tin này", p)
        self.assertIn("MỘT câu trả lời", p)
        for cu in ("tôi sẽ gửi", "sẵn sàng", "tin nhắn tiếp theo", "đầu tiên, hãy"):
            self.assertNotIn(cu, p)                                 # hết kiểu hai lượt
        for buoc in ("BƯỚC 1: CHỌN TIÊU ĐỀ VIDEO", "BƯỚC 2: VIẾT THẺ TAG YOUTUBE",
                     "BƯỚC 3: VIẾT MÔ TẢ VIDEO CHUẨN SEO"):
            self.assertIn(buoc, p)
        self.assertNotIn("BƯỚC 4", p)
        # Mốc mà seo_docx_parser tìm theo từ khoá vẫn được yêu cầu trong đầu ra.
        for moc in ("CHỌN TIÊU ĐỀ", "THẺ TAG", "MÔ TẢ VIDEO", "Tiêu đề tốt nhất được chọn"):
            self.assertIn(moc, p)

    def test_excerpt_body_them_moc_khi_de_bai_tu_dat_thieu(self):
        self.assertEqual(seo.excerpt_body("  abc "), "abc")        # đề bài mặc định đã có mốc
        with patch.object(seo, "SEO_PROMPT", "Đề bài riêng không mốc"):
            self.assertEqual(seo.excerpt_body("abc"), f"{seo.EXCERPT_MARK}\nabc")

    def test_bo_rao_ngoai_giu_rao_trong(self):
        boc = "```markdown\n" + SEO_ANSWER + "\n```"
        self.assertEqual(seo.strip_outer_fence(boc), SEO_ANSWER.strip())
        self.assertEqual(seo.strip_outer_fence(SEO_ANSWER), SEO_ANSWER.strip())
        self.assertIn("```text", seo.strip_outer_fence(boc))         # khối thẻ tag còn nguyên
        self.assertEqual(seo.strip_outer_fence(None), "")

    def test_mau_tra_loi_qua_duoc_chot_dang(self):
        self.assertTrue(seo._looks_like_seo(SEO_ANSWER))
        self.assertFalse(seo._looks_like_seo("Vâng, bạn gửi đoạn trích đi, tôi làm ngay."))


class _StubBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.stub = os.path.join(self.tmp.name, "codex_stub.py")
        Path(self.stub).write_text(STUB, encoding="utf-8")
        self.log = os.path.join(self.tmp.name, "prompts.log")
        self.answer = os.path.join(self.tmp.name, "tra_loi.txt")
        Path(self.answer).write_text(SEO_ANSWER, encoding="utf-8")
        self.env = patch.dict(os.environ, {"OMNI_GPT_CLI": self.stub, "STUB_LOG": self.log,
                                           "STUB_ANSWER": self.answer, "STUB_FAIL": "",
                                           "OMNI_GEMINI_BACKEND": "cli"})
        self.env.start()
        self.addCleanup(self.env.stop)
        dich_gptcli._cache.clear()
        self.addCleanup(dich_gptcli._cache.clear)
        self.inp = Path(self.tmp.name) / "gemini_result.docx"
        self.out = Path(self.tmp.name) / "seoYoutube.docx"
        _make_input_docx(self.inp)
        self.sleeps = []
        sl = patch.object(seo.time, "sleep", lambda s: self.sleeps.append(s))
        sl.start()
        self.addCleanup(sl.stop)

    def prompts(self):
        if not os.path.exists(self.log):
            return []
        return [p for p in Path(self.log).read_text(encoding="utf-8").split("=====\n") if p.strip()]


class GptCliTests(_StubBase):
    def test_seo_la_mot_lenh_duy_nhat(self):
        # Driver DÙNG CHUNG với bước dịch: còn đọng câu hướng dẫn dịch + đuôi bản dịch.
        drv = g.init_firefox(on_log=quiet)
        self.assertTrue(getattr(drv, "is_gpt_cli", False))
        drv.set_instruction(g.TRANSLATE_PREFIX_CLI)
        drv.remember("Đuôi bản dịch đoạn trước còn đọng.")

        ans = seo.run(str(self.inp), str(self.out), log=quiet, driver=drv, keep_open=True)

        self.assertIn("BƯỚC 1: CHỌN TIÊU ĐỀ VIDEO", ans)
        ps = self.prompts()
        self.assertEqual(len(ps), 1)                                  # đúng MỘT lệnh codex exec
        p = ps[0]
        self.assertTrue(p.startswith(dich_gptcli.CLI_HEADER))
        self.assertIn(seo.SEO_PROMPT.strip(), p)
        self.assertTrue(p.rstrip().endswith(seo.EXCERPT_MARK + "\n\n" + EXCERPT))   # đoạn ở cuối
        self.assertEqual(p.count(seo.EXCERPT_MARK), 2)                # một trong đề bài, một mốc thật
        for rac in ("ĐOẠN CẦN DỊCH", "ĐUÔI BẢN DỊCH", "Đuôi bản dịch đoạn trước",
                    g.TRANSLATE_PREFIX_CLI.strip(), "Đoạn hai không được gửi"):
            self.assertNotIn(rac, p)                                  # không lẫn đồ của bước dịch
        self.assertEqual(self.sleeps, [])                             # không chờ "mở chat"
        self.assertEqual(drv.instruction, "")                         # get() đã xoá hướng dẫn dịch

        got = parse_seo_docx(self.out)
        self.assertEqual(got["title"], TITLE)
        self.assertIn("Lão Tần", got["tags"])
        self.assertTrue(got["description"].startswith("#MimiAudio"))
        self.assertTrue(got["description"].endswith("mỗi ngày."))
        self.assertFalse(got.get("issues"))

    def test_cli_loi_thi_khong_mo_firefox_va_giu_file_rong(self):
        drv = g.init_firefox(on_log=quiet)
        with patch.dict(os.environ, {"STUB_FAIL": "1"}), \
                patch.object(seo.g, "init_firefox") as mo:
            ans = seo.run(str(self.inp), str(self.out), log=quiet, driver=drv,
                          keep_open=True, attempts=2)
        self.assertEqual(ans, "")
        mo.assert_not_called()                                        # CLI không có dự phòng Firefox
        self.assertGreaterEqual(len(self.prompts()), 2)               # có gửi lại, mỗi lượt một lệnh
        got = parse_seo_docx(self.out)
        self.assertEqual((got["title"], got["tags"], got["description"]), ("", [], ""))

    def test_gemini_cung_mot_tin_de_bai_truoc_doan_sau(self):
        class FakeExtension:
            is_chrome_extension = True
            current_url = "https://gemini.google.com/app"

            def get(self, url):
                self.current_url = url

            def responses(self, _sel):
                return []

        drv = FakeExtension()
        with patch.object(seo.g, "send_to_gemini", return_value=SEO_ANSWER) as send:
            ans = seo.run(str(self.inp), str(self.out), log=quiet, driver=drv, keep_open=True)
        self.assertIn(TITLE, ans)
        send.assert_called_once()
        args, kwargs = send.call_args
        self.assertIs(args[0], drv)
        self.assertEqual(args[1], EXCERPT)                            # đoạn trích = nội dung tin
        self.assertEqual(kwargs["prefix"], seo.SEO_PROMPT)            # đề bài kết bằng mốc, đứng trước
        self.assertEqual(self.prompts(), [])                          # không đụng codex
        self.assertEqual(parse_seo_docx(self.out)["title"], TITLE)


if __name__ == "__main__":
    unittest.main()
