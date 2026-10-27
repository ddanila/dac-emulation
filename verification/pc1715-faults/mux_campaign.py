#!/usr/bin/env python3
"""Functional DL257 select-stuck faults, including A28.2 CAS suppression."""
import argparse
import gzip
import hashlib
import itertools
import json
import os
from pathlib import Path
import subprocess
import tempfile
from campaign import HERE, ROM_SHA, compare


def instrument(source):
    helper='''
static unsigned mux1,mux2; /* 0 normal, 1 select low, 2 select high */
static uint16_t mux_address(uint16_t a) {
  unsigned row=a&127,col=(a>>7)&127;
  unsigned low=(mux1==1 ? 15 : 0)|(mux2==1 ? 112 : 0);
  unsigned high=(mux1==2 ? 15 : 0)|(mux2==2 ? 112 : 0);
  return (a&0xc000) | ((row&~high)|(col&high)) |
         (((col&~low)|(row&low))<<7);
}
'''
    marker='static uint8_t undriven(experiment *x) {'
    assert source.count(marker)==1
    source=source.replace(marker,helper+'\n'+marker)
    marker='  uint8_t d=x->board.ram[a];'
    assert source.count(marker)==1
    source=source.replace(marker,'  a=mux_address(a);\n'+marker)
    marker='  uint8_t data=rom_drives ?'
    assert source.count(marker)==1
    source=source.replace(marker,'  if (mux2==1) ram_drives=0; /* A28.2 A3 is pulled high: no /CAS. */\n'+marker)
    marker='  if (!x->bit_enabled) x->original.write'
    assert source.count(marker)==1
    source=source.replace(marker,'  if (mux2==1) return;\n  a=mux_address(a);\n'+marker)
    marker='  unsigned count=0;int was_fetch=0,was_read=0;'
    assert source.count(marker)==1
    source=source.replace(marker,'''  mux1=(unsigned)strtoul(getenv("MB001_MUX1"),NULL,10);
  mux2=(unsigned)strtoul(getenv("MB001_MUX2"),NULL,10);
'''+marker)
    return source.replace('"../../machines/robotron1715/pc1715.h"',
                          json.dumps(str(HERE.parents[1]/'machines/robotron1715/pc1715.h')))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    assert hashlib.sha256(args.rom.read_bytes()).hexdigest()==ROM_SHA
    fixture=HERE/'mb001-full-reads.json.gz'
    hardware=json.loads(gzip.decompress(fixture.read_bytes()))
    reference=json.loads(gzip.decompress((HERE/'bit-results/qualification.json.gz').read_bytes()))
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder);source=root/'probe.c';binary=root/'probe'
        source.write_text(instrument((HERE/'probe.c').read_text()))
        objects=[str(HERE.parents[1]/p) for p in ['build/machines/robotron1715/pc1715.o',
                 'build/common/cpu/z80.o','build/common/trace/trace.o']]
        subprocess.run(['cc','-O2','-std=c11','-Wall','-Wextra','-Werror',str(source),
                        *objects,'-o',str(binary)],check=True)
        def run(params,m1,m2):
            env=dict(os.environ,MB001_MUX1=str(m1),MB001_MUX2=str(m2))
            return json.loads(subprocess.check_output([str(binary),str(args.rom.resolve()),
                                                       *map(str,params)],env=env))
        assert run(reference['parameters'],0,0)==reference['model']
        harness=root/'pins.c'
        harness.write_text('#define main probe_main\n#include '+json.dumps(str(source))+
            '\n#undef main\n'+r'''
int main(void) {
  for (mux1=0;mux1<3;mux1++) for(mux2=0;mux2<3;mux2++)
    for(unsigned a=0;a<65536;a++) {
      unsigned expected=a&0xc000;
      for(unsigned pin=0;pin<7;pin++) {
        unsigned mode=pin<4?mux1:mux2;
        unsigned r=(a>>(pin+(mode==2?7:0)))&1;
        unsigned c=(a>>(pin+(mode==1?0:7)))&1;
        expected|=(r<<pin)|(c<<(pin+7));
      }
      if(mux_address(a)!=expected) return 1;
    }
  experiment x={0};pc1715_init(&x.board);x.original=x.board.cpu.bus;
  x.fault=DECODER_ALIAS;x.floating=FIXED;x.bias=255;
  mux1=0;mux2=1;
  write_memory(&x,0x1234,0x5a);
  if(x.board.ram[mux_address(0x1234)]!=0) return 2;
  if(read_memory(&x,0x1234)!=255 || x.driven) return 3;
  return 0;
}
''')
        subprocess.run(['cc','-O2','-std=c11',str(harness),*objects,'-o',str(root/'pins')],check=True)
        subprocess.run([str(root/'pins')],check=True)
        patterns=['stripe:0:8:255','stripe:7:8:255',
                  'xorstripe:0:8:255:1:231','xorstripe:0:8:255:1:239',
                  'xorstripe:7:8:255:8:231','xorstripe:7:8:255:8:239']
        cases=[];best=[None]*len(hardware['runs'])
        for m1,m2,mask,pattern,write in itertools.product(range(3),range(3),(0,0xc000,0xffe0,0xffc0),patterns,range(5)):
            params=reference['parameters'][:]
            params[4]=mask;params[9]=pattern;params[13]=write
            model=run(params,m1,m2);scores=compare(hardware,model)
            config=dict(mux1=m1,mux2=m2,common_mask=mask,pattern=pattern,d3_write=write)
            cases.append(dict(config=config,scores=scores))
            for i,score in enumerate(scores):
                if best[i] is None or score['combined_prefix']>best[i]['score']['combined_prefix']:
                    best[i]=dict(config=config,score=score,model=model)
        result=dict(rom_sha256=ROM_SHA,fixture_sha256=hashlib.sha256(fixture.read_bytes()).hexdigest(),
                    source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in [HERE/'probe.c',Path(__file__),HERE/'campaign.py']},
                    base_parameters=reference['parameters'],exhaustive_pin_mapping_test_passed=True,
                    cas_suppression_test_passed=True,normal_control_preserves_simulation=True,cases=cases,best=best)
        args.output.write_bytes(gzip.compress((json.dumps(result,separators=(',',':'))+'\n').encode(),mtime=0))
        print(json.dumps(dict(cases=len(cases),best=[dict(config=b['config'],score=b['score']) for b in best]),indent=2))


if __name__=='__main__':
    main()
