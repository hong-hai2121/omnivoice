import { TabDriver } from "./driver.js";
import { observeUpload } from "./upload.js";
import { auditCaption } from "./caption.js";
import { matchContentPost, postTitle, postEpisode } from './posts.js';
import { pageTask } from "./dom.js";
import { isTikTok, validateJob, episodeKey, statusGroup, TIKTOK_UPLOAD_URL, TIKTOK_CONTENT_URL } from "./model.js";

let running = null;
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const dashboard = chrome.runtime.getURL("dashboard.html");
const sameReceipt = (a, b) => {
  if (a === b) return true;
  if (!a || !b || typeof a !== 'object' || typeof b !== 'object' || Array.isArray(a) !== Array.isArray(b)) return false;
  const keys = Object.keys(a);
  return keys.length === Object.keys(b).length && keys.every(key => Object.hasOwn(b, key) && sameReceipt(a[key], b[key]));
};
const canResumeConfirmation = (receipt, request) => request.type === 'fill' && request.publish === true &&
  receipt.state === 'uncertain' && !receipt.confirmation && receipt.video === request.row.video && receipt.date === request.row.gio_dang &&
  (receipt.tabId === undefined || receipt.tabId === Number(request.tabId)) &&
  (receipt.schedule === undefined ? request.schedule === true : receipt.schedule === request.schedule);
chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {});
chrome.debugger.onDetach.addListener(source => {
  if (running?.tabId === source.tabId && !running.detaching) running.cancelled = true;
});

async function run(request, token) {
  const log = [];
  const captionTrace = [];
  let titleWarning = false;
  let stage = "Kiểm tra dữ liệu";
  const report = async (status, message) => {
    log.push(new Date().toLocaleTimeString("vi-VN") + "  " + message);
    await chrome.storage.local.set({ progress: { status, rowId: request.type === "inspect" ? undefined : request.row?.id,
      version: chrome.runtime.getManifest().version, updatedAt: new Date().toISOString(), log: [...log] } });
    if (request.row?.id && request.type !== "inspect") {
      const { rowResults = {} } = await chrome.storage.local.get("rowResults");
      rowResults[request.row.id] = { trang_thai: status, ghi_chu: message, statusOrigin: "local" };
      await chrome.storage.local.set({ rowResults });
    }
  };
  const check = async () => {
    if (token.cancelled) throw new Error("Da dung thao tac. Ban nhap tren TikTok duoc giu lai.");
    const tab = await chrome.tabs.get(token.tabId);
    if (!isTikTok(tab.url)) throw new Error("Tab khong con o TikTok Studio.");
  };
  const driver = new TabDriver(token.tabId, check, request.selectors);
  const command = (method, params = {}, sessionId = driver.current?.sessionId) => driver.command(method, params, sessionId);
  const dom = (...args) => driver.dom(...args);
  const key = async (key, code, windowsVirtualKeyCode, modifiers = 0, text) => {
    await command("Input.dispatchKeyEvent", { type: "keyDown", key, code, windowsVirtualKeyCode, nativeVirtualKeyCode: windowsVirtualKeyCode, modifiers, ...(text ? { text, unmodifiedText: text } : {}) });
    await command("Input.dispatchKeyEvent", { type: "keyUp", key, code, windowsVirtualKeyCode, nativeVirtualKeyCode: windowsVirtualKeyCode, modifiers });
  };
  const snapshot = async label => {
    const value = await dom("captionSnapshot");
    // Keep the first steps too (where a lost title shows up) and a short HTML excerpt.
    captionTrace.push({ step: label, at: new Date().toISOString(), ...value, html: value.html?.slice(0, 3000) });
    if (captionTrace.length > 60) captionTrace.splice(10, 1);
    return value;
  };
  const checkCaption = async (label, tags) => {
    const value = await snapshot(label);
    const state = auditCaption(value, request.row.tieu_de, tags);
    if (!state.present) throw new Error("Không thấy ô mô tả khi đọc lại.");
    if (!state.tagsMatch) throw new Error(`Hashtag chưa khớp. Thiếu: ${state.missing.join(" ") || "không"}; thừa/sai: ${state.extra.join(" ") || "không"}. Chưa bấm đăng.`);
    if (!state.titleMatches) {
      // Only a near-identical title may pass on a warning; a missing or different one never posts.
      if (!state.titleClose) throw new Error(`Tiêu đề chưa khớp: ô mô tả đang có "${state.actualTitle || "(trống)"}". Chưa bấm đăng.`);
      if (!request.schedule || !request.publish) throw new Error("Tiêu đề chưa khớp sau khi điền. Kiểm tra nội dung trên TikTok.");
      titleWarning = true;
      await report("running", `Cảnh báo: tiêu đề khác nội dung dự kiến. Vẫn tiếp tục theo lựa chọn Đặt ngày giờ + Bấm Đăng / Lên lịch. Tiêu đề hiện tại: ${state.actualTitle}`);
    }
    return value.text;
  };
  const waitFor = async (fn, timeout, message) => {
    const end = Date.now() + timeout;
    while (Date.now() < end) {
      await check();
      if (await fn()) return;
      await sleep(500);
    }
    throw new Error(message);
  };
  const verifySubmission = async label => {
    if (!await dom('draftCheck', { video: request.row.video })) throw new Error('Video trong ban nhap da thay doi. Dung truoc khi dang.');
    const caption = await checkCaption(label, request.row.hashtag.trim().split(/\s+/).filter(Boolean));
    const [date, time] = (request.row.gio_dang || '').split('T');
    if (request.schedule) {
      validateJob(request.row, true);
      if (!await dom('scheduleCheck', { date, time })) throw new Error('Ngay/gio da thay doi. Dung truoc khi dang.');
    } else if (!await dom('immediateCheck')) throw new Error('TikTok dang bat Len lich. Bat Len lich trong extension hoac tat tren TikTok truoc khi dang ngay.');
    if (!(await dom('uploadState')).ready) throw new Error('Video chua tai thanh cong 100%. Chua bam xac nhan.');
    return { video: request.row.video, schedule: request.schedule, date, time, caption, authorized: true };
  };
  const saveSubmission = async (key, receipt) => {
    const { submissions = {} } = await chrome.storage.local.get('submissions');
    submissions[key] = receipt;
    await chrome.storage.local.set({ submissions });
  };
  const newSubmission = previous => {
    const receipt = { state: 'uncertain', video: request.row.video, date: request.row.gio_dang,
      title: request.row.tieu_de, schedule: request.schedule, tabId: token.tabId, at: new Date().toISOString() };
    if (previous) {
      const { previousAttempts = [], ...lastAttempt } = previous;
      receipt.previousAttempts = [...previousAttempts, lastAttempt];
      receipt.repostAuthorizedAt = receipt.at;
    }
    return receipt;
  };
  const finishSubmission = async (key, receipt, resume = false) => {
    if (resume && (await dom('publishOutcome')).state !== 'confirmation') throw new Error('Lan bam truoc chua ro ket qua va khong con dung hop thoai cho xac nhan. Kiem tra TikTok; khong bam lai nut dang.');
    let checkingContent = false, contentMessage = '';
    await waitFor(async () => {
      let outcome;
      try { outcome = await driver.publicationState(); }
      catch { driver.current = null; return false; }
      if (outcome.state === 'content') {
        stage = 'Đối chiếu danh sách bài đăng';
        if (!checkingContent) {
          checkingContent = true;
          await report('running', 'Đã chuyển sang Nội dung. Đang đối chiếu tiêu đề và trạng thái bài trên TikTok...');
        }
        if (!outcome.content.ready) return false;
        const previous = receipt.previousAttempts || [];
        const matched = matchContentPost(outcome.content.posts, { title: receipt.caption || receipt.title || request.row.tieu_de,
          schedule: request.schedule, date: request.row.gio_dang, excludeIds: previous.map(attempt => attempt.postEvidence?.id).filter(Boolean) });
        contentMessage = matched.message || '';
        if (matched.state !== 'matched') return false;
        if (previous.some(attempt => !attempt.postEvidence?.id && (!request.schedule || attempt.date === receipt.date))) {
          contentMessage = 'Tiêu đề khớp nhưng lần đăng lại chưa phân biệt được với bài cũ. Kiểm tra danh sách trên TikTok.';
          return false;
        }
        receipt.postEvidence = { ...matched.post, source: 'content-list', matchedBy: 'title', checkedAt: new Date().toISOString() };
        return true;
      }
      if (['error', 'dialog'].includes(outcome.state)) throw new Error('Can kiem tra TikTok: ' + outcome.message);
      if (outcome.state === 'confirmation' && !receipt.confirmation && outcome.ready) {
        stage = 'Xác nhận Đăng ngay';
        const verified = await verifySubmission('Trước xác nhận Đăng ngay');
        receipt.caption = verified.caption;
        receipt.confirmation = { kind: outcome.kind, state: 'attempted', at: new Date().toISOString() };
        // Reserve the confirmation before clicking; even an uncertain response must not repeat it.
        await saveSubmission(key, receipt);
        await dom('confirmPublish', verified);
        await report('running', 'Đã bấm Đăng ngay trong hộp thoại kiểm tra video chưa hoàn tất. Đang chờ TikTok xác nhận kết quả.');
      }
      return outcome.state === 'success';
    }, 45_000, 'Da bam nut nhung chua xac nhan thanh cong. Kiem tra TikTok; khong chay lai de tranh trung video.')
      .catch(error => { if (contentMessage) error.message += ' ' + contentMessage; throw error; });
    receipt.state = 'success';
    await saveSubmission(key, receipt);
    const confirmation = receipt.postEvidence
      ? `Đã thấy đúng tiêu đề trong Nội dung: ${receipt.postEvidence.kind === 'scheduled' ? 'đã lên lịch' : 'đã đăng'} · ${receipt.postEvidence.stage} · ${receipt.postEvidence.url}`
      : (request.schedule ? 'TikTok da xac nhan len lich thanh cong.' : 'TikTok da xac nhan dang thanh cong.');
    await report('done', confirmation + (titleWarning ? ' Có cảnh báo tiêu đề khác nội dung dự kiến.' : ''));
  };
  try {
    await check();
    if (request.type !== "inspect") validateJob(request.row, request.schedule);
    const receiptKey = request.row && (episodeKey(request.row.video) || request.row.video.toLowerCase());
    let previousSubmission, repost = false;
    if (request.publish) {
      const { submissions = {} } = await chrome.storage.local.get("submissions");
      previousSubmission = submissions[receiptKey];
      repost = Object.hasOwn(request.repostReceipts || {}, receiptKey);
      if (repost && (!previousSubmission || !sameReceipt(previousSubmission, request.repostReceipts[receiptKey]))) throw new Error('Bien nhan da thay doi. Xac nhan lai yeu cau dang lai.');
      if (previousSubmission && !repost && !canResumeConfirmation(previousSubmission, request)) throw new Error("Video nay da co lan bam Dang / Len lich. Kiem tra TikTok; chon Cho phep dang lai neu muon dang them lan nua.");
    }
    let tab = await chrome.tabs.get(token.tabId);
    if (request.type === 'prepare' && (request.freshUpload || /^\/tiktokstudio\/content\/?$/.test(new URL(tab.url).pathname))) {
      stage = 'Mở trang tải lên';
      await report('running', 'Đang tự mở trang tải lên TikTok cho video tiếp theo...');
      await check();
      await chrome.tabs.update(token.tabId, { url: TIKTOK_UPLOAD_URL });
      await waitFor(async () => {
        tab = await chrome.tabs.get(token.tabId);
        return tab.status === 'complete' && /^\/tiktokstudio\/upload\/?$/.test(new URL(tab.url).pathname);
      }, 30_000, 'Trang tải lên TikTok chưa sẵn sàng sau 30 giây. Chưa nạp video; kiểm tra kết nối hoặc đăng nhập.');
    }
    if (request.type !== "inspect" && !/\/(tiktokstudio|creator-center)\/upload/.test(new URL(tab.url).pathname)) {
      throw new Error("Mo trang Tai len TikTok Studio truoc khi chay.");
    }
    await report("running", "Ket noi tab TikTok...");
    await driver.attach();
    if (request.type === "inspect") {
      const diagnostic = await driver.inspect(true);
      await report("done", "Da doc cau truc trang.");
      return { diagnostic };
    }
    if (previousSubmission && !repost) {
      stage = 'Tiếp tục xác nhận Đăng ngay';
      await waitFor(() => driver.findEditor(), 8000, 'Khong con ban nhap de xac nhan. Kiem tra ket qua tren TikTok.');
      await report('running', 'Tiếp tục hộp thoại của lần bấm trước; không nạp video, điền lại nội dung hoặc bấm lại Lên lịch.');
      await finishSubmission(receiptKey, previousSubmission, true);
      return {};
    }
    if (repost && request.type === 'fill') {
      stage = 'Kiểm tra yêu cầu đăng lại';
      await waitFor(() => driver.findEditor(), 8000, 'Khong con ban nhap de dang lai. Mo trang tai len va dung Nap & dien.');
      const outcome = await dom('publishOutcome');
      if (outcome.state === 'confirmation') {
        if (!canResumeConfirmation({ ...previousSubmission, state: 'uncertain', confirmation: undefined }, request)) throw new Error('Hop thoai dang mo khong khop video, tab hoac lich cua lan truoc. Chua bam xac nhan.');
        await report('running', 'Đã xác nhận thử lại Đăng ngay; giữ nguyên video, mô tả và lịch. Biên nhận cũ được giữ trong lịch sử.');
        await finishSubmission(receiptKey, newSubmission(previousSubmission), true);
        return {};
      }
      if (outcome.state !== 'waiting') throw new Error('Trang dang co thong bao can kiem tra. Chua dang lai: ' + outcome.message);
    }
    if (request.type === "prepare") {
      stage = "Nạp video";
      let input, opened = false;
      await waitFor(async () => {
        input = await driver.fileInput();
        if (input) return true;
        if (!opened) opened = await driver.openFileControl();
        return false;
      }, 30_000, "Chua thay o tai video sau 30 giay. Mo trang Tai len, kiem tra dang nhap. Chan doan da duoc luu.");
      if (!input.objectId) throw new Error("Khong truy cap duoc o tai video.");
      let probeId;
      try {
        const probe = await command("Runtime.callFunctionOn", { objectId: input.objectId, functionDeclaration: observeUpload.toString() }, input.sessionId);
        probeId = probe.result?.objectId;
        if (!probeId || probe.exceptionDetails) throw new Error("Không khởi tạo được bước xác nhận file. Chưa nạp video.");
        await command("DOM.setFileInputFiles", { objectId: input.objectId, files: [request.row.video] }, input.sessionId);
        const selected = await command("Runtime.callFunctionOn", {
          objectId: probeId, functionDeclaration: "function() { return this.read(); }",
          returnByValue: true, awaitPromise: true,
        }, input.sessionId);
        const file = selected.result?.value;
        if (!file) throw new Error("Không đọc được file từ ô tải hoặc sự kiện chọn file. Kiểm tra bản nháp trước khi nạp lại. File: " + request.row.video);
        if (!file.size || !file.readable) throw new Error(`Chrome không đọc được nội dung video (file mất, rỗng hoặc không có quyền đọc). File: ${request.row.video}; dung lượng: ${file.size}; ${file.readError || "không đọc được byte đầu"}`);
        if (file.name.normalize("NFC") !== request.row.video.split(/[\\/]/).at(-1).normalize("NFC")) throw new Error(`File nhận được không khớp: ${file.name}. File đã chọn: ${request.row.video}`);
      } finally {
        // Cleanup must also run after cancellation, without invoking check().
        const target = { tabId: token.tabId, ...(input.sessionId ? { sessionId: input.sessionId } : {}) };
        if (probeId) await chrome.debugger.sendCommand(target, "Runtime.callFunctionOn", { objectId: probeId, functionDeclaration: "function() { this.dispose(); }" }).catch(() => {});
        for (const objectId of [probeId, input.objectId].filter(Boolean)) await chrome.debugger.sendCommand(target, "Runtime.releaseObject", { objectId }).catch(() => {});
      }
      await report("running", "Da nap file. Dang cho o mo ta...");
    }
    stage = "Điền mô tả / hashtag";
    await waitFor(() => driver.findEditor(), 120_000, "Chua thay o mo ta. Kiem tra tai video / dang nhap, roi bam Dien tiep.");
    if (request.type === "prepare") await dom("draftMark", { video: request.row.video });
    if (request.publish && !await dom("draftCheck", { video: request.row.video })) throw new Error("Chua xac nhan ban nhap nay duoc nap tu video da chon. Khong tu dong dang; kiem tra video tren TikTok.");
    const knownDraft = await dom("draftCheck", { video: request.row.video });
    const tags = request.row.hashtag.trim().split(/\s+/).filter(Boolean);
    const sameEditor = (a, b) => a?.present && b?.present && a.editorId === b.editorId && a.editorKey === b.editorKey;
    const neutralFocus = state => !state.dialogOpen && (state.focused || ['BODY', 'HTML'].includes(state.active?.tag));
    const focusError = () => new Error("Ô mô tả đã mất focus hoặc có hộp thoại. Dừng để không gửi phím nhầm vào nút đăng / ô khác.");
    let expectedEditor;
    const verifyEditor = async (focused = true) => {
      const state = await dom("captionSnapshot");
      if (!sameEditor(state, expectedEditor)) {
        if (!neutralFocus(state)) throw focusError();
        const error = new Error("TikTok vừa tạo lại ô mô tả trong lúc điền.");
        error.code = 'CAPTION_REPLACED'; throw error;
      }
      if (!state.editable || state.dialogOpen || (focused && !state.focused)) throw focusError();
      return state;
    };
    const focusCaption = async (initial = false) => {
      const state = await verifyEditor(false);
      if (!initial && !neutralFocus(state)) throw focusError();
      await dom("captionFocusOnly");
      await verifyEditor();
    };
    const stableCaption = async () => {
      let previous, stableSince = 0;
      await waitFor(async () => {
        if (!await driver.findEditor()) { previous = null; return false; }
        const state = await dom("captionSnapshot");
        if (state.dialogOpen) throw focusError();
        if (!state.editable) { previous = null; return false; }
        if (!sameEditor(previous, state) || previous.text !== state.text) stableSince = Date.now();
        previous = state;
        return Date.now() - stableSince >= 1000;
      }, 10_000, "Ô mô tả chưa ổn định. Giữ bản nháp và thử Điền tiếp sau khi TikTok khởi tạo xong.");
      return previous;
    };
    const appendTag = async tag => {
      await focusCaption();
      // Native selection events keep the editor's internal caret outside hashtag entities.
      await key("End", "End", 35, 2);
      await verifyEditor();
      await key("ArrowRight", "ArrowRight", 39);
      await verifyEditor();
      await key(" ", "Space", 32, 0, " ");
      await verifyEditor();
      await command("Input.insertText", { text: tag });
      await snapshot("Đã nhập " + tag);
      await sleep(1000);
      await snapshot("Trước Enter " + tag);
      await verifyEditor();
      await key("Enter", "Enter", 13, 0, "\r");
      await sleep(350);
      const value = await snapshot("Sau Enter " + tag);
      await verifyEditor(false);
      return value;
    };
    // TikTok has wiped a freshly typed title (2/10, tập 117): read it back and retype it
    // before any hashtag, instead of finding out only at the final check.
    const typeTitle = async () => {
      const title = request.row.tieu_de.trim();
      for (let tries = 0; ; tries++) {
        await key("a", "KeyA", 65, 2);
        await verifyEditor();
        if (tries) { await key("Backspace", "Backspace", 8); await verifyEditor(); }
        await command("Input.insertText", { text: title });
        await verifyEditor();
        await sleep(500);
        const state = auditCaption(await snapshot(tries ? `Đọc lại tiêu đề (lần ${tries + 1})` : "Sau khi nhập tiêu đề"), title, []);
        if (state.titleClose && !state.actualTags.length) return;
        if (tries >= 2) throw new Error(`Tiêu đề chưa khớp sau ${tries + 1} lần nhập: ô mô tả đang có "${state.actualTitle || "(trống)"}". Chưa nhập hashtag, chưa bấm đăng.`);
        await report("running", `Tiêu đề chưa vào ô mô tả (đang có "${state.actualTitle || "trống"}"). Xóa và nhập lại lần ${tries + 2}.`);
        await focusCaption();
      }
    };
    for (let attempt = 0; attempt < 2; attempt++) {
      expectedEditor = await stableCaption();
      try {
        if (knownDraft && !await dom("draftCheck", { video: request.row.video })) throw new Error("Video trong bản nháp đã đổi. Không tự điền lại mô tả.");
        if (attempt && !neutralFocus(expectedEditor)) throw focusError();
        await focusCaption(attempt === 0);
        await typeTitle();
        const completed = [];
        for (const tag of tags) {
          completed.push(tag);
          let value = await appendTag(tag);
          let state = auditCaption(value, request.row.tieu_de, completed);
          // One bounded repair pass; never keep appending duplicates to a broken editor.
          if (state.missing.length && !state.extra.length) {
            await report("running", "Nhập lại hashtag bị mất: " + state.missing.join(" "));
            for (const missing of state.missing) value = await appendTag(missing);
            state = auditCaption(value, request.row.tieu_de, completed);
          }
          if (!state.tagsMatch) throw new Error(`Sau Enter ${tag}, hashtag chưa được giữ đủ. Thiếu: ${state.missing.join(" ")}; thừa/sai: ${state.extra.join(" ")}. Đã lưu từng bước để kiểm tra.`);
        }
        await verifyEditor(false);
        const filled = auditCaption(await snapshot("Kiểm tra tiêu đề sau hashtag"), request.row.tieu_de, tags);
        if (!filled.titleClose) {
          const error = new Error(`Tiêu đề bị mất sau khi nhập hashtag: ô mô tả đang có "${filled.actualTitle || "(trống)"}".`);
          error.code = 'TITLE_LOST'; throw error;
        }
        await checkCaption("Sau khi điền", tags);
        break;
      } catch (error) {
        if (!['CAPTION_REPLACED', 'TITLE_LOST'].includes(error.code)) throw error;
        const lost = error.code === 'TITLE_LOST';
        await snapshot(lost ? "Tiêu đề bị mất" : "Ô mô tả bị tạo lại");
        if (attempt) throw new Error(lost ? `${error.message} Đã điền lại một lần vẫn mất. Chưa bấm đăng.` : "TikTok tiếp tục tạo lại ô mô tả sau một lần thử lại. Chưa bấm đăng; chờ trang ổn định rồi Điền tiếp.");
        if (!lost && (!knownDraft || !await dom("draftCheck", { video: request.row.video }))) throw new Error("Video trong bản nháp đã đổi hoặc chưa được xác nhận. Không tự điền lại mô tả.");
        await report("running", lost ? "Tiêu đề bị mất sau khi nhập hashtag. Xóa ô mô tả, điền lại tiêu đề và hashtag một lần."
          : "TikTok vừa tạo lại ô mô tả. Chờ ổn định rồi điền lại tiêu đề và hashtag một lần trên cùng video.");
      }
    }
    await report("running", "Đã điền và đọc lại mô tả/hashtag." + (titleWarning ? " Có cảnh báo tiêu đề." : ""));
    if (tags.length) await report("running", `Hashtag: đã nhập ${tags.length} mục, mỗi mục cách trước, chờ 1 giây rồi Enter; đã đọc lại nội dung.`);
    if (request.schedule) {
      stage = "Bật lên lịch";
      const state = await dom("schedule");
      await report("running", state === "already" ? "Len lich da bat, giu nguyen." : "Da bat Len lich.");
      stage = "Tìm ô ngày / giờ";
      await waitFor(() => dom("scheduleReady"), 8000, "Chua tim thay o ngay/gio. Xuat chan doan de kiem tra.");
      const [date, time] = request.row.gio_dang.split("T");
      stage = "Chọn ngày " + date;
      if (await dom("dateCheck", { date })) {
        await report("running", "Ngày trên TikTok đã khớp, giữ nguyên.");
      } else if (await dom("openDate", { date })) {
        await waitFor(() => dom("datePickerReady", { date }), 4000, "Popup ngay chua mo sau khi bam o ngay.");
        const [year, month] = date.split('-').map(Number);
        const targetMonth = year * 12 + month - 1;
        let picked = false;
        for (let attempt = 0; attempt <= 12; attempt++) {
          let calendar = await dom("calendarState");
          if (calendar.count === 1) {
            await waitFor(async () => (await dom("calendarState")).gridValid, 4000, "Chua doc duoc thang/nam va luoi ngay cua popup TikTok.");
            calendar = await dom("calendarState");
          }
          if (await dom("pickDate", { value: date }) === "picked") { picked = true; break; }
          if (attempt === 12) break;
          const direction = calendar.count ? Math.sign(targetMonth - calendar.index) : 1;
          if (!direction || !await dom("changeMonth", { direction })) break;
          if (calendar.count) {
            await waitFor(async () => {
              const next = await dom("calendarState");
              return next.count === 1 && next.gridValid && next.index === calendar.index + direction;
            }, 4000, "Lich chua chuyen dung thang. Chua bam tiep de tranh chon nham ngay.");
          } else await sleep(300);
        }
        if (!picked) throw new Error("Chua nhan dien duoc ngay trong lich. Xuat chan doan khi lich dang mo.");
      } else await dom("setDate", { value: date });
      await waitFor(() => dom("dateCheck", { date }), 4000, "Ngay doc lai khong khop sau khi chon. Chua chon gio / dang.");
      stage = "Chọn giờ " + time;
      if (await dom("timeCheck", { time })) {
        await report("running", "Giờ trên TikTok đã khớp, giữ nguyên.");
      } else if (await dom("openTime")) {
        await waitFor(() => dom("timePickerReady"), 4000, "Popup gio chua mo sau khi bam o gio.");
        const [hour, minute] = time.split(":");
        if (!await dom("pickTime", { part: "hour", value: hour })) throw new Error("Chua nhan dien duoc cot gio. Xuat chan doan khi bang gio dang mo.");
        await waitFor(() => dom("timePartCheck", { part: "hour", value: hour }), 4000, "Gio doc lai khong khop sau khi chon.");
        await dom("openTime");
        await waitFor(() => dom("timePickerReady"), 4000, "Popup phut chua san sang sau khi chon gio.");
        if (!await dom("pickTime", { part: "minute", value: minute })) throw new Error("Chua nhan dien duoc cot phut. Xuat chan doan khi bang gio dang mo.");
      } else await dom("setTime", { value: time });
      await sleep(500);
      stage = "Đọc lại ngày / giờ";
      await waitFor(() => dom("scheduleCheck", { date, time }), 4000, "Ngay/gio doc lai khong khop. Chua xac nhan lich.");
      await report("running", "Da doc lai dung ngay/gio tren bieu mau.");
    }
    if (request.publish) {
      stage = "Đăng / lên lịch";
      await report("running", "Dang cho tai/xu ly video: cần thanh tải success 100% và nút Đăng / Lên lịch sẵn sàng...");
      await waitFor(() => dom("publishReady", { schedule: request.schedule }), 30 * 60_000, "Chưa xác nhận tải success 100% hoặc nút Đăng / Lên lịch chưa sẵn sàng sau 30 phút.");
      const verified = await verifySubmission("Trước khi đăng");
      const priorOutcome = await dom('publishOutcome');
      if (priorOutcome.state !== 'waiting') throw new Error('Trang dang co thong bao/hoi thoai can kiem tra. Khong bam dang khi ket qua mo ho: ' + priorOutcome.message);
      const receipt = newSubmission(repost ? previousSubmission : null);
      receipt.caption = verified.caption;
      // Persist before clicking: a worker restart must never repeat a submission.
      await saveSubmission(receiptKey, receipt);
      await dom("publish", { schedule: request.schedule, authorized: true });
      await finishSubmission(receiptKey, receipt);
    } else await report("review", "Cho kiem tra tren TikTok. Chua bam Dang / Len lich; video co the van dang tai hoac xu ly.");
    return {};
  } catch (error) {
    let diagnostic = { version: chrome.runtime.getManifest().version, selectors: request.selectors || {}, stage, error: error.message,
      expectedCaption: request.row && { title: request.row.tieu_de, hashtag: request.row.hashtag }, captionTrace,
      expectedSchedule: request.schedule ? request.row?.gio_dang : null, capturedAt: new Date().toISOString() };
    if (driver.attached && !token.cancelled) {
      try { diagnostic = { ...diagnostic, ...await driver.inspect(true) }; } catch (captureError) { diagnostic.captureError = captureError.message; }
    }
    if (!token.cancelled) {
      await chrome.storage.local.set({ lastDiagnostic: diagnostic });
      error.message = `[${stage}] ${error.message}`;
    }
    await report(token.cancelled ? "stopped" : "error", error.message);
    throw error;
  } finally {
    // Every run (done, error or stopped) keeps its caption steps for later diagnosis.
    if (captionTrace.length) await chrome.storage.local.set({ lastCaptionTrace: { at: new Date().toISOString(),
      version: chrome.runtime.getManifest().version, rowId: request.row?.id, title: request.row?.tieu_de, stopped: token.cancelled, trace: captionTrace } }).catch(() => {});
    token.detaching = true;
    await driver.close();
    token.detaching = false;
  }
}

async function checkContentList(request, token) {
  const rows = request.rows || [request.row];
  if (!rows.length || rows.some(row => !row?.id || typeof row.tieu_de !== 'string' || !row.tieu_de.trim())) throw new Error('Chọn video có tiêu đề để kiểm tra.');
  const check = async () => {
    if (token.cancelled) throw new Error('Đã dừng kiểm tra bài đăng.');
    const tab = await chrome.tabs.get(token.tabId);
    if (!isTikTok(tab.url) || !/^\/tiktokstudio\/content\/?$/.test(new URL(tab.url).pathname)) throw new Error('Chọn tab Nội dung TikTok Studio để kiểm tra bài đăng.');
  };
  const driver = new TabDriver(token.tabId, check);
  try {
    await check(); await driver.attach();
    await chrome.storage.local.set({ progress: { status: 'running', version: chrome.runtime.getManifest().version,
      log: ['Đang đọc danh sách bài trên trang Nội dung TikTok...'], updatedAt: new Date().toISOString() } });
    let content;
    for (let attempt = 0; attempt < 30; attempt++) {
      await check();
      try { content = await driver.evaluate(null, 'contentPosts'); } catch { content = null; }
      if (content?.ready) break;
      await sleep(500);
    }
    if (!content?.ready) throw new Error('Chưa đọc được bảng Nội dung TikTok. Giữ trang mở rồi kiểm tra lại.');
    await check();
    const { rowResults = {}, submissions = {} } = await chrome.storage.local.get(['rowResults', 'submissions']);
    const results = [], checkedAt = new Date().toISOString();
    for (const row of rows) {
      const match = matchContentPost(content.posts, { title: row.tieu_de });
      const key = episodeKey(row.video) || String(row.video || '').toLowerCase();
      if (match.state === 'matched') {
        const postEvidence = { ...match.post, source: 'content-list', matchedBy: 'title', checkedAt };
        const note = `Đã thấy bài ${match.post.kind === 'scheduled' ? 'đã lên lịch' : 'đã đăng'}: ${match.post.stage} · ${match.post.url}`;
        rowResults[row.id] = { trang_thai: 'done', ghi_chu: note, statusOrigin: 'local', postEvidence };
        if (key) submissions[key] = { ...(submissions[key] || { video: row.video, title: row.tieu_de, date: row.gio_dang, schedule: match.post.kind === 'scheduled', at: null }), state: 'success', postEvidence };
        results.push({ id: row.id, state: 'matched', message: note });
      } else {
        // A virtualized table can omit an older post; absence must not erase existing success.
        if (statusGroup(rowResults[row.id] || row) !== 'done') rowResults[row.id] = { trang_thai: 'review', ghi_chu: match.message, statusOrigin: 'local' };
        results.push({ id: row.id, state: match.state, message: match.message });
      }
    }
    await check();
    await chrome.storage.local.set({ rowResults, submissions, progress: { status: 'done', version: chrome.runtime.getManifest().version, updatedAt: checkedAt,
      log: [`Đối chiếu ${rows.length} video với ${content.posts.length} bài đang hiển thị: ${results.filter(result => result.state === 'matched').length} khớp.`,
        ...results.map((result, index) => `${rows[index].tieu_de}: ${result.message}`)] } });
    return { results };
  } catch (error) {
    await chrome.storage.local.set({ progress: { status: token.cancelled ? 'stopped' : 'error', version: chrome.runtime.getManifest().version,
      updatedAt: new Date().toISOString(), log: [error.message] } });
    throw error;
  } finally {
    token.detaching = true;
    await driver.close();
    token.detaching = false;
  }
}

/* Read TikTok Studio's post list (scheduled + published) in a temporary tab, read-only.
   The tab is shown briefly because hidden tabs do not render the virtualized table. */
async function readPostList(request) {
  if (running) throw new Error("Đang có thao tác chạy. Chờ xong rồi cập nhật.");
  const token = { cancelled: false, reading: true };
  running = token;
  let tabId, previous;
  try {
    const own = request.windowId ? await chrome.windows.get(request.windowId).catch(() => null) : null;
    const win = own?.type === "normal" ? own : await chrome.windows.getLastFocused({ windowTypes: ["normal"] }).catch(() => null);
    [previous] = win ? await chrome.tabs.query({ active: true, windowId: win.id }) : [];
    tabId = (await chrome.tabs.create({ url: "about:blank", active: true, ...(win ? { windowId: win.id } : {}) })).id;
    await chrome.tabs.update(tabId, { url: TIKTOK_CONTENT_URL });
    const read = async (action, data = {}) => {
      const tab = await chrome.tabs.get(tabId);
      if (!isTikTok(tab.url)) return null;
      if (action !== "postProbe" && !/^\/tiktokstudio\/content\/?$/.test(new URL(tab.url).pathname)) {
        if (tab.status === "complete" && /login/.test(tab.url)) throw new Error("TikTok chưa đăng nhập trong profile này.");
        return null;
      }
      try {
        const [frame] = await chrome.scripting.executeScript({ target: { tabId }, func: pageTask, args: [action, data] });
        return frame?.result ?? null;
      } catch { return null; } // The SPA can replace the document between polls.
    };
    const targets = (request.targets || []).map(item => ({ title: postTitle(item.title), episode: item.episode ?? postEpisode(item.title) }));
    const found = new Map();
    let total = null, complete = false, first = 0, idle = 0;
    const end = Date.now() + 30_000;
    try {
      // Wait for the first rows; an account without posts shows an empty table for a while.
      while (Date.now() < end) {
        const content = await read("postList");
        if (content?.ready) {
          total = content.total ?? total;
          for (const post of content.posts) found.set(post.id, post);
          if (found.size || (first && Date.now() - first > 4000)) break;
          first ||= Date.now();
        }
        await sleep(700);
      }
      if (!first && !found.size) {
        const page = (await chrome.tabs.get(tabId).catch(() => null))?.url || "";
        throw new Error(`Không đọc được danh sách Bài đăng trên TikTok Studio sau 30 giây (trang đang mở: ${page.split("?")[0] || "không rõ"}).`);
      }
      // Scroll only as far as needed: stop once every target is found or the list is older than it.
      for (let round = 0; round < 40 && !complete; round++) {
        const numbers = [...found.values()].map(post => postEpisode(post.caption)).filter(value => value !== null);
        const oldest = numbers.length ? Math.min(...numbers) : null;
        const titles = new Set([...found.values()].map(post => postTitle(post.caption)));
        if (targets.every(item => titles.has(item.title) || (item.episode !== null && oldest !== null && oldest < item.episode))) break;
        if (total !== null && found.size >= total) { complete = true; break; }
        const step = await read("contentScroll");
        await sleep(900);
        const before = found.size;
        for (const post of (await read("postList"))?.posts || []) found.set(post.id, post);
        idle = found.size > before ? 0 : idle + 1;
        if (step?.atEnd && idle >= 2) complete = true;
        else if (!step?.moved && idle >= 3) break;
      }
    } catch (error) {
      // Keep what the page looked like so a changed TikTok layout can be diagnosed later.
      await chrome.storage.local.set({ lastPostRead: { at: new Date().toISOString(), version: chrome.runtime.getManifest().version,
        ok: false, error: error.message, found: found.size, tabUrl: (await chrome.tabs.get(tabId).catch(() => null))?.url,
        probe: await read("postProbe").catch(() => null) } });
      throw error;
    }
    if (total !== null && found.size >= total) complete = true;
    const posts = [...found.values()];
    await chrome.storage.local.set({ lastPostRead: { at: new Date().toISOString(), version: chrome.runtime.getManifest().version,
      ok: true, found: posts.length, total, complete, sample: posts.slice(0, 3), probe: posts.length ? null : await read("postProbe") } });
    return { list: { posts, total, complete, readAt: new Date().toISOString() } };
  } finally {
    if (tabId !== undefined) {
      const tab = await chrome.tabs.get(tabId).catch(() => null);
      await chrome.tabs.remove(tabId).catch(() => {});
      if (tab?.active && previous?.id !== undefined) await chrome.tabs.update(previous.id, { active: true }).catch(() => {});
    }
    if (running === token) running = null;
  }
}

async function runQueue(request) {
  if (running) throw new Error("Dang co thao tac chay. Dung hoac cho hoan tat.");
  const token = { tabId: Number(request.tabId), cancelled: false };
  running = token;
  try {
    if (request.type === 'checkPosts') return await checkContentList(request, token);
    const rows = request.rows || [request.row];
    if (!rows.length || rows.length > 1 && (!request.publish || request.type !== "prepare")) throw new Error("Chay nhieu video can bat Bam Dang / Len lich va dung Nap & dien.");
    if (request.type !== "inspect") for (const row of rows) validateJob(row, request.schedule);
    if (request.publish && rows.some(row => !String(row.tieu_de || "").trim())) {
      throw new Error("Có video chưa có tiêu đề. Nhập tiêu đề trước khi bật Bấm Đăng / Lên lịch.");
    }
    if (request.publish) {
      const { submissions = {} } = await chrome.storage.local.get("submissions");
      const keys = rows.map(row => episodeKey(row.video) || row.video.toLowerCase());
      if (new Set(keys).size !== keys.length) throw new Error("Hang doi co nhieu ban cua cung mot tap. Chi chon mot ban moi tap.");
      const approvals = request.repostReceipts || {};
      // Approval is scoped to selected videos and the exact receipts shown in the confirmation.
      if (Object.entries(approvals).some(([key, receipt]) => !keys.includes(key) || !submissions[key] || !sameReceipt(submissions[key], receipt))) throw new Error('Bien nhan da thay doi hoac khong thuoc video da chon. Xac nhan lai yeu cau dang lai.');
      if (keys.some((key, index) => submissions[key] && !Object.hasOwn(approvals, key) && !(rows.length === 1 && canResumeConfirmation(submissions[key], { ...request, row: rows[index] })))) throw new Error("Hang doi co video da bam Dang / Len lich. Kiem tra TikTok; chon Cho phep dang lai va xac nhan neu muon dang them lan nua.");
    }
    let result;
    for (const [index, row] of rows.entries()) {
      if (token.cancelled) throw new Error("Da dung hang doi.");
      result = await run({ ...request, row, freshUpload: index > 0 }, token);
    }
    return result;
  } finally { if (running === token) running = null; }
}

chrome.runtime.onMessage.addListener((request, sender, respond) => {
  if (sender.id !== chrome.runtime.id || sender.url !== dashboard) return false;
  if (request.type === "stop") {
    if (running) running.cancelled = true;
    respond({ ok: true }); return false;
  }
  if (request.type === "status") { respond({ ok: true, running: !!running && !running.reading }); return false; }
  if (request.type === "readPosts") {
    readPostList(request).then(result => respond({ ok: true, ...result }), error => respond({ ok: false, error: error.message }));
    return true;
  }
  if (!["prepare", "fill", "inspect", "checkPosts"].includes(request.type)) return false;
  runQueue(request).then(result => respond({ ok: true, ...result }), error => respond({ ok: false, error: error.message }));
  return true;
});
