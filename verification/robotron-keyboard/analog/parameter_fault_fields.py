"""Expected isolated board parameter mutations, independent of native injection."""
FIELDS={'parameter-word':0,'parameter-signed':1,'parameter-sized':2,'parameter-local':3,'parameter-file':4,'parameter-line':5,'parameter-name':6,'parameter-width':9,'parameter-scope':10,'parameter-name-pointer':11}


def toggle(payload,field):
    if field not in range(7):raise ValueError('Unexpected changed parameter field')
    row=next((p for p in payload['rows'] if p['kind']=='binary' and p['value']['width']>0),None)
    if row is None:raise ValueError('Missing binary parameter fault target')
    value=row['value']
    if field==0:value['words'][0][0]^=1
    elif field in (1,2):value['signed' if field==1 else 'sized']^=1
    elif field in (3,4,5):row[('local','file','line')[field-3]]^=1
    else:
        name=bytearray.fromhex(row['name']);name[0]^=1;row['name']=name.hex()
