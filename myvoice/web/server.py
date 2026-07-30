"""Bảng điều khiển web cho myvoice — FastAPI + HTMX.

Chạy:  myvoice\\chay_web.bat      (hoặc)
       venv\\Scripts\\python.exe -m myvoice.web.server

Server này điều khiển máy thật (ffmpeg, GPU, Firefox, xoá file) nên mặc định
nghe trên LAN kèm một token: mở lần đầu bằng đường dẫn có ?token=... in ra ở
console, token được nhớ trong cookie. Đừng mở cổng này ra Internet.
"""

from __future__ import annotations

import asyncio
import json
import os
import queue
import secrets
import socket
import sys
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Form, Request
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               RedirectResponse, StreamingResponse)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

if __package__ in (None, ""):        # chạy thẳng file: python web/server.py
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    __package__ = "myvoice.web"

from . import core, steps as steps_mod          # noqa: E402
from .jobs import log, log_bus, runner          # noqa: E402

WEB_DIR = core.WEB_DIR
TOKEN_FILE = WEB_DIR / "token.txt"
COOKIE = "mv_token"


def _token() -> str:
    """Token cố định giữa các lần chạy (đổi = xoá web/token.txt)."""
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

app = FastAPI(title="myvoice — bảng điều khiển")
app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))


# ── Bảo vệ bằng token ───────────────────────────────────────────────────────
@app.middleware("http")
async def require_token(request: Request, call_next):
    if request.url.path.startswith("/static"):
        return await call_next(request)
    given = request.query_params.get("token") or request.cookies.get(COOKIE, "")
    if not secrets.compare_digest(given, TOKEN):
        return HTMLResponse(
            "<h1>Cần token</h1><p>Mở bằng đường dẫn có <code>?token=…</code> "
            "in ở cửa sổ console lúc khởi động server.</p>", status_code=401)
    response = await call_next(request)
    if request.query_params.get("token"):     # ghi nhớ để lần sau khỏi kèm token
        response.set_cookie(COOKIE, TOKEN, max_age=30 * 86400, httponly=True,
                            samesite="lax")
    return response


def _page(request: Request, name: str, **ctx) -> HTMLResponse:
    ctx.setdefault("active", "")
    return templates.TemplateResponse(request, name, ctx)


# ── Trang Tiến độ ───────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def page_progress(request: Request):
    return _page(request, "progress.html", active="progress",
                 rows=core.episode_rows(), step_labels=core.STEP_LABELS,
                 single_steps=steps_mod.SINGLE_STEPS)


@app.get("/partials/episodes", response_class=HTMLResponse)
def partial_episodes(request: Request):
    return templates.TemplateResponse(
        request, "_episodes.html",
        {"rows": core.episode_rows(), "step_labels": core.STEP_LABELS,
         "single_steps": steps_mod.SINGLE_STEPS})


@app.get("/tap/{episode}/thumbnail")
def episode_thumbnail(episode: str):
    folder = core.episode_folder(episode)
    if folder:
        png = folder / f"thumbnail{episode}.png"
        if png.exists():
            return FileResponse(str(png))
    return JSONResponse({"error": "chưa có thumbnail"}, status_code=404)


# ── Trang Chạy ──────────────────────────────────────────────────────────────
@app.get("/chay", response_class=HTMLResponse)
def page_run(request: Request):
    pipe = core.load_pipeline()
    _, tts_err = core.tts_settings()
    return _page(request, "run.html", active="run", pipe=pipe, q=runner.state(),
                 step_choices=steps_mod.STEP_CHOICES, tts_error=tts_err,
                 next_episode=core.next_episode())


@app.post("/chay")
def run_sources(sources: str = Form(""), steps: list[str] = Form(default=[]),
                force: str = Form(""), model: str = Form(""), speed: str = Form("")):
    """Xếp hàng: mỗi dòng nguồn (link/file) thành một việc chạy các bước đã chọn."""
    lines = [s.strip() for s in sources.splitlines() if s.strip()]
    chosen = [k for k, _ in steps_mod.STEP_CHOICES if k in steps]
    if not lines:
        log("⚠️ Chưa nhập link hoặc đường dẫn file nào.")
        return RedirectResponse("/chay", status_code=303)
    if not chosen:
        log("⚠️ Chưa chọn bước nào để chạy.")
        return RedirectResponse("/chay", status_code=303)

    if model or speed:                       # nhớ cài đặt quy trình (chung với GUI)
        pipe = core.load_pipeline()
        if model:
            pipe["model"] = model
        if speed:
            pipe["speed"] = speed
        core.save_pipeline(pipe)

    steps_mod.cleanup_tmp()
    for src in lines:
        built, err = steps_mod.build_steps(chosen, source=src, force=bool(force))
        if err:
            log(f"⛔ {err}")
            break
        runner.enqueue(steps_mod.title_for(src, "", chosen), built)
    return RedirectResponse("/chay", status_code=303)


@app.post("/tap/{episode}/buoc/{step}")
def run_single_step(episode: str, step: str, force: str = Form("")):
    """Chạy lại một bước cho một tập đã có (nút trong bảng tiến độ)."""
    if step not in steps_mod.SINGLE_STEPS:
        return JSONResponse({"error": "bước không hợp lệ"}, status_code=400)
    source = ""
    for key, entry in core.gui.load_manifest().items():
        if str(entry.get("episode", "")).zfill(2) == str(episode).zfill(2):
            source = entry.get("source", key)
            break
    built, err = steps_mod.build_steps([step], source=source, episode=episode,
                                       force=bool(force))
    if err:
        log(f"⛔ {err}")
    else:
        runner.enqueue(steps_mod.title_for("", episode, [step]), built)
    return RedirectResponse("/", status_code=303)


# ── Hàng đợi ────────────────────────────────────────────────────────────────
@app.get("/partials/queue", response_class=HTMLResponse)
def partial_queue(request: Request):
    return templates.TemplateResponse(request, "_queue.html", {"q": runner.state()})


@app.post("/hangdoi/{action}")
def queue_action(action: str):
    {"pause": runner.pause, "resume": runner.resume,
     "skip": runner.skip_current, "stop": runner.stop_all}.get(action, lambda: None)()
    return RedirectResponse("/chay", status_code=303)


@app.post("/hangdoi/bo/{job_id}")
def queue_remove(job_id: int):
    runner.remove(job_id)
    return RedirectResponse("/chay", status_code=303)


# ── Nhật ký (SSE) ───────────────────────────────────────────────────────────
@app.get("/nhatky/stream")
async def log_stream(request: Request):
    q = log_bus.subscribe()

    async def gen():
        try:
            for _, line in log_bus.tail(200):
                yield f"data: {json.dumps(line)}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    _, line = q.get_nowait()
                    yield f"data: {json.dumps(line)}\n\n"
                except queue.Empty:
                    await asyncio.sleep(0.4)
                    yield ": ping\n\n"      # giữ kết nối sống qua proxy/điện thoại
        finally:
            log_bus.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


# ── Cài đặt ─────────────────────────────────────────────────────────────────
_NUM_KEYS = {"chunk": int, "cut_target": float, "cut_min": float, "cut_max": float,
             "doc_percent": int, "tiktok_percent": int, "tiktok_caption_pos": int,
             "tiktok_music_db": int, "sub_max_chars": int}
_TEXT_KEYS = ["ngang_speed", "doc_speed", "tiktok_speed", "ngang_source", "effect",
              "sub_mode", "sub_model"]


@app.get("/caidat", response_class=HTMLResponse)
def page_settings(request: Request):
    return _page(request, "settings.html", active="settings",
                 opts=core.load_options(), pipe=core.load_pipeline(),
                 web=core.load_web_settings(), voices=core.list_voices(),
                 effects=[core.EFFECT_NONE] + core.list_effects(),
                 ngang_sources=core.list_ngang_sources(),
                 sub_modes=[core.SUB_MODE_SRT, core.SUB_MODE_BURN])


@app.post("/caidat")
async def save_settings(request: Request):
    form = await request.form()
    opts = core.load_options()
    # Checkbox không tick thì trình duyệt KHÔNG gửi gì cả, nên không thể suy ra
    # "vắng mặt = tắt": làm vậy sẽ tắt luôn các tuỳ chọn chỉ có bên GUI (from_gemini,
    # bring_front…). Mỗi checkbox trên trang kèm một hidden "_bools" khai tên mình,
    # nên ở đây chỉ đụng đúng những ô trang này thật sự hiển thị.
    for k in form.getlist("_bools"):
        opts[str(k)] = str(k) in form
    for k, cast in _NUM_KEYS.items():
        if form.get(k, "") != "":
            try:
                opts[k] = cast(str(form[k]).replace(",", "."))
            except ValueError:
                pass
    for k in _TEXT_KEYS:
        if k in form:
            opts[k] = str(form[k])
    core.save_options(opts)

    pipe = core.load_pipeline()
    for k in ("model", "speed"):
        if form.get(k):
            pipe[k] = str(form[k])
    core.save_pipeline(pipe)

    core.save_web_settings({"mode": str(form.get("mode", "clone")),
                            "voice": str(form.get("voice", "")),
                            "instruct": str(form.get("instruct", ""))})
    log("💾 Đã lưu cài đặt (dùng chung với GUI).")
    return RedirectResponse("/caidat", status_code=303)


# ── Copy SEO ────────────────────────────────────────────────────────────────
@app.get("/seo", response_class=HTMLResponse)
def page_seo(request: Request, tap: str = ""):
    rows = [r for r in core.episode_rows() if r["steps"]["seo"]]
    chosen = tap or (rows[0]["episode"] if rows else "")
    blocks = None
    if chosen:
        folder = core.episode_folder(chosen)
        if folder:
            blocks = core.seo_blocks(folder, chosen)
    return _page(request, "seo.html", active="seo", rows=rows,
                 chosen=chosen, blocks=blocks)


# ── Khởi động ───────────────────────────────────────────────────────────────
def _lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def main() -> None:
    import uvicorn

    port = int(os.environ.get("MYVOICE_WEB_PORT", "8765"))
    url = f"http://{_lan_ip()}:{port}/?token={quote(TOKEN)}"
    print("=" * 68)
    print("  myvoice — bảng điều khiển web")
    print(f"  Máy này   : http://127.0.0.1:{port}/?token={quote(TOKEN)}")
    print(f"  Điện thoại: {url}")
    print(f"  Token nằm ở: {TOKEN_FILE}  (xoá file này = đổi token)")
    print("=" * 68)
    log("🌐 Bảng điều khiển web đã sẵn sàng.")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


if __name__ == "__main__":
    main()
