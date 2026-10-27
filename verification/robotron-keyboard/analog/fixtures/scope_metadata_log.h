/* Compact only serialized log records. Snapshot buffers remain dense. */
#include <stdarg.h>
static char*robotron_metadata_previous[2];
static unsigned long long robotron_metadata_sequence[2];
static int robotron_metadata_log(FILE*out,const char*format,...)
{
    char*text=NULL;va_list args;va_start(args,format);
    int length=vasprintf(&text,format,args);va_end(args);if(length<0)return -1;
    const char*cursor=text;
    while(*cursor){
        const char*m=strstr(cursor,"VSM_BEGIN "),*r=strstr(cursor,"VSMR_BEGIN ");
        const char*start=!m?r:!r?m:m<r?m:r;
        if(!start){if(fputs(cursor,out)==EOF)goto failed;break;}
        if(start!=text && start[-1]!='\n')goto failed;
        if(fwrite(cursor,1,start-cursor,out)!=(size_t)(start-cursor))goto failed;
        unsigned index=start==r;const char*tag=index?"VSMRD":"VSMD";
        const char*footer=strstr(start,index?"\nVSMR_END ":"\nVSM_END ");
        const char*head=strchr(start,'\n');const char*end=footer?strchr(footer+1,'\n'):NULL;
        unsigned version;unsigned long long tick;
        if(!head||!end||sscanf(start,index?"VSMR_BEGIN %u %llu":"VSM_BEGIN %u %llu",&version,&tick)!=2||version!=1)goto failed;
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
