# -*- coding: utf-8 -*-
"""
taogiong_nghethu.py — 🎧 NGHE THỬ cài đặt giọng (tông / bộ lọc / chuẩn âm / âm lượng)
trên ~30 giây GIỌNG THẬT của một tập, không phải chạy lại TTS.

Ý của user (06/11/2026): chỉnh xong các ô giọng thì nghe được ngay; mẫu để nghe là 30 s
của một kịch bản đang có trong kịch_bản/, lưu thành FILE RIÊNG (xoá kịch bản đi mẫu vẫn
còn); hôm sau tạo đợt kịch bản mới thì lấy tập ĐẦU TIÊN của đợt đó, thay bản cũ.

MẪU GỐC lấy ở đâu
    <tập>/output_chunks/0000.wav, 0001.wav… là từng câu model sinh ra, CHƯA qua tông /
    bộ lọc / chuẩn âm / âm lượng (output.wav thì đã qua — áp thêm lần nữa là chồng hiệu
    ứng). Ghép các câu đầu đúng như bài thật (cân mức giữa các câu → cắt mép im lặng →
    chèn nghỉ theo dấu câu) tới khi đủ MAU_GIAY rồi dừng ở CUỐI CÂU. Không cần GPU.

LƯU Ở ĐÂU (myvoice/voice/nghe_thu/, ngoài kịch_bản/ nên xoá tập không mất)
    mau_goc.wav   — đúng MỘT mẫu gốc; có mẫu mới là ghi đè bản cũ
    mau_goc.json  — mẫu lấy từ tập nào, dài bao nhiêu, đọc câu gì
    xt_<mã>.wav   — bản đã áp một bộ cài đặt (nghe lại cùng bộ số thì khỏi dựng lại);
                    chỉ giữ XT_GIU bản mới nhất, đổi mẫu gốc là xoá hết

CHỌN TẬP NÀO (chon_tap)
    Trong các tập ĐÃ CÓ GIỌNG, xếp theo lúc tạo thư mục; "đợt" = các tập tạo liền nhau,
    hai tập cách nhau từ DOT_CACH_GIO giờ là sang đợt khác. Lấy tập ĐẦU TIÊN của đợt MỚI
    NHẤT. Không tính theo ngày lịch vì user hay làm vắt qua nửa đêm. Đợt mới chưa tập nào
    có giọng → vẫn là tập đầu của đợt trước; kịch_bản/ trống → giữ nguyên mẫu đang có.

KHI NÀO THAY MẪU (cap_nhat)
    Tập được chọn khác tập của mẫu đang lưu (hoặc tập đó vừa tạo lại giọng bằng giọng /
    văn bản khác — chữ ký _signature.txt đổi). Gọi ở hai chỗ: cuối bước tạo giọng
    (amain.run_tts) để mẫu có sẵn kể cả khi chưa ai bấm nghe, và mỗi lần bấm 🎧.

ÁP CÀI ĐẶT (nghe_thu) — cùng thứ tự, cùng hàm với bài thật:
    tông + bộ lọc (một lượt ffmpeg) → âm lượng (chuẩn âm −14 LUFS gỡ hẳn 10/11/2026).
    Lệch duy nhất: 🔆 Sáng giọng ở chế độ Clone còn EQ cả GIỌNG MẪU
    lúc sinh câu, mà câu trong mẫu đã sinh sẵn ở mức sáng của tập đó → nghe thử chỉ thấy
    phần EQ áp lên audio (web báo khi hai mức lệch nhau).

Chạy lẻ:
    venv\\Scripts\\python myvoice\\scripts\\taogiong_nghethu.py            # xem / lấy mẫu
    venv\\Scripts\\python myvoice\\scripts\\taogiong_nghethu.py --pitch 1 --sang 80 --amluong 5
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

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import hieuung_giong as hu            # noqa: E402

MAU_DIR = _HERE.parent / "voice" / "nghe_thu"
MAU_WAV = "mau_goc.wav"
MAU_JSON = "mau_goc.json"
GIONG_MARK = "_giong.json"        # trong thư mục chunk: tập này sinh bằng chế độ / giọng nào

MAU_GIAY = 30.0                   # mẫu dài ít nhất ngần này (rồi dừng ở cuối câu)
MAU_GIAY_TOI_DA = 36.0            # câu cuối kéo quá mức này → cắt về MAU_GIAY, vát đuôi
MAU_GIAY_IT_NHAT = 8.0            # tập chưa đủ ngần này giây giọng gốc → chưa lấy mẫu được
VAT_GIAY = 0.30                   # vát nhỏ dần khi phải cắt giữa câu
DUOI_GIAY = 0.50                  # im lặng cuối mẫu (đuôi vang có chỗ tắt)
DOT_CACH_GIO = 6.0                # hai tập tạo cách nhau từ ngần này giờ = hai đợt kịch bản
XT_GIU = 6                        # số bản nghe thử đã áp cài đặt được giữ lại
VAN_BAN_TOI_DA = 600              # ký tự lời đọc ghi vào mau_goc.json (để xem mẫu đọc gì)

_XT_RE = re.compile(r"^xt_[0-9a-f]{12}\.wav$")
_KHOA = threading.RLock()         # một tiến trình chỉ một lượt dựng/đổi mẫu cùng lúc


class ChuaCoMau(RuntimeError):
    """Chưa có mẫu nào và kịch_bản/ cũng chưa có tập nào đã tạo giọng để lấy."""


def _gui():
    """Module amain_taogiong_gui đang nạp (kể cả khi nó chạy dưới tên __main__)."""
    g = sys.modules.get("amain_taogiong_gui")
    if g is not None:
        return g
    m = sys.modules.get("__main__")
    if m is not None and hasattr(m, "_join_with_pauses") and hasattr(m, "episode_dirs"):
        return m
    import amain_taogiong_gui as g
    return g


# ── CHỌN TẬP ────────────────────────────────────────────────────────────────────
def thu_muc_chunk(folder) -> Path:
    return _gui().chunks_dir_for(Path(folder) / "output.wav")


def _tao_luc(p: Path) -> float:
    """Lúc TẠO thư mục (Windows: st_ctime là giờ tạo; Python 3.12+ có st_birthtime)."""
    st = Path(p).stat()
    return float(getattr(st, "st_birthtime", st.st_ctime))


def _chu_ky(folder) -> str:
    try:
        return (thu_muc_chunk(folder) / "_signature.txt").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def tap_co_giong(folder) -> bool:
    """Tập đã tạo giọng xong: có output.wav và còn câu gốc đầu tiên trong output_chunks/."""
    folder = Path(folder)
    try:
        return ((folder / "output.wav").stat().st_size > 4096
                and (thu_muc_chunk(folder) / "0000.wav").stat().st_size > 4096)
    except OSError:
        return False


def chon_tap():
    """Thư mục tập để lấy mẫu: tập ĐẦU TIÊN của đợt mới nhất trong các tập đã có giọng
    (xem đầu file). Không tập nào có giọng → None."""
    ds = []
    for p in _gui().episode_dirs():
        if not tap_co_giong(p):
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


def ghi_giong(tmp_dir, mode, voice_param) -> None:
    """Ghi chế độ + tên giọng đã sinh các câu vào thư mục chunk (amain.run_tts gọi lúc
    tạo giọng) — để mẫu nghe thử nói được nó đang đọc bằng giọng nào."""
    try:
        ten = Path(str(voice_param)).name if mode == "clone" else str(voice_param or "")
        (Path(tmp_dir) / GIONG_MARK).write_text(
            json.dumps({"che_do": str(mode or ""), "giong": ten}, ensure_ascii=False),
            encoding="utf-8")
    except Exception:
        pass


def _doc_json(path) -> dict:
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _van_ban_doan(folder, so_wav: int):
    """Lời của từng câu trong output_chunks (để chèn nghỉ đúng loại dấu): chia lại
    input.docx bằng đúng ba bước của lúc tạo giọng. Số câu chia ra KHÁC số file wav
    (văn bản / ô cắt câu đã đổi sau khi tạo giọng) → None, bên gọi nghỉ đều kiểu hết câu."""
    try:
        import dich_input_docx as inputdocx
        import taogiong_chia_cau as chia
        inp = inputdocx.input_for(folder)
        if not Path(inp).exists():
            return None
        ds = chia.split_for_tts(inputdocx.read_input_text(inp), chia.chunk_size_from_options())
        return ds if len(ds) == so_wav else None
    except Exception:
        return None


def tao_mau(folder) -> dict:
    """Dựng mẫu gốc từ các câu đầu của `folder` rồi THAY mẫu đang lưu (bản cũ bị ghi đè,
    các bản xt_ dựng từ nó bị xoá). Trả thông tin mẫu mới; không đủ giọng gốc → ChuaCoMau."""
    gui = _gui()
    folder = Path(folder)
    cdir = thu_muc_chunk(folder)
    so_wav = sum(1 for _ in cdir.glob("[0-9][0-9][0-9][0-9].wav"))
    van_ban = _van_ban_doan(folder, so_wav)

    parts, cau, sr, tong = [], [], None, 0.0
    while tong < MAU_GIAY:
        f = cdir / f"{len(parts):04d}.wav"
        try:
            if f.stat().st_size <= 4096:
                break
            x, r = sf.read(str(f), dtype="float32", always_2d=False)
        except Exception:
            break                                   # hết câu / câu đang ghi dở
        if x.ndim > 1:
            x = x.mean(axis=1)
        if sr is None:
            sr = int(r)
        elif int(r) != sr:
            break
        chu = van_ban[len(parts)] if van_ban else "."
        parts.append(x)
        cau.append(chu)
        tong += len(gui._trim_edges(x, sr)) / sr + gui._pause_after(chu)
    if not parts or tong < MAU_GIAY_IT_NHAT:
        raise ChuaCoMau(f"{folder.name}: chưa đủ giọng gốc trong {cdir.name} để lấy mẫu")

    # Mốc mức tiếng nói (trung vị) TRƯỚC khi cân — chỉ ghi vào meta để tham khảo.
    muc = [m for m in (gui._speech_rms(p, sr) for p in parts) if m > 1e-4]
    muc_rms = float(np.median(muc)) if muc else 0.0
    parts = gui._balance_chunk_levels(parts, sr)
    am = gui._join_with_pauses(parts, cau, sr)
    cat = len(am) / sr > MAU_GIAY_TOI_DA
    if cat:                                         # câu cuối dài quá → cắt, vát cho khỏi cụt
        am = am[: int(MAU_GIAY * sr)].copy()
        n = min(int(VAT_GIAY * sr), len(am))
        am[-n:] *= np.linspace(1.0, 0.0, n, dtype="float32")
    am = np.concatenate([am, np.zeros(int(DUOI_GIAY * sr), dtype="float32")])

    loi = " ".join(str(c).strip() for c in cau) if van_ban else ""
    chu_ky = _chu_ky(folder)
    meta = dict(
        tap=gui.episode_of(folder.name) or "", thu_muc=folder.name, chu_ky=chu_ky,
        ma=hashlib.sha1(f"{folder.name}|{chu_ky}|{time.time()}".encode("utf-8")).hexdigest()[:10],
        tap_tao_luc=_tao_luc(folder), lay_luc=time.time(),
        so_cau=len(parts), giay=round(len(am) / sr, 2), sr=sr, muc_rms=muc_rms,
        cat_giua_cau=bool(cat), nghi_theo_dau=bool(van_ban),
        # Mức 🔆 Sáng giọng lúc sinh các câu (chế độ Clone EQ cả giọng mẫu) + giọng đã đọc.
        sang_goc=hu.fx_from(_doc_json(cdir / gui.FX_MARK))["sang_giong"],
        giong=_doc_json(cdir / GIONG_MARK),
        van_ban=loi[:VAN_BAN_TOI_DA] + ("…" if len(loi) > VAN_BAN_TOI_DA else ""),
    )

    with _KHOA:
        MAU_DIR.mkdir(parents=True, exist_ok=True)
        tam = MAU_DIR / f"mau_goc.{os.getpid()}.tmp.wav"
        try:
            sf.write(str(tam), am, sr, subtype="PCM_16")
            _xoa_ban_nghe()                         # các bản dựng từ mẫu cũ
            os.replace(tam, MAU_DIR / MAU_WAV)      # thay = bản cũ mất, chỉ còn một mẫu
        finally:
            tam.unlink(missing_ok=True)
        (MAU_DIR / MAU_JSON).write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                                        encoding="utf-8")
    return meta


def cap_nhat(log=None):
    """Bảo đảm mẫu đang lưu là của tập chon_tap() chỉ ra; lệch thì dựng lại + thay.
    Trả thông tin mẫu đang dùng. Không tập nào có giọng (kịch_bản trống / đợt mới chưa
    tạo giọng) → giữ mẫu cũ; chưa từng có mẫu → None."""
    with _KHOA:
        cu = doc_mau()
        try:
            tap = chon_tap()
        except Exception:
            tap = None
        if tap is None:
            return cu
        if cu and cu.get("thu_muc") == tap.name and cu.get("chu_ky") == _chu_ky(tap):
            return cu
        try:
            moi = tao_mau(tap)
        except Exception as e:
            if log:
                log(f"⚠️ Mẫu nghe thử: chưa lấy được từ {tap.name} ({e})"
                    + (" → giữ mẫu cũ." if cu else "."))
            return cu
        if log:
            log(f"🎧 Mẫu nghe thử: lấy {moi['giay']:.0f} s đầu tập {moi['tap']}"
                + (f" (thay mẫu tập {cu.get('tap')})" if cu else "") + f" → {MAU_DIR / MAU_WAV}")
        return moi


def ten_giong(giong: dict | None) -> str:
    """Tên giọng để hiện: bỏ đuôi file của giọng Clone; chưa ghi (tập cũ) → ''."""
    ten = str((giong or {}).get("giong") or "").strip()
    if (giong or {}).get("che_do") == "clone":
        ten = Path(ten).stem
    return ten


def nhan_mau(meta: dict | None) -> str:
    """Một dòng ngắn cho giao diện: 'Mẫu: tập 164 · 31 s · giọng Ngọc Huyền'."""
    if not meta:
        return ""
    s = f"Mẫu: tập {meta.get('tap') or '?'} · {float(meta.get('giay') or 0):.0f} s"
    ten = ten_giong(meta.get("giong"))
    return s + (f" · giọng {ten}" if ten else "")


# ── ÁP CÀI ĐẶT ──────────────────────────────────────────────────────────────────
def mo_ta(pitch: float, fx: dict, am_luong: float) -> str:
    p = []
    if abs(pitch) > 1e-9:
        p.append(f"tông {pitch:+.1f}")
    if hu.fx_active(**fx):
        p.append(hu.fx_describe(**fx))
    if abs(am_luong) > 1e-9:
        p.append(f"âm lượng {am_luong:+.1f} dB")
    return ", ".join(p) or "giọng gốc, chưa chỉnh gì"


def _xoa_ban_nghe(giu: Path | None = None, so_giu: int = 0) -> None:
    """Dọn các bản xt_: giữ `giu` + `so_giu` bản mới nhất, xoá phần còn lại và file tạm
    bỏ dở quá 1 giờ. File đang phát (Windows khoá) thì thôi, lượt sau dọn."""
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


def nghe_thu(pitch=0.0, fx=None, am_luong=0.0, log=None) -> dict:
    """Áp bộ cài đặt lên mẫu gốc → file wav để phát.
    Trả {"file": Path, "mau": thông tin mẫu, "mo_ta": str, "moi": vừa dựng hay lấy bản đã có}.
    Chưa có mẫu và chưa tập nào có giọng → ChuaCoMau."""
    gui = _gui()
    meta = cap_nhat(log)
    if not meta:
        raise ChuaCoMau("Chưa có mẫu nghe thử: kịch_bản chưa có tập nào đã tạo giọng. "
                        "Tạo giọng một tập rồi bấm lại.")
    pitch = hu.parse_pitch(pitch, 0.0)
    fx = hu.fx_from(fx)
    am_luong = hu.parse_amluong(am_luong)
    khoa = hashlib.sha1(json.dumps([meta.get("ma"), pitch, fx, am_luong],
                                   sort_keys=True).encode("utf-8")).hexdigest()[:12]
    out = MAU_DIR / f"xt_{khoa}.wav"
    moi = not (out.exists() and out.stat().st_size > 4096)
    if moi:
        tam = MAU_DIR / f"xt_{khoa}.{os.getpid()}_{threading.get_ident()}.tmp.wav"
        try:
            shutil.copyfile(MAU_DIR / MAU_WAV, tam)
            gui._apply_voice_fx_file(tam, pitch, fx)
            hu.apply_amluong_file(tam, am_luong)
            os.replace(tam, out)
        finally:
            tam.unlink(missing_ok=True)
    else:
        try:
            os.utime(out)                           # vừa nghe lại → xếp mới nhất, khỏi bị dọn
        except OSError:
            pass
    _xoa_ban_nghe(giu=out, so_giu=XT_GIU)
    return dict(file=out, mau=meta, mo_ta=mo_ta(pitch, fx, am_luong), moi=moi)


# ── CHẠY LẺ ─────────────────────────────────────────────────────────────────────
def _cli(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Mẫu nghe thử cài đặt giọng (~30 s giọng gốc của một tập).")
    ap.add_argument("--pitch", type=float, default=0.0, help="tông (bán cung)")
    ap.add_argument("--vang", nargs=2, type=int, metavar=("TRUONG_DO", "CUONG_DO"), default=(0, 0))
    ap.add_argument("--thieunien", type=int, default=0)
    ap.add_argument("--sang", type=int, default=0)
    ap.add_argument("--amluong", type=float, default=0.0, help="âm lượng cơ bản (dB)")
    a = ap.parse_args(argv)
    try:
        kq = nghe_thu(pitch=a.pitch, am_luong=a.amluong,
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
