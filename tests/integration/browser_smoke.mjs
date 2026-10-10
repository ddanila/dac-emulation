import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import create from '../../dist/dac.js';
const wasm=await create({wasmBinary:await readFile(new URL('../../dist/dac.wasm',import.meta.url))});
const read=n=>readFile(new URL('../../dist/demo/'+n,import.meta.url));
function load(s,slot,b){const p=wasm._malloc(b.length);try{wasm.HEAPU8.set(b,p);return wasm._dac_load(s,slot,p,b.length);}finally{wasm._free(p);}}
const a=wasm._dac_create(2),b=wasm._dac_create(2);assert(a&&b&&a!==b);
assert(wasm._dac_power(a,1)<0); // missing firmware
for(const s of [a,b])for(const [slot,file] of [[0,'robotron.bin'],[1,'cas.bin'],[2,'glyphs.bin']])assert.equal(load(s,slot,await read(file)),0);
assert.equal(wasm._dac_power(a,1),0);assert.equal(wasm._dac_run(a,1e9),100000);
function pixels(s){const p=wasm._dac_video(s),n=wasm._dac_width(s)*wasm._dac_height(s)*4;return wasm.HEAPU8.slice(p,p+n);}
const boot=pixels(a);assert(boot.some((v,i)=>i%4===0&&v===0xa0));
assert.notDeepEqual(boot,pixels(b));
for(const c of 'HELLO')assert.equal(wasm._dac_key(a,c.charCodeAt(0),1),0);
wasm._dac_run(a,100000);assert.notDeepEqual(pixels(a),boot);
assert.equal(wasm._dac_reset(a),0);wasm._dac_run(a,100000);assert.deepEqual(pixels(a),boot);
assert.equal(wasm._dac_power(a,0),0);assert.equal(wasm._dac_run(a,100),0);
assert(pixels(a).every((v,i)=>v===(i%4===3?255:0)));wasm._dac_destroy(a);wasm._dac_destroy(b);
for(const [kind,name] of [[0,'juku.bin'],[1,'vjuga.bin']]){
 const s=wasm._dac_create(kind);assert.equal(load(s,0,await read(name)),0);assert.equal(wasm._dac_power(s,1),0);
 for(let i=0;i<5;i++)wasm._dac_run(s,100000);
 assert(pixels(s).some((v,i)=>i%4===0&&v===0xa0));wasm._dac_destroy(s);
}
console.log('PASS WASM: independent instances, bounded slices, power/reset, keyboard, all three machine profiles');
// Snapshot restores CPU/device state as well as pixels, and rejects corruption
// without changing the running instance. This original ROM needs no downloads.
const s=wasm._dac_create(2);
for(const [slot,file] of [[0,'robotron.bin'],[1,'cas.bin'],[2,'glyphs.bin']]) assert.equal(load(s,slot,await read(file)),0);
wasm._dac_power(s,1);wasm._dac_run(s,50000);
const n=wasm._dac_state_size(s), snapshot=wasm._malloc(n);
assert(n>262144);assert.equal(wasm._dac_state_save(s,snapshot,n),0);
const savedPixels=pixels(s);
wasm._dac_key(s,65,1);wasm._dac_run(s,50000);
const changedPixels=pixels(s);assert.notDeepEqual(changedPixels,savedPixels);
wasm.HEAPU8[snapshot+n-1]^=1;
assert(wasm._dac_state_load(s,snapshot,n)<0);assert.deepEqual(pixels(s),changedPixels);
wasm.HEAPU8[snapshot+n-1]^=1;
assert.equal(wasm._dac_state_load(s,snapshot,n),0);assert.deepEqual(pixels(s),savedPixels);
wasm._dac_key(s,65,1);wasm._dac_run(s,50000);assert.deepEqual(pixels(s),changedPixels);
wasm._free(snapshot);wasm._dac_destroy(s);
console.log('PASS WASM snapshot round trip, deterministic continuation and corrupt-state rejection');
