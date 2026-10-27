import json
import struct
import tempfile
import unittest
from pathlib import Path

from chay_quet import NO_VIDEO, TIKTOK_MAX_SECONDS, hms, scan_episodes, video_duration


def box(kind, payload):
    return struct.pack(">I4s", 8 + len(payload), kind) + payload


def mp4_bytes(seconds, version=0, faststart=True):
    """A minimal MP4: ftyp, moov(mvhd with the given length) and a small mdat."""
    scale = 1000
    if version == 1:
        mvhd = b"\x01\x00\x00\x00" + b"\x00" * 16 + struct.pack(">IQ", scale, int(seconds * scale)) + b"\x00" * 80
    else:
        mvhd = b"\x00\x00\x00\x00" + b"\x00" * 8 + struct.pack(">II", scale, int(seconds * scale)) + b"\x00" * 80
    ftyp = box(b"ftyp", b"isom\x00\x00\x02\x00isomiso2mp41")
    moov = box(b"moov", box(b"mvhd", mvhd) + box(b"free", b"\x00" * 100))
    mdat = box(b"mdat", b"\x00" * 1000)
    return ftyp + moov + mdat if faststart else ftyp + mdat + moov


class DurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="gptcode-duration-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def episode(self, name, files):
        folder = self.root / name
        folder.mkdir()
        for filename, content in files.items():
            (folder / filename).write_bytes(content)
        (folder / "youtube_upload.json").write_text(json.dumps({"title": "Tập thử", "episode": name[1:]}), encoding="utf-8")
        return folder

    def test_duration_is_read_from_mvhd_wherever_moov_sits(self):
        for version in (0, 1):
            for faststart in (True, False):
                path = self.root / f"v{version}-{int(faststart)}.mp4"
                path.write_bytes(mp4_bytes(3613.4, version, faststart))
                self.assertAlmostEqual(video_duration(path), 3613.4, places=1, msg=f"version {version} faststart {faststart}")
        plain = self.root / "plain.mp4"
        plain.write_bytes(b"video")
        self.assertIsNone(video_duration(plain))
        self.assertEqual(hms(3613), "1:00:13")
        self.assertEqual(hms(1807.6), "30:08")

    def test_a_full_file_over_sixty_minutes_gives_way_to_the_half_video(self):
        folder = self.episode("A139", {
            "[Full] Mimi audio Số 139 - Tên.mp4": mp4_bytes(TIKTOK_MAX_SECONDS + 13),
            "Full ở Mimi audio Số 139 - Tên.mp4": mp4_bytes(1807),
            "short.mp4": mp4_bytes(168),
        })
        full = scan_episodes(self.root, "dai")
        row = full["muc"][0]
        self.assertEqual(row["video"], str(folder / "Full ở Mimi audio Số 139 - Tên.mp4"), "the half video stands in automatically")
        self.assertEqual(row["trang_thai"], "cho")
        self.assertIn("Bản Full dài 1:00:13 quá 60 phút, dùng Nửa video 30:07", row["ghi_chu"])
        self.assertEqual(set(row["variants"]), {"nua", "ngan"})
        self.assertEqual(row["thoi_luong"], {"dai": 3613, "nua": 1807, "ngan": 168})
        self.assertEqual(len(full["ghi_chu"]), 1)
        self.assertIn("A139", full["ghi_chu"][0])
        half = scan_episodes(self.root, "nua")["muc"][0]
        self.assertEqual(half["video"], str(folder / "Full ở Mimi audio Số 139 - Tên.mp4"))
        self.assertEqual(half["trang_thai"], "cho")
        self.assertEqual(half["ghi_chu"], "")
        (folder / "Full ở Mimi audio Số 139 - Tên.mp4").unlink()
        alone = scan_episodes(self.root, "dai")["muc"][0]
        self.assertEqual(alone["video"], "")
        self.assertEqual(alone["trang_thai"], NO_VIDEO)
        self.assertIn("quá 60 phút", alone["ghi_chu"])
        self.assertEqual(set(alone["variants"]), {"ngan"})

    def test_exactly_sixty_minutes_and_unreadable_lengths_stay_available(self):
        self.episode("B140", {"[Full] Mimi audio Số 140 - Tên.mp4": mp4_bytes(TIKTOK_MAX_SECONDS), "tiktok.mp4": b"not an mp4"})
        result = scan_episodes(self.root, "dai")
        row = result["muc"][0]
        self.assertTrue(row["video"].endswith("[Full] Mimi audio Số 140 - Tên.mp4"))
        self.assertEqual(set(row["variants"]), {"dai", "nua"})
        self.assertEqual(row["thoi_luong"], {"dai": 3600})
        self.assertEqual(result["ghi_chu"], [])


if __name__ == "__main__":
    unittest.main()
