# -*- coding: utf-8 -*-
"""YouTube Short: dòng chữ dưới là 'Tập Số N' (20/11/2026) thay cho "Nghe trọn tập tại kênh
Mimi audio" của bản dọc/TikTok. Chữ đã nung vào hình nên Short phải dựng lại hình từ video
gốc + lớp phủ riêng; thiếu video gốc thì lùi về cắt thẳng từ TikTok.
Dựng tập giả 3 giây bằng ffmpeg (không nạp model, không đụng kịch_bản/ thật)."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageChops

from myvoice.web import core   # noqa: F401 — vá sys.path (scripts/)

import video_doc_khung as vdk  # noqa: E402
import video_short as vs  # noqa: E402

FFMPEG = shutil.which("ffmpeg")
DAI = 3          # giây


def _ff(*args) -> None:
    subprocess.run([FFMPEG, "-y", "-v", "error", *args], check=True, timeout=180)


def _hang_chu(img: Image.Image, che: bool = False):
    """Khoảng x (trái, phải) của nét chữ TRẮNG trên hàng dòng dưới (cta_y ± 30); None = trống."""
    y = vdk.bo_cuc(che)["cta_y"]
    hang = img.convert("L").crop((0, y - 30, vdk.W, y + 30)).point(lambda v: 255 if v > 235 else 0)
    box = hang.getbbox()
    return (box[0], box[2]) if box else None


def _hang_tren(img: Image.Image, che: bool = False):
    """Khoảng x của nét chữ TRẮNG ngang hàng logo, tính từ x=300 (bên phải logo); None = trống."""
    y = vdk.bo_cuc(che)["logo"][1] + vdk.LOGO_H // 2
    hang = img.convert("L").crop((300, y - 20, vdk.W, y + 20)).point(lambda v: 255 if v > 235 else 0)
    box = hang.getbbox()
    return (box[0] + 300, box[2] + 300) if box else None


class DongChuSoTapTests(unittest.TestCase):
    def test_cta_short(self):
        self.assertEqual(vdk.cta_short("188"), "Tập Số 188")
        self.assertEqual(vdk.cta_short("07"), "Tập Số 7")
        self.assertEqual(vdk.cta_short(12), "Tập Số 12")
        self.assertIsNone(vdk.cta_short(""))
        self.assertIsNone(vdk.cta_short(None))

    def test_lop_phu_chi_doi_dong_duoi(self):
        with tempfile.TemporaryDirectory() as d:
            cu = Image.open(vdk.ve_lop_tap("tím", "188", "Tiêu Đề Thử", Path(d) / "cu.png"))
            moi = Image.open(vdk.ve_lop_tap("tím", "188", "Tiêu Đề Thử", Path(d) / "moi.png",
                                            cta=vdk.cta_short("188")))
            y = vdk.bo_cuc(False)["cta_y"]
            tren = (0, 0, vdk.W, y - 60)             # logo + tiêu đề + dải video: không đổi
            self.assertEqual(cu.crop(tren).tobytes(), moi.crop(tren).tobytes())
            x_cu, x_moi = _hang_chu(cu), _hang_chu(moi)
            self.assertIsNotNone(x_moi)
            # "Tập Số 188" ngắn hơn hẳn "Nghe trọn tập tại kênh Mimi audio", vẫn canh giữa.
            self.assertLess(x_moi[1] - x_moi[0], (x_cu[1] - x_cu[0]) * 0.6)
            self.assertAlmostEqual((x_moi[0] + x_moi[1]) / 2, vdk.W / 2, delta=6)

    def test_dong_tren_tieu_de(self):
        """Short ghi thêm dòng số tập PHÍA TRÊN tiêu đề (ngang hàng logo); bản dọc/TikTok thì không."""
        for che in (False, True):
            with tempfile.TemporaryDirectory() as d:
                so = vdk.cta_short("188")
                thuong = Image.open(vdk.ve_lop_tap("tím", "188", "Tiêu Đề Thử", Path(d) / "a.png", che=che))
                short = Image.open(vdk.ve_lop_tap("tím", "188", "Tiêu Đề Thử", Path(d) / "b.png",
                                                  che=che, cta=so, dong_tren=so))
                self.assertIsNone(_hang_tren(thuong, che))
                x = _hang_tren(short, che)
                self.assertIsNotNone(x, f"không thấy dòng trên tiêu đề (che={che})")
                self.assertAlmostEqual((x[0] + x[1]) / 2, vdk.W / 2, delta=8)      # canh giữa
                # Nằm gọn TRÊN ô tiêu đề, không đè lên tiêu đề: ô tiêu đề hai bản y hệt nhau.
                o = vdk.bo_cuc(che)["tieu_de"]
                self.assertEqual(thuong.crop(o).tobytes(), short.crop(o).tobytes())

    def test_dong_tren_dai_khong_de_logo(self):
        with tempfile.TemporaryDirectory() as d:
            dai = "Tập Số 1234567890 Rất Dài Dài"
            a = Image.open(vdk.ve_lop_tap("tím", "1", "T", Path(d) / "a.png"))
            b = Image.open(vdk.ve_lop_tap("tím", "1", "T", Path(d) / "b.png", dong_tren=dai))
            # Chữ (phần khác nhau giữa hai lớp phủ) nằm trọn bên phải logo và trong màn hình.
            lg = vdk._th().load_logo_cropped(vdk.duong_logo("tím"))
            mep_logo = vdk.bo_cuc(False)["logo"][0] + round(lg.width * vdk.LOGO_H / lg.height)
            khac = ImageChops.difference(a.convert("RGBA"), b.convert("RGBA")).getbbox()
            self.assertIsNotNone(khac)
            self.assertGreaterEqual(khac[0], mep_logo)
            self.assertLessEqual(khac[2], vdk.W)


@unittest.skipUnless(FFMPEG, "cần ffmpeg/ffprobe")
class DungShortTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.td = Path(tempfile.mkdtemp())
        cls.tap = cls.td / "K07 - tập thử"
        cls.tap.mkdir()
        # Video gốc bản ngang (nguyên cỡ clip) + json như video_khung ghi.
        _ff("-f", "lavfi", "-i", f"testsrc2=s=1920x1080:r=30:d={DAI}", "-c:v", "libx264",
            "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(cls.tap / vdk.GOC_NAME))
        (cls.tap / "YOUTUBE_goc.json").write_text(
            json.dumps({"goc": "raw", "che": False, "logo": "logo tím.png"}), encoding="utf-8")
        # Bản dọc của tập: lớp phủ (dòng dưới cũ) + tiktok.mp4 có nhạc + bản giọng trần.
        lop = vdk.ve_lop_tap("tím", "07", "Tiêu Đề Thử", cls.tap / vdk.LOP_TAP_NAME)
        cls.x_cu = _hang_chu(Image.open(lop))
        _ff("-f", "lavfi", "-i", f"sine=f=220:d={DAI}", "-ar", "48000",
            str(cls.tap / "output_tiktok.wav"))
        _ff("-f", "lavfi", "-i", f"color=c=0x202020:s=1080x1920:r=30:d={DAI}",
            "-i", str(lop), "-f", "lavfi", "-i", f"sine=f=880:d={DAI}",
            "-filter_complex", "[0:v][1:v]overlay=0:0[v]", "-map", "[v]", "-map", "2:a",
            "-t", str(DAI), "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", str(cls.tap / "tiktok.mp4"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.td, ignore_errors=True)

    def _khung_hinh(self, video: Path) -> Image.Image:
        png = video.with_suffix(".khung.png")
        _ff("-ss", "1", "-i", str(video), "-frames:v", "1", str(png))
        with Image.open(png) as im:
            return im.convert("RGB")

    def test_short_co_dong_tap_so(self):
        ghi = []
        out = vs.build_short(self.tap / "tiktok.mp4", self.td / "short_moi.mp4", log=ghi.append)
        nhat_ky = "\n".join(ghi)
        self.assertIn("Tập Số 7", nhat_ky)
        self.assertNotIn("lùi về cắt", nhat_ky)
        self.assertTrue(vdk.video_hop_le(out))
        self.assertEqual(vdk.get_resolution(out), (vdk.W, vdk.H))
        self.assertAlmostEqual(vdk.get_duration(out), DAI, delta=0.2)
        self.assertFalse(list(self.td.glob("*_lop.png")))          # lớp phủ tạm đã dọn
        khung = self._khung_hinh(out)
        x_moi = _hang_chu(khung)
        self.assertIsNotNone(x_moi, "không thấy dòng chữ dưới trong Short")
        self.assertLess(x_moi[1] - x_moi[0], (self.x_cu[1] - self.x_cu[0]) * 0.6)
        # Dòng số tập có thêm ở PHÍA TRÊN tiêu đề; bản TikTok nguồn thì hàng đó trống.
        self.assertIsNotNone(_hang_tren(khung), "không thấy dòng số tập phía trên tiêu đề")
        self.assertIsNone(_hang_tren(self._khung_hinh(self.tap / "tiktok.mp4")))
        # Tiếng là bản giọng trần (220 Hz), không phải tiếng có nhạc của TikTok.
        self.assertTrue(any("output_tiktok.wav" in s for s in ghi), ghi)

    def test_khung_tat_thi_cat_thang(self):
        ghi = []
        out = vs.build_short(self.tap / "tiktok.mp4", self.td / "short_cat.mp4",
                             khung=False, log=ghi.append)
        self.assertNotIn("Tập Số", "\n".join(ghi))
        x = _hang_chu(self._khung_hinh(out))
        self.assertAlmostEqual(x[1] - x[0], self.x_cu[1] - self.x_cu[0], delta=12)   # chữ cũ

    def test_mat_video_goc_thi_lui_ve_cat(self):
        with tempfile.TemporaryDirectory() as d:
            tap = Path(d) / "K08 - mất gốc"
            tap.mkdir()
            for ten in ("tiktok.mp4", "output_tiktok.wav", vdk.LOP_TAP_NAME):
                shutil.copy(self.tap / ten, tap / ten)
            ghi = []
            out = vs.build_short(tap / "tiktok.mp4", log=ghi.append)
            self.assertEqual(out, tap / vs.SHORT_NAME)
            # (tiktok giả nền một màu nén quá nhỏ nên không hỏi video_hop_le — đo thời lượng)
            self.assertAlmostEqual(vdk.get_duration(out), DAI, delta=0.2)
            self.assertIn("lùi về cắt", "\n".join(ghi))
            x = _hang_chu(self._khung_hinh(out))
            self.assertAlmostEqual(x[1] - x[0], self.x_cu[1] - self.x_cu[0], delta=12)


if __name__ == "__main__":
    unittest.main()
