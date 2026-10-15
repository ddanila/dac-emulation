#!/usr/bin/env python3
"""Original MIT Z80 CP/M receiver; explicit opcodes keep builds dependency-free.
DACRX NAME.EXT receives XMODEM-128/checksum over Robotron SIO B, 1200 8N1.
Refuses existing files. Cancellation closes a partial file; erase it explicitly.
"""
from pathlib import Path
code=bytearray();labels={};fix=[]
def emit(*b):code.extend(b)
def label(n):labels[n]=0x100+len(code)
def ref(op,n):emit(op,0,0);fix.append((len(code)-2,n))
def call(n):ref(0xcd,n)
def jump(n):ref(0xc3,n)
def ld_a(v):emit(0x3e,v)
def out(p,v):ld_a(v);emit(0xd3,p)
def bdos(n):emit(0x0e,n,0x11,0x5c,0,0xcd,5,0)
# Require a filename. Save no assumptions about the caller stack.
emit(0x3a,0x5d,0,0xfe,32);ref(0xca,'exit')
bdos(15);emit(0xfe,255);ref(0xc2,'exists')
bdos(22);emit(0xfe,255);ref(0xca,'exit')
for v in [0x18,4,0x44,3,0xc1,5,0xea]:out(15,v)
out(9,7);out(9,13)
ld_a(1);ref(0x32,'expected')
label('nak');ld_a(0x15);call('put')
label('next');call('get');ref(0xda,'nak')
emit(0xfe,0x18);ref(0xca,'cancel')
emit(0xfe,4);ref(0xca,'done')
emit(0xfe,1);ref(0xc2,'next')
# Read number, complement, 128 data bytes, checksum into a private buffer.
ref(0x21,'packet');emit(0x06,131)
label('read');call('get');ref(0xda,'nak');emit(0x77,0x23,0x10,0);code[-1]=(labels['read']-(0x100+len(code)))&255
ref(0x21,'packet');emit(0x7e,0x23,0xae,0xfe,255);ref(0xc2,'nak')
emit(0x23,0x06,128,0xaf)
label('sum');emit(0x86,0x23,0x10,0);code[-1]=(labels['sum']-(0x100+len(code)))&255
emit(0xbe);ref(0xc2,'nak')
ref(0x3a,'expected');emit(0x47);ref(0x3a,'packet');emit(0xb8);ref(0xca,'write')
emit(0x3c,0xb8) # packet+1 == expected: duplicate previous block
ref(0xc2,'cancel');jump('ack')
label('write');ref(0x11,'data');emit(0x0e,26,0xcd,5,0)
bdos(21);emit(0xb7);ref(0xc2,'cancel')
ref(0x21,'expected');emit(0x34)
label('ack');ld_a(6);call('put');jump('next')
label('done');bdos(16);emit(0xfe,255);ref(0xca,'failed');ld_a(6);call('put');jump('exit')
label('cancel');bdos(16)
label('failed');ld_a(0x18);call('put');jump('exit')
label('exists');bdos(16)
label('exit');emit(0x11,0x80,0,0x0e,26,0xcd,5,0,0xc3,0,0)
# Bounded polling read (~2 million clocks). Carry indicates timeout.
label('get');emit(0xc5,0x01,0,0)
label('poll');emit(0xdb,15,0xe6,1);ref(0xc2,'received');emit(0x0b,0x78,0xb1);ref(0xc2,'poll');emit(0xc1,0x37,0xc9)
label('received');emit(0xdb,13,0xb7,0xc1,0xc9)
label('put');emit(0xf5)
label('txwait');emit(0xdb,15,0xe6,4);ref(0xca,'txwait');emit(0xf1,0xd3,13,0xc9)
label('expected');emit(1)
label('packet');emit(0,0);label('data');emit(*([0]*129))
for pos,name in fix:code[pos:pos+2]=labels[name].to_bytes(2,'little')
Path(__file__).with_name('DACRX.COM').write_bytes(code)
print(f'DACRX.COM: {len(code)} bytes')
