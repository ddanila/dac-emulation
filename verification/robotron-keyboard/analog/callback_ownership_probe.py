#!/usr/bin/env python3
"""Show native callback cancellation hidden by complete wire/head snapshots."""
import argparse,json,os,platform,shutil,subprocess
from pathlib import Path
from wire_probe import parse
from callback_ownership_contract import analyze
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent

def review(root):
    receipt=json.loads((root/'run.json').read_text());contract=json.loads((root/'source-contract.json').read_text())
    if analyze(contract['evidence'])!=contract['analysis']:raise ValueError('Changed source ownership analysis')
    expected=[f'CALLBACK 2000 {label} 1 0' for label in 'CBA']+[f'CALLBACK 4000 {label} 2 0' for label in 'CA']+['finish']
    original=None;state=None
    for mode in ('original','disabled','observe','no-cancel'):
        if receipt['runs'][mode]['exitCode'] or (root/(mode+'.stderr')).read_text():raise ValueError('Failed native continuation')
        lines=(root/(mode+'.stdout')).read_text().splitlines();ordinary=[];cursor=0;seen=False
        while cursor<len(lines):
            line=lines[cursor];cursor+=1
            if line!='OWN_BEFORE':ordinary.append('finish' if '$finish called at 5000 (1ps)' in line else line);continue
            if seen or mode!='observe':raise ValueError('Unexpected ownership witness')
            seen=True;start=cursor
            while cursor<len(lines) and lines[cursor]!='OWN_AFTER':cursor+=1
            if cursor==len(lines):raise ValueError('Missing after snapshot')
            before=lines[start:cursor];cursor+=1;start=cursor
            while cursor<len(lines) and not lines[cursor].startswith('OWN_CANCELLED '):cursor+=1
            if cursor==len(lines):raise ValueError('Missing cancellation identity')
            after=lines[start:cursor];marker=lines[cursor].split();cursor+=1
            if len(marker)!=2 or int(marker[1])<1:raise ValueError('Missing live callback identity')
            state=parse(before)
            if before!=after or state['tick']!=3000:raise ValueError('Wire/head image changed during cancellation')
            if sum(bool(f['callbacks']) for f in state['filters'])!=1:raise ValueError('Missing native callback owner')
        want=expected if mode!='no-cancel' else [f'CALLBACK {tick} {label} {value} 0' for tick,value in ((2000,1),(4000,2)) for label in 'CBA']+['finish']
        if ordinary!=want or seen!=(mode=='observe'):raise ValueError('Changed native callback order or continuation')
        if mode=='original':original=ordinary
        if mode in ('disabled','observe') and ordinary!=original:raise ValueError('Candidate differs from original')
    if state is None:raise ValueError('Missing native witness')
    return dict(qualified=False,controlsPassed=True,completeWireAndHeadImagesExactlyEqual=True,cancelledMiddleCallbackChangesContinuation=True,originalAndCandidateContinuationExactlyEqual=True,sourceContractSha256=sha(root/'source-contract.json'),scope='Native middle-callback cancellation leaves complete wire/filter payloads and callback/array-word heads identical, but removes one subsequent invocation. All three callbacks share a native owner and execute in reverse registration order. This is a counterexample to head-only state sufficiency, not complete callback-list observation.',nextRequirements=contract['analysis']['admissionRequirements'])

def run(candidate,baseline,modules,contract,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for name,digest in build['outputs'].items():
        if sha(candidate/name)!=digest:raise ValueError('Changed native runtime')
    for ext in ('c','v'):shutil.copy2(HERE/f'fixtures/callback_ownership.{ext}',out/f'probe.{ext}')
    shutil.copy2(contract,out/'source-contract.json');shutil.copy2(candidate/'build.json',out/'build.json')
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')],['cc',*flags,'-I'+str(candidate),'-o',str(out/'probe.vpi'),str(out/'probe.c')]]
    for command in commands:subprocess.run(command,check=True)
    paths=[baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',*modules.glob('*.vpi')];pins={str(p):sha(p) for p in paths};runs={}
    for name,lib in [('original',baseline),('disabled',candidate/'vvp/libvvp.so'),('observe',candidate/'vvp/libvvp.so'),('no-cancel',baseline)]:
        env=dict(os.environ,K7658_CALLBACK_OWNERSHIP=name);env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp'];r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr);runs[name]=dict(command=cmd,exitCode=r.returncode,library=str(lib));r.check_returncode()
    if any(sha(Path(p))!=h for p,h in pins.items()):raise ValueError('Changed runtime during controls')
    sources={n:sha(HERE/n) for n in ('callback_ownership_probe.py','callback_ownership_contract.py','wire_probe.py','island_filter_probe.py','net_probe.py','fixtures/callback_ownership.c','fixtures/callback_ownership.v')}
    (out/'run.json').write_text(json.dumps(dict(commands=commands,runs=runs,dependencies=pins,sources=sources),indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','contract','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if review(a.check)!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed assessment')
        print('Callback ownership counterexample and source contract verified.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.contract,a.out)):p.error('Need runtime, source contract and fresh output paths')
        run(a.candidate,a.baseline,a.modules,a.contract,a.out)
