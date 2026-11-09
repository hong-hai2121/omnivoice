# -*- coding: utf-8 -*-
"""Đăng video lên YouTube Studio bằng thao tác trên trang (Playwright + Chrome thật) — KHÔNG qua
Data API, nên không dính hạn mức ~11 video/ngày của API.

Luồng: mở trang upload → nạp file (CDP) → tiêu đề / mô tả → thumbnail → danh sách phát → đối tượng
trẻ em → thẻ (trong 'Hiện thêm') → nội dung bị thay đổi (AI) → Tiếp ×3 → Lên lịch (hoặc chế độ
hiển thị) → chờ tải xong → Lưu → đọc link. Selector dùng id ổn định của Studio, chữ hiển thị bắt cả
tiếng Việt lẫn Anh. Mỗi bước có xác minh bằng chữ Studio hiển thị; lệch là dừng (raise) để KHÔNG
bấm Lưu bừa.

Cách làm mượn từ tool "Đăng video tự động" (đã chạy thật trên kênh khác 10/2026); phần thumbnail
và câu "Nội dung bị thay đổi = Có" là thêm cho OmniVoice (kênh dùng giọng TTS, giống cờ
contains_ai của đường API).
"""
from __future__ import annotations

import os
import re
import time
from datetime import date, datetime, timedelta

from dang_chung import JS_FIND_IMAGE_INPUT, clear_field, norm_space, set_file_via_cdp

UPLOAD_URL = "https://www.youtube.com/upload"
STUDIO_URL = "https://studio.youtube.com/"
MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTHS_EN_FULL = ["January", "February", "March", "April", "May", "June", "July", "August",
                  "September", "October", "November", "December"]
TAGS_LIMIT = 500            # Studio: tổng ký tự mọi thẻ (#tags-count '413/500')
TAGS_NHAP_TOI_DA = 490      # lọc trong code TRƯỚC khi gõ, dưới ngưỡng Studio một chút
THUMB_MAX_BYTES = 2 * 1024 * 1024
ANH_LOI_DIR = os.path.dirname(os.path.abspath(__file__))

# Ô <input type=file> của Studio nằm trong shadow DOM của ytcp-uploads-file-picker.
_FIND_VIDEO_INPUT_JS = """(() => {
  const deep = (root, sel) => {
    const hit = root.querySelector(sel);
    if (hit) return hit;
    for (const el of root.querySelectorAll('*')) {
      if (el.shadowRoot) { const r = deep(el.shadowRoot, sel); if (r) return r; }
    }
    return null;
  };
  const picker = deep(document, 'ytcp-uploads-file-picker');
  return (picker && deep(picker, 'input[type=file]')) || deep(document, 'input[type=file]');
})()"""


def _dismiss_popups(page):
    for sel in ('ytcp-auth-confirmation-dialog ytcp-button', 'tp-yt-paper-dialog #dismiss-button',
                'ytcp-button#dismiss-button'):
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=300):
                loc.click(timeout=1000)
        except Exception:
            pass


def _check_logged_in(page):
    if "accounts.google.com" in page.url:
        raise RuntimeError("Profile Chrome này chưa đăng nhập YouTube. Đăng nhập Google ngay trong tab Chrome "
                           "đang mở (1 lần, Chrome ghi nhớ) rồi chạy lại.")


def _fill_textbox(page, container_ids, text, log):
    """container_ids: các ID có thể của ô (Studio đổi ID theo thời gian: title-textbox → title-textarea)."""
    sel = ", ".join(f'ytcp-uploads-dialog #{cid} #textbox' for cid in container_ids)
    box = page.locator(sel).first
    box.wait_for(state="visible", timeout=60000)
    clear_field(page, box, log, "ô " + container_ids[0])
    # Mô tả kết thúc bằng hashtag → con trỏ dính '#tag' làm Studio bật popup gợi ý che ô dưới; thêm xuống dòng.
    if text.rstrip().rsplit("\n", 1)[-1].lstrip().startswith("#") and not text.endswith("\n"):
        text = text.rstrip() + "\n"
    box.fill(text)
    page.wait_for_timeout(300)
    got = " ".join(box.inner_text().split())
    if not got.startswith(" ".join(text.split())[:40]):
        clear_field(page, box, log, "ô " + container_ids[0])
        page.keyboard.insert_text(text)
    _dong_goi_y_hashtag(page, log)


def _dong_goi_y_hashtag(page, log):
    def mo():
        try:
            lb = page.locator('ytcp-uploads-dialog [role="listbox"], ytcp-uploads-dialog tp-yt-paper-listbox, '
                              'ytcp-uploads-dialog ytcp-social-suggestions-textbox tp-yt-iron-dropdown').filter(visible=True)
            return lb.count() > 0 and "#" in " ".join(lb.first.inner_text(timeout=1500).split())[:200]
        except Exception:
            return False
    if not mo():
        return
    page.keyboard.press("Space")
    page.wait_for_timeout(400)
    if mo():
        try:
            page.locator('ytcp-uploads-dialog #title-textarea, ytcp-uploads-dialog #title-textbox').first.click(position={"x": 5, "y": 5})
            page.wait_for_timeout(300)
        except Exception:
            pass
    log("  (đã đóng popup gợi ý hashtag" + ("" if not mo() else " — VẪN CÒN, có thể che ô bên dưới") + ")")


def _norm(s):
    return re.sub(r"[\W_]+", " ", (s or "").lower(), flags=re.UNICODE).strip()


def _set_thumbnail(page, thumb_path, log):
    """Nạp ảnh bìa vào ô 'Hình thu nhỏ' của hộp tải lên (input[type=file] accept image, xuyên shadow DOM).
    Không bắt buộc: lỗi chỉ ghi cảnh báo, video vẫn đăng (giống đường API: thumbnail là bước phụ)."""
    if not thumb_path or not os.path.isfile(thumb_path):
        return False
    size = os.path.getsize(thumb_path)
    if size > THUMB_MAX_BYTES:
        log(f"  ⚠ Thumbnail {size / 1048576:.2f} MB > 2 MB — Studio không nhận, bỏ qua ảnh bìa (đặt tay sau).")
        return False
    try:
        set_file_via_cdp(page, thumb_path, log, find_js=JS_FIND_IMAGE_INPUT, ten="thumbnail")
        page.wait_for_timeout(2500)
        log(f"✓ Thumbnail: {os.path.basename(thumb_path)}")
        return True
    except Exception as e:
        log(f"  ⚠ Không đặt được thumbnail ({str(e)[:120]}) — video vẫn đăng, đặt ảnh bìa tay sau.")
        return False


def _pick_playlist(page, name, log):
    log(f"Chọn danh sách phát: {name}")
    trig = page.locator('ytcp-video-metadata-playlists ytcp-dropdown-trigger, '
                        'ytcp-video-metadata-playlists ytcp-text-dropdown-trigger').first
    trig.scroll_into_view_if_needed()
    trig.click()
    dialog = page.locator('ytcp-playlist-dialog tp-yt-paper-dialog#dialog').first
    dialog.wait_for(state="visible", timeout=15000)
    rows = dialog.locator('#playlists-list ytcp-ve')
    try:
        rows.first.wait_for(state="attached", timeout=15000)
    except Exception:
        snippet = re.sub(r"\s+", " ", dialog.inner_text(timeout=2000))[:300]
        raise RuntimeError(f"Hộp thoại playlist không hiện danh sách. Nội dung thấy được: {snippet!r}")
    page.wait_for_timeout(300)
    names = [t.strip() for t in rows.all_inner_texts()]
    want = _norm(name)
    idx = next((i for i, n in enumerate(names) if _norm(n) == want), None)
    if idx is None:
        cands = [i for i, n in enumerate(names) if want and (want in _norm(n) or _norm(n) in want)]
        if cands:
            idx = cands[0]
    if idx is None:
        raise RuntimeError(f"Không tìm thấy danh sách phát '{name}'. Kênh đang có: "
                           + "; ".join(names[:12]) + (" ..." if len(names) > 12 else ""))
    box = dialog.locator(f'#checkbox-{idx}').first
    if box.count():
        box.scroll_into_view_if_needed()
        box.click()
    else:
        rows.nth(idx).click()
    page.wait_for_timeout(400)
    done = dialog.locator('ytcp-button.done-button').or_(
        dialog.locator('ytcp-button', has_text=re.compile(r"^\s*(Xong|Done)\s*$", re.I)))
    done.first.click()
    page.wait_for_timeout(800)
    log(f"✓ Đã chọn danh sách phát: {names[idx]}")


def _tags_count(container):
    try:
        txt = container.locator('#tags-count').first.inner_text(timeout=2000)
        m = re.search(r"(\d+)\s*/\s*(\d+)", txt)
        if m:
            return int(m.group(1)), int(m.group(2))
    except Exception:
        pass
    return None, TAGS_LIMIT


def studio_tag_count(tags):
    """Cách Studio đếm: mỗi thẻ = số ký tự + 2 nếu có dấu cách (bọc ngoặc kép), + 1 dấu phẩy giữa các thẻ."""
    tags = [t for t in tags if t]
    if not tags:
        return 0
    return sum(len(t) + (2 if " " in t else 0) for t in tags) + (len(tags) - 1)


def loc_the_truoc_khi_nhap(tags, log=print, toi_da=TAGS_NHAP_TOI_DA):
    """Bỏ thẻ CUỐI danh sách cho tới khi tổng (cách đếm Studio) <= toi_da. Giữ thứ tự."""
    giu = [t.strip() for t in tags if t and t.strip()]
    bo = []
    while giu and studio_tag_count(giu) > toi_da:
        bo.append(giu.pop())
    if bo:
        log(f"  Bỏ {len(bo)} thẻ cuối để tổng <= {toi_da} ký tự (Studio đếm): {', '.join(reversed(bo))}")
    return giu


def _remove_last_tag(page, container, tag_input):
    before, _ = _tags_count(container)
    for cach in ("nut-x", "backspace", "backspace"):
        try:
            if cach == "nut-x":
                chip = container.locator('ytcp-chip, ytcp-free-text-chip, .chip').last
                if chip.count() == 0:
                    continue
                btn = chip.locator('ytcp-icon-button, button').first
                if btn.count() == 0:
                    continue
                btn.click(timeout=2000)
            else:
                tag_input.click()
                page.keyboard.press("Backspace")
        except Exception:
            continue
        page.wait_for_timeout(300)
        after, _ = _tags_count(container)
        if before is None or (after is not None and after < before):
            return True
    return False


def _fill_tags(page, tags, log):
    tags = loc_the_truoc_khi_nhap(tags, log)
    log(f"Điền {len(tags)} thẻ ({studio_tag_count(tags)} ký tự theo Studio)")
    container = page.locator('ytcp-form-input-container#tags-container').first
    if not container.is_visible():
        toggle = page.locator('ytcp-video-metadata-editor #toggle-button').first
        toggle.scroll_into_view_if_needed()
        toggle.click()
        container.wait_for(state="visible", timeout=15000)
        page.wait_for_timeout(500)
    container.scroll_into_view_if_needed()
    clear = container.locator('#clear-button').first
    if clear.count() and clear.is_visible():
        clear.click()
        page.wait_for_timeout(400)
    tag_input = container.locator('input#text-input, input').first
    tag_input.wait_for(state="visible", timeout=10000)
    clear_field(page, tag_input, log, "ô nhập thẻ")
    added, dropped = [], []
    for t in tags:
        if dropped:
            dropped.append(t)
            continue
        page.keyboard.type(t)
        page.keyboard.press(",")
        page.wait_for_timeout(300)
        used, limit = _tags_count(container)
        if used is not None and used > limit:
            log(f"  Thẻ '{t}' làm vượt giới hạn ({used}/{limit}) → gỡ ra.")
            if not _remove_last_tag(page, container, tag_input):
                log("  ⚠ Không gỡ được thẻ cuối — hãy kiểm tra ô thẻ trong Chrome.")
            dropped.append(t)
            continue
        added.append(t)
    used, limit = _tags_count(container)
    if used is not None and used > limit:
        log(f"  ⚠ Thẻ vẫn vượt giới hạn: {used}/{limit} — Studio sẽ không cho Tiếp.")
    if dropped:
        log(f"  Bỏ qua vì hết chỗ: {', '.join(dropped)}")
    log(f"✓ Đã điền {len(added)} thẻ" + (f" ({used}/{limit})." if used is not None else "."))


def _answer_altered_content(page, contains_ai, log):
    """Mục 'Nội dung bị thay đổi' (công bố nội dung AI): contains_ai → 'Có', không thì 'Không'.
    Kênh không có mục này thì bỏ qua."""
    try:
        section = page.locator('ytcp-video-metadata-altered-content')
        if section.count() == 0:
            return
        mau = r"^\s*(Có|Yes)\s*$" if contains_ai else r"^\s*(Không|No)\s*$"
        radio = section.locator('tp-yt-paper-radio-button').filter(has_text=re.compile(mau, re.I)).first
        if radio.is_visible():
            radio.scroll_into_view_if_needed()
            radio.click()
            log("✓ Nội dung bị thay đổi (AI): chọn " + ("'Có'" if contains_ai else "'Không'"))
    except Exception:
        pass


def _set_kids(page, made_for_kids, log):
    name = "VIDEO_MADE_FOR_KIDS_MFK" if made_for_kids else "VIDEO_MADE_FOR_KIDS_NOT_MFK"
    radio = page.locator(f'tp-yt-paper-radio-button[name="{name}"]').first
    radio.scroll_into_view_if_needed()
    radio.click()
    log("✓ Đối tượng: " + ("Dành cho trẻ em" if made_for_kids else "Không dành cho trẻ em"))


def _wait_upload_done(page, log, timeout_sec=3600):
    log("Đang chờ video tải lên xong...")
    label = page.locator('ytcp-video-upload-progress .progress-label').first
    deadline = time.time() + timeout_sec
    last_txt = ""
    while time.time() < deadline:
        try:
            txt = label.inner_text(timeout=5000).strip()
        except Exception:
            txt = ""
        if txt and txt != last_txt:
            log(f"  [{txt}]")
            last_txt = txt
        if txt and not re.search(r"Đang tải|Uploading", txt, re.I):
            log("✓ Video đã tải lên máy chủ xong.")
            return
        time.sleep(3)
    raise RuntimeError("Hết giờ chờ video tải lên.")


def get_channel_info(page, log=print):
    """Vào Studio: đã đăng nhập chưa + tên kênh + id kênh (nút 'Kiểm tra kết nối')."""
    page.goto(STUDIO_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(4000)
    url = page.url
    if "accounts.google.com" in url:
        return {"logged_in": False, "name": "", "channel_id": "", "url": url}
    name = ""
    try:
        name = page.locator("#account-name, ytcp-navigation-drawer #entity-name").first.inner_text(timeout=10000).strip()
    except Exception:
        pass
    m = re.search(r"/channel/(UC[\w-]+)", url)
    cid = m.group(1) if m else ""
    return {"logged_in": True, "name": name, "channel_id": cid,
            "url": f"https://studio.youtube.com/channel/{cid}" if cid else url}


def _round_15(dt):
    q = (dt.minute + 7) // 15 * 15
    return dt.replace(minute=0, second=0, microsecond=0) + timedelta(minutes=q)


def _format_date_like(sample, when):
    """Gõ ngày theo đúng định dạng Studio đang hiển thị (locale máy): lấy chuỗi mẫu (thường là hôm nay,
    vd. '13 thg 10, 2026' hoặc 'Oct 13, 2026'), thay số/tháng bằng ngày cần đặt."""
    s = (sample or "").strip()
    if not s or not re.search(r"\d", s):
        return when.strftime("%d/%m/%Y")
    today = date.today()
    month_word = False
    for names in (MONTHS_EN_FULL, MONTHS_EN):
        for name in names:
            if re.search(rf"\b{name}\b", s):
                s = re.sub(rf"\b{name}\b", names[when.month - 1], s)
                month_word = True
                break
        if month_word:
            break
    nums = [(m.start(), m.end(), m.group()) for m in re.finditer(r"\d+", s)]
    roles, rest = {}, []
    for i, (_a, _b, txt) in enumerate(nums):
        if len(txt) == 4:
            roles[i] = when.year
        else:
            rest.append(i)
    if month_word:
        if rest:
            roles[rest[0]] = when.day
    elif len(rest) >= 2:
        a, b = int(nums[rest[0]][2]), int(nums[rest[1]][2])
        if a == today.month and b == today.day and a != b:
            roles[rest[0]], roles[rest[1]] = when.month, when.day
        else:
            roles[rest[0]], roles[rest[1]] = when.day, when.month
    elif len(rest) == 1:
        roles[rest[0]] = when.day
    out, last = [], 0
    for i, (a, b, txt) in enumerate(nums):
        out.append(s[last:a])
        val = roles.get(i)
        out.append(txt if val is None else (f"{val:02d}" if (len(txt) == 2 and txt[0] == "0") else str(val)))
        last = b
    out.append(s[last:])
    return "".join(out)


def _set_schedule(page, when, log):
    """Bước Chế độ hiển thị → 'Lên lịch': đặt ngày + giờ, đọc lại chữ Studio để xác minh."""
    when = _round_15(when)
    log(f"Lên lịch công bố: {when:%d/%m/%Y %H:%M}")
    radio = page.locator('tp-yt-paper-radio-button[name="SCHEDULE"]').first
    try:
        radio.wait_for(state="visible", timeout=3000)
        radio.scroll_into_view_if_needed()
        radio.click()
    except Exception:
        # giao diện mới (10/2026): khung riêng 'Lên lịch' dưới khung 'Lưu hoặc xuất bản'
        khung = page.locator('ytcp-video-visibility-select p#visibility-title, p#visibility-title').filter(
            has_text=re.compile(r"Lên lịch|Schedule", re.I)).first
        khung.wait_for(state="attached", timeout=15000)
        khung.scroll_into_view_if_needed()
        khung.click()
    page.wait_for_timeout(1000)
    picker = page.locator('ytcp-datetime-picker').first
    picker.wait_for(state="attached", timeout=15000)

    date_trig = picker.locator('#datepicker-trigger').first
    date_trig.scroll_into_view_if_needed()
    shown0 = re.sub(r"\s+", " ", date_trig.inner_text(timeout=3000)).strip()
    digits0 = re.findall(r"\d+", shown0)
    if (str(when.day) in digits0 and str(when.year) in shown0
            and (str(when.month) in digits0 or f"{when.month:02d}" in digits0)):
        log(f"  Ngày đang hiện '{shown0}' đã đúng.")
    else:
        date_trig.click()
        page.wait_for_timeout(600)
        date_input = page.locator('ytcp-date-picker input, ytcp-date-picker tp-yt-paper-input input').first
        date_input.wait_for(state="visible", timeout=10000)
        sample = ""
        try:
            sample = date_input.input_value(timeout=2000)
        except Exception:
            pass
        text = _format_date_like(sample or shown0, when)
        log(f"  Ngày: mẫu '{(sample or shown0).strip()}' → gõ '{text}'")
        date_input.click()
        page.keyboard.press("Control+a")
        page.keyboard.type(text)
        page.keyboard.press("Enter")
        page.wait_for_timeout(800)

    hhmm = f"{when:%H:%M}"
    hhmm_12 = when.strftime("%I:%M %p").lstrip("0")
    time_trig = picker.locator('#time-of-day-trigger').first
    time_box = picker.locator('#time-of-day-container input').first
    if time_trig.count():
        time_trig.scroll_into_view_if_needed()
        time_trig.click()
        page.wait_for_timeout(600)
        item = page.locator('tp-yt-paper-item').filter(
            has_text=re.compile(rf"^\s*({re.escape(hhmm)}|{re.escape(hhmm_12)})\s*$", re.I)).first
        try:
            item.wait_for(state="visible", timeout=5000)
            item.scroll_into_view_if_needed()
            item.click()
        except Exception:
            tin = page.locator('ytcp-datetime-picker input[type="text"], ytcp-time-of-day-picker input').first
            tin.wait_for(state="visible", timeout=5000)
            tin.click()
            page.keyboard.press("Control+a")
            page.keyboard.type(hhmm)
            page.keyboard.press("Enter")
        page.wait_for_timeout(800)
        shown_time = re.sub(r"\s+", " ", time_trig.inner_text(timeout=3000)).strip()
    else:
        time_box.wait_for(state="visible", timeout=10000)
        time_box.click()
        page.wait_for_timeout(300)
        page.keyboard.press("Control+a")
        page.keyboard.type(hhmm, delay=60)
        page.keyboard.press("Enter")
        page.wait_for_timeout(1000)
        shown_time = (time_box.input_value(timeout=3000) or "").strip()

    shown_date = re.sub(r"\s+", " ", date_trig.inner_text(timeout=3000)).strip()
    log(f"  Studio hiển thị: ngày '{shown_date}', giờ '{shown_time}'")
    digits = re.findall(r"\d+", shown_date)
    ok_date = (str(when.day) in digits or f"{when.day:02d}" in digits) and str(when.year) in shown_date
    ok_time = hhmm in shown_time or hhmm_12.lower() in shown_time.lower()
    if not (ok_date and ok_time):
        raise RuntimeError(f"Không đặt được lịch: Studio hiển thị '{shown_date} {shown_time}', "
                           f"cần {when:%d/%m/%Y %H:%M}. Đã dừng, chưa bấm Lưu.")
    log("✓ Đã đặt lịch công bố.")


def _get_video_link(page):
    try:
        a = page.locator('ytcp-uploads-dialog a#video-link, ytcp-video-info a, .video-url-fadeable a').first
        return a.get_attribute("href", timeout=3000)
    except Exception:
        return None


def video_id_from_link(link):
    m = re.search(r"(?:youtu\.be/|v=|/video/)([\w-]{6,})", link or "")
    return m.group(1) if m else ""


def upload_video(page, video_path, title, description, playlist=None, tags=None, visibility="SCHEDULE",
                 made_for_kids=False, contains_ai=True, thumbnail_path=None, log=print, dry_run=False,
                 schedule_at=None):
    """Toàn bộ luồng đăng. visibility: PRIVATE | UNLISTED | PUBLIC | SCHEDULE (+ schedule_at).

    dry_run=True: làm hết mọi bước rồi DỪNG trước nút Lưu/Lên lịch cuối; hộp thoại để mở trong Chrome
    cho người dùng kiểm tra (Studio vẫn tải byte lên, video nằm dạng bản nháp — xoá được trong Nội dung).
    Trả về link video (https://youtu.be/…) hoặc None."""
    if visibility == "SCHEDULE" and not schedule_at:
        raise ValueError("visibility=SCHEDULE cần schedule_at (datetime)")
    tags = tags or []

    log("Mở trang tải video lên YouTube Studio...")
    page.goto(UPLOAD_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)
    _check_logged_in(page)
    _dismiss_popups(page)

    log(f"Chọn file: {video_path}")
    page.locator('ytcp-uploads-file-picker input[type="file"]').first.wait_for(state="attached", timeout=30000)
    set_file_via_cdp(page, video_path, log, find_js=_FIND_VIDEO_INPUT_JS, ten="video")
    log("✓ Đã nạp file, chờ hộp thoại chi tiết...")
    page.locator('ytcp-uploads-dialog[workflow-step="DETAILS"], ytcp-uploads-dialog[video-id]') \
        .first.wait_for(state="attached", timeout=120000)
    page.wait_for_timeout(2500)

    log(f"Điền tiêu đề: {title}")
    _fill_textbox(page, ("title-textarea", "title-textbox"), title, log)
    log("Điền mô tả...")
    _fill_textbox(page, ("description-textarea", "description-textbox"), description, log)
    _set_thumbnail(page, thumbnail_path, log)
    if playlist:
        _pick_playlist(page, playlist, log)
    _set_kids(page, made_for_kids, log)
    if tags:
        _fill_tags(page, tags, log)
    _answer_altered_content(page, contains_ai, log)

    video_link = _get_video_link(page)
    if video_link:
        log(f"Link video: {video_link}")

    for i in range(3):
        nxt = page.locator('ytcp-uploads-dialog #next-button').first
        nxt.wait_for(state="visible", timeout=30000)
        nxt.click()
        log(f"✓ Tiếp ({i + 1}/3)")
        page.wait_for_timeout(1500)

    if visibility == "SCHEDULE":
        _set_schedule(page, schedule_at, log)
    else:
        vis_names = {"PRIVATE": "Riêng tư", "UNLISTED": "Không công khai", "PUBLIC": "Công khai"}
        log(f"Chế độ hiển thị: {vis_names.get(visibility, visibility)}")
        radio = page.locator(f'tp-yt-paper-radio-button[name="{visibility}"]').first
        radio.scroll_into_view_if_needed()
        radio.click()
        page.wait_for_timeout(500)

    if dry_run:
        shot = os.path.join(ANH_LOI_DIR, "youtube_chay_thu.png")
        try:
            page.screenshot(path=shot)
            log(f"Ảnh chụp hộp thoại lúc dừng: {shot}")
        except Exception:
            pass
        log("⏸ CHẠY THỬ: đã làm hết các bước — DỪNG trước nút Lưu/Lên lịch. Hộp thoại vẫn mở trong Chrome; "
            "video đang ở dạng bản nháp, CHƯA đăng.")
        return video_link

    _wait_upload_done(page, log)
    done_btn = page.locator('ytcp-uploads-dialog #done-button').first
    done_btn.click()
    log("✓ Đã bấm Lưu/Lên lịch.")
    video_link = _sau_khi_luu(page, done_btn, video_link, log)
    log("🎉 YouTube: xong" + (f" — {video_link}" if video_link else "") + " (Studio xử lý độ phân giải trong nền).")
    return video_link


# ----- sau nút Lưu/Lên lịch -----
RE_HOP_KET_QUA = re.compile(r"Đã lên lịch cho video|đã lên lịch|đã xuất bản|Video published|Video scheduled|"
                            r"vẫn đang xử lý|still processing", re.I)
RE_NUT_DONG_Y = re.compile(r"^\s*(Xác nhận|Đồng ý|Tiếp tục|Vẫn \S.*|Lên lịch|Xuất bản|Lưu|Đã hiểu|Được|Có|OK|Đóng|"
                           r"Confirm|Continue|Schedule.*|Publish.*|Save|Got it|Yes|Okay|Proceed|Close)\s*$", re.I)
RE_NUT_TU_CHOI = re.compile(r"hủy|huỷ|quay lại|bỏ|không|cancel|back|dismiss|later|để sau", re.I)


def _hop_tai_len_dang_mo(done_btn):
    try:
        return done_btn.is_visible(timeout=1500)
    except Exception:
        return False


def _hop_ket_qua(page):
    try:
        kq = page.locator('tp-yt-paper-dialog').filter(visible=True).filter(has_text=RE_HOP_KET_QUA)
        for i in range(kq.count()):
            d = kq.nth(i)
            if d.locator('#done-button').count():
                continue
            return d, " ".join(d.inner_text(timeout=3000).split())
    except Exception:
        pass
    return None, ""


def _dong_hop_ket_qua(page, hop, log):
    for sel in ('ytcp-uploads-still-processing-dialog #close-button', 'ytcp-uploads-still-processing-dialog ytcp-button',
                'ytcp-uploads-share-dialog #close-icon-button', '#close-button', '#close-icon-button'):
        try:
            btn = (hop if sel.startswith('#') else page).locator(sel).first
            if btn.is_visible(timeout=1500):
                btn.click(timeout=3000)
                return True
        except Exception:
            pass
    try:
        dong = hop.locator('ytcp-button, button').filter(has_text=re.compile(r"^\s*(Đóng|Close)\s*$")).filter(visible=True).first
        if dong.count():
            dong.click(timeout=3000)
            return True
    except Exception:
        pass
    log("  ⚠ Không thấy nút Đóng của hộp kết quả — bỏ qua (video đã lưu).")
    return False


def _nut_dong_y_trong(hop):
    try:
        b = hop.locator('#confirm-button').filter(visible=True).first
        if b.count():
            return b, b.inner_text(timeout=1000).strip() or "confirm"
    except Exception:
        pass
    for sel in ('ytcp-button', 'tp-yt-paper-button', 'button'):
        try:
            bs = hop.locator(sel).filter(visible=True)
            n = bs.count()
        except Exception:
            continue
        ung = []
        for k in range(n):
            b = bs.nth(k)
            try:
                t = " ".join(b.inner_text(timeout=1000).split())
            except Exception:
                continue
            if t and RE_NUT_DONG_Y.match(t) and not RE_NUT_TU_CHOI.search(t):
                ung.append((k, b, t))
        if ung:
            k, b, t = ung[-1]
            return b, t
    return None, ""


def _bam_popup_xac_nhan(page, log):
    try:
        dlgs = page.locator('tp-yt-paper-dialog, ytcp-confirmation-dialog, [role="dialog"], [role="alertdialog"]').filter(visible=True)
        n = dlgs.count()
    except Exception:
        return ""
    for i in range(n):
        d = dlgs.nth(i)
        try:
            if d.locator('#done-button').count() or d.locator('#next-button').count():
                continue
            txt = " ".join(d.inner_text(timeout=2000).split())
        except Exception:
            continue
        if not txt or len(txt) > 1500:
            continue
        nut, ten = _nut_dong_y_trong(d)
        if nut is None:
            log(f"  Studio hiện hộp thoại nhưng không thấy nút đồng ý: {txt[:160]!r}")
            continue
        shot = os.path.join(ANH_LOI_DIR, "youtube_popup_gan_nhat.png")
        try:
            page.screenshot(path=shot)
        except Exception:
            pass
        log(f"  Studio hỏi thêm sau khi Lưu: {txt[:200]!r} → bấm '{ten}' (ảnh: {shot})")
        nut.click(timeout=5000)
        page.wait_for_timeout(1500)
        return txt
    return ""


def _sau_khi_luu(page, done_btn, video_link, log, timeout_sec=120):
    """Sau nút Lưu: (a) popup cần xác nhận → bấm đồng ý; (b) hộp tải lên đóng + hộp 'Đã lên lịch cho video'
    → lấy link, Đóng. CHỈ coi là xong khi hộp tải lên đã đóng; quá giờ mà vẫn mở → raise kèm ảnh."""
    t0 = time.time()
    da_bam, bam_lai = 0, False

    def _xu_ly(hop, txt):
        nonlocal video_link
        m = re.search(r"https://(?:youtu\.be|www\.youtube\.com|youtube\.com)/[\w\-?=&./]+", txt)
        if m:
            video_link = m.group(0)
        log(f"  Studio: {txt[:160]}")
        _dong_hop_ket_qua(page, hop, log)
        page.wait_for_timeout(1000)

    while time.time() - t0 < timeout_sec:
        page.wait_for_timeout(1500)
        hop, txt = _hop_ket_qua(page)
        if hop is not None:
            _xu_ly(hop, txt)
            for _ in range(6):
                if not _hop_tai_len_dang_mo(done_btn):
                    break
                page.wait_for_timeout(1000)
            return video_link
        if not _hop_tai_len_dang_mo(done_btn):
            log("  Hộp thoại tải lên đã đóng.")
            for _ in range(4):
                hop, txt = _hop_ket_qua(page)
                if hop is not None:
                    _xu_ly(hop, txt)
                    break
                page.wait_for_timeout(1500)
            return video_link
        if da_bam < 3 and _bam_popup_xac_nhan(page, log):
            da_bam += 1
            continue
        if not bam_lai and time.time() - t0 > 10:
            bam_lai = True
            try:
                if done_btn.is_enabled(timeout=1000):
                    done_btn.click(timeout=3000)
                    log("  (hộp tải lên vẫn mở sau 10 s → bấm Lưu/Lên lịch lần nữa)")
            except Exception:
                pass
    shot = os.path.join(ANH_LOI_DIR, "youtube_loi_sau_luu.png")
    try:
        page.screenshot(path=shot)
    except Exception:
        pass
    raise RuntimeError(f"Đã bấm Lưu/Lên lịch nhưng hộp thoại tải lên vẫn mở sau {timeout_sec}s — có popup Studio chưa "
                       f"xác nhận được? Xem tab Chrome và ảnh {shot}; bấm xác nhận tay rồi chạy lại nếu cần.")


# ----- đọc lịch đã đặt THẬT trên kênh (xếp video mới SAU video đang lên lịch muộn nhất) -----
RE_NGAY_VI = re.compile(r"(\d{1,2}) thg (\d{1,2}), (\d{4})")
RE_GIO_24 = re.compile(r"\b(\d{1,2}):(\d{2})\b")
RE_GIO_12 = re.compile(r"(\d{1,2}):(\d{2})\s*(SA|CH|AM|PM)", re.I)
RE_NGAY_EN = re.compile(r"\b(" + "|".join(MONTHS_EN) + r")\w*\s+(\d{1,2}),\s+(\d{4})")


def _gio_len_lich_trang_sua(page, vid, log):
    page.goto(f"https://studio.youtube.com/video/{vid}/edit", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(4000)
    box = page.locator("ytcp-video-metadata-visibility").first
    box.wait_for(state="visible", timeout=20000)
    if not re.search(r"lên lịch|scheduled", box.inner_text(timeout=3000), re.I):
        return None
    box.scroll_into_view_if_needed()
    box.click()
    ngay_txt = gio_txt = ""
    try:
        picker = page.locator("ytcp-datetime-picker").first
        picker.wait_for(state="visible", timeout=10000)
        page.wait_for_timeout(800)
        ngay_txt = " ".join(picker.locator("#datepicker-trigger").first.inner_text(timeout=5000).split())
        gio_txt = (picker.locator("#time-of-day-container input").first.input_value(timeout=5000) or "").strip()
    finally:
        page.keyboard.press("Escape")
        page.wait_for_timeout(600)
    mn = RE_NGAY_VI.search(ngay_txt)
    if mn:
        y, mo, d = int(mn.group(3)), int(mn.group(2)), int(mn.group(1))
    else:
        me = RE_NGAY_EN.search(ngay_txt)
        if not me:
            log(f"  (YouTube {vid}: không hiểu ngày {ngay_txt!r})")
            return None
        y, mo, d = int(me.group(3)), MONTHS_EN.index(me.group(1)) + 1, int(me.group(2))
    m12 = RE_GIO_12.search(gio_txt)
    if m12:
        h = int(m12.group(1)) % 12 + (12 if m12.group(3).upper() in ("CH", "PM") else 0)
        mi = int(m12.group(2))
    else:
        mg = RE_GIO_24.search(gio_txt)
        if not mg:
            log(f"  (YouTube {vid}: không hiểu giờ {gio_txt!r})")
            return None
        h, mi = int(mg.group(1)), int(mg.group(2))
    return datetime(y, mo, d, h, mi)


def lich_da_dat(page, log=print, toi_da=40):
    """Datetime các video 'Đã lên lịch' ở CẢ tab Shorts lẫn tab Video: ngày lấy ở bảng, giờ ở trang sửa
    từng video (không đọc được giờ → 23:59 ngày đó cho chắc chắn xếp sau). Trả về list đã sắp xếp."""
    page.goto(STUDIO_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)
    _check_logged_in(page)
    m = re.search(r"/channel/(UC[\w-]+)", page.url)
    if not m:
        raise RuntimeError("không lấy được id kênh từ địa chỉ Studio")
    cid = m.group(1)
    tim = []
    for tab in ("short", "upload"):
        page.goto(f"https://studio.youtube.com/channel/{cid}/videos/{tab}", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(6000)
        rows = page.locator("ytcp-video-row")
        for i in range(min(rows.count(), toi_da)):
            r = rows.nth(i)
            try:
                t = " ".join(r.inner_text(timeout=3000).split())
            except Exception:
                continue
            if not re.search(r"Đã lên lịch|Scheduled", t):
                continue
            vid = ""
            try:
                href = r.locator("a#video-title, a[href*='/video/']").first.get_attribute("href", timeout=2000) or ""
                mv = re.search(r"/video/([\w-]+)/", href)
                vid = mv.group(1) if mv else ""
            except Exception:
                pass
            mn = RE_NGAY_VI.search(t)
            ngay = date(int(mn.group(3)), int(mn.group(2)), int(mn.group(1))) if mn else None
            tim.append((tab, vid, ngay, t[:50]))
    out = set()
    for tab, vid, ngay, ten in tim:
        dt = None
        if vid:
            try:
                dt = _gio_len_lich_trang_sua(page, vid, log)
            except Exception:
                dt = None
        if dt is None and ngay is not None:
            dt = datetime.combine(ngay, datetime.min.time()).replace(hour=23, minute=59)
            log(f"  (YouTube: không đọc được giờ của '{ten}' → coi là {dt:%d/%m %H:%M})")
        if dt is not None:
            out.add(dt)
    return sorted(out)
