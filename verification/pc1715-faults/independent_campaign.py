#!/usr/bin/env python3
"""Test independent D3 addressing; CPU execution never consumes capture data."""
import argparse
import gzip
import hashlib
import itertools
import json
from pathlib import Path
import subprocess
from campaign import HERE, ROM_SHA, compare


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if hashlib.sha256(args.rom.read_bytes()).hexdigest()!=ROM_SHA:
        parser.error('Unexpected ROM hash')
    fixture=HERE/'mb001-full-reads.json.gz'
    hardware=json.loads(gzip.decompress(fixture.read_bytes()))
    assert all(sum(r['clocks'] for r in run['fetches'][:16])+2<256
               for run in hardware['runs'])
    best=[None]*len(hardware['runs'])
    cases=[]
    promoted=0
    # Independent chip retains 3..16 low address bits; common RAM retains 3..8.
    # The narrow sweep deliberately tests the structural limitation of stage 2.
    configs=itertools.product(range(3,9),range(3,17),range(5),range(2),range(3,6),(231,239))
    for common_bits,chip_bits,write,invert,mode,xor in configs:
        params=['decoder-ram-alias','fixed',255,0,
                65535^((1<<common_bits)-1),0,0,256,255,
                f'xorstripe:0:8:255:1:{xor}',3,
                65535^((1<<chip_bits)-1),0,write,invert,mode]
        def run():
            return json.loads(subprocess.check_output([
                str(HERE.parents[1]/'build/pc1715-fault-probe'),str(args.rom.resolve()),
                *map(str,params)]))
        model=run()
        scores=compare(hardware,model)
        if max(s['combined_prefix'] for s in scores)>=16:
            params[7]=12000
            model=run()
            scores=compare(hardware,model)
            promoted+=1
        cases.append(dict(parameters=params[:],scores=scores))
        for i,score in enumerate(scores):
            if best[i] is None or score['combined_prefix']>best[i]['score']['combined_prefix']:
                best[i]=dict(parameters=params[:],score=score,model=model)
    result=dict(rom_sha256=ROM_SHA,fixture_sha256=hashlib.sha256(fixture.read_bytes()).hexdigest(),
                source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in [HERE/'probe.c',Path(__file__),HERE/'campaign.py']},
                promoted=promoted,cases=cases,best=best)
    args.output.write_bytes(gzip.compress((json.dumps(result,separators=(',',':'))+'\n').encode(),mtime=0))
    print(json.dumps(dict(cases=len(cases),promoted=promoted,
                         best=[dict(parameters=b['parameters'],score=b['score']) for b in best]),indent=2))


if __name__=='__main__':
    main()
