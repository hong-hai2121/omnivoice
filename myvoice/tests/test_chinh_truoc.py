# -*- coding: utf-8 -*-
"""🎛 CHỈNH TRƯỚC của myvideo (18/11/2026): nguồn vừa nạp hiện thành hàng chờ ở bảng Kết
quả, tick + nút 🎛 mở khung xem trước (phóng to · dải che mờ · âm lượng tiếng gốc), 🧪 chạy
thử 3 phút đầu (①②③, không ④), xong thì chỉnh riêng âm lượng giọng đọc; 💾 ghi vào đúng
các khoá bước ④ đọc, dải che lưu theo từng video.

Server chạy qua TestClient (không mở cổng); cài đặt, kho vùng che, bản xem trước và thư
mục output đều trỏ sang thư mục tạm — không đụng dữ liệu thật. Video thử dựng bằng ffmpeg."""
import re
import shutil
import subprocess
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

LINK = "https://www.bilibili.com/video/BV1xx411c7mD"


def _ffmpeg(*args):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


class ChinhTruocTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="ct_"))
        cls.out = cls.tmp / "output"
        cls.out.mkdir()
        (cls.tmp / "web_settings.json").write_text("{}", encoding="utf-8")
        cls.xep = []
        cls._va = [patch.object(sv, "SETTINGS_FILE", cls.tmp / "web_settings.json"),
                   patch.object(sv, "OUTPUT_DIR", cls.out), patch.object(st, "OUTPUT_DIR", cls.out),
                   patch.object(ct, "KHO_FILE", cls.tmp / "chinh_truoc.json"),
                   patch.object(ct, "XEM_DIR", cls.tmp / "xemtruoc"),
                   patch.object(sv.q, "enqueue", lambda title, steps: cls.xep.append((title, steps)))]
        for p in cls._va:
            p.start()
        cls.src = cls.tmp / "Tap Moi.mp4"            # 320×180, 3 giây, có tiếng
        _ffmpeg("-f", "lavfi", "-i", "testsrc=size=320x180:rate=10", "-f", "lavfi", "-i",
                "sine=frequency=440", "-t", "3", "-pix_fmt", "yuv420p", "-c:v", "libx264",
                "-c:a", "aac", str(cls.src))
        cls.c = TestClient(sv.app)
        cls.c.cookies.set(sv.COOKIE, sv.TOKEN)
        cls.mid = f"src:{cls.src}"

    @classmethod
    def tearDownClass(cls):
        for p in cls._va:
            p.stop()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.xep.clear()

    # ── nguồn chờ ────────────────────────────────────────────────────────────
    def test_1_nap_nguon_hien_thanh_hang_cho_tick_duoc(self):
        r = self.c.post("/nguon/nap", data={"sources": f"{self.src}\nC:\\Us\nC:\\khong\\co.mp4\n{LINK}"})
        self.assertEqual(r.json(), {"them": 2})                 # dòng gõ dở / file không có: bỏ
        self.assertEqual(self.c.post("/nguon/nap", data={"sources": str(self.src)}).json(), {"them": 0})
        bang = self.c.get("/partials/bang").text
        self.assertIn('class="hangcho"', bang)
        self.assertIn("Tap Moi.mp4", bang)
        self.assertIn("BV1xx411c7mD", bang)
        self.assertRegex(bang, r'class="tickv" value="src:[^"]*Tap Moi\.mp4"')
        self.assertIn("link chưa tải về máy", bang)
        self.assertNotIn("<form", bang)                         # khối nằm trong form chính

    def test_2_trang_chinh_co_nut_va_khung_dung_cho(self):
        html = self.c.get("/").text
        self.assertRegex(html, r'(?s)id="nutChinhTruoc".*?📂 Mở thư mục')
        self.assertLess(html.find('id="bang"'), html.find('id="chinhtruoc"'))
        self.assertLess(html.find('id="chinhtruoc"'), html.find('id="bangfile"'))
        self.assertLess(html.find('id="chinhtruoc"'), html.find("📁 File mới trong output"))
        # 📁 File mới: khối THU GỌN — <details> đóng sẵn (không có open), danh sách nằm bên trong;
        # chỉ dòng tiêu đề (kèm nút 🗑 Clear nếu có file) hiện ra.
        tep = self.c.get("/partials/file")
        self.assertEqual(tep.status_code, 200)
        the = re.search(r"<details[^>]*id=\"fileMoi\"[^>]*>", tep.text).group()
        self.assertNotIn("open", the)
        self.assertLess(tep.text.find("<summary"), tep.text.find("📁 File mới trong output"))
        self.assertLess(tep.text.find("</summary>"), tep.text.find("Xoá chỉ đưa vào Thùng rác"))
        self.assertNotIn("<form", tep.text)

    # ── khung xem trước của nguồn CHƯA chạy ─────────────────────────────────
    def test_3_khung_xem_truoc_nguon_chua_chay(self):
        """Luồng user chốt 20/11/2026: chọn video để chỉnh trước là CẮT NGAY clip gốc 3 phút và cho
        xem clip đó — chưa nhận diện / lồng tiếng gì; bấm 🧪 mới chạy."""
        clip = self.out / "Tap Moi_thu3p.mp4"
        # Hỏi trạng thái / lưu chỉnh KHÔNG được tự cắt clip — chỉ lúc MỞ khung mới cắt.
        self.assertEqual(sv._ct_muc(self.mid)["loai"], "nguon")
        self.assertFalse(clip.exists())
        panel = self.c.get("/partials/chinhtruoc", params={"id": self.mid}).text
        self.assertTrue(clip.is_file())                          # mở khung = cắt sẵn clip gốc
        self.assertEqual(self.xep, [])                           # …và CHƯA xếp việc gì vào hàng đợi
        self.assertIn("clip gốc 3 phút đầu", panel)
        self.assertIn("🧪 Chạy thử 3 phút ở tốc độ 0.7x (nhận diện + dịch + lồng tiếng)", panel)
        m = sv._ct_muc(self.mid)
        self.assertEqual((m["loai"], m["w"], m["h"], m["co_thu"]), ("clip", 320, 180, False))
        self.assertFalse(m["co_vung"])
        self.assertEqual([(b["key"], b["dang"]) for b in m["cac_ban"]], [("clip", True), ("nguon", False)])
        self.assertTrue(m["video_url"].startswith("/chinhtruoc/tep?f=Tap%20Moi_thu3p.mp4"))
        r = self.c.get(m["video_url"], headers={"Range": "bytes=0-99"})
        self.assertEqual(r.status_code, 206)                    # có Range → tua được
        # Mở lại khung không cắt lại (clip còn mới hơn file nguồn).
        t0 = clip.stat().st_mtime_ns
        self.c.get("/partials/chinhtruoc", params={"id": self.mid})
        self.assertEqual(clip.stat().st_mtime_ns, t0)
        # File nguồn cả bài vẫn xem được qua nút "Xem bản" — phát thẳng, đủ độ dài.
        mn = sv._ct_muc(self.mid, "nguon")
        self.assertTrue(mn["video_url"].startswith("/chinhtruoc/nguon?src="))
        rn = self.c.get(mn["video_url"], headers={"Range": "bytes=0-99"})
        self.assertEqual(rn.headers["content-range"].split("/")[-1], str(self.src.stat().st_size))
        self.assertEqual(list((self.tmp / "xemtruoc").glob("*.mp4")) if (self.tmp / "xemtruoc").exists() else [], [])
        # Bản xem trước thu nhỏ chỉ còn là đường lùi khi trình duyệt không đọc được clip.
        self.assertTrue(m["du_phong_url"].startswith("/chinhtruoc/xem?src="))
        self.assertEqual(self.c.get(m["du_phong_url"], headers={"Range": "bytes=0-99"}).status_code, 206)
        ban = list((self.tmp / "xemtruoc").glob("*.mp4"))
        self.assertEqual(len(ban), 1)
        info = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                               "stream=codec_name,height", "-of", "csv=p=0", str(ban[0])],
                              capture_output=True, text=True).stdout.strip()
        self.assertEqual(info, f"h264,{ct.XEM_CAO}")
        panel = self.c.get("/partials/chinhtruoc", params={"id": self.mid}).text
        for can in ('id="ctVideo"', 'id="ctZoomK"', 'id="ctCheBat"', 'id="ctGocK"', 'id="ctLuu"', 'id="ctThu"',
                    'id="ctDocK"',       # ↕ cột vị trí dọc dưới thanh phóng to
                    'id="ctDayK"'):      # thanh độ dày lớp che mờ
            self.assertIn(can, panel)
        self.assertRegex(panel, r'id="ctGiongK"[^>]*disabled')   # chưa lồng tiếng → khoá thanh giọng
        # Khung nằm TRONG form chính: ô có name sẽ lẫn vào cài đặt lúc bấm ▶ Chạy.
        self.assertIsNone(re.search(r"<(input|select|textarea)[^>]*\sname=", panel))

    def test_4_khung_khong_vo_voi_dau_vao_xau(self):
        for mid, can in ((f"src:{LINK}", "chưa tải về máy"), ("base:../../x", "Không nhận ra video"),
                         ("", "Không nhận ra video")):
            r = self.c.get("/partials/chinhtruoc", params={"id": mid})
            self.assertEqual(r.status_code, 200)
            self.assertIn(can, r.text)
        self.assertIn(self.c.get("/chinhtruoc/tep", params={"f": "../web_settings.json"}).status_code, (400, 404))
        self.assertEqual(self.c.get("/chinhtruoc/xem", params={"src": str(self.tmp / "web_settings.json")}).status_code, 404)

    # ── 💾 áp dụng ──────────────────────────────────────────────────────────
    def test_5_luu_ghi_dung_khoa_buoc_4_doc(self):
        d = self.c.post("/chinhtruoc/luu", data={"id": self.mid, "zoom": "15", "chesub": "1", "y0": "120",
                                                 "y1": "170", "gocdb": "-12", "ttsdb": "4",
                                                 "zoom_y": "-40"}).json()
        s = sv.load_settings()
        self.assertEqual((s["zoom"], s["chesub"], s["gocdb"], s["ttsdb"]), ("15", True, "-12", "4"))
        self.assertEqual((s["zoom_y"], d["zoom_y"]), ("-40", "-40"))      # ↕ vị trí dọc của hình
        self.assertEqual(d["vung"], {"y0": 120, "y1": 170, "w": 320, "h": 180})
        self.assertEqual(ct.vung("tap moi"), d["vung"])
        # Video ① CHƯA có mà lượt dựng ④ của chính bài vẫn nhận đúng dải vừa kéo.
        base = st.base_for(str(self.src), "0.7")
        argv = st._steps_for(["gan"], str(self.src), base, {**sv.DEFAULTS, **s})[0].argv
        self.assertEqual(argv[argv.index("--vung") + 1], "120:170")
        self.assertNotIn("--che-sub-goc", argv)
        self.assertEqual(argv[argv.index("--zoom") + 1], "15")
        self.assertIn("--zoom-y=-40", argv)                      # viết liền: số âm không bị đọc thành cờ
        self.assertEqual(argv[argv.index("--goc-db") + 1], "-12")
        self.assertEqual(argv[argv.index("--tts-db") + 1], "4")
        self.assertFalse(base.parent.exists())                   # không tạo thư mục output sớm
        # Nấc tận trái của tiếng gốc = "như cũ" (khoá rỗng); tắt che mờ thì không gửi cờ che nào;
        # không phóng thì vị trí dọc về giữa (không có phần dôi nào để dời).
        self.c.post("/chinhtruoc/luu", data={"id": self.mid, "zoom": "0", "chesub": "", "y0": "120",
                                             "y1": "170", "gocdb": "-21", "ttsdb": "0", "zoom_y": "60"})
        s = sv.load_settings()
        self.assertEqual((s["zoom"], s["chesub"], s["gocdb"], s["ttsdb"]), ("", False, "", "0"))
        self.assertEqual(s["zoom_y"], "0")
        argv = st._steps_for(["gan"], str(self.src), base, {**sv.DEFAULTS, **s})[0].argv
        self.assertNotIn("--vung", argv)
        self.assertNotIn("--che-sub-goc", argv)
        self.assertFalse(any(a.startswith("--zoom") for a in argv))

    def test_5b_nut_chay_mang_du_muc_da_ap_dung(self):
        """User báo 24/11/2026: 💾 Áp dụng rồi bấm ▶ Chạy tất cả mà video ra MẤT tiếng gốc, hình cắt
        giữa. Mức tiếng gốc / giọng đọc và vị trí dọc không có ô trong form chính — /chay phải dựng
        lệnh từ cài đặt đã trộn, không phải riêng các ô của form."""
        cu = (self.tmp / "web_settings.json").read_text(encoding="utf-8")
        try:
            self.c.post("/chinhtruoc/luu", data={"id": self.mid, "zoom": "10", "chesub": "1", "y0": "120",
                                                 "y1": "170", "gocdb": "-14", "ttsdb": "3", "zoom_y": "90"})
            r = self.c.post("/chay", data={"start": "tatca", "sources": str(self.src), "speed": "0.7",
                                           "model": "medium", "zoom": "10", "chesub": "1", "thaytieng": "1"},
                            headers={"hx-request": "true"})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(len(self.xep), 1)
            gan = next(b.argv for b in self.xep[0][1] if any("video_gansub_cung.py" in a for a in b.argv))
            self.assertEqual(gan[gan.index("--goc-db") + 1], "-14")          # tiếng gốc còn, lót dưới giọng đọc
            self.assertEqual(gan[gan.index("--tts-db") + 1], "3")
            self.assertEqual(gan[gan.index("--zoom") + 1], "10")
            self.assertIn("--zoom-y=90", gan)                                # hình dịch lên như đã kéo
            self.assertEqual(gan[gan.index("--vung") + 1], "120:170")
            # …và bấm ▶ không xoá mấy mức đó khỏi cài đặt đang lưu.
            s = sv.load_settings()
            self.assertEqual((s["gocdb"], s["ttsdb"], s["zoom_y"]), ("-14", "3", "90"))
            # Tab 🔊 cũng lưu riêng (chuẩn hoá tiếng gốc) → ▶ Chạy phải mang theo.
            self.xep.clear()
            self.c.post("/amthanh/luu", data={"gocdb": "-6", "gocnorm": "1", "ttsdb": "0"})
            self.c.post("/chay", data={"start": "tatca", "sources": str(self.src), "speed": "0.7",
                                       "model": "medium", "thaytieng": "1"}, headers={"hx-request": "true"})
            gan = next(b.argv for b in self.xep[0][1] if any("video_gansub_cung.py" in a for a in b.argv))
            self.assertEqual(gan[gan.index("--goc-db") + 1], "-6")
            self.assertIn("--goc-norm", gan)
            self.assertNotIn("--tts-db", gan)
        finally:
            (self.tmp / "web_settings.json").write_text(cu, encoding="utf-8")

    def test_5a_chieu_rong_lop_che_khong_phu_het_be_ngang(self):
        """User yêu cầu 20/11/2026: chiều rộng lớp che mờ chỉnh được, không nhất thiết phủ hết bề
        ngang — lưu theo từng video (x0/x1), bước ④ nhận qua --vung y0:y1:x0:x1."""
        luu = {"id": self.mid, "zoom": "0", "chesub": "1", "y0": "120", "y1": "170", "gocdb": "-21", "ttsdb": "0"}
        base = st.base_for(str(self.src), "0.7")
        lenh = lambda: st._steps_for(["gan"], str(self.src), base, {**sv.DEFAULTS, **sv.load_settings()})[0].argv  # noqa: E731
        d = self.c.post("/chinhtruoc/luu", data={**luu, "x0": "60", "x1": "260"}).json()
        self.assertEqual(d["vung"], {"y0": 120, "y1": 170, "w": 320, "h": 180, "x0": 60, "x1": 260})
        self.assertEqual(ct.ngang(ct.vung("tap moi")), (60, 260))
        m = sv._ct_muc(self.mid)
        self.assertEqual((m["x0"], m["x1"]), (60, 260))
        argv = lenh()
        self.assertEqual(argv[argv.index("--vung") + 1], "120:170:60:260")
        # Khung: thanh chiều rộng + thanh vị trí ngang + hai nút có chữ + mép kéo trái/phải.
        panel = self.c.get("/partials/chinhtruoc", params={"id": self.mid}).text
        for can in ('id="ctRongK"', 'id="ctNgangK"', 'data-mep="trai"', 'data-mep="phai"',
                    "↔ Chiều rộng lớp che mờ", "↔ Phủ hết bề ngang", "↺ Về giữa"):
            self.assertIn(can, panel)
        # Mép kéo trái/phải KHÔNG được mang tên lớp của hai cột khung (ct-trai / ct-phai): trùng tên
        # là luật CSS của mép (rộng 12px) bóp luôn hai cột — đã gặp lúc viết, ảnh chụp mới lộ ra.
        self.assertEqual(len(re.findall(r'class="ct-(?:trai|phai)"', panel)), 2)
        self.assertNotRegex(panel, r"\.ct-(?:trai|phai)\b[^{}]*\{")
        self.assertRegex(panel, r'id="ctRongK" min="16" max="320" step="1" value="200"')
        self.assertRegex(panel, r'id="ctNgangK" min="0" max="120" step="1" value="60"')
        self.assertIn("let x0 = 60, x1 = 260;", panel)
        self.assertIsNone(re.search(r"<(input|select|textarea)[^>]*\sname=", panel))
        # Lưu mà KHÔNG gửi x (gọi kiểu cũ) hoặc gửi khoảng hẹp vô lý → giữ khoảng ngang đang lưu.
        for them in ({}, {"x0": "100", "x1": "104"}):
            d = self.c.post("/chinhtruoc/luu", data={**luu, "y0": "118", **them}).json()
            self.assertEqual((d["vung"]["y0"], d["vung"]["x0"], d["vung"]["x1"]), (118, 60, 260))
        # Kéo về phủ hết bề ngang → bản ghi và lệnh bước ④ y như trước khi có chức năng này.
        d = self.c.post("/chinhtruoc/luu", data={**luu, "x0": "0", "x1": "320"}).json()
        self.assertEqual(d["vung"], {"y0": 120, "y1": 170, "w": 320, "h": 180})
        self.assertIsNone(ct.ngang(ct.vung("tap moi")))
        argv = lenh()
        self.assertEqual(argv[argv.index("--vung") + 1], "120:170")
        m = sv._ct_muc(self.mid)
        self.assertEqual((m["x0"], m["x1"]), (0, 320))
        # Vùng lưu lúc khung hình cỡ khác (nguồn bị thay bản khác cỡ) → co cả hai chiều theo tỉ lệ.
        ct.luu_vung("tap moi", 240, 340, 640, 360, 120, 520)
        m = sv._ct_muc(self.mid)
        self.assertEqual((m["y0"], m["y1"], m["x0"], m["x1"]), (120, 170, 60, 260))
        ct.luu_vung("tap moi", 120, 170, 320, 180)

    # ── 🧪 chạy thử 3 phút → bản lồng tiếng ─────────────────────────────────
    def test_6_chay_thu_3_phut_roi_chinh_am_luong_giong(self):
        r = self.c.post("/chinhtruoc/thu", data={"ct_id": self.mid}, headers={"hx-request": "true"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(self.xep), 1)
        ten, buoc = self.xep[0]
        self.assertIn("thử 3 phút", ten)
        clip = self.out / "Tap Moi_thu3p.mp4"
        # Clip gốc đã cắt lúc mở khung (test_3) → việc chạy thử DÙNG LẠI, không có bước cắt đè
        # (khung có thể đang phát chính clip đó).
        lenh = [" ".join(b.argv) for b in buoc]
        self.assertEqual(len(lenh), 3)                           # ① ② ③ — không cắt lại, không dựng ④
        self.assertIn(str(clip), buoc[0].argv)                   # ① chạy trên chính clip 3 phút
        # Chưa có clip (link vừa tải, file nguồn đổi) thì việc tự cắt 180 giây đầu trước.
        cu = clip.read_bytes()
        clip.unlink()
        _t, b4, _e = st.build("thu3p", str(self.src), {**sv.DEFAULTS, **sv.load_settings()})
        cat = b4[0].argv
        self.assertEqual((len(b4), cat[cat.index("-t") + 1], cat[-1]), (4, "180", str(clip)))
        clip.write_bytes(cu)
        buoc = [None] + buoc                                     # giữ chỉ số ①=1 ②=2 ③=3 cho phần dưới
        self.assertIn("video_chamlai_srt.py", lenh[0])
        self.assertIn("dich_srt.py", lenh[1])
        self.assertIn("taogiong_srt.py", lenh[2])
        self.assertFalse(any("video_gansub_cung.py" in x for x in lenh))
        # Bấm 🧪 = làm lại bản thử TỪ ĐẦU theo cài đặt mới: nhận diện lại + đọc lại mọi câu.
        self.assertIn("--redo-asr", buoc[1].argv)
        self.assertIn("--redo-tts", lenh[2])
        tt = self.c.get("/chinhtruoc/trangthai", params={"id": self.mid}).json()
        self.assertEqual((tt["long_tieng"], tt["ban_thu"], tt["thu"]["dang"]), (False, 0, False))
        # Việc chạy thử đang nằm trong hàng đợi → khung biết đang ở bước nào / đang đợi thứ mấy.
        viec = {"id": 1, "title": ten, "status": "running", "step_index": 1, "step_total": 4,
                "step_label": "① Chậm video + SRT tiếng Trung"}
        with patch.object(sv.q, "state", lambda: {"current": viec, "pending": [], "history": []}):
            tt = self.c.get("/chinhtruoc/trangthai", params={"id": self.mid}).json()
        self.assertEqual(tt["thu"], {"dang": True, "buoc": "① Chậm video + SRT tiếng Trung (2/4)", "cuoi": ""})
        with patch.object(sv.q, "state", lambda: {"current": {**viec, "title": "việc khác"},
                                                  "pending": [viec], "history": []}):
            self.assertIn("thứ 1", self.c.get("/chinhtruoc/trangthai", params={"id": self.mid}).json()["thu"]["buoc"])
        with patch.object(sv.q, "state", lambda: {"current": None, "pending": [],
                                                  "history": [{**viec, "status": "failed"}]}):
            self.assertEqual(self.c.get("/chinhtruoc/trangthai", params={"id": self.mid}).json()["thu"],
                             {"dang": False, "buoc": "", "cuoi": "failed"})

        # Giả lập bản thử chạy xong: video ① + audio giọng đọc của clip thử.
        tb = st.base_for(str(clip), "0.7")
        tb.parent.mkdir(parents=True)
        shutil.copy(self.src, f"{tb}.mp4")
        _ffmpeg("-f", "lavfi", "-i", "sine=frequency=300:duration=2", f"{tb}_vi_audio.wav")
        self.c.post("/chinhtruoc/luu", data={"id": self.mid, "zoom": "0", "chesub": "1", "y0": "100",
                                             "y1": "160", "gocdb": "-21", "ttsdb": "0"})
        m = sv._ct_muc(self.mid)
        self.assertEqual((m["loai"], m["y0"], m["y1"]), ("thu", 100, 160))
        self.assertEqual(self.c.get("/chinhtruoc/trangthai", params={"id": self.mid}).json()["long_tieng"], True)
        panel = self.c.get("/partials/chinhtruoc", params={"id": self.mid}).text
        self.assertIn('id="ctGiong"', panel)                     # có audio giọng đọc
        self.assertIsNone(re.search(r'id="ctGiongK"[^>]*disabled', panel))
        for url in re.findall(r'src="(/chinhtruoc/tep[^"]+)"', panel):
            self.assertEqual(self.c.get(url.replace("&amp;", "&"), headers={"Range": "bytes=0-9"}).status_code, 206)
        # Có hai bản (bản thử đã lồng tiếng + file nguồn) → hàng nút chọn bản; chọn "nguon" là
        # về video thật, không kèm giọng đọc.
        self.assertEqual([(b["key"], b["dang"]) for b in m["cac_ban"]],
                         [("clip", False), ("thu", True), ("nguon", False)])
        self.assertEqual(panel.count('class="small ct-ban'), 3)
        self.assertTrue(m["co_thu"])
        self.assertIn("🔁 Làm lại bản thử 3 phút 0.7x theo cài đặt mới", panel)   # đã có bản thử → nút thành "làm lại"
        self.assertEqual(sv._ct_muc(self.mid, "clip")["audio_url"], "")     # clip gốc: không kèm giọng
        m_nguon = sv._ct_muc(self.mid, "nguon")
        self.assertEqual((m_nguon["loai"], m_nguon["audio_url"]), ("nguon", ""))
        self.assertTrue(m_nguon["video_url"].startswith("/chinhtruoc/nguon?src="))
        p_nguon = self.c.get("/partials/chinhtruoc", params={"id": self.mid, "xem": "nguon"}).text
        self.assertIn("file nguồn gốc — video thật", p_nguon)
        # Lưu lúc đã có video ① của bản thử → ghi luôn _vungsub.json cạnh nó (trang 🫥 thấy cùng số).
        self.assertIn('"y0": 100', Path(f"{tb}_vungsub.json").read_text(encoding="utf-8"))
        # Tick thẳng HÀNG BẢN THỬ ở bảng cũng mở đúng video này và vẫn biết file nguồn.
        m2 = sv._ct_muc("base:" + tb.relative_to(self.out).as_posix())
        self.assertEqual((m2["khoa"], m2["src"]), ("tap moi", str(self.src)))
        # …và mặc định phát bản thử đã lồng tiếng, kể cả khi video ① cả bài cũng đã có giọng đọc
        # (khung chỉnh trước đi theo luồng 3 phút; video cả bài là bản xem thêm qua nút "Xem bản").
        that = st.base_for(str(self.src), "0.7")
        that.parent.mkdir(parents=True)
        shutil.copy(self.src, f"{that}.mp4")
        _ffmpeg("-f", "lavfi", "-i", "sine=frequency=200:duration=2", f"{that}_vi_audio.wav")
        self.assertEqual(sv._ct_muc("base:" + tb.relative_to(self.out).as_posix())["loai"], "thu")
        id_that = "base:" + that.relative_to(self.out).as_posix()
        self.assertEqual(sv._ct_muc(id_that)["loai"], "thu")
        self.assertEqual(sv._ct_muc(id_that, "that")["loai"], "that")
        self.assertEqual([b["key"] for b in sv._ct_muc(id_that)["cac_ban"]], ["clip", "thu", "that", "nguon"])
        shutil.rmtree(that.parent)
        # Chạy thử lại ghi đè file cùng tên → địa chỉ phát kèm dấu giờ sửa (khỏi dính bản cũ trong
        # bộ đệm trình duyệt), và dấu ban_thu đổi theo để khung biết đã có bản mới.
        import os
        self.assertRegex(m2["audio_url"], r"&v=\d+$")
        cu = sv._ct_muc(self.mid)["ban_thu"]
        os.utime(f"{tb}_vi_audio.wav", (cu + 50, cu + 50))
        moi = sv._ct_muc(self.mid)
        self.assertEqual(moi["ban_thu"], cu + 50)
        self.assertTrue(moi["audio_url"].endswith(f"&v={cu + 50}"))
        self.assertEqual(self.c.get("/chinhtruoc/trangthai", params={"id": self.mid}).json()["ban_thu"], cu + 50)
        # Trang 🫥 sửa / bỏ vùng thì kho chỉnh trước theo ngay (kẻo ④ lấy số cũ).
        rel = tb.relative_to(self.out).as_posix()
        self.assertTrue(self.c.post("/vungsub/luu", data={"base": rel, "y0": "90", "y1": "150"}).json()["ok"])
        self.assertEqual((ct.vung("tap moi")["y0"], ct.vung("tap moi")["y1"]), (90, 150))
        self.c.post("/vungsub/xoa", data={"base": rel})
        self.assertIsNone(ct.vung("tap moi"))

    def test_65_bang_moc_gio_co_nut_nghe_goc_va_nghe_giong(self):
        """⏱ Mốc giờ 5 câu đầu: mỗi câu nghe được TIẾNG GỐC (từ video ①, đúng khe sub) và GIỌNG
        ĐỌC phần mềm tạo (từ audio đã xếp, đúng chỗ câu đó nằm)."""
        import json
        b = self.out / "Bai Nghe" / "Bai Nghe_x0.7"
        b.parent.mkdir(parents=True)
        shutil.copy(self.src, f"{b}.mp4")
        _ffmpeg("-f", "lavfi", "-i", "sine=frequency=300:duration=3", f"{b}_vi_audio.wav")
        srt = "1\n00:00:00,500 --> 00:00:01,200\n{}\n\n2\n00:00:01,500 --> 00:00:02,400\n{}\n"
        Path(f"{b}.srt").write_text(srt.format("你好。", "走吧。"), encoding="utf-8")
        Path(f"{b}_vi.srt").write_text(srt.format("Xin chào.", "Đi thôi."), encoding="utf-8")
        Path(f"{b}_vi_timeline.json").write_text(json.dumps({"cues": [
            {"srt_start_ms": 500, "start_ms": 500, "duration_ms": 900},
            {"srt_start_ms": 1500, "start_ms": 1650, "duration_ms": 700}]}), encoding="utf-8")
        html = self.c.get("/partials/socau", params={"base": "Bai Nghe/Bai Nghe_x0.7"}).text
        self.assertEqual(html.count("▶ Nghe gốc"), 2 + 1)        # 2 nút + 1 lần trong dòng giải thích
        self.assertEqual(html.count("▶ Nghe giọng"), 2 + 1)
        self.assertRegex(html, r'data-loai="goc"\s+data-s="500" data-e="1200"')       # khe sub của câu 1
        self.assertRegex(html, r'data-loai="giong"\s+data-s="1650" data-e="2350"')   # chỗ giọng câu 2 nằm
        for url in re.findall(r'<audio id="sc\w+" src="([^"]+)"', html):
            self.assertEqual(self.c.get(url.replace("&amp;", "&"), headers={"Range": "bytes=0-9"}).status_code, 206)
        self.assertEqual(len(re.findall(r'<audio id="sc\w+"', html)), 2)
        # Mốc giờ thuộc bản nhận diện CŨ (_words.json 3 trường) → bảng cảnh báo + nút chạy lại cả
        # bài, ép nhận diện lại; bản mới (4 trường) thì không cảnh báo.
        self.assertNotIn("/chaylai", html)
        Path(f"{b}_words.json").write_text('[[0.5, 0.8, "你"], [0.8, 1.2, "好。"]]', encoding="utf-8")
        html = self.c.get("/partials/socau", params={"base": "Bai Nghe/Bai Nghe_x0.7"}).text
        self.assertIn("bản cũ", html)
        self.assertIn('hx-post="/chaylai"', html)
        nguon = self.tmp / "Bai Nghe.mp4"
        shutil.copy(self.src, nguon)
        self.c.post("/nguon/nap", data={"sources": str(nguon)})
        r = self.c.post("/chaylai", data={"base": "Bai Nghe/Bai Nghe_x0.7"}, headers={"hx-request": "true"})
        self.assertEqual((r.status_code, len(self.xep)), (200, 1))
        buoc = self.xep[0][1]
        self.assertEqual(len(buoc), 4)                           # ① ② ③ ④
        self.assertIn("--redo-asr", buoc[0].argv)                # bỏ mốc giờ cũ, nhận diện lại
        self.assertEqual(buoc[0].argv[3], str(nguon))
        Path(f"{b}_words.json").write_text('[[0.5, 0.8, "你", 0], [0.8, 1.2, "好。", 1]]', encoding="utf-8")
        self.assertNotIn("/chaylai", self.c.get("/partials/socau", params={"base": "Bai Nghe/Bai Nghe_x0.7"}).text)
        # Chưa có giọng (chỉ mới bước ①) → chỉ có nút nghe gốc.
        Path(f"{b}_vi_audio.wav").unlink()
        Path(f"{b}_vi_timeline.json").unlink()
        html = self.c.get("/partials/socau", params={"base": "Bai Nghe/Bai Nghe_x0.7"}).text
        self.assertIn('data-loai="goc"', html)
        self.assertNotIn('data-loai="giong"', html)
        shutil.rmtree(b.parent)

    # ── 🐢 tốc độ sau khi làm chậm: mỗi tốc độ một bản thử riêng ─────────────
    def test_6a_moi_toc_do_mot_ban_thu_rieng(self):
        """User yêu cầu 20/11/2026: tốc độ sau khi làm chậm cũng chỉnh thử được trên 3 phút đầu —
        thử 0.7 rồi thử 0.8, chọn lại 0.7 là CÓ SẴN bản đã làm (không xếp việc, không đụng file)."""
        import os
        clip = self.out / "Tap Moi_thu3p.mp4"
        tb7, tb8 = st.base_for(str(clip), "0.7"), st.base_for(str(clip), "0.8")
        self.assertTrue(Path(f"{tb7}_vi_audio.wav").is_file())   # bản thử 0.7 do test_6 để lại
        m7 = sv._ct_muc(self.mid)
        self.assertEqual((m7["toc"], m7["loai"]), ("0.7", "thu"))
        self.assertEqual([(t["toc"], t["co_giong"], t["dang"]) for t in m7["cac_toc"]],
                         [("0.6", False, False), ("0.7", True, True), ("0.8", False, False),
                          ("0.9", False, False), ("1.0", False, False)])
        # Các nấc của hàng nút = đúng các nấc của ô "Tốc độ sau khi làm chậm" ở khối ①.
        o = re.search(r'(?s)<select name="speed">(.*?)</select>', self.c.get("/").text).group(1)
        self.assertEqual(tuple(re.findall(r'<option value="([^"]+)"', o)), ct.TOC_DO)

        # Chuyển sang 0.8 (chưa thử): xem clip gốc phát chậm 0.8x, nút là "chạy thử ở 0.8x" —
        # chỉ đổi tốc độ thì KHÔNG xếp việc gì.
        p8 = self.c.get("/partials/chinhtruoc", params={"id": self.mid, "toc": "0.8"}).text
        self.assertEqual(self.xep, [])
        self.assertRegex(p8, r'id="ctPanel" data-mid="src:[^"]+" data-toc="0\.8">')   # khung ghi tốc độ đang xem
        self.assertIn("🧪 Chạy thử 3 phút ở tốc độ 0.8x (nhận diện + dịch + lồng tiếng)", p8)
        self.assertIn("Tốc độ 0.8x chưa có bản thử", p8)
        self.assertIn("đang phát chậm 0.8x để xem thử nhịp", p8)
        self.assertRegex(p8, r'ct-toc primary" data-toc="0\.8"\s+data-nhan="0\.8x" disabled')
        self.assertRegex(p8, r'ct-toc ghost" data-toc="0\.7"[^>]*>0\.7x ✅ có sẵn<')
        self.assertIn('"ct_toc": "0.8"', p8.replace("&#34;", '"'))
        self.assertIsNone(re.search(r"<(input|select|textarea)[^>]*\sname=", p8))
        m8 = sv._ct_muc(self.mid, toc="0.8")
        self.assertEqual((m8["toc"], m8["loai"], m8["co_thu"], m8["ban_thu"]), ("0.8", "clip", False, 0))

        # 🧪 ở 0.8: chạy ĐÚNG tốc độ đó, mọi file ra mang tag _x0.8 — không đụng file bản 0.7.
        r = self.c.post("/chinhtruoc/thu", data={"ct_id": self.mid, "ct_toc": "0.8"}, headers={"hx-request": "true"})
        self.assertEqual((r.status_code, len(self.xep)), (200, 1))
        ten, buoc = self.xep[0]
        self.assertIn("×0.8 ", ten)
        a1 = buoc[0].argv
        self.assertEqual(a1[a1.index("--speed") + 1], "0.8")
        self.assertTrue(any(str(a).endswith("_thu3p_x0.8_vi.srt") for a in buoc[2].argv))
        self.assertFalse(any("_x0.7" in str(a) for b in buoc for a in b.argv))
        # Việc 0.8 đang chạy: khung đang xem 0.8 thấy tiến độ; khung đang xem 0.7 thì KHÔNG coi là
        # việc của mình (bản 0.7 vẫn xem bình thường) nhưng nút 0.8x hiện ⏳.
        viec = {"id": 1, "title": ten, "status": "running", "step_index": 0, "step_total": 3,
                "step_label": "① Chậm video + SRT tiếng Trung"}
        with patch.object(sv.q, "state", lambda: {"current": viec, "pending": [], "history": []}):
            t7 = self.c.get("/chinhtruoc/trangthai", params={"id": self.mid, "toc": "0.7"}).json()
            t8 = self.c.get("/chinhtruoc/trangthai", params={"id": self.mid, "toc": "0.8"}).json()
        self.assertEqual((t7["thu"]["dang"], t8["thu"]["dang"]), (False, True))
        self.assertEqual((t7["toc"], t8["toc"]), ("0.7", "0.8"))
        self.assertEqual([t["toc"] for t in t7["cac_toc"] if t["dang"]], ["0.8"])
        self.assertEqual([t["toc"] for t in t7["cac_toc"] if t["co_giong"]], ["0.7"])

        # Giả lập bản thử 0.8 chạy xong → khung 0.8 phát bản 0.8.
        shutil.copy(self.src, f"{tb8}.mp4")
        _ffmpeg("-f", "lavfi", "-i", "sine=frequency=500:duration=2", f"{tb8}_vi_audio.wav")
        m8 = sv._ct_muc(self.mid, toc="0.8")
        self.assertEqual((m8["loai"], m8["video"], m8["co_thu"]), ("thu", Path(f"{tb8}.mp4"), True))
        # CHỌN LẠI 0.7: bản đã làm có sẵn — không xếp việc, file bản 0.7 không bị đụng tới.
        self.xep.clear()
        dau = {p.name: p.stat().st_mtime_ns for p in tb7.parent.iterdir() if "_x0.7" in p.name}
        p7 = self.c.get("/partials/chinhtruoc", params={"id": self.mid, "toc": "0.7"}).text
        m7 = sv._ct_muc(self.mid, toc="0.7")
        self.assertEqual((m7["loai"], m7["video"], m7["audio"]),
                         ("thu", Path(f"{tb7}.mp4"), Path(f"{tb7}_vi_audio.wav")))
        self.assertEqual(self.xep, [])
        self.assertEqual({p.name: p.stat().st_mtime_ns for p in tb7.parent.iterdir() if "_x0.7" in p.name}, dau)
        self.assertIn("bản thử 3 phút đầu ở tốc độ 0.7x — đã lồng tiếng", p7)
        self.assertIn("🔁 Làm lại bản thử 3 phút 0.7x theo cài đặt mới", p7)
        self.assertRegex(p7, r'ct-toc primary" data-toc="0\.7"\s+data-nhan="0\.7x" disabled')
        self.assertRegex(p7, r'ct-toc ghost" data-toc="0\.8"[^>]*>0\.8x ✅ có sẵn<')
        self.assertEqual([b["nhan"] for b in m7["cac_ban"] if b["key"] == "thu"], ["🧪 Bản thử 3 phút 0.7x đã lồng tiếng"])
        # Mọi đoạn script của khung (hàng nút tốc độ + phần chính) đúng cú pháp, ở cả hai kiểu khung.
        if shutil.which("node"):
            for html in (p7, p8):
                ds = re.findall(r"<script>(.*?)</script>", html, re.S)
                self.assertEqual(len(ds), 2)
                for js in ds:
                    f = self.tmp / "khung.js"
                    f.write_text(js, encoding="utf-8")
                    kq = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
                    self.assertEqual(kq.returncode, 0, kq.stderr[:300])
        # Tick thẳng HÀNG của một bản thử ở bảng → khung mở ở tốc độ của chính hàng đó.
        for tb, toc in ((tb7, "0.7"), (tb8, "0.8")):
            self.assertEqual(sv._ct_muc("base:" + tb.relative_to(self.out).as_posix())["toc"], toc)
        # 💾 ghi tốc độ đang chọn vào khoá speed của khối ① (lượt chạy thật dùng đúng nó); khung
        # bản cũ không gửi toc thì speed giữ nguyên.
        luu = {"id": self.mid, "zoom": "0", "chesub": "1", "y0": "", "y1": "", "gocdb": "-21", "ttsdb": "0"}
        d = self.c.post("/chinhtruoc/luu", data={**luu, "toc": "0.8"}).json()
        self.assertEqual((d["speed"], sv.load_settings()["speed"]), ("0.8", "0.8"))
        self.assertEqual(sv._ct_muc(self.mid)["toc"], "0.8")     # hàng nguồn chờ: theo tốc độ khối ①
        self.assertNotIn("speed", self.c.post("/chinhtruoc/luu", data=luu).json())
        self.assertEqual(sv.load_settings()["speed"], "0.8")
        self.c.post("/chinhtruoc/luu", data={**luu, "toc": "0.7"})
        self.assertEqual(sv.load_settings()["speed"], "0.7")
        # ↔ Chiều rộng lớp che đã chỉnh ở khung: ghi cả vào _vungsub.json cạnh video ①; trang 🫥
        # (chỉ sửa chiều DỌC) bấm Lưu thì khoảng ngang được GIỮ, và trang vẽ dải đúng khoảng đó.
        rel = tb7.relative_to(self.out).as_posix()
        self.c.post("/chinhtruoc/luu", data={**luu, "y0": "100", "y1": "160", "x0": "60", "x1": "260", "toc": "0.7"})
        self.assertIn('"x0": 60', Path(f"{tb7}_vungsub.json").read_text(encoding="utf-8"))
        self.assertTrue(self.c.post("/vungsub/luu", data={"base": rel, "y0": "90", "y1": "150"}).json()["ok"])
        self.assertEqual(ct.vung("tap moi"), {"y0": 90, "y1": 150, "w": 320, "h": 180, "x0": 60, "x1": 260})
        self.assertIn('"x1": 260', Path(f"{tb7}_vungsub.json").read_text(encoding="utf-8"))
        self.assertIn("X0 = 60, X1 = 260", self.c.get("/vungsub", params={"base": rel}).text)
        self.c.post("/vungsub/xoa", data={"base": rel})
        self.assertIsNone(ct.vung("tap moi"))
        for p in tb8.parent.iterdir():                           # dọn bản 0.8 cho các bài sau
            if "_x0.8" in p.name:
                os.remove(p)

    def test_6b_chuan_toc(self):
        for vao, ra in (("0.7", "0.7"), ("1", "1.0"), (0.80, "0.8"), ("0,9", "0.9"), ("0.75", "0.75"),
                        ("abc", "?"), ("9", "?"), ("", "?"), (None, "?"), ("0.2", "?")):
            self.assertEqual(ct.chuan_toc(vao, "?"), ra, vao)
        self.assertEqual(sv._toc_cua("Tap Moi_thu3p_x0.8"), "0.8")
        self.assertEqual(sv._toc_cua("Tap Moi_x1"), "1.0")
        self.assertEqual(sv._toc_cua("Tap Moi"), "")

    def test_7_bo_nguon_cho(self):
        self.c.post("/nguon/nap", data={"sources": LINK})
        self.c.post("/nguon/bo", data={"src": LINK}, headers={"hx-request": "true"})
        self.assertNotIn(LINK, sv.load_settings().get("cho_chinh", []))


class ServerCuTests(unittest.TestCase):
    """Server chạy BẢN CODE CŨ (20/11/2026): trang .html luôn là bản mới còn code .py chỉ nạp lúc
    khởi động — lệch nhau thì khung 🎛 Chỉnh trước từng đứng im ở "⏳ Đang nạp video…" (script hỏng
    cú pháp vì thiếu biến). Giữ ba lớp chặn: băng cảnh báo trên trang, launcher tự bật lại server
    cũ, và khung không vỡ khi gặp server cũ."""

    @classmethod
    def setUpClass(cls):
        cls.c = TestClient(sv.app)
        cls.c.cookies.set(sv.COOKIE, sv.TOKEN)
        if str(REPO / "myvideo") not in sys.path:
            sys.path.insert(0, str(REPO / "myvideo"))
        import chay
        cls.chay = chay

    def test_trang_bao_khi_code_tren_dia_moi_hon_luc_khoi_dong(self):
        self.assertEqual(self.c.get("/api/ping").json(), {"app": "myvideo", "ma": sv.MA_KHOI_DONG})
        self.assertEqual(sv._code_cu(), "")
        self.assertNotIn("BẢN CODE CŨ", self.c.get("/amthanh").text)
        with patch.object(sv, "_ma_code", lambda: sv.MA_KHOI_DONG + 60):
            self.assertIn("code được sửa lúc", sv._code_cu())
            html = self.c.get("/amthanh").text
        self.assertIn("BẢN CODE CŨ", html)
        self.assertIn("đóng cửa sổ OmniVideo (launcher) rồi mở lại", html)
        # Server quá cũ chưa đăng ký hàm code_cu → trang (đã là bản mới) vẫn phải báo.
        ham = sv.templates.env.globals.pop("code_cu")
        try:
            self.assertIn("BẢN CODE CŨ", self.c.get("/amthanh").text)
        finally:
            sv.templates.env.globals["code_cu"] = ham

    def test_launcher_va_server_tinh_cung_mot_con_dau(self):
        self.assertEqual(self.chay._ma_code(), sv._ma_code())

    def test_khung_khong_vo_khi_server_cu_thieu_truong_moi(self):
        """Dựng khung với bộ dữ liệu của server CŨ (thiếu ban_thu, cac_ban, co_thu, du_phong_url,
        zoom_y) — script vẫn phải đúng cú pháp."""
        m_cu = {"id": "base:a/a_x0.7", "khoa": "a", "ten": "a_x0.7", "src": "C:/a.mp4", "loai": "that",
                "video_url": "/chinhtruoc/tep?f=a/a_x0.7.mp4", "audio_url": "", "base_do": "a/a_x0.7",
                "w": 320, "h": 180, "ly_do": "", "co_vung": False, "y0": 130, "y1": 158}
        html = sv.templates.env.get_template("_chinhtruoc.html").render(
            m=m_cu, mid=m_cu["id"], zoom=0, chesub=True, gocdb=-21, ttsdb=0, thu_phut=3)
        js = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
        self.assertIn("const BAN_THU = 0;", js)
        self.assertNotRegex(js, r"const \w+ = ;")
        if shutil.which("node"):
            with tempfile.TemporaryDirectory() as tmp:
                f = Path(tmp) / "khung.js"
                f.write_text(js, encoding="utf-8")
                kq = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
                self.assertEqual(kq.returncode, 0, kq.stderr[:300])

    def test_launcher_nhan_ra_server_cu_va_tat_duoc_no(self):
        """Server giả trả /api/ping: thiếu "ma" hoặc "ma" cũ hơn đĩa = cũ; "ma" bằng đĩa = mới. Tắt
        theo cổng: tìm đúng PID đang nghe, tắt xong cổng trống."""
        import json
        import socket
        import time
        with socket.socket() as so:
            so.bind(("127.0.0.1", 0))
            port = so.getsockname()[1]
        ma = self.chay._ma_code()
        ma_chay = Path(tempfile.gettempdir()) / f"ping_gia_{port}.py"
        ma_chay.write_text(
            "import json, sys\n"
            "from http.server import BaseHTTPRequestHandler, HTTPServer\n"
            "tra = json.loads(sys.argv[2])\n"
            "class H(BaseHTTPRequestHandler):\n"
            "    def do_GET(self):\n"
            "        b = json.dumps(tra).encode(); self.send_response(200)\n"
            "        self.send_header('Content-Type', 'application/json'); self.end_headers(); self.wfile.write(b)\n"
            "    def log_message(self, *a): pass\n"
            "HTTPServer(('127.0.0.1', int(sys.argv[1])), H).serve_forever()\n", encoding="utf-8")

        def bat(tra):
            p = subprocess.Popen([sys.executable, str(ma_chay), str(port), json.dumps(tra)])
            for _ in range(50):
                if not self.chay._cong_trong(port):
                    break
                time.sleep(0.1)
            return p

        try:
            for tra, cu in (({"app": "myvideo"}, True), ({"app": "myvideo", "ma": ma - 5}, True),
                            ({"app": "myvideo", "ma": ma}, False), ({"app": "khac"}, False)):
                p = bat(tra)
                try:
                    self.assertEqual(self.chay._server_cu(port), cu, tra)
                    # python của venv trên Windows là tiến trình bọc: cái thật sự nghe cổng là
                    # tiến trình CON của nó → chỉ đòi tìm ra MỘT pid, tắt xong thì cả hai cùng hết.
                    self.assertIsInstance(self.chay._pid_nghe_cong(port), int)
                finally:
                    self.assertTrue(self.chay._tat_server_o_cong(port))     # tắt theo cổng
                    self.assertTrue(self.chay._cong_trong(port))
                    p.wait(timeout=5)
            self.assertFalse(self.chay._server_cu(port))            # không ai nghe → không coi là cũ
            self.assertIsNone(self.chay._pid_nghe_cong(port))
            self.assertFalse(self.chay._tat_server_o_cong(port))
        finally:
            ma_chay.unlink()


class ViTriDocTests(unittest.TestCase):
    """↕ Vị trí dọc sau khi phóng (bước ④ --zoom-y): dựng THẬT bằng ffmpeg trên một khung nửa
    trên ĐỎ, nửa dưới XANH rồi đo màu — chắc chiều kéo đúng như nhãn trên trang."""

    @classmethod
    def setUpClass(cls):
        if str(REPO / "myvideo") not in sys.path:
            sys.path.insert(0, str(REPO / "myvideo"))
        import video_gansub_cung
        cls.vg = video_gansub_cung

    def _mau(self, zoom, zoom_y):
        """→ (tỉ lệ đỏ, cỡ khung ra) sau khi áp filter phóng."""
        r = subprocess.run(
            ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=red:s=64x32", "-f", "lavfi", "-i",
             "color=blue:s=64x32", "-filter_complex",
             f"[0][1]vstack,{self.vg.loc_zoom(zoom, zoom_y, 64, 64)}", "-frames:v", "1",
             "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
        self.assertEqual(len(r), 64 * 64 * 3)                    # khung ra vẫn 64×64
        do = sum(1 for i in range(0, len(r), 3) if r[i] > 128 and r[i + 2] < 128)
        return do / (64 * 64)

    def test_keo_len_xuong_dung_chieu(self):
        self.assertAlmostEqual(self._mau(100, 0), 0.5, delta=0.06)      # giữa: nửa đỏ nửa xanh
        self.assertLess(self._mau(100, 100), 0.03)       # +100 = hình dịch LÊN hết cỡ → chỉ còn nửa dưới (xanh)
        self.assertGreater(self._mau(100, -100), 0.97)   # −100 = hình dịch XUỐNG hết cỡ → chỉ còn nửa trên (đỏ)
        self.assertAlmostEqual(self._mau(100, -50), 0.75, delta=0.06)

    def test_phong_to_cat_ve_dung_khung_cu(self):
        """User báo 24/11/2026: video 854×480 phóng 10% ra 852×478, không còn đúng tỉ lệ gốc — phép
        tính số thực của ffmpeg làm hụt khung (528/1.1 = 479,99999… → 478). Giờ chuỗi filter mang
        SỐ CỤ THỂ: phóng lên cỡ chẵn ≥ khung gốc rồi crop ĐÚNG khung gốc, mức nào cũng vậy."""
        self.assertEqual(self.vg.loc_zoom(10, 0, 854, 480),
                         "scale=940:528:flags=lanczos,crop=854:480:43:24")
        self.assertEqual(self.vg.loc_zoom(10, 90, 854, 480, "3844/3843"),      # dịch lên 90% phần dôi (48px)
                         "scale=940:528:flags=lanczos,crop=854:480:43:46,setsar=sar=3844/3843:max=3844")
        for w, h in ((854, 480), (852, 480), (1920, 1080), (1280, 720), (640, 360), (720, 1280), (1080, 1920)):
            for zoom in range(1, 101):
                for zoom_y in (-100, 0, 100):
                    loc = self.vg.loc_zoom(zoom, zoom_y, w, h)
                    sw, sh, cw, ch, x, y = (int(n) for n in re.fullmatch(
                        r"scale=(\d+):(\d+):flags=lanczos,crop=(\d+):(\d+):(\d+):(\d+)", loc).groups())
                    self.assertEqual((cw, ch), (w, h), loc)                    # ra đúng khung gốc
                    self.assertTrue(sw >= w and sh >= h and sw % 2 == 0 and sh % 2 == 0, loc)
                    self.assertTrue(0 <= x <= sw - w and 0 <= y <= sh - h, loc)   # cửa sổ cắt nằm trong hình phóng
                    self.assertEqual(y, {-100: 0, 0: (sh - h) // 2, 100: sh - h}[zoom_y], loc)
        self.assertEqual(self.vg.loc_zoom(10, 0, 853, 481), self.vg.loc_zoom(10, 0, 852, 480))   # cạnh lẻ → chẵn
        with self.assertRaises(ValueError):
            self.vg.loc_zoom(10)                                 # thiếu cỡ khung: báo ngay, đừng đoán

    def test_buoc_4_giu_dung_khung_va_tieng_goc(self):
        """Chạy THẬT video_gansub_cung.py trên video 854×480 (SAR 3844:3843 như file Bilibili của
        user): phóng 10% + dịch lên 90% + thay tiếng + giữ tiếng gốc −14 dB → video ra vẫn 854×480,
        cùng SAR, và tiếng ra có CẢ giọng đọc (1000 Hz) lẫn tiếng gốc (440 Hz). Bỏ --goc-db thì tiếng
        gốc tắt hẳn như cũ."""
        import os
        import numpy as np

        def muc(tep):
            """→ (mức 440 Hz, mức 1000 Hz) của tiếng trong video, 0…1 so với đỉnh phổ."""
            pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(tep), "-vn", "-ac", "1", "-ar", "8000",
                                  "-f", "s16le", "-"], capture_output=True, check=True).stdout
            pho = np.abs(np.fft.rfft(np.frombuffer(pcm, dtype=np.int16).astype(np.float64)))
            tan = np.fft.rfftfreq(len(pcm) // 2, 1 / 8000)
            lay = lambda f: float(pho[(tan > f - 15) & (tan < f + 15)].max() / pho.max())  # noqa: E731
            return lay(440), lay(1000)

        with tempfile.TemporaryDirectory() as tmp:
            video, giong = Path(tmp) / "khung_x0.7.mp4", Path(tmp) / "giong.wav"
            _ffmpeg("-f", "lavfi", "-i", "testsrc=size=854x480:rate=10", "-f", "lavfi", "-i", "sine=frequency=440",
                    "-t", "2", "-vf", "setsar=sar=3844/3843:max=3844", "-pix_fmt", "yuv420p", "-c:v", "libx264",
                    "-c:a", "aac", str(video))
            _ffmpeg("-f", "lavfi", "-i", "sine=frequency=1000:duration=2", str(giong))
            ra = Path(tmp) / "khung_x0.7_sub.mp4"

            def dung(*them):
                kq = subprocess.run([sys.executable, str(REPO / "myvideo" / "video_gansub_cung.py"), str(video),
                                     "--audio", str(giong), "--zoom", "10", "--zoom-y=90", "--cpu", *them],
                                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                                    cwd=str(REPO), env={**os.environ, "PYTHONIOENCODING": "utf-8"})
                self.assertEqual(kq.returncode, 0, (kq.stdout + kq.stderr)[-400:])
                return kq.stdout

            ra_chu = dung("--goc-db", "-14")
            self.assertIn("hình dịch LÊN 90% phần dôi", ra_chu)
            self.assertIn("Giữ tiếng gốc dưới giọng đọc: -14dB", ra_chu)
            khung = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                    "stream=width,height,sample_aspect_ratio", "-of", "csv=p=0", str(ra)],
                                   capture_output=True, text=True).stdout.strip()
            self.assertEqual(khung, "854,480,3844:3843")          # đúng cỡ + tỉ lệ của video gốc
            goc, doc = muc(ra)
            self.assertGreater(doc, 0.9)                          # giọng đọc là tiếng chính
            self.assertAlmostEqual(goc, 10 ** (-14 / 20), delta=0.08)   # tiếng gốc còn, nhỏ hơn 14 dB
            dung()                                                # không --goc-db: thay tiếng = tắt hẳn tiếng gốc
            self.assertLess(muc(ra)[0], 0.01)


class CheNgangTests(unittest.TestCase):
    """↔ Chiều rộng lớp che mờ (bước ④ --vung y0:y1:x0:x1): dựng THẬT bằng ffmpeg trên một khung kẻ
    ca-rô mịn rồi so với khung gốc — trong vùng che phải nhoè, NGOÀI vùng che không đổi pixel nào."""

    W, H = 320, 180
    CARO = "nullsrc=s=320x180,geq=lum='255*mod(floor(X/4)+floor(Y/4),2)':cb=128:cr=128,format=yuv420p"

    @classmethod
    def setUpClass(cls):
        if str(REPO / "myvideo") not in sys.path:
            sys.path.insert(0, str(REPO / "myvideo"))
        import video_gansub_cung
        cls.vg = video_gansub_cung

    def _khung(self, loc=""):
        r = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", self.CARO + (f",{loc}" if loc else ""),
                            "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                           capture_output=True, check=True).stdout
        self.assertEqual(len(r), self.W * self.H)
        return r

    def _lech(self, a, b, x0, x1, y0, y1):
        """Độ lệch trung bình (0–255) giữa hai khung trong ô [x0,x1)×[y0,y1)."""
        tong = sum(abs(a[y * self.W + x] - b[y * self.W + x]) for y in range(y0, y1) for x in range(x0, x1))
        return tong / ((x1 - x0) * (y1 - y0))

    def test_chi_mo_dung_khoang_ngang(self):
        goc = self._khung()
        hep = self._khung(self.vg.loc_che({"y0": 120, "y1": 160, "x0": 80, "x1": 240}))
        self.assertGreater(self._lech(goc, hep, 90, 230, 125, 155), 60)       # trong vùng: ca-rô nhoè thành xám
        self.assertEqual(self._lech(goc, hep, 0, 80, 120, 160), 0)            # bên TRÁI vùng che: nguyên nét
        self.assertEqual(self._lech(goc, hep, 240, 320, 120, 160), 0)         # bên PHẢI vùng che: nguyên nét
        self.assertEqual(self._lech(goc, hep, 0, 320, 0, 120), 0)             # phía trên dải
        self.assertEqual(self._lech(goc, hep, 0, 320, 160, 180), 0)           # phía dưới dải
        # Không ghi x0/x1 = phủ hết bề ngang như trước giờ: hai đầu dải cũng nhoè.
        het = self._khung(self.vg.loc_che({"y0": 120, "y1": 160}))
        self.assertGreater(self._lech(goc, het, 4, 76, 125, 155), 60)
        self.assertGreater(self._lech(goc, het, 244, 316, 125, 155), 60)

    def test_chuoi_filter_cu_khong_doi_va_canh_le_lam_tron_chan(self):
        self.assertEqual(self.vg.loc_che({"y0": 10, "y1": 50}),
                         "split[goc][mo];[mo]crop=iw:40:0:10,gblur=sigma=10[dai];[goc][dai]overlay=0:10")
        self.assertEqual(self.vg.loc_che({"y0": 10, "y1": 50, "x0": 81, "x1": 241}, ":enable='between(t,1,2)'"),
                         "split[goc][mo];[mo]crop=160:40:80:10,gblur=sigma=10[dai];"
                         "[goc][dai]overlay=80:10:enable='between(t,1,2)'")

    def test_chay_ca_lenh_buoc_4_tren_video_ca_ro(self):
        """Chạy THẬT video_gansub_cung.py (không sub, không thay tiếng, encode CPU) trên một video
        ca-rô đứng yên với --vung y0:y1:x0:x1 rồi đo khung hình ra: trong khoảng ngang đã chọn mất
        hết nét ca-rô, hai bên và phía trên còn nguyên nét."""
        import os
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "caro_x0.7.mp4"
            _ffmpeg("-f", "lavfi", "-i", self.CARO + ",fps=10", "-t", "2", "-c:v", "libx264", "-crf", "10", str(video))
            kq = subprocess.run([sys.executable, str(REPO / "myvideo" / "video_gansub_cung.py"), str(video),
                                 "--vung", "120:160:80:240", "--che-khe", "0", "--cpu"],
                                capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(REPO),
                                env={**os.environ, "PYTHONIOENCODING": "utf-8"})
            ra = Path(tmp) / "caro_x0.7_sub.mp4"
            self.assertEqual(kq.returncode, 0, (kq.stdout + kq.stderr)[-400:])
            self.assertIn("ngang x 80–240 / 320px", kq.stdout)
            self.assertTrue(ra.is_file())
            a = subprocess.run(["ffmpeg", "-v", "error", "-i", str(ra), "-frames:v", "1", "-f", "rawvideo",
                                "-pix_fmt", "gray", "-"], capture_output=True, check=True).stdout
        self.assertEqual(len(a), self.W * self.H)

        def net(x0, x1, y0, y1):          # chênh lệch trung bình giữa hai điểm ảnh kề nhau theo chiều ngang
            return sum(abs(a[y * self.W + x] - a[y * self.W + x + 1])
                       for y in range(y0, y1) for x in range(x0, x1 - 1)) / ((x1 - x0 - 1) * (y1 - y0))
        self.assertLess(net(90, 230, 125, 155), 8)        # trong lớp che: ca-rô nhoè hết
        self.assertGreater(net(4, 76, 125, 155), 30)      # bên trái lớp che: còn nét
        self.assertGreater(net(244, 316, 125, 155), 30)   # bên phải lớp che: còn nét
        self.assertGreater(net(90, 230, 40, 100), 30)     # phía trên dải: còn nét

    def test_doc_co_vung(self):
        d = self.vg.doc_vung
        self.assertEqual(d("120:160", 320, 180), {"y0": 120, "y1": 160, "w": 320, "h": 180})
        self.assertEqual(d("120:160:80:240", 320, 180), {"y0": 120, "y1": 160, "w": 320, "h": 180, "x0": 80, "x1": 240})
        self.assertEqual(d("120:160:0:320", 320, 180), {"y0": 120, "y1": 160, "w": 320, "h": 180})    # phủ hết → như cũ
        self.assertEqual(d("120:160:-5:999", 320, 180), {"y0": 120, "y1": 160, "w": 320, "h": 180})  # kẹp vào khung
        for sai in ("120", "1:2:3", "120:160:200:200", "a:b"):
            with self.assertRaises(ValueError):
                d(sai, 320, 180)


class KhoTests(unittest.TestCase):
    def test_ngang_cua_vung_che(self):
        self.assertIsNone(ct.ngang(None))
        self.assertIsNone(ct.ngang({"y0": 1, "y1": 9, "w": 320, "h": 180}))                       # bản ghi cũ
        self.assertIsNone(ct.ngang({"y0": 1, "y1": 9, "w": 320, "h": 180, "x0": 0, "x1": 320}))   # phủ hết
        self.assertEqual(ct.ngang({"y0": 1, "y1": 9, "w": 320, "h": 180, "x0": 40, "x1": 320}), (40, 320))
        self.assertIsNone(ct.ngang({"y0": 1, "y1": 9, "w": 320, "h": 180, "x0": 90, "x1": 90}))

    def test_gop_nguon_cho_moi_len_dau_bo_trung(self):
        self.assertEqual(ct.gop_nguon_cho(["a", "b"], ["c", "a"]), ["c", "a", "b"])
        self.assertEqual(len(ct.gop_nguon_cho([str(i) for i in range(100)], ["x"])), ct.CHO_MAX)

    def test_clip_3_phut_cat_mot_lan_va_cat_lai_khi_nguon_doi(self):
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            src, clip = Path(tmp) / "a.mp4", Path(tmp) / "out" / "a_thu3p.mp4"
            _ffmpeg("-f", "lavfi", "-i", "testsrc=size=160x90:rate=10", "-f", "lavfi", "-i", "sine=frequency=440",
                    "-t", "2", "-pix_fmt", "yuv420p", str(src))
            self.assertFalse(ct.clip_con_dung(src, clip))
            self.assertTrue(ct.cat_clip(src, clip))                 # tự tạo thư mục, cắt bằng -c copy
            self.assertTrue(ct.clip_con_dung(src, clip))
            self.assertEqual(list(clip.parent.glob("*.tam.mp4")), [])
            t = clip.stat().st_mtime
            os.utime(src, (t + 100, t + 100))                       # file nguồn đổi → clip cũ hết dùng được
            self.assertFalse(ct.clip_con_dung(src, clip))
            hong = Path(tmp) / "hong.mp4"
            hong.write_bytes(b"khong phai video")
            self.assertFalse(ct.cat_clip(hong, Path(tmp) / "out" / "hong_thu3p.mp4"))   # không cắt được → False
            self.assertFalse((Path(tmp) / "out" / "hong_thu3p.mp4").exists())

    def test_doc_db(self):
        self.assertEqual(ct.doc_db("12", -20, 20, 0), 12)
        self.assertEqual(ct.doc_db("99", -20, 20, 0), 20)
        self.assertEqual(ct.doc_db("", -20, 20, -21), -21)
        self.assertEqual(ct.doc_db("-3,5", -20, 20, 0), -3)


if __name__ == "__main__":
    unittest.main()
