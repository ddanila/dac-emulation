/* Exercise the actual ADC normal-conversion body with controlled rollback. */
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef enum {ZERO,ONE,UNKNOWN} Digital_State_t;
#define ANALOG 0
#define EVENT 1
#define TRUE 1
#define FALSE 0
#define STRONG 1
static double times[2],previous_value,current_value,input_value,requested;
static int call_type,queued,allow_break,changed,state,strength;
static double delay;
#define TIME times[0]
#define T(i) times[i]
#define CALL_TYPE call_type
#define INPUT(x) input_value
#define OUTPUT_STATE(x) state
#define OUTPUT_CHANGED(x) changed
#define OUTPUT_DELAY(x) delay
#define OUTPUT_STRENGTH(x) strength
#define PARAM(x) 0.0
static void *cm_analog_get_ptr(int tag,int history){(void)tag;return history?&previous_value:&current_value;}
static int cm_analog_set_temp_bkpt(double t){requested=t;return !allow_break;}
static void cm_event_queue(double t){assert(t==TIME);queued++;}
#define cm_message_printf(...) ((void)0)
/* GET_OUT_VALUE */
static void evaluate(int type,double old_voltage,double voltage,int old_state,double low,double high){
 int i,size_in=1,size_out=1; Digital_State_t stored=old_state,*out=&stored,test;
 double in_low=low,in_high=high;
 call_type=type;previous_value=old_voltage;input_value=voltage;state=old_state;
 changed=1;queued=0;requested=-1;current_value=-99;
 /* NORMAL_CONVERSION */
}
int main(void){
 times[0]=20e-9;times[1]=10e-9;allow_break=1;
 unsetenv("ROBOTRON_ADC_CROSSINGS");
 evaluate(ANALOG,0,5,ZERO,.8,2);assert(queued==1 && requested==-1);
 evaluate(EVENT,0,5,ZERO,.8,2);assert(state==ONE);
 setenv("ROBOTRON_ADC_CROSSINGS","1",1);
 evaluate(ANALOG,0,5,ZERO,.8,2);assert(!queued && fabs(requested-11.6e-9)<1e-22 && current_value==5);
 evaluate(EVENT,0,5,ZERO,.8,2);assert(!changed && state==ZERO);
 evaluate(ANALOG,5,0,ONE,.8,2);assert(fabs(requested-16e-9)<1e-22);
 /* Accepted history is read, never overwritten by a trial or event call. */
 assert(previous_value==5);
 evaluate(EVENT,5,0,ONE,.8,2);assert(previous_value==5 && current_value==-99);
 /* Equality cannot strand a transition until an unrestricted later step. */
 evaluate(ANALOG,.8,1.4,ZERO,.8,2);assert(fabs(requested-15e-9)<1e-22);
 evaluate(ANALOG,2,1.4,ONE,.8,2);assert(fabs(requested-15e-9)<1e-22);
 /* At the engine's minimum spacing, retain native state semantics. */
 allow_break=0;
 evaluate(EVENT,0,1.4,ZERO,.8,2);assert(state==UNKNOWN);
 evaluate(EVENT,1.4,1.4,UNKNOWN,.8,2);assert(!changed && requested==-1);
 evaluate(EVENT,1.4,1.4,ONE,2,.8);assert(!changed); /* Schmitt hold */
 evaluate(EVENT,0,0,ZERO,.8,2);assert(!changed && requested==-1);
 puts("ADC crossing rollback, equality, unknown and disabled controls pass");
}
