/* Only this isolated content script touches Gemini's DOM. No page-supplied
 * messages, API keys, clipboard access or arbitrary JavaScript execution. */
(() => {
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  const visible = element => Boolean(element && element.getClientRects().length
    && getComputedStyle(element).visibility !== "hidden");
  const first = selectors => {
    for (const selector of selectors) {
      const element = [...document.querySelectorAll(selector)].find(visible);
      if (element) return element;
    }
    return null;
  };
  const editors = ["div.ql-editor[contenteditable='true']",
    "div[contenteditable='true'][role='textbox']", "textarea"];
  const generating = () => Boolean(first([
    "button[aria-label*='Stop response']", "button[aria-label*='Stop generating']",
    "button[aria-label*='Dừng']", "button.stop-button",
    "button:has(mat-icon[fonticon='stop'])"
  ]));
  let submitting = false;
  const completed = new Map();

  async function handle(message) {
    if (message.expires && Date.now() / 1000 >= message.expires) throw new Error("Lệnh đã hết hạn.");
    if (message.action === "ready") return {ready: Boolean(first(editors))};
    if (message.action === "responses") {
      for (const selector of message.selectors) {
        const elements = [...document.querySelectorAll(selector)];
        if (elements.length) return {texts: elements.map(e => e.innerText || ""), generating: generating()};
      }
      return {texts: [], generating: generating()};
    }
    if (message.action !== "submit") throw new Error("Lệnh không hỗ trợ.");
    if (submitting || generating()) throw new Error("Gemini vẫn đang trả lời. Đợi xong rồi chạy tiếp.");
    submitting = true;
    try {
      const editor = first(message.editor_selectors);
      if (!editor) throw new Error("Không thấy ô nhập. Kiểm tra đăng nhập Gemini.");
      if (typeof message.text !== "string" || !message.text.trim()) throw new Error("Nội dung gửi rỗng.");
      editor.focus();
      if (editor.tagName === "TEXTAREA") {
        Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value").set.call(editor, message.text);
        editor.dispatchEvent(new Event("input", {bubbles: true}));
      } else {
        const range = document.createRange();
        range.selectNodeContents(editor);
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
        if (!document.execCommand("insertText", false, message.text)) {
          throw new Error("Không dán được nội dung vào Gemini; chưa gửi đoạn này.");
        }
        editor.dispatchEvent(new InputEvent("input", {bubbles: true, inputType: "insertText", data: message.text}));
      }
      // Quill renders blank lines as <p><br></p> and alternates nbsp/space, so
      // compare with every run of whitespace collapsed; a truncated paste still differs.
      const normalize = text => text.replace(/\u00a0/g, " ").replace(/\s+/g, " ").trim();
      if (normalize(editor.value ?? editor.innerText) !== normalize(message.text)) {
        throw new Error("Nội dung trong ô nhập chưa khớp; đã dừng trước khi gửi.");
      }
      const deadline = Date.now() + 8000;
      while (Date.now() < deadline) {
        const button = first(message.send_selectors);
        if (button && !button.disabled && button.getAttribute("aria-disabled") !== "true") {
          button.click();
          // Click is not an acknowledgement (login dialogs or quota limits can
          // leave the prompt unsent). Never click a second time automatically.
          const acceptedBy = Date.now() + 8000;
          while (Date.now() < acceptedBy) {
            if (!editor.isConnected || !(editor.value ?? editor.innerText).trim() || generating()) {
              return {submitted: true};
            }
            await sleep(150);
          }
          throw new Error("Gemini chưa xác nhận nhận tin nhắn. Kiểm tra đăng nhập hoặc thông báo trên tab rồi chạy tiếp.");
        }
        await sleep(150);
      }
      throw new Error("Không thấy nút Gửi đang bật; chưa gửi đoạn này.");
    } finally {
      submitting = false;
    }
  }

  chrome.runtime.onMessage.addListener((message, sender, respond) => {
    if (sender.id !== chrome.runtime.id || message.source !== "omnivoice") return;
    if (message.id && completed.has(message.id)) {
      respond(completed.get(message.id));
      return;
    }
    handle(message).then(value => ({value}), error => ({error: error.message})).then(result => {
      if (message.id && message.action === "submit") {
        completed.set(message.id, result);
        if (completed.size > 20) completed.delete(completed.keys().next().value);
      }
      respond(result);
    });
    return true;
  });
})();
