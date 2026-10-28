"""Bind sampled ADC decisions to board models and scalar HDL input delivery."""
import argparse,json,math,re
from pathlib import Path
from trace_io import open_text
from ttl7406_probe import sha
from adc_decision_control_review import assess as control_assess
from delivery_audit_review import scan as delivery_scan
from raw_pair_review import compare_raw
from audit_log import equal
from postreset_startup_review import FIRMWARE
HERE=Path(__file__).resolve().parent

def scan(folder):
    deck=(folder/'io.cir').read_text();models={};converters={};outputs={}
    for name,params in re.findall(r'^\.model\s+(\S+)\s+adc_bridge\(([^)]*)\)\s*$',deck,re.M|re.I):
        values=dict(in_low=.1,in_high=.9,rise_delay=1e-9,fall_delay=1e-9)
        for key,value in re.findall(r'(\w+)=([^\s]+)',params):values[key]=float(value)
        if set(values)!={'in_low','in_high','rise_delay','fall_delay'} or values['in_low']>values['in_high'] or not all(math.isfinite(v) for v in values.values()):raise ValueError('Unsupported ADC model')
        models[name.lower()]=values
    for name,inputs,outs,model in re.findall(r'^(A\S+)\s+\[([^]]+)\]\s+\[([^]]+)\]\s+(\S+)\s*$',deck,re.M|re.I):
        if model.lower() not in models:continue
        inputs=inputs.lower().split();outs=outs.lower().split()
        if len(inputs)!=len(outs):raise ValueError('Unsupported multi-bit conversion')
        for node,output in zip(inputs,outs):
            key=(name.lower(),node)
            if key in converters or output in outputs:raise ValueError('Ambiguous ADC connection')
            converters[key]=dict(models[model.lower()],output=output);outputs[output]=key
    hdl=re.search(r'^Ahdl\s+\[([^]]+)\]',deck,re.M|re.I)
    compiled=(folder/'io.vvp').read_text();top=re.search(r'\.scope module, "firmware_io_electrical_bus".*?(?=\nS_\w+ \.scope)',compiled,re.S)
    if not hdl or not top or not converters:raise ValueError('Missing ADC/HDL binding')
    ports=re.findall(r'\.port_info \d+ /INPUT (\d+) "([^"]+)";',top[0]);nodes=hdl[1].lower().split();offset=0;scalar={}
    for width,name in ports:
        width=int(width)
        if width==1 and nodes[offset] in outputs:scalar[name]=outputs[nodes[offset]]
        offset+=width
    if offset!=len(nodes):raise ValueError('HDL input width mismatch')
    decisions=[];pending={};witnesses=[];applications=[];input_count=0
    with open_text(folder/'ngspice.log') as stream:
        for line in stream:
            if 'ADC_CROSS ' in line:
                m=re.fullmatch(r'Instance: (\S+)\s+Message: ADC_CROSS time=(\S+) node=(\S+) value=(\S+) old=(\d+) new=(\d+)\s*',line)
                if not m:raise ValueError('Malformed ADC trace')
                instance,time,node,value,old,new=m.groups();key=(instance.lower(),node.lower())
                if key not in converters:raise ValueError('Unknown ADC connection')
                time=float.fromhex(time);value=float.fromhex(value);old=int(old);new=int(new);model=converters[key]
                expected=1 if value>=model['in_high'] else 0 if value<=model['in_low'] else 2
                if not math.isfinite(time) or time<0 or not math.isfinite(value) or old not in range(4) or old==new or new!=expected:raise ValueError('ADC decision violates source threshold rule')
                delay=model['fall_delay'] if new==0 or (new==2 and old!=0) else model['rise_delay']
                record=dict(instance=key[0],node=key[1],time=time,value=value,old=old,new=new,delay=delay,scheduled=time+delay)
                decisions.append(record);pending[key]=record
            elif line.startswith('DELIVERY_AUDIT input '):
                d=dict(x.split('=',1) for x in line.split()[2:]);port=d['port'];input_count+=1
                if port not in scalar:continue
                applications.append(d)
    # ADC diagnostics use the frontend output stream while bridge diagnostics
    # use stderr. Buffering can reorder their lines; bind exact recorded times.
    for event in decisions:pending.setdefault(((event['instance'],event['node']),event['scheduled']),[]).append(event)
    for d in applications:
        port=d['port'];actual=float(d['actual']);target=float(d['target']);base=float(d['base']);aval=int(d['aval']);bval=int(d['bval'])
        matches=pending.get((scalar[port],base),[])
        if not matches:raise ValueError('Input without exact ADC event-base match')
        event=matches[0]
        if any(other!=event for other in matches):raise ValueError('Ambiguous ADC event-base match')
        expected=(0,0) if event['new']==0 else (1,0) if event['new']==1 else (1,1)
        if (aval,bval)!=expected:raise ValueError('ADC/input value mismatch')
        witnesses.append(dict(port=port,**event,actual=actual,target=target,base=base,targetAheadSeconds=target-base,hdlOffsetSeconds=actual-base))
    if not decisions or not witnesses or set(scalar)-{w['port'] for w in witnesses}:raise ValueError('Incomplete ADC/input observation')
    return dict(decisions=len(decisions),initialDecisions=sum(d['time']==0 for d in decisions),converters=len(converters),inputApplications=input_count,scalarPorts=scalar,scalarDeliveryWitnesses=witnesses,maximumTargetAheadSeconds=max(w['targetAheadSeconds'] for w in witnesses),maximumAbsoluteHdlOffsetSeconds=max(abs(w['hdlOffsetSeconds']) for w in witnesses))

def assess(root):
    from retained_evidence import check
    retained=HERE/'reports/delivery-audit-board';check(retained)
    evidence=root/'adc-source';check(evidence);proof=json.loads((evidence/'assessment.json').read_text());selected=json.loads((evidence/'selected-build.json').read_text())
    if sha(evidence/'cfunc.o')!=proof['adcObjectSha256'] or proof['adcObjectSha256'] not in selected['objects'].values() or proof['selectedDigitalSha256']!=selected['outputs']['digital.cm']:raise ValueError('Changed ADC source/object binding')
    base=control_assess(root,HERE/'adc_decision_capture.py');comparisons={};audits={}
    runtime=json.loads((root/'off/run.json').read_text())['runtime']
    if [m['sha256'] for m in runtime['codeModels'] if Path(m['path']).name=='digital.cm']!=[proof['selectedDigitalSha256']]:raise ValueError('Trace source is not selected model')
    for mode in ('off','tick','on','retry'):
        prior=json.loads((retained/mode/'run.json').read_text());folder=root/mode
        comparisons[mode]=compare_raw(folder/'waveform.raw',retained/mode/'waveform.raw',[base['logs'][mode]['count'],prior['summary']['count']],20e-6,exact=True)
        if not equal(folder/'ngspice.log',retained/mode/'ngspice.log',FIRMWARE):raise ValueError('ADC logging changed firmware')
        audits[mode]=dict(decisions=scan(folder),delivery=delivery_scan(folder/'ngspice.log'))
    return dict(qualified=False,controlsPassed=True,boardAssessment=base,exactOriginalComparisons=comparisons,audits=audits,scope='ADC trace logging preserves all bounded samples and firmware. Sampled decisions satisfy source thresholds, and observed scalar input values/event bases bind to preceding ADC decisions plus declared delay. These are logged event decisions, not exact analog crossings or complete rejected-step histories. Full post-reset qualification and numerical non-growth remain open.')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.write_text(json.dumps(assess(a.root),indent=2)+'\n')
