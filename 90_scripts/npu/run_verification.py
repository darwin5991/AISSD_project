"""Generate/assemble/simulate/compare/verify scenario CLI, local offline only."""
import argparse,json,uuid,subprocess,sys
from pathlib import Path
from datetime import datetime
import numpy as np
from scenario import Scenario
from model_loader import ROOT,load,sha
from reference import generate as reference
from memory_builder import build
from assembly_generator import generate as assembly
from assembler import assemble,write_hex
from simulator import compile_sim,simulate
from comparator import compare

def generate(s):
    s.validate();run=ROOT/'07_runs/npu'/f'{s.name}_{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:6]}'
    for sub in ('input','output','logs'):(run/sub).mkdir(parents=True)
    s.save(run/'scenario.json');data,hashes=load(s)
    np.savez_compressed(run/'quantized.npz',**data)
    np.savez_compressed(run/'reference.npz',**reference(s,data))
    words,m=build(s,data);source=assembly(s,m);program=assemble(source)
    (run/'input/program.asm').write_text(source);write_hex(run/'input/imem.hex',program);write_hex(run/'input/dmem.hex',words)
    m.update(hashes);m['imem_words']=len(program);m['scenario']=json.loads((run/'scenario.json').read_text())
    m['files_sha256']={str(p.relative_to(run)).replace('\\','/'):sha(p) for p in [run/'reference.npz',run/'quantized.npz',run/'scenario.json',run/'input/program.asm',run/'input/imem.hex',run/'input/dmem.hex']}
    m['git_head']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    m['toolchain_sha256']={str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in sorted(Path(__file__).parent.glob('*.py'))}
    m['input_quantized_sha256']=__import__('hashlib').sha256(data['input'].tobytes()).hexdigest()
    (run/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
    print('GENERATED',run,flush=True);return run

def run_sim(run,build_dir=None,timeout=1200):
    run=Path(run).resolve();m=json.loads((run/'manifest.json').read_text())
    if build_dir is None:build_dir=compile_sim(ROOT/'99_build'/('npu_model_'+uuid.uuid4().hex[:8]))
    build_dir=Path(build_dir).resolve()
    hashes=json.loads((build_dir/'source_hashes.json').read_text())
    for name,digest in hashes.items():
        if sha(ROOT/name)!=digest:raise ValueError('stale compiled source '+name)
    (run/'logs/simulator_sources.json').write_text(json.dumps(dict(build=str(build_dir),sources=hashes),indent=2))
    # Generous cycle watchdog, not an overall performance benchmark.
    simulate(build_dir,run,m['imem_words'],m['initial_words'],m['dump']['base'],m['dump']['words'],limit=200000+len(m['sample_ids'])*50000,timeout=timeout)
    return build_dir

def verify(s,build_dir=None,timeout=1200,diagnostic=True):
    run=generate(s);b=run_sim(run,build_dir,timeout);report=compare(run)
    print(s.name,'PASS' if report['passed'] else 'FAIL',json.dumps(report['fields']),flush=True)
    if not report['passed']:
        if diagnostic:
            diag=Scenario(s.name+'_diagnostic',report['mismatching_sample_ids'],[o['id'] for o in s.ops],s.ops)
            verify(diag,b,timeout,False)
        raise AssertionError('comparison failed '+str(run))
    return run,b

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['generate','simulate','compare','verify']);p.add_argument('--count',type=int,default=1)
    p.add_argument('--ids',help='ordered comma-separated sample IDs');p.add_argument('--save',default='fc1,fc2,fc3,argmax');p.add_argument('--scenario');p.add_argument('--run');p.add_argument('--build');p.add_argument('--timeout',type=int,default=1200)
    a=p.parse_args();s=Scenario.load(a.scenario) if a.scenario else Scenario(f'mnist_{a.count}_{a.save.replace(",","_")}',[int(x) for x in a.ids.split(',')] if a.ids else list(range(a.count)),a.save.split(','))
    if a.action=='generate':generate(s)
    elif a.action=='simulate':run_sim(a.run,a.build,a.timeout)
    elif a.action=='compare':
        r=compare(a.run);print(json.dumps(r,indent=2));sys.exit(0 if r['passed'] else 1)
    else:verify(s,a.build,a.timeout)
if __name__=='__main__':main()
