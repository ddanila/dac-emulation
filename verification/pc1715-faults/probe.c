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
  unsigned bit_enabled, bit_index, bit_write, bit_read_xor, bit_address_mode;
  uint16_t bit_address_mask, bit_address_value;
  unsigned bit_timed, bit_change_cycle, bit_next_write;
} experiment;
typedef struct {
  uint64_t cycle;
  uint16_t address;
  uint8_t cpu, connector, ce, oe, driven;
  unsigned reads;
  uint8_t read_data[8];
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
static uint16_t bit_address(experiment *x,uint16_t a,int write) {
  if ((x->bit_address_mode==1 && write) || (x->bit_address_mode==2 && !write)) return a;
  return (a & ~x->bit_address_mask) | x->bit_address_value;
}
static uint8_t ram_read(experiment *x,uint16_t a) {
  uint8_t d=x->board.ram[a];
  if (x->bit_enabled) {
    uint8_t bit=1u<<x->bit_index;
    uint8_t value=x->board.ram[bit_address(x,a,0)] ^ (x->bit_read_xor ? bit : 0);
    d=(d & ~bit) | (value & bit);
  }
  return d;
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
  uint8_t data=rom_drives ? m->rom[a] : ram_drives ? ram_read(x,a) : undriven(x);
  /* Low-dominant resolution is a hypothesis, not measured contention voltage. */
  if (rom_drives && ram_drives) data &= ram_read(x,a);
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
  if (!x->bit_enabled) x->original.write(x->original.user,a,d);
  else {
    uint8_t bit=1u<<x->bit_index;
    /* Other seven DRAM bit planes retain the ordinary write address/data. */
    x->original.write(x->original.user,a,(d & ~bit) | (x->board.ram[a] & bit));
    uint16_t ba=bit_address(x,a,1);
    unsigned v=(d>>x->bit_index)&1;
    unsigned mode=x->bit_timed && x->board.cpu.cycles>=x->bit_change_cycle ? x->bit_next_write : x->bit_write;
    switch (mode) {
      case 1: return; /* Selected chip's write-enable never asserts. */
      case 2: v=0; break;
      case 3: v=1; break;
      case 4: v^=1; break;
    }
    x->board.ram[ba]=(x->board.ram[ba]&~bit) | (v<<x->bit_index);
  }
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
  if (argc<10 || (argc>12 && argc!=17 && argc!=18 && argc!=20)) {
    fprintf(stderr,"usage: %s ROM fault floating bias decay mask value ram-seed ticks [initial-bus [ram-pattern]]\n"
      "fault: healthy|rom-oe-high|rom-ce-high|rd-buffer-high|address-mask|"
      "data-mask|rom-data-mask|ram-contention|data-buffer-open|decoder-ram-alias|decoder-ram-alias-d3-high\n"
      "floating: fixed|hold|decay; seed=0: zero RAM, 1: FF RAM, >=2: xorshift32\n"
      "optional after ram-pattern: bit-index bit-address-mask bit-address-value bit-write-mode bit-read-xor\n"
      "write modes: 0 normal, 1 disabled, 2 low, 3 high, 4 inverted\n"
      "optional final bit-address-mode: 0 read+write, 1 read only, 2 write only\n"
      "optional after that: change-cycle next-write-mode (one timed fault transition)\n",argv[0]);
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
  const char *pattern=argc>=12 ? argv[11] : "seed";
  unsigned long bit_config[5]={0};
  unsigned long address_mode=0;
  if (argc>=18 && (!number(argv[17],&address_mode) || address_mode>2)) return 2;
  unsigned long change_cycle=0,next_write=0;
  if (argc==20 && (!number(argv[18],&change_cycle) || change_cycle>1000000 ||
                  !number(argv[19],&next_write) || next_write>4)) return 2;
  if (argc>=17) {
    for (unsigned i=0;i<5;i++) if (!number(argv[12+i],&bit_config[i])) return 2;
    if (bit_config[0]>7 || bit_config[1]>65535 || bit_config[2]>65535 ||
        (bit_config[2]&~bit_config[1]) || bit_config[3]>4 || bit_config[4]>1) return 2;
  }
  unsigned stripe_bit=0, stripe_low=0, stripe_high=0;
  unsigned xor_bit=0,xor_value=0;
  int consumed=0;
  int stripe=sscanf(pattern,"stripe:%u:%u:%u%n",&stripe_bit,&stripe_low,&stripe_high,&consumed)==3 &&
             !pattern[consumed] && stripe_bit<16 && stripe_low<256 && stripe_high<256;
  int xorstripe=sscanf(pattern,"xorstripe:%u:%u:%u:%u:%u%n",&stripe_bit,&stripe_low,&stripe_high,
                       &xor_bit,&xor_value,&consumed)==5 && !pattern[consumed] &&
                stripe_bit<16 && stripe_low<256 && stripe_high<256 && xor_bit<16 && xor_value<256;
  if (strcmp(pattern,"seed") && !stripe && !xorstripe) return 2;
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
    if (stripe || xorstripe) x->board.ram[a]=(a & (1u<<stripe_bit)) ? stripe_high : stripe_low;
    if (xorstripe && (a & (1u<<xor_bit))) x->board.ram[a] ^= xor_value;
  }
  x->fault=(enum fault)f;x->floating=(enum floating)b;x->bias=n[0];x->held=initial;
  x->decay=n[1];x->mask=n[2];x->value=n[3];
  x->bit_enabled=argc>=17;x->bit_index=bit_config[0];x->bit_address_mode=address_mode;
  x->bit_address_mask=bit_config[1];x->bit_address_value=bit_config[2];
  x->bit_write=bit_config[3];x->bit_read_xor=bit_config[4];
  x->bit_timed=argc==20;x->bit_change_cycle=change_cycle;x->bit_next_write=next_write;
  x->original=x->board.cpu.bus;
  x->board.cpu.bus=(dac_z80_bus){x,read_memory,write_memory,input,output,ack};
  unsigned count=0;int was_fetch=0,was_read=0;
  for (unsigned long tick=0;tick<n[5];tick++) {
    pc1715_run(&x->board,1);
    uint64_t pins=x->board.cpu.pins;
    int rd=(pins&Z80_RD)!=0;
    int op=rd && (pins&Z80_MREQ) && (pins&Z80_M1);
    if (op && !was_fetch) {
      rows[count++]=(fetch){.cycle=x->board.cpu.cycles,.address=Z80_GET_ADDR(pins)};
    }
    if (op) {
      fetch *r=&rows[count-1];r->cpu=Z80_GET_DATA(pins);r->connector=x->observed;
      r->ce=x->ce;r->oe=x->oe;r->driven=x->driven;
    }
    if (rd && !was_read && !op && count) rows[count-1].reads++;
    if (rd && !op && count) {
      fetch *r=&rows[count-1];
      if (!r->reads || r->reads>8) {free(rows);free(x);return 3;}
      r->read_data[r->reads-1]=Z80_GET_DATA(pins);
    }
    was_fetch=op;was_read=rd;
  }
  printf("{\"fault\":\"%s\",\"floating\":\"%s\",\"bias\":%lu,\"decay\":%lu,"
         "\"mask\":%lu,\"value\":%lu,\"ram_seed\":%lu,\"ticks\":%lu,"
         "\"initial_bus\":%lu,\"ram_pattern\":\"%s\",\"rom_enabled\":%u,\"io_writes\":%" PRIu64 ","
         "\"bit_fault\":{\"enabled\":%u,\"index\":%u,\"address_mask\":%u,\"address_value\":%u,\"write_mode\":%u,\"read_xor\":%u,\"address_mode\":%u,\"timed\":%u,\"change_cycle\":%u,\"next_write\":%u},\"cpu_a\":%u,\"fetches\":[",
         names[f],bus_names[b],n[0],n[1],n[2],n[3],n[4],n[5],
         initial,pattern,x->board.rom_enabled,x->board.io_writes,
         x->bit_enabled,x->bit_index,x->bit_address_mask,x->bit_address_value,x->bit_write,x->bit_read_xor,x->bit_address_mode,
         x->bit_timed,x->bit_change_cycle,x->bit_next_write,
         x->board.cpu.cpu.a);
  for (unsigned i=0;i<count;i++) {
    fetch *r=&rows[i];
    printf("%s{\"cycle\":%" PRIu64 ",\"address\":%u,\"cpu\":%u,\"data\":%u,"
           "\"ce\":%u,\"oe\":%u,\"driven\":%u,\"reads\":%u,\"clocks\":%" PRIu64 ",\"read_data\":[",
           i?",":"",r->cycle,r->address,r->cpu,r->connector,r->ce,r->oe,r->driven,
           r->reads,i+1<count?rows[i+1].cycle-r->cycle:0);
    for (unsigned j=0;j<r->reads;j++) printf("%s%u",j?",":"",r->read_data[j]);
    printf("]}");
  }
  puts("]}");free(rows);free(x);return ferror(stdout)?1:0;
}
