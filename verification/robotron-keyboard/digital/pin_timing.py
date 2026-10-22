#!/usr/bin/env python3
"""Reproduce pin-boundary differences without shifting timestamps or patching cores."""
import argparse
import json
import subprocess
from pathlib import Path
from qualify import ROOT, sha

HERE=Path(__file__).resolve().parent
PROGRAM=bytes.fromhex('3e 55 d3 12 3e aa d3 34 db 56 d3 78 32 00 80 3a 00 80 01 9a bc ed 79 ed 78 d3 90 76')
EXPECTED=[(0x5512,0x55),(0xaa34,0xaa),(0xa678,0xa6),(0x8000,0xa6),(0xbc9a,0xa6),(0xa690,0xa6)]*2

def rows(path):
    result=[]
    for line in path.read_text().splitlines():
        fields=line.split()
        if fields[:1]!=['PIN']:continue
        result.append([int(x) if x.isdigit() else None for x in fields[1:]])
    if len(result)!=800:raise ValueError('Incomplete pin capture')
    if [(p[0],p[1]) for p in result]!=[(c,e) for c in range(400) for e in range(2)]:raise ValueError('Invalid edge coordinates')
    return result

def assess(trace, reset_at=240):
    pulses=[];active=None
    for p in trace:
        cycle,edge,reset,wait,address,data,mreq,iorq,rd,wr=p
        at=cycle*2+edge
        if wr and reset:
            if active is None:
                active={'startHalfCycle':at,'address':address,'data':data,'io':bool(iorq),'samples':[]}
            active['samples'].append([at,address,data,wait])
        elif active is not None:
            active['endHalfCycle']=at
            active['stableAddressAndData']=all(s[1:3]==[active['address'],active['data']] for s in active['samples'])
            pulses.append(active);active=None
    actual=[(p['address'],p['data']) for p in pulses]
    return {'writes':pulses,'expectedWriteValues':actual==EXPECTED,
            'stableDuringWrite':bool(pulses) and all(p['stableAddressAndData'] for p in pulses),
            'resetOutputsInactive':all(p[-4:]==[0,0,0,0] for p in trace if p[2]==0 and p[0]>reset_at),
            'waitObservedDuringWrite':any(s[-1]==0 for p in pulses for s in p['samples']),
            'readAssertions':[{'halfCycle':p[0]*2+p[1],'address':p[4]} for i,p in enumerate(trace) if p[7:9]==[1,1] and (i==0 or trace[i-1][7:9]!=[1,1])]}

def setup_hold(path, assessment):
    drive=[]
    for line in path.read_text().splitlines():
        p=line.split()
        if p[:1]==['DRIVE']:drive.append([int(x) if x.isdigit() else None for x in p[1:]])
    if len(drive)!=800:raise ValueError('Missing output data observations')
    checks=[]
    for pulse in assessment['writes']:
        start,end=pulse['startHalfCycle'],pulse['endHalfCycle']
        expected=[pulse['address'],pulse['data']]
        before=start
        while before>0 and drive[before-1][2:]==expected:before-=1
        after=end
        while after<len(drive) and drive[after][2:]==expected:after+=1
        checks.append({'assertHalfCycle':start,'setupObservedHalfCycles':start-before,
                       'holdObservedHalfCycles':after-end,
                       'knownAtAssertion':pulse['data'] is not None,
                       'stableThroughPulse':pulse['stableAddressAndData']})
    return {'writes':checks,'scope':'HDL address/dout samples at both clock edges; conservative discrete observation intervals, not manufacturer nanosecond limits or electrical output drive qualification.'}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,default=ROOT/'build/keyboard-controller-pin-timing');ap.add_argument('--verify',type=Path);a=ap.parse_args()
    if a.verify:
        report=json.loads((a.verify/'assessment.json').read_text())
        for name,digest in report['sourceHashes'].items():
            if sha(ROOT/name)!=digest:raise ValueError('Producer changed: '+name)
        for name,digest in report['artifacts'].items():
            if sha(a.verify/name)!=digest:raise ValueError('Capture changed: '+name)
        for name,result in report['profiles'].items():
            rebuilt=assess(rows(a.verify/(name+'.txt')))
            if name!='c':rebuilt['setupHold']=setup_hold(a.verify/(name+'.txt'),rebuilt)
            if rebuilt!=result:raise ValueError('Assessment changed: '+name)
        for case,pair in report['scenarios'].items():
            reset_at={'reset-write':16,'reset-read':44}.get(case,240)
            rebuilt={}
            for name in ('c','tv80'):
                rebuilt[name]=assess(rows(a.verify/(case+'-'+name+'.txt')),reset_at)
                rebuilt[name]['postResetRecovery']=[(w['address'],w['data']) for w in rebuilt[name]['writes'] if w['startHalfCycle']>=2*(reset_at+16)]==EXPECTED[:6]
            rebuilt['writeValuesAgree']=[(w['address'],w['data']) for w in rebuilt['c']['writes']]==[(w['address'],w['data']) for w in rebuilt['tv80']['writes']]
            if rebuilt!=pair:raise ValueError('Scenario assessment changed: '+case)
        if report['qualified']:raise ValueError('Unsupported qualification claim')
        print('Retained instruction pin evidence verified; physical timing remains open.')
        return
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
    def run(args,log=None):
        if log:
            with (out/log).open('w') as f:subprocess.run(list(map(str,args)),check=True,stdout=f,timeout=30)
        else:subprocess.run(list(map(str,args)),check=True,timeout=30)
    (out/'program.bin').write_bytes(PROGRAM)
    (out/'program.hex').write_text('\n'.join(f'{b:02x}' for b in PROGRAM)+ '\n')
    run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror',HERE/'pin_timing.c','-o',out/'probe'])
    run([out/'probe',out/'program.bin',240,15,19],'c.txt')
    rtl=sorted((ROOT/'third_party/cpu/tv80').glob('*.v'))
    for name,early in [('tv80',0),('early-write',1)]:
        run(['iverilog','-g2012','-s','pin_timing',f'-Ppin_timing.EARLY={early}','-o',out/(name+'.vvp'),*rtl,HERE/'pin_timing.v'])
        run(['vvp',out/(name+'.vvp'),'+rom='+str(out/'program.hex'),'+reset_at=240','+wait_at=15','+wait_end=19'],name+'.txt')
    reports={name:assess(rows(out/(name+'.txt'))) for name in ('c','tv80','early-write')}
    for name in ('tv80','early-write'):reports[name]['setupHold']=setup_hold(out/(name+'.txt'),reports[name])
    # The negative control must expose bad data; matching edge positions alone is insufficient.
    if not all(w['knownAtAssertion'] and w['setupObservedHalfCycles']>0 and w['holdObservedHalfCycles']>0 for w in reports['tv80']['setupHold']['writes']):raise ValueError('Default HDL setup/hold regression')
    if not all(reports[n]['expectedWriteValues'] and reports[n]['stableDuringWrite'] and reports[n]['resetOutputsInactive'] and reports[n]['waitObservedDuringWrite'] for n in ('c','tv80')):raise ValueError('Baseline instruction regression')
    if reports['early-write']['expectedWriteValues'] or reports['early-write']['stableDuringWrite']:raise ValueError('Negative control no longer exposes stale data; review required')
    scenarios={}
    for case,reset_at,wait_at,wait_end in [('no-wait',240,0,0),('read-wait',240,43,48),('reset-write',16,0,0),('reset-read',44,0,0)]:
        pair={}
        for name in ('c','tv80'):
            log=case+'-'+name+'.txt'
            if name=='c':run([out/'probe',out/'program.bin',reset_at,wait_at,wait_end],log)
            else:run(['vvp',out/'tv80.vvp','+rom='+str(out/'program.hex'),f'+reset_at={reset_at}',f'+wait_at={wait_at}',f'+wait_end={wait_end}'],log)
            pair[name]=assess(rows(out/log),reset_at)
            # A reset can truncate or suppress a write; require the complete subsequent program.
            recovered=[(w['address'],w['data']) for w in pair[name]['writes'] if w['startHalfCycle']>=2*(reset_at+16)]
            pair[name]['postResetRecovery']=recovered==EXPECTED[:6]
            if not pair[name]['postResetRecovery'] or not pair[name]['resetOutputsInactive']:raise ValueError('Reset recovery failed: '+log)
        pair['writeValuesAgree']=[(w['address'],w['data']) for w in pair['c']['writes']]==[(w['address'],w['data']) for w in pair['tv80']['writes']]
        scenarios[case]=pair
    report={'schema':1,'profiles':reports,'scenarios':scenarios,'qualified':False,
      'sourceHashes':{str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),HERE/'pin_timing.c',HERE/'pin_timing.v',ROOT/'third_party/cpu/chips/z80.h',*rtl]},
      'artifacts':{name:sha(out/name) for name in ('program.bin','program.hex',*[p.name for p in sorted(out.glob('*.txt'))])},
      'reference':{'url':'https://www.zilog.com/docs/z80/um0080.pdf','locator':'UM008011-0816, Figures 6 and 7, printed pages 9–11'},
      'requirements':['Write data precedes WR assertion and remains stable through the write pulse.','I/O control spans the automatic wait state; external WAIT extends the transaction.','Memory and I/O cycles have different control timing; do not apply a universal timestamp shift.'],
      'boundary':'C advances once per T-state; its second edge row repeats the held observation and is not independently simulated. HDL rows sample after nonblocking updates. The traces share stimulus coordinates, not an asserted equivalence of internal T-state labels. Reset reinitializes C but is a sampled pin in HDL. No nanosecond/U880 qualification follows.',
      'finding':'A shared reset during the first write yields one extra C write before reset; both recover. During external read waits C defers its I/O read assertion until WAIT releases, while TV80 holds its read active. Both default cores execute immediate and ED-prefixed I/O, memory writes/readback and reset recovery correctly. T2Write=1 clocks stale/unknown data and changes data while WR is active. Default TV80 retains different I/O assertion timing from C. The C transaction API does not expose an independent half-cycle setup/hold model.',
      'nextProof':'A physical pin adapter needs an explicit T-state/half-cycle contract for both cores, including read sampling and reset. Neither moving callbacks nor selecting T2Write=1 is a qualified correction.'}
    (out/'assessment.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Instruction values, wait extension witness, reset recovery and rejected early-write control verified; pin timing remains unqualified.')
if __name__=='__main__':main()
