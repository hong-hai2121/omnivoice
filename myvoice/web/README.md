# Bảng điều khiển web

Bản web chạy **song song** với GUI Tkinter, không thay thế và không sửa gì trong
`scripts/`. Sinh ra vì GUI đã hết chỗ: mỗi chức năng mới lại phải chen thêm một
tab, còn web thì thêm một trang là xong — và xem được từ điện thoại.

## Chạy

```
myvoice\chay_web.bat
```

Cửa sổ console in ra hai đường dẫn: một cho máy này, một cho điện thoại trong
cùng WiFi. Mở đường dẫn kèm `?token=…`, token được nhớ trong cookie 30 ngày.

Đổi cổng: đặt biến môi trường `MYVOICE_WEB_PORT` (mặc định `8765`).
Đổi token: xoá `web/token.txt`, chạy lại.

⚠️ Server này chạy ffmpeg, dùng GPU, mở Firefox và ghi file trên máy bạn. Chỉ để
trong mạng nhà — **đừng mở cổng ra Internet**.

## Bốn trang

| Trang | Làm gì |
|---|---|
| **Tiến độ** | Mọi tập trong `kịch_bản/` với 8 bước; bấm ô còn thiếu để chạy lại đúng bước đó |
| **Chạy** | Dán nhiều link/file, chọn bước, xếp vào hàng đợi; tạm dừng · bỏ việc · dừng hết |
| **Copy SEO** | Tiêu đề · tiêu đề TikTok · mô tả · thẻ tag, đúng nội dung 3 nút Copy bên GUI |
| **Cài đặt** | Giọng, nhận diện, video ngang/dọc/TikTok, phụ đề |

Nhật ký hiện ở đáy mọi trang, đẩy thẳng từ tiến trình đang chạy (SSE).

## Cấu trúc

```
web/
  server.py      FastAPI: route + token + SSE nhật ký
  core.py        cầu nối sang scripts/ — hằng đường dẫn, trạng thái tập, cài đặt, SEO
  jobs.py        hàng đợi MỘT worker; mỗi bước là một tiến trình con
  steps.py       yêu cầu từ giao diện → danh sách bước cho hàng đợi
  runners/
    run_episode.py  chạy các bước của một tập
  templates/     Jinja2 + HTMX
  static/        CSS, JS, htmx.min.js (kèm sẵn — chạy được khi không có mạng)
```

## Hai điều cần biết khi sửa

**1. Không chép lại logic.** `runners/run_episode.py` tạo một `App` “rỗng”
(`HeadlessApp` — cố ý không gọi `super().__init__()` nên không dựng cửa sổ Tk) rồi
gọi thẳng các method thuần logic của `amain_taogiong_gui`: `_allocate_episode`,
`_dich_gemini_cho_tap`, `_batch_prepare_input`, `_make_thumbnail_for_folder`,
`_batch_run_tts`, `_manifest_update`. Nhờ vậy các chốt an toàn (dịch thiếu đoạn thì
KHÔNG ghi input.txt, không tạo audio/video) chỉ tồn tại ở MỘT nơi.

Hệ quả: method nào bên GUI đổi sang đọc `tk.Var` thì web sẽ **nổ ngay** chứ không
âm thầm chạy sai. Đó là chủ ý.

**2. Cài đặt dùng chung với GUI.** Trang Cài đặt ghi vào chính
`taogiong_options.json` và `taogiong_pipeline.json`. Riêng chế độ giọng + giọng
mẫu để ở `web/web_settings.json`, vì `_save_opt_settings` của GUI ghi đè file kia
bằng một dict cố định nên khoá lạ sẽ bị xoá.

Checkbox nào hiển thị trên trang thì kèm một hidden `_bools` khai tên mình. Không
có nó, các tuỳ chọn chỉ GUI dùng (`from_gemini`, `bring_front`) sẽ bị tắt mỗi lần
lưu — checkbox bỏ tick thì trình duyệt không gửi gì cả, không thể suy ra ý định.

## Giới hạn hiện tại

- Mỗi bước là một tiến trình mới → model Whisper nạp lại cho mỗi tập (~10–20s).
  GUI giữ model qua các tập nên nhanh hơn ở batch dài.
- Chưa có: thumbnail (chỉnh tay), đăng YouTube, gán sub, xoá tiếng, bong bóng.
  Các GUI rời đó vẫn dùng như cũ.
- “Tạm dừng” dừng giữa các việc, không dừng giữa chừng một bước đang chạy.
