import { episodeKey, rowKey, LOCKED_STATUSES } from "./model.js";

const locked = row => LOCKED_STATUSES.includes(row.trang_thai);
const pad = value => String(value).padStart(2, "0");
const iso = date => `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;

function parseDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value || "")) return null;
  const date = new Date(value);
  return Number.isFinite(+date) && iso(date) === value ? date : null;
}

export function episodeNumber(row) {
  for (const value of [row.hashtag, row.tieu_de, row.video]) {
    const match = String(value || "").match(/MimiAudioSo(\d+)|Số\s*(\d+)/i);
    if (match) return Number(match[1] || match[2]);
  }
  const folder = rowKey(row).split("\\").at(-1) || "";
  const match = folder.match(/^[a-z]?(\d+)/i);
  return match ? Number(match[1]) : null;
}

function slotsFrom(value) {
  const slots = new Set();
  for (const token of String(value || "").split(/[,;\s]+/).filter(Boolean)) {
    const match = token.match(/^(\d{1,2})[:h.](\d{2})?$/);
    const hour = Number(match?.[1]), minute = Number(match?.[2] || 0);
    if (!match || hour > 23 || minute > 59) throw new Error(`Khung giờ không hợp lệ: ${token}`);
    slots.add(hour * 60 + minute - minute % 5);
  }
  return [...slots].sort((a, b) => a - b);
}

/* The latest time already planned (TikTok posts, posted rows, JSON, manual edits) is the
   anchor; every video not posted yet gets the following free slots, whatever its episode
   number, so a remade old episode (113) also lands in the future. Videos that are ready go
   first, scripts still waiting for their video after them. `posted` holds dated TikTok
   posts as { gio_dang, tieu_de }, including posts whose folder is already gone. */
export function syncSchedule(rows, source, now = new Date(), posted = []) {
  const result = { restored: 0, assigned: 0, changed: 0, anchor: "", anchorFrom: "", slots: "", notes: [] };
  if (!Array.isArray(source?.muc) && !posted.length) return result;
  source = { khung_gio: source?.khung_gio || "", muc: Array.isArray(source?.muc) ? source.muc : [] };
  const before = JSON.stringify(rows);
  const earliest = +now + 20 * 60_000;
  const stale = value => !parseDate(value) || +parseDate(value) < earliest;
  const legacy = new Map(source.muc.map(row => [episodeKey(row.video), row]).filter(([key]) => key));
  for (const row of rows) {
    const saved = legacy.get(rowKey(row));
    if (locked(row)) {
      if (!row.gio_dang && parseDate(saved?.gio_dang)) { row.gio_dang = saved.gio_dang; result.restored++; }
      continue;
    }
    if (row.scheduleKind === "manual") continue;
    // A past plan from the old JSON is not a date for a video that still needs posting.
    if (!stale(saved?.gio_dang) && (!row.gio_dang || ["json", "auto"].includes(row.scheduleKind) || row.gio_dang === saved.gio_dang)) {
      if (row.gio_dang !== saved.gio_dang) result.restored++;
      row.gio_dang = saved.gio_dang; row.scheduleKind = "json";
    }
  }
  const candidates = rows.filter(row => !locked(row) && (row.scheduleKind === "auto" || stale(row.gio_dang)));
  // Include JSON rows whose videos are no longer present in the scanned folder.
  const fixed = new Map(legacy);
  for (const row of rows) {
    const key = rowKey(row);
    if (key && !candidates.includes(row)) fixed.set(key, row);
  }
  const anchors = [...fixed.values()].filter(row => parseDate(row.gio_dang));
  // TikTok can list the same time twice (reposts) or a time a row already holds.
  const taken = new Set(anchors.map(row => row.gio_dang));
  for (const post of posted) {
    if (!parseDate(post.gio_dang) || taken.has(post.gio_dang)) continue;
    taken.add(post.gio_dang);
    anchors.push({ video: "", hashtag: "", tieu_de: String(post.tieu_de || ""), gio_dang: post.gio_dang, fromTikTok: true });
  }
  anchors.sort((a, b) => a.gio_dang.localeCompare(b.gio_dang));
  const anchor = anchors.at(-1);
  let slots;
  try {
    slots = slotsFrom(source.khung_gio || anchor?.gio_dang.slice(11) || "");
  } catch (error) { result.notes.push(error.message); }
  if (!anchor || !slots?.length) {
    result.notes.push(!anchor ? "Chưa có giờ đăng làm mốc trong JSON, TikTok hoặc danh sách." : "Chưa có khung giờ hợp lệ.");
    result.changed = Number(JSON.stringify(rows) !== before);
    return result;
  }
  result.anchor = anchor.gio_dang;
  result.anchorFrom = anchor.fromTikTok || anchor.scheduleKind === "tiktok" ? "tiktok" : "json";
  result.slots = slots.map(value => `${pad(Math.floor(value / 60))}:${pad(value % 60)}`).join(", ");
  const used = new Set(anchors.map(row => row.gio_dang));
  if (used.size !== anchors.length) result.notes.push("Các lịch cố định đang có giờ trùng nhau; cần kiểm tra lại.");
  const order = row => [row.video ? 0 : 1, episodeNumber(row) ?? Infinity];
  candidates.sort((a, b) => { const [x, y] = [order(a), order(b)]; return x[0] - y[0] || x[1] - y[1]; });
  const limit = new Date(now); limit.setDate(limit.getDate() + 30);
  const start = new Date(Math.max(+now, +parseDate(anchor.gio_dang)));
  start.setHours(0, 0, 0, 0);
  const available = [];
  for (let day = new Date(start); day <= limit; day.setDate(day.getDate() + 1)) {
    for (const minutes of slots) {
      const date = new Date(day); date.setHours(Math.floor(minutes / 60), minutes % 60, 0, 0);
      const value = iso(date);
      if (+date >= earliest && date <= limit && value > anchor.gio_dang && !used.has(value)) available.push(value);
    }
  }
  for (const row of candidates) {
    const value = available.shift() || "";
    if (row.gio_dang !== value) { row.gio_dang = value; if (value) result.assigned++; }
    row.scheduleKind = "auto";
  }
  const overflow = candidates.filter(row => !row.gio_dang).length;
  if (overflow) result.notes.push(`${overflow} video chưa có chỗ trong 30 ngày tới.`);
  result.changed = Number(JSON.stringify(rows) !== before);
  return result;
}
