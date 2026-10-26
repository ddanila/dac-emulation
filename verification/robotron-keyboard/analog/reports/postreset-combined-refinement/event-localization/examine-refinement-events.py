from pathlib import Path
import json,math,hashlib
root=Path('build/keyboard-controller-analog/postreset-refinement-events');steps=('25','12.5','6.25')
data={s:json.loads((root/(s+'.json')).read_text()) for s in steps}
for d in data.values():
 for e in d['events']:
  assert set(e)=={'actual','target','base','port'}
  assert all(math.isfinite(e[k]) for k in ('actual','target','base'))
  assert abs(e['actual']/1e-12-round(e['actual']/1e-12))<1e-6
pairs={}
for a,b in (('25','12.5'),('12.5','6.25'),('25','6.25')):
 left,right=data[a]['events'],data[b]['events']
 assert [e['port'] for e in left]==[e['port'] for e in right]
 differences=[]
 for i,(x,y) in enumerate(zip(left,right)):
  delta=round(y['actual']/1e-12)-round(x['actual']/1e-12)
  if delta:differences.append({'ordinal':i,'port':x['port'],'leftActualSeconds':x['actual'],'rightActualSeconds':y['actual'],'rightMinusLeftTicks':delta})
 pairs[a+'-'+b]={'samePortSequence':True,'events':len(left),'actualTimeDifferences':differences,'portsWithActualTimeDifferences':sorted({d['port'] for d in differences})}
result={'qualified':False,'scope':'Ordinal comparison of every retained TIME_AUDIT output record. These records identify ports and timestamps, not output values; exact firmware equivalence comes from the separate full review.','tickSeconds':1e-12,'pairs':pairs,'worstVoltageErrorEvent':{s:[e for e in data[s]['events'] if e['port']=='data_sink' and .001109019e0<e['actual']<.001109020e0] for s in steps},'interpretation':'A one-tick data_sink timing difference accompanies the worst voltage-error region. Causality and a correct timing fix are not established; no waveform alignment or numerical-gate exception is applied.'}
(root/'assessment.json').write_text(json.dumps(result,indent=2)+'\n')
print({k:len(v['actualTimeDifferences']) for k,v in pairs.items()})
