# -*- coding: utf-8 -*-
"""
video_gansub_cung.py — VẼ CỨNG (burn/hardsub) phụ đề SRT vào video đã làm chậm,
tuỳ chọn THAY luôn tiếng bằng audio TTS đã sắp xếp.

Ba việc của bước này đều BỎ ĐƯỢC, tự do phối:
  • vẽ sub  — bỏ --srt là không vẽ chữ nào (video sạch, chỉ thay tiếng).
  • che mờ  — không có --che-sub-goc/--vung là để nguyên sub gốc đốt trong hình.
  • thay tiếng — không có --audio là giữ tiếng gốc.
Bỏ cả vẽ sub lẫn che mờ thì HÌNH GIỮ NGUYÊN: chỉ ghép lại tiếng (-c:v copy),
không encode lại nên nhanh và không mất tí chất lượng nào.

KIỂU phụ đề chọn bằng --kieu <tên> — kho kiểu nằm ở myvideo/kieusub_mau/*.json
(xem myvideo/kieusub.py): hộp bo góc cổ điển, viền đậm, karaoke nhuộm màu,
Hormozi hiện từng chữ, bật từng từ… Mặc định "hopbo" — y hệt sub myvoice cũ.

Cách dùng:
    # gắn sub Việt vào video chậm (tiếng giữ nguyên tiếng gốc)
    python video_gansub_cung.py "output/…_x0.7.mp4" --srt "output/…_x0.7_vi.srt"

    # KHÔNG vẽ sub, chỉ thay tiếng Việt (hình giữ nguyên, không encode lại)
    python video_gansub_cung.py "output/…_x0.7.mp4" --audio "output/…_x0.7_vi_audio.wav"

    # bản TTS hoàn chỉnh: sub ĐÃ SẮP XẾP + thay tiếng bằng giọng Việt
    python video_gansub_cung.py "output/…_x0.7.mp4" \
        --srt "output/…_x0.7_vi_sapxep.srt" --audio "output/…_x0.7_vi_audio.wav"

    --kieu …    kiểu phụ đề (tên file trong kieusub_mau, mặc định hopbo).
    --font/--mau/--mau-vien/--cochu/--vitri  đè font · màu chữ · màu viền ·
                cỡ chữ (%) · vị trí chữ (% chiều cao từ đáy) của kiểu.
    --cpu       ép encode CPU (libx264) — dùng khi GPU đang bận TTS/nhận diện.
    --out …     tên video kết quả (mặc định: <video>_sub.mp4).

Dòng quá dài tự xuống dòng ở ranh giới từ (wrap_sentence của video_gansub, chia
đều để không có dòng mồ côi); SRT song ngữ (2 dòng/câu) giữ nguyên 2 dòng.
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

SCRIPT_DIR = Path(__file__).resolve().parent
MYVOICE_SCRIPTS = SCRIPT_DIR.parent / "myvoice" / "scripts"
sys.path.insert(0, str(MYVOICE_SCRIPTS))
sys.path.insert(0, str(SCRIPT_DIR))
from video_gansub import has_nvenc, wrap_sentence  # noqa: E402
import kieusub  # noqa: E402
import timvungsub  # noqa: E402

MAX_LINE_CHARS = 50          # cùng mặc định --max-chars của video_gansub.py

_TS = re.compile(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})")


def parse_srt_multiline(path):
    """Đọc SRT → list (start_s, end_s, text) — GIỮ nguyên xuống dòng trong câu
    (bản song ngữ có 2 dòng/câu; dich_srt.parse_srt nối mất nên không dùng)."""
    content = Path(path).read_text(encoding="utf-8-sig")
    cues = []
    for block in re.split(r"\n\s*\n", content.strip()):
        lines = [l for l in block.splitlines() if l.strip()]
        ti = next((i for i, l in enumerate(lines) if len(_TS.findall(l)) >= 2), None)
        if ti is None:
            continue
        m = _TS.findall(lines[ti])
        def sec(h, mi, s, ms):
            return int(h) * 3600 + int(mi) * 60 + int(s) + int(ms) / 1000
        text = "\n".join(l.strip() for l in lines[ti + 1:]).strip()
        if text:
            cues.append((sec(*m[0]), sec(*m[1]), text))
    return cues


def wrap_cue(text, max_chars=MAX_LINE_CHARS):
    """Mỗi dòng của câu quá dài → chia đều tại ranh giới từ (wrap_sentence)."""
    out = []
    for line in text.split("\n"):
        out.extend([line] if len(line) <= max_chars
                   else wrap_sentence(line, max_chars))
    return "\n".join(out)


def burn(video, out_path, ass_path=None, audio=None, force_cpu=False, vung=None):
    """Dựng video kết quả. Ba phần đều tuỳ chọn, bỏ hết cũng chạy:

    `ass_path` → vẽ cứng phụ đề (None = không vẽ chữ nào).
    `vung` (dict y0/y1 của timvungsub) → LÀM MỜ dải đó suốt video để che sub
    gốc đốt sẵn, rồi mới vẽ sub Việt đè lên trên dải mờ (None = không che).
    `audio` → THAY tiếng bằng file này (None = giữ tiếng gốc).

    Không vẽ sub mà cũng không che mờ = hình không đổi một pixel nào → -c:v copy
    (ghép lại tiếng thôi): nhanh hơn hẳn và không mất chất lượng vì encode lại.

    Mô phỏng burn_subs của video_gansub (NVENC ưu tiên, lỗi tự lùi CPU) nhưng
    thêm được nhánh thay audio nên viết lại cmd ở đây.
    """
    # Tên file dính ký tự ĐẶC BIỆT của filtergraph (' , ; [ ] =) — như dấu '
    # trong "Can't" — thì ffmpeg nuốt/hiểu sai ký tự đó và đi mở một tên khác
    # ("Unable to open … Cant …"). Escape hai tầng của ffmpeg rất dễ trật, nên
    # chép .ass sang tên tạm an toàn cùng thư mục rồi vẽ từ bản đó, xong xoá.
    tmp_ass = None
    if ass_path and re.search(r"[\\'\[\],;:=]", ass_path.name):
        tmp_ass = ass_path.with_name(f"~sub_{os.getpid()}.ass")
        tmp_ass.write_bytes(ass_path.read_bytes())
    # fontsdir: kho font riêng myvideo/fonts (Anton, Bangers…) — không cần cài font.
    sub_vf = (f"subtitles={(tmp_ass or ass_path).name}"
              f"{kieusub.fontsdir_arg(ass_path.parent)}"
              if ass_path else "")
    if vung:
        y0, day = int(vung["y0"]), int(vung["y1"]) - int(vung["y0"])
        sigma = max(10, min(30, day // 4))       # blur đủ tan chữ, theo độ dày dải
        vf = (f"split[goc][mo];"
              f"[mo]crop=iw:{day}:0:{y0},gblur=sigma={sigma}[dai];"
              f"[goc][dai]overlay=0:{y0}")
        if sub_vf:
            vf += "," + sub_vf
    else:
        vf = sub_vf

    def build_cmd(gpu):
        codec = (["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "19"]
                 if gpu else ["-c:v", "libx264", "-preset", "medium", "-crf", "18"])
        cmd = ["ffmpeg", "-y", "-i", str(Path(video).resolve())]
        if audio:
            # -map 1:a: chỉ lấy audio TTS — tiếng gốc của video TẮT hẳn.
            # loudnorm -14 LUFS: chuẩn âm lượng YouTube, video nào cũng đều tai.
            cmd += ["-i", str(Path(audio).resolve()),
                    "-map", "0:v", "-map", "1:a",
                    "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", "48000",
                    "-c:a", "aac", "-b:a", "192k", "-shortest"]
        else:
            cmd += ["-c:a", "copy"]
        cmd += (["-vf", vf, *codec, "-pix_fmt", "yuv420p"] if vf
                else ["-c:v", "copy"])
        cmd += ["-movflags", "+faststart", "-stats", "-loglevel", "warning",
                str(Path(out_path).resolve())]
        return cmd

    # cwd = thư mục chứa .ass để filter subtitles= chỉ cần TÊN file (đường dẫn
    # Windows có dấu hai chấm, nhét vào filtergraph là hỏng cú pháp).
    cwd = str((ass_path or Path(out_path)).parent)
    if not vf:
        print("🎬 Hình giữ nguyên (copy) — chỉ ghép lại tiếng.")
        return subprocess.run(build_cmd(False), cwd=cwd).returncode == 0
    use_gpu = (not force_cpu) and has_nvenc()
    print("🎬 Encode:", "GPU (h264_nvenc)" if use_gpu else "CPU (libx264)")
    try:
        r = subprocess.run(build_cmd(use_gpu), cwd=cwd)
        if r.returncode != 0 and use_gpu:
            print("   GPU lỗi, chuyển sang CPU (libx264)…")
            r = subprocess.run(build_cmd(False), cwd=cwd)
        return r.returncode == 0
    finally:
        if tmp_ass is not None:
            try:
                tmp_ass.unlink()
            except OSError:
                pass


def main():
    parser = argparse.ArgumentParser(
        description="Vẽ cứng phụ đề (kiểu khung bo góc của myvoice) vào video.")
    parser.add_argument("video", help="Video nền (thường là …_x0.7.mp4).")
    parser.add_argument("--srt", default="",
                        help="File SRT cần vẽ cứng. BỎ TRỐNG = không vẽ chữ nào "
                             "(video sạch — dùng khi chỉ muốn thay tiếng).")
    parser.add_argument("--audio", default="",
                        help="Thay tiếng bằng file audio này (vd …_vi_audio.wav). "
                             "Bỏ trống = giữ tiếng gốc.")
    parser.add_argument("--out", default="",
                        help="Video kết quả (mặc định <video>_sub.mp4).")
    parser.add_argument("--max-chars", type=int, default=MAX_LINE_CHARS,
                        help=f"Số ký tự tối đa mỗi dòng hiển thị (mặc định {MAX_LINE_CHARS}).")
    parser.add_argument("--kieu", default=kieusub.MACDINH,
                        help="Kiểu phụ đề — tên file JSON trong kho kieusub_mau "
                             f"(mặc định {kieusub.MACDINH}).")
    parser.add_argument("--font", default="",
                        help="Đè font chữ của kiểu (tên family — xem "
                             "kieusub.danh_sach_font). Bỏ trống = font của kiểu.")
    parser.add_argument("--mau", default="",
                        help="Đè MÀU CHỮ của kiểu (RGB hex, vd FFD700; rỗng = "
                             "màu gốc của kiểu — viền/nền giữ nguyên).")
    parser.add_argument("--mau-vien", default="",
                        help="Đè MÀU VIỀN quanh chữ (RGB hex, vd 00E5FF; rỗng = "
                             "viền gốc). Kiểu không có viền thì không thấy gì.")
    parser.add_argument("--cochu", default="",
                        help="Phóng to/thu nhỏ chữ của kiểu, tính bằng %% "
                             "(50-200; rỗng hoặc 100 = giữ cỡ gốc của kiểu).")
    parser.add_argument("--vitri", default="",
                        help="Đáy dòng chữ cách đáy khung bao nhiêu %% chiều cao "
                             "(0-100; rỗng = tự đặt — ngồi trên dải che nếu có, "
                             "không thì lề mặc định của kiểu).")
    parser.add_argument("--che-sub-goc", action="store_true",
                        help="Tự dò dải sub gốc đốt sẵn (10 khung hình) rồi LÀM MỜ "
                             "dải đó suốt video, sub Việt đè lên trên dải mờ.")
    parser.add_argument("--vung", default="",
                        help="Ghi đè vùng che bằng tay: 'y0:y1' theo pixel video "
                             "(vd 920:1010) — dùng khi tự dò bị lệch.")
    parser.add_argument("--cpu", action="store_true",
                        help="Ép encode CPU — dùng khi GPU đang bận việc khác.")
    args = parser.parse_args()

    video = Path(args.video)
    ve_sub = bool(args.srt)              # bỏ --srt = không vẽ chữ nào
    if not video.is_file():
        print(f"❌ Không thấy video: {video}")
        sys.exit(1)
    cues = cue_times = kieu = None
    if ve_sub:
        srt = Path(args.srt)
        if not srt.is_file():
            print(f"❌ Không thấy SRT: {srt}")
            sys.exit(1)
        cues_raw = parse_srt_multiline(srt)
        if not cues_raw:
            print("❌ SRT không có câu nào.")
            sys.exit(1)
        # Font / màu chữ / màu viền / cỡ chữ do người dùng đè lên kiểu (rỗng =
        # giữ của kiểu). Thứ tự bọc y hệt myvoice: font → màu chữ → màu viền →
        # cỡ chữ; ap_cochu phải đứng CUỐI vì nó còn rút trần ký tự/dòng theo
        # tỉ lệ ngược (chữ to hơn thì ít ký tự lọt một dòng hơn).
        kieu = kieusub.ap_cochu(
            kieusub.ap_mau_vien(
                kieusub.ap_mau(kieusub.ap_font(kieusub.lay(args.kieu), args.font),
                               args.mau), args.mau_vien), args.cochu)
        for nhan, gt in (("🔤 Font", args.font), ("🎨 Màu chữ", args.mau),
                         ("🖍 Màu viền", args.mau_vien), ("🔍 Cỡ chữ", args.cochu)):
            if gt:
                print(f"{nhan}: {gt}")
        # Kiểu font to (Hormozi, Arial Black…) mang trần ký tự/dòng RIÊNG nhỏ hơn
        # để chữ không tràn mép — lấy trần chặt hơn giữa kiểu và --max-chars.
        max_chars = kieusub.chon_max_chars(kieu, args.max_chars)
        cues = [wrap_cue(t, max_chars) for _s, _e, t in cues_raw]
        cue_times = [(s, e) for s, e, _t in cues_raw]
        print(f"✂️  {len(cues)} dòng phụ đề từ: {srt.name}")
    else:
        print("✍️  Không vẽ sub — giữ hình sạch chữ.")

    # Vùng che sub Trung: --vung tay > tự dò 10 khung > không che.
    vung = None
    if args.vung:
        try:
            y0, y1 = (int(x) for x in args.vung.split(":"))
            _w, _h, _d = timvungsub._probe(video)
            vung = {"y0": y0, "y1": y1, "w": _w, "h": _h}
            print(f"🫥 Che vùng chỉ định tay: y {y0}–{y1}")
        except Exception as e:
            print(f"❌ --vung phải dạng y0:y1 (vd 920:1010): {e}")
            sys.exit(1)
    elif args.che_sub_goc:
        try:
            vung = timvungsub.tim_vung(video)
        except Exception as e:
            print(f"⚠️ Lỗi dò vùng sub ({e}) — burn không che.")
        if vung is None:
            print("🫥 Không thấy dải sub gốc nào — burn bình thường, không che.")

    out_path = Path(args.out) if args.out else video.with_name(video.stem + "_sub.mp4")
    ass_path = None
    if ve_sub:
        # Có dải che thì hạ sub Việt xuống NGỒI TRÊN dải mờ (đáy chữ chạm gần đáy
        # dải); không thì dùng lề mặc định của kho kiểu.
        margin_v = kieusub.SUB_MARGIN_V
        if vung:
            margin_v = max(10, round(kieusub.ASS_PLAY_H * (vung["h"] - vung["y1"])
                                     / vung["h"]) + 6)
        # --vitri (% chiều cao từ đáy) ĐÈ cả hai mức trên: người dùng đã kéo
        # thanh vị trí trên web thì chữ nằm đúng chỗ đã ngắm, kể cả khi có dải che.
        if args.vitri:
            margin_v = kieusub.vitri_margin(args.vitri, kieusub.ASS_PLAY_H, margin_v)
            print(f"↕ Vị trí chữ: cách đáy {args.vitri}% chiều cao ({margin_v}px)")
        ass_path = out_path.with_suffix(".ass")
        kieusub.write_ass_kieu(cues, cue_times, ass_path, kieu, margin_v=margin_v)
        print(f"💾 Kiểu phụ đề: {kieu['ten']} ({kieu['id']}) → {ass_path.name}")

    audio = args.audio or None
    if audio:
        if not Path(audio).is_file():
            print(f"❌ Không thấy audio: {audio}")
            sys.exit(1)
        print(f"🔊 Thay tiếng bằng: {Path(audio).name}")

    # Bỏ hết cả ba thì file ra y hệt file vào — chặn sớm cho đỡ tốn công.
    if not ve_sub and not vung and not audio:
        print("❌ Không vẽ sub, không che mờ, không thay tiếng — chẳng có gì để làm.")
        sys.exit(1)

    if not burn(video, out_path, ass_path=ass_path, audio=audio,
                force_cpu=args.cpu, vung=vung):
        print("❌ ffmpeg lỗi khi vẽ phụ đề.")
        sys.exit(1)
    size = out_path.stat().st_size / 1024 / 1024
    print(f"\n✅ Xong: {out_path}  ({size:.1f} MB)")


if __name__ == "__main__":
    main()
