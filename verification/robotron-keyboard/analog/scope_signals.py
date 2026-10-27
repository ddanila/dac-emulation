#!/usr/bin/env python3
"""Replay complete registered scope signal payloads independent of bridge admission."""
import argparse,json,os,platform,shutil,subprocess,copy
from pathlib import Path
from ttl7406_probe import sha
from signal_handles import parse as signal_parse
HERE=Path(__file__).resolve().parent
REFUSALS=('node','scope','name','array-arm','cache','bit-index','bit-parent','bit-base','missing-owner','duplicate-owner')


def parse(lines):
    i=next((i for i,l in enumerate(lines) if l.startswith('VSH_BEGIN ')),None)
    if i is None or not lines[0].startswith('VSA_BEGIN '):raise ValueError('Missing scope/admitted signal image')
    return dict(all=signal_parse([l.replace('VSA_','VSH_',1) for l in lines[:i]]),admitted=signal_parse(lines[i:]))


def review(root):
    receipt=json.loads((root/'run.json').read_text());images={}
    for mode in ('baseline','disabled','enabled'):
        if receipt['runs'][mode]['exitCode'] or (root/(mode+'.stderr')).read_text():raise ValueError('Native scope signal failure')
        lines=(root/(mode+'.stdout')).read_text().splitlines();i=0;events=[]
        while i<len(lines):
            line=lines[i];i+=1
            if line.startswith('IMAGE '):
                key=line.split()[1];start=i
                while i<len(lines) and lines[i]!='IMAGE_END':i+=1
                if i==len(lines) or key in images or mode!='enabled':raise ValueError('Invalid scope signal image')
                images[key]=parse(lines[start:i]);i+=1
            else:events.append('finish' if '$finish called at 3000 (1ps)' in line else line)
        expected=[]
        for r in (1,2):
            expected += [f'ROUND {r}','SIGNAL -6 10']
            if mode=='enabled':expected += ['REFUSED '+s for s in REFUSALS]
            expected.append(f'RESTORED {r}')
        if events!=expected+['CONTINUE -6 -6','finish']:raise ValueError('Changed scope signal continuation/refusal')
    if set(images)!={f'{kind}{r}' for r in (1,2) for kind in ('before','signed','range','restored','cached','cached-restored')}:raise ValueError('Missing scope signal controls')
    for r in (1,2):
        before=images[f'before{r}'];all_rows=before['all']['rows'];admitted=before['admitted']['rows']
        if before['all']['tick']!=r*1000 or len(all_rows)!=2 or len(admitted)!=1 or admitted[0] not in all_rows:raise ValueError('Wrong scope signal coverage')
        index=next(i for i,row in enumerate(all_rows) if row not in admitted)
        if bytes.fromhex(all_rows[index]['name'])!=b'hidden\0':raise ValueError('Wrong unadmitted target')
        for kind,key,value in (('signed','signed',0),('range','msb',4)):
            expected=copy.deepcopy(before);expected['all']['rows'][index][key]=value
            if images[f'{kind}{r}']!=expected:raise ValueError('Wrong isolated signal change')
        if images[f'restored{r}']!=before:raise ValueError('Signal restoration differs')
        cached=images[f'cached{r}'];expected=copy.deepcopy(before);row=cached['all']['rows'][index]
        if row['count']!=4 or not row['bits'] or [b['value'] for b in row['cache']]!=[0,1,2,3]:raise ValueError('Invalid native lazy cache')
        for key in ('bits','count','cache'):expected['all']['rows'][index][key]=row[key]
        if cached!=expected or images[f'cached-restored{r}']!=cached:raise ValueError('Cache growth/restoration differs')
        if r==1 and all_rows[index]['count']!=0:raise ValueError('Cache was not created during probe')
        if r==2 and before!=cached:raise ValueError('Second cache access changed state')
    return dict(qualified=False,controlsPassed=True,rounds=2,registeredScopeSignals=2,admittedBridgeSignals=1,
        zeroOutputRefusalsPerRound=len(REFUSALS),originalContinuationExactlyEqual=True,
        scope='Every registered vector signal is observed independently of explicit bridge admission. Unadmitted signedness/range changes and lazy bit creation are captured exactly. Ten invalid pointer/union/cache/ownership cases per round refuse before output and restore exactly. Existing admission is unchanged. Static native fixture only; unsupported-family, lifecycle and operational board qualification remain open.')


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed runtime')
    for ext in ('cc','v'):shutil.copy2(HERE/f'fixtures/scope_signals.{ext}',out/f'probe.{ext}')
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
