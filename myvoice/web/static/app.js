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
      if (row) flashRow(row, addSource(row.dataset.path));
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
          <button type="button" class="filerow" data-path="${esc(f.path)}" data-name="${esc(f.name)}">
            <span class="filerow-name">${esc(f.name)}</span>
            <span class="filerow-meta">${esc(f.size)} · ${esc(f.when)}</span>
          </button>`).join('')
          : '<p class="empty">Thư mục trống.</p>'}
        ${g.more ? `<p class="hint">…và ${g.more} file cũ hơn không hiện ở đây.</p>` : ''}
      </div>`).join('');
    dlg.querySelector('.modal-find').focus();
  }

  function flashRow(row, added) {
    const meta = row.querySelector('.filerow-meta');
    const old = meta.textContent;
    meta.textContent = added ? '✓ đã thêm' : 'đã có trong ô Nguồn';
    row.classList.add('filerow-hit');
    setTimeout(() => { meta.textContent = old; row.classList.remove('filerow-hit'); }, 1100);
  }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }
})();
