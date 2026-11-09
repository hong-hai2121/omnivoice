# -*- coding: utf-8 -*-
"""GPU bắt buộc (27/10/2026): chức năng dùng GPU mà GPU không có / không chạy được thì
ném GpuLoi — báo lỗi rồi dừng, KHÔNG âm thầm rớt về CPU. Không chạy ffmpeg/torch thật:
torch và faster_whisper được thay bằng module giả trong sys.modules."""
import sys
import types
import unittest
from unittest.mock import patch

from myvoice.web import core   # noqa: F401  (đưa myvoice/scripts vào sys.path như test khác)

import video_khung                      # noqa: E402
import taogiong_kiemtra_matchu as ktm   # noqa: E402
import nhandien_giongnoi as recog       # noqa: E402
from gpu_batbuoc import GpuLoi          # noqa: E402

gui = core.gui


def _torch_gia(co_cuda: bool, trong_gb: float = 8.0):
    """Module torch giả: chỉ đủ cho _chon_thiet_bi / get_model hỏi CUDA + VRAM trống."""
    t = types.ModuleType("torch")
    t.cuda = types.SimpleNamespace(
        is_available=lambda: co_cuda,
        mem_get_info=lambda: (int(trong_gb * 2**30), int(8 * 2**30)),
        empty_cache=lambda: None)
    return t


class NvencBatBuocTests(unittest.TestCase):
    def test_khong_co_nvenc_thi_dung(self):
        with patch.object(video_khung, "has_nvenc", return_value=False):
            with self.assertRaises(GpuLoi):
                video_khung.nvenc_batbuoc(True)

    def test_use_gpu_tat_la_chu_y_dung_cpu(self):
        with patch.object(video_khung, "has_nvenc", return_value=False):
            self.assertFalse(video_khung.nvenc_batbuoc(False))

    def test_co_nvenc(self):
        with patch.object(video_khung, "has_nvenc", return_value=True):
            self.assertTrue(video_khung.nvenc_batbuoc(True))

    def test_nvenc_loi_khong_thu_cpu_va_giu_loi_ffmpeg(self):
        with self.assertRaises(GpuLoi) as cm:
            video_khung.dung_neu_nvenc_loi(1, "[h264_nvenc] OpenEncodeSessionEx failed", True)
        self.assertIn("OpenEncodeSessionEx", str(cm.exception))   # lỗi thật của ffmpeg đi kèm
        self.assertIn("không chuyển sang CPU", str(cm.exception))
        video_khung.dung_neu_nvenc_loi(0, "", True)      # chạy tốt → không ném
        video_khung.dung_neu_nvenc_loi(1, "x", False)    # CPU chủ ý → lỗi theo đường cũ

    def test_gpu_loi_la_runtime_error(self):
        # Bên gọi cũ bắt RuntimeError vẫn thấy; chỗ nuốt lỗi phải bắt GpuLoi TRƯỚC.
        self.assertTrue(issubclass(GpuLoi, RuntimeError))


class AsrKiemTraTests(unittest.TestCase):
    def test_khong_cuda_thi_dung(self):
        with patch.dict(sys.modules, {"torch": _torch_gia(False)}):
            with self.assertRaises(GpuLoi):
                ktm._chon_thiet_bi()

    def test_thieu_vram_thi_dung_khong_lui_cpu(self):
        with patch.dict(sys.modules, {"torch": _torch_gia(True, trong_gb=1.0)}):
            with self.assertRaises(GpuLoi) as cm:
                ktm._chon_thiet_bi()
        self.assertIn("VRAM", str(cm.exception))

    def test_du_vram_thi_cuda(self):
        with patch.dict(sys.modules, {"torch": _torch_gia(True, trong_gb=6.0)}):
            self.assertEqual(ktm._chon_thiet_bi(), ("cuda", "float16"))

    def test_quet_khong_nuot_gpu_loi(self):
        # Thiếu model/thư viện → bỏ qua bước kiểm như cũ; thiếu GPU → ném tiếp lên bên gọi.
        with patch.object(ktm, "_get_model", side_effect=RuntimeError("thiếu model")):
            self.assertEqual(ktm.quet_va_xac_minh(["a"], "."), {})
        with patch.object(ktm, "_get_model", side_effect=GpuLoi("không có GPU")):
            with self.assertRaises(GpuLoi):
                ktm.quet_va_xac_minh(["a"], ".")


class NhanDienTests(unittest.TestCase):
    def test_get_model_khong_cuda_thi_dung(self):
        fw = types.ModuleType("faster_whisper")
        fw.WhisperModel = object
        fw.BatchedInferencePipeline = object
        with patch.dict(sys.modules, {"torch": _torch_gia(False), "faster_whisper": fw}):
            recog.free_model()
            with self.assertRaises(GpuLoi):
                recog.get_model("tiny")


class OmniVoiceTests(unittest.TestCase):
    def test_load_omnivoice_cpu_thi_dung_truoc_khi_nap(self):
        # Thiết bị không phải CUDA → ném ngay, chưa đụng tới torch/model.
        with self.assertRaises(GpuLoi):
            gui.load_omnivoice("cpu")


if __name__ == "__main__":
    unittest.main()
