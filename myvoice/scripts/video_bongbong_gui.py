# -*- coding: utf-8 -*-
"""GUI điều khiển hiệu ứng bong bóng của bubble_video.py.

Chạy từ thư mục gốc OmniVoice:
    venv\Scripts\python myvoice\scripts\bubble_video_gui.py

GUI gọi trực tiếp các hàm render trong bubble_video.py; không sửa các giá trị
mặc định trong file renderer.
"""

from __future__ import annotations

import contextlib
import io
import queue
import shutil
import sys
import threading
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import bubble_video as bubble


EFFECTS_DIR = Path(bubble.EFFECTS_DIR)
WINDOW_WIDTH = 1120
WINDOW_HEIGHT = 700


class QueueWriter(io.TextIOBase):
    """Chuyển print() của worker sang ô nhật ký Tkinter."""

    def __init__(self, events: queue.Queue[tuple[str, str]]):
        self.events = events

    def write(self, text: str) -> int:
        if text:
            self.events.put(("log", text))
        return len(text)

    def flush(self) -> None:
        pass


class BubbleVideoGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Hiệu ứng bong bóng video")
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.root.minsize(980, 620)
        self.root.configure(bg="#F4F6FB")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.events: queue.Queue[tuple[str, str]] = queue.Queue()
        self.running = False

        default_input = Path(bubble.INPUT)
        default_mode = bubble.RENDER_MODE if bubble.RENDER_MODE in {"burn", "transparent"} else "burn"
        default_output = EFFECTS_DIR / (
            "bubbles_output.mp4" if default_mode == "burn" else "bubbles_overlay.mov"
        )

        self.mode_var = tk.StringVar(value=default_mode)
        self.input_var = tk.StringVar(value=str(default_input) if default_input.exists() else "")
        self.output_var = tk.StringVar(value=str(default_output))
        self.image_dir_var = tk.StringVar(value=str(Path(bubble.IMAGE_DIR)))
        self.duration_var = tk.StringVar(
            value="" if bubble.CLIP_SECONDS is None else str(bubble.CLIP_SECONDS)
        )
        self.width_var = tk.StringVar(value=str(bubble.OUTPUT_WIDTH))
        self.height_var = tk.StringVar(value=str(bubble.OUTPUT_HEIGHT))
        self.fps_var = tk.StringVar(value=str(bubble.OUTPUT_FPS))
        self.feature_random_var = tk.BooleanVar(value=bubble.FEATURE_IN_RANDOM)
        self.until_images_var = tk.BooleanVar(value=bubble.RENDER_UNTIL_IMAGES_FINISH)

        self.settings = {
            "spawn_rate": tk.StringVar(value=str(bubble.SPAWN_RATE)),
            "max_bubbles": tk.StringVar(value=str(bubble.MAX_BUBBLES)),
            "fade_out": tk.StringVar(value=str(bubble.FADE_OUT_SEC)),
            "slow_speed": tk.StringVar(value=str(bubble.SLOW_SPEED)),
            "fast_speed": tk.StringVar(value=str(bubble.FAST_SPEED)),
            "fast_frac": tk.StringVar(value=str(bubble.FAST_FRAC)),
            "drift_ratio": tk.StringVar(value=str(bubble.DRIFT_RATIO)),
            "tiny_frac": tk.StringVar(value=str(bubble.TINY_FRAC)),
            "size_min": tk.StringVar(value=str(bubble.SIZE_MIN)),
            "size_max": tk.StringVar(value=str(bubble.SIZE_MAX)),
            "tiny_min": tk.StringVar(value=str(bubble.TINY_MIN)),
            "tiny_max": tk.StringVar(value=str(bubble.TINY_MAX)),
            "shell_opacity": tk.StringVar(value=str(bubble.SHELL_OPACITY)),
            "inner_opacity": tk.StringVar(value=str(bubble.INNER_OPACITY)),
            "seed": tk.StringVar(value="" if bubble.SEED is None else str(bubble.SEED)),
        }

        self.status_var = tk.StringVar(value="Sẵn sàng")
        self._build_ui()
        self.root.after(100, self._poll_events)
        self.root.after(120, self._center_window)

    def _setup_style(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TEntry", padding=8, font=("Segoe UI", 10))
        style.configure("Primary.TButton", background="#5B5CE2", foreground="white", padding=(19, 11), font=("Segoe UI", 11, "bold"))
        style.map("Primary.TButton", background=[("active", "#4849C7"), ("disabled", "#C8C8F1")])
        style.configure("Browse.TButton", background="#E8EAFF", foreground="#4849B4", padding=(10, 7), font=("Segoe UI", 9, "bold"))
        style.map("Browse.TButton", background=[("active", "#DCDDFA")])
        style.configure("TNotebook", background="#F4F6FB", borderwidth=0)
        style.configure("TNotebook.Tab", background="#E7EAF2", foreground="#5D687B", padding=(22, 10), font=("Segoe UI", 10, "bold"))
        style.map("TNotebook.Tab", background=[("selected", "#FFFFFF")], foreground=[("selected", "#3F3E9D")])

    @staticmethod
    def _card(parent: tk.Misc, padding: int = 18) -> tk.Frame:
        return tk.Frame(parent, bg="white", highlightbackground="#E3E8F1", highlightthickness=1, padx=padding, pady=padding)

    def _center_window(self) -> None:
        x = max(0, (self.root.winfo_screenwidth() - WINDOW_WIDTH) // 2)
        y = max(0, (self.root.winfo_screenheight() - WINDOW_HEIGHT) // 2)
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}+{x}+{y}")

    def _section_label(self, parent: tk.Misc, text: str, description: str, *, grid: bool = False) -> None:
        header = tk.Frame(parent, bg="white")
        tk.Label(header, text=text, bg="white", fg="#20253F", font=("Segoe UI", 13, "bold")).pack(anchor="w")
        tk.Label(header, text=description, bg="white", fg="#718096", font=("Segoe UI", 9)).pack(anchor="w", pady=(3, 0))
        if grid:
            header.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 16))
        else:
            header.pack(anchor="w", pady=(0, 16))

    def _build_ui(self) -> None:
        self._setup_style()
        header = tk.Frame(self.root, bg="#25235A", height=108)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="BUBBLE VIDEO STUDIO", bg="#25235A", fg="white", font=("Segoe UI", 19, "bold")).pack(
            anchor="w", padx=30, pady=(19, 2)
        )
        tk.Label(
            header,
            text="Tạo lớp bong bóng có ảnh · render MP4 trực tiếp hoặc MOV nền trong suốt",
            bg="#25235A",
            fg="#D4D5FF",
            font=("Segoe UI", 10),
        ).pack(anchor="w", padx=30)

        outer = tk.Frame(self.root, bg="#F4F6FB", padx=22, pady=18)
        outer.pack(fill="both", expand=True)
        notebook = ttk.Notebook(outer)
        notebook.pack(fill="both", expand=True)

        basic = tk.Frame(notebook, bg="#F4F6FB", padx=12, pady=12)
        advanced = tk.Frame(notebook, bg="#F4F6FB", padx=12, pady=12)
        log_tab = tk.Frame(notebook, bg="#F4F6FB", padx=12, pady=12)
        notebook.add(basic, text="Thiết lập")
        notebook.add(advanced, text="Hiệu ứng nâng cao")
        notebook.add(log_tab, text="Nhật ký render")

        basic.columnconfigure(0, weight=5)
        basic.columnconfigure(1, weight=4)
        basic.columnconfigure(2, weight=3)
        basic.rowconfigure(0, weight=1)
        source_card = self._card(basic)
        source_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        source_card.columnconfigure(1, weight=1)
        self._section_label(source_card, "Nguồn & đầu ra", "Chọn video, ảnh trong bong bóng và tên file kết quả.", grid=True)

        tk.Label(source_card, text="CHẾ ĐỘ RENDER", bg="white", fg="#5D687B", font=("Segoe UI", 8, "bold")).grid(
            row=2, column=0, columnspan=3, sticky="w", pady=(0, 6)
        )
        mode_frame = tk.Frame(source_card, bg="white")
        mode_frame.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(0, 15))
        tk.Radiobutton(
            mode_frame, text="  Ghép trực tiếp MP4", variable=self.mode_var, value="burn", command=self._on_mode_changed,
            bg="#F3F4FF", activebackground="#E9E9FF", selectcolor="#DAD8FF", fg="#393881", font=("Segoe UI", 10, "bold"),
            indicatoron=0, relief="flat", padx=13, pady=9,
        ).pack(side="left", padx=(0, 8))
        tk.Radiobutton(
            mode_frame, text="  MOV nền trong suốt", variable=self.mode_var, value="transparent", command=self._on_mode_changed,
            bg="#F3F4FF", activebackground="#E9E9FF", selectcolor="#DAD8FF", fg="#393881", font=("Segoe UI", 10, "bold"),
            indicatoron=0, relief="flat", padx=13, pady=9,
        ).pack(side="left")

        self.input_label = tk.Label(source_card, text="Video đầu vào:", bg="white", fg="#4A5568", font=("Segoe UI", 10, "bold"))
        self.input_label.grid(row=4, column=0, sticky="w", pady=7)
        self._add_path_row(source_card, 4, self.input_var, self._browse_input)
        tk.Label(source_card, text="Tên file xuất:", bg="white", fg="#4A5568", font=("Segoe UI", 10, "bold")).grid(
            row=5, column=0, sticky="w", pady=7
        )
        self._add_path_row(source_card, 5, self.output_var, self._browse_output)
        tk.Label(source_card, text="Thư mục ảnh:", bg="white", fg="#4A5568", font=("Segoe UI", 10, "bold")).grid(
            row=6, column=0, sticky="w", pady=7
        )
        self._add_path_row(source_card, 6, self.image_dir_var, self._browse_image_dir, folder=True)
        tk.Label(
            source_card, text=f"Mọi file xuất luôn nằm trong: {EFFECTS_DIR}", bg="white", fg="#7A8497", font=("Segoe UI", 9),
            wraplength=470,
        ).grid(row=7, column=0, columnspan=3, sticky="w", pady=(12, 0))

        option_card = self._card(basic)
        option_card.grid(row=0, column=1, sticky="nsew", padx=8)
        self._section_label(option_card, "Thời lượng & nội dung", "Thiết lập clip MOV và cách sử dụng danh sách ảnh.")
        tk.Label(option_card, text="Độ dài lớp bong bóng (giây)", bg="white", fg="#4A5568", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        ttk.Entry(option_card, textvariable=self.duration_var, width=18).pack(anchor="w", pady=(6, 4))
        tk.Label(
            option_card, text="Để trống = dùng hết video tham chiếu. Chỉ áp dụng với MOV.", bg="white", fg="#7A8497", font=("Segoe UI", 9), wraplength=300,
        ).pack(anchor="w", pady=(0, 16))

        resolution = tk.Frame(option_card, bg="#F7F8FC", highlightbackground="#E2E7F0", highlightthickness=1, padx=10, pady=10)
        resolution.pack(fill="x")
        tk.Label(resolution, text="MOV không có video tham chiếu", bg="#F7F8FC", fg="#4A5568", font=("Segoe UI", 9, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 8)
        )
        self._add_compact_entry(resolution, 0, "Rộng", self.width_var, row=1)
        self._add_compact_entry(resolution, 2, "Cao", self.height_var, row=1)
        self._add_compact_entry(resolution, 0, "FPS", self.fps_var, row=2)

        tk.Checkbutton(
            option_card, text="Cho Pink.png xuất hiện ngẫu nhiên", variable=self.feature_random_var, bg="white", activebackground="white",
            fg="#4A5568", selectcolor="#D9D7FF", font=("Segoe UI", 10), anchor="w",
        ).pack(anchor="w", pady=(18, 8))
        tk.Checkbutton(
            option_card, text="Dùng từng ảnh một lần rồi tự dừng", variable=self.until_images_var, bg="white", activebackground="white",
            fg="#4A5568", selectcolor="#D9D7FF", font=("Segoe UI", 10), anchor="w",
        ).pack(anchor="w")
        tk.Label(
            option_card, text="Tùy chọn này chỉ dùng với MOV nền trong suốt. Pink.png luôn là bong bóng lớn nhất.",
            bg="white", fg="#7A8497", font=("Segoe UI", 9), wraplength=310, justify="left",
        ).pack(anchor="w", pady=(5, 0))

        render_card = self._card(basic)
        render_card.grid(row=0, column=2, sticky="nsew", padx=(8, 0))
        self._section_label(render_card, "Render video", "Sẵn sàng tạo hiệu ứng bong bóng.")
        indicator = tk.Frame(render_card, bg="#F0EFFF", padx=12, pady=12)
        indicator.pack(fill="x", pady=(0, 16))
        tk.Label(indicator, text="ĐẦU RA", bg="#F0EFFF", fg="#6256B6", font=("Segoe UI", 8, "bold")).pack(anchor="w")
        tk.Label(indicator, text="scripts / hieuung", bg="#F0EFFF", fg="#332F66", font=("Segoe UI", 10, "bold"), wraplength=170).pack(
            anchor="w", pady=(4, 0)
        )
        self.render_button = ttk.Button(render_card, text="✦ Render", style="Primary.TButton", command=self._start_render)
        self.render_button.pack(fill="x", pady=(0, 12))
        self.status_label = tk.Label(
            render_card, textvariable=self.status_var, bg="white", fg="#5B5CE2", font=("Segoe UI", 10, "bold"),
            wraplength=180, justify="left",
        )
        self.status_label.pack(anchor="w")
        tk.Label(
            render_card,
            text="Tên trùng sẽ tự tăng hậu tố _2, _3 để bảo toàn file cũ.",
            bg="white", fg="#7A8497", font=("Segoe UI", 9), wraplength=185, justify="left",
        ).pack(anchor="w", pady=(8, 0))

        advanced.columnconfigure(0, weight=1)
        advanced.rowconfigure(0, weight=1)
        advanced_card = self._card(advanced)
        advanced_card.grid(row=0, column=0, sticky="nsew")
        advanced_card.columnconfigure(1, weight=1)
        advanced_card.columnconfigure(3, weight=1)
        self._section_label(
            advanced_card,
            "Tinh chỉnh hiệu ứng",
            "Các thông số này ảnh hưởng trực tiếp đến mật độ, tốc độ và kích thước bong bóng.",
            grid=True,
        )
        fields = [
            ("Tần suất sinh (bóng/giây)", "spawn_rate"),
            ("Số bóng tối đa", "max_bubbles"),
            ("Mờ tan cuối clip (giây)", "fade_out"),
            ("Tốc độ chậm (px/giây)", "slow_speed"),
            ("Tốc độ nhanh (px/giây)", "fast_speed"),
            ("Tỷ lệ bóng nhanh (0–1)", "fast_frac"),
            ("Độ bay xéo sang phải", "drift_ratio"),
            ("Tỷ lệ bóng bé tý (0–1)", "tiny_frac"),
            ("Cỡ ảnh nhỏ nhất", "size_min"),
            ("Cỡ ảnh lớn nhất", "size_max"),
            ("Cỡ bóng bé tý nhỏ nhất", "tiny_min"),
            ("Cỡ bóng bé tý lớn nhất", "tiny_max"),
            ("Độ đục vỏ (0–1)", "shell_opacity"),
            ("Độ rõ ảnh trong (0–1)", "inner_opacity"),
            ("Hạt ngẫu nhiên (trống = mỗi lần khác)", "seed"),
        ]
        for index, (label, key) in enumerate(fields):
            row, offset = divmod(index, 2)
            row += 2
            column = offset * 2
            tk.Label(advanced_card, text=label, bg="white", fg="#4A5568", font=("Segoe UI", 10)).grid(
                row=row, column=column, sticky="w", padx=(0, 8), pady=8
            )
            ttk.Entry(advanced_card, textvariable=self.settings[key], width=18).grid(
                row=row, column=column + 1, sticky="ew", padx=(0, 18), pady=6
            )
        tk.Label(
            advanced_card, text="Lưu ý: render càng nhiều bóng, kích thước lớn và video dài thì càng chậm.",
            bg="white", fg="#7A8497", font=("Segoe UI", 9),
        ).grid(row=10, column=0, columnspan=4, sticky="w", pady=(16, 0))

        log_card = self._card(log_tab, padding=0)
        log_card.pack(fill="both", expand=True)
        log_header = tk.Frame(log_card, bg="#202336", padx=16, pady=12)
        log_header.pack(fill="x")
        tk.Label(log_header, text="Tiến trình render", bg="#202336", fg="white", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        tk.Label(log_header, text="Thông tin frame, trạng thái ffmpeg và lỗi được hiển thị tại đây.", bg="#202336", fg="#B5BED4", font=("Segoe UI", 9)).pack(anchor="w", pady=(2, 0))
        log_content = tk.Frame(log_card, bg="#161923", padx=2, pady=2)
        log_content.pack(fill="both", expand=True)
        self.log_text = tk.Text(log_content, wrap="word", height=24, state="disabled", bg="#161923", fg="#D5DEEF", insertbackground="white", relief="flat", font=("Cascadia Mono", 10))
        log_scroll = ttk.Scrollbar(log_content, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")

        self._on_mode_changed()

    def _add_path_row(
        self,
        parent: tk.Frame,
        row: int,
        variable: tk.StringVar,
        command,
        folder: bool = False,
    ) -> None:
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", pady=5)
        ttk.Button(parent, text="Chọn thư mục" if folder else "Chọn file", style="Browse.TButton", command=command).grid(
            row=row, column=2, sticky="e", padx=(8, 0), pady=5
        )

    @staticmethod
    def _add_compact_entry(
        parent: tk.Frame,
        column: int,
        label: str,
        variable: tk.StringVar,
        *,
        row: int,
    ) -> None:
        tk.Label(parent, text=f"{label}:", bg="#F7F8FC", fg="#4A5568", font=("Segoe UI", 9)).grid(
            row=row, column=column, sticky="w", padx=(0, 5), pady=2
        )
        ttk.Entry(parent, textvariable=variable, width=7).grid(
            row=row, column=column + 1, sticky="w", padx=(0, 14), pady=2
        )

    def _on_mode_changed(self) -> None:
        transparent = self.mode_var.get() == "transparent"
        self.input_label.configure(
            text="Video tham chiếu (không bắt buộc):" if transparent else "Video đầu vào:"
        )
        output = self.output_var.get().strip()
        if output:
            desired_extension = ".mov" if transparent else ".mp4"
            self.output_var.set(str(Path(output).with_suffix(desired_extension)))

    def _browse_input(self) -> None:
        path = filedialog.askopenfilename(
            title="Chọn video",
            filetypes=[("Video", "*.mp4 *.mov *.mkv *.avi *.webm"), ("Tất cả", "*.*")],
        )
        if path:
            self.input_var.set(path)
            current_output = self.output_var.get().strip()
            if not current_output or Path(current_output).parent == EFFECTS_DIR:
                source = Path(path)
                suffix = ".mov" if self.mode_var.get() == "transparent" else ".mp4"
                self.output_var.set(str(EFFECTS_DIR / f"{source.stem}_bubbles{suffix}"))

    def _browse_output(self) -> None:
        transparent = self.mode_var.get() == "transparent"
        extension = ".mov" if transparent else ".mp4"
        path = filedialog.asksaveasfilename(
            title="Chọn file xuất",
            initialdir=str(EFFECTS_DIR),
            initialfile=Path(self.output_var.get()).name,
            defaultextension=extension,
            filetypes=[("MOV nền trong suốt", "*.mov")] if transparent else [("MP4", "*.mp4")],
        )
        if path:
            # Chỉ nhận tên file: mọi đầu ra phải nằm trong scripts/hieuung.
            self.output_var.set(str(EFFECTS_DIR / Path(path).name))

    def _browse_image_dir(self) -> None:
        path = filedialog.askdirectory(title="Chọn thư mục ảnh cho bong bóng")
        if path:
            self.image_dir_var.set(path)

    @staticmethod
    def _float(value: str, name: str, minimum: float | None = None, maximum: float | None = None) -> float:
        try:
            result = float(value.strip())
        except ValueError as exc:
            raise ValueError(f"{name} phải là một số.") from exc
        if minimum is not None and result < minimum:
            raise ValueError(f"{name} phải lớn hơn hoặc bằng {minimum}.")
        if maximum is not None and result > maximum:
            raise ValueError(f"{name} phải nhỏ hơn hoặc bằng {maximum}.")
        return result

    @classmethod
    def _integer(cls, value: str, name: str, minimum: int = 1) -> int:
        result = cls._float(value, name, minimum)
        if not result.is_integer():
            raise ValueError(f"{name} phải là số nguyên.")
        return int(result)

    def _read_config(self) -> dict:
        mode = self.mode_var.get()
        image_dir = Path(self.image_dir_var.get().strip()).expanduser()
        if not image_dir.is_dir():
            raise ValueError("Thư mục ảnh không tồn tại.")

        input_text = self.input_var.get().strip()
        input_path = Path(input_text).expanduser() if input_text else None
        if mode == "burn" and (input_path is None or not input_path.is_file()):
            raise ValueError("Chế độ ghép trực tiếp cần một video đầu vào hợp lệ.")
        if mode == "burn" and self.until_images_var.get():
            raise ValueError(
                "Chế độ dùng hết ảnh cần chọn MOV nền trong suốt, vì MP4 ghép trực tiếp "
                "không thể dài hơn video gốc."
            )
        if mode == "transparent" and input_path is not None and not input_path.is_file():
            raise ValueError("Video tham chiếu không tồn tại.")

        output_text = self.output_var.get().strip()
        if not output_text:
            raise ValueError("Hãy chọn file xuất.")
        # Người dùng có thể gõ cả đường dẫn, nhưng đầu ra luôn bị cố định vào hieuung.
        output_path = EFFECTS_DIR / Path(output_text).name
        output_path = output_path.with_suffix(".mov" if mode == "transparent" else ".mp4")

        duration_text = self.duration_var.get().strip()
        duration = None if not duration_text else self._float(duration_text, "Độ dài", 0.1)
        size_min = self._integer(self.settings["size_min"].get(), "Cỡ ảnh nhỏ nhất")
        size_max = self._integer(self.settings["size_max"].get(), "Cỡ ảnh lớn nhất")
        tiny_min = self._integer(self.settings["tiny_min"].get(), "Cỡ bóng bé tý nhỏ nhất")
        tiny_max = self._integer(self.settings["tiny_max"].get(), "Cỡ bóng bé tý lớn nhất")
        if size_min > size_max or tiny_min > tiny_max:
            raise ValueError("Kích thước nhỏ nhất không được lớn hơn kích thước lớn nhất.")

        seed_text = self.settings["seed"].get().strip()
        try:
            seed = None if not seed_text else int(seed_text)
        except ValueError as exc:
            raise ValueError("Hạt ngẫu nhiên phải là số nguyên hoặc để trống.") from exc

        return {
            "mode": mode,
            "input_path": input_path,
            "output_path": output_path,
            "image_dir": image_dir,
            "duration": duration,
            "width": self._integer(self.width_var.get(), "Chiều rộng"),
            "height": self._integer(self.height_var.get(), "Chiều cao"),
            "fps": self._float(self.fps_var.get(), "FPS", 1.0),
            "spawn_rate": self._float(self.settings["spawn_rate"].get(), "Tần suất sinh", 0.01),
            "max_bubbles": self._integer(self.settings["max_bubbles"].get(), "Số bóng tối đa"),
            "fade_out": self._float(self.settings["fade_out"].get(), "Mờ tan cuối clip", 0.0),
            "slow_speed": self._float(self.settings["slow_speed"].get(), "Tốc độ chậm", 0.01),
            "fast_speed": self._float(self.settings["fast_speed"].get(), "Tốc độ nhanh", 0.01),
            "fast_frac": self._float(self.settings["fast_frac"].get(), "Tỷ lệ bóng nhanh", 0.0, 1.0),
            "drift_ratio": self._float(self.settings["drift_ratio"].get(), "Độ bay xéo", 0.0),
            "tiny_frac": self._float(self.settings["tiny_frac"].get(), "Tỷ lệ bóng bé tý", 0.0, 1.0),
            "size_min": size_min,
            "size_max": size_max,
            "tiny_min": tiny_min,
            "tiny_max": tiny_max,
            "shell_opacity": self._float(self.settings["shell_opacity"].get(), "Độ đục vỏ", 0.0, 1.0),
            "inner_opacity": self._float(self.settings["inner_opacity"].get(), "Độ rõ ảnh trong", 0.0, 1.0),
            "feature_in_random": self.feature_random_var.get(),
            "until_images_finish": self.until_images_var.get(),
            "seed": seed,
        }

    def _start_render(self) -> None:
        if self.running:
            return
        try:
            config = self._read_config()
        except ValueError as exc:
            messagebox.showerror("Thiếu hoặc sai dữ liệu", str(exc), parent=self.root)
            return

        missing = [name for name in (bubble.FFMPEG, bubble.FFPROBE) if shutil.which(name) is None]
        if missing:
            messagebox.showerror(
                "Thiếu ffmpeg",
                f"Không tìm thấy: {', '.join(missing)}. Hãy cài ffmpeg và thêm vào PATH.",
                parent=self.root,
            )
            return

        self.running = True
        self.render_button.configure(state="disabled")
        self.status_var.set("Đang render — không đóng cửa sổ này")
        self.status_label.configure(fg="#D97706")
        self._clear_log()
        self._append_log("Bắt đầu render...\n")
        threading.Thread(target=self._render_worker, args=(config,), daemon=True).start()

    @staticmethod
    def _configure_renderer(config: dict) -> None:
        bubble.RENDER_MODE = config["mode"]
        bubble.CLIP_SECONDS = config["duration"]
        bubble.OUTPUT_WIDTH = config["width"]
        bubble.OUTPUT_HEIGHT = config["height"]
        bubble.OUTPUT_FPS = config["fps"]
        bubble.SPAWN_RATE = config["spawn_rate"]
        bubble.MAX_BUBBLES = config["max_bubbles"]
        bubble.FADE_OUT_SEC = config["fade_out"]
        bubble.SLOW_SPEED = config["slow_speed"]
        bubble.FAST_SPEED = config["fast_speed"]
        bubble.FAST_FRAC = config["fast_frac"]
        bubble.DRIFT_RATIO = config["drift_ratio"]
        bubble.TINY_FRAC = config["tiny_frac"]
        bubble.SIZE_MIN = config["size_min"]
        bubble.SIZE_MAX = config["size_max"]
        bubble.TINY_MIN = config["tiny_min"]
        bubble.TINY_MAX = config["tiny_max"]
        bubble.SHELL_OPACITY = config["shell_opacity"]
        bubble.INNER_OPACITY = config["inner_opacity"]
        bubble.FEATURE_IN_RANDOM = config["feature_in_random"]
        bubble.RENDER_UNTIL_IMAGES_FINISH = config["until_images_finish"]
        bubble.SEED = config["seed"]

        # Nạp lại danh sách ảnh và bỏ cache sprite để lần render sau dùng đúng ảnh/tham số mới.
        bubble.IMAGE_DIR = str(config["image_dir"])
        bubble.IMAGES = bubble._load_image_paths()
        bubble.FEATURE_INDEX = next(
            (index for index, path in enumerate(bubble.IMAGES)
             if path.name.casefold() == bubble.FEATURE_IMAGE_NAME.casefold()),
            None,
        )
        bubble.RANDOM_IMAGE_INDICES = [
            index for index in range(len(bubble.IMAGES))
            if bubble.FEATURE_IN_RANDOM or index != bubble.FEATURE_INDEX
        ]
        bubble._SPRITE_CACHE.clear()

    def _render_worker(self, config: dict) -> None:
        writer = QueueWriter(self.events)
        try:
            with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
                self._configure_renderer(config)
                output_path = config["output_path"]
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path = bubble._unique_path(output_path)

                print(f"Ảnh trong bong bóng: {len(bubble.IMAGES)} file")
                print(f"File xuất: {output_path}")
                if config["mode"] == "transparent":
                    reference = config["input_path"] or Path("__no_video_reference__.mp4")
                    bubble.render_transparent_mov(output_path, reference)
                else:
                    bubble.render_onto_video(config["input_path"], output_path)
                self.events.put(("done", str(output_path)))
        except BaseException:
            self.events.put(("error", traceback.format_exc()))

    def _poll_events(self) -> None:
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "log":
                    self._append_log(value)
                elif kind == "done":
                    self.running = False
                    self.render_button.configure(state="normal")
                    self.status_var.set("Hoàn tất")
                    self.status_label.configure(fg="#15803D")
                    self._append_log(f"\nHoàn tất → {value}\n")
                    messagebox.showinfo("Hoàn tất", f"Đã tạo video:\n{value}", parent=self.root)
                elif kind == "error":
                    self.running = False
                    self.render_button.configure(state="normal")
                    self.status_var.set("Có lỗi")
                    self.status_label.configure(fg="#DC2626")
                    self._append_log(f"\nLỖI:\n{value}\n")
                    messagebox.showerror("Render thất bại", "Xem chi tiết tại tab Nhật ký.", parent=self.root)
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
            messagebox.showwarning("Đang render", "Render đang chạy. Hãy đợi hoàn tất trước khi đóng.", parent=self.root)
            return
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    BubbleVideoGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
