/* Synthetic patterns use the same output logic as firmware captures. */
#include "../../machines/robotron1715m/video_output.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
static uint64_t pending;
static unsigned levels;
static int have,first=1;
static void flush(void) {
 if(have){printf("%s[%llu,%u,%u,%u]",first?"":",",(unsigned long long)pending,levels&1,(levels>>1)&1,(levels>>2)&1);first=0;}
}
static void event(void *user,uint64_t t,unsigned v,unsigned s,unsigned i) {
 (void)user;if(have && t!=pending)flush();pending=t;levels=v|s<<1|i<<2;have=1;
}
int main(int argc,char **argv) {
 const char *names[]={"black","white","alternating","bars","checkerboard","text","highlight"};
 unsigned pattern=7;
 if(argc==2)for(unsigned i=0;i<7;i++)if(!strcmp(argv[1],names[i]))pattern=i;
 if(pattern==7){fputs("usage: robotron-signal-pattern black|white|alternating|bars|checkerboard|text|highlight\n",stderr);return 2;}
 printf("{\"format\":\"dac-monitor-input-v2\",\"clock_hz\":%u,\"signals\":[\"VIDEO\",\"BSYN\",\"INTENS\"],"
 "\"qualification\":\"synthetic-test-pattern\",\"board_revision\":\"1.93.310412.6/04\","
 "\"time_origin\":{\"dot_tick\":0},\"pattern\":\"%s\","
 "\"assumptions\":[\"Synthetic 80 columns, 32 retrace characters, 24 rows, 12 lines/row, 2 retrace rows\","
 "\"Text pattern uses a synthetic glyph, not a firmware character generator\","
 "\"Nominal E05 5.9 us pulses; no specimen calibration\"],\"events\":[",ROBOTRON_VIDEO_HZ,names[pattern]);
 robotron_video_output o={0};o.uv1_end=o.uv2_end=UINT64_MAX;o.sink=event;
 const unsigned dots=112*8*26*12;
 for(unsigned d=0;d<dots;d++) {
   unsigned x=d%(112*8),line=d/(112*8),blank=x>=640||line>=288;
   unsigned v=0,h=0;
   if(!blank)switch(pattern) {
    case 0:break;
    case 1:v=1;break;
    case 2:v=x&1;break;
    case 3:v=(x/32)&1;break;
    case 4:v=((x/8)^(line/12))&1;break;
    case 5:{const unsigned glyph[8]={0x7c,0x42,0x42,0x7c,0x48,0x44,0x42,0};v=line%12<8?(glyph[line%12]>>(7-x%8))&1:0;break;}
    case 6:v=1;h=(x/80)&1;break;
   }
   robotron_video_output_logic(&o,(uint64_t)d*13,v,h,x>=640,line>=288);
 }
 robotron_video_output_logic(&o,(uint64_t)dots*13,0,0,0,0);
 event(NULL,(uint64_t)dots*13,o.levels&1,(o.levels>>1)&1,(o.levels>>2)&1);flush();puts("]}");return ferror(stdout)?1:0;
}
