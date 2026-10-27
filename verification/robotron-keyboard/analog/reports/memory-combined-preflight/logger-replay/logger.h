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
