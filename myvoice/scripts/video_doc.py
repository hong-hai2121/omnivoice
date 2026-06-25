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

import io
import sys
import tempfile
from pathlib import Path

# Ép UTF-8 cho stdout/stderr khi chạy độc lập (guard cho trường hợp không có .buffer).
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

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
                    skip_existing=False) -> Path:
    """Dựng video DỌC 1080x1920 (không khung) từ một file audio. Trả về đường dẫn output.

    Ném RuntimeError nếu thiếu tài nguyên hoặc ffmpeg lỗi. `log` là hàm nhận chuỗi
    để ghi tiến trình (mặc định print; GUI truyền logging.info).

    effect: đường dẫn file hiệu ứng (.mov alpha trong scripts/hieuung/). None = bỏ qua.
    progress: hàm tùy chọn (pct, cur, total, speed) để cập nhật thanh tiến trình GUI
              thay cho việc spam % ra log (xem run_ffmpeg_progress).
    skip_existing: nếu True và video dọc đã tồn tại thì trả về luôn, KHÔNG dựng lại
                   (chế độ ♻ "chỉ dựng phần còn thiếu").
    """
    # Trả về sớm nếu đã có sẵn (chế độ dùng lại) — tránh dựng lại tốn thời gian.
    audio_file = Path(audio_file)
    output = audio_file.parent / (audio_file.stem + "_doc.mp4")
    if skip_existing and output.exists() and output.stat().st_size > 0:
        log(f"♻ Video dọc đã có → bỏ qua dựng lại: {output.name}")
        return output

    videos = sorted(VIDEO_DIR.glob("*.mp4"))
    if not videos:
        raise RuntimeError(f"Không có file .mp4 nào trong: {VIDEO_DIR}")

    if not audio_file.exists():
        raise RuntimeError(f"Không tìm thấy audio: {audio_file}")
    audio_dur = get_duration(audio_file)

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
            f"[bg][fx]overlay=0:0:shortest=0[out]"
        )
    else:
        filt = base + "[out]"

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
        # Inputs: 0=video(ghép)  [1=hiệu ứng]  cuối=audio
        cmd = ["ffmpeg", "-y", "-stream_loop", "-1",     # lặp video nền: không hết frame trước audio
               "-f", "concat", "-safe", "0", "-i", str(concat_list)]
        if effect:
            cmd += ["-stream_loop", "-1", "-i", str(effect)]   # input 1
        cmd += ["-i", str(audio_file)]                          # audio
        audio_idx = 2 if effect else 1
        cmd += [
            "-filter_complex", filt,
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
