import { captionText } from './caption.js';

export const postTitle = value => captionText(captionText(value).replace(/#[\p{L}\p{M}\p{N}_]+/gu, ' ')).toLocaleLowerCase('vi');
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
