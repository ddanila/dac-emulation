#!/usr/bin/env python3
"""Bounded weak-D3 row-retention experiment using PC1715 row/column mapping.

This is a deterministic fault abstraction, not an analog DRAM simulation.
All 128 rows start freshly restored; expiration clears D3 throughout one row,
across columns and banks. Memory accesses restore rows; CPU refresh optionally
reaches them. No observed data is supplied to the CPU.
"""
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
static uint64_t row_last[128];
static unsigned retention_limit,refresh_enabled;
static void restore_row(experiment *x,uint16_t a,uint64_t cycle) {
  if (!retention_limit) return;
  unsigned row=a&127;
  if (cycle-row_last[row]>retention_limit)
    for (unsigned cell=row;cell<65536;cell+=128) x->board.ram[cell]&=~8u;
  row_last[row]=cycle;
}
'''
    marker='static uint8_t undriven(experiment *x) {'
    assert source.count(marker)==1
    source=source.replace(marker,helper+'\n'+marker)
    marker='  uint8_t d=x->board.ram[a];'
    assert source.count(marker)==1
    source=source.replace(marker,'  restore_row(x,a,x->board.cpu.cycles);\n'+marker)
    marker='  if (!x->bit_enabled) x->original.write'
    assert source.count(marker)==1
    source=source.replace(marker,'  restore_row(x,a,x->board.cpu.cycles);\n'+marker)
    marker='  unsigned count=0;int was_fetch=0,was_read=0;'
    assert source.count(marker)==1
    source=source.replace(marker,'''  retention_limit=(unsigned)strtoul(getenv("MB001_RETENTION"),NULL,10);
  refresh_enabled=(unsigned)strtoul(getenv("MB001_REFRESH"),NULL,10);
  int was_refresh=0;
'''+marker)
    marker='    uint64_t pins=x->board.cpu.pins;'
    assert source.count(marker)==1
    source=source.replace(marker,marker+'''
    int refreshing=(pins&(Z80_MREQ|Z80_RFSH))==(Z80_MREQ|Z80_RFSH);
    if (refresh_enabled && refreshing && !was_refresh) {
      uint16_t a=(Z80_GET_ADDR(pins)&~x->mask)|x->value;
      restore_row(x,a,x->board.cpu.cycles-1);
    }
    was_refresh=refreshing;''')
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
        objects=['build/machines/robotron1715/pc1715.o','build/common/cpu/z80.o','build/common/trace/trace.o']
        subprocess.run(['cc','-O2','-std=c11','-Wall','-Wextra','-Werror',str(source),
                        *[str(HERE.parents[1]/p) for p in objects],'-o',str(binary)],check=True)
        def run(params,limit,refresh):
            env=dict(os.environ,MB001_RETENTION=str(limit),MB001_REFRESH=str(refresh))
            return json.loads(subprocess.check_output([str(binary),str(args.rom.resolve()),
                                                       *map(str,params)],env=env))
        for limit in [0,1000000]:
            for refresh in [0,1]:
                assert run(reference['parameters'],limit,refresh)==reference['model']
        # Direct state checks: same row across columns/banks decays together;
        # another row is unaffected; restore-before-deadline extends retention.
        harness=root/'rows.c'
        harness.write_text('#define main probe_main\n#include '+json.dumps(str(source))+
            '\n#undef main\n'+r'''
int main(void) {
  experiment x={0}; memset(x.board.ram,255,sizeof x.board.ram);
  retention_limit=10;
  restore_row(&x,3,5); restore_row(&x,131,14);
  if (x.board.ram[3]!=255) return 1;
  restore_row(&x,3,25);
  if (x.board.ram[3]!=247 || x.board.ram[131]!=247 || x.board.ram[16387]!=247) return 2;
  if (x.board.ram[4]!=255) return 3;
  return 0;
}
''')
        subprocess.run(['cc','-O2','-std=c11',str(harness),
                        *[str(HERE.parents[1]/p) for p in objects],'-o',str(root/'rows')],check=True)
        subprocess.run([str(root/'rows')],check=True)
        best=[None]*len(hardware['runs']);cases=[]
        # 4916 clocks = nominal 2 ms at the model's 2.458 MHz clock.
        for bits,xor,refresh,limit in itertools.product((5,6),(231,239),(0,1),[*range(1,641),4916]):
            params=reference['parameters'][:]
            params[4]=65535^((1<<bits)-1)
            params[9]=f'xorstripe:0:8:255:1:{xor}'
            model=run(params,limit,refresh);scores=compare(hardware,model)
            config=dict(common_bits=bits,xor=xor,cpu_refresh=refresh,retention_clocks=limit)
            cases.append(dict(config=config,scores=scores))
            for i,score in enumerate(scores):
                if best[i] is None or score['combined_prefix']>best[i]['score']['combined_prefix']:
                    best[i]=dict(config=config,score=score,model=model)
        result=dict(rom_sha256=ROM_SHA,fixture_sha256=hashlib.sha256(fixture.read_bytes()).hexdigest(),
                    source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in [HERE/'probe.c',Path(__file__),HERE/'campaign.py']},
                    base_parameters=reference['parameters'],row_tests_passed=True,
                    nondecaying_controls_preserve_simulation=True,cases=cases,best=best)
        args.output.write_bytes(gzip.compress((json.dumps(result,separators=(',',':'))+'\n').encode(),mtime=0))
        print(json.dumps(dict(cases=len(cases),best=[dict(config=b['config'],score=b['score']) for b in best]),indent=2))


if __name__=='__main__':
    main()
