# -*- coding: utf-8 -*-
"""
web_tiktok.py — Bảng điều khiển WEB cho bộ đăng TikTok (FastAPI, chạy tại chỗ).

Đây là CHỨC NĂNG RIÊNG, đứng độc lập trong thư mục Desktop Automation: không
import gì từ myvoice, không dùng chung cài đặt, không đụng hàng đợi của bảng
điều khiển myvoice (cổng 8765). Bộ này nghe cổng 8770.

Trang có một bảng, mỗi dòng là một video sắp đăng:

    ☑  Tiêu đề  │  Hashtag  │  Link local (file mp4)  │  Trạng thái

Ba ô đầu sửa thẳng trong bảng, gõ tới đâu lưu tới đó vào danh_sach.json.

Vì sao phải có nút "➕ Thêm file mp4" thay vì ô chọn file của trình duyệt: trình
duyệt CỐ TÌNH giấu đường dẫn thật, `<input type=file>` chỉ trả về mỗi tên file.
Mà muốn đưa video cho TikTok thì phải có đường dẫn đầy đủ. Nên nút này gọi
chon_file.py chạy riêng, bật hộp thoại Windows rồi lấy đường dẫn về.

Nút "🔎 Quét kịch_bản" dò thẳng thư mục tập của myvoice, tự điền tiêu đề TikTok
lấy từ youtube_upload.json — chỉ ĐỌC, không sửa gì bên đó.

An toàn: chỉ nghe 127.0.0.1, và mọi lệnh ghi đều đòi header X-Omni nên một trang
web lạ đang mở trong cùng trình duyệt không gọi vào đây được.

Chạy:  chay_web.bat   (hoặc bấm ▶ vào chay_web.py trong VS Code)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dung_venv import dam_bao_venv                          # noqa: E402

dam_bao_venv(__file__)

import json                     # noqa: E402
import re                       # noqa: E402
import subprocess               # noqa: E402
import threading                # noqa: E402
import time                     # noqa: E402
import uuid                     # noqa: E402

from fastapi import FastAPI, Header, HTTPException, Request   # noqa: E402
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse  # noqa: E402

import tiktok_chon_video as tct  # noqa: E402

HERE = Path(__file__).resolve().parent
DANH_SACH_FILE = HERE / "danh_sach.json"
ANH = HERE / "anh_thu"
KICH_BAN = tct.KICH_BAN
CONG = 8770
KHOA = "omni-tiktok"           # header X-Omni: chặn trang lạ gọi vào

HASHTAG_MAC_DINH = "#truyenaudio #truyenfull #audio #fyp"


# ─────────────────────────────── danh sách ──────────────────────────────────
def danh_sach_rong() -> dict:
    return {"hashtag_chung": HASHTAG_MAC_DINH, "profile": tct.PROFILE, "muc": []}


def doc_danh_sach() -> dict:
    if not DANH_SACH_FILE.exists():
        return danh_sach_rong()
    try:
        d = json.loads(DANH_SACH_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return danh_sach_rong()
    d.setdefault("hashtag_chung", HASHTAG_MAC_DINH)
    d.setdefault("profile", tct.PROFILE)
    d.setdefault("muc", [])
    return d


def ghi_danh_sach(d: dict) -> None:
    DANH_SACH_FILE.write_text(json.dumps(d, ensure_ascii=False, indent=2),
                              encoding="utf-8")


def muc_moi(video: str = "", tieu_de: str = "", hashtag: str = "") -> dict:
    return {"id": uuid.uuid4().hex[:8], "chon": True, "tieu_de": tieu_de,
            "hashtag": hashtag, "video": video, "trang_thai": "chờ", "ghi_chu": ""}


# ───────────────────────── quét thư mục kịch_bản ────────────────────────────
# Tên file bản dọc sau khi đăng YouTube: 'Full ở Mimi audio Số 118 - ....mp4'
# (xem myvoice/YOUTUBE/dang_tap_youtube.py). Thứ tự ưu tiên khi một tập có nhiều
# bản dọc: bản mồi đã đổi tên → tiktok.mp4 chưa đổi tên → short.mp4.
_UU_TIEN = ("Full ở *.mp4", "tiktok.mp4", "short.mp4")


def video_cua_tap(thu_muc: Path) -> Path | None:
    for mau in _UU_TIEN:
        if "*" in mau:
            co = sorted(thu_muc.glob(mau))
            if co:
                return co[0]
        elif (thu_muc / mau).exists():
            return thu_muc / mau
    return None


def quet_kich_ban(hashtag_chung: str) -> tuple[list[dict], list[str]]:
    """Mọi tập đã dựng xong bản dọc → dòng sẵn sàng thêm vào bảng.

    Tiêu đề lấy từ youtube_upload.json của tập, thêm 'Full ở' phía trước cho
    đúng lối đặt tên bài mồi TikTok. Tập nào đã có biên nhận tiktok_upload.json
    thì ghi chú là đã đăng, không tự bỏ đi — để người xem còn quyết."""
    ra, ghi_chu = [], []
    if not KICH_BAN.is_dir():
        return ra, [f"Không thấy thư mục: {KICH_BAN}"]

    for tm in sorted(KICH_BAN.iterdir()):
        if not tm.is_dir():
            continue
        video = video_cua_tap(tm)
        if not video:
            continue
        tieu_de, so_tap = "", ""
        yt = tm / "youtube_upload.json"
        if yt.exists():
            try:
                d = json.loads(yt.read_text(encoding="utf-8"))
                tieu_de = str(d.get("title") or "")
                so_tap = str(d.get("episode") or "")
            except (json.JSONDecodeError, OSError):
                pass
        if not so_tap:
            m = re.match(r"^[A-Za-z]?(\d+)", tm.name)
            so_tap = m.group(1) if m else ""
        if tieu_de and not tieu_de.lower().startswith("full ở"):
            tieu_de = f"Full ở {tieu_de}"

        the_tap = f"#MimiAudioSo{so_tap} " if so_tap else ""
        m = muc_moi(str(video), tieu_de, (the_tap + hashtag_chung).strip())
        if (tm / "tiktok_upload.json").exists():
            m["trang_thai"] = "đã đăng"
            m["chon"] = False
            m["ghi_chu"] = "đã có biên nhận tiktok_upload.json"
        ra.append(m)
    if not ra:
        ghi_chu.append("Không tập nào có sẵn bản dọc (Full ở…/tiktok.mp4/short.mp4).")
    return ra, ghi_chu


# ──────────────────────────── hàng đợi chạy ─────────────────────────────────
class HangDoi:
    """Một luồng chạy duy nhất, để hai lần bấm Chạy không giẫm lên nhau."""

    def __init__(self):
        self.dang_chay = False
        self.xin_dung = False
        self.nhat_ky: list[str] = []
        self.dang_lam = ""
        self.khoa = threading.Lock()

    def ghi(self, dong: str) -> None:
        with self.khoa:
            self.nhat_ky.append(f"{time.strftime('%H:%M:%S')}  {dong}")
            del self.nhat_ky[:-400]

    def xoa_nhat_ky(self) -> None:
        with self.khoa:
            self.nhat_ky.clear()

    def anh_chup(self) -> dict:
        with self.khoa:
            return {"dang_chay": self.dang_chay, "dang_lam": self.dang_lam,
                    "nhat_ky": list(self.nhat_ky)}


hang_doi = HangDoi()


def chay_hang_doi(ids: list[str], chi_do: bool) -> None:
    d = doc_danh_sach()
    can_lam = [m for m in d["muc"] if m["id"] in ids]
    hang_doi.ghi(f"▶ Bắt đầu — {len(can_lam)} video"
                 + ("  (chế độ chỉ dò nút, không bấm)" if chi_do else ""))
    try:
        for i, m in enumerate(can_lam, 1):
            if hang_doi.xin_dung:
                hang_doi.ghi("⏹ Đã dừng theo yêu cầu.")
                break
            ten = Path(m["video"]).name or "(chưa chọn file)"
            hang_doi.dang_lam = f"{i}/{len(can_lam)} — {ten}"
            hang_doi.ghi(f"── [{i}/{len(can_lam)}] {ten}")
            _dat_trang_thai(m["id"], "đang nạp", "")
            try:
                ket = tct.nap_video(m["video"], profile=d.get("profile", tct.PROFILE),
                                    chi_do=chi_do, log=hang_doi.ghi)
                _dat_trang_thai(m["id"], "đã nạp" if ket["ok"] else "lỗi",
                                ket["ly_do"])
            except Exception as e:                      # noqa: BLE001
                hang_doi.ghi(f"❌ {type(e).__name__}: {e}")
                _dat_trang_thai(m["id"], "lỗi", f"{type(e).__name__}: {e}")
        else:
            hang_doi.ghi("✅ Xong cả hàng đợi.")
    finally:
        hang_doi.dang_chay = False
        hang_doi.xin_dung = False
        hang_doi.dang_lam = ""


def _dat_trang_thai(muc_id: str, trang_thai: str, ghi_chu: str) -> None:
    d = doc_danh_sach()
    for m in d["muc"]:
        if m["id"] == muc_id:
            m["trang_thai"], m["ghi_chu"] = trang_thai, ghi_chu
    ghi_danh_sach(d)


# ──────────────────────────────── server ────────────────────────────────────
app = FastAPI(title="TikTok — bảng điều khiển")


def canh(x_omni: str | None) -> None:
    if x_omni != KHOA:
        raise HTTPException(403, "Thiếu header X-Omni.")


@app.get("/", response_class=HTMLResponse)
def trang_chu() -> str:
    return TRANG


@app.get("/api/danh-sach")
def api_danh_sach() -> dict:
    return doc_danh_sach()


@app.post("/api/luu")
async def api_luu(req: Request, x_omni: str = Header(None)) -> dict:
    canh(x_omni)
    d = await req.json()
    cu = doc_danh_sach()
    cu["hashtag_chung"] = d.get("hashtag_chung", cu["hashtag_chung"])
    cu["profile"] = d.get("profile", cu["profile"])
    if "muc" in d:
        cu["muc"] = d["muc"]
    ghi_danh_sach(cu)
    return {"ok": True, "so_dong": len(cu["muc"])}


@app.post("/api/them-file")
def api_them_file(x_omni: str = Header(None)) -> dict:
    """Bật hộp thoại chọn file của Windows (tiến trình riêng) rồi thêm vào bảng."""
    canh(x_omni)
    d = doc_danh_sach()
    mo_san = str(KICH_BAN) if KICH_BAN.is_dir() else ""
    try:
        ra = subprocess.run(
            [sys.executable, "-X", "utf8", str(HERE / "chon_file.py"),
             "--thu-muc", mo_san],
            capture_output=True, text=True, encoding="utf-8", timeout=300)
    except subprocess.TimeoutExpired:
        return {"ok": False, "loi": "Hộp thoại mở quá lâu, đã bỏ."}
    duong_dan = [x.strip() for x in (ra.stdout or "").splitlines() if x.strip()]
    for p in duong_dan:
        d["muc"].append(muc_moi(p, Path(p).stem, d["hashtag_chung"]))
    ghi_danh_sach(d)
    return {"ok": True, "them": len(duong_dan), "danh_sach": d}


@app.post("/api/quet")
def api_quet(x_omni: str = Header(None)) -> dict:
    canh(x_omni)
    d = doc_danh_sach()
    moi, ghi_chu = quet_kich_ban(d["hashtag_chung"])
    da_co = {m["video"] for m in d["muc"]}
    them = [m for m in moi if m["video"] not in da_co]
    d["muc"].extend(them)
    ghi_danh_sach(d)
    return {"ok": True, "them": len(them), "bo_qua_trung": len(moi) - len(them),
            "ghi_chu": ghi_chu, "danh_sach": d}


@app.post("/api/chay")
async def api_chay(req: Request, x_omni: str = Header(None)) -> dict:
    canh(x_omni)
    if hang_doi.dang_chay:
        return {"ok": False, "loi": "Đang chạy rồi."}
    than = await req.json()
    ids = than.get("ids") or []
    if not ids:
        return {"ok": False, "loi": "Chưa tick dòng nào."}
    hang_doi.xoa_nhat_ky()
    hang_doi.dang_chay = True
    hang_doi.xin_dung = False
    threading.Thread(target=chay_hang_doi, args=(ids, bool(than.get("chi_do"))),
                     daemon=True).start()
    return {"ok": True, "so_dong": len(ids)}


@app.post("/api/dung")
def api_dung(x_omni: str = Header(None)) -> dict:
    canh(x_omni)
    hang_doi.xin_dung = True
    hang_doi.ghi("⏹ Đã nhận lệnh dừng — sẽ dừng sau video đang làm.")
    return {"ok": True}


@app.get("/api/trang-thai")
def api_trang_thai() -> dict:
    t = hang_doi.anh_chup()
    t["muc"] = [{"id": m["id"], "trang_thai": m.get("trang_thai", ""),
                 "ghi_chu": m.get("ghi_chu", "")} for m in doc_danh_sach()["muc"]]
    return t


@app.get("/anh/{ten}")
def api_anh(ten: str):
    p = ANH / Path(ten).name
    if not p.exists():
        return JSONResponse({"loi": "chưa có ảnh"}, status_code=404)
    return FileResponse(p, headers={"Cache-Control": "no-store"})


TRANG = r"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TikTok — bảng điều khiển</title>
<style>
  :root{
    --nen:#f6f7f9; --the:#fff; --chu:#15171a; --mo:#667085; --vien:#e3e6ea;
    --do:#fe2c55; --xanh:#0a7d3f; --vang:#a8690a; --xam:#eef0f3;
  }
  @media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
    --nen:#111316; --the:#191c20; --chu:#e8eaed; --mo:#9aa3af; --vien:#2a2f36;
    --xam:#23272d;
  }}
  *{box-sizing:border-box}
  body{margin:0;background:var(--nen);color:var(--chu);
       font:15px/1.5 "Segoe UI",system-ui,sans-serif}
  .boc{max-width:1400px;margin:0 auto;padding:20px 16px 60px}
  h1{font-size:20px;margin:0 0 4px}
  .phu{color:var(--mo);font-size:13px;margin:0 0 18px}
  .the{background:var(--the);border:1px solid var(--vien);border-radius:12px;
       padding:14px;margin-bottom:16px}
  .hang{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
  button{font:inherit;padding:8px 14px;border-radius:8px;border:1px solid var(--vien);
         background:var(--the);color:var(--chu);cursor:pointer}
  button:hover{border-color:var(--mo)}
  button.chinh{background:var(--do);border-color:var(--do);color:#fff;font-weight:600}
  button.chinh:disabled{opacity:.45;cursor:not-allowed}
  input[type=text]{font:inherit;width:100%;padding:7px 9px;border-radius:7px;
       border:1px solid var(--vien);background:var(--nen);color:var(--chu)}
  input[type=text]:focus{outline:2px solid var(--do);outline-offset:-1px}
  table{width:100%;border-collapse:collapse}
  th,td{padding:7px 8px;border-bottom:1px solid var(--vien);vertical-align:middle}
  th{text-align:left;font-size:12px;color:var(--mo);text-transform:uppercase;
     letter-spacing:.04em;font-weight:600}
  td.giua,th.giua{text-align:center}
  .tt{font-size:12px;padding:3px 9px;border-radius:999px;background:var(--xam);
      white-space:nowrap;display:inline-block}
  .tt.xong{background:#d7f3e3;color:var(--xanh)}
  .tt.loi{background:#fde2e6;color:var(--do)}
  .tt.chay{background:#fdefd2;color:var(--vang)}
  @media (prefers-color-scheme:dark){:root:not([data-theme="light"]) .tt.xong{background:#10331f}
    :root:not([data-theme="light"]) .tt.loi{background:#3a1119}
    :root:not([data-theme="light"]) .tt.chay{background:#3a2c0e}}
  .xoa{border:0;background:none;color:var(--mo);font-size:17px;padding:2px 6px}
  .xoa:hover{color:var(--do)}
  pre.log{background:#0c0e11;color:#b7f7c6;border-radius:10px;padding:12px;
      height:260px;overflow:auto;margin:0;font:12.5px/1.6 Consolas,monospace;
      white-space:pre-wrap;word-break:break-word}
  .nho{font-size:12px;color:var(--mo)}
  .duongdan{font:12.5px Consolas,monospace}
  .anh{display:flex;gap:12px;flex-wrap:wrap}
  .anh figure{margin:0;flex:1 1 300px}
  .anh img{width:100%;border:1px solid var(--vien);border-radius:8px;display:block}
  .anh figcaption{font-size:12px;color:var(--mo);padding-top:6px}
  .canhbao{border-left:3px solid var(--do);padding-left:10px;font-size:13px;
      color:var(--mo);margin-top:10px}
</style></head><body><div class="boc">

<h1>TikTok — bảng điều khiển</h1>
<p class="phu">Nhìn màn hình và bấm ngầm vào Chrome <b id="ten-profile">Profile 83</b>.
   Không cướp chuột — bạn cứ làm việc bình thường trong lúc nó chạy.
   Hiện mới tới bước <b>nạp video</b>: điền caption và bấm Đăng chưa làm.</p>

<div class="the">
  <div class="hang">
    <button onclick="themFile()">➕ Thêm file mp4…</button>
    <button onclick="quet()">🔎 Quét thư mục kịch_bản</button>
    <button onclick="themDongTrong()">➕ Dòng trống</button>
    <span style="flex:1"></span>
    <label class="nho"><input type="checkbox" id="chi-do"> chỉ dò nút, không bấm</label>
    <button class="chinh" id="nut-chay" onclick="chay()">▶ Chạy dòng đã chọn</button>
    <button id="nut-dung" onclick="dung()" disabled>⏹ Dừng</button>
  </div>
  <div class="hang" style="margin-top:10px">
    <span class="nho">Hashtag chung (dùng cho dòng mới):</span>
    <input type="text" id="hashtag-chung" style="flex:1;min-width:260px"
           oninput="luuHoan()">
  </div>
</div>

<div class="the">
  <table>
    <thead><tr>
      <th class="giua" style="width:38px"><input type="checkbox" id="chon-tat"
          onchange="chonTat(this.checked)"></th>
      <th style="width:28%">Tiêu đề</th>
      <th style="width:24%">Hashtag</th>
      <th>Link local (file mp4)</th>
      <th style="width:150px">Trạng thái</th>
      <th style="width:36px"></th>
    </tr></thead>
    <tbody id="than"></tbody>
  </table>
  <p class="nho" id="trong" style="display:none;padding:18px 4px">
    Chưa có dòng nào. Bấm <b>Quét thư mục kịch_bản</b> để tự điền từ các tập đã dựng,
    hoặc <b>Thêm file mp4…</b> để chọn tay.</p>
</div>

<div class="the">
  <div class="hang" style="margin-bottom:8px">
    <b>Nhật ký</b><span class="nho" id="dang-lam"></span>
    <span style="flex:1"></span>
    <button onclick="xemAnh()">🖼 Xem ảnh lần chạy gần nhất</button>
  </div>
  <pre class="log" id="log">(chưa chạy)</pre>
  <div class="anh" id="khung-anh" style="margin-top:12px;display:none">
    <figure><img id="anh1"><figcaption>Nút máy nhìn thấy — khung đỏ dày là chỗ nó bấm,
      khung xanh là ứng viên bị loại</figcaption></figure>
    <figure><img id="anh2"><figcaption>Màn hình sau khi nạp video</figcaption></figure>
  </div>
  <p class="canhbao">Lúc hộp thoại chọn file bật lên, Windows kéo tiêu điểm bàn phím
     sang đó chưa tới một giây rồi tự đóng. Đó là chỗ duy nhất giành với bạn;
     con trỏ chuột thì không hề bị đụng.</p>
</div>

<script>
const H = {"Content-Type":"application/json","X-Omni":"omni-tiktok"};
let DL = {hashtag_chung:"", profile:"", muc:[]};
let hen = null;

const esc = s => (s??"").replace(/[&<>"]/g, c =>
  ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

async function tai(){
  DL = await (await fetch("/api/danh-sach")).json();
  document.getElementById("hashtag-chung").value = DL.hashtag_chung || "";
  document.getElementById("ten-profile").textContent = DL.profile || "Profile 83";
  ve();
}

function lopTT(t){
  if(t==="đã nạp"||t==="đã đăng") return "xong";
  if(t==="lỗi") return "loi";
  if(t==="đang nạp") return "chay";
  return "";
}

function ve(){
  const than = document.getElementById("than");
  than.innerHTML = DL.muc.map((m,i) => `<tr data-id="${m.id}">
    <td class="giua"><input type="checkbox" ${m.chon?"checked":""}
        onchange="sua(${i},'chon',this.checked)"></td>
    <td><input type="text" value="${esc(m.tieu_de)}" placeholder="Tiêu đề bài đăng"
        oninput="sua(${i},'tieu_de',this.value)"></td>
    <td><input type="text" value="${esc(m.hashtag)}" placeholder="#hashtag"
        oninput="sua(${i},'hashtag',this.value)"></td>
    <td><input type="text" class="duongdan" value="${esc(m.video)}"
        placeholder="D:\\...\\video.mp4" oninput="sua(${i},'video',this.value)"></td>
    <td><span class="tt ${lopTT(m.trang_thai)}" title="${esc(m.ghi_chu)}"
        >${esc(m.trang_thai||"chờ")}</span></td>
    <td class="giua"><button class="xoa" title="Bỏ dòng"
        onclick="boDong(${i})">✕</button></td></tr>`).join("");
  document.getElementById("trong").style.display = DL.muc.length ? "none" : "block";
}

function sua(i, truong, gt){ DL.muc[i][truong] = gt; luuHoan(); }
function boDong(i){ DL.muc.splice(i,1); ve(); luu(); }
function chonTat(v){ DL.muc.forEach(m => m.chon = v); ve(); luu(); }
function themDongTrong(){
  DL.muc.push({id:Math.random().toString(16).slice(2,10), chon:true, tieu_de:"",
               hashtag:document.getElementById("hashtag-chung").value,
               video:"", trang_thai:"chờ", ghi_chu:""});
  ve(); luu();
}

function luuHoan(){ clearTimeout(hen); hen = setTimeout(luu, 400); }
async function luu(){
  DL.hashtag_chung = document.getElementById("hashtag-chung").value;
  await fetch("/api/luu", {method:"POST", headers:H, body:JSON.stringify(DL)});
}

async function themFile(){
  const r = await (await fetch("/api/them-file",{method:"POST",headers:H})).json();
  if(r.danh_sach){ DL = r.danh_sach; ve(); }
  if(r.them === 0) alert("Chưa chọn file nào.");
}

async function quet(){
  const r = await (await fetch("/api/quet",{method:"POST",headers:H})).json();
  if(r.danh_sach){ DL = r.danh_sach; ve(); }
  let s = `Thêm ${r.them} dòng.`;
  if(r.bo_qua_trung) s += `  Bỏ qua ${r.bo_qua_trung} dòng đã có trong bảng.`;
  if(r.ghi_chu && r.ghi_chu.length) s += "\n" + r.ghi_chu.join("\n");
  alert(s);
}

async function chay(){
  await luu();
  const ids = DL.muc.filter(m => m.chon).map(m => m.id);
  if(!ids.length){ alert("Chưa tick dòng nào."); return; }
  const chiDo = document.getElementById("chi-do").checked;
  if(!chiDo && !confirm(`Sẽ nạp ${ids.length} video lên TikTok (KHÔNG bấm Đăng). Tiếp?`))
    return;
  const r = await (await fetch("/api/chay",{method:"POST",headers:H,
    body:JSON.stringify({ids, chi_do:chiDo})})).json();
  if(!r.ok){ alert(r.loi); return; }
  theoDoi();
}

async function dung(){ await fetch("/api/dung",{method:"POST",headers:H}); }

async function theoDoi(){
  const t = await (await fetch("/api/trang-thai")).json();
  const log = document.getElementById("log");
  log.textContent = t.nhat_ky.length ? t.nhat_ky.join("\n") : "(chưa chạy)";
  log.scrollTop = log.scrollHeight;
  document.getElementById("dang-lam").textContent = t.dang_lam ? " — " + t.dang_lam : "";
  document.getElementById("nut-chay").disabled = t.dang_chay;
  document.getElementById("nut-dung").disabled = !t.dang_chay;
  t.muc.forEach(x => {
    const m = DL.muc.find(y => y.id === x.id);
    if(m){ m.trang_thai = x.trang_thai; m.ghi_chu = x.ghi_chu; }
    const o = document.querySelector(`tr[data-id="${x.id}"] .tt`);
    if(o){ o.textContent = x.trang_thai || "chờ"; o.title = x.ghi_chu || "";
           o.className = "tt " + lopTT(x.trang_thai); }
  });
  if(t.dang_chay) setTimeout(theoDoi, 1000);
  else xemAnh();
}

function xemAnh(){
  const t = Date.now();
  document.getElementById("anh1").src = "/anh/tiktok_b1_do_nut.png?t=" + t;
  document.getElementById("anh2").src = "/anh/tiktok_b1_sau_khi_nap.png?t=" + t;
  document.getElementById("khung-anh").style.display = "flex";
}

tai(); theoDoi();
</script></div></body></html>"""


def main():
    import uvicorn
    print("═" * 64)
    print("  TikTok — bảng điều khiển (chức năng riêng, không dính myvoice)")
    print(f"  Địa chỉ: http://127.0.0.1:{CONG}")
    print("  Đóng cửa sổ này là tắt server.")
    print("═" * 64)
    uvicorn.run(app, host="127.0.0.1", port=CONG, log_level="warning")


if __name__ == "__main__":
    main()
