# -*- coding: utf-8 -*-
"""chay_doan.py — Chạy MỘT bước (② dịch / ③ giọng / ④ gắn) cho TỪNG ĐOẠN của
video đã chia, rồi GHÉP kết quả thành bản cả bài. Video không chia (không có
<gốc>_doan.json) thì chạy lệnh y nguyên — nên web bọc MỌI bước ②③④ qua đây,
khỏi phải biết trước video có bị chia hay không (bước ① mới quyết định).

    chay_doan.py --base <gốc không đuôi> --buoc dich|giong|gan [--bo-qua-da-xong]
                 -- <lệnh của bước, viết cho gốc CẢ BÀI>

Cách chạy từng đoạn: mọi tham số chứa đường dẫn gốc cả bài được THAY bằng gốc
đoạn (…\\<tên>_x0.7 → …\\<tên>_d01_x0.7) — các script ②③④ chỉ nhìn tên file nên
không phải sửa gì. Lệnh của đoạn nào lỗi thì dừng ở đó với đúng mã lỗi; đoạn đã
xong giữ nguyên trên đĩa, chạy lại là tiếp.

--bo-qua-da-xong (nút ⏩ của bảng): đoạn đã có kết quả của bước này thì bỏ qua —
còn ▶/②③④ bấm tay thì chạy lại mọi đoạn, đúng nghĩa "chạy lại".

Ghép sau khi đủ đoạn (xem doan.py): ② → _vi.srt (+ song ngữ) · ③ → _vi_sapxep.srt,
_vi_audio.wav, _vi_timeline.json · ④ → _sub.mp4 (hoặc _doc.mp4 khi --khung doc).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import doan  # noqa: E402


def _la_doc(argv: list[str]) -> bool:
    try:
        return argv[argv.index("--khung") + 1] == "doc"
    except (ValueError, IndexError):
        return False


def _ket_qua(C: Path, buoc: str, doc: bool) -> list[Path]:
    """File kết quả của bước `buoc` cho gốc C — có đủ là coi như đoạn đã xong."""
    if buoc == "dich":
        return [Path(f"{C}_vi.srt")]
    if buoc == "giong":
        return [Path(f"{C}_vi_audio.wav"), Path(f"{C}_vi_sapxep.srt")]
    return [Path(f"{C}_doc.mp4" if doc else f"{C}_sub.mp4")]


def ghep(base: Path, buoc: str, doc: bool) -> bool:
    cac = doan.cac_doan(base)
    dai = doan.thoi_luong_doan(base)
    B = str(base)
    print(f"\n🧩 Ghép {len(cac)} đoạn → bản cả bài ({Path(B).name})")
    if buoc == "dich":
        ok = doan.noi_srt([f"{C}_vi.srt" for C in cac], f"{B}_vi.srt", dai)
        # Bản song ngữ: có đủ ở mọi đoạn mới nối (thiếu thì thôi, không bắt buộc).
        for hau in ("_zhvi.srt", "_envi.srt"):
            parts = [Path(f"{C}{hau}") for C in cac]
            if all(p.is_file() for p in parts):
                doan.noi_srt(parts, f"{B}{hau}", dai)
        return ok
    if buoc == "giong":
        ok = doan.noi_srt([f"{C}_vi_sapxep.srt" for C in cac], f"{B}_vi_sapxep.srt", dai)
        ok = doan.noi_wav([f"{C}_vi_audio.wav" for C in cac], f"{B}_vi_audio.wav", dai) and ok
        parts = [Path(f"{C}_vi_timeline.json") for C in cac]
        if all(p.is_file() for p in parts):
            doan.noi_timeline(parts, f"{B}_vi_timeline.json", dai,
                              srt_name=Path(f"{B}_vi.srt").name)
        return ok
    hau = "_doc.mp4" if doc else "_sub.mp4"
    ok = doan.noi_video([f"{C}{hau}" for C in cac], f"{B}{hau}")
    # Video chậm cả bài (bước ① thường đã nối; lỡ thiếu thì nối ở đây cho
    # thumbnail / trang vùng sub có cái mà dùng).
    if ok and not Path(f"{B}.mp4").is_file():
        doan.noi_video([f"{C}.mp4" for C in cac], f"{B}.mp4")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description="Chạy một bước cho từng đoạn rồi ghép.")
    ap.add_argument("--base", required=True, help="gốc cả bài, không đuôi (…\\<tên>_x0.7)")
    ap.add_argument("--buoc", required=True, choices=["dich", "giong", "gan"])
    ap.add_argument("--bo-qua-da-xong", action="store_true",
                    help="đoạn đã có kết quả của bước này thì bỏ qua (nút ⏩)")
    ap.add_argument("lenh", nargs=argparse.REMAINDER, help="-- rồi lệnh của bước")
    a = ap.parse_args()
    argv = a.lenh[1:] if a.lenh and a.lenh[0] == "--" else a.lenh
    if not argv:
        print("❌ Thiếu lệnh của bước (sau --).")
        return 2
    base = Path(a.base)
    cac = doan.cac_doan(base)
    if not cac:
        # Video không chia → chạy y nguyên, trong suốt với hàng đợi.
        return subprocess.run(argv).returncode

    doc = _la_doc(argv)
    # Gốc cả bài có thể xuất hiện trong lệnh với dấu \\ hay / (web dùng \\, gọi
    # tay hay dùng /) — thay cả hai dạng, dạng dài trước kẻo thay dở chừng.
    dang_goc = sorted({a.base, str(base), str(base).replace("\\", "/")}, key=len, reverse=True)
    print(f"✂ Video chia {len(cac)} đoạn — chạy bước {a.buoc} từng đoạn"
          + (" (bỏ qua đoạn đã xong)" if a.bo_qua_da_xong else "") + ".")
    for k, C in enumerate(cac, 1):
        if a.bo_qua_da_xong and all(p.is_file() for p in _ket_qua(C, a.buoc, doc)):
            print(f"♻ Đoạn {k}/{len(cac)} ({C.name}) đã xong — bỏ qua.")
            continue
        print(f"\n━━━━━━━━ Đoạn {k}/{len(cac)}: {C.name} ━━━━━━━━", flush=True)
        argv_c = list(argv)
        for g in dang_goc:
            argv_c = [s.replace(g, str(C)) for s in argv_c]
        if argv_c == argv:
            print(f"❌ Lệnh không chứa đường dẫn gốc cả bài ({base}) — không biết thay "
                  "sang đoạn nào. Lệnh phải viết theo gốc cả bài (xem đầu file).")
            return 2
        rc = subprocess.run(argv_c).returncode
        if rc != 0:
            print(f"\n❌ Đoạn {k}/{len(cac)} lỗi (mã {rc}) — dừng. Đoạn đã xong giữ "
                  "nguyên, chạy lại là làm tiếp từ đoạn này.")
            return rc
    thieu = [C.name for C in cac
             if not all(p.is_file() for p in _ket_qua(C, a.buoc, doc))]
    if thieu:
        print(f"❌ Chạy xong mà thiếu kết quả ở: {', '.join(thieu)} — không ghép.")
        return 1
    return 0 if ghep(base, a.buoc, doc) else 1


if __name__ == "__main__":
    sys.exit(main())
