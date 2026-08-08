# -*- coding: utf-8 -*-
"""
Cắt video YOUTUBE SHORT (≤ 2 phút 50) từ video TikTok đã dựng.

KHÔNG dựng lại video: chỉ cắt bớt phần đuôi của tiktok.mp4 bằng `ffmpeg -c copy`
nên xong gần như tức thì và giữ NGUYÊN chất lượng. Short vì thế thừa hưởng đúng
những gì bản TikTok đã có — khung dọc 1080x1920, chữ 'Mimi audio Số N', ảnh bìa ở
frame đầu, nhạc nền.

Điểm cắt lấy ở CUỐI CÂU: dò khoảng lặng (TTS luôn nghỉ giữa hai câu) gần mốc 2:50
nhất trong cửa sổ [2:20 – 2:50] — dùng đúng find_sentence_end_silence mà bước cắt
audio TikTok đang dùng, nên hai chỗ không thể lệch cách hiểu "hết câu". Không dò
được khoảng lặng nào thì cắt cứng ở 2:50, thà hụt nửa câu còn hơn không có short.

Vì sao 2:50 mà không phải 3:00: YouTube nhận Short khi video dọc và DƯỚI 3 phút —
sát mốc quá thì chỉ cần lệch vài frame là YouTube xếp thành video thường.

Cách dùng:
    python video_short.py <thư mục tập | file tiktok.mp4>
"""

import shutil
import subprocess
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from video_timclip import (ClipFinderError, CREATE_NO_WINDOW,  # noqa: E402
                          find_sentence_end_silence, probe_audio_duration)

SHORT_NAME = "short.mp4"     # tên file kết quả trong thư mục tập
MAX_SECONDS = 170.0          # 2 phút 50 — dưới mốc 3 phút của YouTube Shorts
SEARCH_BACK = 40.0           # dò khoảng lặng trong [MAX-40s, MAX]
SILENCE_DB = -35.0           # ngưỡng coi là im lặng (giống bước cắt audio TikTok)
# Thử lần lượt các mức "khoảng lặng dài bao nhiêu thì tính là hết câu". Bản TikTok
# thường được TĂNG TỐC (x1.05–x1.10) nên khoảng nghỉ giữa hai câu co lại theo —
# 0.5s như bước cắt audio là quá chặt, nhiều tập không ra mốc nào.
MIN_SILENCES = (0.35, 0.2)


def _fmt(seconds: float) -> str:
    m, s = divmod(float(seconds), 60)
    return f"{int(m)}:{s:05.2f}"


def find_voice_audio(video: Path, log=print):
    """File audio GIỌNG (chưa trộn nhạc nền) cùng nhịp với video, hoặc None.

    Video TikTok có nhạc nền thì tiếng nhạc chạy suốt, dò khoảng lặng trên chính
    video sẽ KHÔNG ra mốc nào (nhạc mix chỉ dưới giọng ~12dB, không phải im lặng).
    Bản giọng trước khi trộn vẫn nằm trong thư mục tập và DÀI ĐÚNG BẰNG video (trộn
    nhạc không đổi thời lượng), nên nhận ra nó bằng thời lượng là chắc nhất — khỏi
    phụ thuộc đuôi tên vốn đổi theo mức tăng tốc (output_tiktok_sped110.wav…).
    """
    try:
        muc_tieu = probe_audio_duration(video)
    except ClipFinderError:
        return None
    ung_vien = []
    for wav in video.parent.glob("*.wav"):
        if "bgm" in wav.name.lower():        # chính là bản ĐÃ trộn nhạc
            continue
        try:
            if abs(probe_audio_duration(wav) - muc_tieu) <= 0.5:
                ung_vien.append(wav)
        except ClipFinderError:
            continue
    if not ung_vien:
        return None
    # Nhiều file cùng khớp → ưu tiên bản dành riêng cho TikTok.
    ung_vien.sort(key=lambda p: (0 if "tiktok" in p.name.lower() else 1, p.name))
    log(f"[short] Dò điểm cắt trên audio giọng: {ung_vien[0].name}")
    return ung_vien[0]


def find_cut_point(video: Path, voice_audio=None, max_seconds: float = MAX_SECONDS,
                   log=print) -> float:
    """Giây nên cắt: cuối câu gần mốc max_seconds nhất; dò hỏng → chính max_seconds."""
    nguon = Path(voice_audio) if voice_audio else (find_voice_audio(video, log=log) or video)
    target_min = max_seconds / 60.0
    min_min = max(0.05, (max_seconds - SEARCH_BACK) / 60.0)
    loi = None
    for min_silence in MIN_SILENCES:
        try:
            cut, _ = find_sentence_end_silence(
                nguon, target_minutes=target_min, min_minutes=min_min,
                max_minutes=target_min, silence_db=SILENCE_DB, min_silence=min_silence)
            return cut
        except (ClipFinderError, OSError) as e:
            loi = e
    log(f"[short] Không tìm được khoảng lặng cuối câu ({loi}) → cắt thẳng ở {_fmt(max_seconds)}.")
    return max_seconds


def build_short(tiktok_video, output=None, *, voice_audio=None,
                max_seconds: float = MAX_SECONDS,
                skip_existing: bool = False, log=print) -> Path:
    """Cắt tiktok_video thành short ≤ max_seconds. Trả về đường dẫn short.

    voice_audio: audio GIỌNG cùng nhịp với video (chưa trộn nhạc nền) để dò điểm
        cắt cuối câu. None → tự tìm trong thư mục, xem find_voice_audio.

    Ném RuntimeError nếu thiếu video nguồn hoặc ffmpeg cắt lỗi.
    tiktok_video ngắn sẵn → copy nguyên (short vẫn phải là file riêng vì bản TikTok
    sẽ bị đổi tên sau khi đăng).
    """
    src = Path(tiktok_video)
    out = Path(output) if output else src.with_name(SHORT_NAME)

    if skip_existing and out.exists() and out.stat().st_size > 0:
        log(f"♻ Video Short đã có → bỏ qua cắt lại: {out.name}")
        return out
    if not src.is_file() or src.stat().st_size == 0:
        raise RuntimeError(f"Không có video TikTok để cắt Short: {src}")

    try:
        duration = probe_audio_duration(src)
    except ClipFinderError as e:
        raise RuntimeError(f"Không đọc được thời lượng {src.name}: {e}") from e

    if duration <= max_seconds:
        log(f"[short] {src.name} chỉ {_fmt(duration)} (≤ {_fmt(max_seconds)}) → dùng nguyên.")
        shutil.copy2(src, out)
        return out

    cut = find_cut_point(src, voice_audio, max_seconds, log=log)
    res = subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-i", str(src), "-t", f"{cut:.3f}", "-c", "copy",
         "-movflags", "+faststart", str(out)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=CREATE_NO_WINDOW)
    if res.returncode != 0 or not out.exists() or out.stat().st_size == 0:
        raise RuntimeError(f"ffmpeg cắt Short lỗi: {res.stderr.strip().splitlines()[-1:]}")

    # `-c copy` cắt ở frame gần nhất nên độ dài thật lệch vài phần trăm giây so với
    # điểm cắt — đọc lại để chắc chắn vẫn dưới mốc 3 phút của YouTube.
    try:
        thuc = probe_audio_duration(out)
    except ClipFinderError:
        thuc = cut
    log(f"✂ Short: cắt {src.name} tại {_fmt(cut)} "
        f"(gốc {_fmt(duration)}) → {out.name} [{_fmt(thuc)}]")
    return out


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    arg = Path(sys.argv[1])
    src = arg / "tiktok.mp4" if arg.is_dir() else arg
    if not src.is_file():
        # Sau khi đăng, tiktok.mp4 đã đổi tên theo tiêu đề SEO (xem dang_tap_youtube).
        cands = sorted(p for p in src.parent.glob("*.mp4")
                       if p.name.lower().startswith(("tiktok", "full ở")))
        if not cands:
            print(f"Không tìm thấy video TikTok trong {src.parent}")
            return 2
        src = cands[0]
    try:
        build_short(src)
    except RuntimeError as e:
        print(f"Lỗi: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
