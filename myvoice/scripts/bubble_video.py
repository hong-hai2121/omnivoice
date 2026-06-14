"""
Hiệu ứng BONG BÓNG XÀ PHÒNG 3D ánh cầu vồng — render THẲNG lên video theo clip.

Đường đi: bong bóng bay THẲNG theo đường xéo từ góc TRÁI-DƯỚI → PHẢI-TRÊN
(không ziczac). Có 2 loại tốc độ: NHANH và CHẬM.

Hiệu ứng tổng thể của cả clip: TRỐNG → ĐẦY → TAN
  - Đầu clip màn hình trống, bong bóng sinh dần từ đáy bay lên cho đầy.
  - Cuối clip cả lớp bong bóng MỜ TAN dần (FADE_OUT_SEC giây cuối).

Vẻ ngoài bong bóng (giống quả cầu 3D, không bị phẳng):
  - Fresnel: tâm rất trong, càng ra mép càng đục/sáng (rìa quả cầu thuỷ tinh).
  - Màng xà phòng: số vòng màu cầu vồng tăng theo 1/cosθ → vòng màu dồn ở rìa.
  - Viền sáng mảnh + đốm specular → có khối.
  - Bên trong là ẢNH (thư mục Anh/) bo tròn, hoặc nốt nhạc nếu không có ảnh.
  - Thêm bong bóng "bé tý" trang trí (không ảnh).

Cách làm: render từng frame lớp bong bóng (RGBA trong suốt) rồi PIPE thẳng cho
ffmpeg overlay lên video gốc trong 1 lượt, GIỮ nguyên âm thanh gốc (không tạo
file overlay trung gian).

Cách dùng:
    python bubble_video.py                   # render lên INPUT -> OUTPUT
    python bubble_video.py in.mp4 out.mp4    # render lên video chỉ định

Thư viện: numpy, Pillow (vẽ nốt nhạc), ffmpeg/ffprobe.
"""

import sys
import math
import random
import colorsys
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


# ════════════════════════════════════════════════════════════════════════════
#  THAM SỐ — chỉnh tại đây
# ════════════════════════════════════════════════════════════════════════════
_HERE = Path(__file__).resolve().parent

INPUT  = "D:/Python/omnivoice/OmniVoice/myvoice/videongang/一起来邂逅宫崎骏的夏天_哔哩哔哩_bilibili.mp4"
OUTPUT = "D:/Python/omnivoice/OmniVoice/myvoice/scripts/bubbles_output.mp4"

# — Render theo từng clip: TRỐNG → ĐẦY → TAN —
CLIP_SECONDS     = 30.0      # độ dài video kết quả (giây); None = lấy trọn độ dài video gốc
SPAWN_RATE       = 2.2       # số bong bóng sinh ra mỗi giây (đầu clip trống, sinh dần cho đầy)
MAX_BUBBLES      = 16        # số bong bóng tối đa hiện cùng lúc (mật độ; nhỏ = thưa)
FADE_OUT_SEC     = 3.0       # vài giây CUỐI clip: cả lớp bong bóng mờ tan dần
COLOR_ROT_SPEED  = 0.05      # tốc độ xoay màu cầu vồng (vòng/giây)

# — Đường đi: bay THẲNG theo đường xéo trái-dưới → phải-trên (không ziczac) —
SLOW_SPEED       = 100.0      # tốc độ bay (dọc) của loại CHẬM (px/giây) — +20%
FAST_SPEED       = 228.0     # tốc độ bay (dọc) của loại NHANH (px/giây) — +20%
FAST_FRAC        = 0.40      # tỉ lệ bong bóng loại NHANH (còn lại là chậm)
DRIFT_RATIO      = 0.55      # độ "xéo": tỉ lệ ngang/dọc (>0 = lệch sang PHẢI khi bay lên)

# — Số lượng & kích thước —
TINY_FRAC        = 0.45      # tỉ lệ bong bóng "bé tý" trang trí (không ảnh)
SIZE_MIN         = 75        # đường kính nhỏ nhất của bong bóng có ảnh (px)
SIZE_MAX         = 160       # đường kính lớn nhất (px)
TINY_MIN         = 18        # đường kính bé nhất của loại bé tý (px)
TINY_MAX         = 44        # đường kính lớn nhất của loại bé tý (px)
FADE_START_FRAC  = 0.18      # mỗi bong bóng mờ nhẹ khi tâm vào 18% trên cùng (tránh cắt cứng ở đỉnh)

# — Vẻ ngoài 3D / màng xà phòng —
CENTER_ALPHA     = 0.05      # độ đục ở TÂM (rất trong)
EDGE_ALPHA       = 0.42      # độ đục ở RÌA (Fresnel) — tăng dần từ tâm ra mép
FRESNEL_POWER    = 3.0       # độ cong Fresnel (lớn = tâm trong hơn, dồn đục ra mép)
RING_DENSITY     = 0.55      # mật độ vòng màu cầu vồng (dồn ở rìa → cảm giác 3D)
RING_ASYM        = 0.22      # lệch màu nhẹ theo góc cho tự nhiên
RIM_ALPHA        = 0.55      # độ đậm viền sáng ngoài cùng
RIM_WHITE        = 0.85      # độ trắng của viền
HIGHLIGHT_STR    = 1.00      # độ sáng đốm specular chính
NOTE_ALPHA       = 0.80      # độ đậm của nốt nhạc (chỉ dùng khi KHÔNG có ảnh)

# — Ảnh bên trong bong bóng (thay cho nốt nhạc) —
IMAGE_DIR        = str(_HERE.parent / "Anh")   # thư mục ảnh; rỗng/không ảnh → quay lại nốt nhạc
IMAGE_EXTS       = {".png", ".jpg", ".jpeg", ".webp"}
INNER_FRAC       = 0.72      # đường kính ảnh (bo tròn) so với đường kính bong bóng
INNER_OPACITY    = 0.92      # độ rõ của ảnh trên nền video (1 = đặc)

# — Màu cầu vồng —
RAINBOW_SAT      = 0.90      # độ bão hoà
RAINBOW_VAL      = 1.00      # độ sáng

# — Khác —
SEED             = 42        # hạt ngẫu nhiên cố định (None = mỗi lần khác nhau)
FFMPEG           = "ffmpeg"
FFPROBE          = "ffprobe"


# ── Ép UTF-8 cho stdout/stderr khi chạy độc lập (in được tiếng Việt) ──────────
for _name in ("stdout", "stderr"):
    _s = getattr(sys, _name)
    if hasattr(_s, "buffer"):
        import io
        setattr(sys, _name, io.TextIOWrapper(_s.buffer, encoding="utf-8", errors="replace"))


# ── Bảng màu cầu vồng 256 màu (hue → RGB), tính sẵn 1 lần ────────────────────
def _build_palette() -> np.ndarray:
    pal = np.zeros((256, 3), dtype=np.float32)
    for i in range(256):
        r, g, b = colorsys.hsv_to_rgb(i / 256.0, RAINBOW_SAT, RAINBOW_VAL)
        pal[i] = (r * 255.0, g * 255.0, b * 255.0)
    return pal

PALETTE = _build_palette()


def _load_image_paths():
    p = Path(IMAGE_DIR)
    if not p.exists():
        return []
    return sorted(q for q in p.iterdir() if q.suffix.lower() in IMAGE_EXTS)

IMAGES = _load_image_paths()   # danh sách ảnh để bỏ vào bong bóng (rỗng → dùng nốt nhạc)


def _smoothstep(e0: float, e1: float, x: np.ndarray) -> np.ndarray:
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


# ── Vẽ nốt nhạc bằng vector (không phụ thuộc font) ───────────────────────────
#   style 1 = ♪ · style 2 = ♫ (1 dầm) · style 3 = ♬ (2 dầm)
def _render_note(d: int, style: int) -> np.ndarray:
    img = Image.new("L", (d, d), 0)
    dr = ImageDraw.Draw(img)
    f = float(d)
    hw, hh = 0.20 * f, 0.15 * f
    st = max(2, int(round(0.040 * f)))

    def head(cx, cy):
        dr.ellipse([cx - hw / 2, cy - hh / 2, cx + hw / 2, cy + hh / 2], fill=255)

    def stem(x, y_bottom, y_top):
        dr.line([(x, y_bottom), (x, y_top)], fill=255, width=st)

    if style == 1:
        cx, cy = 0.42 * f, 0.64 * f
        head(cx, cy)
        sx = cx + hw / 2 - st / 2
        ytop = 0.30 * f
        stem(sx, cy, ytop)
        dr.polygon([(sx, ytop), (sx + 0.15 * f, ytop + 0.07 * f),
                    (sx + 0.11 * f, ytop + 0.21 * f), (sx, ytop + 0.13 * f)], fill=255)
    else:
        cx1, cx2 = 0.32 * f, 0.62 * f
        cy = 0.66 * f
        head(cx1, cy)
        head(cx2, cy)
        sx1 = cx1 + hw / 2 - st / 2
        sx2 = cx2 + hw / 2 - st / 2
        ytop = 0.32 * f
        stem(sx1, cy, ytop)
        stem(sx2, cy, ytop)
        bt = max(2, int(round(0.075 * f)))
        dr.line([(sx1, ytop), (sx2, ytop)], fill=255, width=bt)
        if style == 3:
            y2 = ytop + 0.11 * f
            dr.line([(sx1, y2), (sx2, y2)], fill=255, width=bt)

    return np.asarray(img, dtype=np.float32) / 255.0


# ── Đặt ẢNH (bo tròn) vào giữa bong bóng — thay cho nốt nhạc ──────────────────
def _circular_mask(d: int, frac: float) -> np.ndarray:
    """Mặt nạ tròn mềm: 1 trong bán kính 'frac' (chuẩn hoá), mờ dần về 0 ở mép."""
    R = d / 2.0
    yy, xx = np.mgrid[0:d, 0:d].astype(np.float32)
    c = (d - 1) / 2.0
    rn = np.sqrt(((xx - c) / R) ** 2 + ((yy - c) / R) ** 2)
    return (1.0 - _smoothstep(frac - 0.04, frac, rn)).astype(np.float32)


def _build_inner_image(path: Path, d: int):
    """Nạp ảnh, scale 'cover' rồi bo tròn vào giữa. Trả (rgb d×d×3, alpha d×d)."""
    box = max(1, int(round(d * INNER_FRAC)))
    im = Image.open(path).convert("RGBA")
    iw, ih = im.size
    s = box / min(iw, ih)                                     # phủ kín ô vuông (cover)
    im = im.resize((max(1, round(iw * s)), max(1, round(ih * s))), Image.LANCZOS)
    nw, nh = im.size
    left, top = (nw - box) // 2, (nh - box) // 2
    im = im.crop((left, top, left + box, top + box))          # cắt giữa thành ô box×box
    arr = np.asarray(im, dtype=np.float32)

    rgb = np.zeros((d, d, 3), np.float32)
    a = np.zeros((d, d), np.float32)
    off = (d - box) // 2
    rgb[off:off + box, off:off + box] = arr[..., :3]
    a[off:off + box, off:off + box] = arr[..., 3] / 255.0
    a *= _circular_mask(d, INNER_FRAC)                        # bo tròn + tôn trọng alpha ảnh
    return rgb, a


def _build_inner_note(d: int, style: int):
    """Nốt nhạc trắng (dùng khi không có ảnh). Trả (rgb d×d×3 trắng, alpha d×d)."""
    a = (_render_note(d, style) * NOTE_ALPHA).astype(np.float32)
    rgb = np.full((d, d, 3), 255.0, np.float32)
    return rgb, a


def _build_inner(d: int, inner_key):
    kind, val = inner_key
    if kind == "img":
        return _build_inner_image(IMAGES[val], d)
    if kind == "note":
        return _build_inner_note(d, val)
    # "none": bong bóng trơn (loại bé tý trang trí) — không có gì bên trong
    return np.zeros((d, d, 3), np.float32), np.zeros((d, d), np.float32)


# ── Dựng hình dạng tĩnh 3D của một bong bóng (cache theo (đường kính, nội dung)) ──
def _build_sprite(d: int, inner_key):
    R = d / 2.0
    yy, xx = np.mgrid[0:d, 0:d].astype(np.float32)
    c = (d - 1) / 2.0
    nx = (xx - c) / R
    ny = (yy - c) / R
    r = np.sqrt(nx * nx + ny * ny)
    rr = np.clip(r, 0.0, 0.999)
    inside = r <= 1.0

    # Màng xà phòng: số vòng màu ~ 1/cosθ (path = 1/√(1−r²)) → vòng màu dồn ở rìa
    path = 1.0 / np.sqrt(1.0 - rr * rr)
    ang = np.arctan2(ny, nx) / (2.0 * math.pi)
    hue = (RING_DENSITY * (path - 1.0) + RING_ASYM * ang) % 1.0
    base_idx = ((hue * 256.0).astype(np.int32) & 255).astype(np.uint8)

    # Khử răng cưa ở mép ngoài
    edge = 1.0 - _smoothstep(0.985, 1.0, r)

    # Fresnel: trong ở tâm, đục dần ra rìa (rìa quả cầu phản xạ mạnh)
    fres = rr ** FRESNEL_POWER
    base_alpha = np.where(inside, CENTER_ALPHA + (EDGE_ALPHA - CENTER_ALPHA) * fres, 0.0).astype(np.float32)
    white_mix = np.zeros_like(base_alpha)

    # Viền sáng mảnh ngoài cùng
    rim = np.exp(-((r - 0.965) / 0.022) ** 2).astype(np.float32)
    base_alpha += rim * RIM_ALPHA
    white_mix += rim * RIM_WHITE

    # Specular chính (sắc + quầng mềm) ở góc trên-trái
    hd = np.sqrt((nx + 0.42) ** 2 + (ny + 0.46) ** 2)
    spec = np.exp(-(hd / 0.10) ** 2) + 0.35 * np.exp(-(hd / 0.24) ** 2)
    white_mix += spec * HIGHLIGHT_STR
    base_alpha += spec * 0.55

    # Specular phụ nhỏ (góc dưới-phải) cho cảm giác khối
    hd2 = np.sqrt((nx - 0.30) ** 2 + (ny - 0.40) ** 2)
    spec2 = np.exp(-(hd2 / 0.07) ** 2) * 0.5
    white_mix += spec2
    base_alpha += spec2 * 0.3

    base_alpha = np.clip(base_alpha, 0.0, 1.0) * edge
    white_mix = np.clip(white_mix, 0.0, 1.0) * edge

    # Nội dung bên trong (ảnh hoặc nốt nhạc), giữ trong vùng tâm
    inner_rgb, inner_a = _build_inner(d, inner_key)
    inner_a = (inner_a * (r <= 0.97)).astype(np.float32)

    return base_idx, base_alpha, white_mix, inner_rgb, inner_a


_SPRITE_CACHE: dict = {}

def _get_sprite(d: int, inner_key):
    spr = _SPRITE_CACHE.get((d, inner_key))
    if spr is None:
        spr = _build_sprite(d, inner_key)
        _SPRITE_CACHE[(d, inner_key)] = spr
    return spr


class Bubble:
    __slots__ = ("d", "inner_key", "hue_phase", "x0", "y0", "speed", "vx",
                 "t_spawn", "t_despawn", "sprite")


def _make_bubble(rng: random.Random, W: int, H: int, t_spawn: float) -> Bubble:
    b = Bubble()
    if rng.random() < TINY_FRAC:
        b.d = int(rng.uniform(TINY_MIN, TINY_MAX))
        b.inner_key = ("none", 0)                               # bé tý → bong bóng trơn
    else:
        b.d = int(rng.uniform(SIZE_MIN, SIZE_MAX))
        if IMAGES:
            b.inner_key = ("img", rng.randrange(len(IMAGES)))   # ảnh ngẫu nhiên từ Anh/
        else:
            b.inner_key = ("note", rng.choice((1, 2, 3)))       # không có ảnh → nốt nhạc
    b.hue_phase = rng.random()
    r = b.d / 2.0
    # 2 loại tốc độ: nhanh / chậm
    speed = FAST_SPEED if rng.random() < FAST_FRAC else SLOW_SPEED
    b.speed = speed                                            # tốc độ bay lên (dọc), px/giây
    b.vx = speed * DRIFT_RATIO                                 # trôi ngang → bay THẲNG xéo sang phải
    b.x0 = rng.uniform(-H * DRIFT_RATIO, W)                    # trải sang trái để vào từ góc dưới-trái
    b.y0 = H + r                                               # sinh ngay dưới đáy (vô hình)
    b.t_spawn = t_spawn
    b.t_despawn = t_spawn + (H + 2.0 * r) / speed              # khi bay hẳn ra khỏi đỉnh
    b.sprite = _get_sprite(b.d, b.inner_key)
    return b


def _build_schedule(W: int, H: int, duration: float):
    """Lịch sinh bong bóng: đầu clip TRỐNG, sinh dần từ đáy cho đầy; ngừng sinh gần cuối."""
    rng = random.Random(SEED)
    bubbles, intervals = [], []
    stop_spawn = max(0.0, duration - FADE_OUT_SEC)             # ngừng sinh khi bắt đầu mờ tan
    t = 0.0
    while t < stop_spawn:
        ncur = sum(1 for (a, b) in intervals if a <= t <= b)   # số đang hiện tại thời điểm t
        if ncur < MAX_BUBBLES:
            bub = _make_bubble(rng, W, H, t)
            bubbles.append(bub)
            intervals.append((bub.t_spawn, bub.t_despawn))
        t += (1.0 / SPAWN_RATE) * rng.uniform(0.7, 1.3)        # nhịp sinh có nhiễu nhẹ
    return bubbles


def _global_fade(t: float, duration: float) -> float:
    """=1.0 gần như suốt clip; ramp 1→0 trong FADE_OUT_SEC giây cuối (cả lớp mờ tan)."""
    if t >= duration - FADE_OUT_SEC:
        return max(0.0, (duration - t) / FADE_OUT_SEC)
    return 1.0


def _composite_over(layer: np.ndarray, b: Bubble, cx: float, cy: float,
                    fade: float, rot: float, W: int, H: int):
    """Trộn (alpha-over) một bong bóng lên lớp RGBA trong suốt 'layer' (uint8 HxWx4)."""
    d = b.d
    x0 = int(round(cx - d / 2.0))
    y0 = int(round(cy - d / 2.0))
    fx0 = x0 if x0 > 0 else 0
    fy0 = y0 if y0 > 0 else 0
    fx1 = x0 + d if x0 + d < W else W
    fy1 = y0 + d if y0 + d < H else H
    if fx0 >= fx1 or fy0 >= fy1:
        return
    sx0, sy0 = fx0 - x0, fy0 - y0
    sx1, sy1 = sx0 + (fx1 - fx0), sy0 + (fy1 - fy0)

    base_idx, base_alpha, white_mix, inner_rgb, inner_a = b.sprite

    rot_i = np.uint8(int(rot * 256.0) & 255)
    idx = base_idx[sy0:sy1, sx0:sx1] + rot_i
    rgb = PALETTE[idx]                                   # (h,w,3) float32 0..255 — màng cầu vồng

    ia = inner_a[sy0:sy1, sx0:sx1, None]
    rgb = rgb * (1.0 - ia) + inner_rgb[sy0:sy1, sx0:sx1] * ia    # ẢNH bên trong

    wm = white_mix[sy0:sy1, sx0:sx1, None]
    rgb = rgb * (1.0 - wm) + 255.0 * wm                          # viền + highlight ĐÈ lên trên (phản xạ)

    # Độ đục: nơi có ảnh thì đặc hơn (để nhìn rõ ảnh trên video)
    a = np.maximum(base_alpha[sy0:sy1, sx0:sx1], inner_a[sy0:sy1, sx0:sx1] * INNER_OPACITY)
    np.minimum(a, 1.0, out=a)
    a = a * fade

    # alpha-over lên nền trong suốt: out = src trên dst
    reg = layer[fy0:fy1, fx0:fx1].astype(np.float32)
    ra = reg[..., 3:4] / 255.0
    rrgb = reg[..., :3] / 255.0
    sa = a[:, :, None]
    srgb = rgb / 255.0
    out_a = sa + ra * (1.0 - sa)
    safe = np.maximum(out_a, 1e-6)
    out_rgb = (srgb * sa + rrgb * ra * (1.0 - sa)) / safe
    reg[..., :3] = np.clip(out_rgb * 255.0, 0, 255)
    reg[..., 3:4] = np.clip(out_a * 255.0, 0, 255)
    layer[fy0:fy1, fx0:fx1] = reg.astype(np.uint8)


def _render_frame(t: float, bubbles, W: int, H: int, duration: float) -> np.ndarray:
    """Một frame lớp bong bóng RGBA (nền trong suốt) tại thời điểm t (giây)."""
    layer = np.zeros((H, W, 4), dtype=np.uint8)
    gfade = _global_fade(t, duration)                    # mờ tan toàn cục ở cuối clip
    if gfade <= 0.0:
        return layer
    fade_start_y = H * FADE_START_FRAC
    for b in bubbles:
        if t < b.t_spawn or t > b.t_despawn:
            continue
        age = t - b.t_spawn
        y = b.y0 - b.speed * age                          # bay lên
        if y >= fade_start_y:
            fade = gfade
        else:
            fade = (y / fade_start_y) * gfade             # mờ nhẹ khi tới đỉnh
            if fade <= 0.01:
                continue
        x = b.x0 + b.vx * age                             # đường THẲNG xéo, không ziczac
        rot = t * COLOR_ROT_SPEED + b.hue_phase
        _composite_over(layer, b, x, y, fade, rot, W, H)
    return layer


# ════════════════════════════════════════════════════════════════════════════
#  RENDER bong bóng THẲNG lên video (trống → đầy → tan), giữ âm thanh gốc
#  Pipe từng frame RGBA cho ffmpeg overlay lên video gốc trong 1 lượt.
# ════════════════════════════════════════════════════════════════════════════
def render_onto_video(in_path: Path, out_path: Path):
    W, H = _probe_size(in_path)
    fps = _probe_fps(in_path)
    duration = _probe_duration(in_path)
    has_audio = _has_audio(in_path)
    n_frames = int(round(duration * fps))
    bubbles = _build_schedule(W, H, duration)
    print(f"Khung {W}x{H}  fps={fps:.3f}  dài={duration:.2f}s  — {len(bubbles)} bong bóng")

    # input 0 = video gốc · input 1 = lớp bong bóng (rawvideo qua stdin)
    filt = "[0:v][1:v]overlay=0:0:format=auto[v]"
    cmd = [
        FFMPEG, "-y",
        "-i", str(in_path),
        "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-r", f"{fps}", "-i", "-",
        "-filter_complex", filt,
        "-map", "[v]",
    ]
    if has_audio:
        cmd += ["-map", "0:a", "-c:a", "copy"]            # giữ nguyên âm thanh gốc
    cmd += [
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
        "-shortest", str(out_path),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        for i in range(n_frames):
            frame = _render_frame(i / fps, bubbles, W, H, duration)
            proc.stdin.write(frame.tobytes())
            if (i + 1) % max(1, n_frames // 10) == 0:
                print(f"  {i + 1}/{n_frames} frame")
    finally:
        proc.stdin.close()
        rc = proc.wait()
    if rc != 0:
        print("[LỖI] ffmpeg render thất bại.", file=sys.stderr)
        sys.exit(1)


# ════════════════════════════════════════════════════════════════════════════
#  GHÉP overlay (LẶP) lên video, giữ âm thanh gốc — do ffmpeg làm (nhanh)
# ════════════════════════════════════════════════════════════════════════════
def _probe_size(p: Path):
    r = subprocess.run(
        [FFPROBE, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", str(p)],
        capture_output=True, text=True)
    w, h = r.stdout.strip().split("x")
    return int(w), int(h)


def _has_audio(p: Path) -> bool:
    r = subprocess.run(
        [FFPROBE, "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=index", "-of", "csv=p=0", str(p)],
        capture_output=True, text=True)
    return bool(r.stdout.strip())


def _probe_fps(p: Path) -> float:
    r = subprocess.run(
        [FFPROBE, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", str(p)],
        capture_output=True, text=True)
    num, den = r.stdout.strip().split("/")
    return float(num) / float(den)


def _probe_duration(p: Path) -> float:
    r = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(p)],
        capture_output=True, text=True)
    return float(r.stdout.strip())


def main():
    args = sys.argv[1:]
    in_path = Path(args[0]) if len(args) >= 1 else Path(INPUT)
    out_path = Path(args[1]) if len(args) >= 2 else Path(OUTPUT)
    if not in_path.exists():
        print(f"[LỖI] Không tìm thấy video đầu vào: {in_path}")
        sys.exit(1)

    print(f"Render bong bóng lên: {in_path.name}  (trống → đầy → tan, giữ âm thanh gốc)")
    render_onto_video(in_path, out_path)
    print(f"Hoàn tất → {out_path}")


if __name__ == "__main__":
    main()
