"""Tab 🤖 GPT CLI: kiểm tra codex (binary · phiên bản · đăng nhập · lệnh thử ngắn) và
nhắn thử MỘT tin rồi đợi CLI trả lời, ngay trên web — y khuôn tab 🧩 Extension
(gemini_test).

Chạy TRONG tiến trình server, không qua hàng đợi, không ghi file. Một lượt thử tại
một thời điểm. Mỗi lượt gửi là MỘT lệnh `codex exec` riêng (CLI không nhớ gì giữa
hai lệnh), nên ô "như lúc dịch thật" cho thấy rõ: câu hướng dẫn dịch (bản CLI) + thẻ
hư cấu đi KÈM trong cùng một tin — đề bài đã ghép được trả về để người dùng soi.
"""
from __future__ import annotations

import threading
import time

SAMPLE_TEXT = "你好，今天的天气很好。我们一起去公园散步吧。"
PING_TEXT = "Trả lời đúng một chữ: OK"
MAX_LINES = 400


class GptCliTester:
    def __init__(self):
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._reset("")

    def _reset(self, mode: str) -> None:
        self.mode = mode
        self.lines: list[str] = []
        self.result = ""
        self.error = ""
        self.prompt = ""          # đề bài đã ghép gửi đi (soi được câu hướng dẫn gửi kèm)
        self.text = ""            # tin đã gửi (PING_TEXT khi 🔌) — bong bóng "Bạn" trên tab
        self.full = False         # gửi như lúc dịch thật?
        self.info: dict = {}      # path / version / logged_in / login / model / effort
        self.elapsed = 0.0        # giây CLI trả lời (lệnh gửi thử)
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
                    "result": self.result, "error": self.error, "prompt": self.prompt,
                    "text": self.text, "full": self.full,
                    "info": dict(self.info), "elapsed": self.elapsed,
                    "started": self.started, "finished": self.finished}

    def start(self, mode: str, text: str = "", full_prefix: bool = False) -> None:
        """mode "check": tìm codex, hỏi đăng nhập, gửi một lệnh ngắn (PING_TEXT).
        "send": gửi `text` (tin tự do, hoặc như lúc dịch thật nếu full_prefix) rồi đợi."""
        if mode not in ("check", "send"):
            raise ValueError("Chế độ thử không hợp lệ.")
        text = (text or "").strip()
        if mode == "send" and not text:
            raise ValueError("Nhập một tin ngắn để gửi thử.")
        with self._lock:
            if self.running():
                raise RuntimeError("Đang có lượt thử chạy — đợi xong đã.")
            self._reset(mode)
            self.text = text if mode == "send" else PING_TEXT
            self.full = mode == "send" and bool(full_prefix)
            self._thread = threading.Thread(target=self._run, args=(mode, text, bool(full_prefix)),
                                            daemon=True, name="gptcli-test")
            self._thread.start()

    def _run(self, mode: str, text: str, full_prefix: bool) -> None:
        import dich_gptcli as gc
        try:
            self.log("🔎 Tìm codex trên PATH (lấy bản mới nhất) và hỏi trạng thái đăng nhập…")
            info = gc.kiem_tra()                      # không có codex → GptCliError
            with self._lock:
                self.info = info
            self.log(f"✅ {info['path']} — codex-cli {info['version']}")
            self.log(("✅ " if info["logged_in"] else "⚠️ ") + info["login"])
            if not info["logged_in"]:
                self.log("   Mở terminal, chạy `codex login` (tài khoản ChatGPT) rồi thử lại.")
            hl = gc.hieu_luc()                        # cùng model/mức mà lệnh dịch thật sẽ dùng
            with self._lock:
                self.info.update(model=hl["model"], effort=hl["effort"])
            self.log(f"🎛 {gc.mo_ta_hieu_luc(hl)}")

            import dich_gemini as g
            drv = gc.GptCliDriver(on_log=None)
            if mode == "check":
                msg = PING_TEXT
                self.log(f"🏓 Gửi một lệnh thử ngắn (\"{PING_TEXT}\") — kiểm cả model trong "
                         "~/.codex/config.toml có chạy được với tài khoản này không…")
            elif full_prefix:
                # Như lúc dịch thật: đăng ký câu hướng dẫn (bản CLI) + thẻ hư cấu; driver
                # ghép tất cả vào CÙNG một lệnh vì CLI không nhớ gì giữa hai lệnh.
                g.send_prefix_to_gemini(drv, g.load_prefix(), on_log=self.log)
                tag = g.FICTION_TAG.strip()
                msg = (tag + "\n" + text) if tag else text
            else:
                msg = text
            prompt = drv.compose(msg)
            with self._lock:
                self.prompt = prompt
            if mode == "send":
                self.log(f"📤 Gửi tin {len(text)} ký tự (đề bài ghép {len(prompt)} ký tự) — "
                         "một lệnh codex exec, đợi trả lời…")
            t0 = time.time()
            ans = (g.send_to_gemini(drv, msg, on_log=self.log) or "").strip()
            elapsed = time.time() - t0
            with self._lock:
                self.elapsed = elapsed
            if not ans:
                raise RuntimeError("GPT CLI không trả về nội dung — xem nhật ký.")
            with self._lock:
                self.result = ans
            if mode == "check":
                self.log(f"🎉 Kết nối tốt: CLI trả lời \"{ans[:60]}\" sau {elapsed:.0f} s. "
                         "Bấm 🧪 Gửi thử để nhắn một tin.")
            else:
                self.log(f"🎉 Nhận được {len(ans)} ký tự sau {elapsed:.0f} s. GPT CLI hoạt động tốt.")
        except Exception as e:
            with self._lock:
                self.error = str(e)
            self.log(f"❌ {e}")
        finally:
            with self._lock:
                self.finished = time.time()


tester = GptCliTester()
