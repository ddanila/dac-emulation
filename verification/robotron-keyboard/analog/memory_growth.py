#!/usr/bin/env python3
"""Review native memory allocation after a complete initial inventory."""
import argparse,copy,json,os,platform,shutil,struct,subprocess
from pathlib import Path
from ttl7406_probe import sha
from memory_metadata import parse as parse_memory
from array_probe import parse as parse_arrays, validate as validate_arrays
HERE=Path(__file__).resolve().parent


def parse(lines):
    split=next((i for i,line in enumerate(lines) if line.startswith('VAR_BEGIN ')),None)
    if split is None:raise ValueError('Missing dense array image')
    memory=parse_memory(lines[:split]);arrays=parse_arrays(lines[split:]);validate_arrays(arrays)
    if memory['tick']!=arrays['tick'] or {r['array'] for r in memory['rows']}!={a['key'] for a in arrays['arrays']}:raise ValueError('Memory/array mismatch')
    return dict(memory=memory,arrays=arrays)


def review(root):
    receipt=json.loads((root/'run.json').read_text());images={}
    if set(receipt['runs'])!={'baseline','disabled','enabled'}:raise ValueError('Missing growth comparisons')
    for mode in ('baseline','disabled','enabled'):
        if receipt['runs'][mode]['exitCode'] or (root/(mode+'.stderr')).read_text():raise ValueError('Native growth failed')
        lines=(root/(mode+'.stdout')).read_text().splitlines();i=0;events=[]
        while i<len(lines):
            line=lines[i];i+=1
            if line.startswith('IMAGE '):
                label=line.split()[1];start=i
                while i<len(lines) and lines[i]!='IMAGE_END':i+=1
                if i==len(lines) or mode!='enabled' or label in images:raise ValueError('Invalid growth image')
                images[label]=parse(lines[start:i]);i+=1
            else:events.append('finish' if '$finish called at 3000 (1ps)' in line else line)
        expected=[]
        for n in (1,2):
            expected.append(f'ROUND {n}')
            if mode!='baseline':
                expected.append(f'REFUSED {n}')
                for k in range(2):expected += [f'ADDED {n} {k}',f'CACHED {n} {k}']
        if events!=expected+['CONTINUE 17 34','finish']:raise ValueError('Missing growth or changed continuation')
    labels={f'before{n}' for n in (1,2)}|{f'{phase}{n}_{k}' for phase in ('after','cached') for n in (1,2) for k in range(2)}
    if set(images)!=labels or len(images['before1']['memory']['rows'])!=1:raise ValueError('Missing full growth coverage')
    previous=None
    for n in (1,2):
        before=images[f'before{n}']
        if before['memory']['tick']!=n*1000:raise ValueError('Wrong growth time')
        if previous is not None:
            expected=copy.deepcopy(previous)
            for stream in expected.values():stream['tick']=n*1000
            if before!=expected:raise ValueError('Growth state changed across continuation')
        for kind in range(2):
            after=images[f'after{n}_{kind}'];old=before['memory']['rows'];rows=after['memory']['rows']
            if after['memory']['tick']!=n*1000 or len(rows)!=len(old)+1 or rows[:-1]!=old:raise ValueError('Changed existing memory state')
            row=rows[-1];serial=2*(n-1)+kind+1
            if row['id']<=max(p['id'] for p in old) or row['handle'] in {p['handle'] for p in old} or row['scope']!=old[0]['scope'] or bytes.fromhex(row['name'])!=f'__memory_growth_{kind}_{serial}\0'.encode():raise ValueError('Invalid fresh memory identity')
            old_arrays=before['arrays'];new_arrays=after['arrays'];a=new_arrays['arrays'][-1]
            if new_arrays['arrays'][:-1]!=old_arrays['arrays'] or len(new_arrays['arrays'])!=len(old_arrays['arrays'])+1 or new_arrays['ports']!=old_arrays['ports']:raise ValueError('Changed existing array payload')
            if a['key']!=row['array'] or a['scope']!=row['scope'] or a['first']!=(1 if kind else 0) or a['last']!=(3 if kind else 1) or a['width']!=(80 if kind else 8) or a['signed']!=kind or a['swap']!=kind or a['cache'] or a['head']:raise ValueError('Wrong new array shape')
            if a['words']!=[('1' if i%2==0 else '0')+'3'*(a['width']-1) for i in range(a['size'])]:raise ValueError('Wrong new array value')
            cached=images[f'cached{n}_{kind}'];expected=copy.deepcopy(after);c=cached['arrays']['arrays'][-1]
            if not c['cache']:raise ValueError('Missing lazy word cache')
            for key in ('cache','cacheParent','cacheWords'):expected['arrays']['arrays'][-1][key]=c[key]
            if cached!=expected:raise ValueError('Lazy cache changed other state')
            before=cached
        previous=before
    return dict(qualified=False,controlsPassed=True,initialMemories=1,finalMemories=5,newMemories=4,lazyCaches=4,rounds=2,unknownKindRefusals=2,originalHdlContinuationExactlyEqual=True,scope='Native opt-in allocation after initial inventory adds static 8-bit and signed 80-bit memories with ascending/descending declared ranges. Fresh identities, complete X-bearing payloads, unchanged prior state and lazy word caches are checked across continuation. Destruction, address reuse, compact logging and operational board qualification remain separate.')


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed runtime')
    for ext in ('cc','v'):shutil.copy2(HERE/f'fixtures/memory_growth.{ext}',out/f'probe.{ext}')
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands=[['iverilog','-g2012','-ginterconnect','-o',str(out/'probe.vvp'),str(out/'probe.v')],['c++','-std=c++11',*flags,'-I'+str(candidate),'-I'+str(candidate/'vvp'),'-o',str(out/'probe.vpi'),str(out/'probe.cc')]]
    for cmd in commands:subprocess.run(cmd,check=True)
    pins={str(p):sha(p) for p in [baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',out/'probe.vvp',*modules.glob('*.vpi')]};runs={}
    for mode in ('baseline','disabled','enabled'):
        lib=baseline if mode=='baseline' else candidate/'vvp/libvvp.so'
        env=dict(os.environ,K7658_PORT_PAYLOAD='on' if mode=='enabled' else 'off');env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
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
