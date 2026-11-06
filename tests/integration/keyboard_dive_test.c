#include "../../common/runtime/session.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static dac_session *start(const unsigned char *keyboard) {
  dac_session *s=dac_create(2);assert(s);
  unsigned char rom[2048]={0x76};
  unsigned char prom[256]={0};
  assert(!dac_load(s,1,prom,sizeof(prom)));
  assert(!dac_load(s,0,rom,sizeof(rom)));
  assert(!dac_load(s,3,keyboard,2048));assert(!dac_power(s,1));return s;
}
int main(int argc,char **argv) {
  unsigned char rom[2048]={0x01,0x01,0x80,0xed,0x78,0xd3,0,0xc3,3,0};
  if(argc>1&&strcmp(argv[1],"--synthetic")){FILE *f=fopen(argv[1],"rb");assert(f&&fread(rom,1,2048,f)==2048);fclose(f);}
  dac_session *a=start(rom),*b=start(rom);
  if(argc>2&&!strcmp(argv[2],"--listing")) {
    for(unsigned pc=0;pc<2048;) {unsigned next=dac_keyboard_disassemble(a,pc);printf("%04x  %s\n",pc,dac_debug_text(a));assert(next>pc);pc=next;}
    dac_destroy(a);dac_destroy(b);return 0;
  }
  assert(dac_dive_capabilities(a)==1);assert(!dac_dive_capture(a,1));
  assert(!dac_matrix(a,4,1));assert(!dac_matrix(b,4,1));
  for(unsigned i=0;i<10;i++){dac_run(a,100000);dac_run(b,100000);}
  assert(!dac_dive_capture(a,0));
  if(argc>2&&!strcmp(argv[2],"--trace")) {
    unsigned n=dac_dive_count(a);assert(fwrite(dac_dive_data(a,0),216,n,stdout)==n);
    dac_destroy(a);dac_destroy(b);return 0;
  }
  unsigned count=dac_dive_count(a);assert(count>10);
  const uint32_t *rows=dac_dive_data(a,0);unsigned kinds=0;
  for(unsigned i=0;i<count;i++) {
    const uint32_t *r=rows+i*54;kinds|=1u<<r[2];
    if(i)assert(r[0]>=r[-54]);
    assert(r[6]<65536&&r[7]<65536);
  }
  assert((kinds&(1<<1))&&(kinds&(1<<2))&&(kinds&(1<<3)));
  size_t size=dac_state_size(a);assert(size==dac_state_size(b));
  void *sa=malloc(size),*sb=malloc(size);assert(sa&&sb);
  assert(!dac_state_save(a,sa,size)&&!dac_state_save(b,sb,size));
  assert(!memcmp(sa,sb,size));
  assert(!dac_state_load(a,sa,size));
  assert(dac_keyboard_byte(a,0)==dac_keyboard_byte(a,0x800));
  unsigned before=dac_keyboard_reg(a,17);assert(dac_keyboard_step(a)>0);
  assert(dac_keyboard_reg(a,17)>before&&dac_keyboard_reg(a,21));
  assert(!dac_dive_capture(a,1));dac_run(a,10000);assert(dac_dive_count(a));
  assert(!dac_dive_arm(a,2,65536,8,1));
  assert(dac_debug_run(a,100000)>0);assert(dac_debug_hit(a)==3);
  unsigned trigger=dac_dive_trigger(a);assert(trigger>0&&trigger<=9);
  assert(dac_dive_data(a,trigger-1)[2]==2);
  assert(dac_dive_arm(a,12,0,0,0)<0);
  assert(!dac_reset(a));assert(!dac_dive_count(a));
  assert(!dac_matrix(a,4,1));assert(!dac_dive_arm(a,1,5,0,0));
  assert(!dac_matrix(a,4,0));assert(!dac_matrix(a,5,1));
  assert(dac_dive_matrix(a,0,1)==0);assert(dac_dive_count(a)==1);
  assert(!dac_dive_capture(a,1));assert(!dac_tap(a,10,0));dac_run(a,100);
  unsigned contacts=0;for(unsigned i=0;i<dac_dive_count(a);i++)contacts+=dac_dive_data(a,i)[2]==1;
  assert(contacts);
  printf("Keyboard dive: %u ordered records; observation preserves complete state; step/mirror/restore passed.\n",count);
  free(sa);free(sb);dac_destroy(a);dac_destroy(b);
}
