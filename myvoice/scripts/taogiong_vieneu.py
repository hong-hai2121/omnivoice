# -*- coding: utf-8 -*-
"""
taogiong_vieneu.py — VieNeu-TTS làm PHƯƠNG ÁN TẠO GIỌNG THỨ 2 (cạnh OmniVoice), chạy CPU
ngay TRONG tiến trình của phần mềm (11/11/2026, user: "tích hợp với code để chạy 1 phần mềm",
"mặc định chọn Ngọc Huyền").

Vì sao CPU, vì sao không server
    Bản 04–09/11/2026 chạy VieNeu trên GPU qua tiến trình con + server HTTP (vieneu_worker.py,
    đã gỡ; code ở nhánh luu-sau-02-11-vieneu): bản GPU của SDK cần transformers 4.57 còn venv
    OmniVoice là 5.x nên không import chung được. Đường GPU nhanh ("gop") làm card RTX 4060
    TDR sau vài giây, đường GPU sống được ("mau") RTF 0,66.
    Nhánh ONNX/CPU của SDK thì torch-free — không cần torch lẫn transformers — nên import
    thẳng được trong venv OmniVoice: không server, không tiến trình con, KHÔNG chạm card màn
    hình (GPU để cho Whisper kiểm mất chữ và NVENC dựng video ở các bước sau).
    Đo 11/11/2026 trên i5-13400F, giọng Ngọc Huyền: nạp ~9 s, RTF 0,43–0,45 (≈ 36 câu/phút,
    tập 600 câu ≈ 17 phút — ngang OmniVoice clone), RAM ~1,3 GB. Số luồng ONNX 6…16 không
    đổi tốc độ; 2–4 máy đọc song song chỉ nhanh hơn 20–25% (thêm 1,2 GB RAM mỗi máy) nên giữ
    MỘT máy đọc tuần tự.

Cần gì
    • Mã nguồn SDK: kho clone myvoice/voice/VieNeu-TTS — import từ src/ của kho, KHÔNG
      pip install gói vieneu (khỏi kéo gradio/librosa đè lên venv OmniVoice).
    • Hai gói nhỏ trong venv OmniVoice: sea-g2p, kaldi-native-fbank (cài 11/11/2026, bản
      0.9.1 / 1.22.3 như .venv của kho). onnxruntime, soxr, tokenizers, huggingface_hub có sẵn.
    • Model ONNX (~450 MB) + codec: tự tải về cache HuggingFace ở lần nạp đầu; các lần sau
      CHỈ dùng cache, không hỏi mạng (xem _tao_tts: nạp nhanh hơn, giọng không tự đổi theo repo).

Dùng (amain_taogiong_gui.nap_engine / do_engine / _generate_chunk gọi):
    may = MayDoc()                                 # nạp model lên CPU
    audio = may.doc("Xin chào.", "Ngọc Huyền")     # float32 mono, may.sr = 48000
    may.tat()                                      # trả RAM

Module này KHÔNG import gì nặng lúc import (GUI / web mở cho nhẹ): SDK chỉ nạp trong MayDoc().
Test: myvoice/tests/test_vieneu_cpu.py (máy đọc giả, không cần model).
"""
from __future__ import annotations

import gc
import importlib.util
import logging
import sys
import time
from pathlib import Path

import numpy as np

MODE = "vieneu"                                        # giá trị khoá "mode" trong cài đặt
KHO = Path(__file__).resolve().parent.parent / "voice" / "VieNeu-TTS"   # kho clone (gitignore)
SRC = KHO / "src"                                      # gói vieneu + vieneu_utils nằm ở đây
SR = 48_000                                            # v3 Turbo ra 48 kHz
GIONG_MAC_DINH = "Ngọc Huyền"                          # user chốt 04/11 và 11/11/2026
# 25 giọng dựng sẵn v3 Turbo (assets/voices_v3_turbo.json của kho): 10 giọng đầu là mục
# "featured" theo thứ tự kho xếp, còn lại theo file. Giữ TĨNH để GUI / web hiện danh sách mà
# không phải nạp model; test_vieneu_cpu.py so với file của kho (khi kho có trên đĩa).
GIONG_DUNG_SAN = (
    "Adam bựa", "Trúc Ly", "Thiện Minh", "Mai Anh", "Hải Đăng", "Thùy Dung", "Thiền Tâm Đức",
    "Ngọc Huyền", "Quang Sơn", "Ngọc Trân", "Minh Đức", "Phạm Tuyên", "Thái Sơn", "Xuân Vĩnh",
    "Thanh Bình", "Ngọc Linh", "Đoan Trang", "Thục Đoan", "Minh Triết", "Mỹ Duyên", "Quỳnh Anh",
    "Đức Trí", "Kim Thanh", "Adam", "Quốc Tuấn",
)
# module cần có trong venv → tên để pip install khi thiếu
GOI_CAN = {
    "onnxruntime": "onnxruntime",
    "sea_g2p": "sea-g2p==0.9.1",
    "kaldi_native_fbank": "kaldi-native-fbank==1.22.3",
    "soxr": "soxr",
    "tokenizers": "tokenizers",
    "huggingface_hub": "huggingface_hub",
}
# Tham số lấy mẫu của bài thật — giữ như bản 04–09/11/2026 (đọc truyện đều giọng hơn mặc
# định 0.8 / 25 của SDK).
NHIET_DO = 0.4
TOP_K = 50
CAU_LAM_NONG = "Xin chào."                             # câu đầu gánh phần khởi động session ONNX
LANG_KHI_RONG = 0.3                                    # giây lặng trả về khi câu không có gì để đọc


def giong_hop_le(ten) -> str:
    """Tên giọng dựng sẵn hợp lệ; trống / lạ → mặc định (Ngọc Huyền)."""
    ten = str(ten or "").strip()
    return ten if ten in GIONG_DUNG_SAN else GIONG_MAC_DINH


def trang_thai() -> dict:
    """Dùng được chưa — KHÔNG import SDK. Trả dict: co_kho, thieu (list tên pip), san_sang,
    mo_ta (một dòng cho nhãn / thông báo lỗi)."""
    co_kho = (SRC / "vieneu" / "__init__.py").is_file()
    thieu = [pip for mod, pip in GOI_CAN.items() if importlib.util.find_spec(mod) is None]
    if co_kho and not thieu:
        mo_ta = "chạy CPU trong phần mềm · 48 kHz · không dùng card màn hình"
    elif not co_kho:
        mo_ta = ("thiếu kho myvoice/voice/VieNeu-TTS — vào myvoice/voice rồi chạy: "
                 "git clone https://github.com/pnnbao97/VieNeu-TTS.git")
    else:
        mo_ta = "thiếu gói — chạy: venv/Scripts/python -m pip install " + " ".join(thieu)
    return dict(co_kho=co_kho, thieu=thieu, san_sang=co_kho and not thieu, mo_ta=mo_ta)


def _tao_tts(chi_cache: bool):
    """Vieneu(backend="onnx", device="cpu") — nói RÕ hai tham số để SDK không tự dò CUDA rồi
    nạp bản PyTorch.

    chi_cache=True: bật cờ offline của huggingface_hub trong lúc nạp → SDK chỉ lấy file đã có
    trong cache HuggingFace, không gửi yêu cầu nào lên mạng. Ba cái lợi (đo 11/11/2026):
      • nạp 7 s thay vì 11 s (khỏi ~20 lượt HEAD), mất mạng không phải chờ 45 s;
      • chạy đêm không phụ thuộc huggingface.co;
      • GIỌNG KHÔNG TỰ ĐỔI: tác giả đẩy model mới lên repo thì máy này vẫn đọc bằng bản đang
        có, không nửa bộ truyện giọng cũ nửa bộ giọng mới (muốn cập nhật: xoá thư mục
        models--pnnbao-ump--VieNeu-TTS-v3-Turbo trong ~/.cache/huggingface/hub rồi chạy lại).
    Cache thiếu file model → SDK ném lỗi, MayDoc gọi lại với chi_cache=False để tải về.
    Cờ là biến toàn cục của huggingface_hub: trong ~7 s đó luồng khác của CÙNG tiến trình cũng
    không tải được gì từ Hub — bước tạo giọng chạy trong tiến trình riêng của nó nên vô hại."""
    from vieneu import Vieneu                  # nạp ở đây, không phải lúc import module
    # Bản tải về: huggingface_hub hỏi máy chủ từng file (~20 dòng "HTTP Request: HEAD …" của
    # httpx ở mức INFO) — tắt tạm để Nhật ký không ngập.
    httpx_log = logging.getLogger("httpx")
    muc_cu = httpx_log.level
    httpx_log.setLevel(logging.WARNING)
    hf = None
    if chi_cache:
        from huggingface_hub import constants as hf
        co_cu = hf.HF_HUB_OFFLINE
        hf.HF_HUB_OFFLINE = True
    try:
        return Vieneu(backend="onnx", device="cpu")
    finally:
        if hf is not None:
            hf.HF_HUB_OFFLINE = co_cu
        httpx_log.setLevel(muc_cu)


class MayDoc:
    """Máy đọc VieNeu v3 Turbo, backend ONNX trên CPU. Một máy cho cả bài: nạp 1 lần (~7 s),
    doc() từng câu, tat() khi xong. Không an toàn đa luồng (bài thật gọi tuần tự)."""

    def __init__(self):
        tt = trang_thai()
        if not tt["san_sang"]:
            raise RuntimeError(f"VieNeu chưa dùng được: {tt['mo_ta']}")
        if str(SRC) not in sys.path:
            sys.path.append(str(SRC))          # cuối sys.path: không che gói nào của venv
        t = time.perf_counter()
        # Ưu tiên model ĐÃ CÓ trong cache (không hỏi mạng); cache thiếu file — lần nạp đầu
        # tiên trên máy — mới để SDK tải về.
        try:
            self.tts = _tao_tts(chi_cache=True)
            self.tu_cache = True
        except Exception:
            self.tts = _tao_tts(chi_cache=False)
            self.tu_cache = False
        self.sr = int(getattr(self.tts, "sample_rate", SR))
        self.backend = str(getattr(self.tts, "backend", "onnx"))
        self.tts.infer(CAU_LAM_NONG, voice=GIONG_MAC_DINH, apply_watermark=False, batch_size=1)
        self.t_nap = time.perf_counter() - t

    def doc(self, text: str, voice: str = GIONG_MAC_DINH) -> np.ndarray:
        """Một câu → audio float32 mono ở self.sr. Giọng lạ → Ngọc Huyền. Câu không có gì để
        đọc (toàn dấu) → một quãng lặng ngắn + cảnh báo, để cả bài không dừng vì một mẩu rỗng."""
        if self.tts is None:
            raise RuntimeError("máy đọc VieNeu đã tắt")
        text = " ".join(str(text or "").split())
        a = self.tts.infer(text, voice=giong_hop_le(voice), temperature=NHIET_DO, top_k=TOP_K,
                           apply_watermark=False, batch_size=1)
        a = np.asarray(a, dtype=np.float32).reshape(-1)
        if not len(a):
            logging.warning(f"⚠️ VieNeu không đọc được gì từ {text[:60]!r} → chèn {LANG_KHI_RONG} s lặng.")
            a = np.zeros(int(LANG_KHI_RONG * self.sr), dtype=np.float32)
        return a

    def tat(self) -> None:
        """Bỏ model khỏi RAM (gọi nhiều lần cũng được)."""
        tts, self.tts = self.tts, None
        if tts is not None:
            try:
                tts.close()
            except Exception:
                pass
        del tts
        gc.collect()
