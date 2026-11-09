# -*- coding: utf-8 -*-
"""
hieuung_giong.py — BỘ LỌC GIỌNG NÓI kiểu CapCut, chạy hoàn toàn bằng ffmpeg sẵn có.

Ba bộ lọc (tên + thang 0–100 đặt theo đúng CapCut để chỉnh cho quen tay):

  🔔 TIẾNG VANG  — "Trường độ" (0–100: phòng nhỏ → hội trường) và "Cường độ"
     (0–100: mức tiếng vang trộn vào; 0 = tắt). Làm bằng filter `afir` của
     ffmpeg (tích chập với ĐÁP ỨNG XUNG). Đáp ứng xung không lấy từ file mẫu
     nào mà TỰ SINH bằng numpy: tiền trễ (pre-delay) + vài phản xạ sớm + đuôi
     nhiễu tắt dần theo hàm mũ, dải cao tắt nhanh hơn dải trầm (như phòng thật,
     tường hút âm cao). "Trường độ" quyết định RT60 (thời gian tắt 60 dB) và
     tiền trễ; "Cường độ" quyết định tỉ lệ wet/dry. Không dùng `aecho` vì nó
     chỉ cho vài tiếng dội rời rạc, không ra tiếng vang mịn như CapCut.

  🧒 GIỌNG THIẾU NIÊN — "Cường độ" (0–100). Giọng trẻ hơn = cao độ (f0) nhỉnh
     lên VÀ formant (cộng hưởng khoang miệng — ống thanh quản ngắn hơn) dời lên
     theo tỉ lệ KHÁC cao độ. Theo Praat "Change gender": nam → nữ dời formant
     ×1.1; ở đây 100% = formant ×TN_FORMANT_MAX, cao độ +TN_PITCH_MAX_ST bán
     cung, nhỏ hơn thì nội suy tuyến tính. ffmpeg rubberband không chỉnh
     formant riêng được (chỉ "preserved"/"shifted"), nên dời formant bằng mẹo
     3 bước trong MỘT chuỗi filter:
        rubberband pitch = p/r (giữ formant)  → cao độ ×p/r, formant giữ, tốc độ giữ
        asetrate sr·r + aresample sr          → cao độ ×r, formant ×r, nhanh ×r
        atempo tốc_độ/r                       → trả tốc độ về (× tốc độ nghe thử)
     ⇒ cao độ ×p, formant ×r, thời lượng giữ — chỉ MỘT lần rubberband nên không
     cộng dồn méo. Build ffmpeg không có rubberband → asetrate kéo cả cao độ lẫn
     formant cùng tỉ lệ (kiểu "chipmunk" nhẹ), chấp nhận được.

  🔆 SÁNG GIỌNG — "Cường độ" (0–100), thêm 23/10/2026 để trị giọng clone nghe
     "ồm ồm, không thanh". Đo giọng mẫu ngọc huyền 01: ~80 % năng lượng dồn vào
     150–600 Hz, dải 2,5–5 kHz (cảm giác "thanh, trong") chỉ ~1 %; bản clone
     chép y nguyên (trọng tâm phổ ~500 Hz) nên đổi tông/tốc độ không sửa được.
     Bộ lọc là chuỗi EQ ffmpeg, mức 100 = highpass 110 Hz, cắt 230 Hz −6 dB,
     cắt 480 Hz −3 dB, nâng 3,2 kHz +6 dB, highshelf 6 kHz +6 dB, từ mức 50
     thêm aexciter sinh họa âm 7–11,5 kHz bù phần model chỉ ra 24 kHz; mức
     nhỏ hơn nội suy tuyến tính (đo: mức ~65 đưa trọng tâm phổ 507 → 863 Hz,
     mức 100 → 1172 Hz). Áp ở HAI chỗ: lên output.wav (chuỗi ở đây, sau có
     alimiter ghìm đỉnh) VÀ lên GIỌNG MẪU trong bộ nhớ lúc dựng prompt clone
     (amain._voice_prompt, không exciter) — model nghe mẫu sáng thì phát âm
     sáng từ gốc, EQ output chỉ đánh bóng. File giọng mẫu không bị sửa. Mặc
     định 80 ở cả hai bảng (user chốt 23/10/2026 sau khi nghe demo): myvoice
     khoá sang_giong (taogiong_options.json), myvideo khoá sanggiong
     (web/web_settings.json → taogiong_srt.py --sang; bên đó EQ mẫu lúc dựng
     prompt + EQ audio tổng _vi_audio.wav sau khi trộn).

Các hàm đổi tông / tốc độ (has_rubberband, pitch_factor, atempo_chain,
build_audio_filter) chuyển về đây làm "nhà" chung; amain_taogiong_gui import
lại để bài thật, app Thử giọng và web cùng một đường — nghe thử ra sao thì bài
thật ra vậy.

Dùng lẻ (thử nhanh một file):
    venv\\Scripts\\python myvoice\\scripts\\hieuung_giong.py in.wav --vang 80 76 --thieunien 100 --sang 60
    → in_fx.wav cạnh file gốc (hoặc --out). Thêm --pitch 2 --speed 1.1 nếu muốn.

Nguồn tham khảo: ffmpeg afir/rubberband/asetrate/atempo docs; Praat manual
"Sound: Change gender..." (formant shift ratio, pitch median); Amphion
processors/data_augment.py (formant shift bằng parselmouth — không dùng để
khỏi cài thêm, nhưng tỉ lệ formant 1.0–1.4 lấy làm mốc).
"""

import os
import re
import sys
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_HERE = Path(__file__).resolve().parent
IR_CACHE_DIR = _HERE / "hieuung_cache"      # đáp ứng xung đã sinh (theo sr + trường độ)

# ── THANG CHỈNH TAY ─────────────────────────────────────────────────────────────
FX_MIN, FX_MAX = 0, 100                      # thang 0–100 như CapCut

# Tiếng vang: trường độ 0 → 100 ứng RT60 (giây) nội suy theo hàm mũ — tai nghe
# độ dài vang theo tỉ lệ, không theo hiệu. 80 ≈ 1,8 s (hội trường vừa).
VANG_RT60_MIN, VANG_RT60_MAX = 0.25, 3.0
VANG_PREDELAY_MIN_MS, VANG_PREDELAY_MAX_MS = 8.0, 40.0   # tiền trễ: phòng to → trễ lâu
VANG_WET_MAX = 0.8        # cường độ 100 → wet 0,8 (dry 1,0; đáp ứng xung chuẩn năng lượng 1)
VANG_DRY_MIN = 0.75       # cường độ 100 → dry hạ còn 0,75 để tổng không bị to vọt
# Cộng vang vào giọng đã chuẩn độ to thì đỉnh vượt 1,0 (đo 20/10/2026: 1,22 ở mức
# 80/76) → ghi 16-bit là cắt méo. alimiter chỉ ghìm các đỉnh vượt ngưỡng này,
# level=false để không tự kéo to lên, latency=true để bù trễ lookahead (không lệch
# thời gian so với bản không vang).
VANG_LIMIT = 0.97
# Đuôi vang theo dải: (tần số cắt Hz, hệ số nhân RT60). Dải cao tắt nhanh hơn.
VANG_BANDS = ((400.0, 1.00), (2000.0, 0.90), (6000.0, 0.70), (None, 0.45))
# Phản xạ sớm (ms, biên độ) trước khi đuôi khuếch tán bắt đầu — cho cảm giác "phòng".
VANG_EARLY = ((5.0, 0.55), (9.0, 0.40), (14.0, 0.33), (21.0, 0.27), (29.0, 0.20), (38.0, 0.14))
VANG_EARLY_GAIN = 0.5     # mức cụm phản xạ sớm so với đuôi

# Thiếu niên: 100% = formant ×1,18 và cao độ +4 bán cung (Praat gợi ý nam→nữ
# formant ×1,1; giọng kể chuyện nữ muốn "nhí" hơn cần nhỉnh hơn chút).
TN_FORMANT_MAX = 1.18
TN_PITCH_MAX_ST = 4.0

# Sáng giọng: mức 100 ứng với bộ EQ dưới (dB âm = cắt, dương = nâng), mức thấp
# hơn nhân tuyến tính theo x = mức/100. Đo 23/10/2026 trên bản clone ngọc huyền 01:
# trọng tâm phổ 507 Hz → 863 Hz (mức ~65) → 1172 Hz (mức 100).
SANG_HP_HZ = (80.0, 110.0)          # highpass: mức 0+ → 80 Hz, mức 100 → 110 Hz
SANG_EQ = (                         # (tần số Hz, độ rộng Q, dB ở mức 100)
    (230.0, 1.2, -6.0),             # cục "ồm" 150–350 Hz
    (480.0, 1.0, -3.0),             # đục 400–600 Hz
    (3200.0, 0.9, 6.0),             # presence: rõ chữ, "thanh"
)
SANG_SHELF = (6000.0, 6.0)          # highshelf (Hz, dB ở mức 100): "air"
SANG_EXCITER_FROM = 50              # từ mức này mới thêm aexciter (họa âm dải cao)
SANG_EXCITER = dict(freq=7000.0, ceil=11500.0, drive=6.0, amount=1.0)  # amount ở mức 100
SANG_LIMIT = 0.97                   # alimiter sau EQ: nâng +6 dB có thể đội đỉnh quá 1,0

# Đổi tông: bán cung; ±12 = một quãng tám (giữ nguyên giới hạn cũ của amain).
PITCH_MIN, PITCH_MAX = -6.0, 6.0
_HAS_RUBBERBAND = None


# ── ĐỌC / KẸP THAM SỐ ───────────────────────────────────────────────────────────
def parse_fx(value, default: int = 0) -> int:
    """Đọc mức 0–100 (ô nhập / JSON / slider) → int, kẹp [FX_MIN, FX_MAX]."""
    try:
        v = int(round(float(str(value).replace(",", ".").strip())))
    except (TypeError, ValueError):
        return default
    return max(FX_MIN, min(v, FX_MAX))


def parse_pitch(value, default: float = 0.0) -> float:
    """Đọc mức tông (ô nhập / JSON) → float, làm tròn 0,5, kẹp [PITCH_MIN, PITCH_MAX]."""
    try:
        v = float(str(value).replace(",", ".").strip())
    except (TypeError, ValueError):
        return default
    v = round(v * 2) / 2
    return max(PITCH_MIN, min(v, PITCH_MAX))


def fx_from(opts: dict | None) -> dict:
    """Rút 4 khoá bộ lọc từ dict tuỳ chọn (taogiong_options.json / form) →
    {"vang_truong_do", "vang_cuong_do", "thieu_nien", "sang_giong"} đã kẹp 0–100."""
    opts = opts or {}
    return dict(
        vang_truong_do=parse_fx(opts.get("vang_truong_do"), 0),
        vang_cuong_do=parse_fx(opts.get("vang_cuong_do"), 0),
        thieu_nien=parse_fx(opts.get("thieu_nien"), 0),
        sang_giong=parse_fx(opts.get("sang_giong"), 0),
    )


def fx_active(vang_cuong_do: int = 0, thieu_nien: int = 0, sang_giong: int = 0,
              **_ignored) -> bool:
    """Có bộ lọc nào đang bật không (tiếng vang bật khi CƯỜNG ĐỘ > 0)."""
    return parse_fx(vang_cuong_do) > 0 or parse_fx(thieu_nien) > 0 or parse_fx(sang_giong) > 0


def fx_tag(vang_truong_do: int = 0, vang_cuong_do: int = 0, thieu_nien: int = 0,
           sang_giong: int = 0) -> str:
    """Đuôi tên file cache: '' khi tắt hết, còn thì '_vang80-76_tn100_sang60'."""
    tag = ""
    if parse_fx(vang_cuong_do) > 0:
        tag += f"_vang{parse_fx(vang_truong_do)}-{parse_fx(vang_cuong_do)}"
    if parse_fx(thieu_nien) > 0:
        tag += f"_tn{parse_fx(thieu_nien)}"
    if parse_fx(sang_giong) > 0:
        tag += f"_sang{parse_fx(sang_giong)}"
    return tag


def fx_describe(vang_truong_do: int = 0, vang_cuong_do: int = 0, thieu_nien: int = 0,
                sang_giong: int = 0) -> str:
    """Mô tả ngắn cho nhật ký: 'tiếng vang 80/76, thiếu niên 100, sáng giọng 60'
    hoặc 'không'."""
    parts = []
    if parse_fx(vang_cuong_do) > 0:
        parts.append(f"tiếng vang trường độ {parse_fx(vang_truong_do)} / cường độ {parse_fx(vang_cuong_do)}")
    if parse_fx(thieu_nien) > 0:
        parts.append(f"thiếu niên {parse_fx(thieu_nien)}")
    if parse_fx(sang_giong) > 0:
        parts.append(f"sáng giọng {parse_fx(sang_giong)}")
    return ", ".join(parts) or "không"


# ── ĐỔI TÔNG / TỐC ĐỘ (chuyển từ amain_taogiong_gui sang, giữ nguyên hành vi) ──
def has_rubberband() -> bool:
    """ffmpeg đang dùng có filter rubberband không (dò 1 lần, nhớ kết quả)."""
    global _HAS_RUBBERBAND
    if _HAS_RUBBERBAND is None:
        try:
            r = subprocess.run(
                [shutil.which("ffmpeg") or "ffmpeg", "-hide_banner", "-filters"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                creationflags=CREATE_NO_WINDOW)
            _HAS_RUBBERBAND = re.search(r"^\s*\S+\s+rubberband\s", r.stdout or "",
                                        re.M) is not None
        except Exception:
            _HAS_RUBBERBAND = False
    return _HAS_RUBBERBAND


def pitch_factor(semitones: float) -> float:
    """Hệ số nhân tần số ứng với số bán cung: +12 → ×2, −12 → ×0.5."""
    return 2.0 ** (semitones / 12.0)


def atempo_chain(ratio: float) -> list[str]:
    """Tách tỉ lệ tốc độ thành chuỗi atempo, mỗi mắt trong [0.5, 2.0] — ffmpeg mới
    cho tới 100 nhưng bản cũ chỉ tới 2.0, chia nhỏ thì chạy được ở cả hai."""
    parts = []
    while ratio > 2.0:
        parts.append("atempo=2.0")
        ratio /= 2.0
    while ratio < 0.5:
        parts.append("atempo=0.5")
        ratio /= 0.5
    parts.append(f"atempo={ratio:.3f}")
    return parts


def _rubberband(pitch: float) -> str:
    """Filter rubberband đổi cao độ ×pitch, giữ formant (ra "người đó" nói cao/trầm
    hơn, không chipmunk); transients=smooth + detector=soft chỉnh cho giọng nói —
    đo 20/10/2026 trên app Thử giọng: bám tông đúng hơn, ít rung giật hơn mặc định."""
    return (f"rubberband=pitch={pitch:.5f}:formant=preserved"
            ":transients=smooth:detector=soft")


def teen_params(thieu_nien: int) -> tuple[float, float]:
    """Mức thiếu niên 0–100 → (tỉ lệ formant r, số bán cung cộng thêm)."""
    x = parse_fx(thieu_nien) / 100.0
    return 1.0 + (TN_FORMANT_MAX - 1.0) * x, TN_PITCH_MAX_ST * x


def sang_params(sang_giong: int) -> dict:
    """Mức sáng giọng 0–100 → tham số EQ thực: highpass (Hz), eq [(Hz, Q, dB)],
    shelf (Hz, dB), exciter (amount; 0 khi dưới SANG_EXCITER_FROM)."""
    lv = parse_fx(sang_giong)
    x = lv / 100.0
    ex = max(0.0, (lv - SANG_EXCITER_FROM) / float(100 - SANG_EXCITER_FROM))
    return dict(
        x=x,
        highpass=SANG_HP_HZ[0] + (SANG_HP_HZ[1] - SANG_HP_HZ[0]) * x,
        eq=[(f, q, g * x) for f, q, g in SANG_EQ],
        shelf=(SANG_SHELF[0], SANG_SHELF[1] * x),
        exciter=SANG_EXCITER["amount"] * ex,
    )


def sang_chain(sang_giong: int, sample_rate: int, exciter: bool = True) -> list[str]:
    """Các mắt filter ffmpeg của bộ lọc 🔆 Sáng giọng; [] khi mức 0.
    exciter=False: bỏ aexciter (EQ giọng mẫu — họa âm giả vào mẫu thì model học
    cả tiếng xì). aexciter đòi ceil ≥ 9999 Hz và phải dưới Nyquist → tự bỏ ở
    sample rate thấp (≤ 2×ceil)."""
    if parse_fx(sang_giong) <= 0:
        return []
    p = sang_params(sang_giong)
    chain = [f"highpass=f={p['highpass']:.0f}"]
    chain += [f"equalizer=f={f:.0f}:t=q:w={q:g}:g={g:.2f}" for f, q, g in p["eq"]]
    chain.append(f"highshelf=f={p['shelf'][0]:.0f}:g={p['shelf'][1]:.2f}")
    if exciter and p["exciter"] > 1e-6 and sample_rate / 2.0 > SANG_EXCITER["ceil"]:
        e = SANG_EXCITER
        chain.append(f"aexciter=amount={p['exciter']:.2f}:drive={e['drive']:g}:blend=0"
                     f":freq={e['freq']:.0f}:ceil={e['ceil']:.0f}")
    return chain


def build_audio_filter(speed: float, semitones: float, sample_rate: int,
                       thieu_nien: int = 0, sang_giong: int = 0,
                       sang_exciter: bool = True) -> str:
    """Chuỗi -filter:a cho ffmpeg: đổi formant (thiếu niên) + đổi tông trước, đổi
    tốc độ sau, rồi EQ sáng giọng (đặt SAU asetrate để các dải EQ nằm đúng tần số
    tuyệt đối) + alimiter ghìm đỉnh. Rỗng khi tốc độ 1.0, tông 0 và không bộ lọc
    (không cần render). thieu_nien=0, sang_giong=0 → y hệt hàm cũ bên amain
    (cache tốc độ/tông cũ vẫn đúng). sang_exciter=False: xem sang_chain."""
    r_formant, tn_st = teen_params(thieu_nien)
    semitones = semitones + tn_st
    chain = []
    has_pitch = abs(semitones) > 1e-9
    has_speed = abs(speed - 1.0) > 1e-6
    has_formant = r_formant > 1.0 + 1e-6
    p = pitch_factor(semitones) if has_pitch else 1.0

    if has_formant and has_rubberband():
        # asetrate chỉ nhận số nguyên → tính lại r thực để atempo bù đúng thời lượng.
        new_rate = int(round(sample_rate * r_formant))
        r = new_rate / sample_rate
        chain.append(_rubberband(p / r))                         # cao độ ×p/r, formant giữ
        chain += [f"asetrate={new_rate}", f"aresample={sample_rate}"]  # ×r cả cao độ + formant
        chain += atempo_chain(speed / r)                         # trả tốc độ về (× speed)
    elif has_formant:
        # Không rubberband: asetrate kéo cao độ + formant cùng tỉ lệ (chipmunk nhẹ).
        new_rate = int(round(sample_rate * max(p, r_formant)))
        k = new_rate / sample_rate
        chain += [f"asetrate={new_rate}", f"aresample={sample_rate}"]
        chain += atempo_chain(speed / k)
    elif has_pitch:
        if has_rubberband():
            chain.append(_rubberband(p))
            if has_speed:
                chain += atempo_chain(speed)
        else:
            # asetrate kéo cả cao độ lẫn tốc độ lên p lần → atempo chia lại p.
            chain += [f"asetrate={round(sample_rate * p)}", f"aresample={sample_rate}"]
            chain += atempo_chain(speed / p)
    elif has_speed:
        chain += atempo_chain(speed)
    sang = sang_chain(sang_giong, sample_rate, sang_exciter)
    if sang:
        chain += sang
        chain.append(f"alimiter=limit={SANG_LIMIT}:attack=5:release=60:level=false:latency=true")
    return ",".join(chain)


# ── TIẾNG VANG: sinh đáp ứng xung ───────────────────────────────────────────────
def vang_params(vang_truong_do: int, vang_cuong_do: int) -> dict:
    """Trường độ/cường độ 0–100 → rt60 (s), predelay (ms), wet, dry."""
    d = parse_fx(vang_truong_do) / 100.0
    c = parse_fx(vang_cuong_do) / 100.0
    rt60 = VANG_RT60_MIN * (VANG_RT60_MAX / VANG_RT60_MIN) ** d
    predelay = VANG_PREDELAY_MIN_MS + (VANG_PREDELAY_MAX_MS - VANG_PREDELAY_MIN_MS) * d
    return dict(rt60=rt60, predelay_ms=predelay,
                wet=VANG_WET_MAX * c, dry=1.0 - (1.0 - VANG_DRY_MIN) * c)


def build_ir(sample_rate: int, vang_truong_do: int, vang_cuong_do: int = 100,
             seed: int = 20261020) -> np.ndarray:
    """Đáp ứng xung tiếng vang (mono, float32) = XUNG TRỰC TIẾP (dry) + ĐUÔI VANG (wet).

    afir KHÔNG có đường trộn dry/wet riêng: "dry" của nó là gain ĐẦU VÀO, "wet"
    là gain ĐẦU RA (đo 20/10/2026: dry=0 → im lặng hoàn toàn). Nên đường trực
    tiếp phải nằm NGAY TRONG đáp ứng xung: ir[0] = dry; đuôi (chuẩn năng lượng 1
    rồi nhân wet) gồm cụm phản xạ sớm → sau tiền trễ là nhiễu Gauss chia 4 dải,
    mỗi dải tắt dần theo hàm mũ với RT60 riêng (cao tắt nhanh). Cùng một IR chứa
    cả hai đường nên afir có trễ bao nhiêu thì dry/wet vẫn khớp pha. Seed cố
    định để cùng tham số sinh ra cùng IR (cache theo tên file là đủ)."""
    from scipy.signal import butter, sosfilt

    pr = vang_params(vang_truong_do, vang_cuong_do)
    rt60, predelay = pr["rt60"], pr["predelay_ms"] / 1000.0
    sr = int(sample_rate)
    n = int(sr * (predelay + rt60 * 1.15)) + 1
    t = np.arange(n, dtype=np.float64) / sr
    rng = np.random.default_rng(seed)
    noise = rng.standard_normal(n)

    # Đuôi khuếch tán: chia dải, mỗi dải một tốc độ tắt.
    tail = np.zeros(n, dtype=np.float64)
    lo = None
    for cutoff, k in VANG_BANDS:
        if cutoff is None:
            sos = butter(4, lo, btype="highpass", fs=sr, output="sos")
        elif lo is None:
            sos = butter(4, cutoff, btype="lowpass", fs=sr, output="sos")
        else:
            sos = butter(4, [lo, cutoff], btype="bandpass", fs=sr, output="sos")
        env = np.exp(-6.9078 * t / (rt60 * k))          # -60 dB sau rt60·k giây
        tail += sosfilt(sos, noise) * env
        lo = cutoff
    # Mép vào mềm 4 ms để đuôi không "bật" lên đột ngột sau tiền trễ.
    ramp = min(int(0.004 * sr), n)
    tail[:ramp] *= np.linspace(0.0, 1.0, ramp)
    start = int(predelay * sr)
    ir = np.zeros(n, dtype=np.float64)
    ir[start:] = tail[: n - start]

    # Phản xạ sớm: vài xung thưa, giãn dần theo trường độ (phòng to → phản xạ
    # muộn hơn) nhưng tối đa ×2 để vẫn là "phản xạ sớm", không thành tiếng dội rời.
    d = parse_fx(vang_truong_do) / 100.0
    scale = 1.0 + d
    tail_rms0 = float(np.sqrt(np.mean(tail[:int(0.02 * sr)] ** 2))) or 1.0
    for ms, amp in VANG_EARLY:
        i = int(ms / 1000.0 * scale * sr)
        if i < n:
            # Xung mạnh nhất ≈ 1,1× mức đuôi lúc bắt đầu: nghe rõ "phòng" mà không át đuôi.
            ir[i] += amp * VANG_EARLY_GAIN * 4.0 * tail_rms0 * rng.choice((-1.0, 1.0))

    ir /= np.sqrt(np.sum(ir ** 2)) or 1.0           # đuôi năng lượng 1 → wet ≈ RMS tín hiệu
    ir *= pr["wet"]
    ir[0] += pr["dry"]                               # xung trực tiếp = đường dry
    return ir.astype(np.float32)


def ir_file(sample_rate: int, vang_truong_do: int, vang_cuong_do: int) -> Path:
    """File WAV đáp ứng xung cho (sr, trường độ, cường độ) — sinh một lần, dùng lại."""
    IR_CACHE_DIR.mkdir(exist_ok=True)
    f = IR_CACHE_DIR / (f"ir_{int(sample_rate)}_d{parse_fx(vang_truong_do)}"
                        f"_c{parse_fx(vang_cuong_do)}.wav")
    if not f.exists() or f.stat().st_size < 1000:
        sf.write(str(f), build_ir(sample_rate, vang_truong_do, vang_cuong_do),
                 int(sample_rate), subtype="FLOAT")
    return f


# ── GHÉP LỆNH FFMPEG ────────────────────────────────────────────────────────────
def sample_rate_of(src) -> int:
    """Tần số lấy mẫu của file audio: soundfile trước (wav/flac/ogg); không đọc
    được (mp3/m4a với libsndfile cũ — giọng mẫu hay là mp3) thì hỏi ffprobe."""
    try:
        return int(sf.info(str(src)).samplerate)
    except Exception:
        r = subprocess.run([shutil.which("ffprobe") or "ffprobe", "-v", "error",
                            "-select_streams", "a:0", "-show_entries", "stream=sample_rate",
                            "-of", "default=nw=1:nk=1", str(src)],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", creationflags=CREATE_NO_WINDOW)
        return int((r.stdout or "").strip().splitlines()[0])


def build_ffmpeg_args(src, speed: float = 1.0, pitch: float = 0.0, sample_rate: int | None = None,
                      vang_truong_do: int = 0, vang_cuong_do: int = 0, thieu_nien: int = 0,
                      sang_giong: int = 0, sang_exciter: bool = True
                      ) -> tuple[list[str], int, bool]:
    """Phần đầu vào + filter của lệnh ffmpeg (chưa có tên file ra).
    Trả (args, sample_rate, có_lọc_gì_không). Tiếng vang dùng -filter_complex vì
    afir cần đáp ứng xung làm luồng vào thứ hai; còn lại dùng -filter:a như cũ."""
    src = str(src)
    sr = int(sample_rate or sample_rate_of(src))
    chain = build_audio_filter(speed, pitch, sr, thieu_nien, sang_giong, sang_exciter)
    args = ["-i", src]
    if parse_fx(vang_cuong_do) > 0:
        pr = vang_params(vang_truong_do, vang_cuong_do)
        args += ["-i", str(ir_file(sr, vang_truong_do, vang_cuong_do))]
        # apad: đệm im lặng đúng bằng RT60 để đuôi vang của chữ cuối không bị cắt
        # (afir không tự kéo dài đầu ra). dry=1:wet=1 vì tỉ lệ dry/wet đã nằm
        # trong IR (xem build_ir). gtype=none + irnorm=-1: KHÔNG để afir tự chuẩn
        # hoá IR (mặc định nó chia cho chuẩn L1 → đuôi dài 2 s bị nhỏ đi ~40 dB).
        # irfmt=mono: một IR cho mọi kênh. alimiter: xem VANG_LIMIT.
        fc = (f"[0:a]{chain or 'anull'},apad=pad_dur={pr['rt60']:.2f}[v];"
              f"[v][1:a]afir=dry=1:wet=1:gtype=none:irnorm=-1:irfmt=mono,"
              f"alimiter=limit={VANG_LIMIT}:attack=5:release=60:level=false:latency=true[out]")
        args += ["-filter_complex", fc, "-map", "[out]"]
        return args, sr, True
    if chain:
        args += ["-filter:a", chain]
        return args, sr, True
    return args, sr, False


def apply_fx_file(src, out=None, speed: float = 1.0, pitch: float = 0.0,
                  vang_truong_do: int = 0, vang_cuong_do: int = 0, thieu_nien: int = 0,
                  sang_giong: int = 0, sang_exciter: bool = True,
                  codec: str = "pcm_s16le") -> Path:
    """Áp tông + tốc độ + bộ lọc (vang / thiếu niên / sáng giọng) lên `src` → `out`
    (giữ sample rate).
    out=None → ghi đè chính file nguồn (qua file tạm; lỗi thì file cũ còn nguyên).
    Không có gì để áp → chỉ chép (hoặc giữ nguyên nếu out == src)."""
    src = Path(src)
    out = Path(out) if out else src
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("Không tìm thấy ffmpeg trong PATH.")
    args, sr, active = build_ffmpeg_args(src, speed, pitch, None, vang_truong_do,
                                         vang_cuong_do, thieu_nien, sang_giong, sang_exciter)
    if not active:
        if out != src:
            shutil.copyfile(src, out)
        return out
    tmp = out.with_name(out.stem + "_fx.tmp" + (out.suffix or ".wav"))
    cmd = [ffmpeg, "-y", "-hide_banner", "-nostats", "-loglevel", "error", *args,
           "-ar", str(sr), "-c:a", codec, str(tmp)]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", creationflags=CREATE_NO_WINDOW)
    if r.returncode != 0 or not tmp.exists() or tmp.stat().st_size <= 4096:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg bộ lọc giọng lỗi: {(r.stderr or '')[-300:] or r.returncode}")
    os.replace(tmp, out)
    return out


def eq_giong_mau_tam(ref, sang_giong: int) -> Path:
    """Bản GIỌNG MẪU đã qua EQ 🔆 Sáng giọng mức `sang_giong` để dựng prompt clone
    — ghi ra file wav TẠM (tempfile; bên gọi xoá sau khi dựng prompt), KHÔNG
    exciter (họa âm giả vào mẫu thì model học cả tiếng xì), giữ sample rate gốc.
    File mẫu gốc không bị đụng. Lỗi (thiếu ffmpeg, file hỏng) → raise, bên gọi
    quyết (myvoice/amain._voice_prompt và myvideo/taogiong_srt._voice_prompt đều
    lùi về dựng prompt từ mẫu gốc và không lưu .pt dưới tên .sang<N>)."""
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".wav", prefix="giongmau_sang_", delete=False) as f:
        tmp = Path(f.name)
    try:
        apply_fx_file(ref, tmp, sang_giong=sang_giong, sang_exciter=False)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return tmp


# ── CHẠY LẺ ─────────────────────────────────────────────────────────────────────
def _cli(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Áp bộ lọc giọng (tiếng vang / thiếu niên) lên một file audio.")
    ap.add_argument("src", help="file audio vào (wav/mp3/...)")
    ap.add_argument("--out", help="file ra (mặc định <src>_fx.wav cạnh file vào)")
    ap.add_argument("--vang", nargs=2, type=int, metavar=("TRUONG_DO", "CUONG_DO"), default=(0, 0),
                    help="tiếng vang: trường độ 0–100, cường độ 0–100 (0 = tắt)")
    ap.add_argument("--thieunien", type=int, default=0, help="giọng thiếu niên: cường độ 0–100")
    ap.add_argument("--sang", type=int, default=0, help="sáng giọng (bớt ồm): cường độ 0–100")
    ap.add_argument("--pitch", type=float, default=0.0, help="tông giọng (bán cung)")
    ap.add_argument("--speed", type=float, default=1.0, help="tốc độ (giữ cao độ)")
    a = ap.parse_args(argv)
    src = Path(a.src)
    out = Path(a.out) if a.out else src.with_name(src.stem + "_fx.wav")
    apply_fx_file(src, out, speed=a.speed, pitch=parse_pitch(a.pitch),
                  vang_truong_do=a.vang[0], vang_cuong_do=a.vang[1], thieu_nien=a.thieunien,
                  sang_giong=a.sang)
    print(json.dumps({"out": str(out), "fx": fx_describe(a.vang[0], a.vang[1], a.thieunien, a.sang),
                      "pitch": a.pitch, "speed": a.speed}, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(_cli())
