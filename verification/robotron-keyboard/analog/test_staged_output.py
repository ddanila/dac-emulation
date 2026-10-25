"""Exercise actual output/dispatch code across repeated staging and callback reset."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from build_staged_output import patch, ENABLE
HERE=Path(__file__).resolve().parent


def probe():
    source=patch((HERE/'fixtures/ngspice-47/d_cosim.mod').read_text())
    a=source.index('static void output(');b=source.index('/* Run the co-simulation.',a);output=source[a:b]
    a=source.index('    /* Start a new callback staging window.');b=source.index('    /* Check TIME',a);dispatch=source[a:b]
    code=r'''
#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
enum {ZERO=0,ONE=1,UNKNOWN=2,STRONG=0,FALSE=0,TRUE=1};
typedef struct {int state,strength;} Digital_t;
struct context {double time,delay;};
struct instance {struct {double vtime;} info;unsigned out_ports,inout_ports,op_pending;Digital_t *out_vals;};
struct port {Digital_t value;int changed;double delay;};
static struct port d_out[2],d_inout[1];static Digital_t history[2];
static void *cm_event_get_ptr(int tag,int previous){assert(tag==1&&previous==0);return history;}
#define DBG(...)
#define ARGS struct context *ctx
#define XSPICE_ARG ctx
#define TIME (ctx->time)
#define PARAM(name) (ctx->name)
#define OUTPUT(p) (&(p).value)
#define OUTPUT_CHANGED(p) ((p).changed)
#define OUTPUT_DELAY(p) ((p).delay)
#define cm_message_printf(...) fprintf(stderr,__VA_ARGS__)
'''+ENABLE+output+'\nstatic void dispatch(struct instance *ip,ARGS){unsigned i;\n'+dispatch+'\n}\n'+r'''
static int scenario(const char *mode){
 setenv("ROBOTRON_STAGED_OUTPUT",mode,1);
 struct context ctx={1e-6,10e-9};Digital_t pending[2]={{UNKNOWN,STRONG},{ONE,STRONG}};
 struct instance ip={.info={1e-6},.out_ports=2,.op_pending=1,.out_vals=pending};
 for(unsigned i=0;i<2;i++){history[i]=(Digital_t){ZERO,STRONG};d_out[i].value=history[i];d_out[i].changed=TRUE;}
 dispatch(&ip,&ctx);assert(d_out[0].changed&&d_out[1].changed);
 pending[1].state=ZERO;ip.op_pending=1;output(&ip,&ctx);
 assert(d_out[0].value.state==UNKNOWN&&d_out[1].value.state==ZERO);
 int retained=d_out[0].changed;
 /* The next callback must clear stale changed flags even with pending data. */
 d_out[0].changed=d_out[1].changed=TRUE;ip.op_pending=1;dispatch(&ip,&ctx);
 assert(!d_out[0].changed&&!d_out[1].changed);
 d_out[0].changed=d_out[1].changed=TRUE;ip.op_pending=0;dispatch(&ip,&ctx);
 assert(!d_out[0].changed&&!d_out[1].changed);
 return retained;
}
int main(void){int old=scenario("off"),fixed=scenario("on");printf("%d %d\n",old,fixed);return 0;}
'''
    with tempfile.TemporaryDirectory() as tmp:
        p=Path(tmp);(p/'probe.c').write_text(code)
        subprocess.run(['cc','-std=c99','-Wall','-Wextra','-Werror',str(p/'probe.c'),'-o',str(p/'probe')],check=True,capture_output=True)
        return subprocess.run([str(p/'probe')],check=True,capture_output=True,text=True).stdout.strip()

class StagedOutputTests(unittest.TestCase):
    def test_accumulates_within_callback_and_resets_between_callbacks(self):self.assertEqual(probe(),'0 1')

if __name__=='__main__':unittest.main()
