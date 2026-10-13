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
 assert(pixels(s).some((v,i)=>i%4===0&&v===0xa0));
 const n=wasm._dac_state_size(s),p=wasm._malloc(n),before=pixels(s);
 assert(n>65536);assert.equal(wasm._dac_state_save(s,p,n),0);
 wasm._dac_run(s,100000);const after=pixels(s);wasm._dac_power(s,0);
 assert.equal(wasm._dac_state_load(s,p,n),0);assert.deepEqual(pixels(s),before);
 wasm._dac_run(s,100000);assert.deepEqual(pixels(s),after);
 wasm._free(p);wasm._dac_destroy(s);
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
const savedPhase=[0,1].map(u=>wasm._dac_drive_phase_unit(s,u));
assert(savedPhase.every(p=>p>=0&&p<798720));
assert.equal(wasm._dac_drive_phase_unit(s,2),0);
wasm._dac_key(s,65,1);wasm._dac_run(s,50000);
const changedPixels=pixels(s);assert.notDeepEqual(changedPixels,savedPixels);
wasm.HEAPU8[snapshot+n-1]^=1;
assert(wasm._dac_state_load(s,snapshot,n)<0);assert.deepEqual(pixels(s),changedPixels);
wasm.HEAPU8[snapshot+n-1]^=1;
assert.equal(wasm._dac_state_load(s,snapshot,n),0);assert.deepEqual(pixels(s),savedPixels);
assert.deepEqual([0,1].map(u=>wasm._dac_drive_phase_unit(s,u)),savedPhase);
wasm._dac_key(s,65,1);wasm._dac_run(s,50000);assert.deepEqual(pixels(s),changedPixels);
wasm._free(snapshot);wasm._dac_destroy(s);
console.log('PASS WASM snapshot round trip, deterministic continuation and corrupt-state rejection');
// Both drive payloads and write modes participate in a Robotron snapshot.
const dual=wasm._dac_create(2);
for(const [slot,file] of [[0,'robotron.bin'],[1,'cas.bin'],[2,'glyphs.bin']])assert.equal(load(dual,slot,await read(file)),0);
const diskbuf=wasm._malloc(819200);
for(const unit of [0,1]) {
 wasm.HEAPU8.fill(0x41+unit,diskbuf,diskbuf+819200);
 assert.equal(wasm._dac_mount_unit(dual,unit,diskbuf,819200,unit),0);
}
wasm._dac_power(dual,1);wasm._dac_run(dual,100000);
const dualsize=wasm._dac_state_size(dual),dualstate=wasm._malloc(dualsize);
assert.equal(wasm._dac_state_save(dual,dualstate,dualsize),0);
assert(wasm._dac_drive_status_unit(dual,1)&8);
wasm._dac_power(dual,0);
assert(wasm._dac_drive_status_unit(dual,1)&8); // inserted medium remains visible with power off
assert.equal(wasm._dac_mount_unit(dual,1,0,0,0),0);
assert(wasm._dac_state_load(dual,dualstate,dualsize)<0);
assert.equal(wasm._dac_mount_unit(dual,1,diskbuf,819200,1),0);
assert.equal(wasm._dac_state_load(dual,dualstate,dualsize),0);
for(const unit of [0,1]) {
 const ptr=wasm._dac_disk_data_unit(dual,unit);
 assert.equal(wasm._dac_disk_size_unit(dual,unit),819200);
 assert(wasm.HEAPU8.subarray(ptr,ptr+819200).every(b=>b===0x41+unit));
}
wasm._free(diskbuf);wasm._free(dualstate);wasm._dac_destroy(dual);
console.log('PASS two-drive snapshot payloads, mount/eject and media mismatch rejection');
// A snapshot taken between STEP and settling restores fractional pose, motor
// acceleration and the timestamped event ring, not just the final cylinder.
const mechanical=wasm._dac_create(2),seekRom=new Uint8Array(2048);
seekRom.set([0x3e,15,0xd3,0x1d,0x3e,0,0xd3,0x1d,0x3e,3,0xd3,0x1d,0x76]);
assert.equal(load(mechanical,0,seekRom),0);
assert.equal(load(mechanical,1,await read('cas.bin')),0);
wasm._dac_power(mechanical,1);wasm._dac_run(mechanical,30000);
const pose=()=>[wasm._dac_drive_position_unit(mechanical,0),wasm._dac_drive_phase_unit(mechanical,0),wasm._dac_drive_steps_unit(mechanical,0),wasm._dac_drive_step_age(mechanical,0,0),wasm._dac_drive_mechanics_unit(mechanical,0)];
const beforePose=pose();assert(beforePose[0]>0&&beforePose[0]<65536);assert.equal(beforePose[2],1);
const sn=wasm._dac_state_size(mechanical),sp=wasm._malloc(sn);
assert.equal(wasm._dac_state_save(mechanical,sp,sn),0);
wasm._dac_run(mechanical,30000);const afterPose=pose();
assert.equal(wasm._dac_state_load(mechanical,sp,sn),0);assert.deepEqual(pose(),beforePose);
wasm._dac_run(mechanical,30000);assert.deepEqual(pose(),afterPose);
wasm._free(sp);wasm._dac_destroy(mechanical);
console.log('PASS WASM snapshot mid-seek: fractional head, ramp speed, phase and STEP timestamps');

const doorSession=wasm._dac_create(2);
for(const [slot,file] of [[0,'robotron.bin'],[1,'cas.bin']]) load(doorSession,slot,await read(file));
const diskPtr=wasm._malloc(819200);
wasm.HEAPU8.fill(0x5a,diskPtr,diskPtr+819200);
assert.equal(wasm._dac_mount_unit(doorSession,0,diskPtr,819200,1),0);
wasm._free(diskPtr);
assert(wasm._dac_drive_inserted(doorSession,0,0)<0);
assert.equal(wasm._dac_drive_door(doorSession,0,1),0);
assert.equal(wasm._dac_drive_inserted(doorSession,0,0),0);
assert.equal(wasm._dac_drive_status_unit(doorSession,0)&8,0);
assert.equal(wasm._dac_disk_size_unit(doorSession,0),819200);
assert.equal(wasm.HEAPU8[wasm._dac_disk_data_unit(doorSession,0)],0x5a);
assert.equal(wasm._dac_drive_inserted(doorSession,0,1),0);
assert(wasm._dac_drive_status_unit(doorSession,0)&8);
wasm._dac_power(doorSession,1);
assert(wasm._dac_drive_status_unit(doorSession,0)&32);
wasm._dac_reset(doorSession);
assert(wasm._dac_drive_status_unit(doorSession,0)&32);
const dn=wasm._dac_state_size(doorSession),dp=wasm._malloc(dn);
assert.equal(wasm._dac_state_save(doorSession,dp,dn),0);
wasm._dac_drive_door(doorSession,0,0);
assert.equal(wasm._dac_state_load(doorSession,dp,dn),0);
assert(wasm._dac_drive_status_unit(doorSession,0)&32);
assert(wasm._dac_drive_door(doorSession,2,1)<0);
wasm._free(dp);wasm._dac_destroy(doorSession);
console.log('PASS independent drive doors survive power/reset and snapshots');
