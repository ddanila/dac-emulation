#!/usr/bin/env python3
"""Rebuild the selected ADC object exactly to bind existing trace semantics."""
import argparse,json,os,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha

def run(adc,selected,cmpp,source,build,out):
    adc=adc.resolve();selected=selected.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    receipt=json.loads((selected/'build.json').read_text());expected=receipt['objects'][str(adc/'cfunc.o')]
    if sha(adc/'cfunc.o')!=expected or sha(selected/'digital.cm')!=receipt['outputs']['digital.cm']:raise ValueError('Changed selected ADC/model')
    for name in ('cfunc.mod','ifspec.ifs'):shutil.copyfile(adc/name,out/name)
    commands=[[str(cmpp),'-mod'],['cc','-O2','-fPIC','-MMD','-MF',str(out/'headers.d'),'-I'+str(build/'src/include'),'-I'+str(source/'src/include'),'-c',str(out/'cfunc.c'),'-o',str(out/'cfunc.o')]]
    subprocess.run(commands[0],env=dict(os.environ,CMPP_IDIR=str(out),CMPP_ODIR=str(out)),check=True);subprocess.run(commands[1],check=True)
    if (out/'cfunc.c').read_bytes()!=(adc/'cfunc.c').read_bytes() or sha(out/'cfunc.o')!=expected:raise ValueError('Selected ADC object not reproduced exactly')
    text=(out/'cfunc.mod').read_text();logging='''                    if (getenv("ROBOTRON_ADC_TRACE"))
                        cm_message_printf("ADC_CROSS time=%a node=%s value=%a old=%d new=%d", TIME, cm_get_node_name("in", i), INPUT(in[i]), out[i], test);'''
    if text.count('ROBOTRON_ADC_TRACE')!=1 or text.count(logging)!=1:raise ValueError('Changed observational trace guard')
    deps=(out/'headers.d').read_text().replace('\\\n',' ').split(':',1)[1].split();headers={p:sha(Path(p)) for p in deps if Path(p)!=out/'cfunc.c'}
    shutil.copyfile(selected/'build.json',out/'selected-build.json')
    result=dict(controlsPassed=True,generatedSourceExactlyEqual=True,compiledObjectExactlyEqual=True,adcObjectSha256=expected,selectedDigitalSha256=receipt['outputs']['digital.cm'],commands=commands,headers=headers,preprocessor=dict(path=str(cmpp),sha256=sha(cmpp)),compiler=subprocess.check_output(['cc','--version'],text=True),scope='The existing trace flag guards only a diagnostic call in the EVENT changed-value branch, before output assignment/delay handling. It reports sampled threshold decisions, not an independently measured crossing or complete analog-step/rejection history. Multi-bit conversion bypasses this branch; Schmitt unknown decisions can later be suppressed.')
    (out/'assessment.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('adc','selected','cmpp','source','build','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();run(a.adc,a.selected,a.cmpp,a.source,a.build,a.out)
