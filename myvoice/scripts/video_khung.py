"""
Dựng video nền theo độ dài audio rồi lồng vào bộ khung trang trí nhiều lớp.

Quy trình:
  - Lấy thời lượng từ file audio (kịch_bản/*.wav) làm thời lượng đích.
  - Ghép RANDOM các video trong videongang/ (lặp lại tới khi đủ thời lượng audio).
  - Lồng video đã ghép vào khung (cắt bo góc theo khung1).
  - Mux audio gốc (wav) vào, cắt video đúng bằng độ dài audio (-shortest).

Thứ tự lớp (từ dưới lên trên):
  1. Khung0.png       -> nền dưới cùng
  2. video + hiệu ứng -> hiệu ứng phủ THẲNG vào video ghép, rồi cùng đưa vào
                         khung1 và cắt bo góc (dư ra ngoài khung1 bị cắt bỏ)
  3. khung1*.png      -> viền khung video (bo góc); nhiều màu, chọn ngẫu nhiên mỗi lần dựng
  4. khung2.png       -> lớp trang trí trên cùng (chữ/hoa văn), KHÔNG in sẵn logo;
                         logo Mimi audio cùng màu viền được dán vào ô K2_LOGO_BOX

MODE:
  - "fit"  : hiện trọn video (có thể có dải nền trên/dưới) — không mất hình.
  - "fill" : phóng to + cắt cho video phủ kín vùng trong khung.

Đầu ra:  kịch_bản/<tên_audio>_videodone.mp4

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
BG_DIR     = BASE_DIR / "Backbround"
KHUNG0     = BG_DIR / "Khung0.png"     # nền dưới cùng
KHUNG1     = BG_DIR / "khung1.png"     # viền khung video (bo góc) — bản hồng gốc, dự phòng
# Viền khung có NHIỀU màu: khung1.png (hồng), khung1 xanh.png, khung1 tím.png, khung1 đỏ.png ...
# Mỗi lần dựng video chọn NGẪU NHIÊN một viền (random_frame); thêm màu chỉ cần thả file
# "khung1 <màu>.png" CÙNG HÌNH DẠNG (vùng trong dò theo kênh alpha, không theo màu).
KHUNG1_PATTERN = "khung1*.png"
KHUNG2     = BG_DIR / "khung2.png"     # trang trí trên cùng (KHÔNG còn in sẵn logo)
# Logo Mimi audio: dùng chung kho logo của thumbnail (logo.png hồng, logo xanh.png, ...).
# khung2.png đã bỏ logo in sẵn; mỗi lần dựng, logo CÙNG MÀU viền khung1 (logo_for_frame)
# được dán vào K2_LOGO_BOX — đúng ô logo từng chiếm trong khung2 cũ (đo bằng cách so
# khung2 cũ với khung2 đã bỏ logo). Logo nằm DƯỚI khung2 để nút Subscribe đè lên như gốc.
LOGO_DIR   = BASE_DIR / "YOUTUBE" / "thumbnail"
K2_LOGO_BOX = (0, 346, 348, 690)
VIDEO_DIR  = BASE_DIR / "videongang"   # kho video ngang để ghép random
SCRIPT_DIR = BASE_DIR / "kịch_bản"     # nơi chứa audio + xuất video

# Ưu tiên GPU (NVIDIA NVENC) để dựng video; tự fallback về CPU (libx264) nếu GPU lỗi.
USE_GPU = True

# Chiều cao thấp nhất của video xuất. Nếu bộ khung PNG bị thay bằng bản 720p,
# video vẫn được render lại tối thiểu 1080p thay vì hạ theo kích thước khung.
MIN_OUTPUT_HEIGHT = 1080
# Hạ CQ/CRF để ưu tiên chi tiết sau khi ghép khung. File xuất sẽ lớn hơn và
# dựng chậm hơn một chút so với cấu hình mặc định trước đây (CQ 19 / CRF 18).
NVENC_CQ = 16
X264_CRF = 16

MODE  = "fill"      # "fit" hoặc "fill"
INSET = 6           # thu vào trong vài px để không đè lên viền
ZOOM  = 1.25        # phóng to NỘI DUNG video bên trong vùng (1.0 = vừa khít, 1.25 = 125%)
OVERSCAN = 10       # nới VÙNG video ra ngoài N px mỗi cạnh (theo px của khung) để video
                    # luồn xuống dưới viền khung1 — khử viền đen quanh video

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


def _even(value: float) -> int:
    """Kích thước video phải chia hết cho 2 để mã hóa yuv420p."""
    return max(2, int(round(value / 2.0)) * 2)


def output_canvas_size(width: int, height: int) -> tuple[int, int]:
    """Trả về canvas giữ tỷ lệ, cao ít nhất MIN_OUTPUT_HEIGHT."""
    scale = max(1.0, MIN_OUTPUT_HEIGHT / height)
    return _even(width * scale), _even(height * scale)


def scale_box(x: int, y: int, w: int, h: int,
              source_w: int, source_h: int,
              target_w: int, target_h: int) -> tuple[int, int, int, int]:
    """Scale tọa độ vùng trong của khung mà không làm lệch mép."""
    left = round(x * target_w / source_w)
    top = round(y * target_h / source_h)
    right = round((x + w) * target_w / source_w)
    bottom = round((y + h) * target_h / source_h)
    return left, top, right - left, bottom - top


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


def get_duration(path: Path) -> float:
    path = Path(path)
    data = _ffprobe_json(["-show_entries", "format=duration"], path)
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


def probe_durations(videos, log=print) -> dict:
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
            dur = get_duration(v)
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


def list_frames() -> list[Path]:
    """Liệt kê các viền khung video (khung1.png, khung1 xanh.png, ...) theo tên."""
    return sorted(BG_DIR.glob(KHUNG1_PATTERN), key=lambda p: p.name.casefold())


def random_frame() -> Path:
    """Chọn ngẫu nhiên một viền khung; không có file nào thì về khung1.png."""
    frames = list_frames()
    return random.choice(frames) if frames else KHUNG1


def logo_for_frame(frame: Path) -> Path:
    """Logo cùng màu với viền khung1: "khung1 xanh.png" → "logo xanh.png"; thiếu thì logo.png."""
    stem = frame.stem
    suffix = stem[len("khung1"):] if stem.casefold().startswith("khung1") else ""
    candidate = LOGO_DIR / f"logo{suffix}.png"
    return candidate if candidate.exists() else LOGO_DIR / "logo.png"


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
    """Trả về (ảnh RGBA, mảng bool pixel VIỀN = pixel không trong suốt).

    Trước đây dò viền theo MÀU HỒNG nên viền màu khác (xanh/tím/đỏ) không dò được.
    Với khung1.png gốc, pixel hồng trùng khít pixel đục (đã kiểm), nên dò theo alpha
    cho kết quả y hệt mà dùng được mọi màu.
    """
    im = Image.open(png_path).convert("RGBA")
    a  = np.array(im)
    return im, a[:, :, 3] > 50


pink_mask = frame_mask   # tên cũ, giữ cho tương thích


def detect_inner_box(im, pink):
    """Trả về (x, y, w, h) vùng trống bên trong viền khung hồng."""
    ys, xs = np.where(pink)
    if len(xs) == 0:
        raise RuntimeError("Không tìm thấy viền khung trong ảnh PNG.")

    cy, cx = im.height // 2, im.width // 2

    def inner_edges(mask_line):
        idx = np.where(mask_line)[0]
        first_end = idx[0]                       # mép trong của viền đặc bên đầu
        for v in idx[1:]:
            if v == first_end + 1:
                first_end = v
            else:
                break
        last_start = idx[-1]                     # mép trong của viền đặc bên cuối
        for v in idx[-2::-1]:
            if v == last_start - 1:
                last_start = v
            else:
                break
        return first_end, last_start

    left_in, right_in = inner_edges(pink[cy, :])
    top_in, bottom_in = inner_edges(pink[:, cx])

    x = left_in + 1 + INSET
    y = top_in  + 1 + INSET
    w = (right_in - left_in - 1) - 2 * INSET
    h = (bottom_in - top_in - 1) - 2 * INSET
    return x, y, w, h


def prepare_static_layers(pink, target_size: tuple[int, int], frame: Path = KHUNG1,
                          logo: Path | None = None):
    """Pre-scale các lớp khung tĩnh về đúng cw×ch MỘT LẦN bằng PIL.

    Trước đây ffmpeg phải scale (lanczos) khung0/khung1/khung2/mask trên TỪNG frame
    rồi overlay 3 lần — rất tốn CPU với video dài. Ở đây ta:
      - resize sẵn 3 ảnh khung + mask đúng kích thước canvas một lần,
      - gộp khung1+khung2 (đều nằm trên video) thành 1 lớp phủ trên,
    nên filter graph chỉ còn overlay (không scale mỗi frame) và bớt 1 overlay.

    Mask trắng = vùng bên trong khung (kể cả góc bo tròn) nhờ binary_fill_holes lấp
    kín phần trong vòng viền. `frame` = file viền khung1 đang dùng (màu ngẫu nhiên),
    `logo` = logo dán vào ô K2_LOGO_BOX (giữa khung1 và khung2). Trả về (bg_path, top_path, mask_path).
    """
    cw, ch = target_size
    resample = Image.Resampling.LANCZOS
    tmp = Path(tempfile.gettempdir())

    with Image.open(KHUNG0) as src:
        src.convert("RGBA").resize((cw, ch), resample).save(tmp / "khung0_scaled.png")
    bg_path = tmp / "khung0_scaled.png"

    # khung1 -> logo -> khung2: gộp thành một lớp phủ trên cùng (logo dưới khung2 để nút
    # Subscribe của khung2 đè lên mép logo như bản khung2 cũ có logo in sẵn).
    with Image.open(frame) as src1, Image.open(KHUNG2) as src2:
        top = src1.convert("RGBA").resize((cw, ch), resample)
        k2 = src2.convert("RGBA").resize((cw, ch), resample)
    if logo:
        top = paste_logo(top, logo)
    top = Image.alpha_composite(top, k2)
    top_path = tmp / "khung_top.png"
    top.save(top_path)

    show = ndimage.binary_fill_holes(pink)
    mask_img = Image.fromarray(np.where(show, 255, 0).astype("uint8"), "L").resize((cw, ch), resample)
    mask_path = tmp / "khung_mask.png"
    mask_img.save(mask_path)

    return bg_path, top_path, mask_path


def build_video(audio_file: Path, *, mode: str = MODE, log=print, effect=None,
                progress=None, skip_existing=False, output: Path | None = None,
                source_dir: Path | None = None, frame: Path | None = None,
                logo: Path | None = None) -> Path:
    """
    Dựng video nền + khung từ một file audio cụ thể.

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
            Nếu có, hiệu ứng được phủ THẲNG vào video ghép TRƯỚC, rồi mới đưa vào
            khung1 và cắt bo góc (lặp lại nếu ngắn hơn audio). None = không thêm.

    source_dir: thư mục kho clip ngang để ghép random. None (mặc định) → dùng cả
                videongang/. Truyền 1 thư mục con (vd videongang/thiennhien) để chỉ
                ghép clip theo chủ đề đó.

    frame: file viền khung (khung1*.png) cụ thể. None (mặc định) → chọn NGẪU NHIÊN
           một màu trong Backbround/ (xem random_frame).

    logo: file logo dán vào khung2. None (mặc định) → logo CÙNG MÀU với viền đã chọn
          (xem logo_for_frame), lấy từ kho logo thumbnail.
    """
    # Trả về sớm nếu đã có sẵn (chế độ dùng lại) — tránh dựng lại tốn thời gian.
    audio_file = Path(audio_file)
    output = Path(output) if output else audio_file.parent / (audio_file.stem + "_videodone.mp4")
    if skip_existing and output.exists() and output.stat().st_size > 0:
        log(f"♻ Video ngang đã có → bỏ qua dựng lại: {output.name}")
        return output

    frame = Path(frame) if frame else random_frame()
    logo = Path(logo) if logo else logo_for_frame(frame)
    for f in (KHUNG0, frame, KHUNG2):
        if not f.exists():
            raise RuntimeError(f"Không tìm thấy khung: {f}")

    # Chuẩn hóa hiệu ứng: bỏ qua nếu rỗng hoặc file không tồn tại.
    effect = Path(effect) if effect else None
    if effect and not effect.exists():
        log(f"[Cảnh báo] Không tìm thấy file hiệu ứng, bỏ qua: {effect}")
        effect = None

    src_dir = Path(source_dir) if source_dir else VIDEO_DIR
    videos = sorted(src_dir.glob("*.mp4"))
    if not videos and not source_dir:
        # Kho gốc videongang/ rỗng (đã dồn clip vào thư mục con theo chủ đề) → khi
        # chọn "tất cả" thì gom MỌI clip trong các thư mục con thay vì báo lỗi.
        videos = sorted(src_dir.rglob("*.mp4"))
        if videos:
            log(f"📁 Nguồn video ngang: tất cả thư mục con ({len(videos)} clip)")
    if not videos:
        raise RuntimeError(f"Không có file .mp4 nào trong: {src_dir}")
    if source_dir:
        log(f"📁 Nguồn video ngang: {src_dir.name}/ ({len(videos)} clip)")

    audio_file = Path(audio_file)
    if not audio_file.exists():
        raise RuntimeError(f"Không tìm thấy audio: {audio_file}")
    audio_dur  = get_duration(audio_file)
    # output đã được xác định ở trên (tôn trọng tham số output tùy chọn).

    # Khung + vùng trong + mặt nạ bo góc (lấy từ viền khung1 đã chọn)
    im, pink = frame_mask(frame)
    source_w, source_h = im.size
    cw, ch = output_canvas_size(source_w, source_h)
    ix, iy, iw, ih = detect_inner_box(im, pink)
    ix, iy, iw, ih = scale_box(
        ix, iy, iw, ih, source_w, source_h, cw, ch
    )
    bg_path, top_path, mask_path = prepare_static_layers(pink, (cw, ch), frame, logo)

    # Ghép random tới khi đủ thời lượng audio (clip lỗi đã bị loại khỏi durations)
    durations = probe_durations(videos, log)
    videos = [v for v in videos if v in durations]
    if not videos:
        raise RuntimeError(f"Không đọc được clip nào trong: {src_dir}")
    seq, total = build_playlist(videos, durations, audio_dur)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt",
                                     delete=False, encoding="utf-8") as f:
        concat_list = Path(f.name)
        for v in seq:
            f.write(f"file '{v.as_posix()}'\n")

    log(f"Khung gốc  : {source_w}x{source_h}")
    log(f"Viền khung : {frame.name}")
    log(f"Logo       : {logo.name if logo.exists() else '(không thấy) ' + str(logo)}")
    log(f"Video xuất : {cw}x{ch} (tối thiểu {MIN_OUTPUT_HEIGHT}p)")
    log(f"Vùng trong : x={ix} y={iy} {iw}x{ih}")
    log(f"Chế độ     : {mode}  (zoom {ZOOM:g}x, nới {OVERSCAN}px)")
    log(f"Audio      : {audio_file.name}  ({audio_dur:.2f}s)")
    log(f"Kho video  : {len(videos)} clip -> ghép {len(seq)} đoạn ({total:.2f}s)")
    log(f"Hiệu ứng   : {effect.name if effect else '(không)'}")
    log(f"Đầu ra     : {output}")

    # ── Bước 1: phủ hiệu ứng THẲNG vào video thô (trước khi đưa vào khung) ──────
    # Hiệu ứng được scale đúng kích thước video ghép rồi overlay lên video, nên
    # bong bóng "dính" vào nội dung video; khi đưa video vào khung + cắt bo góc thì
    # hiệu ứng cũng bị cắt theo đúng vùng khung1 (không tràn ra nền/khung).
    src_label = "[0:v]"
    pre = ""
    if effect:
        vw, vh = get_resolution(seq[0])   # các clip đã chuẩn hoá cùng độ phân giải
        pre = (
            f"[5:v]scale={vw}:{vh}:force_original_aspect_ratio=increase,"
            f"crop={vw}:{vh},format=rgba[fx];"
            f"[0:v][fx]overlay=0:0:shortest=0[srcfx];"
        )
        src_label = "[srcfx]"

    # ── Bước 2: đưa video (đã có hiệu ứng) vào vùng trong của khung ────────────
    if mode == "fill":
        # Nới vùng đặt video ra ngoài OVERSCAN px mỗi cạnh (theo px của khung) để
        # video luồn xuống dưới viền khung1 → khử viền đen. Đây là "phóng to so với
        # khung", khác hẳn ZOOM (phóng to nội dung video bên trong vùng đó).
        overscan_x = round(OVERSCAN * cw / source_w)
        overscan_y = round(OVERSCAN * ch / source_h)
        bx = max(0, ix - overscan_x)
        by = max(0, iy - overscan_y)
        bw = min(iw + 2 * overscan_x, cw - bx)
        bh = min(ih + 2 * overscan_y, ch - by)
        # Phủ kín vùng (đã nới); ZOOM>1 thì phóng nội dung rồi cắt giữa về đúng vùng.
        zw, zh = round(bw * ZOOM), round(bh * ZOOM)
        place = (
            f"{src_label}scale={zw}:{zh}:force_original_aspect_ratio=increase,"
            f"crop={bw}:{bh},pad={cw}:{ch}:{bx}:{by}:black[vid];"
        )
    else:  # fit
        # Thu vừa khít (giữ trọn hình), căn giữa trong vùng khung
        place = (
            f"{src_label}scale={iw}:{ih}:force_original_aspect_ratio=decrease,"
            f"pad={cw}:{ch}:{ix}+({iw}-iw)/2:{iy}+({ih}-ih)/2:black[vid];"
        )

    # ── Bước 3: xếp lớp khung — nền khung0 -> video (cắt bo góc) -> khung1+khung2
    # Hiệu ứng đã nằm sẵn trong [vid] (cắt bo góc cùng video), nên lớp khung phủ
    # bình thường lên trên; phần hiệu ứng dư ra ngoài khung1 đã bị mask cắt bỏ.
    # Các lớp khung tĩnh đã được pre-scale đúng cw×ch (xem prepare_static_layers),
    # nên KHÔNG scale lại mỗi frame; khung1+khung2 đã gộp sẵn thành 1 lớp phủ trên.
    # Inputs: 0=video(ghép) 1=khung0 2=khung_top 3=mask 4=audio [5=hiệu ứng]
    filt = (
        pre + place +
        f"[3:v]format=gray[mask];"
        f"[vid][mask]alphamerge[va];"
        f"[1:v][va]overlay=0:0[b1];"
        f"[b1][2:v]overlay=0:0[out]"
    )

    def build_cmd(gpu):
        if gpu:
            codec = [
                "-c:v", "h264_nvenc",
                "-preset", "p5",        # cân bằng tốc độ/chất lượng (p7 chậm nhất; p5 nhanh hơn nhiều, mắt thường gần như không phân biệt)
                "-tune", "hq",
                "-rc", "vbr",
                "-cq", str(NVENC_CQ),
                "-b:v", "0",            # để CQ tự cấp bitrate theo cảnh
                "-profile:v", "high",
            ]
        else:
            codec = [
                "-c:v", "libx264", "-preset", "slow",
                "-crf", str(X264_CRF), "-profile:v", "high",
            ]
        cmd = [
            "ffmpeg", "-y",
            "-stream_loop", "-1",                       # lặp video nền: không hết frame trước audio
            "-f", "concat", "-safe", "0", "-i", str(concat_list),   # 0: video ghép
            "-loop", "1", "-i", str(bg_path),    # 1: khung0 (nền) đã pre-scale
            "-loop", "1", "-i", str(top_path),   # 2: khung1+khung2 gộp, đã pre-scale
            "-loop", "1", "-i", str(mask_path),  # 3: mask bo góc đã pre-scale
            "-i", str(audio_file),               # 4: audio
        ]
        if effect:
            # -stream_loop -1: lặp vô hạn input hiệu ứng (sẽ bị -t cắt đúng độ dài).
            cmd += ["-stream_loop", "-1", "-i", str(effect)]   # input 5
        cmd += [
            "-filter_complex", filt,
            "-map", "[out]",
            "-map", "4:a",
            "-t", f"{audio_dur:.6f}",           # cắt video đúng bằng độ dài audio
            *codec,
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            str(output),
        ]
        return cmd

    use_gpu = USE_GPU and has_nvenc()
    log("Đang dựng video... (GPU - h264_nvenc)" if use_gpu else "Đang dựng video... (CPU - libx264)")
    rc, err_tail = run_ffmpeg_progress(build_cmd(use_gpu), audio_dur, log, progress=progress)
    # GPU lỗi (driver/độ phân giải/encoder) → thử lại bằng CPU để không hỏng cả lượt dựng.
    if rc != 0 and use_gpu:
        log("GPU lỗi, chuyển sang CPU (libx264)...")
        rc, err_tail = run_ffmpeg_progress(build_cmd(False), audio_dur, log, progress=progress)
    # Dọn file tạm — bỏ qua nếu Windows còn khóa (không để rớt cả lượt dựng đã xong).
    for tmp_path in (concat_list, bg_path, top_path, mask_path):
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
    if rc != 0:
        raise RuntimeError(f"ffmpeg lỗi:\n{err_tail}")

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
