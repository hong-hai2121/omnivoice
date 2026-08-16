# -*- coding: utf-8 -*-
"""
video_gansub_cung.py — VẼ CỨNG (burn/hardsub) phụ đề SRT vào video đã làm chậm,
tuỳ chọn THAY luôn tiếng bằng audio TTS đã sắp xếp.

KIỂU phụ đề chọn bằng --kieu <tên> — kho kiểu nằm ở myvideo/kieusub_mau/*.json
(xem myvideo/kieusub.py): hộp bo góc cổ điển, viền đậm, karaoke nhuộm màu,
Hormozi hiện từng chữ, bật từng từ… Mặc định "hopbo" — y hệt sub myvoice cũ.

Cách dùng:
    # gắn sub Việt vào video chậm (tiếng giữ nguyên tiếng Trung gốc)
    python video_gansub_cung.py "output/…_x0.7.mp4" --srt "output/…_x0.7_vi.srt"

    # bản TTS hoàn chỉnh: sub ĐÃ SẮP XẾP + thay tiếng bằng giọng Việt
    python video_gansub_cung.py "output/…_x0.7.mp4" \
        --srt "output/…_x0.7_vi_sapxep.srt" --audio "output/…_x0.7_vi_audio.wav"

    --kieu …    kiểu phụ đề (tên file trong kieusub_mau, mặc định hopbo).
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


def burn(video, ass_path, out_path, audio=None, force_cpu=False, vung=None):
    """Vẽ cứng .ass vào hình; audio=None giữ tiếng gốc, có audio thì THAY tiếng.

    `vung` (dict y0/y1 của timvungsub) → LÀM MỜ dải đó suốt video để che sub
    Trung đốt sẵn, rồi mới vẽ sub Việt đè lên trên dải mờ.

    Mô phỏng burn_subs của video_gansub (NVENC ưu tiên, lỗi tự lùi CPU) nhưng
    thêm được nhánh thay audio nên viết lại cmd ở đây.
    """
    # fontsdir: kho font riêng myvideo/fonts (Anton, Bangers…) — không cần cài font.
    sub_vf = f"subtitles={ass_path.name}{kieusub.fontsdir_arg(ass_path.parent)}"
    if vung:
        y0, day = int(vung["y0"]), int(vung["y1"]) - int(vung["y0"])
        sigma = max(10, min(30, day // 4))       # blur đủ tan chữ, theo độ dày dải
        vf = (f"split[goc][mo];"
              f"[mo]crop=iw:{day}:0:{y0},gblur=sigma={sigma}[dai];"
              f"[goc][dai]overlay=0:{y0},{sub_vf}")
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
        cmd += ["-vf", vf, *codec, "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", "-stats", "-loglevel", "warning",
                str(Path(out_path).resolve())]
        return cmd

    use_gpu = (not force_cpu) and has_nvenc()
    print("🎬 Encode:", "GPU (h264_nvenc)" if use_gpu else "CPU (libx264)")
    r = subprocess.run(build_cmd(use_gpu), cwd=str(ass_path.parent))
    if r.returncode != 0 and use_gpu:
        print("   GPU lỗi, chuyển sang CPU (libx264)…")
        r = subprocess.run(build_cmd(False), cwd=str(ass_path.parent))
    return r.returncode == 0


def main():
    parser = argparse.ArgumentParser(
        description="Vẽ cứng phụ đề (kiểu khung bo góc của myvoice) vào video.")
    parser.add_argument("video", help="Video nền (thường là …_x0.7.mp4).")
    parser.add_argument("--srt", required=True, help="File SRT cần vẽ cứng.")
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
    parser.add_argument("--che-sub-goc", action="store_true",
                        help="Tự dò dải sub Trung đốt sẵn (10 khung hình) rồi LÀM MỜ "
                             "dải đó suốt video, sub Việt đè lên trên dải mờ.")
    parser.add_argument("--vung", default="",
                        help="Ghi đè vùng che bằng tay: 'y0:y1' theo pixel video "
                             "(vd 920:1010) — dùng khi tự dò bị lệch.")
    parser.add_argument("--cpu", action="store_true",
                        help="Ép encode CPU — dùng khi GPU đang bận việc khác.")
    args = parser.parse_args()

    video = Path(args.video)
    srt = Path(args.srt)
    if not video.is_file():
        print(f"❌ Không thấy video: {video}")
        sys.exit(1)
    if not srt.is_file():
        print(f"❌ Không thấy SRT: {srt}")
        sys.exit(1)

    cues_raw = parse_srt_multiline(srt)
    if not cues_raw:
        print("❌ SRT không có câu nào.")
        sys.exit(1)
    # Kiểu font to (Hormozi, Arial Black…) mang trần ký tự/dòng RIÊNG nhỏ hơn
    # để chữ không tràn mép — lấy trần chặt hơn giữa kiểu và --max-chars.
    kieu = kieusub.lay(args.kieu)
    if args.font:
        kieu = kieusub.ap_font(kieu, args.font)
        print(f"🔤 Font: {args.font}")
    max_chars = min(args.max_chars, kieu["max_chars"] or args.max_chars)
    cues = [wrap_cue(t, max_chars) for _s, _e, t in cues_raw]
    cue_times = [(s, e) for s, e, _t in cues_raw]
    print(f"✂️  {len(cues)} dòng phụ đề từ: {srt.name}")

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
            print("🫥 Không thấy dải sub Trung nào — burn bình thường, không che.")

    # Có dải che thì hạ sub Việt xuống NGỒI TRÊN dải mờ (đáy chữ chạm gần đáy
    # dải); không thì dùng lề mặc định của kho kiểu.
    margin_v = kieusub.SUB_MARGIN_V
    if vung:
        margin_v = max(10, round(kieusub.ASS_PLAY_H * (vung["h"] - vung["y1"])
                                 / vung["h"]) + 6)

    out_path = Path(args.out) if args.out else video.with_name(video.stem + "_sub.mp4")
    ass_path = out_path.with_suffix(".ass")
    kieusub.write_ass_kieu(cues, cue_times, ass_path, kieu, margin_v=margin_v)
    print(f"💾 Kiểu phụ đề: {kieu['ten']} ({kieu['id']}) → {ass_path.name}")

    audio = args.audio or None
    if audio:
        if not Path(audio).is_file():
            print(f"❌ Không thấy audio: {audio}")
            sys.exit(1)
        print(f"🔊 Thay tiếng bằng: {Path(audio).name}")

    if not burn(video, ass_path, out_path, audio=audio, force_cpu=args.cpu,
                vung=vung):
        print("❌ ffmpeg lỗi khi vẽ phụ đề.")
        sys.exit(1)
    size = out_path.stat().st_size / 1024 / 1024
    print(f"\n✅ Xong: {out_path}  ({size:.1f} MB)")


if __name__ == "__main__":
    main()
