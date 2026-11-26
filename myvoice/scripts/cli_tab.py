# -*- coding: utf-8 -*-
"""cli_tab.py — phần xử lý của tab 🤖 CLI dịch (GPT CLI + Gemini CLI gộp MỘT tab),
DÙNG CHUNG cho web myvoice và web myvideo (26/11/2026).

Hai bảng web mỗi bên có template + route riêng (khung trang khác nhau) nhưng mọi thứ
"tính toán" nằm ở đây để không viết hai lần:
  • ngu_canh(nha)  — biến cho template: CLI đang xem, model đã lưu, danh sách model,
                     cách dịch mặc định đang chọn…
  • thong_tin(nha) — thẻ trạng thái (binary · đăng nhập · model sẽ dùng · cách dịch);
                     KHÔNG gọi model.
  • luu(form)      — lưu model / mức cố gắng của một CLI và/hoặc CÁCH DỊCH MẶC ĐỊNH.
Bộ nhắn thử (GptCliTester) vẫn ở myvoice/web/gptcli_test.py — myvideo nạp file đó.

nha = "gpt" (codex, ChatGPT → cách dịch "cli") | "gemini" (agy, Google → "gemini_cli").
"""
import dich_gptcli as gc
import gemini_backend

TAB = {"gpt": {"chon": "cli", "icon": "🤖"}, "gemini": {"chon": "gemini_cli", "icon": "✨"}}
# Bốn cách dịch chọn được làm MẶC ĐỊNH (khoá gemini_backend dùng chung myvoice · myvideo · GUI).
CACH_DICH = (
    ("extension", "🧩 Chrome Extension", "Gemini web trong Chrome — phải giữ Chrome đang mở"),
    ("firefox", "🦊 Firefox / Selenium", "Gemini web qua Firefox — đường dự phòng"),
    ("cli", "🤖 GPT CLI", "Codex · tài khoản ChatGPT — không cần trình duyệt"),
    ("gemini_cli", "✨ Gemini CLI", "Antigravity (agy) · tài khoản Google — không cần trình duyệt"),
)
TEN_CACH_DICH = {k: ten for k, ten, _ in CACH_DICH}


JS_FILE = gemini_backend.BASE_DIR / "web" / "static" / "cli_tab.js"   # JS của tab, hai bảng nạp chung


def chuan_nha(value) -> str:
    return "gemini" if str(value or "") == "gemini" else "gpt"


def nha_mac_dinh() -> str:
    """CLI nên mở sẵn khi vào tab: cái đang là cách dịch mặc định (không phải CLI → GPT)."""
    return gemini_backend.cli_nha(gemini_backend.saved_backend())


def ngu_canh(nha) -> dict:
    """Biến cho template tab CLI (cả hai bảng web)."""
    import dich_gemini as g
    nha = chuan_nha(nha)
    cai_dat = gc.cai_dat(nha)
    models = gc.danh_sach_model(nha)
    backend = gemini_backend.saved_backend()
    return {
        "nha": nha, "ten": gc.TEN_NHA[nha], "icon": TAB[nha]["icon"], "lenh": gc.LENH_NHA[nha],
        "backend": backend, "cach_dich": CACH_DICH,
        # ?v=mtime: sửa JS xong là URL đổi, trình duyệt không dính bản cũ.
        "cli_js_v": int(JS_FILE.stat().st_mtime) if JS_FILE.exists() else 0,
        "backend_is_cli": backend == TAB[nha]["chon"],
        "cai_dat": cai_dat, "models": models, "cfg": gc.config_mac_dinh(),
        "model_khac": bool(cai_dat["model"]) and cai_dat["model"] not in {m["slug"] for m in models},
        "muc": [(k, *gc.MUC_CO_GANG_NHAN[k]) for k in gc.MUC_CO_GANG],
        # Câu hướng dẫn NGẮN viết riêng cho CLI (gửi kèm từng đoạn) — để soi ở khối nhắn thử.
        "cli_header": gc.CLI_HEADER, "cli_huongdan": g.TRANSLATE_PREFIX_CLI.strip(),
    }


def thong_tin(nha) -> dict:
    """Thẻ trạng thái: binary · đăng nhập · model/mức sẽ dùng · cách dịch đang chọn.
    Chỉ `--version` + xem đăng nhập (~1–2 s), không gọi model."""
    nha = chuan_nha(nha)
    backend = gemini_backend.saved_backend()
    out = {"ok": True, "backend": backend, "backend_ten": TEN_CACH_DICH.get(backend, backend),
           "nha": nha, "chon": TAB[nha]["chon"], "ten": gc.TEN_NHA[nha],
           "lenh": "agy" if nha == "gemini" else "codex-cli", **gc.hieu_luc(nha)}
    try:
        out.update(gc.kiem_tra(nha))
    except gc.GptCliError as e:
        out.update(ok=False, error=str(e))
    return out


def luu(form):
    """Lưu từ form của tab → (nha, câu tóm tắt). Các ô (có ô nào lưu ô đó):
      • nha                — tab đang xem (ô ẩn), cho biết model/effort là của CLI nào;
      • model / model_khac / effort — dich_gptcli.luu_cai_dat (khoá gptcli_* / geminicli_model);
      • mac_dinh           — CÁCH DỊCH MẶC ĐỊNH: extension | firefox | cli | gemini_cli;
      • co_dung_cli + dung_cli — ô tick kiểu cũ "dùng CLI này làm cách dịch" (giữ cho
        tương thích): tick = chọn CLI của tab; bỏ tick khi đang là nó = về Chrome Extension."""
    nha = chuan_nha(form.get("nha"))
    tab, ten = TAB[nha], gc.TEN_NHA[nha]
    notes = []
    if "effort" in form or "model" in form:
        model = str(form.get("model") or "").strip()
        if model == "__khac__":
            model = str(form.get("model_khac") or "").strip()
        saved = gc.luu_cai_dat(model=model, effort=str(form.get("effort") or ""), nha=nha)
        if nha == "gemini":                   # Gemini gộp mức vào tên model
            notes.append(f"{ten}: {saved['model'] or 'model agy tự chọn'}")
        else:
            notes.append(f"{saved['model'] or 'model theo config.toml'} · mức "
                         f"{saved['effort'] or 'mặc định'}")
    if form.get("mac_dinh") in gemini_backend.BACKENDS:
        chon = gemini_backend.set_backend(form.get("mac_dinh"))
        notes.append(f"dịch mặc định: {TEN_CACH_DICH[chon]}")
    if "co_dung_cli" in form:
        if "dung_cli" in form:
            gemini_backend.set_backend(tab["chon"])
            notes.append(f"cách dịch: {ten}")
        elif gemini_backend.saved_backend() == tab["chon"]:
            gemini_backend.set_backend(gemini_backend.DEFAULT_BACKEND)
            notes.append("cách dịch: Chrome Extension")
    return nha, (" · ".join(notes) if notes else "không có gì đổi")
