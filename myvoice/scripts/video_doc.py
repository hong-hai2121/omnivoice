"""
Dựng video DỌC (9:16, 1080x1920) từ audio — KHÔNG dùng khung trang trí.

Khác với video_khung.py (video NGANG có khung Khung0/khung1/khung2): bản dọc chỉ
ghép RANDOM các clip trong videodoc/ cho đủ thời lượng audio, scale + cắt giữa về
đúng khung dọc rồi mux audio. Không có lớp khung nào.

  - Lấy thời lượng từ file audio làm thời lượng đích.
  - Ghép random video trong videodoc/ (lặp tới khi đủ).
  - Scale "fill" + crop giữa về 1080x1920 (không méo, không viền đen).
  - (Tùy chọn) phủ hiệu ứng .mov alpha trong scripts/hieuung/.
  - Mux audio gốc, cắt video đúng độ dài audio (-t).

Đầu ra:  kịch_bản/<tên_audio>_doc.mp4

Cách dùng:
    python video_doc.py
"""

import sys
import tempfile
from pathlib import Path

# Ép UTF-8 cho stdout/stderr. Dùng reconfigure() (đổi tại chỗ) thay vì bọc
# TextIOWrapper mới: bọc thêm wrapper sẽ khiến wrapper trung gian bị GC đóng luôn
# buffer dùng chung → "I/O operation on closed file" (xem chú thích ở video_khung).
for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream is not None:
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

# Cho phép import video_khung (dùng chung helper) khi chạy từ thư mục con.
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

# Tái dùng các tiện ích đã có của bản ngang (đọc thời lượng, dò NVENC, ghép playlist, tìm audio).
from video_khung import (get_duration, has_nvenc, build_playlist, find_audio,
                         run_ffmpeg_progress)

BASE_DIR   = Path(__file__).resolve().parent.parent   # myvoice/
VIDEO_DIR  = BASE_DIR / "videodoc"     # kho video DỌC để ghép random
SCRIPT_DIR = BASE_DIR / "kịch_bản"     # nơi chứa audio + xuất video

OUT_W, OUT_H = 1080, 1920   # khung dọc 9:16

# Ưu tiên GPU (NVENC), tự fallback CPU (libx264) nếu GPU lỗi.
USE_GPU  = True
NVENC_CQ = 18
X264_CRF = 18


def build_video_doc(audio_file: Path, *, log=print, effect=None, progress=None,
                    skip_existing=False, source_video=None, source_dir=None,
                    output: Path | None = None,
                    caption_png: Path | None = None,
                    caption_pulse_period: float = 300.0) -> Path:
    """Dựng video DỌC 1080x1920 (không khung) từ một file audio. Trả về đường dẫn output.

    Ném RuntimeError nếu thiếu tài nguyên hoặc ffmpeg lỗi. `log` là hàm nhận chuỗi
    để ghi tiến trình (mặc định print; GUI truyền logging.info).

    effect: đường dẫn file hiệu ứng (.mov alpha trong scripts/hieuung/). None = bỏ qua.
    progress: hàm tùy chọn (pct, cur, total, speed) để cập nhật thanh tiến trình GUI
              thay cho việc spam % ra log (xem run_ffmpeg_progress).
    skip_existing: nếu True và video dọc đã tồn tại thì trả về luôn, KHÔNG dựng lại
                   (chế độ ♻ "chỉ dựng phần còn thiếu").
    source_video: nếu có → DÙNG LẠI video này (vd video ngang đã dựng) làm nguồn:
                  phóng to "fill" cho khớp chiều cao khung dọc rồi cắt giữa, thay
                  âm bằng audio_file. Khi đó BỎ QUA kho videodoc/ và hiệu ứng (video
                  nguồn đã có sẵn khung/hiệu ứng).
    source_dir: thư mục chứa clip để ghép random (thay cho kho videodoc/ mặc định).
                Dùng khi muốn lấy nguồn từ 1 thư mục con của videodoc/ (vd theo chủ đề).
                Bỏ qua nếu đã truyền source_video. None → dùng videodoc/ như cũ.
    output: đường dẫn video kết quả tùy chọn. None (mặc định) → đặt cạnh audio với
            tên <tên_audio>_doc.mp4. Truyền vào để đặt tên riêng (vd facebook.mp4);
            skip_existing khi đó kiểm tra ĐÚNG file này nên vẫn "chỉ dựng phần còn thiếu".
    caption_png: ảnh PNG TRONG SUỐT kích thước đúng khung dọc (1080x1920), đã vẽ sẵn
            chữ ở vị trí mong muốn → phủ (overlay) lên trên cùng video. None = không.
            Truyền qua -i (không dính escaping filtergraph nên chữ tiếng Việt an toàn).
    caption_pulse_period: chu kỳ (giây) của hiệu ứng HÚT MẮT — cứ mỗi chu kỳ, chữ
            NẢY lên ~70px trong 1.2s rồi về chỗ (mặc định 300 = mỗi 5 phút 1 lần).
            ≤ 0 → chữ đứng yên, không nảy. Chỉ áp dụng khi có caption_png.
    """
    # Trả về sớm nếu đã có sẵn (chế độ dùng lại) — tránh dựng lại tốn thời gian.
    audio_file = Path(audio_file)
    output = Path(output) if output else audio_file.parent / (audio_file.stem + "_doc.mp4")
    if skip_existing and output.exists() and output.stat().st_size > 0:
        log(f"♻ Video dọc đã có → bỏ qua dựng lại: {output.name}")
        return output

    if not audio_file.exists():
        raise RuntimeError(f"Không tìm thấy audio: {audio_file}")
    audio_dur = get_duration(audio_file)

    # Ảnh chữ overlay (tùy chọn). Video base kết ở nhãn [vid] khi có caption để phủ
    # thêm 1 lớp overlay; không có thì kết thẳng ở [out].
    caption_png = Path(caption_png) if caption_png else None
    if caption_png and not caption_png.exists():
        log(f"[Cảnh báo] Không tìm thấy ảnh chữ overlay, bỏ qua: {caption_png}")
        caption_png = None
    has_caption = caption_png is not None
    vend = "[vid]" if has_caption else "[out]"

    reuse_ngang = source_video is not None
    if reuse_ngang:
        # ── DÙNG LẠI VIDEO NGANG: phóng to khớp chiều cao dọc + cắt giữa ──────
        source_video = Path(source_video)
        if not source_video.exists():
            raise RuntimeError(f"Không tìm thấy video ngang để dùng lại: {source_video}")
        if effect:
            log("ℹ Dùng lại video ngang → bỏ qua hiệu ứng (video nguồn đã có sẵn).")
        log(f"Khung dọc  : {OUT_W}x{OUT_H} (dùng lại video ngang, phóng to khớp chiều cao)")
        log(f"Video nguồn: {source_video.name}")
        log(f"Audio      : {audio_file.name}  ({audio_dur:.2f}s)")
        log(f"Đầu ra     : {output}")
        # Scale "fill" cho khớp chiều cao 1920 rồi cắt giữa về 1080 (như bản random).
        filt = (
            f"[0:v]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,"
            f"crop={OUT_W}:{OUT_H},setsar=1" + vend
        )
        concat_list = None
    else:
        video_dir = Path(source_dir) if source_dir else VIDEO_DIR
        videos = sorted(video_dir.glob("*.mp4"))
        if not videos:
            raise RuntimeError(f"Không có file .mp4 nào trong: {video_dir}")

        effect = Path(effect) if effect else None
        if effect and not effect.exists():
            log(f"[Cảnh báo] Không tìm thấy file hiệu ứng, bỏ qua: {effect}")
            effect = None

        # Ghép random tới khi đủ thời lượng audio
        durations = {v: get_duration(v) for v in videos}
        seq, total = build_playlist(videos, durations, audio_dur)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt",
                                         delete=False, encoding="utf-8") as f:
            concat_list = Path(f.name)
            for v in seq:
                f.write(f"file '{v.as_posix()}'\n")

        log(f"Khung dọc  : {OUT_W}x{OUT_H} (KHÔNG khung)")
        log(f"Nguồn clip : {video_dir}")
        log(f"Audio      : {audio_file.name}  ({audio_dur:.2f}s)")
        log(f"Kho video  : {len(videos)} clip -> ghép {len(seq)} đoạn ({total:.2f}s)")
        log(f"Hiệu ứng   : {effect.name if effect else '(không)'}")
        log(f"Đầu ra     : {output}")

        # Scale "fill" + cắt giữa về đúng khung dọc (không méo, không viền đen).
        base = (
            f"[0:v]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,"
            f"crop={OUT_W}:{OUT_H},setsar=1"
        )
        if effect:
            # Hiệu ứng scale phủ kín khung dọc rồi overlay lên video nền.
            filt = (
                base + "[bg];"
                f"[1:v]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,"
                f"crop={OUT_W}:{OUT_H},format=rgba[fx];"
                f"[bg][fx]overlay=0:0:shortest=0" + vend
            )
        else:
            filt = base + vend

    def build_cmd(gpu):
        if gpu:
            codec = [
                "-c:v", "h264_nvenc",
                "-preset", "p5",        # cân bằng tốc độ/chất lượng (p7 chậm nhất; p5 nhanh hơn nhiều, mắt thường gần như không phân biệt)
                "-tune", "hq",
                "-rc", "vbr", "-cq", str(NVENC_CQ), "-b:v", "0", "-profile:v", "high",
            ]
        else:
            codec = [
                "-c:v", "libx264", "-preset", "slow",
                "-crf", str(X264_CRF), "-profile:v", "high",
            ]
        if reuse_ngang:
            # Inputs: 0=video ngang (lặp nếu ngắn hơn audio)  1=audio
            cmd = ["ffmpeg", "-y", "-stream_loop", "-1", "-i", str(source_video),
                   "-i", str(audio_file)]
            audio_idx = 1
        else:
            # Inputs: 0=video(ghép)  [1=hiệu ứng]  cuối=audio
            cmd = ["ffmpeg", "-y", "-stream_loop", "-1",     # lặp video nền: không hết frame trước audio
                   "-f", "concat", "-safe", "0", "-i", str(concat_list)]
            if effect:
                cmd += ["-stream_loop", "-1", "-i", str(effect)]   # input 1
            cmd += ["-i", str(audio_file)]                          # audio
            audio_idx = 2 if effect else 1
        # Ảnh chữ caption: input tĩnh (lặp 1 frame) → overlay lên trên cùng → [out].
        full_filt = filt
        if has_caption:
            cmd += ["-loop", "1", "-i", str(caption_png)]           # sau audio
            cap_idx = audio_idx + 1
            if caption_pulse_period and caption_pulse_period > 0:
                P = caption_pulse_period
                # HÚT MẮT: mỗi P giây, chữ NẢY lên ~70px trong 1.2s rồi về (dấu phẩy
                # trong biểu thức phải escape \, vì filtergraph dùng , tách filter).
                yexpr = f"-70*sin(PI*mod(t\\,{P:g})/1.2)*lt(mod(t\\,{P:g})\\,1.2)"
                ov = f"overlay=x=0:y={yexpr}"
            else:
                ov = "overlay=0:0"
            full_filt = filt + f";[vid][{cap_idx}:v]{ov}[out]"
        cmd += [
            "-filter_complex", full_filt,
            "-map", "[out]",
            "-map", f"{audio_idx}:a",
            "-t", f"{audio_dur:.6f}",            # cắt video đúng bằng độ dài audio
            *codec,
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            str(output),
        ]
        return cmd

    use_gpu = USE_GPU and has_nvenc()
    log("Đang dựng video dọc... (GPU - h264_nvenc)" if use_gpu
        else "Đang dựng video dọc... (CPU - libx264)")
    rc, err_tail = run_ffmpeg_progress(build_cmd(use_gpu), audio_dur, log,
                                       label="Dựng video dọc", progress=progress)
    if rc != 0 and use_gpu:
        log("GPU lỗi, chuyển sang CPU (libx264)...")
        rc, err_tail = run_ffmpeg_progress(build_cmd(False), audio_dur, log,
                                           label="Dựng video dọc", progress=progress)
    # Dọn file tạm — bỏ qua nếu Windows còn khóa (không để rớt cả lượt dựng đã xong).
    if concat_list is not None:
        try:
            concat_list.unlink(missing_ok=True)
        except OSError:
            pass
    if rc != 0:
        raise RuntimeError(f"ffmpeg lỗi:\n{err_tail}")

    final_dur = get_duration(output)
    size_mb   = output.stat().st_size / 1024 / 1024
    log(f"Hoàn tất! Thời lượng {final_dur:.2f}s — {size_mb:.1f} MB — {output}")
    return output


def main():
    audio_file = find_audio()
    try:
        build_video_doc(audio_file)
    except Exception as e:
        print(f"[LỖI] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
