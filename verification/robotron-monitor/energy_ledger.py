"""Signed circuit work and independent passive storage from ngspice expansion.

Semiconductor work includes internal storage; it is not labelled heat. Numerical
thermal/flux/current monitor states are explicitly excluded, never counted as
physical energy. Unsupported primitives block coverage before a solve.
"""
import hashlib,json,math,re,subprocess,time
from file_hash import digest_stream
from pathlib import Path
import monitor_runtime

EXCLUDED={
 'c.xcrt.ch':'thermal state','c.xcrt.cc':'thermal state',
 'r.xcrt.rhc':'thermal conductance','r.xcrt.rha':'thermal conductance','r.xcrt.rca':'thermal conductance',
 'b.xcrt.bheat':'duplicate electrical-to-thermal transfer','b.xcrt.bhrad':'thermal loss','b.xcrt.bcrad':'thermal loss',
 'v.xcrt.vholdh':'held temperature','v.xcrt.vholdc':'held temperature',
 'b.xcrt.blaunch':'current monitor','b.xcrt.bemitted':'current monitor','v.xcrt.vcollection':'current monitor',
 'c.x1136.xshared.cflux':'magnetic B-state, not physical capacitance',
 'r.x1136.xshared.rflux':'numerical flux-state leakage',
 'b.x1136.xshared.bflux':'Faraday B-state integrator'}


def number(s):
    m=re.fullmatch(r'([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?)(meg|[tgkmunpf])?',s.lower())
    if not m:raise ValueError('unevaluated passive value: '+s)
    return float(m[1])*{None:1,'t':1e12,'g':1e9,'meg':1e6,'k':1e3,'m':1e-3,'u':1e-6,'n':1e-9,'p':1e-12,'f':1e-15}[m[2]]


def inventory(listing):
    parts=[];names=set()
    for line in listing.splitlines():
        match=re.match(r'\s*(\d+) : (.*)',line)
        if not match or int(match[1])==1:continue
        tokens=match[2].lower().split()
        if not tokens or tokens[0].startswith(('.', '*')):continue
        name=tokens[0];kind=name[0]
        if name in names:raise ValueError('duplicate expanded component '+name)
        names.add(name)
        if kind not in 'rclkdqvbefgh':raise ValueError('unsupported energy primitive '+name)
        part=dict(name=name,kind=kind,nodes=tokens[1:4] if kind=='q' else tokens[1:3])
        if name in EXCLUDED:
            part['excluded']=EXCLUDED[name];parts.append(part);continue
        if kind in 'rcl':
            if any(not option.startswith('ic=') for option in tokens[4:]):raise ValueError('unsupported passive options '+name)
            part['value']=number(tokens[3])
            if part['value']<=0:raise ValueError('nonpositive passive '+name)
        if kind=='k':part.update(inductors=tokens[1:3],coupling=number(tokens[3]),nodes=[])
        if kind=='q' and len(tokens)!=5:raise ValueError('unsupported BJT terminals/options '+name)
        if kind=='f':part.update(control=tokens[3],gain=number(tokens[4]))
        if kind=='g':part.update(control_nodes=tokens[3:5],gain=number(tokens[5]))
        if kind=='b':part['behavior']=match[2][match[2].lower().find(tokens[3]):]
        parts.append(part)
    if not parts:raise ValueError('empty expanded energy inventory')
    return parts


def current_probe(part):
    n=part['name'];k=part['kind']
    if k=='d' and 'terminal_meter' in part:return 'i('+part['terminal_meter']+')'
    if k in 'lveh':return f'i({n})'
    if k in 'bcd':return f'@{n}[id]' if k=='d' else f'@{n}[i]'
    return None


def instrument(text,output,runtime):
    out=Path(output).resolve();out.mkdir(parents=True,exist_ok=False)
    binary,receipt=monitor_runtime.verify(runtime)
    original=text
    # Device @ic/@ib omit external base-collector displacement current in
    # ngspice's BJT implementation. Measure actual external terminal currents.
    def meter_device(match):
        tokens=match[0].split();name=tokens[0]
        bjt=name.lower().startswith('q')
        if len(tokens)!=(5 if bjt else 4):raise ValueError('unsupported semiconductor terminal instrumentation')
        lines=[]
        for i,terminal in (((1,'c'),(2,'b'),(3,'e')) if bjt else ((1,'a'),)):
            internal=name+'_energy_'+terminal
            lines.append(f'V{internal} {tokens[i]} {internal} 0')
            tokens[i]=internal
        return '\n'.join([' '.join(tokens),*lines])
    text=re.sub(r'(?im)^[ \t]*[qd][^\n]*',meter_device,text)
    deck=re.sub(r'(?im)^\.tran[^\n]*\n','',text)
    deck=re.sub(r'(?im)^\.save[^\n]*\n','',deck)
    deck=re.sub(r'(?im)^\.end\s*$', '.control\nlisting e\nquit\n.endc\n.end',deck)
    (out/'listing.cir').write_text(deck)
    p=subprocess.run([str(binary),'-n','-b','listing.cir'],cwd=out,text=True,capture_output=True,timeout=30)
    (out/'expanded.txt').write_text(p.stdout+p.stderr)
    if p.returncode:raise ValueError('energy inventory expansion failed')
    parts=inventory(p.stdout);probes=set()
    meters={part['nodes'][1]:part['name'] for part in parts if part['kind']=='v' and '_energy_' in part['name']}
    for part in parts:
        if part['kind']=='q':part['terminal_meters']=[meters[n] for n in part['nodes']]
        if part['kind']=='d':part['terminal_meter']=meters[part['nodes'][0]]
    for part in parts:
        if 'excluded' in part:continue
        probes.update(f'v({n})' for n in part['nodes'] if n!='0')
        current=current_probe(part)
        if current:probes.add(current)
        if part['kind']=='q':probes.update(f'i({n})' for n in part['terminal_meters'])
        if part['kind']=='f':probes.add(f'i({part["control"]})')
        if part['kind']=='g':probes.update(f'v({n})' for n in part['control_nodes'] if n!='0')
    probes.add('v(x1136.xshared.flux_b)') if any(p['name']=='b.x1136.xshared.bprimary' for p in parts) else None
    additions=' '.join(sorted(probes))
    instrumented=re.sub(r'(?im)^(\.save[^\n]*)',lambda m:m[0]+' '+additions,text)
    manifest=dict(format='dac-circuit-energy-inventory-v1',parts=parts,runtime=receipt,
        original_deck_sha256=hashlib.sha256(original.encode()).hexdigest(),
        instrumented_deck_sha256=hashlib.sha256(instrumented.encode()).hexdigest(),
        coverage_complete=True,parts_sha256=hashlib.sha256(json.dumps(parts,sort_keys=True).encode()).hexdigest(),probes=sorted(probes))
    (out/'inventory.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return instrumented,manifest


def voltage(row,node):return 0. if node=='0' else row['v('+node+')']

def current(row,p):
    key=current_probe(p)
    if key in row:return row[key]
    # ngspice exposes saved scalar device parameters as i(@device[param]).
    return row['i('+key+')']


def core_energy(b,core,smoothing=1e-5):
    # Integral_0^B H(s) ds using exactly the smoothed inverse constitutive law.
    h=core['h_a_per_m'];bs=core['b_t'];i=h.index(0);h=h[i:];bs=bs[i:]
    slopes=[(v-u)/(y-x) for u,v,x,y in zip(h,h[1:],bs,bs[1:])]
    def primitive(x):return .5*(x*math.sqrt(x*x+smoothing*smoothing)+smoothing*smoothing*math.asinh(x/smoothing))
    integral=.5*slopes[0]*b*b
    for i in range(1,len(slopes)):
        knee=bs[i];delta=slopes[i]-slopes[i-1]
        integral+=delta*(.5*b*b+.5*(primitive(b-knee)-primitive(-knee)-primitive(b+knee)+primitive(knee)))
    def val(k):v=core[k];return v['value'] if isinstance(v,dict) else v
    return val('area_m2')*val('length_m')*integral


def normalization(groups,storage_change):
    # Internal E/F transformer transfers cancel in controlled-source work.
    # Counting both sides would inflate the scale and conceal a residual.
    sources=(groups['source_work'],groups['controlled_source_work'])
    delivered=sum(max(-v,0.) for v in sources)
    absorbed=sum(max(v,0.) for v in sources)+sum(max(groups[k],0.) for k in
        ('resistor_loss','semiconductor_work','beam_work','grid2_work','heater_work'))
    return max(delivered,absorbed,abs(storage_change),1e-30)


def assess(raw,manifest,*,start_s,end_s,core=None,deadline=None):
    import steady_supply
    raw=Path(raw)
    if not all(math.isfinite(t) for t in (start_s,end_s)) or not 0<=start_s<end_s:raise ValueError('invalid energy window')
    if manifest.get('parts_sha256')!=hashlib.sha256(json.dumps(manifest['parts'],sort_keys=True).encode()).hexdigest():
        raise ValueError('energy inventory integrity mismatch')
    if any((p['kind']=='d' and not p.get('terminal_meter')) or
           (p['kind']=='q' and len(p.get('terminal_meters',[]))!=3) for p in manifest['parts']):
        raise ValueError('incomplete semiconductor terminal metering')
    deck=Path(raw).with_name('run.cir')
    if not deck.exists() or hashlib.sha256(deck.read_bytes()).hexdigest()!=manifest['instrumented_deck_sha256']:
        raise ValueError('energy inventory does not match solved deck')
    with raw.open('rb') as stream:raw_sha256=digest_stream(stream)
    parts=manifest['parts'];known={p['name']:p for p in parts}
    energies={};absolute={};previous=None;first=last=None;first_time=None
    groups={k:0. for k in ('source_work','resistor_loss','semiconductor_work','controlled_source_work','beam_work','grid2_work','heater_work','magnetic_work','diagnostic_storage_work')}
    def state(row):
        stores={};powers={}
        for p in parts:
            if 'excluded' in p:continue
            n=p['name'];k=p['kind'];nodes=p['nodes']
            v=voltage(row,nodes[0])-voltage(row,nodes[1]) if nodes else 0
            if k=='c':
                stores[n]=.5*p['value']*v*v;powers[n]=('diagnostic_storage_work',v*current(row,p));continue
            if k=='l':
                stores[n]=.5*p['value']*current(row,p)**2;powers[n]=('diagnostic_storage_work',v*current(row,p));continue
            if k=='k':
                a,b=(known[x] for x in p['inductors']);stores[n]=p['coupling']*math.sqrt(a['value']*b['value'])*current(row,a)*current(row,b);continue
            if k=='r':power=v*v/p['value'];group='resistor_loss'
            elif k=='q':
                # Include emitter independently: the implicit substrate is at
                # ground, and its displacement current need not sum to zero
                # over the three exposed terminals.
                if len(p['terminal_meters'])!=3:raise ValueError('incomplete BJT terminal metering')
                power=sum(voltage(row,node)*row['i('+meter+')'] for node,meter in zip(nodes,p['terminal_meters']));group='semiconductor_work'
            elif k=='d':power=v*current(row,p);group='semiconductor_work'
            elif k=='v':power=v*current(row,p);group='source_work'
            elif k=='f':power=v*row['i('+p['control']+')']*p['gain'];group='controlled_source_work'
            elif k=='g':power=v*(voltage(row,p['control_nodes'][0])-voltage(row,p['control_nodes'][1]))*p['gain'];group='controlled_source_work'
            else:
                power=v*current(row,p);group='controlled_source_work'
                if n in ('b.xcrt.bbeam','b.xcrt.blaunchload'):group='beam_work'
                if n=='b.xcrt.bg2':group='grid2_work'
                if n=='b.xcrt.bheater':group='heater_work'
                if n=='b.x1136.xshared.bprimary':group='magnetic_work'
            powers[n]=(group,power)
        if any(p['name']=='b.x1136.xshared.bprimary' for p in parts):
            if core is None:raise ValueError('missing constitutive law for core storage')
            stores['physical-core']=core_energy(row['v(x1136.xshared.flux_b)'],core)
        return stores,powers
    def accumulate(row):
        nonlocal previous,first,last,first_time
        st,pw=state(row)
        if first is None:first=st;first_time=row['time']
        if previous:
            t,old=previous;dt=row['time']-t
            for n,(group,power) in pw.items():
                e=dt*(old[n][1]+power)/2;groups[group]+=e;energies[n]=energies.get(n,0.)+e
                absolute[group]=absolute.get(group,0.)+dt*(abs(old[n][1])+abs(power))/2
        previous=(row['time'],pw);last=st
    prior=None
    for index,row in enumerate(steady_supply.raw_rows(raw)):
        if index%10000==0 and deadline is not None and time.monotonic()>=deadline:raise TimeoutError('energy accounting budget exhausted')
        # Decimal SPICE stop times can round one ULP below the Python value.
        # This only reconciles endpoint representation; it does not extrapolate
        # a missing timestep or admit duplicate/nonmonotonic raw samples.
        for boundary in (start_s,end_s):
            if abs(row['time']-boundary)<=4*math.ulp(boundary):row['time']=boundary
        t=row['time']
        if prior is not None:
            for boundary in (start_s,end_s):
                if prior['time']<boundary<=t and (previous is None or previous[0]<boundary):
                    f=(boundary-prior['time'])/(t-prior['time']);cut={k:prior[k]+f*(row[k]-prior[k]) for k in row};cut['time']=boundary;accumulate(cut)
        if start_s<=t<end_s and (previous is None or previous[0]<t):accumulate(row)
        prior=row
    if first is None or first_time!=start_s or previous[0]!=end_s:raise ValueError('incomplete energy window')
    delta={k:last[k]-v for k,v in first.items()};core_delta=delta.get('physical-core',0.)
    core_residual=abs(groups['magnetic_work']-core_delta)/max(absolute.get('magnetic_work',0.),abs(core_delta),1e-30)
    # Replace reversible primary work with independently computed core storage.
    balance=sum(v for k,v in groups.items() if k not in ('magnetic_work','diagnostic_storage_work'))+sum(delta.values())
    scale=normalization(groups,sum(delta.values()))
    residual=abs(balance)/scale
    terminal_residual=sum(groups.values());terminal_error=abs(terminal_residual)/scale
    with raw.open('rb') as stream:
        if digest_stream(stream)!=raw_sha256:raise ValueError('energy raw trace changed during accounting')
    return dict(format='dac-circuit-energy-ledger-v1',start_s=start_s,end_s=end_s,groups_j=groups,
        raw_sha256=raw_sha256,inventory_sha256=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest(),
        component_work_j=energies,storage_change_j=delta,residual_j=balance,normalization_j=scale,relative_error=residual,
        passive_work_minus_storage_j=groups['diagnostic_storage_work']-sum(v for n,v in delta.items() if n!='physical-core'),
        terminal_work_residual_j=terminal_residual,terminal_relative_error=terminal_error,
        magnetic_relative_error=core_residual,coverage_complete=manifest['coverage_complete'],
        accepted=manifest['coverage_complete'] and residual<.01 and terminal_error<.01 and (core is None or core_residual<.01),
        qualification='signed-work-and-passive-storage; semiconductor terminal work includes internal storage',full_monitor_qualified=False)
