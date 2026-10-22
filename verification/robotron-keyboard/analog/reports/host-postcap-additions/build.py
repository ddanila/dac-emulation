#!/usr/bin/env python3
"""Extend the pinned experimental runtime without changing circuit parameters."""
import argparse,hashlib,json,os,shutil,subprocess
from pathlib import Path
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
base=a.base.resolve();out=a.out.resolve();analog=Path(__file__).resolve().parents[2]
parent=json.loads((base/'provenance.json').read_text())
if sha(base/'build/src/ngspice')!=parent['executableSha256']:raise ValueError('Changed base runtime')
for key,name in [('assemblyHeaderSha256','capacitor_assembly.h'),('budgetHeaderSha256','accepted_budget.h')]:
 if parent[key]!=sha(analog/'engine-patches'/name):raise ValueError('Changed base header')
out.mkdir();shutil.copytree(base/'source',out/'source');header=analog/'engine-patches/postcap_additions.h'
shutil.copy2(header,out/'source/src/maths/sparse/postcap_additions.h')
path=out/'source/src/maths/sparse/spsmp.c';text=path.read_text();needle='#include "capacitor_assembly.h"';assert text.count(needle)==1;path.write_text(text.replace(needle,needle+'\n#include "postcap_additions.h"'))
changed=['src/maths/sparse/spsmp.c']
for device,prefix,conductance in [('res','RES','here->RESconduct'),('sw','SW','g_now')]:
 path=out/f'source/src/spicelib/devices/{device}/{device}load.c';text=path.read_text()
 declaration='extern int RobotronPostCapEnabled(void);\nextern int RobotronPostCapAdd(int,int,double,const double *,const double *);\n'
 index=text.index('\nint\n');text=text[:index]+'\n'+declaration+text[index:]
 marker=f'    {prefix}model *model =';index=text.index(marker)
 text=text[:index]+'    int exact=RobotronPostCapEnabled();\n    double before[4],after[4];\n    if(exact<0)return E_BADPARM;\n'+text[index:]
 # Instrument only DC/transient loading, leaving the AC entry point untouched.
 points=['posPos','negNeg','posNeg','negPos'];statements=[f'            *(here->{prefix}{k}Ptr) '+('+= ' if i<2 else '-= ')+conductance+';' for i,k in enumerate(points)]
 first=min(text.index(x) for x in statements);last=max(text.index(x)+len(x) for x in statements)
 block=text[first:last]
 before='            if(exact) {\n'+''.join(f'                before[{i}]=*here->{prefix}{k}Ptr;\n' for i,k in enumerate(points))+'            }\n'
 after='\n            if(exact) {\n'+''.join(f'                after[{i}]=*here->{prefix}{k}Ptr;\n' for i,k in enumerate(points))+f'                if(RobotronPostCapAdd(here->{prefix}posNode,here->{prefix}negNode,{conductance},before,after))return E_BADPARM;\n'+'            }'
 text=text[:first]+before+block+after+text[last:];path.write_text(text);changed.append(str(path.relative_to(out/'source')))
(out/'build').mkdir();env=dict(os.environ)
for key in ('CPPFLAGS','LIBS'):env[key]=parent['buildInputs'][key]
command=[str(out/'source/configure'),'--prefix='+str(out/'install'),'--without-x','--with-readline=no','--disable-openmp','--disable-klu']
for name,cmd in [('configure.log',command),('make.log',['make','-j3'])]:
 with (out/name).open('w') as f:subprocess.run(cmd,cwd=out/'build',env=env,stdout=f,stderr=subprocess.STDOUT,check=True)
report=dict(parent);report.update(postcapBaseProvenanceSha256=sha(base/'provenance.json'),postcapHeaderSha256=sha(header),postcapBuilderSha256=sha(__file__),postcapSources={n:sha(out/'source'/n) for n in changed},postcapOriginalSources={n:sha(base/'source'/n) for n in changed},executableSha256=sha(out/'build/src/ngspice'),buildInputs={'configure':command,'CPPFLAGS':env['CPPFLAGS'],'LIBS':env['LIBS']})
(out/'provenance.json').write_text(json.dumps(report,indent=2)+'\n')
print(out/'provenance.json')
