#!/usr/bin/env python3
"""Observe startup and the first before-step boundary at or after five microseconds."""
import argparse,json
from pathlib import Path
import build_memory_fault_bridge as base
from build_startup_callback_bridge import once
from ttl7406_probe import sha
PREVIOUS=base.fault_header


def late_header(header):
    header=PREVIOUS(header)
    header=once(header,'    static unsigned long long ordinal;','')
    marker='    struct ng_vvp *ctx = (struct ng_vvp*)info->handle;'
    # The serial counts every hook, including omitted intermediate observations.
    header=once(header,marker,'''    static unsigned long long ordinal;
    if(strncmp(mode,"memory-",7))exit(3);
    if(ordinal && (info->vtime<5e-6 || strcmp(phase,"before-step"))){++ordinal;return;}
'''+marker)
    return once(header,'if(memory_field>=0 && robotron_start_phase==1){','if(memory_field>=0 && info->vtime>=5e-6){')


def build(source,vpi,vpi_header,out):
    try:base.fault_header=late_header;base.build(source,vpi,vpi_header,out)
    finally:base.fault_header=PREVIOUS
    p=out/'build.json';r=json.loads(p.read_text());r['sources'][str(Path(__file__).resolve())]=sha(Path(__file__))
    r['scope']='Two selected complete observations: paused startup and first before-step hook at or after 5 us. Intermediate hooks increment the native boundary serial without observing. Five memory modes restore before termination. No complete trajectory or waveform qualification.'
    p.write_text(json.dumps(r,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
