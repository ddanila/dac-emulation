/* Optional functional scanout capture. Does not change serialized machine state.
 * This derives connector stimulus from the core's row-latched scanout, not RGB
 * screenshots. BSYN phase/polarity is a declared adapter assumption, not a
 * reconstructed display-board gate-level output. See the monitor lab README.
 */
#include "../../machines/robotron1715m/robotron.h"
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>

static int load(const char *path, void *data, size_t bytes) {
  FILE *f=fopen(path,"rb"); if(!f)return 0;
  int ok=fread(data,1,bytes,f)==bytes && fgetc(f)==EOF;
  fclose(f);return ok;
}
static unsigned number(const char *s, unsigned limit) {
  char *end;errno=0;unsigned long value=strtoul(s,&end,10);
  if(errno || !*s || *end || value>limit) {fprintf(stderr,"Invalid tick budget\n");exit(2);}
  return (unsigned)value;
}
int main(int argc,char **argv) {
  if(argc!=8){fprintf(stderr,"usage: %s ROM2048 PROM256 CHARGEN4096-or-- DISK boot_cpu_ticks capture_dot_ticks OUTPUT.json\n",argv[0]);return 2;}
  unsigned boot=number(argv[5],200000000),end=number(argv[6],13824000);
  if(end<16)return 2;
  robotron *m=calloc(1,sizeof(*m));if(!m)return 2;robotron_init(m);
  if(!load(argv[1],m->rom,sizeof(m->rom))||!load(argv[2],m->prom,sizeof(m->prom))||(strcmp(argv[3],"-")&&!load(argv[3],m->chargen,sizeof(m->chargen)))){free(m);return 2;}
  FILE *df=fopen(argv[4],"rb");if(!df){free(m);return 2;}
  if(fseek(df,0,SEEK_END)){fclose(df);free(m);return 2;}
  long n=ftell(df);if(n<256||n>1048576||fseek(df,0,SEEK_SET)){fclose(df);free(m);return 2;}
  uint8_t *disk=malloc((size_t)n);if(!disk){fclose(df);free(m);return 2;}
  int ok=fread(disk,1,(size_t)n,df)==(size_t)n;fclose(df);
  if(!ok||robotron_disk(m,dac_memory_storage(disk,(size_t)n,0),0)){free(disk);free(m);return 2;}
  robotron_run(m,boot);
  FILE *out=fopen(argv[7],"wx");if(!out){perror(argv[7]);free(disk);free(m);return 2;}
  fprintf(out,"{\"format\":\"dac-monitor-input-v1\",\"clock_hz\":13824000,\"provenance\":\"Functional M/W scanout; 8 dots per 1.728 MHz character. Active-low BSYN during modeled retrace is an unverified adapter assumption. No analog receiver or gate-delay qualification.\",\"boot_cpu_ticks\":%u,\"events\":[",boot);
  unsigned dots=0,last=99,elapsed=0;int first=1;
  /* Bound lack of scanout (e.g. stopped controller); never hang on bad media. */
  while(dots<end && elapsed++<3993600u*2u) {
    unsigned before=m->raster.fraction;robotron_run(m,1);
    if(m->raster.fraction>=before || m->raster.stopped==2)continue;
    unsigned cols=(m->crtc[0]&127)+1;if(cols>80)cols=80;
    unsigned rows=(m->crtc[1]&63)+1;if(rows>24)rows=24;
    unsigned line_clocks=cols+2*((m->crtc[3]&15)+1);
    unsigned col=m->raster.character%line_clocks;
    unsigned line=m->raster.character/line_clocks;
    if(m->crtc[0]&128)line/=2;
    unsigned row=m->raster.row;
    unsigned blank=row>=rows||col>=cols||line>=16;
    unsigned sync=blank?0:1, bits=0, intens=0;
    if(!blank&&m->display_on&&!(m->disconnected&2)&&(m->raster.valid_rows&(1u<<row))) {
      const robotron_video_row *r=&m->raster.scanout[row];
      if(col<r->columns&&line<r->lines){bits=r->pixels[col][line];intens=r->highlight[col][line]?1:0;}
    }
    for(unsigned i=0;i<8&&dots<end;i++,dots++) {
      unsigned video=(bits>>(7-i))&1,value=video|(sync<<1)|(intens<<2);
      if(value!=last){fprintf(out,"%s[%u,%u,%u,%u]",first?"":",",dots,video,sync,intens);first=0;last=value;}
    }
  }
  if(dots!=end){fprintf(stderr,"Controller did not produce the requested scanout; capture rejected\n");fclose(out);free(disk);free(m);return 1;}
  fprintf(out,",[%u,%u,%u,%u]]}\n",dots,last&1,(last>>1)&1,(last>>2)&1);
  ok=!ferror(out);if(fclose(out))ok=0;free(disk);free(m);return ok?0:1;
}
