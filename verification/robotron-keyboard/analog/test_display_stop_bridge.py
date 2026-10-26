import os,subprocess,tempfile,unittest
from pathlib import Path
from build_display_stop_bridge import HERE,STOP,stop_header
from display_stop_review import bundle
from test_display_board_review import state
from test_private_sync_family_board_review import IDENTITIES


def stopped(present=True):
    s=state()
    if not present:s=[l.replace('VF_CB 1 1 0 9','VF_CB 1 1 0 6') for l in s]
    return s[:-1]+[f'VR_BEGIN 1 {int(present)} {1 if present else 0}','VR_END','VA_END']


class StopLinkTests(unittest.TestCase):
    def test_live_delayed_and_output_stop_relationships(self):
        self.assertEqual(bundle(stopped(),IDENTITIES)['stop'],{'present':True,'callbackId':1})
        self.assertEqual(bundle(stopped(False),IDENTITIES)['stop'],{'present':False,'callbackId':0})

    def test_wrong_callback_missing_identity_and_wrong_phase_rejected(self):
        s=stopped()
        cases=[[l.replace('VR_BEGIN 1 1 1','VR_BEGIN 1 1 2') for l in s],
               [l.replace('VR_BEGIN 1 1 1','VR_BEGIN 1 0 0') for l in s],
               [l.replace('VF_CB 1 1 0 9','VF_CB 1 1 0 6') for l in s],
               [l.replace('VF_CB 1 1 0 9','VF_CB 1 0 0 9') for l in s],
               [l for l in s if not l.startswith('VR_BEGIN')]]
        for lines in cases:
            with self.assertRaises(ValueError):bundle(lines,IDENTITIES)

    def test_pinned_snapshot_composition_rejects_changed_boundaries(self):
        header=(HERE/'fixtures/display_board_bridge.h').read_text()
        out=stop_header(header)
        self.assertIn('display_stop_link(f, ctx, api)',out)
        self.assertIn('VB_STOP_FAULT',out)
        with self.assertRaises(ValueError):stop_header(header+header)
        with self.assertRaises(ValueError):stop_header(header.replace('static char *display_snapshot(', 'static char *changed('))

    def test_opaque_handle_is_resolved_before_use_and_fault_can_be_restored(self):
        prefix=r'''
#define _GNU_SOURCE
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
struct t_cb_data;
static int32_t callback(struct t_cb_data *unused) {(void)unused;return 0;}
static int32_t (*robotron_stop_function)(struct t_cb_data*)=callback;
struct ng_vvp {void *stop_cb;};
static struct ng_vvp context;
static int lookups;
static unsigned long long lookup(const void *handle,int32_t(*function)(struct t_cb_data*),char *user) {
 ++lookups;
 return handle==(void*)(uintptr_t)32 && function==callback && user==(char*)&context ? 7 : 0;
}
struct display_board_api {unsigned long long (*lookup)(const void*,int32_t(*)(struct t_cb_data*),char*);};
'''
        suffix=r'''
int main(void) {
 struct display_board_api api={lookup};char *text=NULL;size_t size=0;
 FILE *f=open_memstream(&text,&size);
 if(!f || display_stop_link(f,&context,api) || lookups) return 1;
 context.stop_cb=(void*)(uintptr_t)32;
 if(display_stop_link(f,&context,api) || lookups!=1) return 2;
 context.stop_cb=(void*)(uintptr_t)1;
 if(display_stop_link(f,&context,api)!=-1 || lookups!=2) return 3;
 context.stop_cb=(void*)(uintptr_t)32;
 if(display_stop_link(f,&context,api) || lookups!=3 || fclose(f)) return 4;
 int result=strcmp(text,"VR_BEGIN 1 0 0\nVR_END\nVR_BEGIN 1 1 7\nVR_END\nVR_BEGIN 1 1 7\nVR_END\n");
 free(text);return result?5:0;
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'probe.c').write_text(prefix+STOP+suffix)
            subprocess.run([os.environ.get('CC','cc'),'-Werror=incompatible-pointer-types',str(p/'probe.c'),'-o',str(p/'probe')],check=True,capture_output=True,text=True)
            subprocess.run([str(p/'probe')],check=True,capture_output=True,text=True)


if __name__=='__main__':unittest.main()
