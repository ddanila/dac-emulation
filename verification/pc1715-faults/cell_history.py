#!/usr/bin/env python3
"""Trace a forward fault model and perturb initial D3 cells for sensitivity only.

Temporary instrumentation leaves the committed native probe unchanged. Captured
bytes never enter the CPU; a single initial-cell flip is not a component model.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from campaign import HERE, ROM_SHA, compare


def instrument(source):
    old='  return d;\n}\nstatic uint8_t read_memory'
    assert source.count(old)==1
    source=source.replace(old,'''  fprintf(stderr,"R %llu %u %u %u %u\\n",
      (unsigned long long)x->board.cpu.cycles,external,a,
      x->bit_enabled ? bit_address(x,a,external,0) : a,d);
  return d;
}
static uint8_t read_memory''')
    old='  if (!x->bit_enabled) x->original.write'
    assert source.count(old)==1
    source=source.replace(old,'''  fprintf(stderr,"W %llu %u %u %u %u\\n",
      (unsigned long long)x->board.cpu.cycles,external,a,
      x->bit_enabled ? bit_address(x,a,external,1) : a,d);
  if (!x->bit_enabled) x->original.write''')
    old='  x->fault=(enum fault)f;'
    assert source.count(old)==1
    source=source.replace(old,'''  const char *flip=getenv("MB001_FLIP_CELL");
  if (flip) {
    unsigned long cell;
    if (!number(flip,&cell) || cell>65535) return 2;
    x->board.ram[cell]^=8;
  }
  x->fault=(enum fault)f;''')
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
    qualified=HERE/'bit-results/qualification.json.gz'
    reference=json.loads(gzip.decompress(qualified.read_bytes()))
    params=reference['parameters']
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder)
        source=root/'probe.c'
        source.write_text(instrument((HERE/'probe.c').read_text()))
        binary=root/'probe'
        objects=['build/machines/robotron1715/pc1715.o','build/common/cpu/z80.o','build/common/trace/trace.o']
        subprocess.run(['cc','-O2','-std=c11','-Wall','-Wextra','-Werror',str(source),
                        *[str(HERE.parents[1]/p) for p in objects],'-o',str(binary)],check=True)
        def run(flip=None):
            env=dict(os.environ)
            env.pop('MB001_FLIP_CELL',None)
            if flip is not None: env['MB001_FLIP_CELL']=str(flip)
            result=subprocess.run([str(binary),str(args.rom.resolve()),*map(str,params)],
                                  env=env,capture_output=True,text=True,check=True)
            return json.loads(result.stdout),result.stderr
        model,trace=run()
        assert model==reference['model'], 'Instrumentation changed the simulation'
        events=[]
        for line in trace.splitlines():
            kind,cycle,external,common,bit,data=line.split()
            events.append(dict(kind=kind,cycle=int(cycle),external=int(external),
                               common=int(common),bit=int(bit),data=int(data)))
        flips=[]
        corrected=None
        for cell in range(32):
            modified,_=run(cell)
            scores=compare(hardware,modified)
            if cell==23: corrected=modified
            i=scores[3]['combined_prefix']
            flips.append(dict(cell=cell,scores=scores,
                              run4_first_mismatch=dict(window=i+1,
                                observed=hardware['runs'][3]['fetches'][i],
                                modeled=modified['fetches'][i])))
        # Diagnostic only: the one-cell flip is not a physical fault proposal.
        # It verifies the inferred address of the next read after fixing fetch83.
        assert flips[23]['scores'][3]['combined_prefix']==83
        early=corrected['fetches'][2]
        late=corrected['fetches'][83]
        assert early['address']&31==late['address']&31==24
        assert params[13]==1  # D3 writes disabled, so cell bit is invariant.
        actual=hardware['runs'][3]['fetches']
        assert actual[2]['data']&8 and not actual[83]['data']&8
        contradiction=dict(
            scope='32-byte shared RAM alias, D3 writes disabled, CPU reads equal connector samples',
            cell=24,earlier_window=3,later_window=84,
            earlier_address=early['address'],later_address=late['address'],
            earlier_cycle=early['cycle'],later_cycle=late['cycle'],
            earlier_required_d3=1,later_required_d3=0,
            corrected_first83_intervals_match=True,
            conclusion='No static initial D3 value at this cell can satisfy both reads')
        result=dict(parameters=params,rom_sha256=ROM_SHA,
                    source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in [HERE/'probe.c',Path(__file__),HERE/'campaign.py']},
                    fixture_sha256=hashlib.sha256(fixture.read_bytes()).hexdigest(),
                    reference_sha256=hashlib.sha256(qualified.read_bytes()).hexdigest(),
                    instrumentation_preserves_full_simulation=True,
                    events=events,initial_cell_flips=flips,static_cell_contradiction=contradiction)
        args.output.write_bytes(gzip.compress((json.dumps(result,separators=(',',':'))+'\n').encode(),mtime=0))
        print(json.dumps(dict(events=len(events),run4_flip_prefixes=[
            [f['cell'],f['scores'][3]['combined_prefix']] for f in flips]),indent=2))


if __name__=='__main__':
    main()
