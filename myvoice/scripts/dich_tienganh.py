"""
dich_tienganh.py — Xử lý từ TIẾNG ANH còn sót trong bản dịch Gemini.

Gemini dịch Trung→Việt đôi khi để lọt nguyên từ tiếng Anh giữa câu Việt
("If thấy hay…", "Twenty năm sau", "Sit vào trong xe", "Hand Liễu Như Yên
run lên"). TTS đọc mấy chữ này rất kỳ nên phải chặn trước khi ghi input.txt.

Hai bước, giống kiểu dich_hanviet:
  1) fix_english(text) — THAY từ tiếng Anh chắc chắn sai bằng tiếng Việt theo
     bảng tienganh_map.tsv, giữ nguyên kiểu hoa/thường (If→Nếu, BUT→NHƯNG).
  2) find_suspects(text) — DÒ các từ ASCII "không giống tiếng Việt" còn lại rồi
     CẢNH BÁO (không tự sửa), để người dùng tự quyết: thêm vào bảng thay, hoặc
     đánh dấu giữ nguyên nếu là tên riêng / từ mượn.

Điểm mấu chốt: KHÔNG được đụng tiếng Việt không dấu hợp lệ. "so" (so sánh),
"in" (bản in), "run" (run rẩy), "net" (quán net), "gen" (đột biến gen), "hot",
"top" đều là tiếng Việt/từ mượn quen thuộc — bảng thay tuyệt đối không chứa
chúng, và bộ dò dùng luật ghép vần tiếng Việt (_VN_SYL) để bỏ qua chúng.

Bảng tra: tienganh_map.tsv (en<TAB>vi, cột 2 là "=" nghĩa là giữ nguyên).

Chạy thử:
    python dich_tienganh.py "If thấy hay thì Sit xuống, Twenty năm sau"
"""

import re
import sys
from pathlib import Path

_MAP_PATH = Path(__file__).resolve().parent / "tienganh_map.tsv"

# Cột 2 mang giá trị này = "từ hợp lệ, GIỮ NGUYÊN, đừng cảnh báo": tên riêng,
# thương hiệu, từ mượn đã quen (video, camera, hot search, Mercedes…) VÀ những
# từ trùng tiếng Việt không dấu (so, in, run, net, gen…). Dòng "=" luôn thắng
# dòng thay — chốt an toàn để không bao giờ sửa hỏng chữ tiếng Việt thật.
_KEEP_MARK = "="

_MAP: dict | None = None       # en(thường) → vi
_KEEP: set | None = None       # en(thường) giữ nguyên
_RE: "re.Pattern | None" = None  # regex khớp mọi khóa trong _MAP


# ── Luật ghép vần tiếng Việt (bỏ dấu) ────────────────────────────────────────
# Dùng để nhận ra "từ này TRÔNG như tiếng Việt" → không cảnh báo. Chỉ cần đúng
# tương đối: sai kiểu bỏ sót thì mất một cảnh báo, không làm hỏng văn bản.
_VN_SYL = re.compile(
    r'^(?:ngh|ng|nh|ch|gh|gi|kh|ph|th|tr|qu|[bcdghklmnprstvx])?'      # âm đầu
    r'(?:uye|uya|uyu|uoi|uou|ieu|yeu|oai|oay|oao|oeo|uai|uay|'        # vần 3
    r'ai|ao|au|ay|eo|eu|ia|ie|iu|oa|oe|oi|oo|ua|ue|ui|uo|uu|uy|ya|ye|yu|'
    r'a|e|i|o|u|y)'                                                   # vần 1
    r'(?:ch|ng|nh|[cmnpt])?$',                                        # âm cuối
    re.IGNORECASE)

# Token chữ cái (kể cả chữ Việt có dấu) — chỉ xét token TOÀN ASCII.
_WORD = re.compile(r'[^\W\d_]+', re.UNICODE)


def _load() -> tuple[dict, set, "re.Pattern | None"]:
    global _MAP, _KEEP, _RE
    if _MAP is None:
        m, keep = {}, set()
        try:
            with open(_MAP_PATH, encoding="utf-8") as f:
                for line in f:
                    line = line.rstrip("\n")
                    if line.startswith("#") or "\t" not in line:
                        continue
                    en, vi = line.split("\t", 1)
                    en, vi = en.strip().lower(), vi.strip()
                    if not en or not vi:
                        continue
                    if vi == _KEEP_MARK:
                        keep.add(en)
                        m.pop(en, None)     # cột "=" luôn thắng: cấm thay
                    elif en not in keep:
                        m[en] = vi
        except FileNotFoundError:
            pass  # không có bảng → thành no-op an toàn
        _MAP, _KEEP = m, keep
        _RE = re.compile(
            r'\b(?:' + '|'.join(re.escape(k) for k in
                                sorted(m, key=len, reverse=True)) + r')\b',
            re.IGNORECASE) if m else None
    return _MAP, _KEEP, _RE


def _looks_vietnamese(w: str) -> bool:
    """True nếu w (ASCII, thường) ghép vần được theo luật tiếng Việt không dấu."""
    return bool(_VN_SYL.match(w))


def _match_case(src: str, dst: str) -> str:
    """Chép kiểu hoa/thường của từ gốc sang từ thay: BUT→NHƯNG, But→Nhưng."""
    if src.isupper() and len(src) > 1:
        return dst.upper()
    if src[0].isupper():
        return dst[0].upper() + dst[1:]
    return dst


def fix_english(text: str, on_log=None) -> tuple[str, int, list]:
    """Thay từ tiếng Anh sót → tiếng Việt và dò từ lạ còn lại.

    Trả về (text_đã_sửa, số_từ_đã_thay, danh_sách_từ_nghi_ngờ).
    Từ nghi ngờ CHỈ để cảnh báo — hàm này không tự ý sửa chúng.
    """
    m, _keep, rx = _load()
    n = 0
    seen = {}

    def repl(mm: "re.Match") -> str:
        nonlocal n
        w = mm.group(0)
        vi = _match_case(w, m[w.lower()])
        n += 1
        seen[w.lower()] = (w, vi)
        return vi

    out = rx.sub(repl, text) if rx else text
    if on_log:
        for w, vi in seen.values():
            on_log(f"   • EN: “{w}” → “{vi}”")
    return out, n, find_suspects(out)


def find_suspects(text: str) -> list:
    """Các từ ASCII không ghép vần được theo tiếng Việt và không nằm trong danh
    sách giữ nguyên — nhiều khả năng là tiếng Anh sót hoặc tên riêng mới.

    Trả về list từ (chữ thường, không trùng lặp) theo thứ tự xuất hiện.
    """
    _m, keep, _rx = _load()
    out, got = [], set()
    for w in _WORD.findall(text or ""):
        if not w.isascii() or len(w) < 2:
            continue
        low = w.lower()
        if low in got or low in keep or _looks_vietnamese(low):
            continue
        got.add(low)
        out.append(low)
    return out


def main(argv=None):
    args = argv if argv is not None else sys.argv[1:]
    sys.stdout.reconfigure(encoding="utf-8")
    m, keep, _rx = _load()
    if not args:
        print(f"Bảng tra: {_MAP_PATH} ({len(m)} từ thay, {len(keep)} từ giữ nguyên)")
        print('Dùng: python dich_tienganh.py "If thấy hay thì Sit xuống"')
        print('      python dich_tienganh.py -f duong_dan_input.txt')
        return
    if args[0] in ("-f", "--file"):
        text = Path(args[1]).read_text(encoding="utf-8")
        _out, n, sus = fix_english(text)
        print(f"[thay {n} từ]")
        print("Từ nghi ngờ:", ", ".join(sus) if sus else "(không có)")
        return
    out, n, sus = fix_english(" ".join(args))
    print(f"[thay {n} từ | nghi ngờ {len(sus)}]")
    print(out)
    if sus:
        print("Từ nghi ngờ:", ", ".join(sus))


if __name__ == "__main__":
    main()
