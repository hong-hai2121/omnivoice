# -*- coding: utf-8 -*-
"""
Gắn phụ đề (sub) vào video — dùng ĐÚNG chữ từ file kịch bản gốc, căn thời gian theo audio.

Ý tưởng:
  1. Đọc văn bản gốc (vd kịch_bản/input.txt) → cắt thành các "cue" phụ đề ngắn.
  2. Dùng faster-whisper nghe audio (tiếng Việt, word-level timestamps) để biết mỗi
     TỪ vang lên vào lúc nào.
  3. Khớp (align) chuỗi từ gốc với chuỗi từ Whisper → suy ra mốc giờ bắt đầu/kết thúc
     cho từng cue. Chữ hiển thị là chữ GỐC (không dùng chữ Whisper nhận ra), nên
     chính xác 100%; Whisper chỉ dùng để lấy mốc thời gian.
  4. Xuất file .srt rồi MUX (nhúng mềm) vào mp4 bằng ffmpeg — không render lại hình,
     player có thể bật/tắt phụ đề.

Cách dùng:
    # mặc định: audio tách từ video, kịch bản = ../kịch_bản/input.txt
    python gan_sub_video.py "duong_dan/output_videodone.mp4"

    # chỉ rõ audio + kịch bản + nơi lưu
    python gan_sub_video.py "output_videodone.mp4" --audio "output3.wav" \
        --script "../kịch_bản/input.txt" --out "output_sub.mp4"

Yêu cầu:
    pip install faster-whisper
    ffmpeg + ffprobe trong PATH.
"""

import argparse
import difflib
import os
import re
import subprocess
import sys
from pathlib import Path

# Console Windows in được tiếng Việt
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# Tái dùng hạ tầng Whisper sẵn có (nạp model từ cache local, không gọi mạng)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nhan_dien_audio_tieng_trung import (  # noqa: E402
    extract_audio,
    get_audio_duration,
    get_model,
)

SCRIPT_DIR = Path(__file__).resolve().parent
# input.txt nằm ở myvoice/kịch_bản/
DEFAULT_SCRIPT = SCRIPT_DIR.parent / "kịch_bản" / "input.txt"

AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma"}

# Tách câu: sau dấu kết câu (. ! ? …) và khoảng trắng theo sau.
_SENT_SPLIT = re.compile(r"(?<=[.!?…])\s+")
# Token để KHỚP: \w (có Unicode) bắt được chữ Việt có dấu, số, và cả chữ Hán lẫn vào.
_WORD_RE = re.compile(r"\w+", re.UNICODE)


def norm_tokens(text: str):
    """Tách văn bản thành danh sách token thường-hoá (chữ thường, bỏ dấu câu)."""
    return _WORD_RE.findall(text.lower())


# ----------------------------------------------------------------------------- #
# 1) Cắt văn bản gốc thành các cue phụ đề ngắn
# ----------------------------------------------------------------------------- #
def wrap_sentence(sentence: str, max_chars: int):
    """Cắt 1 câu dài thành nhiều mẩu ≤ max_chars, luôn cắt ở ranh giới từ."""
    words = sentence.split()
    pieces, cur = [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > max_chars:
            pieces.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        pieces.append(cur)
    return pieces


def build_cues(text: str, max_chars: int):
    """Trả về danh sách cue (chuỗi hiển thị) từ văn bản gốc.

    Mỗi dòng không rỗng = 1 đoạn; tách đoạn thành câu; câu quá dài thì cắt theo từ.
    Giữ NGUYÊN chữ gốc (kể cả hoa/thường, dấu câu) để hiển thị.
    """
    cues = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        for sentence in _SENT_SPLIT.split(line):
            sentence = sentence.strip()
            if not sentence:
                continue
            if len(sentence) <= max_chars:
                cues.append(sentence)
            else:
                cues.extend(wrap_sentence(sentence, max_chars))
    return cues


# ----------------------------------------------------------------------------- #
# 2) Nghe audio → danh sách từ kèm mốc giờ
# ----------------------------------------------------------------------------- #
_TRANSCRIBE_OPTS = dict(
    language="vi",
    word_timestamps=True,        # cần mốc giờ TỪNG TỪ để căn sub
    condition_on_previous_text=False,
    temperature=0,
    beam_size=5,
    vad_filter=True,
    vad_parameters=dict(min_silence_duration_ms=400),
)


def transcribe_words(audio_path, model_name="medium", on_progress=None):
    """Nghe audio, trả về (words, starts, ends): 3 list song song.

    words[i] là token thường-hoá của từ thứ i; starts/ends là mốc giờ (giây).
    """
    # Dùng model thường (không batched) để word_timestamps ổn định.
    model, _batched, _device = get_model(model_name, use_batched=False)
    duration = get_audio_duration(audio_path) or 0
    print("📝 Đang nghe audio để lấy mốc thời gian (tiếng Việt)...")
    segments, info = model.transcribe(audio_path, **_TRANSCRIBE_OPTS)
    total = duration or float(getattr(info, "duration", 0) or 0)

    words, starts, ends = [], [], []
    for seg in segments:
        for w in (seg.words or []):
            tok = norm_tokens(w.word)
            if not tok:
                continue
            # Một "từ" Whisper hiếm khi gồm nhiều token; nếu có, chia đều mốc giờ.
            n = len(tok)
            span = (w.end - w.start) / n if n else 0
            for k, t in enumerate(tok):
                words.append(t)
                starts.append(w.start + k * span)
                ends.append(w.start + (k + 1) * span)
        if on_progress and total:
            on_progress(min(seg.end / total, 1.0))
    return words, starts, ends


# ----------------------------------------------------------------------------- #
# 3) Khớp từ gốc ↔ từ Whisper → mốc giờ cho từng cue
# ----------------------------------------------------------------------------- #
def align_cues(cues, w_words, w_starts, w_ends, audio_dur):
    """Gán (start, end) cho từng cue dựa trên khớp chuỗi từ.

    - Xây chuỗi token gốc (nối tất cả cue) + nhớ token nào thuộc cue nào.
    - SequenceMatcher khớp token gốc với token Whisper.
    - Token gốc khớp được → lấy mốc giờ Whisper; token không khớp → nội suy.
    - Cue lấy start = mốc đầu của token sớm nhất, end = mốc cuối token muộn nhất.
    """
    # Chuỗi token gốc + bản đồ token → cue
    o_words, o_cue = [], []
    for ci, cue in enumerate(cues):
        for t in norm_tokens(cue):
            o_words.append(t)
            o_cue.append(ci)

    n = len(o_words)
    o_start = [None] * n
    o_end = [None] * n

    if w_words and n:
        sm = difflib.SequenceMatcher(a=o_words, b=w_words, autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                for k in range(i2 - i1):
                    o_start[i1 + k] = w_starts[j1 + k]
                    o_end[i1 + k] = w_ends[j1 + k]

    # Nội suy mốc giờ cho token chưa khớp (kẹp giữa 2 token đã biết)
    _interpolate(o_start, o_end, audio_dur)

    # Gom theo cue
    cue_times = []
    for ci in range(len(cues)):
        idxs = [i for i in range(n) if o_cue[i] == ci]
        if not idxs:
            cue_times.append(None)
            continue
        st = min(o_start[i] for i in idxs if o_start[i] is not None)
        en = max(o_end[i] for i in idxs if o_end[i] is not None)
        cue_times.append((st, en))

    _fill_empty_cues(cue_times, audio_dur)
    _sanitize(cue_times, audio_dur)
    return cue_times


def _interpolate(o_start, o_end, audio_dur):
    """Điền mốc giờ còn thiếu bằng nội suy tuyến tính theo chỉ số token."""
    n = len(o_start)
    if n == 0:
        return
    # Mỏ neo đầu/cuối nếu thiếu
    if o_start[0] is None:
        o_start[0] = 0.0
    if o_end[n - 1] is None:
        o_end[n - 1] = audio_dur or (o_start[0] + n * 0.3)

    # Lấp start
    i = 0
    while i < n:
        if o_start[i] is None:
            j = i
            while j < n and o_start[j] is None:
                j += 1
            left = o_end[i - 1] if i > 0 and o_end[i - 1] is not None else o_start[i - 1]
            right = o_start[j] if j < n else (audio_dur or left)
            left = left if left is not None else 0.0
            right = right if right is not None else left
            step = (right - left) / (j - i + 1)
            for k in range(i, j):
                o_start[k] = left + step * (k - i + 1)
            i = j
        else:
            i += 1
    # End suy ra từ start kế tiếp nếu thiếu
    for i in range(n):
        if o_end[i] is None:
            o_end[i] = o_start[i + 1] if i + 1 < n else (audio_dur or o_start[i] + 0.3)


def _fill_empty_cues(cue_times, audio_dur):
    """Cue không có token nào khớp (vd toàn chữ Hán) → nội suy từ cue lân cận."""
    n = len(cue_times)
    for i in range(n):
        if cue_times[i] is not None:
            continue
        prev_end = next((cue_times[k][1] for k in range(i - 1, -1, -1)
                         if cue_times[k]), 0.0)
        nxt_start = next((cue_times[k][0] for k in range(i + 1, n)
                          if cue_times[k]), audio_dur or prev_end + 1.0)
        if nxt_start <= prev_end:
            nxt_start = prev_end + 1.0
        cue_times[i] = (prev_end, nxt_start)


def _sanitize(cue_times, audio_dur, min_dur=0.6, gap=0.04):
    """Bảo đảm thời gian tăng dần, không chồng lấn, mỗi cue đủ dài để đọc."""
    prev_end = 0.0
    for i, t in enumerate(cue_times):
        st, en = t
        st = max(st, prev_end)
        if en < st + min_dur:
            en = st + min_dur
        if audio_dur:
            en = min(en, audio_dur)
            st = min(st, max(0.0, audio_dur - 0.1))
        cue_times[i] = (st, en)
        prev_end = en + gap


# ----------------------------------------------------------------------------- #
# 4) Xuất SRT + mux vào video
# ----------------------------------------------------------------------------- #
def _fmt_ts(sec: float) -> str:
    if sec < 0:
        sec = 0
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(cues, cue_times, srt_path: Path):
    lines = []
    for i, (cue, (st, en)) in enumerate(zip(cues, cue_times), 1):
        lines.append(str(i))
        lines.append(f"{_fmt_ts(st)} --> {_fmt_ts(en)}")
        lines.append(cue)
        lines.append("")
    srt_path.write_text("\n".join(lines), encoding="utf-8")
    return srt_path


# Kiểu chữ phụ đề khi burn-in (cú pháp force_style của ASS).
# Chữ trắng đậm, viền đen dày, bóng nhẹ, canh giữa dưới — dễ đọc trên mọi nền.
# FontSize tính theo độ cao 1080; ffmpeg tự co theo độ phân giải thật.
BURN_STYLE = (
    "FontName=Arial,FontSize=22,Bold=1,"
    "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BackColour=&H80000000,"
    "BorderStyle=1,Outline=2,Shadow=1,Alignment=2,MarginV=45"
)


def has_nvenc() -> bool:
    """Kiểm tra ffmpeg có encoder h264_nvenc (GPU NVIDIA) hay không."""
    try:
        r = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        return r.returncode == 0 and "h264_nvenc" in r.stdout
    except Exception:
        return False


def burn_subs(video_path: Path, srt_path: Path, out_path: Path, style=BURN_STYLE):
    """Vẽ CỨNG phụ đề thẳng vào khung hình (hardsub) — phải re-encode video.

    Ưu tiên GPU (h264_nvenc) cho nhanh; nếu GPU lỗi tự fallback về CPU (libx264).
    Để né rắc rối escape đường dẫn Windows (dấu ':' của ổ đĩa) trong bộ lọc
    subtitles, ta chạy ffmpeg với cwd = thư mục chứa .srt và chỉ truyền TÊN file.
    """
    vf = f"subtitles={srt_path.name}:force_style='{style}'"

    def build_cmd(gpu):
        if gpu:
            codec = ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "19"]
        else:
            codec = ["-c:v", "libx264", "-preset", "medium", "-crf", "18"]
        return [
            "ffmpeg", "-y",
            "-i", str(video_path.resolve()),
            "-vf", vf,
            *codec,
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            str(out_path.resolve()),
        ]

    use_gpu = has_nvenc()
    print("   Encode: GPU (h264_nvenc)" if use_gpu else "   Encode: CPU (libx264)")
    result = subprocess.run(build_cmd(use_gpu), capture_output=True, text=True,
                            encoding="utf-8", errors="replace", cwd=str(srt_path.parent))
    # GPU lỗi (driver/độ phân giải/encoder) → thử lại bằng CPU để không hỏng cả lượt.
    if result.returncode != 0 and use_gpu:
        print("   GPU lỗi, chuyển sang CPU (libx264)...")
        result = subprocess.run(build_cmd(False), capture_output=True, text=True,
                                encoding="utf-8", errors="replace", cwd=str(srt_path.parent))
    if result.returncode != 0:
        print(f"❌ Lỗi ffmpeg khi burn sub:\n{result.stderr[-1200:]}", file=sys.stderr)
        return False
    return True


def mux_softsub(video_path: Path, srt_path: Path, out_path: Path):
    """Nhúng mềm .srt vào mp4 (codec mov_text), không render lại hình/tiếng."""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(srt_path),
        "-map", "0", "-map", "1",
        "-c", "copy",
        "-c:s", "mov_text",
        "-metadata:s:s:0", "language=vie",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                            errors="replace")
    if result.returncode != 0:
        print(f"❌ Lỗi ffmpeg khi mux sub:\n{result.stderr[-1000:]}", file=sys.stderr)
        return False
    return True


# ----------------------------------------------------------------------------- #
def main():
    parser = argparse.ArgumentParser(
        description="Gắn phụ đề (soft sub) vào video, dùng chữ gốc + căn giờ theo audio."
    )
    parser.add_argument("video", help="Video cần gắn phụ đề (mp4).")
    parser.add_argument("--audio", default=None,
                        help="File audio để căn giờ (mặc định: tách từ video).")
    parser.add_argument("--script", default=str(DEFAULT_SCRIPT),
                        help="File văn bản kịch bản gốc (mặc định: ../kịch_bản/input.txt).")
    parser.add_argument("--out", default=None,
                        help="Video kết quả (mặc định: <tên video>_sub.mp4).")
    parser.add_argument("--model", default="medium",
                        help="Model whisper: tiny/base/small/medium/large-v3 (mặc định: medium).")
    parser.add_argument("--max-chars", type=int, default=50,
                        help="Độ dài tối đa mỗi dòng phụ đề (mặc định: 50).")
    parser.add_argument("--burn", action="store_true",
                        help="Vẽ cứng phụ đề vào hình (hardsub, re-encode) thay vì nhúng mềm.")
    args = parser.parse_args()

    video_path = Path(args.video)
    if not video_path.is_file():
        print(f"❌ Không tìm thấy video: {video_path}")
        sys.exit(1)
    script_path = Path(args.script)
    if not script_path.is_file():
        print(f"❌ Không tìm thấy file kịch bản: {script_path}")
        sys.exit(1)

    out_path = Path(args.out) if args.out else video_path.with_name(video_path.stem + "_sub.mp4")
    srt_path = out_path.with_suffix(".srt")

    # 1) Cue từ kịch bản gốc
    text = script_path.read_text(encoding="utf-8")
    cues = build_cues(text, args.max_chars)
    if not cues:
        print("❌ Kịch bản rỗng, không có gì để làm phụ đề.")
        sys.exit(1)
    print(f"✂️  Đã cắt {len(cues)} dòng phụ đề từ: {script_path.name}")

    # 2) Chuẩn bị audio để nghe
    temp_wav = None
    if args.audio:
        audio_path = args.audio
        if Path(audio_path).suffix.lower() not in AUDIO_EXTS:
            temp_wav = str(out_path.with_name(out_path.stem + "_temp16k.wav"))
            if not extract_audio(audio_path, temp_wav):
                sys.exit(1)
            audio_path = temp_wav
    else:
        temp_wav = str(out_path.with_name(out_path.stem + "_temp16k.wav"))
        print("🎧 Tách audio từ video để căn giờ...")
        if not extract_audio(str(video_path), temp_wav):
            sys.exit(1)
        audio_path = temp_wav

    audio_dur = get_audio_duration(audio_path) or 0
    if audio_dur:
        print(f"⏳ Thời lượng audio: {audio_dur / 60:.1f} phút")

    # 3) Nghe + khớp
    def _prog(frac):
        print(f"\r   tiến độ nghe: {frac * 100:5.1f}%", end="", flush=True)

    w_words, w_starts, w_ends = transcribe_words(audio_path, args.model, on_progress=_prog)
    print()
    if not w_words:
        print("⚠️ Whisper không nhận được từ nào — phụ đề sẽ rải đều theo thời lượng.")
    cue_times = align_cues(cues, w_words, w_starts, w_ends, audio_dur)

    # 4) SRT + mux
    write_srt(cues, cue_times, srt_path)
    print(f"💾 Đã ghi phụ đề: {srt_path}")

    if args.burn:
        print("🎬 Đang VẼ CỨNG phụ đề vào hình (re-encode, hơi lâu)...")
        ok = burn_subs(video_path, srt_path, out_path)
    else:
        print("🎬 Đang nhúng phụ đề (soft sub) vào video...")
        ok = mux_softsub(video_path, srt_path, out_path)

    if temp_wav and os.path.exists(temp_wav):
        try:
            os.remove(temp_wav)
        except Exception:
            pass

    if not ok:
        sys.exit(1)
    size_mb = out_path.stat().st_size / 1024 / 1024
    print(f"\n✅ Hoàn tất!")
    print(f"   Video có sub : {out_path}  ({size_mb:.1f} MB)")
    print(f"   File .srt     : {srt_path}")
    print("   (Phụ đề mềm — bật/tắt trong trình phát. Nếu player không hiện, mở .srt kèm theo.)")


if __name__ == "__main__":
    main()
