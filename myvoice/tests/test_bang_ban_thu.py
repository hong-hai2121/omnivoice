# -*- coding: utf-8 -*-
"""Bảng 📼 Kết quả của myvideo (24/11/2026): không lẫn bản thử với video thật, và xoá ở
bảng là DỌN SẠCH video đó khỏi output.

User: "sao video thử lại có ở trong này" — bản thử 3 phút của 🎛 Chỉnh trước
(output/<tên>_thu3p/<tên>_thu3p_x0.7.*) cũng mang tag _x… nên trước đây hiện thành một
hàng y như video thật (④ luôn "—", ô tên cắt chữ nên không thấy đuôi _thu3p).
User: "khi xoá ở đây là xoá tệp khỏi output luôn và cái chỉnh trước cũng mất video liên
quan đi hết" — 🗑 trước đây để sót file từng đoạn của video dài, bản thử và clip đã cắt.

Server chạy qua TestClient; output, cài đặt, bản xem trước trỏ sang thư mục tạm — dựng
lại trước MỖI bài; st.recycle là đồ giả (xoá thẳng trong thư mục tạm, không đụng Thùng
rác thật), hàng đợi không ghi nhật ký."""
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

HX = {"hx-request": "true"}


def _tao(p: Path, noi_dung: bytes = b"x") -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(noi_dung)
    return p


class BangBanThuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="bt_"))
        cls.out = cls.tmp / "output"
        cls.caidat = cls.tmp / "web_settings.json"
        cls.xoa = []
        cls.ban = [False]                                      # hàng đợi đang chạy?

        def _recycle_gia(paths, on_log=None):
            cls.xoa.append([Path(p) for p in paths])
            for p in paths:
                shutil.rmtree(p) if Path(p).is_dir() else Path(p).unlink()
            return len(paths), 0

        cls._va = [patch.object(sv, "SETTINGS_FILE", cls.caidat),
                   patch.object(sv, "OUTPUT_DIR", cls.out), patch.object(st, "OUTPUT_DIR", cls.out),
                   patch.object(ct, "KHO_FILE", cls.tmp / "chinh_truoc.json"),
                   patch.object(ct, "XEM_DIR", cls.tmp / "xemtruoc"),
                   patch.object(st, "recycle", _recycle_gia),
                   patch.object(sv.q, "busy", lambda: cls.ban[0]),
                   patch.object(sv.q, "note", lambda *a, **k: None)]
        for p in cls._va:
            p.start()
        cls.c = TestClient(sv.app)
        cls.c.cookies.set(sv.COOKIE, sv.TOKEN)

    @classmethod
    def tearDownClass(cls):
        for p in cls._va:
            p.stop()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.xoa.clear()
        self.ban[0] = False
        for d in (self.out, self.tmp / "nguon", self.tmp / "xemtruoc"):
            shutil.rmtree(d, ignore_errors=True)
        o = self.out
        o.mkdir()
        self.src_a = _tao(self.tmp / "nguon" / "Phim A.mp4")   # nguồn của video thật A
        self.src_b = _tao(self.tmp / "nguon" / "Phim B.mp4")   # nguồn chờ, mới có bản thử
        self.src_g = _tao(self.tmp / "nguon" / "Phim G.mp4")   # nguồn chờ, chưa có gì trong output
        self.caidat.write_text(json.dumps(
            {"cho_chinh": [str(self.src_a), str(self.src_b), str(self.src_g)]}), encoding="utf-8")
        # A: video thật đủ ①, kèm bản thử 3 phút + clip đã cắt
        _tao(o / "Phim A" / "Phim A_x0.7.mp4")
        _tao(o / "Phim A" / "Phim A_x0.7.srt")
        _tao(o / "Phim A_thu3p" / "Phim A_thu3p_x0.7.mp4")
        _tao(o / "Phim A_thu3p" / "Phim A_thu3p_x0.7_vi_audio.wav")
        _tao(o / "Phim A_thu3p.mp4")
        # B: chỉ có bản thử + clip, nguồn còn nằm ở danh sách chờ
        _tao(o / "Phim B_thu3p" / "Phim B_thu3p_x0.7.mp4")
        _tao(o / "Phim B_thu3p.mp4")
        # C: chỉ có bản thử (hai tốc độ) + clip, nguồn KHÔNG còn ở danh sách chờ
        _tao(o / "Phim C_thu3p" / "Phim C_thu3p_x0.7.mp4")
        _tao(o / "Phim C_thu3p" / "Phim C_thu3p_x0.8.mp4")
        _tao(o / "Phim C_thu3p.mp4")
        # D: bản nháp 60 giây đủ 4 bước (nút 🧪 Thử 60 giây) + clip 60 giây đã cắt
        _tao(o / "Phim D_thu60" / "Phim D_thu60_x0.7.mp4")
        _tao(o / "Phim D_thu60" / "Phim D_thu60_x0.7_sub.mp4")
        _tao(o / "Phim D_thu60.mp4")

    def _bang(self) -> str:
        r = self.c.get("/partials/bang")
        self.assertEqual(r.status_code, 200)
        return r.text

    def _tick(self, bang: str) -> list[str]:
        return re.findall(r'class="tickv" value="([^"]*)"', bang)

    def _cho(self) -> list[str]:
        return json.loads(self.caidat.read_text(encoding="utf-8")).get("cho_chinh") or []

    # ── bản thử không lẫn với video thật ─────────────────────────────────────
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
        self.assertIn("hx-confirm", hang)                                   # ✕ sẽ xoá bản thử → phải hỏi lại
        hang_g = re.search(r'(?s)<tr class="hangcho">(?:(?!</tr>).)*Phim G\.mp4.*?</tr>', bang).group()
        self.assertIn("chưa chạy bước nào", hang_g)
        self.assertNotIn("hx-confirm", hang_g)                              # chưa có gì trong output → khỏi hỏi

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
        self.assertRegex(hang, r'hx-post="/xoa-thu" hx-vals=\'\{"ten": "Phim C"\}\'')
        r = self.c.post("/xoa-thu", data={"ten": "Phim C"}, headers=HX)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(sorted(self.xoa[0]), sorted([self.out / "Phim C_thu3p", self.out / "Phim C_thu3p.mp4"]))
        self.assertNotIn("Phim C", self._bang())
        self.assertEqual(json.loads(r.headers["HX-Trigger"]), {"mvid:daxoa": {"khoa": "phim c"}})

    def test_clip_3_phut_mo_coi_van_co_hang_de_xoa(self):
        """Mở khung 🎛 là cắt ngay output/<tên>_thu3p.mp4; video không còn hàng nào khác thì clip
        này vẫn phải hiện — không thì nằm lại output mà không có chỗ bấm xoá."""
        _tao(self.out / "Phim H_thu3p.mp4")
        bang = self._bang()
        self.assertEqual(bang.count("chỉ còn clip 3 phút đã cắt"), 1)       # clip của A/B/C đã có hàng lo
        hang = re.search(r'(?s)<tr class="hangcho">(?:(?!</tr>).)*Phim H.*?</tr>', bang).group()
        self.assertNotIn("tickv", hang)                                     # không có gì để mở trong 🎛
        self.c.post("/xoa-thu", data={"ten": "Phim H"}, headers=HX)
        self.assertEqual(self.xoa, [[self.out / "Phim H_thu3p.mp4"]])
        self.assertNotIn("Phim H", self._bang())
        # Tên lạ / có dấu đường dẫn: không xoá gì.
        for ten in ("../Phim A", "Khong Co", "Phim A/Phim A"):
            self.c.post("/xoa-thu", data={"ten": ten}, headers=HX)
        self.assertEqual(len(self.xoa), 1)

    def test_video_dai_chi_con_file_doan_van_co_hang_de_xoa(self):
        """Đồ sót của lỗi cũ (🗑 chỉ lấy bản ghép): thư mục vài GB toàn file đoạn mà bảng báo
        "chưa có video nào" — nay vẫn ra một hàng, ghi rõ, bấm 🗑 là hết."""
        f = self.out / "Phim F"
        for ten in ("Phim F_d01_x0.7.mp4", "Phim F_d01_x0.7_sub.mp4", "Phim F_d02_x0.7.mp4"):
            _tao(f / ten)
        (f / "Phim F_d02_x0.7_vi_tts").mkdir()
        rows = {r["base"]: r for r in st.scan_rows(limit=500)}
        self.assertTrue(rows["Phim F/Phim F_x0.7"]["chi_doan"])
        self.assertFalse(rows["Phim A/Phim A_x0.7"]["chi_doan"])
        self.assertEqual([b for b in rows if "_d0" in b], [])               # đoạn không thành hàng riêng
        bang = self._bang()
        self.assertIn("base:Phim F/Phim F_x0.7", self._tick(bang))
        hang = re.search(r'(?s)<tr class="">(?:(?!</tr>).)*Phim F/Phim F_x0\.7.*?</tr>', bang).group()
        self.assertIn("chỉ còn file từng đoạn", hang)
        self.c.post("/xoa", data={"base": "Phim F/Phim F_x0.7"}, headers=HX)
        self.assertEqual(self.xoa, [[f]])
        self.assertNotIn("Phim F", self._bang())
        # Video dài bình thường (còn bản ghép): vẫn một hàng, không mang nhãn đồ sót.
        e = self.out / "Phim E"
        for ten in ("Phim E_x0.7.mp4", "Phim E_x0.7_doan.json", "Phim E_d01_x0.7.mp4"):
            _tao(e / ten)
        rows = [r for r in st.scan_rows(limit=500) if r["base"].startswith("Phim E/")]
        self.assertEqual([(r["base"], r["chi_doan"]) for r in rows], [("Phim E/Phim E_x0.7", False)])

    def test_ban_nhap_60_giay_van_la_hang_co_nhan(self):
        bang = self._bang()
        self.assertIn("base:Phim D_thu60/Phim D_thu60_x0.7", self._tick(bang))
        hang = re.search(r'(?s)<tr class="done">(?:(?!</tr>).)*Phim D_thu60.*?</tr>', bang).group()
        self.assertIn("🧪 thử 60s", hang)
        hang_a = re.search(r'(?s)<tr class="">(?:(?!</tr>).)*Phim A/Phim A_x0\.7.*?</tr>', bang).group()
        self.assertNotIn("nhanthu", hang_a)                                 # video thật không mang nhãn thử
        # 🗑 bản nháp: thư mục của nó + clip 60 giây đã cắt nằm ngoài thư mục.
        self.c.post("/xoa", data={"base": "Phim D_thu60/Phim D_thu60_x0.7"}, headers=HX)
        self.assertEqual(sorted(self.xoa[0]), sorted([self.out / "Phim D_thu60", self.out / "Phim D_thu60.mp4"]))

    # ── xoá ở bảng = dọn sạch video đó khỏi output ───────────────────────────
    def test_xoa_video_that_don_ca_ban_thu_va_nguon_cho(self):
        # Bản xem trước thu nhỏ của clip thử + của file nguồn (đã dựng lúc xem trong khung 🎛).
        xem = [ct.XEM_DIR / f"{ct._ma(p)}.mp4" for p in (self.out / "Phim A_thu3p.mp4", self.src_a)]
        for p in xem:
            _tao(p)
        r = self.c.post("/xoa", data={"base": "Phim A/Phim A_x0.7"}, headers=HX)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(sorted(self.xoa[0]), sorted([self.out / "Phim A", self.out / "Phim A_thu3p",
                                                      self.out / "Phim A_thu3p.mp4"]))
        self.assertEqual([p.name for p in self.out.iterdir() if "Phim A" in p.name], [])   # output sạch bóng A
        self.assertEqual([p for p in xem if p.exists()], [])
        self.assertTrue(self.src_a.is_file())                               # FILE NGUỒN không bao giờ bị đụng
        self.assertNotIn(str(self.src_a), self._cho())                      # hàng không quay lại thành "⏳ mới nạp"
        self.assertIn(str(self.src_b), self._cho())
        self.assertNotIn("Phim A", self._bang())
        # Trang được báo để đóng khung 🎛 đang mở đúng video này.
        self.assertEqual(json.loads(r.headers["HX-Trigger"]), {"mvid:daxoa": {"khoa": "phim a"}})

    def test_xoa_video_dai_don_ca_cac_doan(self):
        e = self.out / "Phim E"
        for ten in ("Phim E_x0.7.mp4", "Phim E_x0.7_sub.mp4", "Phim E_x0.7_doan.json",
                    "Phim E_d01_x0.7.mp4", "Phim E_d01_x0.7_vi.srt", "Phim E_d02_x0.7.mp4",
                    "Phim E_d02_x0.7_sub.mp4"):
            _tao(e / ten)
        (e / "Phim E_d01_x0.7_vi_tts").mkdir()
        self.assertEqual(st.files_of("Phim E/Phim E_x0.7"), [e])             # cả thư mục, không sót đoạn nào
        # Cùng thư mục còn gốc tốc độ khác: chỉ lấy đúng file (kể cả đoạn) của gốc đang xoá.
        _tao(e / "Phim E_x0.8.mp4")
        _tao(e / "Phim E_d01_x0.8.mp4")
        _tao(e / "Phim E_x0.75.mp4")                                         # trùng tiền tố, gốc KHÁC
        _tao(e / "Phim E_d01_x0.75.mp4")
        _tao(self.out / "Phim E_thu3p.mp4")
        lay = sorted(p.name for p in st.files_of("Phim E/Phim E_x0.7"))
        self.assertEqual(lay, sorted(["Phim E_x0.7.mp4", "Phim E_x0.7_sub.mp4", "Phim E_x0.7_doan.json",
                                      "Phim E_d01_x0.7.mp4", "Phim E_d01_x0.7_vi.srt", "Phim E_d01_x0.7_vi_tts",
                                      "Phim E_d02_x0.7.mp4", "Phim E_d02_x0.7_sub.mp4"]))
        r = self.c.post("/xoa", data={"base": "Phim E/Phim E_x0.7"}, headers=HX)
        con = sorted(p.name for p in e.iterdir())
        self.assertEqual(con, ["Phim E_d01_x0.75.mp4", "Phim E_d01_x0.8.mp4", "Phim E_x0.75.mp4", "Phim E_x0.8.mp4"])
        # Video còn gốc khác (0.8) → bản thử của nó giữ lại, khung 🎛 không bị đóng.
        self.assertTrue((self.out / "Phim E_thu3p.mp4").is_file())
        self.assertNotIn("HX-Trigger", r.headers)

    def test_bo_nguon_cho_don_luon_ban_thu(self):
        self.ban[0] = True                                                  # hàng đợi đang chạy → chưa xoá
        r = self.c.post("/nguon/bo", data={"src": str(self.src_b)}, headers=HX)
        self.assertIn("Hàng đợi đang chạy", r.text)
        self.assertEqual(self.xoa, [])
        self.assertIn(str(self.src_b), self._cho())
        # …còn nguồn chưa có gì trong output thì bỏ dòng được ngay cả lúc hàng đợi chạy.
        self.c.post("/nguon/bo", data={"src": str(self.src_g)}, headers=HX)
        self.assertNotIn(str(self.src_g), self._cho())
        self.assertEqual(self.xoa, [])
        self.ban[0] = False
        r = self.c.post("/nguon/bo", data={"src": str(self.src_b)}, headers=HX)
        self.assertEqual(sorted(self.xoa[0]), sorted([self.out / "Phim B_thu3p", self.out / "Phim B_thu3p.mp4"]))
        self.assertNotIn(str(self.src_b), self._cho())
        self.assertTrue(self.src_b.is_file())                               # file nguồn còn nguyên
        self.assertNotIn("Phim B", self._bang())                            # không hiện lại thành hàng "chỉ có bản thử"
        self.assertEqual(json.loads(r.headers["HX-Trigger"]), {"mvid:daxoa": {"khoa": "phim b"}})

    def test_trang_dong_khung_khi_video_bi_xoa(self):
        html = self.c.get("/").text
        self.assertIn('addEventListener("mvid:daxoa"', html)
        khung = self.c.get("/partials/chinhtruoc", params={"id": "base:Phim A/Phim A_x0.7"}).text
        self.assertIn('data-khoa="phim a"', khung)


if __name__ == "__main__":
    unittest.main()
