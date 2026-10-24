/* Actual patched single-bit callback with explicit accepted/trial storage. */
#include <assert.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include "dac_anchor.h"
typedef enum {ZERO,ONE,UNKNOWN} Digital_State_t;
struct d_data { Digital_State_t i; double i_changed; };
static RobotronDacRamp slots[2][2];
static double time_now, output[2], corners[8];
static int corner_count;
#define TIME time_now
#define OUTPUT(x) output[i]
static void *cm_analog_get_ptr(int tag,int history) {
    assert(tag==1 && history>=0 && history<=1);return slots[history];
}
static void cm_analog_set_perm_bkpt(double time) {
    assert(time>TIME && corner_count<8);corners[corner_count++]=time;
}
static void callback(double time,struct d_data *in) {
    time_now=time;corner_count=0;
    double out[2],out_low=0,out_high=5,out_undef=2.5,rise_slope=5e9,fall_slope=2.5e9,vout;
    int size_in=2,i;
    switch(0) {case 0:
        /* ACTUAL_ANCHORED_CALLBACK */
    }
}
static void commit(void) {memcpy(slots[1],slots[0],sizeof slots[1]);}
static void near(double value,double wanted) {assert(fabs(value-wanted)<1e-12);}
int main(void) {
    setenv("ROBOTRON_DAC_ANCHORED","1",1);
    struct d_data in[2]={{ZERO,0},{ONE,0}};
    callback(0,in);assert(output[0]==0 && output[1]==5);commit();
    double start=1e-8;
    in[0]=(struct d_data){ONE,start};in[1]=(struct d_data){ZERO,start};
    callback(start,in);assert(output[0]==0 && output[1]==5);
    assert(corner_count==2);near(corners[0],start+1e-9);near(corners[1],start+2e-9);commit();
    RobotronDacRamp accepted[2];memcpy(accepted,slots[1],sizeof accepted);
    callback(start+.5e-9,in);double expected[2]={output[0],output[1]};
    near(expected[0],2.5);near(expected[1],3.75);
    /* Reject a later trial; retry must use accepted state, not trial state. */
    callback(start+3e-9,in);assert(output[0]==5 && output[1]==0);
    callback(start+.5e-9,in);
    assert(output[0]==expected[0] && output[1]==expected[1]);
    assert(memcmp(accepted,slots[1],sizeof accepted)==0);commit();
    in[0]=(struct d_data){ZERO,start+.6e-9};in[1]=(struct d_data){UNKNOWN,start+.6e-9};
    callback(start+.8e-9,in);near(output[0],2.5);near(output[1],3.0);
    expected[0]=output[0];expected[1]=output[1];
    callback(start+4e-9,in);assert(output[0]==0 && output[1]==2.5);
    callback(start+.8e-9,in);
    assert(output[0]==expected[0] && output[1]==expected[1]);
    /* Repeated Newton calls must also leave the accepted snapshots untouched. */
    memcpy(accepted,slots[1],sizeof accepted);callback(start+.8e-9,in);
    assert(memcmp(accepted,slots[1],sizeof accepted)==0);
    /* A future event must not change the current ramp or its pending corner. */
    in[0]=(struct d_data){ZERO,start+1.5e-9};
    callback(start+.9e-9,in);near(output[0],4.5);
    near(corners[0],start+1e-9);
    return 0;
}
