#!/usr/bin/env python3
"""Capture full scope metadata controls only after complete typed-signal review."""
import argparse,json
from pathlib import Path
from scope_metadata_board_review import require_typed_source
from scope_metadata_fault_capture import run as capture


def run(source,assessment,bridge,icarus,out):
    require_typed_source(json.loads(assessment.read_text()))
    capture(source,assessment,bridge,icarus,out,startup_only=False)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','assessment','bridge','icarus','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();run(a.source,a.assessment,a.bridge,a.icarus,a.out)
