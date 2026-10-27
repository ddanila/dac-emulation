#!/usr/bin/env python3
"""Verify complete native callback/signal/node/filter cross-references."""
import argparse,json,os,platform,shutil,subprocess
from pathlib import Path
from signal_handles import parse as signal_parse
from callback_list_probe import parse as list_parse
from net_probe import parse as graph_parse,validate as graph_validate,pointer
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


def parse(lines):
    a=lines[0].split()
    if len(a)!=3 or a[:2]!=['VSL_BEGIN','1']:raise ValueError('Invalid callback signal header')
    rows=[]
    for line in lines[1:-1]:
        a=line.split()
        if len(a)!=10 or a[0]!='VSL_LINK':raise ValueError('Invalid callback signal link')
        row=dict(callbackId=int(a[1]),callback=pointer(a[2]),handleId=int(a[3]),handle=pointer(a[4]),ownerId=int(a[5]),owner=pointer(a[6]),filter=pointer(a[7]),nodeId=int(a[8]),node=pointer(a[9]))
        if min(row.values())<=0:raise ValueError('Invalid callback signal identity')
        rows.append(row)
    if lines[-1]!=f'VSL_END {len(rows)}' or [r['callbackId'] for r in rows]!=sorted({r['callbackId'] for r in rows}):raise ValueError('Incomplete callback signal links')
    return dict(tick=int(lines[0].split()[2]),rows=rows)


def validate(state):
    links,signals,lists,graph=(state[k] for k in ('links','signals','lists','graph'))
    if len({s['tick'] for s in (links,signals,lists,graph)})!=1:raise ValueError('Cross-reference time mismatch')
    graph_validate(graph);handles={r['id']:r for r in signals['rows']};nodes={n['id']:n for n in graph['nodes']}
    callbacks={c['id']:(o,c) for o in lists['owners'] for c in o['callbacks']}
    if {r['callbackId'] for r in links['rows']}!=set(callbacks):raise ValueError('Incomplete callback cross-references')
    for r in links['rows']:
        owner,cb=callbacks[r['callbackId']];handle=handles.get(r['handleId']);node=nodes.get(r['nodeId'])
        if not handle or not node:raise ValueError('Unregistered handle or node')
        if (owner['id'],owner['pointer'],cb['pointer'],cb['object'])!=(r['ownerId'],r['owner'],r['callback'],r['handle']):raise ValueError('Callback owner/object linkage mismatch')
        if (handle['pointer'],handle['nodeId'],handle['node'])!=(r['handle'],r['nodeId'],r['node']):raise ValueError('Typed handle/node linkage mismatch')
        if (node['key'],node['filter'])!=(r['node'],r['filter']):raise ValueError('Registered filter linkage mismatch')
    return len(links['rows'])


def review(root):
    receipt=json.loads((root/'run.json').read_text());states={}
    expected=['DONE 0','CALLBACK a 5','CALLBACK b 12','DONE 1','CALLBACK a 7','DONE 2','CONTINUE 7 1','finish']
    for mode in ('baseline','disabled','enabled'):
        if receipt['runs'][mode]['exitCode'] or (root/(mode+'.stderr')).read_text():raise ValueError('Failed native callback link run')
        lines=(root/(mode+'.stdout')).read_text().splitlines();i=0;events=[];refusals=[]
        while i<len(lines):
            line=lines[i];i+=1
            if line.startswith('STATE '):
                name=line.split()[1]
                if mode!='enabled' or name in states:raise ValueError('Invalid link stage')
                state={}
                for key,prefix,parser in [('links','VSL',parse),('signals','VSH',signal_parse),('lists','VCL',list_parse),('graph','VNG',graph_parse)]:
                    start=i
                    while i<len(lines) and not lines[i].startswith(prefix+'_END '):i+=1
                    if i==len(lines):raise ValueError('Incomplete linked state')
                    i+=1;state[key]=parser(lines[start:i])
                if i==len(lines) or lines[i]!='END_STATE':raise ValueError('Missing state end')
                i+=1;validate(state);states[name]=state;continue
            if line.startswith('REFUSED '):refusals.append(line[8:]);continue
            events.append('finish' if '$finish called at 5000 (1ps)' in line else line)
        if events!=expected:raise ValueError('Changed native callback continuation')
        wanted=['callbacks-unadmitted','handles-unadmitted','other-node','foreign-node','other-filter','foreign-filter','other-object','foreign-object']+['active-traversal']*3 if mode=='enabled' else []
        if refusals!=wanted:raise ValueError('Missing native linkage refusals')
    if set(states)!={'before','restored','changed','cancelled','deleted'} or states['before']!=states['restored']:raise ValueError('Incomplete or unrestored link controls')
    base=states['before']['links']['rows']
    if len(base)!=2:raise ValueError('Missing distinct native owners')
    for stage,tick in [('before',1000),('restored',1000),('changed',3000),('cancelled',3000),('deleted',5000)]:
        state=states[stage]
        if state['links']['tick']!=tick or state['links']['rows']!=(base[:1] if stage=='deleted' else base):raise ValueError('Changed link lifetime through cancellation')
        callbacks=[c for o in state['lists']['owners'] for c in o['callbacks']]
        cancelled=[c['id'] for c in callbacks if not c['function']]
        if cancelled!=([base[1]['callbackId']] if stage=='cancelled' else []):raise ValueError('Incorrect deferred cancellation')
    if len({r['ownerId'] for r in base})!=2 or len({r['nodeId'] for r in base})!=2:raise ValueError('Missing distinct graph ownership')
    return dict(qualified=False,controlsPassed=True,originalContinuationExactlyEqual=True,
                scope='Native callback allocation/lifetime, typed signal handoff, registered node and adjusted owner/filter linkage agree with independent full inventories. Unadmitted objects, foreign/mismatched node/filter/object pointers and active traversal refuse before output. Restored faults preserve continuation; cancelled callbacks remain linked until native deletion. This fixture does not qualify board integration, aggregate runtime cost or general rollback.')


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed runtime')
    for ext in ('cc','v'):shutil.copy2(HERE/f'fixtures/callback_signal_links.{ext}',out/f'probe.{ext}')
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')],['c++','-std=c++11',*flags,'-I'+str(candidate),'-I'+str(candidate/'vvp'),'-o',str(out/'probe.vpi'),str(out/'probe.cc')]]
    for cmd in commands:subprocess.run(cmd,check=True)
    pins={str(p):sha(p) for p in [baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',out/'probe.vvp',*modules.glob('*.vpi')]};runs={}
    for mode in ('baseline','disabled','enabled'):
        lib=baseline if mode=='baseline' else candidate/'vvp/libvvp.so'
        env=dict(os.environ,K7658_REFERENTS='on' if mode=='enabled' else 'off');env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp'];r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(mode+'.stdout')).write_text(r.stdout);(out/(mode+'.stderr')).write_text(r.stderr);runs[mode]=dict(exitCode=r.returncode,command=cmd,library=str(lib));r.check_returncode()
    if any(sha(Path(p))!=h for p,h in pins.items()):raise ValueError('Dependencies changed')
    (out/'build.json').write_text(json.dumps(build,indent=2)+'\n')
    (out/'run.json').write_text(json.dumps(dict(runs=runs,commands=commands,dependencies=pins),indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();run(a.candidate,a.baseline,a.modules,a.out)
