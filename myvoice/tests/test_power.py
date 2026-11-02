"""power.py — hai ô ⏻ tắt máy / 🌙 cho máy ngủ dùng CHUNG một bộ đếm (31/10/2026).

Chạy từ gốc repo:  venv\\Scripts\\python.exe -m unittest myvoice/tests/test_power.py

Chỉ thử phần logic (_tick / arm / state) với hàng đợi và đồng hồ giả — không gọi
shutdown hay SetSuspendState thật.
"""

import threading
import unittest
from unittest.mock import patch

from myvoice.web import power


def _lam_watcher() -> power.PowerWhenDone:
    # __init__ tự bật luồng nền canh hàng đợi — thử logic thì không cần, chặn lại.
    with patch.object(threading.Thread, "start"):
        return power.PowerWhenDone()


class ArmTests(unittest.TestCase):
    def setUp(self):
        p = patch.object(power, "log")
        p.start()
        self.addCleanup(p.stop)
        self.w = _lam_watcher()

    def test_mac_dinh_tat(self):
        st = self.w.state()
        self.assertFalse(st["armed"])
        self.assertEqual(st["mode"], "")
        self.assertFalse(st["counting"])

    def test_hai_che_do_loai_tru_nhau(self):
        self.w.arm("sleep")
        st = self.w.state()
        self.assertTrue(st["armed"])
        self.assertEqual(st["mode"], "sleep")
        self.assertEqual(st["label"], "cho máy ngủ")
        self.assertEqual(st["delay_min"], power.SLEEP_DELAY_MIN)
        self.w.arm("shutdown")              # đổi chế độ = thay, không cộng dồn
        st = self.w.state()
        self.assertEqual(st["mode"], "shutdown")
        self.assertEqual(st["label"], "tắt máy")
        self.assertEqual(st["delay_min"], power.SHUTDOWN_DELAY_MIN)
        self.w.arm("")
        self.assertFalse(self.w.state()["armed"])

    def test_kieu_cu_bool_van_hieu(self):
        self.w.arm(True)
        self.assertEqual(self.w.state()["mode"], "shutdown")
        self.w.arm(False)
        self.assertEqual(self.w.state()["mode"], "")

    def test_che_do_la_coi_nhu_tat(self):
        self.w.arm("hibernate")
        self.assertEqual(self.w.state()["mode"], "")

    def test_ca_hai_cho_1_phut(self):
        # 31/10/2026: user hạ ⏻ 5 → 1 phút và cho 🌙 quay lại cũng 1 phút.
        self.assertEqual(power.SHUTDOWN_DELAY_MIN, 1)
        self.assertEqual(power.SLEEP_DELAY_MIN, 1)
        self.assertEqual(self.w.state()["shutdown_delay_min"], 1)
        self.assertEqual(self.w.state()["sleep_delay_min"], 1)


class TickTests(unittest.TestCase):
    """Đồng hồ + hàng đợi giả: self.now là time.monotonic, self.busy là hàng đợi chính."""

    def setUp(self):
        self.busy = False
        self.now = 1000.0
        for p in (patch.object(power.runner, "heavy_busy", side_effect=lambda: self.busy),
                  patch.object(power.upload_runner, "heavy_busy", return_value=False),
                  patch.object(power.fb_runner, "heavy_busy", return_value=False),
                  patch.object(power.time, "monotonic", side_effect=lambda: self.now),
                  patch.object(power, "log")):
            p.start()
            self.addCleanup(p.stop)
        self.w = _lam_watcher()

    def _chay_mot_me(self):
        """Hàng đợi bận một lượt rồi rảnh → bắt đầu đếm ngược."""
        self.busy = True
        self.assertEqual(self.w._tick(), "")
        self.busy = False
        self.assertEqual(self.w._tick(), "")
        self.assertTrue(self.w.state()["counting"])

    def test_tick_luc_ranh_khong_dem(self):
        self.w.arm("sleep")
        for _ in range(5):
            self.assertEqual(self.w._tick(), "")
            self.now += 600
        self.assertFalse(self.w.state()["counting"])

    def test_ngu_sau_1_phut_mot_lan_duy_nhat(self):
        self.w.arm("sleep")
        self._chay_mot_me()
        self.assertEqual(self.w.state()["left"], f"{power.SLEEP_DELAY_MIN}:00")
        self.now += power.SLEEP_DELAY_MIN * 60 - 1
        self.assertEqual(self.w._tick(), "")
        self.now += 2
        self.assertEqual(self.w._tick(), "sleep")
        st = self.w.state()                 # hết giờ = tự bỏ tick
        self.assertEqual(st["mode"], "")
        self.assertFalse(st["counting"])
        self.now += 3600
        self.assertEqual(self.w._tick(), "")   # dậy rồi không ngủ lại

    def test_tat_may_sau_1_phut(self):
        self.w.arm("shutdown")
        self._chay_mot_me()
        self.now += power.SHUTDOWN_DELAY_MIN * 60 + 1
        self.assertEqual(self.w._tick(), "shutdown")
        self.assertEqual(self.w.state()["mode"], "")

    def test_viec_moi_chen_vao_huy_dem(self):
        self.w.arm("shutdown")
        self._chay_mot_me()
        self.busy = True
        self.assertEqual(self.w._tick(), "")
        self.assertFalse(self.w.state()["counting"])
        self.now += 3600                    # bận lâu — không được tắt giữa chừng
        self.assertEqual(self.w._tick(), "")
        self.busy = False
        self.assertEqual(self.w._tick(), "")   # rảnh lại → đếm lại từ đầu
        self.assertTrue(self.w.state()["counting"])
        self.now += power.SHUTDOWN_DELAY_MIN * 60 + 1
        self.assertEqual(self.w._tick(), "shutdown")

    def test_bo_tick_giua_luc_dem_la_huy(self):
        self.w.arm("sleep")
        self._chay_mot_me()
        self.w.arm("")
        self.assertFalse(self.w.state()["counting"])
        self.now += 3600
        self.assertEqual(self.w._tick(), "")

    def test_doi_che_do_giua_luc_dem_thi_dem_lai(self):
        self.w.arm("sleep")
        self._chay_mot_me()
        self.w.arm("shutdown")              # đổi ⏻ ↔ 🌙 = phải thấy bận lại đã
        self.assertFalse(self.w.state()["counting"])
        self.now += 3600
        self.assertEqual(self.w._tick(), "")
        self._chay_mot_me()
        self.now += power.SHUTDOWN_DELAY_MIN * 60 + 1
        self.assertEqual(self.w._tick(), "shutdown")

    def test_dang_tai_len_cung_la_ban(self):
        self.w.arm("sleep")
        with patch.object(power.fb_runner, "heavy_busy", return_value=True):
            self.assertEqual(self.w._tick(), "")
        self.assertEqual(self.w._tick(), "")      # rảnh → bắt đầu đếm
        self.assertTrue(self.w.state()["counting"])


if __name__ == "__main__":
    unittest.main()
