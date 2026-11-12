"""MIT. Build the scratch-RAM diagnostic measured on PC001; requires z80asm."""
from pathlib import Path
import subprocess
out=Path(__file__).parent
cases=[('MOV','ld a,(de)\n ld (hl),a'),('STORE','ld (hl),a'),('IMM','ld (hl),05ah'),('ABS','ld (04000h),a'),('WORD','ld (04000h),de'),('INC','inc (hl)'),('SET','set 7,(hl)'),('LDI','ex de,hl\n ldi'),('LDD','ex de,hl\n ldd'),('LDIR','ex de,hl\n ldir'),('LDDR','ex de,hl\n lddr'),('EXSP','ex (sp),hl'),('PUSH','push de'),('IX','ld (ix+0),a'),('READWORD','ld hl,(04000h)'),('READDE','ld de,(04000h)\n ex de,hl'),('POP','pop hl'),('READA','ld a,(04000h)'),('RLD','rld'),('RRD','rrd')]
s=' org 0f100h\n di\n ld (oldsp),sp\n ld sp,0ff00h\n'
for n,(name,op) in enumerate(cases):
 s+=f''' call setup
 ld hl,04000h
 ld de,0f060h
 ld ix,04000h
 ld bc,1
 ld a,05ah
'''
 if name in ('EXSP','POP'):s+=' ld sp,04000h\n'
 if name=='PUSH':s+=' ld sp,04002h\n'
 s+=op+'\n ld (0f080h),hl\n ld (0f082h),a\n ld sp,0ff00h\n'
 for col,(bank,address) in enumerate([(0x11,0x4000),(0x11,0x4001),(0x22,0x4000),(0x22,0x4001),(0x22,0xf080),(0x22,0xf081),(0x22,0xf082)]):
  s+=f" ld a,{bank}\n out (24h),a\n ld a,({address})\n ld hl,res{n}+{col*3}\n call hex\n"
s+=''' ld a,22h
 out (24h),a
 ld sp,(oldsp)
 ld de,results
 ld c,9
 call 5
 jp 0
setup:
 ld a,11h
 out (24h),a
 ld hl,01111h
 ld (04000h),hl
 ld a,22h
 out (24h),a
 ld hl,02222h
 ld (04000h),hl
 ld a,05ah
 ld (0f060h),a
 ld a,21h
 out (24h),a
 ret
hex:
 push af
 rrca
 rrca
 rrca
 rrca
 call digit
 pop af
 inc hl
digit:
 and 15
 add a,'0'
 cp ':'
 jr c,store
 add a,7
store: ld (hl),a
 ret
oldsp: dw 0
results: db 13,10
'''
for n,(name,_) in enumerate(cases):s+=f" db '{name} '\nres{n}: db '00 00 00 00 00 00 00',13,10\n"
s+=" db '$'\nend:\n"
(out/'bank-body.asm').write_text(s);subprocess.run(['z80asm','-o',str(out/'body.bin'),str(out/'bank-body.asm')],check=True)
b=(out/'body.bin').read_bytes();assert len(b)<0xdf0,len(b)
# A normal COM entry copies the position-dependent common code, then jumps there.
loader=bytes.fromhex('210f011100f101')+len(b).to_bytes(2,'little')+bytes.fromhex('edb0c300f100')
assert len(loader)==15
(out/'BANK.COM').write_bytes(loader+b);print('body bytes',len(b))
