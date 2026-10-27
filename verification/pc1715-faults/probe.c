/* MIT. Native PC1715 fault experiments, not an electrical board simulation.
 * No captured byte sequence is an input. CPU and RAM writes run normally.
 * Component faults and explicitly chosen undriven-bus policies are the only
 * interventions. See README.md for scope, schematic sources and limitations. */
#include "../../machines/robotron1715/pc1715.h"
#include <errno.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum fault { HEALTHY, ROM_OE, ROM_CE, RD_BUFFER, ADDRESS, DATA, ROM_DATA,
             RAM_CONTENTION, DATA_BUFFER, DECODER_ALIAS, DECODER_ALIAS_D3 };
enum floating { FIXED, HOLD, DECAY };
typedef struct {
  pc1715 board;
  dac_z80_bus original;
  enum fault fault;
  enum floating floating;
  uint16_t mask, value;
  uint8_t bias, held, observed, ce, oe, driven;
  uint64_t last_drive;
  unsigned decay;
} experiment;
typedef struct {
  uint64_t cycle;
  uint16_t address;
  uint8_t cpu, connector, ce, oe, driven;
  unsigned reads;
} fetch;

static uint8_t undriven(experiment *x) {
  if (x->floating == FIXED) return x->bias;
  if (x->floating == DECAY && x->board.cpu.cycles-x->last_drive >= x->decay)
    return x->bias;
  return x->held;
}
static uint8_t drive(experiment *x, uint8_t data) {
  x->held=data; x->last_drive=x->board.cpu.cycles;
  return data;
}
static uint8_t read_memory(void *p, uint16_t address) {
  experiment *x=p;
  pc1715 *m=&x->board;
  uint16_t a=x->fault==ADDRESS ? (address & ~x->mask) | x->value : address;
  int selected=m->rom_enabled && a<2048;
  int decoder_fault=x->fault==DECODER_ALIAS || x->fault==DECODER_ALIAS_D3;
  x->ce= !m->rom_enabled || x->fault==ROM_CE;
  /* Logical decoder output during a memory read, NOT a gate-delay model. */
  x->oe= a>=2048 || x->fault==ROM_OE || x->fault==RD_BUFFER || decoder_fault;
  int rom_drives=selected && !x->ce && !x->oe;
  int ram_drives= !selected && x->fault!=RD_BUFFER && x->fault!=DATA_BUFFER;
  if (decoder_fault) {
    ram_drives=1;
    a=(a & ~x->mask) | x->value;
  }
  if (x->fault==RAM_CONTENTION) ram_drives=1;
  uint8_t data=rom_drives ? m->rom[a] : ram_drives ? m->ram[a] : undriven(x);
  /* Low-dominant resolution is a hypothesis, not measured contention voltage. */
  if (rom_drives && ram_drives) data &= m->ram[a];
  if (x->fault==DATA || (x->fault==ROM_DATA && rom_drives))
    data=(data & ~x->mask) | x->value;
  if (x->fault==DECODER_ALIAS_D3) data |= 8;
  x->driven=rom_drives || ram_drives;
  if (x->driven) drive(x,data);
  /* The boot ROM is on CPU D, whereas X2 is buffered DB. */
  x->observed=x->fault==DATA_BUFFER ? x->bias : data;
  return data;
}
static void write_memory(void *p, uint16_t a, uint8_t d) {
  experiment *x=p;
  drive(x,d);
  if (x->fault==DATA_BUFFER) return; /* CPU writes cannot cross an open buffer. */
  if (x->fault==ADDRESS || x->fault==DECODER_ALIAS || x->fault==DECODER_ALIAS_D3)
    a=(a & ~x->mask) | x->value;
  x->original.write(x->original.user,a,d);
}
static uint8_t input(void *p,uint16_t a) {
  experiment *x=p;
  return drive(x,x->original.input(x->original.user,a));
}
static void output(void *p,uint16_t a,uint8_t d) {
  experiment *x=p; drive(x,d); x->original.output(x->original.user,a,d);
}
static uint8_t ack(void *p) {
  experiment *x=p;
  return drive(x,x->original.ack(x->original.user));
}
static int number(const char *s, unsigned long *n) {
  char *end; errno=0; *n=strtoul(s,&end,0);
  return !errno && *s && *s!='-' && !*end;
}
int main(int argc,char **argv) {
  if (argc<10 || argc>12) {
    fprintf(stderr,"usage: %s ROM fault floating bias decay mask value ram-seed ticks [initial-bus [ram-pattern]]\n"
      "fault: healthy|rom-oe-high|rom-ce-high|rd-buffer-high|address-mask|"
      "data-mask|rom-data-mask|ram-contention|data-buffer-open|decoder-ram-alias|decoder-ram-alias-d3-high\n"
      "floating: fixed|hold|decay; seed=0: zero RAM, 1: FF RAM, >=2: xorshift32\n",argv[0]);
    return 2;
  }
  const char *names[]={"healthy","rom-oe-high","rom-ce-high","rd-buffer-high",
    "address-mask","data-mask","rom-data-mask","ram-contention","data-buffer-open",
    "decoder-ram-alias","decoder-ram-alias-d3-high"};
  const char *bus_names[]={"fixed","hold","decay"};
  unsigned f=0,b=0;
  for (;f<sizeof(names)/sizeof(*names) && strcmp(argv[2],names[f]);f++);
  for (;b<3 && strcmp(argv[3],bus_names[b]);b++);
  unsigned long n[6];
  for (unsigned i=0;i<6;i++) if (!number(argv[i+4],&n[i])) return 2;
  unsigned long initial=n[0];
  if (argc>=11 && (!number(argv[10],&initial) || initial>255)) return 2;
  const char *pattern=argc==12 ? argv[11] : "seed";
  unsigned stripe_bit=0, stripe_low=0, stripe_high=0;
  int consumed=0;
  int stripe=sscanf(pattern,"stripe:%u:%u:%u%n",&stripe_bit,&stripe_low,&stripe_high,&consumed)==3 &&
             !pattern[consumed] && stripe_bit<16 && stripe_low<256 && stripe_high<256;
  if (strcmp(pattern,"seed") && !stripe) return 2;
  if (f>=sizeof(names)/sizeof(*names) || b>=3 || n[0]>255 || n[1]>100000 ||
      n[2]>65535 || n[3]>65535 || (n[3]&~n[2]) || n[4]>UINT32_MAX ||
      !n[5] || n[5]>1000000 || ((f==DATA || f==ROM_DATA) && n[2]>255)) return 2;
  experiment *x=calloc(1,sizeof(*x)); fetch *rows=calloc(n[5],sizeof(*rows));
  if (!x || !rows) {free(x);free(rows);return 2;}
  pc1715_init(&x->board);
  FILE *rom=fopen(argv[1],"rb");
  int good=rom && fread(x->board.rom,1,2048,rom)==2048 && fgetc(rom)==EOF && !ferror(rom);
  if (rom) fclose(rom);
  if (!good) {free(x);free(rows);fputs("Expected exactly 2048 ROM bytes\n",stderr);return 2;}
  uint32_t seed=(uint32_t)n[4];
  for (unsigned a=0;a<65536;a++) {
    if (n[4]>=2) {seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;}
    x->board.ram[a]=n[4]==0 ? 0 : n[4]==1 ? 255 : (uint8_t)seed;
    if (stripe) x->board.ram[a]=(a & (1u<<stripe_bit)) ? stripe_high : stripe_low;
  }
  x->fault=(enum fault)f;x->floating=(enum floating)b;x->bias=n[0];x->held=initial;
  x->decay=n[1];x->mask=n[2];x->value=n[3];
  x->original=x->board.cpu.bus;
  x->board.cpu.bus=(dac_z80_bus){x,read_memory,write_memory,input,output,ack};
  unsigned count=0;int was_fetch=0,was_read=0;
  for (unsigned long tick=0;tick<n[5];tick++) {
    pc1715_run(&x->board,1);
    uint64_t pins=x->board.cpu.pins;
    int rd=(pins&(Z80_MREQ|Z80_RD))==(Z80_MREQ|Z80_RD);
    int op=rd && (pins&Z80_M1);
    if (op && !was_fetch) {
      rows[count++]=(fetch){.cycle=x->board.cpu.cycles,.address=Z80_GET_ADDR(pins)};
    }
    if (op) {
      fetch *r=&rows[count-1];r->cpu=Z80_GET_DATA(pins);r->connector=x->observed;
      r->ce=x->ce;r->oe=x->oe;r->driven=x->driven;
    }
    if (rd && !was_read && !op && count) rows[count-1].reads++;
    was_fetch=op;was_read=rd;
  }
  printf("{\"fault\":\"%s\",\"floating\":\"%s\",\"bias\":%lu,\"decay\":%lu,"
         "\"mask\":%lu,\"value\":%lu,\"ram_seed\":%lu,\"ticks\":%lu,"
         "\"initial_bus\":%lu,\"ram_pattern\":\"%s\",\"rom_enabled\":%u,\"io_writes\":%" PRIu64 ",\"fetches\":[",
         names[f],bus_names[b],n[0],n[1],n[2],n[3],n[4],n[5],
         initial,pattern,x->board.rom_enabled,x->board.io_writes);
  for (unsigned i=0;i<count;i++) {
    fetch *r=&rows[i];
    printf("%s{\"cycle\":%" PRIu64 ",\"address\":%u,\"cpu\":%u,\"data\":%u,"
           "\"ce\":%u,\"oe\":%u,\"driven\":%u,\"reads\":%u,\"clocks\":%" PRIu64 "}",
           i?",":"",r->cycle,r->address,r->cpu,r->connector,r->ce,r->oe,r->driven,
           r->reads,i+1<count?rows[i+1].cycle-r->cycle:0);
  }
  puts("]}");free(rows);free(x);return ferror(stdout)?1:0;
}
