# -*- coding: utf-8 -*-
"""
Làm chậm video 0.7x + nhận diện tiếng Trung → phụ đề SRT khớp video ĐÃ làm chậm.

Cách làm (tương tự myvoice/scripts/nhandien_giongnoi.py, dùng chung model cache):
  1. Xuất video làm chậm:  setpts=PTS/0.7 (hình) + atempo=0.7 (tiếng).
  2. Trích audio 16kHz mono CŨNG ở tốc độ 0.7 → mốc giờ Whisper trả về
     khớp THẲNG với video đã làm chậm, không phải quy đổi gì thêm.
  3. Nhận diện bằng faster-whisper với word_timestamps=True: mỗi CHỮ có mốc
     giờ riêng → đoạn bắt đầu của câu = mốc chữ đầu tiên, kết thúc = mốc chữ
     cuối cùng. Đây là cách cho mốc giờ chính xác nhất (mốc theo segment 30s
     của Whisper hay bị sớm/muộn cả giây).
  4. Ghép chữ thành câu phụ đề theo DẤU CÂU TIẾNG TRUNG:
       - Ngắt CHÍNH tại 。！？… (hết câu là chốt, dù ngắn).
       - Đủ max-chars (mặc định 16 chữ Hán) → ngắt PHỤ tại ，、；：
       - hard-max (mặc định 16) là TRẦN CỨNG: chữ sắp làm vượt trần thì CẮT LUI
         về sau dấu câu gần nhất trong dòng (phần sau dấu sang dòng kế) — không
         cắt cụt giữa cụm từ; dòng không có dấu nào mới cắt ngay tại trần.
       - Mảnh < min-chars (4 chữ) hoặc hiển thị < 0.6s → gộp vào câu liền trước
         (tránh phụ đề nháy qua quá nhanh không kịp đọc).

  5. TỰ DỊCH sang tiếng Việt: gọi dich_srt.py gửi SRT lên Gemini (Firefox,
     profile đã đăng nhập — Firefox phải ĐÓNG trước khi chạy) → lưu thêm
     <tên>_vi.srt (Việt) + <tên>_zhvi.srt (song ngữ). Tắt bằng --no-dich.

Cách dùng (MỘT lệnh ra đủ: video chậm + SRT Trung + SRT Việt):
    python video_chamlai_srt.py "duong_dan/video.mp4"
    python video_chamlai_srt.py "video.mp4" --model large-v3 --max-chars 16
    python video_chamlai_srt.py "video.mp4" --no-video   (chỉ làm SRT, bỏ qua render video)
    python video_chamlai_srt.py "video.mp4" --no-dich    (không dịch, chỉ SRT tiếng Trung)

Kết quả mặc định nằm trong myvideo/output/:  <tên>_x0.7.mp4, <tên>_x0.7.srt,
<tên>_x0.7_vi.srt, <tên>_x0.7_zhvi.srt (cùng tên nhau để trình phát tự nạp).
"""

import argparse
import json
import os
import subprocess
import sys

# Bảo đảm console Windows in được tiếng Trung/Việt
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Dùng lại phần nạp model + tham số nhận diện của myvoice (chung whisper_cache,
# chung chống-kẹt-lặp), khỏi chép lại code.
MYVOICE_SCRIPTS = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "myvoice", "scripts"))
sys.path.insert(0, MYVOICE_SCRIPTS)
from nhandien_giongnoi import (  # noqa: E402
    FFMPEG_PATH,
    _TRANSCRIBE_OPTS,
    extract_audio,
    get_audio_duration,
    get_model,
)

# ---------------- Quy tắc ngắt câu tiếng Trung ----------------
MAJOR_BREAKS = "。！？!?…"       # hết câu → luôn chốt phụ đề
MINOR_BREAKS = "，、；：,;:"      # ngắt phụ khi câu đã dài
_CLOSERS = "”’」』）)\"'"         # dấu đóng đi liền sau dấu kết câu
_OPENERS = "“‘「『（(《〈"
_PUNCT = set(MAJOR_BREAKS + MINOR_BREAKS + _CLOSERS + _OPENERS + "《》〈〉·—－-‥")


def _nchars(text):
    """Đếm số CHỮ thật (bỏ dấu câu, khoảng trắng) — dùng làm ngưỡng ngắt."""
    return sum(1 for c in text if c not in _PUNCT and not c.isspace())


def slow_video(src, dst, speed=0.7):
    """Xuất video làm chậm: hình setpts, tiếng atempo (0.5–2.0). libx264 CRF 18
    giữ chất lượng gần gốc (ưu tiên chất lượng hơn tốc độ render)."""
    if not FFMPEG_PATH:
        print("❌ Không tìm thấy ffmpeg trong PATH.")
        return None
    print(f"🎬 Đang render video chậm {speed:g}x (video ~{1/speed:.2f} lần dài hơn)...")
    cmd = [
        FFMPEG_PATH, "-y", "-i", src,
        "-filter_complex", f"[0:v]setpts=PTS/{speed}[v];[0:a]atempo={speed}[a]",
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-crf", "18", "-preset", "medium",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        "-stats", "-loglevel", "warning",
        dst,
    ]
    try:
        subprocess.run(cmd, check=True)
        print(f"✅ Video đã làm chậm: {dst}")
        return dst
    except subprocess.CalledProcessError as e:
        print(f"❌ Lỗi render video: {e}")
        return None


def transcribe_words(audio_path, model_name="medium"):
    """Nhận diện và trả về danh sách chữ [(start, end, chữ), ...].

    Dùng model THƯỜNG (không batched): có đủ vòng temperature-fallback chống
    kẹt lặp, và word_timestamps hoạt động ổn định nhất — ưu tiên đúng mốc giờ
    hơn là nhanh.
    """
    model, _batched, _device = get_model(model_name, use_batched=False)

    opts = dict(_TRANSCRIBE_OPTS)
    opts["word_timestamps"] = True

    duration = get_audio_duration(audio_path) or 0
    if duration:
        print(f"⏳ Thời lượng audio (đã chậm): {duration / 60:.1f} phút")
    print("📝 Đang nhận diện tiếng Trung (kèm mốc giờ từng chữ)...")

    segments, info = model.transcribe(audio_path, **opts)
    total = duration or float(getattr(info, "duration", 0) or 0)

    words = []
    for seg in segments:
        if seg.words:
            for w in seg.words:
                token = w.word.strip()
                if token:
                    words.append((w.start, w.end, token))
        elif seg.text.strip():
            # hiếm khi thiếu word-level → dùng mốc cả câu còn hơn bỏ chữ
            words.append((seg.start, seg.end, seg.text.strip()))
        frac = min(seg.end / total, 1.0) if total else 0
        mm, ss = divmod(int(seg.end), 60)
        print(f"\r⏳ {frac * 100:5.1f}%  [{mm:02d}:{ss:02d}] {seg.text.strip()[:40]:<40}",
              end="", flush=True)
    print()
    return words


def build_subs(words, max_chars=16, hard_max=16, min_chars=4, min_dur=0.6):
    """Ghép chữ (có mốc giờ) thành các câu phụ đề theo dấu câu tiếng Trung.

    Trả về danh sách [start, end, text]. start/end lấy đúng mốc chữ đầu/cuối.
    Vượt trần hard_max thì CẮT LUI về dấu câu gần nhất trong dòng (phần sau dấu
    chuyển sang dòng kế); dòng không có dấu nào mới phải cắt ngay tại trần.
    """
    subs = []
    cur = []            # các chữ (ws, we, token) của dòng đang gom
    breaks = MAJOR_BREAKS + MINOR_BREAKS

    def _text(part):
        return "".join(t for _w, _e, t in part)

    def _flush(upto=None):
        """Chốt cur[:upto] thành một dòng; phần còn lại giữ làm dòng kế."""
        nonlocal cur
        part, rest = (cur, []) if upto is None else (cur[:upto], cur[upto:])
        text = _text(part)
        if text.strip():
            subs.append([part[0][0], max(w[1] for w in part), text])
        cur = rest

    for ws, we, token in words:
        # Dấu câu đứng riêng ngay sau khi vừa chốt câu (vd dấu ” sau 。):
        # dán vào câu trước, không mở câu mới chỉ chứa dấu.
        if not cur and _nchars(token) == 0 and subs:
            subs[-1][2] += token
            subs[-1][1] = max(subs[-1][1], we)
            continue
        # TRẦN CỨNG: thêm chữ này mà vượt hard_max thì chốt dòng hiện tại TRƯỚC,
        # ưu tiên CẮT LUI về sau dấu câu gần nhất trong dòng (không cắt cụt giữa
        # cụm từ ở đúng chữ 16). while: phần lui sang dòng kế cộng chữ mới vẫn
        # có thể vượt trần → cắt tiếp cho tới khi đủ chỗ.
        while cur and _nchars(_text(cur)) + _nchars(token) > hard_max:
            cut = None
            for i in range(len(cur) - 1, -1, -1):
                if any(c in breaks for c in cur[i][2]):
                    cut = i + 1
                    break
            _flush(None if cut in (None, len(cur)) else cut)
        cur.append((ws, we, token))

        if any(c in MAJOR_BREAKS for c in token):
            _flush()
            continue
        if _nchars(_text(cur)) >= max_chars and token[-1] in MINOR_BREAKS:
            _flush()
    if cur:
        _flush()

    # Gộp mảnh quá ngắn (ít chữ hoặc hiện quá nhanh) vào câu liền trước,
    # miễn là gộp xong không phình quá hard_max và hai câu nằm sát nhau.
    merged = []
    for s in subs:
        too_small = _nchars(s[2]) < min_chars or (s[1] - s[0]) < min_dur
        if (merged and too_small
                and _nchars(merged[-1][2]) + _nchars(s[2]) <= hard_max
                and s[0] - merged[-1][1] < 1.0):
            merged[-1][1] = s[1]
            merged[-1][2] += s[2]
        else:
            merged.append(s)
    return merged


def pad_ends(subs, pad=0.2):
    """Nới đuôi mỗi câu thêm `pad` giây cho dễ đọc, nhưng KHÔNG đè lên câu sau."""
    for i, s in enumerate(subs):
        if pad <= 0:
            break
        limit = subs[i + 1][0] - 0.05 if i + 1 < len(subs) else s[1] + pad
        s[1] = max(s[1], min(s[1] + pad, limit))
    return subs


def _fmt_srt_time(t):
    ms = int(round(max(t, 0) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(subs, out_path):
    with open(out_path, "w", encoding="utf-8") as f:
        for i, (start, end, text) in enumerate(subs, 1):
            f.write(f"{i}\n{_fmt_srt_time(start)} --> {_fmt_srt_time(end)}\n{text.strip()}\n\n")
    print(f"💾 Đã lưu phụ đề: {out_path}  ({len(subs)} câu)")
    return out_path


def main():
    parser = argparse.ArgumentParser(
        description="Làm chậm video + nhận diện tiếng Trung ra SRT (mốc giờ theo từng chữ).")
    parser.add_argument("media", help="Đường dẫn file video (hoặc audio) cần xử lý.")
    parser.add_argument("--speed", type=float, default=0.7,
                        help="Tốc độ sau khi làm chậm (mặc định 0.7).")
    parser.add_argument("--model", default="medium",
                        help="Model whisper: tiny/base/small/medium/large-v3 (mặc định medium).")
    parser.add_argument("--max-chars", type=int, default=16,
                        help="Đủ số chữ này thì ngắt tại ，、；： (mặc định 16).")
    parser.add_argument("--hard-max", type=int, default=16,
                        help="TRẦN CỨNG: không dòng nào vượt quá số chữ này — vượt thì "
                             "cắt lui về dấu câu gần nhất trong dòng (mặc định 16).")
    parser.add_argument("--min-chars", type=int, default=4,
                        help="Câu ít hơn số chữ này bị gộp vào câu trước (mặc định 4).")
    parser.add_argument("--pad", type=float, default=0.2,
                        help="Nới đuôi mỗi câu thêm N giây, không đè câu sau (mặc định 0.2; 0 = tắt).")
    parser.add_argument("--no-video", action="store_true",
                        help="Chỉ tạo SRT, bỏ qua bước render video chậm.")
    parser.add_argument("--redo-asr", action="store_true",
                        help="Nhận diện lại từ đầu, bỏ qua file *_words.json đã lưu.")
    parser.add_argument("--no-dich", action="store_true",
                        help="Không tự dịch sang tiếng Việt sau khi ra SRT tiếng Trung.")
    parser.add_argument("--out-dir", default=os.path.join(SCRIPT_DIR, "output"),
                        help="Thư mục lưu kết quả (mặc định myvideo/output).")
    args = parser.parse_args()

    if not os.path.isfile(args.media):
        print(f"❌ Không tìm thấy file: {args.media}")
        sys.exit(1)
    os.makedirs(args.out_dir, exist_ok=True)

    base = os.path.splitext(os.path.basename(args.media))[0]
    tag = f"_x{args.speed:g}"
    out_video = os.path.join(args.out_dir, f"{base}{tag}.mp4")
    out_srt = os.path.join(args.out_dir, f"{base}{tag}.srt")
    temp_wav = os.path.join(args.out_dir, f"{base}{tag}_temp_audio.wav")
    words_json = os.path.join(args.out_dir, f"{base}{tag}_words.json")

    try:
        # 1+2. Lấy mốc giờ từng chữ: đã lưu từ lần trước thì dùng lại (đổi ngưỡng
        # ngắt câu chỉ mất vài giây), chưa có thì trích audio + nhận diện rồi LƯU.
        if os.path.isfile(words_json) and not args.redo_asr:
            print(f"♻ Dùng lại mốc giờ từng chữ đã lưu: {os.path.basename(words_json)}"
                  "  (--redo-asr nếu muốn nhận diện lại)")
            with open(words_json, encoding="utf-8") as f:
                words = [tuple(w) for w in json.load(f)]
        else:
            # Audio 16kHz mono ĐÃ làm chậm → mốc giờ ASR khớp thẳng video chậm.
            if not extract_audio(args.media, temp_wav, tempo=args.speed):
                sys.exit(1)
            words = transcribe_words(temp_wav, model_name=args.model)
            with open(words_json, "w", encoding="utf-8") as f:
                json.dump(words, f, ensure_ascii=False)
            print(f"💾 Đã lưu mốc giờ từng chữ: {words_json}")
        if not words:
            print("❌ Không nhận diện được chữ nào.")
            sys.exit(1)

        # 3. Ghép thành câu phụ đề theo dấu câu tiếng Trung rồi ghi SRT.
        subs = build_subs(words, max_chars=args.max_chars, hard_max=args.hard_max,
                          min_chars=args.min_chars)
        subs = pad_ends(subs, pad=args.pad)
        write_srt(subs, out_srt)
        n_chars = sum(_nchars(s[2]) for s in subs)
        print(f"📊 {len(subs)} câu, trung bình {n_chars / max(len(subs), 1):.1f} chữ/câu.")

        # 3b. Tự dịch sang tiếng Việt: gửi SRT lên Gemini (Firefox) → lưu _vi.srt
        # + _zhvi.srt. Lỗi dịch KHÔNG làm hỏng cả lượt — SRT tiếng Trung đã lưu,
        # chạy lại dich_srt.py là dịch tiếp (có file tiến độ _vi.partial.json).
        if not args.no_dich:
            out_vi = f"{os.path.splitext(out_srt)[0]}_vi.srt"
            if os.path.isfile(out_vi):
                print(f"♻ Đã có bản dịch {os.path.basename(out_vi)} — bỏ qua bước dịch "
                      "(xoá file đó nếu muốn dịch lại).")
            else:
                print("🌐 Đang dịch sang tiếng Việt qua Gemini (Firefox phải ĐÓNG trước)...")
                dich_script = os.path.join(SCRIPT_DIR, "dich_srt.py")
                ret = subprocess.run([sys.executable, dich_script, out_srt])
                if ret.returncode != 0:
                    print("⚠️ Dịch chưa xong — SRT tiếng Trung vẫn an toàn. Chạy lại:\n"
                          f'   python "{dich_script}" "{out_srt}"')

        # 4. Render video chậm (để sau ASR: lỡ render lỗi vẫn còn SRT).
        if not args.no_video:
            if not slow_video(args.media, out_video, speed=args.speed):
                sys.exit(1)
    finally:
        if os.path.exists(temp_wav):
            try:
                os.remove(temp_wav)
            except Exception:
                pass

    print("\n✅ Xong. Kết quả trong:", args.out_dir)


if __name__ == "__main__":
    main()
