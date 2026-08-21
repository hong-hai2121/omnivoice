# -*- coding: utf-8 -*-
"""Sinh SEO (tiêu đề · mô tả · thẻ tag) cho video đã dịch — từ <base>_vi.srt.

Cách chạy (web xếp vào HÀNG ĐỢI CHÍNH — dùng Firefox nên không được chạy song
song với bước ② dịch):
    venv\\Scripts\\python.exe myvideo\\seo_video.py --base "<thư mục>/<tên>_x0.7"
    (lặp --base để làm nhiều video trong MỘT phiên Firefox)

Cách hoạt động: mượn bộ lái Gemini của myvoice (dich_gemini — Selenium Firefox
profile đã đăng nhập, KHÔNG cần API key), mỗi video mở CHAT MỚI rồi gửi phụ đề
tiếng Việt kèm lời dặn; trả về theo mốc "TIÊU ĐỀ / MÔ TẢ / THẺ TAG" thì ghi
<base>_seo.json = {"title", "desc", "tags"}. File này là nguồn caption cho cả
đăng YouTube (dang_youtube.py) lẫn lên lịch Facebook (FACEBOOK/…).

⚠️ Firefox phải ĐÓNG trước khi chạy (Selenium cần khoá profile) — y hệt bước ②.
Tên kênh (nếu muốn nhắc trong mô tả) đặt ở khoá `seo_kenh` trong
myvideo/web/web_settings.json — kênh MỚI chưa đặt tên thì cứ để trống.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]              # …/OmniVoice
VENV_PY = ROOT / "venv" / "Scripts" / "python.exe"
OUTPUT_DIR = ROOT / "myvideo" / "output"
SETTINGS_FILE = ROOT / "myvideo" / "web" / "web_settings.json"

sys.path.insert(0, str(ROOT / "myvoice" / "scripts"))
import dich_gemini as dg  # noqa: E402  (bộ lái Firefox/Gemini dùng chung)

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass

MAX_INPUT_CHARS = 5000      # phụ đề dài thì phần đầu là đủ cho Gemini nắm nội dung
ATTEMPTS = 2                # mỗi video thử tối đa bấy nhiêu lượt (chat mới mỗi lượt)

_XTAG_CUOI = re.compile(r"_x\d+(?:\.\d+)?$")
_TIMESTAMP = re.compile(r"^\d{2}:\d{2}:\d{2}[,.]\d{3}\s*-->")


def ten_hienthi(base: str) -> str:
    name = base.split("/")[-1]
    m = _XTAG_CUOI.search(name)
    return name[: m.start()] if m else name


def _srt_text(path: Path) -> str:
    """Ruột chữ của file SRT: bỏ số thứ tự, mốc giờ, dòng trống, gộp một mạch."""
    lines = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = raw.strip().lstrip("\ufeff")
        if not s or s.isdigit() or _TIMESTAMP.match(s):
            continue
        lines.append(s)
    return " ".join(lines)


def _prompt(noi_dung: str, kenh: str) -> str:
    """Lời dặn TỰ CHỨA — gửi vào chat mới trống vẫn ra đúng định dạng."""
    dong_kenh = (f"Video sẽ đăng trên kênh YouTube \"{kenh}\" — có thể nhắc tên "
                 "kênh trong mô tả nếu tự nhiên.\n" if kenh else "")
    return (
        "Bạn là chuyên gia SEO YouTube cho video tiếng Việt. Dưới đây là phụ đề "
        "tiếng Việt của một video. Hãy viết bộ SEO đúng nội dung video, hấp dẫn "
        "nhưng không giật tít sai sự thật.\n"
        + dong_kenh +
        "TRẢ VỀ ĐÚNG ĐỊNH DẠNG SAU, không thêm lời dẫn nào khác:\n"
        "TIÊU ĐỀ: <một dòng duy nhất, 50-90 ký tự, tiếng Việt có dấu>\n"
        "MÔ TẢ:\n"
        "<4-6 dòng mô tả nội dung; dòng cuối cùng là 4-6 hashtag>\n"
        "THẺ TAG: <khoảng 400 ký tự, các thẻ phân cách bằng dấu phẩy, gồm từ "
        "khoá chính, chủ đề, và cụm người xem hay tìm>\n\n"
        "PHỤ ĐỀ VIDEO:\n"
    ) + noi_dung


def _parse(text: str) -> dict | None:
    """Bóc {"title", "desc", "tags"} từ câu trả lời — định vị theo TỪ KHOÁ,
    không phụ thuộc hoa thường hay markdown Gemini tự thêm."""
    if not text:
        return None
    t = re.sub(r"[*#>`]+", "", text)          # gỡ markdown trang trí
    m_tit = re.search(r"TI[ÊE]U\s*[ĐD][ỀE]\s*:?\s*(.+)", t, re.IGNORECASE)
    m_desc = re.search(r"M[ÔO]\s*T[ẢA]\s*:?\s*\n", t, re.IGNORECASE)
    m_tag = re.search(r"TH[ẺE]\s*TAG\s*:?\s*", t, re.IGNORECASE)
    if not (m_tit and m_desc and m_tag):
        return None
    title = m_tit.group(1).strip().strip('"').strip()
    desc = t[m_desc.end(): m_tag.start()].strip()
    tags = [x.strip() for x in t[m_tag.end():].replace("\n", ",").split(",") if x.strip()]
    if not (5 <= len(title) <= 150) or len(desc) < 30 or not tags:
        return None
    return {"title": title, "desc": desc, "tags": tags}


def seo_valid(base: str) -> bool:
    try:
        d = json.loads((OUTPUT_DIR / f"{base}_seo.json").read_text(encoding="utf-8"))
        return bool(d.get("title"))
    except (OSError, ValueError):
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description="Sinh SEO từ SRT tiếng Việt (Gemini web)")
    ap.add_argument("--base", action="append", default=[],
                    help="gốc video trong output (lặp cờ cho nhiều video)")
    ap.add_argument("--force", action="store_true", help="làm lại cả video đã có SEO")
    args = ap.parse_args()
    if not args.base:
        print("⛔ Thiếu --base.")
        return 2

    try:
        kenh = (json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                .get("seo_kenh") or "").strip()
    except (OSError, ValueError):
        kenh = ""

    viec = []
    for base in args.base:
        srt = OUTPUT_DIR / f"{base}_vi.srt"
        if not srt.is_file():
            print(f"⛔ {ten_hienthi(base)}: chưa có {srt.name} — chạy bước ② trước.")
            return 2
        if not args.force and seo_valid(base):
            print(f"⏭ {ten_hienthi(base)}: đã có SEO — bỏ qua (dùng --force để làm lại).")
            continue
        viec.append((base, srt))
    if not viec:
        print("✅ Không có video nào cần SEO.")
        return 0

    print("🦊 Mở Firefox (Gemini)... Firefox đang mở sẵn thì phải đóng trước.")
    driver = dg.init_firefox()
    loi = 0
    try:
        for i, (base, srt) in enumerate(viec):
            print(f"📑 [{i + 1}/{len(viec)}] {ten_hienthi(base)}")
            noi_dung = _srt_text(srt)[:MAX_INPUT_CHARS]
            seo = None
            for lan in range(1, ATTEMPTS + 1):
                # Mỗi lượt một CHAT MỚI — gửi vào chat cũ dễ đọc nhầm câu trả
                # lời trước đó (bài học tập 55-58 bên myvoice dùng chung SEO).
                if not dg.is_driver_alive(driver):
                    driver = dg.restart_firefox(driver)
                else:
                    driver.get(dg.GEMINI_URL)
                    time.sleep(6)
                tra_loi = dg.send_to_gemini(driver, _prompt(noi_dung, kenh))
                seo = _parse(tra_loi or "")
                if seo:
                    break
                print(f"  ⚠️ Lượt {lan}: câu trả lời không đúng định dạng"
                      + (" — thử lại chat mới..." if lan < ATTEMPTS else ""))
            if not seo:
                # KHÔNG ghi bừa kết quả hỏng — thiếu SEO thì đăng bài dùng tên
                # video, còn hơn mang tiêu đề sai của video khác.
                print(f"  ⛔ Bỏ qua {ten_hienthi(base)} — Gemini không trả đúng định dạng.")
                loi += 1
                continue
            seo["made_at"] = datetime.now().isoformat(timespec="seconds")
            out = OUTPUT_DIR / f"{base}_seo.json"
            out.write_text(json.dumps(seo, ensure_ascii=False, indent=2),
                           encoding="utf-8")
            print(f"  ✅ «{seo['title']}» → {out.name}")
    finally:
        try:
            driver.quit()
        except Exception:
            pass
    print(f"🏁 Xong: {len(viec) - loi}/{len(viec)} video có SEO.")
    return 0 if loi == 0 else 2


if __name__ == "__main__":
    if VENV_PY.exists() and Path(sys.executable).resolve() != VENV_PY.resolve():
        import subprocess
        raise SystemExit(subprocess.call([str(VENV_PY), *sys.argv], cwd=str(ROOT)))
    raise SystemExit(main())
