import { importQueue, isTikTok, episodeKey, mergeScan, pruneMissingFolders, syncStatuses, videoKind, switchVariants, statusGroup, TIKTOK_UPLOAD_URL } from "./model.js";
import { syncSchedule, episodeNumber } from "./schedule.js";

const $ = id => document.getElementById(id);
const version = chrome.runtime.getManifest().version;
$("build-version").textContent = "v" + version;
const icons = () => globalThis.lucide?.createIcons();
const compact = matchMedia("(max-width: 700px)");
const adaptPanel = () => { $("scan-source").open = !compact.matches; };
compact.addEventListener("change", adaptPanel); adaptPanel();
const names = { cho: "Chờ", review: "Chờ kiểm tra", done: "Đã xử lý", error: "Lỗi", stopped: "Đã dừng", running: "Đang chạy" };
let rows = [], selected = "", busy = false, selectors = {};
let checkedIds = [];
let scanBusy = false, variantBusy = false, initialized = false, ignoredFolders = [];
let scheduleSource = null;
let scanSettings = { auto: true, kind: "dai", hashtags: "#truyenaudio #truyenfull #audio #fyp" };
let saveChain = Promise.resolve();
const persist = () => {
  const snapshot = structuredClone({ rows, selected, checkedIds, selectors, scanSettings, ignoredFolders });
  saveChain = saveChain.catch(() => {}).then(() => chrome.storage.local.set(snapshot));
  saveChain.catch(showError);
  return saveChain;
};
function showError(error) {
  const message = error.message || String(error);
  $("log").textContent = message;
  $("operation-error").textContent = message;
  $("operation-error").hidden = false;
}
function download(value, filename) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }));
  const a = document.createElement("a"); a.href = url; a.download = filename; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}
function setBusy(value) {
  busy = value;
  const locked = value || variantBusy;
  for (const id of ["import", "add", "inspect", "tab", "schedule", "publish", "select-all", "clear-selection"]) $(id).disabled = locked;
  $("repost").disabled = locked || !$("publish").checked;
  for (const id of ["import", "add"]) $(id).disabled = locked || scanBusy;
  const reason = value ? "Đang xử lý video" : variantBusy ? "Đang đổi phiên bản video" : checkedIds.length === 0 ? "Chưa chọn video" : checkedIds.length > 1 && !$("publish").checked ? `Đang chọn ${checkedIds.length} video; bật Bấm Đăng / Lên lịch để chạy hàng đợi` : "";
  for (const id of ["prepare", "fill"]) { $(id).disabled = !!reason; $(id).title = reason; }
  $("fill").disabled ||= checkedIds.length !== 1;
  $("check-posts").disabled = locked || !checkedIds.length;
  $("action-state").textContent = reason || (checkedIds.length > 1 ? `Sẵn sàng chạy ${checkedIds.length} video` : `Sẵn sàng: ${rows.find(row => row.id === checkedIds[0])?.tieu_de || "video đã chọn"}`);
  for (const id of ["reviewed", "variant-half", "variant-full", "variant-short"]) $(id).disabled = value || scanBusy || checkedIds.length === 0;
  $("stop").disabled = !value;
  for (const id of ["scan", "scan-kind", "scan-hashtags", "auto-scan"]) $(id).disabled = value || scanBusy;
  for (const el of document.querySelectorAll("#rows input, #rows textarea, #rows button, #rows select")) el.disabled = locked || (scanBusy && el.type !== "checkbox");
  for (const el of document.querySelectorAll("#selectors input")) el.disabled = locked;
}
function visibleRows() {
  const query = $("search").value.trim().toLocaleLowerCase("vi");
  const filter = $("status-filter").value;
  return rows.filter(row => (!query || [row.tieu_de, row.hashtag, row.video].join(" ").toLocaleLowerCase("vi").includes(query)) &&
    (filter === "all" || statusGroup(row) === filter));
}
function render() {
  checkedIds = [...new Set(checkedIds)].filter(id => rows.some(row => row.id === id));
  selected = checkedIds[0] || "";
  $("rows").replaceChildren();
  const visible = visibleRows();
  for (const row of visible) {
    const tr = document.createElement("tr");
    tr.dataset.id = row.id;
    tr.classList.toggle("selected", checkedIds.includes(row.id));
    const cell = () => { const td = document.createElement("td"); tr.append(td); return td; };
    const check = document.createElement("input"); check.type = "checkbox";
    check.setAttribute("aria-label", "Chọn " + (row.tieu_de || "video")); check.checked = checkedIds.includes(row.id);
    check.addEventListener("change", () => { checkedIds = check.checked ? [...new Set([...checkedIds, row.id])] : checkedIds.filter(id => id !== row.id); render(); persist(); }); cell().append(check);
    const field = (key, type = "text", multiline = false) => {
      const el = document.createElement(multiline ? "textarea" : "input");
      if (!multiline) el.type = type;
      el.value = row[key]; el.setAttribute("aria-label", { tieu_de: "Tiêu đề", hashtag: "Hashtag", video: "Đường dẫn video", gio_dang: "Giờ đăng" }[key]);
      if (type === "datetime-local") el.step = "300";
      el.addEventListener("input", () => {
        row[key] = el.value;
        if (key === "gio_dang") row.scheduleKind = "manual";
        if (key === "video") row.variantChoice = "manual";
        persist();
      });
      if (key === "gio_dang") el.addEventListener("change", () => { updateSchedule(); persist(); render(); });
      return el;
    };
    const episode = document.createElement("span"); episode.className = "episode";
    episode.textContent = episodeNumber(row) !== null ? `TẬP ${episodeNumber(row)}` : "VIDEO";
    cell().append(episode, field("tieu_de", "text", true), field("hashtag"));
    const variant = document.createElement("select"); variant.className = "video-select"; variant.setAttribute("aria-label", "Phiên bản video");
    for (const [value, title] of [["dai", "Full"], ["nua", "Nửa video"], ["ngan", "Short"]]) variant.add(new Option(title, value));
    const kind = videoKind(row);
    if (!kind) variant.add(new Option("File tùy chọn", ""));
    variant.value = kind;
    variant.addEventListener("change", () => changeVariant(variant.value, [row.id]).catch(showError));
    const details = document.createElement("details"); details.className = "file-detail";
    const filename = document.createElement("summary"); filename.textContent = row.video.split(/[\\/]/).at(-1) || "Đường dẫn video"; filename.title = row.video;
    const path = field("video", "text", true); path.className = "path"; details.append(filename, path);
    cell().append(variant, details);
    cell().append(field("gio_dang", "datetime-local"));
    const group = statusGroup(row);
    const status = document.createElement("span"); status.className = "status " + group;
    const statusIcon = document.createElement("i"); statusIcon.dataset.lucide = ({ error: "circle-alert", done: "circle-check", running: "loader-circle", scheduled: "calendar-clock", review: "eye", waiting: "clock-3" })[group];
    status.append(statusIcon, document.createTextNode(names[row.trang_thai] || row.trang_thai)); status.title = row.ghi_chu;
    const source = document.createElement("span"); source.className = "status-source"; source.textContent = ({ json: "JSON cũ", local: "Extension", receipt: "Biên nhận" })[row.statusOrigin] || "";
    const statusCell = cell(); statusCell.append(status, source);
    if (group === "error" && row.ghi_chu) {
      const note = document.createElement("div"); note.className = "status-note"; note.textContent = row.ghi_chu;
      statusCell.append(note);
    }
    const remove = document.createElement("button"); remove.title = "Xóa dòng"; remove.setAttribute("aria-label", "Xóa dòng");
    const icon = document.createElement("i"); icon.dataset.lucide = "trash-2"; remove.append(icon);
    remove.addEventListener("click", () => {
      const key = episodeKey(row.video);
      if (key && !ignoredFolders.includes(key)) ignoredFolders.push(key);
      rows = rows.filter(item => item.id !== row.id);
      checkedIds = checkedIds.filter(id => id !== row.id);
      render(); persist();
    });
    cell().append(remove); $("rows").append(tr);
  }
  $("empty").hidden = visible.length > 0; $("empty").textContent = rows.length ? "Không có video phù hợp" : "Chưa có video";
  $("count").textContent = visible.length === rows.length ? `${rows.length} video` : `${visible.length} / ${rows.length} video`;
  $("total-count").textContent = rows.length;
  $("scheduled-count").textContent = rows.filter(row => row.gio_dang).length;
  $("done-count").textContent = rows.filter(row => statusGroup(row) === "done").length;
  $("attention-count").textContent = rows.filter(row => ["error", "review"].includes(statusGroup(row))).length;
  const hidden = checkedIds.filter(id => !visible.some(row => row.id === id)).length;
  $("selection-count").textContent = `${checkedIds.length} đã chọn` + (hidden ? ` (${hidden} đang ẩn)` : "");
  $("select-all").checked = visible.length > 0 && visible.every(row => checkedIds.includes(row.id));
  $("select-all").indeterminate = !$("select-all").checked && visible.some(row => checkedIds.includes(row.id));
  icons(); setBusy(busy);
}
async function refreshTabs() {
  const previous = $("tab").value;
  const tabs = (await chrome.tabs.query({})).filter(tab => isTikTok(tab.url) && /\/(tiktokstudio\/(upload|content)|creator-center\/upload)\/?$/.test(new URL(tab.url).pathname));
  $("tab").replaceChildren();
  for (const tab of tabs) $("tab").add(new Option(`${tab.title} (#${tab.id})`, tab.id));
  if (tabs.some(tab => String(tab.id) === previous)) $("tab").value = previous;
  $("connection-status").textContent = tabs.length ? tabs.length + " tab Studio" : "Chưa có tab Studio";
}
function progress(value, restored = false) {
  if (!value) return;
  const history = restored ? `Lần chạy trước · bản ${value.version || "không rõ"}` : "";
  $("operation-error").hidden = value.status !== "error";
  $("operation-error").textContent = value.status === "error" ? [history, value.log.at(-1)].filter(Boolean).join("\n") : "";
  $("state").textContent = (restored ? "Lần chạy trước: " : "") + (names[value.status] || value.status);
  $("log").textContent = [history, ...value.log].filter(Boolean).join("\n");
  $("log").scrollTop = $("log").scrollHeight;
  const row = rows.find(item => item.id === value.rowId);
  if (row) { row.trang_thai = value.status; row.ghi_chu = value.log.at(-1) || ""; row.statusOrigin = "local"; persist(); render(); }
}
async function execute(type) {
  if (busy || variantBusy) return;
  if (!$("tab").value) throw new Error("Mở tab TikTok Studio trong profile này.");
  if (!["inspect", "checkPosts"].includes(type) && checkedIds.length !== 1 && !(type === "prepare" && $("publish").checked && checkedIds.length)) throw new Error("Chạy nhiều video cần bật Bấm Đăng / Lên lịch.");
  const row = rows.find(item => item.id === checkedIds[0]);
  if (type !== "inspect" && !row) throw new Error("Chọn một video.");
  setBusy(true);
  $("operation-error").hidden = true;
  $("operation-error").textContent = "";
  $("state").textContent = "Đang bắt đầu";
  $("log").textContent = `${new Date().toLocaleTimeString("vi-VN")}  Bắt đầu thao tác · v${version}`;
  try {
    await persist();
    const request = structuredClone({ type, tabId: Number($("tab").value), row,
      rows: ["prepare", "checkPosts"].includes(type) ? rows.filter(item => checkedIds.includes(item.id)) : undefined,
      publish: !["inspect", "checkPosts"].includes(type) && $("publish").checked, schedule: $("schedule").checked, selectors });
    if (request.publish && $("repost").checked) {
      $("repost").checked = false;
      const { submissions = {} } = await chrome.storage.local.get("submissions");
      const selectedRows = request.rows || [request.row];
      const existing = selectedRows.filter(item => submissions[episodeKey(item.video) || item.video.toLowerCase()]);
      if (existing.length) {
        const details = existing.map(item => `${item.tieu_de || item.video}\n${item.video}\nLịch mới: ${request.schedule ? item.gio_dang.replace("T", " ") : "Đăng ngay"}`).join("\n\n");
        if (!confirm(`Đăng lại ${existing.length} video đã từng bấm Đăng / Lên lịch?\n\n${details}\n\nVideo có thể đã được đăng hoặc lên lịch. Tiếp tục có thể tạo bài trùng. Biên nhận cũ vẫn được giữ.`)) {
          $("state").textContent = "Đã hủy"; $("log").textContent = "Đã hủy yêu cầu đăng lại. Chưa thao tác trên TikTok.";
          return;
        }
        request.repostReceipts = Object.fromEntries(existing.map(item => {
          const key = episodeKey(item.video) || item.video.toLowerCase();
          return [key, submissions[key]];
        }));
      }
    }
    const response = await chrome.runtime.sendMessage(request);
    if (!response?.ok) throw new Error(response?.error || "Mất kết nối extension.");
    if (response.diagnostic) download(response.diagnostic, "tiktok-dom.json");
  } finally { setBusy(false); }
}
function updateSchedule() {
  const result = syncSchedule(rows, scheduleSource);
  $("schedule-status").textContent = result.anchor
    ? `Mốc cuối: ${result.anchor.replace("T", " ")} · Khung giờ: ${result.slots} · Lấy từ danh_sach.json`
    : (result.notes[0] || "Chưa đọc lịch từ danh_sach.json.");
  if (result.anchor && result.notes.length) $("schedule-status").textContent += " · " + result.notes.join("; ");
  return result;
}
async function fetchScan(kind) {
  const params = new URLSearchParams({ kind, hashtags: scanSettings.hashtags });
  let response;
  try {
    response = await fetch(`http://127.0.0.1:8771/api/scan?${params}`, {
      headers: { "X-Omni": "gptcode-scanner" }, signal: AbortSignal.timeout(15_000), cache: "no-store",
    });
  } catch { throw new Error("Chưa kết nối bộ quét. Chạy gptcode\\chay_quet.py rồi bấm Quét kịch_bản."); }
  const data = await response.json();
  if (!response.ok || !data.ok) throw new Error(data.error || "Không quét được thư mục.");
  return data;
}
async function changeVariant(kind, ids = checkedIds) {
  if (busy || scanBusy || !ids.length || !["dai", "nua", "ngan"].includes(kind)) return;
  scanBusy = true; variantBusy = true; setBusy(busy);
  try {
    const data = await fetchScan(kind);
    const result = switchVariants(rows, ids, kind, importQueue(data));
    await persist();
    const name = ({ dai: "full", nua: "nửa video", ngan: "short" })[kind];
    $("log").textContent = `Đã đổi ${result.changed} video sang bản ${name}.`;
    if (result.missing.length) $("log").textContent += `\nKhông có bản ${name}:\n` + result.missing.join("\n");
  } finally { scanBusy = false; variantBusy = false; render(); }
}
async function scan(manual = false) {
  if (busy || scanBusy) return;
  if (!manual && (!scanSettings.auto || document.activeElement?.closest("#rows, .scan-tools"))) return;
  scanBusy = true; setBusy(busy);
  $("scan-status").textContent = "Đang quét kịch_bản...";
  try {
    const data = await fetchScan(scanSettings.kind);
    // Do not mutate the queue if an upload started or the user began editing during fetch.
    if (busy || (!manual && document.activeElement?.closest("#rows"))) {
      $("scan-status").textContent = "Chờ hoàn tất thao tác để cập nhật danh sách."; return;
    }
    if (manual) ignoredFolders = [];
    const removed = pruneMissingFolders(rows, data);
    checkedIds = checkedIds.filter(id => rows.some(row => row.id === id));
    selected = checkedIds[0] || "";
    const result = mergeScan(rows, importQueue(data), ignoredFolders);
    scheduleSource = data.schedule || null;
    const statusChanges = syncStatuses(rows, scheduleSource);
    const scheduling = updateSchedule();
    if (removed || result.added || result.updated || scheduling.changed || statusChanges || manual) { await persist(); render(); }
    $("scan-status").textContent = `${data.muc.length} video · thêm ${result.added} · cập nhật ${result.updated} · ${new Date().toLocaleTimeString("vi-VN")} · ${data.root}`;
    if (removed) $("scan-status").textContent += ` · bỏ ${removed} dòng có thư mục đã xóa`;
    if (data.folders_complete === undefined) $("scan-status").textContent += " · Khởi động lại chay_quet.py để đồng bộ thư mục đã xóa";
    if (scheduling.restored || scheduling.assigned) $("scan-status").textContent += ` · lấy lại ${scheduling.restored} lịch · xếp mới ${scheduling.assigned} lịch`;
    if (data.ghi_chu?.length) $("scan-status").textContent += " · " + data.ghi_chu.join("; ");
  } catch (error) { $("scan-status").textContent = error.message; }
  finally { scanBusy = false; setBusy(busy); }
}
function on(id, fn) { $(id).addEventListener("click", () => Promise.resolve().then(fn).catch(showError)); }
on("scan", () => scan(true));
on("clear-selection", () => { checkedIds = []; render(); persist(); });
on("variant-half", () => changeVariant("nua"));
on("variant-full", () => changeVariant("dai"));
on("variant-short", () => changeVariant("ngan"));
$("search").addEventListener("input", render);
$("status-filter").addEventListener("change", render);
$("select-all").addEventListener("change", () => {
  const ids = visibleRows().map(row => row.id);
  checkedIds = $("select-all").checked ? [...new Set([...checkedIds, ...ids])] : checkedIds.filter(id => !ids.includes(id));
  render(); persist();
});
for (const id of ["scan-kind", "scan-hashtags", "auto-scan"]) {
  $(id).addEventListener("change", () => {
    scanSettings = { auto: $("auto-scan").checked, kind: $("scan-kind").value, hashtags: $("scan-hashtags").value.trim() };
    persist();
    if (scanSettings.auto || id === "scan-kind") scan(true);
  });
}
on("refresh", refreshTabs);
$("publish").addEventListener("change", () => { if (!$("publish").checked) $("repost").checked = false; setBusy(busy); });
on("popout", () => chrome.windows.create({ url: chrome.runtime.getURL("dashboard.html"), type: "popup", width: 1080, height: 820 }));
on("last-diagnostic", async () => {
  const { lastDiagnostic } = await chrome.storage.local.get("lastDiagnostic");
  if (!lastDiagnostic) throw new Error("Chưa có chẩn đoán lỗi đã lưu.");
  download(lastDiagnostic, "tiktok-dom-error.json");
});
on("receipts", async () => download((await chrome.storage.local.get("submissions")).submissions || {}, "tiktok-bien-nhan.json"));
on("open", async () => { await chrome.tabs.create({ url: TIKTOK_UPLOAD_URL, active: false }); await refreshTabs(); });
on("import", () => $("json-file").click());
on("export", () => download({ muc: rows }, "danh_sach_extension.json"));
on("add", () => { const row = importQueue([{}])[0]; rows.push(row); checkedIds = [row.id]; $("search").value = ""; $("status-filter").value = "all"; render(); persist(); });
on("prepare", () => execute("prepare"));
on("fill", () => execute("fill"));
on("check-posts", () => execute("checkPosts"));
on("inspect", () => execute("inspect"));
on("stop", () => chrome.runtime.sendMessage({ type: "stop" }));
on("reviewed", async () => {
  const { rowResults = {} } = await chrome.storage.local.get("rowResults");
  for (const row of rows.filter(item => checkedIds.includes(item.id))) {
    row.trang_thai = "done"; row.ghi_chu = "Người dùng đánh dấu đã xử lý"; row.statusOrigin = "local";
    rowResults[row.id] = { trang_thai: row.trang_thai, ghi_chu: row.ghi_chu, statusOrigin: "local" };
  }
  await chrome.storage.local.set({ rowResults }); persist(); render();
});
$("json-file").addEventListener("change", async event => {
  try {
    const file = event.target.files[0]; if (!file) return;
    const data = JSON.parse(await file.text());
    const incoming = importQueue(data);
    const known = new Map(rows.filter(row => row.video).map(row => [episodeKey(row.video), row]));
    const added = incoming.filter(row => {
      const key = episodeKey(row.video), existing = known.get(key);
      if (key && existing) {
        if ((!existing.gio_dang || existing.scheduleKind === "auto") && row.gio_dang) { existing.gio_dang = row.gio_dang; existing.scheduleKind = "json"; }
        return false;
      }
      known.set(key, row); return true;
    });
    rows.push(...added); syncStatuses(rows, { muc: incoming });
    await persist(); render();
    $("log").textContent = `Đã thêm ${added.length} video.`;
  } catch (error) { showError(error); } finally { event.target.value = ""; }
});
for (const input of document.querySelectorAll("[data-key]")) {
  input.addEventListener("change", () => { selectors[input.dataset.key] = input.value.trim(); persist(); });
}
chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== "local") return;
  if (changes.progress) { progress(changes.progress.newValue); if (changes.progress.newValue?.status === "running") setBusy(true); }
  if (changes.rowResults?.newValue) {
    for (const row of rows) Object.assign(row, changes.rowResults.newValue?.[row.id] || {});
    render(); persist();
  }
});
async function init() {
  const saved = await chrome.storage.local.get(["rows", "selected", "checkedIds", "selectors", "progress", "scanSettings", "ignoredFolders", "rowResults"]);
  rows = saved.rows || []; selected = saved.selected || rows[0]?.id || ""; selectors = saved.selectors || {};
  for (const row of rows) Object.assign(row, saved.rowResults?.[row.id] || {});
  checkedIds = saved.checkedIds || (saved.selected ? [saved.selected] : []);
  scanSettings = { ...scanSettings, ...saved.scanSettings }; ignoredFolders = saved.ignoredFolders || [];
  $("auto-scan").checked = scanSettings.auto; $("scan-kind").value = scanSettings.kind; $("scan-hashtags").value = scanSettings.hashtags;
  for (const input of document.querySelectorAll("[data-key]")) input.value = selectors[input.dataset.key] || "";
  const status = await chrome.runtime.sendMessage({ type: "status" });
  busy = status.running;
  if (saved.progress?.status === "running" && !busy) {
    saved.progress.status = "stopped";
    saved.progress.log.push("Phiên trước đã gián đoạn. Kiểm tra bản nháp trên TikTok trước khi tiếp tục.");
  }
  render(); progress(saved.progress, !busy); await refreshTabs();
  initialized = true; await scan();
}
init().catch(showError);
setInterval(() => { if (initialized) scan(); }, 30_000);
setInterval(async () => {
  if (!busy) return;
  try {
    const status = await chrome.runtime.sendMessage({ type: "status" });
    if (!status.running) setBusy(false);
  } catch { setBusy(false); }
}, 1500);
