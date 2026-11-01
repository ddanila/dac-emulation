#!/usr/bin/env python3
"""Compare fault mechanisms against MB001 startup traces, excluding disputed probes.

Scores are deterministic compatibility measures, not posterior probabilities.
No captured bytes are supplied to the forward model.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import extract
from campaign import HERE, ROM_SHA, compare


def configurations():
    patterns=[('seed',0),('seed',1),('seed',42),('seed',12345),
              ('stripe:0:0:255',0),('stripe:0:8:255',0),
              ('xorstripe:0:8:255:1:231',0),('xorstripe:0:8:255:1:239',0)]
    def config(fault='healthy',mask=0,value=0,pattern='seed',seed=0,
               bus='fixed',bias=255,decay=0,initial=255):
        return [fault,bus,bias,decay,mask,value,seed,12000,initial,pattern]
    for pattern,seed in patterns:
        yield 'healthy_or_RAM_initial_state_only',config(pattern=pattern,seed=seed)
        yield 'RAM_drives_alongside_ROM',config('ram-contention',pattern=pattern,seed=seed)
        yield 'ROM_decoder_inactive_RAM_admitted',config('decoder-ram-alias',pattern=pattern,seed=seed)
        yield 'AB15_forced_high',config('address-mask',32768,32768,pattern,seed)
        for bit in range(11,15):
            yield 'other_ROM_address_bit_high',config('address-mask',1<<bit,1<<bit,pattern,seed)
        # A frozen whole high-address latch, rather than selectively fitted cells.
        for high in (0x08,0x38,0x80,0xff):
            yield 'high_address_byte_frozen',config('address-mask',0xff00,high<<8,pattern,seed)
        for retained in (5,6,7):
            mask=(0xffff<<retained)&0xffff
            yield 'multi_address_bits_forced_high',config('address-mask',mask,mask,pattern,seed)
            yield 'decoder_plus_RAM_alias',config('decoder-ram-alias',mask,0,pattern,seed)
            yield 'decoder_alias_D3_writes_disabled',config('decoder-ram-alias',mask,0,pattern,seed)+[3,0,0,1,0,0]
    for fault,family in [('rom-oe-high','ROM_output_disabled_only'),
                         ('rd-buffer-high','buffered_RD_missing'),
                         ('rom-ce-high','ROM_CE_inactive'),
                         ('data-buffer-open','CPU_connector_data_path_open')]:
        for bias in (0,8,255):
            for initial in (0,8,255):
                for bus in ('fixed','hold'):
                    yield family,config(fault,bus=bus,bias=bias,initial=initial)
                for delay in (1,2,4,8,16):
                    yield family,config(fault,bus='decay',bias=bias,initial=initial,decay=delay)
    for mask in (1,2,4,8,16,32,64,128,0x29):
        for value in (0,mask):
            yield 'ROM_read_data_clamped',config('rom-data-mask',mask,value)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom',type=Path,required=True)
    parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    assert hashlib.sha256(args.rom.read_bytes()).hexdigest()==ROM_SHA
    args.output.mkdir(parents=True,exist_ok=True)
    newer=sorted(p.name for p in args.evidence.iterdir()
                 if p.name.startswith(('20261028-','20261029-','20261031-'))
                 and (p/'capture.lac.gz').exists() and 'invalid' not in p.name)
    extract.RUNS=extract.RUNS+newer
    hardware=extract.extract(args.evidence,limit=0,read_data=True)
    hardware['excluded_channels']='CH15 and higher: disputed A15/latch/control probes are never scored'
    hardware['controls_caveat']='CE/OE still rely on their probes; control-free sensitivity scores also retained'
    fixture=(json.dumps(hardware,separators=(',',':'))+'\n').encode()
    (args.output/'observations.json.gz').write_bytes(gzip.compress(fixture,mtime=0))
    no_controls=json.loads(json.dumps(hardware))
    for run in no_controls['runs']:
        for row in run['fetches']:
            row.pop('ce',None);row.pop('oe',None)
    cases=[];families={}
    for index,(family,params) in enumerate(configurations()):
        model=json.loads(subprocess.check_output([str(HERE.parents[1]/'build/pc1715-fault-probe'),
                                                 str(args.rom.resolve()),*map(str,params)]))
        scores=compare(hardware,model);sensitive=compare(no_controls,model)
        case=dict(id=index,family=family,parameters=params,scores=scores,
                  without_rom_controls=sensitive,first16=model['fetches'][:16])
        cases.append(case)
        if family not in families:
            families[family]=dict(cases=0,best=[None]*len(scores),best_without_controls=[0]*len(scores))
        group=families[family];group['cases']+=1
        for i,score in enumerate(scores):
            group['best_without_controls'][i]=max(group['best_without_controls'][i],sensitive[i]['combined_prefix'])
            if group['best'][i] is None or score['combined_prefix']>group['best'][i]['score']['combined_prefix']:
                group['best'][i]=dict(case=index,score=score,parameters=params,model=model)
        if (index+1)%100==0: print('Completed',index+1,flush=True)
    summary={}
    for name,group in families.items():
        best=group['best']
        summary[name]=dict(cases=group['cases'],
             best_prefixes=[b['score']['combined_prefix'] for b in best],
             best_prefixes_without_rom_controls=group['best_without_controls'],
             complete_runs=[b['score']['run'] for b in best if b['score']['reproduces_bounded_observation']],
             median_best_prefix=statistics.median(b['score']['combined_prefix'] for b in best),
             maximum_best_prefix=max(b['score']['combined_prefix'] for b in best),
             cases_matching_all_runs=[c['id'] for c in cases if c['family']==name and
                                     all(s['reproduces_bounded_observation'] for s in c['scores'])])
    prior_path=HERE/'bit-results/qualification.json.gz'
    prior=json.loads(gzip.decompress(prior_path.read_bytes()))
    frozen=next(c for c in cases if c['parameters']==prior['parameters'])
    winner=next(b for b in families['decoder_alias_D3_writes_disabled']['best']
                if b['score']['run']=='20261031-a15-decoder-compare')
    assert winner['parameters']==prior['parameters'] and winner['model']==prior['model']
    prior_check=dict(reference_sha256=hashlib.sha256(prior_path.read_bytes()).hexdigest(),
                     parameters_and_complete_forward_model_unchanged=True,
                     all_scores=frozen['scores'])
    source_paths=[HERE/'probe.c',Path(__file__),HERE/'extract.py',HERE/'campaign.py',
                  HERE.parents[1]/'machines/robotron1715/pc1715.c',
                  HERE.parents[1]/'common/cpu/z80.c',HERE.parents[1]/'third_party/cpu/chips/z80.h']
    report=dict(rom_sha256=ROM_SHA,fixture_sha256=hashlib.sha256(fixture).hexdigest(),
                source_sha256={str(p.relative_to(HERE.parents[1])):hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths},
                runs=[dict(name=r['name'],intervals=len(r['fetches'])) for r in hardware['runs']],
                cases=cases,families=families,summary=summary,prior_candidate_check=prior_check,
                probability_warning='No priors or measurement/noise likelihood calibrated; no posterior probabilities computed. Per-run maxima may use different fitted parameters, not one explanation of all runs.')
    (args.output/'campaign.json.gz').write_bytes(gzip.compress((json.dumps(report,separators=(',',':'))+'\n').encode(),mtime=0))
    (args.output/'summary.json').write_text(json.dumps(dict(runs=report['runs'],families=summary,
          probability_warning=report['probability_warning']),indent=2)+'\n')
    print(json.dumps({k:{n:v[n] for n in ['cases','complete_runs','median_best_prefix','maximum_best_prefix']} for k,v in summary.items()},indent=2))


if __name__=='__main__':
    main()
