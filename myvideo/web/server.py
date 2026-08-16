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
import os
import secrets
import sys
import threading
import time
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
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
DOWNLOAD_DIR = Path.home() / "Downloads"

# Cài đặt của TỪNG BƯỚC (lưu lại sau mỗi lần bấm chạy):
#   ① speed/model/maxchars · ② batchchars/offline · ③ voice (+ voice_stars ghim ⭐)
#   ④ kieusub/subfont/subchars/chesub/thaytieng/cpu
DEFAULTS = dict(speed="0.7", model="medium", maxchars="16",
                batchchars="1200", offline=False,
                voice="", voice_stars=[], subchars="50",
                kieusub="hopbo", subfont="", chesub=True,
                auto2=True, auto3=True, auto4=True, thaytieng=True, cpu=False)


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


def _list_downloads(limit: int = 12) -> list[dict]:
    """Video/audio mới nhất trong Downloads — bấm là điền vào ô Nguồn."""
    try:
        items = [p for p in DOWNLOAD_DIR.iterdir()
                 if p.is_file() and p.suffix.lower() in MEDIA_EXTS]
    except Exception:
        return []
    items.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [{"name": p.name, "path": str(p),
             "size": _human_size(p.stat().st_size)} for p in items[:limit]]


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
    return {"rows": st.scan_rows(bool(s.get("thaytieng", True))),
            "files": _list_output(), "output_dir": str(OUTPUT_DIR)}


def _home(loi: str = "") -> RedirectResponse:
    url = "/?loi=" + quote(loi) if loi else "/"
    return RedirectResponse(url=url, status_code=303)


# ── Trang chính + partial ────────────────────────────────────────────────────
def _queue_ctx() -> dict:
    return {"q": q.state(), "loglines": tail.tail(18), "power": power.state()}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    s = load_settings()
    # Giọng ⭐ đã ghim đứng đầu danh sách, phần còn lại theo thứ tự tên.
    vs = st.list_voices()
    stars = [v for v in s.get("voice_stars", []) if v in vs]
    return templates.TemplateResponse(request, "index.html", {
        "settings": s,
        "downloads": _list_downloads(),
        "voices": stars + [v for v in vs if v not in stars],
        "voice_stars": stars,
        "fonts": kieusub.danh_sach_font(),
        "kieusubs": kieusub.danh_sach_web(),
        "loi": request.query_params.get("loi", ""),
        **_queue_ctx(),
        **_bang_ctx(),
    })


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
    return dict(
        speed=g("speed") or "0.7",
        model=g("model") or "medium",
        maxchars=_clamp(g("maxchars"), 4, 60, 16),
        batchchars=_clamp(g("batchchars"), 200, 5000, 1200),
        offline=bool(g("offline")),
        voice=g("voice") or "",
        subchars=_clamp(g("subchars"), 10, 120, 50),
        kieusub=g("kieusub") or "hopbo",
        subfont=g("subfont") or "",
        chesub=bool(g("chesub")),
        auto2=bool(g("auto2")), auto3=bool(g("auto3")), auto4=bool(g("auto4")),
        thaytieng=bool(g("thaytieng")), cpu=bool(g("cpu")),
    )


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
        return _home("Ô Nguồn đang trống — mỗi dòng một file video.")
    jobs, errs = [], []
    for src in sources:
        title, job_steps, err = st.build(start, src, s)
        if err:
            errs.append(err)
        else:
            jobs.append((title, job_steps))
    if errs:
        # Có dòng hỏng thì KHÔNG xếp dòng nào — sửa xong bấm lại, khỏi lẫn nửa chừng.
        return _home(" · ".join(errs[:3]) + (" …" if len(errs) > 3 else ""))
    for title, job_steps in jobs:
        q.enqueue(title, job_steps)
    return _home()


@app.post("/luu")
async def luu(request: Request):
    save_settings(_settings_from_form(await request.form()))
    return _home()


@app.post("/giong-sao")
async def giong_sao(request: Request):
    """Nút ⭐ cạnh ô giọng đọc: ghim/bỏ ghim giọng ĐANG CHỌN lên đầu danh sách.
    Tiện thể lưu luôn cài đặt đang điền trên form (khỏi mất khi trang tải lại)."""
    form = await request.form()
    s = _settings_from_form(form)
    v = (form.get("voice") or "").strip()
    if not v:
        return _home("Chọn một giọng trong danh sách rồi bấm ⭐ để ghim/bỏ ghim.")
    stars = [x for x in load_settings().get("voice_stars", []) if isinstance(x, str)]
    if v in stars:
        stars.remove(v)
    else:
        stars.insert(0, v)
    save_settings({**s, "voice_stars": stars})
    return _home()


@app.post("/tiep")
async def tiep(base: str = Form(...)):
    title, job_steps, err = st.resume(base, load_settings())
    if err:
        return _home(err)
    q.enqueue(title, job_steps)
    return _home()


@app.post("/buoc")
async def buoc(base: str = Form(...), key: str = Form(...)):
    title, job_steps, err = st.single(base, key, load_settings())
    if err:
        return _home(err)
    q.enqueue(title, job_steps)
    return _home()


# ── Điều khiển hàng đợi ──────────────────────────────────────────────────────
@app.post("/hangdoi/pause")
async def hd_pause():
    q.pause()
    return _home()


@app.post("/hangdoi/resume")
async def hd_resume():
    q.resume()
    return _home()


@app.post("/hangdoi/skip")
async def hd_skip():
    q.skip_current()
    return _home()


@app.post("/hangdoi/stop")
async def hd_stop():
    q.stop_all()
    return _home()


@app.post("/hangdoi/bo/{jid}")
async def hd_bo(jid: int):
    q.remove(jid)
    return _home()


@app.post("/hangdoi/power")
async def hd_power(request: Request):
    """Ô “Xong hết thì ngủ/tắt máy” — htmx gửi lên là trả lại ngay khối hàng đợi."""
    form = await request.form()
    power.arm(bool(form.get("on")), form.get("mode") or "")
    if request.headers.get("hx-request"):
        return templates.TemplateResponse(request, "_queue.html", _queue_ctx())
    return _home()


# ── Xoá output: CHỈ đưa vào Thùng rác, có xác nhận ở trình duyệt ─────────────
@app.post("/xoa")
async def xoa(base: str = Form(...)):
    if not st.is_base(base):
        return _home(f"Tên không hợp lệ: {base}")
    if q.busy():
        return _home("Hàng đợi đang chạy — dừng hết trước rồi hãy xoá (file có thể đang được ghi).")
    files = st.files_of(base)
    if not files:
        return _home(f"{base}: không thấy file nào trong output.")
    ok, fail = st.recycle(files, on_log=q.note)
    q.note(f"🗑 {base}: đã đưa {ok} mục vào Thùng rác"
           + (f", {fail} mục KHÔNG xoá được" if fail else "")
           + " — khôi phục: mở Thùng rác Windows.")
    return _home(f"{base}: {fail} mục không đưa vào Thùng rác được — xem nhật ký."
                 if fail else "")


@app.post("/xoa-het")
async def xoa_het():
    if q.busy():
        return _home("Hàng đợi đang chạy — dừng hết trước rồi hãy xoá (file có thể đang được ghi).")
    try:
        files = list(OUTPUT_DIR.iterdir())
    except OSError:
        files = []
    if not files:
        return _home("Thư mục output đang trống.")
    ok, fail = st.recycle(files, on_log=q.note)
    q.note(f"🗑 Đã đưa {ok} mục của output vào Thùng rác"
           + (f", {fail} mục KHÔNG xoá được" if fail else "")
           + " — khôi phục: mở Thùng rác Windows.")
    return _home(f"{fail} mục không đưa vào Thùng rác được — xem nhật ký." if fail else "")


@app.post("/mo-thumuc")
async def mo_thumuc():
    OUTPUT_DIR.mkdir(exist_ok=True)
    try:
        os.startfile(str(OUTPUT_DIR))          # noqa: S606 — máy cục bộ, cố ý
    except Exception as e:
        return _home(f"Không mở được thư mục: {e}")
    return _home()


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
