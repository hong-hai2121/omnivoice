# -*- coding: utf-8 -*-
"""dich_geminicli.py — Gọi Gemini CLI như một bộ dịch chạy MỘT LẦN (26/11/2026).

"Gemini CLI" ở đây là Antigravity CLI của Google (lệnh `agy`), KHÔNG phải lệnh `gemini`
cũ: Google ngừng phục vụ `gemini` cho tài khoản Google cá nhân từ 18/6/2026 (đăng nhập
vẫn qua nhưng hỏi thì báo "migrate to the Antigravity suite"). `agy` dùng chung đăng
nhập với Antigravity IDE — cùng cách tool "Ghép video Flow" đang gọi (hoi_gemini.py).

Module này là NHÁNH GEMINI của dich_gptcli: bên ngoài không gọi thẳng, cứ gọi
dich_gptcli.goi / kiem_tra / hieu_luc… với nha="gemini" (hoặc để trống — khi ô cách
dịch chọn "gemini_cli" thì dich_gptcli tự rẽ sang đây). Nhờ vậy dịch truyện theo đoạn,
🔁 dịch lại đoạn trống, 📑 SEO và dịch SRT bên myvideo dùng được Gemini mà không đổi gì.

Lệnh chạy:
    agy --output-format json --disable-slash-commands --print-timeout <N>s
        [--model id] -p <đề bài>
→ một dòng JSON {"status":"SUCCESS","response":...} hoặc {"status":"ERROR","error":...}.
  • stdin KHÔNG được coi là đề bài. Đề bài dài quá giới hạn dòng lệnh Windows (32767
    ký tự) thì ghi ra file trong thư mục làm việc rồi bảo agy đọc file đó.
  • `agy` là agent có công cụ; ở chế độ in (-p) công cụ cần xin phép tự bị từ chối, chỉ
    đọc được file trong thư mục làm việc → mỗi lệnh chạy trong một thư mục tạm RỖNG.
  • Mỗi lệnh là một phiên mới (không truyền --conversation) — không nhớ gì, y như codex.

Chọn binary: biến OMNI_GEMINI_CLI (đuôi .py thì chạy bằng python hiện tại — stub thử
nghiệm) → không đặt thì quét PATH + chỗ cài quen thuộc (~/.gemini/bin do Antigravity IDE
tải về, %LOCALAPPDATA%\\agy\\bin do script cài), lấy bản MỚI NHẤT.

Model: tham số → biến OMNI_GEMINI_CLI_MODEL → ô cài đặt tab ✨ Gemini CLI (khoá
geminicli_model trong taogiong_pipeline.json) → trống thì agy tự chọn. Gemini KHÔNG có
ô "mức cố gắng" riêng: mức nằm ngay trong tên model (gemini-4-neon-high / -medium / -low).

Đăng nhập: chạy `agy` trong terminal, làm theo màn hình (trình duyệt mở trang Google).
Token nằm trong Windows Credential Manager, mục "gemini:antigravity" — có mục này = đã
đăng nhập (chỉ đọc email trong id_token để hiện lên tab, không giữ token).
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import dich_gptcli as gc
from dich_gptcli import GptCliError

TEN = "Gemini CLI"
_TEN_FILE = ("agy.exe", "agy.cmd", "agy") if os.name == "nt" else ("agy",)
_KHOA_MODEL = "geminicli_model"
_KHO = "gemini:antigravity"            # mục giữ token trong Windows Credential Manager
GIOI_HAN_DONG_LENH = 30000             # Windows cho tối đa 32767 ký tự cả dòng lệnh
TEN_FILE_DE_BAI = "de_bai.txt"
CAU_DOC_FILE = (f"Toàn bộ yêu cầu nằm trong file {TEN_FILE_DE_BAI} ở thư mục làm việc hiện "
                "tại. Hãy đọc hết file đó rồi trả lời đúng theo yêu cầu ghi trong file. Chỉ "
                "in ra câu trả lời, không tạo hay sửa file nào.")
NHAC_KHONG_CONG_CU = "\n\n(Trả lời trực tiếp bằng văn bản; không dùng công cụ, không chạy lệnh.)"
LENH_CAI = ('powershell -NoProfile -ExecutionPolicy Bypass -Command '
            '"irm https://antigravity.google/cli/install.ps1 | iex"')
# Dùng khi chưa hỏi được `agy models` (chưa đăng nhập / mất mạng) — id của agy 1.5.
MODEL_MAC_DINH = [("gemini-4-neon-high", "Gemini 4 Neon (High)"),
                  ("gemini-4-carbon-medium", "Gemini 4 Carbon (Medium)"),
                  ("gemini-3.8-flash-medium", "Gemini 3.8 Flash (Medium)")]
MODEL_NHO, MODEL_NHO_LOI = 6 * 3600, 300   # giây nhớ danh sách: hỏi được / không hỏi được


def _thu_muc_ung_vien():
    """PATH + chỗ agy hay nằm (server mở từ shortcut có thể thiếu PATH)."""
    ds = [d.strip().strip('"') for d in os.environ.get("PATH", "").split(os.pathsep)]
    home = Path.home()
    ds += [str(home / ".gemini" / "bin"), str(home / "AppData" / "Local" / "agy" / "bin"),
           str(home / ".local" / "bin")]
    return [d for d in ds if d]


def ung_vien():
    seen, out = set(), []
    for d in _thu_muc_ung_vien():
        for ten in _TEN_FILE:
            p = os.path.join(d, ten)
            key = os.path.normcase(os.path.abspath(p))
            if key not in seen and os.path.isfile(p):
                seen.add(key)
                out.append(p)
    return out


_cache = {}
_model_cache = {}


def tim_agy():
    """(đường dẫn, phiên bản) agy dùng được: OMNI_GEMINI_CLI nếu đặt, không thì bản MỚI
    NHẤT tìm thấy. Nhớ trong tiến trình."""
    if "path" in _cache:
        return _cache["path"], _cache["ver"]
    env = gc._env("OMNI_GEMINI_CLI")
    if env:
        ver = gc.phien_ban(env)
        if ver is None:
            raise GptCliError(f"OMNI_GEMINI_CLI={env} không chạy được (`--version` lỗi).")
        _cache.update(path=env, ver=ver)
        return env, ver
    best = None
    for p in ung_vien():
        ver = gc.phien_ban(p)
        if ver and (best is None or ver > best[1]):
            best = (p, ver)
    if best is None:
        raise GptCliError(
            "Không tìm thấy lệnh agy (Antigravity CLI — Gemini). Cài bằng PowerShell: "
            f"{LENH_CAI} rồi chạy `agy` để đăng nhập Google; hoặc đặt "
            "OMNI_GEMINI_CLI=<đường dẫn agy.exe>.")
    _cache.update(path=best[0], ver=best[1])
    return best


def _kho_doc():
    """Nội dung mục token trong Windows Credential Manager; không có → None."""
    import ctypes
    from ctypes import wintypes

    class CRED(ctypes.Structure):
        _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD),
                    ("TargetName", wintypes.LPWSTR), ("Comment", wintypes.LPWSTR),
                    ("LastWritten", wintypes.FILETIME), ("CredentialBlobSize", wintypes.DWORD),
                    ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                    ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD),
                    ("Attributes", ctypes.c_void_p), ("TargetAlias", wintypes.LPWSTR),
                    ("UserName", wintypes.LPWSTR)]

    adv = ctypes.WinDLL("advapi32", use_last_error=True)
    adv.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                              ctypes.POINTER(ctypes.c_void_p)]
    adv.CredReadW.restype = wintypes.BOOL
    adv.CredFree.argtypes = [ctypes.c_void_p]
    p = ctypes.c_void_p()
    if not adv.CredReadW(_KHO, 1, 0, ctypes.byref(p)):          # 1 = CRED_TYPE_GENERIC
        return None
    try:
        c = ctypes.cast(p, ctypes.POINTER(CRED)).contents
        return ctypes.string_at(c.CredentialBlob, c.CredentialBlobSize) if c.CredentialBlobSize else b""
    finally:
        adv.CredFree(p)


def dang_nhap(binary=None):
    """(đã đăng nhập?, dòng trạng thái). Chỉ xem máy, không mở mạng. Binary là stub
    (OMNI_GEMINI_CLI) hoặc không phải Windows → không kiểm được, coi như đã đăng nhập
    (lệnh gửi thật sẽ báo nếu chưa)."""
    if gc._env("OMNI_GEMINI_CLI") or os.name != "nt":
        return True, "không kiểm được ở đây — lệnh gửi sẽ báo nếu chưa đăng nhập"
    try:
        blob = _kho_doc()
    except Exception as e:
        return False, f"không đọc được kho mật khẩu Windows: {e}"
    if blob is None:
        return False, "chưa đăng nhập Google — mở terminal chạy `agy` rồi làm theo màn hình"
    email = ""
    try:
        import base64
        than = str(json.loads(blob.decode("utf-8")).get("id_token") or "").split(".")[1]
        email = str(json.loads(base64.urlsafe_b64decode(than + "=" * (-len(than) % 4))).get("email") or "")
    except Exception:
        pass
    return True, "đăng nhập Google (Antigravity)" + (f" — {email}" if email else "")


def kiem_tra():
    """Cùng khuôn dich_gptcli.kiem_tra: path, version, logged_in, login."""
    path, ver = tim_agy()
    ok, line = dang_nhap(path)
    return {"path": path, "version": ".".join(map(str, ver)), "logged_in": ok, "login": line}


def cai_dat():
    return {"model": str(gc._doc_pipe().get(_KHOA_MODEL) or "").strip(), "effort": ""}


def luu_cai_dat(model=None, effort=None):
    """Ghi RIÊNG khoá geminicli_model, giữ nguyên mọi cài đặt khác (effort bỏ qua —
    Gemini gộp mức vào tên model)."""
    if model is not None:
        d = gc._doc_pipe()
        d[_KHOA_MODEL] = str(model).strip()
        gc._pipe_file().write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    return cai_dat()


def danh_sach_model():
    """Model Gemini mà agy đang cho dùng (`agy models`, cần mạng → nhớ MODEL_NHO giây).
    Chưa đăng nhập / lỗi → danh sách mặc định. Cùng khuôn dich_gptcli.danh_sach_model."""
    def khuon(cap):
        return [{"slug": s, "ten": t, "mo_ta": "", "mac_dinh": "", "muc": [], "uu_tien": i}
                for i, (s, t) in enumerate(cap)]
    try:
        path, _ = tim_agy()
    except GptCliError:
        return khuon(MODEL_MAC_DINH)
    now = time.time()
    if _model_cache.get("path") == path and now < _model_cache.get("het", 0):
        return _model_cache["kq"]
    cap = []
    if dang_nhap(path)[0]:               # chưa đăng nhập thì không gọi (agy tự bật đăng nhập)
        tmp = tempfile.mkdtemp(prefix="omni_geminicli_")
        try:
            _, out, _ = gc._chay(path, ["models"], stdin_text="", timeout=40, cwd=tmp)
            for dong in out.splitlines():        # "gemini-4-neon-high<TAB>Gemini 4 Neon (High)"
                phan = re.split(r"\t+|\s{2,}", dong.strip(), maxsplit=1)
                if len(phan) == 2 and phan[0].startswith("gemini-") and phan[1].strip():
                    cap.append((phan[0], phan[1].strip()))
        except (OSError, subprocess.SubprocessError):
            cap = []
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    _model_cache.update(path=path, kq=khuon(cap or MODEL_MAC_DINH),
                        het=now + (MODEL_NHO if cap else MODEL_NHO_LOI))
    return _model_cache["kq"]


def hieu_luc():
    """Model SẼ dùng cho lệnh kế và lấy từ đâu (cùng khuôn dich_gptcli.hieu_luc)."""
    out = {"effort": "", "effort_nguon": "gộp trong tên model"}
    if gc._env("OMNI_GEMINI_CLI_MODEL"):
        out["model"], out["model_nguon"] = gc._env("OMNI_GEMINI_CLI_MODEL"), "biến môi trường OMNI_GEMINI_CLI_MODEL"
    elif cai_dat()["model"]:
        out["model"], out["model_nguon"] = cai_dat()["model"], "ô cài đặt tab Gemini CLI"
    else:
        out["model"], out["model_nguon"] = "", "agy tự chọn"
    return out


def mo_ta_hieu_luc(hl=None):
    hl = hl or hieu_luc()
    return f"{hl['model'] or 'model agy tự chọn'} ({hl['model_nguon']})"


def _doc_json(out):
    """Dòng JSON kết quả trong stdout (agy có thể in thêm dòng chữ phía trước)."""
    for dong in reversed((out or "").strip().splitlines()):
        dong = dong.strip()
        if not dong.startswith("{"):
            continue
        try:
            d = json.loads(dong)
        except ValueError:
            continue
        if isinstance(d, dict) and ("status" in d or "response" in d):
            return d
    return None


def _rut_gon_loi(s):
    s = " | ".join(l.strip() for l in (s or "").splitlines() if l.strip())
    thuong = s.lower()
    if "invalid model selection" in thuong:
        s = "Model này không có trong agy — chọn lại ở tab ✨ Gemini CLI (hoặc để agy tự chọn). " + s
    elif any(t in thuong for t in ("not signed in", "unauthenticated", "sign in to",
                                   "please log in", "login required", " 401")):
        s = "Chưa đăng nhập Google cho agy — mở terminal chạy `agy` để đăng nhập. " + s
    return s[:400]


def _mot_lenh(path, prompt, model, timeout, tmp):
    """Chạy agy một lượt → dict JSON kết quả (status SUCCESS). Lỗi → GptCliError."""
    dau = ["--output-format", "json", "--disable-slash-commands",
           "--print-timeout", f"{max(5, int(timeout))}s"]
    if model:
        dau += ["--model", model]
    args = dau + ["-p", prompt]
    if len(subprocess.list2cmdline(gc._lenh(path) + args)) > GIOI_HAN_DONG_LENH:
        Path(tmp, TEN_FILE_DE_BAI).write_text(prompt, encoding="utf-8")
        args = dau + ["-p", CAU_DOC_FILE]
    try:
        rc, out, err = gc._chay(path, args, stdin_text="", timeout=timeout + 20, cwd=tmp)
    except subprocess.TimeoutExpired:
        raise GptCliError(f"{TEN} không trả lời sau {timeout} giây.") from None
    except OSError as e:
        raise GptCliError(f"Không chạy được {path}: {e}") from None
    d = _doc_json(out)
    if d is None:
        raise GptCliError(f"agy (mã {rc}) không có trả lời: "
                          f"{_rut_gon_loi(err or out) or '(im lặng)'}")
    if d.get("error") or str(d.get("status") or "SUCCESS").upper() != "SUCCESS":
        loi = str(d.get("error") or d.get("status"))
        if "print timeout" in loi:
            raise GptCliError(f"{TEN} không trả lời sau {timeout} giây.")
        raise GptCliError(f"agy báo lỗi: {_rut_gon_loi(loi)}")
    return d


def goi(prompt, timeout=None, on_log=None, model=None):
    """Chạy MỘT lệnh `agy -p` với đề bài → văn bản trả lời. Cùng khuôn dich_gptcli.goi."""
    path, _ = tim_agy()
    timeout = timeout or gc.TIMEOUT
    if model is None:
        model = gc._env("OMNI_GEMINI_CLI_MODEL") or cai_dat()["model"]
    tmp = tempfile.mkdtemp(prefix="omni_geminicli_")
    t0 = time.time()
    try:
        d = _mot_lenh(path, prompt, model, timeout, tmp)
        text = str(d.get("response") or "").strip()
        if not text and d.get("denied_actions"):
            # model định dùng công cụ (bị từ chối ở chế độ in) thay vì trả lời → nhắc, hỏi lại MỘT lần
            d = _mot_lenh(path, prompt + NHAC_KHONG_CONG_CU, model, timeout, tmp)
            text = str(d.get("response") or "").strip()
        if not text:
            raise GptCliError(f"{TEN} không trả lời bằng chữ"
                              + (" (định dùng công cụ)." if d.get("denied_actions") else "."))
        if on_log:
            on_log(f"⏱ {TEN} trả lời sau {time.time() - t0:.0f} s.")
        return text
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    return gc.main(argv, nha="gemini")


if __name__ == "__main__":
    sys.exit(main())
