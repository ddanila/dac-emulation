#!/usr/bin/env python3
"""Add a selectable delayed negative control to the combined-fix observer."""
import argparse
import json
from pathlib import Path
import build_startup_fixes as startup
from ttl7406_probe import sha

DELAY = r'''
#include <errno.h>
#include <math.h>
static int history_corruption_due(double time){
 const char *s=getenv("ROBOTRON_HISTORY_CORRUPT_AFTER");
 double after=0;
 if(s){
  char *end;errno=0;after=strtod(s,&end);
  if(errno||end==s||*end||!isfinite(after)||after<0){
   fprintf(stderr,"Invalid history corruption start\n");exit(2);
  }
 }
 if(time<after)return 0;
 fprintf(stderr,"HISTORY_CORRUPTION time=%.17g after=%.17g\n",time,after);
 return 1;
}
'''


def delayed(header):
    marker = 'static void history_rejected(struct instance *ip,char *before,double time){'
    condition = 'if(history_mode()==2){'
    if header.count(marker) != 1 or header.count(condition) != 1:
        raise ValueError('Missing or ambiguous corruption hook')
    return header.replace(marker, DELAY + '\n' + marker).replace(condition,
        'if(history_mode()==2&&history_corruption_due(time)){')


def instrument(text, fixture):
    text, header = startup.instrument(text, fixture)
    return text, delayed(header)


def run(a):
    original = startup.staged.instrument
    try:
        startup.staged.instrument = instrument
        startup.staged.run(a)
    finally:
        startup.staged.instrument = original
    path = a.out / 'build.json'; receipt = json.loads(path.read_text())
    for p in (Path(__file__), Path(startup.__file__), Path(startup.history.__file__)):
        receipt['sources'][str(p.resolve())] = sha(p)
    receipt['scope'] = 'Combined startup fixes with immediate or delayed output-delay corruption at an input-barrier rejection. No wider rollback claim.'
    path.write_text(json.dumps(receipt, indent=2) + '\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('base', 'ngspice-source', 'ngspice-build', 'vpi-include', 'out'):
        p.add_argument('--' + name, type=Path, required=True)
    run(p.parse_args())
