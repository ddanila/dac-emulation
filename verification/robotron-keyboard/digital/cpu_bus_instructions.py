#!/usr/bin/env python3
"""Production backend instruction/flags, live input, WAIT and reset acceptance."""
import argparse
import json
import subprocess
from pathlib import Path
from c_read_instructions import programs, parse
from cpu_bus_candidate import generate
from qualify import ROOT, sha
HERE=Path(__file__).resolve().parent

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,default=ROOT/'build/keyboard-controller-cpu-bus-instructions');a=ap.parse_args()
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
    def run(cmd):return subprocess.check_output(list(map(str,cmd)),text=True,timeout=30)
    run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror',HERE/'cpu_bus_instructions.c',ROOT/'machines/robotron1715m/keyboard_cpu.c','-o',out/'probe'])
    rtl=generate(out/'rtl')
    bench=(HERE/'c_read_instructions.v').read_text().replace('tv80_io_candidate cpu(', 'cpu_bus_candidate cpu(').replace('cpu.base.', 'cpu.qualified.base.')
    (out/'bench.v').write_text(bench)
    for late in (0,1):run(['iverilog','-g2012','-DTV80_REFRESH','-s','c_read_instructions',f'-Pc_read_instructions.LATE={late}','-o',out/f'bench-{late}.vvp',*rtl,out/'bench.v'])
    results=[]
    for name,program in programs().items():
        for late in (0,1):
            if late and (name=='indexed-memory' or name.startswith(('out','ot'))):continue
            for wait,reset in ((0,0),(1,0),(0,1)):
                label=f'{name}-{late}-{wait}-{reset}';folder=out/label;folder.mkdir(exist_ok=True)
                (folder/'program.bin').write_bytes(program);(folder/'program.hex').write_text('\n'.join(f'{x:02x}' for x in program)+'\n')
                (folder/'c.txt').write_text(run([out/'probe',folder/'program.bin',wait,reset,late]))
                (folder/'hdl.txt').write_text(run(['vvp',out/f'bench-{late}.vvp','+rom='+str(folder/'program.hex'),f'+mode={wait}',f'+reset={reset}']))
                c,h=parse(folder/'c.txt'),parse(folder/'hdl.txt')
                passed=c['RAM']==h['RAM'] and [v[1:] for v in c['OUT']]==[v[1:] for v in h['OUT']] and c['FINAL'][-1][:2]==h['AF'][-1] and c['FINAL'][-1][-1]==1 and h['HALT']==[[1]]
                if late:passed=passed and bool(c['LATE'])
                results.append({'id':label,'passed':bool(passed),'cAF':c['FINAL'][-1][:2],'hdlAF':h['AF'][-1]})
    sources=[Path(__file__),HERE/'cpu_bus_instructions.c',HERE/'c_read_instructions.py',HERE/'c_read_instructions.v',ROOT/'machines/robotron1715m/keyboard_cpu.c',ROOT/'machines/robotron1715m/keyboard_cpu.h',*sorted((ROOT/'machines/robotron1715m/generated/keyboard_cpu').glob('*.h'))]
    report={'passed':all(r['passed'] for r in results),'productionBackendTested':True,'cases':results,'sources':{str(p.relative_to(ROOT)):sha(p) for p in sources},'artifacts':{str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.suffix in ('.txt','.bin','.hex','.v')}}
    (out/'assessment.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'passed':report['passed'],'failures':[r for r in results if not r['passed']]},indent=2))
    if not report['passed']:raise SystemExit(1)
if __name__=='__main__':main()
