# -*- coding: utf-8 -*-
"""
vieneu_worker.py — tiến trình con sinh giọng bằng SDK VieNeu-TTS (chạy TRONG .venv của kho
voice/VieNeu-TTS, KHÔNG import được từ venv OmniVoice). Bài tạo giọng thật
(scripts/amain_taogiong_gui.py, chế độ 🗣 VieNeu) bật nó qua vieneu_client.SdkWorker rồi gọi HTTP.

Vì sao không dùng API server của kho (apps.openai_speech)? Server đó chỉ có đường streaming
(infer_stream, bộ lập lịch 16 luồng) — đo 04/11/2026 trên RTX 4060: RTF ≈ 0,46, ngang
OmniVoice clone. SDK gọi thẳng infer()/infer_batch() (batch trên GPU) đạt RTF 0,075/0,035,
VRAM ~0,7 GB — nhanh gấp 6–13 lần, hợp bài dài hàng trăm đoạn.

Giao thức (JSON, cổng loopback):
    GET  /health            → {"status":"ok","sr":48000,"voices":[...],"backend":"pytorch"}
    POST /infer             ← {"texts":[...], "voice":"Ngọc Huyền", "temperature":0.4, "top_k":50}
                            → {"sr":48000, "audios":[base64 int16 mono, ...]}   (cùng thứ tự texts)
    POST /shutdown          → tắt tiến trình
Lỗi → mã 4xx/5xx + {"error": "..."}.

Chạy tay:  .venv/Scripts/python.exe ../vieneu_worker.py --port 8010
Phần máy chủ tách khỏi SDK (make_server(engine, port)) để test bằng engine giả trong venv
OmniVoice (tests/test_vieneu_mode.py) mà không cần cài VieNeu.

--device cuda = ÉP GPU (05/11/2026; bài thật luôn gọi kiểu này): không dùng được CUDA thì in
dòng "❌ KHÔNG CÓ GPU: …" rồi thoát mã MA_KHONG_GPU, KHÔNG nạp model. SDK để "auto" thì khi
mất CUDA nó lặng lẽ chạy ONNX/CPU — đêm 05/11/2026 driver NVIDIA treo, 5 tập sinh đủ đoạn
bằng CPU (39 đoạn/phút thay vì 165) rồi mới dừng ở bước ASR kiểm tra (GPU bắt buộc).
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np

SR = 48_000
# Hai hằng dưới phải KHỚP vieneu_client.py (bên đó chạy ở venv OmniVoice, đọc mã thoát +
# dòng log của worker); tests/test_vieneu_mode.py giữ cho hai bên không lệch.
MA_KHONG_GPU = 79                      # mã thoát khi bị ép --device cuda mà CUDA không dùng được
DAU_KHONG_GPU = "❌ KHÔNG CÓ GPU:"     # đầu dòng báo lý do, client chép vào lỗi ném lên


def kiem_cuda() -> str:
    """"" nếu CUDA dùng được THẬT trong .venv này; ngược lại là lý do (một dòng).

    Thử cấp phát một tensor chứ không chỉ hỏi is_available(): sau khi driver card treo,
    có lúc is_available() vẫn True mà tạo context thì lỗi. Model đằng nào cũng nạp lên
    card ngay sau đó nên phép thử này không tốn thêm gì."""
    try:
        import torch
    except Exception as e:  # noqa: BLE001 — .venv cài bản CPU (chỉ ONNX) thì không có torch
        return (f"không nạp được torch trong .venv của kho ({type(e).__name__}: {e}) — "
                "bản cài CPU? Mở app Thử giọng → tab 🗣️ → ⬇ Cài GPU")
    try:
        if not torch.cuda.is_available():
            return ("torch.cuda.is_available() = False — driver card màn hình vừa treo "
                    "(khởi động lại máy) hoặc .venv của kho cài bản CPU (⬇ Cài GPU)")
        torch.zeros(1, device="cuda")
    except Exception as e:  # noqa: BLE001
        return f"CUDA không khởi tạo được ({type(e).__name__}: {e}) — khởi động lại máy rồi chạy lại"
    return ""


def ma_hoa_audio(a) -> str:
    """float32 [-1, 1] (hoặc int16) → base64 int16 mono."""
    a = np.asarray(a)
    if a.dtype == np.int16:          # về float TRƯỚC khi lấy trung bình kênh (mean đổi dtype)
        a = a.astype(np.float32) / 32768.0
    if a.ndim > 1:
        a = a.mean(axis=1)
    a = np.clip(np.asarray(a, dtype=np.float32), -1.0, 1.0)
    return base64.b64encode((a * 32767.0).astype("<i2").tobytes()).decode("ascii")


def giai_ma_audio(s: str) -> np.ndarray:
    """base64 int16 mono → float32 [-1, 1]."""
    return np.frombuffer(base64.b64decode(s), dtype="<i2").astype(np.float32) / 32768.0


class _Engine:
    """Bọc Vieneu() của SDK: infer 1 câu hay infer_batch nhiều câu, trả float32."""

    def __init__(self, device: str = "auto"):
        from vieneu import Vieneu   # chỉ có trong .venv của kho
        kw = {} if device == "auto" else {"device": device}
        t = time.perf_counter()
        self.tts = Vieneu(**kw)
        self.backend = getattr(self.tts, "backend", "?")
        self.t_nap = round(time.perf_counter() - t, 1)
        try:
            self.voices = [label for label, _vid in self.tts.list_preset_voices()]
        except Exception:
            self.voices = []

    def infer(self, texts: list[str], voice: str, temperature: float = 0.4, top_k: int = 50) -> list:
        if len(texts) == 1:
            return [self.tts.infer(texts[0], voice=voice, temperature=temperature, top_k=top_k,
                                   show_progress=False)]
        return self.tts.infer_batch(texts, voice=voice, temperature=temperature, top_k=top_k)


def make_server(engine, port: int, host: str = "127.0.0.1") -> ThreadingHTTPServer:
    """HTTP server bọc `engine` (có .infer(texts, voice, temperature, top_k) → list audio,
    .voices, .backend). Một lần chỉ một lệnh infer chạy (khoá) — GPU không chia sẻ."""
    khoa = threading.Lock()

    class H(BaseHTTPRequestHandler):
        server_version = "vieneu_worker/1"

        def log_message(self, fmt, *args):   # im: log của mình in ở dưới
            pass

        def _json(self, code: int, obj: dict) -> None:
            data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/health":
                self._json(200, dict(status="ok", sr=SR, voices=list(getattr(engine, "voices", [])),
                                     backend=getattr(engine, "backend", "?")))
            else:
                self._json(404, dict(error="không có đường " + self.path))

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n) if n else b"{}"
            if self.path == "/shutdown":
                self._json(200, dict(status="bye"))
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            if self.path != "/infer":
                self._json(404, dict(error="không có đường " + self.path))
                return
            try:
                req = json.loads(raw.decode("utf-8"))
                texts = [str(t).strip() for t in (req.get("texts") or [])]
                if not texts or any(not t for t in texts):
                    raise ValueError("texts rỗng")
                voice = req.get("voice") or None
                temperature = float(req.get("temperature", 0.4))
                top_k = int(req.get("top_k", 50))
            except (ValueError, TypeError, json.JSONDecodeError) as e:
                self._json(400, dict(error=f"yêu cầu sai: {e}"))
                return
            t = time.perf_counter()
            try:
                with khoa:
                    audios = engine.infer(texts, voice, temperature, top_k)
            except Exception as e:  # noqa: BLE001 — trả lỗi về client thay vì chết server
                print(f"❌ infer lỗi: {e!r}", flush=True)
                self._json(500, dict(error=f"{type(e).__name__}: {e}"))
                return
            giay = sum(len(a) for a in audios) / SR
            print(f"🔊 {len(texts)} đoạn · {giay:.1f}s audio · {time.perf_counter() - t:.2f}s · giọng {voice}",
                  flush=True)
            self._json(200, dict(sr=SR, audios=[ma_hoa_audio(a) for a in audios]))

    return ThreadingHTTPServer((host, port), H)


def main() -> int:
    ap = argparse.ArgumentParser(description="VieNeu SDK worker (HTTP loopback)")
    ap.add_argument("--port", type=int, default=8010)
    ap.add_argument("--device", default="auto",
                    help="auto|cuda|cpu — cuda = ÉP GPU: không có CUDA thì thoát mã "
                         f"{MA_KHONG_GPU}, không lặng lẽ chạy CPU")
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if a.device == "cuda":
        ly_do = kiem_cuda()
        if ly_do:
            print(f"{DAU_KHONG_GPU} {ly_do}", flush=True)
            return MA_KHONG_GPU
    print(f"⏳ nạp VieNeu-TTS v3 Turbo (SDK, device={a.device})…", flush=True)
    eng = _Engine(a.device)
    if a.device == "cuda" and str(eng.backend).lower() == "onnx":
        # Chốt thứ hai: bị ép GPU mà SDK vẫn chọn ONNX (đường CPU) thì coi như không có GPU.
        print(f"{DAU_KHONG_GPU} SDK nạp backend ONNX/CPU dù được yêu cầu cuda", flush=True)
        return MA_KHONG_GPU
    srv = make_server(eng, a.port)
    print(f"✅ worker sẵn sàng sau {eng.t_nap}s: backend={eng.backend}, {len(eng.voices)} giọng, "
          f"cổng {a.port}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    print("⏹ worker tắt", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
