#!/usr/bin/env python3
"""Review actual initialized board parameter faults and complete restorations."""
import argparse,copy,json
from pathlib import Path
import parameter_board_budget as previous
from parameter_payload import parse
from scope_metadata_records import parse as metadata_parse
from scope_metadata_bindings import reference_parse


def review(root):
    prior=previous.review(root);raw=(root/'parameters-before.txt').read_bytes();before=parse(raw.decode().splitlines())
    if before['tick']!=0 or len(before['rows'])!=56 or any(r['kind']!='binary' or not 0<r['value']['width']<=r['value']['wordBits'] for r in before['rows']):raise ValueError('Changed board parameter profile')
    metadata=metadata_parse((root/'metadata-before.txt').read_text().splitlines());reference=reference_parse((root/'metadata-references-before.txt').read_text().splitlines());compiled=(root/'io.vvp').read_text()
    events=[];files=set()
    for round in (1,2):
        for field in range(16):
            name=f'parameter-restored-{round}-{field}.txt';files.add(name)
            if (root/name).read_bytes()!=raw:raise ValueError('Parameter restoration differs')
            applicable=field<=6 or 9<=field<=11
            events.append(f'{"CHANGED" if field<=6 else "REFUSED" if applicable else "ABSENT"} {round} {field}')
            if field>6:continue
            expected=copy.deepcopy(before);row=expected['rows'][0];value=row['value']
            if field==0:value['words'][0][0]^=1
            elif field in (1,2):value['signed' if field==1 else 'sized']^=1
            elif field in (3,4,5):row[('local','file','line')[field-3]]^=1
            else:
                namebytes=bytearray.fromhex(row['name']);namebytes[0]^=1;row['name']=namebytes.hex()
            name=f'parameter-changed-{round}-{field}.txt';files.add(name);changed=parse((root/name).read_text().splitlines())
            if changed!=expected:raise ValueError('Wrong isolated board parameter fault')
            try:previous.bindings(changed,metadata,reference,compiled)
            except ValueError:pass
            else:raise ValueError('Compiled binding accepted altered parameter')
    if (root/'parameter-faults.txt').read_text().splitlines()!=events:raise ValueError('Incomplete parameter fault events')
    if {p.name for pattern in ('parameter-changed-*.txt','parameter-restored-*.txt') for p in root.glob(pattern)}!=files:raise ValueError('Unexpected parameter fault images')
    return dict(qualified=False,controlsPassed=True,initialBoardBindings=prior,rounds=2,changedFields=['binaryWord','signed','sized','local','file','line','nameBytes'],refusedFields=['binaryWidth','scopePointer','namePointer'],absentFields=['realBytes','stringBytes','wideAPointer','wideBPointer','stringPointer','stringLength'],exactRestorations=20,unchangedAbsentControls=12,compiledBindingRejections=14,
        scope='Two rounds on the actual initialized keyboard population: seven exact isolated changes reject independent compiled bindings, three invalid fields refuse before output, and six absent-family controls return unavailable without changing the complete parameter image. All 56 parameters restore byte-for-byte at tick zero. Does not execute HDL continuation or qualify operational transient faults, unsupported subclasses or lifecycle changes.')


def run(source,bridge,icarus,out):
    previous.run(source,bridge,icarus,out)
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','bridge','icarus','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();run(a.source,a.bridge,a.icarus,a.out)
