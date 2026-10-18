"""Run from the core root after both recorded-supply engine runs complete."""
from pathlib import Path
import hashlib,json,sys
sys.path.insert(0,'verification/robotron-keyboard/analog')
from clock_convergence import compare_clocks
from xyce_oscillator_probe import model_for_xyce
BASE=Path('build/keyboard-controller-analog')
LEFT=BASE/'clock-full-precision-supply-replay'
RIGHT=BASE/'xyce-recorded-supply'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
a=json.loads((LEFT/'assessment.json').read_text());b=json.loads((RIGHT/'assessment.json').read_text())
assert a['completed'] and b['completed']
assert a['connectivitySha256']==b['connectivitySha256']
assert a['supply']['fileSha256']==b['supply']['fileSha256']
assert a['supply']['sourceUncompressedSha256']==b['supply']['sourceUncompressedSha256']
result={'qualified':False,'inputAssessments':{'ngspice':sha(LEFT/'assessment.json'),'xyce':sha(RIGHT/'assessment.json')},'sourceScriptSha256':sha(Path(__file__)),'supplyFileSha256':a['supply']['fileSha256'],'comparisons':{},'boundary':'Same canonical isolated oscillator, nominal CPU load, printed supply samples and gate equations. Source scheduling and solver tolerance semantics differ. No phase alignment, no physical startup or full-board qualification.'}
for i,label in enumerate(['coarse','fine']):
 assert a['runs'][i]['stepNs']==b['runs'][i]['stepNs']
 step=a['runs'][i]['stepNs']
 original=LEFT/label/'ls_nand_pullup.cir';adapted=RIGHT/label/'model.cir'
 assert sha(original)==a['runs'][i]['gateModelSha256']
 assert sha(adapted)==b['runs'][i]['modelSha256']
 assert model_for_xyce(original.read_text())==adapted.read_text()
 assert sha(LEFT/label/'trace.txt')==a['runs'][i]['traceSha256']
 assert sha(RIGHT/label/'trace.txt')==b['runs'][i]['normalizedTraceSha256']
 result['comparisons'][label]=compare_clocks(LEFT/label/'trace.txt',RIGHT/label/'trace.txt',step,step,columns=3)
(BASE/'xyce-supply-comparison/assessment.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:{x:v[x] for x in ['passed','maximumBracketDifferenceNs','firstDifference']} for k,v in result['comparisons'].items()},indent=2))
