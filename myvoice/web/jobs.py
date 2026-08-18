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
import re
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
# Chỗ xem tiến trình ĐẦY ĐỦ là cửa sổ console đã mở sẵn khi bật server
# (chay_web.bat / nút 🌐 Bảng web của GUI). Riêng hàng đợi ĐĂNG còn giữ thêm một
# vòng đệm (LogTail bên dưới) để trang web và GUI cùng nhìn thấy — xem chú thích ở đó.
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


class LogTail:
    """Vòng đệm các dòng nhật ký gần đây của MỘT hàng đợi.

    Vì sao cần: console của server nằm ở cửa sổ khác, mà GUI lại là TIẾN TRÌNH
    KHÁC HẲN — bấm “⬆ Đăng ngay” trên web thì hai chỗ đó không hay biết gì, nhìn
    vào chỉ thấy im lìm không rõ có chạy hay không. Vòng đệm này là nguồn chung để
    trang web hiện vài dòng cuối và GUI hỏi xin dòng mới qua /api/nhatky-dang.

    Mỗi dòng mang một SỐ THỨ TỰ tăng dần: bên đọc chỉ cần nhớ số cuối đã lấy rồi
    hỏi “có gì mới hơn số này không”, nên không đọc trùng, cũng không sót khi
    chậm nhịp (miễn chưa trôi khỏi vòng đệm).
    """

    _PCT = re.compile(r"Tải lên (\d{1,3})%")
    # Dòng mở/kết một việc → tiến độ % của việc trước không còn nghĩa gì nữa.
    _RESET = ("▶", "➕", "✅", "❌", "⛔", "⏹", "♻", "⏭")

    def __init__(self, maxlen: int = 200):
        self._lines: deque[tuple[int, str, str]] = deque(maxlen=maxlen)   # (số, giờ, nội dung)
        self._lock = threading.Lock()
        self._seq = 0
        self._percent: int | None = None
        self._pct_step = -1

    def add(self, text: str) -> None:
        text = str(text).rstrip()
        if not text:
            return
        pct = self._PCT.search(text)
        with self._lock:
            if pct:
                # Tiến độ tải lên nhảy từng % → hàng trăm dòng mỗi video. Giữ số %
                # mới nhất cho thanh tiến trình, còn vào nhật ký thì mỗi mốc 10%
                # một dòng: đủ biết là còn sống mà không ngập ô nhật ký của GUI.
                self._percent = min(100, int(pct.group(1)))
                step = self._percent // 10
                if step == self._pct_step:
                    return
                self._pct_step = step
                text = f"⬆ Tải lên {self._percent}%"
            elif text.startswith(self._RESET):
                self._percent, self._pct_step = None, -1
            self._seq += 1
            self._lines.append((self._seq, datetime.now().strftime("%H:%M:%S"), text))

    def since(self, seq: int) -> tuple[int, list[str]]:
        """Các dòng mới hơn `seq` → (số thứ tự cuối, nội dung KHÔNG kèm giờ).

        Không kèm giờ vì bên đọc (GUI) tự đóng dấu thời gian của nó.
        """
        with self._lock:
            return self._seq, [t for n, _, t in self._lines if n > seq]

    def tail(self, n: int = 8) -> list[str]:
        """n dòng cuối, có kèm giờ — dùng để hiện trên trang web."""
        with self._lock:
            return [f"{when}  {t}" for _, when, t in list(self._lines)[-n:]]

    @property
    def seq(self) -> int:
        with self._lock:
            return self._seq

    @property
    def percent(self) -> int | None:
        return self._percent


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
    # Việc NHẸ (xem trước, kiểm tra nhanh): vẫn xếp hàng chạy bình thường nhưng
    # KHÔNG tính vào heavy_busy() — bấm một nút xem kế hoạch mà bị coi là "đã
    # chạy xong mẻ" rồi 3 phút sau 🌙 úp máy thì vô lý.
    light: bool = False
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

    def __init__(self, tail: "LogTail | None" = None):
        self._pending: deque[Job] = deque()
        self._history: deque[Job] = deque(maxlen=40)
        self._current: Job | None = None
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._paused = False
        self._skip_current = False
        self._ids = itertools.count(1)
        # Vòng đệm nhật ký RIÊNG của hàng đợi này (có thể không có). Mọi dòng của
        # hàng đợi phải đi qua self.note() thì vòng đệm mới đủ, đừng gọi log() thẳng.
        self._tail = tail
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    # ── API cho tầng web ────────────────────────────────────────────────────
    def note(self, text: str) -> None:
        """Ghi một dòng nhật ký MANG DANH hàng đợi này: console + vòng đệm riêng."""
        log(text)
        if self._tail is not None:
            try:
                self._tail.add(text)
            except Exception:       # nhật ký hỏng không được làm hỏng việc đang chạy
                pass

    def enqueue(self, title: str, steps: list[Step], light: bool = False) -> Job:
        job = Job(id=next(self._ids), title=title, steps=steps, light=light)
        with self._lock:
            self._pending.append(job)
        self.note(f"➕ Xếp hàng: {title} ({len(steps)} bước)")
        self._wake.set()
        return job

    def pause(self) -> None:
        self._paused = True
        self.note("⏸ Tạm dừng — việc đang chạy vẫn chạy nốt, chưa lấy việc mới.")

    def resume(self) -> None:
        self._paused = False
        self.note("▶ Chạy tiếp hàng đợi.")
        self._wake.set()

    def skip_current(self) -> None:
        """Bỏ việc đang chạy (kill tiến trình con), hàng đợi vẫn chạy tiếp."""
        with self._lock:
            proc, cur = self._proc, self._current
        if cur is None:
            return
        self._skip_current = True
        self.note(f"⏭ Bỏ việc đang chạy: {cur.title}")
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
        self.note(f"⏹ Dừng hàng đợi (huỷ {dropped} việc chờ)." )
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

    def heavy_busy(self) -> bool:
        """busy() nhưng BỎ QUA các việc `light` — nguồn sự thật cho 🌙/⏻
        (power.py và /api/trangthai): chỉ mẻ thật mới kích hoạt ngủ/tắt máy."""
        with self._lock:
            if self._current is not None and not self._current.light:
                return True
            return any(not j.light for j in self._pending)

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
                self.note(f"❌ Lỗi hàng đợi: {e}")
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
        self.note(f"▶ {job.title}")
        for i, step in enumerate(job.steps):
            job.step_index = i
            if self._skip_current:
                job.status = "stopped"
                job.message = "Đã bỏ giữa chừng."
                self.note(f"⏹ {job.title}: dừng ở bước “{step.label}”.")
                return
            self.note(f"── [{i + 1}/{len(job.steps)}] {step.label}")
            code = self._run_step(step)
            if self._skip_current:
                job.status = "stopped"
                job.message = f"Đã dừng ở bước “{step.label}”."
                return
            if code in step.soft_fail_codes:
                job.status = "stopped"
                job.message = f"Dừng ở bước “{step.label}” (mã {code}) — xem nhật ký."
                self.note(f"⛔ {job.title}: dừng ở “{step.label}” (mã {code}).")
                return
            if code != 0:
                job.status = "failed"
                job.message = f"Bước “{step.label}” lỗi (mã {code})."
                self.note(f"❌ {job.title}: bước “{step.label}” lỗi (mã {code}).")
                return
            if step.on_success is not None:
                try:
                    step.on_success()
                except Exception as e:      # nối việc hỏng ≠ bước vừa chạy hỏng
                    self.note(f"⚠️ Không nối được việc sau bước “{step.label}”: {e}")
        job.step_index = len(job.steps)
        job.status = "done"
        job.message = "Hoàn tất."
        self.note(f"✅ {job.title} — xong.")

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
            self.note(f"❌ Không chạy được: {e}")
            return 1

        with self._lock:
            self._proc = proc
        try:
            for line in proc.stdout:                     # type: ignore[union-attr]
                line = line.rstrip("\r\n")
                if line.strip():
                    self.note(line)
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

# Nhật ký RIÊNG của hàng đợi đăng — trang web hiện vài dòng cuối, GUI hỏi xin dòng
# mới qua /api/nhatky-dang. Chỉ hàng đợi đăng mới cần: hàng đợi chính in ra hàng
# nghìn dòng ffmpeg/Whisper, chiếu hết sang GUI thì ô nhật ký thành bãi rác.
upload_log = LogTail()

# Hàng đợi RIÊNG cho việc đăng YouTube, chạy SONG SONG với hàng đợi trên.
#
# Vì sao được phép song song trong khi cả file này chủ trương một worker: lý do có
# một worker là tranh chấp tài nguyên ĐỘC QUYỀN (GPU, profile Firefox, CPU cho
# ffmpeg). Đăng video chỉ tốn BĂNG THÔNG — không đụng cái nào trong số đó. Bắt tập
# sau đợi tập trước tải lên xong là để GPU nằm không hàng chục phút mỗi mẻ.
#
# Vẫn chỉ MỘT worker cho riêng hàng này: tải hai video cùng lúc chỉ chia nhỏ băng
# thông chứ không nhanh hơn.
upload_runner = JobRunner(tail=upload_log)

# Hàng đợi thứ BA: lên lịch đăng Facebook. Tách khỏi hàng đợi đăng YouTube để hai
# nơi chạy SONG SONG — dựng xong một tập là vừa đẩy lên YouTube vừa xếp lịch Page,
# không ai đợi ai, và hàng đợi chính đi tiếp tập sau ngay.
#
# Nhưng vẫn chỉ MỘT worker cho riêng hàng này, không được bỏ: hai lần chạy script
# Facebook cùng lúc sẽ cùng đọc "giờ lên lịch xa nhất" rồi cùng xếp vào ĐÚNG MỘT
# khung giờ — hai tập chồng lên nhau trên Page.
fb_log = LogTail()
fb_runner = JobRunner(tail=fb_log)
