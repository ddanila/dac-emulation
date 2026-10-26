#include "../../common/runtime/pc1715.h"
#include "../../common/runtime/observe.h"
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
  unsigned reads, writes, ticks, resets, acks, retis, irq;
  uint16_t address;
  uint8_t data;
} card_state;
static int card_read(void *p, uint16_t a, uint8_t *data) {
  card_state *s = p;
  s->reads++;
  s->address = a;
  *data = 0xa5;
  return (a & 255) == 2;
}
static void card_write(void *p, uint16_t a, uint8_t data) {
  card_state *s = p;
  s->writes++;
  s->address = a;
  s->data = data;
}
static void card_tick(void *p, uint64_t cycle) {
  card_state *s = p;
  assert(cycle == s->ticks++);
}
static int card_irq(void *p) { return ((card_state *)p)->irq; }
static uint8_t card_ack(void *p) {
  card_state *s = p;
  s->acks++;
  s->irq = 0;
  return 0xff;
}
static void card_reti(void *p) { ((card_state *)p)->retis++; }
static void card_reset(void *p) {
  card_state *s = p;
  unsigned resets = s->resets + 1;
  memset(s, 0, sizeof(*s));
  s->resets = resets;
}
static pc1715_card card(card_state *s) {
  return (pc1715_card){s, card_read, card_write, card_tick, card_irq,
                       card_ack, card_reti, card_reset, NULL};
}
static unsigned ir, iw, ia, mr, mw;
static void observe(void *user, const dac_trace_event *e) {
  (void)user;
  assert(e->source == 3 && e->master == DAC_MASTER_CPU);
  if (!strcmp(e->kind, "IR")) ir++;
  if (!strcmp(e->kind, "IW")) iw++;
  if (!strcmp(e->kind, "IA")) ia++;
  if (!strcmp(e->kind, "MR")) mr++;
  if (!strcmp(e->kind, "MW")) mw++;
}
static void boot_program(uint8_t *rom) {
  /* Original synthetic test: copy ROM into shadow RAM, switch overlay off,
   * consume exactly one FIFO byte, issue a write, halt. */
  const uint8_t code[] = {
    0x31, 0x00, 0xf0, 0x21, 0, 0, 0x11, 0, 0, 0x01, 0, 8, 0xed, 0xb0,
    0x3e, 0x5a, 0xd3, 0x28, 0x01, 0x02, 0x12, 0xed, 0x78,
    0x32, 0x00, 0x80, 0x3e, 0xc3, 0xd3, 0x04, 0x76};
  memset(rom, 0, 2048);
  memcpy(rom, code, sizeof(code));
}
static void board(void) {
  pc1715 *m = malloc(sizeof(*m)), *split = malloc(sizeof(*split));
  assert(m && split);
  uint8_t rom[2048];
  boot_program(rom);
  pc1715_init(m);
  assert(pc1715_load(m, rom, 2047) == -EINVAL);
  assert(!pc1715_load(m, rom, sizeof(rom)));
  pc1715_write(m, 0, 0x42);
  assert(pc1715_read(m, 0) == rom[0] && m->ram[0] == 0x42);
  pc1715_write(m, 0x800, 0x66);
  assert(pc1715_read(m, 0x800) == 0x66); /* no ROM mirroring */
  card_state s = {0}, ss = {0};
  pc1715_card c = card(&s), cs = card(&ss);
  assert(!pc1715_attach(m, &c));
  m->trace = (dac_trace_sink){observe, NULL, 0, 0};
  pc1715_run(m, 60000);
  assert(!m->rom_enabled && (m->cpu.pins & Z80_HALT));
  assert(m->ram[0x8000] == 0xa5 && s.reads == 1 && s.writes == 2);
  assert(s.address == 0xc304 && s.data == 0xc3 && s.ticks == 60000);
  assert(ir == 1 && iw == 2 && !ia && mr && mw);
  assert(pc1715_load(m, rom, sizeof(rom)) == -EBUSY);
  assert(pc1715_attach(m, NULL) == -EBUSY);
  assert(!memcmp(m->ram, rom, 2048));
  pc1715_init(split);
  assert(!pc1715_load(split, rom, sizeof(rom)) && !pc1715_attach(split, &cs));
  pc1715_write(split, 0x800, 0x66);
  for (unsigned i = 0; i < 60000; i++) pc1715_run(split, 1);
  assert(!memcmp(m->ram, split->ram, 65536));
  assert(!memcmp(&m->cpu.cpu, &split->cpu.cpu, sizeof(z80_t)));
  assert(s.reads == ss.reads && s.writes == ss.writes);
  pc1715_reset(m);
  assert(m->rom_enabled && !m->cpu.cycles && s.resets == 2);
  assert(m->ram[0x8000] == 0xa5); /* reset does not erase physical RAM */
  assert(!pc1715_attach(m, NULL));
  pc1715_run(m, 60000);
  assert(m->ram[0x8000] == 0xff && m->unclaimed_reads == 1);
  free(split);
  free(m);
}
static void interrupts(void) {
  pc1715 *m = calloc(1, sizeof(*m));
  assert(m);
  uint8_t rom[2048] = {0x31, 0x00, 0xf0, 0xed, 0x56, 0xfb, 0x76, 0x18, 0xfd};
  const uint8_t isr[] = {0x3e, 0x77, 0x32, 0x00, 0x90, 0xed, 0x4d};
  memcpy(rom + 0x38, isr, sizeof(isr));
  card_state s = {0};
  pc1715_card c = card(&s);
  pc1715_init(m);
  assert(!pc1715_load(m, rom, sizeof(rom)) && !pc1715_attach(m, &c));
  s.irq = 1;
  ir = iw = ia = 0;
  m->trace = (dac_trace_sink){observe, NULL, 0, 0};
  pc1715_run(m, 1000);
  assert(m->ram[0x9000] == 0x77 && s.acks == 1 && s.retis == 1);
  assert(ia == 1 && !ir && !iw && !s.reads && !s.writes);
  free(m);
}
static int slow_io(void *p, uint16_t address, int write) {
  card_state *s = p;
  assert((address & 255) == (write ? 4 : 2));
  return s->ticks < (write ? 400u : 200u);
}
static void waits(void) {
  uint8_t rom[2048] = {0x01, 2, 0x12, 0xed, 0x78, 0x32, 0, 0x80,
                      0x3e, 0xc3, 0xd3, 4, 0x76};
  pc1715 *m = malloc(sizeof(*m));
  assert(m);
  pc1715_init(m);
  card_state state = {0};
  pc1715_card c = card(&state); c.wait = slow_io;
  assert(!pc1715_load(m, rom, sizeof(rom)) && !pc1715_attach(m, &c));
  assert(!pc1715_onboard_enable(m));
  assert(pc1715_onboard_write(m,8,0x87));assert(pc1715_onboard_write(m,8,2));
  pc1715_run(m, 100);
  assert(m->ctc[0].pending); /* onboard clocks continue through a card WAIT */
  assert(m->io_waiting && !state.reads && !state.writes);
  assert(m->cpu.cycles == 100 && state.ticks == 100);
  pc1715_run(m, 200);
  assert(state.reads == 1 && !state.writes && m->ram[0x8000] == 0xa5);
  assert(m->io_waiting); /* write stalls without a repeated callback */
  pc1715_run(m, 200);
  assert(state.reads == 1 && state.writes == 1 && state.data == 0xc3);
  assert(m->cpu.pins & Z80_HALT);
  assert(m->wait_ticks > 300 && !(m->cpu.pins & Z80_WAIT));
  pc1715_reset(m); pc1715_run(m, 100);
  assert(m->io_waiting);
  pc1715_reset(m);
  assert(!m->io_waiting && !m->wait_ticks && !(m->cpu.pins & Z80_WAIT));
  free(m);
}
static void runtime(void) {
  uint8_t rom[2048], data = 0;
  boot_program(rom);
  dac_session *s = dac_create(3), *wm = dac_create(2);
  assert(s && wm && !dac_create(4));
  assert(dac_power(s, 1) == -ENOENT);
  assert(dac_load(s, 1, rom, 256) == -EINVAL);
  assert(!dac_load(s, 0, rom, sizeof(rom)));
  card_state state = {0};
  pc1715_card c = card(&state);
  assert(dac_pc1715_attach(wm, &c) == -ENOTSUP);
  assert(!dac_pc1715_attach(s, &c));
  assert(!dac_power(s, 1)); /* no W/M CAS PROM required */
  assert(dac_pc1715_attach(s, NULL) == -EBUSY);
  ir = iw = ia = mr = mw = 0;
  dac_trace_sink sink = {observe, NULL, 0, 0};
  assert(!dac_set_trace(s, &sink) && dac_run(s, 60000) == 60000);
  assert(ir == 1 && iw == 2 && mr && mw);
  dac_observation result;
  assert(!dac_observe(s, &result) && result.cycles == 60000 && !result.bank && result.halted);
  assert(!dac_peek(s, DAC_MEMORY_RAM, 0x8000, &data, 1) && data == 0xa5);
  assert(dac_peek(s, DAC_MEMORY_RAM, 65536, &data, 1) == -EINVAL);
  assert(dac_peek(s, DAC_MEMORY_ROM, 2048, &data, 1) == -EINVAL);
  assert(dac_peek(s, DAC_MEMORY_VIDEO, 0, &data, 1) == -ENOTSUP);
  assert(!dac_video(s) && !dac_width(s) && !dac_height(s));
  assert(dac_mount_unit(s, 0, rom, sizeof(rom), 0) == -ENOTSUP);
  assert(dac_key(s, 'A', 1) == -ENOTSUP);
  assert(!dac_state_size(s) && dac_state_save(s, rom, sizeof(rom)) == -ENOTSUP);
  assert(dac_state_load(s, rom, sizeof(rom)) == -ENOTSUP);
  assert(!dac_reset(s) && state.resets == 2);
  assert(!dac_observe(s, &result) && result.cycles == 0 && result.bank == 1);
  assert(dac_run(s, 60000) == 60000 && state.reads == 1);
  assert(!dac_power(s, 0) && !dac_pc1715_attach(s, NULL));
  assert(!dac_power(s, 1) && dac_run(s, 60000) == 60000);
  assert(!dac_peek(s, DAC_MEMORY_RAM, 0x8000, &data, 1) && data == 0xff);
  dac_destroy(s);
  dac_destroy(wm);
}
static void ow(pc1715 *m,unsigned port,uint8_t value){assert(pc1715_onboard_write(m,port,value));}
static uint8_t rd(pc1715 *m,unsigned port){uint8_t v;assert(pc1715_onboard_read(m,port,&v));return v;}
static void wr(pc1715 *m,unsigned ch,unsigned reg,uint8_t value){ow(m,14+ch,reg);ow(m,14+ch,value);}
static void counter(pc1715 *m,unsigned ch){ow(m,8+ch,0xd7);ow(m,8+ch,1);}
static void edge(pc1715 *m,unsigned ch){pc1715_ctc_input(m,ch,0);pc1715_ctc_input(m,ch,1);}
static void sio_setup(pc1715 *m){
  wr(m,1,2,0x60);wr(m,0,1,0x13);wr(m,1,1,0x17);
  for(unsigned ch=0;ch<2;ch++){wr(m,ch,3,1);wr(m,ch,5,8);}
}
static void motherboard_chain(void){
  pc1715 *m=malloc(sizeof(*m));assert(m);pc1715_init(m);
  assert(!pc1715_onboard_enable(m));card_state state={0};pc1715_card c=card(&state);
  assert(!pc1715_attach(m,&c));ow(m,8,0x40);counter(m,0);counter(m,3);sio_setup(m);
  edge(m,3);assert(!pc1715_sio_receive(m,1,0x55));state.irq=1;
  assert(pc1715_irq_ack(m)==0xff && state.acks==1);
  assert(!pc1715_irq_pending(m));pc1715_irq_reti(m);assert(state.retis==1);
  assert(pc1715_irq_ack(m)==0x46);edge(m,0);
  assert(pc1715_irq_ack(m)==0x40);state.irq=1;
  assert(pc1715_irq_ack(m)==0xff);pc1715_irq_reti(m);
  assert(!pc1715_irq_pending(m));pc1715_irq_reti(m); /* release CTC0 only */
  assert(!pc1715_irq_pending(m));pc1715_irq_reti(m); /* release CTC3 */
  assert(pc1715_irq_ack(m)==0x64);
  assert(!pc1715_sio_receive(m,0,0x33));assert(pc1715_irq_ack(m)==0x6c);
  assert(rd(m,12)==0x33);pc1715_irq_reti(m);assert(m->sio[1].service[0]);
  assert(rd(m,13)==0x55);pc1715_irq_reti(m);assert(!pc1715_irq_pending(m));
  unsigned retis=state.retis;pc1715_irq_reti(m);assert(state.retis==retis);
  /* All six SIO request classes; service blocks all lower priority sources. */
  assert(!pc1715_sio_receive(m,0,1));assert(!pc1715_sio_receive(m,1,2));
  ow(m,12,3);ow(m,13,4);pc1715_sio_external(m,0);pc1715_sio_external(m,1);
  pc1715_run(m,1);
  const uint8_t vectors[]={0x6c,0x68,0x6a,0x64,0x60,0x62};
  for(unsigned n=0;n<6;n++){
    assert(pc1715_irq_ack(m)==vectors[n]);assert(!pc1715_irq_pending(m));
    unsigned ch=n/3,kind=n%3;
    if(!kind)(void)rd(m,12+ch);else ow(m,14+ch,kind==1?0x28:0x10);
    pc1715_irq_reti(m);
  }
  assert(!pc1715_irq_pending(m));
  /* Card shutdown releases the chain without delivering the next RETI to it. */
  state.irq=1;assert(pc1715_irq_ack(m)==0xff);edge(m,0);
  retis=state.retis;pc1715_card_quiesce(m);assert(pc1715_irq_ack(m)==0x40);
  pc1715_irq_reti(m);assert(state.retis==retis && !m->ctc[0].service);
  state.irq=1;assert(!pc1715_irq_pending(m));
  edge(m,0);assert(pc1715_irq_ack(m)==0x40);
  assert(!pc1715_sio_receive(m,0,9));
  pc1715_reset(m);assert(m->onboard && !m->card_offline && !pc1715_irq_pending(m));
  for(unsigned n=0;n<4;n++)assert(!m->ctc[n].service && !m->ctc[n].pending);
  /* Timers, prescalers, constant zero=256, edge polarity and explicit reset. */
  ow(m,8,0x40);ow(m,8,0x87);ow(m,8,2);
  pc1715_run(m,31);assert(!pc1715_irq_pending(m));pc1715_run(m,1);assert(pc1715_irq_ack(m)==0x40);
  ow(m,8,3);assert(!pc1715_irq_pending(m) && !m->ctc[0].service);
  ow(m,9,0xc7);ow(m,9,0);assert(m->ctc[1].count==256);
  pc1715_ctc_input(m,1,1);assert(m->ctc[1].count==256);
  pc1715_ctc_input(m,1,0);assert(m->ctc[1].count==255);
  assert(pc1715_onboard_enable(m)==-EBUSY);
  pc1715_reset(m);ow(m,8,0x40);ow(m,8,0xa7);ow(m,8,2);
  pc1715_run(m,511);assert(!pc1715_irq_pending(m));pc1715_run(m,1);assert(pc1715_irq_ack(m)==0x40);
  pc1715_reset(m);ow(m,8,0x40);ow(m,8,0x9f);ow(m,8,1);
  pc1715_run(m,64);assert(!pc1715_irq_pending(m));edge(m,0);
  pc1715_run(m,15);assert(!pc1715_irq_pending(m));pc1715_run(m,1);assert(pc1715_irq_ack(m)==0x40);
  free(m);
}
static void motherboard_cpu(void){
  pc1715 *m=malloc(sizeof(*m));assert(m);pc1715_init(m);assert(!pc1715_onboard_enable(m));
  /* Synthetic IM2 guest configures a CTC counter through actual OUT cycles.
     ISR increments a RAM byte and executes EI/RETI. */
  const uint8_t boot[]={0x31,0,0xf0,0x3e,0x80,0xed,0x47,0xed,0x5e,
    0x3e,0x40,0xd3,8,0x3e,0xd7,0xd3,8,0x3e,1,0xd3,8,0xfb,0x76,0x18,0xfd};
  memcpy(m->rom,boot,sizeof(boot));m->ram[0x8040]=0;m->ram[0x8041]=0x90;
  const uint8_t handler[]={0x21,0,0xa0,0x34,0xfb,0xed,0x4d};memcpy(m->ram+0x9000,handler,sizeof(handler));
  pc1715_run(m,300);assert(m->cpu.pins&Z80_HALT);edge(m,0);
  pc1715_run(m,300);assert(m->ram[0xa000]==1 && !m->ctc[0].service);
  edge(m,0);pc1715_run(m,300);assert(m->ram[0xa000]==2);
  assert(!pc1715_irq_pending(m));free(m);
}
int main(void) {
  board();
  interrupts();
  runtime();
  waits();
  motherboard_chain();
  motherboard_cpu();
  puts("PASS plain PC1715 memory, bus, WAIT, card/CTC/SIO priority, nesting, IM2/RETI, quiesce and session isolation");
  return 0;
}
