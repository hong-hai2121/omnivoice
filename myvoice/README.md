# myvoice

Thư mục này chứa các công cụ và dữ liệu tự viết thêm cho quy trình tạo video/lồng tiếng. Phần lõi của OmniVoice nằm ở các thư mục cấp trên; phần việc thực tế hằng ngày nằm chủ yếu trong `myvoice/`.

## Chạy

**Cách dùng chính: bản WEB.** Bấm đúp `myvoice\chay.bat` — server bật và trình
duyệt tự mở bảng điều khiển (xem `web/README.md`). GUI Tkinter cũ vẫn giữ nguyên,
mở bằng `myvoice\chay_gui.bat` khi cần.

Trong VS Code thì mở `myvoice/chay.py` bấm ▶ Run (hoặc F5 → “▶ myvoice — bảng
điều khiển WEB”); nút ▶ của VS Code không chạy được file .bat.

## Dịch qua Chrome Extension (Gemini) — mặc định; Firefox/Selenium là dự phòng

Từ 01/10/2026 bước dịch, dịch lại đoạn trống và SEO dùng **hồ sơ Chrome nào đã cài
extension `chrome_gemini_extension`** và đăng nhập Gemini — không cần Selenium hay
geckodriver. Ở khối **Dịch qua Gemini** hoặc **Nhận diện → Chạy cho những tập đã
tick** có hai ô loại trừ nhau: **Dịch bằng Chrome Extension (mặc định)** và **Dịch
bằng Firefox / Selenium (dự phòng)** — cách cũ giữ nguyên, chỉ bật khi muốn. Lựa
chọn lưu chung cho web và GUI Tkinter; việc đã xếp hàng trên web giữ lựa chọn tại
lúc xếp.

**Dự phòng tự động:** chọn extension mà extension không kết nối được (Chrome đóng,
chưa bấm Kết nối, chưa đăng nhập Gemini, cổng bận vì phiên khác…) thì nhật ký ghi
`⚠️ Chrome Extension không sẵn sàng…` rồi `🦊 DỰ PHÒNG: mở Firefox` và việc chạy tiếp
bằng Firefox như trước (cần Firefox đang đóng, profile đã đăng nhập). Chờ Chrome hỏi
lệnh tối đa 40 s trước khi dự phòng. Tắt bằng `OMNI_GEMINI_EXTENSION_FALLBACK=0`
(khi đó việc dừng và báo lỗi). Việc đang chạy Firefox không nhảy sang extension
giữa chừng, và ngược lại extension mất kết nối giữa chừng thì dừng, giữ tiến độ
(đoạn chưa xác nhận không tự gửi lại) — ⏩ chạy tiếp sau khi kiểm tra tab.

1. Mở `chrome://extensions`, bật **Developer mode** → **Load unpacked**.
2. Chọn thư mục [`chrome_gemini_extension`](../chrome_gemini_extension) ở gốc dự án (cùng cấp với `myvoice`).
3. Extension tự bật với **mã kết nối mặc định** `omnivoice-gemini-local` (máy chỉ chạy
   nội bộ, bridge chỉ nghe 127.0.0.1 nên không cần đổi). Muốn mã riêng: ghi vào
   `myvoice/.gemini_extension_token` hoặc đặt `OMNI_GEMINI_EXTENSION_TOKEN`, rồi dán
   cùng mã vào popup extension → **Lưu và kết nối**.
4. Đăng nhập Gemini trên hồ sơ Chrome đó. Vào tab **🧩 Extension** trên web
   (`/gemini-extension`) bấm **🔌 Kiểm tra kết nối**, rồi **🧪 Gửi thử** một đoạn
   tiếng Trung ngắn — nhật ký và kết quả hiện ngay trên trang (ép dùng extension,
   không dự phòng Firefox, không ghi file). Xong thì bấm Dịch ở Home như trước.

Giữ Chrome và tab Gemini mở; có thể đóng popup extension. Extension tự mở một
tab riêng cho phiên dịch, không yêu cầu đóng Chrome hoặc cài ChromeDriver. Trước
khi bấm Dịch, trạng thái “Đang chờ ứng dụng” là bình thường (extension thăm dò
chậm dần tới 5 s/lần khi ứng dụng chưa chạy). Chỉ cài extension trên MỘT hồ sơ
Chrome và chỉ chạy một phiên dịch extension tại một thời điểm — phiên thứ hai sẽ
dự phòng Firefox. Khi cập nhật mã extension, bấm **Reload** ở `chrome://extensions`,
rồi chạy công việc mới.

Extension chỉ thay phần điều khiển trình duyệt. Câu hướng dẫn, chia đoạn, lưu
DOCX từng đoạn, tiếp tục bản dịch dở, tô đỏ/kiểm tra và retry vẫn dùng lõi Python
cũ. Tab được giữ lại để đối chiếu khi xong. Bridge chỉ nghe `127.0.0.1:17863`, mã kết
nối mặc định cố định (xem trên; file `.gemini_extension_token` chỉ là tuỳ chọn ghi đè,
không đưa vào Git). Không cần API key Gemini.

Kiểm tra phần cầu nối và lưu DOCX: `venv\Scripts\python.exe -m unittest discover -s myvoice/tests -v`.
Kiểm tra extension đã cài trong Chromium với trang Gemini giả lập (dùng Playwright
sẵn ở `Desktop Automation/gptcode`):
`node --test "Desktop Automation/gptcode/tests/gemini-extension.test.mjs"`.

## Chạy script lẻ

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
| `scripts/amain_taogiong_gui.py` | **Kho logic dùng chung; chạy thẳng file này là mở bản WEB (từ 05/09/2026). GUI Tkinter cũ vẫn mở được bằng `--gui` hoặc `chay_gui.bat`.** Cột trái: quy trình tạo kịch bản (① nhận diện giọng nói → ② dịch Gemini → ③ tạo `input.txt`). Cột giữa: tạo/clone giọng. Có tùy chọn **cắt bản 10–15 phút**, dựng **video ngang** và **video dọc**. |
| `scripts/taogiong.py` | Bản chạy dòng lệnh của quy trình clone giọng. |
| `scripts/taogiong_kiemtra_audio.py` | Rà các đoạn WAV lỗi/spike sau khi tạo audio. |
| `scripts/video_khung.py` | Dựng **video NGANG**: ghép random clip trong `videongang/` rồi lồng vào khung PNG (`Backbround/`): nền `Khung0*.png` + viền `khung1*.png` đều chọn NGẪU NHIÊN mỗi lần dựng. Đầu ra `<audio>_videodone.mp4`. **🎞 `source_video=`** (24/10/2026, ô “Lấy video tải xuống làm video nguồn” bên GUI/web): dùng MỘT video — video tải xuống của tập — thay kho clip: tắt tiếng gốc (không map audio), phóng to `source_zoom` (mặc định 120 %) rồi cắt giữa, kéo/nén thời lượng khớp audio (kẹp 0,5–2×, lệch hơn thì lặp/cắt). |
| `scripts/video_khung0_tao.py` | Vẽ thêm các kiểu **nền Khung0** cho video ngang (mèo, tông hồng; 08/09/2026) bằng PIL: `Backbround/Khung0 <tên>.png` (chấm bi, ca rô, dâu tây, hoa anh đào, kẹo sọc) CÙNG BỐ CỤC với `Khung0.png` gốc — 5 cụm trang trí đúng chỗ bản gốc, vùng logo/Subscribe để trơn vì nền ghép với khung1/logo/khung2. `--force` vẽ lại, `--xem` xuất ảnh ghép thử vào `Backbround/khung0_xemtruoc/`. Thêm kiểu = thêm hàm vào `KIEU`. |
| `scripts/video_doc.py` | Dựng **video DỌC 1080×1920 (KHÔNG khung)**: ghép random clip trong `videodoc/`, mux audio. Đầu ra `<audio>_doc.mp4`. (Đường cũ — chỉ chạy khi tắt ô 🖼 `doc_khung`.) |
| `scripts/video_doc_khung.py` | **Video DỌC từ VIDEO GỐC của bản ngang** (08/09/2026, mặc định): `video_khung.build_video(goc_out=)` xuất thêm `YOUTUBE_goc.mp4` (đoạn video đã ghép, trước khi lồng khung) → đặt vào dải giữa khung dọc tạo sẵn `Backbround/khungdoc/khungdoc <màu>.png` (nền hoa + khung "anhdoc" xoay ngang + logo + thẻ Số + tiêu đề trên giấy + ảnh mèo + "Nghe trọn tập tại kênh Mimi audio" + nút Đăng ký), một lệnh ffmpeg, không ghép clip dọc. Màu theo viền khung ngang. Tập cũ không có file gốc thì cắt vùng trong của `YOUTUBE.mp4`. `--tao-khung --force` vẽ lại bộ khung; web xem trước ở khối 7 trang Giọng nói. |
| `scripts/video_timclip.py` | Gợi ý đoạn clip ngắn từ kịch bản; cung cấp hàm cắt audio tại khoảng lặng cuối câu (dùng cho bước cắt % của video dọc/TikTok). |
| `scripts/video_xoatieng.py` | **GUI (mặc định)**: chọn nhiều video (mặc định mở ở Downloads) → xóa tiếng + **cắt đầy khung** về khung hình đồng nhất (Ngang 1920×1080 / Dọc 1080×1920), tùy chọn **cắt bỏ số giây đầu/cuối** mỗi video → lưu vào thư mục đầu ra tùy chọn (mặc định `videongang/`) với tên tuần tự `<tiền tố><số>.mp4` (vd `nauan01.mp4`), tự nối tiếp số đang có, **giữ nguyên file gốc**. Cờ `--batch`: luồng cũ `mp4/` → `mp4_no_audio/` cho `video_ghepcuoi.py`. |
| `scripts/video_ghepcuoi.py` | Ghép video đã tắt tiếng với `kịch_bản/output.wav`. |
| `scripts/doiten_video.py` | Chuẩn hóa khung hình + xóa tiếng + đổi tên tuần tự. **GUI chọn chế độ NGANG** (`videongang/`→1920×1080, tag `_ng_`) **hoặc DỌC** (`videodoc/`→1080×1920, tag `_doc_`); hoặc CLI `--mode ngang|doc`. |
| `scripts/doiten_anh.py` | Chỉ đổi tên ảnh mới/chưa có tên số chuẩn trong `Anh/`; các file như `1.png`, `2.jpg` và `Pink.png` được giữ nguyên. Chạy trực tiếp sẽ đổi tên, thêm `--dry-run` để chỉ xem trước. |
| `scripts/video_bongbong.py` | Tạo/ghép hiệu ứng bong bóng; đọc ảnh trong `Anh/` và xử lý riêng `Pink.png`. Đầu ra mặc định nằm trong `scripts/hieuung/`. |
| `scripts/video_bongbong_gui.py` | Giao diện chọn video, ảnh, tên file xuất và các tham số hiệu ứng để chạy `video_bongbong.py` mà không sửa mã. Đầu ra luôn nằm trong `scripts/hieuung/`. |
| `scripts/video_gansub.py` | Gắn phụ đề vào video. |
| `scripts/nhandien_giongnoi.py` | Nhận diện audio/video tiếng Trung → văn bản (faster-whisper). |
| `scripts/nhandien_gui.py` | Giao diện nhận diện giọng nói tiếng Trung; tự nạp sẵn `kịch_bản/tiengTrung.docx`, có nút gửi Gemini. |
| `scripts/dich_gemini.py` | Lõi gửi nội dung sang Gemini qua Firefox/Selenium (mở trình duyệt, gõ từng đoạn, lấy kết quả). Mỗi đoạn gửi một lần; gửi hết tập, đoạn vừa `(trống)` được gửi lại một lần trong **chat mới** với đề bài ngắn (`retry_blanks_in_new_chat`, tắt bằng `OMNI_GEMINI_BLANK_RETRY=0`) — dịch được thì TÔ ĐỎ để kiểm (nhãn "n đỏ" cột Dịch trang Nhận diện). Tập còn đoạn `(trống)` **hoặc** đoạn đỏ chưa ✔ kiểm thì DỪNG sau bước dịch (`blocking_chunks`): không tạo input / SEO / giọng / video / đăng cho tới khi lấp trống và bỏ đỏ rồi ⏩ chạy tiếp. Câu dẫn nhập Gemini hay chèn ("Bản dịch tiếng Việt mạch truyện:", "Dưới đây là bản dịch…:") được bỏ ngay khi nhận trả lời (`strip_lead_lines` trong `send_to_gemini`) và khi ghi docx (`save_results_docx`), nên `gemini_result.docx` sạch từ lúc lưu. |
| `scripts/dich_docx.py` | Dịch `tiengTrung.docx` qua Gemini → `gemini_result.docx`. |
| `scripts/dich_tachdoan.py` | Tách nội dung DOCX thành các đoạn (~1000–1500 ký tự, cắt ở cuối câu). |
| `scripts/dich_kiemtra.py` | Kiểm tra `gemini_result.docx` (bắt câu dẫn nhập/thừa) trước khi tạo audio. |
| `scripts/dich_lai_trong.py` | Lấp các đoạn còn `(trống)` trong `gemini_result.docx` của từng tập: mỗi đoạn gửi Gemini đúng một lần với đề bài ngắn `BLANK_RETRY_PROMPT` ("Dịch đi thẳng vào nội dung. Không giải thích thêm:" + nội dung, không câu hướng dẫn dài, không thẻ hư cấu — từ 15/09/2026), ghi thẳng vào đúng đoạn trống để kiểm (không sao lưu bản cũ nữa; trả lời còn nguyên tiếng Trung thì giữ "(trống)") (`--episode 98`, `--all`, `--dry-run`). Nút 🔁 trên trang Nhận diện gọi file này. |
| `scripts/dich_chuanbi_input.py` | Kiểm tra + bỏ cấu trúc `gemini_result.docx`, ghép nội dung → `kịch_bản/input.docx` cho TTS (Word; đoạn dịch nhờ câu nhắc được tô đỏ). Tự bỏ câu dẫn nhập Gemini hay chèn ("Bản dịch tiếng Việt mạch truyện:", "Dưới đây là bản dịch…:", kể cả khi dính giữa dòng) — `remove_lead_lines`, dùng chung cho mọi đường tạo input; gặp mẫu mới thì thêm vào `_LEAD_STARTS` / `_LEAD_INLINE_RE`. |
| `scripts/dich_input_docx.py` | Đọc/ghi/tìm file kịch bản TTS `input.docx` (từ 05/09/2026; đọc được cả `input.txt` cũ), tô đỏ đoạn dịch nhờ câu nhắc. Mọi script đều đi qua đây. |
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
| `input.docx` | Văn bản cuối cho TTS (Word, giữ tô đỏ; tập cũ còn `input.txt` vẫn đọc được) | `dich_chuanbi_input.py` (kiểm tra + ghép) |

## Quy trình cơ bản

```text
audio/video tiếng Trung
  → nhandien_giongnoi (nhận diện)        → kịch_bản/tiengTrung.docx
  → dịch Gemini (dich_docx / nút Gemini) → kịch_bản/gemini_result.docx
  → dich_chuanbi_input (kiểm tra+ghép)   → kịch_bản/input.docx
  → taogiong_gui.py / taogiong.py        → kịch_bản/output.wav
  → video_khung.py  (ngang, có khung)    → <audio>_videodone.mp4  (+ YOUTUBE_goc.mp4: video gốc trước khi lồng khung)
  → video_doc_khung.py (dọc = video gốc + khung dọc tạo sẵn, mặc định) → facebook.mp4
  → video_doc.py    (dọc, không khung — đường cũ khi tắt 🖼 doc_khung)   → <audio>_doc.mp4
  → (tùy chọn) video_gansub.py / video_bongbong.py
```

Ba bước đầu (nhận diện → Gemini → input.docx) đã được tích hợp sẵn vào **cột trái** của `taogiong_gui.py`, nên thường chỉ cần mở một giao diện.

## Tạo giọng & video trong `taogiong_gui.py`

Giao diện chia 3 cột: **(1) quy trình tạo kịch bản · (2) điều khiển TTS · (3) nhật ký** (nút Chạy/Tạm dừng/Nghe thử nằm ở đầu cột nhật ký).

Khi bấm **▶ Chạy**, ngoài `output.wav` còn có các tùy chọn ở khung "Cài đặt":

- **🎵 Tông giọng** (bán cung, mặc định **+2** từ 20/10/2026; cùng ô bên web, khoá `pitch` trong `taogiong_options.json`): áp lên `output.wav` ngay sau khi ghép đoạn, trước chuẩn độ to, bằng ffmpeg `rubberband` (giữ tốc độ, giữ âm sắc người đọc; ffmpeg không có rubberband thì `asetrate`+`atempo`). Vì đổi ở audio gốc nên video ngang/dọc/TikTok, bản tăng tốc, trộn nhạc đều theo. Chỉ áp lúc **tạo** giọng: ♻ dùng lại audio thì giữ tông cũ (mức đã áp ghi ở `_pitch.txt` trong thư mục chunk; khác mức đang chọn thì nhật ký báo, bỏ tick ♻ để tạo lại). Nghe thử trước bằng `voice/thu_giong.py` (thanh 🎵 mở lên đúng mức này; kéo về 0 để nghe giọng gốc).
- **🔔 Tiếng vang / 🧒 Giọng thiếu niên** (từ 20/10/2026, bộ lọc giọng kiểu CapCut; khoá `vang_truong_do`, `vang_cuong_do`, `thieu_nien` trong `taogiong_options.json`, thang **0–100**, 0 = tắt; cùng ô bên GUI và web; lõi ở `scripts/hieuung_giong.py`): áp lên `output.wav` **cùng lúc với tông giọng**, trong một lần ffmpeg, nên video nào cũng theo và ♻ dùng lại audio thì giữ bộ lọc cũ (mức đã áp ghi ở `_hieuung.json` trong thư mục chunk). **Tiếng vang**: *trường độ* = độ dài đuôi vang (0 ≈ 0,25 s phòng nhỏ → 100 ≈ 3 s hội trường; 80 ≈ 1,8 s), *cường độ* = mức vang trộn vào (bật khi > 0) — làm bằng filter `afir` tích chập với đáp ứng xung tự sinh bằng numpy (tiền trễ + phản xạ sớm + đuôi nhiễu tắt dần, dải cao tắt nhanh hơn), không phải `aecho` (chỉ ra vài tiếng dội rời); `afir` không có đường trộn dry/wet riêng nên xung trực tiếp nằm ngay trong đáp ứng xung (dry/wet luôn khớp pha), sau đó `alimiter` ghìm đỉnh < 0,97 (có bù trễ) vì cộng vang vào giọng đã chuẩn độ to thì đỉnh vượt 1,0. **Thiếu niên**: giọng trẻ hơn = dời formant lên (100 → ×1,18) + nhỉnh cao độ (100 → +4 bán cung), làm bằng một lần `rubberband` (giữ formant) rồi `asetrate`+`atempo` để formant dời theo tỉ lệ khác cao độ; muốn đổi mức tối đa thì sửa `TN_FORMANT_MAX` / `TN_PITCH_MAX_ST`, còn độ vang sửa `VANG_*` đầu file. Nghe thử bằng `voice/thu_giong.py` (hai thanh 🔔 🧒 mở lên đúng mức bài thật; kéo về 0 để tắt). Thử lẻ một file: `venv\Scripts\python myvoice\scripts\hieuung_giong.py in.wav --vang 80 76 --thieunien 100 --sang 60`.
- **🔆 Sáng giọng** (từ 23/10/2026; khoá `sang_giong`, 0–100, 0 = tắt, **mặc định 80**; cùng ô GUI/web/app Thử giọng; myvideo dùng chung lõi — xem cuối mục): trị giọng clone nghe "ồm ồm, không thanh". Đo trên giọng mẫu *ngọc huyền 01*: ~80 % năng lượng dồn vào 150–600 Hz, dải 2,5–5 kHz chỉ ~1 %, bản clone chép y nguyên (trọng tâm phổ ~500 Hz) nên đổi tông/tốc độ không sửa được. Bộ lọc là chuỗi EQ ffmpeg (mức 100 = highpass 110 Hz, cắt 230 Hz −6 dB, cắt 480 Hz −3 dB, nâng 3,2 kHz +6 dB, highshelf 6 kHz +6 dB; từ mức 50 thêm `aexciter` sinh họa âm 7–11,5 kHz bù phần model chỉ ra 24 kHz; mức nhỏ hơn nội suy; đo mức ~65 đưa trọng tâm phổ 507 → 863 Hz, mức 100 → 1172 Hz; sửa `SANG_*` đầu `hieuung_giong.py`), áp ở **hai chỗ**: lên `output.wav` cùng lúc với tông như hai bộ lọc trên, **và lên giọng mẫu trong bộ nhớ lúc dựng prompt clone** (`_voice_prompt` → `_eq_giong_mau`, không exciter; file mẫu không đổi, prompt lưu riêng `<mẫu>.sang<N>.prompt.pt`) — model nghe mẫu sáng thì phát âm sáng từ gốc, EQ output chỉ đánh bóng. Vì prompt đổi nên mức này vào chữ ký `_signature.txt`: đổi mức là sinh lại hết các đoạn (mức 0 giữ chữ ký cũ, tập đã tạo không bị sinh lại). Cùng ngày thêm `highpass=f=80` đứng trước bộ nén trong `SPEECH_COMPRESSOR`: dưới f0 giọng nam nên không đổi âm sắc, chỉ để tiếng ù dưới 80 Hz không kích bộ nén. App Thử giọng: thanh 🔆 áp EQ lên bản phát ngay, còn bấm Tạo thì EQ cả giọng mẫu và lưu bản thử thành `<giọng>_sang<N>.wav`. **myvideo** dùng chung lõi (`hieuung_giong.eq_giong_mau_tam` + `apply_fx_file`) nhưng cài đặt riêng: khoá `sanggiong` (mặc định 80) trong `myvideo/web/web_settings.json`, thanh kéo ở **khối ③ trang chính** (lưu cùng form chính; ô 🔊 Nghe thử ở đó phát bản mẫu đã EQ theo mức qua `/nghe/giong?sang=`, cache ở `myvideo/voice/_nghe_thu/`), bước ③ truyền `--sang` cho `taogiong_srt.py`; bên đó EQ giọng mẫu lúc dựng prompt (`<giọng>.sang<N>.prompt.pt`) rồi EQ **audio tổng** `_vi_audio.wav` sau khi trộn (từng câu không EQ riêng), mức đã dùng ghi vào `_vanban.json` nên đổi mức là bước ③ đọc lại toàn bộ câu. Từ 24/10/2026 myvideo cũng **dùng chung kho giọng** này: ô chọn giọng bước ③ liệt kê `myvoice/voice` trước (cộng file chỉ có trong kho cũ `myvideo/voice`; trùng tên thì myvoice thắng), `taogiong_srt.py` tìm giọng theo cùng thứ tự, nên `.prompt.pt` / `.sang<N>.prompt.pt` đã dựng bên này bên kia dùng lại luôn; cài đặt (giọng đang chọn, ⭐) vẫn riêng từng bảng. Cùng ngày **gộp code trùng**: `taogiong_srt.py` không còn chép lại nạp model / trả VRAM / dựng prompt / đọc câu mà import thẳng `load_omnivoice`, `_tra_vram`, `_do_omnivoice`, `_voice_prompt`, `_generate_chunk` của `amain_taogiong_gui` (app Thử giọng và `run_tts` cũng nạp model qua `load_omnivoice`); và **mang nốt chức năng myvoice sang myvideo**: cân mức giữa các câu (`_balance_chunk_levels` trong `mix_audio`), nén nhẹ + chuẩn −14 LUFS (`_loudnorm_file` + `SPEECH_COMPRESSOR`) trên `_vi_audio.wav`, tông giọng 🎵 + tiếng vang 🔔 + thiếu niên 🧒 (khoá `pitch`, `vang_truong_do`, `vang_cuong_do`, `thieu_nien` trong `web_settings.json`, ô ở khối ③, mặc định 0) áp cùng lúc với 🔆 trước khi chuẩn độ to — đúng thứ tự `run_tts`.
- **🎬 Tự dựng video** (ngang): dựng video có khung từ **audio full**.
- **📱 Video dọc** (mặc định bật): dựng video dọc từ **audio full** (muốn ngắn hơn thì đặt **%** audio, cắt ở cuối câu). Nguồn hình video dọc (Facebook) chọn theo thứ tự ưu tiên:
  - **📁 Ghép từ thư mục con videodoc** (theo `videodoc/input.txt`): ghi TÊN 1 thư mục con của `videodoc/` vào file `videodoc/input.txt` → ghép random clip trong thư mục chủ đề đó. Sửa file = đổi nguồn cho tương lai (không cần đụng code). File rỗng/không hợp lệ → tự dùng cả kho `videodoc/`.
  - **♻ Dùng lại video ngang** (YouTube.mp4) đã dựng, phóng to khớp chiều cao dọc + cắt giữa.
  - Không tick gì → ghép random cả kho `videodoc/`. Mọi trường hợp đều áp **audio của video dọc/Facebook**.

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
