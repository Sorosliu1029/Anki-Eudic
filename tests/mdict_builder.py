"""Build tiny synthetic MDict files for tests (no real dictionary content)."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

from anki_eudic.mdict import ripemd128


def _compress(raw: bytes) -> bytes:
    return b"\x02\x00\x00\x00" + struct.pack(">I", zlib.adler32(raw)) + zlib.compress(raw)


def _encrypt(data: bytes, key: bytes) -> bytes:
    output = bytearray()
    previous = 0x36
    for i, byte in enumerate(data):
        value = byte ^ previous ^ (i & 0xFF) ^ key[i % len(key)]
        cipher = ((value >> 4) | (value << 4)) & 0xFF
        output.append(cipher)
        previous = cipher
    return bytes(output)


def _chunks(items: list, size: int) -> list[list]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def build_mdict(
    path: Path,
    entries: list[tuple[str, bytes]],
    *,
    mdd: bool = False,
    encrypted: bool = True,
    per_block: int = 2,
) -> Path:
    """Write ``entries`` (already sorted keys, raw record bytes) as an MDict v2 file."""
    encoding = "utf-16-le" if mdd else "utf-8"
    terminator = b"\x00\x00" if mdd else b"\x00"
    tag = "Library_Data" if mdd else "Dictionary"
    header_text = (
        f'<{tag} GeneratedByEngineVersion="2.0" RequiredEngineVersion="2.0" '
        f'Encrypted="{2 if encrypted else 0}" Encoding="{"" if mdd else "UTF-8"}" '
        'KeyCaseSensitive="No" Title="Test &amp; Demo"/>\r\n\x00'
    )
    header = header_text.encode("utf-16-le")
    output = struct.pack(">I", len(header)) + header + struct.pack("<I", zlib.adler32(header))

    offsets = []
    record_stream = b""
    for _key, record in entries:
        offsets.append(len(record_stream))
        record_stream += record

    key_blocks = b""
    info = b""
    chunks = _chunks(list(zip(offsets, [key for key, _ in entries])), per_block)
    for chunk in chunks:
        raw = b"".join(
            struct.pack(">Q", off) + key.encode(encoding) + terminator for off, key in chunk
        )
        block = _compress(raw)
        key_blocks += block
        info += struct.pack(">Q", len(chunk))
        for bound in (chunk[0][1], chunk[-1][1]):
            encoded = bound.encode(encoding)
            units = len(encoded) // len(terminator)
            info += struct.pack(">H", units) + encoded + terminator
        info += struct.pack(">2Q", len(block), len(raw))
    info_block = _compress(info)
    if encrypted:
        key = ripemd128(info_block[4:8] + struct.pack("<I", 0x3695))
        info_block = info_block[:8] + _encrypt(info_block[8:], key)
    sizes = struct.pack(
        ">5Q", len(chunks), len(entries), len(info), len(info_block), len(key_blocks)
    )
    output += sizes + struct.pack(">I", zlib.adler32(sizes)) + info_block + key_blocks

    record_blocks = b""
    record_info = b""
    third = max(1, len(record_stream) // 3)
    pieces = [record_stream[i : i + third] for i in range(0, len(record_stream), third)]
    for piece in pieces:
        block = _compress(piece)
        record_blocks += block
        record_info += struct.pack(">2Q", len(block), len(piece))
    output += struct.pack(">4Q", len(pieces), len(entries), len(record_info), len(record_blocks))
    output += record_info + record_blocks
    path.write_bytes(output)
    return path
