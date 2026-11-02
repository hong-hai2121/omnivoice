# -*- coding: utf-8 -*-
"""Nối Playwright vào Chrome THẬT đang mở của OmniVoice — mỗi nền tảng một profile riêng.

Cấu hình nằm ở myvoice/TRINHDUYET/cau_hinh.json (tự tạo lần đầu, profile ĐỂ TRỐNG — người dùng
điền sau). Mỗi nền tảng ("youtube" / "tiktok") cần ba thứ, chuẩn bị MỘT LẦN cho profile đó:
  1. Cài "Playwright Extension" (Microsoft) từ Chrome Web Store trong đúng profile.
  2. chrome://extensions → Chi tiết của extension → bật "Cho phép truy cập URL tệp" (bắt buộc,
     không bật thì không nạp được file video vào <input type=file>: Chrome trả "Not allowed").
  3. Bấm icon extension → trang trạng thái → chép dòng PLAYWRIGHT_MCP_EXTENSION_TOKEN=… → dán vào
     "extension_token" của nền tảng đó trong cau_hinh.json (dán cả dòng cũng được).

⛔ CHỐT CHẶN PROFILE THAM KHẢO (user 30/10/2026): tool "Đăng video tự động"
(D:\\Python\\GetLinktoText\\DangvideoYTBTikTokZalo) dùng Chrome "Profile 9" (YouTube), "Profile 85"
(TikTok) và Cốc Cốc "Profile 12" (Zalo). OmniVoice KHÔNG ĐƯỢC dùng các profile/token đó —
kiem_profile_cam() từ chối ngay khi cấu hình trùng (so tên profile; token so bằng SHA-256, không
lưu token thô ở đây). Muốn cố ý dùng lại thì sửa PROFILE_CAM/TOKEN_CAM_SHA256 — đó là quyết định
của người dùng, không phải của mã.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
import time
from pathlib import Path

from pw_extension_relay import EXTENSION_ID, EXTENSION_STORE_URL, ExtensionRelay

APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "cau_hinh.json"

LOCALAPPDATA = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
DEFAULT_USER_DATA = str(Path(LOCALAPPDATA) / "Google" / "Chrome" / "User Data")

NEN_TANG = ("youtube", "tiktok")
NHAN = {"youtube": "YouTube Studio", "tiktok": "TikTok Studio"}

PROFILE_DEFAULTS = {
    "browser_path": "",        # trống = tự dò chrome.exe
    "user_data_dir": "",       # trống = User Data mặc định của Chrome
    "profile_dir": "",         # ví dụ "Profile 3" — ĐỂ TRỐNG cho tới khi người dùng liên kết
    "extension_token": "",     # PLAYWRIGHT_MCP_EXTENSION_TOKEN=… của extension TRONG profile đó
    "client_name": "",         # tên hiện ở nhóm tab "Playwright · …"; trống = "OmniVoice · <nền tảng>"
}

DEFAULT_CONFIG = {
    "connect_timeout_sec": 60,
    "khung_gio": ["08:00", "18:00"],   # khung giờ công bố mỗi ngày (giống API: 08:00 / 18:00)
    "short_sau_gio": 1,                # Short lên sau bản chính bấy nhiêu giờ (= dang_tap_youtube.SHORT_DELAY_HOURS)
    "tiktok_ban": "full",              # TikTok đăng bản nào: full = '[Full] …' dọc đầy đủ | ngan = tiktok.mp4
    "so_hashtag_tiktok": 6,            # TikTok chỉ lấy N hashtag đầu của mô tả
    "playlist": "",                    # danh sách phát YouTube; trống = không chọn
    "doc_lich_that": True,             # trước khi xếp giờ, đọc lịch đã đặt THẬT trên Studio (chậm hơn nhưng chắc)
    "nen_tang": {name: dict(PROFILE_DEFAULTS) for name in NEN_TANG},
}

# ---- profile/token của tool tham khảo — CẤM dùng cho OmniVoice (xem docstring) ----
PROFILE_CAM = (
    ("google\\chrome\\user data", "profile 9"),     # Đăng video YouTube (tool tham khảo)
    ("google\\chrome\\user data", "profile 85"),    # Đăng video TikTok (tool tham khảo)
    ("coccoc\\browser\\user data", "profile 12"),   # Đăng video Zalo (tool tham khảo, Cốc Cốc)
)
TOKEN_CAM_SHA256 = {
    "33bcc360081334ff31d674c0a023f2d49f148e5357a2f60b5ad09cb926df7b64",
    "a27a985727e9885bdce557b454300a551646df2266cde2d653661143430e950f",
    "4d347dce28c21056a5c910d93dc95d8a16ddd9fac51bd0fdf2b423f26f69163e",
}


class ProfileCamError(RuntimeError):
    """Cấu hình trỏ vào profile/token của tool tham khảo 'Đăng video tự động'."""


class ChuaCauHinhError(RuntimeError):
    """Nền tảng chưa có profile/token — người dùng chưa liên kết."""


# ------------------------------------------------------------------ cấu hình
def load_config() -> dict:
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))     # bản sao sâu
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        if isinstance(data, dict):
            for k, v in data.items():
                if k == "nen_tang" and isinstance(v, dict):
                    for name, p in v.items():
                        if isinstance(p, dict):
                            cfg["nen_tang"].setdefault(name, dict(PROFILE_DEFAULTS)).update(
                                {kk: vv for kk, vv in p.items() if kk in PROFILE_DEFAULTS})
                elif k in DEFAULT_CONFIG:
                    cfg[k] = v
    else:
        save_config(cfg)
    return cfg


def save_config(cfg: dict) -> None:
    out = {k: cfg.get(k, DEFAULT_CONFIG[k]) for k in DEFAULT_CONFIG if k != "nen_tang"}
    out["nen_tang"] = {}
    for name, p in (cfg.get("nen_tang") or {}).items():
        out["nen_tang"][name] = {k: (p or {}).get(k, PROFILE_DEFAULTS[k]) for k in PROFILE_DEFAULTS}
    CONFIG_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_token(token) -> str:
    """'PLAYWRIGHT_MCP_EXTENSION_TOKEN=abc', 'abc', có ngoặc kép… → 'abc'."""
    t = (token or "").strip().strip('"').strip("'")
    if "=" in t and t.upper().startswith("PLAYWRIGHT_MCP_EXTENSION_TOKEN"):
        t = t.split("=", 1)[1].strip().strip('"').strip("'")
    return t


def nen_tang_cfg(cfg: dict, name: str) -> dict:
    """Cấu hình trình duyệt của một nền tảng, đã điền mặc định (user_data_dir, client_name, token sạch)."""
    if name not in NEN_TANG:
        raise ValueError(f"Nền tảng lạ: {name!r} (chỉ có {', '.join(NEN_TANG)})")
    p = dict(PROFILE_DEFAULTS)
    p.update({k: v for k, v in ((cfg.get("nen_tang") or {}).get(name) or {}).items() if k in PROFILE_DEFAULTS})
    p["name"] = name
    p["user_data_dir"] = str(p.get("user_data_dir") or DEFAULT_USER_DATA)
    p["profile_dir"] = str(p.get("profile_dir") or "").strip()
    p["extension_token"] = normalize_token(p.get("extension_token"))
    p["client_name"] = str(p.get("client_name") or f"OmniVoice · {NHAN.get(name, name)}")
    p["connect_timeout_sec"] = float(cfg.get("connect_timeout_sec") or 60)
    return p


def _norm_path(s: str) -> str:
    return str(s or "").replace("/", "\\").rstrip("\\").lower()


def kiem_profile_cam(pcfg: dict) -> None:
    """Ném ProfileCamError nếu profile/token là của tool tham khảo 'Đăng video tự động'."""
    udd, prof = _norm_path(pcfg.get("user_data_dir")), str(pcfg.get("profile_dir") or "").strip().lower()
    for duoi, cam in PROFILE_CAM:
        if prof == cam and udd.endswith(duoi):
            raise ProfileCamError(
                f"[{pcfg.get('name', '?')}] profile '{pcfg.get('profile_dir')}' trong '{pcfg.get('user_data_dir')}' "
                "là profile của tool tham khảo 'Đăng video tự động' — OmniVoice KHÔNG dùng profile đó. "
                "Hãy tạo/chọn profile Chrome khác cho kênh Mimi audio rồi điền vào cau_hinh.json.")
    tok = normalize_token(pcfg.get("extension_token"))
    if tok and hashlib.sha256(tok.encode("utf-8")).hexdigest() in TOKEN_CAM_SHA256:
        raise ProfileCamError(
            f"[{pcfg.get('name', '?')}] extension_token này là token của tool tham khảo 'Đăng video tự động' "
            "(cùng extension trong profile của tool đó). Lấy token từ extension cài trong profile RIÊNG của OmniVoice.")


def kiem_san_sang(cfg: dict, name: str) -> dict:
    """Cấu hình nền tảng đủ dùng chưa: trả về pcfg; thiếu → ChuaCauHinhError; trùng tool tham khảo → ProfileCamError."""
    p = nen_tang_cfg(cfg, name)
    kiem_profile_cam(p)
    if not p["profile_dir"]:
        raise ChuaCauHinhError(
            f"[{NHAN.get(name, name)}] chưa liên kết profile Chrome — điền nen_tang.{name}.profile_dir "
            f"(và extension_token) trong {CONFIG_PATH}.")
    if not p["extension_token"]:
        raise ChuaCauHinhError(
            f"[{NHAN.get(name, name)}] chưa có extension_token — bấm icon Playwright Extension trong profile "
            f"'{p['profile_dir']}' → chép dòng PLAYWRIGHT_MCP_EXTENSION_TOKEN=… vào {CONFIG_PATH}.")
    return p


def trang_thai(cfg: dict | None = None) -> dict:
    """{nền tảng: {"ok": bool, "ly_do": str, "profile": str}} cho giao diện / log."""
    cfg = cfg or load_config()
    out = {}
    for name in NEN_TANG:
        try:
            p = kiem_san_sang(cfg, name)
            out[name] = {"ok": True, "ly_do": "", "profile": p["profile_dir"]}
        except (ChuaCauHinhError, ProfileCamError, ValueError) as e:
            out[name] = {"ok": False, "ly_do": str(e), "profile": nen_tang_cfg(cfg, name)["profile_dir"]}
    return out


# ------------------------------------------------------------------ Chrome
def find_browser(pcfg: dict) -> str:
    if pcfg.get("browser_path") and Path(pcfg["browser_path"]).exists():
        return pcfg["browser_path"]
    for c in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
              str(Path(LOCALAPPDATA) / "Google" / "Chrome" / "Application" / "chrome.exe")):
        if Path(c).exists():
            return c
    raise FileNotFoundError("Không tìm thấy chrome.exe — điền browser_path vào cau_hinh.json")


def profile_path(pcfg: dict) -> Path:
    return Path(pcfg["user_data_dir"]) / pcfg["profile_dir"]


def extension_installed(pcfg: dict) -> bool:
    """Extension đã cài trong profile chưa (Web Store giải nén vào <profile>/Extensions/<id>, hoặc có
    bản ghi extensions.settings trong Preferences / Secure Preferences)."""
    p = profile_path(pcfg)
    if (p / "Extensions" / EXTENSION_ID).exists():
        return True
    for fname in ("Preferences", "Secure Preferences"):
        try:
            prefs = json.loads((p / fname).read_text(encoding="utf-8"))
        except Exception:
            continue
        rec = ((prefs.get("extensions") or {}).get("settings") or {}).get(EXTENSION_ID)
        if isinstance(rec, dict) and rec:
            return True
    return False


def _spawn_browser(pcfg: dict, url: str) -> None:
    args = [find_browser(pcfg)]
    if _norm_path(pcfg.get("user_data_dir")) != _norm_path(DEFAULT_USER_DATA):
        args.append(f"--user-data-dir={pcfg['user_data_dir']}")
    args += [f"--profile-directory={pcfg['profile_dir']}", url]
    subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     close_fds=True, creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)


def open_store_page(pcfg: dict, log=print) -> None:
    log(f"Mở trang cài Playwright Extension trong profile '{pcfg['profile_dir']}'...")
    _spawn_browser(pcfg, EXTENSION_STORE_URL)


def open_extension_settings(pcfg: dict) -> None:
    """Trang chi tiết extension (chỗ bật 'Cho phép truy cập URL tệp')."""
    _spawn_browser(pcfg, f"chrome://extensions/?id={EXTENSION_ID}")


# ------------------------------------------------------------------ phiên theo profile
# Mỗi profile một relay + một trình duyệt Playwright + một tab điều khiển; giữ tới khi ngắt.
_sessions: dict[tuple, dict] = {}
_current_key = None
_pw = None                 # MỘT Playwright chung (mỗi thread chỉ được một sync_playwright)
_keepalive = None
KEEPALIVE_GIAY = 15        # extension MV3 ngủ nếu không có lệnh → gửi lệnh nhẹ định kỳ


def _key(pcfg):
    return (_norm_path(pcfg.get("user_data_dir")), str(pcfg.get("profile_dir") or ""))


def _page_song(page):
    try:
        return page is not None and not page.is_closed()
    except Exception:
        return False


def _keepalive_loop():
    while True:
        time.sleep(KEEPALIVE_GIAY)
        for s in list(_sessions.values()):
            r = s["relay"]
            if not r.connected:
                continue
            try:
                r.send_cdp("Runtime.evaluate", {"expression": "1", "returnByValue": True}, timeout=10)
            except Exception:
                pass


def _bat_keepalive():
    global _keepalive
    if _keepalive is not None and _keepalive.is_alive():
        return
    _keepalive = threading.Thread(target=_keepalive_loop, name="cdp-keepalive", daemon=True)
    _keepalive.start()


def ket_noi(cfg: dict, name: str, log=print):
    """Nối (hoặc dùng lại phiên còn sống) với profile của nền tảng `name`. Trả về (relay, page).

    Thứ tự: kiểm cấu hình (chốt profile tham khảo) → bật relay → mở trang connect trong đúng
    profile → chờ extension nối → Playwright connect_over_cdp. KHÔNG bring_to_front.
    """
    global _current_key, _pw
    pcfg = kiem_san_sang(cfg, name)
    key = _key(pcfg)
    s = _sessions.get(key)
    if s is not None:
        if s["relay"].connected and _page_song(s.get("page")):
            _current_key = key
            return s["relay"], s["page"]
        log(f"Kết nối profile '{pcfg['profile_dir']}' đã rớt → nối lại.")
        _bo_phien(key)

    browser_exe = find_browser(pcfg)
    if not extension_installed(pcfg):
        open_store_page(pcfg, log)
        raise RuntimeError(
            f"Chưa cài Playwright Extension trong profile '{pcfg['profile_dir']}'. Đã mở Chrome Web Store "
            "trong profile đó — bấm 'Thêm vào Chrome', rồi: (1) chrome://extensions → Chi tiết → bật "
            "'Cho phép truy cập URL tệp'; (2) bấm icon extension → chép token → dán vào cau_hinh.json. "
            "Sau đó chạy lại.")

    relay = ExtensionRelay(log=log)
    relay.start()
    log(f"Relay sẵn sàng (cổng {relay.port}). Mở trang kết nối trong profile '{pcfg['profile_dir']}'...")
    udd = None if _norm_path(pcfg["user_data_dir"]) == _norm_path(DEFAULT_USER_DATA) else pcfg["user_data_dir"]
    relay.open_connect_page(browser_exe, pcfg["profile_dir"], pcfg["client_name"], pcfg["extension_token"], udd)
    try:
        relay.wait_for_extension(pcfg["connect_timeout_sec"])
    except Exception:
        relay.stop()
        raise
    log(f"✓ Extension đã nối — đang điều khiển Chrome thật (profile '{pcfg['profile_dir']}').")

    if _pw is None:
        from playwright.sync_api import sync_playwright
        _pw = sync_playwright().start()
    browser = _pw.chromium.connect_over_cdp(relay.cdp_endpoint, timeout=30000)
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    _sessions[key] = {"relay": relay, "browser": browser, "page": page, "cfg": pcfg}
    _current_key = key
    _bat_keepalive()
    log("✓ Playwright đã nối vào Chrome (qua extension).")
    return relay, page


def _relay_hien_tai():
    s = _sessions.get(_current_key) if _current_key is not None else None
    return s["relay"] if s else None


def cdp_send(method, params=None, timeout=30.0):
    """Lệnh CDP thẳng tới tab điều khiển của phiên hiện tại (xem ExtensionRelay.send_cdp)."""
    r = _relay_hien_tai()
    if r is None or not r.connected:
        raise RuntimeError("Chưa kết nối extension — gọi ket_noi() trước.")
    return r.send_cdp(method, params, timeout=timeout)


def close_tab(page) -> bool:
    if page is None:
        return False
    try:
        page.close(run_before_unload=False)
        return True
    except Exception:
        return False


def _bo_phien(key, dong_tab=False):
    s = _sessions.pop(key, None)
    if not s:
        return
    if dong_tab and not close_tab(s.get("page")):
        try:
            s["relay"].close_first_tab()
        except Exception:
            pass
    try:
        s["relay"].stop()
    except Exception:
        pass


def ngat_tat_ca(dong_tab=True, log=None) -> None:
    """Đóng tab điều khiển của từng profile, tắt relay, dừng Playwright."""
    global _pw, _current_key
    for key in list(_sessions):
        _bo_phien(key, dong_tab=dong_tab)
    _current_key = None
    if _pw is not None:
        try:
            _pw.stop()
        except Exception:
            pass
        _pw = None
    if log:
        log("✓ Đã ngắt mọi kết nối trình duyệt.")
