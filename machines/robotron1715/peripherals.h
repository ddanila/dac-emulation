/* MIT. Register-level classic-board CTC/SIO subset; included by pc1715.c.
 * Source contract and exclusions: interrupts.md. No serial waveform model. */
static void ctc_count(pc1715_ctc *c) {
  if (!c->running || !c->count) return;
  if (!--c->count) { c->count=c->reload; if(c->control&128)c->pending=1; }
}
void pc1715_ctc_input(pc1715 *m,unsigned n,int level) {
  if(!m->onboard || n>=4)return;
  pc1715_ctc *c=&m->ctc[n];
  unsigned edge=!!level!=c->level && !!level==!!(c->control&16);
  c->level=!!level;
  if(!edge || c->waiting || !c->reload)return;
  if(c->control&64)ctc_count(c);
  else if((c->control&8) && !c->running){c->running=1;c->divider=0;}
}
static void peripheral_tick(pc1715 *m) {
  if(!m->onboard)return;
  for(unsigned n=0;n<4;n++) {
    pc1715_ctc *c=&m->ctc[n];
    if(c->running && !(c->control&64) && ++c->divider==((c->control&32)?256:16)) {
      c->divider=0;ctc_count(c);
    }
  }
  for(unsigned n=0;n<2;n++) {
    pc1715_sio *s=&m->sio[n];
    if(s->tx_busy){s->tx_busy=0;if(s->wr[1]&2)s->pending[1]=1;}
  }
}
int pc1715_onboard_enable(pc1715 *m) {
  if(!m)return -EINVAL;
  if(m->cpu.cycles)return -EBUSY;
  m->onboard=1;return 0;
}
int pc1715_sio_receive(pc1715 *m,unsigned n,uint8_t data) {
  if(!m->onboard || n>=2)return -EINVAL;
  pc1715_sio *s=&m->sio[n];
  if(!(s->wr[3]&1))return -EAGAIN;
  if(s->count==3){s->errors|=0x20;return -ENOSPC;} /* bounded seam, not overrun silicon */
  s->fifo[s->count++]=data;
  unsigned mode=s->wr[1]&24;
  if(mode==16 || mode==24 || (mode==8 && s->first)) {
    s->pending[0]=1;s->first=0;
  }
  return 0;
}
void pc1715_sio_external(pc1715 *m,unsigned n) {
  if(m->onboard && n<2 && (m->sio[n].wr[1]&1))m->sio[n].pending[2]=1;
}
static int interrupt_source(pc1715 *m) {
  if(!m->card_offline) {
    if(m->card_service)return -1;
    if(m->card.irq && m->card.irq(m->card.user))return 0;
  }
  if(!m->onboard)return -1;
  for(unsigned n=0;n<4;n++) {
    if(m->ctc[n].service)return -1;
    if(m->ctc[n].pending)return 1+(int)n;
  }
  for(unsigned n=0;n<2;n++)for(unsigned k=0;k<3;k++) {
    pc1715_sio *s=&m->sio[n];
    if(s->service[k])return -1;
    unsigned enabled=k==0?(s->wr[1]&24):k==1?(s->wr[1]&2):(s->wr[1]&1);
    if(enabled && s->pending[k])return 5+(int)(n*3+k);
  }
  return -1;
}
int pc1715_irq_pending(pc1715 *m){return interrupt_source(m)>=0;}
uint8_t pc1715_irq_ack(pc1715 *m) {
  int source=interrupt_source(m);
  if(source<0)return 0xff;
  if(!source){m->card_service=1;return m->card.ack?m->card.ack(m->card.user):0xff;}
  if(source<=4){pc1715_ctc *c=&m->ctc[source-1];c->pending=0;c->service=1;return m->ctc_vector+2*(source-1);}
  unsigned n=(source-5)/3,k=(source-5)%3;
  pc1715_sio *s=&m->sio[n];s->service[k]=1;
  if(k==0)s->pending[k]=0; /* TX/external remain until explicitly cleared. */
  static const uint8_t status[2][3]={{12,8,10},{4,0,2}};
  uint8_t vector=m->sio[1].wr[2];
  return (m->sio[1].wr[1]&4)?(vector&0xf1)|status[n][k]:vector;
}
static void sio_reti(pc1715 *m) {
  for(unsigned n=0;n<2;n++)for(unsigned k=0;k<3;k++)if(m->sio[n].service[k]) {
    m->sio[n].service[k]=0;
    if(k==0 && m->sio[n].count && (m->sio[n].wr[1]&16))m->sio[n].pending[0]=1;
    return;
  }
}
void pc1715_irq_reti(pc1715 *m) {
  if(m->card_service){m->card_service=0;if(m->card.reti)m->card.reti(m->card.user);return;}
  if(!m->onboard)return;
  for(unsigned n=0;n<4;n++)if(m->ctc[n].service){m->ctc[n].service=0;return;}
  sio_reti(m);
}
void pc1715_card_quiesce(pc1715 *m){m->card_offline=1;m->card_service=0;}
int pc1715_onboard_read(pc1715 *m,uint16_t address,uint8_t *data) {
  unsigned a=address&255;
  if(!m->onboard || a<8 || a>15)return 0;
  if(a<12){*data=(uint8_t)m->ctc[a-8].count;return 1;}
  unsigned n=a&1;pc1715_sio *s=&m->sio[n];
  if(!(a&2)){
    *data=s->count?s->fifo[0]:0;
    if(s->count){--s->count;memmove(s->fifo,s->fifo+1,s->count);}
    if(!s->count)s->pending[0]=0;
  }else {
    unsigned reg=s->pointer;s->pointer=0;
    *data=reg==0?(s->count?1:0)|(s->tx_busy?0:4):reg==1?s->errors|1:reg==2?m->sio[1].wr[2]:0;
  }
  return 1;
}
int pc1715_onboard_write(pc1715 *m,uint16_t address,uint8_t data) {
  unsigned a=address&255;
  if(!m->onboard || a<8 || a>15)return 0;
  if(a<12){
    pc1715_ctc *c=&m->ctc[a-8];
    if(c->waiting){c->reload=c->count=data?data:256;c->waiting=0;c->divider=0;
      c->control&=~2;c->running=!!(c->control&64)||!(c->control&8);}
    else if(!(data&1)){if(a==8)m->ctc_vector=data&0xf8;}
    else {c->control=data;c->waiting=!!(data&4);
      if(data&2){c->running=0;c->pending=c->service=0;c->divider=0;}
      if(!(data&128))c->pending=0;
    }
    return 1;
  }
  pc1715_sio *s=&m->sio[a&1];
  if(!(a&2)){s->pending[1]=0;if(s->wr[5]&8)s->tx_busy=1;return 1;}
  if(s->pointer){unsigned reg=s->pointer;s->pointer=0;s->wr[reg]=data;if(reg==1)s->first=1;return 1;}
  switch((data>>3)&7){
    case 2:s->pending[2]=0;break;
    case 3:memset(s,0,sizeof(*s));break;
    case 4:s->first=1;break;
    case 5:s->pending[1]=0;break;
    case 6:s->errors=0;break;
    case 7:if(!(a&1))sio_reti(m);break;
    default:break;
  }
  s->pointer=data&7;return 1;
}
