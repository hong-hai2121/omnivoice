# -*- coding: utf-8 -*-
"""⬇ Tải video Bilibili qua app Bili23 Downloader (mặc định: CHẤT LƯỢNG CAO NHẤT).

Dán link bilibili.com / b23.tv vào ô Nguồn của web myvideo là bước ⬇ này được
xếp TRƯỚC bước ①: nhờ app Bili23 Downloader (D:\\Python\\BBDown — GUI PySide6,
kèm MCP server HTTP cổng 23330) tải video về rồi dọn thành đúng file --out
(Downloads/<mã BV>.mp4), các bước ①→④ dùng tiếp như file local bình thường.

Vì sao đi QUA APP thay vì tự gọi API Bilibili: app giữ sẵn đăng nhập (chất
lượng cao nhất mà tài khoản xem được), tự chọn CDN, tự ghép luồng DASH bằng
ffmpeg, tự thử lại khi rớt mạng — toàn việc app đã làm tốt, ở đây chỉ ra lệnh.

- Chất lượng: mặc định KHÔNG chỉ định gì — app theo danh sách ưu tiên của người
  dùng (8K → … thấp dần), đúng nghĩa "cao nhất tải được"; chỉ ép container mp4.
  Thêm --chat-luong 360P / 480P / 720P / 1080P (05/11/2026) khi chỉ cần TIẾNG
  (kênh audio myvoice: nhận diện xong là hết việc của file) — tải nhanh, nhẹ đĩa.
  Video không có đúng mức đó thì lấy mức gần nhất KHÔNG VƯỢT yêu cầu (chon_muc).
- App chưa mở thì tự mở (pythonw trong .venv của app) rồi đợi MCP lên.
- File --out đã có thì bỏ qua, coi như xong — chạy lại vô hại.
- Đợt tải xong, hàng đợi myvoice gọi `--dong-app` (08/11/2026, user yêu cầu): đóng app
  NẾU chính script này đã mở nó (dấu PID ở %TEMP%\\omnivoice_bili23_tu_mo.json); app
  người dùng mở sẵn từ trước, hay PID đã thành tiến trình khác, thì để nguyên.

Dùng tay:  python myvideo/video_taibilibili.py <link> --out <file.mp4>
           thêm --chat-luong 360P để tải bản nhẹ;
           thêm --chi-phan-tich để chỉ xem link ra những tập nào (không tải).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

# Thư mục app Bili23 Downloader (repo + .venv của chính nó). Đổi chỗ thì đặt
# biến môi trường thay vì sửa code.
BBDOWN_DIR = Path(os.environ.get("OMNI_BBDOWN_DIR", r"D:\Python\BBDown"))
CFG_PATH = Path(os.environ.get("APPDATA", "")) / "Bili23 Downloader" / "config.json"
# Dấu "app do script này tự mở" (08/11/2026): mo_app() ghi PID + đường dẫn pythonw của app
# vào đây; cuối đợt tải, hàng đợi gọi `--dong-app` → chỉ đóng đúng tiến trình đó. Để ở
# %TEMP% vì myvoice lẫn myvideo cùng dùng một dấu, và khởi động lại máy là dấu cũ vô nghĩa.
DAU_TU_MO = Path(os.environ.get("OMNI_BILI23_DAU", "")
                 or Path(tempfile.gettempdir()) / "omnivoice_bili23_tu_mo.json")
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# Trạng thái task của app (DownloadStatus bên đó, đã hạ chữ) → nhãn tiếng Việt.
TRANG_THAI = {
    "queued": "xếp hàng", "parsing": "phân tích", "downloading": "đang tải",
    "paused": "tạm dừng (mở app bấm ▶ chạy tiếp)", "completed": "xong",
    "ffmpeg_queued": "chờ ffmpeg", "merging": "ghép hình + tiếng",
    "converting": "chuyển định dạng", "additional_processing": "xử lý thêm",
    "failed": "TẢI HỎNG", "ffmpeg_failed": "FFMPEG HỎNG",
}
HONG = {"failed", "ffmpeg_failed"}
# Task CÒN VIỆC (đang tải/ghép…) — `--dong-app` thấy còn thì chưa đóng app (task có thể của
# myvideo hay của người dùng tạo tay). paused/failed/completed không tính.
DANG_LAM = {"queued", "parsing", "downloading", "ffmpeg_queued", "merging", "converting",
            "additional_processing"}

# Mức chất lượng video của app (tên trong video_quality_map bên đó → mã qn của
# Bilibili; mã lớn hơn = nét hơn). Dùng để xếp hạng khi video thiếu mức được xin.
MUC_VIDEO = {"360P": 16, "480P": 32, "720P": 64, "1080P": 80, "AI": 100,
             "1080P+": 112, "1080P60": 116, "4K": 120, "4K_SDR": 122, "HDR": 125,
             "DOLBY_VISION": 126, "8K": 127}


class ThatBai(Exception):
    """Lỗi có lời giải thích sẵn cho người dùng — in ra rồi exit 1."""


def chuan_chat_luong(s) -> str:
    """Chữ ở --chat-luong → "auto" (cao nhất tải được) hoặc tên mức của app.
    Nhận cả "360", "360p", "360P"; mức lạ thì báo rõ thay vì âm thầm tải bản khác."""
    t = str(s or "").strip().upper().replace(" ", "")
    if t in ("", "AUTO"):
        return "auto"
    if t.isdigit():
        t += "P"
    if t in MUC_VIDEO:
        return t
    raise ThatBai(f"Không hiểu mức chất lượng '{s}' — dùng một trong: auto, "
                  + ", ".join(sorted(MUC_VIDEO, key=MUC_VIDEO.get)) + ".")


def chon_muc(yeu_cau: str, co_san) -> str:
    """Mức người dùng xin → mức sẽ gửi cho app, theo những mức video này THẬT SỰ có.

    App gặp mức video không có thì âm thầm nhảy về mức đầu danh sách của nó (thường
    là cao nhất) — xin 360P mà ra 1080P. Nên chọn sẵn ở đây: mức cao nhất KHÔNG
    VƯỢT yêu cầu; video chỉ có các mức cao hơn thì lấy mức thấp nhất đang có."""
    if yeu_cau == "auto":
        return "auto"
    co = [m for m in (co_san or []) if m in MUC_VIDEO]
    if not co or yeu_cau in co:
        return yeu_cau
    duoi = [m for m in co if MUC_VIDEO[m] <= MUC_VIDEO[yeu_cau]]
    return max(duoi, key=MUC_VIDEO.get) if duoi else min(co, key=MUC_VIDEO.get)


def doc_cau_hinh() -> tuple[str, str]:
    """→ (url MCP, token) từ config.json của app — app và web dùng CHUNG một
    file cấu hình nên không phải khai token ở đâu thêm."""
    try:
        mcp = json.loads(CFG_PATH.read_text(encoding="utf-8"))["MCP"]
    except (OSError, KeyError, ValueError) as e:
        raise ThatBai(f"Không đọc được cấu hình app Bili23 ({CFG_PATH}): {e}\n"
                      "   → Mở app Bili23 Downloader ít nhất một lần cho nó tự tạo.")
    if not mcp.get("mcp_enabled"):
        raise ThatBai("App Bili23 đang TẮT MCP server.\n"
                      "   → Mở app → Cài đặt → MCP → bật lên rồi chạy lại.")
    port, token = mcp.get("mcp_port", 23330), mcp.get("mcp_token", "")
    if not token:
        raise ThatBai("Config app chưa có mcp_token — mở app (nó tự sinh token) rồi chạy lại.")
    return f"http://127.0.0.1:{port}/mcp", token


def rpc(url: str, token: str, method: str, params: dict | None = None,
        timeout: float = 60.0) -> dict:
    """Một lệnh JSON-RPC tới MCP của app (giao thức stateless, khỏi handshake)."""
    body = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        body["params"] = params
    req = urllib.request.Request(
        url, json.dumps(body).encode("utf-8"),
        {"Content-Type": "application/json",
         "Accept": "application/json, text/event-stream",
         "Authorization": f"Bearer {token}"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise ThatBai("App Bili23 từ chối token (401) — app đang chạy với token "
                          "khác trong config. Đóng app mở lại rồi chạy lại bước này.")
        raise ThatBai(f"MCP Bili23 trả lỗi HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")
    if data.get("error"):
        raise ThatBai(f"MCP Bili23 báo lỗi: {data['error'].get('message', data['error'])}")
    return data.get("result") or {}


def goi_tool(url: str, token: str, name: str, arguments: dict,
             timeout: float = 120.0) -> dict:
    """tools/call → structuredContent; tool báo isError thì ném lời nhắn của nó."""
    res = rpc(url, token, "tools/call", {"name": name, "arguments": arguments},
              timeout=timeout)
    if res.get("isError"):
        text = " ".join(c.get("text", "") for c in res.get("content", [])
                        if c.get("type") == "text").strip()
        raise ThatBai(f"[{name}] {text or 'tool báo lỗi không lời nhắn'}")
    return res.get("structuredContent") or {}


def cho_mcp(url: str, token: str, han: float) -> bool:
    """Ping tới khi MCP trả lời (app mở xong) hoặc hết hạn."""
    moc = time.monotonic() + han
    while time.monotonic() < moc:
        try:
            rpc(url, token, "ping", timeout=3.0)
            return True
        except ThatBai:
            raise                      # 401/lỗi giao thức: đợi thêm cũng vô ích
        except Exception:
            time.sleep(2.0)
    return False


def mo_app() -> None:
    """App chưa chạy → tự mở GUI (pythonw của .venv bên đó, không hiện console)."""
    pyw = BBDOWN_DIR / ".venv" / "Scripts" / "pythonw.exe"
    main = BBDOWN_DIR / "src" / "main.py"
    if not pyw.is_file() or not main.is_file():
        raise ThatBai(f"Không thấy app Bili23 ở {BBDOWN_DIR} (đặt OMNI_BBDOWN_DIR "
                      "nếu để chỗ khác) — mở app bằng tay rồi chạy lại.")
    print("🚀 App Bili23 chưa mở — đang mở giúp…", flush=True)
    proc = subprocess.Popen([str(pyw), str(main)], cwd=str(BBDOWN_DIR),
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    _ghi_dau_tu_mo(proc.pid, pyw)


def _ghi_dau_tu_mo(pid: int, exe: Path) -> None:
    """Ghi dấu "app do mình mở" (PID + exe) cho `--dong-app` đọc lại ở cuối đợt tải.
    Không ghi được thì chỉ mất tính năng tự đóng — việc tải vẫn chạy."""
    try:
        DAU_TU_MO.write_text(json.dumps({"pid": int(pid), "exe": str(exe),
                                         "luc": time.strftime("%Y-%m-%d %H:%M:%S")}),
                             encoding="utf-8")
    except OSError:
        pass


def _xoa_dau_tu_mo() -> None:
    try:
        DAU_TU_MO.unlink()
    except OSError:
        pass


def _duong_dan_exe(pid: int) -> str:
    """Đường dẫn exe của tiến trình `pid` — "" nếu đã chết hoặc không xem được (Windows API,
    không cần psutil). Dùng để chắc PID trong dấu VẪN là pythonw của app, chưa bị cấp lại."""
    if sys.platform != "win32":
        return ""
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x1000, False, int(pid))        # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        n = wintypes.DWORD(len(buf))
        if not k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
            return ""
        return buf.value
    finally:
        k32.CloseHandle(h)


def _taskkill(pid: int, ep: bool) -> None:
    """taskkill /T luôn: pythonw của .venv chỉ là bộ phóng, cửa sổ app nằm ở pythonw CON
    (bản gốc), nên phải đi cả cây. Không /F = gửi WM_CLOSE (app tự lưu rồi thoát);
    ep=True = thêm /F ép diệt (ffmpeg con nếu còn)."""
    cmd = ["taskkill", "/PID", str(pid), "/T"] + (["/F"] if ep else [])
    try:
        subprocess.run(cmd, capture_output=True, creationflags=CREATE_NO_WINDOW)
    except Exception:
        pass


def _task_dang_lam():
    """Số task của app CÒN VIỆC (list_tasks state=downloading, lọc theo DANG_LAM) — None nếu
    không hỏi được MCP (app treo/tắt MCP: đằng nào cũng là app của mình, cứ đóng)."""
    try:
        url, token = doc_cau_hinh()
        kq = goi_tool(url, token, "list_tasks", {"state": "downloading"}, timeout=20.0)
        return sum(1 for t in (kq.get("tasks") or [])
                   if str(t.get("status", "")).lower() in DANG_LAM)
    except Exception:       # noqa: BLE001
        return None


def dong_app_neu_tu_mo(cho: float = 8.0) -> str:
    """Đóng app Bili23 NẾU chính script này đã mở nó (có dấu DAU_TU_MO và PID vẫn là pythonw
    của app) → một dòng kể đã làm gì. App người dùng mở sẵn (không có dấu) hay PID đã thành
    tiến trình khác thì để nguyên; app còn task đang tải (myvideo / người dùng tạo tay) thì
    CHƯA đóng, giữ dấu cho lượt sau. Không ném lỗi: dọn dẹp không được làm hỏng hàng đợi."""
    try:
        dau = json.loads(DAU_TU_MO.read_text(encoding="utf-8"))
        pid, exe = int(dau["pid"]), str(dau.get("exe", ""))
    except (OSError, ValueError, KeyError, TypeError):
        return "ℹ️ App Bili23 không do hàng đợi tự mở (hoặc đã đóng) → để nguyên."
    dang_chay = _duong_dan_exe(pid)
    if not dang_chay:
        _xoa_dau_tu_mo()
        return f"ℹ️ App Bili23 (PID {pid}) đã đóng từ trước → không phải làm gì."
    if os.path.normcase(dang_chay) != os.path.normcase(exe):
        _xoa_dau_tu_mo()
        return (f"ℹ️ PID {pid} giờ là tiến trình khác ({Path(dang_chay).name}), không phải "
                "app Bili23 do hàng đợi mở → để nguyên.")
    con = _task_dang_lam()
    if con:
        return (f"⏳ App Bili23 còn {con} task đang tải (của myvideo hay bạn tạo tay) → chưa "
                "đóng, lượt tải sau sẽ đóng.")
    _xoa_dau_tu_mo()
    _taskkill(pid, ep=False)                 # đóng êm trước
    moc = time.monotonic() + cho
    while time.monotonic() < moc and _duong_dan_exe(pid):
        time.sleep(0.5)
    if _duong_dan_exe(pid):                  # còn sống (vd thu vào khay) → ép
        _taskkill(pid, ep=True)
        return f"🧹 Đã đóng app Bili23 (PID {pid}, phải ép) — app do bộ tải tự mở, tải xong thì dọn."
    return f"🧹 Đã đóng app Bili23 (PID {pid}) — app do bộ tải tự mở, tải xong thì dọn."


def chon_tap(kq: dict) -> tuple[str, str]:
    """Kết quả parse_url → (episode_id, tiêu đề) của ĐÚNG MỘT video cần tải.

    Link trỏ hẳn một phần (?p=…) thì app đã chỉ sẵn link_target_episode_id;
    video một phần thì lấy luôn; còn link ra cả danh sách nhiều tập mà không
    chỉ phần nào thì bắt người dùng chọn — tải bừa tập đầu dễ sai ý."""
    eps = kq.get("episodes") or []
    if not eps:
        raise ThatBai("Link không ra tập nào tải được (video hỏng / chỉ dành cho hội viên?).")
    muc_tieu = kq.get("link_target_episode_id")
    if muc_tieu:
        ep = next((e for e in eps if e.get("episode_id") == muc_tieu), None)
        if ep:
            return muc_tieu, ep.get("title", "")
    if len(eps) == 1:
        return eps[0]["episode_id"], eps[0].get("title", "")
    vi_du = " · ".join(e.get("title", "?") for e in eps[:4])
    raise ThatBai(f"Link ra {len(eps)} tập ({vi_du}…) mà không chỉ rõ tập nào — "
                  "dán link của ĐÚNG tập muốn tải (bấm vào tập đó trên web "
                  "Bilibili rồi copy link có ?p=…).")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Tải video Bilibili qua app Bili23 Downloader (MCP).")
    ap.add_argument("url", nargs="?", help="Link bilibili.com / b23.tv (hoặc mã BV/av trần)")
    ap.add_argument("--out", help="File .mp4 đích (đường dẫn đầy đủ)")
    ap.add_argument("--dong-app", action="store_true",
                    help="Không tải gì: đóng app Bili23 nếu chính script này đã mở nó (cuối "
                         "đợt tải của hàng đợi), rồi thoát")
    ap.add_argument("--timeout", type=float, default=14400,
                    help="Đợi tải tối đa bấy nhiêu giây (mặc định 14400 = 4 giờ)")
    ap.add_argument("--cho-app", type=float, default=90,
                    help="Đợi app mở tối đa bấy nhiêu giây (mặc định 90)")
    ap.add_argument("--chi-phan-tich", action="store_true",
                    help="Chỉ phân tích link xem ra tập nào, KHÔNG tải")
    ap.add_argument("--chat-luong", default="auto",
                    help="Mức video: auto (mặc định = cao nhất tải được), 1080P, 720P, "
                         "480P, 360P… — chỉ cần tiếng thì 360P là đủ")
    args = ap.parse_args(argv)
    if args.dong_app:
        print(dong_app_neu_tu_mo(), flush=True)
        return 0
    if not args.url or not args.out:
        ap.error("cần <link> và --out <file.mp4> (hoặc chỉ --dong-app)")
    yeu_cau = chuan_chat_luong(args.chat_luong)

    out = Path(args.out)
    if out.is_file() and out.stat().st_size > 1_000_000:
        print(f"✅ Đã có sẵn {out.name} ({out.stat().st_size // 1_000_000} MB) — bỏ qua tải.")
        return 0

    url, token = doc_cau_hinh()
    print(f"🔗 {args.url}\n📡 MCP Bili23: {url}", flush=True)

    # App phải đang mở (MCP sống trong GUI) — chưa mở thì mở giúp rồi đợi.
    if not cho_mcp(url, token, han=3.0):
        mo_app()
        if not cho_mcp(url, token, han=args.cho_app):
            raise ThatBai(f"Mở app rồi mà {args.cho_app:g}s chưa thấy MCP lên — "
                          "mở app Bili23 bằng tay, nhìn xem có báo lỗi gì không.")

    dn = goi_tool(url, token, "get_login_status", {})
    # Chỉ đáng nhắc khi đang xin bản cao nhất: mức thấp (360P…) không cần đăng nhập.
    if yeu_cau == "auto" and (not dn.get("logged_in") or dn.get("session_expired")):
        print("⚠ Phiên đăng nhập Bilibili trong app đã hết/chưa có — vẫn tải được "
              "nhưng chất lượng có thể bị giới hạn. Mở app đăng nhập lại để có bản "
              "cao nhất.", flush=True)

    kq = goi_tool(url, token, "parse_url", {"url": args.url}, timeout=180.0)
    ep_id, tieu_de = chon_tap(kq)
    chat_luong = (kq.get("available") or {}).get("video_quality") or []
    print(f"🎬 {tieu_de or '(không rõ tiêu đề)'}"
          + (f"\n🏷 Chất lượng video đang có: {', '.join(map(str, chat_luong))}"
             if chat_luong else ""), flush=True)
    if args.chi_phan_tich:
        print(json.dumps(kq, ensure_ascii=False, indent=2))
        return 0

    # Không chỉ định chất lượng → app theo danh sách ưu tiên của người dùng
    # (cao nhất trước). Có --chat-luong thì xin đúng mức đó (đã dò theo các mức
    # video này có). redownload=True: app từng tải video này rồi thì vẫn tải
    # lại — vì file đích của mình chưa có (đã có thì thoát từ đầu rồi).
    tuy_chon = {"container": "mp4"}
    muc = chon_muc(yeu_cau, chat_luong)
    if muc != "auto":
        tuy_chon["video_quality"] = muc
        print(f"🎚 Tải mức {muc}"
              + (f" (video không có {yeu_cau} — lấy mức gần nhất)" if muc != yeu_cau else ""),
              flush=True)
    tao = goi_tool(url, token, "create_download",
                   {"episode_ids": [ep_id], "options": tuy_chon,
                    "redownload": True}, timeout=120.0)
    tasks = tao.get("tasks") or []
    if not tasks:
        raise ThatBai("App nhận lệnh nhưng không thấy task mới — có thể một hộp "
                      "thoại đang chờ bấm trong app. Mở app Bili23 xem rồi chạy lại.")
    task_id = tasks[0]["task_id"]
    print(f"⬇ Bắt đầu tải (task {task_id})…", flush=True)

    # Đợi tải xong: hỏi thăm 2 giây/lần, chỉ in khi nhích ≥5% hoặc đổi trạng
    # thái — log hàng đợi web khỏi ngập.
    moc = time.monotonic() + args.timeout
    da_in = ("", -1)
    while True:
        if time.monotonic() > moc:
            raise ThatBai(f"Quá {args.timeout:g}s chưa tải xong — việc tải VẪN chạy "
                          "trong app; đợi app xong rồi bấm chạy lại là nó nhặt file.")
        tt = goi_tool(url, token, "get_task_status", {"task_id": task_id})
        trang_thai = tt.get("status", "")
        phan_tram = int(tt.get("progress") or 0)
        if trang_thai in HONG:
            raise ThatBai(f"App báo {TRANG_THAI.get(trang_thai, trang_thai)} — mở app "
                          "Bili23 xem lỗi chi tiết (thường do mạng/phiên đăng nhập).")
        if trang_thai == "completed":
            break
        moi = (trang_thai, phan_tram // 5)
        if moi != da_in:
            # speed là SỐ byte/giây — đổi sang MB/s cho đọc được.
            toc_do = tt.get("speed", "")
            if isinstance(toc_do, (int, float)) and toc_do > 0:
                toc_do = f"{toc_do / 1_048_576:.1f} MB/s"
            print(f"   {TRANG_THAI.get(trang_thai, trang_thai)} {phan_tram}%"
                  + (f" — {toc_do}" if toc_do else ""), flush=True)
            da_in = moi
        time.sleep(2.0)

    duong = tt.get("file_path", "")
    if not duong or not os.path.isfile(duong):
        raise ThatBai(f"App báo xong nhưng không thấy file ({duong or 'không rõ'}) — "
                      "mở app, chuột phải task → mở thư mục xem file nằm đâu.")

    # Dọn về đúng tên --out (mã BV — pipeline cần biết TÊN TRƯỚC khi tải xong;
    # tên gốc theo tiêu đề thì đến lúc này mới biết). shutil.move chịu được
    # khác ổ đĩa; tiêu đề thật vẫn nằm trên dòng 🎬 trong log.
    import shutil
    out.parent.mkdir(parents=True, exist_ok=True)
    if os.path.abspath(duong) != os.path.abspath(out):
        shutil.move(duong, out)
    print(f"✅ Tải xong, chất lượng {tt.get('video_quality', '?')}: {out}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ThatBai as e:
        print(f"❌ {e}", flush=True)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
