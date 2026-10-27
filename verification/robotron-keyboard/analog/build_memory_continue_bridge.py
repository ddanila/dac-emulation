#!/usr/bin/env python3
"""Restore one later memory fault and resume ordinary execution to completion."""
import argparse,json
from pathlib import Path
import build_memory_late_bridge as base
from build_startup_callback_bridge import once
from ttl7406_probe import sha
PREVIOUS=base.late_header


def continue_header(header):
    header=PREVIOUS(header)
    header=once(header,'    static unsigned long long ordinal;','''    static unsigned long long ordinal;
    static int memory_fault_done;
    if(memory_fault_done)return;''')
    return once(header,'exit(names_ok&&arrays_ok&&equal&&(memory_field==0?changed_ok:rejected)?2:3);','''if(!(names_ok&&arrays_ok&&equal&&(memory_field==0?changed_ok:rejected)))exit(3);
        memory_fault_done=1;return;''')


def build(source,vpi,vpi_header,out):
    try:base.late_header=continue_header;base.build(source,vpi,vpi_header,out)
    finally:base.late_header=PREVIOUS
    p=out/'build.json';r=json.loads(p.read_text());r['sources'][str(Path(__file__).resolve())]=sha(Path(__file__))
    r['scope']='Complete startup and selected 5-us memory fault snapshots, exact restoration, then ordinary execution resumes with further observation disabled. Full waveform/firmware comparison required; no intervening private-state lifetime coverage.'
    p.write_text(json.dumps(r,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
