#!/usr/bin/env python3
"""Review native parameter destruction, stale-owner refusal and address reuse."""
import argparse,copy,json,os,platform,shutil,struct,subprocess
from pathlib import Path
from ttl7406_probe import sha
from memory_metadata import parse as parse_memory
from array_probe import parse as parse_arrays, validate as validate_arrays
HERE=Path(__file__).resolve().parent


def parse_image(lines):
    from parameter_payload import parse
    from scope_metadata_records import parse as metadata_parse
    from scope_metadata_bindings import reference_parse
    starts=[i for i,line in enumerate(lines) if line.startswith(('VPM_BEGIN ','VSM_BEGIN ','VSMR_BEGIN '))]
    if len(starts)!=3 or starts[0]!=0:raise ValueError('Missing parameter/scope images')
    ends=starts[1:]+[len(lines)];parameters,metadata,reference=[fn(lines[a:b]) for fn,a,b in zip((parse,metadata_parse,reference_parse),starts,ends)]
    if len({x['tick'] for x in (parameters,metadata,reference)})!=1:raise ValueError('Scope time mismatch')
    refs={r['id']:r for r in reference['scopes']}
    if set(refs)!={r['id'] for r in metadata['scopes']}:raise ValueError('Unbound scopes')
    if {r['id']:(r['pointer'],r['type']) for r in reference['objects']}!={r['id']:(r['pointer'],41) for r in parameters['rows']}:raise ValueError('Stale or missing parameter object registration')
    owners={}
    for scope in metadata['scopes']:
        for item in scope['intern']:
            if item['id'] in owners or item['type']!=41:raise ValueError('Duplicate or wrong scope object')
            owners[item['id']]=refs[scope['id']]['pointer']
    if owners!={r['id']:r['scope'] for r in parameters['rows']}:raise ValueError('Unbound parameter owner')
    return parameters


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
                for c in (0,1,2):
                    expected.append(f'CREATED {n} {c}')
                    if mode=='enabled':expected.append(f'REFUSED {n} {c} 3')
                    expected += [f'DESTROYED {n} {c}',f'DETACHED {n} {c}']
        if events!=expected+['CONTINUE 3 123456789abcdef01234 1.5','finish']:raise ValueError('Missing destruction/refusal or changed continuation')
    labels={f'before{n}' for n in (1,2)}|{f'{phase}{n}_{c}' for phase in ('created','detached') for n in (1,2) for c in (0,1,2)}
    if set(images)!=labels:raise ValueError('Missing lifecycle images')
    ids=[];pointers=[]
    for n in (1,2):
        before=images[f'before{n}'];parameters=parse_image(before)
        if parameters['tick']!=1000*n or len(parameters['rows'])!=4:raise ValueError('Wrong initial state')
        for c in (0,1,2):
            if images[f'detached{n}_{c}']!=before:raise ValueError('Destruction/detachment left stale state')
            new=parse_image(images[f'created{n}_{c}'])
            if new['tick']!=parameters['tick'] or len(new['rows'])!=5 or new['rows'][:-1]!=parameters['rows']:raise ValueError('Changed original parameter state')
            row=new['rows'][-1];v=row['value']
            if row['name']!=f'__parameter_lifecycle_{c}_{3*(n-1)+c+1}\0'.encode().hex() or row['scope']!=parameters['rows'][0]['scope'] or row['id']<=max(x['id'] for x in parameters['rows']) or row['kind']!=('binary','real','string')[c]:raise ValueError('Wrong reconstructed parameter')
            if c==0:
                if v['width']!=80 or v['signed'] or v['sized']:raise ValueError('Wrong binary shape')
                for bit in range(80):
                    a,b=v['words'][bit//v['wordBits']];mask=1<<(bit%v['wordBits'])
                    if not a&mask or bool(b&mask)!=(bit!=0):raise ValueError('Wrong binary payload')
            elif c==1 and v['value']!=struct.pack('=d',2.5).hex():raise ValueError('Wrong real payload')
            elif c==2 and v['value']!='47005200':raise ValueError('Wrong embedded-null string')
            ids.append(row['id']);pointers.append(row['pointer'])
    if ids!=sorted(set(ids)) or len(set(pointers))!=1:raise ValueError('Missing fresh identities at the same native address')
    return dict(qualified=False,controlsPassed=True,nativeDestructions=6,sameAddressConstructions=6,freshObjectIds=ids,zeroOutputRefusals=18,exactDetachedRestorations=6,originalHdlContinuationExactlyEqual=True,scope='Exact binary/real/string native destructors invalidate observer and scope ownership. Three inventories refuse stale scope entries after each destruction. Detachment restores all original inventories exactly; six placements at one reserved address receive fresh IDs and preserve wide X, real and embedded-null string payloads. Test-owned parameters have no compiled references. Full graph teardown, allocator-dependent reuse, external dangling handles and operational deletion remain unqualified.')


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed runtime')
    for ext in ('cc','v'):shutil.copy2(HERE/f'fixtures/parameter_lifecycle.{ext}',out/f'probe.{ext}')
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
