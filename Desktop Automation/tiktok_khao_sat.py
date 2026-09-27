# -*- coding: utf-8 -*-
"""
tiktok_khao_sat.py — CHỤP TOÀN BỘ trang soạn bài TikTok, không bấm gì cả.

Dùng khi cần dạy cho bot một chỗ mới trên trang (công tắc 'Đăng theo lịch', ô
ngày giờ, nút Đăng...): chạy cái này để có ảnh thật ở đúng độ phân giải mà bot
nhìn thấy, rồi mới viết bước bấm. Đoán mò toạ độ là hỏng.

Việc nó làm: tìm cửa sổ Chrome đang mở TikTok → chụp → lăn chuột ngầm xuống một
quãng → chụp tiếp, cho tới khi trang không đổi nữa (đã chạm đáy) → cuộn trả lại
lên đầu trang cho y như lúc chưa đụng vào.

TUYỆT ĐỐI không bấm, không gõ, không đăng. Chạy lúc nào cũng an toàn.

Chạy:  chay_khao_sat.bat
       ... rồi xem anh_thu\\khaosat_00.png, khaosat_01.png, ...
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dung_venv import dam_bao_venv                          # noqa: E402

dam_bao_venv(__file__)

import argparse             # noqa: E402
import time                 # noqa: E402

import nen_win as nw        # noqa: E402

HERE = Path(__file__).resolve().parent
ANH = HERE / "anh_thu"
DO_TIKTOK = (254, 44, 85)       # #FE2C55 — nút chính của TikTok
XAM_O = (242, 242, 242)         # nền các ô nhập


def ta_khoi(img, rgb, it_nhat: int, ten: str) -> list[str]:
    ra = []
    for k in nw.tim_nut_mau(img, rgb, dung_sai=6 if rgb == DO_TIKTOK else 2,
                            it_nhat=it_nhat)[:6]:
        ra.append(f"{ten} tâm({k['cx']},{k['cy']}) khung {k['rong']}x{k['cao']} "
                  f"góc({k['x0']},{k['y0']})")
    return ra


def khao_sat(hwnd: int, nac: int = 5, so_buoc: int = 14, log=print) -> list[Path]:
    dich = nw.cua_so_nhan_chuot(hwnd)
    l, t, r, b = nw.khung(hwnd)
    giua = ((l + r) // 2, (t + b) // 2)
    ANH.mkdir(parents=True, exist_ok=True)
    for cu in ANH.glob("khaosat_*.png"):
        cu.unlink()

    anh_cu, ra, da_cuon = None, [], 0
    for i in range(so_buoc):
        time.sleep(0.8)
        img, _, _ = nw.chup_ngam(hwnd)
        if img is None:
            log("❌ Không chụp được cửa sổ.")
            break
        lech = nw.khac_anh(anh_cu, img, nguong=12)
        p = ANH / f"khaosat_{i:02d}.png"
        img.save(p)
        ra.append(p)
        log(f"── ảnh {i:02d} (đã cuộn {da_cuon * 100} px CSS, lệch ảnh trước "
            f"{lech:.1f}%) → {p.name}")
        for dong in ta_khoi(img, DO_TIKTOK, 1500, "   ĐỎ "):
            log(dong)
        for dong in ta_khoi(img, XAM_O, 20000, "   XÁM"):
            log(dong)
        if i and lech < 0.5:
            log("   (trang không đổi nữa — đã tới đáy)")
            break
        anh_cu = img
        nw.cuon_ngam(dich, giua[0], giua[1], -nac)
        da_cuon += nac

    if da_cuon:
        log(f"▶ Cuộn trả lại lên đầu trang ({da_cuon} nấc)")
        nw.cuon_ngam(dich, giua[0], giua[1], da_cuon + 3)
    return ra


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nac", type=int, default=5,
                    help="Mỗi lần cuộn bao nhiêu nấc (1 nấc = 100 px CSS).")
    ap.add_argument("--so-buoc", type=int, default=14)
    args = ap.parse_args()

    print("═" * 72)
    print("TIKTOK — chụp toàn trang soạn bài (KHÔNG bấm, KHÔNG gõ, KHÔNG đăng)")
    print("═" * 72)
    co = nw.tim_cua_so("Chrome_WidgetWin_1", "TikTok")
    if not co:
        sys.exit("❌ Không thấy cửa sổ Chrome nào đang mở TikTok.")
    hwnd = co[0]
    print(f"Cửa sổ {hwnd} — {nw.tieu_de(hwnd)!r}\n")
    ra = khao_sat(hwnd, nac=args.nac, so_buoc=args.so_buoc)
    print("\n" + "═" * 72)
    print(f"XONG — {len(ra)} ảnh trong {ANH}")
    print("═" * 72)


if __name__ == "__main__":
    main()
