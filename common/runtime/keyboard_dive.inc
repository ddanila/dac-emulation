/* Included by session.c: observation state is owned by the host session, never
 * the emulated machine. Record layout is documented in keyboard-dive.md. */
#define DIVE_WORDS 54u
#define DIVE_CAPACITY 262144u
#define DIVE_REGS(reg) (reg)->pc,(reg)->sp,(reg)->af,(reg)->bc,(reg)->de,(reg)->hl,(reg)->ix,(reg)->iy,(reg)->af2,(reg)->bc2,(reg)->de2,(reg)->hl2,(reg)->im,(reg)->iff1,(reg)->iff2,(reg)->i,(reg)->r
static unsigned keyboard_boundary(dac_session *s) {
  k7658_z80_t *r=&s->r->keyboard.cpu.cpu;
  return ((r->pins&(Z80_M1|Z80_RD))==(Z80_M1|Z80_RD)) && !r->prefix_active;
}
static void dive_snapshot(dac_session *s,uint32_t *row,unsigned kind,unsigned address,unsigned value) {
  robotron *m=s->r;
  k7658_cpu *k=&m->keyboard.cpu;
  uint32_t kr[]={DIVE_REGS(&k->cpu)},hr[]={DIVE_REGS(&m->cpu.cpu)};
  memset(row,0,DIVE_WORDS*sizeof(*row));
  row[0]=(uint32_t)m->cpu.cycles;row[1]=(uint32_t)(m->cpu.cycles>>32);
  row[2]=kind;row[3]=address;row[4]=value;row[5]=(uint32_t)k->cycles;
  row[6]=s->dive_kpc;row[7]=s->dive_hpc;
  row[8]=(uint32_t)k->pins;row[9]=(uint32_t)(k->pins>>32);
  row[10]=m->rx.phase|(m->rx.bits<<8)|(m->rx.count<<16)|(m->rx.errors<<24);
  row[11]=m->rx.byte;row[12]=m->bank;row[13]=(uint32_t)m->keyboard.strobes;
  memcpy(row+14,kr,sizeof(kr));memcpy(row+31,hr,sizeof(hr));
  for(unsigned i=0;i<4;i++) {
    row[48]|=(uint32_t)m->keyboard.rom[(s->dive_kpc+i)&2047]<<(8*i);
    row[49]|=(uint32_t)robotron_peek(m,(uint16_t)(s->dive_hpc+i))<<(8*i);
  }
  row[50]=m->sio_regs[0][3]|(m->sio_regs[0][4]<<8);
  row[51]=m->keyboard.leds;row[52]=(uint32_t)(k->cycles>>32);
  row[53]=(!!(k->pins&Z80_HALT))|(!!(m->cpu.pins&Z80_HALT)<<1);
}
static void dive_contact(unsigned *matrix,unsigned key,unsigned value) {
  if(key>=104)return;
  if(value)matrix[key/8]|=1u<<(key%8);else matrix[key/8]&=~(1u<<(key%8));
}
static void dive_event(void *user,unsigned kind,unsigned address,unsigned value) {
  dac_session *s=user;
  if(!s->dive_on)return;
  if(!kind) {
    if(s->dive_contact_clock!=s->r->keyboard.cpu.cycles){
      s->dive_contact_clock=s->r->keyboard.cpu.cycles;
      for(unsigned col=0;col<13;col++){
        unsigned current=s->r->keyboard.matrix[col]|s->r->keyboard.synthetic[col];
        unsigned changed=current^s->dive_contacts[col];
        for(unsigned bit=0;bit<8;bit++)if(changed&(1u<<bit))dive_event(s,1,col*8+bit,!!(current&(1u<<bit)));
      }
    }
    unsigned kd=keyboard_boundary(s),hd=z80_opdone(&s->r->cpu.cpu);
    if(kd&&!s->dive_kdone) {
      s->dive_kpc=Z80_GET_ADDR(s->r->keyboard.cpu.cpu.pins);
      dive_event(s,2,s->dive_kpc,s->r->keyboard.rom[s->dive_kpc&2047]);
    }
    if(hd&&!s->dive_hdone) {
      s->dive_hpc=Z80_GET_ADDR(s->r->cpu.pins);
      dive_event(s,8,s->dive_hpc,robotron_peek(s->r,(uint16_t)s->dive_hpc));
    }
    s->dive_kdone=kd;s->dive_hdone=hd;
    return;
  }
  if(kind==1)dive_contact(s->dive_contacts,address,value);
  if(!s->dive_detailed && (kind==2||kind==8))return;
  if(kind==10) {
    if(address>=1920 || s->dive_scan[address]==value)return;
    s->dive_scan[address]=value;
  }
  if(s->dive_waiting) {
    if(kind==s->dive_trigger_kind && (s->dive_trigger_address==65536 || address==s->dive_trigger_address)) {
      s->dive_waiting=0;s->dive_trigger_index=s->dive_count+1;
      if(s->dive_stop)s->debug_hit=3;
    }else{
      if(!s->dive_pre){if(kind==1)dive_contact(s->dive_initial,address,value);return;}
      if(s->dive_count==s->dive_pre){
        if(s->dive_rows[2]==1)dive_contact(s->dive_initial,s->dive_rows[3],s->dive_rows[4]);
        memmove(s->dive_rows,s->dive_rows+DIVE_WORDS,(s->dive_count-1)*DIVE_WORDS*sizeof(uint32_t));
        s->dive_count--;
      }
    }
  }
  if(s->dive_count==DIVE_CAPACITY) {
    s->dive_on=0;s->dive_full=1;bind_observer(s);return;
  }
  dive_snapshot(s,s->dive_rows+s->dive_count++*DIVE_WORDS,kind,address,value);
}
unsigned dac_dive_capabilities(dac_session *s) {
  return s&&s->r&&s->on&&s->r->keyboard_enabled ? 1 : 0;
}
int dac_dive_capture(dac_session *s,unsigned enabled) {
  if(!dac_dive_capabilities(s))return -EINVAL;
  if(enabled) {
    if(!s->dive_rows)s->dive_rows=malloc(DIVE_CAPACITY*DIVE_WORDS*sizeof(uint32_t));
    if(!s->dive_rows)return -ENOMEM;
    s->dive_count=s->dive_full=0;s->dive_detailed=1;
    for(unsigned i=0;i<13;i++)s->dive_contacts[i]=s->dive_initial[i]=s->r->keyboard.matrix[i]|s->r->keyboard.synthetic[i];
    s->dive_contact_clock=s->r->keyboard.cpu.cycles;
    s->dive_waiting=s->dive_trigger_kind=s->dive_trigger_index=0;
    s->dive_kdone=keyboard_boundary(s);s->dive_hdone=z80_opdone(&s->r->cpu.cpu);
    s->dive_kpc=s->r->keyboard.cpu.cpu.pc;s->dive_hpc=s->r->cpu.cpu.pc;
    for(unsigned i=0;i<1920;i++)s->dive_scan[i]=s->r->raster.scanout[i/80].code[i%80];
  }
  s->dive_on=!!enabled;if(!enabled)s->dive_waiting=0;bind_observer(s);return 0;
}
unsigned dac_dive_status(dac_session *s) {return s ? s->dive_waiting?4:s->dive_on?1:s->dive_full?3:2 : 0;}
unsigned dac_dive_count(dac_session *s) {return s?s->dive_count:0;}
const uint32_t *dac_dive_data(dac_session *s,unsigned first) {
  return s&&first<s->dive_count ? s->dive_rows+first*DIVE_WORDS : NULL;
}
unsigned dac_keyboard_reg(dac_session *s,unsigned field) {
  if(!dac_dive_capabilities(s))return 0;
  k7658_cpu *k=&s->r->keyboard.cpu;
  uint32_t values[]={DIVE_REGS(&k->cpu),(uint32_t)k->cycles,(uint32_t)(k->cycles>>32),0,!!(k->pins&Z80_HALT),keyboard_boundary(s),Z80_GET_ADDR(k->cpu.pins)};
  return field<sizeof(values)/sizeof(*values)?values[field]:0;
}
int dac_keyboard_byte(dac_session *s,unsigned address) {
  return dac_dive_capabilities(s)&&address<65536?s->r->keyboard.rom[address&2047]:-EINVAL;
}
unsigned dac_keyboard_disassemble(dac_session *s,unsigned address) {
  if(!dac_dive_capabilities(s)||address>65535)return 0;
  debug_dasm d={s,(uint16_t)address,0,0,1,0};
  unsigned next=z80dasm_op((uint16_t)address,debug_input,debug_output,&d);
  s->debug_text[d.length]=0;return next;
}
/* All peripherals advance. Step waits for a NEW boundary, not a held fetch. */
unsigned dac_keyboard_step(dac_session *s) {
  if(!dac_dive_capabilities(s))return 0;
  unsigned n=0,previous=keyboard_boundary(s);
  do {
    robotron_run(s->r,1);n++;
    unsigned now=keyboard_boundary(s);
    if(now&&!previous)break;
    previous=now;
  }while(n<100000);
  return n;
}

unsigned dac_dive_screen(dac_session *s,unsigned cell) {
  return s&&s->r&&cell<1920 ? s->r->raster.scanout[cell/80].code[cell%80] : 0;
}

unsigned dac_dive_instruction(dac_session *s,unsigned address,unsigned packed) {
  if(!s || address>65535)return 0;
  debug_dasm d={s,(uint16_t)address,0,0,2,packed};
  unsigned next=z80dasm_op((uint16_t)address,debug_input,debug_output,&d);
  s->debug_text[d.length]=0;
  if(((next-address)&65535)>4)strcpy(s->debug_text,"Extended prefix sequence: inspect ROM bytes");
  return next;
}

int dac_dive_arm(dac_session *s,unsigned kind,unsigned address,unsigned pre,unsigned stop) {
  if(kind<1||kind>11||address>65536||pre>128||stop>1)return -EINVAL;
  int result=dac_dive_capture(s,1);if(result)return result;
  s->dive_trigger_kind=kind;s->dive_trigger_address=address;s->dive_pre=pre;
  s->dive_waiting=1;s->dive_stop=stop;s->debug_hit=0;return 0;
}
unsigned dac_dive_trigger(dac_session *s){return s?s->dive_trigger_index:0;}

void dac_dive_detail(dac_session *s,unsigned enabled){if(s)s->dive_detailed=!!enabled;}

unsigned dac_dive_matrix(dac_session *s,unsigned column,unsigned initial){
  if(!dac_dive_capabilities(s)||column>=13)return 0;
  return initial?s->dive_initial[column]:s->r->keyboard.matrix[column]|s->r->keyboard.synthetic[column];
}
