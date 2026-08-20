# -*- coding: utf-8 -*-
"""
Làm chậm video 0.7x + nhận diện tiếng gốc → phụ đề SRT khớp video ĐÃ làm chậm.

Tiếng gốc chọn bằng --lang: zh (Trung, mặc định) hoặc en (Anh). Ngôn ngữ quyết
định ba thứ: gọi Whisper với language nào, NỐI chữ thành dòng ra sao (Trung viết
liền, Anh có khoảng trắng) và bộ dấu ngắt câu nào — xem bảng NGON_NGU bên dưới.

Cách làm (tương tự myvoice/scripts/nhandien_giongnoi.py, dùng chung model cache):
  1. Xuất video làm chậm:  setpts=PTS/0.7 (hình) + atempo=0.7 (tiếng).
  2. Trích audio 16kHz mono CŨNG ở tốc độ 0.7 → mốc giờ Whisper trả về
     khớp THẲNG với video đã làm chậm, không phải quy đổi gì thêm.
  3. Nhận diện bằng faster-whisper với word_timestamps=True: mỗi CHỮ có mốc
     giờ riêng → đoạn bắt đầu của câu = mốc chữ đầu tiên, kết thúc = mốc chữ
     cuối cùng. Đây là cách cho mốc giờ chính xác nhất (mốc theo segment 30s
     của Whisper hay bị sớm/muộn cả giây).
  4. Ghép chữ thành câu phụ đề theo DẤU CÂU CỦA CHÍNH TIẾNG ĐÓ:
       - Ngắt CHÍNH tại 。！？… (Trung) / . ! ? (Anh) — hết câu là chốt, dù ngắn.
       - Đủ max-chars (16 chữ Hán · 42 ký tự tiếng Anh) → ngắt PHỤ tại
         ，、；： (Trung) / , ; : — (Anh)
       - hard-max là TRẦN CỨNG: chữ sắp làm vượt trần thì CẮT LUI
         về sau dấu câu gần nhất trong dòng (phần sau dấu sang dòng kế) — không
         cắt cụt giữa cụm từ; dòng không có dấu nào mới cắt ngay tại trần.
       - Mảnh < min-chars (4 chữ Hán · 10 ký tự Anh) hoặc hiển thị < 0.6s →
         gộp vào câu liền trước
         (tránh phụ đề nháy qua quá nhanh không kịp đọc).

  5. TỰ DỊCH sang tiếng Việt: gọi dich_srt.py gửi SRT lên Gemini (Firefox,
     profile đã đăng nhập — Firefox phải ĐÓNG trước khi chạy) → lưu thêm
     <tên>_vi.srt (Việt) + <tên>_zhvi.srt / <tên>_envi.srt (song ngữ).
     Tắt bằng --no-dich.

Cách dùng (MỘT lệnh ra đủ: video chậm + SRT gốc + SRT Việt):
    python video_chamlai_srt.py "duong_dan/video.mp4"
    python video_chamlai_srt.py "video.mp4" --lang en   (video tiếng Anh)
    python video_chamlai_srt.py "video.mp4" --model large-v3 --max-chars 16
    python video_chamlai_srt.py "video.mp4" --no-video   (chỉ làm SRT, bỏ qua render video)
    python video_chamlai_srt.py "video.mp4" --no-dich    (không dịch, chỉ SRT tiếng gốc)

Kết quả mặc định nằm trong myvideo/output/:  <tên>_x0.7.mp4, <tên>_x0.7.srt,
<tên>_x0.7_vi.srt, <tên>_x0.7_zhvi.srt (cùng tên nhau để trình phát tự nạp).

Mốc giờ từng chữ lưu riêng theo tiếng (<tên>_words.json cho Trung,
<tên>_words_en.json cho Anh) — đổi --lang là nhận diện lại, không dùng nhầm
mốc giờ của tiếng kia.
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
    free_model,
    get_audio_duration,
    get_model,
)

# ---------------- Quy tắc ngắt câu theo từng tiếng ----------------
_CLOSERS = "”’」』）)\"'"         # dấu đóng đi liền sau dấu kết câu
_OPENERS = "“‘「『（(《〈"
_PUNCT = set("。！？!?…，、；：,;:.-" + _CLOSERS + _OPENERS + "《》〈〉·—－‥")

# Ba thứ KHÁC nhau giữa hai tiếng: gọi Whisper thế nào, nối chữ thành dòng ra
# sao, và đâu là dấu ngắt. Thêm tiếng mới = thêm một mục ở đây.
NGON_NGU = {
    "zh": {
        "ten": "Trung",
        "whisper": "zh",
        "prompt": "以下是普通话的句子，请用简体中文加上标点符号。",
        "noi": "",                 # chữ Hán viết liền, không chèn khoảng trắng
        "major": "。！？!?…",        # hết câu → chốt dòng
        "minor": "，、；：,;:",       # ngắt phụ khi dòng đã dài
        "dem_kytu": False,         # ngưỡng đếm theo CHỮ (bỏ dấu câu)
        "max_chars": 16,
        "min_chars": 4,
        "don_vi": "chữ",
    },
    "en": {
        "ten": "Anh",
        "whisper": "en",
        # Câu mẫu có chấm phẩy + viết hoa đàng hoàng: Whisper bám theo kiểu đó,
        # khỏi trả về một dải chữ thường không dấu câu (không dấu thì lấy gì ngắt).
        "prompt": "Hello, and welcome back. Today, we'll look at three things: "
                  "what happened, why it matters, and what comes next.",
        "noi": " ",                # tiếng Anh: chữ cách nhau bằng khoảng trắng
        "major": ".!?…",
        "minor": ",;:—–",
        "dem_kytu": True,          # ngưỡng đếm theo KÝ TỰ (chuẩn phụ đề ~42)
        "max_chars": 42,
        "min_chars": 10,
        "don_vi": "ký tự",
        # Hai chỗ đè lên _TRANSCRIBE_OPTS (vốn chỉnh cho tiếng Trung):
        #
        # no_repeat_ngram_size=0 — bản gốc cấm lặp mọi cụm 3 chữ trong một cửa
        # sổ 30s. Tiếng Anh lặp cụm 3 từ là chuyện thường ("I don't know, I
        # don't know") — cấm thì Whisper phải bịa từ khác. Chống kẹt lặp đã có
        # vòng lùi temperature + ngưỡng nén lo.
        #
        # condition_on_previous_text=True — QUAN TRỌNG cho dấu câu. Để False thì
        # câu mẫu initial_prompt chỉ áp cho cửa sổ 30s ĐẦU TIÊN, từ cửa sổ thứ
        # hai trở đi Whisper đọc không ngữ cảnh nên thôi chấm câu, trả về một
        # dải chữ chạy dài ("...level this way you can scale smarter and not
        # waste your money so if you ever felt like you..."). Không có dấu thì
        # không biết đâu là câu để dịch và để đọc. Đo trên 4 phút audio thật:
        # 17 dấu kết câu (False) → 34 (True), tức 166 → 84 ký tự mỗi câu. Đổi
        # lại nhận diện chậm hơn ~3 lần (4 phút audio: 17s → 49s) vì mỗi cửa sổ
        # phải nuốt thêm ngữ cảnh — chấp nhận, vì cắt câu sai thì hỏng cả bản
        # dịch lẫn giọng đọc ở hai bước sau. Chạy lẻ muốn nhanh: --khong-ngu-canh.
        "opts": {"no_repeat_ngram_size": 0, "condition_on_previous_text": True},
    },
}
MAC_DINH = "zh"


def _cfg(lang):
    return NGON_NGU.get(lang or MAC_DINH, NGON_NGU[MAC_DINH])


def _nchars(text, lang=MAC_DINH):
    """Độ dài dòng dùng làm ngưỡng ngắt.

    Trung đếm số CHỮ thật (bỏ dấu câu/khoảng trắng — 16 chữ Hán là một dòng
    vừa mắt); Anh đếm KÝ TỰ kể cả khoảng trắng, vì bề ngang dòng phụ đề tiếng
    Anh do ký tự quyết định chứ không phải số từ.
    """
    if _cfg(lang)["dem_kytu"]:
        return len(text.strip())
    return sum(1 for c in text if c not in _PUNCT and not c.isspace())


def _chi_dau(token):
    """Token chỉ toàn dấu câu (vd ” đứng riêng sau 。) — không mở dòng mới vì nó."""
    return not any(c.isalnum() for c in token)


def _ghep(tokens, lang=MAC_DINH):
    """Nối các token thành dòng: Trung viết liền, Anh chèn khoảng trắng —
    trừ token mở đầu bằng dấu câu (dấu phẩy, 's...) thì dán thẳng vào chữ trước."""
    sep = _cfg(lang)["noi"]
    if not sep:
        return "".join(tokens)
    out = ""
    for t in tokens:
        if out and t and (t[0].isalnum() or t[0] in '"“([{$&@#*'):
            out += sep
        out += t
    return out


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


def transcribe_words(audio_path, model_name="medium", lang=MAC_DINH,
                     khong_ngu_canh=False):
    """Nhận diện và trả về danh sách chữ [(start, end, chữ), ...].

    Dùng model THƯỜNG (không batched): có đủ vòng temperature-fallback chống
    kẹt lặp, và word_timestamps hoạt động ổn định nhất — ưu tiên đúng mốc giờ
    hơn là nhanh.
    """
    model, _batched, _device = get_model(model_name, use_batched=False)

    cfg = _cfg(lang)
    # _TRANSCRIBE_OPTS của myvoice cố định tiếng Trung (kèm câu mẫu chữ Hán) —
    # chép ra rồi đè language/initial_prompt cho đúng tiếng đang chọn.
    opts = dict(_TRANSCRIBE_OPTS)
    opts["word_timestamps"] = True
    opts["language"] = cfg["whisper"]
    opts["initial_prompt"] = cfg["prompt"]
    opts.update(cfg.get("opts", {}))
    if khong_ngu_canh:
        opts["condition_on_previous_text"] = False

    duration = get_audio_duration(audio_path) or 0
    if duration:
        print(f"⏳ Thời lượng audio (đã chậm): {duration / 60:.1f} phút")
    print(f"📝 Đang nhận diện tiếng {cfg['ten']} (kèm mốc giờ từng chữ)...")

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


def build_subs(words, max_chars=16, hard_max=16, min_chars=4, min_dur=0.6,
               lang=MAC_DINH):
    """Ghép chữ (có mốc giờ) thành các câu phụ đề theo dấu câu của tiếng `lang`.

    Trả về danh sách [start, end, text]. start/end lấy đúng mốc chữ đầu/cuối.
    Vượt trần hard_max thì CẮT LUI về dấu câu gần nhất trong dòng (phần sau dấu
    chuyển sang dòng kế); dòng không có dấu nào mới phải cắt ngay tại trần.
    """
    subs = []
    cur = []            # các chữ (ws, we, token) của dòng đang gom
    cfg = _cfg(lang)
    major, minor = cfg["major"], cfg["minor"]
    breaks = major + minor

    def _text(part):
        return _ghep([t for _w, _e, t in part], lang)

    def _flush(upto=None):
        """Chốt cur[:upto] thành một dòng; phần còn lại giữ làm dòng kế."""
        nonlocal cur
        part, rest = (cur, []) if upto is None else (cur[:upto], cur[upto:])
        text = _text(part)
        if text.strip():
            subs.append([part[0][0], max(w[1] for w in part), text])
        cur = rest

    for ws, we, token in words:
        # Token CHỈ có dấu câu (dấu ” sau 。, hay dấu : ， đứng riêng): dán vào
        # dòng đang gom — chưa gom gì thì dán vào dòng vừa chốt. Không bao giờ
        # vì một cái dấu mà cắt dòng hay mở dòng mới chỉ chứa dấu.
        if _chi_dau(token):
            if cur:
                cur.append((ws, we, token))
                if any(c in major for c in token):
                    _flush()
            elif subs:
                subs[-1][2] += token
                subs[-1][1] = max(subs[-1][1], we)
            continue
        # TRẦN CỨNG: thêm chữ này mà vượt hard_max thì chốt dòng hiện tại TRƯỚC,
        # ưu tiên CẮT LUI về sau dấu câu gần nhất trong dòng (không cắt cụt giữa
        # cụm từ ở đúng chữ 16). while: phần lui sang dòng kế cộng chữ mới vẫn
        # có thể vượt trần → cắt tiếp cho tới khi đủ chỗ.
        while cur and _nchars(_text(cur + [(ws, we, token)]), lang) > hard_max:
            cut = None
            for i in range(len(cur) - 1, -1, -1):
                if any(c in breaks for c in cur[i][2]):
                    cut = i + 1
                    break
            _flush(None if cut in (None, len(cur)) else cut)
        cur.append((ws, we, token))

        if any(c in major for c in token):
            _flush()
            continue
        if _nchars(_text(cur), lang) >= max_chars and token[-1] in minor:
            _flush()
    if cur:
        _flush()

    # Gộp mảnh quá ngắn (ít chữ hoặc hiện quá nhanh) vào câu liền trước,
    # miễn là gộp xong không phình quá hard_max và hai câu nằm sát nhau.
    merged = []
    for s in subs:
        too_small = _nchars(s[2], lang) < min_chars or (s[1] - s[0]) < min_dur
        if (merged and too_small
                and _nchars(_ghep([merged[-1][2], s[2]], lang), lang) <= hard_max
                and s[0] - merged[-1][1] < 1.0):
            merged[-1][1] = s[1]
            merged[-1][2] = _ghep([merged[-1][2], s[2]], lang)
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
        description="Làm chậm video + nhận diện tiếng gốc ra SRT (mốc giờ theo từng chữ).")
    parser.add_argument("media", help="Đường dẫn file video (hoặc audio) cần xử lý.")
    parser.add_argument("--lang", default=MAC_DINH, choices=sorted(NGON_NGU),
                        help="Tiếng GỐC của video: zh = Trung (mặc định), en = Anh.")
    parser.add_argument("--speed", type=float, default=0.7,
                        help="Tốc độ sau khi làm chậm (mặc định 0.7).")
    parser.add_argument("--model", default="medium",
                        help="Model whisper: tiny/base/small/medium/large-v3 (mặc định medium).")
    parser.add_argument("--max-chars", type=int, default=None,
                        help="Đủ mức này thì ngắt tại dấu phụ (mặc định 16 chữ Hán · 42 ký tự Anh).")
    parser.add_argument("--hard-max", type=int, default=None,
                        help="TRẦN CỨNG: không dòng nào vượt mức này — vượt thì cắt lui "
                             "về dấu câu gần nhất trong dòng (mặc định bằng --max-chars).")
    parser.add_argument("--min-chars", type=int, default=None,
                        help="Câu ngắn hơn mức này bị gộp vào câu trước (mặc định 4 chữ Hán · 10 ký tự Anh).")
    parser.add_argument("--pad", type=float, default=0.2,
                        help="Nới đuôi mỗi câu thêm N giây, không đè câu sau (mặc định 0.2; 0 = tắt).")
    parser.add_argument("--no-video", action="store_true",
                        help="Chỉ tạo SRT, bỏ qua bước render video chậm.")
    parser.add_argument("--khong-ngu-canh", action="store_true",
                        help="Nhận diện KHÔNG dùng ngữ cảnh câu trước: nhanh hơn "
                             "~3 lần nhưng Whisper hay quên chấm câu (chỉ nên dùng "
                             "khi cần bản nháp gấp).")
    parser.add_argument("--redo-asr", action="store_true",
                        help="Nhận diện lại từ đầu, bỏ qua file *_words.json đã lưu.")
    parser.add_argument("--no-dich", action="store_true",
                        help="Không tự dịch sang tiếng Việt sau khi ra SRT tiếng gốc.")
    parser.add_argument("--out-dir", default=os.path.join(SCRIPT_DIR, "output"),
                        help="Thư mục lưu kết quả (mặc định myvideo/output).")
    args = parser.parse_args()

    cfg = _cfg(args.lang)
    max_chars = args.max_chars or cfg["max_chars"]
    hard_max = args.hard_max or max_chars
    min_chars = args.min_chars or cfg["min_chars"]

    if not os.path.isfile(args.media):
        print(f"❌ Không tìm thấy file: {args.media}")
        sys.exit(1)
    os.makedirs(args.out_dir, exist_ok=True)

    base = os.path.splitext(os.path.basename(args.media))[0]
    tag = f"_x{args.speed:g}"
    out_video = os.path.join(args.out_dir, f"{base}{tag}.mp4")
    out_srt = os.path.join(args.out_dir, f"{base}{tag}.srt")
    temp_wav = os.path.join(args.out_dir, f"{base}{tag}_temp_audio.wav")
    # Mốc giờ lưu RIÊNG theo tiếng: đổi --lang là nhận diện lại chứ không xài
    # nhầm mốc giờ của tiếng kia (tên cũ _words.json giữ nguyên cho tiếng Trung).
    hau_to = "" if args.lang == MAC_DINH else f"_{args.lang}"
    words_json = os.path.join(args.out_dir, f"{base}{tag}_words{hau_to}.json")

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
            words = transcribe_words(temp_wav, model_name=args.model, lang=args.lang,
                                     khong_ngu_canh=args.khong_ngu_canh)
            # Nhận diện xong là Whisper hết việc: nhả ngay chứ đừng để nó ngồi
            # trong VRAM suốt mấy phút render video bên dưới (libx264 chạy CPU
            # nhưng card còn phải chia cho Chrome, và bước sau cần chỗ trống).
            free_model()
            with open(words_json, "w", encoding="utf-8") as f:
                json.dump(words, f, ensure_ascii=False)
            print(f"💾 Đã lưu mốc giờ từng chữ: {words_json}")
        if not words:
            print("❌ Không nhận diện được chữ nào.")
            sys.exit(1)

        # 3. Ghép thành câu phụ đề theo dấu câu của tiếng đã chọn rồi ghi SRT.
        subs = build_subs(words, max_chars=max_chars, hard_max=hard_max,
                          min_chars=min_chars, lang=args.lang)
        subs = pad_ends(subs, pad=args.pad)
        write_srt(subs, out_srt)
        n_chars = sum(_nchars(s[2], args.lang) for s in subs)
        print(f"📊 {len(subs)} câu, trung bình "
              f"{n_chars / max(len(subs), 1):.1f} {cfg['don_vi']}/câu.")

        # 3b. Tự dịch sang tiếng Việt: gửi SRT lên Gemini (Firefox) → lưu _vi.srt
        # + bản song ngữ. Lỗi dịch KHÔNG làm hỏng cả lượt — SRT tiếng gốc đã lưu,
        # chạy lại dich_srt.py là dịch tiếp (có file tiến độ _vi.partial.json).
        if not args.no_dich:
            out_vi = f"{os.path.splitext(out_srt)[0]}_vi.srt"
            if os.path.isfile(out_vi):
                print(f"♻ Đã có bản dịch {os.path.basename(out_vi)} — bỏ qua bước dịch "
                      "(xoá file đó nếu muốn dịch lại).")
            else:
                print("🌐 Đang dịch sang tiếng Việt qua Gemini (Firefox phải ĐÓNG trước)...")
                dich_script = os.path.join(SCRIPT_DIR, "dich_srt.py")
                ret = subprocess.run([sys.executable, dich_script, out_srt,
                                      "--lang", args.lang])
                if ret.returncode != 0:
                    print(f"⚠️ Dịch chưa xong — SRT tiếng {cfg['ten']} vẫn an toàn. "
                          "Chạy lại:\n"
                          f'   python "{dich_script}" "{out_srt}" --lang {args.lang}')

        # 4. Render video chậm (để sau ASR: lỡ render lỗi vẫn còn SRT).
        # Đã có sẵn thì BỎ QUA: video chậm chẳng liên quan gì tới nhận diện, nên
        # chạy lại bước ① chỉ để làm lại SRT (đổi ngôn ngữ, bật nghe-ngữ-cảnh,
        # --redo-asr) không phải ngồi render lại từng đó phút cho một file y hệt.
        if not args.no_video:
            if os.path.isfile(out_video):
                print(f"♻ Đã có {os.path.basename(out_video)} — bỏ qua render "
                      "(xoá file đó nếu muốn dựng lại).")
            elif not slow_video(args.media, out_video, speed=args.speed):
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
