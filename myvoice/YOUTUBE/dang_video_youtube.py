# -*- coding: utf-8 -*-
"""
Giao diện: ĐĂNG VIDEO TỰ ĐỘNG LÊN YOUTUBE (tiêu đề + mô tả + thẻ tag).

Dùng YouTube Data API v3 (OAuth). Lần đầu chạy sẽ mở trình duyệt để bạn đăng nhập
và cấp quyền; sau đó token được lưu lại (token.json) nên các lần sau không phải
đăng nhập lại.

Chạy:  python dang_video_youtube.py

────────────────────────────────────────────────────────────────────────────
CHUẨN BỊ MỘT LẦN (bắt buộc, do YouTube yêu cầu OAuth):
  1. Vào https://console.cloud.google.com/  → tạo Project.
  2. "APIs & Services" → "Library" → bật "YouTube Data API v3".
  3. "APIs & Services" → "OAuth consent screen": chọn External, điền tên app,
     thêm email của bạn vào mục "Test users".
  4. "Credentials" → "Create Credentials" → "OAuth client ID" → loại
     "Desktop app" → tải file JSON về, đổi tên thành  client_secret.json
     và đặt vào thư mục:  myvoice/YOUTUBE/client_secret.json
  (Nút "Mở thư mục cấu hình" trong app sẽ mở đúng thư mục này.)

CÀI THƯ VIỆN (nếu thiếu — app sẽ báo và cho cài tự động):
  pip install google-api-python-client google-auth-oauthlib google-auth-httplib2
────────────────────────────────────────────────────────────────────────────
"""

import sys, os

# ── Tự chuyển sang python của venv (giống các script *_gui.py khác) ──────────
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
_VENV_PYTHON = os.path.join(_REPO_ROOT, "venv", "Scripts", "python.exe")
if __name__ == "__main__" and os.path.exists(_VENV_PYTHON) and \
        os.path.normcase(os.path.abspath(sys.executable)) != \
        os.path.normcase(os.path.abspath(_VENV_PYTHON)):
    import subprocess
    subprocess.run([_VENV_PYTHON] + sys.argv)
    sys.exit()

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import json
import queue
import random
import re
import threading
import time
import traceback
import subprocess
import webbrowser
from pathlib import Path
from datetime import datetime, timedelta, timezone

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog

# ── Cấu hình thư mục ─────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent              # myvoice/YOUTUBE/
YT_DIR = BASE_DIR                                        # client_secret/token/settings nằm cùng thư mục script
YT_DIR.mkdir(exist_ok=True)
CLIENT_SECRET_FILE = YT_DIR / "client_secret.json"      # bạn tải từ Google Cloud Console
TOKEN_FILE = YT_DIR / "token.json"                      # token đăng nhập, tự sinh sau lần đầu
SETTINGS_FILE = YT_DIR / "settings.json"                # ghi nhớ lựa chọn lần trước
CACHE_FILE = YT_DIR / "kenh_video_cache.json"           # cache kênh + video (đỡ gọi API lặp lại)
KICHBAN_DIR = BASE_DIR.parent / "kịch_bản"              # nơi chứa seoYoutube.docx (kết quả SEO Gemini)
SEO_DOCX_FILE = KICHBAN_DIR / "seoYoutube.docx"         # file SEO để tách Tiêu đề/Mô tả/Thẻ tag
OUTPUT_DIR = KICHBAN_DIR / "output"                     # nơi chứa video đã dựng (output*_videodone.mp4, *_doc.mp4)

VIDEO_EXTS = [("Video", "*.mp4 *.mov *.mkv *.avi *.flv *.webm *.m4v *.wmv"),
              ("Tất cả", "*.*")]
IMAGE_EXTS = [("Ảnh", "*.jpg *.jpeg *.png"), ("Tất cả", "*.*")]

# Quyền: upload video + đặt thumbnail, và ĐỌC thông tin kênh/video đã đăng.
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]

# Giới hạn của YouTube (để cảnh báo sớm trước khi gọi API).
MAX_TITLE = 100        # ký tự
MAX_DESC = 5000        # ký tự
MAX_TAGS_TOTAL = 500   # tổng ký tự thẻ tag, ĐẾM KIỂU YOUTUBE (tag có dấu cách +2 — khớp cap_tags)

# Giới hạn thumbnail của YouTube (kiểm tra ngay ở GUI, khỏi đợi API báo lỗi).
THUMB_MAX_BYTES = 2 * 1024 * 1024       # tối đa 2MB
THUMB_MIN_WIDTH = 640                   # chiều rộng tối thiểu
THUMB_REC_W, THUMB_REC_H = 1280, 720    # độ phân giải khuyến nghị
THUMB_FORMATS = {"JPEG", "PNG", "GIF", "BMP"}   # định dạng YouTube chấp nhận

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
DEFAULT_CATEGORY = "Người & Blog (22)"

PRIVACY = {
    "Riêng tư (private)": "private",
    "Không công khai / ai có link (unlisted)": "unlisted",
    "Công khai (public)": "public",
}
DEFAULT_PRIVACY = "Không công khai / ai có link (unlisted)"

# ── Bảng màu giao diện (nền xám nhạt hiện đại, accent đỏ YouTube) ─────────────
UI = dict(
    bg="#f4f6fb",          # nền trang
    surface="#ffffff",     # nền thẻ/khối
    border="#e2e6ef",
    field="#ffffff",
    fg="#1f2440", muted="#6b7280",
    accent="#ff2433", accent_dk="#d61f2b",     # đỏ YouTube — nút ĐĂNG + tiến trình
    seo="#5b5ce2", seo_dk="#4849c7",           # tím indigo — nút SEO + Thumbnail
    soft="#eaedf4", soft_dk="#dde1ea",         # nút phụ
    hover="#eef1f6",
    header="#26244f", header_sub="#c9c9ef",    # thanh tiêu đề trên cùng
    log_bg="#fbfbfc", log_info="#475063", log_warn="#b07400", log_err="#d62828",
    log_ok="#1d8a4e",
)


# ───────────────────────────────────────────────────────────────────────────
# Phần backend: xác thực + upload (tách khỏi GUI để dễ đọc)
# ───────────────────────────────────────────────────────────────────────────
def _check_deps():
    """Trả về None nếu đủ thư viện, ngược lại trả về thông báo lỗi."""
    try:
        import google_auth_oauthlib.flow      # noqa: F401
        import googleapiclient.discovery       # noqa: F401
        import googleapiclient.http            # noqa: F401
        import google.auth.transport.requests  # noqa: F401
        return None
    except ImportError as e:
        return str(e)


def install_deps(log):
    """Cài các thư viện Google API vào venv hiện tại."""
    pkgs = ["google-api-python-client", "google-auth-oauthlib", "google-auth-httplib2"]
    log(f"Đang cài: {' '.join(pkgs)} ...", "info")
    proc = subprocess.run([sys.executable, "-m", "pip", "install", *pkgs],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.stdout:
        log(proc.stdout.strip(), "info")
    if proc.returncode != 0:
        log(proc.stderr.strip(), "err")
        raise RuntimeError("Cài thư viện thất bại.")
    log("Đã cài xong thư viện Google API.", "ok")


def get_credentials(log, force_new=False, interactive=True, login_timeout=None):
    """Lấy credentials hợp lệ; tự refresh hoặc mở trình duyệt đăng nhập khi cần.

    force_new=True: bỏ qua token đã lưu, mở trình duyệt với màn hình CHỌN TÀI
    KHOẢN/KÊNH của Google — dùng cho nút "Đổi kênh". Lưu ý: 1 Gmail có thể có
    nhiều kênh, nhưng token bị KHOÁ vào đúng kênh đã chọn lúc đăng nhập; muốn
    thao tác kênh khác thì phải đăng nhập lại và chọn kênh đó.

    interactive=False: CHỈ dùng token sẵn có (kể cả làm mới), KHÔNG mở trình duyệt —
    trả về None nếu bắt buộc phải đăng nhập lại. Dùng để KIỂM TRA trước khi chạy mẻ
    dài: bật trình duyệt đòi đăng nhập giữa chừng là treo cả mẻ chạy qua đêm.

    login_timeout=<giây>: chờ tối đa bấy nhiêu giây cho lần bấm "Cho phép" trong
    trình duyệt rồi ném WSGITimeoutError. None (mặc định, bản GUI dùng) = chờ mãi:
    ngồi ngay đó thì cứ để người dùng thong thả. Bản web đặt hạn giờ vì lần đăng
    nhập chạy trong luồng nền — bỏ dở giữa chừng mà không có hạn thì luồng đó treo
    luôn, giữ mãi cổng nghe callback và chặn lần bấm nút sau.
    """
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not CLIENT_SECRET_FILE.exists():
        raise FileNotFoundError(
            "Chưa có client_secret.json.\n\n"
            f"Hãy đặt file vào:\n{CLIENT_SECRET_FILE}\n\n"
            "Xem hướng dẫn lấy file ở đầu script (hoặc nút 'Hướng dẫn lấy quyền')."
        )

    creds = None
    if not force_new and TOKEN_FILE.exists():
        try:
            info = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
            # Token đời cũ chỉ có quyền upload → không đọc được kênh/video.
            # Thiếu quyền nào trong SCOPES là coi như không có token, buộc
            # đăng nhập lại một lần để Google cấp đủ quyền (khỏi phải xóa tay).
            if set(SCOPES) <= set(info.get("scopes", [])):
                creds = Credentials.from_authorized_user_info(info, SCOPES)
            else:
                log("Token cũ thiếu quyền đọc kênh — cần đăng nhập lại một lần.", "warn")
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

    log("Mở trình duyệt để đăng nhập Google & cấp quyền...", "info")
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_FILE), SCOPES)
    # "Đổi kênh": select_account bắt Google hiện lại màn hình chọn tài khoản,
    # nơi mỗi kênh của cùng một Gmail hiện thành một dòng riêng để chọn.
    prompt = "select_account consent" if force_new else "consent"
    creds = flow.run_local_server(port=0, prompt=prompt,
                                  timeout_seconds=login_timeout)
    if force_new and TOKEN_FILE.exists():
        # Giữ lại token kênh cũ (không ghi đè mất) trước khi lưu token kênh mới.
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
    s = re.sub(r"\.\d+(?=Z|[+-]\d)", "", s.strip())   # bỏ phần lẻ giây nếu có
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone()
    except ValueError:
        return None


def fetch_channel_videos(log, max_videos=50, force_new_login=False):
    """Đọc kênh đang đăng nhập + danh sách video (kể cả video đã hẹn giờ).

    Trả về (chan, videos):
      chan   = {"title", "id", "custom_url", "video_count"}
      videos = [{"id", "title", "privacy", "publish_at", "published_at"}, ...]
               mới nhất trước; publish_at là giờ HẸN ĐĂNG (giờ máy) nếu có.
    """
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
    # private/đã hẹn giờ vẫn hiện vì mình đăng nhập bằng chính chủ kênh.
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

    videos = []
    for i in range(0, len(video_ids), 50):   # videos.list nhận tối đa 50 id/lần
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
# Mỗi lần gọi API xong, kết quả được lưu vào kenh_video_cache.json (riêng theo
# từng channel id — đổi kênh không mất dữ liệu kênh kia). Nhờ vậy mỗi phiên chạy
# app chỉ cần gọi API 1 lần; video vừa đăng được ghi bổ sung thẳng vào cache.
# Đây cũng là nguồn dữ liệu cho tính năng LÊN LỊCH sau này (biết các giờ đã hẹn).
def _cache_read_raw():
    """Đọc cache thô (datetime còn là chuỗi ISO). Hỏng/thiếu → khung rỗng."""
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("channels"), dict):
            return data
    except Exception:
        pass
    return {"current": None, "channels": {}}


def load_video_cache():
    """Đọc cache, datetime đã parse sẵn.

    Trả về {"current": channel_id|None, "channels": {id: {
        "channel": {...}, "fetched_at": iso str, "videos": [{...}, ...]}}}
    """
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
    """Ghi bổ sung video VỪA ĐĂNG vào đầu cache của kênh hiện tại.

    Nhờ vậy sau khi đăng không cần gọi API đọc lại mà danh sách vẫn đúng."""
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
    """Các video đang hẹn giờ (theo cache) của kênh hiện tại, sắp theo giờ đăng.

    Dành cho tính năng lên lịch: biết các khung giờ đã chiếm để gợi ý giờ mới."""
    data = load_video_cache()
    entry = data["channels"].get(data.get("current"))
    if not entry:
        return []
    now = datetime.now().astimezone()
    return sorted((v for v in entry["videos"]
                   if v["privacy"] == "private" and v["publish_at"]
                   and v["publish_at"] > now),
                  key=lambda v: v["publish_at"])


# ── LÊN LỊCH ĐĂNG: 2 khung giờ mỗi ngày ──────────────────────────────────────
# Đăng hàng loạt mà tập nào cũng hẹn "ngày mai" thì cả mẻ lên sóng cùng một lúc.
# Mỗi tập được xếp vào MỘT khung giờ trống kế tiếp, dò theo lịch đã hẹn thật của
# kênh (cache) — nên chạy nhiều mẻ khác ngày vẫn nối đuôi nhau, không đè lên nhau
# và cũng không đè lên video bạn đã tự hẹn giờ trong YouTube Studio.
UPLOAD_SLOTS = ((8, 0), (18, 0))    # 08:00 sáng và 18:00 tối (giờ máy)
SLOT_MIN_LEAD_MINUTES = 60          # giờ hẹn phải cách hiện tại ít nhất bấy nhiêu


def to_rfc3339(dt):
    """datetime (giờ máy) → chuỗi RFC3339 UTC mà YouTube API yêu cầu."""
    return dt.astimezone().astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.0Z")


def next_publish_slot(now=None, taken=None, after_last=True):
    """Khung giờ đăng TRỐNG gần nhất (datetime giờ máy).

    taken: danh sách giờ đã chiếm; None → lấy từ cache (các video đang hẹn giờ của
    kênh, gồm cả video vừa đăng trong mẻ này vì upload_video ghi thẳng vào cache).

    after_last=True: giờ mới phải nằm SAU video hẹn giờ muộn nhất. Kênh truyện đánh
    số tập nên tập mới BẮT BUỘC lên sau tập cũ — chỉ tìm "khung trống gần nhất" là
    chưa đủ: tập 47 đang hẹn 20:00 hôm nay thì khung 18:00 hôm nay tuy còn trống
    nhưng dùng nó sẽ cho tập 48 công khai TRƯỚC tập 47.
    """
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


_EP_RE = re.compile(r"số\s*(\d+)", re.IGNORECASE)   # 'Số 45' trong tiêu đề video


def episode_numbers(videos):
    """Tách mọi 'Số N' xuất hiện trong tiêu đề các video. Trả về set số nguyên."""
    nums = set()
    for v in videos:
        for m in _EP_RE.finditer(v.get("title") or ""):
            nums.add(int(m.group(1)))
    return nums


def find_missing_episodes(videos):
    """Các SỐ TẬP CÒN SÓT trong dải tập của danh sách video (tính cả video hẹn giờ).

    Trả về (missing, lo, hi): số thiếu trong khoảng [lo..hi] (lo/hi = tập nhỏ
    nhất/lớn nhất đã có); ([], None, None) nếu không tách được số tập nào."""
    nums = episode_numbers(videos)
    if not nums:
        return [], None, None
    lo, hi = min(nums), max(nums)
    return sorted(set(range(lo, hi + 1)) - nums), lo, hi


def cached_missing_episodes():
    """find_missing_episodes trên cache của kênh hiện tại — nguồn cho việc LÀM BÙ tập."""
    data = load_video_cache()
    entry = data["channels"].get(data.get("current"))
    if not entry:
        return [], None, None
    return find_missing_episodes(entry["videos"])


def _http_reason(err):
    """Lấy 'reason' từ HttpError của Google API (vd 'forbidden', 'thumbnailSizeTooLarge')."""
    try:
        data = json.loads(err.content.decode("utf-8"))
        errs = data.get("error", {}).get("errors", [])
        return errs[0].get("reason", "") if errs else ""
    except Exception:
        return ""


def upload_video(opts, log, progress_cb):
    """
    Thực hiện upload. `opts` là dict gồm:
      video_path, title, description, tags(list), category_id,
      privacy, publish_at(str RFC3339 hoặc None), made_for_kids(bool),
      contains_ai(bool), thumbnail_path(str hoặc None)
    Trả về video_id.
    """
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError

    creds = get_credentials(log)
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

    status = {
        "privacyStatus": opts["privacy"],
        "selfDeclaredMadeForKids": bool(opts["made_for_kids"]),
        # Ô "Altered content" của YouTube Studio, bản API: khai báo video có nội
        # dung do AI tạo/biến đổi (giọng đọc tổng hợp...). YouTube chỉ gắn nhãn
        # nhỏ trong mô tả mở rộng, không ảnh hưởng đề xuất hay kiếm tiền.
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
    # Upload resumable: lỗi 5xx / lỗi mạng chỉ là TẠM THỜI — thử lại đúng chunk đó
    # với thời gian chờ tăng dần (cách Google khuyến nghị), khỏi mất cả phiên tải
    # vì một cú chập mạng ở phút chót. Lỗi 4xx (sai quyền, video quá dài...) là
    # vĩnh viễn → báo ngay. Cứ tải được một chunk là đếm lại từ đầu.
    import http.client
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

    # Đặt thumbnail (nếu có) — KHÔNG đợi YouTube xử lý xong video.
    # Ngay sau khi tải lên, video còn "đang xử lý" nên YouTube đôi khi từ chối
    # thumbnail tạm thời → thử lại vài lần có chờ tăng dần. Lỗi quyền/ảnh sai
    # (chưa xác minh kênh, ảnh > 2MB...) là vĩnh viễn → dừng sớm + báo rõ.
    if opts.get("thumbnail_path"):
        log("Đang đặt ảnh thumbnail...", "info")
        FATAL = {"forbidden", "thumbnailSizeTooLarge", "invalidImage",
                 "invalidImageFormat", "mediaBodyRequired"}
        delays = [0, 3, 6, 10, 15, 20]   # thử ngay, rồi chờ dần (tổng ~54s nếu cứ lỗi)
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
                log("→ Kênh CHƯA XÁC MINH nên YouTube không cho đặt thumbnail tùy chỉnh. "
                    "Hãy xác minh tại https://www.youtube.com/verify rồi đặt thumbnail thủ công.", "warn")
            elif reason == "thumbnailSizeTooLarge":
                log("→ Ảnh thumbnail vượt 2MB. Hãy giảm dung lượng ảnh.", "warn")
            elif reason in ("invalidImage", "invalidImageFormat"):
                log("→ Ảnh không hợp lệ (chỉ JPG/PNG/GIF/BMP).", "warn")

    return video_id


# ───────────────────────────────────────────────────────────────────────────
# GUI
# ───────────────────────────────────────────────────────────────────────────
class App:
    def __init__(self, root):
        self.root = root
        self.q = queue.Queue()           # hàng đợi log/progress từ thread worker
        self.worker = None
        self.thumb_ok = True             # thumbnail có hợp lệ không (cập nhật bởi _check_thumb)
        self.chan_win = None             # cửa sổ "Kênh & video" (Toplevel)
        self.chan_worker = None          # thread đang đọc kênh/video (nếu có)
        self.chan_fetched = False        # phiên này đã gọi API đọc kênh chưa (chỉ gọi 1 lần)
        root.title("Đăng video tự động lên YouTube")
        root.configure(bg=UI["bg"])
        self._center(root, 1320, 720)
        root.minsize(1080, 560)

        self._build_styles()
        self._build_header()
        self._build_form()
        self._load_settings()
        self._set_default_video()   # điền sẵn video mới nhất trong kịch_bản/output
        self._poll_queue()
        root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _center(self, root, w, h):
        """Mở cửa sổ ở giữa màn hình (ngang giữa, 1/3 từ trên xuống)."""
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        x, y = (sw - w) // 2, (sh - h) // 3
        root.geometry(f"{w}x{h}+{max(x, 0)}+{max(y, 0)}")

    # ---- style ----
    def _build_styles(self):
        st = ttk.Style()
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        C = UI
        base = ("Segoe UI", 10)
        st.configure(".", font=base, background=C["bg"], foreground=C["fg"])
        st.configure("TFrame", background=C["bg"])
        st.configure("TLabel", background=C["bg"], foreground=C["fg"], font=base)
        st.configure("Muted.TLabel", background=C["bg"], foreground=C["muted"],
                     font=("Segoe UI", 9))
        st.configure("Field.TLabel", background=C["bg"], foreground=C["fg"],
                     font=("Segoe UI", 10, "bold"))

        # Trường nhập + spinbox
        for w in ("TEntry", "TSpinbox"):
            st.configure(w, fieldbackground=C["field"], background=C["field"],
                         bordercolor=C["border"], lightcolor=C["border"],
                         darkcolor=C["border"], foreground=C["fg"],
                         insertcolor=C["fg"], padding=6)
            st.map(w, bordercolor=[("focus", C["accent"])],
                   lightcolor=[("focus", C["accent"])])
        st.configure("TSpinbox", arrowcolor=C["muted"])

        # Combobox
        st.configure("TCombobox", fieldbackground=C["field"], background=C["field"],
                     bordercolor=C["border"], lightcolor=C["border"],
                     darkcolor=C["border"], arrowcolor=C["muted"], padding=5)
        st.map("TCombobox",
               fieldbackground=[("readonly", C["field"])],
               foreground=[("readonly", C["fg"])],
               selectbackground=[("readonly", C["field"])],
               selectforeground=[("readonly", C["fg"])],
               bordercolor=[("focus", C["accent"])],
               lightcolor=[("focus", C["accent"])])
        self.root.option_add("*TCombobox*Listbox.background", C["field"])
        self.root.option_add("*TCombobox*Listbox.foreground", C["fg"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", C["seo"])
        self.root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")

        # Checkbutton
        st.configure("TCheckbutton", background=C["bg"], foreground=C["fg"])
        st.map("TCheckbutton",
               background=[("active", C["bg"])],
               foreground=[("active", C["seo"]), ("selected", C["seo"])],
               indicatorcolor=[("selected", C["seo"]), ("!selected", "#cfd3da")])

        # Nút mặc định = nút phụ (soft)
        st.configure("TButton", background=C["soft"], foreground=C["fg"],
                     bordercolor=C["border"], relief="flat", focusthickness=0,
                     padding=(12, 7), font=base)
        st.map("TButton",
               background=[("active", C["hover"]), ("pressed", C["soft_dk"]),
                           ("disabled", "#f1f2f5")],
               foreground=[("disabled", "#b3b8c2")])
        st.configure("Soft.TButton", background=C["soft"], foreground=C["fg"],
                     padding=(12, 7))
        st.map("Soft.TButton",
               background=[("active", C["hover"]), ("pressed", C["soft_dk"])])

        # Nút chính ĐĂNG (đỏ YouTube)
        st.configure("Accent.TButton", background=C["accent"], foreground="#ffffff",
                     padding=(22, 10), font=("Segoe UI", 10, "bold"))
        st.map("Accent.TButton",
               background=[("active", C["accent_dk"]), ("pressed", C["accent_dk"]),
                           ("disabled", "#f3a6ad")],
               foreground=[("disabled", "#ffffff")])

        # Nút quy trình SEO + Thumbnail (tím indigo)
        st.configure("Seo.TButton", background=C["seo"], foreground="#ffffff",
                     padding=(16, 9), font=("Segoe UI", 10, "bold"))
        st.map("Seo.TButton",
               background=[("active", C["seo_dk"]), ("pressed", C["seo_dk"]),
                           ("disabled", "#c7c8f0")],
               foreground=[("disabled", "#ffffff")])

        # Nút chip nhỏ (đặt nhanh giờ)
        st.configure("Chip.TButton", background=C["soft"], foreground=C["seo"],
                     padding=(9, 4), font=("Segoe UI", 9, "bold"))
        st.map("Chip.TButton", background=[("active", C["hover"])])

        # Nút stepper số tập (−/+)
        st.configure("Stepper.TButton", background=C["soft"], foreground=C["fg"],
                     padding=(2, 1), font=("Segoe UI", 13, "bold"))
        st.map("Stepper.TButton", background=[("active", C["hover"])])

        # Thanh tiến trình (đỏ)
        st.configure("TProgressbar", background=C["accent"], troughcolor=C["soft"],
                     bordercolor=C["soft"], lightcolor=C["accent"],
                     darkcolor=C["accent"], thickness=12)

        # Thẻ nhóm (LabelFrame có viền + tiêu đề)
        st.configure("Card.TLabelframe", background=C["bg"], bordercolor=C["border"],
                     relief="solid", borderwidth=1)
        st.configure("Card.TLabelframe.Label", background=C["bg"], foreground=C["seo"],
                     font=("Segoe UI", 11, "bold"))

    # ---- header ----
    def _build_header(self):
        """Thanh tiêu đề màu trên cùng — nâng cảm giác hiện đại, không đổi bố cục form."""
        C = UI
        bar = tk.Frame(self.root, bg=C["header"], height=88)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        inner = tk.Frame(bar, bg=C["header"])
        inner.pack(anchor="w", padx=24, pady=15)
        row = tk.Frame(inner, bg=C["header"])
        row.pack(anchor="w")
        tk.Label(row, text=" ▶ ", bg=C["accent"], fg="#ffffff",
                 font=("Segoe UI", 12, "bold")).pack(side="left")
        tk.Label(row, text="  ĐĂNG VIDEO YOUTUBE", bg=C["header"], fg="#ffffff",
                 font=("Segoe UI", 17, "bold")).pack(side="left")
        tk.Label(inner,
                 text="Lấy SEO Gemini · tạo thumbnail · hẹn giờ đăng — tất cả trong một cửa sổ",
                 bg=C["header"], fg=C["header_sub"],
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(5, 0))

    # ---- form ----
    def _build_form(self):
        outer = ttk.Frame(self.root)
        outer.pack(fill="both", expand=True, padx=14, pady=12)
        outer.columnconfigure(0, weight=5, uniform="col")
        outer.columnconfigure(1, weight=4, uniform="col")
        outer.columnconfigure(2, weight=5, uniform="col")
        outer.rowconfigure(0, weight=1)

        # ════════════ CỘT 1 — NỘI DUNG VIDEO ════════════
        c1 = ttk.LabelFrame(outer, text="  Nội dung video  ",
                            style="Card.TLabelframe", padding=12)
        c1.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        c1.columnconfigure(0, weight=1)

        ttk.Label(c1, text="File video *", style="Field.TLabel").grid(
            row=0, column=0, sticky="w")
        fv = ttk.Frame(c1)
        fv.grid(row=1, column=0, sticky="ew", pady=(2, 10))
        fv.columnconfigure(0, weight=1)
        self.var_video = tk.StringVar()
        ttk.Entry(fv, textvariable=self.var_video).grid(row=0, column=0, sticky="ew")
        ttk.Button(fv, text="Chọn...", style="Soft.TButton",
                   command=self._pick_video).grid(row=0, column=1, padx=(6, 0))

        th = ttk.Frame(c1)
        th.grid(row=2, column=0, sticky="ew")
        th.columnconfigure(0, weight=1)
        ttk.Label(th, text="Tiêu đề *", style="Field.TLabel").grid(row=0, column=0, sticky="w")
        self.lbl_title_cnt = ttk.Label(th, text="0/100", style="Muted.TLabel")
        self.lbl_title_cnt.grid(row=0, column=1, sticky="e")
        self.var_title = tk.StringVar()
        self.var_title.trace_add("write", lambda *_: self._update_counters())
        ttk.Entry(c1, textvariable=self.var_title).grid(
            row=3, column=0, sticky="ew", pady=(2, 10))

        dh = ttk.Frame(c1)
        dh.grid(row=4, column=0, sticky="ew")
        dh.columnconfigure(0, weight=1)
        ttk.Label(dh, text="Mô tả", style="Field.TLabel").grid(row=0, column=0, sticky="w")
        self.lbl_desc_cnt = ttk.Label(dh, text="0/5000", style="Muted.TLabel")
        self.lbl_desc_cnt.grid(row=0, column=1, sticky="e")
        self.txt_desc = tk.Text(c1, height=8, wrap="word",
                                bg=UI["field"], fg=UI["fg"], relief="flat", borderwidth=0,
                                highlightthickness=1, highlightbackground=UI["border"],
                                highlightcolor=UI["accent"], padx=8, pady=6,
                                font=("Segoe UI", 10))
        self.txt_desc.grid(row=5, column=0, sticky="nsew", pady=(2, 10))
        self.txt_desc.bind("<KeyRelease>", lambda _e: self._update_counters())
        c1.rowconfigure(5, weight=1)

        th2 = ttk.Frame(c1)
        th2.grid(row=6, column=0, sticky="ew")
        th2.columnconfigure(0, weight=1)
        ttk.Label(th2, text="Thẻ tag", style="Field.TLabel").grid(row=0, column=0, sticky="w")
        self.lbl_tags_cnt = ttk.Label(th2, text="0/480", style="Muted.TLabel")
        self.lbl_tags_cnt.grid(row=0, column=1, sticky="e")
        self.var_tags = tk.StringVar()
        self.var_tags.trace_add("write", lambda *_: self._update_counters())
        ttk.Entry(c1, textvariable=self.var_tags).grid(
            row=7, column=0, sticky="ew", pady=(2, 0))
        ttk.Label(c1, text="(các tag cách nhau bằng dấu phẩy)",
                  style="Muted.TLabel").grid(row=8, column=0, sticky="w")

        # ════════════ CỘT 2 — TUỲ CHỌN ĐĂNG ════════════
        c2 = ttk.LabelFrame(outer, text="  Tuỳ chọn đăng  ",
                            style="Card.TLabelframe", padding=12)
        c2.grid(row=0, column=1, sticky="nsew", padx=8)
        c2.columnconfigure(0, weight=1)

        ep = ttk.Frame(c2)
        ep.grid(row=0, column=0, sticky="w", pady=(0, 10))
        ttk.Label(ep, text="Số tập (thumbnail)", style="Field.TLabel").pack(side="left")
        self.var_episode = tk.StringVar(value="01")
        ttk.Entry(ep, textvariable=self.var_episode, width=6,
                  justify="center").pack(side="left", padx=6)
        ttk.Button(ep, text="−", width=3, style="Stepper.TButton",
                   command=lambda: self._change_episode(-1)).pack(side="left")
        ttk.Button(ep, text="+", width=3, style="Stepper.TButton",
                   command=lambda: self._change_episode(1)).pack(side="left", padx=(4, 0))

        ttk.Label(c2, text="Danh mục", style="Field.TLabel").grid(row=1, column=0, sticky="w")
        self.var_cat = tk.StringVar(value=DEFAULT_CATEGORY)
        ttk.Combobox(c2, textvariable=self.var_cat, values=list(CATEGORIES),
                     state="readonly").grid(row=2, column=0, sticky="ew", pady=(2, 10))

        ttk.Label(c2, text="Chế độ (quyền riêng tư)", style="Field.TLabel").grid(
            row=3, column=0, sticky="w")
        self.var_priv = tk.StringVar(value=DEFAULT_PRIVACY)
        ttk.Combobox(c2, textvariable=self.var_priv, values=list(PRIVACY),
                     state="readonly").grid(row=4, column=0, sticky="ew", pady=(2, 8))

        chk = ttk.Frame(c2)
        chk.grid(row=5, column=0, sticky="w", pady=(0, 10))
        self.var_kids = tk.BooleanVar(value=False)
        ttk.Checkbutton(chk, text="Nội dung cho trẻ em",
                        variable=self.var_kids).pack(anchor="w")
        # Khai báo "Altered content" (status.containsSyntheticMedia). Kênh dùng giọng
        # TTS nên mặc định BẬT; chỉ tắt khi đăng video không có nội dung AI.
        self.var_ai = tk.BooleanVar(value=True)
        ttk.Checkbutton(chk, text="Nội dung có sử dụng AI (khai báo với YouTube)",
                        variable=self.var_ai).pack(anchor="w", pady=(4, 0))

        ttk.Label(c2, text="Thumbnail", style="Field.TLabel").grid(row=6, column=0, sticky="w")
        tf = ttk.Frame(c2)
        tf.grid(row=7, column=0, sticky="ew", pady=(2, 0))
        tf.columnconfigure(0, weight=1)
        self.var_thumb = tk.StringVar()
        self.var_thumb.trace_add("write", self._check_thumb)
        ttk.Entry(tf, textvariable=self.var_thumb).grid(row=0, column=0, sticky="ew")
        ttk.Button(tf, text="Chọn...", style="Soft.TButton",
                   command=self._pick_thumb).grid(row=0, column=1, padx=(6, 0))
        self.lbl_thumb = ttk.Label(c2, text="", style="Muted.TLabel")
        self.lbl_thumb.grid(row=8, column=0, sticky="w", pady=(2, 8))

        ttk.Separator(c2, orient="horizontal").grid(row=9, column=0, sticky="ew", pady=(2, 8))

        sc = ttk.Frame(c2)
        sc.grid(row=10, column=0, sticky="w")
        self.var_sched_on = tk.BooleanVar(value=False)
        ttk.Checkbutton(sc, text="Hẹn giờ đăng (giờ máy)", variable=self.var_sched_on,
                        command=self._toggle_sched).pack(side="left")
        ttk.Label(c2, text="Video để 'riêng tư' tới giờ rồi tự công khai",
                  style="Muted.TLabel").grid(row=11, column=0, sticky="w")

        d0 = (datetime.now() + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        self.var_s_day = tk.StringVar(value=f"{d0.day:02d}")
        self.var_s_month = tk.StringVar(value=f"{d0.month:02d}")
        self.var_s_year = tk.StringVar(value=str(d0.year))
        self.var_s_hour = tk.StringVar(value=f"{d0.hour:02d}")
        self.var_s_minute = tk.StringVar(value=f"{d0.minute:02d}")
        self._sched_widgets = []

        def _mk_spin(parent, lo, hi, var, width, fmt="%02.0f", inc=1):
            sp = ttk.Spinbox(parent, from_=lo, to=hi, textvariable=var, width=width,
                             wrap=True, format=fmt, increment=inc, state="disabled",
                             command=self._update_sched_preview)
            sp.bind("<KeyRelease>", lambda _e: self._update_sched_preview())
            self._sched_widgets.append(sp)
            return sp

        pd = ttk.Frame(c2)
        pd.grid(row=12, column=0, sticky="w", pady=(6, 0))
        ttk.Label(pd, text="Ngày").pack(side="left")
        _mk_spin(pd, 1, 31, self.var_s_day, 4).pack(side="left", padx=(4, 10))
        ttk.Label(pd, text="Tháng").pack(side="left")
        _mk_spin(pd, 1, 12, self.var_s_month, 4).pack(side="left", padx=(4, 10))
        ttk.Label(pd, text="Năm").pack(side="left")
        _mk_spin(pd, d0.year, d0.year + 3, self.var_s_year, 6, fmt="%.0f").pack(side="left", padx=(4, 0))

        pt = ttk.Frame(c2)
        pt.grid(row=13, column=0, sticky="w", pady=(6, 0))
        ttk.Label(pt, text="Giờ").pack(side="left")
        _mk_spin(pt, 0, 23, self.var_s_hour, 4).pack(side="left", padx=(4, 2))
        ttk.Label(pt, text=":").pack(side="left")
        _mk_spin(pt, 0, 59, self.var_s_minute, 4, inc=5).pack(side="left", padx=(2, 0))

        qk = ttk.Frame(c2)
        qk.grid(row=14, column=0, sticky="w", pady=(8, 0))
        for _label, _kw in [("+1 giờ", dict(hours=1)),
                            ("Tối nay 20:00", dict(at=(20, 0))),
                            ("Sáng mai 08:00", dict(at=(8, 0), tomorrow=True))]:
            ttk.Button(qk, text=_label, style="Chip.TButton",
                       command=lambda k=_kw: self._sched_quick(**k)).pack(side="left", padx=(0, 6))

        self.lbl_sched = ttk.Label(c2, text="", style="Muted.TLabel")
        self.lbl_sched.grid(row=15, column=0, sticky="w", pady=(6, 0))

        # ════════════ CỘT 3 — THAO TÁC & NHẬT KÝ ════════════
        c3 = ttk.LabelFrame(outer, text="  Thao tác & Nhật ký  ",
                            style="Card.TLabelframe", padding=12)
        c3.grid(row=0, column=2, sticky="nsew", padx=(8, 0))
        c3.columnconfigure(0, weight=1)
        c3.rowconfigure(5, weight=1)   # ô nhật ký giãn ra

        self.btn_upload = ttk.Button(c3, text="⬆  ĐĂNG VIDEO", style="Accent.TButton",
                                     command=self._on_upload)
        self.btn_upload.grid(row=0, column=0, sticky="ew")
        self.btn_seo = ttk.Button(c3, text="🤖 Lấy SEO + Thumbnail", style="Seo.TButton",
                                  command=self._on_seo_pipeline)
        self.btn_seo.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(c3, text="📄 Đọc SEO sẵn", style="Soft.TButton",
                   command=self._load_seo_from_docx).grid(row=2, column=0, sticky="ew", pady=(8, 0))

        self.pb = ttk.Progressbar(c3, mode="determinate", maximum=100)
        self.pb.grid(row=3, column=0, sticky="ew", pady=(12, 2))

        ttk.Label(c3, text="NHẬT KÝ", style="Muted.TLabel").grid(
            row=4, column=0, sticky="w", pady=(8, 4))
        logwrap = ttk.Frame(c3)
        logwrap.grid(row=5, column=0, sticky="nsew")
        logwrap.columnconfigure(0, weight=1)
        logwrap.rowconfigure(0, weight=1)
        self.log_widget = scrolledtext.ScrolledText(
            logwrap, height=8, wrap="word", state="disabled",
            bg=UI["log_bg"], fg=UI["log_info"], relief="flat", borderwidth=0,
            highlightthickness=1, highlightbackground=UI["border"],
            highlightcolor=UI["border"], padx=10, pady=8, font=("Consolas", 9))
        self.log_widget.grid(row=0, column=0, sticky="nsew")
        for tag, color in [("info", UI["log_info"]), ("warn", UI["log_warn"]),
                           ("err", UI["log_err"]), ("ok", UI["log_ok"])]:
            self.log_widget.tag_config(tag, foreground=color)

        util = ttk.Frame(c3)
        util.grid(row=6, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(util, text="📋 Kênh & video", style="Soft.TButton",
                   command=self._open_channel_win).pack(side="left")
        ttk.Button(util, text="Mở thư mục cấu hình", style="Soft.TButton",
                   command=self._open_cfg_dir).pack(side="left", padx=6)
        ttk.Button(util, text="Hướng dẫn", style="Soft.TButton",
                   command=self._open_help).pack(side="left")

    # ---- helpers GUI ----
    def _find_latest_video(self):
        """Video mới nhất (theo thời gian sửa): quét kịch_bản/output và các THƯ MỤC TẬP
        kịch_bản/NN - .../ (trong thư mục tập chỉ lấy YOUTUBE.* — bỏ tiktok/facebook)."""
        exts = {".mp4", ".mov", ".mkv", ".avi", ".flv", ".webm", ".m4v", ".wmv"}
        vids = []
        if OUTPUT_DIR.is_dir():
            vids += [p for p in OUTPUT_DIR.iterdir()
                     if p.is_file() and p.suffix.lower() in exts]
        if KICHBAN_DIR.is_dir():
            for d in KICHBAN_DIR.iterdir():
                if d.is_dir() and d != OUTPUT_DIR:
                    vids += [p for p in d.iterdir()
                             if p.is_file() and p.suffix.lower() in exts
                             and p.stem.upper() == "YOUTUBE"]
        if not vids:
            return ""
        return str(max(vids, key=lambda p: p.stat().st_mtime))

    def _set_default_video(self):
        """Khi mở app: điền sẵn video mới nhất (nếu ô đang trống) + tự điền SEO
        nếu video nằm trong thư mục tập có seoYoutube.docx."""
        if self.var_video.get().strip():
            return
        latest = self._find_latest_video()
        if latest:
            self.var_video.set(latest)
            self.log(f"Đã chọn sẵn video mới nhất: {Path(latest).name}", "info")
            if not self._auto_fill_from_folder(latest) and not self.var_title.get().strip():
                self.var_title.set(Path(latest).stem)   # gợi ý tiêu đề từ tên file

    def _pick_video(self):
        init = str(KICHBAN_DIR) if KICHBAN_DIR.is_dir() else str(Path.home())
        f = filedialog.askopenfilename(title="Chọn file video",
                                       initialdir=init, filetypes=VIDEO_EXTS)
        if f:
            self.var_video.set(f)
            if not self._auto_fill_from_folder(f) and not self.var_title.get().strip():
                self.var_title.set(Path(f).stem)   # gợi ý tiêu đề từ tên file

    def _auto_fill_from_folder(self, video_path):
        """Video nằm trong THƯ MỤC TẬP (kịch_bản/NN - .../ có seoYoutube.docx cạnh video):
        tự tách Tiêu đề/Mô tả/Thẻ tag từ file SEO đó (cùng cách nút 'Đọc SEO sẵn'),
        lấy số tập từ tên thư mục, chọn sẵn thumbnail<N>.png nếu có, đặt danh mục
        mặc định và hẹn giờ đăng = hiện tại + 1 ngày.

        Trả về True nếu thư mục có seoYoutube.docx (đã xử lý), False nếu không."""
        folder = Path(video_path).resolve().parent
        docx = folder / "seoYoutube.docx"
        if not docx.is_file():
            return False

        # Số tập nằm đầu tên thư mục 'NN - ...' → khớp số chèn vào tiêu đề/thumbnail.
        m = re.match(r"\s*(\d+)\s*-", folder.name)
        if m:
            self.var_episode.set(m.group(1).zfill(2))

        try:
            from seo_docx_parser import parse_seo_docx
            seo = parse_seo_docx(docx)
        except ImportError:
            messagebox.showerror("Thiếu thư viện",
                                 "Chưa cài python-docx. Chạy: pip install python-docx")
            return True
        except Exception as e:
            messagebox.showerror("Lỗi đọc SEO", f"Không đọc được {docx}:\n{e}")
            self.log("LỖI đọc SEO: " + str(e), "err")
            return True
        self.log(f"Thư mục tập {folder.name}: tự đọc {docx.name}", "info")
        self._apply_seo(seo)

        # Thumbnail cùng tập (vd thumbnail46.png) — bỏ bản dọc (_dọc) dành cho TikTok.
        if m:
            for name in (f"thumbnail{m.group(1)}.png",
                         f"thumbnail{int(m.group(1))}.png"):
                thumb = folder / name
                if thumb.is_file():
                    self.var_thumb.set(str(thumb))
                    break

        # Danh mục mặc định + hẹn giờ đăng = giờ hiện tại + 1 ngày.
        self.var_cat.set(DEFAULT_CATEGORY)
        self._set_sched((datetime.now() + timedelta(days=1)).replace(second=0, microsecond=0))
        return True

    def _change_episode(self, delta):
        """Tăng/giảm số tập, giữ độ rộng (zero-pad) như 01, 02 ..."""
        cur = self.var_episode.get().strip()
        if not cur.isdecimal():
            self.var_episode.set("01")
            return
        width = max(2, len(cur))
        self.var_episode.set(str(max(0, int(cur) + delta)).zfill(width))

    def _title_with_episode(self, title):
        """Chèn 'Số <số tập>' ngay sau 'Mimi audio' trong tiêu đề (khớp số ở thumbnail).

        Không có 'Mimi audio' thì thêm vào cuối; đã có 'Số' sẵn thì giữ nguyên.
        """
        ep = self.var_episode.get().strip()
        if not ep or not title:
            return title
        suffix = f"Số {ep}"
        marker = "mimi audio"
        idx = title.lower().rfind(marker)
        if idx == -1:
            return f"{title} {suffix}"
        end = idx + len(marker)
        after = title[end:]
        if after.lstrip().lower().startswith("số"):   # tránh nhân đôi khi chạy lại
            return title
        return f"{title[:end]} {suffix}{after}".rstrip()

    def _apply_seo(self, seo):
        """Điền Tiêu đề/Mô tả/Thẻ tag từ dict SEO đã tách vào form. Chạy ở main thread.

        Trả về tiêu đề (str) nếu điền được, "" nếu không tách được nội dung.
        """
        title, desc, tags = seo["title"], seo["description"], seo["tags"]
        issues = seo.get("issues", [])

        # Không tách được gì → nhiều khả năng Gemini trả về CẤU TRÚC KHÁC (hoặc file rỗng).
        if not (title or desc or tags):
            detail = "\n".join("• " + s for s in issues) if issues else \
                "• Không tìm thấy các mục Tiêu đề / Thẻ tag / Mô tả quen thuộc."
            messagebox.showerror(
                "Không đọc được SEO",
                "Gemini có thể đã trả về CẤU TRÚC KHÁC với định dạng mong đợi nên "
                "không tách được nội dung:\n\n" + detail +
                "\n\nHãy mở seoYoutube.docx kiểm tra, hoặc chạy lại quy trình SEO.")
            self.log("LỖI SEO: không tách được nội dung — " + " | ".join(issues), "err")
            return ""

        # Tách được MỘT PHẦN → vẫn điền phần có, nhưng CẢNH BÁO rõ phần bị thiếu.
        if issues:
            messagebox.showwarning(
                "SEO thiếu một số phần",
                "Cấu trúc SEO khác mong đợi — chỉ lấy được một phần. Thiếu:\n\n" +
                "\n".join("• " + s for s in issues) +
                "\n\nHãy kiểm tra lại các ô trước khi đăng.")
            for s in issues:
                self.log("⚠ SEO thiếu: " + s, "warn")

        # Chuẩn hoá 3 phần theo ĐÚNG quy ước tab 'Copy SEO theo tập' (amain_taogiong_gui
        # → _seo_copy_blocks) — dùng chung hàm thumbnail_gui để 2 nơi không lệch nhau.
        f_title, f_desc, f_tags = self._compose_like_copyseo(title, desc, tags)
        if title:
            self.var_title.set(f_title)
        if desc:
            self.txt_desc.delete("1.0", "end")
            self.txt_desc.insert("1.0", f_desc)
        if tags:
            self.var_tags.set(f_tags)
        self._update_counters()
        n_tags = len([t for t in f_tags.split(",") if t.strip()])
        self.log(f"✔ SEO: tiêu đề {len(f_title)} ký tự, {n_tags} thẻ tag, "
                 f"mô tả {len(f_desc)} ký tự.", "ok")
        return title

    def _compose_like_copyseo(self, title, desc, tags):
        """Chuẩn hoá (tiêu đề, mô tả, thẻ tag) theo quy ước tab 'Copy SEO theo tập':
          • tiêu đề : 'Mimi audio Số <tập> | <tên truyện>'
          • mô tả   : '#MimiAudioSo<tập>' lên đầu, 'Số <tập>' vào dòng tiêu đề,
                      '#truyenfull #full' ở cuối
          • thẻ tag : thẻ tập + tên truyện lên đầu, cắt cho vừa 500 (đếm kiểu YouTube)
        Trả về (title, desc, tags_csv). Không nạp được thumbnail_gui → dùng cách cũ."""
        try:
            import thumbnail_gui as tg
            ep = self.var_episode.get().strip()
            ep = ep if ep.isdecimal() else ""
            f_title = tg.compose_youtube_title(title, ep) or title
            f_desc = desc
            if desc:
                f_desc = tg.add_episode_to_description(desc, ep)
                f_desc = tg.add_episode_hashtag_top(f_desc, ep)
                f_desc = tg.add_full_hashtags(f_desc)
            f_tags = tg.cap_tags(tags, ep, title) if tags else ""
            return f_title, f_desc, f_tags
        except Exception as e:
            self.log(f"⚠ Không dùng được quy ước 'Copy SEO theo tập' ({e}) "
                     "— dùng cách chèn số tập cũ.", "warn")
            return self._title_with_episode(title), desc, ", ".join(tags)

    def _load_seo_from_docx(self):
        """Đọc lại seoYoutube.docx CÓ SẴN (không chạy Gemini), điền vào form."""
        path = SEO_DOCX_FILE
        if not path.exists():
            f = filedialog.askopenfilename(
                title="Chọn file SEO (.docx)",
                filetypes=[("Word", "*.docx"), ("Tất cả", "*.*")])
            if not f:
                return
            path = Path(f)
        try:
            from seo_docx_parser import parse_seo_docx
            seo = parse_seo_docx(path)
        except ImportError:
            messagebox.showerror("Thiếu thư viện",
                                 "Chưa cài python-docx. Chạy: pip install python-docx")
            return
        except Exception as e:
            messagebox.showerror("Lỗi đọc SEO", f"Không đọc được {path}:\n{e}")
            self.log("LỖI đọc SEO: " + str(e), "err")
            return
        self._apply_seo(seo)

    # ---- quy trình: SEO Gemini → điền form → tạo thumbnail ----
    def _on_seo_pipeline(self):
        """Bấm 'Lấy SEO + Thumbnail': chạy seo_youtube_gemini → điền form → thumbnail."""
        if self.worker is not None:
            return
        if not messagebox.askyesno(
                "Lấy SEO + Tạo thumbnail",
                "Quy trình tự động:\n"
                "①  Mở Firefox, gửi nội dung lên Gemini SEO → seoYoutube.docx\n"
                "②  Điền Tiêu đề / Mô tả / Thẻ tag vào form\n"
                "③  Tạo thumbnail từ tiêu đề + số tập, dùng luôn làm thumbnail đăng\n\n"
                "Hãy ĐÓNG Firefox đang mở (profile bị khoá khi đang chạy) và đảm bảo "
                "profile đã đăng nhập Google.\n\nTiếp tục?"):
            return
        number = self.var_episode.get().strip()
        self.pb["value"] = 0
        self.btn_seo.config(state="disabled")
        self.btn_upload.config(state="disabled")
        self.worker = threading.Thread(target=self._run_seo_pipeline,
                                       args=(number,), daemon=True)
        self.worker.start()

    def _run_seo_pipeline(self, number):
        """Chạy nền: ① Gemini SEO → ② đọc + điền form → ③ tạo thumbnail."""
        try:
            try:
                import seo_youtube_gemini as seo_gen
            except Exception as e:
                self.log("Không nạp được seo_youtube_gemini: " + str(e), "err")
                return

            src = str(seo_gen.DEFAULT_INPUT)
            if not Path(src).exists():
                self.log(f"Không thấy nguồn dịch: {src}\n"
                         "Hãy dịch Gemini (tạo gemini_result.docx) trước.", "err")
                return

            # ① Tạo SEO qua Gemini
            self.log("①  Mở Firefox + gửi nội dung lên Gemini SEO...", "info")
            seo_gen.run(src, str(SEO_DOCX_FILE), keep_open=True,
                        log=lambda m: self.log(str(m), "info"))

            # ② Đọc SEO + điền form (điền widget phải ở main thread → qua queue)
            from seo_docx_parser import parse_seo_docx
            seo = parse_seo_docx(SEO_DOCX_FILE)
            self.q.put(("seo_fill", seo))

            # ③ Tạo thumbnail từ tiêu đề SEO + số tập
            title = (seo.get("title") or "").strip()
            if not title:
                self.log("⚠ SEO không có tiêu đề → bỏ qua bước tạo thumbnail.", "warn")
                return
            self.log("③  Tạo thumbnail...", "info")
            thumb = self._make_thumbnail(title, number)
            self.q.put(("thumb_done", str(thumb)))
        except Exception as e:
            self.log("LỖI quy trình SEO: " + str(e), "err")
            self.log(traceback.format_exc(), "err")
        finally:
            self.q.put(("seo_done",))

    def _make_thumbnail(self, title, number):
        """Render 1 thumbnail vào kịch_bản/output bằng dien_tieu_de_thumbnail."""
        import dien_tieu_de_thumbnail as tr
        photos = tr.list_photo_files(tr.CAT_IMAGE_DIR)
        if not photos:
            raise RuntimeError(f"Không có ảnh nền trong: {tr.CAT_IMAGE_DIR}")
        photo = random.choice(photos)
        return tr.add_title(
            tr.SOURCE_IMAGE, tr.next_thumbnail_path(), title, photo,
            tr.FRAME_IMAGE, (number or tr.DEFAULT_NUMBER), tr.NUMBER_FRAME_IMAGE,
        )

    def _pick_thumb(self):
        f = filedialog.askopenfilename(title="Chọn ảnh thumbnail", filetypes=IMAGE_EXTS)
        if f:
            self.var_thumb.set(f)

    def _check_thumb(self, *_):
        """Kiểm tra thumbnail ngay tại GUI theo giới hạn của YouTube.
        Cập nhật self.thumb_ok và dòng trạng thái màu (✔/⚠/✖)."""
        path = self.var_thumb.get().strip()
        self.thumb_ok = True
        if not path:
            self.lbl_thumb.config(text="", foreground=UI["muted"])
            return

        p = Path(path)
        if not p.is_file():
            self.thumb_ok = False
            self.lbl_thumb.config(text="✖ Không tìm thấy file ảnh.", foreground=UI["log_err"])
            return

        size = p.stat().st_size
        try:
            from PIL import Image
            with Image.open(p) as im:
                w, h = im.size
                fmt = im.format
        except Exception:
            self.thumb_ok = False
            self.lbl_thumb.config(text="✖ Không đọc được ảnh (file hỏng hoặc không phải ảnh).",
                                  foreground=UI["log_err"])
            return

        errs, warns = [], []
        if size > THUMB_MAX_BYTES:
            errs.append(f"dung lượng {size/1024/1024:.1f}MB > 2MB")
        if fmt not in THUMB_FORMATS:
            errs.append(f"định dạng {fmt} không hỗ trợ (chỉ JPG/PNG/GIF)")
        if w < THUMB_MIN_WIDTH:
            errs.append(f"rộng {w}px < tối thiểu {THUMB_MIN_WIDTH}px")
        # Cảnh báo (không chặn upload):
        if h and abs(w / h - 16 / 9) > 0.05:
            warns.append("tỷ lệ không phải 16:9 (YouTube sẽ thêm viền)")
        if w < THUMB_REC_W or h < THUMB_REC_H:
            warns.append(f"nên dùng {THUMB_REC_W}x{THUMB_REC_H}")

        info = f"{w}x{h}, {fmt}, {size/1024:.0f}KB"
        if errs:
            self.thumb_ok = False
            self.lbl_thumb.config(text="✖ " + info + " — " + "; ".join(errs),
                                  foreground=UI["log_err"])
        elif warns:
            self.lbl_thumb.config(text="⚠ " + info + " — " + "; ".join(warns),
                                  foreground=UI["log_warn"])
        else:
            self.lbl_thumb.config(text="✔ " + info + " — phù hợp", foreground=UI["log_ok"])

    def _toggle_sched(self):
        state = "normal" if self.var_sched_on.get() else "disabled"
        for w in self._sched_widgets:
            w.config(state=state)
        self._update_sched_preview()

    def _sched_datetime(self):
        """Ghép các spinbox thành datetime (giờ máy). Lỗi nếu ngày/giờ không hợp lệ."""
        try:
            d = int(self.var_s_day.get())
            mo = int(self.var_s_month.get())
            y = int(self.var_s_year.get())
            h = int(self.var_s_hour.get())
            mi = int(self.var_s_minute.get())
        except (TypeError, ValueError):
            raise ValueError("Ngày/giờ phải là số.")
        try:
            return datetime(y, mo, d, h, mi)
        except ValueError:
            raise ValueError("Ngày giờ không tồn tại (ví dụ 30/02).")

    def _update_sched_preview(self):
        """Hiện ngày giờ sẽ đăng (kèm thứ trong tuần) hoặc cảnh báo nếu sai/quá khứ."""
        if not self.var_sched_on.get():
            self.lbl_sched.config(text="", foreground=UI["muted"])
            return
        try:
            dt = self._sched_datetime()
        except ValueError as e:
            self.lbl_sched.config(text="⚠ " + str(e), foreground=UI["log_err"])
            return
        thu = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"][dt.weekday()]
        if dt <= datetime.now():
            self.lbl_sched.config(
                text=f"→ {thu}, {dt.strftime('%d/%m/%Y %H:%M')}  — ⚠ đã ở quá khứ",
                foreground=UI["log_warn"])
        else:
            self.lbl_sched.config(
                text=f"→ Sẽ đăng: {thu}, {dt.strftime('%d/%m/%Y %H:%M')}",
                foreground=UI["log_ok"])

    def _set_sched(self, dt):
        """Điền datetime vào các spinbox và bật hẹn giờ (dùng cho nút đặt nhanh)."""
        self.var_s_day.set(f"{dt.day:02d}")
        self.var_s_month.set(f"{dt.month:02d}")
        self.var_s_year.set(str(dt.year))
        self.var_s_hour.set(f"{dt.hour:02d}")
        self.var_s_minute.set(f"{dt.minute:02d}")
        if not self.var_sched_on.get():
            self.var_sched_on.set(True)
        self._toggle_sched()   # mở khóa spinbox + cập nhật xem trước

    def _sched_quick(self, hours=None, at=None, tomorrow=False):
        """Đặt nhanh: sau N giờ, hoặc đến mốc giờ cố định (tự đẩy sang mai nếu đã qua)."""
        now = datetime.now()
        if hours:
            dt = (now + timedelta(hours=hours)).replace(second=0, microsecond=0)
        else:
            hh, mm = at
            dt = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if tomorrow or dt <= now:
                dt += timedelta(days=1)
        self._set_sched(dt)

    def _open_cfg_dir(self):
        try:
            os.startfile(str(YT_DIR))   # Windows
        except Exception:
            self.log(f"Thư mục cấu hình: {YT_DIR}", "info")

    def _open_help(self):
        webbrowser.open("https://console.cloud.google.com/apis/library/youtube.googleapis.com")
        messagebox.showinfo(
            "Hướng dẫn lấy quyền",
            "1. Bật 'YouTube Data API v3' trong Google Cloud Console.\n"
            "2. Tạo OAuth client ID loại 'Desktop app'.\n"
            "3. Tải JSON, đổi tên thành client_secret.json và đặt vào thư mục cấu hình\n"
            "   (bấm nút 'Mở thư mục cấu hình').\n\n"
            "Chi tiết đầy đủ nằm ở phần đầu file script.")

    # ---- cửa sổ Kênh & video ----
    def _open_channel_win(self):
        """Mở cửa sổ xem kênh đang đăng nhập + video đã đăng / đã hẹn giờ."""
        if self.chan_win is not None and self.chan_win.winfo_exists():
            self.chan_win.lift()
            return
        C = UI
        win = tk.Toplevel(self.root)
        self.chan_win = win
        win.title("Kênh & video trên YouTube")
        win.configure(bg=C["bg"])
        w, h = 900, 540
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        win.geometry(f"{w}x{h}+{max((sw - w) // 2, 0)}+{max((sh - h) // 3, 0)}")

        top = ttk.Frame(win)
        top.pack(fill="x", padx=12, pady=(12, 4))
        self.lbl_chan = ttk.Label(top, text="Kênh: đang tải…", style="Field.TLabel")
        self.lbl_chan.pack(side="left")
        self.btn_chan_switch = ttk.Button(top, text="🔁 Đổi kênh…", style="Soft.TButton",
                                          command=lambda: self._fetch_channel(force_new=True))
        self.btn_chan_switch.pack(side="right")
        self.btn_chan_reload = ttk.Button(top, text="🔄 Tải lại", style="Soft.TButton",
                                          command=lambda: self._fetch_channel(force_new=False))
        self.btn_chan_reload.pack(side="right", padx=(0, 6))

        ttk.Label(win, wraplength=860, style="Muted.TLabel",
                  text="1 Gmail có thể có nhiều kênh nhưng token chỉ nhìn thấy MỘT kênh "
                       "— kênh đã chọn lúc đăng nhập (video cũng đăng lên kênh đó). "
                       "Bấm 'Đổi kênh…' để đăng nhập lại và chọn kênh khác."
                  ).pack(anchor="w", padx=12)

        # Dòng cảnh báo các SỐ TẬP CÒN SÓT (tách 'Số N' từ tiêu đề video).
        self.lbl_missing = ttk.Label(win, text="", style="Muted.TLabel", wraplength=860)
        self.lbl_missing.pack(anchor="w", padx=12, pady=(4, 0))

        wrap = ttk.Frame(win)
        wrap.pack(fill="both", expand=True, padx=12, pady=(8, 4))
        wrap.columnconfigure(0, weight=1)
        wrap.rowconfigure(0, weight=1)
        tv = ttk.Treeview(wrap, columns=("title", "status", "time"), show="headings")
        tv.heading("title", text="Tiêu đề")
        tv.heading("status", text="Trạng thái")
        tv.heading("time", text="Thời gian (giờ máy)")
        tv.column("title", width=470, anchor="w")
        tv.column("status", width=170, anchor="w", stretch=False)
        tv.column("time", width=190, anchor="w", stretch=False)
        tv.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(wrap, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=sb.set)
        sb.grid(row=0, column=1, sticky="ns")
        tv.tag_configure("sched", foreground=UI["log_warn"])
        tv.tag_configure("public", foreground=UI["log_ok"])
        tv.bind("<Double-1>", self._open_selected_video)
        self.tv_chan = tv

        ttk.Label(win, text="Đúp chuột vào một dòng để mở video trong YouTube Studio.",
                  style="Muted.TLabel").pack(anchor="w", padx=12, pady=(0, 10))

        # Hiện cache ngay (nếu có) cho nhanh; API chỉ gọi 1 LẦN mỗi phiên chạy —
        # các lần mở cửa sổ sau dùng cache (đã được cập nhật khi đăng video mới).
        had_cache = self._show_cached_channel()
        if not (self.chan_fetched and had_cache):
            self._fetch_channel(force_new=False)

    def _open_selected_video(self, _e=None):
        """Đúp chuột vào một video trong bảng → mở trang sửa video ở YouTube Studio."""
        sel = self.tv_chan.selection()
        if sel:
            webbrowser.open(f"https://studio.youtube.com/video/{sel[0]}/edit")

    def _fetch_channel(self, force_new=False):
        """Chạy nền: đăng nhập (nếu cần) + đọc kênh & video rồi đổ vào bảng."""
        if self.chan_worker is not None:
            return
        if force_new and not messagebox.askyesno(
                "Đổi kênh",
                "Sẽ mở trình duyệt để bạn đăng nhập lại.\n\n"
                "Ở màn hình chọn tài khoản của Google, hãy chọn đúng KÊNH muốn "
                "dùng — mỗi kênh của cùng một Gmail hiện thành một dòng riêng.\n\n"
                "Token kênh hiện tại sẽ được giữ lại thành token_old_*.json.\n\n"
                "Tiếp tục?", parent=self.chan_win):
            return
        self.lbl_chan.config(text="Kênh: đang tải…")
        self.btn_chan_reload.config(state="disabled")
        self.btn_chan_switch.config(state="disabled")
        self.chan_worker = threading.Thread(target=self._run_fetch_channel,
                                            args=(force_new,), daemon=True)
        self.chan_worker.start()

    def _run_fetch_channel(self, force_new):
        try:
            missing = _check_deps()
            if missing:
                self.log(f"Thiếu thư viện Google API ({missing}).", "warn")
                install_deps(self.log)
                if _check_deps():
                    raise RuntimeError("Vẫn thiếu thư viện sau khi cài. Hãy cài thủ công.")
            chan, videos = fetch_channel_videos(self.log, max_videos=500,
                                                force_new_login=force_new)
            self.chan_fetched = True   # phiên này đã gọi API — lần sau dùng cache
            self.q.put(("chan_data", chan, videos))
        except Exception as e:
            self.log("LỖI đọc kênh: " + str(e), "err")
            self.log(traceback.format_exc(), "err")
            self.q.put(("chan_err",))
        finally:
            self.q.put(("chan_done",))

    def _chan_win_alive(self):
        return self.chan_win is not None and self.chan_win.winfo_exists()

    def _show_cached_channel(self):
        """Đổ dữ liệu từ cache (nếu có) vào cửa sổ. Trả về True nếu có cache."""
        data = load_video_cache()
        entry = data["channels"].get(data.get("current"))
        if not entry or not self._chan_win_alive():
            return False
        self._show_channel(entry["channel"], entry["videos"],
                           fetched_at=entry.get("fetched_at"))
        return True

    def _show_channel(self, chan, videos, fetched_at=None):
        """Đổ dữ liệu kênh + video vào cửa sổ. Chạy ở main thread (qua queue).

        fetched_at (chuỗi ISO) = dữ liệu lấy từ cache của lần gọi API lúc đó;
        None = dữ liệu API vừa gọi xong."""
        if not self._chan_win_alive():
            return
        extra = f"  ({chan['custom_url']})" if chan.get("custom_url") else ""
        note = ""
        if fetched_at:
            try:
                note = ("  ·  dữ liệu lúc "
                        + datetime.fromisoformat(fetched_at).strftime("%H:%M %d/%m"))
            except (TypeError, ValueError):
                pass
        self.lbl_chan.config(
            text=f"Kênh: {chan['title']}{extra}  ·  {chan['video_count']} video{note}")
        self.tv_chan.delete(*self.tv_chan.get_children())
        n_sched = 0
        for v in videos:
            if v["privacy"] == "private" and v["publish_at"]:
                n_sched += 1
                status, t, tag = "🕑 Đã hẹn giờ", v["publish_at"], "sched"
            elif v["privacy"] == "public":
                status, t, tag = "✔ Công khai", v["published_at"], "public"
            elif v["privacy"] == "unlisted":
                status, t, tag = "Không công khai", v["published_at"], ""
            else:
                status, t, tag = "Riêng tư", v["published_at"], ""
            ts = t.strftime("%d/%m/%Y %H:%M") if t else ""
            self.tv_chan.insert("", "end", iid=v["id"],
                                values=(v["title"], status, ts),
                                tags=(tag,) if tag else ())
        # Dò các số tập còn sót để làm bù (tính cả video đang hẹn giờ).
        missing, lo, hi = find_missing_episodes(videos)
        if lo is None:
            self.lbl_missing.config(text="Không tách được 'Số ...' từ tiêu đề video "
                                         "nên chưa dò được tập thiếu.",
                                    foreground=UI["muted"])
        elif missing:
            self.lbl_missing.config(
                text=f"⚠ Tập còn thiếu (đã có Số {lo} → Số {hi}): "
                     + ", ".join(map(str, missing)),
                foreground=UI["log_warn"])
        else:
            self.lbl_missing.config(
                text=f"✔ Đủ tập liên tục từ Số {lo} đến Số {hi} — không sót tập nào.",
                foreground=UI["log_ok"])

        if fetched_at is None:   # chỉ log khi là dữ liệu API mới (cache thì im lặng)
            self.log(f"Kênh '{chan['title']}': {len(videos)} video gần nhất, "
                     f"trong đó {n_sched} đang hẹn giờ.", "ok")
            if missing:
                self.log("⚠ Tập còn thiếu: " + ", ".join(map(str, missing)), "warn")

    def _on_close(self):
        """Bấm ✕ khi đang tải video / chạy SEO: worker là thread daemon nên đóng
        cửa sổ là NGẮT giữa chừng không một lời báo — hỏi xác nhận trước."""
        if self.worker is not None and not messagebox.askyesno(
                "Đang chạy dở",
                "Đang tải video lên YouTube hoặc chạy SEO.\n"
                "Đóng cửa sổ bây giờ sẽ NGẮT công việc giữa chừng.\n\nVẫn đóng?"):
            return
        self.root.destroy()

    def _update_counters(self):
        t = len(self.var_title.get())
        d = len(self.txt_desc.get("1.0", "end-1c"))
        tags = self._parse_tags()
        try:
            import thumbnail_gui as tg
            g = tg.youtube_tags_len(tags)   # đếm đúng kiểu YouTube (khớp cap_tags)
        except Exception:
            g = sum(len(x) for x in tags) + max(0, len(tags) - 1)
        self.lbl_title_cnt.config(text=f"{t}/{MAX_TITLE}",
                                  foreground=UI["log_err"] if t > MAX_TITLE else UI["muted"])
        self.lbl_desc_cnt.config(text=f"{d}/{MAX_DESC}",
                                 foreground=UI["log_err"] if d > MAX_DESC else UI["muted"])
        self.lbl_tags_cnt.config(text=f"{g}/{MAX_TAGS_TOTAL}",
                                 foreground=UI["log_err"] if g > MAX_TAGS_TOTAL else UI["muted"])

    def _parse_tags(self):
        return [t.strip() for t in self.var_tags.get().split(",") if t.strip()]

    def log(self, msg, level="info"):
        self.q.put(("log", level, msg))

    # ---- queue polling (cập nhật GUI từ thread chính) ----
    def _poll_queue(self):
        try:
            while True:
                kind, *rest = self.q.get_nowait()
                if kind == "log":
                    level, msg = rest
                    self.log_widget.config(state="normal")
                    self.log_widget.insert("end", msg + "\n", level)
                    self.log_widget.see("end")
                    self.log_widget.config(state="disabled")
                elif kind == "progress":
                    self.pb["value"] = rest[0]
                elif kind == "done":
                    self.btn_upload.config(state="normal")
                    self.btn_seo.config(state="normal")
                    self.worker = None
                    if self._chan_win_alive():   # video vừa đăng đã nằm trong cache
                        self._show_cached_channel()
                elif kind == "seo_fill":
                    self._apply_seo(rest[0])
                elif kind == "thumb_done":
                    path = rest[0]
                    self.var_thumb.set(path)   # dùng luôn làm thumbnail để đăng
                    self.log("Đã tạo thumbnail: " + path, "ok")
                elif kind == "seo_done":
                    self.btn_seo.config(state="normal")
                    self.btn_upload.config(state="normal")
                    self.worker = None
                elif kind == "chan_data":
                    self._show_channel(*rest)
                elif kind == "chan_err":
                    if self._chan_win_alive():
                        self.lbl_chan.config(text="Kênh: LỖI — xem nhật ký ở cửa sổ chính")
                elif kind == "chan_done":
                    self.chan_worker = None
                    if self._chan_win_alive():
                        self.btn_chan_reload.config(state="normal")
                        self.btn_chan_switch.config(state="normal")
        except queue.Empty:
            pass
        self.root.after(120, self._poll_queue)

    # ---- validate + upload ----
    def _validate(self):
        v = self.var_video.get().strip()
        if not v or not Path(v).is_file():
            return "Chưa chọn file video hợp lệ."
        if not self.var_title.get().strip():
            return "Chưa nhập tiêu đề."
        if len(self.var_title.get()) > MAX_TITLE:
            return f"Tiêu đề quá dài (> {MAX_TITLE} ký tự)."
        if len(self.txt_desc.get('1.0', 'end-1c')) > MAX_DESC:
            return f"Mô tả quá dài (> {MAX_DESC} ký tự)."
        th = self.var_thumb.get().strip()
        if th:
            self._check_thumb()
            if not self.thumb_ok:
                return "Thumbnail không hợp lệ — xem dòng đỏ dưới ô thumbnail."
        if self.var_sched_on.get():
            try:
                dt = self._sched_datetime()
            except ValueError as e:
                return "Giờ hẹn không hợp lệ: " + str(e)
            if dt <= datetime.now():
                return "Giờ hẹn phải ở tương lai (hãy chọn ngày giờ sau hiện tại)."
        return None

    def _sched_to_rfc3339(self):
        """Chuyển ngày giờ đã chọn (giờ máy) sang RFC3339 UTC mà API yêu cầu."""
        return to_rfc3339(self._sched_datetime())

    def _on_upload(self):
        if self.worker is not None:
            return
        err = self._validate()
        if err:
            messagebox.showerror("Thiếu thông tin", err)
            return

        opts = {
            "video_path": self.var_video.get().strip(),
            "title": self.var_title.get().strip(),
            "description": self.txt_desc.get("1.0", "end-1c"),
            "tags": self._parse_tags(),
            "category_id": CATEGORIES[self.var_cat.get()],
            "privacy": PRIVACY[self.var_priv.get()],
            "made_for_kids": self.var_kids.get(),
            "contains_ai": self.var_ai.get(),
            "thumbnail_path": self.var_thumb.get().strip() or None,
            "publish_at": self._sched_to_rfc3339() if self.var_sched_on.get() else None,
        }
        self._save_settings()
        self.pb["value"] = 0
        self.btn_upload.config(state="disabled")
        self.btn_seo.config(state="disabled")
        self.worker = threading.Thread(target=self._run, args=(opts,), daemon=True)
        self.worker.start()

    def _run(self, opts):
        try:
            missing = _check_deps()
            if missing:
                self.log(f"Thiếu thư viện Google API ({missing}).", "warn")
                install_deps(self.log)
                if _check_deps():
                    raise RuntimeError("Vẫn thiếu thư viện sau khi cài. Hãy cài thủ công.")
            upload_video(opts, self.log,
                         lambda p: self.q.put(("progress", p)))
        except Exception as e:
            self.log("LỖI: " + str(e), "err")
            self.log(traceback.format_exc(), "err")
        finally:
            self.q.put(("done",))

    # ---- ghi nhớ lựa chọn ----
    def _save_settings(self):
        data = {
            "title": self.var_title.get(),
            "description": self.txt_desc.get("1.0", "end-1c"),
            "tags": self.var_tags.get(),
            "category": self.var_cat.get(),
            "privacy": self.var_priv.get(),
            "made_for_kids": self.var_kids.get(),
            "contains_ai": self.var_ai.get(),
            "episode": self.var_episode.get(),
        }
        try:
            SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
        except Exception:
            pass

    def _load_settings(self):
        if not SETTINGS_FILE.exists():
            self.log("Sẵn sàng. Lần đầu dùng: đặt client_secret.json vào thư mục cấu hình "
                     "(nút 'Mở thư mục cấu hình').", "info")
            return
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            self.var_title.set(data.get("title", ""))
            self.txt_desc.insert("1.0", data.get("description", ""))
            self.var_tags.set(data.get("tags", ""))
            if data.get("category") in CATEGORIES:
                self.var_cat.set(data["category"])
            if data.get("privacy") in PRIVACY:
                self.var_priv.set(data["privacy"])
            self.var_kids.set(bool(data.get("made_for_kids", False)))
            self.var_ai.set(bool(data.get("contains_ai", True)))
            ep = str(data.get("episode", "")).strip()
            if ep.isdecimal():
                self.var_episode.set(ep.zfill(max(2, len(ep))))
            self._update_counters()
        except Exception:
            pass


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
