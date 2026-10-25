#!/usr/bin/env python3
"""Compare real keyboard HDL state across controlled d_cosim barrier rejections."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
from compressed_output import capture
from controller_interface import generate
from cpu_read_phase_candidate import circuit_sources
from trace_io import open_text
from ttl7406_probe import sha
from compare_firmware_io import sha as logical_sha

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
BOUNDARY=('Controlled input-barrier trials through pinned d_cosim scheduler code and real Icarus keyboard HDL. '
          'Exposed HDL variables, bridge queues and continuation are checked. '
          'No analog Newton/LTE convergence, arbitrary rollback, complete event-queue introspection or full-repeat claim.')


def observations(path):
    snapshots=[];events=[];block=None;summary=None
    with open_text(path) as stream:
        for line in stream:
            if line.startswith('SNAPSHOT '):
                if block is not None:raise ValueError('Nested snapshot')
                block=[line]
            elif line=='END_SNAPSHOT\n':
                if block is None:raise ValueError('Orphan snapshot end')
                snapshots.append(''.join(block));block=None
            elif block is not None:block.append(line)
            elif line.startswith('STATE_RESULT '):
                if summary is not None:raise ValueError('Duplicate completion')
                match=re.fullmatch(r'STATE_RESULT items=(\d+) delivered=(\d+) outputs=(\d+) rejected=(\d+)\n',line)
                if not match:raise ValueError('Malformed completion')
                summary=dict(zip(('items','delivered','outputs','rejected'),map(int,match.groups())))
            else:events.append(line)
    if block is not None or summary is None or len(snapshots)!=16:raise ValueError('Incomplete state capture')
    if [int(s.splitlines()[0].split()[1]) for s in snapshots]!=list(range(16,257,16)):
        raise ValueError('Wrong continuation boundaries')
    return snapshots,events,summary


def assess(out):
    control,events,base=observations(out/'control.log')
    retry,retry_events,on=observations(out/'retry.log')
    delayed,delayed_events,negative=observations(out/'delayed-corruption.log')
    if base['rejected']!=0 or on['rejected']!=512 or negative['rejected']!=512:
        raise ValueError('Missing rejection coverage')
    if control!=retry or events!=retry_events or any(base[k]!=on[k] for k in ('items','delivered','outputs')):
        raise ValueError('Rejected trials changed continuation')
    if delayed==control and delayed_events==events:raise ValueError('Delayed corruption escaped continuation check')
    if not any(line.startswith('FIRST_FETCH ') for line in events):raise ValueError('No firmware execution')
    states=[line for line in control[0].splitlines() if line.startswith('state ')]
    names=[line.split()[1] for line in states]
    if len(names)!=base['items'] or len(set(names))!=len(names):raise ValueError('Incomplete state inventory')
    if not any('.cpu.' in n for n in names) or sum(n.startswith('boot_cosim.rom[') for n in names)!=2048:
        raise ValueError('Missing CPU or ROM state')
    if control[0].splitlines()[1:]==control[-1].splitlines()[1:]:raise ValueError('Vacuous continuation')
    with open_text(out/'register-corruption.log') as stream:
        if 'Rejected trial changed internal state at edge 16' not in stream.read():raise ValueError('Missing immediate corruption detection')
    return {'stateAndContinuationPassed':True,'immediateCorruptionDetected':True,
            'delayedCorruptionDetectedByContinuation':True,'exposedStateObjects':len(names),
            'rejectedTrials':on['rejected'],'continuationBoundaries':len(control),
            'qualified':False,'boundary':BOUNDARY}


def run(args):
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    bridge=json.loads(args.bridge.read_text())
    for item in bridge['libraries'].values():
        if sha(Path(item['path']))!=item['sha256']:raise ValueError('Changed bridge dependency')
    ng=args.ngspice_source.resolve()
    upstream=HERE/'fixtures/ngspice-47/d_cosim.mod'
    if sha(upstream)!='aa31bc8cf686914b3f667c9790aae4b79115a6f3b0e786732358a63df9340207':raise ValueError('Changed scheduler source')
    if sha(args.rom)!='11de663d84c848533ece1432b541c3a1ca3a95da47098e7aef79daeb9bc28966':raise ValueError('Need standard S600 hex')
    source=out/'src/xspice/icm/digital/d_cosim/cfunc.mod';source.parent.mkdir(parents=True);shutil.copyfile(upstream,source)
    subprocess.run(['patch','-d',str(out),'-p1','-i',str(HERE/'engine-patches/cosim-input-barrier.patch')],check=True,capture_output=True)
    text=source.read_text();scheduler=text[text.index('static int advance('):text.index('/* Check whether an input value has changed.')]
    scheduler=scheduler.replace(', XSPICE_ARG','').replace(', ARGS','')
    (out/'probe.c').write_text((HERE/'fixtures/cosim_state_harness.c').read_text().replace('/* SCHEDULER */',scheduler))
    includes=[ng/'src/include',ng/'src/xspice/verilog',args.vpi_include]
    subprocess.run(['cc','-std=c11','-O2',*[f'-I{p}' for p in includes],str(out/'probe.c'),'-o',str(out/'probe')],check=True)
    (out/'controller_analog.v').write_text(generate(explicit_cpu_drive=True,resolved_bus=True))
    cpu,profile=circuit_sources(ROOT/'third_party/cpu/tv80',out,'qualified-digital')
    hdl=[*cpu,HERE.parent/'chips.v',HERE.parent/'generated/controller.v',HERE/'boot_cosim.v',out/'controller_analog.v']
    subprocess.run(['iverilog','-g2012','-DTV80_REFRESH','-s','boot_cosim','-o',str(out/'board.vvp'),*map(str,hdl)],check=True)
    shutil.copyfile(args.rom,out/'s600.hex');shutil.copyfile(args.bridge,out/'bridge.json')
    receipt={'bridgeSha256':sha(args.bridge),'cpu':profile,'sources':{str(p):sha(p) for p in [Path(__file__),HERE/'fixtures/cosim_state_harness.c',upstream,HERE/'engine-patches/cosim-input-barrier.patch',*hdl]},
             'headers':{str(p):sha(p) for p in [ng/'src/include/ngspice/cmtypes.h',ng/'src/include/ngspice/cosim.h',ng/'src/xspice/verilog/coroutine.h',ng/'src/xspice/verilog/icarus_shim.h',args.vpi_include/'vpi_user.h']},
             'compiler':subprocess.check_output(['cc','--version'],text=True).splitlines()[0],
             'iverilog':subprocess.run(['iverilog','-V'],capture_output=True,text=True,check=True).stdout.splitlines()[0],
             'inputs':{name:sha(out/name) for name in ('probe.c','probe','board.vvp','s600.hex')},'runs':{},'qualified':False}
    for name,mode in [('control',0),('retry',1),('register-corruption',2),('delayed-corruption',3)]:
        with capture(out,[name+'.log']) as storage:
            with (out/(name+'.log')).open('w') as log:
                process=subprocess.run([str(out/'probe'),bridge['libraries']['shim']['path'],bridge['libraries']['libvvp']['path'],bridge['libraries']['vpi']['path'],str(out/'board.vvp'),str(mode)],cwd=out,stdout=log,stderr=subprocess.STDOUT,timeout=60)
        receipt['runs'][name]={'exitCode':process.returncode,'storage':storage}
        (out/'run.json').write_text(json.dumps(receipt,indent=2)+'\n')
        if process.returncode!=(2 if mode==2 else 0):raise ValueError('Unexpected state-probe exit '+name)
    for item in bridge['libraries'].values():
        if sha(Path(item['path']))!=item['sha256']:raise ValueError('Bridge changed during probe')
    result=assess(out);(out/'assessment.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


def check(out):
    manifest=json.loads((out/'manifest.json').read_text())
    actual={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name!='manifest.json'}
    if actual!=manifest:raise ValueError('Changed retained internal-state evidence')
    receipt=json.loads((out/'run.json').read_text())
    for name,run in receipt['runs'].items():
        if run['exitCode']!=(2 if name=='register-corruption' else 0):raise ValueError('Incomplete state run')
        if logical_sha(out/(name+'.log'))!=run['storage'][name+'.log']['sha256']:
            raise ValueError('Changed captured state log')
    if assess(out)!=json.loads((out/'assessment.json').read_text()):raise ValueError('Changed state interpretation')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('bridge','ngspice-source','vpi-include','rom'):p.add_argument('--'+name,type=Path)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--check',action='store_true')
    args=p.parse_args()
    if args.check:check(args.out)
    else:
        if not all((args.bridge,args.ngspice_source,args.vpi_include,args.rom)):p.error('Capture needs bridge, source, VPI headers and ROM')
        run(args)
