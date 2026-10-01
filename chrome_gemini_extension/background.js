/* The bridge delivers a command once. Persist receipt BEFORE browser effects;
 * after a worker restart an uncertain command fails instead of being replayed. */
// The application listens on 17863. "bridgePort" in storage is set ONLY by the automated
// tests, so their throwaway bridges never reach the real Chrome profile (02/10/2026:
// test runs on 17863 opened Gemini tabs in the user's browser).
const BRIDGE_PORT = 17863;
const bridgeUrl = settings => `http://127.0.0.1:${settings.bridgePort || BRIDGE_PORT}`;
// Default pairing code (also in popup.js and myvoice/scripts/gemini_backend.py):
// the bridge only listens on loopback, so a fixed code is accepted by the owner.
const DEFAULT_TOKEN = "omnivoice-gemini-local";
const POLL_MS = 750;        // while the GUI is running a job
const POLL_IDLE_MAX_MS = 5000;  // backed off while no application listens
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
let polling = false;
let delay = POLL_MS;
let timer;

async function request(settings, path, token, body) {
  const clientId = settings.clientId;
  const response = await fetch(bridgeUrl(settings) + path, {
    method: body ? "POST" : "GET",
    headers: {Authorization: `Bearer ${token}`,
      "X-Client-Id": clientId, ...(body ? {"Content-Type": "application/json"} : {})},
    ...(body ? {body: JSON.stringify(body)} : {}),
    signal: AbortSignal.timeout(4000), cache: "no-store"
  });
  return {response, data: await response.json()};
}

async function api(path, settings, body) {
  let {response, data} = await request(settings, path, settings.token, body);
  if (response.status === 403 && settings.token !== DEFAULT_TOKEN) {
    // A code pasted by mistake (e.g. the web page's ?token=) or kept from an older
    // version: try the fixed default once and keep it if the application accepts it.
    // A rejected request was never processed, so repeating it cannot send twice.
    const retry = await request(settings, path, DEFAULT_TOKEN, body);
    if (retry.response.status !== 403) {
      settings.token = DEFAULT_TOKEN;
      await chrome.storage.local.set({token: DEFAULT_TOKEN});
      ({response, data} = retry);
    }
  }
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}

async function content(tabId, command) {
  return chrome.tabs.sendMessage(tabId, {source: "omnivoice", ...command});
}

async function execute(command) {
  if (Date.now() / 1000 >= command.expires) throw new Error("Lệnh đã hết hạn.");
  let {tabId, tabSession} = await chrome.storage.session.get(["tabId", "tabSession"]);
  if (command.action === "navigate") {
    const url = new URL(command.url);
    if (url.origin !== "https://gemini.google.com") throw new Error("Địa chỉ Gemini không hợp lệ.");
    // ONE working tab for every job (02/10/2026). The web queue runs each episode in
    // its own Python process, i.e. a new session per episode; opening a tab per session
    // piled up one heavy Gemini tab per episode. A new session now reuses the tab this
    // extension opened before and starts a fresh chat in it; the finished chat stays in
    // Gemini's history (sidebar). The tab is reused only while it is still on Gemini:
    // if the user took it elsewhere it is left alone and a new tab is opened.
    if (tabId !== undefined) {
      try {
        const old = await chrome.tabs.get(tabId);
        if (!old.url?.startsWith("https://gemini.google.com/")) tabId = undefined;
      } catch { tabId = undefined; }
    }
    if (tabId === undefined) {
      const tab = await chrome.tabs.create({url: command.url, active: true});
      tabId = tab.id;
    } else {
      // A reload is needed even when /app is the current SPA address.
      await chrome.tabs.update(tabId, {url: command.url, active: true});
    }
    await chrome.storage.session.set({tabId, tabSession: command.session});
    await sleep(700);
    const deadline = Math.min(Date.now() + 45000, command.expires * 1000);
    while (Date.now() < deadline) {
      const tab = await chrome.tabs.get(tabId);
      if (tab.status === "complete" && tab.url?.startsWith("https://gemini.google.com/")) {
        try {
          const result = await content(tabId, {action: "ready"});
          if (result?.value?.ready) return {url: tab.url};
        } catch { /* Content script still loading. */ }
      }
      await sleep(500);
    }
    throw new Error("Chưa thấy ô nhập Gemini. Hãy đăng nhập Google trong tab Gemini rồi chạy lại.");
  }
  if (tabSession !== command.session || tabId === undefined) {
    throw new Error("Mất phiên Gemini. Hãy chạy tiếp công việc từ GUI.");
  }
  const tab = await chrome.tabs.get(tabId);
  if (!tab.url?.startsWith("https://gemini.google.com/")) {
    throw new Error("Tab dịch không còn ở Gemini. Hãy đăng nhập rồi chạy tiếp.");
  }
  if (command.action === "status") return {url: tab.url};
  if (!["responses", "submit"].includes(command.action)) throw new Error("Lệnh không hỗ trợ.");
  const result = await content(tabId, command);
  if (!result || result.error) throw new Error(result?.error || "Tab Gemini không phản hồi.");
  return result.value;
}

async function poll() {
  if (polling) return;
  polling = true;
  clearTimeout(timer);
  let enabled = false;
  try {
    const settings = await chrome.storage.local.get(["enabled", "token", "clientId", "bridgePort"]);
    enabled = Boolean(settings.enabled && settings.token);
    if (!enabled) return;
    if (!settings.clientId) {
      settings.clientId = crypto.randomUUID();
      await chrome.storage.local.set({clientId: settings.clientId});
    }
    const {pending} = await chrome.storage.session.get("pending");
    // A report may have been lost after the browser already submitted the text.
    // It is safe to retry a report, never the submit itself.
    if (pending) {
      try {
        await api("/result", settings, pending.result || {
          session: pending.session, id: pending.id,
          error: "Extension khởi động lại khi đang thao tác. Đã dừng để tránh gửi trùng; kiểm tra chat rồi chạy tiếp."
        });
      } catch (error) {
        // Python may already have accepted the report or started a new session.
        if (!["Lệnh đã hết hạn", "Client không sở hữu phiên"].includes(error.message)) throw error;
      }
      await chrome.storage.session.remove("pending");
    }
    const {session, command} = await api("/command", settings);
    delay = POLL_MS;
    if (command) {
      await chrome.storage.session.set({pending: {session, id: command.id}});
      let result;
      try { result = {session, id: command.id, value: await execute(command)}; }
      catch (error) { result = {session, id: command.id, error: error.message}; }
      await chrome.storage.session.set({pending: {session, id: command.id, result}});
      await api("/result", settings, result);
      await chrome.storage.session.remove("pending");
      await chrome.storage.local.set({status: result.error || "Đã kết nối · đang xử lý yêu cầu từ GUI"});
    } else {
      await chrome.storage.local.set({status: "Đã kết nối · chờ yêu cầu từ GUI"});
    }
  } catch (error) {
    const offline = error.message === "Failed to fetch" || error.name === "TimeoutError";
    await chrome.storage.local.set({status: offline
      ? "Đang chờ ứng dụng. Bấm Dịch trong GUI (cách dịch Chrome Extension là mặc định)."
      : error.message});
    // No application is listening: slow down instead of hammering the loopback port.
    if (offline) delay = Math.min(delay * 2, POLL_IDLE_MAX_MS);
    // A stale report is rejected with 409 after its Python command timed out.
    if (error.message === "Lệnh đã hết hạn") await chrome.storage.session.remove("pending");
  } finally {
    polling = false;
    if (enabled) timer = setTimeout(poll, delay);
  }
}

async function wake() {
  await chrome.alarms.create("bridge", {periodInMinutes: 0.5});
  void poll();
}
async function install() {
  // First install: connect with the default code right away, no popup step needed.
  // A saved token (custom or after Disconnect) is left untouched.
  const saved = await chrome.storage.local.get(["token", "enabled"]);
  if (!saved.token) {
    await chrome.storage.local.set({token: DEFAULT_TOKEN, enabled: true, status: "Đang kết nối…"});
  }
  await wake();
}
chrome.runtime.onInstalled.addListener(install);
chrome.runtime.onStartup.addListener(wake);
chrome.alarms.onAlarm.addListener(alarm => { if (alarm.name === "bridge") void poll(); });
chrome.runtime.onMessage.addListener(message => {
  if (message.type === "connect") { delay = POLL_MS; void wake(); }
});
void wake();
