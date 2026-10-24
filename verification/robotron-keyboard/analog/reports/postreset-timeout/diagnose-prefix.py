from pathlib import Path
import sys,json,hashlib,gzip,lzma,struct
repository=next(p for p in Path(__file__).resolve().parents if (p/'verification/robotron-keyboard/analog/bus_observation.py').is_file())
sys.path.insert(0,str(repository/'verification/robotron-keyboard/analog'))
from raw_waveform import header
from bus_observation import measure
root=Path('build/keyboard-controller-analog/trtol-postreset-raw-25')
retained=json.loads(Path('verification/robotron-keyboard/analog/reports/postreset-timeout/assessment.json').read_text())
source=root/'waveform.raw.xz.partial'
assert hashlib.sha256(source.read_bytes()).hexdigest()==retained['rawPartial']['sha256']
trace=root/'diagnostic-bus-prefix.txt.gz';count=0;first=last=None
with gzip.open(trace,'wt') as dest:
 expected=['time',*[f'v(n_d{i})' for i in range(8)],'v(n_p5v)']
 dest.write(' '.join(expected)+'\n')
 try:
  with lzma.open(source,'rb') as stream:
   names,_=header(stream);selection=[names.index(n) for n in expected];record=struct.Struct('='+'d'*len(names))
   while True:
    data=stream.read(record.size)
    if len(data)!=record.size:break
    values=record.unpack(data)
    if first is None:first=values[0]
    last=values[0];count+=1
    dest.write(' '.join(format(values[i],'.17g') for i in selection)+'\n')
 except EOFError:pass
rom=bytes(int(v,16) for v in (root/'s600.hex').read_text().split())
try:bus={'assessment':measure((root/'ngspice.log').read_text(),trace.with_suffix(''),25,rom)}
except ValueError as exc:bus={'error':str(exc),'details':getattr(exc,'details',None)}
r={'scope':'Diagnostic only: available complete samples from an immutable timed-out partial archive. Full original log is retained; no failing read is omitted. Not full-window acceptance.', 'qualified':False,'sourcePartialSha256':retained['rawPartial']['sha256'],'rows':count,'firstSeconds':first,'lastSeconds':last,'bus':bus}
(root/'prefix-diagnostic.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
