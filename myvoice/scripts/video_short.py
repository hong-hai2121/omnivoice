# -*- coding: utf-8 -*-
"""
Dựng video YOUTUBE SHORT (≤ 2 phút 50) cho tập đã có video TikTok.

DÒNG CHỮ DƯỚI = 'Tập Số N' (20/11/2026). Bản dọc/TikTok ghi "Nghe trọn tập tại kênh
Mimi audio" ở dưới dải video; chữ đó đã nung vào hình nên cắt thẳng từ tiktok.mp4 thì
không đổi được. Vì vậy với tập dựng bằng bố cục khung dọc (video_doc_khung), Short
dựng lại phần HÌNH từ video gốc sạch chữ (YOUTUBE_goc.mp4) + lớp phủ riêng có dòng
'Tập Số N' — cùng logo, tiêu đề, ảnh bìa frame đầu như bản TikTok, chỉ khác dòng dưới.
Chỉ encode ≤ 2:50 nên mất chừng một phút. Xem build_short_so_tap.

Không đủ điều kiện dựng lại (tập không dùng khung dọc, mất video gốc, không rõ số
tập, ffmpeg lỗi) thì lùi về cách cũ: cắt bớt phần đuôi của tiktok.mp4, luồng HÌNH
giữ nguyên bằng `-c:v copy` — có Short với dòng chữ của bản TikTok còn hơn không có.

TRỪ NHẠC NỀN: luồng tiếng KHÔNG lấy của tiktok.mp4 mà là bản giọng trần (chưa trộn
nhạc), vốn đã có sẵn cùng nhịp với video. YouTube soi bản quyền nhạc chặt hơn TikTok,
mà nhạc nền chỉ là nền — bỏ đi không mất gì.

Không còn bản giọng trần (chạy lại lẻ, thư mục đã dọn rác) thì lấy tiếng của
facebook.mp4: video đó dựng thẳng từ audio giọng nên vốn đã sạch nhạc (khi phải cắt
thẳng thì cắt luôn hình của nó).

Điểm cắt lấy ở CUỐI CÂU: dò khoảng lặng (TTS luôn nghỉ giữa hai câu) gần mốc 2:50
nhất trong cửa sổ [2:20 – 2:50] — dùng đúng find_sentence_end_silence mà bước cắt
audio TikTok đang dùng, nên hai chỗ không thể lệch cách hiểu "hết câu". Không dò
được khoảng lặng nào thì cắt cứng ở 2:50, thà hụt nửa câu còn hơn không có short.

Vì sao 2:50 mà không phải 3:00: YouTube nhận Short khi video dọc và DƯỚI 3 phút —
sát mốc quá thì chỉ cần lệch vài frame là YouTube xếp thành video thường.

Cách dùng:
    python video_short.py <thư mục tập | file tiktok.mp4> [file short ra]
    (không ghi file ra → short.mp4 trong thư mục tập, ĐÈ bản đang có)
"""

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
AUDIO_BITRATE = "192k"       # AAC cho luồng tiếng thay vào (giọng nói, thừa sức)
# Giọng trần lệch quá ngần này so với video thì coi như không khớp — thà lùi về
# facebook.mp4 còn hơn ghép nhầm bản giọng khác nhịp rồi tiếng chạy lệch hình.
SYNC_TOLERANCE = 1.0


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
    log(f"[short] Bản giọng trần: {ung_vien[0].name}")
    return ung_vien[0]


def resolve_voice_audio(video: Path, voice_audio=None, log=print):
    """Bản giọng TRẦN dùng làm tiếng cho Short, hoặc None nếu không có bản nào khớp.

    Ưu tiên file caller đưa sang (bước dựng TikTok biết chính xác nó là file nào);
    không có thì tự dò trong thư mục. Dù đường nào cũng đối chiếu lại thời lượng với
    video — xem SYNC_TOLERANCE.
    """
    cand = Path(voice_audio) if voice_audio else None
    if cand is not None and not (cand.is_file() and cand.stat().st_size > 0):
        log(f"[short] Không thấy bản giọng được chỉ định: {cand.name}")
        cand = None
    if cand is None:
        cand = find_voice_audio(video, log=log)
    if cand is None:
        return None
    try:
        lech = abs(probe_audio_duration(cand) - probe_audio_duration(video))
    except ClipFinderError as e:
        log(f"[short] Không đo được {cand.name} ({e}) → bỏ qua bản giọng này.")
        return None
    if lech > SYNC_TOLERANCE:
        log(f"[short] {cand.name} lệch {lech:.1f}s so với video → không dùng (sợ tiếng lệch hình).")
        return None
    return cand


def find_no_music_video(video: Path):
    """Video dọc vốn đã KHÔNG có nhạc nền, để cắt Short khi thiếu bản giọng trần.

    facebook.mp4 dựng thẳng từ audio giọng, chưa qua bước trộn nhạc của TikTok. Đổi
    lại nó chưa có khung tiêu đề / chữ 'Mimi audio Số N' — chấp nhận mất khung còn
    hơn đẩy nhạc nền TikTok lên YouTube.
    """
    folder = video.parent
    for cand in [folder / "facebook.mp4", *sorted(folder.glob("*_doc.mp4"))]:
        if cand.is_file() and cand.stat().st_size > 0 and cand.name != video.name:
            return cand
    return None


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


def _vdk():
    """video_doc_khung (bố cục dọc: lớp phủ + dựng từ video gốc). Nạp trễ vì kéo theo PIL."""
    import video_doc_khung
    return video_doc_khung


def tap_dung_khung_doc(folder: Path) -> bool:
    """Bản dọc của tập có dựng bằng bố cục khung (video_doc_khung) không — nhận ra qua lớp
    phủ khungdoc_tap.png mà bước dựng dọc để lại trong thư mục tập."""
    try:
        return (Path(folder) / _vdk().LOP_TAP_NAME).is_file()
    except Exception:
        return False


def find_cover(folder: Path):
    """Thumbnail DỌC của tập (thumbnail<N>_dọc.png) để đè frame đầu Short, hoặc None."""
    cands = sorted(Path(folder).glob("thumbnail*_dọc.png"), key=lambda p: p.stat().st_mtime)
    return cands[-1] if cands else None


def build_short_so_tap(folder, tieng, cut: float, out, *, caption=None, che_chu=None,
                       cover_png=None, log=print, progress=None) -> bool:
    """Dựng Short có DÒNG DƯỚI 'Tập Số N' thay cho "Nghe trọn tập tại kênh Mimi audio".

    Hình lấy từ video gốc sạch chữ của tập (video_doc_khung.nguon_goc — cùng nguồn mà
    facebook.mp4 rồi tiktok.mp4 đã dùng, cũng chạy từ giây 0) + lớp phủ vẽ riêng cho
    Short: cùng logo, cùng tiêu đề, chỉ đổi dòng dưới. Tiếng = `cut` giây đầu của `tieng`
    (bản giọng trần, hoặc video vốn không nhạc).

    Trả True khi `out` đã dựng xong. False = không đủ điều kiện hoặc dựng lỗi (đã ghi
    lý do vào log) — bên gọi lùi về cắt thẳng từ video TikTok, dòng chữ giữ như cũ.
    """
    folder, out = Path(folder), Path(out)
    lop = out.with_name(out.stem + "_lop.png")
    try:
        vdk = _vdk()
        che = vdk.che_cua_tap(folder, che_chu)
        nguon, crop, _ = vdk.nguon_goc(folder, che=che)
        if nguon is None:
            log(f"[short] Không còn video gốc ({vdk.GOC_NAME} / YOUTUBE.mp4) trong "
                f"{folder.name} để dựng lại hình.")
            return False
        info = vdk.thong_tin_tap(folder, caption)
        cta = vdk.cta_short(info["episode"])
        if not cta:
            log(f"[short] Không đọc được SỐ TẬP từ tên thư mục “{folder.name}” hay tiêu đề "
                f"SEO → không ghi được dòng “{vdk.CTA_SHORT.format(so='N')}”.")
            return False
        mau = vdk.chon_mau(folder)
        # Dòng số tập ghi HAI chỗ: dưới dải video và phía trên tiêu đề (ngang hàng logo).
        vdk.ve_lop_tap(mau, info["episode"], info["title"], lop, log=log, che=che,
                       cta=cta, dong_tren=cta)
        log(f"[short] Dòng “{cta}” ở trên tiêu đề + dưới video (logo {mau}) — dựng lại "
            f"hình từ {nguon.name}.")
        vdk.build_video_doc_khung(tieng, nguon, out, lop, crop=crop, cover_png=cover_png,
                                  log=log, progress=progress, che=che, thoi_luong=cut)
        return True
    except Exception as e:
        log(f"[short] Dựng lại hình với dòng số tập lỗi: {e}")
        return False
    finally:
        try:
            lop.unlink(missing_ok=True)
        except OSError:
            pass


def build_short(tiktok_video, output=None, *, voice_audio=None,
                max_seconds: float = MAX_SECONDS,
                skip_existing: bool = False, log=print,
                khung=None, caption=None, che_chu=None, cover_png=None,
                progress=None) -> Path:
    """Dựng short ≤ max_seconds cho tập của tiktok_video, BỎ nhạc nền. Trả về đường dẫn short.

    voice_audio: audio GIỌNG cùng nhịp với video (chưa trộn nhạc nền). Vừa dùng để
        dò điểm cắt cuối câu, vừa là luồng tiếng ghép vào Short. None → tự tìm trong
        thư mục, xem find_voice_audio.
    khung: True → dựng lại hình với dòng dưới 'Tập Số N' (build_short_so_tap); False →
        chỉ cắt từ video TikTok (dòng chữ y như TikTok); None → tự nhận theo thư mục
        tập (tap_dung_khung_doc). Dựng lại không được thì tự lùi về cắt.
    caption: chữ TikTok 'Mimi audio Số N' — nguồn số tập dự phòng khi tên thư mục
        không có số. che_chu: ô ✂ che chữ Trung (None → theo YOUTUBE_goc.json).
    cover_png: thumbnail dọc đè frame đầu (None → tự tìm trong thư mục, xem find_cover).
    progress: hàm (pct, cur, total, speed) cho thanh tiến trình khi dựng lại hình.

    Không có bản giọng trần nào khớp thì lấy tiếng (và, khi phải cắt thẳng, cả hình)
    từ facebook.mp4 — vốn không nhạc, xem find_no_music_video.

    Ném RuntimeError nếu không còn nguồn nào sạch nhạc, hoặc ffmpeg cắt lỗi.
    Video ngắn sẵn vẫn ghi ra file riêng vì bản TikTok sẽ bị đổi tên sau khi đăng.
    """
    src = Path(tiktok_video)
    out = Path(output) if output else src.with_name(SHORT_NAME)
    folder = src.parent

    if skip_existing and out.exists() and out.stat().st_size > 0:
        log(f"♻ Video Short đã có → bỏ qua cắt lại: {out.name}")
        return out
    if not src.is_file() or src.stat().st_size == 0:
        raise RuntimeError(f"Không có video TikTok để cắt Short: {src}")

    # voice = luồng tiếng sẽ ghép vào. None nghĩa là audio sẵn trong src đã sạch nhạc.
    voice = resolve_voice_audio(src, voice_audio, log=log)
    if voice is None:
        thay_the = find_no_music_video(src)
        if thay_the is None:
            raise RuntimeError(
                f"Không còn bản giọng trần lẫn {src.parent.name}/facebook.mp4 để cắt Short "
                f"sạch nhạc — bỏ qua còn hơn đẩy nhạc nền TikTok lên YouTube.")
        log(f"[short] Thiếu bản giọng trần → cắt từ {thay_the.name} "
            f"(sạch nhạc nhưng CHƯA có khung tiêu đề).")
        src = thay_the

    try:
        duration = probe_audio_duration(src)
    except ClipFinderError as e:
        raise RuntimeError(f"Không đọc được thời lượng {src.name}: {e}") from e

    if duration <= max_seconds:
        log(f"[short] {src.name} chỉ {_fmt(duration)} (≤ {_fmt(max_seconds)}) → lấy trọn.")
        cut = duration
    else:
        cut = find_cut_point(src, voice, max_seconds, log=log)

    # ── Đường chính: dựng lại hình để dòng dưới là 'Tập Số N' ──────────────────
    if khung is None:
        khung = tap_dung_khung_doc(folder)
    da_dung = False
    if khung:
        da_dung = build_short_so_tap(
            folder, voice or src, cut, out, caption=caption, che_chu=che_chu,
            cover_png=cover_png or find_cover(folder), log=log, progress=progress)
        if not da_dung:
            log(f"⚠ Short lùi về cắt thẳng từ {src.name} → dòng chữ dưới GIỮ như bản "
                f"TikTok, chưa phải số tập.")

    # ── Đường lùi: cắt thẳng, hình copy nguyên (chữ đã nung trong hình đi theo) ──
    if not da_dung:
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(src)]
        if voice is not None:
            # Chỉ luồng tiếng bị thay bằng giọng trần.
            cmd += ["-i", str(voice), "-map", "0:v:0", "-map", "1:a:0",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", AUDIO_BITRATE]
        else:
            cmd += ["-c", "copy"]
        cmd += ["-t", f"{cut:.3f}", "-movflags", "+faststart", str(out)]

        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                             errors="replace", creationflags=CREATE_NO_WINDOW)
        if res.returncode != 0 or not out.exists() or out.stat().st_size == 0:
            raise RuntimeError(f"ffmpeg cắt Short lỗi: {res.stderr.strip().splitlines()[-1:]}")

    # Hình copy chỉ cắt được ở frame gần nhất, độ dài thật lệch vài phần trăm giây so
    # với điểm cắt — đọc lại để chắc chắn vẫn dưới mốc 3 phút của YouTube.
    try:
        thuc = probe_audio_duration(out)
    except ClipFinderError:
        thuc = cut
    tieng = f"tiếng ← {voice.name}" if voice is not None else f"tiếng ← {src.name} (vốn không nhạc)"
    cach = "dựng lại hình + dòng số tập" if da_dung else f"cắt {src.name}"
    log(f"✂ Short: {cach}, dừng tại {_fmt(cut)} (gốc {_fmt(duration)}), {tieng} "
        f"→ {out.name} [{_fmt(thuc)}]")
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
        build_short(src, sys.argv[2] if len(sys.argv) > 2 else None)
    except RuntimeError as e:
        print(f"Lỗi: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
