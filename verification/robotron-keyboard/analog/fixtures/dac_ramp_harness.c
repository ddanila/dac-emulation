/* Exercise the actual single-bit DAC evaluator with controlled event history. */
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef enum {ZERO,ONE,UNKNOWN} Digital_State_t;
struct d_data {Digital_State_t i; double i_changed;};
static double times[2], output, breakpoint;
static int calls;
#define TIME times[0]
#define T(i) times[i]
#define OUTPUT(x) output
static void cm_analog_set_perm_bkpt(double t){breakpoint=t;calls++;}
static double evaluate(Digital_State_t old,Digital_State_t now,double changed,double previous) {
 struct d_data a[1]={{now,changed}},b[1]={{old,0}},*in=a,*in_old=b;
 double stored[1]={previous},out[1],*out_old=stored;
 double out_low=0,out_high=5,out_undef=2.5,rise_slope=5e9,fall_slope=2.5e9;
 double time_inc=T(0)-T(1),when,iota,vout,interval[2];
 int i,size_in=1,step,step_count;
 calls=0;breakpoint=-1;
 /* SINGLE_BIT_EVALUATOR */
 return output;
}
int main(int argc,char **argv){
 assert(argc==2);int patched=atoi(argv[1]);
 times[0]=.001005012;times[1]=times[0]-1e-9;
 unsetenv("ROBOTRON_DAC_BREAKPOINTS");
 double value=evaluate(ZERO,ONE,TIME,0);assert(value==0 && calls==0);
 setenv("ROBOTRON_DAC_BREAKPOINTS","1",1);
 value=evaluate(ZERO,ONE,TIME,0);assert(value==0);
 assert(calls==(patched?1:0));if(patched)assert(fabs(breakpoint-(TIME+1e-9))<1e-18);
 value=evaluate(ONE,ZERO,TIME,5);assert(value==5);assert(calls==(patched?1:0));
 if(patched)assert(fabs(breakpoint-(TIME+2e-9))<1e-18);
 value=evaluate(ZERO,UNKNOWN,TIME,0);assert(value==0);assert(calls==(patched?1:0));
 if(patched)assert(fabs(breakpoint-(TIME+.5e-9))<1e-18);
 /* Same digital state on the next analog call must still advertise ramp end. */
 times[1]=times[0];times[0]+=1e-10;
 value=evaluate(ONE,ONE,times[1],0);assert(fabs(value-.5)<1e-8);assert(calls==(patched?1:0));
 value=evaluate(ONE,ONE,times[1],5);assert(value==5 && calls==0);
 /* Output arithmetic is unaffected, including interrupted ramps. */
 for(int old=ZERO;old<=UNKNOWN;old++)for(int now=ZERO;now<=UNKNOWN;now++)for(int j=0;j<11;j++){
  double initial=j*.5,changed=(TIME+T(1))/2;
  unsetenv("ROBOTRON_DAC_BREAKPOINTS");double off=evaluate(old,now,changed,initial);
  setenv("ROBOTRON_DAC_BREAKPOINTS","1",1);double on=evaluate(old,now,changed,initial);
  assert(memcmp(&off,&on,sizeof off)==0);
 }
 puts("DAC ramp output unchanged; boundary corner scheduling checked");
}
