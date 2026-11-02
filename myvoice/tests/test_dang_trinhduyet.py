# -*- coding: utf-8 -*-
"""Đăng qua Chrome thật (myvoice/TRINHDUYET, 30/10/2026): phần THUẦN — cấu hình + chốt chặn profile của
tool tham khảo, xếp khung giờ, tìm file trong thư mục tập, hashtag TikTok, biên nhận — và luồng
dang_youtube/dang_tiktok với trình duyệt GIẢ (không mở Chrome, không mạng)."""
import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from myvoice.web import core   # noqa: F401  (đưa myvoice/TRINHDUYET + YOUTUBE vào sys.path)

import dang_tap_trinhduyet as dt      # noqa: E402
import dang_tiktok_studio as tts      # noqa: E402
import dang_youtube_studio as yts     # noqa: E402
import trinhduyet                     # noqa: E402
from dang_chung import hashtags_in_text   # noqa: E402

BLOCKS = {
    "title": "Mimi audio Số 156 | Màn Đóng Vai Độc Ác Của Thiên Kim Giả",
    "title_tiktok": "Full ở Mimi audio Số 156 | Màn Đóng Vai Độc Ác Của Thiên Kim Giả",
    "desc": "#MimiAudioSo156 #MimiAudio #TruyenAudio #TruyenTamLyXaHoi #TruyenKichTinh #Audio #Them1 #Them2\n"
            "Màn Đóng Vai Độc Ác | Mimi audio Số 156\n👉 Đăng ký.\n#truyenfull #full",
    "tags": "mimi audio số 156, truyện audio, truyện đêm khuya",
}


def _tap(root, name="F156 - abc", ep="156", files=("YOUTUBE.mp4", "facebook.mp4", "tiktok.mp4", "short.mp4")):
    f = root / name
    f.mkdir(parents=True, exist_ok=True)
    for n in files:
        (f / n).write_bytes(b"x" * 10)
    (f / f"thumbnail{ep}.png").write_bytes(b"png")
    return f


class CauHinhTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_load_tao_file_profile_trong(self):
        with patch.object(trinhduyet, "CONFIG_PATH", self.tmp / "cau_hinh.json"):
            cfg = trinhduyet.load_config()
            self.assertTrue((self.tmp / "cau_hinh.json").exists())
            for name in trinhduyet.NEN_TANG:
                self.assertEqual(cfg["nen_tang"][name]["profile_dir"], "")
                self.assertEqual(cfg["nen_tang"][name]["extension_token"], "")
                with self.assertRaises(trinhduyet.ChuaCauHinhError):
                    trinhduyet.kiem_san_sang(cfg, name)
            st = trinhduyet.trang_thai(cfg)
            self.assertFalse(st["youtube"]["ok"])
            self.assertIn("chưa liên kết", st["youtube"]["ly_do"])

    def test_nen_tang_cfg_dien_mac_dinh(self):
        cfg = {"nen_tang": {"youtube": {"profile_dir": "Profile 3",
                                        "extension_token": 'PLAYWRIGHT_MCP_EXTENSION_TOKEN="abc"'}}}
        p = trinhduyet.nen_tang_cfg(cfg, "youtube")
        self.assertEqual(p["extension_token"], "abc")
        self.assertEqual(p["user_data_dir"], trinhduyet.DEFAULT_USER_DATA)
        self.assertEqual(p["client_name"], "OmniVoice · YouTube Studio")
        self.assertEqual(trinhduyet.kiem_san_sang(cfg, "youtube")["profile_dir"], "Profile 3")
        with self.assertRaises(ValueError):
            trinhduyet.nen_tang_cfg(cfg, "zalo")

    def test_chan_profile_tool_tham_khao(self):
        """Profile 9 / 85 (Chrome) và Profile 12 (Cốc Cốc) của tool 'Đăng video tự động' bị từ chối."""
        for udd, prof in ((r"C:\Users\PC\AppData\Local\Google\Chrome\User Data", "Profile 9"),
                          ("", "Profile 85"),
                          (r"C:\Users\PC\AppData\Local\CocCoc\Browser\User Data", "profile 12")):
            cfg = {"nen_tang": {"tiktok": {"user_data_dir": udd, "profile_dir": prof, "extension_token": "t"}}}
            with self.assertRaises(trinhduyet.ProfileCamError, msg=prof):
                trinhduyet.kiem_san_sang(cfg, "tiktok")
        # Cùng tên profile nhưng User Data khác (không phải của tool kia) thì cho qua
        cfg = {"nen_tang": {"tiktok": {"user_data_dir": r"D:\ChromeRieng\User Data", "profile_dir": "Profile 9",
                                       "extension_token": "t"}}}
        trinhduyet.kiem_san_sang(cfg, "tiktok")
        # Profile 12 trên Chrome (không phải Cốc Cốc) cũng không phải profile của tool kia
        cfg = {"nen_tang": {"tiktok": {"profile_dir": "Profile 12", "extension_token": "t"}}}
        trinhduyet.kiem_san_sang(cfg, "tiktok")

    def test_chan_token_tool_tham_khao(self):
        """Token so bằng SHA-256 (không lưu token thô): dán token của tool kia là bị chặn."""
        fake = "token-cua-omnivoice"
        self.assertNotIn(hashlib.sha256(fake.encode()).hexdigest(), trinhduyet.TOKEN_CAM_SHA256)
        with patch.object(trinhduyet, "TOKEN_CAM_SHA256", {hashlib.sha256(b"token-tham-khao").hexdigest()}):
            cfg = {"nen_tang": {"youtube": {"profile_dir": "Profile 3",
                                            "extension_token": "PLAYWRIGHT_MCP_EXTENSION_TOKEN=token-tham-khao"}}}
            with self.assertRaises(trinhduyet.ProfileCamError):
                trinhduyet.kiem_san_sang(cfg, "youtube")
            cfg["nen_tang"]["youtube"]["extension_token"] = fake
            trinhduyet.kiem_san_sang(cfg, "youtube")

    def test_khong_tham_chieu_thu_muc_tool_tham_khao(self):
        """Mã trong TRINHDUYET không đọc config của tool tham khảo."""
        for f in Path(trinhduyet.APP_DIR).glob("*.py"):
            s = f.read_text(encoding="utf-8")
            self.assertNotIn("DangvideoYTBTikTokZalo\\\\config", s, f.name)
            self.assertNotIn("GetLinktoText\\\\DangvideoYTBTikTokZalo\\\\config.json", s, f.name)


class KhungGioTest(unittest.TestCase):
    def test_sau_moc_muon_nhat_va_khong_trung(self):
        now = datetime(2026, 10, 30, 10, 0)
        self.assertEqual(dt.khung_ke_tiep(now, [], ["08:00", "18:00"], 60), datetime(2026, 10, 30, 18, 0))
        # đã có mốc 18:00 hôm nay → sáng mai
        self.assertEqual(dt.khung_ke_tiep(now, [datetime(2026, 10, 30, 18, 0)], ["08:00", "18:00"], 60),
                         datetime(2026, 10, 31, 8, 0))
        # mốc muộn nhất 01/11 08:00 (kể cả có mốc aware +07:00) → 01/11 18:00, không chen vào 31/10
        taken = [datetime(2026, 10, 30, 18, 0), datetime.fromisoformat("2026-11-01T08:00:00+07:00")]
        self.assertEqual(dt.khung_ke_tiep(now, taken, ["08:00", "18:00"], 60), datetime(2026, 11, 1, 18, 0))
        # lead: 17:30 + 60 phút > 18:00 → sáng mai
        self.assertEqual(dt.khung_ke_tiep(datetime(2026, 10, 30, 17, 30), [], ["08:00", "18:00"], 60),
                         datetime(2026, 10, 31, 8, 0))
        # khung hỏng → mặc định 08:00/18:00; khung lạ hợp lệ thì dùng
        self.assertEqual(dt.parse_khung_gio(["x", "25:00"]), [(8, 0), (18, 0)])
        self.assertEqual(dt.khung_ke_tiep(now, [], ["12:30"], 60), datetime(2026, 10, 30, 12, 30))

    def test_gio_da_hen_local_doc_bien_nhan(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        a = _tap(tmp, "A1 - x", "1")
        (a / "youtube_upload.json").write_text(json.dumps({
            "video_id": "v1", "publish_at": "2099-01-01T08:00:00+07:00", "short_publish_at": "2099-01-01T09:00:00+07:00"}),
            encoding="utf-8")
        (a / "tiktok_upload.json").write_text(json.dumps({"uploaded_at": "x", "publish_at": "2099-01-02T18:00:00+07:00"}),
                                              encoding="utf-8")
        b = _tap(tmp, "B2 - y", "2")
        (b / "youtube_upload.json").write_text(json.dumps({"video_id": "v2", "publish_at": "2000-01-01T08:00:00+07:00"}),
                                               encoding="utf-8")      # quá khứ → bỏ
        (tmp / "rac.txt").write_text("x")
        got = dt.gio_da_hen_local(tmp, now=datetime(2026, 10, 30))
        self.assertEqual([x.strftime("%Y-%m-%d %H:%M") for x in got["youtube"]], ["2099-01-01 08:00", "2099-01-01 09:00"])
        self.assertEqual([x.strftime("%Y-%m-%d %H:%M") for x in got["tiktok"]], ["2099-01-02 18:00"])

    def test_tiktok_parse_lich_text(self):
        body = "Bài A 16 tháng 10, 6:00 CH · Bài B 17 tháng 10 2023, 12:00 CH · Bài C 2 tháng 11, 8:00 SA"
        got = tts.parse_lich_text(body, now=datetime(2026, 10, 30, 12, 0))
        self.assertEqual(got, [datetime(2026, 11, 2, 8, 0)])
        self.assertEqual(tts.kiem_gio_hop_le(datetime(2026, 10, 30, 12, 10), datetime(2026, 10, 30, 12, 0))[:6], "TikTok")
        self.assertEqual(tts.kiem_gio_hop_le(datetime(2026, 11, 15, 8, 0), datetime(2026, 10, 30, 12, 0))[:6], "TikTok")
        self.assertEqual(tts.kiem_gio_hop_le(datetime(2026, 11, 2, 8, 0), datetime(2026, 10, 30, 12, 0)), "")
        self.assertEqual(tts.lam_tron_5(datetime(2026, 1, 1, 8, 7, 30)), datetime(2026, 1, 1, 8, 5))


class FileVaNoiDungTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_tim_video_tiktok_full_va_ngan(self):
        f = _tap(self.tmp, files=("YOUTUBE.mp4",))
        self.assertIsNone(dt.tim_video_tiktok(f, "full"))
        (f / "[Full] Mimi audio Số 156 - Tên.mp4").write_bytes(b"x")
        self.assertEqual(dt.tim_video_tiktok(f, "full").name, "[Full] Mimi audio Số 156 - Tên.mp4")
        (f / "facebook.mp4").write_bytes(b"x")
        self.assertEqual(dt.tim_video_tiktok(f, "full").name, "facebook.mp4")
        self.assertIsNone(dt.tim_video_tiktok(f, "ngan"))
        (f / "youtube_upload.json").write_text(json.dumps({"tiktok_file": "Full ở Mimi audio Số 156 - Tên.mp4"}), encoding="utf-8")
        (f / "Full ở Mimi audio Số 156 - Tên.mp4").write_bytes(b"x")
        self.assertEqual(dt.tim_video_tiktok(f, "ngan").name, "Full ở Mimi audio Số 156 - Tên.mp4")

    def test_hashtag_va_caption(self):
        self.assertEqual(dt.hashtags_tiktok(BLOCKS, 6),
                         ["#MimiAudioSo156", "#MimiAudio", "#TruyenAudio", "#TruyenTamLyXaHoi", "#TruyenKichTinh", "#Audio"])
        self.assertEqual(hashtags_in_text("#a #A #b", 5), ["#a", "#b"])
        self.assertEqual(dt.caption_tiktok(BLOCKS), BLOCKS["title_tiktok"])
        self.assertEqual(dt.caption_tiktok({"title": " A  B "}), "A B")

    def test_title_key_va_trung_local(self):
        self.assertEqual(dt.title_key("Full ở Mimi audio Số 12 | Mẹ Chồng #Shorts (61 ký tự)"), "mẹ chồng")
        self.assertEqual(dt.title_key("Mimi audio Số 156 | Mẹ Chồng"), dt.title_key("[Full] Mẹ Chồng | Mimi audio"))
        a = _tap(self.tmp, "A150 - x", "150")
        (a / "youtube_upload.json").write_text(json.dumps({"video_id": "v", "episode": "150",
                                                           "title": "Mimi audio Số 150 | Màn Đóng Vai Độc Ác Của Thiên Kim Giả"}),
                                               encoding="utf-8")
        self.assertEqual(dt.tieu_de_trung_local(BLOCKS["title"], "156", self.tmp), "A150 - x")
        self.assertEqual(dt.tieu_de_trung_local(BLOCKS["title"], "150", self.tmp), "")   # chính tập đó → không tính
        self.assertEqual(dt.tieu_de_trung_local("Mimi audio Số 156 | Truyện Khác", "156", self.tmp), "")

    def test_studio_tag_count_va_loc(self):
        self.assertEqual(yts.studio_tag_count(["a b", "c"]), 5 + 1 + 1)
        tags = ["x" * 200, "y" * 200, "z" * 200]
        self.assertEqual(yts.loc_the_truoc_khi_nhap(tags, log=lambda m: None), ["x" * 200, "y" * 200])
        self.assertEqual(yts.video_id_from_link("https://youtu.be/EpyHxQQMHi0"), "EpyHxQQMHi0")
        self.assertEqual(yts._format_date_like("13 thg 10, 2026", datetime(2026, 11, 2)), "2 thg 11, 2026")
        self.assertEqual(yts._format_date_like("Oct 13, 2026", datetime(2026, 11, 2)), "Nov 2, 2026")

    def test_ke_hoach_youtube(self):
        f = _tap(self.tmp)
        cfg = dict(trinhduyet.DEFAULT_CONFIG)
        with patch.object(dt.up, "load_settings", return_value={"privacy": "schedule", "made_for_kids": False, "contains_ai": True}):
            plan = dt.ke_hoach_youtube(f, "156", BLOCKS, cfg, now=datetime(2026, 10, 30, 10, 0), taken=[])
        self.assertEqual(plan["bo_qua"], "")
        self.assertEqual(plan["publish_at"], datetime(2026, 10, 30, 18, 0))
        self.assertEqual(plan["short_at"], datetime(2026, 10, 30, 19, 0))
        self.assertEqual(plan["visibility"], "SCHEDULE")
        self.assertEqual(plan["thumbnail"].name, "thumbnail156.png")
        self.assertEqual(plan["short_title"], BLOCKS["title_tiktok"] + " #Shorts")
        self.assertEqual(plan["tags"], ["mimi audio số 156", "truyện audio", "truyện đêm khuya"])
        self.assertIn("[youtube] YOUTUBE.mp4 → 30/10/2026 18:00", dt.mo_ta_ke_hoach(plan, "youtube"))
        # tiêu đề quá dài → bỏ qua
        with patch.object(dt.up, "load_settings", return_value={"privacy": "schedule"}):
            p2 = dt.ke_hoach_youtube(f, "156", {**BLOCKS, "title": "x" * 101}, cfg)
        self.assertIn("101 ký tự", p2["bo_qua"])

    def test_ke_hoach_tiktok(self):
        f = _tap(self.tmp)
        cfg = dict(trinhduyet.DEFAULT_CONFIG)
        plan = dt.ke_hoach_tiktok(f, "156", BLOCKS, cfg, now=datetime(2026, 10, 30, 10, 0), taken=[])
        self.assertEqual(plan["bo_qua"], "")
        self.assertEqual(plan["video"].name, "facebook.mp4")
        self.assertEqual(plan["publish_at"], datetime(2026, 10, 30, 18, 0))
        self.assertEqual(len(plan["hashtags"]), 6)
        # TikTok đã kín 10 ngày → bỏ qua, không ép
        taken = [datetime(2026, 11, 9, 18, 0)]
        p2 = dt.ke_hoach_tiktok(f, "156", BLOCKS, cfg, now=datetime(2026, 10, 30, 10, 0), taken=taken)
        self.assertIn("10 ngày", p2["bo_qua"])
        p3 = dt.ke_hoach_tiktok(f, "156", BLOCKS, {**cfg, "tiktok_ban": "ngan"}, now=datetime(2026, 10, 30, 10, 0))
        self.assertEqual(p3["video"].name, "tiktok.mp4")


class _PageGia:
    url = "https://studio.youtube.com/channel/UC_test123/videos/upload"

    def is_closed(self):
        return False


class LuongDangTest(unittest.TestCase):
    """dang_youtube / dang_tiktok với trình duyệt giả: kiểm biên nhận, đổi tên file, chạy thử không ghi gì."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.f = _tap(self.tmp)
        self.cfg = json.loads(json.dumps(trinhduyet.DEFAULT_CONFIG))
        self.log_lines = []
        self.goi = []
        p = patch.object(trinhduyet, "ket_noi", side_effect=lambda cfg, name, log=None: (None, _PageGia()))
        p.start(); self.addCleanup(p.stop)
        p = patch.object(dt.up, "load_settings", return_value={"privacy": "schedule", "made_for_kids": False, "contains_ai": True})
        p.start(); self.addCleanup(p.stop)

    def _log(self, m, level="info"):
        self.log_lines.append((level, m))

    def _yt_upload_gia(self, page, video_path, title, description, **kw):
        self.goi.append(("youtube", Path(video_path).name, title, kw.get("schedule_at"), kw.get("dry_run")))
        return None if kw.get("dry_run") else f"https://youtu.be/ID{len(self.goi)}xxxxxxxx"   # id thật 11 ký tự

    def test_dang_youtube_ghi_bien_nhan_va_doi_ten(self):
        with patch.object(yts, "upload_video", side_effect=self._yt_upload_gia):
            rec = dt.dang_youtube(self.f, "156", BLOCKS, self.cfg, self._log, now=datetime(2026, 10, 30, 10, 0))
        self.assertEqual(rec["video_id"], "ID1xxxxxxxx")
        self.assertEqual(rec["short_video_id"], "ID2xxxxxxxx")
        self.assertEqual(rec["via"], "studio")
        self.assertEqual(rec["channel_id"], "UC_test123")
        self.assertEqual(rec["publish_at_text"], "30/10/2026 18:00")
        self.assertEqual(rec["short_publish_at_text"], "30/10/2026 19:00")
        self.assertEqual(rec["privacy"], "private")
        self.assertEqual(rec["thumbnail"], "thumbnail156.png")
        self.assertTrue(rec["publish_at"].startswith("2026-10-30T18:00:00"))
        # file: biên nhận cùng khuôn với đường API, hai bản dọc đã đổi tên
        on_disk = json.loads((self.f / "youtube_upload.json").read_text(encoding="utf-8"))
        self.assertEqual(on_disk["url"], "https://youtu.be/ID1xxxxxxxx")
        self.assertTrue((self.f / rec["facebook_file"]).is_file())
        self.assertTrue(rec["facebook_file"].startswith("[Full] Mimi audio Số 156"))
        self.assertTrue(rec["tiktok_file"].startswith("Full ở Mimi audio Số 156"))
        self.assertFalse((self.f / "facebook.mp4").exists())
        # gọi đúng 2 lượt: bản chính rồi Short, Short hẹn +1 giờ
        self.assertEqual([g[1] for g in self.goi], ["YOUTUBE.mp4", "short.mp4"])
        self.assertEqual(self.goi[1][3], datetime(2026, 10, 30, 19, 0))
        # tập đã đăng → lần sau bỏ qua, không gọi trình duyệt
        self.goi.clear()
        with patch.object(yts, "upload_video", side_effect=self._yt_upload_gia):
            self.assertIsNone(dt.dang_youtube(self.f, "156", BLOCKS, self.cfg, self._log))
        self.assertEqual(self.goi, [])
        # TikTok (đã đổi tên) vẫn tìm được bản [Full], xếp sau mốc YouTube? — không: TikTok có lịch riêng
        tt_plan = dt.ke_hoach_tiktok(self.f, "156", BLOCKS, self.cfg, now=datetime(2026, 10, 30, 10, 0))
        self.assertTrue(tt_plan["video"].name.startswith("[Full]"))

    def test_chay_thu_khong_ghi_gi(self):
        with patch.object(yts, "upload_video", side_effect=self._yt_upload_gia):
            rec = dt.dang_youtube(self.f, "156", BLOCKS, self.cfg, self._log, dry_run=True)
        self.assertIsNone(rec)
        self.assertFalse((self.f / "youtube_upload.json").exists())
        self.assertTrue((self.f / "facebook.mp4").exists())
        self.assertEqual(len(self.goi), 1)          # không đăng Short khi chạy thử
        self.assertTrue(self.goi[0][4])

    def test_short_loi_khong_keo_do_ban_chinh(self):
        def gia(page, video_path, title, description, **kw):
            if Path(video_path).name == "short.mp4":
                raise RuntimeError("Studio lỗi Short")
            return "https://youtu.be/MAIN1xxxxxx"
        with patch.object(yts, "upload_video", side_effect=gia):
            rec = dt.dang_youtube(self.f, "156", BLOCKS, self.cfg, self._log)
        self.assertEqual(rec["video_id"], "MAIN1xxxxxx")
        self.assertEqual(rec["short_video_id"], "")
        self.assertTrue(any("Short lỗi" in m for _l, m in self.log_lines))

    def test_dang_tiktok_ghi_bien_nhan(self):
        goi = []

        def gia(page, video_path, caption, hashtags, schedule_at=None, log=print, dry_run=False):
            goi.append((Path(video_path).name, caption, list(hashtags), schedule_at, dry_run))
            return None if dry_run else tts.CONTENT_URL
        with patch.object(tts, "upload_video", side_effect=gia):
            self.assertIsNone(dt.dang_tiktok(self.f, "156", BLOCKS, self.cfg, self._log, dry_run=True,
                                             now=datetime(2026, 10, 30, 10, 0)))
            self.assertFalse((self.f / "tiktok_upload.json").exists())
            rec = dt.dang_tiktok(self.f, "156", BLOCKS, self.cfg, self._log, now=datetime(2026, 10, 30, 10, 0),
                                 lich_that=[datetime(2026, 10, 31, 8, 0)])
        self.assertEqual(rec["publish_at_text"], "31/10/2026 18:00")      # sau mốc thật 31/10 08:00
        self.assertEqual(rec["video_file"], "facebook.mp4")
        self.assertEqual(rec["caption"], BLOCKS["title_tiktok"])
        self.assertEqual(goi[-1][2][:2], ["#MimiAudioSo156", "#MimiAudio"])
        self.assertTrue((self.f / "tiktok_upload.json").exists())
        with patch.object(tts, "upload_video", side_effect=gia):
            self.assertIsNone(dt.dang_tiktok(self.f, "156", BLOCKS, self.cfg, self._log))   # đã có biên nhận → bỏ qua
        self.assertEqual(len(goi), 2)

    def test_dang_tap_loi_mot_nen_tang_khong_chan_nen_tang_kia(self):
        with patch.object(yts, "upload_video", side_effect=RuntimeError("YouTube hỏng")), \
             patch.object(tts, "upload_video", return_value=tts.CONTENT_URL), \
             patch.object(trinhduyet, "cdp_send", side_effect=RuntimeError("no relay")):
            kq = dt.dang_tap(self.f, "156", BLOCKS, ("youtube", "tiktok"), self.cfg, self._log)
        self.assertTrue(str(kq["youtube"]).startswith("lỗi"))
        self.assertIsInstance(kq["tiktok"], dict)

    def test_chua_cau_hinh_la_bo_qua_khong_phai_loi(self):
        trinhduyet.ket_noi.side_effect = lambda cfg, name, log=None: (_ for _ in ()).throw(
            trinhduyet.ChuaCauHinhError("chưa liên kết"))
        kq = dt.dang_tap(self.f, "156", BLOCKS, ("youtube",), self.cfg, self._log)
        self.assertTrue(str(kq["youtube"]).startswith("chưa cấu hình"))
        self.assertFalse((self.f / "youtube_upload.json").exists())


class RelayTest(unittest.TestCase):
    """Relay chạy thật trên loopback với một 'extension' giả (websockets client): bắt tay, rồi một client CDP
    gửi Browser.getVersion / Target.setAutoAttach và lệnh có sessionId → relay dịch thành chrome.debugger.*"""

    def test_bat_tay_va_dich_lenh(self):
        import asyncio
        import threading
        from pw_extension_relay import ExtensionRelay

        relay = ExtensionRelay(log=lambda m: None)
        relay.start()
        self.addCleanup(relay.stop)
        nhan = []           # lệnh extension giả nhận được

        async def ext_gia(stop):
            from websockets.asyncio.client import connect
            async with connect(relay.extension_endpoint) as ws:
                await ws.send(json.dumps({"method": "chrome.tabs.onCreated", "params": [{"id": 7, "url": "about:blank"}]}))
                await ws.send(json.dumps({"method": "extension.initialized", "params": []}))
                while not stop.is_set():
                    try:
                        raw = await asyncio.wait_for(ws.recv(), 0.2)
                    except asyncio.TimeoutError:
                        continue
                    msg = json.loads(raw)
                    nhan.append((msg["method"], msg["params"]))
                    if msg["method"] == "chrome.debugger.attach":
                        res = None
                    elif msg["params"][1] == "Target.getTargetInfo":
                        res = {"targetInfo": {"targetId": "T7", "type": "page", "url": "about:blank"}}
                    else:
                        res = {"result": {"type": "number", "value": 1}}
                    await ws.send(json.dumps({"id": msg["id"], "result": res}))

        async def cdp_gia():
            from websockets.asyncio.client import connect
            out = {}
            async with connect(relay.cdp_endpoint) as ws:
                await ws.send(json.dumps({"id": 1, "method": "Browser.getVersion"}))
                out["version"] = json.loads(await ws.recv())
                await ws.send(json.dumps({"id": 2, "method": "Target.setAutoAttach", "params": {"autoAttach": True}}))
                got = []
                for _ in range(2):
                    got.append(json.loads(await ws.recv()))
                out["attach"] = got
                sid = next(m["params"]["sessionId"] for m in got if m.get("method") == "Target.attachedToTarget")
                await ws.send(json.dumps({"id": 3, "sessionId": sid, "method": "Runtime.evaluate", "params": {"expression": "1"}}))
                out["eval"] = json.loads(await ws.recv())
            return out

        stop = threading.Event()
        th = threading.Thread(target=lambda: asyncio.run(ext_gia(stop)), daemon=True)
        th.start()
        relay.wait_for_extension(10)
        self.assertTrue(relay.connected)
        out = asyncio.run(cdp_gia())
        stop.set()
        th.join(3)
        self.assertEqual(out["version"]["result"]["product"], "Chrome/Extension-Bridge")
        self.assertTrue(any(m.get("method") == "Target.attachedToTarget" for m in out["attach"]))
        self.assertEqual(out["eval"]["result"]["result"]["value"], 1)
        self.assertEqual(out["eval"]["sessionId"], "pw-tab-1")
        self.assertEqual(nhan[0], ("chrome.debugger.attach", [{"tabId": 7}, "1.3"]))
        self.assertEqual(nhan[-1][1][:2], [{"tabId": 7}, "Runtime.evaluate"])


class WebWiringTest(unittest.TestCase):
    def test_upload_backend_mac_dinh_api_va_chon_studio(self):
        with patch.object(core, "load_pipeline", return_value={}):
            self.assertEqual(core.upload_backend(), "api")
        with patch.object(core, "load_pipeline", return_value={"upload_backend": "studio"}):
            self.assertEqual(core.upload_backend(), "studio")
            from myvoice.web import steps
            st = steps.upload_steps("156")
            self.assertEqual(len(st), 1)
            self.assertIn("run_dang_trinhduyet.py", st[0].argv[2])
            self.assertEqual(st[0].argv[-3:], ["--nen-tang", "youtube", "tiktok"])
            self.assertIn("TRINHDUYET", st[0].env["PYTHONPATH"])
        with patch.object(core, "load_pipeline", return_value={"upload_backend": "api"}):
            self.assertIn("run_upload.py", steps.upload_steps("156")[0].argv[2])


if __name__ == "__main__":
    unittest.main()
