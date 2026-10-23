#!/usr/bin/env python3
"""Check published static endpoint conditions without fitting semiconductor parameters."""
import argparse,json,math,os,shutil,subprocess
from pathlib import Path
from failure_evidence import solver_diagnostic
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent

def fixtures():
    limits=json.loads((HERE/'ttl7406_limits.json').read_text())
    for c in limits['cases']:
        yield '7406',c['name'],[f'Vcc vp 0 {c["supplyVolts"]}',f'Vin a 0 {c["inputVolts"]}',f'Rload vp y {c["pullupOhms"]}',f'Iload 0 y {c["injectedOutputAmps"]}'],('v(y)' if c['metric']=='outputVolts' else '-i(Vin)'),c.get('minimum',0),c.get('maximum',0)
    # TI SDLS031A printed p.3: VIK at II=-12mA; IOH at Vout=30V.
    yield '7406','input-clamp',['Vcc vp 0 4.75','Iinput a 0 .012','Rload vp y 1e9'],'v(a)',-1.5,0
    yield '7406','off-leakage',['Vcc vp 0 4.75','Vin a 0 .8','Vout y 0 30'],'-i(Vout)',0,.00025
    limits=json.loads((HERE/'d104_limits.json').read_text())
    for c in limits['dcChecks']:
        n=c['parameter'];metric='v(y)' if n.startswith('VO') else '-i(Vin)'
        lo,hi=({'IIL':(-c.get('maxMagnitudeA',0),0),'IIH':(0,c.get('maxA',0)),
                'VOH':(c.get('minV',0),c['supplyV']),'VOL':(0,c.get('maxV',0))})[n]
        yield '7404',n,[f'Vcc vp 0 {c["supplyV"]}',f'Vin a 0 {c["inputV"]}',f'Iload y 0 {-c.get("outputCurrentA",0)}'],metric,lo,hi

def verify(root):
    report=json.loads((root/'assessment.json').read_text())
    for name,digest in report['sources'].items():
        if sha(HERE/name)!=digest:raise ValueError('Device producer changed: '+name)
    expected={(d,n,t) for d,n,*_ in fixtures() for t in (0,25,70)}
    if {(c['device'],c['name'],c['temperatureC']) for c in report['cases']}!=expected:
        raise ValueError('Incomplete endpoint inventory')
    limits={(d,n):(metric,lo,hi) for d,n,_,metric,lo,hi in fixtures()}
    for c in report['cases']:
        folder=root/c['directory']
        for name,digest in c['artifacts'].items():
            if sha(folder/name)!=digest:raise ValueError('Changed device capture')
        metric,lo,hi=limits[c['device'],c['name']]
        value=float((folder/'trace.txt').read_text().splitlines()[1].split()[1])
        if (c['metric'],c['minimum'],c['maximum'],c['value'],c['withinLimit'])!=(metric,lo,hi,value,lo<=value<=hi):
            raise ValueError('Incorrect endpoint assessment')
        if solver_diagnostic((folder/'ngspice.log').read_text()):raise ValueError('Invalid solver capture')
    if not report['completed'] or report['qualified'] or report['staticEndpointsPassed']!=all(c['withinLimit'] for c in report['cases']):
        raise ValueError('Incorrect qualification scope')
    return report

def main():
    p=argparse.ArgumentParser();group=p.add_mutually_exclusive_group(required=True);group.add_argument('--out',type=Path);group.add_argument('--verify',type=Path);p.add_argument('--ngspice',default='ngspice');a=p.parse_args()
    if a.verify:
        verify(a.verify);print('Static endpoint evidence verified; dynamic applicability remains separate.');return
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=False);(out/'spinit').write_text('* Empty initialization.\n')
    exe=Path(shutil.which(a.ngspice) or a.ngspice).resolve();env=dict(os.environ,SPICE_SCRIPTS=str(out))
    report={'completed':False,'qualified':False,'scope':__doc__,'temperatureSamplesC':[0,25,70],
      'sources':{n:sha(HERE/n) for n in ('device_endpoint_probe.py','ttl7406_probe.py','ttl7406_nominal.cir','ttl7404_nominal.cir','ttl7406_limits.json','d104_limits.json','failure_evidence.py')},
      'runtime':{'path':str(exe),'sha256':sha(exe),'spinitSha256':sha(out/'spinit')},
      'sourceConditions':{'7406':{'url':'https://www.ti.com/lit/ds/symlink/sn7406.pdf','locator':'SDLS031A printed page 3, SN7406 column, DC bounds over 0–70 C; switching bounds apply at 25 C only'},'7404':json.loads((HERE/'d104_limits.json').read_text())['source']},
      'assumptions':{'inputReverseBeta':.01,'temperatureModel':'Unmodified SPICE generic semiconductor temperature laws; endpoints are screens, not validated temperature dependence'},
      'boundary':'No parameter fitting, continuous temperature/process coverage, dynamic qualification, clone equivalence or specimen calibration. D104 limits are tested against a TI 7404-topology proxy. Passing static endpoints cannot admit oscillator or host dynamics.', 'cases':[]}
    try:
        for device,name,circuit,metric,lo,hi in fixtures():
            for temp in report['temperatureSamplesC']:
                folder=out/f'{device}-{name}-{temp}C';folder.mkdir()
                deck='\n'.join(['Static device endpoint screen',*circuit,(HERE/f'ttl{device}_nominal.cir').read_text(),f'Xdut a y vp 0 TTL{device}_NOMINAL input_br=.01',f'.temp {temp}', '.options reltol=1e-8 vntol=1e-10 abstol=1e-15','.control','set numdgt=17','set wr_singlescale','set wr_vecnames','op',f'let observed = {metric}','wrdata trace.txt observed','quit','.endc','.end',''])
                (folder/'probe.cir').write_text(deck)
                r=subprocess.run([str(exe),'-n','-b','probe.cir'],cwd=folder,env=env,capture_output=True,text=True,timeout=30)
                log=r.stdout+r.stderr;(folder/'ngspice.log').write_text(log);r.check_returncode()
                if solver_diagnostic(log):raise ValueError(solver_diagnostic(log))
                rows=(folder/'trace.txt').read_text().splitlines()[1:]
                if len(rows)!=1:raise ValueError('Expected one DC point')
                values=list(map(float,rows[0].split()))
                if len(values)!=2 or not all(map(math.isfinite,values)):raise ValueError('Invalid DC point')
                value=values[1]
                report['cases'].append({'device':device,'name':name,'temperatureC':temp,'metric':metric,'minimum':lo,'maximum':hi,'value':value,'withinLimit':lo<=value<=hi,'directory':folder.name,'artifacts':{n:sha(folder/n) for n in ('probe.cir','ngspice.log','trace.txt')}})
        if sha(exe)!=report['runtime']['sha256']:raise ValueError('Runtime changed')
        report['staticEndpointsPassed']=all(c['withinLimit'] for c in report['cases']);report['completed']=True
    finally:(out/'assessment.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'staticEndpointsPassed':report['staticEndpointsPassed'],'failures':[c for c in report['cases'] if not c['withinLimit']]}))
if __name__=='__main__':main()
