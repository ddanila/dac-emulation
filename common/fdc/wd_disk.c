#include "wd_disk.h"
#include <errno.h>
#include <string.h>
#include <stdlib.h>

int wd_disk_bind(wd_disk* disk, dac_storage storage, int heads, int writable) {
  return wd_disk_bind_geometry(disk, storage,
      (dac_geometry){JUK_TRACKS, (unsigned)heads, JUK_SECTORS_PER_TRACK, JUK_SECTOR_SIZE, 1}, writable);
}
int wd_disk_bind_geometry(wd_disk* disk, dac_storage storage, dac_geometry geometry, int writable) {
  if (!disk || geometry.tracks>80 || !geometry.heads || geometry.heads>2 ||
      !geometry.sectors || geometry.sectors>WD_MAX_SECTORS ||
      geometry.sector_size<128 || geometry.sector_size>WD_MAX_SECTOR_SIZE ||
      (geometry.sector_size & (geometry.sector_size-1)) || geometry.first_sector+geometry.sectors>256) return -EINVAL;
  dac_media media;
  int result = dac_media_init(&media, storage, geometry, writable);
  if (result) return result;
  memset(disk, 0, sizeof(*disk));
  disk->heads = (int)geometry.heads;
  disk->size = (long)storage.size;
  disk->writable = writable != 0;
  disk->media = media;
  return 0;
}
long wd_disk_offset(const wd_disk* disk, int track, int head, int sector) {
  uint64_t offset;
  if(disk && disk->imd){
    if(track<0 || track>=80 || head<0 || head>=2)return -1;
    const wd_track *tr=&disk->tracks[track*2+head];
    for(unsigned i=0;i<tr->count;i++)if(tr->sector[i].id==sector)return tr->sector[i].type ? (long)tr->sector[i].offset : -1;
    return -1;
  }
  if (!disk || dac_media_offset(&disk->media, (unsigned)track,
      (unsigned)head, (unsigned)sector, &offset)) return -1;
  return (long)offset;
}
static long metadata_index(const wd_disk* disk, int track, int head, int sector) {
  if (!disk || !disk->media.storage.read) return -1;
  if (track < 0 || track >= (int)disk->media.geometry.tracks) return -1;
  if (head < 0 || head >= disk->heads) return -1;
  sector -= (int)disk->media.geometry.first_sector;
  if (sector < 0 || sector >= (int)disk->media.geometry.sectors) return -1;
  return ((long)track * 2 + head) * disk->media.geometry.sectors + sector;
}


int wd_disk_read_sector(wd_disk* disk, int t, int h, int s, uint8_t *out) {
  if (!disk) return -EINVAL;
  if(disk->imd){long off=wd_disk_offset(disk,t,h,s);return off<0 ? -ENOENT : disk->media.storage.read(disk->media.storage.user,(uint64_t)off,out,wd_disk_sector_size(disk,t,h,s));}
  return dac_media_read(&disk->media, (unsigned)t, (unsigned)h, (unsigned)s, out);
}
int wd_disk_write_sector(wd_disk* disk, int t, int h, int s, const uint8_t *in) {
  if (!disk || !disk->writable) return -EROFS;
  if(disk->imd){long off=wd_disk_offset(disk,t,h,s);return off<0 ? -ENOENT : disk->media.storage.write(disk->media.storage.user,(uint64_t)off,in,wd_disk_sector_size(disk,t,h,s));}
  return dac_media_write(&disk->media, (unsigned)t, (unsigned)h, (unsigned)s, in);
}
static const wd_sector *imd_sector(const wd_disk *d,int t,int h,int s){
 if(!d || !d->imd || t<0 || t>=80 || h<0 || h>1)return NULL;
 const wd_track *tr=&d->tracks[t*2+h];for(unsigned i=0;i<tr->count;i++)if(tr->sector[i].id==s)return &tr->sector[i];return NULL;
}
int wd_disk_sector_deleted(const wd_disk* disk, int track, int head, int sector) {
  if(disk && disk->imd){const wd_sector *p=imd_sector(disk,track,head,sector);return p ? (p->type==3 || p->type==7) : -EINVAL;}
  long index = metadata_index(disk, track, head, sector);
  if (index < 0) return -EINVAL;
  return disk->deleted_data[index] != 0;
}


int wd_disk_set_sector_deleted(wd_disk* disk, int track, int head, int sector, int deleted) {
  if (!disk || !disk->writable) return -EROFS;
  if(disk->imd){wd_sector *p=(wd_sector *)imd_sector(disk,track,head,sector);if(!p || !p->type)return -EINVAL;
    uint8_t type=deleted?3:1;int r=disk->media.storage.write(disk->media.storage.user,p->offset-1,&type,1);if(!r)p->type=type;return r;}
  long index = metadata_index(disk, track, head, sector);
  if (index < 0) return -EINVAL;
  uint8_t value = deleted != 0;
  if (disk->marks.write) {
    int result = disk->marks.write(disk->marks.user, (uint64_t)index, &value, 1);
    if (result) return result;
  }
  disk->deleted_data[index] = value;
  return 0;
}

unsigned wd_disk_sector_size(const wd_disk *d,int t,int h,int s){
 const wd_sector *p=imd_sector(d,t,h,s);return d ? (d->imd ? (p ? 128u<<p->code : 0) : d->media.geometry.sector_size) : 0;
}
unsigned wd_disk_sector_count(const wd_disk *d,int t,int h){return !d || t<0 || t>=80 || h<0 || h>1 ? 0 : d->imd ? d->tracks[t*2+h].count : d->media.geometry.sectors;}
int wd_disk_sector_id(const wd_disk *d,int t,int h,unsigned i){return i>=wd_disk_sector_count(d,t,h) ? -1 : d->imd ? d->tracks[t*2+h].sector[i].id : (int)(d->media.geometry.first_sector+i);}
int wd_disk_encoding(const wd_disk *d,int t,int h){return !d || t<0 || t>=80 || h<0 || h>1 ? -1 : d->imd ? d->tracks[t*2+h].fm : 0;}
int wd_disk_sector_error(const wd_disk *d,int t,int h,int s){const wd_sector *p=imd_sector(d,t,h,s);return p && p->type>=5;}
int wd_disk_id(const wd_disk *d,int t,int h,int s,uint8_t out[4]){
 const wd_sector *p=imd_sector(d,t,h,s);
 if(d && d->imd){if(!p)return -ENOENT;out[0]=p->cylinder;out[1]=p->head;out[2]=p->id;out[3]=p->code;return 0;}
 if(wd_disk_offset(d,t,h,s)<0)return -ENOENT;
 unsigned size=d->media.geometry.sector_size,code=0;while(size>128){size>>=1;code++;}
 out[0]=(uint8_t)t;out[1]=(uint8_t)h;out[2]=(uint8_t)s;out[3]=(uint8_t)code;return 0;
}
/* Normalize compressed records before mounting, so guest writes never move
 * other sectors. Preserve ID maps, missing sectors, deleted and CRC-error flags. */
static int imd_parse(const uint8_t *b,size_t n,uint8_t *out,size_t *length,wd_disk *d){
 if(n<5 || memcmp(b,"IMD ",4))return -EINVAL;
 size_t pos=4;while(pos<n && b[pos]!=0x1a)pos++;
 if(pos==n || pos>65535)return -EINVAL;
 pos++;size_t used=pos;if(out)memcpy(out,b,pos);
 unsigned seen[160]={0};
 while(pos<n){
  if(n-pos<5)return -EINVAL;
  unsigned mode=b[pos],t=b[pos+1],flags=b[pos+2],h=flags&1,count=b[pos+3],code=b[pos+4];
  if((mode!=2 && mode!=5)||t>=80||(flags&0x3e)||!count||count>WD_MAX_SECTORS||code>4)return -ENOTSUP;
  if(seen[t*2+h]++)return -EINVAL;
  size_t header=5+count*(1+!!(flags&0x80)+!!(flags&0x40));
  if(header>n-pos || used+header>2*1024*1024)return -EINVAL;
  const uint8_t *ids=b+pos+5,*cyl=flags&0x80 ? ids+count:NULL,*heads=flags&0x40 ? ids+count*(1+!!cyl):NULL;
  if(out)memcpy(out+used,b+pos,header);used+=header;pos+=header;
  wd_track *tr=d?&d->tracks[t*2+h]:NULL;if(tr){tr->count=count;tr->fm=mode==2;}
  unsigned id_seen[256]={0};
  for(unsigned i=0;i<count;i++){
   if(id_seen[ids[i]]++ || pos>=n)return -EINVAL;
   unsigned type=b[pos++],size=128u<<code;if(type>8)return -EINVAL;
   unsigned bytes=type ? (type&1 ? size : 1) : 0;
   if(bytes>n-pos || used+1+(type?size:0)>2*1024*1024)return -EINVAL;
   if(tr){tr->sector[i]=(wd_sector){(uint32_t)(used+1),ids[i],cyl?cyl[i]:(uint8_t)t,heads?heads[i]:(uint8_t)h,(uint8_t)code,(uint8_t)(type && !(type&1)?type-1:type)};}
   if(out){out[used]=type && !(type&1)?type-1:type;if(type){if(type&1)memcpy(out+used+1,b+pos,size);else memset(out+used+1,b[pos],size);}}
   used+=1+(type?size:0);pos+=bytes;
  }
  if(d){if(t+1>d->media.geometry.tracks)d->media.geometry.tracks=t+1;if(h+1>(unsigned)d->heads)d->heads=h+1;}
 }
 if(!seen[0])return -EINVAL;
 *length=used;return 0;
}
int wd_disk_import(const void *data,size_t n,uint8_t **out,size_t *length){
 if(!data || !out || !length)return -EINVAL;
 if(n==JUK_SINGLE_SIDED_SIZE || n==JUK_DOUBLE_SIDED_SIZE){
  /* An IMD signature takes precedence over coincidental raw image length. */
  if(memcmp(data,"IMD ",4)){*out=malloc(n);if(!*out)return -ENOMEM;memcpy(*out,data,n);*length=n;return 0;}
 }
 uint8_t *copy=malloc(2*1024*1024);if(!copy)return -ENOMEM;
 int r=imd_parse(data,n,copy,length,NULL);if(r){free(copy);return r;}
 *out=copy;return 0;
}
int wd_disk_bind_image(wd_disk *d,dac_storage storage,int writable){
 if(!d || !storage.read || storage.size<4 || (writable && !storage.write))return -EINVAL;
 uint8_t magic[4];if(storage.read(storage.user,0,magic,4))return -EINVAL;
 if(memcmp(magic,"IMD ",4))return wd_disk_bind(d,storage,storage.size==JUK_DOUBLE_SIDED_SIZE?2:1,writable);
 if(storage.size>2*1024*1024)return -EINVAL;
 uint8_t *bytes=malloc((size_t)storage.size);if(!bytes)return -ENOMEM;
 int r=storage.read(storage.user,0,bytes,(size_t)storage.size);size_t size=0;
 if(!r){memset(d,0,sizeof(*d));r=imd_parse(bytes,(size_t)storage.size,NULL,&size,d);}
 free(bytes);if(r)return r;if(size!=storage.size)return -EINVAL; /* import first */
 d->imd=1;d->size=(long)size;d->writable=!!writable;d->media.storage=storage;d->media.writable=!!writable;
 d->media.geometry.heads=d->heads;return 0;
}
