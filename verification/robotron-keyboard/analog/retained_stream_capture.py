"""Run three raw producers with bounded pipes, logs and replayable raw archives.

Commands are built from an inherited raw-output descriptor. The middle stream is
fanned out to two concurrent comparators, so all three levels are executed once.
Separate retention revision of stream_capture; existing pinned campaigns stay unchanged.
This transport layer does not establish circuit, stimulus or firmware admission.
"""
import hashlib
import json
import lzma
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import threading
import time
from filter_truncation_log import diagnostic
from raw_stream_review import compare_streams


def run(build_commands, out, env, expected_end, timeout, *,
        max_log_bytes=1024**3, max_compressed_log_bytes=256*1024**2,
        max_log_line_bytes=1024**2, max_raw_bytes=None, max_compressed_raw_bytes=None):
    if len(build_commands)!=3:raise ValueError('Need three producer commands')
    if not math.isfinite(timeout) or timeout<=0:raise ValueError('Need a finite positive timeout')
    limits={'logicalLogBytes':max_log_bytes,'compressedLogBytes':max_compressed_log_bytes,
            'logLineBytes':max_log_line_bytes, 'logicalRawBytes':max_raw_bytes,
            'compressedRawBytes':max_compressed_raw_bytes}
    if any(type(v) is not int or v<=0 for v in limits.values()):
        raise ValueError('Log and raw budgets must be explicit positive integer byte counts')
    usage={key:0 for key in ('logicalLogBytes','compressedLogBytes','logicalRawBytes','compressedRawBytes')}
    budget_lock=threading.Lock()
    def reserve(key,size):
        with budget_lock:
            if usage[key]+size>limits[key]:raise ValueError('Storage budget exceeded: '+key)
            usage[key]+=size
    class BudgetedLog:
        def __init__(self,target,key='compressedLogBytes'):self.target=target;self.key=key
        def write(self,data):
            reserve(self.key,len(data))
            return self.target.write(data)
        def flush(self):self.target.flush()
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    processes=[];threads=[];errors=[];logs=[None]*3;comparisons=[None]*2
    raw_receipts=[None]*3
    raw=[];branches=[];start=time.monotonic();success=False
    lock=threading.Lock()
    def task(fn):
        def invoke():
            try:fn()
            except BaseException as exc:
                with lock:errors.append(exc)
        thread=threading.Thread(target=invoke,daemon=True);threads.append(thread);thread.start()
    def drain(index,stream):
        digest=hashlib.sha256();size=0;counts=[];failure=None
        with stream,open(out/f'{index}.log.xz.partial','wb') as sink, \
                lzma.open(BudgetedLog(sink),'wb',preset=1) as target:
            while True:
                data=stream.readline(max_log_line_bytes+1)
                if not data:break
                if len(data)>max_log_line_bytes:raise ValueError('Log line budget exceeded')
                reserve('logicalLogBytes',len(data))
                digest.update(data);size+=len(data);target.write(data)
                line=data.decode('utf-8')
                failure=failure or diagnostic(line) or ('HDL diagnostic' if 'SORRY:' in line else None)
                counts.extend(map(int,re.findall(r'No\. of Data Rows\s*:\s*(\d+)',line)))
                if len(counts)>1:raise ValueError('Multiple producer completion counts')
        if failure:raise ValueError(f'Producer {index}: {failure}')
        if len(counts)!=1:raise ValueError('Missing producer completion count')
        logs[index]={'sha256':digest.hexdigest(),'bytes':size,'samples':counts[0]}
    def pump(index,source,destinations):
        digest=hashlib.sha256();size=0
        try:
            with source,open(out/f'{index}.raw.xz.partial','wb') as sink, \
                    lzma.open(BudgetedLog(sink,'compressedRawBytes'),'wb',preset=1) as archive:
                for data in iter(lambda:source.read(65536),b''):
                    reserve('logicalRawBytes',len(data))
                    digest.update(data);size+=len(data);archive.write(data)
                    for dest in destinations:dest.write(data);dest.flush()
            raw_receipts[index]={'sha256':digest.hexdigest(),'bytes':size,
                'compressedBytes':(out/f'{index}.raw.xz.partial').stat().st_size}
        finally:
            for dest in destinations:dest.close()
    def completed(indices):
        # Comparators reach here only after the raw pipes reach EOF. Log threads
        # must keep draining while we wait for completion, even with full pipes.
        while any(processes[i].poll() is None or logs[i] is None for i in indices):
            if errors:raise ValueError('Producer/log validation failed') from errors[0]
            if time.monotonic()-start>timeout:raise TimeoutError('Streaming capture timed out')
            time.sleep(.01)
        if any(processes[i].returncode!=0 for i in indices):raise ValueError('Raw producer failed')
        return [logs[i]['samples'] for i in indices]
    def compare(index,left,right):
        with left,right:
            comparisons[index]=compare_streams(left,right,expected_end,lambda:completed((index,index+1)))
    try:
        for index,build in enumerate(build_commands):
            read_fd,write_fd=os.pipe();reader=os.fdopen(read_fd,'rb');raw.append(reader)
            try:
                command,cwd=build(write_fd)
                process=subprocess.Popen(command,cwd=cwd,env=env,stdout=subprocess.PIPE,
                                         stderr=subprocess.STDOUT,pass_fds=(write_fd,),start_new_session=True)
                processes.append(process)
            finally:os.close(write_fd)
            task(lambda i=index,s=process.stdout:drain(i,s))
        for _ in range(4):
            r,w=os.pipe();branches.append((os.fdopen(r,'rb'),os.fdopen(w,'wb')))
        task(lambda:pump(0,raw[0],[branches[2][1]]))
        task(lambda:pump(1,raw[1],[branches[0][1],branches[1][1]]))
        task(lambda:pump(2,raw[2],[branches[3][1]]))
        task(lambda:compare(0,branches[2][0],branches[0][0]))
        task(lambda:compare(1,branches[1][0],branches[3][0]))
        while any(t.is_alive() for t in threads):
            if errors:raise ValueError('Streaming capture failed') from errors[0]
            if any(p.poll() not in (None,0) for p in processes):raise ValueError('Raw producer failed')
            if time.monotonic()-start>timeout:raise TimeoutError('Streaming capture timed out')
            time.sleep(.01)
        if errors:raise ValueError('Streaming capture failed') from errors[0]
        if not all(comparisons):raise ValueError('Missing paired comparisons')
        middle=[comparisons[0]['streams'][1],comparisons[1]['streams'][0]]
        if middle[0]!=middle[1]:raise ValueError('Middle stream fanout changed bytes')
        if any(p.wait()!=0 for p in processes):raise ValueError('Raw producer failed')
        consumed=[comparisons[0]['streams'][0],middle[0],comparisons[1]['streams'][1]]
        for i in range(3):
            if raw_receipts[i] is None or any(raw_receipts[i][k]!=consumed[i][k] for k in ('sha256','bytes')):
                raise ValueError('Archived bytes differ from compared bytes')
        for i in range(3):
            (out/f'{i}.log.xz.partial').replace(out/f'{i}.log.xz')
            (out/f'{i}.raw.xz.partial').replace(out/f'{i}.raw.xz')
        result={'completed':True,'comparisons':[c['comparison'] for c in comparisons],
                'streams':[comparisons[0]['streams'][0],middle[0],comparisons[1]['streams'][1]],
                'logs':logs,'storageLimits':limits,'storageUsage':dict(usage),'rawArchives':raw_receipts,'elapsedSeconds':time.monotonic()-start,'qualified':False,
                'boundary':'Three complete raw producers compared online and retained losslessly as compressed raw archives with explicit aggregate byte caps. Circuit/stimulus identity, serial coverage, numerical acceptance and independent model admission are separate.'}
        (out/'transport.json').write_text(json.dumps(result,indent=2)+'\n');success=True
        return result
    except BaseException as exc:
        (out/'failure.json').write_text(json.dumps({'completed':False,'storageLimits':limits,'storageUsage':dict(usage),'error':str(exc),'detail':str(errors[0]) if errors else None,'elapsedSeconds':time.monotonic()-start},indent=2)+'\n')
        raise
    finally:
        if not success:
            for p in processes:
                if p.poll() is not None:continue
                try:os.killpg(p.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                except PermissionError:p.kill()
        for p in processes:p.wait()
        for t in threads:t.join(timeout=5)
        for stream in raw+[s for pair in branches for s in pair]:
            if not stream.closed:stream.close()
