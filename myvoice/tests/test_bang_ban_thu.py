# -*- coding: utf-8 -*-
"""Bảng 📼 Kết quả của myvideo KHÔNG lẫn bản thử với video thật (24/11/2026).

User: "sao video thử lại có ở trong này" — bản thử 3 phút của 🎛 Chỉnh trước
(output/<tên>_thu3p/<tên>_thu3p_x0.7.*) cũng mang tag _x… nên trước đây hiện thành một
hàng y như video thật (④ luôn "—", ô tên cắt chữ nên không thấy đuôi _thu3p).

Server chạy qua TestClient; output, cài đặt trỏ sang thư mục tạm, st.recycle là đồ giả
(không đưa gì vào Thùng rác thật), hàng đợi không ghi nhật ký."""
import json
import re
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
with patch.object(threading.Thread, "start", lambda self: None):     # không bật luồng nền
    from myvideo.web import chinhtruoc as ct, server as sv, steps as st
from starlette.testclient import TestClient  # noqa: E402


def _tao(p: Path, noi_dung: bytes = b"x") -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(noi_dung)
    return p


class BangBanThuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="bt_"))
        cls.out = cls.tmp / "output"
        cls.out.mkdir()
        cls.src_b = _tao(cls.tmp / "Phim B.mp4")              # nguồn chờ, mới có bản thử
        (cls.tmp / "web_settings.json").write_text(
            json.dumps({"cho_chinh": [str(cls.src_b)]}), encoding="utf-8")
        cls.xoa = []

        def _recycle_gia(paths, on_log=None):
            cls.xoa.append([Path(p) for p in paths])
            return len(paths), 0

        cls._va = [patch.object(sv, "SETTINGS_FILE", cls.tmp / "web_settings.json"),
                   patch.object(sv, "OUTPUT_DIR", cls.out), patch.object(st, "OUTPUT_DIR", cls.out),
                   patch.object(ct, "KHO_FILE", cls.tmp / "chinh_truoc.json"),
                   patch.object(ct, "XEM_DIR", cls.tmp / "xemtruoc"),
                   patch.object(st, "recycle", _recycle_gia),
                   patch.object(sv.q, "busy", lambda: False),
                   patch.object(sv.q, "note", lambda *a, **k: None)]
        for p in cls._va:
            p.start()
        o = cls.out
        # A: video thật đủ ①, kèm bản thử 3 phút + clip đã cắt
        _tao(o / "Phim A" / "Phim A_x0.7.mp4")
        _tao(o / "Phim A" / "Phim A_x0.7.srt")
        _tao(o / "Phim A_thu3p" / "Phim A_thu3p_x0.7.mp4")
        _tao(o / "Phim A_thu3p" / "Phim A_thu3p_x0.7_vi_audio.wav")
        _tao(o / "Phim A_thu3p.mp4")
        # B: chỉ có bản thử, nguồn còn nằm ở danh sách chờ
        _tao(o / "Phim B_thu3p" / "Phim B_thu3p_x0.7.mp4")
        # C: chỉ có bản thử (hai tốc độ) + clip, nguồn KHÔNG còn ở danh sách chờ
        _tao(o / "Phim C_thu3p" / "Phim C_thu3p_x0.7.mp4")
        _tao(o / "Phim C_thu3p" / "Phim C_thu3p_x0.8.mp4")
        _tao(o / "Phim C_thu3p.mp4")
        # D: bản nháp 60 giây đủ 4 bước (nút 🧪 Thử 60 giây)
        _tao(o / "Phim D_thu60" / "Phim D_thu60_x0.7.mp4")
        _tao(o / "Phim D_thu60" / "Phim D_thu60_x0.7_sub.mp4")
        cls.c = TestClient(sv.app)
        cls.c.cookies.set(sv.COOKIE, sv.TOKEN)

    @classmethod
    def tearDownClass(cls):
        for p in cls._va:
            p.stop()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.xoa.clear()

    def _bang(self) -> str:
        r = self.c.get("/partials/bang")
        self.assertEqual(r.status_code, 200)
        return r.text

    def _tick(self, bang: str) -> list[str]:
        return re.findall(r'class="tickv" value="([^"]*)"', bang)

    def test_nhan_ra_ban_thu(self):
        self.assertEqual(sv._la_thu("Phim A_thu3p/Phim A_thu3p_x0.7"), ct.THU_DUOI)
        self.assertEqual(sv._la_thu("Phim D_thu60/Phim D_thu60_x0.7"), "_thu60")
        self.assertEqual(sv._la_thu("Phim A/Phim A_x0.7"), "")
        self.assertEqual(sv._la_thu("thu3p phim/thu3p phim_x0.7"), "")      # chỉ tính ĐUÔI tên

    def test_ban_thu_3_phut_khong_thanh_hang_rieng(self):
        tick = self._tick(self._bang())
        self.assertIn("base:Phim A/Phim A_x0.7", tick)                      # video thật: còn nguyên
        for t in tick:                                                      # không hàng nào là bản thử của A / B
            self.assertNotIn("Phim A_thu3p", t)
            self.assertNotIn("Phim B_thu3p", t)
        # scan_rows KHÔNG đổi — khung 🎛 vẫn tìm ra bản thử của video qua nó.
        self.assertIn("Phim A_thu3p/Phim A_thu3p_x0.7", [r["base"] for r in st.scan_rows(limit=500)])
        m = sv._ct_muc("base:Phim A/Phim A_x0.7")
        self.assertEqual(m["v_thu"], self.out / "Phim A_thu3p" / "Phim A_thu3p_x0.7.mp4")
        self.assertTrue(m["co_thu"])

    def test_nguon_cho_ghi_da_co_ban_thu(self):
        bang = self._bang()
        self.assertIn(f"src:{self.src_b}", self._tick(bang))
        hang = re.search(r'(?s)<tr class="hangcho">(?:(?!</tr>).)*Phim B\.mp4.*?</tr>', bang).group()
        self.assertIn("đã có bản thử 3 phút", hang)
        self.assertNotIn("chưa chạy bước nào", hang)

    def test_chi_co_ban_thu_thi_mot_hang_ghi_ro(self):
        bang = self._bang()
        tick = [t for t in self._tick(bang) if "Phim C" in t]
        self.assertEqual(len(tick), 1)                                      # hai tốc độ thử vẫn chỉ MỘT hàng
        self.assertTrue(tick[0].startswith("base:Phim C_thu3p/Phim C_thu3p_x0."))
        hang = re.search(r'(?s)<tr class="hangcho">(?:(?!</tr>).)*Phim C.*?</tr>', bang).group()
        self.assertIn("chỉ có bản thử 3 phút", hang)
        self.assertIn("thư mục thử + clip đã cắt", hang)                    # lời hỏi lại của nút 🗑 nói rõ xoá gì
        self.assertNotIn("okc", hang)                                       # không vẽ cột ①②③④
        self.assertIsNotNone(sv._ct_muc(tick[0]))                           # tick hàng này mở được khung 🎛
        # 🗑 của hàng này dọn TRỌN bản thử: thư mục thử (mọi tốc độ) + clip đã cắt.
        r = self.c.post("/xoa", data={"base": tick[0][5:]}, headers={"hx-request": "true"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(sorted(self.xoa[0]), sorted([self.out / "Phim C_thu3p", self.out / "Phim C_thu3p.mp4"]))

    def test_xoa_video_that_khong_dung_ban_thu(self):
        self.c.post("/xoa", data={"base": "Phim A/Phim A_x0.7"}, headers={"hx-request": "true"})
        self.assertEqual(self.xoa, [[self.out / "Phim A"]])

    def test_ban_nhap_60_giay_van_la_hang_co_nhan(self):
        bang = self._bang()
        self.assertIn("base:Phim D_thu60/Phim D_thu60_x0.7", self._tick(bang))
        hang = re.search(r'(?s)<tr class="done">(?:(?!</tr>).)*Phim D_thu60.*?</tr>', bang).group()
        self.assertIn("🧪 thử 60s", hang)
        hang_a = re.search(r'(?s)<tr class="">(?:(?!</tr>).)*Phim A/Phim A_x0\.7.*?</tr>', bang).group()
        self.assertNotIn("nhanthu", hang_a)                                 # video thật không mang nhãn thử


if __name__ == "__main__":
    unittest.main()
