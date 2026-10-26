import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from build_private_sync_family_bridge import HERE,identity_header,identity_vpi


class SyncFamilyBridgeTests(unittest.TestCase):
    def test_vpi_only_adds_explicit_handoff_before_registration(self):
        source='prefix\n    cbd.user_data = (PLI_BYTE8 *)Get_ng_vvp();\n    vpi_register_cb(&cbd);\nsuffix\n'
        result=identity_vpi(source)
        self.assertIn('Robotron_sync_identity((struct ng_vvp*)cbd.user_data, next_advance_cb);\n    vpi_register_cb',result)
        result=result.replace('    extern void Robotron_sync_identity(struct ng_vvp*, PLI_INT32(*)(struct t_cb_data*));\n','').replace('    Robotron_sync_identity((struct ng_vvp*)cbd.user_data, next_advance_cb);\n','')
        self.assertEqual(result,source)
        for bad in (source+source,source.replace('Get_ng_vvp','other_context')):
            with self.assertRaises(ValueError):identity_vpi(bad)

    def test_compiled_handoff_matches_function_and_context_and_fails_closed(self):
        header=identity_header((HERE/'fixtures/private_sync_bridge.h').read_text())
        prefix=r'''
#define _GNU_SOURCE
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
struct ng_vvp {void *vvp_handle;};
struct co_info {void *handle; double vtime;};
struct t_cb_data;
static int32_t expected_function(struct t_cb_data *unused) {(void)unused;return 7;}
static struct ng_vvp expected_context;
static int observe(FILE *stream,char *user,int(*function)(struct t_cb_data*)) {
 if(user!=(char*)&expected_context || function!=expected_function) exit(4);
 fputs("matched\n",stream);return 0;
}
static void *dlsym(void *handle,const char *name) {
 (void)handle;
 if(strcmp(name,"robotron_vvp_sync_family_inventory")) exit(5);
 return (void*)observe;
}
'''
        suffix=r'''
int main(int argc,char **argv) {
 (void)argc;struct ng_vvp other={0};
 if(!strcmp(argv[1],"missing")) {private_sync_snapshot(&expected_context);return 9;}
 if(!strcmp(argv[1],"null")) {Robotron_sync_identity(&expected_context,NULL);return 9;}
 Robotron_sync_identity(&expected_context,expected_function);
 if(!strcmp(argv[1],"duplicate")) {Robotron_sync_identity(&expected_context,expected_function);return 9;}
 if(!strcmp(argv[1],"wrong-context")) {private_sync_snapshot(&other);return 9;}
 char *snapshot=private_sync_snapshot(&expected_context);
 int result=strcmp(snapshot,"matched\n")!=0;free(snapshot);return result;
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'probe.c').write_text(prefix+header+suffix)
            subprocess.run([os.environ.get('CC','cc'),'-Werror=incompatible-pointer-types',str(p/'probe.c'),'-o',str(p/'probe')],check=True,capture_output=True,text=True)
            for mode in ('ok','missing','null','duplicate','wrong-context'):
                with self.subTest(mode=mode):
                    result=subprocess.run([str(p/'probe'),mode],capture_output=True,text=True)
                    self.assertEqual(result.returncode,0 if mode=='ok' else 2,result.stderr)


if __name__=='__main__':unittest.main()
