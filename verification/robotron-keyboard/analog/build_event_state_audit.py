#!/usr/bin/env python3
"""Extend the live history observer with controller output scheduling state."""
import argparse
import json
from pathlib import Path
import build_history_audit as history
from ttl7406_probe import sha
BASE_INSTRUMENT=history.instrument
EXTRA=r'''
#include "ngspice/mif.h"
#include "ngspice/evt.h"
static void event_snapshot(struct instance *ip,FILE *f,int published){
 Evt_Output_Queue_t *queue=&g_mif_info.ckt->evt->queue.output;
 fprintf(f,"E_SUM %a %a %d %d %d\n",queue->last_time,queue->next_time,queue->num_modified,queue->num_pending,queue->num_changed);
 unsigned counts[]={ip->out_ports,ip->inout_ports};
 for(unsigned connection=1;connection<=2;connection++)for(unsigned i=0;i<counts[connection-1];i++){
  Mif_Port_Data_t *port=g_mif_info.instance->conn[connection]->port[i];
  int index=port->evt_data.output_index;assert(index>=0);
  Evt_Output_Event_t *first=*queue->current[index];unsigned count=0;
  for(Evt_Output_Event_t *event=first;event;event=event->next){
   if(++count>100000){fprintf(stderr,"Output event traversal exceeded safety bound\n");exit(2);}
  }
  int valid=published&&port->changed;
  Digital_t value={0,0};if(valid)value=*(Digital_t*)port->output.pvalue;
  fprintf(f,"E_PORT %u %u %d %d %a %d %d %d %u\n",connection,i,index,port->changed,port->delay,valid,value.state,value.strength,count);
  unsigned ordinal=0;
  for(Evt_Output_Event_t *event=first;event;event=event->next){
   Digital_t *value=event->value;
   fprintf(f,"E_ITEM %d %u %a %a %d %a %d %d\n",index,ordinal++,event->event_time,event->posted_time,event->removed,event->removed?event->removed_time:0.0,value->state,value->strength);
  }
 }
}
'''


def instrument(text,fixture):
    text,header=BASE_INSTRUMENT(text,fixture)
    header=header.replace('static char *history_snapshot(struct instance *ip){',EXTRA+'\nstatic char *history_snapshot(struct instance *ip,int published){')
    header=header.replace("fputc('\\n',f);fclose(f);return text;", "fputc('\\n',f);event_snapshot(ip,f,published);fclose(f);return text;")
    header=header.replace('history_snapshot(ip)', 'history_snapshot(ip,0)')
    header=header.replace('char *s=history_snapshot(ip,0);','char *s=history_snapshot(ip,!strcmp(phase,"output-after"));')
    old='''  Digital_t *values=cm_event_get_ptr(0,0);assert(ip->in_ports>0);
  values[0].state=values[0].state==ZERO?ONE:ZERO;'''
    new='''  assert(ip->out_ports>0);
  g_mif_info.instance->conn[1]->port[0]->delay+=1e-9;
  fprintf(stderr,"E_CORRUPT output-delay\\n");'''
    if header.count(old)!=1:raise ValueError('Missing negative history control')
    header=header.replace(old,new)
    text=text.replace('history_snapshot(ip)', 'history_snapshot(ip,0)')
    return text,header


def run(a):
    original=history.instrument
    try:history.instrument=instrument;history.run(a)
    finally:history.instrument=original
    path=a.out/'build.json';receipt=json.loads(path.read_text())
    receipt['sources'][str(Path(__file__).resolve())]=sha(Path(__file__))
    receipt['scope']='Initialized callback histories plus controller-port changed flags, delays, assigned output values after publication, and complete lists starting at each controller output queue current pointer. Excludes other models, past/free queue history and private HDL events.'
    path.write_text(json.dumps(receipt,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('base','ngspice-source','ngspice-build','vpi-include','out'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
