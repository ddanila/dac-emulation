#!/usr/bin/env python3
"""Explicit tapped-winding hypotheses, not a recovered factory T3 specification.

The graph and relative polarities are independent of numerical parameters.
Generated models retain the existing shared-core energy coupling, with every
section represented separately. Nothing in this module selects a historical
winner or promotes a standalone magnetic test to a complete monitor result.
"""
import argparse,copy,hashlib,itertools,json,math,re
from pathlib import Path
import magnetics
ROOT=Path(__file__).resolve().parent


def finite(value):
    return type(value) in (int,float) and math.isfinite(value)


def validate(graph):
    if graph.get('format')!='dac-monitor-winding-graph-v1' or graph.get('historical_topology_verified') is not False:
        raise ValueError('expected an explicitly unverified winding graph')
    groups=graph.get('groups',[])
    if not 2<=len(groups)<=8:raise ValueError('invalid winding group count')
    ids=set();terminals=set();sections=0
    for group in groups:
        name=group.get('id');taps=group.get('taps',[])
        if not isinstance(name,str) or not re.fullmatch('[a-z][a-z0-9_]*',name) or name in ids:
            raise ValueError('duplicate/invalid winding identity')
        ids.add(name)
        if not 2<=len(taps)<=16 or any(not isinstance(t,str) or not re.fullmatch('X[12]_[0-9]{1,2}',t) for t in taps):
            raise ValueError('invalid winding terminals')
        if len(set(taps))!=len(taps) or terminals.intersection(taps):raise ValueError('duplicate winding terminal')
        terminals.update(taps);sections+=len(taps)-1
        if not group.get('evidence') or not group.get('assumption'):raise ValueError('winding evidence/assumption required')
    if sections>63 or graph.get('anchor') not in ids:raise ValueError('invalid winding anchor or section budget')
    return graph


def signature(graph,polarity):
    """Canonicalize global core reversal; signs remain relative to one anchor."""
    validate(graph)
    if set(polarity)!={g['id'] for g in graph['groups']} or any(type(p) is not int or p not in (-1,1) for p in polarity.values()):
        raise ValueError('invalid candidate polarities')
    anchor=polarity[graph['anchor']]
    normalized={name:sign*anchor for name,sign in polarity.items()}
    # Taps are explicitly ordered hypotheses. Numerical turns never enter identity.
    edges=sorted((g['id'],tuple(g['taps']),normalized[g['id']]) for g in graph['groups'])
    return hashlib.sha256(json.dumps(edges,separators=(',',':')).encode()).hexdigest()


def enumerate_candidates(graph):
    validate(graph)
    other=sorted(g['id'] for g in graph['groups'] if g['id']!=graph['anchor'])
    out=[];seen=set()
    for signs in itertools.product((1,-1),repeat=len(other)):
        polarity={graph['anchor']:1}|dict(zip(other,signs));key=signature(graph,polarity)
        if key in seen:continue
        seen.add(key)
        out.append(dict(id='t3-'+key[:16],topology_sha256=key,polarity=polarity,
                        qualification='experimental-winding-candidate',historical_topology_verified=False))
    return out


def bounded(parameter):
    if not isinstance(parameter,dict) or set(parameter)!={'value','minimum','maximum','evidence','rationale'}:
        raise ValueError('parameter needs value, bounds, evidence and rationale')
    lo,value,hi=(parameter[k] for k in ('minimum','value','maximum'))
    if not all(finite(v) for v in (lo,value,hi)) or not 0<lo<=value<=hi or parameter['evidence'] not in ('assumed-bound','documented-bound') or not parameter['rationale']:
        raise ValueError('invalid magnetic parameter bound')
    return value


def compile_model(graph,candidate,parameters,name='T3_CANDIDATE',shorted_turns=None,*,backend='xspice'):
    """Compile a tapped wrapper; caller supplies every numerical section bound.

    Core B(H) data retain magnetics.py's validation and are explicitly separate
    from candidate topology. Connections outside T3 are never synthesized here.
    """
    validate(graph)
    if candidate not in enumerate_candidates(graph):raise ValueError('candidate does not belong to graph')
    if not re.fullmatch('[A-Za-z][A-Za-z0-9_]*',name):raise ValueError('invalid model name')
    if parameters.get('format')!='dac-monitor-magnetic-parameters-v1' or not parameters.get('rationale'):
        raise ValueError('magnetic parameters need independent provenance')
    expected={g['id'] for g in graph['groups']}
    if set(parameters.get('groups',{}))!=expected:raise ValueError('missing or extra numerical winding groups')
    windings=[];pins=[];ports=[];descriptions=[]
    for group in graph['groups']:
        gid=group['id'];taps=group['taps'];values=parameters['groups'][gid]
        if len(values)!=len(taps)-1:raise ValueError('wrong section count')
        ports+=taps
        for i,(a,b) in enumerate(zip(taps,taps[1:])):
            keys={'turns','resistance_ohm','leakage_h','capacitance_f'}
            skin={'skin_resistance_ohm','skin_fraction'}
            if set(values[i]) not in (keys,keys|skin):raise ValueError('invalid magnetic section parameters')
            section={k:bounded(v) for k,v in values[i].items()}
            if 'skin_fraction' in section and values[i]['skin_fraction']['maximum']>=1:
                raise ValueError('skin leakage fraction bound must stay below one')
            section['polarity']=candidate['polarity'][gid]
            windings.append(section);pins += [a,b]
            descriptions.append(dict(group=gid,terminals=[a,b],parameters=copy.deepcopy(values[i]),polarity=section['polarity']))
    core=copy.deepcopy(parameters['core'])
    for key in ('area_m2','length_m','loss_ohm'):core[key]=bounded(core[key])
    if backend not in ('xspice','flux','coupled'):raise ValueError('unknown magnetic backend')
    build={'xspice': magnetics.transformer,
           'flux': magnetics.transformer_flux,
           'coupled': magnetics.transformer_coupled}[backend]
    model=build(name+'_CORE',windings,core,shorted_turns)
    model+='\n'.join(['.subckt '+name+' '+' '.join(ports),
                     'Xshared '+' '.join(pins)+' '+name+'_CORE','.ends '+name])+'\n'
    return model,dict(candidate=candidate,ports=ports,sections=descriptions,backend=backend,
                     topology=graph,numerical_parameters=parameters,
                     limitations=['Candidate topology; no factory polarity claim.',
                                  'Shared reversible core with lumped section parasitics; no hysteresis or measured distributed field.',
                                  'External wiring and monitor validation are not provided by this model.'],
                     full_monitor_qualified=False)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--graph',type=Path,default=ROOT/'reference/k7222-11/t3-winding-hypothesis.json')
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();graph=json.loads(args.graph.read_text());candidates=enumerate_candidates(graph)
    args.output.mkdir(parents=True,exist_ok=False)
    (args.output/'graph.json').write_text(json.dumps(graph,indent=2)+'\n')
    (args.output/'candidates.json').write_text(json.dumps(dict(status='topology-candidates-only',candidates=candidates,
        full_monitor_qualified=False,remaining=['Numerical section parameters','External circuit assembly','Service-waveform and convergence checks']),indent=2)+'\n')
    print(f'{len(candidates)} explicit polarity candidates; no circuit prediction generated')


if __name__=='__main__':main()
