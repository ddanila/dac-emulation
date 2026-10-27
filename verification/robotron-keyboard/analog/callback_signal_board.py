"""Validate typed bridge handles and owner links at combined board boundaries."""
from signal_handle_board_budget import compiled_handles
from net_probe import pointer


class SignalHandleState:
    def __init__(self,compiled):
        self.compiled=compiled;self.bindings=None;self.contract=None;self.metadata=None;self.caches={};self.observations=0;self.links=0;self.cache_observations=0

    def set_bindings(self,lines):
        if self.bindings is not None or self.observations:raise ValueError('Late/duplicate typed handle bindings')
        a=lines[0].split()
        if len(a)!=3 or a[:2]!=['VHB_BEGIN','1'] or lines[-1]!='VHB_END':raise ValueError('Invalid typed handle header')
        rows=[]
        for line in lines[1:-1]:
            a=line.split()
            if len(a)!=5 or a[0]!='VHB_LINK':raise ValueError('Invalid typed handle binding')
            index,identity=int(a[1]),int(a[2]);port,handle=map(pointer,a[3:])
            if index!=len(rows) or min(identity,port,handle)<=0:raise ValueError('Invalid typed handle handoff')
            rows.append(dict(index=index,id=identity,port=port,handle=handle))
        if not rows or len(rows)!=int(lines[0].split()[2]) or any(len({r[k] for r in rows})!=len(rows) for k in ('id','port','handle')):raise ValueError('Incomplete/aliased typed handle handoff')
        self.bindings=rows

    def observe(self,state,graph,callbacks):
        if self.bindings is None:raise ValueError('Missing typed handle handoff')
        typed=state['typedSignals'];links=state['callbackSignalLinks'];tick=state['threads']['tick']
        if typed['tick']!=tick or links['tick']!=tick:raise ValueError('Typed handle boundary time mismatch')
        ports=state['portState']['ports'];rows={r['id']:r for r in typed['rows']}
        if len(ports)!=len(self.bindings) or set(rows)!={b['id'] for b in self.bindings}:raise ValueError('Changed typed port population')
        if self.contract is None:self.contract=compiled_handles(self.compiled,[p['name'] for p in ports])
        nodes={n['id']:n for n in graph.nodes};scopes={s['id']:s['pointer'] for s in state['scopes']};metadata=[]
        for port,b in zip(ports,self.bindings):
            r=rows[b['id']]
            if r['pointer']!=b['handle'] or bytes.fromhex(r['name'])!=port['name'].rsplit('.',1)[-1].encode()+b'\0':raise ValueError('Changed typed port identity')
            if any(r[k]!=v for k,v in self.contract[port['name']].items()) or abs(r['msb']-r['lsb'])+1!=port['bits']:raise ValueError('Typed metadata differs from compiled port')
            node=nodes.get(r['nodeId'])
            if not node or node['key']!=r['node'] or not node['filter'] or scopes.get(r['scopeId'])!=r['scope']:raise ValueError('Unbound typed graph/scope identity')
            width=port['bits'];expected=[r['lsb']+i if r['msb']>=r['lsb'] else r['lsb']-i for i in range(width)]
            if r['count'] and (r['count']!=width or [x['value'] for x in r['cache']]!=expected):raise ValueError('Wrong typed bit-cache mapping')
            cache={k:r[k] for k in ('bits','count','cache')}
            if b['id'] in self.caches and cache!=self.caches[b['id']]:raise ValueError('Changed existing typed bit-cache allocation')
            if r['count']:self.caches[b['id']]=cache;self.cache_observations+=1
            metadata.append({k:v for k,v in r.items() if k not in ('bits','count','cache')})
        if self.metadata is None:self.metadata=metadata
        if metadata!=self.metadata:raise ValueError('Changed typed signal metadata/lifetime')
        bindings={r['index']:r for r in self.bindings}
        cb_bindings={r['id']:r for r in callbacks.bindings}
        if {r['callbackId'] for r in links['rows']}!=set(cb_bindings):raise ValueError('Incomplete callback signal links')
        for link in links['rows']:
            cb=cb_bindings[link['callbackId']];b=bindings[cb['index']];r=rows[b['id']]
            owner_id,cb_pointer,_,_=callbacks.callback_identities[cb['id']]
            if (b['port'],b['handle'])!=(cb['user'],cb['object']):raise ValueError('Typed port differs from callback handoff')
            if owner_id not in callbacks.previous or callbacks.identities[owner_id][0]!=link['owner'] or owner_id!=link['ownerId'] or cb_pointer!=link['callback']:raise ValueError('Callback owner lifetime mismatch')
            if (link['handleId'],link['handle'],link['nodeId'],link['node'])!=(b['id'],b['handle'],r['nodeId'],r['node']):raise ValueError('Callback typed signal/node mismatch')
            if nodes[r['nodeId']]['filter']!=link['filter']:raise ValueError('Callback native filter mismatch')
        self.observations+=1;self.links+=len(links['rows'])

    def result(self):
        if not self.observations:raise ValueError('Missing typed signal observations')
        return dict(typedSignalObservations=self.observations,boundTypedPortHandles=len(self.bindings),callbackSignalLinkObservations=self.links,typedBitCacheObservations=self.cache_observations)
