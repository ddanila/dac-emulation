#!/usr/bin/env python3
"""Build an opt-in observer of initialized d_cosim/XSPICE history transitions."""
import argparse
import json
from pathlib import Path
import build_live_state_audit as builder
from ttl7406_probe import sha

HEADER=r'''#include <assert.h>
static int history_mode(void){
 const char *s=getenv("ROBOTRON_HISTORY_STATE");
 if(!s||!strcmp(s,"off"))return 0;
 if(!strcmp(s,"check"))return 1;
 if(!strcmp(s,"corrupt"))return 2;
 fprintf(stderr,"Invalid ROBOTRON_HISTORY_STATE mode\n");exit(2);
}
static char *history_snapshot(struct instance *ip){
 char *text=NULL;size_t length=0;FILE *f=open_memstream(&text,&length);assert(f);
 fprintf(f,"H_SCHED %a %a %a %d %u\n",ip->info.vtime,ip->last_step,ip->extra,ip->q_index,ip->op_pending);
 for(int i=0;i<=ip->q_index;i++)fprintf(f,"H_QUEUE %d %a %u %d %d\n",i,ip->q[i].when,ip->q[i].which,ip->q[i].what.state,ip->q[i].what.strength);
 unsigned sizes[]={ip->in_ports+ip->inout_ports,ip->out_ports+ip->inout_ports};
 for(int tag=0;tag<2;tag++)for(int previous=0;previous<2;previous++){
  Digital_t *values=cm_event_get_ptr(tag,previous);assert(values);
  fprintf(f,"H_ARRAY %d %d %u",tag,previous,sizes[tag]);
  for(unsigned i=0;i<sizes[tag];i++)fprintf(f," %d:%d",values[i].state,values[i].strength);
  fputc('\n',f);
 }
 /* Pending storage is not initialized until accept_output has seeded it. */
 fprintf(f,"H_PENDING %u",ip->op_pending?sizes[1]:0);
 if(ip->op_pending)for(unsigned i=0;i<sizes[1];i++)fprintf(f," %d:%d",ip->out_vals[i].state,ip->out_vals[i].strength);
 fputc('\n',f);fclose(f);return text;
}
static void history_entry(struct instance *ip,const char *phase,double time){
 if(!history_mode())return;
 char *s=history_snapshot(ip);
 fprintf(stderr,"H_BEGIN %s %.17g\n%sH_END\n",phase,time,s);free(s);
}
static void history_rejected(struct instance *ip,char *before,double time){
 if(!before)return;
 if(history_mode()==2){
  Digital_t *values=cm_event_get_ptr(0,0);assert(ip->in_ports>0);
  values[0].state=values[0].state==ZERO?ONE:ZERO;
 }
 char *after=history_snapshot(ip);int equal=!strcmp(before,after);
 fprintf(stderr,"H_REJECT %.17g equal=%d\n",time,equal);free(before);free(after);
 if(!equal){fprintf(stderr,"Rejected trial changed XSPICE history\n");exit(2);}
}
'''


def instrument(text, fixture):
    replacements={
        '/* Called at end of simulation run to free memory. */':'#include "live_state_audit.h"\n\n/* Called at end of simulation run to free memory. */',
        '    delay = PARAM(delay) - (TIME - ip->info.vtime);':'    history_entry(ip,"output-before",TIME);\n    delay = PARAM(delay) - (TIME - ip->info.vtime);',
        '    ip->op_pending = 0;\n}':'    ip->op_pending = 0;\n    history_entry(ip,"output-after",TIME);\n}',
        '    (*ip->info.step)(&ip->info);':'    history_entry(ip,"advance-before",TIME);\n    (*ip->info.step)(&ip->info);\n    history_entry(ip,"advance-after",TIME);',
        '    /* Check for pending output. */':'    history_entry(ip,"callback-entry",TIME);\n    /* Check for pending output. */',
        '    } else if (CALL_TYPE == STEP_PENDING) {':'        history_entry(ip,"event-after",TIME);\n    } else if (CALL_TYPE == STEP_PENDING) {',
        'static void run(struct instance *ip, ARGS)\n{':'static void run(struct instance *ip, ARGS)\n{\n    history_entry(ip,"run-entry",TIME);',
        '''        if (ip->q[i].when > T(1) && ip->q[i].when < TIME &&
            !cm_analog_set_temp_bkpt(ip->q[i].when))
            return;''':'''        if (ip->q[i].when > T(1) && ip->q[i].when < TIME) {
            char *before=history_mode()?history_snapshot(ip):NULL;
            if (!cm_analog_set_temp_bkpt(ip->q[i].when)) {
                history_rejected(ip,before,TIME);
                return;
            }
            free(before);
        }'''}
    for old,new in replacements.items():
        if text.count(old)!=1:raise ValueError('Missing or ambiguous history hook: '+old)
        text=text.replace(old,new)
    return text,HEADER


def run(a):
    original=builder.instrument
    try:
        builder.instrument=instrument;builder.run(a)
    finally:builder.instrument=original
    path=a.out/'build.json';receipt=json.loads(path.read_text())
    receipt['sources'][str(Path(__file__).resolve())]=sha(Path(__file__))
    receipt['scope']='Initialized d_cosim callbacks: current/previous input/output history, meaningful pending output and input queue. No HDL event queue, initialization, output scheduling flags or general rollback qualification.'
    path.write_text(json.dumps(receipt,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('base','ngspice-source','ngspice-build','vpi-include','out'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
