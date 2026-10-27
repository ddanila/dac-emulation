#!/usr/bin/env python3
"""Validate complete admitted callback lists and deferred native removal."""
import argparse,copy,json,os,platform,shutil,subprocess
from pathlib import Path
from net_probe import pointer
from net_types_probe import class_name
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent

def parse(lines):
    if len(lines)<2:raise ValueError('Truncated callback list')
    a=lines[0].split()
    if len(a)!=3 or a[:2]!=['VCL_BEGIN','1'] or int(a[2])<0:raise ValueError('Invalid callback list header')
    tick=int(a[2]);owners=[];callbacks=set();words=set();addresses=set();i=1
    while i<len(lines) and lines[i].startswith('VCL_OWNER '):
        a=lines[i].split();i+=1
        if len(a)!=8:raise ValueError('Invalid callback owner')
        owner=dict(id=int(a[1]),pointer=pointer(a[2]),kind=class_name(a[3]),head=pointer(a[4]),wordHead=pointer(a[5]),callbacks=[],words=[])
        if owner['id']<=0 or (owners and owner['id']<=owners[-1]['id']) or owner['pointer']<=0 or owner['pointer'] in addresses or owner['kind'] not in ('vvp_wire_vec4','vvp_wire_vec8'):raise ValueError('Invalid/unknown callback owner')
        addresses.add(owner['pointer']);nc,nw=map(int,a[6:]);next_cb=owner['head'];next_word=owner['wordHead']
        if min(nc,nw)<0:raise ValueError('Negative list length')
        for _ in range(nc):
            if i>=len(lines):raise ValueError('Missing callback')
            a=lines[i].split();i+=1
            if len(a)!=12 or a[0]!='VCL_CALLBACK':raise ValueError('Invalid callback record')
            cb=dict(id=int(a[1]),pointer=pointer(a[2]),next=pointer(a[3]),reason=int(a[4]),function=pointer(a[5]),object=pointer(a[6]),user=pointer(a[7]),time=pointer(a[8]),value=pointer(a[9]),timeType=int(a[10]),format=int(a[11]))
            if cb['id']<=0 or cb['id'] in callbacks or cb['pointer']<=0 or cb['pointer'] in addresses or cb['pointer']!=next_cb or not cb['time'] or not cb['value'] or (cb['reason'],cb['timeType'],cb['format'])!=(1,3,9):raise ValueError('Invalid callback membership or admission')
            callbacks.add(cb['id']);addresses.add(cb['pointer']);next_cb=cb['next'];owner['callbacks'].append(cb)
        for _ in range(nw):
            if i>=len(lines):raise ValueError('Missing array-word association')
            a=lines[i].split();i+=1
            if len(a)!=6 or a[0]!='VCL_WORD':raise ValueError('Invalid array-word association')
            word=dict(id=int(a[1]),pointer=pointer(a[2]),next=pointer(a[3]),array=pointer(a[4]),word=int(a[5]))
            if word['id']<=0 or word['id'] in words or word['pointer']<=0 or word['pointer'] in addresses or word['pointer']!=next_word or word['word']<0:raise ValueError('Invalid array-word membership')
            words.add(word['id']);addresses.add(word['pointer']);next_word=word['next'];owner['words'].append(word)
        if next_cb or next_word:raise ValueError('Unobserved tail or cycle')
        owners.append(owner)
    if lines[i:]!=[f'VCL_END {len(owners)} {len(callbacks)} {len(words)}']:raise ValueError('Incomplete callback list footer')
    return dict(tick=tick,owners=owners)


def review(root):
    receipt=json.loads((root/'run.json').read_text());ordinary_reference=None;faults={};observations=0;dispatch_refusals=0
    want=[f'CALLBACK {tick} {label} {value} 0' for tick,value,labels in ((2000,1,'CBA'),(4000,2,'CA'),(6000,3,'A')) for label in labels]+['finish']
    for mode in ('baseline','disabled','enabled','corrupt'):
        if receipt['runs'][mode]['exitCode'] or (root/(mode+'.stderr')).read_text():raise ValueError('Native callback run failed')
        lines=(root/(mode+'.stdout')).read_text().splitlines();cursor=stage=active=0;ordinary=[];initial=None;identity_rows={};owner_layout=None;admitted=False
        def consume(wanted):
            nonlocal cursor
            if cursor>=len(lines) or lines[cursor]!=wanted:raise ValueError('Expected '+wanted)
            cursor+=1
        def snapshot():
            nonlocal cursor
            start=cursor
            while cursor<len(lines) and not lines[cursor].startswith('VCL_END '):cursor+=1
            if cursor==len(lines):raise ValueError('Truncated list snapshot')
            cursor+=1;return parse(lines[start:cursor])
        while cursor<len(lines):
            line=lines[cursor]
            if line=='LST_UNADMITTED_REFUSED':
                if admitted or stage or mode not in ('enabled','corrupt'):raise ValueError('Invalid registration admission guard')
                admitted=True;cursor+=1;continue
            if line=='LST_ACTIVE_REFUSED':
                if mode not in ('enabled','corrupt'):raise ValueError('Unexpected active refusal')
                active+=1;cursor+=1;continue
            if not line.startswith('LST_STAGE '):
                ordinary.append('finish' if '$finish called at 9000 (1ps)' in line else line);cursor+=1;continue
            consume(f'LST_STAGE {stage}')
            if mode in ('enabled','corrupt'):
                if not admitted:raise ValueError('Missing caller admission')
                consume('LST_BEFORE');before=snapshot();consume('LST_REPEAT')
                if snapshot()!=before:raise ValueError('Observation changed callback state')
                expected_time=(1000,3000,3000,4000,5000,6000,7000,8000)[stage]
                if before['tick']!=expected_time:raise ValueError('Wrong callback lifecycle time')
                layout=[(o['id'],o['pointer'],o['kind'],o['wordHead'],o['words']) for o in before['owners']]
                if owner_layout is None:owner_layout=layout
                if layout!=owner_layout:raise ValueError('Owner allocation or array associations changed')
                populated=[o for o in before['owners'] if o['callbacks']]
                if len(populated)!=(stage!=7):raise ValueError('Wrong callback owner population')
                callbacks=populated[0]['callbacks'] if populated else []
                if stage==0:
                    if len(callbacks)!=3 or len({c['user'] for c in callbacks})!=3 or len({c['object'] for c in callbacks})!=1 or len({c['function'] for c in callbacks})!=1 or not all(c['function'] and c['user'] and c['object'] for c in callbacks):raise ValueError('Wrong callback registration')
                    initial=copy.deepcopy(callbacks);identity_rows={c['id']:c for c in initial}
                indices=((0,1,2),(0,1,2),(0,1,2),(0,2),(0,2),(2,),(2,),())[stage]
                expected=[copy.deepcopy(initial[j]) for j in indices]
                for j,c in enumerate(expected):c['next']=expected[j+1]['pointer'] if j+1<len(expected) else 0
                if stage==2:expected[1]['function']=0
                if stage in (4,6):expected[0]['function']=0
                if callbacks!=expected:raise ValueError('Wrong ordered callback/deferred cancellation state')
                observations+=1
                if mode=='corrupt':
                    for index in range(3):
                        selected=next((c for c in callbacks if c['id']==initial[2-index]['id'] and c['function']),None)
                        if selected is None:continue
                        for field in range(4):
                            consume(f'LST_FAULT {index} {field} {-1 if field==3 else 0}')
                            if field!=3:
                                actual=snapshot();changed=copy.deepcopy(before);cb=next(c for o in changed['owners'] for c in o['callbacks'] if c['id']==selected['id']);cb[('user','object','function')[field]]=1 if field==1 else 0
                                if actual!=changed:raise ValueError('Wrong callback mutation or unrelated change')
                            consume('LST_RESTORED')
                            if snapshot()!=before:raise ValueError('Callback fault not restored')
                            key=f'{index}:{field}';faults[key]=faults.get(key,0)+1
            consume(f'LST_DONE {stage}');stage+=1
        if stage!=8 or ordinary!=want or active!=(6 if mode in ('enabled','corrupt') else 0):raise ValueError('Changed native callback continuation or missing traversal refusal')
        if ordinary_reference is None:ordinary_reference=ordinary
        if ordinary!=ordinary_reference:raise ValueError('Candidate differs from original continuation')
        dispatch_refusals+=active
    if set(faults)!={f'{i}:{f}' for i in range(3) for f in range(4)}:raise ValueError('Missing restored callback fields')
    return dict(qualified=False,controlsPassed=True,observations=observations,faultsByTarget=faults,activeTraversalRefusals=dispatch_refusals,originalContinuationExactlyEqual=True,scope='Native exact-base callbacks on one signal: complete ordered owner/list rows reveal middle, head and final cancellation before delayed deletion. User/object/function faults change only their fields; invalid next pointers refuse before output and all faults restore before continuation. Unadmitted caller fields and active value traversal refuse. Original output order and values remain exact.',notEstablished=['Native nonempty array-word association controls','Native subclass/unknown-owner refusal controls and post-registration allocation growth','Typed signal/array/user-data referents and suspended callback traversal','Compact encoding, operational integration and general rollback'])

def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed built runtime')
    for ext in ('c','v'):shutil.copy2(HERE/f'fixtures/callback_lists.{ext}',out/f'probe.{ext}')
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')]]
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands.append(['cc',*flags,'-I'+str(candidate),'-o',str(out/'probe.vpi'),str(out/'probe.c')])
    for cmd in commands:subprocess.run(cmd,check=True)
    paths=[baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',*modules.glob('*.vpi')]
    pins={str(p):sha(p) for p in paths};runs={}
    for name,lib,mode in [('baseline',baseline,'off'),('disabled',candidate/'vvp/libvvp.so','off'),('enabled',candidate/'vvp/libvvp.so','on'),('corrupt',candidate/'vvp/libvvp.so','corrupt')]:
        env=dict(os.environ,K7658_CALLBACK_LISTS=mode);env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp']
        r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr)
        runs[name]={'command':cmd,'exitCode':r.returncode,'library':str(lib),'mode':mode};r.check_returncode()
    if any(sha(Path(p))!=h for p,h in pins.items()):raise ValueError('Runtime changed during controls')
    shutil.copy2(candidate/'build.json',out/'build.json')
    (out/'run.json').write_text(json.dumps({'qualified':False,'commands':commands,'runs':runs,'dependencies':pins,'candidateBuildSha256':sha(candidate/'build.json'),'sources':{n:sha(HERE/n) for n in ('callback_list_probe.py','net_probe.py','net_types_probe.py','fixtures/callback_lists.c','fixtures/callback_lists.v')}},indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if review(a.check)!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed assessment')
        print('Complete admitted callback list controls verified.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need all runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
