"""Validated, bounded reads of the selected MOBI file without copying the book."""

import os
import stat
import struct

from udeck.i18n import tr

MAX_MOBI_SIZE = 512 * 1024 * 1024
MAX_MOBI_SLICE = 64 * 1024 * 1024
MAX_MOBI_TEXT = 128 * 1024 * 1024


class MobiFile:
    def __init__(self, path, stamp=None):
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
        self.stream = os.fdopen(descriptor, "rb")
        try:
            info = os.fstat(self.stream.fileno())
            self.stamp = (info.st_size, info.st_mtime_ns)
            self.size = info.st_size
            if not stat.S_ISREG(info.st_mode) or (stamp and list(self.stamp) != stamp):
                raise OSError(tr("Book changed; refresh the library"))
            if self.size > MAX_MOBI_SIZE:
                raise ValueError(tr("MOBI file exceeds 512 MiB"))
            header = self.stream.read(78)
            if len(header) != 78 or header[60:68] != b"BOOKMOBI":
                raise ValueError(tr("Invalid MOBI file"))
            count = struct.unpack_from(">H", header, 76)[0]
            table = self.stream.read(count * 8)
            if count < 2 or len(table) != count * 8:
                raise ValueError(tr("Invalid MOBI record table"))
            offsets = [struct.unpack_from(">I", table, i * 8)[0] for i in range(count)]
            if offsets[0] < 78 + count * 8 or any(
                    end <= start or end > self.size
                    for start, end in zip(offsets, offsets[1:] + [self.size], strict=True)):
                raise ValueError(tr("Invalid MOBI record table"))
            if any(end - start > MAX_MOBI_SLICE
                   for start, end in zip(offsets, offsets[1:] + [self.size], strict=True)):
                raise ValueError(tr("MOBI record is too large"))

            def validate_record(index):
                start = offsets[index]
                end = offsets[index + 1] if index + 1 < count else self.size
                self.stream.seek(start)
                record = self.stream.read(end - start)
                if len(record) < 248 or record[16:20] != b"MOBI":
                    raise ValueError(tr("Invalid MOBI header"))
                compression, _, length, text_records, _, encryption = struct.unpack_from(">HHIHHH", record)
                header_length = struct.unpack_from(">I", record, 20)[0]
                if header_length < 232 or 16 + header_length > len(record) or not 0 < text_records < count - index:
                    raise ValueError(tr("Invalid MOBI header"))
                if encryption:
                    raise ValueError(tr("DRM-protected MOBI books are not supported"))
                if compression not in (1, 2, 17480):
                    raise ValueError(tr("Unsupported MOBI compression"))
                if length > MAX_MOBI_TEXT:
                    raise ValueError(tr("MOBI text is too large"))
                # Validate a combo book's KF8 header too, including its encryption flag.
                if struct.unpack_from(">I", record, 128)[0] & 64:
                    exth = record[16 + header_length:]
                    if len(exth) < 12 or exth[:4] != b"EXTH":
                        raise ValueError(tr("Invalid MOBI header"))
                    exth_length, entries = struct.unpack_from(">II", exth, 4)
                    if not 12 <= exth_length <= len(exth):
                        raise ValueError(tr("Invalid MOBI header"))
                    pos = 12
                    for _ in range(entries):
                        if pos + 8 > exth_length:
                            raise ValueError(tr("Invalid MOBI header"))
                        kind, size = struct.unpack_from(">II", exth, pos)
                        if size < 8 or pos + size > exth_length:
                            raise ValueError(tr("Invalid MOBI header"))
                        if kind == 121 and size == 12:
                            boundary = struct.unpack_from(">I", exth, pos + 8)[0]
                            if boundary != 0xffffffff:
                                if index or not 0 < boundary < count:
                                    raise ValueError(tr("Invalid MOBI record table"))
                                validate_record(boundary)
                        pos += size

            validate_record(0)
        except BaseException:
            self.stream.close()
            raise

    def read(self, start, end):
        if not 0 <= start <= end <= self.size or end - start > MAX_MOBI_SLICE:
            raise ValueError(tr("Invalid MOBI byte range"))
        info = os.fstat(self.stream.fileno())
        if (info.st_size, info.st_mtime_ns) != self.stamp:
            raise OSError(tr("Book changed; refresh the library"))
        self.stream.seek(start)
        data = self.stream.read(end - start)
        if len(data) != end - start:
            raise OSError(tr("Book changed; refresh the library"))
        return data

    def close(self):
        self.stream.close()
