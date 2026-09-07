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
  let data = null;      // JSON từ /api/doan-do: {tap, ten, total, doan: [{j, zh, vi}]}
  let cur = 0;          // chỉ số đoạn đang xem trong data.doan
  let tap = '';
  let notice = null;    // {kind, text} hiện dưới ô tiếng Việt sau khi render lại

  document.addEventListener('click', (e) => {
    const b = e.target.closest('.badge-do');
    if (!b) return;
    e.preventDefault();
    open(b.dataset.tap || '');
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

  async function open(t) {
    close(true);
    tap = t;
    dlg = document.createElement('div');
    dlg.className = 'modal';
    dlg.innerHTML = `
      <div class="modal-card trongmodal">
        <div class="modal-head">
          <b>🔴 Đoạn tô đỏ cần kiểm — tập ${esc(t)}</b>
          <span class="spacer"></span>
          <button type="button" class="small modal-x">✕</button>
        </div>
        <div class="modal-body"><p class="hint">Đang đọc gemini_result.docx…</p></div>
        <div class="modal-foot">
          <span class="hint">Đoạn này Gemini dịch được nhờ câu nhắc sau khi từ chối, hoặc nhờ chat mới (lượt 2)
            — đối chiếu tiếng Trung bên trái, sửa chữ bên phải nếu cần, rồi ✔ Đã kiểm để bỏ màu đỏ
            trong gemini_result.docx (file cũ được sao lưu cạnh đó).</span>
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
      const resp = await fetch(`/api/doan-do?tap=${encodeURIComponent(t)}`, { credentials: 'same-origin' });
      j = await resp.json();
    } catch (_) {
      if (body()) body().innerHTML = '<p class="warn">Không đọc được dữ liệu — server còn chạy không?</p>';
      return;
    }
    if (!dlg) return;                                   // đã đóng trong lúc chờ
    if (j.loi) { body().innerHTML = `<p class="warn">${esc(j.loi)}</p>`; return; }
    if (!j.doan || !j.doan.length) {
      body().innerHTML = `<p class="empty">Tập ${esc(t)} không còn đoạn tô đỏ nào trong gemini_result.docx.</p>`;
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
    const tabs = data.doan.map((x, i) =>
      `<button type="button" class="trong-tab${x.xong ? ' xong' : ' do'}${i === cur ? ' dang' : ''}"
               data-i="${i}">Đoạn ${x.j}${x.xong ? ' ✓' : ''}</button>`).join('');
    const conLai = data.doan.filter((x) => !x.xong).length;
    const trangThai = d.xong ? 'đã kiểm ✓' : 'đang TÔ ĐỎ — cần kiểm';
    const vi = d.draft != null ? d.draft : (d.vi || '');
    body().innerHTML = `
      <div class="trong-tabs">${tabs}
        <span class="hint">${conLai} đoạn còn đỏ / ${data.total} đoạn của tập</span></div>
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
