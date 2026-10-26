import os,subprocess,tempfile,unittest
from pathlib import Path
from build_startup_callback_bridge import HERE,startup_vpi,startup_header

class StartupCallbackBridge(unittest.TestCase):
    def test_handoff_and_fault_restore_order(self):
        source='    vpi_register_cb(&cb);\n    cbd.user_data = (PLI_BYTE8 *)Get_ng_vvp();\n    vpi_register_cb(&cbd);\n    /* Make a direct call to the "end-of-advance" callback to start running. */\n    cr_init(&ctx->cr_ctx);\n    next_advance_cb(cb);\n    return 0;'
        result=startup_vpi(source)
        self.assertIn('registered,start_cb)',result)
        self.assertLess(result.index('Robotron_start_phase(ctx,1)'),result.index('next_advance_cb(cb);'))
        self.assertGreater(result.index('Robotron_start_phase(ctx,2)'),result.index('next_advance_cb(cb);'))
        with self.assertRaises(ValueError):startup_vpi(source+source)
        header=startup_header((HERE/'fixtures/display_board_bridge.h').read_text())
        self.assertLess(header.index('robotron_start_fault(start_field)!=1) exit(3)'),header.index('int rejected=changed==NULL;'))

    def test_lifetime_phase_and_fault_contract(self):
        prefix=r'''
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
struct t_cb_data;struct __vpiHandle;
struct ng_vvp {void *vvp_handle;};
static int live=1,bad;static unsigned long long lifetime=7;
static struct ng_vvp ctx={(void*)1};
static int32_t callback(struct t_cb_data *cb){(void)cb;return 0;}
static unsigned long long lookup(const void *h,int32_t(*fn)(struct t_cb_data*),char *u){return live && !bad && h==(void*)16 && fn==callback && u==(char*)&ctx ? lifetime : 0;}
static int toggle(const void *h,int32_t(*fn)(struct t_cb_data*),char *u,int field){(void)h;(void)fn;(void)u;if(field<0 || field>3)return -1;bad=!bad;return 1;}
static void *fake_dlsym(void *lib,const char *name){if(lib!=(void*)1)exit(9);if(!strcmp(name,"robotron_vvp_start_identity"))return (void*)lookup;if(!strcmp(name,"robotron_vvp_start_toggle"))return (void*)toggle;return NULL;}
#define dlsym fake_dlsym
'''
        suffix=r'''
static char *shot(void){char *p=NULL;size_t n=0;FILE *f=open_memstream(&p,&n);int r=robotron_start_inventory(f,&ctx);fclose(f);if(r){free(p);return NULL;}return p;}
int main(int argc,char **argv){
 (void)argc;Robotron_start_registration(&ctx,(void*)16,callback);
 if(!strcmp(argv[1],"duplicate")){Robotron_start_registration(&ctx,(void*)16,callback);return 8;}
 if(!strcmp(argv[1],"skip")){Robotron_start_phase(&ctx,2);return 8;}
 if(shot())return 10;
 Robotron_start_phase(&ctx,1);char *before=shot();if(!before)return 11;
 for(int f=0;f<4;f++){if(robotron_start_fault(f)!=1 || shot() || robotron_start_fault(f)!=1)return 12;char *after=shot();if(!after || strcmp(before,after))return 13;free(after);}
 lifetime=8;if(shot())return 14;lifetime=7;
 live=0;if(shot())return 15;live=1;
 Robotron_start_phase(&ctx,2);if(shot())return 16;
 live=0;char *after=shot();if(!after)return 17;
 printf("%s%s",before,after);free(before);free(after);
 if(robotron_start_fault(0)!=-1)return 18;return 0;
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'probe.c').write_text(prefix+(HERE/'fixtures/startup_callback_bridge.h').read_text()+suffix)
            subprocess.run([os.environ.get('CC','cc'),'-Werror=incompatible-pointer-types',str(p/'probe.c'),'-o',str(p/'probe')],check=True,capture_output=True,text=True)
            r=subprocess.run([str(p/'probe'),'normal'],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stdout.splitlines(),['VS_START 1 7 7','VS_START 2 7 0'])
            for mode in ('duplicate','skip'):self.assertEqual(subprocess.run([str(p/'probe'),mode]).returncode,2)

if __name__=='__main__':unittest.main()
