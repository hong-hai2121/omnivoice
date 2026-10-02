"""Read-only local episode scanner for the Chrome extension. Python stdlib only."""

import argparse
import json
import os
import re
import struct
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


ROOT = Path(__file__).resolve().parents[2] / "myvoice" / "k\u1ecbch_b\u1ea3n"
DEFAULT_HASHTAGS = "#truyenaudio #truyenfull #audio #fyp"
PORT = 8771
QUEUE_FILE = Path(__file__).resolve().parent.parent / "danh_sach.json"
# Episode folders are "<letter><number> - <source>"; other folders (output...) are not episodes.
EPISODE_FOLDER = re.compile(r"^[A-Za-z]?(\d+)")
NO_VIDEO = "chưa có video"
KIND_NAMES = {"dai": "Full", "nua": "Nửa video", "ngan": "Short"}


def pick_video(folder, kind):
    names = sorted(p for p in folder.iterdir() if p.is_file())
    patterns = {
        "dai": (("[Full] ", ".mp4"), ("facebook", ".mp4")),
        "nua": (("Full \u1edf ", ".mp4"), ("tiktok", ".mp4")),
        "ngan": (("short.mp4", ""),),
    }[kind]
    for prefix, suffix in patterns:
        for item in names:
            if item.name.startswith(prefix) and item.name.lower().endswith(suffix or prefix.lower()):
                return item
    return None


def scan_episodes(root=ROOT, kind="dai", hashtags=DEFAULT_HASHTAGS):
    if kind not in ("dai", "nua", "ngan"):
        raise ValueError("Loai video phai la dai, nua hoac ngan.")
    root = root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Khong thay thu muc: {root}")
    rows, notes, folders = [], [], []
    folders_complete = True
    for folder in sorted(root.iterdir()):
        try:
            if not folder.is_dir():
                continue
            # Inventory folders even when a video variant is absent or unfinished.
            folders.append(str(folder))
            if not folder.resolve().is_relative_to(root):
                continue
            video = pick_video(folder, kind)
            if video is not None and (not video.resolve().is_relative_to(root) or video.stat().st_size == 0):
                video = None
            # New scripts are listed before their video is rendered; other folders need a video.
            if video is None and not EPISODE_FOLDER.match(folder.name):
                continue
            title, episode = "", ""
            metadata = folder / "youtube_upload.json"
            if metadata.is_file() and metadata.resolve().is_relative_to(root):
                try:
                    data = json.loads(metadata.read_text(encoding="utf-8-sig"))
                    if not isinstance(data, dict):
                        raise ValueError("JSON phai la object")
                    title, episode = str(data.get("title") or ""), str(data.get("episode") or "")
                except (OSError, ValueError) as error:
                    notes.append(f"{folder.name}: khong doc duoc youtube_upload.json ({error})")
            if not episode:
                match = EPISODE_FOLDER.match(folder.name)
                episode = match.group(1) if match else ""
            if title and not title.lower().startswith("full \u1edf"):
                title = f"Full \u1edf {title}"
            uploaded = (folder / "tiktok_upload.json").is_file()
            variants = {}
            for variant in ("dai", "nua", "ngan"):
                candidate = pick_video(folder, variant)
                if candidate and candidate.resolve().is_relative_to(root) and candidate.stat().st_size > 0:
                    variants[variant] = str(candidate)
            if uploaded:
                status, note = "\u0111\u00e3 \u0111\u0103ng", "Da co bien nhan tiktok_upload.json"
            elif video is None:
                status = NO_VIDEO
                note = f"Chua co ban {KIND_NAMES[kind]}" + (" (co ban khac, doi o Phien ban video)" if variants else "")
            else:
                status, note = "cho", ""
            rows.append({
                "video": str(video) if video else "", "thu_muc": str(folder), "tieu_de": title,
                "hashtag": ((f"#MimiAudioSo{episode} " if episode else "") + hashtags).strip(),
                "gio_dang": "", "trang_thai": status, "ghi_chu": note,
                "variants": variants, "statusOrigin": "receipt" if uploaded else "",
            })
        except OSError as error:
            folders_complete = False
            notes.append(f"{folder.name}: {error}")
    return {"ok": True, "root": str(root), "muc": rows, "ghi_chu": notes,
            "folders": folders, "folders_complete": folders_complete}


def read_schedule(queue_file=QUEUE_FILE):
    data = json.loads(queue_file.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or not isinstance(data.get("muc"), list):
        raise ValueError("danh_sach.json phai co danh sach muc")
    return {
        "source": str(queue_file.resolve()), "khung_gio": str(data.get("khung_gio") or ""),
        "muc": [{key: str(row.get(key) or "") for key in
                 ("video", "tieu_de", "hashtag", "gio_dang", "trang_thai", "ghi_chu")}
                for row in data["muc"] if isinstance(row, dict)],
    }


def scan_payload(root=ROOT, kind="dai", hashtags=DEFAULT_HASHTAGS, queue_file=QUEUE_FILE):
    result = scan_episodes(root, kind, hashtags)
    try:
        result["schedule"] = read_schedule(queue_file)
    except (OSError, ValueError) as error:
        result["schedule"] = None
        result["ghi_chu"].append(f"Khong doc duoc lich tu {queue_file}: {error}")
    return result


def make_server(root=ROOT, port=PORT, queue_file=QUEUE_FILE):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def allowed(self):
            origin = self.headers.get("Origin", "")
            return (self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}" and
                    (not origin or re.fullmatch(r"chrome-extension://[a-p]{32}", origin)))

        def reply(self, status, data):
            body = json.dumps(data, ensure_ascii=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            origin = self.headers.get("Origin", "")
            if re.fullmatch(r"chrome-extension://[a-p]{32}", origin):
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Access-Control-Allow-Headers", "X-Omni")
                self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
                self.send_header("Vary", "Origin")
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self):
            self.reply(200 if self.allowed() else 403, {})

        def do_GET(self):
            if not self.allowed() or self.headers.get("X-Omni") != "gptcode-scanner":
                self.reply(403, {"ok": False, "error": "Extension access only"})
                return
            url = urlsplit(self.path)
            if url.path == "/health":
                self.reply(200, {"ok": True, "service": "gptcode-scanner"})
                return
            if url.path != "/api/scan":
                self.reply(404, {"ok": False, "error": "Not found"})
                return
            query = parse_qs(url.query, keep_blank_values=True)
            try:
                result = scan_payload(root, query.get("kind", ["dai"])[0],
                                      query.get("hashtags", [DEFAULT_HASHTAGS])[0][:2000], queue_file)
                self.reply(200, result)
            except (OSError, ValueError) as error:
                self.reply(400, {"ok": False, "error": str(error)})

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def native_reply(stdin, stdout, root=ROOT, queue_file=QUEUE_FILE):
    """Answer one Chrome native-messaging request: 4-byte length + JSON in each direction."""
    header = stdin.read(4)
    if len(header) < 4:
        return False
    request = json.loads(stdin.read(struct.unpack("@I", header)[0]).decode("utf-8"))
    try:
        if not isinstance(request, dict):
            raise ValueError("Yeu cau phai la object")
        result = scan_payload(root, str(request.get("kind") or "dai"),
                              str(request.get("hashtags") or DEFAULT_HASHTAGS)[:2000], queue_file)
    except (OSError, ValueError) as error:
        result = {"ok": False, "error": str(error)}
    body = json.dumps(result, ensure_ascii=True).encode("utf-8")
    stdout.write(struct.pack("@I", len(body)) + body)
    stdout.flush()
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--queue", type=Path, default=QUEUE_FILE)
    parser.add_argument("--once", action="store_true", help="Scan once and print JSON")
    parser.add_argument("--native", action="store_true", help="Chrome native messaging host (cai_bo_quet.py)")
    # Chrome appends the caller origin and --parent-window to native hosts.
    args, _chrome_args = parser.parse_known_args()
    if args.native:
        if os.name == "nt":
            import msvcrt
            msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
            msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
        native_reply(sys.stdin.buffer, sys.stdout.buffer, args.root, args.queue)
        return
    if args.once:
        print(json.dumps(scan_payload(args.root, queue_file=args.queue), ensure_ascii=True))
        return
    try:
        server = make_server(args.root, args.port, args.queue)
    except OSError as error:
        raise SystemExit(f"Khong mo duoc cong {args.port}: {error}. Kiem tra tien trinh dang chay.") from error
    print(f"OmniVoice scanner: http://127.0.0.1:{args.port}", flush=True)
    print("Mo extension OmniVoice TikTok. Giu cua so nay chay; Ctrl+C de dung.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
