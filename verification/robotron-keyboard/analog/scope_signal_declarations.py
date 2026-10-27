#!/usr/bin/env python3
"""Match all observed scope vector signal metadata to compiled declarations."""
import argparse,json,re
from pathlib import Path
from scope_metadata_bindings import parse as joined_parse
from scope_signals_board_budget import review as budget_review
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


def compiled_signals(text):
    quoted=r'"(?:\\.|[^"\\])*"';scopes={};current=None;rows={};hidden=0
    for raw in text.splitlines():
        line=raw.strip()
        if re.match(r'^\S+\s+\.scope\s',line):
            m=re.fullmatch(r'(\S+)\s+\.scope\s+[^,]+,\s*('+quoted+r')\s+('+quoted+r')\s+(.+);',line)
            if not m:raise ValueError('Unsupported compiled scope')
            parent=re.search(r',\s*([^,\s]+)$',m[4]);parent=parent[1] if parent else None
            if parent is not None and parent not in scopes:raise ValueError('Unknown compiled parent')
            current=m[1]
            if current in scopes:raise ValueError('Duplicate compiled scope')
            scopes[current]=(scopes[parent] if parent else ())+ (json.loads(m[2]),)
        elif line.startswith('.scope '):
            current=line[7:].removesuffix(';')
            if current not in scopes:raise ValueError('Unknown recalled scope')
        elif re.match(r'^\S+\s+\.(?:var|net)',line):
            m=re.fullmatch(r'(\S+)\s+\.(var|net8|net)(/[a-z0-9]+)?\s+(\*)?('+quoted+r'),\s*(-?\d+)\s+(-?\d+)([^;]*);(?:\s+.*)?',line)
            if not m or current not in scopes:raise ValueError('Unsupported compiled signal declaration')
            label,kind,flag,local,name,left,right,tail=m.groups();flag=flag or ''
            allowed=('', '/s','/i','/2s','/2u') if kind=='var' else ('','/s','/2s','/2u')
            if flag not in allowed or (kind=='var' and tail.strip()) or (kind!='var' and not re.fullmatch(r',\s*\S+(?:\s*,\s*\S+)*',tail)):
                raise ValueError('Unsupported signal fields')
            if local:hidden+=1;continue
            if kind=='var' and flag in ('/2s','/2u'):raise ValueError('Unsupported named two-state variable family')
            key=(scopes[current],json.loads(name))
            if key in rows:raise ValueError('Duplicate compiled signal name')
            rows[key]=dict(kind='14signal_integer' if flag=='/i' else '10signal_reg' if kind=='var' else '10signal_net',signed=int(flag in ('/s','/i','/2s')),msb=int(left),lsb=int(right))
    if not rows:raise ValueError('Missing compiled signals')
    return rows,hidden


def validate(state,compiled):
    declarations,hidden=compiled_signals(compiled);scopes={s['id']:s for s in state['metadata']['scopes']}
    traversal={s['traversal']:s['id'] for s in state['reference']['scopes']};paths={};seen=set()
    def name(value):
        raw=bytes.fromhex(value)
        if not raw.endswith(b'\0') or b'\0' in raw[:-1]:raise ValueError('Invalid bounded declaration name')
        return raw[:-1].decode()
    def path(ident):
        if ident not in paths:
            scope=scopes[ident];paths[ident]=(path(scope['parent']) if scope['parent'] else ())+ (name(scope['nameBytes']),)
        return paths[ident]
    for row in state['signals']['rows']:
        key=(path(traversal[row['scopeId']]),name(row['name']))
        if key in seen or declarations.get(key)!={k:row[k] for k in ('kind','signed','msb','lsb')}:raise ValueError('Signal metadata differs from compiled declaration')
        seen.add(key);width=abs(row['msb']-row['lsb'])+1
        if row['count']:
            step=1 if row['msb']>=row['lsb'] else -1
            if row['count']!=width or [b['value'] for b in row['cache']]!=[row['lsb']+step*i for i in range(width)]:raise ValueError('Signal bit cache differs from declared indices')
    if seen!=set(declarations):raise ValueError('Incomplete compiled signal coverage')
    return dict(signals=len(seen),hiddenFunctorOnlyDeclarations=hidden,compiledNamesClassesSignednessAndRangesExactlyEqual=True)


def state(root):
    lines=[l for n in ('metadata-before.txt','metadata-references-before.txt','handle-scopes.txt') for l in (root/n).read_text().splitlines()]
    lines += [l.replace('VSA_','VSH_',1) for l in (root/'scope-signals-before.txt').read_text().splitlines()]
    return joined_parse(lines)


def review(root):
    prior=budget_review(root);result=validate(state(root),(root/'io.vvp').read_text())
    return dict(qualified=False,controlsPassed=True,priorBudgetAssessmentSha256=sha(root/'assessment.json'),bindings=result,
        scope='Independent compiled scope paths and visible vector declarations match every initialized native signal name, exact class, signedness and declared bounds. Compiler-local star declarations do not create VPI handles. Existing owner/net and complete population checks are preserved. No ordinary write exclusion, unsupported-family/lifecycle, compact or normal transient qualification.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.write_text(json.dumps(review(a.root),indent=2)+'\n')
