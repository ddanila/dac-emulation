#include "../../machines/robotron1715m/video_output.h"
#include <assert.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
static robotron m;
static uint64_t hash,events,last;
static void sink(void *user,uint64_t t,unsigned v,unsigned s,unsigned i) {
  (void)user;assert(t>=last);last=t;
  hash=(hash^t)*1099511628211ull;hash=(hash^(v|s<<1|i<<2))*1099511628211ull;events++;
}
static void logic(void) {
  robotron_video_output o={0};o.uv1_end=o.uv2_end=UINT64_MAX;
  robotron_video_output_logic(&o,0,0,0,0,0);
  assert(o.levels==6); /* dark, sync idle high, normal intensity high */
  robotron_video_output_logic(&o,100,1,1,1,0);
  assert(o.levels==3); /* bright highlighted pixel */
  robotron_video_output_logic(&o,1159,1,1,1,0);assert(o.levels==3);
  robotron_video_output_logic(&o,1160,1,1,1,0);assert(o.levels==1);
  robotron_video_output_logic(&o,2220,1,1,1,0);assert(o.levels==3);
  robotron_video_output_logic(&o,3000,0,0,0,1);assert(o.vertical && !(o.levels&2));
  for(unsigned n=0;n<4;n++) {
    robotron_video_output_logic(&o,4000+n*12000,0,0,1,1);
    assert(o.vertical==(n<3));
    assert(o.levels&2); /* UV1 makes a positive serration during VRTC. */
    robotron_video_output_logic(&o,7000+n*12000,0,0,0,1);
    assert(!!(o.levels&2)==(n==3));
  }
  assert(o.delay==15 && !o.vertical && (o.levels&2));
  /* VRTC held high does not continuously re-set the vertical latch. */
  robotron_video_output_logic(&o,60000,0,0,0,1);assert(!o.vertical);
}
static void observational(void) {
  robotron_init(&m);m.rom[0]=0x76;
  m.crtc[0]=79;m.crtc[1]=23;m.crtc[2]=15;m.crtc[3]=9;
  m.display_on=1;m.raster.valid_rows=1;m.raster.scanout[0].columns=80;
  m.raster.scanout[0].lines=16;
  for(unsigned c=0;c<80;c++)for(unsigned l=0;l<16;l++) {
    m.raster.scanout[0].pixels[c][l]=c&1?0xaa:0x55;
    m.raster.scanout[0].highlight[c][l]=c&1;
  }
  robotron *saved=malloc(sizeof(m)),*expected=malloc(sizeof(m));assert(saved&&expected);
  memcpy(saved,&m,sizeof(m));robotron_run(&m,100000);memcpy(expected,&m,sizeof(m));
  memcpy(&m,saved,sizeof(m));robotron_video_output o;
  hash=events=last=0;robotron_video_output_init(&o,&m,sink,NULL);
  robotron_video_output_run(&m,&o,100000);
  assert(!memcmp(&m,expected,sizeof(m)));assert(o.time==4500000 && events>100);
  uint64_t h=hash,n=events;
  memcpy(&m,saved,sizeof(m));hash=events=last=0;
  robotron_video_output_init(&o,&m,sink,NULL);
  for(unsigned done=0;done<100000;) {
    unsigned chunk=(done%97)+1;if(chunk>100000-done)chunk=100000-done;
    robotron_video_output_run(&m,&o,chunk);done+=chunk;
  }
  assert(hash==h && events==n && !memcmp(&m,expected,sizeof(m)));
  robotron_video_output_init(&o,&m,NULL,NULL);
  unsigned phase=m.raster.fraction;
  robotron_video_output_run(&m,&o,3993600);
  assert(o.time==ROBOTRON_VIDEO_HZ && m.raster.fraction==(phase+3993600ull*45)%104);
  /* Static stopped output still advances elapsed time; it is a valid recording. */
  m.raster.stopped=2;robotron_video_output_init(&o,&m,NULL,NULL);
  robotron_video_output_run(&m,&o,3993600);
  assert(o.time==ROBOTRON_VIDEO_HZ && !(o.levels&1));
  free(saved);free(expected);
}
int main(void) {logic();observational();puts("video output: gate vectors, polarity, exact clock, chunk independence, non-interference and stopped capture passed");}
