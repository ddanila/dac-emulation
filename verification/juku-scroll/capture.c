/* Opt-in real-media investigation; schedule times are independent of video IRQs. */
#include "juku_internal.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static FILE *events;
static FILE *instructions;
static juku *machine;
static void bus(void *user, const dac_trace_event *e) {
  (void)user;
  if ((!strcmp(e->kind,"IW") && e->address>=0x10 && e->address<=0x17) ||
      !strcmp(e->kind,"IA") || (!strcmp(e->kind,"IR") && e->address==5) ||
      (!strcmp(e->kind,"MW") && e->address>=0xd499 && e->address<=0xd49b))
    fprintf(events,"%s,%lu,%04x,%02x,%04x\n",e->kind,(unsigned long)e->cycle,e->address,e->data,machine->cpu.pc);
}
/* EKTA #0037 and EKDOS 2.30 observation points, never execution overrides. */
static int watched_pc(uint16_t pc) {
  switch (pc) {
    case 0xdcd1: /* console output: E */
    case 0xd9df: /* console input return: A */
    case 0xb690: /* CCP accepts the character before ':' as a drive */
    case 0xcd71: /* BIOS drive range check */
    case 0xcd75:
    case 0xcd83: /* BIOS disk parameter header indexing */
    case 0x1076: /* scroll entry */
    case 0x10b6:
    case 0x10ed:
    case 0x1128:
    case 0x0dee: /* ESC ':' */
    case 0x0df7: /* ESC ';' */
    case 0x0fa8:
    case 0x0bf0: /* escape dispatch */
      return 1;
    default:
      return 0;
  }
}
static int read_key(FILE *f, unsigned long *ms, unsigned *key, int *down) {
  unsigned long previous = *ms;
  int n = fscanf(f, "%lu %x %d", ms, key, down);
  if (n == EOF && !ferror(f)) return 0;
  if (n != 3 || *ms < previous || *key > 255 || (*down != 0 && *down != 1)) {
    fputs("invalid or unordered keyboard schedule\n", stderr);
    exit(2);
  }
  return 1;
}
static size_t read_file(const char *name, void *data, size_t size) {
  FILE*f=fopen(name,"rb");if(!f){perror(name);exit(2);}
  size_t n=fread(data,1,size,f);if(ferror(f)||fgetc(f)!=EOF)exit(2);fclose(f);return n;
}
int main(int argc,char**argv) {
  if(argc!=7){fprintf(stderr,"usage: capture ROM DISK PREFIX SCHEDULE END_MS CAPTURE_FROM_MS\n");return 2;}
  juku*j=machine=juku_create();if(!j)return 2;
  uint8_t rom[16384];size_t n=read_file(argv[1],rom,sizeof(rom));
  if(juku_load_rom(j,rom,n))return 2;
  uint8_t *disk=malloc(819200);if(!disk)return 2;n=read_file(argv[2],disk,819200);
  if(n!=409600 && n!=819200)return 2;
  if(juk_disk_bind(&j->disk,dac_memory_storage(disk,n,0),n==819200?2:1,0))return 2;
  juku_fdc_init(&j->fdc,&j->disk);j->fdc_enabled=1;j->kbd_enabled=1;
  FILE*keys=fopen(argv[4],"r");if(!keys)return 2;
  unsigned long ms=0;unsigned key;int down,have=read_key(keys,&ms,&key,&down);
  char path[4096];if(strlen(argv[3])>sizeof(path)-80)return 2;
  snprintf(path,sizeof(path),"%s.events.csv",argv[3]);events=fopen(path,"w");if(!events)return 2;
  fputs("kind,cycle,address,value,pc\n",events);
  j->bus_trace=(dac_trace_sink){bus,NULL,0,0};
  snprintf(path,sizeof(path),"%s.instructions.csv",argv[3]);instructions=fopen(path,"w");if(!instructions)return 2;
  fputs("cycle,pc,a,sp,bc,de,hl,iff,carry\n",instructions);
  snprintf(path,sizeof(path),"%s.samples.csv",argv[3]);FILE*samples=fopen(path,"w");if(!samples)return 2;
  fputs("cycle,pc,sp,a,iff,frame_irqs,frames,scroll_flag,escape_flag,parsed_drive\n",samples);
  unsigned long end=strtoul(argv[5],NULL,0)*2000,from=strtoul(argv[6],NULL,0)*2000,next=0;
  uint64_t sequence=0;unsigned long histogram[65536]={0};
  while(j->cpu.cyc<end) {
    while(have && j->cpu.cyc>=ms*2000) {
      juku_key(j,(uint8_t)key,down);
      fprintf(events,"KEY,%lu,%02x,%d,%04x\n",j->cpu.cyc,key,down,j->cpu.pc);
      have=read_key(keys,&ms,&key,&down);
    }
    if(j->cpu.cyc>=from)histogram[j->cpu.pc]++;
    if (j->cpu.cyc >= next) {
      fprintf(samples,"%lu,%04x,%04x,%02x,%d,%lu,%llu,%02x,%02x,%02x\n",j->cpu.cyc,j->cpu.pc,j->cpu.sp,j->cpu.a,j->cpu.iff,j->frame_irq_count,(unsigned long long)j->scanout.sequence,j->ram[0xd499],j->ram[0xd49a],j->ram[0xbbf0]);
      next += 40000;
    }
    if (j->cpu.cyc >= from && watched_pc(j->cpu.pc) &&
        juku_peek_byte(j, j->cpu.pc) != 0)
      fprintf(instructions,"%lu,%04x,%02x,%04x,%04x,%04x,%04x,%d,%d\n",j->cpu.cyc,j->cpu.pc,j->cpu.a,j->cpu.sp,((j->cpu.b<<8)|j->cpu.c),((j->cpu.d<<8)|j->cpu.e),((j->cpu.h<<8)|j->cpu.l),j->cpu.iff,j->cpu.cf);
    unsigned long before=j->cpu.cyc;juku_step(j);
    if(before==j->cpu.cyc){fputs("CPU stopped advancing\n",stderr);return 3;}
    if(j->scanout.sequence!=sequence) {
      sequence=j->scanout.sequence;
      if(j->cpu.cyc<from)continue;
      unsigned stride,lines;const uint8_t*p=juku_frame(j,&stride,&lines,NULL);
      snprintf(path,sizeof(path),"%s-%06llu.pbm",argv[3],(unsigned long long)sequence);
      FILE*f=fopen(path,"wb");if(!f)return 2;fprintf(f,"P4\n%u %u\n",stride*8,lines);
      for(unsigned i=0;i<stride*lines;i++)fputc(p[i]^255,f);
      if(fclose(f))return 2;
    }
  }
  snprintf(path,sizeof(path),"%s.ram",argv[3]);FILE*f=fopen(path,"wb");if(!f)return 2;if(fwrite(j->ram,1,65536,f)!=65536 || fclose(f))return 2;
  snprintf(path,sizeof(path),"%s.pc.csv",argv[3]);f=fopen(path,"w");if(!f)return 2;for(unsigned i=0;i<65536;i++)if(histogram[i])fprintf(f,"%04x,%lu\n",i,histogram[i]);fclose(f);
  fprintf(stdout,"cycles=%lu pc=%04x frames=%llu irq=%lu prompt=%d\n",j->cpu.cyc,j->cpu.pc,(unsigned long long)sequence,j->frame_irq_count,juku_ekdos_prompt_visible(j));
  int bad=fclose(keys);bad|=fclose(events);bad|=fclose(samples);bad|=fclose(instructions);
  free(disk);juku_destroy(j);return bad?2:0;
}
