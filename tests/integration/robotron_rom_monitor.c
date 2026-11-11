/* MIT. Process peer for actual 1715W ROM execution, no guest PC shortcuts.
 * stdin: T hex, S ticks, F physical offset mask value, D, Q.
 * stdout: hex wire replies, one line per command. Artifacts on stderr only.
 */
#include "../../machines/robotron1715m/robotron.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static robotron m;
static uint8_t saved_ram[sizeof(m.ram)], saved_rom[2048], saved_prom[256];
static unsigned fault_at = ~0u, fault_mask, fault_value, no_ram, bad_display;
static unsigned reads, writes, violations, alias_mask, stall_tx, fault_reads;
static unsigned display_writes, first_tx_display_writes = ~0u;
static unsigned peer_baud = 9600;
static uint32_t pixels[640 * 384];
static uint8_t read_bus(void *p, uint16_t a) {
  unsigned mapped = robotron_mapping(p, a, 0), physical = mapped & 0xffffff;
  if ((mapped >> 24) == DAC_SPACE_RAM) {
    reads++;
    if (no_ram) {
      violations++;
      return 0xa5;
    }
    uint8_t v = robotron_read(p, a & ~alias_mask);
    if (physical == fault_at) {
      v = (v & ~fault_mask) | (fault_value & fault_mask);
      if (fault_reads && !--fault_reads)
        fault_at = ~0u;
    }
    return v;
  }
  return robotron_read(p, a);
}
static void write_bus(void *p, uint16_t a, uint8_t v) {
  unsigned mapped = robotron_mapping(p, a, 1);
  if ((mapped >> 24) == DAC_SPACE_RAM) {
    writes++;
    if (no_ram) {
      violations++;
      return;
    }
    a &= ~alias_mask;
  }
  if ((mapped >> 24) == DAC_SPACE_VIDEO || (mapped >> 24) == DAC_SPACE_GLYPHS)
    display_writes++;
  if (bad_display &&
      ((mapped >> 24) == DAC_SPACE_VIDEO || (mapped >> 24) == DAC_SPACE_GLYPHS))
    return;
  robotron_write(p, a, v);
}
static void output_bus(void *p, uint16_t a, uint8_t v) {
  if ((a & 255) == 13 && first_tx_display_writes == ~0u)
    first_tx_display_writes = display_writes;
  if (stall_tx && (a & 255) == 13) {
    m.v24.full = 1;
    return;
  }
  robotron_output(p, a, v);
}
static void load(const char *path, void *dst, size_t size) {
  FILE *f = fopen(path, "rb");
  if (!f || fread(dst, 1, size, f) != size) {
    fprintf(stderr, "bad image %s\n", path);
    exit(2);
  }
  fclose(f);
}
static void output(void) {
  for (unsigned i = 0; i < m.v24.decoded_size; i++)
    printf("%02x", m.v24.decoded[i]);
  puts("");
  fflush(stdout);
  m.v24.decoded_size = 0;
  m.v24.size = 0;
}
int main(int argc, char **argv) {
  if (argc < 3)
    return 2;
  if (argc > 4) peer_baud = (unsigned)strtoul(argv[4], 0, 0);
  robotron_init(&m);
  load(argv[1], m.rom, 2048);
  load(argv[2], m.prom, 256);
  no_ram = argc > 3 && strstr(argv[3], "no-ram");
  bad_display = argc > 3 && strstr(argv[3], "no-display");
  stall_tx = argc > 3 && strstr(argv[3], "no-tx");
  memset(m.ram, 0xa7, sizeof(m.ram));
  memset(m.vram, 0x9b, sizeof(m.vram));
  memset(m.chargen, 0xde, sizeof(m.chargen));
  m.cpu.bus.read = read_bus;
  m.cpu.bus.write = write_bus;
  m.cpu.bus.output = output_bus;
  m.v24.peer_baud = peer_baud;
  m.v24.peer_format = 0x208;
  m.v24.signals = 3;
  robotron_run(&m, peer_baud == 1200 ? 4000000 : 2000000);
  output();
  char line[8192];
  while (fgets(line, sizeof(line), stdin)) {
    if (line[0] == 'Q')
      break;
    if (line[0] == 'T') {
      for (char *q = line + 1; *q && *q != '\n';) {
        while (*q == ' ')
          q++;
        unsigned v;
        if (sscanf(q, "%2x", &v) != 1)
          break;
        m.v24.input[(m.v24.read + m.v24.count) % 65536] = (uint8_t)v;
        m.v24.count++;
        q += 2;
      }
      robotron_run(&m, 1000000);
    } else if (line[0] == 'S')
      robotron_run(&m, (unsigned)strtoul(line + 1, 0, 0));
    else if (line[0] == 'Z') {
      /* Model reset of CPU/devices while retaining DRAM and reference images.
       * This is a controlled fixture event, not a claim about power-on RAM. */
      memcpy(saved_ram, m.ram, sizeof(m.ram));
      memcpy(saved_rom, m.rom, sizeof(m.rom));
      memcpy(saved_prom, m.prom, sizeof(m.prom));
      robotron_init(&m);
      memcpy(m.ram, saved_ram, sizeof(m.ram));
      memcpy(m.rom, saved_rom, sizeof(m.rom));
      memcpy(m.prom, saved_prom, sizeof(m.prom));
      m.cpu.bus.read = read_bus;
      m.cpu.bus.write = write_bus;
      m.cpu.bus.output = output_bus;
      m.v24.peer_baud = peer_baud;
      m.v24.peer_format = 0x208;
      m.v24.signals = 3;
      robotron_run(&m, peer_baud == 1200 ? 4000000 : 2000000);
    } else if (line[0] == 'F') {
      fault_reads = 0;
      sscanf(line + 1, "%x %x %x %u", &fault_at, &fault_mask, &fault_value,
             &fault_reads);
    } else if (line[0] == 'A')
      alias_mask = (unsigned)strtoul(line + 1, 0, 0);
    else if (line[0] == 'U') {
      stall_tx = (unsigned)strtoul(line + 1, 0, 0);
      if (!stall_tx)
        m.v24.full = 0;
    } else if (line[0] == 'B')
      m.v24.peer_baud = (unsigned)strtoul(line + 1, 0, 0);
    else if (line[0] == 'P')
      m.v24.peer_format = (unsigned)strtoul(line + 1, 0, 0);
    else if (line[0] == 'V') {
      unsigned w, h;
      robotron_video(&m, pixels, &w, &h);
      char name[4096];
      if (sscanf(line + 1, "%4095s", name) == 1) {
        FILE *f = fopen(name, "wb");
        if (!f)
          return 2;
        fprintf(f, "P6\n%u %u\n255\n", w, h);
        for (unsigned i = 0; i < w * h; i++) {
          uint8_t rgb[3] = {(pixels[i] >> 16) & 255, (pixels[i] >> 8) & 255,
                            pixels[i] & 255};
          fwrite(rgb, 1, 3, f);
        }
        fclose(f);
      }
    } else if (line[0] == 'D') {
      unsigned w, h, lit = 0;
      robotron_video(&m, pixels, &w, &h);
      for (unsigned i = 0; i < w * h; i++)
        if (pixels[i] != 0xff101812)
          lit++;
      fprintf(stderr,
              "{\"first_tx_display_writes\":%u,\"lit_pixels\":%u,\"pc\":%u,"
              "\"ram_reads\":%u,\"ram_writes\":%u,"
              "\"violations\":%u,\"display\":%u,\"font0\":%u,\"title\":[",
              first_tx_display_writes, lit, m.cpu.cpu.pc, reads, writes,
              violations, m.display_on, m.chargen[128]);
      for (unsigned i = 0; i < 12; i++)
        fprintf(stderr, "%s%u", i ? "," : "", m.vram[i]);
      fprintf(stderr, "]}\n");
    }
    output();
  }
  return violations ? 3 : 0;
}
