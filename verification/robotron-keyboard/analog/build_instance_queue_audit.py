#!/usr/bin/env python3
"""Extend circuit output observation to ngspice instance queues and anchors."""
import argparse
import json
from pathlib import Path
import build_circuit_output_audit as circuit
from ttl7406_probe import sha

EXTRA = r'''
static void instance_queue_snapshot(FILE *f){
 Evt_Ckt_Data_t *evt=g_mif_info.ckt->evt;
 Evt_Inst_Queue_t *q=&evt->queue.inst;
 int count=evt->counts.num_insts;
 fprintf(f,"I_SUM %d %a %a %d %d %d\n",count,q->last_time,q->next_time,
  q->num_modified,q->num_pending,q->num_to_call);
 int sizes[]={q->num_modified,q->num_pending,q->num_to_call};
 int *indices[]={q->modified_index,q->pending_index,q->to_call_index};
 for(int list=0;list<3;list++){
  assert(sizes[list]>=0&&sizes[list]<=count);
  for(int ordinal=0;ordinal<sizes[list];ordinal++){
   int index=indices[list][ordinal];assert(index>=0&&index<count);
   fprintf(f,"I_INDEX %d %d %d\n",list,ordinal,index);
  }
 }
 for(int index=0;index<count;index++){
  MIFinstance *inst=evt->info.inst_table[index]->inst_ptr;
  fprintf(f,"I_INST %d %d %s %d %d %d\n",index,inst==g_mif_info.instance,
   inst->MIFname,q->modified[index],q->pending[index],q->to_call[index]);
  Evt_Inst_Event_t **slot=&q->head[index];unsigned ordinal=0;
  int seen_current=0,seen_last=0;
  for(;;){
   if(ordinal>=100000){fprintf(stderr,"Instance queue traversal exceeded safety bound\n");exit(2);}
   int current=slot==q->current[index],last=slot==q->last_step[index];
   seen_current+=current;seen_last+=last;
   fprintf(f,"I_SLOT %d %u %d %d %d\n",index,ordinal,current,last,*slot!=NULL);
   if(!*slot)break;
   fprintf(f,"I_EVENT %d %u %a %a\n",index,ordinal,(*slot)->event_time,(*slot)->posted_time);
   slot=&(*slot)->next;ordinal++;
  }
  if(seen_current!=1||seen_last!=1){fprintf(stderr,"Instance queue anchor outside retained list\n");exit(2);}
 }
}
static void instance_queue_corrupt(void){
 Evt_Ckt_Data_t *evt=g_mif_info.ckt->evt;
 Evt_Inst_Queue_t *q=&evt->queue.inst;
 for(int index=0;index<evt->counts.num_insts;index++){
  MIFinstance *inst=evt->info.inst_table[index]->inst_ptr;
  if(inst==g_mif_info.instance||!q->head[index]||q->current[index]==&q->head[index])continue;
  Evt_Inst_Event_t **slot=&q->head[index];unsigned ordinal=0;
  while(slot!=q->current[index]){
   if(!*slot||ordinal>=100000){fprintf(stderr,"Invalid instance fault anchor\n");exit(2);}
   slot=&(*slot)->next;ordinal++;
  }
  q->current[index]=&q->head[index];
  fprintf(stderr,"C_CORRUPT instance-current index=%d instance=%s from=%u to=0\n",
   index,inst->MIFname,ordinal);
  return;
 }
 fprintf(stderr,"No external consumed instance event to rewind\n");exit(2);
}
'''


def instrument(text, fixture):
    text, header = circuit.instrument(text, fixture)
    marker = 'static char *history_snapshot(struct instance *ip,int published){'
    snapshot = 'circuit_output_snapshot(f);fclose(f);return text;'
    corruption = '  circuit_output_corrupt();'
    if any(header.count(s) != 1 for s in (marker, snapshot, corruption)):
        raise ValueError('Missing instance audit hook')
    old_fault = circuit.EXTRA[circuit.EXTRA.index('static void circuit_output_corrupt(void){'):]
    if header.count(old_fault) != 1: raise ValueError('Missing output fault helper')
    header = header.replace(old_fault, '')
    header = header.replace(marker, EXTRA+'\n'+marker)
    header = header.replace(snapshot, 'circuit_output_snapshot(f);instance_queue_snapshot(f);fclose(f);return text;')
    header = header.replace(corruption, '  instance_queue_corrupt();')
    return text, header


def run(a):
    staged = circuit.delayed.startup.staged
    original = staged.instrument
    try:
        staged.instrument = instrument
        staged.run(a)
    finally:
        staged.instrument = original
    path = a.out/'build.json'; receipt=json.loads(path.read_text())
    for module in (circuit,circuit.delayed,circuit.delayed.startup,circuit.delayed.startup.history):
        p=Path(module.__file__);receipt['sources'][str(p.resolve())]=sha(p)
    p=Path(__file__);receipt['sources'][str(p.resolve())]=sha(p)
    receipt['scope']='Combined fixes, all digital output pending queues, and all instance event lists with current/last-step slot positions, queue clocks, ordered worklists and flags. Excludes freed instance events and private HDL events.'
    path.write_text(json.dumps(receipt,indent=2)+'\n')


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('base','ngspice-source','ngspice-build','vpi-include','out'):
        p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
