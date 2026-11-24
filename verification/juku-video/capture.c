/* Local, opt-in real-media capture. No firmware or disk bytes are vendored. */
#include "juku_internal.h"
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static FILE *events;
static void signal_event(void *user, uint64_t ns, unsigned pin, uint8_t level) {
  (void)user;
  fprintf(events,"signal,%llu,%u,%u\n",(unsigned long long)ns,pin,level);
}
static void bus_event(void *user, const dac_trace_event *e) {
  (void)user;
  if ((!strcmp(e->kind,"IW") && e->address>=0x10 && e->address<=0x17) ||
      !strcmp(e->kind,"IA"))
    fprintf(events,"%s,%llu,%u,%u\n",e->kind,(unsigned long long)e->cycle*500,e->address,e->data);
}
static size_t read_file(const char *name, uint8_t *data, size_t size) {
  FILE*f=fopen(name,"rb");if(!f){perror(name);exit(2);}
  size_t n=fread(data,1,size,f);if(ferror(f)||fgetc(f)!=EOF){fclose(f);exit(2);}fclose(f);return n;
}
int main(int argc,char**argv) {
  if(argc!=6){fprintf(stderr,"usage: capture ROM DISK-or-- OUTPUT-PREFIX KEYS CYCLES\n");return 2;}
  juku*j=juku_create();if(!j)return 2;
  uint8_t rom[16384];size_t n=read_file(argv[1],rom,sizeof(rom));
  if(juku_load_rom(j,rom,n))return 2;
  uint8_t *disk=NULL;
  if(strcmp(argv[2],"-")) {
    disk=malloc(819200);if(!disk)return 2;n=read_file(argv[2],disk,819200);
    if(n!=409600 && n!=819200)return 2;
    if(juk_disk_bind(&j->disk,dac_memory_storage(disk,n,0),n==819200?2:1,0))return 2;
    juku_fdc_init(&j->fdc,&j->disk);j->fdc_enabled=1;
  }
  j->kbd_enabled=1;j->kbd_str=argv[4];j->kbd_hold_frames=6;j->kbd_gap_frames=8;
  char path[4096];
  if(strlen(argv[3])>sizeof(path)-80)return 2;
  snprintf(path,sizeof(path),"%s.events.csv",argv[3]);events=fopen(path,"w");if(!events)return 2;
  fputs("kind,time_ns,address_or_pin,value\n",events);
  j->hooks.video_signal=signal_event;
  j->bus_trace=(dac_trace_sink){bus_event,NULL,0,0};
  snprintf(path,sizeof(path),"%s.frames.csv",argv[3]);FILE*frames=fopen(path,"w");if(!frames)return 2;
  fputs("sequence,cycle,stride,lines\n",frames);
  unsigned long cycles=strtoul(argv[5],NULL,0);uint64_t sequence=0;
  while(j->cpu.cyc<cycles) {
    unsigned long before=j->cpu.cyc;juku_step(j);if(before==j->cpu.cyc)break;
    if(j->scanout.sequence!=sequence) {
      sequence=j->scanout.sequence;unsigned stride,lines;
      const uint8_t*p=juku_frame(j,&stride,&lines,NULL);
      snprintf(path,sizeof(path),"%s-%06llu.pbm",argv[3],(unsigned long long)sequence);
      FILE*f=fopen(path,"wb");if(!f)return 2;
      fprintf(f,"P4\n%u %u\n",stride*8,lines);
      /* PBM's 1 means black; core's 1 is illuminated. */
      for(unsigned i=0;i<stride*lines;i++)fputc(p[i]^255,f);
      if(fclose(f))return 2;
      fprintf(frames,"%llu,%lu,%u,%u\n",(unsigned long long)sequence,j->cpu.cyc,stride,lines);
    }
  }
  snprintf(path,sizeof(path),"%s.summary.json",argv[3]);FILE*f=fopen(path,"w");if(!f)return 2;
  fprintf(f,"{\"cycles\":%lu,\"frames\":%llu,\"width\":%u,\"height\":%u,\"ekdos_prompt\":%s,\"frame_irqs\":%lu}\n",
    j->cpu.cyc,(unsigned long long)sequence,j->scanout.frame_stride*8,j->scanout.frame_lines,
    juku_ekdos_prompt_visible(j)?"true":"false",j->frame_irq_count);
  int bad=fclose(f);bad|=fclose(events);bad|=fclose(frames);
  free(disk);juku_destroy(j);return bad?2:0;
}
