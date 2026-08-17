# -*- coding: utf-8 -*-
"""GUI tạo phụ đề cho video — bọc video_gansub.py cho khỏi phải gõ lệnh.

Chạy từ thư mục gốc OmniVoice:
    venv\\Scripts\\python myvoice\\scripts\\video_gansub_gui.py

Cách làm (do video_gansub.py đảm nhiệm):
  chữ lấy từ kịch bản GỐC (input.txt) → Whisper chỉ nghe audio để lấy mốc giờ
  từng từ → khớp hai chuỗi → xuất .srt. Nhờ vậy tên riêng, dấu câu chính xác
  tuyệt đối, khác hẳn kiểu để Whisper tự chép lời.

Ba kiểu xuất:
  • Chỉ .srt   – nhanh nhất, không đụng vào video. Tải lên YouTube Studio.
  • Nhúng mềm  – gắn .srt vào mp4 (bật/tắt được trong trình phát). Lưu ý: đa số
                 mạng xã hội BỎ QUA phụ đề mềm khi upload.
  • Vẽ cứng    – in chữ thẳng vào khung hình. Bắt buộc nếu muốn có phụ đề trên
                 TikTok/Reels. Phải mã hóa lại video nên lâu hơn nhiều.
"""

from __future__ import annotations

import os
import sys

# ── Tự chuyển sang python của venv (giống các *_gui.py khác) ────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))                       # myvoice/scripts
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, os.pardir, os.pardir))  # gốc repo
_VENV_PYTHON = os.path.join(_REPO_ROOT, "venv", "Scripts", "python.exe")
if __name__ == "__main__" and os.path.exists(_VENV_PYTHON) and \
        os.path.normcase(os.path.abspath(sys.executable)) != \
        os.path.normcase(os.path.abspath(_VENV_PYTHON)):
    import subprocess as _sp
    _sp.run([_VENV_PYTHON] + sys.argv)
    sys.exit()

import queue
import re
import shutil
import subprocess
import threading
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

SCRIPT_DIR = Path(__file__).resolve().parent          # myvoice/scripts
MYVOICE_DIR = SCRIPT_DIR.parent                       # myvoice/
GANSUB = SCRIPT_DIR / "video_gansub.py"
WHISPER_CACHE = SCRIPT_DIR / "whisper_cache"
KICHBAN_DIR = MYVOICE_DIR / "kịch_bản"

VIDEO_EXTS = [("Video", "*.mp4 *.mkv *.mov *.avi *.webm"), ("Tất cả", "*.*")]
TEXT_EXTS = [("Văn bản", "*.txt"), ("Tất cả", "*.*")]

# Model nhỏ → nhanh nhưng mốc giờ thô hơn. large-v3-turbo là điểm cân bằng tốt cho
# tiếng Việt: nặng ngang medium (1.5GB) nhưng nghe chuẩn hơn và nhanh hơn.
MODELS = ["small", "medium", "large-v3-turbo", "large-v3"]

WINDOW_WIDTH = 1020
WINDOW_HEIGHT = 760

# Whisper in tiến độ dạng "   tiến độ nghe:  42.3%" (dùng \r nên mỗi lần là 1 dòng).
_PROGRESS_RE = re.compile(r"tiến độ nghe:\s*([\d.]+)\s*%")
_SRT_OUT_RE = re.compile(r"File \.srt\s*:\s*(.+?)\s*(?:\(|$)")
_VIDEO_OUT_RE = re.compile(r"Video có sub\s*:\s*(.+?)\s*(?:\(|$)")


def cached_models() -> set[str]:
    """Tên các model whisper đã nằm sẵn trên đĩa (chạy được offline)."""
    if not WHISPER_CACHE.is_dir():
        return set()
    # Chủ repo khác nhau theo model (Systran, riêng turbo là mobiuslabsgmbh) → cắt theo
    # phần sau "faster-whisper-" thay vì so cứng một prefix.
    marker = "--faster-whisper-"
    return {d.name.split(marker, 1)[1] for d in WHISPER_CACHE.iterdir()
            if d.is_dir() and marker in d.name}


def guess_script(video: Path) -> Path | None:
    """input.txt nằm CẠNH video (mỗi dự án một thư mục) — không có thì trả None."""
    sibling = video.resolve().parent / "input.txt"
    if sibling.is_file() and sibling.stat().st_size > 0:
        return sibling
    return None


class GanSubGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Tạo phụ đề cho video")
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.root.minsize(940, 730)
        self.root.configure(bg="#F4F6FB")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.events: queue.Queue[tuple[str, str]] = queue.Queue()
        self.running = False
        self.proc: subprocess.Popen | None = None
        self.result_path: Path | None = None
        self._cached = cached_models()

        self.video_var = tk.StringVar()
        self.script_var = tk.StringVar()
        self.script_hint_var = tk.StringVar(value="Chọn video trước — kịch bản sẽ tự tìm.")
        self.mode_var = tk.StringVar(value="srt")            # srt | soft | burn
        self.model_var = tk.StringVar(value="large-v3-turbo")
        self.maxchars_var = tk.StringVar(value="50")
        self.status_var = tk.StringVar(value="Sẵn sàng")
        self.progress_var = tk.DoubleVar(value=0.0)

        self._build_ui()
        self.root.after(100, self._poll_events)
        self.root.after(120, self._center_window)

    # ── Giao diện ────────────────────────────────────────────────────────────
    def _setup_style(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TEntry", padding=8, font=("Segoe UI", 10))
        style.configure("TCombobox", padding=6, font=("Segoe UI", 10))
        style.configure("Primary.TButton", background="#5B5CE2", foreground="white",
                        padding=(19, 11), font=("Segoe UI", 11, "bold"))
        style.map("Primary.TButton", background=[("active", "#4849C7"), ("disabled", "#C8C8F1")])
        style.configure("Browse.TButton", background="#E8EAFF", foreground="#4849B4",
                        padding=(10, 7), font=("Segoe UI", 9, "bold"))
        style.map("Browse.TButton", background=[("active", "#DCDDFA")])
        style.configure("Stop.TButton", background="#FDE2E2", foreground="#B42318",
                        padding=(14, 10), font=("Segoe UI", 10, "bold"))
        style.map("Stop.TButton", background=[("active", "#F9C9C9"), ("disabled", "#F5F5F5")])
        style.configure("Sub.Horizontal.TProgressbar", troughcolor="#E9ECF5",
                        background="#5B5CE2", thickness=14)

    @staticmethod
    def _card(parent: tk.Misc, padding: int = 18) -> tk.Frame:
        return tk.Frame(parent, bg="white", highlightbackground="#E3E8F1",
                        highlightthickness=1, padx=padding, pady=padding)

    def _center_window(self) -> None:
        x = max(0, (self.root.winfo_screenwidth() - WINDOW_WIDTH) // 2)
        y = max(0, (self.root.winfo_screenheight() - WINDOW_HEIGHT) // 3)
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
        tk.Label(header, text="TẠO PHỤ ĐỀ CHO VIDEO", bg="#25235A", fg="white",
                 font=("Segoe UI", 18, "bold")).pack(anchor="w", padx=28, pady=(18, 2))
        tk.Label(header, text="Chữ lấy từ kịch bản gốc · Whisper chỉ dùng để căn giờ · chính xác 100% tên riêng",
                 bg="#25235A", fg="#D4D5FF", font=("Segoe UI", 10)).pack(anchor="w", padx=28)

        body = tk.Frame(self.root, bg="#F4F6FB")
        body.pack(fill="both", expand=True, padx=24, pady=18)

        # Màn hình làm việc chỉ cao ~860px nên KHÔNG xếp 3 thẻ chồng dọc (sẽ tràn,
        # khung nhật ký bị cắt). Nguồn nằm trên cùng cho ô đường dẫn đủ rộng, hai
        # thẻ còn lại đặt cạnh nhau.
        lower = tk.Frame(body, bg="#F4F6FB")

        # ── Nguồn ──
        card1 = self._card(body)
        card1.pack(fill="x")
        self._section_label(card1, "1 · Nguồn",
                            "Chọn video; kịch bản input.txt cạnh video sẽ được tự nhận.")

        row = tk.Frame(card1, bg="white")
        row.pack(fill="x", pady=(0, 10))
        tk.Label(row, text="Video", bg="white", fg="#3B4256", width=9, anchor="w",
                 font=("Segoe UI", 10)).pack(side="left")
        ttk.Entry(row, textvariable=self.video_var).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Chọn…", style="Browse.TButton",
                   command=self._pick_video).pack(side="left", padx=(8, 0))

        row = tk.Frame(card1, bg="white")
        row.pack(fill="x")
        tk.Label(row, text="Kịch bản", bg="white", fg="#3B4256", width=9, anchor="w",
                 font=("Segoe UI", 10)).pack(side="left")
        ttk.Entry(row, textvariable=self.script_var).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Chọn…", style="Browse.TButton",
                   command=self._pick_script).pack(side="left", padx=(8, 0))
        tk.Label(card1, textvariable=self.script_hint_var, bg="white", fg="#718096",
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(6, 0))

        # ── Tùy chọn (cột trái) ──
        lower.pack(fill="both", expand=True, pady=(16, 0))
        card2 = self._card(lower, padding=16)
        card2.pack(side="left", fill="y")
        self._section_label(card2, "2 · Kiểu xuất",
                            "Đưa lên YouTube thì dùng .srt rời.")

        for value, title, desc in [
            ("srt", "Chỉ xuất file .srt",
             "Tải lên YouTube Studio. Không đụng vào video."),
            ("soft", "Nhúng mềm vào mp4",
             "Xem bằng VLC được; upload lên mạng thường bị bỏ qua."),
            ("burn", "Vẽ cứng vào khung hình",
             "Bắt buộc cho TikTok/Reels. Mã hóa lại nên lâu."),
        ]:
            f = tk.Frame(card2, bg="white")
            f.pack(fill="x", anchor="w", pady=(0, 6))
            tk.Radiobutton(f, text=title, value=value, variable=self.mode_var,
                           bg="white", fg="#20253F", activebackground="white",
                           selectcolor="white", font=("Segoe UI", 10, "bold"),
                           anchor="w").pack(anchor="w")
            tk.Label(f, text=desc, bg="white", fg="#718096",
                     font=("Segoe UI", 9)).pack(anchor="w", padx=(26, 0))

        opts = tk.Frame(card2, bg="white")
        opts.pack(fill="x", pady=(8, 0))
        tk.Label(opts, text="Model nghe", bg="white", fg="#3B4256", width=14, anchor="w",
                 font=("Segoe UI", 10)).pack(side="left")
        self.cb_model = ttk.Combobox(opts, textvariable=self.model_var, width=15,
                                     state="readonly", values=MODELS)
        self.cb_model.pack(side="left")
        self.cb_model.bind("<<ComboboxSelected>>", lambda _e: self._update_model_hint())
        self.model_hint = tk.Label(card2, text="", bg="white", fg="#718096",
                                   font=("Segoe UI", 9))
        self.model_hint.pack(anchor="w", padx=(2, 0), pady=(3, 0))
        self._update_model_hint()

        opts2 = tk.Frame(card2, bg="white")
        opts2.pack(fill="x", pady=(8, 0))
        tk.Label(opts2, text="Dài mỗi dòng", bg="white", fg="#3B4256", width=14, anchor="w",
                 font=("Segoe UI", 10)).pack(side="left")
        ttk.Spinbox(opts2, from_=20, to=90, increment=1, width=6,
                    textvariable=self.maxchars_var).pack(side="left")
        tk.Label(opts2, text="ký tự", bg="white", fg="#718096",
                 font=("Segoe UI", 9)).pack(side="left", padx=(6, 0))

        # ── Chạy (cột phải) ──
        card3 = self._card(lower, padding=16)
        card3.pack(side="left", fill="both", expand=True, padx=(16, 0))
        self._section_label(card3, "3 · Chạy",
                            "Video 35 phút mất khoảng 6 phút với model medium (GPU, không cần mạng).")

        bar = tk.Frame(card3, bg="white")
        bar.pack(fill="x", pady=(0, 10))
        self.run_button = ttk.Button(bar, text="Tạo phụ đề", style="Primary.TButton",
                                     command=self._start)
        self.run_button.pack(side="left")
        self.stop_button = ttk.Button(bar, text="Dừng", style="Stop.TButton",
                                      command=self._stop, state="disabled")
        self.stop_button.pack(side="left", padx=(10, 0))
        self.open_button = ttk.Button(bar, text="Mở thư mục kết quả", style="Browse.TButton",
                                      command=self._open_result, state="disabled")
        self.open_button.pack(side="right")

        self.status_label = tk.Label(card3, textvariable=self.status_var, bg="white",
                                     fg="#4B5563", font=("Segoe UI", 10, "bold"))
        self.status_label.pack(anchor="w")
        ttk.Progressbar(card3, style="Sub.Horizontal.TProgressbar", maximum=100,
                        variable=self.progress_var).pack(fill="x", pady=(6, 12))

        log_wrap = tk.Frame(card3, bg="white")
        log_wrap.pack(fill="both", expand=True)
        # width nhỏ: khung tự giãn theo pack(fill=both), để rộng sẽ đội cả cửa sổ.
        self.log_text = tk.Text(log_wrap, height=8, width=46, wrap="word", state="disabled",
                                bg="#FBFBFD", fg="#3B4256", relief="flat",
                                highlightthickness=1, highlightbackground="#E3E8F1",
                                font=("Consolas", 9), padx=10, pady=8)
        self.log_text.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(log_wrap, orient="vertical", command=self.log_text.yview)
        sb.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=sb.set)

    def _update_model_hint(self) -> None:
        name = self.model_var.get()
        if name in self._cached:
            self.model_hint.configure(text="đã tải sẵn — chạy offline", fg="#15803D")
        else:
            self.model_hint.configure(text="CHƯA tải — lần đầu sẽ cần mạng", fg="#B45309")

    # ── Chọn file ────────────────────────────────────────────────────────────
    def _pick_video(self) -> None:
        start = KICHBAN_DIR if KICHBAN_DIR.is_dir() else MYVOICE_DIR
        path = filedialog.askopenfilename(title="Chọn video cần làm phụ đề",
                                          initialdir=str(start), filetypes=VIDEO_EXTS)
        if not path:
            return
        self.video_var.set(path)
        found = guess_script(Path(path))
        if found:
            self.script_var.set(str(found))
            self.script_hint_var.set(f"Đã tự tìm thấy kịch bản: {found}")
        else:
            self.script_var.set("")
            self.script_hint_var.set(
                "Không thấy input.txt cạnh video — hãy chọn file kịch bản bằng tay.")

    def _pick_script(self) -> None:
        video = self.video_var.get().strip()
        start = Path(video).parent if video else KICHBAN_DIR
        path = filedialog.askopenfilename(title="Chọn file kịch bản (input.txt)",
                                          initialdir=str(start), filetypes=TEXT_EXTS)
        if path:
            self.script_var.set(path)
            self.script_hint_var.set(f"Kịch bản đang dùng: {path}")

    # ── Chạy xử lý ───────────────────────────────────────────────────────────
    def _read_config(self) -> dict:
        video_text = self.video_var.get().strip()
        if not video_text:
            raise ValueError("Hãy chọn video cần làm phụ đề.")
        video = Path(video_text).expanduser()
        if not video.is_file():
            raise ValueError("Video không tồn tại.")

        script_text = self.script_var.get().strip()
        if not script_text:
            raise ValueError("Chưa có file kịch bản. Chọn file input.txt của video này.")
        script = Path(script_text).expanduser()
        if not script.is_file():
            raise ValueError("File kịch bản không tồn tại.")
        if script.stat().st_size == 0:
            raise ValueError(f"File kịch bản rỗng:\n{script}")

        try:
            maxchars = int(self.maxchars_var.get().strip())
        except ValueError as exc:
            raise ValueError("Độ dài mỗi dòng phải là một số nguyên.") from exc
        if not 20 <= maxchars <= 90:
            raise ValueError("Độ dài mỗi dòng nên nằm trong khoảng 20–90 ký tự.")

        return {"video": video, "script": script, "mode": self.mode_var.get(),
                "model": self.model_var.get(), "maxchars": maxchars}

    def _start(self) -> None:
        if self.running:
            return
        try:
            config = self._read_config()
        except ValueError as exc:
            messagebox.showerror("Thiếu hoặc sai dữ liệu", str(exc), parent=self.root)
            return

        if not GANSUB.is_file():
            messagebox.showerror("Thiếu script", f"Không tìm thấy:\n{GANSUB}", parent=self.root)
            return
        if shutil.which("ffmpeg") is None:
            messagebox.showerror("Thiếu ffmpeg",
                                 "Không tìm thấy ffmpeg trong PATH. Hãy cài ffmpeg trước.",
                                 parent=self.root)
            return
        if config["mode"] == "burn" and not messagebox.askyesno(
                "Vẽ cứng phụ đề",
                "Kiểu này phải MÃ HÓA LẠI toàn bộ video nên lâu hơn nhiều "
                "(video dài 35 phút có thể mất thêm 5–10 phút).\n\nTiếp tục?",
                parent=self.root):
            return

        self.running = True
        self.result_path = None
        self.run_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.open_button.configure(state="disabled")
        self.progress_var.set(0)
        self.status_var.set("Đang chạy — không đóng cửa sổ này")
        self.status_label.configure(fg="#D97706")
        self._clear_log()
        threading.Thread(target=self._worker, args=(config,), daemon=True).start()

    def _worker(self, config: dict) -> None:
        try:
            cmd = [sys.executable, "-u", str(GANSUB), str(config["video"]),
                   "--script", str(config["script"]),
                   "--model", config["model"],
                   "--max-chars", str(config["maxchars"])]
            if config["mode"] == "srt":
                cmd.append("--srt-only")
            elif config["mode"] == "burn":
                cmd.append("--burn")

            self.events.put(("log", "$ " + " ".join(cmd) + "\n\n"))
            self.proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            for line in self.proc.stdout:                       # type: ignore[union-attr]
                m = _PROGRESS_RE.search(line)
                if m:
                    # Dòng tiến độ lặp lại liên tục → chỉ đẩy thanh, không đổ vào log.
                    self.events.put(("progress", m.group(1)))
                    continue
                for rx in (_SRT_OUT_RE, _VIDEO_OUT_RE):
                    hit = rx.search(line)
                    if hit:
                        self.events.put(("result", hit.group(1).strip()))
                self.events.put(("log", line))
            code = self.proc.wait()
            self.proc = None

            if code != 0:
                self.events.put(("error", f"Tiến trình kết thúc với mã lỗi {code}. "
                                          "Xem nhật ký phía trên."))
                return
            self.events.put(("done", ""))
        except BaseException:
            self.events.put(("error", traceback.format_exc()))

    def _stop(self) -> None:
        if not self.running or self.proc is None:
            return
        if not messagebox.askyesno("Dừng", "Dừng việc tạo phụ đề đang chạy?",
                                   parent=self.root):
            return
        try:
            self.proc.terminate()
        except Exception:
            pass
        self.events.put(("log", "\n⏹ Đã yêu cầu dừng.\n"))

    # ── Vòng lặp cập nhật giao diện ──────────────────────────────────────────
    def _poll_events(self) -> None:
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "log":
                    self._append_log(value)
                elif kind == "progress":
                    try:
                        pct = float(value)
                    except ValueError:
                        pct = 0.0
                    self.progress_var.set(pct)
                    self.status_var.set(f"Đang nghe audio để căn giờ… {pct:.0f}%")
                elif kind == "result":
                    self.result_path = Path(value)
                elif kind == "done":
                    self._finish(ok=True)
                elif kind == "error":
                    self._append_log(f"\nLỖI:\n{value}\n")
                    self._finish(ok=False)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_events)

    def _finish(self, ok: bool) -> None:
        self.running = False
        self.proc = None
        self.run_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        if ok:
            self.progress_var.set(100)
            self.status_var.set("Hoàn tất")
            self.status_label.configure(fg="#15803D")
            if self.result_path:
                self.open_button.configure(state="normal")
                messagebox.showinfo("Hoàn tất", f"Đã tạo xong:\n{self.result_path}",
                                    parent=self.root)
            else:
                messagebox.showinfo("Hoàn tất", "Đã chạy xong. Xem nhật ký để biết đường dẫn.",
                                    parent=self.root)
        else:
            self.status_var.set("Có lỗi")
            self.status_label.configure(fg="#DC2626")
            messagebox.showerror("Thất bại", "Xem chi tiết ở nhật ký.", parent=self.root)

    def _open_result(self) -> None:
        if not self.result_path:
            return
        folder = self.result_path.parent
        try:
            os.startfile(str(folder))       # type: ignore[attr-defined]
        except Exception as exc:
            messagebox.showerror("Không mở được thư mục", str(exc), parent=self.root)

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
            messagebox.showwarning("Đang chạy",
                                   "Đang tạo phụ đề. Bấm Dừng rồi hãy đóng cửa sổ.",
                                   parent=self.root)
            return
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    GanSubGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
