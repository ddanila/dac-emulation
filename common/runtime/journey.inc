/* Journey ABI 1. Observation and experiment scheduling belong to the host. */
#define JOURNEY_WORDS 96u
#define JOURNEY_CAPACITY 131072u
static void journey_record(dac_session *s,unsigned kind,unsigned address,unsigned value,unsigned master,unsigned space,unsigned offset) {
  if(!s->journey_on)return;
  if(s->journey_count==JOURNEY_CAPACITY){s->journey_on=0;s->journey_full=1;bind_observer(s);return;}
  robotron *m=s->r;robotron_fdc *f=&m->fdc;robotron_dma *d=&m->dma;
  uint32_t *r=s->journey_rows+s->journey_count++*JOURNEY_WORDS;
  memset(r,0,JOURNEY_WORDS*4);dive_snapshot(s,r,kind,address,value);
  r[54]=master;r[55]=space;r[56]=offset;
  r[57]=f->phase|(f->search<<4)|(f->command[0]<<8)|(f->write<<16)|(f->pending<<24);
  r[58]=f->unit|(f->physical[f->unit&3]<<8)|(f->head<<16)|(f->sector<<24);
  r[59]=f->data_pos|(f->data_len<<16);
  for(unsigned i=0;i<4;i++)r[60]|=(uint32_t)f->command[i]<<(8*i);
  r[61]=f->result[0]|(f->result[1]<<8)|(f->result[2]<<16)|(f->result_pos<<24);
  r[62]=d->remaining;r[63]=d->run_a|(d->run_b<<16);
  r[64]=robotron_journey_probe(m,0);r[65]=robotron_journey_probe(m,1);
  r[66]=m->raster.row|(m->raster.character<<8);r[67]=m->raster.frames;
  r[68]=m->cursor[0]|(m->cursor[1]<<8);
  for(unsigned i=0;i<4;i++)r[69]|=(uint32_t)m->crtc[i]<<(8*i);
  for(unsigned u=0;u<2;u++){
    r[70+u]=m->rotation[u];r[72+u]=robotron_head_position(m,u);
    r[74+u]=dac_drive_mechanics_unit(s,u);r[76+u]=f->steps[u];
  }
  r[78]=robotron_mapping(m,(uint16_t)s->dive_hpc,0);r[79]=m->raster.stream;
  r[80]=m->cpu.pins;r[81]=m->cpu.pins>>32;
  r[82]=d->transferred;r[83]=d->status|(d->enabled<<8)|(d->in_service<<9)|(d->irq_enabled<<10)|(d->mode<<16);
  r[84]=m->ctc_vector[0];r[85]=m->sio_regs[1][2];
  r[86]=m->ctc[0].counter|(m->ctc[0].constant<<16);r[87]=m->ctc[0].control;
  r[88]=m->display_on|(m->raster.underrun<<1)|(m->raster.stopped<<2);
  r[89]=m->cpu.cpu.sp<65535 ? robotron_peek(m,m->cpu.cpu.sp)|(robotron_peek(m,m->cpu.cpu.sp+1)<<8):robotron_peek(m,65535);
  r[90]=f->cmd_pos|(f->result_len<<8);r[91]=m->motor;
  r[92]=s->journey_fault;r[93]=s->journey_fault_seen;r[94]=robotron_journey_probe(m,2);r[95]=1;
  if(kind==s->journey_trigger_kind&&(s->journey_trigger_address==65536||address==s->journey_trigger_address)&&!s->journey_trigger_index){s->journey_trigger_index=s->journey_count;if(s->journey_stop)s->debug_hit=3;}
}
static void journey_bus(dac_session *s,const dac_trace_event *e) {
  unsigned kind=e->kind[0]=='M'?(e->kind[1]=='R'?12:13):e->kind[1]=='R'?14:e->kind[1]=='W'?15:16;
  unsigned poll=((e->address&255)*31+s->dive_hpc*17+s->r->bank*7+kind*5)&4095;
  if(!(s->journey_mask&2)){
    if(kind==12 && e->master!=DAC_MASTER_DMA)return;
    if(kind==13 && e->master!=DAC_MASTER_DMA && e->space!=DAC_SPACE_VIDEO)return;
    if(e->master==DAC_MASTER_DMA && s->r->dma.transferred>1 && (s->r->dma.transferred&255) && s->r->dma.remaining>1)return;
    unsigned port=e->address&255;
    if(((kind==14&&(port==0x1c||port==0x40||port==0xe||port==0xf||port==0||(port>=4&&port<=11)))||(kind==15&&port>=0x24&&port<=0x27))&&s->journey_poll[poll]){
      uint32_t *last=s->journey_rows+(s->journey_poll[poll]-1)*JOURNEY_WORDS;
      if(last[2]==kind&&(last[3]&255)==port&&last[4]==e->data&&last[7]==s->dive_hpc&&last[12]==s->r->bank){last[95]++;return;}
    }
    if(kind==13&&e->space==DAC_SPACE_VIDEO&&s->journey_count){
      uint32_t *last=s->journey_rows+(s->journey_count-1)*JOURNEY_WORDS;
      if(last[2]==kind&&last[4]==e->data&&last[3]+last[95]==e->address){last[95]++;return;}
    }
  }
  journey_record(s,kind,e->address,e->data,e->master,e->space,e->offset);
  if(kind==14||(kind==15&&(e->address&255)>=0x24&&(e->address&255)<=0x27))s->journey_poll[poll]=s->journey_count;
}
static unsigned machine_event(void *p,unsigned kind,unsigned address,unsigned value) {
  dac_session *s=p;robotron *m=s->r;unsigned inhibit=0;
  if(kind==4&&s->journey_fault==2&&++s->journey_fault_seen==s->journey_fault_value){inhibit=1;journey_record(s,41,2,s->journey_fault_seen,0,0,0);}
  if(kind==30&&s->journey_fault==6&&address&&m->cpu.cycles<s->journey_fault_until)inhibit=1;
  if(s->dive_on&&kind<=11)dive_event(s,kind,address,value);
  if(!s->journey_on)return inhibit;
  if(kind==0){
    unsigned kd=keyboard_boundary(s),hd=z80_opdone(&m->cpu.cpu);
    if(kd&&!s->journey_kdone){s->dive_kpc=Z80_GET_ADDR(m->keyboard.cpu.cpu.pins);if(s->journey_mask&1)journey_record(s,2,s->dive_kpc,m->keyboard.rom[s->dive_kpc&2047],0,DAC_SPACE_ROM,s->dive_kpc&2047);}
    if(hd&&!s->journey_hdone){
      s->dive_hpc=Z80_GET_ADDR(m->cpu.pins);unsigned map=robotron_mapping(m,s->dive_hpc,0),page=(map>>24)*64+((map&0xffffff)>>12);
      if(s->journey_mask&1)journey_record(s,8,s->dive_hpc,robotron_peek(m,s->dive_hpc),0,map>>24,map&0xffffff);
      else if(page<512&&!(s->journey_seen[page/32]&(1u<<(page%32)))){s->journey_seen[page/32]|=1u<<(page%32);journey_record(s,26,s->dive_hpc,map,0,map>>24,map&0xffffff);}
    }
    s->journey_kdone=kd;s->journey_hdone=hd;
    unsigned state[]={m->bank,m->fdc.phase|(m->fdc.search<<4)|(m->fdc.command[0]<<8),m->fdc.steps[0],m->fdc.steps[1],m->drive[0].index_count,m->drive[1].index_count,robotron_journey_probe(m,0),robotron_journey_probe(m,1)};
    for(unsigned i=0;i<8;i++)if(state[i]!=s->journey_last[i]){unsigned previous=s->journey_last[i];s->journey_last[i]=state[i];if((s->journey_mask&2)||(i!=0&&i!=6)||(i==6&&((previous^state[i])&24)))journey_record(s,24,i,state[i],0,0,0);}
    return inhibit;
  }
  if(kind==30){unsigned state=address|(inhibit<<16);if(state!=s->journey_last[8]){s->journey_last[8]=state;journey_record(s,30,address,inhibit,0,0,0);}return inhibit;}
  if(kind==22){if(!(s->journey_mask&4)||(address&65535)!=s->journey_pixel)return inhibit;}
  if(kind==10){if(address>=1920||s->journey_scan[address]==value)return inhibit;s->journey_scan[address]=value;}
  if(!(s->journey_mask&1)&&(kind==3||kind==4||kind==5||kind==11))return inhibit;
  journey_record(s,kind,address,value,0,0,0);return inhibit;
}
unsigned dac_journey_capabilities(dac_session *s){return s&&s->r?1:0;}
unsigned dac_journey_words(void){return JOURNEY_WORDS;}
int dac_journey_capture(dac_session *s,unsigned mask){
  if(!s||!s->r||!s->on||mask>7)return -EINVAL;
  if(!s->journey_rows)s->journey_rows=malloc(JOURNEY_CAPACITY*JOURNEY_WORDS*4);
  if(!s->journey_rows)return -ENOMEM;
  s->journey_count=s->journey_full=s->journey_trigger_index=s->journey_trigger_kind=0;s->journey_mask=mask;s->journey_on=1;
  memset(s->journey_poll,0,sizeof(s->journey_poll));
  memset(s->journey_seen,0,sizeof(s->journey_seen));
  memset(s->journey_last,255,sizeof(s->journey_last));memset(s->journey_scan,255,sizeof(s->journey_scan));
  s->journey_kdone=s->journey_hdone=0;s->dive_hpc=s->r->cpu.cpu.pc;s->dive_kpc=s->r->keyboard.cpu.cpu.pc;
  bind_observer(s);journey_record(s,25,s->r->cpu.cpu.pc,mask,0,0,0);return 0;
}
void dac_journey_stop(dac_session *s){if(s){s->journey_on=0;bind_observer(s);}}
unsigned dac_journey_count(dac_session *s){return s?s->journey_count:0;}
unsigned dac_journey_status(dac_session *s){return s?s->journey_on?1:s->journey_full?3:2:0;}
const uint32_t *dac_journey_data(dac_session *s,unsigned first){return s&&first<s->journey_count?s->journey_rows+first*JOURNEY_WORDS:NULL;}
int dac_journey_select(dac_session *s,unsigned cell){if(!s||cell>=1920)return -EINVAL;s->journey_pixel=cell;return 0;}
int dac_journey_arm(dac_session *s,unsigned kind,unsigned address,unsigned mask,unsigned stop){if(kind>41||!kind||address>65536||stop>1)return -EINVAL;int r=dac_journey_capture(s,mask);if(r)return r;s->journey_trigger_kind=kind;s->journey_trigger_address=address;s->journey_stop=stop;s->debug_hit=0;return 0;}
unsigned dac_journey_trigger(dac_session *s){return s?s->journey_trigger_index:0;}
/* Controlled experiment overlays. They intentionally alter a private machine.
 * The experiment wrapper retains parameters; ordinary snapshot ABI is unchanged. */
int dac_journey_fault(dac_session *s,unsigned kind,unsigned address,unsigned value){
  if(!s||!s->r||!s->on||kind>8)return -EINVAL;
  robotron *m=s->r;
  if((kind==1&&address>=104)||(kind==2&&(!value||value>100000))||(kind==3&&(address>=2048||!value||value>255))||(kind==7&&(address>=4096||!value||value>255))||(kind==5&&((address&255)>=80||((address>>8)&255)>1||((address>>16)&255)<1||((address>>16)&255)>29))||(kind==6&&(!value||value>39936000)))return -EINVAL;
  if(s->journey_fault==1)dac_matrix(s,s->journey_fault_address,0);
  s->journey_fault=kind;s->journey_fault_address=address;s->journey_fault_value=value;s->journey_fault_seen=0;
  if(kind==1)dac_matrix(s,address,1);
  if(kind==3)m->keyboard.rom[address]^=value;
  if(kind==4){m->drive[0].ejected=1;m->drive[0].ready=0;}
  if(kind==5){robotron_track *t=&m->tracks[0][(address&255)*2+((address>>8)&255)];unsigned found=0;for(unsigned i=0;i<t->count;i++)if(t->sector[i].r==((address>>16)&255)){t->sector[i].st1|=0x20;t->sector[i].st2|=0x20;found=1;}if(!found){s->journey_fault=0;return -ENOENT;}}
  if(kind==6)s->journey_fault_until=m->cpu.cycles+value;
  if(kind==7)m->chargen[address]^=value;
  if(kind==8){s->writable=0;m->disk.writable=0;m->disk.storage=dac_memory_storage(s->disk,s->disk_size,0);}
  bind_observer(s);journey_record(s,40,kind,address,0,0,value);return 0;
}
unsigned dac_journey_peek(dac_session *s,unsigned space,unsigned address){
  if(!s||!s->r)return 0;
  robotron *m=s->r;
  if(space==1&&address<262144)return m->ram[address];
  if(space==2&&address<2048)return m->rom[address];
  if(space==3&&address<4096)return m->vram[address];
  if(space==4&&address<4096)return m->chargen[address];
  if(space==7&&address<256)return m->prom[address];
  return 0;
}
