#include "video_output.h"
#include <string.h>
#include <limits.h>

static void emit(robotron_video_output *o, uint64_t t, unsigned video, unsigned highlight) {
  unsigned uv1=o->uv1_end!=UINT64_MAX, uv2=o->uv2_end!=UINT64_MAX;
  /* E04 latch -> E03.3 (VSYN), E04.1 -> E03.4 (BSYN).
   * E03.1 inverts HGLT: low INTENS means highlighted. */
  unsigned bsyn=!(o->vertical && !uv1) && !uv2;
  unsigned levels=video | (bsyn<<1) | ((!highlight)<<2);
  if (!o->initialized || levels!=o->levels) {
    o->levels=levels;o->initialized=1;
    if(o->sink)o->sink(o->user,t,video,bsyn,!highlight);
  }
}
static void deadlines(robotron_video_output *o, uint64_t t) {
  for (;;) {
    uint64_t next=o->uv1_end<o->uv2_end?o->uv1_end:o->uv2_end;
    if(next==UINT64_MAX || next>t)break;
    if(o->uv2_end==next)o->uv2_end=UINT64_MAX;
    if(o->uv1_end==next) {
      o->uv1_end=UINT64_MAX;
      o->uv2_end=next+ROBOTRON_VIDEO_PULSE;
    }
    emit(o,next,o->levels&1,o->highlight);
  }
}
void robotron_video_output_logic(robotron_video_output *o,uint64_t t,
                                unsigned video,unsigned highlight,unsigned hrtc,unsigned vrtc) {
  deadlines(o,t);
  if(vrtc && !o->vrtc)o->vertical=1; /* E08/RC/E04 leading-edge set pulse. */
  if(hrtc && !o->hrtc) {
    o->uv1_end=t+ROBOTRON_VIDEO_PULSE; /* E05.1, retriggerable. */
    o->delay=((o->delay<<1)|vrtc)&15; /* E07, clocked by HRTC, not CCLK. */
    if(o->delay&8)o->vertical=0; /* E07 /Q2 resets the NAND latch. */
  }
  o->hrtc=hrtc;o->vrtc=vrtc;o->highlight=highlight;
  emit(o,t,video,highlight);
}
static void latch(robotron_video_output *o,const robotron *m) {
  unsigned cols=(m->crtc[0]&127)+1,rows=(m->crtc[1]&63)+1;
  if(cols>80)cols=80;
  if(rows>24)rows=24;
  unsigned clocks=cols+2*((m->crtc[3]&15)+1);
  unsigned col=m->raster.character%clocks,line=m->raster.character/clocks;
  if(m->crtc[0]&128)line/=2;
  unsigned row=m->raster.row,stopped=m->raster.stopped==2;
  unsigned hrtc=!stopped && col>=cols,vrtc=!stopped && row>=rows;
  o->word=0;unsigned highlight=0;
  if(!stopped && !hrtc && !vrtc && line<16 && m->display_on &&
     !(m->disconnected&2) && (m->raster.valid_rows&(1u<<row))) {
    const robotron_video_row *r=&m->raster.scanout[row];
    if(col<r->columns && line<r->lines) {
      o->word=r->pixels[col][line];highlight=!!r->highlight[col][line];
    }
  }
  robotron_video_output_logic(o,o->time,(o->word>>(7-o->dot))&1,highlight,hrtc,vrtc);
}
void robotron_video_output_init(robotron_video_output *o,const robotron *m,
                               robotron_video_sink sink,void *user) {
  memset(o,0,sizeof(*o));o->sink=sink;o->user=user;
  o->uv1_end=o->uv2_end=UINT64_MAX;
  o->phase=m->raster.fraction;o->dot=o->phase/13;
  latch(o,m);
}
void robotron_video_output_run(robotron *m,robotron_video_output *o,unsigned ticks) {
  while(ticks--) {
    unsigned before=m->raster.fraction,stopped=m->raster.stopped==2;
    uint64_t start=o->time,end=start+45;
    robotron_run(m,1);
    /* The core resolves character events at the enclosing CPU tick. Their
     * clock crossing itself is reconstructed exactly, not rounded to that tick.
     * Dot shifts retain the character word until the next character load. */
    if(!stopped && m->raster.fraction==(before+45)%104) {
      for(unsigned delta=13-before%13;delta<=45;delta+=13) {
        o->time=start+delta;o->dot=((before+delta)%104)/13;
        if(!o->dot)latch(o,m);
        else robotron_video_output_logic(o,o->time,(o->word>>(7-o->dot))&1,
                                          o->highlight,o->hrtc,o->vrtc);
      }
    } else if(stopped!=(m->raster.stopped==2) || before!=m->raster.fraction) {
      /* Programmed reset/start is only known at CPU resolution in this core. */
      o->time=end;o->dot=m->raster.fraction/13;latch(o,m);
    }
    deadlines(o,end);o->time=end;o->phase=m->raster.fraction;
  }
}
