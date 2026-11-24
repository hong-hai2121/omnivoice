# -*- coding: utf-8 -*-
"""Cắt dòng phụ đề ở bước ① (myvideo/video_chamlai_srt.py) khi Whisper KHÔNG chấm câu.

Lỗi gốc (18/11/2026, bài 85 phút tiếng Trung chỉ có 98 dấu câu trên 11.738 chữ):
build_subs đếm đủ 16 chữ là cắt, nên chữ cuối câu này rơi sang đầu câu kia
("否则魂 / 飞魄散"), bước ② dịch và bước ③ đọc đúng những mẩu lệch đó. Whisper vẫn
tách đúng từng vế thành một segment — các test này giữ cho ranh giới ấy được dùng:
cờ hết_vế, chữ lạc quanh chỗ nghỉ, từ nối / lời dẫn không nằm cuối dòng, vế dài
chia cân, và bước ② gộp dòng không làm mất ranh giới vế."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "myvideo"))
import video_chamlai_srt as v  # noqa: E402
import dich_srt  # noqa: E402

CHU = 0.25      # mỗi chữ dài 0,25 s


def chu(*ve, t0=0.0, khe=None, lang="zh", co=2):
    """Dựng danh sách [start, end, chữ, hết_vế] từ các vế. Trung: mỗi chữ Hán một
    token (dấu câu dính vào chữ trước); Anh: mỗi từ một token. khe = {chỉ số vế:
    giây nghỉ TRƯỚC vế đó}. co = cờ ở chữ cuối mỗi vế: 2 = ranh giới vế thật
    (nhận diện không ngữ cảnh), 1 = chỗ Whisper ngắt segment lúc có ngữ cảnh."""
    out, t = [], t0
    for k, vế in enumerate(ve):
        t += (khe or {}).get(k, 0.0)
        if lang == "zh":
            toks = []
            for c in vế:
                if toks and not c.isalnum():
                    toks[-1] += c
                else:
                    toks.append(c)
        else:
            toks = vế.split()
        for j, tok in enumerate(toks):
            out.append([round(t, 3), round(t + CHU, 3), tok, co if j == len(toks) - 1 else 0])
            t += CHU
    return out


def dong(subs):
    return [s[2] for s in subs]


class KhongDauCauTests(unittest.TestCase):
    VE = ("为我祭炼轮回", "是为众生何错之有", "错在你", "月祖代袍", "轮迴自有天道才诀",
          "交出生死簿", "否则", "休怪我等不客气")

    def test_dong_chi_cat_o_ranh_gioi_ve(self):
        subs = v.build_subs(chu(*self.VE), lang="zh")
        for d in dong(subs):
            self.assertLessEqual(v._nchars(d, "zh"), 16)
            for manh in d.split(" "):                 # mỗi mảnh là một vế nguyên vẹn
                self.assertIn(manh, self.VE, d)
        self.assertEqual(" ".join(dong(subs)), " ".join(self.VE))   # không mất, không lặp chữ

    def test_ban_cu_khong_co_thi_cat_cung_16_chu(self):
        """Đối chứng: bỏ cờ hết_vế thì đúng là lỗi cũ — và main() phải nhận ra để nhận diện lại."""
        cu = [w[:3] for w in chu(*self.VE)]
        self.assertFalse(v.co_ranh_gioi(cu))
        self.assertTrue(v.co_ranh_gioi(chu(*self.VE)))
        d = dong(v.build_subs(cu, lang="zh"))
        self.assertEqual(d[0], "为我祭炼轮回是为众生何错之有错在")       # cắt giữa "错在你"

    def test_tu_noi_khong_nam_cuoi_dong(self):
        d = dong(v.build_subs(chu("直向点", "将生死部交于道祖", "否则", "魂飞魄散", "红军", "原来是你"),
                              lang="zh"))
        self.assertEqual(d[0], "直向点 将生死部交于道祖")
        self.assertTrue(d[1].startswith("否则 魂飞魄散"), d)

    def test_loi_dan_ngan_di_voi_cau_sau(self):
        d = dong(v.build_subs(chu("能为三十四效力", "是卑职的荣幸", "好了", "你就别再谦虚了"), lang="zh"))
        self.assertEqual(d, ["能为三十四效力 是卑职的荣幸", "好了 你就别再谦虚了"])

    def test_nghi_dai_thi_chot_dong(self):
        subs = v.build_subs(chu("既然轮迴已开", "那我便", khe={1: 1.0}), lang="zh")
        self.assertEqual(dong(subs), ["既然轮迴已开", "那我便"])
        self.assertAlmostEqual(subs[1][0] - subs[0][1], 1.0, places=2)

    def test_co_dau_cau_thi_nhu_cu(self):
        d = dong(v.build_subs(chu("轮迴乃天道致命,非你可擅自祭炼。", "巫妖大战,生灵涂炭,亿万冤魂无归。"), lang="zh"))
        self.assertEqual(d, ["轮迴乃天道致命,非你可擅自祭炼。", "巫妖大战,生灵涂炭,亿万冤魂无归。"])

    def test_co_dau_cau_thi_cat_o_dau_cau_chu_khong_o_cho_ngat_tam(self):
        """Nghe theo ngữ cảnh, Whisper ngắt segment giữa cụm "当个 | 鬼差" (cờ 1): đó là
        chỗ yếu — cắt ở dấu phẩy trước nó, và không chèn khoảng trắng vào giữa cụm."""
        d = dong(v.build_subs(chu("苏藩啊,你很有才能,在这三十三司当个", "鬼差,有点委屈你了。", co=1), lang="zh"))
        self.assertEqual(d, ["苏藩啊,你很有才能,", "在这三十三司当个鬼差,有点委屈你了。"])

    def test_loi_goi_ngan_nhap_vao_cau_sau(self):
        """"陆冈, ‖nghỉ 0,9 s‖ 他便是你说的苏凡。" — lời gọi thuộc câu sau, không đứng riêng
        và không dính ngược vào câu trước đã hết."""
        d = dong(v.build_subs(chu("谢二位神君。", "陆冈,", "他便是你说的苏凡。", khe={2: 0.9}, co=1), lang="zh"))
        self.assertEqual(d, ["谢二位神君。", "陆冈,他便是你说的苏凡。"])


class KhongGioiHanTests(unittest.TestCase):
    """max_chars = 0 (mặc định tiếng Trung từ 18/11/2026): bỏ trần 16 chữ, mỗi dòng
    SRT là một câu trọn — chỉ chốt ở dấu hết câu hoặc chỗ nghỉ."""

    def test_moi_dong_mot_cau_tron(self):
        ve = ("如今我勾魂十九司司君之位空缺三个月了,", "我已经向长司举荐了你,", "等下,随我去见长司。",
              "十九司司君?")
        d = dong(v.build_subs(chu(*ve, co=1), max_chars=0, lang="zh"))
        self.assertEqual(d, ["如今我勾魂十九司司君之位空缺三个月了,我已经向长司举荐了你,等下,随我去见长司。",
                             "十九司司君?"])
        # Đối chứng: trần 16 thì câu đầu bị bẻ, có chỗ chia giữa vế.
        self.assertGreater(len(v.build_subs(chu(*ve, co=1), max_chars=16, hard_max=16, lang="zh")), 3)

    def test_cho_nghi_van_chot_dong(self):
        d = dong(v.build_subs(chu("既然轮迴已开,", "那我便...", khe={1: 1.6}, co=1), max_chars=0, lang="zh"))
        self.assertEqual(d, ["既然轮迴已开,", "那我便..."])

    def test_khuc_khong_dau_cau_van_co_tran_va_cat_o_het_ve(self):
        ve = ("这小怪才成为鬼差半个月", "竟然已经修炼到鬼杀境界了", "他的鬼神七灾", "竟然修练到了第二灾",
              "苏凡兄弟", "多有得罪", "我们这就离去")
        d = dong(v.build_subs(chu(*ve), max_chars=0, lang="zh"))
        self.assertGreater(len(d), 1)                       # không chạy thành một dòng 55 chữ
        self.assertEqual(" ".join(d), " ".join(ve))
        for x in d:
            self.assertLess(v._nchars(x, "zh"), 50)
            for manh in x.split(" "):
                self.assertIn(manh, ve, d)                   # chỉ cắt ở ranh giới vế

    def test_cau_qua_dai_cat_o_dau_phay(self):
        cau = "当年见你之时,便知你与我教有缘," * 5 + "所以只能减去你一些寿元。"       # 86 chữ, một câu
        d = dong(v.build_subs(chu(cau, co=1), max_chars=0, lang="zh"))
        self.assertEqual("".join(d), cau)
        self.assertGreater(len(d), 1)
        for x in d[:-1]:
            self.assertLessEqual(v._nchars(x, "zh"), 70)
            self.assertEqual(x[-1], ",")

    def _chay_main(self, *them):
        """Chạy main() thật trên mốc giờ đã lưu sẵn (không nhận diện, không render)."""
        import json
        import tempfile
        ve = ("如今我勾魂十九司司君之位空缺三个月了,", "我已经向长司举荐了你。")
        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp) / "bai.mp4"
            media.write_bytes(b"")
            (Path(tmp) / "bai_x0.7_words.json").write_text(
                json.dumps(chu(*ve, co=1), ensure_ascii=False), encoding="utf-8")
            argv = ["video_chamlai_srt.py", str(media), "--no-video", "--no-dich",
                    "--out-dir", tmp, *them]
            with patch.object(sys, "argv", argv):
                v.main()
            return [c[1] for c in dich_srt.parse_srt(str(Path(tmp) / "bai_x0.7.srt"))]

    def test_main_mac_dinh_tieng_trung_khong_gioi_han(self):
        self.assertEqual(self._chay_main(), ["如今我勾魂十九司司君之位空缺三个月了,我已经向长司举荐了你。"])

    def test_main_so_0_tu_trang_web_la_khong_gioi_han_chu_khong_roi_ve_16(self):
        """Trang web gửi --max-chars 0 --hard-max 0."""
        self.assertEqual(self._chay_main("--max-chars", "0", "--hard-max", "0"),
                         ["如今我勾魂十九司司君之位空缺三个月了,我已经向长司举荐了你。"])

    def test_main_van_ep_duoc_16_chu_neu_muon(self):
        d = self._chay_main("--max-chars", "16", "--hard-max", "16")
        self.assertGreater(len(d), 1)
        for x in d:
            self.assertLessEqual(v._nchars(x, "zh"), 16)


class TrangWebTranDongTests(unittest.TestCase):
    """Ô "số chữ tối đa/dòng SRT" trên trang: 0 = không giới hạn và phải tới được script."""

    @classmethod
    def setUpClass(cls):
        import threading
        if str(REPO) not in sys.path:
            sys.path.insert(0, str(REPO))
        with patch.object(threading.Thread, "start", lambda self: None):   # không bật luồng nền
            from myvideo.web import steps, server
        cls.st, cls.sv = steps, server

    def test_o_nhap_giu_duoc_so_0(self):
        sv = self.sv
        self.assertEqual(sv.DEFAULTS["maxchars"], "0")
        self.assertEqual(sv._tran_dong("0", 4, 60, 0), "0")
        self.assertEqual(sv._tran_dong("", 4, 60, 0), "0")        # ô trống → mặc định không giới hạn
        self.assertEqual(sv._tran_dong("16", 4, 60, 0), "16")
        self.assertEqual(sv._tran_dong("2", 4, 60, 0), "4")
        self.assertEqual(sv._tran_dong("abc", 10, 120, 42), "42")
        html = (REPO / "myvideo" / "web" / "templates" / "index.html").read_text(encoding="utf-8")
        self.assertRegex(html, r'name="maxchars" type="number" min="0"')

    def test_buoc_1_gui_so_0_cho_script(self):
        s = dict(self.sv.DEFAULTS, lang="zh")
        buoc = self.st._steps_for(["cham"], "x.mp4", REPO / "myvideo" / "output" / "x" / "x_x0.7", s)
        argv = buoc[0].argv
        self.assertEqual(argv[argv.index("--max-chars") + 1], "0")
        self.assertEqual(argv[argv.index("--hard-max") + 1], "0")
        self.assertNotIn("--khong-ngu-canh", argv)          # ô ngữ cảnh mặc định bật


class ChuLacTests(unittest.TestCase):
    def test_chu_dau_ve_bi_dan_truoc_cho_nghi(self):
        """"那我便 | 你们 ‖17 s‖ 四人": Whisper ghi giờ "你们" sát câu trước."""
        w = chu("那我便", "你们四人", "速来紫霄宫见我")
        for x in w[5:]:                    # từ chữ "四" trở đi lùi 17 s
            x[0] += 17.0
            x[1] += 17.0
        sua, n = v.sua_chu_lac(w)
        self.assertEqual(n, 2)
        self.assertGreater(sua[3][0], 17.0)                    # "你" đã sang sau chỗ nghỉ
        self.assertAlmostEqual(sua[4][1], sua[5][0], places=3)   # "们" sát trước "四"
        subs = v.build_subs(w, lang="zh")
        self.assertEqual(dong(subs), ["那我便", "你们四人 速来紫霄宫见我"])
        self.assertGreater(subs[1][0], 17.0)      # phụ đề (và giọng đọc) không vào sớm 17 s
        self.assertLess(subs[0][1], 1.0)

    def test_chu_cuoi_ve_bi_day_sau_cho_nghi(self):
        w = chu("不得进入其他区域", "隆儿你放心")
        for x in w[7:]:                    # chữ "域" và vế sau lùi 1,6 s
            x[0] += 1.6
            x[1] += 1.6
        subs = v.build_subs(w, lang="zh")
        self.assertEqual(dong(subs)[0], "不得进入其他区域")

    def test_chu_keo_dai_bat_thuong(self):
        w = chu("苏凡", "来大殿一趟")
        w[2][0] -= 20.0                    # "来" bị ghi dài 20 s (nuốt quãng nhạc trước nó)
        w[0][0] -= 20.0; w[0][1] -= 20.0
        w[1][0] -= 20.0; w[1][1] -= 20.0
        subs = v.build_subs(w, lang="zh")
        self.assertEqual(dong(subs), ["苏凡", "来大殿一趟"])
        self.assertLess(subs[1][1] - subs[1][0], 3.0)


class VeDaiTests(unittest.TestCase):
    def test_ve_dai_hon_dong_chia_can_khong_rot_duoi(self):
        ve = "你给那鬼差准备的宝物难道没有送出去"                  # 17 chữ, không có chỗ cắt
        d = dong(v.build_subs(chu(ve, "李道長"), lang="zh"))
        self.assertEqual("".join(d).replace(" ", ""), ve + "李道長")
        self.assertGreaterEqual(v._nchars(d[0], "zh"), 4)
        self.assertGreaterEqual(v._nchars(d[1].split(" ")[0], "zh"), 4)   # không còn mẩu "去" cụt
        for x in d:
            self.assertLessEqual(v._nchars(x, "zh"), 16)

    def test_chia_o_cho_nguoi_noi_ngung(self):
        w = chu("恐怕我西方教也唯有那几位圣驼才能与之抗衡")              # 20 chữ
        w[6][1] += 0.6                     # chữ "也" kéo dài = có nhịp ngừng trước nó
        for x in w[7:]:
            x[0] += 0.6
            x[1] += 0.6
        d = dong(v.build_subs(w, lang="zh"))
        self.assertEqual(d, ["恐怕我西方教", "也唯有那几位圣驼才能与之抗衡"])

    def test_tu_noi_di_cung_nua_dau_cua_ve_dai(self):
        d = dong(v.build_subs(chu("乃是卑职手下唯一没有漏魂之人", "因此", "卑职认为他有能力担当十九司司君之位"),
                              lang="zh"))
        self.assertEqual(d[0], "乃是卑职手下唯一没有漏魂之人")
        self.assertTrue(d[1].startswith("因此 卑职"), d)


class TiengAnhTests(unittest.TestCase):
    def test_khong_dau_cau_cat_theo_ve_va_khong_ket_bang_tu_noi(self):
        ve = ("this way you can scale smarter and", "not waste your money so",
              "if you ever felt like you were guessing")
        d = dong(v.build_subs(chu(*ve, lang="en"), max_chars=42, hard_max=42, min_chars=10,
                              lang="en"))             # ngưỡng tiếng Anh như main() truyền
        self.assertEqual(" ".join(d), " ".join(ve))
        for x in d:
            self.assertLessEqual(len(x), 42)
            self.assertNotIn(x.split()[-1], ("and", "so"), d)
        self.assertEqual(d[0], "this way you can scale smarter")


def _W(s, e, t):
    return SimpleNamespace(start=s, end=e, word=t)


def _seg(s, e, text, words=None):
    return SimpleNamespace(start=s, end=e, text=text, words=words)


class NhanDienTests(unittest.TestCase):
    def _chay(self, transcribe, audio=None, **kw):
        """transcribe_words với model giả; audio = mảng mẫu giả cho đường theo khúc."""
        import numpy as np
        model = SimpleNamespace(transcribe=transcribe)
        with patch.object(v, "get_model", return_value=(model, None, "cpu")), \
                patch.object(v, "get_audio_duration", return_value=3.0), \
                patch("faster_whisper.decode_audio",
                      return_value=np.zeros(48000, dtype="float32") if audio is None else audio):
            return v.transcribe_words("x.wav", lang="zh", **kw)

    def test_transcribe_words_ghi_co_het_ve(self):
        segs = [_seg(0, 1, "错在你", [_W(0, .3, "错"), _W(.3, .6, "在"), _W(.6, 1, "你")]),
                _seg(1, 2, "月祖代袍", [_W(1, 1.5, "月祖"), _W(1.5, 2, "代袍")]),
                _seg(2, 3, "否则", None)]
        words = self._chay(lambda *a, **k: (iter(segs), None), khong_ngu_canh=True)
        self.assertEqual([w[2] for w in words], ["错", "在", "你", "月祖", "代袍", "否则"])
        self.assertEqual([w[3] for w in words], [0, 0, 2, 0, 2, 2])    # không ngữ cảnh: vế thật
        self.assertTrue(v.co_ranh_gioi(words))

    def test_tieng_trung_mac_dinh_nghe_theo_ngu_canh_va_bo_cau_mau_bi_chep_lai(self):
        thay = []

        def transcribe(audio, **opts):
            thay.append(opts)
            return iter([_seg(0, 1, "请用简体中文加上标点符号。", [_W(0, 1, "请用简体中文加上标点符号。")]),
                         _seg(1, 2, "道何依?", [_W(1, 1.5, "道何"), _W(1.5, 2, "依?")])]), None
        words = self._chay(transcribe)
        self.assertTrue(thay[0]["condition_on_previous_text"])
        self.assertIn("标点符号", thay[0]["initial_prompt"])
        # Chép câu mẫu = ngữ cảnh đã bẩn → chạy lại khúc không lời mồi, không ngữ cảnh.
        self.assertEqual(len(thay), 2)
        self.assertIsNone(thay[1]["initial_prompt"])
        self.assertFalse(thay[1]["condition_on_previous_text"])
        self.assertEqual([w[2] for w in words], ["道何", "依?"])      # câu mẫu bị chép lại đã bỏ
        self.assertEqual([w[3] for w in words], [0, 2])

    def test_moi_khuc_mot_luot_moi_bang_duoi_khuc_truoc(self):
        import numpy as np
        audio = np.zeros(int(13 * 60 * v._SR), dtype="float32")          # 13 phút
        # tiếng nói 0–5'10", im tới 5'20", nói tới 10'30", im tới 10'50", nói tới hết
        noi = [{"start": 0, "end": 310 * v._SR}, {"start": 320 * v._SR, "end": 630 * v._SR},
               {"start": 650 * v._SR, "end": 780 * v._SR}]
        goi = []

        def transcribe(a, **opts):
            goi.append((len(a) / v._SR, opts["initial_prompt"]))
            k = len(goi)
            cau = f"这是第{k}段的最后一句话。"
            segs = [_seg(1, 2, cau, [_W(1, 2, cau)])]
            if k == 2:      # Whisper đọc lại câu cuối của lời mồi rồi mới vào lời thật
                segs.insert(0, _seg(0, 1, "这是第1段的最后一句话。", [_W(0, 1, "这是第1段的最后一句话。")]))
            return iter(segs), None
        with patch("faster_whisper.vad.get_speech_timestamps", return_value=noi):
            words = self._chay(transcribe, audio=audio)
        self.assertEqual([round(x[0]) for x in goi], [315, 325, 140])   # cắt giữa hai quãng im
        self.assertIn("标点符号", goi[0][1])                           # khúc đầu: câu mẫu
        self.assertEqual(goi[1][1], "这是第1段的最后一句话。")            # khúc sau: đuôi khúc trước
        self.assertEqual(goi[2][1], "这是第2段的最后一句话。")
        self.assertEqual([w[2] for w in words],                       # câu bị đọc lại đã bỏ
                         ["这是第1段的最后一句话。", "这是第2段的最后一句话。", "这是第3段的最后一句话。"])
        self.assertEqual([w[0] for w in words], [1.0, 316.0, 641.0])   # mốc giờ theo cả bài
        self.assertEqual([w[3] for w in words], [1, 1, 1])             # có ngữ cảnh: chỗ ngắt yếu

    def test_khuc_kho_dau_thi_chay_lai_khong_ngu_canh(self):
        kho = "".join("我们去吃饭吧" for _ in range(20))               # 120 chữ không dấu câu

        def transcribe(a, **opts):
            if opts["condition_on_previous_text"]:
                return iter([_seg(0, 9, kho, [_W(i * .07, i * .07 + .07, c) for i, c in enumerate(kho)])]), None
            return iter([_seg(0, 1, "我们去", [_W(0, 1, "我们去")]), _seg(1, 2, "吃饭吧", [_W(1, 2, "吃饭吧")])]), None
        words = self._chay(transcribe)
        self.assertEqual([w[2] for w in words], ["我们去", "吃饭吧"])
        self.assertEqual([w[3] for w in words], [2, 2])

    def test_khuc_nuot_loi_thi_chay_lai(self):
        """193 giây có tiếng nói mà chỉ ra vài chữ = Whisper nuốt lời (đo thật: 632 → 17 chữ)."""
        day_du = "这年头我地府算是废了。" * 30

        def transcribe(a, **opts):
            info = SimpleNamespace(duration_after_vad=193.0)
            if opts["condition_on_previous_text"]:
                return iter([_seg(0, 1, "不知好歹。", [_W(0, 1, "不知好歹。")])]), info
            return iter([_seg(0, 190, day_du, [_W(0, 190, day_du)])]), info
        words = self._chay(transcribe)
        self.assertEqual(words[0][2], day_du)


class GopCauTests(unittest.TestCase):
    def test_gop_dong_trung_giu_khoang_trang_giua_ve(self):
        cues = [("00:00:01,000 --> 00:00:03,000", "为我祭炼轮回 是为众生何错之有"),
                ("00:00:03,000 --> 00:00:06,000", "错在你 月祖代袍"),
                ("00:00:06,600 --> 00:00:08,000", "那我便")]
        cau = dich_srt.gop_cau(cues, "zh")
        self.assertEqual([t for _, t in cau], ["为我祭炼轮回 是为众生何错之有 错在你 月祖代袍", "那我便"])
        self.assertEqual(cau[0][0], "00:00:01,000 --> 00:00:06,000")

    def test_dong_co_dau_cau_bi_cat_giua_ve_thi_noi_lien(self):
        """Cùng file có khúc không dấu (cách vế bằng khoảng trắng) và khúc có dấu: dòng
        có dấu câu bị cắt giữa vế cho vừa bề ngang phải nối LIỀN, không chèn khoảng trắng."""
        cues = [("00:00:01,000 --> 00:00:03,000", "错在你 月祖代袍"),
                ("00:00:05,000 --> 00:00:07,000", "如今我勾魂十九司司"),
                ("00:00:07,000 --> 00:00:09,000", "君之位空缺三个月了,"),
                ("00:00:09,000 --> 00:00:11,000", "我已经向长司举荐了你。")]
        self.assertEqual([t for _, t in dich_srt.gop_cau(cues, "zh")],
                         ["错在你 月祖代袍", "如今我勾魂十九司司君之位空缺三个月了,我已经向长司举荐了你。"])

    def test_srt_cu_viet_lien_thi_van_noi_lien(self):
        cues = [("00:00:01,000 --> 00:00:03,000", "否则魂"), ("00:00:03,000 --> 00:00:05,000", "飞魄散。")]
        self.assertEqual([t for _, t in dich_srt.gop_cau(cues, "zh")], ["否则魂飞魄散。"])

    def test_cho_nghi_buoc_1_da_chot_thi_buoc_2_cung_tach(self):
        """Chỗ nghỉ 0,7 s giữa hai chữ → bước ① chốt dòng, nới đuôi 0,2 s còn 0,5 s trong SRT."""
        subs = v.pad_ends(v.build_subs(chu("走过去看看", "说不定能挑几个当鬼差", khe={1: v.KHE_CHOT}), lang="zh"))
        cues = [(f"{v._fmt_srt_time(s[0])} --> {v._fmt_srt_time(s[1])}", s[2]) for s in subs]
        self.assertEqual(len(cues), 2)
        self.assertEqual(len(dich_srt.gop_cau(cues, "zh")), 2)


class OTickTrenTrangTests(unittest.TestCase):
    """Server đọc ô tick vắng mặt = TẮT. Ô "ngucanh" (Whisper chấm câu) và "gopcau"
    (gộp dòng thành câu) từng rơi khỏi index.html trong một lần sửa giao diện —
    từ đó mọi lượt chạy đều ngầm tắt cả hai mà trang không còn chỗ nào để bật."""

    def test_moi_o_tick_server_doc_deu_co_tren_trang(self):
        import re
        web = REPO / "myvideo" / "web"
        src = (web / "server.py").read_text(encoding="utf-8")
        than = re.search(r"def _settings_from_form\(form\).*?\n    return ", src, re.S).group(0)
        o_tick = set(re.findall(r'bool\(g\("(\w+)"\)\)', than))
        self.assertIn("ngucanh", o_tick)
        self.assertIn("gopcau", o_tick)
        html = "\n".join(p.read_text(encoding="utf-8") for p in (web / "templates").glob("*.html"))
        co = set(re.findall(r'type="checkbox"\s+name="(\w+)"', html))
        self.assertEqual(sorted(o_tick - co), [])


if __name__ == "__main__":
    unittest.main()
