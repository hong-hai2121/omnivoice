# -*- coding: utf-8 -*-
"""
vieneu_client.py — nối VieNeu-TTS vào app Thử giọng (voice/thu_giong.py) mà KHÔNG import
gói vieneu vào venv của OmniVoice (04/11/2026).

Cách nối: kho đã clone ở voice/VieNeu-TTS có .venv riêng do `uv sync` tạo (torch 2.8 cu128
cho GPU hoặc chỉ ONNX cho CPU). App bật API server chuẩn OpenAI của kho
(`python -m apps.openai_speech`, cổng 8000) bằng python của .venv đó rồi gọi HTTP:
    GET  /v1/voices          danh sách giọng dựng sẵn + giọng đã đăng ký
    POST /v1/voices          đăng ký giọng clone từ clip (multipart name/file/denoise)
    POST /v1/audio/speech    sinh audio; xin pcm s16le 48 kHz để đo chunk đầu và tự ghi wav
    GET  /health             sẵn sàng khi model đã nạp + warm-up xong
Web UI Gradio của kho (`python -m apps.gradio_main`, cổng 7860) cũng bật từ đây để dùng
đủ 4 tab gốc (Đọc truyện/PDF, Hội thoại, SRT, Voice Cloning) trên trình duyệt.

Bài tạo giọng THẬT (scripts/amain_taogiong_gui.py, chế độ 🗣 VieNeu — mặc định từ 04/11/2026)
không đi qua API server trên: server chỉ có đường streaming (RTF ≈ 0,46, ngang OmniVoice).
Nó bật `SdkWorker` — voice/vieneu_worker.py chạy SDK infer/infer_batch trong .venv của kho
(RTF 0,04–0,08, VRAM ~0,7 GB) và gọi POST /infer (JSON, audio base64 int16 48 kHz).

Module này KHÔNG có Tk: hàm thuần (tách kịch bản hội thoại, đọc SRT, xếp timeline),
quản lý tiến trình con (cài đặt, server, web UI) và client HTTP (requests). Test ở
myvoice/tests/test_vieneu_client.py chạy với server giả, không cần cài VieNeu.
"""
from __future__ import annotations

import base64
import os
import re
import shutil
import socket
import subprocess
import threading
import time
import wave
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import requests

HERE = Path(__file__).resolve().parent                  # myvoice/voice
VIENEU_DIR = HERE / "VieNeu-TTS"                        # kho clone (git clone 04/11/2026)
VENV_PY = VIENEU_DIR / ".venv" / "Scripts" / "python.exe"   # python riêng do `uv sync` tạo
UV = shutil.which("uv") or str(Path.home() / ".local" / "bin" / "uv.exe")
SR = 48_000                                             # v3 Turbo ra 48 kHz
CONG_API = 8000                                         # PORT mặc định của apps.openai_speech
CONG_WEB = 7860                                         # GRADIO_SERVER_PORT mặc định
WORKER_PY = HERE / "vieneu_worker.py"                   # worker SDK cho bài tạo giọng thật (chế độ 🗣 VieNeu)
CONG_WORKER = 8010                                      # cổng worker; bận thì dò tiếp (chon_cong)
# Worker bị ép --device cuda mà CUDA không dùng được → in dòng DAU_KHONG_GPU rồi thoát mã
# MA_KHONG_GPU (05/11/2026). Hai hằng phải KHỚP vieneu_worker.py (worker chạy ở venv khác
# nên không import chung được); tests/test_vieneu_mode.py giữ cho hai bên không lệch.
MA_KHONG_GPU = 79
DAU_KHONG_GPU = "❌ KHÔNG CÓ GPU:"
GIONG_MAC_DINH = "Ngọc Huyền"                           # giọng VieNeu mặc định của bài thật (user chốt 04/11/2026)
# 25 giọng dựng sẵn v3 Turbo (assets/voices_v3_turbo.json của kho): 10 giọng đầu là mục
# "featured" theo thứ tự kho xếp, còn lại theo file. Giữ TĨNH để GUI hiện danh sách khi
# worker chưa bật; worker lên thì SdkWorker.giong lấy từ /health.
GIONG_DUNG_SAN = (
    "Adam bựa", "Trúc Ly", "Thiện Minh", "Mai Anh", "Hải Đăng", "Thùy Dung", "Thiền Tâm Đức",
    "Ngọc Huyền", "Quang Sơn", "Ngọc Trân", "Minh Đức", "Phạm Tuyên", "Thái Sơn", "Xuân Vĩnh",
    "Thanh Bình", "Ngọc Linh", "Đoan Trang", "Thục Đoan", "Minh Triết", "Mỹ Duyên", "Quỳnh Anh",
    "Đức Trí", "Kim Thanh", "Adam", "Quốc Tuấn",
)
TAG_CAM_XUC = ("[cười]", "[thở dài]", "[hắng giọng]")  # tag phi ngôn từ (thử nghiệm)
BACKENDS = ("auto", "pytorch", "onnx")                  # VIENEU_BACKEND: auto → có CUDA thì pytorch
PRECISIONS = ("fp32", "int8")                           # VIENEU_PRECISION (chỉ CPU/ONNX; int8 cần VNNI)
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_VOICE_NAME = re.compile(r"[^\W_][\w .\-]{0,63}")       # đúng luật tên giọng của server (fullmatch)


# ── trạng thái kho / cài đặt ──────────────────────────────────────────────────
def phien_ban() -> str:
    """Bản vieneu trong pyproject.toml của kho; không đọc được → "?"."""
    try:
        m = re.search(r'^version\s*=\s*"([^"]+)"',
                      (VIENEU_DIR / "pyproject.toml").read_text(encoding="utf-8", errors="replace"), re.M)
        return m.group(1) if m else "?"
    except OSError:
        return "?"


def trang_thai() -> dict:
    """Kho đã clone chưa, cài chưa (.venv của kho; có torch = bản GPU), bản nào. Không
    import vieneu. Trả dict: co_kho, da_cai, gpu, phien_ban, mo_ta (một dòng cho nhãn)."""
    co_kho = (VIENEU_DIR / "pyproject.toml").exists()
    da_cai = VENV_PY.exists()
    gpu = da_cai and (VIENEU_DIR / ".venv" / "Lib" / "site-packages" / "torch").is_dir()
    ban = phien_ban() if co_kho else "?"
    if not co_kho:
        mo_ta = "chưa thấy kho — chạy  git clone https://github.com/pnnbao97/VieNeu-TTS.git  trong voice/"
    elif not da_cai:
        mo_ta = (f"đã clone (bản {ban}); CHƯA cài — bấm ⬇ Cài GPU (torch cu128, máy có RTX) hoặc "
                 "⬇ Cài CPU (chỉ ONNX, nhẹ); cài vào .venv riêng trong kho, không đụng venv OmniVoice")
    else:
        mo_ta = (f"đã cài bản {ban} ({'GPU: PyTorch cu128 + ONNX' if gpu else 'CPU: ONNX, không torch'}) "
                 "trong voice/VieNeu-TTS/.venv — bật API server rồi dùng thử ở các tab bên cạnh")
    return dict(co_kho=co_kho, da_cai=da_cai, gpu=gpu, phien_ban=ban, mo_ta=mo_ta)


def cong_trong(cong: int, host: str = "127.0.0.1") -> bool:
    """Cổng còn trống không — thử BIND (connect tới cổng trống trên máy này đợi hết
    timeout, xem ghi nhớ cổng 8766)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, cong))
            return True
        except OSError:
            return False


# ── tiến trình con: cài đặt, API server, Web UI ───────────────────────────────
def _env(**extra) -> dict:
    """Môi trường cho tiến trình con: UTF-8 + không đệm stdout (đọc log ngay), cộng các
    biến truyền vào (None thì bỏ)."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1", PYTHONUNBUFFERED="1")
    env.update({k: str(v) for k, v in extra.items() if v is not None})
    return env


def _doc_dong(proc: subprocess.Popen, on_line: Callable[[str], None]) -> None:
    """Đọc stdout (đã gộp stderr) từng dòng → on_line(chuỗi), tới khi tiến trình đóng ống."""
    assert proc.stdout is not None
    for raw in iter(proc.stdout.readline, b""):
        try:
            on_line(raw.decode("utf-8", "replace").rstrip())
        except Exception:
            pass


def cai_dat(gpu: bool, on_line: Callable[[str], None], uv: Optional[str] = None) -> int:
    """`uv sync` (CPU) hoặc `uv sync --extra cuda` (GPU) trong kho — tạo/cập nhật .venv riêng.
    Dòng log → on_line; CHẶN tới khi xong, trả mã thoát (0 = OK). Gọi trong thread nền."""
    uv = uv or UV
    if not Path(uv).exists() and not shutil.which(uv):
        on_line(f"❌ không thấy uv ({uv}) — cài: powershell -c \"irm https://astral.sh/uv/install.ps1 | iex\"")
        return 127
    cmd = [uv, "sync"] + (["--extra", "cuda"] if gpu else [])
    on_line("$ " + " ".join(cmd) + f"   (trong {VIENEU_DIR})")
    proc = subprocess.Popen(cmd, cwd=str(VIENEU_DIR), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            env=_env(UV_LINK_MODE="copy"), creationflags=CREATE_NO_WINDOW)
    _doc_dong(proc, on_line)
    return proc.wait()


class TienTrinh:
    """Một tiến trình con chạy từ .venv của kho (API server / Web UI): bật, đọc log nền, tắt."""

    def __init__(self, ten: str):
        self.ten = ten
        self.proc: Optional[subprocess.Popen] = None
        self.cong: Optional[int] = None

    @property
    def dang_chay(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.cong}"

    def _bat(self, cmd: list[str], env: dict, cong: int, on_line: Callable[[str], None]) -> None:
        if self.dang_chay:
            raise RuntimeError(f"{self.ten} đang chạy ở cổng {self.cong}")
        if not VENV_PY.exists():
            raise RuntimeError("VieNeu-TTS chưa cài (chưa có .venv trong kho) — bấm ⬇ Cài trước")
        if not cong_trong(cong):
            raise RuntimeError(f"cổng {cong} đang bận — đổi cổng khác (hoặc server cũ còn chạy)")
        self.cong = cong
        self.proc = subprocess.Popen(cmd, cwd=str(VIENEU_DIR), stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, env=env, creationflags=CREATE_NO_WINDOW)
        threading.Thread(target=_doc_dong, args=(self.proc, on_line), daemon=True,
                         name=f"log-{self.ten}").start()

    def tat(self) -> None:
        """Tắt tiến trình (terminate, quá 5 s thì kill). Không chạy thì thôi."""
        if self.proc is None:
            return
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None


class ApiServer(TienTrinh):
    """`python -m apps.openai_speech` — API chuẩn OpenAI của kho, nạp model lúc khởi động."""

    def __init__(self):
        super().__init__("API server")
        self.backend = "auto"

    @staticmethod
    def env_server(cong: int, backend: str = "auto", precision: str = "fp32",
                   device: str = "auto", max_streams: Optional[int] = None) -> dict:
        """Biến môi trường server đọc (xem docstring apps/openai_speech.py). Tách riêng để test."""
        if backend not in BACKENDS:
            raise ValueError(f"backend lạ: {backend} (chọn {', '.join(BACKENDS)})")
        if precision not in PRECISIONS:
            raise ValueError(f"precision lạ: {precision} (chọn {', '.join(PRECISIONS)})")
        return _env(PORT=cong, HOST="127.0.0.1", VIENEU_BACKEND=backend, VIENEU_PRECISION=precision,
                    VIENEU_DEVICE=device, VIENEU_MAX_STREAMS=max_streams)

    def bat(self, cong: int = CONG_API, backend: str = "auto", precision: str = "fp32",
            device: str = "auto", max_streams: Optional[int] = None,
            on_line: Callable[[str], None] = print) -> None:
        self.backend = backend
        self._bat([str(VENV_PY), "-m", "apps.openai_speech"],
                  self.env_server(cong, backend, precision, device, max_streams), cong, on_line)

    def health(self, timeout: float = 2.0) -> Optional[dict]:
        """dict từ /health khi server đã sẵn sàng; None khi chưa trả lời / lỗi."""
        try:
            r = requests.get(self.url + "/health", timeout=timeout)
            return r.json() if r.status_code == 200 else None
        except (requests.RequestException, ValueError):
            return None

    def cho_san_sang(self, timeout: float = 900.0, moi: float = 1.0) -> Optional[dict]:
        """Đợi /health trả OK (model nạp + warm-up; lần đầu còn tải model từ Hugging Face
        nên có thể lâu). Tiến trình chết giữa chừng hoặc hết giờ → None."""
        han = time.monotonic() + timeout
        while time.monotonic() < han:
            if not self.dang_chay:
                return None
            h = self.health()
            if h:
                return h
            time.sleep(moi)
        return None


class WebUi(TienTrinh):
    """`python -m apps.gradio_main` — Web UI Gradio của kho (4 tab gốc) trên trình duyệt."""

    def __init__(self):
        super().__init__("Web UI")

    def bat(self, cong: int = CONG_WEB, on_line: Callable[[str], None] = print) -> None:
        self._bat([str(VENV_PY), "-m", "apps.gradio_main"],
                  _env(GRADIO_SERVER_PORT=cong, GRADIO_SERVER_NAME="127.0.0.1"), cong, on_line)

    def cho_san_sang(self, timeout: float = 120.0, moi: float = 0.5) -> bool:
        """Gradio nghe cổng là xong (model nạp sau, bằng nút 🔄 Tải Model trên trang)."""
        han = time.monotonic() + timeout
        while time.monotonic() < han:
            if not self.dang_chay:
                return False
            try:
                if requests.get(self.url, timeout=1).status_code < 500:
                    return True
            except requests.RequestException:
                pass
            time.sleep(moi)
        return False


# ── client HTTP ───────────────────────────────────────────────────────────────
def _loi(r: requests.Response) -> str:
    """Thông báo lỗi của server theo kiểu OpenAI {"error": {"message"}}; không phải JSON thì
    lấy chữ thô (cắt ngắn)."""
    try:
        return str(r.json()["error"]["message"])
    except Exception:
        return (r.text or f"HTTP {r.status_code}").strip()[:300]


def _kiem(r: requests.Response) -> requests.Response:
    if r.status_code >= 400:
        raise RuntimeError(f"server trả {r.status_code}: {_loi(r)}")
    return r


def giong_tren_server(url: str) -> list[dict]:
    """GET /v1/voices → [{"id", "name", "description", ...}] (giọng dựng sẵn + đã đăng ký).
    Chấp nhận cả phần tử là chuỗi (id trần) cho chắc."""
    r = _kiem(requests.get(url + "/v1/voices", timeout=10))
    data = r.json()
    items = data.get("data", data) if isinstance(data, dict) else data
    out = []
    for it in items or []:
        if isinstance(it, str):
            out.append(dict(id=it, name=it, description=""))
        else:
            vid = it.get("id") or it.get("name")
            if vid:
                out.append(dict(id=vid, name=it.get("name") or vid, description=it.get("description") or ""))
    return out


def ten_giong_tu_file(p: Path | str) -> str:
    """Tên đăng ký giọng clone từ tên file mẫu: bỏ đuôi, giữ chữ/số (có dấu)/khoảng
    trắng/./-/_ theo luật server, bắt đầu bằng chữ hoặc số, tối đa 64 ký tự."""
    stem = Path(p).stem
    stem = re.sub(r"[^\w .\-]+", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip()
    stem = re.sub(r"^[\W_]+", "", stem)[:64].rstrip()
    return stem or "giong"


def dang_ky_giong(url: str, ten: str, clip: Path | str, denoise: bool = True, mo_ta: str = "") -> dict:
    """POST /v1/voices: đăng ký clip (3–8 s, dài hơn server tự cắt) làm giọng `ten` trong
    tiến trình server đang chạy. Tên trùng giọng dựng sẵn → server trả 409."""
    clip = Path(clip)
    if not _VOICE_NAME.fullmatch(ten):
        raise ValueError(f"tên giọng không hợp lệ: {ten!r} (chữ/số/khoảng trắng/./-/_, tối đa 64)")
    with open(clip, "rb") as f:
        r = requests.post(url + "/v1/voices", data=dict(name=ten, denoise=str(denoise).lower(),
                                                        description=mo_ta or ""),
                          files={"file": (clip.name, f)}, timeout=300)
    return _kiem(r).json()


def doc(url: str, text: str, voice: Optional[str], temperature: float = 0.8, max_chars: int = 256,
        timeout: float = 900.0, on_chunk: Optional[Callable[[int], None]] = None) -> tuple[np.ndarray, dict]:
    """POST /v1/audio/speech xin pcm s16le 48 kHz, đọc theo luồng để đo CHUNK ĐẦU (TTFA).
    Trả (audio int16 mono, info: ttfa_ms, tong_s, audio_s, rtf). on_chunk(số byte đã nhận)."""
    text = (text or "").strip()
    if not text:
        raise ValueError("văn bản trống")
    body = dict(model="vieneu-v3-turbo", input=text, voice=voice or None, response_format="pcm",
                sample_rate=SR, temperature=float(temperature), max_chars=int(max_chars))
    t0 = time.perf_counter()
    r = requests.post(url + "/v1/audio/speech", json=body, stream=True, timeout=(10, timeout))
    _kiem(r)
    chunks: list[bytes] = []
    ttfa: Optional[float] = None
    n = 0
    for c in r.iter_content(chunk_size=8192):
        if not c:
            continue
        if ttfa is None:
            ttfa = time.perf_counter() - t0
        chunks.append(c)
        n += len(c)
        if on_chunk:
            on_chunk(n)
    tong = time.perf_counter() - t0
    data = b"".join(chunks)
    if len(data) % 2:
        data = data[:-1]
    audio = np.frombuffer(data, dtype="<i2")
    audio_s = len(audio) / SR
    info = dict(ttfa_ms=round((ttfa or tong) * 1000), tong_s=round(tong, 2), audio_s=round(audio_s, 2),
                rtf=round(tong / audio_s, 3) if audio_s > 0 else None)
    return audio, info


def ghi_wav(path: Path | str, audio: np.ndarray, sr: int = SR) -> Path:
    """Ghi int16 mono ra wav PCM (winsound phát được). Tạo thư mục nếu thiếu."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    a = np.asarray(audio)
    if a.dtype != np.int16:
        a = np.clip(a, -32768, 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(a.tobytes())
    return path


def mo_ta_info(info: dict) -> str:
    """Một dòng cho nhãn kết quả: chunk đầu · thời gian sinh · độ dài audio · RTF."""
    rtf = info.get("rtf")
    return (f"chunk đầu {info.get('ttfa_ms', '?')} ms · sinh {info.get('tong_s', '?')} s · "
            f"audio {info.get('audio_s', '?')} s · RTF {rtf if rtf is not None else '?'}"
            + ("  (RTF < 1 = nhanh hơn thời gian thực)" if rtf is not None else ""))


# ── hội thoại nhiều người nói ─────────────────────────────────────────────────
_DONG_VAI = re.compile(r"^\s*([^:：\n]{1,40}?)\s*[:：]\s*(.+?)\s*$")


def tach_hoi_thoai(script: str) -> list[tuple[str, str]]:
    """Kịch bản "Tên: câu nói" mỗi dòng → [(tên, câu)]. Dòng không có "Tên:" nối tiếp vào
    câu của người nói trước (xuống dòng giữa câu); đứng đầu mà không có tên thì bỏ."""
    out: list[tuple[str, str]] = []
    for dong in (script or "").splitlines():
        if not dong.strip():
            continue
        m = _DONG_VAI.match(dong)
        if m:
            out.append((m.group(1).strip(), m.group(2).strip()))
        elif out:
            ten, cau = out[-1]
            out[-1] = (ten, (cau + " " + dong.strip()).strip())
    return out


def nhan_vat(script: str) -> list[str]:
    """Tên các vai theo thứ tự xuất hiện, không trùng."""
    seen: list[str] = []
    for ten, _ in tach_hoi_thoai(script):
        if ten not in seen:
            seen.append(ten)
    return seen


def noi_tiep(clips: list[np.ndarray], nghi_s: float = 0.3, sr: int = SR) -> np.ndarray:
    """Ghép các đoạn int16 nối tiếp, chèn khoảng lặng `nghi_s` giữa các đoạn."""
    gap = np.zeros(int(max(nghi_s, 0.0) * sr), dtype=np.int16)
    parts: list[np.ndarray] = []
    for i, c in enumerate(clips):
        if i and len(gap):
            parts.append(gap)
        parts.append(np.asarray(c, dtype=np.int16))
    return np.concatenate(parts) if parts else np.zeros(0, dtype=np.int16)


def hoi_thoai(url: str, script: str, giong: dict[str, str], nghi_s: float = 0.3, temperature: float = 0.8,
              on_progress: Optional[Callable[[int, int, str], None]] = None) -> tuple[np.ndarray, list[dict]]:
    """Sinh từng câu bằng giọng của vai đó (giong[tên] = id giọng trên server) rồi ghép nối
    tiếp có khoảng lặng. Trả (audio int16, info từng câu). Vai chưa gán giọng → lỗi rõ."""
    cac_cau = tach_hoi_thoai(script)
    if not cac_cau:
        raise ValueError("kịch bản trống hoặc không có dòng dạng  Tên: câu nói")
    thieu = sorted({t for t, _ in cac_cau if not giong.get(t)})
    if thieu:
        raise ValueError("chưa gán giọng cho: " + ", ".join(thieu))
    clips, infos = [], []
    for i, (ten, cau) in enumerate(cac_cau, 1):
        if on_progress:
            on_progress(i, len(cac_cau), ten)
        a, info = doc(url, cau, giong[ten], temperature=temperature)
        clips.append(a)
        infos.append(dict(info, ten=ten, cau=cau))
    return noi_tiep(clips, nghi_s), infos


# ── SRT → audio ───────────────────────────────────────────────────────────────
_TIME = re.compile(r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})")
_TAG = re.compile(r"<[^>]+>|\{[^}]+\}")


def _ms(m: re.Match) -> int:
    h, mi, s, frac = m.groups()
    frac = (frac + "000")[:3]
    return ((int(h) * 60 + int(mi)) * 60 + int(s)) * 1000 + int(frac)


def doc_srt(text: str) -> list[dict]:
    """Đọc .srt dễ tính (như apps/srt_speech.py của kho): khối cách nhau bằng dòng trống,
    dòng số thứ tự tuỳ chọn, `HH:MM:SS,mmm --> HH:MM:SS,mmm`, rồi 1+ dòng chữ; bỏ tag
    HTML/ASS, bỏ cue trống; trả [{start_ms, end_ms, text}] theo thứ tự bắt đầu."""
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    cues: list[dict] = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        ti = next((i for i, l in enumerate(lines) if "-->" in l), None)
        if ti is None:
            continue
        ma = _TIME.search(lines[ti].split("-->", 1)[0])
        mb = _TIME.search(lines[ti].split("-->", 1)[1])
        if not ma or not mb:
            continue
        body = re.sub(r"\s+", " ", " ".join(_TAG.sub("", l) for l in lines[ti + 1:])).strip()
        if not body:
            continue
        a = _ms(ma)
        cues.append(dict(start_ms=a, end_ms=max(_ms(mb), a + 100), text=body))
    cues.sort(key=lambda c: c["start_ms"])
    return cues


def xep_timeline(clips: list[np.ndarray], cues: list[dict], sr: int = SR) -> tuple[np.ndarray, int, float]:
    """Đặt mỗi đoạn vào đúng mốc bắt đầu của cue; đoạn đọc tràn sang cue sau thì ĐẨY cue
    sau lùi lại (không đè, không co giãn giọng). Trả (track int16, số cue bị đẩy, lệch
    tối đa giây)."""
    starts: list[int] = []
    day, lech_max = 0, 0.0
    cursor = 0
    for c, w in zip(cues, clips):
        muon = int(c["start_ms"] * sr / 1000)
        at = max(muon, cursor)
        if at > muon:
            day += 1
            lech_max = max(lech_max, (at - muon) / sr)
        starts.append(at)
        cursor = at + len(w)
    total = max((s + len(w) for s, w in zip(starts, clips)), default=0)
    out = np.zeros(total + sr // 2, dtype=np.int32)
    for s, w in zip(starts, clips):
        out[s:s + len(w)] += np.asarray(w, dtype=np.int32)
    return np.clip(out, -32768, 32767).astype(np.int16), day, round(lech_max, 2)


def srt_sang_audio(url: str, srt_path: Path | str, voice: Optional[str], giu_moc: bool = True,
                   temperature: float = 0.8, nghi_s: float = 0.5,
                   on_progress: Optional[Callable[[int, int, str], None]] = None) -> tuple[np.ndarray, dict]:
    """Đọc từng cue của file .srt bằng một giọng; giu_moc=True → xếp đúng mốc thời gian
    (tràn thì đẩy cue sau), False → đọc nối tiếp cách `nghi_s`. Trả (audio int16, tóm tắt)."""
    cues = doc_srt(Path(srt_path).read_text(encoding="utf-8", errors="replace"))
    if not cues:
        raise ValueError("file SRT không có cue nào đọc được")
    clips, infos = [], []
    for i, c in enumerate(cues, 1):
        if on_progress:
            on_progress(i, len(cues), c["text"])
        a, info = doc(url, c["text"], voice, temperature=temperature)
        clips.append(a)
        infos.append(info)
    if giu_moc:
        track, day, lech = xep_timeline(clips, cues)
    else:
        track, day, lech = noi_tiep(clips, nghi_s), 0, 0.0
    tom_tat = dict(so_cue=len(cues), day=day, lech_max_s=lech, giu_moc=giu_moc,
                   audio_s=round(len(track) / SR, 2), infos=infos)
    return track, tom_tat


# ── worker SDK — bài tạo giọng thật, chế độ 🗣 VieNeu ─────────────────────────
def chon_cong(bat_dau: int = CONG_WORKER, so: int = 20) -> int:
    """Cổng trống đầu tiên trong [bat_dau, bat_dau + so) — dò bằng bind (xem cong_trong)."""
    for c in range(bat_dau, bat_dau + so):
        if cong_trong(c):
            return c
    raise RuntimeError(f"không còn cổng trống trong {bat_dau}–{bat_dau + so - 1}")


def giai_ma_audio(s: str) -> np.ndarray:
    """base64 int16 mono (worker trả) → float32 [-1, 1]."""
    return np.frombuffer(base64.b64decode(s), dtype="<i2").astype(np.float32) / 32768.0


def _loi_worker(r: requests.Response) -> str:
    try:
        return str(r.json()["error"])
    except Exception:
        return (r.text or f"HTTP {r.status_code}").strip()[:300]


class KhongCoGpu(RuntimeError):
    """Worker VieNeu không dùng được GPU: bị ép --device cuda mà CUDA không có (bat), hoặc
    CUDA lỗi giữa chừng lúc đang đọc (doc_nhieu). amain_taogiong_gui đổi thành GpuLoi để cả
    lượt dừng và hàng đợi web tạm dừng — module này không import scripts/gpu_batbuoc để app
    Thử giọng dùng riêng được."""


class SdkWorker(TienTrinh):
    """`python voice/vieneu_worker.py --port N` trong .venv của kho. amain_taogiong_gui.run_tts
    chế độ "vieneu" dùng: bat() → doc()/doc_nhieu() từng đoạn → tat().

    Cách đọc (09/11/2026, xem đầu vieneu_worker.py): mặc định "mau" = worker đọc từng mẩu qua
    infer_stream — đúng đường API server của kho, đường duy nhất sống qua test phân định trên
    RTX 4060 (RTF ~0,66). "gop" = infer()/infer_batch() fused batch, RTF 0,075 nhưng làm card
    TDR sau vài giây; chỉ truyền cach="gop" để so sánh. Test: tests/test_vieneu_mode.py."""

    def __init__(self):
        super().__init__("VieNeu worker")
        self.sr = SR
        self.giong: list[str] = list(GIONG_DUNG_SAN)
        self.backend = "?"
        self.cach = "?"            # worker báo lại qua /health sau khi bật

    def bat(self, cong: Optional[int] = None, device: str = "auto",
            on_line: Optional[Callable[[str], None]] = None, timeout: float = 600.0,
            cach: str = "mau") -> dict:
        """Bật worker rồi ĐỢI /health (nạp model ~10 s; lần đầu còn tải model). Không lên →
        tắt + RuntimeError. Trả dict health (voices, backend, cach).

        device="cuda" = ÉP GPU (bài thật gọi kiểu này từ 05/11/2026): worker không dùng được
        CUDA thì thoát mã MA_KHONG_GPU → ném KhongCoGpu kèm lý do worker in ra, thay vì để SDK
        lặng lẽ chạy ONNX/CPU chậm gấp ~4 lần."""
        nhan = on_line or (lambda s: None)
        ly_do: list[str] = []          # dòng "❌ KHÔNG CÓ GPU: …" worker in trước khi thoát

        def on_line(s: str) -> None:
            if s.startswith(DAU_KHONG_GPU):
                ly_do.append(s[len(DAU_KHONG_GPU):].strip())
            nhan(s)

        if not WORKER_PY.exists():
            raise RuntimeError(f"thiếu {WORKER_PY.name} cạnh vieneu_client.py")
        cong = cong or chon_cong()
        # --parent-pid (09/11/2026): tiến trình này (GUI / runner bước / script) tắt vì bất cứ
        # lý do gì — đóng cửa sổ, taskkill cả cây, sập — thì worker tự thoát, model rời VRAM;
        # không còn worker mồ côi nằm giữ ~0,7 GB tới khi tắt máy.
        self._bat([str(VENV_PY), str(WORKER_PY), "--port", str(cong), "--device", device,
                   "--parent-pid", str(os.getpid()), "--cach", cach],
                  _env(), cong, on_line)
        h = self.cho_san_sang(timeout)
        if not h:
            ma = self.proc.poll() if self.proc is not None else None
            self.tat()
            if ma == MA_KHONG_GPU:
                han = time.monotonic() + 1.0     # luồng đọc log có thể tới chậm một nhịp
                while not ly_do and time.monotonic() < han:
                    time.sleep(0.05)
                raise KhongCoGpu("VieNeu worker không dùng được GPU"
                                 + (f": {ly_do[-1]}" if ly_do else " (xem dòng [vieneu] ❌ ở nhật ký)"))
            raise RuntimeError("VieNeu worker không lên (xem nhật ký [vieneu]) — thử lại hoặc chuyển về Clone")
        self.sr = int(h.get("sr") or SR)
        self.giong = list(h.get("voices") or GIONG_DUNG_SAN)
        self.backend = str(h.get("backend") or "?")
        self.cach = str(h.get("cach") or cach)
        return h

    def health(self, timeout: float = 2.0) -> Optional[dict]:
        try:
            r = requests.get(self.url + "/health", timeout=timeout)
            return r.json() if r.status_code == 200 else None
        except (requests.RequestException, ValueError):
            return None

    def cho_san_sang(self, timeout: float = 600.0, moi: float = 0.5) -> Optional[dict]:
        han = time.monotonic() + timeout
        while time.monotonic() < han:
            if self.proc is not None and not self.dang_chay:
                return None
            h = self.health()
            if h:
                return h
            time.sleep(moi)
        return None

    def doc_nhieu(self, texts: list[str], voice: str, temperature: float = 0.4, top_k: int = 50,
                  timeout: float = 900.0) -> list[np.ndarray]:
        """POST /infer nhiều đoạn một lượt (worker gọi infer_batch) → list float32 48 kHz, cùng thứ tự."""
        if self.proc is not None and not self.dang_chay:
            raise RuntimeError("VieNeu worker đã tắt / chết giữa chừng")
        r = requests.post(self.url + "/infer",
                          json=dict(texts=list(texts), voice=voice, temperature=float(temperature),
                                    top_k=int(top_k)),
                          timeout=(10, timeout))
        if r.status_code >= 400:
            loi = _loi_worker(r)
            if r.status_code >= 500 and "cuda" in loi.lower():
                # CUDA lỗi GIỮA CHỪNG (driver treo, hết VRAM): đoạn sau cũng sẽ lỗi y hệt.
                raise KhongCoGpu(f"VieNeu worker lỗi GPU giữa chừng ({r.status_code}): {loi}")
            raise RuntimeError(f"VieNeu worker trả {r.status_code}: {loi}")
        d = r.json()
        self.sr = int(d.get("sr") or SR)
        return [giai_ma_audio(s) for s in d["audios"]]

    def doc(self, text: str, voice: str, **kw) -> np.ndarray:
        """Một đoạn → float32 48 kHz (đường _generate_chunk của run_tts)."""
        return self.doc_nhieu([text], voice, **kw)[0]

    def tat(self) -> None:
        if self.dang_chay:
            try:
                requests.post(self.url + "/shutdown", timeout=2)
            except requests.RequestException:
                pass
        super().tat()
