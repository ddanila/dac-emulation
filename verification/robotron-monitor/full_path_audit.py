#!/usr/bin/env python3
"""Audit actual historical connectivity; this is not a full-monitor simulator."""
import argparse,json,subprocess
from pathlib import Path
import lab,reference
ROOT=Path(__file__).resolve().parent
SHEETS=(('k7222-11-input.kicad_sch','012-6921',{'T200_BOUND':14}),
        ('k7222-11-sync-filter.kicad_sch','012-6931',None),
        ('k7222-11-vertical-oscillator.kicad_sch','012-6931',None),
        ('k7222-11-neck.kicad_sch','012-6891',None))


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
        result['blockers']=json.loads(requirements.read_text())['blockers']
        result['hashes']['requirements']=lab.digest(requirements.read_bytes())
        result['hashes']['inventory']=lab.digest((ROOT/'reference/k7222-11/inventory.json').read_bytes())
        result['status']='blocked'
        result['reason']='Complete historical circuit and validated electrical/thermal continuation are not implemented; optical backend tests cannot satisfy these gates.'
        save();return result
    except (ValueError,OSError,subprocess.SubprocessError) as error:
        result['failure']=str(error);save();raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=audit(args.output)
    print(json.dumps(dict(status=result['status'],connected=result['coverage']['connected'],missing=len(result['coverage']['missing']),blockers=result['blockers']),indent=2))
    raise SystemExit(2)
