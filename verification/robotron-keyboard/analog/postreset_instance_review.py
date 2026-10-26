#!/usr/bin/env python3
"""Extend complete post-reset controls to instance queues and rollback anchors."""
import argparse
import json
from pathlib import Path
from instance_queue_review import external_fault, inventory, runtime_summary
from postreset_state_review import assess as state_assess
from ttl7406_probe import sha


def assess(root, source, baseline):
    result=state_assess(root,source,baseline,fault_review=external_fault,summary_review=runtime_summary)
    result['instanceQueues']=inventory(root/'check/ngspice.log')
    if not result['instanceQueues']['externalPendingEventObservations']:
        raise ValueError('No actual external pending instance events observed')
    result['scope']='Complete 1.16-ms post-reset observer controls for output and instance queues, worklists and rollback anchors. Negative controls rewind an external instance current slot; delayed injection follows 1.1 ms and firmware execution.'
    result['reviewSources']={n:sha(Path(__file__).with_name(n)) for n in
        ('postreset_instance_review.py','postreset_state_review.py','instance_queue_review.py')}
    result['notEstablished']=['Private HDL events and freed instance storage','Full-repeat qualification',
                              'Startup and supply recovery','Numerical convergence','Device admission']
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('root','source','baseline','out'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();result=assess(a.root,a.source,a.baseline)
    with a.out.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
