"""
Giao diện desktop cho Voice Cloning — chạy: python clone_gui.py
"""

import sys, os
_VENV_PYTHON = os.path.join(os.path.dirname(__file__), "venv", "Scripts", "python.exe")
if os.path.exists(_VENV_PYTHON) and os.path.abspath(sys.executable) != os.path.abspath(_VENV_PYTHON):
    import subprocess
    subprocess.run([_VENV_PYTHON] + sys.argv)
    sys.exit()

import re
import threading
import logging
import queue
import numpy as np
import soundfile as sf
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
from pathlib import Path

try:
    import sv_ttk
    _HAS_SV_TTK = True
except ImportError:
    _HAS_SV_TTK = False


BASE_DIR   = Path(__file__).parent
VOICE_DIR  = BASE_DIR / "voice"
SCRIPT_DIR = BASE_DIR / "kịch_bản"
AUDIO_EXTS = {".mp3", ".wav", ".MP3", ".WAV", ".flac", ".FLAC"}

SCRIPT_DIR.mkdir(exist_ok=True)

# Tự chuyển input.txt cũ từ voice/ sang kịch_bản/ nếu chưa có
_old_input = VOICE_DIR / "input.txt"
_new_input = SCRIPT_DIR / "input.txt"
if not _new_input.exists():
    if _old_input.exists():
        _new_input.write_bytes(_old_input.read_bytes())
    else:
        _new_input.write_text("", encoding="utf-8")


def list_voice_files():
    if not VOICE_DIR.exists():
        return []
    return sorted(f.name for f in VOICE_DIR.iterdir() if f.suffix in AUDIO_EXTS)


# ── QUEUE ĐỂ TRUYỀN LOG TỪ THREAD VỀ GUI ───────────────────────────────────
log_queue = queue.Queue()


class QueueHandler(logging.Handler):
    def emit(self, record):
        log_queue.put(self.format(record))


# ── LOGIC CLONE ──────────────────────────────────────────────────────────────
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


def run_tts(mode, voice_param, text_file, output, chunk_size, progress_var, status_var, btn_run, btn_pause, pause_event):
    import torch
    from omnivoice.models.omnivoice import OmniVoice
    from omnivoice.utils.common import get_best_device

    try:
        full_text = Path(text_file).read_text(encoding="utf-8").strip()
        chunks = split_chunks(full_text.lower(), chunk_size)
        total = len(chunks)

        preview_path = Path(text_file).parent / (Path(text_file).stem + "_preview.txt")
        preview_path.write_text("\n\n".join(chunks), encoding="utf-8")
        logging.info(f"File preview đã lưu → {preview_path}")

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
            # Chờ nếu đang tạm dừng
            if not pause_event.is_set():
                status_var.set(f"⏸  Đã tạm dừng (đoạn {i+1}/{total})")
                logging.info("Tạm dừng...")
                pause_event.wait()
                status_var.set(f"Đoạn {i+1}/{total}...")
                logging.info("Tiếp tục.")

            tmp_file = tmp_dir / f"{i:04d}.wav"
            pct = int((i / total) * 100)
            progress_var.set(pct)
            status_var.set(f"Đoạn {i+1}/{total}...")

            if tmp_file.exists() and tmp_file.stat().st_size > 4096:
                logging.info(f"[{i+1}/{total}] bỏ qua (đã có)")
                continue
            elif tmp_file.exists():
                logging.warning(f"[{i+1}/{total}] file cũ bị lỗi/cụt → generate lại")
                tmp_file.unlink()

            logging.info(f"[{i+1}/{total}] {chunk[:60]!r}")
            if mode == "clone":
                result = model.generate(text=chunk, ref_audio=voice_param)
            elif mode == "design":
                result = model.generate(text=chunk, instruct=voice_param)
            else:
                result = model.generate(text=chunk)
            sf.write(str(tmp_file), result[0], sr)

        status_var.set("Đang ghép file...")
        logging.info("Ghép tất cả đoạn...")
        parts = [
            sf.read(str(tmp_dir / f"{i:04d}.wav"), dtype="float32")[0]
            for i in range(total)
        ]

        # Crossfade ngắn giữa các chunk để tránh click/vấp tại ranh giới
        fade = min(256, min(len(p) for p in parts) // 2)
        fade_in  = np.linspace(0, 1, fade, dtype="float32")
        fade_out = np.linspace(1, 0, fade, dtype="float32")
        merged = parts[0].copy()
        merged[-fade:] *= fade_out
        for p in parts[1:]:
            p = p.copy()
            p[:fade] *= fade_in
            merged[-fade:] += p[:fade]
            merged = np.concatenate([merged, p[fade:]])

        sf.write(output, merged, sr)
        progress_var.set(100)
        status_var.set(f"Xong!  →  {output}")
        logging.info(f"Đã lưu → {output}")

    except Exception as e:
        logging.error(f"Lỗi: {e}")
        status_var.set(f"Lỗi: {e}")
    finally:
        pause_event.set()
        btn_run.config(state="normal")
        btn_pause.config(state="disabled", text="⏸  Tạm dừng")


# ── GIAO DIỆN ────────────────────────────────────────────────────────────────
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("OmniVoice TTS")
        self.resizable(True, True)
        if _HAS_SV_TTK:
            sv_ttk.set_theme("dark")
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._setup_logging()
        self._build_ui()
        self._poll_log()
        self.update_idletasks()
        self.minsize(self.winfo_width(), self.winfo_height())

    def _setup_logging(self):
        handler = QueueHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%H:%M:%S"))
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(logging.INFO)

    def _build_ui(self):
        root = ttk.Frame(self, padding=16)
        root.grid(sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        root.columnconfigure(0, weight=1)

        # ── Header ──
        hdr = ttk.Frame(root)
        hdr.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        ttk.Label(hdr, text="OmniVoice TTS",
                  font=("Segoe UI", 18, "bold")).pack(side="left")
        ttk.Label(hdr, text="  Đọc văn bản · Nhân giọng · Thiết kế giọng",
                  font=("Segoe UI", 10)).pack(side="left", pady=4)

        # ── Section: Chế độ ──
        sec_mode = ttk.LabelFrame(root, text="  Chế độ  ", padding=10)
        sec_mode.grid(row=1, column=0, sticky="ew", pady=6)
        sec_mode.columnconfigure(0, weight=1)

        self.var_mode = tk.StringVar(value="clone")
        mode_row = ttk.Frame(sec_mode)
        mode_row.grid(row=0, column=0, sticky="w")
        for label, val, desc in [
            ("🎙  Clone giọng",   "clone",   "Nhái theo giọng mẫu"),
            ("🎨  Thiết kế giọng","design",  "Mô tả đặc điểm giọng"),
            ("🔊  Giọng mặc định","default", "Model tự chọn"),
        ]:
            f = ttk.Frame(mode_row)
            f.pack(side="left", padx=6)
            ttk.Radiobutton(f, text=label, variable=self.var_mode,
                            value=val, command=self._on_mode_change).pack(anchor="w")
            ttk.Label(f, text=desc, font=("Segoe UI", 8)).pack(anchor="w", padx=20)

        # Khu vực động
        self.voice_frame = ttk.Frame(sec_mode)
        self.voice_frame.grid(row=1, column=0, sticky="ew", pady=(10, 2))

        # Clone
        self.frm_clone = ttk.Frame(self.voice_frame)
        ttk.Label(self.frm_clone, text="Giọng mẫu:", width=14, anchor="e").pack(side="left", padx=(0, 6))
        voices = list_voice_files()
        self.var_ref = tk.StringVar(value=voices[0] if voices else "")
        self.cb_ref = ttk.Combobox(self.frm_clone, textvariable=self.var_ref,
                                   values=voices, width=42, state="readonly")
        self.cb_ref.pack(side="left")
        ttk.Button(self.frm_clone, text="↻", width=3,
                   command=self._refresh_voices).pack(side="left", padx=(6, 0))

        # Design
        self.frm_design = ttk.Frame(self.voice_frame)

        # Chọn ngôn ngữ instruct
        lang_row = ttk.Frame(self.frm_design)
        lang_row.pack(anchor="w", pady=(0, 6))
        ttk.Label(lang_row, text="Ngôn ngữ:").pack(side="left", padx=(0, 8))
        self.var_lang = tk.StringVar(value="en")
        ttk.Radiobutton(lang_row, text="English", variable=self.var_lang,
                        value="en", command=self._on_lang_change).pack(side="left", padx=4)
        ttk.Radiobutton(lang_row, text="中文", variable=self.var_lang,
                        value="zh", command=self._on_lang_change).pack(side="left", padx=4)

        # Dropdowns thuộc tính — được xây lại khi đổi ngôn ngữ
        self.design_attr_frame = ttk.Frame(self.frm_design)
        self.design_attr_frame.pack(anchor="w", fill="x")

        # Instruct kết quả (có thể chỉnh tay)
        res_row = ttk.Frame(self.frm_design)
        res_row.pack(anchor="w", fill="x", pady=(8, 0))
        ttk.Label(res_row, text="Lệnh gửi model:").pack(side="left", padx=(0, 8))
        self.var_instruct = tk.StringVar(value="female, young adult")
        ttk.Entry(res_row, textvariable=self.var_instruct, width=46).pack(side="left", fill="x", expand=True)

        self._design_vars: list[tk.StringVar] = []
        self._design_sep = ", "
        self._build_design_dropdowns()

        # Default
        self.frm_default = ttk.Frame(self.voice_frame)
        ttk.Label(self.frm_default, text="Model tự động chọn giọng phù hợp với văn bản",
                  font=("Segoe UI", 9)).pack(side="left", padx=4)

        self._on_mode_change()

        # ── Section: Tệp ──
        sec_file = ttk.LabelFrame(root, text="  Tệp  ", padding=10)
        sec_file.grid(row=2, column=0, sticky="ew", pady=6)
        sec_file.columnconfigure(1, weight=1)

        for row, (lbl, attr, default, is_save) in enumerate([
            ("Văn bản (.txt):", "var_txt", str(SCRIPT_DIR / "input.txt"),  False),
            ("Kết quả (.wav):", "var_out", str(SCRIPT_DIR / "output.wav"), True),
        ]):
            ttk.Label(sec_file, text=lbl, width=16, anchor="e").grid(
                row=row, column=0, sticky="e", padx=(0, 8), pady=4)
            var = tk.StringVar(value=default)
            setattr(self, attr, var)
            ttk.Entry(sec_file, textvariable=var).grid(
                row=row, column=1, sticky="ew", pady=4)
            cmd = (lambda v=var: self._pick_save(v, [("WAV", "*.wav")])) if is_save \
                else (lambda v=var: self._pick_file(v, [("Text", "*.txt")]))
            ttk.Button(sec_file, text="Chọn…", width=7, command=cmd).grid(
                row=row, column=2, padx=(8, 0), pady=4)

        # ── Section: Cài đặt ──
        sec_opt = ttk.LabelFrame(root, text="  Cài đặt  ", padding=10)
        sec_opt.grid(row=3, column=0, sticky="ew", pady=6)

        ttk.Label(sec_opt, text="Độ dài mỗi đoạn (ký tự):").pack(side="left", padx=(0, 10))
        self.var_chunk = tk.IntVar(value=300)
        ttk.Spinbox(sec_opt, from_=100, to=1000, increment=50,
                    textvariable=self.var_chunk, width=7).pack(side="left")
        ttk.Label(sec_opt, text="  (ảnh hưởng tới RAM GPU — nhỏ hơn = nhẹ hơn)",
                  font=("Segoe UI", 8)).pack(side="left", padx=8)

        # ── Hành động ──
        act = ttk.Frame(root)
        act.grid(row=4, column=0, sticky="ew", pady=(12, 6))
        self.btn_run = ttk.Button(act, text="▶   Chạy", command=self._start, width=14)
        self.btn_run.pack(side="left", padx=(0, 8))
        self.btn_pause = ttk.Button(act, text="⏸  Tạm dừng", command=self._toggle_pause,
                                    width=14, state="disabled")
        self.btn_pause.pack(side="left", padx=(0, 8))
        ttk.Button(act, text="🗑  Xóa chunks cũ", command=self._clear_chunks).pack(side="left")

        # ── Tiến trình ──
        prog_frame = ttk.Frame(root)
        prog_frame.grid(row=5, column=0, sticky="ew", pady=(0, 4))
        prog_frame.columnconfigure(0, weight=1)
        self.progress = tk.IntVar(value=0)
        self.progress_bar = ttk.Progressbar(prog_frame, variable=self.progress,
                                            maximum=100, mode="determinate")
        self.progress_bar.grid(row=0, column=0, sticky="ew")
        self.status = tk.StringVar(value="Sẵn sàng.")
        ttk.Label(prog_frame, textvariable=self.status,
                  font=("Segoe UI", 9)).grid(row=1, column=0, sticky="w", pady=(2, 0))

        # ── Log ──
        log_frame = ttk.LabelFrame(root, text="  Log  ", padding=(8, 6))
        log_frame.grid(row=6, column=0, sticky="nsew", pady=(6, 0))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        root.rowconfigure(6, weight=1)
        self.log_box = scrolledtext.ScrolledText(log_frame, width=72, height=12,
                                                  state="disabled",
                                                  font=("Consolas", 9),
                                                  relief="flat", borderwidth=0)
        self.log_box.grid(row=0, column=0, sticky="nsew")

    def _build_design_dropdowns(self):
        for w in self.design_attr_frame.winfo_children():
            w.destroy()
        self._design_vars.clear()
        self._design_maps: list[dict] = []

        NONE = "—"

        if self.var_lang.get() == "en":
            self._design_sep = ", "
            # (label_vi, [(hiển_thị_vi, giá_trị_model), ...])
            groups = [
                [
                    ("Giới tính", [(NONE,""), ("Nữ","female"), ("Nam","male")]),
                    ("Tuổi",      [(NONE,""), ("Trẻ em","child"), ("Thiếu niên","teenager"),
                                   ("Thanh niên","young adult"), ("Trung niên","middle-aged"),
                                   ("Cao tuổi","elderly")]),
                    ("Âm điệu",  [(NONE,""), ("Rất thấp","very low pitch"), ("Thấp","low pitch"),
                                   ("Vừa","moderate pitch"), ("Cao","high pitch"),
                                   ("Rất cao","very high pitch")]),
                    ("Đặc biệt", [(NONE,""), ("Thì thầm","whisper")]),
                ],
                [
                    ("Giọng vùng", [(NONE,""), ("Mỹ","american accent"), ("Úc","australian accent"),
                                    ("Anh","british accent"), ("Canada","canadian accent"),
                                    ("Trung Quốc","chinese accent"), ("Ấn Độ","indian accent"),
                                    ("Nhật Bản","japanese accent"), ("Hàn Quốc","korean accent"),
                                    ("Bồ Đào Nha","portuguese accent"), ("Nga","russian accent")]),
                ],
            ]
        else:
            self._design_sep = "，"
            groups = [
                [
                    ("Giới tính", [(NONE,""), ("Nữ","女"), ("Nam","男")]),
                    ("Tuổi",      [(NONE,""), ("Trẻ em","儿童"), ("Thiếu niên","少年"),
                                   ("Thanh niên","青年"), ("Trung niên","中年"), ("Cao tuổi","老年")]),
                    ("Âm điệu",  [(NONE,""), ("Rất thấp","极低音调"), ("Thấp","低音调"),
                                   ("Vừa","中音调"), ("Cao","高音调"), ("Rất cao","极高音调")]),
                    ("Đặc biệt", [(NONE,""), ("Thì thầm","耳语")]),
                ],
                [
                    ("Phương ngữ", [(NONE,""), ("Đông Bắc","东北话"), ("Vân Nam","云南话"),
                                    ("Tứ Xuyên","四川话"), ("Ninh Hạ","宁夏话"), ("Cam Túc","甘肃话"),
                                    ("Quế Lâm","桂林话"), ("Hà Nam","河南话"), ("Tế Nam","济南话"),
                                    ("Thiểm Tây","陕西话"), ("Thạch Gia Trang","石家庄话"),
                                    ("Quý Châu","贵州话"), ("Thanh Đảo","青岛话")]),
                ],
            ]

        for group in groups:
            row_f = ttk.Frame(self.design_attr_frame)
            row_f.pack(anchor="w", pady=3)
            for label, options in group:
                displays = [d for d, _ in options]
                mapping  = {d: v for d, v in options}
                cell = ttk.Frame(row_f)
                cell.pack(side="left", padx=(0, 14))
                ttk.Label(cell, text=label, font=("Segoe UI", 8)).pack(anchor="w")
                var = tk.StringVar(value=NONE)
                self._design_vars.append(var)
                self._design_maps.append(mapping)
                ttk.Combobox(cell, textvariable=var, values=displays,
                             width=17, state="readonly").pack()
                var.trace_add("write", lambda *_: self._update_instruct())

    def _on_lang_change(self):
        self._build_design_dropdowns()
        self._update_instruct()

    def _update_instruct(self):
        parts = []
        for var, mapping in zip(self._design_vars, self._design_maps):
            actual = mapping.get(var.get(), "")
            if actual:
                parts.append(actual)
        self.var_instruct.set(self._design_sep.join(parts))

    def _on_mode_change(self):
        for frm in (self.frm_clone, self.frm_design, self.frm_default):
            frm.pack_forget()
        {"clone":   self.frm_clone,
         "design":  self.frm_design,
         "default": self.frm_default}[self.var_mode.get()].pack(anchor="w")

    def _refresh_voices(self):
        voices = list_voice_files()
        self.cb_ref["values"] = voices
        if voices and self.var_ref.get() not in voices:
            self.var_ref.set(voices[0])
        logging.info(f"Tìm thấy {len(voices)} file giọng trong {VOICE_DIR}")

    def _clear_chunks(self):
        output_path = Path(self.var_out.get())
        tmp_dir = output_path.parent / (output_path.stem + "_chunks")
        if not tmp_dir.exists():
            messagebox.showinfo("Thông báo", "Không tìm thấy thư mục chunks.")
            return
        files = list(tmp_dir.glob("*.wav"))
        if not files:
            messagebox.showinfo("Thông báo", "Thư mục chunks đã trống.")
            return
        if messagebox.askyesno("Xác nhận",
                               f"Xóa {len(files)} file chunks trong:\n{tmp_dir}\n\n"
                               "Tiến trình sẽ bắt đầu lại từ đầu!"):
            for f in files:
                f.unlink()
            logging.info(f"Đã xóa {len(files)} chunks trong {tmp_dir}")
            self.status.set(f"Đã xóa {len(files)} chunks.")

    def _pick_file(self, var, filetypes):
        path = filedialog.askopenfilename(filetypes=filetypes)
        if path:
            var.set(path)

    def _pick_save(self, var, filetypes):
        path = filedialog.asksaveasfilename(defaultextension=".wav", filetypes=filetypes)
        if path:
            var.set(path)

    def _start(self):
        mode = self.var_mode.get()
        if mode == "clone":
            voice_name = self.var_ref.get()
            if not voice_name:
                messagebox.showwarning("Thiếu giọng mẫu",
                                       f"Không tìm thấy file audio trong:\n{VOICE_DIR}")
                return
            voice_param = str(VOICE_DIR / voice_name)
        elif mode == "design":
            voice_param = self.var_instruct.get().strip()
            if not voice_param:
                messagebox.showwarning("Thiếu mô tả", "Vui lòng nhập mô tả giọng đọc.")
                return
        else:
            voice_param = None

        self._pause_event = threading.Event()
        self._pause_event.set()
        self.btn_run.config(state="disabled")
        self.btn_pause.config(state="normal", text="⏸  Tạm dừng")
        self.progress.set(0)
        self.status.set("Đang khởi động...")
        threading.Thread(
            target=run_tts,
            args=(mode, voice_param, self.var_txt.get(), self.var_out.get(),
                  self.var_chunk.get(), self.progress, self.status,
                  self.btn_run, self.btn_pause, self._pause_event),
            daemon=True,
        ).start()

    def _toggle_pause(self):
        if self._pause_event.is_set():
            self._pause_event.clear()
            self.btn_pause.config(text="▶  Tiếp tục")
        else:
            self._pause_event.set()
            self.btn_pause.config(text="⏸  Tạm dừng")

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
