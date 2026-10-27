/*
 * Main file for the shared library ivlng.so that is used
 * by ngspice's d_cosim code model to connect an instance of
 * an Icarus Verilog simulation (libvvp.so).
 * Licensed on the same terms as Ngspice.
 *
 * Copyright (c) 2024-2025 Giles Atkinson
 */

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>
#include <stdbool.h>

/* The VVP code runs on its own stack, handled by cr_xxx() functions. */

#include "coroutine_shim.h"

#ifdef _MSC_VER
#include "../../../visualc/src/include/ngspice/config.h"
#else
#include "ngspice/config.h"  // For NGSPICELIBDIR
#endif

#include "ngspice/cmtypes.h" // For Digital_t
#include "ngspice/cosim.h"


#ifndef NGSPICELIBDIR
#if defined(__MINGW32__) || defined(_MSC_VER)
#define NGSPICELIBDIR "C:\\Spice64\\lib\\ngspice"
#else
#define NGSPICELIBDIR "/usr/local/lib/ngspice"
#endif
#endif

/* This header file defines the external interface. It also contains an initial
 * comment that describes how this shared library is used.
 */

#include "icarus_shim.h"

/* Report fatal errors. */

static void fail(const char *what, int why)
{
    fprintf(stderr, "Icarus shim failed in function %s: %s.\n",
            what, strerror(why));
    abort();
}

static void input(struct co_info *pinfo, unsigned int bit, Digital_t *val)
{
    struct ng_vvp    *ctx = (struct ng_vvp *)pinfo->handle;
    struct ngvp_port *pp;
    unsigned int      count;
    int               a, b, dirty;

    /* Convert the value. */

    if (val->strength <= HI_IMPEDANCE && val->state != UNKNOWN) {
        a = val->state; // Normal - '0'/'1'.
        b = 0;
    } else if (val->strength == HI_IMPEDANCE) {
        a = 0;          // High impedance - 'z'.
        b = 1;
    } else {
        a = 1;          // Undefined - 'x'.
        b = 1;
    }

    /* Find the port. */

    if (bit >= pinfo->in_count) {
        bit -= pinfo->in_count;
        if (bit >= pinfo->inout_count)
            return;
        pp = ctx->ports + ctx->ins + ctx->outs; // Point at inouts.
        count = ctx->inouts;
    } else {
        pp = ctx->ports;
        count = ctx->ins;
    }

    while (count--) {
        if (pp[count].position <= bit)
            break;
    }
    pp = pp + count;
    bit -= pp->position;

    /* Check and update. */

    dirty = 0;
    bit = pp->bits - bit - 1; // Bit position for big-endian.
    a <<= bit;
    if (a ^ pp->previous.aval) {
        if (a)
            pp->previous.aval |= a;
        else
            pp->previous.aval &= ~(1 << bit);
        dirty = 1;
    }
    b <<= bit;
    if (b ^ pp->previous.bval) {
        if (b)
            pp->previous.bval |= b;
        else
            pp->previous.bval &= ~(1 << bit);
        dirty = 1;
    }

    if (dirty && !(pp->flags & IN_PENDING)) {
        pp->flags |= IN_PENDING;
        ++ctx->in_pending;
    }
}

/* Move the VVP simulation forward. */

/* Single-instance identity handoff, completed on the HDL thread before
 * start_cb can yield to SPICE. Neither callback code nor data is guessed from
 * addresses, allocator contents or a possibly expired stop_cb handle. */
struct t_cb_data;
static struct ng_vvp *robotron_identity_context;
static int32_t (*robotron_stop_function)(struct t_cb_data*);
void Robotron_sync_identity(struct ng_vvp *ctx, int32_t (*function)(struct t_cb_data*))
{
    if (!ctx || !function || robotron_identity_context || robotron_stop_function) {
        fprintf(stderr, "Invalid synchronization callback identity handoff\n"); exit(2);
    }
    robotron_identity_context = ctx;
    robotron_stop_function = function;
}

static int robotron_memory_inventory(FILE*,struct ng_vvp*);
static char*robotron_parameter_text(struct ng_vvp*);
static int robotron_parameter_inventory(FILE*,struct ng_vvp*);
static char*robotron_all_signal_text(struct ng_vvp*);
static int robotron_scope_signals_inventory(FILE*,struct ng_vvp*);
static char*robotron_port_payload_text(struct ng_vvp*);
static int robotron_port_payload_inventory(FILE*,struct ng_vvp*);
static char*robotron_scope_metadata_text(struct ng_vvp*);
/* Compact only serialized log records. Snapshot buffers remain dense. */
#include <stdarg.h>
static char*robotron_metadata_previous[6];
static unsigned long long robotron_metadata_sequence[6];
static int robotron_metadata_log(FILE*out,const char*format,...)
{
    char*text=NULL;va_list args;va_start(args,format);
    int length=vasprintf(&text,format,args);va_end(args);if(length<0)return -1;
    const char*cursor=text;
    while(*cursor){
        const char*m=strstr(cursor,"VSM_BEGIN "),*r=strstr(cursor,"VSMR_BEGIN ");
        const char*p=strstr(cursor,"VPP_BEGIN ");
        const char*start=!m?r:!r?m:m<r?m:r;
        if(p&&(!start||p<start))start=p;
        const char*s=strstr(cursor,"VSA_BEGIN ");if(s&&(!start||s<start))start=s;
        const char*q=strstr(cursor,"VPM_BEGIN ");if(q&&(!start||q<start))start=q;
        const char*t=strstr(cursor,"VMM_BEGIN ");if(t&&(!start||t<start))start=t;
        if(!start){if(fputs(cursor,out)==EOF)goto failed;break;}
        if(start!=text && start[-1]!='\n')goto failed;
        if(fwrite(cursor,1,start-cursor,out)!=(size_t)(start-cursor))goto failed;
        unsigned index=start==t?5:start==q?4:start==s?3:start==p?2:start==r?1:0;const char*tag=index==5?"VMMD":index==4?"VPMD":index==3?"VSAD":index==2?"VPPD":index?"VSMRD":"VSMD";
        const char*footer=strstr(start,index==5?"\nVMM_END ":index==4?"\nVPM_END ":index==3?"\nVSA_END ":index==2?"\nVPP_END ":index?"\nVSMR_END ":"\nVSM_END ");
        const char*head=strchr(start,'\n');const char*end=footer?strchr(footer+1,'\n'):NULL;
        unsigned version;unsigned long long tick;
        if(!head||!end||sscanf(start,index==5?"VMM_BEGIN %u %llu":index==4?"VPM_BEGIN %u %llu":index==3?"VSA_BEGIN %u %llu":index==2?"VPP_BEGIN %u %llu":index?"VSMR_BEGIN %u %llu":"VSM_BEGIN %u %llu",&version,&tick)!=2||version!=1)goto failed;
        ++end;size_t bytes=end-head-1;char*body=malloc(bytes+1);if(!body)goto failed;
        memcpy(body,head+1,bytes);body[bytes]=0;
        unsigned full=!robotron_metadata_previous[index]||strcmp(body,robotron_metadata_previous[index]);
        if(robotron_metadata_sequence[index]==~0ULL){free(body);goto failed;}
        if(fprintf(out,"%s_BEGIN 1 %llu %llu %u %zu\n",tag,tick,robotron_metadata_sequence[index]+1,!!full,bytes)<0 ||
           (full&&fwrite(body,1,bytes,out)!=bytes) || fprintf(out,"%s_END\n",tag)<0 || ferror(out)){
            free(body);goto failed;
        }
        free(robotron_metadata_previous[index]);robotron_metadata_previous[index]=body;
        ++robotron_metadata_sequence[index];cursor=end;
    }
    free(text);return length;
failed:
    free(text);return -1;
}
static int robotron_scope_metadata_inventory(FILE*out,struct ng_vvp*ctx)
{
    int(*metadata)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_scope_metadata_inventory");
    int(*references)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_scope_metadata_reference_inventory");
    return !metadata||!references||metadata(out)||references(out)?-1:0;
}

static int robotron_typed_fault(struct ng_vvp*,int);
static char*robotron_typed_text(struct ng_vvp*);
static void robotron_typed_signal_reference(struct ng_vvp*);
static int robotron_typed_signal_inventory(FILE*,struct ng_vvp*);
static void robotron_callback_reference(struct ng_vvp*);
static int robotron_callback_inventory(FILE*,struct ng_vvp*);
static char* robotron_callback_text(struct ng_vvp*);

static int robotron_raw_assignment_inventory(FILE *f,struct ng_vvp *ctx)
{
    int (*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_assignment_raw_inventory");
    return inventory?inventory(f):-1;
}
static int robotron_raw_assignment_fault(struct ng_vvp *ctx,int operation)
{
    int (*toggle)(unsigned long long,int)=dlsym(ctx->vvp_handle,"robotron_vvp_assignment_raw_toggle");
    char *text=NULL;size_t size=0;FILE *f=open_memstream(&text,&size);
    if(!f || !toggle)return -1;
    int result=robotron_raw_assignment_inventory(f,ctx);if(fclose(f))result=-1;
    if(result){free(text);return -1;}
    unsigned long long selected=0;char *save=NULL;
    for(char *line=strtok_r(text,"\n",&save);line;line=strtok_r(NULL,"\n",&save)) {
        long long slot;char region[32];unsigned long long ordinal,id;void *address,*target;unsigned port,width;
        if(sscanf(line,"VAR_EVENT %lld %31s %llu %llu %p %p %u %u",&slot,region,&ordinal,&id,&address,&target,&port,&width)==8 && (operation!=0 || width)) {selected=id;break;}
    }
    free(text);return selected?toggle(selected,operation):0;
}


static int robotron_raw_island_inventory(FILE *f,struct ng_vvp *ctx)
{
    int (*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_island_raw_delta_inventory");
    return inventory ? inventory(f) : -1;
}
static int robotron_raw_island_fault(struct ng_vvp *ctx,int field)
{
    int (*toggle)(int,int)=dlsym(ctx->vvp_handle,"robotron_vvp_island_raw_toggle");
    int vector=field==1?1:0;int operation=field==0?0:field==1?2:1;
    return toggle?toggle(vector,operation):-1;
}
static void robotron_raw_island_reference(struct ng_vvp *ctx)
{
    static struct ng_vvp *owner;
    if(owner && owner!=ctx)exit(3);
    if(owner)return;
    int (*reference)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_island_raw_reference");
    if(!reference || reference(stderr))exit(2);
    owner=ctx;
}


static int robotron_resolver_inventory(FILE *f,struct ng_vvp *ctx)
{
    int (*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_resolver_delta_inventory");
    return inventory ? inventory(f) : -1;
}
static int robotron_resolver_fault(struct ng_vvp *ctx,int field)
{
    static unsigned long long saved;static unsigned saved_index;
    int (*toggle)(unsigned long long,int,unsigned)=dlsym(ctx->vvp_handle,"robotron_vvp_resolver_toggle");
    int (*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_resolver_inventory");
    if(!toggle || !inventory)return -1;
    if(saved){int result=toggle(saved,field,saved_index);if(result==1)saved=0;return result;}
    char *text=NULL;size_t size=0;FILE *f=open_memstream(&text,&size);if(!f)return -1;
    int result=inventory(f);if(fclose(f))result=-1;
    if(result){free(text);return -1;}
    char *cursor=text,*line;
    while((line=strsep(&cursor,"\n"))!=NULL){
        unsigned long long id;unsigned slots;
        if(sscanf(line,"VRS_NODE %llu %*s %*s %*u %*u %*s %*s %*s %u",&id,&slots)!=2)continue;
        for(unsigned index=0;index<((field==0 || field==6)?slots:1);index++){
            result=toggle(id,field,index);
            if(result){if(result==1){saved=id;saved_index=index;}free(text);return result;}
        }
    }
    free(text);return 0;
}
static void robotron_resolver_reference(struct ng_vvp *ctx)
{
    static struct ng_vvp *owner;
    if(owner && owner!=ctx)exit(3);
    if(owner)return;
    int (*reference)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_resolver_reference");
    if(!reference || reference(stderr))exit(2);
    owner=ctx;
}


static int robotron_concat_inventory(FILE *f,struct ng_vvp *ctx)
{
    int (*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_concat_delta_inventory");
    return inventory ? inventory(f) : -1;
}
static int robotron_concat_fault(struct ng_vvp *ctx,int field)
{
    static unsigned long long saved;
    int (*toggle)(unsigned long long,int)=dlsym(ctx->vvp_handle,"robotron_vvp_concat_toggle");
    int (*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_concat_inventory");
    if(!toggle || !inventory)return -1;
    if(saved){int result=toggle(saved,field);if(result==1)saved=0;return result;}
    char *text=NULL;size_t size=0;FILE *f=open_memstream(&text,&size);if(!f)return -1;
    int result=inventory(f);if(fclose(f))result=-1;
    if(result){free(text);return -1;}
    char *cursor=text,*line;
    while((line=strsep(&cursor,"\n"))!=NULL){
        unsigned long long id;int kind;
        if(sscanf(line,"VCN_NODE %llu %*s %*s %d",&id,&kind)!=2)continue;
        result=toggle(id,field);
        if(result){if(result==1)saved=id;free(text);return result;}
    }
    free(text);return 0;
}
static void robotron_concat_reference(struct ng_vvp *ctx)
{
    static struct ng_vvp *owner;
    if(owner && owner!=ctx)exit(3);
    if(owner)return;
    int (*reference)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_concat_reference");
    if(!reference || reference(stderr))exit(2);
    owner=ctx;
}


static int robotron_raw_wire_inventory(FILE *f,struct ng_vvp *ctx)
{
    int (*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_wire_raw_delta_inventory");
    return inventory ? inventory(f) : -1;
}
static int robotron_raw_wire_fault(struct ng_vvp *ctx,int field)
{
    static unsigned long long saved;
    int (*toggle)(unsigned long long,int)=dlsym(ctx->vvp_handle,"robotron_vvp_wire_raw_toggle");
    int (*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_wire_raw_inventory");
    if(!toggle || !inventory)return -1;
    if(saved){int result=toggle(saved,0);if(result==1)saved=0;return result;}
    char *text=NULL;size_t size=0;FILE *f=open_memstream(&text,&size);if(!f)return -1;
    int result=inventory(f);if(fclose(f))result=-1;
    if(result){free(text);return -1;}
    char *cursor=text,*line;
    while((line=strsep(&cursor,"\n"))!=NULL){
        unsigned long long id;
        if(sscanf(line,"VWB_FILTER %llu",&id)!=1)continue;
        result=toggle(id,0);
        if(result){if(result==1)saved=id;free(text);return result;}
    }
    free(text);return 0;
}
static void robotron_raw_wire_reference(struct ng_vvp *ctx)
{
    static struct ng_vvp *owner;
    if(owner && owner!=ctx)exit(3);
    if(owner)return;
    int (*reference)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_wire_raw_reference");
    if(!reference || reference(stderr))exit(2);
    owner=ctx;
}


static int robotron_reduction_inventory(FILE *f,struct ng_vvp *ctx)
{
    int (*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_reduction_delta_inventory");
    return inventory ? inventory(f) : -1;
}
static int robotron_reduction_fault(struct ng_vvp *ctx,int field)
{
    static unsigned long long saved;
    int (*toggle)(unsigned long long,int)=dlsym(ctx->vvp_handle,"robotron_vvp_reduction_toggle");
    int (*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_reduction_inventory");
    if(!toggle || !inventory)return -1;
    if(saved){int result=toggle(saved,field);if(result==1)saved=0;return result;}
    char *text=NULL;size_t size=0;FILE *f=open_memstream(&text,&size);if(!f)return -1;
    int result=inventory(f);if(fclose(f))result=-1;
    if(result){free(text);return -1;}
    char *cursor=text,*line;
    while((line=strsep(&cursor,"\n"))!=NULL){
        unsigned long long id;int kind;
        if(sscanf(line,"VRD_NODE %llu %*s %*s %d",&id,&kind)!=2)continue;
        result=toggle(id,field);
        if(result){if(result==1)saved=id;free(text);return result;}
    }
    free(text);return 0;
}
static void robotron_reduction_reference(struct ng_vvp *ctx)
{
    static struct ng_vvp *owner;
    if(owner && owner!=ctx)exit(3);
    if(owner)return;
    int (*reference)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_reduction_reference");
    if(!reference || reference(stderr))exit(2);
    owner=ctx;
}


static int robotron_arithmetic_inventory(FILE *f,struct ng_vvp *ctx)
{
    int (*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_arithmetic_delta_inventory");
    return inventory ? inventory(f) : -1;
}
static int robotron_arithmetic_fault(struct ng_vvp *ctx,int field)
{
    static unsigned long long saved;
    int (*toggle)(unsigned long long,int)=dlsym(ctx->vvp_handle,"robotron_vvp_arithmetic_toggle");
    int (*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_arithmetic_inventory");
    if(!toggle || !inventory)return -1;
    if(saved){int result=toggle(saved,field);if(result==1)saved=0;return result;}
    char *text=NULL;size_t size=0;FILE *f=open_memstream(&text,&size);if(!f)return -1;
    int result=inventory(f);if(fclose(f))result=-1;
    if(result){free(text);return -1;}
    char *cursor=text,*line;
    while((line=strsep(&cursor,"\n"))!=NULL){
        unsigned long long id;int kind;
        if(sscanf(line,"VAR_NODE %llu %*s %*s %d",&id,&kind)!=2)continue;
        result=toggle(id,field);
        if(result){if(result==1)saved=id;free(text);return result;}
    }
    free(text);return 0;
}
static void robotron_arithmetic_reference(struct ng_vvp *ctx)
{
    static struct ng_vvp *owner;
    if(owner && owner!=ctx)exit(3);
    if(owner)return;
    int (*reference)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_arithmetic_reference");
    if(!reference || reference(stderr))exit(2);
    owner=ctx;
}


static int robotron_gate_inventory(FILE *f,struct ng_vvp *ctx)
{
    int (*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_gate_delta_inventory");
    return inventory ? inventory(f) : -1;
}
static int robotron_gate_fault(struct ng_vvp *ctx,int field)
{
    static unsigned long long saved;
    int (*toggle)(unsigned long long,int)=dlsym(ctx->vvp_handle,"robotron_vvp_gate_toggle");
    int (*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_gate_inventory");
    if(!toggle || !inventory)return -1;
    if(saved){int result=toggle(saved,field);if(result==1)saved=0;return result;}
    char *text=NULL;size_t size=0;FILE *f=open_memstream(&text,&size);if(!f)return -1;
    int result=inventory(f);if(fclose(f))result=-1;
    if(result){free(text);return -1;}
    char *cursor=text,*line;
    while((line=strsep(&cursor,"\n"))!=NULL){
        unsigned long long id;int kind;
        if(sscanf(line,"VGL_GATE %llu %*s %*s %*s %d",&id,&kind)!=2 || kind>3)continue;
        result=toggle(id,field);
        if(result){if(result==1)saved=id;free(text);return result;}
    }
    free(text);return 0;
}
static void robotron_gate_reference(struct ng_vvp *ctx)
{
    static struct ng_vvp *owner;
    if(owner && owner!=ctx)exit(3);
    if(owner)return;
    int (*reference)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_gate_reference");
    if(!reference || reference(stderr))exit(2);
    owner=ctx;
}


static int robotron_mux_inventory(FILE *f,struct ng_vvp *ctx)
{
    int (*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_mux_delta_inventory");
    return inventory ? inventory(f) : -1;
}
static int robotron_mux_fault(struct ng_vvp *ctx,int field)
{
    int (*toggle)(int)=dlsym(ctx->vvp_handle,"robotron_vvp_mux_toggle");
    return toggle ? toggle(field) : -1;
}
static void robotron_mux_reference(struct ng_vvp *ctx)
{
    static struct ng_vvp *owner;
    if(owner && owner!=ctx)exit(3);
    if(owner)return;
    int (*reference)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_mux_reference");
    if(!reference || reference(stderr))exit(2);
    owner=ctx;
}


static int robotron_signal_inventory(FILE *f,struct ng_vvp *ctx)
{
    int (*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_signal_delta_inventory");
    return inventory ? inventory(f) : -1;
}
static int robotron_signal_fault(struct ng_vvp *ctx,int field)
{
    int (*toggle)(int)=dlsym(ctx->vvp_handle,"robotron_vvp_signal_toggle");
    return toggle ? toggle(field) : -1;
}
static void robotron_signal_reference(struct ng_vvp *ctx)
{
    static struct ng_vvp *owner;
    if(owner && owner!=ctx)exit(3);
    if(owner)return;
    int (*reference)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_signal_reference");
    int (*types)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_net_types");
    if(!reference || !types || types(stderr) || reference(stderr))exit(2);
    owner=ctx;
}


static int robotron_wire_inventory(FILE *f,struct ng_vvp *ctx)
{
    int (*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_wire_delta_inventory");
    return inventory ? inventory(f) : -1;
}
static int robotron_wire_fault(struct ng_vvp *ctx,int kind,int field)
{
    int (*toggle)(int,int)=dlsym(ctx->vvp_handle,"robotron_vvp_wire_toggle");
    return toggle ? toggle(kind,field) : -1;
}
static void robotron_wire_reference(struct ng_vvp *ctx)
{
    static struct ng_vvp *owner;
    if(owner && owner!=ctx)exit(3);
    if(owner)return;
    int (*reference)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_wire_reference");
    if(!reference || reference(stderr))exit(2);
    owner=ctx;
}


static int robotron_net_inventory(FILE *f,struct ng_vvp *ctx)
{
    int (*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_net_delta_inventory");
    return inventory ? inventory(f) : -1;
}
static int robotron_net_fault(struct ng_vvp *ctx,int field)
{
    int (*toggle)(int)=dlsym(ctx->vvp_handle,"robotron_vvp_net_toggle");
    return toggle ? toggle(field) : -1;
}
static void robotron_net_reference(struct ng_vvp *ctx)
{
    static struct ng_vvp *owner;
    if(owner && owner!=ctx)exit(3);
    if(owner)return;
    int (*reference)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_net_reference");
    if(!reference || reference(stderr))exit(2);
    owner=ctx;
}


static int robotron_array_inventory(FILE *f,struct ng_vvp *ctx)
{
    int (*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_array_compact_inventory");
    return inventory ? inventory(f) : -1;
}
static int robotron_array_fault(struct ng_vvp *ctx,int field)
{
    int (*toggle)(int)=dlsym(ctx->vvp_handle,"robotron_vvp_array_toggle");
    return toggle ? toggle(field) : -1;
}


static int robotron_operand_inventory(FILE *f,struct ng_vvp *ctx)
{
    int (*inventory)(FILE*,int)=dlsym(ctx->vvp_handle,"robotron_vvp_code_operand_inventory");
    return inventory ? inventory(f,1) : -1;
}
static int robotron_operand_fault(struct ng_vvp *ctx,int field)
{
    int (*toggle)(int)=dlsym(ctx->vvp_handle,"robotron_vvp_code_operand_toggle");
    return toggle ? toggle(field) : -1;
}
static void robotron_operand_reference(struct ng_vvp *ctx)
{
    static struct ng_vvp *owner;
    if(owner && owner!=ctx)exit(3);
    if(owner)return;
    int (*reference)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_code_operand_reference");
    if(!reference || reference(stderr))exit(2);
    owner=ctx;
}


static int robotron_scope_inventory(FILE *f,struct ng_vvp *ctx)
{
    int (*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_scope_inventory");
    return inventory ? inventory(f) : -1;
}
static int robotron_scope_fault(struct ng_vvp *ctx)
{
    int (*toggle)(void)=dlsym(ctx->vvp_handle,"robotron_vvp_scope_toggle");
    return toggle ? toggle() : -1;
}


static int robotron_code_inventory(FILE *f,struct ng_vvp *ctx)
{
    int (*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_thread_code_inventory");
    return inventory ? inventory(f) : -1;
}
static int robotron_code_fault(struct ng_vvp *ctx,int field)
{
    int (*toggle)(int)=dlsym(ctx->vvp_handle,"robotron_vvp_thread_toggle");
    return toggle ? toggle(field) : -1;
}


static int robotron_wait_inventory(FILE *f,struct ng_vvp *ctx)
{
    int (*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_wait_inventory");
    return inventory ? inventory(f) : -1;
}
static int robotron_wait_fault(struct ng_vvp *ctx,int field)
{
    int (*toggle)(int)=dlsym(ctx->vvp_handle,"robotron_vvp_wait_toggle");
    return toggle ? toggle(field) : -1;
}


static int robotron_thread_inventory(FILE *f,struct ng_vvp *ctx)
{
    int (*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_thread_compact_inventory");
    int (*queue)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_thread_queue_inventory");
    return inventory && queue ? (inventory(f) || queue(f)) : -1;
}
static int robotron_thread_fault(struct ng_vvp *ctx,int field)
{
    int (*toggle)(int)=dlsym(ctx->vvp_handle,"robotron_vvp_thread_toggle");
    int (*queue)(void)=dlsym(ctx->vvp_handle,"robotron_vvp_thread_queue_toggle");
    return field==8 ? (queue?queue():-1) : (toggle?toggle(field):-1);
}


static int robotron_filter_inventory(FILE *f,struct ng_vvp *ctx)
{
    int (*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_island_filter_inventory");
    return inventory?inventory(f):-1;
}
static int robotron_filter_fault(struct ng_vvp *ctx,int field)
{
    int (*toggle)(int)=dlsym(ctx->vvp_handle,"robotron_vvp_island_filter_toggle");
    return toggle?toggle(field):-1;
}


static int robotron_island_inventory(FILE *f,struct ng_vvp *ctx)
{
    int (*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_island_inventory");
    int (*queue)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_island_queue_inventory");
    return inventory && queue ? (inventory(f) || queue(f)) : -1;
}
static int robotron_island_fault(struct ng_vvp *ctx,int field)
{
    int (*toggle)(int)=dlsym(ctx->vvp_handle,"robotron_vvp_island_toggle");
    int (*queue)(void)=dlsym(ctx->vvp_handle,"robotron_vvp_island_queue_toggle");
    return field==6 ? (queue?queue():-1) : (toggle?toggle(field):-1);
}


static int robotron_primitive_inventory(FILE *f,struct ng_vvp *ctx)
{
    int (*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_primitive_inventory");
    return inventory ? inventory(f) : -1;
}
static int robotron_primitive_fault(struct ng_vvp *ctx,int kind,int field)
{
    int (*toggle)(int,int)=dlsym(ctx->vvp_handle,"robotron_vvp_primitive_toggle");
    return toggle ? toggle(kind,field) : -1;
}


static int robotron_assignment_inventory(FILE *f,struct ng_vvp *ctx)
{
    int (*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_assignment_inventory");
    return inventory ? inventory(f) : -1;
}
static int robotron_assignment_fault(struct ng_vvp *ctx,int kind,int field)
{
    int (*toggle)(int,int)=dlsym(ctx->vvp_handle,"robotron_vvp_assignment_toggle");
    return toggle ? toggle(kind,field) : -1;
}

/* The startup callback is removed from its pending list before the first
 * coroutine yield. Its runtime lifetime remains live until start_cb returns. */
typedef unsigned long long (*startup_lookup_fn)(const void*,int32_t(*)(struct t_cb_data*),char*);
typedef int (*startup_toggle_fn)(const void*,int32_t(*)(struct t_cb_data*),char*,int);
static struct ng_vvp *robotron_start_context;
static struct __vpiHandle *robotron_start_callback;
static int32_t (*robotron_start_function)(struct t_cb_data*);
static unsigned long long robotron_start_lifetime;
static int robotron_start_phase;
static startup_lookup_fn robotron_start_lookup;
static startup_toggle_fn robotron_start_toggle;

void Robotron_start_registration(struct ng_vvp *ctx,struct __vpiHandle *callback,
                                 int32_t (*function)(struct t_cb_data*))
{
    if (!ctx || !callback || !function || robotron_start_context) exit(2);
    robotron_start_lookup=dlsym(ctx->vvp_handle,"robotron_vvp_start_identity");
    robotron_start_toggle=dlsym(ctx->vvp_handle,"robotron_vvp_start_toggle");
    if (!robotron_start_lookup || !robotron_start_toggle) exit(2);
    robotron_start_lifetime=robotron_start_lookup(callback,function,(char*)ctx);
    if (!robotron_start_lifetime) exit(2);
    robotron_start_context=ctx;robotron_start_callback=callback;robotron_start_function=function;
}

void Robotron_start_phase(struct ng_vvp *ctx,int phase)
{
    if (ctx!=robotron_start_context || phase!=robotron_start_phase+1 || phase>2) exit(2);
    robotron_start_phase=phase;
}

static int robotron_start_inventory(FILE *f,struct ng_vvp *ctx)
{
    if (ctx!=robotron_start_context || !robotron_start_lookup ||
        (robotron_start_phase!=1 && robotron_start_phase!=2)) return -1;
    unsigned long long id=robotron_start_lookup(robotron_start_callback,robotron_start_function,(char*)ctx);
    /* Phase 2 is observed only after return to the scheduler and destruction.
     * Never dereference the saved opaque callback after its lifetime ends. */
    if (id!=(robotron_start_phase==1 ? robotron_start_lifetime : 0)) return -1;
    return fprintf(f,"VS_START %d %llu %llu\n",robotron_start_phase,robotron_start_lifetime,id)<0 ? -1 : 0;
}

static int robotron_start_fault(int field)
{
    if (robotron_start_phase!=1 || !robotron_start_toggle) return -1;
    return robotron_start_toggle(robotron_start_callback,robotron_start_function,(char*)robotron_start_context,field);
}

/* SPICE owns the coroutine mutex at these boundaries. Typed APIs are resolved
 * from the actual loaded module; supplied opaque handles are never unpacked. */
typedef unsigned long long (*display_lookup_fn)(const void*, int32_t(*)(struct t_cb_data*), char*);
typedef int (*display_null_fn)(const void*, int32_t(*)(struct t_cb_data*), char*);
struct display_board_api {
    int (*family)(FILE*, char*, int32_t(*)(struct t_cb_data*));
    int (*payload)(FILE*);
    int (*association)(FILE*, display_lookup_fn);
    int (*mutate)(display_null_fn);
    display_lookup_fn lookup;
    display_null_fn toggle;
    int (*executing)(FILE*);
    int (*toggle_delete)(void);
};
static struct display_board_api display_api(struct ng_vvp *ctx)
{
    struct display_board_api api;
    const char *path = getenv("ROBOTRON_DISPLAY_MODULE");
    void *module = path && path[0] == '/' ? dlopen(path, RTLD_LAZY | RTLD_NOLOAD) : NULL;
    if (!module || ctx != robotron_identity_context || !robotron_stop_function) {
        robotron_metadata_log(stderr, "Missing loaded display module or stop identity\n"); exit(2);
    }
    api.family = dlsym(ctx->vvp_handle, "robotron_vvp_sync_family_inventory");
    api.lookup = dlsym(ctx->vvp_handle, "robotron_vvp_sync_payload_identity");
    api.toggle = dlsym(ctx->vvp_handle, "robotron_vvp_sync_toggle_payload_null");
    api.executing = dlsym(ctx->vvp_handle, "robotron_vvp_executing_inventory");
    api.toggle_delete = dlsym(ctx->vvp_handle, "robotron_vvp_executing_toggle_delete");
    api.payload = dlsym(module, "robotron_display_inventory");
    api.association = dlsym(module, "robotron_display_associations");
    api.mutate = dlsym(module, "robotron_display_toggle_callback_data");
    dlclose(module); /* The simulator retains ownership of its loaded module. */
    if (!api.family || !api.lookup || !api.toggle || !api.payload || !api.association || !api.mutate || !api.executing || !api.toggle_delete) {
        robotron_metadata_log(stderr, "Missing typed display board API\n"); exit(2);
    }
    return api;
}

/* A saved stop handle is opaque. The runtime compares it against its live
 * registry before checking the known function/context; no stale dereference. */
static int display_stop_link(FILE *f, struct ng_vvp *ctx, struct display_board_api api)
{
    unsigned long long id = 0;
    if (ctx->stop_cb) {
        id = api.lookup(ctx->stop_cb, robotron_stop_function, (char*)ctx);
        if (!id) return -1;
    }
    return fprintf(f, "VR_BEGIN 1 %d %llu\nVR_END\n", ctx->stop_cb != NULL, id) < 0 ? -1 : 0;
}

/* Registered on the HDL thread after all ports and output values are seeded,
 * before its first yield. Input-only `new` is intentionally never inspected. */
struct robotron_port_identity {
    struct __vpiHandle *handle;
    uint16_t bits;
    uint32_t position;
    char *name;
};
static struct ng_vvp *robotron_ports_context;
static struct ngvp_port *robotron_ports_base;
static struct co_info *robotron_ports_cosim;
static void *robotron_ports_library;
static uint32_t robotron_ports_ins, robotron_ports_outs, robotron_ports_inouts;
static size_t robotron_ports_count;
static struct robotron_port_identity *robotron_ports_ids;

void Robotron_ports_identity(struct ng_vvp *ctx,
                            char *(*name)(int32_t, struct __vpiHandle*), int32_t property)
{
    if (!ctx || ctx != robotron_identity_context || !name || robotron_ports_context ||
        !ctx->ports || !ctx->cosim_context || !ctx->vvp_handle) {
        robotron_metadata_log(stderr,"Invalid port identity handoff\n"); exit(2);
    }
    uint64_t count = (uint64_t)ctx->ins + ctx->outs + ctx->inouts;
    if (!count || count > SIZE_MAX / sizeof(*robotron_ports_ids)) exit(2);
    robotron_ports_ids = calloc((size_t)count, sizeof(*robotron_ports_ids));
    if (!robotron_ports_ids) exit(2);
    uint64_t position = 0;
    for (size_t i=0; i<count; ++i) {
        struct ngvp_port *p=ctx->ports+i;
        if (i==0 || i==ctx->ins || i==(uint64_t)ctx->ins+ctx->outs) position=0;
        if (!p->handle || p->ctx!=ctx || !p->bits || p->bits>32 || p->position!=position) exit(2);
        position += p->bits;
        const char *text=name(property,p->handle);
        if (!text || !*text) exit(2);
        for (size_t j=0; j<i; ++j)
            if (robotron_ports_ids[j].handle==p->handle || !strcmp(robotron_ports_ids[j].name,text)) exit(2);
        robotron_ports_ids[i].handle=p->handle;
        robotron_ports_ids[i].bits=p->bits;
        robotron_ports_ids[i].position=p->position;
        robotron_ports_ids[i].name=strdup(text);
        if (!robotron_ports_ids[i].name) exit(2);
    }
    robotron_ports_context=ctx; robotron_ports_base=ctx->ports;
    robotron_ports_cosim=ctx->cosim_context; robotron_ports_library=ctx->vvp_handle;
    robotron_ports_ins=ctx->ins; robotron_ports_outs=ctx->outs; robotron_ports_inouts=ctx->inouts;
    robotron_ports_count=(size_t)count;
}

static int robotron_ports_inventory(FILE *f, struct ng_vvp *ctx)
{
    if (!f || !ctx || ctx!=robotron_ports_context || ctx->ports!=robotron_ports_base ||
        ctx->cosim_context!=robotron_ports_cosim || ctx->vvp_handle!=robotron_ports_library ||
        ctx->ins!=robotron_ports_ins || ctx->outs!=robotron_ports_outs || ctx->inouts!=robotron_ports_inouts) return -1;
    uint32_t inputs=0,outputs=0;
    /* Check identities before any handle use or observation of port values. */
    for (size_t i=0; i<robotron_ports_count; ++i) {
        const struct ngvp_port *p=ctx->ports+i;
        const struct robotron_port_identity *id=robotron_ports_ids+i;
        unsigned allowed=i<ctx->ins ? IN_PENDING : (i<(uint64_t)ctx->ins+ctx->outs ? OUT_PENDING : IN_PENDING|OUT_PENDING);
        if (p->handle!=id->handle || p->ctx!=ctx || p->bits!=id->bits || p->position!=id->position || (p->flags & ~allowed)) return -1;
        inputs += !!(p->flags & IN_PENDING); outputs += !!(p->flags & OUT_PENDING);
    }
    if (inputs!=ctx->in_pending || outputs!=ctx->out_pending || (ctx->stop!=0 && ctx->stop!=1)) return -1;
    if (fprintf(f,"VP_BEGIN 1 %u %u %u\nVP_CONTEXT %a %a %u %u %d\n",ctx->ins,ctx->outs,ctx->inouts,
                ctx->base_time,ctx->tick_length,ctx->in_pending,ctx->out_pending,ctx->stop)<0) return -1;
    for (size_t i=0; i<robotron_ports_count; ++i) {
        const struct ngvp_port *p=ctx->ports+i;
        unsigned direction=i<ctx->ins ? 1 : (i<(uint64_t)ctx->ins+ctx->outs ? 2 : 3);
        if (fprintf(f,"VP_PORT %zu %u %u %u %u %d %d ",i,direction,p->bits,p->position,p->flags,p->previous.aval,p->previous.bval)<0) return -1;
        if (direction==1) {
            if (fprintf(f,"- - ")<0) return -1;
        } else if (fprintf(f,"%d %d ",p->new.aval,p->new.bval)<0) return -1;
        for (const unsigned char *s=(const unsigned char*)robotron_ports_ids[i].name; *s; ++s)
            if (fprintf(f,"%02x",*s)<0) return -1;
        if (fprintf(f,"\n")<0) return -1;
    }
    return fprintf(f,"VP_END\n")<0 || ferror(f) ? -1 : 0;
}

/* watch() runs before pp metadata is initialized: record opaque identities
 * here, and read port fields only in the paused, initialized inventory. */
typedef unsigned long long (*output_lookup_fn)(const void*,int32_t(*)(struct t_cb_data*),char*,struct __vpiHandle*);
typedef int (*output_toggle_fn)(const void*,int32_t(*)(struct t_cb_data*),char*,struct __vpiHandle*,int);
struct robotron_output_identity {
    struct ngvp_port *port;
    struct __vpiHandle *callback, *signal;
    int32_t (*function)(struct t_cb_data*);
    unsigned long long lifetime;
};
static struct robotron_output_identity *robotron_outputs;
static size_t robotron_outputs_count,robotron_outputs_capacity;
static output_lookup_fn robotron_output_lookup;
static output_toggle_fn robotron_output_toggle;

void Robotron_output_registration(void *port,struct __vpiHandle *callback,
                                  int32_t (*function)(struct t_cb_data*),struct __vpiHandle *signal)
{
    struct ng_vvp *ctx=robotron_identity_context;
    if (!ctx || !ctx->ports || !port || !callback || !function || !signal) exit(2);
    size_t count=(size_t)ctx->outs+ctx->inouts;
    if (!robotron_outputs) {
        if (!count || count>SIZE_MAX/sizeof(*robotron_outputs)) exit(2);
        robotron_outputs=calloc(count,sizeof(*robotron_outputs));
        if (!robotron_outputs) exit(2);
        robotron_outputs_capacity=count;
        robotron_output_lookup=dlsym(ctx->vvp_handle,"robotron_vvp_value_identity");
        robotron_output_toggle=dlsym(ctx->vvp_handle,"robotron_vvp_value_toggle");
        if (!robotron_output_lookup || !robotron_output_toggle) exit(2);
    }
    if (count!=robotron_outputs_capacity || robotron_outputs_count>=count) exit(2);
    size_t index=0;
    while (index<count && port!=(void*)(ctx->ports+ctx->ins+index)) ++index;
    if (index==count || robotron_outputs[index].port) exit(2);
    for (size_t i=0;i<count;i++)
        if (robotron_outputs[i].callback==callback) exit(2);
    unsigned long long id=robotron_output_lookup(callback,function,port,signal);
    if (!id) exit(2);
    robotron_outputs[index]=(struct robotron_output_identity){port,callback,signal,function,id};
    ++robotron_outputs_count;
}

static int robotron_output_inventory(FILE *f,struct ng_vvp *ctx)
{
    if (ctx!=robotron_ports_context || !robotron_outputs || !robotron_output_lookup ||
        robotron_outputs_count!=(size_t)ctx->outs+ctx->inouts) return -1;
    if (fprintf(f,"VW_BEGIN 1 %zu\n",robotron_outputs_count)<0) return -1;
    for (size_t i=0;i<robotron_outputs_count;i++) {
        const struct robotron_output_identity *r=robotron_outputs+i;
        struct ngvp_port *port=ctx->ports+ctx->ins+i;
        if (r->port!=port || port->handle!=r->signal || port->ctx!=ctx ||
            robotron_output_lookup(r->callback,r->function,(char*)port,r->signal)!=r->lifetime) return -1;
        if (fprintf(f,"VW_LINK %zu %llu\n",(size_t)ctx->ins+i,r->lifetime)<0) return -1;
    }
    return fprintf(f,"VW_END\n")<0 || ferror(f) ? -1 : 0;
}

static int robotron_output_fault(int field)
{
    if (!robotron_outputs_count || !robotron_output_toggle) return -1;
    const struct robotron_output_identity *r=robotron_outputs;
    return robotron_output_toggle(r->callback,r->function,(char*)r->port,r->signal,field);
}

static char *display_snapshot(struct ng_vvp *ctx, struct display_board_api api)
{
    char *text = NULL; size_t length = 0;
    FILE *f = open_memstream(&text, &length);
    if (!f) exit(2);
    int failed = fprintf(f, "VA_BEGIN\n") < 0 ||
        api.family(f, (char*)ctx, robotron_stop_function) || api.payload(f) ||
        api.association(f, api.lookup) || display_stop_link(f, ctx, api) || api.executing(f) || robotron_ports_inventory(f, ctx) || robotron_output_inventory(f, ctx) || robotron_start_inventory(f, ctx) || robotron_assignment_inventory(f, ctx) || robotron_primitive_inventory(f, ctx) || robotron_island_inventory(f, ctx) || robotron_filter_inventory(f, ctx) || robotron_thread_inventory(f, ctx) || robotron_wait_inventory(f, ctx) || robotron_code_inventory(f, ctx) || robotron_scope_inventory(f, ctx) || robotron_operand_inventory(f, ctx) || robotron_array_inventory(f, ctx) || robotron_net_inventory(f, ctx) || robotron_wire_inventory(f, ctx) || robotron_signal_inventory(f, ctx) || robotron_mux_inventory(f, ctx) || robotron_gate_inventory(f, ctx) || robotron_arithmetic_inventory(f, ctx) || robotron_reduction_inventory(f, ctx) || robotron_raw_wire_inventory(f, ctx) || robotron_concat_inventory(f, ctx) || robotron_resolver_inventory(f, ctx) || robotron_raw_island_inventory(f, ctx) || robotron_raw_assignment_inventory(f, ctx) || robotron_callback_inventory(f, ctx) || robotron_typed_signal_inventory(f, ctx) || robotron_scope_metadata_inventory(f, ctx) || robotron_port_payload_inventory(f, ctx) || robotron_scope_signals_inventory(f, ctx) || robotron_parameter_inventory(f, ctx) || robotron_memory_inventory(f, ctx) || fprintf(f, "VA_END\n") < 0;
    if (fclose(f)) failed = 1;
    if (failed) {free(text); return NULL;}
    return text;
}
static char *display_payload_text(struct display_board_api api)
{
    char *text = NULL; size_t length = 0;
    FILE *f = open_memstream(&text, &length);
    if (!f) exit(2);
    int failed = api.payload(f);
    if (fclose(f)) failed = 1;
    if (failed) {free(text); return NULL;}
    return text;
}
static void private_sync_boundary(struct co_info *info, const char *phase)
{
    const char *mode = getenv("ROBOTRON_PRIVATE_DISPLAY");
    if (!mode || !strcmp(mode, "off")) return;
    if (strcmp(mode, "observe") && strcmp(mode, "corrupt") && strcmp(mode, "stop-corrupt") && strcmp(mode, "wrapper-corrupt") && strcmp(mode,"port-handle-corrupt") && strcmp(mode,"port-context-corrupt") && strcmp(mode,"port-value-corrupt") && strcmp(mode,"output-user-corrupt") && strcmp(mode,"output-object-corrupt") && strcmp(mode,"output-function-corrupt") && strcmp(mode,"output-link-corrupt") && strcmp(mode,"startup-user-corrupt") && strcmp(mode,"startup-function-corrupt") && strcmp(mode,"startup-time-corrupt") && strcmp(mode,"startup-link-corrupt") && strcmp(mode,"assignment-v4-value-corrupt") && strcmp(mode,"assignment-v4-target-corrupt") && strcmp(mode,"assignment-v4-width-corrupt") && strcmp(mode,"assignment-v8-value-corrupt") && strcmp(mode,"assignment-v8-target-corrupt") && strcmp(mode,"assignment-v8-strength-corrupt") && strcmp(mode,"primitive-not-value-corrupt") && strcmp(mode,"primitive-not-target-corrupt") && strcmp(mode,"primitive-part-value-corrupt") && strcmp(mode,"primitive-part-target-corrupt") && strcmp(mode,"primitive-part-base-corrupt") && strcmp(mode,"island-flag-corrupt") && strcmp(mode,"island-input-corrupt") && strcmp(mode,"island-output-corrupt") && strcmp(mode,"island-strength-corrupt") && strcmp(mode,"island-enable-corrupt") && strcmp(mode,"island-mesh-corrupt") && strcmp(mode,"island-queue-corrupt") && strcmp(mode,"filter-init-corrupt") && strcmp(mode,"filter-driven-corrupt") && strcmp(mode,"filter-propagate-corrupt") && strcmp(mode,"filter-strength-corrupt") && strcmp(mode,"thread-schedule-corrupt") && strcmp(mode,"thread-flag-corrupt") && strcmp(mode,"thread-word-corrupt") && strcmp(mode,"thread-pc-corrupt") && strcmp(mode,"thread-wait-corrupt") && strcmp(mode,"thread-queue-corrupt") && strcmp(mode,"wait-head-corrupt") && strcmp(mode,"wait-mask-corrupt") && strcmp(mode,"wait-history-corrupt") && strcmp(mode,"wait-cache-corrupt") && strcmp(mode,"code-null-corrupt") && strcmp(mode,"code-foreign-corrupt") && strcmp(mode,"scope-startup-corrupt") && strcmp(mode,"scope-late-corrupt") && strcmp(mode,"operand-immediate-corrupt") && strcmp(mode,"operand-target-corrupt") && strcmp(mode,"operand-handle-corrupt") && strcmp(mode,"operand-unknown-corrupt") && strcmp(mode,"array-word-corrupt") && strcmp(mode,"array-address-corrupt") && strcmp(mode,"array-link-corrupt") && strcmp(mode,"array-cache-corrupt") && strcmp(mode,"net-head-corrupt") && strcmp(mode,"net-link-corrupt") && strcmp(mode,"net-tag-corrupt") && strcmp(mode,"net-fun-corrupt") && strcmp(mode,"net-filter-corrupt") && strcmp(mode,"net-foreign-corrupt") && strcmp(mode,"wire4-init-corrupt") && strcmp(mode,"wire4-driven-corrupt") && strcmp(mode,"wire4-propagate-corrupt") && strcmp(mode,"wire8-init-corrupt") && strcmp(mode,"wire8-driven-corrupt") && strcmp(mode,"wire8-propagate-corrupt") && strcmp(mode,"signal-init-corrupt") && strcmp(mode,"signal-value-corrupt") && strcmp(mode,"signal-active-corrupt") && strcmp(mode,"mux-a-corrupt") && strcmp(mode,"mux-b-corrupt") && strcmp(mode,"mux-select-corrupt") && strcmp(mode,"mux-run-corrupt") && strcmp(mode,"gate-input0-corrupt") && strcmp(mode,"gate-input1-corrupt") && strcmp(mode,"gate-input2-corrupt") && strcmp(mode,"gate-input3-corrupt") && strcmp(mode,"gate-invert-corrupt") && strcmp(mode,"arithmetic-input0-corrupt") && strcmp(mode,"arithmetic-input1-corrupt") && strcmp(mode,"arithmetic-fallback-corrupt") && strcmp(mode,"arithmetic-width-corrupt") && strcmp(mode,"reduction-bit-corrupt") && strcmp(mode,"reduction-size-corrupt") && strcmp(mode,"raw-wire-corrupt") && strcmp(mode,"raw-wire-delayed-corrupt") && strcmp(mode,"concat-cache-corrupt") && strcmp(mode,"concat-width-corrupt") && strcmp(mode,"concat-raw-corrupt") && strcmp(mode,"resolver-cache-corrupt") && strcmp(mode,"resolver-allocation-corrupt") && strcmp(mode,"resolver-raw-corrupt") && strcmp(mode,"raw-island-cache-corrupt") && strcmp(mode,"raw-island-width-corrupt") && strcmp(mode,"raw-island-raw-corrupt") && strcmp(mode,"raw-assignment-byte-corrupt") && strcmp(mode,"raw-assignment-width-corrupt") && strcmp(mode,"raw-assignment-port-corrupt") && strcmp(mode,"callback-list-user-corrupt") && strcmp(mode,"callback-list-object-corrupt") && strcmp(mode,"callback-list-function-corrupt") && strcmp(mode,"callback-list-link-corrupt") && strcmp(mode,"typed-signal-signed-corrupt") && strcmp(mode,"typed-signal-range-corrupt") && strcmp(mode,"typed-signal-node-corrupt") && strcmp(mode,"typed-signal-name-corrupt") && strcmp(mode,"typed-signal-cache-corrupt") && strcmp(mode,"typed-signal-scope-corrupt") && strcmp(mode,"scope-metadata-units-corrupt") && strcmp(mode,"scope-metadata-line-corrupt") && strcmp(mode,"scope-metadata-function-type-corrupt") && strcmp(mode,"scope-metadata-function-width-corrupt") && strcmp(mode,"scope-metadata-function-init-corrupt") && strcmp(mode,"scope-metadata-intern-corrupt") && strcmp(mode,"port-payload-index-corrupt") && strcmp(mode,"port-payload-direction-corrupt") && strcmp(mode,"port-payload-bit-index-corrupt") && strcmp(mode,"port-payload-width-corrupt") && strcmp(mode,"port-payload-parent-corrupt") && strcmp(mode,"port-payload-name-pointer-corrupt") && strcmp(mode,"port-payload-net-reference-corrupt") && strcmp(mode,"port-payload-bit-parent-corrupt") && strcmp(mode,"port-payload-readiness-corrupt") && strcmp(mode,"scope-signal-signed-corrupt") && strcmp(mode,"scope-signal-range-corrupt") && strcmp(mode,"scope-signal-node-corrupt") && strcmp(mode,"scope-signal-name-corrupt") && strcmp(mode,"scope-signal-cache-corrupt") && strcmp(mode,"scope-signal-scope-corrupt") && strcmp(mode,"parameter-word-corrupt") && strcmp(mode,"parameter-signed-corrupt") && strcmp(mode,"parameter-sized-corrupt") && strcmp(mode,"parameter-local-corrupt") && strcmp(mode,"parameter-file-corrupt") && strcmp(mode,"parameter-line-corrupt") && strcmp(mode,"parameter-name-corrupt") && strcmp(mode,"parameter-width-corrupt") && strcmp(mode,"parameter-scope-corrupt") && strcmp(mode,"parameter-name-pointer-corrupt")) {
        robotron_metadata_log(stderr, "Invalid display board mode\n"); exit(2);
    }
    static unsigned long long ordinal;
    static int parameter_fault_done;
    if(parameter_fault_done)return;
    if(strncmp(mode,"parameter-",10))exit(3);
    if(ordinal && (info->vtime<5e-6 || strcmp(phase,"before-step"))){++ordinal;return;}
    struct ng_vvp *ctx = (struct ng_vvp*)info->handle;
    struct display_board_api api = display_api(ctx);

    robotron_operand_reference(ctx);
    robotron_net_reference(ctx);
    robotron_wire_reference(ctx);
    robotron_signal_reference(ctx);
    robotron_mux_reference(ctx);
    robotron_gate_reference(ctx);
    robotron_arithmetic_reference(ctx);
    robotron_reduction_reference(ctx);
    robotron_raw_wire_reference(ctx);
    robotron_concat_reference(ctx);
    robotron_resolver_reference(ctx);
    robotron_raw_island_reference(ctx);
    robotron_callback_reference(ctx);
    robotron_typed_signal_reference(ctx);
    char *before = display_snapshot(ctx, api);
    if (!before) {robotron_metadata_log(stderr, "Invalid display association\n"); exit(2);}
    robotron_metadata_log(stderr, "VB_BRIDGE %llu %s %.17g\nVB_STAGE before\n%s", ordinal++, phase, info->vtime, before);

































    int parameter_field=!strcmp(mode,"parameter-word-corrupt")?0:!strcmp(mode,"parameter-signed-corrupt")?1:!strcmp(mode,"parameter-sized-corrupt")?2:!strcmp(mode,"parameter-local-corrupt")?3:!strcmp(mode,"parameter-file-corrupt")?4:!strcmp(mode,"parameter-line-corrupt")?5:!strcmp(mode,"parameter-name-corrupt")?6:!strcmp(mode,"parameter-width-corrupt")?9:!strcmp(mode,"parameter-scope-corrupt")?10:!strcmp(mode,"parameter-name-pointer-corrupt")?11:-1;
    if(parameter_field>=0 && info->vtime>=5e-6){
        int(*toggle)(unsigned)=dlsym(ctx->vvp_handle,"robotron_vvp_parameter_toggle");
        char*direct_before=robotron_parameter_text(ctx);if(!toggle||!direct_before)exit(2);
        if(toggle(parameter_field)!=1)exit(2);
        char*direct=robotron_parameter_text(ctx);char*changed=display_snapshot(ctx,api);
        if(toggle(parameter_field)!=1)exit(3);
        char*restored=display_snapshot(ctx,api);
        int direct_ok=parameter_field<7?(direct&&strcmp(direct_before,direct)!=0):direct==NULL;
        int changed_ok=changed&&strcmp(before,changed)!=0,rejected=changed==NULL;
        int equal=restored&&!strcmp(before,restored);
        if(changed)robotron_metadata_log(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)robotron_metadata_log(stderr,"VB_STAGE restored\n%s",restored);
        robotron_metadata_log(stderr,"VB_PARAMETER_FAULT field=%d direct=%d changed=%d rejected=%d restored=%d\n",parameter_field,direct_ok,changed_ok,rejected,equal);
        free(direct_before);free(direct);free(before);free(changed);free(restored);
        if(!(direct_ok&&equal&&(parameter_field<7?changed_ok:rejected)))exit(3);
        parameter_fault_done=1;return;
    }

    int all_signal_field=!strcmp(mode,"scope-signal-signed-corrupt")?0:!strcmp(mode,"scope-signal-range-corrupt")?1:!strcmp(mode,"scope-signal-node-corrupt")?2:!strcmp(mode,"scope-signal-name-corrupt")?3:!strcmp(mode,"scope-signal-cache-corrupt")?4:!strcmp(mode,"scope-signal-scope-corrupt")?5:-1;
    if(all_signal_field>=0 && robotron_start_phase==1){
        int(*toggle)(unsigned)=dlsym(ctx->vvp_handle,"robotron_vvp_scope_signal_toggle");
        char*direct_before=robotron_all_signal_text(ctx);char*admitted_before=robotron_typed_text(ctx);if(!toggle||!direct_before||!admitted_before)exit(2);
        if(toggle(all_signal_field)!=1)exit(2);
        char*direct=robotron_all_signal_text(ctx);char*admitted_after=robotron_typed_text(ctx);int admitted_equal=admitted_after&&!strcmp(admitted_before,admitted_after);char*changed=display_snapshot(ctx,api);
        if(toggle(all_signal_field)!=1)exit(3);
        char*restored=display_snapshot(ctx,api);
        int direct_ok=all_signal_field<2?(direct&&strcmp(direct_before,direct)!=0):direct==NULL;
        int changed_ok=changed&&strcmp(before,changed)!=0,rejected=changed==NULL;
        int equal=restored&&!strcmp(before,restored);
        if(changed)robotron_metadata_log(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)robotron_metadata_log(stderr,"VB_STAGE restored\n%s",restored);
        robotron_metadata_log(stderr,"VB_SCOPE_SIGNAL_FAULT field=%d direct=%d changed=%d rejected=%d restored=%d admitted_unchanged=%d\n",all_signal_field,direct_ok,changed_ok,rejected,equal,admitted_equal);
        free(admitted_before);free(admitted_after);free(direct_before);free(direct);free(before);free(changed);free(restored);
        exit(admitted_equal&&direct_ok&&equal&&(all_signal_field<2?changed_ok:rejected)?2:3);
    }

    int port_field=!strcmp(mode,"port-payload-index-corrupt")?0:!strcmp(mode,"port-payload-direction-corrupt")?1:!strcmp(mode,"port-payload-bit-index-corrupt")?2:!strcmp(mode,"port-payload-width-corrupt")?3:!strcmp(mode,"port-payload-parent-corrupt")?4:!strcmp(mode,"port-payload-name-pointer-corrupt")?5:!strcmp(mode,"port-payload-net-reference-corrupt")?6:!strcmp(mode,"port-payload-bit-parent-corrupt")?7:!strcmp(mode,"port-payload-readiness-corrupt")?8:-1;
    if(port_field>=0 && robotron_start_phase==1){
        int(*toggle)(unsigned)=dlsym(ctx->vvp_handle,"robotron_vvp_port_payload_toggle");
        char*direct_before=robotron_port_payload_text(ctx);if(!toggle||!direct_before)exit(2);
        if(toggle(port_field)!=1)exit(2);
        char*direct=robotron_port_payload_text(ctx);char*changed=display_snapshot(ctx,api);
        if(toggle(port_field)!=1)exit(3);
        char*restored=display_snapshot(ctx,api);
        int direct_ok=port_field<3?(direct&&strcmp(direct_before,direct)!=0):direct==NULL;
        int changed_ok=changed&&strcmp(before,changed)!=0,rejected=changed==NULL;
        int equal=restored&&!strcmp(before,restored);
        if(changed)robotron_metadata_log(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)robotron_metadata_log(stderr,"VB_STAGE restored\n%s",restored);
        robotron_metadata_log(stderr,"VB_PORT_PAYLOAD_FAULT field=%d direct=%d changed=%d rejected=%d restored=%d\n",port_field,direct_ok,changed_ok,rejected,equal);
        free(direct_before);free(direct);free(before);free(changed);free(restored);
        exit(direct_ok&&equal&&(port_field<3?changed_ok:rejected)?2:3);
    }

    int metadata_field=!strcmp(mode,"scope-metadata-units-corrupt")?0:!strcmp(mode,"scope-metadata-line-corrupt")?1:!strcmp(mode,"scope-metadata-function-type-corrupt")?2:!strcmp(mode,"scope-metadata-function-width-corrupt")?3:!strcmp(mode,"scope-metadata-function-init-corrupt")?4:!strcmp(mode,"scope-metadata-intern-corrupt")?5:-1;
    if(metadata_field>=0 && robotron_start_phase==1){
        int(*toggle)(unsigned)=dlsym(ctx->vvp_handle,"robotron_vvp_scope_metadata_toggle");
        char*direct_before=robotron_scope_metadata_text(ctx);if(!toggle||!direct_before)exit(2);
        if(toggle(metadata_field)!=1)exit(2);
        char*direct=robotron_scope_metadata_text(ctx);char*changed=display_snapshot(ctx,api);
        if(toggle(metadata_field)!=1)exit(3);
        char*restored=display_snapshot(ctx,api);
        int direct_ok=metadata_field<5?(direct&&strcmp(direct_before,direct)!=0):direct==NULL;
        int changed_ok=changed&&strcmp(before,changed)!=0,rejected=changed==NULL;
        int equal=restored&&!strcmp(before,restored);
        if(changed)robotron_metadata_log(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)robotron_metadata_log(stderr,"VB_STAGE restored\n%s",restored);
        robotron_metadata_log(stderr,"VB_SCOPE_METADATA_FAULT field=%d direct=%d changed=%d rejected=%d restored=%d\n",metadata_field,direct_ok,changed_ok,rejected,equal);
        free(direct_before);free(direct);free(before);free(changed);free(restored);
        exit(direct_ok&&equal&&(metadata_field<5?changed_ok:rejected)?2:3);
    }

    int typed_field=!strcmp(mode,"typed-signal-signed-corrupt")?0:!strcmp(mode,"typed-signal-range-corrupt")?1:!strcmp(mode,"typed-signal-node-corrupt")?2:!strcmp(mode,"typed-signal-name-corrupt")?3:!strcmp(mode,"typed-signal-cache-corrupt")?4:!strcmp(mode,"typed-signal-scope-corrupt")?5:-1;
    if(typed_field>=0 && robotron_start_phase==1){
        char*direct_before=robotron_typed_text(ctx);if(!direct_before)exit(2);
        if(robotron_typed_fault(ctx,typed_field)!=1)exit(2);
        char*direct=robotron_typed_text(ctx);
        char*changed=display_snapshot(ctx,api);
        if(robotron_typed_fault(ctx,typed_field)!=1)exit(3);
        char*restored=display_snapshot(ctx,api);
        int direct_ok=typed_field<2?(direct&&strcmp(direct_before,direct)!=0):direct==NULL;
        int changed_ok=changed&&strcmp(before,changed)!=0,rejected=changed==NULL;
        int equal=restored&&!strcmp(before,restored);
        if(changed)robotron_metadata_log(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)robotron_metadata_log(stderr,"VB_STAGE restored\n%s",restored);
        robotron_metadata_log(stderr,"VB_TYPED_SIGNAL_FAULT field=%d direct=%d changed=%d rejected=%d restored=%d\n",typed_field,direct_ok,changed_ok,rejected,equal);
        free(direct_before);free(direct);free(before);free(changed);free(restored);
        exit(direct_ok&&equal&&(typed_field<2?changed_ok:rejected)?2:3);
    }

    int callback_list_field=!strcmp(mode,"callback-list-user-corrupt")?0:!strcmp(mode,"callback-list-object-corrupt")?1:!strcmp(mode,"callback-list-function-corrupt")?2:!strcmp(mode,"callback-list-link-corrupt")?3:-1;
    if(callback_list_field>=0 && robotron_start_phase==1){
        if(robotron_output_fault(callback_list_field)!=1)exit(2);
        char*direct=robotron_callback_text(ctx);
        char*changed=display_snapshot(ctx,api);
        if(robotron_output_fault(callback_list_field)!=1)exit(3);
        char*restored=display_snapshot(ctx,api);
        int direct_rejected=direct==NULL,rejected=changed==NULL,equal=restored&&!strcmp(before,restored);
        if(restored)robotron_metadata_log(stderr,"VB_STAGE restored\n%s",restored);
        robotron_metadata_log(stderr,"VB_CALLBACK_LIST_FAULT field=%d direct_rejected=%d rejected=%d restored=%d\n",callback_list_field,direct_rejected,rejected,equal);
        free(before);free(direct);free(changed);free(restored);
        exit(direct_rejected&&rejected&&equal?2:3);
    }

    int raw_assignment_op=!strcmp(mode,"raw-assignment-byte-corrupt")?0:!strcmp(mode,"raw-assignment-width-corrupt")?2:!strcmp(mode,"raw-assignment-port-corrupt")?3:-1;
    if(raw_assignment_op>=0 && robotron_start_phase==1) {
        if(robotron_raw_assignment_fault(ctx,raw_assignment_op)!=1)exit(2);
        char *changed=display_snapshot(ctx,api);
        if(robotron_raw_assignment_fault(ctx,raw_assignment_op)!=1)exit(3);
        char *restored=display_snapshot(ctx,api);
        int detected=changed && strcmp(before,changed)!=0;
        int equal=restored && !strcmp(before,restored);
        if(changed)robotron_metadata_log(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)robotron_metadata_log(stderr,"VB_STAGE restored\n%s",restored);
        robotron_metadata_log(stderr,"VB_RAW_ASSIGNMENT_FAULT operation=%d changed=%d restored=%d\n",raw_assignment_op,detected,equal);
        free(before);free(changed);free(restored);
        exit(detected && equal?2:3);
    }

    int raw_island_field=!strcmp(mode,"raw-island-cache-corrupt")?0:!strcmp(mode,"raw-island-width-corrupt")?1:!strcmp(mode,"raw-island-raw-corrupt")?2:-1;
    if(raw_island_field>=0 && (raw_island_field==0 ? robotron_start_phase==1 : info->vtime>=5e-6)) {
        if(robotron_raw_island_fault(ctx,raw_island_field)!=1)exit(2);
        char *changed=display_snapshot(ctx,api);
        if(robotron_raw_island_fault(ctx,raw_island_field)!=1)exit(3);
        char *restored=display_snapshot(ctx,api);
        int detected=changed && strcmp(before,changed)!=0;
        int equal=restored && !strcmp(before,restored);
        if(changed)robotron_metadata_log(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)robotron_metadata_log(stderr,"VB_STAGE restored\n%s",restored);
        robotron_metadata_log(stderr,"VB_RAW_ISLAND_FAULT field=%d changed=%d restored=%d\n",raw_island_field,detected,equal);
        free(before);free(changed);free(restored);
        exit(detected && equal?2:3);
    }

    int resolver_field=!strcmp(mode,"resolver-cache-corrupt")?0:!strcmp(mode,"resolver-allocation-corrupt")?5:!strcmp(mode,"resolver-raw-corrupt")?6:-1;
    if(resolver_field>=0 && (resolver_field==0 ? robotron_start_phase==1 : info->vtime>=5e-6)) {
        if(robotron_resolver_fault(ctx,resolver_field)!=1)exit(2);
        char *changed=display_snapshot(ctx,api);
        if(robotron_resolver_fault(ctx,resolver_field)!=1)exit(3);
        char *restored=display_snapshot(ctx,api);
        int detected=changed && strcmp(before,changed)!=0;
        int equal=restored && !strcmp(before,restored);
        if(changed)robotron_metadata_log(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)robotron_metadata_log(stderr,"VB_STAGE restored\n%s",restored);
        robotron_metadata_log(stderr,"VB_RESOLVER_FAULT field=%d changed=%d restored=%d\n",resolver_field,detected,equal);
        free(before);free(changed);free(restored);
        exit(detected && equal?2:3);
    }

    int concat_field=!strcmp(mode,"concat-cache-corrupt")?0:!strcmp(mode,"concat-width-corrupt")?1:!strcmp(mode,"concat-raw-corrupt")?6:-1;
    if(concat_field>=0 && (concat_field==0 ? robotron_start_phase==1 : info->vtime>=5e-6)) {
        if(robotron_concat_fault(ctx,concat_field)!=1)exit(2);
        char *changed=display_snapshot(ctx,api);
        if(robotron_concat_fault(ctx,concat_field)!=1)exit(3);
        char *restored=display_snapshot(ctx,api);
        int detected=changed && strcmp(before,changed)!=0;
        int equal=restored && !strcmp(before,restored);
        if(changed)robotron_metadata_log(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)robotron_metadata_log(stderr,"VB_STAGE restored\n%s",restored);
        robotron_metadata_log(stderr,"VB_CONCAT_FAULT field=%d changed=%d restored=%d\n",concat_field,detected,equal);
        free(before);free(changed);free(restored);
        exit(detected && equal?2:3);
    }

    int raw_wire_field=!strcmp(mode,"raw-wire-corrupt")?0:!strcmp(mode,"raw-wire-delayed-corrupt")?1:-1;
    if(raw_wire_field>=0 && (raw_wire_field==0 ? robotron_start_phase==1 : info->vtime>=5e-6)) {
        if(robotron_raw_wire_fault(ctx,raw_wire_field)!=1)exit(2);
        char *changed=display_snapshot(ctx,api);
        if(robotron_raw_wire_fault(ctx,raw_wire_field)!=1)exit(3);
        char *restored=display_snapshot(ctx,api);
        int detected=changed && strcmp(before,changed)!=0;
        int equal=restored && !strcmp(before,restored);
        if(changed)robotron_metadata_log(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)robotron_metadata_log(stderr,"VB_STAGE restored\n%s",restored);
        robotron_metadata_log(stderr,"VB_RAW_WIRE_FAULT delayed=%d changed=%d restored=%d\n",raw_wire_field,detected,equal);
        free(before);free(changed);free(restored);
        exit(detected && equal?2:3);
    }

    int reduction_field=!strcmp(mode,"reduction-bit-corrupt")?0:!strcmp(mode,"reduction-size-corrupt")?1:-1;
    if(reduction_field>=0 && (reduction_field==0 ? robotron_start_phase==1 : info->vtime>=5e-6)) {
        if(robotron_reduction_fault(ctx,reduction_field)!=1)exit(2);
        char *changed=display_snapshot(ctx,api);
        if(robotron_reduction_fault(ctx,reduction_field)!=1)exit(3);
        char *restored=display_snapshot(ctx,api);
        int detected=changed && strcmp(before,changed)!=0;
        int equal=restored && !strcmp(before,restored);
        if(changed)robotron_metadata_log(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)robotron_metadata_log(stderr,"VB_STAGE restored\n%s",restored);
        robotron_metadata_log(stderr,"VB_REDUCTION_FAULT field=%d changed=%d restored=%d\n",reduction_field,detected,equal);
        free(before);free(changed);free(restored);
        exit(detected && equal?2:3);
    }

    int arithmetic_field=!strcmp(mode,"arithmetic-input0-corrupt")?0:!strcmp(mode,"arithmetic-input1-corrupt")?1:!strcmp(mode,"arithmetic-fallback-corrupt")?2:!strcmp(mode,"arithmetic-width-corrupt")?3:-1;
    if(arithmetic_field>=0 && (arithmetic_field==0 ? robotron_start_phase==1 : info->vtime>=5e-6)) {
        if(robotron_arithmetic_fault(ctx,arithmetic_field)!=1)exit(2);
        char *changed=display_snapshot(ctx,api);
        if(robotron_arithmetic_fault(ctx,arithmetic_field)!=1)exit(3);
        char *restored=display_snapshot(ctx,api);
        int detected=changed && strcmp(before,changed)!=0;
        int equal=restored && !strcmp(before,restored);
        if(changed)robotron_metadata_log(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)robotron_metadata_log(stderr,"VB_STAGE restored\n%s",restored);
        robotron_metadata_log(stderr,"VB_ARITHMETIC_FAULT field=%d changed=%d restored=%d\n",arithmetic_field,detected,equal);
        free(before);free(changed);free(restored);
        exit(detected && equal?2:3);
    }

    int gate_field=!strcmp(mode,"gate-input0-corrupt")?0:!strcmp(mode,"gate-input1-corrupt")?1:!strcmp(mode,"gate-input2-corrupt")?2:!strcmp(mode,"gate-input3-corrupt")?3:!strcmp(mode,"gate-invert-corrupt")?5:-1;
    if(gate_field>=0 && (gate_field==0 ? robotron_start_phase==1 : info->vtime>=5e-6)) {
        if(robotron_gate_fault(ctx,gate_field)!=1)exit(2);
        char *changed=display_snapshot(ctx,api);
        if(robotron_gate_fault(ctx,gate_field)!=1)exit(3);
        char *restored=display_snapshot(ctx,api);
        int detected=changed && strcmp(before,changed)!=0;
        int equal=restored && !strcmp(before,restored);
        if(changed)robotron_metadata_log(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)robotron_metadata_log(stderr,"VB_STAGE restored\n%s",restored);
        robotron_metadata_log(stderr,"VB_GATE_FAULT field=%d changed=%d restored=%d\n",gate_field,detected,equal);
        free(before);free(changed);free(restored);
        exit(detected && equal?2:3);
    }

    int mux_field=!strcmp(mode,"mux-a-corrupt")?0:!strcmp(mode,"mux-b-corrupt")?1:!strcmp(mode,"mux-select-corrupt")?2:!strcmp(mode,"mux-run-corrupt")?3:-1;
    if(mux_field>=0 && (mux_field==0 ? robotron_start_phase==1 : info->vtime>=5e-6)) {
        if(robotron_mux_fault(ctx,mux_field)!=1)exit(2);
        char *changed=display_snapshot(ctx,api);
        if(robotron_mux_fault(ctx,mux_field)!=1)exit(3);
        char *restored=display_snapshot(ctx,api);
        int detected=changed && strcmp(before,changed)!=0;
        int equal=restored && !strcmp(before,restored);
        if(changed)robotron_metadata_log(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)robotron_metadata_log(stderr,"VB_STAGE restored\n%s",restored);
        robotron_metadata_log(stderr,"VB_MUX_FAULT field=%d changed=%d restored=%d\n",mux_field,detected,equal);
        free(before);free(changed);free(restored);
        exit(detected && equal?2:3);
    }

    int signal_field=!strcmp(mode,"signal-init-corrupt")?0:!strcmp(mode,"signal-value-corrupt")?1:!strcmp(mode,"signal-active-corrupt")?4:-1;
    if(signal_field>=0 && (signal_field==0 ? robotron_start_phase==1 : info->vtime>=5e-6)) {
        if(robotron_signal_fault(ctx,signal_field)!=1)exit(2);
        char *changed=display_snapshot(ctx,api);
        if(robotron_signal_fault(ctx,signal_field)!=1)exit(3);
        char *restored=display_snapshot(ctx,api);
        int detected=changed && strcmp(before,changed)!=0;
        int equal=restored && !strcmp(before,restored);
        if(changed)robotron_metadata_log(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)robotron_metadata_log(stderr,"VB_STAGE restored\n%s",restored);
        robotron_metadata_log(stderr,"VB_SIGNAL_FAULT field=%d changed=%d restored=%d\n",signal_field,detected,equal);
        free(before);free(changed);free(restored);
        exit(detected && equal?2:3);
    }

    int wire_kind=strstr(mode,"wire4-")==mode?4:strstr(mode,"wire8-")==mode?8:0;
    int wire_field=strstr(mode,"-init-corrupt")?0:strstr(mode,"-driven-corrupt")?1:strstr(mode,"-propagate-corrupt")?4:-1;
    if(wire_kind && wire_field>=0 && (wire_field==0 ? robotron_start_phase==1 : info->vtime>=5e-6)) {
        if(robotron_wire_fault(ctx,wire_kind,wire_field)!=1)exit(2);
        char *changed=display_snapshot(ctx,api);
        if(robotron_wire_fault(ctx,wire_kind,wire_field)!=1)exit(3);
        char *restored=display_snapshot(ctx,api);
        int detected=changed && strcmp(before,changed)!=0;
        int equal=restored && !strcmp(before,restored);
        if(changed)robotron_metadata_log(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)robotron_metadata_log(stderr,"VB_STAGE restored\n%s",restored);
        robotron_metadata_log(stderr,"VB_WIRE_FAULT kind=%d field=%d changed=%d restored=%d\n",wire_kind,wire_field,detected,equal);
        free(before);free(changed);free(restored);
        exit(detected && equal?2:3);
    }

    int net_field=!strcmp(mode,"net-head-corrupt")?0:!strcmp(mode,"net-link-corrupt")?1:!strcmp(mode,"net-tag-corrupt")?2:!strcmp(mode,"net-fun-corrupt")?3:!strcmp(mode,"net-filter-corrupt")?4:!strcmp(mode,"net-foreign-corrupt")?5:-1;
    if(net_field>=0 && ((net_field==0 || net_field==5) ? robotron_start_phase==1 : info->vtime>=5e-6)) {
        if(robotron_net_fault(ctx,net_field)!=1)exit(2);
        char *changed=display_snapshot(ctx,api);
        if(robotron_net_fault(ctx,net_field)!=1)exit(3);
        char *restored=display_snapshot(ctx,api);
        int detected=changed && strcmp(before,changed)!=0;
        int equal=restored && !strcmp(before,restored);
        if(changed)robotron_metadata_log(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)robotron_metadata_log(stderr,"VB_STAGE restored\n%s",restored);
        robotron_metadata_log(stderr,"VB_NET_FAULT field=%d changed=%d restored=%d\n",net_field,detected,equal);
        free(before);free(changed);free(restored);
        exit(detected && equal?2:3);
    }

    int array_field=!strcmp(mode,"array-word-corrupt")?0:!strcmp(mode,"array-address-corrupt")?1:!strcmp(mode,"array-link-corrupt")?2:!strcmp(mode,"array-cache-corrupt")?3:-1;
    if(array_field>=0 && (array_field==2 ? robotron_start_phase==1 : info->vtime>=5e-6)) {
        if(robotron_array_fault(ctx,array_field)!=1)exit(2);
        char *changed=display_snapshot(ctx,api);
        if(robotron_array_fault(ctx,array_field)!=1)exit(3);
        char *restored=display_snapshot(ctx,api);
        int detected=changed && strcmp(before,changed)!=0;
        int equal=restored && !strcmp(before,restored);
        if(changed)robotron_metadata_log(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)robotron_metadata_log(stderr,"VB_STAGE restored\n%s",restored);
        robotron_metadata_log(stderr,"VB_ARRAY_FAULT field=%d changed=%d restored=%d\n",array_field,detected,equal);
        free(before);free(changed);free(restored);
        exit(detected && equal?2:3);
    }

    int operand_field=!strcmp(mode,"operand-immediate-corrupt")?0:!strcmp(mode,"operand-target-corrupt")?1:!strcmp(mode,"operand-handle-corrupt")?2:!strcmp(mode,"operand-unknown-corrupt")?3:-1;
    if(operand_field>=0 && ((operand_field==1 || operand_field==2) ? info->vtime>=5e-6 : robotron_start_phase==1)) {
        if(robotron_operand_fault(ctx,operand_field)!=1)exit(2);
        char *changed=display_snapshot(ctx,api);
        if(robotron_operand_fault(ctx,operand_field)!=1)exit(3);
        char *restored=display_snapshot(ctx,api);
        int detected=operand_field==3 ? changed==NULL : changed && strcmp(before,changed)!=0;
        int equal=restored && !strcmp(before,restored);
        if(changed)robotron_metadata_log(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)robotron_metadata_log(stderr,"VB_STAGE restored\n%s",restored);
        if(operand_field==3)robotron_metadata_log(stderr,"VB_OPERAND_REFUSAL field=3 rejected=%d restored=%d\n",detected,equal);
        else robotron_metadata_log(stderr,"VB_OPERAND_FAULT field=%d changed=%d restored=%d\n",operand_field,detected,equal);
        free(before);free(changed);free(restored);
        exit(detected && equal?2:3);
    }

    int scope_early=!strcmp(mode,"scope-startup-corrupt");
    int scope_late=!strcmp(mode,"scope-late-corrupt");
    if((scope_early && robotron_start_phase==1) || (scope_late && info->vtime>=5e-6)) {
        if(robotron_scope_fault(ctx)!=1)exit(2);
        char *changed=display_snapshot(ctx,api);
        if(robotron_scope_fault(ctx)!=1)exit(3);
        char *restored=display_snapshot(ctx,api);
        int detected=changed && strcmp(before,changed)!=0;
        int equal=restored && !strcmp(before,restored);
        if(changed)robotron_metadata_log(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)robotron_metadata_log(stderr,"VB_STAGE restored\n%s",restored);
        robotron_metadata_log(stderr,"VB_SCOPE_FAULT field=%d changed=%d restored=%d\n",scope_late,detected,equal);
        free(before);free(changed);free(restored);
        exit(detected && equal?2:3);
    }

    int code_field=!strcmp(mode,"code-null-corrupt")?3:!strcmp(mode,"code-foreign-corrupt")?11:-1;
    if(code_field>=0 && robotron_start_phase==1) {
        if(robotron_code_fault(ctx,code_field)!=1)exit(2);
        char *changed=display_snapshot(ctx,api);
        if(robotron_code_fault(ctx,code_field)!=1)exit(3);
        char *restored=display_snapshot(ctx,api);
        int detected=changed && strcmp(before,changed)!=0;
        int equal=restored && !strcmp(before,restored);
        if(changed)robotron_metadata_log(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)robotron_metadata_log(stderr,"VB_STAGE restored\n%s",restored);
        robotron_metadata_log(stderr,"VB_CODE_FAULT field=%d changed=%d restored=%d\n",code_field,detected,equal);
        free(before);free(changed);free(restored);
        exit(detected && equal?2:3);
    }

    int wait_field=-1;
    const char *wait_modes[]={"wait-head-corrupt","wait-mask-corrupt","wait-history-corrupt","wait-cache-corrupt"};
    for(int i=0;i<4;i++)if(!strcmp(mode,wait_modes[i]))wait_field=i;
    if(wait_field>=0 && ((wait_field==0 || wait_field==3) ? info->vtime>=5e-6 : robotron_start_phase==1)) {
        if(robotron_wait_fault(ctx,wait_field)!=1)exit(2);
        char *changed=display_snapshot(ctx,api);
        if(robotron_wait_fault(ctx,wait_field)!=1)exit(3);
        char *restored=display_snapshot(ctx,api);
        int detected=changed && strcmp(before,changed)!=0;
        int equal=restored && !strcmp(before,restored);
        if(changed)robotron_metadata_log(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)robotron_metadata_log(stderr,"VB_STAGE restored\n%s",restored);
        robotron_metadata_log(stderr,"VB_WAIT_FAULT field=%d changed=%d restored=%d\n",wait_field,detected,equal);
        free(before);free(changed);free(restored);
        exit(detected && equal?2:3);
    }

    int thread_field=-1;
    const char *thread_modes[]={"thread-schedule-corrupt","thread-flag-corrupt","thread-word-corrupt",
                               "thread-pc-corrupt","thread-wait-corrupt","thread-queue-corrupt"};
    const int thread_fields[]={0,1,2,3,4,8};
    for(int i=0;i<6;i++)if(!strcmp(mode,thread_modes[i]))thread_field=thread_fields[i];
    if(thread_field>=0 && (thread_field==2 ? info->vtime>=5e-6 : robotron_start_phase==1)) {
        if(robotron_thread_fault(ctx,thread_field)!=1)exit(2);
        char *changed=display_snapshot(ctx,api);
        if(robotron_thread_fault(ctx,thread_field)!=1)exit(3);
        char *restored=display_snapshot(ctx,api);
        int detected=changed && strcmp(before,changed)!=0;
        int equal=restored && !strcmp(before,restored);
        if(changed)robotron_metadata_log(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)robotron_metadata_log(stderr,"VB_STAGE restored\n%s",restored);
        robotron_metadata_log(stderr,"VB_THREAD_FAULT field=%d changed=%d restored=%d\n",thread_field,detected,equal);
        free(before);free(changed);free(restored);
        exit(detected && equal?2:3);
    }

    int filter_field=-1;
    const char *filter_modes[]={"filter-init-corrupt","filter-driven-corrupt","filter-propagate-corrupt","filter-strength-corrupt"};
    const int filter_fields[]={0,1,4,6};
    for(int i=0;i<4;i++)if(!strcmp(mode,filter_modes[i]))filter_field=filter_fields[i];
    if(filter_field>=0 && (filter_field==6 ? info->vtime>=5e-6 : robotron_start_phase==1)) {
        if(robotron_filter_fault(ctx,filter_field)!=1)exit(2);
        char *changed=display_snapshot(ctx,api);
        if(robotron_filter_fault(ctx,filter_field)!=1)exit(3);
        char *restored=display_snapshot(ctx,api);
        int detected=changed && strcmp(before,changed)!=0;
        int equal=restored && !strcmp(before,restored);
        if(changed)robotron_metadata_log(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)robotron_metadata_log(stderr,"VB_STAGE restored\n%s",restored);
        robotron_metadata_log(stderr,"VB_FILTER_FAULT field=%d changed=%d restored=%d\n",filter_field,detected,equal);
        free(before);free(changed);free(restored);
        exit(detected && equal?2:3);
    }

    int island_field=-1;
    const char *island_modes[]={"island-flag-corrupt","island-input-corrupt","island-output-corrupt",
        "island-strength-corrupt","island-enable-corrupt","island-mesh-corrupt","island-queue-corrupt"};
    for(int i=0;i<7;i++)if(!strcmp(mode,island_modes[i]))island_field=i;
    if(island_field>=0 && (island_field==2 ? info->vtime>=5e-6 : robotron_start_phase==1)) {
        if(robotron_island_fault(ctx,island_field)!=1)exit(2);
        char *changed=display_snapshot(ctx,api);
        if(robotron_island_fault(ctx,island_field)!=1)exit(3);
        char *restored=display_snapshot(ctx,api);
        int detected=changed && strcmp(before,changed)!=0;
        int equal=restored && !strcmp(before,restored);
        if(changed)robotron_metadata_log(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)robotron_metadata_log(stderr,"VB_STAGE restored\n%s",restored);
        robotron_metadata_log(stderr,"VB_ISLAND_FAULT field=%d changed=%d restored=%d\n",island_field,detected,equal);
        free(before);free(changed);free(restored);
        exit(detected && equal?2:3);
    }

    int primitive_kind=0,primitive_field=-1;
    const char *primitive_modes[]={"primitive-not-value-corrupt","primitive-not-target-corrupt",
                                 "primitive-part-value-corrupt","primitive-part-target-corrupt","primitive-part-base-corrupt"};
    for(int i=0;i<5;i++) if(!strcmp(mode,primitive_modes[i])) {primitive_kind=i<2?1:2;primitive_field=i<2?i:i-2;}
    if(primitive_kind && robotron_start_phase==1) {
        if(robotron_primitive_fault(ctx,primitive_kind,primitive_field)!=1) exit(2);
        char *changed=display_snapshot(ctx,api);
        if(robotron_primitive_fault(ctx,primitive_kind,primitive_field)!=1) exit(3);
        char *restored=display_snapshot(ctx,api);
        int detected=changed && strcmp(before,changed)!=0;
        int equal=restored && !strcmp(before,restored);
        if(changed)robotron_metadata_log(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)robotron_metadata_log(stderr,"VB_STAGE restored\n%s",restored);
        robotron_metadata_log(stderr,"VB_PRIMITIVE_FAULT kind=%d field=%d changed=%d restored=%d\n",primitive_kind,primitive_field,detected,equal);
        free(before);free(changed);free(restored);
        exit(detected && equal?2:3);
    }

    int assign_kind=0,assign_field=-1;
    const char *assign_modes[]={"assignment-v4-value-corrupt","assignment-v4-target-corrupt","assignment-v4-width-corrupt",
                              "assignment-v8-value-corrupt","assignment-v8-target-corrupt","assignment-v8-strength-corrupt"};
    for(int i=0;i<6;i++) if(!strcmp(mode,assign_modes[i])) {assign_kind=i<3?4:8;assign_field=i%3;}
    if(assign_kind && robotron_start_phase==1) {
        if(robotron_assignment_fault(ctx,assign_kind,assign_field)!=1) exit(2);
        char *changed=display_snapshot(ctx,api);
        if(robotron_assignment_fault(ctx,assign_kind,assign_field)!=1) exit(3);
        char *restored=display_snapshot(ctx,api);
        int detected=changed && strcmp(before,changed)!=0;
        int equal=restored && !strcmp(before,restored);
        if(changed)robotron_metadata_log(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)robotron_metadata_log(stderr,"VB_STAGE restored\n%s",restored);
        robotron_metadata_log(stderr,"VB_ASSIGN_FAULT kind=%d field=%d changed=%d restored=%d\n",assign_kind,assign_field,detected,equal);
        free(before);free(changed);free(restored);
        exit(detected && equal?2:3);
    }

    int start_field = !strcmp(mode,"startup-user-corrupt") ? 0 :
        !strcmp(mode,"startup-function-corrupt") ? 1 :
        !strcmp(mode,"startup-time-corrupt") ? 2 :
        !strcmp(mode,"startup-link-corrupt") ? 3 : -1;
    if (start_field>=0 && robotron_start_phase==1) {
        if (robotron_start_fault(start_field)!=1) exit(2);
        char *changed=display_snapshot(ctx,api);
        if (robotron_start_fault(start_field)!=1) exit(3);
        char *restored=display_snapshot(ctx,api);
        int rejected=changed==NULL;
        int equal=restored && !strcmp(before,restored);
        if (restored) robotron_metadata_log(stderr,"VB_STAGE restored\n%s",restored);
        robotron_metadata_log(stderr,"VB_START_FAULT field=%d rejected=%d restored=%d\n",start_field,rejected,equal);
        free(before);free(changed);free(restored);
        exit(rejected && equal ? 2 : 3);
    }

    int output_field = !strcmp(mode,"output-user-corrupt") ? 0 :
        !strcmp(mode,"output-object-corrupt") ? 1 :
        !strcmp(mode,"output-function-corrupt") ? 2 :
        !strcmp(mode,"output-link-corrupt") ? 3 : -1;
    if (output_field>=0 && info->vtime>=5e-6) {
        if (robotron_output_fault(output_field)!=1) exit(2);
        char *changed=display_snapshot(ctx,api);
        if (robotron_output_fault(output_field)!=1) exit(3);
        char *restored=display_snapshot(ctx,api);
        int rejected=changed==NULL;
        int equal=restored && !strcmp(before,restored);
        if (restored) robotron_metadata_log(stderr,"VB_STAGE restored\n%s",restored);
        robotron_metadata_log(stderr,"VB_OUTPUT_FAULT field=%d rejected=%d restored=%d\n",output_field,rejected,equal);
        free(before);free(changed);free(restored);
        exit(rejected && equal ? 2 : 3);
    }

    if ((!strcmp(mode,"port-handle-corrupt") || !strcmp(mode,"port-context-corrupt") ||
         !strcmp(mode,"port-value-corrupt")) && info->vtime >= 5e-6) {
        struct ngvp_port *port=ctx->ports;
        struct __vpiHandle *saved_handle=port->handle;
        struct ng_vvp *saved_context=port->ctx;
        int32_t saved_value=port->previous.aval;
        int value_fault=!strcmp(mode,"port-value-corrupt");
        if (!strcmp(mode,"port-handle-corrupt")) port->handle=(struct __vpiHandle*)(uintptr_t)1;
        else if (!strcmp(mode,"port-context-corrupt")) port->ctx=NULL;
        else port->previous.aval ^= 1;
        char *changed=display_snapshot(ctx,api);
        port->handle=saved_handle; port->ctx=saved_context; port->previous.aval=saved_value;
        char *restored=display_snapshot(ctx,api);
        int detected=value_fault ? (changed && strcmp(before,changed)) : changed==NULL;
        int equal=restored && !strcmp(before,restored);
        if (changed) robotron_metadata_log(stderr,"VB_STAGE changed\n%s",changed);
        if (restored) robotron_metadata_log(stderr,"VB_STAGE restored\n%s",restored);
        robotron_metadata_log(stderr,"VB_PORT_FAULT kind=%s detected=%d restored=%d\n",mode,!!detected,equal);
        free(before); free(changed); free(restored);
        exit(detected && equal ? 2 : 3);
    }

    if (!strcmp(mode, "wrapper-corrupt") && info->vtime >= 5e-6) {
        int changed = api.toggle_delete();
        if (changed != 0 && changed != 1) exit(2);
        if (changed) {
            char *after = display_snapshot(ctx, api);
            if (api.toggle_delete() != 1) exit(3);
            char *restored = display_snapshot(ctx, api);
            int detected = after && strcmp(before, after);
            int equal = restored && !strcmp(before, restored);
            if (after) robotron_metadata_log(stderr, "VB_STAGE changed\n%s", after);
            if (restored) robotron_metadata_log(stderr, "VB_STAGE restored\n%s", restored);
            robotron_metadata_log(stderr, "VB_WRAPPER_FAULT detected=%d restored=%d\n", !!detected, equal);
            free(before); free(after); free(restored);
            exit(detected && equal ? 2 : 3);
        }
    }

    if (!strcmp(mode, "stop-corrupt") && info->vtime >= 5e-6 && ctx->stop_cb) {
        struct __vpiHandle *saved = ctx->stop_cb;
        ctx->stop_cb = (struct __vpiHandle*)(uintptr_t)1;
        char *changed = display_snapshot(ctx, api);
        ctx->stop_cb = saved;
        char *restored = display_snapshot(ctx, api);
        int rejected = changed == NULL;
        int equal = restored && !strcmp(before, restored);
        if (restored) robotron_metadata_log(stderr, "VB_STAGE restored\n%s", restored);
        robotron_metadata_log(stderr, "VB_STOP_FAULT rejected=%d restored=%d\n", rejected, equal);
        free(before); free(changed); free(restored);
        exit(rejected && equal ? 2 : 3);
    }

    if (!strcmp(mode, "corrupt") && info->vtime >= 5e-6) {
        char *payload_before = display_payload_text(api);
        if (!payload_before) exit(2);
        int changed = api.mutate(api.toggle);
        if (changed != 0 && changed != 1) exit(2);
        if (changed) {
            char *after = display_snapshot(ctx, api);
            char *payload_after = display_payload_text(api);
            /* Restore before any possible transfer back to the HDL scheduler. */
            if (api.mutate(api.toggle) != 1) exit(3);
            char *restored = display_snapshot(ctx, api);
            int rejected = after == NULL;
            int unchanged = payload_after && !strcmp(payload_before, payload_after);
            int equal = restored && !strcmp(before, restored);
            if (restored) robotron_metadata_log(stderr, "VB_STAGE restored\n%s", restored);
            robotron_metadata_log(stderr, "VB_FAULT payload_unchanged=%d rejected=%d restored=%d\n", unchanged, rejected, equal);
            free(before); free(after); free(restored); free(payload_before); free(payload_after);
            exit(rejected && unchanged && equal ? 2 : 3);
        }
        free(payload_before);
    }
    char *repeat = display_snapshot(ctx, api);
    if (!repeat) exit(2);
    int equal = !strcmp(before, repeat);
    robotron_metadata_log(stderr, "VB_STAGE repeat\n%sVB_STABLE equal=%d\n", repeat, equal);
    free(before); free(repeat);
    if (!equal) exit(2);
}


static struct ng_vvp *robotron_callback_context;
static int robotron_callback_bindings(struct ng_vvp *ctx)
{
    if(!ctx || ctx!=robotron_ports_context || ctx->ports!=robotron_ports_base ||
       !robotron_outputs || robotron_outputs_count!=(size_t)ctx->outs+ctx->inouts)return -1;
    for(size_t i=0;i<robotron_outputs_count;i++){
        const struct robotron_output_identity*r=robotron_outputs+i;
        struct ngvp_port*p=ctx->ports+ctx->ins+i;
        if(r->port!=p || p->ctx!=ctx || p->handle!=r->signal ||
           robotron_output_lookup(r->callback,r->function,(char*)p,r->signal)!=r->lifetime)return -1;
    }
    return 0;
}
static void robotron_callback_reference(struct ng_vvp *ctx)
{
    if(robotron_callback_context){if(robotron_callback_context!=ctx)exit(3);return;}
    if(robotron_callback_bindings(ctx))exit(2);
    output_lookup_fn admit=dlsym(ctx->vvp_handle,"robotron_vvp_callback_list_admit");
    int(*reference)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_callback_list_reference");
    if(!admit||!reference)exit(2);
    for(size_t i=0;i<robotron_outputs_count;i++){
        const struct robotron_output_identity*r=robotron_outputs+i;
        if(admit(r->callback,r->function,(char*)r->port,r->signal)!=r->lifetime)exit(2);
    }
    robotron_metadata_log(stderr,"VLB_BEGIN 1 %zu\n",robotron_outputs_count);
    for(size_t i=0;i<robotron_outputs_count;i++){
        const struct robotron_output_identity*r=robotron_outputs+i;
        robotron_metadata_log(stderr,"VLB_LINK %zu %llu %p %p %p %p\n",(size_t)ctx->ins+i,r->lifetime,(void*)r->port,(void*)r->callback,(void*)r->signal,(void*)r->function);
    }
    robotron_metadata_log(stderr,"VLB_END\n");
    if(ferror(stderr)||reference(stderr))exit(2);
    robotron_callback_context=ctx;
}
static int robotron_callback_inventory(FILE*f,struct ng_vvp*ctx)
{
    if(robotron_callback_context!=ctx || robotron_callback_bindings(ctx))return -1;
    int(*delta)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_callback_list_delta_inventory");
    return delta?delta(f):-1;
}
static char* robotron_callback_text(struct ng_vvp*ctx)
{
    char*text=NULL;size_t size=0;FILE*f=open_memstream(&text,&size);if(!f)return NULL;
    int result=robotron_callback_inventory(f,ctx);if(fclose(f))result=-1;
    if(result){free(text);return NULL;}return text;
}


static struct ng_vvp*robotron_typed_signal_context;
static struct robotron_typed_signal_binding {void*handle;unsigned long long id;} *robotron_typed_signal_bindings;
static size_t robotron_typed_signal_count;
static void robotron_typed_signal_reference(struct ng_vvp*ctx)
{
    if(robotron_typed_signal_context){if(robotron_typed_signal_context!=ctx)exit(3);return;}
    if(ctx!=robotron_ports_context || ctx->ports!=robotron_ports_base)exit(2);
    unsigned long long(*admit)(void*)=dlsym(ctx->vvp_handle,"robotron_vvp_signal_handle_admit");
    if(!admit)exit(2);
    robotron_typed_signal_count=(size_t)ctx->ins+ctx->outs+ctx->inouts;
    robotron_typed_signal_bindings=calloc(robotron_typed_signal_count,sizeof(*robotron_typed_signal_bindings));
    if(!robotron_typed_signal_bindings)exit(2);
    robotron_metadata_log(stderr,"VHB_BEGIN 1 %zu\n",robotron_typed_signal_count);
    for(size_t i=0;i<robotron_typed_signal_count;++i){
        struct ngvp_port*p=ctx->ports+i;
        if(p->ctx!=ctx || !p->handle)exit(2);
        unsigned long long id=admit(p->handle);if(!id)exit(2);
        robotron_typed_signal_bindings[i].handle=p->handle;robotron_typed_signal_bindings[i].id=id;
        robotron_metadata_log(stderr,"VHB_LINK %zu %llu %p %p\n",i,id,(void*)p,(void*)p->handle);
    }
    robotron_metadata_log(stderr,"VHB_END\n");if(ferror(stderr))exit(2);robotron_typed_signal_context=ctx;
}
static int robotron_typed_signal_inventory(FILE*f,struct ng_vvp*ctx)
{
    if(!ctx || robotron_typed_signal_context!=ctx || ctx!=robotron_ports_context ||
       ctx->ports!=robotron_ports_base || robotron_typed_signal_count!=(size_t)ctx->ins+ctx->outs+ctx->inouts)return -1;
    for(size_t i=0;i<robotron_typed_signal_count;++i)
        if(ctx->ports[i].ctx!=ctx || ctx->ports[i].handle!=robotron_typed_signal_bindings[i].handle)return -1;
    int(*handles)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_signal_handle_inventory");
    int(*links)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_callback_signal_inventory");
    return !handles||!links||handles(f)||links(f)?-1:0;
}


static int robotron_typed_fault(struct ng_vvp*ctx,int field)
{
    if(ctx!=robotron_typed_signal_context || ctx->ins>=robotron_typed_signal_count)return -1;
    int(*toggle)(unsigned long long,int)=dlsym(ctx->vvp_handle,"robotron_vvp_signal_handle_toggle");
    return toggle?toggle(robotron_typed_signal_bindings[ctx->ins].id,field):-1;
}
static char*robotron_typed_text(struct ng_vvp*ctx)
{
    char*text=NULL;size_t size=0;FILE*f=open_memstream(&text,&size);if(!f)return NULL;
    int result=robotron_typed_signal_inventory(f,ctx);if(fclose(f))result=-1;
    if(result){free(text);return NULL;}return text;
}


static char*robotron_scope_metadata_text(struct ng_vvp*ctx)
{
    char*text=NULL;size_t size=0;FILE*f=open_memstream(&text,&size);if(!f)return NULL;
    int rc=robotron_scope_metadata_inventory(f,ctx);if(fclose(f))rc=-1;
    if(rc){free(text);return NULL;}return text;
}


static int robotron_port_payload_inventory(FILE*out,struct ng_vvp*ctx)
{
    int(*ports)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_port_payload_inventory");
    return ports?ports(out):-1;
}


static char*robotron_port_payload_text(struct ng_vvp*ctx)
{
    char*text=NULL;size_t size=0;FILE*f=open_memstream(&text,&size);if(!f)return NULL;
    int rc=robotron_port_payload_inventory(f,ctx);if(fclose(f))rc=-1;
    if(rc){free(text);if(rc>=0||size)exit(3);return NULL;}return text;
}


static int robotron_scope_signals_inventory(FILE*out,struct ng_vvp*ctx)
{
    int(*signals)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_scope_signal_inventory");
    return signals?signals(out):-1;
}


static char*robotron_all_signal_text(struct ng_vvp*ctx)
{
    char*text=NULL;size_t size=0;FILE*f=open_memstream(&text,&size);if(!f)return NULL;
    int rc=robotron_scope_signals_inventory(f,ctx);if(fclose(f))rc=-1;
    if(rc){free(text);if(rc>=0||size)exit(3);return NULL;}return text;
}


static int robotron_parameter_inventory(FILE*out,struct ng_vvp*ctx)
{
    int(*parameters)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_parameter_inventory");
    return parameters?parameters(out):-1;
}


static char*robotron_parameter_text(struct ng_vvp*ctx)
{
    char*text=NULL;size_t size=0;FILE*f=open_memstream(&text,&size);if(!f)return NULL;
    int rc=robotron_parameter_inventory(f,ctx);if(fclose(f))rc=-1;
    if(rc){free(text);if(rc>=0||size)exit(3);return NULL;}return text;
}


static int robotron_memory_inventory(FILE*out,struct ng_vvp*ctx)
{
    int(*memory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_memory_metadata_inventory");
    return memory?memory(out):-1;
}

static void step(struct co_info *pinfo)
{
    struct ng_vvp *ctx = (struct ng_vvp *)pinfo->handle;

    /* Let VVP run.  It will stop when it has caught up with SPICE time
     * (pinfo->vtime) or produced output.
     */

    private_sync_boundary(pinfo, "before-step");
    cr_yield_to_sim(&ctx->cr_ctx);
    private_sync_boundary(pinfo, "after-step");

    /* Check for output. */

    if (ctx->out_pending) {
        struct ngvp_port *pp;
        uint32_t          changed, mask, limit, i, bit;

        limit = ctx->outs + ctx->inouts;
        for (i = 0, pp = ctx->ports + ctx->ins; i < limit; ++i, ++pp) {
            if (!(pp->flags & OUT_PENDING))
                continue;

            pp->flags &= (uint16_t)~OUT_PENDING;
            changed = (uint32_t)((pp->new.aval ^ pp->previous.aval) |
                                 (pp->new.bval ^ pp->previous.bval));
            if (changed) {
                bit = pp->position;
                mask = 1 << (pp->bits - 1);
                while (changed) {
                    if (mask & changed) {
                        const Digital_t lv_vals[] =
                            { {ZERO, STRONG}, {ONE, STRONG},
                              {ZERO, HI_IMPEDANCE}, {UNKNOWN, STRONG} };
                        uint32_t a, b;

                        a = ((uint32_t)pp->new.aval & mask) != 0;
                        b = ((uint32_t)pp->new.bval & mask) != 0;
                        a += (b << 1);
                        pinfo->out_fn(pinfo, bit, (Digital_t *)lv_vals + a);
                        changed &= ~mask;
                    }
                    mask >>= 1;
                    ++bit;
                }
                pp->previous.aval = pp->new.aval;
                pp->previous.bval = pp->new.bval;
            }
            if (--ctx->out_pending == 0)
                break;
        }
        if (ctx->out_pending)
            abort();
    }
}

static void cleanup(struct co_info *pinfo)
{
    struct ng_vvp *ctx = (struct ng_vvp *)pinfo->handle;

    if (!ctx)
        return;

    /* Tell VVP to exit. */

    ctx->stop = 1;
    cr_yield_to_sim(&ctx->cr_ctx);
    cr_cleanup(&ctx->cr_ctx);
    free(ctx->ports);
    dlclose(ctx->vvp_handle);
    free(ctx);
    pinfo->handle = NULL;
}

/* Static variable and function for passing context from this library
 * to an instance of ivlng.vpi running in the VVP thread.
 * Get_ng_vvp() is called in the VVP thread and must synchronise.
 * XSPICE initialisation is single-threaded, so a static is OK.
 */

static struct ng_vvp *context;

struct ng_vvp *Get_ng_vvp(void)
{
    return context;
}

/* Thread start function runs the Verilog simulation. */

static void *run_vvp(void *arg)
{
    static const char * const  fn_names[] = { VVP_FN_0, VVP_FN_1, VVP_FN_2,
                                              VVP_FN_3, VVP_FN_4, 0 };
    struct co_info            *pinfo = (struct co_info *)arg;
    struct vvp_ptrs            fns;
    void                     **fpptr;
    const char                *file;
    struct ng_vvp             *ctx;
    int                        i;

    cr_safety();        // Make safe with signals.

    /* Find the functions to be called in libvvp. */

    fpptr = (void **)&fns;
    for (i = 0; ; ++i, ++fpptr) {
        if (!fn_names[i])
            break;
        *fpptr = dlsym(context->vvp_handle, fn_names[i]);
        if (!*fpptr) {
            fprintf(stderr, "Icarus shim failed to find VVP function: %s.\n",
                    dlerror());
            abort();
        }
    }

    /* Start the simulation. */

    fns.add_module_path(".");
    file = (pinfo->lib_argc >= 3) ? pinfo->lib_argv[2] : NULL; // VVP log file.
    fns.init(file, (int)pinfo->sim_argc, (char **)pinfo->sim_argv);
    fns.no_signals();

    /* The VPI file will usually be /usr/local/lib/ngspice/ivlng.vpi
     * or C:\Spice64\lib\ngspice\ivlng.vpi.
     */

    if (pinfo->lib_argc >= 2 && pinfo->lib_argv[1][0]) // Explicit VPI file.
        file = pinfo->lib_argv[1];
    else
#ifdef STAND_ALONE
        file = "./ivlng";
#else
        file = NGSPICELIBDIR "/ivlng";
#endif
    fns.load_module(file);
    fns.run(pinfo->sim_argv[0]);

    /* The simulation has finished.  Do nothing until destroyed. */

    ctx = (struct ng_vvp *)pinfo->handle;
    ctx->stop = 1;
    for (;;)
        cr_yield_to_spice(&ctx->cr_ctx);

    return NULL;
}

/* Entry point to this shared library.  Called by d_cosim. */

#if !defined(__MINGW32__) && !defined(_MSC_VER)
__attribute__((visibility("default")))
#endif
void Cosim_setup(struct co_info *pinfo)
{
    char             *file;
    struct ngvp_port *last_port;

    /* It is assumed that there is no parallel access to this function
     * as ngspice initialisation is single-threaded.
     */

    context = calloc(1, sizeof (struct ng_vvp));
    if (!context)
        fail("malloc", errno);
    context->cosim_context = pinfo;
    pinfo->handle = context;

    /* Load libvvp.  It is not statically linked as that would create
     * an unwanted build dependency on Icarus Verilog.
     */

    if (pinfo->lib_argc > 0 && pinfo->lib_argv[0][0]) // Explicit path to VVP?
        file = (char *)pinfo->lib_argv[0];
    else //libvvp is assumed to be in the OS search path.
        file = "libvvp";
    context->vvp_handle = pinfo->dlopen_fn(file);
    if (!context->vvp_handle) {
        fprintf(stderr, "Icarus shim failed to load VVP library\n");
        abort();
    }

    /* Set-up the execution stack for libvvp and start it. */

    cr_init(&context->cr_ctx, run_vvp, pinfo);

    /* Return required values in *pinfo. */

    last_port = context->ports + context->ins - 1;
    pinfo->in_count = context->ins ? last_port->position + last_port->bits : 0;
    last_port += context->outs;
    pinfo->out_count =
        context->outs ? last_port->position + last_port->bits : 0;
    last_port += context->inouts;
    pinfo->inout_count =
        context->inouts ? last_port->position + last_port->bits : 0;
    pinfo->cleanup = cleanup;
    pinfo->step = step;
    pinfo->in_fn = input;
    pinfo->method = Normal;
}
