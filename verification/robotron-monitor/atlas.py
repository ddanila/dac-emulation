#!/usr/bin/env python3
"""Generate a reproducible, explicitly unvalidated electrical fault atlas.

Accepted entries require nominal, joint-ensemble, held-out and refinement runs.
Unsupported/failed/indeterminate entries contain no published predictions.
Current historical coverage is checked independently from numerical success.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import shutil
import subprocess

import atlas_features as features
import reference

ROOT=reference.ROOT


def write_json(path,value):
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def load_inputs(catalogue,scenario_file,scenario_id):
    cat=json.loads(Path(catalogue).read_text());scenarios=json.loads(Path(scenario_file).read_text())
    if cat.get('format')!='dac-monitor-fault-catalogue-v1' or scenarios.get('format')!='dac-monitor-scenarios-v1':
        raise ValueError('unsupported catalogue/scenario format')
    ids=[f['id'] for f in cat['faults']]
    import re
    if len(set(ids))!=len(ids) or any(not re.fullmatch('[a-z0-9][a-z0-9-]{0,79}',id) for id in ids):
        raise ValueError('invalid or duplicate fault identity')
    choices=[s for s in scenarios['scenarios'] if s['id']==scenario_id]
    if len(choices)!=1:raise ValueError('unknown/duplicate scenario')
    profile_path=(ROOT/cat['profile']).resolve()
    if not profile_path.is_relative_to(ROOT):raise ValueError('profile outside laboratory')
    profile=reference.read_profile(profile_path)
    if choices[0]['model_id']!=profile['id']:raise ValueError('scenario/profile mismatch')
    return cat,choices[0],profile,profile_path


def ensemble(profile,inventory,count,seed,scenario):
    """Seeded Latin-hypercube exploration; NOT a probability distribution."""
    if type(count) is not int or not 2<=count<=128:raise ValueError('ensemble size must be 2–128')
    rng=random.Random(seed);result=[dict(parameters={},component_factors={}) for _ in range(count)]
    axes=[]
    for name,p in sorted(profile['parameters'].items()):
        if name not in scenario.get('parameters',{}):
            axes.append(('parameters',name,p['minimum'],p['maximum']))
    for p in inventory['parts']:
        if p['board']==profile['board'] and p['kind'] in ('resistor','capacitor','inductor') and p['value'] and p['tolerance_percent']:
            t=p['tolerance_percent']/100
            axes.append(('component_factors',p['id'],1-t,1+t))
    for group,name,lo,hi in axes:
        buckets=list(range(count));rng.shuffle(buckets)
        for i,bucket in enumerate(buckets):
            fraction=(bucket+rng.random())/count
            value=math.exp(math.log(lo)+fraction*(math.log(hi)-math.log(lo))) if hi/lo>=100 else lo+fraction*(hi-lo)
            result[i][group][name]=value
    return result


def build(output,*,catalogue=ROOT/'atlas/catalogue.json',scenario_file=ROOT/'atlas/scenarios.json',
          scenario_id='nominal',members=16,held_out=8,seed=722211,only=None):
    cat,scenario,profile,profile_path=load_inputs(catalogue,scenario_file,scenario_id)
    faults=cat['faults']
    if only:
        if not set(only)<={f['id'] for f in faults}:raise ValueError('unknown fault selection')
        faults=[f for f in faults if f['id'] in only]
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    publish=output/'public';publish.mkdir()
    inventory=json.loads((ROOT/profile['inventory']).read_text())
    train=ensemble(profile,inventory,members,seed,scenario)
    held=ensemble(profile,inventory,held_out,seed+1,scenario)
    samples=[dict(parameters={},component_factors={})]+train+held
    write_json(output/'ensemble.json',dict(method='Latin hypercube; log-spaced only for ranges spanning at least 100x',
               seed=seed,training=train,held_out=held,interpretation='Parameter exploration, not measured tolerances or probabilities.'))
    snapshots={name:(ROOT/name).read_bytes() for name in ('atlas.py','atlas_features.py','reference.py','faults.py')}
    snapshots|={'catalogue.json':Path(catalogue).read_bytes(),'scenarios.json':Path(scenario_file).read_bytes()}
    for name,content in snapshots.items():(output/name).write_bytes(content)
    source_hashes={name:hashlib.sha256(content).hexdigest() for name,content in snapshots.items()}

    def solve(directory,fault,sample,step=None,regularization=1.):
        report=reference.run(profile_path,directory,start=scenario['start'],stop=scenario['stop'],
               step=step or scenario['step'],changes=sample['parameters'],component_factors=sample['component_factors'],
               fault=fault,scenario=scenario,regularization=regularization)
        rows=reference.read_samples(directory/'samples.txt',profile['probes'],scenario['start'],scenario['stop'],step or scenario['step'])
        return report,features.extract(rows,profile['probes'],scenario['feature_windows'])

    cases=[];results={};nominal_reports={}
    definitions=[dict(id='nominal',name='Nominal model',stage='Neck/video',symptoms=[],target=None)]+faults
    for definition in definitions:
        id=definition['id'];entry=dict(definition=definition,hardware_validation='none')
        if definition.get('status')=='unsupported':
            entry.update(status='unsupported',reason=definition['reason']);cases.append(entry);continue
        fault=None if id=='nominal' else definition
        case_dir=output/id;case_dir.mkdir()
        accepted=[];failures=[];reports=[]
        for i,sample in enumerate(samples):
            try:
                report,signature=solve(case_dir/f'sample-{i:03}',fault,sample)
                accepted.append(signature);reports.append(report)
            except (ValueError,OSError,subprocess.SubprocessError) as error:
                failures.append(dict(sample=i,error=str(error)))
                # A nominal failure invalidates this case and makes extra solves uninformative.
                if i==0:break
        numerical=[]
        if not failures:
            try:
                _,refined=solve(case_dir/'refined',fault,samples[0],step=scenario['step']/2)
                numerical.append(dict(check='time-step',**features.refinement(accepted[0],refined)))
                if fault and fault['operation'] in ('open','short'):
                    for factor in (.1,10.):
                        _,changed=solve(case_dir/f'regularization-{factor}',fault,samples[0],regularization=factor)
                        numerical.append(dict(check=f'regularization-{factor}',**features.refinement(accepted[0],changed)))
            except (ValueError,OSError,subprocess.SubprocessError) as error:
                failures.append(dict(sample='refinement',error=str(error)))
        status='simulation-failed' if failures else 'accepted-simulation' if all(x['passed'] for x in numerical) else 'indeterminate'
        local=dict(definition=definition,status=status,failures=failures,numerical_checks=numerical,
                   completed_samples=len(accepted),required_samples=len(samples),source_hashes=source_hashes)
        write_json(case_dir/'validation.json',local)
        entry.update(status=status,validation=local)
        if status=='accepted-simulation':
            results[id]=dict(training=features.envelope(accepted[:members+1]),held=accepted[members+1:])
            nominal_reports[id]=reports[0]
            entry.update(features=results[id]['training'],nominal_features=accepted[0],
                         replay=id+'.mcrt',conditions=scenario,coverage=reports[0]['coverage'],
                         model_hashes=reports[0]['hashes'],similar_faults=[],distinguishing_observations=[])
            shutil.copyfile(case_dir/'sample-000/replay.mcrt',publish/(id+'.mcrt'))
        else:
            entry['reason']='Solver failure or incomplete ensemble; predictions withheld.' if failures else 'Numerical refinement failed; predictions withheld.'
        cases.append(entry)
        print(id+': '+status,flush=True)

    # Independent held-out signatures are compared to the training envelopes.
    accepted_cases=[c for c in cases if c['status']=='accepted-simulation']
    pairs=[];confusion=[]
    for i,a in enumerate(accepted_cases):
        aid=a['definition']['id']
        for b in accepted_cases[i+1:]:
            bid=b['definition']['id'];comparison=features.compare(a['features'],b['features'])
            pairs.append(dict(a=aid,b=bid,**comparison))
            if comparison['ambiguous']:
                a['similar_faults'].append(bid);b['similar_faults'].append(aid)
            else:
                # Report every separating observation; no ranked next-test instruction.
                a['distinguishing_observations'].append(dict(other=bid,features=comparison['separating_features']))
                b['distinguishing_observations'].append(dict(other=aid,features=comparison['separating_features']))
        for index,signature in enumerate(results[aid]['held']):
            point=features.envelope([signature])
            compatible=[b['definition']['id'] for b in accepted_cases if features.compare(point,b['features'])['ambiguous']]
            confusion.append(dict(actual=aid,sample=index,compatible=compatible,
                                   outside_own_training_envelope=aid not in compatible))
    index=dict(format='dac-monitor-atlas-v1',revision=cat['revision'],model_id=profile['id'],
               name='K7222.11/.21 fault atlas — development bench',scope=cat['scope'],
               hardware_validation='none',scenario=scenario,probes=profile['probes'],
               components=nominal_reports.get('nominal',{}).get('components',[]),
               source_hashes=source_hashes,ensemble=dict(training=members,held_out=held_out,seed=seed),
               publication_gate=dict(first_release_eligible=False,
                   reason='Complete power/horizontal/flyback path is not implemented; accepted entries cover only the neck bench.'),
               limitations=profile['limitations']+[
                   'Feature windows describe settled levels. Transition-only faults may be indistinguishable in these features.',
                   'Intervals summarize sampled assumptions, not guaranteed bounds or diagnostic probabilities.',
                   'Held-out parameter cases use the same model; they are not hardware validation.',
                   'No screen symptom, automatic diagnosis or live measurement instructions are inferred.'],
               cases=cases,comparisons=pairs,held_out_confusion=confusion)
    # A failed nominal model prevents publication of fault predictions altogether.
    if not any(c['definition']['id']=='nominal' for c in accepted_cases):
        raise ValueError('nominal model failed validation; atlas not published (see run logs)')
    write_json(publish/'index.json',index)
    for entry in cases:
        write_json(publish/(entry['definition']['id']+'.json'),dict(atlas=index['name'],revision=cat['revision'],
                   hardware_validation='none',limitations=index['limitations'],scenario=scenario,case=entry))
    manifest={p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(publish.iterdir()) if p.is_file()}
    write_json(publish/'manifest.json',dict(format='dac-monitor-atlas-manifest-v1',files=manifest))
    return index


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--scenario',default='nominal')
    parser.add_argument('--members',type=int,default=16)
    parser.add_argument('--held-out',type=int,default=8)
    parser.add_argument('--seed',type=int,default=722211)
    parser.add_argument('--fault',action='append')
    args=parser.parse_args()
    build(args.output,scenario_id=args.scenario,members=args.members,held_out=args.held_out,seed=args.seed,only=args.fault)
