"""Run: venv/Scripts/python.exe -m unittest discover -s myvoice/tests -v"""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import gemini_backend as backend
from gemini_extension import ChromeExtensionDriver, ExtensionBridge
import dich_gemini as g


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.bridge = ExtensionBridge(port=0, token="test-token")
        self.addCleanup(self.bridge.close)
        self.url = f"http://127.0.0.1:{self.bridge.server.server_port}"

    def request(self, path="/command", data=None, token="test-token", client="chrome-a", **headers):
        headers = {"Authorization": f"Bearer {token}", "X-Client-Id": client, **headers}
        request = Request(self.url + path, data=json.dumps(data).encode() if data else None, headers=headers)
        with urlopen(request, timeout=2) as response:
            return json.load(response)

    def start_call(self, **kwargs):
        result = {}
        def run():
            try:
                result["value"] = self.bridge.call("submit", **kwargs)
            except Exception as exc:
                result["error"] = exc
        thread = threading.Thread(target=run)
        thread.start()
        self.addCleanup(thread.join, 2)
        return result, thread

    def command(self):
        for _ in range(100):
            payload = self.request()
            if payload["command"]:
                return payload["command"]
            time.sleep(.005)
        self.fail("No command")

    def test_authenticated_round_trip_and_no_redelivery(self):
        result, thread = self.start_call(text="你好\nTiếng Việt", timeout=2)
        command = self.command()
        self.assertEqual(command["text"], "你好\nTiếng Việt")
        self.assertIsNone(self.request()["command"])
        self.request("/result", {"session": command["session"], "id": command["id"], "value": "Bản dịch"})
        thread.join(2)
        self.assertEqual(result, {"value": "Bản dịch"})

    def test_rejects_wrong_token_web_origin_and_second_client(self):
        for headers in ({"token": "wrong"}, {"Origin": "https://evil.example"}, {"Host": "evil.example"}):
            with self.assertRaises(HTTPError) as caught:
                self.request(**headers)
            self.assertEqual(caught.exception.code, 403)
            message = json.load(caught.exception)["error"]
            if "token" in headers:
                # The popup shows this text: it must say which code to paste.
                self.assertIn("Sai mã kết nối", message)
                self.assertIn("?token=", message)
            else:
                self.assertEqual(message, "Sai nguồn yêu cầu")
        self.request(Origin="chrome-extension://" + "a" * 32)
        with self.assertRaises(HTTPError) as caught:
            self.request(client="chrome-b")
        self.assertEqual(caught.exception.code, 409)

    def test_timeout_and_late_response_cannot_satisfy_next_command(self):
        result, thread = self.start_call(timeout=.08)
        old = self.command()
        thread.join(2)
        self.assertIsInstance(result["error"], TimeoutError)
        result, thread = self.start_call(timeout=2)
        new = self.command()
        with self.assertRaises(HTTPError) as caught:
            self.request("/result", {"session": old["session"], "id": old["id"], "value": "old"})
        self.assertEqual(caught.exception.code, 409)
        self.request("/result", {"session": new["session"], "id": new["id"], "value": "new"})
        thread.join(2)
        self.assertEqual(result["value"], "new")

    def test_close_interrupts_waiter_and_releases_port(self):
        result, thread = self.start_call(timeout=2)
        self.command()
        port = self.bridge.server.server_port
        self.bridge.close()
        thread.join(2)
        self.assertIsInstance(result["error"], RuntimeError)
        other = ExtensionBridge(port=port, token="new")
        other.close()

    def test_cannot_start_two_sessions_on_the_same_port(self):
        with self.assertRaises(RuntimeError):
            duplicate = ExtensionBridge(port=self.bridge.server.server_port, token="other")
            duplicate.close()

    def test_driver_fails_fast_without_a_polling_chrome_and_releases_the_port(self):
        bridge = ExtensionBridge(port=0, token="lonely")
        port = bridge.server.server_port
        with self.assertRaisesRegex(RuntimeError, "chưa kết nối"):
            ChromeExtensionDriver("https://gemini.google.com/app", bridge=bridge, connect_timeout=.2)
        self.assertTrue(bridge.closed)
        ExtensionBridge(port=port, token="again").close()

    def test_first_poll_marks_the_bridge_connected(self):
        self.assertFalse(self.bridge.wait_for_client(0))
        self.request()
        self.assertTrue(self.bridge.wait_for_client(1))


class BrowserChoiceTests(unittest.TestCase):
    def test_extension_is_the_default_and_firefox_only_when_chosen(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True), \
                patch.object(backend, "PIPE_FILE", Path(tmp) / "settings.json"):
            self.assertEqual(backend.get_backend(), "extension")      # no settings file
            backend.PIPE_FILE.write_text('{"model":"medium"}', encoding="utf-8")
            self.assertEqual(backend.get_backend(), "extension")      # key missing
            backend.PIPE_FILE.write_text('{"gemini_backend":"firefox"}', encoding="utf-8")
            self.assertEqual(backend.get_backend(), "firefox")
            backend.PIPE_FILE.write_text('{"gemini_backend":"bogus"}', encoding="utf-8")
            self.assertEqual(backend.get_backend(), "extension")
            with patch.dict(os.environ, {"OMNI_GEMINI_BACKEND": "firefox"}):
                self.assertEqual(backend.get_backend(), "firefox")
            self.assertEqual(backend.get_backend(), "extension")
            self.assertTrue(backend.fallback_enabled())
            with patch.dict(os.environ, {"OMNI_GEMINI_EXTENSION_FALLBACK": "0"}):
                self.assertFalse(backend.fallback_enabled())

    def test_extension_never_initializes_selenium(self):
        with patch("gemini_extension.ChromeExtensionDriver") as driver, \
                patch.object(g, "_ensure_selenium", side_effect=AssertionError("Selenium called")):
            self.assertIs(g.init_firefox(backend="extension"), driver.return_value)
            driver.assert_called_once_with(g.GEMINI_URL)

    def test_unreachable_extension_falls_back_to_firefox_and_says_so(self):
        logs = []
        with patch.object(g, "get_backend", return_value="extension"), \
                patch("gemini_extension.ChromeExtensionDriver",
                      side_effect=RuntimeError("Chrome Extension chưa kết nối")) as extension, \
                patch("selenium.webdriver.Firefox") as firefox, \
                patch("selenium.webdriver.firefox.options.Options"), \
                patch("selenium.webdriver.firefox.service.Service"), \
                patch.object(g.time, "sleep"):
            driver = g.init_firefox(on_log=logs.append)
        self.assertIs(driver, firefox.return_value)
        extension.assert_called_once_with(g.GEMINI_URL)
        driver.get.assert_called_once_with(g.GEMINI_URL)
        self.assertTrue(any("không sẵn sàng" in line and "chưa kết nối" in line for line in logs), logs)
        self.assertTrue(any("DỰ PHÒNG" in line and "Firefox" in line for line in logs), logs)

    def test_fallback_is_off_when_disabled_or_when_extension_is_forced(self):
        with patch("gemini_extension.ChromeExtensionDriver", side_effect=RuntimeError("down")), \
                patch.object(g, "_ensure_selenium", side_effect=AssertionError("Selenium called")):
            with patch.object(g, "get_backend", return_value="extension"), \
                    patch.dict(os.environ, {"OMNI_GEMINI_EXTENSION_FALLBACK": "0"}):
                with self.assertRaisesRegex(RuntimeError, "down"):
                    g.init_firefox(on_log=lambda _: None)
            with self.assertRaisesRegex(RuntimeError, "down"):
                g.init_firefox(backend="extension", on_log=lambda _: None)

    def test_translation_loop_passes_its_logger_to_the_browser_opener(self):
        logs = []
        driver = Mock(is_chrome_extension=False)
        with patch.object(g, "init_firefox", return_value=driver) as opener, \
                patch.object(g, "send_to_gemini", return_value="Bản dịch đủ dài để không bị coi là cụt."), \
                patch.object(g, "send_prefix_to_gemini"):
            g.send_chunks_to_gemini(["你好"], on_log=logs.append)
        self.assertEqual(opener.call_args.kwargs["on_log"], logs.append)

    def test_restart_reuses_extension_session(self):
        from unittest.mock import Mock
        driver = Mock(is_chrome_extension=True)
        self.assertIs(g.restart_firefox(driver, on_log=lambda _: None), driver)
        driver.get.assert_called_once_with(g.GEMINI_URL)
        driver.quit.assert_not_called()


class FirefoxCompatibilityTests(unittest.TestCase):
    def test_firefox_keeps_profile_binary_url_and_startup_wait(self):
        with patch.object(g, "get_backend", return_value="firefox"), \
                patch("gemini_extension.ChromeExtensionDriver") as extension, \
                patch("selenium.webdriver.Firefox") as firefox, \
                patch("selenium.webdriver.firefox.options.Options") as options, \
                patch("selenium.webdriver.firefox.service.Service") as service, \
                patch.object(g.os.path, "exists", return_value=True), \
                patch.object(g.os.path, "isdir", return_value=True), \
                patch.object(g.time, "sleep") as sleep:
            driver = g.init_firefox(profile="saved-firefox-profile", url="https://gemini.google.com/app/old", wait=8)
            self.assertIs(driver, firefox.return_value)
            self.assertEqual(options.return_value.binary_location, g.FIREFOX_BINARY)
            self.assertEqual([call.args for call in options.return_value.add_argument.call_args_list],
                             [("-profile",), ("saved-firefox-profile",)])
            service.assert_called_once_with(executable_path=g.GECKODRIVER_PATH)
            driver.get.assert_called_once_with("https://gemini.google.com/app/old")
            sleep.assert_called_once_with(8)
            extension.assert_not_called()

    def test_firefox_restart_cannot_switch_to_extension_mid_job(self):
        driver = Mock(is_chrome_extension=False)
        with patch.object(g, "get_backend", return_value="extension"), \
                patch.object(g, "init_firefox") as reopen, patch.object(g.time, "sleep") as sleep:
            self.assertIs(g.restart_firefox(driver, profile="old-profile", on_log=lambda _: None),
                          reopen.return_value)
            driver.quit.assert_called_once_with()
            sleep.assert_called_once_with(3)
            self.assertEqual(reopen.call_args.kwargs["backend"], "firefox")
            self.assertEqual(reopen.call_args.kwargs["profile"], "old-profile")
            self.assertEqual(reopen.call_args.kwargs["url"], g.GEMINI_URL)

    def test_firefox_prefix_failure_still_continues_as_before(self):
        driver = Mock(is_chrome_extension=False)
        with patch.object(g, "send_to_gemini", side_effect=RuntimeError("old prefix timeout")):
            g.send_prefix_to_gemini(driver, "old instruction", on_log=lambda _: None)

    def test_firefox_keep_open_still_controls_owned_browser(self):
        for keep_open in (True, False):
            with self.subTest(keep_open=keep_open):
                driver = Mock(is_chrome_extension=False)
                answer = "Xin chào, hôm nay chúng ta cùng đi dạo trong công viên."
                with patch.object(g, "init_firefox", return_value=driver), \
                        patch.object(g, "send_to_gemini", return_value=answer), \
                        patch.object(g, "send_prefix_to_gemini"):
                    results = g.send_chunks_to_gemini(["你好"], keep_open=keep_open, on_log=lambda _: None)
                self.assertEqual(results, [answer])
                self.assertEqual(driver.quit.call_count, 0 if keep_open else 1)


class TranslationTests(unittest.TestCase):
    def test_resume_preserves_completed_blank_and_red_docx_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gemini_result.docx"
            chunks = ["你好", "世界", "新的"]
            old = "Xin chào, đây là bản dịch đã được kiểm tra đầy đủ."
            new = "Một ngày mới bắt đầu và mọi người cùng bước ra ngoài."
            g.save_results_docx(chunks, [old, ""], path, red={1})
            with patch.object(g, "send_to_gemini", return_value=new) as send, \
                    patch.object(g, "send_prefix_to_gemini"), patch.object(g, "RESEND_BLANK", False):
                result = g.send_chunks_to_gemini(chunks, driver=object(), out_path=path,
                                                resume=True, on_log=lambda _: None)
            self.assertEqual(result, [old, "", new])
            self.assertEqual(send.call_count, 1)
            self.assertEqual(g.read_results_docx(path, 3), [old, "(trống)", new])
            self.assertIn(1, g.read_red_marks(path, 3))

    def test_dead_browser_keeps_chunks_unsent_instead_of_blank(self):
        """Tập 113 (02/10/2026): cửa sổ Firefox dự phòng đóng → 9 đoạn thành "(trống)"
        tức thì và ⏩ không bao giờ gửi lại. Trình duyệt chết = CHƯA gửi."""
        dead = Mock(is_chrome_extension=False)
        type(dead).current_url = property(lambda _self: (_ for _ in ()).throw(RuntimeError("closed")))
        with self.assertRaises(g.GeminiNotSentError):
            g.send_to_gemini(dead, "你好", on_log=lambda _: None)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gemini_result.docx"
            with self.assertRaises(g.GeminiNotSentError):
                g.send_chunks_to_gemini(["你好", "世界"], driver=dead, out_path=path,
                                        on_log=lambda _: None)
            saved = g.read_results_docx(path, 2)
            self.assertFalse(any(g.is_sent_blank(r) for r in saved), saved)
            # ⏩ chạy tiếp sẽ gửi lại cả hai đoạn.
            self.assertEqual([j for j, _ in g.chunks_to_resend(["你好", "世界"], saved)], [1, 2])

    def test_missing_editor_is_not_sent_either(self):
        driver = Mock(is_chrome_extension=False)
        with patch("selenium.webdriver.support.ui.WebDriverWait") as wait:
            wait.return_value.until.side_effect = TimeoutError("no editor")
            with self.assertRaisesRegex(g.GeminiNotSentError, "ô nhập"):
                g.send_to_gemini(driver, "你好", on_log=lambda _: None)

    def test_disconnect_does_not_turn_unsent_chunk_into_a_blank(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "result.docx"
            with patch.object(g, "send_to_gemini", side_effect=RuntimeError("disconnected")), \
                    patch.object(g, "send_prefix_to_gemini"):
                with self.assertRaisesRegex(RuntimeError, "disconnected"):
                    g.send_chunks_to_gemini(["你好"], driver=object(), out_path=path, on_log=lambda _: None)
            self.assertFalse(g.is_sent_blank(g.read_results_docx(path, 1)[0]))


class WebChoiceTests(unittest.TestCase):
    def test_both_forms_persist_browser_without_resetting_other_settings(self):
        from myvoice.web import server
        from starlette.datastructures import FormData
        original = {"gemini_backend": "firefox", "model": "medium", "speed": "0.7",
                    "upload": True, "sleep": True}
        for save in (server._save_pipe_from_form, server._save_model_speed):
            with patch.object(server.core, "load_pipeline", return_value=dict(original)), \
                    patch.object(server.core, "save_pipeline") as write:
                save(FormData({"gemini_backend": "extension"}))
                saved = write.call_args.args[0]
                self.assertEqual(saved["gemini_backend"], "extension")
                self.assertTrue(saved["upload"])
                self.assertTrue(saved["sleep"])

    def test_queued_translation_and_retry_freeze_the_browser_choice(self):
        from myvoice.web import core, steps
        with patch.object(core, "load_pipeline", return_value={"gemini_backend": "firefox"}):
            env = core.subprocess_env()
            retry = steps.retranslate_steps("01")[0]
        self.assertEqual(env["OMNI_GEMINI_BACKEND"], "firefox")
        self.assertEqual(retry.env["OMNI_GEMINI_BACKEND"], "firefox")
        with patch.object(core, "load_pipeline", return_value={"model": "medium"}):
            self.assertEqual(core.subprocess_env()["OMNI_GEMINI_BACKEND"], "extension")

    def test_backend_form_defaults_to_extension_and_shows_firefox_as_fallback(self):
        from fastapi.testclient import TestClient
        from myvoice.web import server
        with patch.object(server, "_vram", return_value={}), \
                patch.object(server.core, "upload_slots_text", return_value="08:00"), \
                patch.object(server.core, "load_pipeline", return_value={"model": "medium"}):
            client = TestClient(server.app)
            client.cookies.set(server.COOKIE, server.TOKEN)
            html = client.get("/").text
        self.assertIn("Dịch bằng Chrome Extension (mặc định)", html)
        self.assertIn("Dịch bằng Firefox / Selenium (dự phòng)", html)
        self.assertRegex(html, r'value="extension"\s+checked')
        self.assertNotRegex(html, r'value="firefox"\s+checked')

    def test_setup_page_requires_gui_authentication(self):
        from fastapi.testclient import TestClient
        from myvoice.web import server
        with patch.object(backend, "connection_token", return_value="test-pair-code"), \
                patch.object(server, "_vram", return_value={}), \
                patch.object(server.core, "upload_slots_text", return_value="08:00"):
            client = TestClient(server.app)
            self.assertEqual(client.get("/gemini-extension").status_code, 401)
            self.assertEqual(client.get("/api/gemini-test").status_code, 401)
            client.cookies.set(server.COOKIE, server.TOKEN)
            response = client.get("/gemini-extension")
            self.assertEqual(response.status_code, 200)
            self.assertIn("test-pair-code", response.text)
            self.assertIn("dán đúng mã này vào popup", response.text)   # mã khác mặc định
            self.assertIn('id="ext-test"', response.text)               # khối thử extension
            self.assertIn("🧩", response.text)                           # có tab trên menu
        with patch.object(backend, "connection_token", return_value=backend.DEFAULT_TOKEN), \
                patch.object(server, "_vram", return_value={}), \
                patch.object(server.core, "upload_slots_text", return_value="08:00"):
            html = TestClient(server.app, cookies={server.COOKIE: server.TOKEN}).get("/gemini-extension").text
            self.assertIn(backend.DEFAULT_TOKEN, html)
            self.assertIn("không cần đổi", html)


class ConnectionTokenTests(unittest.TestCase):
    def test_default_token_unless_file_or_environment_overrides(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True), \
                patch.object(backend, "TOKEN_FILE", Path(tmp) / "token"):
            self.assertEqual(backend.connection_token(), backend.DEFAULT_TOKEN)
            self.assertFalse(backend.TOKEN_FILE.exists())      # không tự sinh file nữa
            backend.TOKEN_FILE.write_text(" custom-from-file \n", encoding="utf-8")
            self.assertEqual(backend.connection_token(), "custom-from-file")
            with patch.dict(os.environ, {"OMNI_GEMINI_EXTENSION_TOKEN": "from-env"}):
                self.assertEqual(backend.connection_token(), "from-env")

    def test_browser_tests_never_use_the_real_bridge_port(self):
        """02/10/2026: Playwright bridges on 17863 drove the user's real Chrome (it opened
        Gemini tabs). Every test bridge must pass an explicit test port."""
        import re
        repo = Path(__file__).resolve().parents[2]
        for path in (repo / "Desktop Automation" / "gptcode" / "tests" / "gemini-extension.test.mjs",
                     repo / "myvoice" / "tests" / "gemini_browser_fixture.py"):
            text = path.read_text(encoding="utf-8")
            calls = re.findall(r"ExtensionBridge\(([^)]*)\)", text)
            self.assertTrue(calls, path.name)
            for args in calls:
                self.assertIn("port=", args, f"{path.name}: ExtensionBridge({args})")
        js = (repo / "Desktop Automation" / "gptcode" / "tests" / "gemini-extension.test.mjs").read_text(encoding="utf-8")
        self.assertIn("bridgePort", js)
        self.assertNotRegex(js, r"TEST_PORT = 17863\b")

    def test_extension_files_share_the_default_token(self):
        root = Path(__file__).resolve().parents[2] / "chrome_gemini_extension"
        for name in ("background.js", "popup.js"):
            self.assertIn(f'DEFAULT_TOKEN = "{backend.DEFAULT_TOKEN}"',
                          (root / name).read_text(encoding="utf-8"), name)

    def test_rejected_polls_make_the_connect_error_say_wrong_token(self):
        bridge = ExtensionBridge(port=0, token="right")
        self.addCleanup(bridge.close)
        url = f"http://127.0.0.1:{bridge.server.server_port}/command"
        with self.assertRaises(HTTPError):
            urlopen(Request(url, headers={"Authorization": "Bearer wrong", "X-Client-Id": "c"}), timeout=2)
        with self.assertRaisesRegex(RuntimeError, "SAI mã kết nối"):
            ChromeExtensionDriver("https://gemini.google.com/app", bridge=bridge, connect_timeout=.1)


class ExtensionTestTabTests(unittest.TestCase):
    def setUp(self):
        from myvoice.web import gemini_test
        self.mod = gemini_test
        self.tester = gemini_test.GeminiTester()

    def wait(self):
        self.tester._thread.join(5)
        self.assertFalse(self.tester.running())

    def test_check_forces_the_extension_and_reports_the_tab(self):
        driver = Mock(is_chrome_extension=True, current_url="https://gemini.google.com/app")
        with patch.object(g, "init_firefox", return_value=driver) as opener:
            self.tester.start("check")
            self.wait()
        self.assertEqual(opener.call_args.kwargs["backend"], "extension")
        state = self.tester.state()
        self.assertEqual(state["error"], "")
        self.assertEqual(state["url"], "https://gemini.google.com/app")
        self.assertTrue(any("Chrome đã kết nối" in line for line in state["lines"]), state["lines"])
        driver.quit.assert_called_once_with()

    def test_send_uses_short_prompt_by_default_and_full_prefix_on_request(self):
        driver = Mock(is_chrome_extension=True, current_url="https://gemini.google.com/app")
        answer = "Xin chào, hôm nay thời tiết đẹp. Chúng ta cùng đi dạo công viên nhé."
        with patch.object(g, "init_firefox", return_value=driver), \
                patch.object(g, "send_to_gemini", return_value=answer) as send, \
                patch.object(g, "send_prefix_to_gemini") as prefix:
            self.tester.start("send", "你好")
            self.wait()
            self.assertEqual(self.tester.state()["result"], answer)
            self.assertTrue(send.call_args.args[1].startswith(g.BLANK_RETRY_PROMPT.strip()))
            self.assertTrue(send.call_args.args[1].endswith("\n你好"))
            prefix.assert_not_called()
            self.tester.start("send", "你好", full_prefix=True)
            self.wait()
            prefix.assert_called_once()
            self.assertEqual(prefix.call_args.args[1], g.load_prefix())
            self.assertTrue(send.call_args.args[1].endswith("\n你好"))
            self.assertNotIn(g.BLANK_RETRY_PROMPT.strip(), send.call_args.args[1])
        self.assertEqual(driver.quit.call_count, 2)

    def test_failure_is_reported_in_state(self):
        with patch.object(g, "init_firefox", side_effect=RuntimeError("Chrome Extension chưa kết nối")):
            self.tester.start("check")
            self.wait()
        state = self.tester.state()
        self.assertIn("chưa kết nối", state["error"])
        self.assertTrue(any("❌" in line for line in state["lines"]))

    def test_one_run_at_a_time_and_input_validation(self):
        gate = threading.Event()
        driver = Mock(is_chrome_extension=True, current_url="https://gemini.google.com/app")

        def slow(**_):
            gate.wait(5)
            return driver

        with patch.object(g, "init_firefox", side_effect=slow):
            self.tester.start("check")
            with self.assertRaisesRegex(RuntimeError, "Đang có lượt thử"):
                self.tester.start("check")
            gate.set()
            self.wait()
        with self.assertRaises(ValueError):
            self.tester.start("send", "   ")
        with self.assertRaises(ValueError):
            self.tester.start("bogus")

    def test_api_routes_expose_state_and_validate_input(self):
        from fastapi.testclient import TestClient
        from myvoice.web import server
        client = TestClient(server.app, cookies={server.COOKIE: server.TOKEN})
        with patch.object(self.mod, "tester", self.tester):
            self.assertFalse(client.get("/api/gemini-test").json()["running"])
            resp = client.post("/api/gemini-test/chay", data={"mode": "send", "text": "  "})
            self.assertEqual(resp.status_code, 400)
            self.assertIn("Nhập một đoạn", resp.json()["error"])
            driver = Mock(is_chrome_extension=True, current_url="https://gemini.google.com/app")
            with patch.object(g, "init_firefox", return_value=driver):
                resp = client.post("/api/gemini-test/chay", data={"mode": "check"})
                self.assertEqual(resp.status_code, 200)
                self.wait()
            self.assertEqual(client.get("/api/gemini-test").json()["url"], "https://gemini.google.com/app")


if __name__ == "__main__":
    unittest.main()
