#!/usr/bin/env python3
"""Run the BDOS diagnostic through the public native session API."""
import argparse
import ctypes as C
import json
from pathlib import Path
from guest import prepare,verify

def main():
    p=argparse.ArgumentParser()
    for n in ('library','rom','disk','output'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    media=a.output/'guest.juk';prepare(a.disk,media)
    lib=C.CDLL(str(a.library.resolve()));ptr=C.c_void_p;u=C.c_uint
    signatures={'create':([u],ptr),'load':([ptr,u,ptr,C.c_size_t],C.c_int),
      'mount':([ptr,ptr,C.c_size_t,C.c_int],C.c_int),'power':([ptr,C.c_int],C.c_int),
      'run':([ptr,u],u),'key':([ptr,u,C.c_int],C.c_int),'video':([ptr],ptr),
      'width':([ptr],u),'height':([ptr],u),'disk_data':([ptr],ptr),'destroy':([ptr],None)}
    for name,(args,result) in signatures.items():
        fn=getattr(lib,'dac_'+name);fn.argtypes=args;fn.restype=result
    s=lib.dac_create(0);assert s
    rom=a.rom.read_bytes();disk=media.read_bytes()
    assert lib.dac_load(s,0,rom,len(rom))==0 and lib.dac_mount(s,disk,len(disk),1)==0
    assert lib.dac_power(s,1)==0
    schedule=[]
    for start,text in [(2000,'TDD'),(16000,'fdc25\r')]:
        for i,ch in enumerate(text):schedule.extend([(start+280*i,ord(ch),1),(start+280*i+120,0,0)])
    (a.output/'input.keys').write_text(''.join(f'{t} {k:02x} {d}\n' for t,k,d in schedule))
    cycle=0
    for t,key,down in schedule+[(90000,0,0)]:
        target=t*2000
        while cycle<target:
            advanced=lib.dac_run(s,min(20000,target-cycle));assert advanced;cycle+=advanced
        assert lib.dac_key(s,key,down)==0
    w,h=lib.dac_width(s),lib.dac_height(s)
    rgba=C.string_at(lib.dac_video(s),w*h*4);packed=bytearray(w*h//8)
    for i in range(w*h):
        if rgba[4*i]==0xa0:packed[i//8]|=128>>(i%8)
    (a.output/'final.pbm').write_bytes(f'P4\n{w} {h}\n'.encode()+bytes(v^255 for v in packed))
    from analyze import text_rows,font_table
    rows=text_rows(packed,font_table(rom));assert 'FDC25 PASS' in rows and any(row.startswith('A>') for row in rows[rows.index('FDC25 PASS')+1:]),rows
    after=C.string_at(lib.dac_disk_data(s),len(disk));report=verify(disk,after)
    (a.output/'written.juk').write_bytes(after)
    report.update(final_text=rows,cycles=cycle)
    (a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    lib.dac_destroy(s);print(json.dumps(report))

if __name__=='__main__':main()
