# -*- coding: utf-8 -*-
"""
thu_khong_chiem_chuot.py — Thử phương án NHÌN MÀN HÌNH mà KHÔNG cướp chuột.

Yêu cầu đặt ra: không dùng DOM/CDP, không phải đóng Chrome, và tuyệt đối không
chiếm con trỏ chuột của người đang ngồi máy. Ba thứ đó ép bỏ PyAutoGUI (nó gọi
SendInput — điều khiển đúng con trỏ vật lý). Còn lại hai đường, bài thử này đo
xem Chrome có chịu hay không:

  ĐO 1 — CHỤP NGẦM:  PrintWindow(PW_RENDERFULLCONTENT) chụp thẳng cửa sổ Chrome,
          kể cả khi nó KHÔNG ở trên cùng. Nếu được thì khỏi cần MSS, và bot không
          phải giành màn hình với bạn. (MSS chỉ chụp được cái đang hiện.)

  ĐO 2 — BẤM NGẦM:   PostMessage WM_LBUTTONDOWN/UP gửi thẳng vào cửa sổ Chrome.
          Con trỏ chuột KHÔNG hề di chuyển. Câu hỏi: Chromium có nhận không?
          Nhiều ứng dụng nhận, nhưng Chromium lọc khá gắt — phải thử mới biết.

  ĐO 3 — GÕ NGẦM:    PostMessage WM_CHAR từng ký tự Unicode. Đây là chỗ quyết
          định số phận tên thư mục "kịch_bản\\N118 - _女主九族…": WM_CHAR đi bằng
          mã Unicode chứ không bằng mã phím vật lý, nên về lý là gõ được cả chữ
          Hán lẫn dấu tiếng Việt — thứ PyAutoGUI chịu chết.

Cách đọc kết quả: trang thử tự ghi tình trạng vào TIÊU ĐỀ cửa sổ (document.title).
Tiêu đề cửa sổ đọc được bằng GetWindowTextW ở tầng hệ điều hành, KHÔNG đụng gì tới
DOM — nên bài thử không lén dùng lại đúng thứ đang cần loại bỏ.

Chạy:  "D:\\Python\\omnivoice\\OmniVoice\\venv\\Scripts\\python.exe" -X utf8 thu_khong_chiem_chuot.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dung_venv import dam_bao_venv                          # noqa: E402

dam_bao_venv(__file__)      # phải gọi TRƯỚC khi đụng tới numpy/Pillow

import ctypes               # noqa: E402
import subprocess           # noqa: E402
import time                 # noqa: E402
from ctypes import wintypes  # noqa: E402

import numpy as np          # noqa: E402
from PIL import Image       # noqa: E402

HERE = Path(__file__).resolve().parent
ANH = HERE / "anh_thu"
CHROME_EXE = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
PROFILE = "Profile 83"
MOC = "THU-BAM-NEN"          # mốc nhận ra cửa sổ trang thử qua tiêu đề

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
user32.SetProcessDPIAware()

WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP = 0x0200, 0x0201, 0x0202
WM_CHAR, MK_LBUTTON = 0x0102, 0x0001

for f, res, arg in (
    (user32.GetWindowDC, wintypes.HDC, [wintypes.HWND]),
    (gdi32.CreateCompatibleDC, wintypes.HDC, [wintypes.HDC]),
    (gdi32.CreateCompatibleBitmap, wintypes.HBITMAP,
     [wintypes.HDC, ctypes.c_int, ctypes.c_int]),
    (gdi32.SelectObject, wintypes.HGDIOBJ, [wintypes.HDC, wintypes.HGDIOBJ]),
    (gdi32.DeleteObject, wintypes.BOOL, [wintypes.HGDIOBJ]),
    (gdi32.DeleteDC, wintypes.BOOL, [wintypes.HDC]),
    (user32.ReleaseDC, ctypes.c_int, [wintypes.HWND, wintypes.HDC]),
    (user32.PrintWindow, wintypes.BOOL,
     [wintypes.HWND, wintypes.HDC, wintypes.UINT]),
):
    f.restype, f.argtypes = res, arg


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


# ───────────────────────────── cửa sổ & con trỏ ─────────────────────────────
def tieu_de(hwnd: int) -> str:
    n = user32.GetWindowTextLengthW(hwnd)
    b = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, b, n + 1)
    return b.value


def lop_cua_so(hwnd: int) -> str:
    b = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, b, 256)
    return b.value


def tim_cua_so(moc: str) -> int | None:
    ra = []

    def _moi(h, _):
        if user32.IsWindowVisible(h) and moc in tieu_de(h):
            ra.append(h)
        return True

    user32.EnumWindows(_ENUM(_moi), 0)
    return ra[0] if ra else None


def con_cua_so(hwnd: int) -> list[tuple[int, str]]:
    ra = []

    def _moi(h, _):
        ra.append((h, lop_cua_so(h)))
        return True

    user32.EnumChildWindows(hwnd, _ENUM(_moi), 0)
    return ra


def vi_tri_chuot() -> tuple[int, int]:
    p = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


def khung(hwnd: int) -> tuple[int, int, int, int]:
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def man_sang_khach(hwnd: int, x: int, y: int) -> tuple[int, int]:
    p = wintypes.POINT(x, y)
    user32.ScreenToClient(hwnd, ctypes.byref(p))
    return p.x, p.y


# ─────────────────────────── ĐO 1: chụp ngầm ────────────────────────────────
def chup_ngam(hwnd: int) -> tuple[Image.Image | None, tuple[int, int], bool]:
    """Chụp cửa sổ bằng PrintWindow — không cần đưa nó lên trên cùng."""
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


def tim_khoi_mau(img: Image.Image, mau: str) -> dict | None:
    """Tìm khối màu đặc trong ảnh → tâm + khung bao.

    Đây chính là khâu 'nhận diện nút' của phương án nhìn màn hình, làm bằng mặt
    nạ màu cho gọn; thật thì thay bằng dò mẫu OpenCV hoặc OCR."""
    a = np.asarray(img, dtype=np.int16)
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    mat_na = ((r > 200) & (g < 70) & (b > 200) if mau == "hong"
              else (r > 200) & (g > 200) & (b < 70))
    ys, xs = np.nonzero(mat_na)
    if len(xs) < 500:
        return None
    return {"cx": int(xs.mean()), "cy": int(ys.mean()), "so": int(len(xs)),
            "x0": int(xs.min()), "x1": int(xs.max()),
            "y0": int(ys.min()), "y1": int(ys.max())}


# ─────────────────── ĐO 2 & 3: bấm ngầm / gõ ngầm ───────────────────────────
def bam_ngam(hwnd: int, x: int, y: int) -> None:
    """Gửi chuỗi tin nhắn chuột THẲNG vào cửa sổ. Con trỏ không hề nhúc nhích."""
    lp = (y << 16) | (x & 0xFFFF)
    user32.PostMessageW(hwnd, WM_MOUSEMOVE, 0, lp)
    time.sleep(0.03)
    user32.PostMessageW(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lp)
    time.sleep(0.06)
    user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, lp)


def doc_toa_do(td: str) -> tuple[int, int] | None:
    """Bóc 'X=.. Y=..' mà trang thử ghi vào tiêu đề cửa sổ."""
    if "X=" not in td or "Y=" not in td:
        return None
    try:
        x = int(td.split("X=", 1)[1].split()[0])
        y = int(td.split("Y=", 1)[1].split()[0])
        return x, y
    except (ValueError, IndexError):
        return None


def go_ngam(hwnd: int, chu: str) -> None:
    """Gõ bằng WM_CHAR — đi theo mã Unicode nên có dấu tiếng Việt và chữ Hán."""
    for c in chu:
        user32.PostMessageW(hwnd, WM_CHAR, ord(c), 1)
        time.sleep(0.02)


# ───────────────────────────── trang thử ────────────────────────────────────
# Nút hồng cánh sen 520x240 CSS: biết trước kích thước CSS nên đo số điểm ảnh
# của nó trong ảnh chụp là suy ra ĐÚNG hệ số phóng DPI, khỏi phải đoán.
BUT_CSS_W, BUT_CSS_H = 520, 240
TRANG = """<!doctype html><meta charset="utf-8"><title>THU-BAM-NEN san sang</title>
<body style="margin:0;font:22px system-ui;background:#fff">
<div style="padding:24px">
  <div id="but" style="width:520px;height:240px;background:#FF00FF;color:#fff;
       display:flex;align-items:center;justify-content:center;font-size:34px">
    NUT THU — bam vao day
  </div>
  <input id="o" style="margin-top:24px;width:760px;height:70px;font-size:26px;
         padding:10px;background:#FFFF00;border:0" placeholder="o nhap thu">
  <pre id="kq" style="font-size:24px">chua co gi</pre>
</div>
<script>
let n = 0;
function bao(s){ document.title = 'THU-BAM-NEN ' + s; kq.textContent = s; }
document.addEventListener('click', e => {
  n++; bao('BAM=' + n + ' TRUSTED=' + e.isTrusted +
           ' X=' + e.clientX + ' Y=' + e.clientY);
});
o.addEventListener('input', () => bao('GO=' + o.value));
</script></body>"""


# ──────────────────────────────── chạy thử ──────────────────────────────────
def main():
    ANH.mkdir(parents=True, exist_ok=True)
    trang = HERE / "thu_bam_nen.html"
    trang.write_text(TRANG, encoding="utf-8")

    print("═" * 72)
    print("THỬ: nhìn màn hình + bấm NGẦM, không đụng con trỏ chuột")
    print("═" * 72)

    print(f"\n▶ Mở trang thử trong Chrome '{PROFILE}' (không đóng Chrome nào cả)")
    subprocess.Popen([str(CHROME_EXE), f"--profile-directory={PROFILE}",
                      "--new-window", trang.as_uri()])

    hwnd = None
    for _ in range(40):
        time.sleep(0.5)
        hwnd = tim_cua_so(MOC)
        if hwnd:
            break
    if not hwnd:
        sys.exit("❌ Không thấy cửa sổ trang thử.")
    time.sleep(2.0)
    print(f"  Cửa sổ: hwnd={hwnd}  lớp={lop_cua_so(hwnd)}")
    print(f"  Tiêu đề: {tieu_de(hwnd)!r}")

    con = con_cua_so(hwnd)
    print(f"  Cửa sổ con: {[c[1] for c in con] or '(không có)'}")
    # Chromium dựng một cửa sổ con 'legacy' để nhận tin nhắn chuột/bàn phím.
    render = next((h for h, lop in con if "RenderWidget" in lop), None)
    print(f"  Cửa sổ nhận tin nhắn: {render or '(chỉ có cửa sổ cha)'}")

    # ── ĐO 1 ────────────────────────────────────────────────────────────────
    print("\n" + "─" * 72)
    print("ĐO 1 — chụp ngầm bằng PrintWindow")
    print("─" * 72)
    img, goc, ok = chup_ngam(hwnd)
    if img is None:
        sys.exit("❌ Không chụp được.")
    img.save(ANH / "nen_truoc.png")
    a = np.asarray(img)
    print(f"  PrintWindow trả về: {ok}   kích thước: {img.size}")
    print(f"  Ảnh có đen thui không? trung bình sáng = {a.mean():.1f} "
          f"({'ĐEN — hỏng' if a.mean() < 8 else 'có hình'})")
    nut = tim_khoi_mau(img, "hong")
    o_go = tim_khoi_mau(img, "vang")
    if not nut:
        print("  ⚠ Không thấy nút hồng trong ảnh — trang chưa vẽ xong?")
        sys.exit(1)
    rong, cao = nut["x1"] - nut["x0"] + 1, nut["y1"] - nut["y0"] + 1
    ti_le = rong / BUT_CSS_W        # nút vốn 520 CSS → đo ra hệ số phóng DPI thật
    print(f"  Nút hồng: tâm ({nut['cx']},{nut['cy']}), khung {rong}x{cao} điểm ảnh")
    print(f"  Nút vốn {BUT_CSS_W}x{BUT_CSS_H} CSS → hệ số phóng DPI đo được = {ti_le:.3f}")
    print(f"  Ô nhập vàng: " +
          (f"tâm ({o_go['cx']},{o_go['cy']})" if o_go else "KHÔNG thấy"))
    print(f"  Ảnh: {ANH / 'nen_truoc.png'}")

    # ── ĐO 2 ────────────────────────────────────────────────────────────────
    print("\n" + "─" * 72)
    print("ĐO 2 — bấm ngầm: Chrome có DÙNG ĐÚNG toạ độ mình gửi không?")
    print("─" * 72)
    chuot_truoc = vi_tri_chuot()
    dich = render or hwnd
    print(f"  Con trỏ trước khi bấm: {chuot_truoc}")
    print("  Bấm 3 điểm KHÁC NHAU trong nút — toạ độ trang báo về phải bám theo:")
    diem = [(nut["x0"] + rong // 5, nut["y0"] + cao // 5),
            (nut["cx"], nut["cy"]),
            (nut["x1"] - rong // 5, nut["y1"] - cao // 5)]
    ket = []
    for i, (ix, iy) in enumerate(diem, 1):
        cx, cy = man_sang_khach(dich, goc[0] + ix, goc[1] + iy)
        bam_ngam(dich, cx, cy)
        time.sleep(0.7)
        bao = doc_toa_do(tieu_de(hwnd))
        ket.append(((ix, iy), (cx, cy), bao))
        print(f"   {i}. điểm ảnh({ix},{iy}) → gửi khách({cx},{cy}) → trang báo {bao}")

    if all(k[2] for k in ket):
        d_gui = (ket[2][1][0] - ket[0][1][0], ket[2][1][1] - ket[0][1][1])
        d_bao = (ket[2][2][0] - ket[0][2][0], ket[2][2][1] - ket[0][2][1])
        mong = (d_gui[0] / ti_le, d_gui[1] / ti_le)
        lech = max(abs(d_bao[0] - mong[0]), abs(d_bao[1] - mong[1]))
        print(f"  Gửi cách nhau {d_gui} điểm ảnh; chia hệ số phóng → mong đợi "
              f"({mong[0]:.0f},{mong[1]:.0f}) CSS")
        print(f"  Trang báo cách nhau {d_bao} CSS — lệch {lech:.1f}")
        print("  ✅ Chrome DÙNG ĐÚNG toạ độ mình gửi (bấm ngầm điều khiển được)"
              if lech <= 4 else
              "  ❌ Chrome KHÔNG theo toạ độ gửi — bấm ngầm không lái được")
    else:
        print("  ❌ Có cú bấm không tới nơi.")

    chuot_sau = vi_tri_chuot()
    print(f"  Con trỏ sau : {chuot_sau}   "
          f"{'✅ ĐỨNG YÊN suốt' if chuot_sau == chuot_truoc else '⚠ ĐÃ DI CHUYỂN'}")

    # ── ĐO 3 ────────────────────────────────────────────────────────────────
    print("\n" + "─" * 72)
    print("ĐO 3 — gõ ngầm chữ có dấu + chữ Hán bằng WM_CHAR")
    print("─" * 72)
    if o_go:
        cx, cy = man_sang_khach(dich, goc[0] + o_go["cx"], goc[1] + o_go["cy"])
        bam_ngam(dich, cx, cy)          # bấm vào ô nhập để đặt tiêu điểm
        time.sleep(0.7)
        print(f"  Đã bấm ngầm vào ô nhập tại khách({cx},{cy}) để lấy tiêu điểm")
    thu_chuoi = "kịch_bản N118 - 女主九族"
    print(f"  Gõ: {thu_chuoi!r}")
    go_ngam(dich, thu_chuoi)
    time.sleep(1.0)
    td = tieu_de(hwnd)
    if "GO=" in td:
        nhan = td.split("GO=", 1)[1].split(" - Google Chrome")[0]
        print(f"  Ô nhập nhận được: {nhan!r}")
        print("  ✅ KHỚP nguyên vẹn — gõ được cả dấu tiếng Việt lẫn chữ Hán"
              if nhan == thu_chuoi else f"  ⚠ LỆCH so với chuỗi gốc {thu_chuoi!r}")
    else:
        print(f"  ❌ Ô nhập không nhận ký tự nào. Tiêu đề: {td!r}")

    img2, _, _ = chup_ngam(hwnd)
    if img2:
        img2.save(ANH / "nen_sau.png")
        print(f"  Ảnh sau: {ANH / 'nen_sau.png'}")

    print("\n" + "═" * 72)
    print("XONG — cửa sổ để nguyên cho bạn xem.")
    print("═" * 72)


if __name__ == "__main__":
    main()
