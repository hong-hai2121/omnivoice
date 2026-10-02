"""Register chay_quet.py as a Chrome native messaging host (current Windows user only).

Afterwards the extension starts the scanner itself; there is no window to keep open.
  python cai_bo_quet.py          install / refresh
  python cai_bo_quet.py --go     remove the registry key and generated manifest
"""

import argparse
import json
import os
import sys
from pathlib import Path

HOST = "com.omnivoice.gptcode_scanner"
HERE = Path(__file__).resolve().parent
EXTENSION = HERE / "extension"
MANIFEST = HERE / "native_host.json"
LAUNCHER = HERE / "native_host.bat"
REG_PATH = rf"Software\Google\Chrome\NativeMessagingHosts\{HOST}"


def chrome_profiles():
    base = Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data"
    return [p for p in base.iterdir() if p.is_dir()] if base.is_dir() else []


def find_extension_ids(extension=EXTENSION):
    """Unpacked extension IDs come from the load path; read them from every Chrome profile."""
    wanted = os.path.normcase(str(extension.resolve()))
    found = set()
    for profile in chrome_profiles():
        for name in ("Secure Preferences", "Preferences"):
            try:
                data = json.loads((profile / name).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            settings = data.get("extensions", {}).get("settings", {})
            for ext_id, value in settings.items():
                path = value.get("path") if isinstance(value, dict) else None
                if path and os.path.normcase(os.path.normpath(path)) == wanted:
                    found.add(ext_id)
    return sorted(found)


def install(ids):
    import winreg
    MANIFEST.write_text(json.dumps({
        "name": HOST, "description": "OmniVoice TikTok - doc thu muc kich_ban (chi doc)",
        "path": str(LAUNCHER), "type": "stdio",
        "allowed_origins": [f"chrome-extension://{ext_id}/" for ext_id in ids],
    }, indent=2), encoding="utf-8")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_PATH) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, str(MANIFEST))


def uninstall():
    import winreg
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, REG_PATH)
    except FileNotFoundError:
        pass
    if MANIFEST.exists():
        MANIFEST.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--id", action="append", default=[], help="Extension ID (mac dinh: tu doc tu Chrome)")
    parser.add_argument("--go", action="store_true", help="Go bo dang ky")
    args = parser.parse_args()
    if sys.platform != "win32":
        raise SystemExit("Chi ho tro Windows.")
    if args.go:
        uninstall()
        print("Da go bo dang ky bo quet khoi Chrome.")
        return
    ids = sorted(set(args.id) | set(find_extension_ids()))
    if not ids:
        raise SystemExit(f"Chua thay extension nap tu {EXTENSION}. Load unpacked trong Chrome truoc, "
                         "hoac chay lai voi --id <ID extension>.")
    install(ids)
    print("Da dang ky bo quet cho extension:", ", ".join(ids))
    print("Reload extension trong chrome://extensions roi bam Cap nhat kich ban.")


if __name__ == "__main__":
    main()
