/* Real Icarus state around the pinned d_cosim input-barrier scheduler.
 * The analog trial/rejection driver is controlled, not a SPICE convergence test. */
#define _GNU_SOURCE
#include <assert.h>
#include <dlfcn.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include "ngspice/cmtypes.h"
#include "ngspice/cosim.h"
#include "coroutine.h"
#include "icarus_shim.h"
#include "vpi_user.h"
#define ARGS void
#define XSPICE_ARG
#define TIME analog_time
#define T(n) history[n]
#define PARAM(name) bridge_delay
#define DBG(...) ((void)0)
#define cm_message_printf(...) fprintf(stderr,__VA_ARGS__)
struct pend_in {double when;unsigned which;Digital_t what;};
struct instance {struct co_info info;int q_index;struct pend_in *q;unsigned op_pending;double extra,last_step;};
static double analog_time,history[2],bridge_delay=1e-6,breakpoint;
static unsigned delivered, outputs;
static int cm_analog_set_temp_bkpt(double t) {
 if(t<=history[1]||t>=TIME)return 1;
 breakpoint=t;return 0;
}
static const char *cm_message_get_errmsg(void){return "invalid boundary";}
static void cm_event_queue(double t){(void)t;abort();}
static void output(struct instance *ip){ip->op_pending=0;}
static void observed_output(struct co_info *info,unsigned bit,Digital_t *value){
 (void)bit;(void)value;((struct instance*)info)->op_pending=1;outputs++;
}
static void (*real_input)(struct co_info*,unsigned,Digital_t*);
static void counted_input(struct co_info *info,unsigned bit,Digital_t *value){delivered++;real_input(info,bit,value);}
static int advance(struct instance *ip)
{
    /* The co-simulator should advance to the time in ip->info.vtime,
     * but should pause when output is generated and update vtime.
     */

    (*ip->info.step)(&ip->info);

    if (ip->op_pending) {

        /* The co-simulator produced some output. */

        if (TIME - ip->info.vtime <= PARAM(delay)) {
#if 1
            DBG("Direct output with SPICE %.16g CS %.16g",
                TIME, ip->info.vtime);
            output(ip); // Normal output, unlikely.
#else
            cm_event_queue((TIME + ip->info.vtime + PARAM(delay)) / 2.0);
#endif
        } else {
            double when, delta;

            /* Something changed that may alter the future of the
             * SPICE simulation.  Truncate the current timestep so that
             * SPICE will see the pending output, which currently occurred
             * in the past.
             */

            when = ip->info.vtime + ip->extra;
            DBG("Truncating timestep from %.16g to %.16g", TIME, when);
	    if (cm_analog_set_temp_bkpt(when)) {
                /* Failed to set breakpoint, as it was probably too early.
                 * This could happen if a "Normal" simulation behaves like
                 * an "After_input" simulation is expected to do, and produces
                 * output immediately on input, and uses its own time.
		 * Try and recover: this may lead to a warning on output.
                 */

                DBG("Attempting recovery from failed timestep truncation: %s "
                    "%.16g->%.16g",
                    cm_message_get_errmsg(), TIME, when);
                delta = (TIME - ip->info.vtime) / 1000;
                when = ip->info.vtime;
		if (when < ip->last_step) {
                    cm_message_printf("WARNING: client simulator requested "
                                      "output in the past: %.16g < %.16g",
                                      when, ip->last_step);
                    when = ip->last_step - delta;
                }

		do {
                    when += delta;
                } while (cm_analog_set_temp_bkpt(when));
            }

            /* Any remaining input events are in an alternate future. */

            ip->q_index = -1;
            return 1;
        }
    }
    return 0;
}

/* Called from the main function to run the co-simulation. */

static void run(struct instance *ip)
{
    struct pend_in  *rp;
    double           sim_started;
    int              i;

    if (ip->q_index < 0) {
        /* No queued input, advance to current TIME. */

        DBG("Advancing vtime by %g without input %.16g -> %.16g",
            TIME - ip->info.vtime, ip->info.vtime, TIME);
        ip->info.vtime = TIME;
        if (!advance(ip))
	   ip->last_step = ip->info.vtime;
        return;
    }

    /* Inputs inside a tentative analog interval must not be committed to
     * an irreversible simulator. A later output can shorten the interval,
     * and Newton/LTE rejection can then retry before the consumed input.
     * Settle the analog circuit at its earliest uncommitted input first.
     * Older queued inputs may already be at an accepted analog boundary.
     */
    for (i = 0; i <= ip->q_index; ++i) {
        if (ip->q[i].when > T(1) && ip->q[i].when < TIME &&
            !cm_analog_set_temp_bkpt(ip->q[i].when))
            return;
    }

    /* Scan the queue. */

    DBG("%.16g: Running Q with %d entries", TIME, ip->q_index + 1);
    sim_started = ip->info.vtime;

    for (i = 0; i <= ip->q_index; ++i) {
        rp = ip->q + i;
        if (rp->when <= sim_started) {
            /* Not expected.  */

            cm_message_printf("Warning simulated event is in the past:\n"
                              "XSPICE %.16g\n"
                              "Event  %.16g\n"
                              "Cosim  %.16g",
                              TIME, rp->when, ip->info.vtime);
            cm_message_printf("i=%d index=%d", i, ip->q_index);
            continue;
        }

        /* Step the simulation forward to the input event time. */

        ip->info.vtime = rp->when;
        if ((ip->info.method == Normal || ip->info.method == Both) &&
            advance(ip)) {
            ip->q_index = -1;
            return;
        }

        /* Pass input change to simulation. */

        (*ip->info.in_fn)(&ip->info, rp->which, &rp->what);
        while (i < ip->q_index && ip->q[i + 1].when == rp->when) {
            /* Another change at the same time. */

            ++i;
            rp = ip->q + i;
            (*ip->info.in_fn)(&ip->info, rp->which, &rp->what);
        }

        /* Simulator requested to run after input change. */

        if ((ip->info.method == After_input || ip->info.method == Both) &&
            advance(ip)) {
            ip->q_index = -1;
            return;
        }
    }

    /* All input was processed.  Advance to end of the timestep. */

    ip->q_index = -1;
    if (ip->info.method == Normal && TIME > ip->info.vtime) {
        ip->info.vtime = TIME;
        if (advance(ip))
	   return;
    }
    ip->last_step = ip->info.vtime;
}


static vpiHandle (*iterate)(PLI_INT32,vpiHandle),(*scan_handle)(vpiHandle);
static PLI_INT32 (*get)(PLI_INT32,vpiHandle);
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
 fprintf(f,"scheduler %d %u %a %a %u %u\n",ip->q_index,ip->op_pending,ip->last_step,ip->extra,delivered,outputs);
 for(int i=0;i<=ip->q_index;i++)fprintf(f,"queue %a %u %d %d\n",ip->q[i].when,ip->q[i].which,ip->q[i].what.state,ip->q[i].what.strength);
 for(unsigned i=0;i<ctx->ins+ctx->outs+ctx->inouts;i++){
  struct ngvp_port *p=ctx->ports+i;
  fprintf(f,"port %u %u %u %u %d %d %d %d\n",i,p->bits,p->flags,p->position,p->previous.aval,p->previous.bval,p->new.aval,p->new.bval);
 }
 for(size_t i=0;i<item_count;i++){
  s_vpi_value val={.format=get(vpiType,items[i].handle)==vpiRealVar?vpiRealVal:vpiBinStrVal};get_value(items[i].handle,&val);
  fprintf(f,"state %s %d ",items[i].name,get(vpiSize,items[i].handle));
  if(val.format==vpiRealVal)fprintf(f,"%a\n",val.value.real);else fprintf(f,"%s\n",val.value.str);
 }
 fclose(f);return text;
}
static void *load(const char *path){void *h=dlopen(path,RTLD_NOW|RTLD_GLOBAL);if(!h){fprintf(stderr,"%s\n",dlerror());abort();}return h;}
static void settle(struct instance *ip,double target){
 analog_time=target;unsigned count=0;
 do {run(ip);assert(++count<10000);}while(target-ip->info.vtime>1e-12);
 history[1]=target;
}
int main(int argc,char **argv){
 assert(argc==6);int inject=atoi(argv[5]);
 const char *libs[]={argv[2],argv[3]},*sim[]={argv[4]};
 struct pend_in q[128];
 struct instance ip={.info={.lib_argc=2,.sim_argc=1,.lib_argv=libs,.sim_argv=sim,.out_fn=observed_output,.dlopen_fn=load},.q_index=-1,.q=q,.extra=1e-9};
 void *shim=load(argv[1]);void (*setup)(struct co_info*)=dlsym(shim,"Cosim_setup");assert(setup);setup(&ip.info);
 struct ng_vvp *ctx=ip.info.handle;void *vvp=ctx->vvp_handle;
 #define BIND(name,symbol) name=dlsym(vvp,symbol);assert(name)
 BIND(get_time,"vpi_get_time");BIND(iterate,"vpi_iterate");BIND(scan_handle,"vpi_scan");BIND(get,"vpi_get");BIND(get_str,"vpi_get_str");BIND(get_value,"vpi_get_value");BIND(put_value,"vpi_put_value");
 collect(NULL);assert(item_count>0);qsort(items,item_count,sizeof(*items),by_name);
 real_input=ip.info.in_fn;ip.info.in_fn=counted_input;
 unsigned clock_bit=UINT32_MAX,reset_bit=UINT32_MAX;
 for(unsigned i=0;i<ctx->ins;i++){
  struct ngvp_port *p=ctx->ports+i;const char *name=get_str(vpiName,p->handle);
  if(!strcmp(name,"clk")||!strcmp(name,"fixture_clk"))clock_bit=p->position;
  if(!strcmp(name,"reset_n")||!strcmp(name,"fixture_reset_n"))reset_bit=p->position;
  for(unsigned j=0;j<p->bits;j++){
   Digital_t value={(!strcmp(name,"clk")||!strcmp(name,"reset_n"))?ZERO:ONE,STRONG};
   ip.info.in_fn(&ip.info,p->position+j,&value);
  }
 }
 assert(clock_bit!=UINT32_MAX&&reset_bit!=UINT32_MAX);
 settle(&ip,1e-9);
 for(unsigned edge=1;edge<=256;edge++){
  double target=edge*500e-9;
  ip.q_index=0;q[0]=(struct pend_in){target,clock_bit,{edge%2?ONE:ZERO,STRONG}};
  if(edge==9){ip.q_index=1;q[1]=(struct pend_in){target,reset_bit,{ONE,STRONG}};}
  if(inject){
   for(unsigned retry=0;retry<2;retry++){
    char *before=snapshot(&ip);analog_time=target+100e-9;breakpoint=0;run(&ip);
    assert(breakpoint==target);
    if(inject==2&&edge==16){
     for(size_t i=0;i<item_count;i++)if(get(vpiType,items[i].handle)==vpiReg){
      s_vpi_value value={.format=vpiIntVal,.value.integer=123};put_value(items[i].handle,&value,NULL,vpiNoDelay);break;
     }
    }
    if(inject==3&&edge==16&&retry==0){
     for(size_t i=0;i<item_count;i++)if(get(vpiType,items[i].handle)==vpiMemoryWord){
      s_vpi_value value={.format=vpiIntVal,.value.integer=123};
      s_vpi_time delay={.type=vpiSimTime,.low=100};
      put_value(items[i].handle,&value,&delay,vpiTransportDelay);break;
     }
    }
    char *after=snapshot(&ip);
    if(strcmp(before,after)){fprintf(stderr,"Rejected trial changed internal state at edge %u\n",edge);return 2;}
    free(before);free(after);
   }
  }
  settle(&ip,target);ip.q_index=-1;
  /* Cross the delayed nonblocking assignments too; compare continuation. */
  settle(&ip,target+2e-9);
  if(edge%16==0){char *s=snapshot(&ip);printf("SNAPSHOT %u\n%sEND_SNAPSHOT\n",edge,s);free(s);}
 }
 printf("STATE_RESULT items=%zu delivered=%u outputs=%u rejected=%u\n",item_count,delivered,outputs,inject?512:0);
 ip.info.cleanup(&ip.info);return 0;
}
