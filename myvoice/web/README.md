# Bảng điều khiển web

Đây là **cách dùng chính** của myvoice. GUI Tkinter vẫn còn nguyên trong
`scripts/amain_taogiong_gui.py` (không xoá, vẫn mở được bằng `chay_gui.bat`) nhưng
việc hằng ngày làm hết trên web. Bản web không sửa gì trong `scripts/` — nó gọi
thẳng các hàm logic của GUI.

Chỉ dùng **ngay trên máy này** — không có chế độ mở qua mạng LAN/điện thoại.

## Chạy

```
myvoice\chay.bat          ← bật server + TỰ MỞ trình duyệt
myvoice\chay_gui.bat      ← chỉ khi cần GUI Tkinter cũ
```

Trong **VS Code** (nút ▶ không chạy được file .bat): mở `myvoice/chay.py` rồi bấm
▶ Run, hoặc bấm **F5** và chọn “▶ myvoice — bảng điều khiển WEB”
(`.vscode/launch.json`). `chay.py` tự chạy lại bằng python của venv nếu interpreter
đang chọn là cái khác, nên bấm ▶ ở bất kỳ đâu cũng ra đúng môi trường.
Thêm cờ `--gui` để mở GUI cũ.

Đóng cửa sổ console là tắt server. Server tự mở trình duyệt khi khởi động; không
muốn thì đặt `MYVOICE_WEB_NO_OPEN=1` (nút **🌐 Bảng web** của GUI đặt sẵn cờ này
vì nó tự mở lấy).

Cửa sổ console in ra đường dẫn kèm `?token=…`; token được nhớ trong cookie 30 ngày.
Token giữ lại để trang web lạ đang mở trong cùng trình duyệt không gọi vào được.

Server **chỉ nghe trên 127.0.0.1**, không có tuỳ chọn mở ra LAN: nó chạy ffmpeg,
dùng GPU, mở Firefox và xoá file ngay trên máy bạn.

| Muốn gì | Làm sao |
|---|---|
| Đổi cổng (mặc định 8765) | đặt `MYVOICE_WEB_PORT` |
| Không tự mở trình duyệt | đặt `MYVOICE_WEB_NO_OPEN=1` |
| Đổi token | xoá `web/token.txt` rồi chạy lại |

## Sáu trang — menu trái, xếp theo thứ tự làm việc

| Trang | Tab tương ứng bên GUI | Có gì |
|---|---|---|
| **🏠 Home** (trang chủ `/`) | 🏠 Home (đầy đủ) | **Mọi nút chức năng**: hàng đợi · ① kịch bản ①②③ · ② hàng loạt theo tập (bảng tập + ②③④⑤) · ③ giọng nói & video · ④ thumbnail |
| **🛠 Tạo kịch bản** (`/kichban`) | Tạo kịch bản | Ba bước ①②③ với các ô ⛓ nối bước, hàng đợi, tập bỏ qua, câu mở đầu Gemini, reset quy trình |
| **🎙 Nhận diện** | Nhận diện | ① nhận diện link → bảng tập tick chọn → các nút hàng loạt ②③④⑤ |
| **🎧 Giọng nói** | Giọng nói (TTS + video) | Chế độ clone/thiết kế/mặc định, giọng mẫu + ★ + nghe thử, tệp vào/ra, cài đặt chung, video ngang · phụ đề · dọc · TikTok, ba nút “Dựng lại”, xoá output |
| **🖼 Thumbnail** | Thumbnail | Tiêu đề (gợi ý sẵn từ SEO), ảnh nền, số tập, xem trước bản ngang + dọc |
| **📑 Copy SEO** | Copy SEO | Tiêu đề · tiêu đề TikTok · mô tả · thẻ tag, đúng nội dung 3 nút Copy bên GUI |

Làm việc hằng ngày chỉ cần trang **Home** — các trang còn lại là chỗ xem kỹ từng
phần và vài tuỳ chọn ít dùng (tập bỏ qua, câu mở đầu Gemini, reset quy trình, xóa
output, xem trước thumbnail, copy SEO).

Ở Home, mỗi khối tự dàn thành nhiều cột bằng **CSS columns** (`body.p-home
.form-grid`) — grid xếp theo hàng nên khối cao thấp lệch nhau để lại lỗ hổng, còn
columns thì rót khối sau vào ngay chỗ trống. Riêng khối hàng loạt dùng
`.batch-grid`: cột hẹp (nhập link · nút chạy) | cột rộng (bảng tập 10 cột).
Các trang riêng vẫn xếp **dọc một cột theo đúng thứ tự bấm**, căn giữa màn hình.

Giao diện: menu trái tím gradient (giữ nguyên mọi trang) + mỗi trang một tông màu
riêng để nhìn là biết đang ở đâu — Home chàm · kịch bản tím · nhận diện xanh dương · giọng nói
hồng · thumbnail cam · SEO xanh ngọc. Tông màu khai báo ở đầu `static/app.css`
(`body.p-<tên trang>` đặt `--accent`/`--accent2`/`--accent-soft`), đổi một dòng là
đổi cả trang; sáng/tối tự theo cài đặt Windows.

**Nhật ký nằm ở cửa sổ console của server**, không còn panel dưới trang web:
mọi dòng của tiến trình con in thẳng ra đó.

**Nút 💾 lưu tại chỗ, không tải lại trang** — mọi nút "💾 Lưu…" (và hai form
Tập bỏ qua / Câu mở đầu) gửi qua htmx: lưu xong hiện mẩu "✓ đã lưu" cạnh nút
rồi tự mờ đi, chỗ đang cuộn và các ô đang gõ dở giữ nguyên. Trình duyệt tắt JS
thì rơi về kiểu chuyển hướng như cũ (route `/…/luu` trả redirect khi không có
header `HX-Request`).

**Trên Home, bấm BẤT KỲ nút chạy nào là lưu HẾT các khối cài đặt** — Home ghép
4 form riêng mà trình duyệt chỉ gửi form chứa nút vừa bấm, nên sửa "Tăng tốc"
bên khối Giọng nói rồi bấm 🎙 Nhận diện là giá trị mới không được ghi ra file
(chuỗi tự chạy vẫn dựng video theo tốc độ cũ). Vì vậy app.js chặn submit của cả
4 form (quy trình · giọng nói & video · thumbnail · đăng), gửi dữ liệu 3 form
còn lại vào đúng route `/…/luu` của từng khối trước (khối đang gửi tự lưu trong
handler của nó), xong mới submit thật (`requestSubmit` giữ nguyên nút vừa bấm).
Nút 💾 htmx không qua đường này (htmx tự gửi, không có sự kiện submit) — mỗi nút
💾 vẫn chỉ lưu đúng khối của nó như nhãn ghi. Trang riêng chỉ có một form nên
không bị chặn gì. CỐ Ý không lưu (mỗi lần mở trang là trống/mặc định): ô Nguồn
(chỉ giữ chip "Gần đây"), "Số tập bắt đầu", hai ô mỗi-lần-chạy "Làm lại cả bước
đã có kết quả" và "♻ Dùng lại audio/video đã có", tiêu đề thumbnail (nội dung
của từng tập), và "Số tập (chữ trên video)" (tự suy từ bộ đếm thumbnail + 1).

**📘 Đăng Facebook** — khối cuối trang Home (dưới Đăng YouTube): **bảng các tập
chưa đăng Page** kèm **giờ lên lịch dự kiến** và **tiêu đề đúng như bài sẽ đăng**,
xem được TRƯỚC khi bấm chạy; ba nút — 📘 đăng các tập chưa đăng · 🔍 xem kế hoạch
(dry-run) · 🔄 đối chiếu Page. Tick vài tập thì chỉ làm những tập đó, không tick ô
nào = làm tất cả. Lịch xếp **9h/19h hằng ngày**, nối tiếp bài mới nhất trên Page.

Giờ dự kiến tính bằng **đúng hàm** mà lúc chạy thật sẽ dùng (`plan_slots` của
script, mốc suy từ sổ qua `known_anchor`) — bảng nói một đằng Facebook nhận một
nẻo là kiểu sai khó chịu nhất, nên hai bên không được có hai phép tính. Lúc bấm
chạy script vẫn hỏi Page một lần rồi chốt theo mốc muộn hơn.

Tiêu đề bài đăng do **`compose_facebook_title`** (trong `YOUTUBE/thumbnail_gui.py`,
cạnh `compose_youtube_title` / `compose_tiktok_title`) dựng: lấy **tiêu đề
YouTube** rồi ghép **bộ hashtag của mô tả** vào cùng MỘT DÒNG. Lý do gộp: bảng tin
Facebook cắt bớt bằng “Xem thêm”, hashtag nằm dưới mô tả dài coi như không ai
thấy. Hashtag lấy từ mô tả SEO chứ không bịa thêm (`hashtags_in` bỏ trùng, bỏ dấu
câu dính đuôi), nên muốn đổi bộ hashtag thì sửa ở SEO như mọi kênh khác.

Cả ba nút chạy `myvoice/FACEBOOK/dang_video_facebook.py` trong **hàng đợi đăng**
nên kế hoạch/tiến trình hiện ở nhật ký hàng đợi đăng, trang không tải lại. Hai
việc 🔍/🔄 xếp hàng dạng **light** (xem `JobRunner.heavy_busy`) nên KHÔNG kích
hoạt 🌙/⏻ — bấm xem kế hoạch xong máy không tự ngủ sau 3 phút.

Trang không gọi Graph API lúc render (chậm theo đường truyền): danh sách tập đã
có trên Page đọc từ `FACEBOOK/page_cache.json` mà script ghi ra mỗi lần chạy —
bấm 🔄 để cập nhật. Cache giữ **tập hợp** số tập chứ không chỉ số lớn nhất, nên
kênh có lỗ (52 đã lên mà 49 chưa) vẫn phát hiện được. Token Page nằm ở `.env`
gốc repo (`FB_PAGE_ID_MIMIAUDIO` / `FB_PAGE_ACCESS_TOKEN_MIMIAUDIO`).

**Hai chốt an toàn của script, đừng gỡ khi sửa sau này:**

*Mã lỗi phải NGƯNG HẲN, tuyệt đối không thử lại* — `4` (hạn mức app), `17` (hạn
mức người dùng), `32` (hạn mức Page), `613` (gọi quá dày), `190` (token hỏng).
Xem `FATAL_CODES` trong `dang_video_facebook.py`: gặp mã này thì bỏ luôn vòng
thử lại 3 lần của bước tải khúc video, ngưng cả lượt chạy và thoát mã **2**
(khác mã 1 của lỗi thường) — thử lại chỉ kéo dài thời gian bị Facebook chặn,
còn token hỏng thì lần nào cũng hỏng như nhau.

*“Đã đăng chưa” tra SỔ LOCAL, Page chỉ hỏi mốc thời gian* — `FACEBOOK/da_dang.json`
là nguồn sự thật cho câu hỏi tập nào đã lên Page: script ghi vào đó ngay khi
Facebook nhận video (và ghi thêm biên nhận `facebook_upload.json` trong thư mục
tập). Việc thường ngày vì thế chỉ hỏi Page **đúng một việc** — bài lên lịch/đăng
mới nhất, để biết xếp tiếp từ đâu (`latest_time`). Số request đo thật:

| Thao tác | Request |
|---|---|
| Trang web dựng bảng tập chưa đăng | **0** (đọc file) |
| 🔍 xem kế hoạch · 📘 đăng (phần lên kế hoạch) | **1–2** |
| 🔄 đối chiếu Page (chỉ khi cần) | ~3 |
| mỗi tập đăng thật | 1 mở phiên + số khúc do FB chia + 1 kết thúc |

Nút 🔄 (`--sync`) quét Page rồi cập nhật sổ — chỉ cần khi có bài đăng tay ngoài
script hoặc mất sổ. Lần quét đó dùng **quét gia tăng**: `/posts` và `/videos` trả
bài mới nhất trước nên chỉ đọc tới bài đã thấy lần trước (mốc `newest` trong
`page_cache.json`) rồi dừng — đo thử Page 1200 bài: lần đầu 25 request, các lần
sau 3. `/scheduled_posts` đọc hết vì nó chỉ chứa bài CHỜ lịch (ít, đăng rồi là
rời danh sách).

*Chạm 75% hạn mức là TỰ NGƯNG, không đợi Meta chặn* — mọi response của Graph API
kèm header `X-App-Usage` / `X-Page-Usage` / `X-Business-Use-Case-Usage`, mỗi cái
có `call_count` · `total_cputime` · `total_time` tính theo %. `_resp()` đọc header
TRƯỚC khi xử lý thân response, lấy chỉ số cao nhất; chạm `USAGE_LIMIT_PCT` (75)
thì ném `UsageStop` — lớp này kế thừa `FbError` với `fatal=True` nên đi chung mọi
nhánh "không thử lại" đã có. Mốc được chạy lại ghi ra `FACEBOOK/cooldown.json`
(theo `estimated_time_to_regain_access` nếu Meta nói rõ, không thì hết giờ hiện
tại) vì **mỗi lần bấm nút trên web là một tiến trình mới** — không ghi ra đĩa thì
bấm lại vài lần là vẫn nã đủ request cho tới lúc bị chặn thật. Khối trên trang
hiện dòng "⏸ Đang tạm ngưng tới HH:MM" trong lúc đó. Gặp mã chặn thật
(4/17/32/613) cũng ghi mốc y hệt.

*Đọc Page thiếu thì KHÔNG xếp lịch* — `page_state` trả thêm cờ `complete`; nguồn
nào lỗi (kể cả lỗi tạm thời) hoặc còn trang chưa đọc là hạ cờ, và khi cờ hạ thì
script từ chối đăng đồng thời **không ghi đè** `page_cache.json`. Lý do: đọc
thiếu nghĩa là có tập đã đăng mà mình không thấy → xếp tiếp là đăng trùng lên
Page, mà cache thiếu còn khiến bảng trên trang hiện tập đã đăng thành "chưa đăng".

**🌙 Xong hết thì cho máy ngủ** — ô tick ngay đầu khối *Hàng đợi*, **mặc định
BẬT sẵn mỗi lần mở server** (an toàn vì phải từng thấy hàng đợi bận rồi mới đếm
ngủ — tick suông lúc chưa chạy gì thì không úp máy). Chạy xong CẢ
hàng đợi chính lẫn hàng đợi đăng YouTube, rảnh thêm 3 phút thì máy ngủ; có việc
mới chen vào là huỷ đếm; ngủ xong tự bỏ tick (một lần duy nhất). Bỏ tick là huỷ,
kể cả lúc đang đếm ngược. Ngủ chứ không tắt máy: sáng chạm chuột là server, hàng
đợi và các phiên đăng nhập còn nguyên.

Code ở `power.py`, nhưng **lệnh ngủ + số phút chờ nằm bên GUI**
(`suspend_computer` / `SLEEP_DELAY_MIN` trong `amain_taogiong_gui.py`) — ô 🌙 bên
GUI và ô 🌙 trên web phải cư xử y hệt nhau. Máy nào bật sẵn ngủ đông có thể vào
hibernate thay vì sleep — muốn ngủ thật thì `powercfg -h off`.

Không port sang web: ô “⏻ xong thì TẮT MÁY” (web chỉ cho ngủ, không tắt máy bạn)
và “⬆️ hiện cửa sổ khi tạo giọng” (web không có cửa sổ). Hai tuỳ chọn đó vẫn còn
nguyên bên GUI và không bị trang web ghi đè.

## Cấu trúc

```
web/
  server.py      FastAPI: route + token
  core.py        cầu nối sang scripts/ — hằng đường dẫn, trạng thái tập, cài đặt, SEO
  jobs.py        hàng đợi MỘT worker; mỗi bước là một tiến trình con; log() → console
  power.py       ô “🌙 xong hết thì cho máy ngủ” — luồng nền canh hai hàng đợi
  steps.py       yêu cầu từ giao diện → danh sách bước cho hàng đợi
  runners/
    run_episode.py    chạy các bước của một tập
    run_tts.py        tạo giọng + dựng lại video (trang Giọng nói)
    run_thumbnail.py  tạo thumbnail từ tiêu đề tự nhập
  templates/     Jinja2 + HTMX
    _form_script.html / _form_voice.html   khối dùng chung cho Home và trang riêng
  static/        CSS, JS, htmx.min.js (kèm sẵn — chạy được khi không có mạng)
```

## Ba điều cần biết khi sửa

**1. Không chép lại logic.** `runners/run_episode.py` tạo một `App` “rỗng”
(`HeadlessApp` — cố ý không gọi `super().__init__()` nên không dựng cửa sổ Tk) rồi
gọi thẳng các method thuần logic của `amain_taogiong_gui`: `_allocate_episode`,
`_dich_gemini_cho_tap`, `_batch_prepare_input`, `_make_thumbnail_for_folder`,
`_batch_run_tts`, `_manifest_update`. Nhờ vậy các chốt an toàn (dịch thiếu đoạn thì
KHÔNG ghi input.txt, không tạo audio/video) chỉ tồn tại ở MỘT nơi.

Hệ quả: method nào bên GUI đổi sang đọc `tk.Var` thì web sẽ **nổ ngay** chứ không
âm thầm chạy sai. Đó là chủ ý.

**2. Home không chép lại giao diện.** `home.html` chỉ `include` đúng hai partial
`_form_script.html` + `_form_voice.html` mà trang Tạo kịch bản và trang Giọng nói
đang dùng, còn context lấy từ `_script_ctx()` / `_voice_ctx()` trong `server.py`.
Thêm một ô mới ở trang riêng là Home có ngay, không có bản sao nào phải giữ đồng bộ.
Các nút chạy quay về đúng trang vừa bấm nhờ `_back(request, …)` (đọc Referer).

**3. Cài đặt dùng chung với GUI.** Các trang ghi thẳng vào chính
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
