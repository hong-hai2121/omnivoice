# -*- coding: utf-8 -*-
"""
taive_drive.py — TẢI VIDEO ĐÃ DỰNG LÊN GOOGLE DRIVE.

Mặc định tải 2 video mới nhất trong  kịch_bản/output/  lên một thư mục Drive:
  • "video full"  = *_videodone.mp4  (video NGANG dựng từ audio đầy đủ)
  • "video cắt"   = *_doc.mp4        (video DỌC dựng từ bản cắt)

Dùng Google Drive API v3 (OAuth) — TÁI DÙNG client_secret.json của YOUTUBE/
(cùng project Google), nhưng lưu token RIÊNG (token_drive.json) với quyền Drive,
nên KHÔNG ảnh hưởng token đăng YouTube.

Cách dùng:
    python taive_drive.py                         # tự tìm + tải full & cắt mới nhất
    python taive_drive.py full                     # chỉ tải video full
    python taive_drive.py cut                       # chỉ tải video cắt
    python taive_drive.py "D:/.../abc.mp4" ...      # tải đúng các file chỉ định
    python taive_drive.py --folder <ID hoặc URL>    # đổi thư mục Drive đích

────────────────────────────────────────────────────────────────────────────
CHUẨN BỊ MỘT LẦN (bắt buộc — Drive là API riêng so với YouTube):
  1. Vào https://console.cloud.google.com/  → đúng project của client_secret.json
     (project "api-yotube-499811").
  2. "APIs & Services" → "Library" → bật "Google Drive API".
  3. "OAuth consent screen": thêm scope  .../auth/drive.file  (và đảm bảo email của
     bạn nằm trong "Test users").
  4. TÀI KHOẢN Google bạn đăng nhập phải có quyền SỬA (Editor) thư mục Drive đích.
  Lần đầu chạy sẽ mở trình duyệt để đăng nhập + cấp quyền; sau đó lưu token_drive.json.

CÀI THƯ VIỆN (nếu thiếu — script tự cài vào venv):
  pip install google-api-python-client google-auth-oauthlib google-auth-httplib2
────────────────────────────────────────────────────────────────────────────
"""

import sys
import os

# ── Tự chuyển sang python của venv (giống các script khác trong dự án) ───────
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
_VENV_PYTHON = os.path.join(_REPO_ROOT, "venv", "Scripts", "python.exe")
if os.path.exists(_VENV_PYTHON) and os.path.abspath(sys.executable) != os.path.abspath(_VENV_PYTHON):
    import subprocess
    subprocess.run([_VENV_PYTHON] + sys.argv)
    sys.exit()

import io
import re
import subprocess
from pathlib import Path

# ── Ép UTF-8 cho stdout/stderr khi chạy độc lập (in được tiếng Việt) ─────────
for _name in ("stdout", "stderr"):
    _s = getattr(sys, _name, None)
    if _s is not None and hasattr(_s, "buffer"):
        setattr(sys, _name, io.TextIOWrapper(_s.buffer, encoding="utf-8", errors="replace"))


# ── Thư mục & cấu hình ───────────────────────────────────────────────────────
_HERE      = Path(__file__).resolve().parent          # myvoice/scripts/
BASE_DIR   = _HERE.parent                              # myvoice/
OUTPUT_DIR = BASE_DIR / "kịch_bản" / "output"          # nơi chứa video đã dựng
YT_DIR     = BASE_DIR / "YOUTUBE"                      # tái dùng client_secret.json ở đây

CLIENT_SECRET_FILE = YT_DIR / "client_secret.json"    # dùng chung với đăng YouTube
TOKEN_FILE         = YT_DIR / "token_drive.json"       # token RIÊNG cho Drive (không đụng YouTube)

# Quyền tối thiểu: chỉ tạo/ghi các file do app này tạo (đủ để tải file mới vào thư mục).
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

# Thư mục Drive đích mặc định (đổi bằng --folder hoặc biến môi trường OMNI_DRIVE_FOLDER).
DEFAULT_FOLDER_ID = os.environ.get(
    "OMNI_DRIVE_FOLDER", "1rSgVBo9zROoCJNEjGSvlWJ09rhvh1G6N"
)

# Mẫu tên file của 2 loại video do pipeline tạo ra.
FULL_GLOB = "*_videodone.mp4"   # video NGANG (audio full)
CUT_GLOB  = "*_doc.mp4"         # video DỌC (bản cắt)


def _log(msg, level="info"):
    print(msg)


# ── Phụ trợ ──────────────────────────────────────────────────────────────────
def extract_folder_id(value: str) -> str:
    """Cho phép truyền cả URL Drive lẫn ID; trả về ID thuần."""
    if not value:
        return value
    m = re.search(r"/folders/([A-Za-z0-9_-]+)", value)
    if m:
        return m.group(1)
    m = re.search(r"[?&]id=([A-Za-z0-9_-]+)", value)
    if m:
        return m.group(1)
    return value.strip()


def _latest(glob_pat: str) -> Path | None:
    """File khớp mẫu MỚI NHẤT (theo thời gian sửa) trong OUTPUT_DIR, hoặc None."""
    if not OUTPUT_DIR.exists():
        return None
    files = list(OUTPUT_DIR.glob(glob_pat))
    return max(files, key=lambda p: p.stat().st_mtime) if files else None


def find_full_video() -> Path | None:
    """Video full (NGANG) mới nhất: *_videodone.mp4."""
    return _latest(FULL_GLOB)


def find_cut_video() -> Path | None:
    """Video cắt (DỌC) mới nhất: *_doc.mp4."""
    return _latest(CUT_GLOB)


# ── Thư viện Google API ──────────────────────────────────────────────────────
def _check_deps():
    try:
        import google_auth_oauthlib.flow      # noqa: F401
        import googleapiclient.discovery       # noqa: F401
        import googleapiclient.http            # noqa: F401
        import google.auth.transport.requests  # noqa: F401
        return None
    except ImportError as e:
        return str(e)


def install_deps(log=_log):
    pkgs = ["google-api-python-client", "google-auth-oauthlib", "google-auth-httplib2"]
    log(f"Đang cài: {' '.join(pkgs)} ...")
    proc = subprocess.run([sys.executable, "-m", "pip", "install", *pkgs],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.stdout:
        log(proc.stdout.strip())
    if proc.returncode != 0:
        log(proc.stderr.strip(), "err")
        raise RuntimeError("Cài thư viện thất bại.")
    log("Đã cài xong thư viện Google API.")


def get_credentials(log=_log):
    """Lấy credentials Drive hợp lệ; tự refresh hoặc mở trình duyệt đăng nhập khi cần."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not CLIENT_SECRET_FILE.exists():
        raise FileNotFoundError(
            "Chưa có client_secret.json.\n\n"
            f"Hãy đặt file (tải từ Google Cloud Console) vào:\n{CLIENT_SECRET_FILE}\n"
            "Có thể dùng chung file của phần đăng YouTube."
        )

    creds = None
    if TOKEN_FILE.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        except Exception:
            creds = None

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        log("Token Drive hết hạn — đang làm mới...")
        try:
            creds.refresh(Request())
            TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
            return creds
        except Exception:
            log("Làm mới token thất bại, sẽ đăng nhập lại.", "warn")

    log("Mở trình duyệt để đăng nhập Google & cấp quyền Drive...")
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_FILE), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
    log("Đăng nhập thành công, đã lưu token_drive.json.")
    return creds


# ── Tải 1 file lên Drive ─────────────────────────────────────────────────────
def upload_to_drive(file_path, folder_id=DEFAULT_FOLDER_ID, log=_log,
                    progress_cb=None, creds=None):
    """Tải MỘT file lên thư mục Drive. Trả về dict {'id', 'name', 'webViewLink'}.

    creds: truyền credentials có sẵn để tái dùng (tránh xác thực lại từng file).
    """
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError

    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file để tải: {file_path}")

    folder_id = extract_folder_id(folder_id)
    if creds is None:
        creds = get_credentials(log)
    service = build("drive", "v3", credentials=creds, cache_discovery=False)

    metadata = {"name": file_path.name, "parents": [folder_id]}
    media = MediaFileUpload(str(file_path), mimetype="video/mp4",
                            chunksize=8 * 1024 * 1024, resumable=True)
    request = service.files().create(
        body=metadata, media_body=media,
        fields="id, name, webViewLink", supportsAllDrives=True)

    log(f"⬆ Đang tải: {file_path.name} ({file_path.stat().st_size / 1024 / 1024:.1f} MB)...")
    response = None
    last_pct = -1
    while response is None:
        try:
            chunk_status, response = request.next_chunk()
        except HttpError as e:
            raise RuntimeError(f"Lỗi Drive API: {e}")
        if chunk_status:
            pct = int(chunk_status.progress() * 100)
            if pct != last_pct:
                last_pct = pct
                if progress_cb:
                    progress_cb(pct)
                else:
                    log(f"  {pct}%")
    if progress_cb:
        progress_cb(100)
    log(f"✅ Xong: {response.get('name')} → {response.get('webViewLink')}")
    return response


# ── Tải nhiều file (full + cắt) ──────────────────────────────────────────────
def upload_videos(paths, folder_id=DEFAULT_FOLDER_ID, log=_log, progress_cb=None):
    """Tải lần lượt danh sách file; tái dùng 1 lần xác thực. Trả về list kết quả."""
    creds = get_credentials(log)
    results = []
    for p in paths:
        results.append(upload_to_drive(p, folder_id=folder_id, log=log,
                                       progress_cb=progress_cb, creds=creds))
    return results


def upload_full_and_cut(folder_id=DEFAULT_FOLDER_ID, which="both", log=_log,
                        progress_cb=None):
    """Tự tìm video full/cắt mới nhất trong output/ rồi tải lên.

    which: "both" | "full" | "cut".
    """
    targets = []
    if which in ("both", "full"):
        f = find_full_video()
        if f:
            targets.append(f)
        else:
            log(f"⚠️ Không thấy video full ({FULL_GLOB}) trong {OUTPUT_DIR}", "warn")
    if which in ("both", "cut"):
        c = find_cut_video()
        if c:
            targets.append(c)
        else:
            log(f"⚠️ Không thấy video cắt ({CUT_GLOB}) trong {OUTPUT_DIR}", "warn")
    if not targets:
        raise RuntimeError("Không có video nào để tải. Hãy dựng video trước.")
    return upload_videos(targets, folder_id=folder_id, log=log, progress_cb=progress_cb)


# ── CLI ──────────────────────────────────────────────────────────────────────
def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)

    # Tách --folder <ID/URL>
    folder_id = DEFAULT_FOLDER_ID
    if "--folder" in argv:
        i = argv.index("--folder")
        try:
            folder_id = argv[i + 1]
            del argv[i:i + 2]
        except IndexError:
            print("Lỗi: --folder cần một ID hoặc URL theo sau.", file=sys.stderr)
            return 2

    # Bảo đảm có thư viện
    miss = _check_deps()
    if miss:
        print(f"Thiếu thư viện Google API ({miss}). Đang cài...")
        try:
            install_deps()
        except Exception as e:
            print(f"Lỗi cài thư viện: {e}", file=sys.stderr)
            return 2

    # Xác định file cần tải
    explicit = [a for a in argv if a not in ("full", "cut", "both")]
    mode = next((a for a in argv if a in ("full", "cut", "both")), None)

    try:
        if explicit:
            paths = [Path(p) for p in explicit]
            upload_videos(paths, folder_id=folder_id)
        else:
            upload_full_and_cut(folder_id=folder_id, which=mode or "both")
    except Exception as e:
        print(f"Lỗi: {e}", file=sys.stderr)
        return 1

    print("Hoàn tất tải lên Drive.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
