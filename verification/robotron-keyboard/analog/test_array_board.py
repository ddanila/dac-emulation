import copy
import unittest
from pathlib import Path
from array_board_review import ArrayState
from array_probe import parse,target
from build_array_bridge import array_header,HERE
ROOT=HERE/'reports/array-compact'


class ArrayBoard(unittest.TestCase):
    def snapshots(self):
        lines=(ROOT/'enabled.stdout').read_text().splitlines();result=[]
        for i,line in enumerate(lines):
            if line=='VAM_BEFORE':
                end=next(j for j in range(i+1,len(lines)) if lines[j].startswith('VAR_END '))
                array=parse(lines[i+1:end+1])
                result.append(dict(arrays=array,threads=dict(tick=array['tick']),scopes=[dict(pointer=p) for p in {a['scope'] for a in array['arrays']}],prior='unchanged'))
        return result
    def tracker(self):return ArrayState((ROOT/'probe.vvp').read_text())
    def test_native_trajectory_and_coverage(self):
        tracker=self.tracker()
        for state in self.snapshots():tracker.observe(state)
        result=tracker.result(False)
        self.assertTrue(result['loadedArrayStateObserved'])
        self.assertTrue(result['wordHandleCacheObserved'])
        self.assertGreater(result['readPortsWithAddressChanges'],0)
    def test_owner_and_storage_changes_rejected(self):
        first=self.snapshots()[0];tracker=self.tracker();tracker.observe(first)
        bad=copy.deepcopy(first);bad['scopes']=[]
        with self.assertRaises(ValueError):tracker.observe(bad)
        bad=copy.deepcopy(first);bad['arrays']['arrays'][0]['storage']+=1
        with self.assertRaises(ValueError):tracker.observe(bad)
    def test_fault_and_unrelated_state(self):
        before=self.snapshots()[0];tracker=self.tracker();tracker.observe(before)
        after=copy.deepcopy(before);index=target(before['arrays'],2);after['arrays']['ports'][index]['next']=0
        tracker.changed(before,after,'link')
        after['prior']='changed'
        with self.assertRaises(ValueError):tracker.changed(before,after,'link')
    def test_bridge_preserves_layers_and_restoration(self):
        header=array_header((HERE/'fixtures/display_board_bridge.h').read_text())
        for name in ('ports','output','start','assignment','primitive','island','filter','thread','wait','code','scope','operand','array'):
            self.assertIn('robotron_'+name+'_inventory(f, ctx)',header)
        start=header.index('    int array_field=')
        restore=header.index('robotron_array_fault(ctx,array_field)!=1)exit(3)',start)
        self.assertLess(restore,header.index('int detected=',restore))
        self.assertIn('array_field==2 ? robotron_start_phase==1 : info->vtime>=5e-6',header)


if __name__=='__main__':unittest.main()
