"""Run three raw producers with bounded pipes and independently compressed logs.

Commands are built from an inherited raw-output descriptor. The middle stream is
fanned out to two concurrent comparators, so all three levels are executed once.
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


def run(build_commands, out, env, expected_end, timeout):
    if len(build_commands)!=3:raise ValueError('Need three producer commands')
    if not math.isfinite(timeout) or timeout<=0:raise ValueError('Need a finite positive timeout')
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    processes=[];threads=[];errors=[];logs=[None]*3;comparisons=[None]*2
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
        with stream,lzma.open(out/f'{index}.log.xz.partial','wb',preset=1) as target:
            for data in stream:
                digest.update(data);size+=len(data);target.write(data)
                line=data.decode('utf-8')
                failure=failure or diagnostic(line) or ('HDL diagnostic' if 'SORRY:' in line else None)
                counts.extend(map(int,re.findall(r'No\. of Data Rows\s*:\s*(\d+)',line)))
                if len(counts)>1:raise ValueError('Multiple producer completion counts')
        if failure:raise ValueError(f'Producer {index}: {failure}')
        if len(counts)!=1:raise ValueError('Missing producer completion count')
        logs[index]={'sha256':digest.hexdigest(),'bytes':size,'samples':counts[0]}
    def pump(source,destinations):
        try:
            with source:
                for data in iter(lambda:source.read(65536),b''):
                    for dest in destinations:dest.write(data);dest.flush()
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
        for _ in range(2):
            r,w=os.pipe();branches.append((os.fdopen(r,'rb'),os.fdopen(w,'wb')))
        task(lambda:pump(raw[1],[pair[1] for pair in branches]))
        task(lambda:compare(0,raw[0],branches[0][0]))
        task(lambda:compare(1,branches[1][0],raw[2]))
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
        for i in range(3):(out/f'{i}.log.xz.partial').replace(out/f'{i}.log.xz')
        result={'completed':True,'comparisons':[c['comparison'] for c in comparisons],
                'streams':[comparisons[0]['streams'][0],middle[0],comparisons[1]['streams'][1]],
                'logs':logs,'elapsedSeconds':time.monotonic()-start,'qualified':False,
                'boundary':'Three complete raw producers compared online; no raw spool. Circuit/stimulus identity, serial coverage, numerical acceptance and independent model admission are separate.'}
        (out/'transport.json').write_text(json.dumps(result,indent=2)+'\n');success=True
        return result
    except BaseException as exc:
        (out/'failure.json').write_text(json.dumps({'completed':False,'error':str(exc),'detail':str(errors[0]) if errors else None,'elapsedSeconds':time.monotonic()-start},indent=2)+'\n')
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
