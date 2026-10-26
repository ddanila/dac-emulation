#!/usr/bin/env python3
"""Observe output-driven truncation and force one failed initial breakpoint."""
import argparse
import json
from pathlib import Path
import build_startup_fixes as startup
from ttl7406_probe import sha

HELPER=r'''
static int output_breakpoint(double when,double now,struct instance *ip,int recovery){
 const char *mode=getenv("ROBOTRON_OUTPUT_BREAKPOINT");
 int observe=mode&&strcmp(mode,"off");
 if(observe&&strcmp(mode,"observe")&&strcmp(mode,"fail-once")){
  fprintf(stderr,"Invalid output breakpoint probe mode\n");exit(2);
 }
 /* One fault per process; fixture must contain one d_cosim instance. */
 static int injected=0;
 int inject=observe&&!strcmp(mode,"fail-once")&&!recovery&&!injected;
 int status;
 if(inject){injected=1;status=1;}else status=cm_analog_set_temp_bkpt(when);
 if(observe)fprintf(stderr,"OUTPUT_BKPT recovery=%d time=%a vtime=%a requested=%a last=%a status=%d injected=%d\n",
  recovery,now,ip->info.vtime,when,ip->last_step,status,inject);
 return status;
}
'''


def patch(text):
    start=text.index('static int advance(struct instance *ip, ARGS)')
    end=text.index('/* Called from the main function',start)
    body=text[start:end]
    initial='if (cm_analog_set_temp_bkpt(when)) {'
    recovery='} while (cm_analog_set_temp_bkpt(when));'
    if body.count(initial)!=1 or body.count(recovery)!=1:raise ValueError('Changed output truncation branches')
    body=body.replace(initial,'if (output_breakpoint(when,TIME,ip,0)) {')
    body=body.replace(recovery,'} while (output_breakpoint(when,TIME,ip,1));')
    return text[:start]+HELPER+'\n'+body+text[end:]


def instrument(text,fixture):
    text,header=startup.instrument(text,fixture)
    return patch(text),header


def run(a):
    original=startup.staged.instrument
    try:
        startup.staged.instrument=instrument
        startup.staged.run(a)
    finally:startup.staged.instrument=original
    p=a.out/'build.json';r=json.loads(p.read_text())
    for module in (startup,startup.history):
        path=Path(module.__file__);r['sources'][str(path.resolve())]=sha(path)
    path=Path(__file__);r['sources'][str(path.resolve())]=sha(path)
    r['scope']='Opt-in output truncation observer and one artificial initial breakpoint failure per process, after HDL advancement. Single-controller fixture only. Does not qualify recovery or private HDL state.'
    p.write_text(json.dumps(r,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('base','ngspice-source','ngspice-build','vpi-include','out'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
