"""Small authenticated loopback bridge for the Gemini Chrome extension.

Only browser transport lives here. Prompts, retries, validation and DOCX saving
remain in dich_gemini. Commands are delivered once: an uncertain submit must
stop the job instead of silently sending the same paragraph twice.
"""
import json
import secrets
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import urlsplit

from gemini_backend import BRIDGE_PORT, EXTENSION_CONNECT_TIMEOUT, connection_token


class BridgeServer(ThreadingHTTPServer):
    def server_bind(self):
        # On Windows SO_REUSEADDR allows TWO live listeners on the same port.
        # Exclusive binding prevents two GUI/runner processes mixing sessions.
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.allow_reuse_address = False
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class ExtensionBridge:
    def __init__(self, port=BRIDGE_PORT, token=None):
        self.token = token or connection_token()
        self.session = secrets.token_hex(16)
        self.lock = threading.Lock()
        self.serial = threading.Lock()
        self.pending = None
        self.owner = None
        self.connected = threading.Event()   # set khi Chrome nào đó hỏi lệnh lần đầu
        self.bad_auth = 0                    # số lượt hỏi lệnh bị từ chối (sai mã kết nối)
        self.closed = False
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass  # Never log authorization headers or source text.

            def allowed_origin(self):
                origin = self.headers.get("Origin", "")
                return not origin or (
                    origin.startswith("chrome-extension://")
                    and len(origin.removeprefix("chrome-extension://")) == 32
                    and all(c in "abcdefghijklmnop" for c in origin[19:])
                )

            def reply(self, status, payload):
                data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                origin = self.headers.get("Origin", "")
                if origin and self.allowed_origin():
                    self.send_header("Access-Control-Allow-Origin", origin)
                    self.send_header("Vary", "Origin")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def auth_error(self):
                """None nếu hợp lệ; ngược lại là câu báo hiện ở popup extension."""
                host = f"127.0.0.1:{bridge.server.server_port}"
                if self.headers.get("Host") != host or not self.allowed_origin():
                    return "Sai nguồn yêu cầu"
                if not secrets.compare_digest(self.headers.get("Authorization", ""),
                                              f"Bearer {bridge.token}"):
                    # 02/10/2026: người dùng dán nhầm mã ?token= của trang web vào popup.
                    return ("Sai mã kết nối. Mở tab 🧩 Extension trên web myvoice, copy ô "
                            "Mã kết nối dán vào đây (KHÔNG phải mã ?token= trong link web)")
                return None

            def authorized(self):
                return self.auth_error() is None

            def do_OPTIONS(self):
                if not self.allowed_origin():
                    return self.reply(403, {"error": "Origin không hợp lệ"})
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin", ""))
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, X-Client-Id")
                self.send_header("Access-Control-Allow-Private-Network", "true")
                self.end_headers()

            def do_GET(self):
                error = self.auth_error()
                if error:
                    with bridge.lock:
                        bridge.bad_auth += 1   # có Chrome hỏi nhưng sai mã → báo rõ khi hết giờ chờ
                    return self.reply(403, {"error": error})
                if self.path != "/command":
                    return self.reply(404, {"error": "Không có đường dẫn này"})
                client = self.headers.get("X-Client-Id", "")
                if not client or len(client) > 128:
                    return self.reply(400, {"error": "Thiếu client ID"})
                with bridge.lock:
                    if bridge.owner and bridge.owner != client:
                        return self.reply(409, {"error": "Một Chrome khác đang kết nối phiên này"})
                    bridge.owner = client
                    bridge.connected.set()
                    command = None
                    p = bridge.pending
                    if p and not p["delivered"] and p["command"]["expires"] > time.time():
                        p["delivered"] = True
                        command = p["command"]
                self.reply(200, {"session": bridge.session, "command": command})

            def do_POST(self):
                error = self.auth_error()
                if error:
                    return self.reply(403, {"error": error})
                if self.path != "/result":
                    return self.reply(404, {"error": "Không có đường dẫn này"})
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 0 < size <= 4 * 1024 * 1024:
                        raise ValueError("Kích thước không hợp lệ")
                    data = json.loads(self.rfile.read(size))
                    if not isinstance(data, dict):
                        raise ValueError("Cần JSON object")
                except (ValueError, UnicodeError):
                    return self.reply(400, {"error": "Kết quả không hợp lệ"})
                with bridge.lock:
                    if not bridge.owner or self.headers.get("X-Client-Id") != bridge.owner:
                        return self.reply(409, {"error": "Client không sở hữu phiên"})
                    p = bridge.pending
                    if (data.get("session") != bridge.session or not p
                            or data.get("id") != p["command"]["id"] or not p["delivered"]):
                        return self.reply(409, {"error": "Lệnh đã hết hạn"})
                    if not p["done"].is_set():
                        p["result"] = data
                        p["done"].set()
                self.reply(200, {"ok": True})

        try:
            self.server = BridgeServer(("127.0.0.1", port), Handler)
        except OSError as exc:
            raise RuntimeError(
                f"Không mở được cổng extension {port}. Hãy kết thúc phiên dịch Chrome khác trước."
            ) from exc
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def wait_for_client(self, timeout):
        """True nếu có Chrome (extension) hỏi lệnh trong `timeout` giây."""
        return self.connected.wait(timeout)

    def call(self, action, timeout=65, **payload):
        with self.serial:
            p = {"command": {"id": secrets.token_hex(16), "session": self.session,
                             "action": action, "expires": time.time() + timeout, **payload},
                 "delivered": False, "done": threading.Event(), "result": None}
            with self.lock:
                if self.closed:
                    raise RuntimeError("Phiên Chrome Extension đã đóng")
                self.pending = p
            try:
                if not p["done"].wait(timeout):
                    raise TimeoutError(
                        "Chrome Extension không phản hồi. Mở biểu tượng OmniVoice Gemini, "
                        "dán mã kết nối và bật Kết nối; kiểm tra tab Gemini đã đăng nhập. "
                        "Lệnh chưa được xác nhận sẽ không tự gửi lại."
                    )
                result = p["result"] or {}
                if result.get("error"):
                    raise RuntimeError(f"Chrome Extension: {result['error']}")
                return result.get("value")
            finally:
                with self.lock:
                    if self.pending is p:
                        self.pending = None

    def close(self):
        with self.lock:
            if self.closed:
                return
            self.closed = True
            if self.pending:
                self.pending["result"] = {"error": "Phiên dịch đã đóng"}
                self.pending["done"].set()
        self.server.shutdown()
        self.server.server_close()


class ChromeExtensionDriver:
    """The browser operations used by translation, blank retry and SEO."""
    is_chrome_extension = True

    def __init__(self, url, bridge=None, connect_timeout=EXTENSION_CONNECT_TIMEOUT):
        self.bridge = bridge or ExtensionBridge()
        self.generating = False
        try:
            # Báo sớm (thay vì đợi hết 65 s của lệnh navigate) khi KHÔNG có Chrome nào
            # hỏi lệnh: Chrome đóng, chưa bấm Kết nối, sai mã... → bên gọi dự phòng Firefox.
            if connect_timeout and not self.bridge.wait_for_client(connect_timeout):
                if self.bridge.bad_auth:
                    why = (f"có Chrome hỏi lệnh nhưng SAI mã kết nối ({self.bridge.bad_auth} lượt) "
                           "— mở popup extension, dán đúng mã ở tab 🧩 Extension rồi Lưu và kết nối")
                else:
                    why = (f"không có Chrome nào hỏi lệnh trong {int(connect_timeout)} giây — mở "
                           "Chrome có cài extension OmniVoice Gemini và bật kết nối trong popup")
                raise RuntimeError(f"Chrome Extension chưa kết nối: {why}.")
            self.get(url)
        except Exception:
            self.quit()
            raise

    def get(self, url):
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc != "gemini.google.com":
            raise ValueError("Extension chỉ mở https://gemini.google.com")
        self.bridge.call("navigate", url=url)

    @property
    def current_url(self):
        return self.bridge.call("status")["url"]

    def responses(self, selectors):
        state = self.bridge.call("responses", selectors=selectors)
        self.generating = bool(state.get("generating"))
        return [SimpleNamespace(text=t) for t in state["texts"]]

    def submit(self, text, editor_selectors, send_selectors):
        self.bridge.call("submit", text=text, editor_selectors=editor_selectors,
                         send_selectors=send_selectors)

    def quit(self):
        # Leave Chrome and the conversation visible for inspection.
        self.bridge.close()
