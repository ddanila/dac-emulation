#!/usr/bin/env python3
"""Build an opt-in fix preserving changed outputs across repeated publication."""
import argparse
import json
from pathlib import Path
import build_event_state_audit as observer
from ttl7406_probe import sha
BASE_INSTRUMENT=observer.instrument
ENABLE=r'''
static int staged_output_enabled(void){
 const char *s=getenv("ROBOTRON_STAGED_OUTPUT");
 if(!s||!strcmp(s,"off"))return 0;
 if(!strcmp(s,"on"))return 1;
 fprintf(stderr,"Invalid staged-output mode\n");exit(2);
}
'''


def patch(text):
    start=text.index('static void output(');end=text.index('/* Run the co-simulation.',start)
    body=text[start:end]
    for port in ('d_out','d_inout'):
        old='''        } else {
            OUTPUT_CHANGED('''+port+'''[i]) = FALSE;
        }'''
        new=old.replace('} else {','} else if (!staged_output_enabled()) {')
        if body.count(old)!=1:raise ValueError('Missing output flag clear')
        body=body.replace(old,new)
    text=text[:start]+ENABLE+'\n'+body+text[end:]
    marker='    /* Check for pending output. */'
    reset='''    /* Start a new callback staging window. Later output() calls accumulate
     * changed flags; the engine queues final values only after we return. */
    if (staged_output_enabled()) {
        for (i=0;i<ip->out_ports;i++)OUTPUT_CHANGED(d_out[i])=FALSE;
        for (i=0;i<ip->inout_ports;i++)OUTPUT_CHANGED(d_inout[i])=FALSE;
    }
'''
    if text.count(marker)!=1:raise ValueError('Missing callback staging boundary')
    return text.replace(marker,reset+'\n'+marker)


def instrument(text,fixture):return BASE_INSTRUMENT(patch(text),fixture)


def run(a):
    original=observer.history.instrument
    try:
        observer.history.instrument=instrument
        observer.history.run(a)
    finally:observer.history.instrument=original
    path=a.out/'build.json';r=json.loads(path.read_text())
    for p in (Path(__file__),Path(observer.__file__)):r['sources'][str(p.resolve())]=sha(p)
    r['scope']='Opt-in accumulation of changed flags across output() calls within one initialized callback, with the existing scheduling observer. No full-board qualification.'
    path.write_text(json.dumps(r,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('base','ngspice-source','ngspice-build','vpi-include','out'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
