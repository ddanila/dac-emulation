#!/usr/bin/env python3
"""Demonstrate TV80's non-M1 operand sampling edge with an executed instruction."""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

from cpu_read_phase_candidate import generate, generate_core

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / 'build/keyboard-controller-analog/cpu-read-phase')
    parser.add_argument('--profile', choices=('tv80', 'falling-candidate', 'falling-indexed-candidate'), default='tv80')
    parser.add_argument('--read-kind', choices=('memory', 'io', 'indexed-opcode'), default='memory')
    parser.add_argument('--wait', action='store_true', help='Insert a WAIT interval in the operand read')
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    tv80 = ROOT / 'third_party/cpu/tv80'
    source = json.loads((tv80 / 'SOURCE.json').read_text())
    for name, digest in source['files'].items():
        if sha(tv80 / name) != digest:
            raise ValueError('TV80 source differs: ' + name)
    indexed = args.read_kind == 'indexed-opcode'
    fixture_name = 'cpu_indexed_phase_probe.v' if indexed else 'cpu_read_phase_probe.v'
    report = {'passed': False, 'qualified': False, 'scope': __doc__, 'tv80': source,
              'fixtureSha256': sha(HERE / fixture_name),
              'runnerSha256': sha(Path(__file__)),
              'boundary': 'Isolated read-phase experiments. Generated dual-edge models are not synthesis or U880 qualifications; interrupt, bus-grant, reset and full S600 behavior remain unqualified.'}
    report.update(profile=args.profile, insertedWait=args.wait, readKind=args.read_kind)
    bench = (HERE / fixture_name).read_text()
    expected = '12' if args.profile == 'tv80' else '34'
    if indexed:
        expected = '01' if args.profile == 'falling-indexed-candidate' else '00'
    sources = sorted(tv80.glob('*.v'))
    if args.profile != 'tv80':
        wrapper = out / 'tv80n_candidate.v'
        wrapper.write_text(generate((tv80 / 'tv80n.v').read_text()))
        sources = [p for p in sources if p.name != 'tv80n.v'] + [wrapper]
        report['candidateGeneratorSha256'] = sha(HERE / 'cpu_read_phase_candidate.py')
        report['candidateWrapperSha256'] = sha(wrapper)
        if not indexed:
            bench = bench.replace("dout!==8'h12", "dout!==8'h34")
    if args.profile == 'falling-indexed-candidate':
        core = out / 'tv80_core_candidate.v'
        core.write_text(generate_core((tv80 / 'tv80_core.v').read_text()))
        sources = [p for p in sources if p.name != 'tv80_core.v'] + [core]
        report['candidateCoreSha256'] = sha(core)
        if indexed:
            bench = bench.replace("dout!==8'h00", "dout!==8'h01")
            bench = bench.replace("Expected current core to execute earlier RES opcode",
                                  "Expected indexed candidate to execute later SET opcode")
    if args.read_kind == 'io':
        bench = bench.replace("assign di=address==0 ? 8'h3e : address==1 ? (late ? 8'h34 : 8'h12) :",
                              "assign di=!iorq_n ? (late ? 8'h34 : 8'h12) : address==0 ? 8'hdb : address==1 ? 8'h80 :")
        bench = bench.replace('!mreq_n && !rd_n && address==1', '!iorq_n && !rd_n')
        # Select the final accepted read, rather than an intermediate T3
        # repetition caused by IOWait. This affects fixture stimulus only.
        bench = bench.replace('reset_n && cpu.tstate[2]',
                              'reset_n && cpu.i_tv80_core.Auto_Wait_t1 && cpu.tstate[2]')
    if args.wait:
        bench = bench.replace('reg clk=0, reset_n=0, late=0;', 'reg clk=0, reset_n=0, late=0, wait_n=1, waited=0;')
        bench = bench.replace(".wait_n(1'b1)", '.wait_n(wait_n)')
        bench = bench.replace('reset_n && cpu.', 'reset_n && cpu.wait_n && cpu.', 1)
        bench = bench.replace(' always #500 clk=~clk;', """ always @(negedge mreq_n) if(reset_n && address==1 && !waited) begin
   waited=1;wait_n=0;$display("WAIT_ASSERT %0t",$time);
   #2000;wait_n=1;$display("WAIT_RELEASE %0t",$time);
 end
 always #500 clk=~clk;""")
    if args.wait and args.read_kind == 'io':
        bench = bench.replace('negedge mreq_n) if(reset_n && address==1',
                              'negedge iorq_n) if(reset_n && !rd_n')
        bench = bench.replace('#2000;wait_n=1', '#4000;wait_n=1')
    if args.wait and indexed:
        bench = bench.replace('negedge mreq_n) if(reset_n && address==1',
                              'negedge mreq_n) if(reset_n && address==7')
    fixture = out / 'probe.v'
    fixture.write_text(bench)
    report['executedFixtureSha256'] = sha(fixture)
    try:
        subprocess.run(['iverilog', '-g2012', '-s', 'probe', '-o', str(out / 'probe.vvp'),
                        *map(str, sources), str(fixture)], check=True)
        run = subprocess.run(['vvp', str(out / 'probe.vvp')], cwd=out, capture_output=True,
                             text=True, timeout=30)
        (out / 'simulation.log').write_text(run.stdout + run.stderr)
        run.check_returncode()
        def event(name, pattern):
            values = re.findall('^' + name + ' ' + pattern + '$', run.stdout, re.M)
            if len(values) != 1:
                raise ValueError('Missing or ambiguous event: ' + name)
            return values[0]
        rise, early = event('OPERAND_RISE', r'(\d+) ([0-9a-f]{2})')
        change = event('OPERAND_CHANGE', r'(\d+)')
        fall, late, captured = event('OPERAND_FALL', r'(\d+) ([0-9a-f]{2}) ([0-9a-f]{2})')
        written, address, output = event('OUTPUT', r'(\d+) ([0-9a-f]{4}) ([0-9a-f]{2})')
        if not (int(rise) < int(change) < int(fall) < int(written)):
            raise ValueError('Invalid phase event order')
        early_expected, late_expected = ('86', 'c6') if indexed else ('12', '34')
        if (early, late, address, output) != (early_expected, late_expected, expected + '80', expected):
            raise ValueError('Unexpected instruction-level sampling behavior')
        if args.profile == 'tv80' and captured != early_expected:
            raise ValueError('Legacy rising-edge input register differs')
        if indexed:
            memory_time, memory_address, memory_value = event('MEMORY_WRITE', r'(\d+) ([0-9a-f]{4}) ([0-9a-f]{2})')
            if (memory_address, memory_value) != ('0010', expected) or not (
                    int(fall) < int(memory_time) < int(written)):
                raise ValueError('Indexed instruction memory effect differs')
        report['laterValueUsed'] = (args.profile == 'falling-indexed-candidate'
                                    if indexed else args.profile != 'tv80')
        if args.wait:
            asserted = event('WAIT_ASSERT', r'(\d+)')
            released = event('WAIT_RELEASE', r'(\d+)')
            wait_ps = 4000000 if args.read_kind == 'io' else 2000000
            baseline_read_ps = 29500000 if indexed else (12500000 if args.read_kind == 'io' else 8500000)
            if (int(released) - int(asserted) != wait_ps or int(released) >= int(rise)
                    or int(rise) <= baseline_read_ps):
                raise ValueError('WAIT did not postpone the accepted operand beyond its unstretched fixture time')
            report['waitReadDelayNs'] = (int(rise) - baseline_read_ps) / 1000
        setup_ns = (int(fall) - int(change)) / 1000
        if setup_ns < 60 or 'READ_PHASE_DIAGNOSTIC_PASS' not in run.stdout:
            raise ValueError('Insufficient falling-edge setup or incomplete fixture')
        report.update(passed=True, risingEdgeValue=early, fallingEdgeValue=late,
                      registerBeforeFallingEdge=captured, instructionOutput=output, fallingEdgeSetupNs=setup_ns,
                      reference={'url': 'https://www.tiffe.de/robotron/Bausteinuebersicht/U880D-CPU.pdf',
                                 'sha256': 'a3266f1cea4d24c0c91ca2941f6b40762f24a2934e6cf41dccd5fb52f80e75be',
                                 'page': 'Printed 58, PDF 59', 'nonM1SetupNs': 60},
                      files={name: sha(out / name) for name in ('probe.vvp', 'simulation.log')})
        report['iverilog'] = subprocess.run(['iverilog', '-V'], capture_output=True,
                                            text=True, check=True).stdout.splitlines()[0]
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
