"""Invoked by the Playwright test; uses temporary documents and a fake Gemini page."""
import functools
import os
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import dich_gemini as g
from gemini_extension import ChromeExtensionDriver, ExtensionBridge

out = Path(sys.argv[1]) / "gemini_result.docx"
# Test port only (OMNI_TEST_BRIDGE_PORT): 17863 belongs to the real Chrome extension.
bridge = ExtensionBridge(port=int(os.environ["OMNI_TEST_BRIDGE_PORT"]), token="test-extension-token")
print("BRIDGE_READY", flush=True)
driver = ChromeExtensionDriver("https://gemini.google.com/app", bridge=bridge)
print("BROWSER_READY", flush=True)
g.send_to_gemini = functools.partial(g.send_to_gemini, timeout=15, settle=.1)
try:
    chunks = ["你好，今天的天气很好。", "我们一起去公园散步。"]
    results = g.send_chunks_to_gemini(chunks, prefix="Hãy dịch tiếng Trung sang tiếng Việt.",
                                    driver=driver, out_path=out, on_log=print)
    assert len(results) == 2 and all("Một ngày đẹp trời" in result for result in results), results
    assert all("Bản dịch thử nghiệm" not in result for result in results), results
    assert g.read_results_docx(out, 2) == results
    # Resume completed paragraphs must not send any more prompts.
    assert g.send_chunks_to_gemini(chunks, driver=driver, out_path=out, resume=True,
                                   on_log=lambda _: None) == results
    driver.get("https://gemini.google.com/app")
    assert not g._get_responses(driver), "New chat kept stale responses"
    print(json.dumps({"ok": True, "paragraphs": len(results)}), flush=True)
finally:
    driver.quit()
