#!/usr/bin/env python3
"""Join native scope metadata identities to scope membership and signal handles."""
import argparse,json,os,platform,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
from scope_metadata_records import parse as metadata_parse
from signal_handles import parse as signal_parse
HERE=Path(__file__).resolve().parent


def reference_parse(lines):
    a=lines[0].split()
    if len(a)!=3 or a[:2]!=['VSMR_BEGIN','1']:raise ValueError('Missing reference header')
    tick=int(a[2]);scopes=[];objects=[];i=1
    while i<len(lines) and lines[i].startswith('VSMR_SCOPE '):
        a=lines[i].split();i+=1
        if len(a)!=4:raise ValueError('Invalid scope reference')
        scopes.append(dict(id=int(a[1]),pointer=int(a[2],16),traversal=int(a[3])))
    while i<len(lines) and lines[i].startswith('VSMR_OBJECT '):
        a=lines[i].split();i+=1
        if len(a)!=4:raise ValueError('Invalid object reference')
        objects.append(dict(id=int(a[1]),pointer=int(a[2],16),type=int(a[3])))
    if tick<0 or not scopes or lines[i:]!=[f'VSMR_END {len(scopes)} {len(objects)}']:raise ValueError('Incomplete references')
    for rows in (scopes,objects):
        if any(v<=0 for r in rows for v in r.values()) or len({r['id'] for r in rows})!=len(rows) or len({r['pointer'] for r in rows})!=len(rows):raise ValueError('Aliased references')
    if [r['traversal'] for r in scopes]!=list(range(1,len(scopes)+1)):raise ValueError('Invalid traversal mapping')
    if [r['id'] for r in objects]!=sorted(r['id'] for r in objects):raise ValueError('Unordered object identities')
    return dict(tick=tick,scopes=scopes,objects=objects)


def membership_parse(lines):
    a=lines[0].split()
    if len(a)!=3 or a[:2]!=['VSC_BEGIN','1']:raise ValueError('Invalid membership header')
    tick=int(a[2]);scopes=[];i=1
    while i<len(lines) and lines[i].startswith('VSC_SCOPE '):
        a=lines[i].split();i+=1
        if len(a)!=6:raise ValueError('Invalid membership row')
        ident,pointer,parent,kind,count=int(a[1]),int(a[2],16),int(a[3]),int(a[4]),int(a[5]);members=[]
        if ident!=len(scopes)+1 or pointer<=0 or not 0<=parent<ident or count<0:raise ValueError('Invalid scope membership identity')
        for _ in range(count):
            if i>=len(lines):raise ValueError('Truncated members')
            a=lines[i].split();i+=1
            if len(a)!=2 or a[0]!='VSC_MEMBER':raise ValueError('Missing member')
            members.append(int(a[1]))
        if members!=sorted(set(members)) or any(m<=0 for m in members):raise ValueError('Invalid thread membership')
        scopes.append(dict(id=ident,pointer=pointer,parent=parent,type=kind,members=members))
    if tick<0 or not scopes or len({r['pointer'] for r in scopes})!=len(scopes) or lines[i:]!=[f'VSC_END {len(scopes)}']:raise ValueError('Incomplete membership')
    return dict(tick=tick,scopes=scopes)


def parse(lines):
    starts=[i for i,l in enumerate(lines) if l.startswith(('VSM_BEGIN ','VSMR_BEGIN ','VSC_BEGIN ','VSH_BEGIN '))]
    if len(starts)!=4 or starts[0]!=0:raise ValueError('Missing combined sections')
    ends=starts[1:]+[len(lines)]
    return {key:fn(lines[a:b]) for key,fn,a,b in zip(('metadata','reference','membership','signals'),(metadata_parse,reference_parse,membership_parse,signal_parse),starts,ends)}


def validate(state):
    m,r,c,s=(state[k] for k in ('metadata','reference','membership','signals'))
    if len({v['tick'] for v in (m,r,c,s)})!=1:raise ValueError('Cross-observer time mismatch')
    refs={x['id']:x for x in r['scopes']};traversal={x['traversal']:x for x in r['scopes']}
    metadata={x['id']:x for x in m['scopes']};objects={x['id']:x for x in r['objects']}
    if set(refs)!=set(metadata) or len(c['scopes'])!=len(refs):raise ValueError('Cross-observer scope population mismatch')
    for scope in c['scopes']:
        ref=traversal[scope['id']];meta=metadata[ref['id']]
        parent=traversal[scope['parent']]['id'] if scope['parent'] else 0
        if ref['pointer']!=scope['pointer'] or meta['parent']!=parent or meta['type']!=scope['type']:raise ValueError('Cross-observer scope binding mismatch')
    owners={}
    for scope in m['scopes']:
        for item in scope['intern']:
            obj=objects.get(item['id'])
            if obj is None or obj['type']!=item['type']:raise ValueError('Unknown internal object identity/type')
            owners.setdefault(obj['pointer'],[]).append(scope['id'])
    for scope in m['scopes']:
        if owners.get(refs[scope['id']]['pointer'],[])!=([scope['parent']] if scope['parent'] else []):raise ValueError('Scope hierarchy/internal membership mismatch')
    pointer_objects={x['pointer']:x for x in r['objects']}
    kinds={'10signal_reg':48,'10signal_net':36,'14signal_integer':25}
    for signal in s['rows']:
        ref=traversal.get(signal['scopeId']);obj=pointer_objects.get(signal['pointer'])
        if not ref or ref['pointer']!=signal['scope'] or not obj or obj['type']!=kinds[signal['kind']]:raise ValueError('Signal scope/object binding mismatch')
        if owners.get(signal['pointer'])!=[ref['id']]:raise ValueError('Signal missing or duplicated in owning scope')
    return dict(scopes=len(refs),registeredObjects=len(objects),boundSignals=len(s['rows']))


def review(root):
    receipt=json.loads((root/'run.json').read_text());images={}
    expected=[]
    for i in (1,2):expected += [f'ROUND {i}','OMITTED signal','REFUSED intern',f'RESTORED {i}']
    expected += ['CONTINUE 5 2','finish']
    for mode in ('baseline','disabled','enabled'):
        if receipt['runs'][mode]['exitCode'] or (root/(mode+'.stderr')).read_text():raise ValueError('Failed native binding control')
        lines=(root/(mode+'.stdout')).read_text().splitlines();i=0;events=[]
        while i<len(lines):
            line=lines[i];i+=1
            if line.startswith('IMAGE '):
                key=line.split()[1];start=i
                while i<len(lines) and lines[i]!='BUNDLE_END':i+=1
                if i==len(lines) or key in images or mode!='enabled':raise ValueError('Invalid combined image')
                images[key]=parse(lines[start:i]);i+=1
            else:events.append('finish' if '$finish called at 3000 (1ps)' in line else line)
        if events!=expected:raise ValueError('Changed original continuation')
    if set(images)!={f'{kind}{i}' for i in (1,2) for kind in ('before','missing','restored')}:raise ValueError('Missing controls')
    counts=[]
    for i in (1,2):
        before=images[f'before{i}'];missing=images[f'missing{i}'];restored=images[f'restored{i}']
        if before!=restored or before['metadata']['tick']!=i*1000:raise ValueError('Changed restoration/time')
        counts.append(validate(before))
        if counts[-1]['boundSignals']!=2:raise ValueError('Missing signal handoffs')
        if any(before[k]!=missing[k] for k in ('reference','membership','signals')):raise ValueError('Omission changed unrelated observer')
        try:validate(missing)
        except ValueError as error:
            if str(error)!='Signal missing or duplicated in owning scope':raise
        else:raise ValueError('Missing signal accepted')
    return dict(qualified=False,controlsPassed=True,originalContinuationExactlyEqual=True,rounds=2,bindings=counts,
        scope='Native scope metadata references join exact scope addresses/traversal IDs and two admitted signal handles. Omitted signal membership is rejected while reference, scope-thread and signal images remain unchanged. Foreign intern reference scans refuse before output; restoration is exact. Static native lifetime only; no other intern payload, general deletion/address reuse or operational board qualification.')


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed runtime')
    for ext in ('cc','v'):shutil.copy2(HERE/f'fixtures/scope_metadata_bindings.{ext}',out/f'probe.{ext}')
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')],['c++','-std=c++11',*flags,'-I'+str(candidate),'-I'+str(candidate/'vvp'),'-o',str(out/'probe.vpi'),str(out/'probe.cc')]]
    for cmd in commands:subprocess.run(cmd,check=True)
    pins={str(p):sha(p) for p in [baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',out/'probe.vvp',*modules.glob('*.vpi')]};runs={}
    for mode in ('baseline','disabled','enabled'):
        lib=baseline if mode=='baseline' else candidate/'vvp/libvvp.so'
        env=dict(os.environ,K7658_SCOPE_METADATA_BINDINGS='on' if mode=='enabled' else 'off');env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
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
