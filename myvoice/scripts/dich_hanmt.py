# -*- coding: utf-8 -*-
"""
dich_hanmt.py — Dịch NGHĨA sang tiếng Việt bằng model opus-mt offline.

Mặc định là zh→vi (opus-mt-zh-vi): dùng cho các đoạn chữ Hán DÀI mà Gemini bỏ
sót nguyên câu/cụm — MT cho nghĩa thật (山鸡→gà rừng). Chữ lẻ/tên/thành ngữ thì
để dich_hanviet phiên âm (MT hay bịa với input ngắn). Xem logic ghép ở
dich_hanviet.translate_han().

Còn nhận model KHÁC qua tham số model_id — myvideo dịch phụ đề tiếng Anh dùng
MODEL_EN_VI (opus-mt-en-vi). Mỗi model nạp/xả riêng, không đụng nhau.

- Model cache tại scripts/mt_cache → nạp OFFLINE (local_files_only); lần đầu chưa
  có cache thì tự tải (~300MB mỗi model) rồi lưu lại.
- Nạp LƯỜI: chỉ tải model khi thật sự có đoạn cần dịch.
- Xả TAY: gọi giai_phong() khi dịch xong cả bài (dich_hanviet.translate_han tự
  gọi; không tham số = xả HẾT mọi model). Module này bị import THẲNG vào tiến
  trình GUI, mà GUI thì sống suốt buổi → không xả là ~0.4 GB VRAM nằm lì tới khi
  tắt app, đúng lúc bước sau cần chỗ cho OmniVoice. Xả rồi vẫn dịch lại được:
  _ensure() tự nạp lần sau.
- Mọi lỗi (thiếu model/thiếu mạng lần đầu…) → trả None để bên gọi tự fallback.
"""

from pathlib import Path

MODEL_ID = "Helsinki-NLP/opus-mt-zh-vi"       # mặc định: tiếng Trung → Việt
MODEL_EN_VI = "Helsinki-NLP/opus-mt-en-vi"    # tiếng Anh → Việt
CACHE_DIR = str(Path(__file__).resolve().parent / "mt_cache")

# model_id → {"tok": …, "model": …, "dev": …, "state": unknown|ok|failed}
_kho: dict = {}


def _o(model_id: str) -> dict:
    return _kho.setdefault(model_id, {"tok": None, "model": None, "dev": None,
                                      "state": "unknown"})


def _ensure(model_id: str = MODEL_ID) -> bool:
    """Nạp model (lười). Trả True nếu sẵn sàng, False nếu không dùng được."""
    o = _o(model_id)
    if o["state"] == "ok":
        return True
    if o["state"] == "failed":
        return False
    try:
        import torch
        from transformers import MarianMTModel, MarianTokenizer
        # Ưu tiên OFFLINE (đã cache); nếu chưa cache thì cho tải về 1 lần.
        try:
            tok = MarianTokenizer.from_pretrained(model_id, cache_dir=CACHE_DIR,
                                                  local_files_only=True)
            model = MarianMTModel.from_pretrained(model_id, cache_dir=CACHE_DIR,
                                                  local_files_only=True)
        except Exception:
            print(f"⬇ Lần đầu dùng {model_id} — đang tải model (~300MB) về "
                  f"{CACHE_DIR}...", flush=True)
            tok = MarianTokenizer.from_pretrained(model_id, cache_dir=CACHE_DIR)
            model = MarianMTModel.from_pretrained(model_id, cache_dir=CACHE_DIR)
        o["dev"] = "cuda" if torch.cuda.is_available() else "cpu"
        o["tok"], o["model"] = tok, model.to(o["dev"]).eval()
        o["state"] = "ok"
        return True
    except Exception:
        o["state"] = "failed"
        return False


def available(model_id: str = MODEL_ID) -> bool:
    return _ensure(model_id)


def giai_phong(model_id: str = None):
    """Nhả model khỏi VRAM/RAM (không tham số = nhả HẾT). Gọi lại nhiều lần vô
    hại; nạp lại được ngay sau đó.

    Thứ tự bắt buộc: bỏ HẾT tham chiếu (model/tok) rồi mới gc.collect() +
    empty_cache(), không thì allocator của torch vẫn giữ nguyên khối đó.
    Đặt state về "unknown" chứ không phải "failed" — lần sau còn nạp lại.
    """
    ids = [model_id] if model_id else list(_kho)
    da_tha = False
    for mid in ids:
        o = _kho.get(mid)
        if not o or (o["model"] is None and o["tok"] is None):
            continue
        o["tok"] = o["model"] = o["dev"] = None
        o["state"] = "unknown"
        da_tha = True
    if not da_tha:
        return
    import gc
    gc.collect()
    try:
        import torch
        torch.cuda.empty_cache()
    except Exception:
        pass


def translate(texts, model_id: str = MODEL_ID):
    """Dịch danh sách câu → tiếng Việt (nghĩa) bằng model chỉ định.

    Trả về list[str] cùng độ dài, hoặc None nếu model không dùng được.
    """
    if not texts or not _ensure(model_id):
        return None
    o = _o(model_id)
    try:
        import torch
        batch = o["tok"](list(texts), return_tensors="pt", padding=True,
                         truncation=True, max_length=512).to(o["dev"])
        with torch.no_grad():
            gen = o["model"].generate(**batch, num_beams=4, max_length=512)
        return [o["tok"].decode(g, skip_special_tokens=True).strip() for g in gen]
    except Exception:
        return None


def main(argv=None):
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    args = argv if argv is not None else sys.argv[1:]
    model_id = MODEL_ID
    if args and args[0] in ("--en", "--en-vi"):
        model_id, args = MODEL_EN_VI, args[1:]
    if not args:
        print(f"Model: {model_id}\nCache: {CACHE_DIR}\nSẵn sàng: {available(model_id)}")
        print('Dùng: python dich_hanmt.py "我是山鸡"'
              '   ·   python dich_hanmt.py --en "I am a wild chicken"')
        return
    out = translate([" ".join(args)], model_id)
    print(out[0] if out else "(model không dùng được)")


if __name__ == "__main__":
    main()
