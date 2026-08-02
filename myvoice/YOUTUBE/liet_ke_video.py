# -*- coding: utf-8 -*-
"""
liet_ke_video.py — Liệt kê DANH SÁCH VIDEO ĐÃ ĐĂNG của kênh (kể cả video đang
HẸN GIỜ, còn ở chế độ riêng tư) qua YouTube Data API v3.

Máy KHÔNG lưu danh sách bài đăng — dang_video_youtube.py đăng xong chỉ in link
vào Nhật ký. Danh sách thật nằm trên kênh, trong playlist "uploads"; script này
đăng nhập OAuth với quyền CHỈ ĐỌC (youtube.readonly) rồi in ra:
    ID · chế độ (public/private/unlisted) · giờ đăng hoặc giờ HẸN · tiêu đề

Token đọc lưu RIÊNG (token_readonly.json) — không đụng token upload (token.json)
của app đăng video.

Chạy:   python liet_ke_video.py [số_video]
        số_video mặc định 30; dùng 'all' để lấy toàn bộ.

Lần ĐẦU chạy sẽ mở trình duyệt đăng nhập — gmail có 2 KÊNH thì màn hình Google
sẽ liệt kê cả hai: NHỚ CHỌN ĐÚNG KÊNH muốn xem (token gắn với kênh đã chọn;
muốn đổi kênh thì xoá token_readonly.json rồi chạy lại).
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

# In tiếng Việt ra console Windows (mặc định cp1252 sẽ lỗi UnicodeEncodeError).
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE_DIR = Path(__file__).resolve().parent
CLIENT_SECRET_FILE = BASE_DIR / "client_secret.json"     # dùng chung với app đăng video
TOKEN_RO_FILE = BASE_DIR / "token_readonly.json"         # token CHỈ ĐỌC, riêng script này

SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]


def get_credentials():
    """Đăng nhập OAuth quyền chỉ đọc; tự refresh, lưu token_readonly.json."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not CLIENT_SECRET_FILE.exists():
        raise SystemExit(f"Chưa có client_secret.json tại: {CLIENT_SECRET_FILE}")

    creds = None
    if TOKEN_RO_FILE.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_RO_FILE), SCOPES)
        except Exception:
            creds = None
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            TOKEN_RO_FILE.write_text(creds.to_json(), encoding="utf-8")
            return creds
        except Exception:
            pass

    print("Mở trình duyệt đăng nhập (chọn ĐÚNG kênh muốn xem)...")
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_FILE), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent select_account")
    TOKEN_RO_FILE.write_text(creds.to_json(), encoding="utf-8")
    return creds


def _local(ts):
    """RFC3339 UTC ('2026-08-03T10:00:00Z') → 'dd/mm/YYYY HH:MM' giờ máy."""
    if not ts:
        return ""
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return dt.astimezone().strftime("%d/%m/%Y %H:%M")


def main():
    limit = 30
    if len(sys.argv) > 1:
        limit = None if sys.argv[1].lower() == "all" else int(sys.argv[1])

    from googleapiclient.discovery import build
    youtube = build("youtube", "v3", credentials=get_credentials(),
                    cache_discovery=False)

    # Kênh của token → playlist 'uploads' chứa TOÀN BỘ video đã tải lên.
    ch = youtube.channels().list(part="snippet,contentDetails", mine=True).execute()
    items = ch.get("items") or []
    if not items:
        raise SystemExit("Token này không gắn với kênh nào (chọn nhầm tài khoản?).")
    channel = items[0]
    uploads_id = channel["contentDetails"]["relatedPlaylists"]["uploads"]
    print(f"\nKênh: {channel['snippet']['title']}  (playlist uploads: {uploads_id})\n")

    # Duyệt playlist uploads (mới nhất trước), gom videoId theo trang 50.
    video_ids = []
    page = None
    while True:
        res = youtube.playlistItems().list(
            part="contentDetails", playlistId=uploads_id,
            maxResults=50, pageToken=page).execute()
        video_ids += [it["contentDetails"]["videoId"] for it in res.get("items", [])]
        page = res.get("nextPageToken")
        if not page or (limit and len(video_ids) >= limit):
            break
    if limit:
        video_ids = video_ids[:limit]
    if not video_ids:
        print("Kênh chưa có video nào.")
        return

    # Lấy chế độ + giờ hẹn (status.publishAt chỉ hiện với video mình sở hữu).
    rows = []
    for i in range(0, len(video_ids), 50):
        res = youtube.videos().list(part="snippet,status",
                                    id=",".join(video_ids[i:i + 50])).execute()
        for v in res.get("items", []):
            st = v.get("status", {})
            sched = st.get("publishAt")
            if sched:
                dt = datetime.fromisoformat(sched.replace("Z", "+00:00"))
                when = ("HẸN " if dt > datetime.now(timezone.utc) else "") + _local(sched)
            else:
                when = _local(v["snippet"].get("publishedAt"))
            rows.append((v["id"], st.get("privacyStatus", "?"), when,
                         v["snippet"].get("title", "")))

    w_when = max(len(r[2]) for r in rows)
    print(f"{'#':>3}  {'VIDEO ID':<11}  {'CHẾ ĐỘ':<8}  {'GIỜ ĐĂNG / HẸN':<{w_when}}  TIÊU ĐỀ")
    print("-" * (3 + 2 + 11 + 2 + 8 + 2 + w_when + 2 + 40))
    for n, (vid, priv, when, title) in enumerate(rows, 1):
        print(f"{n:>3}  {vid:<11}  {priv:<8}  {when:<{w_when}}  {title}")
    print(f"\nTổng: {len(rows)} video.  Link: https://youtu.be/<VIDEO ID>")


if __name__ == "__main__":
    main()
