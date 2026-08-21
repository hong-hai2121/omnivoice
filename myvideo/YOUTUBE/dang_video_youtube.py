# -*- coding: utf-8 -*-
"""Thư viện đăng YouTube cho myvideo — YouTube Data API v3, KÊNH RIÊNG.

Mang lớp logic từ myvoice/YOUTUBE/dang_video_youtube.py sang (2026-08-21), bỏ
phần GUI + nghiệp vụ "tập truyện"; giữ nguyên: đăng nhập OAuth (tự refresh,
đổi kênh backup token cũ), upload resumable có thử lại kiểu Google khuyến nghị,
cache kênh/video, xếp khung giờ công chiếu 2 mốc/ngày.

⚠️ HỒ SƠ KÊNH (nhiều tài khoản): token/cache KHÔNG nằm cứng một chỗ nữa —
mỗi kênh một hồ sơ myvideo/kenh/<tên>/ (xem myvideo/kenh_hoso.py):
    token.json              ← token KHOÁ vào đúng kênh đã chọn lúc đăng nhập
    kenh_video_cache.json   ← cache kênh + video, tự sinh
    client_secret.json      ← bản CHUNG ở myvideo/kenh/ (một Google Cloud
                              project đủ cho nhiều kênh); hồ sơ đặt bản riêng
                              trong thư mục nó thì bản riêng thắng.
Bên gọi (dang_youtube.py / web) phải gọi chon_kenh(<thư mục hồ sơ>, <client
secret>) trước — chưa gọi mà đụng API là nổ ngay chứ không âm thầm đọc nhầm
kênh khác; TUYỆT ĐỐI không đọc sang thư mục của myvoice.
"""

from __future__ import annotations

import http.client
import json
import random
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# chon_kenh() trỏ ba đường dẫn này vào hồ sơ kênh đang dùng. Để None cho mọi
# lượt gọi quên chọn kênh nổ ngay (xem _da_chon).
CLIENT_SECRET_FILE = None
TOKEN_FILE = None
CACHE_FILE = None


def chon_kenh(ho_so: Path, client_secret: Path) -> None:
    """Trỏ token + cache vào hồ sơ kênh `ho_so` (myvideo/kenh/<tên>/)."""
    global CLIENT_SECRET_FILE, TOKEN_FILE, CACHE_FILE
    CLIENT_SECRET_FILE = Path(client_secret)
    TOKEN_FILE = Path(ho_so) / "token.json"
    CACHE_FILE = Path(ho_so) / "kenh_video_cache.json"


def _da_chon() -> None:
    if TOKEN_FILE is None:
        raise RuntimeError("Chưa chọn hồ sơ kênh — gọi chon_kenh(...) trước.")

# Quyền: upload video + đặt thumbnail, và ĐỌC thông tin kênh/video đã đăng.
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]

# Giới hạn của YouTube (cảnh báo sớm trước khi gọi API).
MAX_TITLE = 100
MAX_DESC = 5000
THUMB_MAX_BYTES = 2 * 1024 * 1024

# Danh mục video phổ biến (categoryId của YouTube). Nhãn hiển thị → id.
CATEGORIES = {
    "Phim & Hoạt hình (1)": "1",
    "Ô tô & Xe cộ (2)": "2",
    "Âm nhạc (10)": "10",
    "Thú cưng & Động vật (15)": "15",
    "Thể thao (17)": "17",
    "Du lịch & Sự kiện (19)": "19",
    "Trò chơi / Gaming (20)": "20",
    "Người & Blog (22)": "22",
    "Hài (23)": "23",
    "Giải trí (24)": "24",
    "Tin tức & Chính trị (25)": "25",
    "Hướng dẫn & Phong cách (26)": "26",
    "Giáo dục (27)": "27",
    "Khoa học & Công nghệ (28)": "28",
}

# 2 khung giờ công chiếu mỗi ngày (giờ máy) — đăng hàng loạt vẫn dàn đều lịch.
UPLOAD_SLOTS = ((8, 0), (18, 0))
SLOT_MIN_LEAD_MINUTES = 60


def get_credentials(log, force_new=False, interactive=True, login_timeout=None):
    """Credentials hợp lệ; tự refresh, hoặc mở trình duyệt đăng nhập khi cần.

    force_new=True: bỏ token cũ (backup lại), bắt Google hiện màn hình CHỌN
    KÊNH — token bị khoá vào đúng kênh chọn lúc đăng nhập, đổi kênh là phải
    đăng nhập lại. interactive=False: chỉ dùng token sẵn có (kể cả làm mới),
    KHÔNG mở trình duyệt — trả None nếu bắt buộc đăng nhập lại; dùng cho các
    lượt chạy nền. login_timeout=<giây>: hạn chờ bấm "Cho phép" — lượt đăng
    nhập chạy trong hàng đợi nền phải có hạn, kẻo treo giữ cổng callback mãi.
    """
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow

    _da_chon()
    if not CLIENT_SECRET_FILE.exists():
        raise FileNotFoundError(
            f"Chưa có client_secret.json cho hồ sơ kênh này.\n"
            f"Hãy đặt file vào: {CLIENT_SECRET_FILE}")

    creds = None
    if not force_new and TOKEN_FILE.exists():
        try:
            info = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
            # Token thiếu quyền nào trong SCOPES là coi như không có, buộc đăng
            # nhập lại một lần để Google cấp đủ (khỏi phải xoá tay).
            if set(SCOPES) <= set(info.get("scopes", [])):
                creds = Credentials.from_authorized_user_info(info, SCOPES)
            else:
                log("Token cũ thiếu quyền — cần đăng nhập lại một lần.", "warn")
        except Exception:
            creds = None

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        log("Token hết hạn — đang làm mới...", "info")
        try:
            creds.refresh(Request())
            TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
            return creds
        except Exception:
            log("Làm mới token thất bại, sẽ đăng nhập lại.", "warn")

    if not interactive:
        return None

    log("Mở trình duyệt để đăng nhập Google & cấp quyền — CHỌN ĐÚNG KÊNH MỚI...", "info")
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_FILE), SCOPES)
    prompt = "select_account consent" if force_new else "consent"
    creds = flow.run_local_server(port=0, prompt=prompt,
                                  timeout_seconds=login_timeout)
    if force_new and TOKEN_FILE.exists():
        # Giữ token kênh cũ (không ghi đè mất) trước khi lưu token kênh mới.
        backup = TOKEN_FILE.with_name(f"token_old_{datetime.now():%Y%m%d_%H%M%S}.json")
        try:
            TOKEN_FILE.replace(backup)
            log(f"Token kênh cũ được giữ ở: {backup.name}", "info")
        except OSError:
            pass
    TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
    log("Đăng nhập thành công, đã lưu token.", "ok")
    return creds


def _parse_yt_time(s):
    """RFC3339 UTC của YouTube ('2026-08-02T13:00:00Z') → datetime giờ máy."""
    if not s:
        return None
    s = re.sub(r"\.\d+(?=Z|[+-]\d)", "", s.strip())
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone()
    except ValueError:
        return None


def to_rfc3339(dt):
    """datetime (giờ máy) → chuỗi RFC3339 UTC mà YouTube API yêu cầu."""
    return dt.astimezone().astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.0Z")


def fetch_channel_videos(log, max_videos=50, force_new_login=False):
    """Đọc kênh đang đăng nhập + video mới nhất (kể cả video hẹn giờ) → cache.

    Trả về (chan, videos): chan = {"title", "id", "custom_url", "video_count",
    "videos_complete"}; videos mới nhất trước, publish_at là giờ HẸN (giờ máy)."""
    from googleapiclient.discovery import build

    creds = get_credentials(log, force_new=force_new_login)
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

    resp = youtube.channels().list(part="snippet,contentDetails,statistics",
                                   mine=True).execute()
    items = resp.get("items", [])
    if not items:
        raise RuntimeError("Tài khoản/kênh đang đăng nhập không có kênh YouTube nào.")
    c = items[0]
    chan = {
        "title": c["snippet"]["title"],
        "id": c["id"],
        "custom_url": c["snippet"].get("customUrl", ""),
        "video_count": int(c.get("statistics", {}).get("videoCount", 0)),
    }

    # Playlist "uploads" chứa MỌI video của kênh, mới nhất trước — video
    # private/đã hẹn giờ vẫn hiện vì đăng nhập bằng chính chủ kênh.
    uploads_id = c["contentDetails"]["relatedPlaylists"]["uploads"]
    video_ids, page_token = [], None
    while len(video_ids) < max_videos:
        pl = youtube.playlistItems().list(
            part="contentDetails", playlistId=uploads_id,
            maxResults=min(50, max_videos - len(video_ids)),
            pageToken=page_token).execute()
        video_ids += [it["contentDetails"]["videoId"] for it in pl.get("items", [])]
        page_token = pl.get("nextPageToken")
        if not page_token:
            break
    chan["videos_complete"] = not page_token

    videos = []
    for i in range(0, len(video_ids), 50):     # videos.list nhận tối đa 50 id/lần
        resp = youtube.videos().list(part="snippet,status",
                                     id=",".join(video_ids[i:i + 50])).execute()
        for v in resp.get("items", []):
            st = v.get("status", {})
            videos.append({
                "id": v["id"],
                "title": v["snippet"]["title"],
                "privacy": st.get("privacyStatus", ""),
                "publish_at": _parse_yt_time(st.get("publishAt")),
                "published_at": _parse_yt_time(v["snippet"].get("publishedAt")),
            })
    save_video_cache(chan, videos)
    return chan, videos


# ── Cache kênh/video ─────────────────────────────────────────────────────────
def _cache_read_raw():
    """Đọc cache thô (datetime còn là chuỗi ISO). Hỏng/thiếu → khung rỗng."""
    _da_chon()
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("channels"), dict):
            return data
    except Exception:
        pass
    return {"current": None, "channels": {}}


def load_video_cache():
    """Đọc cache, datetime đã parse sẵn."""
    raw = _cache_read_raw()
    for entry in raw["channels"].values():
        for v in entry.get("videos", []):
            for k in ("publish_at", "published_at"):
                s = v.get(k)
                try:
                    v[k] = datetime.fromisoformat(s) if s else None
                except (TypeError, ValueError):
                    v[k] = None
    return raw


def save_video_cache(chan, videos):
    """Lưu kết quả một lần gọi API vào cache (ghi đè phần của đúng kênh đó)."""
    raw = _cache_read_raw()
    raw["current"] = chan["id"]
    raw["channels"][chan["id"]] = {
        "channel": chan,
        "fetched_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "videos": [dict(v,
                        publish_at=v["publish_at"].isoformat() if v["publish_at"] else None,
                        published_at=v["published_at"].isoformat() if v["published_at"] else None)
                   for v in videos],
    }
    try:
        CACHE_FILE.write_text(json.dumps(raw, ensure_ascii=False, indent=1),
                              encoding="utf-8")
    except OSError:
        pass


def cache_add_uploaded(video_id, title, privacy, publish_at_rfc3339):
    """Ghi bổ sung video VỪA ĐĂNG vào đầu cache — sau khi đăng không cần gọi
    API đọc lại mà khung giờ video sau vẫn tự tránh video này."""
    raw = _cache_read_raw()
    entry = raw.get("channels", {}).get(raw.get("current"))
    if not entry:
        return
    pub = _parse_yt_time(publish_at_rfc3339)
    entry["videos"].insert(0, {
        "id": video_id,
        "title": title,
        "privacy": privacy,
        "publish_at": pub.isoformat() if pub else None,
        "published_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    })
    ch = entry.get("channel", {})
    ch["video_count"] = int(ch.get("video_count", 0)) + 1
    try:
        CACHE_FILE.write_text(json.dumps(raw, ensure_ascii=False, indent=1),
                              encoding="utf-8")
    except OSError:
        pass


def cached_scheduled_videos():
    """Video đang hẹn giờ (theo cache) của kênh hiện tại, sắp theo giờ đăng."""
    data = load_video_cache()
    entry = data["channels"].get(data.get("current"))
    if not entry:
        return []
    now = datetime.now().astimezone()
    return sorted((v for v in entry["videos"]
                   if v["privacy"] == "private" and v["publish_at"]
                   and v["publish_at"] > now),
                  key=lambda v: v["publish_at"])


def next_publish_slot(now=None, taken=None, after_last=True):
    """Khung giờ đăng TRỐNG gần nhất (datetime giờ máy).

    taken=None → lấy từ cache (gồm cả video vừa đăng trong mẻ này, vì
    upload_video ghi thẳng vào cache). after_last=True: giờ mới nằm SAU video
    hẹn muộn nhất — thứ tự lên sóng khớp thứ tự đăng, mẻ nào cũng nối đuôi."""
    now = (now or datetime.now()).astimezone()
    if taken is None:
        taken = [v["publish_at"] for v in cached_scheduled_videos()]
    times = [t.astimezone() for t in taken if t]
    used = {t.replace(second=0, microsecond=0) for t in times}
    earliest = now + timedelta(minutes=SLOT_MIN_LEAD_MINUTES)
    if after_last and times:
        earliest = max(earliest, max(times) + timedelta(minutes=1))
    day = earliest.replace(hour=0, minute=0, second=0, microsecond=0)
    for _ in range(370):        # dò tối đa ~1 năm tới
        for hh, mm in UPLOAD_SLOTS:
            slot = day.replace(hour=hh, minute=mm)
            if slot >= earliest and slot not in used:
                return slot
        day += timedelta(days=1)
    raise RuntimeError("Không tìm được khung giờ đăng trống trong 1 năm tới.")


def _http_reason(e) -> str:
    """Mã 'reason' trong body lỗi của YouTube API (rỗng nếu không đọc được)."""
    try:
        data = json.loads(e.content.decode("utf-8"))
        return data["error"]["errors"][0].get("reason", "")
    except Exception:
        return ""


def upload_video(opts, log, progress_cb):
    """Upload. `opts`: video_path, title, description, tags(list), category_id,
    privacy, publish_at(str RFC3339 | None), made_for_kids, contains_ai,
    thumbnail_path(str | None). Trả về video_id."""
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError

    creds = get_credentials(log)
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

    status = {
        "privacyStatus": opts["privacy"],
        "selfDeclaredMadeForKids": bool(opts["made_for_kids"]),
        # Khai báo "Altered content": video có nội dung AI (giọng đọc tổng hợp).
        "containsSyntheticMedia": bool(opts.get("contains_ai", True)),
    }
    # Hẹn giờ đăng: YouTube yêu cầu privacy = private và có publishAt.
    if opts.get("publish_at"):
        status["privacyStatus"] = "private"
        status["publishAt"] = opts["publish_at"]

    body = {
        "snippet": {
            "title": opts["title"],
            "description": opts["description"],
            "tags": opts["tags"],
            "categoryId": opts["category_id"],
        },
        "status": status,
    }

    media = MediaFileUpload(opts["video_path"], chunksize=4 * 1024 * 1024, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    log("Bắt đầu tải video lên YouTube...", "info")
    # Resumable: lỗi 5xx / lỗi mạng là TẠM THỜI — thử lại đúng chunk đó với chờ
    # tăng dần (cách Google khuyến nghị). Lỗi 4xx là vĩnh viễn → báo ngay.
    RETRIABLE_STATUS = {500, 502, 503, 504}
    MAX_RETRIES = 8
    retries = 0
    response = None
    while response is None:
        try:
            chunk_status, response = request.next_chunk()
        except HttpError as e:
            if e.resp.status not in RETRIABLE_STATUS:
                raise RuntimeError(f"Lỗi từ YouTube API: {e}")
            reason = f"YouTube trả mã {e.resp.status}"
        except (OSError, http.client.HTTPException) as e:
            reason = f"lỗi mạng ({e.__class__.__name__}: {e})"
        else:
            retries = 0
            if chunk_status:
                progress_cb(int(chunk_status.progress() * 100))
            continue
        retries += 1
        if retries > MAX_RETRIES:
            raise RuntimeError(f"Ngắt upload sau {MAX_RETRIES} lần thử lại — {reason}.")
        wait = min(2 ** retries, 60) + random.random()
        log(f"  {reason} — thử lại lần {retries}/{MAX_RETRIES} sau {wait:.0f}s...", "warn")
        time.sleep(wait)
    progress_cb(100)

    video_id = response["id"]
    log(f"Đăng video thành công! ID = {video_id}", "ok")
    log(f"Link: https://youtu.be/{video_id}", "ok")
    try:
        cache_add_uploaded(video_id, opts["title"], status["privacyStatus"],
                           status.get("publishAt"))
    except Exception:
        pass   # cache hỏng không được cản trở việc đăng

    # Đặt thumbnail (nếu có) — video mới tải còn "đang xử lý" nên YouTube đôi
    # khi từ chối tạm thời → thử lại có chờ tăng dần; lỗi quyền/ảnh sai là
    # vĩnh viễn → dừng sớm + nói rõ cách xử lý.
    if opts.get("thumbnail_path"):
        log("Đang đặt ảnh thumbnail...", "info")
        FATAL = {"forbidden", "thumbnailSizeTooLarge", "invalidImage",
                 "invalidImageFormat", "mediaBodyRequired"}
        delays = [0, 3, 6, 10, 15, 20]
        last_err = None
        for i, wait in enumerate(delays):
            if wait:
                time.sleep(wait)
            try:
                youtube.thumbnails().set(
                    videoId=video_id,
                    media_body=MediaFileUpload(opts["thumbnail_path"]),
                ).execute()
                log("Đã đặt thumbnail. Hoàn tất.", "ok")
                last_err = None
                break
            except HttpError as e:
                last_err = e
                reason = _http_reason(e)
                if reason in FATAL:
                    break   # thử lại cũng vô ích
                log(f"  Thumbnail chưa nhận (lần {i + 1}/{len(delays)}: "
                    f"{reason or 'video đang xử lý'}) — chờ rồi thử lại...", "warn")
        if last_err is not None:
            reason = _http_reason(last_err)
            log(f"Không đặt được thumbnail (video vẫn đã đăng): {last_err}", "warn")
            if reason == "forbidden":
                log("→ Kênh CHƯA XÁC MINH nên không đặt được thumbnail tùy chỉnh. "
                    "Xác minh tại https://www.youtube.com/verify rồi đặt tay.", "warn")
            elif reason == "thumbnailSizeTooLarge":
                log("→ Ảnh thumbnail vượt 2MB. Hãy giảm dung lượng ảnh.", "warn")
            elif reason in ("invalidImage", "invalidImageFormat"):
                log("→ Ảnh không hợp lệ (chỉ JPG/PNG/GIF/BMP).", "warn")

    return video_id
