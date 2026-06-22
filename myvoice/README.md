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
| `mp4/` | Video nguồn (còn âm thanh) cho `video_xoatieng.py`. |
| `videodoc/` | Kho clip **dọc** để ghép video dọc; chuẩn hóa + đổi tên `_doc_*.mp4` bằng `doiten_video.py` (chế độ dọc). |
| `videongang/` | Kho clip **ngang** để ghép video ngang; chuẩn hóa + đổi tên `_ng_*.mp4` bằng `doiten_video.py` (chế độ ngang). |
| `voice/` | File giọng mẫu để clone giọng. |
| `YOUTUBE/` | Công cụ tạo thumbnail, SEO và đăng video YouTube. |
| `scripts/` | Các script xử lý TTS, audio, video và tài liệu. |

## Các script cần nhớ

| Script | Mục đích |
| --- | --- |
| `scripts/taogiong_gui.py` | **Giao diện chính, tất-cả-trong-một.** Cột trái: quy trình tạo kịch bản (① nhận diện giọng nói → ② dịch Gemini → ③ tạo `input.txt`). Cột giữa: tạo/clone giọng. Có tùy chọn **cắt bản 10–15 phút**, dựng **video ngang** và **video dọc**. |
| `scripts/taogiong.py` | Bản chạy dòng lệnh của quy trình clone giọng. |
| `scripts/taogiong_kiemtra_audio.py` | Rà các đoạn WAV lỗi/spike sau khi tạo audio. |
| `scripts/video_khung.py` | Dựng **video NGANG**: ghép random clip trong `videongang/` rồi lồng vào khung PNG (`Backbround/`). Đầu ra `<audio>_videodone.mp4`. |
| `scripts/video_doc.py` | Dựng **video DỌC 1080×1920 (KHÔNG khung)**: ghép random clip trong `videodoc/`, mux audio. Đầu ra `<audio>_doc.mp4`. |
| `scripts/video_timclip.py` | Gợi ý đoạn clip ngắn từ kịch bản; và **cắt audio bản 10–15 phút** tại khoảng lặng cuối câu (dùng cho video dọc). |
| `scripts/video_xoatieng.py` | Xóa audio gốc + scale video nguồn trong `mp4/` → `mp4_no_audio/`. |
| `scripts/video_ghepcuoi.py` | Ghép video đã tắt tiếng với `kịch_bản/output.wav`. |
| `scripts/doiten_video.py` | Chuẩn hóa khung hình + xóa tiếng + đổi tên tuần tự. **GUI chọn chế độ NGANG** (`videongang/`→1920×1080, tag `_ng_`) **hoặc DỌC** (`videodoc/`→1080×1920, tag `_doc_`); hoặc CLI `--mode ngang|doc`. |
| `scripts/doiten_anh.py` | Chỉ đổi tên ảnh mới/chưa có tên số chuẩn trong `Anh/`; các file như `1.png`, `2.jpg` và `Pink.png` được giữ nguyên. Chạy trực tiếp sẽ đổi tên, thêm `--dry-run` để chỉ xem trước. |
| `scripts/video_bongbong.py` | Tạo/ghép hiệu ứng bong bóng; đọc ảnh trong `Anh/` và xử lý riêng `Pink.png`. Đầu ra mặc định nằm trong `scripts/hieuung/`. |
| `scripts/video_bongbong_gui.py` | Giao diện chọn video, ảnh, tên file xuất và các tham số hiệu ứng để chạy `video_bongbong.py` mà không sửa mã. Đầu ra luôn nằm trong `scripts/hieuung/`. |
| `scripts/video_gansub.py` | Gắn phụ đề vào video. |
| `scripts/nhandien_giongnoi.py` | Nhận diện audio/video tiếng Trung → văn bản (faster-whisper). |
| `scripts/nhandien_gui.py` | Giao diện nhận diện giọng nói tiếng Trung; tự nạp sẵn `kịch_bản/tiengTrung.docx`, có nút gửi Gemini. |
| `scripts/dich_gemini.py` | Lõi gửi nội dung sang Gemini qua Firefox/Selenium (mở trình duyệt, gõ từng đoạn, lấy kết quả). |
| `scripts/dich_docx.py` | Dịch `tiengTrung.docx` qua Gemini → `gemini_result.docx`. |
| `scripts/dich_tachdoan.py` | Tách nội dung DOCX thành các đoạn (~1000–1500 ký tự, cắt ở cuối câu). |
| `scripts/dich_kiemtra.py` | Kiểm tra `gemini_result.docx` (bắt câu dẫn nhập/thừa) trước khi tạo audio. |
| `scripts/dich_chuanbi_input.py` | Kiểm tra + bỏ cấu trúc `gemini_result.docx`, ghép nội dung → `kịch_bản/input.txt` cho TTS. |
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

## File kịch bản chuẩn trong `kịch_bản/`

Toàn bộ pipeline dùng thống nhất 3 file (không còn `noidungGemini.docx` cũ):

| File | Vai trò | Sinh ra bởi |
| --- | --- | --- |
| `tiengTrung.docx` | Văn bản tiếng Trung (中文) — nguồn để dịch | Nhận diện giọng nói (`nhandien_giongnoi`) |
| `gemini_result.docx` | Bản dịch tiếng Việt từ Gemini | Nút "Gửi Gemini" / `dich_docx.py` |
| `input.txt` | Văn bản cuối cho TTS | `dich_chuanbi_input.py` (kiểm tra + ghép) |

## Quy trình cơ bản

```text
audio/video tiếng Trung
  → nhandien_giongnoi (nhận diện)        → kịch_bản/tiengTrung.docx
  → dịch Gemini (dich_docx / nút Gemini) → kịch_bản/gemini_result.docx
  → dich_chuanbi_input (kiểm tra+ghép)   → kịch_bản/input.txt
  → taogiong_gui.py / taogiong.py        → kịch_bản/output.wav (+ output_cut.wav nếu cắt)
  → video_khung.py  (ngang, có khung)    → <audio>_videodone.mp4
  → video_doc.py    (dọc, không khung)   → <audio>_doc.mp4
  → (tùy chọn) video_gansub.py / video_bongbong.py
```

Ba bước đầu (nhận diện → Gemini → input.txt) đã được tích hợp sẵn vào **cột trái** của `taogiong_gui.py`, nên thường chỉ cần mở một giao diện.

## Tạo giọng & video trong `taogiong_gui.py`

Giao diện chia 3 cột: **(1) quy trình tạo kịch bản · (2) điều khiển TTS · (3) nhật ký** (nút Chạy/Tạm dừng/Nghe thử nằm ở đầu cột nhật ký).

Khi bấm **▶ Chạy**, ngoài `output.wav` còn có các tùy chọn ở khung "Cài đặt":

- **✂️ Cắt 10–15 phút** (mặc định bật): cắt thêm `output_cut.wav` từ `output.wav` (chỉ cắt bằng ffmpeg, **không** tạo lại giọng). Chỉnh được số phút Đích/Từ/Đến.
- **🎬 Tự dựng video** (ngang): dựng video có khung từ **audio full**.
- **📱 Video dọc** (mặc định bật): dựng video dọc từ **audio bản cắt**; tick thêm **"dùng audio không cắt"** để video dọc dùng audio full (tiếng giống video ngang).

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
