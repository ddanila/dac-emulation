#include <assert.h>
#include <stdint.h>
#include "coroutine.h"
#include "icarus_shim.h"
#include "vpi_user.h"
static vpiHandle (*iterate)(PLI_INT32,vpiHandle),(*scan_handle)(vpiHandle);
static PLI_INT32 (*state_vpi_get)(PLI_INT32,vpiHandle);
static char *(*get_str)(PLI_INT32,vpiHandle);
static void (*get_value)(vpiHandle,p_vpi_value);
static void (*get_time)(vpiHandle,p_vpi_time);
static vpiHandle (*put_value)(vpiHandle,p_vpi_value,p_vpi_time,PLI_INT32);
static struct item {char *name;vpiHandle handle;} *items;
static size_t item_count;
static void collect(vpiHandle scope){
 int types[]={vpiReg,vpiNet,vpiIntegerVar,vpiTimeVar,vpiRealVar,vpiMemoryWord};
 for(unsigned i=0;i<sizeof(types)/sizeof(types[0]);i++){
  vpiHandle it=iterate(types[i],scope),h;
  while(it&&(h=scan_handle(it))){
   const char *name=get_str(vpiFullName,h);bool seen=false;
   for(size_t j=0;j<item_count;j++)if(!strcmp(items[j].name,name)){
    assert(items[j].handle==h);seen=true;break;
   }
   if(seen)continue;
   items=realloc(items,(item_count+1)*sizeof(*items));assert(items);
   items[item_count++]=(struct item){strdup(get_str(vpiFullName,h)),h};
  }
 }
 int scopes[]={vpiModule,vpiGenScope,vpiNamedBegin,vpiNamedFork,vpiTask,vpiFunction,vpiMemory};
 for(unsigned i=0;i<sizeof(scopes)/sizeof(scopes[0]);i++){
  vpiHandle it=iterate(scopes[i],scope),h;
  while(it&&(h=scan_handle(it)))collect(h);
 }
}
static int by_name(const void *a,const void *b){return strcmp(((const struct item*)a)->name,((const struct item*)b)->name);}
static char *snapshot(struct instance *ip){
 char *text=NULL;size_t length=0;FILE *f=open_memstream(&text,&length);assert(f);
 struct ng_vvp *ctx=ip->info.handle;
 s_vpi_time now={.type=vpiSimTime};get_time(NULL,&now);
 fprintf(f,"hdl_time %u %u\n",now.high,now.low);
 fprintf(f,"bridge %a %a %a %u %u %d %d\n",ip->info.vtime,ctx->base_time,ctx->tick_length,ctx->in_pending,ctx->out_pending,ctx->stop,ctx->stop_cb!=NULL);
 fprintf(f,"scheduler %d %u %a %a\n",ip->q_index,ip->op_pending,ip->last_step,ip->extra);
 for(int i=0;i<=ip->q_index;i++)fprintf(f,"queue %a %u %d %d\n",ip->q[i].when,ip->q[i].which,ip->q[i].what.state,ip->q[i].what.strength);
 for(unsigned i=0;i<ctx->ins+ctx->outs+ctx->inouts;i++){
  struct ngvp_port *p=ctx->ports+i;
  fprintf(f,"port %u %u %u %u %d %d %d %d\n",i,p->bits,p->flags,p->position,p->previous.aval,p->previous.bval,p->new.aval,p->new.bval);
 }
 for(size_t i=0;i<item_count;i++){
  s_vpi_value val={.format=state_vpi_get(vpiType,items[i].handle)==vpiRealVar?vpiRealVal:vpiBinStrVal};get_value(items[i].handle,&val);
  fprintf(f,"state %s %d ",items[i].name,state_vpi_get(vpiSize,items[i].handle));
  if(val.format==vpiRealVal)fprintf(f,"%a\n",val.value.real);else fprintf(f,"%s\n",val.value.str);
 }
 fclose(f);return text;
}

static int state_mode(void){
 const char *s=getenv("ROBOTRON_LIVE_STATE");
 if(!s||!strcmp(s,"off"))return 0;
 if(!strcmp(s,"observe"))return 1;
 if(!strcmp(s,"check"))return 2;
 if(!strcmp(s,"corrupt"))return 3;
 fprintf(stderr,"Invalid ROBOTRON_LIVE_STATE mode\n");exit(2);
}
static void state_init(struct instance *ip){
 if(item_count)return;
 struct ng_vvp *ctx=ip->info.handle;void *vvp=ctx->vvp_handle;
 #define BIND(name,symbol) name=dlsym(vvp,symbol);assert(name)
 BIND(get_time,"vpi_get_time");BIND(iterate,"vpi_iterate");BIND(scan_handle,"vpi_scan");
 BIND(state_vpi_get,"vpi_get");BIND(get_str,"vpi_get_str");BIND(get_value,"vpi_get_value");BIND(put_value,"vpi_put_value");
 #undef BIND
 collect(NULL);assert(item_count>0);qsort(items,item_count,sizeof(*items),by_name);
 fprintf(stderr,"STATE_INVENTORY items=%zu\n",item_count);
 for(size_t i=0;i<item_count;i++)fprintf(stderr,"STATE_OBJECT %s %d\n",items[i].name,state_vpi_get(vpiSize,items[i].handle));
}
static void state_entry(struct instance *ip,double time){
 if(!state_mode())return;
 state_init(ip);
 char *s=snapshot(ip);
 /* Full snapshots are retained: hashes alone are not the equality oracle. */
 fprintf(stderr,"STATE_ENTRY %.17g\n%sSTATE_END\n",time,s);free(s);
}
static void state_rejected(struct instance *ip,char *before,double time){
 if(!before)return;
 if(state_mode()==3){
  for(size_t i=0;i<item_count;i++)if(state_vpi_get(vpiType,items[i].handle)==vpiReg){
   s_vpi_value v={.format=vpiIntVal,.value.integer=123};put_value(items[i].handle,&v,NULL,vpiNoDelay);break;
  }
 }
 char *after=snapshot(ip);int equal=!strcmp(before,after);
 fprintf(stderr,"STATE_REJECT %.17g equal=%d\n",time,equal);free(before);free(after);
 if(!equal){fprintf(stderr,"Live rejected trial changed internal state\n");exit(2);}
}
