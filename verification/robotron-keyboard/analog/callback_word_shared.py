#!/usr/bin/env python3
"""Check native net-array association lists and restored fields."""
import argparse,copy,json,os,platform,shutil,subprocess
from pathlib import Path
from callback_list_probe import parse
from net_probe import pointer
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent

def review(root):
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        regenerated=Path(tmp)/'probe.vvp'
        regenerated.write_bytes((root/'compiler.vvp').read_bytes());adapt(regenerated)
        if regenerated.read_bytes()!=(root/'probe.vvp').read_bytes() or json.loads((regenerated.parent/'adapter.json').read_text())!=json.loads((root/'adapter.json').read_text()):raise ValueError('Changed native test adapter')
    receipt=json.loads((root/'run.json').read_text());faults={};observations=0;reference=None
    expected_output=['VALUE 1000 0000 0000','VALUE 3000 1100 0011','VALUE 5000 0101 1010','VALUE 7000 10xz 10xz','finish']
    for mode in ('baseline','disabled','enabled','corrupt'):
        if receipt['runs'][mode]['exitCode'] or (root/(mode+'.stderr')).read_text():raise ValueError('Native array association run failed')
        lines=(root/(mode+'.stdout')).read_text().splitlines();cursor=stage=0;ordinary=[];sources={};arrays={};layout=None
        def consume(wanted):
            nonlocal cursor
            if cursor>=len(lines) or lines[cursor]!=wanted:raise ValueError('Expected '+wanted)
            cursor+=1
        def snapshot():
            nonlocal cursor
            start=cursor
            while cursor<len(lines) and not lines[cursor].startswith('VCL_END '):cursor+=1
            if cursor==len(lines):raise ValueError('Truncated array association list')
            cursor+=1;return parse(lines[start:cursor])
        while cursor<len(lines):
            line=lines[cursor]
            if not line.startswith('WORD_STAGE '):ordinary.append('finish' if '$finish called at 8000 (1ps)' in line else line);cursor+=1;continue
            consume(f'WORD_STAGE {stage}')
            if mode in ('enabled','corrupt'):
                if not stage:
                    for name,size in (('words',2),('aliases',3)):
                        a=lines[cursor].split();cursor+=1
                        if len(a)!=4 or a[:2]!=['WORD_ARRAY',name] or int(a[3])!=size or not pointer(a[2]):raise ValueError('Missing native array binding')
                        arrays[name]=(pointer(a[2]),size)
                        for index in range(size):
                            a=lines[cursor].split();cursor+=1
                            if len(a)!=4 or a[:3]!=['WORD_SOURCE',name,str(index)] or not pointer(a[3]):raise ValueError('Missing typed word owner binding')
                            sources[(name,index)]=pointer(a[3])
                    if len(set(sources.values()))!=2 or len({p for p,n in arrays.values()})!=2:raise ValueError('Aliased native metadata')
                consume('WORD_BEFORE');before=snapshot();consume('WORD_REPEAT')
                if snapshot()!=before or before['tick']!=(stage*2+1)*1000:raise ValueError('Changed association observation or time')
                if layout is None:layout=before['owners']
                if before['owners']!=layout:raise ValueError('Association list changed across native propagation')
                by_owner={o['pointer']:o for o in before['owners']};allowed={p:n for p,n in arrays.values()};rows=[]
                for o in before['owners']:
                    if o['callbacks']:raise ValueError('Unexpected value callback')
                    for word in o['words']:
                        if word['array'] not in allowed or word['word']>=allowed[word['array']]:raise ValueError('Foreign array/word referent')
                        rows.append(word)
                expected={}
                for (name,index),key in sources.items():expected.setdefault(key,set()).add((arrays[name][0],index))
                if sorted(map(len,expected.values()))!=[2,3]:raise ValueError('Missing shared-owner association chains')
                if not sources['words',0]==sources['aliases',0]==sources['aliases',1] or sources['words',1]!=sources['aliases',2]:raise ValueError('Wrong shared driver identity')
                # Native attachment prepends each node; monotonic allocation IDs
                # expose order even when compile-time forward references resolve later.
                for key in expected:
                    if key not in by_owner:raise ValueError('Missing native word owner')
                    ids=[w['id'] for w in by_owner[key]['words']]
                    if ids!=sorted(ids,reverse=True):raise ValueError('Wrong native association order')
                for key,members in expected.items():
                    if key not in by_owner or {(w['array'],w['word']) for w in by_owner[key]['words']}!=members:raise ValueError('Wrong shared-owner membership')
                if len(rows)!=5:raise ValueError('Missing/duplicate array association')
                observations+=1
                if mode=='corrupt':
                    for row in rows:
                        for field in range(3):
                            consume(f"WORD_FAULT {row['id']} {field} {-1 if field==2 else 0}")
                            if field!=2:
                                actual=snapshot();changed=copy.deepcopy(before);word=next(w for o in changed['owners'] for w in o['words'] if w['id']==row['id'])
                                if field==0:word['word']^=1
                                else:word['array']=1
                                if actual!=changed:raise ValueError('Wrong association fault or unrelated change')
                            consume('WORD_RESTORED')
                            if snapshot()!=before:raise ValueError('Association fault not restored')
                            key=f"{row['id']}:{field}";faults[key]=faults.get(key,0)+1
            consume(f'WORD_DONE {stage}');stage+=1
        if stage!=4 or ordinary!=expected_output:raise ValueError('Changed native dynamic array selection: '+repr(ordinary))
        if reference is None:reference=ordinary
        if ordinary!=reference:raise ValueError('Candidate changed original continuation')
    if len(faults)!=15 or set(faults.values())!={4}:raise ValueError('Missing association field controls')
    return dict(qualified=False,controlsPassed=True,observations=observations,faultsByTarget=faults,originalContinuationExactlyEqual=True,scope='A test-only VVP adapter connects five array words directly to their original two driver nodes, exercising shared-owner association chains through native attachment and dispatch on both original and candidate runtimes. Independently obtained VPI word owners bind every association. Concrete array identities use the adjusted native pointer rather than the VPI base-subobject address. Every array pointer and word address binds to VPI array identity/size and expected word membership. Full lists survive dynamic read-port selection and X/Z propagation. Index and array-pointer faults change only their target field; invalid next pointers refuse before output. All restore before original-equivalent continuation.',notEstablished=['Runtime creation/removal of array-word associations','Registration during active callbacks and typed callback object/user referents','Compact encoding, operational integration and general rollback'])

def adapt(path):
    """Native test adapter: bypass only the five compiler-inserted array BUFZs.

    Preserve the emitted design separately. Both original and candidate execute
    the same adapted VVP. This tests native shared ownership, not compiler output.
    """
    import re
    original=path.read_text();lines=original.splitlines();drivers={};arrays={};buffers={}
    for line in lines:
        m=re.fullmatch(r'(\S+) \.var "([ab])", 3 0;',line)
        if m:drivers[m[2]]=m[1]
        m=re.fullmatch(r'(\S+) \.array "(words|aliases)", [12] 0;',line)
        if m:arrays[m[1]]=m[2]
        m=re.fullmatch(r'(\S+) \.functor BUFZ 4, (\S+), C4<0000>, C4<0000>, C4<0000>;',line)
        if m:buffers[m[1]]=m[2]
    if set(drivers)!={'a','b'} or set(arrays.values())!={'words','aliases'}:raise ValueError('Changed fixture compiler layout')
    replaced=[]
    for i,line in enumerate(lines):
        m=re.fullmatch(r'(\S+ \.net) (\S+) ([012]), 3 0, (\S+); 1 drivers',line)
        if not m or m[2] not in arrays:continue
        name=arrays[m[2]];index=int(m[3]);source='b' if index==(1 if name=='words' else 2) else 'a'
        if buffers.get(m[4])!=drivers[source]:raise ValueError('Unexpected array driver buffer')
        lines[i]=f'{m[1]} {m[2]} {m[3]}, 3 0, {drivers[source]}; 1 drivers'
        replaced.append(dict(array=name,index=index,buffer=m[4],driver=drivers[source]))
    if len(replaced)!=5:raise ValueError('Missing native shared-owner attachments')
    path.with_name('compiler.vvp').write_text(original)
    path.write_text('\n'.join(lines)+'\n')
    path.with_name('adapter.json').write_text(json.dumps(dict(scope='Test-only native shared-owner net-array wiring; not an unmodified compiler artifact.',compilerSha256=sha(path.with_name('compiler.vvp')),adaptedSha256=sha(path),replacements=replaced),indent=2)+'\n')

def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed built runtime')
    for ext in ('cc','v'):shutil.copy2(HERE/f'fixtures/callback_words.{ext}',out/f'probe.{ext}')
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')]]
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands.append(['c++','-std=c++11',*flags,'-I'+str(candidate),'-I'+str(candidate/'vvp'),'-o',str(out/'probe.vpi'),str(out/'probe.cc')])
    for cmd in commands:subprocess.run(cmd,check=True)
    adapt(out/'probe.vvp')
    paths=[baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',*modules.glob('*.vpi')]
    pins={str(p):sha(p) for p in paths};runs={}
    for name,lib,mode in [('baseline',baseline,'off'),('disabled',candidate/'vvp/libvvp.so','off'),('enabled',candidate/'vvp/libvvp.so','on'),('corrupt',candidate/'vvp/libvvp.so','corrupt')]:
        env=dict(os.environ,K7658_CALLBACK_WORDS=mode);env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp']
        r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr)
        runs[name]={'command':cmd,'exitCode':r.returncode,'library':str(lib),'mode':mode};r.check_returncode()
    if any(sha(Path(p))!=h for p,h in pins.items()):raise ValueError('Runtime changed during controls')
    shutil.copy2(candidate/'build.json',out/'build.json')
    (out/'run.json').write_text(json.dumps({'qualified':False,'commands':commands,'runs':runs,'dependencies':pins,'candidateBuildSha256':sha(candidate/'build.json'),'sources':{n:sha(HERE/n) for n in ('callback_word_shared.py','callback_word_probe.py','callback_list_probe.py','net_probe.py','net_types_probe.py','fixtures/callback_words.cc','fixtures/callback_words.v')}},indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if review(a.check)!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed assessment')
        print('Native array-word associations verified.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need all runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
