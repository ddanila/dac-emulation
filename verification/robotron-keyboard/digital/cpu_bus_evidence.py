#!/usr/bin/env python3
"""Retain and independently reassess production keyboard digital acceptance."""
import argparse
import gzip
import io
import json
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path
from qualify import ROOT, sha
from cpu_bus_review import parse as pins, failures, nop_oracle, memory_oracle
from c_read_instructions import parse as instructions, programs
from io_boundary_evidence import artifacts, verify_capture
from verify_joint_phase import extract
HERE=Path(__file__).resolve().parent
REPORTS=HERE/'reports/cpu-bus'
RUNS={'hdl':(ROOT/'build/keyboard-controller-cpu-bus','assessment.json'),
      'cross':(ROOT/'build/keyboard-controller-cpu-bus','cross-pins.json'),
      'instructions':(ROOT/'build/keyboard-controller-cpu-bus-instructions','assessment.json'),
      'firmware':(ROOT/'build/keyboard-controller-cpu-bus-production','assessment.json')}


def verify(reports,base):
    for name,r in reports.items():
        for path,digest in r['sources'].items():
            if sha(ROOT/path)!=digest:raise ValueError('Producer source changed: '+path)
        for path,digest in artifacts(name,r).items():
            if sha(base/name/path)!=digest:raise ValueError('Capture changed: '+name+'/'+path)
    h=reports['hdl'];assert h['passed'] and h['refreshDisabledDetected']
    expected={f'{name}-{suffix}' for name in ('nop','mixed','indexed','block','internal') for suffix in ['plain',*[f'bus-{i}' for i in range(200)]]}
    expected|={'late-plain',*[f'wait-bus-{i}' for i in range(1,5)],*[f'{kind}-{im}-{mode}' for kind in ('irq','nmi') for im in range(3) for mode in ('plain','bus')]}
    assert {r['id'] for r in h['cases']}==expected
    for case in h['cases']:
        rows=pins((base/'hdl'/(case['id']+'.txt')).read_text())
        assert case['passed'] and not failures(rows)
        if case['id']=='nop-plain':assert not nop_oracle(rows)
        if case['id']=='mixed-plain':assert not memory_oracle(rows)
    assert nop_oracle(pins((base/'hdl/no-refresh.txt').read_text()))
    c=reports['cross'];assert c['passed'] and c['pinsCompared']
    assert {r['id'] for r in c['cases']}==expected
    for case in c['cases']:
        label=case['id'];clog=(base/'cross'/(label+'.txt')).read_text();hlog=(base/'hdl'/(label+'.txt')).read_text()
        rows=pins(hlog)
        wire=[list(map(int,line.split()[1:])) for line in clog.splitlines() if line.startswith('WIRE ')]
        bus=[list(map(int,line.split()[1:])) for line in clog.splitlines() if line.startswith('BUS ')]
        assert len(wire)==len(bus)==len(rows)==800
        keys='cycle edge address data m1 mreq iorq rd wr rfsh halt busack'.split()
        for w,b,r in zip(wire,bus,rows):
            v=dict(zip(keys,w));assert b[:3]==[r['cycle'],r['edge'],r['busack']]
            selected=[k for k in keys if k not in ('address','data')]
            if r['mreq'] or r['iorq'] or v['mreq'] or v['iorq']:selected+=['address']
            if r['wr'] or v['wr']:selected+=['data']
            assert all(v[k]==r[k] for k in selected),(label,v,r)
        result=lambda text:[line for line in text.splitlines() if line.startswith(('RESULT ','OUTPUT '))]
        assert result(clog)==result(hlog)==case['cResult']==case['hdlResult']
        assert case['busackAgrees'] and case['resultAgrees'] and not case['pinMismatches']
    r=reports['instructions'];assert r['passed'] and r['productionBackendTested']
    expected={f'{name}-{late}-{wait}-{reset}' for name in programs() for late in (0,1)
              if not(late and (name=='indexed-memory' or name.startswith(('out','ot'))))
              for wait,reset in ((0,0),(1,0),(0,1))}
    assert {x['id'] for x in r['cases']}==expected
    for case in r['cases']:
        folder=base/'instructions'/case['id'];cv=instructions(folder/'c.txt');hv=instructions(folder/'hdl.txt')
        assert cv['RAM']==hv['RAM'] and [v[1:] for v in cv['OUT']]==[v[1:] for v in hv['OUT']]
        assert cv['FINAL'][-1][:2]==hv['AF'][-1]==case['cAF']==case['hdlAF']
        assert cv['FINAL'][-1][-1]==1 and hv['HALT']==[[1]] and case['passed']
        if case['id'].rsplit('-',3)[1]=='1':assert cv['LATE']
    assert reports['firmware']['productionBackendTested']
    verify_capture('firmware',reports['firmware'],base/'firmware')
    assert all(reports['firmware'][k] for k in ('functionalAgreement','serialCycleAgreement','realLedTransitionAgreement'))
    subprocess.run(['python3',str(ROOT/'tools/generate_keyboard_cpu.py'),'--check'],check=True)
    with tempfile.TemporaryDirectory() as tmp:
        exe=Path(tmp)/'backend'
        subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror',str(ROOT/'tests/integration/keyboard_backend_test.c'),str(ROOT/'machines/robotron1715m/keyboard_board.c'),str(ROOT/'machines/robotron1715m/keyboard_cpu.c'),'-o',str(exe)],check=True)
        subprocess.run([str(exe)],check=True)
    assert 'keyboard_board.o' in (ROOT/'Makefile').read_text()
    assert '#include "keyboard_board.h"' in (ROOT/'machines/robotron1715m/robotron.h').read_text()
    assert 'machines/robotron1715m/keyboard_board.c' in (ROOT/'runners/browser/build.sh').read_text()
    return {'qualified':True,'productionAdopted':True,
            'gates':{'machineCycleArbitration':True,'memoryRefreshInterruptPins':True,
                     'instructionFlagsWaitResetAndLateInputs':True,'firmwareFunctionalAgreement':True,
                     'serialCycleAgreement':True,'knownLedTransitionAgreement':True,
                     'startupValidityAndCpuOnlyReset':True,'nativeAndBrowserBackendSelected':True},
            'boundary':'Reference Z80 digital acceptance for the retained instruction, phase-sweep and complete standard-S600 scenarios. Selected addresses, write data and controls agree at identical edge labels; inactive/undriven bus values are not CPU-output comparisons. BUSRQ exposes bus ownership, not driven zeroes. This is not exhaustive Z80 opcode conformance, U880 specimen calibration, analog qualification or historical copper verification.'}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--retain',action='store_true');a=ap.parse_args()
    REPORTS.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        base=Path(tmp)
        if a.retain:
            reports={name:json.loads((folder/report).read_text()) for name,(folder,report) in RUNS.items()}
            for name,r in reports.items():
                folder=RUNS[name][0]/('c-pins' if name=='cross' else '')
                for path in artifacts(name,r):
                    dest=base/name/path;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(folder/path,dest)
            result=verify(reports,base)
            for name,r in reports.items():(REPORTS/(name+'.json')).write_text(json.dumps(r,indent=2)+'\n')
            (REPORTS/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
            with (REPORTS/'captures.tar.gz').open('wb') as target:
                with gzip.GzipFile(filename='',fileobj=target,mode='wb',mtime=0) as compressed:
                    with tarfile.open(fileobj=compressed,mode='w') as archive:
                        for path in sorted(base.rglob('*')):
                            if path.is_file():
                                info=tarfile.TarInfo(str(path.relative_to(base)));data=path.read_bytes();info.size=len(data);info.mode=0o644;archive.addfile(info,io.BytesIO(data))
            receipt={p.name:sha(p) for p in REPORTS.iterdir() if p.name!='receipt.json'}
            (REPORTS/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
        else:
            receipt=json.loads((REPORTS/'receipt.json').read_text())
            for name,digest in receipt.items():assert sha(REPORTS/name)==digest,name
            extract(REPORTS/'captures.tar.gz',base)
            reports={name:json.loads((REPORTS/(name+'.json')).read_text()) for name in RUNS}
            assert verify(reports,base)==json.loads((REPORTS/'summary.json').read_text())
    print('Production keyboard digital acceptance verified; electrical and specimen scope remains separate.')
if __name__=='__main__':main()
