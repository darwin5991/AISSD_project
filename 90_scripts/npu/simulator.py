"""Owned XSim subprocesses, bounded timeouts, unique build directories."""
import os,subprocess,json,hashlib
from pathlib import Path
from model_loader import ROOT
BIN=Path('D:/AMDDesignTools/2025.2/Vivado/bin')
def sources(full=True):
    files=[ROOT/'04_rtl/isa/npu_isa_pkg.sv']
    files+=sorted(p for p in (ROOT/'04_rtl/isa').glob('*.sv') if p.name!='npu_isa_pkg.sv')
    if full=='dma':
        files += [ROOT/'04_rtl/controller/dma_controller.sv']
        files += [ROOT/'04_rtl/memory'/n for n in ('single_port_bram.sv','npu_memory_wrapper.sv','dmem_port_mux.sv')]
        files += [ROOT/'05_tb/npu/dma_harness.sv']
    elif full:
        for folder in ('common','mac_array','accumulator_postprocess'): files+=sorted((ROOT/'04_rtl'/folder).glob('*.sv'))
        files += [ROOT/'04_rtl/controller'/n for n in ('unpack_int8x4.sv','argmax_unit.sv','argmax_tracker.sv','argmax_update.sv','byte_select4.sv','signed_compare8.sv','dma_controller.sv','gemm_controller.sv','argmax_engine.sv')]
        files += [ROOT/'04_rtl/memory'/n for n in ('single_port_bram.sv','npu_memory_wrapper.sv','dmem_port_mux.sv')]
        files += [ROOT/'04_rtl/npu_top.sv']
    return files
def environment(build):
    env=os.environ.copy(); env['XILINX_LOCAL_USER_DATA']='no'
    for key in ('APPDATA','TEMP','TMP'):
        p=build/key.lower();p.mkdir(parents=True,exist_ok=True);env[key]=p.as_posix()
    return env
def command(args,build,log,timeout=600):
    # .bat tools require Windows command processing; list2cmdline quotes local paths.
    with (build/log).open('w') as f:
        cmd=' '.join(('"'+str(a)+'"') if '=' in str(a) else subprocess.list2cmdline([str(a)]) for a in args)
        result=subprocess.run(cmd,cwd=build,env=environment(build),stdout=f,stderr=subprocess.STDOUT,timeout=timeout)
    text=(build/log).read_text(errors='replace')
    if result.returncode or any(x in text for x in ('ERROR:','FATAL_ERROR:','Fatal:','FATAL:')): raise RuntimeError(f'tool failed {build/log}')
    return text
def compile_sim(build,full=True):
    build=Path(build).resolve();build.mkdir(parents=True,exist_ok=False)
    files=sources(full)+[ROOT/'05_tb/npu'/n for n in ('external_imem.sv','external_dmem.sv','tb_npu_top.sv')]
    if not full:files+=[ROOT/'05_tb/npu/scalar_harness.sv']
    args=[BIN/'xvlog.bat','--sv']+([] if full else ['-d','SCALAR_ONLY'])+[p.as_posix() for p in files]
    command(args,build,'compile.log')
    command([BIN/'xelab.bat','tb_npu_top','-s','npu_snapshot','--timescale','1ns/1ps'],build,'elaborate.log')
    (build/'source_hashes.json').write_text(json.dumps({str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},indent=2))
    return build
def simulate(build,run,imem_words,dmem_words,dump_base,dump_words,limit=2000000,timeout=600):
    build=Path(build).resolve();run=Path(run).resolve()
    args=[BIN/'xsim.bat','npu_snapshot','-runall','-onerror','quit']
    values=dict(IMEM=(run/'input/imem.hex').as_posix(),DMEM=(run/'input/dmem.hex').as_posix(),OUTPUT=(run/'output/results.hex').as_posix(),IMEM_WORDS=imem_words,DMEM_WORDS=dmem_words,DUMP_BASE=dump_base,DUMP_WORDS=dump_words,LIMIT=limit)
    for k,v in values.items():args+=['-testplusarg',f'{k}={v}']
    log='simulate_'+run.name+'.log';text=command(args,build,log,timeout)
    (run/'logs/xsim.log').write_text(text)
    if 'NPU_EXTERNAL_PASS' not in text:raise RuntimeError('no TB pass '+str(build/log))
