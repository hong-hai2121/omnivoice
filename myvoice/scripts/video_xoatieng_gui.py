# -*- coding: utf-8 -*-
"""GUI xóa tiếng + cắt bớt đoạn cuối cho MỘT video.

Chạy từ thư mục gốc OmniVoice:
    venv\\Scripts\\python myvoice\\scripts\\video_xoatieng_gui.py

Hai chức năng:
  1) Xóa tiếng  – bỏ toàn bộ âm thanh khỏi video.
  2) Cắt cuối   – cắt bỏ N giây cuối video (số giây chỉnh được).

Đầu ra mặc định nằm trong myvoice/videongang (ngang) hoặc myvoice/videodoc (dọc).
Chỉ xóa tiếng và không cắt → sao chép luồng video (nhanh, không giảm chất lượng).
Có cắt cuối → mã hóa lại bằng libx264 để cắt chính xác.
"""

from __future__ import annotations

import queue
import shutil
import subprocess
import threading
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

MYVOICE_DIR = Path(__file__).resolve().parent.parent   # myvoice/
DIR_NGANG = MYVOICE_DIR / "videongang"
DIR_DOC = MYVOICE_DIR / "videodoc"

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"

WINDOW_WIDTH = 940
WINDOW_HEIGHT = 660


def get_duration(path: Path) -> float:
    """Trả về độ dài video (giây). Ném ValueError nếu không đọc được."""
    result = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    )
    text = result.stdout.strip()
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(f"Không đọc được độ dài video ({path.name}).") from exc


def unique_path(path: Path) -> Path:
    """Tránh ghi đè file cũ: thêm hậu tố _2, _3... nếu tên đã tồn tại."""
    if not path.exists():
        return path
    stem, suffix, parent = path.stem, path.suffix, path.parent
    i = 2
    while True:
        candidate = parent / f"{stem}_{i}{suffix}"
        if not candidate.exists():
            return candidate
        i += 1


class VideoXoaTiengGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Xóa tiếng & cắt cuối video")
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.root.minsize(820, 560)
        self.root.configure(bg="#F4F6FB")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.events: queue.Queue[tuple[str, str]] = queue.Queue()
        self.running = False
        self.proc: subprocess.Popen | None = None

        self.input_var = tk.StringVar(value="")
        self.orient_var = tk.StringVar(value="ngang")          # ngang | doc
        self.output_dir_var = tk.StringVar(value=str(DIR_NGANG))
        self.output_name_var = tk.StringVar(value="")
        self.remove_audio_var = tk.BooleanVar(value=True)
        self.trim_var = tk.StringVar(value="0")                # số giây cắt cuối
        self.status_var = tk.StringVar(value="Sẵn sàng")

        self._build_ui()
        self.root.after(100, self._poll_events)
        self.root.after(120, self._center_window)

    # ── Giao diện ────────────────────────────────────────────────────────────
    def _setup_style(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TEntry", padding=8, font=("Segoe UI", 10))
        style.configure("Primary.TButton", background="#5B5CE2", foreground="white",
                        padding=(19, 11), font=("Segoe UI", 11, "bold"))
        style.map("Primary.TButton", background=[("active", "#4849C7"), ("disabled", "#C8C8F1")])
        style.configure("Browse.TButton", background="#E8EAFF", foreground="#4849B4",
                        padding=(10, 7), font=("Segoe UI", 9, "bold"))
        style.map("Browse.TButton", background=[("active", "#DCDDFA")])

    @staticmethod
    def _card(parent: tk.Misc, padding: int = 18) -> tk.Frame:
        return tk.Frame(parent, bg="white", highlightbackground="#E3E8F1",
                        highlightthickness=1, padx=padding, pady=padding)

    def _center_window(self) -> None:
        x = max(0, (self.root.winfo_screenwidth() - WINDOW_WIDTH) // 2)
        y = max(0, (self.root.winfo_screenheight() - WINDOW_HEIGHT) // 2)
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}+{x}+{y}")

    def _section_label(self, parent: tk.Misc, text: str, description: str) -> None:
        header = tk.Frame(parent, bg="white")
        tk.Label(header, text=text, bg="white", fg="#20253F",
                 font=("Segoe UI", 13, "bold")).pack(anchor="w")
        tk.Label(header, text=description, bg="white", fg="#718096",
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(3, 0))
        header.pack(anchor="w", pady=(0, 14))

    def _build_ui(self) -> None:
        self._setup_style()

        header = tk.Frame(self.root, bg="#25235A", height=100)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="XÓA TIẾNG & CẮT CUỐI VIDEO", bg="#25235A", fg="white",
                 font=("Segoe UI", 18, "bold")).pack(anchor="w", padx=28, pady=(18, 2))
        tk.Label(header, text="Bỏ âm thanh và cắt bớt vài giây cuối · lưu vào videongang / videodoc",
                 bg="#25235A", fg="#D4D5FF", font=("Segoe UI", 10)).pack(anchor="w", padx=28)

        outer = tk.Frame(self.root, bg="#F4F6FB", padx=22, pady=16)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=3)
        outer.columnconfigure(1, weight=2)
        outer.rowconfigure(0, weight=1)

        # ── Cột trái: nguồn & đầu ra ─────────────────────────────────────────
        src_card = self._card(outer)
        src_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        src_card.columnconfigure(1, weight=1)
        self._section_label(src_card, "Nguồn & đầu ra",
                            "Chọn video cần xử lý và nơi lưu kết quả.")

        tk.Label(src_card, text="Video đầu vào:", bg="white", fg="#4A5568",
                 font=("Segoe UI", 10, "bold")).grid(row=1, column=0, sticky="w", pady=7)
        ttk.Entry(src_card, textvariable=self.input_var).grid(row=1, column=1, sticky="ew", pady=5)
        ttk.Button(src_card, text="Chọn file", style="Browse.TButton",
                   command=self._browse_input).grid(row=1, column=2, sticky="e", padx=(8, 0), pady=5)

        tk.Label(src_card, text="HƯỚNG VIDEO", bg="white", fg="#5D687B",
                 font=("Segoe UI", 8, "bold")).grid(row=2, column=0, columnspan=3,
                                                    sticky="w", pady=(14, 6))
        orient_frame = tk.Frame(src_card, bg="white")
        orient_frame.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(0, 6))
        tk.Radiobutton(orient_frame, text="  Ngang (videongang)", variable=self.orient_var,
                       value="ngang", command=self._on_orient_changed,
                       bg="#F3F4FF", activebackground="#E9E9FF", selectcolor="#DAD8FF",
                       fg="#393881", font=("Segoe UI", 10, "bold"), indicatoron=0,
                       relief="flat", padx=13, pady=9).pack(side="left", padx=(0, 8))
        tk.Radiobutton(orient_frame, text="  Dọc (videodoc)", variable=self.orient_var,
                       value="doc", command=self._on_orient_changed,
                       bg="#F3F4FF", activebackground="#E9E9FF", selectcolor="#DAD8FF",
                       fg="#393881", font=("Segoe UI", 10, "bold"), indicatoron=0,
                       relief="flat", padx=13, pady=9).pack(side="left")

        tk.Label(src_card, text="Thư mục lưu:", bg="white", fg="#4A5568",
                 font=("Segoe UI", 10, "bold")).grid(row=4, column=0, sticky="w", pady=7)
        ttk.Entry(src_card, textvariable=self.output_dir_var).grid(row=4, column=1, sticky="ew", pady=5)
        ttk.Button(src_card, text="Chọn thư mục", style="Browse.TButton",
                   command=self._browse_output_dir).grid(row=4, column=2, sticky="e", padx=(8, 0), pady=5)

        tk.Label(src_card, text="Tên file xuất:", bg="white", fg="#4A5568",
                 font=("Segoe UI", 10, "bold")).grid(row=5, column=0, sticky="w", pady=7)
        ttk.Entry(src_card, textvariable=self.output_name_var).grid(row=5, column=1, sticky="ew", pady=5)
        tk.Label(src_card, text="Để trống = giữ nguyên tên video gốc.", bg="white",
                 fg="#7A8497", font=("Segoe UI", 9)).grid(row=6, column=1, sticky="w", pady=(0, 2))

        # ── Cột phải: tùy chọn & chạy ────────────────────────────────────────
        opt_card = self._card(outer)
        opt_card.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        self._section_label(opt_card, "Tùy chọn xử lý", "Bật/tắt hai chức năng.")

        tk.Checkbutton(opt_card, text="Xóa tiếng (bỏ âm thanh)", variable=self.remove_audio_var,
                       bg="white", activebackground="white", fg="#4A5568",
                       selectcolor="#D9D7FF", font=("Segoe UI", 11), anchor="w").pack(anchor="w", pady=(2, 12))

        tk.Label(opt_card, text="Cắt bỏ cuối video (giây):", bg="white", fg="#4A5568",
                 font=("Segoe UI", 10, "bold")).pack(anchor="w")
        ttk.Entry(opt_card, textvariable=self.trim_var, width=14).pack(anchor="w", pady=(6, 4))
        tk.Label(opt_card, text="0 = không cắt. Ví dụ 3 = bỏ 3 giây cuối.\nCó cắt → video được mã hóa lại.",
                 bg="white", fg="#7A8497", font=("Segoe UI", 9), justify="left").pack(anchor="w", pady=(0, 16))

        self.run_button = ttk.Button(opt_card, text="✦ Xử lý video",
                                     style="Primary.TButton", command=self._start)
        self.run_button.pack(fill="x", pady=(4, 10))
        self.status_label = tk.Label(opt_card, textvariable=self.status_var, bg="white",
                                     fg="#5B5CE2", font=("Segoe UI", 10, "bold"),
                                     wraplength=230, justify="left")
        self.status_label.pack(anchor="w")

        # ── Nhật ký ──────────────────────────────────────────────────────────
        log_card = self._card(self.root, padding=0)
        log_card.pack(fill="both", expand=True, padx=22, pady=(0, 16))
        log_header = tk.Frame(log_card, bg="#202336", padx=16, pady=10)
        log_header.pack(fill="x")
        tk.Label(log_header, text="Nhật ký xử lý", bg="#202336", fg="white",
                 font=("Segoe UI", 11, "bold")).pack(anchor="w")
        log_content = tk.Frame(log_card, bg="#161923", padx=2, pady=2)
        log_content.pack(fill="both", expand=True)
        self.log_text = tk.Text(log_content, wrap="word", height=8, state="disabled",
                                bg="#161923", fg="#D5DEEF", insertbackground="white",
                                relief="flat", font=("Cascadia Mono", 9))
        log_scroll = ttk.Scrollbar(log_content, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")

    # ── Sự kiện chọn file / thư mục ──────────────────────────────────────────
    def _browse_input(self) -> None:
        path = filedialog.askopenfilename(
            title="Chọn video đầu vào",
            filetypes=[("Video", "*.mp4 *.mov *.mkv *.avi *.webm"), ("Tất cả", "*.*")],
        )
        if path:
            self.input_var.set(path)

    def _browse_output_dir(self) -> None:
        path = filedialog.askdirectory(title="Chọn thư mục lưu kết quả",
                                       initialdir=self.output_dir_var.get() or str(MYVOICE_DIR))
        if path:
            self.output_dir_var.set(path)

    def _on_orient_changed(self) -> None:
        self.output_dir_var.set(str(DIR_NGANG if self.orient_var.get() == "ngang" else DIR_DOC))

    # ── Chạy xử lý ───────────────────────────────────────────────────────────
    def _read_config(self) -> dict:
        input_text = self.input_var.get().strip()
        if not input_text:
            raise ValueError("Hãy chọn video đầu vào.")
        input_path = Path(input_text).expanduser()
        if not input_path.is_file():
            raise ValueError("Video đầu vào không tồn tại.")

        out_dir = Path(self.output_dir_var.get().strip() or DIR_NGANG).expanduser()

        name = self.output_name_var.get().strip() or input_path.name
        if not Path(name).suffix:
            name += input_path.suffix or ".mp4"
        output_path = out_dir / Path(name).name

        trim_text = self.trim_var.get().strip() or "0"
        try:
            trim = float(trim_text)
        except ValueError as exc:
            raise ValueError("Số giây cắt cuối phải là một số.") from exc
        if trim < 0:
            raise ValueError("Số giây cắt cuối không được âm.")

        remove_audio = self.remove_audio_var.get()
        if not remove_audio and trim == 0:
            raise ValueError("Chưa chọn thao tác nào: hãy bật xóa tiếng hoặc nhập số giây cắt cuối.")

        return {
            "input_path": input_path,
            "output_path": output_path,
            "remove_audio": remove_audio,
            "trim": trim,
        }

    def _start(self) -> None:
        if self.running:
            return
        try:
            config = self._read_config()
        except ValueError as exc:
            messagebox.showerror("Thiếu hoặc sai dữ liệu", str(exc), parent=self.root)
            return

        missing = [n for n in (FFMPEG, FFPROBE) if shutil.which(n) is None]
        if missing:
            messagebox.showerror("Thiếu ffmpeg",
                                 f"Không tìm thấy: {', '.join(missing)}. Hãy cài ffmpeg và thêm vào PATH.",
                                 parent=self.root)
            return

        self.running = True
        self.run_button.configure(state="disabled")
        self.status_var.set("Đang xử lý — không đóng cửa sổ này")
        self.status_label.configure(fg="#D97706")
        self._clear_log()
        threading.Thread(target=self._worker, args=(config,), daemon=True).start()

    def _worker(self, config: dict) -> None:
        try:
            src: Path = config["input_path"]
            dst: Path = config["output_path"]
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst = unique_path(dst)
            config["output_path"] = dst

            trim: float = config["trim"]
            remove_audio: bool = config["remove_audio"]

            self.events.put(("log", f"Nguồn : {src}\n"))
            self.events.put(("log", f"Đích  : {dst}\n"))

            cmd = [FFMPEG, "-y", "-i", str(src)]

            if trim > 0:
                duration = get_duration(src)
                new_dur = duration - trim
                if new_dur <= 0:
                    self.events.put(("error",
                        f"Video chỉ dài {duration:.2f}s, không thể cắt bỏ {trim:.2f}s cuối."))
                    return
                self.events.put(("log",
                    f"Độ dài: {duration:.2f}s → cắt còn {new_dur:.2f}s (bỏ {trim:.2f}s cuối)\n"))
                # Có cắt → mã hóa lại để điểm cắt chính xác.
                cmd += ["-t", f"{new_dur:.3f}", "-c:v", "libx264", "-crf", "18",
                        "-preset", "fast", "-pix_fmt", "yuv420p"]
                if remove_audio:
                    cmd += ["-an"]
                    self.events.put(("log", "Thao tác: xóa tiếng + cắt cuối\n"))
                else:
                    cmd += ["-c:a", "aac", "-b:a", "192k"]
                    self.events.put(("log", "Thao tác: cắt cuối (giữ âm thanh)\n"))
            else:
                # Chỉ xóa tiếng → sao chép luồng video, không giảm chất lượng.
                cmd += ["-c:v", "copy", "-an"]
                self.events.put(("log", "Thao tác: xóa tiếng (sao chép nhanh, giữ nguyên chất lượng)\n"))

            cmd += [str(dst)]
            self.events.put(("log", "\n$ " + " ".join(cmd) + "\n\n"))

            self.proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
            )
            for line in self.proc.stdout:                       # type: ignore[union-attr]
                self.events.put(("log", line))
            code = self.proc.wait()
            self.proc = None

            if code != 0:
                self.events.put(("error", f"ffmpeg kết thúc với mã lỗi {code}. Xem nhật ký phía trên."))
                return
            self.events.put(("done", str(dst)))
        except BaseException:
            self.events.put(("error", traceback.format_exc()))

    # ── Vòng lặp cập nhật giao diện ──────────────────────────────────────────
    def _poll_events(self) -> None:
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "log":
                    self._append_log(value)
                elif kind == "done":
                    self.running = False
                    self.run_button.configure(state="normal")
                    self.status_var.set("Hoàn tất")
                    self.status_label.configure(fg="#15803D")
                    self._append_log(f"\nHoàn tất → {value}\n")
                    messagebox.showinfo("Hoàn tất", f"Đã xử lý xong:\n{value}", parent=self.root)
                elif kind == "error":
                    self.running = False
                    self.run_button.configure(state="normal")
                    self.status_var.set("Có lỗi")
                    self.status_label.configure(fg="#DC2626")
                    self._append_log(f"\nLỖI:\n{value}\n")
                    messagebox.showerror("Xử lý thất bại", "Xem chi tiết ở nhật ký.", parent=self.root)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_events)

    def _append_log(self, text: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _on_close(self) -> None:
        if self.running:
            messagebox.showwarning("Đang xử lý",
                                   "Đang xử lý video. Hãy đợi hoàn tất trước khi đóng.",
                                   parent=self.root)
            return
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    VideoXoaTiengGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
