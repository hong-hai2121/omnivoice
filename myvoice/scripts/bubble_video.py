"""
Hiệu ứng BONG BÓNG XÀ PHÒNG 3D ánh cầu vồng — render THẲNG lên video theo clip.

Đường đi: bong bóng bay THẲNG theo đường xéo từ góc TRÁI-DƯỚI → PHẢI-TRÊN
(không ziczac). Có 2 loại tốc độ: NHANH và CHẬM.

Hiệu ứng tổng thể của cả clip: TRỐNG → ĐẦY → TAN
  - Đầu clip màn hình trống, bong bóng sinh dần từ đáy bay lên cho đầy.
  - Cuối clip cả lớp bong bóng MỜ TAN dần (FADE_OUT_SEC giây cuối).

Vẻ ngoài bong bóng: DÙNG ẢNH vỏ ngoài có sẵn (anhla/vongoai.png), phóng/thu theo
cỡ — KHÔNG tự vẽ vành cầu vồng/viền/đốm sáng nữa.
  - Vỏ bong bóng = ảnh vongoai.png (đã có sẵn vành óng ánh + phản xạ).
  - Bên trong là ẢNH (thư mục Anh/) bo tròn đặt giữa, hoặc nốt nhạc nếu không có ảnh.
  - Đốm phản xạ sáng của vỏ được "screen" đè lại lên ảnh để trông như nằm sau lớp kính.
  - Thêm bong bóng "bé tý" trang trí (chỉ vỏ, không ảnh).

Cách làm: render từng frame lớp bong bóng (RGBA trong suốt) rồi PIPE thẳng cho
ffmpeg overlay lên video gốc trong 1 lượt, GIỮ nguyên âm thanh gốc (không tạo
file overlay trung gian).

Hai chế độ (đặt RENDER_MODE):
    "transparent"  → xuất MOV nền RỖNG (kênh alpha) để TỰ ghép lên video khác  ← mặc định
    "burn"         → ghép bong bóng thẳng lên video INPUT, xuất .mp4 (giữ tiếng gốc)

Cách dùng:
    python bubble_video.py                   # theo RENDER_MODE: -> OUTPUT_MOV (hoặc OUTPUT)
    python bubble_video.py ref.mp4 out.mov   # transparent: ref.mp4 chỉ để lấy kích thước/fps
    python bubble_video.py in.mp4 out.mp4    # burn: ghép thẳng lên in.mp4

Thư viện: numpy, Pillow (vẽ nốt nhạc), ffmpeg/ffprobe.
"""

import sys
import random
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


# ════════════════════════════════════════════════════════════════════════════
#  THAM SỐ — chỉnh tại đây
# ════════════════════════════════════════════════════════════════════════════
_HERE = Path(__file__).resolve().parent

INPUT  = "D:/Python/omnivoice/OmniVoice/myvoice/videongang/一起来邂逅宫崎骏的夏天_哔哩哔哩_bilibili.mp4"
OUTPUT = "D:/Python/omnivoice/OmniVoice/myvoice/scripts/bubbles_output.mp4"          # chế độ "burn"
OUTPUT_MOV = "D:/Python/omnivoice/OmniVoice/myvoice/scripts/bubbles_overlay.mov"     # chế độ "transparent"

# — CHẾ ĐỘ RENDER —
#   "transparent" = xuất MOV nền RỖNG (kênh alpha) để bạn TỰ ghép lên video khác  ← QUAN TRỌNG
#   "burn"        = ghép bong bóng THẲNG lên video INPUT, xuất .mp4 (giữ tiếng gốc)
RENDER_MODE      = "transparent"
# Kích thước/fps cho MOV nền rỗng khi KHÔNG có video tham chiếu (nếu có thì lấy theo video)
OUTPUT_WIDTH     = 1920
OUTPUT_HEIGHT    = 1080
OUTPUT_FPS       = 30.0

# — Render theo từng clip: TRỐNG → ĐẦY → TAN —
CLIP_SECONDS     = 30.0      # độ dài video kết quả (giây); None = lấy trọn độ dài video gốc
SPAWN_RATE       = 2.2       # số bong bóng sinh ra mỗi giây (đầu clip trống, sinh dần cho đầy)
MAX_BUBBLES      = 16        # số bong bóng tối đa hiện cùng lúc (mật độ; nhỏ = thưa)
FADE_OUT_SEC     = 3.0       # vài giây CUỐI clip: cả lớp bong bóng mờ tan dần

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

# — Vỏ ngoài bong bóng: ẢNH có sẵn (thay cho việc tự vẽ vành/viền/đốm sáng) —
SHELL_IMAGE      = str(_HERE / "anhla" / "vongoai.png")  # ảnh vỏ bong bóng (RGBA, nền trong)
SHELL_OPACITY    = 1.0       # độ đục của vỏ (1 = như ảnh gốc; <1 = nhìn xuyên thấy video sau)
SPEC_THRESH      = 200.0     # ngưỡng sáng coi là "phản xạ" của vỏ (0..255)
SPEC_STRENGTH    = 0.85      # độ đậm khi "screen" phản xạ của vỏ ĐÈ lại lên ảnh bên trong
NOTE_ALPHA       = 0.80      # độ đậm của nốt nhạc (chỉ dùng khi KHÔNG có ảnh)

# — Ảnh bên trong bong bóng (thay cho nốt nhạc) —
IMAGE_DIR        = str(_HERE.parent / "Anh")   # thư mục ảnh; rỗng/không ảnh → quay lại nốt nhạc
IMAGE_EXTS       = {".png", ".jpg", ".jpeg", ".webp"}
INNER_FRAC       = 0.92      # đường kính ảnh (bo tròn) so với đường kính bong bóng — SÁT VIỀN hơn
INNER_FEATHER    = 0.07      # dải MỜ NGẮN ở vòng ngoài: ảnh mở/tan dần vào vỏ (chuẩn hoá; nhỏ = mờ ít)
INNER_OPACITY    = 0.97      # độ rõ của ảnh (cao = chân thật, ít bị vỏ phủ lên)

# — Bong bóng "ngôi sao": LUÔN có 1 bóng TO NHẤT mang ảnh này trên màn hình —
FEATURE_IMAGE_NAME = "Pink.png"  # tên ảnh trong Anh/ dùng cho bong bóng to nhất (luôn hiện)
FEATURE_IN_RANDOM  = False       # True = ảnh này còn được dùng ngẫu nhiên ở các bóng khác
FEATURE_OVERLAP    = 0.70        # nhịp sinh bóng feature = OVERLAP × đời sống (nhỏ → luôn ≥1 bóng hiện)

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


# ── Nạp ẢNH vỏ bong bóng 1 lần: cắt theo viền alpha rồi đệm về VUÔNG (giữ tâm) ──
#   Bong bóng trong ảnh thường không phủ kín khung; cắt đúng phần bong bóng rồi
#   đệm về ô vuông để khi thu/phóng về d×d không bị méo và vẫn nằm GIỮA sprite.
def _load_shell_base() -> np.ndarray:
    """Trả ảnh vỏ RGBA uint8 hình VUÔNG, bong bóng nằm giữa, ngoài viền trong suốt."""
    im = Image.open(SHELL_IMAGE).convert("RGBA")
    arr = np.asarray(im)
    alpha = arr[..., 3]
    ys, xs = np.where(alpha > 8)
    if len(xs) == 0:
        return arr.copy()
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    crop = arr[y0:y1, x0:x1]
    h, w = crop.shape[:2]
    s = max(h, w)
    sq = np.zeros((s, s, 4), dtype=np.uint8)
    oy, ox = (s - h) // 2, (s - w) // 2
    sq[oy:oy + h, ox:ox + w] = crop
    return sq

_SHELL_BASE = _load_shell_base()   # ảnh vỏ vuông, tính sẵn 1 lần


def _load_image_paths():
    p = Path(IMAGE_DIR)
    if not p.exists():
        return []
    return sorted(q for q in p.iterdir() if q.suffix.lower() in IMAGE_EXTS)

IMAGES = _load_image_paths()   # danh sách ảnh để bỏ vào bong bóng (rỗng → dùng nốt nhạc)

# Chỉ số ảnh "ngôi sao" (Pink.png) và nhóm ảnh cho bong bóng ngẫu nhiên
FEATURE_INDEX = next(
    (i for i, p in enumerate(IMAGES) if p.name.lower() == FEATURE_IMAGE_NAME.lower()),
    None,
)
RANDOM_IMAGE_INDICES = [
    i for i in range(len(IMAGES))
    if FEATURE_IN_RANDOM or i != FEATURE_INDEX                  # loại ảnh feature khỏi nhóm ngẫu nhiên
]


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
def _circular_mask(d: int, frac: float, feather: float = INNER_FEATHER) -> np.ndarray:
    """Mặt nạ tròn mềm: =1 trong bán kính 'frac' (chuẩn hoá), MỞ DẦN về 0 trong dải
    'feather' (đoạn mờ NGẮN sát mép) để ảnh tan mềm vào vỏ bong bóng."""
    R = d / 2.0
    yy, xx = np.mgrid[0:d, 0:d].astype(np.float32)
    c = (d - 1) / 2.0
    rn = np.sqrt(((xx - c) / R) ** 2 + ((yy - c) / R) ** 2)
    return (1.0 - _smoothstep(frac - feather, frac, rn)).astype(np.float32)


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


# ── Vỏ bong bóng theo đường kính d: thu/phóng ảnh vỏ về d×d (cache theo d) ──
_SHELL_CACHE: dict = {}

def _get_shell(d: int):
    """Trả (rgb d×d×3 float 0..255, alpha d×d float 0..1) của ẢNH vỏ ở cỡ d."""
    s = _SHELL_CACHE.get(d)
    if s is None:
        im = Image.fromarray(_SHELL_BASE).resize((d, d), Image.LANCZOS)
        a = np.asarray(im, dtype=np.float32)
        s = (a[..., :3].copy(), (a[..., 3] / 255.0).copy())
        _SHELL_CACHE[d] = s
    return s


# ── Dựng "sprite" một bong bóng = VỎ (ảnh) + ẢNH bên trong (cache theo (d, nội dung)) ──
#   Không tự vẽ vành/viền/đốm sáng nữa; vỏ lấy thẳng từ ảnh. Thêm mặt nạ "phản xạ"
#   (chỗ vỏ sáng gần trắng) để screen ĐÈ lại lên ảnh cho giống nằm sau lớp kính.
def _build_sprite(d: int, inner_key):
    shell_rgb, shell_a = _get_shell(d)
    lum = shell_rgb @ np.array([0.299, 0.587, 0.114], dtype=np.float32)   # độ sáng vỏ
    spec = (np.clip((lum - SPEC_THRESH) / (255.0 - SPEC_THRESH), 0.0, 1.0)
            * shell_a).astype(np.float32)                                # phản xạ (chỉ trong vỏ)
    inner_rgb, inner_a = _build_inner(d, inner_key)                       # ảnh/nốt nhạc giữa vỏ
    return shell_rgb, shell_a, spec, inner_rgb, inner_a


_SPRITE_CACHE: dict = {}

def _get_sprite(d: int, inner_key):
    spr = _SPRITE_CACHE.get((d, inner_key))
    if spr is None:
        spr = _build_sprite(d, inner_key)
        _SPRITE_CACHE[(d, inner_key)] = spr
    return spr


class Bubble:
    __slots__ = ("d", "inner_key", "x0", "y0", "speed", "vx",
                 "t_spawn", "t_despawn", "sprite")


def _make_bubble(rng: random.Random, W: int, H: int, t_spawn: float) -> Bubble:
    b = Bubble()
    if rng.random() < TINY_FRAC:
        b.d = int(rng.uniform(TINY_MIN, TINY_MAX))
        b.inner_key = ("none", 0)                               # bé tý → bong bóng trơn
    else:
        b.d = int(rng.uniform(SIZE_MIN, SIZE_MAX))
        if RANDOM_IMAGE_INDICES:
            b.inner_key = ("img", rng.choice(RANDOM_IMAGE_INDICES))  # ảnh ngẫu nhiên (trừ Pink.png)
        else:
            b.inner_key = ("note", rng.choice((1, 2, 3)))       # không có ảnh → nốt nhạc
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


def _make_feature_bubble(rng: random.Random, W: int, H: int, t_spawn: float) -> Bubble:
    """Bong bóng 'ngôi sao': cỡ TO NHẤT (SIZE_MAX), mang ảnh Pink.png, bay chậm."""
    b = Bubble()
    b.d = SIZE_MAX                                             # luôn ở mức to nhất
    b.inner_key = ("img", FEATURE_INDEX)
    r = b.d / 2.0
    b.speed = SLOW_SPEED                                       # bay chậm để nổi bật, ở lâu trên màn hình
    b.vx = b.speed * DRIFT_RATIO
    b.x0 = rng.uniform(-H * DRIFT_RATIO, W)
    b.y0 = H + r
    b.t_spawn = t_spawn
    b.t_despawn = t_spawn + (H + 2.0 * r) / b.speed
    b.sprite = _get_sprite(b.d, b.inner_key)
    return b


def _build_schedule(W: int, H: int, duration: float):
    """Lịch sinh bong bóng: đầu clip TRỐNG, sinh dần từ đáy cho đầy; ngừng sinh gần cuối.

    Riêng bong bóng 'ngôi sao' (Pink.png, cỡ to nhất) được sinh NỐI TIẾP nhau để
    LÚC NÀO trên màn hình cũng có ít nhất 1 bóng này.
    """
    rng = random.Random(SEED)
    bubbles, intervals = [], []
    stop_spawn = max(0.0, duration - FADE_OUT_SEC)             # ngừng sinh khi bắt đầu mờ tan

    # 1) Luồng bóng "ngôi sao" — luôn có ≥1 bóng to nhất mang Pink.png trên màn hình
    if FEATURE_INDEX is not None:
        life = (H + 2.0 * (SIZE_MAX / 2.0)) / SLOW_SPEED       # đời sống 1 bóng feature (giây)
        period = max(0.5, life * FEATURE_OVERLAP)              # nhịp sinh < đời sống → cửa sổ hiện chồng nhau
        tf = -life * 0.5                                       # bắt đầu trước t=0 để màn hình không trống
        while tf < stop_spawn:
            fb = _make_feature_bubble(rng, W, H, tf)
            bubbles.append(fb)
            intervals.append((fb.t_spawn, fb.t_despawn))
            tf += period

    # 2) Luồng bóng ngẫu nhiên — tôn trọng MAX_BUBBLES (đã tính cả bóng feature)
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
                    fade: float, W: int, H: int):
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

    shell_rgb, shell_a, spec, inner_rgb, inner_a = b.sprite

    rgb = shell_rgb[sy0:sy1, sx0:sx1].copy()                     # VỎ bong bóng (ảnh)

    ia = (inner_a[sy0:sy1, sx0:sx1] * INNER_OPACITY)[..., None]
    rgb = rgb * (1.0 - ia) + inner_rgb[sy0:sy1, sx0:sx1] * ia    # ẢNH đặt vào giữa vỏ

    sp = (spec[sy0:sy1, sx0:sx1] * SPEC_STRENGTH)[..., None]
    rgb = rgb + (255.0 - rgb) * sp                              # phản xạ của vỏ ĐÈ lại (screen)

    # Độ đục: lấy thẳng theo alpha của ẢNH vỏ (SHELL_OPACITY để nhìn xuyên nếu muốn)
    a = shell_a[sy0:sy1, sx0:sx1] * (SHELL_OPACITY * fade)

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
        _composite_over(layer, b, x, y, fade, W, H)
    return layer


# ════════════════════════════════════════════════════════════════════════════
#  RENDER MOV NỀN RỖNG (kênh alpha) — để GHÉP lên video khác sau này
#  qtrle/argb = lossless, giữ trong suốt. CPU-only (NVENC không hỗ trợ alpha).
# ════════════════════════════════════════════════════════════════════════════
def _transparent_render_spec(ref_path: Path):
    """Khung/fps/độ dài cho MOV nền rỗng: lấy theo video tham chiếu nếu có, không thì dùng mặc định."""
    W, H, fps = OUTPUT_WIDTH, OUTPUT_HEIGHT, OUTPUT_FPS
    if ref_path.exists():
        W, H = _probe_size(ref_path)
        fps = _probe_fps(ref_path)
        if CLIP_SECONDS is None:
            return W, H, fps, _probe_duration(ref_path)
    return W, H, fps, float(CLIP_SECONDS or 30.0)


def render_transparent_mov(out_path: Path, ref_path: Path):
    W, H, fps, duration = _transparent_render_spec(ref_path)
    n_frames = int(round(duration * fps))
    bubbles = _build_schedule(W, H, duration)
    print(f"Khung {W}x{H}  fps={fps:.3f}  dài={duration:.2f}s  — {len(bubbles)} bong bóng")

    cmd = [
        FFMPEG, "-y",
        "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-r", f"{fps}", "-i", "-",
        "-an",
        "-c:v", "qtrle", "-pix_fmt", "argb",              # codec giữ ALPHA (nền trong suốt)
        str(out_path),
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
        print("[LỖI] ffmpeg render MOV nền rỗng thất bại.", file=sys.stderr)
        sys.exit(1)


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


def _unique_path(path: Path) -> Path:
    """Trả về đường dẫn CHƯA tồn tại: nếu trùng thì thêm _2, _3, ... để KHÔNG đè bản cũ."""
    if not path.exists():
        return path
    n = 2
    while True:
        cand = path.with_name(f"{path.stem}_{n}{path.suffix}")
        if not cand.exists():
            return cand
        n += 1


def main():
    args = sys.argv[1:]
    ref_path = Path(args[0]) if len(args) >= 1 else Path(INPUT)

    if RENDER_MODE == "transparent":
        # MOV nền RỖNG để ghép lên video khác — video tham chiếu (nếu có) chỉ để lấy kích thước/fps
        out_path = Path(args[1]) if len(args) >= 2 else Path(OUTPUT_MOV)
        if out_path.suffix.lower() != ".mov":
            out_path = out_path.with_suffix(".mov")
        out_path = _unique_path(out_path)                 # không đè bản cũ → tạo bản mới
        print(f"Render MOV NỀN RỖNG (để ghép video khác): {out_path.name}  (trống → đầy → tan)")
        render_transparent_mov(out_path, ref_path)
        print(f"Hoàn tất → {out_path}")
    else:  # "burn"
        out_path = Path(args[1]) if len(args) >= 2 else Path(OUTPUT)
        if not ref_path.exists():
            print(f"[LỖI] Không tìm thấy video đầu vào: {ref_path}")
            sys.exit(1)
        out_path = _unique_path(out_path)                 # không đè bản cũ → tạo bản mới
        print(f"Render bong bóng lên: {ref_path.name}  (trống → đầy → tan, giữ âm thanh gốc)")
        render_onto_video(ref_path, out_path)
        print(f"Hoàn tất → {out_path}")


if __name__ == "__main__":
    main()
