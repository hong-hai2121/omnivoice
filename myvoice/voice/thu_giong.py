# -*- coding: utf-8 -*-
"""
thu_giong.py — Thử nhanh các giọng mẫu trong thư mục voice/.

Chọn 1 giọng (hoặc tạo cho TẤT CẢ), nhập/dùng kịch bản mẫu sẵn rồi tạo audio
clone để NGHE THỬ xem giọng nào hợp. Chức năng giống "tạo giọng" nhưng gọn,
chỉ để so sánh giọng. Kết quả lưu ở voice/_thu_giong/<tên_giọng>.wav.

Chạy:  python thu_giong.py   (tự chuyển sang python của venv)
"""

import sys
import os

# ── Tự chuyển sang python của venv (giống các *_gui.py khác) ─────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))                      # myvoice/voice
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, os.pardir, os.pardir))  # OmniVoice (gốc repo)
_VENV_PYTHON = os.path.join(_REPO_ROOT, "venv", "Scripts", "python.exe")
if __name__ == "__main__" and os.path.exists(_VENV_PYTHON) and \
        os.path.normcase(os.path.abspath(sys.executable)) != \
        os.path.normcase(os.path.abspath(_VENV_PYTHON)):
    import subprocess
    subprocess.run([_VENV_PYTHON] + sys.argv)
    sys.exit()
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)   # để import được package omnivoice

import re
import queue
import shutil
import subprocess
import threading
import time
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

import numpy as np
import soundfile as sf

VOICE_DIR = Path(_HERE)                       # thư mục chứa giọng mẫu = chính thư mục này
OUT_DIR = VOICE_DIR / "_thu_giong"            # nơi lưu audio nghe thử
OUT_DIR.mkdir(exist_ok=True)
AUDIO_EXTS = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wma"}
CHUNK_SIZE = 300                              # ký tự tối đa mỗi đoạn khi tách

# ── NGHE THỬ THEO TỐC ĐỘ ────────────────────────────────────────────────────────
# Đổi tốc độ bằng ffmpeg atempo (GIỮ NGUYÊN cao độ, không bị "chipmunk" như cách
# đổi sample rate). File gốc trong _thu_giong/ KHÔNG bị đụng — bản đổi tốc độ để
# riêng ở _thu_giong/_tocdo/ và có cache theo từng mức tốc độ.
FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
SPEED_DIR = OUT_DIR / "_tocdo"
SPEED_MIN, SPEED_MAX, SPEED_STEP = 0.75, 1.60, 0.05

# Kịch bản mẫu để thử giọng (sửa tay thoải mái) — có câu kể, câu hỏi để nghe ngữ điệu.
DEFAULT_SCRIPT = (
    "Chào bạn, hôm nay trời khá đẹp, nắng nhẹ và gió mát. "
    "Tôi vừa đi dạo một vòng quanh hồ, ngắm mấy chú chim sẻ đậu trên cành, "
    "cảm giác thật sự dễ chịu."
)

UI = dict(
    bg="#ffffff", fg="#1f2430", muted="#7b828f",
    accent="#e84393", accent_dk="#c92f7b",
    field="#ffffff", border="#e4e7ec", hover="#f1f3f6",
    log_bg="#fbfbfc", log_info="#475063", log_warn="#b07400", log_err="#d62828", ok="#1f9d55",
)

SPLIT_CHARS = re.compile(r"(?<=[.!?。！？\n])\s*")


def list_voices():
    """Danh sách file giọng mẫu trong thư mục (bỏ qua thư mục con _thu_giong)."""
    if not VOICE_DIR.exists():
        return []
    return sorted(f.name for f in VOICE_DIR.iterdir()
                  if f.is_file() and f.suffix.lower() in AUDIO_EXTS)


def split_chunks(text, max_len=CHUNK_SIZE):
    """Tách text thành các đoạn <= max_len ký tự, ưu tiên cắt ở cuối câu."""
    parts = SPLIT_CHARS.split(text)
    chunks, cur = [], ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if len(cur) + len(part) + 1 <= max_len:
            cur = (cur + " " + part).strip()
        else:
            if cur:
                chunks.append(cur)
            cur = part
    if cur:
        chunks.append(cur)
    return chunks or [text.strip()]


def safe_stem(name: str) -> str:
    """Bỏ phần đuôi + ký tự không hợp lệ để đặt tên file kết quả."""
    return re.sub(r"[^\w\-. ]+", "_", Path(name).stem).strip() or "giong"


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("Thử giọng — OmniVoice")
        root.configure(bg=UI["bg"])
        self._center(root, 940, 620)
        root.minsize(820, 540)

        self._busy = False
        self._playing = False
        self._last_src = None       # file wav GỐC vừa phát (để đổi tốc độ phát lại)
        self._play_until = 0.0      # mốc thời gian dự kiến phát xong (winsound không báo)
        self._model = None          # nạp 1 lần, dùng lại
        self._sr = None
        self.q = queue.Queue()      # (kind, payload) từ thread nền

        self._build_styles()
        self._build_ui()
        self._reload_voices()
        self.root.after(120, self._poll)

    # ── tiện ích ──
    def _center(self, root, w, h):
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f"{w}x{h}+{max((sw - w)//2, 0)}+{max((sh - h)//3, 0)}")

    def _build_styles(self):
        st = ttk.Style()
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        C = UI
        st.configure("TFrame", background=C["bg"])
        st.configure("TLabel", background=C["bg"], foreground=C["fg"], font=("Segoe UI", 10))
        st.configure("Title.TLabel", background=C["bg"], foreground=C["accent_dk"],
                     font=("Segoe UI Semibold", 16))
        st.configure("Muted.TLabel", background=C["bg"], foreground=C["muted"], font=("Segoe UI", 9))
        st.configure("TButton", padding=(12, 7), font=("Segoe UI", 10))
        st.configure("Accent.TButton", foreground="#ffffff", background=C["accent"],
                     padding=(16, 9), font=("Segoe UI", 10, "bold"))
        st.map("Accent.TButton", background=[("active", C["accent_dk"]), ("disabled", "#f0a8c6")])

    def _build_ui(self):
        pad = dict(padx=16)
        ttk.Label(self.root, text="🎚️  Thử giọng — chọn giọng + kịch bản mẫu để nghe",
                  style="Title.TLabel").pack(anchor="w", pady=(14, 2), **pad)
        ttk.Label(self.root, text="Tạo audio clone ngắn để so sánh xem giọng nào hợp. "
                                  "Kết quả lưu ở voice/_thu_giong/.",
                  style="Muted.TLabel").pack(anchor="w", pady=(0, 10), **pad)

        body = ttk.Frame(self.root)
        body.pack(fill="both", expand=True, **pad)
        body.columnconfigure(0, weight=0, minsize=300)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        # ── Trái: danh sách giọng ──
        left = ttk.LabelFrame(body, text="  Giọng mẫu  ", padding=10)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        self.listbox = tk.Listbox(left, activestyle="dotbox", font=("Segoe UI", 10),
                                  bg=UI["field"], fg=UI["fg"], selectbackground=UI["accent"],
                                  selectforeground="#ffffff", relief="flat",
                                  highlightthickness=1, highlightbackground=UI["border"])
        self.listbox.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(left, orient="vertical", command=self.listbox.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.listbox.configure(yscrollcommand=sb.set)
        self.listbox.bind("<Double-Button-1>", lambda _e: self._on_make_one())
        ttk.Button(left, text="↻ Tải lại danh sách",
                   command=self._reload_voices).grid(row=1, column=0, columnspan=2,
                                                     sticky="ew", pady=(8, 0))

        # ── Phải: kịch bản + nút + log ──
        right = ttk.Frame(body)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(4, weight=1)

        ttk.Label(right, text="Kịch bản thử (sửa tay được):",
                  style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        self.txt = tk.Text(right, height=5, wrap="word", font=("Segoe UI", 11),
                           bg=UI["field"], fg=UI["fg"], relief="flat", borderwidth=0,
                           highlightthickness=1, highlightbackground=UI["border"],
                           highlightcolor=UI["accent"], padx=10, pady=8)
        self.txt.grid(row=1, column=0, sticky="ew", pady=(4, 10))
        self.txt.insert("1.0", DEFAULT_SCRIPT)

        actions = ttk.Frame(right)
        actions.grid(row=2, column=0, sticky="ew")
        self.btn_make = ttk.Button(actions, text="🔊  Tạo & nghe giọng đã chọn",
                                   style="Accent.TButton", command=self._on_make_one)
        self.btn_make.pack(side="left")
        self.btn_play = ttk.Button(actions, text="▶  Nghe lại", command=self._on_play_saved)
        self.btn_play.pack(side="left", padx=(8, 0))
        self.btn_stop = ttk.Button(actions, text="⏹  Dừng", command=self._stop_play)
        self.btn_stop.pack(side="left", padx=(8, 0))
        self.btn_all = ttk.Button(actions, text="🔁  Tạo cho TẤT CẢ giọng",
                                  command=self._on_make_all)
        self.btn_all.pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="📁  Mở thư mục kết quả",
                   command=self._open_out).pack(side="right")

        # ── Tốc độ nghe thử ──
        speed_row = ttk.Frame(right)
        speed_row.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        ttk.Label(speed_row, text="⏩  Tốc độ nghe:").pack(side="left")
        ttk.Button(speed_row, text="−", width=3,
                   command=lambda: self._bump_speed(-SPEED_STEP)).pack(side="left", padx=(8, 0))
        self.var_speed = tk.DoubleVar(value=1.0)
        self.scale_speed = ttk.Scale(speed_row, from_=SPEED_MIN, to=SPEED_MAX, length=280,
                                     orient="horizontal", variable=self.var_speed,
                                     command=lambda _v: self._update_speed_label())
        self.scale_speed.pack(side="left", padx=6)
        self.scale_speed.bind("<ButtonRelease-1>", self._on_speed_release)
        ttk.Button(speed_row, text="+", width=3,
                   command=lambda: self._bump_speed(SPEED_STEP)).pack(side="left")
        self.lbl_speed = ttk.Label(speed_row, text="1.00×", width=6,
                                   font=("Segoe UI Semibold", 11))
        self.lbl_speed.pack(side="left", padx=(10, 0))
        ttk.Button(speed_row, text="↺ 1.0×", width=8,
                   command=lambda: self._set_speed(1.0)).pack(side="left", padx=(6, 0))
        ttk.Label(speed_row, text="giữ nguyên cao độ  •  file gốc không đổi",
                  style="Muted.TLabel").pack(side="left", padx=(12, 0))

        self.status = tk.StringVar(value="Sẵn sàng.")
        ttk.Label(right, textvariable=self.status, style="Muted.TLabel").grid(
            row=5, column=0, sticky="w", pady=(8, 2))
        self.pb = ttk.Progressbar(right, mode="determinate", maximum=100)
        self.pb.grid(row=6, column=0, sticky="ew")

        logf = ttk.LabelFrame(right, text="  Nhật ký  ", padding=6)
        logf.grid(row=4, column=0, sticky="nsew", pady=(10, 6))
        logf.rowconfigure(0, weight=1)
        logf.columnconfigure(0, weight=1)
        self.logbox = scrolledtext.ScrolledText(logf, height=7, wrap="word", state="disabled",
                                                font=("Consolas", 9), relief="flat", borderwidth=0,
                                                bg=UI["log_bg"], fg=UI["log_info"], padx=8, pady=6)
        self.logbox.grid(row=0, column=0, sticky="nsew")
        for tag, color in [("info", UI["log_info"]), ("warn", UI["log_warn"]),
                           ("err", UI["log_err"]), ("ok", UI["ok"])]:
            self.logbox.tag_config(tag, foreground=color)

    # ── danh sách giọng ──
    def _reload_voices(self):
        voices = list_voices()
        self.listbox.delete(0, "end")
        for v in voices:
            self.listbox.insert("end", v)
        if voices:
            self.listbox.selection_set(0)
        self.status.set(f"Có {len(voices)} giọng trong {VOICE_DIR.name}/.")

    def _selected_voice(self):
        sel = self.listbox.curselection()
        return self.listbox.get(sel[0]) if sel else None

    # ── log / queue ──
    def _log(self, msg, level="info"):
        self.q.put(("log", (level, str(msg))))

    def _set_status(self, text):
        self.q.put(("status", text))

    def _set_prog(self, pct):
        self.q.put(("prog", pct))

    def _poll(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    level, msg = payload
                    self.logbox.config(state="normal")
                    self.logbox.insert("end", msg + "\n", level)
                    self.logbox.see("end")
                    self.logbox.config(state="disabled")
                elif kind == "status":
                    self.status.set(payload)
                elif kind == "prog":
                    self.pb["value"] = payload
                elif kind == "done":
                    self._set_busy(False)
                    play = payload
                    if play and Path(play).exists():
                        self._play_file(Path(play))
        except queue.Empty:
            pass
        self.root.after(120, self._poll)

    def _set_busy(self, busy):
        self._busy = busy
        state = "disabled" if busy else "normal"
        for b in (self.btn_make, self.btn_all, self.btn_play):
            b.config(state=state)

    # ── model ──
    def _ensure_model(self):
        """Nạp model OmniVoice 1 lần (lần đầu sẽ chậm), giữ lại cho các lượt sau."""
        if self._model is not None:
            return
        import torch
        from omnivoice.models.omnivoice import OmniVoice
        from omnivoice.utils.common import get_best_device
        device = get_best_device()
        self._log(f"📦 Đang tải model OmniVoice (device={device})... lần đầu hơi lâu.")
        self._set_status("Đang tải model...")
        self._model = OmniVoice.from_pretrained(
            "k2-fsa/OmniVoice", device_map=device, dtype=torch.float16)
        self._sr = self._model.sampling_rate
        self._log("✅ Đã tải model.", "ok")

    @staticmethod
    def _don_vram():
        """gc + empty_cache. Chỉ gọi khi đã bỏ HẾT tham chiếu tới thứ cần xả —
        dọn lúc model còn sống thì torch chẳng trả được khối nào cho driver."""
        import gc
        gc.collect()
        try:
            import torch
            torch.cuda.empty_cache()
        except Exception:
            pass

    def _xa_whisper_con(self):
        """Xả Whisper mà OmniVoice tự nạp để phiên âm giọng mẫu (~1.6 GB fp16).

        generate(ref_audio=...) không kèm ref_text nên OmniVoice nạp
        whisper-large-v3-turbo để nghe file giọng mẫu, xong rồi nằm lì trong VRAM
        tới khi tắt app. Gọi sau khi tạo xong CẢ LƯỢT (không gọi giữa các đoạn —
        đoạn kế lại phải nạp lại). Tham chiếu duy nhất nằm ở thuộc tính này nên
        gán None là chết hẳn, dọn ngay sau đó trả được thật.
        """
        if getattr(self._model, "_asr_pipe", None) is None:
            return
        self._model._asr_pipe = None
        self._don_vram()
        self._log("🧹 Đã xả Whisper phiên âm giọng mẫu khỏi VRAM (~1.6 GB).")

    def _nha_model(self):
        """Nhả hẳn OmniVoice khỏi VRAM (đóng cửa sổ). Bấm tạo lại thì tự nạp lại.

        Bỏ tham chiếu TRƯỚC (self._model = None) rồi mới dọn — làm ngược thứ tự
        thì trọng số vẫn còn sống, dọn xong không trả được gì cho driver.
        """
        if self._model is None:
            return
        self._xa_whisper_con()
        self._model = None
        self._don_vram()

    def _synthesize(self, text, voice_path):
        """Sinh audio clone cho 1 giọng; ghép các đoạn nếu kịch bản dài."""
        chunks = split_chunks(text.strip().lower())
        parts = []
        for j, c in enumerate(chunks):
            self._set_status(f"Đang tạo đoạn {j + 1}/{len(chunks)}...")
            parts.append(self._model.generate(text=c, ref_audio=str(voice_path))[0])
        return np.concatenate(parts) if len(parts) > 1 else parts[0]

    # ── tạo cho 1 giọng ──
    def _on_make_one(self):
        if self._busy:
            return
        voice = self._selected_voice()
        if not voice:
            messagebox.showwarning("Chưa chọn giọng", "Hãy chọn một giọng trong danh sách.")
            return
        text = self.txt.get("1.0", "end").strip()
        if not text:
            messagebox.showwarning("Thiếu kịch bản", "Hãy nhập kịch bản thử.")
            return
        self._stop_play()
        self._set_busy(True)
        self.pb["value"] = 0
        threading.Thread(target=self._worker_one, args=(voice, text), daemon=True).start()

    def _worker_one(self, voice, text):
        out = None
        try:
            self._ensure_model()
            self._log(f"🎙️ Thử giọng: {voice}")
            audio = self._synthesize(text, VOICE_DIR / voice)
            out = OUT_DIR / f"{safe_stem(voice)}.wav"
            sf.write(str(out), audio, self._sr)
            self.pb["value"] = 100
            self._log(f"✅ Xong → {out.name} (nghe thử ngay).", "ok")
            self._set_status(f"Xong: {voice} → đang phát...")
        except Exception as e:
            self._log(f"❌ Lỗi: {e}", "err")
            self._log(traceback.format_exc(), "err")
            self._set_status(f"Lỗi: {e}")
            out = None
        finally:
            self._xa_whisper_con()   # xong lượt → Whisper hết việc, trả VRAM
            self.q.put(("done", str(out) if out else None))

    # ── tạo cho tất cả giọng ──
    def _on_make_all(self):
        if self._busy:
            return
        voices = list_voices()
        if not voices:
            messagebox.showwarning("Không có giọng", f"Không thấy giọng nào trong {VOICE_DIR}.")
            return
        text = self.txt.get("1.0", "end").strip()
        if not text:
            messagebox.showwarning("Thiếu kịch bản", "Hãy nhập kịch bản thử.")
            return
        if not messagebox.askyesno(
                "Tạo cho tất cả",
                f"Sẽ tạo audio thử cho TẤT CẢ {len(voices)} giọng.\n"
                "Có thể mất một lúc. Xong rồi chọn từng giọng bấm '▶ Nghe lại' để so sánh.\n\nTiếp tục?"):
            return
        self._stop_play()
        self._set_busy(True)
        self.pb["value"] = 0
        threading.Thread(target=self._worker_all, args=(voices, text), daemon=True).start()

    def _worker_all(self, voices, text):
        try:
            self._ensure_model()
            total = len(voices)
            for k, voice in enumerate(voices):
                self._log(f"[{k + 1}/{total}] 🎙️ {voice}")
                try:
                    audio = self._synthesize(text, VOICE_DIR / voice)
                    out = OUT_DIR / f"{safe_stem(voice)}.wav"
                    sf.write(str(out), audio, self._sr)
                    self._log(f"   ✅ → {out.name}", "ok")
                except Exception as e:
                    self._log(f"   ❌ {voice}: {e}", "err")
                self._set_prog(int((k + 1) / total * 100))
            self._set_status(f"Xong tất cả {total} giọng. Chọn giọng + '▶ Nghe lại' để so sánh.")
            self._log("🎉 Hoàn thành tạo cho tất cả giọng.", "ok")
        except Exception as e:
            self._log(f"❌ Lỗi: {e}", "err")
            self._set_status(f"Lỗi: {e}")
        finally:
            self._xa_whisper_con()   # xong cả mẻ → Whisper hết việc, trả VRAM
            self.q.put(("done", None))

    # ── tốc độ nghe thử ──
    def _speed(self) -> float:
        """Tốc độ đang chọn, đã làm tròn về bội của SPEED_STEP (1.05, 1.10, 1.15...)."""
        v = round(self.var_speed.get() / SPEED_STEP) * SPEED_STEP
        return round(min(SPEED_MAX, max(SPEED_MIN, v)), 2)

    def _update_speed_label(self):
        self.lbl_speed.config(text=f"{self._speed():.2f}×")

    def _set_speed(self, value: float):
        self.var_speed.set(min(SPEED_MAX, max(SPEED_MIN, value)))
        self._update_speed_label()
        self._on_speed_release()

    def _bump_speed(self, delta: float):
        self._set_speed(self._speed() + delta)

    def _on_speed_release(self, _e=None):
        """Nhả chuột / bấm ±: nếu đang phát dở thì phát lại luôn ở tốc độ mới để so sánh."""
        self._update_speed_label()
        if self._is_playing() and self._last_src and self._last_src.exists():
            self._play_file(self._last_src)

    def _is_playing(self) -> bool:
        """winsound không báo khi phát xong → ước lượng bằng độ dài file."""
        return self._playing and time.monotonic() < self._play_until

    def _speed_file(self, src: Path, speed: float) -> Path:
        """Bản đổi tốc độ (giữ cao độ) của `src` — dùng lại nếu đã render và còn mới."""
        SPEED_DIR.mkdir(exist_ok=True)
        dst = SPEED_DIR / f"{src.stem}@{speed:.2f}x.wav"
        if dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
            return dst
        proc = subprocess.run(
            [FFMPEG, "-y", "-loglevel", "error", "-i", str(src),
             "-filter:a", f"atempo={speed:.3f}", str(dst)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if proc.returncode != 0 or not dst.exists():
            raise RuntimeError((proc.stderr or "ffmpeg lỗi không rõ").strip()[-300:])
        return dst

    # ── phát lại ──
    def _on_play_saved(self):
        voice = self._selected_voice()
        if not voice:
            messagebox.showwarning("Chưa chọn giọng", "Hãy chọn một giọng để nghe lại.")
            return
        f = OUT_DIR / f"{safe_stem(voice)}.wav"
        if not f.exists():
            messagebox.showinfo("Chưa có bản thử",
                                f"Chưa tạo bản thử cho '{voice}'.\nBấm '🔊 Tạo & nghe' trước.")
            return
        self._play_file(f)

    def _play_file(self, path: Path):
        """Phát `path` (file GỐC) ở tốc độ đang chọn; file gốc không bị sửa."""
        self._stop_play()
        self._last_src = path
        speed = self._speed()
        play_path = path
        if abs(speed - 1.0) > 1e-6:
            self.status.set(f"⏩ Đang đổi tốc độ {speed:.2f}×...")
            self.root.update_idletasks()
            try:
                play_path = self._speed_file(path, speed)
            except Exception as e:
                self._log(f"⚠️ Không đổi được tốc độ ({e}) → phát ở 1.00×.", "warn")
                speed = 1.0
        try:
            duration = sf.info(str(play_path)).duration
        except Exception:
            duration = 0.0
        try:
            import winsound
            winsound.PlaySound(str(play_path), winsound.SND_FILENAME | winsound.SND_ASYNC)
            self._playing = True
            self._play_until = time.monotonic() + duration + 0.3
            self.status.set(f"▶ Đang phát: {path.name}  ({speed:.2f}×, {duration:.1f}s)")
        except Exception:
            try:
                os.startfile(str(play_path))  # type: ignore[attr-defined]
            except Exception as e:
                messagebox.showerror("Lỗi phát audio", str(e))

    def _stop_play(self):
        try:
            import winsound
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass
        self._playing = False
        self._play_until = 0.0

    def _open_out(self):
        try:
            os.startfile(str(OUT_DIR))  # type: ignore[attr-defined]
        except Exception:
            self.status.set(f"Thư mục kết quả: {OUT_DIR}")


def main():
    root = tk.Tk()
    app = App(root)

    # Nhả model TRƯỚC khi Tk đóng: để CUDA tự dọn lúc trình thông dịch thoát thì
    # thi thoảng treo/nổ lỗi driver trên Windows, mà máy chấm dứt tiến trình chậm
    # thì card vẫn kẹt vài GB trong lúc bên kia (tạo giọng, dựng video) đang chờ.
    def _thoat():
        try:
            app._nha_model()
        except Exception:
            pass
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", _thoat)
    root.mainloop()


if __name__ == "__main__":
    main()
