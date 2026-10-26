import os,subprocess,tempfile,unittest
from pathlib import Path
from build_executing_wrapper_bridge import HERE,REGISTER,wrapper_header


class WrapperBridgeTests(unittest.TestCase):
    def test_changed_source_boundaries_fail_closed(self):
        source=(HERE/'fixtures/display_board_bridge.h').read_text()
        with self.assertRaises(ValueError):wrapper_header(source+source)
        with self.assertRaises(ValueError):wrapper_header(source.replace('    display_null_fn toggle;',''))

    def test_real_bridge_code_restores_deletion_before_exit(self):
        prefix=r'''
#define _GNU_SOURCE
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#define RTLD_LAZY 1
#define RTLD_NOLOAD 2
struct t_cb_data;
struct __vpiHandle;
struct ng_vvp {void *vvp_handle;struct __vpiHandle *stop_cb;};
struct co_info {void *handle;double vtime;};
static struct ng_vvp context;
static int deletion;
static const char *test_mode;
static int32_t callback(struct t_cb_data *cb) {(void)cb;return 0;}
static int family(FILE *f,char *ctx,int32_t(*fn)(struct t_cb_data*)) {
 if(ctx!=(char*)&context || fn!=callback) exit(7);
 fputs("family\n",f);return 0;
}
static int payload(FILE *f) {fputs("payload\n",f);return 0;}
static unsigned long long lookup(const void *p,int32_t(*fn)(struct t_cb_data*),char *ctx) {(void)p;(void)fn;(void)ctx;return 1;}
static int toggle_payload(const void *p,int32_t(*fn)(struct t_cb_data*),char *ctx) {(void)p;(void)fn;(void)ctx;return -1;}
static int association(FILE *f,unsigned long long(*find)(const void*,int32_t(*)(struct t_cb_data*),char*)) {(void)find;fputs("link\n",f);return 0;}
static int mutate(int(*toggle)(const void*,int32_t(*)(struct t_cb_data*),char*)) {(void)toggle;return -1;}
static int executing(FILE *f) {fprintf(f,"VE_BEGIN 1 1\nVE_FRAME 0 7 1 %d\nVE_END\n",deletion);return 0;}
static int toggle_delete(void) {deletion=!deletion;return 1;}
static void *dlopen(const char *path,int flags) {(void)path;(void)flags;return (void*)1;}
static int dlclose(void *p) {(void)p;return 0;}
static void *dlsym(void *p,const char *name) {
 (void)p;
 if(!strcmp(name,"robotron_vvp_sync_family_inventory")) return (void*)family;
 if(!strcmp(name,"robotron_vvp_sync_payload_identity")) return (void*)lookup;
 if(!strcmp(name,"robotron_vvp_sync_toggle_payload_null")) return (void*)toggle_payload;
 if(!strcmp(name,"robotron_display_inventory")) return (void*)payload;
 if(!strcmp(name,"robotron_display_associations")) return (void*)association;
 if(!strcmp(name,"robotron_display_toggle_callback_data")) return (void*)mutate;
 if(!strcmp(name,"robotron_vvp_executing_inventory")) return (void*)executing;
 if(!strcmp(name,"robotron_vvp_executing_toggle_delete")) return !strcmp(test_mode,"missing-api")?NULL:(void*)toggle_delete;
 exit(6);
}
static void restored(void) {if(deletion) _Exit(8);}
'''
        suffix=r'''
int main(int argc,char **argv) {
 (void)argc;test_mode=argv[1];atexit(restored);
 setenv("ROBOTRON_DISPLAY_MODULE","/loaded/system.vpi",1);
 setenv("ROBOTRON_PRIVATE_DISPLAY",!strcmp(test_mode,"corrupt")?"wrapper-corrupt":"observe",1);
 Robotron_sync_identity(&context,callback);
 struct co_info info={&context,6e-6};private_sync_boundary(&info,"before-step");
 puts("continued");return 0;
}
'''
        source=prefix+REGISTER+wrapper_header((HERE/'fixtures/display_board_bridge.h').read_text())+suffix
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'probe.c').write_text(source)
            subprocess.run([os.environ.get('CC','cc'),'-Werror=incompatible-pointer-types',str(p/'probe.c'),'-o',str(p/'probe')],check=True,capture_output=True,text=True)
            for mode in ('observe','corrupt','missing-api'):
                r=subprocess.run([str(p/'probe'),mode],capture_output=True,text=True)
                self.assertEqual(r.returncode,0 if mode=='observe' else 2,r.stderr)
                if mode=='corrupt':
                    self.assertIn('VB_WRAPPER_FAULT detected=1 restored=1',r.stderr)
                    self.assertIn('VE_FRAME 0 7 1 1',r.stderr);self.assertNotIn('continued',r.stdout)
                elif mode=='observe':self.assertIn('VB_STABLE equal=1',r.stderr)


if __name__=='__main__':unittest.main()
