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
import queue
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime

CREATE_NO_WINDOW = 0x08000000

# ── Nhật ký chung: vòng đệm để tải lại trang vẫn thấy, + kênh đẩy cho SSE ────
_LOG_LIMIT = 4000


class LogBus:
    def __init__(self):
        self._lines: deque[tuple[int, str]] = deque(maxlen=_LOG_LIMIT)
        self._subs: list[queue.Queue] = []
        self._lock = threading.Lock()
        self._seq = itertools.count(1)

    def publish(self, text: str) -> None:
        for line in str(text).splitlines() or [""]:
            item = (next(self._seq), line)
            with self._lock:
                self._lines.append(item)
                subs = list(self._subs)
            for q in subs:
                try:
                    q.put_nowait(item)
                except queue.Full:
                    pass

    def tail(self, n: int = 400) -> list[tuple[int, str]]:
        with self._lock:
            return list(self._lines)[-n:]

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=2000)
        with self._lock:
            self._subs.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._subs:
                self._subs.remove(q)


log_bus = LogBus()


def log(text: str) -> None:
    log_bus.publish(text)


# ── Mô tả công việc ─────────────────────────────────────────────────────────
@dataclass
class Step:
    label: str
    argv: list[str]
    cwd: str | None = None
    env: dict | None = None
    # Mã thoát được coi là "bỏ qua có chủ ý" chứ không phải lỗi (vd bước chuẩn bị
    # input.txt trả 1 khi bản dịch còn thiếu đoạn → dừng tập này, không phải hỏng).
    soft_fail_codes: tuple[int, ...] = ()


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
    """Kết thúc tiến trình con: xin lịch sự trước, cứng rắn sau 5 giây."""
    if proc is None or proc.poll() is not None:
        return
    try:
        proc.terminate()
    except Exception:
        return
    deadline = time.time() + 5
    while time.time() < deadline and proc.poll() is None:
        time.sleep(0.2)
    if proc.poll() is None:
        try:
            proc.kill()
        except Exception:
            pass


runner = JobRunner()
