# OmniVoice TikTok - Chrome Extension

Mã đang dùng nằm trong thư mục này; các script Desktop Automation cũ đã được dọn.
Giữ `Desktop Automation\danh_sach.json` làm nguồn lịch/trạng thái và bản sao lưu JSON
bên cạnh. Code cùng ảnh thử cũ được nén trong `gptcode\backups\desktop-automation-legacy-20260930-173749.zip`,
không được extension nạp hoặc chạy. Không cần giải nén để sử dụng extension.
Extension điều khiển một tab bằng `chrome.debugger` (Chrome DevTools Protocol),
không dùng Selenium, ChromeDriver, tọa độ màn hình, clipboard hay chuột/bàn phím Windows.
Điều khiển tab không cần Python hay cổng remote debugging. Chức năng tự quét
video dùng bộ đọc thư mục Python nhỏ chạy riêng trên `127.0.0.1:8771`.

## Cài vào Chrome

1. Dùng Chrome 125 trở lên, mở **đúng profile Chrome đã đăng nhập TikTok** (bản cũ đang dùng Profile 83).
2. Vào `chrome://extensions`, bật **Developer mode / Chế độ nhà phát triển**.
3. Chọn **Load unpacked / Tải tiện ích đã giải nén**, chọn thư mục:
   `D:\Python\omnivoice\OmniVoice\Desktop Automation\gptcode\extension`
4. Mở TikTok Studio, bấm biểu tượng **OmniVoice TikTok** trong menu tiện ích.
   Bảng mở bên cạnh trang Studio, không chuyển sang tab khác. Biểu tượng cửa sổ
   ở góc trên bên phải mở bảng thành cửa sổ riêng. Trên bảng hẹp, mở **Nguồn video & lịch**
   để sửa nguồn quét/hashtag chung; hashtag từng video vẫn sửa ngay trong danh sách.

Chrome sẽ báo quyền debugger và hiển thị thanh thông báo khi extension kết nối
với tab. Đó là cơ chế chính thức của Chrome. Không mở DevTools trên tab đang chạy
vì có thể ngắt kết nối debugger. Khi nâng cấp mã, bấm Reload ở `chrome://extensions`
rồi tải lại bảng điều khiển.
Số phiên bản nằm cạnh tên bảng (hiện tại `v0.5.15`). Nhật ký khôi phục khi mở lại
được ghi rõ **Lần chạy trước**, không phải lỗi vừa phát sinh. Lần chạy mới thay
nhật ký cũ và lưu thời điểm cùng phiên bản đã xử lý. Nếu vẫn thấy giao diện cũ,
đóng bảng/cửa sổ tiện ích, Reload chính tiện ích rồi mở lại; F5 TikTok không cập nhật tiện ích.

## Tự cập nhật từ kịch_bản

1. Chạy `chay_quet.py` trong VS Code hoặc mở `chay_quet.bat` ngay trong `gptcode`.
   Chỉ cần Python 3.9 trở lên, không cần cài thư viện. Giữ bộ quét đang chạy.
2. Nếu extension đã cài bản trước, bấm **Reload** trong `chrome://extensions`,
   chấp nhận quyền truy cập localhost nếu Chrome yêu cầu, rồi tải lại bảng điều khiển.
3. Bảng tự quét lúc mở và mỗi 30 giây khi bật **Tự cập nhật**. Có thể bấm
   **Quét kịch_bản** bất kỳ lúc nào. Chức năng này cần bảng điều khiển đang mở.

Thư mục mặc định là `myvoice\kịch_bản` trong cùng repo. Bộ quét chọn `[Full] *.mp4`,
nếu không có thì lấy `facebook*.mp4`, giống bản cũ. Chọn **Đoạn ngắn** để lấy
`short.mp4`. Chọn **Nửa video** để lấy `Full ở … .mp4`, hoặc `tiktok*.mp4` nếu chưa
đổi tên. Đây là bản đã dựng sẵn theo tỷ lệ ở công cụ tạo video, không cắt mới và
không mặc định coi `short.mp4` là nửa tập. File rỗng được bỏ qua; cần đợi render
hoàn tất trước khi nạp lên TikTok.
Tiêu đề lấy từ `youtube_upload.json`, thêm `Full ở`; hashtag thêm `#MimiAudioSoN`
và phần **Hashtag chung**. Có `tiktok_upload.json` thì ghi trạng thái đã đăng.

Chống trùng theo thư mục tập, giữ lịch đăng và nội dung bạn đã sửa. Đường dẫn video
của dòng nhập từ bản cũ được cập nhật sang file quét thấy lần đầu; những lần sau chỉ
cập nhật các trường còn giống dữ liệu tự điền trước đó. Dòng đã xử lý, đã đăng hoặc
đang chờ kiểm tra không bị thay đổi.
Xóa dòng sẽ ẩn tập đó khỏi các lần quét tự động; bấm **Quét kịch_bản** để lấy lại.
Bộ quét đối chiếu toàn bộ thư mục tập: thư mục đã xóa khỏi `kịch_bản` thì dòng
tương ứng tự rời danh sách sau lần quét thành công tiếp theo, kể cả dòng nhập từ
JSON cũ hoặc đã xử lý. Không xóa file, JSON gốc hay biên nhận đăng. Dòng thêm thủ
công từ ngoài thư mục nguồn vẫn được giữ lại. Nếu chỉ thiếu một bản Full/Nửa/Short
nhưng thư mục tập còn tồn tại, dòng vẫn được giữ. Khi quét lỗi hoặc thiếu quyền
đọc, không tự loại dòng dựa trên danh sách chưa đầy đủ.
Sau khi cập nhật bản 0.5.3, khởi động lại `chay_quet.py` để có danh mục thư mục mới.
Bộ quét chỉ đọc dữ liệu, không sửa thư mục kịch bản hay danh sách của công cụ cũ.

Lệnh chạy từ terminal:

```powershell
python "D:\Python\omnivoice\OmniVoice\Desktop Automation\gptcode\chay_quet.py"
```

Có thể đổi thư mục bằng `--root "D:\thu_muc_kich_ban"`. Nếu cổng 8771 đang bị chiếm,
kiểm tra tiến trình đang chạy trước khi mở thêm bộ quét. Bộ quét chỉ cung cấp API
cho extension; không có trang web điều khiển ở địa chỉ localhost.

## Trạng thái và phiên bản video

Trạng thái cùng ghi chú cũng được lấy từ `danh_sach.json`, ghép theo thư mục tập.
Nhãn **JSON cũ** cho biết đây là trạng thái lưu từ công cụ cũ, không phải kết quả
kiểm tra trực tiếp TikTok. Ví dụ `đang hẹn giờ` trong JSON được giữ nguyên nhãn nhưng
không có nghĩa tác vụ đó đang chạy trong extension. Kết quả mới của extension và
biên nhận đã đăng được giữ lại, không bị lần quét sau ghi đè bằng trạng thái cũ.

- Tích các dòng, bấm **Nửa video**, **Full** hoặc **Short** để đổi hàng loạt.
- Hoặc đổi bằng menu **Phiên bản video** ngay trên từng dòng. Lựa chọn được giữ qua
  các lần quét và khi mở lại bảng, không đổi mô tả, trạng thái hoặc giờ đăng.
- Nếu thiếu bản được chọn, giữ file hiện tại và báo rõ video bị thiếu trong nhật ký.
- Ô chọn đầu bảng chọn/bỏ chọn các dòng đang hiển thị theo bộ lọc. Ô tìm kiếm và bộ
  lọc trạng thái giúp tìm tập đang cần xử lý. **Điền tiếp** yêu cầu đúng một dòng.
  **Nạp & điền** chạy nhiều dòng khi bật **Bấm Đăng / Lên lịch**; nếu không bật,
  chỉ chuẩn bị một bản nháp. Đổi phiên bản và đánh dấu đã xử lý cho phép chọn nhiều dòng.
- Bấm tên file để mở đường dẫn có thể chỉnh sửa. Thanh thao tác nằm ngay trước
  bảng; giao diện điện thoại hiển thị các trường theo chiều dọc.

## Nối tiếp giờ đăng từ JSON cũ

Bộ quét đọc lại `Desktop Automation\danh_sach.json` mỗi lần quét, lấy `gio_dang`
và `khung_gio`. Các video được ghép theo thư mục tập, kể cả khi tên file đã đổi từ
bản cũ sang `[Full]` hoặc `short.mp4`. Không ghi ngược vào JSON cũ.

- Khôi phục giờ đã có trong JSON cho các ô trống; thời gian bạn sửa tay trong
  extension được giữ nguyên.
- Lấy giờ đăng muộn nhất làm mốc, xếp các tập tiếp theo theo số tập và khung giờ
  của JSON. Tập cũ trước mốc không tự nhận lịch mới.
- Ví dụ: tập 124 lúc `2026-10-02T20:00`, khung `08:00, 20:00` thì tập 125 nhận
  `2026-10-03T08:00`, tập 126 nhận `2026-10-03T20:00`.
- Khi JSON đổi hoặc bạn sửa giờ của một dòng, các lịch tự sinh tiếp theo được
  tính lại. Dòng đã đăng/đã xử lý/đang chờ kiểm tra giữ nguyên lịch.
- Tránh lịch trùng, bỏ giờ quá gần hiện tại (dưới 20 phút), chỉ xếp trong 30 ngày
  tới như bản cũ. Nếu JSON không có khung giờ thì dùng giờ của mốc cuối mỗi ngày.
  Nếu chưa có mốc hoặc JSON bị lỗi, giữ danh sách và báo trạng thái, không đoán ngày.

Lịch được lưu trong kho riêng của extension. Việc tự điền cột **Giờ đăng** không
bật tùy chọn **Đặt ngày giờ** và không bấm đăng trên TikTok. Có thể dùng `--queue`
với `chay_quet.py` để chỉ định một file JSON nguồn khác.

## Dùng với danh sách hiện có

1. Bấm **Nhập JSON**, chọn `Desktop Automation\danh_sach.json`.
   Dữ liệu được nhập vào kho riêng của extension; file cũ không bị sửa.
   Nhập lại ghép theo thư mục tập, bổ sung lịch còn thiếu và đồng bộ trạng thái;
   không tạo dòng trùng khi tên file thay đổi.
2. Mở trang tải lên TikTok Studio trong cùng profile, chọn đúng tab trong bảng.
   Đảm bảo đó là bản nháp trống trước khi nạp video mới.
3. Chọn một dòng, kiểm tra đường dẫn file, mô tả, hashtag, ngày giờ.
4. **Đặt ngày giờ** và **Bấm Đăng / Lên lịch** mặc định bật mỗi lần mở bảng.
   Bỏ tích **Bấm Đăng / Lên lịch** nếu chỉ muốn chuẩn bị bản nháp để kiểm tra.
   Mở bảng không tự chạy; vẫn cần bấm nút thao tác.
   Bấm **Nạp & điền**. File được gán trực tiếp vào ô tải lên bằng CDP,
   không mở hộp thoại file. Nếu Chrome từ chối truy cập file, kiểm tra mục
   **Allow access to file URLs** trong chi tiết extension nếu Chrome cung cấp mục đó.
5. **Đặt ngày giờ** mặc định bật, dùng lịch của dòng đã chọn; bỏ tích nếu không muốn điền lịch.
   Giờ được nhập theo múi giờ hiển thị trên trang TikTok; đối chiếu múi giờ tài khoản
   với Windows. Không tự quy đổi. Ngày giờ phải còn ít nhất 15 phút và phút là bội số 5;
   giới hạn xa nhất còn tùy giao diện/tài khoản TikTok.
6. **Điền tiếp** chỉ điền mô tả/lịch trên bản nháp đang mở, không tải file lần nữa.
   Tự bấm đăng ở chế độ này chỉ được phép với bản nháp extension đã nạp trong
   cùng trang chưa tải lại. Với bản nháp không xác định được video, hãy kiểm tra
   và bấm nút cuối trực tiếp trên TikTok.
   Riêng khi còn hộp thoại kiểm tra video của lần bấm trước, bản 0.5.11 chỉ
   tiếp tục bước xác nhận dưới đây, không điền lại hoặc bấm lại nút Lên lịch.
7. Nếu không bật bấm nút cuối: kiểm tra video tải/xử lý xong, mô tả và lịch trên TikTok,
   rồi tự bấm đăng/lên lịch. Sau đó có thể bấm **Đã xử lý** trong bảng.
8. Nếu đã bật bấm nút cuối: extension chờ thanh `.info-progress` hiển thị có
   lớp `success` và độ rộng `100%`, đồng thời nút sẵn sàng (tối đa 30 phút), đọc lại
   mô tả và ngày giờ, rồi bấm một lần. Chỉ báo hoàn tất khi đọc được thông báo
   đăng/lên lịch thành công hoặc đối chiếu được bài trên trang Nội dung như dưới đây.
   Chỉ chuyển trang hoặc tải file xong chưa được tính là thành công.

Từ bản 0.5.13, sau khi TikTok chuyển tới `/tiktokstudio/content`, extension đọc các
dòng con của `components_PostTable_Container` và tiêu đề trong
`components_PostInfoCell_Container > a`. Đối chiếu toàn bộ tiêu đề, bỏ hashtag,
chuẩn hóa Unicode/khoảng trắng và không phân biệt hoa thường; không so khớp gần đúng
theo số tập hoặc một phần tên. Biểu tượng `Alarm` xác định bài đã lên lịch;
ngày/giờ hiển thị phải khớp lịch đã chọn khi xác nhận sau lần đăng tự động.
Lưu ID, URL, tiêu đề và trạng thái bài vào `postEvidence` trong biên nhận.

Để kiểm tra các lần đã chạy trước đó: mở trang **Nội dung** TikTok, chọn tab đó
trong bảng extension (bấm làm mới danh sách tab nếu cần), chọn các video rồi bấm
**Kiểm tra bài đăng**. Bước này chỉ đọc, không tải video hay bấm đăng; bỏ qua việc
lịch cũ đã quá hạn. Dòng có tiêu đề khớp duy nhất và trạng thái đã đăng/lên lịch
được đánh dấu **Đã xử lý**. Nhật ký ghi trạng thái thực tế và URL bài.
Đối chiếu thủ công theo tên xác nhận bài đã tồn tại, không chứng minh một lần đăng
lại vừa tạo ra bài mới. Không thay đổi ngày giờ trong danh sách khi kiểm tra thủ công.

Bảng TikTok tải từng phần: chỉ kiểm tra các dòng đã hiện trong DOM. Không tìm thấy
chưa có nghĩa là đăng thất bại; cuộn/lọc danh sách TikTok đến bài cần kiểm tra rồi
bấm lại. Không hạ trạng thái của dòng đã xác nhận thành công chỉ vì bài chưa hiện.
Trùng tiêu đề, trạng thái đang xử lý/kiểm tra hoặc lịch không khớp thì không tự xác
nhận. Khi đăng lại, bước tự động loại ID bài cũ đã biết; nếu lịch/tên có thể trùng
bài cũ nhưng chưa lưu được ID lần trước, giữ chờ kiểm tra để tránh nhận nhầm bài cũ.

Bản 0.5.11 xử lý cả hai dạng hộp thoại **Tiếp tục đăng?**: thông báo TikTok vẫn
đang kiểm tra video, có hoặc không có đoạn **Kiểm tra bản quyền chưa hoàn tất**.
Extension bấm **Đăng ngay** đúng trong hộp thoại đó khi đã bật **Bấm Đăng /
Lên lịch**. Thao tác này tiếp tục đăng trước khi kiểm tra hoàn tất; ở dạng có cảnh
báo bản quyền, TikTok cho biết phần kiểm tra chưa hoàn tất sẽ chấm dứt.
Extension không đổi chế độ đăng hoặc lịch đã chọn; đọc lại file, hashtag, ngày/giờ
và tiến trình success 100% trước khi xác nhận. Hộp thoại khác, nhiều nút trùng tên
hoặc nội dung không nhận diện được vẫn dừng. Chỉ báo hoàn tất sau thông báo thành công
hoặc đối chiếu được bài trên trang Nội dung.

Nếu bản cũ đã dừng ở hộp thoại này: giữ nguyên tab TikTok và hộp thoại, Reload
extension, chọn đúng dòng và bấm **Điền tiếp** với tùy chọn bấm nút cuối bật.
Chỉ tiếp tục khi biên nhận còn `uncertain`, chưa bấm xác nhận, cùng file/lịch và
bản nháp vẫn được nhận diện. Không nạp video hoặc bấm Lên lịch lần nữa. Lần bấm
Đăng ngay cũng được lưu trước khi thực hiện; nếu kết quả không rõ, không tự bấm lại.

Khi chọn nhiều dòng và bật bấm nút cuối, hàng đợi chạy theo thứ tự trong danh sách.
Chỉ mở trang tải mới cho video kế tiếp sau khi video trước được xác nhận thành công.
Từ bản 0.5.14, nếu tab đang ở **Nội dung**, bấm **Nạp & điền** cho video mới sẽ
tự chuyển cùng tab về `https://www.tiktok.com/tiktokstudio/upload?from=creator_center&tab=video`,
chờ trang tải xong rồi mới nạp file. Video tiếp theo trong hàng đợi và nút **Mở Studio**
cũng dùng link này. Không cần quay về thủ công. Nếu đã ở trang tải lên, không tải lại
trang để tránh mất bản nháp. **Điền tiếp** và **Kiểm tra bài đăng** không tự chuyển trang.
Đóng bảng không dừng tác vụ nền, nhưng phải giữ Chrome và tab TikTok đang mở.
Kết quả từng dòng và biên nhận lần bấm được lưu trong extension; không ghi ngược
`danh_sach.json` hoặc `tiktok_upload.json` của công cụ cũ.

Nếu có hộp thoại xác nhận chưa nhận diện hoặc không đọc được kết quả sau 45 giây,
hàng đợi dừng. Video có thể đã được đăng: kiểm tra trực tiếp TikTok trước khi thao tác
tiếp. Không tự bấm lần hai cho cùng thư mục tập, kể cả sau khi mở lại Chrome hoặc đổi
full/nửa video. Nút **Xuất biên nhận đăng** trong nhật ký tải thông tin lần bấm;
biên nhận `uncertain` không có nghĩa là đăng thất bại.

Từ bản 0.5.12, có thể chủ động đăng lại: chọn đúng video, bật **Bấm Đăng / Lên lịch**
và **Cho phép đăng lại**, rồi bấm **Nạp & điền** trên trang tải mới hoặc **Điền tiếp**
trên bản nháp đang mở. Hộp xác nhận liệt kê các video đã có biên nhận và cảnh báo
có thể tạo bài trùng. Hủy thì không thao tác trên TikTok. Lựa chọn đăng lại chỉ dùng
cho lần chạy đó và tự tắt, không được lưu khi mở lại bảng. Nếu chỉ còn hộp thoại
**Đăng ngay** đúng video/lịch của lần trước, **Điền tiếp** thử lại bước xác nhận,
không nạp lại video hay bấm lại Lên lịch. Vẫn kiểm tra đúng bản nháp, hashtag,
ngày/giờ và tải success 100%. Biên nhận cũ không bị xóa: được giữ ở `previousAttempts`
trong bản xuất biên nhận khi thực sự bắt đầu lần bấm mới; lỗi trước đó giữ nguyên
biên nhận. Biên nhận thay đổi sau lúc xác nhận thì phải xác nhận lại.

Khi tắt **Đặt ngày giờ**, extension không thay đổi tùy chọn lịch đã có trên TikTok.
Nếu lịch đã bật sẵn, extension giữ nguyên, không bấm bật/tắt lần nữa.
Khi đồng thời yêu cầu đăng ngay, extension dừng nếu TikTok đang bật lịch, tránh
đăng bằng một lịch không được kiểm tra.
Bạn có thể làm việc ở tab hoặc ứng dụng khác; giữ Chrome và tab TikTok đang mở,
không để máy ngủ. Nút **Dừng** ngừng các thao tác tiếp theo, không hủy upload đã gửi
hoặc xóa bản nháp trên TikTok.

## Khả năng và giới hạn

- Đọc file qua đường dẫn tuyệt đối Windows, không sao chép video lớn qua bộ nhớ
  extension. Bộ quét Python chỉ đọc thư mục kịch bản đã cấu hình. Vẫn có thể thêm
  dòng bằng nút dấu cộng hoặc nhập JSON khi không chạy bộ quét.
- Mô tả được điền bằng `Input.insertText` trong tab và đọc lại để so sánh.
  Mỗi hashtag được nhập sau một dấu cách (kể cả hashtag đầu), chờ ít nhất 1 giây
  rồi gửi Enter trong tab qua CDP. Lần lượt làm hết hashtag rồi mới bật lịch.
  Con trỏ được chuyển bằng Ctrl+End và phím mũi tên trong chính tab để trình soạn
  thảo cập nhật vị trí, không đặt DOM Range vào token hashtag. Sau Enter chờ thêm
  để token ổn định, đọc lại toàn bộ hashtag đã nhập; hashtag mất được thử bổ sung
  một lượt trước khi chuyển tiếp. Không lặp sửa vô hạn hoặc bỏ qua hashtag còn thiếu.
  Bản 0.5.9 chờ ô mô tả và nội dung ổn định ít nhất 1 giây trước khi điền.
  Theo dõi cả phần tử nhập và mã `data-editor` của Draft: nếu TikTok tạo lại ô
  lúc khởi tạo video, chỉ thử điền lại toàn bộ một lần sau khi xác nhận vẫn là
  cùng video. Mỗi hashtag vẫn cách trước, chờ 1 giây rồi Enter và đọc lại.
  Nếu focus chuyển sang nút/ô khác, có hộp thoại, video đổi hoặc ô tiếp tục bị
  tạo lại, dừng. Không gửi Enter khi chưa xác nhận focus ở ô mô tả. Nội dung vẫn
  được đọc lại; nếu Enter chọn sai gợi ý làm đổi hashtag, dừng trước khi đăng.
- Kiểm tra riêng tiêu đề và hashtag, bỏ qua khác biệt khoảng trắng/ký tự zero-width
  do token tạo ra. Theo lựa chọn của người dùng, khi **cả Đặt ngày giờ và Bấm Đăng /
  Lên lịch đều bật**, tiêu đề lệch chỉ ghi cảnh báo và vẫn tiếp tục lên lịch/đăng.
  Thiếu/sai hashtag, bản nháp không xác định, ngày giờ sai hoặc tải chưa đủ 100%
  vẫn dừng. Nhật ký hoàn tất giữ lại cảnh báo tiêu đề, không báo đã xác minh khớp.
- Hỗ trợ radio `.Radio__innerCircle--checked-false/true`, bộ chọn giờ/phút
  `.tiktok-timepicker-left/right` và nút `[data-e2e="post_video_button"]` từ HTML
  TikTok đã cung cấp. Radio đã bật không bị bấm tắt. Ngày đã đúng được giữ nguyên.
  Bản 0.5.7 mở popup bằng khung chứa ô `.TUXFormField` trong `.scheduled-picker`,
  không dùng chuỗi selector dài có số thứ tự hoặc ép sửa ô readonly. Lịch
  `.calendar-wrapper` được đọc theo `.month-title`, `.year-title`, hàng thứ và
  toàn bộ lưới ngày; hỗ trợ tên tháng tiếng Việt như **Tháng Chín**. Chỉ chọn
  `.day.valid` của đúng tháng, không nhầm với ngày cùng số ở tháng trước/sau.
  Chuyển tháng tiến/lùi bằng mũi tên của popup, chờ tháng mới xuất hiện trước khi
  bấm tiếp. Ngày bị khóa, lịch không đổi hoặc đọc lại không khớp thì dừng.
  Chọn giờ rồi phút ở hai cột; nếu popup đóng sau chọn giờ, tự mở lại để chọn phút.
  Ngày và giờ đã đúng được giữ nguyên. Đọc lại ô ngày ngay sau chọn ngày, kiểm tra
  giờ sau chọn giờ, rồi xác nhận cả ngày/giờ trước nút Đăng / Lên lịch.
  Bản 0.5.8 không nhận radio **Bây giờ** hoặc checkbox/switch là ô nhập giờ.
  Popup còn lớp `.tiktok-timepicker-invisible` được coi là đóng, dù vẫn tồn tại
  trong DOM; extension phải mở popup rồi mới chọn giờ/phút.
- Không bấm Đăng/Lên lịch nếu thiếu thanh tiến trình, chưa đủ `100%`, chưa có
  `success` hoặc nút còn loading/disabled. Kiểm tra lại các điều kiện ngay lúc bấm.
- Chờ ô tải xuất hiện tối đa 30 giây, bỏ qua ô tải ảnh, tìm cả iframe TikTok và
  shadow DOM mở. Nếu chỉ có nút chọn file, chặn hộp thoại hệ điều hành rồi mở ô tải.
  Khi có nhiều ô video không phân biệt được, dừng thay vì chọn ngẫu nhiên.
- Giữ tham chiếu file ngay từ sự kiện chọn file, xác nhận tên/dung lượng và đọc
  thử một byte. Trang có thể xóa giá trị ô tải sau khi nhận file; trường hợp này
  không còn bị coi là mất file. File thực sự không tồn tại, rỗng hoặc không đọc
  được vẫn bị chặn, kèm đường dẫn trong lỗi. Đây là xác nhận file đã được đưa vào
  trang, không phải xác nhận TikTok đã tải hoặc đăng thành công.
- Bộ chọn lịch hỗ trợ ô nhập ngày/giờ chỉnh sửa được, lịch có ngày đầy đủ trong
  `data-date`/`aria-label`, một số lịch có tiêu đề tháng/năm và bánh xe giờ/phút có
  `role=listbox` / `role=option`. Đây không phải cam kết cho mọi phiên bản TikTok.
- Nếu giao diện chưa được nhận diện, extension dừng và báo lỗi. Mở bộ chọn đang
  gặp lỗi, bấm **Xuất chẩn đoán** để lấy `tiktok-dom.json` phục vụ điều chỉnh adapter.
  File này chứa nhãn, giá trị và cấu trúc các điều khiển đang hiển thị; kiểm tra nội
  dung trước khi chia sẻ. Không có cookie, mật khẩu hoặc nội dung lưu trữ tài khoản.
  Khi lỗi xảy ra, extension cũng cố lưu chẩn đoán ngay tại thời điểm lỗi. Bấm
  **Tải chẩn đoán lỗi gần nhất** trong nhật ký để lấy `tiktok-dom-error.json`.
  Chẩn đoán mô tả gồm nội dung/HTML, định danh ô, focus ở từng bước hashtag và ảnh chụp tab
  cùng phiên bản extension và các CSS selector tùy chỉnh của lần chạy lỗi.
  Ảnh chỉ được lưu khi Chrome cho phép, lấy tab TikTok được chọn qua CDP, không chụp màn hình
  ứng dụng khác. Kiểm tra nội dung trước khi chia sẻ file chẩn đoán.
- Mục **Bộ chọn phần tử** cho phép ghi đè CSS selector khi ô file, mô tả, tùy chọn
  lịch, ngày, giờ hoặc nút đăng không được nhận diện. Mỗi selector cần trỏ tới đúng
  một phần tử. Shadow DOM đóng và iframe từ miền ngoài TikTok chưa được hỗ trợ.
- Khi mất kết nối hoặc đóng Chrome, tác vụ không tự chạy tiếp. Kiểm tra bản nháp
  rồi dùng **Điền tiếp**. Gỡ extension sẽ xóa kho dữ liệu riêng; **Xuất danh sách**
  để giữ lại danh sách khi cần.

## Kiểm thử

Node chỉ cần cho người phát triển, không cần để sử dụng extension:

```powershell
cd 'D:\Python\omnivoice\OmniVoice\Desktop Automation\gptcode'
npm ci
npx playwright install chromium
npm test
python -m unittest discover -s tests -p "test_*.py"
```

Test mở extension thật trong Chromium với profile tạm, chặn mạng TikTok và thay
bằng trang mẫu. Kiểm tra nạp file CDP, iframe, shadow DOM, ô tải chậm, hashtag chờ 1 giây rồi Enter,
lịch đã bật, popup lịch/giờ từ HTML đã cung cấp, chuyển tháng tiến/lùi và qua năm,
ngày nhuận, ngày bị khóa, popup phản hồi chậm và giá trị không cập nhật,
đăng có lựa chọn, hàng đợi, chống bấm trùng, dừng tác vụ, cửa sổ riêng,
nhập danh sách và giao diện desktop/mobile. Không đăng gì lên tài khoản
thật. Cần kiểm thử bổ sung trên DOM TikTok đang đăng nhập trước khi dùng thường xuyên.

Các file `extension/vendor/lucide.js` và giấy phép đi kèm được đóng gói sẵn,
không tải JavaScript từ CDN khi chạy.

Tài liệu chính thức:

- https://developer.chrome.com/docs/extensions/reference/api/debugger
- https://developer.chrome.com/docs/extensions/reference/api/sidePanel
- https://chromedevtools.github.io/devtools-protocol/tot/DOM/#method-setFileInputFiles
- https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle
- https://developer.chrome.com/docs/extensions/develop/concepts/network-requests
