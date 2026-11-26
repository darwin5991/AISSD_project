"""Bounded native Vivado OOC stages, no external network/board configuration."""
import argparse,json,uuid,subprocess
from pathlib import Path
from simulator import ROOT,BIN,sources,command
from model_loader import sha
def main():
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['synth','implement','power']);p.add_argument('--run');p.add_argument('--timeout',type=int,default=1800);p.add_argument('--functional-runs',nargs='*')
    a=p.parse_args();out=Path(a.run).resolve() if a.run else ROOT/'99_build'/('npu_ooc_'+uuid.uuid4().hex[:10])
    if a.stage=='synth':
        out.mkdir(parents=True,exist_ok=False)
        files=sources();(out/'sources.txt').write_text('\n'.join(p.as_posix() for p in files)+'\n')
        record=dict(git_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),part='xc7a100tcsg324-1',period_ns=10,sources={str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in files})
        record['constraints_sha256']=sha(ROOT/'06_fpga/constraints/npu_top_ooc.xdc')
        record['tcl_sha256']=sha(ROOT/'06_fpga/tcl/build_npu_ooc.tcl')
        record['driver_sha256']=sha(Path(__file__))
        (out/'source_hashes.json').write_text(json.dumps(record,indent=2))
    else:
        record=json.loads((out/'source_hashes.json').read_text())
        for name,digest in record['sources'].items():
            if sha(ROOT/name)!=digest:raise ValueError('stale FPGA source '+name)
        if a.stage=='power':
            gate=json.loads((out/'routed_gate.json').read_text())
            if gate['wns_ns']<0 or gate['whs_ns']<0:raise ValueError('route gate')
            if not a.functional_runs:raise ValueError('provide six passing required scenario run paths')
            evidence=[];counts=[]
            for name in a.functional_runs:
                r=Path(name);m=json.loads((r/'manifest.json').read_text());cmp=json.loads((r/'comparison.json').read_text())
                if not cmp['passed']:raise ValueError('functional failure')
                sim=json.loads((r/'logs/simulator_sources.json').read_text())
                sim_hashes={key.replace('\\','/'):digest for key,digest in sim['sources'].items()}
                for key,digest in record['sources'].items():
                    if sim_hashes.get(key)!=digest:raise ValueError('functional/route source mismatch '+key)
                counts.append((len(m['sample_ids']),tuple(m['fields'])))
                evidence.append(dict(run=str(r),comparison_sha256=sha(r/'comparison.json')))
            needed=[(1,('fc1','fc2','fc3','argmax')),(5,('fc1','fc2','fc3','argmax')),(20,('argmax',)),(100,('argmax',)),(200,('argmax',)),(200,('fc3','argmax'))]
            if sorted(counts)!=sorted(needed):raise ValueError('required functional gate set')
            (out/'functional_and_route_pass.json').write_text(json.dumps(dict(route=gate,functional=evidence),indent=2))
    print('FPGA',a.stage,out,flush=True)
    args=[BIN/'vivado.bat','-mode','batch','-source',(ROOT/'06_fpga/tcl/build_npu_ooc.tcl').as_posix(),'-log',a.stage+'.vivado.log','-journal',a.stage+'.jou','-tclargs',ROOT.as_posix(),out.as_posix(),a.stage]
    (out/(a.stage+'_command.json')).write_text(json.dumps([str(x) for x in args],indent=2))
    text=command(args,out,a.stage+'_console.log',a.timeout)
    marker={'synth':'NPU_SYNTH_COMPLETE','implement':'NPU_ROUTE_TIMING_COMPLETE','power':'NPU_POWER_COMPLETE'}[a.stage]
    if marker not in text:raise RuntimeError('missing stage completion marker')
    print(marker,flush=True)
if __name__=='__main__':main()
