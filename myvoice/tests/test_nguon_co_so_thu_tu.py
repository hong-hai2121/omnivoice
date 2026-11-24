# -*- coding: utf-8 -*-
"""Link dán có SỐ THỨ TỰ / chữ thừa ("1. https://…") phải ra đúng cái link (20/11/2026).
Trước đó norm_source coi dòng ấy là file local → hạ chữ thường + gắn ổ đĩa, manifest lưu
"d:\\…\\1. https:\\www.bilibili.com\\video\\bv1xrwr6kegj" và tập 194–203 không tải được.
Manifest dùng file tạm — không đụng kịch_bản/ thật."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from myvoice.web import core
from myvoice.web.runners import run_episode

gui = core.gui
LINK = "https://www.bilibili.com/video/BV1XrWR6KEgJ/"


class LamSachNguonTests(unittest.TestCase):
    def test_bo_so_thu_tu_va_chu_thua(self):
        for dong in (f"1. {LINK}", f"10. {LINK}", f"2) {LINK}", f"- {LINK}", f"• {LINK}",
                     f"  3.{LINK}  ", f'"{LINK}"', f"【全文已完结】 {LINK} 复制链接", f"{LINK} xem sau",
                     f"1. {LINK}，"):
            self.assertEqual(gui.lam_sach_nguon(dong), LINK, dong)

    def test_link_tran_giu_nguyen(self):
        for link in (LINK, "https://b23.tv/AbCdEf", "http://example.com/a?x=1&y=B",
                     "https://www.bilibili.com/video/BV12VJr6VEzU/?spm_id_from=333.1387&vd_source=72e"):
            self.assertEqual(gui.lam_sach_nguon(link), link)
            self.assertEqual(gui.norm_source(link), link)

    def test_khoa_manifest_giu_hoa_thuong_cua_ma_bv(self):
        self.assertEqual(gui.norm_source(f"1. {LINK}"), LINK)      # không còn "bv1xrwr6kegj"

    def test_file_local_van_nhu_cu(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "1. Tập Thử.MP3"
            f.write_bytes(b"x")
            self.assertEqual(gui.lam_sach_nguon(f'"{f}"'), str(f))
            self.assertEqual(gui.norm_source(str(f)), os.path.normcase(os.path.abspath(f)))
        self.assertEqual(gui.lam_sach_nguon("khong_co_file.mp3"), "khong_co_file.mp3")
        self.assertEqual(gui.lam_sach_nguon(""), "")


class NapNguonTests(unittest.TestCase):
    def test_link_danh_so_nap_vao_manifest_la_link_that(self):
        with tempfile.TemporaryDirectory() as d:
            mf = Path(d) / "batch_manifest.json"
            with patch.object(gui, "MANIFEST_FILE", mf):
                nap = core.register_sources([f"1. {LINK}", LINK,
                                             "2. https://www.bilibili.com/video/BV1m8WH6vEnc/"])
                m = json.loads(mf.read_text(encoding="utf-8"))
        self.assertEqual(sorted(m), sorted([LINK, "https://www.bilibili.com/video/BV1m8WH6vEnc/"]))
        self.assertEqual(m[LINK]["source"], LINK)
        # "1. link" và "link" là MỘT nguồn → một tập, không cấp hai số.
        self.assertEqual(nap[0][1], nap[1][1])
        self.assertNotEqual(nap[0][1], nap[2][1])
        self.assertEqual(len({v["episode"] for v in m.values()}), 2)

    def test_bo_tai_nhan_link_sach(self):
        with patch.object(core, "load_options", return_value={}), \
                patch.object(run_episode, "_tai_video_bilibili",
                             return_value=("x.mp4", "")) as tai:
            media, why = run_episode._fetch_media(f"1. {LINK}", "194")
        self.assertEqual((media, why), ("x.mp4", ""))
        self.assertEqual(tai.call_args.args[0], LINK)


if __name__ == "__main__":
    unittest.main()
