#!/usr/bin/env python3
"""Package an existing WASM build with version, source identity and hashes."""
import argparse,hashlib,json,subprocess,zipfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('version');a=p.parse_args()
if not a.version or any(c not in '0123456789abcdefghijklmnopqrstuvwxyz.-' for c in a.version):raise SystemExit('Invalid version')
dist=root/'dist';files=[p for p in dist.rglob('*') if p.is_file() and p.name not in ('manifest.json','SHA256SUMS') and p.suffix!='.zip']
assert (dist/'dac.wasm').is_file() and (dist/'dac.js').is_file()
meta={'version':a.version,'repository':'https://github.com/ddanila/dac-emulation','commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),'abi':1,'emscripten':'6.0.12','sha256':{str(p.relative_to(dist)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}}
# Include the original demo manifest as well.
files.append(dist/'demo/manifest.json');meta['sha256']['demo/manifest.json']=hashlib.sha256(files[-1].read_bytes()).hexdigest()
(dist/'manifest.json').write_text(json.dumps(meta,indent=2)+'\n');files.append(dist/'manifest.json')
(dist/'SHA256SUMS').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(dist)}\n' for p in sorted(files)))
files.append(dist/'SHA256SUMS')
archive=dist/f'dac-emulation-{a.version}-browser.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
 for p in sorted(files):
  info=zipfile.ZipInfo(str(p.relative_to(dist)),date_time=(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,p.read_bytes())
print(archive)
