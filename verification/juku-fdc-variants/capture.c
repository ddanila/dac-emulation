/* Opt-in real-media investigation; schedule times are independent of video IRQs. */
#include "juku_internal.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static FILE *events, *data_reads, *console;
static juku *machine;
static unsigned long overlay_writes;
static unsigned long fdc_reads[4], fdc_writes[4];
/* Diagnostic JUSS contacts, separate from the core's default keyboard layout. */
static uint8_t (*base_in)(void *, uint8_t);
static unsigned live_contact;
static uint8_t juss_in(void *u, uint8_t port) {
  uint8_t value = base_in(u, port);
  if (port != 5 || !live_contact) return value;
  unsigned key=live_contact, shift=key>='A' && key<='Z';
  if (shift) key+=32;
  const char *rows[]={"1234567890","qwertyuiop","asdfghjkl","zxcvbnm"};
  const unsigned columns[]={2,1,1,0}, row_numbers[]={1,2,3,4};
  unsigned col=0,row=0;int found=0;
  for(unsigned i=0;i<4;i++) {const char *c=strchr(rows[i],(int)key);if(c){col=columns[i]+(unsigned)(c-rows[i]);row=row_numbers[i];found=1;break;}}
  if(key==13){col=13;row=3;found=1;}
  if(key=='.'){col=8;row=4;found=1;}
  if(key==' '){col=3;row=5;found=1;}
  if(!found){fputs("unsupported JUSS probe key\n",stderr);exit(2);}
  value = (uint8_t)((value & 0x30) | 0x80 | (shift ? 0 : 0x40));
  return (uint8_t)(value | (machine->kbd_col == col ? ((~row & 7) << 1) : 15));
}
static void bus(void *user, const dac_trace_event *e) {
  (void)user;
  if (e->address >= 0x1c && e->address <= 0x1f &&
      (!strcmp(e->kind,"IR") || !strcmp(e->kind,"IW"))) {
    unsigned reg = e->address & 3;
    if (reg == 3 && !strcmp(e->kind,"IR")) {
      juku_fdc *f = &machine->fdc;
      unsigned offset = (f->buffer_pos + 511) % 512;
      fprintf(data_reads,"%lu,%u,%u,%u,%u,%02x\n",(unsigned long)e->cycle,
              f->physical_track,f->head,f->sector,offset,
              machine->fdc_bus_invert ? (uint8_t)~e->data : e->data);
    }
    unsigned long n = !strcmp(e->kind,"IR") ? ++fdc_reads[reg] : ++fdc_writes[reg];
    if (n <= 64 || (!strcmp(e->kind,"IW") && reg == 0))
      fprintf(events,"%s,%lu,%04x,%02x,%04x\n",e->kind,(unsigned long)e->cycle,e->address,e->data,machine->cpu.pc);
  }
  if (!strcmp(e->kind,"MW") && e->address >= 0xd800 && (machine->mode == 1 || machine->mode == 2)) {
    if (overlay_writes++ < 32)
      fprintf(events,"OVERLAYWRITE,%lu,%04x,%02x,%04x\n",machine->cpu.cyc,e->address,e->data,machine->cpu.pc);
  }
  if ((!strcmp(e->kind,"IW") && e->address>=0x10 && e->address<=0x17) ||
      !strcmp(e->kind,"IA") || (!strcmp(e->kind,"IR") && e->address==5) ||
      (!strcmp(e->kind,"MW") && e->address>=0xd7f9 && e->address<=0xd7fe))
    fprintf(events,"%s,%lu,%04x,%02x,%04x\n",e->kind,(unsigned long)e->cycle,e->address,e->data,machine->cpu.pc);
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
  if(juk_disk_bind(&j->disk,dac_memory_storage(disk,n,1),n==819200?2:1,1))return 2;
  juku_fdc_init(&j->fdc,&j->disk);j->fdc_enabled=1;j->kbd_enabled=1;
  const char *invert = getenv("JUKU_FDC_BUS_INVERT");
  j->fdc_bus_invert = invert && !strcmp(invert,"1");
  FILE*keys=fopen(argv[4],"r");if(!keys)return 2;
  unsigned long ms=0;unsigned key;int down,have=read_key(keys,&ms,&key,&down);
  char path[4096];if(strlen(argv[3])>sizeof(path)-80)return 2;
  snprintf(path,sizeof(path),"%s.events.csv",argv[3]);events=fopen(path,"w");if(!events)return 2;
  fputs("kind,cycle,address,value,pc\n",events);
  snprintf(path,sizeof(path),"%s.data.csv",argv[3]);data_reads=fopen(path,"w");if(!data_reads)return 2;
  fputs("cycle,track,head,sector,offset,value\n",data_reads);
  snprintf(path,sizeof(path),"%s.console",argv[3]);console=fopen(path,"wb");if(!console)return 2;
  j->bus_trace=(dac_trace_sink){bus,NULL,0,0};

  snprintf(path,sizeof(path),"%s.frames.csv",argv[3]);FILE*frames=fopen(path,"w");if(!frames)return 2;
  fputs("sequence,cycle,width,height,lit_bytes\n",frames);
  int juss = getenv("JUKU_JUSS_CONTACTS") != NULL;
  if (juss) {base_in=j->cpu.port_in; j->cpu.port_in=juss_in;}
  unsigned long checkpoint=28000;
  snprintf(path,sizeof(path),"%s.samples.csv",argv[3]);FILE*samples=fopen(path,"w");if(!samples)return 2;
  fputs("cycle,pc,sp,a,iff,frame_irqs,frames,font_latin_lo,font_latin_hi,font_source_lo\n",samples);
  unsigned long end=strtoul(argv[5],NULL,0)*2000,from=strtoul(argv[6],NULL,0)*2000,next=0;
  uint64_t sequence=0;
  while(j->cpu.cyc<end) {
    while(have && j->cpu.cyc>=ms*2000) {
      if (juss) {
        live_contact = down ? key : 0;
      } else juku_key(j,(uint8_t)key,down);
      fprintf(events,"KEY,%lu,%02x,%d,%04x\n",j->cpu.cyc,key,down,j->cpu.pc);
      have=read_key(keys,&ms,&key,&down);
    }
    if (j->cpu.cyc >= next) {
      fprintf(samples,"%lu,%04x,%04x,%02x,%d,%lu,%llu,%02x,%02x,%02x\n",j->cpu.cyc,j->cpu.pc,j->cpu.sp,j->cpu.a,j->cpu.iff,j->frame_irq_count,(unsigned long long)j->scanout.sequence,j->ram[0xd7fb],j->ram[0xd7fc],j->ram[0x249b]);
      next += 40000;
    }
    if(j->cpu.pc==0xffd9) fputc(j->cpu.a,console);
    unsigned long before=j->cpu.cyc;juku_step(j);
    if(before==j->cpu.cyc){fputs("CPU stopped advancing\n",stderr);return 3;}
    if(j->cpu.cyc >= checkpoint*2000) {
      snprintf(path,sizeof(path),"%s-%lu.ram",argv[3],checkpoint);
      FILE*f=fopen(path,"wb");if(!f)return 2;
      if(fwrite(j->ram,1,65536,f)!=65536 || fclose(f))return 2;
      checkpoint += 2000;
    }
    if(j->scanout.sequence!=sequence) {
      sequence=j->scanout.sequence;
      if(j->cpu.cyc<from)continue;
      unsigned stride,lines;const uint8_t*p=juku_frame(j,&stride,&lines,NULL);
      unsigned lit=0;for(unsigned i=0;i<stride*lines;i++)lit+=p[i]!=0;
      fprintf(frames,"%llu,%lu,%u,%u,%u\n",(unsigned long long)sequence,j->cpu.cyc,stride*8,lines,lit);
      snprintf(path,sizeof(path),"%s-%06llu.pbm",argv[3],(unsigned long long)sequence);
      FILE*f=fopen(path,"wb");if(!f)return 2;fprintf(f,"P4\n%u %u\n",stride*8,lines);
      for(unsigned i=0;i<stride*lines;i++)fputc(p[i]^255,f);
      if(fclose(f))return 2;
    }
  }
  snprintf(path,sizeof(path),"%s.ram",argv[3]);FILE*f=fopen(path,"wb");if(!f)return 2;if(fwrite(j->ram,1,65536,f)!=65536 || fclose(f))return 2;
  fprintf(stdout,"cycles=%lu pc=%04x frames=%llu irq=%lu prompt=%d\n",j->cpu.cyc,j->cpu.pc,(unsigned long long)sequence,j->frame_irq_count,juku_ekdos_prompt_visible(j));
  fprintf(stdout,"overlay_writes=%lu inversion=%d\n",overlay_writes,j->fdc_bus_invert);
  for (unsigned r=0;r<4;r++) fprintf(stdout,"fdc_register=%u reads=%lu writes=%lu\n",r,fdc_reads[r],fdc_writes[r]);
  int bad=fclose(frames);bad|=fclose(keys);bad|=fclose(events);bad|=fclose(samples);bad|=fclose(data_reads);bad|=fclose(console);
  snprintf(path,sizeof(path),"%s.juk",argv[3]);f=fopen(path,"wb");if(!f)return 2;
  if(fwrite(disk,1,n,f)!=n || fclose(f))return 2;
  free(disk);juku_destroy(j);return bad?2:0;
}
