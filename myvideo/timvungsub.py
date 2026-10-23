# -*- coding: utf-8 -*-
"""timvungsub.py — Dò DẢI PHỤ ĐỀ TRUNG đốt sẵn trong hình, cho bước gắn sub che đi.

Cách dò (rẻ, không cần OCR): lấy vài khung hình, tìm điểm ảnh kiểu "chữ sáng
có viền tối sát cạnh" ở NỬA DƯỚI khung — đặc trưng của hardsub (trắng/vàng,
viền đen); cộng dồn theo từng HÀNG ngang qua các khung: hàng nào có chữ ở >= 2
khung khác nhau là thuộc dải sub (chữ đổi câu liên tục nhưng dải thì đứng yên
— logo/watermark tĩnh cũng lọt nhưng thường lệch hẳn ra một run riêng và bị
loại vì điểm thấp). Trục ngang lấy TRỌN bề rộng video.

KHUNG LẤY Ở ĐÂU (22/10/2026): lấy ở LÚC CÓ GIỌNG NÓI, và KIỂM từng khung.
Bước ① đã nhận diện giọng nói cả bài (<video>.srt cạnh video, mốc giờ từng
câu) — hardsub chỉ hiện khi có người nói, nên bốc khung trong lúc có tiếng là
gần như chắc có chữ; khung rải đều mù quáng như trước hay rơi vào màn tiêu đề /
cảnh im lặng (không có sub). Cách chọn: chia tổng thời gian có giọng nói thành
SO_KHUNG phần bằng nhau → 5 khung NGẪU NHIÊN nhưng CÁCH NHAU ĐỀU; mỗi phần bốc
một mốc rồi KIỂM khung đó có chữ kiểu hardsub thật không (cue hardsub ngắn hơn
câu Whisper gộp, có lúc đang nói mà chữ đã tắt) — không có thì bốc lại mốc khác
trong cùng phần, tối đa SO_THU lần. Khung nào cũng có chữ nên dải sub có mặt ở
MỌI khung, còn chữ cảnh/tiêu đề chỉ lọt 1–2 khung → chọn run có mặt ở nhiều
khung nhất (hoà thì theo điểm). Không có SRT (video thô chưa qua bước ①) thì lùi
về rải đều 10 khung như cũ, chọn run theo điểm.

Kết quả cache vào <video>_vungsub.json cạnh video — dựng lại không phải dò
lại; dò lệch thì sửa tay file đó (hoặc xoá đi cho dò lại từ đầu). File ghi kèm
"moc_giay" = các mốc khung đã dùng, trang 🫥 trên web soi lại đúng khung đó.

Chạy tay:  python myvideo/timvungsub.py "output/…/…_x0.7.mp4" [--so-khung 5] [--srt …]
"""

from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

SO_KHUNG = 5           # khung lấy ở lúc CÓ GIỌNG NÓI — 5 là đủ vì khung nào cũng có chữ
SO_KHUNG_RAI = 10      # không có SRT → rải đều cả video; nhiều hơn vì có khung im lặng
SO_THU = 6             # mỗi phần bốc tối đa N mốc tới khi gặp khung có chữ
CAT_MEP_CAU = 0.15     # bỏ 15% đầu/cuối mỗi câu (hardsub hiện/tắt lệch tiếng vài trăm ms)
CAU_TOI_THIEU = 0.6    # câu ngắn hơn (giây) thì bỏ — hardsub có khi không kịp hiện
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
DIEM_CO_CHU = 80       # MỘT khung "có chữ" khi có run dày >= 3 hàng và tổng điểm-chữ
HANG_CO_CHU = 3        # >= 80 (trên bản 640 — một dòng sub ngắn ~100, nhiễu hạt < 60)

_SRT_TIME = re.compile(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})")


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


def _hang_chu(g: np.ndarray) -> np.ndarray:
    """Số điểm-chữ (sáng, có viền tối sát cạnh) trên từng HÀNG của một khung xám;
    phần trên khung (TU_Y) bỏ hẳn — logo/tiêu đề không tính."""
    m = (g > NGUONG_SANG) & (_loc_min(g, BK_VIEN) < NGUONG_TOI)
    m[: int(g.shape[0] * TU_Y)] = False
    return m.sum(axis=1)


def _runs(ok: np.ndarray, h_nho: int) -> list[tuple[int, int]]:
    """Gom các hàng đạt (mask bool) thành RUN liên tục [(y_đầu, y_cuối)], nối hai
    run cách nhau sát (khe 2 dòng sub)."""
    idx = np.flatnonzero(ok)
    if not len(idx):
        return []
    runs, a, prev = [], idx[0], idx[0]
    for y in idx[1:]:
        if y - prev > max(2, int(GAP_NOI * h_nho)):
            runs.append((int(a), int(prev)))
            a = y
        prev = y
    runs.append((int(a), int(prev)))
    return runs


def _co_chu(g: np.ndarray | None) -> bool:
    """Khung này có CHỮ kiểu hardsub không: một run dày >= HANG_CO_CHU hàng với
    tổng điểm >= DIEM_CO_CHU (nhiễu hạt / mép sáng chỉ 1-2 hàng, điểm thấp)."""
    if g is None:
        return False
    hang = _hang_chu(g)
    w = g.shape[1]
    for a, b in _runs(hang > w * TI_LE_HANG, g.shape[0]):
        if b - a + 1 >= HANG_CO_CHU and int(hang[a:b + 1].sum()) >= DIEM_CO_CHU * w / SCALE_W:
            return True
    return False


def _cache_path(video) -> Path:
    v = Path(video)
    return v.with_name(v.stem + "_vungsub.json")


# ── Mốc khung ở lúc có giọng nói ─────────────────────────────────────────────
def _doc_srt(path) -> list[tuple[float, float]]:
    """[(start_s, end_s)] của từng câu trong SRT — chỉ cần mốc giờ, bỏ chữ."""
    try:
        raw = Path(path).read_text(encoding="utf-8-sig")
    except OSError:
        return []
    out = []
    for m in _SRT_TIME.finditer(raw):
        g = [int(x) for x in m.groups()]
        s = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
        e = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
        if e > s:
            out.append((s, e))
    return out


def tim_srt(video) -> Path | None:
    """SRT nhận diện giọng nói của bước ① nằm cạnh video: <tên>.srt (tiếng gốc),
    không có thì <tên>_vi.srt (bản dịch — cùng mốc giờ). KHÔNG lấy _vi_sapxep.srt:
    bản đó đã xếp lại theo giọng đọc TTS, không còn khớp lúc hardsub hiện."""
    v = Path(video)
    for hau in (".srt", "_vi.srt"):
        p = v.with_name(v.stem + hau)
        if p.is_file():
            return p
    return None


def moc_giong_noi(srt, so_khung: int, dur: float, rnd: random.Random | None = None,
                  kiem_tra=None, so_thu: int = SO_THU) -> list[float]:
    """Chọn `so_khung` mốc giây NGẪU NHIÊN nhưng CÁCH NHAU ĐỀU trong phần video
    có giọng nói: nối các câu của SRT thành một "dòng thời gian giọng nói" (bỏ
    câu quá ngắn, cắt 15% đầu/cuối mỗi câu), chia dòng đó thành `so_khung` phần
    bằng nhau, mỗi phần bốc một điểm ngẫu nhiên rồi đổi ngược về giây thật.

    `kiem_tra(t) -> bool` (tuỳ chọn): khung tại t có chữ không — không thì bốc
    lại mốc khác TRONG CÙNG PHẦN, tối đa `so_thu` lần; phần nào bốc mãi không
    ra khung có chữ thì bỏ (ít khung hơn còn hơn thêm khung không có sub).
    → [] nếu SRT rỗng / không câu nào đủ dài / không phần nào có khung có chữ."""
    cau = []
    for s, e in _doc_srt(srt):
        if e - s < CAU_TOI_THIEU or s >= dur:
            continue
        mep = max(0.15, (e - s) * CAT_MEP_CAU)
        a, b = s + mep, min(e, dur) - mep
        if b - a > 0.05:
            cau.append((a, b))
    tong = sum(b - a for a, b in cau)
    if not cau or tong <= 0 or so_khung <= 0:
        return []
    rnd = rnd or random.Random()
    buoc = tong / so_khung

    def giay_that(u: float) -> float:
        acc = 0.0
        for a, b in cau:
            if u < acc + (b - a):
                return round(a + (u - acc), 2)
            acc += b - a
        return round(cau[-1][1], 2)

    mocs = []
    for k in range(so_khung):
        for _ in range(so_thu if kiem_tra else 1):
            t = giay_that((k + rnd.uniform(0.05, 0.95)) * buoc)
            if t in mocs:
                continue
            if kiem_tra is None or kiem_tra(t):
                mocs.append(t)
                break
    return mocs


def _bo_khung(video, w: int, h: int):
    """(lay, h_nho): lay(t) → khung xám thu nhỏ tại giây t, nhớ lại — khung đã
    lấy để KIỂM có chữ thì dò luôn trên khung đó, khỏi đọc video hai lần."""
    h_nho = max(2, round(h * SCALE_W / w / 2) * 2)
    khung: dict[float, np.ndarray | None] = {}

    def lay(t: float):
        if t not in khung:
            khung[t] = _khung_xam(video, float(t), SCALE_W, h_nho)
        return khung[t]

    return lay, khung, h_nho


def moc_xem_thu(video, so_khung: int = SO_KHUNG) -> list[float]:
    """Mốc khung để TRANG WEB soi: mốc đã dò (trong cache) → bốc lúc có giọng nói
    + kiểm có chữ (seed cố định theo cỡ file, tải lại trang vẫn ra cùng bộ;
    ~1-2 giây) → [] (không có SRT)."""
    video = Path(video)
    try:
        d = json.loads(_cache_path(video).read_text(encoding="utf-8"))
        mocs = [float(t) for t in d.get("moc_giay", [])]
        if mocs:
            return mocs
    except (OSError, ValueError, TypeError):
        pass
    srt = tim_srt(video)
    if not srt:
        return []
    try:
        w, h, dur = _probe(video)
    except Exception:
        return []
    lay, _khung, _h = _bo_khung(video, w, h)
    return moc_giong_noi(srt, so_khung, dur, random.Random(video.stat().st_size),
                         kiem_tra=lambda t: _co_chu(lay(t)))


def _mmss(t: float) -> str:
    t = int(t)
    return f"{t // 60}:{t % 60:02d}"


# ── Khoảng thời gian CÓ TIẾNG GỐC → chỉ che mờ trong các khoảng đó ──────────
KHE_KHONG_CHE = 1.0    # khe không có tiếng gốc dài hơn (giây) thì KHÔNG che — cảnh
                       # võ thuật / không thoại thường không có hardsub
DEM_CHE = 0.4          # đệm mỗi khoảng có tiếng thêm (giây) hai đầu — hardsub hiện
                       # sớm / tắt muộn hơn tiếng vài trăm ms
NHAY_MIN = 0.5         # khoảng KHÔNG che ngắn hơn (giây) thì che luôn — dải mờ tắt
                       # rồi bật lại trong nửa giây nhìn như nháy


def khoang_co_tieng(srt, dur: float, khe: float = KHE_KHONG_CHE, dem: float = DEM_CHE,
                    nhay_min: float = NHAY_MIN) -> list[tuple[float, float]]:
    """Các khoảng [a, b] (giây) cần CHE MỜ theo SRT giọng nói bước ①: câu nối câu
    cách nhau <= `khe` gộp thành một khoảng (khe dài hơn là không thoại → không
    che), mỗi khoảng đệm `dem` hai đầu, rồi khoảng hở còn ngắn hơn `nhay_min`
    thì nối luôn kẻo dải mờ nháy. [] nếu SRT không có câu nào."""
    cau = sorted(_doc_srt(srt))
    if not cau:
        return []
    khoang: list[list[float]] = []
    for s, e in cau:
        if khoang and s - khoang[-1][1] <= khe:
            khoang[-1][1] = max(khoang[-1][1], e)
        else:
            khoang.append([s, e])
    khoang = [[max(0.0, s - dem), min(dur, e + dem) if dur > 0 else e + dem]
              for s, e in khoang]
    ra: list[list[float]] = []
    for s, e in khoang:
        if ra and s - ra[-1][1] < nhay_min:
            ra[-1][1] = max(ra[-1][1], e)
        else:
            ra.append([s, e])
    return [(round(s, 2), round(e, 2)) for s, e in ra if e > s]


def bieu_thuc_enable(khoang) -> str:
    """Biểu thức `enable` của ffmpeg cho các khoảng [a, b]: between(t,a,b)+…"""
    return "+".join(f"between(t,{a:g},{b:g})" for a, b in khoang)


# ── Dò dải ───────────────────────────────────────────────────────────────────
def tim_vung(video, so_khung: int | None = None, dung_cache: bool = True,
             srt=None, seed: int | None = None) -> dict | None:
    """Dò dải sub → {"y0", "y1", "w", "h", "moc_giay", …} theo PIXEL GỐC của
    video, None nếu không thấy dải nào (video không có hardsub).

    `srt`: SRT giọng nói để chọn khung (mặc định tự tìm cạnh video, xem tim_srt).
    `so_khung`: mặc định SO_KHUNG (5) khi có SRT, SO_KHUNG_RAI (10) khi rải đều.
    `seed`: cố định bộ khung ngẫu nhiên (None = mỗi lần một bộ)."""
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
    lay, khung, h_nho = _bo_khung(video, w, h)   # khung đã lấy — kiểm xong dò luôn

    # Chọn mốc khung: lúc có giọng nói (SRT bước ①, kiểm từng khung có chữ) →
    # rải đều cả video.
    srt = Path(srt) if srt else tim_srt(video)
    mocs: list[float] = []
    nguon = "rai_deu"
    if srt and srt.is_file():
        mocs = moc_giong_noi(srt, so_khung or SO_KHUNG, dur, random.Random(seed),
                             kiem_tra=lambda t: _co_chu(lay(t)))
        if mocs:
            nguon = "giong_noi"
            print(f"🗣 Lấy {len(mocs)} khung có chữ lúc có giọng nói (theo {srt.name}, "
                  f"soi {len(khung)} khung): " + ", ".join(_mmss(t) for t in mocs))
        else:
            print(f"⚠️ {srt.name}: không bốc được khung nào có chữ lúc có giọng nói "
                  f"(soi {len(khung)} khung) — rải đều khung như cũ.")
    if not mocs:
        n = so_khung or SO_KHUNG_RAI
        mocs = [round(float(t), 2) for t in np.linspace(0.05 * dur, 0.95 * dur, n)]
        print(f"📐 Rải đều {n} khung cả video: " + ", ".join(_mmss(t) for t in mocs))

    diem = np.zeros(h_nho, dtype=np.int32)      # tổng điểm-chữ từng hàng (mọi khung)
    co_chu = np.zeros(h_nho, dtype=np.int32)    # số khung mà hàng này có chữ
    for t in mocs:
        g = lay(t)
        if g is None:
            continue
        hang = _hang_chu(g)
        diem += hang
        co_chu += hang > SCALE_W * TI_LE_HANG

    runs = _runs(co_chu >= KHUNG_CO_SUB, h_nho)
    if not runs:
        return None

    # Chọn run: khung lấy lúc có giọng nói đã KIỂM có chữ nên dải sub phải có mặt
    # ở (gần) mọi khung, còn chữ cảnh/tiêu đề chỉ lọt 1–2 khung → ưu tiên run
    # có số khung cao nhất, hoà thì tổng điểm. Rải đều thì sub chỉ có ở một phần
    # khung (im lặng không có chữ) nên theo tổng điểm như cũ.
    if nguon == "giong_noi":
        y0s, y1s = max(runs, key=lambda r: (int(co_chu[r[0]:r[1] + 1].max()),
                                            int(diem[r[0]:r[1] + 1].sum())))
    else:
        y0s, y1s = max(runs, key=lambda r: int(diem[r[0]:r[1] + 1].sum()))

    dem = max(1, int(DEM_DOC * h_nho))
    y0 = max(0, int((y0s - dem) * h / h_nho))
    y1 = min(h, int((y1s + 1 + dem) * h / h_nho))
    vung = {"y0": y0, "y1": y1, "w": w, "h": h,
            "so_khung": len(mocs), "nguon_moc": nguon, "moc_giay": mocs,
            "srt": srt.name if (srt and nguon == "giong_noi") else "",
            "ghi_chu": "sửa y0/y1 nếu dò lệch; xoá file để dò lại"}
    if dung_cache:
        try:
            cache.write_text(json.dumps(vung, ensure_ascii=False, indent=2),
                             encoding="utf-8")
        except OSError:
            pass
    print(f"🔎 Dải sub Trung: y {y0}–{y1} / cao {h}px "
          f"(dày {y1 - y0}px, dò {len(mocs)} khung hình"
          + (" lúc có giọng nói)" if nguon == "giong_noi" else " rải đều)"))
    return vung


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(
        description="Dò dải sub Trung đốt trong hình (chỉ in kết quả, không ghi cache).")
    ap.add_argument("video")
    ap.add_argument("--so-khung", type=int, default=None,
                    help=f"số khung hình (mặc định {SO_KHUNG} khi có SRT giọng nói, "
                         f"{SO_KHUNG_RAI} khi rải đều)")
    ap.add_argument("--srt", default="",
                    help="SRT giọng nói để chọn khung (mặc định: <video>.srt cạnh video)")
    ap.add_argument("--seed", type=int, default=None, help="cố định bộ khung ngẫu nhiên")
    ap.add_argument("--luu", action="store_true", help="ghi kết quả vào <video>_vungsub.json")
    a = ap.parse_args()
    v = tim_vung(a.video, so_khung=a.so_khung, dung_cache=a.luu,
                 srt=a.srt or None, seed=a.seed)
    print(v if v else "Không thấy dải sub nào ở nửa dưới khung hình.")


if __name__ == "__main__":
    main()
