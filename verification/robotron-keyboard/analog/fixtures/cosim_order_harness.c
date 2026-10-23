/* Controlled analog rejection around the retained input/output sequence.
 * Scheduler functions are extracted verbatim from pinned ngspice source.
 * The mock HDL cannot roll back, just like the Icarus runtime. */
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#define ARGS void
#define XSPICE_ARG
#define TIME analog_time
#define T(n) history[n]
#define PARAM(name) bridge_delay
#define DBG(...) ((void)0)
#define cm_message_printf(...) ((void)0)
typedef int Digital_t;
typedef enum {Normal,After_input,Both} Cosim_method;
struct co_info {double vtime;Cosim_method method;void (*step)(struct co_info*);void (*in_fn)(struct co_info*,unsigned,Digital_t*);};
struct pend_in {double when;unsigned which;Digital_t what;};
struct instance {struct co_info info;int q_index;struct pend_in *q;unsigned op_pending;double extra,last_step;};
static double analog_time,history[2],bridge_delay=10e-9,breakpoint;
static double actual,input_time,output_time;
static int inputs,pending,reversals,steps,outputs;
static int cm_analog_set_temp_bkpt(double t) {
 if(t<=history[1]||t>=TIME)return 1;
 breakpoint=t;return 0;
}
static const char *cm_message_get_errmsg(void){return "invalid boundary";}
static void cm_event_queue(double t){(void)t;}
static void output(struct instance *ip){ip->op_pending=0;outputs++;}
static void step(struct co_info *info){
 struct instance *ip=(struct instance*)info;steps++;
 if(info->vtime+1e-12<actual){reversals++;return;}
 if(pending){pending=0;info->vtime=actual;output_time=actual;ip->op_pending=1;return;}
 actual=info->vtime;
}
static void input(struct co_info *info,unsigned bit,Digital_t *value){
 (void)info;(void)bit;(void)value;inputs++;pending=1;input_time=actual;
}
/* SCHEDULER */
int main(int argc,char **argv){
 assert(argc==2);int patched=atoi(argv[1]);
 const double base=.025137050997371894,event=.025137051997371894;
 const double trial=.025137066304702898,retry=.025137051658783594;
 struct pend_in q[3]={{event,0,1},{event,1,1},{event,2,1}};
 struct instance ip={.info={base,Normal,step,input},.q_index=2,.q=q,.extra=bridge_delay/3,.last_step=base};
 actual=base;history[1]=base;analog_time=trial;breakpoint=0;
 run(&ip);
 if(!patched){
  assert(inputs==3&&breakpoint>event&&actual==event);
  /* The analog retry after output truncation lands before consumed input. */
  analog_time=retry;ip.op_pending=0;run(&ip);assert(reversals==1);
  puts("upstream: reproduced backwards request after output truncation");return 0;
 }
 assert(breakpoint==event&&inputs==0&&steps==0);
 /* A queued event at the previous committed boundary must not hide the
  * first future event from preflight. No inputs may leak before retry. */
 q[0].when=base;breakpoint=0;run(&ip);
 assert(breakpoint==event&&inputs==0&&steps==0);q[0].when=event;
 /* A rejected analog retry is invisible to HDL. Its earlier successful
  * replacement has no input yet; the event remains queued in XSPICE. */
 ip.q_index=-1;analog_time=retry;run(&ip);assert(reversals==0&&inputs==0);
 history[1]=retry;analog_time=event;ip.q_index=2;run(&ip);
 assert(inputs==3&&input_time==event&&reversals==0);
 /* Event is now an accepted analog boundary; output cannot rewind before it. */
 history[1]=event;analog_time=trial;breakpoint=0;run(&ip);
 assert(output_time==event&&breakpoint>history[1]&&reversals==0);
 /* Reject again, but stay after the accepted boundary. Pending output is
  * handled by the model before its next run, as in ucm_d_cosim(). */
 output(&ip);analog_time=event+0.2e-9;run(&ip);
 assert(reversals==0&&inputs==3&&outputs==1);
 /* No-input and grouped same-time input paths remain live and monotonic. */
 history[1]=analog_time;analog_time+=1e-9;run(&ip);assert(actual==analog_time);
 q[0].when=analog_time;q[1].when=analog_time;ip.q_index=1;
 ip.info.vtime=history[1];actual=history[1];run(&ip);
 assert(inputs==5&&reversals==0);
 puts("input barrier: rejected trials stay reversible; grouped inputs delivered once");
 return 0;
}
