"""Diff the independent page-16 pin list against a fresh neck-board KiCad export."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'reference/k7222-11/page16-neck-source-netlist.json'
ASSEMBLY=ROOT/'reference/k7222-11/assembly.json'
SHEET=ROOT/'circuits/k7222-11-neck.kicad_sch'

# These are spelling translations, not inferred connections. The left-hand
# topology was transcribed from the scanned page before this comparison.
NET_NAMES={
    '41P':'p41','OO':'0','VID':'vid','VID_AFTER_R6':'clamp',
    'V1_BASE':'base','V1_COLLECTOR':'collector','SUK_DRIVE':'brightness',
    'SUK':'cathode','FEEDBACK':'tail','IS':'intens',
    'HEATER_10_7P':'p10_7','UG1_INPUT':'ug1','SUG1':'g1',
    'UG2_INPUT':'ug2','SUG2':'g2','UG4_INPUT':'ug4','SUG4':'g4',
}
PIN_NUMBER={'1':'1','2':'2','+':'1','-':'2','A':'1','K':'2',
            'C':'1','B':'2','E':'3'}


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compare(source,assembly,xml,*,source_pdf_sha256,sheet_sha256):
    if source.get('format')!='dac-monitor-independent-source-netlist-v1':
        raise ValueError('unsupported independent source netlist')
    if source['source']['pdf_sha256']!=source_pdf_sha256 or source['source']['page']!=16:
        raise ValueError('wrong scanned schematic source')
    nets=source['nets']
    if set(nets)!=set(NET_NAMES):raise ValueError('unmapped source net')
    expected_parts={};expected_connectors={}
    for source_net,terminals in nets.items():
        model_net=NET_NAMES[source_net]
        for terminal in terminals:
            part,pin=terminal.rsplit(':',1)
            if part in ('X1','X2','X3'):
                expected_connectors.setdefault(part,{})[pin]=model_net
            else:
                key=('012-6891:'+part,PIN_NUMBER[pin])
                if key in expected_parts:raise ValueError('duplicate source terminal: '+terminal)
                expected_parts[key]=model_net
    if expected_connectors!=assembly.get('neck_connectors'):
        raise ValueError('source connector pins differ from assembly map')
    for diode in source['diode_directions']:
        part='012-6891:'+diode['section']
        if (expected_parts[(part,'1')]!=NET_NAMES[diode['anode_net']]
                or expected_parts[(part,'2')]!=NET_NAMES[diode['cathode_net']]):
            raise ValueError('source diode direction conflicts with its netlist')
    transistor=source['transistor'];part='012-6891:'+transistor['part']
    for pin,key in (('1','collector_net'),('2','base_net'),('3','emitter_net')):
        if expected_parts[(part,pin)]!=NET_NAMES[transistor[key]]:
            raise ValueError('source transistor pins conflict with its netlist')
    cap=source['capacitor_polarity'];part='012-6891:'+cap['part']
    if (expected_parts[(part,'1')]!=NET_NAMES[cap['positive_net']]
            or expected_parts[(part,'2')]!=NET_NAMES[cap['negative_net']]):
        raise ValueError('source electrolytic polarity conflicts with its netlist')
    tree=ET.parse(xml);root=tree.getroot()
    refs={};connector_refs={};seen_source_ids=set()
    for comp in root.findall('./components/comp'):
        source_id=next((p.get('value') for p in comp.findall('property')
                        if p.get('name')=='SourceId'),None)
        if source_id is None or source_id in seen_source_ids:
            raise ValueError('missing or duplicate KiCad SourceId')
        seen_source_ids.add(source_id)
        refs[comp.get('ref')]=source_id
        if source_id in ('012-6891:X1','012-6891:X2','012-6891:X3'):
            connector_refs[comp.get('ref')]=source_id.split(':')[-1]
    if set(connector_refs.values())!={'X1','X2','X3'}:
        raise ValueError('KiCad export lacks physical neck connector pins')
    actual={};actual_connectors={name:{} for name in connector_refs.values()}
    for net in root.findall('./nets/net'):
        model_net=net.get('name').lstrip('/')
        for node in net.findall('node'):
            ref=node.get('ref');pin=node.get('pin')
            if ref in connector_refs:
                name=connector_refs[ref]
                if pin in actual_connectors[name]:raise ValueError('KiCad connector pin occurs twice')
                actual_connectors[name][pin]=model_net
                continue
            key=(refs[ref],pin)
            if key in actual:raise ValueError('KiCad terminal occurs on two nets')
            actual[key]=model_net
    missing=[dict(source_id=part,pin=pin,expected_net=net,actual_net=actual.get((part,pin)))
             for (part,pin),net in sorted(expected_parts.items()) if actual.get((part,pin))!=net]
    extra=[dict(source_id=part,pin=pin,actual_net=net)
           for (part,pin),net in sorted(actual.items()) if (part,pin) not in expected_parts]
    connector_misses=[dict(connector=name,pin=pin,expected_net=net,
                           actual_net=actual_connectors.get(name,{}).get(pin))
                      for name,pins in sorted(expected_connectors.items())
                      for pin,net in sorted(pins.items(),key=lambda item:int(item[0]))
                      if actual_connectors.get(name,{}).get(pin)!=net]
    connector_extras=[dict(connector=name,pin=pin,actual_net=net)
                      for name,pins in sorted(actual_connectors.items())
                      for pin,net in sorted(pins.items(),key=lambda item:int(item[0]))
                      if pin not in expected_connectors.get(name,{})]
    return dict(format='dac-monitor-page16-neck-comparison-v1',
        qualification='independent source component and physical connector pins compared with fresh KiCad export',
        source_netlist_sha256=sha(SOURCE),source_pdf_sha256=source_pdf_sha256,
        sheet_sha256=sheet_sha256,assembly_sha256=sha(ASSEMBLY),
        source_nets=len(nets),source_component_pins=len(expected_parts),
        source_connector_pins=sum(map(len,expected_connectors.values())),
        matched_component_pins=len(expected_parts)-len(missing),
        matched_connector_pins=sum(map(len,expected_connectors.values()))-len(connector_misses),
        diode_directions_checked=len(source['diode_directions']),
        connector_pin_map_matches=not connector_misses and not connector_extras,
        missing_or_changed_pins=missing,extra_kicad_pins=extra,
        missing_or_changed_connector_pins=connector_misses,
        extra_kicad_connector_pins=connector_extras,
        passed=not missing and not extra and not connector_misses and not connector_extras)


def run(source_pdf):
    source_pdf=Path(source_pdf)
    source=json.loads(SOURCE.read_text());assembly=json.loads(ASSEMBLY.read_text())
    if sha(source_pdf)!=source['source']['pdf_sha256']:
        raise ValueError('source PDF differs from independent reading')
    with tempfile.TemporaryDirectory() as directory:
        xml=Path(directory)/'neck.xml'
        subprocess.run(['kicad-cli','sch','export','netlist','--format','kicadxml',
                        '-o',str(xml),str(SHEET)],check=True,capture_output=True,text=True)
        return compare(source,assembly,xml,source_pdf_sha256=sha(source_pdf),
                       sheet_sha256=sha(SHEET))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-pdf',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();report=run(args.source_pdf)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(f"{report['matched_component_pins']}/{report['source_component_pins']} component pins match")
    return 0 if report['passed'] else 2


if __name__=='__main__':raise SystemExit(main())
