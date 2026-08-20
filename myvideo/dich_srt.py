# -*- coding: utf-8 -*-
"""
dich_srt.py — Dịch file phụ đề SRT (Trung hoặc Anh) → tiếng Việt, GIỮ NGUYÊN mốc giờ.

Tiếng gốc tự ĐOÁN từ chính nội dung file (nhiều chữ Hán → Trung, còn lại → Anh),
ép bằng --lang zh|en. Đoán từ file chứ không nhận từ ngoài: chạy lẻ bước ② cho
một video cũ vẫn đúng tiếng của nó, khỏi lệ thuộc ô đang chọn trên trang web.

GỘP DÒNG THÀNH CÂU (mặc định, tắt bằng --giu-dong): SRT của bước ① cắt dòng theo
BỀ NGANG MÀN HÌNH (16 chữ Hán / 42 ký tự Anh) nên phần lớn dòng đứt giữa câu —
đo trên bài 895 dòng tiếng Anh: 83% số dòng KHÔNG kết thúc bằng . ! ?. Dịch từng
mẩu như vậy thì Gemini phải đoán, và vì trật tự từ tiếng Việt khác nên ý của câu
này trào sang dòng kia ("…tiền bạc. Nên nếu bạn từng thấy mình"), rồi bước ③ đọc
đúng mẩu lệch đó nên nghe cụt và sai nhịp. Gộp lại trước khi dịch: 895 dòng →
217 câu, mỗi câu dịch trọn nghĩa và đọc trọn hơi. Mốc giờ lấy từ đầu dòng đầu
tới cuối dòng cuối; bước ④ tự xuống dòng khi vẽ nên hiển thị vẫn gọn.

MẶC ĐỊNH dịch bằng GEMINI (web, Firefox profile đã đăng nhập — tái dùng
myvoice/scripts/dich_gemini.py). Cách giữ khớp dòng ↔ mốc giờ: gửi từng LÔ
dòng gắn mã B[x] (x = số thứ tự trong SRT) và yêu cầu Gemini trả về đúng các
mã đó — mỗi mã nhận về gắn thẳng vào mốc giờ của câu tương ứng. Tiến độ lưu
vào <tên>_vi.partial.json sau MỖI lô: lỗi giữa chừng chạy lại là dịch tiếp,
không mất phần đã xong. Câu thiếu / còn nhiều chữ Hán được tự gửi lại (tối đa
2 lượt bổ sung); vẫn thiếu thì giữ nguyên tiếng Trung trong file kết quả.

LƯU Ý: Firefox dùng profile đã đăng nhập Google phải ĐÓNG trước khi chạy
(Firefox khoá profile khi đang mở).

--offline: dịch bằng opus-mt (dich_hanmt: opus-mt-zh-vi cho tiếng Trung,
opus-mt-en-vi cho tiếng Anh) — nhanh, không cần Firefox, nhưng chất lượng thô
hơn hẳn (chỉ nên dùng làm nháp). Model nào chưa có trong scripts/mt_cache thì
lần đầu tự tải (~300MB).

Cách dùng:
    python dich_srt.py "duong_dan/phude.srt"
    python dich_srt.py "phude.srt" --lang en
    python dich_srt.py "phude.srt" --offline

Kết quả (cạnh file gốc):
    <tên>_vi.srt    — chỉ tiếng Việt
    <tên>_zhvi.srt  — song ngữ: dòng 1 tiếng gốc, dòng 2 tiếng Việt
                      (phụ đề tiếng Anh thì tên là <tên>_envi.srt)
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

# ── Tiếng gốc của phụ đề ────────────────────────────────────────────────────
TEN_LANG = {"zh": "Trung", "en": "Anh"}
_HAN_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")


def han_ratio(text):
    """Tỉ lệ chữ Hán trên tổng ký tự không phải khoảng trắng (0..1).

    Viết tại chỗ chứ không mượn dich_gemini.chinese_ratio: đường --offline
    không được kéo theo cả module selenium chỉ để đếm chữ."""
    non_space = sum(1 for c in (text or "") if not c.isspace())
    return len(_HAN_RE.findall(text or "")) / non_space if non_space else 0.0


def doan_lang(texts):
    """Đoán tiếng gốc: nhiều chữ Hán → zh, còn lại → en. Phân biệt Trung/Anh
    bằng bảng chữ nên gần như không sai (SRT Trung ~100% chữ Hán, Anh ~0%)."""
    return "zh" if han_ratio(" ".join(texts[:400])) >= 0.15 else "en"


# ── Gộp dòng thành CÂU ──────────────────────────────────────────────────────
_KET_CAU = ".!?…。！？"          # hết câu → chốt
_PHAY = ",;:，、；："              # ngắt phụ → chỗ chốt dự phòng khi câu quá dài
_DONG_CUOI = "\"'”’」』）)"       # dấu đóng đi sau dấu kết câu
# Trần an toàn khi ASR quên chấm câu cả đoạn dài (đơn vị: ký tự của dòng gộp).
TRAN = {"zh": 70, "en": 200}
# Khe lặng giữa hai dòng ≥ ngần này giây thì coi như hết câu, dù không có dấu.
KHE_LANG = 0.7


def _het_cau(text):
    t = text.rstrip().rstrip(_DONG_CUOI)
    return bool(t) and t[-1] in _KET_CAU


def _noi(a, b, lang):
    """Nối hai mẩu: tiếng Trung viết liền, tiếng Anh chèn khoảng trắng — trừ khi
    mẩu sau mở đầu bằng dấu (vd "-driven" nối vào "data" thành "data-driven")."""
    if not a:
        return b
    if lang == "zh" or not b or not (b[0].isalnum() or b[0] in '"“([{$&@#*'):
        return a + b
    return a + " " + b


def _giay(time_line):
    """(start, end) tính bằng giây từ dòng mốc giờ."""
    m = _TIME_RE.search(time_line)
    def s(x):
        h, mi, rest = x.split(":")
        sec, ms = rest.split(",")
        return int(h) * 3600 + int(mi) * 60 + int(sec) + int(ms) / 1000
    return s(m.group(1)), s(m.group(2))


def gop_cau(cues, lang):
    """[(mốc giờ, text)] theo DÒNG → theo CÂU. Mốc giờ mới = đầu dòng đầu →
    cuối dòng cuối của câu đó.

    Chốt một câu khi: dòng kết thúc bằng . ! ? (hoặc 。！？), HOẶC khe lặng trước
    dòng sau ≥ KHE_LANG giây, HOẶC câu đã vượt trần ký tự — vượt trần thì lùi về
    dòng gần nhất kết thúc bằng dấu phẩy để khỏi cắt giữa cụm từ."""
    tran = TRAN.get(lang, TRAN["en"])
    cau, cum = [], []          # cum: các dòng của câu đang gom

    def _gop(phan):
        txt = ""
        for _tl, t in phan:
            txt = _noi(txt, t.strip(), lang)
        return txt

    def chot(den=None):
        nonlocal cum
        phan, con = (cum, []) if den is None else (cum[:den], cum[den:])
        # Dòng mở đầu bằng dấu là ĐUÔI của từ ở dòng trước ("data" + "-driven"):
        # kéo nó về câu trước, đừng để nó mở đầu câu sau.
        while con and con[0][1].strip()[:1] and not (con[0][1].strip()[0].isalnum()
                                                     or con[0][1].strip()[0] in '"“([{$'):
            phan, con = phan + con[:1], con[1:]
        if phan:
            dau = phan[0][0].split("-->")[0].strip()
            cuoi = phan[-1][0].split("-->")[1].strip()
            cau.append((f"{dau} --> {cuoi}", _gop(phan)))
        cum = con

    for tl, text in cues:
        if cum:
            nghi = _giay(tl)[0] - _giay(cum[-1][0])[1]
            if nghi >= KHE_LANG:            # im lặng = ranh giới câu tự nhiên
                chot()
        cum.append((tl, text))
        if _het_cau(text):
            chot()
        elif len(_gop(cum)) >= tran:
            # Quá dài mà chưa thấy dấu kết câu (ASR quên chấm cả đoạn): lùi về
            # dòng gần nhất kết thúc bằng dấu phẩy. CHỈ lùi khi phần chốt lại còn
            # đủ dài (≥60% trần) — lùi về dấu phẩy ngay đầu cụm thì để lại một
            # mẩu cụt ("So in this video,") mà phần đuôi vẫn dài y như cũ.
            lui = next((i + 1 for i in range(len(cum) - 2, -1, -1)
                        if cum[i][1].rstrip()[-1:] in _PHAY
                        and len(_gop(cum[:i + 1])) >= tran * 0.6), None)
            chot(lui)
    chot()
    return cau


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
# Chỉ bốn chỗ khác nhau giữa Trung và Anh (ví dụ thể loại, tên riêng, từ vay
# mượn, "không chừa chữ gốc") — phần còn lại là luật phụ đề chung cho cả hai.
_RIENG = {
    "zh": {
        "theloai": "cổ trang, tu tiên, hiện đại, hài, tài liệu, đời thường",
        "tenrieng":
            "- Tên riêng (nhân vật, môn phái, địa danh, chức danh, chiêu thức...) giữ "
            "nguyên âm Hán-Việt (ví dụ: 老秦 -> Lão Tần), không Việt hóa tên riêng.\n"
            "- Mỗi câu chỉ nên có tối đa 1-2 từ Hán-Việt \"nặng\", còn lại ưu tiên tiếng "
            "Việt phổ thông để người xem dễ hiểu.\n",
        "khongchua": "không chừa chữ Hán",
    },
    "en": {
        "theloai": "phim truyện, phỏng vấn, tài liệu, hướng dẫn, tin tức, vlog đời thường",
        "tenrieng":
            "- Tên riêng (nhân vật, thương hiệu, địa danh, tên sản phẩm...) GIỮ NGUYÊN "
            "như bản gốc, KHÔNG phiên âm; riêng địa danh/tổ chức đã có tên Việt quen "
            "thuộc thì dùng tên Việt (United Nations -> Liên Hợp Quốc).\n"
            "- Thuật ngữ nào có từ tiếng Việt thông dụng thì dịch hẳn ra tiếng Việt, "
            "đừng để lẫn từ tiếng Anh giữa câu; chỉ giữ tiếng Anh khi là tên riêng hoặc "
            "từ đã quen dùng trong tiếng Việt (video, laptop, app...).\n"
            "- Thành ngữ, lối nói đùa, chơi chữ thì dịch THOÁT sang cách nói tương "
            "đương của người Việt, đừng dịch từng chữ.\n",
        "khongchua": "không chừa nguyên câu tiếng Anh",
    },
}


def gemini_prefix(lang="zh"):
    """Lời dặn gửi KÈM MỖI LÔ, ghép theo tiếng gốc của phụ đề."""
    r = _RIENG.get(lang, _RIENG["zh"])
    return (
        f"Sau đây là các dòng phụ đề tiếng {TEN_LANG.get(lang, 'Trung')} cần "
        "dịch sang tiếng Việt. "
        "Mỗi dòng được đánh dấu bằng mã B[x]. Hãy dịch theo các yêu cầu sau:\n"
        f"- Tự nhận biết thể loại/bối cảnh từ nội dung ({r['theloai']}...) và "
        "dùng giọng văn phù hợp; từ ngữ dễ hiểu, tự nhiên với người Việt hiện "
        "đại; ưu tiên câu ngắn, rõ ràng.\n"
        "- Đây là PHỤ ĐỀ video, người xem chỉ có vài giây để đọc mỗi dòng: dịch "
        "ngắn gọn; không thêm ký tự thừa, không biểu tượng, KHÔNG dùng định dạng "
        "markdown hay danh sách đánh số.\n"
        + r["tenrieng"] +
        "- Xưng hô đúng vai vế và NHẤT QUÁN trong cùng một mối quan hệ (sư phụ - "
        "đệ tử, cha - con, anh - em, tiền bối - vãn bối...).\n"
        "- Hội thoại: dịch đúng từng lời, giữ rõ ai đang nói và ngữ khí phù hợp.\n"
        "- Nhiều dòng liên tiếp có thể là MỘT câu dài bị cắt theo mốc thời gian: "
        "dịch sao cho các dòng đọc nối nhau vẫn mượt, nhưng ý của dòng nào phải "
        "nằm đúng dòng đó, không dồn ý sang dòng khác.\n"
        f"- Dịch sát nghĩa, không thêm bớt nội dung, {r['khongchua']}, giữ "
        "nguyên thứ tự các dòng.\n"
        "- Trả lại ĐÚNG số dòng như đầu vào: mỗi dòng bắt đầu bằng đúng mã B[x] "
        "của nó, mỗi mã đúng 1 dòng, không gộp, không thiếu, không thừa, không "
        "tương tác gì thêm với tôi.\n"
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


def translate_gemini(texts, partial_path, batch_chars=1200, lang="zh"):
    """Dịch qua Gemini web. Trả list cùng độ dài (câu hỏng giữ nguyên tiếng gốc)."""
    import dich_gemini as dg

    prefix = gemini_prefix(lang)
    ten = TEN_LANG.get(lang, "Trung")

    # Chữ ký của ĐẦU VÀO: đổi cách cắt câu (gộp/không gộp, sửa SRT gốc) là chỉ
    # số câu lệch hết → tiến độ cũ mà dùng lại thì bản dịch gắn nhầm mốc giờ.
    chu_ky = f"{len(texts)}|{sum(len(t) for t in texts)}"
    done = {}
    if os.path.exists(partial_path):
        try:
            with open(partial_path, encoding="utf-8") as f:
                d = json.load(f)
            if d.get("chu_ky") == chu_ky:
                done = {int(k): v for k, v in d.get("cau", {}).items()}
                print(f"♻ Tiếp tục phiên trước: đã có {len(done)}/{len(texts)} câu.")
            else:
                print("♻ Bỏ tiến độ dịch cũ: cách cắt câu đã khác, dịch lại từ đầu.")
        except Exception:
            done = {}

    def _save():
        with open(partial_path, "w", encoding="utf-8") as f:
            json.dump({"chu_ky": chu_ky,
                       "cau": {str(k): v for k, v in done.items()}},
                      f, ensure_ascii=False)

    def _ok(i, v):
        """Bản dịch dùng được: có chữ, và không phải là câu gốc chép lại.

        Trung: đo tỉ lệ chữ Hán còn sót. Anh: cùng bảng chữ nên không đo được
        như vậy — so thẳng với câu gốc, y hệt nghĩa là Gemini bỏ qua dòng đó."""
        if not (v and v.strip()):
            return False
        if lang == "zh":
            return dg.chinese_ratio(v) <= 0.3
        return v.strip().casefold() != texts[i].strip().casefold()

    n_total = len(texts)
    driver = None
    try:
        # Lượt 1: dịch tất cả. Lượt 2-3: chỉ gửi lại các câu thiếu/còn Hán.
        for attempt in range(3):
            todo = [i for i in range(n_total) if not _ok(i, done.get(i))]
            if not todo:
                break
            if attempt:
                print(f"🔁 Lượt bổ sung {attempt}: dịch lại {len(todo)} câu "
                      "thiếu/chưa dịch...")
            chunks = _pack_chunks(todo, texts, max_chars=batch_chars)
            for ci, chunk in enumerate(chunks, 1):
                body = "\n".join(f"B[{i + 1}] {texts[i]}" for i in chunk)
                if driver is None or not dg.is_driver_alive(driver):
                    print("🌐 Đang mở Firefox + Gemini...")
                    driver = dg.init_firefox()
                print(f"📤 Gửi lô {ci}/{len(chunks)} ({len(chunk)} câu)...")
                ans = dg.send_to_gemini(driver, body, prefix=prefix)
                restarts = 0
                while not ans and restarts < dg.MAX_TIMEOUT_RESTARTS:
                    restarts += 1
                    print(f"🔄 Không có kết quả — mở lại Firefox (lần {restarts})...")
                    driver = dg.restart_firefox(driver)
                    ans = dg.send_to_gemini(driver, body, prefix=prefix)
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
                n_ok = sum(1 for k in range(n_total) if _ok(k, done.get(k)))
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
        print(f"⚠️ {len(missing)} câu không dịch được — giữ nguyên tiếng {ten} "
              f"(số thứ tự: {', '.join(str(i + 1) for i in missing[:20])}"
              f"{'...' if len(missing) > 20 else ''}).")
    else:
        try:
            os.remove(partial_path)   # xong trọn vẹn → bỏ file tiến độ
        except Exception:
            pass
    return [(done.get(i) or "").strip() or texts[i] for i in range(n_total)]


# ── Dịch OFFLINE (--offline, opus-mt) — chất lượng thô, chỉ nên làm nháp ─────
def translate_offline(texts, batch=32, lang="zh"):
    import dich_hanmt
    model_id = dich_hanmt.MODEL_ID if lang == "zh" else dich_hanmt.MODEL_EN_VI
    if not dich_hanmt.available(model_id):
        print(f"❌ Model dịch offline ({model_id}) không nạp được.")
        return None
    out, total = [], len(texts)
    for i in range(0, total, batch):
        part = texts[i:i + batch]
        vi = dich_hanmt.translate(part, model_id)
        if vi is None:
            vi = []
            for t in part:
                one = dich_hanmt.translate([t], model_id)
                vi.append(one[0] if one else t)
        out.extend(vi)
        print(f"\r⏳ Dịch: {min(i + batch, total)}/{total} câu", end="", flush=True)
    print()
    dich_hanmt.giai_phong(model_id)      # nhả VRAM ngay: bước ③ cần chỗ cho TTS
    return out


def main():
    parser = argparse.ArgumentParser(
        description="Dịch SRT (Trung/Anh) sang tiếng Việt (Gemini web, giữ mốc giờ).")
    parser.add_argument("srt", help="File .srt tiếng Trung hoặc tiếng Anh.")
    parser.add_argument("--lang", default="auto", choices=["auto", "zh", "en"],
                        help="Tiếng gốc của SRT (mặc định auto: tự đoán từ nội dung).")
    parser.add_argument("--giu-dong", action="store_true",
                        help="GIỮ nguyên từng dòng SRT thay vì gộp thành câu trọn "
                             "vẹn (bản dịch và giọng đọc sẽ theo đúng mẩu của bước ①).")
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
    lang = args.lang if args.lang != "auto" else doan_lang(texts)
    print(f"🈯 Tiếng gốc: {TEN_LANG.get(lang, lang)}"
          f"{' (tự đoán)' if args.lang == 'auto' else ''}")

    if not args.giu_dong:
        n_dong = len(cues)
        cues = gop_cau(cues, lang)
        texts = [text for _, text in cues]
        print(f"🧩 Gộp {n_dong} dòng → {len(cues)} câu trọn vẹn "
              f"({n_dong / max(len(cues), 1):.1f} dòng/câu) — dịch và đọc theo CÂU. "
              "Muốn giữ từng dòng thì thêm --giu-dong.")
    if args.offline:
        vi = translate_offline(texts, batch=args.batch, lang=lang)
    else:
        vi = translate_gemini(texts, stem + "_vi.partial.json",
                              batch_chars=args.batch_chars, lang=lang)
    if vi is None:
        sys.exit(1)

    out_vi = write_srt([(t, v) for (t, _), v in zip(cues, vi)], stem + "_vi.srt")
    print(f"💾 Bản tiếng Việt : {out_vi}")
    out_song = write_srt(
        [(t, f"{goc}\n{v}") for (t, goc), v in zip(cues, vi)],
        f"{stem}_{lang}vi.srt")          # _zhvi.srt (Trung) · _envi.srt (Anh)
    print(f"💾 Bản song ngữ   : {out_song}")


if __name__ == "__main__":
    main()
