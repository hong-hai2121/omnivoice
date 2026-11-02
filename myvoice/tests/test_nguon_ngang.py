# -*- coding: utf-8 -*-
"""Ô "Nguồn ngang" tick được NHIỀU thư mục con videongang/ (01/11/2026): chuẩn hoá
giá trị lưu (chuỗi cũ 1 tên / list), đổi ra thư mục hợp lệ, gom clip để xáo chung, và
server web lưu cụm checkbox. Không chạy ffmpeg, không mở cửa sổ Tk."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from starlette.datastructures import FormData

from myvoice.web import core, server

gui = core.gui
import video_khung  # noqa: E402  (sys.path đã có scripts/ nhờ core)

ALL = gui.NGANG_SOURCE_ALL


def _kho(root: Path) -> None:
    """Kho giả: nauan/ (2 clip), vlog/ (1 clip), trong/ (không có clip), file lẻ ở gốc không có."""
    (root / "nauan").mkdir()
    (root / "nauan" / "a.mp4").write_bytes(b"0")
    (root / "nauan" / "b.mp4").write_bytes(b"0")
    (root / "vlog").mkdir()
    (root / "vlog" / "c.mp4").write_bytes(b"0")
    (root / "trong").mkdir()
    (root / "trong" / "ghichu.txt").write_text("x", encoding="utf-8")


class NgangSourceListTests(unittest.TestCase):
    def test_rong_va_tat_ca(self):
        self.assertEqual(gui.ngang_source_list(None), [])
        self.assertEqual(gui.ngang_source_list(""), [])
        self.assertEqual(gui.ngang_source_list(ALL), [])
        self.assertEqual(gui.ngang_source_list([ALL, "", "  "]), [])

    def test_chuoi_cu_mot_ten(self):
        self.assertEqual(gui.ngang_source_list("nauan"), ["nauan"])
        self.assertEqual(gui.ngang_source_list("  nauan "), ["nauan"])

    def test_chuoi_nhieu_ten_noi_gach_dung(self):
        self.assertEqual(gui.ngang_source_list("nauan|vlog| nauan "), ["nauan", "vlog"])

    def test_list_bo_trong_trung_giu_thu_tu(self):
        self.assertEqual(gui.ngang_source_list(["vlog", "", ALL, "nauan", "vlog"]),
                         ["vlog", "nauan"])
        self.assertEqual(gui.ngang_source_list(("thiennhien",)), ["thiennhien"])

    def test_ten_hien_tren_o(self):
        self.assertEqual(gui.ten_ngang_source([]), ALL)
        self.assertEqual(gui.ten_ngang_source("nauan"), "nauan")
        self.assertEqual(gui.ten_ngang_source(["nauan", "vlog"]), "nauan + vlog")
        self.assertEqual(gui.ten_ngang_source(["a", "b", "c", "d"]), "a + b +2")


class ResolveNgangSourceTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        _kho(self.root)
        p = patch.object(gui, "VIDEONGANG_DIR", self.root)
        p.start()
        self.addCleanup(p.stop)
        self.logs: list[str] = []

    def test_list_sources_chi_thu_muc_co_clip(self):
        self.assertEqual(gui.list_ngang_sources(), ["nauan", "vlog"])

    def test_tat_ca_va_rong_tra_none(self):
        self.assertIsNone(gui.resolve_ngang_source(ALL, log=self.logs.append))
        self.assertIsNone(gui.resolve_ngang_source(None, log=self.logs.append))
        self.assertIsNone(gui.resolve_ngang_source([], log=self.logs.append))
        self.assertEqual(self.logs, [])

    def test_chuoi_cu_mot_ten(self):
        self.assertEqual(gui.resolve_ngang_source("nauan", log=self.logs.append),
                         [self.root / "nauan"])

    def test_nhieu_thu_muc_giu_thu_tu(self):
        self.assertEqual(gui.resolve_ngang_source(["vlog", "nauan"], log=self.logs.append),
                         [self.root / "vlog", self.root / "nauan"])
        self.assertEqual(self.logs, [])

    def test_bo_thu_muc_hong_giu_thu_muc_tot(self):
        out = gui.resolve_ngang_source(["nauan", "trong", "khongco"], log=self.logs.append)
        self.assertEqual(out, [self.root / "nauan"])
        self.assertEqual(len(self.logs), 2)
        self.assertIn("'trong'", self.logs[0])
        self.assertIn("'khongco'", self.logs[1])

    def test_hong_het_thi_ve_ca_kho(self):
        self.assertIsNone(gui.resolve_ngang_source(["trong"], log=self.logs.append))
        self.assertTrue(any("cả kho" in m for m in self.logs))


class GomClipKhoTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        _kho(self.root)
        p = patch.object(video_khung, "VIDEO_DIR", self.root)
        p.start()
        self.addCleanup(p.stop)
        self.logs: list[str] = []

    def test_none_gom_moi_thu_muc_con_khi_goc_rong(self):
        videos, ten = video_khung.gom_clip_kho(None, self.logs.append)
        self.assertEqual([v.name for v in videos], ["a.mp4", "b.mp4", "c.mp4"])
        self.assertEqual(ten, str(self.root))
        self.assertIn("tất cả thư mục con (3 clip)", self.logs[0])

    def test_mot_thu_muc(self):
        videos, ten = video_khung.gom_clip_kho(self.root / "nauan", self.logs.append)
        self.assertEqual([v.name for v in videos], ["a.mp4", "b.mp4"])
        self.assertEqual(ten, "nauan/")
        # chuỗi đường dẫn cũng nhận
        videos2, _ = video_khung.gom_clip_kho(str(self.root / "vlog"), self.logs.append)
        self.assertEqual([v.name for v in videos2], ["c.mp4"])

    def test_nhieu_thu_muc_gop_clip(self):
        videos, ten = video_khung.gom_clip_kho(
            [self.root / "nauan", self.root / "vlog"], self.logs.append)
        self.assertEqual(sorted(v.name for v in videos), ["a.mp4", "b.mp4", "c.mp4"])
        self.assertEqual(ten, "nauan/ + vlog/")
        self.assertIn("nauan/ + vlog/ (3 clip)", self.logs[0])

    def test_thu_muc_khong_clip_bao_loi(self):
        with self.assertRaises(RuntimeError) as cm:
            video_khung.gom_clip_kho([self.root / "trong"], self.logs.append)
        self.assertIn("trong/", str(cm.exception))

    def test_playlist_xao_chung_moi_thu_muc(self):
        """Clip của mọi thư mục đã tick đều có thể xuất hiện khi ghép đủ dài."""
        videos, _ = video_khung.gom_clip_kho([self.root / "nauan", self.root / "vlog"])
        durations = {v: 10.0 for v in videos}
        seq, total = video_khung.build_playlist(videos, durations, 60.0)
        self.assertGreaterEqual(total, 60.0)
        self.assertEqual(set(seq), set(videos))


class WebLuuNguonNgangTests(unittest.TestCase):
    def _luu(self, form: FormData, cu: dict) -> dict:
        saved: dict = {}
        with patch.object(core, "load_options", return_value=dict(cu)), \
             patch.object(core, "save_options", side_effect=saved.update):
            server._save_opts_from_form(form)
        return saved

    def test_tick_nhieu_luu_list(self):
        saved = self._luu(FormData([("ngang_source", ""), ("ngang_source", "nauan"),
                                    ("ngang_source", "vlog")]), {"ngang_source": "nauan"})
        self.assertEqual(saved["ngang_source"], ["nauan", "vlog"])

    def test_bo_tick_het_la_ca_kho(self):
        saved = self._luu(FormData([("ngang_source", "")]), {"ngang_source": ["nauan"]})
        self.assertEqual(saved["ngang_source"], [])

    def test_form_khong_co_o_thi_giu_nguyen(self):
        saved = self._luu(FormData([("ngang_speed", "1.2")]), {"ngang_source": "nauan"})
        self.assertEqual(saved["ngang_source"], "nauan")
        self.assertEqual(saved["ngang_speed"], "1.2")

    def test_tts_settings_dua_list_cho_runner(self):
        with patch.object(core, "load_options",
                          return_value={"ngang_source": "nauan|vlog", "effect": ""}), \
             patch.object(core, "load_web_settings", return_value={"mode": "default"}):
            ts, err = core.tts_settings()
        self.assertIsNotNone(ts, err)
        self.assertEqual(ts["ngang_source"], ["nauan", "vlog"])

    def test_template_bien_dich_duoc(self):
        tpl = server.templates.env.get_template("_form_voice.html")
        self.assertIsNotNone(tpl)


if __name__ == "__main__":
    unittest.main()
