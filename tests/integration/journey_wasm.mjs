import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import create from '../../dist/dac.js';
const native=execFileSync('build/journey-test',['--trace'],{maxBuffer:64*1024*1024});
const m=await create(),h=m._dac_create(2);
function load(slot,bytes){const p=m._malloc(bytes.length);m.HEAPU8.set(bytes,p);assert.equal(m._dac_load(h,slot,p,bytes.length),0);m._free(p);}
const rom=new Uint8Array(2048);rom.set([0xf3,0x31,0,0xf0,0x3e,0x61,0x32,0,0x30,0x3a,0,0x30,0xd3,4,0x3c,0xc3,6,0]);load(0,rom);load(1,new Uint8Array(256).fill(15));
assert.equal(m._dac_power(h,1),0);assert.equal(m._dac_journey_capture(h,7),0);m._dac_run(h,20000);m._dac_journey_stop(h);
const count=m._dac_journey_count(h),p=m._dac_journey_data(h,0);assert.deepEqual(Buffer.from(m.HEAPU8.slice(p,p+count*96*4)),native);m._dac_destroy(h);console.log(`PASS native/WASM journey: ${count} identical event, peripheral and register records`);
