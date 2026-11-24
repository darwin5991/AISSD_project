"""Preserved Phase 1..7, fault, Python and Legacy regression after FPGA reset wrapper."""
from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,subprocess,sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
VIVADO="D:/AMDDesignTools/2025.2/Vivado/bin"

def main():
    out=ROOT/"07_runs"/("npu_phase8_regression_"+datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%fZ"))
    out.mkdir();print("[RUN] "+str(out),flush=True)
    tracked=subprocess.check_output(["git","ls-files"],cwd=ROOT,text=True).splitlines()
    guard={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in tracked
           if p.startswith(("04_rtl/","05_tb/","90_scripts/","03_model/","06_fpga/"))}
    m=dict(status="FAIL",results=[],protected_sources=len(guard))
    try:
        for phase in ["phase1","phase2","phase3","phase4","phase5","phase6","fault_priority","scenario"]:
            command=[sys.executable,"-X","utf8","-B",f"90_scripts/npu/run_{phase}.py","--vivado-bin",VIVADO]
            if phase=="phase1":command+=["--legacy"]
            if phase=="scenario":command+=["--counts","1","200","--no-regressions"]
            print("[REGRESSION] "+phase,flush=True)
            log=out/(phase+".log")
            with log.open("w",encoding="utf-8") as f:
                rc=subprocess.run(command,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,timeout=1800).returncode
            import re
            paths=re.findall(r"^\[RUN\] (.+)$",log.read_text(encoding="utf-8",errors="replace"),re.M)
            item=dict(name=phase,command=command,return_code=rc,status="FAIL",log=str(log))
            m["results"].append(item)
            if rc or not paths:raise RuntimeError("regression failed "+phase)
            metrics=Path(paths[-1].strip())/"metrics.json"
            child=json.loads(metrics.read_text(encoding="utf-8"))
            if child["status"]!="PASS":raise RuntimeError("incomplete regression "+phase)
            item.update(status="PASS",run=str(metrics.parent),metrics_sha256=hashlib.sha256(metrics.read_bytes()).hexdigest())
            print("[REGRESSION_PASS] "+phase,flush=True)
        m["status"]="PASS"
    except Exception as error:
        m["reason"]=repr(error);print("[STOP] "+repr(error),flush=True)
    finally:
        m["source_changed"]=[p for p,h in guard.items() if hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h]
        if m["source_changed"]:m["status"]="FAIL"
        (out/"metrics.json").write_text(json.dumps(m,indent=2)+"\n",encoding="utf-8")
    print("[PHASE8_REGRESSION] "+m["status"],flush=True)
    return int(m["status"]!="PASS")

if __name__=="__main__":raise SystemExit(main())
