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


def chia_cue(start, end, text, max_chars=MAX_LINE_CHARS, dong=2):
    """Một cue SRT → các LẦN HIỆN ≤ `dong` dòng; mốc giờ chia theo số ký tự.

    Nếp cũ (wrap_cue) bẻ dòng xong hiện TẤT CẢ một lượt — câu dịch dài (nhất là
    khi bước ② gộp câu) ra 3-4 dòng chữ chiếm nửa màn hình. Giờ theo đúng nếp
    build_cues bên myvoice: cắt câu thành mẩu vừa MỘT lần hiện (≤ max_chars ×
    dong ký tự, cắt ở ranh giới từ) rồi bẻ mẩu thành các dòng dài xấp xỉ nhau.
    Khác myvoice ở chỗ cue ở đây MANG SẴN mốc giờ: chia khoảng giờ của cue cho
    các mẩu theo tỉ lệ ký tự — tổng thời lượng không đổi, không đè sang cue sau.
    """
    dong = max(1, int(dong or 1))
    units = []                       # mỗi phần tử = các dòng của MỘT lần hiện
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        for mau in wrap_sentence(line, max_chars * dong):
            units.append(wrap_sentence(mau, max_chars))
    if not units:
        return []
    # Cue gốc có sẵn nhiều dòng (bản song ngữ 2 dòng/câu): các dòng ngắn đứng
    # cạnh nhau vẫn nên hiện CÙNG LÚC — gộp mẩu liền kề tới khi đủ `dong` dòng.
    gop = [units[0]]
    for u in units[1:]:
        if len(gop[-1]) + len(u) <= dong:
            gop[-1] = gop[-1] + u
        else:
            gop.append(u)
    trong = [sum(len(l) for l in u) for u in gop]
    tong = sum(trong) or 1
    out, t = [], start
    for u, w in zip(gop, trong):
        t2 = t + (end - start) * w / tong
        out.append((t, t2, "\n".join(u)))
        t = t2
    out[-1] = (out[-1][0], end, out[-1][2])     # chống sai số cộng dồn
    return out


def burn(video, out_path, ass_path=None, audio=None, force_cpu=False, vung=None,
         zoom=0, doc=False, nhac=None, nhac_db=-18.0, logo=None):
    """Dựng video kết quả. Các phần đều tuỳ chọn, bỏ hết cũng chạy:

    `ass_path` → vẽ cứng phụ đề (None = không vẽ chữ nào).
    `vung` (dict y0/y1 của timvungsub) → LÀM MỜ dải đó suốt video để che sub
    gốc đốt sẵn, rồi mới vẽ sub Việt đè lên trên dải mờ (None = không che).
    `audio` → THAY tiếng bằng file này (None = giữ tiếng gốc).
    `zoom` → PHÓNG TO video nền bấy nhiêu % (20 = to gấp 1.2 lần) rồi cắt giữa
    về đúng khung cũ — mép hình mất đều bốn phía, độ phân giải không đổi.
    `doc` → dựng KHUNG DỌC 9:16 (1080×1920): video nằm giữa, hai dải trên dưới
    là chính nó phóng to + làm mờ (nếp TikTok/Shorts quen mắt) — chữ vẽ SAU
    nên .ass phải soạn theo khung 1080×1920.
    `nhac` → trộn NHẠC NỀN này dưới tiếng chính, âm lượng `nhac_db` dB (âm là
    nhỏ hơn tiếng chính; nhạc ngắn tự lặp lại cho phủ hết video).
    `logo` → đóng ảnh PNG này (logo kênh) ở góc phải trên suốt video, rộng
    ~12%% khung; nền trong suốt của PNG giữ nguyên.

    Không vẽ sub, không che mờ, không zoom, không dọc, không logo = hình không
    đổi pixel nào → -c:v copy (ghép lại tiếng thôi): nhanh, không mất chất lượng.

    Thứ tự filter CÓ CHỦ Ý: che mờ trước (toạ độ dải do timvungsub dò trên
    hình GỐC) → zoom → đổi khung dọc → vẽ chữ → đóng logo (chữ + logo vẽ SAU
    nên không bị phóng/cắt theo, nằm đúng vị trí đã ngắm ở ảnh xem thử).

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
    parts = []
    if vung:
        y0, day = int(vung["y0"]), int(vung["y1"]) - int(vung["y0"])
        sigma = max(10, min(30, day // 4))       # blur đủ tan chữ, theo độ dày dải
        parts.append(f"split[goc][mo];"
                     f"[mo]crop=iw:{day}:0:{y0},gblur=sigma={sigma}[dai];"
                     f"[goc][dai]overlay=0:{y0}")
    if zoom:
        # Phóng z lần rồi cắt GIỮA về khung cũ. trunc(…/2)*2: mọi cạnh chẵn —
        # yuv420p/libx264 từ chối cạnh lẻ; khung 16:9 chuẩn ra lại đúng số cũ
        # (1920×1.2=2304 → /1.2=1920), khung dị lắm mới hụt 2px.
        z = 1 + max(0, int(zoom)) / 100
        parts.append(f"scale=trunc(iw*{z:g}/2)*2:trunc(ih*{z:g}/2)*2:flags=lanczos,"
                     f"crop=trunc(iw/{z:g}/2)*2:trunc(ih/{z:g}/2)*2")
    if doc:
        # Khung DỌC 1080×1920: nền = chính video phóng phủ kín + gblur, video
        # thật scale ngang 1080 đặt GIỮA. Không cắt mất nội dung nào của hình.
        parts.append(
            "split[nen][chinh];"
            "[nen]scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,gblur=sigma=28[bg];"
            "[chinh]scale=1080:-2:flags=lanczos[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2")
    if sub_vf:
        parts.append(sub_vf)
    vf = ",".join(parts)

    # Logo cần cỡ khung THÀNH PHẨM để tính bề rộng: dọc = 1080 cố định, còn
    # lại là bề rộng gốc (zoom cắt về đúng khung cũ nên không đổi số đo).
    logo_w = pad = 0
    if logo:
        vw = 1080 if doc else timvungsub._probe(video)[0]
        logo_w = max(48, round(vw * 0.12 / 2) * 2)
        pad = max(12, vw // 100)

    LOUD = "loudnorm=I=-14:TP=-1.5:LRA=11"

    def build_cmd(gpu):
        codec = (["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "19"]
                 if gpu else ["-c:v", "libx264", "-preset", "medium", "-crf", "18"])
        cmd = ["ffmpeg", "-y", "-i", str(Path(video).resolve())]
        ai_tts = ai_nhac = vi_logo = None
        n = 1
        if audio:
            cmd += ["-i", str(Path(audio).resolve())]
            ai_tts, n = n, n + 1
        if nhac:
            # -stream_loop -1: nhạc ngắn tự lặp cho phủ hết video; amix
            # duration=first chốt độ dài theo tiếng chính nên không kéo lê.
            cmd += ["-stream_loop", "-1", "-i", str(Path(nhac).resolve())]
            ai_nhac, n = n, n + 1
        if logo:
            # Ảnh tĩnh chỉ có 1 khung hình — overlay mặc định (eof_action=repeat)
            # giữ khung đó suốt video nên không cần -loop.
            cmd += ["-i", str(Path(logo).resolve())]
            vi_logo, n = n, n + 1

        fc, maps, out_a, out_v = [], [], [], []
        # ── Tiếng: TTS (loudnorm -14 LUFS chuẩn YouTube) ± nhạc nền ──────────
        if ai_nhac is not None:
            # amix normalize=0: KHÔNG tự hạ tiếng chính xuống — nhạc đã tự nhỏ
            # bằng volume dB; duration=first ăn theo độ dài tiếng chính.
            chinh = (f"[{ai_tts}:a]{LOUD},aresample=48000[chinh]"
                     if ai_tts is not None else "[0:a]anull[chinh]")
            fc += [chinh, f"[{ai_nhac}:a]volume={float(nhac_db):g}dB[bg]",
                   "[chinh][bg]amix=inputs=2:duration=first:normalize=0[aout]"]
            maps += ["-map", "[aout]"]
            out_a = ["-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
        elif ai_tts is not None:
            # -map (i):a: chỉ lấy audio TTS — tiếng gốc của video TẮT hẳn.
            maps += ["-map", f"{ai_tts}:a"]
            out_a = ["-af", LOUD, "-ar", "48000", "-c:a", "aac", "-b:a", "192k"]
        else:
            out_a = ["-c:a", "copy"]
        # ── Hình: chuỗi vf (che mờ → zoom → dọc → chữ) ± logo đè cuối ────────
        if vi_logo is not None:
            fc += [f"[0:v]{vf or 'null'}[vv]",
                   f"[{vi_logo}:v]scale={logo_w}:-1[lg]",
                   f"[vv][lg]overlay=W-w-{pad}:{pad}[vout]"]
            maps = ["-map", "[vout]"] + maps
            out_v = [*codec, "-pix_fmt", "yuv420p"]
        elif vf:
            if fc:
                # Đã có filter_complex (nhạc nền): dồn luôn chuỗi hình vào đó —
                # trộn -vf với -filter_complex trong một lệnh là ffmpeg từ chối.
                fc.append(f"[0:v]{vf}[vout]")
                maps = ["-map", "[vout]"] + maps
                out_v = [*codec, "-pix_fmt", "yuv420p"]
            else:
                maps = (["-map", "0:v"] + maps) if maps else []
                out_v = ["-vf", vf, *codec, "-pix_fmt", "yuv420p"]
        else:
            maps = (["-map", "0:v"] + maps) if maps else []
            out_v = ["-c:v", "copy"]
        if fc:
            cmd += ["-filter_complex", ";".join(fc)]
        cmd += maps + out_v + out_a
        if ai_tts is not None:
            cmd += ["-shortest"]
        cmd += ["-movflags", "+faststart", "-stats", "-loglevel", "warning",
                str(Path(out_path).resolve())]
        return cmd

    # cwd = thư mục chứa .ass để filter subtitles= chỉ cần TÊN file (đường dẫn
    # Windows có dấu hai chấm, nhét vào filtergraph là hỏng cú pháp).
    cwd = str((ass_path or Path(out_path)).parent)
    if not vf and not logo:
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


def ghep_outro(main_mp4, outro_mp4):
    """Nối OUTRO (kêu gọi đăng ký…) vào cuối video thành phẩm, TẠI CHỖ.

    Cách nối giữ chất lượng: KHÔNG encode lại video chính (đã tốn cả buổi dựng
    và encode thêm lượt nữa là mất chất) — chỉ encode outro (ngắn) sang đúng
    cỡ khung / fps / mẫu tiếng của video chính rồi nối bằng concat demuxer
    -c copy. Outro lệch chuẩn cỡ nào cũng tự scale + pad về khớp.

    Lỗi ở bất kỳ khâu nào chỉ cảnh báo và GIỮ NGUYÊN video chính — thiếu outro
    còn hơn hỏng video. Trả về True nếu đã nối được.
    """
    main_mp4, outro_mp4 = Path(main_mp4), Path(outro_mp4)

    def _probe_json(p):
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(p)],
            capture_output=True, text=True, timeout=60)
        import json as _json
        return _json.loads(r.stdout).get("streams", [])

    try:
        vs = next(s for s in _probe_json(main_mp4) if s["codec_type"] == "video")
        au = next((s for s in _probe_json(main_mp4) if s["codec_type"] == "audio"), None)
        w, h = int(vs["width"]), int(vs["height"])
        fps = vs.get("r_frame_rate") or "30"
        sr = int(au["sample_rate"]) if au else 48000
        ch = int(au.get("channels", 2)) if au else 2
        outro_co_tieng = any(s["codec_type"] == "audio" for s in _probe_json(outro_mp4))
    except Exception as e:
        print(f"⚠️ Không đọc được thông số video để ghép outro ({e}) — bỏ qua outro.")
        return False

    folder = main_mp4.parent
    tmp_outro = folder / f"~outro_{os.getpid()}.mp4"
    tmp_main = folder / f"~main_{os.getpid()}.mp4"
    tmp_out = folder / f"~cat_{os.getpid()}.mp4"
    tmp_list = folder / f"~list_{os.getpid()}.txt"
    try:
        # 1) Encode outro về ĐÚNG chuẩn của video chính (concat copy đòi khớp
        #    codec/cỡ/fps/tiếng từng ly). Outro không có tiếng thì độn im lặng.
        cmd = ["ffmpeg", "-y", "-i", str(outro_mp4)]
        if not outro_co_tieng:
            cmd += ["-f", "lavfi", "-i", f"anullsrc=r={sr}:cl={'stereo' if ch >= 2 else 'mono'}"]
        cmd += ["-filter_complex",
                f"[0:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,fps={fps},format=yuv420p[v]",
                "-map", "[v]", "-map", f"{0 if outro_co_tieng else 1}:a",
                "-c:v", "libx264", "-crf", "18", "-preset", "medium",
                "-c:a", "aac", "-b:a", "192k", "-ar", str(sr), "-ac", str(ch),
                "-shortest", "-loglevel", "error", str(tmp_outro)]
        if subprocess.run(cmd).returncode != 0:
            print("⚠️ Encode outro lỗi — bỏ qua outro.")
            return False
        # 2) Hardlink video chính sang tên tạm KHÔNG dấu — danh sách concat có
        #    tên dính ' là hỏng (cùng họ lỗi filter subtitles); link cứng không
        #    tốn thêm dung lượng. Link không được (khác ổ/quyền) mới phải copy.
        try:
            os.link(main_mp4, tmp_main)
        except OSError:
            import shutil
            shutil.copyfile(main_mp4, tmp_main)
        tmp_list.write_text(f"file '{tmp_main.name}'\nfile '{tmp_outro.name}'\n",
                            encoding="utf-8")
        # 3) Nối -c copy (không encode lại video chính) rồi thay tại chỗ.
        r = subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                            "-i", str(tmp_list), "-c", "copy",
                            "-movflags", "+faststart", "-loglevel", "error",
                            str(tmp_out)], cwd=str(folder))
        if r.returncode != 0 or not tmp_out.is_file():
            print("⚠️ Nối outro lỗi — giữ nguyên video chính.")
            return False
        os.replace(tmp_out, main_mp4)
        print(f"🏷 Đã nối outro: {outro_mp4.name}")
        return True
    finally:
        for p in (tmp_outro, tmp_main, tmp_out, tmp_list):
            try:
                p.unlink()
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
    parser.add_argument("--dong", type=int, default=2, choices=[1, 2],
                        help="Số DÒNG tối đa mỗi lần hiện chữ (mặc định 2 — như "
                             "ảnh mẫu của kho kiểu). Câu dài hơn thì tách thành "
                             "nhiều lần hiện nối nhau, giờ chia theo số ký tự.")
    parser.add_argument("--zoom", type=int, default=0,
                        help="PHÓNG TO video nền bấy nhiêu %% (vd 20 = to gấp "
                             "1.2 lần) rồi cắt giữa về đúng khung cũ — mép hình "
                             "mất đều bốn phía, độ phân giải giữ nguyên. "
                             "0 = không phóng. Chữ vẽ SAU zoom nên không bị phóng; "
                             "dải che mờ dò trên hình gốc nên vẫn che đúng chỗ.")
    parser.add_argument("--khung", default="ngang", choices=["ngang", "doc"],
                        help="doc = dựng bản DỌC 9:16 (1080×1920, video giữa + "
                             "nền chính nó làm mờ trên dưới — kiểu TikTok/Shorts); "
                             "ra <video>_doc.mp4, chữ tự soạn theo khung dọc. "
                             "Mặc định ngang (giữ khung gốc).")
    parser.add_argument("--nhac", default="",
                        help="Trộn NHẠC NỀN này (mp3/wav…) nhỏ dưới tiếng chính, "
                             "tự lặp cho phủ hết video. Bỏ trống = không nhạc.")
    parser.add_argument("--nhac-db", type=float, default=-18.0,
                        help="Âm lượng nhạc nền, dB so với 0 (mặc định -18 — "
                             "nghe rõ tiếng đọc, nhạc chỉ lót nền; -25 là rất nhỏ).")
    parser.add_argument("--logo", default="",
                        help="Đóng ảnh PNG này (logo kênh) góc phải trên suốt "
                             "video, rộng ~12%% khung. Bỏ trống = không logo.")
    parser.add_argument("--outro", default="",
                        help="Nối video này vào CUỐI video thành phẩm (outro kêu "
                             "gọi đăng ký) — outro được encode khớp chuẩn rồi nối "
                             "-c copy, KHÔNG encode lại video chính.")
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
    doc = args.khung == "doc"
    if doc:
        print("📱 Khung DỌC 9:16 (1080×1920) — video giữa, nền chính nó làm mờ.")
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
        # Khung dọc hẹp bằng 1080/1920 khung ngang → trần rút thêm (doc=True).
        max_chars = kieusub.chon_max_chars(kieu, args.max_chars, doc=doc)
        hien = [c for s0, e0, t in cues_raw
                for c in chia_cue(s0, e0, t, max_chars, args.dong)]
        cues = [t for _s, _e, t in hien]
        cue_times = [(s0, e0) for s0, e0, _t in hien]
        print(f"✂️  {len(cues)} lần hiện chữ (≤{args.dong} dòng/lần) "
              f"từ {len(cues_raw)} câu của: {srt.name}")
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

    out_path = Path(args.out) if args.out else video.with_name(
        video.stem + ("_doc.mp4" if doc else "_sub.mp4"))
    ass_path = None
    if ve_sub:
        # Khung dọc: .ass soạn theo 1080×1920 (chữ vẽ SAU khi đổi khung). Lề
        # đáy mặc định ~22% để chữ ngồi trên dải mờ DƯỚI video giữa khung —
        # đúng chỗ TikTok/Shorts hay đặt; dải che sub gốc không dùng làm mốc
        # (toạ độ của nó là trên hình gốc, sau khi ghép dọc đã trôi chỗ khác).
        pw, ph = (1080, 1920) if doc else (kieusub.ASS_PLAY_W, kieusub.ASS_PLAY_H)
        margin_v = round(ph * 0.22) if doc else kieusub.SUB_MARGIN_V
        # Có dải che thì hạ sub Việt xuống NGỒI TRÊN dải mờ (đáy chữ chạm gần đáy
        # dải); không thì dùng lề mặc định của kho kiểu.
        if vung and not doc:
            margin_v = max(10, round(ph * (vung["h"] - vung["y1"])
                                     / vung["h"]) + 6)
        # --vitri (% chiều cao từ đáy) ĐÈ cả hai mức trên: người dùng đã kéo
        # thanh vị trí trên web thì chữ nằm đúng chỗ đã ngắm, kể cả khi có dải che.
        if args.vitri:
            margin_v = kieusub.vitri_margin(args.vitri, ph, margin_v)
            print(f"↕ Vị trí chữ: cách đáy {args.vitri}% chiều cao ({margin_v}px)")
        ass_path = out_path.with_suffix(".ass")
        kieusub.write_ass_kieu(cues, cue_times, ass_path, kieu,
                               play_w=pw, play_h=ph, margin_v=margin_v)
        print(f"💾 Kiểu phụ đề: {kieu['ten']} ({kieu['id']}) → {ass_path.name}")

    audio = args.audio or None
    if audio:
        if not Path(audio).is_file():
            print(f"❌ Không thấy audio: {audio}")
            sys.exit(1)
        print(f"🔊 Thay tiếng bằng: {Path(audio).name}")

    zoom = max(0, min(100, args.zoom or 0))
    if zoom:
        print(f"🔎 Phóng to video nền: +{zoom}% (cắt giữa, khung giữ nguyên)")

    # Nhạc nền / logo / outro: file chỉ định mà không có thật thì BÁO rồi bỏ
    # qua phần đó — đừng vì thiếu cái phụ mà hỏng cả video chính.
    nhac = args.nhac or None
    if nhac and not Path(nhac).is_file():
        print(f"⚠️ Không thấy nhạc nền: {nhac} — dựng không nhạc.")
        nhac = None
    if nhac:
        print(f"🎵 Nhạc nền: {Path(nhac).name} ({args.nhac_db:g}dB, tự lặp)")
    logo = args.logo or None
    if logo and not Path(logo).is_file():
        print(f"⚠️ Không thấy logo: {logo} — dựng không logo.")
        logo = None
    if logo:
        print(f"🏷 Logo kênh: {Path(logo).name} (góc phải trên)")
    outro = args.outro or None
    if outro and not Path(outro).is_file():
        print(f"⚠️ Không thấy outro: {outro} — dựng không outro.")
        outro = None

    # Bỏ hết thì file ra y hệt file vào — chặn sớm cho đỡ tốn công.
    if not any((ve_sub, vung, audio, zoom, doc, nhac, logo, outro)):
        print("❌ Không vẽ sub, không che mờ, không thay tiếng, không zoom, "
              "không khung dọc, không nhạc/logo/outro — chẳng có gì để làm.")
        sys.exit(1)

    if not burn(video, out_path, ass_path=ass_path, audio=audio,
                force_cpu=args.cpu, vung=vung, zoom=zoom, doc=doc,
                nhac=nhac, nhac_db=args.nhac_db, logo=logo):
        print("❌ ffmpeg lỗi khi vẽ phụ đề.")
        sys.exit(1)
    if outro:
        ghep_outro(out_path, outro)
    size = out_path.stat().st_size / 1024 / 1024
    print(f"\n✅ Xong: {out_path}  ({size:.1f} MB)")


if __name__ == "__main__":
    main()
