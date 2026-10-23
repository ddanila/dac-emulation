#!/usr/bin/env python3
"""Instrument nonlinear device accumulation on the pinned post-capacitor runtime."""
import argparse,hashlib,json,os,re,shutil,subprocess
from pathlib import Path
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def transform(text):
    pattern=r'(?m)^(\s*)(\()?\*\(([^\n)]+)\)\s*([+-])=\s*([^;]+);'
    inventory=[]
    def replace(m):
        indent,outer,pointer,sign,value=m.groups()
        if outer:
            assert value.rstrip().endswith(')');value=value.rstrip()[:-1]
        if pointer.startswith('ckt->CKTstate'):return m.group(0)
        if not (pointer.startswith('here->') or pointer.startswith('ckt->CKTrhs + ')):
            raise ValueError('Unsupported stamp: '+pointer)
        row=pointer.split(' + ',1)[1] if pointer.startswith('ckt->CKTrhs') else '-1'
        inventory.append({'pointer':pointer,'sign':sign,'value':' '.join(value.split())})
        return f'{indent}RobotronDeviceAdd({pointer},{sign}({value}),{row});'
    result=re.sub(pattern,replace,text)
    if re.search(r'\*\((?:here->|ckt->CKTrhs)[^\n)]*\)\s*[+-]=',result):raise ValueError('Unconverted stamp')
    return 'extern double RobotronDeviceAdd(double *,double,int);\n'+result,inventory

def main():
    p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    base=a.base.resolve();out=a.out.resolve();analog=Path(__file__).resolve().parents[2]
    parent=json.loads((base/'provenance.json').read_text())
    if sha(base/'build/src/ngspice')!=parent['executableSha256']:raise ValueError('Changed base runtime')
    if parent['postcapHeaderSha256']!=sha(analog/'engine-patches/postcap_additions.h'):raise ValueError('Changed base header')
    out.mkdir();shutil.copytree(base/'source',out/'source');header=analog/'engine-patches/device_additions.h'
    shutil.copy2(header,out/'source/src/maths/sparse/device_additions.h')
    path=out/'source/src/maths/sparse/spsmp.c';text=path.read_text()
    needle='#include "postcap_additions.h"';assert text.count(needle)==1
    text=text.replace(needle,needle+'\n#include "device_additions.h"')
    needle='return spGetElement( Matrix->SPmatrix, Row, Col );';assert text.count(needle)==1
    text=text.replace(needle,'return robotron_device_address(spGetElement(Matrix->SPmatrix,Row,Col),Row,Col);')
    needle='if (robotron_cap_apply(&solver)) return 9;';assert text.count(needle)==1
    text=text.replace(needle,'if (device_error || RobotronDeviceEnabled()<0) return 10;\n    '+needle);path.write_text(text)
    changed=['src/maths/sparse/spsmp.c'];inventory={}
    for device in ('bjt','dio'):
        name=f'src/spicelib/devices/{device}/{device}load.c';path=out/'source'/name
        text,inventory[device]=transform(path.read_text());path.write_text(text);changed.append(name)
    (out/'build').mkdir();env=dict(os.environ)
    for key in ('CPPFLAGS','LIBS'):env[key]=parent['buildInputs'][key]
    command=[str(out/'source/configure'),'--prefix='+str(out/'install'),'--without-x','--with-readline=no','--disable-openmp','--disable-klu']
    for name,cmd in [('configure.log',command),('make.log',['make','-j3'])]:
        with (out/name).open('w') as f:subprocess.run(cmd,cwd=out/'build',env=env,stdout=f,stderr=subprocess.STDOUT,check=True)
    report=dict(parent);report.update(deviceBaseProvenanceSha256=sha(base/'provenance.json'),deviceHeaderSha256=sha(header),deviceBuilderSha256=sha(__file__),deviceSources={n:sha(out/'source'/n) for n in changed},deviceOriginalSources={n:sha(base/'source'/n) for n in changed},deviceStampInventory=inventory,executableSha256=sha(out/'build/src/ngspice'),buildInputs={'configure':command,'CPPFLAGS':env['CPPFLAGS'],'LIBS':env['LIBS']})
    (out/'provenance.json').write_text(json.dumps(report,indent=2)+'\n')
    print(out/'provenance.json')
if __name__=='__main__':main()
