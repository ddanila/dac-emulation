import os,subprocess,tempfile,unittest
from pathlib import Path
from build_display_board_bridge import HERE,REGISTER


class DisplayBridgeTests(unittest.TestCase):
    def test_paused_boundary_restores_fault_and_fails_closed(self):
        prefix=r'''
#define _GNU_SOURCE
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#define RTLD_LAZY 1
#define RTLD_NOLOAD 2
struct ng_vvp {void *vvp_handle;};
struct co_info {void *handle; double vtime;};
struct t_cb_data;
static struct ng_vvp context;
static int broken;
static const char *test_mode;
static int32_t callback(struct t_cb_data *unused) {(void)unused;return 0;}
static unsigned long long lookup(const void *h,int32_t(*fn)(struct t_cb_data*),char *data) {
 (void)h;(void)fn;(void)data;return broken?0:1;
}
static int toggle(const void *h,int32_t(*fn)(struct t_cb_data*),char *data) {
 (void)h;(void)fn;(void)data;broken=!broken;return 1;
}
static int family(FILE *f,char *ctx,int32_t(*fn)(struct t_cb_data*)) {
 if(ctx!=(char*)&context || fn!=callback) exit(7);
 fputs("family\n",f);return 0;
}
static int payload(FILE *f) {fputs("payload\n",f);return 0;}
static int association(FILE *f,unsigned long long(*find)(const void*,int32_t(*)(struct t_cb_data*),char*)) {
 if(!find(NULL,NULL,NULL)) return -1;
 fputs("linked\n",f);return 0;
}
static int mutate(int(*change)(const void*,int32_t(*)(struct t_cb_data*),char*)) {
 if(!strcmp(test_mode,"empty")) return 0;
 return change(NULL,NULL,NULL);
}
static void *dlopen(const char *path,int mode) {
 if(mode!=(RTLD_LAZY|RTLD_NOLOAD) || strcmp(path,"/loaded/system.vpi")) exit(6);
 return !strcmp(test_mode,"unloaded")?NULL:(void*)1;
}
static int dlclose(void *p) {(void)p;return 0;}
static void *dlsym(void *p,const char *name) {
 (void)p;
 if(!strcmp(test_mode,"missing-api")) return NULL;
 if(!strcmp(name,"robotron_vvp_sync_family_inventory")) return (void*)family;
 if(!strcmp(name,"robotron_vvp_sync_payload_identity")) return (void*)lookup;
 if(!strcmp(name,"robotron_vvp_sync_toggle_payload_null")) return (void*)toggle;
 if(!strcmp(name,"robotron_display_inventory")) return (void*)payload;
 if(!strcmp(name,"robotron_display_associations")) return (void*)association;
 if(!strcmp(name,"robotron_display_toggle_callback_data")) return (void*)mutate;
 exit(5);
}
static void check_restored(void) {if(broken) _Exit(8);}
'''
        suffix=r'''
int main(int argc,char **argv) {
 (void)argc;test_mode=argv[1];atexit(check_restored);
 setenv("ROBOTRON_DISPLAY_MODULE","/loaded/system.vpi",1);
 setenv("ROBOTRON_PRIVATE_DISPLAY",!strcmp(test_mode,"observe")?"observe":"corrupt",1);
 if(strcmp(test_mode,"missing-identity")) Robotron_sync_identity(&context,callback);
 struct co_info info={&context,6e-6};private_sync_boundary(&info,"before-step");
 if(broken) return 9;
 puts("continued restored");return 0;
}
'''
        header=(HERE/'fixtures/display_board_bridge.h').read_text()
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'probe.c').write_text(prefix+REGISTER+header+suffix)
            subprocess.run([os.environ.get('CC','cc'),'-Werror=incompatible-pointer-types',str(p/'probe.c'),'-o',str(p/'probe')],check=True,capture_output=True,text=True)
            for mode in ('observe','empty','corrupt','unloaded','missing-api','missing-identity'):
                with self.subTest(mode=mode):
                    r=subprocess.run([str(p/'probe'),mode],capture_output=True,text=True)
                    self.assertEqual(r.returncode,0 if mode in ('observe','empty') else 2,r.stderr)
                    if mode=='corrupt':
                        self.assertIn('VB_FAULT payload_unchanged=1 rejected=1 restored=1',r.stderr)
                        self.assertNotIn('continued',r.stdout)
                    if mode in ('observe','empty'):self.assertIn('VB_STABLE equal=1',r.stderr)


if __name__=='__main__':unittest.main()
