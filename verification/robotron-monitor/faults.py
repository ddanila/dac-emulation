"""Reversible, source-addressed fault transformations of exported connectivity.

No fault changes the authored schematic or widens healthy parameter bounds.
Inserted elements have separate derived identities and explicit numerical or
physical roles. Unsupported mutations fail closed instead of becoming nominal.
"""
import copy
import math
import re


class UnsupportedFault(ValueError):
    pass


def number(value):
    """Parse a single SPICE passive value (M is milli, MEG is mega)."""
    if isinstance(value,(float,int)) and not isinstance(value,bool):
        n=float(value)
    else:
        match=re.fullmatch(r'([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?)(meg|[tgkmunpf]?)',str(value),re.I)
        if not match:raise ValueError('not a literal passive value: '+str(value))
        n=float(match[1])*{'':1,'t':1e12,'g':1e9,'meg':1e6,'k':1e3,'m':1e-3,'u':1e-6,'n':1e-9,'p':1e-12,'f':1e-15}[match[2].lower()]
    if not math.isfinite(n) or n<=0:raise ValueError('passive value must be finite and positive')
    return n


def apply(components,models,fault,*,regularization=1.):
    """Return derived components, model cards and an auditable mutation record."""
    result=copy.deepcopy(components)
    if fault is None:return result,models,None
    if not math.isfinite(regularization) or not .1<=regularization<=10:
        raise ValueError('invalid regularization factor')
    matches=[c for c in result if c.get('source_id')==fault['target']]
    if len(matches)!=1:raise UnsupportedFault('target is absent or ambiguous: '+fault['target'])
    c=matches[0];original=copy.deepcopy(c);kind=c['reference'][0];op=fault['operation']
    additions=[];notes=[];refs={c['reference'].lower() for c in result}

    def resistor(a,b,value,role):
        index=1
        while 'rfault'+str(index) in refs:index+=1
        ref='Rfault'+str(index);refs.add(ref.lower())
        additions.append(dict(reference=ref,nodes=[a,b],value=f'{number(value):.15g}',
                              derived_from=fault['target'],role=role))

    def terminal(index,resistance,role):
        if not 0<=index<len(c['nodes']):raise UnsupportedFault('terminal outside device')
        old=c['nodes'][index];new='fault_'+c['reference'].lower()+'_'+str(index)
        if any(new in item['nodes'] for item in result):raise ValueError('fault net collision')
        c['nodes'][index]=new;resistor(old,new,resistance,role)

    if op in ('resistance_scale','capacitance_scale'):
        if kind!= {'resistance_scale':'R','capacitance_scale':'C'}[op]:raise UnsupportedFault('wrong passive type')
        c['value']=f"{number(c['value'])*number(fault['factor']):.15g}"
    elif op=='open':
        # Insert in series: retain any model capacitance/storage behind the break.
        if kind not in 'RCLDQ':raise UnsupportedFault('open requires a supported discrete device')
        terminal(int(fault.get('terminal',1))-1,1e12*regularization,'numerical open approximation')
        notes.append('Open represented by 1e12 ohm times the numerical refinement factor.')
    elif op in ('short','leakage'):
        if kind not in 'RCLDQ':raise UnsupportedFault('short/leakage requires a supported discrete device')
        terminals=fault.get('terminals',[1,2])
        if len(terminals)!=2 or any(type(t) is not int or not 1<=t<=len(c['nodes']) for t in terminals) or terminals[0]==terminals[1]:
            raise ValueError('invalid fault terminal pair')
        value=.001*regularization if op=='short' else number(fault['resistance_ohm'])
        resistor(*(c['nodes'][t-1] for t in terminals),value,
                 'numerical short approximation' if op=='short' else 'physical leakage resistance approximation')
        notes.append('A resistive leakage path is an approximation, not a fitted junction leakage law.' if op=='leakage' else 'Short represented by 1 milliohm times the numerical refinement factor.')
    elif op=='esr':
        if kind!='C':raise UnsupportedFault('ESR requires a capacitor')
        terminal(0,number(fault['resistance_ohm']),'additional capacitor ESR')
    elif op=='gain_scale':
        if kind!='Q':raise UnsupportedFault('gain degradation requires a BJT')
        model=c['value']
        match=re.search(r'(?im)^\.model\s+'+re.escape(model)+r'\s+(NPN|PNP)\s*\((.*?)\)',models.replace('\n+',' '),re.S|re.I)
        if not match:raise UnsupportedFault('BJT model cannot be cloned')
        body=match[2];factor=number(fault['factor'])
        if factor>=1:raise ValueError('gain degradation factor must be below one')
        bf=re.search(r'\bBF\s*=\s*(\{[^}]+\}|[^\s]+)',body,re.I)
        if not bf:raise UnsupportedFault('BJT gain not explicit')
        replacement='{('+bf[1].strip('{}')+')*'+str(factor)+'}'
        body=body[:bf.start(1)]+replacement+body[bf.end(1):]
        new_model='FAULT_'+c['reference']
        if re.search(r'\b'+re.escape(new_model)+r'\b',models,re.I):raise ValueError('fault model collision')
        models+=f'\n.model {new_model} {match[1]}({body})\n';c['value']=new_model
    else:
        raise UnsupportedFault('unsupported fault operation: '+op)
    result+=additions
    return result,models,dict(definition=copy.deepcopy(fault),original=original,
                              effective=copy.deepcopy(c),inserted=additions,
                              regularization=regularization,notes=notes)
