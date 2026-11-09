# -*- coding: utf-8 -*-
"""Ba chốt sau sự cố đêm 05/11/2026 (mẻ 6 tập 164–169, chế độ 🗣 VieNeu).

02:33 driver NVIDIA treo → tới khi khởi động lại máy không tiến trình mới nào dùng được
CUDA. VieNeu (device=auto) lặng lẽ rớt về ONNX/CPU, sinh đủ đoạn chậm gấp ~4 lần rồi dừng
ở bước ASR kiểm tra (GPU bắt buộc); hàng đợi cứ chạy tiếp 5 tập sau và hỏng y hệt; hàng
đợi hết thì ô ⏻ tắt máy, nhật ký (chỉ ở console) mất sạch.

  1. VieNeu ÉP GPU: worker --device cuda không có CUDA → thoát mã 79, client ném
     KhongCoGpu, nap_engine đổi thành GpuLoi (không còn lặng lẽ chạy CPU).
  2. Lỗi GPU → runner trả mã 79 → hàng đợi TẠM DỪNG (giữ việc còn chờ), nêu lý do trên
     trang; ô ⏻ vẫn tắt máy nhưng ghi rõ vì sao.
  3. Nhật ký hàng đợi chép ra tệp theo ngày, đọc lại được ở trang /nhatky.

Chạy từ gốc repo:  venv\\Scripts\\python.exe -m unittest myvoice/tests/test_dung_loi_gpu.py
Không cần cài VieNeu, không đụng GPU thật: torch giả, worker giả, hàng đợi chạy `python -c`.
"""
import os
import socket
import sys
import tempfile
import threading
import time
import types
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from starlette.requests import Request

from myvoice.web import core  # noqa: F401  vá sys.path (scripts/) + import amain_taogiong_gui
import amain_taogiong_gui as tts  # noqa: E402
import gpu_batbuoc  # noqa: E402
from gpu_batbuoc import GpuLoi, MA_THOAT_GPU  # noqa: E402
from myvoice.web import jobs, power, server, steps  # noqa: E402
from myvoice.web.runners import run_episode  # noqa: E402

_VOICE_DIR = Path(__file__).resolve().parents[1] / "voice"
if str(_VOICE_DIR) not in sys.path:
    sys.path.insert(0, str(_VOICE_DIR))
import vieneu_client as vn  # noqa: E402
import vieneu_worker as vw  # noqa: E402

# ── CHỐT AN TOÀN: tiến trình chạy test KHÔNG BAO GIỜ được tắt máy / cho máy ngủ thật ──
# (05/11/2026 — user nhắc: thử phần tắt máy phải cẩn thận.) Các test ở đây chỉ gọi _tick()
# với đồng hồ giả trên một watcher KHÔNG bật luồng canh, nên vốn không tới được lệnh thật.
# Nhưng watcher toàn cục của power.py vẫn sống trong tiến trình này; lỡ sau này có test
# nào bật nó lên thì hai hàm phát lệnh đã bị thay bằng hàm ném lỗi — thay ngay lúc import,
# giữ suốt đời tiến trình, không gỡ.
def _cam_lenh_that(*_a, **_k):
    raise AssertionError("test không được phát lệnh tắt máy / cho máy ngủ thật")


power.PowerWhenDone._shutdown_now = _cam_lenh_that
power.PowerWhenDone._sleep_now = _cam_lenh_that

PY = sys.executable
ENV = dict(os.environ, PYTHONIOENCODING="utf-8")
# Runner thật in dòng này ngay trước khi thoát mã 79 (xem run_episode.main).
LOI_GPU = ("print('⛔ LỖI GPU ở tập 99 → dừng cả hàng đợi: không có CUDA (thử)'); "
           "raise SystemExit(79)")


def _buoc(ma_py: str, **kw) -> jobs.Step:
    return jobs.Step(label=kw.pop("label", "bước thử"), argv=[PY, "-c", ma_py], env=ENV, **kw)


def _ghi(path: Path) -> str:
    """Mã python ghi một tệp đánh dấu — bước này CÓ chạy thì tệp xuất hiện."""
    return f"open({str(path)!r}, 'w').write('x')"


def _cho(dieu_kien, giay: float = 30.0) -> None:
    han = time.monotonic() + giay
    while time.monotonic() < han:
        if dieu_kien():
            return
        time.sleep(0.05)
    raise AssertionError("hết giờ chờ hàng đợi")


class _V:
    """Thay tk.IntVar/StringVar cho run_tts."""

    def __init__(self, v=""):
        self._v = v

    def set(self, v):
        self._v = v

    def get(self):
        return self._v


# ── 1. VieNeu ép GPU ─────────────────────────────────────────────────────────
class TestWorkerEpGpu(unittest.TestCase):
    def test_hang_so_hai_ben_khop(self):
        # Worker chạy ở venv khác nên hai hằng phải chép tay — test giữ cho không lệch.
        self.assertEqual(vn.MA_KHONG_GPU, vw.MA_KHONG_GPU)
        self.assertEqual(vn.DAU_KHONG_GPU, vw.DAU_KHONG_GPU)
        self.assertEqual(vw.MA_KHONG_GPU, MA_THOAT_GPU)

    def _torch_gia(self, co_cuda=True, zeros=None):
        return types.SimpleNamespace(
            cuda=types.SimpleNamespace(is_available=lambda: co_cuda),
            zeros=zeros or (lambda *a, **k: object()))

    def test_kiem_cuda_dung_duoc(self):
        with patch.dict(sys.modules, {"torch": self._torch_gia()}):
            self.assertEqual(vw.kiem_cuda(), "")

    def test_kiem_cuda_khong_co_cuda(self):
        with patch.dict(sys.modules, {"torch": self._torch_gia(co_cuda=False)}):
            ly_do = vw.kiem_cuda()
        self.assertIn("is_available() = False", ly_do)
        self.assertIn("khởi động lại", ly_do)

    def test_kiem_cuda_available_nhung_khoi_tao_loi(self):
        # Sau khi driver treo có lúc is_available() vẫn True mà tạo context thì lỗi.
        def no(*a, **k):
            raise RuntimeError("CUDA error: unknown error")
        with patch.dict(sys.modules, {"torch": self._torch_gia(zeros=no)}):
            ly_do = vw.kiem_cuda()
        self.assertIn("không khởi tạo được", ly_do)
        self.assertIn("unknown error", ly_do)

    def test_kiem_cuda_venv_ban_cpu_khong_co_torch(self):
        with patch.dict(sys.modules, {"torch": None}):      # import torch → ImportError
            ly_do = vw.kiem_cuda()
        self.assertIn("không nạp được torch", ly_do)
        self.assertIn("Cài GPU", ly_do)

    def test_main_ep_cuda_khong_co_gpu_thoat_79_khong_nap_model(self):
        with patch.object(sys, "argv", ["vieneu_worker.py", "--port", "1", "--device", "cuda"]), \
                patch.object(vw, "kiem_cuda", return_value="driver treo (thử)"), \
                patch.object(vw, "_Engine", side_effect=AssertionError("không được nạp model")), \
                patch("builtins.print") as in_ra:
            self.assertEqual(vw.main(), vw.MA_KHONG_GPU)
        dong = [c.args[0] for c in in_ra.call_args_list]
        self.assertTrue(any(d.startswith(vw.DAU_KHONG_GPU) and "driver treo (thử)" in d
                            for d in dong), dong)

    def test_main_ep_cuda_ma_sdk_van_chon_onnx_cung_thoat_79(self):
        eng = types.SimpleNamespace(backend="onnx", t_nap=0.1, voices=[])
        with patch.object(sys, "argv", ["vieneu_worker.py", "--port", "1", "--device", "cuda"]), \
                patch.object(vw, "kiem_cuda", return_value=""), \
                patch.object(vw, "_Engine", return_value=eng), \
                patch.object(vw, "make_server", side_effect=AssertionError("không được mở server")), \
                patch("builtins.print"):
            self.assertEqual(vw.main(), vw.MA_KHONG_GPU)


class _ProcGia:
    """Tiến trình worker đã thoát với mã `ma`."""

    def __init__(self, ma):
        self.returncode = ma

    def poll(self):
        return self.returncode

    def terminate(self):
        pass

    def wait(self, timeout=None):
        return self.returncode

    def kill(self):
        pass


class TestClientEpGpu(unittest.TestCase):
    def _bat_voi_worker_chet(self, ma, dong_log):
        w = vn.SdkWorker()
        ghi = {}

        def _bat_gia(cmd, env, cong, on_line):
            ghi["cmd"] = cmd
            w.cong, w.proc = cong, _ProcGia(ma)
            for d in dong_log:
                on_line(d)

        nhan = []
        with patch.object(w, "_bat", _bat_gia):
            try:
                w.bat(cong=65001, device="cuda", on_line=nhan.append)
            except RuntimeError as e:
                return w, ghi["cmd"], nhan, e
        raise AssertionError("bat() phải ném lỗi khi worker chết")

    def test_worker_thoat_79_thanh_khong_co_gpu_kem_ly_do(self):
        w, cmd, nhan, e = self._bat_voi_worker_chet(
            vn.MA_KHONG_GPU, ["⏳ khởi động", f"{vn.DAU_KHONG_GPU} torch.cuda.is_available() = False"])
        self.assertIsInstance(e, vn.KhongCoGpu)
        self.assertIn("is_available() = False", str(e))
        self.assertEqual(cmd[cmd.index("--device") + 1], "cuda")
        self.assertEqual(len(nhan), 2)            # dòng log vẫn tới bên gọi đủ
        self.assertIsNone(w.proc)                 # đã dọn tiến trình

    def test_worker_chet_ma_khac_van_la_loi_thuong(self):
        _w, _cmd, _nhan, e = self._bat_voi_worker_chet(1, ["Traceback…"])
        self.assertNotIsInstance(e, vn.KhongCoGpu)
        self.assertIn("không lên", str(e))

    def test_cuda_loi_giua_chung_thanh_khong_co_gpu(self):
        class Eng:
            voices, backend = ["Ngọc Huyền"], "pytorch"

            def infer(self, texts, voice, temperature, top_k):
                raise RuntimeError("CUDA error: unknown error")

        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            cong = s.getsockname()[1]
        srv = vw.make_server(Eng(), cong)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        w = vn.SdkWorker()
        w.cong = cong
        with patch("builtins.print"), self.assertRaises(vn.KhongCoGpu) as cm:
            w.doc("xin chào.", "Ngọc Huyền")
        self.assertIn("CUDA error", str(cm.exception))


class TestNapEngineEpGpu(unittest.TestCase):
    def test_bat_worker_voi_device_cuda(self):
        class W:
            sr, backend, giong = 48_000, "pytorch", ["a"]

            def bat(self, device="auto", on_line=None):
                self.device = device
                return {}
        w = W()
        with patch.object(tts.vn, "trang_thai", return_value=dict(da_cai=True)), \
                patch.object(tts.vn, "SdkWorker", return_value=w):
            model, sr = tts.nap_engine("vieneu")
        self.assertIs(model, w)
        self.assertEqual(w.device, "cuda")        # KHÔNG còn "auto" (lặng lẽ rớt CPU)
        self.assertEqual(sr, 48_000)

    def test_khong_co_gpu_thanh_gpu_loi(self):
        class W:
            def bat(self, **kw):
                raise vn.KhongCoGpu("VieNeu worker không dùng được GPU: driver treo (thử)")
        with patch.object(tts.vn, "trang_thai", return_value=dict(da_cai=True)), \
                patch.object(tts.vn, "SdkWorker", return_value=W()):
            with self.assertRaises(GpuLoi) as cm:
                tts.nap_engine("vieneu")
        self.assertIn("driver treo (thử)", str(cm.exception))
        self.assertIn("không tạo giọng VieNeu bằng CPU", str(cm.exception))


# ── 2. Lỗi GPU → mã 79 → hàng đợi tạm dừng ───────────────────────────────────
class TestRunTtsGhiLoiGpu(unittest.TestCase):
    """run_tts nuốt lỗi rồi trả False — nó phải ghi lại nếu lỗi đó là lỗi GPU."""

    def _chay(self, **vá):
        with tempfile.TemporaryDirectory() as d:
            ev = threading.Event()
            ev.set()
            stub = tts._NullWidget()
            with patch.object(tts, "_play_done_sound"), patch.object(tts.logging, "error"), \
                    patch.object(tts.logging, "info"), patch.object(tts.logging, "warning"):
                with patch.multiple(tts, **vá):
                    return tts.run_tts("vieneu", "Ngọc Huyền", ["xin chào."],
                                       str(Path(d) / "output.wav"), _V(0), _V(""),
                                       stub, stub, stub, ev)

    def test_gpu_loi_luc_nap_engine_duoc_ghi(self):
        ok = self._chay(nap_engine=MagicMock(side_effect=GpuLoi("không có CUDA (thử)")))
        self.assertFalse(ok)
        self.assertEqual(gpu_batbuoc.loi_cuoi(), "không có CUDA (thử)")

    def test_worker_mat_cuda_giua_chung_cung_duoc_ghi(self):
        class W(vn.SdkWorker):
            def doc(self, text, voice, **kw):
                raise vn.KhongCoGpu("VieNeu worker lỗi GPU giữa chừng (500): CUDA error")

            def tat(self):
                pass
        ok = self._chay(nap_engine=MagicMock(return_value=(W(), 48_000)))
        self.assertFalse(ok)
        self.assertIn("giữa chừng", gpu_batbuoc.loi_cuoi())

    def test_loi_thuong_khong_bi_coi_la_loi_gpu(self):
        gpu_batbuoc.ghi_loi("lỗi GPU của lượt TRƯỚC")       # không được dính sang lượt này
        ok = self._chay(nap_engine=MagicMock(side_effect=RuntimeError("worker không lên")))
        self.assertFalse(ok)
        self.assertEqual(gpu_batbuoc.loi_cuoi(), "")


class TestRunnerMaThoat(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for p in (patch.object(run_episode, "_setup_logging"),
                  patch.object(run_episode, "_resolve_folder",
                               return_value=(Path(self.tmp.name), "99"))):
            p.start()
            self.addCleanup(p.stop)

    def test_ma_79_la_mot_nguon(self):
        self.assertEqual(run_episode.GPU_LOI, MA_THOAT_GPU)
        self.assertEqual(steps.GPU_CODE, MA_THOAT_GPU)
        self.assertEqual(MA_THOAT_GPU, 79)
        self.assertNotIn(MA_THOAT_GPU, (run_episode.STOP, run_episode.SEO_SOFT, run_episode.ERROR))

    def test_step_tts_loi_gpu_tra_79(self):
        app = MagicMock()
        app._seo_docx_valid.return_value = True
        app._batch_run_tts.return_value = False
        ts = {"tts": {"mode": "vieneu", "chunk": 160}}
        with patch.object(run_episode.logging, "error"):
            with patch.object(run_episode, "gpu_loi_cuoi", return_value="không có CUDA"):
                ma = run_episode.step_tts(app, Path(self.tmp.name), "99", dict(ts))
            self.assertEqual(ma, run_episode.GPU_LOI)
            with patch.object(run_episode, "gpu_loi_cuoi", return_value=""):
                ma = run_episode.step_tts(app, Path(self.tmp.name), "99", dict(ts))
            self.assertEqual(ma, run_episode.ERROR)      # lỗi thường vẫn là mã lỗi thường
        self.assertEqual(app._batch_run_tts.call_count, 2)

    def test_main_buoc_nem_gpu_loi_tra_79_va_in_ly_do_cuoi_cung(self):
        with patch.object(run_episode, "step_recognize",
                          side_effect=GpuLoi("không có GPU CUDA để nhận diện")), \
                patch.object(run_episode.logging, "info"), \
                patch.object(run_episode.logging, "error") as loi:
            ma = run_episode.main(["--steps", "recognize", "--episode", "99"])
        self.assertEqual(ma, run_episode.GPU_LOI)
        cuoi = loi.call_args_list[-1].args[0]            # hàng đợi lấy dòng ⛔ CUỐI làm lý do
        self.assertTrue(cuoi.startswith("⛔ LỖI GPU"), cuoi)
        self.assertIn("không có GPU CUDA để nhận diện", cuoi)

    def test_main_buoc_tts_tra_79_thi_main_tra_79(self):
        with patch.object(run_episode, "step_tts", return_value=run_episode.GPU_LOI), \
                patch.object(run_episode, "gpu_loi_cuoi", return_value="VRAM trống 0.4 GB"), \
                patch.object(run_episode.logging, "info"), \
                patch.object(run_episode.logging, "error") as loi:
            ma = run_episode.main(["--steps", "tts", "--episode", "99"])
        self.assertEqual(ma, run_episode.GPU_LOI)
        self.assertIn("VRAM trống 0.4 GB", loi.call_args_list[-1].args[0])

    def test_main_loi_thuong_van_tra_2(self):
        with patch.object(run_episode, "step_recognize", side_effect=ValueError("hỏng")), \
                patch.object(run_episode.logging, "info"), \
                patch.object(run_episode.logging, "error"):
            self.assertEqual(run_episode.main(["--steps", "recognize", "--episode", "99"]),
                             run_episode.ERROR)


class TestBuocMangMaDung(unittest.TestCase):
    """Mọi bước chạy runner dùng GPU phải khai halt_codes — không thì mã 79 thành lỗi thường."""

    def setUp(self):
        for p in (patch.object(steps, "_write_tts_json", return_value=("thu.json", "")),
                  patch.object(core, "load_pipeline", return_value={})):
            p.start()
            self.addCleanup(p.stop)

    def test_dot_chay_tiep(self):
        buoc, loi = steps.resume_step(["thumbnail", "tts"], "nguon", "99",
                                      continue_on_fail=True)
        self.assertEqual(loi, "")
        self.assertEqual(buoc.halt_codes, (MA_THOAT_GPU,))
        self.assertTrue(buoc.continue_on_fail)

    def test_chuoi_buoc_le(self):
        ds, loi = steps.build_steps(["recognize", "tts"], source="nguon", episode="99")
        self.assertEqual(loi, "")
        self.assertTrue(all(b.halt_codes == (MA_THOAT_GPU,) for b in ds))

    def test_trang_giong_noi(self):
        ds, loi = steps.tts_steps()
        self.assertEqual(loi, "")
        self.assertEqual(ds[0].halt_codes, (MA_THOAT_GPU,))


class TestHangDoiDungViLoi(unittest.TestCase):
    def setUp(self):
        self.dong: list[str] = []
        p = patch.object(jobs, "log", self.dong.append)
        p.start()
        self.addCleanup(p.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dau = Path(self.tmp.name) / "da_chay.txt"
        self.r = jobs.JobRunner()
        self.addCleanup(self.r.stop_all)

    def _cho_dung(self):
        _cho(lambda: self.r.halted() is not None)
        _cho(lambda: self.r.state()["current"] is None)

    def test_ma_79_tam_dung_giu_viec_cho_roi_tiep(self):
        self.r.enqueue("Tập 99 — thử", [_buoc(LOI_GPU, halt_codes=(79,), label="④ giọng")])
        self.r.enqueue("Tập 100", [_buoc(_ghi(self.dau))])
        self._cho_dung()
        st = self.r.state()
        self.assertTrue(st["paused"])
        self.assertEqual(st["halt"]["title"], "Tập 99 — thử")
        self.assertEqual(st["halt"]["step"], "④ giọng")
        self.assertIn("không có CUDA (thử)", st["halt"]["reason"])    # lý do = dòng ⛔ của runner
        self.assertEqual([j["title"] for j in st["pending"]], ["Tập 100"])
        self.assertEqual(st["history"][0]["status"], "failed")
        time.sleep(1.5)                       # worker tỉnh mỗi giây — việc chờ KHÔNG được chạy
        self.assertFalse(self.dau.exists())
        # Ô ⏻ nhìn heavy_busy(): việc chờ không tự chạy được nữa → coi là hết việc.
        self.assertTrue(self.r.busy())
        self.assertFalse(self.r.heavy_busy())
        self.assertTrue(any("TẠM DỪNG hàng đợi" in d and "1 việc còn chờ" in d for d in self.dong))

        self.r.resume()                       # sửa xong, bấm ▶ Tiếp
        _cho(self.dau.exists)
        _cho(lambda: not self.r.busy())
        self.assertIsNone(self.r.halted())
        self.assertFalse(self.r.state()["paused"])

    def test_ma_79_thang_continue_on_fail_trong_dot(self):
        # Đêm 05/11: một việc "đợt" 6 tập, mỗi tập một bước continue_on_fail → chạy tiếp cả 5.
        self.r.enqueue("⏩ đợt 4 — 2 tập", [
            _buoc(LOI_GPU, halt_codes=(79,), continue_on_fail=True, label="tập 99"),
            _buoc(_ghi(self.dau), halt_codes=(79,), continue_on_fail=True, label="tập 100")])
        self._cho_dung()
        self.assertFalse(self.dau.exists())               # tập sau trong đợt KHÔNG chạy
        self.assertEqual(self.r.state()["history"][0]["status"], "failed")
        self.assertEqual(self.r.halted()["step"], "tập 99")

    def test_ma_loi_thuong_khong_dung_hang_doi(self):
        self.r.enqueue("Tập 99", [_buoc("raise SystemExit(2)", halt_codes=(79,))])
        self.r.enqueue("Tập 100", [_buoc(_ghi(self.dau), halt_codes=(79,))])
        _cho(self.dau.exists)
        _cho(lambda: not self.r.busy())
        self.assertIsNone(self.r.halted())
        self.assertFalse(self.r.state()["paused"])

    def test_buoc_khong_khai_halt_codes_thi_79_la_loi_thuong(self):
        self.r.enqueue("Tập 99", [_buoc(LOI_GPU)])
        self.r.enqueue("Tập 100", [_buoc(_ghi(self.dau))])
        _cho(self.dau.exists)
        self.assertIsNone(self.r.halted())

    def test_dung_het_xoa_ly_do(self):
        self.r.enqueue("Tập 99", [_buoc(LOI_GPU, halt_codes=(79,))])
        self.r.enqueue("Tập 100", [_buoc(_ghi(self.dau))])
        self._cho_dung()
        self.r.stop_all()
        st = self.r.state()
        self.assertIsNone(st["halt"])
        self.assertFalse(st["paused"])
        self.assertEqual(st["pending"], [])


class TestTatMayKhiDungViLoi(unittest.TestCase):
    def test_tien_trinh_test_khong_phat_duoc_lenh_that(self):
        # Chốt an toàn ở đầu file: kể cả watcher TOÀN CỤC cũng không gọi được shutdown / ngủ.
        with patch.object(power.subprocess, "run") as chay, patch.object(power, "suspend") as ngu:
            for ham in (power.watcher._shutdown_now, power.watcher._sleep_now):
                with self.assertRaises(AssertionError):
                    ham()
        chay.assert_not_called()
        ngu.assert_not_called()
        self.assertFalse(power.watcher.state()["armed"])     # và nó vốn không hề được bật

    def test_van_dem_nguoc_va_ghi_ro_ly_do(self):
        ban = {"v": True}
        now = {"t": 1000.0}
        ly_do = {"at": "02:35:10", "title": "⏩ đợt 4 — 6 tập", "step": "tập 165",
                 "reason": "⛔ LỖI GPU ở tập 165 → dừng cả hàng đợi: không có CUDA"}
        ghi = MagicMock()
        for p in (patch.object(power.runner, "heavy_busy", side_effect=lambda: ban["v"]),
                  patch.object(power.runner, "halted", return_value=ly_do),
                  patch.object(power.upload_runner, "heavy_busy", return_value=False),
                  patch.object(power.fb_runner, "heavy_busy", return_value=False),
                  patch.object(power.time, "monotonic", side_effect=lambda: now["t"]),
                  patch.object(power, "log", ghi)):
            p.start()
            self.addCleanup(p.stop)
        with patch.object(threading.Thread, "start"):
            w = power.PowerWhenDone()
        w.arm("shutdown")
        self.assertEqual(w._tick(), "")            # đang chạy tập 165
        ban["v"] = False                           # hàng đợi dừng vì lỗi → heavy_busy False
        self.assertEqual(w._tick(), "")
        self.assertTrue(w.state()["counting"])
        dong = ghi.call_args_list[-1].args[0]
        self.assertIn("DỪNG VÌ LỖI", dong)
        self.assertIn("không có CUDA", dong)
        self.assertIn("TẮT MÁY", dong)
        now["t"] += power.SHUTDOWN_DELAY_MIN * 60 + 1
        self.assertEqual(w._tick(), "shutdown")


# ── 3. Nhật ký ra tệp ────────────────────────────────────────────────────────
class TestNhatKyTep(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(jobs.bat_nhat_ky_tep, None)     # đóng tệp TRƯỚC khi xoá thư mục tạm
        self.dir = Path(self.tmp.name) / "nhatky"
        self.hom_nay = datetime.now().strftime("%Y-%m-%d")

    def _tep(self) -> Path:
        return self.dir / f"hangdoi_{self.hom_nay}.log"

    def test_mac_dinh_tat_import_khong_sinh_tep(self):
        self.assertIsNone(jobs.thu_muc_nhat_ky())
        with patch("builtins.print"):
            jobs.log("dòng thử")                         # không bật thì không ghi gì, không lỗi
        self.assertEqual(jobs.cac_ngay_nhat_ky(), [])
        self.assertEqual(jobs.doc_nhat_ky(), ("", [], 0))

    def test_moi_dong_ra_tep_kem_gio_va_xa_ngay(self):
        jobs.bat_nhat_ky_tep(self.dir)
        with patch("builtins.print"):
            jobs.log("▶ Tập 99\n[1/3] 'câu một'\n❌ Lỗi thử")
        # Chưa đóng tệp mà đã đọc được đủ 3 dòng = xả theo từng dòng (tắt máy đột ngột vẫn còn).
        dong = self._tep().read_text(encoding="utf-8").splitlines()
        self.assertEqual([d[10:] for d in dong], ["▶ Tập 99", "[1/3] 'câu một'", "❌ Lỗi thử"])
        self.assertRegex(dong[0], r"^\d\d:\d\d:\d\d  ")

    def test_khong_co_console_van_ghi_tep(self):
        jobs.bat_nhat_ky_tep(self.dir)
        with patch("builtins.print", side_effect=OSError("pythonw: không có console")):
            jobs.log("dòng một\ndòng hai")
        self.assertEqual(len(self._tep().read_text(encoding="utf-8").splitlines()), 2)

    def test_doc_lai_moc_chinh_va_day_du(self):
        jobs.bat_nhat_ky_tep(self.dir)
        with patch("builtins.print"):
            jobs.log("▶ Tập 99\n── [1/1] ④ Tạo giọng + video\n[1/703] 'câu một'\n"
                     "  [SPIKE] 0060.wav\n⛔ LỖI GPU ở tập 99 → dừng cả hàng đợi: thử\n"
                     "⏻ Hết giờ — đang TẮT MÁY")
        ngay, moc, tong = jobs.doc_nhat_ky(chi_moc=True)
        self.assertEqual(ngay, self.hom_nay)
        self.assertEqual(tong, 4)
        self.assertEqual([d[10:11] for d in moc], ["▶", "─", "⛔", "⏻"])
        self.assertEqual(jobs.doc_nhat_ky()[2], 6)
        self.assertEqual(len(jobs.doc_nhat_ky(toi_da=2)[1]), 2)      # chỉ lấy các dòng CUỐI
        self.assertEqual(jobs.doc_nhat_ky(toi_da=2)[1][-1][10:], "⏻ Hết giờ — đang TẮT MÁY")

    def test_ngay_la_khong_lot_duong_dan(self):
        jobs.bat_nhat_ky_tep(self.dir)
        with patch("builtins.print"):
            jobs.log("x")
        for la in ("../../web_settings", "2020-01-01", "..\\..\\token"):
            self.assertEqual(jobs.doc_nhat_ky(la)[0], self.hom_nay)

    def test_tu_xoa_tep_qua_han_giu_tep_con_han(self):
        self.dir.mkdir(parents=True)
        cu = self.dir / "hangdoi_2020-01-01.log"
        hom_qua = self.dir / f"hangdoi_{datetime.now() - timedelta(days=1):%Y-%m-%d}.log"
        khac = self.dir / "ghi_chu.txt"
        for p in (cu, hom_qua, khac):
            p.write_text("x", encoding="utf-8")
        jobs.bat_nhat_ky_tep(self.dir)
        with patch("builtins.print"):
            jobs.log("dòng mới")
        self.assertFalse(cu.exists())
        self.assertTrue(hom_qua.exists())
        self.assertTrue(khac.exists())                   # không đụng tệp không phải của mình
        self.assertEqual(jobs.cac_ngay_nhat_ky()[0], self.hom_nay)

    def test_ghi_hong_khong_lam_hong_viec(self):
        chan = Path(self.tmp.name) / "la_tep"
        chan.write_text("x", encoding="utf-8")           # "thư mục" thật ra là một tệp
        jobs.bat_nhat_ky_tep(chan)
        with patch("builtins.print"):
            jobs.log("dòng một")                         # không được ném lỗi
            jobs.log("dòng hai")
        self.assertEqual(chan.read_text(encoding="utf-8"), "x")


class TestTrangWeb(unittest.TestCase):
    def test_khoi_hang_doi_neu_ro_ly_do_dung(self):
        q = {"paused": True, "current": None, "history": [],
             "pending": [{"id": 2, "title": "Tập 100"}],
             "halt": {"at": "02:35:10", "title": "⏩ đợt 4 — 6 tập", "step": "tập 165",
                      "reason": "⛔ LỖI GPU ở tập 165 → dừng cả hàng đợi: <không có CUDA>"}}
        html = server.templates.env.get_template("_queue.html").render(q=q)
        self.assertIn("DỪNG VÌ LỖI GPU", html)
        self.assertIn("02:35:10", html)
        self.assertIn("&lt;không có CUDA&gt;", html)      # lý do được escape, không chèn HTML
        self.assertIn("1 việc còn chờ", html)
        self.assertIn('href="/nhatky"', html)
        self.assertNotIn("đang tạm dừng — bấm", html)     # không lặp dòng "tạm dừng" thường

    def test_tam_dung_thuong_van_nhu_cu(self):
        q = {"paused": True, "halt": None, "current": None, "pending": [], "history": []}
        html = server.templates.env.get_template("_queue.html").render(q=q)
        self.assertIn("đang tạm dừng — bấm", html)
        self.assertNotIn("DỪNG VÌ LỖI GPU", html)

    def test_trang_nhat_ky_doc_tu_tep(self):
        with tempfile.TemporaryDirectory() as d:
            jobs.bat_nhat_ky_tep(d)
            self.addCleanup(jobs.bat_nhat_ky_tep, None)
            with patch("builtins.print"):
                jobs.log("▶ Tập 99\n[1/703] 'câu một'\n⛔ LỖI GPU ở tập 99: <thử>")
            yc = Request({"type": "http", "method": "GET", "path": "/nhatky",
                          "query_string": b"", "headers": []})
            moc = server.page_nhatky(yc, ngay="", daydu=0).body.decode("utf-8")
            day_du = server.page_nhatky(yc, ngay="", daydu=1).body.decode("utf-8")
            jobs.bat_nhat_ky_tep(None)                    # đóng tệp trước khi xoá thư mục tạm
        self.assertIn("▶ Tập 99", moc)
        self.assertIn('class="l-loi"', moc)               # dòng lỗi tô đỏ
        self.assertIn("&lt;thử&gt;", moc)
        self.assertNotIn("câu một", moc)                  # mốc chính: ẩn dòng từng đoạn
        self.assertIn("câu một", day_du)

    def test_trang_nhat_ky_khi_chua_co_tep(self):
        yc = Request({"type": "http", "method": "GET", "path": "/nhatky",
                      "query_string": b"", "headers": []})
        html = server.page_nhatky(yc, ngay="", daydu=0).body.decode("utf-8")
        self.assertIn("Chưa có tệp nhật ký nào", html)


if __name__ == "__main__":
    unittest.main()
