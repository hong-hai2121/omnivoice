"""Tạo giọng cho một file văn bản bất kỳ — bản web của nút “▶ Chạy” và ba nút
“▶ Dựng lại” bên GUI.

Khác run_episode.py ở chỗ không gắn với thư mục tập: nhận thẳng input.txt và
output.wav, đúng như tab “Giọng nói”. Vẫn gọi cùng một hàm `run_tts` của
amain_taogiong_gui nên kết quả không lệch với GUI.

    python run_tts.py --tts-json cfg.json [--input in.txt] [--output out.wav]
                      [--from-gemini] [--reuse] [--rebuild ngang|doc|tiktok]
                      [--episode 07]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
import traceback
from pathlib import Path

_WEB_DIR = Path(__file__).resolve().parent.parent
_BASE_DIR = _WEB_DIR.parent
for _p in (str(_BASE_DIR.parent), str(_BASE_DIR / "scripts"), str(_BASE_DIR / "YOUTUBE"),
           str(_BASE_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import amain_taogiong_gui as gui                       # noqa: E402
from run_episode import _Var, HeadlessApp, _setup_logging, STOP   # noqa: E402

ERROR = 2


def _effect_path(ts: dict):
    name = (ts.get("effect") or "").strip()
    if not name:
        return None
    p = Path(name)
    return str(p) if p.is_absolute() or p.exists() else None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Tạo giọng / dựng lại video (bản web).")
    parser.add_argument("--tts-json", required=True, help="File JSON cài đặt.")
    parser.add_argument("--input", default="", help="File văn bản .txt.")
    parser.add_argument("--output", default="", help="File kết quả .wav.")
    parser.add_argument("--from-gemini", action="store_true",
                        help="Lấy nội dung từ gemini_result.docx + kiểm tra trước.")
    parser.add_argument("--reuse", action="store_true",
                        help="Dùng lại audio/video đã có, chỉ làm phần còn thiếu.")
    parser.add_argument("--rebuild", choices=["ngang", "doc", "tiktok"], default="",
                        help="Chỉ dựng lại một loại video từ audio có sẵn.")
    parser.add_argument("--episode", default="", help="Số tập (chữ trên video TikTok).")
    args = parser.parse_args(argv)

    _setup_logging()
    try:
        ts = json.loads(Path(args.tts_json).read_text(encoding="utf-8"))
    except Exception as e:
        logging.error(f"❌ Không đọc được cài đặt: {e}")
        return ERROR

    output = Path(args.output or (gui.OUTPUT_DIR / "output.wav"))
    input_txt = Path(args.input or (gui.SCRIPT_DIR / "input.txt"))
    output.parent.mkdir(parents=True, exist_ok=True)

    # ⛔ CHỐT ĐOẠN HỎNG (giống _batch_run_tts bên GUI): bản dịch của thư mục tập
    # còn đoạn chưa dịch / bị Gemini từ chối / dịch cụt → KHÔNG tạo giọng, KHÔNG
    # dựng video (kể cả --rebuild) — input/audio hiện có sinh từ bản dịch hỏng.
    # Thư mục không phải tập (không có tiengTrung/gemini docx) → không chặn.
    bad = gui.kiem_ban_dich_folder(output.parent)
    if bad:
        mota = ", ".join(f"đoạn {j} {ly_do}" for j, ly_do in bad)
        logging.error(f"⛔ {output.parent.name}: bản dịch có đoạn hỏng ({mota}) → "
                      "KHÔNG tạo giọng/dựng video. Chạy lại bước dịch Gemini trước.")
        return ERROR

    app = HeadlessApp()
    progress, status = _Var(0), _Var("")
    stub = gui._NullWidget()
    pause = threading.Event()
    pause.set()

    effect = _effect_path(ts)
    ep = str(args.episode).strip()
    # Chữ TikTok luôn ghi, giống nút “Dựng lại” bên GUI (kể cả khi số tập trống).
    caption = f"Mimi audio Số {ep.zfill(2)}" if ep else None
    out_dir = output.parent
    common = dict(
        effect=effect,
        ngang_speed=ts.get("ngang_speed", 1.0), ngang_source=ts.get("ngang_source"),
        ngang_out=out_dir / "YOUTUBE.mp4",
        doc_speed=ts.get("doc_speed", 1.0), doc_percent=ts.get("doc_percent", 100),
        doc_from_ngang=ts.get("doc_from_ngang", False),
        doc_from_subfolder=ts.get("doc_from_subfolder", False),
        doc_no_effect=ts.get("doc_no_effect", False), doc_out=out_dir / "facebook.mp4",
        tiktok_out=out_dir / "tiktok.mp4",
        short_out=out_dir / "short.mp4",
        tiktok_speed=ts.get("tiktok_speed", 1.0),
        tiktok_percent=ts.get("tiktok_percent", 50),
        tiktok_no_effect=ts.get("tiktok_no_effect", False),
        tiktok_caption=caption, tiktok_caption_pos=ts.get("tiktok_caption_pos", 40),
        tiktok_music=ts.get("tiktok_music", False),
        tiktok_music_db=ts.get("tiktok_music_db", -12),
        tiktok_music_loop=ts.get("tiktok_music_loop", False),
        sub_mode=ts.get("sub_mode", gui.SUB_MODE_SRT),
        sub_model=ts.get("sub_model", "large-v3-turbo"),
        sub_max_chars=ts.get("sub_max_chars", 50),
        sub_kieu=ts.get("sub_kieu", "hopbo"),
        sub_font=ts.get("sub_font", ""),
        sub_mau=ts.get("sub_mau", ""),
        sub_mau_vien=ts.get("sub_mau_vien", ""),
        sub_vitri=ts.get("sub_vitri", ""),
        sub_cochu=ts.get("sub_cochu", ""),
        sub_bengang=ts.get("sub_bengang", ""),
        sub_dong=ts.get("sub_dong", 2),
    )

    try:
        if args.rebuild:
            kind = args.rebuild
            if not (output.exists() and output.stat().st_size > 4096):
                logging.error(f"❌ Chưa có audio để dựng video: {output}")
                return ERROR
            logging.info(f"🎬 Dựng lại video {kind} từ {output.name} (không chạy lại TTS).")
            gui.run_tts(
                "", None, [], str(output), progress, status, stub, stub, stub, pause,
                video_only=True, reuse=True,
                make_video=(kind == "ngang"),
                make_video_doc=(kind == "doc"),
                make_tiktok=(kind == "tiktok"),
                # Dựng lại TikTok là short cũ lệch theo → cắt lại cho khớp.
                make_short=(kind == "tiktok" and ts.get("make_short", False)),
                # Mỗi nút "Dựng lại" chỉ làm phụ đề cho chính khung của nó, y như
                # GUI: ngang → phụ đề ngang, dọc → phụ đề khung dọc. TikTok cố ý
                # KHÔNG có (nó mượn hình của facebook.mp4 nhưng audio ngắn hơn).
                make_sub=(kind == "ngang" and ts.get("make_sub", False)),
                make_sub_doc=(kind == "doc" and ts.get("make_sub_doc", False)),
                **common)
        else:
            if args.from_gemini and not app._prepare_input_from_gemini():
                logging.error("⛔ Nội dung từ Gemini chưa đạt → không tạo audio.")
                return STOP
            if not input_txt.exists():
                logging.error(f"❌ Không thấy file văn bản: {input_txt}")
                return ERROR
            text = gui.clean_text(input_txt.read_text(encoding="utf-8"))
            chunks = gui.split_chunks(text.lower(), int(ts.get("chunk", 300)))
            if not chunks:
                logging.error(f"❌ File văn bản rỗng: {input_txt}")
                return ERROR
            logging.info(f"🎧 Tạo giọng {len(chunks)} đoạn → {output}")
            gui.run_tts(
                ts.get("mode", "clone"), ts.get("voice_param"), chunks, str(output),
                progress, status, stub, stub, stub, pause,
                reuse=args.reuse,
                make_video=ts.get("make_video", False),
                make_video_doc=ts.get("make_video_doc", False),
                make_tiktok=ts.get("make_tiktok", False),
                make_short=ts.get("make_short", False),
                make_sub=ts.get("make_sub", False),
                make_sub_doc=ts.get("make_sub_doc", False),
                **common)
        if status.get():
            logging.info(status.get())
        logging.info("✅ Xong.")
        return 0
    except Exception as e:
        logging.error(f"❌ Lỗi: {e}")
        logging.error(traceback.format_exc())
        return ERROR


if __name__ == "__main__":
    sys.exit(main())
