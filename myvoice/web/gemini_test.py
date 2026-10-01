"""Tab 🧩 Extension: thử kết nối và gửi thử MỘT đoạn qua Chrome Extension ngay trên web.

Chạy TRONG tiến trình server, không qua hàng đợi — chỉ là lượt thử, không ghi file
nào. Luôn ÉP cách "extension" (backend="extension" → init_firefox KHÔNG dự phòng
Firefox) vì mục đích là kiểm chính extension. Một lượt thử tại một thời điểm; đang
có phiên dịch thật (cổng 17863 bận) thì bridge báo lỗi ngay, không chen vào phiên đó.
"""
from __future__ import annotations

import threading
import time

SAMPLE_TEXT = "你好，今天的天气很好。我们一起去公园散步吧。"
MAX_LINES = 400


class GeminiTester:
    def __init__(self):
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._reset("")

    def _reset(self, mode: str) -> None:
        self.mode = mode
        self.lines: list[str] = []
        self.result = ""
        self.error = ""
        self.url = ""
        self.started = time.time() if mode else 0.0
        self.finished = 0.0

    def log(self, msg) -> None:
        with self._lock:
            self.lines.append(f"{time.strftime('%H:%M:%S')} {msg}")
            del self.lines[:-MAX_LINES]

    def running(self) -> bool:
        t = self._thread
        return t is not None and t.is_alive()

    def state(self) -> dict:
        with self._lock:
            return {"running": self.running(), "mode": self.mode, "lines": list(self.lines),
                    "result": self.result, "error": self.error, "url": self.url,
                    "started": self.started, "finished": self.finished}

    def start(self, mode: str, text: str = "", full_prefix: bool = False) -> None:
        """mode "check": mở cầu nối + tab Gemini rồi đóng. "send": thêm bước gửi `text`."""
        if mode not in ("check", "send"):
            raise ValueError("Chế độ thử không hợp lệ.")
        text = (text or "").strip()
        if mode == "send" and not text:
            raise ValueError("Nhập một đoạn tiếng Trung ngắn để gửi thử.")
        with self._lock:
            if self.running():
                raise RuntimeError("Đang có lượt thử chạy — đợi xong đã.")
            self._reset(mode)
            self._thread = threading.Thread(target=self._run, args=(mode, text, bool(full_prefix)),
                                            daemon=True, name="gemini-test")
            self._thread.start()

    def _run(self, mode: str, text: str, full_prefix: bool) -> None:
        import dich_gemini as g
        driver = None
        try:
            self.log("🔌 Mở cầu nối 127.0.0.1:17863, chờ Chrome (extension) hỏi lệnh — tối đa 40 s…")
            driver = g.init_firefox(backend="extension", on_log=self.log)
            url = driver.current_url
            with self._lock:
                self.url = url
            self.log(f"✅ Chrome đã kết nối, tab Gemini sẵn sàng: {url}")
            if mode == "send":
                if full_prefix:
                    self.log("📨 Gửi câu hướng dẫn dịch đầy đủ như lúc dịch thật (tin nhắn riêng)…")
                    g.send_prefix_to_gemini(driver, g.load_prefix(), on_log=self.log)
                    tag = g.FICTION_TAG.strip()
                    msg = (tag + "\n" + text) if tag else text
                else:
                    de_bai = g.BLANK_RETRY_PROMPT.strip()
                    msg = (de_bai + "\n" + text) if de_bai else text
                self.log(f"📤 Gửi {len(text)} ký tự thử…")
                ans = (g.send_to_gemini(driver, msg, on_log=self.log) or "").strip()
                if not ans:
                    raise RuntimeError("Gemini không trả về nội dung — xem nhật ký và tab Chrome.")
                with self._lock:
                    self.result = ans
                self.log(f"🎉 Nhận được {len(ans)} ký tự. Extension hoạt động tốt.")
            else:
                self.log("🎉 Kết nối tốt. Bấm 🧪 Gửi thử để dịch một đoạn.")
        except Exception as e:
            with self._lock:
                self.error = str(e)
            self.log(f"❌ {e}")
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except Exception:
                    pass
            with self._lock:
                self.finished = time.time()


tester = GeminiTester()
