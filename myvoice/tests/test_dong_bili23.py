# -*- coding: utf-8 -*-
"""Tự đóng app Bili23 sau khi tải xong (08/11/2026, user yêu cầu).

Script tải (myvideo/video_taibilibili.py) ghi dấu PID khi CHÍNH NÓ mở app; cuối đợt tải,
hàng đợi myvoice chạy `--dong-app` → chỉ đóng đúng tiến trình đó, app người dùng mở sẵn thì
để nguyên. Không mở/đóng app thật, không taskkill thật, không đụng %TEMP% thật.

Chạy từ gốc repo:  venv\\Scripts\\python.exe -m unittest myvoice/tests/test_dong_bili23.py
"""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from myvoice.web import steps
from myvoice.web.runners import run_episode

# Nạp ĐÚNG file script mà runner gọi (không chèn myvideo/ vào sys.path).
_spec = importlib.util.spec_from_file_location("video_taibilibili_dong", run_episode.TAIBILI_SCRIPT)
tb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tb)


class _FakePopen:
    """Thay subprocess.Popen lúc mở app: không chạy gì, chỉ có PID."""

    def __init__(self, argv, **kw):
        self.argv = argv
        self.pid = 4242


class DauTuMoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = Path(self.tmp.name)
        self.app = d / "BBDown"
        (self.app / ".venv" / "Scripts").mkdir(parents=True)
        (self.app / "src").mkdir()
        self.pyw = self.app / ".venv" / "Scripts" / "pythonw.exe"
        self.pyw.write_bytes(b"")
        (self.app / "src" / "main.py").write_text("", encoding="utf-8")
        self.dau = d / "dau.json"
        self.goi: list = []
        for p in (patch.object(tb, "BBDOWN_DIR", self.app),
                  patch.object(tb, "DAU_TU_MO", self.dau),
                  patch.object(tb.subprocess, "Popen", _FakePopen),
                  patch.object(tb, "_taskkill",
                               side_effect=lambda pid, ep: self.goi.append((pid, ep))),
                  patch.object(tb.time, "sleep", lambda s: None),
                  patch.object(tb, "_task_dang_lam", return_value=0),
                  patch("builtins.print")):
            p.start()
            self.addCleanup(p.stop)

    def test_con_task_dang_tai_thi_chua_dong_va_giu_dau(self):
        """Task của myvideo / người dùng tạo tay còn đang tải → không đóng, dấu giữ cho lượt sau."""
        tb.mo_app()
        with patch.object(tb, "_duong_dan_exe", return_value=str(self.pyw)), \
                patch.object(tb, "_task_dang_lam", return_value=2):
            msg = tb.dong_app_neu_tu_mo()
        self.assertIn("còn 2 task", msg)
        self.assertEqual(self.goi, [])
        self.assertTrue(self.dau.exists())

    def test_khong_hoi_duoc_mcp_thi_van_dong(self):
        tb.mo_app()
        song = [str(self.pyw)]
        with patch.object(tb, "_duong_dan_exe", side_effect=lambda pid: song.pop(0) if song else ""), \
                patch.object(tb, "_task_dang_lam", return_value=None):
            msg = tb.dong_app_neu_tu_mo(cho=1.0)
        self.assertIn("Đã đóng app Bili23", msg)

    def test_mo_app_ghi_dau_pid_va_exe(self):
        tb.mo_app()
        dau = json.loads(self.dau.read_text(encoding="utf-8"))
        self.assertEqual(dau["pid"], 4242)
        self.assertEqual(Path(dau["exe"]), self.pyw)

    def test_khong_co_dau_thi_de_nguyen(self):
        """App do người dùng mở sẵn (script chưa từng mở) → không đụng."""
        msg = tb.dong_app_neu_tu_mo()
        self.assertIn("không do hàng đợi tự mở", msg)
        self.assertEqual(self.goi, [])

    def test_app_da_dong_tu_truoc(self):
        tb.mo_app()
        with patch.object(tb, "_duong_dan_exe", return_value=""):
            msg = tb.dong_app_neu_tu_mo()
        self.assertIn("đã đóng từ trước", msg)
        self.assertEqual(self.goi, [])
        self.assertFalse(self.dau.exists())          # dấu cũ được dọn

    def test_pid_da_thanh_tien_trinh_khac_thi_khong_dong(self):
        """Windows cấp lại PID: dấu còn mà PID giờ là app khác → tuyệt đối không kill."""
        tb.mo_app()
        with patch.object(tb, "_duong_dan_exe", return_value=r"C:\Windows\notepad.exe"):
            msg = tb.dong_app_neu_tu_mo()
        self.assertIn("để nguyên", msg)
        self.assertEqual(self.goi, [])
        self.assertFalse(self.dau.exists())

    def test_dong_em_khi_dung_la_app(self):
        tb.mo_app()
        song = [str(self.pyw), str(self.pyw)]        # 2 lần còn sống (kiểm + vòng chờ) rồi thoát
        with patch.object(tb, "_duong_dan_exe",
                          side_effect=lambda pid: song.pop(0) if song else ""):
            msg = tb.dong_app_neu_tu_mo(cho=1.0)
        self.assertIn("Đã đóng app Bili23", msg)
        self.assertNotIn("phải ép", msg)
        self.assertEqual(self.goi, [(4242, False)])  # chỉ WM_CLOSE, không /F
        self.assertFalse(self.dau.exists())

    def test_ep_neu_dong_em_khong_xong(self):
        tb.mo_app()
        with patch.object(tb, "_duong_dan_exe", return_value=str(self.pyw)), \
                patch.object(tb.time, "monotonic", side_effect=[0.0, 0.0, 100.0, 100.0]):
            msg = tb.dong_app_neu_tu_mo(cho=1.0)
        self.assertIn("phải ép", msg)
        self.assertEqual(self.goi, [(4242, False), (4242, True)])

    @unittest.skipUnless(sys.platform == "win32", "normcase chỉ gộp hoa/thường trên Windows")
    def test_duong_dan_khac_hoa_thuong_van_la_mot(self):
        """API Windows trả đường dẫn theo đúng chữ trên đĩa, dấu ghi theo cấu hình — hoa/thường
        khác nhau vẫn phải nhận ra là cùng một app."""
        tb.mo_app()
        song = [str(self.pyw).upper()]
        with patch.object(tb, "_duong_dan_exe",
                          side_effect=lambda pid: song.pop(0) if song else ""):
            msg = tb.dong_app_neu_tu_mo(cho=1.0)
        self.assertIn("Đã đóng app Bili23", msg)

    def test_dau_hong_thi_coi_nhu_khong_co(self):
        self.dau.write_text("không phải json", encoding="utf-8")
        msg = tb.dong_app_neu_tu_mo()
        self.assertIn("để nguyên", msg)
        self.assertEqual(self.goi, [])


class DemTaskTests(unittest.TestCase):
    """_task_dang_lam thật (không bị setUp của lớp trên thay) — chỉ MCP bị giả."""

    def test_dem_task_chi_tinh_task_dang_lam(self):
        kq = {"tasks": [{"status": "downloading"}, {"status": "completed"},
                        {"status": "failed"}, {"status": "paused"}, {"status": "MERGING"}]}
        with patch.object(tb, "doc_cau_hinh", return_value=("http://x/mcp", "t")), \
                patch.object(tb, "goi_tool", return_value=kq) as goi:
            self.assertEqual(tb._task_dang_lam(), 2)
        self.assertEqual(goi.call_args.args[2], "list_tasks")
        self.assertEqual(goi.call_args.args[3], {"state": "downloading"})
        with patch.object(tb, "doc_cau_hinh", side_effect=tb.ThatBai("app tắt MCP")):
            self.assertIsNone(tb._task_dang_lam())


class CliTests(unittest.TestCase):
    def test_dong_app_khong_can_link(self):
        with patch.object(tb, "dong_app_neu_tu_mo", return_value="ℹ️ thử") as dong, \
                patch("builtins.print"):
            self.assertEqual(tb.main(["--dong-app"]), 0)
        dong.assert_called_once()

    def test_tai_van_can_link_va_out(self):
        for argv in ([], ["https://www.bilibili.com/video/BV1x"], ["--out", "a.mp4"]):
            with self.assertRaises(SystemExit), patch("sys.stderr"):
                tb.main(argv)


class BuocCuoiDotTaiTests(unittest.TestCase):
    def test_buoc_dong_app_tro_dung_script(self):
        s = steps.dong_bili23_step()
        self.assertEqual(s.argv[-1], "--dong-app")
        self.assertEqual(Path(s.argv[-2]), run_episode.TAIBILI_SCRIPT)
        self.assertEqual(steps.TAIBILI_SCRIPT, run_episode.TAIBILI_SCRIPT)
        self.assertTrue(run_episode.TAIBILI_SCRIPT.is_file())
        self.assertTrue(s.continue_on_fail)          # dọn dẹp hỏng không làm đợt tải "lỗi"
        self.assertIn("Bili23", s.label)


if __name__ == "__main__":
    unittest.main()
