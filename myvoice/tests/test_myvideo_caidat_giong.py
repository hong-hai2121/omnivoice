# -*- coding: utf-8 -*-
"""myvideo mang trọn bộ cài đặt giọng của myvoice sang (09/11/2026): 🔊 âm lượng dB (khoá am_luong_db → taogiong_srt.py --am-luong, cộng ở bước cuối
hau_ky_audio), 🎚 mẫu giọng (bảng hu.MAU_GIONG vào trang, không lưu), 🎧 nghe thử cài đặt
trên ~30 s giọng thật (taogiong_nghethu_srt.py + route /nghethu, /nghe/caidat), và các ô
tông/vang/thiếu niên đứng ngoài khối giọng mẫu.

Không nạp model. output/ và thư mục mẫu đều là thư mục TẠM. ffmpeg thật chỉ ở phần nghe
thử (tiếng sin giả)."""
import asyncio
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile as sf
from starlette.datastructures import FormData

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(REPO / "myvideo") not in sys.path:
    sys.path.insert(0, str(REPO / "myvideo"))
import taogiong_srt as ts  # noqa: E402  (tự chèn myvoice/scripts, kéo amain_taogiong_gui)
import taogiong_nghethu_srt as nt  # noqa: E402
import hieuung_giong as hu  # noqa: E402
# Import server myvideo mà KHÔNG cho luồng nền khởi động.
import gc  # noqa: E402
import threading  # noqa: E402
gc.collect()
with patch.object(threading.Thread, "start", lambda self: None):
    from myvideo.web import steps as st, server as sv  # noqa: E402

SR = 48_000
GIO = 3600.0


def _cau(giay, hz, bien=0.2):
    """Một 'câu' giả: tiếng sin `hz`, 0,1 s im lặng hai mép như engine vẫn để."""
    t = np.arange(int(SR * giay)) / SR
    lang = np.zeros(int(0.1 * SR), dtype=np.float32)
    return np.concatenate([lang, (bien * np.sin(2 * np.pi * hz * t)).astype(np.float32), lang])


def _rms(wav, giay=20.0):
    x, sr = sf.read(str(wav), dtype="float32")
    x = x[: int(sr * giay)]
    return float(np.sqrt(np.mean(x.astype("float64") ** 2)))


# ── taogiong_srt: --am-luong + hau_ky_audio ─────────────────────────────────────
class TestHauKyAudio(unittest.TestCase):
    def _goi(self, **kw):
        goi = []
        with patch.object(ts.hu, "apply_fx_file", lambda f, **k: goi.append(("fx", k))), \
                patch.object(ts.hu, "apply_amluong_file", lambda f, db: goi.append(("amluong", db))):
            kq = ts.hau_ky_audio(Path("x.wav"), log=lambda s: None, **kw)
        return goi, kq

    def test_thu_tu_tong_am_luong(self):
        goi, kq = self._goi(pitch=1, fx=dict(sang_giong=80), am_luong="+3")
        self.assertEqual([g[0] for g in goi], ["fx", "amluong"])     # không còn bước loudnorm
        self.assertEqual(goi[0][1]["pitch"], 1.0)
        self.assertEqual(goi[0][1]["sang_giong"], 80)
        self.assertEqual(goi[1][1], 3.0)
        self.assertEqual((kq["pitch"], kq["am_luong"]), (1.0, 3.0))
        self.assertNotIn("chuan_am", kq)

    def test_mac_dinh_khong_dung_gi(self):
        goi, kq = self._goi()
        self.assertEqual(goi, [])
        self.assertEqual(kq["am_luong"], 0.0)

    def test_am_luong_kep_va_doc_dau_phay(self):
        goi, kq = self._goi(am_luong="2,5")
        self.assertEqual(goi, [("amluong", 2.5)])
        goi, kq = self._goi(am_luong=99)
        self.assertEqual(goi, [("amluong", hu.AMLUONG_MAX)])

    def test_loi_am_luong_khong_lam_hong_buoc_truoc(self):
        def no(f, db):
            raise RuntimeError("ffmpeg hỏng")
        nhat_ky = []
        with patch.object(ts.hu, "apply_amluong_file", no):
            kq = ts.hau_ky_audio(Path("x.wav"), am_luong=3, log=nhat_ky.append)
        self.assertEqual(kq["am_luong"], 3.0)
        self.assertTrue(any("Không đổi được âm lượng" in s for s in nhat_ky))

    def test_logging_khong_bi_cau_hinh_lai_khi_import(self):
        """Module import từ web không được gọi logging.basicConfig(force=True)."""
        src = (REPO / "myvideo" / "taogiong_srt.py").read_text(encoding="utf-8")
        i = src.index("logging.basicConfig(")
        self.assertIn('if __name__ == "__main__":', src[i - 400:i])


class TestSteps(unittest.TestCase):
    def _argv(self, s):
        with tempfile.TemporaryDirectory() as td:
            b = Path(td) / "tap1"
            (b.parent / "tap1_vi.srt").write_text("", encoding="utf-8")
            steps = st._steps_for(["giong"], "x.mp4", b, s)
        self.assertEqual(len(steps), 1)
        return steps[0].argv

    def test_am_luong_truyen_cho_buoc_3(self):
        a = self._argv({"am_luong_db": "3"})
        self.assertEqual(a[a.index("--am-luong") + 1], "3")
        self.assertNotIn("--engine", a)              # mặc định omni: lệnh không có --engine (chỉ thêm khi chọn VieNeu, 11/11/2026)
        a = self._argv({"voice": "mau.wav", "am_luong_db": "-2.5"})
        self.assertEqual(a[a.index("--am-luong") + 1], "-2.5")
        self.assertEqual(a[a.index("--voice") + 1], "mau.wav")

    def test_thieu_khoa_thi_0(self):
        a = self._argv({})
        self.assertEqual(a[a.index("--am-luong") + 1], "0")


# ── Server: mặc định, form, trang, route nghe thử ───────────────────────────────
class TestServer(unittest.TestCase):
    def test_mac_dinh(self):
        self.assertEqual(sv.DEFAULTS["am_luong_db"], "0")

    def test_form_am_luong(self):
        s = sv._settings_from_form(FormData([("am_luong_db", "+3")]))
        self.assertEqual(s["am_luong_db"], "3")
        s = sv._settings_from_form(FormData([("am_luong_db", "2,7")]))
        self.assertEqual(s["am_luong_db"], "2.5")
        s = sv._settings_from_form(FormData([("am_luong_db", "50")]))
        self.assertEqual(float(s["am_luong_db"]), hu.AMLUONG_MAX)
        s = sv._settings_from_form(FormData([]))
        self.assertEqual(s["am_luong_db"], "0")
        # ô 🎚 mẫu giọng không được lưu thành cài đặt
        s = sv._settings_from_form(FormData([("mau_giong", "Sáng rõ")]))
        self.assertNotIn("mau_giong", s)

    def _trang(self, settings=None):
        from starlette.requests import Request
        scope = {"type": "http", "method": "GET", "path": "/", "headers": [], "query_string": b"",
                 "app": sv.app, "router": sv.app.router, "scheme": "http", "server": ("127.0.0.1", 1)}
        with patch.object(sv, "load_settings", lambda: {**sv.DEFAULTS, **(settings or {})}):
            r = asyncio.run(sv.index(Request(scope)))
        self.assertEqual(r.status_code, 200)
        return r.body.decode("utf-8")

    def test_trang_co_du_o_va_ngoai_khoi_clone(self):
        h = self._trang({"am_luong_db": "4"})
        self.assertIn('name="am_luong_db" value="4"', h)
        self.assertIn('name="mau_giong"', h)
        for ten in hu.mau_ten():
            self.assertIn(f'<option value="{ten}">', h)
        self.assertIn(f'value="{hu.MAU_TUY_CHINH}"', h)
        self.assertIn('id="nghethuNut"', h)
        self.assertIn('id="nghethuAudio"', h)
        self.assertIn('/nghethu', h)
        # Các ô tông/vang/thiếu niên đứng trong khối cài đặt chung, SAU khối giọng mẫu
        # (ô cài đặt không nằm trong khối giọng mẫu).
        clone = h.index('id="khoiClone"')
        caidat = h.index('id="khoiCaiDat"')
        self.assertLess(clone, caidat)
        for ten in ("pitch", "vang_truong_do", "vang_cuong_do", "thieu_nien", "am_luong_db"):
            self.assertGreater(h.index(f'name="{ten}"'), caidat, ten)
        self.assertIn('id="pitches"', h)
        self.assertIn('id="amluongs"', h)

    def test_nghe_caidat_tu_choi_ten_la(self):
        self.assertEqual(asyncio.run(sv.nghe_caidat(f="../web_settings.json")).status_code, 404)
        self.assertEqual(asyncio.run(sv.nghe_caidat(f="mau_goc.wav")).status_code, 404)
        with patch.object(nt, "MAU_DIR", Path(tempfile.gettempdir()) / "khong_co_mau_x"):
            self.assertEqual(asyncio.run(sv.nghe_caidat(f="xt_0123456789ab.wav")).status_code, 404)


# ── taogiong_nghethu_srt: chọn video, lấy mẫu, áp cài đặt ───────────────────────
class _Nen(unittest.TestCase):
    """output/ + thư mục mẫu tạm; giờ tạo thư mục _tts lấy từ self.luc (đặt tay)."""

    def setUp(self):
        self.td = Path(tempfile.mkdtemp(prefix="mv_nghethu_"))
        self.out = self.td / "output"
        self.out.mkdir()
        self.mau = self.td / "mau"
        self.luc = {}
        self._p = [patch.object(nt, "OUTPUT_DIR", self.out), patch.object(nt, "MAU_DIR", self.mau),
                   patch.object(nt, "_tao_luc", lambda p: self.luc.get(str(Path(p)), 0.0))]
        for p in self._p:
            p.start()

    def tearDown(self):
        for p in self._p:
            p.stop()
        shutil.rmtree(self.td, ignore_errors=True)

    def tao_video(self, ten, luc, so_cau=12, giay=3.0, hz=440.0, giong="clone|mau.wav",
                  sang=0, cau_rong=()):
        """output/<ten>/<ten>_x0.7_vi_tts/0001.wav… + _vanban.json; trả thư mục _tts."""
        d = self.out / ten / f"{ten}_x0.7_vi_tts"
        d.mkdir(parents=True)
        cau = []
        for i in range(so_cau):
            cau.append("" if i in cau_rong else f"câu số {i + 1}.")
            if i in cau_rong:
                continue
            sf.write(str(d / f"{i + 1:04d}.wav"), _cau(giay, hz), SR, subtype="PCM_16")
        (d / nt.SO_VAN_BAN).write_text(json.dumps({"sang": sang, "giong": giong, "cau": cau},
                                                  ensure_ascii=False), encoding="utf-8")
        self.luc[str(d)] = luc
        return d


class TestChonVideo(_Nen):
    def test_dau_dot_moi_nhat(self):
        t0 = 1_800_000_000.0
        self.tao_video("a", t0)
        self.tao_video("b", t0 + 1 * GIO)
        self.tao_video("c", t0 + 10 * GIO)           # đợt mới
        self.tao_video("d", t0 + 11 * GIO)
        self.assertEqual(nt.ten_video(nt.chon_video()), "c_x0.7")

    def test_bo_qua_video_chua_co_giong(self):
        t0 = 1_800_000_000.0
        self.tao_video("a", t0)
        d = self.tao_video("b", t0 + 10 * GIO)
        (d / nt.SO_VAN_BAN).write_text("[]", encoding="utf-8")      # sổ trống = đang đọc lại dở
        self.assertEqual(nt.ten_video(nt.chon_video()), "a_x0.7")
        self.assertFalse(nt.co_giong(d))

    def test_khong_co_gi(self):
        self.assertIsNone(nt.chon_video())
        self.assertIsNone(nt.cap_nhat())

    def test_ket_qua_cu_dang_phang(self):
        d = self.out / "cu_x0.7_vi_tts"
        d.mkdir()
        for i in range(4):
            sf.write(str(d / f"{i + 1:04d}.wav"), _cau(3.0, 440.0), SR, subtype="PCM_16")
        (d / nt.SO_VAN_BAN).write_text(json.dumps(["a.", "b.", "c.", "d."]), encoding="utf-8")
        self.luc[str(d)] = 1.0
        self.assertEqual(nt.chon_video(), d)
        self.assertEqual(nt.doc_so(d)["giong"], "")
        self.assertEqual(nt.ten_video(d), "cu_x0.7")


class TestTaoMau(_Nen):
    def test_mau_du_30s_dung_cuoi_cau(self):
        d = self.tao_video("a", 1.0, so_cau=20, giay=3.0)
        meta = nt.tao_mau(d)
        self.assertEqual(meta["video"], "a_x0.7")
        self.assertEqual(meta["giong"], "clone|mau.wav")
        self.assertGreaterEqual(meta["giay"], nt.MAU_GIAY)
        self.assertLessEqual(meta["giay"], nt.MAU_GIAY_TOI_DA + 1)
        self.assertFalse(meta["cat_giua_cau"])
        self.assertTrue(meta["nghi_theo_dau"])
        self.assertIn("câu số 1.", meta["van_ban"])
        self.assertTrue((self.mau / nt.MAU_WAV).is_file())
        self.assertEqual(nt.doc_mau()["ma"], meta["ma"])
        self.assertIn("Mẫu: video a_x0.7", nt.nhan_mau(meta))
        self.assertIn("giọng mau", nt.nhan_mau(meta))

    def test_cau_rong_khong_co_wav_thi_nhay_qua(self):
        d = self.tao_video("a", 1.0, so_cau=16, giay=3.0, cau_rong=(1, 2))
        meta = nt.tao_mau(d)
        self.assertGreaterEqual(meta["giay"], nt.MAU_GIAY)
        self.assertNotIn("câu số 2.", meta["van_ban"])
        self.assertIn("câu số 4.", meta["van_ban"])

    def test_chua_du_giong_thi_bao(self):
        d = self.tao_video("a", 1.0, so_cau=2, giay=1.0)
        with self.assertRaises(nt.ChuaCoMau):
            nt.tao_mau(d)

    def test_ten_giong_clone(self):
        self.assertEqual(nt.ten_giong("clone|ngọc huyền 01.wav"), "ngọc huyền 01")
        self.assertEqual(nt.ten_giong("vieneu|Mai Anh"), "Mai Anh")   # sổ của bản VieNeu cũ vẫn đọc được
        self.assertEqual(nt.ten_giong(""), "")
        self.assertEqual(nt.che_do_giong("clone|a.wav"), ("clone", "a.wav"))


class TestCapNhat(_Nen):
    def test_thay_mau_khi_doi_dot_hay_doi_giong(self):
        t0 = 1_800_000_000.0
        self.tao_video("a", t0)
        m1 = nt.cap_nhat()
        self.assertEqual(m1["video"], "a_x0.7")
        self.assertEqual(nt.cap_nhat()["ma"], m1["ma"])   # không đổi → vẫn mẫu đang lưu
        # đợt mới có giọng → thay mẫu, bản xt_ cũ bị xoá
        (self.mau / "xt_0123456789ab.wav").write_bytes(b"0" * 5000)
        self.tao_video("b", t0 + 10 * GIO, hz=880.0)
        m2 = nt.cap_nhat()
        self.assertEqual(m2["video"], "b_x0.7")
        self.assertFalse((self.mau / "xt_0123456789ab.wav").exists())
        # cùng video nhưng đọc lại bằng giọng khác (sổ đổi) → thay mẫu
        d = self.out / "b" / "b_x0.7_vi_tts"
        so = json.loads((d / nt.SO_VAN_BAN).read_text(encoding="utf-8"))
        so["giong"] = "clone|mau.wav"
        time.sleep(1.1)                                 # mtime sổ chắc chắn đổi (độ phân giải 1 s)
        (d / nt.SO_VAN_BAN).write_text(json.dumps(so), encoding="utf-8")
        m3 = nt.cap_nhat()
        self.assertNotEqual(m3["ma"], m2["ma"])
        self.assertEqual(m3["giong"], "clone|mau.wav")


class TestNgheThu(_Nen):
    def setUp(self):
        super().setUp()
        self.tao_video("a", 1.0, so_cau=14, giay=3.0)

    def test_am_luong_6db_to_gap_doi_va_cache(self):
        goc = nt.nghe_thu()
        self.assertEqual(goc["mo_ta"], "giọng gốc, chưa chỉnh gì")
        self.assertTrue(nt.la_ban_nghe(goc["file"].name))
        to = nt.nghe_thu(am_luong=6)
        self.assertIn("âm lượng +6.0 dB", to["mo_ta"])
        self.assertTrue(to["moi"])
        ty = _rms(to["file"]) / _rms(goc["file"])
        self.assertAlmostEqual(ty, 2.0, delta=0.2)      # +6 dB ≈ ×2 (có bộ chặn đỉnh)
        lai = nt.nghe_thu(am_luong=6)
        self.assertFalse(lai["moi"])
        self.assertEqual(lai["file"], to["file"])

    def test_don_ban_cu_giu_XT_GIU(self):
        for db in range(0, 9):
            nt.nghe_thu(am_luong=db)
        ban = [f for f in self.mau.iterdir() if nt.la_ban_nghe(f.name)]
        self.assertEqual(len(ban), nt.XT_GIU)

    def test_route_nghethu_tra_url_phat_duoc(self):
        r = sv.nghethu(pitch="0", vang_truong_do="0", vang_cuong_do="0", thieu_nien="0",
                       sanggiong="0", am_luong_db="3", voice="mau.wav")
        j = json.loads(r.body)
        self.assertTrue(j["ok"], j)
        self.assertIn("âm lượng +3.0 dB", j["mo_ta"])
        self.assertIn("Mẫu: video a_x0.7", j["mau"])
        self.assertEqual(j["ghi_chu"], [])                 # cùng giọng với mẫu
        self.assertTrue(j["url"].startswith("/nghe/caidat?f=xt_"))
        ten = j["url"].split("f=")[1]
        self.assertEqual(asyncio.run(sv.nghe_caidat(f=ten)).status_code, 200)
        # chọn giọng khác → ghi chú; ô giọng trống (tự lấy file đầu) → không ghi chú
        r = sv.nghethu(voice="khac.wav")
        self.assertEqual(len(json.loads(r.body)["ghi_chu"]), 1)
        r = sv.nghethu(voice="")
        self.assertEqual(json.loads(r.body)["ghi_chu"], [])

    def test_route_chua_co_mau(self):
        shutil.rmtree(self.out)
        self.out.mkdir()
        r = sv.nghethu()
        j = json.loads(r.body)
        self.assertFalse(j["ok"])
        self.assertIn("bước ③", j["loi"])


if __name__ == "__main__":
    unittest.main()
