"""Compile the actual initializer and accept_output against a partial-output shim."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from build_output_history_init import BLOCK
HERE=Path(__file__).resolve().parent


def probe():
    source=(HERE/'fixtures/ngspice-47/d_cosim.mod').read_text()
    accept=source[source.index('static void accept_output('):source.index('/* Push pending outputs')]
    code=r'''
#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef struct {int state,strength;} Digital_t;
enum {ZERO=0,ONE=1,STRONG=0};
struct co_info {int unused;};
struct instance {struct co_info info;unsigned out_ports,inout_ports,op_pending;Digital_t *out_vals;};
static Digital_t history[2];
static void *cm_event_get_ptr(int tag,int previous){assert(tag==1&&previous==0);return history;}
#define DBG(...)
#define OUTPUT(port) (&(port))
'''+accept+r'''
static int scenario(const char *seed,const char *initialize){
 unsigned i,outs=2,inouts=0;
 Digital_t d_out[2]={{ZERO,STRONG},{ZERO,STRONG}},d_inout[1]={{ZERO,STRONG}};
 history[0]=(Digital_t){ONE,STRONG};history[1]=history[0];
 if(seed)setenv("ROBOTRON_HISTORY_SEED",seed,1);else unsetenv("ROBOTRON_HISTORY_SEED");
 setenv("ROBOTRON_HISTORY_INIT",initialize,1);
'''+BLOCK+r'''
 Digital_t pending[2]={{ZERO,STRONG},{ZERO,STRONG}};
 struct instance ip={.out_ports=2,.out_vals=pending};Digital_t change={ONE,STRONG};
 /* Only the first output changed. The untouched second output must stay low. */
 accept_output(&ip.info,0,&change);
 assert(ip.op_pending==1&&pending[0].state==ONE);
 return pending[1].state;
}
int main(void){
 int dirty_zero=scenario("zero","off"),dirty_one=scenario("one","off");
 int repaired_zero=scenario("zero","on"),repaired_one=scenario("one","on"),repaired=scenario(NULL,"on");
 printf("%d %d %d %d %d\n",dirty_zero,dirty_one,repaired_zero,repaired_one,repaired);
 return 0;
}
'''
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp);(path/'probe.c').write_text(code)
        subprocess.run(['cc','-std=c99','-Wall','-Wextra','-Werror',str(path/'probe.c'),'-o',str(path/'probe')],check=True,capture_output=True)
        return subprocess.run([str(path/'probe')],check=True,capture_output=True,text=True).stdout.strip()


class OutputHistoryTests(unittest.TestCase):
    def test_partial_output_depends_on_dirty_history_until_initialized(self):
        self.assertEqual(probe(),'0 1 0 0 0')

if __name__=='__main__':unittest.main()
