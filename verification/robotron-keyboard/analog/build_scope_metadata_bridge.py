#!/usr/bin/env python3
"""Add dense scope metadata checks and compact log output to combined observation."""
import argparse,json
from pathlib import Path
import build_typed_signal_fault_bridge as base
from build_startup_callback_bridge import once
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
PREVIOUS_HEADER=base.fault_header


def metadata_header(header):
    header=PREVIOUS_HEADER(header)
    header=once(header,'robotron_typed_signal_inventory(f, ctx) || fprintf(f, "VA_END\\n")','robotron_typed_signal_inventory(f, ctx) || robotron_scope_metadata_inventory(f, ctx) || fprintf(f, "VA_END\\n")')
    header=header.replace('fprintf(stderr,','robotron_metadata_log(stderr,')
    helper=(HERE/'fixtures/scope_metadata_log.h').read_text()
    return helper+'\n'+header


def build(source,vpi,vpi_header,out):
    try:
        base.fault_header=metadata_header;base.build(source,vpi,vpi_header,out)
    finally:base.fault_header=PREVIOUS_HEADER
    p=out/'build.json';r=json.loads(p.read_text())
    for f in (Path(__file__).resolve(),HERE/'fixtures/scope_metadata_log.h'):r['sources'][str(f)]=sha(f)
    r['scope']='Combined typed signal and prior observers plus dense scope metadata/reference snapshots. Native byte comparisons stay dense; complete logged metadata bodies use exact previous-image encoding. Startup fault and operational qualification are separate.'
    p.write_text(json.dumps(r,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
