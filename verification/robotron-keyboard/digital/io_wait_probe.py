#!/usr/bin/env python3
"""Independent Figure-7 half-edge WAIT witnesses; old candidates are controls."""
import argparse,json,subprocess
from pathlib import Path
from qualify import ROOT,sha
from c_read_candidate import generate
from c_read_instructions import programs
from io_wait_candidate import c_generate,hdl_generate,core_generate
HERE=Path(__file__).resolve().parent

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,default=ROOT/'build/keyboard-controller-io-wait');a=ap.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
 def run(cmd):return subprocess.check_output(list(map(str,cmd)),text=True,timeout=30)
 run(['python3',HERE/'c_read_sampling.py','--out',out/'sampling'])
 vendor=ROOT/'third_party/cpu/tv80';sources=[p for p in sorted(vendor.glob('*.v')) if p.name!='tv80n.v']+[out/'sampling/tv80n_falling.v']
 for profile in ('old','candidate'):
  folder=out/profile;folder.mkdir(exist_ok=True)
  (folder/'candidate.h').write_text(generate((ROOT/'third_party/cpu/chips/z80.h').read_text()))
  c=(HERE/'c_read_half.h').read_text();h=(HERE/'tv80_io_candidate.v').read_text()
  (folder/'c_read_half.h').write_text(c if profile=='old' else c_generate(c))
  (folder/'tv80_io_candidate.v').write_text(h if profile=='old' else hdl_generate(h))
  run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-I',folder,HERE/'io_wait_probe.c','-o',folder/'probe'])
  core=(vendor/'tv80_core.v').read_text()
  (folder/'tv80_core.v').write_text(core if profile=='old' else core_generate(core))
  rtl=[p for p in sources if p.name!='tv80_core.v']+[folder/'tv80_core.v']
  run(['iverilog','-g2012','-s','probe','-o',folder/'probe.vvp',*rtl,folder/'tv80_io_candidate.v',HERE/'io_wait_probe.v'])
 results=[]
 for name,program in programs().items():
  if name=='indexed-memory' or name.startswith(('out','ot')):continue
  (out/'program.bin').write_bytes(program)
  (out/'program.hex').write_text('\n'.join(f'{x:02x}' for x in program)+'\n')
  for start,stop in [(1,2),(1,3),(1,4),(2,3),(2,4),(3,4),(3,5),(4,5),(4,6),(5,6),(1,8),(6,9)]:
   # First sample is automatic Tw falling (offset 3); each accepted WAIT adds 2 half-edges.
   sample=3
   while start<=sample<stop:sample+=2
   expected=sample+2
   row={'instruction':name,'start':start,'stop':stop,'expectedWidth':expected}
   for profile in ('old','candidate'):
    for lang in ('c','hdl'):
     folder=out/profile
     cmd=[folder/'probe',start,stop,out/'program.bin'] if lang=='c' else ['vvp',folder/'probe.vvp',f'+start={start}',f'+stop={stop}','+rom='+str(out/'program.hex')]
     log=run(cmd);(folder/f'{name}-{lang}-{start}-{stop}.txt').write_text(log)
     vals={f[0]:int(f[1]) for l in log.splitlines() if (f:=l.split()) and f[0] in ('WIDTH','RELEASE','HALT','A')}
     row[profile+'-'+lang]={'width':vals.get('RELEASE',vals.get('WIDTH')),'halt':vals['HALT'],'data':vals['A']}
   results.append(row)
 report={'reference':'https://www.zilog.com/docs/z80/um0080.pdf','locator':'Figure 7 and printed pages 7, 10–11','scope':'Immediate, ED and block reads, including ignored DD/FD prefixes; stable and between-edge WAIT transitions. First-read pulse and completion checked. Does not qualify writes, reset, memory or interrupts.',
 'passed':all(r[k]['width']==r['expectedWidth'] and r[k]['halt']==1 for r in results for k in ('candidate-c','candidate-hdl')),
 'negativeControls':{k:any(r[k]['width']!=r['expectedWidth'] for r in results) for k in ('old-c','old-hdl')},'cases':results,
 'sources':{str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),HERE/'io_wait_candidate.py',HERE/'io_wait_probe.c',HERE/'c_read_instructions.py',HERE/'io_wait_probe.v',HERE/'c_read_half.h',HERE/'c_read_candidate.py',HERE/'tv80_io_candidate.v',HERE/'io_flags_candidate.py',HERE/'c_read_sampling.py',HERE/'c_read_half_test.c',ROOT/'third_party/cpu/chips/z80.h',*sorted(vendor.glob('*.v'))]},
 'artifacts':{str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.suffix in ('.txt','.h','.v')}}
 (out/'assessment.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:v for k,v in report.items() if k in ('passed','negativeControls','cases')},indent=2))
 if not report['passed'] or not all(report['negativeControls'].values()):raise SystemExit(1)
if __name__=='__main__':main()
