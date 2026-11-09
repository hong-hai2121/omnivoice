# -*- coding: utf-8 -*-
"""voice/vieneu_client.py — nối VieNeu-TTS qua API server của kho (04/11/2026). Hàm thuần
(tách hội thoại, đọc SRT, xếp timeline, tên giọng), môi trường server, và client HTTP
chạy với SERVER GIẢ (http.server trong thread) trả pcm im lặng — không cần cài VieNeu."""
import json
import re
import socket
import sys
import tempfile
import threading
import unittest
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import numpy as np

_VOICE_DIR = Path(__file__).resolve().parents[1] / "voice"
if str(_VOICE_DIR) not in sys.path:
    sys.path.insert(0, str(_VOICE_DIR))
import vieneu_client as vn  # noqa: E402

SR = vn.SR
MAU_PER_CHAR = 480          # server giả: 10 ms audio cho mỗi ký tự văn bản


class _GiaHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):        # im lặng
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._json(dict(status="ok", backend="gia", max_streams=1, sample_rate=SR))
        elif self.path == "/v1/voices":
            data = [dict(id="Mai Anh", name="Mai Anh", description="nữ Bắc", featured=1, aliases=[]),
                    dict(id="Hải Đăng", name="Hải Đăng", description="", featured=2, aliases=[])]
            data += [dict(id=t, name=t, description="đã đăng ký") for t in self.server.da_dang_ky]
            self._json(dict(object="list", data=data))
        else:
            self._json(dict(error=dict(message="not found")), 404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n)
        if self.path == "/v1/audio/speech":
            req = json.loads(body)
            self.server.requests.append(req)
            if req.get("voice") == "LỖI":
                self._json(dict(error=dict(message="unknown voice 'LỖI'; see GET /v1/voices")), 400)
                return
            pcm = np.full(MAU_PER_CHAR * len(req["input"]), 1000, dtype="<i2").tobytes()
            self.send_response(200)
            self.send_header("Content-Type", "audio/pcm")
            self.send_header("Content-Length", str(len(pcm)))
            self.end_headers()
            for i in range(0, len(pcm), 4096):      # gửi nhiều mẩu như streaming thật
                self.wfile.write(pcm[i:i + 4096])
        elif self.path == "/v1/voices":
            m = re.search(rb'name="name"\r\n\r\n(.*?)\r\n', body, re.S)
            ten = m.group(1).decode("utf-8") if m else ""
            if not ten:
                self._json(dict(error=dict(message="name missing")), 400)
                return
            if ten in ("Mai Anh", "Hải Đăng"):
                self._json(dict(error=dict(message=f"'{ten}' is a built-in voice")), 409)
                return
            self.server.da_dang_ky.append(ten)
            self.server.clips.append(len(body))
            self._json(dict(id=ten, name=ten, description=""))
        else:
            self._json(dict(error=dict(message="not found")), 404)


class ServerGiaMixin:
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), _GiaHandler)
        cls.srv.requests, cls.srv.da_dang_ky, cls.srv.clips = [], [], []
        cls.th = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.th.start()
        cls.url = f"http://127.0.0.1:{cls.srv.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()


class HamThuanTests(unittest.TestCase):
    def test_tach_hoi_thoai_va_noi_dong(self):
        s = "An: xin chào\nBình： chào An\n  mình khoẻ\n\nAn: tốt quá"
        self.assertEqual(vn.tach_hoi_thoai(s), [("An", "xin chào"), ("Bình", "chào An mình khoẻ"), ("An", "tốt quá")])
        self.assertEqual(vn.nhan_vat(s), ["An", "Bình"])
        self.assertEqual(vn.tach_hoi_thoai("dòng không tên\nAn: a"), [("An", "a")])
        self.assertEqual(vn.tach_hoi_thoai(""), [])

    def test_ten_giong_tu_file(self):
        self.assertEqual(vn.ten_giong_tu_file("ngọc huyền 01 ngọt ngào.wav"), "ngọc huyền 01 ngọt ngào")
        self.assertEqual(vn.ten_giong_tu_file(Path("D:/x/  __x!!y.mp3")), "x y")
        self.assertEqual(vn.ten_giong_tu_file("!!!.wav"), "giong")
        self.assertLessEqual(len(vn.ten_giong_tu_file("a" * 100 + ".wav")), 64)
        for ten in ("ngọc huyền 01 ngọt ngào", "x y", "giong"):
            self.assertIsNotNone(vn._VOICE_NAME.fullmatch(ten), ten)

    def test_doc_srt_de_tinh(self):
        srt = ("\ufeff1\n00:00:01,000 --> 00:00:02,500\n<i>Xin</i> chào\n\n"
               "00:00:00.200 --> 00:00:00.900\n{\\an8}Mở đầu\n\n3\n00:00:05,000 --> 00:00:04,000\n\n\n"
               "4\n00:00:06,000 --> 00:00:07,000\nCâu  cuối\nnối dòng\n")
        cues = vn.doc_srt(srt)
        self.assertEqual([c["text"] for c in cues], ["Mở đầu", "Xin chào", "Câu cuối nối dòng"])
        self.assertEqual(cues[0]["start_ms"], 200)
        self.assertEqual(cues[1]["end_ms"], 2500)

    def test_xep_timeline_day_cue_sau(self):
        cues = [dict(start_ms=0, end_ms=1000, text="a"), dict(start_ms=1000, end_ms=2000, text="b"),
                dict(start_ms=5000, end_ms=6000, text="c")]
        clips = [np.ones(2 * SR, dtype=np.int16), np.ones(SR // 2, dtype=np.int16), np.ones(SR, dtype=np.int16)]
        track, day, lech = vn.xep_timeline(clips, cues)
        self.assertEqual((day, lech), (1, 1.0))                  # cue b bị đẩy 1 s, cue c đúng chỗ
        self.assertEqual(len(track), 6 * SR + SR // 2)           # c kết thúc ở 6 s + đệm 0,5 s
        self.assertEqual(int(track[int(2.2 * SR)]), 1)           # b đang phát ở 2,2 s
        self.assertEqual(int(track[int(4 * SR)]), 0)             # 4 s: im lặng
        self.assertEqual(int(track[int(5.5 * SR)]), 1)

    def test_noi_tiep_co_nghi(self):
        a = vn.noi_tiep([np.ones(10, dtype=np.int16), np.ones(5, dtype=np.int16)], nghi_s=0.5)
        self.assertEqual(len(a), 10 + SR // 2 + 5)
        self.assertEqual(len(vn.noi_tiep([], 0.3)), 0)

    def test_ghi_wav_doc_lai(self):
        with tempfile.TemporaryDirectory() as d:
            p = vn.ghi_wav(Path(d) / "sub" / "x.wav", np.arange(-5, 5, dtype=np.int16))
            with wave.open(str(p)) as w:
                self.assertEqual((w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()), (1, 2, SR, 10))

    def test_mo_ta_info(self):
        s = vn.mo_ta_info(dict(ttfa_ms=120, tong_s=1.5, audio_s=3.0, rtf=0.5))
        for tu in ("120 ms", "1.5 s", "3.0 s", "RTF 0.5"):
            self.assertIn(tu, s)


class ServerEnvTests(unittest.TestCase):
    def test_env_server_dung_bien(self):
        env = vn.ApiServer.env_server(8123, "onnx", "int8", max_streams=2)
        self.assertEqual(env["PORT"], "8123")
        self.assertEqual(env["HOST"], "127.0.0.1")
        self.assertEqual((env["VIENEU_BACKEND"], env["VIENEU_PRECISION"], env["VIENEU_MAX_STREAMS"]),
                         ("onnx", "int8", "2"))
        self.assertEqual(env["PYTHONUNBUFFERED"], "1")
        self.assertNotIn("VIENEU_MAX_STREAMS", vn.ApiServer.env_server(8000))

    def test_backend_la_thi_bao_loi(self):
        with self.assertRaises(ValueError):
            vn.ApiServer.env_server(8000, "gpu")
        with self.assertRaises(ValueError):
            vn.ApiServer.env_server(8000, precision="bf16")

    def test_cong_trong(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            s.listen(1)
            self.assertFalse(vn.cong_trong(s.getsockname()[1]))
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            cong = s.getsockname()[1]
        self.assertTrue(vn.cong_trong(cong))

    def test_chua_cai_thi_khong_bat(self):
        api = vn.ApiServer()
        with patch.object(vn, "VENV_PY", Path("Z:/khong/co/python.exe")):
            with self.assertRaisesRegex(RuntimeError, "chưa cài"):
                api.bat(8000)
        self.assertFalse(api.dang_chay)
        api.tat()                                   # chưa bật → không lỗi
        self.assertIsNone(vn.WebUi().proc)

    def test_trang_thai_co_du_khoa(self):
        tt = vn.trang_thai()
        self.assertEqual(set(tt), {"co_kho", "da_cai", "gpu", "phien_ban", "mo_ta"})
        self.assertNotIn("vieneu", sys.modules)


class ClientTests(ServerGiaMixin, unittest.TestCase):
    def test_giong_tren_server(self):
        ids = [v["id"] for v in vn.giong_tren_server(self.url)]
        self.assertEqual(ids[:2], ["Mai Anh", "Hải Đăng"])

    def test_doc_tra_audio_va_info(self):
        nhan: list[int] = []
        a, info = vn.doc(self.url, "Xin chào", "Mai Anh", temperature=0.7, max_chars=128, on_chunk=nhan.append)
        self.assertEqual(len(a), MAU_PER_CHAR * len("Xin chào"))
        self.assertEqual(a.dtype, np.int16)
        self.assertEqual(set(info), {"ttfa_ms", "tong_s", "audio_s", "rtf"})
        self.assertAlmostEqual(info["audio_s"], len(a) / SR, places=2)
        self.assertTrue(nhan and nhan[-1] == len(a) * 2)
        req = self.srv.requests[-1]
        self.assertEqual((req["voice"], req["response_format"], req["sample_rate"], req["temperature"], req["max_chars"]),
                         ("Mai Anh", "pcm", SR, 0.7, 128))

    def test_doc_loi_server_thanh_runtimeerror(self):
        with self.assertRaisesRegex(RuntimeError, "400.*unknown voice"):
            vn.doc(self.url, "a", "LỖI")
        with self.assertRaises(ValueError):
            vn.doc(self.url, "   ", "Mai Anh")

    def test_dang_ky_giong_roi_thay_trong_danh_sach(self):
        with tempfile.TemporaryDirectory() as d:
            clip = Path(d) / "giọng thử.wav"
            vn.ghi_wav(clip, np.zeros(SR, dtype=np.int16))
            kq = vn.dang_ky_giong(self.url, "giọng thử", clip, denoise=True, mo_ta="giọng mẫu của mình")
            self.assertEqual(kq["id"], "giọng thử")
            self.assertIn("giọng thử", [v["id"] for v in vn.giong_tren_server(self.url)])
            self.assertGreater(self.srv.clips[-1], SR * 2)          # clip đã được gửi lên
            with self.assertRaisesRegex(RuntimeError, "409"):
                vn.dang_ky_giong(self.url, "Mai Anh", clip)
            with self.assertRaises(ValueError):
                vn.dang_ky_giong(self.url, "", clip)

    def test_hoi_thoai_ghep_co_nghi(self):
        script = "An: một hai\nBình: ba"
        a, infos = vn.hoi_thoai(self.url, script, {"An": "Mai Anh", "Bình": "Hải Đăng"}, nghi_s=0.5)
        self.assertEqual(len(a), MAU_PER_CHAR * 7 + SR // 2 + MAU_PER_CHAR * 2)
        self.assertEqual([i["ten"] for i in infos], ["An", "Bình"])
        self.assertEqual(self.srv.requests[-1]["voice"], "Hải Đăng")
        with self.assertRaisesRegex(ValueError, "Bình"):
            vn.hoi_thoai(self.url, script, {"An": "Mai Anh"})
        with self.assertRaises(ValueError):
            vn.hoi_thoai(self.url, "không có vai", {})

    def test_srt_sang_audio_giu_moc_va_noi_tiep(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.srt"
            p.write_text("1\n00:00:00,000 --> 00:00:01,000\nmột hai ba bốn năm sáu bảy tám chín mười một hai\n\n"
                         "2\n00:00:01,000 --> 00:00:02,000\nba\n", encoding="utf-8")
            track, tt = vn.srt_sang_audio(self.url, p, "Mai Anh", giu_moc=True)
            # cue 1: 48 ký tự × 10 ms = 0,48 s → không tràn; cue 2 đúng mốc 1 s
            self.assertEqual((tt["so_cue"], tt["day"]), (2, 0))
            self.assertEqual(len(track), SR + MAU_PER_CHAR * 2 + SR // 2)
            track2, tt2 = vn.srt_sang_audio(self.url, p, "Mai Anh", giu_moc=False, nghi_s=0.5)
            self.assertEqual(len(track2), MAU_PER_CHAR * 48 + SR // 2 + MAU_PER_CHAR * 2)
            self.assertFalse(tt2["giu_moc"])

    def test_health_qua_apiserver(self):
        api = vn.ApiServer()
        api.cong = self.srv.server_address[1]
        self.assertEqual(api.health()["backend"], "gia")
        api.cong = 1          # không ai nghe → None, không ném lỗi
        self.assertIsNone(api.health(0.3))


if __name__ == "__main__":
    unittest.main()
