"""
Phát hiện chunk .wav bị lỗi spike âm thanh (tiếng lạ to bất thường).

Nguyên lý:
- Chia mỗi file thành các khung nhỏ (50ms)
- Tính RMS trung bình toàn file
- Tìm khung nào có RMS vượt quá N lần mức trung bình → spike
- Xuất danh sách file lỗi + vị trí spike (giây)
"""

import io
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE_DIR      = Path(__file__).resolve().parent.parent   # myvoice/
CHUNKS_DIR    = BASE_DIR / "kịch_bản" / "output_chunks"
PREVIEW_FILE  = BASE_DIR / "kịch_bản" / "input_preview.txt"

FRAME_MS      = 50       # độ dài mỗi khung phân tích (ms)
SPIKE_RATIO   = 5.0      # khung vượt N × RMS_median → spike thật sự
SILENT_RMS    = 0.005    # file có median < ngưỡng này = gần như im lặng (lỗi nặng)
MIN_RMS       = 0.001    # bỏ qua file hoàn toàn trống


def check_file(path: Path, expected_text: str = "") -> dict:
    data, sr = sf.read(str(path), dtype="float32", always_2d=False)
    if data.ndim > 1:
        data = data.mean(axis=1)

    frame_size = int(sr * FRAME_MS / 1000)
    frames = [data[i:i+frame_size] for i in range(0, len(data)-frame_size, frame_size)]
    if not frames:
        return {"file": path.name, "ok": False, "reason": "file rỗng"}

    rms_per_frame  = np.array([np.sqrt(np.mean(f**2)) for f in frames])
    median_rms     = float(np.median(rms_per_frame))   # median ổn hơn mean khi có spike
    peak_rms       = rms_per_frame.max()
    peak_abs       = float(np.abs(data).max())
    crest          = peak_rms / median_rms if median_rms > MIN_RMS else 0

    # Spike: vượt N × median HOẶC peak tuyệt đối quá cao
    # Spike thật: khung vượt N× median VÀ median đủ lớn để có giọng nói
    spike_frames   = np.where(
        (rms_per_frame > SPIKE_RATIO * max(median_rms, MIN_RMS * 5))
    )[0]
    spike_times    = [round(idx * FRAME_MS / 1000, 2) for idx in spike_frames]
    # File gần im lặng nhưng có spike = lỗi nặng (model sinh toàn noise)
    is_silent      = median_rms < SILENT_RMS

    duration = len(data) / sr

    has_error = bool(spike_times) or is_silent
    return {
        "file":        path.name,
        "duration":    round(duration, 2),
        "median_rms":  round(median_rms, 4),
        "peak_abs":    round(peak_abs, 4),
        "crest":       round(float(crest), 1),
        "spikes":      spike_times,
        "silent":      is_silent,
        "ok":          not has_error and median_rms > MIN_RMS,
        "text":        expected_text[:80],
    }


def main():
    wav_files = sorted(CHUNKS_DIR.glob("*.wav"))
    if not wav_files:
        print(f"Không tìm thấy file .wav trong {CHUNKS_DIR}")
        sys.exit(1)

    # Đọc text gốc từng chunk
    if PREVIEW_FILE.exists():
        chunks_text = PREVIEW_FILE.read_text(encoding="utf-8").split("\n\n")
    else:
        chunks_text = [""] * len(wav_files)

    print(f"Kiểm tra {len(wav_files)} file — ngưỡng spike: {SPIKE_RATIO}× RMS\n")
    print(f"{'File':<12} {'Dur':>6} {'Median':>7} {'PeakAbs':>8} {'Crest':>7}  Trạng thái")
    print("-" * 75)

    errors = []
    for wav in wav_files:
        idx = int(wav.stem)
        text = chunks_text[idx] if idx < len(chunks_text) else ""
        r = check_file(wav, text)

        status = "OK"
        if not r["ok"]:
            if r.get("reason"):
                status = f"LỖI: {r['reason']}"
            elif r.get("silent"):
                status = "LỖI: gần im lặng (model sinh noise)"
                errors.append(r)
            elif r["spikes"]:
                status = f"SPIKE @{r['spikes'][:3]}s"
                errors.append(r)
            elif r["median_rms"] <= MIN_RMS:
                status = "LỖI: file trống"
                errors.append(r)

        flag = "  ← !" if not r["ok"] else ""
        print(f"{r['file']:<12} {r.get('duration',0):>6.1f}s  "
              f"{r.get('median_rms',0):>7.4f}  {r.get('peak_abs',0):>8.4f}  "
              f"{r.get('crest',0):>6.1f}x  {status}{flag}")

    print(f"\n{'='*70}")
    if errors:
        print(f"Tìm thấy {len(errors)} file lỗi:\n")
        for r in errors:
            spike_info = f"spike@{r['spikes'][:5]}s" if r['spikes'] else f"peak_abs={r['peak_abs']:.3f}"
            print(f"  [{r['file']}]  crest={r['crest']}x  {spike_info}")
            print(f"    Text: {r['text']}")
            print()
        print("→ Xóa các file lỗi trong output_chunks/ rồi chạy lại clone_gui.py để generate lại.")
        print("→ Xóa các file lỗi trên rồi chạy lại clone_gui.py để generate lại.")
    else:
        print("Không phát hiện spike — tất cả file bình thường.")


if __name__ == "__main__":
    main()
