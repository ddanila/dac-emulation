#!/usr/bin/env python3
"""Qualify complete bounded all-signal captures, including every prior layer."""
from scope_signal_fault_core_review import *
from scope_signal_fault_review import inventory


def require_port_source(prior):
    required={'port-payload-'+n+'-corrupt' for n in ('index','direction','bit-index','width','parent','name-pointer','net-reference','bit-parent','readiness')}
    required.update('callback-list-'+n+'-corrupt' for n in ('user','object','function','link'))
    if not prior.get('controlsPassed') or not prior.get('reviewCompleted') or not prior.get('firmwareRecordsExactlyEqual') or not required.issubset(prior.get('negativeControls',{})):
        raise ValueError('Need fully reviewed port-payload predecessor, not startup-only controls')
    observed=prior.get('observedState',{});boundaries=observed.get('boundaries',0);metadata=observed.get('scopeMetadata',{})
    if set(prior.get('comparisons',{}))!={'disabledBaseline','enabledObserver'} or boundaries<=0:
        raise ValueError('Missing predecessor normal sample comparisons or boundaries')
    if metadata.get('snapshots')!=2*boundaries or metadata.get('scopes',0)<=0 or metadata.get('boundSignals',0)<=0:
        raise ValueError('Incomplete predecessor metadata coverage')
    if metadata.get('ports',0)<=0 or metadata.get('portBits',0)<=0:raise ValueError('Missing predecessor port population')
    for prefix in ('metadata','reference','port'):
        if metadata.get(prefix+'Full',0)<=0 or metadata.get(prefix+'Full',0)+metadata.get(prefix+'Reused',0)!=metadata['snapshots']:
            raise ValueError('Incomplete predecessor compact reconstruction')


def assess(root,producer):
    names=('baseline','off','observe','callback-list-user-corrupt','callback-list-object-corrupt','callback-list-function-corrupt','callback-list-link-corrupt')+('scope-signal-signed-corrupt', 'scope-signal-range-corrupt', 'scope-signal-node-corrupt', 'scope-signal-name-corrupt', 'scope-signal-cache-corrupt', 'scope-signal-scope-corrupt')
    if any(not (root/n/'run.json').is_file() for n in names):raise ValueError('Need complete normal and fault campaign; startup preflight is insufficient')
    runs={n:json.loads((root/n/'run.json').read_text()) for n in names}
    profile=compiled_contract((root/'baseline/io.vvp').read_text())
    base=runs['baseline'];prior=json.loads((root/'baseline-assessment.json').read_text())
    if not prior.get('controlsPassed') or prior['receipts']['off']!=sha(root/'baseline/run.json'):raise ValueError('Unreviewed baseline')
    require_port_source(prior)
    if base['mode']!='off' or base['endSeconds']!=20e-6:raise ValueError('Changed baseline scope')
    identities=verify_symbols(root,runs)
    def dep(run,name):
        matches=[d for d in run['externalDependencies'] if Path(d['path']).name==name]
        if len(matches)!=1:raise ValueError('Ambiguous dependency')
        return matches[0]
    replaced={'ivlng.so','ivlng.vpi','libvvp.so','system.vpi'}
    def shared(run):return {d['path']:d['sha256'] for d in run['externalDependencies'] if Path(d['path']).name not in replaced}
    if shared(base)!=shared(runs['off']):raise ValueError('Changed non-candidate runtime')
    for filename,outputs in [('bridge-build.json',('ivlng.so','ivlng.vpi')),('icarus-build.json',('vvp/libvvp.so','vpi/system.vpi'))]:
        build=json.loads((root/filename).read_text())
        for name in outputs:
            if dep(runs['off'],Path(name).name)['sha256']!=build['outputs'][name]:raise ValueError('Unmatched built runtime')
    deck=(root/'baseline/io.cir').read_text()
    for name in ('ivlng.so','ivlng.vpi','libvvp.so'):
        old,new=dep(base,name),dep(runs['off'],name)
        if old['path']==new['path'] or deck.count(old['path'])!=1:raise ValueError('Missing distinct candidate runtime')
        deck=deck.replace(old['path'],new['path'])
    original=(root/'baseline/io.vvp').read_text();marker=':vpi_module "'+dep(base,'system.vpi')['path']+'";'
    if original.count(marker)!=1:raise ValueError('Changed system module placement')
    vvp=original.replace(marker,':vpi_module "'+dep(runs['off'],'system.vpi')['path']+'";')
    startup=startup_identity(root/'baseline/ngspice.log');scans={};receipts={}
    for mode,r in runs.items():
        folder=root/mode;negative=mode not in ('baseline','off','observe')
        if not r['completed'] or r.get('error') or r['exitCode']!=(2 if negative else 0) or r['log']['exitCode']!=r['exitCode'] or r['expectedExitCode']!=r['exitCode']:raise ValueError('Incomplete or wrong termination')
        if r['runtime']!=base['runtime'] or r['endSeconds']!=base['endSeconds']:raise ValueError('Changed runtime/window')
        if mode!='baseline':
            if r.get('startupOnly') is not False:raise ValueError('Startup-only preflight is not an operational campaign')
            if r.get('captureTimeoutSeconds')!=3300:raise ValueError('Changed callback capture budget')
            if r.get('compiledThreadProfile')!=profile or r.get('threadContractSourceSha256')!=sha(Path(board_thread_contract.__file__)):raise ValueError('Changed compiled thread contract')
            if r['mode']!=mode or r['producerSha256']!=sha(producer):raise ValueError('Changed producer/mode')
            for key,path in [('baselineReceiptSha256','baseline/run.json'),('baselineAssessmentSha256','baseline-assessment.json'),('bridgeBuildSha256','bridge-build.json'),('icarusBuildSha256','icarus-build.json'),('symbolReceiptSha256','symbols.json')]:
                if r[key]!=sha(root/path):raise ValueError('Changed '+key)
            expected=dict(base['environment'],ROBOTRON_DISPLAY_MODULE=dep(runs['off'],'system.vpi')['path'],ROBOTRON_PRIVATE_DISPLAY=mode)
            if r['environment']!=expected or r['externalDependencies']!=runs['off']['externalDependencies']:raise ValueError('Changed matched control')
            if r.get('runtimeEnvironment')!={'SPICE_SCRIPTS':str(Path(base['runtime']['spinit']['path']).parent)}:raise ValueError('Missing XSPICE selection')
            if (folder/'io.cir').read_text()!=deck or (folder/'io.vvp').read_text()!=vvp:raise ValueError('Changed circuit or HDL beyond runtime substitutions')
        if set(r['inputs'])!=set(base['inputs']):raise ValueError('Changed inputs')
        for name,h in r['inputs'].items():
            if sha(folder/name)!=h or (name=='s600.hex' and h!=base['inputs'][name]):raise ValueError('Changed input/firmware')
        for name,h in [('waveform.raw',r['storage']['waveform.raw']['sha256']),('ngspice.log',r['log']['sha256'])]:
            if logical_sha(folder/name)!=h:raise ValueError('Changed output')
        if not negative:
            if startup_identity(folder/'ngspice.log')!=startup:raise ValueError('Changed initialized models')
        else:
            early=[line for line in records(folder/'ngspice.log',('HISTORY_INIT ','Instance: ')) if line.startswith('HISTORY_INIT ') or 'DAC_ANCHORED enabled' in line]
            if early!=startup[:len(early)]:raise ValueError('Changed early initialization diagnostics')
        if not negative:
            scans[mode]=complete(folder/'ngspice.log')
            if not scans[mode]['latchesMatch']:raise ValueError('Invalid firmware continuation')
        if not negative and not any(records(folder/'ngspice.log',('FIRST_FETCH ',))):raise ValueError('Missing firmware execution')
        receipts[mode]=sha(folder/'run.json')
    for mode in ('baseline','off'):
        if next(records(root/mode/'ngspice.log',('VB_','VA_','VF_','VD_','VJ_','VR_','VE_','VP_','VW_','VS_','VAP_','VPR_','VI_','VIQ_','VIF_','VT_','VTQ_','VWE_','VTC_','VSC_','VCO_','VAC_','VAR_','VND_','VNG_','VWD_','VSD_','VNT_','VXD_','VXM_','VGD_','VAD_','VRE_','VWC_','VCD_','VRX_','VIX_','VLD_','VLB_','VHB_','VSH_','VSL_','VSM_','VSMR_','VSMD_','VSMRD_','VPP_','VPPD_','VSA_','VSAD_')),None) is not None:raise ValueError('Disabled observer emitted records')
    contract=port_contract((root/'baseline/io.vvp').read_text())
    observed=inventory(root/'observe/ngspice.log',identities,contract=contract,compiled=(root/'baseline/io.vvp').read_text())
    if observed['scopeCount']!=len(analyze((root/'baseline/io.vvp').read_text())['scopes']):raise ValueError('Scope inventory differs from compiled board')
    expected={}
    for line in (root/'baseline/io.vvp').read_text().splitlines():
        if ' .event' not in line:continue
        kind=3 if ' .event/or ' in line else 2 if ' .event anyedge,' in line else 1
        expected[kind]=expected.get(kind,0)+1
    actual={}
    # The native counts are checked in each boundary through a fixed event-kind layout.
    for kind,count in observed['waitEventKinds'].items():actual[int(kind)]=count
    if actual!=expected:raise ValueError('Wait-event inventory differs from compiled board')
    negatives={mode:inventory(root/mode/'ngspice.log',identities,fault_type=mode.removesuffix('-corrupt'),contract=contract,compiled=(root/'baseline/io.vvp').read_text()) for mode in ('callback-list-user-corrupt','callback-list-object-corrupt','callback-list-function-corrupt','callback-list-link-corrupt')+('scope-signal-signed-corrupt', 'scope-signal-range-corrupt', 'scope-signal-node-corrupt', 'scope-signal-name-corrupt', 'scope-signal-cache-corrupt', 'scope-signal-scope-corrupt')}
    comparisons={}
    for label,left,right in [('disabledBaseline','baseline','off'),('enabledObserver','off','observe')]:
        comparisons[label]=compare_raw(root/left/'waveform.raw',root/right/'waveform.raw',[scans[n]['count'] for n in (left,right)],20e-6,exact=True)
        if not equal(root/left/'ngspice.log',root/right/'ngspice.log',FIRMWARE):raise ValueError('Changed firmware continuation')
    return {'compiledThreadProfile':profile,'reviewCompleted':True,'qualified':False,'controlsPassed':True,'comparisons':comparisons,'firmwareRecordsExactlyEqual':True,
            'observedState':observed,'negativeControls':negatives,'receipts':receipts,
            'scope':'Complete 20-us service fixture with reset at 1 us. Every preceding state layer, reconstructed dense scope metadata/reference image and admitted scope/signal ownership is reviewed at each boundary. Dense comparisons preserve exact restoration despite compact log output. All native port and bit identities bind to compiled declarations at every snapshot. Every registered vector signal binds to native owners/nets and compiled name/class/signedness/range. Non-bridge signedness/range faults and node/name/cache/scope refusals restore complete state while bridge admission remains unchanged. Every normal waveform sample and firmware record must match baseline and disabled controls exactly. Later signal faults, remaining intern payloads and general rollback remain separate.',
            'notEstablished':['Referenced operand objects, nonempty event-control payloads and scope intern contents and deep context/object/callback/fanout referents','Reachable detached/deferred-deletion paths, freed-storage equivalence or general rollback','Full post-reset/startup/repeat/supply recovery qualification']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('root','producer','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();result=assess(a.root,a.producer)
    with a.out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
