#!/usr/bin/env python3
"""Build fingerprinted opt-in DAC corner, ADC crossing and logging experiments."""
import argparse,json,os,platform,subprocess,tarfile
from pathlib import Path
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
ARCHIVE='894e649651f1838a14095e5a5439e7d3aa63e87ede14d283173fda4fcdef675f'
def main():
 p=argparse.ArgumentParser(description=__doc__)
 for key in ('archive','ngspice-source','ngspice-build','spinit','out'):p.add_argument('--'+key,type=Path,required=True)
 p.add_argument('--dac-anchored',action='store_true');p.add_argument('--dac-state-audit',action='store_true');p.add_argument('--adc-crossings',action='store_true');p.add_argument('--audit',action='store_true');a=p.parse_args()
 if sha(a.archive)!=ARCHIVE:raise ValueError('Expected pinned ngspice 47 archive')
 out=a.out.resolve();out.mkdir(parents=True,exist_ok=False);source=a.ngspice_source.resolve();build=a.ngspice_build.resolve()
 names=('d_cosim','dac_bridge','adc_bridge')
 with tarfile.open(a.archive) as archive:
  for name in names:
   folder=out/'src/xspice/icm/digital'/name;folder.mkdir(parents=True)
   for f in ('cfunc.mod','ifspec.ifs'):
    member='ngspice-47/src/xspice/icm/digital/'+name+'/'+f
    (folder/f).write_bytes(archive.extractfile(member).read())
 patches=['ngspice-47-strict-time-diagnostic.patch','cosim-input-barrier.patch','dac-ramp-breakpoint.patch']
 if a.dac_anchored:
  patches.append('dac-anchored-ramp.patch')
  (out/'src/xspice/icm/digital/dac_bridge/dac_anchor.h').write_bytes((HERE/'engine-patches/dac_anchor.h').read_bytes())
 if a.dac_state_audit:patches.append('dac-state-audit.patch')
 if a.audit:patches.append('live-event-audit.patch')
 if a.adc_crossings:patches.append('adc-crossing-breakpoint.patch')
 for patch in patches:subprocess.run(['patch','-d',str(out),'-p1','-i',str(HERE/'engine-patches'/patch)],check=True,capture_output=True)
 objects=[];cmpp=build/'src/xspice/cmpp/cmpp'
 for name in names:
  folder=out/'src/xspice/icm/digital'/name
  subprocess.run([str(cmpp),'-mod'],env=dict(os.environ,CMPP_IDIR=str(folder),CMPP_ODIR=str(folder)),check=True)
  obj=folder/'cfunc.o';subprocess.run(['cc','-O2','-fPIC','-I'+str(build/'src/include'),'-I'+str(source/'src/include'),'-c',str(folder/'cfunc.c'),'-o',str(obj)],check=True);objects.append(obj)
 icm=build/'src/xspice/icm';excluded={icm/'digital'/n/'cfunc.o' for n in names}
 reused=sorted(x for x in (icm/'digital').rglob('*.o') if x not in excluded)+[icm/n for n in ('dstring.o','tline_common.o','msline_common.o')]
 if not any(x.name=='dlmain.o' for x in reused):raise ValueError('Missing digital library objects')
 flags=['-bundle','-flat_namespace','-undefined','suppress'] if platform.system()=='Darwin' else ['-shared']
 subprocess.run(['cc',*flags,*map(str,reused+objects),'-lm','-o',str(out/'digital.cm')],check=True)
 lines=a.spinit.read_text().splitlines();indices=[i for i,l in enumerate(lines) if l.startswith('codemodel ') and l.endswith('/digital.cm')]
 if len(indices)!=1:raise ValueError('Expected one explicit digital library')
 lines[indices[0]]='codemodel '+str(out/'digital.cm');(out/'spinit').write_text('\n'.join(lines)+'\n')
 report={'archiveSha256':ARCHIVE,'builderSha256':sha(Path(__file__)),'patches':{n:sha(HERE/'engine-patches'/n) for n in patches},'dacAnchorHeaderSha256':sha(HERE/'engine-patches/dac_anchor.h') if a.dac_anchored else None,'reusedObjects':{str(x):sha(x) for x in reused},'preprocessorSha256':sha(cmpp),'compiler':subprocess.check_output(['cc','--version'],text=True).splitlines()[0],'outputs':{n:sha(out/n) for n in ('digital.cm','spinit')},'environment':'ROBOTRON_DAC_BREAKPOINTS enables single-bit corner scheduling; ROBOTRON_LIVE_EVENTS enables logs. ROBOTRON_ADC_CROSSINGS enables rollback crossing localization; ROBOTRON_ADC_TRACE logs state changes. ROBOTRON_DAC_STATE_AUDIT logs wr_high evaluator state through 12 ns when compiled with --dac-state-audit. ROBOTRON_DAC_ANCHORED enables event-anchored single-bit arithmetic when built with --dac-anchored. All default off. Diagnostic only.'}
 (out/'build.json').write_text(json.dumps(report,indent=2)+'\n');print(out/'build.json')
if __name__=='__main__':main()
