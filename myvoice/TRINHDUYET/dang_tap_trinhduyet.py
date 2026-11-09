# -*- coding: utf-8 -*-
"""Đăng video của MỘT THƯ MỤC TẬP (kịch_bản/<chữ><số> - …) lên YouTube Studio + TikTok Studio bằng
Chrome thật (Playwright Extension) — bản 'trình duyệt' song song với đường API ở YOUTUBE/dang_tap_youtube.py.

Lấy gì trong thư mục tập:
  • YouTube : YOUTUBE.mp4 (bản ngang) + thumbnail<NN>.png + short.mp4 (Short, hẹn sau bản chính 1 giờ)
  • TikTok  : bản dọc ĐẦY ĐỦ '[Full] …' / facebook.mp4 (tiktok_ban = full, mặc định — bảng TikTok cũ cũng
              đăng bản này) hoặc tiktok.mp4 / 'Full ở …' (tiktok_ban = ngan)
  • Tiêu đề / mô tả / thẻ: bên gọi truyền `blocks` = core.seo_blocks(folder, ep) (đúng nội dung 3 nút Copy SEO),
    nên cách đặt tiêu đề vẫn chỉ có MỘT nơi quy định.

Biên nhận: youtube_upload.json (CÙNG khuôn với đường API, thêm "via": "studio") → mọi chỗ khác của pipeline
(bảng tiến độ, Facebook tìm file đã đổi tên, chống đăng trùng) vẫn hiểu; tiktok_upload.json là biên nhận mới
cho TikTok. Sau khi đăng YouTube xong vẫn đổi tên hai bản dọc như đường API (rename_doc).

Khung giờ: 08:00 / 18:00 (cau_hinh.khung_gio), xếp SAU video đang lên lịch muộn nhất — nguồn: biên nhận local
của mọi tập + (nếu doc_lich_that) lịch đọc thật trên Studio. TikTok có giới hạn riêng: sớm nhất 15 phút,
muộn nhất 10 ngày → quá 10 ngày thì bỏ qua TikTok của tập đó (báo rõ), không ép.

Module này KHÔNG import web/core (nặng); runner web/runners/run_dang_trinhduyet.py lo phần đó.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
BASE_DIR = APP_DIR.parent                       # myvoice/
KICHBAN_DIR = BASE_DIR / "kịch_bản"
for _p in (str(APP_DIR), str(BASE_DIR / "YOUTUBE")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import dang_tap_youtube as up                   # noqa: E402  (find_video, rename_doc, short_title… dùng chung)
import trinhduyet                               # noqa: E402
from dang_chung import hashtags_in_text         # noqa: E402

RECORD_YT = up.RECORD_NAME                      # youtube_upload.json
RECORD_TT = "tiktok_upload.json"
VIA = "studio"
YT_LEAD_MIN = 60        # giống dang_video_youtube.SLOT_MIN_LEAD_MINUTES
TT_LEAD_MIN = 20        # TikTok nhận sớm nhất 15 phút → chừa 20
MAX_TITLE, MAX_DESC = 100, 5000
BAN_FULL, BAN_NGAN = "full", "ngan"
TIKTOK_CONTENT_URL = "https://www.tiktok.com/tiktokstudio/content"

_TITLE_HEAD_RE = re.compile(r"^\s*(\[full\]|full\s+ở)\s*", re.IGNORECASE)
_BRAND_CHUNK_RE = re.compile(r"\s*\|?\s*mimi\s*audio(\s*số\s*\d+)?\s*", re.IGNORECASE)
_SHORTS_RE = re.compile(r"#shorts\b", re.IGNORECASE)
_NOTE_RE = re.compile(r"\s*\(\s*\d+\s*ký tự\s*\)\s*$", re.IGNORECASE)


# ------------------------------------------------------------------ hàm thuần (có test)
def title_key(title: str) -> str:
    """Khoá so trùng = TÊN TRUYỆN: bỏ '#Shorts', '[Full]'/'Full ở', 'Mimi audio Số n', '|', ghi chú '(61 ký tự)'."""
    t = _SHORTS_RE.sub(" ", title or "")
    t = _NOTE_RE.sub("", t)
    t = _TITLE_HEAD_RE.sub("", t)
    t = _BRAND_CHUNK_RE.sub(" ", t)
    return " ".join(t.lower().strip().strip("|").split())


def parse_khung_gio(khung) -> list[tuple[int, int]]:
    """['08:00', '18:00'] → [(8, 0), (18, 0)], sắp xếp, bỏ mục hỏng; rỗng → mặc định 08:00/18:00."""
    out = []
    for s in khung or []:
        m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", str(s))
        if m and 0 <= int(m.group(1)) < 24 and 0 <= int(m.group(2)) < 60:
            out.append((int(m.group(1)), int(m.group(2))))
    return sorted(set(out)) or [(8, 0), (18, 0)]


def _naive_local(dt: datetime) -> datetime:
    """Mọi mốc giờ xử lý ở dạng giờ máy KHÔNG tz (Studio hiển thị giờ máy)."""
    return dt.astimezone().replace(tzinfo=None) if dt.tzinfo else dt


def parse_dt(s) -> datetime | None:
    try:
        return _naive_local(datetime.fromisoformat(str(s).strip()))
    except (TypeError, ValueError):
        return None


def khung_ke_tiep(now: datetime, taken, khung_gio, lead_min: int, after_last: bool = True) -> datetime:
    """Khung giờ TRỐNG gần nhất (giờ máy): >= now + lead_min, không trùng giờ đã chiếm, và (after_last) phải
    SAU mốc muộn nhất đã chiếm — tập mới bắt buộc lên sau tập cũ (kênh đánh số tập)."""
    now = _naive_local(now)
    times = [_naive_local(t) for t in (taken or []) if t]
    used = {t.replace(second=0, microsecond=0) for t in times}
    earliest = now + timedelta(minutes=lead_min)
    if after_last and times:
        earliest = max(earliest, max(times) + timedelta(minutes=1))
    day = earliest.replace(hour=0, minute=0, second=0, microsecond=0)
    for _ in range(370):
        for hh, mm in parse_khung_gio(khung_gio):
            slot = day.replace(hour=hh, minute=mm)
            if slot >= earliest and slot not in used:
                return slot
        day += timedelta(days=1)
    raise RuntimeError("Không tìm được khung giờ đăng trống trong 1 năm tới.")


def _doc_json(path: Path) -> dict:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def gio_da_hen_local(kichban_dir: Path = KICHBAN_DIR, now: datetime | None = None) -> dict:
    """Giờ đã hẹn theo biên nhận trong MỌI thư mục tập (chỉ mốc tương lai):
    {"youtube": [publish_at + short_publish_at…], "tiktok": [publish_at…]}."""
    now = _naive_local(now or datetime.now())
    out = {"youtube": [], "tiktok": []}
    kichban_dir = Path(kichban_dir)
    if not kichban_dir.is_dir():
        return out
    for folder in kichban_dir.iterdir():
        if not folder.is_dir():
            continue
        yt = _doc_json(folder / RECORD_YT)
        for k in ("publish_at", "short_publish_at"):
            dt = parse_dt(yt.get(k)) if yt.get(k) else None
            if dt and dt > now:
                out["youtube"].append(dt)
        tt = _doc_json(folder / RECORD_TT)
        dt = parse_dt(tt.get("publish_at")) if tt.get("publish_at") else None
        if dt and dt > now:
            out["tiktok"].append(dt)
    out["youtube"].sort()
    out["tiktok"].sort()
    return out


def tieu_de_trung_local(title: str, episode: str, kichban_dir: Path = KICHBAN_DIR) -> str:
    """Thư mục tập KHÁC đã đăng (có youtube_upload.json) cùng TÊN TRUYỆN → tên thư mục đó; không → ''.
    Chốt chống SEO lấy nhầm kết quả tập khác (đường API tra kênh qua cache; bản này tra biên nhận local)."""
    want = title_key(title)
    if not want:
        return ""
    ep = str(episode).strip().lstrip("0") or "0"
    for folder in sorted(Path(kichban_dir).iterdir()) if Path(kichban_dir).is_dir() else []:
        rec = _doc_json(folder / RECORD_YT)
        if not rec.get("video_id"):
            continue
        if (str(rec.get("episode", "")).strip().lstrip("0") or "0") == ep:
            continue
        if title_key(rec.get("title") or "") == want:
            return folder.name
    return ""


def tim_video_tiktok(folder: Path, ban: str = BAN_FULL) -> Path | None:
    """Video để đăng TikTok. full: facebook.mp4 → tên ghi ở youtube_upload.json (facebook_file) → '[Full] *.mp4'
    → 'facebook *.mp4' / '*_doc.mp4'. ngan: tiktok.mp4 → tiktok_file → 'tiktok *.mp4' / 'Full ở *.mp4'.
    (Cùng thứ tự với dang_video_facebook.find_video_full / find_video_ngan.)"""
    folder = Path(folder)
    rec = _doc_json(folder / RECORD_YT)
    if (ban or BAN_FULL).strip().lower() == BAN_NGAN:
        goc, key, prefixes, patterns = "tiktok.mp4", "tiktok_file", ("full ở ",), ("tiktok *.mp4",)
    else:
        goc, key, prefixes, patterns = "facebook.mp4", "facebook_file", ("[full] ",), ("facebook *.mp4", "*_doc.mp4")
    if (folder / goc).is_file():
        return folder / goc
    name = str(rec.get(key) or "")
    if name and (folder / name).is_file():
        return folder / name
    for pre in prefixes:        # không glob '[Full] *' được: trong glob '[…]' là lớp ký tự
        hits = sorted(p for p in folder.glob("*.mp4") if p.name.lower().startswith(pre))
        if hits:
            return hits[0]
    for pat in patterns:
        hits = sorted(folder.glob(pat))
        if hits:
            return hits[0]
    return None


def hashtags_tiktok(blocks: dict, n: int = 6) -> list[str]:
    """N hashtag đầu của mô tả SEO (dòng đầu mô tả là '#MimiAudioSo156 #MimiAudio …'), bỏ trùng."""
    return hashtags_in_text((blocks or {}).get("desc") or "", limit=max(1, int(n or 6)))


def caption_tiktok(blocks: dict) -> str:
    """MỘT dòng: tiêu đề TikTok ('Full ở Mimi audio Số N | …'), không có thì tiêu đề YouTube."""
    for k in ("title_tiktok", "title"):
        t = " ".join(str((blocks or {}).get(k) or "").split())
        if t:
            return t
    return ""


def _iso(dt: datetime | None) -> str:
    return dt.astimezone().isoformat(timespec="seconds") if dt else ""


def _text(dt: datetime | None, fallback: str = "") -> str:
    return dt.strftime("%d/%m/%Y %H:%M") if dt else fallback


def _channel_id_from_url(url: str) -> str:
    m = re.search(r"/channel/(UC[\w-]+)", url or "")
    return m.group(1) if m else ""


# ------------------------------------------------------------------ kế hoạch
def ke_hoach_youtube(folder: Path, episode: str, blocks: dict, cfg: dict, now: datetime | None = None,
                     taken=None) -> dict:
    """Mọi thứ sẽ đăng lên YouTube cho tập này (chưa đụng trình duyệt). Trả về dict; khoá 'bo_qua' = lý do
    không đăng (rỗng = đăng được)."""
    folder = Path(folder)
    ep = str(episode)
    stg = up.load_settings()
    mode = str(stg.get("privacy") or "schedule")
    plan = {"bo_qua": "", "canh_bao": [], "episode": ep, "mode": mode,
            "made_for_kids": bool(stg.get("made_for_kids", False)),
            "contains_ai": bool(stg.get("contains_ai", True)),
            "playlist": str(cfg.get("playlist") or "")}
    if up.already_uploaded(folder):
        plan["bo_qua"] = f"tập {ep} đã đăng YouTube (có {RECORD_YT})"
        return plan
    video = up.find_video(folder)
    if video is None:
        plan["bo_qua"] = f"tập {ep}: không có {up.VIDEO_NAME}"
        return plan
    title = (blocks.get("title") or "").strip()
    desc = blocks.get("desc") or ""
    if not title:
        plan["bo_qua"] = f"tập {ep}: SEO không có tiêu đề"
        return plan
    if len(title) > MAX_TITLE:
        plan["bo_qua"] = f"tập {ep}: tiêu đề {len(title)} ký tự > {MAX_TITLE} — sửa SEO rồi đăng lại"
        return plan
    if len(desc) > MAX_DESC:
        plan["canh_bao"].append(f"mô tả {len(desc)} ký tự > {MAX_DESC} → cắt bớt phần cuối")
        desc = desc[:MAX_DESC]
    if not up.ALLOW_DUP_TITLE:
        dup = tieu_de_trung_local(title, ep, folder.parent)
        if dup:
            plan["bo_qua"] = (f"tập {ep}: thư mục '{dup}' đã đăng video CÙNG TÊN TRUYỆN — nhiều khả năng SEO lấy "
                              f"nhầm kết quả cũ → không đăng (đặt {up.ALLOW_DUP_TITLE_ENV}=1 nếu cố ý)")
            return plan
    thumb = up.find_thumbnail(folder, ep)
    if thumb is None:
        plan["canh_bao"].append(f"không thấy thumbnail{ep}.png — đăng không kèm ảnh bìa")
    publish_at = None
    if mode == "schedule":
        publish_at = khung_ke_tiep(now or datetime.now(), taken, cfg.get("khung_gio"), YT_LEAD_MIN)
    short = folder / up.SHORT_NAME
    short_ok = short.is_file() and short.stat().st_size > 0
    short_title = up.short_title(blocks, MAX_TITLE) if short_ok else ""
    if short_ok and not short_title:
        plan["canh_bao"].append("không dựng được tiêu đề Short → bỏ qua Short")
    plan.update({
        "video": video, "thumbnail": thumb, "title": title, "desc": desc,
        "tags": [t.strip() for t in (blocks.get("tags") or "").split(",") if t.strip()],
        "publish_at": publish_at,
        "short": short if (short_ok and short_title) else None, "short_title": short_title,
        "short_at": (publish_at + timedelta(hours=float(cfg.get("short_sau_gio") or 1))) if publish_at else None,
        "visibility": {"schedule": "SCHEDULE", "public": "PUBLIC", "unlisted": "UNLISTED"}.get(mode, "PRIVATE"),
    })
    return plan


def ke_hoach_tiktok(folder: Path, episode: str, blocks: dict, cfg: dict, now: datetime | None = None,
                    taken=None) -> dict:
    folder = Path(folder)
    ep = str(episode)
    plan = {"bo_qua": "", "canh_bao": [], "episode": ep}
    if _doc_json(folder / RECORD_TT).get("uploaded_at"):
        plan["bo_qua"] = f"tập {ep} đã đăng TikTok (có {RECORD_TT})"
        return plan
    ban = str(cfg.get("tiktok_ban") or BAN_FULL)
    video = tim_video_tiktok(folder, ban)
    if video is None:
        plan["bo_qua"] = f"tập {ep}: không có video dọc " + ("ngắn (tiktok.mp4)" if ban == BAN_NGAN else "đầy đủ ([Full]/facebook.mp4)")
        return plan
    caption = caption_tiktok(blocks)
    if not caption:
        plan["bo_qua"] = f"tập {ep}: SEO không có tiêu đề TikTok"
        return plan
    now = _naive_local(now or datetime.now())
    when = khung_ke_tiep(now, taken, cfg.get("khung_gio"), TT_LEAD_MIN)
    from dang_tiktok_studio import kiem_gio_hop_le, lam_tron_5
    when = lam_tron_5(when)
    loi = kiem_gio_hop_le(when, now)
    if loi:
        plan["bo_qua"] = f"tập {ep}: {loi} (TikTok đã kín lịch 10 ngày — đăng lại sau)"
        return plan
    plan.update({"video": video, "ban": ban, "caption": caption,
                 "hashtags": hashtags_tiktok(blocks, cfg.get("so_hashtag_tiktok") or 6),
                 "publish_at": when})
    return plan


def mo_ta_ke_hoach(plan: dict, nen_tang: str) -> str:
    """Một đoạn chữ cho log / --ke-hoach."""
    if plan.get("bo_qua"):
        return f"[{nen_tang}] ⏭ bỏ qua: {plan['bo_qua']}"
    dong = []
    if nen_tang == "youtube":
        dong.append(f"[youtube] {Path(plan['video']).name} → {_text(plan['publish_at'], plan['visibility'])}"
                    f" · thumbnail: {Path(plan['thumbnail']).name if plan.get('thumbnail') else '—'}")
        dong.append(f"  tiêu đề: {plan['title']}")
        dong.append(f"  thẻ: {len(plan['tags'])} · mô tả {len(plan['desc'])} ký tự"
                    + (f" · playlist: {plan['playlist']}" if plan.get("playlist") else ""))
        if plan.get("short"):
            dong.append(f"  Short: {Path(plan['short']).name} → {_text(plan['short_at'], plan['visibility'])} · {plan['short_title']}")
    else:
        dong.append(f"[tiktok] {Path(plan['video']).name} ({plan['ban']}) → {_text(plan['publish_at'])}")
        dong.append(f"  mô tả: {plan['caption']} {' '.join(plan['hashtags'])}")
    for c in plan.get("canh_bao") or []:
        dong.append(f"  ⚠ {c}")
    return "\n".join(dong)


# ------------------------------------------------------------------ đăng
def _ghi(path: Path, rec: dict, log, nhan: str):
    try:
        path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError as e:
        log(f"❌ ĐÃ ĐĂNG {nhan} nhưng KHÔNG ghi được {path.name}: {e}. Chạy lại có thể đăng TRÙNG!", "err")


def dang_youtube(folder: Path, episode: str, blocks: dict, cfg: dict, log, dry_run: bool = False,
                 lich_that=None, now: datetime | None = None) -> dict | None:
    """Đăng YouTube (bản chính + Short) của một tập qua Studio. Trả về bản ghi đã lưu, None nếu bỏ qua.
    lich_that: list datetime đọc từ Studio (None = chỉ dựa biên nhận local)."""
    import dang_youtube_studio as yts

    folder = Path(folder)
    ep = str(episode)
    taken = gio_da_hen_local(folder.parent, now)["youtube"] + list(lich_that or [])
    plan = ke_hoach_youtube(folder, ep, blocks, cfg, now, taken)
    for c in plan["canh_bao"]:
        log(f"⚠️ Tập {ep}: {c}", "warn")
    if plan["bo_qua"]:
        log(f"⏭ YouTube: {plan['bo_qua']}", "info")
        return None
    log(mo_ta_ke_hoach(plan, "youtube"), "info")

    _relay, page = trinhduyet.ket_noi(cfg, "youtube", lambda m: log(m, "info"))
    lg = lambda m: log(m, "info")   # noqa: E731
    link = yts.upload_video(page, str(plan["video"]), plan["title"], plan["desc"], playlist=plan["playlist"] or None,
                            tags=plan["tags"], visibility=plan["visibility"], made_for_kids=plan["made_for_kids"],
                            contains_ai=plan["contains_ai"], thumbnail_path=str(plan["thumbnail"]) if plan["thumbnail"] else None,
                            log=lg, dry_run=dry_run, schedule_at=plan["publish_at"])
    if dry_run:
        log(f"⏸ Tập {ep}: CHẠY THỬ YouTube xong (chưa Lưu, chưa ghi biên nhận, chưa đổi tên file).", "info")
        return None
    video_id = yts.video_id_from_link(link)
    if not video_id:
        raise RuntimeError(f"Tập {ep}: Studio báo xong nhưng không đọc được link video — kiểm tra Nội dung trên Studio "
                           "trước khi chạy lại (tránh đăng trùng).")
    main_url = f"https://youtu.be/{video_id}"
    channel_id = _channel_id_from_url(page.url)

    live_at = plan["publish_at"] or datetime.now()
    tiktok = up.rename_doc(folder, up.TIKTOK_NAME,
                           up.safe_stem(blocks.get("title_tiktok")) or up.time_stem(up.TIKTOK_NAME, live_at), log)
    facebook = up.rename_doc(folder, up.FACEBOOK_NAME, up.full_stem(blocks, live_at), log)

    short = None
    if plan["short"]:
        try:
            log(f"⬆ Đăng Short tập {ep}: {plan['short'].name} → {_text(plan['short_at'], plan['visibility'])}", "info")
            s_link = yts.upload_video(page, str(plan["short"]), plan["short_title"],
                                      up.short_description(main_url, ep), tags=plan["tags"],
                                      visibility=plan["visibility"], made_for_kids=plan["made_for_kids"],
                                      contains_ai=plan["contains_ai"], log=lg, schedule_at=plan["short_at"])
            s_id = yts.video_id_from_link(s_link)
            if s_id:
                short = {"video_id": s_id, "url": f"https://youtu.be/{s_id}", "publish_at": _iso(plan["short_at"]),
                         "publish_at_text": _text(plan["short_at"], plan["visibility"])}
                log(f"✅ Short tập {ep}: {short['url']} — {short['publish_at_text']}", "ok")
            else:
                log(f"⚠️ Tập {ep}: Short đã lưu nhưng không đọc được link — bổ sung tay vào {RECORD_YT}.", "warn")
        except Exception as e:
            log(f"⚠️ Tập {ep}: đăng Short lỗi ({e}) — video chính KHÔNG ảnh hưởng. Đăng Short tay nếu cần.", "warn")

    privacy = "private" if plan["mode"] == "schedule" else plan["mode"]
    rec = {
        "episode": ep, "video_id": video_id, "url": main_url, "title": plan["title"], "privacy": privacy,
        "publish_at": _iso(plan["publish_at"]),
        "publish_at_text": _text(plan["publish_at"], up.PRIVACY_LABELS.get(plan["mode"], plan["mode"])),
        "uploaded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "video_file": plan["video"].name,
        "tiktok_file": tiktok.name if tiktok else "",
        "facebook_file": facebook.name if facebook else "",
        "short_video_id": short["video_id"] if short else "",
        "short_url": short["url"] if short else "",
        "short_publish_at": short["publish_at"] if short else "",
        "short_publish_at_text": short["publish_at_text"] if short else "",
        "thumbnail": plan["thumbnail"].name if plan["thumbnail"] else "",
        "made_for_kids": plan["made_for_kids"], "contains_ai": plan["contains_ai"],
        "channel_id": channel_id, "via": VIA,
    }
    _ghi(folder / RECORD_YT, rec, log, f"tập {ep} ({main_url})")
    log(f"✅ Tập {ep} đã đăng YouTube (Studio): {main_url} — {rec['publish_at_text']}", "ok")
    return rec


def dang_tiktok(folder: Path, episode: str, blocks: dict, cfg: dict, log, dry_run: bool = False,
                lich_that=None, now: datetime | None = None) -> dict | None:
    import dang_tiktok_studio as tts

    folder = Path(folder)
    ep = str(episode)
    taken = gio_da_hen_local(folder.parent, now)["tiktok"] + list(lich_that or [])
    plan = ke_hoach_tiktok(folder, ep, blocks, cfg, now, taken)
    for c in plan["canh_bao"]:
        log(f"⚠️ Tập {ep}: {c}", "warn")
    if plan["bo_qua"]:
        log(f"⏭ TikTok: {plan['bo_qua']}", "info")
        return None
    log(mo_ta_ke_hoach(plan, "tiktok"), "info")

    _relay, page = trinhduyet.ket_noi(cfg, "tiktok", lambda m: log(m, "info"))
    url = tts.upload_video(page, str(plan["video"]), plan["caption"], plan["hashtags"],
                           schedule_at=plan["publish_at"], log=lambda m: log(m, "info"), dry_run=dry_run)
    if dry_run:
        log(f"⏸ Tập {ep}: CHẠY THỬ TikTok xong (chưa bấm nút cuối, chưa ghi biên nhận).", "info")
        return None
    rec = {
        "episode": ep, "video_file": plan["video"].name, "ban": plan["ban"], "caption": plan["caption"],
        "hashtags": plan["hashtags"], "publish_at": _iso(plan["publish_at"]),
        "publish_at_text": _text(plan["publish_at"]),
        "uploaded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "url": url or TIKTOK_CONTENT_URL, "via": VIA,
    }
    _ghi(folder / RECORD_TT, rec, log, f"TikTok tập {ep}")
    log(f"✅ Tập {ep} đã lên lịch TikTok (Studio): {rec['publish_at_text']}", "ok")
    return rec


def dang_tap(folder: Path, episode: str, blocks: dict, nen_tang=("youtube", "tiktok"), cfg: dict | None = None,
             log=None, dry_run: bool = False, lich_that: dict | None = None) -> dict:
    """Đăng một tập lên các nền tảng chọn. Trả về {"youtube": rec|None|"lỗi: …", "tiktok": …}.
    Lỗi ở một nền tảng không chặn nền tảng kia (ghi vào kết quả + log)."""
    cfg = cfg or trinhduyet.load_config()
    log = log or (lambda m, level="info": print(m))
    lich_that = lich_that or {}
    ham = {"youtube": dang_youtube, "tiktok": dang_tiktok}
    out = {}
    for name in nen_tang:
        if name not in ham:
            out[name] = f"lỗi: nền tảng lạ {name!r}"
            continue
        try:
            out[name] = ham[name](folder, episode, blocks, cfg, log, dry_run=dry_run, lich_that=lich_that.get(name))
        except trinhduyet.ProfileCamError as e:
            out[name] = f"lỗi: {e}"
            log(f"⛔ {e}", "err")
        except trinhduyet.ChuaCauHinhError as e:
            out[name] = f"chưa cấu hình: {e}"
            log(f"⏭ {e}", "warn")
        except Exception as e:
            out[name] = f"lỗi: {e}"
            log(f"❌ Tập {episode} [{name}]: {e}", "err")
            _chup_loi(name, log)
    return out


def _chup_loi(name: str, log):
    """Chụp tab đang điều khiển lúc lỗi để xem lại (ảnh trong thư mục TRINHDUYET)."""
    try:
        shot = APP_DIR / f"loi_gan_nhat_{name}.png"
        import base64
        data = trinhduyet.cdp_send("Page.captureScreenshot", {"format": "png"}).get("data")
        if data:
            shot.write_bytes(base64.b64decode(data))
            log(f"  Ảnh lúc lỗi: {shot}", "info")
    except Exception:
        pass


def doc_lich_that(cfg: dict, nen_tang, log) -> dict:
    """Đọc lịch đã đặt THẬT trên Studio của từng nền tảng (nếu doc_lich_that bật và profile đã cấu hình).
    Lỗi đọc → bỏ qua nền tảng đó (chỉ dựa biên nhận local), không chặn việc đăng."""
    out = {}
    if not cfg.get("doc_lich_that", True):
        return out
    for name in nen_tang:
        try:
            trinhduyet.kiem_san_sang(cfg, name)
        except Exception:
            continue
        try:
            _relay, page = trinhduyet.ket_noi(cfg, name, lambda m: log(m, "info"))
            if name == "youtube":
                import dang_youtube_studio as yts
                lst = yts.lich_da_dat(page, lambda m: log(m, "info"))
            else:
                import dang_tiktok_studio as tts
                lst = tts.lich_da_dat(page, lambda m: log(m, "info"))
            out[name] = lst
            log(f"📅 {trinhduyet.NHAN[name]}: {len(lst)} mốc đang lên lịch"
                + (f", muộn nhất {max(lst):%d/%m/%Y %H:%M}" if lst else ""), "info")
        except Exception as e:
            log(f"⚠️ Không đọc được lịch thật {trinhduyet.NHAN[name]} ({e}) — xếp giờ theo biên nhận local.", "warn")
    return out
