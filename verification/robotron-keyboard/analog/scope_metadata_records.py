#!/usr/bin/env python3
"""Strict, lossless parser for version-one native static scope metadata records."""
import argparse
import json
import re
from pathlib import Path

SCOPE_TYPES={20,32,33,35,59,134,600}
UINT64=(1<<64)-1
UINT32=(1<<32)-1


def parse(lines):
    """Parse one complete image; preserve byte strings and ordered intern entries.

    This validates the transport and its self-contained scope references. It does
    not bind object IDs to other observers or establish their payload coverage.
    """
    rows=[]
    for line in lines:
        if not isinstance(line,str) or not line or len(line)>1048576 or '\n' in line or '\r' in line:
            raise ValueError('Invalid scope metadata line')
        row=line.split(' ')
        if any(not word for word in row):raise ValueError('Noncanonical scope metadata spacing')
        rows.append(row)
    pos=0
    def take(kind,count):
        nonlocal pos
        if pos>=len(rows) or rows[pos][0]!=kind or len(rows[pos])!=count+1:
            raise ValueError('Missing or malformed '+kind)
        row=rows[pos][1:];pos+=1;return row
    def number(word,low=0,high=UINT64):
        if not re.fullmatch(r'0|-?[1-9][0-9]*',word):raise ValueError('Noncanonical integer')
        value=int(word)
        if not low<=value<=high:raise ValueError('Integer outside native field range')
        return value
    def byte_string(kind):
        count,value=take(kind,2);count=number(count,1,524288)
        if len(value)!=count*2 or not re.fullmatch('[0-9a-f]+',value):raise ValueError('Invalid bounded name bytes')
        # Include terminator bytes even if corrupted; do not normalize as text.
        return value
    version,tick=take('VSM_BEGIN',2)
    if version!='1':raise ValueError('Unsupported scope metadata version')
    tick=number(tick);scopes=[];seen=set();object_types={}
    while pos<len(rows) and rows[pos][0]=='VSM_SCOPE':
        r=take('VSM_SCOPE',10)
        ident=number(r[0],1);parent=number(r[1]);kind=number(r[2],1,UINT32)
        if ident in seen or (parent and parent not in seen) or kind not in SCOPE_TYPES:
            raise ValueError('Invalid static scope identity, parent or family')
        seen.add(ident)
        scope=dict(id=ident,parent=parent,type=kind,file=number(r[3],0,UINT32),
            line=number(r[4],0,UINT32),definitionFile=number(r[5],0,UINT32),
            definitionLine=number(r[6],0,UINT32),cell=number(r[7],0,1),
            timeUnits=number(r[8],-128,127),timePrecision=number(r[9],-128,127),
            nameBytes=byte_string('VSM_NAME'),definitionBytes=byte_string('VSM_DEFINITION'))
        backrefs=[number(v) for v in take('VSM_TIME',3)]
        if any(v not in (0,ident) for v in backrefs):raise ValueError('Foreign scoped-time backreference')
        scope['timeReferences']=backrefs
        if kind==20:
            f=take('VSM_FUNCTION',3)
            scope['function']=dict(type=number(f[0],0,(1<<31)-1),width=number(f[1],0,UINT32),initialValue=number(f[2],0,3))
        count=number(take('VSM_INTERN',1)[0]);items=[]
        if count>len(rows)-pos:raise ValueError('Truncated internal object table')
        for _ in range(count):
            ident_word,type_word=take('VSM_OBJECT',2)
            obj=number(ident_word,1);obj_type=number(type_word,1,(1<<31)-1)
            if obj in object_types and object_types[obj]!=obj_type:raise ValueError('Object identity changed type')
            object_types[obj]=obj_type;items.append(dict(id=obj,type=obj_type))
        scope['intern']=items;scopes.append(scope)
    count=number(take('VSM_END',1)[0],1)
    if count!=len(scopes) or pos!=len(rows):raise ValueError('Incomplete image or trailing records')
    return dict(version=1,tick=tick,scopes=scopes)


def images(path):
    """Extract named native-control images; refuse truncated or duplicate blocks."""
    result={};key=None;lines=[]
    for line in Path(path).read_text().splitlines():
        if line.startswith('IMAGE '):
            if key is not None or len(line.split())!=2:raise ValueError('Overlapping image')
            key=line.split()[1]
            if key in result:raise ValueError('Duplicate image')
            lines=[]
        elif key is not None:
            lines.append(line)
            if line.startswith('VSM_END '):result[key]=parse(lines);key=None
        elif line.startswith('VSM_'):raise ValueError('Orphan metadata record')
    if key is not None or not result:raise ValueError('Missing or truncated image')
    return result


def assess(path):
    result=images(path)
    changes='units precision file line deffile defline cell name definition omit order time stime realtime'.split()
    fields=dict(zip(changes,['timeUnits','timePrecision','file','line','definitionFile','definitionLine','cell','nameBytes','definitionBytes','intern','intern','timeReferences','timeReferences','timeReferences']))
    if set(result)!={f'{kind}{i}' for i in (1,2) for kind in ['before','restored',*changes]}:raise ValueError('Incomplete native controls')
    for i in (1,2):
        before=result[f'before{i}']
        if before!=result[f'restored{i}']:raise ValueError('Metadata restoration changed')
        for kind,field in fields.items():
            after=result[f'{kind}{i}']
            if after['tick']!=before['tick'] or [s['id'] for s in after['scopes']]!=[s['id'] for s in before['scopes']]:raise ValueError('Changed time or scope population')
            differences=[(a,b) for a,b in zip(before['scopes'],after['scopes']) if a!=b]
            if len(differences)!=1:raise ValueError('Wrong number of changed scopes')
            a,b=differences[0]
            allowed={field}
            # Native name interning may alias instance and definition strings.
            if kind in ('name','definition'):allowed={'nameBytes','definitionBytes'}
            if a[field]==b[field] or any(a[k]!=b[k] for k in a if k not in allowed):raise ValueError('Changed unrelated metadata')
            if kind in ('units','precision','file','deffile') and b[field]!=a[field]+1:raise ValueError('Wrong scalar mutation')
            if kind in ('line','defline') and b[field]!=a[field]+17:raise ValueError('Wrong source-line mutation')
            if kind=='cell' and b[field]!=1-a[field]:raise ValueError('Wrong cell mutation')
            if kind in ('name','definition'):
                expected=('58' if kind=='name' else '59')+a[field][2:]
                if b[field]!=expected:raise ValueError('Wrong name mutation')
            if kind in ('time','stime','realtime'):
                expected=list(a[field]);expected[('time','stime','realtime').index(kind)]=a['id']
                if b[field]!=expected:raise ValueError('Wrong lazy time-reference mutation')
            if kind=='order' and b[field]!=[a[field][1],a[field][0],*a[field][2:]]:raise ValueError('Wrong ordering mutation')
            if kind=='omit' and (len(a[field])!=len(b[field])+1 or any(x not in a[field] for x in b[field])):raise ValueError('Invalid omission witness')
            if kind=='order' and sorted(a[field],key=lambda x:x['id'])!=sorted(b[field],key=lambda x:x['id']):raise ValueError('Ordering fault changed objects')
    return dict(qualified=False,parserControlsPassed=True,imageCount=len(result),rounds=2,
        changedFields=fields,scope='Lossless native metadata image parsing and semantic mutation/restoration review. No operational board binding, object payload coverage, function-field mutation or deletion/address reuse qualification.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('native_output',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    a.out.write_text(json.dumps(assess(a.native_output),indent=2)+'\n')
