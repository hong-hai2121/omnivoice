"""Bảng điều khiển web cho myvoice — FastAPI + HTMX.

Chạy:  myvoice\\chay_web.bat      (hoặc)
       venv\\Scripts\\python.exe -m myvoice.web.server

Server này điều khiển máy thật (ffmpeg, GPU, Firefox, xoá file) nên CHỈ nghe
trên 127.0.0.1 — không có chế độ mở ra mạng LAN. Vẫn giữ một token trong cookie
để trang web lạ đang mở trong cùng trình duyệt không gọi được vào đây.

Nhật ký chạy in thẳng ra cửa sổ console của server. Riêng hàng đợi ĐĂNG có thêm
vài dòng cuối ngay trong khối hàng đợi trên trang, và /api/nhatky-dang để GUI
(tiến trình khác) chiếu sang ô Nhật ký của nó.
"""

from __future__ import annotations

import os
import secrets
import subprocess
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
    __package__ = "myvoice.web"

from . import core, power, steps as steps_mod              # noqa: E402
from .jobs import (fb_log, fb_runner, log, runner,          # noqa: E402
                   upload_log, upload_runner)

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


def _asset_v() -> str:
    """Dấu phiên bản gắn vào URL của app.css/app.js — xem base.html.

    StaticFiles không gửi Cache-Control, nên trình duyệt tự đoán và có thể lấy
    lại bản trong cache mà không thèm hỏi server: sửa app.js xong mở trang vẫn
    chạy code cũ, nút bấm không ăn gì, mà nhìn HTML thì thấy đúng nút mới nên
    rất khó đoán ra. Lấy mtime làm phiên bản: file đổi là URL đổi là tải lại.
    """
    try:
        d = WEB_DIR / "static"
        return str(int(max((d / n).stat().st_mtime for n in ("app.css", "app.js"))))
    except Exception:
        return "0"


templates.env.globals["asset_v"] = _asset_v


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
    ctx.setdefault("on_home", False)
    # Hàng đợi ĐĂNG chạy song song với hàng đợi chính nên trang nào cũng cần thấy.
    ctx.setdefault("qu", upload_runner.state())
    ctx.setdefault("ulog", upload_log.tail(8))
    ctx.setdefault("upct", upload_log.percent)
    # Hàng đợi Facebook chạy song song với hai hàng trên → trang nào cũng thấy.
    ctx.setdefault("qf", fb_runner.state())
    ctx.setdefault("flog", fb_log.tail(8))
    ctx.setdefault("slots", core.upload_slots_text())
    # Ô "🌙 Xong hết thì cho máy ngủ" nằm trong khối hàng đợi → trang nào có khối
    # đó cũng cần trạng thái này.
    ctx.setdefault("sleepq", power.watcher.state())
    # Đồng hồ 📊 VRAM cũng nằm trong khối hàng đợi — đưa vào từ lượt tải đầu,
    # khỏi đợi htmx làm mới 2 giây sau mới hiện (có cache 5s nên không tốn gì).
    ctx.setdefault("vram", _vram())
    return templates.TemplateResponse(request, name, ctx)


# ── Context dùng chung ──────────────────────────────────────────────────────
# Trang Home gom cả bốn khối (giống view "Home (đầy đủ)" bên GUI) nên bốn hàm
# này là NGUỒN DUY NHẤT: sửa một chỗ, cả Home lẫn trang riêng cùng đổi.
def _script_ctx() -> dict:
    _, tts_err = core.tts_settings()
    return {"pipe": core.load_pipeline(), "tts_error": tts_err,
            "next_episode": core.next_episode(), "prefix": core.load_prefix(),
            "skip_episodes": core.load_skip_episodes(),
            "shutdown_delay": core.gui.SHUTDOWN_DELAY_MIN,
            # Link/file đã chạy lần trước — ô Nguồn hiện thành nút bấm lại.
            "src_history": core.source_history(),
            # Chế độ đánh số đã lưu — trang Tạo kịch bản riêng không có khối
            # Thumbnail (nơi đặt radio) nên vẫn phải theo lựa chọn đã nhớ.
            "epsrc": core.load_web_settings().get("epsrc", "manual")}


def _kieusubs() -> list[dict]:
    """Kho kiểu phụ đề (scripts/kieusub.py) — lỗi cũng không được sập trang."""
    try:
        import kieusub
        return kieusub.danh_sach_web()
    except Exception:
        return []


def _sub_fonts() -> list[dict]:
    """Danh sách font chọn được (kèm ảnh xem trước) — lỗi thì trả rỗng."""
    try:
        import kieusub
        return kieusub.danh_sach_font_web()
    except Exception:
        return []


def _voice_ctx() -> dict:
    web = core.load_web_settings()
    out_wav = web.get("output") or str(core.OUTPUT_DIR / "output.wav")
    voices = core.list_voices()
    # Chưa chọn giọng bao giờ (hoặc giọng đã lưu không còn trong myvoice/voice/)
    # → lấy giọng có ★. Đổi ★ sang giọng khác là mặc định đi theo, khỏi sửa file.
    names = {v["name"] for v in voices}
    saved = str(web.get("voice", ""))
    starred = next((v["name"] for v in voices if v["fav"]), "")
    return {
        "opts": core.load_options(), "web": web, "voices": voices,
        "current_voice": (saved if saved in names
                          else starred or (voices[0]["name"] if voices else "")),
        "effects": core.list_effects(),
        "ngang_sources": [core.NGANG_SOURCE_ALL] + core.list_ngang_sources(),
        "effect_none": core.EFFECT_NONE,
        "sub_modes": [core.SUB_MODE_SRT, core.SUB_MODE_BURN],
        # Kho kiểu phụ đề (scripts/kieusub_mau, dùng chung myvideo) — thẻ ảnh
        # chọn kiểu khi "vẽ cứng vào hình"; ảnh nằm ở static/kieusub.
        "kieusubs": _kieusubs(),
        "sub_fonts": _sub_fonts(),
        "input_txt": web.get("input") or str(core.SCRIPT_DIR / "input.txt"),
        "output_wav": out_wav, "has_audio": Path(out_wav).exists(),
        "voice_dir": str(core.VOICE_DIR),
        "tiktok_episode": core.thumbnail_episode() + 1,
    }


def _recog_ctx() -> dict:
    return {"rows": core.episode_rows(), "step_labels": core.STEP_LABELS}


def _upload_ctx() -> dict:
    """Khối "Đăng YouTube": cài đặt + danh sách chọn + tập đang chờ đăng.

    Tên kênh lấy từ CACHE, không gọi API ở đây — mở trang mà đi gọi mạng thì trang
    chậm theo đường truyền, mà thông tin này chỉ để xem.
    """
    chan_note = ""
    try:
        import dang_video_youtube as yt
        data = yt.load_video_cache()
        entry = data["channels"].get(data.get("current"))
        if entry:
            ch = entry["channel"]
            slot = core.next_publish_slot_text()
            chan_note = (f"Kênh: {ch['title']} · {ch['video_count']} video"
                         + (f" · khung giờ trống kế tiếp {slot}" if slot else ""))
    except Exception:
        pass
    return {"up": core.upload_settings(), "up_choices": core.upload_choices(),
            "pending": core.episodes_pending_upload(), "chan_note": chan_note}


def _thumb_ctx(tap: str = "") -> dict:
    rows = core.episode_rows()
    chosen = tap or (rows[0]["episode"] if rows else "")
    title = ""
    folder = core.episode_folder(chosen) if chosen else None
    if folder:
        blocks = core.seo_blocks(folder, chosen)
        if blocks:                      # gợi ý sẵn tiêu đề SEO của tập đang chọn
            title = blocks["title"]
    web = core.load_web_settings()
    return {"rows": rows, "chosen": chosen, "suggested": title,
            "photos": core.list_photos(), "episode_number": core.thumbnail_episode(),
            "missing": core.missing_episodes(),
            "epsrc": web.get("epsrc", "manual"),
            "thumb_photo": web.get("thumb_photo", ""),
            "thumb_doc": bool(web.get("thumb_doc", True))}


# ── Trang chủ: Home — MỌI nút chức năng (view "🏠 Home (đầy đủ)" bên GUI) ───
@app.get("/", response_class=HTMLResponse)
def page_home(request: Request):
    # Gộp bằng dict (không phải **a, **b) vì các phần dùng chung khoá "rows".
    # KHÔNG gọi _recog_ctx: khối "chạy hàng loạt theo tập" đã chuyển hẳn sang trang
    # /nhandien, mà gọi thừa thì episode_rows() bị quét hai lần mỗi lần mở Home.
    # on_home=True: ô "Số tập (chữ trên video)" hiện ở khối Thumbnail thay vì trong
    # khối Giọng nói (xem _field_tiktok_episode.html).
    ctx = {**_script_ctx(), **_voice_ctx(), **_thumb_ctx(), **_upload_ctx()}
    # Khối Đăng Facebook: danh sách tập chưa đăng Page + lịch đang chờ (đọc đĩa +
    # cache, không gọi mạng).
    ctx["fb"] = _fb_ctx()
    return _page(request, "home.html", active="home", q=runner.state(),
                 on_home=True, **ctx)


# ── Trang Tạo kịch bản (view "script" bên GUI) ──────────────────────────────
@app.get("/kichban", response_class=HTMLResponse)
def page_script(request: Request):
    return _page(request, "script.html", active="script", q=runner.state(),
                 **_script_ctx())


def _save_pipe_from_form(form) -> dict:
    """Nhớ cài đặt quy trình mỗi lần bấm chạy — y như GUI (_save_pipe_settings).

    KHÔNG đụng hai khoá "shutdown"/"sleep": trang web không có ô “xong thì tắt máy”,
    còn ô “🌙 xong thì cho máy ngủ” của nó chỉ nhớ trong bộ nhớ server chứ không ghi
    ra file — ghi đè mỗi lần chạy là âm thầm tắt cài đặt ⏻/🌙 của GUI.
    """
    pipe = core.load_pipeline()
    for k in ("model", "speed"):
        if form.get(k):
            pipe[k] = str(form[k])
    # KHÔNG đụng khoá "upload": ô tick đó nằm ở khối "Đăng YouTube", không có trên
    # form này. Checkbox vắng mặt bị hiểu là tắt → mỗi lần bấm chạy ở khối 1 sẽ âm
    # thầm tắt chế độ tự đăng.
    for k in ("auto2", "auto3", "auto_tts", "seo"):
        pipe[k] = k in form
    core.save_pipeline(pipe)
    return pipe


def _save_model_speed(form) -> dict:
    """Chỉ model + tốc độ. Dùng cho form hàng loạt — form đó KHÔNG có các ô ⛓,
    gọi _save_pipe_from_form sẽ tắt sạch chúng."""
    pipe = core.load_pipeline()
    for k in ("model", "speed"):
        if form.get(k):
            pipe[k] = str(form[k])
    core.save_pipeline(pipe)
    return pipe


def _upload_ready() -> bool:
    """Kiểm tra TRƯỚC khi xếp việc: đủ thư viện + đã đăng nhập YouTube.

    Dùng cho các nút ĐĂNG NGAY (⑥ và “⬆ Đăng ngay các tập chưa đăng”): người dùng
    đang ngồi đó bấm, hỏng thì báo liền. Đồng thời đọc lại kênh: vừa nói rõ sẽ đăng
    lên kênh nào (một Gmail có thể nhiều kênh), vừa nạp cache các giờ đã hẹn để xếp
    khung 08:00/18:00 không bị trùng.

    KHÔNG dùng làm chốt cho chuỗi tự động — xem _auto_upload_wanted.
    """
    chan, err = core.refresh_channel()
    if err:
        upload_runner.note(f"⛔ Chưa đăng YouTube được: {err}")
        return False
    slot = core.next_publish_slot_text()
    upload_runner.note(
        f"⬆ Sẽ đăng lên kênh: {chan['title']} ({chan['id']}) — {chan['video_count']} video."
        + (f" Khung giờ trống kế tiếp: {slot}." if slot else ""))
    return True


def _auto_upload_wanted(chain: list[str]) -> bool:
    """Dựng xong video thì có NỐI việc đăng vào hàng đợi đăng không?

    Chỉ hỏi hai điều: ô “⬆ tự động đăng” có bật không, và chuỗi này có bước 'tts'
    không (việc đăng móc vào bước dựng video).

    KHÔNG chặn theo tình trạng đăng nhập như trước. Lý do: mẻ chạy đêm mất hàng
    GIỜ, mà chốt đăng nhập lại kiểm ngay lúc bấm nút — chỉ cần một lần mạng chập
    hay token vừa hết hạn là cả mẻ mất luôn phần đăng, hàng đợi rỗng, máy ngủ theo
    lịch, sáng ra video nằm im trong thư mục mà nhật ký báo “xong” hết. Đăng nhập
    hỏng thật thì run_upload.py phát hiện ĐÚNG LÚC đăng và việc đó báo lỗi đỏ ở
    hàng đợi đăng — thấy được, chứ không âm thầm biến mất.
    """
    if not (bool(core.load_pipeline().get("upload")) and "tts" in chain):
        return False
    ok, err = core.upload_check()
    if not ok:
        upload_runner.note(
            f"⚠️ Tự động đăng đang BẬT nhưng hiện chưa đăng nhập YouTube được: {err} "
            "→ vẫn xếp việc đăng sau khi dựng xong; tới lúc đó còn hỏng thì việc "
            "đăng sẽ báo lỗi ở đây (không bỏ qua im lặng).")
    return True


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

    lines = [s.strip() for s in str(form.get("sources", "")).splitlines() if s.strip()]
    if not lines:
        # Chưa có gì để chạy thì KHÔNG lưu gì cả — nếu lưu, một lần bấm nhầm sẽ
        # tắt hết các ô ⛓ đang bật.
        log("⚠️ Chưa nhập link hoặc đường dẫn file nào.")
        return _back(request, "/kichban")

    core.remember_sources(lines)      # để lần sau bấm lại, khỏi đi tìm/gõ lại
    pipe = _save_pipe_from_form(form)
    chain = _chain_from(start, pipe)
    force = bool(form.get("force"))
    upload = _auto_upload_wanted(chain)
    # LÀM BÙ: bắt đầu từ số tập đã chọn rồi vét tiếp các số kênh còn thiếu; hết thì
    # cấp số mới. Tính TRƯỚC cho cả mẻ để ghi ra nhật ký, khỏi phải đoán.
    start_ep = str(form.get("episode", "")).strip()
    if start_ep and not start_ep.isdecimal():
        log(f"⚠️ Số tập '{start_ep}' không phải số → bỏ qua, để tự cấp số.")
        start_ep = ""
    mode = "auto" if str(form.get("epsrc", "manual")) == "auto" else "manual"
    plan = core.plan_episodes(lines, start_ep, mode=mode)
    if mode == "auto":
        log("🔖 Tự làm bù: lấy tập kênh còn thiếu từ số bé nhất, hết thì nối sau "
            f"tập mới nhất kênh đã có ({core.latest_channel_episode()}).")
    if start_ep or mode == "auto":
        log("🔖 Cấp số tập: " + " · ".join(
            f"link {i + 1} → " + (f"tập {ep}" if ep else "tập cũ (nguồn đã chạy)")
            for i, ep in enumerate(plan)))

    steps_mod.cleanup_tmp()
    for src, ep in zip(lines, plan):
        built, err = steps_mod.build_steps(chain, source=src, episode=ep,
                                           force=force, upload=upload)
        if err:
            log(f"⛔ {err}")
            break
        runner.enqueue(steps_mod.title_for(src, ep, chain), built)
    return _back(request, "/kichban")


@app.post("/kichban/luu")
async def save_pipe_only(request: Request):
    """Nút 💾 của khối Tạo kịch bản: chỉ lưu, không xếp việc nào vào hàng đợi."""
    _save_pipe_from_form(await request.form())
    log("💾 Đã lưu cài đặt quy trình (model · tốc độ · các ô ⛓).")
    return _saved(request, "/kichban")


@app.get("/api/tep-nguon")
def api_source_files():
    """File audio/video đang nằm trong các thư mục tải về — cho nút 📂 Thêm từ máy.

    Server chỉ chạy trên 127.0.0.1 (xem đầu file) nên đọc thẳng đĩa máy này là
    đúng chỗ người dùng vừa tải file về; trình duyệt không tự đọc được đường dẫn
    thật của file nên phải hỏi server.
    """
    return JSONResponse({"groups": core.list_download_files()})


@app.post("/kichban/xoalichsu")
def clear_source_history():
    """Nút 🗑 ở hàng “Gần đây”: quên các nguồn đã chạy, KHÔNG đụng ô đang nhập.

    Trả JSON chứ không redirect: khối Nguồn nằm trong form chạy chung nên nút này
    là type=button gọi ngầm bằng fetch (nếu để submit thì nó thành nút mặc định
    của form — bấm Enter ở ô “Số tập” hoá ra xoá lịch sử). Xem app.js.
    """
    core.clear_source_history()
    log("🗑 Đã xoá danh sách nguồn gần đây.")
    return JSONResponse({"ok": True})


@app.post("/kichban/reset")
def reset_pipeline():
    core.save_pipeline(dict(core.PIPE_DEFAULTS))
    log("↺ Đã đặt lại cài đặt quy trình về mặc định.")
    return RedirectResponse("/kichban", status_code=303)


@app.post("/kichban/tapboqua")
def save_skip(request: Request, skip: str = Form("")):
    nums = core.save_skip_episodes(skip)
    text = ", ".join(map(str, nums)) or "(không có)"
    log(f"⏭ Tập bỏ qua: {text}")
    # Mẩu trả về nhắc lại danh sách ĐÃ CHUẨN HOÁ — ô nhập vẫn giữ nguyên chữ vừa
    # gõ (không tải lại trang) nên đây là chỗ cho thấy server hiểu thành gì.
    return _saved(request, "/kichban", f"✓ Đã lưu: {text}")


@app.post("/kichban/mocau")
def save_prefix(request: Request, prefix: str = Form("")):
    core.save_prefix(prefix)
    log("💾 Đã lưu câu mở đầu gửi Gemini.")
    return _saved(request, "/kichban")


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
    _save_voice_from_form(form)

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


@app.post("/giongnoi/luu")
async def save_voice_only(request: Request):
    """Nút 💾 của khối Giọng nói & video: chỉ lưu, không tạo giọng."""
    _save_voice_from_form(await request.form())
    log("💾 Đã lưu cài đặt giọng nói + video.")
    return _saved(request, "/giongnoi")


@app.get("/giongnoi/kieusub-xemtruoc")
def kieusub_xemtruoc(kieu: str = "hopbo", font: str = "", mau: str = "",
                     vitri: str = "", khung: str = "", cochu: str = "",
                     dong: int = 2, mauvien: str = "", bengang: str = ""):
    """Ảnh xem thử TỔ HỢP kiểu + font + màu chữ/viền + cỡ chữ + số dòng (+ vị trí).

    khung=ngang → khung 16:9 nguyên vẹn để thấy VỊ TRÍ chữ trên màn hình
    (vitri = % chiều cao từ đáy). cochu = % phóng to/thu nhỏ chữ, dong = số
    dòng mỗi lần hiện chữ, bengang = % bề ngang dòng chữ (đổi chỗ xuống dòng).
    Render bằng đúng libass sẽ burn; mỗi tổ hợp chỉ render một lần (cache
    xt_* trong static/kieusub) nên lần đầu ~1-3 giây, các lần sau tức thì."""
    try:
        import kieusub
        p = kieusub.ve_xemtruoc(kieu, font, mau, vitri,
                                ca_khung=(khung == "ngang"),
                                cochu=cochu, dong=dong, mau_vien=mauvien,
                                bengang=bengang)
    except Exception:
        p = None
    if not p:
        return JSONResponse({"error": "không vẽ được ảnh xem thử"}, status_code=404)
    return FileResponse(str(p))


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
    "upload":    ("⑥ Đăng YouTube", ["upload"]),
}
# Tập "đủ điều kiện" cho từng nút khi KHÔNG tick tập nào — giống cách GUI lọc.
_BATCH_READY = {
    "translate": lambda s: s["recognize"] and not s["input"],
    "seo":       lambda s: s["translate"] and not s["seo"],
    "thumbnail": lambda s: s["seo"] and not s["thumbnail"],
    "tts":       lambda s: s["input"] and not s["video_ngang"],
    "upload":    lambda s: s["video_ngang"] and s["seo"] and not s["upload"],
}


@app.post("/nhandien/luu")
async def save_recog_only(request: Request):
    """Nút 💾 của khối chạy hàng loạt (chỉ có model + tốc độ để nhớ)."""
    _save_model_speed(await request.form())
    log("💾 Đã lưu model + tốc độ nhận diện.")
    return _saved(request, "/nhandien")


@app.get("/nhandien", response_class=HTMLResponse)
def page_recog(request: Request):
    return _page(request, "recog.html", active="recog", q=runner.state(),
                 pipe=core.load_pipeline(), **_recog_ctx())


@app.get("/partials/recog-table", response_class=HTMLResponse)
def partial_recog_table(request: Request):
    return templates.TemplateResponse(
        request, "_recog_table.html",
        {"rows": core.episode_rows(), "step_labels": core.STEP_LABELS})


def _run_resume(request: Request, form) -> RedirectResponse:
    """Nút ⏩ Chạy tiếp: mỗi tập MỘT việc chạy liền mạch ĐÚNG các bước còn thiếu
    (vd tập dịch xong rồi thì chỉ chạy input → SEO → thumbnail → giọng + video).
    Bản web của '▶ Chạy tiếp tập đang chọn' bên GUI, nhưng chạy được nhiều tập."""
    picked = [str(e) for e in form.getlist("tap")]
    rows = core.episode_rows()
    if picked:
        targets = [r for r in rows if r["episode"] in picked]
    else:
        targets = [r for r in rows if r["done_count"] < r["total_steps"]]
        log(f"ℹ️ Không tick tập nào → chạy tiếp {len(targets)} tập còn việc.")

    # Tôn trọng ô '⬆ tự động đăng' của quy trình: bật thì dựng xong video là nối
    # việc đăng, y như chuỗi ①→③. (Mỗi tập thiếu một kiểu nên chốt 'tts' xét lại
    # theo từng tập ở dưới; ở đây chỉ hỏi ô tick.)
    upload_on = _auto_upload_wanted(["tts"])

    steps_mod.cleanup_tmp()
    queued = 0
    for r in sorted(targets, key=lambda r: int(r["episode"])):
        missing = core.missing_steps(r["steps"])
        if not missing:
            continue
        post = [k for k in missing if k in core.POST_STEPS]
        if post and len(post) == len(missing):
            # Chỉ còn việc ĐĂNG LẺ (Short / Facebook). Chỉ làm cho tập được TICK rõ
            # ràng: "chạy tiếp tất cả" mà tự đăng Short cho mọi tập cũ thì vừa đốt
            # quota vừa rải Short cũ lên kênh. Hai việc đi hai hàng đợi riêng như
            # sau khi dựng video (queue_after_build).
            if not picked:
                continue
            if "short" in post:
                steps_mod.queue_short(r["episode"])
                queued += 1
            if "facebook" in post:
                steps_mod.queue_facebook(r["episode"])
                queued += 1
            continue
        if "recognize" in missing and not r["source"]:
            log(f"⚠️ Tập {r['episode']}: chưa có bản nhận diện mà không rõ link gốc "
                "→ dán lại link vào ô nhận diện để chạy tập này.")
            continue
        built, err = steps_mod.resume_steps(missing, r["source"], r["episode"],
                                            upload=upload_on)
        if err:
            log(f"⛔ {err}")
            continue
        runner.enqueue(f"Tập {r['episode']} — ⏩ chạy tiếp "
                       f"({len(missing)} bước thiếu)", built)
        queued += 1
    if not queued:
        log("✅ Không có tập nào cần chạy tiếp — các tập đã đủ bước.")
    return _back(request, "/nhandien")


@app.post("/nhandien")
async def run_recog(request: Request):
    form = await request.form()
    action = str(form.get("action", ""))
    if action == "resume":
        _save_model_speed(form)      # nhớ model + tốc độ như các nút khác
        return _run_resume(request, form)
    if action not in _BATCH_BUTTONS:
        return _back(request, "/nhandien")

    _save_model_speed(form)
    label, chain = _BATCH_BUTTONS[action]
    force = bool(form.get("force"))
    steps_mod.cleanup_tmp()

    if action == "recognize":
        lines = [s.strip() for s in str(form.get("sources", "")).splitlines() if s.strip()]
        if not lines:
            log("⚠️ Chưa nhập link hoặc file nào để nhận diện.")
            return _back(request, "/nhandien")
        for src in lines:
            built, err = steps_mod.build_steps(chain, source=src, force=force)
            if err:
                log(f"⛔ {err}")
                break
            runner.enqueue(steps_mod.title_for(src, "", chain), built)
        return _back(request, "/nhandien")

    if action == "upload" and not _upload_ready():
        return _back(request, "/nhandien")

    picked = [str(e) for e in form.getlist("tap")]
    rows = core.episode_rows()
    if picked:
        targets = [r for r in rows if r["episode"] in picked]
    else:
        ready = _BATCH_READY[action]
        targets = [r for r in rows if ready(r["steps"])]
        log(f"ℹ️ Không tick tập nào → chạy {len(targets)} tập đủ điều kiện cho “{label}”.")

    if action == "upload":
        # Loại tập mà KÊNH đã có (đăng tay từ trước, không có youtube_upload.json).
        on_channel = core.episodes_on_channel()
        skipped = [r["episode"] for r in targets if int(r["episode"]) in on_channel]
        targets = [r for r in targets if int(r["episode"]) not in on_channel]
        if skipped:
            upload_runner.note(f"♻ Bỏ qua {len(skipped)} tập kênh đã có: "
                               f"{', '.join(skipped)}.")

    if not targets:
        log(f"⚠️ Không có tập nào để chạy “{label}”.")
        return _back(request, "/nhandien")

    # Nút ⑤ dựng video hàng loạt cũng phải TÔN TRỌNG ô '⬆ tự động đăng', y như chuỗi
    # ①→③ và nút ⏩ chạy tiếp. Trước đây chỗ này quên truyền upload= nên bấm ⑤ là mẻ
    # đó KHÔNG BAO GIỜ tự đăng dù ô tick đang bật — dựng xong, hàng đợi rỗng, máy ngủ.
    upload = _auto_upload_wanted(chain)

    for r in sorted(targets, key=lambda r: int(r["episode"])):
        # Đăng đi hàng đợi RIÊNG (song song), các bước khác đi hàng đợi chính.
        if action == "upload":
            steps_mod.queue_upload(r["episode"])
            continue
        built, err = steps_mod.build_steps(chain, source=r["source"],
                                           episode=r["episode"], force=force,
                                           upload=upload)
        if err:
            log(f"⛔ {err}")
            break
        runner.enqueue(steps_mod.title_for("", r["episode"], chain), built)
    return _back(request, "/nhandien")


# ── Khối Đăng YouTube ───────────────────────────────────────────────────────
def _save_upload_from_form(form) -> dict:
    """Lưu cài đặt đăng + ô 'tự động đăng'. Mọi checkbox trên form này đều hiển thị
    nên suy 'vắng mặt = tắt' ở đây là đúng."""
    cfg = core.save_upload_settings({
        "category_id": str(form.get("category_id", "") or "22"),
        "privacy": str(form.get("privacy", "") or "schedule"),
        "made_for_kids": "made_for_kids" in form,
        "contains_ai": "contains_ai" in form,
    })
    pipe = core.load_pipeline()
    pipe["upload"] = "upload" in form
    core.save_pipeline(pipe)
    return cfg


@app.post("/dangyoutube/luu")
async def save_upload(request: Request):
    form = await request.form()
    cfg = _save_upload_from_form(form)
    auto = "BẬT" if core.load_pipeline().get("upload") else "TẮT"
    log(f"💾 Đã lưu cài đặt đăng YouTube (tự động đăng: {auto} · danh mục "
        f"{cfg.get('category_id')} · {cfg.get('privacy')} · trẻ em: "
        f"{cfg.get('made_for_kids')} · AI: {cfg.get('contains_ai')}).")
    return _saved(request, "/", f"✓ Đã lưu — tự động đăng: {auto}")


@app.post("/dangyoutube/chay")
async def run_upload_now(request: Request):
    """Nút '⬆ Đăng ngay': lưu cài đặt rồi xếp các tập chưa đăng vào hàng đợi đăng."""
    _save_upload_from_form(await request.form())
    if not _upload_ready():
        return _back(request, "/")
    pending = core.episodes_pending_upload()
    # Hai dòng này đi qua upload_runner.note để LỌT vào nhật ký hàng đợi đăng: bấm
    # nút mà không có tập nào đủ điều kiện thì phải thấy LÝ DO ngay trên trang/GUI,
    # chứ không phải im lìm như hỏng.
    if not pending:
        upload_runner.note("⚠️ Không có tập nào cần đăng (thiếu video/SEO, "
                           "hoặc kênh đã có hết).")
        return _back(request, "/")
    upload_runner.note(f"⬆ Xếp {len(pending)} tập vào hàng đợi đăng: {', '.join(pending)}")
    for ep in pending:
        steps_mod.queue_upload(ep)
    return _back(request, "/")


# Luồng đang chạy phiên đăng nhập Google (None = không có). Chỉ cho MỘT phiên: hai
# lần bấm là hai cửa sổ Google, cái sau ghi đè token của cái trước.
_login_thread: threading.Thread | None = None


def _do_youtube_login() -> None:
    """Thân của luồng đăng nhập. Mọi dòng đều qua upload_runner.note để hiện ngay
    trong khối hàng đợi đăng (trang tự hỏi lại mỗi 2 giây) — người bấm nút thấy được
    tiến trình, chứ luồng nền mà im lìm thì không biết còn sống hay đã chết."""
    chan, err = core.youtube_login(upload_runner.note)
    if err:
        upload_runner.note(f"⛔ Đăng nhập YouTube thất bại: {err}")
        return
    slot = core.next_publish_slot_text()
    upload_runner.note(
        f"✅ Đã đăng nhập YouTube — kênh: {chan['title']} ({chan['id']}) — "
        f"{chan['video_count']} video."
        + (f" Khung giờ trống kế tiếp: {slot}." if slot else ""))


@app.post("/dangyoutube/dangnhap")
def youtube_login(request: Request):
    """Nút '🔑 Đăng nhập YouTube': mở cửa sổ Google ngay trên máy này.

    Chạy ở LUỒNG NỀN rồi trả trang về liền. Đăng nhập mất từ vài giây tới vài phút
    (chọn tài khoản, cấp quyền) — chờ trong handler là uvicorn treo, trang đứng hình
    và chính cái tab đang mở cũng không tải nổi.
    """
    global _login_thread
    if _login_thread is not None and _login_thread.is_alive():
        upload_runner.note("⏳ Cửa sổ đăng nhập Google đang mở sẵn — làm nốt ở cửa "
                           "sổ đó (bấm hai lần là hai phiên, phiên sau đè token "
                           "phiên trước).")
        return _back(request, "/")
    upload_runner.note("🔑 Đang mở trình duyệt để đăng nhập YouTube — chọn tài khoản "
                       "và bấm Cho phép trong cửa sổ vừa hiện ra (chờ tối đa 5 phút).")
    _login_thread = threading.Thread(target=_do_youtube_login, daemon=True,
                                     name="youtube-login")
    _login_thread.start()
    return _back(request, "/")


# ── Khối Đăng Facebook (Page MimiAudio) ─────────────────────────────────────
def _fb_picked(form) -> list[str]:
    """Các tập được tick trong bảng; không tick ô nào = tất cả tập chưa đăng."""
    return [str(e) for e in form.getlist("fbtap")]


def _fb_ctx(note: str = "") -> dict:
    """Ngữ cảnh khối Đăng Facebook: danh sách chờ + lịch Page (đọc đĩa, không gọi
    mạng) kèm trạng thái hàng đợi.

    `busy` để khối tự gọi lại /partials/facebook mỗi 6s trong lúc hàng đợi
    Facebook còn việc: bấm 🔄 xong là bảng tự vẽ lại theo lịch mới đọc được, khỏi
    phải nhớ tải lại trang. Hết việc thì bản vẽ mới không còn hx-get nên vòng làm
    mới tự tắt."""
    ctx = core.facebook_pending()
    ctx["busy"] = fb_runner.busy()
    ctx["note"] = note
    return ctx


def _fb_block(request: Request, note: str, fallback: str = "/"):
    """Trả lời cho ba nút của khối: htmx thì thay CHÍNH khối đó bằng bản mới vẽ
    (kèm mẩu trả lời cạnh nút), không có JS thì chuyển hướng như cũ."""
    if request.headers.get("hx-request"):
        return templates.TemplateResponse(request, "_form_facebook.html",
                                          {"fb": _fb_ctx(note)})
    return _back(request, fallback)


@app.get("/partials/facebook", response_class=HTMLResponse)
def partial_facebook(request: Request):
    """Khối Đăng Facebook vẽ lại — vòng tự làm mới của #fbblock gọi vào đây."""
    return templates.TemplateResponse(request, "_form_facebook.html",
                                      {"fb": _fb_ctx()})


@app.post("/dangfacebook/chay")
async def run_facebook_schedule(request: Request):
    """Nút '📘 Đăng các tập chưa đăng': chạy dang_video_facebook.py trong hàng đợi
    ĐĂNG (kế hoạch + tiến trình hiện ở nhật ký hàng đợi đăng)."""
    picked = _fb_picked(await request.form())
    fb_runner.note("📘 Xếp việc lên lịch Facebook (9h/19h)"
                   + (f" — các tập: {', '.join(picked)}." if picked
                      else " — tất cả tập chưa đăng."))
    fb_runner.enqueue("📘 Lên lịch Facebook (9h/19h)",
                      steps_mod.facebook_steps(dry_run=False, episodes=picked))
    return _fb_block(request, "✓ Đã xếp việc — theo dõi ở khối Hàng đợi")


@app.post("/dangfacebook/xemtruoc")
async def preview_facebook_schedule(request: Request):
    """Nút '🔍 Xem kế hoạch': chạy bản --dry-run — chỉ in kế hoạch, không đăng."""
    picked = _fb_picked(await request.form())
    # light=True: việc xem trước không được tính vào heavy_busy — kẻo ô 🌙 (mặc
    # định bật) thấy "bận rồi rảnh" mà đếm 3 phút cho máy ngủ chỉ vì một cú bấm.
    fb_runner.enqueue("📘 Kế hoạch Facebook (xem trước, không đăng)",
                      steps_mod.facebook_steps(dry_run=True, episodes=picked),
                      light=True)
    return _fb_block(request, "🔍 Đang xem — kế hoạch hiện ở khối Hàng đợi")


@app.post("/dangfacebook/quet")
def scan_facebook_page(request: Request):
    """Nút '🔄 Cập nhật lịch Page': đọc lại bài đã đăng + lịch đang chờ + số phận
    từng bài script đã xếp (bị xoá / bị dời giờ), rồi cập nhật sổ. Bảng tập chưa
    đăng và bảng lịch vẽ lại theo — khối tự làm mới nên xong là thấy ngay.
    Cũng là việc nhẹ (chỉ gọi vài request đọc)."""
    fb_runner.enqueue("🔄 Cập nhật lịch Page Facebook",
                      steps_mod.facebook_steps(only_scan=True), light=True)
    return _fb_block(request, "🔄 Đang đọc lại lịch Page — bảng tự cập nhật khi xong")


@app.post("/dangfacebook/tudong")
async def toggle_facebook_auto(request: Request):
    """Ô "📘 Dựng xong thì tự lên lịch Facebook".

    Form này CHỈ có mỗi ô đó nên suy được "vắng mặt = bỏ tick" (giống ô 🌙)."""
    on = bool((await request.form()).get("on"))
    core.save_web_settings({"fb_auto": on})
    log("📘 Bật tự động lên lịch Facebook: dựng xong video tập nào là xếp lịch "
        "Page tập đó, chạy song song với đăng YouTube." if on
        else "📘 Đã tắt tự động lên lịch Facebook.")
    return _saved(request, "/",
                  "✓ Đã bật tự động lên lịch Facebook" if on
                  else "✓ Đã tắt tự động lên lịch Facebook")


# ── Trang Thumbnail ─────────────────────────────────────────────────────────
@app.get("/thumbnail", response_class=HTMLResponse)
def page_thumbnail(request: Request, tap: str = ""):
    return _page(request, "thumbnail.html", active="thumbnail", q=runner.state(),
                 **_thumb_ctx(tap))


def _save_thumb_from_form(form) -> None:
    """Nhớ tuỳ chọn khối Thumbnail. Mọi ô ở đây đều hiển thị trên form nên suy
    'checkbox vắng mặt = tắt' là đúng."""
    core.save_web_settings({
        "epsrc": "auto" if str(form.get("epsrc", "")) == "auto" else "manual",
        "thumb_photo": str(form.get("photo", "")),
        "thumb_doc": "doc" in form,
    })


@app.post("/thumbnail/luu")
async def save_thumb_only(request: Request):
    """Nút 💾 của khối Thumbnail: chỉ lưu tuỳ chọn, không tạo ảnh."""
    _save_thumb_from_form(await request.form())
    web = core.load_web_settings()
    log(f"💾 Đã lưu tuỳ chọn thumbnail (đánh số: {web['epsrc']} · ảnh nền: "
        f"{web['thumb_photo'] or 'ngẫu nhiên'} · bản dọc: "
        f"{'có' if web['thumb_doc'] else 'không'}).")
    return _saved(request, "/thumbnail")


@app.post("/thumbnail")
async def make_thumbnail(request: Request):
    form = await request.form()
    _save_thumb_from_form(form)     # bấm tạo ảnh cũng nhớ lựa chọn, như các khối khác
    title = str(form.get("title", "")).strip()
    # Số in lên ảnh lấy từ ô "Số tập" — ô đó phản ánh TẬP ĐANG LÀM (chế độ tự làm bù
    # điền số kênh còn thiếu, chế độ tự nhập thì bạn gõ). Ô "Tập" chỉ dùng để chọn
    # tập lấy sẵn tiêu đề SEO, và là nguồn dự phòng ở trang /thumbnail riêng (trang
    # đó không có ô "Số tập").
    episode = str(form.get("episode_manual", "")).strip()
    if not episode.isdecimal():
        episode = str(form.get("episode", "")).strip()
    episode = episode.zfill(2) if episode.isdecimal() else ""
    if not title:
        log("⚠️ Chưa nhập tiêu đề cho thumbnail.")
        return _back(request, "/thumbnail")
    if episode and not core.episode_folder(episode):
        log(f"ℹ️ Tập {episode} chưa có thư mục → ảnh lưu tạm vào kịch_bản/; "
            "quy trình sẽ tạo lại đúng chỗ khi chạy tập này.")
    built = steps_mod.thumbnail_steps(title, episode=episode,
                                      photo=str(form.get("photo", "")),
                                      doc=bool(form.get("doc")))
    runner.enqueue(f"Thumbnail tập {episode or '—'}", built)
    return _back(request, f"/thumbnail?tap={episode}")


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
@app.get("/api/trangthai")
def api_state():
    """Trạng thái gọn dạng JSON — cho cửa sổ bật server (myvoice/chay.py) biết còn
    việc đang chạy không, phục vụ ô '⏻ Tự động tắt máy khi xong'. Chỉ coi là RẢNH
    khi CẢ hàng đợi chính lẫn hàng đợi đăng YouTube đều hết việc.

    Kèm luôn trạng thái chế độ ngủ: ô 🌙 bên cửa sổ đó chỉ là công tắc từ xa của ô 🌙
    trên trang web, nên nó cần soi lại chỗ này để vẽ đúng tick + đếm ngược."""
    q = runner.state()
    sleep = power.watcher.state()
    return {
        # heavy_busy: việc "light" (xem kế hoạch Facebook…) không tính — kẻo ô ⏻
        # bên cửa sổ launcher coi đó là mẻ thật rồi hẹn tắt máy.
        "busy": runner.heavy_busy(),
        # Gộp hàng đợi Facebook vào đây: cửa sổ launcher chỉ đọc hai khoá này, mà
        # đang tải video lên Page thì TUYỆT ĐỐI không được tắt/ngủ máy.
        "upload_busy": upload_runner.heavy_busy() or fb_runner.heavy_busy(),
        "current": (q.get("current") or {}).get("title", ""),
        "pending": len(q.get("pending") or []),
        "sleep_armed": sleep["armed"],
        "sleep_left": sleep["left"],
    }


# ── 📊 VRAM còn trống (card 8GB dùng chung với Chrome — thấy sắp cạn thì khoan
# xếp mẻ mới, kẻo model tràn sang RAM chậm gấp chục lần). Hỏi nvidia-smi tối đa
# 5 giây/lần dù khối hàng đợi vẽ lại 2 giây/lần; máy không có nvidia thì thôi.
# Cùng khuôn với đồng hồ VRAM bên myvideo/web/server.py. #
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


@app.get("/partials/queue", response_class=HTMLResponse)
def partial_queue(request: Request):
    return templates.TemplateResponse(
        request, "_queue.html",
        {"q": runner.state(), "qu": upload_runner.state(),
         "ulog": upload_log.tail(8), "upct": upload_log.percent,
         "qf": fb_runner.state(), "flog": fb_log.tail(8),
         "sleepq": power.watcher.state(), "vram": _vram()})


@app.get("/api/nhatky-dang")
def api_upload_log(since: int = -1):
    """Nhật ký hàng đợi ĐĂNG cho tiến trình khác (GUI) đọc.

    since < 0 nghĩa là “chỉ lấy từ giờ trở đi”: trả về số thứ tự hiện tại kèm danh
    sách rỗng, để GUI vừa mở không đổ ra cả mẻ đăng từ hôm trước.
    """
    if since < 0:
        return JSONResponse({"next": upload_log.seq, "lines": [],
                             "percent": upload_log.percent})
    seq, lines = upload_log.since(since)
    return JSONResponse({"next": seq, "lines": lines, "percent": upload_log.percent})


@app.post("/hangdoi/ngu", response_class=HTMLResponse)
async def queue_sleep(request: Request):
    """Ô "🌙 Xong hết thì cho máy ngủ".

    Form này CHỈ có mỗi ô đó, nên ở đây suy được "vắng mặt = bỏ tick" — điều
    không làm được ở các form nhiều ô khác trong file này.

    Trả thẳng khối hàng đợi (htmx thay tại chỗ) để tick xong thấy đếm ngược ngay,
    không nhảy trang; trình duyệt tắt JS thì rơi về kiểu chuyển hướng như các nút
    hàng đợi khác.
    """
    form = await request.form()
    power.watcher.arm(bool(form.get("on")))
    if request.headers.get("HX-Request"):
        return partial_queue(request)
    return _back(request)


def _back(request: Request, fallback: str = "/") -> RedirectResponse:
    """Về đúng trang vừa bấm — nút hàng đợi có mặt ở nhiều trang."""
    ref = request.headers.get("referer", "")
    return RedirectResponse(ref or fallback, status_code=303)


def _saved(request: Request, fallback: str, note: str = "✓ Đã lưu"):
    """Trả lời cho các nút 💾 CHỈ LƯU: bấm qua htmx thì trả mẩu "✓ đã lưu" đặt
    vào ô .luunote cạnh nút — KHÔNG tải lại trang, khỏi mất chỗ đang cuộn và
    các ô đang gõ dở. Không có JS thì rơi về chuyển hướng như cũ."""
    if request.headers.get("hx-request"):
        return HTMLResponse(f'<span class="savenote">{note}</span>')
    return _back(request, fallback)


@app.post("/hangdoi/{action}")
def queue_action(action: str, request: Request):
    {"pause": runner.pause, "resume": runner.resume,
     "skip": runner.skip_current, "stop": runner.stop_all}.get(action, lambda: None)()
    return _back(request)


@app.post("/hangdoi/bo/{job_id}")
def queue_remove(job_id: int, request: Request):
    runner.remove(job_id)
    return _back(request)


@app.post("/hangdoidang/{action}")
def upload_queue_action(action: str, request: Request):
    """Điều khiển RIÊNG hàng đợi đăng — dừng việc tải lên không đụng gì tới việc
    dựng video đang chạy, và ngược lại."""
    {"pause": upload_runner.pause, "resume": upload_runner.resume,
     "skip": upload_runner.skip_current,
     "stop": upload_runner.stop_all}.get(action, lambda: None)()
    return _back(request)


@app.post("/hangdoidang/bo/{job_id}")
def upload_queue_remove(job_id: int, request: Request):
    upload_runner.remove(job_id)
    return _back(request)


@app.post("/hangdoifb/{action}")
def fb_queue_action(action: str, request: Request):
    """Điều khiển RIÊNG hàng đợi Facebook — nó chạy song song với hai hàng kia."""
    {"pause": fb_runner.pause, "resume": fb_runner.resume,
     "skip": fb_runner.skip_current,
     "stop": fb_runner.stop_all}.get(action, lambda: None)()
    return _back(request)


@app.post("/hangdoifb/bo/{job_id}")
def fb_queue_remove(job_id: int, request: Request):
    fb_runner.remove(job_id)
    return _back(request)


# ── Cài đặt ─────────────────────────────────────────────────────────────────
_NUM_KEYS = {"chunk": int,
             "doc_percent": int, "tiktok_percent": int, "tiktok_caption_pos": int,
             "tiktok_music_db": int, "sub_max_chars": int, "sub_dong": int}
_TEXT_KEYS = ["ngang_speed", "doc_speed", "tiktok_speed", "ngang_source", "effect",
              "sub_mode", "sub_model", "sub_kieu", "sub_font", "sub_mau",
              "sub_vitri", "sub_cochu", "sub_bengang", "sub_mau_vien"]


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


def _save_voice_from_form(form) -> None:
    """Toàn bộ cài đặt của khối Giọng nói: tuỳ chọn chung (taogiong_options.json)
    + chế độ/giọng/tệp của riêng bản web (web_settings.json)."""
    _save_opts_from_form(form)
    core.save_web_settings({
        "mode": str(form.get("mode", "clone")),
        "voice": str(form.get("voice", "")),
        "instruct": str(form.get("instruct", "")),
        "input": str(form.get("input_txt", "")),
        "output": str(form.get("output_wav", "")),
    })


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


# ── Trang Đăng bài: hai khối đăng của Home trên một màn hình ────────────────
@app.get("/dangbai", response_class=HTMLResponse)
def page_post(request: Request):
    """Trang riêng gom "Đăng YouTube" + "Đăng Facebook".

    Dựng bằng ĐÚNG hai hàm ngữ cảnh mà Home dùng (_upload_ctx / _fb_ctx) và đúng
    hai template đó, nên hai trang không thể lệch nhau: bấm bên nào cũng vào cùng
    hàng đợi, cùng file cài đặt. `pipe` phải có vì khối YouTube chứa ô "tự động
    đăng sau khi dựng xong" — ô ấy nằm trong taogiong_pipeline.json chứ không phải
    cài đặt đăng."""
    return _page(request, "dangbai.html", active="post", q=runner.state(),
                 pipe=core.load_pipeline(), fb=_fb_ctx(), **_upload_ctx())


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


def _port_busy(port: int, timeout: float = 0.4) -> bool:
    """Đã có ai nghe ở cổng này chưa (nhiều khả năng là server đang chạy sẵn)."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _should_open_browser() -> bool:
    """Có tự mở trình duyệt không. Đặt MYVOICE_WEB_NO_OPEN=1 để tắt — GUI dùng cờ
    này vì nó tự mở lấy, bật cả hai bên sẽ ra hai tab."""
    return os.environ.get("MYVOICE_WEB_NO_OPEN", "").strip() in ("", "0", "false")


def main() -> None:
    import uvicorn

    port = int(os.environ.get("MYVOICE_WEB_PORT", "8765"))

    # Bấm shortcut lần thứ hai khi server đã chạy: mở luôn trình duyệt vào bản đang
    # chạy rồi thoát, thay vì để uvicorn văng traceback "địa chỉ đang bận".
    if _port_busy(port):
        print(f"Bảng điều khiển đã chạy sẵn — mở lại: {_url(port)}")
        if _should_open_browser():
            import webbrowser
            webbrowser.open(_url(port))
        return

    print("=" * 68)
    print("  myvoice — bảng điều khiển web")
    print(f"  Địa chỉ: {_url(port)}")
    print("  Chỉ mở được trên máy này (không nghe trên mạng LAN).")
    print(f"  Token nằm ở: {TOKEN_FILE}  (xoá file này = đổi token)")
    print("  Nhật ký chạy hiện ngay trong cửa sổ này. Đóng cửa sổ = tắt server.")
    print("=" * 68)

    if _should_open_browser():
        threading.Thread(target=_open_browser_when_ready, args=(port,),
                         daemon=True).start()

    # Ảnh xem trước kiểu phụ đề còn thiếu (kiểu mới thêm) → tự vẽ nền sau,
    # không chặn khởi động; vẽ xong tải lại trang là thấy.
    try:
        import kieusub
        threading.Thread(target=kieusub.taomau_thieu, daemon=True).start()
    except Exception:
        pass

    log("🌐 Bảng điều khiển web đã sẵn sàng.")
    log("🌙 Mặc định BẬT “xong hết thì cho máy ngủ” — không muốn thì bỏ tick "
        "trên trang web.")
    # CHỈ 127.0.0.1: server chạy ffmpeg/GPU/Firefox và xoá file ngay trên máy bạn.
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
