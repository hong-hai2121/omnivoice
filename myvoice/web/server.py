"""Bảng điều khiển web cho myvoice — FastAPI + HTMX.

Chạy:  myvoice\\chay_web.bat      (hoặc)
       venv\\Scripts\\python.exe -m myvoice.web.server

Server này điều khiển máy thật (ffmpeg, GPU, Firefox, xoá file) nên CHỈ nghe
trên 127.0.0.1 — không có chế độ mở ra mạng LAN. Vẫn giữ một token trong cookie
để trang web lạ đang mở trong cùng trình duyệt không gọi được vào đây.

Nhật ký chạy in thẳng ra cửa sổ console của server (không còn panel nhật ký).
"""

from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Form, Request
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               RedirectResponse)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

if __package__ in (None, ""):        # chạy thẳng file: python web/server.py
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    __package__ = "myvoice.web"

from . import core, steps as steps_mod          # noqa: E402
from .jobs import log, runner                   # noqa: E402

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


# ── Context dùng chung ──────────────────────────────────────────────────────
# Trang Home ghép cả hai khối (giống view "Home (đầy đủ)" bên GUI) nên hai hàm
# này là NGUỒN DUY NHẤT: sửa một chỗ, cả Home lẫn trang riêng cùng đổi.
def _script_ctx() -> dict:
    _, tts_err = core.tts_settings()
    return {"pipe": core.load_pipeline(), "tts_error": tts_err,
            "next_episode": core.next_episode(), "prefix": core.load_prefix(),
            "skip_episodes": core.load_skip_episodes(),
            "shutdown_delay": core.gui.SHUTDOWN_DELAY_MIN}


def _voice_ctx() -> dict:
    web = core.load_web_settings()
    out_wav = web.get("output") or str(core.OUTPUT_DIR / "output.wav")
    voices = core.list_voices()
    return {
        "opts": core.load_options(), "web": web, "voices": voices,
        # Chưa chọn giọng bao giờ → lấy mục đầu danh sách, đúng như combobox của GUI.
        "current_voice": web.get("voice") or (voices[0]["name"] if voices else ""),
        "effects": core.list_effects(),
        "ngang_sources": [core.NGANG_SOURCE_ALL] + core.list_ngang_sources(),
        "effect_none": core.EFFECT_NONE,
        "sub_modes": [core.SUB_MODE_SRT, core.SUB_MODE_BURN],
        "input_txt": web.get("input") or str(core.SCRIPT_DIR / "input.txt"),
        "output_wav": out_wav, "has_audio": Path(out_wav).exists(),
        "voice_dir": str(core.VOICE_DIR),
        "tiktok_episode": core.thumbnail_episode() + 1,
    }


# ── Trang chủ: Home (view "🏠 Home (đầy đủ)" bên GUI) ───────────────────────
@app.get("/", response_class=HTMLResponse)
def page_home(request: Request):
    return _page(request, "home.html", active="home", q=runner.state(),
                 **_script_ctx(), **_voice_ctx())


# ── Trang Tạo kịch bản (view "script" bên GUI) ──────────────────────────────
@app.get("/kichban", response_class=HTMLResponse)
def page_script(request: Request):
    return _page(request, "script.html", active="script", q=runner.state(),
                 **_script_ctx())


def _save_pipe_from_form(form) -> dict:
    """Nhớ cài đặt quy trình mỗi lần bấm chạy — y như GUI (_save_pipe_settings)."""
    pipe = core.load_pipeline()
    for k in ("model", "speed"):
        if form.get(k):
            pipe[k] = str(form[k])
    for k in ("auto2", "auto3", "auto_tts", "seo", "shutdown"):
        pipe[k] = k in form
    core.save_pipeline(pipe)
    return pipe


# Chuỗi chính ①→②→③→giọng. Mỗi nấc có một ô "⛓ tự động chạy tiếp"; ô tắt thì
# chuỗi DỪNG ở đó, y như GUI. SEO + thumbnail là tuỳ chọn đi kèm bước ② (var_seo).
_STAGES = ["recognize", "translate", "input", "tts"]
_GATES = {"translate": "auto2", "input": "auto3", "tts": "auto_tts"}


def _chain_from(start: str, pipe: dict) -> list[str]:
    steps: list[str] = []
    begin = _STAGES.index(start) if start in _STAGES else 0
    for i, name in enumerate(_STAGES[begin:]):
        if i > 0 and not pipe.get(_GATES[name]):
            break
        steps.append(name)
    if pipe.get("seo") and "translate" in steps:
        pos = steps.index("input") + 1 if "input" in steps else len(steps)
        steps[pos:pos] = ["seo", "thumbnail"]
    return steps


@app.post("/kichban/chay")
async def run_script(request: Request):
    form = await request.form()
    start = str(form.get("start", "recognize"))
    if start not in _STAGES:
        start = "recognize"
    pipe = _save_pipe_from_form(form)
    if "shutdown" in form:
        log("⏻ Ô “xong thì tắt máy” chỉ có tác dụng bên GUI — bản web không tự tắt máy.")

    lines = [s.strip() for s in str(form.get("sources", "")).splitlines() if s.strip()]
    if not lines:
        log("⚠️ Chưa nhập link hoặc đường dẫn file nào.")
        return _back(request, "/kichban")

    chain = _chain_from(start, pipe)
    force = bool(form.get("force"))
    steps_mod.cleanup_tmp()
    for src in lines:
        built, err = steps_mod.build_steps(chain, source=src, force=force)
        if err:
            log(f"⛔ {err}")
            break
        runner.enqueue(steps_mod.title_for(src, "", chain), built)
    return _back(request, "/kichban")


@app.post("/kichban/reset")
def reset_pipeline():
    core.save_pipeline(dict(core.PIPE_DEFAULTS))
    log("↺ Đã đặt lại cài đặt quy trình về mặc định.")
    return RedirectResponse("/kichban", status_code=303)


@app.post("/kichban/tapboqua")
def save_skip(skip: str = Form("")):
    nums = core.save_skip_episodes(skip)
    log(f"⏭ Tập bỏ qua: {', '.join(map(str, nums)) or '(không có)'}")
    return RedirectResponse("/kichban", status_code=303)


@app.post("/kichban/mocau")
def save_prefix(prefix: str = Form("")):
    core.save_prefix(prefix)
    log("💾 Đã lưu câu mở đầu gửi Gemini.")
    return RedirectResponse("/kichban", status_code=303)


# ── Trang Giọng nói (view "voice" bên GUI: TTS + video) ─────────────────────
@app.get("/giongnoi", response_class=HTMLResponse)
def page_voice(request: Request):
    return _page(request, "voice.html", active="voice", q=runner.state(),
                 **_voice_ctx())


@app.post("/giongnoi")
async def run_voice(request: Request):
    """Một form, nhiều nút: Chạy · Dựng lại ngang/dọc/tiktok. Bấm nút nào cũng LƯU
    cài đặt trước rồi mới chạy — đúng thói quen của GUI."""
    form = await request.form()
    _save_opts_from_form(form)
    core.save_web_settings({
        "mode": str(form.get("mode", "clone")),
        "voice": str(form.get("voice", "")),
        "instruct": str(form.get("instruct", "")),
        "input": str(form.get("input_txt", "")),
        "output": str(form.get("output_wav", "")),
    })

    action = str(form.get("action", "run"))
    rebuild = action if action in ("ngang", "doc", "tiktok") else ""
    built, err = steps_mod.tts_steps(
        input_txt=str(form.get("input_txt", "")),
        output_wav=str(form.get("output_wav", "")),
        from_gemini=bool(form.get("from_gemini")) and not rebuild,
        reuse=bool(form.get("reuse")),
        rebuild=rebuild,
        episode=str(form.get("tiktok_episode", "")))
    if err:
        log(f"⛔ {err}")
    else:
        runner.enqueue(built[0].label, built)
    return _back(request, "/giongnoi")


@app.get("/giongnoi/nghe")
def play_audio(file: str = ""):
    """Phát audio ngay trong trình duyệt — bản web của nút “🔊 Nghe thử”.
    Chỉ mở file nằm trong myvoice/ (chặn đọc lung tung ngoài dự án)."""
    try:
        path = Path(file).resolve()
        path.relative_to(core.BASE_DIR.resolve())
    except (ValueError, OSError):
        return JSONResponse({"error": "đường dẫn không hợp lệ"}, status_code=400)
    if not path.is_file():
        return JSONResponse({"error": "chưa có file"}, status_code=404)
    return FileResponse(str(path))


@app.post("/giongnoi/yeuthich/{kind}")
def toggle_favorite(kind: str, request: Request, name: str = Form("")):
    """Nút ☆/★ cạnh giọng mẫu và hiệu ứng."""
    if kind == "voice":
        on = core.toggle_voice_favorite(name)
    elif kind == "effect":
        on = core.toggle_effect_favorite(name)
    else:
        return JSONResponse({"error": "loại không hợp lệ"}, status_code=400)
    log(f"{'★' if on else '☆'} {name}")
    return _back(request, "/giongnoi")


@app.post("/giongnoi/xoaketqua")
def clear_output(confirm: str = Form("")):
    """Bản web của nút “🗑 Xóa output”: mọi thứ vào THÙNG RÁC Windows (khôi phục
    được), file trong kịch_bản/ được tạo lại bản rỗng. Đòi tick xác nhận."""
    if not confirm:
        log("⚠️ Chưa tick xác nhận → không xoá gì.")
        return RedirectResponse("/giongnoi", status_code=303)

    out_items = list(core.OUTPUT_DIR.iterdir()) if core.OUTPUT_DIR.exists() else []
    kb_files = [p for p in core.SCRIPT_DIR.iterdir() if p.is_file()] \
        if core.SCRIPT_DIR.exists() else []
    ep_dirs = core.gui.episode_dirs()
    if not (out_items or kb_files or ep_dirs):
        log("Không có gì để xoá.")
        return RedirectResponse("/giongnoi", status_code=303)

    bin_ = core.gui.App._send_to_recycle_bin
    out_ok, out_fail = bin_(out_items)
    ep_ok, ep_fail = bin_(ep_dirs)
    kb_ok, kb_fail = bin_(kb_files)

    emptied = 0
    for p in kb_files:
        if p.exists():          # chưa vào được Thùng rác → GIỮ NGUYÊN, không ghi đè
            log(f"Giữ nguyên (chưa vào Thùng rác được): {p.name}")
            continue
        try:
            if p.suffix.lower() == ".docx":
                from docx import Document
                Document().save(str(p))
            else:
                p.write_text("", encoding="utf-8")
            emptied += 1
        except Exception as e:
            log(f"Không tạo lại được {p.name}: {e}")

    log(f"🗑 Vào Thùng rác: {out_ok} mục output, {ep_ok} thư mục tập, {kb_ok} file "
        f"kịch_bản; tạo lại {emptied} bản rỗng; lỗi {out_fail + ep_fail + kb_fail}.")
    return RedirectResponse("/giongnoi", status_code=303)


# ── Trang Nhận diện (view "recog" bên GUI: bảng tập + 5 nút hàng loạt) ──────
_BATCH_BUTTONS = {
    "recognize": ("① Nhận diện các link rồi ngưng", ["recognize"]),
    "translate": ("② Dịch + tạo input.txt", ["translate", "input"]),
    "seo":       ("③ Gửi SEO (Gemini)", ["seo"]),
    "thumbnail": ("④ Tạo thumbnail (ngang + dọc)", ["thumbnail"]),
    "tts":       ("⑤ Tạo giọng + video", ["tts"]),
}
# Tập "đủ điều kiện" cho từng nút khi KHÔNG tick tập nào — giống cách GUI lọc.
_BATCH_READY = {
    "translate": lambda s: s["recognize"] and not s["input"],
    "seo":       lambda s: s["translate"] and not s["seo"],
    "thumbnail": lambda s: s["seo"] and not s["thumbnail"],
    "tts":       lambda s: s["input"] and not s["video_ngang"],
}


@app.get("/nhandien", response_class=HTMLResponse)
def page_recog(request: Request):
    return _page(request, "recog.html", active="recog", pipe=core.load_pipeline(),
                 q=runner.state(), rows=core.episode_rows(),
                 step_labels=core.STEP_LABELS, buttons=_BATCH_BUTTONS)


@app.get("/partials/recog-table", response_class=HTMLResponse)
def partial_recog_table(request: Request):
    return templates.TemplateResponse(
        request, "_recog_table.html",
        {"rows": core.episode_rows(), "step_labels": core.STEP_LABELS})


@app.post("/nhandien")
async def run_recog(request: Request):
    form = await request.form()
    action = str(form.get("action", ""))
    if action not in _BATCH_BUTTONS:
        return RedirectResponse("/nhandien", status_code=303)

    pipe = core.load_pipeline()
    for k in ("model", "speed"):
        if form.get(k):
            pipe[k] = str(form[k])
    core.save_pipeline(pipe)

    label, chain = _BATCH_BUTTONS[action]
    force = bool(form.get("force"))
    steps_mod.cleanup_tmp()

    if action == "recognize":
        lines = [s.strip() for s in str(form.get("sources", "")).splitlines() if s.strip()]
        if not lines:
            log("⚠️ Chưa nhập link hoặc file nào để nhận diện.")
            return RedirectResponse("/nhandien", status_code=303)
        for src in lines:
            built, err = steps_mod.build_steps(chain, source=src, force=force)
            if err:
                log(f"⛔ {err}")
                break
            runner.enqueue(steps_mod.title_for(src, "", chain), built)
        return RedirectResponse("/nhandien", status_code=303)

    picked = [str(e) for e in form.getlist("tap")]
    rows = core.episode_rows()
    if picked:
        targets = [r for r in rows if r["episode"] in picked]
    else:
        ready = _BATCH_READY[action]
        targets = [r for r in rows if ready(r["steps"])]
        log(f"ℹ️ Không tick tập nào → chạy {len(targets)} tập đủ điều kiện cho “{label}”.")
    if not targets:
        log(f"⚠️ Không có tập nào để chạy “{label}”.")
        return RedirectResponse("/nhandien", status_code=303)

    for r in sorted(targets, key=lambda r: int(r["episode"])):
        built, err = steps_mod.build_steps(chain, source=r["source"],
                                           episode=r["episode"], force=force)
        if err:
            log(f"⛔ {err}")
            break
        runner.enqueue(steps_mod.title_for("", r["episode"], chain), built)
    return RedirectResponse("/nhandien", status_code=303)


# ── Trang Thumbnail ─────────────────────────────────────────────────────────
@app.get("/thumbnail", response_class=HTMLResponse)
def page_thumbnail(request: Request, tap: str = ""):
    rows = core.episode_rows()
    chosen = tap or (rows[0]["episode"] if rows else "")
    title = ""
    folder = core.episode_folder(chosen) if chosen else None
    if folder:
        blocks = core.seo_blocks(folder, chosen)
        if blocks:                      # gợi ý sẵn tiêu đề SEO của tập đang chọn
            title = blocks["title"]
    return _page(request, "thumbnail.html", active="thumbnail", rows=rows,
                 chosen=chosen, suggested=title, photos=core.list_photos(),
                 q=runner.state(), episode_number=core.thumbnail_episode())


@app.post("/thumbnail")
async def make_thumbnail(request: Request):
    form = await request.form()
    title = str(form.get("title", "")).strip()
    episode = str(form.get("episode", "")).strip()
    if not title:
        log("⚠️ Chưa nhập tiêu đề cho thumbnail.")
        return RedirectResponse("/thumbnail", status_code=303)
    built = steps_mod.thumbnail_steps(title, episode=episode,
                                      photo=str(form.get("photo", "")),
                                      doc=bool(form.get("doc")))
    runner.enqueue(f"Thumbnail tập {episode or '—'}", built)
    return RedirectResponse(f"/thumbnail?tap={episode}", status_code=303)


@app.get("/tap/{episode}/thumbnail")
def episode_thumbnail(episode: str):
    folder = core.episode_folder(episode)
    if folder:
        png = folder / f"thumbnail{episode}.png"
        if png.exists():
            return FileResponse(str(png))
    return JSONResponse({"error": "chưa có thumbnail"}, status_code=404)


@app.get("/tap/{episode}/thumbnail-doc")
def episode_thumbnail_doc(episode: str):
    folder = core.episode_folder(episode)
    if folder:
        png = folder / f"thumbnail{episode}_dọc.png"
        if png.exists():
            return FileResponse(str(png))
    return JSONResponse({"error": "chưa có thumbnail dọc"}, status_code=404)


# ── Hàng đợi ────────────────────────────────────────────────────────────────
@app.get("/partials/queue", response_class=HTMLResponse)
def partial_queue(request: Request):
    return templates.TemplateResponse(request, "_queue.html", {"q": runner.state()})


def _back(request: Request, fallback: str = "/") -> RedirectResponse:
    """Về đúng trang vừa bấm — nút hàng đợi có mặt ở nhiều trang."""
    ref = request.headers.get("referer", "")
    return RedirectResponse(ref or fallback, status_code=303)


@app.post("/hangdoi/{action}")
def queue_action(action: str, request: Request):
    {"pause": runner.pause, "resume": runner.resume,
     "skip": runner.skip_current, "stop": runner.stop_all}.get(action, lambda: None)()
    return _back(request)


@app.post("/hangdoi/bo/{job_id}")
def queue_remove(job_id: int, request: Request):
    runner.remove(job_id)
    return _back(request)


# ── Cài đặt ─────────────────────────────────────────────────────────────────
_NUM_KEYS = {"chunk": int, "cut_target": float, "cut_min": float, "cut_max": float,
             "doc_percent": int, "tiktok_percent": int, "tiktok_caption_pos": int,
             "tiktok_music_db": int, "sub_max_chars": int}
_TEXT_KEYS = ["ngang_speed", "doc_speed", "tiktok_speed", "ngang_source", "effect",
              "sub_mode", "sub_model"]


def _save_opts_from_form(form) -> dict:
    """Ghi các tuỳ chọn có trên form vào taogiong_options.json (chung với GUI)."""
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
    return opts


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
def _url(port: int) -> str:
    return f"http://127.0.0.1:{port}/?token={quote(TOKEN)}"


def _open_browser_when_ready(port: int) -> None:
    """Chờ server nghe được rồi mới mở trình duyệt (chạy ở luồng riêng).

    Bật server = có ngay giao diện, không phải copy địa chỉ. Ai không muốn mở
    (vd GUI tự mở lấy) thì đặt MYVOICE_WEB_NO_OPEN=1.
    """
    import socket
    import time
    import webbrowser

    deadline = time.time() + 20
    while time.time() < deadline:
        with socket.socket() as s:
            s.settimeout(0.3)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                webbrowser.open(_url(port))
                return
        time.sleep(0.3)
    log("⚠️ Server chưa sẵn sàng — mở trình duyệt thủ công bằng địa chỉ ở trên.")


def main() -> None:
    import threading

    import uvicorn

    port = int(os.environ.get("MYVOICE_WEB_PORT", "8765"))

    print("=" * 68)
    print("  myvoice — bảng điều khiển web")
    print(f"  Địa chỉ: {_url(port)}")
    print("  Chỉ mở được trên máy này (không nghe trên mạng LAN).")
    print(f"  Token nằm ở: {TOKEN_FILE}  (xoá file này = đổi token)")
    print("  Nhật ký chạy hiện ngay trong cửa sổ này. Đóng cửa sổ = tắt server.")
    print("=" * 68)

    if os.environ.get("MYVOICE_WEB_NO_OPEN", "").strip() in ("", "0", "false"):
        threading.Thread(target=_open_browser_when_ready, args=(port,),
                         daemon=True).start()

    log("🌐 Bảng điều khiển web đã sẵn sàng.")
    # CHỈ 127.0.0.1: server chạy ffmpeg/GPU/Firefox và xoá file ngay trên máy bạn.
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
