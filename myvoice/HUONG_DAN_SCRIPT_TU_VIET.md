# Hướng dẫn các script tự viết thêm trong OmniVoice

> Toàn bộ phần **tự viết thêm** để tạo video lồng giọng nằm gọn trong thư mục
> `myvoice/`, **tách riêng** khỏi package lõi `omnivoice/` (model, training, cli...) của GitHub.
>
> Cập nhật: 14/06/2026

---

## Cấu trúc thư mục

```
OmniVoice/                 ← repo gốc GitHub (omnivoice/, docs/, venv/, pyproject.toml...)
└── myvoice/               ← TẤT CẢ phần tự viết
    ├── scripts/           ← mã nguồn
    │   ├── clone_gui.py
    │   ├── clone.py
    │   ├── check_audio_spikes.py
    │   ├── remove_audio.py
    │   ├── make_final_video.py
    │   └── frame_video.py
    ├── HUONG_DAN_SCRIPT_TU_VIET.md   (file này)
    ├── voice/             ← file giọng mẫu
    ├── kịch_bản/          ← input.txt, output.wav, output_chunks/, final_video.mp4
    ├── Backbround/        ← khung trang trí (Khung0/khung1/khung3.png)
    ├── mp4/               ← video nguồn (có tiếng) cho remove_audio.py
    ├── mp4_no_audio/      ← video đã xóa tiếng (remove_audio.py tạo ra)
    ├── videodoc/          ← video dọc 0.mp4, 1.mp4...
    └── videongang/        ← video ngang
```

> Các script tính đường dẫn theo vị trí file (lùi 2 cấp tới `myvoice/`), nên chạy từ
> đâu cũng được. Hai script TTS (`clone.py`, `clone_gui.py`) tự thêm gốc repo vào
> `sys.path` để `import omnivoice`.

**Chạy** (từ gốc repo `OmniVoice/`):

```
venv\Scripts\python myvoice\scripts\clone_gui.py
venv\Scripts\python myvoice\scripts\frame_video.py
```

---

## Quy trình tổng quát

```
input.txt  ──(clone_gui.py / clone.py)──►  output.wav + output_chunks/*.wav
                                              │
                            check_audio_spikes.py  (kiểm tra chunk lỗi)
                                              │
mp4_no_audio/*.mp4  ──(make_final_video.py)──►  kịch_bản/final_video.mp4
                       (ghép video + output.wav làm nhạc nền)
```

Tất cả dùng chung thư mục `kịch_bản/` (script đầu vào, audio, video kết quả) và `voice/` (file giọng mẫu).

---

## Chi tiết từng file

### `clone_gui.py` — Giao diện chính (khuyên dùng)
**Chạy:** `python clone_gui.py`

App desktop (Tkinter) để chuyển văn bản → giọng nói bằng model **OmniVoice**. Tính năng:

- **3 chế độ:**
  - 🎙 **Clone** — nhái theo file giọng mẫu trong `voice/`.
  - 🎨 **Thiết kế (design)** — mô tả giọng qua dropdown (giới tính, tuổi, âm điệu, giọng vùng/phương ngữ — hỗ trợ Anh & Trung) → tự ghép thành "lệnh model".
  - 🔊 **Mặc định** — model tự chọn giọng.
- **Tách văn bản** thành các đoạn (chunk) theo dấu câu, độ dài chỉnh được (mặc định 300 ký tự — nhỏ hơn = nhẹ GPU hơn). Tự làm sạch text (`clean_text`).
- **Lưu tiến trình từng chunk** vào `output_chunks/` → chạy lại sẽ bỏ qua chunk đã có (resume được). Nút **Tạm dừng / Tiếp tục** và **Xóa chunks**.
- **Tự phát hiện & render lại chunk lỗi spike** (âm thanh to bất thường / gần im lặng) sau khi generate.
- **Ghép chunk** với crossfade ngắn để tránh tiếng "click" ở ranh giới → xuất `output.wav`.
- Tự khởi động lại bằng Python trong `venv/` nếu có.

> Cần `sv_ttk` (tùy chọn, cho theme tối), `torch`, `soundfile`, `numpy` và package `omnivoice`.

### `clone.py` — Phiên bản dòng lệnh (không GUI)
**Chạy:** `python clone.py` (chỉnh phần `CẤU HÌNH` ở đầu file trước)

Bản script đơn giản của `clone_gui.py`, chỉ chế độ **clone**:

- Cấu hình ở đầu file: `REF_AUDIO` (giọng mẫu trong `voice/`), `TEXT_FILE` (`kịch_bản/input.txt`), `OUTPUT`, `CHUNK_SIZE` — nay tính theo `myvoice/` nên không cần sửa khi đổi máy.
- `preprocess_text()` xử lý mạnh hơn GUI: gộp dòng vụn, xóa URL / ghi chú nguồn / markdown, đổi số mục đứng riêng (`1`, `2`...) thành "Phần một", "Phần hai"..., cảnh báo nếu còn ký tự tiếng Trung.
- Tách chunk, generate từng đoạn (resume qua `output_chunks/`), rồi ghép thẳng (nối đơn giản, không crossfade) → `OUTPUT`.

> Dùng khi muốn chạy nhanh/tự động không cần giao diện.

### `check_audio_spikes.py` — Kiểm tra chunk audio lỗi
**Chạy:** `python check_audio_spikes.py`

Quét toàn bộ `kịch_bản/output_chunks/*.wav`, phát hiện file lỗi:

- Chia mỗi file thành khung 50ms, tính RMS, tìm khung vượt **5× RMS trung vị** → **spike** (tiếng lạ to).
- File có RMS trung vị quá thấp → **gần im lặng** (model sinh toàn noise).
- In bảng trạng thái từng file + kèm text gốc (đọc từ `input_preview.txt`), liệt kê file lỗi để bạn xóa và generate lại.

> Là công cụ chẩn đoán độc lập; `clone_gui.py` đã tích hợp sẵn cơ chế tương tự nên thường chỉ cần khi muốn kiểm tra thủ công.

### `make_final_video.py` — Ghép video cuối + nhạc nền
**Chạy:** `python make_final_video.py` (cần **ffmpeg/ffprobe** trong PATH)

- Ghép tất cả video trong `mp4_no_audio/` (đặt tên `0.mp4, 1.mp4, ...`) theo thứ tự số, dùng **concat demuxer** của ffmpeg (copy video, **không re-encode** → rất nhanh).
- Lấy `kịch_bản/output.wav` làm nhạc nền, **cắt vừa khít** tổng thời lượng video và **fade-out 3 giây** cuối.
- Xuất `kịch_bản/final_video.mp4`, in thời lượng & dung lượng.

### `remove_audio.py` — Xóa tiếng + scale video nguồn
**Chạy:** `python remove_audio.py` (cần **ffmpeg** trong PATH)

- Duyệt mọi `.mp4` trong `mp4/`, xóa âm thanh và scale về 1080p dọc (`scale=1080:-2`).
- Lưu sang `mp4_no_audio/` giữ nguyên tên file (đầu vào cho `make_final_video.py`).

### `frame_video.py` — Lồng video vào bộ khung trang trí
**Chạy:** `python frame_video.py` (cần **ffmpeg/ffprobe** trong PATH; cần `scipy`, `Pillow`, `numpy`)

- Xếp 3 lớp trong `Backbround/`: `Khung0.png` (nền) → video → `khung1.png` (viền) → `khung3.png` (trang trí).
- Dò vùng trong khung từ `khung1.png` và dựng **mặt nạ bo góc** (scipy) để 4 góc video không thò ra ngoài góc bo.
- `MODE="fill"` (phủ kín, cắt thừa) hoặc `"fit"` (hiện trọn, có lề). Giữ nguyên audio gốc.
- Đầu vào `videongang/<tên>.mp4` → đầu ra `<tên>_khung.mp4` cùng thư mục.

---

## Ghi chú

- **Thứ tự dùng điển hình:** soạn `kịch_bản/input.txt` → chạy `clone_gui.py` tạo `output.wav` → (tùy chọn) `check_audio_spikes.py` → bỏ video nguồn vào `mp4/` → `remove_audio.py` → `make_final_video.py`.
- **Phụ thuộc:** package `omnivoice` (model `k2-fsa/OmniVoice` tải qua HuggingFace, chạy `torch.float16` trên GPU nếu có), `soundfile`, `numpy`, `scipy`, `Pillow`, `ffmpeg`.
- **Đường dẫn:** mọi script tính theo vị trí file (`Path(__file__).resolve().parent.parent` = `myvoice/`) nên không cần sửa khi đổi máy, miễn giữ nguyên cấu trúc `myvoice/scripts/`.
