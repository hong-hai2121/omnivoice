# -*- coding: utf-8 -*-
"""Bảng điều khiển web cho myvideo — FastAPI, giao diện TỪNG BƯỚC như myvoice/web.

Chạy:  myvideo\\chay.bat      (hoặc)
       venv\\Scripts\\python.exe -m myvideo.web.server

Một trang, xếp theo thứ tự làm việc: hàng đợi → nguồn & tuỳ chọn → bảng trạng
thái từng video (nút ⏩ chạy tiếp các bước còn thiếu, 🗑 xoá cả video trong
output) → bốn khối bước ①②③④ (bấm nút bước nào chạy từ bước đó, ô ⛓ quyết
định nối tiếp).

Hàng đợi tái dùng JobRunner của myvoice (một worker — GPU/phiên Gemini/ffmpeg
đều độc quyền, chạy song song chỉ giẫm chân nhau). Server điều khiển máy thật nên
CHỈ nghe 127.0.0.1, kèm token trong cookie — giống hệt myvoice/web/server.py.
"""

from __future__ import annotations

import json
import mimetypes
import os
import re
import secrets
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Form, Request
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               RedirectResponse, Response)
import jinja2
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

if __package__ in (None, ""):        # chạy thẳng file: python web/server.py
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    __package__ = "myvideo.web"

from . import steps as st            # noqa: E402
from . import chinhtruoc as ct       # noqa: E402  (🎛 chỉnh trước: nguồn chờ, vùng che, xem trước)
from .jobs import (q, q_dang, q_fb, tail, tail_dang, tail_fb)  # noqa: E402
from .power import watcher as power  # noqa: E402

WEB_DIR = Path(__file__).resolve().parent
BASE_DIR = WEB_DIR.parent                     # myvideo/
REPO_ROOT = BASE_DIR.parent                   # gốc repo (chứa venv)

# Windows không đăng ký sẵn .webp trong registry → mimetypes đoán ra "text/plain",
# ảnh xem trước của kiểu ĐỘNG phải trông chờ trình duyệt tự đánh hơi. Khai một
# lần ở đây là cả StaticFiles lẫn FileResponse trả đúng image/webp.
mimetypes.add_type("image/webp", ".webp")

# Kho kiểu phụ đề DÙNG CHUNG với myvoice (đã chuyển về myvoice/scripts/kieusub.py
# ngày 2026-08-16): mẫu JSON, font rời và ảnh xem trước đều nằm bên myvoice.
_MYVOICE_SCRIPTS = str(REPO_ROOT / "myvoice" / "scripts")
if _MYVOICE_SCRIPTS not in sys.path:
    sys.path.insert(0, _MYVOICE_SCRIPTS)
import kieusub                       # noqa: E402
# Cách dịch Gemini (Chrome Extension mặc định · Firefox dự phòng) DÙNG CHUNG
# với myvoice: một lựa chọn trong myvoice/taogiong_pipeline.json cho cả hai
# bảng — dich_gemini (bước ② + SEO) tự đọc từ đó, đổi ở web nào cũng là một.
import gemini_backend                # noqa: E402
import cli_tab                       # noqa: E402  (tab 🤖 CLI dịch: phần xử lý chung với myvoice)
import hieuung_giong as hu          # noqa: E402  (🔆 sáng giọng: bản nghe thử đã EQ)
# 11/11/2026: engine 🗣 VieNeu ở khối ③ (phương án thứ 2, chạy CPU trong tiến trình bước ③) —
# danh sách 25 giọng dựng sẵn + trạng thái "dùng được chưa" lấy từ module nhẹ của myvoice
# (không nạp model ở server; model nạp lúc bước ③ chạy).
import taogiong_vieneu as vn        # noqa: E402
OUTPUT_DIR = st.OUTPUT_DIR
TOKEN_FILE = WEB_DIR / "token.txt"
SETTINGS_FILE = WEB_DIR / "web_settings.json"
COOKIE = "mvid_token"

# ── Nguồn: lịch sử các nguồn đã chạy (hàng chip "Gần đây") ──────────────────
# Chọn file từ máy đi qua hộp Open của Windows (route /api/chon-tep), mở sẵn
# thư mục Tải về = st.TAIVE_DIR.
SRC_HISTORY_MAX = 15        # nhớ bấy nhiêu nguồn gần nhất

# Cài đặt của TỪNG BƯỚC (lưu lại sau mỗi lần bấm chạy):
#   Ô chung: lang (tiếng GỐC của video)
#   ① speed/model/maxchars(+maxchars_en) · ② batchchars/offline
#   ③ voice (+ voice_stars ghim ⭐)
#   ④ vesub/kieusub/subfont/submau/submauvien/subcochu/subvitri/subchars/
#      chesub/thaytieng/cpu
# maxchars giữ RIÊNG theo tiếng: chữ Hán và ký tự Anh là hai ngưỡng khác hẳn
# nhau, dùng chung một ô thì đổi ngôn ngữ lần nào cũng phải gõ lại. "0" = KHÔNG
# giới hạn, mỗi dòng SRT một câu trọn — mặc định của tiếng Trung từ 18/11/2026
# (trần 16 chữ cũ bẻ câu thành mẩu; user bảo bỏ).
# model: large-v3 từ 25/11/2026 (trước là medium) — đo trên phim Trung có nhạc nền,
# đối chiếu 43 câu phụ đề đốt sẵn: large-v3 đủ 43 câu, large-v3-turbo đủ 41 nhưng
# nhanh hơn ~2,5 lần; xem ghi chú vad_filter trong video_chamlai_srt.NGON_NGU.
DEFAULTS = dict(lang="zh", speed="0.7", model="large-v3", maxchars="0",
                maxchars_en="42", ngucanh=True, gopcau=True,
                batchchars="1200", offline=False,
                voice="", voice_stars=[], subchars="50",
                # 11/11/2026: ENGINE bước ③ — "omni" (OmniVoice nhái giọng mẫu `voice`, mặc định)
                # | "vieneu" (phương án thứ 2: VieNeu-TTS giọng dựng sẵn chạy CPU, 48 kHz).
                # giong_vieneu = 1 trong vn.GIONG_DUNG_SAN, mặc định Ngọc Huyền.
                engine="omni", giong_vieneu=vn.GIONG_MAC_DINH,
                kieusub="hopbo", subfont="",
                # Đè lên kiểu đã chọn (rỗng = giữ của kiểu): màu chữ · màu viền
                # · cỡ chữ (% cỡ gốc) · vị trí (% chiều cao từ đáy; rỗng = tự đặt).
                submau="", submauvien="", subcochu="100", subvitri="",
                # Số dòng mỗi lần hiện chữ (2 = như ảnh mẫu của kho kiểu; câu
                # dài hơn thì bước ④ tách thành nhiều lần hiện nối nhau).
                subdong="2",
                # Phóng to video NỀN bấy nhiêu % rồi cắt giữa về khung cũ
                # (rỗng/0 = giữ nguyên). Chữ vẽ sau zoom nên không phóng theo.
                zoom="",
                # ↕ vị trí dọc của hình sau khi phóng (-100…+100, 0 = giữa). Chỉ khung
                # 🎛 Chỉnh trước ghi khoá này; form chính không có ô nên không đụng tới.
                zoom_y="0",
                chesub=True, vesub=True,
                # ✂ Video dài: chia đoạn ~N phút tại chỗ hết câu rồi chạy ②③④ từng
                # đoạn và ghép (bước ① quyết định theo thời lượng; xem doan.py).
                chiadoan=True, chiadoan_phut="30",
                # 📱 kèm bản DỌC 9:16 (<B>_doc.mp4) sau bước ④ — mặc định tắt.
                xuatdoc=False,
                # 🎵 Nhạc nền nhỏ dưới tiếng chính: tên file trong myvideo/nhac
                # (rỗng = không nhạc — mặc định tắt) + âm lượng dB (âm).
                nhacnen="", nhacnen_db="-18",
                # 🔊 TAB ÂM THANH (/amthanh — lưu riêng qua /amthanh/luu, KHÔNG
                # nằm trong form chính): hai kênh chỉnh ĐỘC LẬP cho bước ④.
                # • TIẾNG GỐC video: gocdb = mức dB ("" = như cũ — thay tiếng
                #   thì TẮT hẳn, giữ tiếng gốc thì nguyên mức; thanh kéo kiểu
                #   CapCut), gocnorm = chuẩn hoá về -23 LUFS trước khi áp dB.
                # • GIỌNG ĐỌC (audio bước ③ tạo): ttsdb = chỉnh thêm dB ("0" = như cũ).
                #   (ttsnorm / chuẩn hoá −14 LUFS giọng đọc gỡ hẳn 10/11/2026.)
                # Tất cả mặc định tắt — hành vi y như trước.
                gocdb="", gocnorm=False, ttsdb="0",
                # • 🔆 SÁNG GIỌNG (23/10/2026; ô nằm ở KHỐI ③ trang chính, lưu cùng
                #   form chính /luu & /chay — 24/10 dời từ tab 🔊 về đây vì nó là cài
                #   đặt của bước TẠO GIỌNG): 0–100, trị giọng clone "ồm" — EQ giọng
                #   mẫu lúc dựng prompt + EQ audio tổng (taogiong_srt.py --sang).
                #   Mặc định 0 từ 05/11/2026 (trước 80 — user "tắt hết"); đổi mức là bước ③
                #   đọc lại toàn bộ câu. Ô 🔊 Nghe thử khối ③ phát bản mẫu đã EQ theo mức.
                sanggiong="0",
                # • 🎵 TÔNG GIỌNG (bán cung) + 🔔 TIẾNG VANG (trường độ / cường độ) +
                #   🧒 THIẾU NIÊN — mang từ myvoice sang 24/10/2026, cùng tên khoá bên
                #   đó, cũng ở khối ③; áp lên audio tổng bước ③ (taogiong_srt.py
                #   --pitch / --vang / --thieunien). Mặc định 0 = y như trước.
                pitch="0.0", vang_truong_do="0", vang_cuong_do="0", thieu_nien="0",
                # • 🔊 ÂM LƯỢNG cơ bản (dB) — mang từ myvoice sang 09/11/2026 (khoá am_luong_db
                #   cùng tên bên đó, −10…+20, bước 0,5): cộng thẳng lên audio tổng bước ③ Ở
                #   BƯỚC CUỐI (taogiong_srt.py --am-luong). Từ cùng ngày các ô tông/vang/thiếu
                #   niên/🔆/🔉 đứng riêng ngoài khối giọng mẫu (khối cài đặt chung) + ô 🎚
                #   Mẫu giọng (bảng hu.MAU_GIONG, không lưu — chỉ điền 5 ô) + 🎧 Nghe thử cài
                #   đặt trên ~30 s giọng thật (taogiong_nghethu_srt.py, route /nghethu).
                am_luong_db="0",
                # 🏷 Đóng logo / đè khung viền / nối outro của HỒ SƠ KÊNH đang
                # chọn (kenh/<tên>/logo.png · khung.png · outro.mp4; logo + khung
                # vẽ bằng myvideo/kenh_thietke.py) — mặc định tắt cả ba.
                logo_kenh=False, khung_kenh=False, outro_kenh=False,
                # Tên file logo đang chọn trong kenh/<tên>/ (hồ sơ có thể chứa
                # nhiều "logo*.png", vd hai mascot); rỗng = logo.png / cái đầu.
                logo_file="",
                # ⚠️ DÒNG LƯU Ý góc trái trên suốt video (16/11/2026, user yêu
                # cầu — mặc định BẬT, có công tắc bật/tắt ở khối ④): chữ trắng
                # nét mảnh, nhỏ vừa đọc, 2 dòng sửa được; bước ④ gửi --luuy cho
                # video_gansub_cung.py. Câu chữ user chọn kiểu NHÃN CỰC NGẮN in
                # hoa (bản câu dài đầy đủ bị chê "không hay", rồi "ngắn gọn hơn").
                luuy=True,
                luuy1="VIDEO AI · KHÔNG BẮT CHƯỚC",
                luuy2="CHỈ DÀNH CHO 18+",
                # 🧪 Nút thử cắt 60 giây TỪ PHÚT THỨ này (0/rỗng = từ đầu).
                thu60_tu="",
                auto2=True, auto3=True, auto4=True, thaytieng=True, cpu=False,
                # Khối 📤 ĐĂNG BÀI (lưu qua /dang/luu, KHÔNG nằm trong form chính):
                # `kenh` = HỒ SƠ KÊNH đang dùng (thư mục trong myvideo/kenh/ —
                # nhiều tài khoản, xem kenh_hoso.py); cài đặt YouTube + tên kênh
                # cho SEO. Hai ô TỰ ĐỘNG đăng sau bước ④ mặc định TẮT (khác
                # myvoice) — hồ sơ chưa cấu hình thì không tự ý lên lịch đi đâu
                # cả; cấu hình xong người dùng tự bật.
                kenh="",
                yt_category="22", yt_privacy="schedule", yt_kids=False, yt_ai=True,
                seo_kenh="", auto_dang=False, fb_auto=False,
                # Nguồn đã chạy, mới nhất đứng đầu — hiện thành hàng chip
                # "Gần đây" dưới ô Nguồn, bấm là điền lại, khỏi đi tìm.
                src_history=[])


def _token() -> str:
    try:
        t = TOKEN_FILE.read_text(encoding="utf-8").strip()
        if t:
            return t
    except OSError:
        pass
    t = secrets.token_urlsafe(9)
    TOKEN_FILE.write_text(t, encoding="utf-8")
    return t


TOKEN = _token()


def load_settings() -> dict:
    try:
        d = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        return {**DEFAULTS, **d} if isinstance(d, dict) else dict(DEFAULTS)
    except Exception:
        return dict(DEFAULTS)


def save_settings(data: dict) -> None:
    merged = {**load_settings(), **data}
    SETTINGS_FILE.write_text(json.dumps(merged, ensure_ascii=False, indent=2),
                             encoding="utf-8")


def _clamp(v, lo: int, hi: int, dflt: int) -> str:
    try:
        return str(max(lo, min(int(str(v).strip()), hi)))
    except (TypeError, ValueError):
        return str(dflt)


def _tran_dong(v, lo: int, hi: int, dflt: int) -> str:
    """Ô "số chữ tối đa mỗi dòng SRT": 0 (hoặc số âm) = KHÔNG giới hạn, mỗi dòng
    một câu trọn; số khác kẹp vào [lo, hi]. Không dùng _clamp vì nó kéo 0 lên lo."""
    try:
        n = int(str(v).strip())
    except (TypeError, ValueError):
        return str(dflt)
    return "0" if n <= 0 else str(max(lo, min(n, hi)))


def _hex6(v) -> str:
    """Màu người dùng chọn → 'RRGGBB' viết hoa; sai dạng/rỗng = '' (theo kiểu)."""
    m = str(v or "").strip().lstrip("#")
    return m.upper() if len(m) == 6 and all(c in "0123456789abcdefABCDEF"
                                            for c in m) else ""


def _pct(v, lo: int, hi: int) -> str:
    """Ô % để TRỐNG được (rỗng = tự đặt) — có số thì kẹp vào [lo, hi]."""
    t = str(v or "").strip()
    if not t:
        return ""
    try:
        return str(max(lo, min(int(round(float(t))), hi)))
    except ValueError:
        return ""


def _phut(v) -> str:
    """Ô "từ phút thứ…" của nút 🧪: số phút (cho lẻ 2.5), rỗng/0/rác = từ đầu."""
    t = str(v or "").strip().replace(",", ".")
    try:
        m = max(0.0, min(600.0, float(t)))
        return f"{m:g}" if m else ""
    except ValueError:
        return ""


# ── FastAPI ──────────────────────────────────────────────────────────────────
async def _tat_viec_khi_server_tat() -> None:
    """Server tắt êm (Ctrl+C ở chế độ --console, uvicorn shutdown) → dừng cả ba hàng đợi: kill
    CẢ CÂY việc đang chạy (jobs._terminate taskkill /T) để tiến trình bước ③ đang giữ OmniVoice
    trên VRAM không sống sót sau khi app tắt (user chốt 09/11/2026: tắt app = trả VRAM).
    Launcher chay.py đóng server bằng TerminateProcess nên hook này KHÔNG chạy ở đó — bên đó
    tự taskkill /T cả cây (chay._tat_cay)."""
    for r in (q, q_dang, q_fb):
        try:
            r.stop_all()
        except Exception as e:  # noqa: BLE001 — đang tắt, không để một hàng đợi lỗi chặn hàng khác
            print(f"⚠️ Không dừng được hàng đợi lúc tắt server: {e}")


app = FastAPI(title="myvideo — bảng điều khiển", on_shutdown=[_tat_viec_khi_server_tat])
# Ảnh xem trước kiểu phụ đề nằm bên myvoice (kho dùng chung) — mount TRƯỚC
# /static để đường dẫn /static/kieusub/... trong template khỏi phải đổi.
kieusub.ANH_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static/kieusub", StaticFiles(directory=str(kieusub.ANH_DIR)),
          name="kieusub")
app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))
# Tab 🤖 CLI dịch dùng LẠI template của myvoice (gpt_cli.html): tìm ở thư mục myvideo
# trước, không có mới sang myvoice — nên "base.html" mà template ấy kế thừa vẫn là khung
# trang của myvideo. cli.html bên này chỉ bọc thêm phần tự lưu.
_MYVOICE_WEB = REPO_ROOT / "myvoice" / "web"
templates.env.loader = jinja2.ChoiceLoader([
    jinja2.FileSystemLoader(str(WEB_DIR / "templates")),
    jinja2.FileSystemLoader(str(_MYVOICE_WEB / "templates"))])


def _asset_v() -> str:
    """Chống cache trình duyệt cho app.css — cùng mẹo với myvoice (mtime = phiên bản)."""
    try:
        return str(int((WEB_DIR / "static" / "app.css").stat().st_mtime))
    except Exception:
        return "0"


templates.env.globals["asset_v"] = _asset_v


# ── SERVER CHẠY BẢN CODE CŨ (20/11/2026) ─────────────────────────────────────
# Template .html được Jinja nạp lại mỗi khi sửa, còn code .py thì chỉ nạp lúc
# server khởi động. Sửa code xong mà server cũ vẫn chạy (launcher thấy "đang chạy
# sẵn" là dùng luôn) thì trang MỚI gặp code CŨ: biến thiếu → JavaScript hỏng cú
# pháp → khung 🎛 Chỉnh trước đứng im ở "⏳ Đang nạp video…" (user gặp đúng vậy).
# Chặn bằng một con dấu: giờ sửa mới nhất của các file .py mà TIẾN TRÌNH SERVER
# nạp vào (script các bước chạy thành tiến trình con, lúc nào cũng là bản mới).
#   • trang nào cũng hiện băng cảnh báo khi dấu trên đĩa mới hơn dấu lúc khởi động
#     (base.html; server quá cũ chưa có hàm này thì base.html cũng báo);
#   • /api/ping trả dấu lúc khởi động → launcher chay.py so với đĩa, lệch là tự
#     tắt server cũ rồi bật bản mới (chỉ khi hàng đợi đang rảnh).
# chay.py có bản sao hàm này (_ma_code) — hai bên phải liệt kê CÙNG bộ file.
def _ma_code() -> int:
    tep = [*WEB_DIR.glob("*.py"),
           *(BASE_DIR / n for n in ("doan.py", "kenh_hoso.py", "timvungsub.py"))]
    return max((int(p.stat().st_mtime) for p in tep if p.is_file()), default=0)


MA_KHOI_DONG = _ma_code()
LUC_KHOI_DONG = time.time()


def _code_cu() -> str:
    """Rỗng nếu server đang chạy đúng code trên đĩa; khác rỗng = câu cho băng cảnh báo."""
    moi = _ma_code()
    if moi <= MA_KHOI_DONG:
        return ""
    gio = lambda t: time.strftime("%H:%M %d/%m", time.localtime(t))   # noqa: E731
    return (f"code được sửa lúc {gio(moi)}, còn server này khởi động từ {gio(LUC_KHOI_DONG)}")


templates.env.globals["code_cu"] = _code_cu


# Launcher (chay.py) gọi route này để chắc cái đang nghe ở cổng là myvideo chứ
# không phải chương trình khác (myvoice cũng mặc định 8766) — xem _is_myvideo.
# Không cần token. "ma": dấu code lúc khởi động (xem _ma_code).
@app.get("/api/ping")
def api_ping():
    return JSONResponse({"app": "myvideo", "ma": MA_KHOI_DONG})


@app.middleware("http")
async def require_token(request: Request, call_next):
    if request.url.path.startswith("/static") or request.url.path == "/api/ping":
        return await call_next(request)
    given = request.query_params.get("token") or request.cookies.get(COOKIE, "")
    if not secrets.compare_digest(given, TOKEN):
        return HTMLResponse(
            "<h1>Cần token</h1><p>Mở bằng đường dẫn có <code>?token=…</code> "
            "in ở cửa sổ launcher lúc khởi động.</p>", status_code=401)
    response = await call_next(request)
    if request.query_params.get("token"):
        response.set_cookie(COOKIE, TOKEN, max_age=30 * 86400, httponly=True,
                            samesite="lax")
    return response


def _human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} GB"


# ── Khối Nguồn: lịch sử · dấu đã-làm ────────────────────────────────────────
# Chip "Gần đây" + nút 📂 Thêm từ máy (hộp Open của Windows — /api/chon-tep ở
# dưới). Dấu đã-làm đi kèm cả hai: chip lịch sử lẫn file vừa chọn từ hộp Open.
def _tien_do() -> dict[str, dict]:
    """Tên video (không đuôi, chữ thường) → đã chạy tới đâu trong output.

    Khoá theo TÊN GỐC (cắt bỏ tag _x…) nên nhận ra cả khi dán file nguồn lẫn
    khi dán file kết quả `_x0.7`, và không phụ thuộc tốc độ đang chọn — video
    dựng ở 0.7 rồi mà nay ô Tốc độ để 0.8 vẫn thấy dấu đã làm.
    """
    s = load_settings()
    thay = bool(s.get("thaytieng", True))
    out: dict[str, dict] = {}
    for r in st.scan_rows(thay, limit=500, vesub=bool(s.get("vesub", True))):
        ten = st.tenchinh(Path(r["base"]).name)
        xong = [r["video"] and r["srt"], r["vi"],
                *([r["audio"]] if thay else []), r["sub"]]
        done = sum(1 for x in xong if x)
        p = {"lam": True, "xong": all(xong), "done": done,
             "buoc": f"{done}/{len(xong)}"}
        # Cùng một video có thể có nhiều gốc (dựng 0.7 rồi dựng lại 0.8):
        # giữ cái chạy được xa nhất.
        if p["done"] > out.get(ten, {}).get("done", -1):
            out[ten] = p
    return out


def _danh_dau(src: str, prog: dict[str, dict]) -> dict:
    """Nhãn "đã làm" cho một nguồn — nguồn chưa chạy bao giờ thì không có nhãn.

    Nguồn là LINK Bilibili thì tính theo tên file nó sẽ tải về (<mã BV>.mp4) —
    chip lịch sử của link vẫn hiện đúng video đó đã chạy tới bước nào."""
    ten = (st.ten_tai_bilibili(src) if st.la_link_bilibili(src)
           else Path(src).stem)
    return prog.get(st.tenchinh(ten)) or {"lam": False, "xong": False,
                                          "done": 0, "buoc": ""}


def _src_label(src: str) -> str:
    """Nhãn ngắn cho chip: chỉ tên file (link Bilibili → mã BV), bỏ phần dài."""
    if st.la_link_bilibili(src):
        return f"🔗 Bilibili {st.ten_tai_bilibili(src) or '?'}"
    return Path(src).name or src


def source_history() -> list[dict]:
    """Nguồn đã chạy, mới nhất trước — `full` để điền vào ô, `label` để hiện."""
    raw = load_settings().get("src_history") or []
    prog = _tien_do()
    return [{"full": s, "label": _src_label(s), **_danh_dau(s, prog)}
            for s in raw if isinstance(s, str) and s.strip()]


def remember_sources(lines: list[str]) -> None:
    """Đẩy các nguồn vừa chạy lên đầu lịch sử (bỏ trùng, cắt bớt phần cũ)."""
    old = [s for s in (load_settings().get("src_history") or []) if isinstance(s, str)]
    merged: list[str] = []
    for s in [*reversed([l.strip() for l in lines if l.strip()]), *old]:
        if s not in merged:
            merged.append(s)
    save_settings({"src_history": merged[:SRC_HISTORY_MAX]})


def _list_output(limit: int = 15) -> list[dict]:
    """File mới nhất trong output — mỗi video một thư mục con nên quét sâu 1 cấp,
    tên hiện dạng '<thư mục>/<file>' (file phẳng cũ vẫn hiện tên trần)."""
    items = []
    try:
        for p in OUTPUT_DIR.iterdir():
            if p.is_file():
                items.append(p)
            elif p.is_dir():
                try:
                    items.extend(c for c in p.iterdir() if c.is_file())
                except OSError:
                    pass
    except Exception:
        return []
    items.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [{"name": p.relative_to(OUTPUT_DIR).as_posix(),
             "size": _human_size(p.stat().st_size),
             "when": time.strftime("%d/%m %H:%M", time.localtime(p.stat().st_mtime))}
            for p in items[:limit]]


# ── 🚨 Soát chất lượng từng video (cột "Soát" của bảng Kết quả) ──────────────
# Đọc _vi.srt (câu còn sót chữ Hán = dịch thiếu) + _vi_timeline.json (câu bị
# xếp lệch xa mốc SRT = giọng đè nhau phải dời). Bảng tự vẽ lại 5 giây/lần nên
# cache theo mtime — file không đổi thì không đọc lại.
#
# HAI BẬC báo — đo trên video thật: giọng Việt dài hơn khe tiếng gốc nên vài
# giây lệch là chuyện THƯỜNG của bộ xếp chống đè, video nào cũng ⚠️ thì cột
# thành vô dụng. Sót chữ Hán hoặc lệch quá 10s mới ⚠️ đỏ; lệch 3-10s chỉ ghi
# chú mờ (di chuột đọc chi tiết, bấm 🎞 xem timeline).
_HAN_RE = re.compile(r"[一-鿿㐀-䶿]")
_LECH_MS = 3000                 # từ mức này tính là "có lệch" (ghi chú mờ)
_LECH_NANG_MS = 10000           # lệch quá 10 giây = giọng lạc hẳn khỏi hình → ⚠️
_SOAT_CACHE: dict[str, tuple[tuple, dict]] = {}


def _soat(base: str) -> dict:
    """→ {"han", "lech", "lech_max", "loi": [nặng → ⚠️], "nhe": [ghi chú mờ]}."""
    srt = OUTPUT_DIR / f"{base}_vi.srt"
    tl = OUTPUT_DIR / f"{base}_vi_timeline.json"

    def _mt(p):
        try:
            return p.stat().st_mtime
        except OSError:
            return 0.0

    key = (_mt(srt), _mt(tl))
    hit = _SOAT_CACHE.get(base)
    if hit and hit[0] == key:
        return hit[1]

    han = 0
    if key[0]:
        try:
            for block in re.split(r"\n\s*\n", srt.read_text(encoding="utf-8-sig")):
                text = "\n".join(l for l in block.splitlines()
                                 if l.strip() and not l.strip().isdigit()
                                 and "-->" not in l)
                if len(_HAN_RE.findall(text)) >= 2:   # 1 chữ lẻ có thể là tên riêng
                    han += 1
        except OSError:
            pass
    lech = lech_max = 0
    if key[1]:
        try:
            cues = json.loads(tl.read_text(encoding="utf-8")).get("cues", [])
            do_lech = [abs(int(c.get("shift_ms", 0))) for c in cues]
            lech = sum(1 for x in do_lech if x > _LECH_MS)
            lech_max = max(do_lech, default=0)
        except (OSError, ValueError):
            pass
    loi, nhe = [], []
    if han:
        loi.append(f"{han} câu còn sót chữ Hán trong bản dịch — sửa {base}_vi.srt "
                   "rồi chạy lại ③④")
    ghi_lech = (f"{lech} câu xếp lệch mốc quá {_LECH_MS // 1000}s "
                f"(xa nhất {lech_max / 1000:.1f}s) — bấm 🎞 xem timeline")
    if lech_max > _LECH_NANG_MS:
        loi.append(ghi_lech)
    elif lech:
        nhe.append(ghi_lech)
    out = {"han": han, "lech": lech, "lech_max": lech_max, "loi": loi, "nhe": nhe}
    _SOAT_CACHE[base] = (key, out)
    return out


def _ten_nguon(src: str) -> str:
    """Tên gốc viết thường của một nguồn (file → tên file bỏ đuôi và tag _x…,
    link Bilibili → mã BV) — khoá để nối nguồn với hàng của nó trong output."""
    ten = st.ten_tai_bilibili(src) if st.la_link_bilibili(src) else Path(src).stem
    return st.tenchinh(ten or "")


def _tep_nguon(src: str) -> Path:
    """File trên đĩa của một nguồn — link Bilibili thì là chỗ nó SẼ tải về
    (Downloads/<mã BV>.mp4); file có thật hay chưa do nơi gọi tự kiểm."""
    if st.la_link_bilibili(src):
        return st.TAIVE_DIR / f"{st.ten_tai_bilibili(src) or 'video'}.mp4"
    return Path(src)


def _hang_cho(rows: list[dict], s: dict) -> list[dict]:
    """🎛 NGUỒN CHỜ: file/link đã nạp vào ô Nguồn nhưng chưa có gì trong output →
    vẫn hiện một hàng ở bảng Kết quả (tick được để 🎛 Chỉnh trước)."""
    co = {st.tenchinh(Path(r["base"]).name) for r in rows}
    out: list[dict] = []
    for src in s.get("cho_chinh") or []:
        if not isinstance(src, str) or not src.strip():
            continue
        khoa = _ten_nguon(src)
        if not khoa or khoa in co or any(c["khoa"] == khoa for c in out):
            continue
        link = st.la_link_bilibili(src)
        out.append({"id": "src:" + src, "src": src, "khoa": khoa, "link": link,
                    "ten": _src_label(src), "co_tep": _tep_nguon(src).is_file()})
    return out


# ── 🧪 BẢN THỬ không phải một video của bảng Kết quả (24/11/2026) ─────────────
# Gốc của bản thử cũng mang tag _x… ("<tên>_thu3p/<tên>_thu3p_x0.7") nên scan_rows
# trả nó về như mọi video — bảng hiện thêm một hàng trùng tên với video thật (ô tên
# cắt chữ nên không thấy đuôi _thu3p), bước ④ luôn "—". User: "sao video thử lại có ở
# trong này". Từ nay:
#   • bản thử 3 PHÚT của 🎛 Chỉnh trước (ct.THU_DUOI) KHÔNG thành hàng — nó thuộc về
#     video của nó (hàng thật hoặc hàng nguồn chờ), xem lại trong khung 🎛. Chỉ khi
#     video chưa có hàng nào mới hiện MỘT hàng xám ghi rõ "chỉ có bản thử" (để còn
#     tick xem và 🗑 dọn được, không thành file mồ côi vô hình).
#   • bản nháp 60 GIÂY (nút 🧪 Thử 60 giây, đủ 4 bước) vẫn là một hàng — bảng là chỗ
#     duy nhất mở được nó — nhưng mang nhãn 🧪 trước tên.
# scan_rows giữ nguyên (khung 🎛 tìm bản thử qua nó); chỉ bảng này lọc.
_THU60 = "_thu60"


def _la_thu(base: str) -> str:
    """Gốc là BẢN THỬ → đuôi của nó (ct.THU_DUOI | "_thu60"); video thật → ""."""
    ten = st.tenchinh(Path(base).name)
    return next((d for d in (ct.THU_DUOI, _THU60) if ten.endswith(d)), "")


def _tep_thu_ten(ten: str) -> list[Path]:
    """Mọi thứ của bản thử 3 phút thuộc video tên `ten` (tên gốc, không tag): clip đã
    cắt output/<tên>_thu3p.mp4 + thư mục kết quả output/<tên>_thu3p/ (mọi tốc độ)."""
    if not ten or ten != Path(ten).name:             # chỉ nhận tên trần (chặn ../)
        return []
    return [p for p in (OUTPUT_DIR / f"{ten}{ct.THU_DUOI}.mp4",
                        OUTPUT_DIR / f"{ten}{ct.THU_DUOI}") if p.exists()]


def _tep_thu(base: str) -> list[Path]:
    """Như _tep_thu_ten, cho một GỐC trong output (gốc thật hay gốc thử đều được)."""
    return _tep_thu_ten(Path(base).name[:len(_ct_khoa(base))])   # giữ nguyên hoa/thường


# ── 🗑 XOÁ Ở BẢNG = DỌN SẠCH video đó khỏi output (24/11/2026) ────────────────
# User: "khi xoá ở đây là xoá tệp khỏi output luôn và cái chỉnh trước cũng mất video
# liên quan đi hết". Bấm xoá một hàng thì KHÔNG còn gì của video đó trong output, và
# hàng không quay lại dưới dạng khác (nguồn chờ / chỉ có bản thử):
#   • file của gốc + file từng đoạn của video dài (st.files_of);
#   • video không còn gốc thật nào khác (tốc độ khác) → bản thử 3 phút + clip đã cắt
#     của 🎛 Chỉnh trước, bản xem trước thu nhỏ, và dòng nguồn chờ của nó;
#   • khung 🎛 đang mở đúng video đó tự đóng (trang nghe sự kiện mvid:daxoa).
# Vẫn chỉ đưa vào Thùng rác; FILE NGUỒN (Downloads, ổ khác) không bao giờ bị đụng;
# dải che đã chỉnh tay (chinh_truoc.json) là cài đặt, giữ lại cho lượt chạy sau.
def _tep_xoa(base: str) -> tuple[list[Path], bool]:
    """→ (mọi thứ nút 🗑 của hàng `base` phải dọn, video có HẾT HẲN khỏi output không)."""
    loai = _la_thu(base)
    if loai == ct.THU_DUOI:                          # hàng "chỉ có bản thử"
        return _tep_thu(base), True
    files = st.files_of(base)
    khoa = st.tenchinh(Path(base).name)
    con = any(r["base"] != base and st.tenchinh(Path(r["base"]).name) == khoa
              for r in st.scan_rows(limit=500))      # còn gốc khác của CHÍNH video này
    if con:
        return files, False
    them = _tep_thu(base)
    if loai == _THU60:                               # clip 60 giây đã cắt, nằm ngoài thư mục
        them.append(OUTPUT_DIR / f"{Path(base).name[:len(khoa)]}.mp4")
    return files + [p for p in them if p.exists() and p not in files], True


def _quen_video(khoa: str) -> None:
    """Video `khoa` vừa bị dọn khỏi output → 🎛 Chỉnh trước quên theo: bỏ dòng nguồn chờ
    của nó (kẻo hàng vừa xoá hiện lại thành "⏳ mới nạp") và bản xem trước thu nhỏ của
    file nguồn. (Bản xem trước của clip thử phải bỏ TRƯỚC khi clip vào Thùng rác — nơi
    gọi tự làm, xem ct.bo_xem_truoc.)"""
    cu = [x for x in (load_settings().get("cho_chinh") or []) if isinstance(x, str)]
    cua_no = [x for x in cu if _ten_nguon(x) == khoa]
    for x in cua_no:
        ct.bo_xem_truoc(_tep_nguon(x))
    if cua_no:
        save_settings({"cho_chinh": [x for x in cu if x not in cua_no]})


# ── ▶ XEM VIDEO / 🔁 RENDER LẠI ở cột ④ của bảng (25/11/2026) ─────────────────
# User: "có thêm 1 nút mở video hoàn thành lên xem và có 1 nút render lại theo cài đặt
# mới". Bước ④ ghi THẲNG vào <gốc>_sub.mp4 (ffmpeg -y, không qua file tạm) nên lúc nó
# đang chạy thì video hoàn thành cũ đang bị ghi đè dở — mở ra là file hỏng, bấm render
# lần nữa là xếp trùng một lượt dựng nửa tiếng. Bảng vì thế phải biết bước ④ của từng
# hàng đang ở đâu trong hàng đợi.
def _viec_cua(j: dict, base: str) -> bool:
    """Việc `j` của hàng đợi (as_dict) có phải của gốc `base` không — theo phần đầu tiêu
    đề: nút của bảng ghi cả gốc ("<thư mục>/<tên>_x0.8 — …"), ▶ Chạy tất cả / nút từng
    bước ghi tên trần ("<tên>_x0.8 — …"), 🧪 thử 60s ghi tên FILE NGUỒN."""
    dau = j["title"].split(" — ", 1)[0]
    ten = Path(base).name
    if dau in (base, ten):
        return True
    return ("🧪 thử 60s" in j["title"]
            and st.tenchinh(ten) == (Path(dau).stem + _THU60).lower())


def _dang_dung(base: str, tt: dict) -> str:
    """Bước ④ của `base` trong hàng đợi `tt` (q.state()): "chay" = đang dựng, file thành
    phẩm đang bị ghi đè · "cho" = đã xếp nhưng chưa tới bước ④ · "" = không có."""
    def buoc4(j: dict) -> int:
        return next((i for i, nhan in enumerate(j["steps"]) if nhan.startswith("④")), -1)

    cur = tt.get("current")
    if cur and _viec_cua(cur, base) and buoc4(cur) >= 0:
        return "chay" if cur["step_index"] >= buoc4(cur) else "cho"
    if any(_viec_cua(j, base) and buoc4(j) >= 0 for j in tt.get("pending") or []):
        return "cho"
    return ""


def _bang_ctx() -> dict:
    s = load_settings()
    tt = q.state()
    rows, thu = [], {}
    for r in st.scan_rows(bool(s.get("thaytieng", True)),
                          vesub=bool(s.get("vesub", True))):
        loai = _la_thu(r["base"])
        if loai == ct.THU_DUOI:
            thu.setdefault(_ct_khoa(r["base"]), r)   # mới nhất trước → giữ bản đầu
            continue
        r["soat"] = _soat(r["base"])
        r["id"] = "base:" + r["base"]          # giá trị ô tick ở đầu hàng
        r["thu60"] = loai == _THU60
        r["dung"] = _dang_dung(r["base"], tt)  # "chay" | "cho" | "" — cột ④ (xem trên)
        rows.append(r)
    cho = _hang_cho(rows, s)
    for c in cho:
        c["co_thu"] = c["khoa"] in thu
        # ✕ của hàng chờ sẽ đưa những thứ này vào Thùng rác (clip đã cắt / thư mục thử)
        # → nút phải hỏi lại; chưa có gì trong output thì ✕ chỉ bỏ dòng, khỏi hỏi.
        c["tep_thu"] = bool(_tep_thu_ten(_tep_nguon(c["src"]).stem))
    da_co = ({st.tenchinh(Path(r["base"]).name) for r in rows}
             | {c["khoa"] for c in cho})
    chi_thu = [{"id": "base:" + r["base"], "ten": Path(r["base"]).name[:len(k)], "clip": False}
               for k, r in thu.items() if k not in da_co]
    # Clip 3 phút đã cắt (output/<tên>_thu3p.mp4 — cắt ngay lúc mở khung 🎛) mà video
    # không còn hàng nào: cũng phải hiện, kẻo nằm lại output mà không có chỗ bấm xoá.
    duoi = f"{ct.THU_DUOI}.mp4"
    try:
        clip_le = sorted(p.name[:-len(duoi)] for p in OUTPUT_DIR.iterdir()
                         if p.is_file() and p.name.lower().endswith(duoi))
    except OSError:
        clip_le = []
    chi_thu += [{"id": "", "ten": ten, "clip": True} for ten in clip_le
                if ten and ten.lower() not in da_co and ten.lower() not in thu]
    return {"rows": rows, "cho": cho, "chi_thu": chi_thu,
            "files": _list_output(), "output_dir": str(OUTPUT_DIR)}


# ── 📊 VRAM còn trống (card 8GB dùng chung với Chrome — thấy sắp cạn thì khoan
# xếp mẻ mới, kẻo model tràn sang RAM chậm gấp chục lần). Hỏi nvidia-smi tối đa
# 5 giây/lần dù khối hàng đợi vẽ lại 2 giây/lần; máy không có nvidia thì thôi. #
_VRAM_CACHE: dict = {"t": 0.0, "v": None}


def _vram() -> dict | None:
    now = time.time()
    if now - _VRAM_CACHE["t"] < 5:
        return _VRAM_CACHE["v"]
    v = None
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3,
            creationflags=0x08000000 if sys.platform == "win32" else 0)
        used, total = (int(x) for x in r.stdout.strip().splitlines()[0].split(","))
        v = {"used": used, "total": total, "free": total - used,
             "pct": round(100 * used / total),
             "warn": total - used < 1500}       # dưới ~1.5GB là sắp tràn
    except Exception:
        v = None
    _VRAM_CACHE.update(t=now, v=v)
    return v


def _home(loi: str = "") -> RedirectResponse:
    url = "/?loi=" + quote(loi) if loi else "/"
    return RedirectResponse(url=url, status_code=303)


def _tra(request: Request, loi: str = "", ok: str = "",
         luu: bool = False, chay: bool = False, bao: dict | None = None):
    """Trả lời cho MỌI nút bấm: qua htmx thì cập nhật TẠI CHỖ (khối hàng đợi +
    bảng kết quả + lời nhắn góc phải), KHÔNG tải lại trang — khỏi mất chỗ đang
    cuộn, ô Nguồn đang gõ dở và các tuỳ chọn vừa chỉnh. Không có JS thì rơi về
    chuyển hướng như cũ.

    luu=True (đường /luu và /chay — hai đường DUY NHẤT ghi xuống đĩa) mà không
    lỗi thì kèm HX-Trigger "mvid:xong" để trang tự dọn: bỏ dấu “chưa lưu”, và
    sau lượt CHẠY thì bỏ tick hai ô “làm lại” (hai ô đó chỉ có giá trị cho đúng
    lượt vừa bấm — trước đây trang tải lại nên tự sạch, nay phải tự bỏ).

    bao = sự kiện riêng gửi kèm cho trang ({"mvid:daxoa": {"khoa": …}} sau một lượt 🗑
    — khung 🎛 đang mở đúng video đó tự đóng). json.dumps mặc định chỉ ra ASCII nên
    tên video chữ Hán vẫn nằm gọn trong header.
    """
    if not request.headers.get("hx-request"):
        return _home(loi)
    su_kien = {**({"mvid:xong": {"chay": chay}} if luu and not loi else {}),
               **(bao or {})}
    headers = {"HX-Trigger": json.dumps(su_kien)} if su_kien else {}
    # 📤 Đăng bài và ⏱ Hàng đợi giờ là TAB RIÊNG: chỉ vẽ lại các khối CÓ MẶT
    # trên trang vừa bấm nút (htmx gửi HX-Current-URL) — swap vào id không tồn
    # tại là htmx la lỗi ở console, mà dựng context thừa cũng phí (quét sổ
    # Facebook cho một nút bấm bên trang quy trình chẳng hạn). Khối hàng đợi
    # LUÔN trả (trang nào cũng có #queue — hai trang kia là mỏ neo ẩn).
    url = request.headers.get("hx-current-url") or ""
    tren_dang, tren_hangdoi = "/dangbai" in url, "/hangdoi" in url
    # Tab 🔊 Âm thanh như tab ⏱: ngoài hàng đợi + lời nhắn không cần OOB nào.
    tren_amthanh = "/amthanh" in url
    ctx = {"loi": loi, "ok": ok, "tren_dang": tren_dang,
           "tren_hangdoi": tren_hangdoi, "tren_amthanh": tren_amthanh,
           **_queue_ctx()}
    if tren_dang:
        ctx.update(_dang_ctx())
    elif not (tren_hangdoi or tren_amthanh):
        ctx.update(**_bang_ctx(), **_nguon_ctx())
    return templates.TemplateResponse(request, "_capnhat.html", ctx,
                                      headers=headers)


def _nguon_ctx() -> dict:
    """Hàng chip "Gần đây" — gửi kèm MỌI lượt trả lời để nguồn vừa chạy hiện ra
    ngay (trang không tải lại) và dấu ✓/◐ chạy theo tiến độ."""
    return {"src_history": source_history()}


# ── Trang chính + partial ────────────────────────────────────────────────────
def _queue_ctx() -> dict:
    return {"q": q.state(), "loglines": tail.tail(18), "power": power.state(),
            "vram": _vram()}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    s = load_settings()
    # Giọng ⭐ đã ghim đứng đầu danh sách, phần còn lại theo thứ tự tên.
    vs = st.list_voices()
    stars = [v for v in s.get("voice_stars", []) if v in vs]
    # data-i = chỗ đứng theo tên (chưa ghim). Nút ⭐ giờ xếp lại danh sách ngay
    # trên trang, nên lúc BỎ ghim còn biết trả giọng về đúng chỗ cũ.
    tt = {v: i for i, v in enumerate(vs)}
    # 🏷 Logo trong hồ sơ kênh đang chọn: hồ sơ có thể chứa nhiều "logo*.png"
    # (vd hai mascot) — ô chọn + ảnh xem trước ở khối ④; cái đang dùng theo đúng
    # luật của kenh_hoso.logo_path (chọn → logo.png → cái đầu).
    kenh_ht = kh.hien_tai()
    logo_ht = kh.logo_path(kenh_ht, s.get("logo_file") or "")
    return templates.TemplateResponse(request, "index.html", {
        "settings": s,
        # Cách dịch Gemini đã lưu (dùng chung với myvoice) — cho hai ô ở khối ②.
        "gemini_backend": gemini_backend.saved_backend(),
        "voices": [{"ten": v, "i": tt[v], "sao": v in stars}
                   for v in stars + [v for v in vs if v not in stars]],
        "voice_stars": stars,
        # 🗣 VieNeu (11/11/2026): 25 giọng dựng sẵn + dùng được chưa (thiếu gì thì mo_ta nói).
        "vieneu_giong": list(vn.GIONG_DUNG_SAN),
        "vieneu_san_sang": vn.trang_thai()["san_sang"],
        "vieneu_mo_ta": vn.trang_thai()["mo_ta"],
        # 🎚 Mẫu giọng cài sẵn (09/11/2026, bảng hu.MAU_GIONG chung với myvoice): chọn một
        # mẫu là JS điền tông + 4 bộ lọc; server không đọc ô này. + dòng mẫu 🎧 đang lưu.
        "mau_giong": hu.MAU_GIONG,
        "mau_giong_mota": [(t, hu.MAU_MO_TA.get(t, "")) for t in hu.mau_ten()],
        "mau_tuy_chinh": hu.MAU_TUY_CHINH,
        "nghethu": _nghethu_nhan(),
        "logos": kh.logos(kenh_ht),
        "logo_chon": logo_ht.name if logo_ht else "",
        # 🎵 Kho nhạc nền myvideo/nhac — cho ô chọn ở khối ④.
        "nhacs": st.list_nhac(),
        # Kho kiểu + kho font đều kèm ẢNH XEM TRƯỚC (kieusub.py vẽ bằng đúng
        # libass sẽ burn) — thẻ ảnh chọn kiểu/font giống hệt myvoice.
        "sub_fonts": kieusub.danh_sach_font_web(),
        "kieusubs": kieusub.danh_sach_web(),
        "loi": request.query_params.get("loi", ""),
        **_bang_ctx(),
        **_nguon_ctx(),
    })


@app.get("/dangbai", response_class=HTMLResponse)
async def dangbai_view(request: Request):
    """TAB 📤 Đăng bài — tách khỏi trang quy trình vì khâu này nằm NGOÀI vòng
    lặp 4 bước (dựng xong cả mẻ mới ngó tới). _dang_ctx đã kèm settings."""
    return templates.TemplateResponse(request, "dangbai.html", {
        "trang": "dang",
        "loi": request.query_params.get("loi", ""),
        **_dang_ctx(),
    })


@app.get("/amthanh", response_class=HTMLResponse)
async def amthanh_view(request: Request):
    """TAB 🔊 Âm thanh — HAI KÊNH chỉnh độc lập cho bước ④: tiếng gốc của
    video và giọng đọc code tạo (bước ③). Lưu riêng qua /amthanh/luu nên
    form chính (/luu, /chay) không đụng tới các khoá này."""
    return templates.TemplateResponse(request, "amthanh.html", {
        "settings": load_settings(),
        "trang": "amthanh",
        "loi": request.query_params.get("loi", ""),
    })


# ── TAB 🤖 CLI dịch (26/11/2026) — GPT CLI + Gemini CLI trong MỘT tab, y tab bên myvoice ──
# Cùng template (myvoice/web/templates/gpt_cli.html), cùng JS (cli_tab.js), cùng phần xử
# lý (scripts/cli_tab.py), cùng bộ nhắn thử (myvoice/web/gptcli_test.py) và CÙNG tên route
# nên không viết lại gì: ô ⭐ Dịch mặc định · thẻ trạng thái · model · nhắn thử.
def _nap_cli_thu():
    """Bộ nhắn thử của myvoice, nạp theo đường dẫn file (myvoice.web không phải gói
    import được từ server này; file ấy tự đứng một mình)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "omni_cli_thu", str(_MYVOICE_WEB / "gptcli_test.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cli_thu = _nap_cli_thu()


@app.get("/cli", response_class=HTMLResponse)
@app.get("/gpt-cli", response_class=HTMLResponse)
@app.get("/gemini-cli", response_class=HTMLResponse)
def cli_view(request: Request):
    """/cli mở CLI đang là cách dịch mặc định; /gpt-cli, /gemini-cli mở đúng CLI đó."""
    nha = {"/gpt-cli": "gpt", "/gemini-cli": "gemini"}.get(
        request.url.path, cli_tab.nha_mac_dinh())
    return templates.TemplateResponse(request, "cli.html", {
        "settings": load_settings(), "trang": "cli", "cli_js": "/cli-tab.js",
        "sample_text": cli_thu.SAMPLE_TEXT, **cli_tab.ngu_canh(nha)})


@app.get("/cli-tab.js")
def cli_tab_js():
    return FileResponse(str(cli_tab.JS_FILE), media_type="text/javascript")


@app.get("/api/gptcli-info")
def api_cli_info(nha: str = "gpt"):
    return cli_tab.thong_tin(nha)


@app.post("/gpt-cli/luu")
async def cli_luu(request: Request):
    """Tự lưu của tab: model / mức cố gắng của CLI đang xem + ô ⭐ Dịch mặc định."""
    nha, tom_tat = cli_tab.luu(await request.form())
    print(f"💾 Tab CLI: {tom_tat}.", flush=True)
    if request.headers.get("hx-request"):
        return HTMLResponse(f'<span class="savenote">✓ Đã lưu — {tom_tat}</span>')
    return RedirectResponse("/gemini-cli" if nha == "gemini" else "/gpt-cli", status_code=303)


@app.get("/api/gptcli-test")
def api_cli_test(nha: str = "gpt"):
    return cli_thu.testers[cli_tab.chuan_nha(nha)].state()


@app.post("/api/gptcli-test/chay")
async def api_cli_test_chay(request: Request):
    """Một lượt thử: mode=check (tìm binary + đăng nhập + lệnh ngắn) hoặc send (gửi `text`)."""
    form = await request.form()
    try:
        cli_thu.testers[cli_tab.chuan_nha(form.get("nha"))].start(
            str(form.get("mode") or ""), str(form.get("text") or ""),
            full_prefix=bool(form.get("full_prefix")))
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except RuntimeError as e:
        return JSONResponse({"error": str(e)}, status_code=409)
    return {"ok": True}


@app.post("/amthanh/luu")
async def amthanh_luu(request: Request):
    """Lưu tab 🔊 — CHỈ bốn khoá âm thanh (save_settings trộn, phần khác giữ)."""
    g = (await request.form()).get
    save_settings({
        # Thanh tiếng gốc gửi -21…+20 (vạch 0 ở giữa, trái giảm phải tăng);
        # -21 (nấc tận trái) = tắt/như cũ → lưu rỗng.
        "gocdb": "" if int(_clamp(g("gocdb"), -21, 20, -21)) <= -21
                 else _clamp(g("gocdb"), -20, 20, 0),
        "gocnorm": bool(g("gocnorm")),
        # Giọng đọc: 0 = như cũ; kẹp -20…+20 dB (tăng có chặn đỉnh bên ④).
        "ttsdb": _clamp(g("ttsdb"), -20, 20, 0),
    })
    return _tra(request, ok="Đã lưu cài đặt âm thanh — ăn vào lượt dựng ④ kế tiếp",
                luu=True)


@app.get("/hangdoi", response_class=HTMLResponse)
async def hangdoi_view(request: Request):
    """TAB ⏱ Hàng đợi — nguyên khối "Việc đang chạy" của trang chính dời sang,
    không đổi logic nào (vẫn _queuepanel.html tự làm mới 2 giây/lần)."""
    return templates.TemplateResponse(request, "hangdoi.html", {
        "settings": load_settings(),      # base.html cần settings.lang
        "trang": "hangdoi",
        "loi": request.query_params.get("loi", ""),
        **_queue_ctx(),
    })


# ── 📂 Thêm từ máy: hộp chọn file CỦA WINDOWS, mở sẵn thư mục Tải về ──────────
# 15/11/2026 (user yêu cầu): bỏ bảng chọn file tự vẽ trong trang (liệt kê
# Downloads/Videos/output) — bấm nút là mở thẳng hộp Open của Windows ở
# Downloads. Trình duyệt không cho trang biết đường dẫn thật của file đã chọn
# mà quy trình cần đường dẫn thật, nên SERVER mở hộp chọn (nó chạy ngay trên
# máy này) qua tiến trình con web/chon_tep.py rồi trả đường dẫn về cho trang.
CHON_TEP_SCRIPT = WEB_DIR / "chon_tep.py"
_CHON_TEP_LOCK = threading.Lock()       # mỗi lúc chỉ MỘT hộp chọn


def _hoi_chon_tep() -> list[str]:
    """Mở hộp chọn file và CHỜ người dùng chọn xong → đường dẫn đã chọn ([] =
    bấm Cancel). Không đặt timeout: chọn file bao lâu là việc của người dùng."""
    thu_muc = st.TAIVE_DIR if st.TAIVE_DIR.is_dir() else Path.home()
    r = subprocess.run(
        [st._python(), str(CHON_TEP_SCRIPT), str(thu_muc)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=0x08000000 if sys.platform == "win32" else 0)
    if r.returncode != 0:
        dong_cuoi = (r.stderr or "").strip().splitlines()[-1:]
        raise RuntimeError(dong_cuoi[0] if dong_cuoi else f"mã thoát {r.returncode}")
    ds = json.loads(r.stdout or "[]")
    return [p for p in ds if isinstance(p, str) and Path(p).is_file()]


@app.post("/api/chon-tep")
def api_chon_tep():
    """Nút 📂 Thêm từ máy → {"files": [{path, name, lam, xong, buoc}]}.

    Kèm dấu đã-làm của từng file (như bảng chọn cũ) để trang báo "file này đã
    chạy rồi"; còn việc so TRÙNG với các dòng đang có trong ô Nguồn là của
    trang — chỉ trang mới biết ô đang gõ gì. `def` thường (không async): chạy ở
    luồng phụ, chờ hộp chọn bao lâu cũng không khoá các yêu cầu khác."""
    if not _CHON_TEP_LOCK.acquire(blocking=False):
        return JSONResponse({"error": "Hộp chọn file đang mở sẵn rồi — tìm nó "
                                      "trên thanh tác vụ, chọn xong hoặc bấm Cancel."})
    try:
        ds = _hoi_chon_tep()
    except Exception as e:                      # noqa: BLE001 — báo lên trang
        return JSONResponse({"error": f"Không mở được hộp chọn file: {e}"})
    finally:
        _CHON_TEP_LOCK.release()
    prog = _tien_do() if ds else {}
    return JSONResponse({"files": [{"path": p, "name": Path(p).name,
                                    **_danh_dau(p, prog)} for p in ds]})


@app.post("/nguon/xoalichsu")
async def xoa_lich_su_nguon():
    """Nút 🗑 ở hàng “Gần đây”: quên các nguồn đã chạy, KHÔNG đụng ô đang nhập.

    Trả JSON chứ không redirect: khối Nguồn nằm trong form chạy chung nên nút
    này là type=button gọi ngầm bằng fetch — để submit thì nó thành nút mặc
    định của form, bấm Enter trong ô Nguồn hoá ra xoá lịch sử."""
    save_settings({"src_history": []})
    tail.add("🗑 Đã xoá danh sách nguồn gần đây.")
    return JSONResponse({"ok": True})


@app.get("/kieusub-xemtruoc")
def kieusub_xemtruoc(kieu: str = "hopbo", font: str = "", mau: str = "",
                     vitri: str = "", khung: str = "", cochu: str = "",
                     dong: int = 2, mauvien: str = ""):
    """Ảnh xem thử TỔ HỢP kiểu + font + màu chữ/viền + cỡ chữ + số dòng (+ vị trí).

    khung=ngang → khung 16:9 nguyên vẹn để thấy VỊ TRÍ chữ trên màn hình
    (vitri = % chiều cao từ đáy). Render bằng đúng libass sẽ burn nên nhìn sao
    ra vậy; mỗi tổ hợp chỉ render MỘT lần (cache xt_* trong kho ảnh dùng chung)
    nên lần đầu ~1-3 giây, các lần sau hiện ngay.

    dong = số dòng mỗi lần hiện chữ — bước ④ giờ tách câu SRT dài thành nhiều
    lần hiện ≤ dong dòng (chia_cue của video_gansub_cung), cùng nghĩa myvoice.
    """
    try:
        p = kieusub.ve_xemtruoc(kieu, font, mau, vitri,
                                ca_khung=(khung == "ngang"),
                                cochu=cochu, dong=dong, mau_vien=mauvien)
    except Exception:
        p = None
    if not p:
        return JSONResponse({"error": "không vẽ được ảnh xem thử"}, status_code=404)
    return FileResponse(str(p))


@app.get("/partials/queue", response_class=HTMLResponse)
async def partial_queue(request: Request):
    return templates.TemplateResponse(request, "_queue.html", _queue_ctx())


@app.get("/partials/bang", response_class=HTMLResponse)
async def partial_bang(request: Request):
    return templates.TemplateResponse(request, "_bang.html", _bang_ctx())


@app.get("/partials/file", response_class=HTMLResponse)
async def partial_file(request: Request):
    """Khối 📁 File mới — tách khỏi _bang.html (18/11/2026) để khung 🎛 Chỉnh
    trước chen được vào GIỮA bảng video và khối này mà không bị vẽ lại 5 giây/lần."""
    return templates.TemplateResponse(request, "_file.html", {
        "files": _list_output(), "output_dir": str(OUTPUT_DIR)})


@app.get("/timeline", response_class=HTMLResponse)
async def timeline_view(request: Request, base: str = ""):
    """Trang xem XẾP AUDIO kiểu CapCut: hai track — mốc SRT gốc (trước xếp)
    và mốc đã xếp chống đè (sau xếp) — vẽ từ <gốc>_vi_timeline.json."""
    if not st.is_base(base):
        return _home(f"Tên không hợp lệ: {base}")
    tl = Path(f"{OUTPUT_DIR / base}_vi_timeline.json")
    if not tl.is_file():
        return _home(f"{base}: chưa có timeline — chạy bước ③ trước.")
    try:
        d = json.loads(tl.read_text(encoding="utf-8"))
        cues = d["cues"]
    except Exception as e:
        return _home(f"Không đọc được {tl.name}: {e}")

    def lane(key):
        arr = sorted(cues, key=lambda c: c[key])
        out = []
        for i, c in enumerate(arr):
            start = c[key]
            end = start + c["duration_ms"]
            ov = max(0, end - arr[i + 1][key]) if i + 1 < len(arr) else 0
            out.append({"id": c["id"], "text": c["text"], "start": start,
                        "end": end, "duration_ms": c["duration_ms"],
                        "shift_ms": c.get("shift_ms", 0), "ov": ov})
        return out

    def stat(xs):
        return {"n": sum(1 for c in xs if c["ov"]),
                "tong": f"{sum(c['ov'] for c in xs) / 1000:.1f}"}

    truoc, sau = lane("srt_start_ms"), lane("start_ms")
    end_s = d.get("timeline_end_us", 0) / 1e6
    total_s = max(end_s, max((c["end"] for c in truoc + sau), default=0) / 1000)
    buoc_tick = 10 if total_s <= 300 else 30
    return templates.TemplateResponse(request, "timeline.html", {
        "settings": load_settings(),      # base.html cần settings.lang (thiếu là trang 500)
        "base": base, "truoc": truoc, "sau": sau,
        "st_truoc": stat(truoc), "st_sau": stat(sau),
        "end_s": end_s, "total_s": total_s,
        "ticks": list(range(0, int(total_s) + buoc_tick, buoc_tick)),
        "lech_max": f"{max((abs(c['shift_ms']) for c in sau), default=0) / 1000:.1f}",
    })


# ── ⏱ So mốc giờ MẤY CÂU ĐẦU: khe của sub gốc ↔ giọng đã tạo ─────────────────
# Bấm tên video ở bảng Kết quả (15/11/2026): hiện 5 câu đầu, mỗi câu hai mốc
# đặt cạnh nhau — khe SRT (đầu → cuối) và chỗ giọng đọc thật sự nằm + dài bao
# lâu — để liếc là biết giọng có khớp sub không, khỏi mở cả trang 🎞 timeline.
SOCAU_N = 5
# Mốc SRT và srt_start_ms trong timeline.json lệch nhau tối đa chừng này (ms)
# vẫn coi là MỘT câu — video chia đoạn cộng dồn thời lượng nên lệch vài ms.
_KHOP_MS = 60


def _moc(ms) -> str:
    """Mili-giây → 'p:gg.xx' (thêm giờ khi quá 60 phút) cho bảng so mốc giờ."""
    cs = int(round(int(ms) / 10))
    m, cs = divmod(cs, 6000)
    h, m = divmod(m, 60)
    return (f"{h}:{m:02d}" if h else str(m)) + f":{cs // 100:02d}.{cs % 100:02d}"


templates.env.filters["moc"] = _moc


def _so_cau(base: str, n: int = SOCAU_N) -> dict:
    """n câu đầu của một video → context cho _socau.html.

    Hàng lấy theo <gốc>_vi.srt — đúng các câu bước ③ đem đọc (bước ② có thể gộp
    vài dòng sub gốc thành một câu, khe của câu = đầu dòng đầu → cuối dòng cuối).
    Chưa dịch thì lấy thẳng SRT tiếng gốc. Giọng tra trong _vi_timeline.json
    theo MỐC SRT chứ không theo id: timeline gộp của video chia đoạn đánh lại id.
    """
    B = OUTPUT_DIR / base

    def ms(giay: float) -> int:
        return int(round(giay * 1000))

    goc = st.doan.doc_srt(f"{B}.srt")
    vi = st.doan.doc_srt(f"{B}_vi.srt")
    try:
        tl = json.loads(Path(f"{B}_vi_timeline.json")
                        .read_text(encoding="utf-8")).get("cues", [])
    except (OSError, ValueError):
        tl = []

    rows = []
    for i, (s, e, text) in enumerate((vi or goc)[:n], 1):
        s_ms, e_ms = ms(s), ms(e)
        row = {"i": i, "s": s_ms, "e": e_ms, "dai": e_ms - s_ms,
               "text": " ".join(text.split()), "goc": "", "gop": 0, "v": None}
        if vi:              # chữ tiếng gốc = các dòng sub gốc nằm trong khe này
            trong = [t for gs, ge, t in goc
                     if gs >= s - 0.05 and ge <= e + 0.05]
            row["goc"] = " ".join(" ".join(trong).split())
            row["gop"] = len(trong)
        c = min(tl, key=lambda c: abs(int(c.get("srt_start_ms", 0)) - s_ms),
                default=None)
        if c is not None and abs(int(c.get("srt_start_ms", 0)) - s_ms) <= _KHOP_MS:
            v_s, v_dai = int(c.get("start_ms", 0)), int(c.get("duration_ms", 0))
            row["v"] = {"s": v_s, "e": v_s + v_dai, "dai": v_dai,
                        "doi": v_s - s_ms,              # giọng bị dời khỏi mốc sub
                        "chenh": v_dai - row["dai"]}    # > 0: giọng dài hơn khe
        rows.append(row)

    # ▶ NGHE từng câu ngay trong bảng (19/11/2026, user yêu cầu): tiếng GỐC lấy từ
    # video ① (đúng khe sub của câu), GIỌNG ĐỌC lấy từ audio đã xếp của bước ③
    # (đúng chỗ câu đó nằm). Phát qua /chinhtruoc/tep (có Range → nhảy thẳng tới mốc).
    def _url(duoi: str) -> str:
        return ("/chinhtruoc/tep?f=" + quote(base + duoi)
                if os.path.isfile(f"{B}{duoi}") else "")

    # Mốc giờ nhận diện bằng bản CŨ (trước 18/11/2026: _words.json chỉ có 3 trường,
    # chưa sửa chữ lạc quanh chỗ nghỉ) → câu đứng sau quãng im có thể vào sớm hàng
    # chục giây, giọng ghép vào không khớp lúc nhân vật nói. Bảng báo + mời chạy lại.
    ban_cu = False
    for wj in (f"{B}_words.json", f"{B}_words_en.json"):
        try:
            w0 = json.loads(Path(wj).read_text(encoding="utf-8-sig"))
            ban_cu = bool(w0) and len(w0[0]) < 4
            break
        except (OSError, ValueError, TypeError, IndexError):
            continue
    return {"base": base, "rows": rows, "da_dich": bool(vi), "co_giong": bool(tl),
            "url_goc": _url(".mp4"), "url_giong": _url("_vi_audio.wav"), "ban_cu": ban_cu}


@app.get("/partials/socau", response_class=HTMLResponse)
def partial_socau(request: Request, base: str = ""):
    if not st.is_base(base):
        return templates.TemplateResponse(request, "_socau.html", {
            "base": base, "rows": [], "loi": f"Tên không hợp lệ: {base}"})
    return templates.TemplateResponse(request, "_socau.html", _so_cau(base))


# ── 🫥 Sửa VÙNG CHE sub gốc bằng mắt ─────────────────────────────────────────
# Trước đây dò lệch là phải mở <video>_vungsub.json đoán số pixel. Trang này
# hiện KHUNG HÌNH THẬT của video với dải che tô màu đè lên — kéo hai mép (hoặc
# gõ số) rồi Lưu; bước ④ đọc đúng file JSON đó khi ô "Che mờ sub gốc" bật.
def _vungsub_video(base: str) -> Path | None:
    if not st.is_base(base):
        return None
    v = OUTPUT_DIR / f"{base}.mp4"
    return v if v.is_file() else None


@app.get("/vungsub", response_class=HTMLResponse)
def vungsub_view(request: Request, base: str = ""):
    video = _vungsub_video(base)
    if video is None:
        return _home(f"{base}: chưa có video _x… trong output — chạy bước ① trước.")
    import timvungsub
    try:
        w, h, dur = timvungsub._probe(video)
    except Exception as e:
        return _home(f"Không đọc được thông số video: {e}")
    vung = None
    try:
        d = json.loads(timvungsub._cache_path(video).read_text(encoding="utf-8"))
        if all(k in d for k in ("y0", "y1")):
            vung = d
    except (OSError, ValueError):
        pass
    # Chưa có vùng nào thì mở dải GỢI Ý ở khoảng sub hay nằm (72–88% chiều cao)
    # cho có cái mà kéo — chưa lưu thì chưa ảnh hưởng gì tới bước ④.
    y0 = int(vung["y0"]) if vung else round(h * 0.72)
    y1 = int(vung["y1"]) if vung else round(h * 0.88)
    # Khung bộ dò đã dùng (lúc có giọng nói, trong _vungsub.json) — chưa dò thì
    # bốc theo SRT bước ① — để soi dải đúng trên khung CÓ CHỮ chứ không mò %.
    try:
        moc_giay = timvungsub.moc_xem_thu(video)
    except Exception:
        moc_giay = []
    return templates.TemplateResponse(request, "vungsub.html", {
        "settings": load_settings(),      # base.html cần settings.lang
        "base": base, "w": w, "h": h, "dur": dur,
        "y0": max(0, min(h, y0)), "y1": max(0, min(h, y1)),
        # chiều rộng lớp che (chỉnh ở khung 🎛 Chỉnh trước) — trang này chỉ VẼ đúng, không sửa
        "x0": (ct.ngang(vung) or (0, w))[0], "x1": min(w, (ct.ngang(vung) or (0, w))[1]),
        "co_vung": vung is not None,
        "moc_giay": moc_giay,
        "mocs": [(t, timvungsub._mmss(t)) for t in moc_giay],
    })


@app.get("/vungsub/khung")
def vungsub_khung(base: str = "", t: float = -1.0):
    """MỘT khung hình JPEG của video, nguyên cỡ — toạ độ trên ảnh = pixel video."""
    video = _vungsub_video(base)
    if video is None:
        return JSONResponse({"error": "không thấy video"}, status_code=404)
    import timvungsub
    if t < 0:
        # Mặc định: khung đầu tiên bộ dò đã dùng (có chữ) — không có thì 30% video.
        try:
            mocs = timvungsub.moc_xem_thu(video)
            t = mocs[0] if mocs else timvungsub._probe(video)[2] * 0.3
        except Exception:
            t = 30.0
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{max(0.0, t):.2f}", "-i", str(video),
         "-frames:v", "1", "-f", "image2pipe", "-c:v", "mjpeg", "-q:v", "3", "-"],
        capture_output=True, timeout=60)
    if r.returncode != 0 or not r.stdout:
        return JSONResponse({"error": "ffmpeg không bắt được khung hình"},
                            status_code=500)
    return Response(content=r.stdout, media_type="image/jpeg",
                    headers={"Cache-Control": "no-store"})


@app.post("/vungsub/luu")
def vungsub_luu(base: str = Form(...), y0: int = Form(...), y1: int = Form(...),
                moc_giay: str = Form("")):
    """moc_giay: JSON [giây…] — các khung bộ dò đã dùng, lưu kèm để lần mở sau
    trang vẫn soi đúng khung đó (rỗng = không lưu)."""
    video = _vungsub_video(base)
    if video is None:
        return JSONResponse({"error": "không thấy video"}, status_code=404)
    import timvungsub
    try:
        w, h, _d = timvungsub._probe(video)
    except Exception as e:
        return JSONResponse({"error": f"không đọc được video: {e}"}, status_code=500)
    y0, y1 = max(0, min(h, int(y0))), max(0, min(h, int(y1)))
    if y1 - y0 < 8:
        return JSONResponse({"error": "dải mỏng quá — kéo hai mép cách nhau ra"},
                            status_code=400)
    try:
        mocs = [round(float(x), 2) for x in json.loads(moc_giay or "[]")][:20]
    except (ValueError, TypeError):
        mocs = []
    # Trang này chỉ sửa chiều DỌC — CHIỀU RỘNG lớp che (x0/x1, chỉnh ở khung 🎛 Chỉnh
    # trước) đang lưu cho video này thì giữ nguyên, kẻo lưu ở đây là mất.
    cu = ct.vung(_ct_khoa(base))
    ng = ct.ngang(cu) if (cu and cu.get("w") == w) else None
    timvungsub._cache_path(video).write_text(json.dumps(
        {"y0": y0, "y1": y1, "w": w, "h": h,
         **({"x0": ng[0], "x1": ng[1]} if ng else {}), "moc_giay": mocs,
         "ghi_chu": "sửa bằng trang 🫥 trên web; xoá file để dò lại tự động"},
        ensure_ascii=False, indent=2), encoding="utf-8")
    # Kho 🎛 Chỉnh trước là thứ bước ④ đọc TRƯỚC (cờ --vung) — phải sửa theo,
    # kẻo số cũ trong kho đè lên dải vừa kéo ở trang này.
    ct.luu_vung(_ct_khoa(base), y0, y1, w, h, *(ng or (None, None)))
    tail.add(f"🫥 {base}: đã lưu vùng che y {y0}–{y1}"
             + (f" (ngang giữ {ng[0]}–{ng[1]}px)" if ng else "") + ".")
    return JSONResponse({"ok": True, "y0": y0, "y1": y1})


@app.post("/vungsub/dola")
def vungsub_dola(base: str = Form(...)):
    """Chạy lại bộ dò tự động (5 khung lúc có giọng nói, vài giây) — CHỈ trả
    kết quả + các mốc khung đã dùng cho trang xem thử, chưa ghi gì; ưng thì bấm Lưu."""
    video = _vungsub_video(base)
    if video is None:
        return JSONResponse({"error": "không thấy video"}, status_code=404)
    import timvungsub
    try:
        vung = timvungsub.tim_vung(video, dung_cache=False)
    except Exception as e:
        return JSONResponse({"error": f"dò lỗi: {e}"}, status_code=500)
    if not vung:
        return JSONResponse({"none": True})
    return JSONResponse({"y0": vung["y0"], "y1": vung["y1"],
                         "moc_giay": vung.get("moc_giay", []),
                         "nguon_moc": vung.get("nguon_moc", "")})


@app.post("/vungsub/xoa")
def vungsub_xoa(base: str = Form(...)):
    """Bỏ vùng đã lưu — lượt dựng sau sẽ tự dò lại từ đầu."""
    video = _vungsub_video(base)
    if video is None:
        return JSONResponse({"error": "không thấy video"}, status_code=404)
    import timvungsub
    try:
        timvungsub._cache_path(video).unlink()
    except OSError:
        pass
    ct.bo_vung(_ct_khoa(base))          # kho 🎛 Chỉnh trước cũng quên vùng này
    tail.add(f"🫥 {base}: đã bỏ vùng che — lượt dựng sau tự dò lại.")
    return JSONResponse({"ok": True})


# ── 🎛 CHỈNH TRƯỚC (18/11/2026) ──────────────────────────────────────────────
# User không muốn chạy ①→④ một mạch rồi mới biết kết quả: tick một video ở bảng
# Kết quả → 🎛 Chỉnh trước mở khung xem ngay trên trang (giữa bảng video và khối
# 📁 File mới) để chỉnh phóng to, dải che mờ, âm lượng tiếng gốc; 🧪 chạy thử 3
# phút đầu (①②③) rồi kéo riêng âm lượng giọng đọc / tiếng gốc, nghe ngay trên
# video đang xem. Dữ liệu + bản xem trước: chinhtruoc.py.
def _ct_khoa(base: str) -> str:
    """Gốc trong output → khoá video (tên gốc viết thường; clip thử <tên>_thu3p
    quy về chính video <tên> — chỉnh trên bản thử là chỉnh cho video thật)."""
    ten = st.tenchinh(Path(base).name)
    return ten[:-len(ct.THU_DUOI)] if ten.endswith(ct.THU_DUOI) else ten


_TOC_TAG_RE = re.compile(r"_x(\d+(?:\.\d+)?)$")


def _toc_cua(ten: str) -> str:
    """Tốc độ ghi trong tên một gốc ("abc_thu3p_x0.7" → "0.7"); không có tag → ""."""
    m = _TOC_TAG_RE.search(ten or "")
    return ct.chuan_toc(m.group(1), "") if m else ""


def _ct_muc(mid: str, xem: str = "", tao_clip: bool = False, toc: str = "") -> dict | None:
    """Giá trị ô tick ("base:<gốc trong output>" | "src:<nguồn>") → mọi thứ khung
    chỉnh trước cần: nguồn, video để xem, audio giọng đọc, cỡ khung, vùng che.
    xem = "clip" | "thu" | "that" | "nguon": user chọn hẳn bản muốn xem (rỗng = tự chọn).
    tao_clip=True (chỉ lúc MỞ khung): chưa có clip gốc 3 phút thì cắt ngay từ file nguồn.
    toc = TỐC ĐỘ sau khi làm chậm đang chọn ở khung ("0.7"…): bản thử là bản CỦA ĐÚNG
    tốc độ đó — mỗi tốc độ một bản riêng, chọn lại tốc độ đã thử là có sẵn, không tạo lại.
    Rỗng → tốc độ ghi trong tên hàng vừa tick (_x0.8), không có thì tốc độ ở khối ①."""
    s = load_settings()
    mid = (mid or "").strip()
    theo_ten: dict[str, list[dict]] = {}
    for r in st.scan_rows(limit=500):               # mới nhất trước
        theo_ten.setdefault(st.tenchinh(Path(r["base"]).name), []).append(r)
    toc_hang = ""
    if mid.startswith("base:"):
        rel = mid[5:]
        if not st.is_base(rel):
            return None
        khoa = _ct_khoa(rel)
        src = next((x for x in [*(s.get("cho_chinh") or []), *(s.get("src_history") or [])]
                    if isinstance(x, str) and _ten_nguon(x) == khoa), "")
        ten = Path(rel).name
        goc_ten = Path(rel).name[:len(khoa)]         # tên gốc, giữ nguyên hoa/thường
        toc_hang = _toc_cua(ten)
    elif mid.startswith("src:"):
        src = mid[4:].strip().strip('"')
        khoa = _ten_nguon(src) if src else ""
        if not khoa:
            return None
        ten, goc_ten = _src_label(src), _tep_nguon(src).stem
    else:
        return None
    tep = _tep_nguon(src) if src else None
    tep = tep if (tep and tep.is_file()) else None
    toc = ct.chuan_toc(toc, "") or toc_hang or ct.chuan_toc(s.get("speed"), "0.7")

    def _theo_toc(ds: list[dict]) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for r in ds:                                 # mới nhất trước → giữ cái đầu của mỗi tốc độ
            out.setdefault(_toc_cua(Path(r["base"]).name), r)
        return out

    ds_that = theo_ten.get(khoa) or []
    cac_thu = _theo_toc(theo_ten.get(khoa + ct.THU_DUOI) or [])
    # Video ① cả bài: bản của tốc độ đang chọn, chưa có thì bản mới nhất (nhãn ghi rõ tốc độ).
    r_that = _theo_toc(ds_that).get(toc) or (ds_that[0] if ds_that else None)
    r_thu = cac_thu.get(toc)
    that = (OUTPUT_DIR / r_that["base"] if r_that
            else st.base_for(str(_tep_nguon(src)), toc) if src else None)
    thu = (OUTPUT_DIR / r_thu["base"] if r_thu
           else st.base_for(str(OUTPUT_DIR / f"{goc_ten}{ct.THU_DUOI}.mp4"), toc))

    def _co(b, duoi):
        p = Path(f"{b}{duoi}") if b else None
        return p if (p and p.is_file()) else None

    v_that, a_that = _co(that, ".mp4"), _co(that, "_vi_audio.wav")
    v_thu, a_thu = _co(thu, ".mp4"), _co(thu, "_vi_audio.wav")
    # Hàng nút tốc độ: các nấc của khối ① + mọi tốc độ ĐÃ có bản thử + tốc độ đang chọn.
    cac_toc = [{"toc": t, "nhan": f"{t}x", "dang": t == toc,
                "co_thu": bool(t in cac_thu and _co(OUTPUT_DIR / cac_thu[t]["base"], ".mp4")),
                "co_giong": bool(t in cac_thu and _co(OUTPUT_DIR / cac_thu[t]["base"], "_vi_audio.wav"))}
               for t in sorted({*ct.TOC_DO, *(t for t in cac_thu if t), toc}, key=float)]
    # CLIP GỐC 3 PHÚT (20/11/2026, user chốt luồng): chọn video để chỉnh trước là
    # cắt ngay 3 phút đầu của file nguồn ra output/<tên>_thu3p.mp4 — xem được liền,
    # chưa nhận diện / lồng tiếng gì. 🧪 chạy ①②③ trên CHÍNH clip này.
    clip = OUTPUT_DIR / f"{goc_ten}{ct.THU_DUOI}.mp4"
    if tao_clip and tep is not None:
        ct.cat_clip(tep, clip)
    v_clip = clip if clip.is_file() else None
    # Các BẢN xem được, theo thứ tự nút. Mặc định đi theo luồng 3 phút: bản thử ĐÃ
    # lồng tiếng → chưa có thì clip gốc 3 phút. Video ① cả bài và file nguồn cả bài
    # chỉ là bản xem thêm (bấm nút "Xem bản"), trừ khi không có nguồn để cắt clip.
    # Bản xem trước thu nhỏ 540p chỉ còn là đường lùi khi trình duyệt không đọc
    # được file. `xem` = user bấm nút chọn hẳn một bản.
    phut = ct.THU_GIAY // 60
    ban = {}
    if v_clip:
        ban["clip"] = (v_clip, None, f"✂ Clip gốc {phut} phút (chưa xử lý)")
    if v_thu:
        ban["thu"] = (v_thu, a_thu, f"🧪 Bản thử {phut} phút {toc}x"
                                    + (" đã lồng tiếng" if a_thu else " (chưa có giọng)"))
    if v_that:
        toc_that = _toc_cua(that.name)
        ban["that"] = (v_that, a_that, "🐢 Video ① cả bài" + (f" {toc_that}x" if toc_that else "")
                                       + " (đã làm chậm)" + (" + giọng đọc" if a_that else ""))
    if tep:
        ban["nguon"] = (tep, None, "🎬 File nguồn gốc cả bài")
    if xem in ban:
        loai = xem
    elif "thu" in ban and ban["thu"][1]:
        loai = "thu"
    else:
        loai = next((k for k in ("clip", "that", "thu", "nguon") if k in ban), "")
    video, audio = (ban[loai][0], ban[loai][1]) if loai else (None, None)

    def _url(p: Path) -> str:
        # &v=<giờ sửa file>: chạy thử lại là file cùng tên được ghi đè — không có v
        # thì trình duyệt phát lại bản CŨ đang nằm trong bộ đệm.
        return ("/chinhtruoc/tep?f=" + quote(p.relative_to(OUTPUT_DIR).as_posix())
                + f"&v={int(p.stat().st_mtime)}")

    # Dấu của bản thử hiện có (giờ ghi audio giọng đọc; 0 = chưa có) — khung so dấu
    # này trước/sau một lượt 🧪 để biết bản thử MỚI đã ra.
    ban_thu = int(a_thu.stat().st_mtime) if a_thu else 0

    w = h = 0
    ly_do = ""
    if video is None:
        ly_do = (f"Link này chưa tải về máy (chưa có {_tep_nguon(src).name} trong Downloads) — "
                 "dán link vào ô Nguồn rồi bấm ⬇ Chỉ tải về, hoặc bấm 🧪 Chạy thử 3 phút "
                 "bên dưới (tự tải rồi chạy)." if src and st.la_link_bilibili(src)
                 else f"Không thấy file nguồn: {src}" if src
                 else "Không biết file nguồn của video này và trong output cũng chưa có "
                      "video ① — dán lại file gốc vào ô Nguồn.")
    else:
        try:
            import timvungsub
            w, h, _dur = timvungsub._probe(video)
        except Exception as e:
            ly_do = f"Không đọc được thông số video ({video.name}): {e}"
    # Vùng che: đã chỉnh tay (kho) → cache bộ dò cạnh video → dải gợi ý 72–88%.
    vg, co_vung = ct.vung(khoa), True
    if vg and h and vg.get("h") and vg["h"] != h:
        # Lưu lúc khung hình cao khác (hiếm: nguồn bị thay bằng bản khác cỡ) → co
        # theo tỉ lệ, đừng vứt dải user đã kéo.
        vg = {**vg, "y0": round(vg["y0"] * h / vg["h"]), "y1": round(vg["y1"] * h / vg["h"])}
    if not vg:
        for v in (v_that, v_thu):
            if v is None:
                continue
            try:
                d = json.loads(v.with_name(v.stem + "_vungsub.json").read_text(encoding="utf-8"))
                if all(k in d for k in ("y0", "y1")):
                    vg = d
                    break
            except (OSError, ValueError):
                pass
    if not vg:
        vg, co_vung = {"y0": round(h * 0.72), "y1": round(h * 0.88)}, False
    # Khoảng NGANG của lớp che (mép trái/phải theo pixel video, 20/11/2026): chỉ có khi
    # user đã thu hẹp lớp che (ct.ngang); không có = phủ hết bề ngang như trước giờ. Lưu
    # lúc khung hình rộng khác thì co theo tỉ lệ, như chiều dọc ở trên.
    cx0, cx1 = 0, w
    ng = ct.ngang(vg)
    if ng and w:
        tl = w / vg["w"] if (isinstance(vg.get("w"), int) and vg["w"] and vg["w"] != w) else 1
        a, b = max(0, min(w, round(ng[0] * tl))), max(0, min(w, round(ng[1] * tl)))
        if b - a >= 2:
            cx0, cx1 = a, b
    return {
        "id": mid, "khoa": khoa, "ten": ten, "src": src, "tep": tep, "loai": loai,
        # tên video không kèm tag _thu3p/_x… — tiêu đề khung (tốc độ hiện riêng ở hàng nút)
        "ten_goc": goc_ten if mid.startswith("base:") else ten,
        "toc": toc, "cac_toc": cac_toc,
        "link_chua_tai": bool(src) and st.la_link_bilibili(src) and tep is None,
        "video": video, "audio": audio, "v_that": v_that, "v_thu": v_thu,
        "video_url": ("" if (video is None or not h)
                      else "/chinhtruoc/nguon?src=" + quote(str(video)) if loai == "nguon"
                      else _url(video)),
        # Clip gốc / file nguồn mà trình duyệt không phát được (codec lạ) → khung tự
        # lùi về bản xem trước thu nhỏ 3 phút đầu (H.264 540p do server dựng).
        "du_phong_url": ("/chinhtruoc/xem?src=" + quote(str(video))
                         if (loai in ("nguon", "clip") and video is not None and h) else ""),
        "co_thu": bool(a_thu),            # đã có bản thử lồng tiếng → nút 🧪 thành "làm lại"
        "cac_ban": [{"key": k, "nhan": v[2], "dang": k == loai} for k, v in ban.items()],
        "ban_thu": ban_thu,
        # đầu tiêu đề của VIỆC chạy thử trong hàng đợi (steps.build đặt) — để dò việc đang chạy/đợi.
        # viec_thu = của ĐÚNG tốc độ đang xem (dấu cách cuối: "×0.7 " không khớp nhầm "×0.75 ");
        # viec_thu_chung = của video này ở tốc độ bất kỳ.
        "viec_thu": (f"{_tep_nguon(src).name} — 🧪 thử {phut} phút ×{float(toc):g} " if src else ""),
        "viec_thu_chung": (f"{_tep_nguon(src).name} — 🧪 thử {phut} phút ×" if src else ""),
        "audio_url": _url(audio) if audio else "",
        # gốc (tương đối) của video ① đang xem — cho nút ↺ dò tự động (/vungsub/dola)
        "base_do": (video.relative_to(OUTPUT_DIR).with_suffix("").as_posix()
                    if video is not None and loai in ("that", "thu") else ""),
        "w": w, "h": h, "ly_do": ly_do, "co_vung": co_vung,
        "y0": max(0, min(h, int(vg["y0"]))), "y1": max(0, min(h, int(vg["y1"]))),
        "x0": cx0, "x1": cx1,             # (0, w) = lớp che phủ hết bề ngang
    }


@app.post("/nguon/nap")
async def nguon_nap(request: Request):
    """Ô Nguồn vừa được nạp (gõ/dán, bấm chip, 📂 Thêm từ máy) → nhớ các dòng HỢP
    LỆ (file video có thật / link) thành nguồn chờ để hiện lên bảng Kết quả."""
    form = await request.form()
    dong = [l.strip().strip('"') for l in (form.get("sources") or "").splitlines()]
    moi = [l for l in dong if ct.nguon_hop_le(l, st.la_link_bilibili)]
    cu = [x for x in (load_settings().get("cho_chinh") or []) if isinstance(x, str)]
    gop = ct.gop_nguon_cho(cu, moi)
    if gop != cu:
        save_settings({"cho_chinh": gop})
    return JSONResponse({"them": len([m for m in moi if m not in cu])})


@app.post("/nguon/bo")
async def nguon_bo(request: Request, src: str = Form(...)):
    """Bỏ một nguồn chờ khỏi bảng — không đụng FILE NGUỒN, không đụng ô Nguồn.

    24/11/2026 (xoá ở bảng = dọn sạch, xem _tep_xoa): nguồn đã có bản thử 3 phút /
    clip đã cắt trong output thì đưa luôn vào Thùng rác — kẻo ✕ xong chúng nằm lại
    mà không còn hàng nào để xoá."""
    khoa = _ten_nguon(src)
    files = _tep_thu_ten(_tep_nguon(src).stem) if khoa else []
    if files and q.busy():
        return _tra(request, "Hàng đợi đang chạy — dừng hết trước rồi hãy xoá "
                             "(file có thể đang được ghi).")
    fail = 0
    if files:
        for p in files:
            if p.is_file():
                ct.bo_xem_truoc(p)
        ok_n, fail = st.recycle(files, on_log=q.note)
        q.note(f"🗑 {_src_label(src)}: đã đưa {ok_n} mục bản thử vào Thùng rác"
               + (f", {fail} mục KHÔNG xoá được" if fail else "")
               + " — khôi phục: mở Thùng rác Windows.")
    ct.bo_xem_truoc(_tep_nguon(src))
    cu = [x for x in (load_settings().get("cho_chinh") or []) if isinstance(x, str)]
    save_settings({"cho_chinh": [x for x in cu if x != src]})
    return _tra(request, f"{_src_label(src)}: {fail} mục không đưa vào Thùng rác được — "
                         "xem nhật ký." if fail else "",
                ok=f"Đã bỏ khỏi danh sách: {_src_label(src)}"
                   + (" (bản thử 3 phút đã vào Thùng rác)" if files else ""),
                bao={"mvid:daxoa": {"khoa": khoa}} if khoa else None)


@app.get("/partials/chinhtruoc", response_class=HTMLResponse)
def partial_chinhtruoc(request: Request, id: str = "", xem: str = "", toc: str = ""):
    m = _ct_muc(id, xem, tao_clip=True, toc=toc)   # mở khung = cắt sẵn clip gốc 3 phút (nếu chưa có)
    s = load_settings()
    return templates.TemplateResponse(request, "_chinhtruoc.html", {
        "m": m, "mid": id,
        "zoom": ct.doc_db(s.get("zoom"), 0, 100, 0),
        "zoom_y": ct.doc_db(s.get("zoom_y"), -100, 100, 0),
        "chesub": bool(s.get("chesub", True)),
        # Thanh tiếng gốc: -21 = nấc tận trái = "như cũ" (khoá gocdb rỗng).
        "gocdb": ct.doc_db(s.get("gocdb"), -20, 20, -21) if str(s.get("gocdb") or "").strip() else -21,
        "ttsdb": ct.doc_db(s.get("ttsdb"), -20, 20, 0),
        "thu_phut": ct.THU_GIAY // 60,
    })


@app.get("/chinhtruoc/tep")
def chinhtruoc_tep(f: str = ""):
    """Phát video ① / audio giọng đọc trong output (có Range → tua được)."""
    try:
        p = (OUTPUT_DIR / f).resolve()
        p.relative_to(OUTPUT_DIR.resolve())
    except (ValueError, OSError):
        return JSONResponse({"error": "đường dẫn không hợp lệ"}, status_code=400)
    if p.suffix.lower() not in (".mp4", ".wav") or not p.is_file():
        return JSONResponse({"error": "không thấy file"}, status_code=404)
    return FileResponse(str(p), media_type="video/mp4" if p.suffix.lower() == ".mp4" else "audio/wav")


@app.get("/chinhtruoc/nguon")
def chinhtruoc_nguon(src: str = ""):
    """Phát THẲNG file video nguồn (video thật, đủ độ dài; có Range → tua được).
    Trình duyệt không đọc được định dạng thì khung tự chuyển sang /chinhtruoc/xem."""
    p = Path((src or "").strip().strip('"'))
    if p.suffix.lower() not in ct.VIDEO_EXTS or not p.is_file():
        return JSONResponse({"error": "không thấy file video nguồn"}, status_code=404)
    return FileResponse(str(p), media_type=mimetypes.guess_type(p.name)[0] or "video/mp4")


@app.get("/chinhtruoc/xem")
def chinhtruoc_xem(src: str = ""):
    """Bản xem trước (3 phút đầu, 540p) của một FILE NGUỒN — dựng lần đầu mất
    10–20 giây, các lần sau trả ngay."""
    p = Path((src or "").strip().strip('"'))
    if p.suffix.lower() not in ct.VIDEO_EXTS or not p.is_file():
        return JSONResponse({"error": "không thấy file video nguồn"}, status_code=404)
    try:
        return FileResponse(str(ct.xem_truoc(p)), media_type="video/mp4")
    except Exception as e:
        return JSONResponse({"error": f"không dựng được bản xem trước: {e}"}, status_code=500)


@app.get("/chinhtruoc/trangthai")
def chinhtruoc_trangthai(id: str = "", toc: str = ""):
    """Khung chỉnh trước hỏi định kỳ: bản thử (của tốc độ đang xem) đã có giọng đọc chưa?"""
    # Đọc HÀNG ĐỢI TRƯỚC rồi mới đọc file: nếu hàng đợi báo việc chạy thử đã xong
    # thì audio bản thử đọc sau đó chắc chắn là bản đã ghi xong. Đọc ngược lại là
    # có khe hở "file còn cũ mà hàng đợi đã rảnh" → khung tưởng chạy xong mà không
    # có bản mới.
    tt = q.state()
    m = _ct_muc(id, toc=toc)
    if m is None:
        return JSONResponse({"error": "không nhận ra video"}, status_code=404)
    # Việc 🧪 chạy thử của video này Ở TỐC ĐỘ ĐANG XEM trong hàng đợi: đang chạy (bước
    # nào) / đang đợi / lượt gần nhất kết thúc ra sao. Khung dùng để báo tiến độ và tự
    # nạp bản mới.
    la_thu = lambda j: bool(m["viec_thu"]) and j["title"].startswith(m["viec_thu"])   # noqa: E731
    chay = tt["current"] if (tt["current"] and la_thu(tt["current"])) else None
    doi = next((i for i, j in enumerate(tt["pending"], 1) if la_thu(j)), 0)
    cuoi = next((j["status"] for j in tt["history"] if la_thu(j)), "")
    # Các tốc độ của video này đang có việc chạy thử trong hàng đợi (kể cả tốc độ khác
    # tốc độ đang xem) → hàng nút tốc độ hiện ⏳ ở đúng nút.
    dang_toc = set()
    for j in [tt["current"], *tt["pending"]]:
        if j and m["viec_thu_chung"] and j["title"].startswith(m["viec_thu_chung"]):
            t = ct.chuan_toc(j["title"][len(m["viec_thu_chung"]):].split(" ")[0], "")
            if t:
                dang_toc.add(t)
    return JSONResponse({
        "loai": m["loai"], "long_tieng": bool(m["audio"]),
        "ban_thu": m["ban_thu"], "toc": m["toc"],
        "thu": {"dang": bool(chay or doi),
                "buoc": (f"{chay['step_label']} ({chay['step_index'] + 1}/{chay['step_total']})" if chay
                         else f"đang đợi trong hàng đợi (thứ {doi})" if doi else ""),
                "cuoi": cuoi},
        "cac_toc": [{"toc": t["toc"], "co_giong": t["co_giong"], "dang": t["toc"] in dang_toc}
                    for t in m["cac_toc"]],
    })


@app.post("/chinhtruoc/luu")
def chinhtruoc_luu(id: str = Form(...), zoom: str = Form("0"), chesub: str = Form(""),
                   y0: str = Form(""), y1: str = Form(""),
                   gocdb: str = Form("-21"), ttsdb: str = Form("0"),
                   zoom_y: str = Form("0"), toc: str = Form(""),
                   x0: str = Form(""), x1: str = Form("")):
    """💾 Áp dụng: phóng to / bật che mờ / hai mức âm lượng ghi vào cài đặt CHUNG
    (đúng các khoá khối ④ và tab 🔊 đang dùng); dải che ghi theo TỪNG VIDEO. Tốc độ
    đang chọn ở khung (toc) ghi vào khoá speed của khối ① — lượt chạy thật dùng đúng nó.
    x0/x1 = mép trái/phải của lớp che (pixel video) khi nó hẹp hơn bề ngang; không gửi
    (hoặc hẹp dưới 16px) thì giữ khoảng ngang đang lưu."""
    toc = ct.chuan_toc(toc, "")
    m = _ct_muc(id, toc=toc)
    if m is None:
        return JSONResponse({"error": "không nhận ra video"}, status_code=404)
    z, g = ct.doc_db(zoom, 0, 100, 0), ct.doc_db(gocdb, -21, 20, -21)
    cai = {"zoom": str(z) if z else "", "chesub": chesub in ("1", "true", "on"),
           # không phóng thì không có phần dôi nào để dời → vị trí dọc về giữa
           "zoom_y": str(ct.doc_db(zoom_y, -100, 100, 0)) if z else "0",
           "gocdb": "" if g <= -21 else str(g), "ttsdb": str(ct.doc_db(ttsdb, -20, 20, 0))}
    if toc:                                  # khung bản cũ không gửi toc → không đụng speed
        cai["speed"] = toc
    save_settings(cai)
    vung = None
    if m["h"]:
        try:
            a = max(0, min(m["h"], int(float(y0))))
            b = max(0, min(m["h"], int(float(y1))))
        except (TypeError, ValueError):
            a = b = 0
        try:
            xa = max(0, min(m["w"], int(float(x0))))
            xb = max(0, min(m["w"], int(float(x1))))
        except (TypeError, ValueError):
            xa = xb = 0
        if xb - xa < 16:
            xa, xb = m["x0"], m["x1"]
        if b - a >= 8:
            vung = ct.luu_vung(m["khoa"], a, b, m["w"], m["h"], xa, xb)
            for v in (m["v_that"], m["v_thu"]):      # video ① đã có → trang 🫥 thấy cùng số
                if v is not None:
                    ct.ghi_cache_vung(v, vung, "chỉnh ở khung 🎛 Chỉnh trước; xoá file để dò lại tự động")
    tail.add(f"🎛 {m['ten']}: đã lưu chỉnh trước — " + (f"tốc độ {toc}x · " if toc else "") + f"phóng {z}%"
             + (f" (dọc {int(cai['zoom_y']):+d})" if cai["zoom_y"] != "0" else "") + " · che mờ "
             f"{'bật' if cai['chesub'] else 'tắt'}"
             + (f" (y {vung['y0']}–{vung['y1']}"
                + (f", ngang {vung['x0']}–{vung['x1']}/{vung['w']}px" if "x0" in vung else "") + ")"
                if vung else "")
             + f" · tiếng gốc {cai['gocdb'] or 'như cũ'}{' dB' if cai['gocdb'] else ''}"
             f" · giọng đọc {int(cai['ttsdb']):+d} dB.")
    return JSONResponse({"ok": True, **cai, "vung": vung})


@app.post("/chinhtruoc/thu")
async def chinhtruoc_thu(request: Request):
    """🧪 Chạy thử 3 phút đầu: cắt → ① chậm + SRT → ② dịch → ③ giọng (không ④)."""
    form = await request.form()
    # ct_toc = tốc độ khung đang xem (nút 🧪 gửi kèm): bản thử chạy ở ĐÚNG tốc độ đó,
    # ra file riêng mang tag _x<tốc độ> — bản thử của tốc độ khác vẫn nằm nguyên.
    toc = ct.chuan_toc(form.get("ct_toc") or "", "")
    m = _ct_muc(form.get("ct_id") or "", toc=toc)
    if m is None:
        return _tra(request, "Không nhận ra video cần chạy thử — tick lại ở bảng rồi bấm 🎛 Chỉnh trước.")
    if not m["src"]:
        return _tra(request, f"{m['ten']}: không biết file nguồn để cắt 3 phút đầu — dán lại "
                             "file gốc (hoặc link) vào ô Nguồn rồi mở 🎛 Chỉnh trước từ hàng đó.")
    # Nút nằm trong form chính nên htmx gửi kèm mọi ô cài đặt → chạy thử theo
    # đúng thứ đang hiện trên trang (và lưu luôn, như /chay). Thiếu ô (gọi kiểu
    # khác) thì dùng cài đặt đã lưu, KHÔNG ghi đè bằng mặc định.
    if form.get("speed") and form.get("model"):
        s = _settings_from_form(form)
        if toc:
            s["speed"] = toc
        save_settings(s)
    s = load_settings()                      # bản đã trộn — xem ghi chú ở /chay
    # Không có ct_toc (khung bản cũ): tốc độ theo _ct_muc đã chọn (hàng vừa tick / khối ①).
    s = {**s, "speed": toc or m["toc"]}
    # Bấm 🧪 = LÀM LẠI bản thử từ đầu theo cài đặt đang có (19/11/2026, user yêu cầu):
    # nhận diện lại (bỏ mốc giờ đã lưu của clip thử) và đọc lại mọi câu — không thì
    # bản thử cũ được dùng lại từng phần, xem lại vẫn là kết quả của cài đặt cũ.
    s = {**s, "redoasr": True, "redotts": True}
    title, job_steps, err = st.build("thu3p", m["src"], s)
    if err:
        return _tra(request, err)
    q.enqueue(title, job_steps)
    remember_sources([m["src"]])
    return _tra(request, ok=f"Đã xếp chạy thử {ct.THU_GIAY // 60} phút đầu (①②③) — xong thì khung "
                            "🎛 Chỉnh trước tự báo để nghe bản lồng tiếng", luu=True, chay=True)


# ── Chạy việc ────────────────────────────────────────────────────────────────
def _settings_from_form(form) -> dict:
    g = form.get
    s = dict(
        lang=g("lang") if g("lang") in ("zh", "en") else "zh",
        speed=g("speed") or "0.7",
        model=g("model") or DEFAULTS["model"],
        maxchars=_tran_dong(g("maxchars"), 4, 60, 0),
        maxchars_en=_tran_dong(g("maxchars_en"), 10, 120, 42),
        ngucanh=bool(g("ngucanh")),
        batchchars=_clamp(g("batchchars"), 200, 5000, 1200),
        gopcau=bool(g("gopcau")),
        offline=bool(g("offline")),
        voice=g("voice") or "",
        # 🎙/🗣 engine bước ③ + giọng VieNeu (ô vắng ở trang cũ còn mở → omni / Ngọc Huyền).
        engine="vieneu" if g("engine") == "vieneu" else "omni",
        giong_vieneu=vn.giong_hop_le(g("giong_vieneu")),
        # 🔆 Sáng giọng (khối ③): 0–100, mặc định 80; ô vắng (trang cũ còn mở) → 80.
        sanggiong=_clamp(g("sanggiong"), 0, 100, 0),
        # 🎵🔔🧒 (khối ③, như myvoice): tông kẹp ±6 bán cung làm tròn 0,5; bộ lọc 0–100.
        pitch=f"{hu.parse_pitch(g('pitch'), 0.0):.1f}",
        vang_truong_do=_clamp(g("vang_truong_do"), 0, 100, 0),
        vang_cuong_do=_clamp(g("vang_cuong_do"), 0, 100, 0),
        thieu_nien=_clamp(g("thieu_nien"), 0, 100, 0),
        # 🔊 âm lượng dB (09/11/2026): "+3" / "2,5" đều đọc được, làm tròn 0,5, kẹp −10…+20;
        # ô vắng (trang cũ còn mở) → 0 = giữ nguyên. Ô 🎚 mau_giong KHÔNG lưu (chỉ điền 5 ô).
        am_luong_db=f"{hu.parse_amluong(g('am_luong_db'), 0.0):g}",
        subchars=_clamp(g("subchars"), 10, 120, 50),
        kieusub=g("kieusub") or "hopbo",
        subfont=g("subfont") or "",
        submau=_hex6(g("submau")),
        submauvien=_hex6(g("submauvien")),
        subcochu=_pct(g("subcochu"), 50, 200) or "100",
        subvitri=_pct(g("subvitri"), 0, 100),
        subdong=g("subdong") if g("subdong") in ("1", "2") else "2",
        zoom=_pct(g("zoom"), 0, 100),
        chesub=bool(g("chesub")),
        chiadoan=bool(g("chiadoan")),
        chiadoan_phut=_clamp(g("chiadoan_phut"), 10, 120, 30),
        vesub=bool(g("vesub")),
        xuatdoc=bool(g("xuatdoc")),
        # Nhạc nền: chỉ nhận TÊN FILE trần trong kho myvideo/nhac (chặn ../).
        nhacnen=(g("nhacnen") or "").strip()
                if (g("nhacnen") or "") == Path((g("nhacnen") or "")).name else "",
        nhacnen_db=str(_clamp(g("nhacnen_db"), -40, 0, -18)),
        # (gocdb/gocnorm/ttsdb/ttsnorm KHÔNG đọc ở đây: chúng thuộc tab 🔊 Âm
        # thanh, lưu riêng qua /amthanh/luu — form chính không có mấy ô đó,
        # đọc ở đây là mỗi lượt /luu lại reset về mặc định.)
        logo_kenh=bool(g("logo_kenh")), khung_kenh=bool(g("khung_kenh")),
        outro_kenh=bool(g("outro_kenh")),
        # Logo đang chọn: chỉ nhận TÊN FILE trần (chặn ../), có hay không kiểm
        # ở kenh_hoso.logo_path lúc dùng (file xoá đi thì tự lùi về cái khác).
        logo_file=(g("logo_file") or "").strip()
                  if (g("logo_file") or "") == Path((g("logo_file") or "")).name else "",
        # ⚠️ Dòng lưu ý góc trái trên: ô tick + 2 dòng chữ (cắt 90 ký tự/dòng —
        # dài hơn là tràn khung dọc 1080px). Dòng để trống = bỏ dòng đó.
        luuy=bool(g("luuy")),
        luuy1=" ".join((g("luuy1") or "").split())[:90],
        luuy2=" ".join((g("luuy2") or "").split())[:90],
        thu60_tu=_phut(g("thu60_tu")),
        auto2=bool(g("auto2")), auto3=bool(g("auto3")), auto4=bool(g("auto4")),
        thaytieng=bool(g("thaytieng")), cpu=bool(g("cpu")),
    )
    # Danh sách ⭐ do trang tự sửa (mỗi dòng một tên) và gửi kèm lúc lưu/chạy.
    # CHỈ ghi đè khi form thật sự có ô này — lượt gửi từ trang cũ còn mở (chưa
    # có ô) mà ghi đè là xoá sạch danh sách đã ghim.
    if "voice_stars" in form:
        s["voice_stars"] = [x.strip() for x in (g("voice_stars") or "").splitlines()
                            if x.strip()]
    # Cách dịch Gemini KHÔNG nằm trong web_settings.json của myvideo: nó là lựa
    # chọn dùng chung hai bảng, ghi thẳng vào myvoice/taogiong_pipeline.json
    # (set_backend chỉ đụng đúng khoá này, giữ nguyên cài đặt khác của myvoice).
    if g("gemini_backend") in gemini_backend.BACKENDS:
        gemini_backend.set_backend(g("gemini_backend"))
    return s


@app.post("/chay")
async def chay(request: Request):
    form = await request.form()
    save_settings(_settings_from_form(form))    # bấm chạy cũng là lưu cài đặt
    # Dựng lệnh từ bản ĐÃ TRỘN với cài đặt đang lưu, không phải riêng các ô của form
    # chính: mức tiếng gốc / giọng đọc (tab 🔊, 💾 của khung 🎛 Chỉnh trước) và vị trí
    # dọc sau khi phóng (zoom_y) KHÔNG có ô trong form này. Lấy riêng form thì bước ④
    # mất --goc-db / --goc-norm / --tts-db / --zoom-y: ▶ Chạy ra video tắt tiếng gốc,
    # hình cắt giữa, dù vừa 💾 khác đi (user báo 24/11/2026).
    s = load_settings()
    s["redoasr"] = bool(form.get("redoasr"))    # hai ô "làm lại" chỉ áp dụng
    s["redotts"] = bool(form.get("redotts"))    # cho lượt này, không lưu
    start = form.get("start") or "cham"

    # Ô Nguồn là DANH SÁCH: mỗi dòng một file → mỗi dòng một việc trong hàng đợi.
    sources = [l.strip().strip('"') for l in (form.get("sources") or "").splitlines()]
    sources = [l for l in sources if l]
    if not sources:
        return _tra(request, "Ô Nguồn đang trống — mỗi dòng một file video.")
    jobs, errs = [], []
    for src in sources:
        title, job_steps, err = st.build(start, src, s)
        if err:
            errs.append(err)
        else:
            jobs.append((title, job_steps))
    if errs:
        # Có dòng hỏng thì KHÔNG xếp dòng nào — sửa xong bấm lại, khỏi lẫn nửa chừng.
        return _tra(request, " · ".join(errs[:3]) + (" …" if len(errs) > 3 else ""))
    for title, job_steps in jobs:
        q.enqueue(title, job_steps)
    remember_sources(sources)     # để lần sau bấm chip là xong, khỏi đi tìm lại
    if start == "tai":
        ok = (f"Đã xếp {len(jobs)} link tải LẦN LƯỢT — file về Downloads/<mã BV>.mp4, "
              "tiến độ ở tab ⏱; tải xong thì 📂 Thêm từ máy để chạy ①→④")
    else:
        ok = f"Đã lưu cài đặt · xếp {len(jobs)} việc vào hàng đợi"
    return _tra(request, ok=ok, luu=True, chay=True)


@app.post("/luu")
async def luu(request: Request):
    save_settings(_settings_from_form(await request.form()))
    return _tra(request, ok="Đã lưu cài đặt", luu=True)


@app.post("/chaylai")
async def chay_lai(request: Request, base: str = Form(...)):
    """🔁 Nhận diện lại + chạy lại CẢ BÀI ①②③④ cho một video đã có trong output —
    nút trong bảng ⏱ Mốc giờ khi mốc giờ thuộc bản nhận diện cũ. Ép --redo-asr;
    video ① đã dựng thì bước ① tự bỏ qua phần render, chỉ làm lại SRT."""
    m = _ct_muc("base:" + base)
    if m is None or not m["src"]:
        return _tra(request, f"{Path(base).name}: không biết file nguồn của video này — dán lại "
                             "file gốc vào ô Nguồn rồi bấm ▶ Chạy tất cả ①②③④.")
    s = {**load_settings(), "redoasr": True}
    title, job_steps, err = st.build("tatca", m["src"], s)
    if err:
        return _tra(request, err)
    q.enqueue(title, job_steps)
    return _tra(request, ok=f"Đã xếp: {title} (nhận diện lại từ đầu)")


@app.post("/tiep")
async def tiep(request: Request, base: str = Form(...)):
    title, job_steps, err = st.resume(base, load_settings())
    if err:
        return _tra(request, err)
    q.enqueue(title, job_steps)
    return _tra(request, ok=f"Đã xếp: {title}")


@app.post("/buoc")
async def buoc(request: Request, base: str = Form(...), key: str = Form(...)):
    title, job_steps, err = st.single(base, key, load_settings())
    if err:
        return _tra(request, err)
    q.enqueue(title, job_steps)
    return _tra(request, ok=f"Đã xếp: {title}")


@app.post("/render-lai")
async def render_lai(request: Request):
    """🔁 Render lại (cột ④ của bảng, 25/11/2026): dựng lại ĐÚNG bước ④ cho một video đã
    có trong output, theo cài đặt ĐANG CÓ trên trang.

    Nút nằm trong form chính nên htmx gửi kèm mọi ô của form → lưu trước rồi mới dựng
    lệnh, y như nút 🎬 Chạy bước ④: "theo cài đặt mới" là cái user vừa chỉnh trên trang,
    kể cả khi chưa bấm 💾. Lượt gửi không mang form (trang cũ, công cụ ngoài) thì dùng
    cài đặt đang lưu — tuyệt đối không ghi đè bằng một form rỗng (mọi ô tick thành tắt).
    Video hoàn thành cũ bị GHI ĐÈ (bước ④ ghi thẳng vào _sub.mp4) — nút có hỏi lại."""
    form = await request.form()
    base = str(form.get("base") or "").strip()
    if not st.is_base(base):
        return _tra(request, f"Tên không hợp lệ: {base}")
    ten = Path(base).name
    if _dang_dung(base, q.state()):
        return _tra(request, f"{ten}: bước ④ của video này ĐÃ nằm trong hàng đợi — chờ lượt đó "
                             "xong (xem tab ⏱ Hàng đợi) rồi hãy render lại.")
    co_form = "sources" in form and "speed" in form
    if co_form:
        save_settings(_settings_from_form(form))
    _title, job_steps, err = st.single(base, "gan", load_settings())
    if err:
        return _tra(request, err)
    q.enqueue(f"{base} — 🔁 render lại ④", job_steps)
    return _tra(request, ok=f"🔁 Đã xếp render lại {ten} theo cài đặt hiện tại"
                            + (" (đã lưu cài đặt)" if co_form else "")
                            + " — tiến độ ở tab ⏱ Hàng đợi", luu=co_form)


# ── Điều khiển hàng đợi ──────────────────────────────────────────────────────
@app.post("/hangdoi/pause")
async def hd_pause(request: Request):
    q.pause()
    return _tra(request, ok="⏸ Đã tạm dừng hàng đợi")


@app.post("/hangdoi/resume")
async def hd_resume(request: Request):
    q.resume()
    return _tra(request, ok="▶ Chạy tiếp")


@app.post("/hangdoi/skip")
async def hd_skip(request: Request):
    q.skip_current()
    return _tra(request, ok="⏭ Đã bỏ việc đang chạy")


@app.post("/hangdoi/stop")
async def hd_stop(request: Request):
    q.stop_all()
    return _tra(request, ok="⏹ Đã dừng hết")


@app.post("/hangdoi/bo/{jid}")
async def hd_bo(jid: int, request: Request):
    q.remove(jid)
    return _tra(request, ok="Đã bỏ việc khỏi hàng đợi")


@app.post("/hangdoi/power")
async def hd_power(request: Request):
    """Ô “Xong hết thì ngủ/tắt máy” — htmx gửi lên là trả lại ngay khối hàng đợi."""
    form = await request.form()
    power.arm(bool(form.get("on")), form.get("mode") or "")
    return _tra(request)


# ── 📤 ĐĂNG BÀI: YouTube + Facebook theo HỒ SƠ KÊNH ──────────────────────────
# Nhiều tài khoản quản lý dễ: mỗi kênh một thư mục myvideo/kenh/<tên>/ chứa
# trọn token + sổ sách (xem myvideo/kenh_hoso.py); trang có ô chọn kênh đang
# dùng + nút tạo kênh mới. Hồ sơ chưa cấu hình thì nút đăng khoá kèm dòng "⏳"
# nói rõ bước cần làm — tách hẳn kênh MimiAudio của myvoice, không có đường
# lui nào sang bên đó.
from datetime import datetime as _dt            # noqa: E402

for _p in (str(BASE_DIR), str(BASE_DIR / "YOUTUBE")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import dang_video_youtube as mvyt    # noqa: E402
import kenh_hoso as kh               # noqa: E402

# Script Facebook nạp theo đường dẫn (không đặt myvideo/FACEBOOK vào sys.path —
# kẻo trùng tên module với bản của myvoice nếu sau này cùng tiến trình).
import importlib.util                # noqa: E402

_fb_spec = importlib.util.spec_from_file_location(
    "mv_dang_facebook", str(BASE_DIR / "FACEBOOK" / "dang_video_facebook.py"))
mvfb = importlib.util.module_from_spec(_fb_spec)
_fb_spec.loader.exec_module(mvfb)


def _dang_ctx() -> dict:
    """Context khối 📤 Đăng bài — dựng từ FILE (sổ + cache của HỒ SƠ KÊNH đang
    chọn), không gọi API nào.

    Ngày dự kiến đăng Page tính bằng ĐÚNG plan_slots/known_busy của script —
    bảng nói một đằng Facebook nhận một nẻo là kiểu sai khó chịu nhất."""
    s = load_settings()
    ten = kh.hien_tai()

    # ── YouTube của hồ sơ đang chọn ──────────────────────────────────────────
    yt_thieu = kh.yt_thieu(ten)
    yt_note = ""
    if ten and not yt_thieu:
        mvyt.chon_kenh(kh.thu_muc(ten), kh.client_secret(ten))
        data = mvyt.load_video_cache()
        entry = data["channels"].get(data.get("current"))
        if entry:
            ch = entry.get("channel", {})
            try:
                yt_note = (f"Kênh: {ch.get('title', '?')} · "
                           f"{ch.get('video_count', 0)} video · khung trống kế tiếp "
                           f"{mvyt.next_publish_slot():%d/%m %H:%M}")
            except Exception:
                yt_note = f"Kênh: {ch.get('title', '?')}"
        else:
            yt_note = "Đã đăng nhập — bấm 🔑 lần nữa để đọc thông tin kênh."

    # ── Facebook của hồ sơ đang chọn ─────────────────────────────────────────
    fb_thieu = kh.fb_thieu(ten)
    fb_cooldown, fb_dadang, fb_synced = "", 0, ""
    slots, fb_cho_bases, fb_dukien = [], set(), {}
    if ten:
        mvfb.chon_kenh(ten)                     # trỏ sổ/cache vào hồ sơ này
        until, ly_do = mvfb.cooldown_left()
        if until:
            fb_cooldown = f"⏸ Đang tạm ngưng gọi Facebook tới {until:%H:%M} — {ly_do}"
        led = mvfb.load_ledger()
        cache = mvfb.load_cache()
        fb_dadang = len(led.get("eps") or {})
        fb_synced = (led.get("synced") or "")[:16].replace("T", " ")
        fb_cho, _ = mvfb.pending_videos(led)
        fb_dukien = {it["base"]: when for it, when in
                     zip(fb_cho, mvfb.plan_slots(len(fb_cho), None,
                                                 mvfb.known_busy(led, cache)))}
        fb_cho_bases = {it["base"] for it in fb_cho}
        # Lịch đang chờ trên Page (bản đọc ở lần 🔄 gần nhất) — mốc còn tương lai.
        for sl in cache.get("slots") or []:
            try:
                t = _dt.fromisoformat(str(sl.get("when")))
            except (TypeError, ValueError):
                continue
            if t > _dt.now():
                slots.append({"when": t, "ep": sl.get("ep")})
        slots.sort(key=lambda x: x["when"])

    # Video đã dựng xong (bước ④) — trạng thái đăng tính THEO hồ sơ đang chọn
    # (biên nhận ghi theo kênh: video lên kênh A vẫn là "chưa" với kênh B).
    rows = [r for r in st.scan_rows(limit=100) if r["sub"]]
    rows.reverse()                              # cũ trước, khớp thứ tự sẽ đăng
    table = []
    for r in rows:
        yt_r = bool(ten and kenh_bien_nhan_yt(r["base"], ten))
        table.append({"base": r["base"], "ten": mvfb.ten_hienthi(r["base"]),
                      "seo": r["seo"], "thumb": r["thumb"], "yt": yt_r,
                      "fb": bool(ten) and r["base"] not in fb_cho_bases,
                      "fb_when": fb_dukien.get(r["base"])})

    return {"settings": s, "dang": {
        "kenh": ten, "kenhs": kh.danh_sach(), "kenh_dir": str(kh.KENH_DIR),
        "yt_thieu": yt_thieu, "yt_note": yt_note,
        "categories": mvyt.CATEGORIES,
        "fb_thieu": fb_thieu, "fb_cooldown": fb_cooldown,
        "fb_dadang": fb_dadang, "fb_synced": fb_synced,
        "slots": slots, "rows": table,
        "qd": q_dang.state(), "qd_log": tail_dang.tail(8),
        "qf": q_fb.state(), "qf_log": tail_fb.tail(8),
        # Còn việc (đang chạy HOẶC chờ) ở một trong hai hàng đăng → khối tự vẽ
        # lại 5 giây/lần; rảnh thì bản vẽ mới không còn hx-get, vòng tự tắt.
        "ban": q_dang.busy() or q_fb.busy(),
    }}


def kenh_bien_nhan_yt(base: str, ten: str) -> dict | None:
    """Mục biên nhận YouTube của kênh `ten` cho một video (None = chưa đăng)."""
    return kh.doc_bien_nhan(OUTPUT_DIR / f"{base}_youtube_upload.json").get(ten)


def _queue_after_build(base: str) -> None:
    """Hook của steps: xong bước ④ một video → tự xếp việc đăng NẾU ô tự động
    đang bật VÀ hồ sơ kênh đang chọn đã cấu hình. Chưa cấu hình thì chỉ ghi một
    dòng nhắc — tuyệt đối không có đường lui sang kênh của myvoice."""
    s = load_settings()
    ten = kh.hien_tai()
    if s.get("auto_dang"):
        thieu = kh.yt_thieu(ten)
        if thieu:
            tail_dang.add(f"⏳ Bỏ tự đăng YouTube ({Path(base).name}): {thieu}")
        else:
            title, job_steps = st.youtube_steps(base, ten)
            q_dang.enqueue(title, job_steps)
    if s.get("fb_auto"):
        thieu = kh.fb_thieu(ten)
        if thieu:
            tail_fb.add(f"⏳ Bỏ tự lên lịch Facebook ({Path(base).name}): {thieu}")
        else:
            title, job_steps = st.facebook_steps("chay", ten, [base])
            q_fb.enqueue(title, job_steps)


st.after_build_hook = _queue_after_build


def _chon_from(form) -> list[str]:
    """Các ô tick trong bảng đăng bài (name=chon, value=base) — lọc tên hợp lệ."""
    return [b for b in form.getlist("chon") if st.is_base(b)]


@app.get("/partials/dang", response_class=HTMLResponse)
async def partial_dang(request: Request):
    return templates.TemplateResponse(request, "_dang.html", _dang_ctx())


def _save_dang_form(form) -> None:
    """Cài đặt của khối 📤 — nút 💾 lẫn MỌI nút chạy trong khối đều lưu (nếp
    "bấm chạy cũng là lưu" của cả hai web). Các checkbox đều nằm trong form
    #dangform nên vắng mặt = bỏ tick, suy được ý định."""
    g = form.get
    save_settings({
        # Hồ sơ kênh đang dùng — chỉ nhận tên có thật trong myvideo/kenh/.
        "kenh": g("kenh") if g("kenh") in kh.danh_sach() else "",
        "yt_category": (g("yt_category")
                        if str(g("yt_category")) in set(mvyt.CATEGORIES.values())
                        else "22"),
        "yt_privacy": (g("yt_privacy")
                       if g("yt_privacy") in ("schedule", "public", "unlisted")
                       else "schedule"),
        "yt_kids": bool(g("yt_kids")),
        "yt_ai": bool(g("yt_ai")),
        "seo_kenh": (g("seo_kenh") or "").strip()[:80],
        "auto_dang": bool(g("auto_dang")),
        "fb_auto": bool(g("fb_auto")),
    })


@app.post("/dang/luu")
async def dang_luu(request: Request):
    _save_dang_form(await request.form())
    return _tra(request, ok="Đã lưu cài đặt đăng bài", luu=True)


@app.post("/kenh/tao")
async def kenh_tao(request: Request):
    """Tạo hồ sơ kênh mới (thư mục + facebook.json mẫu) rồi CHỌN LUÔN nó."""
    form = await request.form()
    ten = (form.get("tenmoi") or "").strip()
    loi = kh.tao(ten)
    if loi:
        return _tra(request, loi)
    save_settings({"kenh": ten})
    return _tra(request, ok=f"📡 Đã tạo hồ sơ kênh “{ten}” và chọn làm kênh đang "
                            f"dùng — điền facebook.json + 🔑 đăng nhập YouTube là xong",
                luu=True)


@app.post("/dang/youtube")
async def dang_youtube(request: Request):
    form = await request.form()
    _save_dang_form(form)
    ten = kh.hien_tai()
    thieu = kh.yt_thieu(ten)
    if thieu:
        return _tra(request, f"⏳ YouTube của hồ sơ kênh chưa sẵn sàng: {thieu}")
    chon = _chon_from(form)
    if not chon:                    # không tick ô nào = mọi video KÊNH NÀY chưa đăng
        chon = [r["base"] for r in st.scan_rows(limit=200)
                if r["sub"] and not kenh_bien_nhan_yt(r["base"], ten)]
        chon.reverse()              # cũ trước — thứ tự lên sóng khớp thứ tự dựng
    if not chon:
        return _tra(request, ok=f"Kênh “{ten}” không còn video nào chờ đăng YouTube")
    for b in chon:
        title, job_steps = st.youtube_steps(b, ten)
        q_dang.enqueue(title, job_steps)
    return _tra(request, ok=f"⬆ Đã xếp {len(chon)} video vào hàng đợi đăng "
                            f"YouTube (kênh “{ten}”)")


@app.post("/dang/youtube/dangnhap")
async def dang_youtube_dangnhap(request: Request):
    form = await request.form()
    _save_dang_form(form)
    ten = kh.hien_tai()
    if not ten:
        return _tra(request, "⏳ Chưa chọn hồ sơ kênh nào — tạo/chọn ở đầu khối Đăng bài.")
    if not kh.client_secret(ten).exists():
        return _tra(request, f"⏳ Chưa có client_secret.json — tải OAuth client từ "
                             f"Google Cloud Console rồi đặt vào {kh.KENH_DIR} "
                             f"(dùng chung) hoặc {kh.thu_muc(ten)} (riêng hồ sơ này)")
    title, job_steps = st.youtube_login_steps(ten, bool(form.get("doikenh")))
    # light: lượt đăng nhập không được kích hoạt "🌙 xong hết thì ngủ".
    q_dang.enqueue(title, job_steps, light=True)
    return _tra(request, ok=f"🔑 Đã xếp lượt đăng nhập cho hồ sơ “{ten}” — trình "
                            "duyệt sẽ mở, nhớ chọn ĐÚNG kênh của hồ sơ này")


@app.post("/dang/facebook/{mode}")
async def dang_facebook(mode: str, request: Request):
    if mode not in ("chay", "xemtruoc", "quet"):
        return _tra(request, f"Chế độ không hợp lệ: {mode}")
    form = await request.form()
    _save_dang_form(form)
    ten = kh.hien_tai()
    thieu = kh.fb_thieu(ten)
    if thieu:
        return _tra(request, f"⏳ Facebook của hồ sơ kênh chưa sẵn sàng: {thieu}.")
    chon = _chon_from(form) if mode == "chay" else []
    title, job_steps = st.facebook_steps(mode, ten, chon)
    # 🔍/🔄 là việc NHẸ — không kích hoạt 🌙 (học JobRunner.heavy_busy myvoice).
    q_fb.enqueue(title, job_steps, light=(mode != "chay"))
    return _tra(request, ok=f"Đã xếp: {title}")


@app.post("/seo")
async def seo_chay(request: Request):
    form = await request.form()
    chon = _chon_from(form)
    if not chon and st.is_base(form.get("base") or ""):
        chon = [form.get("base")]           # nút 📑 trên một hàng của bảng
    if not chon:
        return _tra(request, "Chưa chọn video nào để sinh SEO.")
    title, job_steps = st.seo_steps(chon, force=bool(form.get("force")))
    # Hàng đợi CHÍNH: SEO dùng chung phiên Gemini (extension/Firefox) với bước ②
    # — chạy song song là giẫm nhau nên phải xếp nối tiếp.
    q.enqueue(title, job_steps)
    return _tra(request, ok=f"Đã xếp: {title} — dùng Gemini nên xếp ở hàng đợi chính")


@app.post("/thumb")
async def thumb_chay(request: Request):
    form = await request.form()
    chon = _chon_from(form)
    if not chon and st.is_base(form.get("base") or ""):
        chon = [form.get("base")]
    if not chon:
        return _tra(request, "Chưa chọn video nào để vẽ thumbnail.")
    title, job_steps = st.thumb_steps(chon, force=bool(form.get("force")))
    q.enqueue(title, job_steps)
    return _tra(request, ok=f"Đã xếp: {title}")


_Q_DANG = {"dang": q_dang, "fb": q_fb}


@app.post("/hangdoi2/{which}/{action}")
async def hd2(which: str, action: str, request: Request):
    """Điều khiển hai hàng đợi đăng — cùng bộ nút với hàng đợi chính."""
    runner = _Q_DANG.get(which)
    acts = {"pause": ("⏸ Đã tạm dừng", lambda r: r.pause()),
            "resume": ("▶ Chạy tiếp", lambda r: r.resume()),
            "skip": ("⏭ Đã bỏ việc đang chạy", lambda r: r.skip_current()),
            "stop": ("⏹ Đã dừng hết", lambda r: r.stop_all())}
    if runner is None or action not in acts:
        return _tra(request, "Lệnh không hợp lệ")
    msg, fn = acts[action]
    fn(runner)
    return _tra(request, ok=msg + (" (hàng đăng YouTube)" if which == "dang"
                                   else " (hàng Facebook)"))


# ── 🔊 Nghe thử: giọng mẫu + audio tiếng Việt đã xếp ─────────────────────────
def _nghe_thu_giong(src: Path, sang) -> Path:
    """File cho ô 🔊 Nghe thử khối ③: mức 🔆 sáng giọng > 0 → bản giọng mẫu ĐÃ QUA
    EQ ở mức đó (ffmpeg một lần, cache ở voice/_nghe_thu/, làm lại khi file mẫu
    mới hơn) — nghe là biết mức đang kéo ra sao, khỏi tốn một lượt chạy ③. Chỉ là
    XEM TRƯỚC GẦN ĐÚNG: bài thật còn EQ thêm lúc dựng prompt rồi EQ audio tổng.
    File mẫu gốc không đổi. Mức 0 hay ffmpeg hỏng → trả file gốc."""
    muc = hu.parse_fx(sang)
    if muc <= 0:
        return src
    out = st.VOICE_DIR / "_nghe_thu" / f"{src.name}_sang{muc}.wav"
    try:
        if not out.is_file() or out.stat().st_mtime < src.stat().st_mtime:
            out.parent.mkdir(exist_ok=True)
            hu.apply_fx_file(src, out, sang_giong=muc)
        return out
    except Exception:
        return src


@app.get("/nghe/giong")
async def nghe_giong(ten: str = "", sang: str = "0"):
    """Stream file giọng mẫu trong kho (myvoice/voice/giong_mau, kho cũ myvideo/voice) — tên phải có trong kho.
    sang > 0: bản đã EQ 🔆 sáng giọng ở mức đó (xem _nghe_thu_giong)."""
    src = st.voice_path(ten)
    if src is None:
        return JSONResponse({"error": "không có giọng này trong myvoice/voice/giong_mau hay myvideo/voice"},
                            status_code=404)
    f = _nghe_thu_giong(src, sang)
    return FileResponse(str(f), media_type="audio/wav" if f.suffix == ".wav" else None)


# ── 🎧 Nghe thử CÀI ĐẶT giọng bước ③ (09/11/2026, mang từ myvoice sang) ─────────
# Khác ô 🔊 nghe giọng mẫu ở trên (phát file mẫu sẵn có): ở đây áp tông +
# bộ lọc + chuẩn âm + âm lượng ĐANG HIỆN trên form (chưa cần lưu) lên ~30 s giọng THẬT
# của một video đã tạo giọng, bằng đúng hàm hậu kỳ của bước ③ (taogiong_srt.hau_ky_audio).
# Mẫu + cách chọn video + chỗ lưu: myvideo/taogiong_nghethu_srt.py.
def _nghethu_mod():
    """Module nghe thử của myvideo (nạp trễ: kéo theo amain_taogiong_gui của myvoice)."""
    import taogiong_nghethu_srt as nt    # myvideo/ đã trong sys.path (xem phần import kenh_hoso)
    return nt


def _nghethu_nhan() -> str:
    """Dòng 'Mẫu: video … · 31 s · giọng …' cạnh nút 🎧 lúc mở trang (chỉ đọc mau_goc.json)."""
    try:
        nt = _nghethu_mod()
        return nt.nhan_mau(nt.doc_mau())
    except Exception:
        return ""


@app.post("/nghethu")
def nghethu(pitch: str = Form(""), vang_truong_do: str = Form(""), vang_cuong_do: str = Form(""),
            thieu_nien: str = Form(""), sanggiong: str = Form(""), am_luong_db: str = Form(""),
            engine: str = Form(""), giong_vieneu: str = Form(""), voice: str = Form("")):
    """Áp cài đặt đang hiện lên mẫu rồi trả đường phát (route này KHÔNG ghi web_settings.json).
    `def` thường (không async) để FastAPI chạy ở luồng phụ — ffmpeg mất 1–3 giây."""
    try:
        nt = _nghethu_mod()
    except Exception as e:
        return JSONResponse({"ok": False, "loi": f"Chưa nạp được bộ nghe thử: {e}"}, status_code=500)
    fx = dict(vang_truong_do=vang_truong_do, vang_cuong_do=vang_cuong_do,
              thieu_nien=thieu_nien, sang_giong=sanggiong)
    try:
        kq = nt.nghe_thu(pitch=pitch, fx=fx, am_luong=am_luong_db, log=print)
    except nt.ChuaCoMau as e:
        return JSONResponse({"ok": False, "loi": str(e)})
    except Exception as e:
        print(f"⚠️ Nghe thử lỗi: {e}")
        return JSONResponse({"ok": False, "loi": f"Không dựng được bản nghe thử: {e}"}, status_code=500)
    mau = kq["mau"]
    ghi_chu = []
    # Mẫu đọc bằng engine/giọng khác giọng đang chọn trên form (chỉ biết với video tạo từ 04/11/2026).
    mode_mau, ten_mau = nt.che_do_giong(mau.get("giong"))
    mode_chon = "vieneu" if engine == "vieneu" else "clone"
    dang_chon = giong_vieneu if mode_chon == "vieneu" else voice
    if mode_mau:
        khac_engine = (mode_mau == "vieneu") != (mode_chon == "vieneu")
        if khac_engine or (dang_chon and ten_mau and Path(ten_mau).name != Path(dang_chon).name):
            ghi_chu.append(f"Mẫu đọc bằng giọng “{nt.ten_giong(mau.get('giong')) or mode_mau}”, khác "
                           "giọng đang chọn — chạy bước ③ video đầu đợt bằng giọng mới thì mẫu đổi theo.")
    # OmniVoice: mức 🔆 còn EQ giọng mẫu lúc SINH câu — phần đó mẫu giữ ở mức cũ.
    sang = hu.parse_fx(sanggiong)
    if mode_mau == "clone" and sang != int(mau.get("sang_goc") or 0):
        ghi_chu.append(f"Mẫu sinh lúc Sáng giọng {int(mau.get('sang_goc') or 0)}; bài thật ở mức "
                       f"{sang} còn EQ cả giọng mẫu nên sẽ khác đôi chút.")
    return JSONResponse({
        "ok": True,
        "url": "/nghe/caidat?f=" + quote(kq["file"].name),
        "mau": nt.nhan_mau(mau), "mo_ta": kq["mo_ta"], "ghi_chu": ghi_chu,
        "van_ban": mau.get("van_ban", ""),
    })


@app.get("/nghe/caidat")
async def nghe_caidat(f: str = ""):
    """Phát một bản 🎧 đã áp cài đặt (chỉ nhận đúng tên xt_<mã>.wav trong thư mục mẫu)."""
    try:
        nt = _nghethu_mod()
    except Exception as e:
        return JSONResponse({"error": f"chưa nạp được bộ nghe thử: {e}"}, status_code=500)
    if not nt.la_ban_nghe(f):
        return JSONResponse({"error": "tên bản nghe thử không hợp lệ"}, status_code=404)
    p = nt.MAU_DIR / f
    if not p.is_file():
        return JSONResponse({"error": "bản nghe thử này đã bị dọn — bấm 🎧 lại"}, status_code=404)
    return FileResponse(str(p), media_type="audio/wav")


@app.get("/kenh/logo")
async def kenh_logo(ten: str = ""):
    """Ảnh logo trong thư mục HỒ SƠ KÊNH đang chọn — xem trước cạnh ô chọn logo
    ở khối ④. Chỉ trả file nằm trong danh sách logos() của hồ sơ."""
    p = kh.logo_path(kh.hien_tai(), ten)
    if p is None or not p.is_file():
        return JSONResponse({"error": "hồ sơ kênh chưa có logo"}, status_code=404)
    return FileResponse(str(p))


@app.get("/nghe/ketqua")
async def nghe_ketqua(base: str = ""):
    """Audio tiếng Việt đã xếp timeline (<base>_vi_audio.wav) — nghe duyệt
    giọng TRƯỚC khi tốn thời gian dựng bước ④."""
    if not st.is_base(base):
        return JSONResponse({"error": f"tên không hợp lệ: {base}"}, status_code=404)
    f = Path(f"{OUTPUT_DIR / base}_vi_audio.wav")
    if not f.is_file():
        return JSONResponse({"error": "chưa có audio — chạy bước ③ trước"},
                            status_code=404)
    return FileResponse(str(f), media_type="audio/wav")


# ── Xoá output: CHỈ đưa vào Thùng rác, có xác nhận ở trình duyệt ─────────────
@app.post("/xoa")
async def xoa(request: Request, base: str = Form(...)):
    if not st.is_base(base):
        return _tra(request, f"Tên không hợp lệ: {base}")
    if q.busy():
        return _tra(request, "Hàng đợi đang chạy — dừng hết trước rồi hãy xoá "
                             "(file có thể đang được ghi).")
    # Xoá ở bảng = dọn SẠCH video đó khỏi output (xem _tep_xoa): cả file từng đoạn của
    # video dài, và — khi video không còn gốc nào khác — bản thử + clip của 🎛 Chỉnh trước.
    files, het = _tep_xoa(base)
    if not files:
        return _tra(request, f"{base}: không thấy file nào trong output.")
    khoa = _ct_khoa(base)
    for p in files:                     # bản xem trước thu nhỏ của clip thử: bỏ khi clip còn đó
        if p.is_file() and p.suffix.lower() == ".mp4":
            ct.bo_xem_truoc(p)
    ok, fail = st.recycle(files, on_log=q.note)
    if het:
        _quen_video(khoa)
    q.note(f"🗑 {base}: đã đưa {ok} mục vào Thùng rác"
           + (f", {fail} mục KHÔNG xoá được" if fail else "")
           + " — khôi phục: mở Thùng rác Windows.")
    return _tra(request, f"{base}: {fail} mục không đưa vào Thùng rác được — "
                         "xem nhật ký." if fail else "",
                ok=f"🗑 {base}: đã đưa {ok} mục vào Thùng rác",
                bao={"mvid:daxoa": {"khoa": khoa}} if het else None)


@app.post("/xoa-thu")
async def xoa_thu(request: Request, ten: str = Form(...)):
    """🗑 của hàng "🧪 chỉ có bản thử / chỉ còn clip": dọn TRỌN đồ 🎛 Chỉnh trước của video
    tên `ten` trong output — thư mục thử (mọi tốc độ) + clip 3 phút đã cắt."""
    files = _tep_thu_ten(ten)
    if not files:
        return _tra(request, f"{ten}: không thấy bản thử nào trong output.")
    if q.busy():
        return _tra(request, "Hàng đợi đang chạy — dừng hết trước rồi hãy xoá "
                             "(file có thể đang được ghi).")
    for p in files:
        if p.is_file():
            ct.bo_xem_truoc(p)          # bản xem trước thu nhỏ của clip: bỏ khi clip còn đó
    ok, fail = st.recycle(files, on_log=q.note)
    khoa = st.tenchinh(ten)
    _quen_video(khoa)
    q.note(f"🗑 {ten}: đã đưa {ok} mục bản thử vào Thùng rác"
           + (f", {fail} mục KHÔNG xoá được" if fail else "")
           + " — khôi phục: mở Thùng rác Windows.")
    return _tra(request, f"{ten}: {fail} mục không đưa vào Thùng rác được — "
                         "xem nhật ký." if fail else "",
                ok=f"🗑 {ten}: đã đưa {ok} mục bản thử vào Thùng rác",
                bao={"mvid:daxoa": {"khoa": khoa}})


@app.post("/xoa-het")
async def xoa_het(request: Request):
    if q.busy():
        return _tra(request, "Hàng đợi đang chạy — dừng hết trước rồi hãy xoá "
                             "(file có thể đang được ghi).")
    try:
        files = list(OUTPUT_DIR.iterdir())
    except OSError:
        files = []
    if not files:
        return _tra(request, "Thư mục output đang trống.")
    ok, fail = st.recycle(files, on_log=q.note)
    q.note(f"🗑 Đã đưa {ok} mục của output vào Thùng rác"
           + (f", {fail} mục KHÔNG xoá được" if fail else "")
           + " — khôi phục: mở Thùng rác Windows.")
    return _tra(request, f"{fail} mục không đưa vào Thùng rác được — xem nhật ký."
                if fail else "", ok=f"🗑 Đã đưa {ok} mục của output vào Thùng rác")


def _video_xong(base: str) -> Path | None:
    """Video HOÀN THÀNH của bước ④: _sub.mp4, không có thì bản dọc _doc.mp4. Không bao
    giờ trả video ① (chưa có sub/giọng — mở ra user tưởng là thành phẩm)."""
    B = OUTPUT_DIR / base
    return next((p for p in (Path(f"{B}_sub.mp4"), Path(f"{B}_doc.mp4")) if p.is_file()), None)


def _video_de_xem(base: str) -> Path | None:
    """File nên bôi chọn khi mở thư mục của một video: thành phẩm bước ④ trước
    (_sub.mp4, rồi bản dọc _doc.mp4), chưa dựng thì video đã làm chậm của bước ①."""
    v1 = Path(f"{OUTPUT_DIR / base}.mp4")
    return _video_xong(base) or (v1 if v1.is_file() else None)


@app.post("/mo-video")
async def mo_video(request: Request, base: str = Form("")):
    """▶ Xem video (cột ④ của bảng, 25/11/2026): mở video HOÀN THÀNH của một hàng bằng
    trình phát mặc định của Windows — khỏi 📂 mở thư mục rồi bấm đúp. Phát trong trình
    phát của máy chứ không trong trang: thành phẩm là file vài GB, trình phát của máy
    tua/đọc codec nào cũng được. Đang dựng lại thì từ chối (file đang bị ghi đè dở)."""
    if not st.is_base(base):
        return _tra(request, f"Tên không hợp lệ: {base}")
    ten = Path(base).name
    f = _video_xong(base)
    if f is None:
        return _tra(request, f"{ten}: chưa có video hoàn thành ({ten}_sub.mp4) — chạy bước ④ trước.")
    if _dang_dung(base, q.state()) == "chay":
        return _tra(request, f"{ten}: bước ④ đang dựng lại và ghi đè {f.name} — chờ dựng xong "
                             "(xem tab ⏱ Hàng đợi) rồi hãy mở.")
    try:
        os.startfile(str(f))                   # noqa: S606 — máy cục bộ, cố ý
    except Exception as e:
        return _tra(request, f"Không mở được {f.name}: {e}")
    return _tra(request, ok=f"▶ Đã mở {f.name} bằng trình phát video của Windows")


@app.post("/mo-thumuc")
async def mo_thumuc(request: Request, base: str = Form("")):
    """Không có `base`: mở cả thư mục output (nút ở đầu bảng). Có `base` (nút 📂
    của TỪNG video, 15/11/2026): mở thư mục riêng của video đó và BÔI CHỌN sẵn
    video thành phẩm — bấm đúp là xem, khỏi dò giữa chục file srt/wav/json."""
    if not base:
        OUTPUT_DIR.mkdir(exist_ok=True)
        try:
            os.startfile(str(OUTPUT_DIR))      # noqa: S606 — máy cục bộ, cố ý
        except Exception as e:
            return _tra(request, f"Không mở được thư mục: {e}")
        return _tra(request, ok="📂 Đã mở thư mục output")
    if not st.is_base(base):
        return _tra(request, f"Tên không hợp lệ: {base}")
    folder = (OUTPUT_DIR / base).parent
    if not folder.is_dir():
        return _tra(request, f"{base}: thư mục không còn trong output.")
    chon = _video_de_xem(base)
    try:
        if chon is not None:
            # Chuỗi lệnh tự ghép (không phải list): explorer đòi đúng dạng
            # /select,"đường dẫn" — để subprocess tự bọc nháy thì đường dẫn có
            # dấu phẩy mà không có dấu cách sẽ bị explorer cắt ở dấu phẩy.
            subprocess.Popen(f'explorer /select,"{chon}"')
        else:
            os.startfile(str(folder))          # noqa: S606 — máy cục bộ, cố ý
    except Exception as e:
        return _tra(request, f"Không mở được thư mục: {e}")
    return _tra(request, ok=f"📂 Đã mở thư mục {folder.name}"
                + (f" — đang chọn sẵn {chon.name}" if chon else ""))


@app.get("/api/trangthai")
async def trangthai():
    """Cho launcher/công cụ ngoài hỏi nhanh: hàng đợi + chế độ ⏻/🌙 + nhật ký cuối."""
    return JSONResponse({**q.state(), "power": power.state(), "lines": tail.tail(30)})


# ── Khởi động ───────────────────────────────────────────────────────────────
# Cổng mặc định bận (myvoice cũng mặc định 8766) thì dò tiếp 8767, 8768, … tối đa
# chừng này cổng. Launcher myvideo/chay.py dùng CÙNG số + cùng cách chọn (_chon_cong).
SO_CONG_THU = 20
# Cổng dùng lần gần nhất (launcher cũng ghi vào đây) — lần sau thử cổng này TRƯỚC:
# bị đẩy sang 8767 một lần là về sau cứ ở 8767, địa chỉ web không đổi, khỏi dò
# lại từ đầu mỗi lần bật. Xoá file = quay về dò từ cổng mặc định.
CONG_FILE = WEB_DIR / "cong.txt"


def _is_myvideo(port: int, timeout: float = 1.0) -> bool:
    """Cái đang nghe ở cổng có ĐÚNG là bảng web myvideo không (hỏi /api/ping) —
    myvoice cũng mặc định 8766, chỉ dò "cổng bận" thì tưởng mình đang chạy sẵn."""
    from urllib.request import urlopen
    try:
        with urlopen(f"http://127.0.0.1:{port}/api/ping", timeout=timeout) as r:
            return json.load(r).get("app") == "myvideo"
    except Exception:
        return False


def _cong_trong(port: int) -> bool:
    """Cổng còn trống không — BIND THỬ, không connect.

    Bind được ở đây = server ngay sau cũng bind được ("chưa ai nghe" theo connect
    chưa đủ: cổng có thể đã bị bind mà chưa listen). Và bind trả lời tức thì
    (~0,05 ms); connect tới cổng TRỐNG trên Windows lại chờ hết timeout (~0,4 s),
    quét 20 cổng kiểu đó mất ~8 s — chính là lý do trước đây bật bảng web lâu.
    """
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _cong_da_nho(uu_tien: int) -> int | None:
    """Cổng ghi trong CONG_FILE lần trước — chỉ tin khi còn nằm trong dải đang dò
    (đổi MYVIDEO_WEB_PORT sang dải khác thì bỏ qua số cũ). Không có/hỏng → None."""
    try:
        p = int(CONG_FILE.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    return p if uu_tien <= p < uu_tien + SO_CONG_THU else None


def _nho_cong(port: int) -> None:
    """Ghi cổng vừa chọn cho lần sau; ghi hỏng (ổ chỉ đọc…) thì thôi, không chết."""
    try:
        CONG_FILE.write_text(str(port), encoding="utf-8")
    except OSError:
        pass


def _chon_cong(uu_tien: int) -> tuple[int, bool]:
    """Chọn cổng cho bảng web → (cổng, myvideo_đã_chạy_sẵn_ở_đó).

    Thứ tự dò: cổng NHỚ từ lần trước (web/cong.txt) → cổng ưu tiên → phần còn lại
    của dải uu_tien … uu_tien+SO_CONG_THU-1.
    1) Đã có myvideo nghe sẵn ở cổng nào trong dải → trả cổng đó + True: dùng luôn,
       không bật cái thứ hai.
    2) Chưa có → cổng TRỐNG đầu tiên theo thứ tự trên. Cổng nhớ đứng đầu nên bị
       đẩy sang 8767 một lần là lần sau vào thẳng 8767, khỏi dò lại. Cổng ưu tiên
       bị chương trình KHÁC chiếm (myvoice chẳng hạn) thì tự nhảy cổng thay vì
       văng traceback "địa chỉ đang bận".
    Cổng chọn được GHI LẠI vào web/cong.txt. Cả dải đều bận → OSError.

    Dò bằng bind (tức thì) nên quét cả dải chỉ mất vài ms; chỉ cổng ĐANG bận mới
    phải hỏi /api/ping xem có phải mình không.
    """
    dai = range(uu_tien, uu_tien + SO_CONG_THU)
    nho = _cong_da_nho(uu_tien)
    thu_tu = ([nho] if nho is not None else []) + [p for p in dai if p != nho]
    trong = {p: _cong_trong(p) for p in thu_tu}
    for p in thu_tu:
        if not trong[p] and _is_myvideo(p):
            _nho_cong(p)
            return p, True
    for p in thu_tu:
        if trong[p] and _cong_trong(p):      # dò lại sát lúc chọn cho chắc
            _nho_cong(p)
            return p, False
    raise OSError(f"Không còn cổng trống trong khoảng {dai.start}–{dai[-1]} "
                  "(toàn bị chương trình khác chiếm). Đặt MYVIDEO_WEB_PORT sang dải khác.")


def _bao_doi_cong(uu_tien: int, port: int) -> str:
    """Câu báo khi cổng chọn ≠ cổng ưu tiên: do nhớ từ lần trước, hay do bị chiếm."""
    if _cong_trong(uu_tien):
        return (f"ℹ️ Dùng cổng {port} nhớ từ lần trước (cổng {uu_tien} đang trống — "
                f"xoá web/cong.txt nếu muốn quay về {uu_tien}).")
    return f"⚠️ Cổng {uu_tien} đang bị chương trình khác chiếm → dùng cổng {port}."


def main() -> None:
    import webbrowser

    import uvicorn

    uu_tien = int(os.environ.get("MYVIDEO_WEB_PORT", "8766"))
    # Bật lần hai khi đã chạy → mở lại trình duyệt rồi thoát. Cổng bị chương trình
    # KHÁC chiếm (myvoice cũng mặc định 8766) → tự dò cổng trống kế tiếp, không để
    # uvicorn văng traceback "địa chỉ đang bận".
    try:
        port, dang_chay = _chon_cong(uu_tien)
    except OSError as e:
        print(f"⛔ {e}", flush=True)
        raise SystemExit(2)
    url = f"http://127.0.0.1:{port}/?token={quote(TOKEN)}"
    if dang_chay:
        print(f"🌐 myvideo web đã chạy sẵn — mở lại: {url}", flush=True)
        if not os.environ.get("MYVIDEO_WEB_NO_OPEN"):
            webbrowser.open(url)
        return
    if port != uu_tien:
        print(_bao_doi_cong(uu_tien, port), flush=True)

    OUTPUT_DIR.mkdir(exist_ok=True)
    # Chép nhật ký hàng đợi ra tệp myvideo/web/nhatky/hangdoi_<ngày>.log (05/11/2026, cùng
    # cơ chế với myvoice — JobRunner dùng chung): server này thường chạy ẩn (pythonw), xong
    # mẻ còn tự ngủ/tắt máy, nên tệp là chỗ duy nhất đọc lại được vì sao một việc dừng.
    # Bật ở main() chứ không phải lúc import: test import server thì không sinh tệp.
    from myvoice.web.jobs import bat_nhat_ky_tep
    bat_nhat_ky_tep(WEB_DIR / "nhatky")
    # Ảnh xem trước kiểu phụ đề còn thiếu (kiểu mới thêm) → tự vẽ nền sau,
    # không chặn server; vẽ xong tải lại trang là thấy.
    threading.Thread(target=kieusub.taomau_thieu, daemon=True).start()
    print(f"🌐 myvideo web: {url}", flush=True)
    if not os.environ.get("MYVIDEO_WEB_NO_OPEN"):
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
