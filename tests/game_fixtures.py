"""Original tiny programs, with no commercial game data or console logos."""

import struct
from pathlib import Path


def gameboy():
    rom = bytearray(32768)
    rom[0x100:0x103] = bytes.fromhex("c3 50 01")
    rom[0x134:0x13e] = b"UDECK TEST"
    code = bytes.fromhex("f3 af e0 40 3e e4 e0 47 21 00 80 3e aa 06 10 22 05 20 fc 3e 91 e0 40 0e 00 06 ff 05 20 fd 0c 79 e0 47 18 f5")
    rom[0x150:0x150 + len(code)] = code
    checksum = 0
    for byte in rom[0x134:0x14d]:
        checksum = (checksum - byte - 1) & 255
    rom[0x14d] = checksum
    rom[0x14e:0x150] = (sum(rom) & 65535).to_bytes(2, "big")
    return rom


def nes():
    # 6502 initialization, palette, background tile, then an idle loop.
    code = bytearray.fromhex("78 d8 a2 ff 9a a9 00 8d 00 20 8d 01 20 2c 02 20 10 fb "
                             "a9 3f 8d 06 20 a9 00 8d 06 20 a9 21 8d 07 20 "
                             "a9 16 8d 07 20 a9 30 8d 07 20 a9 0f 8d 07 20 "
                             "a9 00 8d 05 20 8d 05 20 a9 0a 8d 01 20")
    loop = 0x8000 + len(code)
    code += bytes([0x4c, loop & 255, loop >> 8])
    prg, chr_rom = bytearray(16384), bytearray(8192)
    prg[:len(code)] = code
    prg[-6:] = struct.pack("<HHH", 0x8000, 0x8000, 0x8000)
    chr_rom[:16] = bytes([0xaa, 0x55] * 4 + [0] * 8)
    return b"NES\x1a" + bytes([1, 1]) + bytes(10) + prg + chr_rom


def gba():
    rom = bytearray(32768)
    struct.pack_into("<I", rom, 0, 0xea00002e)  # Branch to our ARM code at 0xc0.
    rom[0xa0:0xac] = b"UDECK RED   "
    rom[0xac:0xb0] = b"UDKG"
    rom[0xb0:0xb2] = b"00"
    rom[0xb2] = 0x96
    rom[0xbd] = (-sum(rom[0xa0:0xbd]) - 0x19) & 255
    # Set mode 3 + BG2, fill 240 x 160 pixels red, idle forever.
    words = [0xe59f0024, 0xe59f1024, 0xe1c010b0, 0xe59f0020, 0xe3a0101f,
             0xe59f201c, 0xe0c010b2, 0xe2522001, 0x1afffffc, 0xeafffffe, 0xe1a00000,
             0x04000000, 0x00000403, 0x06000000, 0x00009600]
    for index, word in enumerate(words):
        struct.pack_into("<I", rom, 0xc0 + 4 * index, word)
    return rom


def create_original_roms(root):
    paths = []
    for platform, name, data in (("gb", "Original stripes.gb", gameboy()),
                                  ("nes", "Original tiles.nes", nes()),
                                  ("gba", "Original red.gba", gba())):
        path = Path(root) / platform / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.read_bytes() != data:
            raise FileExistsError(path)
        path.write_bytes(data)
        paths.append(path)
    return paths
