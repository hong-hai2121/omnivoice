# -*- coding: utf-8 -*-
"""
nen_win.py — Bộ đồ nghề điều khiển cửa sổ NGẦM trên Windows.

"Ngầm" ở đây nghĩa là: nhìn và bấm được vào một cửa sổ mà KHÔNG đụng tới con trỏ
chuột lẫn bàn phím của người đang ngồi máy. Người dùng vẫn gõ Word, vẫn lướt web
bình thường trong lúc bot làm việc ở cửa sổ khác.

Cách làm, và vì sao chọn cách đó (đã đo thực tế trên máy này —
xem thu_khong_chiem_chuot.py và ảnh trong anh_thu/):

  NHÌN  PrintWindow(PW_RENDERFULLCONTENT) chụp thẳng nội dung một cửa sổ, kể cả
        khi nó bị cửa sổ khác che. Hơn hẳn chụp màn hình (MSS/ImageGrab) vì không
        phải lôi cửa sổ lên trên cùng, tức không giành màn hình với người dùng.

  BẤM   PostMessage WM_LBUTTONDOWN/UP gửi vào đúng cửa sổ con nhận tin nhắn.
        Đã đo: Chromium NHẬN, báo isTrusted=true, và DÙNG ĐÚNG toạ độ gửi kèm
        (sai số 0.2 điểm ảnh trên quãng 311 CSS). Con trỏ thật không nhúc nhích.
        Khác hẳn PyAutoGUI/SendInput — thứ đó cướp con trỏ vật lý.

  GÕ    WM_CHAR đi theo MÃ UNICODE, không theo mã phím vật lý, nên gõ được
        'kịch_bản N118 - 女主九族' nguyên vẹn. Đã đo. Riêng ô nhập Win32 thuần
        (như hộp thoại mở file) thì dùng WM_SETTEXT đặt cả chuỗi một nhát, vừa
        nhanh vừa không sợ rơi ký tự.

Đơn vị toạ độ — chỗ dễ sai nhất, đọc kỹ:
  • Ảnh chụp ra là ĐIỂM ẢNH VẬT LÝ của cả cửa sổ, gốc (0,0) ở góc trên trái cửa sổ.
  • Trang web bên trong tính bằng CSS pixel, và còn lùi xuống dưới thanh tab.
  • Cầu nối: điểm trong ảnh → cộng gốc cửa sổ ra toạ độ màn hình → ScreenToClient
    của cửa sổ đích. Hàm bam_ngam_theo_anh() làm sẵn cả chuỗi này.
"""

import ctypes
import time
from ctypes import wintypes

import numpy as np
from PIL import Image

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
user32.SetProcessDPIAware()

WM_SETTEXT = 0x000C
WM_GETTEXT = 0x000D
WM_GETTEXTLENGTH = 0x000E
WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP = 0x0200, 0x0201, 0x0202
WM_KEYDOWN, WM_KEYUP, WM_CHAR = 0x0100, 0x0101, 0x0102
MK_LBUTTON = 0x0001
VK_RETURN, VK_TAB, VK_ESCAPE, VK_BACK, VK_DELETE = 0x0D, 0x09, 0x1B, 0x08, 0x2E
VK_CONTROL, VK_A, VK_END, VK_HOME = 0x11, 0x41, 0x23, 0x24
LOP_HOP_THOAI = "#32770"          # lớp cửa sổ của mọi hộp thoại Open/Save Windows

for _f, _res, _arg in (
    (user32.GetWindowDC, wintypes.HDC, [wintypes.HWND]),
    (gdi32.CreateCompatibleDC, wintypes.HDC, [wintypes.HDC]),
    (gdi32.CreateCompatibleBitmap, wintypes.HBITMAP,
     [wintypes.HDC, ctypes.c_int, ctypes.c_int]),
    (gdi32.SelectObject, wintypes.HGDIOBJ, [wintypes.HDC, wintypes.HGDIOBJ]),
    (gdi32.DeleteObject, wintypes.BOOL, [wintypes.HGDIOBJ]),
    (gdi32.DeleteDC, wintypes.BOOL, [wintypes.HDC]),
    (user32.ReleaseDC, ctypes.c_int, [wintypes.HWND, wintypes.HDC]),
    (user32.PrintWindow, wintypes.BOOL, [wintypes.HWND, wintypes.HDC, wintypes.UINT]),
):
    _f.restype, _f.argtypes = _res, _arg


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT,
                            wintypes.UINT, ctypes.c_void_p,
                            ctypes.POINTER(BITMAPINFO), wintypes.UINT]

_ENUM = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


# ─────────────────────────────── tìm cửa sổ ─────────────────────────────────
def tieu_de(hwnd: int) -> str:
    n = user32.GetWindowTextLengthW(hwnd)
    b = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, b, n + 1)
    return b.value


def lop_cua_so(hwnd: int) -> str:
    b = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, b, 256)
    return b.value


def moi_cua_so_hien() -> list[int]:
    """Mọi cửa sổ gốc đang hiện, theo thứ tự trên → dưới (Z-order)."""
    ra: list[int] = []

    def _moi(h, _):
        if user32.IsWindowVisible(h):
            ra.append(h)
        return True

    user32.EnumWindows(_ENUM(_moi), 0)
    return ra


def tim_cua_so(lop: str = "", chua_tieu_de: str = "") -> list[int]:
    return [h for h in moi_cua_so_hien()
            if (not lop or lop_cua_so(h) == lop)
            and (not chua_tieu_de or chua_tieu_de in tieu_de(h))]


def cac_con(hwnd: int) -> list[tuple[int, str, str]]:
    """Mọi cửa sổ con (đệ quy 1 tầng): (hwnd, lớp, tiêu đề)."""
    ra: list[tuple[int, str, str]] = []

    def _moi(h, _):
        ra.append((h, lop_cua_so(h), tieu_de(h)))
        return True

    user32.EnumChildWindows(hwnd, _ENUM(_moi), 0)
    return ra


def con_theo_lop(hwnd: int, lop_chua: str) -> list[int]:
    return [h for h, lop, _ in cac_con(hwnd) if lop_chua.lower() in lop.lower()]


def cua_so_nhan_chuot(hwnd_chrome: int) -> int:
    """Cửa sổ con của Chrome thật sự nhận tin nhắn chuột/bàn phím.

    Chromium dựng 'Chrome_RenderWidgetHostHWND' làm cửa sổ cầu nối cho tin nhắn
    Win32; gửi vào cửa sổ cha thì trôi đi mất."""
    con = con_theo_lop(hwnd_chrome, "RenderWidget")
    return con[0] if con else hwnd_chrome


def khung(hwnd: int) -> tuple[int, int, int, int]:
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def man_sang_khach(hwnd: int, x: int, y: int) -> tuple[int, int]:
    p = wintypes.POINT(x, y)
    user32.ScreenToClient(hwnd, ctypes.byref(p))
    return p.x, p.y


def vi_tri_chuot() -> tuple[int, int]:
    p = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


# ──────────────────────────────── chụp ngầm ─────────────────────────────────
def chup_ngam(hwnd: int) -> tuple[Image.Image | None, tuple[int, int], bool]:
    """→ (ảnh cửa sổ, gốc cửa sổ trên màn hình, PrintWindow có báo thành công).

    Ảnh trả về là điểm ảnh VẬT LÝ, gốc (0,0) ở góc trên trái CỬA SỔ (không phải
    góc màn hình, cũng không phải góc vùng web)."""
    l, t, r, b = khung(hwnd)
    w, h = r - l, b - t
    if w <= 0 or h <= 0:
        return None, (l, t), False
    hdc_win = user32.GetWindowDC(hwnd)
    hdc_mem = gdi32.CreateCompatibleDC(hdc_win)
    hbmp = gdi32.CreateCompatibleBitmap(hdc_win, w, h)
    cu = gdi32.SelectObject(hdc_mem, hbmp)
    ok = bool(user32.PrintWindow(hwnd, hdc_mem, 2))   # 2 = PW_RENDERFULLCONTENT

    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth, bmi.bmiHeader.biHeight = w, -h   # âm = ảnh xuôi
    bmi.bmiHeader.biPlanes, bmi.bmiHeader.biBitCount = 1, 32
    bmi.bmiHeader.biCompression = 0
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(hdc_mem, hbmp, 0, h, buf, ctypes.byref(bmi), 0)

    gdi32.SelectObject(hdc_mem, cu)
    gdi32.DeleteObject(hbmp)
    gdi32.DeleteDC(hdc_mem)
    user32.ReleaseDC(hwnd, hdc_win)
    return Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1), (l, t), ok


# ───────────────────────── nhận diện khối màu (nút) ─────────────────────────
def mat_na_mau(img: Image.Image, rgb: tuple[int, int, int],
               dung_sai: int = 30) -> np.ndarray:
    a = np.asarray(img, dtype=np.int16)
    return (np.abs(a[:, :, 0] - rgb[0]) <= dung_sai) & \
           (np.abs(a[:, :, 1] - rgb[1]) <= dung_sai) & \
           (np.abs(a[:, :, 2] - rgb[2]) <= dung_sai)


def cac_khoi(mat_na: np.ndarray, it_nhat: int = 400) -> list[dict]:
    """Tách mặt nạ thành các KHỐI LIỀN NHAU, lớn → nhỏ.

    Phải tách khối chứ không lấy trọng tâm cả mặt nạ: trang TikTok có nhiều chỗ
    cùng màu đỏ (nút 'Tải lên' ở cột trái, nút 'Chọn video' giữa trang, chấm đỏ
    báo tính năng mới). Lấy trọng tâm chung sẽ rơi vào khoảng trống giữa chúng.

    Gộp khối bằng cách mã hoá từng dòng thành các ĐOẠN CHẠY rồi hợp nhất đoạn
    chồng nhau giữa hai dòng kề (union-find) — đủ nhanh cho ảnh 2600x1000 mà
    không cần OpenCV."""
    cao, rong = mat_na.shape
    cha: dict[int, int] = {}

    def tim(x):
        while cha[x] != x:
            cha[x] = cha[cha[x]]
            x = cha[x]
        return x

    def hop(a, b):
        ra, rb = tim(a), tim(b)
        if ra != rb:
            cha[rb] = ra

    doan: list[tuple[int, int, int, int]] = []        # (id, dòng, x0, x1)
    dong_truoc: list[tuple[int, int, int]] = []       # (id, x0, x1)
    for y in range(cao):
        hang = mat_na[y]
        if not hang.any():
            dong_truoc = []
            continue
        d = np.diff(hang.astype(np.int8))
        bat_dau = list(np.flatnonzero(d == 1) + 1)
        ket_thuc = list(np.flatnonzero(d == -1))
        if hang[0]:
            bat_dau.insert(0, 0)
        if hang[-1]:
            ket_thuc.append(rong - 1)

        dong_nay = []
        for x0, x1 in zip(bat_dau, ket_thuc):
            i = len(doan)
            cha[i] = i
            doan.append((i, y, x0, x1))
            for j, px0, px1 in dong_truoc:
                if x0 <= px1 and px0 <= x1:
                    hop(j, i)
            dong_nay.append((i, x0, x1))
        dong_truoc = dong_nay

    gom: dict[int, dict] = {}
    for i, y, x0, x1 in doan:
        g = gom.setdefault(tim(i), {"so": 0, "sx": 0, "sy": 0,
                                    "x0": rong, "x1": 0, "y0": cao, "y1": 0})
        n = x1 - x0 + 1
        g["so"] += n
        g["sx"] += (x0 + x1) * n / 2
        g["sy"] += y * n
        g["x0"], g["x1"] = min(g["x0"], x0), max(g["x1"], x1)
        g["y0"], g["y1"] = min(g["y0"], y), max(g["y1"], y)

    ra = []
    for g in gom.values():
        if g["so"] < it_nhat:
            continue
        ra.append({"so": g["so"],
                   "cx": int(g["sx"] / g["so"]), "cy": int(g["sy"] / g["so"]),
                   "x0": g["x0"], "x1": g["x1"], "y0": g["y0"], "y1": g["y1"],
                   "rong": g["x1"] - g["x0"] + 1, "cao": g["y1"] - g["y0"] + 1})
    return sorted(ra, key=lambda k: -k["so"])


def tim_nut_mau(img: Image.Image, rgb: tuple[int, int, int], dung_sai: int = 30,
                it_nhat: int = 400, vung: tuple[int, int, int, int] | None = None
                ) -> list[dict]:
    """Các nút cùng một màu trong ảnh, lớn → nhỏ. `vung`=(x0,y0,x1,y1) để bó hẹp."""
    mn = mat_na_mau(img, rgb, dung_sai)
    if vung:
        x0, y0, x1, y1 = vung
        che = np.zeros_like(mn)
        che[y0:y1, x0:x1] = True
        mn = mn & che
    return cac_khoi(mn, it_nhat)


# ────────────────────────────── bấm / gõ ngầm ───────────────────────────────
def bam_ngam(hwnd: int, cx: int, cy: int, nghi: float = 0.06) -> None:
    """Bấm chuột trái tại toạ độ KHÁCH của `hwnd`. Con trỏ thật không di chuyển."""
    lp = ((cy & 0xFFFF) << 16) | (cx & 0xFFFF)
    user32.PostMessageW(hwnd, WM_MOUSEMOVE, 0, lp)
    time.sleep(0.03)
    user32.PostMessageW(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lp)
    time.sleep(nghi)
    user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, lp)


def bam_ngam_theo_anh(hwnd_dich: int, goc_cua_so: tuple[int, int],
                      x_anh: int, y_anh: int) -> tuple[int, int]:
    """Bấm vào điểm (x_anh, y_anh) ĐỌC TỪ ẢNH CHỤP của cửa sổ.

    Đây là hàm nên dùng: nó lo hết khâu đổi đơn vị mà chỗ đó hay sai —
    điểm trong ảnh → toạ độ màn hình → toạ độ khách của cửa sổ đích."""
    sx, sy = goc_cua_so[0] + x_anh, goc_cua_so[1] + y_anh
    cx, cy = man_sang_khach(hwnd_dich, sx, sy)
    bam_ngam(hwnd_dich, cx, cy)
    return cx, cy


def go_ngam(hwnd: int, chu: str, nghi: float = 0.02) -> None:
    """Gõ từng ký tự bằng WM_CHAR — đi theo mã Unicode nên có dấu và chữ Hán."""
    for c in chu:
        user32.PostMessageW(hwnd, WM_CHAR, ord(c), 1)
        time.sleep(nghi)


def phim_ngam(hwnd: int, vk: int, nghi: float = 0.05) -> None:
    user32.PostMessageW(hwnd, WM_KEYDOWN, vk, 1)
    time.sleep(nghi)
    user32.PostMessageW(hwnd, WM_KEYUP, vk, 1)


def dat_chu(hwnd_o_nhap: int, chu: str) -> bool:
    """Đặt NGUYÊN chuỗi vào một ô nhập Win32 bằng WM_SETTEXT.

    Dùng cho hộp thoại mở file: đặt một nhát cả đường dẫn, không gõ từng phím
    nên không rơi ký tự, không bị danh sách gợi ý nhảy vào phá."""
    return bool(user32.SendMessageW(hwnd_o_nhap, WM_SETTEXT, 0,
                                    ctypes.c_wchar_p(chu)))


def doc_chu(hwnd_o_nhap: int) -> str:
    n = user32.SendMessageW(hwnd_o_nhap, WM_GETTEXTLENGTH, 0, 0)
    b = ctypes.create_unicode_buffer(n + 1)
    user32.SendMessageW(hwnd_o_nhap, WM_GETTEXT, n + 1, ctypes.byref(b))
    return b.value


# ─────────────────────── hộp thoại mở file của Windows ──────────────────────
def cho_hop_thoai(giay: float = 15.0, tru: set[int] | None = None) -> int | None:
    """Chờ một hộp thoại (#32770) hiện ra; `tru` là những cái đã có từ trước."""
    tru = tru or set()
    han = time.time() + giay
    while time.time() < han:
        for h in tim_cua_so(LOP_HOP_THOAI):
            if h not in tru:
                return h
        time.sleep(0.3)
    return None


def hop_thoai_dang_mo() -> set[int]:
    return set(tim_cua_so(LOP_HOP_THOAI))


def dien_hop_thoai_mo_file(hwnd_hop: int, duong_dan: str,
                           log=print) -> bool:
    """Đưa đường dẫn vào hộp thoại 'Open' rồi xác nhận — không gõ, không bấm chuột.

    Ô tên file của hộp thoại Windows là một Edit nằm trong ComboBoxEx32. Đặt chữ
    bằng WM_SETTEXT rồi gửi Enter vào chính ô đó: đường dẫn dài, có dấu tiếng
    Việt và chữ Hán đều vào trọn vẹn."""
    o_nhap = None
    for h, lop, _ in cac_con(hwnd_hop):
        if lop == "Edit":
            o_nhap = h
            break
        if lop in ("ComboBoxEx32", "ComboBox"):
            trong = con_theo_lop(h, "Edit")
            if trong:
                o_nhap = trong[0]
                break
    if not o_nhap:
        log("  ❌ Không tìm thấy ô tên file trong hộp thoại.")
        return False

    if not dat_chu(o_nhap, duong_dan):
        log("  ❌ WM_SETTEXT không đặt được chữ vào ô tên file.")
        return False
    time.sleep(0.4)
    lai = doc_chu(o_nhap)
    log(f"  Ô tên file đang giữ: {lai!r}")
    if lai != duong_dan:
        log("  ⚠ Chuỗi đọc lại KHÁC chuỗi đặt vào.")
    phim_ngam(o_nhap, VK_RETURN)
    return True
