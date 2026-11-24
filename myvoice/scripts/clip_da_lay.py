# -*- coding: utf-8 -*-
"""
Sổ "clip đã lấy" của kho clip ghép ngẫu nhiên (videongang/, videodoc/) — 18/11/2026.

User: "random lấy video nào thì đánh dấu đã lấy rồi, lần sau chọn video khác không bị trùng
với video đã chọn của các lần trước; khi nào chọn hết các video trong folder đang chọn thì
reset lại từ đầu; có thể cập nhật thư mục và video vào folder".

  - Dựng xong một video, các clip vừa ghép được ghi vào SO_FILE (khoá = đường dẫn clip).
    Dựng hỏng / bị ngắt thì KHÔNG ghi (clip chưa thật sự lên video nào).
  - Lần dựng sau chỉ bốc trong số clip CHƯA lấy của các thư mục đang chọn.
  - Hết clip chưa lấy → RESET riêng các thư mục đang chọn (xoá dấu của chúng), xáo lại và lấy
    tiếp từ đầu. Thư mục không chọn giữ nguyên dấu.
  - Thêm thư mục / thêm video vào kho không phải làm gì: clip mới chưa có trong sổ nên tự là
    "chưa lấy" và được bốc trước; clip đã xoá khỏi đĩa thì dòng của nó bị bỏ ở lần ghi kế.

Chỉ dùng thư viện chuẩn: GUI / web gọi dem() để hiện "còn x/y" mà không phải nạp
numpy/scipy của video_khung.
"""

import json
import os
import random
import time
from pathlib import Path

SO_FILE = Path(__file__).resolve().parent / "clip_da_lay.json"


def khoa(clip) -> str:
    """Khoá của một clip trong sổ: đường dẫn tuyệt đối, Windows thì không phân biệt hoa/thường."""
    return os.path.normcase(os.path.abspath(os.fspath(clip)))


def doc_so() -> dict:
    """Sổ {khoá clip: thời điểm lấy (giây epoch)}. File thiếu/hỏng → {} (chưa lấy clip nào)."""
    try:
        so = json.loads(SO_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return so if isinstance(so, dict) else {}


def _ghi_so(so: dict) -> None:
    """Ghi qua file tạm rồi đổi tên: bị ngắt giữa chừng cũng không để lại sổ cụt."""
    tam = SO_FILE.with_name(SO_FILE.name + ".tmp")
    tam.write_text(json.dumps(so, ensure_ascii=False, indent=0), encoding="utf-8")
    os.replace(tam, SO_FILE)


def da_lay_trong(videos, so: dict | None = None) -> set:
    """Các clip trong `videos` đang mang dấu "đã lấy"."""
    so = doc_so() if so is None else so
    return {v for v in videos if khoa(v) in so}


def chon(videos, durations, target, da_lay=()):
    """Xếp clip cho đủ `target` giây, bốc clip CHƯA lấy trước (thứ tự ngẫu nhiên).

    da_lay: các clip của kho này đã lấy ở những lần dựng trước. Hết clip chưa lấy → reset:
    cả kho lại là "chưa lấy", xáo lại rồi bốc tiếp — clip chưa có trong video đang xếp đi
    trước, nên một video chỉ lặp clip khi kho ngắn hơn audio.

    Trả về (seq, total, moi, so_reset): `moi` = các clip sẽ mang dấu "đã lấy" do lượt này
    (có reset thì chỉ tính từ lần reset cuối), `so_reset` > 0 = phải xoá dấu cũ của kho trước
    khi ghi `moi` (xem danh_dau).
    """
    videos = list(videos)
    da_cu = set(da_lay)
    pool = [v for v in videos if v not in da_cu]
    random.shuffle(pool)
    seq, total, moi, so_reset = [], 0.0, set(), 0
    while total < target:
        if not pool:
            trong_video = set(seq)
            cu = [v for v in videos if v in trong_video]
            pool = [v for v in videos if v not in trong_video]
            random.shuffle(cu)
            random.shuffle(pool)
            pool = cu + pool            # pop() lấy từ cuối → clip chưa có trong video này đi trước
            # Chỗ nối hai vòng: đừng phát liền hai lần cùng một clip.
            if seq and len(pool) > 1 and pool[-1] == seq[-1]:
                pool[0], pool[-1] = pool[-1], pool[0]
            moi = set()
            so_reset += 1
        v = pool.pop()
        seq.append(v)
        moi.add(v)
        total += durations[v]
    return seq, total, moi, so_reset


def danh_dau(videos, moi, reset: bool = False) -> None:
    """Ghi sổ SAU khi dựng xong: reset=True thì xoá dấu của mọi clip trong kho `videos` trước,
    rồi đánh dấu các clip `moi`. Đọc lại sổ ngay lúc ghi (việc khác có thể vừa ghi xong) và
    bỏ luôn dòng của clip không còn trên đĩa."""
    so = doc_so()
    if reset:
        for v in videos:
            so.pop(khoa(v), None)
    luc = round(time.time())
    for v in moi:
        so.setdefault(khoa(v), luc)
    _ghi_so({k: t for k, t in so.items() if os.path.exists(k)})


def chon_co_nho(videos, durations, target):
    """chon() có NHỚ qua các lần dựng → (seq, total, ghi, mo_ta).

    ghi(log=print): gọi SAU khi ffmpeg dựng xong để lưu dấu "đã lấy" (không gọi = không ghi
    gì, lần sau vẫn bốc như chưa có lượt này). mo_ta: một dòng cho nhật ký.
    """
    videos = list(videos)
    da_cu = da_lay_trong(videos)
    seq, total, moi, so_reset = chon(videos, durations, target, da_cu)
    n = len(videos)
    truoc = n - len(da_cu)
    con = n - len(moi) - (0 if so_reset else len(da_cu))
    if so_reset:
        dau = (f"đã lấy hết {n} clip của nguồn đang chọn" if truoc == 0 else
               f"chỉ còn {truoc}/{n} clip chưa lấy, không đủ cho video này → lấy nốt rồi")
        mo_ta = f"{dau} → 🔄 RESET, lấy lại từ đầu (sau video này còn {con} clip chưa lấy)"
    else:
        mo_ta = (f"còn {truoc}/{n} clip chưa lấy → lấy {len(moi)} clip, không trùng các lần "
                 f"trước (sau video này còn {con} clip chưa lấy)")
    if len(seq) > len(set(seq)):
        mo_ta += " — ⚠ nguồn đang chọn ngắn hơn audio nên có clip lặp lại trong cùng video"

    def ghi(log=print):
        try:
            danh_dau(videos, moi, bool(so_reset))
        except OSError as e:
            log(f"[Cảnh báo] Không lưu được sổ clip đã lấy ({SO_FILE.name}): {e}")

    return seq, total, ghi, mo_ta


def dem(thu_muc, so: dict | None = None) -> tuple[int, int]:
    """(số clip CHƯA lấy, tổng số clip .mp4) của một thư mục kho — ô chọn nguồn hiện "còn x/y"."""
    so = doc_so() if so is None else so
    clips = list(Path(thu_muc).glob("*.mp4"))
    return sum(1 for c in clips if khoa(c) not in so), len(clips)


def dat_lai(cac_thu_muc, de_quy: bool = False) -> int:
    """Xoá dấu "đã lấy" của mọi clip .mp4 trong các thư mục (nút ↺ "lấy lại từ đầu") →
    số dấu đã xoá. de_quy=True: tính cả clip trong thư mục con (cả kho)."""
    so = doc_so()
    n = 0
    for d in cac_thu_muc:
        d = Path(d)
        for c in (d.rglob("*.mp4") if de_quy else d.glob("*.mp4")):
            if so.pop(khoa(c), None) is not None:
                n += 1
    if n:
        _ghi_so(so)
    return n
