#!/usr/bin/env python3
"""Rebuild only d_cosim in a fingerprinted ngspice 47 digital code-model library."""
import argparse,json,os,platform,shutil,subprocess,tempfile
from pathlib import Path
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for key in ('ngspice-source','ngspice-build','spinit','out'):p.add_argument('--'+key,type=Path,required=True)
 p.add_argument('--control',action='store_true');a=p.parse_args()
 source=a.ngspice_source.resolve();build=a.ngspice_build.resolve();out=a.out.resolve()
 original=(source/'src/xspice/icm/digital/d_cosim/cfunc.mod').read_text()
 original=original.replace('if (TIME < ip->info.vtime) {','if (TIME <= ip->info.vtime) {')
 if original!=(HERE/'fixtures/ngspice-47/d_cosim.mod').read_text():raise ValueError('Expected pinned ngspice 47 d_cosim source')
 out.mkdir(parents=True,exist_ok=False)
 model=out/'src/xspice/icm/digital/d_cosim';model.mkdir(parents=True)
 (model/'cfunc.mod').write_text(original)
 shutil.copyfile(source/'src/xspice/icm/digital/d_cosim/ifspec.ifs',model/'ifspec.ifs')
 patches=['ngspice-47-strict-time-diagnostic.patch']+([] if a.control else ['cosim-input-barrier.patch'])
 for patch in patches:subprocess.run(['patch','-d',str(out),'-p1','-i',str(HERE/'engine-patches'/patch)],check=True)
 cmpp=build/'src/xspice/cmpp/cmpp'
 subprocess.run([str(cmpp),'-mod'],env=dict(os.environ,CMPP_IDIR=str(model),CMPP_ODIR=str(out)),check=True)
 subprocess.run(['cc','-O2','-fPIC','-I'+str(build/'src/include'),'-I'+str(source/'src/include'),'-c',str(out/'cfunc.c'),'-o',str(out/'cfunc.o')],check=True)
 icm=build/'src/xspice/icm'
 objects=sorted(x for x in (icm/'digital').rglob('*.o') if x!=icm/'digital/d_cosim/cfunc.o')
 if not objects or not any(x.name=='dlmain.o' for x in objects):raise ValueError('Missing built digital code models')
 objects += [icm/x for x in ('dstring.o','tline_common.o','msline_common.o')]
 flags=['-bundle','-flat_namespace','-undefined','suppress'] if platform.system()=='Darwin' else ['-shared']
 subprocess.run(['cc',*flags,*map(str,objects),str(out/'cfunc.o'),'-lm','-o',str(out/'digital.cm')],check=True)
 init=a.spinit.read_text();lines=init.splitlines();matches=[i for i,s in enumerate(lines) if s.strip().startswith('codemodel ') and s.strip().endswith('/digital.cm')]
 if len(matches)!=1:raise ValueError('Expected one literal digital.cm initialization')
 lines[matches[0]]='codemodel '+str(out/'digital.cm');(out/'spinit').write_text('\n'.join(lines)+'\n')
 report={'control':a.control,'sourceVersion':'ngspice-47','builderSha256':sha(Path(__file__)),
 'patches':{n:sha(HERE/'engine-patches'/n) for n in patches},
 'upstreamFixtureSha256':sha(HERE/'fixtures/ngspice-47/d_cosim.mod'),
 'preprocessor':{'path':str(cmpp),'sha256':sha(cmpp)},
 'compiler':subprocess.check_output(['cc','--version'],text=True).splitlines()[0],
 'reusedObjects':{str(x):sha(x) for x in objects},
 'outputs':{n:sha(out/n) for n in ('cfunc.c','cfunc.o','digital.cm','spinit')},
 'scope':'Input-boundary scheduling experiment. Other digital objects are reused unchanged; analog models and solver executable are selected separately by the capture runtime receipt.'}
 (out/'build.json').write_text(json.dumps(report,indent=2)+'\n');print(out/'build.json')
if __name__=='__main__':main()
