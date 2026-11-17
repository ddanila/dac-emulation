/* Source-traceable logical connector capture. Electrical driver/cable models
 * are downstream; this is not a measured connector waveform. */
#include "../../machines/robotron1715m/video_output.h"
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>

static int load(const char *path, void *data, size_t bytes) {
  FILE *f=fopen(path,"rb"); if(!f)return 0;
  int ok=fread(data,1,bytes,f)==bytes && fgetc(f)==EOF;
  fclose(f);return ok;
}
static unsigned number(const char *s, unsigned limit) {
  char *end;errno=0;unsigned long value=strtoul(s,&end,10);
  if(errno || !*s || *end || value>limit) {fprintf(stderr,"Invalid tick budget\n");exit(2);}
  return (unsigned)value;
}
typedef struct { FILE *out; uint64_t origin,end,pending; unsigned levels; int have,first; } recording;
static void flush(recording *r) {
  if(r->have) {fprintf(r->out,"%s[%llu,%u,%u,%u]",r->first?"":",",
      (unsigned long long)r->pending,r->levels&1,(r->levels>>1)&1,(r->levels>>2)&1);r->first=0;}
}
static void event(void *user,uint64_t t,unsigned video,unsigned sync,unsigned intensity) {
  recording *r=user;
  if(t<r->origin || t>r->end)return;
  t-=r->origin;
  if(r->have && t!=r->pending)flush(r);
  r->pending=t;r->levels=video|(sync<<1)|(intensity<<2);r->have=1;
}
int main(int argc,char **argv) {
  if(argc!=8){fprintf(stderr,"usage: %s ROM2048 PROM256 CHARGEN4096-or-- DISK boot_cpu_ticks capture_dot_ticks OUTPUT.json\n",argv[0]);return 2;}
  unsigned boot=number(argv[5],200000000),end=number(argv[6],13824000);
  if(end<16)return 2;
  robotron *m=calloc(1,sizeof(*m));if(!m)return 2;robotron_init(m);
  if(!load(argv[1],m->rom,sizeof(m->rom))||!load(argv[2],m->prom,sizeof(m->prom))||(strcmp(argv[3],"-")&&!load(argv[3],m->chargen,sizeof(m->chargen)))){free(m);return 2;}
  FILE *df=fopen(argv[4],"rb");if(!df){free(m);return 2;}
  if(fseek(df,0,SEEK_END)){fclose(df);free(m);return 2;}
  long n=ftell(df);if(n<256||n>1048576||fseek(df,0,SEEK_SET)){fclose(df);free(m);return 2;}
  uint8_t *disk=malloc((size_t)n);if(!disk){fclose(df);free(m);return 2;}
  int ok=fread(disk,1,(size_t)n,df)==(size_t)n;fclose(df);
  if(!ok||robotron_disk(m,dac_memory_storage(disk,(size_t)n,0),0)){free(disk);free(m);return 2;}
  /* Observe the last 40 ms of boot to establish the line-clocked sync state.
   * The elapsed boot CPU budget remains exactly the requested value. */
  unsigned warm=boot<159744?boot:159744;
  robotron_run(m,boot-warm);
  robotron_video_output observer;robotron_video_output_init(&observer,m,NULL,NULL);
  robotron_video_output_run(m,&observer,warm);
  FILE *out=fopen(argv[7],"wx");if(!out){perror(argv[7]);free(disk);free(m);return 2;}
  fprintf(out,"{\"format\":\"dac-monitor-input-v2\",\"clock_hz\":%u,"
      "\"board_revision\":\"1.93.310412.6/04\",\"signals\":[\"VIDEO\",\"BSYN\",\"INTENS\"],"
      "\"qualification\":\"schematic-derived-logical\","
      "\"time_origin\":{\"boot_cpu_ticks\":%u,\"character_phase_ticks\":%u},"
      "\"assumptions\":[\"8275 functional core, decoded row-latched pixels; not gate-level memory timing\","
      "\"E05 pulse widths nominal 5.9 us, rounded to 1060 master ticks\","
      "\"VRTC edge pulse treated as instantaneous; electrical delays modeled downstream\","
      "\"Programmed reset/start known only at CPU-tick resolution\","
      "\"Sync state initialized idle before observation pre-roll; specimen not verified\"],"
      "\"pre_roll_cpu_ticks\":%u,\"events\":[",ROBOTRON_VIDEO_HZ,boot,m->raster.fraction,warm);
  recording r={out,observer.time,observer.time+(uint64_t)end*13,0,0,0,1};
  observer.sink=event;observer.user=&r;
  event(&r,r.origin,observer.levels&1,(observer.levels>>1)&1,(observer.levels>>2)&1);
  unsigned cpu_ticks=(unsigned)(((uint64_t)end*13+44)/45);
  robotron_video_output_run(m,&observer,cpu_ticks);
  /* Events beyond the requested boundary were discarded; retain the last
   * in-window state, not the observer state from the enclosing CPU tick. */
  unsigned levels=r.levels;
  event(&r,r.end,levels&1,(levels>>1)&1,(levels>>2)&1);flush(&r);
  fprintf(out,"]}\n");
  ok=!ferror(out);if(fclose(out))ok=0;free(disk);free(m);return ok?0:1;
}
