#!/usr/bin/env python3
"""Measure real-shim output clamping for scheduled and input-driven transitions."""
import argparse,json,math,os,re,shutil,subprocess
from fractions import Fraction
from pathlib import Path
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
KINDS=('scheduled-blocking','scheduled-nba','input-blocking','input-nba')


def cases():
    for base in (10000,1078001720):
        center=base*1e-12
        for offset,target in [('below',math.nextafter(center,0)),('exact',center),('above',math.nextafter(center,math.inf)),('quarter',center+.25e-12),('threequarter',center+.75e-12)]:
            for path,prior in [('direct',0.),('staged',target-4.0900804e-12),('near',target-.25e-12)]:
                for kind in range(4):yield f'{base}-{offset}-{path}-{kind}',base,kind,target,prior


def observe(text):
    if 'Error:' in text or 'Invalid absolute' in text:raise ValueError('Runtime diagnostic')
    ticks=re.findall(r'^OUTPUT_TICK (\d+)$',text,re.M)
    outputs=re.findall(r'^OUTPUT time=(\S+) bit=0 state=1 strength=0$',text,re.M)
    if len(ticks)!=1 or len(outputs)!=1:raise ValueError('Missing unique native/delivered edge')
    last=0.;clamps=[]
    for line in text.splitlines():
        if line.startswith('RETURN '):
            match=re.fullmatch(r'RETURN requested=(\S+) returned=(\S+)',line)
            value=float.fromhex(match[2])
            if value<last:raise ValueError('Backward return time')
            last=value
        if line.startswith('OUTPUT '):
            value=float.fromhex(line.split()[1].split('=')[1])
            if value<last:raise ValueError('Output precedes accepted entry time')
        if line.startswith('TIME_AUDIT output '):
            d=dict(x.split('=',1) for x in line.split()[2:]);clamps.append(d)
    return dict(tick=int(ticks[0]),deliveredTime=outputs[0],callbacks=clamps,
                continuation=re.findall(r'^(?:OUTPUT_TICK|OUTPUT|RETURN|APPLY) .+$',text,re.M))


def review(root):
    receipt=json.loads((root/'run.json').read_text());result=[]
    for name,base,kind,target,prior in cases():
        measured={}
        for mode in ('baseline','off','on','drain'):
            entry=receipt['runs'][name+'/'+mode];log=root/entry['log']
            if entry['exitCode'] or entry['target']!=target.hex() or entry['prior']!=prior.hex() or sha(log)!=entry['sha256']:raise ValueError('Failed or changed probe case')
            expected_env={} if mode in ('baseline','off') else {'ROBOTRON_ABSOLUTE_TICKS':'1'}
            if mode=='drain':expected_env['ROBOTRON_DRAIN_TICK']='1'
            if entry['environment']!=expected_env:raise ValueError('Changed mode environment')
            measured[mode]=observe(log.read_text())
        if measured['baseline']!=measured['off']:raise ValueError('Disabled candidate differs from original')
        for label in ('on','drain'):
            expected_tick=base if kind<2 else int(Fraction(target)/Fraction(1e-12))
            if measured[label]['tick']!=expected_tick:raise ValueError('Wrong native event tick')
        if kind<2 and float.fromhex(measured['drain']['deliveredTime'])!=base*1e-12:raise ValueError('Drain did not preserve autonomous event time')
        if kind>=2 and float.fromhex(measured['drain']['deliveredTime'])<target:raise ValueError('Drain broke input causality')
        expected=base if kind<2 else int(Fraction(target)/Fraction(1e-12))
        actual=measured['on']
        if actual['tick']!=expected:raise ValueError('Wrong native event tick')
        delivered=float.fromhex(actual['deliveredTime']);native=expected*1e-12
        if kind>=2 and delivered<target:raise ValueError('Input-driven output predates input application')
        result.append(dict(case=name,kind=KINDS[kind],target=target.hex(),prior=prior.hex(),nativeTick=expected,
                           deliveredTime=actual['deliveredTime'],deliveryMinusNativeSeconds=delivered-native,
                           callbacks=actual['callbacks'],drained=measured['drain']))
    autonomous=[r for r in result if r['kind'].startswith('scheduled') and r['deliveryMinusNativeSeconds']>1e-15]
    driven=[r for r in result if r['kind'].startswith('input') and r['deliveryMinusNativeSeconds']>1e-15]
    if not driven:raise ValueError('Missing causal clamp control')
    return dict(qualified=False,controlsPassed=True,disabledExactlyMatchesOriginal=True,noBackwardReturnsOrOutputs=True,drainedAutonomousTimesExactlyMatchNative=True,drainedInputCausalityPreserved=True,
                cases=result,delayedAutonomousCases=autonomous,clampedInputCases=driven,
                scope='Real-shim scheduled blocking/NBA and input-driven blocking/NBA outputs under fractional entry histories. Exact-tick mode preserves the specified native tick; delivery and entry ordering are measured separately.',
                notEstablished=['Correctness of removing entry-time clamping','Board output-event provenance and numerical convergence','Rollback or physical timing'])


def run(a):
    out=a.out.resolve();out.mkdir(exist_ok=False);board=json.loads(a.board_receipt.read_text());candidate=a.candidate.resolve()
    libs={Path(d['path']).name:d for d in board['externalDependencies'] if Path(d['path']).name in ('ivlng.so','ivlng.vpi','libvvp.so')}
    build=json.loads((candidate/'build.json').read_text())
    if sha(candidate/'ivlng.vpi')!=build['outputs']['ivlng.vpi']:raise ValueError('Changed candidate')
    for d in libs.values():
        if sha(Path(d['path']))!=d['sha256']:raise ValueError('Changed original library')
    include=a.source/'src/include';commands=[['cc','-std=c11','-I'+str(include),str(HERE/'fixtures/input_tick_probe.c'),'-o',str(out/'probe')]]
    subprocess.run(commands[0],check=True);dependencies={d['path']:d['sha256'] for d in libs.values()};dependencies[str(candidate/'ivlng.vpi')]=sha(candidate/'ivlng.vpi');dependencies[str(out/'probe')]=sha(out/'probe')
    for base in (10000,1078001720):
        for kind in range(4):
            vvp=out/f'{base}-{kind}.vvp';cmd=['iverilog','-g2012','-s','output_time_probe',f'-Poutput_time_probe.KIND={kind}',f'-Poutput_time_probe.EVENT_TICK={base}','-o',str(vvp),str(HERE/'fixtures/output_time_probe.v')]
            commands.append(cmd);subprocess.run(cmd,check=True);dependencies[str(vvp)]=sha(vvp)
            for name in re.findall(r'^:vpi_module "([^"]+)";',vvp.read_text(),re.M):dependencies[name]=sha(Path(name))
    receipt=dict(commands=commands,boardReceiptSha256=sha(a.board_receipt),dependencies=dependencies,sources={n:sha(HERE/n) for n in ('output_time_probe.py','fixtures/output_time_probe.v','fixtures/input_tick_probe.c')},probeSha256=sha(out/'probe'),runs={})
    shutil.copy2(candidate/'build.json',out/'candidate-build.json')
    for name,base,kind,target,prior in cases():
        for mode in ('baseline','off','on','drain'):
            env={k:v for k,v in os.environ.items() if not k.startswith('ROBOTRON_')}
            if mode in ('on','drain'):env['ROBOTRON_ABSOLUTE_TICKS']='1'
            if mode=='drain':env['ROBOTRON_DRAIN_TICK']='1'
            vpi=libs['ivlng.vpi']['path'] if mode=='baseline' else str(candidate/'ivlng.vpi')
            cmd=[str(out/'probe'),libs['ivlng.so']['path'],libs['libvvp.so']['path'],vpi,str(out/f'{base}-{kind}.vvp'),target.hex(),prior.hex()]
            log=out/(name+'-'+mode+'.log')
            with log.open('w') as f:r=subprocess.run(cmd,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=10)
            if log.stat().st_size>1024**2:raise ValueError('Excessive probe output')
            receipt['runs'][name+'/'+mode]=dict(command=cmd,exitCode=r.returncode,target=target.hex(),prior=prior.hex(),log=log.name,sha256=sha(log),environment={k:v for k,v in env.items() if k.startswith('ROBOTRON_')})
    if any(sha(Path(n))!=h for n,h in dependencies.items()):raise ValueError('Changed runtime during probe')
    (out/'run.json').write_text(json.dumps(receipt,indent=2)+'\n');(out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('source','candidate','board-receipt','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if review(a.check)!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed output-time assessment')
    else:
        if not all((a.source,a.candidate,a.board_receipt,a.out)):p.error('Need real shim paths and fresh output')
        run(a)
