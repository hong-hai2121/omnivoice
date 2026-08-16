# -*- coding: utf-8 -*-
"""timvungsub.py — Dò DẢI PHỤ ĐỀ TRUNG đốt sẵn trong hình, cho bước gắn sub che đi.

Cách dò (rẻ, không cần OCR): lấy ~10 khung hình rải đều video, tìm điểm ảnh
kiểu "chữ sáng có viền tối sát cạnh" ở NỬA DƯỚI khung — đặc trưng của hardsub
(trắng/vàng, viền đen); cộng dồn theo từng HÀNG ngang qua các khung: hàng nào
có chữ ở >= 2 khung khác nhau là thuộc dải sub (chữ đổi câu liên tục nhưng
dải thì đứng yên — logo/watermark tĩnh cũng lọt nhưng thường lệch hẳn ra một
run riêng và bị loại vì điểm thấp). Trục ngang lấy TRỌN bề rộng video.

Kết quả cache vào <video>_vungsub.json cạnh video — dựng lại không phải dò
lại; dò lệch thì sửa tay file đó (hoặc xoá đi cho dò lại từ đầu).

Chạy tay:  python myvideo/timvungsub.py "output/…/…_x0.7.mp4"
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

SO_KHUNG = 10          # 5-10 khung là đủ: chỉ cần >=2 khung có sub trùng hàng
SCALE_W = 640          # dò trên bản thu nhỏ — nhanh và đỡ nhiễu hạt
NGUONG_SANG = 190      # điểm chữ: sáng hơn mức này (bắt cả chữ trắng lẫn vàng)
NGUONG_TOI = 70        # …và có điểm tối hơn mức này ngay cạnh (viền chữ)
BK_VIEN = 2            # bán kính tìm viền tối quanh điểm sáng (px trên bản 640)
TI_LE_HANG = 0.012     # hàng có >=1.2% bề ngang là điểm-chữ mới tính "có chữ"
                       # (mép trên/dưới của con chữ thưa điểm hơn phần thân)
KHUNG_CO_SUB = 2       # hàng phải có chữ ở ít nhất N khung
GAP_NOI = 0.025        # hai run cách nhau < 2.5% chiều cao thì nối (khe 2 dòng sub)
DEM_DOC = 0.025        # đệm thêm trên/dưới dải — rộng tay chút, dải mờ cao hơn
                       # vài px không ai thấy, hở chân chữ Trung thì thấy ngay
TU_Y = 0.42            # chỉ dò từ 42% chiều cao trở xuống — sub kiểu video truyện
                       # hay nằm NGAY GIỮA khung, không phải lúc nào cũng sát đáy


def _probe(video) -> tuple[int, int, float]:
    """→ (rộng, cao, thời lượng giây) của luồng hình."""
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-show_entries", "format=duration",
         "-of", "json", str(video)],
        capture_output=True, text=True, check=True)
    d = json.loads(r.stdout)
    st = d["streams"][0]
    return int(st["width"]), int(st["height"]), float(d["format"]["duration"])


def _khung_xam(video, t: float, w_nho: int, h_nho: int) -> np.ndarray | None:
    """Một khung hình tại giây t, thu nhỏ, xám 8-bit → mảng (h, w)."""
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(video),
         "-frames:v", "1", "-vf", f"scale={w_nho}:{h_nho}",
         "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        capture_output=True)
    buf = r.stdout
    if len(buf) < w_nho * h_nho:
        return None
    return np.frombuffer(buf[:w_nho * h_nho], dtype=np.uint8).reshape(h_nho, w_nho)


def _loc_min(a: np.ndarray, r: int) -> np.ndarray:
    """Min-filter cửa sổ (2r+1)² bằng dịch mảng — khỏi cần scipy."""
    out = a.astype(np.uint8).copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dy == 0 and dx == 0:
                continue
            s = np.roll(np.roll(a, dy, axis=0), dx, axis=1)
            np.minimum(out, s, out=out)
    return out


def _cache_path(video) -> Path:
    v = Path(video)
    return v.with_name(v.stem + "_vungsub.json")


def tim_vung(video, so_khung: int = SO_KHUNG, dung_cache: bool = True) -> dict | None:
    """Dò dải sub → {"y0", "y1", "w", "h"} theo PIXEL GỐC của video, None nếu
    không thấy dải nào (video không có hardsub)."""
    video = Path(video)
    cache = _cache_path(video)
    if dung_cache and cache.is_file():
        try:
            d = json.loads(cache.read_text(encoding="utf-8"))
            if all(k in d for k in ("y0", "y1", "w", "h")):
                print(f"♻ Dùng vùng sub đã dò: {cache.name} "
                      f"(y {d['y0']}–{d['y1']}) — xoá file này nếu muốn dò lại.")
                return d
        except Exception:
            pass

    w, h, dur = _probe(video)
    h_nho = max(2, round(h * SCALE_W / w / 2) * 2)
    diem = np.zeros(h_nho, dtype=np.int32)      # tổng điểm-chữ từng hàng (mọi khung)
    co_chu = np.zeros(h_nho, dtype=np.int32)    # số khung mà hàng này có chữ

    mocs = np.linspace(0.05 * dur, 0.95 * dur, so_khung)
    for t in mocs:
        g = _khung_xam(video, float(t), SCALE_W, h_nho)
        if g is None:
            continue
        m = (g > NGUONG_SANG) & (_loc_min(g, BK_VIEN) < NGUONG_TOI)
        m[: int(h_nho * TU_Y)] = False          # bỏ phần trên khung (logo/tiêu đề)
        hang = m.sum(axis=1)
        diem += hang
        co_chu += hang > SCALE_W * TI_LE_HANG

    ok = co_chu >= KHUNG_CO_SUB
    if not ok.any():
        return None

    # Gom hàng đạt thành các RUN liên tục, nối run cách nhau sát (khe 2 dòng sub),
    # rồi lấy run tổng điểm cao nhất — loại watermark/logo lệch chỗ, điểm thấp.
    runs, i = [], 0
    idx = np.flatnonzero(ok)
    a = prev = idx[0]
    for y in idx[1:]:
        if y - prev > max(2, int(GAP_NOI * h_nho)):
            runs.append((a, prev))
            a = y
        prev = y
    runs.append((a, prev))
    y0s, y1s = max(runs, key=lambda r: int(diem[r[0]:r[1] + 1].sum()))

    dem = max(1, int(DEM_DOC * h_nho))
    y0 = max(0, int((y0s - dem) * h / h_nho))
    y1 = min(h, int((y1s + 1 + dem) * h / h_nho))
    vung = {"y0": y0, "y1": y1, "w": w, "h": h,
            "so_khung": so_khung, "ghi_chu": "sửa y0/y1 nếu dò lệch; xoá file để dò lại"}
    if dung_cache:
        try:
            cache.write_text(json.dumps(vung, ensure_ascii=False, indent=2),
                             encoding="utf-8")
        except OSError:
            pass
    print(f"🔎 Dải sub Trung: y {y0}–{y1} / cao {h}px "
          f"(dày {y1 - y0}px, dò {so_khung} khung hình)")
    return vung


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if len(sys.argv) < 2:
        print("Dùng: python timvungsub.py <video> [số khung]")
        raise SystemExit(1)
    n = int(sys.argv[2]) if len(sys.argv) > 2 else SO_KHUNG
    v = tim_vung(sys.argv[1], so_khung=n, dung_cache=False)
    print(v if v else "Không thấy dải sub nào ở nửa dưới khung hình.")


if __name__ == "__main__":
    main()
