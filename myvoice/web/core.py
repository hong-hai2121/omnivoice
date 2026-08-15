"""Cầu nối giữa bản web và code sẵn có trong myvoice/scripts.

Nguyên tắc: KHÔNG chép lại logic nghiệp vụ. Mọi thứ đã có trong
amain_taogiong_gui.py — hằng đường dẫn, cách dò thư mục tập, đọc/ghi cài đặt,
đọc SEO — đều import lại từ đó, nên GUI và web dùng CHUNG một nguồn sự thật:
sửa ở scripts/ là cả hai cùng đổi.

Import module GUI KHÔNG mở cửa sổ nào: khối `App().mainloop()` nằm trong
`if __name__ == "__main__"`, còn phần thân module chỉ định nghĩa hằng + hàm.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# ── Đường dẫn + sys.path (giống cách các script trong scripts/ tự dựng) ──────
WEB_DIR    = Path(__file__).resolve().parent
BASE_DIR   = WEB_DIR.parent                 # myvoice/
REPO_ROOT  = BASE_DIR.parent                # gốc repo (chứa package omnivoice + venv)
SCRIPTS_DIR = BASE_DIR / "scripts"
YOUTUBE_DIR = BASE_DIR / "YOUTUBE"
VENV_PYTHON = REPO_ROOT / "venv" / "Scripts" / "python.exe"

for _p in (str(REPO_ROOT), str(SCRIPTS_DIR), str(YOUTUBE_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import amain_taogiong_gui as gui   # noqa: E402  (phải sau khi vá sys.path)

# ── Re-export các hằng dùng nhiều, để phần web không phải gọi gui.X khắp nơi ─
SCRIPT_DIR   = gui.SCRIPT_DIR       # myvoice/kịch_bản
OUTPUT_DIR   = gui.OUTPUT_DIR
VOICE_DIR    = gui.VOICE_DIR
EFFECTS_DIR  = gui.EFFECTS_DIR
MUSIC_DIR    = gui.MUSIC_DIR
MANIFEST_FILE = gui.MANIFEST_FILE
ZH_DOCX_NAME = gui.ZH_DOCX_NAME
EFFECT_NONE  = gui.EFFECT_NONE
NGANG_SOURCE_ALL = gui.NGANG_SOURCE_ALL
SUB_MODE_SRT  = gui.SUB_MODE_SRT
SUB_MODE_BURN = gui.SUB_MODE_BURN
OPTS_DEFAULTS = gui.OPTS_DEFAULTS
PIPE_DEFAULTS = gui.PIPE_DEFAULTS
PREFIX_FILE   = gui.PREFIX_FILE

# Cài đặt CHỈ bản web dùng (chế độ giọng + giọng mẫu đang chọn). Để riêng file vì
# _save_opt_settings của GUI ghi đè taogiong_options.json bằng một dict cố định →
# khoá lạ thêm vào đó sẽ bị xoá mất ở lần GUI lưu kế tiếp.
WEB_SETTINGS_FILE = WEB_DIR / "web_settings.json"
WEB_DEFAULTS = dict(mode="clone", voice="", instruct="", input="", output="",
                    # Tuỳ chọn khối Thumbnail: chế độ đánh số tập cho cả lần chạy
                    # (auto = tự lấy tập kênh còn thiếu | manual = theo số tự nhập),
                    # ảnh nền mặc định, và có làm thêm bản dọc không.
                    epsrc="manual", thumb_photo="", thumb_doc=True,
                    # Link/đường dẫn đã chạy, mới nhất đứng đầu — ô Nguồn hiện
                    # thành nút bấm lại, khỏi phải đi tìm hay gõ lại.
                    src_history=[])

# ── Nguồn: lịch sử + kho file để chọn ───────────────────────────────────────
SRC_HISTORY_MAX = 15        # nhớ bấy nhiêu nguồn gần nhất
SRC_PICK_MAX = 60           # liệt kê tối đa bấy nhiêu file mỗi thư mục

# Hai chỗ file nguồn hay nằm: Downloads của Windows (tải tay về) và downloads_zh
# (mp3 do chính script tải từ link). Nút "Thêm từ máy" bên web đọc đúng hai chỗ này.
DOWNLOAD_DIRS = [
    (Path.home() / "Downloads", "Tải về"),
    (gui.DOWNLOAD_DIR, "mp3 tải từ link"),
]
MEDIA_EXTS = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wma",
              ".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv", ".ts", ".m4v"}

STEP_LABELS = [
    ("recognize",   "Nhận diện"),
    ("translate",   "Dịch"),
    ("input",       "input.txt"),
    ("seo",         "SEO"),
    ("thumbnail",   "Thumbnail"),
    ("audio",       "Giọng"),
    ("video_ngang", "Video ngang"),
    ("video_doc",   "Video dọc"),
    ("upload",      "Đăng"),
]

# Bước KHÔNG tính vào "tập đã xong": đăng YouTube là tuỳ chọn (mặc định tắt), tính
# vào sẽ làm mọi tập đã dựng xong từ trước hoá "còn việc".
DONE_EXCLUDE = {"upload"}


# ── Cài đặt ─────────────────────────────────────────────────────────────────
def load_options() -> dict:
    """Cài đặt TTS/video — CHUNG với GUI (taogiong_options.json)."""
    return gui.load_opt_settings()


def save_options(data: dict) -> None:
    gui.save_opt_settings(data)


def load_pipeline() -> dict:
    """Cài đặt quy trình (model nhận diện, tốc độ, auto…) — CHUNG với GUI."""
    return gui.load_pipe_settings()


def save_pipeline(data: dict) -> None:
    gui.save_pipe_settings(data)


def load_web_settings() -> dict:
    try:
        d = json.loads(WEB_SETTINGS_FILE.read_text(encoding="utf-8"))
        return {**WEB_DEFAULTS, **d} if isinstance(d, dict) else dict(WEB_DEFAULTS)
    except Exception:
        return dict(WEB_DEFAULTS)


def save_web_settings(data: dict) -> None:
    merged = {**load_web_settings(), **data}
    WEB_SETTINGS_FILE.write_text(json.dumps(merged, ensure_ascii=False, indent=2),
                                 encoding="utf-8")


# ── Nguồn đã dùng ───────────────────────────────────────────────────────────
def _src_label(src: str) -> str:
    """Nhãn ngắn cho nút bấm lại: link thì lấy tên miền + đuôi, file thì lấy tên."""
    s = src.strip()
    if s.lower().startswith(("http://", "https://")):
        rest = s.split("://", 1)[1]
        # Bỏ ?query và #fragment TRƯỚC khi tách: không thì "?spm=..." thành đoạn
        # cuối và nhãn hoá ra vô nghĩa.
        rest = rest.split("?", 1)[0].split("#", 1)[0]
        host, _, path = rest.partition("/")
        if host.startswith("www."):
            host = host[4:]
        tail = [p for p in path.split("/") if p]
        return f"{host}/{tail[-1]}" if tail else host
    return Path(s).name or s


def source_history() -> list[dict]:
    """Nguồn đã chạy, mới nhất trước — mỗi mục có `full` (điền vào ô) và `label`."""
    raw = load_web_settings().get("src_history") or []
    return [{"full": s, "label": _src_label(s)} for s in raw if isinstance(s, str) and s.strip()]


def remember_sources(lines: list[str]) -> None:
    """Đẩy các nguồn vừa chạy lên đầu lịch sử (bỏ trùng, cắt bớt phần cũ)."""
    old = [s for s in (load_web_settings().get("src_history") or []) if isinstance(s, str)]
    merged: list[str] = []
    for s in [*reversed([l.strip() for l in lines if l.strip()]), *old]:
        if s not in merged:
            merged.append(s)
    save_web_settings({"src_history": merged[:SRC_HISTORY_MAX]})


def clear_source_history() -> None:
    save_web_settings({"src_history": []})


def list_download_files() -> list[dict]:
    """File audio/video trong các thư mục tải về — mới nhất trước, theo từng nhóm.

    Chỉ đọc tên + cỡ + ngày sửa; server chạy ở 127.0.0.1 nên đọc thẳng đĩa máy
    này là đúng chỗ người dùng vừa tải file về.
    """
    groups = []
    for folder, label in DOWNLOAD_DIRS:
        try:
            items = [p for p in folder.iterdir()
                     if p.is_file() and p.suffix.lower() in MEDIA_EXTS]
        except Exception:
            continue                      # thư mục không có/không đọc được → bỏ qua
        items.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        files = []
        for p in items[:SRC_PICK_MAX]:
            st = p.stat()
            files.append({"name": p.name, "path": str(p),
                          "size": _human_size(st.st_size),
                          "when": _human_when(st.st_mtime)})
        groups.append({"label": label, "folder": str(folder),
                       "files": files, "more": max(0, len(items) - SRC_PICK_MAX)})
    return groups


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} GB"


def _human_when(ts: float) -> str:
    import time
    d = time.time() - ts
    if d < 3600:
        return f"{d / 60:.0f} phút trước"
    if d < 86400:
        return f"{d / 3600:.0f} giờ trước"
    if d < 86400 * 7:
        return f"{d / 86400:.0f} ngày trước"
    return time.strftime("%d/%m/%Y", time.localtime(ts))


# ── Danh sách lựa chọn cho các form ─────────────────────────────────────────
def list_voices() -> list[dict]:
    """Giọng mẫu kèm cờ yêu thích — ★ lên đầu, đúng thứ tự combobox bên GUI."""
    favs = gui.load_favorites()
    names = [gui.strip_star(v) for v in gui.list_voice_files()]
    rows = [{"name": n, "fav": n in favs} for n in names]
    rows.sort(key=lambda r: (not r["fav"], r["name"].lower()))
    return rows


def list_voice_names() -> list[str]:
    return [r["name"] for r in list_voices()]


def toggle_voice_favorite(name: str) -> bool:
    """Bật/tắt ★ cho một giọng — chung file voice_favorites.json với GUI."""
    favs = gui.load_favorites()
    name = gui.strip_star(name)
    if name in favs:
        favs.discard(name)
        on = False
    else:
        favs.add(name)
        on = True
    gui.save_favorites(favs)
    return on


def list_effects() -> list[dict]:
    favs = gui.load_effect_favorites()
    names = [gui.strip_star(e) for e in gui.list_effect_files()]
    rows = [{"name": n, "fav": n in favs} for n in names]
    rows.sort(key=lambda r: (not r["fav"], r["name"].lower()))
    return rows


def list_effect_names() -> list[str]:
    return [r["name"] for r in list_effects()]


def toggle_effect_favorite(name: str) -> bool:
    favs = gui.load_effect_favorites()
    name = gui.strip_star(name)
    if name in favs:
        favs.discard(name)
        on = False
    else:
        favs.add(name)
        on = True
    gui.save_effect_favorites(favs)
    return on


# ── Tập bỏ qua · câu mở đầu · số tập thumbnail (đều dùng chung file với GUI) ──
def load_skip_episodes() -> list[int]:
    return sorted(gui.load_skip_episodes())


def save_skip_episodes(text: str) -> list[int]:
    """Nhận chuỗi người dùng gõ ("7, 12 15") → lưu danh sách số tập bỏ qua."""
    nums = {int(n) for n in re.findall(r"\d+", text or "") if int(n) > 0}
    gui.save_skip_episodes(nums)
    return sorted(nums)


def load_prefix() -> str:
    return gui.load_prefix()


def save_prefix(text: str) -> None:
    gui.PREFIX_FILE.write_text((text or "").strip(), encoding="utf-8")


def thumbnail_episode() -> int:
    return gui.load_episode_number()


def save_thumbnail_episode(n: int) -> None:
    gui.save_episode_number(int(n))


def list_photos() -> list[str]:
    """Ảnh mèo dùng cho thumbnail (myvoice/Anh)."""
    try:
        import dien_tieu_de_thumbnail as renderer
        return sorted(p.name for p in renderer.list_photo_files(renderer.CAT_IMAGE_DIR))
    except Exception:
        return []


def list_ngang_sources() -> list[str]:
    return gui.list_ngang_sources()


def list_music() -> list[str]:
    return gui.list_music_files()


# ── Trạng thái từng tập ─────────────────────────────────────────────────────
def seo_docx_valid(seo_docx) -> bool:
    """SEO đã có tiêu đề đọc được chưa (bản port của App._seo_docx_valid)."""
    try:
        seo_docx = Path(seo_docx)
        if not seo_docx.exists():
            return False
        from seo_docx_parser import parse_seo_docx
        return bool((parse_seo_docx(str(seo_docx)).get("title") or "").strip())
    except Exception:
        return False


def folder_steps(folder, episode: str) -> dict:
    """Các bước ĐÃ XONG của 1 tập, suy từ file thực tế — bản port của
    App._folder_steps (cùng quy ước tên file, để web và GUI báo giống nhau)."""
    folder = Path(folder)
    zh = gui.find_zh_docx(folder)
    gem = folder / "gemini_result.docx"
    inp = folder / "input.txt"

    translate_done = False
    if gem.exists():
        try:
            import dich_gemini as g
            chunks = gui.read_zh_docx_chunks(zh) if zh else []
            if chunks:
                prior = g.read_results_docx(gem, len(chunks))
                translate_done = all(g.is_translation_done(r) for r in prior)
            else:
                translate_done = True   # không rõ số đoạn → coi gem tồn tại là xong
        except Exception:
            translate_done = True

    return {
        "recognize": bool(zh),
        "translate": translate_done,
        "input": inp.exists() and inp.stat().st_size > 0,
        "seo": seo_docx_valid(folder / "seoYoutube.docx"),
        "thumbnail": (folder / f"thumbnail{episode}.png").exists(),
        "audio": (folder / "output.wav").exists(),
        "video_ngang": (folder / "YOUTUBE.mp4").exists()
                        or bool(list(folder.glob("*_videodone.mp4"))),
        # "facebook <ngày giờ>.mp4": tên sau khi đăng YouTube (xem rename_doc) —
        # thiếu nhánh này là tập đã đăng lại hiện "chưa có video dọc".
        "video_doc": (folder / "facebook.mp4").exists()
                      or bool(list(folder.glob("facebook *.mp4")))
                      or bool(list(folder.glob("*_doc.mp4"))),
        # Đã đăng YouTube chưa — suy từ bản ghi mà dang_tap_youtube để lại.
        "upload": (folder / "youtube_upload.json").exists(),
    }


def missing_steps(steps: dict) -> list[str]:
    """Các bước runner CÒN THIẾU của 1 tập, đúng thứ tự chạy — cho nút ⏩ Chạy tiếp
    (bản web của '▶ Chạy tiếp tập đang chọn' bên GUI). Nhận dict của folder_steps.

    "tts" gộp giọng + video: chỉ cần thiếu audio HOẶC video ngang là phải chạy lại
    bước đó — _batch_run_tts tự dùng lại phần đã có, chỉ render phần thiếu.
    """
    out = [k for k in ("recognize", "translate", "input", "seo", "thumbnail")
           if not steps.get(k)]
    if not (steps.get("audio") and steps.get("video_ngang")):
        out.append("tts")
    return out


def episode_rows() -> list[dict]:
    """Mọi tập trong kịch_bản/ kèm trạng thái từng bước + nguồn (từ manifest)."""
    manifest = gui.load_manifest()
    by_episode = {}
    for key, entry in manifest.items():
        ep = str(entry.get("episode", "")).strip()
        if ep.isdecimal():
            by_episode[ep.zfill(2)] = {"source": entry.get("source", key),
                                       "updated": entry.get("updated", "")}

    rows = []
    for folder in gui.episode_dirs():
        ep = gui.episode_of(folder.name)
        info = by_episode.get(ep, {})
        steps = folder_steps(folder, ep)
        core_steps = {k: v for k, v in steps.items() if k not in DONE_EXCLUDE}
        rows.append({
            "episode": ep,
            "name": folder.name,
            "folder": str(folder),
            "title": folder.name.split(" - ", 1)[1] if " - " in folder.name else "",
            "source": info.get("source", ""),
            "updated": info.get("updated", ""),
            "steps": steps,
            "done_count": sum(1 for v in core_steps.values() if v),
            "total_steps": len(core_steps),
        })
    rows.sort(key=lambda r: int(r["episode"]), reverse=True)
    return rows


def episode_folder(episode: str) -> Path | None:
    return gui.find_episode_dir(episode)


def last_used_episode() -> int:
    """Số tập LỚN NHẤT đã dùng: manifest + thư mục tập + số thumbnail đã lưu."""
    used = {int(v["episode"]) for v in gui.load_manifest().values()
            if str(v.get("episode", "")).isdecimal()}
    for p in gui.episode_dirs():
        used.add(int(gui.episode_of(p.name)))
    used.add(gui.load_episode_number())
    return max(used) if used else 0


def next_episode() -> str:
    """Số tập sẽ cấp cho nguồn MỚI (dùng đúng quy tắc của GUI, kể cả tập bỏ qua)."""
    return str(gui.next_episode_number(last_used_episode())).zfill(2)


def latest_channel_episode() -> int:
    """Số tập LỚN NHẤT đang có trên kênh (theo cache). Không đọc được → 0."""
    try:
        import dang_video_youtube as yt
        data = yt.load_video_cache()
        entry = data["channels"].get(data.get("current"))
        nums = yt.episode_numbers(entry["videos"]) if entry else set()
        return max(nums) if nums else 0
    except Exception:
        return 0


def plan_episodes(sources: list[str], start_ep: str = "",
                  mode: str = "manual") -> list[str]:
    """Số tập cấp cho từng nguồn khi chạy hàng loạt (danh sách CÙNG ĐỘ DÀI sources).

    Ô rỗng ở một vị trí = không chỉ định, để runner tự cấp như thường lệ.

    mode="auto"  — TỰ LÀM BÙ: không cần chọn gì, link 1 lấy số kênh còn thiếu BÉ
                   NHẤT, các link sau tăng dần theo danh sách; hết danh sách thì
                   tiếp tục từ (tập mới nhất kênh đã có + 1).
    mode="manual" — theo số tự nhập: link 1 mang `start_ep`, các link sau vét tiếp
                   danh sách còn thiếu kể từ đó rồi mới cấp số mới. start_ep rỗng
                   → không chỉ định gì (giữ nguyên nếp cũ).

    Hai chỗ luôn nhảy qua: số đã có thư mục trong kịch_bản (tập dựng rồi mà chưa đăng
    — cấp lại sẽ đụng thư mục cũ) và số nằm trong danh sách "tập bỏ qua".

    Nguồn ĐÃ có trong manifest thì để rỗng: runner nhận lại đúng tập cũ (chạy tiếp),
    và nó KHÔNG được tiêu mất một số làm bù vốn dành cho tập mới.
    """
    n = len(sources)
    todo = missing_episodes()["todo"]
    skip = gui.load_skip_episodes()

    if mode == "auto":
        pool = list(todo)                       # bé nhất trước
        # Hết tập còn thiếu → nối tiếp sau tập MỚI NHẤT KÊNH ĐÃ CÓ (không dùng bộ
        # đếm thumbnail ở máy — số đó có thể vống lên vì vài lần tạo ảnh thử).
        cursor = gui.next_episode_number(latest_channel_episode(), skip)
    else:
        start = str(start_ep or "").strip()
        if not start.isdecimal():
            return [""] * n
        start = start.zfill(2)
        # Gõ/bấm số nào thì bắt đầu từ ĐÚNG chỗ đó trong danh sách; số không nằm
        # trong danh sách thì chỉ dùng riêng nó rồi chuyển sang cấp số mới.
        pool = todo[todo.index(start):] if start in todo else [start]
        cursor = gui.next_episode_number(last_used_episode(), skip)

    known = {gui.norm_source(k) for k in gui.load_manifest()}
    taken = {gui.episode_of(p.name) for p in gui.episode_dirs()}

    out: list[str] = []
    for src in sources:
        if gui.norm_source(src) in known:
            out.append("")
            continue
        ep = ""
        while pool and not ep:              # ưu tiên vét danh sách làm bù
            cand = pool.pop(0)
            if cand not in taken:
                ep = cand
        while not ep:                       # hết danh sách → cấp số mới
            cand = str(cursor).zfill(2)
            cursor = gui.next_episode_number(cursor, skip)
            if cand not in taken:
                ep = cand
        taken.add(ep)                       # tránh 2 link trong cùng mẻ trùng số
        out.append(ep)
    return out


# ── Nội dung SEO để copy khi đăng video ─────────────────────────────────────
def seo_blocks(folder, episode: str) -> dict | None:
    """Tiêu đề / tiêu đề TikTok / mô tả / thẻ tag — dùng ĐÚNG các hàm compose của
    thumbnail_gui.py (bản port của App._seo_copy_blocks) nên khớp tuyệt đối với
    3 nút Copy bên GUI."""
    seo_docx = Path(folder) / "seoYoutube.docx"
    if not seo_docx.exists():
        return None
    try:
        from seo_docx_parser import parse_seo_docx
        import thumbnail_gui as tg

        seo = parse_seo_docx(str(seo_docx))
        ep = episode if str(episode).strip().isdecimal() else ""
        title = tg.compose_youtube_title(seo.get("title", ""), ep)
        title_tiktok = tg.compose_tiktok_title(seo.get("title", ""), ep)
        desc = tg.add_episode_to_description(seo.get("description", ""), ep)
        desc = tg.add_episode_hashtag_top(desc, ep)
        desc = tg.add_full_hashtags(desc)
        tags = tg.cap_tags(seo.get("tags", []), ep, seo.get("title", ""))
        return {"title": title or "", "title_tiktok": title_tiktok or "",
                "desc": desc or "", "tags": tags or ""}
    except Exception:
        return None


# ── Cài đặt TTS gửi cho runner ──────────────────────────────────────────────
def _f(value, default: float, lo: float, hi: float) -> float:
    try:
        v = float(str(value).replace(",", ".").strip())
    except (TypeError, ValueError):
        return default
    return max(lo, min(v, hi))


def _i(value, default: int, lo: int, hi: int) -> int:
    try:
        v = int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default
    return max(lo, min(v, hi))


def tts_settings() -> tuple[dict | None, str]:
    """Gói cài đặt cho runner tạo giọng — bản đọc-từ-JSON của
    App._collect_tts_settings (GUI đọc tk.Var, web đọc file cài đặt).

    Trả về (settings, lỗi). settings=None nghĩa là cấu hình còn thiếu.
    """
    opts = load_options()
    web = load_web_settings()

    mode = web.get("mode", "clone")
    if mode == "clone":
        voice = (web.get("voice") or "").strip()
        available = list_voice_names()
        if voice not in available:
            voice = available[0] if available else ""
        if not voice:
            return None, f"Chưa có giọng mẫu nào trong {VOICE_DIR}"
        voice_param = str(VOICE_DIR / voice)
    elif mode == "design":
        voice_param = (web.get("instruct") or "").strip()
        if not voice_param:
            return None, "Chế độ Thiết kế cần mô tả giọng đọc."
    else:
        voice_param = None

    cut_audio = bool(opts.get("cut_audio"))
    cut_target = _f(opts.get("cut_target"), 12.0, 0.1, 600.0) if cut_audio else 0.0
    cut_min = _f(opts.get("cut_min"), 10.0, 0.1, 600.0) if cut_audio else 0.0
    cut_max = _f(opts.get("cut_max"), 15.0, 0.1, 600.0) if cut_audio else 0.0
    if cut_audio and not (0 < cut_min <= cut_max):
        return None, "Cấu hình cắt audio sai: cần 0 < phút 'Từ' ≤ phút 'Đến'."

    effect_name = (opts.get("effect") or "").strip()
    effect_path = None
    if effect_name and effect_name != EFFECT_NONE:
        p = EFFECTS_DIR / gui.strip_star(effect_name)
        effect_path = str(p) if p.exists() else None

    return dict(
        mode=mode, voice_param=voice_param,
        chunk=_i(opts.get("chunk"), 300, 50, 2000),
        make_video=bool(opts.get("make_video")), effect=effect_path,
        cut_audio=cut_audio, cut_target=cut_target, cut_min=cut_min, cut_max=cut_max,
        cut_half=bool(opts.get("cut_half")),
        make_video_doc=bool(opts.get("make_video_doc")),
        doc_full_audio=bool(opts.get("doc_full_audio")),
        doc_speed=_f(opts.get("doc_speed"), 1.0, 0.5, 2.0),
        doc_percent=_i(opts.get("doc_percent"), 100, 1, 100),
        ngang_speed=_f(opts.get("ngang_speed"), 1.0, 0.5, 2.0),
        ngang_source=opts.get("ngang_source") or NGANG_SOURCE_ALL,
        doc_from_ngang=bool(opts.get("doc_from_ngang")),
        doc_from_subfolder=bool(opts.get("doc_from_subfolder")),
        doc_no_effect=bool(opts.get("doc_no_effect")),
        make_tiktok=bool(opts.get("make_tiktok")),
        # YouTube Short ≤2:50 cắt từ chính video TikTok, đăng tự động sau bản chính
        # 1 giờ (xem scripts/video_short.py + YOUTUBE/dang_tap_youtube.upload_short).
        make_short=bool(opts.get("make_short")),
        tiktok_speed=_f(opts.get("tiktok_speed"), 1.0, 0.5, 2.0),
        tiktok_percent=_i(opts.get("tiktok_percent"), 50, 1, 100),
        tiktok_no_effect=bool(opts.get("tiktok_no_effect")),
        tiktok_caption_pos=_i(opts.get("tiktok_caption_pos"), 40, 0, 100),
        tiktok_music=bool(opts.get("tiktok_music")),
        tiktok_music_db=_i(opts.get("tiktok_music_db"), -12, -40, 0),
        make_sub=bool(opts.get("make_sub")),
        # Phụ đề video DỌC (facebook.mp4) — cùng kiểu/model/số ký tự với video
        # ngang, khung 1080x1920 tự rút dòng ngắn lại (xem make_youtube_sub).
        make_sub_doc=bool(opts.get("make_sub_doc")),
        sub_mode=opts.get("sub_mode") or SUB_MODE_SRT,
        sub_model=opts.get("sub_model") or "medium",
        sub_max_chars=_i(opts.get("sub_max_chars"), 50, 10, 200),
    ), ""


# ── Đăng YouTube ────────────────────────────────────────────────────────────
def upload_slots_text(default: str = "08:00 & 18:00") -> str:
    """Các khung giờ đăng, lấy từ dang_video_youtube.UPLOAD_SLOTS (nguồn duy nhất)."""
    try:
        import dang_video_youtube as yt
        return " & ".join(f"{h:02d}:{m:02d}" for h, m in yt.UPLOAD_SLOTS)
    except Exception:
        return default


def _yt_module() -> tuple[object | None, str]:
    """Nạp phần đăng YouTube + kiểm hai thứ ngoài tầm token: thư viện Google API và
    client_secret.json. → (module, lỗi). Chung cho upload_check và youtube_login."""
    try:
        import dang_video_youtube as yt
    except Exception as e:
        return None, f"Không nạp được phần đăng YouTube: {e}"

    missing = yt._check_deps()
    if missing:
        return None, ("Thiếu thư viện Google API (" + missing + "). Cài bằng: pip "
                      "install google-api-python-client google-auth-oauthlib "
                      "google-auth-httplib2")
    if not yt.CLIENT_SECRET_FILE.exists():
        return None, f"Chưa có {yt.CLIENT_SECRET_FILE.name} trong myvoice/YOUTUBE/."
    return yt, ""


def upload_check() -> tuple[bool, str]:
    """Đủ điều kiện đăng YouTube chưa? → (ok, thông báo lỗi).

    KHÔNG BAO GIỜ mở trình duyệt đăng nhập: hàm này chạy trong luồng phục vụ trang
    web, chờ ở đây là treo cứng cả bảng điều khiển. Chưa có token dùng được thì báo
    để bấm nút "🔑 Đăng nhập YouTube" (youtube_login) — nút đó mới được mở trình
    duyệt, vì nó chạy ở luồng nền riêng.
    """
    yt, err = _yt_module()
    if err:
        return False, err
    # Giữ lại lời của get_credentials (token hết hạn / làm mới thất bại / thiếu
    # quyền) thay vì ném đi: nuốt mất thì mọi kiểu hỏng đều ra đúng một câu "chưa
    # đăng nhập", không biết là chưa đăng nhập bao giờ hay token vừa bị thu hồi.
    notes: list[str] = []
    try:
        creds = yt.get_credentials(lambda m, *a, **k: notes.append(str(m)),
                                   interactive=False)
    except Exception as e:
        return False, f"Không đọc được token YouTube: {e}"
    if creds is None:
        why = f" ({notes[-1]})" if notes else ""
        return False, (f"Chưa đăng nhập YouTube{why}. Bấm nút “🔑 Đăng nhập "
                       "YouTube” ở khối Đăng YouTube (hoặc mở app 'Đăng video "
                       "YouTube' bên GUI) để đăng nhập lại một lần.")
    return True, ""


def youtube_login(note, timeout: int = 300) -> tuple[dict | None, str]:
    """Đăng nhập YouTube: MỞ TRÌNH DUYỆT trên chính máy đang chạy server. → (kênh, lỗi).

    Gọi hàm này trong LUỒNG NỀN, đừng gọi thẳng từ handler: nó đứng chờ tới lúc
    người dùng bấm "Cho phép" xong (tối đa `timeout` giây).

    Mở trình duyệt được là vì server chỉ nghe 127.0.0.1 — người ngồi trước trang web
    cũng chính là người ngồi trước cái máy này, nên cửa sổ Google hiện ra đúng trước
    mặt họ. Còn token đã hết hạn/bị thu hồi thì không có cách nào lấy lại mà không
    qua trình duyệt.

    `note` nhận từng dòng tiến trình (truyền upload_runner.note để nó lên nhật ký
    hàng đợi đăng). Xong thì đọc luôn kênh: vừa có tên kênh để báo lại, vừa nạp
    kenh_video_cache.json cho việc xếp khung giờ đăng.
    """
    yt, err = _yt_module()
    if err:
        return None, err

    def _log(msg, *a, **k):         # chữ ký log của dang_video_youtube: log(text, level)
        note(str(msg))

    try:
        creds = yt.get_credentials(_log, login_timeout=timeout)
    except Exception as e:
        # So theo TÊN lớp thay vì isinstance: WSGITimeoutError kế thừa AttributeError
        # nên bắt bằng lớp cha sẽ nuốt nhầm lỗi lập trình thật, mà import lớp con vào
        # đây chỉ để so sánh thì lại kéo google_auth_oauthlib lên tận đầu module.
        if type(e).__name__ == "WSGITimeoutError":
            return None, (f"Chờ quá {timeout // 60} phút không thấy bấm Cho phép nên "
                          "đã đóng cửa sổ chờ. Bấm lại nút 🔑 khi sẵn sàng.")
        return None, f"{type(e).__name__}: {e}"
    if creds is None:               # interactive=True nên chỉ xảy ra nếu code đổi
        return None, "Không lấy được token đăng nhập."
    try:
        chan, _videos = yt.fetch_channel_videos(_log)
    except Exception as e:
        return None, f"Đã đăng nhập nhưng chưa đọc được kênh: {e}"
    return chan, ""


def refresh_channel() -> tuple[dict | None, str]:
    """Đọc lại kênh + video đã hẹn giờ (nạp cache cho việc xếp lịch đăng).

    → (thông tin kênh, lỗi). Gọi TRƯỚC khi xếp việc đăng, để biết đăng lên kênh nào
    và để khung giờ 08:00/18:00 không đè lên lịch sẵn có.
    """
    ok, err = upload_check()
    if not ok:
        return None, err
    try:
        import dang_video_youtube as yt
        chan, _videos = yt.fetch_channel_videos(lambda *a, **k: None)
        return chan, ""
    except Exception as e:
        return None, f"Không đọc được kênh YouTube: {e}"


def episodes_on_channel() -> set:
    """Số tập ĐÃ CÓ trên kênh (tách 'Số N' từ tiêu đề video trong cache).

    Chốt chặn đăng trùng cho tập đã đăng tay: tập đó không có youtube_upload.json
    nên chỉ nhìn file trong thư mục là không biết.
    """
    try:
        import dang_video_youtube as yt
        data = yt.load_video_cache()
        entry = data["channels"].get(data.get("current"))
        return yt.episode_numbers(entry["videos"]) if entry else set()
    except Exception:
        return set()


def upload_settings() -> dict:
    """Cài đặt đăng tự động (danh mục · chế độ · trẻ em · AI) — chung với bản GUI."""
    try:
        import dang_tap_youtube as up
        return up.load_settings()
    except Exception:
        return {}


def save_upload_settings(data: dict) -> dict:
    try:
        import dang_tap_youtube as up
        return up.save_settings(data)
    except Exception:
        return {}


def upload_choices() -> dict:
    """Danh sách lựa chọn cho form đăng: danh mục YouTube + các chế độ đăng."""
    try:
        import dang_tap_youtube as up
        import dang_video_youtube as yt
        return {"categories": [{"id": i, "label": lb} for lb, i in yt.CATEGORIES.items()],
                "privacy": [{"id": k, "label": v} for k, v in up.PRIVACY_LABELS.items()]}
    except Exception:
        return {"categories": [], "privacy": []}


def episodes_pending_upload() -> list[str]:
    """Tập đã dựng xong video + có SEO mà CHƯA đăng, và kênh cũng chưa có."""
    try:
        import dang_tap_youtube as up
    except Exception:
        return []
    on_channel = episodes_on_channel()
    out = []
    for folder in gui.episode_dirs():
        ep = gui.episode_of(folder.name)
        if (ep and up.find_video(folder) is not None
                and up.already_uploaded(folder) is None
                and int(ep) not in on_channel
                and seo_docx_valid(folder / "seoYoutube.docx")):
            out.append(ep)
    return out


def missing_episodes() -> dict:
    """Các số tập KÊNH CÒN THIẾU (đọc kenh_video_cache.json), chia làm hai nhóm:

      todo  — chưa có thư mục ở máy → cấp được cho link mới (làm bù thật sự).
      built — ĐÃ có thư mục (dựng xong rồi, chỉ chưa đăng) → không cấp cho link mới
              vì sẽ đụng thư mục đã có; việc cần làm với chúng là bấm ⑥ Đăng YouTube.

    Số tập lấy bằng cách đọc 'Số N' trong tiêu đề video trên kênh, nên chỉ mới tới
    lần đọc kênh gần nhất. Đọc kênh mặc định chỉ lấy 50 video mới nhất → chỉ dò
    thiếu từ Số của video CŨ NHẤT đọc được trở lên (lo), số nhỏ hơn nằm ngoài tầm
    nhìn nên không bị coi là thiếu — xem yt.find_missing_episodes.
    """
    try:
        import dang_video_youtube as yt
        missing, lo, hi = yt.cached_missing_episodes()
    except Exception:
        return {"todo": [], "built": [], "lo": None, "hi": None}
    # Liệt kê thư mục tập MỘT lần rồi tra, thay vì dò lại cho từng số.
    have = {gui.episode_of(p.name) for p in gui.episode_dirs()}
    todo, built = [], []
    for n in missing:
        ep = str(n).zfill(2)
        (built if ep in have else todo).append(ep)
    return {"todo": todo, "built": built, "lo": lo, "hi": hi}


def next_publish_slot_text() -> str:
    """Khung giờ đăng trống kế tiếp, dạng 'dd/mm/YYYY HH:MM' (rỗng nếu chưa tính được)."""
    try:
        import dang_video_youtube as yt
        return f"{yt.next_publish_slot():%d/%m/%Y %H:%M}"
    except Exception:
        return ""


def python_exe() -> str:
    """Interpreter chạy các runner: ưu tiên venv của repo (nơi có torch/whisper)."""
    return str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable


def subprocess_env() -> dict:
    """Env cho runner: log tiếng Việt không vỡ, stdout không đệm (để stream)."""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONPATH"] = os.pathsep.join(
        [str(REPO_ROOT), str(SCRIPTS_DIR), str(YOUTUBE_DIR), env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    return env
