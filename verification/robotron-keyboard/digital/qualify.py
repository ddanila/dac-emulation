#!/usr/bin/env python3
"""Independent-CPU scenario and raw-cycle qualification; never align away timing."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

BOARD=Path(__file__).resolve().parents[1]
ROOT=BOARD.parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(args,**kw):subprocess.run([str(x) for x in args],check=True,cwd=ROOT,**kw)
def scenarios():
    # Each contact is tested individually, including unused physical matrix positions.
    cases=[]
    for col in range(13):
        events=[]
        for row in range(8):
            t=200000+row*200000
            events.extend([[t,'key',col,row,1],[t+100000,'release']])
        cases.append({'id':f'column-{col:02d}','cycles':1900000,'events':events,'scope':'All eight contact positions, press and release; no assumption every contact is a populated key.'})
    cases.extend([
      {'id':'chords-modifiers','cycles':1800000,'events':[[200000,'key',7,5,1],[400000,'key',7,4,1],[600000,'key',8,1,1],[800000,'key',8,0,1],[1000000,'key',7,5,0],[1200000,'key',8,1,0],[1400000,'release']],'scope':'Two overlapping ordinary contacts and modifier transitions while held.'},
      {'id':'reset-transmit','cycles':800000,'events':[[200000,'key',7,5,1],[223600,'reset'],[400000,'key',7,5,1],[600000,'release']],'scope':'Fixed shared reset instant inside the baseline serial burst; verify its location from each CPU trace.'},
    ])
    quiet=json.loads(json.dumps(cases[-1]));quiet['id']='reset-between-edges';quiet['events'][1][0]=223590;quiet['scope']='Reset between serial edges, paired with the fixed near-edge reset case.';cases.append(quiet)
    return cases

def replace_block(text,start,end,replacement):
    if text.count(start)!=1 or text.count(end)!=1:raise ValueError('Fixture template changed')
    a=text.index(start);b=text.index(end,a)
    return text[:a]+replacement+text[b:]
def fixtures(case):
    c=(BOARD/'firmware_probe.c').read_text();v=(BOARD/'firmware_tb.v').read_text()
    cycles=case['cycles'];ce=[];ve=[];reset=[]
    for event in case['events']:
        t,op,*args=event
        if op=='key':
            col,row,down=args;ce.append(f'if(cycle=={t})robotron_keyboard_key(&k,{col},{row},{down});');ve.append(f'{t}:contacts[{col*8+row}]={down};')
        elif op=='release':ce.append(f'if(cycle=={t})robotron_keyboard_release(&k);');ve.append(f'{t}:contacts=0;')
        elif op=='reset':
            reset.append(t);ce.append(f'if(cycle=={t})robotron_keyboard_init(&k,rom,NULL,bit);');ve.extend([f'{t}:begin reset_n=0;contacts=0;end',f'{t+16}:reset_n=1;'])
        else:raise ValueError('Unknown stimulus')
    gate=' && '.join(f'(cycle<{t} || cycle>={t+16})' for t in reset) or '1'
    c=replace_block(c,'  if(cycle==200000)','  if(k.leds!=old_leds)', '\n'.join(ce)+f'\n  if({gate})dac_z80_tick(&k.cpu,0,0);\n')
    c=c.replace(' return 0;', ' printf("DONE %u\\n",cycle);\n return 0;')
    c=c.replace('cycle<4600000',f'cycle<{cycles}').replace('../../machines/robotron1715m/keyboard.h',str(ROOT/'machines/robotron1715m/keyboard.h'))
    # Record actual I/O and write assertion edges, not sampled LED display persistence.
    c=c.replace('static unsigned cycle;','static unsigned cycle;\nstatic unsigned previous_bus;')
    c=c.replace('  if(k.leds!=old_leds)', '''  unsigned bus=(!!(k.cpu.pins & Z80_IORQ)) | ((!!(k.cpu.pins & Z80_WR))<<1) | ((!!(k.cpu.pins & Z80_RD))<<2);
  if((bus&3) && bus!=previous_bus)printf("BUS %u %u %u %u\\n",cycle,bus,Z80_GET_ADDR(k.cpu.pins),Z80_GET_DATA(k.cpu.pins));
  previous_bus=bus;
  if(k.leds!=old_leds)''')
    v=replace_block(v,'  case(cycle)','  if(cycle>=0', '  case(cycle)\n'+ '\n'.join(ve)+'\n  endcase\n')
    v=v.replace('if(cycle==4600000)$finish;', 'if(cycle==4600000)begin $display("DONE %0d",cycle);$finish;end').replace('4600000',str(cycles))
    v=v.replace(' always @(leds)', ''' reg [2:0] previous_bus=0;
 wire [2:0] observed_bus={!rd_n,!wr_n,!iorq_n};
 always @(negedge clk) begin
  #1;
  if(reset_n && cycle>=0 && observed_bus[1:0]!=0 && observed_bus!==previous_bus)
   $display("BUS %0d %0d %0d %0d",cycle,observed_bus,address,wr_n?di:dout);
  previous_bus=observed_bus;
 end
 always @(leds)''')
    return c,v

def parse(path):
    result={k:[] for k in ('BIT','EDGE','LED','BUS')}
    for line in path.read_text().splitlines():
        fields=line.split()
        if fields and fields[0] in result:result[fields[0]].append(fields[1:])
    return result

def compare(c,h):
    report={}
    for kind in c:
        left,right=c[kind],h[kind]
        # Every missing event or unknown value remains a mismatch.
        values=bool(left) and [x[1:] for x in left]==[x[1:] for x in right]
        if not left and not right:values=True
        first=next(({'ordinal':i,'c':a,'hdl':b} for i,(a,b) in enumerate(zip(left,right)) if a!=b),None)
        if first is None and len(left)!=len(right):first={'ordinal':min(len(left),len(right)),'c':left[min(len(left),len(right)):] [:1],'hdl':right[min(len(left),len(right)):] [:1]}
        offsets={}
        for a,b in zip(left,right):
            offset=str(int(b[0])-int(a[0]));offsets[offset]=offsets.get(offset,0)+1
        report[kind]={'cCount':len(left),'hdlCount':len(right),'valuesEquivalent':values,'rawCycleEquivalent':left==right,'offsetCounts':offsets,'firstDifference':first}
    return report

def assess(case,c,h):
    comparison=compare(c,h)
    bursts={}
    for lang,events in [('c',c),('hdl',h)]:
        bursts[lang]=[]
        for event in case['events']:
            t,op,*args=event
            if op=='key' and args[-1]==1:
                end=next((e[0] for e in case['events'] if e[0]>t),case['cycles'])
                bursts[lang].append({'contact':args[:2],'start':t,'end':end,'bits':sum(t<=int(e[0])<end for e in events['BIT'])})
    reset=[]
    for event in case['events']:
        if event[1]!='reset':continue
        t=event[0];witness={}
        for lang,events in [('c',c),('hdl',h)]:
            before=[int(x[0]) for x in events['BIT'] if int(x[0])<t]
            witness[lang]={'precedingBits':len(before),'lastBitCycle':before[-1] if before else None,'partial26BitFrame':bool(before) and len(before)%26!=0,'postResetBits':sum(int(x[0])>=t+16 for x in events['BIT'])}
        reset.append(witness)
    return {'scenario':case,'events':comparison,'contactWindows':bursts,'resetWitnesses':reset,
            'functionalAgreement':all(comparison[k]['valuesEquivalent'] for k in ('BIT','EDGE','LED')),
            'rawCycleAgreement':all(comparison[k]['rawCycleEquivalent'] for k in ('BIT','EDGE','LED')),
            'scope':'Fixture cycle coordinates retained without shifting. BUS edges are diagnostics, not a qualified U880 timing reference.'}

def main():
    p=argparse.ArgumentParser();p.add_argument('--rom',type=Path,required=True);p.add_argument('--out',type=Path,default=ROOT/'build/keyboard-controller-digital');p.add_argument('--case',action='append');a=p.parse_args()
    rom=a.rom.resolve();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
    if len(rom.read_bytes())!=2048:raise ValueError('Expected S600-sized ROM')
    cases=[s for s in scenarios() if not a.case or s['id'] in a.case]
    if not cases or a.case and set(a.case)!={s['id'] for s in cases}:raise ValueError('Unknown scenario')
    (out/'assessment.json').unlink(missing_ok=True)
    sources=[Path(__file__).resolve(),BOARD/'firmware_probe.c',BOARD/'firmware_tb.v',BOARD/'chips.v',BOARD/'generated/controller.v',ROOT/'machines/robotron1715m/keyboard.c',ROOT/'machines/robotron1715m/keyboard.h',ROOT/'common/cpu/z80.c',ROOT/'common/cpu/z80.h',ROOT/'third_party/cpu/chips/z80.h',*sorted((ROOT/'third_party/cpu/tv80').glob('*.v'))]
    results=[]
    for case in cases:
        dest=out/case['id'];dest.mkdir(exist_ok=True);c,v=fixtures(case)
        (dest/'probe.c').write_text(c);(dest/'bench.v').write_text(v)
        (dest/'rom.hex').write_text('\n'.join(f'{v:02x}' for v in rom.read_bytes())+'\n')
        run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror',dest/'probe.c',ROOT/'machines/robotron1715m/keyboard.c',ROOT/'common/cpu/z80.c','-o',dest/'probe'])
        run(['iverilog','-g2012','-s','firmware_tb','-o',dest/'bench.vvp',*sorted((ROOT/'third_party/cpu/tv80').glob('*.v')),BOARD/'chips.v',BOARD/'generated/controller.v',dest/'bench.v'])
        with (dest/'c.txt').open('w') as f:run([dest/'probe',rom],stdout=f,timeout=120)
        with (dest/'hdl.txt').open('w') as f:run(['vvp',dest/'bench.vvp','+rom='+str(dest/'rom.hex')],stdout=f,timeout=300)
        for name in ('c.txt','hdl.txt'):
            if f"DONE {case['cycles']}" not in (dest/name).read_text().splitlines():raise ValueError('Incomplete scenario '+name)
        result=assess(case,parse(dest/'c.txt'),parse(dest/'hdl.txt'));result['artifacts']={name:sha(dest/name) for name in ('c.txt','hdl.txt','probe.c','bench.v')}
        (dest/'assessment.json').write_text(json.dumps(result,indent=2)+'\n');results.append(result)
        print(case['id'], 'functional=',result['functionalAgreement'],'cycle=',result['rawCycleAgreement'],flush=True)
    report={'schema':1,'romSha256':sha(rom),'sources':{str(p.relative_to(ROOT)):sha(p) for p in sources},'cases':results,'functionalAgreement':all(r['functionalAgreement'] for r in results),'rawCycleAgreement':all(r['rawCycleAgreement'] for r in results),'allScenariosRun':len(cases)==len(scenarios()),'electricallyQualified':False,'specimenQualified':False}
    (out/'assessment.json').write_text(json.dumps(report,indent=2)+'\n')
    return 0 if report['functionalAgreement'] else 1
if __name__=='__main__':raise SystemExit(main())
