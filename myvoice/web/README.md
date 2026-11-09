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
| Đổi cổng (mặc định 8766; bận thì tự dò 8767, 8768, … — chạy cùng myvideo vẫn được) | đặt `MYVOICE_WEB_PORT` |
| Không tự mở trình duyệt | đặt `MYVOICE_WEB_NO_OPEN=1` |
| Đổi token | xoá `web/token.txt` rồi chạy lại |

## Bảy trang — menu trái, xếp theo thứ tự làm việc

| Trang | Tab tương ứng bên GUI | Có gì |
|---|---|---|
| **🏠 Home** (trang chủ `/`) | 🏠 Home (đầy đủ) | **Mọi nút chức năng**: hàng đợi · ① kịch bản ①②③ · ② hàng loạt theo tập (bảng tập + ②③④⑤) · ③ giọng nói & video · ④ thumbnail |
| **🛠 Tạo kịch bản** (`/kichban`) | Tạo kịch bản | Ba bước ①②③ với các ô ⛓ nối bước, hàng đợi, tập bỏ qua, câu mở đầu Gemini, reset quy trình |
| **🎙 Nhận diện** | Nhận diện | ① nhận diện link → bảng tập tick chọn → các nút hàng loạt ②③④⑤ |
| **🎧 Giọng nói** | Giọng nói (TTS + video) | Chế độ clone/thiết kế/mặc định, giọng mẫu + ★ + nghe thử, tệp vào/ra, cài đặt chung, video ngang · phụ đề · dọc · TikTok, ba nút “Dựng lại”, xoá output |
| **🖼 Thumbnail** | Thumbnail | Tiêu đề (gợi ý sẵn từ SEO), ảnh nền, số tập, xem trước bản ngang + dọc |

**✂ Che chữ Trung cháy sẵn trong clip** (khối ④ Video ngang, 08/11/2026; khoá
`che_chu_trung` trong `taogiong_options.json`, **mặc định tắt**; GUI Tk chưa có ô → chạy
như tắt): video ngang/dọc từ 08/11/2026 không còn khung trang trí và **không phóng to**
(1:1). Tắt = giữ nguyên khung hình gốc, logo nhỏ góc trên phải, bản dọc dải 1080×1080
giữa màn hình. Bật = cắt 8 % mép trên + 13 % mép dưới (phụ đề Trung + watermark bilibili),
ngang lót dải đen mỏng trên/dưới với logo nằm trong dải dưới, bản dọc dải 1080×852. Trạng
thái ghi vào `YOUTUBE_goc.json` (`che`) nên nút "Dựng lại video dọc" theo đúng bản ngang;
ảnh xem trước khối ⑦ vẽ theo trạng thái đang lưu (cache `static/khungdoc/xt_<màu>[_che].jpg`).
Xem `scripts/video_khung.py` (`loc_phu_kin`, `lop_logo`) và `scripts/video_doc_khung.py` (`bo_cuc`).

**🎞 Lấy video tải xuống làm video nguồn** (khối ④ Video ngang, 24/10/2026; khoá
`ngang_tu_nguon` + `ngang_nguon_zoom` trong `taogiong_options.json`, GUI có cùng ô):
thay vì ghép clip `videongang/`, video ngang lấy hình từ CHÍNH video của tập — link
Bilibili đã tải về `Downloads/<mã BV>.mp4` (bước ⬇ tải / nhận diện), hoặc file video
chọn từ máy. File tải về **không bị sửa**: bước nhận diện + dịch vẫn nghe tiếng gốc,
tới lúc dựng video (bước `tts`) tiếng gốc mới bị tắt (không map audio), hình phóng to
N % (mặc định 120) rồi cắt giữa để che logo/chữ ở mép, và kéo/nén thời lượng cho khớp
giọng đọc (kẹp 0,5–2×, lệch hơn thì lặp/cắt). Không có video (link yt-dlp chỉ mp3,
chưa tải…) → ghi cảnh báo rồi ghép clip theo “Nguồn clip ngang” như cũ. Bản dọc
(`doc_khung`) dựng từ `YOUTUBE_goc.mp4` nên cũng lấy hình này. Runner `run_episode.py`
đưa thẳng đường dẫn video (`ngang_source_video`), còn nút ▶ Dựng lại / GUI tra
`batch_manifest.json` theo thư mục tập (`gui.nguon_video_cua_tap`).

**Ô “Tải Bilibili”** (cạnh Model + Tốc độ ở khối Nguồn và trang Nhận diện, 05/11/2026;
khoá `bili_quality` trong `taogiong_pipeline.json`, mức ở `gui.BILI_QUALITIES`): mức
video khi tải link Bilibili qua app Bili23 — `Cao nhất` (mặc định, như trước) / 1080P /
720P / 480P / 360P. Kênh audio chỉ cần tiếng để nhận diện nên 360P là đủ. Bản thấp lưu
tên RIÊNG `Downloads/<mã BV>_<mức>.mp4`; `<mã BV>.mp4` luôn là bản đầy đủ nên myvideo và
🎞 không nhặt nhầm bản mờ (đã có bản đầy đủ thì dùng luôn, khỏi tải bản thấp). Đang bật
🎞 thì vẫn tải bản cao nhất. Video thiếu đúng mức đã chọn → lấy mức gần nhất không vượt
(`chon_muc` trong `myvideo/video_taibilibili.py`, tham số `--chat-luong`). GUI Tkinter
không có ô này vì ở đó link tải bằng yt-dlp (chỉ mp3), không qua Bili23.

**Tự đóng app Bili23 sau đợt tải** (08/11/2026): bộ tải tự mở app thì ghi dấu PID
(`%TEMP%\omnivoice_bili23_tu_mo.json`); "⏩ đợt 1 · tải video/audio" có thêm bước cuối
*Đóng app Bili23 (nếu bộ tải tự mở)* = `video_taibilibili.py --dong-app`
(`steps.dong_bili23_step`) — chỉ đóng đúng tiến trình đã tự mở, app người dùng mở sẵn
hay PID đã cấp lại thì để nguyên; đóng êm (WM_CLOSE) trước, 8 s còn sống mới ép. Đóng sau
cả đợt chứ không sau từng tập (mở lại mất ~10 s). Chạy lẻ một tập (bước nhận diện tự
tải) không tự đóng. Test: `myvoice/tests/test_dong_bili23.py`.

**Nguồn clip ngang tick NHIỀU thư mục** (khối ③, 01/11/2026): ô chọn 1 thư mục con
`videongang/` đổi thành cụm checkbox (GUI: nút thả menu có ô tick, cùng ô). Khoá
`ngang_source` trong `taogiong_options.json` nay là **list tên thư mục con** (chuỗi 1
tên cũ vẫn đọc được, `gui.ngang_source_list`); `[]`/không tick = cả kho. Lúc dựng,
`video_khung.gom_clip_kho` gộp clip của mọi thư mục đã tick rồi xáo chung tới khi đủ
thời lượng — thư mục nhiều clip xuất hiện nhiều hơn theo tỉ lệ. Thư mục đã tick nhưng
không còn trên đĩa hiện "(không thấy)" để bỏ tick; lúc dựng bị bỏ qua (ghi log), bỏ hết
→ dùng cả kho. Form gửi kèm hidden rỗng cùng tên nên server phân biệt được "bỏ tick hết"
với "trang không có ô này".
| **📑 Copy SEO** | Copy SEO | Tiêu đề · tiêu đề TikTok · mô tả · thẻ tag, đúng nội dung 3 nút Copy bên GUI |
| **📤 Đăng bài** (`/dangbai`) | — | Hàng đợi + **đúng hai khối "Đăng YouTube" và "Đăng Facebook" của Home** cho lúc chỉ ngồi canh việc đăng |

Làm việc hằng ngày chỉ cần trang **Home** — các trang còn lại là chỗ xem kỹ từng
phần và vài tuỳ chọn ít dùng (tập bỏ qua, câu mở đầu Gemini, reset quy trình, xóa
output, xem trước thumbnail, copy SEO).

Riêng **📤 Đăng bài** không thêm chức năng nào: nó `include` đúng hai partial
`_form_upload.html` + `_form_facebook.html` mà Home đang dùng, context lấy từ
chính `_upload_ctx()` / `_fb_ctx()` — nên hai trang **không thể lệch nhau**, bấm
bên nào cũng vào cùng hàng đợi, cùng file cài đặt (kiểm bằng cách so HTML hai
trang: hai khối giống nhau từng ký tự). Các nút quay về đúng trang vừa bấm nhờ
`_back()` đọc Referer, còn nút Facebook trả thẳng khối đã vẽ lại nên trang nào
cũng tự cập nhật tại chỗ.

**🎧 Nghe thử cài đặt giọng (06/11/2026).** Hàng “3 Cài đặt tạo giọng” có nút 🎧 + thanh
phát: `app.js` (khối “Nghe thử”) gửi các ô giọng đang hiện tới `POST /giongnoi/nghethu`
(không ghi cài đặt), server áp lên mẫu ~30 s giọng gốc của tập đầu đợt mới nhất
(`scripts/taogiong_nghethu.py`, lưu ở `voice/nghe_thu/`) rồi trả đường phát qua
`/giongnoi/nghe`. Đã bấm 🎧 một lần thì đổi ô giọng nào là tự phát lại bản mới. Chi tiết
cách chọn tập / lúc thay mẫu: mục 🎧 trong `myvoice/README.md`.

**Hàng thu gọn (06/11/2026).** Từ khối “1 Nhận diện giọng nói” trở xuống (①②③ kịch
bản · 8 khối giọng nói & video · thumbnail · đăng YouTube · đăng Facebook), mỗi khối
là **một hàng trọn bề ngang, bấm đầu hàng để thu gọn/mở** — thay cho kiểu Home tự
chia 2–3 cột bằng CSS columns trước đó. Mỗi hàng là
`<details class="panel fold" data-fold="<khoá>">` + `<summary class="phead">` +
`<div class="foldbody">` (luật ở `app.css`, khối “HÀNG THU GỌN”): thẻ `<details>` gốc
của trình duyệt nên **ô trong hàng đang đóng vẫn gửi theo form** — tự lưu và các nút
chạy không đổi gì. Trạng thái mở/đóng từng hàng nhớ ở `localStorage` (`mv.fold.v1`,
khoá = `data-fold`, dùng chung mọi trang) và được áp lại sau mỗi lần htmx vẽ lại khối
(IIFE cuối `app.js`); chưa bấm hàng nào thì theo thuộc tính `open` của template (mọi
hàng mở, riêng “6 Kiểu phụ đề vẽ cứng” đóng). Hai nút `data-fold-all` ngay trên hàng
đầu thu gọn / mở hết. Trong hàng: `.grid` dùng `auto-fill` (ô nhập không giãn hết
hàng; `.w2`/`.w3` cho ô dài), `.chks` nằm ngang, `.hang` = nút + ô tick trên một dòng,
`.foldsplit` = ô chỉnh bên trái · ảnh/bảng bên phải. Chữ giải thích dài của các khối
này chuyển vào `title` (rê chuột vào ô/nút); “Nguồn clip ngang” dời từ khối 3 sang
khối 4 *Video ngang*. Thêm khối mới thì dùng đúng khuôn trên và đặt `data-fold` riêng.
Khối hàng loạt phía trên vẫn dùng `.batch-grid`: cột hẹp (nhập link · nút chạy) | cột
rộng (bảng tập). Các trang riêng xếp dọc một cột, căn giữa màn hình như cũ.

Giao diện: menu trái tím gradient (giữ nguyên mọi trang) + mỗi trang một tông màu
riêng để nhìn là biết đang ở đâu — Home chàm · kịch bản tím · nhận diện xanh dương · giọng nói
hồng · thumbnail cam · SEO xanh ngọc. Tông màu khai báo ở đầu `static/app.css`
(`body.p-<tên trang>` đặt `--accent`/`--accent2`/`--accent-soft`), đổi một dòng là
đổi cả trang; sáng/tối tự theo cài đặt Windows.

**Nhật ký nằm ở cửa sổ console của server**, không còn panel dưới trang web:
mọi dòng của tiến trình con in thẳng ra đó.

**Nhật ký còn được chép ra tệp** (05/11/2026): `web/nhatky/hangdoi_<ngày>.log`, mỗi
ngày một tệp, mỗi dòng kèm giờ, xả ra đĩa theo từng dòng, giữ 14 ngày
(`jobs.NHATKY_GIU_NGAY`). Console chỉ nằm trong RAM — mẻ chạy đêm xong ô ⏻ tắt máy là
mất hết, sáng ra không biết vì sao dừng (sự cố đêm 05/11/2026). Xem lại ở trang
**📜 Nhật ký** (`/nhatky`, nút cạnh chữ *Hàng đợi*): mặc định chỉ các mốc chính (việc
bắt đầu / xong / lỗi, bước, tắt máy), bấm *Đầy đủ* để xem mọi dòng; dòng lỗi tô đỏ.
Chỉ server thật bật ghi tệp (`jobs.bat_nhat_ky_tep` trong `main()`), test import
module thì không sinh tệp. myvideo dùng chung `JobRunner` nên cũng ghi, vào
`myvideo/web/nhatky/`.

**Lỗi GPU → hàng đợi TẠM DỪNG** (05/11/2026): runner trả mã thoát **79**
(`gpu_batbuoc.MA_THOAT_GPU`) khi lượt chạy dừng vì `GpuLoi` — không có CUDA, thiếu
VRAM, NVENC chết, worker VieNeu mất GPU. Các bước dùng GPU khai `Step.halt_codes`, hàng
đợi thấy mã này thì đánh dấu việc lỗi rồi **tạm dừng, giữ nguyên việc còn chờ** (kể cả
bước `continue_on_fail` trong một đợt) thay vì chạy tiếp các tập sau để hỏng y hệt.
Đầu khối hàng đợi hiện băng đỏ nêu lý do + cách chạy lại; bấm *▶ Tiếp* là chạy tiếp
việc còn chờ, tập vừa lỗi thì ⏩ Chạy tiếp để làm lại. Chế độ 🗣 VieNeu cũng **ép GPU**:
worker bật với `--device cuda`, không dùng được CUDA là dừng ngay chứ không lặng lẽ
chạy ONNX/CPU (chậm ~4 lần rồi vẫn dừng ở bước ASR kiểm tra).

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

**📘 Đăng Facebook** — khối cuối trang Home (dưới Đăng YouTube), cũng có ở trang
📤 Đăng bài: **bảng lịch đang chờ trên Page** + **bảng các tập chưa đăng** kèm
**ngày dự kiến đăng** và **tiêu đề đúng như bài sẽ đăng**, xem được TRƯỚC khi bấm
chạy; ba nút — 📘 đăng các tập chưa đăng · 🔍 xem kế hoạch (dry-run) · 🔄 cập nhật
lịch Page. Tick vài tập thì chỉ làm những tập đó, không tick ô nào = làm tất cả.

**Bản đăng lên Page** (ô radio đầu khối, 15/09/2026; `web_settings.json` khoá
`fb_ban`, route `/dangfacebook/ban`): **full** = `facebook.mp4` trọn tập (mặc
định, nếp cũ) · **ngan** = `tiktok.mp4` **cắt ngắn giống TikTok** (theo % ở khối
Video TikTok, có nhạc nền). Áp cho CẢ tự động lẫn nút 📘; script đọc lúc CHẠY
(`core.facebook_ban()`, hoặc cờ `--ban`) nên việc đang nằm chờ cũng theo ô mới.
Đăng YouTube xong thì **cả hai bản dọc bị đổi tên theo tiêu đề SEO**
(`dang_tap_youtube.rename_doc`): bản TikTok thành `Full ở Mimi audio Số 111 -
….mp4`, bản full thành `[Full] Mimi audio Số 111 - ….mp4` (từ 20/09/2026; trước
đó là `facebook <ngày giờ>.mp4`). Nên cả hai hàm tìm video đều tra
`youtube_upload.json` trước (`facebook_file` / `tiktok_file`) rồi mới mò theo mẫu
tên: `find_video_full` — `facebook.mp4` → bản ghi → `[Full] ….mp4` → `facebook
*.mp4` → `*_doc.mp4`; `find_video_ngan` — `tiktok.mp4` → bản ghi → `tiktok *.mp4`
/ `Full ở *.mp4`. Mẫu `[Full] …` **không glob được** (trong mẫu glob `[...]` là
lớp ký tự) nên so bằng `startswith`. Bản ngắn: tiêu đề bài mở đầu **“Full ở”**
như TikTok (`title_for`) để bài mồi trỏ về bản đầy đủ trên YouTube. Tập chưa dựng TikTok thì **bỏ qua có báo, không đăng bản
full thay** — người chọn bản ngắn là cố ý không đưa trọn tập lên Page. Đổi ô là
server trả lại CẢ khối (bảng video/cỡ/tiêu đề/tập bị bỏ đổi theo); sổ + biên
nhận ghi thêm `ban` và `video` để biết Page đang có bản nào của tập.

Lịch xếp vào các khung **9h/19h còn TRỐNG** tính từ bây giờ, chứ không nối đuôi
bài chờ xa nhất: xoá bài đã lên lịch ngày mai thì lần xếp sau lấp lại đúng ngày
mai. Mỗi mốc đọc được quy về khung gần nhất (`slot_key`) nên bài đăng tay lúc
09:12 vẫn tính là đã chiếm khung 9h. Đọc Page thiếu thì tự lùi về nếp cũ (nối sau
mốc xa nhất) cho khỏi đăng chồng — xem `plan_slots(count, anchor, busy)`.

Khối tự vẽ lại mỗi 6 giây (`/partials/facebook`) trong lúc hàng đợi Facebook còn
việc, nên bấm 🔄 xong là bảng tự cập nhật; hàng đợi rảnh thì bản vẽ mới không còn
`hx-get` nên vòng làm mới tự tắt.

**Nằm trong chuỗi tự động** — ô tick “📘 Dựng xong video thì TỰ lên lịch đăng
Page” (mặc định BẬT, lưu ở `web_settings.json` khoá `fb_auto`). Dựng xong video
một tập là `queue_after_build()` xếp **cả hai** việc đăng rồi đi tiếp tập sau
ngay: YouTube vào `upload_runner`, Facebook vào **`fb_runner` — hàng đợi thứ ba,
riêng biệt**. Riêng chứ không chung với hàng đăng YouTube để hai bên chạy song
song (nếu chung thì Page phải đợi video YouTube tải xong mới tới lượt). Nhưng
`fb_runner` vẫn **một worker duy nhất, đừng bỏ**: hai lần chạy script Facebook
cùng lúc sẽ cùng đọc “giờ lên lịch xa nhất” rồi cùng xếp vào ĐÚNG MỘT khung giờ.

Ô 📘 đọc lại mỗi lần dùng nên bật/tắt giữa mẻ đang chạy là tập kế tiếp theo ngay.
`fb_runner` cũng được tính vào `heavy_busy` của ô ⏻ và vào `upload_busy` của
`/api/trangthai` — đang tải video lên Page mà tắt máy là hỏng.

Ngày dự kiến tính bằng **đúng hàm** mà lúc chạy thật sẽ dùng (`plan_slots` của
script, khung bận suy từ file qua `known_busy`) — bảng nói một đằng Facebook nhận
một nẻo là kiểu sai khó chịu nhất, nên hai bên không được có hai phép tính. Lúc
bấm chạy script vẫn đọc lại lịch Page một lần rồi chốt.

Tiêu đề bài đăng do **`compose_facebook_title`** (trong `YOUTUBE/thumbnail_gui.py`,
cạnh `compose_youtube_title` / `compose_tiktok_title`) dựng: lấy **tiêu đề
YouTube** rồi ghép **bộ hashtag của mô tả** vào cùng MỘT DÒNG. Lý do gộp: bảng tin
Facebook cắt bớt bằng “Xem thêm”, hashtag nằm dưới mô tả dài coi như không ai
thấy. Hashtag lấy từ mô tả SEO chứ không bịa thêm (`hashtags_in` bỏ trùng, bỏ dấu
câu dính đuôi), nên muốn đổi bộ hashtag thì sửa ở SEO như mọi kênh khác.

Cả ba nút chạy `myvoice/FACEBOOK/dang_video_facebook.py` trong **hàng đợi đăng**
nên kế hoạch/tiến trình hiện ở nhật ký hàng đợi đăng, trang không tải lại. Hai
việc 🔍/🔄 xếp hàng dạng **light** (xem `JobRunner.heavy_busy`) nên KHÔNG kích
hoạt ô ⏻/🌙 — bấm xem kế hoạch xong máy không tự tắt/ngủ sau 1 phút.

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

*“Đã đăng chưa” tra SỔ LOCAL, Page chỉ hỏi LỊCH ĐANG CHỜ* — `FACEBOOK/da_dang.json`
là nguồn sự thật cho câu hỏi tập nào đã lên Page: script ghi vào đó ngay khi
Facebook nhận video (và ghi thêm biên nhận `facebook_upload.json` trong thư mục
tập). Việc thường ngày vì thế chỉ hỏi Page **lịch đang chờ** (`page_schedule`), đủ
để biết khung nào còn trống.

Sổ khoá theo **số tập**, mà một số có thể được **cấp lại cho truyện khác** (95–97:
truyện 31/08/2026 lên Page rồi bị xoá thư mục, 07/09 chế độ làm bù cấp lại cho ba
link mới → sổ vẫn nói "đã đăng", cột Facebook tick sẵn từ lúc chưa có video, dựng
xong lại không xếp lịch). Nên "tập này lên Page chưa" chỉ hỏi qua một hàm
`ledger_covers` (script) — cột Facebook của bảng, khối Đăng Facebook và hàng chờ của
script cùng dùng: biên nhận trong thư mục là chắc; mục sổ ghi kèm `thu_muc` +
`nguon` (từ 08/09/2026) thì so với thư mục/nguồn hiện tại; mục sổ cũ không ghi gì
thì tra manifest (`other_sources_of`) — có truyện **khác** từng mang số này trước
lúc đăng là tập mới vẫn vào hàng chờ (kèm dòng nhắc Page còn bài cũ cùng số), còn
dựng lại **cùng** truyện (85, 87) vẫn bỏ qua như trước: muốn đăng bản mới thì xoá
bài cũ trên Page rồi bấm 🔄. Số request đo thật:

| Thao tác | Request |
|---|---|
| Trang web dựng bảng tập chưa đăng + bảng lịch | **0** (đọc file) |
| 🔍 xem kế hoạch · 📘 đăng (phần lên kế hoạch) | **3** (2 edge + 1 batch) |
| 🔄 cập nhật lịch Page (chỉ khi cần) | ~6 |
| mỗi tập đăng thật | 1 mở phiên + số khúc do FB chia + 1 kết thúc |

`page_schedule` gộp hai đường: `fetch_scheduled` đọc `/scheduled_posts` +
`/videos` (chỉ lấy mốc còn ở tương lai), và `verify_ledger` hỏi lại **từng bài
script đã xếp theo `video_id`** bằng MỘT request batch. Phải có đường thứ hai:
bài video xếp lịch nhiều lúc **không hiện ở `/scheduled_posts`** (đo thật: tập 65
chỉ tra ra được bằng `video_id`) — thiếu nó là tưởng khung đó trống rồi xếp chồng.
Đường batch còn cho biết bài nào **đã bị xoá** và bài nào **bị dời giờ** trong app
Facebook.

Nút 🔄 (`--sync`) quét bài đã đăng + đọc lịch + đối chiếu sổ:
* bài đã bị xoá → gạch khỏi sổ, tập đó **quay lại hàng chờ**, khung giờ thành
  trống. Biên nhận trong thư mục tập chỉ được **đánh dấu** `removed_from_page`
  (giữ nguyên `video_id` để tra lại, bỏ dòng dấu là hoàn nguyên);
* bài bị dời giờ → sổ theo giờ mới;
* Page đang có bài KHÁC của đúng tập ấy chờ lịch (xoá rồi đăng lại bằng tay) thì
  **không** gạch — gạch là đăng trùng.

Chỉ mã `100` + `error_subcode 33` (hoặc câu “does not exist”) và `803` mới được
hiểu là *mất bài*; mọi lỗi khác chỉ hạ cờ `complete` — nhầm chỗ này là đăng trùng
cả loạt. Phần quét bài đã đăng vẫn **quét gia tăng**: `/posts` và `/videos` trả
bài mới nhất trước nên chỉ đọc tới bài đã thấy lần trước (mốc `newest` trong
`page_cache.json`) rồi dừng — đo thử Page 1200 bài: lần đầu 25 request, các lần
sau 3.

*Mốc thời gian của Graph API có HAI kiểu* — `/posts` và `/videos` trả chuỗi ISO
`2026-08-18T09:00:00+0000`, còn `/scheduled_posts` và batch trả **số giây epoch**.
`_parse_fbtime` nhận cả hai; chỉ đỡ được kiểu ISO là hỏng ngay khi Page có bài
chờ lịch.

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

**⏻ Xong hết thì tắt máy / 🌙 Xong hết thì cho máy ngủ** — hai ô tick ngay đầu khối
*Hàng đợi*, loại trừ nhau (tick ô này là bỏ ô kia), **nhớ lựa chọn lần trước** (từ
08/11/2026: tick/bỏ tick là ghi khoá `power_mode` vào `web_settings.json`, mở server
lại là bật y như cũ — trước đó mặc định TẮT mỗi lần mở; hết giờ tự bỏ tick trong RAM
nhưng không đổi lựa chọn đã nhớ). Tick trên web hoặc cửa sổ desktop `chay.py` — ô bên
đó là công tắc từ xa, cùng một trạng thái; phải từng thấy hàng đợi bận rồi mới đếm —
tick suông lúc chưa chạy gì thì không tắt/ngủ. Chạy xong CẢ hàng đợi chính lẫn hàng đợi đăng
YouTube/Facebook, rảnh thêm `SHUTDOWN_DELAY_MIN` / `SLEEP_DELAY_MIN` (đều 1 phút từ
31/10/2026) thì phát `shutdown /s /f /t 0` hoặc gọi `suspend_computer`
(SetSuspendState — ngủ: chạm chuột là dậy, server vẫn còn nguyên); có việc mới chen
vào là huỷ đếm; hết giờ tự bỏ tick (một lần duy nhất). Bộ đếm nằm TRONG server nên
bỏ tick là huỷ, kể cả lúc đang đếm ngược — không cần `shutdown /a`. Trước khi đếm
còn tập dựng xong CHƯA đăng thì ghi cảnh báo vào nhật ký đăng (chỉ báo, không tự
đăng). Route `/hangdoi/tatmay`: `on=1` tắt máy, `ngu=1` ngủ, không gì = tắt;
`/api/trangthai` trả thêm `shutdown_mode` ("" / "shutdown" / "sleep").
Hàng đợi chính **dừng vì lỗi GPU** cũng tính là "hết việc" (việc còn chờ không tự chạy
được nữa — `JobRunner.heavy_busy()` bỏ qua chúng): ⏻/🌙 vẫn tắt/ngủ đúng như đã tick,
và dòng đếm ngược ghi rõ lý do dừng vào tệp nhật ký.

Code ở `power.py`, nhưng **số phút chờ + lệnh ngủ nằm bên GUI** (`SHUTDOWN_DELAY_MIN`,
`SLEEP_DELAY_MIN`, `suspend_computer` trong `amain_taogiong_gui.py`) — ô bên GUI và ô
trên web cùng một con số. (🌙 từng bị bỏ 26/10/2026, user cho quay lại 31/10/2026.)

Không port sang web: ô “⬆️ hiện cửa sổ khi tạo giọng” (web không có cửa sổ). Ô ⏻/🌙
của GUI ghi ra `taogiong_pipeline.json`, còn ô ⏻/🌙 của web chỉ nhớ trong bộ nhớ
server — trang web không ghi đè khoá `shutdown`/`sleep` của GUI.

## Cấu trúc

```
web/
  server.py      FastAPI: route + token
  core.py        cầu nối sang scripts/ — hằng đường dẫn, trạng thái tập, cài đặt, SEO
  jobs.py        hàng đợi MỘT worker; mỗi bước là một tiến trình con; log() → console + tệp nhatky/; mã 79 (lỗi GPU) → tạm dừng hàng đợi
  nhatky/        hangdoi_<ngày>.log — nhật ký hàng đợi chép ra tệp (tự sinh, giữ 14 ngày)
  power.py       ô “⏻ tắt máy” / “🌙 cho máy ngủ” khi xong hết — luồng nền canh ba hàng đợi, đếm ngược rồi shutdown/ngủ
  steps.py       yêu cầu từ giao diện → danh sách bước cho hàng đợi
  runners/
    run_episode.py    chạy các bước của một tập
    run_tts.py        tạo giọng + dựng lại video (trang Giọng nói)
    run_thumbnail.py  tạo thumbnail từ tiêu đề tự nhập
  templates/     Jinja2 + HTMX
    _form_script.html / _form_voice.html   khối dùng chung cho Home và trang riêng
    _form_upload.html / _form_facebook.html  khối đăng — dùng chung Home + /dangbai
  static/        CSS, JS, htmx.min.js (kèm sẵn — chạy được khi không có mạng)
```

## Ba điều cần biết khi sửa

**1. Không chép lại logic.** `runners/run_episode.py` tạo một `App` “rỗng”
(`HeadlessApp` — cố ý không gọi `super().__init__()` nên không dựng cửa sổ Tk) rồi
gọi thẳng các method thuần logic của `amain_taogiong_gui`: `_allocate_episode`,
`_dich_gemini_cho_tap`, `_batch_prepare_input`, `_make_thumbnail_for_folder`,
`_batch_run_tts`, `_manifest_update`. Nhờ vậy các chốt an toàn (dịch thiếu đoạn thì
KHÔNG ghi input.docx, không tạo audio/video) chỉ tồn tại ở MỘT nơi.

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
