"""
Voice cloning — hỗ trợ text dài, tự động lưu tiến trình.
Chỉnh phần CẤU HÌNH rồi chạy: python clone.py
"""

# ── CẤU HÌNH ────────────────────────────────────────────────────────────────
REF_AUDIO  = "D:\\Python\\omnivoice\\OmniVoice\\voice\\ngochuyen.MP3"
TEXT_FILE  = "D:\\Python\\omnivoice\\OmniVoice\\voice\\input.txt"
OUTPUT     = "D:\\Python\\omnivoice\\OmniVoice\\voice\\output.wav"

# Số ký tự tối đa mỗi đoạn (tách tại dấu câu gần nhất)
CHUNK_SIZE = 300
# ────────────────────────────────────────────────────────────────────────────

import re
import logging
import numpy as np
import torch
import soundfile as sf
from pathlib import Path
from omnivoice.models.omnivoice import OmniVoice
from omnivoice.utils.common import get_best_device

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)

SPLIT_CHARS = re.compile(r'(?<=[.!?。！？\n])\s*')


def split_chunks(text: str, max_len: int):
    """Tách text thành các đoạn <= max_len ký tự, ưu tiên tại dấu câu / xuống hàng."""
    parts = SPLIT_CHARS.split(text)
    chunks = []
    current = ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if len(current) + len(part) + 1 <= max_len:
            current = (current + " " + part).strip()
        else:
            if current:
                chunks.append(current)
            # Đoạn quá dài thì vẫn giữ nguyên, model tự xử lý chunking
            current = part
    if current:
        chunks.append(current)
    return chunks


# ── THƯ MỤC LƯU FILE TẠM ────────────────────────────────────────────────────
output_path = Path(OUTPUT)
tmp_dir = output_path.parent / (output_path.stem + "_chunks")
tmp_dir.mkdir(exist_ok=True)

# ── ĐỌC TEXT ────────────────────────────────────────────────────────────────
full_text = Path(TEXT_FILE).read_text(encoding="utf-8").strip().lower()
chunks = split_chunks(full_text, CHUNK_SIZE)
total = len(chunks)
logging.info(f"Tổng {total} đoạn, lưu file tạm tại: {tmp_dir}")

# ── TẢI MODEL ────────────────────────────────────────────────────────────────
device = get_best_device()
logging.info(f"Device: {device} — đang tải model...")
model = OmniVoice.from_pretrained(
    "k2-fsa/OmniVoice",
    device_map=device,
    dtype=torch.float16,
)
sr = model.sampling_rate

# ── SINH TỪNG ĐOẠN ───────────────────────────────────────────────────────────
for i, chunk in enumerate(chunks):
    tmp_file = tmp_dir / f"{i:04d}.wav"
    if tmp_file.exists():
        logging.info(f"  [{i+1}/{total}] bỏ qua (đã có) — {tmp_file.name}")
        continue

    logging.info(f"  [{i+1}/{total}] {chunk[:60]!r}")
    result = model.generate(text=chunk, ref_audio=REF_AUDIO)
    sf.write(str(tmp_file), result[0], sr)

# ── GHÉP LẠI ────────────────────────────────────────────────────────────────
logging.info("Ghép tất cả đoạn...")
parts = []
for i in range(total):
    audio, _ = sf.read(str(tmp_dir / f"{i:04d}.wav"), dtype="float32")
    parts.append(audio)

sf.write(OUTPUT, np.concatenate(parts), sr)
logging.info(f"Xong! Đã lưu → {OUTPUT}")
logging.info(f"(File tạm giữ lại tại {tmp_dir} — xóa thủ công nếu không cần)")
