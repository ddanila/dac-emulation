#!/usr/bin/env python3
"""Validate non-mutating array values, read ports and cached word-handle links."""
import argparse,copy,json,os,platform,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
from array_source_contract import profile
from compiled_scope_profile import analyze
HERE=Path(__file__).resolve().parent


def pointer(value):return 0 if value=='(nil)' else int(value,16)


def parse(lines):
    head=lines[0].split()
    if len(head)!=3 or head[:2]!=['VAR_BEGIN','1']:raise ValueError('Invalid array header')
    arrays=[];ports=[];i=1
    while i<len(lines) and lines[i].startswith('VAR_ARRAY '):
        a=lines[i].split()
        if len(a)!=15:raise ValueError('Invalid array metadata')
        array=dict(id=int(a[1]),key=pointer(a[2]),scope=pointer(a[3]),storage=pointer(a[4]),first=int(a[5]),last=int(a[6]),msb=int(a[7]),lsb=int(a[8]),size=int(a[9]),width=int(a[10]),signed=int(a[11]),swap=int(a[12]),head=int(a[13]),cache=pointer(a[14]),words=[],cacheParent=None,cacheWords=[])
        if array['id']!=len(arrays)+1 or min(array['key'],array['scope'],array['storage'],array['size'],array['width'])<=0 or array['size']!=array['last']-array['first']+1 or array['width']!=abs(array['msb']-array['lsb'])+1 or array['signed'] not in (0,1) or array['swap'] not in (0,1):raise ValueError('Invalid array identity/range')
        i+=1
        for index in range(array['size']):
            if i>=len(lines):raise ValueError('Missing array word')
            a=lines[i].split();i+=1
            if len(a)!=3 or a[:2]!=['VAR_WORD',str(index)] or len(a[2])!=array['width'] or set(a[2])-set('0123'):raise ValueError('Invalid logical word')
            array['words'].append(a[2])
        if array['cache']:
            if i>=len(lines):raise ValueError('Missing word cache')
            a=lines[i].split();i+=1
            if len(a)!=2 or a[0]!='VAR_CACHE':raise ValueError('Invalid word-cache parent')
            array['cacheParent']=pointer(a[1])
            for index in range(array['size']):
                if i>=len(lines):raise ValueError('Missing cached word')
                a=lines[i].split();i+=1
                if len(a)!=3 or a[:2]!=['VAR_CACHE_WORD',str(index)]:raise ValueError('Invalid cached word index')
                array['cacheWords'].append(pointer(a[2]))
        arrays.append(array)
    while i<len(lines) and lines[i].startswith('VAR_PORT '):
        a=lines[i].split();i+=1
        if len(a)!=7:raise ValueError('Invalid read port')
        port=dict(id=int(a[1]),key=pointer(a[2]),array=int(a[3]),net=pointer(a[4]),address=int(a[5]),next=int(a[6]))
        if port['id']<1 or (ports and port['id']<=ports[-1]['id']) or min(port['key'],port['array'],port['net'])<=0 or min(port['address'],port['next'])<0:raise ValueError('Invalid read-port identity')
        ports.append(port)
    if not arrays or lines[i:]!=[f'VAR_END {len(arrays)} {len(ports)}']:raise ValueError('Incomplete array inventory')
    return dict(tick=int(head[2]),arrays=arrays,ports=ports)


def validate(snapshot):
    arrays={a['id']:a for a in snapshot['arrays']};ports={p['id']:p for p in snapshot['ports']};seen=set()
    for key in ('key','storage'):
        if len({a[key] for a in arrays.values()})!=len(arrays):raise ValueError('Aliased array identity/storage')
    if len({p['key'] for p in ports.values()})!=len(ports):raise ValueError('Aliased port identity')
    for array in arrays.values():
        if array['cache'] and (array['cacheParent']!=array['key'] or array['cacheWords']!=[array['cache']]*array['size']):raise ValueError('Wrong cached handle ownership')
        current=array['head']
        while current:
            if current in seen or current not in ports or ports[current]['array']!=array['id']:raise ValueError('Invalid or cyclic port list')
            seen.add(current);current=ports[current]['next']
    if seen!=set(ports):raise ValueError('Unlinked read port')


def target(snapshot,field):
    if field==0:return next((i for i,a in enumerate(snapshot['arrays']) if a['width']<=64),None)
    if field==3:return next((i for i,a in enumerate(snapshot['arrays']) if a['cache']),None)
    if field in (1,2):return next((i for i,p in enumerate(snapshot['ports']) if field==1 or p['next']),None)
    raise ValueError('Unknown array fault')


def changed(before,after,field):
    index=target(before,field)
    if index is None:raise ValueError('Missing array fault target')
    expected=copy.deepcopy(before)
    if field==0:
        word=expected['arrays'][index]['words'][0]
        expected['arrays'][index]['words'][0]=('0' if word[0]=='1' else '1')+word[1:]
    elif field==3:expected['arrays'][index]['cacheWords'][0]=0
    elif field==1:
        port=expected['ports'][index];size=next(a['size'] for a in expected['arrays'] if a['id']==port['array'])
        port['address']=0 if port['address']==size else size
    else:expected['ports'][index]['next']=0
    if expected!=after:raise ValueError('Wrong array fault or unrelated state mutation')


def review(root):
    compiled=profile((root/'probe.vvp').read_text())
    trajectory=None;output=None;faults={i:0 for i in range(4)};coverage=set()
    for mode in ('baseline','disabled','enabled','corrupt'):
        lines=(root/(mode+'.stdout')).read_text().splitlines()
        ordinary=[l for l in lines if not l.startswith(('VAR_','VAM_'))]
        if (root/(mode+'.stderr')).read_text():raise ValueError('Unexpected array diagnostics')
        if len(ordinary)!=4 or ordinary[:3]!=['READ 3000 zz zz','OUTSIDE 4000 xx','PARTIAL 5000 cx'] or '$finish called at 5000 (1ps)' not in ordinary[-1]:raise ValueError('Wrong array continuation')
        if output is None:output=ordinary
        elif output!=ordinary:raise ValueError('Changed full output')
        controls=[l for l in lines if l.startswith(('VAR_','VAM_'))];cursor=0;shots=[];pointers={}
        def consume(line):
            nonlocal cursor
            if cursor>=len(controls) or controls[cursor]!=line:raise ValueError('Expected '+line)
            cursor+=1
        def snapshot():
            nonlocal cursor
            start=cursor
            while cursor<len(controls) and not controls[cursor].startswith('VAR_END '):cursor+=1
            if cursor==len(controls):raise ValueError('Truncated array snapshot')
            cursor+=1;return parse(controls[start:cursor])
        def canonical(value):
            if not value:return value
            if value not in pointers:pointers[value]=len(pointers)+1
            return pointers[value]
        for stage in range(5):
            consume(f'VAM_API {stage} {int(mode!="baseline")}')
            if mode in ('enabled','corrupt'):
                consume('VAM_BEFORE');before=snapshot();validate(before)
                if sorted((a['size'],a['width']) for a in before['arrays'])!=sorted((a['words'],a['width']) for a in compiled['arrays']) or len(before['ports'])!=len(compiled['ports']):raise ValueError('Array/port inventory differs from compiled fixture')
                if before['tick']!=(stage+1)*1000:raise ValueError('Wrong array boundary')
                consume('VAM_REPEAT')
                if snapshot()!=before:raise ValueError('Array observer changed state')
                for a in before['arrays']:
                    if stage==0 and (a['cache'] or any(set(w)!={'3'} for w in a['words'])):raise ValueError('Initial X state or absent handle cache changed')
                    if a['width']>64:
                        coverage.add('wide-unwritten' if set(a['words'][0])=={'3'} else 'wide-written')
                    if any(set(w)=={'2'} for w in a['words']):coverage.add('Z-word')
                    if any('3' in w and set(w)&set('01') for w in a['words']):coverage.add('partial-write')
                    if a['cache']:coverage.add('cached-word-handles')
                for p in before['ports']:
                    if p['address']>=next(a['size'] for a in before['arrays'] if a['id']==p['array']):coverage.add('out-of-range-address')
                if mode=='corrupt':
                    for field in range(4):
                        if target(before,field) is None:continue
                        consume(f'VAM_CHANGED {field}');changed(before,snapshot(),field)
                        consume('VAM_RESTORED')
                        if snapshot()!=before:raise ValueError('Array fault not restored')
                        consume(f'VAM_FAULT {field} 1 1');faults[field]+=1
                normal=copy.deepcopy(before)
                for a in normal['arrays']:
                    for key in ('key','scope','storage','cache','cacheParent'):a[key]=canonical(a[key])
                    a['cacheWords']=[canonical(v) for v in a['cacheWords']]
                for p in normal['ports']:
                    for key in ('key','net'):p[key]=canonical(p[key])
                shots.append(normal)
            consume(f'VAM_DONE {stage}')
        if cursor!=len(controls):raise ValueError('Extra array records')
        if shots:
            if trajectory is None:trajectory=shots
            elif trajectory!=shots:raise ValueError('Changed normal array trajectory')
    required={'wide-unwritten','wide-written','Z-word','partial-write','cached-word-handles','out-of-range-address'}
    if not required<=coverage or not all(faults.values()):raise ValueError('Missing array coverage')
    return dict(qualified=False,controlsPassed=True,simulationOutputExactlyEqual=True,normalStateTrajectoryExactlyEqual=True,
                restoredFaults=sum(faults.values()),faultsByField=faults,coverage=sorted(coverage),
                scope='Static four-state arrays, read-port address/link state and existing word-handle ownership. Restored narrow-word faults avoid allocating wide backing storage; observation preserves unwritten X values.',
                unsupportedProfilesRefused=review_refusal(root),notEstablished=['Board integration and capture budgets','Alias and other unsupported-family controls','Destination net/fanout and callback contents','Raw allocation/freed-storage equivalence or general rollback'])


def review_refusal(root):
    runs=json.loads((root/'run.json').read_text())['runs']
    for family in ('auto','two','callback'):
        compiled=(root/(family+'.vvp')).read_text()
        if '.array "memory"' not in compiled:raise ValueError('Refusal fixture lost its memory')
        if family=='auto' and not analyze(compiled)['emitted']['automaticScopes']:raise ValueError('Missing automatic scope stimulus')
        if family=='two' and '.array/2u "other"' not in compiled:raise ValueError('Missing two-state storage stimulus')
        if family=='callback' and '"$array_callback"' not in compiled:raise ValueError('Missing callback registration stimulus')
        reference=None
        for mode in ('baseline','disabled','enabled','corrupt'):
            name=family+'-'+mode;lines=(root/(name+'.stdout')).read_text().splitlines()
            if (root/(name+'.stderr')).read_text():raise ValueError('Unexpected refusal diagnostic')
            if mode in ('enabled','corrupt'):
                if runs[name]['exitCode']!=2 or lines!=['VAM_API 0 1']:raise ValueError('Unsupported array profile accepted')
            else:
                if runs[name]['exitCode']!=0 or len(lines)!=4 or lines[:3]!=['VAM_API 0 '+str(int(mode!='baseline')),'VAM_DONE 0','CONTINUED 1000'] or '$finish called at 1000 (1ps)' not in lines[-1]:raise ValueError('Refusal control failed')
                if reference is None:reference=lines[1:]
                elif reference!=lines[1:]:raise ValueError('Disabled observer changed unsupported continuation')
    return ['automatic-context','two-state-storage','array-callbacks']


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed built runtime')
    for ext in ('c','v'):shutil.copy2(HERE/('fixtures/array_probe.c' if ext=='c' else 'fixtures/array_probe.v'),out/f'probe.{ext}')
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')]]
    shutil.copy2(HERE/'fixtures/array_unsupported.v',out/'unsupported.v')
    for family in ('auto','two','callback'):commands.append(['iverilog','-g2012','-DARRAY_'+family.upper(),'-o',str(out/(family+'.vvp')),str(out/'unsupported.v')])
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands.append(['cc',*flags,'-I'+str(candidate),'-o',str(out/'probe.vpi'),str(out/'probe.c')])
    for cmd in commands:subprocess.run(cmd,check=True)
    paths=[baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',*modules.glob('*.vpi')]
    pins={str(p):sha(p) for p in paths};runs={}
    for name,lib,mode in [('baseline',baseline,'off'),('disabled',candidate/'vvp/libvvp.so','off'),('enabled',candidate/'vvp/libvvp.so','on'),('corrupt',candidate/'vvp/libvvp.so','corrupt')]:
        env=dict(os.environ,K7658_ARRAY_PROBE=mode);env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp']
        r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr)
        runs[name]={'command':cmd,'exitCode':r.returncode,'library':str(lib),'mode':mode};r.check_returncode()
        for family in ('auto','two','callback'):
            command=cmd[:-1]+[family+'.vvp'];r=subprocess.run(command,cwd=out,env=env,capture_output=True,text=True,timeout=30)
            label=family+'-'+name
            (out/(label+'.stdout')).write_text(r.stdout);(out/(label+'.stderr')).write_text(r.stderr)
            runs[label]=dict(command=command,exitCode=r.returncode,library=str(lib),mode=mode)

    if any(sha(Path(p))!=h for p,h in pins.items()):raise ValueError('Runtime changed during controls')
    shutil.copy2(candidate/'build.json',out/'build.json')
    (out/'run.json').write_text(json.dumps({'qualified':False,'commands':commands,'runs':runs,'dependencies':pins,'candidateBuildSha256':sha(candidate/'build.json'),'sources':{n:sha(HERE/n) for n in ('array_probe.py','array_source_contract.py','compiled_scope_profile.py','thread_board_reachability.py','fixtures/array_probe.c','fixtures/array_probe.v','fixtures/array_unsupported.v')}},indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if json.loads(json.dumps(review(a.check)))!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed assessment')
        print('Array storage/read-port controls and restored faults verified.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
