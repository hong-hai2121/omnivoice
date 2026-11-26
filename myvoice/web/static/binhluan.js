// binhluan.js — tab 💬 Bình luận YouTube (web/templates/binhluan.html, 26/11/2026).
// Mọi việc thật nằm ở server (YOUTUBE/binh_luan.QuanLy); file này chỉ:
//   • gửi lệnh: /api/binhluan/tai · traloi · gui · bo · luu
//   • hỏi /api/binhluan mỗi giây KHI còn việc đang chạy rồi vẽ lại.
// Mỗi hàng chỉ dựng lại khi trạng thái của chính nó đổi → ô trả lời đang sửa dở không
// bị vẽ đè mất chữ.
(() => {
  const list = document.getElementById('bl-list');
  if (!list) return;
  const $ = id => document.getElementById(id);
  const BAN = ['xep', 'soan', 'gui'];
  let st = null, timer = null, phien = -1, daVe = new Map(), locCu = null, cheDoCu = null, boQuaCu = null;

  const cheDo = () => (document.querySelector('#bl-chedo input[name=che_do]:checked') || {}).value || 'duyet';
  const anDaTraLoi = () => $('bl-an').checked;
  const boQua = () => $('bl-boqua').checked;

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function nut(cls, text, fn) {
    const b = el('button', cls, text);
    b.type = 'button';
    b.addEventListener('click', fn);
    return b;
  }

  async function goi(duong, data) {
    const fd = new FormData();
    Object.entries(data || {}).forEach(([k, v]) => fd.set(k, v));
    let r, s;
    try {
      r = await fetch(duong, { method: 'POST', body: fd, credentials: 'same-origin' });
      s = await r.json();
    } catch (e) {
      baoLoi('Không gọi được server: ' + e);
      return null;
    }
    if (!r.ok) { baoLoi(s.error || ('HTTP ' + r.status)); return null; }
    baoLoi('');
    ve(s);
    return s;
  }
  function baoLoi(msg) {
    const box = $('bl-loi');
    box.hidden = !msg;
    box.textContent = msg ? '❌ ' + msg : '';
  }

  // ── một hàng bình luận ──
  function chuKy(c) {
    return JSON.stringify([c.tt || '', c.nhap || '', c.loi || '', c.da_tra_loi, c.tra_loi_cua_kenh || '']);
  }
  function dungHang(c) {
    const row = el('div', 'bl-row' + (c.da_tra_loi ? ' xong' : '') + (c.tt === 'loi' ? ' loi' : ''));
    row.dataset.id = c.id;

    const meta = el('div', 'bl-meta');
    meta.appendChild(el('b', '', c.tac_gia || '(ẩn danh)'));
    meta.appendChild(el('span', 'muted small', c.luc + (c.thich ? ' · 👍 ' + c.thich : '')
      + (c.so_tra_loi ? ' · 💬 ' + c.so_tra_loi : '')));
    const a = el('a', 'small', '▶ ' + (c.video || c.video_id || 'video'));
    a.href = 'https://www.youtube.com/watch?v=' + encodeURIComponent(c.video_id) + '&lc=' + encodeURIComponent(c.id);
    a.target = '_blank'; a.rel = 'noopener';
    a.title = 'Mở bình luận này trên YouTube';
    meta.appendChild(a);
    row.appendChild(meta);

    row.appendChild(el('div', 'bl-text', c.noi_dung));

    const tl = el('div', 'bl-reply');
    const act = el('div', 'bl-act');
    const tt = c.tt || '';
    if (c.da_tra_loi) {
      tl.appendChild(el('small', 'bl-nhan ok', tt === 'xong' ? '✅ Vừa gửi trả lời' : '✅ Kênh đã trả lời'));
      tl.appendChild(el('div', 'bl-datl', c.tra_loi_cua_kenh));
      act.appendChild(el('span', 'bl-lydo ok', '✅ Đã trả lời'));
    } else if (tt === 'xep' || tt === 'soan') {
      tl.appendChild(el('div', 'bl-cho', tt === 'xep' ? '⌛ Đang chờ tới lượt Gemini…'
        : '⌛ Gemini CLI đang soạn câu trả lời… (thường 5–30 s)'));
      act.appendChild(el('span', 'bl-lydo', c.che_do === 'tu_dong' ? 'soạn xong sẽ gửi luôn' : 'soạn xong sẽ hiện ra để duyệt'));
    } else if (tt === 'gui') {
      tl.appendChild(el('small', 'bl-nhan', '⌛ Đang gửi lên YouTube…'));
      tl.appendChild(el('div', 'bl-datl', c.nhap));
    } else {
      if (tt === 'loi') tl.appendChild(el('div', 'bl-baoloi', '❌ ' + c.loi));
      if (tt === 'duyet') tl.appendChild(el('small', 'bl-nhan', '✋ Gemini đã soạn — đọc, sửa nếu cần rồi bấm 📤 Gửi'));
      const ta = el('textarea', 'bl-nhap');
      ta.rows = 3;
      ta.value = c.nhap || '';
      ta.placeholder = 'Bấm 🤖 Trả lời để Gemini soạn, hoặc tự gõ câu trả lời rồi bấm 📤 Gửi';
      tl.appendChild(ta);
      const tuDong = cheDo() === 'tu_dong';
      // Chỉ emoji / mốc giờ: Gemini bỏ qua (máy đáp vào là lộ giả) — vẫn tự gõ rồi 📤 Gửi được.
      const khongSoan = c.chi_emoji && boQua() && tt !== 'duyet';
      if (khongSoan) ta.placeholder = 'Chỉ có emoji / mốc giờ — Gemini bỏ qua. Muốn đáp thì tự gõ rồi bấm 📤 Gửi';
      const bTraLoi = nut(tt === 'duyet' ? 'ghost' : 'primary',
        tt === 'duyet' ? '🔁 Soạn lại' : tuDong ? '🤖 Trả lời (gửi luôn)' : '🤖 Trả lời',
        () => goi('/api/binhluan/traloi', { id: c.id, che_do: cheDo() }));
      bTraLoi.title = tuDong ? 'Gemini soạn xong là gửi luôn lên YouTube, không hỏi lại'
        : 'Gemini soạn, câu trả lời hiện ra ở ô bên để bạn duyệt';
      const bGui = nut(tt === 'duyet' ? 'primary' : 'ghost', '📤 Gửi', () => {
        if (!ta.value.trim()) { baoLoi('Ô trả lời của “' + (c.tac_gia || '') + '” đang trống — bấm 🤖 Trả lời để Gemini soạn hoặc tự gõ.'); ta.focus(); return; }
        goi('/api/binhluan/gui', { id: c.id, text: ta.value });
      });
      if (khongSoan) act.appendChild(el('span', 'bl-lydo', '🚫 Gemini bỏ qua: chỉ có emoji / mốc giờ'));
      else act.appendChild(bTraLoi);
      act.appendChild(bGui);
      if (tt === 'duyet' || tt === 'loi')
        act.appendChild(nut('ghost', '✖ Bỏ', () => goi('/api/binhluan/bo', { id: c.id })));
    }
    row.appendChild(tl);
    row.appendChild(act);
    return row;
  }

  // ── vẽ toàn trang theo state ──
  function ve(s) {
    st = s;
    const k = s.kenh || {};
    $('bl-kenh').textContent = k.title ? 'Kênh: ' + k.title + (s.tai_luc ? ' · lấy lúc ' + s.tai_luc : '') : '';
    $('bl-status').textContent = s.dang_tai ? '⌛ đang lấy bình luận…' : '';
    $('bl-tai').disabled = Boolean(s.dang_tai);
    $('bl-tai').textContent = s.tong ? '🔄 Lấy lại bình luận' : '📥 Lấy bình luận';
    const log = $('bl-log');
    log.textContent = s.lines.length ? s.lines.join('\n') : 'Chưa chạy.';
    log.scrollTop = log.scrollHeight;
    if (s.loi) baoLoi(s.loi);

    const tuDong = cheDo() === 'tu_dong';
    const note = $('bl-chedo-note');
    note.textContent = tuDong
      ? '⚡ Đang ở chế độ KHÔNG cần duyệt: bấm 🤖 Trả lời là câu Gemini soạn được đăng công khai dưới tên kênh ngay.'
      : '✋ Đang ở chế độ cần duyệt: không có gì được gửi cho tới khi bạn bấm 📤 Gửi.';
    note.className = 'hint' + (tuDong ? ' bl-canhbao' : '');

    const loc = anDaTraLoi();
    // Bình luận vừa trả lời trong phiên này vẫn hiện (thấy được kết quả) dù đang lọc.
    const hien = s.ds.filter(c => !loc || !c.da_tra_loi || c.tt === 'xong');
    $('bl-dem').textContent = s.tong
      ? s.tong + ' bình luận · ' + s.chua_tra_loi + ' chưa trả lời' + (loc ? ' · đang hiện ' + hien.length : '')
      : '';

    const veLai = s.phien !== phien || loc !== locCu || cheDo() !== cheDoCu || boQua() !== boQuaCu;
    phien = s.phien; locCu = loc; cheDoCu = cheDo(); boQuaCu = boQua();
    // Dựng lại cả bảng (đổi lọc / đổi chế độ / tải lại): giữ chữ đang gõ dở trong các ô trả lời.
    const dangGo = new Map();
    if (veLai) {
      list.querySelectorAll('.bl-row').forEach(r => {
        const ta = r.querySelector('textarea.bl-nhap');
        if (ta && ta.value.trim()) dangGo.set(r.dataset.id, ta.value);
      });
      list.textContent = ''; daVe = new Map();
    }
    if (!hien.length) {
      list.textContent = '';
      daVe = new Map();
      list.appendChild(el('p', 'empty', !s.tong
        ? (s.dang_tai ? '⌛ Đang lấy bình luận…' : 'Chưa lấy danh sách — bấm 📥 Lấy bình luận ở khối 2.')
        : 'Không còn bình luận nào chưa trả lời 🎉 (bỏ tick “Chỉ hiện bình luận kênh CHƯA trả lời” để xem tất cả).'));
    } else {
      const trong = list.querySelector('.empty');
      if (trong) trong.remove();
      const con = new Set(hien.map(c => c.id));
      for (const [id, o] of daVe) if (!con.has(id)) { o.row.remove(); daVe.delete(id); }
      hien.forEach(c => {
        const ck = chuKy(c), o = daVe.get(c.id);
        if (o && o.ck === ck) return;
        const row = dungHang(c);
        const ta = row.querySelector('textarea.bl-nhap');
        if (ta && dangGo.has(c.id)) ta.value = dangGo.get(c.id);
        if (o) o.row.replaceWith(row); else list.appendChild(row);
        daVe.set(c.id, { ck, row });
      });
    }
    clearTimeout(timer);
    if (s.ban) timer = setTimeout(hoi, 1000);
  }
  async function hoi() {
    try {
      const r = await fetch('/api/binhluan', { credentials: 'same-origin' });
      ve(await r.json());
    } catch (e) {
      $('bl-status').textContent = 'Không lấy được trạng thái: ' + e;
      timer = setTimeout(hoi, 3000);
    }
  }

  // ── nút + ô cài đặt (tự lưu) ──
  async function luu(data) {
    const s = await goi('/api/binhluan/luu', data);
    const n = $('bl-luunote');
    if (s && n) { n.textContent = '✓ Đã lưu'; setTimeout(() => { n.textContent = ''; }, 1500); }
  }
  $('bl-tai').addEventListener('click', () => goi('/api/binhluan/tai', { so_luong: $('bl-soluong').value }));
  document.querySelectorAll('#bl-chedo input[name=che_do]').forEach(i =>
    i.addEventListener('change', () => luu({ che_do: cheDo() })));
  $('bl-an').addEventListener('change', () => luu({ an_da_tra_loi: anDaTraLoi() ? '1' : '0' }));
  $('bl-boqua').addEventListener('change', () => luu({ bo_qua_emoji: boQua() ? '1' : '0' }));
  $('bl-soluong').addEventListener('change', () => luu({ so_luong: $('bl-soluong').value }));
  $('bl-huongdan').addEventListener('change', () => luu({ huong_dan: $('bl-huongdan').value }));
  $('bl-hd-macdinh').addEventListener('click', () => {
    $('bl-huongdan').value = $('bl-hd-goc').content.textContent.trim();
    luu({ huong_dan: $('bl-huongdan').value });
  });
  hoi();
})();
