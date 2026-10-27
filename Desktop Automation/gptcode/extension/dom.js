// Serialized into the target tab. Keep all helpers inside this function.
export function pageTask(action, data = {}) {
  const normalize = value => String(value || "").normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "").replace(/[\u0110\u0111]/g, "d").toLowerCase().replace(/\s+/g, " ").trim();
  const visible = el => el.getClientRects().length > 0 && getComputedStyle(el).visibility !== "hidden";
  const all = selector => {
    const matches = [], visit = root => {
      matches.push(...root.querySelectorAll(selector));
      for (const el of root.querySelectorAll("*")) if (el.shadowRoot) visit(el.shadowRoot);
    };
    visit(document); return matches;
  };
  const unique = elements => elements.length === 1 ? elements[0] : null;
  const custom = name => data.selectors?.[name] ? unique(all(data.selectors[name]).filter(visible)) : null;
  const label = el => el.getAttribute("aria-label") ||
    (el.getAttribute("aria-labelledby") || "").split(/\s+/).filter(Boolean)
      .map(id => el.getRootNode().getElementById?.(id)?.textContent || "").join(" ").trim() ||
    (el.labels ? [...el.labels].map(x => x.textContent).join(" ") : "") ||
    el.getAttribute("placeholder") || el.textContent;
  const caption = () => data.selectors?.caption ? custom("caption") :
    unique(all('[contenteditable="true"][role="textbox"], [contenteditable="true"][data-lexical-editor], .public-DraftEditor-content').filter(visible)) ||
    unique(all('textarea, [contenteditable="true"]').filter(visible).filter(el => /caption|description|mo ta/.test(normalize(label(el)))));
  const activeElement = () => {
    let active = document.activeElement;
    while (active?.shadowRoot?.activeElement) active = active.shadowRoot.activeElement;
    return active;
  };
  const captionFocused = el => !!el && (el === activeElement() || el.contains(activeElement()));
  const captionSnapshot = () => {
    const el = caption();
    const active = activeElement();
    const state = { present: !!el, text: "", focused: captionFocused(el),
      active: active ? { tag: active.tagName, role: active.getAttribute('role'), id: active.id } : null,
      pageFocused: document.hasFocus(), visibility: document.visibilityState,
      dialogOpen: blockingDialogs().length > 0 };
    if (!el) return state;
    const identities = globalThis.__omniVoiceCaptionNodes ||= new WeakMap();
    if (!identities.has(el)) identities.set(el, crypto.randomUUID());
    const selection = el.getRootNode().getSelection?.() || getSelection();
    const nativeInput = el.matches('textarea, input');
    const selectionInside = nativeInput || (!!selection?.rangeCount &&
      el.contains(selection.anchorNode) && el.contains(selection.focusNode));
    return { ...state, text: el.value ?? el.innerText, html: el.isContentEditable ? el.innerHTML.slice(0, 30_000) : undefined,
      editorId: identities.get(el), editorKey: el.getAttribute('data-editor') || el.querySelector('[data-editor]')?.getAttribute('data-editor') || null,
      editable: el.isContentEditable || (el.matches('textarea, input') && !el.disabled && !el.readOnly),
      selection: { inside: selectionInside, text: nativeInput ? el.value.slice(el.selectionStart, el.selectionEnd) : selection?.toString(),
        collapsed: nativeInput ? el.selectionStart === el.selectionEnd : selection?.isCollapsed,
        anchorOffset: nativeInput ? el.selectionStart : selection?.anchorOffset,
        focusOffset: nativeInput ? el.selectionEnd : selection?.focusOffset } };
  };
  // "Bay gio" is a radio label, not a time input.
  const fields = () => all('input').filter(el => ['text', 'date', 'time'].includes(el.type) &&
    !el.matches('[role="radio"], [role="checkbox"], [role="switch"]') && visible(el));
  // TikTok has shown the schedule as readonly inputs (.scheduled-picker) and, since October 2026, as plain
  // boxes: <div class="… date-picker-input">2026-10-27</div> and <div class="… time-picker-input"><span>20:00</span></div>.
  // A field is either kind; its text is read with fieldText and a box always needs its popup.
  const fieldText = el => el.matches('input, textarea') ? el.value : (el.textContent || '').replace(/\s+/g, ' ').trim();
  const fieldReadOnly = el => !el.matches('input, textarea') || el.readOnly;
  const outermost = elements => elements.filter(el => !elements.some(other => other !== el && other.contains(el)));
  const inPopup = el => !!el.closest('.calendar-wrapper, [class*="timepicker"], [role="dialog"], [role="listbox"]');
  const pickerBox = kind => unique(outermost(all(`[class*="${kind}-picker-input"]`).filter(el => visible(el) && !inPopup(el))));
  const looksLikeDate = text => /^(\d{4}[-/]\d{2}[-/]\d{2}|\d{2}\/\d{2}\/\d{4}|\d{1,2} (thg|thang) \d{1,2},? \d{4}|[a-z]{3,9} \d{1,2}, \d{4}|\d{1,2} [a-z]{3,9} \d{4})$/.test(normalize(text));
  const looksLikeTime = text => /^\d{1,2}:\d{2}$/.test(String(text || '').trim());
  // Since late October 2026 the boxes are TikTok's Picker component: <div class="Picker__root schedule-picker">
  // <div role="combobox" aria-label="Select date" aria-haspopup="true" aria-expanded="false" data-open="false"
  // class="Picker__trigger …"><span class="Picker__value">24 tháng 10, 2026</span></div></div>. Only the
  // combobox carries the click handler; a click on its wrapper does nothing, so clicks go through clickTarget.
  const triggerSelector = '[role="combobox"], [aria-haspopup], button, [role="button"]';
  const clickTarget = el => el.matches(triggerSelector) || el.matches('input, textarea') ? el : (el.querySelector(triggerSelector) || el);
  const pickerTrigger = kind => unique(all('[role="combobox"], [aria-haspopup]').filter(el => visible(el) && !inPopup(el) && !el.matches('input, textarea') &&
    !el.isContentEditable && (kind === 'date' ? /\b(date|ngay|lich)\b/.test(normalize(el.getAttribute('aria-label'))) || looksLikeDate(el.textContent)
      : /\b(time|gio)\b/.test(normalize(el.getAttribute('aria-label'))) || looksLikeTime(el.textContent))));
  // aria-expanded / data-open of the box's trigger; null when the markup carries neither.
  const pickerExpanded = el => {
    const target = clickTarget(el), value = target.getAttribute('aria-expanded') ?? target.getAttribute('data-open');
    return value === null ? null : value === 'true';
  };
  // Boxes whose whole text is a date or a time, after the Lên lịch radio: the innermost element with
  // that text, widened to the outermost ancestor that shows nothing else (the clickable box).
  const textBoxes = test => {
    const control = scheduleControl();
    const leaves = all('div, span, button, [role="button"]').filter(el => test(el.textContent) && visible(el) && !inPopup(el) &&
      (!control || !!(control.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING)) &&
      ![...el.children].some(child => test(child.textContent)));
    return [...new Set(leaves.map(el => {
      let box = el;
      while (box.parentElement && box.parentElement !== document.body && normalize(box.parentElement.textContent) === normalize(el.textContent)) box = box.parentElement;
      return box;
    }))];
  };
  const dateField = () => data.selectors?.date ? custom("date") : unique(fields().filter(el =>
    el.type === "date" || /date|ngay/.test(normalize(label(el))) || /^\d{4}[-/]\d{2}[-/]\d{2}$/.test(el.value))) ||
    pickerTrigger('date') || pickerBox('date') || unique(textBoxes(looksLikeDate));
  const timeField = () => data.selectors?.time ? custom("time") : unique(fields().filter(el =>
    el.type === "time" || /time|gio/.test(normalize(label(el))) || /^\d{2}:\d{2}$/.test(el.value))) ||
    pickerTrigger('time') || pickerBox('time') || unique(textBoxes(looksLikeTime));
  const scheduleControls = () => {
    if (data.selectors?.schedule) return all(data.selectors.schedule).filter(visible);
    const wanted = text => /^(schedule|schedule video|len lich|hen gio)$/.test(normalize(text));
    const native = all('input[type="radio"], input[type="checkbox"], [role="radio"], [role="switch"], [role="checkbox"]').filter(el =>
      (visible(el) || [...(el.labels || [])].some(visible)) && wanted(label(el)));
    if (native.length) return native;
    const circles = all('.Radio__innerCircle').filter(visible);
    const labeled = circles.filter(circle => {
      for (let el = circle.parentElement, depth = 0; el && depth < 5; el = el.parentElement, depth++) {
        if (el.querySelectorAll('.Radio__innerCircle').length !== 1) break;
        if (wanted(label(el))) return true;
      }
      return false;
    });
    return labeled.length ? labeled : circles.length === 1 ? circles : [];
  };
  const scheduleControl = () => unique(scheduleControls());
  const checked = el => {
    if (typeof el.checked === "boolean") return el.checked;
    if (["true", "false"].includes(el.getAttribute("aria-checked"))) return el.getAttribute("aria-checked") === "true";
    const circle = el.matches('.Radio__innerCircle') ? el : el.querySelector('.Radio__innerCircle');
    if (circle?.classList.contains('Radio__innerCircle--checked-true')) return true;
    if (circle?.classList.contains('Radio__innerCircle--checked-false')) return false;
    return null;
  };
  const setValue = (el, value) => {
    if (!el || el.disabled) throw new Error("Khong tim thay o nhap duy nhat hoac o dang bi khoa.");
    if (fieldReadOnly(el)) throw new Error("Bo chon ngay/gio chi doc. Can bo chon lich DOM phu hop; xuat chan doan de kiem tra.");
    const prototype = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(prototype, "value").set.call(el, value);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    el.blur();
  };
  const dateMatches = (value, target) => {
    const [year, month, day] = target.split("-").map(Number);
    const expected = new Date(year, month - 1, day);
    const forms = [target, target.replaceAll("-", "/"), `${day}/${month}/${year}`, `${String(day).padStart(2, "0")}/${String(month).padStart(2, "0")}/${year}`];
    for (const locale of ["en-US", "en-GB", "vi-VN"]) {
      for (const dateStyle of ["full", "long", "medium"]) forms.push(new Intl.DateTimeFormat(locale, { dateStyle }).format(expected));
    }
    return forms.some(form => normalize(form) === normalize(value));
  };
  const usable = el => visible(el) && !el.disabled && !el.closest('[aria-disabled="true"], [data-disabled="true"]') &&
    ![...el.classList].some(name => /disabled|outside|other-month/.test(name) && !name.endsWith('-false'));
  const calendars = () => all('.calendar-wrapper').filter(visible);
  // --- Popups of unknown markup (TikTok's Picker component since late October 2026) ---
  // Elements showing one number only (a day, an hour, a minute): the text node's parent, so a cell's
  // own label wins over the wrappers around it. TikTok's known popups are read by their own classes.
  const numberLeaves = () => {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT), leaves = [];
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const el = node.parentElement;
      if (el && /^\s*\d{1,2}\s*$/.test(node.data) && el.textContent.trim() === node.data.trim() && visible(el) &&
          !el.closest('.calendar-wrapper, .tiktok-timepicker-time-picker-container, script, style, [contenteditable="true"]')) leaves.push(el);
    }
    return leaves;
  };
  const ancestorsOf = leaves => {
    const found = new Set();
    for (const leaf of leaves) for (let el = leaf.parentElement; el && el !== document.body; el = el.parentElement) found.add(el);
    return [...found];
  };
  // The schedule boxes and the radio: a popup never contains them, the page around them does.
  const formAnchors = () => [scheduleControl(), dateField(), timeField()].filter(Boolean);
  const innermost = elements => elements.filter(el => !elements.some(other => other !== el && el.contains(other)));
  const monthNames = {
    en: Array.from({ length: 12 }, (_, i) => normalize(new Intl.DateTimeFormat('en-US', { month: 'long' }).format(new Date(2026, i, 1)))),
    vi: ['mot', 'hai', 'ba', 'tu', 'nam', 'sau', 'bay', 'tam', 'chin', 'muoi', 'muoi mot', 'muoi hai'],
  };
  // The words of an element without its number cells: "Tháng 10, 2026", "Tháng Mười 2026", "October 2026", "10/2026".
  const headingText = root => {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT), parts = [];
    for (let node = walker.nextNode(); node; node = walker.nextNode()) if (!/^\s*\d{1,2}\s*$/.test(node.data)) parts.push(node.data);
    return parts.join(' ');
  };
  const headingMonthYear = text => {
    const value = normalize(text), year = value.match(/\b(20\d{2})\b/);
    const numeric = value.match(/\bthang\s+(\d{1,2})\b/) || value.match(/\b(\d{1,2})\s*[/-]\s*20\d{2}\b/) || value.match(/\b20\d{2}\s*[/-]\s*(\d{1,2})\b/);
    const named = value.match(/\bthang\s+(muoi hai|muoi mot|muoi|mot|hai|ba|tu|nam|sau|bay|tam|chin)\b/);
    const month = numeric ? Number(numeric[1]) : named ? monthNames.vi.indexOf(named[1]) + 1
      : monthNames.en.findIndex(name => new RegExp(`\\b${name.slice(0, 3)}[a-z]*\\b`).test(value)) + 1;
    return year && month >= 1 && month <= 12 ? { month, year: Number(year[1]) } : null;
  };
  // An open calendar of unknown markup: the smallest element holding a month-and-year heading and at
  // least 28 day numbers, outside the schedule form itself.
  const genericCalendars = () => {
    const leaves = numberLeaves(), anchors = formAnchors();
    const roots = ancestorsOf(leaves).filter(el => !anchors.some(anchor => el.contains(anchor)) &&
      leaves.filter(leaf => el.contains(leaf)).length >= 28 && headingMonthYear(headingText(el)));
    return innermost(roots);
  };
  const genericCells = root => numberLeaves().filter(el => root.contains(el));
  const genericCalendarState = root => {
    const heading = headingMonthYear(headingText(root));
    const state = { count: 1, month: heading.month, year: heading.year, index: heading.year * 12 + heading.month - 1, gridValid: false, generic: true };
    const numbers = genericCells(root).map(el => Number(el.textContent.trim()));
    const days = new Date(heading.year, heading.month, 0).getDate();
    // The days of adjacent months surround the month; the run 1..days is the month itself.
    const start = numbers.findIndex((value, i) => value === 1 && i + days <= numbers.length && numbers.slice(i, i + days).every((n, k) => n === k + 1));
    if (start >= 0) Object.assign(state, { offset: start, gridValid: true });
    return state;
  };
  const usableChain = (el, root) => {
    for (let node = el; node && node !== root.parentElement; node = node.parentElement) if (!usable(node)) return false;
    return true;
  };
  // Hour and minute columns of an unknown time popup: the smallest elements whose numbers are exactly
  // 0–23 (or 1–12) and 0–59 (or every 5 minutes).
  const numberColumns = () => {
    const leaves = numberLeaves(), anchors = formAnchors(), columns = [];
    const run = (values, from, to, step) => {
      const want = [];
      for (let v = from; v <= to; v += step) want.push(v);
      return values.length === want.length && want.every(v => values.includes(v));
    };
    for (const el of ancestorsOf(leaves)) {
      if (anchors.some(anchor => el.contains(anchor))) continue;
      const cells = leaves.filter(leaf => el.contains(leaf)), values = [...new Set(cells.map(leaf => Number(leaf.textContent.trim())))];
      if (values.length !== cells.length) continue;
      const kind = run(values, 0, 23, 1) || run(values, 1, 12, 1) ? 'hour' : run(values, 0, 59, 1) || run(values, 0, 55, 5) ? 'minute' : null;
      if (kind) columns.push({ root: el, kind, cells });
    }
    return columns.filter(column => !columns.some(other => other !== column && other.kind === column.kind && column.root.contains(other.root)));
  };
  const calendarState = () => {
    const roots = calendars(), root = unique(roots);
    const state = { count: roots.length, month: null, year: null, index: null, gridValid: false };
    if (!roots.length) {
      const generic = genericCalendars();
      return generic.length === 1 ? genericCalendarState(generic[0]) : { ...state, count: generic.length, generic: generic.length > 0 };
    }
    if (!root) return state;
    const monthText = normalize(root.querySelector('.month-title')?.textContent);
    const months = ['mot', 'hai', 'ba', 'tu', 'nam', 'sau', 'bay', 'tam', 'chin', 'muoi', 'muoi mot', 'muoi hai'];
    const numeric = monthText.match(/^thang\s+(\d{1,2})$/);
    let month = numeric ? Number(numeric[1]) : months.indexOf(monthText.replace(/^thang\s+/, '')) + 1;
    if (!month) month = Array.from({ length: 12 }, (_, i) => normalize(new Intl.DateTimeFormat('en-US', { month: 'long' }).format(new Date(2026, i, 1)))).indexOf(monthText) + 1;
    const yearText = root.querySelector('.year-title')?.textContent.trim() || '';
    if (month < 1 || month > 12 || !/^\d{4}$/.test(yearText)) return state;
    const year = Number(yearText);
    Object.assign(state, { month, year, index: year * 12 + month - 1 });
    const headers = [...root.querySelectorAll('.day-header-wrapper .day-header')].map(el => normalize(el.textContent));
    const weekdays = [['cn', 'sun', 'sunday'], ['t2', 'mon', 'monday'], ['t3', 'tue', 'tuesday'], ['t4', 'wed', 'wednesday'], ['t5', 'thu', 'thursday'], ['t6', 'fri', 'friday'], ['t7', 'sat', 'saturday']];
    const firstDay = weekdays.findIndex(names => names.includes(headers[0]));
    if (headers.length !== 7 || firstDay < 0 || !headers.every((text, i) => weekdays[(firstDay + i) % 7].includes(text))) return state;
    const offset = (new Date(year, month - 1, 1).getDay() - firstDay + 7) % 7;
    const cells = [...root.querySelectorAll('.days-wrapper .day-span-container > .day')];
    const days = new Date(year, month, 0).getDate();
    // Adjacent months have identical day labels and no date attributes. Validate the whole grid first.
    state.offset = offset;
    state.gridValid = [28, 35, 42].includes(cells.length) && cells.length >= offset + days && cells.every((el, i) =>
      /^\d{1,2}$/.test(el.textContent.trim()) && Number(el.textContent.trim()) === new Date(year, month - 1, 1 - offset + i).getDate());
    return state;
  };
  const timePickers = () => all('.tiktok-timepicker-time-picker-container:not(.tiktok-timepicker-invisible)').filter(visible);
  const datePickerReady = () => calendars().length > 0 || genericCalendars().length > 0 || all('[role="gridcell"], [data-date], [class*="calendar"], button[aria-label]').filter(visible)
    .some(el => el.matches('[role="gridcell"], [data-date], [class*="calendar"]') || dateMatches(el.getAttribute('aria-label'), data.date || '2000-01-01'));
  const timePickerReady = () => timePickers().length > 0 || all('[role="listbox"]').filter(visible).length > 0 || numberColumns().some(column => column.kind === 'hour');
  const openPicker = (el, strategy = 'click') => {
    if (!usable(el)) throw new Error('O ngay/gio dang bi khoa tren TikTok.');
    const wrapper = el.closest('.TUXFormField')?.parentElement;
    // The supplied TikTok popup opens from this wrapper, not from a writable input.
    const target = wrapper?.closest('.scheduled-picker') && wrapper.querySelectorAll('input').length === 1 ? wrapper : clickTarget(el);
    target.scrollIntoView({ block: 'center', inline: 'nearest' });
    if (strategy === 'events') {
      // A component that listens to pointer / mouse events instead of click.
      const rect = target.getBoundingClientRect();
      const init = { bubbles: true, cancelable: true, composed: true, clientX: rect.left + rect.width / 2, clientY: rect.top + rect.height / 2,
        button: 0, buttons: 1, pointerId: 1, pointerType: 'mouse', isPrimary: true };
      target.dispatchEvent(new PointerEvent('pointerdown', init)); target.dispatchEvent(new MouseEvent('mousedown', init));
      target.focus?.();
      target.dispatchEvent(new PointerEvent('pointerup', { ...init, buttons: 0 })); target.dispatchEvent(new MouseEvent('mouseup', { ...init, buttons: 0 }));
      target.dispatchEvent(new MouseEvent('click', { ...init, buttons: 0 }));
      return true;
    }
    target.click(); return true;
  };
  const uploadState = () => {
    const bars = all('.info-progress').filter(visible);
    const bar = unique(bars);
    return { count: bars.length, width: bar?.style.width || "", success: !!bar?.classList.contains('success'),
      ready: !!bar && bar.classList.contains('success') && /^100(?:\.0+)?%$/.test(bar.style.width.trim()) };
  };
  const scheduleMatches = (expectedDate, expectedTime) => {
    const date = dateField(), time = timeField(), control = scheduleControl();
    return scheduleControls().length <= 1 && (!control || checked(control) === true) && !!date && !!time &&
      dateMatches(fieldText(date), expectedDate) && fieldText(time) === expectedTime;
  };
  const immediateMode = () => {
    const control = scheduleControl();
    return control ? checked(control) === false : !dateField() && !timeField();
  };
  const draftMatches = video => {
    if (typeof video !== 'string' || !video) return false;
    const files = fileInputs().flatMap(input => [...(input.files || [])]);
    return globalThis.__omniVoiceDraftVideo === video && files.every(file => file.name === video.split(/[\\/]/).at(-1));
  };
  const captionMatches = text => {
    if (typeof text !== 'string') return false;
    const el = caption();
    const clean = value => String(value || '').normalize('NFC').replace(/\s+/g, ' ').trim();
    return !!el && clean(el.value ?? el.innerText) === clean(text);
  };
  // TikTok's date / time popups are not dialogs to wait for: the old calendar-wrapper / tiktok-timepicker,
  // and since late October 2026 the Picker popover <div role="dialog"><div class="Picker__panel">
  // <div class="TimePicker__panel"><div role="listbox" aria-label="Hours">…, which stays open after the
  // last choice. An open one never blocks the caption or the Lên lịch button.
  const isPickerPopup = el => !!el.querySelector('.calendar-wrapper, [class*="timepicker"], [class*="Picker__panel"], [class*="TimePicker"], [class*="DatePicker"], [class*="Calendar__"]') ||
    [...el.querySelectorAll('[role="listbox"], [role="grid"], [role="group"]')].some(part => /\b(hours?|minutes?|gio|phut|time|date|ngay|calendar|lich)\b/.test(normalize(part.getAttribute('aria-label')))) ||
    genericCalendars().some(root => el.contains(root)) || numberColumns().some(column => el.contains(column.root));
  const nonPickerDialogs = selector => all(selector).filter(el => visible(el) && !isPickerPopup(el));
  const blockingDialogs = () => nonPickerDialogs('[role="dialog"], [aria-modal="true"], dialog[open]');
  const pickerPopups = () => all('[role="dialog"], [class*="Picker__panel"], [class*="popover"], [class*="Popover"]').filter(el => visible(el) && isPickerPopup(el));
  const openPickerFields = () => [dateField(), timeField()].filter(el => el && pickerExpanded(el) === true);
  const publishDialogs = () => {
    const dialogs = nonPickerDialogs('[role="dialog"], [role="alertdialog"], dialog[open]');
    return dialogs.filter(el => !dialogs.some(other => other !== el && el.contains(other)));
  };
  const pendingChecksConfirmation = () => {
    const dialog = unique(publishDialogs());
    if (!dialog) return null;
    const text = normalize(dialog.innerText);
    // TikTok may omit the copyright paragraph; both variants share this video-check warning.
    if (!text.includes('tiep tuc dang?') ||
        !text.includes('chung toi van dang kiem tra video cua ban de phat hien xem co van de tiem an hay khong.') ||
        !text.includes('ban co muon tiep tuc dang truoc khi quy trinh kiem tra hoan tat khong?')) return null;
    const buttons = [...dialog.querySelectorAll('button, [role="button"]')].filter(visible);
    const button = unique(buttons.filter(el => normalize(label(el)) === 'dang ngay'));
    const cancel = unique(buttons.filter(el => normalize(label(el)) === 'huy'));
    if (!button || !cancel) return null;
    const kind = text.includes('kiem tra ban quyen chua hoan tat') ? 'copyright-incomplete' : 'video-checks-incomplete';
    return { dialog, button, kind, ready: usable(button) && button.getAttribute('aria-busy') !== 'true' && button.getAttribute('data-loading') !== 'true' };
  };
  const scheduleSnapshot = () => {
    const field = el => el ? { value: fieldText(el), label: label(el).slice(0, 160), readonly: fieldReadOnly(el), disabled: !!el.disabled,
      type: el.type || el.tagName.toLowerCase(), class: typeof el.className === "string" ? el.className.slice(0, 200) : "", expanded: pickerExpanded(el) } : null;
    const controls = scheduleControls();
    return { controls: controls.map(el => ({ label: label(el), checked: checked(el), disabled: !!el.disabled })),
      date: field(dateField()), time: field(timeField()), calendar: calendarState() };
  };
  // The block around the Lên lịch radio up to the timezone row (SVG bodies dropped), so a changed
  // TikTok layout can be read from a diagnostic instead of guessed.
  const scheduleHtml = () => {
    const timezone = all('div, span, p, label, button').filter(el => visible(el) && /\bgmt\b/.test(normalize(el.textContent)) && el.textContent.length < 120)
      .find(el => ![...el.children].some(child => /\bgmt\b/.test(normalize(child.textContent))));
    const anchors = [scheduleControl(), dateField(), timeField(), timezone].filter(Boolean);
    let box = anchors[0];
    if (!box) return null;
    // The smallest element holding every anchor; without other anchors, a few levels above the radio.
    if (anchors.length > 1) while (box !== document.documentElement && !anchors.every(el => box.contains(el))) box = box.parentElement;
    else for (let depth = 0; depth < 6 && box.parentElement && box.parentElement !== document.body; depth++) box = box.parentElement;
    return box.outerHTML.replace(/<svg[\s\S]*?<\/svg>/g, '<svg/>').slice(0, 40_000);
  };
  // Every open popup (calendar, time columns, dialogs, Picker / popover containers) outside the schedule
  // boxes, so an unrecognised picker can be read from a diagnostic instead of guessed.
  const popupHtml = () => {
    const anchors = formAnchors();
    const named = all('[role="dialog"], [role="listbox"], [role="grid"], [class*="Picker"], [class*="picker"], [class*="alendar"], [class*="timepicker"], [class*="opover"], [class*="opup"], [class*="ropdown"]')
      .filter(el => visible(el) && !anchors.some(anchor => el.contains(anchor) || anchor.contains(el)) && !el.closest('[contenteditable="true"]'));
    const roots = [...new Set([...named, ...genericCalendars(), ...numberColumns().map(column => column.root)])];
    let html = '';
    for (const el of roots.filter(el => !roots.some(other => other !== el && other.contains(el)))) {
      if (html.length >= 60_000) break;
      html += el.outerHTML.replace(/<svg[\s\S]*?<\/svg>/g, '<svg/>') + '\n';
    }
    return html ? html.slice(0, 60_000) : null;
  };
  const fileInputs = () => all(data.selectors?.file || 'input[type="file"]').filter(el => el.type === "file" && !el.disabled &&
    (data.selectors?.file || !el.accept || /video|mp4|mov|webm|m4v|avi/i.test(el.accept)));
  const uploadTrigger = () => unique(all('button, [role="button"], label').filter(usable).filter(el =>
    /^(select video|select file|choose file|chon video|chon tep|chon tap tin|tai video len)$/.test(normalize(label(el)))));
  const contentPage = () => /^\/tiktokstudio\/content\/?$/.test(location.pathname);
  const videoId = link => {
    try {
      const url = new URL(link.getAttribute('href'), location.href);
      const match = /^\/@[^/]+\/video\/(\d+)\/?$/.exec(url.pathname);
      return url.origin === location.origin && match ? match[1] : null;
    } catch { return null; }
  };
  // A post row: its caption link, the date/status labels and every icon (alarm = scheduled).
  const readPost = (row, link, id) => {
    const labels = [...row.querySelectorAll('[data-tt^="components_PublishStageLabel_"]')].filter(visible);
    return { id, url: location.origin + new URL(link.getAttribute('href'), location.href).pathname, caption: link.textContent.trim(),
      stage: [...new Set(labels.map(el => el.textContent.trim()).filter(Boolean))].join(' | '),
      icons: [...new Set([...row.querySelectorAll('[data-icon]')].map(icon => icon.getAttribute('data-icon')))] };
  };
  // Read-only list that starts from each video link instead of TikTok's table hooks, which
  // get renamed or duplicated (a heading carries the same data-tt as the table).
  const postLinks = () => {
    const byId = new Map();
    for (const link of all('a[href*="/video/"]')) {
      const id = videoId(link), caption = link.textContent.trim();
      if (!id || !caption || !visible(link)) continue;
      // The row is the widest ancestor that still holds this post only.
      let row = link;
      for (let parent = row.parentElement; parent && parent !== document.body; parent = parent.parentElement) {
        if ([...parent.querySelectorAll('a[href*="/video/"]')].some(other => (videoId(other) || id) !== id)) break;
        row = parent;
      }
      const post = readPost(row, link, id);
      if (!byId.has(id) || caption.length > byId.get(id).caption.length) byId.set(id, post);
    }
    return [...byId.values()];
  };
  const contentPosts = () => {
    if (!contentPage()) return { page: false, ready: false, posts: [] };
    const containers = all('[data-tt="components_PostTable_Container"]').filter(visible);
    const posts = [], ids = new Set();
    for (const container of containers) {
      for (const row of container.querySelectorAll('[data-tt="components_PostTable_Absolute"]')) {
        if (!visible(row)) continue;
        const link = unique([...row.querySelectorAll('[data-tt="components_PostInfoCell_Container"] a[data-tt="components_PostInfoCell_a"]')].filter(visible));
        const id = link && videoId(link);
        if (!id || ids.has(id)) continue;
        ids.add(id);
        posts.push(readPost(row, link, id));
      }
    }
    if (posts.length) return { page: true, ready: true, posts };
    // No row hook matched (renamed by TikTok, or the list is still loading): the links decide.
    const linked = postLinks();
    return { page: true, ready: containers.length > 0 || linked.length > 0, posts: linked };
  };
  // "Bài đăng 113" tab heading; only small elements are read to keep this cheap.
  const postTotal = () => {
    for (const el of document.querySelectorAll('body *')) {
      if (el.childElementCount > 3 || !visible(el)) continue;
      const match = /^\s*(?:bai dang|posts)\s*\(?\s*(\d[\d.,]*)\s*\)?\s*$/.exec(normalize(el.textContent));
      if (match) return Number(match[1].replace(/[.,]/g, ''));
    }
    return null;
  };
  if (action === 'contentPosts') return data.withTotal ? { ...contentPosts(), total: postTotal() } : contentPosts();
  // Read-only list for "Cập nhật kịch bản" (link-based, with the "Bài đăng N" total).
  if (action === 'postList') {
    if (!contentPage()) return { page: false, ready: false, posts: [] };
    const posts = postLinks();
    const table = all('[data-tt="components_PostTable_Container"]').some(visible);
    return { page: true, ready: posts.length > 0 || table, posts, total: postTotal() };
  }
  if (action === 'postProbe') {
    const count = selector => all(selector).length;
    const links = all('a[href*="/video/"]');
    return { url: location.href, title: document.title, readyState: document.readyState,
      counts: { table: count('[data-tt="components_PostTable_Container"]'), rows: count('[data-tt="components_PostTable_Absolute"]'),
        captionLinks: count('a[data-tt="components_PostInfoCell_a"]'), stageLabels: count('[data-tt^="components_PublishStageLabel_"]'), videoLinks: links.length },
      links: links.slice(0, 5).map(link => ({ href: link.getAttribute('href'), text: link.textContent.trim().slice(0, 80), visible: visible(link) })),
      labels: all('[data-tt^="components_PublishStageLabel_"]').slice(0, 6).map(el => el.textContent.trim().slice(0, 40)),
      text: (document.body?.innerText || '').slice(0, 400) };
  }
  if (action === 'contentScroll') {
    // Virtualized rows: move one screen at a time so no row is skipped.
    const table = all('[data-tt="components_PostTable_Container"]').find(visible) ||
      all('a[href*="/video/"]').find(link => visible(link) && link.textContent.trim())?.parentElement;
    if (!table) return { ok: false, atEnd: true };
    const scrollable = el => /(auto|scroll|overlay)/.test(getComputedStyle(el).overflowY) && el.scrollHeight > el.clientHeight + 4;
    let box = table;
    while (box && box !== document.body && !scrollable(box)) box = box.parentElement;
    const target = box && box !== document.body ? box : document.scrollingElement;
    const view = target === document.scrollingElement ? innerHeight : target.clientHeight;
    const before = target.scrollTop;
    target.scrollTop = before + Math.max(200, view * 0.8);
    return { ok: true, moved: target.scrollTop > before, atEnd: target.scrollTop + view >= target.scrollHeight - 4 };
  }
  if (action === "probe") return { fileCount: fileInputs().length, caption: !!caption(), uploadTrigger: !!uploadTrigger() };
  if (action === "openUpload") {
    if (caption() && (caption().innerText || caption().value || "").trim()) throw new Error("Tab đang có mô tả. Dùng Điền tiếp cho bản nháp hiện tại.");
    const button = uploadTrigger(); if (!button) return false;
    button.click(); return true;
  }
  if (action === "inspect") {
    return { url: location.origin + location.pathname, title: document.title, caption: captionSnapshot(), schedule: scheduleSnapshot(), scheduleHtml: scheduleHtml(), popupHtml: popupHtml(), upload: uploadState(), content: contentPosts(),
      dialogs: publishDialogs().map(el => ({ text: el.innerText.slice(0, 4000), buttons: [...el.querySelectorAll('button, [role="button"]')].map(button => ({
        label: label(button), disabled: !!button.disabled, ariaDisabled: button.getAttribute('aria-disabled'), loading: button.getAttribute('data-loading'),
      })) })),
      controls: all('input, textarea, [contenteditable="true"], [role="radio"], [role="switch"], [role="checkbox"], [role="button"], .Radio__innerCircle, .info-progress, [role="option"], [role="gridcell"], button, [class*="calendar"], [class*="timepicker"], [class*="picker"]')
        .filter(el => visible(el) || el.type === "file").slice(0, 200).map(el => ({
          tag: el.tagName, type: el.type, role: el.getAttribute("role"), id: el.id,
          class: typeof el.className === "string" ? el.className : "", label: label(el).slice(0, 160),
          value: el.type === "password" ? undefined : el.value, readonly: el.readOnly,
          checked: checked(el), disabled: el.disabled, placeholder: el.getAttribute("placeholder"),
          date: el.getAttribute("data-date"), ariaLabel: el.getAttribute("aria-label")
        })) };
  }
  if (action === "file") {
    const inputs = fileInputs();
    const input = unique(inputs.filter(el => /video|mp4|mov|webm/i.test(el.accept))) || unique(inputs);
    if (!input) throw new Error(inputs.length ? `Có ${inputs.length} ô tải video. Cần chọn đúng ô tải, hãy xuất chẩn đoán.` : "Chưa có ô tải video trong khung trang này.");
    if (input.files?.length) throw new Error("Tab dang co video. Hoan tat hoac huy ban nhap truoc khi nap video khac.");
    return input;
  }
  if (action === "captionReady") return !!caption();
  if (action === "captionSnapshot") return captionSnapshot();
  if (action === "captionFocusOnly") {
    const el = caption(); if (!el) throw new Error("Không thấy ô mô tả.");
    el.focus({ preventScroll: true }); return true;
  }
  if (action === "captionHasFocus") {
    return captionFocused(caption());
  }
  if (action === "draftMark") {
    globalThis.__omniVoiceDraftVideo = data.video;
    for (const input of fileInputs()) input.addEventListener("change", () => { delete globalThis.__omniVoiceDraftVideo; }, { once: true });
    return true;
  }
  if (action === "draftCheck") {
    return draftMatches(data.video);
  }
  if (action === "captionEnd") {
    const el = caption(); if (!el) throw new Error("Không thấy ô mô tả.");
    el.focus({ preventScroll: true });
    if (el.isContentEditable) {
      const range = document.createRange(); range.selectNodeContents(el); range.collapse(false);
      const selection = getSelection(); selection.removeAllRanges(); selection.addRange(range);
    } else el.setSelectionRange(el.value.length, el.value.length);
    return true;
  }
  if (action === "captionFocus") {
    const el = caption();
    if (!el) throw new Error("Khong tim thay o mo ta duy nhat.");
    el.focus({ preventScroll: true });
    if (el.isContentEditable) {
      const range = document.createRange(); range.selectNodeContents(el);
      const selection = getSelection(); selection.removeAllRanges(); selection.addRange(range);
    } else { el.select(); }
    return true;
  }
  if (action === "captionCheck") {
    return captionMatches(data.text);
  }
  if (action === "schedule") {
    if (scheduleControls().length > 1) throw new Error("Chua nhan dien duoc tuy chon Len lich duy nhat: co nhieu dieu khien cung nhan.");
    const el = scheduleControl();
    if (!el) {
      if (dateField() && timeField()) return "already";
      throw new Error("Chua nhan dien duoc tuy chon Len lich. Xuat chan doan hoac dat CSS selector.");
    }
    const state = checked(el);
    if (state === null) throw new Error("Khong doc duoc trang thai Len lich.");
    if (state) return "already";
    if (el.disabled || el.closest('[aria-disabled="true"], [data-disabled="true"]')) throw new Error("Tuy chon Len lich dang bi khoa tren TikTok.");
    el.click();
    return "enabled";
  }
  if (action === "scheduleReady") return !!dateField() && !!timeField();
  if (action === "scheduleSnapshot") return scheduleSnapshot();
  if (action === "disarmUnload") {
    // A queue leaves this draft on purpose: keep the page's "leave site?" handlers from running.
    window.onbeforeunload = null;
    window.addEventListener("beforeunload", event => event.stopImmediatePropagation(), true);
    return true;
  }
  if (action === "revealSchedule") {
    // Scroll the schedule block into the viewport before a diagnostic screenshot.
    const el = scheduleControl() || dateField() || timeField();
    if (!el) return false;
    el.scrollIntoView({ block: "center", inline: "nearest" }); return true;
  }
  if (action === "dateCheck") { const el = dateField(); return !!el && dateMatches(fieldText(el), data.date); }
  if (action === "calendarState") return calendarState();
  if (action === "datePickerReady") return datePickerReady();
  if (action === "timePickerReady") return timePickerReady();
  if (action === "timeCheck") { const el = timeField(); return !!el && fieldText(el) === data.time; }
  if (action === "timePartCheck") { const el = timeField(); return !!el && fieldText(el).split(':')[data.part === 'hour' ? 0 : 1] === data.value; }
  if (action === "immediateCheck") {
    return immediateMode();
  }
  if (action === "openDate") {
    const el = dateField();
    if (!el) throw new Error("Khong tim thay o ngay.");
    if (!fieldReadOnly(el)) return false;
    if (datePickerReady()) return true;
    return openPicker(el, data.strategy);
  }
  if (action === "pickerExpanded") { const el = data.field === "time" ? timeField() : dateField(); return el ? pickerExpanded(el) : null; }
  if (action === "pickersClosed") return !pickerPopups().length && !openPickerFields().length;
  if (action === "closePickers") {
    // Dismiss an open date / time popover the way a user would: a press outside it, then Escape. The page
    // closes it asynchronously; the caller polls pickersClosed.
    const open = pickerPopups();
    if (!open.length && !openPickerFields().length) return true;
    const init = { bubbles: true, cancelable: true, composed: true, clientX: 1, clientY: 1, button: 0, pointerId: 1, pointerType: 'mouse', isPrimary: true };
    for (const [type, Event] of [['pointerdown', PointerEvent], ['mousedown', MouseEvent], ['pointerup', PointerEvent], ['mouseup', MouseEvent], ['click', MouseEvent]]) {
      document.body.dispatchEvent(new Event(type, { ...init, buttons: type.endsWith('down') ? 1 : 0 }));
    }
    const escape = { bubbles: true, cancelable: true, composed: true, key: 'Escape', code: 'Escape', keyCode: 27 };
    for (const target of new Set([activeElement(), ...open, document.body])) {
      if (target) { target.dispatchEvent(new KeyboardEvent('keydown', escape)); target.dispatchEvent(new KeyboardEvent('keyup', escape)); }
    }
    return false;
  }
  if (action === "togglePicker") {
    const el = data.field === "time" ? timeField() : dateField();
    if (!el || pickerExpanded(el) !== true) return false;
    clickTarget(el).click(); return true;
  }
  if (action === "pickHashtagSuggestion") {
    // TikTok lists suggestions while a tag is typed; Enter takes the highlighted one, which can be another
    // tag (#audioviral for #audio). The row showing exactly the typed tag is clicked instead when it exists.
    const editor = caption(), wanted = normalize(data.tag);
    if (!editor || !wanted.startsWith('#')) return { found: false, clicked: false, options: [] };
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT), leaves = [];
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const el = node.parentElement, text = normalize(node.data);
      if (el && text.startsWith('#') && !editor.contains(el) && !el.closest('[contenteditable="true"], script, style') && visible(el)) leaves.push({ el, tag: text.split(' ')[0] });
    }
    const options = [...new Set(leaves.map(leaf => leaf.tag))].slice(0, 12);
    const exact = leaves.filter(leaf => leaf.tag === wanted);
    if (exact.length !== 1) return { found: exact.length > 0, clicked: false, options };
    const target = exact[0].el;
    target.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    const rect = target.getBoundingClientRect();
    const init = { bubbles: true, cancelable: true, composed: true, clientX: rect.left + rect.width / 2, clientY: rect.top + rect.height / 2, button: 0, pointerId: 1, pointerType: 'mouse', isPrimary: true };
    target.dispatchEvent(new PointerEvent('pointerdown', { ...init, buttons: 1 })); target.dispatchEvent(new MouseEvent('mousedown', { ...init, buttons: 1 }));
    target.dispatchEvent(new PointerEvent('pointerup', { ...init, buttons: 0 })); target.dispatchEvent(new MouseEvent('mouseup', { ...init, buttons: 0 }));
    target.dispatchEvent(new MouseEvent('click', { ...init, buttons: 0 }));
    return { found: true, clicked: true, options };
  }
  if (action === "fieldRect") {
    // Viewport centre of the box's clickable part, for a real mouse click through the debugger.
    const el = data.field === "time" ? timeField() : dateField();
    if (!el) return null;
    const target = clickTarget(el);
    target.scrollIntoView({ block: "center", inline: "nearest" });
    const rect = target.getBoundingClientRect();
    return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
  }
  if (action === "pickDate") {
    const state = calendarState();
    if (state.count) {
      if (state.count !== 1) throw new Error('Co nhieu popup lich dang mo. Chua chon ngay.');
      if (!state.gridValid) throw new Error('Chua doc duoc thang/nam va luoi ngay cua popup TikTok.');
      const [year, month, day] = data.value.split('-').map(Number);
      if (year !== state.year || month !== state.month) return 'missing';
      if (!Number.isInteger(day) || day < 1 || day > new Date(year, month, 0).getDate()) throw new Error('Ngay can chon khong hop le.');
      if (state.generic) {
        const root = genericCalendars()[0], cell = genericCells(root)[state.offset + day - 1];
        if (!cell || !usableChain(cell, root)) throw new Error('Ngay ' + data.value + ' bi TikTok khoa (o ngay bi vo hieu). Chua chon ngay.');
        cell.scrollIntoView({ block: 'nearest', inline: 'nearest' }); cell.click(); return 'picked';
      }
      const root = unique(calendars());
      const cell = root.querySelectorAll('.days-wrapper .day-span-container > .day')[state.offset + day - 1];
      if (!cell?.classList.contains('valid') || !usable(cell) || !usable(cell.parentElement)) throw new Error('Ngay ' + data.value + ' bi TikTok khoa (khong co day.valid). Chua chon ngay.');
      cell.click(); return 'picked';
    }
    const cells = all('[data-date], [role="gridcell"], [class*="calendar"] button, [class*="calendar-day"], button[aria-label]').filter(usable);
    let matches = cells.filter(el => [el.getAttribute("data-date"), el.getAttribute("aria-label"), el.getAttribute("title")].some(value => value && dateMatches(value, data.value)));
    // Prefer the clickable leaf when a gridcell wraps its own button.
    matches = matches.filter(el => !matches.some(other => other !== el && el.contains(other)));
    const exact = unique(matches);
    if (exact) { exact.click(); return "picked"; }
    const [year, month, day] = data.value.split("-").map(Number);
    const englishMonth = normalize(new Intl.DateTimeFormat("en-US", { month: "long" }).format(new Date(year, month - 1, day)));
    const roots = all('[role="dialog"], [class*="calendar"]').filter(visible).filter(el => {
      const content = normalize(el.textContent);
      return content.includes(String(year)) && (content.includes(englishMonth) || new RegExp(`thang\\s+0?${month}(?!\\d)`).test(content));
    });
    const root = unique(roots.filter(el => !roots.some(other => other !== el && el.contains(other))));
    if (root) {
      const days = [...root.querySelectorAll('[role="gridcell"], button, [class*="calendar-day"]')]
        .filter(usable).filter(el => el.textContent.trim() === String(day));
      const choice = unique(days.filter(el => !days.some(other => other !== el && el.contains(other))));
      if (choice) { choice.click(); return "picked"; }
    }
    return "missing";
  }
  if (action === "nextMonth" || action === "changeMonth") {
    const direction = action === 'nextMonth' ? 1 : data.direction;
    if (![1, -1].includes(direction)) throw new Error('Huong chuyen thang khong hop le.');
    const roots = calendars();
    if (roots.length) {
      if (roots.length !== 1 || !calendarState().gridValid) throw new Error('Popup lich chua san sang de chuyen thang.');
      const arrow = unique([...roots[0].querySelectorAll('.month-header-wrapper .arrow')].filter(usable).filter(el =>
        el.querySelector('svg')?.style.transform.replace(/\s+/g, '') === `rotate(${direction === 1 ? -90 : 90}deg)`));
      if (!arrow) return false;
      arrow.click(); return true;
    }
    const generic = genericCalendars();
    if (generic.length) {
      if (generic.length !== 1 || !calendarState().gridValid) throw new Error('Popup lich chua san sang de chuyen thang.');
      // The arrows: labelled, named by their icon / class, rotated like TikTok's old ones, or simply the
      // only two buttons that hold no day.
      const root = generic[0], cells = genericCells(root);
      const hint = el => normalize([el.getAttribute('aria-label'), el.getAttribute('title'), typeof el.className === 'string' ? el.className : '',
        ...[...el.querySelectorAll('[data-icon], [class]')].map(x => (x.getAttribute('data-icon') || '') + ' ' + (typeof x.className === 'string' ? x.className : ''))].join(' '));
      const sign = el => {
        const text = hint(el), turn = (el.querySelector('svg')?.style.transform || '').replace(/\s+/g, '');
        if (/left|prev|truoc|back/.test(text) || turn === 'rotate(90deg)') return -1;
        if (/right|next|sau|tiep|forward/.test(text) || turn === 'rotate(-90deg)') return 1;
        return 0;
      };
      const buttons = [...root.querySelectorAll('button, [role="button"], [class*="arrow"], [class*="Arrow"], [class*="prev"], [class*="next"], [class*="Prev"], [class*="Next"]')]
        .filter(el => usable(el) && !cells.some(cell => el.contains(cell)));
      const outer = buttons.filter(el => !buttons.some(other => other !== el && other.contains(el)));
      const arrow = unique(outer.filter(el => sign(el) === direction)) || (outer.length === 2 && outer.every(el => !sign(el)) ? outer[direction === 1 ? 1 : 0] : null);
      if (!arrow) return false;
      arrow.click(); return true;
    }
    const next = unique(all('button, [role="button"]').filter(usable).filter(el =>
      (direction === 1 ? /^(next month|thang tiep theo|thang sau)$/ : /^(previous month|prev month|thang truoc)$/).test(normalize(el.getAttribute("aria-label") || el.getAttribute("title")))));
    if (!next) return false;
    next.click(); return true;
  }
  if (action === "openTime") {
    const el = timeField();
    if (!el) throw new Error("Khong tim thay o gio.");
    if (!fieldReadOnly(el)) return false;
    if (timePickerReady()) return true;
    return openPicker(el, data.strategy);
  }
  if (action === "pickTime") {
    const pickers = timePickers();
    if (pickers.length > 1) throw new Error('Co nhieu popup gio dang mo. Chua chon gio.');
    const picker = unique(pickers);
    if (picker) {
      const side = data.part === "hour" ? '.tiktok-timepicker-left' : '.tiktok-timepicker-right';
      const option = unique([...picker.querySelectorAll(side)].filter(usable).filter(el =>
        /^\d{1,2}$/.test(el.textContent.trim()) && Number(el.textContent.trim()) === Number(data.value)));
      const item = option?.closest('.tiktok-timepicker-option-item');
      if (!item || !usable(item)) return false;
      item.scrollIntoView({ block: "nearest", inline: "nearest" });
      option.click(); return true;
    }
    const lists = all('[role="listbox"]').filter(visible);
    const labeled = lists.filter(el => (data.part === "hour" ? /hour|gio/ : /minute|phut/).test(normalize(label(el))));
    const list = unique(labeled) || (lists.length === 2 ? lists[data.part === "hour" ? 0 : 1] : null);
    if (!list) {
      const column = unique(numberColumns().filter(item => item.kind === data.part));
      const option = column ? unique(column.cells.filter(el => Number(el.textContent.trim()) === Number(data.value) && usableChain(el, column.root))) : null;
      if (!option) return false;
      option.scrollIntoView({ block: "nearest", inline: "nearest" }); option.click(); return true;
    }
    const option = unique([...list.querySelectorAll('[role="option"]')].filter(usable).filter(el => /^\d{1,2}$/.test(el.textContent.trim()) && Number(el.textContent.trim()) === Number(data.value)));
    if (!option) return false;
    option.click(); return true;
  }
  if (action === "setDate") {
    const el = dateField();
    const current = el ? fieldText(el) : "";
    let value = data.value;
    if (el?.type !== "date" && /^\d{2}\/\d{2}\/\d{4}$/.test(current)) {
      throw new Error("Dinh dang ngay mo ho (dd/mm hay mm/dd). Can bo chon lich DOM phu hop.");
    }
    if (current.includes("/")) value = value.replaceAll("-", "/");
    setValue(el, value); return true;
  }
  if (action === "setTime") { setValue(timeField(), data.value); return true; }
  if (action === "scheduleCheck") {
    return scheduleMatches(data.date, data.time);
  }
  const publishButton = () => {
    const wanted = data.schedule ? /^(schedule|len lich|hen gio)$/ : /^(post|publish|dang|dang ngay)$/;
    const exact = all('[data-e2e="post_video_button"]').filter(visible);
    const elements = data.selectors?.publish ? all(data.selectors.publish) : exact.length ? exact : all('button, [role="button"]');
    return unique(elements.filter(visible).filter(el => wanted.test(normalize(label(el))) && !el.closest('[role="dialog"]') &&
      !el.matches('[role="radio"], [role="checkbox"], [role="switch"]')));
  };
  const publishReady = button => !!button && usable(button) && button.getAttribute("aria-busy") !== "true" &&
    button.getAttribute("data-loading") !== "true" && uploadState().ready;
  if (action === "uploadState") return uploadState();
  if (action === "publishReady") {
    return publishReady(publishButton());
  }
  if (action === "publish") {
    if (data.authorized !== true) throw new Error("Chưa bật quyền bấm Đăng / Lên lịch.");
    const button = publishButton();
    if (!publishReady(button)) throw new Error("Video chưa tải thành công 100% hoặc nút Đăng / Lên lịch chưa sẵn sàng, không duy nhất.");
    button.click(); return true;
  }
  if (action === "confirmPublish") {
    if (data.authorized !== true) throw new Error('Chua bat quyen xac nhan Dang ngay.');
    const confirmation = pendingChecksConfirmation();
    if (!confirmation?.ready) throw new Error('Khong co hop thoai kiem tra video chua hoan tat voi nut Dang ngay duy nhat, san sang.');
    if (!uploadState().ready || !draftMatches(data.video) || !captionMatches(data.caption)) throw new Error('Video, mo ta hoac tien trinh tai da thay doi. Chua xac nhan Dang ngay.');
    if (!(data.schedule ? scheduleMatches(data.date, data.time) : immediateMode())) throw new Error('Ngay/gio hoac che do dang da thay doi. Chua xac nhan Dang ngay.');
    confirmation.button.click(); return true;
  }
  if (action === "publishOutcome") {
    const messages = all('[role="alert"], [role="status"], [class*="toast"], [data-e2e="publish-success"], [data-e2e="schedule-success"]')
      .filter(visible).map(el => normalize(el.textContent));
    if (messages.some(text => /\b(failed|error|khong thanh cong|that bai|khong the dang)\b/.test(text))) return { state: "error", message: messages.join("; ") };
    if (messages.some(text => /\b(video scheduled|successfully (posted|scheduled|published)|post published|video has been (scheduled|posted|published)|da (dang|len lich).*thanh cong|video da duoc (dang|len lich))\b/.test(text))) return { state: "success", message: messages.join("; ") };
    const confirmation = pendingChecksConfirmation();
    if (confirmation) return { state: 'confirmation', kind: confirmation.kind, ready: confirmation.ready, message: confirmation.dialog.innerText.slice(0, 1000) };
    const dialogs = publishDialogs().map(el => el.innerText.slice(0, 1000));
    return { state: dialogs.length ? "dialog" : "waiting", message: dialogs.join("; ") };
  }
  throw new Error("Lenh DOM khong hop le.");
}
