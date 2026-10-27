#!/usr/bin/env python3
"""Retain the complete best simple forward run and a bounded timed-fault control."""
import argparse
import gzip
import hashlib
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
    base=['decoder-ram-alias','fixed',255,0,0xffe0,0,0,12000,255,
          'xorstripe:0:8:255:1:231',3,0,0,1,0,0]
    def run(parameters):
        return json.loads(subprocess.check_output([str(HERE.parents[1]/'build/pc1715-fault-probe'),
                                                   str(args.rom.resolve())]+list(map(str,parameters))))
    model=run(base);scores=compare(hardware,model)
    mismatches=[]
    for actual,score in zip(hardware['runs'],scores):
        i=score['combined_prefix']
        mismatches.append(dict(run=actual['name'],window=i+1,
                               observed=actual['fetches'][i],modeled=model['fetches'][i]))
    timed=[]
    for clock in range(601):
        candidate=run(base+[clock,2])
        timed.append(dict(change_cycle=clock,scores=compare(hardware,candidate)))
    result=dict(rom_sha256=ROM_SHA,fixture_sha256=hashlib.sha256(fixture.read_bytes()).hexdigest(),
                source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in [HERE/'probe.c',Path(__file__),HERE/'campaign.py']},
                parameters=base,model=model,scores=scores,first_mismatches=mismatches,
                timed_write_sweep=dict(initial_write_mode=1,next_write_mode=2,
                                      change_clock_min=0,change_clock_max=600,cases=timed))
    raw=(json.dumps(result,separators=(',',':'))+'\n').encode()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_bytes(gzip.compress(raw,mtime=0))
    print(json.dumps(dict(scores=scores,first_mismatches=mismatches,
                         timed_best=[max(c['scores'][i]['combined_prefix'] for c in timed)
                                     for i in range(len(hardware['runs']))]),indent=2))


if __name__=='__main__':
    main()
