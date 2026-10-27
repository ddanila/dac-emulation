#!/usr/bin/env python3
"""Pin callback-list ownership, initialization and retained subclass state."""
import argparse,hashlib,json,re,tarfile
from pathlib import Path
from thread_board_reachability import ARCHIVE_SHA
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
BRIDGE_SHA='54419fef0ac32cba3dc8e13790baabcede9e2bc9c26f55424d7ff8686f08215e'

def analyze(evidence):
    def body(name):return evidence[name]['excerpt']
    def require(name,*tokens):
        text=body(name)
        if any(token not in text for token in tokens):raise ValueError('Changed ownership contract: '+name)
        return text
    def order(name,*tokens):
        text=body(name);cursor=0
        for token in tokens:
            found=text.find(token,cursor)
            if found<0:raise ValueError('Changed execution order: '+name)
            cursor=found+len(token)
    require('ownerStorage','value_callback*vpi_callbacks_;','struct __vpi_array_word*array_words_;')
    require('callbackStorage','struct __vpiCallback*next;','struct t_cb_data cb_data;','struct t_vpi_time cb_time;','struct t_vpi_value cb_value;')
    require('initialization','cb_data = *data;','cb_data.time = &cb_time;','cb_data.value = &cb_value;','cb_time.type = vpiSuppressTime;','cb_value.format = vpiSuppressVal;')
    require('removal','obj->cb_data.cb_rtn = 0;')
    if re.search(r'\bdelete\b',body('removal')):raise ValueError('Cancellation no longer deferred')
    require('ownerLists','struct __vpi_array_word* next;','struct __vpiArray* array;','unsigned long word;','tmp->next = array_words_;','array_words_ = tmp;','cb->next = vpi_callbacks_;','vpi_callbacks_ = cb;','prev->next = next;','delete cur;')
    order('ownerLists','void vvp_vpi_callback::run_vpi_callbacks()','array_word->array->word_change(array_word->word);','value_callback *next = vpi_callbacks_;','next = dynamic_cast<value_callback*>(cur->next);','cur->test_value_callback_ready()','get_value(cur->cb_data.value);','callback_execute(cur);')
    order('execution','set_callback_time(&cur->cb_data);','(cur->cb_data.cb_rtn)(&cur->cb_data);')
    require('partSelect','char*value_bits_;','size_t value_off_;','memcmp(value_bits_,','memcpy(value_bits_,','return false;')
    require('arrayCallbacks','long word_addr;','cur->word_addr != (long)addr','cur->cb_data.index =','cur->test_value_callback_ready()')
    require('arrayPartSelect','char*value_bits_;','memcmp(value_bits_,','memcpy(value_bits_,')
    require('signalHandle','struct __vpiBit*bits;','__vpiScope* scope;','vpiHandle parent;','const char*name;','vpiHandle index;','__vpiDecConst msb, lsb;','unsigned is_netarray','vvp_net_t*node;')
    require('bridgeWatch','.type = vpiSuppressTime','.format = vpiVectorVal','.reason = cbValueChange, .cb_rtn = output_cb','cb.obj = handle;','cb.user_data = pp;','vpi_register_cb(&cb);')
    order('bridgeStartup','watch(namesake, pp);','pp->bits =','pp->handle = namesake;','pp->ctx = ctx;')
    order('bridgeOutput','pp->new.aval = cb->value->value.vector->aval;','pp->new.bval = cb->value->value.vector->bval;','return 0;')
    if re.search(r'\b(?:yield|resume|swapcontext|setcontext|vvp_run)\s*\(',body('bridgeOutput')):raise ValueError('Bridge output now yields')
    return dict(
        ownedLists={'vvp_vpi_callback.vpi_callbacks_':['ordered callback allocation/lifetime','next','cb_data.cb_rtn including cancelled-null','object handle and admitted caller user_data','reason','time/value self-bindings and initialized format/type'],
                    'vvp_vpi_callback.array_words_':['ordered association allocation/lifetime','next','array identity','word address']},
        statefulSubclasses={'value_part_callback':['value_bits_ bytes','value_off_','selected handle width/base'],
                            'array_word_value_callback':['word_addr','whole-array callback index when initialized'],
                            'array_word_part_callback':['inherited word_addr','value_bits_ bytes','selected part width']},
        admissionRequirements=[
            'Enumerate all live owners, including empty lists, and bind adjusted owner pointers to native graph/filter classes.',
            'Validate every list link against registered live allocations before dereferencing; reject cycles, foreign owners and aliases. Preserve order and deferred-cancellation nodes until native unlink/destruction.',
            'Exact base-class callback admission does not admit part-select or array subclasses. Refuse unknown families before any output until their additional history is observed.',
            'Observe array-word association nodes independently from procedural-array word-handle caches. Bind each association to array identity and valid word address without allocating VPI handles.',
            'Follow admitted bridge object handles to typed native signal/node/scope identities; handle pointer equality alone is not referent coverage. Select scope/name versus array-parent/index union arms by native flags.',
            'Constructor initialization only proves time type/value format and self-pointers. Establish caller initialization before reading optional index, time words, value union or user_data; never serialize padding.',
            'The bridge watch caller registers before pp metadata initialization. Delay referent validation until registration handoff and port initialization complete.',
            'Value delivery refreshes the temporary union before invocation. The known output callback copies it without an explicit coroutine yield; preserve this scoped continuation argument instead of claiming arbitrary callback scratch is irrelevant.',
            'During invocation, local next/prev/array-word cursors can outlive list mutation. Either observe executing traversal frames or enforce the non-yielding admitted-callback boundary; idle list enumeration alone does not cover suspended traversal.',
            'Require native tail/middle/head cancellation, callback insertion during dispatch, reentrant callbacks, alias associations and subclass refusals. Restore faults before native continuation; preserve all preceding combined state checks.'
        ],scope='Pinned ownership and initialization audit, not new native list coverage or operational qualification.')

def build(archive,bridge,out):
    if sha(archive)!=ARCHIVE_SHA or sha(bridge)!=BRIDGE_SHA:raise ValueError('Changed pinned source')
    files={}
    with tarfile.open(archive) as tar:
        for name in ('vvp_vpi_callback.h','vpi_priv.h','vpi_callback.cc','array.cc'):
            matches=[m for m in tar.getmembers() if m.name.endswith('/vvp/'+name)]
            if len(matches)!=1:raise ValueError('Ambiguous source')
            files[name]=tar.extractfile(matches[0]).read().decode()
    files['bridge-vpi.c']=bridge.read_text()
    def section(name,start,end):
        text=files[name];i=text.index(start);j=text.index(end,i+len(start))
        return dict(file=name,firstLine=text[:i].count('\n')+1,excerpt=text[i:j])
    e={
        'ownerStorage':section('vvp_vpi_callback.h','class vvp_vpi_callback {','#endif /*'),
        'callbackStorage':section('vpi_priv.h','struct __vpiCallback :','extern void callback_execute'),
        'initialization':section('vpi_callback.cc','value_callback::value_callback(', 'static void vpip_real_value_change'),
        'removal':section('vpi_callback.cc','PLI_INT32 vpi_remove_cb(', 'void callback_execute('),
        'execution':section('vpi_callback.cc','void callback_execute(', '/*\n * Usually there is at most'),
        'ownerLists':section('vpi_callback.cc','struct __vpi_array_word {','void vvp_signal_value::get_signal_value('),
        'partSelect':section('vpi_callback.cc','class value_part_callback :','static value_callback*make_value_change_part('),
        'arrayCallbacks':section('array.cc','class array_word_value_callback :','bool array_resolv_list_t::resolve('),
        'arrayPartSelect':section('array.cc','class array_word_part_callback :','value_callback*vpip_array_word_change('),
        'signalHandle':section('vpi_priv.h','struct __vpiSignal :','extern unsigned vpip_size('),
        'bridgeWatch':section('bridge-vpi.c','static void watch(','/* Callback function - simulation is starting.'),
        'bridgeStartup':section('bridge-vpi.c','static PLI_INT32 start_cb(', '    /* Constant-folded outputs'),
        'bridgeOutput':section('bridge-vpi.c','static PLI_INT32 output_cb(', 'static void init('),
    }
    result=dict(qualified=False,archiveSha256=ARCHIVE_SHA,bridgeSha256=BRIDGE_SHA,sources={n:hashlib.sha256(t.encode()).hexdigest() for n,t in files.items()},evidence=e,analysis=analyze(e))
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('archive','bridge','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.archive,a.bridge,a.out)
