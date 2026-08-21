# -*- coding: utf-8 -*-
"""Bảng điều khiển web cho myvideo — FastAPI, giao diện TỪNG BƯỚC như myvoice/web.

Chạy:  myvideo\\chay.bat      (hoặc)
       venv\\Scripts\\python.exe -m myvideo.web.server

Một trang, xếp theo thứ tự làm việc: hàng đợi → nguồn & tuỳ chọn → bốn khối
bước ①②③④ (bấm nút bước nào chạy từ bước đó, ô ⛓ quyết định nối tiếp) →
bảng trạng thái từng video với nút ⏩ chạy tiếp các bước còn thiếu.

Hàng đợi tái dùng JobRunner của myvoice (một worker — GPU/Firefox/ffmpeg đều
độc quyền, chạy song song chỉ giẫm chân nhau). Server điều khiển máy thật nên
CHỈ nghe 127.0.0.1, kèm token trong cookie — giống hệt myvoice/web/server.py.
"""

from __future__ import annotations

import json
import mimetypes
import os
import re
import secrets
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Form, Request
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               RedirectResponse, Response)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

if __package__ in (None, ""):        # chạy thẳng file: python web/server.py
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    __package__ = "myvideo.web"

from . import steps as st            # noqa: E402
from .jobs import (q, q_dang, q_fb, tail, tail_dang, tail_fb)  # noqa: E402
from .power import watcher as power  # noqa: E402

WEB_DIR = Path(__file__).resolve().parent
BASE_DIR = WEB_DIR.parent                     # myvideo/
REPO_ROOT = BASE_DIR.parent                   # gốc repo (chứa venv)

# Windows không đăng ký sẵn .webp trong registry → mimetypes đoán ra "text/plain",
# ảnh xem trước của kiểu ĐỘNG phải trông chờ trình duyệt tự đánh hơi. Khai một
# lần ở đây là cả StaticFiles lẫn FileResponse trả đúng image/webp.
mimetypes.add_type("image/webp", ".webp")

# Kho kiểu phụ đề DÙNG CHUNG với myvoice (đã chuyển về myvoice/scripts/kieusub.py
# ngày 2026-08-16): mẫu JSON, font rời và ảnh xem trước đều nằm bên myvoice.
_MYVOICE_SCRIPTS = str(REPO_ROOT / "myvoice" / "scripts")
if _MYVOICE_SCRIPTS not in sys.path:
    sys.path.insert(0, _MYVOICE_SCRIPTS)
import kieusub                       # noqa: E402
OUTPUT_DIR = st.OUTPUT_DIR
TOKEN_FILE = WEB_DIR / "token.txt"
SETTINGS_FILE = WEB_DIR / "web_settings.json"
COOKIE = "mvid_token"

MEDIA_EXTS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv", ".ts", ".m4v",
              ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus"}

# ── Nguồn: lịch sử + kho file để chọn (giống khối Nguồn bên myvoice) ────────
SRC_HISTORY_MAX = 15        # nhớ bấy nhiêu nguồn gần nhất
SRC_PICK_MAX = 60           # liệt kê tối đa bấy nhiêu file mỗi thư mục

# Ba chỗ file nguồn hay nằm. Thư mục nào không có thì bảng chọn bỏ qua.
#   output = video ĐÃ làm chậm (_x0.7) — dán vào ô Nguồn để chạy lẻ bước ②③④.
DOWNLOAD_DIRS = [
    (Path.home() / "Downloads", "Tải về"),
    (Path.home() / "Videos", "Videos"),
    (OUTPUT_DIR, "Đã làm chậm — chạy lẻ ②③④"),
]

# Cài đặt của TỪNG BƯỚC (lưu lại sau mỗi lần bấm chạy):
#   Ô chung: lang (tiếng GỐC của video)
#   ① speed/model/maxchars(+maxchars_en) · ② batchchars/offline
#   ③ voice (+ voice_stars ghim ⭐)
#   ④ vesub/kieusub/subfont/submau/submauvien/subcochu/subvitri/subchars/
#      chesub/thaytieng/cpu
# maxchars giữ RIÊNG theo tiếng: 16 chữ Hán và 42 ký tự Anh là hai ngưỡng khác
# hẳn nhau, dùng chung một ô thì đổi ngôn ngữ lần nào cũng phải gõ lại.
DEFAULTS = dict(lang="zh", speed="0.7", model="medium", maxchars="16",
                maxchars_en="42", ngucanh=True, gopcau=True,
                batchchars="1200", offline=False,
                voice="", voice_stars=[], subchars="50",
                kieusub="hopbo", subfont="",
                # Đè lên kiểu đã chọn (rỗng = giữ của kiểu): màu chữ · màu viền
                # · cỡ chữ (% cỡ gốc) · vị trí (% chiều cao từ đáy; rỗng = tự đặt).
                submau="", submauvien="", subcochu="100", subvitri="",
                # Số dòng mỗi lần hiện chữ (2 = như ảnh mẫu của kho kiểu; câu
                # dài hơn thì bước ④ tách thành nhiều lần hiện nối nhau).
                subdong="2",
                # Phóng to video NỀN bấy nhiêu % rồi cắt giữa về khung cũ
                # (rỗng/0 = giữ nguyên). Chữ vẽ sau zoom nên không phóng theo.
                zoom="",
                chesub=True, vesub=True,
                # 📱 kèm bản DỌC 9:16 (<B>_doc.mp4) sau bước ④ — mặc định tắt.
                xuatdoc=False,
                # 🎵 Nhạc nền nhỏ dưới tiếng chính: tên file trong myvideo/nhac
                # (rỗng = không nhạc — mặc định tắt) + âm lượng dB (âm).
                nhacnen="", nhacnen_db="-18",
                # 🏷 Đóng logo / nối outro của HỒ SƠ KÊNH đang chọn
                # (kenh/<tên>/logo.png · outro.mp4) — mặc định tắt cả hai.
                logo_kenh=False, outro_kenh=False,
                # 🧪 Nút thử cắt 60 giây TỪ PHÚT THỨ này (0/rỗng = từ đầu).
                thu60_tu="",
                auto2=True, auto3=True, auto4=True, thaytieng=True, cpu=False,
                # Khối 📤 ĐĂNG BÀI (lưu qua /dang/luu, KHÔNG nằm trong form chính):
                # `kenh` = HỒ SƠ KÊNH đang dùng (thư mục trong myvideo/kenh/ —
                # nhiều tài khoản, xem kenh_hoso.py); cài đặt YouTube + tên kênh
                # cho SEO. Hai ô TỰ ĐỘNG đăng sau bước ④ mặc định TẮT (khác
                # myvoice) — hồ sơ chưa cấu hình thì không tự ý lên lịch đi đâu
                # cả; cấu hình xong người dùng tự bật.
                kenh="",
                yt_category="22", yt_privacy="schedule", yt_kids=False, yt_ai=True,
                seo_kenh="", auto_dang=False, fb_auto=False,
                # Nguồn đã chạy, mới nhất đứng đầu — hiện thành hàng chip
                # "Gần đây" dưới ô Nguồn, bấm là điền lại, khỏi đi tìm.
                src_history=[])


def _token() -> str:
    try:
        t = TOKEN_FILE.read_text(encoding="utf-8").strip()
        if t:
            return t
    except OSError:
        pass
    t = secrets.token_urlsafe(9)
    TOKEN_FILE.write_text(t, encoding="utf-8")
    return t


TOKEN = _token()


def load_settings() -> dict:
    try:
        d = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        return {**DEFAULTS, **d} if isinstance(d, dict) else dict(DEFAULTS)
    except Exception:
        return dict(DEFAULTS)


def save_settings(data: dict) -> None:
    merged = {**load_settings(), **data}
    SETTINGS_FILE.write_text(json.dumps(merged, ensure_ascii=False, indent=2),
                             encoding="utf-8")


def _clamp(v, lo: int, hi: int, dflt: int) -> str:
    try:
        return str(max(lo, min(int(str(v).strip()), hi)))
    except (TypeError, ValueError):
        return str(dflt)


def _hex6(v) -> str:
    """Màu người dùng chọn → 'RRGGBB' viết hoa; sai dạng/rỗng = '' (theo kiểu)."""
    m = str(v or "").strip().lstrip("#")
    return m.upper() if len(m) == 6 and all(c in "0123456789abcdefABCDEF"
                                            for c in m) else ""


def _pct(v, lo: int, hi: int) -> str:
    """Ô % để TRỐNG được (rỗng = tự đặt) — có số thì kẹp vào [lo, hi]."""
    t = str(v or "").strip()
    if not t:
        return ""
    try:
        return str(max(lo, min(int(round(float(t))), hi)))
    except ValueError:
        return ""


def _phut(v) -> str:
    """Ô "từ phút thứ…" của nút 🧪: số phút (cho lẻ 2.5), rỗng/0/rác = từ đầu."""
    t = str(v or "").strip().replace(",", ".")
    try:
        m = max(0.0, min(600.0, float(t)))
        return f"{m:g}" if m else ""
    except ValueError:
        return ""


# ── FastAPI ──────────────────────────────────────────────────────────────────
app = FastAPI(title="myvideo — bảng điều khiển")
# Ảnh xem trước kiểu phụ đề nằm bên myvoice (kho dùng chung) — mount TRƯỚC
# /static để đường dẫn /static/kieusub/... trong template khỏi phải đổi.
kieusub.ANH_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static/kieusub", StaticFiles(directory=str(kieusub.ANH_DIR)),
          name="kieusub")
app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))


def _asset_v() -> str:
    """Chống cache trình duyệt cho app.css — cùng mẹo với myvoice (mtime = phiên bản)."""
    try:
        return str(int((WEB_DIR / "static" / "app.css").stat().st_mtime))
    except Exception:
        return "0"


templates.env.globals["asset_v"] = _asset_v


@app.middleware("http")
async def require_token(request: Request, call_next):
    if request.url.path.startswith("/static"):
        return await call_next(request)
    given = request.query_params.get("token") or request.cookies.get(COOKIE, "")
    if not secrets.compare_digest(given, TOKEN):
        return HTMLResponse(
            "<h1>Cần token</h1><p>Mở bằng đường dẫn có <code>?token=…</code> "
            "in ở cửa sổ launcher lúc khởi động.</p>", status_code=401)
    response = await call_next(request)
    if request.query_params.get("token"):
        response.set_cookie(COOKIE, TOKEN, max_age=30 * 86400, httponly=True,
                            samesite="lax")
    return response


def _human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} GB"


def _human_when(ts: float) -> str:
    d = time.time() - ts
    if d < 3600:
        return f"{d / 60:.0f} phút trước"
    if d < 86400:
        return f"{d / 3600:.0f} giờ trước"
    if d < 86400 * 7:
        return f"{d / 86400:.0f} ngày trước"
    return time.strftime("%d/%m/%Y", time.localtime(ts))


# ── Khối Nguồn: lịch sử · dấu đã-làm · bảng chọn file ───────────────────────
# Giống hệt khối Nguồn bên myvoice/web (core.py): chip "Gần đây" + nút 📂 mở
# bảng chọn file. Trình duyệt KHÔNG cho biết đường dẫn thật của file khi dùng
# <input type=file> (chỉ trả "C:\fakepath\…") mà pipeline lại cần đường dẫn
# thật, nên danh sách file do server đọc thẳng từ đĩa — server chỉ nghe
# 127.0.0.1 nên đó cũng chính là máy đang ngồi.
def _tien_do() -> dict[str, dict]:
    """Tên video (không đuôi, chữ thường) → đã chạy tới đâu trong output.

    Khoá theo TÊN GỐC (cắt bỏ tag _x…) nên nhận ra cả khi dán file nguồn lẫn
    khi dán file kết quả `_x0.7`, và không phụ thuộc tốc độ đang chọn — video
    dựng ở 0.7 rồi mà nay ô Tốc độ để 0.8 vẫn thấy dấu đã làm.
    """
    s = load_settings()
    thay = bool(s.get("thaytieng", True))
    out: dict[str, dict] = {}
    for r in st.scan_rows(thay, limit=500, vesub=bool(s.get("vesub", True))):
        ten = st.tenchinh(Path(r["base"]).name)
        xong = [r["video"] and r["srt"], r["vi"],
                *([r["audio"]] if thay else []), r["sub"]]
        done = sum(1 for x in xong if x)
        p = {"lam": True, "xong": all(xong), "done": done,
             "buoc": f"{done}/{len(xong)}"}
        # Cùng một video có thể có nhiều gốc (dựng 0.7 rồi dựng lại 0.8):
        # giữ cái chạy được xa nhất.
        if p["done"] > out.get(ten, {}).get("done", -1):
            out[ten] = p
    return out


def _danh_dau(src: str, prog: dict[str, dict]) -> dict:
    """Nhãn "đã làm" cho một nguồn — nguồn chưa chạy bao giờ thì không có nhãn."""
    return prog.get(st.tenchinh(Path(src).stem)) or {"lam": False, "xong": False,
                                                     "done": 0, "buoc": ""}


def _src_label(src: str) -> str:
    """Nhãn ngắn cho chip: chỉ tên file, bỏ đường dẫn dài loằng ngoằng."""
    return Path(src).name or src


def source_history() -> list[dict]:
    """Nguồn đã chạy, mới nhất trước — `full` để điền vào ô, `label` để hiện."""
    raw = load_settings().get("src_history") or []
    prog = _tien_do()
    return [{"full": s, "label": _src_label(s), **_danh_dau(s, prog)}
            for s in raw if isinstance(s, str) and s.strip()]


def remember_sources(lines: list[str]) -> None:
    """Đẩy các nguồn vừa chạy lên đầu lịch sử (bỏ trùng, cắt bớt phần cũ)."""
    old = [s for s in (load_settings().get("src_history") or []) if isinstance(s, str)]
    merged: list[str] = []
    for s in [*reversed([l.strip() for l in lines if l.strip()]), *old]:
        if s not in merged:
            merged.append(s)
    save_settings({"src_history": merged[:SRC_HISTORY_MAX]})


def _list_source_files() -> list[dict]:
    """File video/audio trong các thư mục nguồn — mới nhất trước, theo từng nhóm.

    Chỉ đọc tên + cỡ + ngày sửa, kèm dấu đã-làm để khỏi chọn nhầm file đã chạy.
    Riêng nhóm output quét sâu một cấp (mỗi video một thư mục con) và chỉ lấy
    video `_x…` — đó mới là thứ dán vào ô Nguồn để chạy lẻ bước ②③④.
    """
    prog = _tien_do()
    groups = []
    for folder, label in DOWNLOAD_DIRS:
        la_out = folder == OUTPUT_DIR
        try:
            if la_out:
                items = [c for p in folder.iterdir() if p.is_dir()
                         for c in p.iterdir()
                         if c.is_file() and c.suffix.lower() == ".mp4"
                         and st.la_video_cham(c.stem)]
                items += [p for p in folder.iterdir()          # kết quả cũ dạng phẳng
                          if p.is_file() and p.suffix.lower() == ".mp4"
                          and st.la_video_cham(p.stem)]
            else:
                items = [p for p in folder.iterdir()
                         if p.is_file() and p.suffix.lower() in MEDIA_EXTS]
        except OSError:
            continue                      # thư mục không có/không đọc được → bỏ qua
        items.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        files = []
        for p in items[:SRC_PICK_MAX]:
            info = p.stat()
            files.append({"name": p.name, "path": str(p),
                          "size": _human_size(info.st_size),
                          "when": _human_when(info.st_mtime),
                          **_danh_dau(str(p), prog)})
        groups.append({"label": label, "folder": str(folder),
                       "files": files, "more": max(0, len(items) - SRC_PICK_MAX)})
    return groups


def _list_output(limit: int = 15) -> list[dict]:
    """File mới nhất trong output — mỗi video một thư mục con nên quét sâu 1 cấp,
    tên hiện dạng '<thư mục>/<file>' (file phẳng cũ vẫn hiện tên trần)."""
    items = []
    try:
        for p in OUTPUT_DIR.iterdir():
            if p.is_file():
                items.append(p)
            elif p.is_dir():
                try:
                    items.extend(c for c in p.iterdir() if c.is_file())
                except OSError:
                    pass
    except Exception:
        return []
    items.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [{"name": p.relative_to(OUTPUT_DIR).as_posix(),
             "size": _human_size(p.stat().st_size),
             "when": time.strftime("%d/%m %H:%M", time.localtime(p.stat().st_mtime))}
            for p in items[:limit]]


# ── 🚨 Soát chất lượng từng video (cột "Soát" của bảng Kết quả) ──────────────
# Đọc _vi.srt (câu còn sót chữ Hán = dịch thiếu) + _vi_timeline.json (câu bị
# xếp lệch xa mốc SRT = giọng đè nhau phải dời). Bảng tự vẽ lại 5 giây/lần nên
# cache theo mtime — file không đổi thì không đọc lại.
#
# HAI BẬC báo — đo trên video thật: giọng Việt dài hơn khe tiếng gốc nên vài
# giây lệch là chuyện THƯỜNG của bộ xếp chống đè, video nào cũng ⚠️ thì cột
# thành vô dụng. Sót chữ Hán hoặc lệch quá 10s mới ⚠️ đỏ; lệch 3-10s chỉ ghi
# chú mờ (di chuột đọc chi tiết, bấm 🎞 xem timeline).
_HAN_RE = re.compile(r"[一-鿿㐀-䶿]")
_LECH_MS = 3000                 # từ mức này tính là "có lệch" (ghi chú mờ)
_LECH_NANG_MS = 10000           # lệch quá 10 giây = giọng lạc hẳn khỏi hình → ⚠️
_SOAT_CACHE: dict[str, tuple[tuple, dict]] = {}


def _soat(base: str) -> dict:
    """→ {"han", "lech", "lech_max", "loi": [nặng → ⚠️], "nhe": [ghi chú mờ]}."""
    srt = OUTPUT_DIR / f"{base}_vi.srt"
    tl = OUTPUT_DIR / f"{base}_vi_timeline.json"

    def _mt(p):
        try:
            return p.stat().st_mtime
        except OSError:
            return 0.0

    key = (_mt(srt), _mt(tl))
    hit = _SOAT_CACHE.get(base)
    if hit and hit[0] == key:
        return hit[1]

    han = 0
    if key[0]:
        try:
            for block in re.split(r"\n\s*\n", srt.read_text(encoding="utf-8-sig")):
                text = "\n".join(l for l in block.splitlines()
                                 if l.strip() and not l.strip().isdigit()
                                 and "-->" not in l)
                if len(_HAN_RE.findall(text)) >= 2:   # 1 chữ lẻ có thể là tên riêng
                    han += 1
        except OSError:
            pass
    lech = lech_max = 0
    if key[1]:
        try:
            cues = json.loads(tl.read_text(encoding="utf-8")).get("cues", [])
            do_lech = [abs(int(c.get("shift_ms", 0))) for c in cues]
            lech = sum(1 for x in do_lech if x > _LECH_MS)
            lech_max = max(do_lech, default=0)
        except (OSError, ValueError):
            pass
    loi, nhe = [], []
    if han:
        loi.append(f"{han} câu còn sót chữ Hán trong bản dịch — sửa {base}_vi.srt "
                   "rồi chạy lại ③④")
    ghi_lech = (f"{lech} câu xếp lệch mốc quá {_LECH_MS // 1000}s "
                f"(xa nhất {lech_max / 1000:.1f}s) — bấm 🎞 xem timeline")
    if lech_max > _LECH_NANG_MS:
        loi.append(ghi_lech)
    elif lech:
        nhe.append(ghi_lech)
    out = {"han": han, "lech": lech, "lech_max": lech_max, "loi": loi, "nhe": nhe}
    _SOAT_CACHE[base] = (key, out)
    return out


def _bang_ctx() -> dict:
    s = load_settings()
    rows = st.scan_rows(bool(s.get("thaytieng", True)),
                        vesub=bool(s.get("vesub", True)))
    for r in rows:
        r["soat"] = _soat(r["base"])
    return {"rows": rows, "files": _list_output(), "output_dir": str(OUTPUT_DIR)}


# ── 📊 VRAM còn trống (card 8GB dùng chung với Chrome — thấy sắp cạn thì khoan
# xếp mẻ mới, kẻo model tràn sang RAM chậm gấp chục lần). Hỏi nvidia-smi tối đa
# 5 giây/lần dù khối hàng đợi vẽ lại 2 giây/lần; máy không có nvidia thì thôi. #
_VRAM_CACHE: dict = {"t": 0.0, "v": None}


def _vram() -> dict | None:
    now = time.time()
    if now - _VRAM_CACHE["t"] < 5:
        return _VRAM_CACHE["v"]
    v = None
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3,
            creationflags=0x08000000 if sys.platform == "win32" else 0)
        used, total = (int(x) for x in r.stdout.strip().splitlines()[0].split(","))
        v = {"used": used, "total": total, "free": total - used,
             "pct": round(100 * used / total),
             "warn": total - used < 1500}       # dưới ~1.5GB là sắp tràn
    except Exception:
        v = None
    _VRAM_CACHE.update(t=now, v=v)
    return v


def _home(loi: str = "") -> RedirectResponse:
    url = "/?loi=" + quote(loi) if loi else "/"
    return RedirectResponse(url=url, status_code=303)


def _tra(request: Request, loi: str = "", ok: str = "",
         luu: bool = False, chay: bool = False):
    """Trả lời cho MỌI nút bấm: qua htmx thì cập nhật TẠI CHỖ (khối hàng đợi +
    bảng kết quả + lời nhắn góc phải), KHÔNG tải lại trang — khỏi mất chỗ đang
    cuộn, ô Nguồn đang gõ dở và các tuỳ chọn vừa chỉnh. Không có JS thì rơi về
    chuyển hướng như cũ.

    luu=True (đường /luu và /chay — hai đường DUY NHẤT ghi xuống đĩa) mà không
    lỗi thì kèm HX-Trigger "mvid:xong" để trang tự dọn: bỏ dấu “chưa lưu”, và
    sau lượt CHẠY thì bỏ tick hai ô “làm lại” (hai ô đó chỉ có giá trị cho đúng
    lượt vừa bấm — trước đây trang tải lại nên tự sạch, nay phải tự bỏ).
    """
    if not request.headers.get("hx-request"):
        return _home(loi)
    headers = ({"HX-Trigger": json.dumps({"mvid:xong": {"chay": chay}})}
               if luu and not loi else {})
    # 📤 Đăng bài và ⏱ Hàng đợi giờ là TAB RIÊNG: chỉ vẽ lại các khối CÓ MẶT
    # trên trang vừa bấm nút (htmx gửi HX-Current-URL) — swap vào id không tồn
    # tại là htmx la lỗi ở console, mà dựng context thừa cũng phí (quét sổ
    # Facebook cho một nút bấm bên trang quy trình chẳng hạn). Khối hàng đợi
    # LUÔN trả (trang nào cũng có #queue — hai trang kia là mỏ neo ẩn).
    url = request.headers.get("hx-current-url") or ""
    tren_dang, tren_hangdoi = "/dangbai" in url, "/hangdoi" in url
    ctx = {"loi": loi, "ok": ok, "tren_dang": tren_dang,
           "tren_hangdoi": tren_hangdoi, **_queue_ctx()}
    if tren_dang:
        ctx.update(_dang_ctx())
    elif not tren_hangdoi:
        ctx.update(**_bang_ctx(), **_nguon_ctx())
    return templates.TemplateResponse(request, "_capnhat.html", ctx,
                                      headers=headers)


def _nguon_ctx() -> dict:
    """Hàng chip "Gần đây" — gửi kèm MỌI lượt trả lời để nguồn vừa chạy hiện ra
    ngay (trang không tải lại) và dấu ✓/◐ chạy theo tiến độ."""
    return {"src_history": source_history()}


# ── Trang chính + partial ────────────────────────────────────────────────────
def _queue_ctx() -> dict:
    return {"q": q.state(), "loglines": tail.tail(18), "power": power.state(),
            "vram": _vram()}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    s = load_settings()
    # Giọng ⭐ đã ghim đứng đầu danh sách, phần còn lại theo thứ tự tên.
    vs = st.list_voices()
    stars = [v for v in s.get("voice_stars", []) if v in vs]
    # data-i = chỗ đứng theo tên (chưa ghim). Nút ⭐ giờ xếp lại danh sách ngay
    # trên trang, nên lúc BỎ ghim còn biết trả giọng về đúng chỗ cũ.
    tt = {v: i for i, v in enumerate(vs)}
    return templates.TemplateResponse(request, "index.html", {
        "settings": s,
        "voices": [{"ten": v, "i": tt[v], "sao": v in stars}
                   for v in stars + [v for v in vs if v not in stars]],
        "voice_stars": stars,
        # 🎵 Kho nhạc nền myvideo/nhac — cho ô chọn ở khối ④.
        "nhacs": st.list_nhac(),
        # Kho kiểu + kho font đều kèm ẢNH XEM TRƯỚC (kieusub.py vẽ bằng đúng
        # libass sẽ burn) — thẻ ảnh chọn kiểu/font giống hệt myvoice.
        "sub_fonts": kieusub.danh_sach_font_web(),
        "kieusubs": kieusub.danh_sach_web(),
        "loi": request.query_params.get("loi", ""),
        **_bang_ctx(),
        **_nguon_ctx(),
    })


@app.get("/dangbai", response_class=HTMLResponse)
async def dangbai_view(request: Request):
    """TAB 📤 Đăng bài — tách khỏi trang quy trình vì khâu này nằm NGOÀI vòng
    lặp 4 bước (dựng xong cả mẻ mới ngó tới). _dang_ctx đã kèm settings."""
    return templates.TemplateResponse(request, "dangbai.html", {
        "trang": "dang",
        "loi": request.query_params.get("loi", ""),
        **_dang_ctx(),
    })


@app.get("/hangdoi", response_class=HTMLResponse)
async def hangdoi_view(request: Request):
    """TAB ⏱ Hàng đợi — nguyên khối "Việc đang chạy" của trang chính dời sang,
    không đổi logic nào (vẫn _queuepanel.html tự làm mới 2 giây/lần)."""
    return templates.TemplateResponse(request, "hangdoi.html", {
        "settings": load_settings(),      # base.html cần settings.lang
        "trang": "hangdoi",
        "loi": request.query_params.get("loi", ""),
        **_queue_ctx(),
    })


@app.get("/api/tep-nguon")
async def api_tep_nguon():
    """File video/audio trong các thư mục nguồn — cho nút 📂 Thêm từ máy.

    Trình duyệt không cho biết đường dẫn thật của file người dùng chọn, mà các
    script lại cần đường dẫn thật; server chạy ngay trên máy này nên đọc thẳng
    đĩa là đúng chỗ vừa tải video về."""
    return JSONResponse({"groups": _list_source_files()})


@app.post("/nguon/xoalichsu")
async def xoa_lich_su_nguon():
    """Nút 🗑 ở hàng “Gần đây”: quên các nguồn đã chạy, KHÔNG đụng ô đang nhập.

    Trả JSON chứ không redirect: khối Nguồn nằm trong form chạy chung nên nút
    này là type=button gọi ngầm bằng fetch — để submit thì nó thành nút mặc
    định của form, bấm Enter trong ô Nguồn hoá ra xoá lịch sử."""
    save_settings({"src_history": []})
    tail.add("🗑 Đã xoá danh sách nguồn gần đây.")
    return JSONResponse({"ok": True})


@app.get("/kieusub-xemtruoc")
def kieusub_xemtruoc(kieu: str = "hopbo", font: str = "", mau: str = "",
                     vitri: str = "", khung: str = "", cochu: str = "",
                     dong: int = 2, mauvien: str = ""):
    """Ảnh xem thử TỔ HỢP kiểu + font + màu chữ/viền + cỡ chữ + số dòng (+ vị trí).

    khung=ngang → khung 16:9 nguyên vẹn để thấy VỊ TRÍ chữ trên màn hình
    (vitri = % chiều cao từ đáy). Render bằng đúng libass sẽ burn nên nhìn sao
    ra vậy; mỗi tổ hợp chỉ render MỘT lần (cache xt_* trong kho ảnh dùng chung)
    nên lần đầu ~1-3 giây, các lần sau hiện ngay.

    dong = số dòng mỗi lần hiện chữ — bước ④ giờ tách câu SRT dài thành nhiều
    lần hiện ≤ dong dòng (chia_cue của video_gansub_cung), cùng nghĩa myvoice.
    """
    try:
        p = kieusub.ve_xemtruoc(kieu, font, mau, vitri,
                                ca_khung=(khung == "ngang"),
                                cochu=cochu, dong=dong, mau_vien=mauvien)
    except Exception:
        p = None
    if not p:
        return JSONResponse({"error": "không vẽ được ảnh xem thử"}, status_code=404)
    return FileResponse(str(p))


@app.get("/partials/queue", response_class=HTMLResponse)
async def partial_queue(request: Request):
    return templates.TemplateResponse(request, "_queue.html", _queue_ctx())


@app.get("/partials/bang", response_class=HTMLResponse)
async def partial_bang(request: Request):
    return templates.TemplateResponse(request, "_bang.html", _bang_ctx())


@app.get("/timeline", response_class=HTMLResponse)
async def timeline_view(request: Request, base: str = ""):
    """Trang xem XẾP AUDIO kiểu CapCut: hai track — mốc SRT gốc (trước xếp)
    và mốc đã xếp chống đè (sau xếp) — vẽ từ <gốc>_vi_timeline.json."""
    if not st.is_base(base):
        return _home(f"Tên không hợp lệ: {base}")
    tl = Path(f"{OUTPUT_DIR / base}_vi_timeline.json")
    if not tl.is_file():
        return _home(f"{base}: chưa có timeline — chạy bước ③ trước.")
    try:
        d = json.loads(tl.read_text(encoding="utf-8"))
        cues = d["cues"]
    except Exception as e:
        return _home(f"Không đọc được {tl.name}: {e}")

    def lane(key):
        arr = sorted(cues, key=lambda c: c[key])
        out = []
        for i, c in enumerate(arr):
            start = c[key]
            end = start + c["duration_ms"]
            ov = max(0, end - arr[i + 1][key]) if i + 1 < len(arr) else 0
            out.append({"id": c["id"], "text": c["text"], "start": start,
                        "end": end, "duration_ms": c["duration_ms"],
                        "shift_ms": c.get("shift_ms", 0), "ov": ov})
        return out

    def stat(xs):
        return {"n": sum(1 for c in xs if c["ov"]),
                "tong": f"{sum(c['ov'] for c in xs) / 1000:.1f}"}

    truoc, sau = lane("srt_start_ms"), lane("start_ms")
    end_s = d.get("timeline_end_us", 0) / 1e6
    total_s = max(end_s, max((c["end"] for c in truoc + sau), default=0) / 1000)
    buoc_tick = 10 if total_s <= 300 else 30
    return templates.TemplateResponse(request, "timeline.html", {
        "base": base, "truoc": truoc, "sau": sau,
        "st_truoc": stat(truoc), "st_sau": stat(sau),
        "end_s": end_s, "total_s": total_s,
        "ticks": list(range(0, int(total_s) + buoc_tick, buoc_tick)),
        "lech_max": f"{max((abs(c['shift_ms']) for c in sau), default=0) / 1000:.1f}",
    })


# ── 🫥 Sửa VÙNG CHE sub gốc bằng mắt ─────────────────────────────────────────
# Trước đây dò lệch là phải mở <video>_vungsub.json đoán số pixel. Trang này
# hiện KHUNG HÌNH THẬT của video với dải che tô màu đè lên — kéo hai mép (hoặc
# gõ số) rồi Lưu; bước ④ đọc đúng file JSON đó khi ô "Che mờ sub gốc" bật.
def _vungsub_video(base: str) -> Path | None:
    if not st.is_base(base):
        return None
    v = OUTPUT_DIR / f"{base}.mp4"
    return v if v.is_file() else None


@app.get("/vungsub", response_class=HTMLResponse)
def vungsub_view(request: Request, base: str = ""):
    video = _vungsub_video(base)
    if video is None:
        return _home(f"{base}: chưa có video _x… trong output — chạy bước ① trước.")
    import timvungsub
    try:
        w, h, dur = timvungsub._probe(video)
    except Exception as e:
        return _home(f"Không đọc được thông số video: {e}")
    vung = None
    try:
        d = json.loads(timvungsub._cache_path(video).read_text(encoding="utf-8"))
        if all(k in d for k in ("y0", "y1")):
            vung = d
    except (OSError, ValueError):
        pass
    # Chưa có vùng nào thì mở dải GỢI Ý ở khoảng sub hay nằm (72–88% chiều cao)
    # cho có cái mà kéo — chưa lưu thì chưa ảnh hưởng gì tới bước ④.
    y0 = int(vung["y0"]) if vung else round(h * 0.72)
    y1 = int(vung["y1"]) if vung else round(h * 0.88)
    return templates.TemplateResponse(request, "vungsub.html", {
        "settings": load_settings(),      # base.html cần settings.lang
        "base": base, "w": w, "h": h, "dur": dur,
        "y0": max(0, min(h, y0)), "y1": max(0, min(h, y1)),
        "co_vung": vung is not None,
    })


@app.get("/vungsub/khung")
def vungsub_khung(base: str = "", t: float = -1.0):
    """MỘT khung hình JPEG của video, nguyên cỡ — toạ độ trên ảnh = pixel video."""
    video = _vungsub_video(base)
    if video is None:
        return JSONResponse({"error": "không thấy video"}, status_code=404)
    import timvungsub
    if t < 0:
        try:
            t = timvungsub._probe(video)[2] * 0.3
        except Exception:
            t = 30.0
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{max(0.0, t):.2f}", "-i", str(video),
         "-frames:v", "1", "-f", "image2pipe", "-c:v", "mjpeg", "-q:v", "3", "-"],
        capture_output=True, timeout=60)
    if r.returncode != 0 or not r.stdout:
        return JSONResponse({"error": "ffmpeg không bắt được khung hình"},
                            status_code=500)
    return Response(content=r.stdout, media_type="image/jpeg",
                    headers={"Cache-Control": "no-store"})


@app.post("/vungsub/luu")
def vungsub_luu(base: str = Form(...), y0: int = Form(...), y1: int = Form(...)):
    video = _vungsub_video(base)
    if video is None:
        return JSONResponse({"error": "không thấy video"}, status_code=404)
    import timvungsub
    try:
        w, h, _d = timvungsub._probe(video)
    except Exception as e:
        return JSONResponse({"error": f"không đọc được video: {e}"}, status_code=500)
    y0, y1 = max(0, min(h, int(y0))), max(0, min(h, int(y1)))
    if y1 - y0 < 8:
        return JSONResponse({"error": "dải mỏng quá — kéo hai mép cách nhau ra"},
                            status_code=400)
    timvungsub._cache_path(video).write_text(json.dumps(
        {"y0": y0, "y1": y1, "w": w, "h": h,
         "ghi_chu": "sửa bằng trang 🫥 trên web; xoá file để dò lại tự động"},
        ensure_ascii=False, indent=2), encoding="utf-8")
    tail.add(f"🫥 {base}: đã lưu vùng che y {y0}–{y1}.")
    return JSONResponse({"ok": True, "y0": y0, "y1": y1})


@app.post("/vungsub/dola")
def vungsub_dola(base: str = Form(...)):
    """Chạy lại bộ dò tự động (10 khung hình, vài giây) — CHỈ trả kết quả cho
    trang xem thử, chưa ghi gì; ưng thì bấm Lưu."""
    video = _vungsub_video(base)
    if video is None:
        return JSONResponse({"error": "không thấy video"}, status_code=404)
    import timvungsub
    try:
        vung = timvungsub.tim_vung(video, dung_cache=False)
    except Exception as e:
        return JSONResponse({"error": f"dò lỗi: {e}"}, status_code=500)
    if not vung:
        return JSONResponse({"none": True})
    return JSONResponse({"y0": vung["y0"], "y1": vung["y1"]})


@app.post("/vungsub/xoa")
def vungsub_xoa(base: str = Form(...)):
    """Bỏ vùng đã lưu — lượt dựng sau sẽ tự dò lại từ đầu."""
    video = _vungsub_video(base)
    if video is None:
        return JSONResponse({"error": "không thấy video"}, status_code=404)
    import timvungsub
    try:
        timvungsub._cache_path(video).unlink()
    except OSError:
        pass
    tail.add(f"🫥 {base}: đã bỏ vùng che — lượt dựng sau tự dò lại.")
    return JSONResponse({"ok": True})


# ── Chạy việc ────────────────────────────────────────────────────────────────
def _settings_from_form(form) -> dict:
    g = form.get
    s = dict(
        lang=g("lang") if g("lang") in ("zh", "en") else "zh",
        speed=g("speed") or "0.7",
        model=g("model") or "medium",
        maxchars=_clamp(g("maxchars"), 4, 60, 16),
        maxchars_en=_clamp(g("maxchars_en"), 10, 120, 42),
        ngucanh=bool(g("ngucanh")),
        batchchars=_clamp(g("batchchars"), 200, 5000, 1200),
        gopcau=bool(g("gopcau")),
        offline=bool(g("offline")),
        voice=g("voice") or "",
        subchars=_clamp(g("subchars"), 10, 120, 50),
        kieusub=g("kieusub") or "hopbo",
        subfont=g("subfont") or "",
        submau=_hex6(g("submau")),
        submauvien=_hex6(g("submauvien")),
        subcochu=_pct(g("subcochu"), 50, 200) or "100",
        subvitri=_pct(g("subvitri"), 0, 100),
        subdong=g("subdong") if g("subdong") in ("1", "2") else "2",
        zoom=_pct(g("zoom"), 0, 100),
        chesub=bool(g("chesub")),
        vesub=bool(g("vesub")),
        xuatdoc=bool(g("xuatdoc")),
        # Nhạc nền: chỉ nhận TÊN FILE trần trong kho myvideo/nhac (chặn ../).
        nhacnen=(g("nhacnen") or "").strip()
                if (g("nhacnen") or "") == Path((g("nhacnen") or "")).name else "",
        nhacnen_db=str(_clamp(g("nhacnen_db"), -40, 0, -18)),
        logo_kenh=bool(g("logo_kenh")), outro_kenh=bool(g("outro_kenh")),
        thu60_tu=_phut(g("thu60_tu")),
        auto2=bool(g("auto2")), auto3=bool(g("auto3")), auto4=bool(g("auto4")),
        thaytieng=bool(g("thaytieng")), cpu=bool(g("cpu")),
    )
    # Danh sách ⭐ do trang tự sửa (mỗi dòng một tên) và gửi kèm lúc lưu/chạy.
    # CHỈ ghi đè khi form thật sự có ô này — lượt gửi từ trang cũ còn mở (chưa
    # có ô) mà ghi đè là xoá sạch danh sách đã ghim.
    if "voice_stars" in form:
        s["voice_stars"] = [x.strip() for x in (g("voice_stars") or "").splitlines()
                            if x.strip()]
    return s


@app.post("/chay")
async def chay(request: Request):
    form = await request.form()
    s = _settings_from_form(form)
    save_settings(s)                            # bấm chạy cũng là lưu cài đặt
    s["redoasr"] = bool(form.get("redoasr"))    # hai ô "làm lại" chỉ áp dụng
    s["redotts"] = bool(form.get("redotts"))    # cho lượt này, không lưu
    start = form.get("start") or "cham"

    # Ô Nguồn là DANH SÁCH: mỗi dòng một file → mỗi dòng một việc trong hàng đợi.
    sources = [l.strip().strip('"') for l in (form.get("sources") or "").splitlines()]
    sources = [l for l in sources if l]
    if not sources:
        return _tra(request, "Ô Nguồn đang trống — mỗi dòng một file video.")
    jobs, errs = [], []
    for src in sources:
        title, job_steps, err = st.build(start, src, s)
        if err:
            errs.append(err)
        else:
            jobs.append((title, job_steps))
    if errs:
        # Có dòng hỏng thì KHÔNG xếp dòng nào — sửa xong bấm lại, khỏi lẫn nửa chừng.
        return _tra(request, " · ".join(errs[:3]) + (" …" if len(errs) > 3 else ""))
    for title, job_steps in jobs:
        q.enqueue(title, job_steps)
    remember_sources(sources)     # để lần sau bấm chip là xong, khỏi đi tìm lại
    return _tra(request, ok=f"Đã lưu cài đặt · xếp {len(jobs)} việc vào hàng đợi",
                luu=True, chay=True)


@app.post("/luu")
async def luu(request: Request):
    save_settings(_settings_from_form(await request.form()))
    return _tra(request, ok="Đã lưu cài đặt", luu=True)


@app.post("/tiep")
async def tiep(request: Request, base: str = Form(...)):
    title, job_steps, err = st.resume(base, load_settings())
    if err:
        return _tra(request, err)
    q.enqueue(title, job_steps)
    return _tra(request, ok=f"Đã xếp: {title}")


@app.post("/buoc")
async def buoc(request: Request, base: str = Form(...), key: str = Form(...)):
    title, job_steps, err = st.single(base, key, load_settings())
    if err:
        return _tra(request, err)
    q.enqueue(title, job_steps)
    return _tra(request, ok=f"Đã xếp: {title}")


# ── Điều khiển hàng đợi ──────────────────────────────────────────────────────
@app.post("/hangdoi/pause")
async def hd_pause(request: Request):
    q.pause()
    return _tra(request, ok="⏸ Đã tạm dừng hàng đợi")


@app.post("/hangdoi/resume")
async def hd_resume(request: Request):
    q.resume()
    return _tra(request, ok="▶ Chạy tiếp")


@app.post("/hangdoi/skip")
async def hd_skip(request: Request):
    q.skip_current()
    return _tra(request, ok="⏭ Đã bỏ việc đang chạy")


@app.post("/hangdoi/stop")
async def hd_stop(request: Request):
    q.stop_all()
    return _tra(request, ok="⏹ Đã dừng hết")


@app.post("/hangdoi/bo/{jid}")
async def hd_bo(jid: int, request: Request):
    q.remove(jid)
    return _tra(request, ok="Đã bỏ việc khỏi hàng đợi")


@app.post("/hangdoi/power")
async def hd_power(request: Request):
    """Ô “Xong hết thì ngủ/tắt máy” — htmx gửi lên là trả lại ngay khối hàng đợi."""
    form = await request.form()
    power.arm(bool(form.get("on")), form.get("mode") or "")
    return _tra(request)


# ── 📤 ĐĂNG BÀI: YouTube + Facebook theo HỒ SƠ KÊNH ──────────────────────────
# Nhiều tài khoản quản lý dễ: mỗi kênh một thư mục myvideo/kenh/<tên>/ chứa
# trọn token + sổ sách (xem myvideo/kenh_hoso.py); trang có ô chọn kênh đang
# dùng + nút tạo kênh mới. Hồ sơ chưa cấu hình thì nút đăng khoá kèm dòng "⏳"
# nói rõ bước cần làm — tách hẳn kênh MimiAudio của myvoice, không có đường
# lui nào sang bên đó.
from datetime import datetime as _dt            # noqa: E402

for _p in (str(BASE_DIR), str(BASE_DIR / "YOUTUBE")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import dang_video_youtube as mvyt    # noqa: E402
import kenh_hoso as kh               # noqa: E402

# Script Facebook nạp theo đường dẫn (không đặt myvideo/FACEBOOK vào sys.path —
# kẻo trùng tên module với bản của myvoice nếu sau này cùng tiến trình).
import importlib.util                # noqa: E402

_fb_spec = importlib.util.spec_from_file_location(
    "mv_dang_facebook", str(BASE_DIR / "FACEBOOK" / "dang_video_facebook.py"))
mvfb = importlib.util.module_from_spec(_fb_spec)
_fb_spec.loader.exec_module(mvfb)


def _dang_ctx() -> dict:
    """Context khối 📤 Đăng bài — dựng từ FILE (sổ + cache của HỒ SƠ KÊNH đang
    chọn), không gọi API nào.

    Ngày dự kiến đăng Page tính bằng ĐÚNG plan_slots/known_busy của script —
    bảng nói một đằng Facebook nhận một nẻo là kiểu sai khó chịu nhất."""
    s = load_settings()
    ten = kh.hien_tai()

    # ── YouTube của hồ sơ đang chọn ──────────────────────────────────────────
    yt_thieu = kh.yt_thieu(ten)
    yt_note = ""
    if ten and not yt_thieu:
        mvyt.chon_kenh(kh.thu_muc(ten), kh.client_secret(ten))
        data = mvyt.load_video_cache()
        entry = data["channels"].get(data.get("current"))
        if entry:
            ch = entry.get("channel", {})
            try:
                yt_note = (f"Kênh: {ch.get('title', '?')} · "
                           f"{ch.get('video_count', 0)} video · khung trống kế tiếp "
                           f"{mvyt.next_publish_slot():%d/%m %H:%M}")
            except Exception:
                yt_note = f"Kênh: {ch.get('title', '?')}"
        else:
            yt_note = "Đã đăng nhập — bấm 🔑 lần nữa để đọc thông tin kênh."

    # ── Facebook của hồ sơ đang chọn ─────────────────────────────────────────
    fb_thieu = kh.fb_thieu(ten)
    fb_cooldown, fb_dadang, fb_synced = "", 0, ""
    slots, fb_cho_bases, fb_dukien = [], set(), {}
    if ten:
        mvfb.chon_kenh(ten)                     # trỏ sổ/cache vào hồ sơ này
        until, ly_do = mvfb.cooldown_left()
        if until:
            fb_cooldown = f"⏸ Đang tạm ngưng gọi Facebook tới {until:%H:%M} — {ly_do}"
        led = mvfb.load_ledger()
        cache = mvfb.load_cache()
        fb_dadang = len(led.get("eps") or {})
        fb_synced = (led.get("synced") or "")[:16].replace("T", " ")
        fb_cho, _ = mvfb.pending_videos(led)
        fb_dukien = {it["base"]: when for it, when in
                     zip(fb_cho, mvfb.plan_slots(len(fb_cho), None,
                                                 mvfb.known_busy(led, cache)))}
        fb_cho_bases = {it["base"] for it in fb_cho}
        # Lịch đang chờ trên Page (bản đọc ở lần 🔄 gần nhất) — mốc còn tương lai.
        for sl in cache.get("slots") or []:
            try:
                t = _dt.fromisoformat(str(sl.get("when")))
            except (TypeError, ValueError):
                continue
            if t > _dt.now():
                slots.append({"when": t, "ep": sl.get("ep")})
        slots.sort(key=lambda x: x["when"])

    # Video đã dựng xong (bước ④) — trạng thái đăng tính THEO hồ sơ đang chọn
    # (biên nhận ghi theo kênh: video lên kênh A vẫn là "chưa" với kênh B).
    rows = [r for r in st.scan_rows(limit=100) if r["sub"]]
    rows.reverse()                              # cũ trước, khớp thứ tự sẽ đăng
    table = []
    for r in rows:
        yt_r = bool(ten and kenh_bien_nhan_yt(r["base"], ten))
        table.append({"base": r["base"], "ten": mvfb.ten_hienthi(r["base"]),
                      "seo": r["seo"], "thumb": r["thumb"], "yt": yt_r,
                      "fb": bool(ten) and r["base"] not in fb_cho_bases,
                      "fb_when": fb_dukien.get(r["base"])})

    return {"settings": s, "dang": {
        "kenh": ten, "kenhs": kh.danh_sach(), "kenh_dir": str(kh.KENH_DIR),
        "yt_thieu": yt_thieu, "yt_note": yt_note,
        "categories": mvyt.CATEGORIES,
        "fb_thieu": fb_thieu, "fb_cooldown": fb_cooldown,
        "fb_dadang": fb_dadang, "fb_synced": fb_synced,
        "slots": slots, "rows": table,
        "qd": q_dang.state(), "qd_log": tail_dang.tail(8),
        "qf": q_fb.state(), "qf_log": tail_fb.tail(8),
        # Còn việc (đang chạy HOẶC chờ) ở một trong hai hàng đăng → khối tự vẽ
        # lại 5 giây/lần; rảnh thì bản vẽ mới không còn hx-get, vòng tự tắt.
        "ban": q_dang.busy() or q_fb.busy(),
    }}


def kenh_bien_nhan_yt(base: str, ten: str) -> dict | None:
    """Mục biên nhận YouTube của kênh `ten` cho một video (None = chưa đăng)."""
    return kh.doc_bien_nhan(OUTPUT_DIR / f"{base}_youtube_upload.json").get(ten)


def _queue_after_build(base: str) -> None:
    """Hook của steps: xong bước ④ một video → tự xếp việc đăng NẾU ô tự động
    đang bật VÀ hồ sơ kênh đang chọn đã cấu hình. Chưa cấu hình thì chỉ ghi một
    dòng nhắc — tuyệt đối không có đường lui sang kênh của myvoice."""
    s = load_settings()
    ten = kh.hien_tai()
    if s.get("auto_dang"):
        thieu = kh.yt_thieu(ten)
        if thieu:
            tail_dang.add(f"⏳ Bỏ tự đăng YouTube ({Path(base).name}): {thieu}")
        else:
            title, job_steps = st.youtube_steps(base, ten)
            q_dang.enqueue(title, job_steps)
    if s.get("fb_auto"):
        thieu = kh.fb_thieu(ten)
        if thieu:
            tail_fb.add(f"⏳ Bỏ tự lên lịch Facebook ({Path(base).name}): {thieu}")
        else:
            title, job_steps = st.facebook_steps("chay", ten, [base])
            q_fb.enqueue(title, job_steps)


st.after_build_hook = _queue_after_build


def _chon_from(form) -> list[str]:
    """Các ô tick trong bảng đăng bài (name=chon, value=base) — lọc tên hợp lệ."""
    return [b for b in form.getlist("chon") if st.is_base(b)]


@app.get("/partials/dang", response_class=HTMLResponse)
async def partial_dang(request: Request):
    return templates.TemplateResponse(request, "_dang.html", _dang_ctx())


def _save_dang_form(form) -> None:
    """Cài đặt của khối 📤 — nút 💾 lẫn MỌI nút chạy trong khối đều lưu (nếp
    "bấm chạy cũng là lưu" của cả hai web). Các checkbox đều nằm trong form
    #dangform nên vắng mặt = bỏ tick, suy được ý định."""
    g = form.get
    save_settings({
        # Hồ sơ kênh đang dùng — chỉ nhận tên có thật trong myvideo/kenh/.
        "kenh": g("kenh") if g("kenh") in kh.danh_sach() else "",
        "yt_category": (g("yt_category")
                        if str(g("yt_category")) in set(mvyt.CATEGORIES.values())
                        else "22"),
        "yt_privacy": (g("yt_privacy")
                       if g("yt_privacy") in ("schedule", "public", "unlisted")
                       else "schedule"),
        "yt_kids": bool(g("yt_kids")),
        "yt_ai": bool(g("yt_ai")),
        "seo_kenh": (g("seo_kenh") or "").strip()[:80],
        "auto_dang": bool(g("auto_dang")),
        "fb_auto": bool(g("fb_auto")),
    })


@app.post("/dang/luu")
async def dang_luu(request: Request):
    _save_dang_form(await request.form())
    return _tra(request, ok="Đã lưu cài đặt đăng bài", luu=True)


@app.post("/kenh/tao")
async def kenh_tao(request: Request):
    """Tạo hồ sơ kênh mới (thư mục + facebook.json mẫu) rồi CHỌN LUÔN nó."""
    form = await request.form()
    ten = (form.get("tenmoi") or "").strip()
    loi = kh.tao(ten)
    if loi:
        return _tra(request, loi)
    save_settings({"kenh": ten})
    return _tra(request, ok=f"📡 Đã tạo hồ sơ kênh “{ten}” và chọn làm kênh đang "
                            f"dùng — điền facebook.json + 🔑 đăng nhập YouTube là xong",
                luu=True)


@app.post("/dang/youtube")
async def dang_youtube(request: Request):
    form = await request.form()
    _save_dang_form(form)
    ten = kh.hien_tai()
    thieu = kh.yt_thieu(ten)
    if thieu:
        return _tra(request, f"⏳ YouTube của hồ sơ kênh chưa sẵn sàng: {thieu}")
    chon = _chon_from(form)
    if not chon:                    # không tick ô nào = mọi video KÊNH NÀY chưa đăng
        chon = [r["base"] for r in st.scan_rows(limit=200)
                if r["sub"] and not kenh_bien_nhan_yt(r["base"], ten)]
        chon.reverse()              # cũ trước — thứ tự lên sóng khớp thứ tự dựng
    if not chon:
        return _tra(request, ok=f"Kênh “{ten}” không còn video nào chờ đăng YouTube")
    for b in chon:
        title, job_steps = st.youtube_steps(b, ten)
        q_dang.enqueue(title, job_steps)
    return _tra(request, ok=f"⬆ Đã xếp {len(chon)} video vào hàng đợi đăng "
                            f"YouTube (kênh “{ten}”)")


@app.post("/dang/youtube/dangnhap")
async def dang_youtube_dangnhap(request: Request):
    form = await request.form()
    _save_dang_form(form)
    ten = kh.hien_tai()
    if not ten:
        return _tra(request, "⏳ Chưa chọn hồ sơ kênh nào — tạo/chọn ở đầu khối Đăng bài.")
    if not kh.client_secret(ten).exists():
        return _tra(request, f"⏳ Chưa có client_secret.json — tải OAuth client từ "
                             f"Google Cloud Console rồi đặt vào {kh.KENH_DIR} "
                             f"(dùng chung) hoặc {kh.thu_muc(ten)} (riêng hồ sơ này)")
    title, job_steps = st.youtube_login_steps(ten, bool(form.get("doikenh")))
    # light: lượt đăng nhập không được kích hoạt "🌙 xong hết thì ngủ".
    q_dang.enqueue(title, job_steps, light=True)
    return _tra(request, ok=f"🔑 Đã xếp lượt đăng nhập cho hồ sơ “{ten}” — trình "
                            "duyệt sẽ mở, nhớ chọn ĐÚNG kênh của hồ sơ này")


@app.post("/dang/facebook/{mode}")
async def dang_facebook(mode: str, request: Request):
    if mode not in ("chay", "xemtruoc", "quet"):
        return _tra(request, f"Chế độ không hợp lệ: {mode}")
    form = await request.form()
    _save_dang_form(form)
    ten = kh.hien_tai()
    thieu = kh.fb_thieu(ten)
    if thieu:
        return _tra(request, f"⏳ Facebook của hồ sơ kênh chưa sẵn sàng: {thieu}.")
    chon = _chon_from(form) if mode == "chay" else []
    title, job_steps = st.facebook_steps(mode, ten, chon)
    # 🔍/🔄 là việc NHẸ — không kích hoạt 🌙 (học JobRunner.heavy_busy myvoice).
    q_fb.enqueue(title, job_steps, light=(mode != "chay"))
    return _tra(request, ok=f"Đã xếp: {title}")


@app.post("/seo")
async def seo_chay(request: Request):
    form = await request.form()
    chon = _chon_from(form)
    if not chon and st.is_base(form.get("base") or ""):
        chon = [form.get("base")]           # nút 📑 trên một hàng của bảng
    if not chon:
        return _tra(request, "Chưa chọn video nào để sinh SEO.")
    title, job_steps = st.seo_steps(chon, force=bool(form.get("force")))
    # Hàng đợi CHÍNH: SEO dùng Firefox, chạy song song bước ② là giẫm profile.
    q.enqueue(title, job_steps)
    return _tra(request, ok=f"Đã xếp: {title} — dùng Firefox nên xếp ở hàng đợi chính")


@app.post("/thumb")
async def thumb_chay(request: Request):
    form = await request.form()
    chon = _chon_from(form)
    if not chon and st.is_base(form.get("base") or ""):
        chon = [form.get("base")]
    if not chon:
        return _tra(request, "Chưa chọn video nào để vẽ thumbnail.")
    title, job_steps = st.thumb_steps(chon, force=bool(form.get("force")))
    q.enqueue(title, job_steps)
    return _tra(request, ok=f"Đã xếp: {title}")


_Q_DANG = {"dang": q_dang, "fb": q_fb}


@app.post("/hangdoi2/{which}/{action}")
async def hd2(which: str, action: str, request: Request):
    """Điều khiển hai hàng đợi đăng — cùng bộ nút với hàng đợi chính."""
    runner = _Q_DANG.get(which)
    acts = {"pause": ("⏸ Đã tạm dừng", lambda r: r.pause()),
            "resume": ("▶ Chạy tiếp", lambda r: r.resume()),
            "skip": ("⏭ Đã bỏ việc đang chạy", lambda r: r.skip_current()),
            "stop": ("⏹ Đã dừng hết", lambda r: r.stop_all())}
    if runner is None or action not in acts:
        return _tra(request, "Lệnh không hợp lệ")
    msg, fn = acts[action]
    fn(runner)
    return _tra(request, ok=msg + (" (hàng đăng YouTube)" if which == "dang"
                                   else " (hàng Facebook)"))


# ── 🔊 Nghe thử: giọng mẫu + audio tiếng Việt đã xếp ─────────────────────────
@app.get("/nghe/giong")
async def nghe_giong(ten: str = ""):
    """Stream file giọng mẫu trong myvideo/voice — tên phải có trong kho."""
    if ten not in st.list_voices():
        return JSONResponse({"error": "không có giọng này trong myvideo/voice"},
                            status_code=404)
    return FileResponse(str(st.VOICE_DIR / ten))


@app.get("/nghe/ketqua")
async def nghe_ketqua(base: str = ""):
    """Audio tiếng Việt đã xếp timeline (<base>_vi_audio.wav) — nghe duyệt
    giọng TRƯỚC khi tốn thời gian dựng bước ④."""
    if not st.is_base(base):
        return JSONResponse({"error": f"tên không hợp lệ: {base}"}, status_code=404)
    f = Path(f"{OUTPUT_DIR / base}_vi_audio.wav")
    if not f.is_file():
        return JSONResponse({"error": "chưa có audio — chạy bước ③ trước"},
                            status_code=404)
    return FileResponse(str(f), media_type="audio/wav")


# ── Xoá output: CHỈ đưa vào Thùng rác, có xác nhận ở trình duyệt ─────────────
@app.post("/xoa")
async def xoa(request: Request, base: str = Form(...)):
    if not st.is_base(base):
        return _tra(request, f"Tên không hợp lệ: {base}")
    if q.busy():
        return _tra(request, "Hàng đợi đang chạy — dừng hết trước rồi hãy xoá "
                             "(file có thể đang được ghi).")
    files = st.files_of(base)
    if not files:
        return _tra(request, f"{base}: không thấy file nào trong output.")
    ok, fail = st.recycle(files, on_log=q.note)
    q.note(f"🗑 {base}: đã đưa {ok} mục vào Thùng rác"
           + (f", {fail} mục KHÔNG xoá được" if fail else "")
           + " — khôi phục: mở Thùng rác Windows.")
    return _tra(request, f"{base}: {fail} mục không đưa vào Thùng rác được — "
                         "xem nhật ký." if fail else "",
                ok=f"🗑 {base}: đã đưa {ok} mục vào Thùng rác")


@app.post("/xoa-het")
async def xoa_het(request: Request):
    if q.busy():
        return _tra(request, "Hàng đợi đang chạy — dừng hết trước rồi hãy xoá "
                             "(file có thể đang được ghi).")
    try:
        files = list(OUTPUT_DIR.iterdir())
    except OSError:
        files = []
    if not files:
        return _tra(request, "Thư mục output đang trống.")
    ok, fail = st.recycle(files, on_log=q.note)
    q.note(f"🗑 Đã đưa {ok} mục của output vào Thùng rác"
           + (f", {fail} mục KHÔNG xoá được" if fail else "")
           + " — khôi phục: mở Thùng rác Windows.")
    return _tra(request, f"{fail} mục không đưa vào Thùng rác được — xem nhật ký."
                if fail else "", ok=f"🗑 Đã đưa {ok} mục của output vào Thùng rác")


@app.post("/mo-thumuc")
async def mo_thumuc(request: Request):
    OUTPUT_DIR.mkdir(exist_ok=True)
    try:
        os.startfile(str(OUTPUT_DIR))          # noqa: S606 — máy cục bộ, cố ý
    except Exception as e:
        return _tra(request, f"Không mở được thư mục: {e}")
    return _tra(request, ok="📂 Đã mở thư mục output")


@app.get("/api/trangthai")
async def trangthai():
    """Cho launcher/công cụ ngoài hỏi nhanh: hàng đợi + vài dòng nhật ký cuối."""
    return JSONResponse({**q.state(), "lines": tail.tail(30)})


def main() -> None:
    import webbrowser

    import uvicorn

    OUTPUT_DIR.mkdir(exist_ok=True)
    # Ảnh xem trước kiểu phụ đề còn thiếu (kiểu mới thêm) → tự vẽ nền sau,
    # không chặn server; vẽ xong tải lại trang là thấy.
    threading.Thread(target=kieusub.taomau_thieu, daemon=True).start()
    port = int(os.environ.get("MYVIDEO_WEB_PORT", "8766"))
    url = f"http://127.0.0.1:{port}/?token={quote(TOKEN)}"
    print(f"🌐 myvideo web: {url}", flush=True)
    if not os.environ.get("MYVIDEO_WEB_NO_OPEN"):
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
