#!/usr/bin/env python3
"""Build an opt-in live d_cosim state observer from the controlled probe inventory."""
import argparse
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


def instrument(text, fixture):
    inventory=fixture[fixture.index('static vpiHandle (*iterate)'):fixture.index('static void *load(')]
    inventory=inventory.replace(' %u %u\\n",ip->q_index,ip->op_pending,ip->last_step,ip->extra,delivered,outputs)',
                                '\\n",ip->q_index,ip->op_pending,ip->last_step,ip->extra)')
    header='''#include <assert.h>
#include <stdint.h>
#include "coroutine.h"
#include "icarus_shim.h"
#include "vpi_user.h"
'''+inventory+'''
static int state_mode(void){
 const char *s=getenv("ROBOTRON_LIVE_STATE");
 if(!s||!strcmp(s,"off"))return 0;
 if(!strcmp(s,"observe"))return 1;
 if(!strcmp(s,"check"))return 2;
 if(!strcmp(s,"corrupt"))return 3;
 fprintf(stderr,"Invalid ROBOTRON_LIVE_STATE mode\\n");exit(2);
}
static void state_init(struct instance *ip){
 if(item_count)return;
 struct ng_vvp *ctx=ip->info.handle;void *vvp=ctx->vvp_handle;
 #define BIND(name,symbol) name=dlsym(vvp,symbol);assert(name)
 BIND(get_time,"vpi_get_time");BIND(iterate,"vpi_iterate");BIND(scan_handle,"vpi_scan");
 BIND(get,"vpi_get");BIND(get_str,"vpi_get_str");BIND(get_value,"vpi_get_value");BIND(put_value,"vpi_put_value");
 #undef BIND
 collect(NULL);assert(item_count>0);qsort(items,item_count,sizeof(*items),by_name);
 fprintf(stderr,"STATE_INVENTORY items=%zu\\n",item_count);
 for(size_t i=0;i<item_count;i++)fprintf(stderr,"STATE_OBJECT %s %d\\n",items[i].name,get(vpiSize,items[i].handle));
}
static void state_entry(struct instance *ip,double time){
 if(!state_mode())return;
 state_init(ip);
 char *s=snapshot(ip);
 /* Full snapshots are retained: hashes alone are not the equality oracle. */
 fprintf(stderr,"STATE_ENTRY %.17g\\n%sSTATE_END\\n",time,s);free(s);
}
static void state_rejected(struct instance *ip,char *before,double time){
 if(!before)return;
 if(state_mode()==3){
  for(size_t i=0;i<item_count;i++)if(get(vpiType,items[i].handle)==vpiReg){
   s_vpi_value v={.format=vpiIntVal,.value.integer=123};put_value(items[i].handle,&v,NULL,vpiNoDelay);break;
  }
 }
 char *after=snapshot(ip);int equal=!strcmp(before,after);
 fprintf(stderr,"STATE_REJECT %.17g equal=%d\\n",time,equal);free(before);free(after);
 if(!equal){fprintf(stderr,"Live rejected trial changed internal state\\n");exit(2);}
}
'''
    header=re.sub(r'\bget\b','state_vpi_get',header)
    marker='static void run(struct instance *ip, ARGS)\n{'
    if text.count(marker)!=1:raise ValueError('Missing scheduler entry')
    text=text.replace(marker,'#include "live_state_audit.h"\n'+marker+'\n    state_entry(ip, TIME);')
    old='''        if (ip->q[i].when > T(1) && ip->q[i].when < TIME &&
            !cm_analog_set_temp_bkpt(ip->q[i].when))
            return;'''
    new='''        if (ip->q[i].when > T(1) && ip->q[i].when < TIME) {
            char *before=state_mode()>=2?snapshot(ip):NULL;
            if (!cm_analog_set_temp_bkpt(ip->q[i].when)) {
                state_rejected(ip,before,TIME);
                return;
            }
            free(before);
        }'''
    if text.count(old)!=1:raise ValueError('Missing input barrier')
    return text.replace(old,new),header


def run(a):
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    base=json.loads((a.base/'build.json').read_text())
    for name,digest in base['outputs'].items():
        if sha(a.base/name)!=digest:raise ValueError('Changed base model output')
    source=a.ngspice_source.resolve();build=a.ngspice_build.resolve()
    folder=out/'d_cosim';folder.mkdir()
    upstream=HERE/'fixtures/ngspice-47/d_cosim.mod'
    if sha(upstream)!='aa31bc8cf686914b3f667c9790aae4b79115a6f3b0e786732358a63df9340207':raise ValueError('Changed scheduler fixture')
    staging=out/'src/xspice/icm/digital/d_cosim';staging.mkdir(parents=True)
    shutil.copyfile(upstream,staging/'cfunc.mod')
    patches=['ngspice-47-strict-time-diagnostic.patch','cosim-input-barrier.patch']
    for patch in patches:subprocess.run(['patch','-d',str(out),'-p1','-i',str(HERE/'engine-patches'/patch)],check=True,capture_output=True)
    shutil.copyfile(a.base/'src/xspice/icm/digital/d_cosim/ifspec.ifs',folder/'ifspec.ifs')
    text,header=instrument((staging/'cfunc.mod').read_text(),(HERE/'fixtures/cosim_state_harness.c').read_text())
    (folder/'cfunc.mod').write_text(text);(folder/'live_state_audit.h').write_text(header)
    cmpp=build/'src/xspice/cmpp/cmpp'
    subprocess.run([str(cmpp),'-mod'],env=dict(os.environ,CMPP_IDIR=str(folder),CMPP_ODIR=str(folder)),check=True)
    includes=[build/'src/include',source/'src/include',source/'src/xspice/verilog',a.vpi_include]
    obj=folder/'cfunc.o'
    subprocess.run(['cc','-O2','-fPIC',*[f'-I{p}' for p in includes],'-c',str(folder/'cfunc.c'),'-o',str(obj)],check=True)
    objects=[Path(p) for p in base['reusedObjects']]
    for p in objects:
        if sha(p)!=base['reusedObjects'][str(p)]:raise ValueError('Changed reused object')
    objects += [a.base/'src/xspice/icm/digital'/n/'cfunc.o' for n in ('dac_bridge','adc_bridge')]
    flags=['-bundle','-flat_namespace','-undefined','suppress'] if platform.system()=='Darwin' else ['-shared']
    subprocess.run(['cc',*flags,*map(str,objects+[obj]),'-lm','-o',str(out/'digital.cm')],check=True)
    lines=(a.base/'spinit').read_text().splitlines();indices=[i for i,l in enumerate(lines) if l.startswith('codemodel ') and l.endswith('/digital.cm')]
    if len(indices)!=1:raise ValueError('Ambiguous digital model')
    lines[indices[0]]='codemodel '+str(out/'digital.cm');(out/'spinit').write_text('\n'.join(lines)+'\n')
    receipt={'baseBuildSha256':sha(a.base/'build.json'),'sources':{str(p):sha(p) for p in [Path(__file__),upstream,HERE/'fixtures/cosim_state_harness.c',*[HERE/'engine-patches'/p for p in patches[:2]]]},
             'objects':{str(p):sha(p) for p in objects},'outputs':{n:sha(out/n) for n in ('digital.cm','spinit','d_cosim/cfunc.mod','d_cosim/live_state_audit.h')},
             'qualified':False,'scope':'Single Icarus instance; full exposed VPI/bridge/input-queue snapshots at scheduler entry and exact comparison around input-barrier rejection. No complete pending-event-queue or general rollback claim.'}
    (out/'build.json').write_text(json.dumps(receipt,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('base','ngspice-source','ngspice-build','vpi-include','out'):p.add_argument('--'+n,type=Path,required=True)
    run(p.parse_args())
