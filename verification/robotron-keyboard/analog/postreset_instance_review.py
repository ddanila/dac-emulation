#!/usr/bin/env python3
"""Extend complete post-reset controls to instance queues and rollback anchors."""
import argparse
import json
import importlib.util
from pathlib import Path
from instance_queue_review import external_fault, inventory, runtime_summary
from postreset_state_review import assess as state_assess
from ttl7406_probe import sha


def cached_state_reviewer():
    # Give this invocation its own module globals. The historical reviewer and
    # its pinned bytes remain unchanged; no process-wide monkey patch is used.
    from cached_circuit_output_review import inventory_fast
    spec = importlib.util.spec_from_file_location(
        '_cached_postreset_state_review', Path(__file__).with_name('postreset_state_review.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.inventory = inventory_fast
    return module.assess


def assess(root, source, baseline, *, cached_output=False):
    review = cached_state_reviewer() if cached_output else state_assess
    result=review(root,source,baseline,fault_review=external_fault,summary_review=runtime_summary)
    result['instanceQueues']=inventory(root/'check/ngspice.log')
    if not result['instanceQueues']['externalPendingEventObservations']:
        raise ValueError('No actual external pending instance events observed')
    result['scope']='Complete 1.16-ms post-reset observer controls for output and instance queues, worklists and rollback anchors. Negative controls rewind an external instance current slot; delayed injection follows 1.1 ms and firmware execution.'
    result['reviewSources']={n:sha(Path(__file__).with_name(n)) for n in
        ('postreset_instance_review.py','postreset_state_review.py','instance_queue_review.py')}
    if cached_output:
        result['reviewSources']['cached_circuit_output_review.py']=sha(Path(__file__).with_name('cached_circuit_output_review.py'))
    result['notEstablished']=['Private HDL events and freed instance storage','Full-repeat qualification',
                              'Startup and supply recovery','Numerical convergence','Device admission']
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('root','source','baseline','out'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--cached-output-inventory', action='store_true', help='Use validated bounded port caching; all other complete checks are unchanged')
    a=p.parse_args();result=assess(a.root,a.source,a.baseline,cached_output=a.cached_output_inventory)
    with a.out.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
