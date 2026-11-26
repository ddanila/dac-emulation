#include "../../common/runtime/session.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static dac_session *start(void) {
  dac_session *s=dac_create(2);assert(s);
  /* DI; SP=f000; counter loop writes VRAM, reads it, writes CTC. */
  unsigned char rom[2048]={0xf3,0x31,0,0xf0,0x3e,0x61,0x32,0,0x30,0x3a,0,0x30,0xd3,4,0x3c,0xc3,6,0};
  unsigned char prom[256];memset(prom,15,sizeof(prom));
  assert(!dac_load(s,0,rom,sizeof(rom)));assert(!dac_load(s,1,prom,sizeof(prom)));assert(!dac_power(s,1));return s;
}
/* Compare counted overview polling with the complete bus/phase history. */
static void sense_polling(unsigned command) {
  unsigned char rom[2048]={0xf3,0x31,0,0xf0,0x3e,8,0xd3,0x1d,
    0xdb,0x1c,0xe6,0xc0,0xfe,0xc0,0x20,0xf8,0xdb,0x1d,0xc3,4,0};
  if(command==4){
    const unsigned char drive[]={0xf3,0x31,0,0xf0,0x06,0,0x3e,4,0xd3,0x1d,
      0x78,0xd3,0x1d,0x3c,0xe6,1,0x47,0xdb,0x1c,0xe6,0xc0,0xfe,0xc0,
      0x20,0xf8,0xdb,0x1d,0xc3,6,0};
    memcpy(rom,drive,sizeof(drive));
  }
  unsigned char prom[256];memset(prom,15,sizeof(prom));
  dac_session *sessions[2];unsigned totals[2][3][256]={{{0}}},counts[2];
  for(unsigned mode=0;mode<2;mode++){
    dac_session *s=sessions[mode]=dac_create(2);assert(s);
    assert(!dac_load(s,0,rom,sizeof(rom))&&!dac_load(s,1,prom,sizeof(prom)));
    assert(!dac_power(s,1)&&!dac_journey_capture(s,mode?2:0));
    for(unsigned t=0;t<200000;t+=100000){
      assert(dac_run(s,100000)==100000);
    }
    dac_journey_stop(s);
    assert(dac_journey_status(s)==2);counts[mode]=dac_journey_count(s);
    const uint32_t *rows=dac_journey_data(s,0);
    for(unsigned i=0;i<counts[mode];i++){
      const uint32_t *r=rows+i*96;
      if((r[2]==14||r[2]==15)&&(r[3]&255)==0x1d)
        totals[mode][r[2]-14][r[4]&255]+=r[95];
      if(r[2]==24&&r[3]==1)totals[mode][2][r[4]&255]+=r[95];
    }
  }
  assert(!memcmp(totals[0],totals[1],sizeof(totals[0])));
  for(unsigned i=0;i<3;i++){
    unsigned total=0;for(unsigned j=0;j<256;j++)total+=totals[0][i][j];
    assert(total>100);
  }
  assert(counts[0]<counts[1]/10);
  size_t n=dac_state_size(sessions[0]);void *a=malloc(n),*b=malloc(n);assert(a&&b);
  assert(!dac_state_save(sessions[0],a,n)&&!dac_state_save(sessions[1],b,n));
  assert(!memcmp(a,b,n));free(a);free(b);
  dac_destroy(sessions[0]);dac_destroy(sessions[1]);
}
int main(int argc,char **argv){
  sense_polling(4);sense_polling(8);
  dac_session *a=start(),*b=start();assert(dac_journey_capabilities(a)==1);assert(dac_journey_words()==96);
  assert(!dac_journey_capture(a,7));dac_run(a,20000);dac_run(b,20000);dac_journey_stop(a);
  unsigned n=dac_journey_count(a);assert(n>100&&dac_journey_status(a)==2);
  const uint32_t *r=dac_journey_data(a,0);unsigned ins=0,reads=0,writes=0;
  for(unsigned i=0;i<n;i++){const uint32_t *p=r+i*96;assert(!i||p[0]>=p[-96]);ins+=p[2]==8;reads+=p[2]==12;writes+=p[2]==13;}
  assert(ins&&reads&&writes);
  if(argc>1&&!strcmp(argv[1],"--trace")){assert(fwrite(r,96*4,n,stdout)==n);dac_destroy(a);dac_destroy(b);return 0;}
  size_t size=dac_state_size(a);void *sa=malloc(size),*sb=malloc(size);assert(sa&&sb);assert(size==dac_state_size(b));
  assert(!dac_state_save(a,sa,size)&&!dac_state_save(b,sb,size));assert(!memcmp(sa,sb,size));
  /* Restore, rerun, and compare all observations, not just the endpoint. */
  assert(!dac_state_load(a,sa,size));assert(!dac_journey_capture(a,7));dac_run(a,10000);dac_journey_stop(a);
  unsigned count=dac_journey_count(a);uint32_t *copy=malloc(count*96*4);assert(copy);memcpy(copy,dac_journey_data(a,0),count*96*4);
  assert(!dac_state_load(a,sa,size));assert(!dac_journey_capture(a,7));dac_run(a,10000);dac_journey_stop(a);
  assert(dac_journey_count(a)==count&&!memcmp(copy,dac_journey_data(a,0),count*96*4));
  assert(dac_journey_capture(a,8)<0);assert(dac_journey_select(a,1920)<0);assert(dac_journey_fault(a,3,2048,1)<0);
  unsigned glyph=dac_journey_peek(a,4,7);assert(!dac_journey_fault(a,7,7,4));assert(dac_journey_peek(a,4,7)==(glyph^4));assert(dac_journey_peek(b,4,7)==glyph);
  assert(!dac_state_load(a,sa,size));assert(dac_journey_peek(a,4,7)==glyph);assert(dac_journey_peek(a,7,0)==15);
  assert(!dac_journey_arm(a,15,65536,7,1));assert(dac_debug_run(a,20000));assert(dac_debug_hit(a)==3);assert(dac_journey_trigger(a)>0);
  free(copy);free(sa);free(sb);dac_destroy(a);dac_destroy(b);printf("Journey: %u ordered events; state neutrality, replay, isolated glyph mutation, bounds, trigger passed.\n",n);
}
