#!/usr/bin/env python3
"""Capture full registered-signal controls after complete port-payload review."""
import argparse,json
from pathlib import Path
from scope_signals_board_review import require_port_source
from scope_signal_fault_capture import run as capture


def run(source,assessment,bridge,icarus,out):
    require_port_source(json.loads(assessment.read_text()))
    capture(source,assessment,bridge,icarus,out,startup_only=False)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','assessment','bridge','icarus','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();run(a.source,a.assessment,a.bridge,a.icarus,a.out)
