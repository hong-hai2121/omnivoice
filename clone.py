"""
Voice cloning — hỗ trợ text dài, tự động lưu tiến trình.
Chỉnh phần CẤU HÌNH rồi chạy: python clone.py
"""

import re
import logging
import numpy as np
import torch
import soundfile as sf
from pathlib import Path
from omnivoice.models.omnivoice import OmniVoice
from omnivoice.utils.common import get_best_device

# ── CẤU HÌNH ────────────────────────────────────────────────────────────────
REF_AUDIO  = "D:\\Python\\omnivoice\\OmniVoice\\voice\\ngochuyen.MP3"
TEXT_FILE  = "D:\\Python\\omnivoice\\OmniVoice\\voice\\input.txt"
OUTPUT     = str(Path.home() / "Downloads" / "output.wav")

# Số ký tự tối đa mỗi đoạn (tách tại dấu câu gần nhất)
CHUNK_SIZE = 300
# ────────────────────────────────────────────────────────────────────────────

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)

SPLIT_CHARS = re.compile(r'(?<=[.!?。！？\n])\s*')

_NUM_VI = {
    1: "phần một", 2: "phần hai", 3: "phần ba", 4: "phần bốn",
    5: "phần năm", 6: "phần sáu", 7: "phần bảy", 8: "phần tám",
    9: "phần chín", 10: "phần mười", 11: "phần mười một",
    12: "phần mười hai", 13: "phần mười ba", 14: "phần mười bốn",
    15: "phần mười lăm", 16: "phần mười sáu", 17: "phần mười bảy",
    18: "phần mười tám", 19: "phần mười chín", 20: "phần hai mươi",
}


def preprocess_text(text: str) -> str:
    """Xử lý văn bản trước TTS:
    1. Gộp các dòng vụn trong cùng đoạn thành một dòng liền.
    2. Xóa URL, dòng nguồn/tác giả, ký hiệu thừa.
    3. Đổi số mục đứng riêng (1, 2, 3…) thành "Phần một", "Phần hai"…
    4. Cảnh báo nếu còn ký tự tiếng Trung sót lại.
    """
    blocks = re.split(r'\n{2,}', text)
    result = []

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        # Xóa URL
        block = re.sub(r'https?://\S+', '', block)
        # Xóa ghi chú nguồn/tác giả dạng (Nguồn: ...) hoặc [Tác giả: ...]
        block = re.sub(r'[\(\[](nguồn|source|tác giả|author)[^\)\]]*[\)\]]', '', block, flags=re.IGNORECASE)
        # Xóa ký hiệu markdown đầu dòng: *, -, #, >
        block = re.sub(r'^[ \t]*[\*\-\#\>]+[ \t]*', '', block, flags=re.MULTILINE)

        block = block.strip()
        if not block:
            continue

        # Số mục đứng riêng → "Phần …"
        if re.fullmatch(r'\d+', block):
            n = int(block)
            result.append(_NUM_VI.get(n, f"phần {n}"))
            continue

        # Gộp các dòng trong block thành một dòng
        lines = [l.strip() for l in block.splitlines() if l.strip()]
        merged = re.sub(r' {2,}', ' ', ' '.join(lines))
        if merged:
            result.append(merged)

    processed = '\n'.join(result)

    # Cảnh báo ký tự tiếng Trung còn sót
    chinese = re.findall(r'[一-鿿㐀-䶿豈-﫿]', processed)
    if chinese:
        logging.warning(f"Còn {len(chinese)} ký tự tiếng Trung chưa xử lý: {''.join(sorted(set(chinese)))}")

    return processed


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
raw_text  = Path(TEXT_FILE).read_text(encoding="utf-8").strip()
full_text = preprocess_text(raw_text).lower()
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
