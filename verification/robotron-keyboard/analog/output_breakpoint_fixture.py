#!/usr/bin/env python3
"""Exercise output-driven truncation using autonomous delayed HDL transitions."""
import argparse,json,shutil,subprocess,time
from pathlib import Path
from audit_log import records
from eval_cache_benchmark import external_dependencies,verify_dependencies
from ngspice_runtime import identify,verify
from output_breakpoint_review import branches
from raw_pair_review import compare_raw
from raw_waveform import header,rows
from staged_output_review import runtime_summary
from ttl7406_probe import sha
from event_state_review import check
HERE=Path(__file__).resolve().parent
MODES=('baseline','off','observe','fail-once')
END=400e-9
EXPECTED=['PROBE_EDGE 53000 1','PROBE_EDGE 131000 0','PROBE_EDGE 197000 1','PROBE_EDGE 301000 0']


def deck(libraries):
    paths={k:v['path'] for k,v in libraries.items()}
    if set(paths)!={'shim','libvvp','vpi'} or any('"' in p or '\n' in p for p in paths.values()):raise ValueError('Invalid bridge paths')
    return f'''Autonomous HDL output timing control
Vin in 0 0
Ain [in] [din] adc
.model adc adc_bridge(in_low=0.8 in_high=2.0)
Ahdl [din] [dq] hdl
.model hdl d_cosim simulation="{paths['shim']}" sim_args=["io.vvp"] delay=1n
+ lib_args=["{paths['libvvp']}" "{paths['vpi']}"]
Aout [dq] [out] dac
.model dac dac_bridge(out_low=0 out_high=5 t_rise=1n t_fall=1n)
Rload out 0 1k
.save v(out)
.tran 10n 400n 0 80n
.control
set filetype=binary
run waveform.raw
quit
.endc
.end
'''


def assess(root):
    counts={};coverage={};sample_errors={};rs={m:json.loads((root/m/'run.json').read_text()) for m in MODES}
    reference=rs['baseline'];bridge=json.loads((root/'bridge.json').read_text())
    for mode,r in rs.items():
        folder=root/mode
        if r['exitCode']!=0 or r['inputs']!=reference['inputs'] or r['externalDependencies']!=reference['externalDependencies']:raise ValueError('Failed or mismatched control')
        build=json.loads((root/('baseline-build.json' if mode=='baseline' else 'candidate-build.json')).read_text())
        if r['runtime']['executable']!=reference['runtime']['executable']:raise ValueError('Changed executable')
        old,new=reference['runtime']['codeModels'],r['runtime']['codeModels']
        if len(old)!=len(new):raise ValueError('Changed model inventory')
        for a,b in zip(old,new):
            if Path(a['path']).name=='digital.cm':
                if b['sha256']!=build['outputs']['digital.cm']:raise ValueError('Wrong digital model')
            elif a!=b:raise ValueError('Changed unrelated model')
        expected={'ROBOTRON_HISTORY_INIT':'on','ROBOTRON_STAGED_OUTPUT':'on','ROBOTRON_HISTORY_STATE':'off','ROBOTRON_OUTPUT_BREAKPOINT':'off' if mode=='baseline' else mode}
        if r['environment']!=expected:raise ValueError('Changed control environment')
        if (folder/'io.cir').read_text()!=deck(bridge['libraries']):raise ValueError('Changed stimulus')
        if set(r['files'])!={'io.cir','io.vvp','ngspice.log','waveform.raw'} or any(r['files'][n]!=h for n,h in r['inputs'].items()):raise ValueError('Missing or mismatched retained inputs')
        for n,h in r['files'].items():
            if sha(folder/n)!=h:raise ValueError('Changed retained file')
        summary=runtime_summary(folder/'ngspice.log')
        if summary['count'] is None or summary['diagnostic'] or summary['sorry']:raise ValueError('Incomplete simulation')
        counts[mode]=summary['count']
        error=0.
        with (folder/'waveform.raw').open('rb') as stream:
            names,declared=header(stream)
            if names!=['time','v(out)']:raise ValueError('Changed observation scope')
            for t,value in rows(stream,len(names),summary['count']):
                expected=0.
                for edge_ns,high in [(53,True),(131,False),(197,True),(301,False)]:
                    start=(edge_ns+1)*1e-9
                    if t<start:break
                    fraction=min(1.,max(0.,(t-start)/1e-9))
                    expected=5*(fraction if high else 1-fraction)
                error=max(error,abs(value-expected))
        sample_errors[mode]=error
        if list(records(folder/'ngspice.log',('PROBE_EDGE ',)))!=EXPECTED:raise ValueError('Lost, duplicated or changed HDL transitions')
        coverage[mode]=branches(records(folder/'ngspice.log',('OUTPUT_BKPT',)),'off' if mode=='baseline' else mode)
    comparisons={}
    for label,a,b,exact in [('disabledBaseline','baseline','off',True),('observer','off','observe',True),('forcedFailure','off','fail-once',False)]:
        comparisons[label]=compare_raw(root/a/'waveform.raw',root/b/'waveform.raw',[counts[a],counts[b]],END,exact=exact)
    if not coverage['observe']['branchExercised'] or not coverage['fail-once']['injectionExercised'] or not coverage['fail-once']['recoveryRequests']:
        raise ValueError('Targeted recovery control did not execute')
    return {'completed':True,'qualified':False,'coverage':coverage,'comparisons':comparisons,'hdlTransitions':EXPECTED,'analyticRampMaximumSampleErrorsVolts':sample_errors,
            'sampleOracleScope':'Known HDL transitions plus 1-ns bridge delay and 1-ns ideal DAC ramp, evaluated only at retained samples; no intersample guarantee.',
            'scope':'Autonomous delayed-output diagnostic, with real ngspice/Icarus execution and an artificial failed initial breakpoint. No keyboard firmware, input perturbation, private-event rollback, numerical convergence or board qualification.'}


def run(a):
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    shutil.copyfile(a.bridge,out/'bridge.json');bridge=json.loads(a.bridge.read_text())
    for item in bridge['libraries'].values():
        if sha(Path(item['path']))!=item['sha256']:raise ValueError('Changed bridge')
    shutil.copyfile(HERE/'fixtures/output_breakpoint.v',out/'io.v')
    subprocess.run(['iverilog','-g2012','-s','delayed_output','-o',str(out/'io.vvp'),str(out/'io.v')],check=True)
    compiler=shutil.which('iverilog');(out/'compiler.json').write_text(json.dumps({'path':compiler,'sha256':sha(Path(compiler))},indent=2)+'\n')
    for name,model in [('baseline',a.baseline_models),('candidate',a.models)]:
        b=json.loads((model/'build.json').read_text())
        for n,h in b['outputs'].items():
            if sha(model/n)!=h:raise ValueError('Changed model build')
        shutil.copyfile(model/'build.json',out/(name+'-build.json'))
    for mode in MODES:
        folder=out/mode;folder.mkdir();shutil.copyfile(out/'io.vvp',folder/'io.vvp');(folder/'io.cir').write_text(deck(bridge['libraries']))
        runtime,env=identify(a.runtime,(a.baseline_models if mode=='baseline' else a.models)/'spinit')
        for k in list(env):
            if k.startswith('ROBOTRON_'):del env[k]
        env.update(ROBOTRON_HISTORY_INIT='on',ROBOTRON_STAGED_OUTPUT='on',ROBOTRON_HISTORY_STATE='off',ROBOTRON_OUTPUT_BREAKPOINT='off' if mode=='baseline' else mode)
        dependencies=external_dependencies(folder,{'deck':'io.cir','inputs':['io.vvp']})
        inputs={n:sha(folder/n) for n in ('io.cir','io.vvp')};start=time.monotonic()
        with (folder/'ngspice.log').open('w') as log:
            p=subprocess.run([runtime['executable']['path'],'-n','-b','io.cir'],cwd=folder,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=30)
        verify(runtime);verify_dependencies(dependencies)
        if inputs!={n:sha(folder/n) for n in inputs}:raise ValueError('Changed inputs')
        r={'exitCode':p.returncode,'runtime':runtime,'environment':{k:v for k,v in env.items() if k.startswith('ROBOTRON_')},'externalDependencies':dependencies,
           'inputs':inputs,'elapsedSeconds':time.monotonic()-start,'files':{n:sha(folder/n) for n in ('io.cir','io.vvp','ngspice.log','waveform.raw')}}
        (folder/'run.json').write_text(json.dumps(r,indent=2)+'\n')
    result=assess(out);(out/'assessment.json').write_text(json.dumps(result,indent=2)+'\n')
    names=('output_breakpoint_fixture.py','fixtures/output_breakpoint.v','build_output_breakpoint_probe.py','output_breakpoint_review.py','raw_pair_review.py','audit_log.py','staged_output_review.py')
    manifest={'files':{str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file()},'sources':{n:sha(HERE/n) for n in names}}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--verify',action='store_true')
    for name in ('bridge','baseline-models','models','runtime'):p.add_argument('--'+name,type=Path)
    a=p.parse_args()
    if a.verify:
        check(a.out)
        if assess(a.out)!=json.loads((a.out/'assessment.json').read_text()):raise ValueError('Stale assessment')
        print('Complete targeted output recovery evidence verified; broader qualification remains open.')
    else:
        if any(getattr(a,n) is None for n in ('bridge','baseline_models','models','runtime')):p.error('Need bridge, both model builds and runtime')
        run(a)
