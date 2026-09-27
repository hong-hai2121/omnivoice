# -*- coding: utf-8 -*-
"""
tiktok_len_lich.py — Hẹn giờ đăng bằng chính chức năng 'Lên lịch' của TikTok.

Bước 3, nối sau tiktok_dien_mo_ta.py. Vẫn nhìn màn hình + bấm ngầm (nen_win.py).

Làm đúng như người dùng tay:
  1. cuộn xuống cuối trang, bấm nút tròn 'Lên lịch' ở mục 'Thời điểm đăng',
  2. cuộn cho hàng giờ/ngày xuống nửa dưới màn hình — hai bảng chọn đều bung
     NGƯỢC LÊN TRÊN, ô nằm cao quá thì bảng bị cắt mất nửa trên,
  3. chọn NGÀY trong bảng lịch,
  4. chọn GIỜ và PHÚT trên bánh xe hai cột,
  5. (tuỳ chọn) bấm nút đỏ 'Lên lịch' để chốt.

Hai chỗ khó, và cách làm cho chắc — không có OCR nên không đọc được chữ số:

  NGÀY  Lịch là lưới 7 cột (CN→T7) x 5-6 hàng, dò bằng cách chiếu điểm ảnh chữ
        lên hai trục (không đoán khoảng cách ô). Trước hết phải biết lịch đang
        hiện THÁNG NÀO — nó mở ở tháng của ngày đang chọn chứ không phải tháng
        này — nhận ra bằng hai dấu cùng lúc: SỐ HÀNG của lưới (TikTok vẽ vừa đủ
        số tuần, không đệm cho tròn 6) và vị trí Ô ĐẬM ĐẦU TIÊN (ngày đã qua bị
        làm mờ). Biết tháng rồi thì ô của ngày cần đặt là phép trừ ngày thuần
        tuý. Ngày rơi ra ngoài lưới thì bấm mũi tên › sang tháng sau. Bấm xong
        kiểm lại: vòng tròn đỏ phải nhảy đúng vào ô vừa bấm.

  GIỜ   Bánh xe cuộn, hàng GIỮA là giá trị đang chọn, mỗi nấc lăn đúng 1 hàng.
        Không đọc được số thì lấy mốc ở ĐẦU danh sách: lăn hết cỡ lên là về 00
        (cả hai cột), rồi lăn xuống đúng số nấc cần — TỪNG NẤC MỘT, đo lại sau
        mỗi nấc. Lăn cả cụm rồi đo tổng là bị lừa: cột toàn chữ số na ná nhau
        nên bánh xe chạm mép rồi mà vẫn lăn thì phép so ảnh vẫn ra số trông hợp
        lý (đã hố một lần: đặt 21:15 mà thành 21:00).

TikTok bắt hẹn sau hiện tại ít nhất 15 phút, và phút chỉ chọn được bội số của 5.

Chạy:
  chay_len_lich.bat --khi-nao "2026-09-23 20:30"        (chỉ đặt, KHÔNG bấm)
  chay_len_lich.bat --khi-nao "2026-09-23 20:30" --bam-dang
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dung_venv import dam_bao_venv                          # noqa: E402

dam_bao_venv(__file__)

import argparse             # noqa: E402
import calendar             # noqa: E402
import time                 # noqa: E402
from datetime import datetime, timedelta   # noqa: E402

import numpy as np          # noqa: E402
from PIL import ImageDraw   # noqa: E402

import nen_win as nw        # noqa: E402

HERE = Path(__file__).resolve().parent
ANH = HERE / "anh_thu"

DO_TIKTOK = (254, 44, 85)
XAM_O = (242, 242, 242)
TRANG = (255, 255, 255)
COT_TRAI = 0.16
X_NEN = 0.155               # khe trống giữa cột menu và thẻ nội dung: bấm vào
                            # đây là đóng được mọi bảng đang bung, không trúng gì
NGUONG_CHU = 200            # chữ xám mờ (ngày đã qua) cũng phải tính là chữ
NGUONG_MO = 120             # tối hơn mức này = ngày CÒN chọn được (chữ đậm hoặc
                            # nền đỏ); nhạt hơn = ngày đã qua, TikTok làm mờ
SOM_NHAT = 15               # TikTok: hẹn sau hiện tại ít nhất 15 phút
BUOC_PHUT = 5               # bánh xe phút chỉ có bội số của 5
XA_NHAT_NGAY = 30           # đo thật 22/09/2026: lịch cho chọn tới
                            # 22/10, tức 30 ngày; xa hơn thì làm mờ


# ─────────────────────────── nhìn: các mốc trên trang ───────────────────────
def _int(k: dict) -> dict:
    return {a: int(b) for a, b in k.items()}


def tim_cham_chon(img) -> dict | None:
    """Nút tròn đỏ đang bật ở mục 'Thời điểm đăng' (Bây giờ / Lên lịch)."""
    w = img.size[0]
    for k in nw.tim_nut_mau(img, DO_TIKTOK, dung_sai=40, it_nhat=120):
        if (k["x0"] > w * COT_TRAI and k["rong"] < 40
                and 0.7 < k["rong"] / max(k["cao"], 1) < 1.4):
            return _int(k)
    return None


def tim_cap_o(img) -> tuple[dict | None, dict | None]:
    """Hai ô xám nằm cùng một hàng = (ô GIỜ, ô NGÀY).

    Chỉ hiện ra khi đã bật 'Lên lịch' — nên đây cũng là cách biết đã bật hay
    chưa, chắc hơn là đo xem chấm đỏ nằm bên trái hay bên phải."""
    w = img.size[0]
    o = [_int(k) for k in nw.tim_nut_mau(img, XAM_O, dung_sai=3, it_nhat=4000)
         if k["x0"] > w * COT_TRAI and 150 <= k["rong"] <= 400
         and 30 <= k["cao"] <= 60]
    # Ghép theo ĐỘ CHỒNG NHAU chiều dọc chứ đừng so tâm: lúc bảng chọn đang
    # bung, mép trên một ô bị che mất nên tâm nó tụt xuống vài điểm ảnh. Và phải
    # xếp lại trái→phải, vì ô bên phải đôi khi nhỉnh lên 1 điểm ảnh là thứ tự
    # đảo ngược, thành ra nhầm ô giờ với ô ngày.
    o.sort(key=lambda k: k["y0"])
    for i in range(len(o) - 1):
        a, b = o[i], o[i + 1]
        chung = min(a["y1"], b["y1"]) - max(a["y0"], b["y0"])
        if chung > 0.5 * min(a["cao"], b["cao"]):
            trai, phai = sorted((a, b), key=lambda k: k["cx"])
            return trai, phai
    return None, None


def tim_nut_dang(img) -> dict | None:
    """Nút đỏ to ở đáy trang: 'Đăng' hoặc 'Lên lịch'.

    Lúc video còn đang tải lên, nút này xám (không bấm được) nên KHÔNG dò ra —
    đúng ý mình: chưa thấy nút đỏ thì chưa được bấm."""
    w = img.size[0]
    ra = [_int(k) for k in nw.tim_nut_mau(img, DO_TIKTOK, dung_sai=34, it_nhat=1500)
          if k["x0"] > w * COT_TRAI and k["rong"] > 150]
    return max(ra, key=lambda k: k["cy"]) if ra else None


def tam_bang_bung(img, o: dict) -> dict | None:
    """Tấm trắng của bảng vừa bung ra phía TRÊN một ô (lịch hoặc bánh xe).

    Nhận ra nó bằng mảng TRẮNG TINH liền khối: nền trang cũng trắng, nhưng bảng
    có viền và bóng đổ nên không dính vào nhau."""
    for k in nw.tim_nut_mau(img, TRANG, dung_sai=0, it_nhat=20000):
        k = _int(k)
        if (k["y1"] <= o["y0"] + 12 and k["y1"] > o["y0"] - 500
                and k["x0"] >= o["x0"] - 40 - 2 * o["rong"]
                and k["x1"] <= o["x1"] + 40 and k["rong"] >= o["rong"] * 0.8):
            return k
    return None


def bam_ra_nen(hwnd: int, dich: int) -> None:
    """Bấm vào khoảng trống của trang để đóng bảng đang bung (lịch, bánh xe)."""
    l, t, r, b = nw.khung(hwnd)
    nw.bam_ngam(dich, *nw.man_sang_khach(dich, l + int((r - l) * X_NEN),
                                         t + (b - t) // 2))
    time.sleep(0.9)


def _dai(mat_na: np.ndarray, it_nhat: int = 2, ke_ho: int = 6) -> list[tuple]:
    """Gom các chỉ số True liền nhau thành từng dải (đầu, cuối, giữa)."""
    idx = np.flatnonzero(mat_na)
    if not len(idx):
        return []
    ra, dau, truoc = [], idx[0], idx[0]
    for i in idx[1:]:
        if i - truoc > ke_ho:
            if truoc - dau + 1 >= it_nhat:
                ra.append((int(dau), int(truoc), int((dau + truoc) // 2)))
            dau = i
        truoc = i
    if truoc - dau + 1 >= it_nhat:
        ra.append((int(dau), int(truoc), int((dau + truoc) // 2)))
    return ra


def doc_luoi_lich(img, tam: dict) -> dict | None:
    """Toạ độ các cột/hàng của lưới ngày, đo từ chính chữ trong bảng.

    Đo chứ không đoán: cỡ chữ và mức phóng của trang đổi thì lưới vẫn đúng."""
    a = np.asarray(img.convert("L"), dtype=np.int16)[
        tam["y0"]:tam["y1"] + 1, tam["x0"]:tam["x1"] + 1]
    toi = a < NGUONG_CHU
    dong = _dai(toi.any(axis=1), it_nhat=4, ke_ho=8)
    if len(dong) < 2:
        return None
    # Mỗi ô có 1-2 chữ số nên phải gộp: hai cụm cách nhau dưới 20 điểm ảnh là
    # cùng một ô. Hàng nào đọc ra đủ 7 ô thì lấy hàng đó làm thước đo cột.
    for d in reversed(dong):
        cot = [tam["x0"] + b[2]
               for b in _dai(toi[d[0]:d[1] + 1].any(axis=0), it_nhat=2, ke_ho=20)]
        if len(cot) == 7:
            return {"cot": cot, "hang": [tam["y0"] + b[2] for b in dong]}
    return None


def o_dam_dau_tien(img, luoi: dict) -> tuple[int, int] | None:
    """Ô ĐẦU TIÊN chưa bị làm mờ trong lưới — mốc neo của cả bảng lịch.

    Không lấy vòng tròn đỏ làm mốc: vòng đỏ là ngày ĐANG CHỌN, chỉ trùng hôm nay
    ở lần mở đầu tiên. Ngày đã qua thì TikTok tô chữ xám nhạt, từ hôm nay trở đi
    mới đậm — nên ô đậm đầu tiên là ngày lớn hơn trong hai cái: hôm nay, và ngày
    ở ô đầu lưới (khi lịch đang hiện tháng sau thì cả lưới đều là tương lai)."""
    a = np.asarray(img.convert("L"), dtype=np.int16)
    dx = (luoi["cot"][-1] - luoi["cot"][0]) // 6
    dy = ((luoi["hang"][-1] - luoi["hang"][0]) // max(len(luoi["hang"]) - 1, 1)
          if len(luoi["hang"]) > 1 else 40)
    for h, y in enumerate(luoi["hang"]):
        for c, x in enumerate(luoi["cot"]):
            o = a[max(0, y - int(dy * 0.3)):y + int(dy * 0.3),
                  max(0, x - int(dx * 0.28)):x + int(dx * 0.28)]
            if o.size and int(o.min()) < NGUONG_MO:
                return h, c
    return None


def o_dam_cuoi_cung(img, luoi: dict) -> tuple[int, int] | None:
    """Ô CUỐI CÙNG chưa bị làm mờ — dấu nhận dạng thứ hai của bảng lịch.

    TikTok làm mờ cả ngày quá xa (ngoài 30 hôm), nên vùng ô đậm là một đoạn có
    đầu có đuôi. Chỉ nhìn đầu đoạn thì hai tháng liền nhau đôi khi giống hệt
    nhau; nhìn thêm đuôi là hết giống."""
    a = np.asarray(img.convert("L"), dtype=np.int16)
    dx = (luoi["cot"][-1] - luoi["cot"][0]) // 6
    dy = ((luoi["hang"][-1] - luoi["hang"][0]) // max(len(luoi["hang"]) - 1, 1)
          if len(luoi["hang"]) > 1 else 40)
    for h in range(len(luoi["hang"]) - 1, -1, -1):
        for c in range(len(luoi["cot"]) - 1, -1, -1):
            y, x = luoi["hang"][h], luoi["cot"][c]
            o = a[max(0, y - int(dy * 0.3)):y + int(dy * 0.3),
                  max(0, x - int(dx * 0.28)):x + int(dx * 0.28)]
            if o.size and int(o.min()) < NGUONG_MO:
                return h, c
    return None


def vong_do_lich(img, tam: dict) -> dict | None:
    """Vòng tròn đỏ = ngày đang được chọn trong bảng lịch."""
    for k in nw.tim_nut_mau(img, DO_TIKTOK, dung_sai=40, it_nhat=300):
        k = _int(k)
        if (tam["x0"] <= k["cx"] <= tam["x1"] and tam["y0"] <= k["cy"] <= tam["y1"]
                and 0.7 < k["rong"] / max(k["cao"], 1) < 1.4 and 20 <= k["rong"] <= 70):
            return k
    return None


def _gan_nhat(day: list[int], gt: int) -> int:
    return min(range(len(day)), key=lambda i: abs(day[i] - gt))


def ngay_dau_luoi(thang) -> "datetime":
    """Ngày nằm ở ô (hàng 0, cột 0) của lưới tháng đó — tuần bắt đầu Chủ Nhật."""
    dau = thang.replace(day=1)
    return dau - timedelta(days=(dau.weekday() + 1) % 7)


def so_hang_luoi(thang) -> int:
    """Lưới tháng đó có mấy hàng. TikTok vẽ vừa đủ số tuần, không đệm cho tròn 6
    — nhờ vậy số hàng thành một dấu hiệu nhận ra tháng."""
    c1 = (thang.replace(day=1).weekday() + 1) % 7
    return -(-(c1 + calendar.monthrange(thang.year, thang.month)[1]) // 7)


def hop_voi_thang(img, luoi: dict, thang, hom_nay) -> bool:
    """Lưới đang nhìn thấy có đúng là tháng `thang` không?

    Soi hai dấu cùng lúc: SỐ HÀNG của lưới, và vị trí Ô ĐẬM ĐẦU TIÊN. Dùng để
    XÁC NHẬN một phỏng đoán, chứ không dùng để đoán mò ra tháng: lịch đang mở ở
    tháng tương lai thì mọi ô đều đậm, hai tháng khác nhau vẫn có thể cho cùng
    một bộ dấu."""
    if so_hang_luoi(thang) != len(luoi["hang"]):
        return False
    dau = ngay_dau_luoi(thang).date()
    cuoi_luoi = dau + timedelta(days=len(luoi["hang"]) * 7 - 1)
    dam_dau = max(hom_nay.date(), dau)
    dam_cuoi = min(hom_nay.date() + timedelta(days=XA_NHAT_NGAY), cuoi_luoi)
    if dam_dau > cuoi_luoi or dam_cuoi < dau:
        return False                             # tháng này không có ô nào đậm
    if o_dam_dau_tien(img, luoi) != divmod((dam_dau - dau).days, 7):
        return False
    thay = o_dam_cuoi_cung(img, luoi)
    mong = divmod((dam_cuoi - dau).days, 7)
    # Nới một ô cho mốc cuối: hạn 30 ngày là đo được chứ không phải TikTok công
    # bố, lệch một ngày vẫn chấp nhận — dấu đầu đoạn mới là dấu chính.
    return bool(thay) and abs((thay[0] * 7 + thay[1]) - (mong[0] * 7 + mong[1])) <= 1


def thang_ke(thang, buoc: int):
    """Tháng liền trước (buoc=-1) hoặc liền sau (buoc=+1)."""
    thang = thang.replace(day=1)
    return ((thang + timedelta(days=32 * buoc)).replace(day=1) if buoc > 0
            else (thang - timedelta(days=1)).replace(day=1))


def doi_thang(hwnd: int, dich: int, goc, o_ngay: dict, tam: dict, luoi: dict,
              buoc: int, log=print):
    """Bấm mũi tên ‹ / › rồi đọc lại bảng → (img, luoi, tam) hoặc None."""
    hang = luoi["hang"]
    dy = (hang[-1] - hang[0]) // max(len(hang) - 1, 1) if len(hang) > 1 else 45
    img, _, _ = nw.chup_ngam(hwnd)
    ten = mui_ten_thang(img, tam, dy)
    if not ten:
        log("  ❌ Không thấy mũi tên đổi tháng ở đầu bảng lịch.")
        return None
    diem = ten["sau"] if buoc > 0 else ten["truoc"]
    log(f"  ▶ bấm mũi tên {'›' if buoc > 0 else '‹'} tại {diem}")
    nw.bam_ngam_theo_anh(dich, goc, *diem)
    time.sleep(1.4)
    img2, _, _ = nw.chup_ngam(hwnd)
    tam2 = tam_bang_bung(img2, o_ngay)
    luoi2 = doc_luoi_lich(img2, tam2) if tam2 else None
    if not luoi2:
        log("  ❌ Đổi tháng xong không đọc lại được lưới ngày.")
        return None
    return img2, luoi2, tam2


def o_cua_ngay(luoi: dict, thang, ngay) -> "tuple[int, int] | None":
    """Ngày `ngay` nằm ở ô nào của lưới tháng `thang` (None = không có trong lưới)."""
    chi_so = (ngay.date() - ngay_dau_luoi(thang).date()).days
    hang, cot = divmod(chi_so, 7)
    return (hang, cot) if 0 <= hang < len(luoi["hang"]) else None


# ──────────────────────────── cuộn & đặt chỗ ────────────────────────────────
def cuon_xuong_day(hwnd: int, dich: int, log=print):
    l, t, r, b = nw.khung(hwnd)
    giua = ((l + r) // 2, (t + b) // 2)
    truoc = None
    for _ in range(4):
        nw.cuon_ngam(dich, giua[0], giua[1], -8, nghi=0.09)
        time.sleep(0.9)
        anh, goc, _ = nw.chup_ngam(hwnd)
        if truoc is not None and nw.khac_anh(truoc, anh) < 0.4:
            return anh, goc
        truoc = anh
    return truoc, goc


def dua_o_xuong_thap(hwnd: int, dich: int, log=print):
    """Cuộn sao cho hàng giờ/ngày nằm ở nửa dưới màn hình.

    Bắt buộc: hai bảng chọn đều bung NGƯỢC LÊN TRÊN. Ô nằm cao thì bảng tràn ra
    ngoài mép trên, nhìn không thấy mà bấm cũng trượt."""
    l, t, r, b = nw.khung(hwnd)
    giua = ((l + r) // 2, (t + b) // 2)
    cao = b - t
    for _ in range(8):
        anh, goc, _ = nw.chup_ngam(hwnd)
        o_gio, o_ngay = tim_cap_o(anh)
        if not o_ngay:
            return None, None, anh, goc
        if cao * 0.55 <= o_ngay["cy"] <= cao * 0.85:
            return o_gio, o_ngay, anh, goc
        nw.cuon_ngam(dich, giua[0], giua[1], 1)
        time.sleep(0.9)
    return o_gio, o_ngay, anh, goc


def bat_che_do_len_lich(hwnd: int, dich: int, log=print) -> bool:
    """Bật nút tròn 'Lên lịch' ở mục 'Thời điểm đăng'."""
    bam_ra_nen(hwnd, dich)          # lỡ còn bảng nào đang bung thì đóng đi đã
    anh, goc = cuon_xuong_day(hwnd, dich, log)
    if anh is None:
        log("  ❌ Không chụp được cửa sổ.")
        return False
    if tim_cap_o(anh)[1]:
        log("  (đã ở chế độ Lên lịch sẵn)")
        return True
    cham = tim_cham_chon(anh)
    if not cham:
        log("  ❌ Không thấy nút tròn 'Bây giờ' ở mục Thời điểm đăng.")
        return False
    # Nút 'Lên lịch' nằm bên phải nút 'Bây giờ'. Khoảng cách theo bề ngang chữ
    # nên đo theo cỡ chính cái nút tròn, và thử vài nấc cho chắc.
    for he_so in (6.0, 5.0, 7.0, 8.5):
        x = cham["cx"] + int(he_so * cham["rong"])
        log(f"  ▶ bấm 'Lên lịch' tại ({x},{cham['cy']})")
        nw.bam_ngam_theo_anh(dich, goc, x, cham["cy"])
        time.sleep(1.6)
        anh2, goc2, _ = nw.chup_ngam(hwnd)
        if tim_cap_o(anh2)[1]:
            log("  ✅ đã bật 'Lên lịch' (hiện ra ô giờ + ô ngày)")
            return True
        anh, goc = anh2, goc2
    log("  ❌ Bấm mấy chỗ mà không hiện ra ô giờ/ngày.")
    return False


# ───────────────────────────────── ngày ─────────────────────────────────────
def mui_ten_thang(img, tam: dict, dy: int) -> dict | None:
    """Hai mũi tên ‹ › ở hàng tiêu đề 'Tháng Chín / 2026', ngay trên lưới ngày.

    Hàng tiêu đề nằm NGOÀI tấm trắng dò được (lưới ngày), nên phải với lên phía
    trên một quãng. Trong hàng đó, cụm chữ ngoài cùng bên trái là ‹, ngoài cùng
    bên phải là ›, ở giữa là tên tháng."""
    y0 = max(0, tam["y0"] - int(3.4 * dy))
    a = np.asarray(img.convert("L"), dtype=np.int16)[y0:tam["y0"] - 2,
                                                    tam["x0"]:tam["x1"] + 1]
    rong = tam["x1"] - tam["x0"]
    hop_le = []
    for d in _dai((a < NGUONG_CHU).any(axis=1), it_nhat=4, ke_ho=8):
        cum = _dai((a[d[0]:d[1] + 1] < NGUONG_CHU).any(axis=0), it_nhat=2, ke_ho=20)
        # Hàng phải có chữ sát cả hai mép mới giống 'mũi tên - tên tháng - mũi
        # tên'. Khúc ảnh bìa tối nằm sau lưng bảng chỉ chạm mép trái nên bị loại.
        if len(cum) >= 3 and cum[0][2] < rong * 0.25 and cum[-1][2] > rong * 0.75:
            hop_le.append((d[2], cum[0][2], cum[-1][2]))
    if not hop_le:
        return None
    # Còn hai hàng cùng dạng: hàng tiêu đề tháng ở TRÊN, hàng thứ (CN T2...) ở
    # dưới — lấy hàng trên.
    y, trai, phai = min(hop_le)
    return {"truoc": (tam["x0"] + trai, y0 + y), "sau": (tam["x0"] + phai, y0 + y)}




def dat_ngay(hwnd: int, dich: int, o_ngay: dict, ngay_can: datetime,
             hom_nay: datetime, log=print) -> bool:
    log(f"▶ Chọn ngày {ngay_can:%d/%m/%Y}")
    nw.bam_ngam_theo_anh(dich, nw.khung(hwnd)[:2], o_ngay["cx"], o_ngay["cy"])
    time.sleep(1.5)
    img, goc, _ = nw.chup_ngam(hwnd)
    tam = tam_bang_bung(img, o_ngay)
    if not tam:
        log("  ❌ Không thấy bảng lịch bung ra.")
        return False
    luoi = doc_luoi_lich(img, tam)
    if not luoi:
        log("  ❌ Không đọc được lưới ngày trong bảng lịch.")
        return False
    # Bảng lịch mở ra ở tháng của NGÀY ĐANG CHỌN, không phải tháng này. Mà lịch
    # đang ở tháng tương lai thì mọi ô đều đậm, không còn dấu nào để biết chắc
    # là tháng nào. Nên: kéo về THÁNG NÀY trước (chỗ duy nhất nhận ra chắc chắn,
    # nhờ vị trí ô đậm đầu tiên = hôm nay), rồi mới đếm bước đi tới.
    thang = hom_nay
    for lan in range(4):
        if hop_voi_thang(img, luoi, thang, hom_nay):
            break
        log(f"  lịch đang ở tháng khác — lùi về tháng {thang:%m/%Y}")
        ra = doi_thang(hwnd, dich, goc, o_ngay, tam, luoi, -1, log)
        if not ra:
            return False
        img, luoi, tam = ra
    else:
        log("  ❌ Lùi mấy lần mà lịch vẫn không về tháng này.")
        return False
    log(f"  Lịch đang ở tháng {thang:%m/%Y} "
        f"({len(luoi['cot'])} cột x {len(luoi['hang'])} hàng)")

    # Ngày cần nằm ngoài lưới thì đi tới; hẹn xa từ cuối tháng có khi phải hai
    # bước (hôm nay 30/01, hẹn 01/03 chẳng hạn).
    o = o_cua_ngay(luoi, thang, ngay_can)
    for _ in range(2):
        if o:
            break
        ra = doi_thang(hwnd, dich, goc, o_ngay, tam, luoi, +1, log)
        if not ra:
            return False
        img, luoi, tam = ra
        thang = thang_ke(thang, +1)
        if not hop_voi_thang(img, luoi, thang, hom_nay):
            log(f"  ❌ Bấm › rồi mà lưới không khớp tháng {thang:%m/%Y}.")
            return False
        o = o_cua_ngay(luoi, thang, ngay_can)
    if not o:
        log(f"  ❌ Không tìm được ô cho ngày {ngay_can:%d/%m/%Y} trên lịch.")
        return False
    hang1, cot1 = o
    x, y = luoi["cot"][cot1], luoi["hang"][hang1]
    lech = (ngay_can.date() - hom_nay.date()).days
    log(f"  ▶ bấm ô cột {cot1} hàng {hang1} tại ({x},{y})  [lệch {lech} ngày]")
    nw.bam_ngam_theo_anh(dich, goc, x, y)
    time.sleep(1.5)

    img2, _, _ = nw.chup_ngam(hwnd)
    tam2 = tam_bang_bung(img2, o_ngay)
    if tam2:                                   # bảng còn mở: xem vòng đỏ đã nhảy chưa
        vong2 = vong_do_lich(img2, tam2)
        if not vong2 or abs(vong2["cx"] - x) > 20 or abs(vong2["cy"] - y) > 16:
            log(f"  ❌ Vòng đỏ không nhảy vào ô vừa bấm "
                f"({vong2 and (vong2['cx'], vong2['cy'])}).")
            return False
        log("  ✅ vòng đỏ đã nhảy đúng ô vừa bấm")
        nw.bam_ngam_theo_anh(dich, goc, o_ngay["cx"], o_ngay["cy"])   # đóng bảng
        time.sleep(0.8)
    else:
        log("  ✅ bảng lịch đã đóng sau khi chọn")
    return True


# ────────────────────────────────── giờ ─────────────────────────────────────
def _dai_cot(img, x: int, y0: int, y1: int, rong: int = 45) -> np.ndarray:
    return np.asarray(img.convert("L"), dtype=np.int16)[y0:y1, x - rong:x + rong]


def _do_truot(a: np.ndarray, b: np.ndarray, toi_da: int = 260) -> tuple[int, float]:
    """b trượt xuống bao nhiêu điểm ảnh so với a (dò bằng sai khác nhỏ nhất)."""
    tot, lech_tot = 0, 1e18
    for d in range(-toi_da, toi_da + 1):
        x, y = (a[d:], b[:len(b) - d]) if d >= 0 else (a[:d], b[-d:])
        if len(x) < 40:
            continue
        lech = float(np.abs(x - y).mean())
        if lech < lech_tot:
            tot, lech_tot = d, lech
    return tot, lech_tot


def _lan_do(hwnd: int, dich: int, goc, x: int, y: int, nac: int,
            vung: tuple[int, int, int]) -> int:
    """Lăn `nac` nấc rồi ĐO xem bánh xe trượt được mấy điểm ảnh."""
    truoc, _, _ = nw.chup_ngam(hwnd)
    nw.cuon_ngam(dich, goc[0] + x, goc[1] + y, nac, nghi=0.1)
    time.sleep(0.8)
    sau, _, _ = nw.chup_ngam(hwnd)
    d, _ = _do_truot(_dai_cot(truoc, *vung), _dai_cot(sau, *vung))
    return abs(d)


def _cao_hang_cot(img, x: int, y0: int, y1: int) -> int:
    """Chiều cao một hàng của bánh xe, đo từ khoảng cách các dòng chữ số.

    Không lấy 'độ trượt của nấc đầu' làm thước như trước: bánh xe vừa bị lăn hết
    cỡ còn trớn, nấc đầu có khi nhảy 2 hàng (đã hố: tập 116 đặt 20:00 hỏng)."""
    a = np.asarray(img.convert("L"), dtype=np.int16)[y0:y1, x - 45:x + 45]
    dong = _dai((a < NGUONG_CHU).any(axis=1), it_nhat=6, ke_ho=6)
    if len(dong) < 3:
        return 0
    kc = sorted(dong[i + 1][2] - dong[i][2] for i in range(len(dong) - 1))
    return int(kc[len(kc) // 2])


def dat_mot_cot(hwnd: int, dich: int, goc, x: int, y_giua: int, vung,
                so_nac: int, ten: str, log=print) -> bool:
    """Lăn lên ĐẦU danh sách (mục 00) rồi lăn xuống đúng `so_nac` hàng.

    Từng nấc một, đo lại sau MỖI nấc và CỘNG DỒN số hàng đã đi: nấc nào lỡ nhảy
    2 hàng thì những nấc sau bù lại, quá đích thì lăn ngược về. Đo tổng cả cụm
    là bị lừa (cột toàn chữ số na ná nhau), còn đứng im giữa chừng là chạm mép
    danh sách — dừng, không đặt bừa.

    Mốc ở ĐẦU: đo thật thì cả hai cột đều bắt đầu từ 00 (kể cả hẹn trong hôm
    nay — TikTok để chọn rồi mới báo đỏ 'phải hẹn trước ít nhất 15 phút')."""
    for _ in range(5):                          # 30 nấc: quá đủ cho 24 mục
        nw.cuon_ngam(dich, goc[0] + x, goc[1] + y_giua, 6, nghi=0.1)
    time.sleep(1.5)                             # đợi bánh xe hết trớn
    if _lan_do(hwnd, dich, goc, x, y_giua, 1, vung) != 0:
        log(f"  ❌ {ten}: lăn hết cỡ lên mà bánh xe vẫn chạy — không tin là đã "
            "về đầu danh sách.")
        return False
    if so_nac == 0:
        log(f"  {ten}: lấy ngay mục đầu (00)")
        return True

    anh, _, _ = nw.chup_ngam(hwnd)
    cao_hang = _cao_hang_cot(anh, *vung) if anh is not None else 0
    if cao_hang < 10:
        log(f"  ❌ {ten}: không đo được chiều cao hàng của bánh xe.")
        return False
    log(f"  {ten}: hàng cao {cao_hang}px, cần xuống {so_nac} hàng")
    da = 0
    for lan in range(so_nac + 8):
        con = so_nac - da
        if con == 0:
            return True
        huong = -1 if con > 0 else 1            # -1 = lăn xuống (số tăng)
        d = _lan_do(hwnd, dich, goc, x, y_giua, huong, vung)
        hang = int(round(d / cao_hang))
        if hang == 0:
            log(f"  ❌ {ten}: nấc thứ {lan + 1} không nhích ({d}px) — chạm mép "
                "danh sách sớm hơn dự tính, dừng, không đặt bừa.")
            return False
        if hang > 1:
            log(f"  {ten}: nấc thứ {lan + 1} nhảy {hang} hàng ({d}px) — sẽ bù")
        da += hang if huong == -1 else -hang
    log(f"  ❌ {ten}: lăn mãi mà chưa về đúng hàng (đang lệch {so_nac - da}).")
    return False


def dat_gio(hwnd: int, dich: int, o_gio: dict, gio: int, phut: int,
            log=print) -> bool:
    log(f"▶ Chọn giờ {gio:02d}:{phut:02d}")
    nw.bam_ngam_theo_anh(dich, nw.khung(hwnd)[:2], o_gio["cx"], o_gio["cy"])
    time.sleep(1.5)
    img, goc, _ = nw.chup_ngam(hwnd)
    tam = tam_bang_bung(img, o_gio)
    if not tam:
        log("  ❌ Không thấy bánh xe chọn giờ bung ra.")
        return False
    y_giua = (tam["y0"] + tam["y1"]) // 2
    x_gio = o_gio["x0"] + o_gio["rong"] // 4
    x_phut = o_gio["x0"] + o_gio["rong"] * 3 // 4
    vung_g = (x_gio, tam["y0"] + 10, tam["y1"] - 10)
    vung_p = (x_phut, tam["y0"] + 10, tam["y1"] - 10)
    log(f"  Bánh xe: {tam['rong']}x{tam['cao']} tại ({tam['x0']},{tam['y0']}), "
        f"hàng giữa y={y_giua}")

    if not dat_mot_cot(hwnd, dich, goc, x_gio, y_giua, vung_g,
                       gio, "cột giờ", log):
        return False
    if not dat_mot_cot(hwnd, dich, goc, x_phut, y_giua, vung_p,
                       phut // BUOC_PHUT, "cột phút", log):
        return False

    nw.bam_ngam_theo_anh(dich, goc, o_gio["cx"], o_gio["cy"])      # đóng bánh xe
    time.sleep(1.0)
    anh, _, _ = nw.chup_ngam(hwnd)
    if tam_bang_bung(anh, o_gio):
        # Bánh xe lì ra khi giờ đang không hợp lệ; bấm ra nền trang cho nó tắt,
        # kẻo nó che mất nút Lên lịch ở bước sau.
        bam_ra_nen(hwnd, dich)
        if tam_bang_bung(nw.chup_ngam(hwnd)[0], o_gio):
            log("  ⚠ Bánh xe chọn giờ vẫn mở — có thể giờ vừa đặt bị TikTok chê.")
            return False
    return True


# ───────────────────────────── bấm nút Lên lịch ─────────────────────────────
XANH_KIEM_TRA = (0, 133, 104)   # dấu ✔ + chữ 'Không phát hiện vấn đề nào'


def so_dau_xanh(img, nut: dict) -> int:
    """Mấy dòng 'Kiểm tra' đã xong — đếm cụm ✔ xanh trong thẻ ngay trên nút.

    Thẻ 'Kiểm tra' có 2 dòng (bản quyền nhạc, nội dung nhanh); dòng chưa xong
    là con quay xám 'Đang kiểm tra... khoảng 10 phút'. Bấm Lên lịch lúc còn
    đang kiểm là TikTok bật thêm một popup hỏi lại."""
    w = img.size[0]
    return len([k for k in nw.tim_nut_mau(img, XANH_KIEM_TRA, dung_sai=25, it_nhat=60)
                if k["x0"] > w * COT_TRAI and nut["cy"] - 420 < k["cy"] < nut["cy"] - 30
                and k["rong"] < 60])


def co_popup(anh_truoc, anh_sau, nut: dict) -> bool:
    """Bấm xong mà nút đỏ ở đáy vẫn còn, trang lại tối đi hoặc có tấm che
    giữa màn — là popup hỏi lại."""
    a = np.asarray(anh_truoc.convert("L"), dtype=np.int16)
    b = np.asarray(anh_sau.convert("L"), dtype=np.int16)
    toi_di = float(b.mean()) < float(a.mean()) - 12          # nền bị phủ mờ
    return toi_di and tim_nut_dang(anh_sau) is not None


def bam_nut_dang(hwnd: int, dich: int, cho_phut: float = 30.0,
                 log=print) -> bool:
    """Chờ nút đỏ 'Lên lịch' bấm được (video tải xong) rồi bấm.

    Lúc video còn đang lên, nút xám — dò màu đỏ không ra, nên cứ chờ tới khi
    thấy đỏ mới bấm. Thấy đỏ rồi còn chờ thêm cho 'Kiểm tra nội dung nhanh'
    xong (2 dấu ✔ xanh), vì bấm lúc đang kiểm là TikTok bật popup hỏi lại."""
    han = time.time() + cho_phut * 60
    lan = 0
    while time.time() < han:
        anh, goc = cuon_xuong_day(hwnd, dich, log)
        nut = tim_nut_dang(anh) if anh is not None else None
        lan += 1
        if not nut:
            log(f"  Phút {lan}: nút Lên lịch còn xám (video chưa tải xong) — "
                f"chờ thêm, tối đa {cho_phut:.0f} phút.")
            time.sleep(60)
            continue
        xanh = so_dau_xanh(anh, nut)
        if xanh < 2 and time.time() < han - 60:
            log(f"  Phút {lan}: nút đã đỏ nhưng mới {xanh}/2 mục kiểm tra xong — "
                "chờ 'Kiểm tra nội dung nhanh' cho khỏi bị hỏi lại.")
            time.sleep(60)
            continue
        log(f"▶ Bấm nút đỏ ở đáy trang tại ({nut['cx']},{nut['cy']}) "
            f"khung {nut['rong']}x{nut['cao']}  [kiểm tra xong {xanh}/2]")
        nw.bam_ngam_theo_anh(dich, goc, nut["cx"], nut["cy"])
        time.sleep(4.0)
        sau, _, _ = nw.chup_ngam(hwnd)
        if co_popup(anh, sau, nut):
            luu_anh(hwnd, "tiktok_b4_popup.png")
            log("  ⚠ TikTok bật popup sau khi bấm — CHƯA biết nút nào, không bấm "
                "mò. Xem anh_thu/tiktok_b4_popup.png và bấm tay giúp.")
            return False
        doi = nw.khac_anh(anh, sau)
        con_nut = tim_nut_dang(sau)
        log(f"  Trang đổi {doi:.1f}% sau khi bấm; nút đỏ "
            f"{'vẫn còn' if con_nut else 'đã biến mất'}")
        return doi > 5 or con_nut is None
    log("  ❌ Chờ hết giờ mà nút Lên lịch vẫn chưa bấm được.")
    return False


# ─────────────────────────────── việc chính ─────────────────────────────────
def kiem_gio(khi_nao: datetime, bay_gio: datetime | None = None) -> tuple[datetime, str]:
    """Nắn giờ hẹn về đúng cái TikTok nhận: phút bội số 5, cách hiện tại ≥15'."""
    bay_gio = bay_gio or datetime.now()
    ghi = ""
    phut = (khi_nao.minute // BUOC_PHUT) * BUOC_PHUT
    if phut != khi_nao.minute:
        ghi += f"Phút {khi_nao.minute} → {phut} (bánh xe chỉ có bội số 5). "
        khi_nao = khi_nao.replace(minute=phut)
    khi_nao = khi_nao.replace(second=0, microsecond=0)
    if khi_nao < bay_gio + timedelta(minutes=SOM_NHAT):
        return khi_nao, ghi + (f"❌ TikTok đòi hẹn sau ít nhất {SOM_NHAT} phút "
                               f"nữa (bây giờ là {bay_gio:%H:%M}).")
    if (khi_nao.date() - bay_gio.date()).days > XA_NHAT_NGAY:
        return khi_nao, ghi + (f"❌ TikTok chỉ cho hẹn trong "
                               f"{XA_NHAT_NGAY} ngày.")
    return khi_nao, ghi


def len_lich(hwnd: int, khi_nao: datetime, bam_dang: bool = False,
             log=print) -> dict:
    """Đặt lịch đăng cho video đang ở màn soạn bài.

    → {"ok": bool, "ly_do": str, "da_bam": bool, "anh": str}"""
    ket = {"ok": False, "ly_do": "", "da_bam": False, "anh": ""}
    khi_nao, ghi = kiem_gio(khi_nao)
    if ghi:
        log("  " + ghi)
    if "❌" in ghi:
        ket["ly_do"] = ghi
        return ket
    log(f"▶ Lên lịch đăng lúc {khi_nao:%d/%m/%Y %H:%M}")

    dich = nw.san_sang(hwnd, log)
    if not dich:
        ket["ly_do"] = (
            "Trang không nhận lệnh nữa: Chrome đã bỏ khung trang của thẻ này "
            "(thường do cửa sổ nằm im quá lâu, hoặc có hộp thoại kẹt ở một cửa "
            "sổ TikTok khác). Đóng hết cửa sổ TikTok rồi chạy lại dòng này — "
            "video sẽ nạp lại từ đầu.")
        return ket

    if not bat_che_do_len_lich(hwnd, dich, log):
        ket["ly_do"] = "Không bật được chế độ 'Lên lịch'."
        return ket

    o_gio, o_ngay, anh, goc = dua_o_xuong_thap(hwnd, dich, log)
    if not o_ngay:
        ket["ly_do"] = "Không thấy ô giờ/ngày sau khi bật Lên lịch."
        return ket
    log(f"  Ô giờ ({o_gio['cx']},{o_gio['cy']}), ô ngày "
        f"({o_ngay['cx']},{o_ngay['cy']})")

    if not dat_ngay(hwnd, dich, o_ngay, khi_nao, datetime.now(), log):
        ket["anh"] = str(luu_anh(hwnd, "tiktok_b3_len_lich.png"))
        ket["ly_do"] = "Không chọn được ngày."
        return ket
    if not dat_gio(hwnd, dich, o_gio, khi_nao.hour, khi_nao.minute, log):
        ket["anh"] = str(luu_anh(hwnd, "tiktok_b3_len_lich.png"))
        ket["ly_do"] = "Không chọn được giờ."
        return ket

    ket["anh"] = str(luu_anh(hwnd, "tiktok_b3_len_lich.png"))
    ket["ok"] = True
    ket["ly_do"] = f"Đã đặt lịch {khi_nao:%d/%m %H:%M}"
    if not bam_dang:
        ket["ly_do"] += " (chưa bấm nút — xem ảnh rồi tự bấm)."
        log("✅ " + ket["ly_do"])
        return ket

    if bam_nut_dang(hwnd, dich, log=log):
        ket["da_bam"] = True
        ket["ly_do"] += " và đã bấm nút Lên lịch."
    else:
        ket["ly_do"] += " nhưng KHÔNG bấm được nút Lên lịch."
        ket["ok"] = False
    ket["anh"] = str(luu_anh(hwnd, "tiktok_b3_len_lich.png"))
    log(("✅ " if ket["ok"] else "❌ ") + ket["ly_do"])
    return ket


def luu_anh(hwnd: int, ten: str) -> Path:
    ANH.mkdir(parents=True, exist_ok=True)
    p = ANH / ten
    anh, _, _ = nw.chup_ngam(hwnd)
    if anh is not None:
        anh.save(p)
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--khi-nao", required=True,
                    help='Giờ hẹn: "2026-09-23 20:30" hoặc "2026-09-23T20:30".')
    ap.add_argument("--bam-dang", action="store_true",
                    help="Bấm luôn nút Lên lịch (video SẼ tự lên kênh đúng giờ).")
    args = ap.parse_args()

    khi_nao = datetime.fromisoformat(args.khi_nao.replace(" ", "T"))
    print("═" * 72)
    print("TIKTOK — hẹn giờ đăng trên màn soạn bài ĐANG MỞ")
    print("═" * 72)
    co = nw.tim_cua_so("Chrome_WidgetWin_1", "TikTok")
    if not co:
        sys.exit("❌ Không thấy cửa sổ Chrome nào đang mở TikTok.")
    if len(co) > 1:
        print(f"⚠ Có {len(co)} cửa sổ TikTok đang mở — chỉ nên để MỘT. "
              "Hộp thoại kẹt ở cửa sổ kia sẽ khoá luôn trang này.")
    hwnd = co[0]
    print(f"Cửa sổ {hwnd} — {nw.tieu_de(hwnd)!r}\n")

    ket = len_lich(hwnd, khi_nao, bam_dang=args.bam_dang)
    print("\n" + "═" * 72)
    print(("XONG. " if ket["ok"] else "DỪNG. ") + ket["ly_do"])
    print(f"Ảnh: {ket['anh']}")
    print("═" * 72)
    sys.exit(0 if ket["ok"] else 1)


if __name__ == "__main__":
    main()
