#!/usr/bin/env python3
"""Build native teardown ASAN runtime with separate ODR indicators for VPI modules."""
import argparse,json
from pathlib import Path
import build_native_teardown_runtime as previous
from ttl7406_probe import sha

def build(archive,out,bison,jobs):
    original=previous.base.subprocess
    class Commands:
        def __getattr__(self,name):return getattr(original,name)
        def run(self,command,**kwargs):
            if command[0]=='./configure':
                for i,value in enumerate(command):
                    if value.startswith(('CFLAGS=','CXXFLAGS=')):
                        command[i]=value+' -fsanitize-address-use-odr-indicator'
            return original.run(command,**kwargs)
    try:previous.base.subprocess=Commands();previous.build(archive,out,bison,jobs)
    finally:previous.base.subprocess=original
    r=json.loads((out/'build.json').read_text());r['sources'][Path(__file__).name]=sha(Path(__file__))
    r['odrIndicators']='All compiled runtime and bundled VPI code uses separate AddressSanitizer ODR indicators. No sanitizer runtime detection option is disabled beyond inherited leak detection in execution controls.'
    (out/'build.json').write_text(json.dumps(r,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('archive','out','bison'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--jobs',type=int,default=2);a=p.parse_args();build(a.archive,a.out,a.bison,a.jobs)
