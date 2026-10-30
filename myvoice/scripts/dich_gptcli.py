# -*- coding: utf-8 -*-
"""dich_gptcli.py — Gọi GPT CLI (OpenAI Codex CLI, lệnh `codex exec`) như một bộ dịch
chạy MỘT LẦN: đưa đề bài qua stdin, nhận câu trả lời cuối cùng qua file `-o`.

Dùng ở hai chỗ:
  • myvideo/dich_srt.py --cli (dịch phụ đề SRT): gọi thẳng goi() — đề bài, cắt lô,
    kiểm tra kết quả nằm ở bên gọi.
  • dich_gemini (dịch truyện theo đoạn, 🔁 dịch lại đoạn trống, SEO myvoice/myvideo):
    khi ô cách dịch chọn "cli", init_firefox trả về GptCliDriver bên dưới — "driver"
    giả cùng giao diện với driver trình duyệt, mỗi lần gửi là một lệnh codex exec.

KHÁC HẲN Gemini web: không có cuộc trò chuyện. Mỗi lệnh `codex exec` là một phiên
mới, chạy xong là quên sạch — không nhớ lời dặn, không nhớ lô trước. Bên gọi phải
gửi lại TOÀN BỘ yêu cầu dịch kèm từng lô (xem dich_srt.cli_prompt).

Chọn binary: biến OMNI_GPT_CLI (đường dẫn codex / codex.cmd; đuôi .py thì chạy
bằng python hiện tại — để thử nghiệm bằng stub) → không đặt thì quét PATH và lấy
bản codex MỚI NHẤT. Lý do không lấy bản đầu tiên PATH trả về: máy này (27/10/2026)
có hai bản — Roaming\\npm\\codex.cmd 0.84.0 đứng TRƯỚC trong PATH nhưng lỗi "model
not supported when using Codex with a ChatGPT account", còn nvm4w\\nodejs\\codex.cmd
0.163.0 chạy được.

Model và mức cố gắng (reasoning effort) — thứ tự ưu tiên: tham số goi() → biến
OMNI_GPT_CLI_MODEL / OMNI_GPT_CLI_EFFORT → ô cài đặt ở tab 🤖 GPT CLI của web myvoice
(hai khoá gptcli_model / gptcli_effort trong taogiong_pipeline.json — cùng file với ô
cách dịch, nên web myvoice · web myvideo · GUI đọc chung; xem cai_dat / luu_cai_dat /
hieu_luc) → để trống thì codex lấy theo ~/.codex/config.toml. Danh sách model tài khoản
này dùng được đọc từ ~/.codex/models_cache.json mà codex tự tải (danh_sach_model).
OMNI_GPT_CLI_TIMEOUT: giây chờ tối đa mỗi lệnh (mặc định 600 — lô 10 câu Trung đo
được ~36 s).

An toàn: mỗi lệnh chạy trong một thư mục tạm RỖNG (-C) với sandbox read-only, nên
mô hình không đọc được repo và không ghi được gì; thư mục tạm xoá ngay sau lệnh.

Cách dùng lẻ:
    python dich_gptcli.py --kiem-tra              # binary · phiên bản · đăng nhập
    echo "Dịch sang tiếng Việt: 你好" | python dich_gptcli.py
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

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

TIMEOUT = int(os.environ.get("OMNI_GPT_CLI_TIMEOUT", "600"))


def _env(name):
    """Biến môi trường đọc LÚC GỌI (GUI/web đặt trước khi chạy; test đặt sau khi import)."""
    return os.environ.get(name, "").strip()


_VER_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)   # web chạy ẩn: đừng bật console
# Tên file codex trên PATH (npm sinh codex.cmd trên Windows; bản exe nếu cài kiểu khác).
_TEN = ("codex.cmd", "codex.exe", "codex") if os.name == "nt" else ("codex",)


class GptCliError(RuntimeError):
    """Không gọi được GPT CLI (thiếu binary, chưa đăng nhập, hết giờ, lỗi API...)."""


def _lenh(binary):
    """argv mở đầu: file .py → chạy bằng python hiện tại (stub thử nghiệm / wrapper)."""
    if binary.lower().endswith(".py"):
        return [sys.executable, binary]
    return [binary]


def _chay(binary, args, stdin_text=None, timeout=60, cwd=None):
    """Chạy binary với args, trả (mã, stdout, stderr). Mọi luồng là UTF-8."""
    p = subprocess.run(_lenh(binary) + list(args), input=stdin_text,
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout, cwd=cwd,
                       creationflags=_NO_WINDOW,
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    return p.returncode, p.stdout or "", p.stderr or ""


def phien_ban(binary):
    """(major, minor, patch) của binary theo `--version`, hoặc None nếu không chạy được."""
    try:
        rc, out, err = _chay(binary, ["--version"], timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    m = _VER_RE.search(out + " " + err)
    return tuple(int(x) for x in m.groups()) if rc == 0 and m else None


def ung_vien():
    """Mọi codex tìm thấy trên PATH (bỏ trùng), theo thứ tự PATH."""
    seen, out = set(), []
    for d in os.environ.get("PATH", "").split(os.pathsep):
        d = d.strip().strip('"')
        if not d:
            continue
        for ten in _TEN:
            p = os.path.join(d, ten)
            key = os.path.normcase(os.path.abspath(p))
            if key not in seen and os.path.isfile(p):
                seen.add(key)
                out.append(p)
    return out


_cache = {}


def tim_codex():
    """(đường dẫn, phiên bản) codex dùng được: OMNI_GPT_CLI nếu đặt, không thì bản
    MỚI NHẤT trên PATH. Kết quả nhớ trong tiến trình (quét PATH tốn ~0,5 s/bản)."""
    if "path" in _cache:
        return _cache["path"], _cache["ver"]
    env = os.environ.get("OMNI_GPT_CLI", "").strip()
    if env:
        ver = phien_ban(env)
        if ver is None:
            raise GptCliError(f"OMNI_GPT_CLI={env} không chạy được (`--version` lỗi).")
        _cache.update(path=env, ver=ver)
        return env, ver
    best = None
    for p in ung_vien():
        ver = phien_ban(p)
        if ver and (best is None or ver > best[1]):
            best = (p, ver)
    if best is None:
        raise GptCliError(
            "Không tìm thấy codex trên PATH. Cài: `npm i -g @openai/codex` rồi `codex login` "
            "(đăng nhập ChatGPT); hoặc đặt OMNI_GPT_CLI=<đường dẫn codex.cmd>.")
    _cache.update(path=best[0], ver=best[1])
    return best


def dang_nhap(binary):
    """(đã đăng nhập?, dòng trạng thái) theo `codex login status`."""
    try:
        rc, out, err = _chay(binary, ["login", "status"], timeout=30)
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"không kiểm được đăng nhập: {e}"
    line = " ".join((out + " " + err).split()) or "(không có trả lời)"
    return rc == 0, line[:120]


def kiem_tra():
    """Thông tin để in đầu lượt dịch: path, version, logged_in, login (dòng trạng thái).
    Không tìm thấy binary → GptCliError."""
    path, ver = tim_codex()
    ok, line = dang_nhap(path)
    return {"path": path, "version": ".".join(map(str, ver)), "logged_in": ok, "login": line}


# ── Cài đặt model / mức cố gắng (tab 🤖 GPT CLI, 29/10/2026) ─────────────────
# Lưu trong taogiong_pipeline.json — cùng file với ô cách dịch (gemini_backend) nên
# web myvoice, web myvideo (dich_srt) và GUI đọc chung; goi() đọc lại mỗi lệnh nên đổi
# ở tab là lệnh kế dùng ngay. Trống = để codex tự lấy theo ~/.codex/config.toml.
# Mức "ultra" (tự chia việc cho agent con) không đưa vào: dịch không cần, lại chạy
# trong sandbox chỉ đọc.
MUC_CO_GANG = ("low", "medium", "high", "xhigh", "max")
MUC_CO_GANG_NHAN = {
    "low": ("🐇 Thấp", "nhanh, suy nghĩ ít — câu ngắn, đơn giản"),
    "medium": ("⚖️ Vừa", "cân bằng tốc độ và chất lượng — hợp dịch truyện"),
    "high": ("🧠 Cao", "suy nghĩ kỹ hơn, chậm hơn — đoạn khó, nhiều điển tích"),
    "xhigh": ("🔬 Rất cao", "rất chậm; hiếm khi cần cho dịch"),
    "max": ("🏔 Tối đa", "chậm nhất, tốn hạn mức nhất"),
}
_KHOA_MODEL, _KHOA_EFFORT = "gptcli_model", "gptcli_effort"


def _pipe_file():
    import gemini_backend            # cùng thư mục; một chỗ định nghĩa đường dẫn file
    return Path(gemini_backend.PIPE_FILE)


def _doc_pipe():
    try:
        data = json.loads(_pipe_file().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _chuan_effort(value):
    value = str(value or "").strip().lower()
    return value if value in MUC_CO_GANG else ""


def cai_dat():
    """{"model", "effort"} ĐÃ LƯU ở tab 🤖 (trống = theo config.toml của codex)."""
    d = _doc_pipe()
    return {"model": str(d.get(_KHOA_MODEL) or "").strip(),
            "effort": _chuan_effort(d.get(_KHOA_EFFORT))}


def luu_cai_dat(model=None, effort=None):
    """Ghi RIÊNG hai khoá gptcli_*, giữ nguyên mọi cài đặt khác trong file (như
    gemini_backend.set_backend). None = không đổi; "" = về mặc định config.toml."""
    d = _doc_pipe()
    if model is not None:
        d[_KHOA_MODEL] = str(model).strip()
    if effort is not None:
        d[_KHOA_EFFORT] = _chuan_effort(effort)
    _pipe_file().write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    return cai_dat()


def codex_home():
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def config_mac_dinh():
    """model / model_reasoning_effort trong ~/.codex/config.toml — thứ codex dùng khi ta
    không chỉ định. Không đọc được → trống."""
    try:
        import tomllib
        with open(codex_home() / "config.toml", "rb") as f:
            d = tomllib.load(f)
    except Exception:
        return {"model": "", "effort": ""}
    return {"model": str(d.get("model") or "").strip(),
            "effort": str(d.get("model_reasoning_effort") or "").strip()}


def danh_sach_model():
    """Model tài khoản này dùng được, theo ~/.codex/models_cache.json mà codex tự tải
    (chỉ visibility "list"), xếp theo priority codex đề nghị. Không có file → []."""
    try:
        d = json.loads((codex_home() / "models_cache.json").read_text(encoding="utf-8"))
        models = d.get("models") or []
    except (OSError, ValueError, AttributeError):
        return []
    out = []
    for m in models:
        if not isinstance(m, dict) or not m.get("slug") or m.get("visibility", "list") != "list":
            continue
        muc = [x.get("effort") for x in (m.get("supported_reasoning_levels") or [])
               if isinstance(x, dict)]
        uu_tien = m.get("priority")
        out.append({"slug": m["slug"], "ten": m.get("display_name") or m["slug"],
                    "mo_ta": m.get("description") or "",
                    "mac_dinh": _chuan_effort(m.get("default_reasoning_level")),
                    "muc": [x for x in muc if x in MUC_CO_GANG],
                    "uu_tien": uu_tien if isinstance(uu_tien, int) else 999})
    out.sort(key=lambda x: (x["uu_tien"], x["slug"]))
    return out


def hieu_luc():
    """Model / mức cố gắng SẼ dùng cho lệnh kế và lấy từ đâu (tab 🤖 và nhật ký nói
    rõ): biến môi trường → ô cài đặt → config.toml → codex tự chọn."""
    saved, cfg = cai_dat(), config_mac_dinh()
    out = {}
    for k, ten_env in (("model", "OMNI_GPT_CLI_MODEL"), ("effort", "OMNI_GPT_CLI_EFFORT")):
        if _env(ten_env):
            out[k], out[k + "_nguon"] = _env(ten_env), f"biến môi trường {ten_env}"
        elif saved[k]:
            out[k], out[k + "_nguon"] = saved[k], "ô cài đặt tab GPT CLI"
        elif cfg[k]:
            out[k], out[k + "_nguon"] = cfg[k], "~/.codex/config.toml"
        else:
            out[k], out[k + "_nguon"] = "", "codex tự chọn"
    return out


def mo_ta_hieu_luc(hl=None):
    """Một dòng cho nhật ký: 'gpt-6.1-sol (ô cài đặt tab GPT CLI) · mức medium (…)'."""
    hl = hl or hieu_luc()
    return (f"{hl['model'] or 'model codex tự chọn'} ({hl['model_nguon']}) · "
            f"mức {hl['effort'] or 'mặc định'} ({hl['effort_nguon']})")


def goi(prompt, timeout=None, on_log=None, model=None, effort=None):
    """Chạy MỘT lệnh `codex exec` với đề bài (qua stdin) → văn bản trả lời cuối cùng.

    Đề bài đi qua stdin (tham số `-`) nên không vướng giới hạn độ dài / ký tự lạ của
    dòng lệnh Windows. Trả lời lấy từ file `-o` (chỉ tin nhắn cuối của mô hình, không
    lẫn dòng tiến trình). Lỗi → GptCliError kèm đuôi stderr để người dùng thấy lý do
    (chưa đăng nhập, model không hợp tài khoản, hết hạn mức...)."""
    path, _ = tim_codex()
    timeout = timeout or TIMEOUT
    if model is None:        # tham số → biến môi trường → ô cài đặt tab 🤖 → config.toml
        model = _env("OMNI_GPT_CLI_MODEL") or cai_dat()["model"]
    if effort is None:
        effort = _env("OMNI_GPT_CLI_EFFORT") or cai_dat()["effort"]
    tmp = tempfile.mkdtemp(prefix="omni_gptcli_")
    out_file = os.path.join(tmp, "tra_loi.txt")
    args = ["exec", "--skip-git-repo-check", "-s", "read-only", "--color", "never",
            "-C", tmp, "-o", out_file]
    if model:
        args += ["-m", model]
    if effort:
        args += ["-c", f'model_reasoning_effort="{effort}"']
    args.append("-")
    t0 = time.time()
    try:
        try:
            rc, out, err = _chay(path, args, stdin_text=prompt, timeout=timeout, cwd=tmp)
        except subprocess.TimeoutExpired:
            raise GptCliError(f"GPT CLI không trả lời sau {timeout} giây.") from None
        except OSError as e:
            raise GptCliError(f"Không chạy được {path}: {e}") from None
        try:
            with open(out_file, encoding="utf-8") as f:
                text = f.read().strip()
        except OSError:
            text = ""
        if not text:
            duoi = " | ".join(l.strip() for l in (err or out).splitlines() if l.strip())[-400:]
            raise GptCliError(f"codex exec (mã {rc}) không có trả lời: {duoi or '(im lặng)'}")
        if on_log:
            on_log(f"⏱ GPT CLI trả lời sau {time.time() - t0:.0f} s"
                   + (f" (mã thoát {rc})" if rc else "") + ".")
        return text
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── "Driver" giả cho dich_gemini (cách dịch "cli") ────────────────────────────
# Dòng mở đầu MỌI lệnh (29/10/2026 viết gọn): nói rõ bối cảnh một lần, không hội thoại.
CLI_HEADER = (
    "Bạn được gọi qua dòng lệnh MỘT LẦN: không có hội thoại, không nhớ gì giữa hai lệnh, "
    "mọi yêu cầu nằm trọn trong tin này. Không đọc hay ghi file, không chạy lệnh, không "
    "hỏi lại — chỉ in câu trả lời.")
NGU_CANH_MAX_CHARS = 400     # đuôi bản dịch đoạn trước gửi kèm lệnh kế (nối mạch, xưng hô)


def duoi_van_ban(text, n=NGU_CANH_MAX_CHARS):
    """n ký tự cuối của text, lùi tới đầu câu gần nhất cho khỏi cụt."""
    t = " ".join((text or "").split())
    if len(t) <= n:
        return t
    t = t[-n:]
    m = re.search(r"[.!?…]\s+", t)
    return t[m.end():] if m and m.end() < len(t) - 40 else t


class GptCliDriver:
    """Thay cho driver trình duyệt trong dich_gemini khi cách dịch là "cli".

    Cùng giao diện mà dich_gemini / SEO / dich_lai_trong đụng tới (get, quit,
    current_url, generating, is_chrome_extension) nhưng mỗi send() là MỘT lệnh
    `codex exec` riêng — không có hội thoại. Vì vậy mỗi lệnh tự mang đủ:
      CLI_HEADER → câu hướng dẫn đã đăng ký (set_instruction — thay cho tin nhắn
      hướng dẫn riêng của Gemini) → prefix của lần gửi (nếu có) → đuôi bản dịch
      đoạn trước (remember; chỉ khi đang dịch theo đoạn) → nội dung.
    get(url) = "chat mới": quên hướng dẫn lẫn ngữ cảnh, y như Gemini mở chat mới
    (bên gọi gửi lại câu hướng dẫn như họ vẫn làm)."""
    is_gpt_cli = True
    is_chrome_extension = False
    generating = False

    def __init__(self, url="", on_log=None):
        self.url = url or "gpt-cli://codex"
        self.instruction = ""
        self.context = ""
        self.calls = 0
        self.info = kiem_tra()                       # không có codex → GptCliError
        if on_log:
            on_log(f"🤖 GPT CLI: {self.info['path']} (codex-cli {self.info['version']}) "
                   f"— {self.info['login']}")
            on_log(f"🎛 {mo_ta_hieu_luc()}")
            if not self.info["logged_in"]:
                on_log("⚠️ Có vẻ chưa đăng nhập: mở terminal chạy `codex login` (tài khoản "
                       "ChatGPT). Vẫn thử gửi...")

    @property
    def current_url(self):
        return self.url

    def get(self, url=None):
        """Chat mới: giữ url (SEO so id cuộc trò chuyện), quên hướng dẫn + ngữ cảnh."""
        if url:
            self.url = url
        self.instruction = ""
        self.context = ""

    def quit(self):
        pass

    def set_instruction(self, text):
        self.instruction = (text or "").strip()

    def remember(self, reply):
        """Nhớ bản dịch vừa nhận để lệnh kế có đuôi của nó làm ngữ cảnh."""
        self.context = (reply or "").strip()

    def compose(self, text, prefix=""):
        parts = [CLI_HEADER]
        if self.instruction:
            parts.append(self.instruction)
        if prefix and prefix.strip():
            parts.append(prefix.strip())
        if self.instruction and self.context:
            parts.append("ĐUÔI BẢN DỊCH ĐOẠN TRƯỚC (chỉ để nối mạch, thống nhất tên và "
                         "xưng hô; không dịch lại, không in lại):\n"
                         + duoi_van_ban(self.context))
        parts.append(("ĐOẠN CẦN DỊCH:\n" + text) if self.instruction else text)
        return "\n\n".join(parts)

    def send(self, text, prefix="", timeout=None, on_log=None):
        """Một lệnh codex exec → văn bản trả lời. Lỗi lần đầu thử lại đúng một lần
        (mạng/CLI trục trặc thoáng qua); lỗi lần hai ném GptCliError ra ngoài."""
        prompt = self.compose(text, prefix)
        self.calls += 1
        try:
            return goi(prompt, timeout=timeout, on_log=on_log)
        except GptCliError as e:
            if on_log:
                on_log(f"⚠️ GPT CLI lỗi: {e} — thử lại một lần...")
            return goi(prompt, timeout=timeout, on_log=on_log)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(
        description="Gọi GPT CLI (codex exec) MỘT lần với đề bài đọc từ stdin.")
    ap.add_argument("--kiem-tra", action="store_true",
                    help="Chỉ báo binary / phiên bản / trạng thái đăng nhập rồi thoát.")
    a = ap.parse_args(argv)
    try:
        info = kiem_tra()
    except GptCliError as e:
        print(f"❌ {e}")
        return 1
    print(f"🤖 {info['path']} (codex-cli {info['version']}) — {info['login']}")
    print(f"🎛 {mo_ta_hieu_luc()}")
    if a.kiem_tra:
        return 0 if info["logged_in"] else 1
    prompt = sys.stdin.read()
    if not prompt.strip():
        print("❌ Đề bài rỗng (đưa qua stdin).")
        return 1
    try:
        print(goi(prompt, on_log=print))
    except GptCliError as e:
        print(f"❌ {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
