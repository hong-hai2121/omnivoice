# -*- coding: utf-8 -*-
"""binhluan_tab.py — Tab 💬 Bình luận YouTube của GUI (26/11/2026).

Khung tkinter nhúng vào amain_taogiong_gui (nút "💬 Bình luận" ở sidebar). Mọi việc thật
(đọc YouTube, Gemini CLI soạn, gửi trả lời) nằm ở YOUTUBE/binh_luan.QuanLy — cùng lõi với
tab 💬 Bình luận của bảng web; ở đây chỉ bấm nút → gọi QuanLy, và hỏi state() định kỳ để
vẽ lại.

Bố cục trải ngang (màn rộng mà thấp): bảng bình luận bên trái · bên phải là bình luận
đang chọn, ô trả lời và các nút.
  ✋ Cần duyệt       — 🤖 Trả lời → câu Gemini soạn hiện ở ô trả lời → 📤 Gửi mới gửi.
  ⚡ Không cần duyệt — 🤖 Trả lời → Gemini soạn xong gửi luôn.
"""
import sys
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import ttk

_YT_DIR = Path(__file__).resolve().parent.parent / "YOUTUBE"
if str(_YT_DIR) not in sys.path:
    sys.path.insert(0, str(_YT_DIR))

import binh_luan as bl   # noqa: E402

_ICON = {"": "•", "xep": "⌛", "soan": "⌛", "duyet": "✋", "gui": "📤", "xong": "✅", "loi": "❌"}
_NHAN = {"": "chưa trả lời", "xep": "chờ Gemini", "soan": "Gemini đang soạn",
         "duyet": "chờ bạn duyệt", "gui": "đang gửi", "xong": "vừa trả lời", "loi": "lỗi"}
_BAN = ("xep", "soan", "gui")


def _mot_dong(s, n=120):
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[:n - 1] + "…"


class BinhLuanPanel(ttk.Frame):
    def __init__(self, parent, quan_ly=None):
        super().__init__(parent, padding=4)
        self.ql = quan_ly or bl.quan_ly()
        cd = bl.doc_cai_dat()
        self.var_che_do = tk.StringVar(value=cd["che_do"])
        self.var_so = tk.StringVar(value=str(cd["so_luong"]))
        self.var_an = tk.BooleanVar(value=cd["an_da_tra_loi"])
        self.var_boqua = tk.BooleanVar(value=cd["bo_qua_emoji"])
        self.var_status = tk.StringVar(value="Chưa lấy danh sách — bấm 📥 Lấy bình luận.")
        self.var_lydo = tk.StringVar(value="")
        self.var_tt = tk.StringVar(value="")
        self._phien = -1
        self._an_cu = None
        self._chon = None            # id bình luận đang chọn
        self._ck_chon = None         # chữ ký trạng thái đã vẽ của bình luận đang chọn
        self._hang = {}              # id → giá trị hàng đã vẽ
        self._ds = {}                # id → bình luận (ảnh chụp gần nhất)
        self._go_tay = {}            # id → chữ người dùng đang gõ dở trong ô trả lời
        self._so_dong_log = 0
        self._job = None
        self._build()
        self.bind("<Map>", lambda e: self._hen(100))
        self.bind("<Destroy>", self._huy)

    # ── dựng giao diện ──
    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        hdr = ttk.Frame(self)
        hdr.grid(row=0, column=0, sticky="ew")
        ttk.Label(hdr, text="💬  Bình luận YouTube", style="Header.TLabel").pack(side="left")
        ttk.Label(hdr, textvariable=self.var_status, style="Sub.TLabel").pack(side="left", padx=(14, 0))

        bar = ttk.Frame(self)
        bar.grid(row=1, column=0, sticky="ew", pady=(6, 8))
        self.btn_tai = ttk.Button(bar, text="📥  Lấy bình luận", style="Accent.TButton",
                                  command=self._tai)
        self.btn_tai.pack(side="left")
        ttk.Label(bar, text="số lượng").pack(side="left", padx=(12, 4))
        ttk.Spinbox(bar, from_=1, to=bl.SO_LUONG_MAX, width=5, textvariable=self.var_so,
                    command=self._luu_so).pack(side="left")
        ttk.Checkbutton(bar, text="Chỉ hiện bình luận CHƯA trả lời", variable=self.var_an,
                        command=self._doi_loc).pack(side="left", padx=(14, 0))
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=14)
        ttk.Label(bar, text="Bấm 🤖 Trả lời thì:").pack(side="left")
        ttk.Radiobutton(bar, text="✋ Cần duyệt (hiện câu trả lời, bấm 📤 Gửi mới gửi)",
                        value="duyet", variable=self.var_che_do,
                        command=self._doi_che_do).pack(side="left", padx=(8, 0))
        ttk.Radiobutton(bar, text="⚡ Không cần duyệt (soạn xong gửi luôn)",
                        value="tu_dong", variable=self.var_che_do,
                        command=self._doi_che_do).pack(side="left", padx=(10, 0))

        pan = ttk.Panedwindow(self, orient="horizontal")
        pan.grid(row=2, column=0, sticky="nsew")

        # ── trái: bảng bình luận ──
        left = ttk.Frame(pan)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)
        cols = ("st", "luc", "tac_gia", "noi_dung", "video")
        tv = ttk.Treeview(left, columns=cols, show="headings", selectmode="browse")
        for c, t, w, st in (("st", "Trạng thái", 125, False), ("luc", "Lúc", 112, False),
                            ("tac_gia", "Người bình luận", 140, False),
                            ("noi_dung", "Bình luận", 280, True), ("video", "Video", 150, True)):
            tv.heading(c, text=t)
            tv.column(c, width=w, anchor="w", stretch=st)
        tv.grid(row=0, column=0, sticky="nsew")
        vs = ttk.Scrollbar(left, orient="vertical", command=tv.yview)
        vs.grid(row=0, column=1, sticky="ns")
        tv.configure(yscrollcommand=vs.set)
        tv.bind("<<TreeviewSelect>>", self._on_chon)
        self.tv = tv
        pan.add(left, weight=1)

        # ── phải: bình luận đang chọn + ô trả lời + nút ──
        right = ttk.Frame(pan, padding=(10, 0, 0, 0))
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        right.rowconfigure(4, weight=1)
        right.rowconfigure(9, weight=1)
        ttk.Label(right, text="Bình luận đang chọn", style="Sub.TLabel").grid(row=0, column=0, sticky="w")
        self.txt_bl = tk.Text(right, height=4, wrap="word", state="disabled", relief="solid", bd=1, font=("Segoe UI", 10))
        self.txt_bl.grid(row=1, column=0, sticky="nsew", pady=(2, 6))
        ttk.Label(right, textvariable=self.var_tt, style="Sub.TLabel",
                  wraplength=520, justify="left").grid(row=2, column=0, sticky="w")
        ttk.Label(right, text="Câu trả lời (Gemini soạn vào đây — sửa được trước khi gửi)",
                  style="Sub.TLabel").grid(row=3, column=0, sticky="w", pady=(4, 0))
        self.txt_tl = tk.Text(right, height=4, wrap="word", relief="solid", bd=1, undo=True, font=("Segoe UI", 10))
        self.txt_tl.grid(row=4, column=0, sticky="nsew", pady=(2, 6))

        btns = ttk.Frame(right)
        btns.grid(row=5, column=0, sticky="ew")
        self.btn_tl = ttk.Button(btns, text="🤖  Trả lời", style="Accent.TButton", command=self._tra_loi)
        self.btn_tl.pack(side="left")
        self.btn_gui = ttk.Button(btns, text="📤  Gửi", command=self._gui)
        self.btn_gui.pack(side="left", padx=(8, 0))
        self.btn_bo = ttk.Button(btns, text="✖  Bỏ nháp", command=self._bo)
        self.btn_bo.pack(side="left", padx=(8, 0))
        self.btn_mo = ttk.Button(btns, text="▶  Xem trên YouTube", command=self._mo)
        self.btn_mo.pack(side="left", padx=(8, 0))
        self.lbl_lydo = tk.Label(right, textvariable=self.var_lydo, fg="#b45309", anchor="w",
                                 justify="left", wraplength=520)
        self.lbl_lydo.grid(row=6, column=0, sticky="w", pady=(4, 6))

        ttk.Checkbutton(right, text="Bỏ qua bình luận chỉ có emoji / mốc giờ (Gemini không trả lời loại này)",
                        variable=self.var_boqua, command=self._doi_boqua).grid(row=7, column=0, sticky="w")
        hd = ttk.Frame(right)
        hd.grid(row=8, column=0, sticky="ew", pady=(4, 0))
        ttk.Label(hd, text="Dặn Gemini trả lời thế nào",
                  style="Sub.TLabel").pack(side="left")
        ttk.Button(hd, text="↺  Về mặc định", command=self._hd_mac_dinh).pack(side="right")
        ttk.Button(hd, text="💾  Lưu câu dặn", command=self._luu_hd).pack(side="right", padx=(0, 6))
        nb = ttk.Panedwindow(right, orient="horizontal")
        nb.grid(row=9, column=0, sticky="nsew", pady=(2, 0))
        self.txt_hd = tk.Text(nb, height=4, width=40, wrap="word", relief="solid", bd=1, undo=True, font=("Segoe UI", 10))
        self.txt_hd.insert("1.0", bl.doc_cai_dat()["huong_dan"])
        nb.add(self.txt_hd, weight=1)
        self.txt_log = tk.Text(nb, height=4, width=40, wrap="word", state="disabled",
                               relief="solid", bd=1, fg="#555", font=("Segoe UI", 9))
        nb.add(self.txt_log, weight=1)
        pan.add(right, weight=1)
        self._ve_nut()

    # ── vòng hỏi trạng thái ──
    def _hen(self, ms):
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
        self._job = self.after(ms, self._tick)

    def _huy(self, e=None):
        if e is not None and e.widget is not self:
            return
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
            self._job = None

    def _tick(self):
        self._job = None
        if not self.winfo_exists():
            return
        if not self.winfo_ismapped():        # tab đang ẩn: thôi hỏi, <Map> sẽ gọi lại
            return
        try:
            s = self.ql.state()
            self._ve(s)
        except Exception as e:
            self.var_status.set(f"Lỗi vẽ tab bình luận: {e}")
            s = {"ban": False}
        self._hen(700 if s.get("ban") else 2500)

    def lam_moi(self):
        """Gọi khi mở tab (amain_taogiong_gui._show_view)."""
        self._hen(50)

    # ── vẽ ──
    def _gia_tri_hang(self, c):
        tt = c.get("tt") or ""
        if c["da_tra_loi"]:
            st = "✅ " + ("vừa trả lời" if tt == "xong" else "đã trả lời")
        else:
            st = f"{_ICON.get(tt, '•')} {_NHAN.get(tt, tt)}"
        return (st, c["luc"], c["tac_gia"], _mot_dong(c["noi_dung"]), _mot_dong(c["video"] or c["video_id"], 60))

    def _ve(self, s):
        kenh = s["kenh"].get("title", "")
        if s["dang_tai"]:
            self.var_status.set("⌛ Đang lấy bình luận…")
        elif s["loi"]:
            self.var_status.set("❌ " + s["loi"])
        elif s["tong"]:
            self.var_status.set(f"Kênh {kenh} · {s['tong']} bình luận · {s['chua_tra_loi']} chưa trả lời"
                                f" · lấy lúc {s['tai_luc']}")
        self.btn_tai.configure(state="disabled" if s["dang_tai"] else "normal",
                               text="🔄  Lấy lại bình luận" if s["tong"] else "📥  Lấy bình luận")

        loc = self.var_an.get()
        hien = [c for c in s["ds"] if not loc or not c["da_tra_loi"] or c.get("tt") == "xong"]
        self._ds = {c["id"]: c for c in s["ds"]}
        if s["phien"] != self._phien or loc != self._an_cu:
            self._phien, self._an_cu = s["phien"], loc
            self.tv.delete(*self.tv.get_children())
            self._hang = {}
        con = {c["id"] for c in hien}
        for cid in [i for i in self._hang if i not in con]:
            if self.tv.exists(cid):
                self.tv.delete(cid)
            del self._hang[cid]
        for c in hien:
            gt = self._gia_tri_hang(c)
            if c["id"] not in self._hang:
                self.tv.insert("", "end", iid=c["id"], values=gt)
            elif self._hang[c["id"]] != gt:
                self.tv.item(c["id"], values=gt)
            self._hang[c["id"]] = gt
        if self._chon and self._chon not in self._hang:
            self._chon, self._ck_chon = None, None
            self._dat_text(self.txt_bl, "")
            self.txt_tl.delete("1.0", "end")
        self._ve_chon()

        if len(s["lines"]) != self._so_dong_log or (s["lines"] and self._so_dong_log == bl.MAX_LINES):
            self._so_dong_log = len(s["lines"])
            self._dat_text(self.txt_log, "\n".join(s["lines"]))
            self.txt_log.see("end")

    @staticmethod
    def _dat_text(w, text):
        w.configure(state="normal")
        w.delete("1.0", "end")
        w.insert("1.0", text)
        w.configure(state="disabled")

    def _ve_chon(self, ep=False):
        """Vẽ lại khung bên phải khi trạng thái của bình luận đang chọn đổi."""
        c = self._ds.get(self._chon) if self._chon else None
        ck = None if c is None else (c["id"], c.get("tt") or "", c.get("nhap") or "", c.get("loi") or "",
                                     c["da_tra_loi"], c.get("tra_loi_cua_kenh") or "")
        if ck == self._ck_chon and not ep:
            self._ve_nut()
            return
        self._ck_chon = ck
        if c is None:
            self.var_tt.set("")
            self._ve_nut()
            return
        self._dat_text(self.txt_bl, f"{c['tac_gia']} · {c['luc']}"
                       + (f" · 👍 {c['thich']}" if c["thich"] else "")
                       + f"\n▶ {c['video'] or c['video_id']}\n\n{c['noi_dung']}")
        tt = c.get("tt") or ""
        self.txt_tl.configure(state="normal")
        if c["da_tra_loi"]:
            noi = c.get("tra_loi_cua_kenh") or ""
            self.var_tt.set("✅ Kênh đã trả lời bình luận này:")
        elif tt in _BAN:
            noi = c.get("nhap") or ""
            self.var_tt.set("⌛ Đang gửi lên YouTube…" if tt == "gui" else
                            "⌛ Gemini CLI đang soạn câu trả lời… (thường 5–30 s) — "
                            + ("soạn xong sẽ GỬI LUÔN." if c.get("che_do") == "tu_dong"
                               else "soạn xong sẽ hiện ở ô dưới để bạn duyệt."))
        elif tt == "duyet":
            noi = c.get("nhap") or ""
            self._go_tay.pop(c["id"], None)
            self.var_tt.set("✋ Gemini đã soạn — đọc, sửa nếu cần rồi bấm 📤 Gửi.")
        elif tt == "loi":
            noi = c.get("nhap") or self._go_tay.get(c["id"], "")
            self.var_tt.set("❌ " + (c.get("loi") or "lỗi"))
        else:
            noi = self._go_tay.get(c["id"], "")
            self.var_tt.set("Chưa trả lời — bấm 🤖 Trả lời để Gemini soạn, hoặc tự gõ rồi bấm 📤 Gửi.")
        self.txt_tl.delete("1.0", "end")
        self.txt_tl.insert("1.0", noi)
        if c["da_tra_loi"] or tt in _BAN:
            self.txt_tl.configure(state="disabled")
        self._ve_nut()

    def _ve_nut(self):
        """Bật/tắt nút; nút bị khoá thì dòng cam bên dưới nói rõ vì sao."""
        c = self._ds.get(self._chon) if self._chon else None
        tu_dong = self.var_che_do.get() == "tu_dong"
        tt = (c or {}).get("tt") or ""
        self.btn_tl.configure(text="🔁  Soạn lại" if tt == "duyet"
                              else "🤖  Trả lời (gửi luôn)" if tu_dong else "🤖  Trả lời")
        if c is None:
            ly_do = "Chưa chọn bình luận — bấm một dòng ở bảng bên trái." if self._hang else \
                    "Bảng đang trống — bấm 📥 Lấy bình luận ở phía trên."
            khoa_tl = khoa_gui = True
        elif c["da_tra_loi"]:
            ly_do, khoa_tl, khoa_gui = "Kênh đã trả lời bình luận này nên không trả lời nữa.", True, True
        elif tt in _BAN:
            ly_do, khoa_tl, khoa_gui = "Đang xử lý bình luận này — đợi xong đã.", True, True
        elif c.get("chi_emoji") and self.var_boqua.get() and tt != "duyet":
            khoa_tl, khoa_gui = True, False
            ly_do = ("🚫 Bình luận chỉ có emoji / mốc giờ nên Gemini bỏ qua (máy đáp vào là lộ giả). "
                     "Muốn đáp thì tự gõ rồi bấm 📤 Gửi, hoặc bỏ tick ô “Bỏ qua…” bên dưới.")
        else:
            khoa_tl = khoa_gui = False
            ly_do = ("⚡ Không cần duyệt: bấm 🤖 Trả lời là câu Gemini soạn được đăng công khai ngay."
                     if tu_dong else "")
        self.btn_tl.configure(state="disabled" if khoa_tl else "normal")
        self.btn_gui.configure(state="disabled" if khoa_gui else "normal",
                               style="Accent.TButton" if tt == "duyet" else "TButton")
        self.btn_bo.configure(state="normal" if tt in ("duyet", "loi") else "disabled")
        self.btn_mo.configure(state="normal" if c else "disabled")
        self.var_lydo.set(ly_do)

    # ── nút bấm ──
    def _bao(self, msg):
        self.var_lydo.set("❌ " + msg)

    def _nho_go_tay(self):
        """Giữ chữ đang gõ dở của bình luận đang chọn trước khi đổi dòng / vẽ lại."""
        c = self._ds.get(self._chon) if self._chon else None
        if c is not None and not c["da_tra_loi"] and (c.get("tt") or "") in ("", "loi"):
            t = self.txt_tl.get("1.0", "end").strip()
            if t:
                self._go_tay[c["id"]] = t
            else:
                self._go_tay.pop(c["id"], None)

    def _on_chon(self, _e=None):
        sel = self.tv.selection()
        moi = sel[0] if sel else None
        if moi == self._chon:
            return
        self._nho_go_tay()
        self._chon = moi
        self._ve_chon(ep=True)

    def _tai(self):
        self._luu_so()
        self.ql.tai()
        self.var_status.set("⌛ Đang lấy bình luận…")
        self._hen(200)

    def _luu_so(self):
        try:
            bl.luu_cai_dat(so_luong=int(self.var_so.get()))
        except (ValueError, OSError):
            pass

    def _doi_loc(self):
        try:
            bl.luu_cai_dat(an_da_tra_loi=self.var_an.get())
        except OSError:
            pass
        self._hen(10)

    def _doi_boqua(self):
        try:
            bl.luu_cai_dat(bo_qua_emoji=self.var_boqua.get())
        except OSError:
            pass
        self._ve_nut()

    def _doi_che_do(self):
        try:
            bl.luu_cai_dat(che_do=self.var_che_do.get())
        except OSError:
            pass
        self._ve_nut()

    def _luu_hd(self):
        try:
            cd = bl.luu_cai_dat(huong_dan=self.txt_hd.get("1.0", "end"))
        except OSError as e:
            self._bao(f"Không lưu được câu dặn: {e}")
            return
        self.txt_hd.delete("1.0", "end")
        self.txt_hd.insert("1.0", cd["huong_dan"])
        self.var_lydo.set("✓ Đã lưu câu dặn Gemini.")

    def _hd_mac_dinh(self):
        self.txt_hd.delete("1.0", "end")
        self.txt_hd.insert("1.0", bl.HUONG_DAN_MAC_DINH)
        self._luu_hd()

    def _tra_loi(self):
        if not self._chon:
            return
        try:
            bl.luu_cai_dat(huong_dan=self.txt_hd.get("1.0", "end"))   # dùng đúng câu dặn đang hiện
            self.ql.tra_loi(self._chon, self.var_che_do.get())
        except (bl.BinhLuanError, OSError) as e:
            self._bao(str(e))
            return
        self._hen(50)

    def _gui(self):
        if not self._chon:
            return
        try:
            self.ql.gui(self._chon, self.txt_tl.get("1.0", "end"))
        except bl.BinhLuanError as e:
            self._bao(str(e))
            return
        self._go_tay.pop(self._chon, None)
        self._hen(50)

    def _bo(self):
        if self._chon:
            self.ql.bo(self._chon)
            self._go_tay.pop(self._chon, None)
            self._hen(10)

    def _mo(self):
        c = self._ds.get(self._chon) if self._chon else None
        if c:
            webbrowser.open(f"https://www.youtube.com/watch?v={c['video_id']}&lc={c['id']}")
