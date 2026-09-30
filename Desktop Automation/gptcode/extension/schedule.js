import { episodeKey } from "./model.js";

const locked = row => ["done", "review", "running", "đã đăng", "đã chốt lịch"].includes(row.trang_thai);
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
  const folder = episodeKey(row.video).split("\\").at(-1) || "";
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

// JSON and user edits are anchors; only dates generated here may be recalculated.
export function syncSchedule(rows, source, now = new Date()) {
  const result = { restored: 0, assigned: 0, changed: 0, anchor: "", slots: "", notes: [] };
  if (!source || !Array.isArray(source.muc)) return result;
  const before = JSON.stringify(rows);
  const legacy = new Map(source.muc.map(row => [episodeKey(row.video), row]).filter(([key]) => key));
  for (const row of rows) {
    const saved = legacy.get(episodeKey(row.video));
    if (locked(row)) {
      if (!row.gio_dang && parseDate(saved?.gio_dang)) { row.gio_dang = saved.gio_dang; result.restored++; }
      continue;
    }
    if (row.scheduleKind === "manual") continue;
    if (parseDate(saved?.gio_dang) && (!row.gio_dang || ["json", "auto"].includes(row.scheduleKind) || row.gio_dang === saved.gio_dang)) {
      if (row.gio_dang !== saved.gio_dang) result.restored++;
      row.gio_dang = saved.gio_dang; row.scheduleKind = "json";
    }
  }
  // Include JSON rows whose videos are no longer present in the scanned folder.
  const fixed = new Map(legacy);
  for (const row of rows) {
    const key = episodeKey(row.video);
    if (key && (row.scheduleKind !== "auto" || locked(row))) fixed.set(key, row);
  }
  const anchors = [...fixed.values()].filter(row => parseDate(row.gio_dang));
  anchors.sort((a, b) => a.gio_dang.localeCompare(b.gio_dang));
  const anchor = anchors.at(-1);
  let slots;
  try {
    slots = slotsFrom(source.khung_gio || anchor?.gio_dang.slice(11) || "");
  } catch (error) { result.notes.push(error.message); }
  if (!anchor || !slots?.length) {
    result.notes.push(!anchor ? "Chưa có giờ đăng làm mốc trong JSON hoặc danh sách." : "Chưa có khung giờ hợp lệ.");
    result.changed = Number(JSON.stringify(rows) !== before);
    return result;
  }
  result.anchor = anchor.gio_dang;
  result.slots = slots.map(value => `${pad(Math.floor(value / 60))}:${pad(value % 60)}`).join(", ");
  const anchorEpisode = episodeNumber(anchor);
  const ordered = [...rows].sort((a, b) => {
    const left = episodeNumber(a), right = episodeNumber(b);
    return left !== null && right !== null ? left - right : 0;
  });
  const anchorIndex = ordered.findIndex(row => episodeKey(row.video) === episodeKey(anchor.video));
  const candidates = ordered.filter((row, index) => {
    if (locked(row) || row.scheduleKind === "manual" || (row.gio_dang && row.scheduleKind !== "auto")) return false;
    const episode = episodeNumber(row);
    return anchorEpisode !== null && episode !== null ? episode > anchorEpisode : anchorIndex >= 0 && index > anchorIndex;
  });
  const used = new Set(anchors.map(row => row.gio_dang));
  if (used.size !== anchors.length) result.notes.push("Các lịch cố định đang có giờ trùng nhau; cần kiểm tra lại.");
  for (const row of rows) {
    if (row.scheduleKind === "auto" && !locked(row) && !candidates.includes(row) && used.has(row.gio_dang)) {
      row.gio_dang = "";
      result.notes.push(`Tập ${episodeNumber(row) ?? row.id}: bỏ lịch tự sinh bị trùng với mốc mới.`);
    }
  }
  const earliest = +now + 20 * 60_000;
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
