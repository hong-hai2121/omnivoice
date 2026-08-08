# -*- coding: utf-8 -*-
"""
don_rac.py — Dọn file audio TRUNG GIAN của một tập sau khi video đã tạo xong.

Mỗi tập để lại ~261 MB audio, trong đó chỉ output.wav là đắt:

    output.wav                  46 MB   ← GIỮ. Phải chạy lại TTS hàng chục phút.
    output_chunks/ (76 file)    47 MB   ← xoá. Chỉ là scratch để resume TTS dở dang.
    output_sped105/110.wav      86 MB   ← xoá. ffmpeg atempo từ output.wav, vài giây.
    output_tiktok*.wav          44 MB   ← xoá. Cắt từ output.wav.
    tiktok_bgm.wav              39 MB   ← xoá. Trộn nhạc nền từ output.wav.

XOÁ HẲN (không qua Thùng rác) — có chủ ý: đây là tính năng giải phóng ổ đĩa, mà file
vào Thùng rác thì vẫn chiếm chỗ tới lúc dọn thùng, coi như vô nghĩa. Bù lại, lớp an
toàn nằm ở chỗ khác và chặt hơn:

  1. CHỈ dọn khi tập ĐÃ CÓ video — chưa có thì giữ nguyên mọi thứ.
  2. CHỈ dọn khi output.wav còn nguyên — thiếu nó thì các file dẫn xuất là thứ duy
     nhất còn lại, xoá đi là mất thật.
  3. Danh sách tên file TƯỜNG MINH, và chốt chặn cuối loại output.wav ra khỏi danh
     sách dù có khớp mẫu nào đi nữa.

Chạy tay:
    python don_rac.py "đường_dẫn_thư_mục_tập"
    python don_rac.py "..." --thu       # chỉ liệt kê, KHÔNG xoá
"""

import shutil
from pathlib import Path

# Bản gốc — TUYỆT ĐỐI không xoá. Mọi file dưới đây đều sinh ra được từ nó.
FILE_GOC = "output.wav"

# Thư mục scratch của TTS (chunk từng đoạn, dùng để chạy tiếp khi đang dở).
THU_MUC_RAC = ("output_chunks",)

# Tên file dẫn xuất cố định.
FILE_RAC = ("output_half.wav", "tiktok_bgm.wav")

# Mẫu file dẫn xuất (đánh số thay đổi theo cài đặt tốc độ / % cắt).
MAU_RAC = ("output_sped*.wav", "output_tiktok*.wav")

# Video đầu ra — có ÍT NHẤT một cái mới coi là "đã làm xong video".
VIDEO_RA = ("YOUTUBE.mp4", "facebook.mp4", "tiktok.mp4", "short.mp4")
MAU_VIDEO_CU = ("*_videodone.mp4", "*_doc.mp4")   # tên các tập làm trước đây


def _mb(n_bytes):
    return n_bytes / 1048576


def co_video(folder) -> bool:
    """True nếu tập đã có ít nhất 1 video đầu ra (kể cả tên kiểu cũ)."""
    folder = Path(folder)
    if any((folder / v).exists() for v in VIDEO_RA):
        return True
    return any(next(folder.glob(m), None) is not None for m in MAU_VIDEO_CU)


def liet_ke_rac(folder):
    """Danh sách đường dẫn sẽ bị xoá (chưa xoá gì). output.wav LUÔN bị loại ra."""
    folder = Path(folder)
    items = []
    for d in THU_MUC_RAC:
        p = folder / d
        if p.is_dir():
            items.append(p)
    for f in FILE_RAC:
        p = folder / f
        if p.is_file():
            items.append(p)
    for mau in MAU_RAC:
        items.extend(p for p in sorted(folder.glob(mau)) if p.is_file())
    # ── Chốt chặn cuối: loại output.wav ra dù khớp mẫu nào đi nữa ──────────────
    return [p for p in items if p.name.lower() != FILE_GOC]


def _dung_luong(p: Path) -> int:
    if p.is_dir():
        return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
    try:
        return p.stat().st_size
    except OSError:
        return 0


def don_rac_audio(folder, on_log=print, thu=False) -> float:
    """Xoá audio trung gian của 1 tập. Trả về số MB đã giải phóng (0.0 nếu không dọn).

    thu=True: chỉ liệt kê, không xoá gì (để xem trước).
    """
    folder = Path(folder)
    ten = folder.name

    # ── Chốt 1: chưa có video thì chưa xong, giữ nguyên mọi thứ ────────────────
    if not co_video(folder):
        on_log(f"⏭ {ten}: chưa có video → KHÔNG dọn audio (giữ nguyên để chạy tiếp).")
        return 0.0

    # ── Chốt 2: mất output.wav thì file dẫn xuất là thứ duy nhất còn lại ───────
    goc = folder / FILE_GOC
    if not (goc.is_file() and goc.stat().st_size > 4096):
        on_log(f"⏭ {ten}: không thấy {FILE_GOC} → KHÔNG dọn (file dẫn xuất lúc này "
               "là bản audio duy nhất còn lại, xoá đi là mất thật).")
        return 0.0

    rac = liet_ke_rac(folder)
    if not rac:
        return 0.0

    tong = sum(_dung_luong(p) for p in rac)
    if thu:
        on_log(f"🔎 {ten}: sẽ xoá {len(rac)} mục, giải phóng {_mb(tong):.0f} MB:")
        for p in rac:
            on_log(f"     • {p.name}  ({_mb(_dung_luong(p)):.1f} MB)")
        return 0.0

    n_ok = 0
    for p in rac:
        try:
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()
            n_ok += 1
        except Exception as e:
            on_log(f"⚠️ {ten}: không xoá được {p.name}: {e}")
    on_log(f"🧹 {ten}: đã dọn {n_ok}/{len(rac)} mục audio trung gian, "
           f"giải phóng {_mb(tong):.0f} MB (giữ {FILE_GOC}).")
    return _mb(tong)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(
        description="Dọn audio trung gian của 1 thư mục tập (giữ output.wav).")
    ap.add_argument("folder", help="Thư mục tập cần dọn.")
    ap.add_argument("--thu", action="store_true", help="Chỉ liệt kê, KHÔNG xoá.")
    a = ap.parse_args(argv)
    don_rac_audio(Path(a.folder), thu=a.thu)


if __name__ == "__main__":
    main()
