r"""Đọc kho chrome.storage.local của extension OmniVoice TikTok (LevelDB) để chẩn đoán.

Dùng khi extension báo lỗi mà không mở được bảng: progress (nhật ký lần chạy cuối),
rowResults, submissions (biên nhận), lastDiagnostic (ảnh chụp + cấu trúc trang lúc lỗi),
lastPostRead, tiktokPosts, lastCaptionTrace, rows.

Cách dùng (Chrome đang mở vẫn được: chép thư mục ra trước vì file LOCK đang bận):
  mkdir %TEMP%\ldb && copy "%LOCALAPPDATA%\Google\Chrome\User Data\Profile 83\Local Extension Settings\bcfcefneiobdlniincflokfdmjckaodc\*" %TEMP%\ldb
  python doc_kho_extension.py %TEMP%\ldb --keys
  python doc_kho_extension.py %TEMP%\ldb progress
  python doc_kho_extension.py %TEMP%\ldb lastDiagnostic ra.json   (trường screenshot là data:image/png;base64)

Không cần thư viện ngoài: tự giải nén snappy và đọc .ldb (bảng) + .log (nhật ký ghi).
Với mỗi khóa chỉ in bản có số thứ tự (sequence) cao nhất, tức giá trị mới nhất.
"""
import json
import os
import struct
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def varint(data, pos):
    shift, value = 0, 0
    while True:
        byte = data[pos]
        pos += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, pos
        shift += 7


def snappy_decompress(src):
    length, pos = varint(src, 0)
    out = bytearray()
    while pos < len(src):
        tag = src[pos]
        pos += 1
        kind = tag & 3
        if kind == 0:
            size = tag >> 2
            if size >= 60:
                extra = size - 59
                size = int.from_bytes(src[pos:pos + extra], "little")
                pos += extra
            size += 1
            out += src[pos:pos + size]
            pos += size
            continue
        if kind == 1:
            size = ((tag >> 2) & 7) + 4
            offset = ((tag >> 5) << 8) | src[pos]
            pos += 1
        elif kind == 2:
            size = (tag >> 2) + 1
            offset = int.from_bytes(src[pos:pos + 2], "little")
            pos += 2
        else:
            size = (tag >> 2) + 1
            offset = int.from_bytes(src[pos:pos + 4], "little")
            pos += 4
        start = len(out) - offset
        for i in range(size):
            out.append(out[start + i])
    return bytes(out)


def read_block(data, offset, size):
    raw = data[offset:offset + size]
    kind = data[offset + size]
    if kind == 1:
        raw = snappy_decompress(raw)
    elif kind != 0:
        raise ValueError(f"unsupported block compression {kind}")
    return raw


def block_entries(block):
    num_restarts = struct.unpack("<I", block[-4:])[0]
    end = len(block) - 4 - num_restarts * 4
    pos, key = 0, b""
    while pos < end:
        shared, pos = varint(block, pos)
        non_shared, pos = varint(block, pos)
        value_len, pos = varint(block, pos)
        key = key[:shared] + block[pos:pos + non_shared]
        pos += non_shared
        value = block[pos:pos + value_len]
        pos += value_len
        yield key, value


def read_table(path, found):
    data = open(path, "rb").read()
    footer = data[-48:]
    if footer[-8:] != bytes.fromhex("57fb808b247547db"):
        print(f"{os.path.basename(path)}: bad magic", file=sys.stderr)
        return
    pos = 0
    _meta_off, pos = varint(footer, pos)
    _meta_size, pos = varint(footer, pos)
    index_off, pos = varint(footer, pos)
    index_size, pos = varint(footer, pos)
    index = read_block(data, index_off, index_size)
    for _key, handle in block_entries(index):
        off, p = varint(handle, 0)
        size, _ = varint(handle, p)
        try:
            block = read_block(data, off, size)
        except Exception as error:  # noqa: BLE001
            print(f"{os.path.basename(path)}: block {off} failed: {error}", file=sys.stderr)
            continue
        for ikey, value in block_entries(block):
            if len(ikey) < 8:
                continue
            user_key, tail = ikey[:-8], ikey[-8:]
            packed = struct.unpack("<Q", tail)[0]
            seq, kind = packed >> 8, packed & 0xFF
            found.append((seq, user_key, kind, value))


def read_wal(path, found):
    data = open(path, "rb").read()
    pos, buf = 0, b""
    while pos + 7 <= len(data):
        if (pos % 32768) > 32768 - 7:
            pos += 32768 - (pos % 32768)
            continue
        _crc, length, kind = struct.unpack("<IHB", data[pos:pos + 7])
        pos += 7
        payload = data[pos:pos + length]
        pos += length
        if kind == 0 and length == 0:
            continue
        if kind in (1, 2):
            buf = payload
        else:
            buf += payload
        if kind in (1, 4):
            batch = buf
            buf = b""
            if len(batch) < 12:
                continue
            seq = struct.unpack("<Q", batch[:8])[0]
            count = struct.unpack("<I", batch[8:12])[0]
            p = 12
            for i in range(count):
                if p >= len(batch):
                    break
                rec = batch[p]
                p += 1
                klen, p = varint(batch, p)
                key = batch[p:p + klen]
                p += klen
                value = b""
                if rec == 1:
                    vlen, p = varint(batch, p)
                    value = batch[p:p + vlen]
                    p += vlen
                found.append((seq + i, key, rec, value))


def load(directory):
    found = []
    for name in sorted(os.listdir(directory)):
        path = os.path.join(directory, name)
        if name.endswith(".ldb"):
            read_table(path, found)
        elif name.endswith(".log"):
            read_wal(path, found)
    latest = {}
    for seq, key, kind, value in found:
        if key not in latest or latest[key][0] < seq:
            latest[key] = (seq, kind, value)
    return latest


def main():
    directory, key = sys.argv[1], sys.argv[2]
    out = sys.argv[3] if len(sys.argv) > 3 else None
    latest = load(directory)
    if key == "--keys":
        for k, (seq, kind, value) in sorted(latest.items(), key=lambda item: item[1][0]):
            print(seq, kind, k.decode("utf-8", "replace"), len(value))
        return
    entry = latest.get(key.encode())
    if not entry:
        print("missing")
        return
    seq, kind, value = entry
    text = value.decode("utf-8", "replace")
    if out:
        open(out, "w", encoding="utf-8").write(text)
        print(f"seq {seq} kind {kind} -> {out} ({len(text)} chars)")
    else:
        print(text)


if __name__ == "__main__":
    main()
