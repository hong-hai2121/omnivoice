# TRINHDUYET — đăng YouTube Studio + TikTok Studio bằng Chrome thật

Đường đăng thứ hai của OmniVoice, song song với `YOUTUBE/` (Data API, hạn mức ~11 video/ngày) và
`FACEBOOK/` (Graph API). Playwright điều khiển **chính Chrome đang mở** của bạn qua extension
"Playwright Extension" (Microsoft) — không mở Chrome riêng, cookie/đăng nhập giữ nguyên, Chrome ≥ 136
không chặn được vì không dùng cổng DevTools.

Cách làm mượn từ tool "Đăng video tự động" (`D:\Python\GetLinktoText\DangvideoYTBTikTokZalo`).
**Không dùng chung profile/token với tool đó** — `trinhduyet.kiem_profile_cam()` từ chối ngay khi cấu
hình trỏ vào Chrome "Profile 9" / "Profile 85" hay Cốc Cốc "Profile 12", hoặc token của ba profile đó.

## Chuẩn bị profile (một lần cho mỗi nền tảng)

1. Trong Chrome, tạo/chọn profile riêng cho kênh Mimi audio (YouTube) và một profile cho TikTok
   (có thể dùng một profile cho cả hai nếu cùng đăng nhập; khi đó điền giống nhau).
2. Mở profile đó → cài **Playwright Extension** từ Chrome Web Store
   (`https://chromewebstore.google.com/detail/playwright-extension/mmlmfjhmonkocbjadbfplnigmagldckm`).
3. `chrome://extensions` → Chi tiết của extension → bật **"Cho phép truy cập URL tệp"** (bắt buộc:
   không bật thì không nạp được file video, Chrome trả "Not allowed").
4. Bấm icon extension → trang trạng thái → chép dòng `PLAYWRIGHT_MCP_EXTENSION_TOKEN=…`.
5. Tên thư mục profile: `chrome://version` → dòng "Đường dẫn hồ sơ" (ví dụ `…\User Data\Profile 3`
   → `profile_dir` = `Profile 3`).
6. Điền vào `cau_hinh.json` (tự tạo khi chạy lần đầu, profile để trống):

```json
"nen_tang": {
  "youtube": {"profile_dir": "Profile 3", "extension_token": "PLAYWRIGHT_MCP_EXTENSION_TOKEN=…"},
  "tiktok":  {"profile_dir": "Profile 4", "extension_token": "…"}
}
```

`browser_path` / `user_data_dir` để trống = chrome.exe và `User Data` mặc định. Chưa điền nền tảng nào
thì nền tảng đó bị bỏ qua (mã dừng 77), không phải lỗi.

## Chạy

```bat
venv\Scripts\python myvoice\web\runners\run_dang_trinhduyet.py --episode 156 --ke-hoach   # chỉ in kế hoạch
venv\Scripts\python myvoice\web\runners\run_dang_trinhduyet.py --episode 156 --chay-thu   # làm hết, dừng trước nút cuối
venv\Scripts\python myvoice\web\runners\run_dang_trinhduyet.py --episode 153 154 155      # đăng thật
```

Trên bảng web: khối **Đăng YouTube** → ô **Cách đăng** = "Trình duyệt Chrome" → các nút ⑤ / "⬆ Đăng
ngay" / ô "⬆ tự động đăng" đều đi qua runner này (hàng đợi đăng, mỗi tập một việc).

## Lấy gì trong thư mục tập

| Nền tảng | File | Tiêu đề / mô tả | Giờ |
|---|---|---|---|
| YouTube | `YOUTUBE.mp4` + `thumbnail<NN>.png`, rồi `short.mp4` | `core.seo_blocks` (đúng 3 nút Copy SEO) | khung 08:00/18:00 sau video lên lịch muộn nhất; Short +1 giờ |
| TikTok | `[Full] …` / `facebook.mp4` (`tiktok_ban` = `full`) hoặc `tiktok.mp4` (`ngan`) | tiêu đề TikTok + 6 hashtag đầu của mô tả | khung 08:00/18:00 sau bài TikTok muộn nhất; chỉ trong 15 phút–10 ngày |

Biên nhận: `youtube_upload.json` (cùng khuôn với đường API, thêm `"via": "studio"`) và
`tiktok_upload.json`. Sau khi đăng YouTube, hai bản dọc được đổi tên như đường API
(`Full ở …`, `[Full] …`).

Giờ đã hẹn lấy từ biên nhận của mọi tập **cộng** lịch đọc thật trên Studio (`doc_lich_that`; tắt bằng
`--khong-doc-lich`). Chốt an toàn giữ nguyên: bản dịch còn đoạn hỏng → không đăng; tên truyện trùng tập
khác đã đăng → không đăng; tiêu đề > 100 ký tự → không đăng.

## Khi lỗi

Ảnh chụp tab lúc lỗi: `loi_gan_nhat_youtube.png` / `loi_gan_nhat_tiktok.png` trong thư mục này.
Tab Chrome được giữ mở ở chế độ `--chay-thu` để xem; chạy thật thì tab đóng khi xong.
