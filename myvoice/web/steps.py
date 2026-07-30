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
from .jobs import Step

RUNNER = core.WEB_DIR / "runners" / "run_episode.py"
TMP_DIR = core.WEB_DIR / ".tmp"

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
    "input":     "Tạo input.txt",
    "seo":       "SEO YouTube",
    "thumbnail": "Thumbnail",
    "tts":       "Tạo giọng + video",
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


def build_steps(step_keys: list[str], source: str = "", episode: str = "",
                force: bool = False) -> tuple[list[Step], str]:
    """→ (danh sách Step, lỗi). Lỗi khác rỗng nghĩa là chưa chạy được."""
    steps: list[Step] = []
    env = core.subprocess_env()
    cwd = str(core.SCRIPTS_DIR)

    for key in step_keys:
        label = dict(STEP_CHOICES).get(key) or SINGLE_STEPS.get(key, key)
        argv = _base_argv(key, source, episode, force)
        if key in ("tts", "all"):
            tts_json, err = _write_tts_json()
            if err:
                return [], err
            argv += ["--tts-json", tts_json]
        steps.append(Step(label=label, argv=argv, cwd=cwd, env=env,
                          # runner trả 1 khi CHỦ ĐỘNG dừng (vd dịch còn thiếu đoạn):
                          # đó là kết quả hợp lệ của một chốt an toàn, không phải sự cố.
                          soft_fail_codes=(1,)))
    return steps, ""


def title_for(source: str, episode: str, step_keys: list[str]) -> str:
    who = f"Tập {str(episode).zfill(2)}" if episode else (source[:60] or "Tập mới")
    what = " · ".join(SINGLE_STEPS.get(k, dict(STEP_CHOICES).get(k, k)) for k in step_keys)
    return f"{who} — {what}"


def cleanup_tmp(keep_hours: int = 24) -> None:
    """Dọn file cài đặt tạm cũ (mỗi lần chạy tạo một file nhỏ)."""
    if not TMP_DIR.exists():
        return
    cutoff = time.time() - keep_hours * 3600
    for p in TMP_DIR.glob("tts_*.json"):
        try:
            if p.stat().st_mtime < cutoff:
                p.unlink()
        except OSError:
            pass
