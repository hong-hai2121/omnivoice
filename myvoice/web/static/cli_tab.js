// cli_tab.js — JS của tab 🤖 CLI dịch, DÙNG CHUNG cho web myvoice và web myvideo
// (template myvoice/web/templates/gpt_cli.html nạp file này; myvideo phát nó ở /cli-tab.js).
// Chỉ cần trang phát sự kiện `mv:daluu` sau khi một form tự lưu xong.
// ── Tab 🤖 GPT CLI và ✨ Gemini CLI (web/gptcli_test.py, 29/10/2026) ─────────
//    Hai tab chung template + khối này; #cli-test mang data-nha ("gpt" | "gemini") và
//    mọi lời gọi API kèm ?nha=… để server trả đúng CLI của tab đang mở (26/11/2026).
//    ① thẻ trạng thái: /api/gptcli-info (tìm codex + đăng nhập + model/mức sẽ dùng +
//       cách dịch đang chọn, KHÔNG gọi model) — đọc lúc mở trang và sau mỗi lần ô cài
//       đặt ② tự lưu (sự kiện mv:daluu do khối tự lưu bên dưới phát).
//    ③ nhắn thử: POST /api/gptcli-test/chay rồi hỏi /api/gptcli-test mỗi giây; tin gửi
//       và trả lời hiện kiểu hội thoại (bong bóng), nhật ký + đề bài gấp trong <details>.
(() => {
  const panel = document.getElementById('cli-test');
  if (!panel) return;
  const $ = id => document.getElementById(id);
  const chat = $('cli-chat'), logBox = $('cli-log'), promptBox = $('cli-prompt');
  const status = $('cli-status'), elapsed = $('cli-elapsed');
  const MUC = { low: 'thấp', medium: 'vừa', high: 'cao', xhigh: 'rất cao', max: 'tối đa' };
  const BACKEND = { cli: '🤖 GPT CLI', gemini_cli: '✨ Gemini CLI', firefox: '🦊 Firefox / Selenium',
                    extension: '🧩 Chrome Extension' };
  const NHA = panel.dataset.nha || 'gpt', TEN = panel.dataset.ten || 'GPT CLI';
  const GEMINI = NHA === 'gemini';
  const Q = '?nha=' + NHA;
  const tuChon = GEMINI ? 'agy tự chọn' : 'codex tự chọn';
  let timer = null, cho = null, daThay = 0, moiGui = false;

  function the(id, lop, chinh, phu) {
    const el = $(id);
    el.className = 'cli-stat' + (lop ? ' ' + lop : '');
    el.querySelector('b').textContent = chinh;
    el.querySelector('i').textContent = phu || '';
  }
  const tenMuc = e => e ? (MUC[e] || e) : 'mặc định';

  async function docInfo() {
    try {
      const r = await fetch('/api/gptcli-info' + Q, { credentials: 'same-origin' });
      const s = await r.json();
      if (s.ok) {
        the('st-codex', 'ok', '✅ ' + s.lenh + ' ' + s.version, s.path);
        the('st-login', s.logged_in ? 'ok' : 'warn',
            s.logged_in ? '✅ Đã đăng nhập' : '⚠️ Chưa đăng nhập', s.login);
      } else {
        the('st-codex', 'loi', '❌ Không thấy ' + (GEMINI ? 'agy' : 'codex'), s.error);
        the('st-login', 'warn', '—', GEMINI ? 'cài agy rồi chạy `agy` để đăng nhập Google'
                                            : 'cài codex rồi chạy `codex login`');
      }
      if (GEMINI) the('st-model', '', s.model || tuChon, 'lấy từ: ' + s.model_nguon);
      else the('st-model', '', (s.model || tuChon) + ' · ' + tenMuc(s.effort),
               'model: ' + s.model_nguon + ' · mức: ' + s.effort_nguon);
      const dung = s.backend === s.chon;
      the('st-backend', dung ? 'ok' : 'warn', BACKEND[s.backend] || s.backend,
          dung ? 'dịch / SEO / SRT xếp mới đi qua ' + TEN
               : 'muốn dùng ' + TEN + ' thì chọn ở ô "Dịch mặc định" đầu trang');
    } catch (e) {
      the('st-codex', 'loi', 'Không lấy được trạng thái', String(e));
    }
  }

  function bong(lop, text, meta) {
    const d = document.createElement('div');
    d.className = 'cli-msg ' + lop;
    if (meta) { const m = document.createElement('small'); m.textContent = meta; d.appendChild(m); }
    d.appendChild(document.createTextNode(text));
    const trong = chat.querySelector('.empty');
    if (trong) trong.remove();
    chat.appendChild(d);
    d.scrollIntoView({ block: 'nearest' });
    return d;
  }
  function metaBan(s) {
    return 'Bạn' + (s.mode === 'check' ? ' · 🔌 lệnh thử ngắn' : s.full ? ' · như lúc dịch thật' : '');
  }
  function metaTraLoi(s) {
    const i = s.info || {};
    return TEN + ' · ' + (i.model || 'model ' + tuChon) + (GEMINI ? '' : ' · mức ' + tenMuc(i.effort))
      + (s.elapsed ? ' · trả lời sau ' + Math.round(s.elapsed) + ' s' : '');
  }
  function hienKetQua(s) {
    if (cho) { cho.remove(); cho = null; }
    if (s.error) bong('loi', '❌ ' + s.error, TEN + ' · lỗi');
    else if (s.result) bong('ai', s.result, metaTraLoi(s));
  }

  async function refresh() {
    clearTimeout(timer);
    try {
      const r = await fetch('/api/gptcli-test' + Q, { credentials: 'same-origin' });
      const s = await r.json();
      logBox.textContent = s.lines.length ? s.lines.join('\n') : 'Chưa chạy.';
      promptBox.textContent = s.prompt || '';
      status.textContent = s.running ? '⌛ đang chạy…' : s.error ? '❌ lỗi — xem khối ③'
        : s.finished ? '✅ xong' : '';
      elapsed.textContent = (!s.running && s.finished && s.elapsed)
        ? 'CLI trả lời sau ' + Math.round(s.elapsed) + ' s' : '';
      $('cli-check').disabled = $('cli-send').disabled = Boolean(s.running);
      logBox.scrollTop = logBox.scrollHeight;
      if (moiGui && s.text) {                       // lượt vừa bấm: bong bóng "Bạn" + chờ
        moiGui = false;
        bong('me', s.text, metaBan(s));
        cho = bong('cho', '⌛ ' + TEN + ' đang trả lời…');
      }
      if (s.running) { timer = setTimeout(refresh, 1000); return; }
      if (s.finished && s.finished !== daThay) {    // lượt vừa xong (hoặc lượt cũ khi mới mở trang)
        daThay = s.finished;
        if (!chat.querySelector('.cli-msg.me') && s.text) bong('me', s.text, metaBan(s) + ' · lượt trước');
        hienKetQua(s);
        docInfo();                                  // 🔌 có thể vừa đổi trạng thái đăng nhập / codex
      }
    } catch (e) {
      status.textContent = 'Không lấy được trạng thái: ' + e;
    }
  }
  async function start(mode) {
    const fd = new FormData();
    fd.set('mode', mode);
    fd.set('nha', NHA);
    fd.set('text', $('cli-text').value);
    if ($('cli-full').checked) fd.set('full_prefix', '1');
    status.textContent = '⌛ đang gửi yêu cầu…';
    const resp = await fetch('/api/gptcli-test/chay', { method: 'POST', body: fd, credentials: 'same-origin' });
    const s = await resp.json().catch(() => ({}));
    if (!resp.ok) { status.textContent = '❌ ' + (s.error || ('HTTP ' + resp.status)); return; }
    moiGui = true;
    refresh();
  }

  // Ô chọn model: "Nhập tay…" mới hiện ô gõ tên.
  const sel = $('cli-model'), khac = $('cli-model-khac-field');
  if (sel && khac) sel.addEventListener('change', () => { khac.hidden = sel.value !== '__khac__'; });
  // Ô ② vừa tự lưu xong → đọc lại thẻ "Model · mức" / "Cách dịch" ở ①.
  document.addEventListener('mv:daluu', (e) => {
    const f = e.detail && e.detail.form;
    if (f && f.closest('#cli-caidat, #cli-macdinh')) docInfo();
  });
  $('cli-check').addEventListener('click', () => start('check'));
  $('cli-send').addEventListener('click', () => start('send'));
  docInfo();
  refresh();
})();
