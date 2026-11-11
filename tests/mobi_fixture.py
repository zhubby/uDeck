"""Small original MOBI6 books; no publisher content or conversion tools required."""

import struct


def mobi_bytes(compression=2):
    title = b"Original MOBI chapters"
    markup = ('<html><head><title>Original MOBI</title><guide>'
              '<reference type="toc" title="Contents" filepos="TOCPOS0000"/>'
              '</guide><script>console.log("UDECK_BOOK_SCRIPT_RAN");'
              'fetch("https://example.com/leak")</script></head><body>'
              '<h1>Contents</h1><p><a filepos="FIRSTPOS00">First meadow</a></p>'
              '<p><a filepos="SECONDPOS0">Second harbor</a></p>')
    for name in ("Meadow", "Harbor"):
        markup += '<mbp:pagebreak/><h1>' + name + '</h1>'
        markup += ''.join(f'<p>{i}. Original {name} paragraph and a steady journey. 中文阅读。</p>'
                          for i in range(130))
    markup += '</body></html>'
    text = markup.encode()
    first = text.index(b'<mbp:pagebreak/>')
    second = text.index(b'<mbp:pagebreak/>', first + 1)
    for key, position in ((b'TOCPOS0000', text.index(b'<h1>Contents')),
                          (b'FIRSTPOS00', first), (b'SECONDPOS0', second)):
        text = text.replace(key, f'{position:010d}'.encode())
    records = [text[i:i + 4096] for i in range(0, len(text), 4096)]
    if compression == 2:
        # PalmDOC literal runs also preserve every byte of UTF-8 text.
        records = [b''.join(bytes([len(run)]) + run
                            for i in range(0, len(record), 8)
                            for run in [record[i:i + 8]]) for record in records]
    header = bytearray(248)
    struct.pack_into('>HHIHHHH', header, 0, compression, 0, len(text), len(records), 4096, 0, 0)
    header[16:20] = b'MOBI'
    for offset, value in ((20, 232), (24, 2), (28, 65001), (32, 1234), (36, 6),
                          (84, len(header)), (88, len(title)), (108, 0xffffffff),
                          (112, 0xffffffff), (244, 0xffffffff)):
        struct.pack_into('>I', header, offset, value)
    header[95] = 9  # English; content also exercises Chinese UTF-8.
    records.insert(0, bytes(header) + title)
    pdb = bytearray(78)
    pdb[:19] = b'Original MOBI book\0'
    pdb[60:68] = b'BOOKMOBI'
    struct.pack_into('>H', pdb, 76, len(records))
    offset = len(pdb) + len(records) * 8 + 2
    table = bytearray()
    for i, record in enumerate(records):
        table += struct.pack('>II', offset, i)
        offset += len(record)
    return bytes(pdb + table + b'\0\0') + b''.join(records)
