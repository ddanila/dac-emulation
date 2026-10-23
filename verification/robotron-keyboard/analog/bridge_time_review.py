#!/usr/bin/env python3
"""Retain a logging-only bridge ordering witness; reject it as electrical acceptance."""
import argparse,json,lzma,re,shutil
from pathlib import Path
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent

def assess(root):
 reports={n:json.loads((root/n/'report.json').read_text()) for n in ('control','audit')}
 logs={n:lzma.decompress((root/n/'ngspice.log.xz').read_bytes()).decode() for n in reports}
 import hashlib
 for n,r in reports.items():
  if hashlib.sha256(logs[n].encode()).hexdigest()!=r['failureArtifacts']['ngspice.log']['sha256']:raise ValueError('Changed bridge log')
  if r['passed'] or not r.get('productionReference') or r['cpuModel']['profile']!='qualified-digital':raise ValueError('Unexpected producer scope')
  if r['error']!='Solver/HDL diagnostics: inspect ngspice.log':raise ValueError('Different producer failure')
 a,b=reports['control'],reports['audit']
 for key in ('assumptions','ngspiceRuntime','iverilog','scenarioSha256','romSha256','cpuModel'):
  if a[key]!=b[key]:raise ValueError('Unmatched bridge experiment: '+key)
 # Compare executed inputs directly; producer-only compatibility fixes may differ.
 for key in ('hdlSha256','cReferenceSources'):
  def names(r):
   result={Path(n).name:h for n,h in r[key].items()}
   if len(result)!=len(r[key]):raise ValueError('Ambiguous input filenames')
   return result
  if names(a)!=names(b):raise ValueError('Executed sources differ: '+key)
 decks=[]
 for n,r in reports.items():
  deck=(root/n/'io.cir').read_text()
  if sha(root/n/'io.cir')!=r['deckSha256']:raise ValueError('Changed deck')
  for name,lib in r['bridge']['libraries'].items():deck=deck.replace(lib['path'],'BRIDGE_'+name)
  decks.append(deck)
 if decks[0]!=decks[1]:raise ValueError('Circuit/stimulus differs')
 producer_changes={n:[h,b['sources'].get(n)] for n,h in a['sources'].items() if b['sources'].get(n)!=h}
 same={n:a['failureArtifacts'][n]['sha256']==b['failureArtifacts'][n]['sha256'] for n in ('trace.txt','bus-trace.txt')}
 if not all(same.values()):raise ValueError('Logging changed waveforms')
 errors={n:re.findall(r'Error: time reversal \(([^)]+)\) in Icarus Shim VPI!',log) for n,log in logs.items()}
 if not errors['control'] or errors['control']!=errors['audit']:raise ValueError('Diagnostic mismatch')
 requests=[dict(zip(('target','actual','base','tick','pending'),map(float,m))) for m in re.findall(r'TIME_AUDIT advance target=(\S+) actual=(\S+) base=(\S+) tick=(\S+) pending=(\S+)',logs['audit'])]
 violations=[dict(r,backwardSeconds=r['actual']-r['target']) for r in requests if r['target']+r['tick']<r['actual']]
 if not violations:raise ValueError('No directly witnessed ordering violation')
 return {'completed':True,'qualified':False,'cpuProfile':'qualified-digital','productionReference':True,
         'producerSourceDifferences':producer_changes,'executedSourcesAndCircuitMatch':True,'loggingOnlyWaveformsIdentical':same,'diagnostics':errors['control'],'orderingViolations':violations,
         'reports':{n:sha(root/n/'report.json') for n in reports},
         'sources':{n:sha(HERE/n) for n in ('bridge_time_review.py','build_bridge_time_audit.py')},
         'boundary':'The bridge was asked to advance to a target earlier than its actual HDL time by more than one HDL tick. The audit leaves both captured waveforms byte-identical. These rejected service captures do not qualify firmware transport, voltage margins or the closed board; they isolate a simulator ordering failure, not a specimen defect.'}

def main():
 p=argparse.ArgumentParser();p.add_argument('--control',type=Path);p.add_argument('--audit',type=Path);p.add_argument('--bridge-source',type=Path);p.add_argument('--rebuilt-bridge',type=Path);p.add_argument('--out',type=Path,required=True);p.add_argument('--verify',action='store_true');a=p.parse_args()
 if a.verify:
  manifest=json.loads((a.out/'manifest.json').read_text())
  for n,h in manifest.items():
   if sha(a.out/n)!=h:raise ValueError('Changed bridge evidence: '+n)
  if assess(a.out)!=json.loads((a.out/'assessment.json').read_text()):raise ValueError('Changed assessment')
 else:
  if not all((a.control,a.audit,a.bridge_source,a.rebuilt_bridge)):p.error('Retention needs both runs and bridge sources')
  if sha(a.bridge_source/'vpi.c')!=sha(a.rebuilt_bridge/'vpi.c'):raise ValueError('Audit builder does not reproduce executed source')
  a.out.mkdir(parents=True,exist_ok=False)
  for name,src in [('control',a.control),('audit',a.audit)]:
   dest=a.out/name;dest.mkdir();r=json.loads((src/'report.json').read_text())
   for n,c in r['failureArtifacts'].items():
    if c['status']=='retained' and sha(src/n)!=c['sha256']:raise ValueError('Producer capture changed')
   for n in ('report.json','run-inputs.json','io.cir','controller_analog.v','reference.log'):shutil.copyfile(src/n,dest/n)
   with (src/'ngspice.log').open('rb') as source,lzma.open(dest/'ngspice.log.xz','wb',preset=3) as target:shutil.copyfileobj(source,target)
  shutil.copyfile(a.bridge_source/'vpi.c',a.out/'audit-vpi.c')
  shutil.copyfile(a.rebuilt_bridge/'bridge.json',a.out/'rebuilt-bridge.json')
  (a.out/'assessment.json').write_text(json.dumps(assess(a.out),indent=2)+'\n')
  (a.out/'manifest.json').write_text(json.dumps({str(p.relative_to(a.out)):sha(p) for p in sorted(a.out.rglob('*')) if p.is_file() and p.name!='manifest.json'},indent=2)+'\n')
 print('Bridge ordering witness verified; electrical acceptance remains false.')
if __name__=='__main__':main()
