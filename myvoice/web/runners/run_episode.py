"""Chạy các bước của MỘT tập — runner cho bảng điều khiển web.

Web không tự viết lại quy trình: nó tạo một App “rỗng” (không dựng cửa sổ Tk) rồi
gọi thẳng các method thuần logic của amain_taogiong_gui — cùng các chốt an toàn mà
GUI dùng (dịch thiếu đoạn thì KHÔNG ghi input.txt, không tạo audio/video…). Sửa
chốt ở scripts/ là web hưởng ngay, khỏi lo hai bản lệch nhau.

Cách gọi (jobs.py lo phần này):
    python run_episode.py --steps translate,input,seo,thumbnail \
        --source "<link|file>" [--episode 07] [--model medium] [--speed 0.7] \
        [--tts-json <file>] [--force]

Mã thoát: 0 = xong · 77 = dừng có chủ ý (bước chặn, vd dịch chưa đủ) · 2 = lỗi.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import traceback
from pathlib import Path

_WEB_DIR = Path(__file__).resolve().parent.parent
_BASE_DIR = _WEB_DIR.parent                     # myvoice/
for _p in (str(_BASE_DIR.parent), str(_BASE_DIR / "scripts"), str(_BASE_DIR / "YOUTUBE"),
           str(_BASE_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import amain_taogiong_gui as gui                # noqa: E402

# KHÔNG dùng 1 cho "dừng có chủ ý": Python thoát mã 1 khi crash trước khi vào
# main() (vd lỗi import) — dùng chung số là nhầm crash thành chốt an toàn.
# Đổi số này thì đổi cả STOP_CODE trong web/steps.py.
STOP = 77       # dừng có chủ ý — không phải sự cố
ERROR = 2

ALL_STEPS = ["recognize", "translate", "input", "seo", "thumbnail", "tts"]
# Gộp "script" thành một bước lớn để dịch → SEO dùng CHUNG một phiên Firefox
# (mở hai lần thì phiên sau vấp profile đang bị khoá).
STEP_GROUPS = {"script": ["translate", "input", "seo", "thumbnail"],
               "all": ALL_STEPS}


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
def step_recognize(app, folder: Path, episode: str, source: str,
                   model: str, speed: float, force: bool) -> int:
    import nhandien_giongnoi as recog

    existing = gui.find_zh_docx(folder)
    if existing and gui.read_zh_docx_chunks(existing) and not force:
        logging.info(f"♻ Bỏ qua nhận diện (đã có {existing.name}).")
        return 0
    if not source:
        logging.error("❌ Không có nguồn (link/file) để nhận diện.")
        return ERROR

    src = source.strip().strip('"').strip("'")
    if os.path.isfile(src):
        media = src
        logging.info(f"📁 File local: {media}")
    elif src.lower().startswith(("http://", "https://")):
        logging.info(f"🌐 Tải audio từ link: {src}")
        media = gui.download_audio_mp3(src, gui.DOWNLOAD_DIR)
        if not media:
            logging.error("❌ Không tải được audio từ link.")
            return ERROR
    else:
        logging.error(f"❌ Nguồn không hợp lệ (không phải file cũng không phải link): {src}")
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
    input_txt = folder / "input.txt"
    if not gemini_docx.exists():
        logging.error("❌ Chưa có gemini_result.docx → chưa tạo được input.txt.")
        return ERROR
    # Vừa dịch xong thì LUÔN ghi lại: bản input cũ có thể được tạo từ bản dịch dở.
    if (not state.get("translated_now") and input_txt.exists()
            and input_txt.stat().st_size > 0 and not state.get("force")):
        logging.info("♻ Bỏ qua tạo input.txt (đã có).")
        return 0
    if not app._batch_prepare_input(gemini_docx, input_txt):
        logging.error("⛔ Không ghi input.txt (xem lý do ở trên) → dừng tập này.")
        return STOP
    logging.info(f"💾 Đã tạo: {input_txt}")
    return 0


def step_seo(app, folder: Path, episode: str, state: dict) -> int:
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
        driver = state.get("driver")
        if driver is None:
            logging.info("🌐 Mở Firefox cho SEO...")
            driver = g.init_firefox()
            state["driver"] = driver
        logging.info("🔎 Tạo SEO YouTube...")
        seo.run(str(gemini_docx), str(seo_docx), keep_open=True,
                log=logging.info, driver=driver)
        logging.info(f"💾 Đã tạo: {seo_docx}")

    # Nội dung 3 nút Copy — luôn dựng lại (nhẹ) để áp logic cắt thẻ tag mới nhất.
    app._save_youtube_seo_copy(seo_docx, folder / "youtube_seo.txt", episode)
    return 0


def step_thumbnail(app, folder: Path, episode: str, state: dict) -> int:
    ngang = folder / f"thumbnail{episode}.png"
    doc = folder / f"thumbnail{episode}_dọc.png"
    if ngang.exists() and doc.exists() and not state.get("force"):
        logging.info("♻ Bỏ qua thumbnail (đã có cả ngang & dọc).")
        return 0
    if not app._make_thumbnail_for_folder(folder, episode):
        logging.error("❌ Không tạo được thumbnail.")
        return ERROR
    try:
        gui.save_episode_number(max(gui.load_episode_number(), int(episode)))
    except Exception:
        pass
    return 0


def step_tts(app, folder: Path, episode: str, state: dict) -> int:
    ts = state.get("tts")
    if not ts:
        logging.error("❌ Thiếu cài đặt tạo giọng (--tts-json).")
        return ERROR
    _close_driver(state)          # nhả RAM Firefox trước khi render video
    if not app._batch_run_tts(folder, ts, episode):
        logging.error("❌ Tạo giọng/video không hoàn tất.")
        return ERROR
    return 0


def _close_driver(state: dict) -> None:
    driver = state.pop("driver", None)
    if driver is not None:
        try:
            driver.quit()
            logging.info("🦊 Đã đóng Firefox.")
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

    state: dict = {"force": args.force}
    if args.tts_json:
        try:
            state["tts"] = json.loads(Path(args.tts_json).read_text(encoding="utf-8"))
        except Exception as e:
            logging.error(f"❌ Không đọc được cài đặt tạo giọng: {e}")
            return ERROR

    code = 0
    try:
        for name in steps:
            logging.info(f"▶ Bước: {name}")
            if name == "recognize":
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
                code = step_tts(app, folder, episode, state)
            # Ghi tiến độ vào manifest sau MỖI bước: web tải lại trang là thấy ngay,
            # và lỡ mất điện giữa chừng vẫn biết tập này đã tới đâu.
            if args.source.strip():
                try:
                    app._manifest_update(args.source.strip(), episode, folder)
                except Exception as e:
                    logging.warning(f"⚠️ Không ghi được manifest: {e}")
            if code != 0:
                break
    except Exception as e:
        logging.error(f"❌ Lỗi: {e}")
        logging.error(traceback.format_exc())
        code = ERROR
    finally:
        _close_driver(state)

    if code == 0:
        logging.info(f"✅ Tập {episode}: xong {len(steps)} bước.")
    return code


if __name__ == "__main__":
    sys.exit(main())
