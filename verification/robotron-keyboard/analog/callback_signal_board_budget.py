#!/usr/bin/env python3
"""Replay actual board callback-owner/signal linkage and full-preflight cost."""
import argparse,json
from pathlib import Path
import signal_handle_board_budget as previous
from callback_signal_links import parse,validate
from signal_handles import parse as signal_parse
from callback_list_probe import parse as list_parse
from net_probe import parse as graph_parse
HERE=Path(__file__).resolve().parent


def review(root):
    bindings=previous.review(root)
    # The diagnostic substitutes linkage scans for the inherited timing loop.
    # Do not publish those measurements as standalone handle-inventory cost.
    timings=bindings.pop('scanTimings');projection=bindings.pop('initialStateProjection')
    text=(root/'links-before.txt').read_text()
    if text!=(root/'links-after.txt').read_text():raise ValueError('Callback link observation changed state')
    state=dict(links=parse(text.splitlines()),signals=signal_parse((root/'handles-before.txt').read_text().splitlines()),lists=list_parse((root/'callbacks-before.txt').read_text().splitlines()),graph=graph_parse((root/'handle-graph.txt').read_text().splitlines()))
    count=validate(state)
    if state['links']['tick'] or count!=bindings['priorCallbackBindings']['initializedBridgeCallbacks']:raise ValueError('Incomplete initialized board links')
    calls=projection['normalSnapshotCalls'];size=len(text.encode())
    return dict(qualified=False,controlsPassed=True,initializedBindings=bindings,callbackSignalLinks=count,linkImageBytes=size,
                linkScanTimings=timings,
                initialStateProjection=dict(normalSnapshotCalls=calls,handleAndLinkLogicalBytes=calls*(bindings['imageBytes']+size),linkScanSeconds=calls*timings['meanSeconds'],excludesAdditionalHandleSerializationOtherObserversAndGrowth=True),
                scope='Actual compiled keyboard bridge callback objects, admitted signal handles, node allocations, adjusted callback-owner pointers and filter addresses agree across independent complete native inventories. Link scan cost includes full callback-list and signal-handle preflight. Diagnostics end before the first coroutine advance; operational growth, total combined cost and integration remain unqualified.')


def run(source,bridge,icarus,out):
    previous.run(source,bridge,icarus,out)
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','bridge','icarus','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();run(a.source,a.bridge,a.icarus,a.out)
