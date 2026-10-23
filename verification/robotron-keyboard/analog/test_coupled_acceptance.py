import contextlib,io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import coupled_acceptance as suite

class AcceptanceTests(unittest.TestCase):
 def test_failed_reused_pair_blocks_later_runs_and_never_qualifies(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);rom=root/'rom';rom.write_bytes(b'reference fixture')
   bridge=root/'bridge.json';bridge.write_text(json.dumps({'libraries':{}}))
   runtime={'identity':'fixture'};dirs=[]
   for name,step in [('coarse',50),('fine',25)]:
    folder=root/name;folder.mkdir();dirs.append(folder)
    r={'passed':False,'error':'voltage gate','assumptions':{'cpuProfile':'qualified-digital','stepNs':step,'electricalBus':True,'busLatchPf':5,'bus7406Pf':5},'ngspiceRuntime':runtime,'bridge':{'libraries':{}},'romSha256':suite.sha(rom),'scenarioSha256':suite.sha(suite.HERE/'scenarios/single-press.json')}
    (folder/'report.json').write_text(json.dumps(r))
   args=['suite','--rom',str(rom),'--bridge',str(bridge),'--ngspice','fixture','--spinit',str(root/'spinit'),'--out',str(root/'result'),'--reuse-single-press',*map(str,dirs)]
   with patch('sys.argv',args),patch.object(suite,'identify',return_value=(runtime,{})),patch.object(suite,'verify'),patch.object(suite.subprocess,'run') as execute,contextlib.redirect_stdout(io.StringIO()):
    with self.assertRaises(SystemExit) as error:suite.main()
    self.assertEqual(error.exception.code,1);execute.assert_not_called()
   result=json.loads((root/'result/assessment.json').read_text())
   self.assertFalse(result['qualified']);self.assertFalse(result['servicePassed'])
   self.assertEqual(result['jobs'][0]['status'],'failed')
   self.assertTrue(all(j['status']=='blocked-by-service-prerequisite' for j in result['jobs'][1:]))
   self.assertEqual(result['closedBoardAcceptance']['status'],'not-run')
   # A prior capture from another runtime cannot be silently reused.
   with patch('sys.argv',args),patch.object(suite,'identify',return_value=({'identity':'different'},{})),patch.object(suite,'verify'):
    with self.assertRaisesRegex(ValueError,'runtime differs'):suite.main()
if __name__=='__main__':unittest.main()
