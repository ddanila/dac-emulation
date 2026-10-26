#include <assert.h>
static int history_mode(void){
 const char *s=getenv("ROBOTRON_HISTORY_STATE");
 if(!s||!strcmp(s,"off"))return 0;
 if(!strcmp(s,"check"))return 1;
 if(!strcmp(s,"corrupt"))return 2;
 fprintf(stderr,"Invalid ROBOTRON_HISTORY_STATE mode\n");exit(2);
}

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

static char *history_snapshot(struct instance *ip,int published){
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
 fputc('\n',f);event_snapshot(ip,f,published);circuit_output_snapshot(f);fclose(f);return text;
}
static void history_entry(struct instance *ip,const char *phase,double time){
 if(!history_mode())return;
 char *s=history_snapshot(ip,!strcmp(phase,"output-after"));
 fprintf(stderr,"H_BEGIN %s %.17g\n%sH_END\n",phase,time,s);free(s);
}

#include <errno.h>
#include <math.h>
static int history_corruption_due(double time){
 const char *s=getenv("ROBOTRON_HISTORY_CORRUPT_AFTER");
 double after=0;
 if(s){
  char *end;errno=0;after=strtod(s,&end);
  if(errno||end==s||*end||!isfinite(after)||after<0){
   fprintf(stderr,"Invalid history corruption start\n");exit(2);
  }
 }
 if(time<after)return 0;
 fprintf(stderr,"HISTORY_CORRUPTION time=%.17g after=%.17g\n",time,after);
 return 1;
}

static void history_rejected(struct instance *ip,char *before,double time){
 if(!before)return;
 if(history_mode()==2&&history_corruption_due(time)){
  assert(ip->out_ports>0);
  circuit_output_corrupt();
 }
 char *after=history_snapshot(ip,0);int equal=!strcmp(before,after);
 fprintf(stderr,"H_REJECT %.17g equal=%d\n",time,equal);free(before);free(after);
 if(!equal){fprintf(stderr,"Rejected trial changed XSPICE history\n");exit(2);}
}
