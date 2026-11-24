"""Phase 7: first 1/5/100/200 MNIST images, one command, unchanged NPU RTL."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import threading
import time

sys.dont_write_bytecode = True
import numpy as np
import psutil
import torch
import torchvision
import assembler
import golden_compare
import memory_allocator as alloc
import run_phase1 as scalar
import weight_packer as packer

ROOT = scalar.ROOT
legacy = scalar.legacy
RTL = scalar.SOURCES[:-1]
NEW = ["90_scripts/npu/"+name+".py" for name in
       ("run_scenario","assembler","memory_allocator","weight_packer","golden_compare")]
NEW += ["05_tb/npu/tb_npu_application.sv","90_scripts/npu/tests/test_application.py"]

def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

class MemoryWatch:
    """Sample total process-tree RSS, plus Windows process peak working sets."""
    def __enter__(self):
        self.stop = threading.Event()
        self.result = dict(sample_interval_seconds=0.1,peak_sampled_tree_rss_bytes=0,processes={})
        self.thread = threading.Thread(target=self.poll,daemon=True)
        self.thread.start()
        return self.result

    def poll(self):
        root = psutil.Process()
        while not self.stop.is_set():
            total = 0
            try:
                processes = [root]+root.children(recursive=True)
            except psutil.Error:
                processes = [root]
            for p in processes:
                try:
                    m = p.memory_info()
                    total += m.rss
                    key = str(p.pid)
                    old = self.result["processes"].get(key,dict(name=p.name(),peak_rss_bytes=0))
                    old["peak_rss_bytes"] = max(old["peak_rss_bytes"],m.rss,getattr(m,"peak_wset",0))
                    self.result["processes"][key] = old
                except psutil.Error:
                    pass
            self.result["peak_sampled_tree_rss_bytes"] = max(self.result["peak_sampled_tree_rss_bytes"],total)
            self.stop.wait(0.1)

    def __exit__(self,*args):
        self.stop.set()
        self.thread.join()

def g0(assets,predictions,layers):
    # Compare batched INT64/wrap reference to the existing explicitly-configured model.
    from src.quantization import IntegerMLP
    old = IntegerMLP(assets["params"],torch.device("cpu")).forward(
        assets["input_fp32"],assets["config"],trace=True,verify_cpu=True)
    for i,name in enumerate(("fc1","fc2","fc3")):
        if not np.array_equal(old["trace"][name]["q"].numpy(),layers[i]):
            raise RuntimeError("G0 existing IntegerMLP layer mismatch "+name)
    if not np.array_equal(old["q"].argmax(1).numpy(),predictions):
        raise RuntimeError("G0 existing IntegerMLP prediction mismatch")
    # Independently check physical packed addressing using the Phase 5 scalar kernel.
    for sample in sorted(set((0,min(7,len(predictions)-1),len(predictions)-1))):
        mem = {}
        for bank,words in enumerate(assets["banks"]):
            mem.update({0x80040000+bank*0x20000+4*i:int(v) for i,v in enumerate(words)})
        mem.update({0x800C0000+4*i:int(v) for i,v in enumerate(assets["bias"])})
        mem.update({0x80000000+4*i:int(v) for i,v in enumerate(packer.pack8(assets["input8"][sample]))})
        for layer,cfg in enumerate(assembler.LAYERS):
            actual = assembler.p5.kernel(mem,cfg)
            padded = np.pad(layers[layer][sample],(0,(-layers[layer].shape[1])%4))
            expected = packer.pack8(padded)
            if actual!=expected.tolist():
                raise RuntimeError("G0 Phase 5 packed kernel mismatch")
            mem.update({cfg[2]+4*i:int(v) for i,v in enumerate(actual)})
    # Existing Legacy sample-7 artifact is a required reproducibility anchor.
    source = assembler.p5.SOURCE
    manifest = json.loads((source/"manifest.json").read_text(encoding="utf-8"))
    if manifest["checkpoint_sha256"]!=sha(assets["paths"][0]):
        raise RuntimeError("G0 baseline checkpoint hash mismatch")
    for name,actual in [(f"weight_bank{i}",w) for i,w in enumerate(assets["banks"])]+[("bias",assets["bias"])]:
        rel="memory/"+name+".hex"
        p=source/rel
        if sha(p)!=manifest["files_sha256"][rel]:
            raise RuntimeError("G0 saved Legacy artifact hash mismatch")
        if not np.array_equal(np.array([int(x,16) for x in p.read_text().split()],dtype=np.uint32),actual):
            raise RuntimeError("G0 Legacy packed model mismatch")
    return dict(status="PASS",existing_model_images=len(predictions),
                phase5_kernel_samples=sorted(set((0,min(7,len(predictions)-1),len(predictions)-1))),
                legacy_model_words=4*29280+163,legacy_source=str(source))

def write_hex(path,words):
    with path.open("w",encoding="ascii",newline="\n") as f:
        for word in np.asarray(words).reshape(-1):
            f.write(f"{int(word)&0xffffffff:08x}\n")

def prepare(directory,count,assets,predictions,layers):
    directory.mkdir(parents=True)
    debug = count==1
    layout = alloc.application_layout(count,debug)
    a,model_loads = assembler.build_program(layout,debug)
    write_hex(directory/"imem.hex",a.words)
    (directory/"program.asm").write_text("\n".join(a.listing)+"\n",encoding="ascii")
    (directory/"program.bin").write_bytes(np.asarray(a.words,dtype="<u4").tobytes())
    blocks = [*assets["banks"],assets["bias"],packer.pack8(assets["input8"][:count].reshape(-1)),
              np.full(count,0xffffffff,dtype=np.uint32)]
    if debug:
        blocks.append(np.full(163,0xffffffff,dtype=np.uint32))
    memory = np.concatenate(blocks)
    if len(memory)*4!=layout.cursor-alloc.BASE:
        raise RuntimeError("allocator/HEX layout mismatch")
    write_hex(directory/"dmem.hex",memory)
    write_hex(directory/"golden_prediction.hex",predictions[:count])
    debug_expected = np.concatenate([packer.pack8(np.pad(x[0],(0,(-x.shape[1])%4))) for x in layers])
    write_hex(directory/"golden_layers.hex",debug_expected if debug else [])
    loop_words = (a.pc-4-a.labels["LOOP"])//4
    dynamic_steps = a.labels["LOOP"]//4+count*loop_words+1
    r=layout.regions
    header = [f"localparam integer IMEM_BYTES=65536,DMEM_BYTES={alloc.DMEM_BYTES};",
              f"localparam integer IMAGE_COUNT={count},CODE_WORDS={len(a.words)},DMEM_INIT_WORDS={len(memory)};",
              f"localparam integer EXPECTED_INSTRUCTIONS={dynamic_steps},MAX_CYCLES={1000000+40000*count};",
              f"localparam bit DEBUG_LAYERS={int(debug)};",
              f"localparam logic [31:0] INPUT_BASE=32'h{r['input'].start:08x},INPUT_END=32'h{r['input'].end:08x};",
              f"localparam logic [31:0] PRED_BASE=32'h{r['prediction'].start:08x},END_PC=32'h{a.pc-4:08x};",
              f"localparam logic [31:0] LAYER_BASE=32'h{r['layers'].start if debug else 0:08x};"]
    for field in ("src","dst","bytes"):
        header += [f"function automatic [31:0] model_{field}(input integer i);","case(i)"]
        header += [f"{i}: model_{field}=32'h{item['length' if field=='bytes' else field]:08x};"
                   for i,item in enumerate(model_loads)]
        header += [f"default:model_{field}=0;","endcase","endfunction"]
    header += ["function automatic [31:0] fc_config(input integer layer,input integer i);","case(layer*10+i)"]
    header += [f"{l*10+i}:fc_config=32'h{v&0xffffffff:08x};"
               for l,cfg in enumerate(assembler.LAYERS) for i,v in enumerate(cfg)]
    header += ["default:fc_config=0;","endcase","endfunction"]
    (directory/"npu_application_profile.vh").write_text("\n".join(header)+"\n",encoding="ascii")
    np.savez_compressed(directory/"golden.npz",input8=assets["input8"][:count],
                        labels=assets["labels"][:count],prediction=predictions[:count],
                        fc1=layers[0][:count],fc2=layers[1][:count],fc3=layers[2][:count])
    info=dict(images=count,image_indices=list(range(count)),memory=layout.manifest(),
              program_words=len(a.words),program_bytes=a.pc,end_pc=a.pc-4,loop_pc=a.labels["LOOP"],
              expected_instructions=dynamic_steps,model_loads=model_loads,
              timer=False,waveform=False,intermediate_store=debug,
              gpr_live_in_loop=[1,3,6,7],setaddr_clobber=4)
    save(directory/"manifest.json",info)
    info["files_sha256"]={p.name:sha(p) for p in directory.iterdir() if p.is_file() and p.name!="manifest.json"}
    save(directory/"manifest.json",info)
    return info,debug_expected

def observed(directory,info,golden,labels,debug_expected):
    rows = [line.split() for line in (directory/"observed_prediction.txt").read_text().splitlines()]
    if len(rows)!=info["images"] or any(len(r)!=2 for r in rows):
        raise RuntimeError("observed Prediction count/format")
    regions = {r["name"]:r for r in info["memory"]["regions"]}
    addresses=[int(r[0],16) for r in rows]
    if addresses!=list(range(regions["prediction"]["start"],regions["prediction"]["end"],4)):
        raise RuntimeError("observed Prediction addresses")
    result=golden_compare.compare([int(r[1],16) for r in rows],golden,labels)
    save(directory/"comparison.json",result)
    if result["golden_mismatches"]:
        raise RuntimeError("RTL/Golden Prediction mismatch")
    rows = [line.split() for line in (directory/"observed_layers.txt").read_text().splitlines()]
    if info["intermediate_store"]:
        if len(rows)!=163 or [int(r[0],16) for r in rows]!=list(range(regions["layers"]["start"],regions["layers"]["end"],4)):
            raise RuntimeError("observed layer addresses/count")
        if [int(r[1],16) for r in rows]!=debug_expected.tolist():
            raise RuntimeError("RTL/Golden layer mismatch")
    elif rows:
        raise RuntimeError("unexpected intermediate STORE")
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vivado-bin",type=Path,required=True)
    parser.add_argument("--counts",type=int,nargs="+",default=[1,5,100,200])
    parser.add_argument("--wall-timeout",type=float,default=1800)
    parser.add_argument("--no-regressions",action="store_true",help="development run only; not the final Gate")
    args=parser.parse_args()
    if args.counts!=sorted(set(args.counts)) or any(n not in (1,5,100,200) for n in args.counts):
        parser.error("counts must be an ascending subset of 1 5 100 200")
    if not 0<args.wall_timeout<float("inf"):
        parser.error("wall timeout must be positive/finite")
    if sys.version_info[:2]!=(3,11) or Path(sys.prefix).name.lower()!="aissd":
        parser.error("use the conda aissd Python 3.11 environment")
    run_id="npu_phase7_"+datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%fZ")
    out=ROOT/"07_runs"/run_id;out.mkdir(parents=True)
    build=ROOT/"99_build"/run_id;build.mkdir(parents=True)
    print("[RUN] "+str(out),flush=True)
    tracked=subprocess.check_output(["git","ls-files"],cwd=ROOT,text=True).splitlines()
    protected=[p for p in tracked if p.startswith(("03_model/","04_rtl/","05_tb/","90_scripts/","01_configs/"))]
    before={p:sha(ROOT/p) for p in protected}
    record=dict(phase=7,git=legacy.git_state(ROOT),command=sys.argv,python=sys.executable,
                versions=dict(python=platform.python_version(),torch=torch.__version__,
                              torchvision=torchvision.__version__,numpy=np.__version__,psutil=psutil.__version__),
                cuda_available=torch.cuda.is_available(),stages=[],sources_sha256={})
    metrics=dict(status="FAIL",gates=[],regressions=[],phase8_started=False,mnist10000_executed=False)
    code=1
    try:
        tools=legacy.find_tools(args.vivado_bin)
        snap=out/"source_snapshot"
        sources=set(RTL+NEW+["90_scripts/run.py","90_scripts/npu/run_phase1.py","90_scripts/npu/gemm_config.py"]+
                    [p.relative_to(ROOT).as_posix() for p in (ROOT/"90_scripts/npu").glob("phase*_vectors.py")]+
                    ["03_model/generate_golden.py"]+
                    [p.relative_to(ROOT).as_posix() for p in (ROOT/"03_model/src").glob("*.py")])
        for name in sorted(sources):
            p=snap/name;p.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/name,p);record["sources_sha256"][name]=sha(p)
        unitlog=out/"application_unit.log"
        command=[sys.executable,"-X","utf8","-B","-m","unittest","discover","-s","90_scripts/npu/tests","-v"]
        with unitlog.open("w",encoding="utf-8") as stream:
            rc=subprocess.run(command,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,timeout=180).returncode
        record["application_unit_command"]=command
        if rc:raise RuntimeError("Application Python unit tests failed; see "+str(unitlog))
        started=time.monotonic()
        assets=packer.load_assets(max(args.counts))
        golden,layers=golden_compare.infer(assets["input8"],assets["weights"],assets["biases"])
        result=g0(assets,golden,layers)
        result.update(gate="G0",elapsed_seconds=round(time.monotonic()-started,3),model_loads=assets["model_loads"])
        metrics["gates"].append(result)
        record.update(dataset_model=[dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p)) for p in assets["paths"]],
                      quantization=assets["config"].as_dict(),preprocessing=assets["preprocessing"],
                      offline_rounding="nearest ties to even",arithmetic="signed INT32 wrap; ReLU; arithmetic shift; signed INT8 saturation")
        print("[G0] PASS",flush=True)
        for count in args.counts:
            name={1:"G1",5:"G2",100:"G3",200:"G4"}[count]
            data=out/"data"/name
            info,debug_expected=prepare(data,count,assets,golden,layers)
            work=build/name;work.mkdir()
            logs=out/"logs"/name;logs.mkdir(parents=True)
            commands=[
                ("compile","xvlog",["-sv","-i",data.as_posix(),*[(snap/p).as_posix() for p in RTL],
                                   (snap/"05_tb/npu/tb_npu_application.sv").as_posix(),"-log","xvlog.log"]),
                ("elaborate","xelab",["work.tb_npu_application","-s","application_sim","-debug","off","-timescale","1ns/1ps","-log","xelab.log"]),
                ("simulate","xsim",["application_sim","-onerror","quit","-onfinish","quit","-R",
                                   "-testplusarg","DATA_DIR="+data.as_posix(),"-log","xsim.log"])]
            print(f"[{name}] images={count}",flush=True)
            for stage,tool,arguments in commands:
                with MemoryWatch() as memory:
                    rc,text=legacy.run_stage(name+"_"+stage,tools[tool],arguments,work,logs,
                                             args.wall_timeout,record["stages"])
                record["stages"][-1]["host_memory"]=memory
                if rc or legacy.ERROR_LINE.search(text):
                    raise RuntimeError(name+" "+stage+" failed; see "+str(logs))
                if stage=="simulate":
                    if len(re.findall(r"^\[APPLICATION\] result=PASS ",text,re.M))!=1:
                        raise RuntimeError(name+" missing Application PASS summary")
                    simulation=record["stages"][-1]
            totals=[int(x) for x in (data/"tb_summary.txt").read_text().split()]
            if len(totals)!=9 or totals[:6]!=[count,count,5+count,3*count,count,count] or totals[6]!=info["expected_instructions"]:
                raise RuntimeError(name+" incomplete TB counters")
            comparison=observed(data,info,golden[:count],assets["labels"][:count],debug_expected)
            gate=dict(gate=name,status="PASS",**comparison,cycles=totals[7],layer_words=totals[8],
                      simulation_seconds=simulation["elapsed_seconds"],host_memory=simulation["host_memory"],
                      program_words=info["program_words"],instructions=totals[6],loads=totals[2],
                      gemm=totals[3],argmax=totals[4],timer=False,waveform=False,intermediate_store=count==1)
            metrics["gates"].append(gate)
            save(out/"metrics.json",metrics);save(out/"manifest.json",record)
            print(f"[{name}] PASS golden={count}/{count} correct={comparison['correct']}/{count} cycles={totals[7]}",flush=True)
        if not args.no_regressions:
            for phase in ["phase1","phase2","phase3","phase4","phase5","phase6","fault_priority"]:
                command=[sys.executable,"-X","utf8","-B",f"90_scripts/npu/run_{phase}.py",
                         "--vivado-bin",str(args.vivado_bin)]
                if phase=="phase1":command+=["--legacy"]
                print("[REGRESSION] "+phase,flush=True)
                log=out/(phase+".log")
                with log.open("w",encoding="utf-8") as stream:
                    rc=subprocess.run(command,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,
                                      timeout=1800).returncode
                text=log.read_text(encoding="utf-8",errors="replace")
                paths=re.findall(r"^\[RUN\] (.+)$",text,re.M)
                item=dict(name=phase,command=command,return_code=rc,log=str(log),status="FAIL")
                metrics["regressions"].append(item)
                if rc or not paths:raise RuntimeError("regression failed "+phase+"; see "+str(log))
                child=json.loads((Path(paths[-1].strip())/"metrics.json").read_text(encoding="utf-8"))
                if child["status"]!="PASS":raise RuntimeError("regression incomplete "+phase)
                item.update(status="PASS",run=paths[-1].strip(),metrics_sha256=sha(Path(paths[-1].strip())/"metrics.json"))
                print("[REGRESSION_PASS] "+phase,flush=True)
        changed=[p for p,h in before.items() if not (ROOT/p).exists() or sha(ROOT/p)!=h]
        metrics["protected_sources"]=dict(files=len(before),changed=changed)
        if changed:raise RuntimeError("protected RTL/model/test source changed")
        full=args.counts==[1,5,100,200] and not args.no_regressions
        metrics.update(status="PASS",phase7_gate="PASS" if full else "PARTIAL",reason="all requested gates completed")
        code=0
    except Exception as error:
        metrics.update(status="FAIL",phase7_gate="FAIL",reason=repr(error))
        print("[STOP] "+repr(error),flush=True)
    finally:
        metrics["protected_sources"]=dict(files=len(before),changed=[
            p for p,h in before.items() if not (ROOT/p).exists() or sha(ROOT/p)!=h])
        record["finished_utc"]=datetime.now(timezone.utc).isoformat()
        record["source_changed_during_run"]=[p for p,h in record["sources_sha256"].items() if sha(ROOT/p)!=h]
        if record["source_changed_during_run"] or metrics["protected_sources"]["changed"]:
            metrics.update(status="FAIL",phase7_gate="FAIL",reason="source integrity failure");code=1
        save(out/"metrics.json",metrics);save(out/"manifest.json",record)
    print("[PHASE7] "+metrics["status"]+" "+metrics.get("phase7_gate","FAIL"),flush=True)
    return code

if __name__=="__main__":
    raise SystemExit(main())
