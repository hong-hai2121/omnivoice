# -*- coding: utf-8 -*-
"""doan.py — Video DÀI chia thành các ĐOẠN ~30 phút, chạy quy trình từng đoạn rồi GHÉP.

Vì sao (22/10/2026, theo yêu cầu người dùng): bài 2 giờ chạy nguyên khối thì mỗi
bước là một lượt dài không có điểm dừng (Gemini vài chục lô liền, hàng nghìn câu
TTS, một lệnh ffmpeg 2 giờ 30), lỗi giữa chừng là mất cả lượt; và bộ xếp
timeline chống đè chỉ cứu được khi còn khe trống — tiếng Việt dài hơn hình thì
cả bài dồn về cuối. Chia ~30 phút: mỗi đoạn tự cân trong khung của nó, bước
nào hỏng chỉ làm lại đoạn đó, kết quả từng đoạn giữ nguyên trên đĩa.

Cắt Ở ĐÂU: bước ① đã nhận diện giọng nói cả bài (mốc giờ từng chữ) nên biết
câu nào kết thúc lúc nào — tới mốc 30 phút thì ĐỢI HẾT CÂU đang nói mới cắt
(ưu tiên câu có dấu kết 。！？; không có thì khe lặng dài nhất), muộn nhất 35
phút; đoạn dài 30–35 phút là bình thường. Mốc cắt nằm GIỮA khe lặng hai câu
nên không câu nào bị bổ đôi; đoạn cuối ngắn dưới 5 phút thì gộp vào đoạn trước.

Tên file (cùng thư mục với gốc, bước ①–④ dùng y hệt một video thường):
    <tên>_x0.7_doan.json          sổ đoạn (speed, mốc giây THEO VIDEO ĐÃ CHẬM)
    <tên>_d01_x0.7.mp4 / .srt     đoạn 1: video chậm + SRT gốc (mốc giờ tính từ 0)
    <tên>_d01_x0.7_vi.srt, _vi_audio.wav, _vi_sapxep.srt, _sub.mp4 …  kết quả từng bước
    <tên>_x0.7.mp4, _vi.srt, _vi_audio.wav, _vi_sapxep.srt, _sub.mp4
                                  bản GHÉP của cả bài — đúng tên bước sau / SEO /
                                  thumbnail / đăng bài vẫn tìm, nên phần còn lại
                                  của web không phải biết gì về đoạn.

Ghép thế nào: video nối bằng concat demuxer -c copy (các đoạn cùng một script
dựng nên cùng codec/cỡ khung — không encode lại, không mất chất); SRT/timeline
cộng mốc giờ theo THỜI LƯỢNG THẬT của từng đoạn video (ffprobe) nên khớp với
video đã nối tới từng mili giây; audio wav cắt/đệm mỗi đoạn đúng bằng thời
lượng đoạn video rồi nối tiếp.

Ai dùng: video_chamlai_srt.py (--chia-doan: ghi sổ + SRT từng đoạn + render từng
đoạn + nối video chậm), chay_doan.py (chạy ②③④ từng đoạn rồi ghép), web/steps.py
(ẩn các hàng đoạn khỏi bảng, đếm số đoạn).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
DOAN_RE = re.compile(r"_d\d{2}_x\d")       # tên đoạn: <tên>_d01_x0.7
HAU_TO_SO = "_doan.json"
_SRT_TIME = re.compile(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})")


# ── Sổ đoạn ──────────────────────────────────────────────────────────────────
def so_path(base) -> Path:
    """<gốc>_doan.json — gốc là đường dẫn KHÔNG đuôi (…/<tên>_x0.7)."""
    return Path(f"{base}{HAU_TO_SO}")


def ten_doan(base_name: str, k: int, tag: str) -> str:
    """'<tên>' + '_d01' + '_x0.7' — chèn số đoạn TRƯỚC tag tốc độ để bảng kết quả
    nhận ra (DOAN_RE) và base_for vẫn cắt đúng tag."""
    return f"{base_name}_d{k:02d}{tag}"


def doc_so(base) -> dict | None:
    try:
        d = json.loads(so_path(base).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) and d.get("doan") else None
    except (OSError, ValueError):
        return None


def ghi_so(base, speed: float, goc: str, lang: str, doan: list[dict]) -> Path:
    p = so_path(base)
    p.write_text(json.dumps({"speed": speed, "goc": goc, "lang": lang, "doan": doan},
                            ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def cac_doan(base) -> list[Path]:
    """Gốc (không đuôi) của từng đoạn, theo thứ tự — [] nếu video không chia."""
    so = doc_so(base)
    if not so:
        return []
    return [Path(base).parent / d["ten"] for d in so["doan"]]


# ── ffprobe / ffmpeg ─────────────────────────────────────────────────────────
def thoi_luong(path) -> float:
    """Thời lượng (giây) theo ffprobe; 0.0 nếu không đọc được."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=120, creationflags=CREATE_NO_WINDOW)
        return float(r.stdout.strip() or 0)
    except Exception:
        return 0.0


def thoi_luong_doan(base) -> list[float]:
    """Thời lượng THẬT của từng đoạn video chậm (<đoạn>.mp4) — mốc ghép SRT/audio
    phải theo số này (video nối bằng -c copy xếp đúng từng đoạn nối nhau).
    Đoạn chưa có video thì lấy den_s − tu_s trong sổ."""
    so = doc_so(base) or {"doan": []}
    ra = []
    for d, C in zip(so["doan"], cac_doan(base)):
        t = thoi_luong(f"{C}.mp4")
        ra.append(t if t > 0 else float(d["den_s"]) - float(d["tu_s"]))
    return ra


def _concat_list(parts, list_path: Path) -> None:
    # concat demuxer: đường dẫn bọc nháy đơn, nháy đơn trong tên escape thành '\''.
    lines = []
    for p in parts:
        s = str(Path(p).resolve()).replace("\\", "/").replace("'", "'\\''")
        lines.append(f"file '{s}'")
    list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def noi_video(parts, dst) -> bool:
    """Nối các mp4 cùng chuẩn bằng concat demuxer, -c copy (không encode lại)."""
    parts = [Path(p) for p in parts]
    thieu = [p.name for p in parts if not p.is_file()]
    if thieu:
        print(f"❌ Thiếu đoạn để nối: {', '.join(thieu)}")
        return False
    dst = Path(dst)
    lst = dst.with_name(f"~noi_{os.getpid()}.txt")
    tmp = dst.with_name(f"~noi_{os.getpid()}{dst.suffix}")
    try:
        _concat_list(parts, lst)
        r = subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                            "-c", "copy", "-movflags", "+faststart",
                            "-loglevel", "error", str(tmp)])
        if r.returncode != 0 or not tmp.is_file():
            print("❌ ffmpeg nối video lỗi.")
            return False
        os.replace(tmp, dst)
        print(f"🔗 Đã nối {len(parts)} đoạn → {dst.name}  ({thoi_luong(dst) / 60:.1f} phút)")
        return True
    finally:
        for p in (lst, tmp):
            try:
                p.unlink()
            except OSError:
                pass


# ── SRT ──────────────────────────────────────────────────────────────────────
def doc_srt(path) -> list[tuple[float, float, str]]:
    """[(start_s, end_s, text)] — text giữ nguyên nhiều dòng."""
    cues = []
    try:
        raw = Path(path).read_text(encoding="utf-8-sig")
    except OSError:
        return cues
    for block in re.split(r"\n\s*\n", raw.strip()):
        lines = [ln for ln in block.splitlines()]
        if len(lines) < 2:
            continue
        m = _SRT_TIME.search(lines[1]) or _SRT_TIME.search(lines[0])
        if not m:
            continue
        g = [int(x) for x in m.groups()]
        s = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
        e = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
        i = 2 if _SRT_TIME.search(lines[1]) else 1
        cues.append((s, e, "\n".join(lines[i:]).strip()))
    return cues


def fmt_srt_time(t: float) -> str:
    ms = int(round(max(t, 0) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def ghi_srt(cues, path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for n, (s, e, t) in enumerate(cues, 1):
            f.write(f"{n}\n{fmt_srt_time(s)} --> {fmt_srt_time(e)}\n{t}\n\n")


def noi_srt(parts, dst, dai: list[float]) -> bool:
    """Nối SRT các đoạn: mốc giờ đoạn k cộng tổng thời lượng các đoạn trước."""
    parts = [Path(p) for p in parts]
    thieu = [p.name for p in parts if not p.is_file()]
    if thieu:
        print(f"❌ Thiếu SRT để nối: {', '.join(thieu)}")
        return False
    cues, offset = [], 0.0
    for p, d in zip(parts, dai):
        cues += [(s + offset, e + offset, t) for s, e, t in doc_srt(p)]
        offset += d
    ghi_srt(cues, dst)
    print(f"🔗 Đã nối {len(parts)} SRT → {Path(dst).name}  ({len(cues)} câu)")
    return True


# ── Audio tổng (wav) ─────────────────────────────────────────────────────────
def noi_wav(parts, dst, dai: list[float]) -> bool:
    """Nối audio tổng các đoạn: mỗi đoạn CẮT/ĐỆM đúng bằng thời lượng đoạn video
    (audio bước ③ dài hơn video ~1 giây đệm) rồi ghi nối tiếp — khớp video đã nối."""
    import numpy as np
    import soundfile as sf

    parts = [Path(p) for p in parts]
    thieu = [p.name for p in parts if not p.is_file()]
    if thieu:
        print(f"❌ Thiếu audio để nối: {', '.join(thieu)}")
        return False
    sr = sf.info(str(parts[0])).samplerate
    dst = Path(dst)
    tmp = dst.with_name(f"~noi_{os.getpid()}.wav")
    try:
        with sf.SoundFile(str(tmp), "w", samplerate=sr, channels=1, subtype="PCM_16") as out:
            for p, d in zip(parts, dai):
                data, sr2 = sf.read(str(p), dtype="float32")
                if sr2 != sr:
                    print(f"❌ {p.name} có sample rate {sr2} ≠ {sr} — không nối được.")
                    return False
                if data.ndim > 1:
                    data = data.mean(axis=1)
                n = int(round(d * sr))
                if len(data) >= n:
                    data = data[:n]
                else:
                    data = np.concatenate([data, np.zeros(n - len(data), dtype="float32")])
                out.write(data)
        os.replace(tmp, dst)
        print(f"🔗 Đã nối {len(parts)} audio → {dst.name}  ({sum(dai) / 60:.1f} phút)")
        return True
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


# ── timeline.json của bước ③ ─────────────────────────────────────────────────
def noi_timeline(parts, dst, dai: list[float], srt_name: str) -> bool:
    """Gộp <đoạn>_vi_timeline.json: cộng mốc ms, đánh lại id — trang 🎞 xem cả bài."""
    cues, offset_ms, overlaps, end_us = [], 0, 0, 0
    for p, d in zip(parts, dai):
        try:
            tl = json.loads(Path(p).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            print(f"⚠️ Không đọc được {Path(p).name} — bỏ qua timeline gộp.")
            return False
        for c in tl.get("cues", []):
            c = dict(c)
            c["id"] = len(cues) + 1
            for k in ("srt_start_ms", "start_ms"):
                c[k] = int(c.get(k, 0)) + offset_ms
            cues.append(c)
        overlaps += int(tl.get("remaining_overlaps", 0))
        offset_ms += int(round(d * 1000))
        end_us += int(round(d * 1_000_000))
    Path(dst).write_text(json.dumps({
        "srt": srt_name, "timeline_end_us": end_us,
        "remaining_overlaps": overlaps, "cues": cues,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"🔗 Đã gộp timeline {len(parts)} đoạn → {Path(dst).name}")
    return True
