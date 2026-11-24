// node verification/juku-video/wasm_capture.mjs ROM PREFIX CYCLES
import {readFile, writeFile} from 'node:fs/promises';
import create from '../../dist/dac.js';
const [romPath,prefix,limit]=process.argv.slice(2);
if(!romPath||!prefix||!Number.isSafeInteger(Number(limit))||Number(limit)<=0)
  throw Error('usage: wasm_capture.mjs ROM OUTPUT-PREFIX CYCLES');
const wasm=await create({wasmBinary:await readFile(new URL('../../dist/dac.wasm',import.meta.url))});
const rom=await readFile(romPath),s=wasm._dac_create(0),p=wasm._malloc(rom.length);
wasm.HEAPU8.set(rom,p);
if(wasm._dac_load(s,0,p,rom.length)||wasm._dac_power(s,1))throw Error('ROM rejected');
wasm._free(p);
let cycles=0;
while(cycles<Number(limit)) {
  const advanced=wasm._dac_run(s,Math.min(100000,Number(limit)-cycles));
  if(!advanced)throw Error('no progress');cycles+=advanced;
}
const pixels=wasm._dac_video(s),width=wasm._dac_width(s),height=wasm._dac_height(s);
const packed=Buffer.alloc(width*height/8,255);
for(let i=0;i<width*height;i++)if(wasm.HEAPU8[pixels+i*4]===0xa0)packed[i>>3]&=~(128>>(i&7));
await writeFile(prefix+'.pbm',Buffer.concat([Buffer.from(`P4\n${width} ${height}\n`),packed]));
await writeFile(prefix+'.json',JSON.stringify({cycles,width,height})+'\n');
wasm._dac_destroy(s);
