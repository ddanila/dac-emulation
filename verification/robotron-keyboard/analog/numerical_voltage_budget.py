"""Report strict convergence separately from a practical board-voltage budget."""
import math
VOLTAGE_BUDGET=.010


def voltage_gate(pairs):
    if len(pairs)!=2:raise ValueError('Two adjacent refinement comparisons required')
    a,b=pairs
    if set(a['signals'])!=set(b['signals']):raise ValueError('Different observed nodes')
    nodes={}
    for name,item in b['signals'].items():
        if item['unit']!='V':continue
        before=a['signals'][name]['maximumAbsoluteDifference']
        after=item['maximumAbsoluteDifference']
        if not all(math.isfinite(x) and x>=0 for x in (before,after)):
            raise ValueError('Invalid numerical difference')
        nodes[name]={'previousDifferenceVolts':before,'finestDifferenceVolts':after,
                     'withinBudget':after<=VOLTAGE_BUDGET,'nonIncreasing':after<=before}
    if not nodes:raise ValueError('No observed voltages')
    board={name:r for name,r in nodes.items() if name not in ('v(wr_low)','v(wr_high)')}
    return {'budgetVolts':VOLTAGE_BUDGET,'nodes':nodes,
            'passed':all(r['withinBudget'] and r['nonIncreasing'] for r in nodes.values()),
            'boardNodesWithinBudget':bool(board) and all(r['previousDifferenceVolts']<=VOLTAGE_BUDGET and r['withinBudget'] for r in board.values()),
            'fixtureControlNodes':['v(wr_low)','v(wr_high)'],
            'boundary':'The strict all-saved/nonincreasing result is preserved. The separate board budget excludes only the two behavioral DAC control voltages; it is not full-repeat or physical qualification.'}

