#!/usr/bin/env python3
"""Build DAC's original MIT diagnostic ROM and glyphs; no historical bytes."""
from pathlib import Path
import json, hashlib
OUT = Path(__file__).resolve().parents[1] / 'dist/demo'
OUT.mkdir(parents=True, exist_ok=True)
# Original compact 5x7 lettering, doubled vertically inside 8x16 cells.
letters = {
'A':['01110','10001','10001','11111','10001','10001','10001'],
'B':['11110','10001','10001','11110','10001','10001','11110'],
'C':['01111','10000','10000','10000','10000','10000','01111'],
'D':['11110','10001','10001','10001','10001','10001','11110'],
'E':['11111','10000','10000','11110','10000','10000','11111'],
'F':['11111','10000','10000','11110','10000','10000','10000'],
'G':['01111','10000','10000','10111','10001','10001','01111'],
'H':['10001','10001','10001','11111','10001','10001','10001'],
'I':['11111','00100','00100','00100','00100','00100','11111'],
'J':['00111','00010','00010','00010','10010','10010','01100'],
'K':['10001','10010','10100','11000','10100','10010','10001'],
'L':['10000','10000','10000','10000','10000','10000','11111'],
'M':['10001','11011','10101','10101','10001','10001','10001'],
'N':['10001','11001','11001','10101','10011','10011','10001'],
'O':['01110','10001','10001','10001','10001','10001','01110'],
'P':['11110','10001','10001','11110','10000','10000','10000'],
'Q':['01110','10001','10001','10001','10101','10010','01101'],
'R':['11110','10001','10001','11110','10100','10010','10001'],
'S':['01111','10000','10000','01110','00001','00001','11110'],
'T':['11111','00100','00100','00100','00100','00100','00100'],
'U':['10001','10001','10001','10001','10001','10001','01110'],
'V':['10001','10001','10001','10001','10001','01010','00100'],
'W':['10001','10001','10001','10101','10101','11011','10001'],
'X':['10001','10001','01010','00100','01010','10001','10001'],
'Y':['10001','10001','01010','00100','00100','00100','00100'],
'Z':['11111','00001','00010','00100','01000','10000','11111'],
'0':['01110','10011','10101','10101','11001','10001','01110'],
'1':['00100','01100','00100','00100','00100','00100','01110'],
'2':['01110','10001','00001','00010','00100','01000','11111'],
'3':['11110','00001','00001','01110','00001','00001','11110'],
'4':['00010','00110','01010','10010','11111','00010','00010'],
'5':['11111','10000','10000','11110','00001','00001','11110'],
'6':['01110','10000','10000','11110','10001','10001','01110'],
'7':['11111','00001','00010','00100','01000','01000','01000'],
'8':['01110','10001','10001','01110','10001','10001','01110'],
'9':['01110','10001','10001','01111','00001','00001','01110'],
'.':['00000','00000','00000','00000','00000','00110','00110'],
'/':['00001','00001','00010','00100','01000','10000','10000'],
'>':['10000','01000','00100','00010','00100','01000','10000'],
'-':['00000','00000','00000','11111','00000','00000','00000'],
':':['00000','00100','00100','00000','00100','00100','00000'],
}
glyph=bytearray(4096)
for ch,rows in letters.items():
 for y in range(14):
  for c in {ord(ch),ord(ch.lower())}:
   glyph[(y+1)*128+c]=int(rows[y//2],2)<<2
(OUT/'glyphs.bin').write_bytes(glyph)
# A Z80 program draws text via the real video RAM, then polls keyboard packets.
rom=bytearray(2048)
# Use absolute jumps for reliable label fixups rather than brittle branch offsets.
program=bytearray([0xf3,0x31,0,0xf0,0x3e,0x20,0xd3,0x19,0x21,0,1,0x11,0,0x30,0x01,0x40,1,0xed,0xb0,0x21,0x90,0x31])
poll=len(program)
program+=bytes([0xdb,0x0e,0xe6,1,0xca,poll,0,0xdb,0x0c,0xfe,0xe0,0xca,poll,0,0xfe,0x9e])
enter_jump=len(program);program+=bytes([0xca,0,0,0x77,0x23,0x7c,0xfe,0x37,0xda,poll,0,0x21,0x90,0x31,0xc3,poll,0])
enter=len(program);program[enter_jump+1]=enter
program+=bytes([0x11,0x50,0,0x19,0xc3,poll,0])
rom[:len(program)]=program
text=['DAC / DANILA\'S ARCHIVE OF COMPUTING','ROBOTRON 1715M - LIVE Z80 DIAGNOSTIC','ORIGINAL DAC ROM. LOAD YOUR MEDIA FOR TOS/M.','TYPE TO TRY THE KEYBOARD.']
rom[256:576]=''.join(x.upper().ljust(80) for x in text).encode('ascii')
(OUT/'robotron.bin').write_bytes(rom)
# Boot bank is explicitly decoded by the machine, the diagnostic uses no other banks.
(OUT/'cas.bin').write_bytes(bytes([15])*256)
# 8080-compatible demo draws a pixel pattern on the real Juku/VJUGA RAM bus.
j=bytearray(16384);j[:19]=bytes([0xf3,0x21,0x00,0xd8,0x01,0xa8,0x25,0x78,0xa9,0x77,0x23,0x0b,0x78,0xb1,0xc2,7,0,0x76,0])
(OUT/'juku.bin').write_bytes(j)
(OUT/'vjuga.bin').write_bytes(j)
(OUT/'manifest.json').write_text(json.dumps({'license':'MIT','description':'Original DAC diagnostics; not historical firmware','sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.glob('*.bin')}},indent=2)+'\n')
print('Built original diagnostic ROMs and glyphs')
