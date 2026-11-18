#!/usr/bin/env python3
"""Prepare blank manual waveform reviews bound to one completed service score."""
import argparse
import json
from pathlib import Path

import phase_a_gates


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--service-score',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    score=json.loads(args.service_score.read_text())
    phase_a_gates.verify_service_score(score)
    template=phase_a_gates.waveform_review_template(score)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as stream:
        stream.write(json.dumps(template,indent=2)+'\n')
    print(f"Blank reviews for {len(template['points'])} test points: {args.output}")


if __name__=='__main__':main()
