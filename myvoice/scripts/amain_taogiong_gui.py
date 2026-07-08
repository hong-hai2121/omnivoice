"""
Giao diện desktop cho Voice Cloning — chạy: python taogiong_gui.py
"""

import sys, os
# Gốc repo OmniVoice (chứa package omnivoice + venv) — lùi 2 cấp từ myvoice/scripts/
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
_VENV_PYTHON = os.path.join(_REPO_ROOT, "venv", "Scripts", "python.exe")
if __name__ == "__main__" and os.path.exists(_VENV_PYTHON) and \
        os.path.normcase(os.path.abspath(sys.executable)) != \
        os.path.normcase(os.path.abspath(_VENV_PYTHON)):
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
SEO_DOCX   = SCRIPT_DIR / "seoYoutube.docx"           # SEO YouTube (Gemini) — chạy sau bước dịch
CHINESE_DOCX = SCRIPT_DIR / "tiengTrung.docx"         # văn bản tiếng Trung (nguồn để dịch Gemini)
YOUTUBE_DIR = BASE_DIR / "YOUTUBE"                    # nơi chứa seo_youtube_gemini.py
DOWNLOAD_DIR = Path(__file__).resolve().parent / "downloads_zh"  # mp3 tải từ link
DRIVE_SCRIPT_FOLDER_ID = "1LU1gRtZJRRpIjedxUGSa_V_zW8L1q8PQ"  # thư mục Drive "kịch bản"
PREFIX_FILE = Path(__file__).resolve().parent / "copy_prefix.txt"  # câu mở đầu dịch (chèn đoạn 1)
FAV_FILE   = BASE_DIR / "voice_favorites.json"        # danh sách giọng mẫu yêu thích
EFFECT_FAV_FILE = BASE_DIR / "effect_favorites.json"  # danh sách hiệu ứng yêu thích (★)
PIPE_FILE  = BASE_DIR / "taogiong_pipeline.json"      # cài đặt quy trình tạo kịch bản (auto + model/tốc độ)
OPTS_FILE  = BASE_DIR / "taogiong_options.json"        # cài đặt mục "Cài đặt" (nhớ lần chạy trước)
# Mặc định quy trình: ① tự chạy ②, ② tự chạy ③, ③ tự chạy tạo giọng (OmniVoice)
PIPE_DEFAULTS = dict(auto2=True, auto3=True, auto_tts=True, seo=True, model="medium", speed="0.7")
AUDIO_EXTS = {".mp3", ".wav", ".MP3", ".WAV", ".flac", ".FLAC"}
STAR       = "★ "                                     # tiền tố hiển thị cho giọng yêu thích

# Kho NHẠC NỀN (myvoice/Music) — chèn vào video TikTok, mix nhỏ hơn giọng.
MUSIC_DIR  = BASE_DIR / "Music"
MUSIC_EXTS = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wma"}

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
    doc_no_effect=False, make_tiktok=False, tiktok_speed="1.0",
    tiktok_no_effect=False, tiktok_caption_pos=40,
    tiktok_music=False, tiktok_music_db=-12, bring_front=True,
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


def read_zh_docx_chunks(path) -> list[str]:
    """Đọc lại các ĐOẠN từ file *_zh.docx (do recog.save_docx tạo: mỗi đoạn 1 đoạn
    văn dưới tiêu đề 'ĐOẠN k'). Mỗi đoạn văn = 1 chunk → tái dùng để TIẾP TỤC dịch
    mà KHÔNG cần nhận diện lại. Trả [] nếu đọc lỗi/không có đoạn nào."""
    try:
        from docx import Document
        doc = Document(str(path))
    except Exception:
        return []
    chunks = []
    for p in doc.paragraphs:
        if not p.text.strip():
            continue
        if (p.style.name or "").startswith(("Heading", "Title")):
            continue   # bỏ tiêu đề 'ĐOẠN k' và tiêu đề file
        chunks.append(p.text.strip())
    return chunks


def download_audio_mp3(url: str, out_dir: Path):
    """Tải audio từ link video (yt-dlp) → trả về đường dẫn .mp3 (None nếu lỗi).

    Dùng cho bước ① nhận diện khi đầu vào là LINK thay vì file có sẵn.
    """
    try:
        import yt_dlp
    except ImportError:
        logging.error("❌ Chưa cài yt-dlp. Chạy: pip install yt-dlp")
        return None
    import nhandien_giongnoi as recog
    ffmpeg_dir = os.path.dirname(recog.FFMPEG_PATH) if getattr(recog, "FFMPEG_PATH", None) else None
    out_dir.mkdir(parents=True, exist_ok=True)

    def hook(d):
        if d.get("status") == "downloading":
            pct = d.get("_percent_str", "").strip()
            if pct:
                logging.info(f"⬇️  Tải... {pct} {d.get('_speed_str', '').strip()}")
        elif d.get("status") == "finished":
            logging.info("✅ Tải xong, đang chuyển sang MP3...")

    ydl_opts = {
        "format": "bestaudio/best",
        # %(id)s tránh tên file có ký tự đặc biệt / tiếng Trung
        "outtmpl": os.path.join(str(out_dir), "%(id)s.%(ext)s"),
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
        ],
        "quiet": True, "no_warnings": True, "noprogress": True, "progress_hooks": [hook],
    }
    if ffmpeg_dir:
        ydl_opts["ffmpeg_location"] = ffmpeg_dir
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            logging.info(f"🎬 Tiêu đề: {info.get('title', '')}")
            mp3_path = os.path.splitext(ydl.prepare_filename(info))[0] + ".mp3"
            if os.path.exists(mp3_path):
                return mp3_path
    except Exception as e:
        logging.error(f"❌ Lỗi khi tải video: {e}")
        return None
    # Phòng khi prepare_filename không khớp: lấy mp3 mới nhất trong thư mục.
    mp3s = sorted(out_dir.glob("*.mp3"), key=lambda p: p.stat().st_mtime, reverse=True)
    return str(mp3s[0]) if mp3s else None


# Số tập ĐÃ TẠO gần nhất — dùng chung với GUI thumbnail (thumbnail_gui_state.json).
THUMB_STATE_FILE = YOUTUBE_DIR / "thumbnail_gui_state.json"


def load_episode_number() -> int:
    """Số tập đã tạo gần nhất (thumbnail_gui_state.json); chưa có → 0."""
    try:
        import json
        d = json.loads(THUMB_STATE_FILE.read_text(encoding="utf-8"))
        n = str(d.get("episode_number", "")).strip()
        if n.isdecimal():
            return int(n)
    except Exception:
        pass
    return 0


def save_episode_number(n: int) -> None:
    """Lưu số tập vừa tạo để lần/ link sau tăng tiếp (đồng bộ với GUI thumbnail)."""
    try:
        import json
        THUMB_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        THUMB_STATE_FILE.write_text(
            json.dumps({"episode_number": str(n).zfill(2)}, ensure_ascii=False, indent=2),
            encoding="utf-8")
    except Exception:
        pass


# ── MANIFEST: nhớ link nào ↔ thư mục tập nào + tiến độ (để chạy tiếp/báo cáo) ──
# File tổng đặt trong kịch_bản/ (đã gitignore). Mỗi lần chạy ghi nguồn (link/file)
# kèm số tập + bước đã xong. Lần sau chạy CÙNG link → tái dùng ĐÚNG thư mục cũ và
# bỏ qua phần đã làm; dù NHẬP KHÁC THỨ TỰ / thiếu link vẫn đúng tập.
MANIFEST_FILE = SCRIPT_DIR / "batch_manifest.json"

# [TẠM] Tắt kiểm CHI TIẾT từng đoạn dịch khi chạy batch: nếu gemini_result.docx đã
# TỒN TẠI thì coi như DỊCH XONG, KHÔNG dò từng đoạn is_translation_done nữa. Lý do:
# check chi tiết hay báo nhầm "chưa xong" → gửi LẠI đoạn đã dịch lên Gemini. Đổi về
# False để bật lại kiểm từng đoạn (chặt chẽ hơn nhưng có thể gửi lại đoạn đã dịch).
SKIP_TRANSLATE_DETAIL_CHECK = True


def norm_source(src: str) -> str:
    """Chuẩn hoá chuỗi nguồn để làm khoá manifest ổn định.

    - Bỏ khoảng trắng + nháy bao quanh.
    - FILE LOCAL: đưa về đường dẫn TUYỆT ĐỐI + normcase (trên Windows: hạ hoa/thường,
      đổi '/'→'\\'). Nhờ vậy cùng một file gõ khác kiểu — hoa/thường ổ đĩa (D:\\ vs d:\\),
      gạch chéo (\\ vs /), tương đối vs tuyệt đối — vẫn ra CÙNG khoá → không nhận diện lại.
    - URL (http/https): giữ NGUYÊN (đường dẫn mạng phân biệt hoa/thường).
    Chỉ ảnh hưởng KHOÁ manifest; thao tác đọc file vẫn dùng chuỗi gốc.
    """
    s = (src or "").strip().strip('"').strip("'").strip()
    if not s:
        return ""
    if s.lower().startswith(("http://", "https://")):
        return s
    try:
        return os.path.normcase(os.path.abspath(s))
    except Exception:
        return s


def load_manifest() -> dict:
    """Đọc manifest (nguồn→{episode, steps, done, updated}); lỗi/thiếu → {}."""
    try:
        import json
        d = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_manifest(data: dict) -> None:
    try:
        import json
        MANIFEST_FILE.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
    except Exception as e:
        logging.warning(f"Không lưu được manifest: {e}")


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
# Gemini dịch mọi câu quảng bá kênh thành câu chứa tên kênh "Mimi audio". Tùy vị
# trí trong bài (mở đầu / thân bài / kết bài) ta thay bằng 3 câu khác nhau dưới
# đây. SỬA 3 CÂU NÀY nếu muốn đổi lời.
PROMO_OPENING = "lại là mimi audio đây, mời bạn nghe câu truyện hôm nay."
PROMO_BODY    = "bạn đang nghe tại mimi audio."
PROMO_ENDING  = ("Cảm ơn bạn đã lắng nghe truyện, đây là câu truyện không có thật "
                 "ở trung quốc xin chào và hẹn gặp lại.")

# Câu quảng bá luôn chứa tên kênh "Mimi audio" → dùng cả cụm làm dấu hiệu nhận
# biết (tránh khớp nhầm từ "mimi" lẻ); vẫn bắt biến thể cũ "truyện/chuyện".
_PROMO_MARKER = re.compile(r'mimi\s+(?:audio|truyện|chuyện)', re.IGNORECASE)
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


# ── SỬA CHỮ "but" TIẾNG ANH BỊ SÓT → "nhưng" ─────────────────────────────────
# Gemini đôi khi để sót liên từ 但 thành "But/but" (tiếng Anh) thay vì "Nhưng".
# Khớp NGUYÊN TỪ (word-boundary) nên KHÔNG đụng "bút", "debut", "buttery"...
_ENG_BUT = re.compile(r'\bbut\b', re.IGNORECASE)


def _but_to_nhung(m: "re.Match") -> str:
    w = m.group(0)
    if w.isupper():          # BUT  → NHƯNG
        return "NHƯNG"
    if w[0].isupper():       # But  → Nhưng
        return "Nhưng"
    return "nhưng"           # but  → nhưng


def replace_leaked_but(text: str) -> tuple[str, int]:
    """Thay chữ tiếng Anh 'but' (Gemini sót khi dịch 但) → 'nhưng', giữ hoa/thường.
    Trả về (text_đã_thay, số_lần_thay)."""
    return _ENG_BUT.subn(_but_to_nhung, text)


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


def list_music_files() -> list[str]:
    """Danh sách file nhạc nền trong myvoice/Music (chỉ tên file)."""
    if not MUSIC_DIR.exists():
        return []
    return sorted(f.name for f in MUSIC_DIR.iterdir()
                  if f.is_file() and f.suffix.lower() in MUSIC_EXTS)


def _detect_peak_db(path: Path, ffmpeg: str, seconds: int = 150):
    """Đọc đỉnh (max_volume, dBFS) của audio bằng volumedetect (tối đa `seconds`
    giây đầu cho nhanh). Trả về float dB hoặc None nếu không đo được."""
    import subprocess
    r = subprocess.run(
        [ffmpeg, "-hide_banner", "-t", str(seconds), "-i", str(path),
         "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    m = re.search(r"max_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", r.stderr or "")
    return float(m.group(1)) if m else None


def _mix_bg_music(voice_wav: Path, music_file: Path, below_db: float,
                  out_wav: Path) -> Path:
    """Trộn NHẠC NỀN vào giọng: nhạc được hạ để đỉnh nhỏ hơn đỉnh GIỌNG đúng
    |below_db| dB (vd giọng -6dB, below=-12 → nhạc ≈ -18dB). Nhạc LẶP cho đủ dài,
    fade-in 1s, cắt bằng độ dài giọng. Trả về out_wav (giữ nguyên độ dài giọng).

    Đo đỉnh giọng + nhạc để tự tính gain → nhỏ hơn giọng ổn định dù nhạc to/nhỏ.
    Đo lỗi thì lùi về giả định giọng -6dB / nhạc 0dB.
    """
    import shutil
    import subprocess
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("Không tìm thấy ffmpeg trong PATH.")
    voice_wav, music_file, out_wav = Path(voice_wav), Path(music_file), Path(out_wav)

    voice_peak = _detect_peak_db(voice_wav, ffmpeg)
    music_peak = _detect_peak_db(music_file, ffmpeg)
    if voice_peak is None:
        voice_peak = -6.0                         # giọng OmniVoice chuẩn hoá ≈ -6dBFS
    target_db = voice_peak + below_db             # đỉnh nhạc mong muốn (dưới giọng)
    gain_db = (target_db - music_peak) if music_peak is not None else target_db
    gain_db = min(gain_db, 0.0)                    # không khuếch đại nhạc vượt gốc

    filt = (f"[1:a]volume={gain_db:.2f}dB,afade=t=in:d=1.0,"
            f"aresample=44100[bg];"
            f"[0:a][bg]amix=inputs=2:duration=first:normalize=0[a]")
    cmd = [ffmpeg, "-y", "-i", str(voice_wav),
           "-stream_loop", "-1", "-i", str(music_file),   # lặp nhạc cho đủ dài
           "-filter_complex", filt, "-map", "[a]",
           "-c:a", "pcm_s16le", str(out_wav)]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0 or not out_wav.exists():
        raise RuntimeError(f"ffmpeg mix nhạc lỗi: {(r.stderr or '')[-300:] or r.returncode}")
    return out_wav


def _render_tiktok_caption_png(text: str, out_png: Path, canvas=(1080, 1920),
                               y_ratio: float = 0.40) -> Path | None:
    """Vẽ 'Mimi audio Số ..' ĐẸP lên PNG TRONG SUỐT đúng khung dọc, TÂM ở ~y_ratio
    chiều cao (0.40 = 40%). Trả về out_png, hoặc None nếu lỗi.

    Thiết kế: nền pill bo góc bán trong suốt + VIỀN vàng + bóng đổ mềm; chữ tô
    GRADIENT vàng→cam có VIỀN tối. Dùng PIL (tiếng Việt có dấu tốt) → tránh
    drawtext/escaping của ffmpeg.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageFilter
    except Exception as e:
        logging.warning(f"Không tạo được chữ TikTok (thiếu PIL): {e}")
        return None
    W, H = canvas
    # Font đậm hỗ trợ tiếng Việt (thử vài font Windows quen thuộc).
    font = None
    for fp, sz in [("C:/Windows/Fonts/segoeuib.ttf", 78),
                   ("C:/Windows/Fonts/arialbd.ttf", 78),
                   ("C:/Windows/Fonts/tahomabd.ttf", 74),
                   ("C:/Windows/Fonts/arial.ttf", 78)]:
        try:
            font = ImageFont.truetype(fp, size=sz)
            break
        except Exception:
            continue
    if font is None:
        font = ImageFont.load_default()

    base = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    measure = ImageDraw.Draw(base)
    stroke = 4
    l, t, r, b = measure.textbbox((0, 0), text, font=font, stroke_width=stroke)
    tw, th = r - l, b - t
    cx, cy = W / 2, H * y_ratio

    # ── Nền pill bo góc + viền vàng + bóng đổ mềm ──
    pad_x, pad_y = 54, 30
    pw, ph = tw + pad_x * 2, th + pad_y * 2
    x0, y0, x1, y1 = cx - pw / 2, cy - ph / 2, cx + pw / 2, cy + ph / 2
    radius = int(ph / 2)
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle([x0, y0 + 8, x1, y1 + 8], radius=radius,
                                             fill=(0, 0, 0, 130))
    base = Image.alpha_composite(base, shadow.filter(ImageFilter.GaussianBlur(12)))
    panel = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(panel).rounded_rectangle([x0, y0, x1, y1], radius=radius,
                                            fill=(25, 12, 35, 190),
                                            outline=(255, 205, 60, 255), width=6)
    base = Image.alpha_composite(base, panel)

    # ── Chữ: viền tối vẽ trước, rồi tô gradient vàng→cam qua mask ──
    tx = cx - tw / 2 - l
    ty = cy - th / 2 - t
    outline = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(outline).text((tx, ty), text, font=font, fill=(0, 0, 0, 0),
                                 stroke_width=stroke, stroke_fill=(70, 25, 0, 255))
    base = Image.alpha_composite(base, outline)
    grad = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    top_c, bot_c = (255, 244, 170), (255, 138, 20)
    gy0, gy1 = int(cy - th / 2), int(cy + th / 2)
    for yy in range(gy0, gy1 + 1):
        f = (yy - gy0) / max(1, gy1 - gy0)
        col = tuple(int(top_c[i] + (bot_c[i] - top_c[i]) * f) for i in range(3))
        gd.line([(int(x0), yy), (int(x1), yy)], fill=col + (255,))
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).text((tx, ty), text, font=font, fill=255)
    base.paste(grad, (0, 0), mask)

    try:
        out_png.parent.mkdir(parents=True, exist_ok=True)
        base.save(str(out_png))
        return out_png
    except Exception as e:
        logging.warning(f"Không lưu được ảnh chữ TikTok: {e}")
        return None


def _play_done_sound(success: bool = True) -> None:
    """Phát âm báo khi chạy xong (async, không chặn; bỏ qua nếu không phát được)."""
    try:
        import winsound
        # SystemAsterisk = báo nhẹ khi hoàn tất; SystemHand = âm báo lỗi.
        alias = "SystemAsterisk" if success else "SystemHand"
        winsound.PlaySound(alias, winsound.SND_ALIAS | winsound.SND_ASYNC)
    except Exception:
        pass


class _NullWidget:
    """Nút giả cho run_tts khi chạy ở chế độ batch (không có nút thật để bật/tắt)."""
    def config(self, *args, **kwargs):
        pass
    configure = config


def run_tts(mode, voice_param, chunks, output, progress_var, status_var, btn_run, btn_pause, btn_preview, pause_event, make_video=False, effect=None, cut_audio=False, cut_target=12.0, cut_min=10.0, cut_max=15.0, make_video_doc=False, doc_full_audio=False, doc_speed=1.0, ngang_speed=1.0, cut_half=False, reuse=False, doc_from_ngang=False, doc_no_effect=False, ngang_out=None, doc_out=None, make_tiktok=False, tiktok_out=None, tiktok_speed=1.0, tiktok_no_effect=False, tiktok_caption=None, tiktok_caption_pos=40, tiktok_music=False, tiktok_music_db=-12.0):
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
                                        skip_existing=reuse_audio, output=ngang_out)
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
                elif ngang_out and Path(ngang_out).exists():
                    ngang_src = Path(ngang_out)   # bản tự động: YOUTUBE.mp4 đã có
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
                                           source_video=ngang_src, output=doc_out)
                progress_var.set(100)
                status_var.set(f"Xong! Video dọc → {vdoc_out.name}")
                logging.info(f"Đã tạo video dọc → {vdoc_out.name}")
            except Exception as e:
                logging.error(f"Lỗi dựng video dọc: {e}")
                status_var.set(f"Lỗi video dọc: {e}")

        # ── (TÙY CHỌN) VIDEO TIKTOK — 10 phút ĐẦU của audio, ghép NGUYÊN video
        #    trong videodoc/ (KHÔNG dùng lại video ngang). File riêng để đăng TikTok.
        if make_tiktok:
            from video_doc import build_video_doc
            from video_timclip import (cut_audio_at_sentence_end,
                                       probe_audio_duration)
            # 1) Audio: lấy ~10 phút đầu, cắt ở CUỐI CÂU (khoảng lặng) nên không cần
            #    chuẩn 10 phút. Audio ≤ ~10 phút → dùng nguyên; cắt lỗi cũng dùng nguyên.
            tk_audio = output_path
            try:
                total_sec = probe_audio_duration(output_path)
            except Exception:
                total_sec = 0.0
            if total_sec > 10.5 * 60:
                tk_wav = output_path.with_name(output_path.stem + "_tiktok" + output_path.suffix)
                if reuse_audio and tk_wav.exists() and tk_wav.stat().st_size > 4096:
                    tk_audio = tk_wav
                    logging.info(f"♻ Dùng lại audio TikTok đã có: {tk_wav.name}")
                else:
                    status_var.set("Đang cắt 10 phút đầu cho TikTok...")
                    try:
                        cut_seconds, _ = cut_audio_at_sentence_end(
                            output_path, tk_wav,
                            target_minutes=10.0, min_minutes=9.0, max_minutes=11.0,
                            silence_db=-35.0, min_silence=0.5)
                        tk_audio = tk_wav
                        m, s = divmod(cut_seconds, 60)
                        logging.info(f"✂ Audio TikTok: cắt tại {int(m)}:{s:05.2f} → {tk_wav.name}")
                    except Exception as e:
                        logging.warning(f"Không cắt được 10 phút cho TikTok (dùng audio đầy đủ): {e}")
                        tk_audio = output_path
            else:
                logging.info(f"🎵 Audio ~{total_sec/60:.1f} phút (≤10) → TikTok dùng nguyên audio.")

            # 1b) Tăng tốc audio (giữ cao độ) nếu chọn mức > 1.0 — như video ngang/dọc.
            if tiktok_speed and tiktok_speed > 1.001:
                status_var.set(f"Đang tăng tốc audio x{tiktok_speed:.2f} cho TikTok...")
                try:
                    tk_audio = _speedup_audio_for_doc(tk_audio, tiktok_speed)
                    logging.info(f"⏩ Tăng tốc audio TikTok x{tiktok_speed:.2f} → {tk_audio.name}")
                except Exception as e:
                    logging.warning(f"Không tăng tốc được audio TikTok (giữ tốc độ gốc): {e}")

            # 1c) Chèn NHẠC NỀN (từ Music/), mix nhỏ hơn giọng |tiktok_music_db| dB.
            if tiktok_music:
                musics = list_music_files()
                if not musics:
                    logging.warning(f"🎼 Bật nhạc nền nhưng {MUSIC_DIR} trống → bỏ qua nhạc.")
                else:
                    import random as _rnd
                    music_file = MUSIC_DIR / _rnd.choice(musics)
                    mix_out = (Path(tiktok_out).with_name(Path(tiktok_out).stem + "_bgm.wav")
                               if tiktok_out
                               else tk_audio.with_name(tk_audio.stem + "_bgm.wav"))
                    if reuse_audio and mix_out.exists() and mix_out.stat().st_size > 4096:
                        tk_audio = mix_out
                        logging.info(f"♻ Dùng lại audio TikTok + nhạc đã có: {mix_out.name}")
                    else:
                        status_var.set("Đang chèn nhạc nền cho TikTok...")
                        try:
                            tk_audio = _mix_bg_music(tk_audio, music_file,
                                                     float(tiktok_music_db), mix_out)
                            logging.info(f"🎼 Nhạc nền: {music_file.name} (≈{tiktok_music_db:.0f}dB "
                                         f"dưới giọng) → {mix_out.name}")
                        except Exception as e:
                            logging.warning(f"Không chèn được nhạc nền (giữ giọng gốc): {e}")

            # 2) Dựng video dọc từ kho videodoc/ (nguyên video, source_video=None).
            #    Tên riêng để KHÔNG đè video dọc (facebook/output_doc).
            tk_video_out = (Path(tiktok_out) if tiktok_out
                            else output_path.with_name(output_path.stem + "_tiktok.mp4"))
            # Chữ overlay 'Mimi audio Số …' ở vị trí % chiều cao do người dùng chọn.
            cap_png = None
            if tiktok_caption:
                y_ratio = max(0.0, min(tiktok_caption_pos / 100.0, 1.0))
                cap_tmp = tk_video_out.with_name(tk_video_out.stem + "_caption.png")
                cap_png = _render_tiktok_caption_png(tiktok_caption, cap_tmp, y_ratio=y_ratio)
                if cap_png:
                    logging.info(f"🔤 Chữ TikTok (≈{tiktok_caption_pos}% cao): {tiktok_caption!r}")
            status_var.set("Đang dựng video TikTok...")
            logging.info(f"Bắt đầu dựng video TikTok từ {tk_audio.name} (kho videodoc/)...")
            try:
                progress_var.set(0)
                tk_effect = None if tiktok_no_effect else effect
                tk_out = build_video_doc(tk_audio, log=logging.info, effect=tk_effect,
                                         progress=_video_progress("🎵 Dựng video TikTok..."),
                                         skip_existing=reuse_audio,
                                         source_video=None, output=tk_video_out,
                                         caption_png=cap_png)
                progress_var.set(100)
                status_var.set(f"Xong! Video TikTok → {tk_out.name}")
                logging.info(f"Đã tạo video TikTok → {tk_out.name}")
            except Exception as e:
                logging.error(f"Lỗi dựng video TikTok: {e}")
                status_var.set(f"Lỗi video TikTok: {e}")
            finally:
                # Dọn ảnh chữ tạm (đã nung vào video). Bỏ qua nếu Windows còn khóa.
                if cap_png:
                    try:
                        Path(cap_png).unlink(missing_ok=True)
                    except OSError:
                        pass

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
        self._log_boxes = []          # mọi ô nhật ký (panel video + tab kịch bản) — cùng nhận log
        self._setup_logging()
        self._build_ui()
        self._poll_log()
        self.update_idletasks()
        self.minsize(1280, 680)
        self._center(1560, 720)   # đủ rộng/cao cho Home + tab Thumbnail (các nút không bị che)

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

    def _bring_to_front(self):
        """Đưa cửa sổ GUI lên trên cùng + lấy focus (vd khi đang làm việc ở VS Code).

        Dùng để bật lên ở bước tạo giọng. Gọi được TỪ THREAD batch: thực thi qua
        self.after(0, ...) cho chạy trên main thread (Tk không an toàn đa luồng).
        Mẹo topmost True→False để cửa sổ bật lên trước mà KHÔNG kẹt 'luôn trên cùng'.
        """
        def _do():
            try:
                if self.state() == "iconic":
                    self.deiconify()             # phòng khi đang thu nhỏ
                self.lift()
                self.attributes("-topmost", True)
                self.update_idletasks()
                self.attributes("-topmost", False)
                self.focus_force()
            except Exception:
                pass
        try:
            self.after(0, _do)
        except Exception:
            pass

    def _setup_logging(self):
        handler = QueueHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%H:%M:%S"))
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(logging.INFO)

    def _build_ui(self):
        root = ttk.Frame(self, padding=18)
        root.grid(sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        # 2 vùng: [nút nhỏ chuyển view] · [nội dung]  (Nhật ký nằm trong panel video)
        root.columnconfigure(0, weight=0)   # sidebar nút nhỏ
        root.columnconfigure(1, weight=1)   # nội dung view
        root.rowconfigure(0, weight=1)

        # ── Sidebar trái: 3 nút nhỏ — Home (đầy đủ) · Tạo kịch bản · Giọng nói ──
        side = ttk.Frame(root)
        side.grid(row=0, column=0, sticky="n", padx=(0, 14))
        self._nav_buttons = {}
        for key, label in [("home",   "🏠  Home\n(đầy đủ)"),
                           ("script", "🛠  Tạo\nkịch bản"),
                           ("voice",  "🎧  Giọng\nnói"),
                           ("thumb",  "🖼  Thumb\nnail"),
                           ("copy",   "📑  Copy\nSEO"),
                           ("report", "📋  Tiến\nđộ")]:
            b = ttk.Button(side, text=label, width=11,
                           command=lambda k=key: self._show_view(k))
            b.pack(fill="x", pady=(0, 8))
            self._nav_buttons[key] = b

        # ── Vùng nội dung: 3 panel (pipeline · TTS · video) HIỆN/ẨN theo view ──
        # Mỗi panel chỉ dựng MỘT lần (không trùng widget); nút chỉ bật/tắt hiển thị
        # bằng grid()/grid_remove(). Home = hiện cả 3 → đúng giao diện gốc đầy đủ.
        content = ttk.Frame(root)
        content.grid(row=0, column=1, sticky="nsew", padx=(0, 16))
        self._content = content
        content.rowconfigure(0, weight=1)
        content.columnconfigure(0, weight=0)   # pipeline
        content.columnconfigure(1, weight=0)   # TTS
        content.columnconfigure(2, weight=1)   # video/hành động (giãn)

        frame_pipeline = ttk.Frame(content)
        frame_pipeline.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        frame_pipeline.columnconfigure(0, weight=1)
        frame_pipeline.rowconfigure(0, weight=1)

        frame_tts = ttk.Frame(content)
        frame_tts.grid(row=0, column=1, sticky="nsew", padx=(0, 16))
        frame_tts.columnconfigure(0, weight=1)
        frame_tts.rowconfigure(0, weight=1)

        frame_video = ttk.Frame(content)
        frame_video.grid(row=0, column=2, sticky="nsew")
        frame_video.columnconfigure(0, weight=1)
        frame_video.rowconfigure(0, weight=1)

        self._panels = {"pipeline": frame_pipeline, "tts": frame_tts,
                        "video": frame_video}

        # Panel Thumbnail — nhúng YOUTUBE/thumbnail_gui.py; phủ cả vùng nội dung khi chọn.
        frame_thumb = ttk.Frame(content)
        frame_thumb.grid(row=0, column=0, columnspan=3, sticky="nsew")
        frame_thumb.rowconfigure(0, weight=1)
        frame_thumb.columnconfigure(0, weight=1)
        self._panels["thumbnail"] = frame_thumb
        self._build_thumbnail_panel(frame_thumb)

        # Panel Tiến độ — bảng các link đã gửi (manifest) + đã làm tới đâu.
        frame_report = ttk.Frame(content)
        frame_report.grid(row=0, column=0, columnspan=3, sticky="nsew")
        frame_report.rowconfigure(0, weight=1)
        frame_report.columnconfigure(0, weight=1)
        self._panels["report"] = frame_report
        self._build_report_panel(frame_report)

        # Panel Copy SEO — danh sách tập (thư mục số trong kịch_bản) + copy tiêu đề/mô tả/thẻ tag.
        frame_copyseo = ttk.Frame(content)
        frame_copyseo.grid(row=0, column=0, columnspan=3, sticky="nsew")
        frame_copyseo.rowconfigure(0, weight=1)
        frame_copyseo.columnconfigure(0, weight=1)
        self._panels["copyseo"] = frame_copyseo
        self._build_copyseo_panel(frame_copyseo)

        # ════════════════════════════════════════════════
        # PANEL pipeline — Quy trình tạo kịch bản (nhận diện → Gemini → SEO → input.txt)
        # ════════════════════════════════════════════════
        self._build_pipeline_column(frame_pipeline, 0)

        # ════════════════════════════════════════════════
        # PANEL TTS — toàn bộ điều khiển TTS
        # ════════════════════════════════════════════════
        left = ttk.Frame(frame_tts)
        left.grid(row=0, column=0, sticky="nsew")
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
        # PANEL video — Video dọc + Hành động + tiến trình
        # ════════════════════════════════════════════════
        right = ttk.Frame(frame_video)
        right.grid(row=0, column=0, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(6, weight=1)   # ô nhật ký (dưới 'Sẵn sàng') giãn theo chiều cao

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

        # ── Video TikTok (group riêng, DƯỚI 'Video dọc', TRÊN nút Chạy) ──
        # Lấy ~10 phút ĐẦU của audio (cắt ở cuối câu) + ghép NGUYÊN video trong
        # videodoc/ → 1 video dọc riêng để đăng TikTok.
        tiktok = ttk.LabelFrame(right, text="  🎵  Video TikTok (10 phút đầu)  ")
        tiktok.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        self.var_make_tiktok = tk.BooleanVar(value=self._opt_settings["make_tiktok"])
        ttk.Checkbutton(tiktok, text="Tạo video TikTok (từ kho videodoc)",
                        variable=self.var_make_tiktok).pack(anchor="w")
        tiktok_opts = ttk.Frame(tiktok)
        tiktok_opts.pack(anchor="w", fill="x", pady=(6, 0))
        ttk.Label(tiktok_opts, text="Tăng tốc:").pack(side="left", padx=(0, 2))
        self.var_tiktok_speed = tk.StringVar(value=self._opt_settings["tiktok_speed"])
        ttk.Combobox(tiktok_opts, textvariable=self.var_tiktok_speed, width=6,
                     values=["1.0", "1.05", "1.1", "1.15", "1.2", "1.25"]).pack(side="left")
        ttk.Label(tiktok_opts, text="x (giữ cao độ)",
                  style="Hint.TLabel").pack(side="left", padx=(4, 0))
        # Không phủ hiệu ứng lên video TikTok (video sạch hiệu ứng).
        tiktok_opts2 = ttk.Frame(tiktok)
        tiktok_opts2.pack(anchor="w", fill="x", pady=(6, 0))
        self.var_tiktok_no_effect = tk.BooleanVar(value=self._opt_settings["tiktok_no_effect"])
        ttk.Checkbutton(tiktok_opts2, text="🚫  Không áp hiệu ứng cho TikTok",
                        variable=self.var_tiktok_no_effect).pack(side="left")
        # Vị trí chữ theo chiều cao (0 = trên cùng, 100 = dưới cùng).
        tiktok_opts3 = ttk.Frame(tiktok)
        tiktok_opts3.pack(anchor="w", fill="x", pady=(6, 0))
        ttk.Label(tiktok_opts3, text="Vị trí chữ (% cao):").pack(side="left", padx=(0, 6))
        self.var_tiktok_caption_pos = tk.IntVar(value=self._opt_settings["tiktok_caption_pos"])
        ttk.Spinbox(tiktok_opts3, from_=5, to=95, increment=5,
                    textvariable=self.var_tiktok_caption_pos, width=5).pack(side="left")
        ttk.Label(tiktok_opts3, text="(0 = trên, 100 = dưới)",
                  style="Hint.TLabel").pack(side="left", padx=(6, 0))
        # Nhạc nền (từ Music/) + mức nhỏ hơn giọng (dB). Giọng ≈ -6dB → -12 = nhạc ≈ -18dB.
        tiktok_opts4 = ttk.Frame(tiktok)
        tiktok_opts4.pack(anchor="w", fill="x", pady=(6, 0))
        self.var_tiktok_music = tk.BooleanVar(value=self._opt_settings["tiktok_music"])
        ttk.Checkbutton(tiktok_opts4, text="🎼  Chèn nhạc nền (Music/)",
                        variable=self.var_tiktok_music).pack(side="left")
        ttk.Label(tiktok_opts4, text="nhỏ hơn giọng:").pack(side="left", padx=(10, 2))
        self.var_tiktok_music_db = tk.IntVar(value=self._opt_settings["tiktok_music_db"])
        ttk.Spinbox(tiktok_opts4, from_=-30, to=0, increment=1,
                    textvariable=self.var_tiktok_music_db, width=5).pack(side="left")
        ttk.Label(tiktok_opts4, text="dB", style="Hint.TLabel").pack(side="left", padx=(4, 0))

        # ── Hành động (Chạy / Tạm dừng / Nghe thử) ──
        act = ttk.Frame(right)
        act.grid(row=2, column=0, sticky="ew", pady=(0, 8))
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
        act2.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        ttk.Button(act2, text="🗑  Xóa output", command=self._clear_output).pack(side="left")
        # ♻ Dùng lại audio/video đã có: bỏ qua tạo giọng nếu output.wav còn đúng
        # văn bản/giọng, và bỏ qua video nào đã dựng — chỉ dựng phần còn thiếu.
        # Mặc định TẮT (mỗi lần mở app) để tránh vô tình dùng lại bản cũ.
        self.var_reuse = tk.BooleanVar(value=False)
        ttk.Checkbutton(act2, text="♻  Dùng lại audio/video đã có (chỉ dựng phần còn thiếu)",
                        variable=self.var_reuse).pack(side="left", padx=(16, 0))

        # ── Đưa cửa sổ lên trước khi tạo giọng (mỗi link 1 lần) ──
        # Hữu ích khi chạy nền: tới bước clone giọng thì GUI tự bật lên trên (vd
        # đang làm việc ở VS Code) để dễ theo dõi / ưu tiên CPU+GPU cho app.
        act3 = ttk.Frame(right)
        act3.grid(row=4, column=0, sticky="ew", pady=(0, 10))
        self.var_bring_front = tk.BooleanVar(value=self._opt_settings["bring_front"])
        ttk.Checkbutton(act3,
                        text="⬆️  Đưa cửa sổ lên trước khi tạo giọng (mỗi link 1 lần)",
                        variable=self.var_bring_front).pack(side="left")

        # ── Tiến trình ──
        prog_frame = ttk.Frame(right)
        prog_frame.grid(row=5, column=0, sticky="ew", pady=(0, 10))
        prog_frame.columnconfigure(0, weight=1)
        self.progress = tk.IntVar(value=0)
        self.progress_bar = ttk.Progressbar(prog_frame, variable=self.progress,
                                            maximum=100, mode="determinate")
        self.progress_bar.grid(row=0, column=0, sticky="ew")
        self.status = tk.StringVar(value="Sẵn sàng.")
        ttk.Label(prog_frame, textvariable=self.status,
                  style="Sub.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))

        # ── Nhật ký: nằm DƯỚI dòng 'Sẵn sàng' trong panel video (giống gốc) ──
        self._build_log_panel(right, 6)
        self._show_view("home")   # mặc định mở Home (đầy đủ như giao diện gốc)

    def _show_view(self, key):
        """Hiện/ẩn 3 panel theo view và làm nổi nút đang chọn:
        • home   → cả 3 panel (giống giao diện gốc đầy đủ)
        • script → chỉ panel quy trình tạo kịch bản
        • voice  → panel TTS + panel video/hành động
        Ô nhật ký luôn hiển thị (nằm ngoài 3 panel)."""
        show = {
            "home":   ("pipeline", "tts", "video"),
            "script": ("pipeline",),
            "voice":  ("tts", "video"),
            "thumb":  ("thumbnail",),
            "copy":   ("copyseo",),
            "report": ("report",),
        }[key]
        for name, fr in self._panels.items():
            if name in show:
                fr.grid()
            else:
                fr.grid_remove()
        if key == "report":
            self._refresh_report()   # cập nhật bảng tiến độ mỗi khi mở tab
        elif key == "copy":
            self._refresh_copyseo()  # quét lại danh sách tập mỗi khi mở tab
        # Riêng tab "Tạo kịch bản": dàn 3 bước theo NGANG + hiện nhật ký, lấp đầy
        # chiều rộng. Ở Home/Giọng nói: pipeline là cột DỌC hẹp (như giao diện gốc).
        is_script = (key == "script")
        self._pipeline_set_layout(horizontal=is_script)
        self._content.columnconfigure(0, weight=1 if is_script else 0)
        for k, b in self._nav_buttons.items():
            b.configure(style="Accent.TButton" if k == key else "TButton")

    def _pipeline_set_layout(self, horizontal: bool):
        """Sắp lại các bước ①②③ của 'Tạo kịch bản':
        • horizontal=True  → 3 bước dàn ngang, nhật ký bên phải (tab xem riêng).
        • horizontal=False → cột dọc hẹp, ẩn nhật ký (Home/Giọng nói)."""
        w = self._pipe_wrap
        s1, s2, s3 = self._pipe_steps
        if horizontal:
            for c, wt in ((0, 0), (1, 0), (2, 0), (3, 1)):
                w.columnconfigure(c, weight=wt)
            w.rowconfigure(1, weight=1)
            self._pipe_hdr.grid_configure(row=0, column=0, columnspan=3, sticky="w")
            s1.grid_configure(row=1, column=0, columnspan=1, sticky="new", padx=(0, 12))
            s2.grid_configure(row=1, column=1, columnspan=1, sticky="new", padx=(0, 12))
            s3.grid_configure(row=1, column=2, columnspan=1, sticky="new", padx=(0, 12))
            self._pipe_pf.grid_configure(row=2, column=0, columnspan=3, sticky="ew")
            self._pipe_btn_open.grid_configure(row=3, column=0, columnspan=3, sticky="w")
            self._pipe_btn_reset.grid_configure(row=4, column=0, columnspan=3, sticky="w")
            self._pipe_log_frame.grid()
            self._batch_ctrl_frame.grid()        # nút Tạm dừng/Dừng: hiện ở tab Tạo kịch bản
        else:
            for c, wt in ((0, 1), (1, 0), (2, 0), (3, 0)):
                w.columnconfigure(c, weight=wt)
            w.rowconfigure(1, weight=0)
            self._pipe_hdr.grid_configure(row=0, column=0, columnspan=1, sticky="ew")
            s1.grid_configure(row=1, column=0, columnspan=1, sticky="ew", padx=0)
            s2.grid_configure(row=2, column=0, columnspan=1, sticky="ew", padx=0)
            s3.grid_configure(row=3, column=0, columnspan=1, sticky="ew", padx=0)
            self._pipe_pf.grid_configure(row=4, column=0, columnspan=1, sticky="ew")
            self._pipe_btn_open.grid_configure(row=5, column=0, columnspan=1, sticky="w")
            self._pipe_btn_reset.grid_configure(row=6, column=0, columnspan=1, sticky="w")
            self._pipe_log_frame.grid_remove()
            self._batch_ctrl_frame.grid_remove()  # ẩn nút Tạm dừng/Dừng ở Home/Giọng nói

    # ── TAB TIẾN ĐỘ: bảng các link đã gửi (manifest) + đã làm tới đâu ────────────
    # Thứ tự bước hiển thị trong cột "Tiến độ" (nhãn ngắn + khoá trong steps dict).
    _REPORT_STEPS = (("Dịch", "translate"), ("SEO", "seo"), ("Thumb", "thumbnail"),
                     ("Giọng", "audio"), ("Vid ngang", "video_ngang"),
                     ("Vid dọc", "video_doc"))

    def _build_report_panel(self, parent):
        wrap = ttk.Frame(parent, padding=4)
        wrap.grid(row=0, column=0, sticky="nsew")
        wrap.columnconfigure(0, weight=1)
        wrap.rowconfigure(2, weight=1)

        hdr = ttk.Frame(wrap)
        hdr.grid(row=0, column=0, sticky="ew")
        ttk.Label(hdr, text="📋  Tiến độ các link đã gửi", style="Header.TLabel").pack(side="left")
        ttk.Label(wrap, text="Mỗi link nhớ ĐÚNG số tập của nó. Chạy lại (chưa xóa output) "
                  "sẽ tiếp tục đúng tập còn dở. ✅ = xong · 🟡 = đang dở · 🔴 = chưa làm.",
                  style="Sub.TLabel").grid(row=1, column=0, sticky="w", pady=(2, 8))

        bar = ttk.Frame(wrap)
        bar.grid(row=2, column=0, sticky="ew")
        bar.columnconfigure(0, weight=1)
        # Bảng
        table = ttk.Frame(bar)
        table.grid(row=0, column=0, sticky="nsew")
        bar.rowconfigure(0, weight=1)
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        cols = ("st", "episode", "progress", "source", "updated")
        tv = ttk.Treeview(table, columns=cols, show="headings")
        for c, t, w, anchor in (("st", "", 34, "center"), ("episode", "Tập", 50, "center"),
                                ("progress", "Tiến độ", 360, "w"),
                                ("source", "Nguồn (link/file)", 380, "w"),
                                ("updated", "Cập nhật", 140, "w")):
            tv.heading(c, text=t)
            tv.column(c, width=w, anchor=anchor, stretch=(c == "source"))
        tv.grid(row=0, column=0, sticky="nsew")
        vs = ttk.Scrollbar(table, orient="vertical", command=tv.yview)
        vs.grid(row=0, column=1, sticky="ns")
        tv.configure(yscrollcommand=vs.set)
        self._report_tv = tv

        foot = ttk.Frame(wrap)
        foot.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(foot, text="🔄  Làm mới", command=self._refresh_report).pack(side="left")
        ttk.Button(foot, text="▶  Chạy tiếp tập đang chọn", style="Accent.TButton",
                   command=self._resume_selected_folder).pack(side="left", padx=(12, 0))
        self.report_summary = tk.StringVar(value="")
        ttk.Label(foot, textvariable=self.report_summary,
                  style="Sub.TLabel").pack(side="left", padx=(12, 0))
        # Nhấp đúp 1 dòng = chạy tiếp tập đó.
        tv.bind("<Double-1>", lambda e: self._resume_selected_folder())

    def _refresh_report(self):
        """Đổ lại bảng tiến độ từ manifest + quét cả thư mục tập chưa có trong manifest."""
        tv = getattr(self, "_report_tv", None)
        if tv is None:
            return
        tv.delete(*tv.get_children())
        m = load_manifest()
        # Gộp: mục manifest (theo episode) + thư mục tập rời chưa có trong manifest.
        rows = {}   # episode(int) -> (source, entry|None)
        for src, e in m.items():
            ep = e.get("episode", "")
            if str(ep).isdecimal():
                rows[int(ep)] = (e.get("source", src), e)
        if SCRIPT_DIR.exists():
            for p in sorted(SCRIPT_DIR.iterdir()):
                if p.is_dir() and p.name.isdecimal() and int(p.name) not in rows:
                    rows[int(p.name)] = ("(không rõ — tạo trước khi có manifest)", None)

        n_done = 0
        for ep in sorted(rows):
            src, e = rows[ep]
            episode = str(ep).zfill(2)
            steps = (e or {}).get("steps") or self._folder_steps(SCRIPT_DIR / episode, episode)
            done = bool((e or {}).get("done")) if e else all(
                steps.get(k) for _, k in self._REPORT_STEPS if k != "video_doc")
            prog = "  ".join(("✅" if steps.get(k) else "⬜") + lbl
                             for lbl, k in self._REPORT_STEPS)
            mark = "✅" if done else ("🟡" if any(steps.values()) else "🔴")
            if done:
                n_done += 1
            updated = (e or {}).get("updated", "")
            tv.insert("", "end", values=(mark, episode, prog, src[:90], updated))
        self.report_summary.set(
            f"{len(rows)} tập • {n_done} hoàn tất • manifest: {MANIFEST_FILE}")

    def _resume_selected_folder(self):
        """Chạy TIẾP 1 tập đang chọn trong bảng — KHÔNG cần link gốc nếu đã có
        bản nhận diện (*_zh.docx). Chỉ làm các bước còn thiếu (vd chỉ còn video)."""
        if self._pipe_busy:
            messagebox.showinfo("Đang bận", "Đang có tác vụ chạy — đợi xong đã nhé.")
            return
        tv = getattr(self, "_report_tv", None)
        sel = tv.selection() if tv else None
        if not sel:
            messagebox.showinfo("Chọn tập", "Hãy chọn 1 tập trong bảng rồi bấm 'Chạy tiếp'.")
            return
        episode = str(tv.item(sel[0], "values")[1]).strip().zfill(2)
        folder = SCRIPT_DIR / episode
        if not folder.exists():
            messagebox.showwarning("Không có thư mục", f"Không thấy thư mục tập {episode}.")
            return
        # Không có link gốc vẫn chạy tiếp được MIỄN LÀ đã nhận diện (có *_zh.docx).
        if not next(iter(folder.glob("*_zh.docx")), None):
            messagebox.showwarning(
                "Thiếu bản nhận diện",
                f"Tập {episode} chưa có *_zh.docx nên KHÔNG thể chạy tiếp mà thiếu link "
                "gốc (cần nhận diện lại). Hãy chạy lại link đó ở tab 'Tạo kịch bản'.")
            return
        tts_settings = self._collect_tts_settings()   # main thread (đọc tk.Var)
        if tts_settings is None:
            return   # cấu hình giọng sai → đã cảnh báo
        self._pipe_set_busy(True)
        self.pipe_progress.set(0)
        self.pipe_link_status.set(f"▶ Chuẩn bị chạy tiếp tập {episode}...")
        self._show_view("script")   # chuyển sang tab có thanh tiến trình + nhật ký
        threading.Thread(target=self._resume_folder_worker,
                         args=(folder, episode, tts_settings), daemon=True).start()

    def _resume_folder_worker(self, folder, episode, tts_settings):
        """Chạy tiếp 1 thư mục tập đã có sẵn (bỏ qua bước đã xong, làm phần còn thiếu).
        Dùng lại toàn bộ logic resume/bỏ-qua như batch nhưng cho ĐÚNG 1 tập."""
        import datetime as _dt
        driver = None
        file_handler = None
        try:
            import nhandien_giongnoi as recog
            import dich_gemini as g
            youtube_dir = str(YOUTUBE_DIR)
            if youtube_dir not in sys.path:
                sys.path.insert(0, youtube_dir)
            import seo_youtube_gemini as seo
            prefix = load_prefix()
            try:
                file_handler = logging.FileHandler(SCRIPT_DIR / "batch_log.txt", encoding="utf-8")
                file_handler.setFormatter(
                    logging.Formatter("%(asctime)s  %(message)s", "%Y-%m-%d %H:%M:%S"))
                logging.getLogger().addHandler(file_handler)
                logging.info("\n" + "═" * 12 + f" CHẠY TIẾP TẬP {episode} "
                             f"({_dt.datetime.now():%Y-%m-%d %H:%M:%S}) " + "═" * 12)
            except Exception:
                pass

            # Nguồn (lấy từ manifest nếu có) — chỉ để ghi log/manifest, KHÔNG cần để chạy.
            m = load_manifest()
            src = next((s for s, e in m.items()
                        if str(e.get("episode", "")).zfill(2) == episode), str(folder))

            gemini_docx = folder / "gemini_result.docx"
            input_txt = folder / "input.txt"
            seo_docx = folder / "seoYoutube.docx"

            # 1+2) Nhận diện: dùng lại *_zh.docx (đã kiểm tra có ở nút bấm).
            existing_zh = next(iter(sorted(folder.glob("*_zh.docx"))), None)
            chunks = read_zh_docx_chunks(existing_zh) if existing_zh else []
            if not chunks:
                logging.error(f"❌ Tập {episode}: không đọc được đoạn từ *_zh.docx.")
                self.pipe_status.set(f"❌ Tập {episode}: lỗi đọc nhận diện.")
                return
            logging.info(f"♻ Dùng lại nhận diện ({existing_zh.name}, {len(chunks)} đoạn).")

            # 3) Dịch Gemini — đủ thì bỏ qua; thiếu thì tiếp tục.
            if SKIP_TRANSLATE_DETAIL_CHECK and gemini_docx.exists():
                # [TẠM] Đã có gemini_result.docx → coi như DỊCH XONG, không dò từng đoạn
                # (tránh gửi lại đoạn đã dịch). Xem cờ SKIP_TRANSLATE_DETAIL_CHECK ở đầu file.
                translated_now = False
                translation_ok = True
                logging.info(f"♻ Bỏ qua dịch Gemini — đã có {gemini_docx.name} "
                             f"(TẠM tắt kiểm từng đoạn).")
            else:
                prior = (g.read_results_docx(gemini_docx, len(chunks))
                         if gemini_docx.exists() else [None] * len(chunks))
                n_todo = sum(1 for r in prior if not g.is_translation_done(r))
                translated_now = n_todo > 0
                if n_todo == 0:
                    logging.info(f"♻ Bỏ qua dịch Gemini (đã đủ {len(chunks)} đoạn).")
                else:
                    logging.info(f"🌐 Mở Firefox dịch {n_todo}/{len(chunks)} đoạn còn thiếu...")
                    driver = g.init_firefox()
                    results = g.send_chunks_to_gemini(
                        chunks, prefix=prefix, on_log=logging.info, out_path=gemini_docx,
                        driver=driver, keep_open=True, resume=True)
                    g.save_results_docx(chunks, results, gemini_docx)
                # ⛔ Dịch chưa xong → DỪNG, không tạo input/audio/video.
                translation_ok = self._translation_complete(gemini_docx, chunks, episode)

            if not translation_ok:
                self.pipe_status.set(f"⛔ Tập {episode}: dịch chưa xong — dừng.")
                self._manifest_update(src, episode, folder, done=False)
                return

            # 4) input.txt — tạo lại nếu vừa dịch (bản cũ có thể dở) hoặc chưa có.
            if translated_now or not (input_txt.exists() and input_txt.stat().st_size > 0):
                self._batch_prepare_input(gemini_docx, input_txt)

            # 5) SEO
            if not self._seo_docx_valid(seo_docx):
                if driver is None:
                    driver = g.init_firefox()
                logging.info("🔎 Tạo SEO YouTube...")
                seo.run(str(gemini_docx), str(seo_docx),
                        keep_open=True, log=logging.info, driver=driver)
            else:
                logging.info("♻ Bỏ qua SEO (đã có).")
            self._save_youtube_seo_copy(seo_docx, folder / "youtube_seo.txt", episode)

            # 6) Thumbnail (ngang + dọc) + cập nhật số tập
            if not (folder / f"thumbnail{episode}.png").exists() \
                    or not (folder / f"thumbnail{episode}_dọc.png").exists():
                self._make_thumbnail_for_folder(folder, episode)
            save_episode_number(max(load_episode_number(), int(episode)))
            # 7) Drive (idempotent)
            self._upload_input_script_to_drive(input_txt, episode)

            # Đóng Firefox trước khi render video (nhả RAM).
            if driver is not None:
                try:
                    driver.quit()
                except Exception:
                    pass
                driver = None

            # 8) Tạo giọng + video (reuse=True → chỉ render phần còn thiếu, vd video dọc).
            if tts_settings:
                try:
                    recog.free_model()
                except Exception:
                    pass
                self.pipe_status.set(f"🎧 Tập {episode}: đang tạo giọng + video...")
                self._batch_run_tts(folder, tts_settings, episode)

            self._manifest_update(src, episode, folder, done=True)
            self.pipe_progress.set(100)
            self.pipe_link_status.set(f"✅ Tập {episode} đã chạy tiếp xong.")
            self.pipe_status.set(f"✅ Tập {episode} hoàn tất.")
            logging.info(f"🎉 Tập {episode} chạy tiếp xong.")
        except Exception as e:
            import traceback
            logging.error(f"❌ Lỗi chạy tiếp tập {episode}: {e}")
            logging.error(traceback.format_exc())
            self.pipe_link_status.set(f"❌ Lỗi chạy tiếp tập {episode}.")
            self.pipe_status.set(f"Lỗi: {e}")
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except Exception:
                    pass
            try:
                import nhandien_giongnoi as recog
                recog.free_model()
            except Exception:
                pass
            if file_handler is not None:
                try:
                    logging.getLogger().removeHandler(file_handler)
                    file_handler.close()
                except Exception:
                    pass
            self._pipe_set_busy(False)

    # ── TAB COPY SEO: chọn 1 tập (thư mục số) → copy tiêu đề/mô tả/thẻ tag ───────
    def _build_copyseo_panel(self, parent):
        wrap = ttk.Frame(parent, padding=4)
        wrap.grid(row=0, column=0, sticky="nsew")
        wrap.columnconfigure(0, weight=1)
        wrap.rowconfigure(2, weight=1)

        hdr = ttk.Frame(wrap)
        hdr.grid(row=0, column=0, sticky="ew")
        ttk.Label(hdr, text="📑  Copy SEO theo tập", style="Header.TLabel").pack(side="left")
        ttk.Label(wrap, text="Chọn 1 tập (thư mục số trong kịch_bản) rồi copy Tiêu đề · Mô tả · Thẻ tag. "
                  "Tiêu đề mở đầu [FULL]; mô tả có #truyenfull #full; thẻ tag < 499 ký tự.",
                  style="Sub.TLabel").grid(row=1, column=0, sticky="w", pady=(2, 8))

        body = ttk.Frame(wrap)
        body.grid(row=2, column=0, sticky="nsew")
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        # Cột trái: danh sách tập có SEO.
        left = ttk.Frame(body)
        left.grid(row=0, column=0, sticky="ns", padx=(0, 12))
        left.rowconfigure(0, weight=1)
        lst = tk.Listbox(left, width=12, exportselection=False, activestyle="dotbox",
                         font=("Segoe UI", 10))
        lst.grid(row=0, column=0, sticky="ns")
        lsb = ttk.Scrollbar(left, orient="vertical", command=lst.yview)
        lsb.grid(row=0, column=1, sticky="ns")
        lst.configure(yscrollcommand=lsb.set)
        lst.bind("<<ListboxSelect>>", lambda e: self._copyseo_load_selected())
        self._copyseo_list = lst

        # Cột phải: 4 nút copy + xem trước nội dung.
        right = ttk.Frame(body)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        btns = ttk.Frame(right)
        btns.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(btns, text="📋  Tiêu đề", command=lambda: self._copyseo_copy("title")).pack(side="left")
        ttk.Button(btns, text="📋  Mô tả", command=lambda: self._copyseo_copy("desc")).pack(side="left", padx=(8, 0))
        ttk.Button(btns, text="📋  Thẻ tag", command=lambda: self._copyseo_copy("tags")).pack(side="left", padx=(8, 0))
        ttk.Button(btns, text="📋  Cả 3", style="Accent.TButton",
                   command=lambda: self._copyseo_copy("all")).pack(side="left", padx=(8, 0))

        txt = tk.Text(right, wrap="word", height=18, font=("Consolas", 10),
                      bg="white", relief="solid", borderwidth=1)
        txt.grid(row=1, column=0, sticky="nsew")
        tsb = ttk.Scrollbar(right, orient="vertical", command=txt.yview)
        tsb.grid(row=1, column=1, sticky="ns")
        txt.configure(yscrollcommand=tsb.set, state="disabled")
        self._copyseo_text = txt

        foot = ttk.Frame(wrap)
        foot.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(foot, text="🔄  Làm mới", command=self._refresh_copyseo).pack(side="left")
        self._copyseo_status = tk.StringVar(value="")
        ttk.Label(foot, textvariable=self._copyseo_status,
                  style="Sub.TLabel").pack(side="left", padx=(12, 0))

        self._copyseo_episodes = []       # các số tập đang hiển thị (khớp index listbox)
        self._copyseo_blocks = {}         # cache: episode -> {'title','desc','tags'}

    def _copyseo_selected_episode(self):
        lst = getattr(self, "_copyseo_list", None)
        sel = lst.curselection() if lst else ()
        eps = getattr(self, "_copyseo_episodes", [])
        if sel and sel[0] < len(eps):
            return eps[sel[0]]
        return None

    def _refresh_copyseo(self):
        """Quét các thư mục số trong kịch_bản CÓ seoYoutube.docx → đổ vào danh sách."""
        lst = getattr(self, "_copyseo_list", None)
        if lst is None:
            return
        prev = self._copyseo_selected_episode()
        self._copyseo_blocks = {}        # SEO có thể đã đổi → đọc lại khi chọn
        eps = []
        if SCRIPT_DIR.exists():
            for p in sorted(SCRIPT_DIR.iterdir()):
                if p.is_dir() and p.name.isdecimal() and (p / "seoYoutube.docx").exists():
                    eps.append(p.name)
        self._copyseo_episodes = eps
        lst.delete(0, tk.END)
        for ep in eps:
            lst.insert(tk.END, f"  Tập {ep}")
        self._copyseo_status.set(f"{len(eps)} tập có SEO trong kịch_bản")
        if prev in eps:                  # giữ nguyên tập đang chọn nếu còn
            i = eps.index(prev)
            lst.selection_set(i)
            lst.see(i)
            self._copyseo_load_selected()
        else:
            self._set_copyseo_preview("← Chọn một tập ở cột trái để xem và copy.")

    def _set_copyseo_preview(self, text: str):
        txt = getattr(self, "_copyseo_text", None)
        if txt is None:
            return
        txt.configure(state="normal")
        txt.delete("1.0", tk.END)
        txt.insert("1.0", text or "")
        txt.configure(state="disabled")

    def _copyseo_load_selected(self):
        """Đọc SEO của tập đang chọn (có cache) rồi hiện xem trước 3 phần."""
        ep = self._copyseo_selected_episode()
        if not ep:
            return
        blocks = self._copyseo_blocks.get(ep)
        if blocks is None:
            blocks = self._seo_copy_blocks(SCRIPT_DIR / ep / "seoYoutube.docx", ep)
            self._copyseo_blocks[ep] = blocks
        if not blocks:
            self._set_copyseo_preview(f"(Không đọc được SEO của tập {ep}.)")
            self._copyseo_status.set(f"Tập {ep}: lỗi đọc SEO")
            return
        self._set_copyseo_preview(
            "===== TIÊU ĐỀ =====\n" + blocks["title"] + "\n\n"
            "===== MÔ TẢ =====\n" + blocks["desc"] + "\n\n"
            "===== THẺ TAG =====\n" + blocks["tags"])
        self._copyseo_status.set(f"Tập {ep} • thẻ tag {len(blocks['tags'])} ký tự")

    def _copyseo_copy(self, which: str):
        """Copy 1 phần (title/desc/tags) hoặc 'all' của tập đang chọn vào clipboard."""
        ep = self._copyseo_selected_episode()
        if not ep:
            messagebox.showinfo("Chọn tập", "Hãy chọn 1 tập trong danh sách bên trái.")
            return
        blocks = self._copyseo_blocks.get(ep) or \
            self._seo_copy_blocks(SCRIPT_DIR / ep / "seoYoutube.docx", ep)
        if not blocks:
            messagebox.showwarning("Không có SEO", f"Tập {ep} chưa đọc được nội dung SEO.")
            return
        self._copyseo_blocks[ep] = blocks
        label = {"title": "tiêu đề", "desc": "mô tả",
                 "tags": "thẻ tag", "all": "cả 3 phần"}[which]
        if which == "all":
            text = blocks["title"] + "\n\n" + blocks["desc"] + "\n\n" + blocks["tags"]
        else:
            text = blocks[which]
        if not text.strip():
            self._copyseo_status.set(f"Tập {ep}: không có {label} để copy.")
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self._copyseo_status.set(f"✓ Đã copy {label} tập {ep} ({len(text)} ký tự)")

    def _build_thumbnail_panel(self, parent):
        """Nhúng GUI tạo thumbnail (YOUTUBE/thumbnail_gui.py) vào 1 panel.
        Lỗi (thiếu thư viện/ảnh nguồn) chỉ hiện thông báo, không làm hỏng app."""
        try:
            youtube_dir = str(YOUTUBE_DIR)
            if youtube_dir not in sys.path:
                sys.path.insert(0, youtube_dir)
            import thumbnail_gui as tg
            host = tk.Frame(parent, bg="#F4F6FB")
            host.grid(row=0, column=0, sticky="nsew")
            self._thumb_gui = tg.ThumbnailGUI(host, embed=True, on_done=self._on_thumbnail_done)
        except Exception as e:
            logging.error(f"Không tải được tab Thumbnail: {e}")
            ttk.Label(parent, text=f"Không mở được Thumbnail Studio:\n{e}",
                      style="Sub.TLabel").grid(row=0, column=0, padx=24, pady=24)

    @staticmethod
    def _drive_script_name(number: str) -> str:
        number = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", str(number or "").strip())
        return f"{number or 'input'}.txt"

    @staticmethod
    def _drive_log(msg, level="info"):
        if level == "err":
            logging.error(msg)
        elif level == "warn":
            logging.warning(msg)
        else:
            logging.info(msg)

    def _set_thumbnail_upload_status(self, text: str, ok: bool = True):
        def _apply():
            gui = getattr(self, "_thumb_gui", None)
            if not gui:
                return
            try:
                gui.status_var.set(text)
                gui.status_label.configure(fg="#15803D" if ok else "#DC2626")
            except Exception:
                pass
        self.after(0, _apply)

    def _on_thumbnail_done(self, output_path: Path, title: str, number: str):
        """Sau khi tạo thumbnail, upload kịch_bản/input.txt lên Drive theo số tập."""
        episode = str(number or "").strip()
        if not episode:
            logging.warning("Không tải input.txt lên Drive: thiếu số tập thumbnail.")
            return
        threading.Thread(
            target=self._upload_input_script_to_drive,
            args=(SCRIPT_DIR / "input.txt", episode),
            daemon=True,
        ).start()

    def _upload_input_script_to_drive(self, input_path: Path, episode: str):
        drive_name = self._drive_script_name(episode)
        try:
            if not input_path.exists():
                raise FileNotFoundError(f"Không tìm thấy {input_path}")
            if input_path.stat().st_size == 0:
                raise RuntimeError(f"{input_path.name} đang rỗng, chưa tải lên Drive.")

            import taive_drive

            missing = taive_drive._check_deps()
            if missing:
                logging.info(f"Thiếu thư viện Google API ({missing}). Đang cài...")
                taive_drive.install_deps(self._drive_log)
                if taive_drive._check_deps():
                    raise RuntimeError("Không cài được thư viện Google API.")

            self._set_thumbnail_upload_status(f"Đang kiểm tra {drive_name} trên Drive...", ok=True)
            creds = taive_drive.get_credentials(self._drive_log)
            existing = taive_drive.find_drive_file(
                drive_name,
                folder_id=DRIVE_SCRIPT_FOLDER_ID,
                log=self._drive_log,
                creds=creds,
            )
            if existing:
                link = existing.get("webViewLink") or existing.get("id", "")
                logging.info(f"↪ Drive đã có {drive_name}, bỏ qua upload: {link}")
                self._set_thumbnail_upload_status(f"Drive đã có {drive_name}, bỏ qua", ok=True)
                return

            self._set_thumbnail_upload_status(f"Đang tải {drive_name} lên Drive...", ok=True)
            logging.info(f"⬆ Tải {input_path.name} lên Drive/kịch bản với tên {drive_name}...")
            result = taive_drive.upload_to_drive(
                input_path,
                folder_id=DRIVE_SCRIPT_FOLDER_ID,
                log=self._drive_log,
                creds=creds,
                drive_name=drive_name,
                mimetype="text/plain",
            )
            link = result.get("webViewLink") or result.get("id", "")
            logging.info(f"✅ Đã tải kịch bản lên Drive: {drive_name} → {link}")
            self._set_thumbnail_upload_status(f"Đã tải {drive_name} lên Drive", ok=True)
        except Exception as e:
            logging.error(f"Lỗi tải input.txt lên Drive: {e}")
            self._set_thumbnail_upload_status("Lỗi tải input.txt lên Drive", ok=False)

    def _make_log_box(self, parent):
        """Tạo 1 ô nhật ký (ScrolledText) đã set màu/tag và đăng ký vào danh sách
        _log_boxes để _poll_log ghi log đồng thời ra mọi ô (panel video + tab kịch bản)."""
        C = UI
        box = scrolledtext.ScrolledText(
            parent, width=46, height=10, state="disabled",
            font=("Consolas", 9), relief="flat", borderwidth=0,
            background=C["log_bg"], foreground=C["log_info"],
            insertbackground=C["fg"], selectbackground=C["accent_soft"],
            padx=10, pady=8, wrap="word",
        )
        box.grid(row=0, column=0, sticky="nsew")
        box.tag_config("info", foreground=C["log_info"])
        box.tag_config("warn", foreground=C["log_warn"])
        box.tag_config("err", foreground=C["log_err"])
        self._log_boxes.append(box)
        return box

    def _build_log_panel(self, parent, row):
        """Ô nhật ký — đặt DƯỚI dòng trạng thái 'Sẵn sàng' trong panel video."""
        log_frame = ttk.LabelFrame(parent, text="  Nhật ký  ")
        log_frame.grid(row=row, column=0, sticky="nsew", pady=(10, 0))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log_box = self._make_log_box(log_frame)

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
                make_tiktok=self.var_make_tiktok.get(),
                tiktok_speed=self.var_tiktok_speed.get(),
                tiktok_no_effect=self.var_tiktok_no_effect.get(),
                tiktok_caption_pos=int(self.var_tiktok_caption_pos.get()),
                tiktok_music=self.var_tiktok_music.get(),
                tiktok_music_db=int(self.var_tiktok_music_db.get()),
                bring_front=self.var_bring_front.get(),
            ))
        except Exception as e:
            logging.warning(f"Không lưu được cài đặt: {e}")

    def _clear_output(self):
        """Xóa output/, XÓA HẲN các thư mục tập VÀ làm rỗng các file trong kịch_bản/.

        - output/ (kịch_bản/output): xóa hẳn mọi file + thư mục con (wav, video, chunks).
        - Thư mục tập (tên toàn chữ số: 01, 02, 17...): XÓA HẲN cả thư mục — mỗi tập
          gồm audio/video, docx dịch/SEO, input.txt, youtube_seo.txt, thumbnail...
          (KHÔNG đụng tới output/ vì tên không phải số.)
        - kịch_bản/: LÀM RỖNG các file nằm trực tiếp ở đây (input.txt, tiengTrung.docx,
          gemini_result.docx, seoYoutube.docx...) — giữ tên file, xóa sạch nội dung.
          Riêng .docx ghi lại thành docx RỖNG HỢP LỆ để code đọc sau không lỗi.
        """
        import shutil
        out_items = list(OUTPUT_DIR.iterdir()) if OUTPUT_DIR.exists() else []
        kb_files = [p for p in SCRIPT_DIR.iterdir() if p.is_file()] if SCRIPT_DIR.exists() else []
        # Thư mục tập = thư mục con của kịch_bản có tên TOÀN CHỮ SỐ (01, 02, 17...).
        ep_dirs = ([p for p in SCRIPT_DIR.iterdir() if p.is_dir() and p.name.isdecimal()]
                   if SCRIPT_DIR.exists() else [])

        if not out_items and not kb_files and not ep_dirs:
            self.status.set("Không có gì để xóa hay làm rỗng.")
            return

        # Xóa ngay, KHÔNG hỏi xác nhận (theo yêu cầu chạy nhanh).
        self._stop_preview()   # nhả file đang nghe (nếu có) để xóa được

        # 1) Xóa hẳn mọi thứ trong output/
        for p in out_items:
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.unlink(missing_ok=True)

        # 2) Xóa hẳn các thư mục tập (01, 02, 17...) — cả audio/video/docx bên trong
        removed_dirs = 0
        for d in ep_dirs:
            try:
                shutil.rmtree(d, ignore_errors=True)
                removed_dirs += 1
            except Exception as e:
                logging.warning(f"Không xóa được thư mục tập {d.name}: {e}")

        # 3) Làm rỗng các file trong kịch_bản/ (giữ tên, xóa nội dung)
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
        logging.info(f"Đã xóa output trong {OUTPUT_DIR}, xóa {removed_dirs} thư mục tập, "
                     f"và làm rỗng {emptied} file trong {SCRIPT_DIR}")
        self.status.set("Đã xóa output + thư mục tập + làm rỗng kịch_bản.")

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

        # 2c) SỬA chữ "but" tiếng Anh Gemini sót → "nhưng"
        content, n_but = replace_leaked_but(content)
        if n_but:
            logging.info(f'🔁 Đã thay {n_but} chữ "but" (tiếng Anh) → "nhưng".')

        # 2d) XỬ LÝ chữ Hán Gemini bỏ sót: câu dài → dịch NGHĨA (MT offline),
        #     chữ ngắn / tên / thành ngữ → phiên âm Hán-Việt.
        try:
            import dich_hanviet as hv
            content, n_mt, n_am = hv.translate_han(content, on_log=logging.info)
            if n_mt or n_am:
                logging.info(f"🈶 Chữ Hán sót: {n_mt} đoạn dịch nghĩa (MT), "
                             f"{n_am} chữ phiên âm Hán-Việt.")
        except Exception as e:
            logging.warning(f"⚠️ Bỏ qua xử lý chữ Hán: {e}")

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
        self._pipe_wrap = wrap

        hdr = ttk.Frame(wrap)
        hdr.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        self._pipe_hdr = hdr
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
        # Nhiều dòng: mỗi dòng 1 link hoặc 1 file. 1 dòng → xử lý như cũ; ≥2 dòng
        # → mỗi link tạo 1 thư mục kịch bản (01, 02, ...) chạy full pipeline.
        # width nhỏ (mặc định Text là 80 ký tự → phình ngang); sticky="ew" vẫn cho
        # ô giãn vừa theo cột nên không cần để rộng.
        self.pipe_txt_sources = tk.Text(frow, height=2, width=20, wrap="none",
                                        font=("Segoe UI", 10), relief="solid", bd=1)
        self.pipe_txt_sources.grid(row=0, column=0, sticky="ew")
        ttk.Button(frow, text="Chọn…", width=8,
                   command=self._pipe_pick_file).grid(row=0, column=1, padx=(8, 0), sticky="n")
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
        ttk.Label(s1, text="(mỗi dòng 1 link/file)",
                  style="Hint.TLabel").grid(row=3, column=0, sticky="w", pady=(4, 0))
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
        self.var_seo = tk.BooleanVar(value=self._pipe_settings["seo"])
        ttk.Checkbutton(s2, text="🔎  Tạo SEO YouTube (Gemini) sau khi xong",
                        variable=self.var_seo).grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Label(s2, text="(gemini_result.docx → seoYoutube.docx)",
                  style="Hint.TLabel").grid(row=3, column=0, sticky="w", pady=(2, 0))
        self.var_auto3 = tk.BooleanVar(value=self._pipe_settings["auto3"])
        ttk.Checkbutton(s2, text="⛓  Tự động chạy bước ③ sau khi xong",
                        variable=self.var_auto3).grid(row=4, column=0, sticky="w", pady=(6, 0))

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

        self._pipe_steps = (s1, s2, s3)

        # Tiến trình + trạng thái của quy trình
        pf = ttk.Frame(wrap)
        pf.grid(row=4, column=0, sticky="ew", pady=(2, 0))
        pf.columnconfigure(0, weight=1)
        self._pipe_pf = pf
        self.pipe_progress = tk.IntVar(value=0)
        ttk.Progressbar(pf, variable=self.pipe_progress, maximum=100).grid(
            row=0, column=0, sticky="ew")
        # Dòng ĐANG CHẠY LINK MẤY — luôn hiển thị (không bị các thông báo bước con
        # ghi đè) ngay dưới thanh tiến trình.
        self.pipe_link_status = tk.StringVar(value="")
        ttk.Label(pf, textvariable=self.pipe_link_status,
                  font=("Segoe UI", 10, "bold"), foreground=UI["accent"]).grid(
            row=1, column=0, sticky="w", pady=(4, 0))
        self.pipe_status = tk.StringVar(value="Sẵn sàng.")
        ttk.Label(pf, textvariable=self.pipe_status, style="Sub.TLabel").grid(
            row=2, column=0, sticky="w", pady=(2, 0))

        # ── Điều khiển batch NHIỀU LINK: Tạm dừng/Tiếp tục + Xong link này rồi dừng ──
        # CHỈ hiện ở tab "Tạo kịch bản" (view script) — ẩn ở Home cho đỡ chật (do
        # _pipeline_set_layout ẩn/hiện). Chỉ BẬT khi đang chạy batch. Tác dụng ở ĐIỂM
        # AN TOÀN (ranh giới bước/link), KHÔNG cắt ngang thao tác đang chạy (Whisper/
        # Gemini/tạo giọng) — nên có thể trễ tới khi bước hiện tại xong.
        self._batch_pause_evt = threading.Event()   # set = đang TẠM DỪNG
        self._batch_stop_evt = threading.Event()    # set = DỪNG sau khi xong link hiện tại
        self._batch_running = False
        self._batch_ctrl_frame = bctl = ttk.Frame(pf)
        bctl.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        self.btn_batch_pause = ttk.Button(
            bctl, text="⏸  Tạm dừng", width=15, state="disabled",
            command=self._batch_toggle_pause)
        self.btn_batch_pause.pack(side="left")
        self.btn_batch_stop = ttk.Button(
            bctl, text="⏹  Xong link này rồi dừng", width=24, state="disabled",
            command=self._batch_request_stop)
        self.btn_batch_stop.pack(side="left", padx=(8, 0))

        self._pipe_btn_open = ttk.Button(wrap, text="↗  Mở cửa sổ nhận diện đầy đủ",
                                         command=self._open_nhan_dien)
        self._pipe_btn_open.grid(row=5, column=0, sticky="w", pady=(8, 0))
        self._pipe_btn_reset = ttk.Button(wrap, text="↺  Reset cài đặt quy trình về gốc",
                                          command=self._reset_pipe_settings)
        self._pipe_btn_reset.grid(row=6, column=0, sticky="w", pady=(6, 0))

        # Nhật ký riêng của tab "Tạo kịch bản" — chỉ hiện khi xem ngang (dàn 3 bước).
        # Cùng nhận log với ô nhật ký ở panel video (qua _log_boxes).
        self._pipe_log_frame = ttk.LabelFrame(wrap, text="  Nhật ký  ")
        self._pipe_log_frame.columnconfigure(0, weight=1)
        self._pipe_log_frame.rowconfigure(0, weight=1)
        self._make_log_box(self._pipe_log_frame)
        self._pipe_log_frame.grid(row=1, column=3, rowspan=4, sticky="nsew", padx=(12, 0))
        self._pipe_log_frame.grid_remove()   # mặc định ẩn (dọc); _show_view bật khi cần

    def _pipe_pick_file(self):
        # askopenfilenames (số nhiều) → chọn được NHIỀU file 1 lần (Ctrl/Shift để
        # quét khối). Mỗi file thêm thành 1 dòng trong ô nhập.
        paths = filedialog.askopenfilenames(
            title="Chọn file audio/video tiếng Trung (có thể chọn nhiều)",
            filetypes=[("Audio/Video", "*.mp3 *.wav *.m4a *.aac *.flac *.ogg *.opus *.wma "
                                       "*.mp4 *.mkv *.mov *.avi *.webm *.flv"),
                       ("Tất cả", "*.*")])
        if paths:
            cur = self.pipe_txt_sources.get("1.0", "end").strip()
            block = "\n".join(paths)
            self.pipe_txt_sources.insert("end", ("\n" if cur else "") + block)

    def _pipe_set_busy(self, busy: bool):
        self._pipe_busy = busy
        state = "disabled" if busy else "normal"
        for b in (self.btn_recog, self.btn_gemini, self.btn_prep):
            b.config(state=state)

    def _save_pipe_settings(self):
        """Lưu cài đặt quy trình hiện tại (auto + model/tốc độ) cho lần sau."""
        save_pipe_settings(dict(
            auto2=self.var_auto2.get(), auto3=self.var_auto3.get(),
            auto_tts=self.var_auto_tts.get(), seo=self.var_seo.get(),
            model=self.pipe_var_model.get(), speed=self.pipe_var_speed.get(),
        ))

    def _reset_pipe_settings(self):
        """Đưa các tùy chọn quy trình về mặc định gốc và lưu lại."""
        self.var_auto2.set(PIPE_DEFAULTS["auto2"])
        self.var_auto3.set(PIPE_DEFAULTS["auto3"])
        self.var_auto_tts.set(PIPE_DEFAULTS["auto_tts"])
        self.var_seo.set(PIPE_DEFAULTS["seo"])
        self.pipe_var_model.set(PIPE_DEFAULTS["model"])
        self.pipe_var_speed.set(PIPE_DEFAULTS["speed"])
        self.pipe_txt_sources.delete("1.0", "end")
        self._save_pipe_settings()
        self.pipe_status.set("↺ Đã reset cài đặt quy trình về mặc định.")

    def _pipe_sources(self) -> list:
        """Danh sách link/file hợp lệ từ ô nhập ① (mỗi dòng 1 mục), giữ thứ tự."""
        out = []
        for line in self.pipe_txt_sources.get("1.0", "end").splitlines():
            s = line.strip().strip('"').strip("'")
            if s and (os.path.isfile(s) or s.lower().startswith(("http://", "https://"))):
                out.append(s)
        return out

    def _pipe_recognize(self):
        if self._pipe_busy:
            return
        sources = self._pipe_sources()
        if not sources:
            self.pipe_status.set("⚠️ Chưa có link/file — hãy nhập đầu vào (mỗi dòng 1 mục).")
            logging.warning("Chưa có link video / file để nhận diện.")
            return
        self._save_pipe_settings()   # ấn chạy → nhớ cài đặt cho lần sau

        # ≥2 link → chế độ NHIỀU LINK: mỗi link 1 thư mục + full pipeline.
        if len(sources) >= 2:
            self._pipe_start_batch(sources)
            return

        self._pipe_set_busy(True)
        self.pipe_progress.set(0)
        self.pipe_link_status.set("")   # 1 link đơn → không hiển thị "đang chạy link mấy"
        self.pipe_status.set("🎙  Đang chuẩn bị...")
        threading.Thread(
            target=self._pipe_recognize_worker,
            args=(sources[0], self.pipe_var_model.get(), self.pipe_var_speed.get()),
            daemon=True).start()

    def _pipe_recognize_worker(self, media, model, speed):
        ok = False
        try:
            import nhandien_giongnoi as recog
            # Đầu vào là LINK → tải MP3 trước; file có sẵn → dùng trực tiếp.
            if not os.path.isfile(media) and str(media).lower().startswith(("http://", "https://")):
                logging.info(f"🌐 Tải audio từ link: {media}")
                self.pipe_status.set("🌐  Đang tải audio từ link...")
                media = download_audio_mp3(media, DOWNLOAD_DIR)
                if not media:
                    logging.error("❌ Không tải được audio từ link.")
                    self.pipe_status.set("❌ Tải link thất bại.")
                    return
            self.pipe_status.set("🎙  Đang nhận diện...")
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

    def _collect_tts_settings(self):
        """Thu thập cài đặt TTS hiện tại (phải gọi trên MAIN THREAD vì đọc các tk.Var)
        để chế độ NHIỀU LINK tạo giọng cho mỗi tập y như khi chạy 1 link.

        Trả về dict cài đặt, hoặc None nếu cấu hình sai (đã hiện cảnh báo)."""
        mode = self.var_mode.get()
        if mode == "clone":
            voice_name = self._current_voice()
            if not voice_name:
                messagebox.showwarning("Thiếu giọng mẫu",
                                       f"Không tìm thấy file audio trong:\n{VOICE_DIR}")
                return None
            voice_param = str(VOICE_DIR / voice_name)
        elif mode == "design":
            voice_param = self.var_instruct.get().strip()
            if not voice_param:
                messagebox.showwarning("Thiếu mô tả", "Vui lòng nhập mô tả giọng đọc.")
                return None
        else:
            voice_param = None

        cut_half = self.var_cut_half.get()
        cut_audio = self.var_cut_audio.get()
        cut_target = cut_min = cut_max = 0.0
        if cut_audio:
            try:
                cut_target = float(self.var_cut_target.get())
                cut_min = float(self.var_cut_min.get())
                cut_max = float(self.var_cut_max.get())
            except Exception:
                messagebox.showwarning("Cấu hình cắt sai", "Số phút không hợp lệ.")
                return None
            if not (0 < cut_min <= cut_max):
                messagebox.showwarning("Cấu hình cắt sai",
                                       "Cần thỏa: 0 < phút 'Từ' ≤ phút 'Đến'.")
                return None

        try:
            doc_speed = float(str(self.var_doc_speed.get()).replace(",", ".").strip())
        except (TypeError, ValueError):
            doc_speed = 1.0
        doc_speed = max(0.5, min(doc_speed, 2.0))
        try:
            ngang_speed = float(str(self.var_ngang_speed.get()).replace(",", ".").strip())
        except (TypeError, ValueError):
            ngang_speed = 1.0
        ngang_speed = max(0.5, min(ngang_speed, 2.0))
        try:
            tiktok_speed = float(str(self.var_tiktok_speed.get()).replace(",", ".").strip())
        except (TypeError, ValueError):
            tiktok_speed = 1.0
        tiktok_speed = max(0.5, min(tiktok_speed, 2.0))
        try:
            tiktok_caption_pos = int(self.var_tiktok_caption_pos.get())
        except Exception:
            tiktok_caption_pos = 40
        tiktok_caption_pos = max(0, min(tiktok_caption_pos, 100))
        try:
            tiktok_music_db = int(self.var_tiktok_music_db.get())
        except Exception:
            tiktok_music_db = -12
        tiktok_music_db = max(-40, min(tiktok_music_db, 0))

        effect_name = self._current_effect()
        effect_path = None
        if effect_name and effect_name != EFFECT_NONE:
            p = EFFECTS_DIR / effect_name
            effect_path = str(p) if p.exists() else None

        return dict(
            mode=mode, voice_param=voice_param, chunk=self.var_chunk.get(),
            make_video=self.var_make_video.get(), effect=effect_path,
            cut_audio=cut_audio, cut_target=cut_target, cut_min=cut_min, cut_max=cut_max,
            make_video_doc=self.var_make_video_doc.get(),
            doc_full_audio=self.var_doc_full_audio.get(), doc_speed=doc_speed,
            ngang_speed=ngang_speed, cut_half=cut_half,
            doc_from_ngang=self.var_doc_from_ngang.get(),
            doc_no_effect=self.var_doc_no_effect.get(),
            make_tiktok=self.var_make_tiktok.get(), tiktok_speed=tiktok_speed,
            tiktok_no_effect=self.var_tiktok_no_effect.get(),
            tiktok_caption_pos=tiktok_caption_pos,
            tiktok_music=self.var_tiktok_music.get(), tiktok_music_db=tiktok_music_db,
            bring_front=self.var_bring_front.get(),
        )

    # ── CHẾ ĐỘ NHIỀU LINK: mỗi link 1 thư mục kịch_bản/NN, full pipeline ───────
    def _pipe_start_batch(self, sources):
        """Xử lý nhiều link lần lượt: mỗi link 1 thư mục (01, 02, ...) trong
        kịch_bản, chạy full pipeline (nhận diện → Gemini → input.txt → SEO → giọng)."""
        # Nếu bật "⛓ Chạy tiếp tạo giọng" thì thu thập cài đặt TTS NGAY BÂY GIỜ trên
        # main thread (worker chạy thread khác, không nên đọc tk.Var). Cấu hình sai
        # (vd clone mà chưa chọn giọng) → dừng trước khi bắt đầu cả batch.
        tts_settings = None
        if self.var_auto_tts.get():
            tts_settings = self._collect_tts_settings()
            if tts_settings is None:
                return
        # Chạy ngay, KHÔNG hỏi xác nhận. Lưu ý: bước dịch & SEO dùng Firefox — hãy
        # ĐÓNG Firefox đang mở (profile bị khoá khi đang chạy) và đảm bảo đã đăng nhập.
        logging.info(f"⛓ Xử lý {len(sources)} link theo thứ tự (mỗi link 1 tập)"
                     + (" + tạo giọng." if tts_settings else "."))
        self._pipe_set_busy(True)
        # Bật điều khiển batch: xoá cờ cũ + cho phép 2 nút Tạm dừng / Dừng-sau-link.
        self._batch_pause_evt.clear()
        self._batch_stop_evt.clear()
        self._batch_running = True
        self.btn_batch_pause.config(state="normal", text="⏸  Tạm dừng")
        self.btn_batch_stop.config(state="normal")
        self.pipe_progress.set(0)
        self.pipe_link_status.set(f"⏳ Chuẩn bị xử lý {len(sources)} link...")
        self.pipe_status.set(f"⏳ Bắt đầu xử lý {len(sources)} link...")
        threading.Thread(
            target=self._pipe_batch_worker,
            args=(sources, self.pipe_var_model.get(), self.pipe_var_speed.get(),
                  tts_settings),
            daemon=True).start()

    # ── Điều khiển batch nhiều link: tạm dừng / dừng-sau-link ──────────────────
    def _batch_toggle_pause(self):
        """Tạm dừng ↔ cho chạy tiếp batch. Áp dụng ở điểm an toàn kế tiếp (giữa bước/link),
        không cắt ngang thao tác đang chạy."""
        if not self._batch_running:
            return
        if self._batch_pause_evt.is_set():
            self._batch_pause_evt.clear()
            self.btn_batch_pause.config(text="⏸  Tạm dừng")
            self.pipe_link_status.set("▶  Cho chạy tiếp...")
            logging.info("▶ Người dùng cho CHẠY TIẾP batch.")
        else:
            self._batch_pause_evt.set()
            self.btn_batch_pause.config(text="▶  Tiếp tục")
            self.pipe_link_status.set("⏸  Sẽ tạm dừng ở điểm an toàn kế tiếp (giữa bước/link)...")
            logging.info("⏸ Người dùng yêu cầu TẠM DỪNG batch.")

    def _batch_request_stop(self):
        """Đánh dấu DỪNG: link đang chạy sẽ hoàn tất RỒI batch dừng (không bắt đầu link kế)."""
        if not self._batch_running:
            return
        self._batch_stop_evt.set()
        # Nếu đang tạm dừng thì bỏ cờ tạm dừng để link hiện tại chạy nốt rồi mới dừng.
        self._batch_pause_evt.clear()
        self.btn_batch_pause.config(state="disabled", text="⏸  Tạm dừng")
        self.btn_batch_stop.config(state="disabled")
        self.pipe_link_status.set("⏹  Sẽ dừng sau khi xong link đang chạy...")
        logging.info("⏹ Người dùng yêu cầu DỪNG sau khi xong link hiện tại.")

    def _batch_pause_wait(self):
        """Chặn (chờ) tại điểm an toàn khi đang TẠM DỪNG; nhả khi bấm Tiếp tục HOẶC khi
        đã bấm Dừng (để link hiện tại chạy nốt rồi dừng ở đầu vòng kế)."""
        if not self._batch_pause_evt.is_set():
            return
        import time
        self.pipe_status.set("⏸ Đã tạm dừng — bấm Tiếp tục để chạy tiếp.")
        while self._batch_pause_evt.is_set() and not self._batch_stop_evt.is_set():
            time.sleep(0.3)

    def _batch_controls_reset(self):
        """Về trạng thái KHÔNG chạy: xoá cờ + tắt 2 nút điều khiển batch."""
        self._batch_running = False
        self._batch_pause_evt.clear()
        self._batch_stop_evt.clear()
        try:
            self.btn_batch_pause.config(state="disabled", text="⏸  Tạm dừng")
            self.btn_batch_stop.config(state="disabled")
        except Exception:
            pass

    def _batch_prepare_input(self, gemini_docx, out_txt) -> bool:
        """Tạo input.txt cho 1 link: bỏ cấu trúc + thay câu quảng bá kênh + bỏ chú
        thích () []. (Bản batch không hỏi/không dừng như bước ③ thủ công.)"""
        try:
            import dich_kiemtra as cg
            findings = cg.check_docx(gemini_docx, on_log=logging.info)
            if findings:
                logging.warning(f"⚠️ {gemini_docx.parent.name}: gemini_result.docx còn "
                                f"{len(findings)} đoạn có câu dẫn nhập/thừa — vẫn ghi input.txt.")
            chunks = cg.read_docx_chunks(gemini_docx)
            content = "\n".join(t for _, t in chunks).strip()
            if not content:
                return False
            content, n_promo = replace_channel_promo(content)
            if n_promo:
                logging.info(f"🔁 Đã thay {n_promo} câu quảng bá kênh.")
            content, n_but = replace_leaked_but(content)
            if n_but:
                logging.info(f'🔁 Đã thay {n_but} chữ "but" → "nhưng".')
            try:
                import dich_hanviet as hv
                content, n_mt, n_am = hv.translate_han(content, on_log=logging.info)
                if n_mt or n_am:
                    logging.info(f"🈶 Chữ Hán sót: {n_mt} đoạn MT, {n_am} chữ phiên âm.")
            except Exception as e:
                logging.warning(f"⚠️ Bỏ qua xử lý chữ Hán: {e}")
            try:
                import dich_chuanbi_input as prep
                content = prep.remove_annotations(content)   # bỏ chú thích () []
            except Exception:
                pass
            Path(out_txt).write_text(content, encoding="utf-8")
            return True
        except Exception as e:
            logging.error(f"⚠️ Lỗi tạo input.txt: {e}")
            return False

    def _batch_run_tts(self, folder, ts, episode=None) -> bool:
        """Tạo giọng OmniVoice cho 1 tập: đọc folder/input.txt → folder/output.wav
        (kèm cắt/dựng video theo cài đặt ts). Chạy ĐỒNG BỘ trong thread batch.

        episode: số tập (để ghi chữ 'Mimi audio Số <episode>' lên video TikTok, khớp
                 số trên thumbnail). None → không ghi chữ."""
        input_txt = folder / "input.txt"
        if not input_txt.exists():
            logging.warning(f"⚠️ {folder.name}: chưa có input.txt → bỏ qua tạo giọng.")
            return False
        try:
            full_text = clean_text(input_txt.read_text(encoding="utf-8"))
        except Exception as e:
            logging.error(f"⚠️ {folder.name}: không đọc được input.txt: {e}")
            return False
        chunks = split_chunks(full_text.lower(), ts["chunk"])
        if not chunks:
            logging.warning(f"⚠️ {folder.name}: input.txt trống → bỏ qua tạo giọng.")
            return False

        # Whisper đã được giải phóng ở lượt gọi (sau khi đóng Firefox) nên ở đây
        # chỉ cần nạp OmniVoice để tạo giọng.
        output = folder / "output.wav"
        stub = _NullWidget()
        pause_event = threading.Event()
        pause_event.set()
        # Tới bước clone giọng cho link này → (tùy chọn) bật cửa sổ GUI lên trên cùng.
        if ts.get("bring_front"):
            self._bring_to_front()
        logging.info(f"🎧 Tạo giọng OmniVoice cho tập {folder.name} ({len(chunks)} đoạn)...")
        # Tiến trình chi tiết (tạo giọng + dựng video) hiện ở THANH TTS (self.progress/
        # self.status); thanh "Tạo kịch bản" để hiển thị tiến độ tổng theo số tập.
        run_tts(
            ts["mode"], ts["voice_param"], chunks, str(output),
            self.progress, self.status,
            stub, stub, stub, pause_event,
            ts["make_video"], ts["effect"],
            ts["cut_audio"], ts["cut_target"], ts["cut_min"], ts["cut_max"],
            ts["make_video_doc"], ts["doc_full_audio"], ts["doc_speed"],
            ts["ngang_speed"], ts["cut_half"], True,   # reuse=True → TIẾP TỤC: dùng
            ts["doc_from_ngang"], ts["doc_no_effect"],  # lại audio/video đã có, chỉ
            # Bản tự động: đặt tên riêng cho các video kết quả trong thư mục tập.
            ngang_out=folder / "YOUTUBE.mp4",      # video NGANG (đăng YouTube)
            doc_out=folder / "facebook.mp4",       # video DỌC  (đăng Facebook)
            make_tiktok=ts.get("make_tiktok", False),
            tiktok_out=folder / "tiktok.mp4",      # video TIKTOK (10 phút đầu)
            tiktok_speed=ts.get("tiktok_speed", 1.0),
            tiktok_no_effect=ts.get("tiktok_no_effect", False),
            # Chữ trên TikTok = 'Mimi audio Số <số ở thumbnail>' (khớp số tập).
            tiktok_caption=(f"Mimi audio Số {episode}" if episode else None),
            tiktok_caption_pos=ts.get("tiktok_caption_pos", 40),
            tiktok_music=ts.get("tiktok_music", False),
            tiktok_music_db=ts.get("tiktok_music_db", -12),
        )                                          # render phần còn thiếu (vd video dọc).
        logging.info(f"🎧 Xong tạo giọng tập {folder.name} → {output.name}")
        return True

    def _make_thumbnail_for_folder(self, folder, episode: str) -> bool:
        """Render thumbnail cho 1 tập — CẢ 2 bản, dùng CHUNG ảnh mèo + tiêu đề + số tập:
          • NGANG (1920×1080): thumbnail<episode>.png
          • DỌC  (1080×1920): thumbnail<episode>_dọc.png  (chuẩn YouTube Shorts)
        Bản nào đã có thì bỏ qua (tạo tiếp phần còn thiếu). Lỗi bản DỌC KHÔNG chặn
        bản NGANG. Tiêu đề lấy từ folder/seoYoutube.docx."""
        try:
            import random
            youtube_dir = str(YOUTUBE_DIR)
            if youtube_dir not in sys.path:
                sys.path.insert(0, youtube_dir)
            import dien_tieu_de_thumbnail as renderer
            from seo_docx_parser import parse_seo_docx

            out_png = folder / f"thumbnail{episode}.png"        # bản NGANG
            out_doc = folder / f"thumbnail{episode}_dọc.png"    # bản DỌC
            need_ngang = not out_png.exists()
            need_doc = not out_doc.exists()
            if not need_ngang and not need_doc:
                return True   # cả 2 bản đã có → khỏi làm lại

            seo_docx = folder / "seoYoutube.docx"
            title = ""
            if seo_docx.exists():
                try:
                    title = (parse_seo_docx(seo_docx).get("title") or "").strip()
                except Exception as e:
                    logging.warning(f"Không đọc được tiêu đề SEO: {e}")
            if not title:
                logging.warning(f"⚠️ {folder.name}: không có tiêu đề SEO — bỏ qua thumbnail.")
                return False
            # Tiêu đề hợp lệ luôn NGẮN (1 câu đã chọn). Nếu parse SEO lấy nhầm cả đoạn
            # (vd câu mở đầu Gemini "Dưới đây là 5 tiêu đề...") thì title rất dài → BỎ QUA
            # thumbnail thay vì nhồi vào renderer (tránh treo CPU + thumbnail xấu).
            if len(title) > 120 or len(title.split()) > 18:
                logging.warning(
                    f"⚠️ {folder.name}: tiêu đề SEO BẤT THƯỜNG ({len(title.split())} từ, "
                    f"{len(title)} ký tự) — có thể parse nhầm câu mở đầu. BỎ QUA thumbnail. "
                    f"Tiêu đề: {title[:80]}…")
                return False

            photos = renderer.list_photo_files(renderer.CAT_IMAGE_DIR)
            if not photos:
                logging.warning(f"⚠️ Không có ảnh mèo trong {renderer.CAT_IMAGE_DIR} — bỏ qua thumbnail.")
                return False

            photo = random.choice(photos)   # dùng CHUNG cho cả bản ngang & dọc
            made = False
            if need_ngang:
                renderer.add_title(
                    renderer.SOURCE_IMAGE, out_png, title, photo,
                    renderer.FRAME_IMAGE, episode, renderer.NUMBER_FRAME_IMAGE)
                logging.info(f"🖼  Đã tạo thumbnail ngang: {out_png.name}")
                made = True
            # Bản DỌC 1080×1920 — bọc riêng để lỗi bản dọc KHÔNG làm hỏng bản ngang.
            if need_doc:
                try:
                    renderer.add_title_vertical(out_doc, title, photo, episode)
                    logging.info(f"🖼  Đã tạo thumbnail dọc: {out_doc.name}")
                    made = True
                except Exception as e:
                    logging.warning(f"⚠️ {folder.name}: lỗi tạo thumbnail dọc (giữ bản ngang): {e}")
            return made
        except Exception as e:
            logging.error(f"Lỗi tạo thumbnail {folder.name}: {e}")
            return False

    def _seo_copy_blocks(self, seo_docx, episode: str):
        """Đọc seoYoutube.docx → {'title','desc','tags'} đã chuẩn hóa cho 1 tập
        (None nếu lỗi). Khớp tuyệt đối với 3 nút Copy của tab Thumbnail:
        tiêu đề mở đầu [FULL] + 'Số <tập>' + '| Mimi audio'; mô tả thêm hashtag
        #truyenfull #full; thẻ tag gắn tag tập rồi cắt cho tổng < 499 ký tự."""
        try:
            youtube_dir = str(YOUTUBE_DIR)
            if youtube_dir not in sys.path:
                sys.path.insert(0, youtube_dir)
            from seo_docx_parser import parse_seo_docx
            import thumbnail_gui as tg   # dùng đúng hàm của 3 nút để khớp tuyệt đối

            seo = parse_seo_docx(str(seo_docx))
            ep = episode if str(episode).strip().isdecimal() else ""
            # Tiêu đề mở đầu [FULL]; mô tả thêm hashtag #truyenfull #full.
            title = tg.add_full_prefix(
                tg.add_episode_to_title(tg.ensure_brand_suffix(seo.get("title", "")), ep))
            desc = tg.add_full_hashtags(
                tg.add_episode_to_description(seo.get("description", ""), ep))

            # Thẻ tag: gắn tag tập rồi cắt bớt cho tổng (nối bằng ', ') < 499 ký tự
            # (giới hạn YouTube) — nhưng LUÔN GIỮ tag tập 'mimi audio số <ep>'.
            tag_list = tg.add_episode_tag(seo.get("tags", []), ep)
            tags = tg.cap_tags(seo.get("tags", []), ep)
            dropped = len(tag_list) - len([t for t in tags.split(", ") if t])
            if dropped:
                ep_tag = f"mimi audio số {ep}" if ep else None
                logging.info(f"✂ Thẻ tag ≥{tg.MAX_TAGS_LEN} ký tự → bỏ {dropped} tag cuối "
                             + (f"(giữ '{ep_tag}')." if ep_tag else "."))
            return {"title": title or "", "desc": desc or "", "tags": tags or ""}
        except Exception as e:
            logging.warning(f"Không đọc được nội dung SEO copy: {e}")
            return None

    def _save_youtube_seo_copy(self, seo_docx, out_path, episode: str) -> bool:
        """Lưu sẵn nội dung 3 nút Copy của tab Thumbnail (tiêu đề · mô tả · thẻ tag)
        ra 1 file .txt để dán nhanh khi đăng YouTube.

        Tab Thumbnail chỉ đọc seoYoutube.docx CHUNG (kịch_bản/) nên khi chạy NHIỀU
        LINK không copy được nội dung từng tập. File này ghi đúng nội dung 3 nút đó
        (đã gắn 'Số <tập>' + hậu tố '| Mimi audio') cho file SEO của riêng tập.
        """
        blocks = self._seo_copy_blocks(seo_docx, episode)
        if not blocks:
            return False
        try:
            content = (
                "===== TIÊU ĐỀ =====\n" + blocks["title"] + "\n\n"
                "===== MÔ TẢ =====\n" + blocks["desc"] + "\n\n"
                "===== THẺ TAG =====\n" + blocks["tags"] + "\n"
            )
            Path(out_path).write_text(content, encoding="utf-8")
            logging.info(f"💾 Đã lưu nội dung copy YouTube (tiêu đề/mô tả/thẻ tag) "
                         f"→ {Path(out_path).name}")
            return True
        except Exception as e:
            logging.warning(f"Không lưu được file copy YouTube SEO: {e}")
            return False

    def _seo_docx_valid(self, seo_docx) -> bool:
        """True nếu seoYoutube.docx đã có nội dung SEO thật (tiêu đề khác rỗng).

        Dùng để TIẾP TỤC: file rỗng/chỉ có tiêu đề (do reset) → coi như chưa làm SEO.
        """
        try:
            if not Path(seo_docx).exists():
                return False
            youtube_dir = str(YOUTUBE_DIR)
            if youtube_dir not in sys.path:
                sys.path.insert(0, youtube_dir)
            from seo_docx_parser import parse_seo_docx
            return bool((parse_seo_docx(str(seo_docx)).get("title") or "").strip())
        except Exception:
            return False

    def _translation_complete(self, gemini_docx, chunks, episode) -> bool:
        """True nếu MỌI đoạn trong gemini_result.docx đã dịch xong (không rỗng, không
        '(chưa dịch)', hết chữ Hán). Thiếu đoạn nào thì ghi log rõ để biết mà sửa."""
        import dich_gemini as g
        n = len(chunks)
        check = g.read_results_docx(gemini_docx, n) if Path(gemini_docx).exists() else [None] * n
        missing = [j + 1 for j, r in enumerate(check) if not g.is_translation_done(r)]
        if not missing:
            return True
        head = ", ".join(map(str, missing[:10])) + ("..." if len(missing) > 10 else "")
        logging.error(
            f"⛔ Tập {episode}: CHƯA dịch xong {len(missing)}/{n} đoạn (đoạn {head}) → "
            "DỪNG, KHÔNG tạo audio/video. Chạy lại để dịch tiếp; nếu Gemini cứ lỗi 1 "
            "đoạn, sửa tay đoạn đó trong gemini_result.docx rồi chạy lại.")
        return False

    # ── MANIFEST: tiến độ + map nguồn↔tập (để chạy tiếp & báo cáo) ──────────────
    def _folder_steps(self, folder, episode: str) -> dict:
        """Bước ĐÃ XONG của 1 tập, suy từ file thực tế trong thư mục."""
        folder = Path(folder)
        zh = next(iter(folder.glob("*_zh.docx")), None)
        gem = folder / "gemini_result.docx"
        inp = folder / "input.txt"
        translate_done = False
        if gem.exists():
            try:
                import dich_gemini as g
                chunks = read_zh_docx_chunks(zh) if zh else []
                if chunks:
                    prior = g.read_results_docx(gem, len(chunks))
                    translate_done = all(g.is_translation_done(r) for r in prior)
                else:
                    translate_done = True   # không rõ số đoạn → coi gem tồn tại là xong
            except Exception:
                translate_done = True
        return {
            "recognize": bool(zh),
            "translate": translate_done,
            "input": inp.exists() and inp.stat().st_size > 0,
            "seo": self._seo_docx_valid(folder / "seoYoutube.docx"),
            "thumbnail": (folder / f"thumbnail{episode}.png").exists(),
            "audio": (folder / "output.wav").exists(),
            # Bản tự động đặt tên YOUTUBE.mp4 / facebook.mp4; vẫn nhận tên cũ
            # (*_videodone.mp4 / *_doc.mp4) cho các tập tạo trước đây.
            "video_ngang": (folder / "YOUTUBE.mp4").exists()
                            or bool(list(folder.glob("*_videodone.mp4"))),
            "video_doc": (folder / "facebook.mp4").exists()
                          or bool(list(folder.glob("*_doc.mp4"))),
        }

    def _manifest_update(self, source, episode, folder, done=None) -> None:
        """Ghi/cập nhật 1 mục manifest (nguồn→tập + tiến độ) rồi lưu ngay."""
        import datetime as _dt
        m = load_manifest()
        key = norm_source(source)
        entry = m.get(key, {})
        entry["source"] = key
        entry["episode"] = str(episode)
        entry["folder"] = str(folder)
        entry["steps"] = self._folder_steps(folder, episode)
        if done is not None:
            entry["done"] = bool(done)
        entry["updated"] = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        m[key] = entry
        save_manifest(m)

    def _allocate_episode(self, source):
        """(episode, is_new). Nguồn đã có trong manifest → ĐÚNG tập cũ; nguồn mới →
        số tập kế tiếp (không trùng manifest / thư mục đã có / số đã lưu)."""
        m = load_manifest()
        key = norm_source(source)
        entry = m.get(key)
        if entry is None:
            # Manifest CŨ khoá theo chuỗi THÔ (trước khi norm_source chuẩn hoá path).
            # Dò mục nào re-chuẩn-hoá ra CÙNG khoá → coi là cùng nguồn; dời sang khoá
            # mới cho gọn (tự vá dần). Nhờ vậy file local đã làm trước đây, dù gõ khác
            # kiểu, vẫn map về ĐÚNG tập cũ thay vì bị cấp tập mới + làm lại.
            for old_key in list(m):
                if old_key != key and norm_source(old_key) == key:
                    entry = m.pop(old_key)
                    m[key] = entry
                    save_manifest(m)
                    break
        if entry is not None and str(entry.get("episode", "")).isdecimal():
            return str(entry["episode"]).zfill(2), False
        used = {int(v["episode"]) for v in m.values()
                if str(v.get("episode", "")).isdecimal()}
        if SCRIPT_DIR.exists():
            for p in SCRIPT_DIR.iterdir():
                if p.is_dir() and p.name.isdecimal():
                    used.add(int(p.name))
        used.add(load_episode_number())
        nxt = (max(used) + 1) if used else 1
        return str(nxt).zfill(2), True

    def _pipe_batch_worker(self, sources, model, speed, tts_settings=None):
        import time
        driver = None
        total = len(sources)
        ok_count = 0

        # Gemini treo → dịch_gemini đóng & mở lại Firefox; cập nhật tham chiếu để
        # SEO và link kế (driver.get / driver.quit) dùng đúng trình duyệt đang mở.
        def _on_driver(d):
            nonlocal driver
            driver = d

        # ④ Ghi nhật ký batch ra kịch_bản/batch_log.txt (append, giữ lịch sử) để sau
        # sự cố mở file là biết dừng ở link/bước nào.
        file_handler = None
        try:
            import datetime as _dt
            file_handler = logging.FileHandler(SCRIPT_DIR / "batch_log.txt", encoding="utf-8")
            file_handler.setFormatter(
                logging.Formatter("%(asctime)s  %(message)s", "%Y-%m-%d %H:%M:%S"))
            logging.getLogger().addHandler(file_handler)
            logging.info("\n" + "═" * 12 + f" BẮT ĐẦU BATCH {total} link "
                         f"({_dt.datetime.now():%Y-%m-%d %H:%M:%S}) " + "═" * 12)
        except Exception as e:
            logging.warning(f"Không mở được batch_log.txt: {e}")

        try:
            import nhandien_giongnoi as recog
            import dich_gemini as g
            youtube_dir = str(YOUTUBE_DIR)
            if youtube_dir not in sys.path:
                sys.path.insert(0, youtube_dir)
            import seo_youtube_gemini as seo
            prefix = load_prefix()
            logging.info(f"📚 NHIỀU LINK: {total} link — mỗi link 1 tập (theo manifest).")
            logging.info(f"📦 Model: {model}  •  Tốc độ: {speed}x")

            for i, src in enumerate(sources, 1):
                # ⏸/⏹ ĐIỂM AN TOÀN GIỮA CÁC LINK: đang tạm dừng thì CHỜ tại đây; đã bấm
                # dừng thì THOÁT vòng (link trước đã hoàn tất, không bắt đầu link mới).
                self._batch_pause_wait()
                if self._batch_stop_evt.is_set():
                    logging.info(f"⏹ ĐÃ DỪNG theo yêu cầu — xong {ok_count}/{total} link, "
                                 f"còn {total - i + 1} link chưa chạy.")
                    self.pipe_link_status.set(
                        f"⏹ Đã dừng — xong {ok_count}/{total} link (còn {total - i + 1}).")
                    break
                # Số tập theo MANIFEST: nguồn cũ → đúng tập cũ (chạy tiếp); nguồn mới
                # → cấp số kế tiếp. Nhờ vậy nhập khác thứ tự / thiếu link vẫn đúng tập.
                episode, is_new = self._allocate_episode(src)
                episode_num = int(episode)
                folder = SCRIPT_DIR / episode            # tên thư mục = số tập
                folder.mkdir(parents=True, exist_ok=True)
                # Ghi nguồn↔tập vào manifest NGAY (kể cả lỗi sau đó vẫn biết link→tập).
                self._manifest_update(src, episode, folder, done=False)
                logging.info(f"🔖 {'Tập MỚI' if is_new else 'Tiếp tục tập'} {episode} "
                             f"← {norm_source(src)[:70]}")
                # Dòng ĐANG CHẠY (luôn hiển thị dưới thanh tiến trình) — giữ nguyên
                # suốt link, không bị thông báo bước con (Gemini/giọng/video) ghi đè.
                self.pipe_link_status.set(f"🔗 Đang chạy: Link {i}/{total} — tập {episode}")
                self.pipe_status.set(f"🔗 Link {i}/{total} → tập {episode}/")
                logging.info(f"════════ 🔗 LINK {i}/{total} → TẬP {episode}/ ════════")
                try:
                    s = src.strip().strip('"').strip("'")
                    gemini_docx = folder / "gemini_result.docx"
                    input_txt = folder / "input.txt"
                    seo_docx = folder / "seoYoutube.docx"

                    # ── 1+2) NHẬN DIỆN — bỏ qua nếu đã có *_zh.docx hợp lệ ──────
                    # (chỉ tải MP3 + chạy Whisper khi THỰC SỰ cần nhận diện lại).
                    existing_zh = next(iter(sorted(folder.glob("*_zh.docx"))), None)
                    chunks = read_zh_docx_chunks(existing_zh) if existing_zh else []
                    if chunks:
                        logging.info(f"♻ Bỏ qua tải + nhận diện (đã có {existing_zh.name}, "
                                     f"{len(chunks)} đoạn).")
                    else:
                        if os.path.isfile(s):
                            media = s
                            logging.info(f"📁 File local: {media}")
                        elif s.lower().startswith(("http://", "https://")):
                            logging.info(f"🌐 Tải từ link: {s}")
                            media = download_audio_mp3(s, DOWNLOAD_DIR)
                            if not media:
                                logging.error(f"❌ Link {i}: không tải được audio — bỏ qua.")
                                continue
                        else:
                            logging.error(f"❌ Link {i}: không hợp lệ — bỏ qua.")
                            continue
                        self.pipe_progress.set(0)
                        transcript = recog.transcribe_chinese(
                            media, model_name=model, speed=float(speed),
                            on_progress=lambda f: self.pipe_progress.set(int(f * 100)))
                        if not transcript:
                            logging.error(f"❌ Link {i}: không nhận diện được — bỏ qua.")
                            continue
                        zh_docx = folder / f"{Path(media).stem}_zh.docx"
                        recog.save_docx(transcript, str(zh_docx), title=Path(media).name)
                        logging.info(f"💾 Đã lưu bản nhận diện: {zh_docx}")
                        chunks = recog.split_into_chunks(transcript)
                    if not chunks:
                        logging.warning(f"⚠️ Link {i}: không có đoạn nào — bỏ qua dịch/SEO.")
                        continue

                    self._batch_pause_wait()          # ⏸ điểm tạm dừng trước khi dịch
                    # ── 3) DỊCH GEMINI — đủ thì bỏ qua; thiếu thì TIẾP TỤC dịch ──
                    if SKIP_TRANSLATE_DETAIL_CHECK and gemini_docx.exists():
                        # [TẠM] Đã có gemini_result.docx → coi như DỊCH XONG, KHÔNG dò
                        # từng đoạn (tránh gửi lại đoạn đã dịch). Xem cờ ở đầu file.
                        translated_now = False
                        translation_ok = True
                        logging.info(f"♻ Bỏ qua dịch Gemini — đã có {gemini_docx.name} "
                                     f"(TẠM tắt kiểm từng đoạn).")
                    else:
                        prior = (g.read_results_docx(gemini_docx, len(chunks))
                                 if gemini_docx.exists() else [None] * len(chunks))
                        n_todo = sum(1 for r in prior if not g.is_translation_done(r))
                        translated_now = n_todo > 0   # có gửi dịch trong lượt này không
                        if n_todo == 0:
                            logging.info(f"♻ Bỏ qua dịch Gemini (đã đủ {len(chunks)} đoạn).")
                        else:
                            if driver is None:
                                logging.info("🌐 Mở Firefox + Gemini (dùng chung dịch + SEO)...")
                                driver = g.init_firefox()
                            else:
                                driver.get(g.GEMINI_URL)   # chat mới cho link này
                                time.sleep(8)
                            logging.info(f"🌐 Dịch {n_todo}/{len(chunks)} đoạn còn thiếu sang Gemini...")
                            results = g.send_chunks_to_gemini(
                                chunks, prefix=prefix, on_log=logging.info, out_path=gemini_docx,
                                driver=driver, keep_open=True, on_driver=_on_driver, resume=True,
                                on_result=lambda i2, t2, _a: self.pipe_status.set(
                                    f"🌐 Link {i}/{total} • Gemini {i2 + 1}/{t2}"))
                            g.save_results_docx(chunks, results, gemini_docx)
                            logging.info(f"💾 Đã lưu bản dịch: {gemini_docx}")
                        # ⛔ CHẶN: DỊCH CHƯA XONG thì KHÔNG tạo input/audio/video (tránh
                        # tình trạng như tập 29: dịch dở vẫn ra audio/video). Lần sau chạy
                        # lại sẽ dịch tiếp các đoạn còn thiếu.
                        translation_ok = self._translation_complete(gemini_docx, chunks, episode)
                    self._manifest_update(src, episode, folder)   # ghi tiến độ sau dịch

                    if not translation_ok:
                        self.pipe_status.set(f"⛔ Tập {episode}: dịch chưa xong — bỏ qua.")
                        continue

                    # ── 4) input.txt — TẠO LẠI nếu vừa dịch (bản cũ có thể dở), hoặc
                    # chưa có. Tạo lại → chữ ký đổi → audio/video tự render lại đúng.
                    if not translated_now and input_txt.exists() and input_txt.stat().st_size > 0:
                        logging.info("♻ Bỏ qua tạo input.txt (đã có).")
                    elif self._batch_prepare_input(gemini_docx, input_txt):
                        logging.info(f"💾 Đã tạo: {input_txt}")

                    self._batch_pause_wait()          # ⏸ điểm tạm dừng trước khi SEO
                    # ── 5) SEO YouTube — bỏ qua nếu seoYoutube.docx đã có tiêu đề ─
                    if self._seo_docx_valid(seo_docx):
                        logging.info("♻ Bỏ qua SEO (đã có seoYoutube.docx hợp lệ).")
                    else:
                        if driver is None:        # dịch đã bỏ qua → mở Firefox cho SEO
                            logging.info("🌐 Mở Firefox cho SEO...")
                            driver = g.init_firefox()
                        logging.info("🔎 Tạo SEO YouTube...")
                        seo.run(str(gemini_docx), str(seo_docx),
                                keep_open=True, log=logging.info, driver=driver)
                        logging.info(f"💾 Đã tạo: {seo_docx}")

                    # 5b) Nội dung 3 nút Copy (tiêu đề/mô tả/thẻ tag) ra .txt — LUÔN
                    # tạo lại (nhẹ, suy ra từ seoYoutube.docx) để áp dụng logic mới nhất
                    # (vd cắt thẻ tag ≤500 ký tự) kể cả khi các bước khác đã bỏ qua.
                    self._save_youtube_seo_copy(
                        seo_docx, folder / "youtube_seo.txt", episode)

                    # ── 6) Thumbnail (ngang + dọc) — bỏ qua nếu đã có CẢ 2 bản ──
                    if (folder / f"thumbnail{episode}.png").exists() \
                            and (folder / f"thumbnail{episode}_dọc.png").exists():
                        logging.info("♻ Bỏ qua thumbnail (đã có cả ngang & dọc).")
                    else:
                        self._make_thumbnail_for_folder(folder, episode)
                    # Xong thumbnail → cập nhật SỐ TẬP (không lùi) + ghi tiến độ manifest.
                    save_episode_number(max(load_episode_number(), episode_num))
                    self._manifest_update(src, episode, folder)

                    # 7) Tải input.txt lên Drive (tự bỏ qua nếu Drive đã có cùng tên).
                    self._upload_input_script_to_drive(input_txt, episode)

                    # ── 8) TẠO GIỌNG + VIDEO NGAY cho link này (tuần tự từng link) ──
                    # Mỗi link chạy ĐẦY ĐỦ: dịch → SEO → video xong mới sang link kế.
                    # Đóng Firefox trước khi render để nhả RAM (video chỉ dùng GPU);
                    # link sau tự mở lại Firefox cho bước dịch.
                    self._batch_pause_wait()          # ⏸ điểm tạm dừng trước khi tạo giọng/video
                    if tts_settings:
                        if driver is not None:
                            try:
                                driver.quit()
                                logging.info("🦊 Đã đóng Firefox trước khi tạo video.")
                            except Exception:
                                pass
                            driver = None
                        # Nhả Whisper trước khi nạp OmniVoice (GPU 8GB không chứa cả 2).
                        try:
                            recog.free_model()
                            logging.info("🧹 Giải phóng Whisper trước khi tạo giọng.")
                        except Exception:
                            pass
                        self.pipe_status.set(f"🎧 Tập {episode}: đang tạo giọng + video...")
                        self._batch_run_tts(folder, tts_settings, episode)

                    self._manifest_update(src, episode, folder, done=True)  # link XONG
                    ok_count += 1
                    done_what = "dịch + SEO + video" if tts_settings else "dịch + SEO"
                    logging.info(f"✅ Link {i}/{total} (tập {episode}) HOÀN TẤT ({done_what}).")
                except Exception as e:
                    # Một link lỗi không làm hỏng cả batch — ghi log (kèm traceback để
                    # dễ tìm nguyên nhân) rồi sang link kế.
                    import traceback
                    logging.error(f"❌ Lỗi ở link {i}/{total}: {e}")
                    logging.error(traceback.format_exc())
                    continue

            # Số tập đã cập nhật theo TỪNG link (sau thumbnail). Manifest giữ map
            # nguồn↔tập + tiến độ → chạy lại (chưa xóa output) sẽ TIẾP TỤC đúng tập,
            # kể cả khi nhập khác thứ tự / thiếu link.
            logging.info(f"🔢 Xong vòng batch: {ok_count}/{total} link hoàn tất.")

            # Mọi link đã chạy ĐẦY ĐỦ TUẦN TỰ (dịch → SEO → video) ngay trong vòng lặp.
            self.pipe_progress.set(100)
            self.pipe_link_status.set(f"✅ Hoàn tất {ok_count}/{total} link.")
            self.pipe_status.set(f"✅ Xong {ok_count}/{total} link → thư mục trong kịch_bản.")
            logging.info(f"🎉 XONG: {ok_count}/{total} link hoàn tất.")
        except Exception as e:
            logging.error(f"Lỗi batch nhiều link: {e}")
            self.pipe_link_status.set(f"❌ Lỗi batch (đã xong {ok_count}/{total} link).")
            self.pipe_status.set(f"Lỗi batch: {e}")
        finally:
            if driver is not None:          # đóng Firefox dùng chung sau khi xong/lỗi
                try:
                    driver.quit()
                except Exception:
                    pass
            try:
                import nhandien_giongnoi as recog
                recog.free_model()
                logging.info("🧹 Đã giải phóng model nhận diện khỏi VRAM.")
            except Exception:
                pass
            if file_handler is not None:        # ngừng ghi nhật ký batch ra file
                try:
                    logging.info("──────── KẾT THÚC BATCH ────────")
                    logging.getLogger().removeHandler(file_handler)
                    file_handler.close()
                except Exception:
                    pass
            self._pipe_set_busy(False)
            self._batch_controls_reset()   # tắt nút Tạm dừng/Dừng khi batch kết thúc

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
        seo_on = self.var_seo.get()
        driver = None

        # Khi dịch_gemini phải đóng & mở lại Firefox (Gemini treo) thì cập nhật lại
        # tham chiếu driver ở đây để bước SEO dùng đúng Firefox đang mở.
        def _on_driver(d):
            nonlocal driver
            driver = d

        try:
            chunks = read_chinese_docx_chunks(CHINESE_DOCX)
            if not chunks:
                logging.error("❌ Không đọc được nội dung tiếng Trung để gửi.")
                self.pipe_status.set("❌ Nội dung trống.")
                return
            import dich_gemini as g
            prefix = load_prefix()
            # Nếu bật SEO: tự mở MỘT Firefox và DÙNG CHUNG cho cả dịch lẫn SEO. Tránh
            # đóng Firefox sau khi dịch rồi mở lại cho SEO — lần mở thứ hai hay kẹt
            # khóa profile khiến SEO không chạy được.
            if seo_on:
                logging.info("🌐 Mở Firefox (dùng chung cho dịch + SEO)...")
                driver = g.init_firefox()
            logging.info(f"🌐 Gửi {len(chunks)} đoạn sang Gemini...")
            results = g.send_chunks_to_gemini(
                chunks, prefix=prefix, on_log=logging.info, out_path=GEMINI_DOCX,
                driver=driver,                 # None → tự mở; có driver → tái dùng
                keep_open=(driver is not None),  # còn SEO ở sau thì giữ Firefox mở
                on_driver=_on_driver,          # đóng/mở lại Firefox → cập nhật driver
                on_result=lambda i, total, ans: self.pipe_status.set(
                    f"🌐 Gemini: đoạn {i + 1}/{total}"))
            g.save_results_docx(chunks, results, GEMINI_DOCX)
            n_ok = sum(1 for r in results if r and r.strip())
            logging.info(f"✅ Gemini xong: {n_ok}/{len(results)} đoạn → {GEMINI_DOCX.name}")
            self.pipe_status.set(f"✅ Gemini xong → {GEMINI_DOCX.name}")
            ok = True
            # Ngay sau khi có nội dung Gemini → tạo SEO YouTube (tiêu đề/mô tả/hashtag)
            # nếu người dùng bật. SEO lỗi KHÔNG làm hỏng quy trình (ok đã True nên
            # vẫn chạy tiếp bước ③).
            if seo_on:
                self._run_seo_youtube(driver=driver)
        except Exception as e:
            logging.error(f"Lỗi gửi Gemini: {e}")
            self.pipe_status.set(f"Lỗi: {e}")
        finally:
            if driver is not None:          # đóng Firefox dùng chung sau khi xong/ lỗi
                try:
                    driver.quit()
                except Exception:
                    pass
            self._pipe_set_busy(False)
            if ok and self.var_auto3.get():   # ⛓ tự động sang bước ③
                self.after(600, lambda: self._pipe_prepare_input(auto=True))

    def _run_seo_youtube(self, driver=None):
        """Chạy SEO YouTube (Gemini) ngay sau bước lấy nội dung Gemini.

        Lấy ĐOẠN ĐẦU của gemini_result.docx, gửi lên cuộc trò chuyện Gemini chuyên
        SEO YouTube (đã có sẵn chỉ dẫn) rồi lưu seoYoutube.docx. driver: tái dùng
        Firefox đang mở (do bước dịch mở) để khỏi mở lại. Mọi lỗi đều được nuốt để
        không chặn các bước tiếp theo của quy trình."""
        try:
            youtube_dir = str(YOUTUBE_DIR)
            if youtube_dir not in sys.path:
                sys.path.insert(0, youtube_dir)
            import seo_youtube_gemini as seo
            self.pipe_status.set("🔎  Đang tạo SEO YouTube (Gemini)...")
            logging.info("🔎 Tạo SEO YouTube từ gemini_result.docx...")
            # Có driver → keep_open=True để seo KHÔNG tự đóng (worker đóng sau cùng).
            seo.run(str(GEMINI_DOCX), str(SEO_DOCX),
                    keep_open=(driver is not None), log=logging.info, driver=driver)
            self.pipe_status.set(f"✅ SEO YouTube xong → {SEO_DOCX.name}")
        except Exception as e:
            logging.error(f"Lỗi tạo SEO YouTube (bỏ qua, tiếp tục quy trình): {e}")
            self.pipe_status.set(f"⚠️ SEO YouTube lỗi: {e}")

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

        # Tốc độ audio cho VIDEO TIKTOK (10 phút đầu) — atempo, giữ cao độ
        make_tiktok = self.var_make_tiktok.get()
        try:
            tiktok_speed = float(str(self.var_tiktok_speed.get()).replace(",", ".").strip())
        except (TypeError, ValueError):
            tiktok_speed = 1.0
        tiktok_speed = max(0.5, min(tiktok_speed, 2.0))
        tiktok_no_effect = self.var_tiktok_no_effect.get()   # không phủ hiệu ứng lên TikTok
        # Chữ TikTok = 'Mimi audio Số <số tập gần nhất>' (khớp thumbnail); 0 → không ghi.
        _ep = load_episode_number()
        tiktok_caption = f"Mimi audio Số {_ep:02d}" if _ep > 0 else None
        try:
            tiktok_caption_pos = int(self.var_tiktok_caption_pos.get())
        except Exception:
            tiktok_caption_pos = 40
        tiktok_caption_pos = max(0, min(tiktok_caption_pos, 100))
        tiktok_music = self.var_tiktok_music.get()
        try:
            tiktok_music_db = int(self.var_tiktok_music_db.get())
        except Exception:
            tiktok_music_db = -12
        tiktok_music_db = max(-40, min(tiktok_music_db, 0))
        if make_tiktok and tiktok_speed > 1.001:
            logging.info(f"Video TikTok sẽ tăng tốc audio x{tiktok_speed:.2f} (giữ cao độ).")

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

        # Áp QUY TẮC ĐẶT TÊN như bản tự động: 3 video theo nền tảng (cùng thư mục output).
        _out_dir = out_path.parent
        ngang_out = _out_dir / "YOUTUBE.mp4"     # video ngang → YouTube
        doc_out = _out_dir / "facebook.mp4"      # video dọc  → Facebook
        tiktok_out = _out_dir / "tiktok.mp4"     # video TikTok

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
            kwargs={"make_tiktok": make_tiktok,   # video TikTok (10 phút đầu)
                    "tiktok_speed": tiktok_speed,
                    "tiktok_no_effect": tiktok_no_effect,
                    "tiktok_caption": tiktok_caption,
                    "tiktok_caption_pos": tiktok_caption_pos,
                    "tiktok_music": tiktok_music,
                    "tiktok_music_db": tiktok_music_db,
                    # Quy tắc đặt tên 3 video (giống bản tự động).
                    "ngang_out": ngang_out,
                    "doc_out": doc_out,
                    "tiktok_out": tiktok_out},
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
            for box in self._log_boxes:   # ghi ra mọi ô nhật ký (video + tab kịch bản)
                box.config(state="normal")
                box.insert("end", msg + "\n", tag)
                box.see("end")
                box.config(state="disabled")
        self.after(200, self._poll_log)


if __name__ == "__main__":
    App().mainloop()
