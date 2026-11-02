# -*- coding: utf-8 -*-
"""Đăng video lên TikTok Studio (tiktok.com/tiktokstudio/upload) qua Chrome thật + Playwright Extension.

Các bước (cách làm mượn từ tool "Đăng video tự động", đã chạy thật trên kênh khác 10/2026):
  1. Mở trang upload, nạp file vào input[type=file] (ẩn) qua CDP → không mở hộp thoại Windows.
  2. Chờ TikTok báo "Đã tải lên".
  3. Ô mô tả là Draft.js: xoá sạch, chèn tiêu đề (MỘT dòng), rồi với TỪNG hashtag: gõ từng ký tự
     "#tag" (bật gợi ý) + chọn đúng dòng gợi ý trùng tên → thẻ có hiệu lực (span.mention).
  4. Lên lịch: radio "Lên lịch" → ngày + giờ (bước 5 phút; sớm nhất 15 phút, muộn nhất 10 ngày).
     Có hai giao diện (cũ: 2 ô readonly; mới ~26/10/2026: 3 ô thả xuống) — tự nhận.
  5. Nút cuối [data-e2e=post_video_button]; xong TikTok về /tiktokstudio/content, hiện "Đã đăng video".
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timedelta

from dang_chung import clear_and_insert, norm_space, set_file_via_cdp, wait_until

UPLOAD_URL = "https://www.tiktok.com/tiktokstudio/upload"
CONTENT_URL = "https://www.tiktok.com/tiktokstudio/content"
THANG_VN = ["Một", "Hai", "Ba", "Tư", "Năm", "Sáu", "Bảy", "Tám", "Chín", "Mười", "Mười Một", "Mười Hai"]
THANG_VN_MOI = ["Một", "Hai", "Ba", "Bốn", "Năm", "Sáu", "Bảy", "Tám", "Chín", "Mười", "Mười Một", "Mười Hai"]
SEL_CAPTION = "div.public-DraftEditor-content"
SEL_POST_BTN = '[data-e2e="post_video_button"]'
SEL_ENTITY = 'span.mention[data-testid="mentionText"]'
SOM_NHAT = timedelta(minutes=15)
MUON_NHAT = timedelta(days=10)


def _check_logged_in(page):
    if re.search(r"/login", page.url) or page.locator('a[href*="/login"], button:has-text("Đăng nhập")').filter(visible=True).count() > 2:
        raise RuntimeError("Chưa đăng nhập TikTok trong profile này — đăng nhập trên Chrome rồi chạy lại.")


def _wait_upload_done(page, log, timeout_sec=1800):
    log("Đang chờ TikTok nhận file...")
    last = ""

    def xong():
        nonlocal last
        if page.locator("text=/Đã tải lên|Uploaded/").filter(visible=True).count():
            return True
        m = re.search(r"(\d{1,3})\s*%", norm_space(page.locator("body").inner_text()))
        if m and m.group(0) != last:
            last = m.group(0)
            log(f"  [đang tải {last}]")
        return False
    wait_until(xong, timeout_sec, every=3, desc="TikTok nhận file")
    log("✓ TikTok đã nhận file (Đã tải lên).")


def _dong_goi_y_trung(page, tag):
    """Dòng gợi ý hashtag có tên TRÙNG HỆT `tag` (vd '#suckhoe 3.2K bài đăng'), không phải thẻ dài hơn."""
    mau = re.compile(rf"^\s*{re.escape(tag)}(\s|$)", re.I)
    cands = page.get_by_text(mau).filter(visible=True)
    for i in range(cands.count()):
        el = cands.nth(i)
        try:
            if el.locator("xpath=ancestor-or-self::*[contains(@class, 'DraftEditor')]").count():
                continue
            txt = norm_space(el.inner_text()).lower()
            if txt.split(" ")[0] == tag.lower():
                return el
        except Exception:
            continue
    return None


def _fill_caption(page, caption, hashtags, log):
    box = page.locator(SEL_CAPTION).first
    box.wait_for(state="visible", timeout=120000)
    log(f"Điền mô tả: {caption}")
    clear_and_insert(page, box, caption.strip(), log, "ô mô tả TikTok")
    for tag in hashtags:
        tag = tag.strip()
        if not tag:
            continue
        if not tag.startswith("#"):
            tag = "#" + tag
        cur = box.inner_text()
        if cur and not cur.endswith((" ", "\n")):
            page.keyboard.type(" ", delay=50)
        truoc = box.locator(SEL_ENTITY).count()
        page.keyboard.type(tag, delay=70)
        page.wait_for_timeout(1500)
        dong = _dong_goi_y_trung(page, tag)
        if dong is not None:
            dong.click()
            cach = "chọn gợi ý trùng tên"
        else:
            page.keyboard.type(" ", delay=50)
            cach = "không có gợi ý trùng, gõ dấu cách"
        page.wait_for_timeout(900)
        sau = box.locator(SEL_ENTITY).count()
        ents = [e.strip().lower() for e in box.locator(SEL_ENTITY).all_inner_texts()]
        log(f"  {tag}: {'✓ thẻ có hiệu lực' if (sau > truoc and tag.lower() in ents) else '⚠ chưa thành thẻ đúng'} ({cach})")
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    doc = norm_space(box.inner_text())
    if not doc.startswith(norm_space(caption)):
        raise RuntimeError(f"Ô mô tả không đúng: {doc[:120]!r}")
    log(f"✓ Mô tả: {doc[:160]}")


def _o_theo_gia_tri(page, mau):
    loc = page.locator("input.TUXTextInputCore-input")
    for i in range(loc.count()):
        if re.fullmatch(mau, loc.nth(i).input_value() or ""):
            return loc.nth(i)
    return None


def lam_tron_5(dt):
    return dt.replace(minute=(dt.minute // 5) * 5, second=0, microsecond=0)


def kiem_gio_hop_le(when, now=None):
    """TikTok chỉ nhận lịch trong [now+15 phút, now+10 ngày]. Trả về chuỗi lỗi hoặc ''."""
    now = now or datetime.now()
    if when < now + SOM_NHAT:
        return f"TikTok chỉ cho lên lịch sớm nhất 15 phút sau: {when:%d/%m/%Y %H:%M} quá gần."
    if when > now + MUON_NHAT:
        return f"TikTok chỉ cho lên lịch tối đa 10 ngày: {when:%d/%m/%Y %H:%M} quá xa."
    return ""


def _chon_ngay(page, when, log):
    o_ngay = _o_theo_gia_tri(page, r"\d{4}-\d{2}-\d{2}")
    if o_ngay is None:
        raise RuntimeError("không thấy ô ngày của phần Lên lịch")
    muon = when.strftime("%Y-%m-%d")
    if o_ngay.input_value() == muon:
        log(f"  Ngày đã đúng {muon}.")
        return
    o_ngay.click()
    page.wait_for_timeout(800)
    lich = page.locator(".calendar-wrapper").filter(visible=True).first
    lich.wait_for(state="visible", timeout=5000)
    for _ in range(13):
        hdr = norm_space(lich.inner_text().split("CN")[0])
        m = re.search(r"Tháng (.+?) / (\d{4})", hdr)
        if not m:
            break
        thang = THANG_VN.index(m.group(1).strip()) + 1 if m.group(1).strip() in THANG_VN else None
        nam = int(m.group(2))
        if thang == when.month and nam == when.year:
            break
        hdr_el = lich.locator("xpath=.//*[contains(normalize-space(.), 'Tháng')]").first.locator("xpath=..")
        nut = hdr_el.locator("xpath=./*").last if (nam, thang or 0) < (when.year, when.month) else hdr_el.locator("xpath=./*").first
        nut.click()
        page.wait_for_timeout(500)
    cells = lich.locator(f'xpath=.//*[normalize-space(text())="{when.day}"]')
    n = cells.count()
    if n == 0:
        raise RuntimeError(f"không thấy ngày {when.day} trong bảng lịch")
    cell = cells.first if when.day <= 15 else cells.nth(n - 1)
    cell.click()
    page.wait_for_timeout(900)
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    if o_ngay.input_value() != muon:
        raise RuntimeError(f"Không đặt được ngày: ô hiện {o_ngay.input_value()!r}, cần {muon}")
    log(f"  ✓ Ngày {muon}")


def _chon_gio(page, when, log):
    o_gio = _o_theo_gia_tri(page, r"\d{1,2}:\d{2}")
    if o_gio is None:
        raise RuntimeError("không thấy ô giờ của phần Lên lịch")
    hh, mm = when.strftime("%H"), when.strftime("%M")
    o_gio.click()
    page.wait_for_timeout(800)
    trai = page.locator(".tiktok-timepicker-option-text.tiktok-timepicker-left").filter(has_text=re.compile(rf"^\s*{hh}\s*$")).first
    phai = page.locator(".tiktok-timepicker-option-text.tiktok-timepicker-right").filter(has_text=re.compile(rf"^\s*{mm}\s*$")).first
    trai.wait_for(state="attached", timeout=5000)
    trai.scroll_into_view_if_needed(); page.wait_for_timeout(300); trai.click(); page.wait_for_timeout(600)
    phai.scroll_into_view_if_needed(); page.wait_for_timeout(300); phai.click(); page.wait_for_timeout(600)
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    page.mouse.click(1200, 300)
    page.wait_for_timeout(300)
    val = o_gio.input_value()
    if val not in (f"{hh}:{mm}", f"{int(hh)}:{mm}"):
        raise RuntimeError(f"Không đặt được giờ: ô hiện {val!r}, cần {hh}:{mm}")
    log(f"  ✓ Giờ {hh}:{mm}")


def _so_trong(s):
    return [int(x) for x in re.findall(r"\d+", s or "")]


def _chon_ngay_gio_moi(page, when, log):
    """Giao diện mới (26/10/2026): ô ngày [role=combobox][aria-label="Select date"] mở .DatePicker__panel
    (tiêu đề .DatePicker__titleMonth/.DatePicker__titleYear, nút Previous/Next month, ngày = button.DatePicker__day
    có aria-label 'Thứ Ba, ngày 27 tháng 10 năm 2026'); ô giờ [aria-label="Select time"] mở .TimePicker__panel với
    2 listbox 'Hours'/'Minutes'. Đọc lại chữ 2 ô để xác minh."""
    o_ngay = page.locator('[role="combobox"][aria-label="Select date"]').first
    o_gio = page.locator('[role="combobox"][aria-label="Select time"]').first
    muon = [when.day, when.month, when.year]
    th = nam = None
    if _so_trong(o_ngay.inner_text()) != muon:
        o_ngay.scroll_into_view_if_needed()
        o_ngay.click()
        page.wait_for_timeout(800)
        panel = page.locator(".DatePicker__panel").filter(visible=True).first
        panel.wait_for(state="visible", timeout=5000)
        for _ in range(13):
            th = norm_space(panel.locator(".DatePicker__titleMonth").first.inner_text()).lower()
            nam = (_so_trong(panel.locator(".DatePicker__titleYear").first.inner_text()) or [0])[0]
            thang = next((i + 1 for i, t in enumerate(THANG_VN_MOI) if th == f"tháng {t}".lower()), None)
            if thang is None or (nam, thang) == (when.year, when.month):
                break
            nut = '[aria-label="Next month"]' if (nam, thang) < (when.year, when.month) else '[aria-label="Previous month"]'
            panel.locator(nut).first.click()
            page.wait_for_timeout(500)
        ngay = panel.locator(f'button.DatePicker__day[aria-label*="ngày {when.day} tháng {when.month:02d} năm {when.year}"]'
                             f':not([data-outside="true"])').first
        try:
            ngay.wait_for(state="visible", timeout=5000)
        except Exception:
            raise RuntimeError(f"không thấy ngày {when:%d/%m/%Y} trong lịch TikTok (lịch đang ở {th} {nam})") from None
        if ngay.get_attribute("disabled") is not None or ngay.get_attribute("data-disabled") == "true":
            raise RuntimeError(f"TikTok không cho chọn ngày {when:%d/%m/%Y} (đã qua hoặc quá 10 ngày tới)")
        ngay.click()
        page.wait_for_timeout(800)
    o_gio.scroll_into_view_if_needed()
    o_gio.click()
    page.wait_for_timeout(800)
    tp = page.locator(".TimePicker__panel").filter(visible=True).first
    tp.wait_for(state="visible", timeout=5000)
    for cot, gt in (("Hours", when.strftime("%H")), ("Minutes", when.strftime("%M"))):
        b = tp.locator(f'[role="listbox"][aria-label="{cot}"] button.TimePicker__item[aria-label="{cot} {gt}"]').first
        b.wait_for(state="attached", timeout=5000)
        b.scroll_into_view_if_needed()
        b.click()
        page.wait_for_timeout(500)
    try:
        page.locator(".scheduled-title-container").first.click()
    except Exception:
        page.keyboard.press("Escape")
    page.wait_for_timeout(600)
    ngay_hien, gio_hien = norm_space(o_ngay.inner_text()), norm_space(o_gio.inner_text())
    if _so_trong(ngay_hien) != muon or _so_trong(gio_hien) != [when.hour, when.minute]:
        raise RuntimeError(f"Không đặt được lịch TikTok: ô hiện '{ngay_hien} {gio_hien}', cần {when:%d/%m/%Y %H:%M}")
    log(f"  ✓ Lịch TikTok: {ngay_hien} {gio_hien}")


def _set_schedule(page, when, log):
    when = lam_tron_5(when)
    loi = kiem_gio_hop_le(when)
    if loi:
        raise ValueError(loi)
    log(f"Lên lịch TikTok: {when:%d/%m/%Y %H:%M}")
    radios = page.locator('input[name="postSchedule"]')
    radios.first.wait_for(state="attached", timeout=30000)
    muc = None
    for i in range(radios.count()):
        nhan = radios.nth(i).evaluate("e => (e.closest('label') || e.parentElement).innerText")
        if "lịch" in nhan.lower() or "schedule" in nhan.lower():
            muc = i
    if muc is None:
        raise RuntimeError("không thấy lựa chọn 'Lên lịch'")
    radios.nth(muc).evaluate("e => (e.closest('label') || e).click()")
    page.wait_for_timeout(1500)
    if page.locator('[role="combobox"][aria-label="Select date"]').count():
        _chon_ngay_gio_moi(page, when, log)
    else:
        _chon_ngay(page, when, log)
        _chon_gio(page, when, log)


RE_NUT_XAC_NHAN = re.compile(r"^\s*(Đăng ngay|Tiếp tục đăng|Tiếp tục|Đăng|Xác nhận|Lên lịch|Post now|Continue|Post)\s*$", re.I)


def _nut_xac_nhan_popup(page):
    """Popup sau nút cuối (vd 'Tiếp tục đăng?' với nút 'Đăng ngay'): nút cần bấm trong hộp thoại đang hiện."""
    dlgs = page.locator('[role="dialog"], .TUXModal, [class*="modal" i], [class*="Modal"]').filter(visible=True)
    for i in range(dlgs.count()):
        d = dlgs.nth(i)
        try:
            txt = norm_space(d.inner_text())
        except Exception:
            continue
        if not txt or len(txt) > 600:
            continue
        bs = d.locator("button").filter(visible=True)
        uu_tien = []
        for k in range(bs.count()):
            b = bs.nth(k)
            t = b.inner_text().strip()
            if RE_NUT_XAC_NHAN.match(t) and not re.search(r"hủy|huỷ|bỏ|cancel|đóng|close|lưu bản nháp", t, re.I):
                uu_tien.append((0 if re.match(r"^\s*Đăng ngay", t, re.I) else 1, k, b))
        if uu_tien:
            uu_tien.sort(key=lambda x: (x[0], x[1]))
            return uu_tien[0][2]
    return None


def upload_video(page, video_path, caption, hashtags=(), schedule_at=None, log=print, dry_run=False):
    """Toàn bộ luồng TikTok. caption: MỘT dòng. hashtags: ['#a', '#b'] gõ từng cái. schedule_at: datetime →
    lên lịch; None → đăng ngay. dry_run: làm hết rồi DỪNG trước nút cuối. Trả về CONTENT_URL khi xong."""
    log("Mở TikTok Studio upload...")
    page.goto(UPLOAD_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2500)
    _check_logged_in(page)
    page.locator('input[type=file]').first.wait_for(state="attached", timeout=60000)
    log(f"Chọn file: {video_path}")
    set_file_via_cdp(page, video_path, log, ten="video")
    page.locator(SEL_CAPTION).first.wait_for(state="visible", timeout=180000)
    _wait_upload_done(page, log)
    _fill_caption(page, caption, list(hashtags or []), log)
    if schedule_at:
        _set_schedule(page, schedule_at, log)
    btn = page.locator(SEL_POST_BTN).first
    btn.wait_for(state="visible", timeout=30000)
    ten_nut = btn.inner_text().strip()
    if dry_run:
        log(f"⏸ CHẠY THỬ: đã làm hết các bước — DỪNG trước nút '{ten_nut}'. Tab vẫn mở để bạn kiểm tra.")
        return None
    if btn.is_disabled():
        raise RuntimeError(f"Nút '{ten_nut}' đang bị khoá — TikTok chưa cho đăng (xem lại mô tả/lịch).")
    btn.click()
    log(f"✓ Đã bấm '{ten_nut}'.")
    deadline = time.time() + 90
    da_bam_popup = False
    while time.time() < deadline:
        if "tiktokstudio/content" in page.url:
            break
        body = norm_space(page.locator("body").inner_text())
        if "Đã đăng video" in body or "Your video has been posted" in body:
            break
        if not da_bam_popup:
            nut_popup = _nut_xac_nhan_popup(page)
            if nut_popup is not None:
                ten = nut_popup.inner_text().strip()
                nut_popup.click()
                da_bam_popup = True
                log(f"  TikTok hỏi xác nhận → đã bấm '{ten}'.")
        time.sleep(1.5)
    page.wait_for_timeout(2000)
    body = norm_space(page.locator("body").inner_text())
    if "Đã đăng video" in body or "tiktokstudio/content" in page.url:
        log("🎉 TikTok: " + ("đã lên lịch" if schedule_at else "đã đăng") + " — xem ở trang Bài đăng.")
        return CONTENT_URL
    raise RuntimeError("Bấm xong nhưng không thấy TikTok xác nhận — kiểm tra tab TikTok.")


# ----- đọc lịch đã đặt (trang Bài đăng hiện '16 tháng 10, 6:00 CH' / '17 tháng 10 2023, 12:00 CH') -----
RE_NGAY_GIO_TT = re.compile(r"(\d{1,2}) tháng (\d{1,2})(?:,? (\d{4}))?,? (\d{1,2}):(\d{2}) (SA|CH)", re.I)


def parse_lich_text(body, now=None):
    """Mọi mốc giờ Ở TƯƠNG LAI ghi trên trang Bài đăng TikTok → list datetime sắp xếp (hàm thuần, có test)."""
    now = now or datetime.now()
    out = set()
    for d, m, y, h, mi, buoi in RE_NGAY_GIO_TT.findall(body or ""):
        gio = int(h) % 12 + (12 if buoi.upper() == "CH" else 0)
        try:
            dt = datetime(int(y) if y else now.year, int(m), int(d), gio, int(mi))
        except ValueError:
            continue
        if dt > now:
            out.add(dt)
    return sorted(out)


def lich_da_dat(page, log=print):
    page.goto(CONTENT_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(6000)
    _check_logged_in(page)
    return parse_lich_text(page.locator("body").inner_text(timeout=15000))
