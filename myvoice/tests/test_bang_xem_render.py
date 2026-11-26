# -*- coding: utf-8 -*-
"""Bảng 📼 Kết quả của myvideo (25/11/2026): cột ④ có nút ▶ Xem video và 🔁 Render lại.

User: "có thêm 1 nút mở video hoàn thành lên xem và có 1 nút render lại theo cài đặt mới".
  ▶ Xem video   → /mo-video: mở <gốc>_sub.mp4 bằng trình phát của Windows.
  🔁 Render lại → /render-lai: lưu các ô đang có trên trang rồi xếp lại ĐÚNG bước ④.
Bước ④ ghi thẳng vào _sub.mp4 nên lúc nó đang chạy thì không cho mở (file dở) và không
cho xếp trùng.

Server chạy qua TestClient; output và cài đặt trỏ sang thư mục tạm, dựng lại trước MỖI bài.
Hàng đợi là đồ giả (enqueue chỉ ghi sổ, state trả cái bài thử đặt), os.startfile là đồ giả
— không video nào bật lên, không việc nào chạy thật."""
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
A = "Phim A/Phim A_x0.8"          # đủ 4 bước
B = "Phim B/Phim B_x0.8"          # mới tới bước ③
# Form chính như trang gửi lên (ô tick vắng mặt = tắt) — đủ để nhận ra "có form".
FORM = {"sources": "", "lang": "zh", "speed": "0.8", "model": "large-v3", "kieusub": "nenvang",
        "subchars": "50", "subdong": "2", "vesub": "on", "thaytieng": "on", "chesub": "on"}


def _tao(p: Path, noi_dung: bytes = b"x") -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(noi_dung)
    return p


def _viec(title, steps, step_index=0):
    return {"id": 1, "title": title, "status": "running", "step_index": step_index,
            "step_total": len(steps), "step_label": steps[step_index], "steps": steps,
            "created": "", "started": "", "finished": "", "message": ""}


class BangXemRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="xr_"))
        cls.out = cls.tmp / "output"
        cls.caidat = cls.tmp / "web_settings.json"
        cls.xep, cls.mo = [], []
        cls.tt = {"paused": False, "current": None, "pending": [], "history": [], "busy": False}
        cls._va = [patch.object(sv, "SETTINGS_FILE", cls.caidat),
                   patch.object(sv, "OUTPUT_DIR", cls.out), patch.object(st, "OUTPUT_DIR", cls.out),
                   patch.object(ct, "KHO_FILE", cls.tmp / "chinh_truoc.json"),
                   patch.object(ct, "XEM_DIR", cls.tmp / "xemtruoc"),
                   patch.object(sv.q, "enqueue", lambda title, steps: cls.xep.append((title, steps))),
                   patch.object(sv.q, "state", lambda: cls.tt),
                   patch.object(sv.q, "note", lambda *a, **k: None),
                   patch.object(sv.os, "startfile", lambda p: cls.mo.append(Path(p)), create=True)]
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
        self.xep.clear()
        self.mo.clear()
        self.tt.update(current=None, pending=[])
        shutil.rmtree(self.out, ignore_errors=True)
        o = self.out
        o.mkdir()
        self.caidat.write_text(json.dumps({"kieusub": "hopbo", "zoom": "", "luuy": True,
                                           "logo_kenh": True, "gocdb": "-14"}), encoding="utf-8")
        for duoi in (".mp4", ".srt", "_vi.srt", "_vi_audio.wav", "_vi_sapxep.srt", "_sub.mp4"):
            _tao(o / f"{A}{duoi}")
        for duoi in (".mp4", ".srt", "_vi.srt", "_vi_audio.wav", "_vi_sapxep.srt"):
            _tao(o / f"{B}{duoi}")

    # ── tiện ích ─────────────────────────────────────────────────────────────
    def _hang(self, ten: str) -> str:
        """HTML của hàng mang tên video `ten` trong bảng."""
        bang = self.c.get("/partials/bang")
        self.assertEqual(bang.status_code, 200)
        hang = [h for h in re.findall(r"(?s)<tr class=\"[^\"]*\">.*?</tr>", bang.text)
                if f"/{ten}</a>" in h]                       # ô tên ghi cả gốc "<thư mục>/<tên>"
        self.assertEqual(len(hang), 1, bang.text)
        return hang[0]

    def _nhan(self, r) -> str:
        """Lời nhắn góc phải của một lượt trả lời htmx."""
        self.assertEqual(r.status_code, 200)
        return re.search(r'(?s)hx-swap-oob="innerHTML:#tinnhan">(.*?)</div>', r.text).group(1)

    def _luu(self) -> dict:
        return json.loads(self.caidat.read_text(encoding="utf-8"))

    # ── bảng ─────────────────────────────────────────────────────────────────
    def test_hai_nut_chi_hien_o_hang_da_co_video_hoan_thanh(self):
        a, b = self._hang("Phim A_x0.8"), self._hang("Phim B_x0.8")
        self.assertRegex(a, r'(?s)hx-post="/mo-video"[^>]*>▶ Xem video</button>')
        self.assertRegex(a, r'(?s)hx-post="/render-lai"[^>]*>🔁 Render lại</button>')
        # gửi đúng gốc của hàng; nút render có hỏi lại vì ghi đè video cũ
        self.assertEqual(len(re.findall(r"""hx-vals='\{"base": "Phim A/Phim A_x0.8"\}'""", a)), 4)
        self.assertRegex(a, r'(?s)hx-post="/render-lai".*?hx-confirm="[^"]*GHI ĐÈ')
        self.assertNotRegex(a, r'(?s)hx-post="/mo-video"[^>]*hx-confirm')
        for nut in ("/mo-video", "/render-lai", "Xem video", "Render lại"):
            self.assertNotIn(nut, b)
        bang = self.c.get("/partials/bang").text
        self.assertNotIn("<form", bang)                        # khối nằm trong form chính
        self.assertIn("<b>▶ Xem video</b>", bang)              # dòng chú thích dưới bảng
        self.assertIn("<b>🔁 Render lại</b>", bang)

    # ── ▶ Xem video ──────────────────────────────────────────────────────────
    def test_xem_video_mo_dung_file_hoan_thanh(self):
        r = self.c.post("/mo-video", data={"base": A, **FORM}, headers=HX)
        self.assertEqual(self.mo, [self.out / f"{A}_sub.mp4"])
        self.assertIn("Đã mở Phim A_x0.8_sub.mp4", self._nhan(r))
        self.assertEqual(self.xep, [])                         # xem không xếp việc gì
        self.assertEqual(self._luu()["kieusub"], "hopbo")      # …và không đụng cài đặt

    def test_xem_video_chua_co_thanh_pham_thi_bao_khong_mo_video_buoc_1(self):
        r = self.c.post("/mo-video", data={"base": B}, headers=HX)
        self.assertEqual(self.mo, [])
        self.assertIn("chưa có video hoàn thành", self._nhan(r))
        self.assertIn("chạy bước ④ trước", self._nhan(r))

    def test_xem_video_chi_co_ban_doc_thi_mo_ban_doc(self):
        (self.out / f"{A}_sub.mp4").unlink()
        _tao(self.out / f"{A}_doc.mp4")
        self.c.post("/mo-video", data={"base": A}, headers=HX)
        self.assertEqual(self.mo, [self.out / f"{A}_doc.mp4"])

    def test_xem_video_ten_la_thi_tu_choi(self):
        for ten in ("", "../x_x0.8", "khong co tag", "a/b/c_x0.8"):
            r = self.c.post("/mo-video", data={"base": ten}, headers=HX)
            self.assertIn("Tên không hợp lệ", self._nhan(r), ten)
        self.assertEqual(self.mo, [])

    def test_mo_thu_muc_van_chon_san_nhu_cu(self):
        self.assertEqual(sv._video_de_xem(A), self.out / f"{A}_sub.mp4")
        self.assertEqual(sv._video_de_xem(B), self.out / f"{B}.mp4")     # chưa dựng → video ①
        self.assertIsNone(sv._video_xong(B))
        self.assertIsNone(sv._video_de_xem("Phim Z/Phim Z_x0.8"))

    # ── 🔁 Render lại ────────────────────────────────────────────────────────
    def test_render_lai_luu_cai_dat_tren_trang_roi_xep_dung_buoc_4(self):
        form = {**FORM, "kieusub": "nenvang", "zoom": "15", "subvitri": "20"}   # vừa chỉnh, chưa 💾
        r = self.c.post("/render-lai", data={"base": A, **form}, headers=HX)
        self.assertIn("Đã xếp render lại Phim A_x0.8", self._nhan(r))
        self.assertIn("đã lưu cài đặt", self._nhan(r))
        luu = self._luu()
        self.assertEqual((luu["kieusub"], luu["zoom"], luu["subvitri"]), ("nenvang", "15", "20"))
        self.assertFalse(luu["luuy"])                          # ô tick vắng trong form = đã tắt
        self.assertEqual(luu["gocdb"], "-14")                  # khoá của tab 🔊: form không có ô → giữ
        self.assertIn("mvid:xong", r.headers.get("hx-trigger", ""))      # trang bỏ dấu "chưa lưu"
        self.assertEqual(len(self.xep), 1)
        title, steps = self.xep[0]
        self.assertEqual(title, f"{A} — 🔁 render lại ④")
        self.assertEqual(len(steps), 1)                        # ĐÚNG một bước ④, không ①②③
        argv = steps[0].argv
        self.assertTrue(steps[0].label.startswith("④"))
        self.assertIn(str(self.out / f"{A}.mp4"), argv)
        self.assertEqual(argv[argv.index("--kieu") + 1], "nenvang")      # theo cài đặt MỚI
        self.assertEqual(argv[argv.index("--zoom") + 1], "15")
        self.assertEqual(argv[argv.index("--vitri") + 1], "20")
        self.assertEqual(argv[argv.index("--goc-db") + 1], "-14")
        self.assertEqual(argv[argv.index("--audio") + 1], str(self.out / f"{A}_vi_audio.wav"))
        self.assertNotIn("--luuy", argv)
        self.assertEqual(self.mo, [])

    def test_render_lai_khong_kem_form_thi_dung_cai_dat_dang_luu_khong_ghi_de(self):
        truoc = self._luu()
        r = self.c.post("/render-lai", data={"base": A}, headers=HX)
        self.assertIn("Đã xếp render lại", self._nhan(r))
        self.assertNotIn("đã lưu cài đặt", self._nhan(r))
        self.assertEqual(self._luu(), truoc)                   # form rỗng không được xoá ô tick
        self.assertNotIn("mvid:xong", r.headers.get("hx-trigger", ""))
        argv = self.xep[0][1][0].argv
        self.assertEqual(argv[argv.index("--kieu") + 1], "hopbo")
        self.assertIn("--luuy", argv)

    def test_render_lai_thieu_dau_vao_thi_bao_ro_khong_xep(self):
        (self.out / f"{A}_vi_audio.wav").unlink()
        r = self.c.post("/render-lai", data={"base": A, **FORM}, headers=HX)
        self.assertIn("Chưa có Phim A_x0.8_vi_audio.wav — chạy bước ③ trước", self._nhan(r))
        self.assertEqual(self.xep, [])
        r = self.c.post("/render-lai", data={"base": "../x_x0.8", **FORM}, headers=HX)
        self.assertIn("Tên không hợp lệ", self._nhan(r))
        self.assertEqual(self.xep, [])

    # ── bước ④ của hàng đang nằm trong hàng đợi ──────────────────────────────
    def test_da_xep_chua_toi_luot_thi_van_xem_duoc_nhung_khong_xep_trung(self):
        self.tt["pending"] = [_viec(f"{A} — 🔁 render lại ④", ["④ Vẽ sub cứng + thay tiếng"])]
        a = self._hang("Phim A_x0.8")
        self.assertIn("⏳ đã xếp render lại", a)
        self.assertIn("▶ Xem video", a)                        # video cũ còn nguyên
        self.assertNotIn("/render-lai", a)
        r = self.c.post("/render-lai", data={"base": A, **FORM, "kieusub": "nenvang"}, headers=HX)
        self.assertIn("ĐÃ nằm trong hàng đợi", self._nhan(r))
        self.assertEqual(self.xep, [])
        self.assertEqual(self._luu()["kieusub"], "hopbo")      # bị từ chối thì chưa lưu gì
        self.c.post("/mo-video", data={"base": A}, headers=HX)
        self.assertEqual(self.mo, [self.out / f"{A}_sub.mp4"])
        self.tt["pending"] = []                                # lượt đó xong → nút render hiện lại
        self.assertIn("/render-lai", self._hang("Phim A_x0.8"))

    def test_dang_dung_thi_khong_mo_file_do_va_o_ghi_ro_ly_do(self):
        self.tt["current"] = _viec(f"{A} — 🔁 render lại ④", ["④ Vẽ sub cứng + thay tiếng"])
        a = self._hang("Phim A_x0.8")
        self.assertIn("⏳ đang render — xong mới xem được", a)   # lý do nằm ngay trong ô
        for nut in ("/mo-video", "/render-lai", "Xem video", "Render lại"):
            self.assertNotIn(nut, a)
        r = self.c.post("/mo-video", data={"base": A}, headers=HX)
        self.assertIn("đang dựng lại", self._nhan(r))
        self.assertEqual(self.mo, [])
        r = self.c.post("/render-lai", data={"base": A, **FORM}, headers=HX)
        self.assertIn("ĐÃ nằm trong hàng đợi", self._nhan(r))
        self.assertEqual(self.xep, [])
        # hàng khác không bị vạ lây
        self.assertNotIn("⏳", self._hang("Phim B_x0.8"))

    def test_nhan_ra_viec_cua_hang_theo_moi_kieu_tieu_de(self):
        b4 = ["① Chậm video + SRT tiếng Trung", "② Dịch Gemini → SRT tiếng Việt",
              "③ Tạo giọng (VieNeu, CPU) + xếp timeline", "④ Vẽ sub cứng + thay tiếng",
              "④ 📱 Bản dọc 9:16 (TikTok/Shorts)"]
        tt = lambda cur=None, pend=(): {"current": cur, "pending": list(pend)}   # noqa: E731
        # ▶ Chạy tất cả ghi TÊN TRẦN; đang ở bước ③ → chưa đụng file thành phẩm
        self.assertEqual(sv._dang_dung(A, tt(_viec("Phim A_x0.8 — ▶ ①②③④", b4, 2))), "cho")
        self.assertEqual(sv._dang_dung(A, tt(_viec("Phim A_x0.8 — ▶ ①②③④", b4, 3))), "chay")
        self.assertEqual(sv._dang_dung(A, tt(_viec("Phim A_x0.8 — ▶ ①②③④", b4, 4))), "chay")
        self.assertEqual(sv._dang_dung(B, tt(_viec("Phim A_x0.8 — ▶ ①②③④", b4, 3))), "")
        # tốc độ khác của cùng video là hàng khác
        self.assertEqual(sv._dang_dung("Phim A/Phim A_x0.7", tt(_viec("Phim A_x0.8 — ▶ ①②③④", b4, 3))), "")
        # việc không có bước ④ (chạy lẻ ③, 🧪 thử 3 phút) không khoá gì
        self.assertEqual(sv._dang_dung(A, tt(_viec(f"{A} — ③", b4[2:3]))), "")
        self.assertEqual(sv._dang_dung(A, tt(pend=[_viec(f"{A} — ③", b4[2:3])])), "")
        self.assertEqual(sv._dang_dung(A, tt(pend=[_viec(f"{A} — ⏩ ②📑③④", b4[1:4])])), "cho")
        # 🧪 thử 60s ghi tên FILE NGUỒN → hàng bản nháp <tên>_thu60
        nhap = "Phim D_thu60/Phim D_thu60_x0.8"
        viec = _viec("Phim D.mp4 — 🧪 thử 60s ①②③④", ["✂ Cắt 60 giây đầu", *b4[:4]], 4)
        self.assertEqual(sv._dang_dung(nhap, tt(viec)), "chay")
        self.assertEqual(sv._dang_dung("Phim D/Phim D_x0.8", tt(viec)), "")
        self.assertEqual(sv._dang_dung(A, tt()), "")


if __name__ == "__main__":
    unittest.main()
