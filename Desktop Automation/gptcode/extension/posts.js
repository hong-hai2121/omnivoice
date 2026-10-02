import { captionText } from './caption.js';
import { NO_VIDEO, statusGroup } from './model.js';
import { episodeNumber } from './schedule.js';

export const postTitle = value => captionText(captionText(value).replace(/#[\p{L}\p{M}\p{N}_]+/gu, ' ')).toLocaleLowerCase('vi');
export function postEpisode(caption) {
  const match = captionText(caption).match(/MimiAudioSo(\d+)|Số\s*(\d+)/i);
  return match ? Number(match[1] || match[2]) : null;
}
const pad = value => String(value).padStart(2, '0');

// TikTok omits the year for near dates; take the candidate closest to now.
export function postDate(when, now = new Date()) {
  if (!when) return '';
  let best = null;
  for (const year of when.year ? [when.year] : [now.getFullYear() - 1, now.getFullYear(), now.getFullYear() + 1]) {
    const date = new Date(year, when.month - 1, when.day, when.hour, when.minute);
    if (date.getMonth() !== when.month - 1 || date.getDate() !== when.day) continue;
    if (!best || Math.abs(date - now) < Math.abs(best - now)) best = date;
  }
  return best ? `${best.getFullYear()}-${pad(best.getMonth() + 1)}-${pad(best.getDate())}T${pad(best.getHours())}:${pad(best.getMinutes())}` : '';
}

// Every dated TikTok post (the newest is "how far the schedule reaches") as anchors for syncSchedule.
export function postAnchors(list, now = new Date()) {
  return (list?.posts || []).map(post => ({ post, stage: postStage(post) })).filter(item => item.stage.kind !== 'pending')
    .map(item => ({ tieu_de: item.post.caption, gio_dang: postDate(item.stage.when, now) })).filter(item => item.gio_dang);
}

/* Judge every row against the TikTok post list (newest first, maybe partially loaded):
   title on TikTok -> scheduled / published; absent -> not posted, unless the list was cut
   before this episode's number range, in which case the row is left as it was. */
export function applyPostList(rows, list, now = new Date()) {
  const result = { scheduled: 0, published: 0, waiting: 0, review: 0, unknown: 0, changedIds: [] };
  if (!Array.isArray(list?.posts)) return result;
  const nowIso = postDate({ year: now.getFullYear(), month: now.getMonth() + 1, day: now.getDate(), hour: now.getHours(), minute: now.getMinutes() }, now);
  const posts = list.posts.map(post => {
    const info = postStage(post), date = postDate(info.when, now);
    // Only a scheduled post can show a future date, even if its alarm icon was not read.
    if (info.kind === 'published' && date > nowIso) info.kind = 'scheduled';
    return { ...post, title: postTitle(post.caption), episode: postEpisode(post.caption), info, date };
  });
  const numbers = posts.map(post => post.episode).filter(value => value !== null);
  const oldest = numbers.length ? Math.min(...numbers) : null;
  const checkedAt = list.readAt || new Date(now).toISOString();
  for (const row of rows) {
    if (statusGroup(row) === 'running') continue;
    const before = JSON.stringify(row);
    const title = postTitle(row.tieu_de), episode = episodeNumber(row);
    const matches = title ? posts.filter(post => post.title === title) : [];
    // A post in the list that is not processing/failed exists on TikTok, even without a date label.
    const live = matches.filter(post => post.info.kind !== 'pending');
    // Untitled rows are scripts without metadata yet; their number alone proves nothing.
    const sameNumber = episode === null || !title ? [] : posts.filter(post => post.episode === episode);
    if (live.length) {
      const post = live.find(item => item.info.kind === 'scheduled') || live[0];
      const scheduled = post.info.kind === 'scheduled';
      row.trang_thai = scheduled ? 'đã lên lịch' : 'đã đăng';
      row.ghi_chu = `TikTok: ${post.stage || row.trang_thai} · ${post.url}` + (matches.length > 1 ? ` · ${matches.length} bài trùng tiêu đề trên TikTok` : '');
      row.statusOrigin = 'tiktok';
      row.postEvidence = { id: post.id, url: post.url, stage: post.stage, kind: scheduled ? 'scheduled' : 'published', source: 'content-list', matchedBy: 'title', checkedAt };
      if (post.date) { row.gio_dang = post.date; row.scheduleKind = 'tiktok'; }
      result[scheduled ? 'scheduled' : 'published']++;
    } else if (matches.length || sameNumber.length) {
      // Processing posts and reused episode numbers need a human look, not a guess.
      const post = matches[0] || sameNumber[0];
      row.trang_thai = 'review';
      row.ghi_chu = matches.length ? `TikTok: ${post.stage || 'chưa rõ trạng thái'} · ${post.url}`
        : `TikTok có bài Số ${episode} nhưng tiêu đề khác: ${captionText(post.caption).slice(0, 90)} · ${post.url}`;
      row.statusOrigin = 'tiktok';
      result.review++;
    } else if (!list.complete && episode !== null && oldest !== null && episode < oldest) {
      result.unknown++;
      continue;
    } else {
      row.trang_thai = row.video ? 'cho' : NO_VIDEO;
      row.ghi_chu = `Chưa thấy trên TikTok (đã đọc ${posts.length} bài)`;
      row.statusOrigin = 'tiktok';
      delete row.postEvidence;
      if (row.scheduleKind === 'tiktok') row.scheduleKind = 'auto';
      result.waiting++;
    }
    if (JSON.stringify(row) !== before) result.changedIds.push(row.id);
  }
  return result;
}
const plain = value => captionText(value).normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[\u0110\u0111]/g, 'd').toLowerCase();

export function postStage(post) {
  const text = plain(post.stage);
  if (/dang (kiem tra|xu ly|tai)|processing|under review|draft|ban nhap|that bai|failed|vi pham|violation|removed|da xoa/.test(text)) return { kind: 'pending' };
  const date = text.match(/\b(\d{1,2}) thang (\d{1,2})(?:,? (\d{4}))?,? (\d{1,2}):(\d{2})(?: (sa|ch))?\b/);
  let when = null;
  if (date && Number(date[1]) >= 1 && Number(date[1]) <= 31 && Number(date[2]) >= 1 && Number(date[2]) <= 12 &&
      Number(date[5]) <= 59 && (date[6] ? Number(date[4]) >= 1 && Number(date[4]) <= 12 : Number(date[4]) <= 23)) {
    let hour = Number(date[4]);
    if (date[6]) hour = hour % 12 + (date[6] === 'ch' ? 12 : 0);
    when = { day: Number(date[1]), month: Number(date[2]), year: date[3] ? Number(date[3]) : null, hour, minute: Number(date[5]) };
  }
  const scheduled = post.icons?.includes('Alarm') || /\b(len lich|scheduled)\b/.test(text);
  return { kind: scheduled ? 'scheduled' : when || /\b(da dang|published|posted)\b/.test(text) ? 'published' : 'unknown', when };
}

export function matchContentPost(posts, { title, schedule, date, excludeIds = [] }) {
  const expected = postTitle(title);
  if (!expected) return { state: 'missing', message: 'Tiêu đề trống, không thể đối chiếu.' };
  const matches = posts.filter(post => postTitle(post.caption) === expected && !excludeIds.includes(post.id));
  if (!matches.length) return { state: 'missing', message: 'Chưa thấy tiêu đề khớp trong các bài đang hiển thị; chưa kết luận đăng thất bại.' };
  if (matches.length !== 1) return { state: 'ambiguous', message: 'Có nhiều bài trùng tiêu đề; cần kiểm tra trên TikTok.' };
  const post = matches[0], stage = postStage(post);
  if (!['scheduled', 'published'].includes(stage.kind)) return { state: 'pending', message: 'Đã thấy tiêu đề nhưng trạng thái bài chưa xác nhận đăng / lên lịch thành công.' };
  if (typeof schedule === 'boolean' && stage.kind !== (schedule ? 'scheduled' : 'published')) return { state: 'mismatch', message: 'Tiêu đề khớp nhưng trạng thái đăng / lên lịch khác yêu cầu.' };
  if (schedule) {
    const target = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(date || '');
    const when = stage.when;
    if (!target || !when || (when.year && when.year !== Number(target[1])) || when.month !== Number(target[2]) ||
        when.day !== Number(target[3]) || when.hour !== Number(target[4]) || when.minute !== Number(target[5])) {
      return { state: 'mismatch', message: 'Tiêu đề khớp nhưng ngày/giờ hiển thị chưa khớp lịch đã chọn.' };
    }
  }
  return { state: 'matched', post: { ...post, kind: stage.kind } };
}
