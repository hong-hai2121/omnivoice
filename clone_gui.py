"""
Giao diện desktop cho Voice Cloning — chạy: python clone_gui.py
"""

import re
import threading
import logging
import queue
import numpy as np
import soundfile as sf
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
from pathlib import Path


# ── QUEUE ĐỂ TRUYỀN LOG TỪ THREAD VỀ GUI ───────────────────────────────────
log_queue = queue.Queue()


class QueueHandler(logging.Handler):
    def emit(self, record):
        log_queue.put(self.format(record))


# ── LOGIC CLONE (giống clone.py) ─────────────────────────────────────────────
SPLIT_CHARS = re.compile(r'(?<=[.!?。！？\n])\s*')


def split_chunks(text: str, max_len: int):
    parts = SPLIT_CHARS.split(text)
    chunks, current = [], ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if len(current) + len(part) + 1 <= max_len:
            current = (current + " " + part).strip()
        else:
            if current:
                chunks.append(current)
            current = part
    if current:
        chunks.append(current)
    return chunks


def run_clone(ref_audio, text_file, output, chunk_size, progress_var, status_var, btn_run):
    import torch
    from omnivoice.models.omnivoice import OmniVoice
    from omnivoice.utils.common import get_best_device

    try:
        full_text = Path(text_file).read_text(encoding="utf-8").strip().lower()
        chunks = split_chunks(full_text, chunk_size)
        total = len(chunks)

        output_path = Path(output)
        tmp_dir = output_path.parent / (output_path.stem + "_chunks")
        tmp_dir.mkdir(exist_ok=True)

        logging.info(f"Tổng {total} đoạn — tải model...")
        status_var.set("Đang tải model...")

        device = get_best_device()
        model = OmniVoice.from_pretrained(
            "k2-fsa/OmniVoice", device_map=device, dtype=torch.float16
        )
        sr = model.sampling_rate

        for i, chunk in enumerate(chunks):
            tmp_file = tmp_dir / f"{i:04d}.wav"
            pct = int((i / total) * 100)
            progress_var.set(pct)
            status_var.set(f"Đoạn {i+1}/{total}...")

            if tmp_file.exists():
                logging.info(f"[{i+1}/{total}] bỏ qua (đã có)")
                continue

            logging.info(f"[{i+1}/{total}] {chunk[:60]!r}")
            result = model.generate(text=chunk, ref_audio=ref_audio)
            sf.write(str(tmp_file), result[0], sr)

        status_var.set("Đang ghép file...")
        logging.info("Ghép tất cả đoạn...")
        parts = [
            sf.read(str(tmp_dir / f"{i:04d}.wav"), dtype="float32")[0]
            for i in range(total)
        ]
        sf.write(output, np.concatenate(parts), sr)
        progress_var.set(100)
        status_var.set(f"Xong!  →  {output}")
        logging.info(f"Đã lưu → {output}")

    except Exception as e:
        logging.error(f"Lỗi: {e}")
        status_var.set(f"Lỗi: {e}")
    finally:
        btn_run.config(state="normal")


# ── GIAO DIỆN ────────────────────────────────────────────────────────────────
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("OmniVoice — Voice Cloning")
        self.resizable(False, False)
        self._setup_logging()
        self._build_ui()
        self._poll_log()

    def _setup_logging(self):
        handler = QueueHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%H:%M:%S"))
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(logging.INFO)

    def _build_ui(self):
        pad = dict(padx=10, pady=5)
        frame = ttk.Frame(self, padding=12)
        frame.grid()

        # ── File giọng mẫu ──
        ttk.Label(frame, text="Giọng mẫu (.mp3/.wav):").grid(row=0, column=0, sticky="w", **pad)
        self.var_ref = tk.StringVar(value="D:\\Python\\omnivoice\\OmniVoice\\voice\\ngochuyen.MP3")
        ttk.Entry(frame, textvariable=self.var_ref, width=52).grid(row=0, column=1, **pad)
        ttk.Button(frame, text="Chọn…", command=lambda: self._pick_file(
            self.var_ref, [("Audio", "*.mp3 *.wav *.MP3 *.WAV")]
        )).grid(row=0, column=2, **pad)

        # ── File text ──
        ttk.Label(frame, text="File văn bản (.txt):").grid(row=1, column=0, sticky="w", **pad)
        self.var_txt = tk.StringVar(value="D:\\Python\\omnivoice\\OmniVoice\\voice\\input.txt")
        ttk.Entry(frame, textvariable=self.var_txt, width=52).grid(row=1, column=1, **pad)
        ttk.Button(frame, text="Chọn…", command=lambda: self._pick_file(
            self.var_txt, [("Text", "*.txt")]
        )).grid(row=1, column=2, **pad)

        # ── File output ──
        ttk.Label(frame, text="Lưu kết quả (.wav):").grid(row=2, column=0, sticky="w", **pad)
        self.var_out = tk.StringVar(value="D:\\Python\\omnivoice\\OmniVoice\\voice\\output.wav")
        ttk.Entry(frame, textvariable=self.var_out, width=52).grid(row=2, column=1, **pad)
        ttk.Button(frame, text="Chọn…", command=lambda: self._pick_save(
            self.var_out, [("WAV", "*.wav")]
        )).grid(row=2, column=2, **pad)

        # ── Chunk size ──
        ttk.Label(frame, text="Độ dài mỗi đoạn (ký tự):").grid(row=3, column=0, sticky="w", **pad)
        self.var_chunk = tk.IntVar(value=300)
        ttk.Spinbox(frame, from_=100, to=1000, increment=50,
                    textvariable=self.var_chunk, width=8).grid(row=3, column=1, sticky="w", **pad)

        # ── Nút Run ──
        self.btn_run = ttk.Button(frame, text="▶  Chạy", command=self._start)
        self.btn_run.grid(row=4, column=0, columnspan=3, pady=10)

        # ── Thanh tiến trình ──
        self.progress = tk.IntVar(value=0)
        ttk.Progressbar(frame, variable=self.progress, maximum=100, length=480).grid(
            row=5, column=0, columnspan=3, **pad)

        # ── Status ──
        self.status = tk.StringVar(value="Sẵn sàng.")
        ttk.Label(frame, textvariable=self.status, foreground="gray").grid(
            row=6, column=0, columnspan=3, sticky="w", padx=10)

        # ── Log ──
        ttk.Label(frame, text="Log:").grid(row=7, column=0, sticky="w", padx=10)
        self.log_box = scrolledtext.ScrolledText(frame, width=68, height=14,
                                                  state="disabled", font=("Consolas", 9))
        self.log_box.grid(row=8, column=0, columnspan=3, padx=10, pady=5)

    def _pick_file(self, var, filetypes):
        path = filedialog.askopenfilename(filetypes=filetypes)
        if path:
            var.set(path)

    def _pick_save(self, var, filetypes):
        path = filedialog.asksaveasfilename(defaultextension=".wav", filetypes=filetypes)
        if path:
            var.set(path)

    def _start(self):
        self.btn_run.config(state="disabled")
        self.progress.set(0)
        self.status.set("Đang khởi động...")
        t = threading.Thread(
            target=run_clone,
            args=(
                self.var_ref.get(),
                self.var_txt.get(),
                self.var_out.get(),
                self.var_chunk.get(),
                self.progress,
                self.status,
                self.btn_run,
            ),
            daemon=True,
        )
        t.start()

    def _poll_log(self):
        while not log_queue.empty():
            msg = log_queue.get_nowait()
            self.log_box.config(state="normal")
            self.log_box.insert("end", msg + "\n")
            self.log_box.see("end")
            self.log_box.config(state="disabled")
        self.after(200, self._poll_log)


if __name__ == "__main__":
    App().mainloop()
