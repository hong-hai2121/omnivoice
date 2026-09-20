# -*- coding: utf-8 -*-
"""
tiktok_chon_video.py — Đưa MỘT video vào trang tải lên của TikTok Studio.

Làm hoàn toàn bằng NHÌN MÀN HÌNH + BẤM NGẦM (xem nen_win.py): không DOM, không
cổng gỡ lỗi, không phải đóng Chrome, và không đụng tới con trỏ chuột của người
đang ngồi máy.

  1. mở https://www.tiktok.com/tiktokstudio/upload bằng Chrome Profile 83 thật,
  2. chụp ngầm cửa sổ, dò các khối MÀU ĐỎ TIKTOK (#FE2C55) để tìm nút,
  3. loại nút 'Tải lên' ở cột trái, giữ nút 'Chọn video' giữa trang,
  4. bấm ngầm vào nút → Windows bật hộp thoại chọn file,
  5. đặt cả đường dẫn vào ô tên file bằng WM_SETTEXT rồi Enter,
  6. chụp lại để xem TikTok đã chuyển sang màn soạn bài chưa.

KHÔNG bấm Đăng, KHÔNG điền caption — hai việc đó thuộc bước sau.

Hàm `nap_video()` là cửa vào cho bên ngoài (bảng điều khiển web gọi nó); chạy
thẳng file này thì `main()` chỉ là lớp dòng lệnh mỏng bọc quanh hàm đó.

Chạy:
  chay_do_nut.bat        chỉ dò nút, không bấm gì
  chay_nap_video.bat     nạp video thật
  ... hoặc: tiktok_chon_video.py [--video ĐƯỜNG_DẪN] [--chi-do] [--cho GIÂY]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))   # chạy từ thư mục nào cũng được
from dung_venv import dam_bao_venv                          # noqa: E402

dam_bao_venv(__file__)      # phải gọi TRƯỚC khi đụng tới numpy/Pillow

import argparse             # noqa: E402
import subprocess           # noqa: E402
import time                 # noqa: E402

from PIL import ImageDraw   # noqa: E402

import nen_win as nw        # noqa: E402

HERE = Path(__file__).resolve().parent
ANH = HERE / "anh_thu"
CHROME_EXE = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
PROFILE = "Profile 83"
URL = "https://www.tiktok.com/tiktokstudio/upload"
KICH_BAN = Path(r"D:\Python\omnivoice\OmniVoice\myvoice\kịch_bản")
VIDEO_MAC_DINH = (KICH_BAN /
                  "N118 - _女主九族消消乐来啊杀我啊来弄死我._哔哩哔哩_bilibili" /
                  "short.mp4")

DO_TIKTOK = (254, 44, 85)      # #FE2C55 — màu nút chính của TikTok
COT_TRAI = 0.16                # cột menu trái chiếm ~16% bề ngang → bỏ qua vùng này


def mo_trang(url: str = URL, profile: str = PROFILE, giay: float = 30) -> int:
    """Mở trang trong Chrome và trả về cửa sổ của nó.

    Ghi nhớ danh sách cửa sổ Chrome TRƯỚC khi mở rồi chỉ nhận cửa sổ mới, để
    không bám nhầm một cửa sổ TikTok còn sót từ lần chạy trước."""
    truoc = set(nw.tim_cua_so("Chrome_WidgetWin_1"))
    subprocess.Popen([str(CHROME_EXE), f"--profile-directory={profile}",
                      "--new-window", url])
    han = time.time() + giay
    while time.time() < han:
        time.sleep(0.6)
        for h in nw.tim_cua_so("Chrome_WidgetWin_1"):
            if h not in truoc and "TikTok" in nw.tieu_de(h):
                return h
    co_san = nw.tim_cua_so("Chrome_WidgetWin_1", "TikTok")
    if co_san:
        return co_san[0]
    raise RuntimeError("Không thấy cửa sổ TikTok Studio.")


def danh_dau(img, khoi_list, chon, ten: str) -> Path:
    """Vẽ khung lên ảnh: xanh = ứng viên, đỏ dày = cái được chọn."""
    ve = img.copy()
    d = ImageDraw.Draw(ve)
    for k in khoi_list:
        d.rectangle([k["x0"], k["y0"], k["x1"], k["y1"]], outline=(0, 160, 255), width=3)
    if chon:
        d.rectangle([chon["x0"] - 4, chon["y0"] - 4, chon["x1"] + 4, chon["y1"] + 4],
                    outline=(255, 0, 0), width=6)
        d.line([chon["cx"] - 20, chon["cy"], chon["cx"] + 20, chon["cy"]],
               fill=(255, 0, 0), width=4)
        d.line([chon["cx"], chon["cy"] - 20, chon["cx"], chon["cy"] + 20],
               fill=(255, 0, 0), width=4)
    ANH.mkdir(parents=True, exist_ok=True)
    p = ANH / ten
    ve.save(p)
    return p


def chon_nut_chon_video(khoi_list: list[dict], rong_anh: int) -> dict | None:
    """Trong các khối đỏ, đâu là nút 'Chọn video'?

    Trang có mấy chỗ cùng màu đỏ: nút 'Tải lên' ở cột trái, chấm đỏ báo tính năng
    mới, và nút 'Chọn video' giữa vùng nội dung. Lọc theo hai dấu hiệu bền:
      • nằm NGOÀI cột menu trái,
      • nằm gần TRỤC GIỮA của vùng nội dung nhất (nút này luôn canh giữa)."""
    bien_trai = rong_anh * COT_TRAI
    ung_vien = [k for k in khoi_list if k["x0"] > bien_trai and k["rong"] >= 120]
    if not ung_vien:
        return None
    giua = (bien_trai + rong_anh) / 2
    return min(ung_vien, key=lambda k: abs(k["cx"] - giua))


def nap_video(video: str | Path, profile: str = PROFILE, cho: int = 12,
              chi_do: bool = False, log=print) -> dict:
    """Nạp MỘT video vào trang tải lên TikTok. KHÔNG điền caption, KHÔNG đăng.

    → {"ok": bool, "ly_do": str, "hwnd": int, "anh_do_nut": str, "anh_sau": str}
    Mọi bước đều ghi qua `log` để bảng điều khiển web chiếu thẳng lên trang."""
    video = Path(video)
    ket: dict = {"ok": False, "ly_do": "", "hwnd": 0,
                 "anh_do_nut": "", "anh_sau": ""}
    if not video.exists():
        ket["ly_do"] = f"Không thấy video: {video}"
        log("❌ " + ket["ly_do"])
        return ket

    log(f"Video : {video.name}  ({video.stat().st_size/1048576:.0f} MB)")
    log(f"Thư mục: {video.parent.name}")
    chuot_dau = nw.vi_tri_chuot()

    log(f"▶ Mở trang tải lên bằng Chrome '{profile}'")
    hwnd = mo_trang(profile=profile)
    dich = nw.cua_so_nhan_chuot(hwnd)
    ket["hwnd"] = hwnd
    log(f"  Cửa sổ {hwnd} — {nw.tieu_de(hwnd)!r}")
    log(f"  Chờ {cho}s cho trang dựng xong ...")
    time.sleep(cho)

    # ── dò nút ──────────────────────────────────────────────────────────────
    img, goc, ok = nw.chup_ngam(hwnd)
    if img is None:
        ket["ly_do"] = "Không chụp được cửa sổ."
        log("❌ " + ket["ly_do"])
        return ket
    log(f"▶ Chụp ngầm: {img.size}, PrintWindow={ok}")
    khoi_list = nw.tim_nut_mau(img, DO_TIKTOK, dung_sai=34, it_nhat=1500)
    log(f"  Khối đỏ TikTok tìm được: {len(khoi_list)}")
    for i, k in enumerate(khoi_list[:6], 1):
        log(f"   {i}. tâm({k['cx']},{k['cy']}) khung {k['rong']}x{k['cao']}")

    nut = chon_nut_chon_video(khoi_list, img.size[0])
    p = danh_dau(img, khoi_list, nut, "tiktok_b1_do_nut.png")
    ket["anh_do_nut"] = str(p)
    if not nut:
        ket["ly_do"] = "Không dò ra nút 'Chọn video'."
        log(f"❌ {ket['ly_do']} Xem ảnh: {p}")
        return ket
    log(f"  → Chọn nút tâm ({nut['cx']},{nut['cy']}), khung {nut['rong']}x{nut['cao']}")

    if chi_do:
        ket.update(ok=True, ly_do="Chỉ dò nút, chưa bấm gì.")
        log("(chỉ dò: dừng ở đây)")
        return ket

    # ── bấm ngầm + hộp thoại ────────────────────────────────────────────────
    log("▶ Bấm ngầm vào nút 'Chọn video'")
    hop_cu = nw.hop_thoai_dang_mo()
    cx, cy = nw.bam_ngam_theo_anh(dich, goc, nut["cx"], nut["cy"])
    log(f"  Gửi cú bấm tới cửa sổ {dich} ở toạ độ khách ({cx},{cy})")

    hop = nw.cho_hop_thoai(15, tru=hop_cu)
    if not hop:
        ket["ly_do"] = "Không thấy hộp thoại chọn file (có thể dò sai nút)."
        log("❌ " + ket["ly_do"])
        return ket
    log(f"  Hộp thoại: {hop} — {nw.tieu_de(hop)!r}")

    log("▶ Đặt đường dẫn vào ô tên file bằng WM_SETTEXT (không gõ phím)")
    if not nw.dien_hop_thoai_mo_file(hop, str(video), log=log):
        ket["ly_do"] = "Không điền được hộp thoại."
        return ket

    for _ in range(20):
        time.sleep(0.5)
        if not nw.user32.IsWindow(hop) or not nw.user32.IsWindowVisible(hop):
            log("  ✅ Hộp thoại đã đóng — Windows nhận đường dẫn.")
            break
    else:
        log("  ⚠ Hộp thoại còn mở, có thể đường dẫn chưa được chấp nhận.")

    # ── xem TikTok đã nhận video chưa ───────────────────────────────────────
    log("▶ Chờ TikTok nạp video ...")
    img2 = img
    for i in range(12):
        time.sleep(2.5)
        anh, _, _ = nw.chup_ngam(hwnd)
        if anh is None:
            continue
        img2 = anh
        con_nut = chon_nut_chon_video(
            nw.tim_nut_mau(anh, DO_TIKTOK, dung_sai=34, it_nhat=1500), anh.size[0])
        # Nút 'Chọn video' biến mất (hoặc dời hẳn chỗ) = đã sang màn soạn bài —
        # dấu hiệu chắc hơn là đọc phần trăm bằng OCR.
        doi = con_nut is None or abs(con_nut["cy"] - nut["cy"]) > 80
        log(f"   {(i+1)*2.5:.0f}s — {'ĐÃ ĐỔI MÀN HÌNH' if doi else 'còn ở màn chọn video'}")
        if doi:
            ket["ok"] = True
            break
    else:
        ket["ly_do"] = "Hết giờ chờ mà trang chưa chuyển sang màn soạn bài."

    ket["anh_sau"] = str(danh_dau(img2, [], None, "tiktok_b1_sau_khi_nap.png"))
    chuot_cuoi = nw.vi_tri_chuot()
    log(f"  Con trỏ chuột: {chuot_dau} → {chuot_cuoi}  "
        f"{'✅ đứng yên suốt' if chuot_dau == chuot_cuoi else '⚠ đã di chuyển'}")
    if ket["ok"]:
        ket["ly_do"] = "Đã nạp video, đang ở màn soạn bài (chưa đăng)."
    return ket


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", default=str(VIDEO_MAC_DINH))
    ap.add_argument("--chi-do", action="store_true",
                    help="Chỉ dò nút và vẽ ảnh, KHÔNG bấm, KHÔNG nạp video.")
    ap.add_argument("--cho", type=int, default=12,
                    help="Số giây chờ trang dựng xong trước khi chụp.")
    args = ap.parse_args()

    print("═" * 72)
    print("TIKTOK — đưa video vào trang tải lên (nhìn màn hình, bấm ngầm)")
    print("═" * 72)

    if not args.chi_do:
        # Đếm lùi trước cú bấm THẬT: bấm nhầm nút ▶ trong VS Code thì vẫn kịp
        # Ctrl+C trước khi video bắt đầu đi lên TikTok.
        print("SẮP CHẠY THẬT — Ctrl+C để dừng")
        for n in (3, 2, 1):
            print(f"   {n} ...", flush=True)
            time.sleep(1)

    ket = nap_video(args.video, cho=args.cho, chi_do=args.chi_do)
    print("\n" + "═" * 72)
    print(("XONG. " if ket["ok"] else "DỪNG. ") + ket["ly_do"])
    print("KHÔNG bấm Đăng, KHÔNG điền caption.")
    print("═" * 72)
    sys.exit(0 if ket["ok"] else 1)


if __name__ == "__main__":
    main()
