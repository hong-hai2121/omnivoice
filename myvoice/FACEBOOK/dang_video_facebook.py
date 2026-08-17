"""Lên lịch đăng video DỌC (facebook.mp4) của các tập lên Page MimiAudio.

Cách chạy:
    venv\\Scripts\\python.exe myvoice\\FACEBOOK\\dang_video_facebook.py            → xem kế hoạch rồi hỏi y/N
    venv\\Scripts\\python.exe myvoice\\FACEBOOK\\dang_video_facebook.py --dry-run  → chỉ xem, không đăng
    thêm --limit 4   → mỗi lần chạy chỉ xếp tối đa 4 tập
    thêm --yes       → khỏi hỏi (cho chạy tự động)

Cách hoạt động:
  1. Hỏi Page (Graph API) ba nguồn: bài ĐÃ đăng · bài ĐANG chờ lịch · kho video.
     Từ đó suy ra: tập lớn nhất đã có trên Page (đọc hashtag #MimiAudioSo<n>)
     và mốc giờ đã xếp lịch xa nhất.
  2. Các tập trong kịch_bản/ có SỐ LỚN HƠN tập đó và đã dựng xong video dọc
     là hàng chờ. Xếp lần lượt vào các khung 09:00 / 19:00 hằng ngày, nối tiếp
     NGAY SAU mốc lịch xa nhất (Page trống thì bắt đầu từ khung gần nhất).
  3. Upload kiểu resumable (start/transfer/finish) — video dài cỡ nào cũng được,
     đứt mạng giữa chừng thì chỉ hỏng tập đang dở, chạy lại là tiếp.

Caption bài đăng lấy từ SEO của tập (seoYoutube.docx, đúng bộ compose của
thumbnail_gui — khớp với nút Copy SEO); tập chưa có SEO thì dùng caption tối
thiểu "MimiAudio — Số <n> #MimiAudioSo<n>".

Token nằm ở file .env GỐC repo (OmniVoice/.env, bị .gitignore che):
    FB_PAGE_ID_MIMIAUDIO / FB_PAGE_ACCESS_TOKEN_MIMIAUDIO
Cần Page access token DÀI HẠN, quyền pages_manage_posts + pages_read_engagement.

Đăng xong ghi facebook_upload.json vào thư mục tập (giống youtube_upload.json)
— vừa làm dấu "tập này xếp lịch rồi", vừa lưu video_id để tra lại.

Facebook chỉ nhận lịch trong khoảng 10 phút → ~75 ngày tới; tập nào rơi ra
ngoài sẽ được bỏ lại, chạy lại script vào hôm khác để xếp tiếp.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]            # …/OmniVoice
VENV_PY = ROOT / "venv" / "Scripts" / "python.exe"
ENV_FILE = ROOT / ".env"

GRAPH = "https://graph.facebook.com/v21.0"
GRAPH_VIDEO = "https://graph-video.facebook.com/v21.0"
CACHE_FILE = Path(__file__).resolve().parent / "page_cache.json"
SLOT_HOURS = (9, 19)              # 09:00 sáng · 19:00 tối, giờ máy (VN)
MIN_LEAD_MIN = 15                 # FB đòi lịch cách hiện tại ≥10 phút — chừa 15
MAX_AHEAD_DAYS = 75               # FB không nhận lịch xa hơn ~75 ngày

# Số tập trong bài đăng, bắt CẢ HAI kiểu đang có trên Page:
#   bài đăng tay cũ:  "Full ở Mimi audio Số 42 - …"   (không hashtag)
#   bài script đăng:  "#MimiAudioSo42" (đứng đầu mô tả SEO)
EP_PATTERNS = (re.compile(r"#MimiAudioSo(\d+)", re.IGNORECASE),
               re.compile(r"Mimi\s*audio\s*S[oố]\s*(\d+)", re.IGNORECASE))

# Console Windows hay là cp1252 — ép UTF-8 trước khi in tiếng Việt/emoji.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass


def _env(name: str) -> str:
    """Đọc một biến trong OmniVoice/.env — vài dòng tự parse, khỏi cần dotenv."""
    try:
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


# ── Hỏi Page: đã đăng đến tập nào, lịch xếp đến đâu ─────────────────────────
def _get(session, path: str, **params) -> dict:
    params["access_token"] = TOKEN
    r = session.get(f"{GRAPH}/{path}", params=params, timeout=60)
    data = r.json()
    if "error" in data:
        raise RuntimeError(data["error"].get("message", str(data["error"])))
    return data


def _parse_fbtime(s: str) -> datetime:
    """'2026-08-18T09:00:00+0000' → datetime giờ ĐỊA PHƯƠNG (naive, để so sánh)."""
    return (datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z")
            .astimezone().replace(tzinfo=None))


def page_state(session) -> tuple[set[int], datetime | None, list[str]]:
    """→ (TẬP HỢP số tập đã thấy trên Page, mốc lịch xa nhất, các cảnh báo).

    Trả về cả TẬP HỢP chứ không chỉ số lớn nhất: kênh có lỗ (đăng 52 rồi mà 49
    chưa lên) thì lấy max sẽ bỏ sót vĩnh viễn những tập nằm dưới.

    Gom cả ba nguồn vì bài video xếp lịch có nơi chỉ hiện ở /videos:
      /posts            bài đã đăng            (created_time)
      /scheduled_posts  bài chờ lịch           (scheduled_publish_time)
      /videos           video kể cả chưa đăng  (scheduled_publish_time nếu có)
    Nguồn nào hỏng thì bỏ qua nhưng PHẢI nói ra — thiếu dữ liệu dễ xếp trùng tập.
    Mỗi nguồn lật hết các trang kết quả (Page có hàng trăm bài).
    """
    seen: set[int] = set()
    last_when, warns = None, []
    sources = (
        ("posts", "message,created_time", "created_time"),
        ("scheduled_posts", "message,scheduled_publish_time", "scheduled_publish_time"),
        ("videos", "description,created_time,scheduled_publish_time", "scheduled_publish_time"),
    )
    for edge, fields, when_key in sources:
        try:
            data = _get(session, f"{PAGE_ID}/{edge}", fields=fields, limit=100)
        except Exception as e:
            warns.append(f"⚠️ Không đọc được /{edge}: {e}")
            continue
        for _page_no in range(20):          # trần an toàn: 20 trang × 100 bài
            for item in data.get("data", []):
                text = item.get("message") or item.get("description") or ""
                for pat in EP_PATTERNS:
                    for m in pat.finditer(text):
                        seen.add(int(m.group(1)))
                if item.get(when_key):
                    try:
                        t = _parse_fbtime(item[when_key])
                        if last_when is None or t > last_when:
                            last_when = t
                    except ValueError:
                        pass
            nxt = (data.get("paging") or {}).get("next")
            if not nxt:
                break
            try:
                data = session.get(nxt, timeout=60).json()
                if "error" in data:
                    break
            except Exception:
                break
    return seen, last_when, warns


def save_cache(seen: set[int], last_when: datetime | None) -> None:
    """Ghi những gì vừa đọc được từ Page ra file, để TRANG WEB dựng danh sách
    "tập chưa đăng" mà không phải gọi mạng mỗi lần mở trang."""
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps({
            "eps": sorted(seen),
            "last_when": last_when.isoformat() if last_when else "",
            "fetched": datetime.now().isoformat(timespec="seconds"),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def load_cache() -> dict:
    """Bản đọc Page gần nhất (rỗng nếu chưa quét lần nào)."""
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


# ── Khung giờ 9h / 19h ──────────────────────────────────────────────────────
def next_slot(after: datetime) -> datetime:
    """Khung 09:00/19:00 gần nhất SAU mốc `after` (cùng ngày hoặc hôm sau)."""
    for day_offset in (0, 1):
        day = (after + timedelta(days=day_offset)).date()
        for hour in SLOT_HOURS:
            slot = datetime.combine(day, datetime.min.time()).replace(hour=hour)
            if slot > after:
                return slot
    raise AssertionError("unreachable")


# ── Tập chờ đăng + nội dung bài ─────────────────────────────────────────────
def find_video(folder: Path) -> Path | None:
    """Video dọc của tập — đúng thứ tự nhánh video_doc bên web/core.py."""
    if (folder / "facebook.mp4").exists():
        return folder / "facebook.mp4"
    for pattern in ("facebook *.mp4", "*_doc.mp4"):
        hits = sorted(folder.glob(pattern))
        if hits:
            return hits[0]
    return None


def caption_for(core, folder: Path, episode: str) -> tuple[str, str]:
    """→ (title video, caption bài đăng) — ưu tiên SEO của tập.

    Caption mở đầu bằng tiêu đề kiểu TikTok ("Full ở Mimi audio Số 42 | …") cho
    ĐỒNG BỘ với các bài đã có trên Page, sau đó là mô tả SEO — dòng đầu mô tả
    chính là "#MimiAudioSo<n> …" nên các lần chạy sau nhận ra tập ngay."""
    seo = core.seo_blocks(folder, episode)
    n = int(episode)
    if seo and seo["title"]:
        head = seo["title_tiktok"] or seo["title"]
        desc = (f"{head}\n\n{seo['desc']}" if seo["desc"]
                else f"{head}\n#MimiAudioSo{episode}")
        return seo["title"], desc
    return f"Mimi audio Số {n}", f"Mimi audio Số {n}\n#MimiAudioSo{episode}"


def pending_episodes(core, seen: set[int]) -> tuple[list[dict], list[str]]:
    """Tập CHƯA có trên Page mà đã dựng xong video dọc, cũ → mới.

    Bỏ qua khi: số tập đã thấy trên Page (`seen`), hoặc thư mục tập đã có dấu
    facebook_upload.json (lần chạy trước đã xếp lịch). Kèm ghi chú tập thiếu video.
    """
    out, notes = [], []
    rows = sorted(core.episode_rows(), key=lambda r: int(r["episode"]))
    for r in rows:
        n = int(r["episode"])
        if n in seen:
            continue
        folder = core.episode_folder(r["episode"])
        if folder is None:
            continue
        if (folder / "facebook_upload.json").exists():   # đã xếp lịch lần trước
            continue
        video = find_video(folder)
        if video is None:
            notes.append(f"  · tập {r['episode']}: CHƯA có video dọc — bỏ qua")
            continue
        title, desc = caption_for(core, folder, r["episode"])
        out.append({"ep": r["episode"], "n": n, "folder": folder,
                    "video": video, "title": title, "desc": desc})
    return out, notes


# ── Upload resumable: start → transfer từng khúc → finish ───────────────────
def upload_scheduled(session, item: dict, when: datetime) -> str:
    """Đẩy video lên Page kèm giờ đăng → video_id. Lỗi thì raise."""
    size = item["video"].stat().st_size
    url = f"{GRAPH_VIDEO}/{PAGE_ID}/videos"

    r = session.post(url, data={"access_token": TOKEN, "upload_phase": "start",
                                "file_size": str(size)}, timeout=120).json()
    if "error" in r:
        raise RuntimeError(r["error"].get("message", str(r["error"])))
    upload_id, video_id = r["upload_session_id"], r.get("video_id", "")
    start, end = int(r["start_offset"]), int(r["end_offset"])

    last_pct = -5
    with open(item["video"], "rb") as f:
        while start < size:
            f.seek(start)
            chunk = f.read(end - start)
            for attempt in (1, 2, 3):        # đứt mạng giữa chừng thì thử lại khúc này
                try:
                    r = session.post(
                        url, data={"access_token": TOKEN, "upload_phase": "transfer",
                                   "upload_session_id": upload_id,
                                   "start_offset": str(start)},
                        files={"video_file_chunk": ("chunk", chunk)},
                        timeout=600).json()
                    if "error" in r:
                        raise RuntimeError(r["error"].get("message", str(r["error"])))
                    break
                except Exception:
                    if attempt == 3:
                        raise
                    time.sleep(5 * attempt)
            start, end = int(r["start_offset"]), int(r["end_offset"])
            # In theo NẤC 5% trên dòng riêng — chạy trong hàng đợi web thì mỗi
            # dòng là một mục nhật ký, in mỗi khúc một dòng sẽ ngập log.
            pct = min(100, start * 100 // size)
            if pct >= last_pct + 5:
                print(f"    … {pct}%", flush=True)
                last_pct = pct

    r = session.post(url, data={
        "access_token": TOKEN, "upload_phase": "finish",
        "upload_session_id": upload_id,
        "published": "false",
        "scheduled_publish_time": str(int(when.timestamp())),
        "title": item["title"], "description": item["desc"],
    }, timeout=600).json()
    if "error" in r:
        raise RuntimeError(r["error"].get("message", str(r["error"])))
    return video_id


def main() -> int:
    ap = argparse.ArgumentParser(description="Lên lịch video dọc lên Page MimiAudio (9h/19h)")
    ap.add_argument("--limit", type=int, default=0, help="tối đa bao nhiêu tập lần này (0 = hết)")
    ap.add_argument("--dry-run", action="store_true", help="chỉ in kế hoạch, không đăng")
    ap.add_argument("--yes", action="store_true", help="không hỏi xác nhận")
    ap.add_argument("--only-scan", action="store_true",
                    help="chỉ đọc Page rồi ghi page_cache.json (cho trang web dựng danh sách)")
    ap.add_argument("--tap", default="",
                    help="chỉ các tập này, cách nhau bằng dấu phẩy (vd: 08,49)")
    args = ap.parse_args()

    if not PAGE_ID or not TOKEN:
        print(f"⛔ Thiếu FB_PAGE_ID_MIMIAUDIO / FB_PAGE_ACCESS_TOKEN_MIMIAUDIO trong {ENV_FILE}")
        return 1

    import requests
    session = requests.Session()

    # myvoice.web.core cho danh sách tập + SEO — import muộn vì nó kéo cả module GUI.
    sys.path.insert(0, str(ROOT))
    from myvoice.web import core

    print("🔎 Đang hỏi Page…")
    seen, last_when, warns = page_state(session)
    for w in warns:
        print(w)
    save_cache(seen, last_when)     # để trang web dựng danh sách khỏi gọi mạng
    print(f"   Page đang có {len(seen)} tập"
          + (f" (mới nhất: {max(seen)})" if seen else " (chưa thấy tập nào)")
          + (f" · lịch xa nhất: {last_when:%d/%m %H:%M}" if last_when
             else " · chưa có lịch chờ"))

    queue, notes = pending_episodes(core, seen)
    if notes:
        print("\n".join(notes))

    if args.tap:        # nút "đăng các tập đã tick" trên web gửi danh sách xuống
        want = {t.strip().lstrip("0") or "0" for t in args.tap.split(",") if t.strip()}
        queue = [it for it in queue if str(it["n"]) in want]
    if args.only_scan:
        print(f"📋 Chưa đăng: {', '.join(it['ep'] for it in queue) or '(không có tập nào)'}")
        return 0
    if args.limit > 0:
        queue = queue[: args.limit]
    if not queue:
        print("✅ Không có tập nào cần xếp lịch.")
        return 0

    # Xếp khung 9h/19h nối tiếp sau lịch hiện có (và không sớm hơn now+15').
    cursor = datetime.now() + timedelta(minutes=MIN_LEAD_MIN)
    if last_when and last_when > cursor:
        cursor = last_when
    deadline = datetime.now() + timedelta(days=MAX_AHEAD_DAYS)
    plan, dropped = [], 0
    for item in queue:
        cursor = next_slot(cursor)
        if cursor > deadline:
            dropped += 1
            continue
        plan.append((item, cursor))
    if dropped:
        print(f"⚠️ {dropped} tập rơi ngoài giới hạn {MAX_AHEAD_DAYS} ngày của Facebook"
              " — chạy lại vào hôm khác để xếp tiếp.")
    if not plan:
        print("✅ Không còn khung giờ hợp lệ để xếp.")
        return 0

    print(f"\n📅 Kế hoạch ({len(plan)} tập, khung {SLOT_HOURS[0]}h/{SLOT_HOURS[1]}h):")
    for item, when in plan:
        print(f"  tập {item['ep']} → {when:%a %d/%m %H:%M} · {item['video'].name}"
              f" · {item['title'][:50]}")
    if args.dry_run:
        print("\n(dry-run — chưa đăng gì)")
        return 0
    if not args.yes:
        try:
            ans = input("\nĐăng theo kế hoạch trên? [y/N] ").strip().lower()
        except EOFError:              # chạy nền không có bàn phím (vd hàng đợi web)
            print("⛔ Không có bàn phím để hỏi xác nhận — chạy lại với --yes.")
            return 1
        if ans != "y":
            print("Đã huỷ, chưa đăng gì.")
            return 0

    ok = 0
    for item, when in plan:
        print(f"⬆ Tập {item['ep']} → {when:%d/%m %H:%M} ({item['video'].stat().st_size // 1_000_000} MB)…")
        try:
            video_id = upload_scheduled(session, item, when)
        except Exception as e:
            # Dừng hẳn thay vì đăng tiếp: tập sau mà lên trước tập lỗi thì thứ tự
            # trên Page lộn xộn, sửa tay mệt hơn là chạy lại.
            print(f"\n⛔ Tập {item['ep']} lỗi: {e}\nDừng tại đây — chạy lại để xếp tiếp từ tập này.")
            break
        (item["folder"] / "facebook_upload.json").write_text(
            json.dumps({"video_id": video_id, "scheduled": when.isoformat(),
                        "uploaded_at": datetime.now().isoformat()},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  ✅ đã xếp lịch (video {video_id or '?'})")
        ok += 1
    print(f"\n🏁 Xong: {ok}/{len(plan)} tập đã lên lịch.")
    return 0 if ok == len(plan) else 1


PAGE_ID = _env("FB_PAGE_ID_MIMIAUDIO")
TOKEN = _env("FB_PAGE_ACCESS_TOKEN_MIMIAUDIO")

if __name__ == "__main__":
    # Chạy nhầm python ngoài venv thì tự chạy lại bằng python của dự án.
    if VENV_PY.exists() and Path(sys.executable).resolve() != VENV_PY.resolve():
        import subprocess
        raise SystemExit(subprocess.call([str(VENV_PY), *sys.argv], cwd=str(ROOT)))
    raise SystemExit(main())
