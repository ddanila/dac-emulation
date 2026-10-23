#!/usr/bin/env python3
import math
import json
import hashlib
import tempfile
from pathlib import Path
from complete_network_review import review
from fixture_crossing_grid import add_crossings
from test_network_refinement import BASE
import unittest
from numerical_voltage_budget import voltage_gate

class AcceptanceTest(unittest.TestCase):
    def pair(self,values):
        return {'signals':{n:{'unit':'V','maximumAbsoluteDifference':v} for n,v in values.items()}}
    def test_all_nodes_and_nonincreasing_requirement(self):
        a=self.pair({'data':.008,'supply':.001});b=self.pair({'data':.004,'supply':.002})
        self.assertFalse(voltage_gate([a,b])['passed'])
        b['signals']['supply']['maximumAbsoluteDifference']=.0005
        self.assertTrue(voltage_gate([a,b])['passed'])
        b['signals']['data']['maximumAbsoluteDifference']=.011
        self.assertFalse(voltage_gate([a,b])['passed'])
    def test_missing_and_invalid_nodes_rejected(self):
        a=self.pair({'data':.008})
        for value in (math.nan,math.inf,-.001):
            with self.assertRaises(ValueError):voltage_gate([a,self.pair({'data':value})])
        with self.assertRaises(ValueError):voltage_gate([a,self.pair({'supply':.001})])
    def test_complete_interval_and_saved_node_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            dirs=[]
            for i,(step,scale) in enumerate([(25,1),(12.5,.5)]):
                p=Path(tmp)/str(i);p.mkdir();dirs.append(p)
                deck=add_crossings(BASE,1/(2**i)).replace('1160000n','20n').replace('25n',str(step)+'n')
                for key,value in [('reltol',1e-6),('vntol',1e-9),('abstol',1e-15)]:
                    import re
                    deck=re.sub(key+r'=[0-9.eE+-]+',key+'='+str(value*scale),deck)
                deck=deck.replace('wrdata witness.txt v(n_D1)','wrdata witness.txt v(n_D1)\nwrdata network_witness.txt v(n_D1)')
                (p/'io.cir').write_text(deck)
                receipt=dict(timedOut=False,exitCode=0,solverDiagnostic=None,networkTrace=True,conservativeCap=True,passiveAssembly=True,observationSignals=['v(n_D1)'],runtime={},inputs={},sourceDeckSha256='fixture',mpfrTransitionBits='256',mpfrStartNs=0,method='trap',enabled=False,matrixBoundarySubstitution=False,stepNs=step,toleranceScale=scale,deckSha256=hashlib.sha256(deck.encode()).hexdigest())
                (p/'run.json').write_text(json.dumps(receipt))
                (p/'network_witness.txt').write_text('time v(n_D1)\n0 0\n1e-8 1\n2e-8 0\n')
                (p/'ngspice.log').write_text('BUS_EDGE_PS 4123\nBUS_SAMPLE 4000 0000 af 0 1 0\nBUS_LATCH 4000 af af\n')
            self.assertTrue(review(dirs,2e-8)['completed'])
            with self.assertRaises(ValueError):review(dirs,3e-8)
            p=dirs[1];deck=(p/'io.cir').read_text().replace('.save v(n_D1)','.save v(n_D1) v(n_D2)');(p/'io.cir').write_text(deck)
            r=json.loads((p/'run.json').read_text());r['deckSha256']=hashlib.sha256(deck.encode()).hexdigest();(p/'run.json').write_text(json.dumps(r))
            with self.assertRaisesRegex(ValueError,'Saved observations excluded'):review(dirs,2e-8)

    def test_fixture_diagnostic_cannot_hide_board_failure(self):
        a=self.pair({'v(wr_high)':.12,'v(n_WR_N)':.0001})
        b=self.pair({'v(wr_high)':.10,'v(n_WR_N)':.00001})
        result=voltage_gate([a,b])
        self.assertFalse(result['passed']);self.assertTrue(result['boardNodesWithinBudget'])
        b['signals']['v(n_WR_N)']['maximumAbsoluteDifference']=.011
        self.assertFalse(voltage_gate([a,b])['boardNodesWithinBudget'])

if __name__=='__main__':unittest.main()
