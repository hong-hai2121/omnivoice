// Nút 📋 Copy của trang SEO, và khối Nguồn (thêm/xoá/chọn file).
// Không có thư viện ngoài nào ngoài htmx.

(function () {
  document.addEventListener('click', async (e) => {
    const btn = e.target.closest('[data-copy]');
    if (!btn) return;
    const el = document.getElementById(btn.dataset.copy);
    if (!el) return;
    const done = (ok) => {
      const old = btn.textContent;
      btn.textContent = ok ? '✅ Đã copy' : '⚠️ Không copy được';
      setTimeout(() => { btn.textContent = old; }, 1500);
    };
    try {
      await navigator.clipboard.writeText(el.textContent);
      done(true);
    } catch (_) {
      // Trình duyệt chặn clipboard khi không phải HTTPS → bôi đen sẵn để Ctrl+C.
      const range = document.createRange();
      range.selectNodeContents(el);
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      done(false);
    }
  });
})();


// ── Home: bấm BẤT KỲ nút chạy nào là LƯU HẾT các khối cài đặt trên trang ─────
// Home ghép 4 form riêng (quy trình · giọng nói & video · thumbnail · đăng), mà
// trình duyệt chỉ gửi form chứa nút vừa bấm: sửa "Tăng tốc" bên khối Giọng nói
// rồi bấm 🎙 Nhận diện là giá trị mới KHÔNG được ghi ra file — chuỗi tự chạy tới
// bước dựng video vẫn dùng tốc độ cũ, tải lại trang thì ô quay về số cũ. Nên khi
// MỘT form trong bốn form gửi đi, gom dữ liệu ba form còn lại gửi vào đúng đường
// 💾 của từng khối (ngữ nghĩa y hệt tự tay bấm 💾), xong xuôi mới cho chạy thật.
// Nút 💾 htmx không qua đây (htmx tự gửi, không có sự kiện submit) — mỗi nút 💾
// vẫn chỉ lưu đúng khối của nó như nhãn ghi. Form hàng đợi/🌙 không nằm trong
// danh sách nên không bị đụng.
(function () {
  // [selector của form, đường 💾 của CHÍNH khối đó]
  const FORMS = [
    ['form[action="/kichban/chay"]', '/kichban/luu'],
    ['#voiceform', '/giongnoi/luu'],
    ['form[action="/thumbnail"]', '/thumbnail/luu'],
    ['form[action="/dangyoutube/luu"]', '/dangyoutube/luu'],
  ];

  document.addEventListener('submit', (e) => {
    const form = e.target;
    if (form.dataset.daLuu) { delete form.dataset.daLuu; return; }   // lượt gửi thật
    const me = FORMS.findIndex(([sel]) => form.matches(sel));
    if (me < 0) return;                // form ngoài danh sách (hàng đợi…): kệ nó
    const others = FORMS
      .filter((_, i) => i !== me)      // khối đang gửi tự lưu trong handler của nó
      .map(([sel, url]) => [document.querySelector(sel), url])
      .filter(([f]) => f);
    if (!others.length) return;        // trang riêng: chỉ có mỗi form này
    e.preventDefault();
    const submitter = e.submitter;     // giữ nút vừa bấm (start=… / formaction)
    // Chờ lưu xong hết mới gửi thật — gửi ngay thì trang unload, fetch bị huỷ.
    // Có khối lưu hỏng vẫn chạy tiếp: việc chạy quan trọng hơn việc nhớ cài đặt.
    Promise.allSettled(others.map(([f, url]) =>
      fetch(url, { method: 'POST', body: new FormData(f),
                   credentials: 'same-origin', redirect: 'manual' })
    )).then(() => {
      form.dataset.daLuu = '1';
      form.requestSubmit(submitter || undefined);
    });
  });
})();


// ── Khối Nguồn: ✕ xoá ô nhập · chip "Gần đây" · 📂 chọn file từ thư mục tải về ──
// Trình duyệt KHÔNG cho biết đường dẫn thật của file khi dùng <input type=file>
// (chỉ trả "C:\fakepath\..."), mà pipeline lại cần đường dẫn thật để chạy. Nên
// danh sách file do server đọc từ đĩa rồi trả về (/api/tep-nguon) — server chỉ
// chạy trên 127.0.0.1 nên đó cũng chính là máy đang ngồi.
(function () {
  const box = () => document.getElementById('srcBox');

  /** Thêm một dòng vào ô Nguồn, bỏ qua nếu đã có sẵn dòng y hệt. */
  function addSource(text) {
    const el = box();
    if (!el || !text) return false;
    const lines = el.value.split('\n').map((s) => s.trim()).filter(Boolean);
    if (lines.includes(text)) return false;
    lines.push(text);
    el.value = lines.join('\n') + '\n';
    el.scrollTop = el.scrollHeight;
    // Báo như người gõ: khối "Ô Nguồn dùng chung" bên dưới bắt sự kiện này để lưu
    // lên server + chép sang các ô Nguồn khác (trang Nhận diện, tab khác).
    el.dispatchEvent(new Event('input', { bubbles: true }));
    return true;
  }

  document.addEventListener('click', (e) => {
    const chip = e.target.closest('.chip[data-src]');
    if (chip) {
      e.preventDefault();
      flash(chip, addSource(chip.dataset.src) ? '✓ đã thêm' : 'đã có rồi');
      return;
    }
    if (e.target.closest('#srcClear')) {
      const el = box();
      // Đã gõ gì đó mới hỏi — ô trống mà cũng bật hộp thoại thì phiền.
      if (el && el.value.trim() && confirm('Xoá hết nội dung ô Nguồn?')) {
        el.value = '';
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.focus();
      }
      return;
    }
    if (e.target.closest('#srcForget')) {
      if (confirm('Quên danh sách nguồn gần đây? (ô nhập giữ nguyên)')) forget();
      return;
    }
    if (e.target.closest('#srcAdd')) openPicker();
  });

  async function forget() {
    try {
      await fetch('/kichban/xoalichsu', { method: 'POST', credentials: 'same-origin' });
      document.querySelector('.chiprow')?.remove();
    } catch (_) {
      alert('Không xoá được — server còn chạy không?');
    }
  }

  function flash(btn, msg) {
    const old = btn.textContent;
    btn.textContent = msg;
    btn.classList.add('chip-hit');
    setTimeout(() => { btn.textContent = old; btn.classList.remove('chip-hit'); }, 900);
  }

  // ── Bảng chọn file ────────────────────────────────────────────────────────
  let dlg = null;

  function closePicker() {
    if (dlg) { dlg.remove(); dlg = null; }
    document.removeEventListener('keydown', onEsc);
  }
  function onEsc(e) { if (e.key === 'Escape') closePicker(); }

  async function openPicker() {
    closePicker();
    dlg = document.createElement('div');
    dlg.className = 'modal';
    dlg.innerHTML = `
      <div class="modal-card">
        <div class="modal-head">
          <b>Chọn file từ máy</b>
          <input class="modal-find" type="text" placeholder="Lọc theo tên…" autofocus>
          <button type="button" class="small modal-x">✕</button>
        </div>
        <div class="modal-body"><p class="hint">Đang đọc thư mục…</p></div>
        <div class="modal-foot">
          <span class="hint">Bấm vào file để thêm vào ô Nguồn — thêm được nhiều file.</span>
          <button type="button" class="primary small modal-x">Xong</button>
        </div>
      </div>`;
    document.body.appendChild(dlg);
    document.addEventListener('keydown', onEsc);
    dlg.addEventListener('click', (e) => {
      if (e.target === dlg || e.target.closest('.modal-x')) closePicker();
      const row = e.target.closest('.filerow');
      if (row) {
        addSource(row.dataset.path);
        danhDauThem(row, true);
      }
    });
    dlg.querySelector('.modal-find').addEventListener('input', (e) => {
      const q = e.target.value.trim().toLowerCase();
      dlg.querySelectorAll('.filerow').forEach((r) => {
        r.hidden = q && !r.dataset.name.toLowerCase().includes(q);
      });
    });

    const body = dlg.querySelector('.modal-body');
    let groups;
    try {
      const resp = await fetch('/api/tep-nguon', { credentials: 'same-origin' });
      groups = (await resp.json()).groups || [];
    } catch (_) {
      body.innerHTML = '<p class="warn">Không đọc được danh sách file — server còn chạy không?</p>';
      return;
    }
    const has = groups.some((g) => g.files.length);
    if (!has) {
      body.innerHTML = '<p class="empty">Không thấy file audio/video nào trong các thư mục tải về.</p>';
      return;
    }
    body.innerHTML = groups.map((g) => `
      <div class="filegroup">
        <div class="filegroup-head">${esc(g.label)}
          <span class="hint">${esc(g.folder)}</span></div>
        ${g.files.length ? g.files.map((f) => `
          <button type="button" class="filerow${f.episode ? (f.xong ? ' filerow-xong' : ' filerow-dang') : ''}"
                  data-path="${esc(f.path)}" data-name="${esc(f.name)}">
            <span class="filerow-name">${esc(f.name)}</span>
            ${dauDaLam(f)}
            <span class="filerow-meta">${esc(f.size)} · ${esc(f.when)}</span>
          </button>`).join('')
          : '<p class="empty">Thư mục trống.</p>'}
        ${g.more ? `<p class="hint">…và ${g.more} file cũ hơn không hiện ở đây.</p>` : ''}
      </div>`).join('');
    // File đã nằm sẵn trong ô Nguồn (thêm ở lần mở trước, hoặc tự gõ vào) cũng
    // mang dấu ngay từ đầu — đóng rồi mở lại bảng vẫn thấy đã thêm những file nào.
    const daCo = new Set((box()?.value || '').split('\n').map((s) => s.trim()).filter(Boolean));
    dlg.querySelectorAll('.filerow').forEach((r) => {
      if (daCo.has(r.dataset.path)) danhDauThem(r);
    });
    dlg.querySelector('.modal-find').focus();
  }

  /** Nhãn "đã làm" của một file: tập mấy, xong hẳn hay còn dở mấy bước.
      Nguồn chưa chạy bao giờ (không có trong manifest) thì không có nhãn nào. */
  function dauDaLam(f) {
    if (!f.episode) return '';
    const tap = 'tập ' + esc(f.episode);
    return f.xong
      ? `<span class="dalam xong" title="Đã làm xong ${tap}">✓ ${tap}</span>`
      : `<span class="dalam dang" title="Đang dở ${tap} — ${esc(f.buoc)} bước">◐ ${tap} · ${esc(f.buoc)}</span>`;
  }

  /** Dán dấu "✓ đã thêm" lên hàng và GIỮ NGUYÊN ở đó — trước đây dấu hiện 1,1s
      rồi mất, danh sách dài là quên mất đã bấm file nào. Thuần hiệu ứng: việc
      không thêm trùng vẫn do addSource lo, bấm lại mấy lần cũng vô hại.
      nhay=true thì nháy thêm một cái cho biết vừa bấm trúng hàng nào. */
  function danhDauThem(row, nhay) {
    row.classList.add('filerow-them');
    if (!row.querySelector('.themroi')) {
      row.querySelector('.filerow-name')
         .insertAdjacentHTML('afterend', '<span class="dalam themroi">✓ đã thêm</span>');
    }
    if (!nhay) return;
    row.classList.add('filerow-hit');
    setTimeout(() => row.classList.remove('filerow-hit'), 700);
  }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }
})();


// ── Khối tự làm mới (hàng đợi 2 s/lần, bảng tập 15 s/lần) ─────────────────
// htmx thay TOÀN BỘ DOM của khối mỗi lượt poll kể cả khi HTML y hệt → màn hình
// nhấp nháy theo nhịp poll, bảng tập thì mất ô tick sau mỗi 15 s (04/09/2026).
// Sửa ở đây: HTML trả về giống lần trước thì bỏ lượt thay; riêng bảng tập nhớ
// các ô đang tick trước khi thay và tick lại sau khi thay.
(function () {
  const KHOI = new Set(['queue', 'recogtable']);

  document.addEventListener('htmx:beforeSwap', (evt) => {
    const t = evt.detail.target;
    if (!t || !KHOI.has(t.id)) return;
    if (evt.detail.isError) { evt.detail.shouldSwap = false; return; }   // 401/500 không đè vào khối
    const moi = evt.detail.serverResponse;
    if (typeof moi !== 'string') return;
    if (t.dataset.htmlCu === moi) { evt.detail.shouldSwap = false; return; }   // y hệt → không đụng DOM
    t.dataset.htmlCu = moi;
    if (t.id === 'recogtable') {
      t.dataset.ticked = JSON.stringify(
        [...t.querySelectorAll('input[name="tap"]:checked')].map((i) => i.value));
    }
  });

  document.addEventListener('htmx:afterSwap', (evt) => {
    const t = evt.detail.target;
    if (!t || t.id !== 'recogtable' || !t.dataset.ticked) return;
    const ticked = new Set(JSON.parse(t.dataset.ticked));
    t.querySelectorAll('input[name="tap"]').forEach((i) => { if (ticked.has(i.value)) i.checked = true; });
  });
})();


// ── Ô tick tập dùng chung trang Nhận diện ↔ Home (+ mọi tab) (03/10/2026) ─────
// Bảng tập có ở cả hai trang (Home: ngay dưới ô Nguồn). Tick ở trang này thì sang
// trang kia, hay tab khác, vẫn thấy đúng các tập đã tick. Lưu ở localStorage của
// trình duyệt — chỉ là lựa chọn tạm trên giao diện, không phải cài đặt. Bảng tự vẽ
// lại (15 s/lần, sau mỗi lần bấm chạy) cũng tick lại theo đây. Không đọc/ghi được
// localStorage thì vẫn như cũ: khối ở trên giữ ô tick qua mỗi lần vẽ lại.
(function () {
  const KEY = 'mvTapTick';
  const SEL = '#recogtable input[name="tap"]';
  function doc() {
    try {
      const v = JSON.parse(localStorage.getItem(KEY) || 'null');
      return Array.isArray(v) ? v : null;
    } catch (_) { return null; }
  }
  function ghi() {
    const v = [...document.querySelectorAll(SEL + ':checked')].map((i) => i.value);
    try { localStorage.setItem(KEY, JSON.stringify(v)); } catch (_) { /* chế độ riêng tư… */ }
  }
  function apDung() {
    const v = doc();
    if (!v) return;
    const s = new Set(v);
    document.querySelectorAll(SEL).forEach((i) => { i.checked = s.has(i.value); });
  }
  // Nút "Chọn tất cả" / "Bỏ chọn" của bảng (_batch_bang.html).
  window.tickAll = function (on) {
    document.querySelectorAll(SEL).forEach((c) => { c.checked = on; });
    ghi();
  };
  document.addEventListener('change', (e) => { if (e.target.matches && e.target.matches(SEL)) ghi(); });
  document.addEventListener('htmx:afterSwap', (e) => {
    if (e.detail.target && e.detail.target.id === 'recogtable') apDung();
  });
  window.addEventListener('storage', (e) => { if (e.key === KEY) apDung(); });   // tab khác vừa tick
  window.addEventListener('pageshow', apDung);                                   // quay lại bằng Back
  apDung();
})();


// ── Popup ✍️ dịch tay đoạn (trống) — bấm nhãn "n trống" ở cột Dịch ────────────
// Yêu cầu 06/09/2026: bấm nhãn mở popup, TRÁI là nguồn tiếng Trung của đoạn đó
// (📋 Copy để đem đi dịch ở đâu tuỳ ý), PHẢI là ô dán bản dịch (📥 Dán) + 💾 Lưu
// → ghi thẳng vào gemini_result.docx qua /api/doan-trong/luu (server sao lưu file
// cũ cạnh đó), coi như đã dịch tay xong. Nhiều đoạn trống thì có dãy nút "Đoạn k"
// để chuyển; bản đang gõ dở của mỗi đoạn được giữ khi chuyển qua lại. Lưu xong
// bảng tập tự làm mới (nhãn "n trống" giảm / biến mất).
(function () {
  let dlg = null;       // phần tử .modal đang mở
  let data = null;      // JSON từ /api/doan-trong: {tap, ten, total, doan: [{j, zh, dau}]}
  let cur = 0;          // chỉ số đoạn đang xem trong data.doan
  let tap = '';
  let notice = null;    // {kind, text} hiện dưới ô bản dịch sau khi render lại

  document.addEventListener('click', (e) => {
    const b = e.target.closest('.badge-trong');
    if (!b) return;
    e.preventDefault();
    open(b.dataset.tap || '');
  });

  function body() { return dlg ? dlg.querySelector('.modal-body') : null; }
  function taValue() { const ta = dlg && dlg.querySelector('.trong-vi'); return ta ? ta.value : ''; }

  /** Đoạn nào còn chữ gõ dở mà chưa lưu → hỏi trước khi đóng. */
  function hasUnsaved() {
    if (!data) return false;
    if (data.doan[cur]) data.doan[cur].draft = taValue();
    return data.doan.some((d) => !d.xong && (d.draft || '').trim());
  }

  function close(force) {
    if (!dlg) return;
    if (!force && hasUnsaved() &&
        !confirm('Có bản dịch dán vào mà chưa 💾 Lưu — đóng và bỏ luôn?')) return;
    dlg.remove(); dlg = null; data = null; notice = null;
    document.removeEventListener('keydown', onEsc);
  }
  function onEsc(e) { if (e.key === 'Escape') close(); }

  async function open(t) {
    close(true);
    tap = t;
    dlg = document.createElement('div');
    dlg.className = 'modal';
    dlg.innerHTML = `
      <div class="modal-card trongmodal">
        <div class="modal-head">
          <b>✍️ Dịch tay đoạn trống — tập ${esc(t)}</b>
          <span class="spacer"></span>
          <button type="button" class="small modal-x">✕</button>
        </div>
        <div class="modal-body"><p class="hint">Đang đọc gemini_result.docx…</p></div>
        <div class="modal-foot">
          <span class="hint">📋 Copy tiếng Trung → dịch ở đâu tuỳ ý → 📥 Dán vào ô bên phải → 💾 Lưu.
            Lưu là ghi thẳng vào gemini_result.docx (file cũ được sao lưu cạnh đó).</span>
          <button type="button" class="small modal-x">Đóng</button>
        </div>
      </div>`;
    document.body.appendChild(dlg);
    document.addEventListener('keydown', onEsc);
    dlg.addEventListener('click', (e) => {
      if (e.target === dlg || e.target.closest('.modal-x')) { close(); return; }
      const tab = e.target.closest('.trong-tab');
      if (tab) { show(+tab.dataset.i); return; }
      if (e.target.closest('.trong-paste')) { paste(); return; }
      if (e.target.closest('.trong-save')) { save(); }
    });

    let j;
    try {
      const resp = await fetch(`/api/doan-trong?tap=${encodeURIComponent(t)}`, { credentials: 'same-origin' });
      j = await resp.json();
    } catch (_) {
      if (body()) body().innerHTML = '<p class="warn">Không đọc được dữ liệu — server còn chạy không?</p>';
      return;
    }
    if (!dlg) return;                                   // đã đóng trong lúc chờ
    if (j.loi) { body().innerHTML = `<p class="warn">${esc(j.loi)}</p>`; return; }
    if (!j.doan || !j.doan.length) {
      body().innerHTML = `<p class="empty">Tập ${esc(t)} không còn đoạn trống nào trong gemini_result.docx.</p>`;
      return;
    }
    data = j;
    cur = 0;
    render();
  }

  function show(i) {
    if (!data || i === cur || !data.doan[i]) return;
    data.doan[cur].draft = taValue();                  // giữ chữ đang gõ dở
    cur = i;
    notice = null;
    render();
  }

  function render() {
    const d = data.doan[cur];
    const tabs = data.doan.map((x, i) =>
      `<button type="button" class="trong-tab${i === cur ? ' dang' : ''}${x.xong ? ' xong' : ''}"
               data-i="${i}">Đoạn ${x.j}${x.xong ? ' ✓' : ''}</button>`).join('');
    const conLai = data.doan.filter((x) => !x.xong).length;
    const trangThai = d.xong ? 'đã lưu ✓' : `đang ${esc(d.dau || '(trống)')}`;
    body().innerHTML = `
      <div class="trong-tabs">${tabs}
        <span class="hint">${conLai} đoạn còn trống / ${data.total} đoạn của tập</span></div>
      <div class="trong-grid">
        <div class="trong-pane">
          <div class="trong-pane-head">🇨🇳 Tiếng Trung — đoạn ${d.j}
            <span class="hint">${d.zh.length} chữ</span>
            <span class="spacer"></span>
            <button type="button" class="small" data-copy="trong-zh-text">📋 Copy</button></div>
          <div class="trong-zh" id="trong-zh-text">${esc(d.zh)}</div>
        </div>
        <div class="trong-pane">
          <div class="trong-pane-head">🇻🇳 Tiếng Việt — ${trangThai}
            <span class="spacer"></span>
            <button type="button" class="small trong-paste">📥 Dán</button>
            <button type="button" class="primary small trong-save">💾 Lưu — đã dịch tay</button></div>
          <textarea class="trong-vi" spellcheck="false"
                    placeholder="Dán bản dịch tiếng Việt của đoạn ${d.j} vào đây (📥 Dán hoặc Ctrl+V) rồi bấm 💾 Lưu…">${esc(d.draft != null ? d.draft : (d.xong ? d.vi : ''))}</textarea>
          <div class="trong-note"></div>
        </div>
      </div>`;
    if (notice) setNote(notice.kind, notice.text);
  }

  function setNote(kind, text) {
    const n = dlg && dlg.querySelector('.trong-note');
    if (!n) return;
    n.className = 'trong-note' + (kind ? ' ' + kind : '');
    n.textContent = text;
    notice = { kind, text };
  }

  async function paste() {
    const ta = dlg.querySelector('.trong-vi');
    try {
      const t = await navigator.clipboard.readText();
      if (!t.trim()) { setNote('warn', 'Clipboard đang trống — copy bản dịch trước rồi bấm 📥 Dán.'); ta.focus(); return; }
      ta.value = t;
      ta.focus();
      setNote('ok', `Đã dán ${t.length} ký tự — xem lại rồi bấm 💾 Lưu.`);
    } catch (_) {
      // Firefox (và Chrome khi không cho phép) chặn đọc clipboard bằng JS → dán tay.
      ta.focus();
      setNote('warn', 'Trình duyệt không cho đọc clipboard — bấm Ctrl+V vào ô bên phải rồi 💾 Lưu.');
    }
  }

  async function save() {
    const d = data.doan[cur];
    const ta = dlg.querySelector('.trong-vi');
    const btn = dlg.querySelector('.trong-save');
    const text = ta.value.trim();
    if (!text) { setNote('bad', 'Ô bản dịch đang trống — dán nội dung rồi mới lưu.'); ta.focus(); return; }
    btn.disabled = true;
    setNote('', 'Đang ghi vào gemini_result.docx…');
    let r;
    try {
      const resp = await fetch('/api/doan-trong/luu', {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tap, doan: d.j, text }),
      });
      r = await resp.json();
    } catch (_) {
      btn.disabled = false;
      setNote('bad', 'Không gọi được server — server còn chạy không?');
      return;
    }
    if (!dlg) return;
    if (!r.ok) { btn.disabled = false; setNote('bad', r.loi || 'Không lưu được.'); return; }

    d.xong = true; d.vi = text; d.draft = null;
    const canhBao = (r.canh_bao && r.canh_bao.length) ? ` ⚠️ ${r.canh_bao.join('; ')}.` : '';
    const conLai = (r.trong || []).length;
    let text2 = `✅ Đã lưu đoạn ${d.j} (${r.ky_tu} ký tự) vào gemini_result.docx${canhBao}`;
    text2 += conLai ? ` Còn trống: đoạn ${r.trong.join(', ')}.` : ' Tập này hết đoạn trống — ⏩ chạy tiếp được rồi.';
    // Sang đoạn trống kế tiếp (nếu có) để dịch tiếp luôn; hết thì ở lại đoạn vừa lưu.
    const next = data.doan.findIndex((x, i) => i !== cur && !x.xong);
    if (next >= 0) cur = next;
    notice = { kind: canhBao ? 'warn' : 'ok', text: text2 };
    render();
    if (window.htmx) htmx.trigger('#recogtable', 'refresh');   // nhãn "n trống" ở bảng đổi theo
  }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }
})();


// ── Popup 🔴 xem đoạn TÔ ĐỎ — bấm nhãn "n đỏ" ở cột Dịch ──────────────────────
// Yêu cầu 07/09/2026: đoạn dịch được nhờ câu nhắc sau khi Gemini từ chối, hoặc nhờ
// lượt 2 chat mới, được TÔ ĐỎ trong gemini_result.docx để người dùng kiểm. Bấm nhãn
// mở popup: TRÁI là tiếng Trung (📋 Copy), PHẢI là tiếng Việt (sửa được tại chỗ).
// ✔ Đã kiểm → gọi /api/doan-do/luu: bỏ màu đỏ đoạn đó, có sửa chữ thì ghi bản sửa
// (server sao lưu file cũ cạnh đó). Dùng chung khung CSS với popup "n trống".
(function () {
  let dlg = null;       // phần tử .modal đang mở
  let data = null;      // JSON từ /api/doan-do: {tap, ten, total, doan: [{j, zh, vi, xong, trong}]}
  let cur = 0;          // chỉ số đoạn đang xem trong data.doan
  let tap = '';
  let notice = null;    // {kind, text} hiện dưới ô tiếng Việt sau khi render lại
  let tatCa = false;    // true = mở từ dấu ✅/— (xem ĐẦY ĐỦ mọi đoạn, 15/09/2026)

  // Nhãn "n đỏ" → chỉ các đoạn đỏ. Dấu ✅ / — (.badge-xem) → MỌI đoạn của tập
  // (/api/doan-do?tatca=1), cùng một popup: đoạn đỏ còn lại vẫn ✔ được, đoạn khác
  // chỉ xem, đoạn (trống) hiện dấu "(trống)".
  document.addEventListener('click', (e) => {
    const b = e.target.closest('.badge-do, .badge-xem');
    if (!b) return;
    e.preventDefault();
    open(b.dataset.tap || '', b.classList.contains('badge-xem'));
  });

  function body() { return dlg ? dlg.querySelector('.modal-body') : null; }
  function taValue() { const ta = dlg && dlg.querySelector('.trong-vi'); return ta ? ta.value : ''; }
  function same(a, b) { return String(a || '').trim() === String(b || '').trim(); }

  /** Đoạn nào có sửa chữ mà chưa ✔ → hỏi trước khi đóng. */
  function hasUnsaved() {
    if (!data) return false;
    const d = data.doan[cur];
    if (d && !d.xong) d.draft = taValue();
    return data.doan.some((x) => !x.xong && x.draft != null && !same(x.draft, x.vi));
  }

  function close(force) {
    if (!dlg) return;
    if (!force && hasUnsaved() &&
        !confirm('Có đoạn đã sửa chữ mà chưa ✔ Đã kiểm — đóng và bỏ phần sửa?')) return;
    dlg.remove(); dlg = null; data = null; notice = null;
    document.removeEventListener('keydown', onEsc);
  }
  function onEsc(e) { if (e.key === 'Escape') close(); }

  async function open(t, all) {
    close(true);
    tap = t;
    tatCa = !!all;
    dlg = document.createElement('div');
    dlg.className = 'modal';
    const head = tatCa ? `📖 Toàn bộ đoạn dịch — tập ${esc(t)}` : `🔴 Đoạn tô đỏ cần kiểm — tập ${esc(t)}`;
    const foot = tatCa
      ? `Mọi đoạn của tập: trái tiếng Trung, phải tiếng Việt — bấm từng thẻ "Đoạn n" để xem.
         Đoạn còn TÔ ĐỎ vẫn sửa / ✔ Đã kiểm được ngay tại đây; đoạn (trống) thì lấp bằng 🔁 Dịch lại
         đoạn (Trống) hoặc nhãn "n trống" ✍️.`
      : `Đoạn này Gemini dịch được nhờ câu nhắc sau khi từ chối, hoặc nhờ chat mới (lượt 2)
         — đối chiếu tiếng Trung bên trái, sửa chữ bên phải nếu cần, rồi ✔ Đã kiểm để bỏ màu đỏ
         trong gemini_result.docx (file cũ được sao lưu cạnh đó).`;
    dlg.innerHTML = `
      <div class="modal-card trongmodal">
        <div class="modal-head">
          <b>${head}</b>
          <span class="spacer"></span>
          <button type="button" class="small modal-x">✕</button>
        </div>
        <div class="modal-body"><p class="hint">Đang đọc gemini_result.docx…</p></div>
        <div class="modal-foot">
          <span class="hint">${foot}</span>
          <button type="button" class="small modal-x">Đóng</button>
        </div>
      </div>`;
    document.body.appendChild(dlg);
    document.addEventListener('keydown', onEsc);
    dlg.addEventListener('click', (e) => {
      if (e.target === dlg || e.target.closest('.modal-x')) { close(); return; }
      const tab = e.target.closest('.trong-tab');
      if (tab) { show(+tab.dataset.i); return; }
      if (e.target.closest('.do-ok')) { review(); }
    });

    let j;
    try {
      const url = `/api/doan-do?tap=${encodeURIComponent(t)}` + (tatCa ? '&tatca=1' : '');
      const resp = await fetch(url, { credentials: 'same-origin' });
      j = await resp.json();
    } catch (_) {
      if (body()) body().innerHTML = '<p class="warn">Không đọc được dữ liệu — server còn chạy không?</p>';
      return;
    }
    if (!dlg) return;                                   // đã đóng trong lúc chờ
    if (j.loi) { body().innerHTML = `<p class="warn">${esc(j.loi)}</p>`; return; }
    if (!j.doan || !j.doan.length) {
      body().innerHTML = tatCa
        ? `<p class="empty">Tập ${esc(t)} chưa có đoạn nào trong gemini_result.docx.</p>`
        : `<p class="empty">Tập ${esc(t)} không còn đoạn tô đỏ nào trong gemini_result.docx.</p>`;
      return;
    }
    data = j;
    cur = 0;
    render();
  }

  function show(i) {
    if (!data || i === cur || !data.doan[i]) return;
    if (!data.doan[cur].xong) data.doan[cur].draft = taValue();   // giữ chữ đang sửa dở
    cur = i;
    notice = null;
    render();
  }

  function render() {
    const d = data.doan[cur];
    // Thẻ mỗi đoạn: đỏ = còn phải kiểm, trống = chưa có bản dịch (chỉ xem), còn lại
    // là bản dịch thường (✓ chỉ hiện ở popup đỏ, nơi nó nghĩa là "đã kiểm").
    const tabs = data.doan.map((x, i) => {
      const cls = x.trong ? ' trong' : (x.xong ? ' xong' : ' do');
      const mark = x.trong ? ' ○' : (!x.xong ? ' 🔴' : (tatCa ? '' : ' ✓'));
      return `<button type="button" class="trong-tab${cls}${i === cur ? ' dang' : ''}"
               data-i="${i}">Đoạn ${x.j}${mark}</button>`;
    }).join('');
    const conLai = data.doan.filter((x) => !x.xong).length;
    const soTrong = data.doan.filter((x) => x.trong).length;
    const tomTat = tatCa
      ? `${data.total} đoạn của tập · ${conLai} đỏ · ${soTrong} trống`
      : `${conLai} đoạn còn đỏ / ${data.total} đoạn của tập`;
    const trangThai = d.trong ? 'đang (trống) — chưa có bản dịch'
      : d.xong ? (tatCa ? 'bản dịch' : 'đã kiểm ✓') : 'đang TÔ ĐỎ — cần kiểm';
    const vi = d.draft != null ? d.draft : (d.vi || '');
    body().innerHTML = `
      <div class="trong-tabs">${tabs}
        <span class="hint">${tomTat}</span></div>
      <div class="trong-grid">
        <div class="trong-pane">
          <div class="trong-pane-head">🇨🇳 Tiếng Trung — đoạn ${d.j}
            <span class="hint">${d.zh.length} chữ</span>
            <span class="spacer"></span>
            <button type="button" class="small" data-copy="do-zh-text">📋 Copy</button></div>
          <div class="trong-zh" id="do-zh-text">${esc(d.zh)}</div>
        </div>
        <div class="trong-pane">
          <div class="trong-pane-head">🇻🇳 Tiếng Việt — ${trangThai}
            <span class="hint">${vi.length} ký tự</span>
            <span class="spacer"></span>
            ${d.xong ? '' : '<button type="button" class="primary small do-ok">✔ Đã kiểm — bỏ đỏ (lưu sửa nếu có)</button>'}</div>
          <textarea class="trong-vi${d.xong ? '' : ' do'}" spellcheck="false"${d.xong ? ' readonly' : ''}>${esc(vi)}</textarea>
          <div class="trong-note"></div>
        </div>
      </div>`;
    if (notice) setNote(notice.kind, notice.text);
  }

  function setNote(kind, text) {
    const n = dlg && dlg.querySelector('.trong-note');
    if (!n) return;
    n.className = 'trong-note' + (kind ? ' ' + kind : '');
    n.textContent = text;
    notice = { kind, text };
  }

  async function review() {
    const d = data.doan[cur];
    const ta = dlg.querySelector('.trong-vi');
    const btn = dlg.querySelector('.do-ok');
    const text = ta.value.trim();
    if (!text) { setNote('bad', 'Ô tiếng Việt đang trống — muốn bỏ nội dung thì dùng nhãn "n trống" ✍️, không xoá ở đây.'); ta.focus(); return; }
    btn.disabled = true;
    setNote('', 'Đang ghi vào gemini_result.docx…');
    let r;
    try {
      const resp = await fetch('/api/doan-do/luu', {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tap, doan: d.j, text }),
      });
      r = await resp.json();
    } catch (_) {
      btn.disabled = false;
      setNote('bad', 'Không gọi được server — server còn chạy không?');
      return;
    }
    if (!dlg) return;
    if (!r.ok) { btn.disabled = false; setNote('bad', r.loi || 'Không ghi được.'); return; }

    d.xong = true; d.vi = text; d.draft = null;
    const canhBao = (r.canh_bao && r.canh_bao.length) ? ` ⚠️ ${r.canh_bao.join('; ')}.` : '';
    const conLai = (r.do || []).length;
    let text2 = r.sua
      ? `✅ Đã lưu bản sửa đoạn ${d.j} (${r.ky_tu} ký tự) và bỏ màu đỏ.${canhBao}`
      : `✅ Đoạn ${d.j} đã kiểm — bỏ màu đỏ, giữ nguyên nội dung.`;
    text2 += conLai ? ` Còn đỏ: đoạn ${r.do.join(', ')}.` : ' Tập này hết đoạn đỏ.';
    if (r.trong && r.trong.length) text2 += ` (Còn trống: đoạn ${r.trong.join(', ')} — nhãn "n trống".)`;
    // Sang đoạn đỏ kế tiếp (nếu có) để kiểm tiếp luôn; hết thì ở lại đoạn vừa kiểm.
    const next = data.doan.findIndex((x, i) => i !== cur && !x.xong);
    if (next >= 0) cur = next;
    notice = { kind: canhBao ? 'warn' : 'ok', text: text2 };
    render();
    if (window.htmx) htmx.trigger('#recogtable', 'refresh');   // nhãn "n đỏ" ở bảng đổi theo
  }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }
})();
// Exactly one Gemini browser, synchronized between the Home page's two forms.
document.addEventListener("change", event => {
  if (!event.target.matches('input[type="checkbox"][name="gemini_backend"]')) return;
  const selected = event.target.value;
  document.querySelectorAll('input[name="gemini_backend"]').forEach(input => {
    input.checked = input.value === selected;
  });
});
// ── Tab 🧩 Extension: thử kết nối / gửi thử qua Chrome Extension. Lượt thử chạy
//    trong tiến trình server (web/gemini_test.py); trang hỏi /api/gemini-test mỗi
//    giây khi đang chạy để in nhật ký và kết quả.
(() => {
  const panel = document.getElementById('ext-test');
  if (!panel) return;
  const $ = id => document.getElementById(id);
  const logBox = $('ext-log'), resultBox = $('ext-result'), status = $('ext-status');
  let timer = null;
  async function refresh() {
    clearTimeout(timer);
    try {
      const resp = await fetch('/api/gemini-test', { credentials: 'same-origin' });
      const s = await resp.json();
      logBox.textContent = s.lines.length ? s.lines.join('\n') : 'Chưa chạy.';
      resultBox.textContent = s.result || '';
      status.textContent = s.running ? '⌛ đang chạy…'
        : s.error ? '❌ ' + s.error
        : s.finished ? '✅ xong' : '';
      $('ext-check').disabled = $('ext-send').disabled = Boolean(s.running);
      logBox.scrollTop = logBox.scrollHeight;
      if (s.running) timer = setTimeout(refresh, 1000);
    } catch (e) {
      status.textContent = 'Không lấy được trạng thái: ' + e;
    }
  }
  async function start(mode) {
    const fd = new FormData();
    fd.set('mode', mode);
    fd.set('text', $('ext-text').value);
    if ($('ext-full').checked) fd.set('full_prefix', '1');
    status.textContent = '⌛ đang gửi yêu cầu…';
    const resp = await fetch('/api/gemini-test/chay', { method: 'POST', body: fd, credentials: 'same-origin' });
    const s = await resp.json().catch(() => ({}));
    if (!resp.ok) { status.textContent = '❌ ' + (s.error || ('HTTP ' + resp.status)); return; }
    refresh();
  }
  $('ext-check').addEventListener('click', () => start('check'));
  $('ext-send').addEventListener('click', () => start('send'));
  refresh();
})();


// ── Thông báo nổi (03/10/2026) ──────────────────────────────────────────────
// Trang không tải lại sau mỗi cú bấm nữa, nên các dòng server báo cho CHÍNH lượt
// bấm đó (“➕ Xếp hàng…”, “⚠️ Chưa nhập link…”, xem _ajax trong server.py) hiện
// thành ô nổi góc dưới phải — trước đây chỉ nằm trong cửa sổ console. Bấm để đóng.
window.mvToast = (function () {
  const MAX = 8;
  function hop() {
    let el = document.getElementById('toasts');
    if (!el) {
      el = document.createElement('div');
      el.id = 'toasts';
      el.setAttribute('aria-live', 'polite');
      document.body.appendChild(el);
    }
    return el;
  }
  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }
  return function (lines) {
    lines = (lines || []).map(String).filter((s) => s.trim());
    if (!lines.length) return;
    const loi = lines.some((s) => /^\s*(⛔|❌)/.test(s));
    const canh = !loi && lines.some((s) => /^\s*⚠/.test(s));
    const t = document.createElement('div');
    t.className = 'toast' + (loi ? ' toast-loi' : canh ? ' toast-canh' : '');
    t.title = 'Bấm để đóng';
    t.innerHTML = lines.slice(0, MAX).map((s) => `<div>${esc(s)}</div>`).join('') +
      (lines.length > MAX
        ? `<div class="toast-them">…và ${lines.length - MAX} dòng nữa (xem cửa sổ console)</div>` : '');
    t.addEventListener('click', () => t.remove());
    hop().appendChild(t);
    const ms = loi || canh ? 9000 : 4500;          // lỗi/cảnh báo để lâu hơn cho kịp đọc
    setTimeout(() => t.classList.add('toast-mo'), ms);
    setTimeout(() => t.remove(), ms + 600);
  };
})();


// ── Ô Nguồn dùng chung mọi trang + mọi tab (03/10/2026) ───────────────────────
// Trang Tạo kịch bản, Nhận diện và Home đều có ô Nguồn (textarea name=sources);
// trước đây mỗi ô một nội dung, chuyển trang là mất. Nay:
//   • gõ/dán/📂 thêm ở ô nào thì các ô Nguồn khác trên cùng trang khớp ngay, và nội
//     dung gửi về server (/api/nguon) sau ~0,4 s — trang nào vẽ ra cũng điền sẵn;
//   • tab khác của cùng trình duyệt nhận ngay qua BroadcastChannel; tab bị ẩn rồi mở
//     lại (hay quay lại bằng nút Back) thì hỏi lại server;
//   • bấm ▶ chạy: server bỏ các dòng vừa xếp hàng khỏi ô (khỏi chạy trùng), trang
//     hỏi lại (pull) để ô hiện đúng phần còn lại.
window.mvNguon = (function () {
  const SEL = 'textarea[name="sources"]';
  const cacO = () => [...document.querySelectorAll(SEL)];
  let ver = Math.max(0, ...cacO().map((t) => Number(t.dataset.ver) || 0));
  let ban = false;              // có thay đổi chưa gửi
  let hen = null;               // hẹn giờ gửi
  let dangGui = Promise.resolve();
  let tuMay = false;            // đang tự điền (không phải người gõ) → bỏ qua sự kiện input
  const kenh = 'BroadcastChannel' in window ? new BroadcastChannel('myvoice-nguon') : null;

  function dien(text, tru) {
    tuMay = true;
    try {
      cacO().forEach((t) => {
        if (t === tru || t.value === text) return;
        t.value = text;
        // Cho các bộ nghe khác (vd bản xem trước cách chia số tập) cập nhật theo.
        t.dispatchEvent(new Event('input', { bubbles: true }));
      });
    } finally {
      tuMay = false;
    }
  }

  /** Gửi ngay phần đang chờ (nếu có) → Promise xong khi server đã nhận. */
  function gui() {
    clearTimeout(hen);
    hen = null;
    if (!ban) return dangGui;
    ban = false;
    const o = cacO()[0];
    const fd = new FormData();
    fd.set('text', o ? o.value : '');
    // keepalive: bấm sang trang khác ngay sau khi gõ thì lượt gửi vẫn đi tới nơi.
    dangGui = dangGui
      .then(() => fetch('/api/nguon', { method: 'POST', body: fd,
                                        credentials: 'same-origin', keepalive: true }))
      .then((r) => r.json())
      .then((d) => { ver = d.ver; if (kenh) kenh.postMessage(d); })
      .catch(() => { ban = true; hen = setTimeout(gui, 3000); });
    return dangGui;
  }

  /** Hỏi server bản mới nhất — bỏ qua nếu ở đây đang gõ dở (bản của mình thắng). */
  async function hoiLai() {
    if (ban || hen) return;
    try {
      const r = await fetch('/api/nguon', { credentials: 'same-origin', cache: 'no-store' });
      const d = await r.json();
      if (ban || hen || d.ver === ver) return;
      ver = d.ver;
      dien(d.text);
    } catch (_) { /* server tắt: giữ nguyên */ }
  }

  document.addEventListener('input', (e) => {
    if (tuMay || !e.target.matches || !e.target.matches(SEL)) return;
    dien(e.target.value, e.target);
    ban = true;
    clearTimeout(hen);
    hen = setTimeout(gui, 400);
  });
  if (kenh) {
    kenh.onmessage = (e) => {
      const d = e.data || {};
      if (ban || hen || typeof d.text !== 'string') return;
      ver = d.ver;
      dien(d.text);
    };
  }
  document.addEventListener('visibilitychange', () => { if (!document.hidden) hoiLai(); });
  window.addEventListener('pageshow', (e) => { if (e.persisted) hoiLai(); });
  window.addEventListener('pagehide', () => { gui(); });
  // Trang vừa mở có thể được vẽ TRƯỚC khi lượt gửi keepalive của trang trước tới
  // server (gõ xong bấm menu ngay) → hỏi lại một lần sau khi mở.
  setTimeout(hoiLai, 900);
  return { flush: gui, pull: hoiLai };
})();


// ── Bấm nút chạy / hàng đợi KHÔNG tải lại trang (03/10/2026) ─────────────────
// Mọi form POST (trừ form/nút đã có hx-post riêng) được gửi ngầm bằng fetch kèm
// header X-Ajax: server làm việc như cũ rồi trả JSON {notes} thay cho cú chuyển
// hướng (xem _ajax trong server.py). Trang đứng yên — chỗ đang cuộn, ô đang gõ, ô
// tập đang tick vẫn nguyên; khối hàng đợi + bảng tập tự làm mới tại chỗ, các dòng
// server báo hiện thành thông báo nổi. Form data-ajax="tailai" (Reset, Xoá output)
// vẫn gửi ngầm nhưng xong thì tải lại trang, vì nội dung trang vừa đổi hẳn.
// Đăng ký SAU khối "Home: lưu hết các khối" ở đầu file: khối đó chặn lượt submit
// đầu (e.defaultPrevented) rồi tự gửi lại — tới lượt đó mới vào đây.
(function () {
  function lamMoi() {
    if (window.htmx) {
      if (document.getElementById('queue')) {
        htmx.ajax('GET', '/partials/queue', { target: '#queue', swap: 'innerHTML' });
      }
      if (document.getElementById('recogtable')) htmx.trigger('#recogtable', 'refresh');
    }
    if (window.mvNguon) window.mvNguon.pull();
  }

  document.addEventListener('submit', async (e) => {
    if (e.defaultPrevented) return;
    const form = e.target;
    const nut = e.submitter;
    const method = ((nut && nut.getAttribute('formmethod')) || form.getAttribute('method') || 'get')
      .toLowerCase();
    if (method !== 'post') return;                     // form GET (chọn tập ở trang SEO…) = điều hướng
    if (form.hasAttribute('hx-post') || (nut && nut.hasAttribute('hx-post'))) return;   // htmx lo
    e.preventDefault();

    const url = (nut && nut.getAttribute('formaction')) || form.getAttribute('action')
      || location.pathname;
    const fd = new FormData(form);
    if (nut && nut.name) fd.append(nut.name, nut.value);   // start=… / action=…
    if (nut) { nut.disabled = true; nut.classList.add('dang-gui'); }
    try {
      // Ô Nguồn đang chờ gửi phải tới server TRƯỚC: không thì lượt gửi muộn đó đè
      // lại các dòng server vừa bỏ khỏi ô sau khi xếp hàng.
      if (window.mvNguon) await window.mvNguon.flush();
      const r = await fetch(url, { method: 'POST', body: fd, credentials: 'same-origin',
                                   headers: { 'X-Ajax': '1' } });
      let notes = [];
      if ((r.headers.get('content-type') || '').includes('json')) {
        const d = await r.json().catch(() => ({}));
        notes = d.notes || [];
        if (!r.ok && d.error) notes.push('⛔ ' + d.error);
      }
      const kem = r.headers.get('X-Notes');
      if (kem) { try { notes = notes.concat(JSON.parse(decodeURIComponent(kem))); } catch (_) {} }
      if (!r.ok) {
        notes.push(r.status === 401 ? '⛔ Hết phiên — mở lại link có ?token=… in ở cửa sổ server.'
                                    : `⛔ Server báo lỗi ${r.status}.`);
      }
      window.mvToast(notes.length ? notes : ['✓ Đã gửi']);
      if (r.ok && form.dataset.ajax === 'tailai') { location.reload(); return; }
      lamMoi();
    } catch (_) {
      window.mvToast(['⛔ Không gửi được — server còn chạy không?']);
    } finally {
      if (nut) { nut.disabled = false; nut.classList.remove('dang-gui'); }
    }
  });
})();


// ── Đổi cài đặt là TỰ LƯU, không tải lại trang (03/10/2026) ───────────────────
// Form mang data-tuluu="<đường 💾 của khối>": tick/chọn/gõ ở ô nào là gửi CẢ form
// vào đúng đường 💾 đó (ngữ nghĩa y hệt tự tay bấm 💾 — "ô tick vắng mặt = tắt"
// vẫn đúng vì gửi đủ form). Ô chọn/tick lưu ngay; ô gõ chữ/số lưu sau khi ngừng gõ
// ~1 s (hoặc khi rời ô). Không kích lưu: ô Nguồn (đã có đường riêng), ô tick tập
// trong bảng, ô "Làm lại…" (chỉ dùng cho một lần chạy) và ô mang data-khongluu.
(function () {
  const BO = new Set(['sources', 'tap', 'force', 'fbtap']);
  const GO_CHU = new Set(['text', 'number', 'search', 'url', 'email', 'tel', 'range']);
  const cho = new Map();        // form → {hen, el}: lượt lưu đang hẹn
  const dang = new Map();       // form → Promise của lượt lưu đang chạy

  function formCanLuu(el) {
    const form = el && el.form;
    if (!form || !form.dataset.tuluu) return null;
    if (!el.name || BO.has(el.name) || el.closest('[data-khongluu]')) return null;
    return form;
  }

  function henLuu(form, el, ms) {
    const c = cho.get(form);
    if (c) clearTimeout(c.hen);
    cho.set(form, { el, hen: setTimeout(() => { cho.delete(form); luu(form, el); }, ms) });
  }

  function luu(form, el) {
    // Nối đuôi lượt trước: hai lượt chạy song song có thể tới server lệch thứ tự,
    // lượt cũ tới sau đè mất giá trị mới.
    const p = (dang.get(form) || Promise.resolve()).then(async () => {
      const r = await fetch(form.dataset.tuluu, {
        method: 'POST', body: new FormData(form), credentials: 'same-origin',
        headers: { 'HX-Request': 'true' }, keepalive: true });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      daLuu(el, await r.text());
    }).catch((err) => window.mvToast(['⚠️ Chưa lưu được cài đặt: ' + err.message]));
    dang.set(form, p);
    return p;
  }

  function daLuu(el, html) {
    // Mẩu "✓ đã lưu" của server → ô .luunote cùng khối (nếu khối đó có).
    const khoi = el.closest('.panel, .savebar, form');
    const note = khoi && khoi.querySelector('.luunote');
    if (note) note.innerHTML = html;
    // Thêm dấu nhỏ ngay cạnh ô vừa đổi — nút 💾 và ô .luunote có khi nằm tít cuối form.
    const r = (el.closest('label') || el).getBoundingClientRect();
    if (!r.width && !r.height) return;
    const b = document.createElement('span');
    b.className = 'tuluu-dau';
    b.textContent = '✓ đã lưu';
    b.style.top = Math.max(4, r.top - 8) + 'px';
    b.style.left = Math.max(4, Math.min(window.innerWidth - 84, r.right - 76)) + 'px';
    document.body.appendChild(b);
    setTimeout(() => b.remove(), 1500);
  }

  document.addEventListener('change', (e) => {
    const form = formCanLuu(e.target);
    if (form) henLuu(form, e.target, 150);
  });
  document.addEventListener('input', (e) => {
    const el = e.target;
    const chu = el instanceof HTMLTextAreaElement
      || (el instanceof HTMLInputElement && GO_CHU.has(el.type));
    if (!chu) return;
    const form = formCanLuu(el);
    if (form) henLuu(form, el, 1000);
  });
  // Đổi xong bấm sang trang khác ngay: lưu nốt lượt đang hẹn (keepalive giữ cho tới nơi).
  window.addEventListener('pagehide', () => {
    cho.forEach((c, form) => { clearTimeout(c.hen); luu(form, c.el); });
    cho.clear();
  });
})();


// ── Khối Thumbnail: đổi "Tập" là điền tiêu đề SEO + đổi ảnh xem trước tại chỗ ──
// Trước đây ô này chuyển hẳn sang /thumbnail?tap=… (đang ở Home cũng bị kéo đi).
window.chonTapThumb = async function (sel) {
  const tap = sel.value;
  const ta = sel.form && sel.form.querySelector('textarea[name="title"]');
  if (tap && ta) {
    try {
      const r = await fetch('/api/tieude?tap=' + encodeURIComponent(tap), { credentials: 'same-origin' });
      ta.value = (await r.json()).title || '';
    } catch (_) {
      window.mvToast(['⚠️ Không lấy được tiêu đề SEO của tập ' + tap]);
    }
  }
  const xem = document.getElementById('xemtruoc');
  if (!xem) return;
  xem.dataset.tap = tap;
  window.xemTruocThumb();
  history.replaceState(null, '', tap ? '/thumbnail?tap=' + encodeURIComponent(tap) : '/thumbnail');
};

/** Nạp lại hai ảnh xem trước của tập đang chọn (trang Thumbnail) — không tải lại trang. */
window.xemTruocThumb = function () {
  const xem = document.getElementById('xemtruoc');
  if (!xem) return;
  const tap = xem.dataset.tap || '';
  const so = document.getElementById('xemtap');
  if (so) so.textContent = tap || '—';
  const trong = document.getElementById('xemtrong');
  xem.hidden = !tap;
  if (trong) trong.hidden = Boolean(tap);
  if (!tap) return;
  const t = Date.now();          // tránh trình duyệt lấy ảnh cũ trong cache
  xem.querySelectorAll('img[data-kieu]').forEach((img) => {
    img.closest('figure').classList.remove('missing');
    img.src = `/tap/${encodeURIComponent(tap)}/${img.dataset.kieu}?t=${t}`;
  });
};
