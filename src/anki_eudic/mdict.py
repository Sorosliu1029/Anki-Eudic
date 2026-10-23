"""A small, read-only reader for MDict ``.mdx``/``.mdd`` files (format version 2.x).

Only the parts of the format needed for lookups are implemented: the header, the
(optionally ``Encrypted="2"``) key-block index and the record blocks. Keys are indexed
once into an SQLite cache outside the dictionary directory, so later lookups read and
decompress a single record block instead of scanning the whole file.

The dictionary files themselves are only ever opened for reading.
"""

from __future__ import annotations

import bisect
import hashlib
import os
import re
import sqlite3
import struct
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path

_INDEX_SCHEMA_VERSION = 1


class MdictError(Exception):
    """Raised for unsupported or corrupt MDict files."""


# --- RIPEMD-128 (only used to derive the key-index decryption key) -----------------

_R_LEFT = (
    list(range(16))
    + [7, 4, 13, 1, 10, 6, 15, 3, 12, 0, 9, 5, 2, 14, 11, 8]
    + [3, 10, 14, 4, 9, 15, 8, 1, 2, 7, 0, 6, 13, 11, 5, 12]
    + [1, 9, 11, 10, 0, 8, 12, 4, 13, 3, 7, 15, 14, 5, 6, 2]
)
_R_RIGHT = (
    [5, 14, 7, 0, 9, 2, 11, 4, 13, 6, 15, 8, 1, 10, 3, 12]
    + [6, 11, 3, 7, 0, 13, 5, 10, 14, 15, 8, 12, 4, 9, 1, 2]
    + [15, 5, 1, 3, 7, 14, 6, 9, 11, 8, 12, 2, 10, 0, 4, 13]
    + [8, 6, 4, 1, 3, 11, 15, 0, 5, 12, 2, 13, 9, 7, 10, 14]
)
_S_LEFT = (
    [11, 14, 15, 12, 5, 8, 7, 9, 11, 13, 14, 15, 6, 7, 9, 8]
    + [7, 6, 8, 13, 11, 9, 7, 15, 7, 12, 15, 9, 11, 7, 13, 12]
    + [11, 13, 6, 7, 14, 9, 13, 15, 14, 8, 13, 6, 5, 12, 7, 5]
    + [11, 12, 14, 15, 14, 15, 9, 8, 9, 14, 5, 6, 8, 6, 5, 12]
)
_S_RIGHT = (
    [8, 9, 9, 11, 13, 15, 15, 5, 7, 7, 8, 11, 14, 14, 12, 6]
    + [9, 13, 15, 7, 12, 8, 9, 11, 7, 7, 12, 7, 6, 15, 13, 11]
    + [9, 7, 15, 11, 8, 6, 6, 14, 12, 13, 5, 14, 13, 13, 7, 5]
    + [15, 5, 8, 11, 14, 14, 6, 14, 6, 9, 12, 9, 12, 5, 15, 8]
)
_K_LEFT = (0x00000000, 0x5A827999, 0x6ED9EBA1, 0x8F1BBCDC)
_K_RIGHT = (0x50A28BE6, 0x5C4DD124, 0x6D703EF3, 0x00000000)
_MASK = 0xFFFFFFFF


def _f(round_: int, x: int, y: int, z: int) -> int:
    if round_ == 0:
        return x ^ y ^ z
    if round_ == 1:
        return (x & y) | (~x & z)
    if round_ == 2:
        return (x | ~y) ^ z
    return (x & z) | (y & ~z)


def _rol(value: int, shift: int) -> int:
    value &= _MASK
    return ((value << shift) | (value >> (32 - shift))) & _MASK


def ripemd128(data: bytes) -> bytes:
    """Return the RIPEMD-128 digest of ``data`` (absent from :mod:`hashlib`)."""
    message = bytearray(data)
    bit_length = len(data) * 8
    message.append(0x80)
    while len(message) % 64 != 56:
        message.append(0)
    message += struct.pack("<Q", bit_length & 0xFFFFFFFFFFFFFFFF)
    h = [0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476]
    for chunk in range(0, len(message), 64):
        x = struct.unpack("<16I", message[chunk : chunk + 64])
        al, bl, cl, dl = h
        ar, br, cr, dr = h
        for j in range(64):
            round_ = j // 16
            t = _rol(al + _f(round_, bl, cl, dl) + x[_R_LEFT[j]] + _K_LEFT[round_], _S_LEFT[j])
            al, dl, cl, bl = dl, cl, bl, t
            t = _rol(
                ar + _f(3 - round_, br, cr, dr) + x[_R_RIGHT[j]] + _K_RIGHT[round_],
                _S_RIGHT[j],
            )
            ar, dr, cr, br = dr, cr, br, t
        t = (h[1] + cl + dr) & _MASK
        h[1] = (h[2] + dl + ar) & _MASK
        h[2] = (h[3] + al + br) & _MASK
        h[3] = (h[0] + bl + cr) & _MASK
        h[0] = t
    return struct.pack("<4I", *h)


def _fast_decrypt(data: bytes, key: bytes) -> bytes:
    output = bytearray(data)
    previous = 0x36
    for i, byte in enumerate(data):
        value = ((byte >> 4) | (byte << 4)) & 0xFF
        output[i] = value ^ previous ^ (i & 0xFF) ^ key[i % len(key)]
        previous = byte
    return bytes(output)


def _decompress(block: bytes, expected_size: int | None = None) -> bytes:
    kind = block[:4]
    payload = block[8:]
    if kind == b"\x00\x00\x00\x00":
        return payload
    if kind == b"\x02\x00\x00\x00":
        return zlib.decompress(payload)
    if kind == b"\x01\x00\x00\x00":
        try:
            import lzo  # type: ignore[import-not-found]
        except ImportError as error:  # pragma: no cover - depends on optional package
            raise MdictError(
                "LZO-compressed MDict blocks require the python-lzo package"
            ) from error
        size = expected_size if expected_size is not None else len(payload) * 8
        return lzo.decompress(payload, False, size)  # pragma: no cover
    raise MdictError(f"Unknown MDict block compression {kind!r}")


# --- Index -------------------------------------------------------------------------


def default_cache_dir() -> Path:
    """Return the per-user cache directory used for MDict key indexes."""
    if override := os.environ.get("ANKI_EUDIC_CACHE_DIR"):
        return Path(override).expanduser()
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    elif os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "anki-eudic"


def normalize_key(key: str) -> str:
    """Normalize a key the way case-insensitive MDict dictionaries compare them."""
    return key.strip().casefold()


@dataclass(frozen=True, slots=True)
class _RecordBlock:
    file_offset: int
    compressed_size: int
    decompressed_offset: int
    decompressed_size: int


class MdictFile:
    """Read-only key/value access to a single ``.mdx`` or ``.mdd`` file."""

    def __init__(self, path: str | Path, cache_dir: str | Path | None = None) -> None:
        self.path = Path(path).expanduser()
        if not self.path.is_file():
            raise FileNotFoundError(self.path)
        self.is_mdd = self.path.suffix.lower() == ".mdd"
        self.header = self._read_header()
        version = float(self.header.get("GeneratedByEngineVersion", "2.0"))
        if version < 2.0:
            raise MdictError(f"MDict engine version {version} is not supported")
        encrypted = int(self.header.get("Encrypted", "0") or 0)
        if encrypted & 1:
            raise MdictError("Record-encrypted (registered) MDict files are not supported")
        self._encrypted_index = bool(encrypted & 2)
        if self.is_mdd:
            self.encoding = "utf-16-le"
        else:
            encoding = self.header.get("Encoding", "UTF-8").upper() or "UTF-8"
            self.encoding = {"GBK": "gb18030", "GB2312": "gb18030", "UTF-16": "utf-16-le"}.get(
                encoding, encoding
            )
        self._cache_dir = Path(cache_dir).expanduser() if cache_dir else default_cache_dir()
        self._db = self._open_index()
        self._blocks = [
            _RecordBlock(*row)
            for row in self._db.execute(
                "SELECT file_offset, compressed_size, decompressed_offset, decompressed_size "
                "FROM blocks ORDER BY decompressed_offset"
            )
        ]
        self._block_starts = [block.decompressed_offset for block in self._blocks]
        self._cached_block: tuple[int, bytes] | None = None

    # Header ---------------------------------------------------------------------

    def _read_header(self) -> dict[str, str]:
        with self.path.open("rb") as handle:
            (size,) = struct.unpack(">I", handle.read(4))
            raw = handle.read(size)
            handle.read(4)  # adler32 checksum
            self._keyword_section_offset = handle.tell()
        text = raw.decode("utf-16-le", errors="replace").rstrip("\x00")
        return {
            name: _unescape_attr(value)
            for name, value in re.findall(r'(\w+)="((?:[^"\\]|\\.)*)"', text)
        }

    # Index construction ---------------------------------------------------------

    def _index_path(self) -> Path:
        stat = self.path.stat()
        identity = f"{self.path.resolve()}|{stat.st_size}|{int(stat.st_mtime)}"
        digest = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:16]
        safe_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", self.path.name)
        return self._cache_dir / f"{safe_stem}.{digest}.v{_INDEX_SCHEMA_VERSION}.sqlite3"

    def _open_index(self) -> sqlite3.Connection:
        index_path = self._index_path()
        if index_path.exists():
            connection = sqlite3.connect(f"file:{index_path}?mode=ro", uri=True)
            try:
                connection.execute("SELECT 1 FROM entries LIMIT 1")
                return connection
            except sqlite3.DatabaseError:
                connection.close()
                index_path.unlink(missing_ok=True)
        index_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = index_path.with_suffix(".tmp")
        temporary.unlink(missing_ok=True)
        connection = sqlite3.connect(temporary)
        try:
            self._build_index(connection)
            connection.commit()
        finally:
            connection.close()
        os.replace(temporary, index_path)
        return sqlite3.connect(f"file:{index_path}?mode=ro", uri=True)

    def _build_index(self, connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE entries (key TEXT NOT NULL, norm TEXT NOT NULL,
                                  offset INTEGER NOT NULL, length INTEGER NOT NULL);
            CREATE TABLE blocks (file_offset INTEGER, compressed_size INTEGER,
                                 decompressed_offset INTEGER, decompressed_size INTEGER);
            """
        )
        with self.path.open("rb") as handle:
            handle.seek(self._keyword_section_offset)
            sizes = handle.read(40)
            handle.read(4)  # checksum
            block_count, _entries, _info_decompressed, info_size, key_blocks_size = struct.unpack(
                ">5Q", sizes
            )
            info = handle.read(info_size)
            if self._encrypted_index:
                key = ripemd128(info[4:8] + struct.pack("<I", 0x3695))
                info = info[:8] + _fast_decrypt(info[8:], key)
            compressed_sizes = self._parse_key_block_info(_decompress(info), block_count)
            keys: list[tuple[int, str]] = []
            for size in compressed_sizes:
                keys.extend(self._parse_key_block(_decompress(handle.read(size))))
            if handle.tell() != self._keyword_section_offset + 44 + info_size + key_blocks_size:
                raise MdictError("Unexpected key section size")

            record_count, _record_entries, record_info_size, _record_size = struct.unpack(
                ">4Q", handle.read(32)
            )
            record_info = handle.read(record_info_size)
            file_offset = handle.tell()
            decompressed_offset = 0
            blocks = []
            for i in range(record_count):
                compressed, decompressed = struct.unpack_from(">2Q", record_info, i * 16)
                blocks.append((file_offset, compressed, decompressed_offset, decompressed))
                file_offset += compressed
                decompressed_offset += decompressed
        connection.executemany("INSERT INTO blocks VALUES (?, ?, ?, ?)", blocks)
        rows = []
        for i, (offset, key) in enumerate(keys):
            end = keys[i + 1][0] if i + 1 < len(keys) else decompressed_offset
            rows.append((key, normalize_key(key), offset, end - offset))
        connection.executemany("INSERT INTO entries VALUES (?, ?, ?, ?)", rows)
        connection.execute("CREATE INDEX entries_key ON entries(key)")
        connection.execute("CREATE INDEX entries_norm ON entries(norm)")

    def _text_unit(self) -> int:
        return 2 if self.encoding.startswith("utf-16") else 1

    def _parse_key_block_info(self, data: bytes, block_count: int) -> list[int]:
        unit = self._text_unit()
        position = 0
        sizes = []
        for _ in range(block_count):
            position += 8  # entries in block
            for _bound in range(2):  # first and last key, each NUL-terminated
                (length,) = struct.unpack_from(">H", data, position)
                position += 2 + (length + 1) * unit
            compressed, _decompressed = struct.unpack_from(">2Q", data, position)
            position += 16
            sizes.append(compressed)
        return sizes

    def _parse_key_block(self, data: bytes) -> list[tuple[int, str]]:
        unit = self._text_unit()
        terminator = b"\x00" * unit
        keys = []
        position = 0
        while position < len(data):
            (offset,) = struct.unpack_from(">Q", data, position)
            position += 8
            end = data.find(terminator, position)
            while unit == 2 and end != -1 and (end - position) % 2:
                end = data.find(terminator, end + 1)
            if end == -1:
                end = len(data)
            keys.append((offset, data[position:end].decode(self.encoding, errors="replace")))
            position = end + unit
        return keys

    # Lookup ---------------------------------------------------------------------

    def __len__(self) -> int:
        return self._db.execute("SELECT COUNT(*) FROM entries").fetchone()[0]

    def keys(self, prefix: str = "") -> list[str]:
        """Return keys whose normalized form starts with ``prefix`` (for exploration)."""
        norm = normalize_key(prefix)
        rows = self._db.execute(
            "SELECT key FROM entries WHERE norm >= ? AND norm < ? ORDER BY norm",
            (norm, norm + "\U0010ffff"),
        )
        return [row[0] for row in rows]

    def lookup_raw(self, key: str) -> list[bytes]:
        """Return every record stored under ``key`` (exact match first, then case-folded)."""
        rows = self._db.execute(
            "SELECT offset, length FROM entries WHERE key = ? ORDER BY offset", (key,)
        ).fetchall()
        if not rows:
            rows = self._db.execute(
                "SELECT offset, length FROM entries WHERE norm = ? ORDER BY offset",
                (normalize_key(key),),
            ).fetchall()
        return [self._read_record(offset, length) for offset, length in rows]

    def _read_record(self, offset: int, length: int) -> bytes:
        index = bisect.bisect_right(self._block_starts, offset) - 1
        if index < 0:
            raise MdictError(f"Record offset {offset} is outside the record section")
        output = bytearray()
        position = offset
        remaining = length
        while remaining > 0 and index < len(self._blocks):
            block = self._blocks[index]
            data = self._block_data(index)
            start = position - block.decompressed_offset
            piece = data[start : start + remaining]
            output += piece
            remaining -= len(piece)
            position += len(piece)
            index += 1
        return bytes(output)

    def _block_data(self, index: int) -> bytes:
        if self._cached_block and self._cached_block[0] == index:
            return self._cached_block[1]
        block = self._blocks[index]
        with self.path.open("rb") as handle:
            handle.seek(block.file_offset)
            data = _decompress(handle.read(block.compressed_size), block.decompressed_size)
        self._cached_block = (index, data)
        return data

    def lookup_text(self, key: str) -> list[str]:
        """Decode the records for ``key`` as text (``.mdx`` only)."""
        return [
            record.decode(self.encoding, errors="replace").rstrip("\x00")
            for record in self.lookup_raw(key)
        ]

    def close(self) -> None:
        self._db.close()


def _unescape_attr(value: str) -> str:
    return (
        value.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&amp;", "&")
    )
