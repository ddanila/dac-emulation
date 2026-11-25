#include "juku_internal.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static size_t load(const char *p, void *out, size_t cap) {
  FILE *f=fopen(p,"rb"); if(!f) exit(2);
  size_t n=fread(out,1,cap,f);
  if(ferror(f)||fgetc(f)!=EOF) exit(2);
  fclose(f); return n;
}
int main(int argc, char **argv) {
  if(argc!=5) return 2;
  juku *j=juku_create(); if(!j) return 2;
  uint8_t rom[16384]; size_t n=load(argv[1],rom,sizeof rom);
  if(juku_load_rom(j,rom,n)) return 2;
  if(strcmp(argv[2],"-")) {
    memset(j->cart,255,sizeof j->cart);
    load(argv[2],j->cart,sizeof j->cart); j->cart_enabled=1;
  }
  load(argv[3],j->ram+0xc100,0x700); j->cpu.pc=0xc100;
  while(j->ram[0xc8ff]!=0xd3 && j->cpu.cyc<3000000) juku_step(j);
  if(j->ram[0xc8ff]!=0xd3) return 3;
  FILE *f=fopen(argv[4],"wb"); if(!f) return 2;
  int ok=fwrite(j->ram,1,65536,f)==65536; if(fclose(f)) ok=0;
  juku_destroy(j); return ok?0:2;
}
