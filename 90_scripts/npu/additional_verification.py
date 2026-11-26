"""User-requested supplemental runs; existing RTL, reference and runners unchanged.

performance: real five-image all-layer inference + separate five bank-load trials.
full: existing 10000-image verify CLI, followed by per-image FP32/INT8/RTL audit.
All raw runs remain ignored; compact evidence is copied to --evidence.
"""
import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

import numpy as np
import torch
from assembler import assemble, write_hex
from assembly_generator import ASSEMBLY_OPS
from comparator import compare
from memory_builder import BANKS, build
from model_loader import ROOT, load, sha, LayerViewer
from reference import generate as reference
from run_verification import run_sim
from scenario import Scenario

BANK_NAMES = ('W0', 'W1', 'W2', 'W3', 'Bias')
IMAGE_NAMES = ('input_load', 'fc1_gemm', 'fc1_store', 'fc2_gemm',
               'fc2_store', 'fc3_gemm', 'fc3_store')
ANCHOR = '7a8d7fc31ac6e1f293ae924fbf65f0555e688242'


def save_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def write_csv(path, header, rows):
    with Path(path).open('w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)


def exact(condition, message):
    if not condition:
        raise AssertionError(message)


def read_words(path, count):
    lines = Path(path).read_text().splitlines()
    exact(len(lines) == count and all(re.fullmatch('[0-9a-fA-F]{8}', s) for s in lines),
          'external dump count/format/X/Z: ' + str(path))
    return np.array([int(s, 16) for s in lines], dtype='<u4')


def theory(s, m):
    # Derived before simulation from transfer sizes and controller schedule.
    bank = [m['regions'][b]['bytes'] // 4 + 2 for b in BANK_NAMES]
    image = [m['regions']['images']['bytes'] // len(s.sample_ids) // 4 + 2]
    layers = []
    for o in s.ops:
        if o['op'] != 'gemm':
            continue
        k, n = o['k'], o['n']
        q, g = k // 4, (n + 3) // 4
        cycles = g * q + g + 6
        image += [cycles, m['fields'][o['id']]['bytes'] // 4 + 2]
        layers.append(dict(layer=o['id'], k=k, n=n, q=q, g=g,
                           useful_multiplies=k*n, padded_multiplies=k*g*4,
                           useful_ideal_cycles=k*n/16, padded_ideal_cycles=g*q,
                           expected_cycles=cycles, bubble_cycles=g-1,
                           prep_cycles=1, drain_cycles=6))
    exact(bank == [29282]*4 + [165], 'independent bank theory differs from request')
    exact(image == [198, 25222, 130, 4134, 34, 105, 5], 'independent image theory differs')
    return dict(banks=bank, image=image, layers=layers)


def measured(command, pointer, offset=0):
    return ['TSTART', command, 'TSTOP', 'CSRR x4,PERF_COUNT', f'SW x4,{offset}({pointer})']


def bank_loads(m, pointer):
    lines = []
    for i, b in enumerate(BANK_NAMES):
        r = m['regions'][b]
        lines += [f'LI x1,{r["base"]}', f'LI x2,{BANKS[b]}', f'LI x3,{r["bytes"]}']
        lines += measured('LOAD x1,x2,x3', pointer, 4*i)
    return lines


def prepare_performance(s, data, hashes, helper=False):
    run = ROOT/'07_runs/npu'/f'{s.name}_{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:6]}'
    for sub in ('input', 'output', 'logs'):
        (run/sub).mkdir(parents=True)
    s.save(run/'scenario.json')
    np.savez_compressed(run/'reference.npz', **reference(s, data))
    np.savez_compressed(run/'quantized.npz', **data)
    words, m = build(s, data)
    expected = theory(s, m)
    result = m['regions']['results']
    if helper:
        # Replace this NEW helper's unused inference slots before sealing inputs.
        words = np.concatenate([words[:(result['base']-0x10000000)//4],
                                np.full(25, 0xa5a5a5a5, dtype='<u4')])
        result.update(bytes=100, words=25)
        m.update(fields={}, record_stride=20, dump=dict(base=result['base'], words=25, file='output/results.hex'))
        lines = [f'LI x6,{result["base"]}', 'LI x7,5', 'load_loop:']
        lines += bank_loads(m, 'x6')
        lines += ['ADDI x6,x6,20', 'ADDI x7,x7,-1', 'BNE x7,x0,load_loop', 'END']
        source = '\n'.join(lines)+'\n'
        timer = dict(base=result['base'], words=25, stride=20)
    else:
        # Append disjoint dense timers; x1 is scratch after each measured op.
        timer_base = 0x10000000 + words.nbytes
        timer = dict(base=timer_base, words=40, stride=28)
        source = compact_performance_program(s, m, timer_base)
        words = np.concatenate([words, np.full(40, 0xa5a5a5a5, dtype='<u4')])
    program = assemble(source)
    (run/'input/program.asm').write_text(source)
    write_hex(run/'input/imem.hex', program)
    write_hex(run/'input/dmem.hex', words)
    m.update(hashes, initial_words=len(words), imem_words=len(program),
             scenario=json.loads((run/'scenario.json').read_text()),
             measurement=dict(helper=helper, timer=timer, expected=expected),
             git_head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
             invocation=sys.argv)
    m['files_sha256'] = {str(p.relative_to(run)).replace('\\', '/'): sha(p) for p in
                         [run/'reference.npz', run/'quantized.npz', run/'scenario.json',
                          run/'input/program.asm', run/'input/imem.hex', run/'input/dmem.hex']}
    m['toolchain_sha256'] = {str(p.relative_to(ROOT)).replace('\\', '/'): sha(p)
                             for p in sorted(Path(__file__).parent.glob('*.py'))}
    save_json(run/'manifest.json', m)
    print('GENERATED', run, flush=True)
    return run, m


def compact_performance_program(s, m, timer_base):
    """x4 snapshot, x1 destination scratch after op; pointers x5..7 preserved."""
    lines = [f'LI x6,{timer_base}'] + bank_loads(m, 'x6')
    lines += [f'LI x5,{m["regions"]["images"]["base"]}',
              f'LI x6,{m["regions"]["results"]["base"]}', 'LI x7,5', 'image_loop:']
    def timed(command, slot):
        # Absolute timer slots keep all persistent image/result pointers intact.
        return ['TSTART', command, 'TSTOP', 'CSRR x4,PERF_COUNT',
                f'LI x1,{timer_base+20+slot*4}', 'SW x4,0(x1)']
    # Explicit five bodies preserve a single reset/start and bank load set.
    lines = lines[:-2]  # remove loop count and unused label
    for row in range(5):
        lines += [f'# MNIST test ID {row}', 'ADDI x1,x5,0', f'LI x2,{BANKS["A"]}', 'LI x3,784']
        lines += timed('LOAD x1,x2,x3', row*7)
        index = row*7+1
        for o in s.ops:
            code = ASSEMBLY_OPS[o['op']](o, m)
            f = m['fields'][o['id']]
            if o['op'] == 'gemm':
                lines += code[:-1] + timed(code[-1], index)
                index += 1
                lines += [f'LI x1,{BANKS[o["dst"]]}', f'ADDI x2,x6,{f["offset"]}', f'LI x3,{f["bytes"]}']
                lines += timed('STORE x1,x2,x3', index)
                index += 1
            else:
                lines += code + [f'SW x1,{f["offset"]}(x6)']
        lines += ['ADDI x5,x5,784', f'ADDI x6,x6,{m["record_stride"]}']
    return '\n'.join(lines+['END'])+'\n'


def simulate_performance(run, m, build_dir, timeout):
    from simulator import simulate
    build_dir = Path(build_dir).resolve()
    hashes = json.loads((build_dir/'source_hashes.json').read_text())
    for name, digest in hashes.items():
        exact(sha(ROOT/name) == digest, 'stale snapshot '+name)
    save_json(run/'logs/simulator_sources.json', dict(build=str(build_dir), sources=hashes))
    dump = m['dump']
    count = dump['words'] + (0 if m['measurement']['helper'] else 40)
    start = time.perf_counter()
    simulate(build_dir, run, m['imem_words'], m['initial_words'], dump['base'], count,
             limit=2000000, timeout=timeout)
    elapsed = time.perf_counter()-start
    raw = read_words(run/'output/results.hex', count)
    shutil.copyfile(run/'output/results.hex', run/'output/combined_raw.hex')
    if not m['measurement']['helper']:
        write_hex(run/'output/results.hex', raw[:dump['words']])
        write_hex(run/'output/timers.hex', raw[dump['words']:])
    save_json(run/'logs/execution.json', dict(wall_seconds=elapsed, limit_cycles=2000000,
              combined_dump_words=count, combined_dump_sha256=sha(run/'output/combined_raw.hex')))
    return raw, elapsed


def performance(args):
    s = Scenario('performance_5', list(range(5)), ['fc1', 'fc2', 'fc3', 'argmax']).validate()
    data, hashes = load(s)
    old_manifest = json.loads((ROOT/'07_runs/npu/v5_20261125_024215_8631ca/manifest.json').read_text())
    exact(hashes['dataset_sha256'] == old_manifest['dataset_sha256'], 'MNIST dataset hash changed')
    run, m = prepare_performance(s, data, hashes)
    raw, elapsed = simulate_performance(run, m, args.build, args.timeout)
    comparison = compare(run)
    exact(comparison['passed'], 'instrumented layer comparison failed: '+str(run))
    old = ROOT/'07_runs/npu/v5_20261125_024215_8631ca'
    exact(sha(run/'output/results.hex') == sha(old/'output/results.hex'), 'instrumented output differs from original V5')
    with np.load(old/'reference.npz', allow_pickle=False) as old_ref, np.load(run/'reference.npz', allow_pickle=False) as new_ref:
        for name in new_ref.files:
            np.testing.assert_array_equal(new_ref[name], old_ref[name])
    timers = raw[m['dump']['words']:]
    initial, images = timers[:5], timers[5:].reshape(5, 7)
    exact(np.array_equal(initial, m['measurement']['expected']['banks']), 'initial LOAD cycles')
    exact(np.all(images == m['measurement']['expected']['image']), 'per-image cycles')
    write_csv(run/'performance_per_image.csv', ['sample_id']+[n+'_cycles' for n in IMAGE_NAMES],
              [[i]+[int(v) for v in row] for i, row in enumerate(images)])
    helper_s = Scenario('performance_weight_repeat_5', list(range(5)), s.save_outputs).validate()
    helper, hm = prepare_performance(helper_s, data, hashes, helper=True)
    repeated_raw, helper_elapsed = simulate_performance(helper, hm, args.build, args.timeout)
    repeated = repeated_raw.reshape(5, 5)
    passed = bool(np.all(repeated == hm['measurement']['expected']['banks']))
    save_json(helper/'comparison.json', dict(passed=passed, expected=hm['measurement']['expected']['banks'], actual=repeated.tolist()))
    exact(passed, 'repeated LOAD cycles')
    write_csv(helper/'weight_load_per_run.csv', ['run_id','w0_load_cycles','w1_load_cycles','w2_load_cycles','w3_load_cycles','bias_load_cycles'],
              [[i+1]+[int(v) for v in row] for i, row in enumerate(repeated)])
    result = dict(passed=True, inference_run=str(run.relative_to(ROOT)), helper_run=str(helper.relative_to(ROOT)),
                  inference_wall_seconds=elapsed, helper_wall_seconds=helper_elapsed,
                  initial_load_cycles=initial.tolist(), image_cycles=images.tolist(), repeated_load_cycles=repeated.tolist(),
                  expected=m['measurement']['expected'], comparison=comparison, original_v5_output_identical=True)
    for i, layer in enumerate(result['expected']['layers']):
        actual = int(images[0, 1+2*i])
        layer.update(measured_cycles=actual, useful_utilization=layer['useful_multiplies']/(16*actual),
                     padding_efficiency=layer['useful_multiplies']/layer['padded_multiplies'],
                     schedule_efficiency=layer['padded_ideal_cycles']/actual,
                     overhead_cycles=actual-layer['padded_ideal_cycles'])
    for source in (run/'performance_per_image.csv', helper/'weight_load_per_run.csv'):
        shutil.copyfile(source, args.evidence/source.name)
    save_json(run/'performance_analysis.json', result)
    save_json(args.evidence/'performance_analysis.json', result)
    print('TEST1 PASS', json.dumps(result), flush=True)


def fp32_predictions(run):
    """Existing evaluate_test FP32 CPU path, retaining per-image predictions."""
    viewer = LayerViewer()
    predictions, labels = [], []
    start = time.perf_counter()
    with torch.inference_mode():
        for first in range(0, 10000, 512):
            samples = [viewer._read_sample(i) for i in range(first, min(first+512, 10000))]
            pixels = torch.cat([x for x, _ in samples])
            x = (pixels/255.0-viewer.mean)/viewer.std
            predictions.extend(viewer.model(x).argmax(1).tolist())
            labels.extend(y for _, y in samples)
    np.savez_compressed(run/'fp32_predictions.npz', sample_ids=np.arange(10000),
                        labels=np.array(labels), argmax=np.array(predictions, dtype=np.uint32))
    result = dict(count=10000, correct=int(np.sum(np.array(predictions)==labels)), device='cpu',
                  dtype='float32', wall_seconds=time.perf_counter()-start,
                  checkpoint_sha256=sha(ROOT/'03_model/checkpoints/MLP_MNIST_GPU_FINAL_BEST.pth'),
                  output_sha256=sha(run/'fp32_predictions.npz'))
    save_json(run/'fp32_summary.json', result)
    return result


def full(args):
    exact((args.evidence/'performance_analysis.json').is_file() and
          json.loads((args.evidence/'performance_analysis.json').read_text())['passed'], 'Test1 required first')
    # Generate once, evaluate FP32, then execute the unchanged existing runner.
    from run_verification import generate
    start = time.perf_counter()
    run = generate(Scenario('mnist_10000_argmax', list(range(10000)), ['argmax']))
    fp_summary = fp32_predictions(run)
    m = json.loads((run/'manifest.json').read_text())
    source = (run/'input/program.asm').read_text()
    exact(source.count('LOAD x1,x2,x3') == 6 and source.count('END') >= 1 and
          'TSTART' not in source and 'TSTOP' not in source and 'STORE ' not in source,
          'bulk assembly mode')
    exact(m['sample_ids'] == list(range(10000)) and m['dump']['words'] == 10000 and
          m['record_stride'] == 4 and m['initial_words']*4 == 8349132, 'bulk capacity/layout')
    save_json(run/'pre_simulation.json', dict(imem_words=m['imem_words'], imem_capacity_words=16384,
              dmem_bytes=m['initial_words']*4, dmem_capacity_bytes=16777216,
              watchdog_cycles=500200000, engine_cycles_lower_bound=117293+10000*(29461+198),
              expected_total_cycles_upper_bound=200000+10000*50000, timeout_seconds=args.timeout,
              reset_start_count=1, weight_load_sets=1, timer=False, waveform=False,
              fp32=fp_summary))
    print('FULL_RUN', run, 'FP32', fp_summary, flush=True)
    sim_start = time.perf_counter()
    run_sim(run, args.build, args.timeout)
    wall = time.perf_counter()-sim_start
    comparison = compare(run)
    save_json(run/'execution.json', dict(simulation_wall_seconds=wall, total_wall_seconds=time.perf_counter()-start))
    if not comparison['passed']:
        from run_verification import verify
        verify(Scenario('mnist_10000_diagnostic', comparison['mismatching_sample_ids'],
                        ['fc1','fc2','fc3','argmax']), args.build, args.timeout)
    analyze_full(run, args.evidence)


def analyze_full(run, evidence):
    m = json.loads((run/'manifest.json').read_text())
    comparison = compare(run)
    rtl = read_words(run/'output/results.hex', 10000)
    with np.load(run/'reference.npz', allow_pickle=False) as ref, np.load(run/'fp32_predictions.npz', allow_pickle=False) as fp:
        ids, labels, integer = ref['sample_ids'], ref['labels'], ref['argmax']
        floating = fp['argmax']
        exact(np.array_equal(ids, np.arange(10000)) and np.array_equal(fp['sample_ids'], ids) and
              np.array_equal(fp['labels'], labels), 'sample IDs/label order')
        exact(len(integer)==len(floating)==len(rtl)==10000 and np.all(rtl <= 9), 'count/ARGMAX range')
        matches = integer == rtl
        rows = [[int(i),int(y),int(f),int(q),int(r),int(ok)] for i,y,f,q,r,ok in zip(ids,labels,floating,integer,rtl,matches)]
        write_csv(run/'mnist_10000_predictions.csv', ['sample_id','ground_truth','python_fp32_argmax','python_int8_argmax','rtl_argmax','int8_rtl_match'], rows)
        result = dict(passed=bool(comparison['passed'] and matches.all()), run=str(run.relative_to(ROOT)),
                      total=10000, matches=int(matches.sum()), mismatches=int((~matches).sum()),
                      mismatching_samples=[rows[i] for i in np.flatnonzero(~matches)],
                      fp32_correct=int(np.sum(floating==labels)), int8_correct=int(np.sum(integer==labels)),
                      rtl_correct=int(np.sum(rtl==labels)), fp32_int8_differences=int(np.sum(floating!=integer)),
                      output_range=[int(rtl.min()),int(rtl.max())], missing=0, duplicate_writes=0,
                      write_count_evidence='external_dmem.dump_results requires writes[idx]==1 for every word before NPU_EXTERNAL_PASS',
                      execution=json.loads((run/'execution.json').read_text()),
                      checkpoint_sha256=m['checkpoint_sha256'], dataset_sha256=m['dataset_sha256'],
                      files_sha256={name:sha(run/name) for name in ['manifest.json','fp32_predictions.npz','output/results.hex','comparison.json','mnist_10000_predictions.csv']})
    exact('NPU_EXTERNAL_PASS' in (run/'logs/xsim.log').read_text(), 'external write count/completion evidence')
    save_json(run/'full_analysis.json', result)
    save_json(evidence/'full_analysis.json', result)
    shutil.copyfile(run/'mnist_10000_predictions.csv', evidence/'mnist_10000_predictions.csv')
    print('TEST2', 'PASS' if result['passed'] else 'FAIL', json.dumps(result), flush=True)
    exact(result['passed'], 'full RTL comparison failed')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['performance', 'full', 'analyze-full'])
    p.add_argument('--build', default='99_build/npu_model_8cf69d59')
    p.add_argument('--timeout', type=int, default=21600)
    p.add_argument('--run')
    p.add_argument('--evidence', type=Path, default=ROOT/'00_docs/programmable_npu/evidence/additional_20261126')
    args = p.parse_args()
    args.evidence.mkdir(parents=True, exist_ok=True)
    if args.action == 'performance':
        performance(args)
    elif args.action == 'full':
        full(args)
    else:
        analyze_full(Path(args.run), args.evidence)


if __name__ == '__main__':
    main()
