# -*- coding: utf-8 -*-
"""Ghép random NHỚ clip đã lấy (18/11/2026): lần dựng sau không bốc trùng clip các lần
trước, lấy hết nguồn đang chọn thì reset, thêm thư mục / video mới thì tính là chưa lấy.
Sổ dùng file tạm (không đụng scripts/clip_da_lay.json thật); không chạy ffmpeg, không mở Tk."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from myvoice.web import core, server

gui = core.gui
import clip_da_lay as cdl  # noqa: E402  (sys.path đã có scripts/ nhờ core)
import video_khung  # noqa: E402


class _Kho(unittest.TestCase):
    """Kho giả: nauan/ 6 clip, vlog/ 4 clip, mỗi clip 10 giây; sổ nằm trong thư mục tạm."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "videongang"
        for ten, n in (("nauan", 6), ("vlog", 4)):
            (self.root / ten).mkdir(parents=True)
            for i in range(n):
                (self.root / ten / f"{ten}{i}.mp4").write_bytes(b"0")
        for mod, attr, val in ((cdl, "SO_FILE", Path(tmp.name) / "so.json"),
                               (gui, "VIDEONGANG_DIR", self.root),
                               (video_khung, "VIDEO_DIR", self.root)):
            p = patch.object(mod, attr, val)
            p.start()
            self.addCleanup(p.stop)

    def clips(self, *ten):
        return sorted(v for t in ten for v in (self.root / t).glob("*.mp4"))

    def dung(self, videos, giay, xong=True):
        """Một lần "dựng video" dài `giay` giây → (các clip đã ghép, dòng nhật ký)."""
        seq, total, ghi, mo_ta = cdl.chon_co_nho(videos, {v: 10.0 for v in videos}, giay)
        self.assertGreaterEqual(total, giay)
        if xong:
            ghi(self.fail)          # ghi sổ lỗi là hỏng test
        return seq, mo_ta


class ChonTests(_Kho):
    def test_khong_so_thi_nhu_xao_thuong(self):
        v = self.clips("nauan")
        seq, total, moi, so_reset = cdl.chon(v, {x: 10.0 for x in v}, 60.0)
        self.assertEqual((sorted(seq), total, moi, so_reset), (v, 60.0, set(v), 0))

    def test_bo_qua_clip_da_lay(self):
        v = self.clips("nauan")
        seq, _, moi, so_reset = cdl.chon(v, {x: 10.0 for x in v}, 30.0, da_lay=v[:3])
        self.assertEqual((sorted(seq), moi, so_reset), (v[3:], set(v[3:]), 0))

    def test_het_clip_chua_lay_thi_reset(self):
        v = self.clips("nauan")
        seq, _, moi, so_reset = cdl.chon(v, {x: 10.0 for x in v}, 40.0, da_lay=v[:4])
        self.assertEqual(so_reset, 1)
        self.assertEqual(set(seq[:2]), set(v[4:]))        # 2 clip chưa lấy đi trước
        self.assertEqual(moi, set(seq[2:]))               # dấu mới chỉ tính từ lúc reset
        self.assertEqual(len(set(seq)), 4)                # chưa hết kho thì không lặp trong video

    def test_da_lay_het_tu_truoc_thi_reset_ngay(self):
        v = self.clips("vlog")
        seq, _, moi, so_reset = cdl.chon(v, {x: 10.0 for x in v}, 20.0, da_lay=v)
        self.assertEqual((so_reset, moi, len(set(seq))), (1, set(seq), 2))

    def test_kho_ngan_hon_audio_khong_phat_lien_mot_clip(self):
        v = self.clips("vlog")
        for _ in range(30):
            seq, *_ = cdl.chon(v, {x: 10.0 for x in v}, 200.0)
            self.assertEqual(len(seq), 20)
            self.assertTrue(all(a != b for a, b in zip(seq, seq[1:])))
            for i in range(0, 20, 4):                    # mỗi vòng đủ mặt cả kho
                self.assertEqual(set(seq[i:i + 4]), set(v))

    def test_build_playlist_cu_van_chay(self):
        v = self.clips("nauan", "vlog")
        seq, total = video_khung.build_playlist(v, {x: 10.0 for x in v}, 100.0)
        self.assertEqual((sorted(seq), total), (v, 100.0))


class SoTests(_Kho):
    def test_cac_lan_dung_khong_trung_roi_reset(self):
        v = self.clips("nauan")
        a, mo_ta = self.dung(v, 20.0)
        self.assertIn("còn 6/6 clip chưa lấy", mo_ta)
        b, _ = self.dung(v, 20.0)
        c, mo_ta = self.dung(v, 20.0)
        self.assertIn("còn 2/6 clip chưa lấy", mo_ta)
        self.assertEqual(sorted(a + b + c), v)            # 3 video, 6 clip, không trùng
        self.assertEqual(cdl.dem(self.root / "nauan"), (0, 6))
        d, mo_ta = self.dung(v, 20.0)                     # hết → reset, lấy lại từ đầu
        self.assertIn("RESET", mo_ta)
        self.assertEqual(cdl.da_lay_trong(v), set(d))
        self.assertEqual(cdl.dem(self.root / "nauan"), (4, 6))

    def test_dung_hong_thi_khong_danh_dau(self):
        v = self.clips("nauan")
        self.dung(v, 30.0, xong=False)
        self.assertFalse(cdl.SO_FILE.exists())
        self.assertEqual(cdl.dem(self.root / "nauan"), (6, 6))

    def test_reset_chi_dung_thu_muc_dang_chon(self):
        self.dung(self.clips("vlog"), 30.0)               # vlog còn 1/4
        self.dung(self.clips("nauan"), 60.0)              # nauan hết
        self.dung(self.clips("nauan"), 20.0)              # nauan reset
        self.assertEqual(cdl.dem(self.root / "vlog"), (1, 4))
        self.assertEqual(cdl.dem(self.root / "nauan"), (4, 6))

    def test_tick_nhieu_thu_muc_dung_chung_dau(self):
        self.dung(self.clips("nauan"), 60.0)              # nauan hết
        seq, mo_ta = self.dung(self.clips("nauan", "vlog"), 30.0)
        self.assertIn("còn 4/10 clip chưa lấy", mo_ta)
        self.assertTrue(all(v.parent.name == "vlog" for v in seq))

    def test_them_video_va_thu_muc_moi_la_chua_lay(self):
        self.dung(self.clips("nauan"), 60.0)
        (self.root / "nauan" / "moi.mp4").write_bytes(b"0")
        (self.root / "thiennhien").mkdir()
        (self.root / "thiennhien" / "t0.mp4").write_bytes(b"0")
        self.assertEqual(gui.dem_ngang_sources(),
                         {"nauan": (1, 7), "thiennhien": (1, 1), "vlog": (4, 4)})
        seq, mo_ta = self.dung(self.clips("nauan"), 10.0)
        self.assertEqual([v.name for v in seq], ["moi.mp4"])
        self.assertNotIn("RESET", mo_ta)

    def test_clip_da_xoa_bi_bo_khoi_so(self):
        v = self.clips("vlog")
        self.dung(v, 40.0)
        v[0].unlink()
        self.dung(self.clips("nauan"), 10.0)
        so = cdl.doc_so()
        self.assertNotIn(cdl.khoa(v[0]), so)
        self.assertEqual(len(so), 4)                      # 3 vlog còn lại + 1 nauan

    def test_so_hong_coi_nhu_chua_lay(self):
        cdl.SO_FILE.write_text("{cụt", encoding="utf-8")
        self.assertEqual(cdl.doc_so(), {})
        cdl.SO_FILE.write_text("[1, 2]", encoding="utf-8")
        self.assertEqual(cdl.doc_so(), {})
        self.dung(self.clips("vlog"), 10.0)
        self.assertEqual(len(cdl.doc_so()), 1)

    def test_dat_lai_theo_nguon_dang_chon(self):
        self.dung(self.clips("nauan"), 30.0)
        self.dung(self.clips("vlog"), 20.0)
        self.assertEqual(gui.dat_lai_ngang_da_lay(["nauan"]), 3)
        self.assertEqual(gui.dem_ngang_sources(), {"nauan": (6, 6), "vlog": (2, 4)})
        self.assertEqual(gui.dat_lai_ngang_da_lay([]), 2)             # [] = cả kho
        self.assertEqual(gui.dem_ngang_sources(), {"nauan": (6, 6), "vlog": (4, 4)})
        self.assertEqual(gui.dat_lai_ngang_da_lay(gui.NGANG_SOURCE_ALL), 0)


class WebTests(_Kho):
    def _client(self):
        c = TestClient(server.app)
        c.cookies.set(server.COOKIE, server.TOKEN)
        return c

    def test_trang_hien_con_bao_nhieu_clip(self):
        self.dung(self.clips("nauan"), 20.0)
        with patch.object(server, "_vram", return_value={}):
            html = self._client().get("/giongnoi").text
        self.assertIn("· còn 4/6", html)
        self.assertIn("· còn 4/4", html)
        # nút ↺ gửi ngầm xong phải tải lại trang (app.js đọc data-ajax của NÚT) để số đổi theo
        self.assertIn('formaction="/giongnoi/dalay-reset" data-ajax="tailai"', html)
        js = (Path(server.__file__).resolve().parent / "static" / "app.js").read_text("utf-8")
        self.assertIn("nut.dataset.ajax === 'tailai'", js)

    def test_nut_lay_lai_tu_dau(self):
        self.dung(self.clips("nauan"), 20.0)
        self.dung(self.clips("vlog"), 20.0)
        logs: list[str] = []
        with patch.object(server, "_save_voice_from_form") as luu, \
             patch.object(server, "log", side_effect=logs.append):
            r = self._client().post("/giongnoi/dalay-reset", follow_redirects=False,
                                    data={"ngang_source": ["", "nauan"]})
        self.assertEqual(r.status_code, 303)
        luu.assert_called_once()
        self.assertEqual(gui.dem_ngang_sources(), {"nauan": (6, 6), "vlog": (2, 4)})
        self.assertIn("nauan: đã xoá 2 dấu", logs[0])


if __name__ == "__main__":
    unittest.main()
