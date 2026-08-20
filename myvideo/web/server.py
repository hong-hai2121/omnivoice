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
import secrets
import sys
import threading
import time
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Form, Request
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               RedirectResponse)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

if __package__ in (None, ""):        # chạy thẳng file: python web/server.py
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    __package__ = "myvideo.web"

from . import steps as st            # noqa: E402
from .jobs import q, tail            # noqa: E402
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
                chesub=True, vesub=True,
                auto2=True, auto3=True, auto4=True, thaytieng=True, cpu=False,
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


def _bang_ctx() -> dict:
    s = load_settings()
    return {"rows": st.scan_rows(bool(s.get("thaytieng", True)),
                                 vesub=bool(s.get("vesub", True))),
            "files": _list_output(), "output_dir": str(OUTPUT_DIR)}


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
    return templates.TemplateResponse(
        request, "_capnhat.html",
        {"loi": loi, "ok": ok, **_queue_ctx(), **_bang_ctx(), **_nguon_ctx()},
        headers=headers)


def _nguon_ctx() -> dict:
    """Hàng chip "Gần đây" — gửi kèm MỌI lượt trả lời để nguồn vừa chạy hiện ra
    ngay (trang không tải lại) và dấu ✓/◐ chạy theo tiến độ."""
    return {"src_history": source_history()}


# ── Trang chính + partial ────────────────────────────────────────────────────
def _queue_ctx() -> dict:
    return {"q": q.state(), "loglines": tail.tail(18), "power": power.state()}


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
        # Kho kiểu + kho font đều kèm ẢNH XEM TRƯỚC (kieusub.py vẽ bằng đúng
        # libass sẽ burn) — thẻ ảnh chọn kiểu/font giống hệt myvoice.
        "sub_fonts": kieusub.danh_sach_font_web(),
        "kieusubs": kieusub.danh_sach_web(),
        "loi": request.query_params.get("loi", ""),
        **_queue_ctx(),
        **_bang_ctx(),
        **_nguon_ctx(),
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
                     mauvien: str = ""):
    """Ảnh xem thử TỔ HỢP kiểu + font + màu chữ/viền + cỡ chữ (+ vị trí).

    khung=ngang → khung 16:9 nguyên vẹn để thấy VỊ TRÍ chữ trên màn hình
    (vitri = % chiều cao từ đáy). Render bằng đúng libass sẽ burn nên nhìn sao
    ra vậy; mỗi tổ hợp chỉ render MỘT lần (cache xt_* trong kho ảnh dùng chung)
    nên lần đầu ~1-3 giây, các lần sau hiện ngay.

    dong=2 cố định: phụ đề myvideo lấy nguyên câu từ SRT rồi mới ngắt dòng, số
    dòng do độ dài câu quyết định chứ không gom được như bên myvoice.
    """
    try:
        p = kieusub.ve_xemtruoc(kieu, font, mau, vitri,
                                ca_khung=(khung == "ngang"),
                                cochu=cochu, dong=2, mau_vien=mauvien)
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
        chesub=bool(g("chesub")),
        vesub=bool(g("vesub")),
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
