#!/usr/bin/env python3
"""Build an opt-in output-history initializer with controlled allocation seeds."""
import argparse
import json
from pathlib import Path
import build_live_state_audit as builder
from ttl7406_probe import sha

BLOCK=r'''
        /* cm_event_alloc grows the state block with realloc for tag 1.
         * Seed modes are fault controls, never normal simulation defaults. */
        {
            const char *seed=getenv("ROBOTRON_HISTORY_SEED");
            const char *enabled=getenv("ROBOTRON_HISTORY_INIT");
            int initialize=enabled && !strcmp(enabled,"on");
            if (enabled && strcmp(enabled,"off") && !initialize) {
                fprintf(stderr,"Invalid output-history initializer mode\n");exit(2);
            }
            if (seed && strcmp(seed,"zero") && strcmp(seed,"one")) {
                fprintf(stderr,"Invalid output-history allocation seed\n");exit(2);
            }
            if (seed || initialize) {
                Digital_t *history=cm_event_get_ptr(1,0);
                if (seed) {
                    for (i=0;i<outs+inouts;i++) {
                        history[i].state=!strcmp(seed,"one")?ONE:ZERO;
                        history[i].strength=STRONG;
                    }
                }
                if (initialize) {
                    for (i=0;i<outs;i++)history[i]=*(Digital_t *)OUTPUT(d_out[i]);
                    for (i=0;i<inouts;i++)history[outs+i]=*(Digital_t *)OUTPUT(d_inout[i]);
                }
                fprintf(stderr,"HISTORY_INIT seed=%s initialized=%d ports=%u\n",seed?seed:"none",initialize,outs+inouts);
            }
        }
'''


def instrument(text, fixture):
    marker='        cm_event_alloc(1, (int)((outs + inouts) * sizeof (Digital_t)));'
    if text.count(marker)!=1:raise ValueError('Missing history allocation')
    return text.replace(marker,marker+'\n'+BLOCK),''


def run(a):
    original=builder.instrument
    try:builder.instrument=instrument;builder.run(a)
    finally:builder.instrument=original
    path=a.out/'build.json';receipt=json.loads(path.read_text())
    receipt['sources'][str(Path(__file__).resolve())]=sha(Path(__file__))
    receipt['scope']='Opt-in initialization of current output history from initialized output ports. Allocation seeds are independent fault controls. No full-board or general rollback qualification.'
    path.write_text(json.dumps(receipt,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('base','ngspice-source','ngspice-build','vpi-include','out'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
