# -*- coding: utf-8 -*-
"""🎧 Nghe thử cài đặt giọng (06/11/2026) — scripts/taogiong_nghethu.py + route /giongnoi/nghethu.

Mẫu ~30 s giọng gốc lấy từ output_chunks của tập ĐẦU TIÊN trong đợt kịch bản mới nhất, lưu
riêng (xoá kịch bản vẫn còn), có đợt mới thì thay bản cũ; áp tông/bộ lọc/chuẩn âm/âm lượng
bằng ffmpeg thật. kịch_bản/ và thư mục mẫu đều là thư mục TẠM — không đụng dữ liệu thật,
không nạp model, không POST route lưu nào."""
import re
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient

from myvoice.web import core, server   # vá sys.path (scripts/) + import amain_taogiong_gui
import taogiong_nghethu as nt          # noqa: E402

gui = core.gui
hu = gui.hu
SR = 24_000
GIO = 3600.0


def _cau(giay, hz, bien=0.2):
    """Một 'câu' giả: tiếng sin `hz`, 0,1 s im lặng hai mép như model vẫn để."""
    t = np.arange(int(SR * giay)) / SR
    lang = np.zeros(int(0.1 * SR), dtype=np.float32)
    return np.concatenate([lang, (bien * np.sin(2 * np.pi * hz * t)).astype(np.float32), lang])


def _tan_so(wav):
    x, sr = sf.read(str(wav), dtype="float32")
    x = x[: sr * 5]
    return float(np.argmax(np.abs(np.fft.rfft(x))) * sr / len(x))


def _rms(wav, giay=20.0):
    x, sr = sf.read(str(wav), dtype="float32")
    x = x[: int(sr * giay)]
    return float(np.sqrt(np.mean(x.astype("float64") ** 2)))


class _Nen(unittest.TestCase):
    """kịch_bản/ + thư mục mẫu tạm; giờ tạo thư mục tập lấy từ self.luc (đặt tay)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.goc = Path(self.tmp.name)
        self.kb = self.goc / "kịch_bản"
        self.kb.mkdir()
        self.mau = self.goc / "voice" / "nghe_thu"
        self.luc = {}
        for p in (patch.object(gui, "SCRIPT_DIR", self.kb),
                  patch.object(nt, "MAU_DIR", self.mau),
                  patch.object(nt, "_tao_luc", lambda p: self.luc[Path(p).name])):
            p.start()
            self.addCleanup(p.stop)

    def tap(self, ten, hz, luc, so_cau=12, giay=4.0, co_giong=True, chu_ky="chu-ky-1"):
        d = self.kb / ten
        c = d / "output_chunks"
        c.mkdir(parents=True)
        for i in range(so_cau):
            sf.write(str(c / f"{i:04d}.wav"), _cau(giay, hz), SR)
        (c / "_signature.txt").write_text(chu_ky, encoding="utf-8")
        if co_giong:
            sf.write(str(d / "output.wav"), _cau(2.0, hz), SR)
        self.luc[ten] = luc
        return d

    def tep_mau(self):
        return sorted(f.name for f in self.mau.iterdir()) if self.mau.exists() else []


class ChonTapTests(_Nen):
    def test_chua_co_tap_nao(self):
        self.assertIsNone(nt.chon_tap())
        self.assertIsNone(nt.cap_nhat())
        with self.assertRaises(nt.ChuaCoMau):
            nt.nghe_thu()
        self.assertEqual(self.tep_mau(), [])

    def test_tap_dau_tien_cua_dot_moi_nhat(self):
        self.tap("A01 - cũ", 200, 0)
        self.tap("B02 - cũ", 200, 0.2 * GIO)
        self.tap("C03 - mới", 300, 30 * GIO)
        self.tap("D04 - mới", 400, 30.1 * GIO)
        self.assertEqual(nt.chon_tap().name, "C03 - mới")

    def test_dot_vat_qua_nua_dem_van_la_mot_dot(self):
        # 23:50 → 00:20 hôm sau: cách nhau 30 phút, không tách đợt theo ngày lịch.
        self.tap("A01 - x", 200, 23.83 * GIO)
        self.tap("B02 - x", 300, 24.33 * GIO)
        self.assertEqual(nt.chon_tap().name, "A01 - x")

    def test_bo_qua_tap_chua_co_giong(self):
        self.tap("A01 - chưa", 200, 30 * GIO, co_giong=False)      # mới có kịch bản
        self.tap("B02 - có", 300, 30.1 * GIO)
        self.assertEqual(nt.chon_tap().name, "B02 - có")

    def test_thu_muc_khong_phai_tap_bi_bo_qua(self):
        self.tap("output", 200, 99 * GIO)
        self.assertIsNone(nt.chon_tap())


class MauGocTests(_Nen):
    def test_lay_khoang_30_giay_dung_o_cuoi_cau(self):
        self.tap("A07 - thử", 300, 0)
        meta = nt.cap_nhat()
        self.assertEqual(meta["tap"], "07")
        self.assertEqual(meta["thu_muc"], "A07 - thử")
        self.assertGreaterEqual(meta["giay"], nt.MAU_GIAY)
        self.assertLessEqual(meta["giay"], nt.MAU_GIAY_TOI_DA + nt.DUOI_GIAY)
        self.assertFalse(meta["cat_giua_cau"])
        self.assertEqual(meta["so_cau"], 7)        # 7 câu × (4,1 s + nghỉ 0,45) ≥ 30 s
        info = sf.info(str(self.mau / nt.MAU_WAV))
        self.assertEqual(info.samplerate, SR)
        self.assertAlmostEqual(info.duration, meta["giay"], delta=0.02)
        self.assertEqual(self.tep_mau(), ["mau_goc.json", "mau_goc.wav"])
        self.assertEqual(nt.nhan_mau(meta), f"Mẫu: tập 07 · {meta['giay']:.0f} s")

    def test_cau_cuoi_qua_dai_thi_cat_va_vat(self):
        self.tap("A07 - dài", 300, 0, so_cau=3, giay=25.0)
        meta = nt.cap_nhat()
        self.assertTrue(meta["cat_giua_cau"])
        self.assertAlmostEqual(meta["giay"], nt.MAU_GIAY + nt.DUOI_GIAY, delta=0.05)
        x, sr = sf.read(str(self.mau / nt.MAU_WAV), dtype="float32")
        self.assertLess(float(np.abs(x[int((nt.MAU_GIAY - 0.01) * sr):]).max()), 0.02)   # vát về 0

    def test_tap_qua_ngan_khong_lay_duoc(self):
        self.tap("A07 - ngắn", 300, 0, so_cau=1, giay=3.0)
        nhat_ky = []
        self.assertIsNone(nt.cap_nhat(log=nhat_ky.append))
        self.assertIn("chưa lấy được", nhat_ky[0])
        self.assertEqual(self.tep_mau(), [])

    def test_xoa_kich_ban_mau_van_con(self):
        self.tap("A07 - thử", 300, 0)
        meta = nt.cap_nhat()
        shutil.rmtree(self.kb / "A07 - thử")
        self.assertEqual(nt.cap_nhat(), meta)                  # giữ mẫu cũ
        self.assertEqual(nt.doc_mau()["tap"], "07")
        self.assertTrue(nt.nghe_thu()["file"].is_file())       # vẫn nghe được

    def test_dot_moi_co_giong_thi_thay_mau_cu(self):
        self.tap("A07 - cũ", 300, 0)
        cu = nt.cap_nhat()
        nt.nghe_thu(am_luong=3)
        self.assertEqual(len([f for f in self.tep_mau() if f.startswith("xt_")]), 1)

        # Hôm sau: đợt mới, mới có kịch bản chưa có giọng → vẫn mẫu cũ.
        self.tap("G08 - mới", 500, 30 * GIO, co_giong=False)
        self.tap("H09 - mới", 600, 30.1 * GIO, co_giong=False)
        self.assertEqual(nt.cap_nhat()["ma"], cu["ma"])

        # Tập SAU của đợt mới có giọng trước → tạm lấy nó; tập ĐẦU có giọng thì về tập đầu.
        sf.write(str(self.kb / "H09 - mới" / "output.wav"), _cau(2.0, 600), SR)
        self.assertEqual(nt.cap_nhat()["tap"], "09")
        sf.write(str(self.kb / "G08 - mới" / "output.wav"), _cau(2.0, 500), SR)
        nhat_ky = []
        moi = nt.cap_nhat(log=nhat_ky.append)
        self.assertEqual(moi["tap"], "08")
        self.assertIn("thay mẫu tập 09", nhat_ky[0])
        # Chỉ còn MỘT mẫu (bản cũ bị thay), các bản xt_ của mẫu cũ đã xoá, đúng tiếng tập 08.
        self.assertEqual(self.tep_mau(), ["mau_goc.json", "mau_goc.wav"])
        self.assertAlmostEqual(_tan_so(self.mau / nt.MAU_WAV), 500, delta=3)
        self.assertEqual(nt.cap_nhat()["ma"], moi["ma"])       # gọi lại không dựng lại

    def test_tao_lai_giong_tap_do_thi_lay_lai_mau(self):
        d = self.tap("A07 - thử", 300, 0)
        cu = nt.cap_nhat()
        (d / "output_chunks" / "_signature.txt").write_text("chu-ky-2", encoding="utf-8")
        moi = nt.cap_nhat()
        self.assertNotEqual(moi["ma"], cu["ma"])
        self.assertEqual(moi["chu_ky"], "chu-ky-2")

    def test_nghi_theo_dau_cau_khi_so_cau_khop_van_ban(self):
        import dich_input_docx as inputdocx
        import taogiong_chia_cau as chia
        loi = "\n".join(f"Đây là câu số {i} của đoạn văn thử nghiệm, đủ dài để không bị gộp."
                        for i in range(1, 11))
        so_cau = len(chia.split_for_tts(loi, chia.chunk_size_from_options()))
        d = self.tap("A07 - thử", 300, 0, so_cau=so_cau)
        inputdocx.write_input(inputdocx.input_path(d), loi)
        meta = nt.cap_nhat()
        self.assertTrue(meta["nghi_theo_dau"])
        self.assertIn("đây là câu số 1 của đoạn văn", meta["van_ban"])

    def test_ghi_ten_giong_cua_tap(self):
        d = self.tap("A07 - thử", 300, 0)
        nt.ghi_giong(d / "output_chunks", "clone", r"D:\x\giong_mau\ngọc huyền 01.mp3")
        meta = nt.cap_nhat()
        self.assertEqual(meta["giong"], {"che_do": "clone", "giong": "ngọc huyền 01.mp3"})
        self.assertTrue(nt.nhan_mau(meta).endswith("· giọng ngọc huyền 01"))
        nt.ghi_giong(d / "output_chunks", "design", "female, young adult")
        self.assertEqual(nt.ten_giong(nt._doc_json(d / "output_chunks" / nt.GIONG_MARK)), "female, young adult")


class ApCaiDatTests(_Nen):
    def setUp(self):
        super().setUp()
        self.tap("A07 - thử", 300, 0)

    def test_khong_chinh_gi_la_y_nguyen_mau_goc(self):
        kq = nt.nghe_thu()
        self.assertEqual(kq["mo_ta"], "giọng gốc, chưa chỉnh gì")
        self.assertTrue(re.fullmatch(r"xt_[0-9a-f]{12}\.wav", kq["file"].name))
        self.assertEqual(kq["file"].read_bytes(), (self.mau / nt.MAU_WAV).read_bytes())

    def test_am_luong_cong_dung_so_db(self):
        goc = _rms(self.mau / nt.MAU_WAV) if nt.cap_nhat() else 0
        to = nt.nghe_thu(am_luong="+6")
        nho = nt.nghe_thu(am_luong=-6)
        self.assertAlmostEqual(20 * np.log10(_rms(to["file"]) / goc), 6.0, delta=0.15)
        self.assertAlmostEqual(20 * np.log10(_rms(nho["file"]) / goc), -6.0, delta=0.15)
        self.assertEqual(to["mo_ta"], "âm lượng +6.0 dB")

    def test_tong_va_bo_loc_giu_do_dai(self):
        kq = nt.nghe_thu(pitch="2", fx=dict(sang_giong=80, thieu_nien=30))
        self.assertIn("tông +2.0", kq["mo_ta"])
        self.assertIn("sáng giọng 80", kq["mo_ta"])
        self.assertAlmostEqual(sf.info(str(kq["file"])).duration, nt.doc_mau()["giay"], delta=0.3)
        self.assertGreater(_tan_so(kq["file"]), 320)           # 300 Hz đã lên tông
        self.assertNotEqual(kq["file"].read_bytes(), (self.mau / nt.MAU_WAV).read_bytes())

    def test_cung_bo_so_thi_dung_lai_ban_da_dung(self):
        a = nt.nghe_thu(pitch=1, am_luong=3)
        b = nt.nghe_thu(pitch="1,0", am_luong="3.0")
        self.assertTrue(a["moi"])
        self.assertFalse(b["moi"])
        self.assertEqual(a["file"], b["file"])

    def test_chi_giu_vai_ban_moi_nhat_va_khong_sot_file_tam(self):
        cuoi = None
        for db in range(1, nt.XT_GIU + 4):
            cuoi = nt.nghe_thu(am_luong=db)["file"]
        ban = [f for f in self.tep_mau() if f.startswith("xt_")]
        self.assertEqual(len(ban), nt.XT_GIU)
        self.assertIn(cuoi.name, ban)
        self.assertFalse([f for f in self.tep_mau() if ".tmp" in f])


class WebTests(_Nen):
    def setUp(self):
        super().setUp()
        self.c = TestClient(server.app)
        self.c.cookies.set(server.COOKIE, server.TOKEN)
        p = patch.object(server, "log")
        self.log = p.start()
        self.addCleanup(p.stop)

    def test_chua_co_mau_bao_ro_khong_loi_500(self):
        r = self.c.post("/giongnoi/nghethu", data={"pitch": "1"})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["ok"])
        self.assertIn("chưa có tập nào đã tạo giọng", r.json()["loi"])

    def test_tra_duong_phat_va_khong_ghi_cai_dat(self):
        self.tap("A07 - thử", 300, 0)
        truoc = (core.load_options(), core.load_web_settings())
        r = self.c.post("/giongnoi/nghethu", data={
            "pitch": "0", "vang_truong_do": "0", "vang_cuong_do": "0", "thieu_nien": "0",
            "sang_giong": "0", "am_luong_db": "+6", "mode": "clone",
            "voice": "ngọc huyền 01.mp3"})
        j = r.json()
        self.assertTrue(j["ok"], j)
        self.assertEqual(j["mo_ta"], "âm lượng +6.0 dB")
        self.assertTrue(j["mau"].startswith("Mẫu: tập 07 · "))
        self.assertEqual(j["ghi_chu"], [])
        self.assertEqual((core.load_options(), core.load_web_settings()), truoc)
        with patch.object(core, "BASE_DIR", self.goc):          # route phát chỉ mở file trong myvoice/
            a = self.c.get(j["url"])
        self.assertEqual(a.status_code, 200)
        self.assertGreater(len(a.content), 100_000)
        self.assertEqual(a.content[:4], b"RIFF")

    def test_bao_khi_mau_khac_giong_dang_chon(self):
        d = self.tap("A07 - thử", 300, 0)
        nt.ghi_giong(d / "output_chunks", "clone", "ngọc huyền 01.mp3")
        (d / "output_chunks" / gui.FX_MARK).write_text('{"sang_giong": 80}', encoding="utf-8")
        khop = self.c.post("/giongnoi/nghethu", data={
            "mode": "clone", "voice": "ngọc huyền 01.mp3", "sang_giong": "80"}).json()
        self.assertEqual(khop["ghi_chu"], [])
        lech = self.c.post("/giongnoi/nghethu", data={
            "mode": "clone", "voice": "ngọc huyền 02.mp3", "sang_giong": "40"}).json()
        self.assertEqual(len(lech["ghi_chu"]), 2)
        self.assertIn("ngọc huyền 01", lech["ghi_chu"][0])
        self.assertIn("Sáng giọng 80", lech["ghi_chu"][1])

    def test_nut_nghe_thu_nam_trong_hang_cai_dat_tao_giong(self):
        self.tap("A07 - thử", 300, 0)
        nt.cap_nhat()
        with patch.object(server, "_vram", return_value={}):
            html = self.c.get("/").text
        i = html.index('data-fold="gn-caidat"')
        khoi = html[i: html.index('data-fold="gn-ngang"')]
        nut = re.search(r"<button[^>]*data-nghethu[^>]*>", khoi)
        self.assertIsNotNone(nut)
        self.assertIn('type="button"', nut.group())             # không được thành nút gửi form
        self.assertRegex(khoi, r"<audio[^>]*hidden")
        self.assertRegex(khoi, r"data-nghethu-note>Mẫu: tập 07 · \d+ s<")
        self.assertLess(html.index('<form id="voiceform"'), i)

    def test_script_mau_giong_dung_sau_5_o_so_no_doc(self):
        """Script chạy ngay khi trình duyệt đọc tới nó: đặt TRƯỚC 5 ô số thì lúc đó các ô
        chưa có trong DOM → nhãn 🎚 luôn về "Tuỳ chỉnh" khi mở trang (lỗi 02–06/11/2026)."""
        with patch.object(server, "_vram", return_value={}):
            html = self.c.get("/giongnoi").text
        script = html.index("sel.value = khop();")
        for o in ("pitch", "vang_truong_do", "vang_cuong_do", "thieu_nien", "sang_giong"):
            self.assertLess(html.index(f'<input name="{o}"'), script, o)

    def test_js_gui_dung_cac_o_va_nghe_lai_khi_doi(self):
        js = (Path(server.__file__).resolve().parent / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("fetch('/giongnoi/nghethu'", js)
        for o in ("pitch", "vang_truong_do", "vang_cuong_do", "thieu_nien", "sang_giong",
                  "am_luong_db", "mau_giong"):
            self.assertIn(f"'{o}'", js[js.index("Nghe thử cài đặt giọng"):], o)


class _V:
    def __init__(self, v):
        self.v = v

    def set(self, v):
        self.v = v

    def get(self):
        return self.v


class RunTtsTests(_Nen):
    """Cuối bước tạo giọng của một TẬP: ghi tên giọng vào output_chunks + lấy mẫu nghe thử."""

    def _chay(self, output):
        ev = threading.Event()
        ev.set()
        stub = gui._NullWidget()
        # Bỏ bước ASR kiểm mất chữ: chặn import đúng MỘT module (patch.dict cả sys.modules sẽ
        # gỡ luôn torch vừa nạp trong run_tts → lượt sau nạp lại torch là lỗi).
        cu = sys.modules.get("taogiong_kiemtra_matchu", self)
        sys.modules["taogiong_kiemtra_matchu"] = None
        self.addCleanup(lambda: sys.modules.pop("taogiong_kiemtra_matchu", None) if cu is self
                        else sys.modules.__setitem__("taogiong_kiemtra_matchu", cu))
        with patch.multiple(gui, nap_engine=MagicMock(return_value=(object(), SR)),
                               _generate_chunk=MagicMock(return_value=[_cau(5.0, 300)]),
                               do_engine=MagicMock(return_value=None), _tra_vram=MagicMock(),
                               _play_done_sound=MagicMock()), \
                patch.object(gui.logging, "info"), patch.object(gui.logging, "warning"):
            return gui.run_tts("design", "female, young adult", ["câu một.", "câu hai.", "câu ba."],
                               str(output), _V(0), _V(""), stub, stub, stub, ev)

    def test_tao_giong_tap_thi_co_mau_va_ten_giong(self):
        d = self.kb / "A07 - thử"
        d.mkdir()
        self.luc[d.name] = 0
        self.assertTrue(self._chay(d / "output.wav"))
        meta = nt.doc_mau()
        self.assertIsNotNone(meta)
        self.assertEqual(meta["tap"], "07")
        self.assertEqual(meta["so_cau"], 3)
        self.assertEqual(meta["giong"], {"che_do": "design", "giong": "female, young adult"})

    def test_file_ngoai_thu_muc_tap_khong_dung_toi_mau(self):
        d = self.kb / "output"                                    # tab Giọng nói: kịch_bản/output
        d.mkdir()
        self.assertTrue(self._chay(d / "output.wav"))
        self.assertIsNone(nt.doc_mau())


if __name__ == "__main__":
    unittest.main()
