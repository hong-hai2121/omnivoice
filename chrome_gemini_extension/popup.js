// Default pairing code (also in background.js and myvoice/scripts/gemini_backend.py).
const DEFAULT_TOKEN = "omnivoice-gemini-local";
const token = document.querySelector("#token");
const status = document.querySelector("#status");
chrome.storage.local.get(["token", "status", "enabled"]).then(saved => {
  token.value = saved.token || DEFAULT_TOKEN;
  status.textContent = saved.enabled ? (saved.status || "Đang kết nối…") : "Chưa kết nối.";
});
document.querySelector("#connect").addEventListener("click", async () => {
  const value = token.value.trim() || DEFAULT_TOKEN;
  token.value = value;
  await chrome.storage.local.set({token: value, enabled: true, status: "Đang kết nối…"});
  await chrome.runtime.sendMessage({type: "connect"});
});
document.querySelector("#disconnect").addEventListener("click", async () => {
  await chrome.storage.local.set({enabled: false, status: "Đã ngắt kết nối. Công việc đang dịch sẽ dừng khi hết thời gian chờ."});
});
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && changes.status) status.textContent = changes.status.newValue;
});
