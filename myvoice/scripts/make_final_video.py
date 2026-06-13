"""
Ghép tất cả video trong mp4_no_audio/ (0.mp4, 1.mp4, ...) theo thứ tự,
lấy output.wav làm nhạc nền, xuất ra kịch_bản/final_video.mp4

- Video nối liền nhau theo số thứ tự
- Audio được cắt vừa khít tổng thời lượng video, fade-out 3 giây cuối
- Không re-encode video (copy), chỉ encode audio
"""

import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

BASE_DIR   = Path(__file__).resolve().parent.parent   # myvoice/
VIDEO_DIR  = BASE_DIR / "mp4_no_audio"
AUDIO_FILE = BASE_DIR / "kịch_bản" / "output.wav"
OUTPUT     = BASE_DIR / "kịch_bản" / "final_video.mp4"
FADE_OUT   = 3.0  # giây fade-out cuối audio


def get_duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", str(path)],
        capture_output=True, text=True,
    )
    return float(json.loads(r.stdout)["format"]["duration"])


def main():
    # Lấy danh sách video theo thứ tự số
    videos = sorted(VIDEO_DIR.glob("*.mp4"), key=lambda x: int(x.stem))
    if not videos:
        print("[LỖI] Không có file .mp4 trong mp4_no_audio/")
        sys.exit(1)
    if not AUDIO_FILE.exists():
        print(f"[LỖI] Không tìm thấy: {AUDIO_FILE}")
        sys.exit(1)

    print(f"Số video : {len(videos)}")

    total_video = sum(get_duration(v) for v in videos)
    audio_dur   = get_duration(AUDIO_FILE)
    print(f"Tổng video: {total_video:.2f}s")
    print(f"Audio     : {audio_dur:.2f}s")
    print(f"Fade-out  : {FADE_OUT}s cuối")
    print(f"Đầu ra    : {OUTPUT}\n")

    # Tạo file danh sách cho ffmpeg concat demuxer
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt",
                                     delete=False, encoding="utf-8") as f:
        concat_list = Path(f.name)
        for v in videos:
            f.write(f"file '{v.as_posix()}'\n")

    print("Bước 1/2 — Ghép video + gắn audio...")

    # Audio filter: trim vừa khít video + fade-out cuối
    fade_start = max(0.0, total_video - FADE_OUT)
    audio_filter = (
        f"atrim=duration={total_video:.6f},"
        f"afade=t=out:st={fade_start:.6f}:d={FADE_OUT}"
    )

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_list),
        "-i", str(AUDIO_FILE),
        "-c:v", "copy",           # copy video — không re-encode, nhanh
        "-af", audio_filter,
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(OUTPUT),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    concat_list.unlink(missing_ok=True)

    if result.returncode != 0:
        print(f"[LỖI ffmpeg]\n{result.stderr[-800:]}", file=sys.stderr)
        sys.exit(1)

    final_dur = get_duration(OUTPUT)
    size_mb   = OUTPUT.stat().st_size / 1024 / 1024
    print(f"\nHoàn tất!")
    print(f"  Thời lượng : {final_dur:.2f}s  ({final_dur/60:.1f} phút)")
    print(f"  Dung lượng : {size_mb:.1f} MB")
    print(f"  Kết quả    : {OUTPUT}")


if __name__ == "__main__":
    main()
