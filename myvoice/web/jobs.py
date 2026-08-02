"""Hàng đợi công việc cho bản web — MỘT worker duy nhất.

Vì sao chỉ một: mọi bước nặng đều tranh nhau tài nguyên độc quyền — GPU (Whisper,
OmniVoice), profile Firefox (Gemini/SEO chỉ mở được một phiên), ffmpeg ăn hết CPU.
Chạy song song không nhanh hơn mà chỉ gây tranh chấp, nên các việc xếp hàng và
chạy lần lượt, đúng như GUI vẫn làm.

Mỗi bước là một tiến trình con (runner trong web/runners hoặc script CLI có sẵn).
Nhờ vậy server nhẹ, bước treo thì kill được, và bước nào crash cũng không kéo sập
bảng điều khiển.
"""

from __future__ import annotations

import itertools
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

CREATE_NO_WINDOW = 0x08000000

# ── Nhật ký: in thẳng ra cửa sổ console của server ──────────────────────────
# Trang web không còn panel nhật ký; chỗ xem tiến trình chi tiết là cửa sổ
# console đã mở sẵn khi bật server (chay_web.bat / nút 🌐 Bảng web của GUI).
_print_lock = threading.Lock()

try:        # console Windows thường là cp1252 → emoji/tiếng Việt sẽ nổ khi in
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # type: ignore[union-attr]
except Exception:
    pass


def log(text: str) -> None:
    with _print_lock:                       # nhiều luồng cùng in → khỏi lẫn dòng
        for line in str(text).splitlines() or [""]:
            try:
                print(line, flush=True)
            except Exception:               # không có console (pythonw) → bỏ qua
                return


# ── Mô tả công việc ─────────────────────────────────────────────────────────
@dataclass
class Step:
    label: str
    argv: list[str]
    cwd: str | None = None
    env: dict | None = None
    # Mã thoát được coi là "bỏ qua có chủ ý" chứ không phải lỗi (vd bước chuẩn bị
    # input.txt trả mã dừng khi bản dịch còn thiếu đoạn → dừng tập này, không phải hỏng).
    soft_fail_codes: tuple[int, ...] = ()
    # Gọi sau khi bước này CHẠY XONG KHÔNG LỖI. Dùng để nối việc sang hàng đợi khác
    # (dựng video xong → xếp việc đăng YouTube vào upload_runner) mà không bắt hàng
    # đợi chính đứng chờ. Lỗi trong callback không được làm hỏng công việc.
    on_success: Callable[[], None] | None = None


@dataclass
class Job:
    id: int
    title: str
    steps: list[Step]
    status: str = "queued"        # queued | running | done | failed | stopped
    step_index: int = 0
    created: str = field(default_factory=lambda: datetime.now().strftime("%H:%M:%S"))
    started: str = ""
    finished: str = ""
    message: str = ""

    def as_dict(self) -> dict:
        return {
            "id": self.id, "title": self.title, "status": self.status,
            "step_index": self.step_index, "step_total": len(self.steps),
            "step_label": (self.steps[self.step_index].label
                           if self.step_index < len(self.steps) else ""),
            "steps": [s.label for s in self.steps],
            "created": self.created, "started": self.started,
            "finished": self.finished, "message": self.message,
        }


class JobRunner:
    """Hàng đợi + worker. Bốn nút điều khiển: chạy, tạm dừng, bỏ việc đang chạy,
    dừng hẳn (xoá cả hàng đợi)."""

    def __init__(self):
        self._pending: deque[Job] = deque()
        self._history: deque[Job] = deque(maxlen=40)
        self._current: Job | None = None
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._paused = False
        self._skip_current = False
        self._ids = itertools.count(1)
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    # ── API cho tầng web ────────────────────────────────────────────────────
    def enqueue(self, title: str, steps: list[Step]) -> Job:
        job = Job(id=next(self._ids), title=title, steps=steps)
        with self._lock:
            self._pending.append(job)
        log(f"➕ Xếp hàng: {title} ({len(steps)} bước)")
        self._wake.set()
        return job

    def pause(self) -> None:
        self._paused = True
        log("⏸ Tạm dừng — việc đang chạy vẫn chạy nốt, chưa lấy việc mới.")

    def resume(self) -> None:
        self._paused = False
        log("▶ Chạy tiếp hàng đợi.")
        self._wake.set()

    def skip_current(self) -> None:
        """Bỏ việc đang chạy (kill tiến trình con), hàng đợi vẫn chạy tiếp."""
        with self._lock:
            proc, cur = self._proc, self._current
        if cur is None:
            return
        self._skip_current = True
        log(f"⏭ Bỏ việc đang chạy: {cur.title}")
        _terminate(proc)

    def stop_all(self) -> None:
        """Dừng hẳn: xoá hàng đợi + kill việc đang chạy."""
        with self._lock:
            dropped = len(self._pending)
            for job in self._pending:
                job.status = "stopped"
                job.message = "Đã huỷ khi dừng hàng đợi."
                self._history.appendleft(job)
            self._pending.clear()
            proc, cur = self._proc, self._current
        self._paused = False
        if cur is not None:
            self._skip_current = True
        log(f"⏹ Dừng hàng đợi (huỷ {dropped} việc chờ)." )
        _terminate(proc)

    def remove(self, job_id: int) -> bool:
        with self._lock:
            for job in list(self._pending):
                if job.id == job_id:
                    self._pending.remove(job)
                    job.status = "stopped"
                    job.message = "Đã bỏ khỏi hàng đợi."
                    self._history.appendleft(job)
                    return True
        return False

    def state(self) -> dict:
        with self._lock:
            return {
                "paused": self._paused,
                "current": self._current.as_dict() if self._current else None,
                "pending": [j.as_dict() for j in self._pending],
                "history": [j.as_dict() for j in list(self._history)[:12]],
                "busy": self._current is not None,
            }

    def busy(self) -> bool:
        with self._lock:
            return self._current is not None or bool(self._pending)

    # ── Worker ──────────────────────────────────────────────────────────────
    def _loop(self) -> None:
        while True:
            job = None
            if not self._paused:
                with self._lock:
                    if self._pending:
                        job = self._pending.popleft()
                        self._current = job
            if job is None:
                self._wake.wait(timeout=1.0)
                self._wake.clear()
                continue
            try:
                self._run_job(job)
            except Exception as e:                      # worker không được chết
                job.status = "failed"
                job.message = str(e)
                log(f"❌ Lỗi hàng đợi: {e}")
            finally:
                job.finished = datetime.now().strftime("%H:%M:%S")
                with self._lock:
                    self._history.appendleft(job)
                    self._current = None
                    self._proc = None
                self._skip_current = False

    def _run_job(self, job: Job) -> None:
        job.status = "running"
        job.started = datetime.now().strftime("%H:%M:%S")
        log(f"▶ {job.title}")
        for i, step in enumerate(job.steps):
            job.step_index = i
            if self._skip_current:
                job.status = "stopped"
                job.message = "Đã bỏ giữa chừng."
                log(f"⏹ {job.title}: dừng ở bước “{step.label}”.")
                return
            log(f"── [{i + 1}/{len(job.steps)}] {step.label}")
            code = self._run_step(step)
            if self._skip_current:
                job.status = "stopped"
                job.message = f"Đã dừng ở bước “{step.label}”."
                return
            if code in step.soft_fail_codes:
                job.status = "stopped"
                job.message = f"Dừng ở bước “{step.label}” (mã {code}) — xem nhật ký."
                log(f"⛔ {job.title}: dừng ở “{step.label}” (mã {code}).")
                return
            if code != 0:
                job.status = "failed"
                job.message = f"Bước “{step.label}” lỗi (mã {code})."
                log(f"❌ {job.title}: bước “{step.label}” lỗi (mã {code}).")
                return
            if step.on_success is not None:
                try:
                    step.on_success()
                except Exception as e:      # nối việc hỏng ≠ bước vừa chạy hỏng
                    log(f"⚠️ Không nối được việc sau bước “{step.label}”: {e}")
        job.step_index = len(job.steps)
        job.status = "done"
        job.message = "Hoàn tất."
        log(f"✅ {job.title} — xong.")

    def _run_step(self, step: Step) -> int:
        try:
            proc = subprocess.Popen(
                step.argv, cwd=step.cwd, env=step.env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True, encoding="utf-8", errors="replace", bufsize=1,
                creationflags=CREATE_NO_WINDOW,
            )
        except Exception as e:
            log(f"❌ Không chạy được: {e}")
            return 1

        with self._lock:
            self._proc = proc
        try:
            for line in proc.stdout:                     # type: ignore[union-attr]
                line = line.rstrip("\r\n")
                if line.strip():
                    log(line)
            return proc.wait()
        finally:
            with self._lock:
                self._proc = None


def _terminate(proc: subprocess.Popen | None) -> None:
    """Kết thúc việc đang chạy — phải diệt CẢ CÂY tiến trình, không riêng runner.

    Runner còn mở Firefox (dịch/SEO) và ffmpeg (render) làm tiến trình CHÁU;
    trên Windows terminate()/kill() chỉ chạm tới đúng runner, các cháu vẫn sống:
    profile Firefox bị khoá làm hỏng lần dịch sau, ffmpeg tiếp tục chiếm GPU và
    giữ file output. taskkill /T là cách chuẩn của Windows để quét cả cây.
    """
    if proc is None or proc.poll() is not None:
        return
    try:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                       capture_output=True, creationflags=CREATE_NO_WINDOW)
    except Exception:
        pass
    deadline = time.time() + 5
    while time.time() < deadline and proc.poll() is None:
        time.sleep(0.2)
    if proc.poll() is None:       # taskkill không diệt được → ít nhất kill runner
        try:
            proc.kill()
        except Exception:
            pass


runner = JobRunner()

# Hàng đợi RIÊNG cho việc đăng YouTube, chạy SONG SONG với hàng đợi trên.
#
# Vì sao được phép song song trong khi cả file này chủ trương một worker: lý do có
# một worker là tranh chấp tài nguyên ĐỘC QUYỀN (GPU, profile Firefox, CPU cho
# ffmpeg). Đăng video chỉ tốn BĂNG THÔNG — không đụng cái nào trong số đó. Bắt tập
# sau đợi tập trước tải lên xong là để GPU nằm không hàng chục phút mỗi mẻ.
#
# Vẫn chỉ MỘT worker cho riêng hàng này: tải hai video cùng lúc chỉ chia nhỏ băng
# thông chứ không nhanh hơn.
upload_runner = JobRunner()
