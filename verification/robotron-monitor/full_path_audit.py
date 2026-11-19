#!/usr/bin/env python3
"""Audit actual historical connectivity; this is not a full-monitor simulator."""
import argparse,json,subprocess
from pathlib import Path
import lab,reference,transformer_candidates
ROOT=Path(__file__).resolve().parent
SHEETS=(('k7222-11-input.kicad_sch','012-6921',{'T200_BOUND':14}),
        ('k7222-11-sync-filter.kicad_sch','012-6931',None),
        ('k7222-11-vertical-oscillator.kicad_sch','012-6931',None),
        ('k7222-11-vertical-integrator.kicad_sch','012-6931',{'MAA723_BOUND':10}),
        ('k7222-11-vertical-output.kicad_sch','012-6931',{'P09A_EQUIV':8,'VERT_POT':3}),
        ('k7222-11-regulator5.kicad_sch','012-6931',{'REG5_POT':3}),
        ('k7222-11-power-input.kicad_sch','012-6931',None),
        ('k7222-11-converter.kicad_sch','012-6931',{'CONVERTER_TRIM':3,'TDA1060_FUNCTIONAL':16,'T1_BOUND':6}),
        ('k7222-11-horizontal-oscillator.kicad_sch','012-6921',{'HORIZONTAL_TRIM':3,'HORIZONTAL_TANK':3,'HORIZONTAL_DRIVER':4}),
        ('k7222-11-horizontal-output.kicad_sch','012-6921',{'HORIZONTAL_CHOKE':2,'HORIZONTAL_LINEARITY':2,'HORIZONTAL_COMPENSATION':2,'HORIZONTAL_BRIGHTNESS':3,'HORIZONTAL_FOCUS':3,'T3_CANDIDATE':19}),
        ('k7222-11-neck.kicad_sch','012-6891',None))


def dispositions(inventory,components):
    """Every inventory entry has a disposition; modeled does not mean qualified."""
    reference.coverage(inventory,components)
    connected={c['source_id']:c for c in components}
    result=[]
    for part in inventory['parts']:
        component=connected.get(part['id'])
        result.append(dict(source_id=part['id'],source=part['source'],
            disposition='modeled' if component else 'unresolved',
            reason=('Connected source-addressed component; device assumptions and assembly validation remain separate gates.'
                    if component else 'No connected implementation in the audited assembly.'),
            source_evidence=part['evidence'],value=part['value'],
            model=component['value'] if component else None,
            nodes=component['nodes'] if component else [],qualified=False))
    return result


def audit(output):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    inventory=json.loads((ROOT/'reference/k7222-11/inventory.json').read_text())
    requirements=ROOT/'reference/k7222-11/full-path-requirements.json'
    result=dict(format='dac-monitor-full-path-audit-v1',status='incomplete',
                full_path_render_eligible=False,full_monitor_qualified=False,
                blockers=[],hashes={},coverage=None)
    def save():(output/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    save()
    try:
        components=[]
        for filename,board,contracts in SHEETS:
            source=ROOT/'circuits'/filename;dest=output/filename;dest.write_bytes(source.read_bytes())
            result['hashes'][filename]=lab.digest(dest.read_bytes())
            xml=output/(source.stem+'.xml')
            lab.run_command(['kicad-cli','sch','export','netlist','--format','kicadxml','-o',str(xml),str(dest)],output,output/(source.stem+'.log'))
            components+=reference.source_connectivity(xml,inventory,board,contracts)
        result['coverage']=reference.coverage(inventory,components)
        result['dispositions']=dispositions(inventory,components)
        result['assembly']={'source':'reference/k7222-11/assembly.json',
                           'complete_interconnect':False,'specimen_identity':'unverified'}
        assembly=ROOT/'reference/k7222-11/assembly.json'
        result['hashes']['assembly']=lab.digest(assembly.read_bytes())
        graph=ROOT/'reference/k7222-11/t3-winding-hypothesis.json'
        candidates=transformer_candidates.enumerate_candidates(json.loads(graph.read_text()))
        result['transformer_candidates']=dict(count=len(candidates),ids=[c['id'] for c in candidates],
            status='polarity-hypotheses-only',external_assembly_connected=False,
            historical_topology_verified=False,numerically_evaluated=False)
        result['hashes']['winding_hypothesis']=lab.digest(graph.read_bytes())
        result['blockers']=json.loads(requirements.read_text())['blockers']
        result['hashes']['requirements']=lab.digest(requirements.read_bytes())
        result['hashes']['inventory']=lab.digest((ROOT/'reference/k7222-11/inventory.json').read_bytes())
        result['status']='blocked'
        result['reason']='Complete historical circuit, settled electrothermal initialization and continuous electrical replay are not implemented; optical backend tests cannot satisfy these gates.'
        save();return result
    except (ValueError,OSError,subprocess.SubprocessError) as error:
        result['failure']=str(error);save();raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=audit(args.output)
    print(json.dumps(dict(status=result['status'],connected=result['coverage']['connected'],missing=len(result['coverage']['missing']),blockers=result['blockers']),indent=2))
    raise SystemExit(2)
