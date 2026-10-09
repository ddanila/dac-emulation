// Optional original-system parity. Inputs stay outside the repository.
import assert from 'node:assert/strict';
import {readFile,mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import create from '../../dist/dac.js';
const [rom,prom,disk]=process.argv.slice(2).map(p=>resolve(p));
if(!disk)throw Error('usage: node wasm_parity.mjs ROM PROM DISK');
const root=new URL('../../',import.meta.url),work=await mkdtemp(join(tmpdir(),'dac-parity-'));
try{
 const expected=join(work,'native.rgba');execFileSync(fileURLToPath(new URL('build/browser-reference',root)),[rom,prom,disk,expected,'40000000'],{timeout:10000});
 const wasm=await create({wasmBinary:await readFile(new URL('dist/dac.wasm',root))});const s=wasm._dac_create(2);
 for(const [slot,path] of [[0,rom],[1,prom],[3,disk]]){
  const b=await readFile(path),p=wasm._malloc(b.length);wasm.HEAPU8.set(b,p);
  assert.equal(slot===3?wasm._dac_mount(s,p,b.length,1):wasm._dac_load(s,slot,p,b.length),0);wasm._free(p);
 }
 assert.equal(wasm._dac_power(s,1),0);for(let i=0;i<400;i++)assert.equal(wasm._dac_run(s,100000),100000);
 const p=wasm._dac_video(s),pixels=wasm.HEAPU8.slice(p,p+640*384*4);
 assert.deepEqual(Buffer.from(pixels),await readFile(expected));assert(wasm._dac_disk_activity(s)>0);wasm._dac_destroy(s);
 console.log('PASS native/WASM original Robotron boot pixels:',createHash('sha256').update(pixels).digest('hex'));
}finally{await rm(work,{recursive:true,force:true});}
