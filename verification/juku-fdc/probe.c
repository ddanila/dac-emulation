/* Issue 25: observe stock execution, or deliberately enable controller pacing.
 * The latter is a diagnostic perturbation, not a proposed machine fix. */
#include "juku_internal.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static size_t load(const char *path, void *data, size_t capacity) {
  FILE *f=fopen(path,"rb"); if(!f){perror(path);exit(2);}
  size_t n=fread(data,1,capacity,f);
  if(ferror(f)||fgetc(f)!=EOF){fclose(f);exit(2);} fclose(f);return n;
}
int main(int argc,char **argv) {
  if(argc!=5){fprintf(stderr,"usage: probe ROM DISK OUTPUT_PREFIX PACED_0_OR_1\n");return 2;}
  if(strcmp(argv[4],"0") && strcmp(argv[4],"1"))return 2;
  juku *j=juku_create(); if(!j)return 2;
  uint8_t rom[16384],*disk=malloc(819200);if(!disk)return 2;
  size_t nr=load(argv[1],rom,sizeof(rom)),nd=load(argv[2],disk,819200);
  if(juku_load_rom(j,rom,nr)||(nd!=819200 && nd!=409600))return 2;
  if(juk_disk_bind(&j->disk,dac_memory_storage(disk,nd,0),nd==819200?2:1,0))return 2;
  juku_fdc_init(&j->fdc,&j->disk);j->fdc.paced_data=(unsigned)atoi(argv[4]);
  j->fdc_enabled=1;j->kbd_enabled=1;
  char path[4096];if(strlen(argv[3])>sizeof(path)-32)return 2;
  snprintf(path,sizeof(path),"%s.csv",argv[3]);FILE *f=fopen(path,"w");if(!f)return 2;
  fputs("cycle,pc,op,reg,a,status,command,position,drq_ticks,byte_delay\n",f);
  const char keys[]="TDDdir\r";
  unsigned index=0;int held=0;
  unsigned long next=4000000,reads=0,early=0;
  while(j->cpu.cyc<60000000) {
    if(index<sizeof(keys)-1 && j->cpu.cyc>=next) {
      if(!held){juku_key(j,(uint8_t)keys[index],1);held=1;next+=240000;}
      else {juku_key(j,0,0);held=0;index++;next+=320000;if(index==3)next=32000000;}
    }
    uint16_t pc=j->cpu.pc;uint8_t op=juku_peek_byte(j,pc),p=juku_peek_byte(j,(uint16_t)(pc+1));
    if(!j->cpu.io_pending&&(op==0xdb||op==0xd3)&&p>=0x1c&&p<=0x1f) {
      fprintf(f,"%lu,%04x,%02x,%02x,%02x,%02x,%02x,%u,%u,%u\n",j->cpu.cyc,pc,op,p,j->cpu.a,j->fdc.status,j->fdc.command,j->fdc.buffer_pos,j->fdc.drq_ticks,j->fdc.byte_delay);
      if(op==0xdb&&p==0x1f){reads++;if((j->fdc.status&3)==1)early++;}
    }
    unsigned long before=j->cpu.cyc;juku_step(j);if(before==j->cpu.cyc)return 3;
  }
  if(fclose(f))return 2;
  snprintf(path,sizeof(path),"%s.ram",argv[3]);f=fopen(path,"wb");if(!f)return 2;
  if(fwrite(j->ram,1,65536,f)!=65536||fclose(f))return 2;
  printf("{\"paced\":%u,\"data_reads\":%lu,\"busy_without_drq_before_in\":%lu,\"final_pc\":\"%04x\",\"final_status\":%u}\n",j->fdc.paced_data,reads,early,j->cpu.pc,j->fdc.status);
  free(disk);juku_destroy(j);return 0;
}
