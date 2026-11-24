"""Phase 8 first synthesis only: unchanged npu_top and SRAM RTL, no IP generation."""
from datetime import datetime,timezone
from pathlib import Path
import ast
import csv
import hashlib
import json
import subprocess
import sys
import time
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def save(path,value):
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def main():
    if len(sys.argv) not in (2,3) or (len(sys.argv)==3 and sys.argv[2]!="--fpga-wrapper"):
        raise SystemExit("Usage: run_phase8_synth.py <Vivado/bin>")
    tree=ast.parse((ROOT/"90_scripts/npu/run_phase1.py").read_text(encoding="utf-8"))
    sources=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign)
                 and any(isinstance(t,ast.Name) and t.id=="SOURCES" for t in n.targets))[:-1]
    if any(not p.startswith("04_rtl/") for p in sources) or "04_rtl/controller/npu_top.sv" not in sources:
        raise RuntimeError("invalid NPU synthesis source list")
    wrapper=len(sys.argv)==3
    top="npu_fpga_top" if wrapper else "npu_top"
    if wrapper:sources += ["06_fpga/rtl/npu_reset_sync.sv","06_fpga/rtl/npu_fpga_top.sv"]
    run_id="npu_phase8_synth_"+datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%fZ")
    out=ROOT/"07_runs"/run_id;out.mkdir(parents=True,exist_ok=False)
    work=ROOT/"99_build"/run_id;work.mkdir(parents=True,exist_ok=False)
    print("[RUN] "+str(out),flush=True)
    all_rtl={p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/"04_rtl").rglob("*.sv")}
    old_project=ROOT/"99_build/vivado_mlp_top_ooc/mlp_top_ooc.xpr"
    guard={str(old_project):sha(old_project),str(ROOT/"06_fpga/constraints/mlp_top_ooc.xdc"):sha(ROOT/"06_fpga/constraints/mlp_top_ooc.xdc")}
    manifest=dict(phase=8,stage="fpga_reset_wrapper_synthesis" if wrapper else "first_unchanged_rtl_synthesis",
        head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
        branch=subprocess.check_output(["git","branch","--show-current"],cwd=ROOT,text=True).strip(),
        part="xc7a100tcsg324-1",top=top,clock_period_ns=10,
        bmg_used=False,implementation_executed=False,rtl_sha256=all_rtl,
        legacy_project_sha256=guard,sources_sha256={})
    snapshot=out/"source_snapshot"
    import shutil
    for name in sources+["06_fpga/tcl/npu_direct_synth.tcl","06_fpga/constraints/npu_direct_ooc.xdc","90_scripts/npu/run_phase8_synth.py"]:
        target=snapshot/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/name,target);manifest["sources_sha256"][name]=sha(target)
    source_list=out/"sources.txt"
    source_list.write_text("\n".join((snapshot/p).as_posix() for p in sources)+"\n",encoding="utf-8")
    command=[str(Path(sys.argv[1])/"vivado.bat"),"-mode","batch","-nojournal",
             "-log",str(out/"vivado.log"),"-source",str(snapshot/"06_fpga/tcl/npu_direct_synth.tcl"),
             "-tclargs",str(source_list),str(snapshot/"06_fpga/constraints/npu_direct_ooc.xdc"),str(out),top]
    manifest.update(command=command,cwd=str(work))
    save(out/"manifest.json",manifest)
    metrics=dict(status="FAIL",synthesis="NOT_COMPLETED",memory_gate="NOT_EVALUATED",
                 implementation="NOT_RUN",rtl_modified=False)
    start=time.monotonic();rc=1
    try:
        with (out/"process.log").open("w",encoding="utf-8") as log:
            process=subprocess.Popen(command,cwd=work,stdout=log,stderr=subprocess.STDOUT)
            rc=process.wait(timeout=1800)
        metrics["return_code"]=rc
        if rc or not (out/"synthesis_status.txt").exists():
            raise RuntimeError("Synthesis/report generation failed; no implementation launched")
        summary=dict(line.split("=",1) for line in (out/"synthesis_status.txt").read_text().splitlines())
        with (out/"banks.tsv").open() as f:
            banks=[{k:int(v) for k,v in row.items()} for row in csv.DictReader(f,delimiter="\t")]
        tiles=int(summary["ramb36"])+int(summary["ramb18"])/2
        mapped=len(banks)==7 and all(b["ramb36"]+b["ramb18"]>0 and b["lutram"]==0 for b in banks)
        metrics.update(synthesis="COMPLETED",summary=summary,banks=banks,
                       bram_tiles=tiles,bram_percent=100*tiles/135,remaining_bram_tiles=135-tiles)
        if not mapped or tiles>135:
            metrics["memory_gate"]="FAIL"
            raise RuntimeError("BRAM inference/capacity gate failed; RTL unchanged; implementation blocked")
        metrics.update(status="SYNTHESIS_REVIEW_REQUIRED",memory_gate="MAPPED_REVIEW_REQUIRED",
                       reason="Review RAM utilization, latency/reset mapping and warnings before next gate")
        print("[SYNTHESIS] completed, BRAM tiles="+str(tiles),flush=True)
        rc=0
    except Exception as error:
        metrics["reason"]=repr(error)
        print("[STOP] "+repr(error),flush=True)
        if "process" in locals() and process.poll() is None:
            subprocess.run(["taskkill","/PID",str(process.pid),"/T","/F"],capture_output=True)
        rc=1
    finally:
        metrics["elapsed_seconds"]=round(time.monotonic()-start,3)
        metrics["rtl_changed"]=[p for p,h in all_rtl.items() if sha(ROOT/p)!=h]
        metrics["legacy_project_changed"]=[p for p,h in guard.items() if sha(p)!=h]
        if metrics["rtl_changed"] or metrics["legacy_project_changed"]:
            metrics.update(status="FAIL",reason="Protected RTL/project source changed");rc=1
        save(out/"metrics.json",metrics)
        manifest["finished_utc"]=datetime.now(timezone.utc).isoformat()
        save(out/"manifest.json",manifest)
    print("[PHASE8_FIRST_SYNTH] "+metrics["status"],flush=True)
    return rc

if __name__=="__main__":
    raise SystemExit(main())
