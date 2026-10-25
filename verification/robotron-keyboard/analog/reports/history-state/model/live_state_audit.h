#include <assert.h>
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
