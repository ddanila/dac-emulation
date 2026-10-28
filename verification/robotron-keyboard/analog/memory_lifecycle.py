#!/usr/bin/env python3
"""Review native memory destruction, stale-owner refusal and address reuse."""
import argparse,copy,json,os,platform,shutil,struct,subprocess
from pathlib import Path
from ttl7406_probe import sha
from memory_metadata import parse as parse_memory
from array_probe import parse as parse_arrays, validate as validate_arrays
HERE=Path(__file__).resolve().parent


def parse_image(lines):
    from array_compact_probe import separate
    ordinary,count,dense,packed=separate(lines)
    if count!=1:raise ValueError('Missing paired compact inventory')
    end=next(i for i,line in enumerate(ordinary) if line.startswith('VMM_END '))
    memory=parse_memory(ordinary[:end+1]);start=end+1
    end=next(i for i,line in enumerate(ordinary) if line.startswith('VAR_END '))
    arrays=parse_arrays(ordinary[start:end+1]);validate_arrays(arrays)
    if memory['tick']!=arrays['tick'] or {r['array'] for r in memory['rows']}!={a['key'] for a in arrays['arrays']}:raise ValueError('Unbound memory state')
    from scope_metadata_records import parse as metadata_parse
    from scope_metadata_bindings import reference_parse
    split=next((i for i,line in enumerate(ordinary) if line.startswith('VSMR_BEGIN ')),None)
    if split is None:raise ValueError('Missing scope reference image')
    metadata=metadata_parse(ordinary[end+1:split]);reference=reference_parse(ordinary[split:])
    if metadata['tick']!=memory['tick'] or reference['tick']!=memory['tick']:raise ValueError('Scope time mismatch')
    refs={r['id']:r for r in reference['scopes']}
    if set(refs)!={r['id'] for r in metadata['scopes']}:raise ValueError('Unbound scopes')
    if {r['id']:(r['pointer'],r['type']) for r in reference['objects']}!={r['id']:(r['handle'],29) for r in memory['rows']}:raise ValueError('Stale or missing memory object registration')
    ownership={}
    for scope in metadata['scopes']:
        for item in scope['intern']:
            if item['id'] in ownership or item['type']!=29:raise ValueError('Duplicate or wrong scope object')
            ownership[item['id']]=refs[scope['id']]['pointer']
    if ownership!={r['id']:r['scope'] for r in memory['rows']}:raise ValueError('Unbound memory scope membership')
    return memory,arrays


def review(root):
    receipt=json.loads((root/'run.json').read_text());images={}
    if set(receipt['runs'])!={'baseline','disabled','enabled'}:raise ValueError('Missing lifecycle controls')
    for mode in ('baseline','disabled','enabled'):
        if receipt['runs'][mode]['exitCode'] or (root/(mode+'.stderr')).read_text():raise ValueError('Native lifecycle failed')
        lines=(root/(mode+'.stdout')).read_text().splitlines();i=0;events=[]
        while i<len(lines):
            line=lines[i];i+=1
            if line.startswith('IMAGE '):
                label=line.split()[1];start=i
                while i<len(lines) and lines[i]!='IMAGE_END':i+=1
                if i==len(lines) or mode!='enabled' or label in images:raise ValueError('Invalid lifecycle image')
                images[label]=lines[start:i];parse_image(images[label]);i+=1
            else:events.append('finish' if '$finish called at 3000 (1ps)' in line else line)
        expected=[]
        for n in (1,2):
            expected.append(f'ROUND {n}')
            if mode!='baseline':
                expected.append(f'INVALID {n}')
                for c in (0,1):
                    expected.append(f'CREATED {n} {c}')
                    if mode=='enabled':expected.append(f'REFUSED {n} {c} 5')
                    expected += [f'DESTROYED {n} {c}',f'DETACHED {n} {c}']
        if events!=expected+['CONTINUE 17 34','finish']:raise ValueError('Missing destruction/refusal or changed continuation')
    labels={f'before{n}' for n in (1,2)}|{f'{phase}{n}_{c}' for phase in ('created','detached') for n in (1,2) for c in (0,1)}
    if set(images)!=labels:raise ValueError('Missing lifecycle images')
    ids=[];pointers=[]
    for n in (1,2):
        before=images[f'before{n}'];m,a=parse_image(before)
        if m['tick']!=1000*n or len(m['rows'])!=1:raise ValueError('Wrong initial state')
        for c in (0,1):
            if images[f'detached{n}_{c}']!=before:raise ValueError('Destruction/detachment left stale state')
            new,arr=parse_image(images[f'created{n}_{c}'])
            if new['tick']!=m['tick'] or len(new['rows'])!=2 or new['rows'][:-1]!=m['rows'] or len(arr['arrays'])!=2 or arr['arrays'][:-1]!=a['arrays'] or arr['ports']!=a['ports']:raise ValueError('Changed original memory state')
            row=new['rows'][-1];word=arr['arrays'][-1]
            if row['name']!=f'__lifecycle_{2*(n-1)+c+1}\0'.encode().hex() or row['scope']!=m['rows'][0]['scope'] or row['id']<=m['rows'][0]['id'] or word['words']!=['1'*8,'3'*8] or not word['cache']:raise ValueError('Wrong reconstructed memory')
            ids.append(row['id']);pointers.append((row['handle'],row['array']))
    if ids!=sorted(set(ids)) or len(set(pointers))!=1:raise ValueError('Missing fresh identities at the same native address')
    return dict(qualified=False,controlsPassed=True,nativeDestructions=4,sameAddressConstructions=4,freshObjectIds=ids,zeroOutputRefusals=20,exactDetachedRestorations=4,pairedArrayImages=10,originalHdlContinuationExactlyEqual=True,scope='Diagnostic scope-registered static memories use the native destructor and placement reconstruction at one address in four cycles. Destruction invalidates memory/scope observer ownership; five inventories refuse stale intern entries before output. Removing the stale entry restores every baseline inventory byte. Reconstructed objects have fresh monotonic IDs and valid payload/cache ownership. Test-owned memories have no HDL references, read ports or callbacks; full graph teardown, dangling external VPI handles, and operational deletion remain unqualified.')


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed runtime')
    for ext in ('cc','v'):shutil.copy2(HERE/f'fixtures/memory_lifecycle.{ext}',out/f'probe.{ext}')
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
