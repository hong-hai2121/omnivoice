import json
import tempfile
import threading
import unittest
from unittest.mock import patch
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from chay_quet import make_server, scan_episodes, scan_payload


class ScannerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="gptcode-scanner-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def episode(self, name="A105", files=("facebook.mp4", "[Full] test.mp4", "short.mp4")):
        folder = self.root / name
        folder.mkdir()
        for filename in files:
            (folder / filename).write_bytes(b"video")
        (folder / "youtube_upload.json").write_text(
            json.dumps({"title": "Ti\u1ebfng Vi\u1ec7t", "episode": "105"}), encoding="utf-8")
        return folder

    def test_full_priority_short_and_metadata(self):
        folder = self.episode()
        row = scan_episodes(self.root)["muc"][0]
        self.assertEqual(row["video"], str(folder / "[Full] test.mp4"))
        self.assertEqual(row["tieu_de"], "Full \u1edf Ti\u1ebfng Vi\u1ec7t")
        self.assertTrue(row["hashtag"].startswith("#MimiAudioSo105 "))
        self.assertEqual(scan_episodes(self.root, "ngan")["muc"][0]["video"], str(folder / "short.mp4"))

    def test_half_is_distinct_from_full_and_short(self):
        folder = self.episode(files=("[Full] test.mp4", "Full \u1edf test.mp4", "tiktok.mp4", "short.mp4"))
        row = scan_episodes(self.root, "nua")["muc"][0]
        self.assertEqual(row["video"], str(folder / "Full \u1edf test.mp4"))
        self.assertEqual(set(row["variants"]), {"dai", "nua", "ngan"})
        self.assertEqual(row["variants"]["dai"], str(folder / "[Full] test.mp4"))
        (folder / "Full \u1edf test.mp4").unlink()
        self.assertEqual(scan_episodes(self.root, "nua")["muc"][0]["video"], str(folder / "tiktok.mp4"))
        (folder / "tiktok.mp4").unlink()
        self.assertEqual(scan_episodes(self.root, "nua")["muc"], [])

    def test_fallback_receipt_and_corrupt_metadata(self):
        folder = self.episode(files=("facebook.mp4",))
        (folder / "youtube_upload.json").write_text("{broken", encoding="utf-8")
        (folder / "tiktok_upload.json").write_text("{}", encoding="utf-8")
        result = scan_episodes(self.root)
        self.assertEqual(len(result["muc"]), 1)
        self.assertEqual(result["muc"][0]["trang_thai"], "\u0111\u00e3 \u0111\u0103ng")
        self.assertTrue(result["muc"][0]["hashtag"].startswith("#MimiAudioSo105 "))
        self.assertEqual(len(result["ghi_chu"]), 1)

    def test_repeat_scan_observes_new_files_and_skips_empty_videos(self):
        folder = self.episode(files=())
        self.assertEqual(scan_episodes(self.root)["muc"], [])
        (folder / "[Full] test.mp4").touch()
        self.assertEqual(scan_episodes(self.root)["muc"], [])
        (folder / "[Full] test.mp4").write_bytes(b"video")
        self.assertEqual(len(scan_episodes(self.root)["muc"]), 1)
        self.assertEqual(len(scan_episodes(self.root)["muc"]), 1)

    def test_folder_inventory_includes_missing_variants_and_observes_deleted_folders(self):
        folder = self.episode(files=("short.mp4",))
        empty = self.root / "A106"
        empty.mkdir()
        result = scan_episodes(self.root, "dai")
        self.assertEqual(result["muc"], [])
        self.assertEqual(set(result["folders"]), {str(folder), str(empty)})
        self.assertTrue(result["folders_complete"])
        empty.rmdir()
        self.assertEqual(scan_episodes(self.root)["folders"], [str(folder)])
        with self.assertRaises(FileNotFoundError):
            scan_episodes(self.root / "missing")

    def test_scan_errors_disable_pruning(self):
        self.episode()
        with patch("chay_quet.pick_video", side_effect=PermissionError("unreadable")):
            result = scan_episodes(self.root)
        self.assertFalse(result["folders_complete"])
        self.assertEqual(len(result["folders"]), 1)
        self.assertTrue(result["ghi_chu"])

    def test_http_readonly_and_origin_validation(self):
        self.episode()
        server = make_server(self.root, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/api/scan"
            origin = "chrome-extension://" + "a" * 32
            headers = {"X-Omni": "gptcode-scanner", "Origin": origin}
            with urlopen(Request(url, headers=headers)) as response:
                self.assertEqual(len(json.load(response)["muc"]), 1)
                self.assertEqual(response.headers["Access-Control-Allow-Origin"], origin)
            for bad_headers in ({}, {**headers, "Origin": "https://example.com"}, {**headers, "Host": "evil.example"}):
                with self.assertRaises(HTTPError) as error:
                    urlopen(Request(url, headers=bad_headers))
                self.assertEqual(error.exception.code, 403)
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(url + "?kind=bad", headers=headers))
            self.assertEqual(error.exception.code, 400)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_json_schedule_is_read_on_each_scan_without_writing(self):
        folder = self.episode()
        queue = self.root / "danh_sach.json"
        data = {"khung_gio": "08:00, 20:00", "muc": [
            {"video": str(folder / "old-name.mp4"), "gio_dang": "2026-10-02T20:00", "trang_thai": "loi lich", "ghi_chu": "test note"}]}
        queue.write_text(json.dumps(data), encoding="utf-8")
        original = queue.read_bytes()
        result = scan_payload(self.root, queue_file=queue)
        self.assertEqual(result["schedule"]["khung_gio"], "08:00, 20:00")
        self.assertEqual(result["schedule"]["muc"][0]["trang_thai"], "loi lich")
        self.assertEqual(result["schedule"]["muc"][0]["ghi_chu"], "test note")
        self.assertEqual(result["schedule"]["muc"][0]["gio_dang"], "2026-10-02T20:00")
        self.assertEqual(queue.read_bytes(), original)
        data["muc"][0]["gio_dang"] = "2026-10-03T20:00"
        queue.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(scan_payload(self.root, queue_file=queue)["schedule"]["muc"][0]["gio_dang"], "2026-10-03T20:00")
        queue.write_text("{broken", encoding="utf-8")
        result = scan_payload(self.root, queue_file=queue)
        self.assertIsNone(result["schedule"])
        self.assertEqual(len(result["muc"]), 1)
        self.assertIn("Khong doc duoc lich", result["ghi_chu"][0])


if __name__ == "__main__":
    unittest.main()
