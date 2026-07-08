# -*- coding: utf-8 -*-
"""
dich_hanmt.py — Dịch NGHĨA zh→vi bằng model offline (opus-mt-zh-vi).

Dùng cho các đoạn chữ Hán DÀI mà Gemini bỏ sót nguyên câu/cụm — MT cho nghĩa
thật (山鸡→gà rừng). Chữ lẻ/tên/thành ngữ thì để dich_hanviet phiên âm (MT hay
bịa với input ngắn). Xem logic ghép ở dich_hanviet.translate_han().

- Model cache tại scripts/mt_cache → nạp OFFLINE (local_files_only); lần đầu chưa
  có cache thì tự tải (~300MB) rồi lưu lại.
- Nạp LƯỜI: chỉ tải model khi thật sự có đoạn cần dịch.
- Mọi lỗi (thiếu model/thiếu mạng lần đầu…) → trả None để bên gọi tự fallback.
"""

from pathlib import Path

MODEL_ID = "Helsinki-NLP/opus-mt-zh-vi"
CACHE_DIR = str(Path(__file__).resolve().parent / "mt_cache")

_tok = None
_model = None
_dev = None
_state = "unknown"          # unknown | ok | failed


def _ensure() -> bool:
    """Nạp model (lười). Trả True nếu sẵn sàng, False nếu không dùng được."""
    global _tok, _model, _dev, _state
    if _state == "ok":
        return True
    if _state == "failed":
        return False
    try:
        import torch
        from transformers import MarianMTModel, MarianTokenizer
        # Ưu tiên OFFLINE (đã cache); nếu chưa cache thì cho tải về 1 lần.
        try:
            _tok = MarianTokenizer.from_pretrained(MODEL_ID, cache_dir=CACHE_DIR,
                                                   local_files_only=True)
            _model = MarianMTModel.from_pretrained(MODEL_ID, cache_dir=CACHE_DIR,
                                                   local_files_only=True)
        except Exception:
            _tok = MarianTokenizer.from_pretrained(MODEL_ID, cache_dir=CACHE_DIR)
            _model = MarianMTModel.from_pretrained(MODEL_ID, cache_dir=CACHE_DIR)
        _dev = "cuda" if torch.cuda.is_available() else "cpu"
        _model = _model.to(_dev).eval()
        _state = "ok"
        return True
    except Exception:
        _state = "failed"
        return False


def available() -> bool:
    return _ensure()


def translate(zh_list):
    """Dịch danh sách câu tiếng Trung → tiếng Việt (nghĩa).

    Trả về list[str] cùng độ dài, hoặc None nếu model không dùng được.
    """
    if not zh_list or not _ensure():
        return None
    try:
        import torch
        batch = _tok(list(zh_list), return_tensors="pt", padding=True,
                     truncation=True, max_length=512).to(_dev)
        with torch.no_grad():
            gen = _model.generate(**batch, num_beams=4, max_length=512)
        return [_tok.decode(g, skip_special_tokens=True).strip() for g in gen]
    except Exception:
        return None


def main(argv=None):
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print(f"Model: {MODEL_ID}\nCache: {CACHE_DIR}\nSẵn sàng: {available()}")
        print('Dùng: python dich_hanmt.py "我是山鸡"')
        return
    out = translate([" ".join(args)])
    print(out[0] if out else "(model không dùng được)")


if __name__ == "__main__":
    main()
