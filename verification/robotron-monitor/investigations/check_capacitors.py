"""Reproduce the neck-C1 check; does not test full-monitor symptoms."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import reference,atlas_features,faults
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--matrix',action='store_true',help='Check all 15 separate/joint C-loss and ESR-increase cases for neck C1')
args=parser.parse_args()
root=args.output
root.mkdir(exist_ok=False)
profile_path=reference.ROOT/'profiles/k7222-11-neck-diagnostic.json'
profile=reference.read_profile(profile_path)
cat=json.loads((reference.ROOT/'atlas/catalogue.json').read_text())
scenario=json.loads((reference.ROOT/'atlas/scenarios.json').read_text())['scenarios'][0]
cases={'nominal':None}|{f['id']:f for f in cat['faults'] if f['id'] in ['bypass-loss','bypass-esr']}
if args.matrix:
    cases={'nominal':None}|{f['id']:f for f in faults.capacitor_matrix('012-6891:C1')}
results={}
for name,fault in cases.items():
    variants=[]
    for tag,step in [('base',2e-8),('refined',1e-8)]:
        out=root/name/tag
        report=reference.run(profile_path,out,step=step,fault=fault,scenario=scenario)
        rows=reference.read_samples(out/'samples.txt',profile['probes'],0,.0004,step)
        signature=atlas_features.extract(rows,profile['probes'],scenario['feature_windows'])
        # Entire recording after the first 25 us; includes switching edges.
        transient=atlas_features.extract(rows,profile['probes'],[dict(id='including-transitions',start=25e-6,stop=.0004)])
        variants.append((signature,transient))
    results[name]={'fault':fault,'settled_features':variants[1][0],
                   'transition_inclusive_features':variants[1][1],
                   'settled_refinement':atlas_features.refinement(variants[0][0],variants[1][0]),
                   'transition_inclusive_refinement':atlas_features.refinement(variants[0][1],variants[1][1]),
                   'model_hashes':report['hashes']}
    print(name,'settled/refinement:',results[name]['settled_refinement']['passed'],results[name]['transition_inclusive_refinement']['passed'],flush=True)
result={'format':'dac-monitor-capacitor-check-v1','model_id':profile['id'],
        'scope':'Neck C1 only; power/horizontal capacitors are unmodeled.',
        'conditions':'0–400 us, nominal external bench supplies and constant tube load. Not thermal warm-up.',
        'can_predict':{'eht':False,'width':False,'height':False,'screen_brightness':False,'thermal_warmup':False},
        'cases':results}
(root/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
(root/'check_capacitors.py').write_text(Path(__file__).read_text())
