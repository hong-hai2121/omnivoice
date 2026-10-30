# -*- coding: utf-8 -*-
"""CHỐT CANH RAM cho tiến trình con (28/10/2026) — ffmpeg ngốn RAM bất thường thì GIẾT
ngay, chụp bằng chứng ai đang ăn RAM/VRAM, để máy không treo tới mức phải khởi động lại.

VÌ SAO: đêm 27/10/2026 (tập 152) ffmpeg NVENC ngốn 52 GB bộ nhớ ảo trong ~28 phút
(Event Viewer System 2004 lúc 21:09; Windows đã báo RADAR_PRE_LEAK ffmpeg.exe từ 20:46),
cả máy ì ạch tới khi user khởi động lại. Dựng lại cùng clip ngay sau thì bình thường
(đỉnh ~1,9 GB), thử nghiệm kho lẫn clip dọc 1080×1920 cũng chỉ 1,86 GB → không phải tại
clip; là sự cố ngẫu nhiên theo điều kiện lúc đó (python TTS giữ 6 GB + CapCut 3,4 GB
chạy nền trên card 8 GB dùng chung). Không tái hiện được thì phải có lưới an toàn:
ffmpeg vượt NGUONG_GB → giết → ghi bằng chứng → video_khung thử lại 1 lần → vẫn vượt
thì ném RamLoi (gpu_batbuoc) cho hàng đợi coi tập CHƯA xong.

Dùng:
    canh = CanhGac(proc.pid, log=log); canh.start(); ...; canh.stop()
    canh.vuot (bị giết?), canh.dinh_gb (đỉnh RAM), canh.bang_chung (ảnh chụp lúc giết)
    kiem_truoc(log)   → 1 dòng RAM/VRAM trước khi dựng, cảnh báo nếu RAM trống thấp
    python ram_canhgac.py   → in ngay ai đang ăn RAM/VRAM (xem bằng mắt, không giết gì)

Ngưỡng đo được: dựng 1080p NVENC bình thường đỉnh ~1,8–1,9 GB; chốt 8 GB (OMNI_FFMPEG_RAM_GB
để đổi) = gấp 4 mức bình thường, vẫn xa mức 32 GB RAM của máy nên máy không kịp ì.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time

try:
    import psutil
except ImportError:          # không có psutil → chốt thành không làm gì (chỉ cảnh báo 1 lần)
    psutil = None

TAG = "[RAM]"                # đầu thông báo lỗi → dung_neu_nvenc_loi nhận ra là lỗi RAM
NGUONG_GB = float(os.environ.get("OMNI_FFMPEG_RAM_GB", "8"))   # ffmpeg vượt → giết
RAM_TRONG_CANH_BAO_GB = 3.0  # RAM trống dưới mức này trước khi dựng → cảnh báo + kể tên
CHU_KY_S = 1.0               # chu kỳ đo
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def _gb(n_bytes: float) -> float:
    return n_bytes / 2**30


def _commit_bytes(p) -> int:
    """Bộ nhớ ảo riêng (commit) — đúng con số Windows ghi trong sự kiện 2004.
    Hệ khác không có `private` thì lấy rss."""
    mi = p.memory_info()
    return int(getattr(mi, "private", None) or mi.rss)


def _commit_cay(p) -> int:
    """Tổng commit của tiến trình + MỌI tiến trình con. ffmpeg không có con, nhưng python.exe
    của venv (bản Store) chỉ là launcher sinh python thật làm con — đo một mình PID gốc
    thì thấy vài chục MB trong khi con ăn hàng GB; cộng cả cây cho chắc."""
    tong = _commit_bytes(p)
    for c in p.children(recursive=True):
        try:
            tong += _commit_bytes(c)
        except (psutil.Error, OSError):
            pass
    return tong


def ram_gb() -> tuple[float, float]:
    """(RAM trống, RAM tổng) GB; không có psutil → (0, 0)."""
    if psutil is None:
        return 0.0, 0.0
    vm = psutil.virtual_memory()
    return _gb(vm.available), _gb(vm.total)


def vram_mib() -> tuple[int, int] | None:
    """(VRAM đang dùng, VRAM tổng) MiB qua nvidia-smi; không có/không chạy được → None."""
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, creationflags=_CREATE_NO_WINDOW)
        used, total = (r.stdout or "").strip().splitlines()[0].split(",")
        return int(used), int(total)
    except Exception:
        return None


def top_tien_trinh(n: int = 6) -> list[tuple[str, int, float]]:
    """n tiến trình ăn nhiều bộ nhớ ảo riêng nhất: [(tên, pid, GB), ...] giảm dần."""
    if psutil is None:
        return []
    rows = []
    for p in psutil.process_iter(["pid", "name"]):
        try:
            rows.append((p.info["name"] or "?", p.info["pid"], _gb(_commit_bytes(p))))
        except (psutil.Error, OSError):
            continue
    rows.sort(key=lambda r: r[2], reverse=True)
    return rows[:n]


def bang_chung(n: int = 6) -> str:
    """Ảnh chụp 2 dòng: RAM/VRAM + ai đang ăn nhiều nhất — để ghi log/file khi có sự cố."""
    trong, tong = ram_gb()
    dong1 = f"RAM trống {trong:.1f}/{tong:.1f} GB"
    if psutil is not None:
        sw = psutil.swap_memory()
        if sw.total:
            dong1 += f" · pagefile dùng {_gb(sw.used):.1f}/{_gb(sw.total):.1f} GB"
    v = vram_mib()
    if v:
        dong1 += f" · VRAM {v[0]}/{v[1]} MiB"
    top = " · ".join(f"{ten}({pid}) {gb:.1f} GB" for ten, pid, gb in top_tien_trinh(n))
    return dong1 + "\nĂn RAM nhiều nhất: " + (top or "(không đọc được)")


def kiem_truoc(log=print) -> None:
    """Một dòng tình trạng RAM/VRAM trước khi chạy ffmpeg; RAM trống thấp thì kể tên thủ phạm.
    Chỉ báo, KHÔNG dừng: thiếu RAM do app khác là việc của người dùng (đóng app)."""
    trong, tong = ram_gb()
    v = vram_mib()
    vram = f" · VRAM {v[0]}/{v[1]} MiB" if v else ""
    log(f"🧠 RAM trống {trong:.1f}/{tong:.1f} GB{vram} · chốt canh ffmpeg: quá {NGUONG_GB:g} GB thì dừng")
    if tong and trong < RAM_TRONG_CANH_BAO_GB:
        top = " · ".join(f"{ten} {gb:.1f} GB" for ten, _pid, gb in top_tien_trinh(4))
        log(f"⚠️ RAM trống chỉ còn {trong:.1f} GB — đang ăn nhiều nhất: {top}. "
            "Nên đóng bớt app (Chrome/CapCut) trước khi dựng tiếp.")


class CanhGac:
    """Luồng nền đo bộ nhớ ảo riêng của tiến trình `pid` mỗi CHU_KY_S; vượt ngưỡng thì
    chụp bằng chứng rồi giết cả cây tiến trình. Sau đó bên gọi xem `vuot` để biết.
    Không có psutil → không canh (vuot luôn False)."""

    def __init__(self, pid: int, nguong_gb: float | None = None, chu_ky: float | None = None,
                 log=None):
        self.pid = pid
        self.nguong_gb = NGUONG_GB if nguong_gb is None else float(nguong_gb)
        self.chu_ky = CHU_KY_S if chu_ky is None else float(chu_ky)
        self.log = log
        self.dinh_gb = 0.0
        self.vuot = False
        self.bang_chung = ""
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> "CanhGac":
        if psutil is None:
            if self.log:
                self.log("⚠️ Không có psutil → không canh được RAM của ffmpeg (pip install psutil).")
            return self
        self._thread = threading.Thread(target=self._chay, name="ram_canhgac", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.chu_ky + 2)

    def __enter__(self) -> "CanhGac":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()

    def _chay(self) -> None:
        try:
            p = psutil.Process(self.pid)
        except psutil.Error:
            return
        while not self._stop.is_set():
            try:
                gb = _gb(_commit_cay(p))
            except (psutil.Error, OSError):
                return                         # tiến trình đã kết thúc
            if gb > self.dinh_gb:
                self.dinh_gb = gb
            if gb > self.nguong_gb:
                self.vuot = True
                self.bang_chung = bang_chung()
                self._giet(p)
                return
            self._stop.wait(self.chu_ky)

    @staticmethod
    def _giet(p) -> None:
        try:
            for c in p.children(recursive=True):
                try:
                    c.kill()
                except psutil.Error:
                    pass
            p.kill()
        except psutil.Error:
            pass


if __name__ == "__main__":
    try:                      # console cp1252 không in được tiếng Việt → ép UTF-8 tại chỗ
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    print(bang_chung(10))
