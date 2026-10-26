"""Execute the real advance() branch with controlled output/breakpoint callbacks."""
from pathlib import Path
import subprocess,tempfile,unittest
from build_output_breakpoint_probe import patch
HERE=Path(__file__).resolve().parent

class OutputBreakpointTests(unittest.TestCase):
    def test_disabled_observer_and_single_failed_request(self):
        text=patch((HERE/'fixtures/ngspice-47/d_cosim.mod').read_text())
        code=text[text.index('static int output_breakpoint('):text.index('/* Called from the main function')]
        harness=r'''
#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
struct info {double vtime;void (*step)(struct info*);};
struct instance {struct info info;int op_pending,q_index;double extra,last_step;};
static double now=10,delay=0;static int calls=0,advances=0,publications=0;
#define ARGS int unused
#define TIME now
#define PARAM(x) delay
#define XSPICE_ARG 0
#define DBG(...) ((void)0)
#define cm_message_printf(...) fprintf(stderr,__VA_ARGS__)
static int cm_analog_set_temp_bkpt(double when){calls++;return when<=1||when>=now;}
static const char *cm_message_get_errmsg(void){return "controlled failure";}
static void output(struct instance *ip,int unused){(void)unused;ip->op_pending=0;publications++;}
static void step(struct info *info){advances++;info->vtime=2;((struct instance*)info)->op_pending=1;}
'''+code+r'''
int main(int argc,char **argv){
 assert(argc==2);setenv("ROBOTRON_OUTPUT_BREAKPOINT",argv[1],1);
 struct instance ip={.info={.vtime=0,.step=step},.q_index=3,.extra=.1,.last_step=1};
 assert(advance(&ip,0)==1);assert(ip.op_pending==1&&ip.q_index==-1&&advances==1&&publications==0);
 assert(calls==1); /* A forced failure skips the first real request, then recovers. */
 ip.q_index=3;assert(advance(&ip,0)==1);assert(calls==2&&advances==2);
 delay=20;assert(advance(&ip,0)==0);assert(calls==2&&publications==1&&ip.op_pending==0);
 return 0;
}
'''
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'probe.c').write_text(harness)
            subprocess.run(['cc','-std=c99','-Wall','-Wextra','-Wno-unused-parameter',str(p/'probe.c'),'-o',str(p/'probe')],check=True,capture_output=True)
            logs={mode:subprocess.run([str(p/'probe'),mode],check=True,capture_output=True,text=True).stderr for mode in ('off','observe','fail-once')}
            self.assertEqual(logs['off'],'')
            self.assertEqual(logs['observe'].count('OUTPUT_BKPT '),2)
            self.assertNotIn('injected=1',logs['observe'])
            self.assertEqual(logs['fail-once'].count('injected=1'),1)
            self.assertEqual(logs['fail-once'].count('recovery=1'),1)
            self.assertEqual(subprocess.run([str(p/'probe'),'invalid'],capture_output=True).returncode,2)

    def test_changed_source_branch_is_rejected(self):
        text=(HERE/'fixtures/ngspice-47/d_cosim.mod').read_text()
        with self.assertRaises(ValueError):patch(text.replace('} while (cm_analog_set_temp_bkpt(when));','} while (0);'))

if __name__=='__main__':unittest.main()
