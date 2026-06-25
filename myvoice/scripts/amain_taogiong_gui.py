"""
Giao diện desktop cho Voice Cloning — chạy: python taogiong_gui.py
"""

import sys, os
# Gốc repo OmniVoice (chứa package omnivoice + venv) — lùi 2 cấp từ myvoice/scripts/
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
_VENV_PYTHON = os.path.join(_REPO_ROOT, "venv", "Scripts", "python.exe")
if os.path.exists(_VENV_PYTHON) and os.path.abspath(sys.executable) != os.path.abspath(_VENV_PYTHON):
    import subprocess
    subprocess.run([_VENV_PYTHON] + sys.argv)
    sys.exit()
# Để import được package omnivoice ở gốc repo dù chạy từ thư mục con
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
# Để import được video_khung.py nằm cùng thư mục scripts/
_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import re
import hashlib
import threading
import logging
import queue
import numpy as np
import soundfile as sf
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
from pathlib import Path


BASE_DIR   = Path(__file__).resolve().parent.parent   # myvoice/
VOICE_DIR  = BASE_DIR / "voice"
SCRIPT_DIR = BASE_DIR / "kịch_bản"
OUTPUT_DIR = SCRIPT_DIR / "output"                    # nơi gom mọi kết quả (wav + video + chunks)
GEMINI_DOCX = SCRIPT_DIR / "gemini_result.docx"       # kết quả dịch Gemini → nguồn nội dung TTS
CHINESE_DOCX = SCRIPT_DIR / "tiengTrung.docx"         # văn bản tiếng Trung (nguồn để dịch Gemini)
PREFIX_FILE = Path(__file__).resolve().parent / "copy_prefix.txt"  # câu mở đầu dịch (chèn đoạn 1)
FAV_FILE   = BASE_DIR / "voice_favorites.json"        # danh sách giọng mẫu yêu thích
EFFECT_FAV_FILE = BASE_DIR / "effect_favorites.json"  # danh sách hiệu ứng yêu thích (★)
PIPE_FILE  = BASE_DIR / "taogiong_pipeline.json"      # cài đặt quy trình tạo kịch bản (auto + model/tốc độ)
OPTS_FILE  = BASE_DIR / "taogiong_options.json"        # cài đặt mục "Cài đặt" (nhớ lần chạy trước)
# Mặc định quy trình: ① tự chạy ②, ② tự chạy ③, ③ tự chạy tạo giọng (OmniVoice)
PIPE_DEFAULTS = dict(auto2=True, auto3=True, auto_tts=True, model="medium", speed="0.7")
AUDIO_EXTS = {".mp3", ".wav", ".MP3", ".WAV", ".flac", ".FLAC"}
STAR       = "★ "                                     # tiền tố hiển thị cho giọng yêu thích

# Kho hiệu ứng phủ lên video (scripts/hieuung/) — thường là .mov có alpha
EFFECTS_DIR = Path(__file__).resolve().parent / "hieuung"
EFFECT_EXTS = {".mov", ".mp4", ".webm", ".mkv", ".avi", ".gif"}
EFFECT_NONE = "Không (mặc định)"                       # mục "không thêm hiệu ứng"
DEFAULT_EFFECT = "bubbles_overlay_6.mov"               # hiệu ứng chọn sẵn nếu có trong hieuung/

# Mặc định mục "Cài đặt" (dùng khi chưa có taogiong_options.json) — sau đó được
# ghi đè bằng giá trị của LẦN CHẠY TRƯỚC để mỗi lần mở giữ lại lựa chọn cũ.
OPTS_DEFAULTS = dict(
    from_gemini=True, chunk=300,
    make_video=True, ngang_speed="1.0", effect=DEFAULT_EFFECT,
    cut_audio=True, cut_target=12.0, cut_min=10.0, cut_max=15.0, cut_half=False,
    make_video_doc=True, doc_full_audio=False, doc_speed="1.0", doc_from_ngang=False,
    doc_no_effect=False,
)

# ── BẢNG MÀU GIAO DIỆN (nền trắng) ───────────────────────────────────────────
UI = dict(
    bg="#ffffff", card="#ffffff", border="#e4e7ec", field="#ffffff",
    fg="#1f2430", muted="#7b828f",
    accent="#e84393", accent_dk="#c92f7b", accent_soft="#f4c4dc",
    track="#edeff2", hover="#f1f3f6", press="#e6e9ee",
    log_bg="#fbfbfc", log_info="#475063", log_warn="#b07400", log_err="#d62828",
)

SCRIPT_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

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


def list_effect_files():
    """Danh sách file hiệu ứng trong scripts/hieuung/ (chỉ tên file)."""
    if not EFFECTS_DIR.exists():
        return []
    return sorted(f.name for f in EFFECTS_DIR.iterdir()
                  if f.is_file() and f.suffix.lower() in EFFECT_EXTS)


def strip_star(label: str) -> str:
    """Bỏ tiền tố ★ để lấy lại tên file thật từ chuỗi hiển thị trong combobox."""
    return label[len(STAR):] if label.startswith(STAR) else label


def load_favorites() -> set:
    try:
        import json
        return set(json.loads(FAV_FILE.read_text(encoding="utf-8")))
    except Exception:
        return set()


def save_favorites(favorites: set):
    import json
    try:
        FAV_FILE.write_text(
            json.dumps(sorted(favorites), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        logging.warning(f"Không lưu được danh sách yêu thích: {e}")


def load_effect_favorites() -> set:
    try:
        import json
        return set(json.loads(EFFECT_FAV_FILE.read_text(encoding="utf-8")))
    except Exception:
        return set()


def save_effect_favorites(favorites: set):
    import json
    try:
        EFFECT_FAV_FILE.write_text(
            json.dumps(sorted(favorites), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        logging.warning(f"Không lưu được hiệu ứng yêu thích: {e}")


def load_pipe_settings() -> dict:
    """Cài đặt quy trình tạo kịch bản đã lưu (auto + model/tốc độ); thiếu thì dùng mặc định."""
    data = dict(PIPE_DEFAULTS)
    try:
        import json
        data.update(json.loads(PIPE_FILE.read_text(encoding="utf-8")))
    except Exception:
        pass
    return data


def save_pipe_settings(data: dict):
    import json
    try:
        PIPE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    except Exception as e:
        logging.warning(f"Không lưu được cài đặt quy trình: {e}")


def load_opt_settings() -> dict:
    """Cài đặt mục 'Cài đặt' đã lưu (mặc định dựa vào lần chạy trước); thiếu thì dùng mặc định."""
    data = dict(OPTS_DEFAULTS)
    try:
        import json
        data.update(json.loads(OPTS_FILE.read_text(encoding="utf-8")))
    except Exception:
        pass
    return data


def save_opt_settings(data: dict):
    import json
    try:
        OPTS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    except Exception as e:
        logging.warning(f"Không lưu được cài đặt: {e}")


def load_prefix() -> str:
    """Câu mở đầu dịch (copy_prefix.txt, dùng chung với GUI nhận diện); chưa có thì rỗng."""
    try:
        if PREFIX_FILE.exists():
            return PREFIX_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        pass
    return ""


def read_chinese_docx_chunks(path) -> list[str]:
    """Đọc nội dung tiếng Trung (bỏ Heading/Title), tách đoạn như khi nhận diện."""
    from docx import Document
    import nhandien_giongnoi as recog
    doc = Document(str(path))
    parts = [p.text.strip() for p in doc.paragraphs
             if p.text.strip() and not (p.style.name or "").startswith(("Heading", "Title"))]
    return recog.split_into_chunks("".join(parts))


# ── QUEUE ĐỂ TRUYỀN LOG TỪ THREAD VỀ GUI ───────────────────────────────────
log_queue = queue.Queue()


class QueueHandler(logging.Handler):
    def emit(self, record):
        log_queue.put((record.levelno, self.format(record)))


# ── LOGIC CLONE ──────────────────────────────────────────────────────────────
# ── PHÁT HIỆN SPIKE ──────────────────────────────────────────────────────────
_SPIKE_RATIO  = 5.0   # khung vượt N× median RMS → spike
_SILENT_RMS   = 0.005 # median quá thấp = gần im lặng
_FRAME_MS     = 50    # độ dài mỗi khung phân tích (ms)


def detect_spike(path: Path, sr: int) -> list[float]:
    """Trả về danh sách thời điểm (giây) bị spike, rỗng nếu OK."""
    data, _ = sf.read(str(path), dtype="float32", always_2d=False)
    if data.ndim > 1:
        data = data.mean(axis=1)
    frame = int(sr * _FRAME_MS / 1000)
    frames = [data[i:i+frame] for i in range(0, len(data) - frame, frame)]
    if not frames:
        return [0.0]
    rms = np.array([np.sqrt(np.mean(f**2)) for f in frames])
    median = float(np.median(rms))
    if median < _SILENT_RMS:
        return [0.0]
    threshold = _SPIKE_RATIO * max(median, 1e-4)
    bad = np.where(rms > threshold)[0]
    return [round(float(t) * _FRAME_MS / 1000, 2) for t in bad]


# ── TÁCH LOGIC GENERATE 1 CHUNK ───────────────────────────────────────────────
def _generate_chunk(model, mode, voice_param, chunk):
    if mode == "clone":
        return model.generate(text=chunk, ref_audio=voice_param)
    elif mode == "design":
        return model.generate(text=chunk, instruct=voice_param)
    return model.generate(text=chunk)


SPLIT_CHARS = re.compile(r'(?<=[.!?。！？\n])\s*')

# Ký tự thay bằng khoảng trắng (tránh ghép từ)
_REPLACE_WITH_SPACE = re.compile(r'[—–\-]+')
# Ký tự xóa hoàn toàn
_REMOVE = re.compile(r'["""\'\'\'`~@#$%^&*_+=|\\<>\[\]{}]')
# Dấu ba chấm → dấu chấm
_ELLIPSIS = re.compile(r'…+|\.{2,}')
# Nhiều khoảng trắng → 1
_SPACES = re.compile(r'[ \t]+')


def clean_text(text: str) -> str:
    text = _ELLIPSIS.sub('.', text)
    text = _REPLACE_WITH_SPACE.sub(' ', text)
    text = _REMOVE.sub('', text)
    text = _SPACES.sub(' ', text)
    return text.strip()


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


# ── THAY CÂU QUẢNG BÁ KÊNH THEO VỊ TRÍ ────────────────────────────────────────
# Gemini dịch mọi câu quảng bá kênh thành câu chứa tên kênh "Mimi Truyện". Tùy vị
# trí trong bài (mở đầu / thân bài / kết bài) ta thay bằng 3 câu khác nhau dưới
# đây. SỬA 3 CÂU NÀY nếu muốn đổi lời.
PROMO_OPENING = "lại là mimi truyện đây, mời bạn nghe câu truyện hôm nay."
PROMO_BODY    = "bạn đang nghe tại mimi truyện."
PROMO_ENDING  = ("Cảm ơn bạn đã lắng nghe truyện, đây là câu truyện không có thật "
                 "ở trung quốc xin chào và hẹn gặp lại.")

# Câu quảng bá luôn chứa tên kênh "Mimi Truyện" → dùng cả cụm làm dấu hiệu nhận
# biết (tránh khớp nhầm từ "mimi" lẻ); cho phép biến thể "chuyện".
_PROMO_MARKER = re.compile(r'mimi\s+(?:truyện|chuyện)', re.IGNORECASE)
# Tách câu nhưng GIỮ dấu kết câu/xuống dòng ở cuối mỗi mảnh để ghép lại nguyên trạng.
_PROMO_SENT_SPLIT = re.compile(r'(?<=[.!?。！？\n])')


def replace_channel_promo(text: str) -> tuple[str, int]:
    """Thay câu quảng bá kênh (chứa 'mimi') bằng 1 trong 3 câu theo vị trí:
    xuất hiện ĐẦU TIÊN → mở đầu, CUỐI CÙNG → kết bài, Ở GIỮA → thân bài.
    Nếu chỉ có 1 câu: nửa đầu văn bản → mở đầu, nửa cuối → kết bài.

    Trả về (text_đã_thay, số_câu_đã_thay). Giữ nguyên khoảng trắng/xuống dòng quanh
    câu để không phá cấu trúc đoạn.
    """
    sentences = _PROMO_SENT_SPLIT.split(text)
    promo_idx = [i for i, s in enumerate(sentences) if _PROMO_MARKER.search(s)]
    if not promo_idx:
        return text, 0
    first, last, n = promo_idx[0], promo_idx[-1], len(sentences)
    for i in promo_idx:
        orig = sentences[i]
        lead = orig[:len(orig) - len(orig.lstrip())]   # khoảng trắng đầu câu
        trail = orig[len(orig.rstrip()):]              # khoảng trắng/\n cuối câu
        if len(promo_idx) == 1:
            repl = PROMO_OPENING if i < n / 2 else PROMO_ENDING
        elif i == first:
            repl = PROMO_OPENING
        elif i == last:
            repl = PROMO_ENDING
        else:
            repl = PROMO_BODY
        sentences[i] = lead + repl + trail
    return "".join(sentences), len(promo_idx)


def chunks_dir_for(output_path: Path) -> Path:
    """Thư mục chunks dùng chung cho mọi bản đánh số (output, output1, output2…).

    Bỏ phần số đuôi của tên file để các lần chạy ghi vào CÙNG một thư mục
    (output_chunks), tránh tạo output1_chunks, output2_chunks… mỗi lần và
    giữ được khả năng tái dùng/“resume” chunk đã tạo.
    """
    stem = output_path.stem
    base = re.match(r"^(.*?)(\d*)$", stem).group(1) or stem
    return output_path.parent / (base + "_chunks")


def unique_path(path: Path) -> Path:
    """Nếu file đã tồn tại, trả về tên mới tăng số: output.wav → output1.wav → output2.wav…"""
    if not path.exists():
        return path
    m = re.match(r"^(.*?)(\d*)$", path.stem)
    base = m.group(1)
    n = int(m.group(2)) + 1 if m.group(2) else 1
    while True:
        cand = path.with_name(f"{base}{n}{path.suffix}")
        if not cand.exists():
            return cand
        n += 1


def _speedup_audio_for_doc(src, factor):
    """Tăng tốc audio cho VIDEO DỌC bằng ffmpeg atempo (giữ cao độ, không bị 'chipmunk').

    factor nằm trong khoảng atempo cho phép (0.5–2.0). Trả về file mới *_spedNNN.wav.
    """
    import shutil
    import subprocess
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("Không tìm thấy ffmpeg trong PATH.")
    src = Path(src)
    tag = f"{factor:.2f}".replace(".", "")          # 1.07 -> "107"
    out = src.with_name(f"{src.stem}_sped{tag}{src.suffix}")
    cmd = [ffmpeg, "-y", "-i", str(src), "-filter:a", f"atempo={factor:.4f}",
           "-vn", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0 or not out.exists():
        raise RuntimeError(f"ffmpeg atempo lỗi: {(r.stderr or '')[-300:] or r.returncode}")
    return out


def _play_done_sound(success: bool = True) -> None:
    """Phát âm báo khi chạy xong (async, không chặn; bỏ qua nếu không phát được)."""
    try:
        import winsound
        # SystemAsterisk = báo nhẹ khi hoàn tất; SystemHand = âm báo lỗi.
        alias = "SystemAsterisk" if success else "SystemHand"
        winsound.PlaySound(alias, winsound.SND_ALIAS | winsound.SND_ASYNC)
    except Exception:
        pass


def run_tts(mode, voice_param, chunks, output, progress_var, status_var, btn_run, btn_pause, btn_preview, pause_event, make_video=False, effect=None, cut_audio=False, cut_target=12.0, cut_min=10.0, cut_max=15.0, make_video_doc=False, doc_full_audio=False, doc_speed=1.0, ngang_speed=1.0, cut_half=False, reuse=False, doc_from_ngang=False, doc_no_effect=False):
    import torch
    from omnivoice.models.omnivoice import OmniVoice
    from omnivoice.utils.common import get_best_device

    failed = False

    # Bước dựng video báo tiến trình qua THANH (progress_var) + dòng trạng thái,
    # KHÔNG spam % ra nhật ký. label đứng trước, % chạy trên thanh.
    def _video_progress(label):
        def _cb(pct, cur, total, speed):
            progress_var.set(int(pct))
            status_var.set(f"{label} {pct:.0f}%  ({cur:.0f}/{total:.0f}s · {speed})")
        return _cb

    try:
        total = len(chunks)
        output_path = Path(output)
        tmp_dir = chunks_dir_for(output_path)
        tmp_dir.mkdir(parents=True, exist_ok=True)

        # Chữ ký cấu hình (giọng/chế độ/văn bản) — quyết định có thể DÙNG LẠI
        # audio cũ hay phải tạo lại (text/giọng đổi → chữ ký khác → tạo lại).
        sig = hashlib.sha1("|".join([mode, str(voice_param), *chunks])
                           .encode("utf-8")).hexdigest()
        sig_file = tmp_dir / "_signature.txt"
        old_sig = sig_file.read_text(encoding="utf-8").strip() if sig_file.exists() else None

        # ♻ Dùng lại: chỉ tái dùng khi audio đã có VÀ chữ ký khớp (cùng văn bản/giọng).
        # Nếu văn bản/giọng đã đổi thì vẫn tạo lại để không ghép nhầm bản cũ.
        audio_ready = output_path.exists() and output_path.stat().st_size > 4096
        reuse_audio = reuse and audio_ready and old_sig == sig

        if reuse_audio:
            logging.info(f"♻ Dùng lại audio đã có (bỏ qua tạo giọng): {output_path.name}")
            status_var.set(f"♻ Dùng audio đã có → {output_path.name}")
            progress_var.set(100)
            btn_preview.config(state="normal")
        else:
            if reuse and not audio_ready:
                logging.info("♻ Chưa có audio để dùng lại → tạo giọng từ đầu.")
            elif reuse and old_sig != sig:
                logging.info("♻ Văn bản/giọng đã đổi → tạo lại giọng (không dùng bản cũ).")

            # Chữ ký khác lần trước → xóa chunk cũ để tạo lại, tránh ghép nhầm.
            if old_sig != sig:
                stale = list(tmp_dir.glob("*.wav"))
                for w in stale:
                    w.unlink()
                if stale:
                    logging.warning(
                        f"Cấu hình đổi (giọng/chế độ/văn bản) → xóa {len(stale)} "
                        "chunk cũ, tạo lại từ đầu."
                    )
                sig_file.write_text(sig, encoding="utf-8")

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
                result = _generate_chunk(model, mode, voice_param, chunk)
                sf.write(str(tmp_file), result[0], sr)

            # ── KIỂM TRA SPIKE SAU KHI GENERATE XONG ────────────────────────
            status_var.set("Kiểm tra chất lượng audio...")
            logging.info("Kiểm tra spike toàn bộ chunks...")
            bad_chunks = []
            for i in range(total):
                f = tmp_dir / f"{i:04d}.wav"
                spikes = detect_spike(f, sr)
                if spikes:
                    bad_chunks.append(i)
                    logging.warning(f"  [SPIKE] {f.name} tại {spikes[:3]}s → render lại")

            if bad_chunks:
                logging.info(f"Render lại {len(bad_chunks)} chunk lỗi: {bad_chunks}")
                for idx, i in enumerate(bad_chunks):
                    status_var.set(f"Render lại chunk lỗi {idx+1}/{len(bad_chunks)}...")
                    tmp_file = tmp_dir / f"{i:04d}.wav"
                    tmp_file.unlink(missing_ok=True)
                    result = _generate_chunk(model, mode, voice_param, chunks[i])
                    sf.write(str(tmp_file), result[0], sr)
                    logging.info(f"  [{i:04d}] render lại xong")
            else:
                logging.info("Không phát hiện spike — tất cả chunk OK.")

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
            btn_preview.config(state="normal")   # cho phép nghe thử kết quả

            # ── GIẢI PHÓNG OMNIVOICE KHỎI VRAM ─────────────────────────────
            # Audio đã tạo + ghép xong; các bước còn lại (cắt, dựng video bằng
            # h264_nvenc) KHÔNG dùng tới OmniVoice. Model nạp mới mỗi lần chạy
            # (không cache), nên xóa ngay để trả ~vài GB VRAM cho NVENC — tránh
            # thiếu VRAM khiến dựng video rớt về CPU (libx264) chậm.
            try:
                import gc
                del model
                gc.collect()
                torch.cuda.empty_cache()
                logging.info("🧹 Đã giải phóng OmniVoice khỏi VRAM trước khi dựng video.")
            except Exception as e:
                logging.warning(f"Không giải phóng được OmniVoice: {e}")

        # ── (TÙY CHỌN) CẮT BẢN NGẮN TỪ AUDIO FULL — nguồn cho video dọc ────
        # Audio full ở trên KHÔNG đổi; đây là file phụ. Hai kiểu LOẠI TRỪ nhau:
        #   • "Cắt 1/2" được ƯU TIÊN: cắt ≈ nửa tổng thời lượng (output_half.wav)
        #     và THAY luôn bản 10–15 phút.
        #   • Nếu không bật 1/2 thì mới cắt bản 10–15 phút (output_cut.wav).
        # Cả hai đều cắt tại khoảng lặng cuối câu gần mốc đích để không cụt giữa câu.
        cut_path = None
        if cut_half:
            hp = output_path.with_name(output_path.stem + "_half" + output_path.suffix)
            if reuse_audio and hp.exists() and hp.stat().st_size > 4096:
                cut_path = hp
                logging.info(f"♻ Dùng lại bản ~1/2 đã có: {hp.name}")
            else:
                status_var.set("Đang cắt bản ~1/2 audio gốc...")
                try:
                    from video_timclip import (cut_audio_at_sentence_end,
                                               probe_audio_duration)
                    total_sec = probe_audio_duration(output_path)
                    half_min = (total_sec / 2.0) / 60.0
                    tol = max(0.5, half_min * 0.2)              # dung sai ±20% (≥0.5 phút)
                    half_seconds, _ = cut_audio_at_sentence_end(
                        output_path, hp,
                        target_minutes=half_min,
                        min_minutes=max(0.1, half_min - tol),
                        max_minutes=min(total_sec / 60.0, half_min + tol),
                        silence_db=-35.0, min_silence=0.5)
                    cut_path = hp                                # thay bản 10–15 phút làm nguồn video dọc
                    m, s = divmod(half_seconds, 60)
                    logging.info(f"✂ Đã cắt bản ~1/2 tại {int(m)}:{s:05.2f} → {hp.name}")
                except Exception as e:
                    logging.warning(f"Không cắt được bản 1/2: {e}")
        elif cut_audio:
            cp = output_path.with_name(output_path.stem + "_cut" + output_path.suffix)
            if reuse_audio and cp.exists() and cp.stat().st_size > 4096:
                cut_path = cp
                logging.info(f"♻ Dùng lại bản 10–15 phút đã có: {cp.name}")
            else:
                status_var.set("Đang cắt bản 10–15 phút...")
                try:
                    from video_timclip import cut_audio_at_sentence_end
                    cut_seconds, _ = cut_audio_at_sentence_end(
                        output_path, cp,
                        target_minutes=cut_target, min_minutes=cut_min,
                        max_minutes=cut_max, silence_db=-35.0, min_silence=0.5)
                    cut_path = cp
                    m, s = divmod(cut_seconds, 60)
                    logging.info(f"✂ Đã cắt bản ngắn tại {int(m)}:{s:05.2f} → {cut_path.name}")
                except Exception as e:
                    logging.warning(f"Không cắt được bản 10–15 phút: {e}")

        # ── TỰ DỰNG VIDEO NGANG TỪ AUDIO FULL (nếu bật) ────────────────────
        ngang_video_path = None   # video ngang vừa dựng (để video dọc dùng lại nếu bật)
        if make_video:
            # Tăng tốc audio (giữ cao độ) trước khi dựng — nếu chọn mức > 1.0
            ngang_audio = output_path
            if ngang_speed and ngang_speed > 1.001:
                status_var.set(f"Đang tăng tốc audio x{ngang_speed:.2f} cho video ngang...")
                try:
                    ngang_audio = _speedup_audio_for_doc(output_path, ngang_speed)
                    logging.info(f"⏩ Tăng tốc audio video ngang x{ngang_speed:.2f} → {ngang_audio.name}")
                except Exception as e:
                    logging.warning(f"Không tăng tốc được audio video ngang (giữ tốc độ gốc): {e}")
                    ngang_audio = output_path
            status_var.set("Đang dựng video...")
            logging.info("Bắt đầu dựng video từ audio vừa tạo...")
            try:
                from video_khung import build_video
                progress_var.set(0)
                video_out = build_video(ngang_audio, log=logging.info, effect=effect,
                                        progress=_video_progress("🎬 Dựng video ngang..."),
                                        skip_existing=reuse_audio)
                progress_var.set(100)
                ngang_video_path = video_out
                status_var.set(f"Xong! Video → {video_out}")
                logging.info(f"Đã tạo video → {video_out}")
            except Exception as e:
                logging.error(f"Lỗi dựng video: {e}")
                status_var.set(f"Audio xong, lỗi dựng video: {e}")

        # ── (TÙY CHỌN) DỰNG VIDEO DỌC (1080x1920, KHÔNG khung) ─────────────
        # Mặc định lấy AUDIO BẢN CẮT (cut_path = bản 1/2 nếu bật, không thì bản
        # 10–15 phút). Nếu chọn "dùng audio không cắt" thì lấy audio full →
        # video dọc có tiếng giống video ngang.
        if make_video_doc:
            if doc_full_audio:
                doc_audio = output_path
            elif cut_path and cut_path.exists():
                doc_audio = cut_path
            else:
                logging.warning("Chưa có bản cắt → video dọc dùng tạm audio full.")
                doc_audio = output_path
            # Tăng tốc audio (giữ cao độ) trước khi dựng — nếu chọn mức > 1.0
            if doc_speed and doc_speed > 1.001:
                status_var.set(f"Đang tăng tốc audio x{doc_speed:.2f} cho video dọc...")
                try:
                    doc_audio = _speedup_audio_for_doc(doc_audio, doc_speed)
                    logging.info(f"⏩ Tăng tốc audio video dọc x{doc_speed:.2f} → {doc_audio.name}")
                except Exception as e:
                    logging.warning(f"Không tăng tốc được audio (giữ tốc độ gốc): {e}")
            # ♻ Dùng lại VIDEO NGANG đã dựng (phóng to khớp chiều cao dọc, thay
            # âm bằng audio video dọc). Ưu tiên video ngang vừa dựng; nếu chưa có
            # (vd không bật dựng video ngang) thì tìm file *_videodone.mp4 đã có.
            ngang_src = None
            if doc_from_ngang:
                if ngang_video_path and ngang_video_path.exists():
                    ngang_src = ngang_video_path
                else:
                    cands = sorted(
                        output_path.parent.glob(output_path.stem + "*_videodone.mp4"),
                        key=lambda p: p.stat().st_mtime, reverse=True)
                    ngang_src = cands[0] if cands else None
                if ngang_src is None:
                    logging.warning("Bật 'dùng lại video ngang' nhưng chưa có video "
                                    "ngang → dựng video dọc bình thường.")
                else:
                    logging.info(f"♻ Video dọc dùng lại video ngang: {ngang_src.name}")

            status_var.set("Đang dựng video dọc...")
            logging.info(f"Bắt đầu dựng video dọc từ {doc_audio.name}...")
            try:
                from video_doc import build_video_doc
                progress_var.set(0)
                # "Không áp hiệu ứng cho video dọc" → bỏ effect ở mọi trường hợp.
                doc_effect = None if doc_no_effect else effect
                vdoc_out = build_video_doc(doc_audio, log=logging.info, effect=doc_effect,
                                           progress=_video_progress("📱 Dựng video dọc..."),
                                           skip_existing=reuse_audio,
                                           source_video=ngang_src)
                progress_var.set(100)
                status_var.set(f"Xong! Video dọc → {vdoc_out.name}")
                logging.info(f"Đã tạo video dọc → {vdoc_out.name}")
            except Exception as e:
                logging.error(f"Lỗi dựng video dọc: {e}")
                status_var.set(f"Lỗi video dọc: {e}")

    except Exception as e:
        failed = True
        logging.error(f"Lỗi: {e}")
        status_var.set(f"Lỗi: {e}")
    finally:
        pause_event.set()
        btn_run.config(state="normal")
        btn_pause.config(state="disabled", text="⏸  Tạm dừng")
        _play_done_sound(success=not failed)   # âm báo khi chạy xong (hoặc lỗi)


# ── GIAO DIỆN ────────────────────────────────────────────────────────────────
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("OmniVoice TTS")
        self.resizable(True, True)
        self.configure(bg=UI["bg"])
        self._apply_theme()
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._playing = False
        self._preview_after = None
        self._last_output = None
        self._pipe_busy = False
        self._pipe_settings = load_pipe_settings()   # auto-chain + model/tốc độ đã lưu
        self._opt_settings = load_opt_settings()      # mục "Cài đặt" của lần chạy trước
        self._favorites = load_favorites()
        self._effect_favorites = load_effect_favorites()
        self._setup_logging()
        self._build_ui()
        self._poll_log()
        self.update_idletasks()
        self.minsize(1200, 620)
        self._center(1420, 672)

    def _apply_theme(self):
        """Theme nền trắng, phẳng, hiện đại (dựa trên 'clam' để tùy biến màu)."""
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        C = UI
        base_font  = ("Segoe UI", 10)
        small_font = ("Segoe UI", 8)

        st.configure(".", background=C["bg"], foreground=C["fg"],
                     font=base_font, bordercolor=C["border"],
                     focuscolor=C["bg"], troughcolor=C["track"])
        st.configure("TFrame", background=C["bg"])
        st.configure("TLabel", background=C["bg"], foreground=C["fg"])
        st.configure("Header.TLabel", font=("Segoe UI", 19, "bold"),
                     foreground=C["fg"])
        st.configure("Brand.TLabel", font=("Segoe UI", 19, "bold"),
                     foreground=C["accent"])
        st.configure("Sub.TLabel", font=("Segoe UI", 9), foreground=C["muted"])
        st.configure("Hint.TLabel", font=small_font, foreground=C["muted"])

        # Khung "thẻ" có viền nhẹ
        st.configure("TLabelframe", background=C["card"], bordercolor=C["border"],
                     relief="solid", borderwidth=1, padding=10)
        st.configure("TLabelframe.Label", background=C["card"],
                     foreground=C["accent"], font=("Segoe UI", 10, "bold"))

        # Nhập liệu
        for w in ("TEntry", "TSpinbox"):
            st.configure(w, fieldbackground=C["field"], background=C["field"],
                         bordercolor=C["border"], lightcolor=C["border"],
                         darkcolor=C["border"], insertcolor=C["fg"], padding=5)
            st.map(w, bordercolor=[("focus", C["accent"])],
                   lightcolor=[("focus", C["accent"])])
        st.configure("TSpinbox", arrowcolor=C["muted"])

        st.configure("TCombobox", fieldbackground=C["field"], background=C["field"],
                     bordercolor=C["border"], lightcolor=C["border"],
                     darkcolor=C["border"], arrowcolor=C["muted"], padding=5)
        st.map("TCombobox",
               fieldbackground=[("readonly", C["field"])],
               foreground=[("readonly", C["fg"])],
               selectbackground=[("readonly", C["field"])],
               selectforeground=[("readonly", C["fg"])],
               bordercolor=[("focus", C["accent"])],
               lightcolor=[("focus", C["accent"])])
        # Danh sách xổ xuống của combobox
        self.option_add("*TCombobox*Listbox.background", C["field"])
        self.option_add("*TCombobox*Listbox.foreground", C["fg"])
        self.option_add("*TCombobox*Listbox.selectBackground", C["accent"])
        self.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
        self.option_add("*TCombobox*Listbox.font", base_font)

        # Radio
        st.configure("TRadiobutton", background=C["card"], foreground=C["fg"])
        st.map("TRadiobutton",
               background=[("active", C["card"])],
               foreground=[("active", C["accent"]), ("selected", C["accent"])],
               indicatorcolor=[("selected", C["accent"]), ("!selected", "#cfd3da")])

        # Checkbox
        st.configure("TCheckbutton", background=C["card"], foreground=C["fg"])
        st.map("TCheckbutton",
               background=[("active", C["card"])],
               foreground=[("active", C["accent"]), ("selected", C["accent"])],
               indicatorcolor=[("selected", C["accent"]), ("!selected", "#cfd3da")])

        # Nút phụ (xám nhạt) + nút chính (nhấn hồng)
        st.configure("TButton", background="#eef0f3", foreground=C["fg"],
                     bordercolor=C["border"], relief="flat",
                     focusthickness=0, padding=(14, 8), font=base_font)
        st.map("TButton",
               background=[("active", C["hover"]), ("pressed", C["press"]),
                           ("disabled", "#f4f5f7")],
               foreground=[("disabled", "#aeb4be")])
        st.configure("Accent.TButton", background=C["accent"], foreground="#ffffff",
                     padding=(20, 9), font=("Segoe UI", 10, "bold"))
        st.map("Accent.TButton",
               background=[("active", C["accent_dk"]), ("pressed", C["accent_dk"]),
                           ("disabled", C["accent_soft"])],
               foreground=[("disabled", "#ffffff")])

        # Thanh tiến trình
        st.configure("TProgressbar", background=C["accent"],
                     troughcolor=C["track"], bordercolor=C["track"],
                     lightcolor=C["accent"], darkcolor=C["accent"], thickness=12)

    def _center(self, w, h):
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x, y = (sw - w) // 2, (sh - h) // 3
        self.geometry(f"{w}x{h}+{max(x,0)}+{max(y,0)}")

    def _setup_logging(self):
        handler = QueueHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%H:%M:%S"))
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(logging.INFO)

    def _build_ui(self):
        C = UI
        root = ttk.Frame(self, padding=18)
        root.grid(sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        # 3 cột: [quy trình tạo kịch bản] · [điều khiển TTS] · [log mở rộng]
        root.columnconfigure(0, weight=0, minsize=330)
        root.columnconfigure(1, weight=0, minsize=470)
        root.columnconfigure(2, weight=1)
        root.rowconfigure(0, weight=1)

        # ════════════════════════════════════════════════
        # CỘT 1 — Quy trình tạo kịch bản (nhận diện → Gemini → input.txt)
        # ════════════════════════════════════════════════
        self._build_pipeline_column(root, 0)

        # ════════════════════════════════════════════════
        # CỘT 2 — toàn bộ điều khiển TTS
        # ════════════════════════════════════════════════
        left = ttk.Frame(root)
        left.grid(row=0, column=1, sticky="nsew", padx=(0, 16))
        left.columnconfigure(0, weight=1)

        # ── Header ──
        hdr = ttk.Frame(left)
        hdr.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        title = ttk.Frame(hdr)
        title.pack(anchor="w", fill="x")
        ttk.Label(title, text="🎧", style="Header.TLabel").pack(side="left", padx=(0, 8))
        ttk.Label(title, text="OmniVoice", style="Header.TLabel").pack(side="left")
        ttk.Label(title, text="TTS", style="Brand.TLabel").pack(side="left", padx=(6, 0))
        ttk.Label(hdr, text="Chuyển văn bản thành giọng nói — Clone · Thiết kế · Mặc định",
                  style="Sub.TLabel").pack(anchor="w", pady=(2, 0))

        # ── Chế độ ──
        sec_mode = ttk.LabelFrame(left, text="  Chế độ  ")
        sec_mode.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        sec_mode.columnconfigure(0, weight=1)

        self.var_mode = tk.StringVar(value="clone")
        mode_row = ttk.Frame(sec_mode)
        mode_row.grid(row=0, column=0, sticky="w")
        for label, val, desc in [
            ("🎙  Clone",   "clone",   "Nhái giọng mẫu"),
            ("🎨  Thiết kế", "design",  "Mô tả giọng"),
            ("🔊  Mặc định", "default", "Model tự chọn"),
        ]:
            f = ttk.Frame(mode_row)
            f.pack(side="left", padx=(0, 18))
            ttk.Radiobutton(f, text=label, variable=self.var_mode,
                            value=val, command=self._on_mode_change).pack(anchor="w")
            ttk.Label(f, text=desc, style="Hint.TLabel").pack(anchor="w", padx=22)

        ttk.Separator(sec_mode, orient="horizontal").grid(
            row=1, column=0, sticky="ew", pady=10)

        self.voice_frame = ttk.Frame(sec_mode)
        self.voice_frame.grid(row=2, column=0, sticky="ew")

        # Clone
        self.frm_clone = ttk.Frame(self.voice_frame)
        ttk.Label(self.frm_clone, text="Giọng mẫu:", width=11, anchor="w").pack(side="left", padx=(0, 6))
        self.var_ref = tk.StringVar()
        self.cb_ref = ttk.Combobox(self.frm_clone, textvariable=self.var_ref,
                                   values=[], width=30, state="readonly")
        self.cb_ref.pack(side="left")
        self.cb_ref.bind("<<ComboboxSelected>>", lambda e: self._update_fav_button())
        self.btn_fav = ttk.Button(self.frm_clone, text="☆", width=3,
                                  command=self._toggle_favorite)
        self.btn_fav.pack(side="left", padx=(6, 0))
        ttk.Button(self.frm_clone, text="↻", width=3,
                   command=self._refresh_voices).pack(side="left", padx=(6, 0))
        self._reload_voice_combo()   # nạp danh sách (yêu thích ★ lên đầu) + chọn mục đầu

        # Design
        self.frm_design = ttk.Frame(self.voice_frame)
        lang_row = ttk.Frame(self.frm_design)
        lang_row.pack(anchor="w", pady=(0, 4))
        ttk.Label(lang_row, text="Ngôn ngữ:").pack(side="left", padx=(0, 8))
        self.var_lang = tk.StringVar(value="en")
        ttk.Radiobutton(lang_row, text="English", variable=self.var_lang,
                        value="en", command=self._on_lang_change).pack(side="left", padx=4)
        ttk.Radiobutton(lang_row, text="中文", variable=self.var_lang,
                        value="zh", command=self._on_lang_change).pack(side="left", padx=4)
        self.design_attr_frame = ttk.Frame(self.frm_design)
        self.design_attr_frame.pack(anchor="w", fill="x")
        res_row = ttk.Frame(self.frm_design)
        res_row.pack(anchor="w", fill="x", pady=(6, 0))
        ttk.Label(res_row, text="Lệnh model:").pack(side="left", padx=(0, 8))
        self.var_instruct = tk.StringVar(value="female, young adult")
        ttk.Entry(res_row, textvariable=self.var_instruct, width=36).pack(side="left", fill="x", expand=True)

        self._design_vars: list[tk.StringVar] = []
        self._design_sep = ", "
        self._build_design_dropdowns()

        # Default
        self.frm_default = ttk.Frame(self.voice_frame)
        ttk.Label(self.frm_default, text="Model tự động chọn giọng phù hợp với văn bản",
                  style="Sub.TLabel").pack(side="left", padx=2)

        self._on_mode_change()

        # ── Tệp ──
        sec_file = ttk.LabelFrame(left, text="  Tệp  ")
        sec_file.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        sec_file.columnconfigure(1, weight=1)

        for r, (lbl, attr, default, is_save) in enumerate([
            ("Văn bản (.txt):", "var_txt", str(SCRIPT_DIR / "input.txt"),  False),
            ("Kết quả (.wav):", "var_out", str(OUTPUT_DIR / "output.wav"), True),
        ]):
            ttk.Label(sec_file, text=lbl, width=14, anchor="w").grid(
                row=r, column=0, sticky="w", padx=(0, 8), pady=4)
            var = tk.StringVar(value=default)
            setattr(self, attr, var)
            ttk.Entry(sec_file, textvariable=var).grid(
                row=r, column=1, sticky="ew", pady=4)
            cmd = (lambda v=var: self._pick_save(v, [("WAV", "*.wav")])) if is_save \
                else (lambda v=var: self._pick_file(v, [("Text", "*.txt")]))
            ttk.Button(sec_file, text="Chọn…", width=8, command=cmd).grid(
                row=r, column=2, padx=(8, 0), pady=4)

        # ── Cài đặt ──
        sec_opt = ttk.LabelFrame(left, text="  Cài đặt  ")
        sec_opt.grid(row=3, column=0, sticky="ew", pady=(0, 12))

        # Nguồn nội dung: lấy từ Gemini (gemini_result.docx) + kiểm tra trước khi tạo
        gem_row = ttk.Frame(sec_opt)
        gem_row.pack(anchor="w", fill="x", pady=(0, 8))
        self.var_from_gemini = tk.BooleanVar(value=self._opt_settings["from_gemini"])
        ttk.Checkbutton(gem_row,
                        text="🌐  Lấy nội dung từ Gemini + kiểm tra trước khi tạo",
                        variable=self.var_from_gemini).pack(side="left")
        ttk.Label(gem_row, text="(gemini_result.docx → input.txt)",
                  style="Hint.TLabel").pack(side="left", padx=8)

        chunk_row = ttk.Frame(sec_opt)
        chunk_row.pack(anchor="w", fill="x")
        ttk.Label(chunk_row, text="Độ dài đoạn (ký tự):").pack(side="left", padx=(0, 8))
        self.var_chunk = tk.IntVar(value=self._opt_settings["chunk"])
        ttk.Spinbox(chunk_row, from_=100, to=1000, increment=50,
                    textvariable=self.var_chunk, width=7).pack(side="left")
        ttk.Label(chunk_row, text="nhỏ hơn = nhẹ RAM GPU hơn",
                  style="Hint.TLabel").pack(side="left", padx=8)

        video_row = ttk.Frame(sec_opt)
        video_row.pack(anchor="w", fill="x", pady=(8, 0))
        self.var_make_video = tk.BooleanVar(value=self._opt_settings["make_video"])
        ttk.Checkbutton(video_row, text="🎬  Tự dựng video (ngang)",
                        variable=self.var_make_video).pack(side="left")
        ttk.Label(video_row, text="Tăng tốc:").pack(side="left", padx=(12, 2))
        self.var_ngang_speed = tk.StringVar(value=self._opt_settings["ngang_speed"])
        ttk.Combobox(video_row, textvariable=self.var_ngang_speed, width=6,
                     values=["1.0", "1.05", "1.1", "1.15", "1.2", "1.25"]).pack(side="left")
        ttk.Label(video_row, text="x (giữ cao độ)",
                  style="Hint.TLabel").pack(side="left", padx=(4, 0))

        # Hiệu ứng phủ lên toàn bộ video (từ đầu đến cuối) — lấy từ scripts/hieuung/
        fx_row = ttk.Frame(sec_opt)
        fx_row.pack(anchor="w", fill="x", pady=(8, 0))
        ttk.Label(fx_row, text="✨  Hiệu ứng:").pack(side="left", padx=(0, 8))
        self.var_effect = tk.StringVar(value=EFFECT_NONE)
        self.cb_effect = ttk.Combobox(fx_row, textvariable=self.var_effect,
                                      values=[EFFECT_NONE], width=24, state="readonly")
        self.cb_effect.pack(side="left")
        self.cb_effect.bind("<<ComboboxSelected>>",
                            lambda e: self._update_effect_fav_button())
        self.btn_effect_fav = ttk.Button(fx_row, text="☆", width=3,
                                         command=self._toggle_effect_favorite)
        self.btn_effect_fav.pack(side="left", padx=(6, 0))
        ttk.Button(fx_row, text="↻", width=3,
                   command=self._refresh_effects).pack(side="left", padx=(6, 0))
        ttk.Label(fx_row, text="(phủ lên toàn video)",
                  style="Hint.TLabel").pack(side="left", padx=8)
        # Nạp danh sách (yêu thích ★ lên đầu) + chọn lại hiệu ứng của lần chạy trước
        self._reload_effect_combo(keep=self._opt_settings.get("effect", EFFECT_NONE))

        # Cắt bản 10–15 phút (file phụ output_cut.wav) — gộp 1 dòng cho gọn chiều cao
        cut_row = ttk.Frame(sec_opt)
        cut_row.pack(anchor="w", fill="x", pady=(8, 0))
        self.var_cut_audio = tk.BooleanVar(value=self._opt_settings["cut_audio"])
        ttk.Checkbutton(cut_row, text="✂️  Cắt 10–15 phút",
                        variable=self.var_cut_audio).pack(side="left")
        ttk.Label(cut_row, text="Đích:").pack(side="left", padx=(10, 2))
        self.var_cut_target = tk.DoubleVar(value=self._opt_settings["cut_target"])
        ttk.Spinbox(cut_row, from_=1, to=60, increment=1,
                    textvariable=self.var_cut_target, width=4).pack(side="left")
        ttk.Label(cut_row, text="Từ:").pack(side="left", padx=(8, 2))
        self.var_cut_min = tk.DoubleVar(value=self._opt_settings["cut_min"])
        ttk.Spinbox(cut_row, from_=1, to=60, increment=1,
                    textvariable=self.var_cut_min, width=4).pack(side="left")
        ttk.Label(cut_row, text="Đến:").pack(side="left", padx=(8, 2))
        self.var_cut_max = tk.DoubleVar(value=self._opt_settings["cut_max"])
        ttk.Spinbox(cut_row, from_=1, to=60, increment=1,
                    textvariable=self.var_cut_max, width=4).pack(side="left")

        # Cắt ~1/2 audio gốc (file riêng output_half.wav) — độc lập bản 10–15 phút
        cuthalf_row = ttk.Frame(sec_opt)
        cuthalf_row.pack(anchor="w", fill="x", pady=(6, 0))
        self.var_cut_half = tk.BooleanVar(value=self._opt_settings["cut_half"])
        ttk.Checkbutton(cuthalf_row, text="✂️  Cắt 1/2 (≈ nửa audio gốc)",
                        variable=self.var_cut_half).pack(side="left")
        ttk.Label(cuthalf_row, text="(thay bản 10–15 phút → output_half.wav)",
                  style="Hint.TLabel").pack(side="left", padx=8)

        # (Khối "Video dọc" đã chuyển sang CỘT 3 bên phải cho đỡ chật.)

        # ════════════════════════════════════════════════
        # CỘT 3 (PHẢI) — Hành động + tiến trình ở TRÊN, nhật ký (nhỏ) ở DƯỚI
        # ════════════════════════════════════════════════
        right = ttk.Frame(root)
        right.grid(row=0, column=2, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(4, weight=1)   # chỉ ô nhật ký giãn ra theo chiều cao

        # ── Video dọc (chuyển từ cột giữa sang cho đỡ chật) ──
        vdoc = ttk.LabelFrame(right, text="  📱  Video dọc (1080×1920)  ")
        vdoc.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.var_make_video_doc = tk.BooleanVar(value=self._opt_settings["make_video_doc"])
        ttk.Checkbutton(vdoc, text="Dựng video dọc (từ bản cắt)",
                        variable=self.var_make_video_doc).pack(anchor="w")
        vdoc_opts = ttk.Frame(vdoc)
        vdoc_opts.pack(anchor="w", fill="x", pady=(6, 0))
        self.var_doc_full_audio = tk.BooleanVar(value=self._opt_settings["doc_full_audio"])
        ttk.Checkbutton(vdoc_opts, text="dùng audio không cắt",
                        variable=self.var_doc_full_audio).pack(side="left")
        ttk.Label(vdoc_opts, text="Tăng tốc:").pack(side="left", padx=(12, 2))
        self.var_doc_speed = tk.StringVar(value=self._opt_settings["doc_speed"])
        # Combobox để sửa tay được (vd 1.07), kèm các mức gợi ý sẵn.
        ttk.Combobox(vdoc_opts, textvariable=self.var_doc_speed, width=6,
                     values=["1.0", "1.05", "1.1", "1.15", "1.2", "1.25"]).pack(side="left")
        ttk.Label(vdoc_opts, text="x (giữ cao độ)",
                  style="Hint.TLabel").pack(side="left", padx=(4, 0))

        # Dùng lại video ngang đã dựng (phóng to khớp chiều cao dọc + cắt giữa),
        # thay âm bằng audio video dọc. Tắt → dựng từ kho videodoc/ như cũ.
        vdoc_opts2 = ttk.Frame(vdoc)
        vdoc_opts2.pack(anchor="w", fill="x", pady=(6, 0))
        self.var_doc_from_ngang = tk.BooleanVar(value=self._opt_settings["doc_from_ngang"])
        ttk.Checkbutton(vdoc_opts2,
                        text="♻  Dùng lại video ngang (phóng to khớp chiều cao)",
                        variable=self.var_doc_from_ngang).pack(side="left")

        # Không phủ hiệu ứng lên video dọc (mọi trường hợp) — video dọc sạch hiệu ứng.
        vdoc_opts3 = ttk.Frame(vdoc)
        vdoc_opts3.pack(anchor="w", fill="x", pady=(6, 0))
        self.var_doc_no_effect = tk.BooleanVar(value=self._opt_settings["doc_no_effect"])
        ttk.Checkbutton(vdoc_opts3, text="🚫  Không áp hiệu ứng cho video dọc",
                        variable=self.var_doc_no_effect).pack(side="left")

        # ── Hành động (Chạy / Tạm dừng / Nghe thử) ──
        act = ttk.Frame(right)
        act.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        self.btn_run = ttk.Button(act, text="▶  Chạy", command=self._start,
                                  style="Accent.TButton")
        self.btn_run.pack(side="left", padx=(0, 8))
        self.btn_pause = ttk.Button(act, text="⏸  Tạm dừng", command=self._toggle_pause,
                                    state="disabled")
        self.btn_pause.pack(side="left", padx=(0, 8))
        self.btn_preview = ttk.Button(act, text="🔊  Nghe thử", command=self._toggle_preview,
                                      state="disabled")
        self.btn_preview.pack(side="left")

        # ── Xóa output + chế độ dùng lại — xuống hàng riêng cho khỏi bị khuất ──
        act2 = ttk.Frame(right)
        act2.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        ttk.Button(act2, text="🗑  Xóa output", command=self._clear_output).pack(side="left")
        # ♻ Dùng lại audio/video đã có: bỏ qua tạo giọng nếu output.wav còn đúng
        # văn bản/giọng, và bỏ qua video nào đã dựng — chỉ dựng phần còn thiếu.
        # Mặc định TẮT (mỗi lần mở app) để tránh vô tình dùng lại bản cũ.
        self.var_reuse = tk.BooleanVar(value=False)
        ttk.Checkbutton(act2, text="♻  Dùng lại audio/video đã có (chỉ dựng phần còn thiếu)",
                        variable=self.var_reuse).pack(side="left", padx=(16, 0))

        # ── Tiến trình ──
        prog_frame = ttk.Frame(right)
        prog_frame.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        prog_frame.columnconfigure(0, weight=1)
        self.progress = tk.IntVar(value=0)
        self.progress_bar = ttk.Progressbar(prog_frame, variable=self.progress,
                                            maximum=100, mode="determinate")
        self.progress_bar.grid(row=0, column=0, sticky="ew")
        self.status = tk.StringVar(value="Sẵn sàng.")
        ttk.Label(prog_frame, textvariable=self.status,
                  style="Sub.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))

        # ── Nhật ký (nhỏ lại — chỉ để theo dõi, không quan trọng) ──
        log_frame = ttk.LabelFrame(right, text="  Nhật ký  ")
        log_frame.grid(row=4, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log_box = scrolledtext.ScrolledText(
            log_frame, width=46, height=10, state="disabled",
            font=("Consolas", 9), relief="flat", borderwidth=0,
            background=C["log_bg"], foreground=C["log_info"],
            insertbackground=C["fg"], selectbackground=C["accent_soft"],
            padx=10, pady=8, wrap="word",
        )
        self.log_box.grid(row=0, column=0, sticky="nsew")
        self.log_box.tag_config("info", foreground=C["log_info"])
        self.log_box.tag_config("warn", foreground=C["log_warn"])
        self.log_box.tag_config("err", foreground=C["log_err"])

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

    def _current_voice(self) -> str:
        """Tên file giọng mẫu thật đang chọn (đã bỏ tiền tố ★)."""
        return strip_star(self.var_ref.get())

    def _reload_voice_combo(self, keep: str | None = None):
        """Dựng lại danh sách giọng: yêu thích (★) lên đầu, còn lại theo a-z.

        keep = tên file thật muốn giữ chọn; mặc định giữ mục đang chọn.
        """
        files = list_voice_files()
        favs = [f for f in files if f in self._favorites]
        rest = [f for f in files if f not in self._favorites]
        ordered = favs + rest
        display = [(STAR + f if f in self._favorites else f) for f in ordered]
        self.cb_ref["values"] = display

        want = keep if keep is not None else self._current_voice()
        if want in ordered:
            self.var_ref.set(STAR + want if want in self._favorites else want)
        elif display:
            self.var_ref.set(display[0])
        else:
            self.var_ref.set("")
        self._update_fav_button()

    def _update_fav_button(self):
        fav = self._current_voice() in self._favorites
        self.btn_fav.config(text="★" if fav else "☆")

    def _toggle_favorite(self):
        name = self._current_voice()
        if not name:
            return
        if name in self._favorites:
            self._favorites.discard(name)
            logging.info(f"☆ Bỏ yêu thích: {name}")
        else:
            self._favorites.add(name)
            logging.info(f"★ Đã thêm yêu thích: {name}")
        save_favorites(self._favorites)
        self._reload_voice_combo(keep=name)

    def _refresh_voices(self):
        self._reload_voice_combo()
        logging.info(f"Tìm thấy {len(list_voice_files())} file giọng trong {VOICE_DIR}")

    def _current_effect(self) -> str:
        """Tên file hiệu ứng thật đang chọn (đã bỏ tiền tố ★); EFFECT_NONE nếu không chọn."""
        return strip_star(self.var_effect.get())

    def _reload_effect_combo(self, keep: str | None = None):
        """Dựng lại danh sách hiệu ứng: yêu thích (★) lên đầu, kèm mục 'Không'.

        keep = tên file thật muốn giữ chọn; mặc định giữ mục đang chọn.
        """
        files = list_effect_files()
        favs = [f for f in files if f in self._effect_favorites]
        rest = [f for f in files if f not in self._effect_favorites]
        ordered = favs + rest
        display = [EFFECT_NONE] + [
            (STAR + f if f in self._effect_favorites else f) for f in ordered]
        self.cb_effect["values"] = display

        want = keep if keep is not None else self._current_effect()
        if want in ordered:
            self.var_effect.set(STAR + want if want in self._effect_favorites else want)
        else:
            self.var_effect.set(EFFECT_NONE)
        self._update_effect_fav_button()

    def _update_effect_fav_button(self):
        cur = self._current_effect()
        is_file = cur in list_effect_files()
        fav = cur in self._effect_favorites
        self.btn_effect_fav.config(text="★" if fav else "☆",
                                   state="normal" if is_file else "disabled")

    def _toggle_effect_favorite(self):
        name = self._current_effect()
        if not name or name == EFFECT_NONE or name not in list_effect_files():
            return
        if name in self._effect_favorites:
            self._effect_favorites.discard(name)
            logging.info(f"☆ Bỏ yêu thích hiệu ứng: {name}")
        else:
            self._effect_favorites.add(name)
            logging.info(f"★ Đã thêm yêu thích hiệu ứng: {name}")
        save_effect_favorites(self._effect_favorites)
        self._reload_effect_combo(keep=name)

    def _refresh_effects(self):
        """Nạp lại danh sách hiệu ứng trong scripts/hieuung/ (giữ mục đang chọn)."""
        self._reload_effect_combo(keep=self._current_effect())
        logging.info(f"Tìm thấy {len(list_effect_files())} hiệu ứng trong {EFFECTS_DIR}")

    def _save_opt_settings(self):
        """Lưu cài đặt mục 'Cài đặt' hiện tại để lần sau mở lại dùng làm mặc định."""
        try:
            save_opt_settings(dict(
                from_gemini=self.var_from_gemini.get(),
                chunk=int(self.var_chunk.get()),
                make_video=self.var_make_video.get(),
                ngang_speed=self.var_ngang_speed.get(),
                effect=self._current_effect(),
                cut_audio=self.var_cut_audio.get(),
                cut_target=float(self.var_cut_target.get()),
                cut_min=float(self.var_cut_min.get()),
                cut_max=float(self.var_cut_max.get()),
                cut_half=self.var_cut_half.get(),
                make_video_doc=self.var_make_video_doc.get(),
                doc_full_audio=self.var_doc_full_audio.get(),
                doc_speed=self.var_doc_speed.get(),
                doc_from_ngang=self.var_doc_from_ngang.get(),
                doc_no_effect=self.var_doc_no_effect.get(),
            ))
        except Exception as e:
            logging.warning(f"Không lưu được cài đặt: {e}")

    def _clear_output(self):
        """Xóa toàn bộ trong output/ VÀ làm rỗng các file trong kịch_bản/.

        - output/ (kịch_bản/output): xóa hẳn mọi file + thư mục con (wav, video, chunks).
        - kịch_bản/: LÀM RỖNG các file nằm trực tiếp ở đây (input.txt, tiengTrung.docx,
          gemini_result.docx, seoYoutube.docx...) — giữ tên file, xóa sạch nội dung.
          Riêng .docx ghi lại thành docx RỖNG HỢP LỆ để code đọc sau không lỗi.
          Thư mục con (output/) không bị coi là file nên không bị đụng ở bước này.
        """
        import shutil
        out_items = list(OUTPUT_DIR.iterdir()) if OUTPUT_DIR.exists() else []
        kb_files = [p for p in SCRIPT_DIR.iterdir() if p.is_file()] if SCRIPT_DIR.exists() else []

        if not out_items and not kb_files:
            messagebox.showinfo("Thông báo", "Không có gì để xóa hay làm rỗng.")
            return

        n_files = sum(1 for p in out_items if p.is_file())
        n_dirs  = sum(1 for p in out_items if p.is_dir())
        if not messagebox.askyesno(
                "Xác nhận",
                f"• XÓA HẾT trong:\n   {OUTPUT_DIR}\n"
                f"   ({n_files} file + {n_dirs} thư mục — wav, video, chunks)\n\n"
                f"• LÀM RỖNG {len(kb_files)} file trong:\n   {SCRIPT_DIR}\n"
                f"   (input.txt, tiengTrung.docx, gemini_result.docx, seoYoutube.docx...)\n\n"
                "Không thể hoàn tác!"):
            return
        self._stop_preview()   # nhả file đang nghe (nếu có) để xóa được

        # 1) Xóa hẳn mọi thứ trong output/
        for p in out_items:
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.unlink(missing_ok=True)

        # 2) Làm rỗng các file trong kịch_bản/ (giữ tên, xóa nội dung)
        emptied = 0
        for p in kb_files:
            try:
                if p.suffix.lower() == ".docx":
                    from docx import Document
                    Document().save(str(p))          # docx rỗng nhưng hợp lệ
                else:
                    p.write_text("", encoding="utf-8")
                emptied += 1
            except Exception as e:
                logging.warning(f"Không làm rỗng được {p.name}: {e}")

        # Đặt lại tên kết quả về output.wav để đánh số lại từ đầu
        self.var_out.set(str(OUTPUT_DIR / "output.wav"))
        self._last_output = None
        self.btn_preview.config(state="disabled")
        logging.info(f"Đã xóa output trong {OUTPUT_DIR} và làm rỗng {emptied} file trong {SCRIPT_DIR}")
        self.status.set("Đã xóa output + làm rỗng kịch_bản.")

    def _pick_file(self, var, filetypes):
        path = filedialog.askopenfilename(filetypes=filetypes)
        if path:
            var.set(path)

    def _pick_save(self, var, filetypes):
        path = filedialog.asksaveasfilename(defaultextension=".wav", filetypes=filetypes)
        if path:
            var.set(path)

    def _open_nhan_dien(self):
        """Mở GUI nhận diện giọng nói tiếng Trung trong cửa sổ/tiến trình riêng."""
        import subprocess
        gui = Path(__file__).resolve().parent / "nhandien_gui.py"
        if not gui.exists():
            messagebox.showerror("Thiếu file", f"Không thấy:\n{gui}")
            return
        try:
            subprocess.Popen([sys.executable, str(gui)])
            logging.info("🎙  Đã mở cửa sổ Nhận diện giọng nói.")
        except Exception as e:
            messagebox.showerror("Lỗi mở Nhận diện", str(e))

    def _prepare_input_from_gemini(self) -> bool:
        """Quy trình trước khi tạo audio: lấy nội dung từ gemini_result.docx.

        1) KIỂM TRA câu dẫn nhập/thừa (dich_kiemtra). Có lỗi → báo + DỪNG,
           không tạo audio (để sửa docx trước).
        2) Bỏ cấu trúc 'Kết quả dịch từ Gemini' / 'Đoạn k', ghép thành 1 nội dung.
        3) Ghi vào file 'Văn bản' (input.txt) đang cấu hình.

        Trả về True nếu sẵn sàng tạo audio; False thì DỪNG.
        """
        if not GEMINI_DOCX.exists():
            messagebox.showerror(
                "Thiếu file Gemini",
                f"Không thấy:\n{GEMINI_DOCX}\n\nHãy dịch Gemini trước, hoặc bỏ tick "
                "'Lấy nội dung từ Gemini' để dùng input.txt thủ công.")
            return False
        try:
            import dich_kiemtra as cg
        except Exception as e:
            messagebox.showerror("Thiếu dich_kiemtra", str(e))
            return False

        # 1) KIỂM TRA
        logging.info("🔎 Kiểm tra gemini_result.docx trước khi tạo audio...")
        findings = cg.check_docx(GEMINI_DOCX, on_log=logging.info)
        if findings:
            lines = []
            for label, hits in findings:
                phrases = ", ".join(f'"{p}"' for p, _ in hits)
                lines.append(f"• {label}: {phrases}")
            messagebox.showwarning(
                "Gemini còn câu dẫn nhập/thừa",
                "gemini_result.docx còn câu dẫn nhập/thừa:\n\n"
                + "\n".join(lines)
                + "\n\nHãy sửa lại docx rồi thử lại. (CHƯA tạo audio.)")
            self.status.set("⛔ Gemini còn câu thừa — chưa tạo audio.")
            return False

        # 2) BỎ CẤU TRÚC + GHÉP NỘI DUNG
        chunks = cg.read_docx_chunks(GEMINI_DOCX)
        content = "\n".join(t for _, t in chunks).strip()
        if not content:
            messagebox.showerror("Trống", f"Không lấy được nội dung từ:\n{GEMINI_DOCX}")
            return False

        # 2b) THAY CÂU QUẢNG BÁ KÊNH theo vị trí (mở đầu / thân bài / kết bài)
        content, n_promo = replace_channel_promo(content)
        if n_promo:
            logging.info(f"🔁 Đã thay {n_promo} câu quảng bá kênh (mở đầu/thân/kết).")

        # 3) GHI VÀO input.txt (đường dẫn ở ô 'Văn bản')
        try:
            out = Path(self.var_txt.get())
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(content, encoding="utf-8")
        except Exception as e:
            messagebox.showerror("Lỗi ghi input.txt", str(e))
            return False
        logging.info(f"✅ Đã lấy {len(content)} ký tự từ Gemini → {out.name} (đã qua kiểm tra)")
        return True

    # ── QUY TRÌNH TẠO KỊCH BẢN (cột trái) ─────────────────────────────────────
    def _build_pipeline_column(self, parent, col):
        """Cột trái: nhận diện giọng nói → dịch Gemini → chuẩn bị input.txt."""
        wrap = ttk.Frame(parent)
        wrap.grid(row=0, column=col, sticky="nsew", padx=(0, 16))
        wrap.columnconfigure(0, weight=1)

        hdr = ttk.Frame(wrap)
        hdr.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        ttk.Label(hdr, text="🛠  Tạo kịch bản", style="Header.TLabel").pack(anchor="w")
        ttk.Label(hdr, text="Audio/Video → 中文 → Gemini → input.txt",
                  style="Sub.TLabel").pack(anchor="w", pady=(2, 0))

        # ① Nhận diện giọng nói
        s1 = ttk.LabelFrame(wrap, text="  ①  Nhận diện giọng nói  ")
        s1.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        s1.columnconfigure(0, weight=1)
        frow = ttk.Frame(s1)
        frow.grid(row=0, column=0, sticky="ew")
        frow.columnconfigure(0, weight=1)
        self.pipe_var_file = tk.StringVar()
        ttk.Entry(frow, textvariable=self.pipe_var_file).grid(row=0, column=0, sticky="ew")
        ttk.Button(frow, text="Chọn…", width=8,
                   command=self._pipe_pick_file).grid(row=0, column=1, padx=(8, 0))
        orow = ttk.Frame(s1)
        orow.grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Label(orow, text="Model:").pack(side="left")
        self.pipe_var_model = tk.StringVar(value=self._pipe_settings["model"])
        ttk.Combobox(orow, textvariable=self.pipe_var_model, width=9, state="readonly",
                     values=["tiny", "base", "small", "medium", "large-v3"]).pack(side="left", padx=(4, 12))
        ttk.Label(orow, text="Tốc độ:").pack(side="left")
        self.pipe_var_speed = tk.StringVar(value=self._pipe_settings["speed"])
        ttk.Combobox(orow, textvariable=self.pipe_var_speed, width=5, state="readonly",
                     values=["0.6", "0.7", "0.8", "0.9", "1.0"]).pack(side="left", padx=(4, 0))
        self.btn_recog = ttk.Button(s1, text="🎙  Nhận diện → tiếng Trung",
                                    style="Accent.TButton", command=self._pipe_recognize)
        self.btn_recog.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        ttk.Label(s1, text="(→ tiengTrung.docx)", style="Hint.TLabel").grid(
            row=3, column=0, sticky="w", pady=(4, 0))
        self.var_auto2 = tk.BooleanVar(value=self._pipe_settings["auto2"])
        ttk.Checkbutton(s1, text="⛓  Tự động chạy bước ② sau khi xong",
                        variable=self.var_auto2).grid(row=4, column=0, sticky="w", pady=(6, 0))

        # ② Dịch Gemini
        s2 = ttk.LabelFrame(wrap, text="  ②  Dịch qua Gemini  ")
        s2.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        s2.columnconfigure(0, weight=1)
        self.btn_gemini = ttk.Button(s2, text="🌐  Gửi Gemini (Firefox)",
                                     style="Accent.TButton", command=self._pipe_send_gemini)
        self.btn_gemini.grid(row=0, column=0, sticky="ew")
        ttk.Label(s2, text="(tiengTrung.docx → gemini_result.docx)",
                  style="Hint.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.var_auto3 = tk.BooleanVar(value=self._pipe_settings["auto3"])
        ttk.Checkbutton(s2, text="⛓  Tự động chạy bước ③ sau khi xong",
                        variable=self.var_auto3).grid(row=2, column=0, sticky="w", pady=(6, 0))

        # ③ Chuẩn bị input.txt
        s3 = ttk.LabelFrame(wrap, text="  ③  Chuẩn bị input.txt  ")
        s3.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        s3.columnconfigure(0, weight=1)
        self.btn_prep = ttk.Button(s3, text="📝  Tạo input.txt",
                                   style="Accent.TButton", command=self._pipe_prepare_input)
        self.btn_prep.grid(row=0, column=0, sticky="ew")
        ttk.Label(s3, text="(kiểm tra + gemini_result.docx → input.txt)",
                  style="Hint.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.var_auto_tts = tk.BooleanVar(value=self._pipe_settings["auto_tts"])
        ttk.Checkbutton(s3, text="⛓  Chạy tiếp tạo giọng (OmniVoice) sau khi xong",
                        variable=self.var_auto_tts).grid(row=2, column=0, sticky="w", pady=(6, 0))

        # Tiến trình + trạng thái của quy trình
        pf = ttk.Frame(wrap)
        pf.grid(row=4, column=0, sticky="ew", pady=(2, 0))
        pf.columnconfigure(0, weight=1)
        self.pipe_progress = tk.IntVar(value=0)
        ttk.Progressbar(pf, variable=self.pipe_progress, maximum=100).grid(
            row=0, column=0, sticky="ew")
        self.pipe_status = tk.StringVar(value="Sẵn sàng.")
        ttk.Label(pf, textvariable=self.pipe_status, style="Sub.TLabel").grid(
            row=1, column=0, sticky="w", pady=(4, 0))

        ttk.Button(wrap, text="↗  Mở cửa sổ nhận diện đầy đủ",
                   command=self._open_nhan_dien).grid(row=5, column=0, sticky="w", pady=(8, 0))
        ttk.Button(wrap, text="↺  Reset cài đặt quy trình về gốc",
                   command=self._reset_pipe_settings).grid(row=6, column=0, sticky="w", pady=(6, 0))

    def _pipe_pick_file(self):
        path = filedialog.askopenfilename(
            title="Chọn file audio/video tiếng Trung",
            filetypes=[("Audio/Video", "*.mp3 *.wav *.m4a *.aac *.flac *.ogg *.opus *.wma "
                                       "*.mp4 *.mkv *.mov *.avi *.webm *.flv"),
                       ("Tất cả", "*.*")])
        if path:
            self.pipe_var_file.set(path)

    def _pipe_set_busy(self, busy: bool):
        self._pipe_busy = busy
        state = "disabled" if busy else "normal"
        for b in (self.btn_recog, self.btn_gemini, self.btn_prep):
            b.config(state=state)

    def _save_pipe_settings(self):
        """Lưu cài đặt quy trình hiện tại (auto + model/tốc độ) cho lần sau."""
        save_pipe_settings(dict(
            auto2=self.var_auto2.get(), auto3=self.var_auto3.get(),
            auto_tts=self.var_auto_tts.get(),
            model=self.pipe_var_model.get(), speed=self.pipe_var_speed.get(),
        ))

    def _reset_pipe_settings(self):
        """Đưa các tùy chọn quy trình về mặc định gốc và lưu lại."""
        self.var_auto2.set(PIPE_DEFAULTS["auto2"])
        self.var_auto3.set(PIPE_DEFAULTS["auto3"])
        self.var_auto_tts.set(PIPE_DEFAULTS["auto_tts"])
        self.pipe_var_model.set(PIPE_DEFAULTS["model"])
        self.pipe_var_speed.set(PIPE_DEFAULTS["speed"])
        self.pipe_var_file.set("")
        self._save_pipe_settings()
        self.pipe_status.set("↺ Đã reset cài đặt quy trình về mặc định.")

    def _pipe_recognize(self):
        if self._pipe_busy:
            return
        media = self.pipe_var_file.get().strip()
        if not media or not os.path.isfile(media):
            messagebox.showwarning("Thiếu file",
                                   "Hãy chọn file audio/video cần nhận diện.")
            return
        self._save_pipe_settings()   # ấn chạy → nhớ cài đặt cho lần sau
        self._pipe_set_busy(True)
        self.pipe_progress.set(0)
        self.pipe_status.set("🎙  Đang nhận diện...")
        threading.Thread(
            target=self._pipe_recognize_worker,
            args=(media, self.pipe_var_model.get(), self.pipe_var_speed.get()),
            daemon=True).start()

    def _pipe_recognize_worker(self, media, model, speed):
        ok = False
        try:
            import nhandien_giongnoi as recog
            logging.info(f"🎙  Nhận diện: {Path(media).name} (model={model}, tốc độ={speed})")
            transcript = recog.transcribe_chinese(
                media, model_name=model, speed=float(speed),
                on_progress=lambda f: self.pipe_progress.set(int(f * 100)))
            if not transcript:
                logging.error("❌ Nhận diện thất bại / không có nội dung.")
                self.pipe_status.set("❌ Nhận diện thất bại.")
                return
            recog.save_docx(transcript, str(CHINESE_DOCX), title=Path(media).name)
            n = len(recog.split_into_chunks(transcript))
            self.pipe_progress.set(100)
            logging.info(f"✅ Nhận diện xong: {len(transcript)} ký tự, {n} đoạn → {CHINESE_DOCX.name}")
            self.pipe_status.set(f"✅ Xong ({n} đoạn) → {CHINESE_DOCX.name}")
            ok = True
        except Exception as e:
            logging.error(f"Lỗi nhận diện: {e}")
            self.pipe_status.set(f"Lỗi: {e}")
        finally:
            # Nhận diện xong → KHÔNG còn dùng model Whisper nữa, giải phóng khỏi
            # VRAM ngay để nhường chỗ cho OmniVoice ở bước tạo giọng (GPU 8GB dễ
            # nghẽn nếu large-v3 ~3GB vẫn nằm lại trong VRAM khi nạp OmniVoice).
            try:
                import nhandien_giongnoi as recog
                recog.free_model()
                logging.info("🧹 Đã giải phóng model nhận diện khỏi VRAM.")
            except Exception as e:
                logging.warning(f"Không giải phóng được model nhận diện: {e}")
            self._pipe_set_busy(False)
            if ok and self.var_auto2.get():   # ⛓ tự động sang bước ②
                self.after(600, lambda: self._pipe_send_gemini(auto=True))

    def _pipe_send_gemini(self, auto=False):
        if self._pipe_busy:
            return
        if not auto:
            self._save_pipe_settings()   # ấn chạy → nhớ cài đặt
        if not CHINESE_DOCX.exists():
            if auto:
                logging.error("⛓ Tự động dừng: chưa có tiengTrung.docx.")
                self.pipe_status.set("❌ Chưa có tiengTrung.docx — dừng tự động.")
                return
            messagebox.showwarning(
                "Chưa có nội dung",
                f"Chưa thấy {CHINESE_DOCX.name}.\nHãy bấm ① Nhận diện trước "
                "(hoặc đặt file tiengTrung.docx vào thư mục kịch_bản).")
            return
        # Khi chạy tự động (chuỗi) thì bỏ qua hộp hỏi xác nhận cho liền mạch.
        if not auto and not messagebox.askyesno(
                "Gửi Gemini",
                "Sẽ mở Firefox và gửi nội dung sang Gemini.\n\n"
                "Hãy ĐÓNG Firefox đang mở (nếu có) và đảm bảo profile đã đăng nhập "
                "Google.\n\nTiếp tục?"):
            return
        if auto:
            logging.info("⛓ Tự động: gửi Gemini (bỏ qua hỏi xác nhận).")
        self._pipe_set_busy(True)
        self.pipe_progress.set(0)
        self.pipe_status.set("🌐  Đang gửi Gemini...")
        threading.Thread(target=self._pipe_gemini_worker, daemon=True).start()

    def _pipe_gemini_worker(self):
        ok = False
        try:
            chunks = read_chinese_docx_chunks(CHINESE_DOCX)
            if not chunks:
                logging.error("❌ Không đọc được nội dung tiếng Trung để gửi.")
                self.pipe_status.set("❌ Nội dung trống.")
                return
            import dich_gemini as g
            prefix = load_prefix()
            logging.info(f"🌐 Gửi {len(chunks)} đoạn sang Gemini (mở Firefox)...")
            results = g.send_chunks_to_gemini(
                chunks, prefix=prefix, on_log=logging.info, out_path=GEMINI_DOCX,
                keep_open=False,        # gửi xong (hoặc lỗi) → tự đóng Firefox
                on_result=lambda i, total, ans: self.pipe_status.set(
                    f"🌐 Gemini: đoạn {i + 1}/{total}"))
            g.save_results_docx(chunks, results, GEMINI_DOCX)
            n_ok = sum(1 for r in results if r and r.strip())
            logging.info(f"✅ Gemini xong: {n_ok}/{len(results)} đoạn → {GEMINI_DOCX.name}")
            self.pipe_status.set(f"✅ Gemini xong → {GEMINI_DOCX.name}")
            ok = True
        except Exception as e:
            logging.error(f"Lỗi gửi Gemini: {e}")
            self.pipe_status.set(f"Lỗi: {e}")
        finally:
            self._pipe_set_busy(False)
            if ok and self.var_auto3.get():   # ⛓ tự động sang bước ③
                self.after(600, lambda: self._pipe_prepare_input(auto=True))

    def _pipe_prepare_input(self, auto=False):
        if self._pipe_busy:
            return
        if not auto:
            self._save_pipe_settings()   # ấn chạy → nhớ cài đặt
        if self._prepare_input_from_gemini():
            self.pipe_status.set("✅ Đã tạo input.txt từ Gemini.")
            if self.var_auto_tts.get():   # ⛓ chạy tiếp tạo giọng (OmniVoice)
                logging.info("⛓ Tự động: chạy tiếp tạo giọng (OmniVoice)...")
                self.after(400, self._start)
            elif not auto:
                messagebox.showinfo(
                    "Xong",
                    "Đã tạo input.txt từ gemini_result.docx.\n"
                    "Giờ có thể bấm '▶ Chạy' để tạo audio.")

    def _start(self):
        self._save_pipe_settings()   # ấn ▶ Chạy → nhớ cài đặt quy trình cho lần sau
        self._save_opt_settings()    # nhớ cả mục "Cài đặt" để lần sau làm mặc định
        mode = self.var_mode.get()
        if mode == "clone":
            voice_name = self._current_voice()
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

        # ── (TÙY CHỌN) Lấy nội dung từ Gemini + KIỂM TRA trước khi tạo audio ──
        if self.var_from_gemini.get():
            if not self._prepare_input_from_gemini():
                return

        # ── Chia text ngay tại đây, trước khi khởi động thread ──────────────
        text_file = Path(self.var_txt.get())
        try:
            full_text = clean_text(text_file.read_text(encoding="utf-8"))
        except Exception as e:
            messagebox.showerror("Lỗi đọc file", str(e))
            return

        chunks = split_chunks(full_text.lower(), self.var_chunk.get())
        if not chunks:
            messagebox.showwarning("File trống", "File văn bản không có nội dung.")
            return

        # Cắt ~1/2 audio gốc (file riêng) — độc lập bản 10–15 phút
        cut_half = self.var_cut_half.get()

        # Tham số cắt bản 10–15 phút (đọc + kiểm tra TRƯỚC khi khóa nút)
        cut_audio = self.var_cut_audio.get()
        cut_target = cut_min = cut_max = 0.0
        if cut_audio:
            try:
                cut_target = float(self.var_cut_target.get())
                cut_min = float(self.var_cut_min.get())
                cut_max = float(self.var_cut_max.get())
            except Exception:
                messagebox.showwarning("Cấu hình cắt sai", "Số phút không hợp lệ.")
                return
            if not (0 < cut_min <= cut_max):
                messagebox.showwarning("Cấu hình cắt sai",
                                       "Cần thỏa: 0 < phút 'Từ' ≤ phút 'Đến'.")
                return

        # Video dọc: bật/tắt + dùng audio cắt (mặc định) hay audio full + tốc độ
        make_video_doc = self.var_make_video_doc.get()
        doc_full_audio = self.var_doc_full_audio.get()
        doc_from_ngang = self.var_doc_from_ngang.get()   # dùng lại video ngang cho dọc
        doc_no_effect = self.var_doc_no_effect.get()     # không phủ hiệu ứng lên video dọc
        try:
            doc_speed = float(str(self.var_doc_speed.get()).replace(",", ".").strip())
        except (TypeError, ValueError):
            doc_speed = 1.0
        doc_speed = max(0.5, min(doc_speed, 2.0))   # atempo chỉ nhận 0.5–2.0
        if make_video_doc and doc_speed > 1.001:
            logging.info(f"Video dọc sẽ tăng tốc audio x{doc_speed:.2f} (giữ cao độ).")

        # Tốc độ audio cho VIDEO NGANG (audio full) — atempo, giữ cao độ
        try:
            ngang_speed = float(str(self.var_ngang_speed.get()).replace(",", ".").strip())
        except (TypeError, ValueError):
            ngang_speed = 1.0
        ngang_speed = max(0.5, min(ngang_speed, 2.0))
        if self.var_make_video.get() and ngang_speed > 1.001:
            logging.info(f"Video ngang sẽ tăng tốc audio x{ngang_speed:.2f} (giữ cao độ).")

        preview_path = text_file.parent / (text_file.stem + "_preview.txt")
        if preview_path.exists():
            preview_path.unlink()
        preview_path.write_text("\n\n".join(chunks), encoding="utf-8")
        logging.info(f"Chia {len(chunks)} đoạn (chunk={self.var_chunk.get()} ký tự) → {preview_path.name}")

        # ♻ Dùng lại audio/video đã có (chỉ dựng phần còn thiếu).
        reuse = self.var_reuse.get()

        # Bình thường: nếu file kết quả đã có → tự đặt tên mới (output.wav →
        # output1.wav…) để KHÔNG ghi đè bản cũ. Khi DÙNG LẠI thì GIỮ NGUYÊN tên
        # để tái dùng audio/video cũ thay vì tạo bản mới.
        if reuse:
            out_path = Path(self.var_out.get())
            logging.info(f"♻ Dùng lại: {out_path.name} (chỉ dựng phần còn thiếu).")
        else:
            out_path = unique_path(Path(self.var_out.get()))
            if str(out_path) != self.var_out.get():
                logging.info(f"File kết quả đã có → dùng tên mới: {out_path.name}")
                self.status.set(f"Kết quả sẽ lưu thành: {out_path.name}")
        self.var_out.set(str(out_path))
        self._last_output = self.var_out.get()

        self._stop_preview()                         # dừng audio đang nghe (nếu có)
        self.btn_preview.config(state="disabled")    # khóa tới khi tạo xong lần này
        self._pause_event = threading.Event()
        self._pause_event.set()
        self.btn_run.config(state="disabled")
        self.btn_pause.config(state="normal", text="⏸  Tạm dừng")
        # Hiệu ứng phủ video (nếu chọn) — bỏ tiền tố ★ rồi chuyển thành đường dẫn đầy đủ
        effect_name = self._current_effect()
        effect_path = None
        if effect_name and effect_name != EFFECT_NONE:
            p = EFFECTS_DIR / effect_name
            effect_path = str(p) if p.exists() else None
            if effect_path:
                logging.info(f"Hiệu ứng phủ video: {effect_name}")

        self.progress.set(0)
        self.status.set(f"Đã chia {len(chunks)} đoạn — đang khởi động...")
        threading.Thread(
            target=run_tts,
            args=(mode, voice_param, chunks, self.var_out.get(),
                  self.progress, self.status,
                  self.btn_run, self.btn_pause, self.btn_preview, self._pause_event,
                  self.var_make_video.get(), effect_path,
                  cut_audio, cut_target, cut_min, cut_max,
                  make_video_doc, doc_full_audio, doc_speed,
                  ngang_speed, cut_half, reuse, doc_from_ngang, doc_no_effect),
            daemon=True,
        ).start()

    def _toggle_pause(self):
        if self._pause_event.is_set():
            self._pause_event.clear()
            self.btn_pause.config(text="▶  Tiếp tục")
        else:
            self._pause_event.set()
            self.btn_pause.config(text="⏸  Tạm dừng")

    # ── NGHE THỬ KẾT QUẢ ──────────────────────────────────────────────────────
    def _toggle_preview(self):
        if self._playing:
            self._stop_preview()
        else:
            self._play_preview()

    def _play_preview(self):
        path = Path(self._last_output or self.var_out.get())
        if not path.exists():
            messagebox.showinfo("Chưa có audio",
                                "Chưa có file kết quả để nghe. Hãy chạy tạo giọng trước.")
            return
        try:
            import winsound
            winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception:
            # Không phát nội bộ được → mở bằng trình phát mặc định của hệ thống
            try:
                os.startfile(str(path))  # type: ignore[attr-defined]
            except Exception as e:
                messagebox.showerror("Lỗi phát audio", str(e))
            return
        self._playing = True
        self.btn_preview.config(text="⏹  Dừng nghe")
        # Tự nhả nút khi nghe hết (winsound không báo kết thúc)
        try:
            dur = sf.info(str(path)).duration
            self._preview_after = self.after(int(dur * 1000) + 300, self._stop_preview)
        except Exception:
            self._preview_after = None

    def _stop_preview(self):
        try:
            import winsound
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass
        if self._preview_after is not None:
            try:
                self.after_cancel(self._preview_after)
            except Exception:
                pass
            self._preview_after = None
        self._playing = False
        self.btn_preview.config(text="🔊  Nghe thử")

    def _poll_log(self):
        while not log_queue.empty():
            levelno, msg = log_queue.get_nowait()
            tag = ("err" if levelno >= logging.ERROR
                   else "warn" if levelno >= logging.WARNING else "info")
            self.log_box.config(state="normal")
            self.log_box.insert("end", msg + "\n", tag)
            self.log_box.see("end")
            self.log_box.config(state="disabled")
        self.after(200, self._poll_log)


if __name__ == "__main__":
    App().mainloop()
