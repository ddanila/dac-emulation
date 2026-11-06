import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import create from '../../dist/dac.js';
const native=execFileSync('build/keyboard-dive-test',['--synthetic','--trace'],{maxBuffer:64*1024*1024});
const m=await create(),h=m._dac_create(2);
function load(slot,bytes){const p=m._malloc(bytes.length);m.HEAPU8.set(bytes,p);assert.equal(m._dac_load(h,slot,p,bytes.length),0);m._free(p);}
const rom=new Uint8Array(2048);rom[0]=0x76;load(0,rom);load(1,new Uint8Array(256));
const keyboard=new Uint8Array(2048);keyboard.set([1,1,0x80,0xed,0x78,0xd3,0,0xc3,3,0]);load(3,keyboard);
assert.equal(m._dac_power(h,1),0);assert.equal(m._dac_dive_capture(h,1),0);m._dac_matrix(h,4,1);
for(let i=0;i<10;i++)m._dac_run(h,100000);
m._dac_dive_capture(h,0);const count=m._dac_dive_count(h),p=m._dac_dive_data(h,0);
assert.deepEqual(Buffer.from(m.HEAPU8.slice(p,p+count*216)),native);
assert.equal(m._dac_dive_arm(h,2,65536,8,1),0);m._dac_debug_run(h,100000);assert.equal(m._dac_debug_hit(h),3);
m._dac_destroy(h);console.log(`PASS native/WASM keyboard dive: ${count} identical event and register records; trigger stop`);
