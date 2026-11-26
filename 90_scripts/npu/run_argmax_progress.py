"""One-program MNIST ARGMAX verification with external-write progress.

Reuses the existing unmodified model/reference/assembly/memory/comparison path.
Only the dedicated external-memory TB differs from the original snapshot.
"""
import argparse
import csv
import json
import subprocess
import time
import uuid
from pathlib import Path

import numpy as np
from model_loader import ROOT, sha
from scenario import Scenario
from run_verification import generate, run_sim, verify
from simulator import BIN, command, sources
from comparator import compare


def save_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')


def compile_progress():
    build=ROOT/'99_build'/('npu_argmax_progress_'+uuid.uuid4().hex[:8])
    build.mkdir(parents=True, exist_ok=False)
    files=sources()+[ROOT/'05_tb/npu'/n for n in
                     ('external_imem.sv','external_dmem.sv','tb_npu_argmax_progress.sv')]
    command([BIN/'xvlog.bat','--sv']+[p.as_posix() for p in files],build,'compile.log')
    command([BIN/'xelab.bat','tb_npu_argmax_progress','-s','npu_snapshot',
             '--timescale','1ns/1ps'],build,'elaborate.log')
    save_json(build/'source_hashes.json',{str(p.relative_to(ROOT)):sha(p) for p in files})
    print('BUILD',build,flush=True)
    return build


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--count',type=int,default=1000)
    p.add_argument('--timeout',type=int,default=3600)
    p.add_argument('--build')
    args=p.parse_args()
    scenario=Scenario(f'mnist_{args.count}_argmax_progress',list(range(args.count)),['argmax']).validate()
    build=Path(args.build).resolve() if args.build else compile_progress()
    started=time.perf_counter()
    run=generate(scenario)
    m=json.loads((run/'manifest.json').read_text())
    source=(run/'input/program.asm').read_text()
    code=[line.strip() for line in source.splitlines() if line.strip() and not line.lstrip().startswith('#')]
    if (m['sample_ids']!=list(range(args.count)) or m['record_stride']!=4 or
        m['dump']['words']!=args.count or code.count('END')!=1 or
        code.count('LOAD x1,x2,x3')!=6 or
        any(line.startswith(('STORE','TSTART','TSTOP')) for line in code)):
        raise ValueError('argmax-only single-program contract')
    save_json(run/'execution_plan.json',dict(invocation=__import__('sys').argv,
              imem_words=m['imem_words'],dmem_bytes=m['initial_words']*4,
              watchdog_cycles=200000+args.count*50000,timeout_seconds=args.timeout,
              accepted_starts=1,weight_load_sets=1,timer=False,waveform=False,
              progress_file='output/results.hex.progress',progress_interval=25))
    print('RUN',run,flush=True)
    sim_started=time.perf_counter()
    run_sim(run,build,args.timeout)
    sim_seconds=time.perf_counter()-sim_started
    comparison=compare(run)
    lines=(run/'output/results.hex').read_text().splitlines()
    actual=np.array([int(line,16) for line in lines],dtype=np.uint32)
    with np.load(run/'reference.npz',allow_pickle=False) as ref:
        expected,labels=ref['argmax'],ref['labels']
        if len(actual)!=args.count or np.any(actual>9):
            raise ValueError('RTL count/range')
        matched=actual==expected
        with (run/'predictions.csv').open('w',newline='',encoding='utf-8') as f:
            writer=csv.writer(f)
            writer.writerow(['sample_id','ground_truth','python_int8_argmax','rtl_argmax','int8_rtl_match'])
            writer.writerows((int(i),int(y),int(q),int(r),int(ok)) for i,y,q,r,ok in
                             zip(ref['sample_ids'],labels,expected,actual,matched))
        summary=dict(passed=bool(comparison['passed'] and matched.all()),
                     count=args.count,matches=int(matched.sum()),mismatches=int((~matched).sum()),
                     python_int8_correct=int(np.sum(expected==labels)),rtl_correct=int(np.sum(actual==labels)),
                     simulation_wall_seconds=sim_seconds,total_wall_seconds=time.perf_counter()-started,
                     run=str(run.relative_to(ROOT)),build=str(build.relative_to(ROOT)),
                     checkpoint_sha256=m['checkpoint_sha256'],dataset_sha256=m['dataset_sha256'],
                     output_sha256=sha(run/'output/results.hex'),predictions_sha256=sha(run/'predictions.csv'),
                     git_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip())
    progress=(run/'output/results.hex.progress').read_text().splitlines()
    if progress!=[f'completed={i} total={args.count}' for i in
                 list(range(0,args.count+1,25))+([] if args.count%25==0 else [args.count])]:
        raise ValueError('progress completion sequence')
    save_json(run/'verification_summary.json',summary)
    print('RESULT',json.dumps(summary),flush=True)
    if not summary['passed']:
        verify(Scenario('argmax_progress_diagnostic',comparison['mismatching_sample_ids'],
                        ['fc1','fc2','fc3','argmax']),timeout=args.timeout)
        raise AssertionError('RTL mismatch '+str(run))


if __name__=='__main__':
    main()
