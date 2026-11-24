"""OOC implementation; timing failure is reported without changing RTL/constraints."""
from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,re,shutil,subprocess,sys,time
ROOT=Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,x):p.write_text(json.dumps(x,indent=2)+"\n",encoding="utf-8")
def main():
    if len(sys.argv)!=3:raise SystemExit("Usage: run_phase8_impl.py <synthesis-run> <Vivado/bin>")
    synth=Path(sys.argv[1]).resolve()
    sm=json.loads((synth/"metrics.json").read_text())
    manifest=json.loads((synth/"manifest.json").read_text())
    if sm.get("synthesis")!="COMPLETED" or sm.get("bram_tiles",999)>135:
        raise SystemExit("Synthesis/BRAM gate not complete")
    if any(b["ramb36"]+b["ramb18"]==0 or b["lutram"] for b in sm["banks"]):
        raise SystemExit("SRAM mapping gate failed")
    review=synth/"memory_gate_review.json"
    if not review.exists() or json.loads(review.read_text())["status"]!="PASS":
        raise SystemExit("Explicit memory gate review is required")
    rid="npu_phase8_impl_"+datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%fZ")
    out=ROOT/"07_runs"/rid;out.mkdir()
    work=ROOT/"99_build"/rid;work.mkdir()
    print("[RUN] "+str(out),flush=True)
    source=ROOT/"06_fpga/tcl/npu_direct_impl.tcl"
    shutil.copyfile(source,out/"executed.tcl")
    command=[str(Path(sys.argv[2])/"vivado.bat"),"-mode","batch","-nojournal",
             "-log",str(out/"vivado.log"),"-source",str(out/"executed.tcl"),
             "-tclargs",str(synth/"synthesized.dcp"),str(out)]
    rec=dict(command=command,cwd=str(work),synthesis_run=str(synth),part=manifest["part"],
             top=manifest["top"],core_top="npu_top",clock_period_ns=10,
             input_checkpoint_sha256=sha(synth/"synthesized.dcp"),
             script_sha256=sha(out/"executed.tcl"),sources_sha256=manifest["sources_sha256"],
             rtl_sha256=manifest["rtl_sha256"],legacy_project_sha256=manifest["legacy_project_sha256"])
    save(out/"manifest.json",rec)
    result=dict(status="FAIL",implementation="NOT_COMPLETED",timing="NOT_EVALUATED",
                clock_period_ns=10,bmg_used=False,bitstream_generated=False)
    started=time.monotonic()
    try:
        with (out/"process.log").open("w",encoding="utf-8") as stream:
            proc=subprocess.Popen(command,cwd=work,stdout=stream,stderr=subprocess.STDOUT)
            rc=proc.wait(timeout=1800)
        result["return_code"]=rc
        if rc or not (out/"implementation_status.txt").exists():
            raise RuntimeError("Implementation/report generation failed; stop without design changes")
        summary=dict(line.split("=",1) for line in (out/"implementation_status.txt").read_text().splitlines())
        lines=(out/"timing_summary.rpt").read_text().splitlines()
        numbers=None
        for i,line in enumerate(lines):
            if "WNS(ns)" in line:
                for candidate in lines[i+1:i+7]:
                    fields=candidate.split()
                    if len(fields)>=8 and re.fullmatch(r"-?\d+\.\d+",fields[0]):
                        numbers=fields;break
                if numbers:break
        if numbers is None:raise RuntimeError("Missing timing summary numeric row")
        values=dict(wns_ns=float(numbers[0]),tns_ns=float(numbers[1]),
                    whs_ns=float(numbers[4]),ths_ns=float(numbers[5]))
        good=values["wns_ns"]>=0 and values["whs_ns"]>=0 and values["tns_ns"]==0 and values["ths_ns"]==0
        result.update(implementation="COMPLETED",summary=summary,**values,
                      timing="PASS" if good else "FAIL",status="PASS" if good else "TIMING_FAIL",
                      boundary_timing_verified=False,
                      reason="100MHz OOC setup/hold evaluated; no frequency/exception changes")
    except Exception as error:
        result["reason"]=repr(error);print("[STOP] "+repr(error),flush=True)
        if "proc" in locals() and proc.poll() is None:
            subprocess.run(["taskkill","/PID",str(proc.pid),"/T","/F"],capture_output=True)
    finally:
        result["elapsed_seconds"]=round(time.monotonic()-started,3)
        result["rtl_changed"]=[p for p,h in rec["rtl_sha256"].items() if sha(ROOT/p)!=h]
        result["legacy_project_changed"]=[p for p,h in rec["legacy_project_sha256"].items() if sha(p)!=h]
        if result["rtl_changed"] or result["legacy_project_changed"]:result["status"]="FAIL"
        save(out/"metrics.json",result)
    print("[PHASE8_IMPLEMENTATION] "+result["status"],flush=True)
    return int(result["status"]!="PASS")
if __name__=="__main__":raise SystemExit(main())
