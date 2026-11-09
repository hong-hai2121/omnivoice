"""power.py — hai ô ⏻ tắt máy / 🌙 cho máy ngủ dùng CHUNG một bộ đếm (31/10/2026).

Chạy từ gốc repo:  venv\\Scripts\\python.exe -m unittest myvoice/tests/test_power.py

Chỉ thử phần logic (_tick / arm / state) với hàng đợi và đồng hồ giả — không gọi
shutdown hay SetSuspendState thật.
"""

import threading
import unittest
from unittest.mock import patch

from myvoice.web import power


# CHỐT AN TOÀN (05/11/2026 — user nhắc: thử phần tắt máy phải cẩn thận): tiến trình chạy
# test KHÔNG BAO GIỜ được tắt máy / cho máy ngủ thật. Các test dưới chỉ gọi _tick() với
# đồng hồ giả trên watcher không bật luồng canh, nhưng watcher toàn cục của power.py vẫn
# sống trong tiến trình này — thay hẳn hai hàm phát lệnh bằng hàm ném lỗi, không gỡ.
def _cam_lenh_that(*_a, **_k):
    raise AssertionError("test không được phát lệnh tắt máy / cho máy ngủ thật")


power.PowerWhenDone._shutdown_now = _cam_lenh_that
power.PowerWhenDone._sleep_now = _cam_lenh_that


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


class NhoTests(unittest.TestCase):
    """Nhớ lựa chọn ⏻/🌙 qua các lần mở server (08/11/2026): web_settings.json khoá power_mode.
    core.save/load_web_settings thay bằng một dict trong RAM — không ghi file thật."""

    def setUp(self):
        self.luu: dict = {}
        for p in (patch.object(power, "log"),
                  patch.object(power.core, "save_web_settings",
                               side_effect=lambda d: self.luu.update(d)),
                  patch.object(power.core, "load_web_settings",
                               side_effect=lambda: dict(self.luu))):
            p.start()
            self.addCleanup(p.stop)
        self.w = _lam_watcher()

    def test_tick_la_ghi_bo_tick_cung_ghi(self):
        self.w.arm("sleep")
        self.assertEqual(self.luu, {power.NHO_KHOA: "sleep"})
        self.w.arm("shutdown")
        self.assertEqual(self.luu[power.NHO_KHOA], "shutdown")
        self.w.arm("")                      # "và ngược lại": bỏ tick cũng nhớ
        self.assertEqual(self.luu[power.NHO_KHOA], "")

    def test_mo_lai_server_bat_y_nhu_lan_truoc(self):
        self.luu[power.NHO_KHOA] = "shutdown"
        w2 = _lam_watcher()
        self.assertEqual(w2.khoi_phuc(), "shutdown")
        st = w2.state()
        self.assertTrue(st["armed"])
        self.assertEqual(st["mode"], "shutdown")
        self.assertFalse(st["counting"])    # vẫn phải thấy bận rồi mới đếm

    def test_lan_truoc_tat_hoac_gia_tri_la_thi_khong_bat(self):
        self.luu[power.NHO_KHOA] = ""
        self.assertEqual(self.w.khoi_phuc(), "")
        self.assertFalse(self.w.state()["armed"])
        self.luu[power.NHO_KHOA] = "hibernate"
        self.assertEqual(self.w.khoi_phuc(), "")
        self.assertFalse(self.w.state()["armed"])
        self.luu.clear()                    # file cũ chưa có khoá → tắt
        self.assertEqual(self.w.khoi_phuc(), "")

    def test_khoi_phuc_chi_doc_khong_ghi(self):
        self.luu[power.NHO_KHOA] = "sleep"
        with patch.object(power.core, "save_web_settings") as ghi:
            self.assertEqual(self.w.khoi_phuc(), "sleep")
        ghi.assert_not_called()

    def test_het_gio_tu_bo_tick_nhung_van_nho_cho_dem_sau(self):
        now = {"t": 1000.0}
        busy = {"b": False}
        with patch.object(power.runner, "heavy_busy", side_effect=lambda: busy["b"]), \
                patch.object(power.upload_runner, "heavy_busy", return_value=False), \
                patch.object(power.fb_runner, "heavy_busy", return_value=False), \
                patch.object(power.time, "monotonic", side_effect=lambda: now["t"]):
            self.w.arm("shutdown")
            busy["b"] = True
            self.w._tick()
            busy["b"] = False
            self.w._tick()                  # rảnh → đếm ngược
            now["t"] += power.SHUTDOWN_DELAY_MIN * 60 + 1
            self.assertEqual(self.w._tick(), "shutdown")
        self.assertEqual(self.w.state()["mode"], "")          # trong RAM: tự bỏ tick
        self.assertEqual(self.luu[power.NHO_KHOA], "shutdown")  # nhưng lựa chọn còn
        self.assertEqual(_lam_watcher().khoi_phuc(), "shutdown")

    def test_file_hong_khong_lam_hong_tick(self):
        with patch.object(power.core, "save_web_settings", side_effect=OSError("đĩa đầy")):
            self.w.arm("sleep")             # không ném lỗi ra ngoài
        self.assertEqual(self.w.state()["mode"], "sleep")
        with patch.object(power.core, "load_web_settings", side_effect=OSError("hỏng")):
            self.assertEqual(_lam_watcher().khoi_phuc(), "")


class RouteNhoTests(unittest.TestCase):
    """Ô tick trên trang web → /hangdoi/tatmay → watcher toàn cục arm(nho=True) → ghi
    web_settings.json. save_web_settings được thay nên không đụng file thật; watcher toàn cục
    được tắt lại ở finally (và nó không bao giờ đếm vì chưa "thấy bận")."""

    def test_route_ghi_lua_chon_ca_khi_bo_tick(self):
        from fastapi.testclient import TestClient
        from myvoice.web import server
        ghi: dict = {}
        with patch.object(power.core, "save_web_settings", side_effect=lambda d: ghi.update(d)), \
                patch.object(power, "log"), patch.object(server, "_vram", return_value={}), \
                patch.object(server.core, "upload_slots_text", return_value="08:00"):
            client = TestClient(server.app)
            client.cookies.set(server.COOKIE, server.TOKEN)
            try:
                r = client.post("/hangdoi/tatmay", data={"ngu": "1"}, headers={"HX-Request": "true"})
                self.assertEqual(r.status_code, 200)
                self.assertEqual(ghi[power.NHO_KHOA], "sleep")
                self.assertEqual(power.watcher.state()["mode"], "sleep")
                r = client.post("/hangdoi/tatmay", data={}, headers={"HX-Request": "true"})
                self.assertEqual(r.status_code, 200)
                self.assertEqual(ghi[power.NHO_KHOA], "")
                self.assertEqual(power.watcher.state()["mode"], "")
            finally:
                power.watcher.arm("", nho=False)


if __name__ == "__main__":
    unittest.main()
