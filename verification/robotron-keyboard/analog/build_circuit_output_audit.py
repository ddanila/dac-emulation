#!/usr/bin/env python3
"""Observe pending digital output queues across the circuit, with an external fault."""
import argparse
import json
from pathlib import Path
import build_delayed_corruption as delayed
from ttl7406_probe import sha

EXTRA = r'''
#include "ngspice/evtudn.h"
static void circuit_output_snapshot(FILE *f){
 Evt_Ckt_Data_t *evt=g_mif_info.ckt->evt;
 Evt_Output_Queue_t *q=&evt->queue.output;
 fprintf(f,"C_SUM %d\n",evt->counts.num_outputs);
 for(int index=0;index<evt->counts.num_outputs;index++){
  Evt_Output_Info_t *info=evt->info.output_table[index];
  assert(info->inst_index>=0&&info->inst_index<evt->counts.num_insts);
  assert(info->node_index>=0&&info->node_index<evt->counts.num_nodes);
  Evt_Node_Info_t *node=evt->info.node_table[info->node_index];
  MIFinstance *inst=evt->info.inst_table[info->inst_index]->inst_ptr;
  assert(node->udn_index>=0&&node->udn_index<g_evt_num_udn_types);
  if(strcmp(g_evt_udn_info[node->udn_index]->name,"d")){
   fprintf(stderr,"Unsupported circuit output type\n");exit(2);
  }
  assert(q->current[index]);
  fprintf(f,"C_PORT %d %d %d %d %s %s %d %d %d\n",index,info->inst_index,
   info->node_index,inst==g_mif_info.instance,inst->MIFname,node->name,
   q->pending[index],q->modified[index],q->changed[index]);
  unsigned ordinal=0;
  for(Evt_Output_Event_t *event=*q->current[index];event;event=event->next){
   if(ordinal>=100000){fprintf(stderr,"Circuit event traversal exceeded safety bound\n");exit(2);}
   Digital_t *value=event->value;assert(value);
   fprintf(f,"C_EVENT %d %u %a %a %d %a %d %d\n",index,ordinal++,event->event_time,
    event->posted_time,event->removed,event->removed?event->removed_time:0.0,value->state,value->strength);
  }
 }
}
static void circuit_output_corrupt(void){
 Evt_Ckt_Data_t *evt=g_mif_info.ckt->evt;
 for(int index=0;index<evt->counts.num_outputs;index++){
  Evt_Output_Info_t *info=evt->info.output_table[index];
  MIFinstance *inst=evt->info.inst_table[info->inst_index]->inst_ptr;
  if(inst==g_mif_info.instance)continue;
  evt->queue.output.pending[index]=!evt->queue.output.pending[index];
  fprintf(stderr,"C_CORRUPT pending index=%d instance=%s\n",index,inst->MIFname);
  return;
 }
 fprintf(stderr,"No non-controller output to corrupt\n");exit(2);
}
'''


def instrument(text, fixture):
    text, header = delayed.instrument(text, fixture)
    marker = 'static char *history_snapshot(struct instance *ip,int published){'
    snapshot = 'event_snapshot(ip,f,published);fclose(f);return text;'
    corruption = '  g_mif_info.instance->conn[1]->port[0]->delay+=1e-9;\n  fprintf(stderr,"E_CORRUPT output-delay\\n");'
    if any(header.count(s) != 1 for s in (marker, snapshot, corruption)):
        raise ValueError('Missing circuit output audit hook')
    header = header.replace(marker, EXTRA + '\n' + marker)
    header = header.replace(snapshot, 'event_snapshot(ip,f,published);circuit_output_snapshot(f);fclose(f);return text;')
    return text, header.replace(corruption, '  circuit_output_corrupt();')


def run(a):
    original = delayed.startup.staged.instrument
    try:
        delayed.startup.staged.instrument = instrument
        delayed.startup.staged.run(a)
    finally:
        delayed.startup.staged.instrument = original
    path = a.out / 'build.json'; receipt = json.loads(path.read_text())
    for p in (Path(__file__), Path(delayed.__file__), Path(delayed.startup.__file__), Path(delayed.startup.history.__file__)):
        receipt['sources'][str(p.resolve())] = sha(p)
    receipt['scope'] = 'Combined fixes; every digital output queue from its current pointer, with pending/modified/changed flags. Excludes past/free output lists, instance queues and private HDL events.'
    path.write_text(json.dumps(receipt, indent=2) + '\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('base', 'ngspice-source', 'ngspice-build', 'vpi-include', 'out'):
        p.add_argument('--' + name, type=Path, required=True)
    run(p.parse_args())
