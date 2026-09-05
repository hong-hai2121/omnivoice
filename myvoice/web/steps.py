"""Dịch yêu cầu từ giao diện web thành các bước cho hàng đợi.

Mỗi bước là một lần gọi runners/run_episode.py. Các bước liên quan tới Firefox
(dịch → input → SEO → thumbnail) gộp làm MỘT để dùng chung một phiên trình duyệt;
nhận diện và tạo giọng tách riêng vì mỗi cái độc chiếm GPU một lúc lâu.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from . import core
from .jobs import Step, fb_runner, log, upload_runner

RUNNER = core.WEB_DIR / "runners" / "run_episode.py"
RUNNER_TTS = core.WEB_DIR / "runners" / "run_tts.py"
RUNNER_THUMB = core.WEB_DIR / "runners" / "run_thumbnail.py"
RUNNER_UPLOAD = core.WEB_DIR / "runners" / "run_upload.py"
# Lấp đoạn "(trống)" trong gemini_result.docx — script CLI có sẵn, không đi qua
# run_episode.py (nó không phải một bước của quy trình, chỉ là việc sửa tay có trợ giúp).
RETRANS_SCRIPT = core.SCRIPTS_DIR / "dich_lai_trong.py"
TMP_DIR = core.WEB_DIR / ".tmp"

# Mã "dừng có chủ ý" của runner — phải khớp STOP trong runners/run_episode.py.
# Không import từ đó được: module runner khởi tạo nặng (kéo cả amain_taogiong_gui),
# nó sinh ra để chạy làm tiến trình riêng chứ không phải để import.
STOP_CODE = 77

# Bước hiện trên giao diện → (nhãn, danh sách bước của runner)
STEP_CHOICES = [
    ("recognize", "① Nhận diện tiếng Trung"),
    ("script",    "② Dịch + input.txt + SEO + thumbnail"),
    ("tts",       "③ Tạo giọng + video"),
]
# Bước lẻ, dùng cho nút “chạy lại” của từng ô trong bảng tiến độ.
SINGLE_STEPS = {
    "recognize": "Nhận diện",
    "translate": "Dịch Gemini",
    "retranslate": "Dịch lại đoạn trống",
    "input":     "Tạo input.txt",
    "seo":       "SEO YouTube",
    "thumbnail": "Thumbnail",
    "tts":       "Tạo giọng + video",
    "upload":    "Đăng YouTube",
    "short":     "Đăng Short",
    "facebook":  "Lên lịch Facebook",
}


def _write_tts_json() -> tuple[str, str]:
    """Ghi cài đặt tạo giọng ra file tạm cho runner đọc. → (đường dẫn, lỗi)."""
    settings, err = core.tts_settings()
    if settings is None:
        return "", err
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    path = TMP_DIR / f"tts_{int(time.time() * 1000)}.json"
    path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path), ""


def _base_argv(step_names: str, source: str, episode: str, force: bool) -> list[str]:
    pipe = core.load_pipeline()
    argv = [core.python_exe(), "-u", str(RUNNER), "--steps", step_names,
            "--model", str(pipe.get("model", "medium")),
            "--speed", str(pipe.get("speed", "0.7"))]
    if source:
        argv += ["--source", source]
    if episode:
        argv += ["--episode", str(episode).zfill(2)]
    if force:
        argv.append("--force")
    return argv


def upload_steps(episode: str) -> list[Step]:
    """Bước ĐĂNG YouTube cho 1 tập (chạy ở hàng đợi riêng upload_runner)."""
    argv = [core.python_exe(), "-u", str(RUNNER_UPLOAD), "--episode", str(episode)]
    return [Step(label=f"Đăng YouTube tập {episode}", argv=argv,
                 cwd=str(core.SCRIPTS_DIR), env=core.subprocess_env(),
                 # STOP_CODE = bỏ qua có chủ ý (đã đăng rồi, kênh đã có tập này…).
                 soft_fail_codes=(STOP_CODE,))]


def retranslate_steps(episode: str, blanks: list[int] | None = None) -> list[Step]:
    """Bước 🔁 Dịch lại đoạn (Trống) cho 1 tập — chạy ở hàng đợi CHÍNH vì điều khiển
    Firefox (profile Gemini chỉ mở được một phiên, như bước dịch/SEO).

    Script gửi mỗi đoạn trống lên Gemini ĐÚNG MỘT LẦN rồi ghi vào gemini_result.docx
    để người dùng kiểm; còn đoạn trống thì trả STOP_CODE (dừng có chủ ý, không phải lỗi).
    """
    episode = str(episode).strip().zfill(2)
    argv = [core.python_exe(), "-u", str(RETRANS_SCRIPT), "--episode", episode]
    n = f" ({len(blanks)} đoạn: {', '.join(map(str, blanks))})" if blanks else ""
    return [Step(label=f"Dịch lại đoạn trống tập {episode}{n}", argv=argv,
                 cwd=str(core.SCRIPTS_DIR), env=core.subprocess_env(),
                 soft_fail_codes=(STOP_CODE,))]


def queue_upload(episode: str) -> None:
    """Xếp việc đăng 1 tập vào hàng đợi RIÊNG — trả về ngay, không chờ tải xong."""
    episode = str(episode).strip().zfill(2)
    upload_runner.enqueue(f"⬆ Đăng YouTube tập {episode}", upload_steps(episode))


def short_steps(episode: str) -> list[Step]:
    """Bước đăng RIÊNG Short (short.mp4) cho tập ĐÃ có video chính trên kênh mà bản
    ghi còn thiếu Short — run_upload.py --short tự kiểm bản ghi/kênh để không trùng."""
    argv = [core.python_exe(), "-u", str(RUNNER_UPLOAD), "--episode", str(episode), "--short"]
    return [Step(label=f"Đăng Short tập {episode}", argv=argv,
                 cwd=str(core.SCRIPTS_DIR), env=core.subprocess_env(),
                 soft_fail_codes=(STOP_CODE,))]


def queue_short(episode: str) -> None:
    """Xếp việc đăng Short của 1 tập vào hàng đợi đăng (cùng hàng với YouTube)."""
    episode = str(episode).strip().zfill(2)
    upload_runner.enqueue(f"⬆ Đăng Short tập {episode}", short_steps(episode))


# Kịch bản lên lịch Facebook — file độc lập, tự đọc token từ .env gốc repo.
FB_SCRIPT = core.WEB_DIR.parent / "FACEBOOK" / "dang_video_facebook.py"


def facebook_steps(dry_run: bool = False, limit: int = 0, only_scan: bool = False,
                   episodes: list[str] | None = None) -> list[Step]:
    """Bước LÊN LỊCH Facebook (Page MimiAudio) — chạy ở hàng đợi ĐĂNG, vì cũng
    chỉ tốn băng thông như đăng YouTube.

    only_scan: chỉ ĐỌC Page (bài đã đăng · lịch đang chờ · bài đã xếp còn sống
    không) rồi ghi page_cache.json + sổ da_dang.json — khối trên trang dựng danh
    sách "tập chưa đăng" và bảng lịch từ hai file đó, khỏi gọi mạng mỗi lần mở
    trang.
    Không dry_run thì truyền --yes: tiến trình con không có bàn phím
    (stdin=DEVNULL), mà người dùng bấm nút trên web là đã xác nhận rồi."""
    argv = [core.python_exe(), "-u", str(FB_SCRIPT)]
    if only_scan:
        argv.append("--sync")
        label = "🔄 Cập nhật lịch Page Facebook"
    elif dry_run:
        argv.append("--dry-run")
        label = "📘 Xem kế hoạch Facebook (không đăng)"
    else:
        argv.append("--yes")
        label = "📘 Lên lịch Facebook 9h/19h"
    if episodes:
        argv += ["--tap", ",".join(episodes)]
    if limit > 0 and not only_scan:
        argv += ["--limit", str(limit)]
    return [Step(label=label, argv=argv, cwd=str(core.SCRIPTS_DIR),
                 env=core.subprocess_env())]


def queue_facebook(episode: str) -> None:
    """Xếp việc lên lịch Facebook cho 1 tập vào hàng đợi RIÊNG của Facebook.

    Hàng riêng (fb_runner) chứ không dùng chung với hàng đợi đăng YouTube: hai
    việc này chạy SONG SONG, tập vừa dựng xong thì vừa đẩy lên YouTube vừa xếp
    lịch Page, không ai đợi ai — mà hàng đợi chính cũng đi tiếp tập sau ngay.
    """
    episode = str(episode).strip().zfill(2)
    fb_runner.enqueue(f"📘 Lên lịch Facebook tập {episode}",
                      facebook_steps(episodes=[episode]))


def queue_after_build(episode: str, upload: bool) -> None:
    """Dựng xong video một tập → xếp các việc ĐĂNG chạy song song.

    `upload` là ô "⬆ tự động đăng" của khối YouTube (chốt lúc bấm chạy), còn
    Facebook đọc cài đặt NGAY LÚC NÀY: mẻ chạy hàng giờ, đổi ý giữa chừng thì lần
    tới có hiệu lực luôn, khỏi phải dừng cả mẻ.
    """
    if upload:
        queue_upload(episode)
    if core.facebook_auto():
        queue_facebook(episode)


def _queue_after_build_from_file(ep_file: Path, upload: bool) -> None:
    """Đọc số tập mà runner vừa ghi ra rồi xếp các việc đăng.

    Phải đi qua file vì với nguồn là link/file, SỐ TẬP do chính runner cấp lúc chạy
    (theo manifest) — lúc dựng danh sách bước ở đây thì chưa ai biết là tập mấy.
    """
    if not upload and not core.facebook_auto():
        return                      # không bật tự đăng ở đâu cả → khỏi đọc file
    try:
        episode = ep_file.read_text(encoding="utf-8").strip()
    except OSError:
        episode = ""
    if not episode:
        log("⚠️ Không rõ vừa dựng xong tập nào → chưa xếp được việc đăng.")
        return
    queue_after_build(episode, upload)


def build_steps(step_keys: list[str], source: str = "", episode: str = "",
                force: bool = False, upload: bool = False) -> tuple[list[Step], str]:
    """→ (danh sách Step, lỗi). Lỗi khác rỗng nghĩa là chưa chạy được.

    upload=True: dựng xong video thì XẾP việc đăng sang hàng đợi riêng rồi đi tiếp
    ngay — tập kế không phải đợi video này tải lên xong.
    """
    steps: list[Step] = []
    env = core.subprocess_env()
    cwd = str(core.SCRIPTS_DIR)

    for key in step_keys:
        # "upload" chạy runner KHÁC (run_upload.py), không phải run_episode.py.
        # Thường thì bên gọi xếp thẳng vào upload_runner cho chạy song song; nhánh
        # này để build_steps(["upload"]) vẫn ra đúng bước chứ không tạo lệnh sai.
        if key == "upload":
            if not episode:
                return [], "Bước đăng YouTube cần biết số tập."
            steps.extend(upload_steps(episode))
            continue
        label = dict(STEP_CHOICES).get(key) or SINGLE_STEPS.get(key, key)
        argv = _base_argv(key, source, episode, force)
        on_success = None
        if key in ("tts", "all"):
            tts_json, err = _write_tts_json()
            if err:
                return [], err
            argv += ["--tts-json", tts_json]
            # Luôn xin runner ghi ra SỐ TẬP và luôn gắn callback, kể cả khi ô
            # "⬆ tự động đăng" đang tắt: ô 📘 Facebook có thể đang bật (hai chế độ
            # độc lập), mà callback mới là chỗ đọc lại cài đặt lúc chạy.
            TMP_DIR.mkdir(parents=True, exist_ok=True)
            ep_file = TMP_DIR / f"ep_{int(time.time() * 1000)}.txt"
            argv += ["--episode-out", str(ep_file)]
            on_success = lambda f=ep_file, u=upload: _queue_after_build_from_file(f, u)   # noqa: E731
        steps.append(Step(label=label, argv=argv, cwd=cwd, env=env,
                          # runner trả STOP_CODE khi CHỦ ĐỘNG dừng (vd dịch còn thiếu
                          # đoạn): kết quả hợp lệ của một chốt an toàn, không phải sự cố.
                          soft_fail_codes=(STOP_CODE,), on_success=on_success))
    return steps, ""


def resume_steps(missing: list[str], source: str, episode: str,
                 upload: bool = False) -> tuple[list[Step], str]:
    """MỘT bước chạy LIỀN MẠCH các bước còn thiếu của một tập → (Step, lỗi).

    Gộp cả chuỗi vào một lần gọi runner (--steps "a,b,c") thay vì mỗi bước một
    tiến trình: dịch → SEO dùng chung một phiên Firefox (mở hai lần thì phiên sau
    vấp profile đang khoá), và tập chạy trọn vẹn không bị việc khác chen ngang.
    """
    # Bước đăng lẻ (Short / Facebook) không phải việc của run_episode.py — bên gọi
    # (_run_resume) xếp chúng vào hàng đợi đăng; lọc ở đây để không tạo lệnh sai.
    missing = [k for k in missing if k not in core.POST_STEPS]
    if not missing:
        return [], f"Tập {episode}: không còn bước nào thiếu."
    argv = _base_argv(",".join(missing), source, episode, force=False)
    on_success = None
    if "tts" in missing:
        tts_json, err = _write_tts_json()
        if err:
            return [], err
        argv += ["--tts-json", tts_json]
        # Số tập đã biết sẵn (chạy tiếp thư mục có rồi) → nối thẳng việc đăng,
        # không cần đi vòng qua file --episode-out như lúc nguồn là link mới.
        on_success = lambda ep=episode, u=upload: queue_after_build(ep, u)   # noqa: E731
    label = "⏩ " + " → ".join(SINGLE_STEPS.get(k, k) for k in missing)
    return [Step(label=label, argv=argv, cwd=str(core.SCRIPTS_DIR),
                 env=core.subprocess_env(), soft_fail_codes=(STOP_CODE,),
                 on_success=on_success)], ""


def tts_steps(input_txt: str = "", output_wav: str = "", from_gemini: bool = False,
              reuse: bool = False, rebuild: str = "", episode: str = "") -> tuple[list[Step], str]:
    """Bước cho trang “Giọng nói”: chạy TTS thủ công hoặc dựng lại một loại video."""
    tts_json, err = _write_tts_json()
    if err:
        return [], err
    argv = [core.python_exe(), "-u", str(RUNNER_TTS), "--tts-json", tts_json]
    if input_txt:
        argv += ["--input", input_txt]
    if output_wav:
        argv += ["--output", output_wav]
    if from_gemini:
        argv.append("--from-gemini")
    if reuse:
        argv.append("--reuse")
    if rebuild:
        argv += ["--rebuild", rebuild]
    if episode:
        argv += ["--episode", str(episode)]
    label = {"ngang": "Dựng lại video ngang", "doc": "Dựng lại video dọc",
             "tiktok": "Dựng lại video TikTok"}.get(rebuild, "Tạo giọng + video")
    return [Step(label=label, argv=argv, cwd=str(core.SCRIPTS_DIR),
                 env=core.subprocess_env(), soft_fail_codes=(STOP_CODE,))], ""


def thumbnail_steps(title: str, episode: str = "", photo: str = "",
                    doc: bool = True) -> list[Step]:
    """Bước cho trang “Thumbnail”: tạo ảnh từ tiêu đề tự nhập."""
    argv = [core.python_exe(), "-u", str(RUNNER_THUMB), "--title", title]
    if episode:
        argv += ["--episode", str(episode)]
    if photo:
        argv += ["--photo", photo]
    if doc:
        argv.append("--doc")
    return [Step(label="Tạo thumbnail", argv=argv, cwd=str(core.SCRIPTS_DIR),
                 env=core.subprocess_env())]


def title_for(source: str, episode: str, step_keys: list[str]) -> str:
    who = f"Tập {str(episode).zfill(2)}" if episode else (source[:60] or "Tập mới")
    what = " · ".join(SINGLE_STEPS.get(k, dict(STEP_CHOICES).get(k, k)) for k in step_keys)
    return f"{who} — {what}"


def cleanup_tmp(keep_hours: int = 24) -> None:
    """Dọn file cài đặt tạm cũ (mỗi lần chạy tạo một file nhỏ)."""
    if not TMP_DIR.exists():
        return
    cutoff = time.time() - keep_hours * 3600
    for pattern in ("tts_*.json", "ep_*.txt"):
        for p in TMP_DIR.glob(pattern):
            try:
                if p.stat().st_mtime < cutoff:
                    p.unlink()
            except OSError:
                pass
