# -*- coding: utf-8 -*-
"""
taogiong_nghethu_srt.py — 🎧 NGHE THỬ cài đặt giọng của bước ③ (tông / bộ lọc / chuẩn âm /
âm lượng) trên ~30 giây GIỌNG THẬT của một video đã tạo giọng — không chạy lại TTS, không GPU.

Mang từ myvoice/scripts/taogiong_nghethu.py (06/11/2026) sang ngày 09/11/2026 theo ý user
"mang các cài đặt giọng nói qua bên myvideo": cùng cách lấy mẫu, cùng thứ tự áp; phần hậu kỳ
gọi ĐÚNG hàm của bài thật (taogiong_srt.hau_ky_audio) nên nghe thử sao, bước ③ ra vậy. Tên
module khác bên myvoice (hậu tố _srt) vì web myvideo có cả myvoice/scripts lẫn myvideo/ trong
sys.path — trùng tên là import nhầm bản bên kia.

Khác myvoice ở chỗ LẤY MẪU: myvideo không có kịch_bản/<tập>/output_chunks mà là
output/<tên>/<base>_vi_tts/0001.wav… (taogiong_srt.generate_all), sổ _vanban.json ở đó ghi lời
từng câu + giọng ("clone|<file>"; video của bản 04–09/11 có thể là "vieneu|…") + mức 🔆 đã sinh.

MẪU GỐC lấy ở đâu
    <base>_vi_tts/0001.wav, 0002.wav… là từng câu engine sinh ra, CHƯA qua hậu kỳ
    (<base>_vi_audio.wav thì đã qua — áp thêm lần nữa là chồng hiệu ứng). Ghép các câu đầu:
    cân mức giữa các câu (không neo mốc) → cắt mép im lặng → chèn nghỉ theo dấu cuối câu,
    tới khi đủ MAU_GIAY rồi dừng ở CUỐI CÂU. (Bài thật đặt câu lên timeline theo SRT nên
    khoảng nghỉ thật dài ngắn tuỳ câu — mẫu chỉ cần nghe được âm sắc + mức.)

LƯU Ở ĐÂU (myvideo/voice/_nghe_thu/caidat/ — ngoài output/ nên xoá video vẫn còn mẫu;
cả myvideo/voice/ đã nằm trong .gitignore)
    mau_goc.wav   — đúng MỘT mẫu gốc; có mẫu mới là ghi đè bản cũ
    mau_goc.json  — mẫu lấy từ video nào, giọng nào, dài bao nhiêu, đọc câu gì
    xt_<mã>.wav   — bản đã áp một bộ cài đặt (nghe lại cùng bộ số thì khỏi dựng lại);
                    chỉ giữ XT_GIU bản mới nhất, đổi mẫu gốc là xoá hết

CHỌN VIDEO NÀO (chon_video) — như chon_tap bên myvoice
    Trong các video ĐÃ CÓ GIỌNG (thư mục _tts có 0001.wav + sổ _vanban.json), xếp theo lúc
    TẠO thư mục _tts; "đợt" = các video tạo liền nhau, hai cái cách nhau từ DOT_CACH_GIO giờ
    là sang đợt khác. Lấy video ĐẦU TIÊN của đợt MỚI NHẤT (mẫu đứng yên suốt một đợt). Đợt
    mới chưa video nào có giọng → vẫn là video đầu của đợt trước; output/ trống → giữ mẫu.

KHI NÀO THAY MẪU (cap_nhat)
    Video được chọn khác video của mẫu đang lưu, hoặc chữ ký đổi (đọc lại bằng engine /
    giọng khác, đổi mức 🔆, dịch lại → sổ _vanban.json hay 0001.wav đổi). Gọi mỗi lần bấm 🎧
    (route POST /nghethu của web myvideo).

ÁP CÀI ĐẶT (nghe_thu) — đúng thứ tự bài thật (taogiong_srt.hau_ky_audio):
    [chuẩn âm: neo mốc −18 dBFS như _balance_chunk_levels(moc=True) trong mix_audio] →
    tông + bộ lọc (một lượt ffmpeg) → [chuẩn âm: nén + loudnorm −14 LUFS] → 🔊 âm lượng.
    Lệch duy nhất: 🔆 Sáng giọng ở engine OmniVoice còn EQ cả GIỌNG MẪU lúc sinh câu, mà câu
    trong mẫu đã sinh ở mức sáng của video đó → nghe thử chỉ thấy phần EQ áp lên audio (web
    báo khi hai mức lệch nhau).

Chạy lẻ:
    venv\\Scripts\\python myvideo\\taogiong_nghethu_srt.py                  # xem / lấy mẫu
    venv\\Scripts\\python myvideo\\taogiong_nghethu_srt.py --pitch 1 --sang 80 --amluong 5
"""

import hashlib
import json
import os
import re
import shutil
import sys
import threading
import time
from pathlib import Path

import numpy as np
import soundfile as sf

_HERE = Path(__file__).resolve().parent            # myvideo/
_REPO = _HERE.parent
_MYVOICE_SCRIPTS = _REPO / "myvoice" / "scripts"
for _p in (str(_HERE), str(_MYVOICE_SCRIPTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import hieuung_giong as hu            # noqa: E402

OUTPUT_DIR = _HERE / "output"
MAU_DIR = _HERE / "voice" / "_nghe_thu" / "caidat"
MAU_WAV = "mau_goc.wav"
MAU_JSON = "mau_goc.json"
SO_VAN_BAN = "_vanban.json"           # sổ của taogiong_srt.generate_all trong thư mục _tts
TTS_DUOI = "_tts"

MAU_GIAY = 30.0                   # mẫu dài ít nhất ngần này (rồi dừng ở cuối câu)
MAU_GIAY_TOI_DA = 36.0            # câu cuối kéo quá mức này → cắt về MAU_GIAY, vát đuôi
MAU_GIAY_IT_NHAT = 8.0            # video chưa đủ ngần này giây giọng gốc → chưa lấy mẫu được
VAT_GIAY = 0.30                   # vát nhỏ dần khi phải cắt giữa câu
DUOI_GIAY = 0.50                  # im lặng cuối mẫu (đuôi vang có chỗ tắt)
DOT_CACH_GIO = 6.0                # hai video tạo giọng cách nhau từ ngần này giờ = hai đợt
XT_GIU = 6                        # số bản nghe thử đã áp cài đặt được giữ lại
VAN_BAN_TOI_DA = 600              # ký tự lời đọc ghi vào mau_goc.json (để xem mẫu đọc gì)
QUET_TOI_DA = 400                 # quét tối đa bấy nhiêu file câu đầu (câu rỗng không có wav)

_XT_RE = re.compile(r"^xt_[0-9a-f]{12}\.wav$")
_KHOA = threading.RLock()         # một tiến trình chỉ một lượt dựng/đổi mẫu cùng lúc


class ChuaCoMau(RuntimeError):
    """Chưa có mẫu nào và output/ cũng chưa có video nào đã tạo giọng để lấy."""


def _gui():
    """amain_taogiong_gui của myvoice (cân mức, cắt mép, nghỉ theo dấu, mốc −18 dBFS) —
    nạp trễ: web myvideo chỉ import module này lúc bấm 🎧."""
    import amain_taogiong_gui as g
    return g


def _ts():
    """taogiong_srt của myvideo — hau_ky_audio là ĐÚNG hàm bài thật dùng ở cuối bước ③."""
    import taogiong_srt as t
    return t


# ── CHỌN VIDEO ──────────────────────────────────────────────────────────────────
def _tao_luc(p: Path) -> float:
    """Lúc TẠO thư mục (Windows: st_ctime là giờ tạo; Python 3.12+ có st_birthtime)."""
    st = Path(p).stat()
    return float(getattr(st, "st_birthtime", st.st_ctime))


def tts_dirs() -> list:
    """Mọi thư mục <base>_vi_tts trong output/: mỗi video một thư mục con (chuẩn hiện nay)
    hoặc nằm thẳng trong output/ (kết quả cũ dạng phẳng)."""
    if not OUTPUT_DIR.is_dir():
        return []
    ds = [p for p in OUTPUT_DIR.glob(f"*/*{TTS_DUOI}") if p.is_dir()]
    ds += [p for p in OUTPUT_DIR.glob(f"*{TTS_DUOI}") if p.is_dir()]
    return ds


def ten_video(tts_dir) -> str:
    """Tên video để hiện: '<base>' (bỏ đuôi _vi_tts / _tts)."""
    n = Path(tts_dir).name
    if n.endswith(TTS_DUOI):
        n = n[: -len(TTS_DUOI)]
    if n.endswith("_vi"):
        n = n[:-3]
    return n


def doc_so(tts_dir) -> dict:
    """Sổ _vanban.json → {"giong": str, "sang": int, "cau": [lời từng câu]}; sổ bản cũ (list
    thuần) = clone, mức 0; không đọc được → {}."""
    try:
        d = json.loads((Path(tts_dir) / SO_VAN_BAN).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if isinstance(d, list):
        return {"giong": "", "sang": 0, "cau": [str(x) for x in d]}
    if not isinstance(d, dict):
        return {}
    return {"giong": str(d.get("giong") or ""), "sang": hu.parse_fx(d.get("sang"), 0),
            "cau": [str(x) for x in (d.get("cau") or [])]}


def co_giong(tts_dir) -> bool:
    """Video đã tạo giọng: có câu đầu + có sổ ghi đủ lời (sổ trống = đang đọc lại dở)."""
    d = Path(tts_dir)
    try:
        return (d / "0001.wav").stat().st_size > 4096 and bool(doc_so(d).get("cau"))
    except OSError:
        return False


def _chu_ky(tts_dir) -> str:
    """Chữ ký để biết video đã sinh lại giọng: giọng + mức 🔆 + số câu + giờ sửa sổ / câu đầu."""
    d = Path(tts_dir)
    so = doc_so(d)
    try:
        m1 = int((d / SO_VAN_BAN).stat().st_mtime)
        m2 = int((d / "0001.wav").stat().st_mtime)
    except OSError:
        m1 = m2 = 0
    return f"{so.get('giong', '')}|{so.get('sang', 0)}|{len(so.get('cau') or [])}|{m1}|{m2}"


def chon_video():
    """Thư mục _tts để lấy mẫu: video ĐẦU TIÊN của đợt mới nhất trong các video đã có giọng
    (xem đầu file). Không video nào có giọng → None."""
    ds = []
    for p in tts_dirs():
        if not co_giong(p):
            continue
        try:
            ds.append((_tao_luc(p), p.name, p))
        except OSError:
            pass
    if not ds:
        return None
    ds.sort()
    dau = len(ds) - 1
    while dau > 0 and ds[dau][0] - ds[dau - 1][0] < DOT_CACH_GIO * 3600:
        dau -= 1
    return ds[dau][2]


# ── MẪU GỐC ─────────────────────────────────────────────────────────────────────
def doc_mau():
    """Thông tin mẫu đang lưu (dict của mau_goc.json); chưa có / file wav mất → None."""
    try:
        meta = json.loads((MAU_DIR / MAU_JSON).read_text(encoding="utf-8"))
        if not isinstance(meta, dict) or (MAU_DIR / MAU_WAV).stat().st_size <= 4096:
            return None
    except (OSError, ValueError):
        return None
    return meta


def tao_mau(tts_dir) -> dict:
    """Dựng mẫu gốc từ các câu đầu trong `tts_dir` rồi THAY mẫu đang lưu (bản cũ bị ghi đè,
    các bản xt_ dựng từ nó bị xoá). Trả thông tin mẫu mới; không đủ giọng gốc → ChuaCoMau."""
    gui = _gui()
    d = Path(tts_dir)
    so = doc_so(d)
    loi_so = so.get("cau") or []

    parts, cau, sr, tong = [], [], None, 0.0
    for i in range(max(len(loi_so), 1) if loi_so else QUET_TOI_DA):
        if tong >= MAU_GIAY or i >= QUET_TOI_DA:
            break
        f = d / f"{i + 1:04d}.wav"
        try:
            if f.stat().st_size <= 4096:
                continue                                # câu đang ghi dở / câm
            x, r = sf.read(str(f), dtype="float32", always_2d=False)
        except FileNotFoundError:
            if loi_so:
                continue                                # câu rỗng không có wav → câu sau
            break                                       # sổ cũ không rõ số câu: hết
        except Exception:
            break
        if x.ndim > 1:
            x = x.mean(axis=1)
        if sr is None:
            sr = int(r)
        elif int(r) != sr:
            break
        chu = loi_so[i] if i < len(loi_so) and loi_so[i] else "."
        parts.append(x)
        cau.append(chu)
        tong += len(gui._trim_edges(x, sr)) / sr + gui._pause_after(chu)
    if not parts or tong < MAU_GIAY_IT_NHAT:
        raise ChuaCoMau(f"{ten_video(d)}: chưa đủ giọng gốc trong {d.name} để lấy mẫu")

    # Mốc mức tiếng nói (trung vị) TRƯỚC khi cân — bước neo −18 dBFS của chuẩn âm cần nó.
    muc = [m for m in (gui._speech_rms(p, sr) for p in parts) if m > 1e-4]
    muc_rms = float(np.median(muc)) if muc else 0.0
    parts = gui._balance_chunk_levels(parts, sr, moc=False)
    am = gui._join_with_pauses(parts, cau, sr)
    cat = len(am) / sr > MAU_GIAY_TOI_DA
    if cat:                                             # câu cuối dài quá → cắt, vát cho khỏi cụt
        am = am[: int(MAU_GIAY * sr)].copy()
        n = min(int(VAT_GIAY * sr), len(am))
        am[-n:] *= np.linspace(1.0, 0.0, n, dtype="float32")
    am = np.concatenate([am, np.zeros(int(DUOI_GIAY * sr), dtype="float32")])

    loi = " ".join(str(c).strip() for c in cau) if loi_so else ""
    chu_ky = _chu_ky(d)
    try:
        thu_muc = str(d.relative_to(OUTPUT_DIR))
    except ValueError:
        thu_muc = str(d)
    meta = dict(
        video=ten_video(d), thu_muc=thu_muc, chu_ky=chu_ky,
        ma=hashlib.sha1(f"{thu_muc}|{chu_ky}|{time.time()}".encode("utf-8")).hexdigest()[:10],
        tao_luc=_tao_luc(d), lay_luc=time.time(),
        so_cau=len(parts), giay=round(len(am) / sr, 2), sr=sr, muc_rms=muc_rms,
        cat_giua_cau=bool(cat), nghi_theo_dau=bool(loi_so),
        # Mức 🔆 lúc sinh các câu (clone EQ cả giọng mẫu) + giọng đã đọc ("clone|…").
        sang_goc=int(so.get("sang") or 0), giong=str(so.get("giong") or ""),
        van_ban=loi[:VAN_BAN_TOI_DA] + ("…" if len(loi) > VAN_BAN_TOI_DA else ""),
    )

    with _KHOA:
        MAU_DIR.mkdir(parents=True, exist_ok=True)
        tam = MAU_DIR / f"mau_goc.{os.getpid()}.tmp.wav"
        try:
            sf.write(str(tam), am, sr, subtype="PCM_16")
            _xoa_ban_nghe()                             # các bản dựng từ mẫu cũ
            os.replace(tam, MAU_DIR / MAU_WAV)          # thay = bản cũ mất, chỉ còn một mẫu
        finally:
            tam.unlink(missing_ok=True)
        (MAU_DIR / MAU_JSON).write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                                        encoding="utf-8")
    return meta


def cap_nhat(log=None):
    """Bảo đảm mẫu đang lưu là của video chon_video() chỉ ra; lệch thì dựng lại + thay.
    Trả thông tin mẫu đang dùng. Không video nào có giọng → giữ mẫu cũ; chưa từng có → None."""
    with _KHOA:
        cu = doc_mau()
        try:
            d = chon_video()
        except Exception:
            d = None
        if d is None:
            return cu
        try:
            thu_muc = str(d.relative_to(OUTPUT_DIR))
        except ValueError:
            thu_muc = str(d)
        if cu and cu.get("thu_muc") == thu_muc and cu.get("chu_ky") == _chu_ky(d):
            return cu
        try:
            moi = tao_mau(d)
        except Exception as e:
            if log:
                log(f"⚠️ Mẫu nghe thử: chưa lấy được từ {ten_video(d)} ({e})"
                    + (" → giữ mẫu cũ." if cu else "."))
            return cu
        if log:
            log(f"🎧 Mẫu nghe thử: lấy {moi['giay']:.0f} s đầu video {moi['video']}"
                + (f" (thay mẫu {cu.get('video')})" if cu else "") + f" → {MAU_DIR / MAU_WAV}")
        return moi


def che_do_giong(giong: str) -> tuple[str, str]:
    """'clone|a.wav' → ('clone', 'a.wav'); sổ của bản VieNeu cũ 'vieneu|Ngọc Huyền' →
    ('vieneu', 'Ngọc Huyền'); sổ cũ không ghi → ('', '')."""
    s = str(giong or "")
    if "|" not in s:
        return ("", "")
    mode, ten = s.split("|", 1)
    return (mode.strip(), ten.strip())


def ten_giong(giong: str) -> str:
    """Tên giọng để hiện: bỏ đuôi file của giọng clone; chưa ghi (video cũ) → ''."""
    mode, ten = che_do_giong(giong)
    return Path(ten).stem if mode == "clone" else ten


def nhan_mau(meta: dict | None) -> str:
    """Một dòng ngắn cho giao diện: 'Mẫu: video abc_x0.7 · 31 s · giọng Ngọc Huyền'."""
    if not meta:
        return ""
    s = f"Mẫu: video {meta.get('video') or '?'} · {float(meta.get('giay') or 0):.0f} s"
    ten = ten_giong(meta.get("giong"))
    return s + (f" · giọng {ten}" if ten else "")


# ── ÁP CÀI ĐẶT ──────────────────────────────────────────────────────────────────
def mo_ta(pitch: float, fx: dict, am_luong: float, chuan_am: bool) -> str:
    p = []
    if abs(pitch) > 1e-9:
        p.append(f"tông {pitch:+.1f}")
    if hu.fx_active(**fx):
        p.append(hu.fx_describe(**fx))
    if chuan_am:
        p.append("chuẩn âm")
    if abs(am_luong) > 1e-9:
        p.append(f"âm lượng {am_luong:+.1f} dB")
    return ", ".join(p) or "giọng gốc, chưa chỉnh gì"


def _neo_moc(wav: Path, muc_rms: float, gui) -> None:
    """Bước 'đặt cả bài về mốc SPEECH_RMS_DBFS' của _balance_chunk_levels(moc=True) — bài
    thật làm trong mix_audio khi bật chuẩn âm; ở đây làm trên mẫu đã ghép (một mức gain)."""
    if muc_rms <= 1e-6:
        return
    x, sr = sf.read(str(wav), dtype="float32", always_2d=False)
    g = 10 ** (gui.SPEECH_RMS_DBFS / 20) / muc_rms
    dinh = float(np.max(np.abs(x))) if x.size else 0.0
    if dinh * g > 0.97:
        g = 0.97 / dinh
    sf.write(str(wav), (x * g).astype("float32"), sr, subtype="PCM_16")


def la_ban_nghe(ten: str) -> bool:
    """Tên file hợp lệ của một bản đã áp cài đặt (route /nghe/caidat chỉ trả đúng dạng này)."""
    return bool(_XT_RE.match(str(ten or "")))


def _xoa_ban_nghe(giu: Path | None = None, so_giu: int = 0) -> None:
    """Dọn các bản xt_: giữ `giu` + `so_giu` bản mới nhất, xoá phần còn lại và file tạm bỏ
    dở quá 1 giờ. File đang phát (Windows khoá) thì thôi, lượt sau dọn."""
    def luc_sua(f):
        try:
            return f.stat().st_mtime
        except OSError:
            return 0.0

    try:
        tep = [f for f in MAU_DIR.iterdir() if f.is_file()]
    except OSError:
        return
    ban = sorted((f for f in tep if _XT_RE.match(f.name)), key=luc_sua, reverse=True)
    bo = [f for f in ban if f != giu][max(0, so_giu - (1 if giu else 0)):]
    bo += [f for f in tep if ".tmp" in f.name and time.time() - luc_sua(f) > 3600]
    for f in bo:
        try:
            f.unlink()
        except OSError:
            pass


def nghe_thu(pitch=0.0, fx=None, am_luong=0.0, chuan_am=False, log=None) -> dict:
    """Áp bộ cài đặt lên mẫu gốc → file wav để phát.
    Trả {"file": Path, "mau": thông tin mẫu, "mo_ta": str, "moi": vừa dựng hay lấy bản đã có}.
    Chưa có mẫu và chưa video nào có giọng → ChuaCoMau."""
    gui = _gui()
    meta = cap_nhat(log)
    if not meta:
        raise ChuaCoMau("Chưa có mẫu nghe thử: output/ chưa có video nào đã tạo giọng (bước ③). "
                        "Chạy bước ③ một video rồi bấm lại.")
    pitch = hu.parse_pitch(pitch, 0.0)
    fx = hu.fx_from(fx)
    am_luong = hu.parse_amluong(am_luong)
    chuan_am = bool(chuan_am)
    khoa = hashlib.sha1(json.dumps([meta.get("ma"), pitch, fx, am_luong, chuan_am],
                                   sort_keys=True).encode("utf-8")).hexdigest()[:12]
    out = MAU_DIR / f"xt_{khoa}.wav"
    moi = not (out.exists() and out.stat().st_size > 4096)
    if moi:
        tam = MAU_DIR / f"xt_{khoa}.{os.getpid()}_{threading.get_ident()}.tmp.wav"
        try:
            shutil.copyfile(MAU_DIR / MAU_WAV, tam)
            if chuan_am:
                _neo_moc(tam, float(meta.get("muc_rms") or 0.0), gui)
            # Đúng hàm bài thật dùng cuối bước ③: tông + bộ lọc → [chuẩn âm] → âm lượng.
            _ts().hau_ky_audio(tam, pitch=pitch, fx=fx, chuan_am=chuan_am, am_luong=am_luong,
                               log=lambda s: None)
            os.replace(tam, out)
        finally:
            tam.unlink(missing_ok=True)
    else:
        try:
            os.utime(out)                               # vừa nghe lại → xếp mới nhất, khỏi bị dọn
        except OSError:
            pass
    _xoa_ban_nghe(giu=out, so_giu=XT_GIU)
    return dict(file=out, mau=meta, mo_ta=mo_ta(pitch, fx, am_luong, chuan_am), moi=moi)


# ── CHẠY LẺ ─────────────────────────────────────────────────────────────────────
def _cli(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Mẫu nghe thử cài đặt giọng bước ③ (~30 s giọng gốc của một video).")
    ap.add_argument("--pitch", type=float, default=0.0, help="tông (bán cung)")
    ap.add_argument("--vang", nargs=2, type=int, metavar=("TRUONG_DO", "CUONG_DO"), default=(0, 0))
    ap.add_argument("--thieunien", type=int, default=0)
    ap.add_argument("--sang", type=int, default=0)
    ap.add_argument("--amluong", type=float, default=0.0, help="âm lượng cơ bản (dB)")
    ap.add_argument("--chuanam", action="store_true", help="áp cả bước chuẩn âm")
    a = ap.parse_args(argv)
    try:
        kq = nghe_thu(pitch=a.pitch, am_luong=a.amluong, chuan_am=a.chuanam,
                      fx=dict(vang_truong_do=a.vang[0], vang_cuong_do=a.vang[1],
                              thieu_nien=a.thieunien, sang_giong=a.sang), log=print)
    except ChuaCoMau as e:
        print(e)
        return 1
    print(json.dumps({"file": str(kq["file"]), "mau": nhan_mau(kq["mau"]), "mo_ta": kq["mo_ta"],
                      "van_ban": kq["mau"].get("van_ban", "")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
