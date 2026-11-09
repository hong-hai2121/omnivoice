"""Chạy các bước của MỘT tập — runner cho bảng điều khiển web.

Web không tự viết lại quy trình: nó tạo một App “rỗng” (không dựng cửa sổ Tk) rồi
gọi thẳng các method thuần logic của amain_taogiong_gui — cùng các chốt an toàn mà
GUI dùng (dịch thiếu đoạn thì KHÔNG ghi input.txt, không tạo audio/video…). Sửa
chốt ở scripts/ là web hưởng ngay, khỏi lo hai bản lệch nhau.

Cách gọi (jobs.py lo phần này):
    python run_episode.py --steps translate,input,seo,thumbnail \
        --source "<link|file>" [--episode 07] [--model medium] [--speed 0.7] \
        [--tts-json <file>] [--force]

Mã thoát: 0 = xong · 77 = dừng có chủ ý (bước chặn, vd dịch chưa đủ) · 2 = lỗi ·
78 = SEO hỏng nhưng không có bước dựng video trong lần gọi này (chuỗi còn bước dựng
video phía sau thì hàng đợi đi tiếp). SEO hỏng mà lần gọi CÓ dựng video → chạy hết,
trả 77 để hàng đợi KHÔNG nối việc đăng YouTube / lên lịch Facebook.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import os
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

_WEB_DIR = Path(__file__).resolve().parent.parent
_BASE_DIR = _WEB_DIR.parent                     # myvoice/
for _p in (str(_BASE_DIR.parent), str(_BASE_DIR / "scripts"), str(_BASE_DIR / "YOUTUBE"),
           str(_BASE_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Chống phình VRAM (giải thích đầy đủ ở đầu scripts/amain_taogiong_gui.py). Đặt
# lại ngay tại cửa vào tiến trình chứ không phó mặc thứ tự import: biến này chỉ ăn
# khi được đặt TRƯỚC lần import torch đầu tiên.
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "garbage_collection_threshold:0.8")

import amain_taogiong_gui as gui                # noqa: E402
from giu_man_hinh import CHO_SANG, NHICH_SAU, giu_man_hinh  # noqa: E402
from myvoice.web import core                    # noqa: E402

# KHÔNG dùng 1 cho "dừng có chủ ý": Python thoát mã 1 khi crash trước khi vào
# main() (vd lỗi import) — dùng chung số là nhầm crash thành chốt an toàn.
# Đổi số này thì đổi cả STOP_CODE trong web/steps.py.
STOP = 77       # dừng có chủ ý — không phải sự cố
ERROR = 2
# SEO hỏng (03/10/2026): KHÔNG chặn cả tập nữa — mẻ chạy đêm 03/10 mất trọn 4 tập vì
# Gemini không nhận tin lúc 04:23. Bước SEO/thumbnail trả mã này, main() ghi nhớ rồi
# đi tiếp; tạo giọng + video ngang vẫn làm, video dọc/TikTok/Short (in tiêu đề SEO)
# để dành tới khi có SEO, và KHÔNG tự đăng. Khớp SEO_SOFT_CODE trong web/steps.py.
SEO_SOFT = 78

# "tai" (17/10/2026): CHỈ tải video/audio của nguồn về máy — ⏩ xếp đợt tải cho mọi
# tập trước, rồi mới nhận diện hàng loạt; "recognize" chạy sau thấy file có sẵn thì
# dùng lại ngay (cả Bili23 lẫn yt-dlp đều bỏ qua khi file đích đã có).
ALL_STEPS = ["tai", "recognize", "translate", "input", "seo", "thumbnail", "tts"]
# Gộp "script" thành một bước lớn để dịch → SEO dùng CHUNG một phiên Firefox
# (mở hai lần thì phiên sau vấp profile đang bị khoá).
STEP_GROUPS = {"script": ["translate", "input", "seo", "thumbnail"],
               "all": ALL_STEPS}
# Bước chạy trong lúc giữ màn hình sáng (03/10/2026): màn hình tắt thì Chrome bóp tab
# Gemini → dịch/SEO hỏng (scripts/giu_man_hinh.py). Các bước khác màn hình tắt thoải mái.
GIU_MAN_HINH = {"recognize", "translate", "seo"}

# ⬇ LINK BILIBILI ở ô Nguồn (17/10/2026): tải VIDEO bản chất lượng cao nhất qua
# app Bili23 Downloader bằng script cầu nối bên myvideo — mượn NGUYÊN script
# (như gemini_backend dùng chung), không viết bộ tải thứ hai. File về
# Downloads/<mã BV>.mp4, TRÙNG chỗ với bên myvideo: video nào bên kia tải rồi
# thì bên này nhặt lại luôn. Link KHÔNG phải bilibili vẫn đi yt-dlp lấy mp3 như cũ.
TAIBILI_SCRIPT = _BASE_DIR.parent / "myvideo" / "video_taibilibili.py"
# Mẫu link/mã + tên file tải về đặt ở amain_taogiong_gui (24/10/2026): bước tts tra
# lại đúng file này khi bật 🎞 "lấy video tải xuống làm video nguồn".
_BILI_LINK_RE = gui.BILI_LINK_RE
_BILI_ID_RE = gui.BILI_ID_RE
# Link tải lỗi NOTE vào đây (giờ · tập · link · lý do) — log web chỉ nằm RAM,
# chạy đêm hỏng link nào sáng ra còn tra lại được.
LINK_LOI_FILE = _BASE_DIR / "kịch_bản" / "link_tai_loi.txt"


def note_link_loi(src: str, ly_do: str, episode: str = "") -> None:
    """Ghi một dòng vào sổ link lỗi — lỗi tải là chuyện của NGUỒN, phải giữ lại
    được sau khi log trôi/tắt server."""
    try:
        LINK_LOI_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LINK_LOI_FILE, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M}"
                    + (f" · tập {episode}" if episode else "")
                    + f" · {src} · {ly_do}\n")
        logging.info(f"📝 Đã note link lỗi vào kịch_bản/{LINK_LOI_FILE.name}")
    except OSError as e:
        logging.warning(f"⚠️ Không ghi được sổ link lỗi: {e}")


def _ten_tai_bilibili(src: str) -> str:
    """Link → tên file sẽ tải về (mã BV/av; link rút gọn b23.tv lấy mã rút gọn).
    Cùng quy ước với myvideo/web/steps.py để hai bên dùng chung một file."""
    return gui.ten_tai_bilibili(src)


def _tai_video_bilibili(src: str) -> tuple[str, str]:
    """Link bilibili → (đường dẫn video đã tải, ""), lỗi thì ("", lý do).

    Chạy video_taibilibili.py làm tiến trình con, in của nó đổ thẳng ra stdout
    cho web thấy tiến độ; dòng ❌ cuối cùng chính là lý do lỗi để note sổ."""
    ten = _ten_tai_bilibili(src)
    if not ten:
        return "", f"không nhận ra mã BV/av trong link: {src}"
    if not TAIBILI_SCRIPT.is_file():
        return "", f"thiếu script {TAIBILI_SCRIPT}"
    out = Path.home() / "Downloads" / f"{ten}.mp4"
    ly_do = ""
    try:
        p = subprocess.Popen([sys.executable, "-u", str(TAIBILI_SCRIPT), src,
                              "--out", str(out)],
                             cwd=str(_BASE_DIR.parent),
                             env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, encoding="utf-8", errors="replace")
        for line in p.stdout:
            line = line.rstrip()
            if line:
                print(line, flush=True)
            if line.startswith("❌"):
                ly_do = line.lstrip("❌").strip()
        rc = p.wait()
    except OSError as e:
        return "", f"không chạy được script tải: {e}"
    if rc == 0 and out.is_file():
        return str(out), ""
    return "", ly_do or f"script tải thoát mã {rc}"


class _Var:
    """Thay cho tk.StringVar/IntVar: các method của App chỉ gọi .set()/.get()."""

    def __init__(self, value=""):
        self._v = value

    def set(self, v):
        self._v = v

    def get(self):
        return self._v


class HeadlessApp(gui.App):
    """App KHÔNG có cửa sổ: cố tình không gọi super().__init__() nên không có
    interpreter Tk nào được dựng. Chỉ dùng cho các method thuần logic đã kiểm:
    _allocate_episode · _dich_gemini_cho_tap · _batch_prepare_input ·
    _make_thumbnail_for_folder · _save_youtube_seo_copy · _batch_run_tts ·
    _manifest_update. Method nào đụng widget sẽ nổ ngay — đó là chủ ý, để lệch
    nhau là biết liền chứ không âm thầm sai."""

    def __init__(self):            # noqa: D107  (cố ý không gọi super)
        self.progress = _Var(0)
        self.status = _Var("")

    def _bring_to_front(self):     # web không có cửa sổ để đưa lên trước
        pass


def _setup_logging() -> None:
    """Mọi logging.* của scripts/ đổ thẳng ra stdout để jobs.py hứng và đẩy lên web."""
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for h in list(root.handlers):
        root.removeHandler(h)
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(handler)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _resolve_folder(app: HeadlessApp, source: str, episode: str | None):
    """(folder, episode). Nguồn đã làm rồi → đúng tập cũ; nguồn mới → tập kế tiếp."""
    if episode:
        ep = str(episode).strip().zfill(2)
    else:
        if not source:
            raise SystemExit("Thiếu --source hoặc --episode.")
        ep, is_new = app._allocate_episode(source)
        logging.info(f"🔢 Tập {ep}" + (" (mới)" if is_new else " (đã có trong manifest)"))
    folder = gui.episode_dir_for(ep, source or None)
    folder.mkdir(parents=True, exist_ok=True)
    return folder, ep


# ── Từng bước ───────────────────────────────────────────────────────────────
def _fetch_media(source: str, episode: str) -> tuple[str, str]:
    """Nguồn → (đường dẫn file media, ""), lỗi → ("", lý do).

    File local dùng thẳng; link thì tải về (Bilibili: NGUYÊN VIDEO bản cao nhất qua
    app Bili23 — file dùng được cho cả myvideo; link khác: yt-dlp lấy mp3). Đã có
    file đích thì cả hai bộ tải đều bỏ qua ngay — nên bước "tai" chạy trước, bước
    "recognize" chạy sau không tải lại. Link tải lỗi được note vào sổ link lỗi."""
    src = (source or "").strip().strip('"').strip("'")
    if not src:
        return "", "Không có nguồn (link/file) để nhận diện."
    if os.path.isfile(src):
        logging.info(f"📁 File local: {src}")
        return src, ""
    if _BILI_LINK_RE.match(src):
        logging.info(f"⬇ Link Bilibili → tải video bản cao nhất qua app Bili23: {src}")
        media, ly_do = _tai_video_bilibili(src)
        if not media:
            note_link_loi(src, ly_do, episode)
            return "", f"Không tải được video Bilibili: {ly_do}"
        logging.info(f"✅ Video đã về: {media}")
        return media, ""
    if src.lower().startswith(("http://", "https://")):
        logging.info(f"🌐 Tải audio từ link: {src}")
        media = gui.download_audio_mp3(src, gui.DOWNLOAD_DIR)
        if not media:
            note_link_loi(src, "yt-dlp không tải được audio (xem log)", episode)
            return "", "Không tải được audio từ link."
        return media, ""
    return "", f"Nguồn không hợp lệ (không phải file cũng không phải link): {src}"


def step_tai(folder: Path, episode: str, source: str, force: bool) -> int:
    """Bước TẢI (17/10/2026): chỉ đem video/audio của nguồn về máy, KHÔNG nhận diện.
    ⏩ xếp đợt tải cho MỌI tập trước, xong hết mới tới đợt nhận diện. Đã có bản
    nhận diện thì khỏi tải (trừ khi --force)."""
    existing = gui.find_zh_docx(folder)
    if existing and gui.read_zh_docx_chunks(existing) and not force:
        logging.info(f"♻ Bỏ qua tải (đã có {existing.name}).")
        return 0
    media, ly_do = _fetch_media(source, episode)
    if not media:
        logging.error(f"❌ {ly_do}")
        return ERROR
    logging.info(f"✅ Sẵn sàng cho đợt nhận diện: {media}")
    return 0


def step_recognize(app, folder: Path, episode: str, source: str,
                   model: str, speed: float, force: bool) -> int:
    import nhandien_giongnoi as recog

    existing = gui.find_zh_docx(folder)
    if existing and gui.read_zh_docx_chunks(existing) and not force:
        logging.info(f"♻ Bỏ qua nhận diện (đã có {existing.name}).")
        return 0
    media, ly_do = _fetch_media(source, episode)
    if not media:
        logging.error(f"❌ {ly_do}")
        return ERROR

    try:
        transcript = recog.transcribe_chinese(
            media, model_name=model, speed=speed,
            on_progress=lambda f: print(f"⏳ Nhận diện {f * 100:.0f}%", flush=True))
        if not transcript:
            logging.error("❌ Không nhận diện được nội dung.")
            return ERROR
        zh_docx = folder / gui.ZH_DOCX_NAME
        recog.save_docx(transcript, str(zh_docx), title=Path(media).name)
        logging.info(f"💾 Đã lưu bản nhận diện: {zh_docx}")
        return 0
    finally:
        try:
            recog.free_model()
            logging.info("🧹 Đã nhả model nhận diện khỏi VRAM.")
        except Exception:
            pass


def _chunks_of(folder: Path):
    zh = gui.find_zh_docx(folder)
    return gui.read_zh_docx_chunks(zh) if zh else []


def step_translate(app, folder: Path, episode: str, state: dict) -> int:
    gemini_docx = folder / "gemini_result.docx"
    chunks = _chunks_of(folder)
    if not chunks:
        logging.error("❌ Chưa có bản nhận diện tiếng Trung (tiengTrung.docx) → chưa dịch được.")
        return ERROR

    driver, translated_now, ok = app._dich_gemini_cho_tap(
        gemini_docx, chunks, gui.load_prefix(), episode, state.get("driver"))
    state["driver"] = driver
    state["translated_now"] = translated_now
    if not ok:
        logging.error(f"⛔ Tập {episode}: dịch chưa xong → dừng, không tạo input/audio/video.")
        return STOP
    return 0


def step_input(app, folder: Path, episode: str, state: dict) -> int:
    gemini_docx = folder / "gemini_result.docx"
    import dich_input_docx as inputdocx
    input_txt = inputdocx.input_path(folder)          # input.docx (05/09/2026)
    if not gemini_docx.exists():
        logging.error("❌ Chưa có gemini_result.docx → chưa tạo được input.docx.")
        return ERROR
    # Vừa dịch xong thì LUÔN ghi lại: bản input cũ có thể được tạo từ bản dịch dở.
    if (not state.get("translated_now") and inputdocx.has_content(input_txt)
            and not state.get("force")):
        logging.info("♻ Bỏ qua tạo input.docx (đã có).")
        return 0
    if not app._batch_prepare_input(gemini_docx, input_txt):
        logging.error("⛔ Không ghi input.docx (xem lý do ở trên) → dừng tập này.")
        return STOP
    logging.info(f"💾 Đã tạo: {input_txt}")
    return 0


def step_seo(app, folder: Path, episode: str, state: dict) -> int:
    # ⛔ Bản dịch còn đoạn hỏng → không làm SEO (SEO đọc gemini_result.docx hỏng
    # ra tiêu đề rác — tập 87 lên YouTube với tiêu đề "Hãy gửi nội dung truyện...").
    bad = gui.kiem_ban_dich_folder(folder)
    if bad:
        mota = ", ".join(f"đoạn {j} {ly_do}" for j, ly_do in bad)
        logging.error(f"⛔ Tập {episode}: bản dịch có đoạn hỏng ({mota}) → không làm "
                      "SEO, bỏ cả tập. Chạy lại bước dịch Gemini trước.")
        return STOP
    import seo_youtube_gemini as seo
    import dich_gemini as g

    gemini_docx = folder / "gemini_result.docx"
    seo_docx = folder / "seoYoutube.docx"
    if not gemini_docx.exists():
        logging.error("❌ Chưa có gemini_result.docx → chưa tạo được SEO.")
        return ERROR

    if app._seo_docx_valid(seo_docx) and not state.get("force"):
        logging.info("♻ Bỏ qua SEO (đã có seoYoutube.docx hợp lệ).")
    else:
        try:
            driver = state.get("driver")
            if driver is None:
                logging.info(f"🌐 Mở {g.browser_label()} cho SEO...")
                driver = g.init_firefox(on_log=logging.info)
                state["driver"] = driver
            logging.info("🔎 Tạo SEO YouTube...")
            seo.run(str(gemini_docx), str(seo_docx), keep_open=True,
                    log=logging.info, driver=driver)
        except Exception as e:      # trình duyệt/Gemini hỏng = SEO hỏng, không phải lỗi tập
            logging.error(f"❌ Lỗi khi làm SEO: {e}")
        if not app._seo_docx_valid(seo_docx):
            return _seo_hong(episode, "không có SEO hợp lệ")
        logging.info(f"💾 Đã tạo: {seo_docx}")

    # Nội dung 3 nút Copy — luôn dựng lại (nhẹ) để áp logic cắt thẻ tag mới nhất.
    app._save_youtube_seo_copy(seo_docx, folder / "youtube_seo.txt", episode)

    # Chốt sớm chống SEO lấy nhầm kết quả của tập khác. Bắt ở ĐÂY chứ không đợi tới
    # lúc đăng: thumbnail và tên file video dọc đều lấy tiêu đề từ SEO, sai từ đây
    # là hỏng cả mẻ dựng. Bản SEO nghi sai được CẤT sang tên khác (không xoá) để lần
    # chạy sau tự làm SEO mới.
    blocks = app._seo_copy_blocks(seo_docx, episode) or {}
    trung = app._seo_title_duplicate(folder, episode, blocks.get("title") or "")
    if trung:
        logging.error(f"⛔ Tập {episode}: tiêu đề SEO trùng — {trung}. Gần như chắc "
                      "chắn Gemini trả về kết quả của tập khác → bỏ bản SEO này "
                      "(chạy lại để làm SEO mới).")
        try:
            parked = seo.park_docx(seo_docx)
            if parked:
                logging.info(f"📦 Đã cất bản SEO nghi sai → {parked.name}")
        except Exception as e:
            logging.warning(f"⚠️ Không cất được {seo_docx.name}: {e}")
        return _seo_hong(episode, "tiêu đề SEO trùng tập khác")
    return 0


def _seo_hong(episode: str, why: str) -> int:
    logging.warning(f"⚠️ Tập {episode}: {why} → VẪN CHẠY TIẾP (bỏ thumbnail, vẫn tạo giọng + "
                    "video ngang). Chưa có SEO thì KHÔNG tự đăng YouTube / không lên lịch "
                    "Facebook.")
    return SEO_SOFT


def step_thumbnail(app, folder: Path, episode: str, state: dict) -> int:
    ngang = folder / f"thumbnail{episode}.png"
    doc = folder / f"thumbnail{episode}_dọc.png"
    if ngang.exists() and doc.exists() and not state.get("force"):
        logging.info("♻ Bỏ qua thumbnail (đã có cả ngang & dọc).")
        return 0
    if not app._seo_docx_valid(folder / "seoYoutube.docx"):
        logging.warning("⚠️ Chưa có SEO hợp lệ → bỏ qua thumbnail (tiêu đề thumbnail lấy "
                        "từ SEO).")
        return SEO_SOFT
    if not app._make_thumbnail_for_folder(folder, episode):
        logging.error("❌ Không tạo được thumbnail.")
        return ERROR
    try:
        gui.save_episode_number(max(gui.load_episode_number(), int(episode)))
    except Exception:
        pass
    return 0


def step_tts(app, folder: Path, episode: str, state: dict, source: str = "") -> int:
    ts = state.get("tts")
    if not ts:
        logging.error("❌ Thiếu cài đặt tạo giọng (--tts-json).")
        return ERROR
    if ts.get("ngang_tu_nguon") and ts.get("make_video") and source:
        # 🎞 Video tải xuống làm nguồn hình (24/10/2026): nguồn của tập biết ngay tại
        # đây (--source) → đưa thẳng đường dẫn cho run_tts. Không có video (link
        # yt-dlp chỉ mp3, file chưa tải) → báo rồi run_tts ghép clip như cũ. Tiếng
        # gốc KHÔNG đụng tới file tải về: nhận diện + dịch đã dùng xong trước đó.
        nguon, ly_do = gui.nguon_video_path(source)
        if nguon:
            ts = dict(ts, ngang_source_video=str(nguon))
            logging.info(f"🎞 Video nguồn cho video ngang: {nguon}")
        else:
            logging.warning(f"⚠️ Không có video nguồn ({ly_do}) → video ngang ghép clip như cũ.")
    marker = folder / core.DOC_CHO_SEO
    seo_ok = app._seo_docx_valid(folder / "seoYoutube.docx")
    hoan = []                     # phần để dành tới khi có SEO
    if not seo_ok:
        # Khung dọc in tiêu đề SEO lên hình + lấy thumbnail dọc làm ảnh bìa, TikTok/
        # Short cắt từ chính bản dọc đó → không có SEO thì để dành, khỏi dựng bản tạm.
        hoan = [k for k in ("make_video_doc", "make_tiktok", "make_short", "make_sub_doc")
                if ts.get(k)]
        ts = dict(ts, make_video_doc=False, make_tiktok=False, make_short=False,
                  make_sub_doc=False)
        if hoan:
            logging.warning("⚠️ Chưa có SEO → chỉ tạo giọng + video ngang; video dọc/"
                            "TikTok/Short (in tiêu đề SEO) để dành tới khi có SEO.")
    _close_driver(state)          # nhả RAM Firefox trước khi render video
    if not app._batch_run_tts(folder, ts, episode):
        logging.error("❌ Tạo giọng/video không hoàn tất.")
        return ERROR
    if not seo_ok:
        if hoan and not core._doc_video_exists(folder):
            try:
                marker.write_text(
                    "Giọng + video ngang dựng lúc CHƯA có SEO → video dọc/TikTok/Short còn "
                    "chờ. ⏩ Chạy tiếp sẽ làm SEO → thumbnail → dựng nốt rồi mới tự đăng.\n",
                    encoding="utf-8")
            except OSError as e:
                logging.warning(f"⚠️ Không ghi được {marker.name}: {e}")
        return SEO_SOFT
    # Đã dựng nốt phần chờ SEO (hoặc đang tắt video dọc) → bỏ dấu, ⏩ thôi chạy lại.
    if marker.exists() and (not ts.get("make_video_doc") or core._doc_video_exists(folder)):
        try:
            marker.unlink()
            logging.info("✅ Đã dựng nốt video dọc/TikTok/Short sau khi có SEO.")
        except OSError as e:
            logging.warning(f"⚠️ Không xoá được {marker.name}: {e}")
    return 0


def _close_driver(state: dict) -> None:
    driver = state.pop("driver", None)
    if driver is not None:
        try:
            driver.quit()
            logging.info("🌐 Đã kết thúc phiên Gemini.")
        except Exception:
            pass


# ── Điều phối ───────────────────────────────────────────────────────────────
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Chạy các bước của một tập (bản web).")
    parser.add_argument("--steps", required=True,
                        help="Danh sách bước, cách nhau bằng dấu phẩy. "
                             f"Bước: {', '.join(ALL_STEPS)}. Nhóm: script, all.")
    parser.add_argument("--source", default="", help="Link hoặc file gốc của tập.")
    parser.add_argument("--episode", default="", help="Số tập (bỏ trống = tự cấp).")
    parser.add_argument("--model", default="medium", help="Model Whisper cho bước nhận diện.")
    parser.add_argument("--speed", type=float, default=0.7, help="Tốc độ audio khi nhận diện.")
    parser.add_argument("--tts-json", default="", help="File JSON cài đặt tạo giọng/video.")
    parser.add_argument("--force", action="store_true",
                        help="Làm lại cả khi bước đó đã có kết quả.")
    parser.add_argument("--episode-out", default="",
                        help="Ghi SỐ TẬP đã cấp ra file này (để bên gọi nối việc "
                             "đăng YouTube — với nguồn là link thì số tập chỉ biết "
                             "được ở đây, lúc chạy).")
    parser.add_argument("--require", default="",
                        help="Các bước phải ĐÃ XONG trước khi chạy (vd translate,input), "
                             "thiếu thì dừng mã 77 — lượt 2 của ⏩ Chạy tiếp.")
    args = parser.parse_args(argv)

    _setup_logging()

    steps: list[str] = []
    for name in args.steps.split(","):
        name = name.strip()
        if not name:
            continue
        steps.extend(STEP_GROUPS.get(name, [name]))
    unknown = [s for s in steps if s not in ALL_STEPS]
    if unknown:
        logging.error(f"❌ Bước không hợp lệ: {', '.join(unknown)}")
        return ERROR

    app = HeadlessApp()
    try:
        folder, episode = _resolve_folder(app, args.source.strip(), args.episode.strip())
    except SystemExit as e:
        logging.error(f"❌ {e}")
        return ERROR
    logging.info(f"📂 Tập {episode} — {folder}")
    if args.episode_out:
        try:
            Path(args.episode_out).write_text(episode, encoding="utf-8")
        except OSError as e:
            logging.warning(f"⚠️ Không ghi được số tập ra {args.episode_out}: {e}")

    # Lượt 2 của ⏩ (04/10/2026): lượt 1 dừng ⛔ ở bước dịch/input (đoạn trống, tô đỏ
    # chưa kiểm…) thì tới đây vẫn chưa xong → không tạo giọng/video từ bản dịch dở,
    # y như chuỗi một-lần-gọi cũ dừng ngay ở bước dịch.
    need = [k.strip() for k in args.require.split(",") if k.strip()]
    if need:
        st = core.folder_steps(folder, episode)
        thieu = [k for k in need if not st.get(k)]
        if thieu:
            logging.error(f"⛔ Tập {episode}: chưa xong {', '.join(thieu)} (lượt trước dừng) "
                          f"→ không chạy {', '.join(steps)}.")
            return STOP

    state: dict = {"force": args.force}
    if args.tts_json:
        try:
            state["tts"] = json.loads(Path(args.tts_json).read_text(encoding="utf-8"))
        except Exception as e:
            logging.error(f"❌ Không đọc được cài đặt tạo giọng: {e}")
            return ERROR

    code = 0
    seo_hong = False
    if GIU_MAN_HINH.intersection(steps):
        logging.info("🖱 Dịch/SEO: nhích chuột đánh thức màn hình trước khi bắt đầu (máy rảnh "
                     f"lâu thì chờ {CHO_SANG} s cho sáng hẳn). "
                     f"Nhận diện/dịch/SEO: máy rảnh {NHICH_SAU // 60} phút thì tự nhích "
                     "chuột 1 px để màn hình không tắt.")
    try:
        for name in steps:
            logging.info(f"▶ Bước: {name}")
            # Dịch/SEO cần màn hình SÁNG HẲN trước khi gửi Gemini (chờ CHO_SANG giây nếu
            # máy đã rảnh lâu); nhận diện chỉ cần giữ màn hình, không cần chờ.
            with (giu_man_hinh(cho_sang=0 if name == "recognize" else CHO_SANG)
                  if name in GIU_MAN_HINH else contextlib.nullcontext()):
                if name == "tai":
                    code = step_tai(folder, episode, args.source.strip(), args.force)
                elif name == "recognize":
                    code = step_recognize(app, folder, episode, args.source.strip(),
                                          args.model, args.speed, args.force)
                elif name == "translate":
                    code = step_translate(app, folder, episode, state)
                elif name == "input":
                    code = step_input(app, folder, episode, state)
                elif name == "seo":
                    code = step_seo(app, folder, episode, state)
                elif name == "thumbnail":
                    code = step_thumbnail(app, folder, episode, state)
                elif name == "tts":
                    code = step_tts(app, folder, episode, state, args.source.strip())
            # Ghi tiến độ vào manifest sau MỖI bước: web tải lại trang là thấy ngay,
            # và lỡ mất điện giữa chừng vẫn biết tập này đã tới đâu.
            if args.source.strip():
                try:
                    app._manifest_update(args.source.strip(), episode, folder)
                except Exception as e:
                    logging.warning(f"⚠️ Không ghi được manifest: {e}")
            if code == SEO_SOFT:            # SEO hỏng: ghi nhớ rồi làm tiếp bước sau
                seo_hong, code = True, 0
            if code != 0:
                break
    except Exception as e:
        logging.error(f"❌ Lỗi: {e}")
        logging.error(traceback.format_exc())
        code = ERROR
    finally:
        _close_driver(state)

    if code == 0 and seo_hong:
        if "tts" in steps:
            # Mã DỪNG để hàng đợi web KHÔNG gọi on_success (nối việc đăng YouTube +
            # lên lịch Facebook) và việc hiện ⛔ cho dễ thấy.
            logging.error(f"⛔ Tập {episode}: đã tạo giọng + video ngang nhưng CHƯA có SEO "
                          "→ KHÔNG tự đăng YouTube, KHÔNG lên lịch Facebook. ⏩ Chạy tiếp sẽ "
                          "làm lại SEO → thumbnail → dựng nốt video dọc/TikTok/Short rồi "
                          "mới tự đăng.")
            return STOP
        logging.warning(f"⚠️ Tập {episode}: chưa có SEO — các bước khác đã chạy xong.")
        return SEO_SOFT
    if code == 0:
        logging.info(f"✅ Tập {episode}: xong {len(steps)} bước.")
    return code


if __name__ == "__main__":
    sys.exit(main())
