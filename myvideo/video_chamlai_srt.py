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
     của Whisper hay bị sớm/muộn cả giây). Nhận diện theo từng KHÚC ~3 phút,
     khúc sau được mồi bằng lời thoại có dấu câu của khúc trước — nhờ vậy
     Whisper chấm câu suốt bài chứ không bỏ dấu giữa chừng (transcribe_words).
  4. Ghép chữ thành câu phụ đề theo DẤU CÂU CỦA CHÍNH TIẾNG ĐÓ:
       - Ngắt CHÍNH tại 。！？… (Trung) / . ! ? (Anh) — hết câu là chốt, dù ngắn;
         chỗ người nói nghỉ ≥ 0,7 s cũng chốt như vậy.
       - Tiếng Trung mặc định KHÔNG giới hạn bề ngang (--max-chars 0): mỗi dòng
         một câu trọn, chỉ có ngắt chính ở trên (kèm lưới an toàn: câu quá 70
         chữ cắt ở dấu phẩy, dòng không dấu câu nào quá 36 chữ chốt ở hết vế).
         Các gạch dưới đây áp dụng khi CÓ đặt max-chars (tiếng Anh mặc định 42).
       - Đủ max-chars (vd 16 chữ Hán · 42 ký tự tiếng Anh) → ngắt PHỤ tại
         ，、；： (Trung) / , ; : — (Anh), và tại RANH GIỚI VẾ Whisper tự tách
         (mỗi segment một vế) — thứ duy nhất còn dùng được khi Whisper không
         chấm câu. Mốc giờ từng chữ lưu kèm cờ hết_vế cho việc này.
       - hard-max là TRẦN CỨNG: chữ sắp làm vượt trần thì CẮT LUI về chỗ ngắt
         gần nhất trong dòng (phần sau sang dòng kế), không để từ nối / lời dẫn
         của câu sau nằm cuối dòng; một vế dài hơn cả dòng thì chia cân ở chỗ
         người nói ngừng — không cắt ở đúng trần rồi rớt 1–2 chữ sang dòng kế.
       - Mảnh < min-chars (4 chữ Hán · 10 ký tự Anh) hoặc hiển thị < 0.6s →
         gộp vào câu liền trước
         (tránh phụ đề nháy qua quá nhanh không kịp đọc).
     Trước khi ghép: sửa mốc giờ các chữ bị Whisper dán nhầm sang bên kia chỗ
     nghỉ (sua_chu_lac) — không thì câu sau chỗ nghỉ vào sớm đúng bằng quãng nghỉ.

  5. TỰ DỊCH sang tiếng Việt: gọi dich_srt.py gửi SRT lên Gemini (Chrome
     Extension như myvoice, Firefox/Selenium là dự phòng) → lưu thêm
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
sys.path.insert(0, SCRIPT_DIR)
import doan  # noqa: E402  — chia / ghép đoạn video dài (xem doan.py)

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
        # 0 = KHÔNG giới hạn bề ngang: mỗi dòng SRT là một câu trọn, chỉ chốt ở
        # dấu hết câu hoặc chỗ nghỉ. Trần 16 chữ cũ bỏ từ 18/11/2026 theo yêu cầu:
        # nó chỉ để dòng chữ Hán vừa mắt, mà video ra chỉ vẽ phụ đề Việt; đổi lại
        # nó bẻ câu thành mẩu, vế nào dài hơn 16 chữ còn bị chia giữa từ.
        "max_chars": 0,
        # Lưới an toàn khi không giới hạn (cùng số với dich_srt.TRAN và
        # TRAN_KHONG_DAU): một câu dài quá tran_cau thì cắt ở dấu phẩy; dòng chưa
        # có dấu câu nào (khúc Whisper không chấm câu) dài tới tran_khong_dau thì
        # chốt ở ranh giới vế — không thì chạy mãi tới chỗ nghỉ kế tiếp.
        "tran_cau": 70,
        "tran_khong_dau": 36,
        "min_chars": 4,
        "don_vi": "chữ",
        # Từ nối MỞ ĐẦU vế sau: Whisper hay tách nó thành một vế riêng ("交出生
        # 死簿 | 否则 | 休怪我等不客气"). Dòng không được kết bằng một vế như vậy —
        # nó thuộc về câu kế, cắt ở đó thì câu sau mất chữ đầu.
        "noi_sau": ("否则", "不然", "要不然", "但是", "但", "可是", "不过", "只是", "然而",
                    "而且", "并且", "况且", "何况", "所以", "因此", "于是", "因为", "如果",
                    "要是", "假如", "若", "虽然", "尽管", "即使", "就算", "哪怕", "既然",
                    "然后", "那么", "还有", "以及", "或者", "而", "却"),
        # condition_on_previous_text=True — có dấu câu hay không là ở đây (xem khối
        # "Nhận diện theo KHÚC"). Đo 7 phút đầu bài thật: 6 → 79 dấu hết câu, chữ
        # nhận đúng hơn (越俎代庖, 生死簿, 阴司); cả bài 85 phút chậm hơn ~1,6 lần
        # (5,5 → 9 phút). Chống kẹt lặp vẫn nguyên như _TRANSCRIBE_OPTS.
        "opts": {"condition_on_previous_text": True},
        # Ba phép soát từng khúc nhận diện (xem khối "Nhận diện theo KHÚC"):
        # kho_dau — có dãy > ngần này chữ liền không dấu câu = Whisper đã bỏ chấm câu.
        "kho_dau": 80,
        # vong_cau_mau — Whisper chép luôn câu mẫu ra thành lời thoại (chỗ nhạc /
        # tiếng ồn); segment chứa một trong các mẩu này là bị chép.
        "vong_cau_mau": ("请用简体中文", "加上标点符号", "以下是普通话"),
        # chu_moi_giay — ít hơn ngần này chữ cho mỗi giây có tiếng nói là Whisper
        # đang nuốt lời (bài thật ở tốc độ 0,7: ~3,3 chữ/giây; khúc hỏng: 0,4).
        "chu_moi_giay": 1.0,
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
        "max_chars": 42,           # đặt 0 = không giới hạn như tiếng Trung
        "tran_cau": 200,           # lưới an toàn khi không giới hạn (xem mục zh)
        "tran_khong_dau": 90,
        "min_chars": 10,
        "don_vi": "ký tự",
        # Tiếng Anh: Whisper hay kết một vế bằng chính từ nối của vế sau ("...scale
        # smarter and | not waste your money so | if you ever..."). Dòng không
        # được kết bằng những từ này — đẩy nó xuống mở đầu dòng kế.
        "noi_sau": ("and", "but", "or", "so", "because", "if", "when", "while",
                    "that", "which", "who", "then", "than", "as", "the", "a", "an",
                    "to", "of", "in", "on", "at", "for", "with", "from", "by"),
        # Soát khúc nhận diện: tiếng Anh tính theo chữ cái (~9/giây ở tốc độ 0,7).
        "chu_moi_giay": 3.0,
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


def slow_video(src, dst, speed=0.7, tu=None, dai=None):
    """Xuất video làm chậm: hình setpts, tiếng atempo (0.5–2.0). libx264 CRF 18
    giữ chất lượng gần gốc (ưu tiên chất lượng hơn tốc độ render).

    tu/dai (giây, theo video GỐC) → chỉ render KHÚC đó (chia đoạn video dài):
    -ss/-t đặt TRƯỚC -i, có encode lại nên cắt chính xác tới khung hình, mốc
    giờ đầu ra bắt đầu từ 0 — đúng khớp SRT của đoạn (đã trừ mốc đầu đoạn)."""
    if not FFMPEG_PATH:
        print("❌ Không tìm thấy ffmpeg trong PATH.")
        return None
    khuc = f" khúc {tu / 60:.1f}→{(tu + dai) / 60:.1f} phút gốc" if tu is not None else ""
    print(f"🎬 Đang render video chậm {speed:g}x{khuc} (dài ~{1/speed:.2f} lần)...")
    cat = ["-ss", f"{tu:.3f}", "-t", f"{dai:.3f}"] if tu is not None else []
    cmd = [
        FFMPEG_PATH, "-y", *cat, "-i", src,
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


# ---------------- Chia đoạn video dài (xem doan.py) ----------------
def _het_cau(text, lang):
    """Câu kết thúc bằng dấu kết câu của tiếng đó (bỏ dấu đóng ngoặc/nháy đi kèm)."""
    t = (text or "").rstrip().rstrip(_CLOSERS).rstrip()
    return bool(t) and t[-1] in _cfg(lang)["major"]


def chia_doan(subs, tong, phut, phut_max, lang=MAC_DINH):
    """Mốc cắt theo video ĐÃ CHẬM → [(tu_s, den_s), ...]; 1 phần tử = không chia.

    Tới mốc `phut` thì ĐỢI HẾT CÂU: lấy ranh giới đầu tiên sau mốc mà câu trước
    nó kết thúc bằng dấu kết câu; không có thì khe lặng DÀI NHẤT giữa hai câu
    trong khoảng tới `phut_max`; khoảng đó không có ranh giới nào (một câu kéo
    dài qua trần) thì cắt ngay TRƯỚC câu đang chạy qua trần. Điểm cắt đặt giữa
    khe lặng (tối đa 0,6 s sau câu) nên không câu nào bị bổ đôi. Đoạn cuối
    ngắn dưới 5 phút gộp vào đoạn trước."""
    muc, tran = phut * 60.0, phut_max * 60.0
    if tong <= tran or len(subs) < 2:
        return [(0.0, tong)]
    moc = [0.0]
    while tong - moc[-1] > tran:
        goc = moc[-1]
        dich, han = goc + muc, goc + tran
        chon, khe_max = None, -1.0
        for i in range(len(subs) - 1):
            e = subs[i][1]
            if e < dich:
                continue
            if e > han:
                break
            khe = subs[i + 1][0] - e
            t = e + min(khe / 2, 0.6)
            if _het_cau(subs[i][2], lang):
                chon = t
                break
            if khe > khe_max:
                chon, khe_max = t, khe
        if chon is None:
            sau = [s[0] for s in subs if dich <= s[0] <= han]
            chon = max(goc + 1.0, min(sau) - 0.05) if sau else han
        if chon <= goc + 1.0:
            chon = han
        moc.append(min(chon, tong))
    # Đoạn cuối quá ngắn (dưới 5 phút với đoạn 30 phút — tỉ lệ 1/6) → gộp vào
    # đoạn trước cho khỏi một lượt nạp model chỉ vì vài câu.
    if len(moc) >= 2 and tong - moc[-1] < min(300.0, muc / 6):
        moc.pop()
    return [(moc[i], moc[i + 1] if i + 1 < len(moc) else tong) for i in range(len(moc))]


def ghi_doan(doan_tg, subs, base, tag, out_dir, speed, media, lang):
    """SRT từng đoạn (mốc giờ tính từ đầu đoạn) + sổ _doan.json → tên các đoạn."""
    so = []
    for k, (tu, den) in enumerate(doan_tg, 1):
        ten = doan.ten_doan(base, k, tag)
        phan = [[s[0] - tu, min(s[1], den) - tu, s[2]] for s in subs if tu <= s[0] < den]
        write_srt(phan, os.path.join(out_dir, ten + ".srt"))
        so.append({"ten": ten, "tu_s": round(tu, 3), "den_s": round(den, 3), "cau": len(phan)})
        print(f"   ✂ đoạn {k}: {tu / 60:.1f} → {den / 60:.1f} phút "
              f"({(den - tu) / 60:.1f} phút, {len(phan)} câu)")
    p = doan.ghi_so(os.path.join(out_dir, f"{base}{tag}"), speed,
                    os.path.abspath(media), lang, so)
    print(f"💾 Sổ đoạn: {os.path.basename(p)}")
    return [d["ten"] for d in so]


def render_doan(media, doan_tg, ten_doan_ds, out_dir, speed, out_video):
    """Render video chậm TỪNG ĐOẠN từ đúng khúc của video gốc (đoạn đã có thì
    bỏ qua — chạy lại là tiếp), rồi nối -c copy thành video chậm cả bài (cho
    thumbnail / trang vùng sub; các bước ②③④ dùng video từng đoạn)."""
    parts = []
    for (tu, den), ten in zip(doan_tg, ten_doan_ds):
        dst = os.path.join(out_dir, ten + ".mp4")
        parts.append(dst)
        if os.path.isfile(dst):
            print(f"♻ Đã có {ten}.mp4 — bỏ qua render.")
            continue
        if not slow_video(media, dst, speed=speed, tu=tu * speed, dai=(den - tu) * speed):
            return False
    if os.path.isfile(out_video):
        print(f"♻ Đã có {os.path.basename(out_video)} — bỏ qua nối.")
        return True
    return doan.noi_video(parts, out_video)


# ---------------- Nhận diện theo KHÚC để Whisper không quên chấm câu ----------------
# Whisper chỉ chấm câu khi "văn bản đứng trước" có dấu câu: câu mẫu initial_prompt
# ở cửa sổ 30 s đầu, rồi (condition_on_previous_text=True) chính lời nó vừa chép
# ra. Chuỗi đó đứt một lần là đứt luôn — đo bài Trung 85 phút chạy MỘT mạch: 28
# phút đầu chấm đều (~60 dấu hết câu mỗi 5 phút), từ phút 30 về sau 0 dấu cho
# tới hết bài, mà tách vế còn tệ hơn lúc không dùng ngữ cảnh ("当个 | 鬼差",
# "三个 | 月"). Nhận diện riêng một khúc với lời mồi có dấu câu thì dấu trở lại
# ngay (phút 26–36: 0 → 134 dấu hết câu).
#
# Vì vậy: cắt audio thành các khúc ~3 phút tại chỗ im, mỗi khúc một lượt
# transcribe. Lời mồi của khúc = ĐUÔI LỜI THOẠI có dấu câu của khúc tốt gần nhất
# (đúng thứ Whisper vẫn tự dùng khi chạy một mạch), riêng khúc đầu mới dùng câu
# mẫu. Soát từng khúc, hỏng thì chạy lại khúc đó KHÔNG lời mồi, KHÔNG ngữ cảnh —
# không có dấu câu nhưng đủ chữ và Whisper tách vế sạch, build_subs cắt theo
# ranh giới vế:
#   • chép lại câu mẫu — ĐỪNG mồi câu mẫu cho từng khúc: khúc nào mở đầu bằng
#     nhạc / tiếng yếu là Whisper chép luôn "请用简体中文加上标点符号。" ra làm lời
#     thoại, rồi vì nghe theo ngữ cảnh nên lặp nó hết khúc, nuốt sạch lời thật
#     (đo: 5/16 khúc 5 phút bị vậy, một khúc 632 chữ chỉ còn 17). Nhồi câu mẫu
#     vào mọi cửa sổ bằng hotwords cũng hỏng y như thế.
#   • ra quá ít chữ so với số giây có tiếng nói (dấu hiệu chung của kiểu nuốt lời);
#   • khô dấu câu (một dãy dài không dấu nào).
KHUC_GIAY = 180.0   # độ dài một khúc
KHUC_TRE = 45.0     # được cắt muộn tới ngần này giây để rơi đúng chỗ im
DUOI_MOI = 120      # số ký tự đuôi lời thoại dùng mồi cho khúc sau
_SR = 16000


def _moc_khuc(audio):
    """Mốc cắt khúc, tính bằng MẪU: [0, ..., len(audio)]. Mỗi mốc nằm GIỮA một
    quãng im (theo VAD, cùng tham số với lúc nhận diện) nên không bổ đôi chữ nào:
    quãng im dài nhất trong KHUC_TRE giây sau mốc tròn; không có thì quãng im
    đầu tiên sau đó."""
    tong = len(audio)
    if tong <= (KHUC_GIAY + KHUC_TRE) * _SR:
        return [0, tong]
    from faster_whisper.vad import VadOptions, get_speech_timestamps
    noi = get_speech_timestamps(audio, VadOptions(**(_TRANSCRIBE_OPTS.get("vad_parameters") or {})),
                                sampling_rate=_SR)
    giua = [((b["start"] - a["end"]), (a["end"] + b["start"]) // 2)
            for a, b in zip(noi, noi[1:]) if b["start"] > a["end"]]
    moc = [0]
    while tong - moc[-1] > (KHUC_GIAY + KHUC_TRE) * _SR:
        dich = moc[-1] + KHUC_GIAY * _SR
        ung = [g for g in giua if dich <= g[1] <= dich + KHUC_TRE * _SR]
        cat = max(ung)[1] if ung else next((g[1] for g in giua if g[1] > dich), tong)
        if cat >= tong:
            break
        moc.append(int(cat))
    return moc + [tong]


def _so_chu(words):
    return sum(1 for w in words for c in w[2] if c.isalnum())


def _chuan(s):
    """Chỉ giữ chữ và số, viết thường — để so hai mẩu lời bất kể dấu câu."""
    return "".join(c for c in (s or "") if c.isalnum()).lower()


def _kho_dau(words):
    """Dãy chữ dài nhất không có dấu câu nào (đếm chữ thật) — đo Whisper có đang
    chấm câu hay không."""
    dai = cur = 0
    for w in words:
        cur += sum(1 for c in w[2] if c.isalnum())
        if w[2][-1] in _DAU_HET_VE:
            cur = 0
        dai = max(dai, cur)
    return dai


def _duoi_moi(words, lang):
    """Đuôi lời thoại của một khúc, làm lời mồi cho khúc sau: ~DUOI_MOI ký tự
    cuối, bắt đầu từ đầu một câu (bỏ mẩu câu cụt ở đầu)."""
    major = _cfg(lang)["major"]
    text = _ghep([w[2] for w in words[-120:]], lang)[-DUOI_MOI:]
    for i, c in enumerate(text[:-30]):
        if c in major:
            return text[i + 1:].lstrip(_CLOSERS + " ")
    return text


def _nhan_dien(model, audio, opts, lech, total, cfg, nhac=""):
    """Một lượt transcribe (cả file hoặc một khúc).

    Trả về (chữ, giây_có_tiếng_nói, chép_câu_mẫu): chữ = [[start, end, chữ,
    hết_vế]] với mốc giờ đã cộng `lech` giây (đầu khúc trong cả bài).

    nhac: lời mồi lấy từ đuôi khúc trước (đã _chuan). Hai segment đầu mà chỉ là
    nhắc lại một mẩu của lời mồi thì bỏ — Whisper thỉnh thoảng đọc lại câu cuối
    nó vừa được cho xem."""
    segments, info = model.transcribe(audio, **opts)
    vong = cfg.get("vong_cau_mau", ())
    words, chep, so = [], False, 0
    for seg in segments:
        text = seg.text.strip()
        if any(v in text for v in vong):
            chep = True     # Whisper chép lại câu mẫu (gặp nhạc/tiếng ồn) — bỏ
            continue
        so += 1
        if nhac and so <= 2 and len(_chuan(text)) >= 4 and _chuan(text) in nhac:
            continue
        n0 = len(words)
        if seg.words:
            for w in seg.words:
                token = w.word.strip()
                if token:
                    words.append([round(w.start + lech, 3), round(w.end + lech, 3), token, 0])
        elif text:
            # hiếm khi thiếu word-level → dùng mốc cả câu còn hơn bỏ chữ
            words.append([round(seg.start + lech, 3), round(seg.end + lech, 3), text, 0])
        if len(words) > n0:
            # chữ cuối segment. 2 = hết VẾ thật (nhận diện không ngữ cảnh: Whisper
            # tách mỗi vế một segment); 1 = chỉ là chỗ Whisper ngắt segment khi
            # nghe theo ngữ cảnh — lúc đó ranh giới thật nằm ở dấu câu, chỗ ngắt
            # segment hay rơi giữa cụm từ ("在这三十三司当个 | 鬼差,").
            words[-1][3] = 1 if opts.get("condition_on_previous_text") else 2
        den = seg.end + lech
        frac = min(den / total, 1.0) if total else 0
        mm, ss = divmod(int(den), 60)
        print(f"\r⏳ {frac * 100:5.1f}%  [{mm:02d}:{ss:02d}] {text[:40]:<40}",
              end="", flush=True)
    return words, float(getattr(info, "duration_after_vad", 0) or 0), chep


def transcribe_words(audio_path, model_name="medium", lang=MAC_DINH,
                     khong_ngu_canh=False):
    """Nhận diện và trả về danh sách chữ [[start, end, chữ, hết_vế], ...].

    hết_vế ≠ 0 ở chữ CUỐI mỗi đoạn (segment) Whisper trả về — 2 nếu khúc đó
    nhận diện không ngữ cảnh (ranh giới vế thật), 1 nếu có ngữ cảnh (chỗ ngắt
    tạm, yếu hơn dấu câu). Phải giữ mốc này:
    lúc Whisper KHÔNG chấm câu (đo bài Trung 85 phút, không ngữ cảnh: 98 dấu
    trên 11.738 chữ) nó vẫn tách đúng từng vế thành một segment riêng ("错在你" |
    "月祖代袍" | "交出生死簿"...). Vứt ranh giới đó đi thì build_subs chỉ còn biết
    đếm đủ 16 chữ là cắt — cắt giữa từ, chữ cuối câu này rơi sang đầu câu kia.

    Mặc định nhận diện theo KHÚC ~3 phút có ngữ cảnh (xem khối ghi chú phía
    trên) để có dấu câu suốt bài; khong_ngu_canh=True thì chạy một mạch không
    ngữ cảnh (nhanh hơn, nhưng tiếng Trung gần như không có dấu câu).

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

    total = get_audio_duration(audio_path) or 0
    if total:
        print(f"⏳ Thời lượng audio (đã chậm): {total / 60:.1f} phút")
    print(f"📝 Đang nhận diện tiếng {cfg['ten']} (kèm mốc giờ từng chữ)...")

    if not opts.get("condition_on_previous_text"):
        words, _noi, _chep = _nhan_dien(model, audio_path, opts, 0.0, total, cfg)
        print()
        return words

    from faster_whisper import decode_audio
    audio = decode_audio(audio_path, sampling_rate=_SR)
    total = total or len(audio) / _SR
    moc = _moc_khuc(audio)
    if len(moc) > 2:
        print(f"✂ Nhận diện theo {len(moc) - 1} khúc ~{KHUC_GIAY / 60:g} phút, cắt ở chỗ im — "
              "mỗi khúc được mồi bằng lời thoại có dấu câu ngay trước nó để Whisper "
              "chấm câu suốt bài.")
    tran = dict(opts, condition_on_previous_text=False, initial_prompt=None)
    nguong, toc = cfg.get("kho_dau"), cfg.get("chu_moi_giay", 0)
    words, duoi, lui = [], "", 0
    for a, b in zip(moc, moc[1:]):
        lech = a / _SR
        khuc, noi, chep = _nhan_dien(model, audio[a:b], dict(opts, initial_prompt=duoi or cfg["prompt"]),
                                     lech, total, cfg, nhac=_chuan(duoi))
        hong = ("chép lại câu mẫu thay vì lời thoại" if chep
                else "ra quá ít chữ so với thời lượng có tiếng nói"
                if noi >= 20 and _so_chu(khuc) < toc * noi
                else "bỏ chấm câu" if nguong and _kho_dau(khuc) > nguong else "")
        if hong:
            lui += 1
            print(f"\n   ↻ khúc {lech / 60:.0f}–{b / _SR / 60:.0f} phút: Whisper {hong} → nhận "
                  "diện lại khúc này không lời mồi, không ngữ cảnh.")
            khuc, _noi, _chep = _nhan_dien(model, audio[a:b], tran, lech, total, cfg)
        elif khuc:
            duoi = _duoi_moi(khuc, lang)
        words.extend(khuc)
    print()
    if lui:
        print(f"ℹ {lui}/{len(moc) - 1} khúc phải nhận diện lại kiểu không ngữ cảnh — các khúc đó "
              "không có dấu câu, cắt dòng theo ranh giới vế của Whisper.")
    return words


# ---------------- Ranh giới vế câu khi KHÔNG có dấu câu ----------------
# Khe lặng giữa hai chữ liền nhau (giây, theo audio đã chậm). Mốc giờ từng chữ
# của Whisper nối sát nhau; đã có khe tức là VAD vừa cắt bỏ một quãng im ≥ 0,8 s
# ở đó (hoặc faster-whisper tự rút bớt một chữ kéo quá dài sát chỗ nghỉ).
KHE_NHO = 0.3      # ≥ ngần này: chỗ nghỉ → được phép cắt dòng tại đây
KHE_CHOT = 0.7     # ≥ ngần này: hết câu → CHỐT dòng (bước ② gộp câu cũng dừng ở đây)
CHU_LAC_TOI_DA = 2  # số chữ đầu vế có thể bị dán nhầm sang trước chỗ nghỉ
CHU_QUA_DAI = 1.5  # một chữ "dài" hơn ngần này giây là đã nuốt cả quãng im cạnh nó
VE_CUT = 2         # (tiếng viết liền) vế ≤ ngần này chữ ở cuối dòng → đẩy xuống dòng kế
NHAP_SAU = 1.5     # mảnh ngắn chưa hết câu cách dòng kế dưới ngần này giây → nhập vào dòng kế
_DAU_HET_VE = set("。！？!?…，、；：,;:.—–")
_DAU_HET_CAU = set("。！？!?….")


def _bon(words):
    """Chuẩn về [start, end, chữ, hết_vế] — nhận cả bản cũ chỉ có 3 phần tử."""
    return [[w[0], w[1], w[2], int(w[3]) if len(w) > 3 else 0] for w in words]


def _het_ve(w):
    """Sau chữ này là hết một vế: Whisper tách segment ở đó, hoặc chữ mang dấu câu."""
    return bool(w[3]) or w[2][-1] in _DAU_HET_VE


def co_ranh_gioi(words):
    """Danh sách chữ có kèm cờ hết_vế không? (_words.json lưu trước 18/11/2026
    chỉ có 3 phần tử — không dựng lại được ranh giới vế, phải nhận diện lại.)"""
    return bool(words) and all(len(w) > 3 for w in words)


def sua_chu_lac(words):
    """Kéo 1–2 chữ ĐẦU VẾ bị dán nhầm sang trước chỗ nghỉ về đúng sau chỗ nghỉ.

    Whisper căn mốc giờ từng chữ trên audio ĐÃ BỎ quãng im (VAD), rồi faster-
    whisper trả mốc về trục giờ thật theo điểm giữa của từng chữ. Chữ đầu tiên
    sau chỗ nghỉ hay nuốt luôn phần đệm quanh vết cắt nên điểm giữa của nó rơi
    sang khúc TRƯỚC — thành ra nó được ghi giờ sát câu trước, cách phần còn lại
    của chính vế mình cả quãng nghỉ: "那我便 | 你们 ‖17 s‖ 四人速来紫霄宫见我".
    Đo bài 85 phút: 191 chỗ nghỉ ≥ 0,5 s lọt vào giữa một vế, 180 chỗ nằm ngay
    sau 1–2 chữ đầu (chỉ 2 chỗ sát cuối) — lệch có hệ thống, không phải ngẫu
    nhiên. Để nguyên thì phụ đề (và giọng đọc ở bước ③) của câu đó vào sớm đúng
    bằng quãng nghỉ, còn cắt dòng theo chỗ nghỉ thì chữ đầu câu dính vào đuôi
    câu trước.

    Sửa: xét từng chỗ nghỉ ≥ KHE_NHO nằm GIỮA một câu (chữ đứng trước chỗ nghỉ
    không kết thúc segment, không mang dấu hết câu). Nếu trước chỗ nghỉ chỉ có
    1–2 chữ tính từ ranh giới vế gần nhất (chỗ Whisper tách segment hoặc một
    dấu câu) thì đó là chữ lạc: đặt chúng ngay TẠI mốc của chữ kế tiếp (đầu khúc
    tiếng nói sau chỗ nghỉ). Chữ lạc tự nó mang dấu phẩy cũng tính ("我, ‖nghỉ‖
    地府鬼差。" — "我" thuộc câu sau).

    Soi gương, hiếm hơn nhiều: chữ CUỐI câu bị đẩy sang SAU chỗ nghỉ ("不得进入
    其他区 ‖1,6 s‖ 域") → kéo về sát chữ trước nó (chỉ khi trước đó có ≥ 3 chữ
    cùng vế, để không giành với luật chữ đầu ở các vế ngắn).

    Cùng một gốc: chữ "kéo dài" hơn CHU_QUA_DAI giây (có chữ ghi 28 giây vì
    đứng sau một quãng nhạc) thật ra là quãng im + chữ. Quãng im dồn về ĐẦU chữ
    đứng sau nó, nên rút đầu chữ lại sát cuối; riêng chữ cuối vế thì rút đuôi.

    Trả về (danh sách mới, số chữ đã sửa).
    """
    out = _bon(words)
    if not out:
        return out, 0
    dai = sorted(w[1] - w[0] for w in out)
    tran = max(2 * dai[len(dai) // 2], 0.2)
    n, dem = len(out), 0

    def _het_cau(w):
        return bool(w[3]) or w[2][-1] in _DAU_HET_CAU

    for k, w in enumerate(out):
        if w[1] - w[0] > CHU_QUA_DAI:
            dau_ve = k == 0 or _het_ve(out[k - 1])
            if _het_ve(w) and not dau_ve:
                w[1] = w[0] + tran
            else:
                w[0] = w[1] - tran
            dem += 1
    for k in range(n - 1):
        if out[k + 1][0] - out[k][1] < KHE_NHO or _het_cau(out[k]):
            continue                     # không nghỉ, hoặc nghỉ đúng chỗ hết câu
        # Chữ đầu: trước chỗ nghỉ có mấy chữ kể từ ranh giới vế gần nhất?
        lac = next((c for c in range(1, CHU_LAC_TOI_DA + 1)
                    if k - c < 0 or _het_ve(out[k - c])), 0)
        if lac:
            # Đặt chữ lạc ĐÚNG TẠI mốc chữ kế tiếp (dài 0), KHÔNG xếp lùi ra trước
            # nó: mốc chữ kế tiếp đã là đầu khúc tiếng nói (còn sớm hơn tiếng thật
            # ~0,4 s đệm của VAD); lùi thêm nữa thì câu vào sớm cả giây — đo 19/11:
            # "故土住手!" tiếng thật ở 60,4 s, xếp lùi ra 59,4 s, đặt tại chỗ là 59,9 s.
            moc = out[k + 1][0]
            for j in range(k, k - lac, -1):
                out[j][0] = out[j][1] = moc
            dem += lac
        elif (_het_cau(out[k + 1]) and k >= 2
              and not any(_het_ve(out[j]) for j in range(k - 2, k + 1))):
            # chữ cuối câu lạc sang sau chỗ nghỉ → về đúng cuối chữ trước nó (dài 0)
            out[k + 1][0] = out[k + 1][1] = out[k][1]
            dem += 1
    return out, dem


def build_subs(words, max_chars=16, hard_max=16, min_chars=4, min_dur=0.6,
               lang=MAC_DINH):
    """Ghép chữ (có mốc giờ) thành các câu phụ đề theo dấu câu của tiếng `lang`.

    Trả về danh sách [start, end, text]. start/end lấy đúng mốc chữ đầu/cuối.

    Chỗ ĐƯỢC cắt dòng, ngoài dấu câu: cuối mỗi vế Whisper đã tách (cờ hết_vế)
    và chỗ nghỉ ≥ KHE_NHO — nhờ vậy bài không có dấu câu nào vẫn cắt đúng ranh
    giới vế chứ không cắt giữa từ. Chỗ nghỉ ≥ KHE_CHOT thì chốt dòng luôn như
    gặp dấu hết câu (một dòng phụ đề không vắt qua quãng im dài).

    Vượt trần hard_max thì CẮT LUI về chỗ được cắt gần nhất trong dòng (phần sau
    chuyển sang dòng kế), và dòng không kết bằng từ nối của câu sau (否则, 而且,
    and, so... — _lui_tu_noi). Dòng không có chỗ cắt nào tức là MỘT vế dài hơn
    cả dòng: chia vế đó thành các phần cân nhau, ưu tiên chỗ người nói ngừng
    (_cat_giua_ve) — không cắt ở đúng trần để rồi rớt 1–2 chữ đuôi sang dòng kế.

    Chỗ cắt có MẠNH có YẾU: dấu câu và ranh giới vế thật (cờ 2 — khúc nhận
    diện không ngữ cảnh) là mạnh; chỗ Whisper ngắt segment lúc nghe theo ngữ
    cảnh (cờ 1) và chỗ nghỉ ngắn là yếu, hay rơi giữa cụm từ. Cắt lui ưu tiên
    chỗ mạnh: "苏藩啊,你很有才能,| 在这三十三司当个 ¦ 鬼差," cắt ở dấu phẩy (|)
    chứ không ở chỗ ngắt tạm (¦).

    Tiếng viết liền (Trung): hai vế nằm chung dòng mà giữa chúng không có dấu
    câu thì cách nhau MỘT khoảng trắng — quy ước phụ đề tiếng Trung, để người
    đọc lẫn máy dịch ở bước ② thấy ranh giới vế ("错在你 月祖代袍"). Chỉ chèn ở
    ranh giới vế thật (cờ 2), không chèn ở chỗ ngắt yếu.

    max_chars = 0: KHÔNG giới hạn bề ngang — mỗi dòng là một câu trọn, chỉ chốt
    ở dấu hết câu hoặc chỗ nghỉ ≥ KHE_CHOT (hard_max bị bỏ qua). Còn hai lưới
    an toàn lấy từ bảng NGON_NGU: câu dài quá tran_cau thì cắt lui về dấu phẩy;
    dòng chưa có dấu câu nào mà đã dài tới tran_khong_dau thì chốt ở chỗ cắt kế.
    """
    subs = []           # [start, end, text, kết_ở_ranh_giới_vế]
    cur = []            # các chữ (ws, we, token, mem, ve) của dòng đang gom —
                        # mem: sau chữ này là chỗ được cắt (hết segment / chỗ nghỉ)
                        # ve:  sau chữ này là hết một VẾ thật (cờ 2)
    cfg = _cfg(lang)
    tran_kd = 0
    if not max_chars:
        max_chars = hard_max = cfg.get("tran_cau", 70)
        tran_kd = cfg.get("tran_khong_dau", 0)
    major, minor = cfg["major"], cfg["minor"]
    breaks = major + minor
    lien = not cfg["noi"]              # tiếng viết liền → tự chèn khoảng trắng
    noi_sau = set(cfg.get("noi_sau", ()))

    words, _lac = sua_chu_lac(words)
    n = len(words)
    dai = sorted(w[1] - w[0] for w in words) or [0.0]
    trung_vi = dai[len(dai) // 2]

    def _cho_cat(t):
        """Sau chữ t (của dòng đang gom) được phép cắt dòng."""
        return t[3] or any(c in breaks for c in t[2])

    def _cho_manh(t):
        """…và đó là chỗ cắt MẠNH: dấu câu hoặc hết một vế thật."""
        return t[4] or any(c in breaks for c in t[2])

    def _cat_lui():
        """Chỗ cắt lui cho dòng đang gom: chỗ được cắt gần cuối nhất; nếu đó là
        chỗ yếu mà trước nó có chỗ mạnh chừa lại ≥ 40% dòng thì lấy chỗ mạnh."""
        cut = next((k + 1 for k in range(len(cur) - 1, -1, -1) if _cho_cat(cur[k])), None)
        if cut is None or _cho_manh(cur[cut - 1]):
            return cut
        manh = next((k + 1 for k in range(cut - 2, -1, -1) if _cho_manh(cur[k])), None)
        if manh and _nchars(_text(cur[:manh]), lang) >= 0.4 * hard_max:
            return manh
        return cut

    def _lui_tu_noi(cut):
        """cur[:cut] kết bằng từ nối của câu sau → lùi điểm cắt về trước nó.

        Trung: xét cả VẾ cuối dòng — là từ nối (Whisper tách "否则" thành một vế
        riêng) hoặc một vế cụt ≤ VE_CUT chữ. Hàm này chỉ chạy khi câu sau nối
        liền không nghỉ (có nghỉ ≥ KHE_CHOT thì dòng đã chốt từ trước), mà vế
        cụt nói liền vào câu sau thì gần như luôn là lời gọi / lời dẫn của câu
        đó ("好了 | 你就别再谦虚了", "七哥 | 你感觉如何").
        Anh: xét TỪ cuối dòng. Sau nó mà có dấu câu thì người nói dừng ở đó thật
        — để yên. Không lùi tới mức dòng rỗng."""
        for _ in range(2):
            last = cur[cut - 1]
            if any(c in breaks for c in last[2]):
                break
            p = cut - 1
            if lien:
                while p > 0 and not _cho_cat(cur[p - 1]):
                    p -= 1
                tu = "".join(t[2] for t in cur[p:cut])
                lung = tu in noi_sau or _nchars(tu, lang) <= VE_CUT
            else:
                lung = last[2].lower() in noi_sau
            if p <= 0 or not lung:
                break
            cut = p
        return cut

    def _cat_giua_ve(i, bo=0):
        """cur là phần đầu của MỘT vế dài hơn cả dòng (không có chỗ cắt nào);
        chữ thứ i sắp thêm vào làm vượt trần. Trả về số chữ đầu của cur nên chốt.

        bo > 0: cur mở đầu bằng `bo` chữ là một từ nối trơ trọi, sau đó mới tới
        vế. Vế ấy tự nó vừa một dòng thì trả None (đừng bổ đôi một vế lành chỉ
        để từ nối có chỗ bám); không vừa thì chia cả cụm, từ nối theo nửa đầu.

        Nhìn tới hết vế để biết nó dài bao nhiêu. Vừa hai dòng thì chia sao cho
        không phần nào ngắn hơn min_chars; dài hơn thì phần đầu chiếm nửa dòng
        trở lên. Trong khoảng cho phép, chọn chỗ mà chữ ĐỨNG SAU điểm cắt kéo
        dài bất thường (≥ 1,6 lần trung vị) — Whisper dồn quãng ngừng vào đầu
        chữ kế tiếp, nên chữ như vậy mở đầu một nhịp nói mới ("恐怕我西方教 | 也唯
        有那几位…", chữ 也 dài gấp 3,4 lần trung vị). Không có chỗ nào như thế
        thì chia đôi."""
        sau = []
        for k in range(i, n):
            w = words[k]
            khe_k = words[k + 1][0] - w[1] if k + 1 < n else KHE_CHOT
            sau.append((w[0], w[1], w[2], False, False))
            if (_het_ve(w) or khe_k >= KHE_NHO
                    or _nchars(_text(cur + sau), lang) > 2 * hard_max):
                break
        if bo and _nchars(_text(cur[bo:] + sau), lang) <= hard_max:
            return None
        tong = _nchars(_text(cur + sau), lang)
        if tong <= 2 * hard_max:
            lo, hi, dich = max(tong - hard_max, min_chars), min(hard_max, tong - min_chars), tong / 2
        else:
            lo, hi, dich = hard_max / 2, hard_max, hard_max
        ung = [(k, d) for k, d in ((k, _nchars(_text(cur[:k]), lang))
                                   for k in range(1, len(cur) + 1)) if lo <= d <= hi]
        if not ung:
            return None

        def _diem(kd):
            k, d = kd
            ke = cur[k] if k < len(cur) else words[i]
            keo = ke[1] - ke[0]
            return (keo if keo >= 1.6 * trung_vi else 0.0, -abs(d - dich))
        return max(ung, key=_diem)[0]

    def _text(part):
        toks = [p[2] for p in part]
        if lien:
            # khoảng trắng SAU chữ cuối một vế thật (không dấu câu), trừ chữ cuối dòng
            toks = [p[2] + " " if p[4] and k < len(part) - 1 and p[2][-1] not in _PUNCT else p[2]
                    for k, p in enumerate(part)]
        return _ghep(toks, lang)

    def _flush(upto=None):
        """Chốt cur[:upto] thành một dòng; phần còn lại giữ làm dòng kế."""
        nonlocal cur
        part, rest = (cur, []) if upto is None else (cur[:upto], cur[upto:])
        text = _text(part)
        if text.strip():
            subs.append([part[0][0], max(w[1] for w in part), text, part[-1][4]])
        cur = rest

    for i, (ws, we, token, het) in enumerate(words):
        khe = words[i + 1][0] - we if i + 1 < n else 0.0
        mem = bool(het) or khe >= KHE_NHO
        tok = (ws, we, token, mem, het == 2)
        # Token CHỈ có dấu câu (dấu ” sau 。, hay dấu : ， đứng riêng): dán vào
        # dòng đang gom — chưa gom gì thì dán vào dòng vừa chốt. Không bao giờ
        # vì một cái dấu mà cắt dòng hay mở dòng mới chỉ chứa dấu.
        if _chi_dau(token):
            if cur:
                cur.append(tok)
                if any(c in major for c in token) or khe >= KHE_CHOT:
                    _flush()
            elif subs:
                subs[-1][2] += token
                subs[-1][1] = max(subs[-1][1], we)
            continue
        # TRẦN CỨNG: thêm chữ này mà vượt hard_max thì chốt dòng hiện tại TRƯỚC,
        # ưu tiên CẮT LUI về chỗ được cắt gần nhất trong dòng — sau dấu câu, cuối
        # vế hay chỗ nghỉ (không cắt cụt giữa cụm từ ở đúng chữ 16). while: phần
        # lui sang dòng kế cộng chữ mới vẫn có thể vượt trần → cắt tiếp cho tới
        # khi đủ chỗ.
        while cur and _nchars(_text(cur + [tok]), lang) > hard_max:
            cut = _cat_lui()
            if cut is not None:
                cut = _lui_tu_noi(cut)
                # Chỗ cắt duy nhất chỉ chừa lại một từ nối trơ trọi ("因此" + một vế
                # dài hơn cả dòng): đừng tách riêng từ nối — chia cả cụm như một vế
                # dài, từ nối đi cùng nửa đầu ("因此 卑职认为他有能力 / 担当…之位").
                dau = "".join(t[2] for t in cur[:cut]) if lien else " ".join(
                    t[2].lower() for t in cur[:cut])
                if dau in noi_sau:
                    cut = _cat_giua_ve(i, bo=cut) or cut
            else:
                cut = _cat_giua_ve(i)
            _flush(None if cut in (None, len(cur)) else cut)
        cur.append(tok)

        if any(c in major for c in token) or khe >= KHE_CHOT:
            _flush()
            continue
        # Dòng đã đủ dài và đang đứng ở chỗ cắt MẠNH → chốt. Ở chỗ yếu thì chưa:
        # để chữ kế tiếp làm vượt trần rồi _cat_lui chọn giữa chỗ này và dấu câu
        # đứng trước nó.
        dai_dong = _nchars(_text(cur), lang)
        if dai_dong >= max_chars and (token[-1] in minor or tok[4]):
            cut = _lui_tu_noi(len(cur))
            _flush(None if cut == len(cur) else cut)
        # Không giới hạn bề ngang mà dòng chưa có lấy một dấu câu (khúc Whisper
        # không chấm câu): không biết câu hết ở đâu → đủ tran_khong_dau thì chốt
        # tại chỗ cắt này, đừng gom tiếp tới chỗ nghỉ kế (có khi 80–90 chữ).
        elif (tran_kd and mem and dai_dong >= tran_kd
              and not any(c in breaks for t in cur for c in t[2])):
            cut = _lui_tu_noi(len(cur))
            _flush(None if cut == len(cur) else cut)
    if cur:
        _flush()

    def _noi_dong(a, b, ranh):
        """Nối mảnh b vào dòng a. Tiếng viết liền: a kết ở ranh giới vế mà chỗ
        nối không có dấu câu thì cách một khoảng trắng như trong _text."""
        if lien and ranh and a and b and a[-1] not in _PUNCT and b[0] not in _PUNCT:
            return a + " " + b
        return _ghep([a, b], lang)

    # Gộp mảnh quá ngắn (ít chữ hoặc hiện quá nhanh) vào câu liền trước,
    # miễn là gộp xong không phình quá hard_max và hai câu nằm sát nhau. Hai
    # loại mảnh KHÔNG gộp ngược vì chúng thuộc về câu SAU, gộp là quay về lỗi cũ:
    # từ nối trơ trọi (vừa được đẩy khỏi đuôi dòng trước), và mảnh mở đầu câu mới
    # (dòng trước đã hết câu bằng 。！？ còn mảnh này thì chưa: "…见我。" + "我,").
    def _het(text):
        t = text.rstrip().rstrip(_CLOSERS).rstrip()
        return bool(t) and t[-1] in major

    merged = []
    for s in subs:
        too_small = ((_nchars(s[2], lang) < min_chars or (s[1] - s[0]) < min_dur)
                     and s[2].strip().lower() not in noi_sau
                     and not (merged and _het(merged[-1][2]) and not _het(s[2])))
        if merged:
            gop = _noi_dong(merged[-1][2], s[2], merged[-1][3])
        if (merged and too_small
                and _nchars(gop, lang) <= hard_max
                and s[0] - merged[-1][1] < 1.0):
            merged[-1][1] = s[1]
            merged[-1][2] = gop
            merged[-1][3] = s[3]
        else:
            merged.append(s)

    # Mảnh ngắn CHƯA hết câu còn sót lại (lời gọi "陆冈,", "可眼下", từ nối trơ
    # trọi) là phần mở đầu của câu SAU: nhập vào dòng kế nếu hai dòng cách nhau
    # dưới NHAP_SAU giây và nhập xong vẫn vừa trần.
    out = []
    for s in merged:
        p = out[-1] if out else None
        if (p and not _het(p[2]) and s[0] - p[1] < NHAP_SAU
                and (_nchars(p[2], lang) < min_chars or (p[1] - p[0]) < min_dur)):
            gop = _noi_dong(p[2], s[2], p[3])
            if _nchars(gop, lang) <= hard_max:
                out[-1] = [p[0], s[1], gop, s[3]]
                continue
        out.append(s)
    return [s[:3] for s in out]


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
                        help="Model whisper: tiny/base/small/medium/large-v3-turbo/large-v3 (mặc định medium).")
    parser.add_argument("--max-chars", type=int, default=None,
                        help="Số chữ tối đa mỗi dòng SRT: đủ mức này thì ngắt tại dấu phụ. "
                             "0 = KHÔNG giới hạn, mỗi dòng một câu trọn (mặc định: Trung 0 · "
                             "Anh 42 ký tự).")
    parser.add_argument("--hard-max", type=int, default=None,
                        help="TRẦN CỨNG: không dòng nào vượt mức này — vượt thì cắt lui "
                             "về dấu câu gần nhất trong dòng (mặc định bằng --max-chars; "
                             "bỏ qua khi --max-chars 0).")
    parser.add_argument("--min-chars", type=int, default=None,
                        help="Câu ngắn hơn mức này bị gộp vào câu trước (mặc định 4 chữ Hán · 10 ký tự Anh).")
    parser.add_argument("--pad", type=float, default=0.2,
                        help="Nới đuôi mỗi câu thêm N giây, không đè câu sau (mặc định 0.2; 0 = tắt).")
    parser.add_argument("--no-video", action="store_true",
                        help="Chỉ tạo SRT, bỏ qua bước render video chậm.")
    parser.add_argument("--khong-ngu-canh", action="store_true",
                        help="Nhận diện một mạch, KHÔNG dùng ngữ cảnh câu trước: nhanh "
                             "hơn (Trung ~1,6 lần, Anh ~3 lần) nhưng Whisper quên chấm "
                             "câu — dòng chỉ còn cắt theo ranh giới vế (chỉ nên dùng "
                             "khi cần bản nháp gấp).")
    parser.add_argument("--redo-asr", action="store_true",
                        help="Nhận diện lại từ đầu, bỏ qua file *_words.json đã lưu.")
    parser.add_argument("--no-dich", action="store_true",
                        help="Không tự dịch sang tiếng Việt sau khi ra SRT tiếng gốc.")
    parser.add_argument("--chia-doan", type=float, default=0.0,
                        help="Video dài: CHIA ĐOẠN cỡ này (phút, theo video đã chậm), cắt "
                             "tại chỗ HẾT CÂU sau mốc; 0 = không chia. Mỗi đoạn một video "
                             "chậm + SRT riêng (<tên>_d01_x0.7…) kèm sổ _doan.json; các "
                             "bước sau chạy từng đoạn qua chay_doan.py rồi ghép lại.")
    parser.add_argument("--chia-doan-max", type=float, default=0.0,
                        help="Muộn nhất phải cắt ở phút này (mặc định = chia-doan + 5).")
    parser.add_argument("--out-dir", default=os.path.join(SCRIPT_DIR, "output"),
                        help="Thư mục lưu kết quả (mặc định myvideo/output).")
    args = parser.parse_args()

    cfg = _cfg(args.lang)
    # --max-chars 0 = không giới hạn (không được hiểu là "chưa truyền" rồi rơi về mặc định).
    max_chars = cfg["max_chars"] if args.max_chars is None else max(args.max_chars, 0)
    hard_max = (args.hard_max or max_chars) if max_chars else 0
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
        words = None
        if os.path.isfile(words_json) and not args.redo_asr:
            try:
                with open(words_json, encoding="utf-8-sig") as f:
                    words = [list(w) for w in json.load(f)]
            except (OSError, ValueError, TypeError) as e:
                # Tệp hỏng (ghi dở lúc máy tắt...) không được chặn cả bước ①.
                print(f"⚠️ Không đọc được {os.path.basename(words_json)} ({e}) → nhận diện lại.")
                words = None
            if words is None:
                pass
            elif co_ranh_gioi(words):
                print(f"♻ Dùng lại mốc giờ từng chữ đã lưu: {os.path.basename(words_json)}"
                      "  (--redo-asr nếu muốn nhận diện lại)")
            else:
                # Bản lưu trước 18/11/2026 không ghi ranh giới vế câu của Whisper:
                # dùng lại thì bài không dấu câu vẫn bị cắt cứng giữa từ như cũ.
                print(f"♻ {os.path.basename(words_json)} là bản cũ, thiếu ranh giới "
                      "vế câu → nhận diện lại để cắt câu cho đúng.")
                words = None
        if words is None:
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

        # 3a. CHIA ĐOẠN (video dài, --chia-doan): mốc cắt chọn theo kết quả nhận
        # diện — đợi HẾT CÂU sau mốc rồi mới cắt (chia_doan / doan.py). Mỗi đoạn
        # một SRT riêng + sổ _doan.json; video chậm từng đoạn render ở bước 4.
        # Các bước ②③④ chạy từng đoạn qua chay_doan.py rồi ghép lại.
        doan_tg, ten_doan_ds = [], []
        so_doan = doan.so_path(os.path.join(args.out_dir, f"{base}{tag}"))
        if args.chia_doan > 0:
            tong = ((get_audio_duration(args.media) or 0) / args.speed) or subs[-1][1]
            phut_max = args.chia_doan_max or (args.chia_doan + 5)
            doan_tg = chia_doan(subs, tong, args.chia_doan, phut_max, lang=args.lang)
            if len(doan_tg) >= 2:
                print(f"✂ Video dài {tong / 60:.1f} phút (đã chậm) → chia {len(doan_tg)} đoạn "
                      f"~{args.chia_doan:g} phút, cắt ở chỗ hết câu:")
                ten_doan_ds = ghi_doan(doan_tg, subs, base, tag, args.out_dir,
                                       args.speed, args.media, args.lang)
            else:
                doan_tg = []
                print(f"✂ Video {tong / 60:.1f} phút ≤ {phut_max:g} phút — không chia đoạn.")
        if not doan_tg and os.path.isfile(so_doan):
            # Lần này không chia (tắt ô / video ngắn) → bỏ sổ cũ kẻo bước sau tưởng
            # vẫn chia; file đoạn cũ để nguyên (xoá được thì phải khôi phục được).
            os.remove(so_doan)
            print(f"🧹 Bỏ sổ đoạn cũ {os.path.basename(so_doan)} (lần này không chia).")

        # 3b. Tự dịch sang tiếng Việt: gửi SRT lên Gemini (extension/Firefox) →
        # lưu _vi.srt + bản song ngữ. Lỗi dịch KHÔNG làm hỏng cả lượt — SRT tiếng
        # gốc đã lưu, chạy lại dich_srt.py là dịch tiếp (file tiến độ _vi.partial.json).
        if not args.no_dich and doan_tg:
            dich_script = os.path.join(SCRIPT_DIR, "dich_srt.py")
            for ten in ten_doan_ds:
                if os.path.isfile(os.path.join(args.out_dir, ten + "_vi.srt")):
                    print(f"♻ Đã có {ten}_vi.srt — bỏ qua.")
                    continue
                print(f"🌐 Dịch đoạn {ten} qua Gemini...")
                ret = subprocess.run([sys.executable, dich_script,
                                      os.path.join(args.out_dir, ten + ".srt"),
                                      "--lang", args.lang])
                if ret.returncode != 0:
                    print(f"⚠️ Dịch đoạn {ten} chưa xong — chạy lại dich_srt.py cho đoạn đó.")
        elif not args.no_dich:
            out_vi = f"{os.path.splitext(out_srt)[0]}_vi.srt"
            if os.path.isfile(out_vi):
                print(f"♻ Đã có bản dịch {os.path.basename(out_vi)} — bỏ qua bước dịch "
                      "(xoá file đó nếu muốn dịch lại).")
            else:
                print("🌐 Đang dịch sang tiếng Việt qua Gemini (Chrome Extension, "
                      "Firefox dự phòng)...")
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
        if not args.no_video and doan_tg:
            if not render_doan(args.media, doan_tg, ten_doan_ds, args.out_dir,
                               args.speed, out_video):
                sys.exit(1)
        elif not args.no_video:
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
