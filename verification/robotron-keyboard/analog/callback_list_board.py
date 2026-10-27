"""Bind compact callback lists to initialized ports at combined board boundaries."""
from callback_delta import block,image,reconstruct
from callback_list_probe import parse
from net_probe import pointer


class CallbackListState:
    def __init__(self):
        self.bindings=None;self.reference=None;self.identities={};self.previous=set();self.retired=set();self.callback_identities={};self.observations=0;self.maximum=0

    def set_bindings(self,lines):
        if self.bindings is not None or self.reference is not None or self.observations:raise ValueError('Late/duplicate callback bindings')
        a=lines[0].split()
        if len(a)!=3 or a[:2]!=['VLB_BEGIN','1'] or lines[-1]!='VLB_END':raise ValueError('Invalid callback binding header')
        bindings=[]
        for line in lines[1:-1]:
            a=line.split()
            if len(a)!=7 or a[0]!='VLB_LINK':raise ValueError('Invalid callback binding')
            index,identity=map(int,a[1:3]);port,handle,signal,function=map(pointer,a[3:])
            if index<0 or identity<=0 or min(port,handle,signal,function)<=0:raise ValueError('Invalid initialized callback identity')
            bindings.append(dict(index=index,id=identity,user=port,pointer=handle,object=signal,function=function))
        if not bindings or len(bindings)!=int(lines[0].split()[2]):raise ValueError('Incomplete callback bindings')
        for key in ('index','id','user','pointer','object'):
            if len({r[key] for r in bindings})!=len(bindings):raise ValueError('Aliased callback bindings')
        if [r['index'] for r in bindings]!=sorted(r['index'] for r in bindings) or len({r['function'] for r in bindings})!=1:raise ValueError('Invalid bridge callback ordering/function')
        self.bindings=bindings

    def set_reference(self,lines):
        if self.bindings is None or self.reference is not None or self.observations:raise ValueError('Missing bindings or repeated callback reference')
        frame,end=block(lines)
        if end!=len(lines) or frame['mode']!='R':raise ValueError('Invalid callback reference')
        self.reference=frame['rows'];parse(image(frame['tick'],self.reference))

    def observe(self,state):
        if self.reference is None or self.bindings is None:raise ValueError('Missing callback reference/bindings')
        frame=state['callbackListFrame'];full=parse(reconstruct(self.reference,frame))
        if full['tick']!=state['threads']['tick']:raise ValueError('Callback boundary time mismatch')
        expected=[p['index'] for p in state['portState']['ports'] if p['direction']!=1]
        if [r['index'] for r in self.bindings]!=expected:raise ValueError('Callback bindings differ from initialized port directions')
        if state['outputCallbacks']!=[dict(port=r['index'],callbackId=r['id']) for r in self.bindings]:raise ValueError('Changed prior output callback lifetimes')
        rows={};current=set()
        for owner in full['owners']:
            identity=owner['id'];intrinsic=(owner['pointer'],owner['kind'])
            if identity in self.retired or self.identities.setdefault(identity,intrinsic)!=intrinsic:raise ValueError('Callback owner lifetime reused')
            current.add(identity)
            # The admitted compiled board has variable arrays, not net arrays.
            if owner['words']:raise ValueError('Net-array association outside admitted board profile')
            for cb in owner['callbacks']:
                rows[cb['id']]=cb
                intrinsic=(identity,cb['pointer'],cb['time'],cb['value'])
                if self.callback_identities.setdefault(cb['id'],intrinsic)!=intrinsic:raise ValueError('Changed callback owner/self-field binding')
        if set(rows)!={r['id'] for r in self.bindings}:raise ValueError('Unbound or missing native callbacks')
        for r in self.bindings:
            if any(rows[r['id']][k]!=r[k] for k in ('pointer','object','user','function')):raise ValueError('Callback differs from initialized bridge referents')
        self.retired.update(self.previous-current);self.previous=current
        self.observations+=1;self.maximum=max(self.maximum,len(current))

    def result(self):
        if not self.observations:raise ValueError('Missing callback board observations')
        return dict(callbackListObservations=self.observations,boundOutputCallbacks=len(self.bindings),uniqueCallbackOwners=len(self.identities),maximumCallbackOwners=self.maximum,retiredCallbackOwners=len(self.retired))
