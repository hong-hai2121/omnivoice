# -*- coding: utf-8 -*-
"""Dựng danh sách bước (Step) cho hàng đợi web myvideo.

Quy trình 4 bước, mỗi bước là một script CLI có sẵn trong myvideo/ — web chỉ
xếp lệnh vào hàng đợi, không import logic nặng nào:
  ① video_chamlai_srt.py  chậm video + SRT tiếng gốc (luôn kèm --no-dich: dịch là bước ②)
  ② dich_srt.py           SRT gốc → SRT Việt qua Gemini (Firefox phải ĐÓNG)
  ③ taogiong_srt.py       giọng OmniVoice từng câu + xếp timeline chống đè
  ④ video_gansub_cung.py  vẽ sub cứng + (tuỳ chọn) thay tiếng bằng audio đã xếp
                          — cả vẽ sub, che mờ lẫn thay tiếng đều bỏ được

Mọi đường dẫn suy ra từ MỘT gốc <output>/<tên>_x<tốc độ> (đúng quy ước đặt tên
của các script), nên xếp bước ②③④ vào hàng đợi TRƯỚC khi bước ① chạy xong
vẫn trỏ đúng file.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from .jobs import Step

BASE_DIR = Path(__file__).resolve().parent.parent       # myvideo/
REPO_ROOT = BASE_DIR.parent
OUTPUT_DIR = BASE_DIR / "output"
VENV_PY = REPO_ROOT / "venv" / "Scripts" / "python.exe"
# Kho giọng RIÊNG của myvideo (myvideo/voice) — độc lập hẳn với myvoice, chỉ
# mượn ý tưởng chức năng; không đọc kho file hay cài đặt bên đó.
VOICE_DIR = BASE_DIR / "voice"
# Kho NHẠC NỀN: bỏ file mp3/wav vào đây là ô chọn ở khối ④ thấy ngay.
NHAC_DIR = BASE_DIR / "nhac"
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".flac", ".ogg"}

# Hồ sơ kênh (logo.png / outro.mp4 nằm trong thư mục hồ sơ) — kenh_hoso đứng
# một mình, không kéo FastAPI hay GUI nào theo.
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
import kenh_hoso  # noqa: E402

ORDER = ["cham", "dich", "giong", "gan"]
NUM = {"cham": "①", "dich": "②", "giong": "③", "gan": "④"}
# Tiếng GỐC của video (ô chọn trên trang) — quyết định Whisper nhận diện tiếng gì
# ở bước ① và số chữ/dòng SRT. Bước ② KHÔNG cần biết: dich_srt.py tự đoán từ
# chính file SRT nó đọc — chạy lẻ bước ② cho video cũ vẫn đúng tiếng của nó.
TEN_LANG = {"zh": "Trung", "en": "Anh"}
LABELS = {
    "cham": "① Chậm video + SRT tiếng gốc",
    "dich": "② Dịch Gemini → SRT tiếng Việt",
    "giong": "③ Giọng OmniVoice + xếp timeline",
    "gan": "④ Vẽ sub cứng + thay tiếng",
}

_XTAG = re.compile(r"_x\d+(?:\.\d+)?")


def _python() -> str:
    return str(VENV_PY) if VENV_PY.exists() else sys.executable


def _env() -> dict:
    return {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}


def list_voices() -> list[str]:
    """Giọng mẫu trong kho riêng myvideo/voice — cho ô chọn của bước ③."""
    try:
        return sorted((p.name for p in VOICE_DIR.iterdir()
                       if p.is_file() and p.suffix.lower() in AUDIO_EXTS),
                      key=str.lower)
    except OSError:
        return []


def list_nhac() -> list[str]:
    """File nhạc nền trong myvideo/nhac — cho ô chọn 🎵 của bước ④."""
    try:
        return sorted((p.name for p in NHAC_DIR.iterdir()
                       if p.is_file() and p.suffix.lower() in AUDIO_EXTS),
                      key=str.lower)
    except OSError:
        return []


def tenchinh(name: str) -> str:
    """Tên video GỐC từ một tên bất kỳ: cắt tag _x… và mọi thứ sau nó, hạ chữ.

    "abc_x0.7", "abc_x0.7_vi_audio", "abc" → "abc". Dùng để nhận ra một video
    đã chạy tới đâu dù đang cầm file nguồn hay file kết quả, ở tốc độ nào."""
    tags = list(_XTAG.finditer(name))
    return (name[:tags[-1].start()] if tags else name).lower()


def la_video_cham(name: str) -> bool:
    """Tên (không đuôi) kết thúc ĐÚNG bằng tag _x… → video ra lò từ bước ①.

    Chặt hơn is_base: "abc_x0.7" đúng, còn "abc_x0.7_sub" (video thành phẩm
    của bước ④) thì không — dán cái đó vào ô Nguồn là chạy nhầm."""
    tags = list(_XTAG.finditer(name))
    return bool(tags) and tags[-1].end() == len(name)


def base_for(src: str, speed) -> Path:
    """Nguồn (file gốc HOẶC một file kết quả có _x…) → gốc tên trong output.

    MỖI VIDEO MỘT THƯ MỤC (như myvoice): video mới ra output/<tên>/<tên>_x0.7.*
    Kết quả CŨ dạng phẳng (file nằm thẳng trong output/) vẫn nhận ra được.
    Cắt theo tag _x… trên p.name (xem chú thích ở scan_rows về bẫy p.stem)."""
    name = Path(src).name
    tags = list(_XTAG.finditer(name))
    if not tags:                       # video gốc mới → thư mục riêng theo tên
        stem = Path(src).stem
        return OUTPUT_DIR / stem / f"{stem}_x{float(speed):g}"
    b = name[:tags[-1].end()]
    folder = name[:tags[-1].start()]
    # Dán ĐƯỜNG DẪN một file kết quả: giữ đúng thư mục file đó đang nằm.
    try:
        parent = Path(src).resolve().parent
        out = OUTPUT_DIR.resolve()
        if parent.parent == out:
            return OUTPUT_DIR / parent.name / b
        if parent == out:
            return OUTPUT_DIR / b      # kết quả cũ dạng phẳng
    except OSError:
        pass
    # Chỉ gõ tên trần: ưu tiên thư mục con, không có thì coi là dạng phẳng cũ.
    if (OUTPUT_DIR / folder).is_dir():
        return OUTPUT_DIR / folder / b
    return OUTPUT_DIR / b


# ── Trạng thái từng video trong output ───────────────────────────────────────
def _flags(base: str) -> dict:
    B = str(OUTPUT_DIR / base)
    return {
        "base": base,
        "video": os.path.isfile(f"{B}.mp4"),
        "srt": os.path.isfile(f"{B}.srt"),
        "vi": os.path.isfile(f"{B}_vi.srt"),
        # Bước ③ ra một CẶP (audio tổng + SRT đã xếp) — thiếu một nửa coi như chưa xong.
        "audio": os.path.isfile(f"{B}_vi_audio.wav")
                 and os.path.isfile(f"{B}_vi_sapxep.srt"),
        "sub": os.path.isfile(f"{B}_sub.mp4"),
        # có timeline.json → bảng hiện nút 🎞 xem trang xếp audio kiểu CapCut
        "tl": os.path.isfile(f"{B}_vi_timeline.json"),
        # Khâu SAU DỰNG: SEO · thumbnail · biên nhận đã đăng YouTube/Facebook.
        "seo": os.path.isfile(f"{B}_seo.json"),
        "thumb": os.path.isfile(f"{B}_thumb.jpg") or os.path.isfile(f"{B}_thumb.png"),
        "yt": os.path.isfile(f"{B}_youtube_upload.json"),
        "fb": os.path.isfile(f"{B}_facebook_upload.json"),
    }


def missing_steps(r: dict, thaytieng: bool, vesub: bool = True) -> tuple[list[str], str]:
    """→ (các bước còn thiếu theo thứ tự chạy, lý do nếu KHÔNG chạy tiếp được)."""
    miss = []
    if not r["vi"]:
        miss.append("dich")
    if thaytieng and not r["audio"]:
        miss.append("giong")
    if not r["sub"]:
        miss.append("gan")
    if not miss:
        return [], ""
    # Bước đầu chuỗi phải có sẵn đầu vào; các bước sau do bước trước sinh ra.
    if miss[0] == "dich" and not r["srt"]:
        return [], "thiếu SRT tiếng gốc — chạy lại bước ① từ file nguồn"
    if "gan" in miss and not r["video"]:
        miss.remove("gan")
        if not miss:
            return [], "thiếu video _x….mp4 — chạy lại bước ① từ file nguồn"
    if "gan" in miss and not (vesub or thaytieng):
        miss.remove("gan")
        if not miss:
            return [], "đã bỏ cả vẽ sub lẫn thay tiếng — bước ④ không còn việc gì"
    return miss, ""


def _mtime(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except OSError:
        return 0.0


def scan_rows(thaytieng: bool = True, limit: int = 25,
              vesub: bool = True) -> list[dict]:
    """Mỗi gốc _x… trong output → một hàng: bước nào đã xong, còn thiếu gì.

    Gốc là ĐƯỜNG DẪN TƯƠNG ĐỐI so với output: video mới nằm thư mục riêng
    ("<tên>/<tên>_x0.7"), kết quả cũ dạng phẳng vẫn ra hàng ("<tên>_x0.7").
    """
    seen: dict[str, float] = {}

    def note(b: str, mt: float) -> None:
        seen[b] = max(seen.get(b, 0.0), mt)

    try:
        entries = list(OUTPUT_DIR.iterdir())
    except OSError:
        return []
    for p in entries:
        # Lấy gốc từ p.name chứ KHÔNG phải p.stem: thư mục "…_x0.7_vi_tts" bị
        # stem coi ".7_vi_tts" là đuôi file → cụt còn "…_x0", sinh gốc ma.
        # Cắt theo vị trí tag _x… thì có đuôi hay không cũng ra đúng gốc.
        tags = list(_XTAG.finditer(p.name))
        if tags:                                   # kết quả cũ dạng phẳng
            note(p.name[:tags[-1].end()], _mtime(p))
        elif p.is_dir():                           # thư mục riêng của một video
            try:
                subs = list(p.iterdir())
            except OSError:
                continue
            for c in subs:
                t2 = list(_XTAG.finditer(c.name))
                if t2:
                    note(f"{p.name}/{c.name[:t2[-1].end()]}", _mtime(c))

    rows = []
    for b, _mt in sorted(seen.items(), key=lambda kv: kv[1], reverse=True)[:limit]:
        r = _flags(b)
        r["missing"], r["resume_err"] = missing_steps(r, thaytieng, vesub)
        r["missing_label"] = "".join(NUM[k] for k in r["missing"])
        rows.append(r)
    return rows


# ── Dựng Step cho hàng đợi ───────────────────────────────────────────────────
# server.py gắn hàm vào đây lúc khởi động: dựng xong bước ④ của một video thì
# gọi hook(base_tương_đối) để xếp việc TỰ ĐĂNG (nếu bật và đã có kênh). Đặt là
# biến module thay vì import server — steps không được kéo FastAPI vào.
after_build_hook = None


def _base_rel(base: Path) -> str:
    try:
        return base.relative_to(OUTPUT_DIR).as_posix()
    except ValueError:
        return base.as_posix()


def _steps_for(keys: list[str], src: str, base: Path, s: dict) -> list[Step]:
    B = str(base)
    env = _env()
    steps = []
    for k in keys:
        label = LABELS[k]
        if k == "cham":
            lang = s.get("lang") or "zh"
            ten = TEN_LANG.get(lang, "Trung")
            label = f"① Chậm video + SRT tiếng {ten}"
            # Mỗi tiếng một ngưỡng dài dòng riêng (16 chữ Hán · 42 ký tự Anh) nên
            # trang lưu hai số khác nhau, đổi ô ngôn ngữ không làm mất số của tiếng kia.
            n = str(s.get("maxchars_en") or "42") if lang == "en" else str(s["maxchars"])
            # --out-dir là THƯ MỤC RIÊNG của video (base.parent) — script tự tạo.
            argv = [_python(), "-u", str(BASE_DIR / "video_chamlai_srt.py"), src,
                    "--speed", str(s["speed"]), "--model", s["model"],
                    "--max-chars", n, "--hard-max", n, "--no-dich",
                    "--lang", lang, "--out-dir", str(base.parent)]
            if not s.get("ngucanh", True):
                argv.append("--khong-ngu-canh")
            if s.get("redoasr"):
                argv.append("--redo-asr")
        elif k == "dich":
            argv = [_python(), "-u", str(BASE_DIR / "dich_srt.py"), f"{B}.srt",
                    "--batch-chars", str(s.get("batchchars", "1200"))]
            if not s.get("gopcau", True):
                argv.append("--giu-dong")
            if s.get("offline"):
                argv.append("--offline")
                label = "② Dịch offline opus-mt (nháp)"
        elif k == "giong":
            argv = [_python(), "-u", str(BASE_DIR / "taogiong_srt.py"), f"{B}_vi.srt"]
            if s.get("voice"):
                argv += ["--voice", s["voice"]]
            if s.get("redotts"):
                argv.append("--redo-tts")
        else:                                   # gan
            # Ba việc của bước ④ bỏ được từng cái: vẽ sub · che mờ sub gốc ·
            # thay tiếng. Bỏ cả vẽ sub lẫn che mờ thì script giữ nguyên hình
            # (-c:v copy), chỉ ghép lại tiếng.
            ve_sub = bool(s.get("vesub", True))
            thay = bool(s.get("thaytieng", True))
            argv = [_python(), "-u", str(BASE_DIR / "video_gansub_cung.py"), f"{B}.mp4",
                    "--max-chars", str(s.get("subchars", "50")),
                    "--dong", str(s.get("subdong") or "2"),
                    "--kieu", s.get("kieusub") or "hopbo"]
            # Font · màu chữ · màu viền · cỡ chữ · vị trí: chỉ gửi ô nào có
            # đặt — bỏ trống là giữ đúng của kiểu (và vị trí tự đặt theo dải che).
            for co, ten in (("subfont", "--font"), ("submau", "--mau"),
                            ("submauvien", "--mau-vien"), ("subcochu", "--cochu"),
                            ("subvitri", "--vitri")):
                if s.get(co):
                    argv += [ten, str(s[co])]
            # Phóng to video nền: 0/rỗng = giữ nguyên, khỏi gửi cờ.
            if str(s.get("zoom") or "").strip() not in ("", "0"):
                argv += ["--zoom", str(s["zoom"])]
            # 🎵 Nhạc nền nhỏ dưới tiếng chính — chọn ở khối ④, mặc định tắt.
            if s.get("nhacnen"):
                nf = NHAC_DIR / s["nhacnen"]
                if nf.is_file():
                    argv += ["--nhac", str(nf),
                             "--nhac-db", str(s.get("nhacnen_db") or "-18")]
            # 🏷 Logo / outro theo HỒ SƠ KÊNH đang chọn — chỉ gửi khi ô bật VÀ
            # file có thật trong myvideo/kenh/<tên>/ (thiếu file thì thôi, không
            # làm hỏng lượt dựng; script cũng tự bỏ qua nếu file biến mất sau).
            if s.get("logo_kenh") or s.get("outro_kenh"):
                kenh = kenh_hoso.hien_tai()
                if kenh:
                    lg = kenh_hoso.thu_muc(kenh) / "logo.png"
                    ot = kenh_hoso.thu_muc(kenh) / "outro.mp4"
                    if s.get("logo_kenh") and lg.is_file():
                        argv += ["--logo", str(lg)]
                    if s.get("outro_kenh") and ot.is_file():
                        argv += ["--outro", str(ot)]
            if s.get("chesub", True):
                argv.append("--che-sub-goc")
            if thay:
                argv += ["--audio", f"{B}_vi_audio.wav"]
            if ve_sub:
                # Thay tiếng thì vẽ bản ĐÃ XẾP (khớp giọng đọc), giữ tiếng gốc
                # thì vẽ bản _vi.srt (khớp mốc giờ gốc).
                argv += ["--srt", f"{B}_vi_sapxep.srt" if thay else f"{B}_vi.srt"]
            label = ("④ Vẽ sub cứng + thay tiếng" if (ve_sub and thay) else
                     "④ Vẽ sub cứng (giữ tiếng gốc)" if ve_sub else
                     "④ Thay tiếng, không vẽ sub" if thay else
                     "④ Chỉ che mờ sub gốc")
            if s.get("cpu"):
                argv.append("--cpu")
        extra = {}
        if k == "gan" and after_build_hook is not None:
            # Xong bước ④ = video thành phẩm → cho server cơ hội xếp việc tự
            # đăng. Hook tự kiểm ô bật/tắt + kênh đã có chưa, ở đây chỉ báo.
            extra["on_success"] = (lambda rb=_base_rel(base): after_build_hook(rb))
        steps.append(Step(label=label, argv=argv, cwd=str(REPO_ROOT), env=env, **extra))
        if k == "gan" and s.get("xuatdoc"):
            # 📱 Bản DỌC 9:16 kèm theo — cùng bộ tuỳ chọn, chỉ thêm --khung doc
            # (script tự đặt tên <B>_doc.mp4 và soạn chữ theo khung 1080×1920).
            steps.append(Step(label="④ 📱 Bản dọc 9:16 (TikTok/Shorts)",
                              argv=argv + ["--khung", "doc"],
                              cwd=str(REPO_ROOT), env=env))
    return steps


def chain_keys(start: str, s: dict) -> list[str]:
    """Bấm nút bước nào thì chạy từ bước đó; các ô ⛓ quyết định nối tiếp bao xa."""
    keys = [start]
    nxt = {"cham": "auto2", "dich": "auto3", "giong": "auto4"}
    k = start
    while k in nxt and s.get(nxt[k]):
        k = ORDER[ORDER.index(k) + 1]
        keys.append(k)
    return keys


def _check_input(start: str, B: str, s: dict) -> str:
    """Đầu vào của BƯỚC ĐẦU chuỗi phải có sẵn (các bước sau do chuỗi sinh ra)."""
    name = Path(B).name
    if start == "dich" and not os.path.isfile(f"{B}.srt"):
        return f"Chưa có {name}.srt — chạy bước ① trước."
    if start == "giong" and not os.path.isfile(f"{B}_vi.srt"):
        return f"Chưa có {name}_vi.srt — chạy bước ② trước."
    if start == "gan":
        if not os.path.isfile(f"{B}.mp4"):
            return f"Chưa có {name}.mp4 — chạy bước ① trước."
        ve_sub, thay = bool(s.get("vesub", True)), bool(s.get("thaytieng", True))
        if not ve_sub and not thay:
            return ("Bước ④ không còn việc gì: đã bỏ cả vẽ sub lẫn thay tiếng "
                    "(tick lại một trong hai).")
        if thay:
            # Không vẽ sub thì chỉ cần file audio, khỏi đòi bản SRT đã xếp.
            can = [f"{B}_vi_audio.wav"] + ([f"{B}_vi_sapxep.srt"] if ve_sub else [])
            for f in can:
                if not os.path.isfile(f):
                    return f"Chưa có {Path(f).name} — chạy bước ③ trước (hoặc bỏ tick thay tiếng)."
        elif not os.path.isfile(f"{B}_vi.srt"):
            return f"Chưa có {name}_vi.srt — chạy bước ② trước."
    return ""


def build(start: str, src: str, s: dict) -> tuple[str, list[Step], str]:
    """Từ form chính: → (tiêu đề việc, các bước, lỗi — khác rỗng là chưa chạy được)."""
    src = (src or "").strip().strip('"')
    if start == "thu60":
        # 🧪 BẢN NHÁP: cắt 60 giây rồi chạy TRỌN 4 bước (bỏ qua các ô ⛓) —
        # duyệt giọng/kiểu sub/vùng che trước khi tốn nửa tiếng cho cả bài.
        # Ô "từ phút thứ…" dời khúc cắt vào giữa bài: 60s ĐẦU thường là intro
        # nhạc hiệu, không đại diện cho giọng đọc lẫn vùng sub của cả video.
        if not src or not os.path.isfile(src):
            return "", [], f"Không thấy file nguồn: {src or '(trống)'}"
        try:
            tu_phut = max(0.0, float(str(s.get("thu60_tu") or "0").replace(",", ".")))
        except ValueError:
            tu_phut = 0.0
        clip = OUTPUT_DIR / f"{Path(src).stem}_thu60.mp4"
        base = base_for(str(clip), s["speed"])
        # -ss TRƯỚC -i + -c copy: nhảy theo keyframe, cắt tức thì — bản nháp
        # lệch vài giây quanh mốc không sao.
        seek = ["-ss", f"{tu_phut * 60:g}"] if tu_phut > 0 else []
        nhan = f"✂ Cắt 60 giây từ phút {tu_phut:g}" if tu_phut > 0 else "✂ Cắt 60 giây đầu"
        cut = Step(label=nhan,
                   argv=["ffmpeg", "-y", "-loglevel", "error", *seek, "-t", "60",
                         "-i", src, "-c", "copy", str(clip)],
                   cwd=str(REPO_ROOT), env=_env())
        steps = [cut] + _steps_for(ORDER, str(clip), base, s)
        return f"{Path(src).name} — 🧪 thử 60s ①②③④", steps, ""
    if start == "tatca":
        # ▶ CHẠY TẤT CẢ: từ bước ① tới bước ④ một mạch, BỎ QUA các ô ⛓ (chúng
        # chỉ điều khiển mấy nút "Chạy bước …" riêng lẻ ở từng khối). Một nút
        # cho cả quy trình — khỏi phải nhớ đã tick đủ ba ô ⛓ hay chưa.
        if not src or not os.path.isfile(src):
            return "", [], f"Không thấy file nguồn: {src or '(trống)'}"
        base = base_for(src, s["speed"])
        return (f"{base.name} — ▶ {''.join(NUM[k] for k in ORDER)}",
                _steps_for(ORDER, src, base, s), "")
    if start == "cham":
        if not src or not os.path.isfile(src):
            return "", [], f"Không thấy file nguồn: {src or '(trống)'}"
    elif not src:
        return "", [], ("Điền nguồn (file gốc hoặc tên _x… trong output) — "
                        "hoặc dùng nút ở bảng Kết quả bên dưới.")
    base = base_for(src, s["speed"])
    if start != "cham":
        err = _check_input(start, str(base), s)
        if err:
            return "", [], err
    keys = chain_keys(start, s)
    title = f"{base.name} — {''.join(NUM[k] for k in keys)}"
    return title, _steps_for(keys, src, base, s), ""


def resume(base: str, s: dict) -> tuple[str, list[Step], str]:
    """Nút ⏩ của bảng: chạy liền mạch các bước còn thiếu của một gốc."""
    r = _flags(base)
    miss, err = missing_steps(r, s.get("thaytieng", True))
    if err:
        return "", [], f"{base}: {err}."
    if not miss:
        return "", [], f"{base}: đủ cả rồi, không còn bước nào thiếu."
    title = f"{base} — ⏩ {''.join(NUM[k] for k in miss)}"
    return title, _steps_for(miss, "", OUTPUT_DIR / base, s), ""


def single(base: str, key: str, s: dict) -> tuple[str, list[Step], str]:
    """Nút ②③④ của bảng: chạy lại đúng MỘT bước cho một gốc."""
    if key not in ("dich", "giong", "gan"):
        return "", [], f"Bước không hợp lệ: {key}"
    err = _check_input(key, str(OUTPUT_DIR / base), s)
    if err:
        return "", [], err
    return f"{base} — {NUM[key]}", _steps_for([key], "", OUTPUT_DIR / base, s), ""


# ── Khâu SAU DỰNG: SEO · thumbnail · đăng YouTube · lên lịch Facebook ────────
# SEO đi HÀNG ĐỢI CHÍNH (dùng Firefox — chạy song song với bước ② là giẫm
# profile); thumbnail cũng hàng chính (ffmpeg). Đăng YouTube/Facebook đi hai
# hàng đợi riêng (jobs.q_dang / jobs.q_fb) vì chỉ tốn băng thông.
def seo_steps(bases: list[str], force: bool = False) -> tuple[str, list[Step]]:
    argv = [_python(), "-u", str(BASE_DIR / "seo_video.py")]
    for b in bases:
        argv += ["--base", b]
    if force:
        argv.append("--force")
    ten = Path(bases[0]).name if len(bases) == 1 else f"{len(bases)} video"
    return (f"📑 SEO — {ten}",
            [Step(label="📑 Sinh SEO (Gemini)", argv=argv,
                  cwd=str(REPO_ROOT), env=_env())])


def thumb_steps(bases: list[str], force: bool = False) -> tuple[str, list[Step]]:
    argv = [_python(), "-u", str(BASE_DIR / "thumbnail_video.py")]
    for b in bases:
        argv += ["--base", b]
    if force:
        argv.append("--force")
    ten = Path(bases[0]).name if len(bases) == 1 else f"{len(bases)} video"
    return (f"🖼 Thumbnail — {ten}",
            [Step(label="🖼 Vẽ thumbnail", argv=argv,
                  cwd=str(REPO_ROOT), env=_env())])


def youtube_steps(base: str, kenh: str) -> tuple[str, list[Step]]:
    """Một video một việc, đăng bằng HỒ SƠ KÊNH `kenh` — mã 77 (kênh này đã
    đăng rồi / hồ sơ chưa cấu hình) là bỏ qua có chủ ý, hàng đợi hiện
    "stopped" chứ không đỏ."""
    return (f"⬆ YouTube [{kenh}] — {Path(base).name}",
            [Step(label="⬆ Đăng YouTube", argv=[
                _python(), "-u", str(BASE_DIR / "dang_youtube.py"),
                "--base", base, "--kenh", kenh],
                cwd=str(REPO_ROOT), env=_env(), soft_fail_codes=(77,))])


def youtube_login_steps(kenh: str, doi_kenh: bool = False) -> tuple[str, list[Step]]:
    argv = [_python(), "-u", str(BASE_DIR / "dang_youtube.py"), "--dangnhap",
            "--kenh", kenh]
    if doi_kenh:
        argv.append("--doi-kenh")
    return (f"🔑 Đăng nhập YouTube [{kenh}]",
            [Step(label="🔑 Đăng nhập YouTube", argv=argv,
                  cwd=str(REPO_ROOT), env=_env(), soft_fail_codes=(77,))])


def facebook_steps(mode: str, kenh: str,
                   chon: list[str] | None = None) -> tuple[str, list[Step]]:
    """mode: 'chay' (đăng thật, --yes) · 'xemtruoc' (--dry-run) · 'quet' (--sync),
    trên Page của HỒ SƠ KÊNH `kenh`.

    Mã thoát 2 của script = tạm ngưng vì hạn mức/token — vẫn để đỏ cho dễ thấy,
    nhật ký nói rõ phải làm gì."""
    argv = [_python(), "-u", str(BASE_DIR / "FACEBOOK" / "dang_video_facebook.py"),
            "--kenh", kenh]
    if mode == "quet":
        argv.append("--sync")
        label = f"🔄 Cập nhật lịch Page [{kenh}]"
    elif mode == "xemtruoc":
        argv.append("--dry-run")
        label = f"🔍 Xem kế hoạch đăng Page [{kenh}]"
    else:
        argv.append("--yes")
        label = f"📘 Lên lịch đăng Page [{kenh}]"
    for b in chon or []:
        argv += ["--chon", b]
    return (label, [Step(label=label, argv=argv, cwd=str(REPO_ROOT), env=_env())])


# ── Xoá output: CHỈ đưa vào Thùng rác (mọi thao tác xoá phải khôi phục được) ──
def is_base(name: str) -> bool:
    """Gốc hợp lệ từ form: có tag _x…, tối đa MỘT cấp thư mục con, cấm ..

    Gốc giờ là đường dẫn tương đối trong output ("<thư mục>/<tên>_x0.7" hoặc
    dạng phẳng cũ "<tên>_x0.7")."""
    if not name or "\\" in name or ".." in name:
        return False
    parts = name.split("/")
    if len(parts) > 2 or any(not p.strip() for p in parts):
        return False
    return bool(_XTAG.search(parts[-1]))


def files_of(base: str) -> list[Path]:
    """Mọi file/thư mục của MỘT gốc trong output.

    So khớp phần đuôi sau tên gốc phải rỗng hoặc bắt đầu bằng . hay _ — để
    "abc_x0.7" không vơ nhầm file của gốc khác trùng tiền tố kiểu "abc_x0.75".
    Nếu gốc có thư mục riêng và trong đó KHÔNG còn gì khác → trả về nguyên
    thư mục (vào Thùng rác một cục, gọn hơn từng file).
    """
    target = OUTPUT_DIR / base
    parent, prefix = target.parent, target.name
    try:
        entries = list(parent.iterdir())
    except OSError:
        return []
    matched = []
    for p in entries:
        if p.name.startswith(prefix):
            rest = p.name[len(prefix):]
            if rest == "" or rest[0] in "._":
                matched.append(p)
    if matched and parent != OUTPUT_DIR and len(matched) == len(entries):
        return [parent]
    return matched


def recycle(paths: list[Path], on_log=None) -> tuple[int, int]:
    """Đưa danh sách vào Thùng rác qua xoa_antoan của myvoice → (ok, lỗi).

    Tái dùng CODE qua import là chủ trương chung (như whisper/gansub) — chỉ
    cấm chia sẻ cài đặt người dùng giữa hai bảng điều khiển.
    """
    scripts = str(REPO_ROOT / "myvoice" / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import xoa_antoan
    return xoa_antoan.send_to_recycle_bin(paths, on_log=on_log)
