#!/usr/bin/env python3
"""Add a source-generated console diagnostic to a disposable EKDOS DS/DD disk."""
import argparse
from pathlib import Path

def physical(offset):
    track, rest = divmod(offset, 5120)
    sector, sub = divmod(rest, 512)
    cylinder, head = (track, 0) if track < 80 else (track - 80, 1)
    return (cylinder * 2 + head) * 5120 + [0, 2, 4, 6, 8, 1, 3, 5, 7, 9][sector] * 512 + sub

def program():
    # 0100 LXI H,data; loop: MOV A,M; ORA A; JZ 0000; INX H;
    # PUSH H; MOV E,A; MVI C,2; CALL 5; POP H; JMP loop.
    code=bytes.fromhex('21 14 01 7e b7 ca 00 00 23 e5 5f 0e 02 cd 05 00 e1 c3 03 01')
    text=b'\x1bL'
    for mode,prefix in [(b'\x1b:', 'S'),(b'\x1b;', 'N'),(b'\x1b:', 'T')]:
        text+=mode
        text+=''.join(f'{prefix}{i:02d} ABCDEFGHIJKLM\r\n' for i in range(60)).encode()
    text+=b'\x1b;SCROLL COMPLETE\r\n\0'
    return code+text

def prepare(source, destination):
    raw=bytearray(source.read_bytes())
    if len(raw)!=819200: raise ValueError('requires an 819200-byte DS/DD JUK image')
    directory=bytes(raw[physical(10240+i)] for i in range(4096))
    entries=[directory[i:i+32] for i in range(0,4096,32)]
    if any(e[0]<16 and e[1:12]==b'SCROLL  COM' for e in entries): raise ValueError('SCROLL.COM already exists')
    slot=next(i for i,e in enumerate(entries) if e[0]==0xe5)
    used={0}
    for e in entries:
        if e[0]<16: used.update(e[16:32])
    code=program()
    if len(code)>4096: raise ValueError('diagnostic exceeds one allocation block')
    block=next(i for i in range(1,197) if i not in used)
    entry=bytearray(32);entry[1:12]=b'SCROLL  COM';entry[15]=(len(code)+127)//128;entry[16]=block
    for i,v in enumerate(entry): raw[physical(10240+slot*32+i)]=v
    for i,v in enumerate(code.ljust(4096,b'\0')): raw[physical(10240+block*4096+i)]=v
    if source.resolve()==destination.resolve(): raise ValueError('output must be a disposable copy')
    destination.write_bytes(raw)
    destination.with_suffix('.com').write_bytes(code)
    return {'block':block,'directory_slot':slot,'program_bytes':len(code)}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('destination',type=Path);a=p.parse_args()
    print(prepare(a.source,a.destination))
