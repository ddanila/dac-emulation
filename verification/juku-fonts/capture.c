/* Real-media font investigation. No execution changes unless CONTROL is set. */
#include "juku_internal.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static juku *j;
static FILE *trace;
static uint8_t (*read_original)(void *, uint16_t);
static unsigned control, patches;
static uint8_t read_observed(void *u, uint16_t a) {
  uint8_t v = read_original(u, a);
  /* Explicit counterfactual: correct only executed LXI H,DD01 operands.
   * This belongs to the diagnostic, never to the emulator. */
  if (control && a > 0x100 && a < 0xb200 && v == 1 &&
      j->cpu.last_opcode_pc == a - 1 && j->cpu.last_opcode == 0x21 &&
      juku_peek_byte(j, a + 1) == 0xdd) {
    fprintf(trace,"PATCH,%lu,%04x,02,%04x\n",j->cpu.cyc,a,j->cpu.pc);
    v = 2; patches++;
  }
  if (a >= 0xdd00 && a < 0xe062 && j->cpu.pc < 0xb200 && j->cpu.cyc > 32000000)
    fprintf(trace,"READ,%lu,%04x,%02x,%04x\n",j->cpu.cyc,a,v,j->cpu.pc);
  return v;
}
static void bus(void *u, const dac_trace_event *e) {
  (void)u;
  if (!strcmp(e->kind,"MW") && e->address >= 0xd7fb && e->address <= 0xd7fc)
    fprintf(trace,"FONT,%lu,%04x,%02x,%04x\n",j->cpu.cyc,e->address,e->data,j->cpu.pc);
}
static size_t load(const char *path, void *data, size_t size) {
  FILE *f=fopen(path,"rb"); if(!f){perror(path);exit(2);}
  size_t n=fread(data,1,size,f);if(ferror(f)||fgetc(f)!=EOF)exit(2);fclose(f);return n;
}
int main(int argc, char **argv) {
  if(argc!=7){fputs("capture ROM DISK KEYS PREFIX END_MS CONTROL\n",stderr);return 2;}
  j=juku_create();if(!j)return 2;
  uint8_t rom[16384],disk[819200];size_t n=load(argv[1],rom,sizeof rom);
  if(juku_load_rom(j,rom,n))return 2;
  n=load(argv[2],disk,sizeof disk);if(n!=sizeof disk)return 2;
  if(juk_disk_bind(&j->disk,dac_memory_storage(disk,n,0),2,0))return 2;
  juku_fdc_init(&j->fdc,&j->disk);j->fdc_enabled=j->kbd_enabled=1;
  char path[4096];if(strlen(argv[4])>sizeof path-40)return 2;
  snprintf(path,sizeof path,"%s.trace.csv",argv[4]);trace=fopen(path,"w");if(!trace)return 2;
  fputs("kind,cycle,address,value,pc\n",trace);
  j->bus_trace=(dac_trace_sink){bus,NULL,0,0};
  read_original=j->cpu.read_byte;j->cpu.read_byte=read_observed;control=atoi(argv[6]);
  FILE *keys=fopen(argv[3],"r");if(!keys)return 2;
  unsigned long ms=0,end=strtoul(argv[5],NULL,10)*2000;unsigned key;int down,count=0;
  int have=fscanf(keys,"%lu %x %d",&ms,&key,&down);
  while(j->cpu.cyc<end){
    while(have==3 && j->cpu.cyc>=ms*2000){
      juku_key(j,key,down);count++;have=fscanf(keys,"%lu %x %d",&ms,&key,&down);
    }
    juku_step(j);
  }
  if(have!=EOF)return 3;
  snprintf(path,sizeof path,"%s.ram",argv[4]);FILE *f=fopen(path,"wb");if(!f)return 2;
  if(fwrite(j->ram,1,65536,f)!=65536||fclose(f))return 2;
  unsigned stride,lines;const uint8_t *frame=juku_frame(j,&stride,&lines,NULL);if(!frame)return 3;
  snprintf(path,sizeof path,"%s.pbm",argv[4]);f=fopen(path,"wb");if(!f)return 2;
  fprintf(f,"P4\n%u %u\n",stride*8,lines);
  for(unsigned i=0;i<stride*lines;i++)fputc(frame[i]^255,f);
  if(fclose(f)||fclose(trace)||fclose(keys))return 2;
  printf("keys=%d patches=%u font=%04x pc=%04x dimensions=%ux%u\n",count,patches,j->ram[0xd7fb]|j->ram[0xd7fc]<<8,j->cpu.pc,stride*8,lines);
  juku_destroy(j);return 0;
}
