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
COOLDOWN_FILE = Path(__file__).resolve().parent / "cooldown.json"
# SỔ ĐÃ ĐĂNG — nguồn sự thật cho câu hỏi "tập này lên Page chưa". Ghi ở LOCAL để
# việc thường ngày không phải quét lại lịch sử Page (xem chú thích ở load_ledger).
LEDGER_FILE = Path(__file__).resolve().parent / "da_dang.json"
SLOT_HOURS = (9, 19)              # 09:00 sáng · 19:00 tối, giờ máy (VN)
MIN_LEAD_MIN = 15                 # FB đòi lịch cách hiện tại ≥10 phút — chừa 15
MAX_AHEAD_DAYS = 75               # FB không nhận lịch xa hơn ~75 ngày

# Chạm bấy nhiêu phần trăm hạn mức là TỰ NGƯNG, không đợi Meta chặn. Mọi response
# của Graph API đều kèm header hạn mức (X-App-Usage / X-Page-Usage /
# X-Business-Use-Case-Usage) với call_count · total_cputime · total_time tính
# theo %. Chạm trần rồi mới dừng thì đã ăn mã 4/17/32/613 và bị chặn cả giờ.
USAGE_LIMIT_PCT = 75

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


# ── Lỗi Graph API ───────────────────────────────────────────────────────────
# Các mã PHẢI dừng hẳn, tuyệt đối không thử lại: thử lại chỉ tốn thêm lượt gọi
# (đang bị chặn vì quá hạn mức) hoặc chắc chắn hỏng như nhau (token sai).
#   4   · hạn mức ứng dụng          17  · hạn mức người dùng
#   32  · hạn mức Page              613 · vượt tần suất cho phép
#   190 · token hỏng/hết hạn
FATAL_CODES = {4, 17, 32, 613, 190}
FATAL_NOTE = {
    4: "vượt hạn mức của ứng dụng",
    17: "vượt hạn mức của người dùng",
    32: "vượt hạn mức của Page",
    613: "gọi quá dày, vượt tần suất cho phép",
    190: "token hỏng hoặc đã hết hạn",
}


class FbError(RuntimeError):
    """Lỗi Graph API kèm mã. `fatal` = thuộc nhóm phải ngưng hẳn."""

    def __init__(self, err: dict):
        self.code = int(err.get("code") or 0)
        self.subcode = err.get("error_subcode")
        self.msg = err.get("message") or str(err)
        self.fatal = self.code in FATAL_CODES
        note = FATAL_NOTE.get(self.code)
        super().__init__(f"[mã {self.code}] {self.msg}" + (f" — {note}" if note else ""))


def _check(data: dict) -> dict:
    """Trả lại data, hoặc ném FbError nếu Graph trả về lỗi."""
    if isinstance(data, dict) and "error" in data:
        raise FbError(data["error"])
    return data


# ── Hạn mức: đọc header, chạm 75% là tự ngưng ───────────────────────────────
class UsageStop(FbError):
    """Tự ngưng vì hạn mức đã dùng tới ngưỡng — KHÔNG phải Meta chặn.

    Kế thừa FbError với fatal=True để đi chung mọi đường đã có: vòng thử lại của
    bước tải khúc video, vòng đọc Page và vòng đăng nhiều tập đều đã có nhánh
    "fatal thì ném thẳng lên", nên không chỗ nào lỡ thử lại.
    """

    def __init__(self, what: str, pct: float, until: datetime):
        self.code = -1
        self.subcode = None
        self.fatal = True
        self.pct = pct
        self.what = what
        self.until = until
        self.msg = (f"đã dùng {pct:.0f}% hạn mức ({what}) — tự ngưng để khỏi bị "
                    f"Meta chặn, chạy lại sau {until:%H:%M}")
        RuntimeError.__init__(self, self.msg)


def _usage_pct(headers) -> tuple[float, str, int]:
    """→ (phần trăm hạn mức CAO NHẤT, tên chỉ số đó, số phút Meta bảo phải chờ).

    Ba header, cùng ba chỉ số call_count · total_cputime · total_time (đơn vị %):
      X-App-Usage                  hạn mức của ứng dụng
      X-Page-Usage                 hạn mức của Page
      X-Business-Use-Case-Usage    hạn mức theo từng nhóm việc (dict → list)
    Lấy con LỚN NHẤT: chạm trần bất kỳ chỉ số nào cũng bị chặn như nhau.
    """
    worst, what, wait_min = 0.0, "", 0

    def look(tag: str, obj) -> None:
        nonlocal worst, what, wait_min
        if not isinstance(obj, dict):
            return
        for k in ("call_count", "total_cputime", "total_time"):
            v = obj.get(k)
            if isinstance(v, (int, float)) and float(v) > worst:
                worst, what = float(v), f"{tag}·{k}"
        v = obj.get("estimated_time_to_regain_access")
        if isinstance(v, (int, float)):
            wait_min = max(wait_min, int(v))

    for tag, name in (("app", "X-App-Usage"), ("page", "X-Page-Usage")):
        try:
            look(tag, json.loads(headers.get(name) or "{}"))
        except ValueError:
            pass
    try:
        buc = json.loads(headers.get("X-Business-Use-Case-Usage") or "{}")
        for entries in (buc.values() if isinstance(buc, dict) else []):
            for e in (entries if isinstance(entries, list) else []):
                look("buc", e)
    except ValueError:
        pass
    return worst, what, wait_min


_usage_peak = 0.0          # % cao nhất thấy trong lượt chạy này (để in tổng kết)
_usage_told = 0.0          # đã báo tới mốc nào rồi, khỏi in lặp mỗi request


def _resp(r):
    """Đọc header hạn mức rồi mới xử lý thân response.

    Chạm USAGE_LIMIT_PCT là ném UsageStop NGAY, trước cả khi đọc kết quả: cứ gọi
    thêm cho tới lúc Meta trả mã 4/17/32/613 thì đã bị chặn cả tiếng đồng hồ.
    """
    global _usage_peak, _usage_told
    pct, what, wait_min = _usage_pct(r.headers)
    _usage_peak = max(_usage_peak, pct)
    if pct >= 50 and pct >= _usage_told + 10:      # 50 · 60 · 70… in một lần mỗi mốc
        _usage_told = pct
        print(f"   ⏱ hạn mức đã dùng {pct:.0f}% ({what})", flush=True)
    if pct >= USAGE_LIMIT_PCT:
        raise UsageStop(what, pct, _cooldown_until(wait_min))
    return _check(r.json())


def _cooldown_until(wait_min: int = 0) -> datetime:
    """Ngưng tới lúc nào: Meta nói rõ bao lâu thì theo, không thì HẾT GIỜ hiện
    tại (cửa sổ hạn mức của Graph API trượt theo giờ)."""
    now = datetime.now()
    if wait_min > 0:
        return now + timedelta(minutes=wait_min)
    return (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)


def save_cooldown(until: datetime, reason: str) -> None:
    """Ghi mốc được phép chạy lại. Mỗi lần bấm nút trên web là một TIẾN TRÌNH
    MỚI, không nhớ gì của lần trước — nên mốc này phải nằm trên đĩa, không thì
    bấm lại vài lần là vẫn nã đủ request cho tới khi Meta chặn thật."""
    try:
        COOLDOWN_FILE.write_text(json.dumps(
            {"until": until.isoformat(timespec="seconds"), "reason": reason},
            ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def cooldown_left() -> tuple[datetime | None, str]:
    """→ (mốc còn phải chờ, lý do) — (None, "") nếu đang được phép chạy."""
    try:
        d = json.loads(COOLDOWN_FILE.read_text(encoding="utf-8"))
        until = datetime.fromisoformat(d["until"])
    except (OSError, ValueError, KeyError):
        return None, ""
    if datetime.now() >= until:
        try:
            COOLDOWN_FILE.unlink()          # hết hạn rồi thì dọn luôn
        except OSError:
            pass
        return None, ""
    return until, str(d.get("reason", ""))


# ── Hỏi Page: đã đăng đến tập nào, lịch xếp đến đâu ─────────────────────────
def _get(session, path: str, **params) -> dict:
    params["access_token"] = TOKEN
    return _resp(session.get(f"{GRAPH}/{path}", params=params, timeout=60))


def _parse_fbtime(s: str) -> datetime:
    """'2026-08-18T09:00:00+0000' → datetime giờ ĐỊA PHƯƠNG (naive, để so sánh)."""
    return (datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z")
            .astimezone().replace(tzinfo=None))


def latest_time(session) -> tuple[datetime | None, str]:
    """Mốc để xếp lịch tiếp → (thời điểm, nguồn của nó).

    Đây là TẤT CẢ những gì việc đăng thường ngày cần hỏi Page, nên chỉ tốn 1–2
    request:
      1. `/scheduled_posts` — bài đang CHỜ lịch. Lấy giờ xa nhất trong đó; danh
         sách này vốn ngắn (chỉ bài chưa đăng) nên đọc một trang là hết.
      2. Không có bài chờ nào → `/posts?limit=1` lấy bài đăng gần nhất, để không
         xếp đè lên khoảng vừa đăng.
    Tập nào đã đăng thì tra SỔ LOCAL (load_ledger), không hỏi Page.
    """
    try:
        d = _get(session, f"{PAGE_ID}/scheduled_posts",
                 fields="scheduled_publish_time", limit=25)
        times = []
        for item in d.get("data", []):
            if item.get("scheduled_publish_time"):
                try:
                    times.append(_parse_fbtime(item["scheduled_publish_time"]))
                except ValueError:
                    pass
        if times:
            return max(times), f"bài chờ lịch xa nhất ({len(times)} bài đang chờ)"
    except FbError as e:
        if e.fatal:
            raise
        print(f"⚠️ Không đọc được /scheduled_posts: {e}")

    d = _get(session, f"{PAGE_ID}/posts", fields="created_time", limit=1)
    for item in d.get("data", []):
        if item.get("created_time"):
            try:
                return _parse_fbtime(item["created_time"]), "bài đăng gần nhất"
            except ValueError:
                pass
    return None, "Page chưa có bài nào"


def page_state(session, prev: dict | None = None) -> tuple[set[int], datetime | None,
                                                           list[str], bool, dict]:
    """→ (TẬP HỢP số tập thấy trên Page, mốc lịch xa nhất, cảnh báo, ĐỌC ĐỦ chưa,
    mốc mới nhất mỗi nguồn để lần sau quét tiếp).

    Trả về cả TẬP HỢP chứ không chỉ số lớn nhất: kênh có lỗ (đăng 52 rồi mà 49
    chưa lên) thì lấy max sẽ bỏ sót vĩnh viễn những tập nằm dưới.

    Ba nguồn, vì bài video xếp lịch có nơi chỉ hiện ở /videos:
      /posts            bài đã đăng            (created_time)
      /scheduled_posts  bài chờ lịch           (scheduled_publish_time)
      /videos           video kể cả chưa đăng  (scheduled_publish_time nếu có)

    QUÉT GIA TĂNG để khỏi gọi API nhiều: /posts và /videos trả bài mới nhất
    trước, nên chỉ đọc tới bài đã thấy ở lượt quét trước (mốc trong `prev`) rồi
    dừng, phần cũ hơn lấy từ tập hợp đã lưu. Nhờ vậy Page có 100 hay 5000 bài thì
    mỗi lượt vẫn ~3 request, thay vì đọc lại cả lịch sử mỗi lần bấm nút.
    Chưa có cache (lần đầu) thì quét đầy đủ. /scheduled_posts luôn đọc hết vì nó
    chỉ chứa bài CHỜ lịch — vốn ít, mà bài đăng rồi thì rời khỏi danh sách.

    Mã lỗi thuộc FATAL_CODES → NÉM RA NGAY, cả lượt chạy ngưng hẳn. Lỗi khác thì
    ghi cảnh báo và hạ cờ `complete`: đọc thiếu nghĩa là có tập ĐÃ đăng mà mình
    không thấy, xếp lịch tiếp là đăng trùng — nên bên gọi phải từ chối đăng.
    """
    prev = prev or {}
    seen: set[int] = {int(n) for n in prev.get("eps", [])}
    newest_prev: dict = prev.get("newest") or {}
    newest_now: dict = dict(newest_prev)
    last_when, warns, complete = None, [], True

    # (nguồn, fields, khoá thời gian, có được dừng sớm không)
    sources = (
        ("posts", "message,created_time", "created_time", True),
        ("scheduled_posts", "message,scheduled_publish_time", "scheduled_publish_time", False),
        ("videos", "description,created_time,scheduled_publish_time", "scheduled_publish_time", True),
    )
    for edge, fields, when_key, can_stop_early in sources:
        try:
            data = _get(session, f"{PAGE_ID}/{edge}", fields=fields, limit=100)
        except FbError as e:
            if e.fatal:
                raise
            warns.append(f"⚠️ Không đọc được /{edge}: {e}")
            complete = False
            continue
        except Exception as e:
            warns.append(f"⚠️ Không đọc được /{edge}: {e}")
            complete = False
            continue

        boundary = newest_prev.get(edge) if can_stop_early else None
        top_time, stopped_early = None, False
        for page_no in range(20):           # trần an toàn: 20 trang × 100 bài
            for item in data.get("data", []):
                made = item.get("created_time") or item.get(when_key) or ""
                if top_time is None and made:
                    top_time = made          # bài mới nhất lượt này = mốc cho lần sau
                if boundary and made and made <= boundary:
                    stopped_early = True     # tới phần đã quét lần trước → đủ rồi
                    break
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
            if stopped_early:
                break
            nxt = (data.get("paging") or {}).get("next")
            if not nxt:
                break
            if page_no == 19:               # còn trang mà đã chạm trần
                warns.append(f"⚠️ /{edge} còn trang chưa đọc (chạm trần 20 trang).")
                complete = False
                break
            try:
                data = _resp(session.get(nxt, timeout=60))
            except FbError as e:
                if e.fatal:
                    raise
                warns.append(f"⚠️ /{edge} đọc dở giữa chừng: {e}")
                complete = False
                break
            except Exception as e:
                warns.append(f"⚠️ /{edge} đọc dở giữa chừng: {e}")
                complete = False
                break
        if top_time:
            newest_now[edge] = top_time

    # Lịch đã xếp từ các lượt TRƯỚC nằm ngoài phần vừa quét (bài cũ theo
    # created_time nhưng giờ đăng ở tương lai) — lấy lại từ cache, chỉ khi còn ở
    # tương lai; mốc quá khứ không ảnh hưởng chỗ xếp tiếp.
    old_when = prev.get("last_when") or ""
    if old_when:
        try:
            t = datetime.fromisoformat(old_when)
            if t > datetime.now() and (last_when is None or t > last_when):
                last_when = t
        except ValueError:
            pass
    return seen, last_when, warns, complete, newest_now


def save_cache(seen: set[int], last_when: datetime | None, newest: dict) -> None:
    """Ghi những gì vừa đọc được từ Page ra file. Hai công dụng:
      • TRANG WEB dựng danh sách "tập chưa đăng" mà không phải gọi mạng;
      • lượt quét sau chỉ đọc phần MỚI hơn `newest` rồi dừng (xem page_state)."""
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps({
            "eps": sorted(seen),
            "last_when": last_when.isoformat() if last_when else "",
            "newest": newest,
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


# ── Sổ "đã đăng" ở LOCAL ────────────────────────────────────────────────────
def load_ledger() -> dict:
    """Sổ ghi tập nào đã lên Page — {"eps": {"53": {...}}, "synced": "..."}.

    Vì sao ghi local thay vì hỏi Page mỗi lần: chuyện "tập này đăng chưa" chỉ đổi
    khi CHÍNH SCRIPT NÀY đăng thêm, nên ghi lại lúc đăng là đủ và không tốn một
    request nào. Việc quét Page (nút 🔄) chỉ cần khi muốn đối chiếu lại — ví dụ
    có bài đăng tay ngoài script, hoặc dựng lại máy mất sổ.

    Lần đầu chưa có sổ thì dựng từ page_cache.json (kết quả quét trước đó), khỏi
    phải gọi API lại.
    """
    try:
        d = json.loads(LEDGER_FILE.read_text(encoding="utf-8"))
        if isinstance(d.get("eps"), dict):
            return d
    except (OSError, ValueError):
        pass
    cached = {str(int(n)): {"source": "quét Page"} for n in load_cache().get("eps", [])}
    return {"eps": cached, "synced": load_cache().get("fetched", "")}


def save_ledger(led: dict) -> None:
    try:
        LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
        LEDGER_FILE.write_text(json.dumps(led, ensure_ascii=False, indent=2),
                               encoding="utf-8")
    except OSError:
        pass


def mark_posted(led: dict, episode: str, info: dict) -> None:
    """Ghi ngay sau khi Facebook nhận video — ghi trước cả khi in dòng ✅ để lỡ
    tắt máy giữa chừng cũng không đăng lại tập đó lần nữa."""
    led.setdefault("eps", {})[str(int(episode))] = info
    save_ledger(led)


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


def plan_slots(count: int, anchor: datetime | None) -> list[datetime]:
    """Giờ đăng cho `count` tập kế tiếp, nối sau `anchor` (và không sớm hơn
    bây giờ + MIN_LEAD_MIN).

    Tách riêng để TRANG WEB xem trước giờ dự kiến bằng đúng phép tính mà lúc
    chạy thật sẽ dùng — hai bên tính khác nhau thì bảng trên màn hình nói một
    đằng, Facebook nhận một nẻo.
    """
    cursor = datetime.now() + timedelta(minutes=MIN_LEAD_MIN)
    if anchor and anchor > cursor:
        cursor = anchor
    out = []
    for _ in range(max(0, count)):
        cursor = next_slot(cursor)
        out.append(cursor)
    return out


def known_anchor(led: dict) -> datetime | None:
    """Mốc xếp lịch SUY TỪ SỔ LOCAL — cho trang web xem trước mà không gọi API.

    Lấy cái muộn nhất trong: các giờ script đã xếp (ghi trong sổ) và mốc Page đọc
    được ở lần chạy gần nhất. Lúc chạy thật vẫn hỏi lại Page (`latest_time`) rồi
    lấy mốc muộn hơn, nên xem trước lệch thì kết quả thật vẫn đúng.
    """
    times = []
    for info in (led.get("eps") or {}).values():
        if isinstance(info, dict) and info.get("scheduled"):
            try:
                times.append(datetime.fromisoformat(info["scheduled"]))
            except ValueError:
                pass
    when = (led.get("anchor") or {}).get("when")
    if when:
        try:
            times.append(datetime.fromisoformat(when))
        except ValueError:
            pass
    return max(times) if times else None


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
    """→ (tiêu đề bài, caption đầy đủ) — lấy từ SEO của tập.

    Tiêu đề dùng `compose_facebook_title` bên thumbnail_gui: TIÊU ĐỀ YOUTUBE kèm
    bộ hashtag của mô tả, gộp MỘT DÒNG (xem chú thích ở hàm đó). Caption = dòng
    tiêu đề ấy rồi tới mô tả SEO.
    """
    seo = core.seo_blocks(folder, episode)
    n = int(episode)
    if seo and (seo.get("title_facebook") or seo.get("title")):
        head = seo.get("title_facebook") or seo["title"]
        desc = f"{head}\n\n{seo['desc']}" if seo.get("desc") else head
        return head, desc
    head = f"Mimi audio Số {n} #MimiAudioSo{episode}"
    return head, head


def pending_episodes(core, led: dict) -> tuple[list[dict], list[str]]:
    """Tập CHƯA đăng mà đã dựng xong video dọc, cũ → mới.

    "Chưa đăng" tra SỔ LOCAL (`led`) chứ không hỏi Page. Vẫn xét thêm dấu
    facebook_upload.json trong thư mục tập: đó là biên nhận của lần đăng trước,
    giữ lại để lỡ sổ hỏng/mất vẫn không đăng trùng.
    """
    out, notes = [], []
    done = set(led.get("eps") or {})
    rows = sorted(core.episode_rows(), key=lambda r: int(r["episode"]))
    for r in rows:
        n = int(r["episode"])
        if str(n) in done:
            continue
        folder = core.episode_folder(r["episode"])
        if folder is None:
            continue
        if (folder / "facebook_upload.json").exists():   # biên nhận lần đăng trước
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

    r = _resp(session.post(url, data={"access_token": TOKEN, "upload_phase": "start",
                                      "file_size": str(size)}, timeout=120))
    upload_id, video_id = r["upload_session_id"], r.get("video_id", "")
    start, end = int(r["start_offset"]), int(r["end_offset"])

    last_pct = -5
    with open(item["video"], "rb") as f:
        while start < size:
            f.seek(start)
            chunk = f.read(end - start)
            for attempt in (1, 2, 3):        # đứt mạng giữa chừng thì thử lại khúc này
                try:
                    r = _resp(session.post(
                        url, data={"access_token": TOKEN, "upload_phase": "transfer",
                                   "upload_session_id": upload_id,
                                   "start_offset": str(start)},
                        files={"video_file_chunk": ("chunk", chunk)},
                        timeout=600))
                    break
                except FbError as e:
                    # Hạn mức / token hỏng: thử lại vô nghĩa, còn làm nặng thêm
                    # tình trạng đang bị chặn → ném thẳng lên cho main dừng hẳn.
                    if e.fatal:
                        raise
                    if attempt == 3:
                        raise
                    time.sleep(5 * attempt)
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

    _resp(session.post(url, data={
        "access_token": TOKEN, "upload_phase": "finish",
        "upload_session_id": upload_id,
        "published": "false",
        "scheduled_publish_time": str(int(when.timestamp())),
        "title": item["title"], "description": item["desc"],
    }, timeout=600))
    return video_id


def main() -> int:
    ap = argparse.ArgumentParser(description="Lên lịch video dọc lên Page MimiAudio (9h/19h)")
    ap.add_argument("--limit", type=int, default=0, help="tối đa bao nhiêu tập lần này (0 = hết)")
    ap.add_argument("--dry-run", action="store_true", help="chỉ in kế hoạch, không đăng")
    ap.add_argument("--yes", action="store_true", help="không hỏi xác nhận")
    ap.add_argument("--sync", "--only-scan", dest="sync", action="store_true",
                    help="đối chiếu với Page: quét bài trên Page rồi cập nhật sổ đã đăng "
                         "(chỉ cần khi có bài đăng tay ngoài script, hoặc mất sổ)")
    ap.add_argument("--liet-ke", action="store_true",
                    help="chỉ in danh sách tập chưa đăng theo SỔ LOCAL — không gọi API")
    ap.add_argument("--tap", default="",
                    help="chỉ các tập này, cách nhau bằng dấu phẩy (vd: 08,49)")
    args = ap.parse_args()

    if not PAGE_ID or not TOKEN:
        print(f"⛔ Thiếu FB_PAGE_ID_MIMIAUDIO / FB_PAGE_ACCESS_TOKEN_MIMIAUDIO trong {ENV_FILE}")
        return 1

    # Lượt chạy trước đã chạm ngưỡng hạn mức → im lặng chờ hết giờ, kể cả nút
    # 🔄/🔍 (chúng cũng tốn lượt gọi như nhau).
    until, reason = cooldown_left()
    if until:
        left = int((until - datetime.now()).total_seconds() // 60) + 1
        print(f"⏸ Đang tạm ngưng gọi Facebook tới {until:%H:%M} (còn {left} phút).")
        print(f"   Lý do: {reason}")
        return 2

    import requests
    session = requests.Session()

    # myvoice.web.core cho danh sách tập + SEO — import muộn vì nó kéo cả module GUI.
    sys.path.insert(0, str(ROOT))
    from myvoice.web import core

    led = load_ledger()

    # ── Nút 🔄: đối chiếu với Page (việc NẶNG, chỉ chạy khi được yêu cầu) ────
    if args.sync:
        print("🔎 Đang đối chiếu với Page…")
        seen, last_when, warns, complete, newest = page_state(session, load_cache())
        for w in warns:
            print(w)
        if not complete:
            print("⛔ Đọc Page KHÔNG ĐỦ — không cập nhật sổ (sổ thiếu sẽ hoá thành "
                  "đăng trùng). Chạy lại khi mạng/API ổn.")
            return 1
        save_cache(seen, last_when, newest)
        added = [str(n) for n in sorted(seen) if str(n) not in (led.get("eps") or {})]
        for n in added:
            led.setdefault("eps", {})[n] = {"source": "quét Page"}
        led["synced"] = datetime.now().isoformat(timespec="seconds")
        save_ledger(led)
        print(f"   Page đang có {len(seen)} tập · sổ ghi thêm {len(added)} tập"
              + (f": {', '.join(added)}" if added else " (sổ đã khớp)"))
        queue, _ = pending_episodes(core, led)
        print(f"📋 Chưa đăng: {', '.join(it['ep'] for it in queue) or '(không có tập nào)'}")
        return 0

    # ── Việc thường ngày: "đăng chưa" tra SỔ LOCAL, không hỏi Page ──────────
    queue, notes = pending_episodes(core, led)
    if notes:
        print("\n".join(notes))
    print(f"📒 Sổ local: đã đăng {len(led.get('eps') or {})} tập"
          + (f" · đối chiếu Page lần cuối {led['synced'][:16].replace('T', ' ')}"
             if led.get("synced") else " · chưa đối chiếu Page lần nào"))

    if args.tap:        # nút "đăng các tập đã tick" trên web gửi danh sách xuống
        want = {t.strip().lstrip("0") or "0" for t in args.tap.split(",") if t.strip()}
        queue = [it for it in queue if str(it["n"]) in want]
    if args.liet_ke:
        print(f"📋 Chưa đăng: {', '.join(it['ep'] for it in queue) or '(không có tập nào)'}")
        return 0
    if args.limit > 0:
        queue = queue[: args.limit]
    if not queue:
        print("✅ Không có tập nào cần xếp lịch.")
        return 0

    # Hỏi Page ĐÚNG MỘT VIỆC: bài lên lịch/đăng mới nhất, để biết xếp tiếp từ đâu.
    print("🔎 Đang hỏi mốc lịch trên Page…")
    last_when, nguon = latest_time(session)
    print(f"   Mốc: {last_when:%d/%m %H:%M} ({nguon})" if last_when
          else f"   Mốc: — ({nguon})")
    # Nhớ mốc vào sổ để TRANG WEB xem trước giờ dự kiến mà không phải gọi API.
    if last_when:
        led["anchor"] = {"when": last_when.isoformat(timespec="seconds"),
                         "nguon": nguon,
                         "at": datetime.now().isoformat(timespec="seconds")}
        save_ledger(led)

    # Xếp khung 9h/19h nối tiếp sau mốc muộn hơn giữa Page và sổ (lịch script vừa
    # xếp có thể chưa kịp hiện ở /scheduled_posts).
    anchor = max([t for t in (last_when, known_anchor(led)) if t], default=None)
    deadline = datetime.now() + timedelta(days=MAX_AHEAD_DAYS)
    plan, dropped = [], 0
    for item, when in zip(queue, plan_slots(len(queue), anchor)):
        if when > deadline:
            dropped += 1
            continue
        plan.append((item, when))
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
        except FbError as e:
            if e.fatal:
                # Hạn mức / token hỏng: các tập sau chắc chắn hỏng y hệt → ngưng
                # hẳn, ném lên main() in thông báo chung.
                print(f"\n⛔ Tập {item['ep']} lỗi: {e}")
                raise
            # Lỗi lẻ của riêng tập này: vẫn dừng thay vì đăng tiếp — tập sau mà
            # lên trước tập lỗi thì thứ tự trên Page lộn xộn, sửa tay mệt hơn.
            print(f"\n⛔ Tập {item['ep']} lỗi: {e}\nDừng tại đây — chạy lại để xếp tiếp từ tập này.")
            break
        except Exception as e:
            print(f"\n⛔ Tập {item['ep']} lỗi: {e}\nDừng tại đây — chạy lại để xếp tiếp từ tập này.")
            break
        info = {"video_id": video_id, "scheduled": when.isoformat(timespec="seconds"),
                "uploaded_at": datetime.now().isoformat(timespec="seconds"),
                "source": "script"}
        # Ghi SỔ trước, biên nhận trong thư mục tập sau: sổ là chỗ vòng sau tra
        # "đăng chưa", mất nó thì tập này bị xếp lại lần nữa.
        mark_posted(led, item["ep"], info)
        (item["folder"] / "facebook_upload.json").write_text(
            json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  ✅ đã xếp lịch (video {video_id or '?'})")
        ok += 1
    print(f"\n🏁 Xong: {ok}/{len(plan)} tập đã lên lịch.")
    return 0 if ok == len(plan) else 1


PAGE_ID = _env("FB_PAGE_ID_MIMIAUDIO")
TOKEN = _env("FB_PAGE_ACCESS_TOKEN_MIMIAUDIO")

def run() -> int:
    """main() + chốt chặn lỗi PHẢI NGƯNG HẲN (FATAL_CODES).

    Bắt ở đây thay vì rải khắp nơi: chỗ nào ném FbError fatal thì cả lượt chạy
    dừng, in đúng một thông báo nói rõ mã lỗi và việc cần làm. Mã thoát 2 để
    phân biệt với lỗi thường (1) — hàng đợi web hiện đỏ như nhau nhưng đọc nhật
    ký là biết ngay phải xử lý token/hạn mức chứ không phải chạy lại."""
    try:
        rc = main()
        if _usage_peak:
            print(f"⏱ Hạn mức dùng cao nhất lượt này: {_usage_peak:.0f}% "
                  f"(ngưỡng tự ngưng {USAGE_LIMIT_PCT}%).")
        return rc
    except UsageStop as e:
        # Tự ngưng TRƯỚC khi bị chặn: ghi mốc ra đĩa để mọi lần bấm nút sau đó
        # cũng đứng yên tới lúc đó, chứ không phải chỉ tiến trình này.
        save_cooldown(e.until, e.msg)
        print(f"\n⏸ TẠM NGƯNG — {e}")
        print(f"   Các lần chạy tiếp theo sẽ tự đứng yên tới {e.until:%H:%M}. "
              "Tập nào đã xếp lịch xong vẫn giữ nguyên, chạy lại là làm tiếp từ tập dở.")
        return 2
    except FbError as e:
        if not e.fatal:
            print(f"⛔ Lỗi Facebook API: {e}")
            return 1
        print(f"\n⛔ NGƯNG HẲN — {e}")
        if e.code == 190:
            print("   Token Page hỏng/hết hạn: lấy Page access token mới (dài hạn) "
                  f"rồi sửa FB_PAGE_ACCESS_TOKEN_MIMIAUDIO trong {ENV_FILE}.")
        else:
            # Đã bị chặn thật → khoá luôn các lần bấm sau, đúng như khi tự ngưng
            # ở 75%: gọi thêm trong lúc bị chặn chỉ kéo dài thời gian bị chặn.
            until = _cooldown_until()
            save_cooldown(until, str(e))
            print("   Đang bị Facebook chặn vì vượt hạn mức — KHÔNG thử lại ngay "
                  "(gọi thêm chỉ kéo dài thời gian bị chặn). Các lần chạy tiếp theo "
                  f"sẽ tự đứng yên tới {until:%H:%M}; tập đã xếp lịch vẫn giữ nguyên.")
        return 2


PAGE_ID = _env("FB_PAGE_ID_MIMIAUDIO")
TOKEN = _env("FB_PAGE_ACCESS_TOKEN_MIMIAUDIO")

if __name__ == "__main__":
    # Chạy nhầm python ngoài venv thì tự chạy lại bằng python của dự án.
    if VENV_PY.exists() and Path(sys.executable).resolve() != VENV_PY.resolve():
        import subprocess
        raise SystemExit(subprocess.call([str(VENV_PY), *sys.argv], cwd=str(ROOT)))
    raise SystemExit(run())
