"""Parse only initialized port state and its fixed direction/packing contract."""
import math


def snapshot(lines):
    h=lines[0].split()
    if len(h)!=5 or h[:2]!=['VP_BEGIN','1'] or lines[-1]!='VP_END':raise ValueError('Invalid port header')
    counts=list(map(int,h[2:]));count=sum(counts)
    if any(n<0 for n in counts) or count<1:raise ValueError('Invalid port counts')
    context=lines[1].split()
    if len(context)!=6 or context[0]!='VP_CONTEXT':raise ValueError('Missing port context')
    base,tick=map(float.fromhex,context[1:3]);pending_in,pending_out,stop=map(int,context[3:])
    if not math.isfinite(base) or base<0 or not math.isfinite(tick) or tick<=0 or min(pending_in,pending_out)<0 or stop not in (0,1):raise ValueError('Invalid bridge context')
    ports=[];names=set();position=0;inputs=outputs=0
    for line in lines[2:-1]:
        a=line.split()
        if len(a)!=11 or a[0]!='VP_PORT':raise ValueError('Invalid port record')
        index,direction,bits,pos,flags,aval,bval=map(int,a[1:8])
        expected=1 if index<counts[0] else (2 if index<counts[0]+counts[1] else 3)
        if index!=len(ports) or direction!=expected or not 1<=bits<=32 or flags & ~{1:1,2:2,3:3}[direction]:raise ValueError('Invalid port layout/flags')
        if index in (0,counts[0],counts[0]+counts[1]):position=0
        if pos!=position:raise ValueError('Changed port packing')
        position+=bits
        if direction==1:
            if a[8:10]!=['-','-']:raise ValueError('Input-only uninitialized new value was read')
            new=None
        else:new=list(map(int,a[8:10]))
        values=[aval,bval]+(new or [])
        if any(not -2**31<=v<2**31 for v in values):raise ValueError('Invalid port vector word')
        name=bytes.fromhex(a[10]).decode()
        if not name or name in names:raise ValueError('Missing/aliased port identity')
        names.add(name);inputs+=bool(flags&1);outputs+=bool(flags&2)
        ports.append({'index':index,'direction':direction,'bits':bits,'position':pos,'flags':flags,'previous':[aval,bval],'new':new,'name':name})
    if len(ports)!=count or inputs!=pending_in or outputs!=pending_out:raise ValueError('Port count/pending mismatch')
    return {'counts':counts,'baseTime':base,'tickLength':tick,'inPending':pending_in,'outPending':pending_out,'stop':stop,'ports':ports}
