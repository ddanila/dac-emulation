#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "logger.h"
int main(void){char*data=NULL;size_t n=0;FILE*f=open_memstream(&data,&n);if(!f)return 2;int c;while((c=getchar())!=EOF)if(fputc(c,f)==EOF)return 2;if(fclose(f))return 2;int rc=robotron_metadata_log(stdout,"%s",data);free(data);return rc<0?2:0;}
