# myvoice

Thư mục này chứa các công cụ và dữ liệu tự viết thêm cho quy trình tạo video/lồng tiếng. Phần lõi của OmniVoice nằm ở các thư mục cấp trên; phần việc thực tế hằng ngày nằm chủ yếu trong `myvoice/`.

## Chạy script

Chạy từ thư mục gốc `OmniVoice/` để dùng đúng môi trường Python:

```powershell
venv\Scripts\python myvoice\scripts\<ten_script>.py
```

Một số script gọi `ffmpeg`/`ffprobe`, vì vậy hai lệnh này phải có trong `PATH`. Các script Gemini hoặc YouTube có thể cần cấu hình khóa/API riêng trong mã hoặc biến môi trường trước khi chạy.

## Bản đồ thư mục

| Đường dẫn | Nội dung |
| --- | --- |
| `Anh/` | Ảnh nguồn dùng cho hiệu ứng bong bóng. Không có script hiện tại tự đổi tên ảnh trong thư mục này. |
| `Anh/Pink.png` | Ảnh đặc biệt trong hiệu ứng bong bóng: luôn dùng cho bong bóng lớn nhất, mặc định không được chọn ngẫu nhiên. |
| `Backbround/` | Các PNG khung/nền để ghép video. Tên thư mục đang là `Backbround` và không nên tự đổi nếu chưa sửa các script tham chiếu. |
| `kịch_bản/` | Kịch bản, DOCX, dữ liệu gợi ý clip và các đầu ra như audio/video/thumbnail. |
| `mp4/` | Video nguồn, thường còn âm thanh. |
| `videodoc/` | Video dọc. |
| `videongang/` | Video ngang. |
| `voice/` | File giọng mẫu để clone giọng. |
| `YOUTUBE/` | Công cụ tạo thumbnail, SEO và đăng video YouTube. |
| `scripts/` | Các script xử lý TTS, audio, video và tài liệu. |

## Các script cần nhớ

| Script | Mục đích |
| --- | --- |
| `scripts/taogiong_gui.py` | Giao diện chính để tạo/clone giọng nói từ kịch bản. |
| `scripts/taogiong.py` | Bản chạy dòng lệnh của quy trình clone giọng. |
| `scripts/taogiong_kiemtra_audio.py` | Rà các đoạn WAV lỗi/spike sau khi tạo audio. |
| `scripts/video_xoatieng.py` | Xóa audio gốc khỏi video nguồn trước khi ghép. |
| `scripts/video_ghepcuoi.py` | Ghép video đã tắt tiếng với `kịch_bản/output.wav`. |
| `scripts/video_khung.py` | Đưa video vào khung PNG trong `Backbround/`. |
| `scripts/doiten_video.py` | Chuẩn hóa và đổi tên **video ngang** theo thứ tự; không xử lý ảnh. |
| `scripts/doiten_anh.py` | Chỉ đổi tên ảnh mới/chưa có tên số chuẩn trong `Anh/`; các file như `1.png`, `2.jpg` và `Pink.png` được giữ nguyên. Chạy trực tiếp sẽ đổi tên, thêm `--dry-run` để chỉ xem trước. |
| `scripts/video_bongbong.py` | Tạo/ghép hiệu ứng bong bóng; đọc ảnh trong `Anh/` và xử lý riêng `Pink.png`. Đầu ra mặc định nằm trong `scripts/hieuung/`. |
| `scripts/video_bongbong_gui.py` | Giao diện chọn video, ảnh, tên file xuất và các tham số hiệu ứng để chạy `video_bongbong.py` mà không sửa mã. Đầu ra luôn nằm trong `scripts/hieuung/`. |
| `scripts/video_gansub.py` | Gắn phụ đề vào video. |
| `scripts/video_timclip.py` | Tìm/gợi ý đoạn clip phù hợp từ nội dung. |
| `scripts/dich_tachdoan.py` | Tách nội dung DOCX thành các phần. |
| `scripts/dich_docx.py` | Dịch DOCX qua Gemini. |
| `scripts/dich_chuanbi_input.py` | Chuẩn bị dữ liệu đầu vào từ kết quả Gemini. |
| `scripts/dich_kiemtra.py` | Kiểm tra DOCX do Gemini tạo/trả về. |
| `scripts/nhandien_gui.py` | Giao diện nhận diện/chuyển đổi audio. |
| `scripts/nhandien_giongnoi.py` | Nhận diện audio tiếng Trung. |
| `YOUTUBE/tao_thumbnail.py` | Tạo thumbnail 1280×720 từ tiêu đề SEO hoặc DOCX. |
| `YOUTUBE/dien_tieu_de_thumbnail.py` | Ghép nền `thumbnail/khung nên.png`, tiêu đề/ảnh mèo/số tập và khung trên `thumbnail/khung trên.png` theo đúng thứ tự lớp; ảnh mèo từ `Anh/` được crop theo `thumbnail/ảnh.png`. Tạo PNG mới, không ghi đè ảnh gốc. |
| `YOUTUBE/thumbnail_gui.py` | GUI nhập tiêu đề và số tập; tự chọn ảnh mèo ngẫu nhiên trong `Anh/`, có xem trước ảnh trước khi tạo thumbnail. Kết quả lưu trong `kịch_bản/output/` theo tên `thumbnail01.png`, `thumbnail02.png`, … |
| `YOUTUBE/seo_youtube_gemini.py` | Tạo nội dung SEO YouTube qua Gemini. |
| `YOUTUBE/dang_video_youtube.py` | Đăng video lên YouTube. |

## Lưu ý về thư mục `Anh/`

`video_bongbong.py` chỉ nạp các ảnh `.png`, `.jpg`, `.jpeg`, `.webp` rồi dùng chúng trong hiệu ứng. Nó **không đổi tên bất kỳ file nào**.

`Pink.png` được khai báo qua `FEATURE_IMAGE_NAME = "Pink.png"`. Khi cần đổi tên hàng loạt ảnh, phải dùng một script riêng và luôn loại trừ file này để tên `Pink.png` không thay đổi.

Script có sẵn cho việc này là `scripts/doiten_anh.py`. Các ảnh đã tên số chuẩn như `1.png`, `2.jpg` được giữ nguyên. Ảnh mới được sắp theo tên kiểu tự nhiên (ví dụ `2.png` trước `10.png`), giữ phần mở rộng và nhận số tiếp theo sau số lớn nhất hiện có:

```powershell
# Đổi tên thật
venv\Scripts\python myvoice\scripts\doiten_anh.py

# Chỉ xem danh sách thay đổi
venv\Scripts\python myvoice\scripts\doiten_anh.py --dry-run
```

## Quy trình cơ bản

```text
kịch_bản/input.txt
  → taogiong_gui.py hoặc taogiong.py
  → kịch_bản/output.wav
  → video_xoatieng.py (nếu cần chuẩn bị video nguồn)
  → video_ghepcuoi.py / video_khung.py / video_bongbong.py / video_gansub.py
  → video hoàn thiện
```

## GUI hiệu ứng bong bóng

Chạy giao diện bằng lệnh sau:

```powershell
venv\Scripts\python myvoice\scripts\video_bongbong_gui.py
```

Chế độ **Ghép trực tiếp** tạo MP4 có bong bóng và giữ âm thanh video. Chế độ **MOV trong suốt** tạo lớp bong bóng có alpha để ghép ở bước khác. GUI luôn giữ `Pink.png` làm ảnh của bong bóng lớn nhất nếu file này có trong thư mục ảnh. Mọi file xuất được lưu tại `scripts/hieuung/`; nếu trùng tên, renderer tự thêm `_2`, `_3`, … thay vì ghi đè file cũ.

Tùy chọn **Dùng từng ảnh một lần và tự dừng khi đã hết ảnh** không dùng giới hạn thời gian đặt sẵn: mỗi ảnh thường xuất hiện một lần rồi MOV kết thúc sau khi bong bóng cuối bay hết và mờ tan. `Pink.png` vẫn là bong bóng đặc biệt. Tùy chọn này chỉ dùng với MOV nền trong suốt vì MP4 ghép trực tiếp không thể dài hơn video nguồn.

## Trước khi chạy một script mới

1. Mở phần cấu hình ở đầu file: nhiều script đặt sẵn thư mục input, output và tùy chọn xử lý.
2. Kiểm tra đầu vào/đầu ra để tránh ghi đè file đang dùng.
3. Với các script xử lý hàng loạt, thử trên một bản sao dữ liệu trước.

Tài liệu chi tiết hơn về pipeline TTS cũ nằm tại [`HUONG_DAN_SCRIPT_TU_VIET.md`](HUONG_DAN_SCRIPT_TU_VIET.md).
