# -*- coding: utf-8 -*-
"""Hàng thu gọn (06/11/2026): từ khối "1 Nhận diện giọng nói" trở xuống mỗi khối là một
<details class="panel fold" data-fold=…>. Chỉ GET (không POST route lưu nào): trang dựng
được, đủ hàng, khoá không trùng, và KHÔNG ô/nút nào rơi khỏi form sau khi đổi cấu trúc."""
import re
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from myvoice.web import server

WEB = Path(server.__file__).resolve().parent
HANG_HOME = ["kb-nhandien", "kb-dich", "kb-input",
             "gn-chedo", "gn-tep", "gn-caidat", "gn-ngang", "gn-phude", "gn-kieusub",
             "gn-doc", "gn-tiktok", "thumb", "youtube", "facebook"]


def _trang(duong):
    with patch.object(server, "_vram", return_value={}):
        c = TestClient(server.app)
        c.cookies.set(server.COOKIE, server.TOKEN)
        r = c.get(duong)
    assert r.status_code == 200, (duong, r.status_code)
    return r.text


def _khoi(html, khoa):
    """Đoạn HTML của hàng `khoa` (từ thẻ <details> tới thẻ đóng </details> của chính nó —
    không hàng nào lồng <details class="fold"> khác, nhưng có thể chứa <details> thường)."""
    i = html.index(f'data-fold="{khoa}"')
    i = html.rindex("<details", 0, i)
    sau, j = 0, i
    for m in re.finditer(r"<details\b|</details>", html[i:]):
        sau += 1 if m.group().startswith("<details") else -1
        if sau == 0:
            j = i + m.end()
            break
    return html[i:j]


class HomeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = _trang("/")

    def test_du_hang_dung_thu_tu_khoa_khong_trung(self):
        khoa = re.findall(r'<details class="panel fold[^"]*"[^>]*data-fold="([^"]+)"', self.html)
        self.assertEqual(khoa, HANG_HOME)

    def test_mac_dinh_mo_het_rieng_kieu_phu_de_dong(self):
        for k in HANG_HOME:
            the = re.search(r"<details[^>]*data-fold=\"%s\"[^>]*>" % k, self.html).group()
            self.assertEqual(" open" in the, k != "gn-kieusub", the)

    def test_dau_hang_la_summary_khong_chua_nut(self):
        """Nút nằm trong <summary> thì bấm nút vừa chạy việc vừa đóng/mở hàng."""
        for k in HANG_HOME:
            dau = re.search(r"<summary class=\"phead\">(.*?)</summary>", _khoi(self.html, k), re.S)
            self.assertIsNotNone(dau, k)
            self.assertNotRegex(dau.group(1), r"<(button|input|select|a)\b", k)

    def test_o_nam_dung_hang(self):
        can = {
            "kb-nhandien": ['value="recognize"', 'name="auto2"'],
            "kb-dich": ['value="translate"', 'name="seo"', 'name="auto3"', 'name="gemini_backend"'],
            "kb-input": ['value="input"', 'name="auto_tts"'],
            "gn-chedo": ['name="mode"', 'name="voice"', 'name="instruct"'],
            "gn-tep": ['name="input_txt"', 'name="output_wav"'],
            "gn-caidat": ['name="chunk"', 'name="mau_giong"', 'name="pitch"', 'name="vang_truong_do"',
                          'name="vang_cuong_do"', 'name="thieu_nien"', 'name="sang_giong"',
                          'name="am_luong_db"', 'name="chuan_am"', 'name="from_gemini"', 'name="reuse"'],
            # "Nguồn clip ngang" dời từ khối 3 sang khối 4 — phải còn cả hidden rỗng cùng tên.
            "gn-ngang": ['name="make_video"', 'name="ngang_speed"', 'name="effect"', 'name="ngang_tu_nguon"',
                         'name="ngang_nguon_zoom"', 'type="hidden" name="ngang_source" value=""',
                         'value="ngang"'],
            "gn-phude": ['name="make_sub"', 'name="make_sub_doc"', 'name="sub_mode"', 'name="sub_model"',
                         'name="sub_max_chars"'],
            "gn-doc": ['name="make_video_doc"', 'name="doc_khung"', 'name="doc_from_ngang"',
                       'name="doc_from_subfolder"', 'name="doc_no_effect"', 'name="doc_speed"',
                       'name="doc_percent"', 'value="doc"'],
            "gn-tiktok": ['name="make_tiktok"', 'name="make_short"', 'name="tiktok_music"',
                          'name="tiktok_music_loop"', 'name="tiktok_no_effect"', 'name="tiktok_caption"',
                          'name="tiktok_percent"', 'name="tiktok_speed"', 'name="tiktok_caption_pos"',
                          'name="tiktok_music_db"', 'value="tiktok"'],
            "thumb": ['name="episode"', 'name="photo"', 'name="tiktok_episode"', 'name="epsrc"',
                      'name="title"', 'name="doc"', 'formaction="/thumbnail/luu"'],
            "youtube": ['name="upload"', 'name="upload_backend"', 'name="category_id"', 'name="privacy"',
                        'name="made_for_kids"', 'name="contains_ai"', 'formaction="/dangyoutube/chay"',
                        'formaction="/dangyoutube/dangnhap"'],
            "facebook": ['action="/dangfacebook/tudong"', 'action="/dangfacebook/ban"',
                         'formaction="/dangfacebook/chay"', 'formaction="/dangfacebook/xemtruoc"',
                         'formaction="/dangfacebook/quet"'],
        }
        for k, ds in can.items():
            khoi = _khoi(self.html, k)
            for o in ds:
                self.assertIn(o, khoi, f"{k}: thiếu {o}")
        self.assertNotIn('name="ngang_source"', _khoi(self.html, "gn-caidat"))

    def test_hang_giong_noi_nam_trong_voiceform(self):
        i = self.html.index('<form id="voiceform"')
        j = self.html.index("</form>", i)
        for k in HANG_HOME[3:11]:
            self.assertTrue(i < self.html.index(f'data-fold="{k}"') < j, k)
        self.assertTrue(i < self.html.index('value="run"') < j)      # nút ▶ Chạy vẫn thuộc form

    def test_nut_mac_dinh_dang_youtube_van_la_luu(self):
        """Nút submit đầu tiên là nút mặc định (phím Enter) — phải là 💾, không phải Đăng ngay."""
        nut = re.findall(r'<button[^>]*formaction="(/dangyoutube/[a-z]+)"', _khoi(self.html, "youtube"))
        self.assertEqual(nut[0], "/dangyoutube/luu")

    def test_thanh_thu_gon_het_mo_het(self):
        self.assertIn('data-fold-all="dong"', self.html)
        self.assertIn('data-fold-all="mo"', self.html)
        for nut in re.findall(r"<button[^>]*data-fold-all[^>]*>", self.html):
            self.assertIn('type="button"', nut)        # không được thành nút submit của form kịch bản


class TrangRiengTests(unittest.TestCase):
    def test_cac_trang_rieng_dung_duoc_va_co_hang(self):
        for duong, so in (("/kichban", 3), ("/giongnoi", 8), ("/thumbnail", 1), ("/dangbai", 2)):
            html = _trang(duong)
            self.assertEqual(len(re.findall(r'<details class="panel fold', html)), so, duong)

    def test_khoi_facebook_tu_ve_lai_van_la_hang(self):
        html = _trang("/partials/facebook")
        self.assertIn('id="fbblock"', html)
        self.assertIn('data-fold="facebook"', html)


class TaiNguyenTests(unittest.TestCase):
    def test_css_bo_chia_cot_home_va_co_luat_hang(self):
        css = (WEB / "static" / "app.css").read_text(encoding="utf-8")
        self.assertNotRegex(css, r"body\.p-home \.form-grid\s*\{[^}]*columns")
        self.assertIn("details.fold > summary.phead", css)
        self.assertIn(".foldbody", css)

    def test_js_nho_trang_thai_va_ap_lai_sau_htmx(self):
        js = (WEB / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("mv.fold.v1", js)
        self.assertIn("document.addEventListener('htmx:afterSwap', apLai)", js)


if __name__ == "__main__":
    unittest.main()
