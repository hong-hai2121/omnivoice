# -*- coding: utf-8 -*-
"""
dich_lai_trong.py — Dịch lại các đoạn còn TRỐNG trong gemini_result.docx của
từng thư mục tập (kịch_bản/<số tập> - <tên>/).

Đoạn TRỐNG = đoạn mà bản dịch chỉ là "(trống)" / "(chưa dịch)" / rỗng / thiếu hẳn
tiêu đề "Đoạn k" (theo dich_gemini.blank_chunks). Đoạn đã có chữ — kể cả đoạn bị
chốt là "dịch lặp" / "dịch cụt" — KHÔNG đụng tới: việc đó là của bước dịch chính
(⏩ Chạy tiếp / ② Dịch), còn ở đây chỉ lấp chỗ trống.

Cách gửi: MỖI ĐOẠN TRỐNG GỬI LÊN GEMINI ĐÚNG MỘT LẦN — không mở lại Firefox,
không cắt đôi, không gửi lại khi kết quả xấu. Kết quả nhận về in nguyên văn ra
nhật ký và ghi ngay vào gemini_result.docx để người dùng tự kiểm; đoạn nào Gemini
vẫn không trả lời (hoặc trả câu TỪ CHỐI) thì để nguyên "(trống)" và báo rõ.
Trước khi ghi đè, bản gemini_result.docx cũ được sao lưu cạnh đó
(gemini_result.saoluu_<ngày-giờ>.docx) để lùi lại được.

Chạy:
    python dich_lai_trong.py --episode 98            # một tập
    python dich_lai_trong.py --episode 98,99,100     # nhiều tập, cùng một Firefox
    python dich_lai_trong.py --all                   # mọi tập có đoạn trống
    python dich_lai_trong.py --episode 98 --doan 1,4 # chỉ các đoạn trống này
    python dich_lai_trong.py --all --dry-run         # chỉ liệt kê, không gửi
    python dich_lai_trong.py --episode 98 --giu-firefox   # xong không đóng Firefox

Mã thoát: 0 = mọi đoạn trống đã có nội dung (hoặc không có gì để làm) ·
          77 = vẫn còn đoạn trống sau lượt gửi (kiểm nhật ký rồi chạy lại) ·
          2 = lỗi (không tìm thấy tập / thiếu tiengTrung.docx).
Bản web (web/steps.py: retranslate_steps) gọi đúng file này với --episode.
"""

import sys
import os

# ── Tự chuyển sang python của venv (giống các script khác trong thư mục này) ──
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
_VENV_PYTHON = os.path.join(_REPO_ROOT, "venv", "Scripts", "python.exe")
if __name__ == "__main__" and os.path.exists(_VENV_PYTHON) and \
        os.path.normcase(os.path.abspath(sys.executable)) != \
        os.path.normcase(os.path.abspath(_VENV_PYTHON)):
    import subprocess
    sys.exit(subprocess.run([_VENV_PYTHON] + sys.argv).returncode)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_BASE_DIR = os.path.dirname(_SCRIPTS_DIR)                       # myvoice/
for _p in (_REPO_ROOT, _SCRIPTS_DIR, os.path.join(_BASE_DIR, "YOUTUBE"), _BASE_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import argparse
import logging
import shutil
import time
from datetime import datetime
from pathlib import Path

import dich_gemini as g
# Dùng lại cách dò thư mục tập / đọc tiengTrung.docx / câu hướng dẫn dịch của GUI
# (một nguồn sự thật, xem web/core.py). Import module này không mở cửa sổ nào.
import amain_taogiong_gui as gui

STOP = 77       # còn đoạn trống sau lượt gửi — dừng có chủ ý, khớp STOP_CODE web/steps.py
ERROR = 2


def log(text=""):
    print(text, flush=True)


def _setup_logging():
    """logging.* của các hàm GUI mượn dùng (vd kiem_ban_dich_folder) đổ ra stdout."""
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for h in list(root.handlers):
        root.removeHandler(h)
    h = logging.StreamHandler(stream=sys.stdout)
    h.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(h)


def _doc_pairs(folder):
    """(đường dẫn gemini_result.docx, chunks tiếng Trung, kết quả hiện có) của 1 tập.
    Thiếu bản nhận diện → chunks rỗng."""
    folder = Path(folder)
    gem = folder / "gemini_result.docx"
    zh = gui.find_zh_docx(folder)
    chunks = gui.read_zh_docx_chunks(zh) if zh else []
    prior = (g.read_results_docx(gem, len(chunks)) if chunks and gem.exists()
             else [None] * len(chunks))
    return gem, chunks, prior


def _backup(gem):
    """Sao lưu gemini_result.docx cạnh file gốc trước khi ghi đè → đường dẫn hoặc None."""
    if not gem.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dst = gem.with_name(f"gemini_result.saoluu_{stamp}.docx")
    try:
        shutil.copy2(gem, dst)
        return dst
    except OSError as e:
        log(f"⚠️ Không sao lưu được {gem.name}: {e}")
        return None


def _ket_qua_xau(chunk, ans):
    """Nhận xét kết quả vừa nhận (chỉ để BÁO, không gửi lại): list lý do, [] = ổn."""
    notes = []
    if g.is_result_too_short(chunk, ans):
        notes.append("ngắn bất thường so với nguồn (dịch cụt?)")
    if g.is_result_duplicated(ans, chunk):
        notes.append("có dấu hiệu dịch hai lần nối nhau")
    if not g.is_translation_done(ans):
        notes.append("còn nhiều chữ Hán")
    return notes


def run_folder(folder, episode, only=None, dry_run=False, driver=None):
    """Lấp các đoạn trống của MỘT tập. → (driver, số đoạn còn trống, số đoạn đã gửi).

    driver: Firefox đang mở (dùng chung cho nhiều tập) — None thì tự mở khi cần.
    Mỗi tập mở một CHAT MỚI rồi gửi câu hướng dẫn dịch trước đoạn đầu (chat mới
    chưa có ngữ cảnh), giống _dich_gemini_cho_tap của GUI.
    Số đoạn còn trống = -1 nghĩa là tập này lỗi (thiếu bản nhận diện).
    """
    folder = Path(folder)
    gem, chunks, prior = _doc_pairs(folder)
    log(f"📂 Tập {episode} — {folder.name}")
    if not chunks:
        log("❌ Chưa có bản nhận diện tiếng Trung (tiengTrung.docx) → không dịch được.")
        return driver, -1, 0
    if not gem.exists():
        log(f"ℹ️ Chưa có {gem.name} — tập này chưa dịch lần nào; dùng bước ② Dịch chứ "
            "không phải lấp chỗ trống.")
        return driver, 0, 0

    todo = g.blank_chunks(prior)
    if only:
        skipped = [j for j in only if j not in todo]
        if skipped:
            log(f"ℹ️ Bỏ qua đoạn {skipped}: không trống (đã có nội dung) hoặc ngoài "
                f"phạm vi 1..{len(chunks)}.")
        todo = [j for j in todo if j in only]
    if not todo:
        log(f"✅ Không có đoạn trống nào trong {gem.name} ({len(chunks)} đoạn).")
        return driver, 0, 0

    log(f"🕳 {len(todo)}/{len(chunks)} đoạn trống: {todo}")
    if dry_run:
        for j in todo:
            log(f"   • đoạn {j}: {len(chunks[j - 1])} chữ nguồn")
        return driver, len(todo), 0

    # Mở Firefox (lần đầu) hoặc mở CHAT MỚI cho tập này.
    if driver is None:
        log("🌐 Đang mở Firefox + Gemini...")
        driver = g.init_firefox()
    else:
        driver.get(g.GEMINI_URL)
        time.sleep(8)
    g.send_prefix_to_gemini(driver, gui.load_prefix(), on_log=log)

    results = list(prior)
    backed_up = False
    sent = 0
    for n, j in enumerate(todo, 1):
        chunk = chunks[j - 1]
        tag = g.FICTION_TAG.strip()
        tagged = (tag + "\n" + chunk) if tag else chunk
        log(f"📤 [{n}/{len(todo)}] Gửi đoạn {j}/{len(chunks)} ({len(chunk)} ký tự) — "
            "một lần duy nhất...")
        try:
            ans = g.send_to_gemini(driver, tagged, on_log=log)
        except Exception as e:
            log(f"❌ Lỗi khi gửi đoạn {j}: {e} — giữ nguyên (trống), sang đoạn kế.")
            continue
        sent += 1
        ans = (ans or "").strip()
        if not ans:
            log(f"⚠️ Đoạn {j}: Gemini không trả về nội dung → giữ nguyên (trống).")
            continue
        if g.is_refusal(ans):
            log(f"🚫 Đoạn {j}: Gemini TỪ CHỐI dịch → giữ nguyên (trống). Câu trả về:\n"
                f"    {ans[:300]}")
            continue

        log(f"\n========== KẾT QUẢ ĐOẠN {j}/{len(chunks)} ==========\n{ans}\n"
            "==========================================")
        for note in _ket_qua_xau(chunk, ans):
            log(f"⚠️ Đoạn {j}: {note} — vẫn ghi, hãy kiểm lại.")
        results[j - 1] = ans
        if not backed_up:
            dst = _backup(gem)
            if dst:
                log(f"🗂 Đã sao lưu bản cũ → {dst.name}")
            backed_up = True
        g.save_results_docx(chunks, results, gem)
        log(f"💾 Đã ghi đoạn {j} vào {gem.name}")

    remaining = g.blank_chunks(results)
    if remaining:
        log(f"⚠️ Tập {episode}: còn {len(remaining)} đoạn trống {remaining} — kiểm nhật "
            "ký ở trên rồi chạy lại khi cần.")
    else:
        log(f"🎉 Tập {episode}: đã lấp đủ {len(todo)} đoạn trống.")
    return driver, len(remaining), sent


def _parse_ints(text):
    out = []
    for part in (text or "").replace(";", ",").split(","):
        part = part.strip()
        if part.isdecimal():
            out.append(int(part))
    return out


def _folders_with_blanks():
    """Mọi thư mục tập có ít nhất một đoạn trống → list (folder, số tập)."""
    out = []
    for folder in gui.episode_dirs():
        gem, chunks, prior = _doc_pairs(folder)
        if chunks and gem.exists() and g.blank_chunks(prior):
            out.append((folder, gui.episode_of(folder.name)))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Dịch lại các đoạn (trống) trong gemini_result.docx — mỗi đoạn gửi "
                    "Gemini đúng một lần.")
    ap.add_argument("--episode", default="",
                    help="Số tập, nhiều tập cách nhau bằng dấu phẩy (vd 98 hoặc 98,99).")
    ap.add_argument("--folder", default="", help="Đường dẫn thư mục tập (thay cho --episode).")
    ap.add_argument("--all", action="store_true", help="Mọi tập trong kịch_bản/ có đoạn trống.")
    ap.add_argument("--doan", default="",
                    help="Chỉ gửi các đoạn trống này (số đoạn 1-based, vd 1,4). Dùng với 1 tập.")
    ap.add_argument("--dry-run", action="store_true", help="Chỉ liệt kê đoạn trống, không gửi.")
    ap.add_argument("--giu-firefox", action="store_true",
                    help="Xong không đóng Firefox (mặc định đóng để không khoá profile).")
    args = ap.parse_args(argv)

    _setup_logging()

    targets = []
    if args.folder:
        f = Path(args.folder)
        if not f.is_dir():
            log(f"❌ Không tìm thấy thư mục: {f}")
            return ERROR
        targets.append((f, gui.episode_of(f.name) or f.name))
    for ep in _parse_ints(args.episode):
        f = gui.find_episode_dir(ep)
        if f is None:
            log(f"❌ Không tìm thấy thư mục tập {ep:02d} trong {gui.SCRIPT_DIR}")
            return ERROR
        targets.append((f, str(ep).zfill(2)))
    if args.all:
        seen = {str(f) for f, _ in targets}
        targets += [(f, ep) for f, ep in _folders_with_blanks() if str(f) not in seen]
    if not targets:
        if args.all:
            log("✅ Không tập nào còn đoạn trống.")
            return 0
        ap.error("cần --episode, --folder hoặc --all")

    only = _parse_ints(args.doan) or None
    if only and len(targets) > 1:
        log("⚠️ --doan chỉ dùng với MỘT tập → bỏ qua, xét mọi đoạn trống.")
        only = None

    driver = None
    still_blank = 0
    total_sent = 0
    errors = 0
    try:
        for folder, ep in sorted(targets, key=lambda t: str(t[1])):
            driver, remaining, sent = run_folder(folder, ep, only=only,
                                                 dry_run=args.dry_run, driver=driver)
            if remaining < 0:
                errors += 1
            else:
                still_blank += remaining
            total_sent += sent
            log("")
    finally:
        if driver is not None and not args.giu_firefox:
            try:
                driver.quit()
                log("🦊 Đã đóng Firefox.")
            except Exception:
                pass

    if args.dry_run:
        log(f"ℹ️ Chạy thử: {still_blank} đoạn trống trong {len(targets)} tập — chưa gửi gì.")
        return 0
    log(f"📊 Đã gửi {total_sent} đoạn · còn trống {still_blank} đoạn · {errors} tập lỗi.")
    if errors and not total_sent:
        return ERROR
    return STOP if still_blank else 0


if __name__ == "__main__":
    sys.exit(main())
