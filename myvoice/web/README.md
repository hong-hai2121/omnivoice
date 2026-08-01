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
| **🎧 Giọng nói** | Giọng nói (TTS + video) | Chế độ clone/thiết kế/mặc định, giọng mẫu + ★ + nghe thử, tệp vào/ra, cài đặt chung, video ngang · phụ đề · cắt audio · dọc · TikTok, ba nút “Dựng lại”, xoá output |
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

Không port sang web: ô “⏻ xong thì tắt máy” (web không tự tắt máy bạn) và
“⬆️ hiện cửa sổ khi tạo giọng” (web không có cửa sổ). Hai tuỳ chọn đó vẫn còn
nguyên bên GUI và không bị trang web ghi đè.

## Cấu trúc

```
web/
  server.py      FastAPI: route + token
  core.py        cầu nối sang scripts/ — hằng đường dẫn, trạng thái tập, cài đặt, SEO
  jobs.py        hàng đợi MỘT worker; mỗi bước là một tiến trình con; log() → console
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
