"""
Dựng video NGANG 1920×1080 theo độ dài audio: ghép clip kho (hoặc video nguồn) phủ KÍN
màn hình, chỉ dán thêm logo Mimi audio nhỏ ở góc trên phải.

Quy trình:
  - Lấy thời lượng từ file audio (kịch_bản/*.wav) làm thời lượng đích.
  - Ghép RANDOM các video trong videongang/ (lặp lại tới khi đủ thời lượng audio).
  - Phóng to ZOOM rồi cắt về 1920×1080 (phần dư cắt ở mép trên/dưới theo CAT_TREN để bỏ
    phụ đề + watermark cháy sẵn trong clip kho), dán logo, mux audio (-t = độ dài audio).

Bố cục "Ngang A" (08/11/2026, user chọn sau khi xem mockup): bỏ hẳn bộ khung cũ (nền
Khung0 + viền khung1 + lớp trang trí khung2 che mất ~52 % màn hình, video chỉ còn 48 %).
Các PNG trong Backbround/ vẫn để nguyên nhưng không dùng khi dựng nữa.

MODE:
  - "fill" : phóng to + cắt cho video phủ kín màn hình (mặc định).
  - "fit"  : hiện trọn video, dải đen trên/dưới nếu khác tỉ lệ.

Đầu ra:  kịch_bản/<tên_audio>_videodone.mp4 (+ YOUTUBE_goc.mp4 nếu goc_out: cùng hình,
         CHƯA dán logo — bản dọc dùng lại, xem video_doc_khung.py)

Cách dùng:
    python video_khung.py
"""

import json
import random
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps
from scipy import ndimage

# Ép UTF-8 cho stdout/stderr (tránh lỗi gõ tiếng Việt). Dùng reconfigure() để đổi
# encoding TẠI CHỖ — KHÔNG bọc TextIOWrapper mới. Nếu bọc wrapper mới, khi module
# khác (video_doc) cũng bọc lần nữa thì wrapper trung gian mất tham chiếu, bị GC và
# ĐÓNG luôn buffer dùng chung → "I/O operation on closed file" ở lần ghi sau.
for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream is not None:
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

BASE_DIR   = Path(__file__).resolve().parent.parent   # myvoice/
BG_DIR     = BASE_DIR / "Backbround"   # bộ khung CŨ (Khung0/khung1/khung2) — không dùng khi dựng nữa
# Logo Mimi audio: dùng chung kho logo của thumbnail (logo.png hồng, logo xanh.png, logo
# tím.png, logo đỏ.png). Mỗi lần dựng chọn NGẪU NHIÊN một màu (random_logo); tên logo ghi
# vào YOUTUBE_goc.json để bản dọc dán logo cùng màu.
LOGO_DIR   = BASE_DIR / "YOUTUBE" / "thumbnail"
LOGO_PATTERN = "logo*.png"
VIDEO_DIR  = BASE_DIR / "videongang"   # kho video ngang để ghép random
SCRIPT_DIR = BASE_DIR / "kịch_bản"     # nơi chứa audio + xuất video

# Khung hình xuất cố định 1920×1080 (trước lấy theo kích thước PNG khung).
CANVAS_W, CANVAS_H = 1920, 1080
# Logo góc trên phải: cao LOGO_CAO px, cách mép trên/phải LOGO_LE px (tính theo 1080p).
LOGO_CAO = 150
LOGO_LE  = 36

# Bộ khung cũ — chỉ còn video_khung0_tao.py (vẽ nền Khung0) tham chiếu để ghép ảnh thử.
KHUNG1 = BG_DIR / "khung1.png"
KHUNG2 = BG_DIR / "khung2.png"
K2_LOGO_BOX = (0, 346, 348, 690)

# Ưu tiên GPU (NVIDIA NVENC) để dựng video; tự fallback về CPU (libx264) nếu GPU lỗi.
USE_GPU = True

# Hạ CQ/CRF để ưu tiên chi tiết. File xuất sẽ lớn hơn và dựng chậm hơn một chút so với
# cấu hình mặc định trước đây (CQ 19 / CRF 18).
NVENC_CQ = 16
X264_CRF = 16

MODE  = "fill"      # "fit" hoặc "fill"
# Clip kho videongang/ (và video tải xuống của tập) là video Trung Quốc: PHỤ ĐỀ cháy sẵn ở
# mép dưới (≈ 89–97 % chiều cao) và watermark bilibili góc trên (≈ 1–7 %, trái hoặc phải vì có
# clip lật gương). Ô ✂ "Che chữ Trung" (che_chu, mặc định TẮT — user chốt 08/11/2026 "không
# cần che… mặc định không check"): BẬT → CẮT BỎ mép trên CAT_TREN_MIN + mép dưới CAT_DUOI_MIN
# (tỉ lệ chiều cao clip), phần thiếu lót DẢI ĐEN trên/dưới (letterbox); TẮT → giữ nguyên khung
# hình gốc. Không phóng to ở cả hai: clip kho vốn là video điện thoại đã nén lại, phóng 1,27–1,3×
# để phủ kín màn hình là thấy mờ (user chê). Zoom chỉ còn ở ô 🎞 video nguồn (người dùng tự
# chọn; phóng bằng lanczos + làm nét nhẹ LAM_NET); zoom ≥ ZOOM_MIN ≈ 1,27 thì hết dải đen.
# Đo 08/11/2026 trên 16 clip mẫu của 3 kho (nauan / vlog / thiennhien); bản khung cũ dùng
# ZOOM 1.25 cắt giữa, viền chấm khung1 che nốt vệt chữ.
CAT_TREN_MIN = 0.08
CAT_DUOI_MIN = 0.13
ZOOM_MIN = 1.0 / (1.0 - CAT_TREN_MIN - CAT_DUOI_MIN)       # mức phóng đủ che không cần dải đen
CAT_TREN = CAT_TREN_MIN / (CAT_TREN_MIN + CAT_DUOI_MIN)   # phần dư cắt ở mép trên (≈ 38 %)
ZOOM  = 1.0            # kho clip: KHÔNG phóng (1:1) → dải đen ≈ 113 px mỗi đầu ở 1080p
LAM_NET = 0.7          # unsharp luma amount khi có phóng (0 = tắt); 1:1 không làm nét
# Logo: nằm gọn TRONG dải đen dưới (bên phải) khi dải đủ cao (≥ LOGO_THANH_MIN px) để không
# che hình; dải thấp hơn (có phóng) thì về góc trên phải như bố cục không dải.
LOGO_THANH_MIN = 90
LOGO_THANH_LE = 8      # lề trên/dưới của logo trong dải đen
# 🎞 Video nguồn (24/10/2026, build_video(source_video=…)): MỘT video — video tải
# xuống của tập — thay kho clip. Thời lượng được kéo/nén (setpts) cho khớp audio vì
# lời đọc là bản dịch của chính video đó; kẹp trong [KEO_MIN, KEO_MAX] để hình không
# giật (quá chậm) hay lướt (quá nhanh) — lệch hơn thì -stream_loop/-t lặp hoặc cắt.
NGUON_FPS = 30              # ép fps sau khi kéo thời lượng (chậm → lặp khung, nhanh → bỏ bớt)
KEO_MIN, KEO_MAX = 0.5, 2.0

# GUI chạy bằng pythonw.exe (không có console), nên MỖI lần gọi ffmpeg/ffprobe
# Windows phải cấp một cửa sổ console mới → màn hình NHẤP NHÁY liên tục khi quét
# hàng trăm clip, và thỉnh thoảng ffprobe trả stdout RỖNG/CỤT do console + pipe
# bị dựng/huỷ dồn dập → json.loads() nổ ("Expecting value: line 1 column 1").
# CREATE_NO_WINDOW: chạy hẳn không console → hết nhấp nháy, hết cả lỗi kèm theo.
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# Cache thời lượng clip: kho videodoc/ có vài trăm file, dựng video nào cũng ffprobe
# lại từ đầu (mỗi file 1 tiến trình). Nhớ theo (kích thước, mtime) nên file sửa/đổi
# là tự probe lại; lần dựng sau gần như không phải gọi ffprobe nữa.
PROBE_CACHE_FILE = Path(__file__).resolve().parent / "probe_cache.json"
_probe_cache: dict | None = None


def _run(cmd, **kw):
    """subprocess.run cho ffmpeg/ffprobe — luôn KHÔNG bật cửa sổ console."""
    kw.setdefault("capture_output", True)
    kw.setdefault("text", True)
    kw.setdefault("encoding", "utf-8")
    kw.setdefault("errors", "replace")
    return subprocess.run(cmd, creationflags=CREATE_NO_WINDOW, **kw)


_nvenc_cached: bool | None = None


def has_nvenc() -> bool:
    """Kiểm tra ffmpeg có encoder h264_nvenc hay không (hỏi 1 lần rồi nhớ)."""
    global _nvenc_cached
    if _nvenc_cached is None:
        r = _run(["ffmpeg", "-hide_banner", "-encoders"])
        _nvenc_cached = r.returncode == 0 and "h264_nvenc" in (r.stdout or "")
    return _nvenc_cached


def run_ffmpeg_progress(cmd, total_dur: float, log=print, label: str = "Dựng video",
                        progress=None):
    """Chạy ffmpeg và báo % theo thời lượng đích nhờ -progress.

    KHÔNG làm chậm render: ffmpeg vẫn mã hóa như cũ, ta chỉ đọc dòng tiến trình
    nó in ra (out_time_us, speed) rồi cập nhật mỗi ~2s. stderr ghi ra file tạm để
    vừa tránh nghẽn pipe (deadlock), vừa lấy được thông báo lỗi khi ffmpeg thất bại.

    progress: hàm tùy chọn nhận (pct, cur, total, speed) để cập nhật THANH tiến
              trình trên GUI. Khi được truyền, KHÔNG ghi dòng % ra log nữa (tiến
              trình hiện bằng thanh chứ không spam nhật ký), và cập nhật dày hơn
              (~0.5s) cho thanh chạy mượt.

    Trả về (returncode, stderr_tail).
    """
    # Chèn -progress pipe:1 -nostats ngay sau 'ffmpeg' để nhận tiến trình qua stdout.
    cmd = [cmd[0], "-progress", "pipe:1", "-nostats", *cmd[1:]]
    err_path = Path(tempfile.gettempdir()) / "ffmpeg_progress_err.log"
    cur, speed, last = 0.0, "?", 0.0
    interval = 0.5 if progress is not None else 2.0   # thanh GUI cập nhật mượt hơn log
    with open(err_path, "w", encoding="utf-8", errors="replace") as ef:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=ef,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            creationflags=CREATE_NO_WINDOW,
        )
        for line in proc.stdout:
            line = line.strip()
            if line.startswith("out_time_us="):
                try:
                    cur = max(0, int(line.split("=", 1)[1])) / 1_000_000
                except ValueError:
                    pass
            elif line.startswith("speed="):
                speed = line.split("=", 1)[1]
            elif line.startswith("progress="):
                now = time.monotonic()
                done = line.endswith("end")
                if done or now - last >= interval:
                    last = now
                    pct = min(100.0, cur / total_dur * 100) if total_dur > 0 else 0.0
                    if progress is not None:
                        progress(pct, cur, total_dur, speed)   # → thanh tiến trình GUI
                    else:
                        log(f"  {label}: {pct:5.1f}%  ({cur:.0f}/{total_dur:.0f}s, tốc độ {speed})")
        proc.wait()
    try:
        tail = err_path.read_text(encoding="utf-8", errors="replace")[-1000:]
    except OSError:
        tail = ""
    try:
        err_path.unlink(missing_ok=True)
    except OSError:
        pass
    return proc.returncode, tail


def _ffprobe_json(args, path: Path, tries: int = 3):
    """Chạy ffprobe -of json và trả về dict — thử lại nếu đầu ra hỏng.

    ffprobe thỉnh thoảng trả stdout RỖNG hoặc CỤT (vd chỉ '{\\n') khi bị gọi dồn
    dập hàng trăm lần từ GUI, hoặc khi file đang bị chương trình khác giữ. Trước
    đây json.loads() nổ thẳng ra ngoài với thông báo khó hiểu ("Expecting value:
    line 1 column 1") và giết cả lượt dựng. Nay: thử lại vài lần rồi mới báo lỗi
    NÊU RÕ TÊN FILE.
    """
    def _why(stderr: str, fallback: str) -> str:
        """Gọn stderr nhiều dòng của ffprobe thành 1 dòng ngắn để ghi log."""
        lines = [ln.strip() for ln in (stderr or "").splitlines() if ln.strip()]
        # Dòng cuối là thông báo dễ hiểu nhất ("Invalid data found...", "No such file...");
        # bỏ tiền tố đường dẫn dài cho gọn.
        msg = lines[-1].split(": ", 1)[-1] if lines else fallback
        return msg[:120]

    last = ""
    for attempt in range(tries):
        r = _run(["ffprobe", "-v", "error", *args, "-of", "json", str(path)])
        out = (r.stdout or "").strip()
        try:
            data = json.loads(out)
        except json.JSONDecodeError:
            # Đầu ra rỗng/cụt → gần như chắc chắn là lỗi tạm thời, thử lại.
            last = _why(r.stderr, f"ffprobe trả về dữ liệu hỏng ({out[:40]!r})")
        else:
            if data:
                return data
            # {} = ffprobe không đọc được file (hỏng / đang bị khoá / thiếu quyền).
            last = _why(r.stderr, "ffprobe không đọc được file")
        if attempt < tries - 1:
            time.sleep(0.2 * (attempt + 1))
    raise RuntimeError(f"Không đọc được {path.name}: {last}")


def get_duration(path: Path, tries: int = 3) -> float:
    path = Path(path)
    data = _ffprobe_json(["-show_entries", "format=duration"], path, tries=tries)
    try:
        return float(data["format"]["duration"])
    except (KeyError, TypeError, ValueError):
        raise RuntimeError(f"File không có thời lượng hợp lệ: {path.name}") from None


def get_resolution(path: Path) -> tuple[int, int]:
    """Lấy (width, height) của luồng video đầu tiên bằng ffprobe."""
    path = Path(path)
    data = _ffprobe_json(
        ["-select_streams", "v:0", "-show_entries", "stream=width,height"], path)
    try:
        s = data["streams"][0]
        return int(s["width"]), int(s["height"])
    except (KeyError, IndexError, TypeError, ValueError):
        raise RuntimeError(f"File không có luồng video hợp lệ: {path.name}") from None


# Dưới cỡ này thì chắc chắn không phải video đầy đủ (vài giây 1080p đã hơn 1 MB).
VIDEO_MIN_BYTES = 200_000


def video_hop_le(path) -> bool:
    """File video DÙNG ĐƯỢC: tồn tại, không quá nhỏ và ffprobe đọc ra thời lượng > 1 s.

    ffmpeg bị ngắt giữa chừng (máy sập, card TDR, NVENC chết, Dừng hàng đợi) để lại file mp4
    CỤT không có moov → ffprobe đọc không ra. Trước 09/11/2026 mọi chỗ chỉ hỏi `exists()` nên
    file cụt được coi là "đã có": ⏩ không dựng lại mà đem đăng YouTube/Facebook luôn. Nay
    folder_steps (web), skip_existing (các bộ dựng) đều hỏi hàm này. Thời lượng lấy qua
    probe_durations (cache theo size + mtime) nên file tốt chỉ probe một lần."""
    try:
        p = Path(path)
        if not p.is_file() or p.stat().st_size < VIDEO_MIN_BYTES:
            return False
        # tries=1: file hỏng thì khỏi thử lại 3 lần (bảng tập hỏi hàm này mỗi lần vẽ).
        dur = probe_durations([p], log=lambda *_: None, tries=1).get(p)
        return dur is not None and dur > 1.0
    except Exception:
        return False


def xoa_video_cut(*paths, log=print) -> None:
    """Xoá file video ffmpeg vừa dựng DỞ (mã lỗi ≠ 0) để lượt sau dựng lại từ đầu thay vì
    thấy file "đã có". Chỉ xoá file nhỏ/không đọc được (video_hop_le False) — file lành lặn
    (vd lỗi ở bước mux cuối mà ffmpeg vẫn ghi xong) thì để nguyên."""
    for p in paths:
        if p is None:
            continue
        try:
            p = Path(p)
            if p.exists() and not video_hop_le(p):
                p.unlink()
                log(f"🧹 Xoá file video dựng dở: {p.name}")
        except OSError as e:
            log(f"[Cảnh báo] Không xoá được file dựng dở {p}: {e}")


def probe_durations(videos, log=print, tries: int = 3) -> dict:
    """Thời lượng của cả kho clip — có cache, và BỎ QUA clip lỗi thay vì chết cả lượt.

    Trước đây đây là chỗ hay hỏng nhất: mỗi clip một tiến trình ffprobe (kho
    videodoc/ có hơn 200 clip → hơn 200 cửa sổ console nhấp nháy), và chỉ cần MỘT
    lần ffprobe trả đầu ra hỏng là cả video rớt. Nay chỉ probe clip nào chưa có
    trong cache (hoặc đã đổi kích thước/ngày sửa), và clip nào đọc không được thì
    ghi cảnh báo rồi bỏ qua — miễn còn clip dùng được là vẫn dựng.
    """
    global _probe_cache
    if _probe_cache is None:
        try:
            _probe_cache = json.loads(PROBE_CACHE_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            _probe_cache = {}     # cache hỏng/chưa có → dựng lại từ đầu, không sao

    durations, bad, added = {}, [], 0
    for v in videos:
        try:
            st = v.stat()
            key = str(v.resolve())
            sig = [st.st_size, st.st_mtime_ns]
            hit = _probe_cache.get(key)
            if isinstance(hit, list) and len(hit) == 3 and hit[:2] == sig:
                durations[v] = float(hit[2])
                continue
            dur = get_duration(v, tries=tries)
            _probe_cache[key] = [*sig, dur]
            durations[v] = dur
            added += 1
        except (OSError, RuntimeError) as e:
            bad.append(f"{v.name} ({e})")

    if bad:
        log(f"[Cảnh báo] Bỏ qua {len(bad)} clip không đọc được: {', '.join(bad[:5])}"
            + (" ..." if len(bad) > 5 else ""))
    if added:
        try:
            PROBE_CACHE_FILE.write_text(
                json.dumps(_probe_cache, ensure_ascii=False), encoding="utf-8")
        except OSError as e:
            # Không ghi được cache thì thôi, lần sau probe lại — nhưng vẫn báo một
            # dòng, kẻo mỗi lần chạy đều probe lại từ đầu mà không hiểu vì sao chậm.
            log(f"[Cảnh báo] Không lưu được cache thời lượng clip: {e}")
    return durations


def find_audio() -> Path:
    """Tìm file wav (ưu tiên output.wav) trong kịch_bản/output/ rồi tới kịch_bản/."""
    search_dirs = [SCRIPT_DIR / "output", SCRIPT_DIR]
    for d in search_dirs:
        if (d / "output.wav").exists():
            return d / "output.wav"
    for d in search_dirs:
        wavs = sorted(d.glob("*.wav"))
        if wavs:
            return wavs[0]
    print(f"[LỖI] Không tìm thấy file .wav nào trong: {SCRIPT_DIR/'output'} hoặc {SCRIPT_DIR}")
    sys.exit(1)


def ti_le_keo(video_dur: float, audio_dur: float) -> float:
    """Hệ số setpts để video nguồn dài bằng audio (= audio/video), kẹp [KEO_MIN,
    KEO_MAX]. Thiếu/0 số đo → 1.0 (giữ nguyên tốc độ)."""
    try:
        video_dur, audio_dur = float(video_dur), float(audio_dur)
    except (TypeError, ValueError):
        return 1.0
    if video_dur <= 0 or audio_dur <= 0:
        return 1.0
    return max(KEO_MIN, min(audio_dur / video_dur, KEO_MAX))


def build_playlist(videos, durations, target):
    """
    Trả về (danh sách video theo thứ tự ngẫu nhiên có lặp, tổng thời lượng).
    Xáo trộn rồi lấy lần lượt; hết thì xáo lại — đảm bảo tổng >= target.
    """
    seq, total, pool = [], 0.0, []
    while total < target:
        if not pool:
            pool = videos[:]
            random.shuffle(pool)
        v = pool.pop()
        seq.append(v)
        total += durations[v]
    return seq, total


def loc_phu_kin(cw: int, ch: int, zoom: float, che: bool = False) -> tuple[str, float, int]:
    """Chuỗi filter ffmpeg đặt video vào khung cw×ch KHÔNG phóng quá `zoom` (1.0 = giữ 1:1):
    phóng `zoom` lần (lanczos + làm nét nhẹ nếu > 1) → che=True thì bỏ mép trên CAT_TREN_MIN,
    mép dưới CAT_DUOI_MIN (watermark + phụ đề cháy sẵn; phần dư khi phóng chia CAT_TREN ở
    trên), che=False thì không cắt mép (phần dư khi phóng cắt giữa) → ngang cắt giữa cho vừa
    cw → phần thiếu lót dải đen trên/dưới (pad). Phóng ≥ ZOOM_MIN (che) hay ≥ 1 (không che)
    thì vừa khít, hết dải đen. Trả về (filter, zoom thực, chiều cao dải đen mỗi đầu ≈ px, 16:9)."""
    z = max(1.0, float(zoom))
    zw, zh = round(cw * z), round(ch * z)
    tren = CAT_TREN_MIN if che else 0.0
    con = (1.0 - CAT_TREN_MIN - CAT_DUOI_MIN) if che else 1.0
    chia = CAT_TREN if che else 0.5
    net = f",unsharp=5:5:{LAM_NET:g}:5:5:0" if (LAM_NET > 0 and z > 1.0) else ""
    f = (f"scale={zw}:{zh}:force_original_aspect_ratio=increase:flags=lanczos,"
         f"crop=min(iw\\,{cw}):min(ih*{con:.4f}\\,{ch}):(iw-ow)/2:"
         f"ih*{tren:g}+(ih*{con:.4f}-oh)*{chia:.4f}{net},"
         f"pad={cw}:{ch}:(ow-iw)/2:(oh-ih)/2:black")
    thanh = int(max(0.0, (ch - min(ch, zh * con)) / 2))
    return f, z, thanh


def list_logos() -> list[Path]:
    """Các logo Mimi audio trong kho thumbnail (logo.png, logo xanh.png, logo tím.png, ...)."""
    return sorted(LOGO_DIR.glob(LOGO_PATTERN), key=lambda p: p.name.casefold())


def random_logo() -> Path:
    """Chọn ngẫu nhiên một màu logo cho tập; kho trống → logo.png."""
    logos = list_logos()
    return random.choice(logos) if logos else LOGO_DIR / "logo.png"


def lop_logo(size: tuple[int, int], logo_path: Path | None, out_path: Path,
             thanh_duoi: int = 0) -> tuple[Path, bool, str]:
    """Vẽ lớp phủ trong suốt cw×ch chỉ có logo nhỏ → PNG tạm.

    thanh_duoi = chiều cao dải đen dưới (px). Đủ cao (≥ LOGO_THANH_MIN) → logo nằm gọn trong
    dải, bên phải, cao thanh − 2·LOGO_THANH_LE (không che hình). Không thì logo góc trên phải,
    cao LOGO_CAO px (theo 1080p), cách mép LOGO_LE px. Logo cắt sát phần có hình. Không có
    file logo → lớp trong suốt rỗng (dựng không logo) để filter graph của ffmpeg giữ nguyên số
    input. Trả về (đường dẫn PNG, có_logo, vị trí "dải dưới" | "góc trên phải").
    """
    cw, ch = size
    layer = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    co_logo = bool(logo_path and Path(logo_path).exists())
    k = ch / 1080
    trong_thanh = thanh_duoi >= round(LOGO_THANH_MIN * k)
    vi_tri = "dải dưới" if trong_thanh else "góc trên phải"
    if co_logo:
        logo = Image.open(logo_path).convert("RGBA")
        bbox = logo.getchannel("A").point(lambda a: 255 if a > 32 else 0).getbbox()
        if bbox:
            logo = logo.crop(bbox)
        le = round(LOGO_LE * k)
        if trong_thanh:
            cao = max(2, thanh_duoi - 2 * round(LOGO_THANH_LE * k))
            logo = ImageOps.contain(logo, (cao * 3, cao), method=Image.Resampling.LANCZOS)
            y = ch - thanh_duoi + (thanh_duoi - logo.height) // 2
        else:
            cao = max(2, round(LOGO_CAO * k))
            logo = ImageOps.contain(logo, (cao * 3, cao), method=Image.Resampling.LANCZOS)
            y = le
        layer.alpha_composite(logo, (cw - le - logo.width, y))
    out_path = Path(out_path)
    layer.save(out_path)
    return out_path, co_logo, vi_tri


# ── Bộ khung CŨ (trước 08/11/2026) ─────────────────────────────────────────────
# Chỉ còn video_khung0_tao.py (vẽ nền Khung0) gọi hai hàm này để ghép ảnh thử; dựng video
# không dùng nữa.
def paste_logo(layer: Image.Image, logo_path: Path) -> Image.Image:
    """Dán logo (cắt sát phần có hình) vào K2_LOGO_BOX, tỉ lệ theo kích thước layer."""
    if not logo_path.exists():
        return layer
    logo = Image.open(logo_path).convert("RGBA")
    bbox = logo.getchannel("A").point(lambda a: 255 if a > 32 else 0).getbbox()
    if bbox:
        logo = logo.crop(bbox)
    cw, ch = layer.size
    sx, sy = cw / 1920, ch / 1080
    x0, y0, x1, y1 = K2_LOGO_BOX
    bw = round(x1 * sx) - round(x0 * sx)
    bh = round(y1 * sy) - round(y0 * sy)
    logo = ImageOps.contain(logo, (bw, bh), method=Image.Resampling.LANCZOS)
    pos = (round(x0 * sx) + (bw - logo.width) // 2, round(y0 * sy) + (bh - logo.height) // 2)
    layer.alpha_composite(logo, pos)
    return layer


def frame_mask(png_path: Path):
    """Trả về (ảnh RGBA, mảng bool pixel VIỀN = pixel không trong suốt) của khung1 cũ."""
    im = Image.open(png_path).convert("RGBA")
    a  = np.array(im)
    return im, a[:, :, 3] > 50


def gom_clip_kho(source_dir, log=print) -> tuple[list[Path], str]:
    """Gom clip .mp4 để ghép random → (danh sách clip, tên kho để ghi log/lỗi).

    source_dir: None/rỗng → cả videongang/ (kho gốc rỗng vì đã dồn clip vào thư mục
    con thì gom MỌI thư mục con); 1 đường dẫn → thư mục đó; list/tuple đường dẫn
    (01/11/2026, ô "Nguồn ngang" tick nhiều) → gộp clip của tất cả rồi build_playlist
    xáo chung. Không có clip → RuntimeError.
    """
    if not source_dir:
        dirs = []
    elif isinstance(source_dir, (str, Path)):
        dirs = [Path(source_dir)]
    else:
        dirs = [Path(d) for d in source_dir if d]
    if not dirs:
        ten = str(VIDEO_DIR)
        videos = sorted(VIDEO_DIR.glob("*.mp4"))
        if not videos:
            videos = sorted(VIDEO_DIR.rglob("*.mp4"))
            if videos:
                log(f"📁 Nguồn video ngang: tất cả thư mục con ({len(videos)} clip)")
    else:
        ten = " + ".join(f"{d.name}/" for d in dirs)
        videos = sorted({v for d in dirs for v in d.glob("*.mp4")})
        if videos:
            log(f"📁 Nguồn video ngang: {ten} ({len(videos)} clip)")
    if not videos:
        raise RuntimeError(f"Không có file .mp4 nào trong: {ten}")
    return videos, ten


def build_video(audio_file: Path, *, mode: str = MODE, log=print, effect=None,
                progress=None, skip_existing=False, output: Path | None = None,
                source_dir=None, logo: Path | None = None, goc_out: Path | None = None,
                source_video: Path | None = None, source_zoom: float = 1.0,
                che_chu: bool = False) -> Path:
    """
    Dựng video ngang không khung + logo nhỏ từ một file audio cụ thể.

    che_chu: (08/11/2026, ô ✂ "Che chữ Trung cháy sẵn", mặc định TẮT) True → cắt bỏ mép trên
             CAT_TREN_MIN / dưới CAT_DUOI_MIN của clip rồi lót dải đen mỏng (logo nằm trong
             dải dưới); False → giữ NGUYÊN khung hình gốc 1:1, không cắt, logo góc trên phải.

    goc_out: (08/09/2026) đường dẫn để xuất THÊM "video gốc" — đoạn video đã ghép +
             hiệu ứng, đã phóng/cắt đúng 1920×1080 nhưng CHƯA dán logo — ngay trong
             cùng lượt ffmpeg (đầu ra thứ hai, không tiếng, nén nhẹ hơn 4 bậc). Bản dọc
             (video_doc_khung) dùng lại file này thay vì ghép clip dọc. Kèm file .json
             cùng tên ghi logo đã chọn + bố cục. None = không xuất.

    Trả về đường dẫn video kết quả. Ném RuntimeError nếu thiếu tài nguyên hoặc
    ffmpeg lỗi (để bên gọi — ví dụ GUI — bắt và hiển thị). `log` là hàm nhận
    chuỗi để ghi tiến trình (mặc định print; GUI truyền logging.info).

    progress: hàm tùy chọn (pct, cur, total, speed) để cập nhật thanh tiến trình
              GUI thay cho việc spam % ra log (xem run_ffmpeg_progress).
    skip_existing: nếu True và video kết quả đã tồn tại thì trả về luôn, KHÔNG
                   dựng lại (chế độ ♻ "chỉ dựng phần còn thiếu").

    output: đường dẫn video kết quả tùy chọn. None (mặc định) → đặt cạnh audio với
            tên <tên_audio>_videodone.mp4. Truyền vào để đặt tên riêng (vd YOUTUBE.mp4);
            skip_existing khi đó kiểm tra ĐÚNG file này nên vẫn "chỉ dựng phần còn thiếu".

    effect: đường dẫn file hiệu ứng (vd .mov có alpha trong scripts/hieuung/).
            Nếu có, hiệu ứng được phủ THẲNG vào video ghép TRƯỚC khi phóng/cắt (lặp
            lại nếu ngắn hơn audio). None = không thêm.

    source_dir: thư mục kho clip ngang để ghép random. None (mặc định) → dùng cả
                videongang/. Truyền 1 thư mục con (vd videongang/thiennhien) để chỉ
                ghép clip theo chủ đề đó, hoặc LIST thư mục con (01/11/2026) → gộp
                clip của tất cả rồi xáo chung (xem gom_clip_kho).

    logo: file logo dán góc trên phải. None (mặc định) → chọn NGẪU NHIÊN một màu trong
          kho logo thumbnail (xem random_logo). Không có file → dựng không logo.

    source_video: (24/10/2026) MỘT video làm nguồn hình thay cho kho clip (video tải
        xuống của tập): tiếng gốc KHÔNG map vào đầu ra (= tắt tiếng), thời lượng kéo/
        nén khớp audio (ti_le_keo), phần thiếu/thừa lặp hoặc cắt. Không đọc được file
        → ghép clip kho như cũ. source_zoom: phóng to nội dung bấy nhiêu lần rồi cắt
        (1.2 = 120%) — thay cho ZOOM mặc định của kho clip.
    """
    # Trả về sớm nếu đã có sẵn (chế độ dùng lại) — tránh dựng lại tốn thời gian.
    audio_file = Path(audio_file)
    output = Path(output) if output else audio_file.parent / (audio_file.stem + "_videodone.mp4")
    if skip_existing and video_hop_le(output):
        log(f"♻ Video ngang đã có → bỏ qua dựng lại: {output.name}")
        return output
    if skip_existing and output.exists():
        log(f"⚠️ {output.name} có sẵn nhưng CỤT/không đọc được (ffmpeg lần trước bị ngắt) → dựng lại.")

    logo = Path(logo) if logo else random_logo()

    # Chuẩn hóa hiệu ứng: bỏ qua nếu rỗng hoặc file không tồn tại.
    effect = Path(effect) if effect else None
    if effect and not effect.exists():
        log(f"[Cảnh báo] Không tìm thấy file hiệu ứng, bỏ qua: {effect}")
        effect = None

    # 🎞 Video nguồn: một file thay cho kho clip; không đọc được thì lùi về kho.
    nguon = Path(source_video) if source_video else None
    nguon_dur = 0.0
    if nguon:
        if not nguon.is_file():
            log(f"[Cảnh báo] Không thấy video nguồn {nguon} → ghép clip kho như cũ.")
            nguon = None
        else:
            try:
                nguon_dur = get_duration(nguon)
            except Exception as e:
                log(f"[Cảnh báo] Không đọc được video nguồn {nguon.name} ({e}) → ghép clip kho như cũ.")
                nguon = None
            if nguon and nguon_dur <= 0.5:
                log(f"[Cảnh báo] Video nguồn {nguon.name} quá ngắn ({nguon_dur:.2f}s) → ghép clip kho như cũ.")
                nguon = None
    ten_kho = ""
    if nguon:
        videos = [nguon]
    else:
        # Kho clip: cả videongang/, 1 thư mục con, hay nhiều thư mục con gộp lại.
        videos, ten_kho = gom_clip_kho(source_dir, log)

    if not audio_file.exists():
        raise RuntimeError(f"Không tìm thấy audio: {audio_file}")
    audio_dur  = get_duration(audio_file)

    cw, ch = CANVAS_W, CANVAS_H
    tmp = Path(tempfile.gettempdir())
    # Phóng: video nguồn theo source_zoom (ô 🎞 bên GUI/web), kho clip theo ZOOM (1:1).
    try:
        zoom = max(1.0, min(float(source_zoom or 1.0), 3.0)) if nguon else ZOOM
    except (TypeError, ValueError):
        zoom = ZOOM
    if mode == "fill":
        loc_dat, zoom, thanh = loc_phu_kin(cw, ch, zoom, bool(che_chu))
    else:  # fit: thu vừa khít (giữ trọn hình), căn giữa, dải đen phần còn lại
        loc_dat = (f"scale={cw}:{ch}:force_original_aspect_ratio=decrease,"
                   f"pad={cw}:{ch}:(ow-iw)/2:(oh-ih)/2:black")
        thanh = 0
    logo_path, co_logo, logo_vi_tri = lop_logo((cw, ch), logo, tmp / "khung_logo.png", thanh)

    concat_list = None
    keo = 1.0
    if nguon:
        # Một video: kéo/nén thời lượng cho khớp audio (lời đọc là bản dịch của chính
        # video này nên hình đi cùng lời); lệch quá mức kẹp thì lặp/cắt phần còn lại.
        keo = ti_le_keo(nguon_dur, audio_dur)
        seq, total = [nguon], nguon_dur * keo
    else:
        # Ghép random tới khi đủ thời lượng audio (clip lỗi đã bị loại khỏi durations)
        durations = probe_durations(videos, log)
        videos = [v for v in videos if v in durations]
        if not videos:
            raise RuntimeError(f"Không đọc được clip nào trong: {ten_kho}")
        seq, total = build_playlist(videos, durations, audio_dur)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt",
                                         delete=False, encoding="utf-8") as f:
            concat_list = Path(f.name)
            for v in seq:
                f.write(f"file '{v.as_posix()}'\n")

    log(f"Bố cục     : {cw}x{ch} không khung, "
        + (f"✂ che chữ Trung: bỏ mép trên {CAT_TREN_MIN:.0%} / dưới {CAT_DUOI_MIN:.0%} của clip"
           if che_chu else "giữ nguyên khung hình gốc (không cắt mép)")
        + (f", dải đen trên/dưới ≈ {thanh} px" if thanh else ""))
    log(f"Logo       : {logo.name if co_logo else '(không thấy) ' + str(logo)} — {logo_vi_tri}")
    log(f"Chế độ     : {mode}  (" + ("giữ 1:1, không phóng" if zoom <= 1.0 + 1e-6 else
        f"phóng {zoom:.3g}x lanczos + làm nét nhẹ") + ")")
    log(f"Audio      : {audio_file.name}  ({audio_dur:.2f}s)")
    if nguon:
        log(f"Video nguồn: {nguon.name} ({nguon_dur:.2f}s) → kéo x{keo:.3f} = {total:.2f}s, "
            f"tắt tiếng gốc, phóng to {zoom * 100:.0f}%"
            + ("" if total >= audio_dur - 0.05 else " (ngắn hơn audio → lặp lại từ đầu)"))
    else:
        log(f"Kho video  : {len(videos)} clip -> ghép {len(seq)} đoạn ({total:.2f}s)")
    log(f"Hiệu ứng   : {effect.name if effect else '(không)'}")
    log(f"Đầu ra     : {output}")

    # ── Bước 1: phủ hiệu ứng THẲNG vào video thô (trước khi phóng/cắt) ──────────
    # Hiệu ứng được scale đúng kích thước video ghép rồi overlay lên video, nên
    # bong bóng "dính" vào nội dung video và bị phóng/cắt cùng video.
    src_label = "[0:v]"
    pre = ""
    if nguon:
        # Kéo/nén thời lượng (setpts) rồi ép fps cho đều khung hình; tiếng gốc không
        # map ra đầu ra nên tự TẮT (file tải về giữ nguyên tiếng).
        pre = f"[0:v]setpts=PTS*{keo:.6f},fps={NGUON_FPS}[nguon];"
        src_label = "[nguon]"
    if effect:
        vw, vh = get_resolution(seq[0])   # các clip đã chuẩn hoá cùng độ phân giải
        pre += (
            f"[3:v]scale={vw}:{vh}:force_original_aspect_ratio=increase,"
            f"crop={vw}:{vh},format=rgba[fx];"
            f"{src_label}[fx]overlay=0:0:shortest=0[srcfx];"
        )
        src_label = "[srcfx]"

    # ── Bước 2: đặt video vào khung cw×ch (loc_dat đã dựng ở trên: cắt mép + dải đen) ──
    noi_dung = loc_dat + ",setsar=1"
    goc_out = Path(goc_out) if goc_out else None
    if goc_out:
        # Video gốc cho bản dọc tách ra TRƯỚC khi cắt/đặt: giữ NGUYÊN cỡ clip (chỉ ép chẵn
        # cho yuv420p) để bản dọc tự cắt đúng vùng cần (1:1, không phóng).
        place = (f"{src_label}split[c1][c2];[c1]{noi_dung}[vid];"
                 f"[c2]scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1[goc];")
    else:
        place = f"{src_label}{noi_dung}[vid];"

    # ── Bước 3: dán lớp logo (PNG trong suốt đã vẽ đúng cw×ch, không scale mỗi frame)
    # Inputs: 0=video(ghép) 1=lớp logo 2=audio [3=hiệu ứng]
    filt = pre + place + "[vid][1:v]overlay=0:0[out]"

    def _codec(gpu, them=0):
        """Tham số mã hoá; `them` = nới chất lượng (CQ/CRF + them) cho đầu ra phụ."""
        if gpu:
            return [
                "-c:v", "h264_nvenc",
                "-preset", "p5",        # cân bằng tốc độ/chất lượng (p7 chậm nhất; p5 nhanh hơn nhiều, mắt thường gần như không phân biệt)
                "-tune", "hq",
                "-rc", "vbr",
                "-cq", str(NVENC_CQ + them),
                "-b:v", "0",            # để CQ tự cấp bitrate theo cảnh
                "-profile:v", "high",
            ]
        return [
            "-c:v", "libx264", "-preset", "slow",
            "-crf", str(X264_CRF + them), "-profile:v", "high",
        ]

    def build_cmd(gpu):
        codec = _codec(gpu)
        cmd = [
            "ffmpeg", "-y",
            "-stream_loop", "-1",                       # lặp video nền: không hết frame trước audio
            # 0: video nguồn (một file, 🎞) hoặc danh sách clip ghép
            *(["-i", str(nguon)] if nguon
              else ["-f", "concat", "-safe", "0", "-i", str(concat_list)]),
            "-loop", "1", "-i", str(logo_path),  # 1: lớp logo (PNG trong suốt cw×ch)
            "-i", str(audio_file),               # 2: audio
        ]
        if effect:
            # -stream_loop -1: lặp vô hạn input hiệu ứng (sẽ bị -t cắt đúng độ dài).
            cmd += ["-stream_loop", "-1", "-i", str(effect)]   # input 3
        cmd += [
            "-filter_complex", filt,
            "-map", "[out]",
            "-map", "2:a",
            "-t", f"{audio_dur:.6f}",           # cắt video đúng bằng độ dài audio
            *codec,
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            str(output),
        ]
        if goc_out:
            # Đầu ra thứ hai: video gốc (không tiếng, chưa phóng/cắt, chưa logo) cho bản dọc —
            # cùng lượt giải mã; nén nhẹ hơn main 2 bậc (là nguồn phóng của bản dọc nên không hạ sâu).
            cmd += ["-map", "[goc]", "-an", "-t", f"{audio_dur:.6f}",
                    *_codec(gpu, 2), "-pix_fmt", "yuv420p", str(goc_out)]
        return cmd

    if goc_out:
        log(f"Video gốc  : {goc_out.name} (video đã ghép nguyên cỡ clip, chưa cắt, chưa logo) "
            f"→ bản dọc tự cắt vùng giữa 1:1")
    use_gpu = USE_GPU and has_nvenc()
    log("Đang dựng video... (GPU - h264_nvenc)" if use_gpu else "Đang dựng video... (CPU - libx264)")
    rc, err_tail = run_ffmpeg_progress(build_cmd(use_gpu), audio_dur, log, progress=progress)
    # GPU lỗi (driver/độ phân giải/encoder) → thử lại bằng CPU để không hỏng cả lượt dựng.
    if rc != 0 and use_gpu:
        log("GPU lỗi, chuyển sang CPU (libx264)...")
        rc, err_tail = run_ffmpeg_progress(build_cmd(False), audio_dur, log, progress=progress)
    # Dọn file tạm — bỏ qua nếu Windows còn khóa (không để rớt cả lượt dựng đã xong).
    for tmp_path in (concat_list, logo_path):
        if tmp_path is None:          # video nguồn: không có danh sách ghép
            continue
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
    if rc != 0:
        xoa_video_cut(output, goc_out, log=log)     # không để file cụt lại thành "đã có"
        raise RuntimeError(f"ffmpeg lỗi:\n{err_tail}")

    if goc_out and goc_out.exists():
        # Ghi kèm bố cục + logo đã chọn: bản dọc dán logo cùng màu, và tập nào mất file gốc
        # thì biết lấy cả khung hình YOUTUBE.mp4 (layout "toanman" = không có viền khung).
        # "goc": "raw" = file gốc chưa cắt mép → bản dọc phải tự bỏ CAT_TREN_MIN/CAT_DUOI_MIN.
        try:
            goc_out.with_suffix(".json").write_text(json.dumps({
                "layout": "toanman", "goc": "raw", "che": bool(che_chu),
                "cat": [CAT_TREN_MIN, CAT_DUOI_MIN], "logo": logo.name if co_logo else "",
                "frame": "", "bg": "", "canvas": [cw, ch],
                "inner": [0, 0, cw, ch], "box": [0, 0, cw, ch], "audio": audio_file.name,
                "source_video": nguon.name if nguon else "",
            }, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception as e:
            log(f"[Cảnh báo] Không ghi được {goc_out.with_suffix('.json').name}: {e}")

    final_dur = get_duration(output)
    size_mb   = output.stat().st_size / 1024 / 1024
    log(f"Hoàn tất! Thời lượng {final_dur:.2f}s — {size_mb:.1f} MB — {output}")
    return output


def main():
    audio_file = find_audio()
    try:
        build_video(audio_file)
    except Exception as e:
        print(f"[LỖI] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
