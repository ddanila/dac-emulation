// Same timed keyboard schedule through the public WASM runtime.
import {readFile, writeFile} from 'node:fs/promises';
import create from '../../dist/dac.js';
const [romPath,diskPath,keysPath,prefix,endArg]=process.argv.slice(2);
if(!endArg)throw Error('usage: wasm_capture.mjs ROM DISK KEYS PREFIX END_MS');
const wasm=await create({wasmBinary:await readFile(new URL('../../dist/dac.wasm',import.meta.url))});
const session=wasm._dac_create(0);
for(const [path,kind] of [[romPath,'rom'],[diskPath,'disk']]) {
 const bytes=await readFile(path),p=wasm._malloc(bytes.length);wasm.HEAPU8.set(bytes,p);
 const error=kind==='rom'?wasm._dac_load(session,0,p,bytes.length):wasm._dac_mount(session,p,bytes.length,1);
 wasm._free(p);if(error)throw Error(kind+' rejected');
}
if(wasm._dac_power(session,1))throw Error('power failed');
const keys=(await readFile(keysPath,'utf8')).trim().split('\n').map(line=>{
 const [ms,key,down]=line.split(/\s+/);return [Number(ms)*2000,parseInt(key,16),Number(down)];
});
let cycles=0,index=0,next=0;const limit=Number(endArg)*2000,samples=[];
async function capture() {
 const pixels=wasm._dac_video(session),width=wasm._dac_width(session),height=wasm._dac_height(session);
 const packed=Buffer.alloc(width*height/8,255);
 for(let i=0;i<width*height;i++)if(wasm.HEAPU8[pixels+i*4]===0xa0)packed[i>>3]&=~(128>>(i&7));
 await writeFile(prefix+`-${Math.round(cycles/2000)}.pbm`,Buffer.concat([Buffer.from(`P4\n${width} ${height}\n`),packed]));
 return {width,height};
}
while(cycles<limit) {
 while(keys[index] && cycles>=keys[index][0]) {
  if(wasm._dac_key(session,keys[index][1],keys[index][2]))throw Error('key rejected');index++;
 }
 const target=Math.min(limit,next,keys[index]?.[0]??limit);
 if(target>cycles) {
  const advanced=wasm._dac_run(session,target-cycles);if(!advanced)throw Error('no progress');cycles+=advanced;
 }
 if(cycles>=next) {
  if(cycles>=17*2000000 && cycles<limit)await capture();
  samples.push({cycles,width:wasm._dac_width(session),height:wasm._dac_height(session)});
  next+=40000;
 }
}
const dimensions=await capture();
await writeFile(prefix+'.json',JSON.stringify({cycles,keys:index,...dimensions,samples})+'\n');
const diskPointer=wasm._dac_disk_data(session),diskSize=wasm._dac_disk_size(session);
if(!diskPointer || !diskSize)throw Error('disk unavailable');
await writeFile(prefix+'.juk',Buffer.from(wasm.HEAPU8.slice(diskPointer,diskPointer+diskSize)));
wasm._dac_destroy(session);
