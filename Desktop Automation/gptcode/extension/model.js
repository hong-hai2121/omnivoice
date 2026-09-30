export const TIKTOK_UPLOAD_URL = 'https://www.tiktok.com/tiktokstudio/upload?from=creator_center&tab=video';

export function importQueue(data) {
  const rows = Array.isArray(data) ? data : data.muc;
  if (!Array.isArray(rows)) throw new Error("JSON phai co danh sach muc.");
  return rows.map(row => ({
    id: crypto.randomUUID(),
    tieu_de: String(row.tieu_de || ""),
    hashtag: String(row.hashtag || ""),
    video: String(row.video || ""),
    gio_dang: String(row.gio_dang || ""),
    trang_thai: String(row.trang_thai || "cho"),
    ghi_chu: String(row.ghi_chu || ""),
    variants: Object.fromEntries(Object.entries(row.variants || {}).filter(([key, value]) => ["dai", "nua", "ngan"].includes(key) && typeof value === "string")),
    statusOrigin: row.statusOrigin === "receipt" ? "receipt" : "",
  }));
}

export function validateJob(row, schedule, now = Date.now()) {
  if (!row) throw new Error("Chon mot video.");
  if (!/^(?:[a-z]:[\\/]|\\\\)/i.test(row.video) || !/\.(mp4|mov|webm)$/i.test(row.video)) {
    throw new Error("Can duong dan day du den video tren Windows (mp4, mov, webm).");
  }
  if (schedule) {
    const value = row.gio_dang;
    const date = new Date(value);
    if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value) || !Number.isFinite(+date)) {
      throw new Error("Can ngay va gio dang hop le.");
    }
    if (date.getDate() !== Number(value.slice(8, 10))) throw new Error("Ngay khong ton tai.");
    if (+date < now + 15 * 60_000) throw new Error("Gio dang phai cach hien tai it nhat 15 phut.");
    if (date.getMinutes() % 5) throw new Error("Phut phai la boi so cua 5.");
  }
}

export function isTikTok(url) {
  try {
    const u = new URL(url);
    return u.protocol === "https:" && ["tiktok.com", "www.tiktok.com"].includes(u.hostname);
  } catch { return false; }
}

export function episodeKey(video) {
  const path = String(video || "").trim().replaceAll("/", "\\").toLowerCase();
  return path.includes("\\") ? path.slice(0, path.lastIndexOf("\\")) : "";
}

export function pruneMissingFolders(rows, scan) {
  // Older/failed scans cannot prove that a folder was deleted.
  if (scan?.ok !== true || scan.folders_complete !== true || !Array.isArray(scan.folders) || !scan.root) return 0;
  const normalize = path => String(path).replaceAll("/", "\\").replace(/\\+$/, "").toLowerCase();
  const root = normalize(scan.root);
  if (!/^(?:[a-z]:\\|\\\\)/.test(root + "\\")) return 0;
  if (scan.folders.some(folder => typeof folder !== "string" || !normalize(folder).startsWith(root + "\\"))) return 0;
  const present = new Set(scan.folders.map(normalize));
  let removed = 0;
  for (let index = rows.length - 1; index >= 0; index--) {
    const path = normalize(rows[index].video);
    if (!path.startsWith(root + "\\")) continue;
    const parts = path.slice(root.length + 1).split("\\");
    if (parts.length < 2 || parts.some(part => !part || part === "." || part === "..")) continue;
    if (!present.has(root + "\\" + parts[0])) { rows.splice(index, 1); removed++; }
  }
  return removed;
}

export function mergeScan(rows, incoming, ignored = []) {
  const byFolder = new Map(rows.map(row => [episodeKey(row.video), row]).filter(([key]) => key));
  const excluded = new Set(ignored);
  let added = 0, updated = 0;
  for (const item of incoming) {
    const key = episodeKey(item.video);
    if (!key || excluded.has(key)) continue;
    const current = byFolder.get(key);
    const source = { video: item.video, tieu_de: item.tieu_de, hashtag: item.hashtag };
    if (!current) {
      const row = { ...item, scanSource: source };
      rows.push(row); byFolder.set(key, row); added++;
      continue;
    }
    const before = JSON.stringify(current);
    current.variants = item.variants || {};
    if (["done", "review", "running", "đã đăng", "đã chốt lịch"].includes(current.trang_thai)) {
      if (JSON.stringify(current) !== before) updated++;
      continue;
    }
    for (const field of ["video", "tieu_de", "hashtag"]) {
      if (field === "video" && current.variantChoice) {
        if (item.variants?.[current.variantChoice]) current.video = item.variants[current.variantChoice];
        continue;
      }
      if (!current[field] || current[field] === current.scanSource?.[field] || (field === "video" && !current.scanSource)) current[field] = item[field];
    }
    if (item.trang_thai === "đã đăng" && current.statusOrigin !== "local") {
      current.trang_thai = item.trang_thai; current.ghi_chu = item.ghi_chu; current.statusOrigin = "receipt";
    }
    current.scanSource = source;
    if (JSON.stringify(current) !== before) updated++;
  }
  return { added, updated };
}

export function syncStatuses(rows, source) {
  const legacy = new Map((source?.muc || []).map(row => [episodeKey(row.video), row]));
  let changed = 0;
  for (const row of rows) {
    const saved = legacy.get(episodeKey(row.video));
    if (!saved?.trang_thai || ["local", "receipt"].includes(row.statusOrigin)) continue;
    if (!row.statusOrigin && ["done", "review", "running", "error", "stopped"].includes(row.trang_thai)) continue;
    const note = String(saved.ghi_chu || "");
    if (row.trang_thai !== saved.trang_thai || row.ghi_chu !== note || row.statusOrigin !== "json") changed++;
    row.trang_thai = saved.trang_thai; row.ghi_chu = note; row.statusOrigin = "json";
  }
  return changed;
}

export function videoKind(row) {
  const name = row.video.split(/[\\/]/).at(-1).toLowerCase();
  if (name === "short.mp4") return "ngan";
  if (name.startsWith("full ở ") || name.startsWith("tiktok")) return "nua";
  if (name.startsWith("[full]") || name.startsWith("facebook")) return "dai";
  return "";
}

export function switchVariants(rows, ids, kind, available) {
  const catalog = new Map(available.map(row => [episodeKey(row.video), row]));
  const selected = new Set(ids);
  let changed = 0;
  const missing = [];
  for (const row of rows) {
    if (!selected.has(row.id)) continue;
    const source = catalog.get(episodeKey(row.video));
    const video = source?.variants?.[kind];
    if (!video) { missing.push(row.tieu_de || row.video); continue; }
    if (row.video !== video) changed++;
    row.video = video; row.variantChoice = kind; row.variants = source.variants;
  }
  return { changed, missing };
}

export function statusGroup(row) {
  const value = String(row.trang_thai || "").toLowerCase();
  if (/error|lỗi/.test(value)) return "error";
  if (["done", "đã đăng", "đã chốt lịch"].includes(value)) return "done";
  if (/^đang |^running$/.test(value)) return "running";
  if (["review", "stopped", "đã nạp", "đã điền"].includes(value)) return "review";
  if (row.gio_dang || value === "đã hẹn giờ") return "scheduled";
  return "waiting";
}
