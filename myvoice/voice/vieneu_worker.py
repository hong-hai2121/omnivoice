# -*- coding: utf-8 -*-
"""
vieneu_worker.py — tiến trình con sinh giọng bằng SDK VieNeu-TTS (chạy TRONG .venv của kho
voice/VieNeu-TTS, KHÔNG import được từ venv OmniVoice). Bài tạo giọng thật
(scripts/amain_taogiong_gui.py, chế độ 🗣 VieNeu) bật nó qua vieneu_client.SdkWorker rồi gọi HTTP.

Vì sao không dùng API server của kho (apps.openai_speech)? Server đó chỉ có đường streaming
(infer_stream, bộ lập lịch 16 luồng) — đo 04/11/2026 trên RTX 4060: RTF ≈ 0,46, ngang
OmniVoice clone. SDK gọi thẳng infer()/infer_batch() (batch trên GPU) đạt RTF 0,075/0,035,
VRAM ~0,7 GB — nhanh gấp 6–13 lần, hợp bài dài hàng trăm đoạn.

09/11/2026 — CÁCH ĐỌC MẶC ĐỊNH ĐỔI SANG "mau" (infer_stream, đọc từng mẩu): test phân định cùng
ngày trên RTX 4060 với 600 câu tập 170, không có amain/runner — đường API server (infer_stream,
bộ lập lịch stream) sống 3 phút, RTF 0,66; đường infer()/fused batch (worker cũ) làm driver TDR
141 + màn hình đen 1b8 sau 8 giây, đúng kiểu các đêm 05/11, 08/11, 09/11 trong pipeline. Đường
cũ giữ lại là "gop" (--cach gop) để so sánh khi card/driver đã sửa. Giá của "mau": chậm ~6 lần
(tập 600 câu ~15–20 phút thay vì ~3), không có babble retry cho câu rất ngắn — bước kiểm mất
chữ bằng ASR của run_tts vẫn bắt và render lại. Bộ lập lịch stream giữ max_streams mặc định
của SDK (16) để KHỚP cấu hình API server đã chứng minh sống; VRAM worker ~2 GB thay vì 0,7.

Giao thức (JSON, cổng loopback):
    GET  /health            → {"status":"ok","sr":48000,"voices":[...],"backend":"pytorch","cach":"mau"}
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

--parent-pid N (09/11/2026, user chốt "tắt app = trả VRAM"): worker canh tiến trình cha N
(canh_cha); cha tắt — đóng cửa sổ GUI/launcher, taskkill, sập — là worker TỰ THOÁT ngay,
model ~0,7 GB rời VRAM. Không có cờ này, worker mồ côi cứ nằm giữ VRAM tới khi tắt máy
(Windows không tự tắt tiến trình con theo cha). vieneu_client.SdkWorker.bat luôn truyền.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
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


# Hai cách đọc của SDK (09/11/2026, xem đầu file): "mau" = infer_stream (đọc từng mẩu, đường
# của app Thử giọng / API server), "gop" = infer()/infer_batch() (fused batch engine, đường cũ).
CACH_DOC = ("mau", "gop")
CACH_MAC_DINH = "mau"
CAU_LAM_NONG = "Xin chào."     # câu warm-up như apps/openai_speech.py để dựng sẵn bộ lập lịch stream


class _Engine:
    """Bọc Vieneu() của SDK, trả float32 48 kHz cho từng câu.

    cach="mau": mỗi câu đi qua infer_stream() rồi nối các mẩu lại — đúng đường API server của
    kho (Test A 09/11/2026 sống 3 phút trên RTX 4060). Trong SDK cả hai đường đều là CUDA graph
    một khung/lần; khác nhau ở prefill, codec giải mã từng cửa sổ thay vì cả đoạn, và card chỉ
    bận ~50% thời gian thay vì 100%.
    cach="gop": infer()/infer_batch() qua fused batch engine — nhanh gấp ~6 lần nhưng làm card
    này TDR trong vài giây (Test B 09/11/2026); chỉ dùng khi gọi --cach gop."""

    def __init__(self, device: str = "auto", cach: str = CACH_MAC_DINH):
        from vieneu import Vieneu   # chỉ có trong .venv của kho
        if cach not in CACH_DOC:
            raise ValueError(f"cách đọc lạ: {cach} (chọn {', '.join(CACH_DOC)})")
        self.cach = cach
        kw = {} if device == "auto" else {"device": device}
        t = time.perf_counter()
        self.tts = Vieneu(**kw)
        self.backend = getattr(self.tts, "backend", "?")
        if cach == "mau":
            # Dựng sẵn bộ lập lịch stream + graph như API server làm lúc khởi động: câu thật
            # đầu tiên không gánh phần capture, và /health = sẵn sàng thật.
            for _ in self.tts.infer_stream(CAU_LAM_NONG, apply_watermark=False):
                pass
        self.t_nap = round(time.perf_counter() - t, 1)
        try:
            self.voices = [label for label, _vid in self.tts.list_preset_voices()]
        except Exception:
            self.voices = []

    def _doc_tung_mau(self, text: str, voice: str, temperature: float, top_k: int) -> np.ndarray:
        """Một câu qua infer_stream(): gom mọi mẩu (kể cả khoảng lặng SDK chèn giữa các chunk
        của câu) thành một mảng — bên nhận (run_tts) vẫn thấy đúng một audio cho một câu."""
        parts = [np.asarray(p, dtype=np.float32)
                 for p in self.tts.infer_stream(text, voice=voice, temperature=temperature, top_k=top_k)
                 if p is not None and len(p)]
        return np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)

    def infer(self, texts: list[str], voice: str, temperature: float = 0.4, top_k: int = 50) -> list:
        if self.cach == "mau":
            return [self._doc_tung_mau(t, voice, temperature, top_k) for t in texts]
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
                                     backend=getattr(engine, "backend", "?"),
                                     cach=getattr(engine, "cach", "?")))
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


# ── CANH TIẾN TRÌNH CHA ──────────────────────────────────────────────────────────
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_SYNCHRONIZE = 0x00100000
_STILL_ACTIVE = 259
_INFINITE = 0xFFFFFFFF


def cha_con_song(pid: int) -> bool:
    """Tiến trình `pid` còn sống? Windows: OpenProcess + GetExitCodeProcess (STILL_ACTIVE);
    nơi khác: os.kill(pid, 0). Không mở được handle = đã chết (cùng user nên không phải
    chuyện quyền)."""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            return False
        try:
            ma = ctypes.c_ulong()
            if not k32.GetExitCodeProcess(h, ctypes.byref(ma)):
                return False
            return ma.value == _STILL_ACTIVE
        finally:
            k32.CloseHandle(h)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def canh_cha(pid: int, khi_chet, moi: float = 1.0):
    """Luồng nền theo dõi tiến trình cha `pid`: cha kết thúc → gọi `khi_chet()` (bài thật:
    thoát ngay để trả VRAM). Windows: mở handle SYNCHRONIZE rồi WaitForSingleObject — về đúng
    lúc cha tắt, không tốn CPU, không sợ PID bị cấp lại; không mở được handle (cha đã chết
    trước khi worker kịp canh) → dò bằng cha_con_song mỗi `moi` giây. pid 0 → không canh,
    trả None. Trả Thread (daemon) để test chờ được."""
    if not pid or pid <= 0:
        return None

    def _canh() -> None:
        if sys.platform == "win32":
            import ctypes
            k32 = ctypes.windll.kernel32
            h = k32.OpenProcess(_SYNCHRONIZE, False, pid)
            if h:
                try:
                    k32.WaitForSingleObject(h, _INFINITE)
                finally:
                    k32.CloseHandle(h)
                khi_chet()
                return
        while cha_con_song(pid):
            time.sleep(moi)
        khi_chet()

    t = threading.Thread(target=_canh, daemon=True, name="canh-cha")
    t.start()
    return t


def _thoat_theo_cha() -> None:
    """Cha tắt → worker tắt ngay (os._exit: không đợi luồng HTTP, model rời VRAM theo tiến trình)."""
    print("⏹ tiến trình cha đã tắt → worker VieNeu tự tắt, trả VRAM", flush=True)
    os._exit(0)


def doi_so() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="VieNeu SDK worker (HTTP loopback)")
    ap.add_argument("--port", type=int, default=8010)
    ap.add_argument("--device", default="auto",
                    help="auto|cuda|cpu — cuda = ÉP GPU: không có CUDA thì thoát mã "
                         f"{MA_KHONG_GPU}, không lặng lẽ chạy CPU")
    ap.add_argument("--parent-pid", type=int, default=0,
                    help="PID tiến trình cha: cha tắt (đóng app, taskkill, sập) là worker tự thoát "
                         "ngay để trả VRAM; 0 = không canh")
    ap.add_argument("--cach", choices=CACH_DOC, default=CACH_MAC_DINH,
                    help="mau = đọc từng mẩu qua infer_stream (mặc định từ 09/11/2026, đường sống "
                         "trên RTX 4060); gop = infer()/fused batch, nhanh ~6 lần nhưng làm card "
                         "TDR — chỉ để so sánh")
    return ap


def main() -> int:
    a = doi_so().parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    # Canh cha TRƯỚC khi nạp model: cha tắt giữa lúc đang nạp cũng thoát luôn.
    canh_cha(a.parent_pid, _thoat_theo_cha)
    if a.device == "cuda":
        ly_do = kiem_cuda()
        if ly_do:
            print(f"{DAU_KHONG_GPU} {ly_do}", flush=True)
            return MA_KHONG_GPU
    print(f"⏳ nạp VieNeu-TTS v3 Turbo (SDK, device={a.device}, cách đọc={a.cach})…", flush=True)
    eng = _Engine(a.device, a.cach)
    if a.device == "cuda" and str(eng.backend).lower() == "onnx":
        # Chốt thứ hai: bị ép GPU mà SDK vẫn chọn ONNX (đường CPU) thì coi như không có GPU.
        print(f"{DAU_KHONG_GPU} SDK nạp backend ONNX/CPU dù được yêu cầu cuda", flush=True)
        return MA_KHONG_GPU
    srv = make_server(eng, a.port)
    print(f"✅ worker sẵn sàng sau {eng.t_nap}s: backend={eng.backend}, cách đọc={eng.cach}, "
          f"{len(eng.voices)} giọng, cổng {a.port}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    print("⏹ worker tắt", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
