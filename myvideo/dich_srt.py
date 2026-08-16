# -*- coding: utf-8 -*-
"""
dich_srt.py — Dịch file phụ đề SRT tiếng Trung → tiếng Việt, GIỮ NGUYÊN mốc giờ.

MẶC ĐỊNH dịch bằng GEMINI (web, Firefox profile đã đăng nhập — tái dùng
myvoice/scripts/dich_gemini.py). Cách giữ khớp dòng ↔ mốc giờ: gửi từng LÔ
dòng gắn mã B[x] (x = số thứ tự trong SRT) và yêu cầu Gemini trả về đúng các
mã đó — mỗi mã nhận về gắn thẳng vào mốc giờ của câu tương ứng. Tiến độ lưu
vào <tên>_vi.partial.json sau MỖI lô: lỗi giữa chừng chạy lại là dịch tiếp,
không mất phần đã xong. Câu thiếu / còn nhiều chữ Hán được tự gửi lại (tối đa
2 lượt bổ sung); vẫn thiếu thì giữ nguyên tiếng Trung trong file kết quả.

LƯU Ý: Firefox dùng profile đã đăng nhập Google phải ĐÓNG trước khi chạy
(Firefox khoá profile khi đang mở).

--offline: dịch bằng opus-mt-zh-vi (dich_hanmt) — nhanh, không cần Firefox,
nhưng chất lượng thô hơn hẳn (chỉ nên dùng làm nháp).

Cách dùng:
    python dich_srt.py "duong_dan/phude.srt"
    python dich_srt.py "phude.srt" --offline

Kết quả (cạnh file gốc):
    <tên>_vi.srt    — chỉ tiếng Việt
    <tên>_zhvi.srt  — song ngữ: dòng 1 tiếng Trung, dòng 2 tiếng Việt
"""

import sys
import os

# ── Tự chuyển sang python của venv (selenium/transformers nằm ở đó) ──────────
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
_VENV_PYTHON = os.path.join(_REPO_ROOT, "venv", "Scripts", "python.exe")
if __name__ == "__main__" and os.path.exists(_VENV_PYTHON) and \
        os.path.normcase(os.path.abspath(sys.executable)) != \
        os.path.normcase(os.path.abspath(_VENV_PYTHON)):
    import subprocess
    sys.exit(subprocess.run([_VENV_PYTHON] + sys.argv).returncode)

import argparse
import json
import re

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MYVOICE_SCRIPTS = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "myvoice", "scripts"))
sys.path.insert(0, MYVOICE_SCRIPTS)

_TIME_RE = re.compile(
    r"(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})")


# ── Đọc / ghi SRT ────────────────────────────────────────────────────────────
def parse_srt(path):
    """Đọc SRT → list [(time_line, text)]. Text nhiều dòng được nối thành 1 dòng."""
    with open(path, encoding="utf-8-sig") as f:
        content = f.read()
    cues = []
    for block in re.split(r"\n\s*\n", content.strip()):
        lines = [l for l in block.splitlines() if l.strip()]
        if len(lines) < 2:
            continue
        ti = 1 if _TIME_RE.search(lines[1] if len(lines) > 1 else "") else 0
        m = _TIME_RE.search(lines[ti])
        if not m:
            continue
        text = " ".join(l.strip() for l in lines[ti + 1:]).strip()
        if text:
            cues.append((lines[ti].strip(), text))
    return cues


def write_srt(cues_texts, out_path):
    """cues_texts: list [(time_line, text)] — text có thể nhiều dòng (song ngữ)."""
    with open(out_path, "w", encoding="utf-8") as f:
        for i, (time_line, text) in enumerate(cues_texts, 1):
            f.write(f"{i}\n{time_line}\n{text}\n\n")
    return out_path


# ── Dịch bằng GEMINI (mặc định) ──────────────────────────────────────────────
# Chỉ dẫn gửi KÈM MỖI LÔ (không dựa vào ngữ cảnh chat — sau restart hay lượt
# dịch bù vẫn đúng luật, và luật đánh dấu là thứ quyết định parse được kết quả).
#
# Vì sao mã B[x] chứ KHÔNG đánh số trần "12."?  Số trần bị Gemini hiểu là danh
# sách markdown: số thứ tự được vẽ bằng CSS ::marker, KHÔNG nằm trong text mà
# Selenium đọc được → mất sạch số, parse 0 câu (đã dính 2026-08-16, phí 50+ lượt
# gửi). B[x] không phải cú pháp markdown nên luôn còn nguyên trong text.
GEMINI_PREFIX = (
    "Sau đây là các dòng phụ đề tiếng Trung cần dịch sang tiếng Việt. "
    "Mỗi dòng được đánh dấu bằng mã B[x]. Hãy dịch theo các yêu cầu sau:\n"
    "- Tự nhận biết thể loại/bối cảnh từ nội dung (cổ trang, tu tiên, hiện đại, "
    "hài, tài liệu, đời thường...) và dùng giọng văn phù hợp; từ ngữ dễ hiểu, "
    "tự nhiên với người Việt hiện đại; ưu tiên câu ngắn, rõ ràng.\n"
    "- Đây là PHỤ ĐỀ video, người xem chỉ có vài giây để đọc mỗi dòng: dịch ngắn "
    "gọn; không thêm ký tự thừa, không biểu tượng, KHÔNG dùng định dạng "
    "markdown hay danh sách đánh số.\n"
    "- Tên riêng (nhân vật, môn phái, địa danh, chức danh, chiêu thức...) giữ "
    "nguyên âm Hán-Việt (ví dụ: 老秦 -> Lão Tần), không Việt hóa tên riêng.\n"
    "- Mỗi câu chỉ nên có tối đa 1-2 từ Hán-Việt \"nặng\", còn lại ưu tiên tiếng "
    "Việt phổ thông để người xem dễ hiểu.\n"
    "- Xưng hô đúng vai vế và NHẤT QUÁN trong cùng một mối quan hệ (sư phụ - đệ "
    "tử, cha - con, anh - em, tiền bối - vãn bối...).\n"
    "- Hội thoại: dịch đúng từng lời, giữ rõ ai đang nói và ngữ khí phù hợp.\n"
    "- Nhiều dòng liên tiếp có thể là MỘT câu dài bị cắt theo mốc thời gian: "
    "dịch sao cho các dòng đọc nối nhau vẫn mượt, nhưng ý của dòng nào phải nằm "
    "đúng dòng đó, không dồn ý sang dòng khác.\n"
    "- Dịch sát nghĩa, không thêm bớt nội dung, không chừa chữ Hán, giữ nguyên "
    "thứ tự các dòng.\n"
    "- Trả lại ĐÚNG số dòng như đầu vào: mỗi dòng bắt đầu bằng đúng mã B[x] của "
    "nó, mỗi mã đúng 1 dòng, không gộp, không thiếu, không thừa, không tương "
    "tác gì thêm với tôi.\n"
    "- Suy nghĩ kỹ trước khi trả lời để bản dịch mạch lạc, dễ hiểu và chính xác."
)

# Dòng kết quả: "B[12] nội dung" (chấp nhận B12., B[12]:, rác markdown đầu dòng;
# fallback "12. nội dung" NẾU Gemini vẫn trả số trần kèm dấu ngăn cách)
_NUM_LINE_RE = re.compile(
    r"^\s*[*\-–>#]*\s*(?:B\s*\[?\s*(\d+)\s*\]?\s*[.)、:：．]?|(\d+)\s*[.)、:：．])\s*(.*)$",
    re.IGNORECASE)


def _parse_numbered(answer):
    """Bóc {số: bản dịch} từ câu trả lời. Dòng không mã → nối vào mã gần nhất."""
    out, cur = {}, None
    for line in (answer or "").splitlines():
        m = _NUM_LINE_RE.match(line)
        if m:
            cur = int(m.group(1) or m.group(2))
            out[cur] = m.group(3).strip()
        elif cur is not None and line.strip():
            out[cur] = (out[cur] + " " + line.strip()).strip()
    return out


def _pack_chunks(idxs, texts, max_chars=1200, max_lines=60):
    """Gom các chỉ số câu thành lô: mỗi lô ≤ max_chars ký tự và ≤ max_lines dòng."""
    chunks, cur, size = [], [], 0
    for i in idxs:
        line_len = len(texts[i]) + 6
        if cur and (size + line_len > max_chars or len(cur) >= max_lines):
            chunks.append(cur)
            cur, size = [], 0
        cur.append(i)
        size += line_len
    if cur:
        chunks.append(cur)
    return chunks


def translate_gemini(texts, partial_path, batch_chars=1200):
    """Dịch qua Gemini web. Trả list cùng độ dài (câu hỏng giữ nguyên tiếng Trung)."""
    import dich_gemini as dg

    done = {}
    if os.path.exists(partial_path):
        try:
            with open(partial_path, encoding="utf-8") as f:
                done = {int(k): v for k, v in json.load(f).items()}
            print(f"♻ Tiếp tục phiên trước: đã có {len(done)}/{len(texts)} câu.")
        except Exception:
            done = {}

    def _save():
        with open(partial_path, "w", encoding="utf-8") as f:
            json.dump({str(k): v for k, v in done.items()}, f, ensure_ascii=False)

    def _ok(v):
        """Bản dịch dùng được: có chữ, không còn đa phần chữ Hán."""
        return bool(v and v.strip()) and dg.chinese_ratio(v) <= 0.3

    n_total = len(texts)
    driver = None
    try:
        # Lượt 1: dịch tất cả. Lượt 2-3: chỉ gửi lại các câu thiếu/còn Hán.
        for attempt in range(3):
            todo = [i for i in range(n_total) if not _ok(done.get(i))]
            if not todo:
                break
            if attempt:
                print(f"🔁 Lượt bổ sung {attempt}: dịch lại {len(todo)} câu thiếu/còn Hán...")
            chunks = _pack_chunks(todo, texts, max_chars=batch_chars)
            for ci, chunk in enumerate(chunks, 1):
                body = "\n".join(f"B[{i + 1}] {texts[i]}" for i in chunk)
                if driver is None or not dg.is_driver_alive(driver):
                    print("🌐 Đang mở Firefox + Gemini...")
                    driver = dg.init_firefox()
                print(f"📤 Gửi lô {ci}/{len(chunks)} ({len(chunk)} câu)...")
                ans = dg.send_to_gemini(driver, body, prefix=GEMINI_PREFIX)
                restarts = 0
                while not ans and restarts < dg.MAX_TIMEOUT_RESTARTS:
                    restarts += 1
                    print(f"🔄 Không có kết quả — mở lại Firefox (lần {restarts})...")
                    driver = dg.restart_firefox(driver)
                    ans = dg.send_to_gemini(driver, body, prefix=GEMINI_PREFIX)
                if not ans:
                    print("⚠️ Lô này không nhận được kết quả — để lượt bổ sung xử lý.")
                    continue
                parsed = _parse_numbered(ans)
                got = 0
                for i in chunk:
                    v = (parsed.get(i + 1) or "").strip()
                    if v:
                        done[i] = v
                        got += 1
                _save()   # ← lưu ngay sau mỗi lô, lỗi giữa chừng không mất gì
                n_ok = sum(1 for k in range(n_total) if _ok(done.get(k)))
                print(f"✅ Lô {ci}/{len(chunks)}: nhận {got}/{len(chunk)} câu "
                      f"— tổng {n_ok}/{n_total}.")
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass

    missing = [i for i in range(n_total) if not (done.get(i) or "").strip()]
    if missing:
        print(f"⚠️ {len(missing)} câu không dịch được — giữ nguyên tiếng Trung "
              f"(số thứ tự: {', '.join(str(i + 1) for i in missing[:20])}"
              f"{'...' if len(missing) > 20 else ''}).")
    else:
        try:
            os.remove(partial_path)   # xong trọn vẹn → bỏ file tiến độ
        except Exception:
            pass
    return [(done.get(i) or "").strip() or texts[i] for i in range(n_total)]


# ── Dịch OFFLINE (--offline, opus-mt) — chất lượng thô, chỉ nên làm nháp ─────
def translate_offline(texts, batch=32):
    import dich_hanmt
    if not dich_hanmt.available():
        print("❌ Model dịch offline (opus-mt-zh-vi) không nạp được.")
        return None
    out, total = [], len(texts)
    for i in range(0, total, batch):
        part = texts[i:i + batch]
        vi = dich_hanmt.translate(part)
        if vi is None:
            vi = []
            for t in part:
                one = dich_hanmt.translate([t])
                vi.append(one[0] if one else t)
        out.extend(vi)
        print(f"\r⏳ Dịch: {min(i + batch, total)}/{total} câu", end="", flush=True)
    print()
    return out


def main():
    parser = argparse.ArgumentParser(
        description="Dịch SRT tiếng Trung sang tiếng Việt (Gemini web, giữ mốc giờ).")
    parser.add_argument("srt", help="File .srt tiếng Trung.")
    parser.add_argument("--offline", action="store_true",
                        help="Dịch bằng opus-mt offline (nhanh, thô) thay vì Gemini.")
    parser.add_argument("--batch", type=int, default=32,
                        help="(offline) Số câu dịch mỗi lô (mặc định 32).")
    parser.add_argument("--batch-chars", type=int, default=1200,
                        help="(gemini) Cỡ mỗi lô gửi, tính bằng ký tự (mặc định 1200).")
    args = parser.parse_args()

    if not os.path.isfile(args.srt):
        print(f"❌ Không tìm thấy file: {args.srt}")
        sys.exit(1)

    cues = parse_srt(args.srt)
    if not cues:
        print("❌ Không đọc được câu nào từ SRT.")
        sys.exit(1)
    print(f"📖 Đã đọc {len(cues)} câu từ: {os.path.basename(args.srt)}")

    stem = os.path.splitext(args.srt)[0]
    texts = [text for _, text in cues]
    if args.offline:
        vi = translate_offline(texts, batch=args.batch)
    else:
        vi = translate_gemini(texts, stem + "_vi.partial.json",
                              batch_chars=args.batch_chars)
    if vi is None:
        sys.exit(1)

    out_vi = write_srt([(t, v) for (t, _), v in zip(cues, vi)], stem + "_vi.srt")
    print(f"💾 Bản tiếng Việt : {out_vi}")
    out_zhvi = write_srt(
        [(t, f"{zh}\n{v}") for (t, zh), v in zip(cues, vi)], stem + "_zhvi.srt")
    print(f"💾 Bản song ngữ   : {out_zhvi}")


if __name__ == "__main__":
    main()
