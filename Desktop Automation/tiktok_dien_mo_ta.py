# -*- coding: utf-8 -*-
"""
tiktok_dien_mo_ta.py — Điền TIÊU ĐỀ + HASHTAG vào màn soạn bài TikTok Studio.

Bước 2, nối sau tiktok_chon_video.py (bước 1 — nạp video). Vẫn đúng lối cũ:
NHÌN MÀN HÌNH + BẤM NGẦM (xem nen_win.py), không DOM, không cổng gỡ lỗi, không
đụng con trỏ chuột của người đang ngồi máy.

  1. chụp ngầm cửa sổ, dò ô 'Mô tả' — khối NỀN XÁM #F2F2F2 rộng giữa trang,
  2. bấm ngầm vào đúng DÒNG CHỮ CUỐI trong ô để con nháy về cuối bài,
  3. xoá sạch chữ TikTok tự điền (tên file) bằng phím Backspace, xoá tới khi
     trong ô không còn cột điểm ảnh nào có chữ — nhìn thấy sạch thì mới thôi,
  4. gõ tiêu đề bằng WM_CHAR (đi theo mã Unicode nên đủ dấu tiếng Việt),
  5. từng hashtag một: gõ ' #tên', CHỜ BẢNG GỢI Ý hiện ra rồi mới ẤN ENTER —
     đây là chỗ quyết định: không có Enter thì TikTok chỉ coi đó là chữ thường,
     không thành hashtag thật.

Bảng gợi ý nhận ra bằng mắt chứ không đọc chữ: nó là tấm trắng đổ xuống che mất
một mảng NỀN XÁM của ô mô tả và dải thẻ bên dưới, nên chỉ cần đếm điểm ảnh xám
trong dải đó — tụt hẳn so với lúc trước khi gõ là bảng đã hiện.

KHÔNG bấm Đăng — việc đó vẫn thuộc bước sau.

Chạy:
  chay_dien_mo_ta.bat --tieu-de "..." --hashtag "#a #b"
  ... chạy trên cửa sổ TikTok ĐANG MỞ SẴN, nên thử đi thử lại thoải mái.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))   # chạy từ thư mục nào cũng được
from dung_venv import dam_bao_venv                          # noqa: E402

dam_bao_venv(__file__)      # phải gọi TRƯỚC khi đụng tới numpy/Pillow

import argparse             # noqa: E402
import time                 # noqa: E402

import numpy as np          # noqa: E402
from PIL import ImageDraw   # noqa: E402

import nen_win as nw        # noqa: E402

HERE = Path(__file__).resolve().parent
ANH = HERE / "anh_thu"

XAM_O_MO_TA = (242, 242, 242)   # #F2F2F2 — nền ô 'Mô tả', giao diện SÁNG
COT_TRAI = 0.16                 # cột menu trái chiếm ~16% bề ngang
NGUONG_TOI = 110                # tối hơn mức này = CHỮ (chữ TikTok #161823)
TI_LE_VUNG_CHU = 0.70           # 70% trên của ô là chỗ gõ chữ; 30% dưới là
                                # hàng nút '# Hashtag  @ Nhắc đến' — đừng bấm vào
TI_LE_GOI_Y = 0.90              # xám còn dưới 90% = bảng gợi ý đã che lên
COT_SACH = 6                    # dưới 6 cột chữ = ô coi như sạch (vạch nháy
                                # chỉ 2-3 cột, một chữ cái đã hơn chục cột)
XOA_MOI_VONG = 25               # số lần Backspace mỗi vòng, xoá tới khi ô sạch
XOA_TOI_DA_VONG = 20


# ──────────────────────────────── nhìn ──────────────────────────────────────
def tim_o_mo_ta(img) -> dict | None:
    """Khối nền xám của ô 'Mô tả'.

    Trang soạn bài có vài mảng cùng màu xám: chính ô mô tả, dải thẻ hashtag gợi
    ý ngay dưới nó, và mấy ô khác ở phần cuối trang. Lọc theo ba dấu hiệu bền:
      • nằm ngoài cột menu trái,
      • rộng gần hết vùng nội dung (ô mô tả luôn kéo hết bề ngang thẻ),
      • cao trên 100 điểm ảnh — dải thẻ gợi ý chỉ cao chừng 55.
    Còn nhiều cái thì lấy cái TRÊN CÙNG: ô mô tả luôn là ô đầu tiên của trang."""
    rong = img.size[0]
    khoi = nw.tim_nut_mau(img, XAM_O_MO_TA, dung_sai=2, it_nhat=20000)
    ung_vien = [k for k in khoi
                if k["x0"] > rong * COT_TRAI and k["rong"] > rong * 0.30
                and k["cao"] >= 100]
    if not ung_vien:
        return None
    # Ép về int thường: số đo khối là int64 của numpy, mà ctypes không nhận
    # thẳng kiểu đó khi gửi toạ độ bấm sang Windows.
    return {k: int(v) for k, v in min(ung_vien, key=lambda k: k["y0"]).items()}


def vung_chu(hop: dict) -> tuple[int, int, int, int]:
    """Khung chữ nhật (x0,y0,x1,y1) của phần GÕ CHỮ bên trong ô mô tả."""
    return (hop["x0"] + 10, hop["y0"] + 6, hop["x1"] - 10,
            hop["y0"] + int(hop["cao"] * TI_LE_VUNG_CHU))


def _xam_anh(img, vung: tuple[int, int, int, int]) -> np.ndarray:
    x0, y0, x1, y1 = vung
    return np.asarray(img.convert("L"), dtype=np.int16)[y0:y1, x0:x1]


def dem_cot_chu(img, vung) -> int:
    """Bao nhiêu CỘT điểm ảnh có chữ trong khung. Ô rỗng thì gần như bằng 0.

    Đếm CỘT chứ không đếm điểm ảnh, vì vạch nháy cũng tối om như chữ: nó chỉ
    chiếm 2-3 cột, còn một chữ cái đã hơn chục cột. Đếm điểm ảnh thì vạch nháy
    nhấp nháy đủ làm vòng xoá chạy mãi mà không bao giờ thấy ô sạch."""
    return int((_xam_anh(img, vung) < NGUONG_TOI).any(axis=0).sum())


def dong_chu_cuoi(img, vung) -> int | None:
    """Dòng (toạ độ ảnh) thấp nhất còn chữ — chỗ nên bấm để con nháy về cuối bài."""
    toi = _xam_anh(img, vung) < NGUONG_TOI
    hang = np.flatnonzero(toi.any(axis=1))
    return None if hang.size == 0 else vung[1] + int(hang[-1])


def dai_theo_doi(hop: dict, img) -> tuple[int, int, int, int]:
    """Dải để rình bảng gợi ý: cả ô mô tả + khoảng ngay dưới nó (dải thẻ gợi ý).

    Bảng gợi ý đổ xuống từ con nháy, che lên một trong hai chỗ đó — nhìn cả dải
    thì con nháy nằm ở dòng nào cũng bắt được."""
    rong, cao = img.size
    return (hop["x0"], hop["y0"], min(hop["x1"], rong - 1),
            min(hop["y1"] + 2 * hop["cao"], cao - 1))


def dem_xam(img, dai) -> int:
    x0, y0, x1, y1 = dai
    return int(nw.mat_na_mau(img, XAM_O_MO_TA, dung_sai=2)[y0:y1, x0:x1].sum())


def luu_anh(img, hop: dict | None, diem: tuple[int, int] | None, ten: str) -> Path:
    """Chụp lại việc máy đã làm: khung ô mô tả + chữ thập ở chỗ nó bấm."""
    ve = img.copy()
    d = ImageDraw.Draw(ve)
    if hop:
        d.rectangle([hop["x0"], hop["y0"], hop["x1"], hop["y1"]],
                    outline=(0, 160, 255), width=3)
        vx0, vy0, vx1, vy1 = vung_chu(hop)
        d.rectangle([vx0, vy0, vx1, vy1], outline=(0, 200, 120), width=2)
    if diem:
        x, y = diem
        d.line([x - 20, y, x + 20, y], fill=(255, 0, 0), width=4)
        d.line([x, y - 20, x, y + 20], fill=(255, 0, 0), width=4)
    ANH.mkdir(parents=True, exist_ok=True)
    p = ANH / ten
    ve.save(p)
    return p


# ──────────────────────────────── gõ ────────────────────────────────────────
def tach_hashtag(chu: str) -> list[str]:
    """'#a #b, c' → ['#a', '#b', '#c'] — bỏ dấu phẩy, tự thêm '#' nếu thiếu."""
    ra = []
    for t in chu.replace(",", " ").split():
        t = t.strip().lstrip("#").strip()
        if t:
            ra.append("#" + t)
    return ra


def xoa_chu_cu(hwnd: int, dich: int, hop: dict, log=print) -> bool:
    """Xoá sạch chữ TikTok tự điền (tên file mp4) bằng Backspace.

    Xoá theo MẮT chứ không đếm ký tự: sau mỗi vòng lại chụp, còn thấy điểm ảnh
    tối trong ô thì xoá tiếp. Bài dài bị cuộn khuất cũng sạch, vì chữ khuất sẽ
    trôi vào tầm nhìn khi phần dưới bị xoá đi."""
    vung = vung_chu(hop)
    truoc = -1
    for vong in range(XOA_TOI_DA_VONG):
        anh, _, _ = nw.chup_ngam(hwnd)
        if anh is None:
            log("  ⚠ Không chụp được cửa sổ giữa chừng.")
            return False
        con = dem_cot_chu(anh, vung)
        if con < COT_SACH:
            log(f"  ✅ Ô mô tả đã sạch sau {vong} vòng xoá.")
            return True
        if vong and con == truoc:
            log(f"  ❌ Xoá 2 vòng mà chữ không suy suyển ({con} cột chữ) — "
                "phím Backspace không tới được ô, có thể bấm hụt tiêu điểm.")
            return False
        log(f"   vòng {vong + 1}: còn {con} cột chữ → Backspace "
            f"{XOA_MOI_VONG} lần")
        truoc = con
        for _ in range(XOA_MOI_VONG):
            nw.phim_ngam(dich, nw.VK_BACK, 0.02)
            time.sleep(0.03)
        time.sleep(0.35)
    log("  ⚠ Hết số vòng xoá mà ô vẫn còn chữ.")
    return False


def cho_bang_goi_y(hwnd: int, dai, xam_goc: int, giay: float, log=print) -> bool:
    """Chờ bảng gợi ý hashtag hiện ra (nó che mất một mảng nền xám)."""
    han = time.time() + giay
    it_nhat = xam_goc
    while time.time() < han:
        time.sleep(0.35)
        anh, _, _ = nw.chup_ngam(hwnd)
        if anh is None:
            continue
        nay = dem_xam(anh, dai)
        it_nhat = min(it_nhat, nay)
        if nay < xam_goc * TI_LE_GOI_Y:
            log(f"    bảng gợi ý đã hiện (xám {xam_goc} → {nay})")
            return True
    log(f"    ⚠ chờ hết {giay:.0f}s chưa thấy bảng gợi ý "
        f"(xám {xam_goc} → thấp nhất {it_nhat})")
    return False


def go_mot_hashtag(hwnd: int, dich: int, the: str, dai, cho_goi_y: float,
                   luon_enter: bool, log=print) -> bool:
    """Gõ MỘT hashtag rồi Enter để TikTok biến nó thành hashtag thật.

    Gõ thêm dấu cách phía trước cho chắc: nếu lần Enter trước đã tự chèn dấu
    cách thì thừa một khoảng trắng (không sao), còn nếu chưa thì tránh được cảnh
    hai hashtag dính vào nhau thành một."""
    anh, _, _ = nw.chup_ngam(hwnd)
    xam_goc = dem_xam(anh, dai) if anh is not None else 0
    log(f"  ▶ {the}")
    nw.go_ngam(dich, " " + the, nghi=0.035)
    time.sleep(0.25)

    co = cho_bang_goi_y(hwnd, dai, xam_goc, cho_goi_y, log) if xam_goc else False
    if not co and not luon_enter:
        log("    (bỏ Enter theo lựa chọn — hashtag này sẽ chỉ là chữ thường)")
        return False
    nw.phim_ngam(dich, nw.VK_RETURN, 0.05)
    time.sleep(0.6)
    return co


# ─────────────────────────────── việc chính ─────────────────────────────────
def dien_mo_ta(hwnd: int, tieu_de: str, hashtag: str, log=print,
               cho_goi_y: float = 5.0, luon_enter: bool = True,
               cho_tu_dien: float = 8.0) -> dict:
    """Điền tiêu đề + hashtag vào ô 'Mô tả' của màn soạn bài đang mở.

    → {"ok": bool, "ly_do": str, "the_that": int, "the_tong": int, "anh": str}
    `the_that` là số hashtag thấy bảng gợi ý lúc Enter — tức gần như chắc chắn
    đã thành hashtag thật."""
    ket: dict = {"ok": False, "ly_do": "", "the_that": 0, "the_tong": 0, "anh": ""}
    tieu_de = (tieu_de or "").strip()
    the_list = tach_hashtag(hashtag or "")
    ket["the_tong"] = len(the_list)
    if not tieu_de and not the_list:
        ket["ly_do"] = "Dòng này không có tiêu đề lẫn hashtag — bỏ qua."
        log("⏩ " + ket["ly_do"])
        return ket
    if not nw.user32.IsWindow(hwnd):
        ket["ly_do"] = "Cửa sổ TikTok không còn."
        log("❌ " + ket["ly_do"])
        return ket

    dich = nw.san_sang(hwnd, log)
    if not dich:
        ket["ly_do"] = (
            "Trang không nhận lệnh nữa: Chrome đã bỏ khung trang của thẻ này "
            "(thường do cửa sổ nằm im quá lâu, hoặc có hộp thoại kẹt ở một cửa "
            "sổ TikTok khác). Đóng hết cửa sổ TikTok rồi chạy lại dòng này — "
            "video sẽ nạp lại từ đầu.")
        log("❌ " + ket["ly_do"])
        return ket
    chuot_dau = nw.vi_tri_chuot()
    log(f"▶ Điền mô tả — tiêu đề {len(tieu_de)} ký tự, {len(the_list)} hashtag")

    # ── dò ô mô tả ──────────────────────────────────────────────────────────
    img, goc, _ = nw.chup_ngam(hwnd)
    if img is None:
        ket["ly_do"] = "Không chụp được cửa sổ."
        log("❌ " + ket["ly_do"])
        return ket
    hop = tim_o_mo_ta(img)
    if not hop:
        ket["anh"] = str(luu_anh(img, None, None, "tiktok_b2_mo_ta.png"))
        ket["ly_do"] = ("Không dò ra ô 'Mô tả' (chưa sang màn soạn bài, "
                        "trang bị cuộn, hoặc TikTok đang để giao diện tối).")
        log(f"❌ {ket['ly_do']} Xem ảnh: {ket['anh']}")
        return ket
    log(f"  Ô mô tả: khung {hop['rong']}x{hop['cao']} tại "
        f"({hop['x0']},{hop['y0']})")
    vung = vung_chu(hop)
    dai = dai_theo_doi(hop, img)

    # TikTok tự điền TÊN FILE vào ô mô tả ngay sau khi nhận video, nhưng chậm
    # hơn lúc màn soạn bài hiện ra một nhịp. Gõ trước nó thì chữ của mình bị nó
    # đè lên — nên chờ chữ tự điền xuất hiện rồi mới xoá.
    han = time.time() + cho_tu_dien
    while time.time() < han:
        if dem_cot_chu(img, vung) >= COT_SACH:
            log("  TikTok đã tự điền tên file vào ô mô tả.")
            break
        time.sleep(0.6)
        anh, goc_moi, _ = nw.chup_ngam(hwnd)
        if anh is not None:
            img, goc = anh, goc_moi        # cửa sổ bị kéo đi chỗ khác vẫn bấm đúng
    else:
        log(f"  Chờ hết {cho_tu_dien:.0f}s, ô mô tả vẫn rỗng — gõ thẳng vào.")

    # ── bấm vào cuối bài ────────────────────────────────────────────────────
    # Bấm bên PHẢI dòng chữ cuối cùng: bấm vào khoảng trống cuối một dòng thì
    # con nháy nhảy về cuối dòng đó, nên Backspace sau đây xoá được sạch bài.
    dong = dong_chu_cuoi(img, vung)
    diem = ((hop["x0"] + 60, hop["y0"] + 30) if dong is None
            else (hop["x1"] - 80, dong))
    log(f"▶ Bấm ngầm vào ô mô tả tại ({diem[0]},{diem[1]})"
        + ("  (ô đang rỗng)" if dong is None else f" — dòng chữ cuối ở y={dong}"))
    nw.bam_ngam_theo_anh(dich, goc, *diem)
    time.sleep(0.6)

    # ── xoá chữ cũ ──────────────────────────────────────────────────────────
    log("▶ Xoá chữ TikTok tự điền (tên file)")
    if not xoa_chu_cu(hwnd, dich, hop, log):
        anh, _, _ = nw.chup_ngam(hwnd)
        ket["anh"] = str(luu_anh(anh or img, hop, diem, "tiktok_b2_mo_ta.png"))
        ket["ly_do"] = "Không xoá được chữ cũ trong ô mô tả."
        log(f"❌ {ket['ly_do']} Xem ảnh: {ket['anh']}")
        return ket

    # ── gõ tiêu đề ──────────────────────────────────────────────────────────
    if tieu_de:
        log(f"▶ Gõ tiêu đề: {tieu_de!r}")
        nw.go_ngam(dich, tieu_de, nghi=0.035)
        time.sleep(0.5)
        anh, _, _ = nw.chup_ngam(hwnd)
        if anh is not None and dem_cot_chu(anh, vung) < COT_SACH:
            ket["anh"] = str(luu_anh(anh, hop, diem, "tiktok_b2_mo_ta.png"))
            ket["ly_do"] = "Gõ xong mà ô mô tả vẫn rỗng — chữ không vào được ô."
            log(f"❌ {ket['ly_do']} Xem ảnh: {ket['anh']}")
            return ket

    # ── gõ hashtag, mỗi cái một lần Enter ───────────────────────────────────
    if the_list:
        log(f"▶ Gõ {len(the_list)} hashtag — mỗi cái chờ bảng gợi ý rồi ẤN ENTER")
    for the in the_list:
        if go_mot_hashtag(hwnd, dich, the, dai, cho_goi_y, luon_enter, log):
            ket["the_that"] += 1

    anh, _, _ = nw.chup_ngam(hwnd)
    ket["anh"] = str(luu_anh(anh or img, hop, diem, "tiktok_b2_mo_ta.png"))
    chuot_cuoi = nw.vi_tri_chuot()
    log(f"  Con trỏ chuột: {chuot_dau} → {chuot_cuoi}  "
        f"{'✅ đứng yên suốt' if chuot_dau == chuot_cuoi else '⚠ đã di chuyển'}")

    ket["ok"] = True
    ket["ly_do"] = (f"Đã điền mô tả; {ket['the_that']}/{ket['the_tong']} hashtag "
                    "thấy bảng gợi ý lúc Enter.")
    if ket["the_that"] < ket["the_tong"]:
        ket["ly_do"] += " Xem ảnh để chắc các thẻ còn lại có thành hashtag không."
    log("✅ " + ket["ly_do"])
    return ket


def cua_so_tiktok() -> int | None:
    """Cửa sổ Chrome đang mở TikTok — để chạy riêng bước này trên màn đang mở."""
    co = nw.tim_cua_so("Chrome_WidgetWin_1", "TikTok")
    return co[0] if co else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tieu-de", default="", help="Tiêu đề bài đăng.")
    ap.add_argument("--hashtag", default="", help="Các hashtag, cách nhau dấu cách.")
    ap.add_argument("--cho-goi-y", type=float, default=5.0,
                    help="Số giây chờ bảng gợi ý hashtag hiện ra.")
    ap.add_argument("--khong-enter", action="store_true",
                    help="Không thấy bảng gợi ý thì THÔI, không ấn Enter "
                         "(mặc định: vẫn ấn).")
    args = ap.parse_args()

    print("═" * 72)
    print("TIKTOK — điền tiêu đề + hashtag vào màn soạn bài ĐANG MỞ")
    print("═" * 72)
    hwnd = cua_so_tiktok()
    if not hwnd:
        sys.exit("❌ Không thấy cửa sổ Chrome nào đang mở TikTok.")
    print(f"Cửa sổ {hwnd} — {nw.tieu_de(hwnd)!r}\n")

    ket = dien_mo_ta(hwnd, args.tieu_de, args.hashtag,
                     cho_goi_y=args.cho_goi_y, luon_enter=not args.khong_enter)
    print("\n" + "═" * 72)
    print(("XONG. " if ket["ok"] else "DỪNG. ") + ket["ly_do"])
    print(f"Ảnh: {ket['anh']}")
    print("KHÔNG bấm Đăng.")
    print("═" * 72)
    sys.exit(0 if ket["ok"] else 1)


if __name__ == "__main__":
    main()
