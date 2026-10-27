#!/usr/bin/env python3
"""Screen per-chip RAM faults; promote candidates before claiming a longer match."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
from campaign import HERE, ROM_SHA, compare


def configurations(xor_mask=None):
    # Common alias widths admitted by the early stack-write evidence, plus
    # wider controls. Individual-chip faults never alter the other seven bits.
    for retained in range(3, 9):
        common_mask=(0xffff << retained) & 0xffff
        for bit_mask in range(1 << min(retained, 7)):
            for bit_value in sorted({0, bit_mask}):
                for write in range(5):
                    for read_xor in [0, 1]:
                        # Two uniform power-on patterns giving initial 08/FF
                        # under the specified sense polarity; not an opcode image.
                        pattern='stripe:0:0:247' if read_xor else 'stripe:0:8:255'
                        if xor_mask is not None:
                            pattern='xor'+pattern+f':1:{xor_mask}'
                        for address_mode in [0,1,2] if bit_mask else [0]:
                            yield ['decoder-ram-alias','fixed',255,0,common_mask,0,
                                   0,256,255,pattern,3,bit_mask,bit_value,write,read_xor,address_mode]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--probe',type=Path,default=HERE.parents[1]/'build/pc1715-fault-probe')
    parser.add_argument('--xor-mask',type=lambda x:int(x,0),default=None,
                        help='Optional regular startup XOR on address bit1 (0..255)')
    parser.add_argument('--hardware',type=Path,default=HERE/'mb001.json')
    args=parser.parse_args()
    if args.xor_mask is not None and not 0<=args.xor_mask<=255:
        parser.error('xor-mask must be 0..255')
    if hashlib.sha256(args.rom.read_bytes()).hexdigest()!=ROM_SHA:
        parser.error('Unexpected ROM hash')
    fixture=args.hardware.read_bytes()
    hardware=json.loads(gzip.decompress(fixture) if args.hardware.suffix=='.gz' else fixture)
    # A correct first-16 match must finish within the screen, otherwise the
    # promotion rule could silently discard a slow but matching candidate.
    if any(sum(f['clocks'] for f in r['fetches'][:16])+1>=256 for r in hardware['runs']):
        parser.error('The first 16 observed intervals exceed the 256-clock screen')
    names=['fault','floating','bias','decay','mask','value','ram_seed','ticks',
           'initial_bus','ram_pattern','bit_index','bit_address_mask','bit_address_value','bit_write','bit_read_xor','bit_address_mode']
    cases=[]; promoted=0
    for index,config in enumerate(configurations(args.xor_mask)):
        def run():
            return json.loads(subprocess.check_output([str(args.probe.resolve()),str(args.rom.resolve())]
                                                      +list(map(str,config))))
        result=run()
        scores=compare(hardware,result)
        # A 256-clock screen may be short. Any >=16-fetch fit is rerun for
        # 12000 clocks and assessed against the entire supplied observation.
        if max(s['combined_prefix'] for s in scores)>=16:
            config[7]=12000;result=run();scores=compare(hardware,result);promoted+=1
        cases.append(dict(id=index,parameters=dict(zip(names,config)),scores=scores,
                          first16=result['fetches'][:16]))
        if index % 1000 == 0:
            print(f'completed {index+1} cases; best prefix '+str(max(s['combined_prefix'] for c in cases for s in c['scores'])),flush=True)
    best=[]
    for run in hardware['runs']:
        ranked=sorted(cases,key=lambda c:next(s['combined_prefix'] for s in c['scores'] if s['run']==run['name']),reverse=True)
        best.append(dict(run=run['name'],top_cases=[dict(id=c['id'],parameters=c['parameters'],
                         score=next(s for s in c['scores'] if s['run']==run['name'])) for c in ranked[:5]]))
    out=dict(cases=len(cases),promoted=promoted,screen_ticks=256,promotion_prefix=16,
             startup_xor_mask=args.xor_mask,
             target_fetches=[len(r['fetches']) for r in hardware['runs']],rom_sha256=ROM_SHA,
             fixture_sha256=hashlib.sha256(fixture).hexdigest(),
             source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in [HERE/'probe.c',HERE/'bit_campaign.py',HERE/'campaign.py']},
             best=best,matches=[dict(case=c['id'],run=s['run']) for c in cases for s in c['scores']
                               if s['reproduces_bounded_observation']],experiments=cases)
    raw=(json.dumps(out,separators=(',',':'))+'\n').encode()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_bytes(gzip.compress(raw,mtime=0))
    out.pop('experiments');out['full_report_sha256']=hashlib.sha256(raw).hexdigest()
    args.output.with_suffix('.summary.json').write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps(dict(cases=out['cases'],promoted=promoted,matches=out['matches'],
                         best=[(b['run'],b['top_cases'][0]['score']['combined_prefix']) for b in best]),indent=2))


if __name__=='__main__':
    main()
