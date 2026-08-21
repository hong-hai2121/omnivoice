"""Lên lịch đăng video ĐÃ DỰNG XONG (bước ④, <base>_sub.mp4) lên Page của myvideo.

Bản mang từ myvoice/FACEBOOK/dang_video_facebook.py sang (2026-08-21), giữ nguyên
toàn bộ lớp Graph API + chốt an toàn hạn mức; chỉ đổi phần "cái gì chờ đăng":
tập trong kịch_bản/ → video trong myvideo/output/ (khoá theo `base` của web).

⚠️ HỒ SƠ KÊNH (nhiều tài khoản): mỗi Page một hồ sơ myvideo/kenh/<tên>/ —
page_id + access_token nằm trong facebook.json CỦA HỒ SƠ (token DÀI HẠN, quyền
pages_manage_posts + pages_read_engagement), sổ da_dang/page_cache/cooldown
cũng nằm trọn trong đó nên đổi kênh không lẫn sổ sách (xem myvideo/kenh_hoso.py).
Hồ sơ chưa điền token thì từ chối chạy — TUYỆT ĐỐI không có đường lui sang kênh
MimiAudio của myvoice: đăng nhầm video dịch lên kênh đang chạy là sự cố không
thu hồi được.

Cách chạy:
    venv\\Scripts\\python.exe myvideo\\FACEBOOK\\dang_video_facebook.py --kenh <tên>            → xem kế hoạch rồi hỏi y/N
    venv\\Scripts\\python.exe myvideo\\FACEBOOK\\dang_video_facebook.py --kenh <tên> --dry-run  → chỉ xem, không đăng
    bỏ --kenh        → dùng kênh đang chọn trên web (khoá `kenh` của web_settings.json)
    thêm --limit 4   → mỗi lần chạy chỉ xếp tối đa 4 bài
    thêm --yes       → khỏi hỏi (cho chạy tự động)

Cách hoạt động:
  1. Hỏi Page (Graph API) LỊCH ĐANG CHỜ: /scheduled_posts + /videos, rồi hỏi lại
     từng bài chính script đã xếp (theo video_id trong sổ) bằng một request batch.
     Từ đó biết khung 09:00/19:00 nào đang có bài, bài nào đã bị XOÁ, bài nào bị
     DỜI giờ trong app Facebook.
  2. Video trong myvideo/output/ đã có <base>_sub.mp4 mà chưa đăng là hàng chờ.
     Xếp vào các khung 09:00 / 19:00 CÒN TRỐNG tính từ bây giờ — xoá bài đã lên
     lịch ngày mai thì lần xếp sau lấp lại đúng ngày mai, không đẩy hết ra sau
     bài chờ xa nhất. Đọc Page thiếu (mạng/API lỗi) thì lùi về nếp cũ: nối tiếp
     ngay sau mốc xa nhất, cho khỏi đăng chồng lên bài đã có.
  3. Upload kiểu resumable (start/transfer/finish) — video dài cỡ nào cũng được,
     đứt mạng giữa chừng thì chỉ hỏng bài đang dở, chạy lại là tiếp.

Caption lấy từ <base>_seo.json (nút 📑 SEO trên web sinh ra); chưa có SEO thì
dùng tên video. Mỗi bài được cấp một SỐ BÀI tăng dần và caption luôn kèm hashtag
đánh dấu #OmniVideoSo<n> — lượt quét Page sau nhận lại bài bằng đúng hashtag đó.

Đăng xong ghi biên nhận <base>_facebook_upload.json cạnh video, THEO TỪNG KÊNH
({"<tên kênh>": {…}}) — vừa làm dấu "kênh này xếp lịch bài này rồi" (kênh khác
vẫn đăng được), vừa lưu video_id để tra lại.

Facebook chỉ nhận lịch trong khoảng 10 phút → ~75 ngày tới; bài nào rơi ra
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

if str(ROOT / "myvideo") not in sys.path:
    sys.path.insert(0, str(ROOT / "myvideo"))
import kenh_hoso  # noqa: E402  (hồ sơ kênh — nhiều tài khoản, xem docstring)

GRAPH = "https://graph.facebook.com/v21.0"
GRAPH_VIDEO = "https://graph-video.facebook.com/v21.0"

# Mọi thứ THEO KÊNH do chon_kenh() trỏ vào hồ sơ myvideo/kenh/<tên>/ trước khi
# chạy: Page ID + token, và ba file trạng thái — sổ ĐÃ ĐĂNG (nguồn sự thật cho
# "bài này lên Page chưa", xem load_ledger), bản đọc Page gần nhất, mốc tạm
# ngưng hạn mức. Để None cho gọi nhầm khi CHƯA chọn kênh nổ ngay thay vì âm
# thầm đọc/ghi lung tung.
KENH = ""
PAGE_ID = TOKEN = ""
CACHE_FILE = COOLDOWN_FILE = LEDGER_FILE = None


def chon_kenh(ten: str) -> str:
    """Trỏ token + sổ sách vào hồ sơ kênh `ten` → lỗi hoặc "" nếu ổn.

    ten rỗng = dùng kênh đang chọn trên web (kenh_hoso.hien_tai()). Hồ sơ chưa
    điền facebook.json vẫn trỏ ĐƯỢC (để web còn xem sổ/lịch local) — PAGE_ID/
    TOKEN rỗng thì main() tự chặn trước khi gọi API."""
    global KENH, PAGE_ID, TOKEN, CACHE_FILE, COOLDOWN_FILE, LEDGER_FILE
    ten = (ten or "").strip() or kenh_hoso.hien_tai()
    if not ten:
        return ("chưa chọn hồ sơ kênh nào — tạo/chọn ở khối Đăng bài trên web, "
                "hoặc chạy kèm --kenh <tên>")
    if ten not in kenh_hoso.danh_sach():
        return f"không có hồ sơ kênh “{ten}” trong {kenh_hoso.KENH_DIR}"
    d = kenh_hoso.thu_muc(ten)
    KENH = ten
    PAGE_ID, TOKEN = kenh_hoso.fb_config(ten)
    CACHE_FILE = d / "page_cache.json"
    COOLDOWN_FILE = d / "cooldown.json"
    LEDGER_FILE = d / "da_dang.json"
    return ""
SLOT_HOURS = (9, 19)              # 09:00 sáng · 19:00 tối, giờ máy (VN)
MIN_LEAD_MIN = 15                 # FB đòi lịch cách hiện tại ≥10 phút — chừa 15
MAX_AHEAD_DAYS = 75               # FB không nhận lịch xa hơn ~75 ngày

# Chạm bấy nhiêu phần trăm hạn mức là TỰ NGƯNG, không đợi Meta chặn. Mọi response
# của Graph API đều kèm header hạn mức (X-App-Usage / X-Page-Usage /
# X-Business-Use-Case-Usage) với call_count · total_cputime · total_time tính
# theo %. Chạm trần rồi mới dừng thì đã ăn mã 4/17/32/613 và bị chặn cả giờ.
USAGE_LIMIT_PCT = 75

# Số bài trong bài đăng — kênh MỚI chỉ có bài do script này đăng nên chỉ cần
# đúng một kiểu hashtag đánh dấu "#OmniVideoSo<n>" (script tự chèn vào caption).
# Số bài là số thứ tự cấp phát trong sổ da_dang.json, KHÔNG phải số tập nội dung.
EP_PATTERNS = (re.compile(r"#OmniVideoSo(\d+)", re.IGNORECASE),)

# Console Windows hay là cp1252 — ép UTF-8 trước khi in tiếng Việt/emoji.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass


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


def _parse_fbtime(s) -> datetime:
    """Mốc thời gian của Graph API → datetime giờ ĐỊA PHƯƠNG (naive, để so sánh).

    Graph trả về HAI kiểu cho cùng một ý: chuỗi ISO '2026-08-18T09:00:00+0000'
    (/posts, /videos) và SỐ GIÂY epoch 1755500400 (/scheduled_posts, batch). Nhận
    cả hai ở một chỗ, không thì mỗi nơi gọi lại phải tự đoán kiểu.
    Kiểu lạ → ValueError, đúng nhánh mà mọi chỗ gọi đang bắt sẵn.
    """
    if isinstance(s, (int, float)) or (isinstance(s, str) and s.isdecimal()):
        try:
            return datetime.fromtimestamp(int(s))
        except (OverflowError, OSError) as e:
            raise ValueError(f"mốc thời gian không hợp lệ: {s!r}") from e
    if not isinstance(s, str):
        raise ValueError(f"mốc thời gian không hợp lệ: {s!r}")
    return (datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z")
            .astimezone().replace(tzinfo=None))


def _ep_of(text: str) -> int | None:
    """Số bài đọc từ nội dung bài đăng (hashtag đánh dấu #OmniVideoSo42)."""
    for pat in EP_PATTERNS:
        m = pat.search(text or "")
        if m:
            return int(m.group(1))
    return None


def fetch_scheduled(session) -> tuple[list[dict], list[str], bool]:
    """Bài ĐANG CHỜ LỊCH trên Page → ([{when, ep, id, edge}], cảnh báo, đọc đủ chưa).

    Chỉ lấy mốc còn ở TƯƠNG LAI — đó là thứ quyết định khung 9h/19h nào còn trống.
    Hai nguồn vì bài video xếp lịch có nơi chỉ hiện ở một chỗ:
      /scheduled_posts  danh sách chờ lịch — vốn ngắn (đăng rồi là rời danh sách)
                        nên đọc hết, trần 5 trang.
      /videos           video chưa đăng còn scheduled_publish_time. Video tải lên
                        sau nằm TRÊN CÙNG (sắp theo created_time) nên chỉ đọc
                        tiếp chừng nào trang vừa đọc còn thấy bài chờ lịch.

    complete=False nghĩa là đọc thiếu → bên gọi phải coi như CHƯA BIẾT chỗ trống;
    lấp chỗ trống lúc đó dễ xếp chồng lên bài đã có.
    """
    now = datetime.now()
    found: dict[tuple, dict] = {}
    warns, complete = [], True

    def take(item: dict, edge: str) -> bool:
        raw = item.get("scheduled_publish_time")
        if not raw:
            return False
        try:
            when = _parse_fbtime(raw)
        except ValueError:
            return False
        if when <= now:                    # đã đăng rồi thì không chiếm khung nào nữa
            return False
        ep = _ep_of(item.get("message") or item.get("description") or "")
        pid = str(item.get("id") or "")
        # Cùng một bài hiện ở cả hai edge với id khác nhau (id bài đăng vs id
        # video) → gộp theo (tập, giờ) khi đọc được số tập.
        key = (ep, when) if ep is not None else (pid, when)
        found.setdefault(key, {"when": when, "ep": ep, "id": pid, "edge": edge})
        return True

    for edge, fields, keep_paging in (
            ("scheduled_posts", "id,message,scheduled_publish_time", True),
            ("videos", "id,description,scheduled_publish_time,created_time", False)):
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
        for _page_no in range(5):
            hits = sum(1 for item in data.get("data", []) if take(item, edge))
            nxt = (data.get("paging") or {}).get("next")
            # /videos: trang này hết bài chờ lịch là dừng — phần sau toàn video đã
            # đăng, đọc thêm chỉ tốn lượt gọi.
            if not nxt or (not keep_paging and not hits):
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
    return sorted(found.values(), key=lambda x: x["when"]), warns, complete


# "Bài không còn nữa" — chỉ nhận đúng hai dạng trả lời này. Mọi lỗi khác (mạng
# chập, thiếu quyền, hạn mức, hỏi sai tên trường) KHÔNG được hiểu là đã xoá:
# nhầm chỗ này là tập đó bị xếp lịch lần thứ hai, đăng trùng lên Page.
#   mã 100 + error_subcode 33 (hoặc câu "does not exist") · id không tra được
#   mã 803                                                · đối tượng đã biến mất
def _looks_gone(err: dict) -> bool:
    code = int(err.get("code") or 0)
    if code == 803:
        return True
    if code != 100:
        return False
    if int(err.get("error_subcode") or 0) == 33:
        return True
    msg = str(err.get("message") or "").lower()
    return "does not exist" in msg or "cannot be loaded" in msg


def _sched_of(body: dict) -> datetime | None:
    """scheduled_publish_time trong trả lời batch (epoch hoặc ISO — xem
    _parse_fbtime) → None nếu bài không còn hẹn giờ nữa."""
    raw = body.get("scheduled_publish_time")
    if not raw:
        return None
    try:
        return _parse_fbtime(raw)
    except ValueError:
        return None


def verify_ledger(session, led: dict) -> tuple[dict, dict, list[str], bool]:
    """Đối chiếu từng bài SCRIPT ĐÃ XẾP còn ở tương lai với Page.

    Một request BATCH hỏi cùng lúc mọi video_id trong sổ có giờ đăng ở tương lai:
      · còn trên Page → lấy giờ HIỆN TẠI (dời giờ trong app Facebook thì theo)
      · mất           → bài đã bị xoá, tập đó phải quay lại hàng chờ
    → ({tập: giờ trên Page}, {tập: giờ cũ của bài đã mất}, cảnh báo, hỏi đủ chưa)

    Hỏi thẳng từng video_id chứ không suy từ /scheduled_posts: bài chờ lịch dạng
    video có lúc không hiện ở edge đó, mà nhầm "không thấy" thành "đã xoá" là
    đăng trùng cả loạt.
    """
    now = datetime.now()
    want = []                     # [(tập, video_id, giờ đang ghi trong sổ)]
    for ep, info in sorted((led.get("eps") or {}).items(), key=lambda kv: int(kv[0])):
        if not isinstance(info, dict) or not info.get("video_id"):
            continue
        try:
            when = datetime.fromisoformat(info.get("scheduled") or "")
        except ValueError:
            continue
        if when > now:
            want.append((ep, str(info["video_id"]), when))
    if not want:
        return {}, {}, [], True

    alive, gone, warns, complete = {}, {}, [], True
    for start in range(0, len(want), 50):            # batch tối đa 50 việc con
        chunk = want[start:start + 50]
        # Chỉ hỏi scheduled_publish_time: hỏi thêm trường mà node video không có
        # thì Graph trả về mã 100 y như id đã xoá, hoá ra tự nhận nhầm là mất bài.
        batch = [{"method": "GET", "relative_url": f"{vid}?fields=scheduled_publish_time"}
                 for _ep, vid, _when in chunk]
        try:
            res = _resp(session.post(GRAPH, data={
                "access_token": TOKEN, "include_headers": "false",
                "batch": json.dumps(batch)}, timeout=120))
        except FbError as e:
            if e.fatal:
                raise
            warns.append(f"⚠️ Không hỏi được các bài đã xếp: {e}")
            return alive, {}, warns, False
        except Exception as e:
            warns.append(f"⚠️ Không hỏi được các bài đã xếp: {e}")
            return alive, {}, warns, False
        if not isinstance(res, list) or len(res) != len(chunk):
            warns.append("⚠️ Trả lời batch không khớp số bài đã hỏi — bỏ qua bước đối chiếu.")
            return alive, {}, warns, False
        for (ep, _vid, old), part in zip(chunk, res):
            code = (part or {}).get("code")
            try:
                body = json.loads((part or {}).get("body") or "{}")
            except ValueError:
                body = {}
            if code == 200 and "error" not in body:
                alive[ep] = _sched_of(body) or old
                continue
            err = body.get("error") or {}
            ecode = int(err.get("code") or 0)
            if ecode in FATAL_CODES:
                raise FbError(err)
            if _looks_gone(err):
                gone[ep] = old
                continue
            warns.append(f"⚠️ Không tra được bài của tập {ep}: [mã {ecode}] "
                         f"{err.get('message') or code}")
            complete = False
    return alive, gone, warns, complete


def page_schedule(session, led: dict) -> dict:
    """Ảnh chụp LỊCH ĐANG CÓ trên Page — nền để biết khung nào còn trống.

    → {"slots": [{when, ep, id, edge}], "gone": {tập: giờ cũ},
       "moved": {tập: giờ mới}, "warns": [...], "complete": bool}

    Gộp hai đường: đọc danh sách chờ lịch của Page, và hỏi lại từng bài chính
    script đã xếp (bài vừa tải lên có khi chưa kịp hiện ở /scheduled_posts).
    """
    sched, warns, ok_sched = fetch_scheduled(session)
    alive, gone, warns2, ok_led = verify_ledger(session, led)
    slots = [dict(s) for s in sched]
    have = {(s["ep"], s["when"].replace(second=0, microsecond=0))
            for s in sched if s["ep"] is not None}
    moved = {}
    for ep, when in alive.items():
        try:
            old = datetime.fromisoformat(
                ((led.get("eps") or {}).get(ep) or {}).get("scheduled") or "")
        except ValueError:
            old = None
        if old and abs((when - old).total_seconds()) > 60:
            moved[ep] = when
        if (int(ep), when.replace(second=0, microsecond=0)) not in have:
            slots.append({"when": when, "ep": int(ep), "id": "", "edge": "sổ"})

    # Bài trong sổ KHÔNG có video_id (ghi từ đời cũ) thì không tra thẳng được →
    # cứ coi khung đó là bận. Thà bỏ trống một khung còn hơn đăng chồng lên bài
    # cũ mà mình không tra ra.
    now = datetime.now()
    for ep, info in (led.get("eps") or {}).items():
        if not isinstance(info, dict) or info.get("video_id") or not info.get("scheduled"):
            continue
        try:
            when = datetime.fromisoformat(info["scheduled"])
        except ValueError:
            continue
        if when > now:
            slots.append({"when": when, "ep": int(ep), "id": "", "edge": "sổ (chưa tra được)"})
    slots.sort(key=lambda s: s["when"])
    return {"slots": slots, "gone": gone, "moved": moved,
            "warns": warns + warns2, "complete": ok_sched and ok_led}


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


def _write_cache(data: dict) -> None:
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    except OSError:
        pass


def save_cache(seen: set[int], last_when: datetime | None, newest: dict) -> None:
    """Ghi những gì vừa đọc được từ Page ra file. Hai công dụng:
      • TRANG WEB dựng danh sách "tập chưa đăng" mà không phải gọi mạng;
      • lượt quét sau chỉ đọc phần MỚI hơn `newest` rồi dừng (xem page_state).

    Phần LỊCH (slots) do save_slots ghi, ở đây chỉ chép lại nguyên si — hai thứ
    đọc bằng hai đường khác nhau, ghi đè lẫn nhau là mất lịch vừa đọc được."""
    old = load_cache()
    _write_cache({
        "eps": sorted(seen),
        "last_when": last_when.isoformat() if last_when else "",
        "newest": newest,
        "fetched": datetime.now().isoformat(timespec="seconds"),
        "slots": old.get("slots") or [],
        "slots_at": old.get("slots_at", ""),
    })


def save_slots(slots: list[dict]) -> None:
    """Ghi LỊCH ĐANG CÓ trên Page vừa đọc được (giữ nguyên phần còn lại của file).

    Trang web xem trước giờ đăng bằng chính bản này: biết khung nào bận thì bảng
    "chưa đăng" hiện đúng ngày dự kiến mà không phải gọi API mỗi lần mở trang.
    """
    d = load_cache()
    d["slots"] = [{"when": s["when"].isoformat(timespec="minutes"),
                   "ep": s.get("ep"), "src": s.get("edge") or s.get("src") or ""}
                  for s in slots]
    d["slots_at"] = datetime.now().isoformat(timespec="seconds")
    _write_cache(d)


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


def slot_key(t: datetime) -> datetime:
    """Khung 9h/19h mà mốc `t` CHIẾM CHỖ — khung gần nó nhất.

    Bài đăng tay hiếm khi rơi đúng 09:00/19:00; không quy về khung thì bài 09:12
    vẫn bị coi là khung trống rồi xếp thêm một bài nữa chồng lên.
    """
    best = None
    for day_offset in (-1, 0, 1):
        day = (t + timedelta(days=day_offset)).date()
        for hour in SLOT_HOURS:
            slot = datetime.combine(day, datetime.min.time()).replace(hour=hour)
            if best is None or abs(slot - t) < abs(best - t):
                best = slot
    return best


def plan_slots(count: int, anchor: datetime | None,
               busy: list[datetime] | None = None) -> list[datetime]:
    """Giờ đăng cho `count` tập kế tiếp (không sớm hơn bây giờ + MIN_LEAD_MIN).

    `busy` = các mốc ĐÃ CÓ BÀI trên Page (đọc bằng page_schedule). Có busy thì
    LẤP CHỖ TRỐNG: duyệt khung 9h/19h từ bây giờ, khung nào chưa có bài thì lấy.
    Nhờ vậy xoá bớt bài đã lên lịch là lần sau lấp lại đúng chỗ đó, chứ không đẩy
    hết ra sau mốc xa nhất — mà mốc xa nhất ấy có khi là bài đã bị xoá.

    busy=None (chưa đọc được lịch Page lần nào) thì giữ nếp cũ: nối tiếp sau
    `anchor`. Không biết khung nào bận mà cứ lấp thì dễ đăng chồng lên bài đã có.

    Tách riêng để TRANG WEB xem trước giờ dự kiến bằng đúng phép tính mà lúc
    chạy thật sẽ dùng — hai bên tính khác nhau thì bảng trên màn hình nói một
    đằng, Facebook nhận một nẻo.
    """
    cursor = datetime.now() + timedelta(minutes=MIN_LEAD_MIN)
    if busy is None and anchor and anchor > cursor:
        cursor = anchor
    taken = {slot_key(t) for t in (busy or [])}
    out: list[datetime] = []
    while len(out) < max(0, count):
        cursor = next_slot(cursor)
        if cursor in taken:
            continue                       # khung này đã có bài → xét khung sau
        out.append(cursor)
    return out


def known_anchor(led: dict) -> datetime | None:
    """Mốc xếp lịch SUY TỪ SỔ LOCAL — cho trang web xem trước mà không gọi API.

    Lấy cái muộn nhất trong: các giờ script đã xếp (ghi trong sổ) và mốc Page đọc
    được ở lần chạy gần nhất. Chỉ còn dùng làm ĐƯỜNG LUI cho lúc đọc lịch Page
    không đủ; bình thường đã có `known_busy` (biết từng khung bận/trống) nên xem
    trước bằng đúng phép tính mà lúc chạy thật sẽ dùng.
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


def known_busy(led: dict | None = None,
               cache: dict | None = None) -> list[datetime] | None:
    """Các mốc ĐÃ CÓ BÀI suy từ dữ liệu LOCAL — cho trang web xem trước giờ đăng
    mà không gọi API.

    Gộp hai nguồn: lịch đọc được ở lần bấm 🔄 gần nhất (page_cache.json) và các
    bài chính script vừa xếp (sổ da_dang.json) — bài mới xếp có khi chưa kịp hiện
    ở /scheduled_posts.

    → None khi CHƯA từng đọc lịch Page lần nào; lúc đó plan_slots giữ nếp cũ
    (nối sau mốc xa nhất) thay vì tưởng mọi khung đều trống.
    """
    led = load_ledger() if led is None else led
    cache = load_cache() if cache is None else cache
    if not cache.get("slots_at"):
        return None
    now, out = datetime.now(), []
    for s in cache.get("slots") or []:
        try:
            t = datetime.fromisoformat(str(s.get("when")))
        except (TypeError, ValueError):
            continue
        if t > now:
            out.append(t)
    for info in (led.get("eps") or {}).values():
        if not isinstance(info, dict) or not info.get("scheduled"):
            continue
        try:
            t = datetime.fromisoformat(info["scheduled"])
        except ValueError:
            continue
        if t > now:
            out.append(t)
    return out


# ── Video chờ đăng + nội dung bài ───────────────────────────────────────────
OUTPUT_DIR = ROOT / "myvideo" / "output"
_XTAG_CUOI = re.compile(r"_x\d+(?:\.\d+)?$")


def receipt_path(base: str) -> Path:
    """Biên nhận đăng Page của một video — <base>_facebook_upload.json cạnh video.

    Đặt theo đúng nếp hậu tố `_…` của các file kết quả nên bảng web coi nó là
    file của hàng đó: bấm 🗑 xoá hàng là biên nhận đi theo vào Thùng rác."""
    return OUTPUT_DIR / f"{base}_facebook_upload.json"


def ten_hienthi(base: str) -> str:
    """Tên video cho người đọc: phần tên trong `base`, cắt tag _x… cuối."""
    name = base.split("/")[-1]
    m = _XTAG_CUOI.search(name)
    return name[: m.start()] if m else name


def marker_alive(receipt: Path) -> bool:
    """Biên nhận đăng Page của KÊNH ĐANG CHỌN còn hiệu lực không.

    Biên nhận ghi THEO KÊNH ({tên kênh: {…}}) — chỉ xét mục của KENH, video đã
    lên kênh khác vẫn đăng được lên kênh này. Mục bị đánh dấu `removed_from_page`
    (nút 🔄 thấy bài đã bị xoá khỏi Page) thì hết chặn: giữ nguyên (còn video_id
    để tra lại) nhưng video quay lại hàng chờ; bỏ dòng dấu là hoàn nguyên.
    """
    if not receipt.exists():
        return False
    try:
        json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True            # đọc không được thì cứ coi là đã đăng, an toàn hơn
    info = kenh_hoso.doc_bien_nhan(receipt).get(KENH)
    return bool(info) and not info.get("removed_from_page")


def unmark_removed(receipt: Path) -> None:
    """Đánh dấu mục của KÊNH ĐANG CHỌN trong biên nhận là "bài không còn trên
    Page" — giữ nguyên phần còn lại (mục kênh khác, video_id để tra lại); sau
    đó video lại hiện trong hàng chờ của kênh này (xem marker_alive)."""
    info = kenh_hoso.doc_bien_nhan(receipt).get(KENH)
    if not info:
        return
    info["removed_from_page"] = datetime.now().isoformat(timespec="seconds")
    try:
        kenh_hoso.ghi_bien_nhan(receipt, KENH, info)
    except OSError:
        pass


def load_seo(base: str) -> dict:
    """SEO của video — <base>_seo.json do nút 📑 SEO trên web sinh (nếu có)."""
    try:
        d = json.loads((OUTPUT_DIR / f"{base}_seo.json").read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def caption_for(base: str, n: int) -> tuple[str, str]:
    """→ (tiêu đề bài, caption đầy đủ).

    Tiêu đề lấy từ <base>_seo.json nếu có, không thì dùng tên video; LUÔN kèm
    hashtag đánh dấu #OmniVideoSo<n> ngay trên dòng tiêu đề — bảng tin Facebook
    cắt bằng "Xem thêm" nên hashtag để dưới mô tả dài coi như không ai thấy, và
    lượt quét Page sau nhận lại bài bằng đúng hashtag này (xem EP_PATTERNS).
    """
    seo = load_seo(base)
    head = (seo.get("title") or "").strip() or ten_hienthi(base)
    head = f"{head} #OmniVideoSo{n}"
    desc = (seo.get("desc") or "").strip()
    return head, (f"{head}\n\n{desc}" if desc else head)


def next_numbers(led: dict, count: int) -> list[int]:
    """`count` SỐ BÀI kế tiếp — nối sau số lớn nhất từng thấy ở cả sổ local lẫn
    cache Page, để không cấp lại số của bài đã có trên Page nhưng rơi khỏi sổ."""
    used = [0]
    for k in led.get("eps") or {}:
        try:
            used.append(int(k))
        except (TypeError, ValueError):
            pass
    for k in load_cache().get("eps") or []:
        try:
            used.append(int(k))
        except (TypeError, ValueError):
            pass
    start = max(used) + 1
    return list(range(start, start + max(0, count)))


def pending_videos(led: dict) -> tuple[list[dict], list[str]]:
    """Video ĐÃ DỰNG XONG (bước ④ ra <base>_sub.mp4) mà chưa đăng, cũ → mới.

    "Chưa đăng" tra SỔ LOCAL (`led`) theo `base` chứ không hỏi Page. Vẫn xét
    thêm biên nhận <base>_facebook_upload.json: đó là dấu của lần đăng trước,
    giữ lại để lỡ sổ hỏng/mất vẫn không đăng trùng. Video đang dựng dở (chưa có
    _sub.mp4) không tính là chờ — dựng xong tự nhiên vào hàng.

    Số bài (#OmniVideoSo<n>) cấp phát tại đây, nối tiếp sổ; hàng đợi đăng chỉ
    MỘT worker nên không có hai lượt chạy giành nhau cùng một số.
    """
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from myvideo.web import steps as st

    out, notes = [], []
    done = {info.get("base") for info in (led.get("eps") or {}).values()
            if isinstance(info, dict) and info.get("base")}
    rows = st.scan_rows(limit=500)
    rows.reverse()                        # scan_rows trả mới → cũ; đăng thì cũ trước
    for r in rows:
        if not r["sub"] or r["base"] in done:
            continue
        if marker_alive(receipt_path(r["base"])):
            continue
        out.append({"base": r["base"],
                    "video": OUTPUT_DIR / f"{r['base']}_sub.mp4"})
    for it, n in zip(out, next_numbers(led, len(out))):
        it["n"], it["ep"] = n, str(n)
        it["title"], it["desc"] = caption_for(it["base"], n)
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
    ap = argparse.ArgumentParser(description="Lên lịch video đã dựng xong lên Page của myvideo (9h/19h)")
    ap.add_argument("--limit", type=int, default=0, help="tối đa bao nhiêu bài lần này (0 = hết)")
    ap.add_argument("--dry-run", action="store_true", help="chỉ in kế hoạch, không đăng")
    ap.add_argument("--yes", action="store_true", help="không hỏi xác nhận")
    ap.add_argument("--sync", "--only-scan", dest="sync", action="store_true",
                    help="đối chiếu với Page: quét bài trên Page rồi cập nhật sổ đã đăng "
                         "(chỉ cần khi có bài đăng tay ngoài script, hoặc mất sổ)")
    ap.add_argument("--liet-ke", action="store_true",
                    help="chỉ in danh sách video chưa đăng theo SỔ LOCAL — không gọi API")
    ap.add_argument("--chon", action="append", default=[],
                    help="chỉ các video này (base trong output, lặp cờ cho nhiều video)")
    ap.add_argument("--kenh", default="",
                    help="hồ sơ kênh trong myvideo/kenh/ (bỏ trống = kênh đang "
                         "chọn trên web)")
    args = ap.parse_args()

    loi_kenh = chon_kenh(args.kenh)
    if loi_kenh:
        print(f"⛔ {loi_kenh}")
        return 1
    print(f"📡 Hồ sơ kênh: {KENH}")
    if not PAGE_ID or not TOKEN:
        print(f"⏳ Hồ sơ “{KENH}” chưa điền Page: mở "
              f"{kenh_hoso.thu_muc(KENH) / 'facebook.json'} điền page_id + "
              "access_token (token Page DÀI HẠN) rồi chạy lại.")
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

    led = load_ledger()

    # ── Nút 🔄: đối chiếu với Page (việc NẶNG, chỉ chạy khi được yêu cầu) ────
    if args.sync:
        print("🔎 Đang đối chiếu với Page…")
        seen, last_when, warns, complete, newest = page_state(session, load_cache())
        snap = page_schedule(session, led)          # lịch ĐANG CÓ trên Page
        for w in warns + snap["warns"]:
            print(w)
        if not complete or not snap["complete"]:
            print("⛔ Đọc Page KHÔNG ĐỦ — không cập nhật sổ (sổ thiếu sẽ hoá thành "
                  "đăng trùng). Chạy lại khi mạng/API ổn.")
            return 1

        # Bài đã bị XOÁ khỏi Page → gạch khỏi sổ để tập đó quay lại hàng chờ, và
        # trả khung giờ ấy về chỗ trống. Đây chính là việc mà nút này sinh ra:
        # xoá bài trên Facebook rồi thì lần xếp sau phải lấp lại đúng chỗ đó.
        # … trừ khi Page đang có bài KHÁC của đúng tập ấy chờ lịch (xoá bài cũ rồi
        # đăng/xếp lại bằng tay): tập đó vẫn sẽ lên, gạch khỏi sổ là đăng trùng.
        sched_eps = {sl["ep"] for sl in snap["slots"] if sl["ep"]}
        for ep, old in sorted(snap["gone"].items(), key=lambda kv: int(kv[0])):
            if int(ep) in sched_eps:
                print(f"   ↔ bài {ep}: bài cũ không còn, nhưng Page đang có bài khác "
                      "cùng số chờ lịch → giữ nguyên trong sổ")
                continue
            info = (led.get("eps") or {}).pop(ep, None)
            seen.discard(int(ep))
            if isinstance(info, dict) and info.get("base"):
                unmark_removed(receipt_path(info["base"]))
            print(f"   ❌ bài {ep}: bài lên lịch {old:%d/%m %H:%M} không còn trên "
                  "Page → đưa lại vào hàng chờ")
        # Dời giờ trong app Facebook thì sổ theo giờ mới (để xem trước khỏi lệch).
        for ep, when in sorted(snap["moved"].items(), key=lambda kv: int(kv[0])):
            info = (led.get("eps") or {}).get(ep)
            if isinstance(info, dict):
                info["scheduled"] = when.isoformat(timespec="seconds")
            print(f"   ↔ bài {ep}: đã dời sang {when:%d/%m %H:%M}")

        # Mốc xa nhất lấy theo LỊCH VỪA ĐỌC, không giữ mốc cũ trong cache: mốc cũ
        # có khi chính là bài vừa bị xoá.
        if snap["slots"]:
            last_when = max(sl["when"] for sl in snap["slots"])
        save_cache(seen, last_when, newest)
        save_slots(snap["slots"])
        added = [str(n) for n in sorted(seen) if str(n) not in (led.get("eps") or {})]
        for n in added:
            led.setdefault("eps", {})[n] = {"source": "quét Page"}
        led["synced"] = datetime.now().isoformat(timespec="seconds")
        save_ledger(led)
        print(f"   Page đang có {len(seen)} bài · sổ ghi thêm {len(added)} bài"
              + (f": {', '.join(added)}" if added else " (sổ đã khớp)"))

        print(f"\n📅 Lịch đang chờ trên Page ({len(snap['slots'])} bài):")
        for sl in snap["slots"]:
            print(f"   {sl['when']:%a %d/%m %H:%M} · "
                  + (f"bài {sl['ep']}" if sl["ep"] else "(bài khác)"))
        if not snap["slots"]:
            print("   (không còn bài nào chờ đăng)")

        queue, _ = pending_videos(led)
        print(f"\n📋 Chưa đăng: "
              f"{', '.join(ten_hienthi(it['base']) for it in queue) or '(không có video nào)'}")
        if queue:
            print("   Khung trống sẽ nhận các video này:")
            for it, when in zip(queue, plan_slots(len(queue), None,
                                                  known_busy(led, load_cache()))):
                print(f"   · {ten_hienthi(it['base'])} → {when:%a %d/%m %H:%M}")
        return 0

    # ── Việc thường ngày: "đăng chưa" tra SỔ LOCAL, không hỏi Page ──────────
    queue, notes = pending_videos(led)
    if notes:
        print("\n".join(notes))
    print(f"📒 Sổ local: đã đăng {len(led.get('eps') or {})} bài"
          + (f" · đối chiếu Page lần cuối {led['synced'][:16].replace('T', ' ')}"
             if led.get("synced") else " · chưa đối chiếu Page lần nào"))

    if args.chon:       # nút "đăng các video đã tick" trên web gửi danh sách base
        want = set(args.chon)
        queue = [it for it in queue if it["base"] in want]
    if args.liet_ke:
        print(f"📋 Chưa đăng: "
              f"{', '.join(ten_hienthi(it['base']) for it in queue) or '(không có video nào)'}")
        return 0
    if args.limit > 0:
        queue = queue[: args.limit]
    if not queue:
        print("✅ Không có video nào cần xếp lịch.")
        return 0

    # Hỏi Page LỊCH ĐANG CHỜ để biết khung 9h/19h nào còn trống.
    print("🔎 Đang đọc lịch đang chờ trên Page…")
    snap = page_schedule(session, led)
    for w in snap["warns"]:
        print(w)
    busy = [sl["when"] for sl in snap["slots"]]
    last_when = max(busy) if busy else None
    print(f"   Đang chờ {len(busy)} bài · xa nhất {last_when:%d/%m %H:%M}" if last_when
          else "   Page không còn bài nào chờ lịch")
    if snap["gone"]:
        print("⚠️ " + ", ".join(f"bài {ep}" for ep in sorted(snap["gone"], key=int))
              + " đã bị xoá khỏi Page — bấm 🔄 Cập nhật lịch Page để đưa lại vào hàng chờ.")
    for ep, when in snap["moved"].items():      # dời giờ trong app Facebook
        info = (led.get("eps") or {}).get(ep)
        if isinstance(info, dict):
            info["scheduled"] = when.isoformat(timespec="seconds")
    # Nhớ mốc + lịch vừa đọc để TRANG WEB xem trước giờ dự kiến, khỏi gọi API.
    if last_when:
        led["anchor"] = {"when": last_when.isoformat(timespec="seconds"),
                         "nguon": "bài chờ lịch xa nhất",
                         "at": datetime.now().isoformat(timespec="seconds")}
    save_ledger(led)
    if snap["complete"]:
        save_slots(snap["slots"])

    # Đọc đủ thì LẤP CHỖ TRỐNG (khung nào chưa có bài thì xếp vào, kể cả khung
    # nằm trước bài chờ xa nhất). Đọc thiếu = không biết khung nào bận → lùi về
    # nếp cũ, nối tiếp sau mốc xa nhất cho khỏi đăng chồng.
    anchor = max([t for t in (last_when, known_anchor(led)) if t], default=None)
    slots = (plan_slots(len(queue), None, busy) if snap["complete"]
             else plan_slots(len(queue), anchor))
    deadline = datetime.now() + timedelta(days=MAX_AHEAD_DAYS)
    plan, dropped = [], 0
    for item, when in zip(queue, slots):
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

    print(f"\n📅 Kế hoạch ({len(plan)} bài, khung {SLOT_HOURS[0]}h/{SLOT_HOURS[1]}h):")
    for item, when in plan:
        print(f"  bài {item['ep']} → {when:%a %d/%m %H:%M} · {item['video'].name}"
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
        print(f"⬆ Bài {item['ep']} · {ten_hienthi(item['base'])} → {when:%d/%m %H:%M} "
              f"({item['video'].stat().st_size // 1_000_000} MB)…")
        try:
            video_id = upload_scheduled(session, item, when)
        except FbError as e:
            if e.fatal:
                # Hạn mức / token hỏng: các bài sau chắc chắn hỏng y hệt → ngưng
                # hẳn, ném lên main() in thông báo chung.
                print(f"\n⛔ Bài {item['ep']} lỗi: {e}")
                raise
            # Lỗi lẻ của riêng bài này: vẫn dừng thay vì đăng tiếp — bài sau mà
            # lên trước bài lỗi thì thứ tự trên Page lộn xộn, sửa tay mệt hơn.
            print(f"\n⛔ Bài {item['ep']} lỗi: {e}\nDừng tại đây — chạy lại để xếp tiếp từ bài này.")
            break
        except Exception as e:
            print(f"\n⛔ Bài {item['ep']} lỗi: {e}\nDừng tại đây — chạy lại để xếp tiếp từ bài này.")
            break
        info = {"video_id": video_id, "scheduled": when.isoformat(timespec="seconds"),
                "uploaded_at": datetime.now().isoformat(timespec="seconds"),
                "source": "script", "base": item["base"]}
        # Ghi SỔ trước, biên nhận cạnh video sau: sổ là chỗ vòng sau tra "đăng
        # chưa", mất nó thì video này bị xếp lại lần nữa. Biên nhận ghi vào mục
        # của kênh đang chọn — không đè mục của kênh khác.
        mark_posted(led, item["ep"], info)
        kenh_hoso.ghi_bien_nhan(receipt_path(item["base"]), KENH, info)
        print(f"  ✅ đã xếp lịch (video {video_id or '?'})")
        ok += 1
    print(f"\n🏁 Xong: {ok}/{len(plan)} bài đã lên lịch.")
    return 0 if ok == len(plan) else 1


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
                  f"rồi sửa access_token trong "
                  f"{kenh_hoso.thu_muc(KENH) / 'facebook.json' if KENH else 'facebook.json của hồ sơ kênh'}.")
        else:
            # Đã bị chặn thật → khoá luôn các lần bấm sau, đúng như khi tự ngưng
            # ở 75%: gọi thêm trong lúc bị chặn chỉ kéo dài thời gian bị chặn.
            until = _cooldown_until()
            save_cooldown(until, str(e))
            print("   Đang bị Facebook chặn vì vượt hạn mức — KHÔNG thử lại ngay "
                  "(gọi thêm chỉ kéo dài thời gian bị chặn). Các lần chạy tiếp theo "
                  f"sẽ tự đứng yên tới {until:%H:%M}; tập đã xếp lịch vẫn giữ nguyên.")
        return 2


if __name__ == "__main__":
    # Chạy nhầm python ngoài venv thì tự chạy lại bằng python của dự án.
    if VENV_PY.exists() and Path(sys.executable).resolve() != VENV_PY.resolve():
        import subprocess
        raise SystemExit(subprocess.call([str(VENV_PY), *sys.argv], cwd=str(ROOT)))
    raise SystemExit(run())
