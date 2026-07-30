// Nhật ký thời gian thực + nút Copy. Không có thư viện ngoài nào ngoài htmx.

(function () {
  const box = document.getElementById('logbox');
  const state = document.getElementById('logstate');
  const auto = document.getElementById('autoscroll');
  if (!box) return;

  const MAX_LINES = 1200;   // giữ màn hình nhẹ khi chạy nhiều giờ

  function append(text) {
    const atBottom = box.scrollTop + box.clientHeight >= box.scrollHeight - 40;
    box.append(text + '\n');
    while (box.childNodes.length > MAX_LINES) box.removeChild(box.firstChild);
    if (auto.checked && atBottom) box.scrollTop = box.scrollHeight;
  }

  let source;
  function connect() {
    source = new EventSource('/nhatky/stream');
    source.onopen = () => { state.textContent = 'đang theo dõi'; };
    source.onmessage = (e) => {
      try { append(JSON.parse(e.data)); } catch (_) { append(e.data); }
    };
    source.onerror = () => {
      state.textContent = 'mất kết nối — thử lại…';
      source.close();
      setTimeout(connect, 3000);   // server tắt/ngủ thì tự nối lại
    };
  }
  connect();

  // Nút 📋 Copy trong trang SEO.
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
