# -*- coding: utf-8 -*-
"""
dich_hanviet.py — Xử lý chữ Hán còn sót trong bản dịch Gemini.

Gemini đôi khi để lọt vài chữ Hán chưa dịch trong gemini_result.docx. Hai cách xử
lý (dùng offline, không cần Gemini):

  1) transliterate(text)  — PHIÊN ÂM Hán-Việt: mỗi chữ Hán → âm Hán-Việt cố định
     (疑→nghi, 凤凰→phượng hoàng). Tốt cho chữ lẻ/tên/thành ngữ.

  2) translate_han(text)  — HYBRID (khuyến dùng): đoạn Hán DÀI (Gemini sót nguyên
     câu) → dịch NGHĨA bằng model offline dich_hanmt (山鸡→gà rừng); chữ ngắn/tên/
     thành ngữ → phiên âm Hán-Việt. Vì MT hay bịa với input ngắn (疑→'Không nghi
     ngờ…') nên chỉ dùng MT cho đoạn đủ dài.

Bảng tra phiên âm: hanviet_map.tsv (char<TAB>âm, chữ đơn) — sinh 1 lần, offline.

CLI test:
    python dich_hanviet.py "谢静 là 顾灵 của 山鸡 疑神疑鬼"
"""

import re
import sys
from pathlib import Path

_MAP_PATH = Path(__file__).resolve().parent / "hanviet_map.tsv"

# Dải chữ Hán (CJK Unified: cơ bản + Ext A + Compatibility). Chữ hiếm ngoài dải
# này sẽ bị bỏ qua (rất hiếm gặp trong nội dung truyện).
_HAN = re.compile(r'[㐀-䶿一-鿿豈-﫿]+')

_MAP: dict | None = None


def _load() -> dict:
    global _MAP
    if _MAP is None:
        m = {}
        try:
            with open(_MAP_PATH, encoding="utf-8") as f:
                for line in f:
                    if line.startswith("#") or "\t" not in line:
                        continue
                    ch, am = line.rstrip("\n").split("\t", 1)
                    if ch and am:
                        m[ch] = am
        except FileNotFoundError:
            pass  # không có bảng → phiên âm trở thành no-op an toàn
        _MAP = m
    return _MAP


# Dấu câu kiểu Trung (CJK punct + fullwidth forms) — bỏ khi còn sót, tránh TTS đọc
# bậy. KHÔNG đụng dấu ASCII hay nháy cong “ ” của tiếng Việt.
_CJK_PUNCT = re.compile(r'[　-〿！-｠]')


def _tidy(s: str) -> str:
    """Bỏ dấu câu kiểu Trung còn sót + gọn khoảng trắng (giữ xuống dòng)."""
    s = _CJK_PUNCT.sub(' ', s)
    s = re.sub(r'[ \t]+', ' ', s)
    s = re.sub(r' *\n *', '\n', s)
    return s.strip()


def transliterate(text: str) -> tuple[str, int]:
    """Thay mọi chữ Hán còn sót bằng âm Hán-Việt (viết thường, cách nhau bằng
    khoảng trắng). Chữ không có trong bảng thì bỏ. Giữ nguyên xuống dòng.

    Trả về (text_đã_thay, số_chữ_Hán_đã_phiên_âm).
    """
    m = _load()
    count = 0

    def repl(match: "re.Match") -> str:
        nonlocal count
        ams = []
        for ch in match.group(0):
            am = m.get(ch)
            if am:
                ams.append(am)
                count += 1
        return " " + " ".join(ams) + " " if ams else " "

    return _tidy(_HAN.sub(repl, text)), count


# ── HYBRID: đoạn Hán DÀI → dịch nghĩa (MT); NGẮN/tên/thành ngữ → phiên âm ──────
# Ngưỡng theo SỐ CHỮ HÁN của 1 ĐOẠN. Các cụm Hán chỉ cách nhau bởi dấu câu/khoảng
# trắng (kể cả dấu phẩy ASCII của bản gốc) được GỘP làm một câu để MT đủ ngữ cảnh.
MT_MIN_HAN = 6

_HAN_ONE = re.compile(r'[㐀-䶿一-鿿豈-﫿]')
_HAN_RUN = re.compile(r'[㐀-䶿一-鿿豈-﫿]+')
# Khe được phép GỘP giữa 2 cụm Hán: chỉ khoảng trắng + dấu câu (KHÔNG chữ/số) nên
# không bao giờ nuốt sang chữ tiếng Việt (chữ Việt luôn có ký tự chữ cái).
_GAP_OK = re.compile(r'^[\s.,;:!?…—–\-()\[\]"\'“”‘’、，。！？；：（）《》「」『』]{0,4}$')


def translate_han(text: str, on_log=None) -> tuple[str, int, int]:
    """Xử lý chữ Hán còn sót theo kiểu HYBRID:
      • đoạn có ≥ MT_MIN_HAN chữ Hán → dịch NGHĨA bằng dich_hanmt (fallback phiên âm
        nếu model không dùng được);
      • đoạn ngắn / tên riêng / thành ngữ → phiên âm Hán-Việt.

    Trả về (text_đã_xử_lý, số_đoạn_dịch_MT, số_chữ_phiên_âm).
    """
    m = _load()
    runs = [(mm.start(), mm.end()) for mm in _HAN_RUN.finditer(text)]
    if not runs:
        return _tidy(text), 0, 0

    # Gộp các cụm Hán chỉ cách nhau bởi dấu câu/khoảng trắng thành 1 đoạn.
    segs = []
    cs, ce = runs[0]
    for s, e in runs[1:]:
        if _GAP_OK.match(text[ce:s]):
            ce = e
        else:
            segs.append((cs, ce)); cs, ce = s, e
    segs.append((cs, ce))

    def phienam(chars):
        ams = [a for a in (m.get(c) for c in chars) if a]
        return ' ' + ' '.join(ams) + ' ' if ams else ' '

    n_mt = n_am = 0
    res, last = [], 0
    for cs, ce in segs:
        res.append(text[last:cs])            # phần văn bản thường trước đoạn
        seg = text[cs:ce]
        hans = [c for c in seg if _HAN_ONE.match(c)]
        done = False
        if len(hans) >= MT_MIN_HAN:
            try:
                import dich_hanmt as mt
                out = mt.translate([seg])
            except Exception:
                out = None
            vi = out[0].strip() if out and out[0].strip() else None
            if vi:
                n_mt += 1
                if on_log:
                    on_log(f"   • MT: “{seg[:24]}…” → “{vi[:40]}…”")
                res.append(' ' + vi + ' ')
                done = True
        if not done:
            res.append(phienam(hans))
            n_am += sum(1 for c in hans if m.get(c))
        last = ce
    res.append(text[last:])
    return _tidy(''.join(res)), n_mt, n_am


def main(argv=None):
    args = argv if argv is not None else sys.argv[1:]
    sys.stdout.reconfigure(encoding="utf-8")
    if not args:
        print(f"Bảng tra: {_MAP_PATH} ({len(_load())} chữ)")
        print('Dùng: python dich_hanviet.py "谢静 疑神疑鬼"')
        return
    text = " ".join(args)
    out, n_mt, n_am = translate_han(text)
    print(f"[MT {n_mt} đoạn | phiên âm {n_am} chữ]")
    print(out)


if __name__ == "__main__":
    main()
