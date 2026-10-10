// Optional original-system parity. Inputs stay outside the repository.
import assert from 'node:assert/strict';
import {readFile,mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import create from '../../dist/dac.js';
const [rom,prom,disk]=process.argv.slice(2,5).map(p=>resolve(p));
if(!disk)throw Error('usage: node wasm_parity.mjs ROM PROM DISK');
const root=new URL('../../',import.meta.url),work=await mkdtemp(join(tmpdir(),'dac-parity-'));
try{
 const expected=join(work,'native.rgba');execFileSync(fileURLToPath(new URL('build/browser-reference',root)),[rom,prom,disk,expected,'100000000'],{timeout:30000});
 const wasm=await create({wasmBinary:await readFile(new URL('dist/dac.wasm',root))});const s=wasm._dac_create(2);
 for(const [slot,path] of [[0,rom],[1,prom],[3,disk]]){
  const b=await readFile(path),p=wasm._malloc(b.length);wasm.HEAPU8.set(b,p);
  assert.equal(slot===3?wasm._dac_mount(s,p,b.length,1):wasm._dac_load(s,slot,p,b.length),0);wasm._free(p);
 }
 const keyboardArg=process.argv.indexOf('--keyboard');
 if(keyboardArg>=0) {
  if(process.argv.includes('--file-operations'))throw Error('Use matrix tests for firmware keyboard input; file operations use the legacy adapter');
  const bytes=await readFile(process.argv[keyboardArg+1]),p=wasm._malloc(bytes.length);
  wasm.HEAPU8.set(bytes,p);assert.equal(wasm._dac_load(s,3,p,bytes.length),0);wasm._free(p);
 }
 assert.equal(wasm._dac_power(s,1),0);
 const stateSize=wasm._dac_state_size(s), state=wasm._malloc(stateSize);
 for(let i=0;i<1000;i++) {
  assert.equal(wasm._dac_run(s,100000),100000);
  if(i===49) assert.equal(wasm._dac_state_save(s,state,stateSize),0);
 }
 const p=wasm._dac_video(s),pixels=wasm.HEAPU8.slice(p,p+wasm._dac_width(s)*wasm._dac_height(s)*4);
 assert.deepEqual(Buffer.from(pixels),await readFile(expected));assert(wasm._dac_disk_activity(s)>0);
 assert.equal(wasm._dac_state_load(s,state,stateSize),0);wasm._free(state);
 for(let i=0;i<950;i++)wasm._dac_run(s,100000);
 const resumed=wasm._dac_video(s);
 assert.deepEqual(wasm.HEAPU8.slice(resumed,resumed+pixels.length),pixels);
 console.log('PASS historical mid-boot snapshot resumes to identical framebuffer');
 console.log('PASS native/WASM original Robotron boot pixels:' ,createHash('sha256').update(pixels).digest('hex'));
 if(process.argv.includes('--file-operations')) {
  const keys='PIP DAC.TXT=CON:\rDAC REGRESSION\r\x1aTYPE DAC.TXT\rPIP DAC2.TXT=DAC.TXT\rPIP DAC.COM=PIP.COM\r';
  const exported=join(work,'session.img');
  execFileSync(fileURLToPath(new URL('build/robotron-boot',root)),[rom,prom,disk,'100000000',keys,'--writable','--export',exported],{timeout:30000,stdio:'pipe'});
  function run(ticks) { while(ticks) {const n=Math.min(ticks,100000);assert.equal(wasm._dac_run(s,n),n);ticks-=n;} }
  for(const ch of keys) {const key=ch.charCodeAt(0);assert.equal(wasm._dac_key(s,key,1),0);run([10,13,26].includes(key)?32000000:1000000);}
  run(32000000);
  const ptr=wasm._dac_disk_data(s),size=wasm._dac_disk_size(s);
  const actual=wasm.HEAPU8.slice(ptr,ptr+size),expectedDisk=await readFile(exported);
  assert.deepEqual(Buffer.from(actual),expectedDisk);
  assert.notDeepEqual(Buffer.from(actual),await readFile(disk));
  console.log('PASS native/WASM create/read/copy disk bytes:',createHash('sha256').update(actual).digest('hex'));
 }
 wasm._dac_destroy(s);
}finally{await rm(work,{recursive:true,force:true});}
