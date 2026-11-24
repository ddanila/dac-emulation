"""Generate a CP/M file write/read diagnostic; all I/O goes through BDOS."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'juku-scroll'))
from prepare import physical

def program():
    code=bytearray(); labels={}; refs=[]
    def emit(*values): code.extend(values)
    def label(name): labels[name]=0x100+len(code)
    def address(op,name):
        emit(op);refs.append((len(code),name));emit(0,0)
    def bdos(fn,ptr=None):
        if ptr: address(0x11,ptr) # LXI D
        emit(0x0e,fn,0xcd,5,0)
    def check(): emit(0xb7);address(0xc2,'fail') # ORA A / JNZ
    # Own stack, preserving the CP/M warm-boot entry at zero.
    emit(0x31,0,0x30)
    bdos(22,'fcb');emit(0xfe,0xff);address(0xca,'fail')
    bdos(26,'buffer')
    address(0x21,'buffer');emit(0x06,128,0xaf)
    label('fill');emit(0x77,0x23,0x3c,0x05);address(0xc2,'fill')
    emit(0x3e,0);address(0x32,'record')
    label('write');address(0x3a,'record');address(0x32,'buffer')
    bdos(21,'fcb');check()
    address(0x3a,'record');emit(0x3c);address(0x32,'record');emit(0xfe,8);address(0xc2,'write')
    bdos(16,'fcb');emit(0xfe,0xff);address(0xca,'fail')
    # Clear FCB extent/current-record/allocation fields before opening again.
    address(0x21,'fcb_tail');emit(0x06,24,0xaf)
    label('clear');emit(0x77,0x23,0x05);address(0xc2,'clear')
    bdos(15,'fcb');emit(0xfe,0xff);address(0xca,'fail')
    emit(0xaf);address(0x32,'record')
    label('read');bdos(20,'fcb');check()
    address(0x21,'buffer');address(0x3a,'record');emit(0xbe);address(0xc2,'fail')
    emit(0x23,0x3e,1)
    label('compare');emit(0xbe);address(0xc2,'fail');emit(0x23,0x3c,0xfe,128);address(0xc2,'compare')
    address(0x3a,'record');emit(0x3c);address(0x32,'record');emit(0xfe,8);address(0xc2,'read')
    bdos(20,'fcb');emit(0xfe,1);address(0xc2,'fail') # EOF
    bdos(16,'fcb');bdos(9,'pass');emit(0xc3,0,0)
    label('fail');bdos(9,'error');emit(0xc3,0,0)
    label('pass');code.extend(b'\r\nFDC25 PASS\r\n$')
    label('error');code.extend(b'\r\nFDC25 FAIL\r\n$')
    label('fcb');code.extend(b'\0FDC25   TST');label('fcb_tail');code.extend(bytes(24))
    label('record');emit(0)
    label('buffer');code.extend(bytes(128))
    for offset,name in refs: code[offset:offset+2]=labels[name].to_bytes(2,'little')
    return bytes(code)

def prepare(source,destination):
    if source.resolve()==destination.resolve(): raise ValueError('disposable output required')
    raw=bytearray(source.read_bytes());assert len(raw)==819200
    entries=[bytes(raw[physical(10240+i+j)] for j in range(32)) for i in range(0,4096,32)]
    assert not any(e[0]<16 and e[1:12] in (b'FDC25   COM',b'FDC25   TST') for e in entries)
    used={0}
    for e in entries:
        if e[0]<16: used.update(e[16:32])
    block=next(i for i in range(1,197) if i not in used)
    slot=next(i for i,e in enumerate(entries) if e[0]==0xe5)
    code=program();assert len(code)<=4096
    entry=bytearray(32);entry[1:12]=b'FDC25   COM';entry[15]=(len(code)+127)//128;entry[16]=block
    for i,v in enumerate(entry):raw[physical(10240+slot*32+i)]=v
    for i,v in enumerate(code.ljust(4096,b'\0')):raw[physical(10240+block*4096+i)]=v
    destination.write_bytes(raw)

def verify(before,after):
    # Decode the created file independently, and forbid changes to unrelated
    # data blocks. Directory updates and newly allocated file blocks are allowed.
    entries=[bytes(after[physical(10240+i+j)] for j in range(32)) for i in range(0,4096,32)]
    found=[e for e in entries if e[0]==0 and e[1:12]==b'FDC25   TST']
    assert len(found)==1 and found[0][15]==8
    blocks=[b for b in found[0][16:32] if b]
    content=b''.join(bytes(after[physical(10240+b*4096+i)] for i in range(4096)) for b in blocks)[:1024]
    assert content==b''.join(bytes([r])+bytes(range(1,128)) for r in range(8))
    permitted={physical(10240+i) for i in range(4096)}
    for b in blocks:permitted.update(physical(10240+b*4096+i) for i in range(4096))
    assert all(a==b or i in permitted for i,(a,b) in enumerate(zip(before,after)))
    return {'file_bytes':len(content),'allocated_blocks':blocks,'unrelated_bytes_unchanged':True}
