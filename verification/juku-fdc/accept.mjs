// Same guest workload through public WASM APIs; input media is a disposable copy.
import {readFile,writeFile} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
const [modulePath,romPath,diskPath,keysPath,prefix]=process.argv.slice(2);
if(!prefix)throw Error('usage: accept.mjs MODULE ROM DISK KEYS OUTPUT_PREFIX');
const {default:create}=await import(pathToFileURL(modulePath));
const m=await create({wasmBinary:await readFile(modulePath.replace(/\.mjs$/,'.wasm'))});
const s=m._dac_create(0);
for(const [file,rom] of [[romPath,true],[diskPath,false]]) {
 const b=await readFile(file),p=m._malloc(b.length);m.HEAPU8.set(b,p);
 const rc=rom?m._dac_load(s,0,p,b.length):m._dac_mount(s,p,b.length,1);
 m._free(p);if(rc)throw Error('load/mount '+rc);
}
if(m._dac_power(s,1))throw Error('power');
const keys=(await readFile(keysPath,'utf8')).trim().split('\n').map(line=>{
 const [t,k,d]=line.split(/\s+/);return [+t,parseInt(k,16),+d];
});
let cycles=0;
for(const [ms,k,d] of [...keys,[90000,0,0]]) {
 while(cycles<ms*2000){const n=m._dac_run(s,Math.min(20000,ms*2000-cycles));if(!n)throw Error('stopped');cycles+=n;}
 if(m._dac_key(s,k,d))throw Error('key');
}
const w=m._dac_width(s),h=m._dac_height(s),p=m._dac_video(s),packed=Buffer.alloc(w*h/8,255);
for(let i=0;i<w*h;i++)if(m.HEAPU8[p+4*i]===0xa0)packed[i>>3]&=~(128>>(i%8));
await writeFile(prefix+'.pbm',Buffer.concat([Buffer.from(`P4\n${w} ${h}\n`),packed]));
await writeFile(prefix+'.juk',m.HEAPU8.slice(m._dac_disk_data(s),m._dac_disk_data(s)+m._dac_disk_size(s)));
m._dac_destroy(s);console.log(JSON.stringify({cycles,width:w,height:h}));
